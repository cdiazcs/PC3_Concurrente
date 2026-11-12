"""REAL RabbitMQ gradient computation by independent local worker processes."""
from dataclasses import replace
import hashlib
import os
import signal
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from test_gradient_aggregation import examples
from cnn_python.dataset import DEFAULT_DATASET,load_split
from cnn_python.gradient_protocol import make_tasks,execute_task,aggregate_gradients,encode
from cnn_python.train import initial_weights
from cnn_python.training_backends import SequentialBackend
from cnn_python.training_amqp import AMQPBackend,training_config
from cnn_python.model_state import ModelState
from cnn_python.train_synchronous import train_sync


@unittest.skipUnless(os.environ.get('PC3_RABBIT_INTEGRATION')=='1','real RabbitMQ training opt-in not enabled')
class DistributedTrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pika
        cls.pika=pika;cls.root=Path(__file__).resolve().parents[1]
        cls.folder=cls.root/'build'/('training-test-'+uuid.uuid4().hex);cls.folder.mkdir(parents=True)
        token=uuid.uuid4().hex;cls.cfg=replace(training_config(),request_queue='train-test-'+token,
            result_queue='train-results-'+token,retry_queue='train-retry-'+token,error_queue='train-errors-'+token)
        cls.data=load_split(split='train');cls.validation=load_split(split='validation')
        cls.digest=hashlib.sha256(DEFAULT_DATASET.read_bytes()).hexdigest()
        cls.processes=[];cls.logs=[];cls.addClassCleanup(cls.cleanup)
        cls.start_workers(2,1)

    @classmethod
    def start_workers(cls,count,local_processes):
        existing=sum(p.poll() is None for p in cls.processes)
        env={**os.environ,'IA_TRAIN_QUEUE':cls.cfg.request_queue,'IA_TRAIN_RESULT_QUEUE':cls.cfg.result_queue,
             'IA_TRAIN_RETRY_QUEUE':cls.cfg.retry_queue,'IA_TRAIN_ERROR_QUEUE':cls.cfg.error_queue,
             'IA_TRAIN_LOCAL_PROCESSES':str(local_processes),'IA_TRAIN_DATASET':str(DEFAULT_DATASET)}
        for i in range(count):
            log=(cls.folder/f'worker-{len(cls.processes)}.log').open('w');cls.logs.append(log)
            cls.processes.append(subprocess.Popen([sys.executable,'workers/python/training_worker.py'],cwd=cls.root,
                env={**env,'IA_TRAIN_WORKER_ID':f'worker-{i}'},stdout=log,stderr=subprocess.STDOUT))
        backend=AMQPBackend(config=cls.cfg);end=time.monotonic()+20
        try:
            while time.monotonic()<end:
                status=backend.channel.queue_declare(cls.cfg.request_queue,passive=True).method
                if status.consumer_count==existing+count:return
                time.sleep(.05)
            raise RuntimeError('training_workers_not_ready')
        finally:backend.close()

    @classmethod
    def stop_workers(cls):
        for process in cls.processes:
            if process.poll() is None:process.terminate()
        for process in cls.processes:
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)

    @classmethod
    def cleanup(cls):
        cls.stop_workers()
        try:
            backend=AMQPBackend(config=cls.cfg)
            for q in (cls.cfg.request_queue,cls.cfg.result_queue,cls.cfg.retry_queue,cls.cfg.error_queue):backend.channel.queue_delete(q)
            backend.close()
        finally:
            for log in cls.logs:log.close()

    def test_a_real_gradients_and_training_same_as_sequential(self):
        backend=AMQPBackend(config=self.cfg,partitions=3,timeout=5)
        try:
            weights=initial_weights(23);indices=list(range(7))
            tasks=make_tasks('real-train',1,0,0,weights,indices,self.digest,3)
            results=backend.map(tasks)
            expected=[execute_task(t,self.data,self.digest) for t in tasks]
            _,a=aggregate_gradients(tasks,results);_,b=aggregate_gradients(tasks,expected)
            self.assertLess(max(abs(x-y) for k in a for x,y in zip(a[k],b[k])),1e-12)
            self.assertGreaterEqual(len({r['pid'] for r in results}),2)
            subset=[i for c in range(3) for i in range(c*240,c*240+4)]
            w,report,state=train_sync(self.data,self.validation,self.digest,SequentialBackend(self.data,self.digest),
                epochs=2,batch_size=5,seed=23,indices=subset)
            v,other,distributed=train_sync(self.data,self.validation,self.digest,backend,
                epochs=2,batch_size=5,seed=23,indices=subset)
            self.assertLess(max(abs(x-y) for k in w for x,y in zip(w[k],v[k])),1e-10)
            self.assertEqual(distributed.optimizer.step,state.optimizer.step)
        finally:backend.close()

    def test_b_duplicate_stale_and_failed_tasks_never_double_apply(self):
        backend=AMQPBackend(config=self.cfg,partitions=2,timeout=3)
        try:
            weights=initial_weights(23);state=ModelState(weights)
            tasks=make_tasks('dedup',1,0,0,weights,list(range(6)),self.digest,2)
            result=execute_task(tasks[0],self.data,self.digest)
            for _ in range(2):
                backend.channel.basic_publish(exchange='',routing_key=backend.reply_queue,body=encode(result),mandatory=True,
                    properties=self.pika.BasicProperties(correlation_id=result['taskId']))
            loss,gradient=aggregate_gradients(tasks,backend.map(tasks))
            self.assertTrue(state.commit('1:0',0,gradient));self.assertFalse(state.commit('1:0',0,gradient))
            self.assertEqual(state.optimizer.step,1)
            next_tasks=make_tasks('dedup',1,1,1,state.weights,list(range(6)),self.digest,2)
            stale=execute_task(next_tasks[0],self.data,self.digest);stale['modelVersion']=0
            backend.channel.basic_publish(exchange='',routing_key=backend.reply_queue,body=encode(stale),mandatory=True,
                properties=self.pika.BasicProperties(correlation_id=stale['taskId']))
            with self.assertRaises(ValueError):backend.map(next_tasks)
            self.assertEqual(state.version,1)
        finally:backend.close()

    def test_c_timeout_missing_workers_and_bad_dataset_checkpoint(self):
        token=uuid.uuid4().hex
        empty=replace(self.cfg,request_queue='train-empty-'+token,result_queue='train-empty-result-'+token,
                      retry_queue='train-empty-retry-'+token,error_queue='train-empty-error-'+token)
        backend=AMQPBackend(config=empty,timeout=.15,max_attempts=2)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                checkpoint=Path(tmp)/'state.json'
                with self.assertRaises(TimeoutError):train_sync(self.data,self.validation,self.digest,backend,
                    epochs=1,batch_size=2,indices=[0,1],checkpoint=checkpoint)
                state,_=ModelState.load(checkpoint);self.assertEqual(state.version,0)
                self.assertGreater(backend.stats['retries'],0)
            for q in (empty.request_queue,empty.result_queue,empty.retry_queue,empty.error_queue):
                backend.channel.queue_delete(q)
        finally:backend.close()
        backend=AMQPBackend(config=self.cfg,timeout=2)
        try:
            tasks=make_tasks('wrong-dataset',1,0,0,initial_weights(23),[0],'wrong',1)
            with self.assertRaisesRegex(ValueError,'worker_error'):backend.map(tasks)
        finally:backend.close()

    def test_d_parallel_local_inside_amqp_workers(self):
        self.stop_workers();self.start_workers(2,2)
        backend=AMQPBackend(config=self.cfg,partitions=2,timeout=10)
        try:
            tasks=make_tasks('amqp-local-parallel',1,0,0,initial_weights(23),list(range(24)),self.digest,2)
            result=backend.map(tasks)
            self.assertTrue(all(len(r['localWorkers'])>=2 for r in result))
            _,a=aggregate_gradients(tasks,result)
            _,b=aggregate_gradients(tasks,[execute_task(t,self.data,self.digest) for t in tasks])
            self.assertLess(max(abs(x-y) for k in a for x,y in zip(a[k],b[k])),1e-12)
        finally:backend.close();self.stop_workers();self.start_workers(2,1)

    def test_e_malformed_task_error_and_worker_survives(self):
        backend=AMQPBackend(config=self.cfg,timeout=3)
        try:
            backend.channel.basic_publish(exchange='',routing_key=self.cfg.request_queue,
                body=b'{"taskId":1,"modelVersion":1e999}',mandatory=True,
                properties=self.pika.BasicProperties(correlation_id='bad-training',reply_to=backend.reply_queue))
            end=time.monotonic()+5
            while time.monotonic()<end:
                method,props,body=backend.channel.basic_get(backend.reply_queue,auto_ack=False)
                if method:
                    from cnn_python.gradient_protocol import decode
                    result=decode(body);backend.channel.basic_ack(method.delivery_tag)
                    self.assertEqual(result['tipo'],'TRAIN_ERROR');self.assertEqual(result['taskId'],'bad-training')
                    break
                time.sleep(.02)
            else:self.fail('missing controlled TRAIN_ERROR')
            tasks=make_tasks('after-bad',1,0,0,initial_weights(23),[0,1],self.digest,2)
            self.assertEqual(len(backend.map(tasks)),2)
        finally:backend.close()

    @unittest.skipUnless(hasattr(signal,'SIGSTOP'),'in-flight process suspension test requires POSIX')
    def test_f_worker_disconnect_requeues_assigned_tasks(self):
        workers=[p for p in self.processes if p.poll() is None]
        for process in workers:os.kill(process.pid,signal.SIGSTOP)
        tasks=make_tasks('disconnect-training',1,0,0,initial_weights(23),list(range(12)),self.digest,2)
        def collect():
            # Each Pika connection is created and used in this one thread.
            backend=AMQPBackend(config=self.cfg,partitions=2,timeout=5)
            try:return backend.map(tasks)
            finally:backend.close()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(collect)
                time.sleep(.25)
                workers[0].kill();workers[0].wait(timeout=5)
                os.kill(workers[1].pid,signal.SIGCONT)
                result=future.result(timeout=15)
            _,gradient=aggregate_gradients(tasks,result)
            state=ModelState(initial_weights(23))
            self.assertTrue(state.commit('1:0',0,gradient));self.assertFalse(state.commit('1:0',0,gradient))
            self.assertEqual(state.optimizer.step,1)
        finally:
            for process in workers:
                if process.poll() is None:os.kill(process.pid,signal.SIGCONT)
            self.start_workers(1,1)


if __name__=='__main__':unittest.main(verbosity=2)
