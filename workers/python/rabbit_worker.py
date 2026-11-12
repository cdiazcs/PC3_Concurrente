"""Nodo IA AMQP. Una conexion/canal Pika por hilo; prefetch y consumidores acotados."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collections import Counter
import hashlib
import json
import logging
import signal
import threading
import time

from workers.python.rabbit_config import Config
from workers.python.rabbit_messages import (MessageError, TemporaryError, encode, error_response,
                                            parse, utc_now, valid_id, validate)
from workers.python.ia_service import IAService

LOG = logging.getLogger('pc3.ia.amqp')


def connection_parameters(config, pika):
    return pika.ConnectionParameters(host=config.host, port=config.port, virtual_host=config.vhost,
        credentials=pika.PlainCredentials(config.user, config.password), heartbeat=config.heartbeat,
        blocked_connection_timeout=config.timeout, socket_timeout=config.timeout,
        stack_timeout=config.timeout+5, connection_attempts=1,
        client_properties={'connection_name': config.worker_id})


def declare(channel, config):
    # Main queue has no extra arguments: compatible with backend queueDeclare(..., null).
    for queue in (config.request_queue, config.result_queue, config.error_queue):
        channel.queue_declare(queue=queue, durable=True)
    if config.publish_control:
        for queue in (config.control_queue, config.log_queue):
            channel.queue_declare(queue=queue, durable=True)
    channel.queue_declare(queue=config.retry_queue, durable=True, arguments={
        'x-queue-type': 'quorum', 'x-dead-letter-strategy': 'at-least-once',
        'x-overflow': 'reject-publish', 'x-max-length-bytes': 16_000_000,
        'x-message-ttl': config.retry_ms, 'x-dead-letter-exchange': '',
        'x-dead-letter-routing-key': config.request_queue})
    channel.basic_qos(prefetch_count=config.prefetch)
    channel.confirm_delivery()


class Worker:
    def __init__(self, config, service=None):
        self.config = config
        self.service = service if service is not None else IAService(config)
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.metrics = Counter()
        self.threads = []

    def emit(self, event):
        with self.lock:
            self.metrics[event['estado']] += 1
            if self.config.metrics_file:
                path = Path(self.config.metrics_file)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('a', encoding='utf-8') as output:
                    output.write(json.dumps(event, allow_nan=False)+'\n')
        LOG.info('%s', json.dumps(event, allow_nan=False))

    def publish(self, channel, queue, message, pika, correlation=None, headers=None):
        channel.basic_publish(exchange='', routing_key=queue, body=encode(message), mandatory=True,
            properties=pika.BasicProperties(content_type='application/json', content_encoding='utf-8',
                delivery_mode=2, correlation_id=correlation, message_id=correlation,
                headers=headers or {}))

    def handle(self, channel, method, properties, body, pika):
        started, received = time.monotonic(), utc_now()
        value, request, duplicate, attempt = {}, None, False, 1
        code, state, inference = None, 'ERROR', None
        try:
            value = parse(body, self.config)
            request = validate(value, self.config, properties.correlation_id)
            header_attempt = (properties.headers or {}).get('x-ia-attempt', value.get('intento', 1))
            if type(header_attempt) is not int or not 1 <= header_attempt <= self.config.max_attempts:
                raise MessageError('invalid_attempt_header')
            attempt = header_attempt
            result, duplicate = self.service.process(request)
            inference = 0.0 if duplicate else result['payload']['duracionMs']
            self.publish(channel, self.config.result_queue, result, pika, request.request_id)
            state = 'DUPLICADO' if duplicate else 'COMPLETADA'
        except TemporaryError as error:
            code = str(error)
            if attempt < self.config.max_attempts:
                self.publish(channel, self.config.retry_queue, value, pika,
                             request.request_id if request else None, {'x-ia-attempt': attempt+1})
                state = 'REINTENTO'
            else:
                self._permanent(channel, value, body, 'retries_exhausted:'+code, pika)
        except MessageError as error:
            code = error.code
            self._permanent(channel, value, body, code, pika)
        except (pika.exceptions.AMQPError, OSError):
            # Confirm/routing/publication failure: no ack; close session and let broker requeue.
            raise
        except Exception:
            # Unexpected internal failures are retried with bounded delay, no exception payload leakage.
            code = 'internal_inference_error'
            if attempt < self.config.max_attempts:
                self.publish(channel, self.config.retry_queue, value, pika,
                             request.request_id if request else None, {'x-ia-attempt': attempt+1})
                state = 'REINTENTO'
            else:
                self._permanent(channel, value, body, code, pika)
        channel.basic_ack(delivery_tag=method.delivery_tag)
        self.emit({'idSolicitud': request.request_id if request else
                   value.get('idSolicitud') if valid_id(value.get('idSolicitud')) else None,
                   'worker': self.config.worker_id, 'modelo': self.config.model,
                   'recibida': received, 'finalizada': utc_now(), 'estado': state,
                   'intento': attempt, 'error': code, 'inferenciaMs': inference,
                   'totalNodoMs': (time.monotonic()-started)*1000})

    def _permanent(self, channel, value, body, code, pika):
        result = error_response(value, code)
        if result['idSolicitud'] is not None:
            self.publish(channel, self.config.result_queue, result, pika, result['idSolicitud'])
        # Sanitized error record, not the raw image/body.
        self.publish(channel, self.config.error_queue, {**result,
                     'mensajeSha256': hashlib.sha256(body).hexdigest()}, pika, result['idSolicitud'])

    def consume(self, number):
        import pika
        backoff = 1.0
        while not self.stop.is_set():
            connection = None
            try:
                connection = pika.BlockingConnection(connection_parameters(self.config, pika))
                channel = connection.channel()
                declare(channel, self.config)
                backoff = 1.0
                next_heartbeat = 0.0
                if self.config.publish_control and number == 0:
                    self.publish(channel, self.config.log_queue, {
                        'schemaVersion': 1, 'tipo': 'IA_CONECTADA', 'worker': self.config.worker_id,
                        'modeloDestino': self.config.model, 'timestamp': utc_now()}, pika)
                for method, properties, body in channel.consume(self.config.request_queue,
                        auto_ack=False, inactivity_timeout=.2):
                    if self.stop.is_set():
                        break
                    if self.config.publish_control and number == 0 and time.monotonic() >= next_heartbeat:
                        with self.lock:
                            counts = dict(self.metrics)
                        self.publish(channel, self.config.control_queue, {
                            'schemaVersion': 1, 'tipo': 'IA_HEARTBEAT', 'worker': self.config.worker_id,
                            'modeloDestino': self.config.model, 'timestamp': utc_now(),
                            'payload': {'consumidoresConfigurados': self.config.concurrency,
                                        'contadoresProceso': counts}}, pika)
                        next_heartbeat = time.monotonic()+15
                    if method is not None:
                        self.handle(channel, method, properties, body, pika)
            except (pika.exceptions.AMQPError, OSError):
                # Do not log exception strings: URLs/credentials can be embedded by clients.
                self.emit({'estado': 'CONEXION_ERROR', 'worker': self.config.worker_id,
                           'modelo': self.config.model, 'consumidor': number, 'timestamp': utc_now()})
            finally:
                if connection is not None and connection.is_open:
                    try:
                        connection.close()
                    except pika.exceptions.AMQPError:
                        pass
            if not self.stop.is_set():
                self.stop.wait(backoff)
                backoff = min(30.0, backoff*2)

    def run(self):
        self.threads = [threading.Thread(target=self.consume, args=(i,), name=f'amqp-{i}')
                        for i in range(self.config.concurrency)]
        for thread in self.threads:
            thread.start()
        try:
            while not self.stop.wait(.2):
                if not all(thread.is_alive() for thread in self.threads):
                    raise RuntimeError('consumer_thread_stopped')
        finally:
            self.stop.set()
            for thread in self.threads:
                thread.join()


def main():
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    # Third-party transport logging is deliberately terse; our events never log images/secrets.
    logging.getLogger('pika').setLevel(logging.CRITICAL)
    config = Config.from_env()
    worker = Worker(config)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: worker.stop.set())
    worker.run()


if __name__ == '__main__':
    main()
