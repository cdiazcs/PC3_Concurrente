# Fase II — sistema completo implementado

Código y pruebas en `integration`, sin commits automáticos. El PDF
P3cc4P1-262_v07.pdf no está presente: se implementan los requisitos pegados por
el usuario. Las referencias de página de la matriz histórica no se verificaron
directamente y no acreditan una nota ni resuelven las dudas A/B o tercer SO.

## Estado inicial antes de cambios

| Componente | Hallazgo inicial |
|---|---|
| Fase I | Build, contratos IA y workers existentes; regresiones reejecutadas |
| PostgreSQL | Resultado y actualización de estado en conexiones distintas; errores impresos |
| Persistencia AMQP | No había consumidor PostgreSQL |
| MariaDB | Registraba desconocidos, autoautorizaba bench-*, y sobrescribía motivo del duplicado |
| Backend | Inferencia sin coordinar validación ni confirmación de persistencia |
| Android | Solo README |
| Desktop | Swing/TCP funcional; identidad de cliente no viajaba separada |
| Web | Gateway socket funcional; descartaba identidad al construir IDENTIFY V1 |

## Arquitectura real

```mermaid
sequenceDiagram
    participant W as Navegador Web
    participant C as Android / Desktop / Gateway TCP
    participant B as Backend Java FULL
    participant R as RabbitMQ
    participant M as Validador MariaDB
    participant I as CNN Python
    participant P as Persistencia Java + PostgreSQL
    opt Cliente Web
        W->>C: HTTP al gateway propio
    end
    C->>B: IDENTIFY2, idSolicitud, idCliente, archivo Base64
    B->>R: cola_validacion
    R->>M: VALIDAR_CLIENTE
    M->>M: Transacción y dictamen inmutable
    M->>R: cola_resultados_validacion
    R->>B: Aprobado o rechazado
    alt Cliente aprobado
        B->>R: cola_modeloA, vector normalizado
        R->>I: INFERENCIA
        I->>R: cola_resultadosA
        R->>B: Clasificación correlacionada
        B->>R: cola_persistencia
        R->>P: GUARDAR_RESULTADO
        P->>P: Solicitud + clasificación + historial + outbox, un COMMIT
        P->>R: cola_resultados_bd, PERSISTIDA
        R->>B: Confirmación
        B->>C: RESULT con el mismo idSolicitud
    else Rechazado / timeout / error
        B->>C: ERROR correlacionado; sin éxito falso
    end
    opt Cliente Web
        C->>W: Respuesta HTTP JSON
    end
```

El gateway Web recibe HTTP/fetch y abre TCP propio al backend. No usa RabbitMQ
desde el navegador. La función de inferencia matemática DISTRIBUTED es distinta
del despliegue de nodos por Tailscale; consultar el contrato para su coordinador
LEGACY privado opcional. Fase II se valida en SEQUENTIAL por RabbitMQ.

## Servicios y dependencias

| Nodo | Procesos | Dependencias exclusivas |
|---|---|---|
| 1 Windows | CentralServer, db.PersistenceWorker, RabbitMQ, PostgreSQL | JDK 21, Erlang compatible con broker, JDBC incluido |
| 2 Ubuntu | workers/python/rabbit_worker.py; worker.py opcional para cálculo TCP | Python 3.10+, venv, pika 1.3.2 |
| 3 Windows | validator_worker.py, C#, Desktop, gateway, Android Studio | mysql-connector-python 9.0.0, Pika, .NET 8, JDK 21, MariaDB, Android SDK para APK |

No todos necesitan instalar ambos motores. La persistencia usa el JDBC ya
incluido; no se añadió psycopg ni otro framework. Android usa Activity, Kotlin y
sockets del SDK base. El gateway oficial usa socket Python, sin framework HTTP.

## PostgreSQL: esquema y transacciones

Aplicar 01_schema.sql y 02_phase2.sql en una base propiedad del nodo 1.
La migración agrega campos sin borrar tablas/datos:

- solicitudes: ID único, cliente/modelo, nombre/MIME/hash, JSON de metadatos,
  fecha y estado. Se rellena metadata ausente, nunca se pisa metadata existente.
- clasificaciones: FK/PK de solicitud, etiqueta, probabilidad, vector JSONB,
  duración y fecha.
- historial_consultas: evento PERSISTIDA de la solicitud y cliente.
- outbox_persistencia: ID único/FK, huella canónica y confirmación JSON durable.

PostgresManager.persistir abre UNA conexión, desactiva autocommit, bloquea la
solicitud por ID y ejecuta todas las escrituras y outbox antes de COMMIT.
Cualquier excepción revierte todo. Resultado/estado no se escriben en conexiones
separadas. Los métodos JDBC propagan errores: el worker responde ERROR.

Una huella sobre cliente/modelo/imagen/resultado detecta conflictos. Se ordenan
claves JSON y normalizan números; una nueva duración de cálculo no invalida el
mismo resultado. Un duplicado idéntico devuelve la confirmación guardada sin
repetir clasificación ni historial. Otro contenido devuelve conflicto.

El ACK AMQP va después de COMMIT y publicación confirmada. Si el proceso cae en
ese intervalo, el input durable sigue sin ACK: el broker reentrega y el outbox
se republica. No se requiere sondear otro dispatcher para esta estrategia; el
input sin ACK es el disparador de recuperación. No se promete exactly-once de
mensajes. El proceso Java debe reiniciarse si pierde su canal de publicación.

Las solicitudes rechazadas quedan auditadas en validaciones MariaDB y no llegan
a CNN ni se presentan como clasificadas en PostgreSQL. La UI muestra historial
de sesión; no se implementó una API para recuperar historial SQL desde el cliente.

## MariaDB: dictamen e identidad

Aplicar 01_schema.sql, 03_phase2.sql y seed de desarrollo explícito 02_seed_clientes.sql.
La tabla clientes no es modificada por el validador. ACTIVO aprueba; BLOQUEADO o
inexistente rechaza, incluidos bench-* desconocidos.

validaciones conserva el id_cliente declarado y un dictamen inmutable por
id_solicitud. cliente_registrado es FK nullable hacia clientes: así se registra
un rechazo desconocido sin inventar una cuenta para satisfacer una FK.
La migración sustituye la FK antigua por esta relación explícita.

Lecturas con bloqueo compartido de cliente y FOR UPDATE de validación,
transacción READ COMMITTED, restricción primaria y reintento tras duplicate-key/
deadlock resuelven carreras. No se hace UPSERT del motivo del duplicado.
Cambiar el cliente de un ID ya usado es conflicto; cambiar posteriormente su
estado no altera el dictamen almacenado de esa operación.

## Contratos y modos

[Contrato TCP](../../contracts/PROTOCOLO_TCP_V1.md) y
[contrato RabbitMQ](../../contracts/RABBITMQ_V1.md).
IDENTIFY2 transporta ID de operación y cliente separados, modo, MIME y Base64
real. El backend verifica firma, tamaño/dimensiones y preprocesa con el código
Java ya probado contra Python. Las probabilidades son del modelo oficial.

SYSTEM_PIPELINE=FULL obliga a BD2 -> IA -> BD1 y rechaza IDENTIFY V1 para impedir
bypass. LEGACY mantiene protocolo y pruebas de Fase I. CLIENT_PROTOCOL=V2 hace
que CLI/Desktop/gateway usen IDENTIFY2; Android siempre usa esa extensión.
Un ID duplicado en vuelo comparte el resultado; otro contenido produce conflicto.
No se bloquea globalmente el backend durante esperas: cada solicitud espera en
su hilo y las respuestas se correlacionan por etapa/ID/cliente.

RESULT se devuelve solo tras PERSISTIDA. Errores separan rechazo, timeout de
validación, fallo de inferencia, fallo de persistencia y persistence_pending.
Este último significa que la clasificación terminó pero no se confirmó el
COMMIT al cliente; puede llegar una confirmación tardía. Conservar el ID, no
convertirlo automáticamente en otra operación.

## Configuración LOCAL / DISTRIBUTED

Copiar config/phase2.local.example.env o phase2.distributed.example.env a .env.
No contienen contraseñas; completar las cuentas fuera de Git. Los nombres .example
son marcadores, no nodos reales. `scripts/run_env.py` carga KEY=VALUE sin evaluar
shell; cada proceso recibe las variables de su nodo.

Variables principales: SYSTEM_PIPELINE, CLIENT_PROTOCOL, CLIENT_ID,
BACKEND_HOST/PORT/BIND_HOST, WORKER_*_HOST/PORT, RABBITMQ_HOST/PORT/USER/PASSWORD/VHOST,
POSTGRES_HOST/PORT/DB/USER/PASSWORD, MARIADB_HOST/PORT/DATABASE/USER/PASSWORD.
Colas QUEUE_VALIDATION/RESULTS, QUEUE_PERSISTENCE/RESULTS e IA_REQUEST/RESULT_QUEUE.
Timeouts: validación 10 s, IA 25 s, persistencia 10 s; conexión de cliente/backend
80 s. Los ejemplos documentan todos los nombres exactos.

Puertos: backend 9000; AMQP 5672; PostgreSQL 5432; MariaDB 3306; workers 9101-9103;
gateway 8080; management 15672 si existe. No publicar estos puertos a Internet.
Para Tailscale obtener direcciones reales con tailscale ip -4/status/ping.
BACKEND_BIND_HOST y el bind de cada worker deben pertenecer a ese equipo.
No usar localhost para otro nodo. No se modificó firewall ni ACL.

## Arranque por integrante

Antes de arrancar, clonar el mismo repositorio y usar integration. Instalar
herramientas según [INSTALACION_EQUIPO](../INSTALACION_EQUIPO.md).

### 1 — Windows: broker, BD1, backend

Iniciar RabbitMQ y PostgreSQL usando los mecanismos de su instalación, sin
cambiar firewall. Aplicar esquemas solo a su base:

```powershell
psql -h HOST_PG -U USUARIO_PG -d BASE_PG -v ON_ERROR_STOP=1 -f databases/postgresql/01_schema.sql
psql -h HOST_PG -U USUARIO_PG -d BASE_PG -v ON_ERROR_STOP=1 -f databases/postgresql/02_phase2.sql
$env:PYTHON = "$PWD/.venv/Scripts/python.exe"
./scripts/Check-Integration.ps1 -Member 1
# Cada comando de servicio en su terminal, con .env completado:
& $env:PYTHON scripts/run_env.py .env java -cp 'build;lib/*' db.PersistenceWorker
& $env:PYTHON scripts/run_env.py .env java -cp 'build;lib/*' CentralServer
```

Los marcadores HOST_PG/USUARIO_PG/BASE_PG se sustituyen por configuración real.
El instalador PostgreSQL provee psql; no colocar passwords en la línea de comandos.

### 2 — Ubuntu: IA

```bash
. .venv/bin/activate
python -m pip install -r workers/python/requirements-amqp.txt
bash scripts/check_integration.sh --member 2
python scripts/run_env.py .env python workers/python/rabbit_worker.py
```

La IA solo necesita alcanzar el broker del nodo 1, no conectarse directamente a SQL.

### 3 — Windows: BD2, clientes

Aplicar con cliente mariadb conectado a su base (SOURCE funciona en Windows/Linux):

```sql
SOURCE databases/mariadb/01_schema.sql;
SOURCE databases/mariadb/03_phase2.sql;
-- Solo desarrollo y con aprobación del dueño de esa base:
SOURCE databases/mariadb/02_seed_clientes.sql;
```

En PowerShell:

```powershell
$env:PYTHON = "$PWD/.venv/Scripts/python.exe"
& $env:PYTHON -m pip install -r databases/mariadb/requirements.txt
./scripts/Check-Integration.ps1 -Member 3
# Cada servicio en una terminal:
& $env:PYTHON scripts/run_env.py .env $env:PYTHON databases/mariadb/validator_worker.py
& $env:PYTHON scripts/run_env.py .env java -cp 'build;lib/*' OpenAICubesGUI
& $env:PYTHON scripts/run_env.py .env $env:PYTHON web-server/http_gateway.py
& $env:PYTHON scripts/run_env.py .env dotnet run --project workers/csharp/Worker.csproj
```

Abrir el gateway HTTP en la interfaz privada configurada, ingresar un cliente del
seed y una imagen. Desktop tiene campo de identificación. Android se construye
con los comandos de [su README](../../clients/android/README.md) y se configura
desde la app; no tiene IP de PC fija.

En Ubuntu los comandos Java usan `build:lib/*` y python del venv. Orden sugerido:
SQL/broker -> validador/IA/persistencia -> backend -> gateway/clientes. Para
cierre, dejar terminar solicitudes, detener clientes/gateway/backend y luego
workers con Ctrl+C; por último los servicios SQL/broker de su dueño. Reiniciar
el worker PostgreSQL si termina con persistence_connection_closed.

## Pruebas reproducibles y seguras

```bash
python scripts/unit_tests.py
bash scripts/check_integration.sh --tcp
# Solo dos bases de prueba propias llamadas pc3_test_* y broker configurado:
python scripts/run_env.py .env python scripts/phase2_integration.py
# En Linux con binarios disponibles, SQL temporal sin servicios globales:
python scripts/phase2_integration.py --isolated --postgres-bin /RUTA/POSTGRES/bin --mariadb-base /RUTA/MARIADB
```

El modo externo utiliza POSTGRES_*, MARIADB_* y PSQL (psql por defecto).
Precrear dos bases pc3_test_* vacías y cuentas limitadas a ellas. El runner
rechaza otros nombres antes de DDL/pruebas y no borra bases de compañeros.
El modo --isolated crea directorios, claves aleatorias y procesos propios en
temporal, escucha solo loopback y los cierra al terminar. No instala servicios.
RabbitMQ debe existir y permitir colas propias de prueba; se usan nombres UUID.
Se verificaron 10/50/100 solicitudes concurrentes, no benchmarks finales.

PowerShell, con el mismo entorno de prueba:

```powershell
& $env:PYTHON scripts/run_env.py .env $env:PYTHON scripts/phase2_integration.py
./clients/android/gradlew.bat -p clients/android :protocol:contractTest
./clients/android/gradlew.bat -p clients/android :app:assembleDebug
```

--phase2/-Phase2 en los scripts existentes llama al runner externo de prueba;
--android/-Android intenta el APK y falla si falta SDK, nunca lo marca aprobado.
--services/-Services solo autentica y realiza SELECT 1, no crea esquemas.
Guardar logs, versiones, commit, SO, salidas de prueba y los IDs; no contraseñas.

## Límites reales

[Resultados de esta sesión](FASE2_RESULTADOS.md). Android APK/dispositivo,
Windows y despliegue físico no verificados. No se acreditó GitHub Actions remoto.
No hay API de consulta SQL de historial en las apps. Se conserva el gateway Java
alternativo pero el oficial es Python sobre sockets. Una sola instancia de
backend por pareja de colas; para varias instancias, aislar colas/workers.
La identificación de cliente no sustituye autenticación criptográfica de usuario.

## Comandos de arranque de motores (solo sus dueños)

Si los instaladores ya gestionan servicios Windows, usar esos servicios y no
arrancar una segunda instancia sobre el mismo puerto. Para procesos propios,
con los directorios bin/sbin correspondientes en PATH, ejemplos manuales:

```powershell
rabbitmq-diagnostics.bat -q ping
# Si su broker propio no esta iniciado, en su terminal:
rabbitmq-server.bat
# PostgreSQL: ruta del cluster propio ya inicializado, nunca una carpeta ajena.
pg_ctl -D 'RUTA_DATOS_POSTGRES_PROPIA' -l 'RUTA_LOG_POSTGRES' start
# MariaDB: archivo de configuracion propio preparado por su instalacion.
mariadbd --defaults-file='RUTA_CONFIG_MARIADB_PROPIA'
```

En Ubuntu, para un broker propio de desarrollo ya instalado, `rabbitmq-server`
lo ejecuta en primer plano; detener con el mecanismo de su instalación.
El nodo IA no necesita instalarlo. Estos son comandos para ejecutar manualmente
por sus dueños; Codex no instaló ni inició servicios globales durante las pruebas.
