"""Portable role profiles; external authenticated probes require --services."""
import argparse
import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]

def run(*args, env=None):
    subprocess.run([sys.executable,*args],cwd=ROOT,env=env,check=True)

def local_environment():
    # Local tests must not inherit listeners/transports of a running remote deployment.
    environment = dict(os.environ)
    environment.update(INFERENCE_TRANSPORT='TCP', INFERENCE_MODE='SEQUENTIAL',
        POSTGRES_ENABLED='false', BACKEND_BIND_HOST='127.0.0.1',
        WORKER_JAVA_HOST='127.0.0.1', WORKER_PYTHON_HOST='127.0.0.1',
        WORKER_CSHARP_HOST='127.0.0.1')
    for key in ('BACKEND_WORKER_TIMEOUT_MS', 'BACKEND_IDENTIFY_TIMEOUT_MS',
                'BACKEND_CLIENT_TIMEOUT_MS', 'CLIENT_TIMEOUT_MS',
                'PC3_WORKER_TIMEOUT_MS', 'PC3_WORKER_MAX_CLIENTS'):
        environment.pop(key, None)
    return environment

def dependencies(member):
    if sys.version_info < (3, 10):
        raise RuntimeError('Python 3.10+ requerido')
    print('Python:', sys.version.split()[0], flush=True)
    packages = {'1': ('pika',), '2': ('pika',), '3': ('pika','mysql-connector-python')}
    expected = {'pika': '1.3.2', 'mysql-connector-python': '9.0.0'}
    for package in packages.get(member, ()):
        actual = importlib.metadata.version(package)
        if actual != expected[package]:
            raise RuntimeError(f'{package}: requiere {expected[package]}, instalado {actual}')
        print(f'OK: {package}=={actual}', flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase2',action='store_true',help='BD2 -> IA -> BD1 reales, solo bases pc3_test_*')
    parser.add_argument('--android',action='store_true',help='construir APK con Android SDK instalado')
    parser.add_argument('--tcp',action='store_true',help='procesos TCP locales; no requiere otros equipos')
    parser.add_argument('--rabbit',action='store_true',help='inferencia AMQP real con colas temporales')
    parser.add_argument('--services',action='store_true',help='autenticacion de servicios del perfil, sin escribir datos')
    parser.add_argument('--member',choices=('all','1','2','3'),default='all')
    args=parser.parse_args()
    if args.services and args.member == 'all':
        parser.error('--services requiere --member 1, 2 o 3')
    if args.member not in ('all', '1') and args.rabbit:
        parser.error('--rabbit requiere perfil all o 1; para autenticar servicios del perfil usar --services')
    print('Perfil integrante:',args.member,flush=True)
    dependencies(args.member)
    if args.member == 'all':
        run('scripts/build.py')
        run('scripts/check_main.py')
    elif args.member == '1':
        run('scripts/build.py','--component','java')
        run('scripts/build.py','--component','python')
    elif args.member == '2':
        run('scripts/build.py','--component','python')
    else:
        run('scripts/build.py','--component','java')
        run('scripts/build.py','--component','csharp','--require-dotnet')
        print('Android: proyecto Kotlin/Gradle y contrato JVM; APK requiere --android y SDK',flush=True)
    local = local_environment()
    run('scripts/unit_tests.py','--member',args.member,env=local)
    if args.tcp:
        if args.member == '2':
            run('-m','unittest','discover','-s','tests','-p','test_cnn.py','-v',env=local)
        elif args.member == '3':
            run('-m','unittest','discover','-s','tests','-p','test_frontend.py','-v',env=local)
        else:
            run('-m','unittest','discover','-s','tests','-p','test_*.py','-v',env=local)
            run('scripts/smoke_main.py',env=local)
    else:
        print('NO VERIFICADO: integracion TCP (usar --tcp)',flush=True)
    if args.rabbit:
        run('scripts/rabbit_java_integration.py')
        run('-m','unittest','discover','-s','tests','-p','test_rabbit_integration.py','-v',
            env={**os.environ,'PC3_RABBIT_INTEGRATION':'1'})
    else:
        print('NO VERIFICADO: inferencia RabbitMQ real (usar --rabbit con all/1)',flush=True)
    if args.phase2:
        run('scripts/phase2_integration.py')
    if args.android:
        wrapper = ROOT/'clients/android'/('gradlew.bat' if os.name == 'nt' else 'gradlew')
        subprocess.run([str(wrapper),'-p',str(ROOT/'clients/android'),':app:assembleDebug'],cwd=ROOT,check=True)
    if args.services:
        run('scripts/check_node.py',args.member)
    else:
        print('NO VERIFICADO: autenticacion de servicios externos (usar --services --member N)',flush=True)

if __name__=='__main__': main()
