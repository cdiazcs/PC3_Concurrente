"""Unit tests: mocked AMQP channel, NOT broker integration evidence."""
from types import SimpleNamespace
from unittest import mock
import unittest
from test_rabbit_messages import config, message
from workers.python.rabbit_messages import TemporaryError, encode
from workers.python.rabbit_worker import Worker


class TransportError(Exception):pass
PIKA=SimpleNamespace(BasicProperties=lambda **kwargs:SimpleNamespace(**kwargs),
                     exceptions=SimpleNamespace(AMQPError=TransportError))


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.worker=Worker(config())
        self.channel=mock.Mock()
        self.props=SimpleNamespace(correlation_id=None,headers={})
        self.method=SimpleNamespace(delivery_tag=7)

    def deliver(self,data=None):
        self.worker.handle(self.channel,self.method,self.props,
                           encode(message() if data is None else data),PIKA)

    def test_publish_confirmed_channel_then_ack(self):
        self.deliver()
        methods=[c[0] for c in self.channel.method_calls]
        self.assertEqual(methods,['basic_publish','basic_ack'])
        args=self.channel.basic_publish.call_args.kwargs
        self.assertTrue(args['mandatory'])
        self.assertEqual(args['properties'].correlation_id,'unit-1')
        self.assertEqual(args['properties'].delivery_mode,2)

    def test_publish_failure_never_ack(self):
        self.channel.basic_publish.side_effect=TransportError()
        with self.assertRaises(TransportError):self.deliver()
        self.channel.basic_ack.assert_not_called()

    def test_error_queue_publish_failure_never_ack(self):
        self.channel.basic_publish.side_effect=[None,TransportError()]
        data=message();data['modeloDestino']='B'
        with self.assertRaises(TransportError):self.deliver(data)
        self.channel.basic_ack.assert_not_called()

    def test_permanent_error_result_and_error_queue_before_ack(self):
        data=message();data['modeloDestino']='B';self.deliver(data)
        routes=[c.kwargs['routing_key'] for c in self.channel.basic_publish.call_args_list]
        self.assertEqual(routes,[self.worker.config.result_queue,self.worker.config.error_queue])
        self.channel.basic_ack.assert_called_once()
        self.assertEqual(self.worker.metrics['ERROR'],1)

    def test_bad_json_no_result_without_id(self):
        self.worker.handle(self.channel,self.method,self.props,b'{',PIKA)
        self.assertEqual(self.channel.basic_publish.call_count,1)
        self.assertEqual(self.channel.basic_publish.call_args.kwargs['routing_key'],self.worker.config.error_queue)

    def test_retry_and_exhaustion(self):
        self.worker.service=mock.Mock()
        self.worker.service.process.side_effect=TemporaryError('temporary')
        self.deliver()
        args=self.channel.basic_publish.call_args.kwargs
        self.assertEqual(args['routing_key'],self.worker.config.retry_queue)
        self.assertEqual(args['properties'].headers['x-ia-attempt'],2)
        self.props.headers={'x-ia-attempt':3};self.channel.reset_mock();self.deliver()
        self.assertEqual(self.channel.basic_publish.call_count,2)
        self.assertTrue(all(c.kwargs['routing_key']!=self.worker.config.retry_queue
                            for c in self.channel.basic_publish.call_args_list))

    def test_duplicate_reuses_inference_but_republishes_correlated_result(self):
        original=self.worker.service.model.predict
        with mock.patch.object(self.worker.service.model,'predict',side_effect=original) as infer:
            self.deliver();self.deliver();self.assertEqual(infer.call_count,1)
        self.assertEqual(self.channel.basic_publish.call_count,2)
        self.assertEqual(self.worker.metrics['DUPLICADO'],1)


if __name__=='__main__':unittest.main(verbosity=2)
