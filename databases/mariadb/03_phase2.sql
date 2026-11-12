-- Additive, repeatable MariaDB migration after 01_schema.sql.
-- Keep the asserted ID even when unknown, without creating a clientes row.
ALTER TABLE validaciones DROP FOREIGN KEY IF EXISTS fk_validacion_cliente;
ALTER TABLE validaciones ADD COLUMN IF NOT EXISTS cliente_registrado VARCHAR(128) NULL;
ALTER TABLE validaciones ADD FOREIGN KEY IF NOT EXISTS fk_validacion_registrado
  (cliente_registrado) REFERENCES clientes(id_cliente);
