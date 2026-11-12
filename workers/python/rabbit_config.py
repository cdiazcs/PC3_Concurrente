"""Configuracion externa del nodo IA; sin credenciales por defecto."""
from dataclasses import dataclass, field
import os
from pathlib import Path


@dataclass(frozen=True)
class Config:
    host: str = 'localhost'
    port: int = 5672
    user: str = field(default='', repr=False)
    password: str = field(default='', repr=False)
    vhost: str = '/'
    model: str = 'A'
    request_queue: str = 'cola_modeloA'
    result_queue: str = 'cola_resultadosA'
    error_queue: str = 'cola_modeloA.ia_errores'
    retry_queue: str = 'cola_modeloA.ia_retry'
    concurrency: int = 2
    prefetch: int = 1
    max_attempts: int = 3
    retry_ms: int = 1000
    timeout: float = 10.0
    heartbeat: int = 60
    max_message: int = 2_000_000
    max_image: int = 1_000_000
    max_pixels: int = 262144
    cache_size: int = 4096
    cache_ttl: float = 3600.0
    coordinator_host: str = ''
    coordinator_port: int = 0
    weights: str = ''
    worker_id: str = 'ia-A'
    metrics_file: str = ''
    publish_control: bool = False
    control_queue: str = 'cola_control_heartbeat'
    log_queue: str = 'cola_logs'

    def __post_init__(self):
        if not self.host or not self.user or not self.password:
            raise ValueError('rabbitmq_host_user_password_required')
        if self.model != 'A':
            raise ValueError('only_trained_model_A_available')
        limits = ((self.port, 1, 65535), (self.concurrency, 1, 16), (self.prefetch, 1, 4),
                  (self.max_attempts, 1, 10), (self.retry_ms, 100, 60000),
                  (self.heartbeat, 10, 600), (self.max_message, 1024, 2_000_000),
                  (self.max_image, 64, 1_000_000), (self.max_pixels, 256, 262144),
                  (self.cache_size, 1, 65536))
        if any(type(v) is not int or not low <= v <= high for v, low, high in limits):
            raise ValueError('invalid_configuration_limits')
        if not 0 < self.timeout < self.heartbeat/2 or not 1 <= self.cache_ttl <= 86400:
            raise ValueError('invalid_timeout_or_cache_ttl')
        if bool(self.coordinator_host) != bool(self.coordinator_port):
            raise ValueError('coordinator_host_and_port_required_together')
        if self.coordinator_port and not 1 <= self.coordinator_port <= 65535:
            raise ValueError('invalid_coordinator_port')
        queues = (self.request_queue, self.result_queue, self.error_queue, self.retry_queue)
        if self.publish_control:
            queues += (self.control_queue, self.log_queue)
        if len(set(queues)) != len(queues) or any(not q or len(q.encode()) > 200 for q in queues):
            raise ValueError('invalid_or_overlapping_queues')

    @classmethod
    def from_env(cls):
        mapping = {'host': 'RABBITMQ_HOST', 'port': 'RABBITMQ_PORT', 'user': 'RABBITMQ_USER',
                   'password': 'RABBITMQ_PASSWORD', 'vhost': 'RABBITMQ_VHOST',
                   'model': 'IA_MODEL_NAME', 'concurrency': 'IA_WORKER_CONCURRENCY',
                   'prefetch': 'IA_PREFETCH', 'max_attempts': 'IA_MAX_ATTEMPTS',
                   'retry_ms': 'IA_RETRY_MS', 'timeout': 'IA_PROCESSING_TIMEOUT_SECONDS',
                   'heartbeat': 'RABBITMQ_HEARTBEAT', 'request_queue': 'IA_REQUEST_QUEUE',
                   'result_queue': 'IA_RESULT_QUEUE', 'error_queue': 'IA_ERROR_QUEUE',
                   'retry_queue': 'IA_RETRY_QUEUE', 'coordinator_host': 'IA_COORDINATOR_HOST',
                   'coordinator_port': 'IA_COORDINATOR_PORT', 'weights': 'IA_WEIGHTS',
                   'worker_id': 'IA_WORKER_ID', 'metrics_file': 'IA_METRICS_FILE',
                   'cache_size': 'IA_CACHE_SIZE', 'cache_ttl': 'IA_CACHE_TTL_SECONDS',
                   'publish_control': 'IA_PUBLISH_CONTROL', 'control_queue': 'IA_CONTROL_QUEUE',
                   'log_queue': 'IA_LOG_QUEUE'}
        integers = {'port', 'concurrency', 'prefetch', 'max_attempts', 'retry_ms', 'heartbeat',
                    'coordinator_port', 'cache_size'}
        floats = {'timeout', 'cache_ttl'}
        if 'IA_PUBLISH_CONTROL' in os.environ and os.environ['IA_PUBLISH_CONTROL'] not in ('0','1'):
            raise ValueError('IA_PUBLISH_CONTROL_must_be_0_or_1')
        values = {k: (os.environ[v] == '1' if k == 'publish_control' else int(os.environ[v]) if k in integers else float(os.environ[v])
                      if k in floats else os.environ[v]) for k, v in mapping.items() if v in os.environ}
        return cls(**values)
