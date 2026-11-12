"""DB RPC transport reusing the IA worker's per-thread AMQP sessions and confirms."""
from dataclasses import replace
import os
from workers.python.rabbit_config import Config
from workers.python.rabbit_messages import MessageError, parse, valid_id, utc_now
from workers.python.rabbit_worker import Worker


def database_config(request, result):
    cfg = Config.from_env()
    return replace(cfg, request_queue=request, result_queue=result,
                   retry_queue=request+'.retry', error_queue=request+'.errores',
                   concurrency=1, publish_control=False)


def validate_envelope(value, correlation, kind):
    from datetime import datetime
    try:
        timestamp = datetime.fromisoformat(value['timestamp'].replace('Z','+00:00'))
        if timestamp.utcoffset() is None: raise ValueError()
    except (KeyError, ValueError, TypeError, AttributeError):
        raise MessageError('invalid_timestamp') from None
    if (type(value.get('schemaVersion')) is not int or value['schemaVersion'] != 1
            or value.get('tipo') != kind or value.get('modeloDestino') != 'A'
            or not valid_id(value.get('idSolicitud')) or not valid_id(value.get('idCliente'))
            or correlation != value['idSolicitud'] or not isinstance(value.get('payload'), dict)):
        raise MessageError('invalid_database_message')


class DatabaseWorker(Worker):
    def __init__(self, config, operation, request_type, result_type):
        super().__init__(config, service=operation)
        self.request_type, self.result_type = request_type, result_type

    def handle(self, channel, method, properties, body, pika):
        value = {}
        try:
            value = parse(body, self.config)
            validate_envelope(value, properties.correlation_id, self.request_type)
            payload = self.service(value)
            result = {**{key: value[key] for key in ('schemaVersion','idSolicitud','idCliente','modeloDestino')},
                      'tipo': self.result_type, 'timestamp': utc_now(), 'estado': 'VALIDADA',
                      'payload': payload}
            self.publish(channel, self.config.result_queue, result, pika, value['idSolicitud'])
            self.emit({'idSolicitud':value['idSolicitud'],'estado':'VALIDADA','aprobado':payload.get('aprobado')})
        except MessageError as error:
            self.fail(channel, value, error.code, pika)
        except (pika.exceptions.AMQPError, OSError):
            raise  # Publication failure: no ACK; reconnect causes broker redelivery.
        except Exception:
            attempt = (properties.headers or {}).get('x-db-attempt', 1)
            if type(attempt) is not int or not 1 <= attempt <= self.config.max_attempts:
                self.fail(channel, value, 'invalid_attempt', pika)
            elif attempt < self.config.max_attempts:
                self.publish(channel, self.config.retry_queue, value, pika,
                             value.get('idSolicitud'), {'x-db-attempt': attempt+1})
            else:
                self.fail(channel, value, 'database_unavailable', pika)
        channel.basic_ack(delivery_tag=method.delivery_tag)

    def fail(self, channel, value, code, pika):
        result = {'schemaVersion':1,'tipo':self.result_type,'timestamp':utc_now(),
                  'idSolicitud':value.get('idSolicitud') if valid_id(value.get('idSolicitud')) else None,
                  'idCliente':value.get('idCliente') if valid_id(value.get('idCliente')) else None,
                  'modeloDestino':'A','estado':'ERROR','error':code,'payload':{}}
        if valid_id(result['idSolicitud']):
            self.publish(channel,self.config.result_queue,result,pika,result['idSolicitud'])
        self.publish(channel,self.config.error_queue,result,pika,
                     result['idSolicitud'] if valid_id(result['idSolicitud']) else None)
