"""Unit transport/contracts only; these mocks are not evidence of SQL or RabbitMQ."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from messaging.database_worker import DatabaseWorker
from workers.python.rabbit_messages import encode
from test_rabbit_messages import config
from test_rabbit_worker import PIKA,TransportError

class DatabaseTransportTests(unittest.TestCase):
    def setUp(self):
        self.operation=mock.Mock(return_value={'aprobado':False,'motivo':'CLIENTE_NO_REGISTRADO'})
        self.worker=DatabaseWorker(config(),self.operation,'VALIDAR_CLIENTE','RESULTADO_VALIDACION')
        self.channel=mock.Mock();self.method=SimpleNamespace(delivery_tag=1)
        self.props=SimpleNamespace(correlation_id='db-1',headers={})
        self.request={'schemaVersion':1,'tipo':'VALIDAR_CLIENTE','idSolicitud':'db-1','idCliente':'unknown',
                      'modeloDestino':'A','timestamp':'2026-11-12T00:00:00Z','payload':{}}
    def deliver(self):self.worker.handle(self.channel,self.method,self.props,encode(self.request),PIKA)
    def test_ack_only_after_confirmed_publication(self):
        self.deliver();self.assertEqual([call[0] for call in self.channel.method_calls],['basic_publish','basic_ack'])
        self.assertEqual(self.channel.basic_publish.call_args.kwargs['properties'].correlation_id,'db-1')
    def test_publish_failure_does_not_ack_after_sql(self):
        self.channel.basic_publish.side_effect=TransportError()
        with self.assertRaises(TransportError):self.deliver()
        self.operation.assert_called_once();self.channel.basic_ack.assert_not_called()
    def test_invalid_schema_and_correlation_do_not_reach_sql(self):
        for schema,correlation in ((2,'db-1'),(1,'other-id')):
            self.request['schemaVersion']=schema;self.props.correlation_id=correlation
            self.deliver();self.operation.assert_not_called()
    def test_bounded_database_retries(self):
        self.operation.side_effect=RuntimeError('temporary SQL outage')
        self.deliver()
        self.assertEqual(self.channel.basic_publish.call_args.kwargs['routing_key'],self.worker.config.retry_queue)
        self.props.headers={'x-db-attempt':3};self.channel.reset_mock();self.deliver()
        self.assertTrue(all(call.kwargs['routing_key']!=self.worker.config.retry_queue for call in self.channel.basic_publish.call_args_list))
        self.channel.basic_ack.assert_called_once()

class WebContractTests(unittest.TestCase):
    def test_response_ids_and_probabilities(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('phase2_web_contract',ROOT/'web-server/http_gateway.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(module.parse_tcp_identify_reply('RESULT|web1|1|3|0.8,0.1,0.1','web1')['etiqueta'],'circulo')
        for text in ('RESULT|other|1|3|0.8,0.1,0.1','RESULT|web1|1|3|NaN,0,1',
                     'RESULT|web1|1|3|0.1,0.1,0.1','ERROR|other|client_rejected'):
            with self.subTest(text=text),self.assertRaises(RuntimeError):module.parse_tcp_identify_reply(text,'web1')

@unittest.skipUnless(shutil.which('javac') and shutil.which('java'),'NO VERIFICADO: requiere JDK 21')
class JvmContractsTests(unittest.TestCase):
    def test_android_and_database_contracts(self):
        from build import compile_java,classpath
        with tempfile.TemporaryDirectory() as folder:
            compile_java(folder)
            android=ROOT/'clients/android/protocol/src'
            subprocess.run(['javac','--release','17','-cp',classpath(folder),'-d',folder,
                str(android/'main/java/uni/openaicubes/Protocol.java'),str(android/'test/java/uni/openaicubes/ProtocolChecks.java'),
                str(ROOT/'tests/DatabaseContractChecks.java')],check=True)
            for main in ('uni.openaicubes.ProtocolChecks','DatabaseContractChecks'):
                subprocess.run(['java','-cp',classpath(folder),main],check=True)
