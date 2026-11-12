"""Puente hacia la CNN validada o el coordinador TCP existente; sin AMQP."""
from collections import OrderedDict
from concurrent.futures import Future, TimeoutError as FutureTimeout
import hashlib
import math
from pathlib import Path
import socket
import struct
import threading
import time

from cnn_python.model import CNN, DEFAULT_WEIGHTS
from .rabbit_messages import MessageError, TemporaryError, response


class ResultCache:
    """LRU/TTL por proceso, coalesce duplicados en vuelo; no promete exactly-once."""
    def __init__(self, capacity, ttl):
        self.capacity, self.ttl = capacity, ttl
        self.lock, self.entries = threading.Lock(), OrderedDict()

    def execute(self, key, fingerprint, compute, timeout):
        now = time.monotonic()
        with self.lock:
            for existing in list(self.entries):
                _, future, timestamp = self.entries[existing]
                if future.done() and now-timestamp > self.ttl:
                    del self.entries[existing]
            if key in self.entries:
                previous, future, _ = self.entries[key]
                if previous != fingerprint:
                    raise MessageError('idempotency_conflict')
                self.entries.move_to_end(key)
                owner = False
            else:
                while len(self.entries) >= self.capacity:
                    evict = next((k for k, (_, f, _) in self.entries.items() if f.done()), None)
                    if evict is None:
                        raise TemporaryError('cache_capacity_busy')
                    del self.entries[evict]
                future = Future()
                self.entries[key] = fingerprint, future, now
                owner = True
        if owner:
            try:
                result = compute()
                with self.lock:
                    self.entries[key] = fingerprint, future, time.monotonic()
                    future.set_result(result)
                return result, False
            except Exception as error:
                with self.lock:
                    self.entries.pop(key, None)
                    future.set_exception(error)
                raise
        try:
            return future.result(timeout=timeout), True
        except FutureTimeout:
            raise TemporaryError('duplicate_wait_timeout') from None


class IAService:
    def __init__(self, config):
        self.config = config
        path = Path(config.weights) if config.weights else DEFAULT_WEIGHTS
        data = path.read_bytes()
        self.weights_hash = hashlib.sha256(data).hexdigest()
        self.model = CNN.load(path)
        if path.read_bytes() != data:
            raise ValueError('weights_changed_during_load')
        self.cache = ResultCache(config.cache_size, config.cache_ttl)

    def process(self, request):
        def compute():
            start = time.monotonic()
            if request.mode == 'DISTRIBUTED':
                probabilities = self._distributed(request)
            else:
                probabilities = self.model.predict(request.pixels).probabilities
            elapsed = (time.monotonic()-start)*1000
            if elapsed > self.config.timeout*1000:
                raise TemporaryError('processing_timeout')
            return response(request, probabilities, elapsed, self.weights_hash)
        return self.cache.execute((request.model, request.request_id), request.fingerprint,
                                  compute, self.config.timeout)

    def _distributed(self, request):
        if not self.config.coordinator_host:
            raise TemporaryError('coordinator_not_configured')
        end = time.monotonic()+self.config.timeout
        def exact(connection, count):
            result = bytearray()
            while len(result) < count:
                left = end-time.monotonic()
                if left <= 0:
                    raise TimeoutError()
                connection.settimeout(left)
                part = connection.recv(count-len(result))
                if not part:
                    raise ConnectionError()
                result.extend(part)
            return bytes(result)
        try:
            with socket.create_connection((self.config.coordinator_host, self.config.coordinator_port),
                                          timeout=self.config.timeout) as connection:
                # Verify model identity, never label another coordinator's weights as ours.
                config_message = ('CONFIG|'+request.request_id).encode()
                connection.sendall(struct.pack('!I', len(config_message))+config_message)
                size = struct.unpack('!I', exact(connection, 4))[0]
                if not 0 < size <= 2_000_000:
                    raise TemporaryError('invalid_coordinator_response')
                fields = exact(connection, size).decode('utf-8').split('|')
                if len(fields) != 8 or fields[:2] != ['CONFIG', request.request_id] or fields[6] != self.weights_hash:
                    raise TemporaryError('coordinator_weights_mismatch')
                message = ('IDENTIFY|'+request.request_id+'|'+','.join(map(str, request.pixels))+'|DISTRIBUTED').encode()
                connection.sendall(struct.pack('!I', len(message))+message)
                size = struct.unpack('!I', exact(connection, 4))[0]
                if not 0 < size <= 2_000_000:
                    raise TemporaryError('invalid_coordinator_response')
                fields = exact(connection, size).decode('utf-8').split('|')
                if len(fields) != 5 or fields[:4] != ['RESULT', request.request_id, '1', '3']:
                    raise TemporaryError('coordinator_error')
                return tuple(float(x) for x in fields[4].split(','))
        except (OSError, ValueError, UnicodeError):
            raise TemporaryError('coordinator_unavailable') from None
