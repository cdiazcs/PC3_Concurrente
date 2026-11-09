# Bases de datos PC3

Scripts iniciales propuestos:

- `postgresql/01_schema.sql`: BD1 para consultas y clasificaciones del modelo A.
- `mariadb/01_schema.sql`: BD2 para la validación de clientes/consultas.

**No contienen un consumidor RabbitMQ ni un driver SQL.** Implementarlos por ramas, desplegar **cada BD en un nodo separado** y demostrar transacciones y claves idempotentes al insertar 1000 solicitudes con concurrencia. Confirmar con el profesor la inconsistencia de la página 4 sobre una tercera BD.

Ejemplo de ejecución manual en estaciones donde ya estén instalados los motores y credenciales:

```bash
psql -U USUARIO -d NOMBRE_BD -f databases/postgresql/01_schema.sql
mariadb -u USUARIO -p NOMBRE_BD < databases/mariadb/01_schema.sql
```
