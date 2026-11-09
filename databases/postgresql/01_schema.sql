-- BD1 del modelo A. Diseño inicial: ejecutar sobre PostgreSQL.
-- ESTADO: sólo schema; aún falta worker AMQP, consultas y pruebas concurrentes.
BEGIN;
CREATE TABLE IF NOT EXISTS solicitudes (
  id_solicitud VARCHAR(128) PRIMARY KEY,
  id_cliente VARCHAR(128) NOT NULL,
  modelo VARCHAR(24) NOT NULL DEFAULT 'A',
  nombre_archivo VARCHAR(255),
  tipo_imagen VARCHAR(80),
  sha256_imagen CHAR(64),
  fecha_solicitud TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  estado VARCHAR(24) NOT NULL DEFAULT 'RECIBIDA'
    CHECK (estado IN ('RECIBIDA','VALIDADA','PROCESANDO','COMPLETADA','ERROR'))
);
CREATE INDEX IF NOT EXISTS idx_solicitudes_cliente_fecha
  ON solicitudes (id_cliente, fecha_solicitud DESC);
CREATE TABLE IF NOT EXISTS clasificaciones (
  id_solicitud VARCHAR(128) PRIMARY KEY REFERENCES solicitudes(id_solicitud),
  etiqueta VARCHAR(64) NOT NULL,
  probabilidad NUMERIC(12,10) NOT NULL CHECK (probabilidad >= 0 AND probabilidad <= 1),
  fecha_resultado TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  duracion_ms NUMERIC(12,3) CHECK (duracion_ms IS NULL OR duracion_ms >= 0)
);
CREATE TABLE IF NOT EXISTS historial_consultas (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id_solicitud VARCHAR(128) NOT NULL REFERENCES solicitudes(id_solicitud),
  id_cliente VARCHAR(128) NOT NULL,
  evento VARCHAR(64) NOT NULL,
  fecha TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  detalle TEXT
);
COMMIT;
