"""Smoke TCP real: Python worker -> Java backend -> Java CLI. Solo stdlib.

No prueba RabbitMQ ni distribucion fisica: valida el nucleo heredado que debe
permanecer funcional antes de fusionar ramas PC3.
"""
from pathlib import Path
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]

def free_port():
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1',0))
        return s.getsockname()[1]

def available(host,port,deadline):
    while time.monotonic()<deadline:
        try:
            with socket.create_connection((host,port),timeout=.15):
                return True
        except OSError:
            time.sleep(.08)
    return False

def main():
    if not shutil.which('javac') or not shutil.which('java'):
        print('Se necesitan javac y java para esta prueba de integracion', file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        java_files=[str(p) for name in ('clients-java','frontend-java','server-java','workers/java')
                    for p in (ROOT/name).glob('*.java')]
        subprocess.run(['javac','-encoding','UTF-8','-d',tmp,*java_files],cwd=ROOT,check=True,timeout=60)
        worker_port,server_port=free_port(),free_port()
        while server_port==worker_port:server_port=free_port()
        worker=subprocess.Popen([sys.executable,'workers/python/worker.py',str(worker_port)],
                                cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        backend=None
        try:
            if not available('127.0.0.1',worker_port,time.monotonic()+8):
                raise RuntimeError('No se inicio worker Python')
            backend=subprocess.Popen(['java','-cp',tmp,'CentralServer',str(server_port),
                                      '127.0.0.1:'+str(worker_port)],cwd=ROOT,
                                      stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            if not available('127.0.0.1',server_port,time.monotonic()+8):
                raise RuntimeError('No se inicio CentralServer')
            cmd=['java','-Djava.awt.headless=true','-cp',tmp,'ClientCli','127.0.0.1',str(server_port),'IDENTIFY',
                 'model/examples/circulo-0.png','smoke1','SEQUENTIAL']
            test=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=20)
            if test.returncode or 'Clase: circulo' not in test.stdout:
                raise RuntimeError('Clasificacion fallida: '+test.stdout+'\n'+test.stderr)
            print('OK: cliente Java -> TCP -> servidor Java -> worker Python -> resultado circulo')
            print('NOTA: RabbitMQ/BD/Android/Web no son parte de esta prueba')
            return 0
        finally:
            for p in (backend,worker):
                if p is not None:
                    p.terminate()
                    try:p.wait(timeout=5)
                    except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
                    if p.stderr:p.stderr.close()

if __name__=='__main__':
    try:sys.exit(main())
    except (RuntimeError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
        print('ERROR:',exc,file=sys.stderr)
        sys.exit(1)
