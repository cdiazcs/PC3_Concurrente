"""Run Phase II only on isolated DBs. --isolated starts temporary SQL processes, never system services."""
import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]

def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]

def wait_port(port,process):
    end=time.monotonic()+25
    while time.monotonic()<end:
        if process.poll() is not None:raise RuntimeError('SQL process exited; inspect build/phase2-fixture logs')
        try:
            with socket.create_connection(('127.0.0.1',port),.1):return
        except OSError:time.sleep(.1)
    raise RuntimeError('SQL startup timeout')

@contextmanager
def isolated(args):
    import mysql.connector
    temporary=tempfile.TemporaryDirectory(prefix='pc3-phase2-')
    folder=Path(temporary.name)
    processes=[];streams=[]
    environment=dict(os.environ)
    database='pc3_test_'+secrets.token_hex(6)
    password=secrets.token_hex(24)
    pg=Path(args.postgres_bin)
    maria=Path(args.mariadb_base)
    try:
        secret=folder/'pg-password';secret.write_text(password);secret.chmod(0o600)
        subprocess.run([str(pg/'initdb'),'-D',str(folder/'pg'),'-U','pc3_test',
                        '--auth=scram-sha-256','--pwfile',str(secret)],check=True,stdout=subprocess.DEVNULL)
        pg_port,maria_port=free_port(),free_port()
        for name,command in [
            ('postgres',[str(pg/'postgres'),'-D',str(folder/'pg'),'-p',str(pg_port),'-h','127.0.0.1','-k',str(folder)]),
        ]:
            stream=(ROOT/'build/phase2-fixture'/f'{name}.txt').open('w');streams.append(stream)
            process=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT);processes.append(process)
        wait_port(pg_port,processes[-1])
        environment.update(POSTGRES_HOST='127.0.0.1',POSTGRES_PORT=str(pg_port),POSTGRES_USER='pc3_test',
                           POSTGRES_PASSWORD=password,POSTGRES_DB=database,PGPASSWORD=password,PGHOST='127.0.0.1',
                           PGPORT=str(pg_port),PGUSER='pc3_test',PGDATABASE=database,PSQL=str(pg/'psql'))
        subprocess.run([str(pg/'createdb'),database],env=environment,check=True)
        stream=(ROOT/'build/phase2-fixture/mariadb-init.txt').open('w');streams.append(stream)
        subprocess.run([str(maria/'bin/mariadb-install-db'),'--no-defaults','--basedir='+str(maria),
                        '--datadir='+str(folder/'maria'),'--auth-root-authentication-method=normal','--skip-test-db'],
                       stdout=stream,stderr=subprocess.STDOUT,check=True)
        stream=(ROOT/'build/phase2-fixture/mariadb.txt').open('w');streams.append(stream)
        socket_path=str(folder/'maria.sock')
        process=subprocess.Popen([str(maria/'sbin/mariadbd'),'--no-defaults','--basedir='+str(maria),
            '--datadir='+str(folder/'maria'),'--bind-address=127.0.0.1','--port='+str(maria_port),
            '--socket='+socket_path,'--pid-file='+str(folder/'maria.pid'),
            '--skip-log-bin','--innodb-buffer-pool-size=64M'],stdout=stream,stderr=subprocess.STDOUT)
        processes.append(process);wait_port(maria_port,process)
        connection=mysql.connector.connect(unix_socket=socket_path,user='root')
        with connection.cursor() as cursor:
            cursor.execute('CREATE DATABASE '+database)
            cursor.execute("CREATE USER 'pc3_test'@'127.0.0.1' IDENTIFIED BY %s",(password,))
            cursor.execute("GRANT ALL ON "+database+".* TO 'pc3_test'@'127.0.0.1'")
        connection.close()
        environment.update(MARIADB_HOST='127.0.0.1',MARIADB_PORT=str(maria_port),MARIADB_DATABASE=database,
                           MARIADB_USER='pc3_test',MARIADB_PASSWORD=password)
        yield environment
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        for stream in streams:stream.close()
        temporary.cleanup()

def execute(environment):
    if any(not environment.get(name,'').startswith('pc3_test_') for name in ('POSTGRES_DB','MARIADB_DATABASE')):
        raise RuntimeError('Refusing integration outside explicitly isolated pc3_test_* databases')
    environment={**environment,'PC3_PHASE2_INTEGRATION':'1'}
    subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_phase2_integration.py','-v'],
                   cwd=ROOT,env=environment,check=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--isolated',action='store_true')
    parser.add_argument('--postgres-bin',default=os.environ.get('POSTGRES_BIN','/usr/lib/postgresql/18/bin'))
    parser.add_argument('--mariadb-base',default=os.environ.get('MARIADB_BASE',''))
    args=parser.parse_args()
    (ROOT/'build/phase2-fixture').mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,'scripts/build.py','--component','java'],cwd=ROOT,check=True)
    if args.isolated:
        if not args.mariadb_base:parser.error('--mariadb-base requerido; no se instalan servicios globales')
        with isolated(args) as environment:execute(environment)
    else:execute(dict(os.environ))
if __name__=='__main__':main()
