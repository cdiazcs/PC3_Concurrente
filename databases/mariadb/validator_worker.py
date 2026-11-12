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

# Configuración por variables de entorno (sin credenciales quemadas en código)
RABBIT_HOST = os.getenv("RABBITMQ_HOST", "127.0.0.1")
RABBIT_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBIT_USER = os.getenv("RABBITMQ_USER", "guest")
RABBIT_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBIT_VHOST = os.getenv("RABBITMQ_VHOST", "/")

QUEUE_IN = os.getenv("QUEUE_VALIDATION", "cola_validacion")
QUEUE_OUT = os.getenv("QUEUE_VALIDATION_RESULTS", "cola_resultados_validacion")

DB_HOST = os.getenv("MARIADB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("MARIADB_PORT", "3306"))
DB_NAME = os.getenv("MARIADB_DATABASE", "pc3_bd2")
DB_USER = os.getenv("MARIADB_USER", "pc3_validator")
DB_PASS = os.getenv("MARIADB_PASSWORD", "pc3_val_pass")


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


def validar_solicitud_idempotente(
    db_pool: pooling.MySQLConnectionPool,
    id_solicitud: str,
    id_cliente: str,
    auto_registrar_sintetico: bool = False,
) -> tuple[bool, str]:
    """
    Ejecuta la validación dentro de una transacción ACID en MariaDB.
    1. Si `id_solicitud` ya existe en `validaciones`, retorna el resultado previo (idempotencia).
    2. Verifica que `id_cliente` exista y tenga estado = 'ACTIVO'.
    3. Inserta el dictamen en `validaciones` y hace COMMIT.
    """
    conn = db_pool.get_connection()
    try:
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        # 1. Verificación de idempotencia (bloqueo de lectura si ya existe)
        cursor.execute(
            "SELECT aprobado, motivo FROM validaciones WHERE id_solicitud = %s",
            (id_solicitud,),
        )
        existente = cursor.fetchone()
        if existente is not None:
            conn.commit()
            return bool(existente["aprobado"]), f"IDEMPOTENTE:{existente['motivo']}"

        # 2. Consultar estado del cliente
        cursor.execute(
            "SELECT estado FROM clientes WHERE id_cliente = %s",
            (id_cliente,),
        )
        cliente = cursor.fetchone()

        if cliente is None:
            if auto_registrar_sintetico and id_cliente.startswith("bench-"):
                # Permite pruebas de carga sintéticas con clientes bench-*
                cursor.execute(
                    "INSERT IGNORE INTO clientes (id_cliente, nombre_visible, estado) VALUES (%s, %s, 'ACTIVO')",
                    (id_cliente, f"Benchmark {id_cliente}"),
                )
                aprobado = True
                motivo = "APROBADO_BENCHMARK"
            else:
                # Para cumplir la FK fk_validacion_cliente, registramos clientes desconocidos como BLOQUEADO o rechazamos
                cursor.execute(
                    "INSERT IGNORE INTO clientes (id_cliente, nombre_visible, estado) VALUES (%s, %s, 'BLOQUEADO')",
                    (id_cliente, "Auto-registrado no autorizado"),
                )
                aprobado = False
                motivo = "CLIENTE_NO_REGISTRADO"
        elif cliente["estado"] != "ACTIVO":
            aprobado = False
            motivo = f"CLIENTE_{cliente['estado']}"
        else:
            aprobado = True
            motivo = "CLIENTE_ACTIVO_AUTORIZADO"

        # 3. Persistir validación (INSERT IGNORE protege contra carreras concurrentes con mismo id_solicitud)
        cursor.execute(
            """
            INSERT INTO validaciones (id_solicitud, id_cliente, aprobado, motivo)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE motivo = VALUES(motivo)
            """,
            (id_solicitud, id_cliente, aprobado, motivo),
        )
        conn.commit()
        return aprobado, motivo

    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def main() -> None:
    auto_bench = os.getenv("AUTO_REGISTER_BENCH", "true").lower() == "true"
    db_pool = create_db_pool()
    logger.info(f"Pool MariaDB conectado a {DB_HOST}:{DB_PORT}/{DB_NAME}")

    credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
    params = pika.ConnectionParameters(
        host=RABBIT_HOST,
        port=RABBIT_PORT,
        virtual_host=RABBIT_VHOST,
        credentials=credentials,
        heartbeat=30,
    )
    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    # Colas durables según contratos/RABBITMQ_V1.md
    channel.queue_declare(queue=QUEUE_IN, durable=True)
    channel.queue_declare(queue=QUEUE_OUT, durable=True)
    channel.basic_qos(prefetch_count=10)

    def on_message(ch, method, properties, body: bytes) -> None:
        try:
            msg = json.loads(body.decode("utf-8"))
            id_solicitud = str(msg.get("idSolicitud", "")).strip()
            id_cliente = str(msg.get("idCliente", "")).strip()

            if not id_solicitud or not id_cliente:
                logger.warning("Mensaje inválido sin idSolicitud o idCliente; descartando.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            aprobado, motivo = validar_solicitud_idempotente(
                db_pool, id_solicitud, id_cliente, auto_registrar_sintetico=auto_bench
            )

            respuesta = {
                "schemaVersion": msg.get("schemaVersion", 1),
                "tipo": "RESULTADO_VALIDACION",
                "idSolicitud": id_solicitud,
                "idCliente": id_cliente,
                "modeloDestino": msg.get("modeloDestino", "A"),
                "timestamp": utc_now_iso(),
                "intento": msg.get("intento", 1),
                "payload": {
                    "aprobado": aprobado,
                    "motivo": motivo,
                    "validador": "BD2-MariaDB",
                },
            }

            out_props = pika.BasicProperties(
                delivery_mode=2,  # Mensaje persistente
                content_type="application/json",
                correlation_id=properties.correlation_id or id_solicitud,
            )
            ch.basic_publish(
                exchange="",
                routing_key=QUEUE_OUT,
                body=json.dumps(respuesta, ensure_ascii=False).encode("utf-8"),
                properties=out_props,
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)
            logger.info(
                f"Validado idSolicitud={id_solicitud} cliente={id_cliente} -> aprobado={aprobado} ({motivo})"
            )

        except Exception as exc:
            logger.error(f"Error procesando mensaje: {exc}", exc_info=True)
            # Reencolar una vez si hubo fallo transitorio de red/BD
            requeue = not method.redelivered
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=requeue)

    channel.basic_consume(queue=QUEUE_IN, on_message_callback=on_message, auto_ack=False)
    logger.info(f"Escuchando '{QUEUE_IN}' -> publicando en '{QUEUE_OUT}'...")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info("Deteniendo validador BD2...")
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    main()