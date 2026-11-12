"""Real Java TCP backend -> broker -> Python CNN -> broker -> Java. Isolated queues."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import time
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from build import compile_java,classpath
from workers.python.rabbit_config import Config
from workers.python.rabbit_worker import connection_parameters
from cnn_python.images import read_image
from cnn_python.model import CNN

def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); return sock.getsockname()[1]

def exchange(port,message):
    def exact(sock,count):
        data=b''
        while len(data)<count:
            part=sock.recv(count-len(data))
            if not part: raise RuntimeError('unexpected_eof')
            data+=part
        return data
    with socket.create_connection(('127.0.0.1',port),3) as sock:
        sock.settimeout(29)
        data=message.encode();sock.sendall(struct.pack('!I',len(data))+data)
        return exact(sock,struct.unpack('!I',exact(sock,4))[0]).decode()

def main():
    import pika
    cfg=Config.from_env()  # Credentials must be explicitly provided.
    token='phase1-'+uuid.uuid4().hex
    cfg=replace(cfg,request_queue=token,result_queue=token+'-results',retry_queue=token+'-retry',error_queue=token+'-errors')
    environment={**os.environ,'INFERENCE_TRANSPORT':'RABBITMQ','POSTGRES_ENABLED':'false',
        'IA_REQUEST_QUEUE':cfg.request_queue,'IA_RESULT_QUEUE':cfg.result_queue,
        'IA_RETRY_QUEUE':cfg.retry_queue,'IA_ERROR_QUEUE':cfg.error_queue,
        'IA_COORDINATOR_HOST':'','IA_COORDINATOR_PORT':'0','BACKEND_BIND_HOST':'127.0.0.1'}
    (ROOT/"build").mkdir(exist_ok=True)
    connection=pika.BlockingConnection(connection_parameters(cfg,pika))
    channel=connection.channel()
    processes=[]
    try:
        with tempfile.TemporaryDirectory() as tmp, (ROOT/'build/rabbit-java.log').open('w') as log:
            compile_java(tmp)
            worker=subprocess.Popen([sys.executable,'workers/python/rabbit_worker.py'],cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT)
            processes.append(worker)
            deadline=time.monotonic()+15
            while True:
                try:
                    # Inspect via a fresh channel: passive lookup can close a channel.
                    probe=connection.channel()
                    count=probe.queue_declare(cfg.request_queue,passive=True).method.consumer_count
                    probe.close()
                    if count: break
                except pika.exceptions.ChannelClosedByBroker: pass
                if time.monotonic()>deadline: raise RuntimeError('worker_not_ready: build/rabbit-java.log')
                connection.process_data_events(time_limit=.1)
            port=free_port()
            backend=subprocess.Popen(['java','-cp',classpath(tmp),'CentralServer',str(port),'127.0.0.1:'+str(free_port())],cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT)
            processes.append(backend)
            deadline=time.monotonic()+10
            while True:
                try:
                    with socket.create_connection(('127.0.0.1',port),.1): break
                except OSError:
                    if backend.poll() is not None or time.monotonic()>deadline: raise RuntimeError('backend_not_ready')
                    time.sleep(.05)
            pixels=read_image(ROOT/'model/examples/circulo-0.png')
            reference=CNN.load().predict(pixels).probabilities
            csv=','.join(map(str,pixels))
            def classify(i):
                identifier=token+'-'+str(i)
                reply=exchange(port,'IDENTIFY|'+identifier+'|'+csv+'|SEQUENTIAL').split('|')
                assert reply[:4]==['RESULT',identifier,'1','3'],reply
                assert len(reply[4].split(',')) == 3, reply
                assert all(abs(float(a)-b)<1e-8 for a,b in zip(reply[4].split(','),reference)),reply
                return reply[1]
            with ThreadPoolExecutor(max_workers=10) as pool:
                ids=list(pool.map(classify,range(10)))
            assert len(set(ids))==10
            print('OK: 10 solicitudes concurrentes Java -> RabbitMQ -> CNN Python -> RabbitMQ -> Java; IDs conservados',flush=True)
            assert exchange(port,'IDENTIFY|invalid|0|SEQUENTIAL')=='ERROR|invalid|invalid_image_size'
            print('OK: solicitud TCP invalida rechazada',flush=True)
            worker.terminate();worker.wait(timeout=15)
            start=time.monotonic()
            reply=exchange(port,'IDENTIFY|disconnected|'+csv+'|SEQUENTIAL')
            assert reply=='ERROR|disconnected|timeout_ia',reply
            print(f'OK: worker desconectado devuelve timeout en {time.monotonic()-start:.1f}s',flush=True)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill();process.wait()
        if connection.is_open:
            for queue in (cfg.request_queue,cfg.result_queue,cfg.retry_queue,cfg.error_queue):
                channel.queue_delete(queue)
            connection.close()
if __name__=='__main__': main()
