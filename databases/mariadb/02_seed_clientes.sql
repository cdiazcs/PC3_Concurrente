-- Clientes iniciales para validación en BD2
INSERT IGNORE INTO clientes (id_cliente, nombre_visible, estado) VALUES
('cliente-demo-01', 'Cliente Demo General', 'ACTIVO'),
('cliente-web-01', 'Cliente Web Browser', 'ACTIVO'),
('cliente-android-01', 'Cliente Movil Kotlin', 'ACTIVO'),
('cliente-desktop-01', 'Cliente Desktop Java', 'ACTIVO'),
('cliente-bloqueado-01', 'Cliente Suspendido Prueba', 'BLOQUEADO');