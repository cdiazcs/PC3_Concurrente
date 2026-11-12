"""Workers de gradientes Python; nunca aplican Adam. Broker AMQP de fase III."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

import hashlib
import json
import logging
import os
import signal
import threading
import time
from cnn_python.dataset import DEFAULT_DATASET,load_split
from cnn_python.gradient_protocol import FIELDS,decode,encode,execute_task,make_tasks,aggregate_gradients,error_result
from cnn_python.training_backends import ParallelBackend
from cnn_python.training_amqp import training_config
from workers.python.rabbit_worker import connection_parameters,declare

LOG=logging.getLogger('pc3.training')


class GradientComputer:
    def __init__(self,dataset=DEFAULT_DATASET,local_processes=1):
        path=Path(dataset);self.dataset_hash=hashlib.sha256(path.read_bytes()).hexdigest()
        self.examples=load_split(path,'train');self.pool=None
        if type(local_processes) is not int or not 1<=local_processes<=16:raise ValueError('training_local_processes')
        if local_processes>1:self.pool=ParallelBackend(self.examples,self.dataset_hash,local_processes)

    def compute(self,task):
        if self.pool is None:
            result=execute_task(task,self.examples,self.dataset_hash)
            result['workerId']=os.environ.get('IA_TRAIN_WORKER_ID','gradient')+':'+str(os.getpid())
            return result
        # Validate original assignment first, then distribute only its own indices locally.
        from cnn_python.gradient_protocol import validate_task
        validate_task(task,self.dataset_hash,len(self.examples))
        parts=make_tasks(task['runId'],task['epoch'],task['batchId'],task['modelVersion'],task['weights'],
                         task['indices'],self.dataset_hash,self.pool.partitions)
        start=time.monotonic();results=self.pool.map(parts);loss,gradients=aggregate_gradients(parts,results)
        return {**{key:task[key] for key in FIELDS},'schemaVersion':1,'tipo':'TRAIN_GRADIENT_RESULT',
            'count':task['count'],'meanLoss':loss,'gradients':gradients,
            'workerId':os.environ.get('IA_TRAIN_WORKER_ID','gradient')+':'+str(os.getpid()),
            'hostname':results[0]['hostname'],'os':results[0]['os'],'pid':os.getpid(),
            'computeSeconds':time.monotonic()-start,
            'computeCpuSeconds':sum(r['computeCpuSeconds'] for r in results),
            'localWorkers':[{k:r[k] for k in ('workerId','pid','hostname','os')} for r in results]}

    def close(self):
        if self.pool is not None:self.pool.close()


def serve(stop=None):
    import pika
    stop=stop or threading.Event();config=training_config()
    computer=GradientComputer(os.environ.get('IA_TRAIN_DATASET',str(DEFAULT_DATASET)),
                              int(os.environ.get('IA_TRAIN_LOCAL_PROCESSES','1')))
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:stop.set())
    backoff=1
    try:
        while not stop.is_set():
            connection=None
            try:
                connection=pika.BlockingConnection(connection_parameters(config,pika));channel=connection.channel()
                declare(channel,config);channel.basic_qos(prefetch_count=1);backoff=1
                for method,properties,body in channel.consume(config.request_queue,auto_ack=False,inactivity_timeout=.2):
                    if stop.is_set():break
                    if method is None:continue
                    task={};started=time.monotonic()
                    try:
                        task=decode(body)
                        if properties.correlation_id!=task.get('taskId'):raise ValueError('training_correlation')
                        if not isinstance(properties.reply_to,str) or not properties.reply_to.startswith('ia-train-results-'):
                            raise ValueError('training_reply_queue')
                        if (not isinstance(task.get('deadline'),(float,int)) or not time.time()<task['deadline']<=time.time()+600):
                            raise ValueError('training_task_expired_or_bad_deadline')
                        result=computer.compute(task)
                    except Exception as error:
                        code=str(error) if isinstance(error,ValueError) else 'gradient_computation_failed'
                        if len(code)>80 or not all(c.isascii() and (c.isalnum() or c=='_') for c in code):
                            code='gradient_task_invalid'
                        result=error_result(task,code,properties.correlation_id)
                    try:
                        if properties.reply_to and properties.reply_to.startswith('ia-train-results-'):
                            channel.basic_publish(exchange='',routing_key=properties.reply_to,body=encode(result),mandatory=True,
                                properties=pika.BasicProperties(delivery_mode=2,content_type='application/json',
                                    correlation_id=result.get('taskId')))
                        else:
                            channel.basic_publish(exchange='',routing_key=config.error_queue,body=encode(result),mandatory=True,
                                properties=pika.BasicProperties(delivery_mode=2))
                        channel.basic_ack(method.delivery_tag)
                    except pika.exceptions.AMQPError:
                        # A dead coordinator's reply queue cannot poison the shared input forever.
                        attempt=(properties.headers or {}).get('x-train-publish-attempt',1)
                        if type(attempt) is not int or not 1<=attempt<=config.max_attempts:attempt=config.max_attempts
                        target=config.retry_queue if attempt<config.max_attempts else config.error_queue
                        payload=task if target==config.retry_queue else error_result(task,'training_result_unroutable',properties.correlation_id)
                        channel.basic_publish(exchange='',routing_key=target,body=encode(payload),mandatory=True,
                            properties=pika.BasicProperties(delivery_mode=2,correlation_id=properties.correlation_id,
                                reply_to=properties.reply_to,headers={'x-train-publish-attempt':attempt+1}))
                        channel.basic_ack(method.delivery_tag)
                    LOG.info('%s',json.dumps({'taskId':result.get('taskId'),'runId':result.get('runId'),
                        'modelVersion':result.get('modelVersion'),'tipo':result['tipo'],
                        'workerPid':os.getpid(),'seconds':time.monotonic()-started}))
            except (pika.exceptions.AMQPError,OSError):
                LOG.warning('training_connection_error')
            finally:
                if connection is not None and connection.is_open:
                    try:connection.close()
                    except pika.exceptions.AMQPError:pass
            if not stop.is_set():stop.wait(backoff);backoff=min(30,backoff*2)
    finally:computer.close()


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    logging.getLogger('pika').setLevel(logging.CRITICAL)
    serve()
