"""Transporte AMQP de entrenamiento, topologia privada v1 sin tocar inferencia."""
from dataclasses import replace
import os
import time
import uuid
from .gradient_protocol import decode,encode,FIELDS,aggregate_gradients
from workers.python.rabbit_config import Config
from workers.python.rabbit_worker import connection_parameters,declare


def training_config():
    base=Config.from_env()
    return replace(base,request_queue=os.environ.get('IA_TRAIN_QUEUE','ia_train_tasks_v1'),
        result_queue=os.environ.get('IA_TRAIN_RESULT_QUEUE','ia_train_results_v1'),
        retry_queue=os.environ.get('IA_TRAIN_RETRY_QUEUE','ia_train_retry_v1'),
        error_queue=os.environ.get('IA_TRAIN_ERROR_QUEUE','ia_train_errors_v1'),publish_control=False)


class AMQPBackend:
    def __init__(self,partitions=2,timeout=30,max_attempts=3,config=None):
        if type(partitions) is not int or not 1<=partitions<=16 or not 0<timeout<=120:
            raise ValueError('training_amqp_limits')
        if type(max_attempts) is not int or not 1<=max_attempts<=5:raise ValueError('training_attempts')
        import pika
        self.pika=pika;self.config=config or training_config()
        self.partitions=partitions;self.timeout=timeout;self.max_attempts=max_attempts
        self.stats={'retries':0,'failedTasks':0,'duplicateResults':0,'discardedResults':0,
                    'publishSeconds':0.0,'receiveSeconds':0.0}
        self.connection=None;self.channel=None;self.reply_queue=''
        self._connect()

    def _connect(self):
        self.connection=self.pika.BlockingConnection(connection_parameters(self.config,self.pika))
        try:
            self.channel=self.connection.channel();declare(self.channel,self.config)
            self.reply_queue='ia-train-results-'+uuid.uuid4().hex
            self.channel.queue_declare(queue=self.reply_queue,exclusive=True,auto_delete=True)
        except Exception:
            if self.connection.is_open:self.connection.close()
            raise

    def map(self,tasks):
        expected={task['taskId']:task for task in tasks};received={};missing=set(expected)
        overall_deadline=time.time()+self.timeout*self.max_attempts
        try:
            for attempt in range(1,self.max_attempts+1):
                if attempt>1:self.stats['retries']+=len(missing)
                start=time.monotonic()
                for identifier in sorted(missing):
                    task={**expected[identifier],'deadline':overall_deadline}
                    self.channel.basic_publish(exchange='',routing_key=self.config.request_queue,body=encode(task),mandatory=True,
                        properties=self.pika.BasicProperties(content_type='application/json',delivery_mode=2,
                            message_id=identifier,correlation_id=identifier,reply_to=self.reply_queue,
                            expiration=str(int(self.timeout*self.max_attempts*1000))))
                self.stats['publishSeconds']+=time.monotonic()-start
                start=time.monotonic();end=start+self.timeout
                while missing and time.monotonic()<end:
                    method,properties,body=self.channel.basic_get(self.reply_queue,auto_ack=False)
                    if method is None:
                        self.connection.process_data_events(time_limit=.01);continue
                    try:
                        result=decode(body);identifier=result.get('taskId')
                        if identifier not in expected:
                            self.stats['discardedResults']+=1;continue
                        if properties.correlation_id!=identifier:raise ValueError('training_correlation')
                        if result.get('tipo')=='TRAIN_ERROR':raise ValueError('gradient_worker_error:'+result.get('code','unknown'))
                        # Validate against a one-partition assignment before accepting into barrier.
                        aggregate_gradients([expected[identifier]],[result])
                        if identifier in received:
                            aggregate_gradients([expected[identifier]],[received[identifier],result])
                            self.stats['duplicateResults']+=1
                        else:
                            received[identifier]=result;missing.remove(identifier)
                    finally:self.channel.basic_ack(method.delivery_tag)
                self.stats['receiveSeconds']+=time.monotonic()-start
                if not missing:return [received[task['taskId']] for task in tasks]
            raise TimeoutError('training_minibatch_incomplete')
        except TimeoutError:
            self.stats['failedTasks']+=len(missing)
            raise
        except (self.pika.exceptions.AMQPError,OSError) as error:
            # Abort this global step, never apply a subset. Restart coordinator from checkpoint.
            self.stats['failedTasks']+=len(missing)
            raise RuntimeError('training_transport_lost_resume_checkpoint') from None
        except Exception:
            self.stats['failedTasks']+=len(missing);raise

    def close(self):
        if self.connection is not None and self.connection.is_open:
            self.connection.close()
