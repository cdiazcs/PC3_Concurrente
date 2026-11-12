"""Fase 2: limites de admision, deadlines de frames y recuperacion TCP real."""
from concurrent.futures import ThreadPoolExecutor
import os
import socket
import subprocess
import sys
import threading
import time
import unittest

import test_protocol as protocol
ROOT = protocol.ROOT
from test_distributed import Forwarder


class WorkerLimitTests(protocol.ProtocolTests):
    def test_large_valid_frame_matches_all_workers(self):
        # About 1.8 MB: valid arithmetic request, not merely an oversized frame rejection.
        values = ','.join(['0.000000']*100000)
        message = 'JOB|large|dense|DENSE|100000|1|'+values+'|'+values+'|0'
        self.assertGreater(len(message.encode('utf-8')), 1_000_000)
        self.assertLess(len(message.encode('utf-8')), protocol.MAX_BYTES)
        for language in ('Java', 'Python', 'CSharp'):
            with self.subTest(language=language):
                reply = protocol.exchange('127.0.0.1', self.endpoints[language], message)
                fields = reply.split('|')
                self.assertEqual(fields[:5], ['PART', 'large', 'dense', '1', '1'])
                self.assertEqual(float(fields[5]), 0)
                self.assertGreaterEqual(int(fields[6]), 0)

    def worker(self, language, *, clients=4, timeout_ms=500, threads=1):
        port = self.free_port()
        commands = {
            'Java': ['java', '-cp', str(self.artifacts) + os.pathsep + str(ROOT/'lib'/'*'), 'WorkerJava'],
            'Python': [sys.executable, 'workers/python/worker.py'],
            'CSharp': ['dotnet', str(self.artifacts/'csharp/Worker.dll')],
        }
        environment = {**os.environ, 'PC3_WORKER_MAX_CLIENTS': str(clients),
                       'PC3_WORKER_TIMEOUT_MS': str(timeout_ms)}
        log = (self.artifacts/f'limits-{language}-{port}.log').open('w', encoding='utf-8')
        self.logs.append(log)
        process = subprocess.Popen(commands[language]+[str(port), str(threads)], cwd=protocol.ROOT,
                                   env=environment, stdout=log, stderr=subprocess.STDOUT)
        self.processes.append(process)
        end = time.monotonic()+15
        while time.monotonic() < end:
            if process.poll() is not None:
                self.fail('worker terminated: '+log.name)
            try:
                self.assertEqual(protocol.exchange('127.0.0.1', port, 'PING|ready'), 'PONG|ready|'+language)
                # Ensure the readiness connection has released its admission slot.
                time.sleep(.05)
                return port
            except OSError:
                time.sleep(.05)
        self.fail('worker not ready: '+log.name)

    def test_connection_limit_rejects_excess_and_recovers(self):
        for language in ('Java', 'Python', 'CSharp'):
            with self.subTest(language=language):
                port = self.worker(language, clients=2, timeout_ms=3000)
                clients = []
                try:
                    for index in range(2):
                        client = socket.create_connection(('127.0.0.1', port), timeout=2)
                        clients.append(client)
                        client.sendall(protocol.frame('PING|hold-'+str(index)))
                        self.assertEqual(protocol.receive(client), f'PONG|hold-{index}|{language}')
                    with socket.create_connection(('127.0.0.1', port), timeout=2) as excess:
                        excess.settimeout(.8)
                        try:
                            self.assertEqual(excess.recv(1), b'')
                        except ConnectionResetError:
                            pass
                    clients.pop().close()
                    end = time.monotonic()+2
                    while True:
                        try:
                            self.assertEqual(protocol.exchange('127.0.0.1', port, 'PING|recovered'),
                                             'PONG|recovered|'+language)
                            break
                        except (OSError, RuntimeError):
                            if time.monotonic() > end:
                                raise
                            time.sleep(.02)
                finally:
                    for client in clients:
                        client.close()

    def test_frame_deadline_covers_header_and_body_despite_drips(self):
        for language in ('Java', 'Python', 'CSharp'):
            port = self.worker(language, timeout_ms=400)
            for initial in (b'\0', b'\0\0\x27\x10'):
                with self.subTest(language=language, initial=initial):
                    stop = threading.Event()
                    with socket.create_connection(('127.0.0.1', port), timeout=2) as client:
                        client.settimeout(1.5)
                        client.sendall(initial)
                        def drip():
                            # Finish a 10000-byte header slowly, then never complete its body.
                            rest = b'\0\x27\x10' if len(initial) == 1 else b''
                            index = 0
                            while not stop.wait(.06):
                                try:
                                    client.sendall(rest[index:index+1] if index < len(rest) else b'x')
                                    index += 1
                                except OSError:
                                    return
                        thread = threading.Thread(target=drip, daemon=True)
                        started = time.monotonic()
                        thread.start()
                        try:
                            try:
                                self.assertEqual(client.recv(1), b'')
                            except ConnectionResetError:
                                pass
                            self.assertLess(time.monotonic()-started, 1.4)
                        finally:
                            stop.set()
                            thread.join(timeout=1)
                    self.assertTrue(protocol.exchange('127.0.0.1', port, 'PING|alive').startswith('PONG|alive|'))

    def test_idle_connection_does_not_occupy_compute_slot(self):
        for language in ('Java', 'Python', 'CSharp'):
            with self.subTest(language=language):
                port = self.worker(language, clients=4, timeout_ms=3000, threads=1)
                with socket.create_connection(('127.0.0.1', port), timeout=2) as idle:
                    # One idle handler must not consume the one arithmetic slot.
                    idle.sendall(b'\0')
                    reply = protocol.exchange('127.0.0.1', port,
                                              'JOB|active|dense|DENSE|2|1|1,2|3,4|5')
                    fields = reply.split('|')
                    self.assertEqual(fields[:5], ['PART', 'active', 'dense', '1', '1'])
                    self.assertEqual(float(fields[5]), 16)

    def test_coordinator_queue_saturation_is_bounded_and_recovers(self):
        gate, entered = threading.Event(), threading.Event()
        def before(fields):
            if fields[0] == 'JOB' and not gate.is_set():
                entered.set()
                gate.wait(timeout=3)
        with Forwarder(self.endpoints['Java'], before=before) as java:
            port = self.free_port()
            self.start(['java', '-Dopenaicubes.taskThreads=1', '-Dopenaicubes.maxQueuedChunks=2',
                        '-cp', str(self.artifacts) + os.pathsep + str(ROOT/'lib'/'*'), 'CentralServer', str(port),
                        '127.0.0.1:'+str(java.port),
                        '127.0.0.1:'+str(self.endpoints['Python'])], port, 'queue-limits')
            pixels = ','.join(['0']*256)
            def request(identifier):
                return protocol.exchange('127.0.0.1', port,
                                         'IDENTIFY|'+identifier+'|'+pixels+'|DISTRIBUTED')
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(request, 'first')
                try:
                    self.assertTrue(entered.wait(timeout=3))
                    started = time.monotonic()
                    self.assertEqual(request('overflow'), 'ERROR|overflow|coordinator_busy')
                    self.assertLess(time.monotonic()-started, 2)
                finally:
                    gate.set()
                self.assertTrue(first.result(timeout=5).startswith('RESULT|first|'))
            self.assertTrue(request('recovered').startswith('RESULT|recovered|'))


def load_tests(loader, tests, pattern):
    # Reuse fixture helpers without duplicating the legacy protocol test cases.
    return unittest.TestSuite(WorkerLimitTests(name) for name in sorted(WorkerLimitTests.__dict__)
                              if name.startswith('test_'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
