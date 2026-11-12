"""Broker REAL opt-in: PC3_RABBIT_INTEGRATION=1. Uses only fresh test queues."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
import uuid
from test_rabbit_messages import config, message
from workers.python.rabbit_config import Config
from workers.python.rabbit_messages import encode, validate
from workers.python.rabbit_worker import connection_parameters, declare
from workers.python.ia_service import IAService


@unittest.skipUnless(os.environ.get('PC3_RABBIT_INTEGRATION')=='1', 'real RabbitMQ test opt-in not enabled')
class RabbitIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pika
        cls.pika=pika
        root=Path(__file__).resolve().parents[1]
        cls.folder=root/'build'/('rabbit-integration-'+uuid.uuid4().hex)
        cls.folder.mkdir(parents=True)
        cls.cfg=replace(Config.from_env(), request_queue='ia-test-'+uuid.uuid4().hex,
                        result_queue='ia-results-'+uuid.uuid4().hex,
                        error_queue='ia-errors-'+uuid.uuid4().hex,retry_queue='ia-retry-'+uuid.uuid4().hex,
                        retry_ms=100, timeout=2, concurrency=3,
                        metrics_file=str(cls.folder/'events.jsonl'),worker_id='ia-test-'+uuid.uuid4().hex,
                        publish_control=True,control_queue='ia-control-'+uuid.uuid4().hex,
                        log_queue='ia-logs-'+uuid.uuid4().hex)
        cls.connection=pika.BlockingConnection(connection_parameters(replace(cls.cfg,worker_id='producer-fixture'),pika));cls.channel=cls.connection.channel()
        declare(cls.channel,cls.cfg)
        cls.environment={**os.environ,'IA_REQUEST_QUEUE':cls.cfg.request_queue,
            'IA_RESULT_QUEUE':cls.cfg.result_queue,'IA_ERROR_QUEUE':cls.cfg.error_queue,
            'IA_RETRY_QUEUE':cls.cfg.retry_queue,'IA_RETRY_MS':'100',
            'IA_PROCESSING_TIMEOUT_SECONDS':'2','IA_WORKER_CONCURRENCY':'3',
            'IA_WORKER_ID':cls.cfg.worker_id,
            'IA_PUBLISH_CONTROL':'1','IA_CONTROL_QUEUE':cls.cfg.control_queue,'IA_LOG_QUEUE':cls.cfg.log_queue,
            'IA_METRICS_FILE':cls.cfg.metrics_file}
        cls.log=(cls.folder/'worker.log').open('w')
        cls.process=subprocess.Popen([sys.executable,'workers/python/rabbit_worker.py'],cwd=root,
                                     env=cls.environment,stdout=cls.log,stderr=subprocess.STDOUT)
        cls.addClassCleanup(cls.cleanup)
        end=time.monotonic()+15
        while time.monotonic()<end:
            status=cls.channel.queue_declare(queue=cls.cfg.request_queue,passive=True).method
            if status.consumer_count==3:break
            if cls.process.poll() is not None:raise RuntimeError('worker exited; see test log')
            time.sleep(.05)
        else:raise RuntimeError('consumers not ready')

    @classmethod
    def cleanup(cls):
        cls.process.terminate()
        try:cls.process.wait(timeout=15)
        except subprocess.TimeoutExpired:cls.process.kill();cls.process.wait(timeout=5)
        cls.log.close()
        if cls.connection.is_open:
            for queue in (cls.cfg.request_queue,cls.cfg.result_queue,cls.cfg.retry_queue,cls.cfg.error_queue,
                          cls.cfg.control_queue,cls.cfg.log_queue):
                cls.channel.queue_delete(queue=queue)
            cls.connection.close()

    def send(self, data, headers=None, correlation=None):
        self.channel.basic_publish(exchange='',routing_key=self.cfg.request_queue,
            body=encode(data) if isinstance(data,dict) else data,mandatory=True,
            properties=self.pika.BasicProperties(content_type='application/json',delivery_mode=2,
                       correlation_id=correlation,headers=headers or {}))

    def collect(self,count,queue=None,timeout=15):
        values=[];end=time.monotonic()+timeout
        while len(values)<count and time.monotonic()<end:
            method,props,body=self.channel.basic_get(queue or self.cfg.result_queue,auto_ack=False)
            if method:
                values.append((json.loads(body),props));self.channel.basic_ack(method.delivery_tag)
            else:time.sleep(.01)
        self.assertEqual(len(values),count)
        return values

    def test_a_real_profiles_correlated_equivalent_and_persistent(self):
        service=IAService(self.cfg)
        for backend in (False,True):
            request=message('real-'+str(backend),backend)
            self.send(request,correlation=request['idSolicitud'])
            result,props=self.collect(1)[0]
            expected,_=service.process(validate(request,self.cfg))
            self.assertEqual(result['payload']['probabilidades'],expected['payload']['probabilidades'])
            self.assertEqual(result['idSolicitud'],request['idSolicitud'])
            self.assertEqual(result['estado'],'COMPLETADA')
            self.assertEqual(props.correlation_id,request['idSolicitud'])
            self.assertEqual(props.delivery_mode,2)

    def test_b_duplicates_conflicts_and_invalid_dlq(self):
        request=message('same-id')
        self.send(request);self.send(request)
        results=self.collect(2)
        self.assertEqual(results[0][0],results[1][0])
        changed=message('same-id');changed['idCliente']='another-client';self.send(changed)
        result,_=self.collect(1)[0]
        self.assertEqual(result['error'],'idempotency_conflict')
        self.collect(1,self.cfg.error_queue)
        self.send(b'{')
        result,_=self.collect(1,self.cfg.error_queue)[0]
        self.assertEqual(result['error'],'invalid_json')
        self.assertNotIn('imagenBase64',str(result))

    def test_c_retry_exhaustion_real_ttl_queue(self):
        request=message('retry-exhausted',backend=True);request['payload']['modo']='DISTRIBUTED'
        self.send(request)
        result,_=self.collect(1)[0]
        self.assertEqual(result['estado'],'ERROR')
        self.assertIn('retries_exhausted:coordinator_not_configured',result['error'])
        self.collect(1,self.cfg.error_queue)
        events=[json.loads(line) for line in Path(self.cfg.metrics_file).read_text().splitlines()]
        retries=[event for event in events if event.get('idSolicitud')=='retry-exhausted' and event['estado']=='REINTENTO']
        self.assertEqual(len(retries),2)

    def test_d_multiple_requests_and_consumer_count(self):
        count=50
        for i in range(count):self.send(message('concurrent-'+str(i),backend=i%2==0))
        results=self.collect(count)
        self.assertEqual({r['idSolicitud'] for r,_ in results},{'concurrent-'+str(i) for i in range(count)})
        self.assertTrue(all(r['estado']=='COMPLETADA' for r,_ in results))
        status=self.channel.queue_declare(self.cfg.request_queue,passive=True).method
        self.assertEqual(status.consumer_count,3)

    def test_d_control_and_logs_real_queues(self):
        event,_=self.collect(1,self.cfg.control_queue)[0]
        self.assertEqual(event['tipo'],'IA_HEARTBEAT')
        self.assertEqual(event['worker'],self.cfg.worker_id)
        event,_=self.collect(1,self.cfg.log_queue)[0]
        self.assertEqual(event['tipo'],'IA_CONECTADA')

    def test_e_process_restart_durable_input(self):
        # Process restart is distinct from a broker-side connection interruption.
        self.process.terminate();self.process.wait(timeout=15)
        self.send(message('restart-delivery'))
        self.__class__.process=subprocess.Popen([sys.executable,'workers/python/rabbit_worker.py'],
            cwd=Path(__file__).resolve().parents[1],env=self.environment,
            stdout=self.log,stderr=subprocess.STDOUT)
        result,_=self.collect(1,timeout=20)[0]
        self.assertEqual(result['idSolicitud'],'restart-delivery')
        self.assertEqual(result['estado'],'COMPLETADA')

    def control(self, *arguments):
        if os.environ.get('PC3_RABBIT_ALLOW_CONTROL') != '1':
            self.skipTest('broker control not explicitly enabled for an isolated node')
        command = [os.environ['PC3_RABBIT_CTL'], '--node', os.environ['PC3_RABBIT_NODE'], *arguments]
        result = subprocess.run(command, capture_output=True, text=True, timeout=40)
        self.assertEqual(result.returncode, 0, 'isolated broker control failed')

    def reopen_producer(self):
        cls = self.__class__
        cls.connection = self.pika.BlockingConnection(connection_parameters(
            replace(self.cfg, worker_id='producer-fixture'), self.pika))
        cls.channel = cls.connection.channel()
        declare(cls.channel, self.cfg)

    def test_f_real_connection_interruption_and_reconnect(self):
        if os.environ.get('PC3_RABBIT_ALLOW_CONTROL') != '1':
            self.skipTest('isolated broker control not enabled')
        self.connection.close()
        self.control('close_all_user_connections', self.cfg.user, 'phase3-isolated-test')
        self.reopen_producer()
        self.send(message('after-disconnect'))
        result, _ = self.collect(1, timeout=20)[0]
        self.assertEqual(result['idSolicitud'], 'after-disconnect')
        self.assertEqual(result['estado'], 'COMPLETADA')

    def test_g_real_broker_application_restart(self):
        if os.environ.get('PC3_RABBIT_ALLOW_CONTROL') != '1':
            self.skipTest('isolated broker control not enabled')
        self.connection.close()
        try:
            self.control('stop_app')
        finally:
            self.control('start_app')
        self.reopen_producer()
        self.send(message('after-broker-restart'))
        result, _ = self.collect(1, timeout=30)[0]
        self.assertEqual(result['idSolicitud'], 'after-broker-restart')
        self.assertEqual(result['estado'], 'COMPLETADA')


if __name__=='__main__':unittest.main(verbosity=2)
