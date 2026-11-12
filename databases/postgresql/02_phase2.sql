-- Additive migration; apply after 01_schema.sql, only to your own database.
BEGIN;
ALTER TABLE solicitudes ADD COLUMN IF NOT EXISTS metadatos_imagen JSONB;
ALTER TABLE clasificaciones ADD COLUMN IF NOT EXISTS probabilidades JSONB;
CREATE TABLE IF NOT EXISTS outbox_persistencia (
  id_solicitud VARCHAR(128) PRIMARY KEY REFERENCES solicitudes(id_solicitud),
  huella CHAR(64) NOT NULL,
  mensaje JSONB NOT NULL,
  fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMIT;
