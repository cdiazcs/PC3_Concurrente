-- BD2 de validación. Diseño inicial: ejecutar en MariaDB (motor distinto a PostgreSQL).
-- ESTADO: sólo schema; aún falta nodo AMQP y lógica real de validación.
CREATE TABLE IF NOT EXISTS clientes (
  id_cliente VARCHAR(128) NOT NULL PRIMARY KEY,
  nombre_visible VARCHAR(120) NULL,
  estado ENUM('ACTIVO','BLOQUEADO') NOT NULL DEFAULT 'ACTIVO',
  fecha_alta TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS validaciones (
  id_solicitud VARCHAR(128) NOT NULL PRIMARY KEY,
  id_cliente VARCHAR(128) NOT NULL,
  aprobado BOOLEAN NOT NULL,
  motivo VARCHAR(200) NOT NULL,
  fecha_validacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_validacion_cliente FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente),
  INDEX idx_validaciones_cliente_fecha (id_cliente, fecha_validacion)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- En pruebas, usar ids de clientes sintéticos; no guardar contraseñas en claro.
