"""REAL AMQP -> existing Java coordinator -> Java/Python/C# chunks (localhost)."""
from dataclasses import replace
import os
import shutil
import sys
import time
import unittest
import uuid
import test_protocol as protocol
from test_rabbit_messages import message
from workers.python.rabbit_config import Config
from workers.python.rabbit_messages import encode, validate
from workers.python.rabbit_worker import connection_parameters, declare
from workers.python.ia_service import IAService
import json
import subprocess


@unittest.skipUnless(os.environ.get('PC3_RABBIT_INTEGRATION')=='1','real RabbitMQ opt-in not enabled')
class RabbitDistributedTests(protocol.ProtocolTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import pika
        cls.pika=pika
        token=uuid.uuid4().hex
        cls.cfg=replace(Config.from_env(),request_queue='ia-dist-'+token,result_queue='ia-dist-results-'+token,
            retry_queue='ia-dist-retry-'+token,error_queue='ia-dist-errors-'+token,
            coordinator_host='127.0.0.1',coordinator_port=cls.central)
        cls.connection=pika.BlockingConnection(connection_parameters(cls.cfg,pika))
        cls.channel=cls.connection.channel();declare(cls.channel,cls.cfg)
        cls.addClassCleanup(cls.cleanup_amqp)
        env={**os.environ,'IA_REQUEST_QUEUE':cls.cfg.request_queue,'IA_RESULT_QUEUE':cls.cfg.result_queue,
            'IA_RETRY_QUEUE':cls.cfg.retry_queue,'IA_ERROR_QUEUE':cls.cfg.error_queue,
            'IA_COORDINATOR_HOST':'127.0.0.1','IA_COORDINATOR_PORT':str(cls.central)}
        log=(cls.artifacts/'amqp-worker.log').open('w');cls.logs.append(log)
        cls.processes.append(subprocess.Popen([sys.executable,'workers/python/rabbit_worker.py'],
            cwd=protocol.ROOT,env=env,stdout=log,stderr=subprocess.STDOUT))

    @classmethod
    def cleanup_amqp(cls):
        # Stop our AMQP consumer before deleting its isolated queues.
        cls.processes[-1].terminate();cls.processes[-1].wait(timeout=15)
        if cls.connection.is_open:
            for q in (cls.cfg.request_queue,cls.cfg.result_queue,cls.cfg.retry_queue,cls.cfg.error_queue):
                cls.channel.queue_delete(q)
            cls.connection.close()

    def test_amqp_reuses_coordinator_and_all_languages(self):
        data=message('amqp-distributed',backend=True);data['payload']['modo']='DISTRIBUTED'
        self.channel.basic_publish(exchange='',routing_key=self.cfg.request_queue,body=encode(data),mandatory=True,
            properties=self.pika.BasicProperties(delivery_mode=2,correlation_id=data['idSolicitud']))
        end=time.monotonic()+20
        while time.monotonic()<end:
            method,props,body=self.channel.basic_get(self.cfg.result_queue,auto_ack=False)
            if method:
                result=json.loads(body);self.channel.basic_ack(method.delivery_tag);break
            time.sleep(.02)
        else:self.fail('AMQP distributed result timeout')
        self.assertEqual(result['estado'],'COMPLETADA')
        local=IAService(self.cfg).model.predict(validate(data,self.cfg).pixels)
        for a,b in zip(result['payload']['probabilidades'],local.probabilities):
            self.assertAlmostEqual(a,b,delta=1e-8)
        trace=(self.artifacts/'Central.log').read_text()
        for language in ('Java','Python','CSharp'):self.assertIn('|'+language+'|',trace)
        self.assertEqual(props.correlation_id,data['idSolicitud'])


def load_tests(loader,tests,pattern):
    return unittest.TestSuite([RabbitDistributedTests('test_amqp_reuses_coordinator_and_all_languages')])


if __name__=='__main__':unittest.main(verbosity=2)
