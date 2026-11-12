"""Authenticated, read-only service probes. Never creates queues or writes SQL."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

class ProbeConfigurationError(ValueError):
    pass

def rabbit():
    import pika
    from workers.python.rabbit_config import Config
    from workers.python.rabbit_worker import connection_parameters
    cfg = Config.from_env()
    connection = pika.BlockingConnection(connection_parameters(cfg, pika))
    try:
        channel = connection.channel()
        channel.close()
    finally:
        connection.close()
    print('OK: RabbitMQ autenticado; sin declarar ni publicar en colas', flush=True)

def postgres():
    from build import classpath
    for key in ('POSTGRES_USER', 'POSTGRES_PASSWORD'):
        if not os.environ.get(key):
            raise ProbeConfigurationError(key + ' requerida y vacia/no definida')
    subprocess.run(['java', '-cp', classpath(ROOT/'build'), 'db.PostgresManager'],
                   cwd=ROOT, check=True, timeout=15)

def mariadb():
    import mysql.connector
    for key in ('MARIADB_USER', 'MARIADB_PASSWORD'):
        if not os.environ.get(key):
            raise ProbeConfigurationError(key + ' requerida y vacia/no definida')
    connection = mysql.connector.connect(
        host=os.environ.get('MARIADB_HOST', '127.0.0.1'),
        port=int(os.environ.get('MARIADB_PORT', '3306')),
        database=os.environ.get('MARIADB_DATABASE', 'pc3_bd2'),
        user=os.environ['MARIADB_USER'], password=os.environ['MARIADB_PASSWORD'],
        connection_timeout=5, autocommit=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute('START TRANSACTION READ ONLY')
            cursor.execute('SELECT 1')
            if cursor.fetchone() != (1,):
                raise RuntimeError('invalid_database_response')
        connection.rollback()
    finally:
        connection.close()
    print('OK: MariaDB autenticado; SELECT 1 en transaccion READ ONLY, rollback', flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('member', choices=('1','2','3'))
    args = parser.parse_args()
    probes = {'1': (rabbit, postgres), '2': (rabbit,), '3': (mariadb,)}
    failed = False
    for probe in probes[args.member]:
        try:
            probe()
        except ProbeConfigurationError as error:
            print(f'NO VERIFICADO: {probe.__name__}: {error}', flush=True)
            failed = True
        except Exception as error:
            # Never include URLs, credentials or exception messages from drivers.
            print(f'FALLO: {probe.__name__} ({type(error).__name__}); revisar variables, permisos y servicio', flush=True)
            failed = True
    return int(failed)

if __name__ == '__main__':
    sys.exit(main())
