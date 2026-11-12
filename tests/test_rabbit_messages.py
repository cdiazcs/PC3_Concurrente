"""Unit tests (no broker, no Pika dependency required)."""
import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest import mock
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workers.python.rabbit_config import Config
from workers.python.rabbit_messages import MessageError, TemporaryError, encode, parse, response, validate
from workers.python.ia_service import IAService, ResultCache
from cnn_python.model import CNN
from cnn_python.images import read_image


def config(**kwargs):
    return Config(user='test-user', password='test-only', **kwargs)


def message(identifier='unit-1', backend=False):
    result = {'schemaVersion': 1, 'idSolicitud': identifier, 'idCliente': 'unit-client',
              'modeloDestino': 'A', 'timestamp': '2026-11-12T08:00:00Z', 'intento': 1,
              'tipo': 'INFERENCIA' if backend else 'CLASIFICAR_IMAGEN', 'payload': {}}
    if backend:
        result['imagenBase64'] = ','.join(map(str, read_image(ROOT/'model/examples/circulo-0.png')))
        result['payload']['modo'] = 'SEQUENTIAL'
    else:
        result['payload'] = {'mimeType': 'image/png', 'imagenBase64': base64.b64encode(
            (ROOT/'model/examples/circulo-0.png').read_bytes()).decode()}
    return result


class MessageTests(unittest.TestCase):
    def test_cache_failure_is_retryable_and_capacity_is_bounded(self):
        cache=ResultCache(1,60)
        with self.assertRaises(TemporaryError):
            cache.execute('id','hash',lambda:(_ for _ in ()).throw(TemporaryError('temporary')),1)
        self.assertEqual(cache.execute('id','hash',lambda:b'ok',1),(b'ok',False))
        self.assertEqual(cache.execute('new','newhash',lambda:b'new',1),(b'new',False))
        self.assertEqual(len(cache.entries),1)

    def test_valid_profiles_same_pixels_result_shapes_and_correlation(self):
        cfg = config()
        requests = [validate(message(backend=b), cfg, 'unit-1') for b in (False, True)]
        self.assertEqual(requests[0].pixels, requests[1].pixels)
        service = IAService(cfg)
        expected = CNN.load().predict(requests[0].pixels)
        for i, req in enumerate(requests):
            result = response(req, expected.probabilities, 1, service.weights_hash)
            self.assertEqual(result['idSolicitud'], req.request_id)
            self.assertEqual(result['estado'], 'COMPLETADA')
            self.assertEqual(result['payload']['etiqueta'], 'circulo')
            self.assertIsInstance(result['payload']['probabilidades'], list if i else dict)
            self.assertLess(abs(sum(expected.probabilities)-1), 1e-12)

    def test_invalid_requests(self):
        cfg = config()
        cases = [('idSolicitud', None), ('idCliente', 'bad id'), ('schemaVersion', True),
                 ('modeloDestino', 'B'), ('tipo', 'other'), ('timestamp', 'yesterday'),
                 ('intento', -1), ('payload', None)]
        for key, value in cases:
            data = message();data[key] = value
            with self.subTest(field=key), self.assertRaises(MessageError):
                validate(data, cfg)
        with self.assertRaisesRegex(MessageError, 'correlation'):
            validate(message(), cfg, 'wrong')
        for payload in ({'mimeType':'image/png', 'imagenBase64':'@@@'},
                        {'mimeType':'image/png', 'imagenBase64':base64.b64encode(b'bad').decode()},
                        {'mimeType':'image/jpeg', 'imagenBase64':'YQ=='}):
            data = message();data['payload'] = payload
            with self.assertRaises(MessageError):validate(data,cfg)
        data = message(backend=True);data['imagenBase64'] = ','.join(['NaN']*256)
        with self.assertRaises(MessageError):validate(data,cfg)

    def test_parser_and_sizes(self):
        cfg = config()
        for data in (b'{', b'[]', b'{"id":1,"id":2}', b'{"id":NaN}', b'\xff', b'x'*(cfg.max_message+1)):
            with self.subTest(data=data[:20]), self.assertRaises(MessageError):parse(data,cfg)
        with self.assertRaisesRegex(MessageError, 'image_size'):
            validate(message(), replace(cfg,max_image=64))

    def test_config_limits_and_secret_repr(self):
        cfg = config()
        self.assertNotIn('test-only',repr(cfg))
        for kwargs in ({'concurrency':0},{'prefetch':100},{'max_attempts':0},
                       {'result_queue':cfg.request_queue},{'model':'B'},{'timeout':60}):
            with self.assertRaises(ValueError):config(**kwargs)
        with self.assertRaises(ValueError):Config()

    def test_duplicate_coalescing_conflicts_and_ttl(self):
        cache = ResultCache(2, .02)
        count = 0
        lock = threading.Lock()
        def calculate():
            nonlocal count
            with lock:count += 1
            time.sleep(.02)
            return b'result'
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _:cache.execute('id','hash',calculate,1),range(8)))
        self.assertEqual(count,1)
        self.assertEqual(sum(not duplicate for _,duplicate in results),1)
        with self.assertRaisesRegex(MessageError,'conflict'):
            cache.execute('id','other',calculate,1)
        time.sleep(.03)
        cache.execute('id','hash',calculate,1)
        self.assertEqual(count,2)

    def test_local_concurrency_immutable_weights_and_same_prediction(self):
        cfg=config();service=IAService(cfg)
        original=dict(service.model.weights)
        def call(i):
            req=validate(message('req-'+str(i)),cfg)
            return service.process(req)[0]
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(call,range(24)))
        self.assertEqual(len({r['idSolicitud'] for r in results}),24)
        self.assertTrue(all(r['payload']['etiqueta']=='circulo' for r in results))
        self.assertEqual(dict(service.model.weights),original)


if __name__=='__main__':unittest.main(verbosity=2)
