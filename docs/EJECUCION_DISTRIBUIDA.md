# Ejecución distribuida — tres equipos

Validación física PENDIENTE. Esta guía permite usar direcciones Tailscale sin
editar fuentes; no implica que esos nodos hayan sido conectados en esta sesión.

| Nodo | Servicios | Puertos TCP habituales |
|---|---|---|
| 1 Windows | backend, worker Java, RabbitMQ, PostgreSQL | 9000, 9101, 5672, 5432 |
| 2 Ubuntu | CNN/MLP, worker AMQP y worker TCP Python | 9102; conexiones salientes a 5672 |
| 3 Windows | clientes Desktop/CLI/Web, worker C#, MariaDB/validador | 9103, 3306; gateway HTTP 8080 opcional |

15672 solo es el panel de administración cuando esté habilitado; no es AMQP.
Android y rediseño de bases de datos quedan fuera de Fase I.

1. Cada dueño inicia Tailscale con su cuenta y comprueba `tailscale status`,
   `tailscale ip -4` y `tailscale ping NOMBRE_REAL_DEL_OTRO_NODO`.
2. Copiar `config/distributed.example.env` a `.env` en cada equipo y sustituir
   todos los nombres `.example` por IP o MagicDNS reales. No se proporcionan IP
   ficticias. Introducir cuentas restringidas del broker fuera del control Git.
3. En nodo 1, BACKEND_BIND_HOST debe ser su dirección Tailscale local; en cada
   worker TCP, WORKER_<LENGUAJE>_HOST debe ser una dirección asignada a su equipo.
   El resto de equipos usa esas direcciones como destinos. No intentar enlazar
   un listener a una dirección perteneciente a otro dispositivo.
4. Revisar con el administrador los permisos Tailscale/ACL y reglas de acceso
   ya existentes. Los scripts no abren firewall ni exponen servicios públicamente.
   Configurar el listener RabbitMQ en la interfaz privada según su instalación.
5. Ejecutar los comandos de [ejecución local](EJECUCION_LOCAL.md) para cada
   servicio en su nodo correspondiente, cargando su `.env` con run_env.py.

El nodo 1 ejecuta backend y WorkerJava; nodo 2 ejecuta rabbit_worker.py y worker.py;
nodo 3 ejecuta `dotnet run --project workers/csharp/Worker.csproj`, clientes y,
si se valida BD2, `python databases/mariadb/validator_worker.py`.
El esquema SQL y credenciales los prepara el dueño de cada motor.
El validador reconoce RABBITMQ_PASSWORD; RABBITMQ_PASS queda como alias heredado.

Para comprobar conectividad de cada perfil:

```text
python scripts/run_env.py .env python scripts/check_node.py 1
python scripts/run_env.py .env python scripts/check_node.py 2
python scripts/run_env.py .env python scripts/check_node.py 3
```

check_node.py verifica autenticación RabbitMQ y/o SELECT 1 de solo lectura según
el perfil; requiere credenciales válidas. No acredita persistencia SQL ni
inferencia. La evidencia final debe incluir SO, hostname/IP privada,
versiones, logs de backend/worker y los mismos IDs de solicitudes por equipo.
Usar un ID distinto por solicitud; TCP heredado no transporta por separado un
ID estable de usuario. Para probar inferencia partida usar modo DISTRIBUTED;
para probar Java/Rabbit/Python en distintos nodos usar SEQUENTIAL vía RabbitMQ.

Si un nodo cae: comprobar Tailscale y proceso dueño del puerto; revisar
BACKEND_*, WORKER_* y RABBITMQ_*; no sustituir una dirección remota por localhost.
Backend devuelve errores con el ID original. Un timeout no acredita cancelación
de una tarea ya publicada: puede existir un resultado tardío, y no se promete
exactly-once. Solo un backend por pareja de colas compartidas de IA.

Fedora se añadirá después de que el profesor confirme el criterio de tercer SO.
No hay evidencia todavía de tres SO ni de tres computadoras en redes distintas.

## Timeouts y modos por entorno

INFERENCE_TRANSPORT=TCP|RABBITMQ selecciona transporte; INFERENCE_MODE=
SEQUENTIAL|DISTRIBUTED configura el modo inicial de CLI/Desktop (el argumento
explícito CLI prevalece). DISTRIBUTED parte operaciones; no acredita equipos
físicos distintos por sí solo.

BACKEND_WORKER_TIMEOUT_MS=10000, BACKEND_IDENTIFY_TIMEOUT_MS=12000 y
BACKEND_CLIENT_TIMEOUT_MS=30000 configuran límites del servidor.
RABBITMQ_REQUEST_TIMEOUT_MS=25000, RABBITMQ_CONFIRM_TIMEOUT_MS=5000 y
RABBITMQ_CONNECT_TIMEOUT_MS=5000 configuran la conexión/publicación Java.
CLIENT_TIMEOUT_MS=30000 es la espera predeterminada CLI/Desktop; la interfaz
Desktop la muestra en segundos. Mantener BACKEND_CLIENT_TIMEOUT_MS mayor que
RABBITMQ_REQUEST_TIMEOUT_MS+1000 y el cliente al menos tan paciente como el
backend. Los `-Dopenaicubes.*TimeoutMs` heredados prevalecen sobre el entorno.

Python usa IA_PROCESSING_TIMEOUT_SECONDS=10, IA_MAX_ATTEMPTS=3,
IA_RETRY_MS=1000 y RABBITMQ_HEARTBEAT=60. PC3_WORKER_TIMEOUT_MS=15000 y
PC3_WORKER_MAX_CLIENTS=64 controlan los workers TCP de los tres lenguajes.
Los límites no cancelan una tarea ya persistida en el broker.

Los puertos 5672, 5432, 3306, 9000, 9101-9103 y 15672 no deben publicarse a
Internet. Usar interfaces y reglas privadas Tailscale acordadas por sus dueños;
no se alteró el firewall ni se habilitó exposición pública en esta sesión.

## Evidencia de validación pendiente

Registrar, en cada nodo, SO, commit de integration, versiones y resultado del
perfil correspondiente. Windows debe ejecutar los .ps1 realmente, no solo
leerlos; Ubuntu debe ejecutar los .sh. Añadir `tailscale status`, las direcciones
privadas reales y `tailscale ping` entre pares. Para inferencia, correlacionar
idSolicitud en logs de Java/Python; para SQL, guardar salida del probe de solo
lectura y, cuando se valide persistencia, la evidencia adicional acordada con el
dueño de cada base de datos. No adjuntar secretos ni publicar estos puertos.

## Fase II: flujo validado y persistido

Copiar config/phase2.local.example.env (LOCAL) o phase2.distributed.example.env
(DISTRIBUTED) a .env y completar credenciales/destinos de su nodo. Seguir
[FASE2_SISTEMA_COMPLETO](integration/FASE2_SISTEMA_COMPLETO.md) para migraciones,
servicio db.PersistenceWorker, validador, IA, backend y clientes V2.
SYSTEM_PIPELINE=FULL no autoriza solicitudes sin identidad; CLIENT_PROTOCOL=V2
se aplica a Desktop/CLI/gateway y Android usa IDENTIFY2. Los ejemplos dejan 80 s
de timeout para la cadena validación/inferencia/persistencia. El gateway oficial
es web-server/http_gateway.py. No iniciar al mismo tiempo el alternativo Java
sobre el mismo puerto. Las pruebas concurrentes de esta fase no son benchmarks
finales ni acreditan despliegue físico entre equipos.
