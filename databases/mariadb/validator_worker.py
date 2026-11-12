#!/usr/bin/env python3
"""
Nodo BD2 (MariaDB) — Servicio de validación de clientes/solicitudes vía RabbitMQ.
Escucha `cola_validacion`, verifica en MariaDB de forma idempotente y transaccional,
y publica el dictamen en `cola_resultados_validacion`.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone

import mysql.connector
from mysql.connector import pooling
import pika

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [BD2-VALIDATOR] %(levelname)s: %(message)s",
)
logger = logging.getLogger("bd2_validator")
logging.getLogger("pika").setLevel(logging.CRITICAL)

# Configuración por variables de entorno (sin credenciales quemadas en código)
RABBIT_HOST = os.getenv("RABBITMQ_HOST", "127.0.0.1")
RABBIT_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBIT_USER = os.getenv("RABBITMQ_USER", "")
RABBIT_PASS = os.getenv("RABBITMQ_PASSWORD", os.getenv("RABBITMQ_PASS", ""))
RABBIT_VHOST = os.getenv("RABBITMQ_VHOST", "/")

QUEUE_IN = os.getenv("QUEUE_VALIDATION", "cola_validacion")
QUEUE_OUT = os.getenv("QUEUE_VALIDATION_RESULTS", "cola_resultados_validacion")

DB_HOST = os.getenv("MARIADB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("MARIADB_PORT", "3306"))
DB_NAME = os.getenv("MARIADB_DATABASE", "pc3_bd2")
DB_USER = os.getenv("MARIADB_USER", "pc3_validator")
DB_PASS = os.getenv("MARIADB_PASSWORD", "")


def create_db_pool() -> pooling.MySQLConnectionPool:
    return pooling.MySQLConnectionPool(
        pool_name="bd2_pool",
        pool_size=int(os.getenv("MARIADB_POOL_SIZE", "8")),
        pool_reset_session=True,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        autocommit=False,
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validar_solicitud_idempotente(db_pool, id_solicitud, id_cliente, auto_registrar_sintetico=False):
    """Unique INSERT wins; duplicate delivery reads the immutable committed verdict."""
    from workers.python.rabbit_messages import MessageError
    if auto_registrar_sintetico:
        raise ValueError('automatic_client_registration_disabled_use_explicit_seed')
    for attempt in range(3):
        conn, cursor = db_pool.get_connection(), None
        try:
            conn.start_transaction(isolation_level='READ COMMITTED')
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT id_cliente, aprobado, motivo FROM validaciones WHERE id_solicitud=%s FOR UPDATE', (id_solicitud,))
            previous = cursor.fetchone()
            if previous:
                if previous['id_cliente'] != id_cliente:
                    raise MessageError('idempotency_conflict')
                conn.commit()
                return bool(previous['aprobado']), previous['motivo']
            cursor.execute('SELECT estado FROM clientes WHERE id_cliente=%s LOCK IN SHARE MODE', (id_cliente,))
            client = cursor.fetchone()
            approved = client is not None and client['estado'] == 'ACTIVO'
            reason = 'CLIENTE_ACTIVO_AUTORIZADO' if approved else ('CLIENTE_BLOQUEADO' if client else 'CLIENTE_NO_REGISTRADO')
            cursor.execute('INSERT INTO validaciones(id_solicitud,id_cliente,aprobado,motivo,cliente_registrado) VALUES(%s,%s,%s,%s,%s)',
                           (id_solicitud,id_cliente,approved,reason,id_cliente if client else None))
            conn.commit()
            return approved, reason
        except mysql.connector.Error as error:
            conn.rollback()
            if error.errno in (1062,1213,1205) and attempt < 2:
                continue  # restart transaction: never overwrite the winning row
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            if cursor is not None: cursor.close()
            conn.close()


def main():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    from messaging.database_worker import DatabaseWorker, database_config
    import signal
    pool = create_db_pool()
    def validate(message):
        approved, reason = validar_solicitud_idempotente(pool,message['idSolicitud'],message['idCliente'])
        return {'aprobado':approved,'motivo':reason,'validador':'BD2-MariaDB'}
    worker = DatabaseWorker(database_config(QUEUE_IN,QUEUE_OUT),validate,'VALIDAR_CLIENTE','RESULTADO_VALIDACION')
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_: worker.stop.set())
    worker.run()

if __name__ == '__main__':
    main()
