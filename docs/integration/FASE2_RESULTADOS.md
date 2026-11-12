# Fase II — resultados reales

Fecha: 12 de noviembre de 2026 (America/Lima). Rama: integration.
[Arquitectura y ejecución](FASE2_SISTEMA_COMPLETO.md).

## A. Estado: PARCIAL

El flujo completo de validación MariaDB, CNN Python y persistencia PostgreSQL
por RabbitMQ está implementado y probado contra servicios reales locales.
Android tiene proyecto Kotlin/Gradle y contrato JVM probado, pero no APK ni
prueba de dispositivo: falta Android SDK. Windows, red privada entre equipos
y ejecución remota de GitHub Actions tampoco se acreditan aquí.
No se avanzó a Fase III ni se realizaron benchmarks finales.

El PDF P3cc4P1-262_v07.pdf no está disponible. Se siguieron los requisitos
pegados, sin atribuir una nota ni afirmar comprobación directa de la rúbrica.

## B. Problemas encontrados y corregidos

- PostgreSQL escribía clasificación y estado en conexiones distintas y ocultaba
  SQLExceptions con prints. Ahora la unidad lógica usa una conexión/transacción
  y rollback, y las excepciones se propagan al servicio.
- No existía consumidor PostgreSQL ni confirmación de persistencia; se añadió
  usando JDBC/AMQP existentes y outbox transaccional.
- MariaDB creaba desconocidos para satisfacer una FK, autoautorizaba bench-* y
  sobrescribía el motivo de duplicados. Se eliminó ese comportamiento y se
  resolvieron carreras por PK/bloqueos/reintentos sin cambiar dictámenes previos.
- Backend no esperaba validación/persistencia y no distinguía identidad de
  cliente del ID de operación. FULL ahora exige ambas etapas y nunca devuelve
  RESULT antes de PERSISTIDA.
- Duplicados concurrentes del mismo ID chocaban entre etapas: se coalescen por
  ID/contenido; distinto contenido se rechaza como conflicto.
- La confirmación PostgreSQL inicial no incluía payload={} y era rechazada por
  el receptor. Se reprodujo con integración real y se corrigió el contrato.
- Mensajes con idCliente null podían cerrar el consumidor durante el rechazo;
  se saneó la respuesta y se agregó prueba real de ese caso.
- Web descartaba idCliente y su timeout de 15 s no cubría el pipeline. V2 lleva
  identidad/Base64 y usa deadline configurable de 80 s. Se validan IDs y números
  finitos/suma de probabilidades en la respuesta.
- El compilador de regresiones necesitaba incluir el nuevo coordinador Java;
  se corrigió la búsqueda recursiva, sin quitar pruebas.
- Android solo tenía README. Se creó proyecto Kotlin, wrapper y módulo de
  contrato JVM, sin frameworks de red.

## C. Archivos modificados o nuevos de Fase II

Además de los cambios locales de Fase I preservados:

- server-java/db/PostgresManager.java; nuevo PersistenceWorker.java.
- server-java/CentralServer.java; nuevo IntegratedPipeline.java.
- server-java/messaging/RabbitMQManager.java; nuevo DatabaseRpc.java.
- server-java/models/MensajesRabbit.java; nuevo DatabaseMessages.java.
- databases/postgresql/01_schema.sql (comentario), nuevo 02_phase2.sql.
- databases/mariadb/01_schema.sql (comentario), validator_worker.py;
  nuevo 03_phase2.sql. Se reutiliza 02_seed_clientes.sql sin auto-registro.
- Nuevo messaging/database_worker.py.
- clients-java/ClientCli.java, frontend-java/ImageClient.java,
  OpenAICubesPanel.java.
- clients/android/: settings/build.gradle.kts, gradle.properties, app Gradle,
  manifest, MainActivity.kt, Protocol.java, ProtocolChecks.java, módulo protocol,
  Gradle Wrapper 8.9 oficial y README.
- web-server/http_gateway.py y README; clients/web/README.md.
- scripts/build.py, check_integration.py, Check-Integration.ps1, unit_tests.py;
  nuevo phase2_integration.py.
- tests/test_protocol.py; nuevos test_phase2_contracts.py,
  test_phase2_integration.py, DatabaseContractChecks.java, Phase2Clients.java y
  PostgresTransactionChecks.java.
- Nuevos config/phase2.local.example.env y phase2.distributed.example.env.
- contracts/PROTOCOLO_TCP_V1.md y RABBITMQ_V1.md.
- .github/workflows/ci-main.yml (job real BD2/IA/BD1 separado).
- README.md, docs/INSTALACION_EQUIPO.md, EJECUCION_LOCAL.md,
  EJECUCION_DISTRIBUIDA.md, ARQUITECTURA_PC3.md, MATRIZ_PC3.md,
  integration/FASE2_SISTEMA_COMPLETO.md, este informe y evidencias/fase2/.

Los algoritmos CNN/MLP, pesos, dataset y worker C# no se alteraron por Fase II.
Los cambios anteriores de Fase I continúan locales y sin commit.

## D. PostgreSQL: transacciones y pruebas

PostgreSQL 18.6 real, ejecutado en directorio temporal con cuenta/contraseña
aleatoria de prueba, sin tocar el cluster del sistema.

APROBADOS: clasificación/estado/historial/outbox en una transacción, FK/PK,
metadata y vector JSON, duplicados sin repetir historial, conflicto de contenido,
publicación de confirmación recuperada de un COMMIT previo sin publicación,
reordenamiento JSON y duración recalculada, y concurrencia con IDs distintos.

Rollback real: un trigger de la base temporal lanza una excepción al actualizar
estado; se verifican CERO filas del ID en solicitudes, clasificaciones,
historial_consultas y outbox_persistencia. Backend devuelve persistence_failed.
La prueba crea y elimina su trigger únicamente en pc3_test_*.

## E. MariaDB: validación y pruebas

MariaDB 11.8.6 real, binarios de paquetes descargados/extractados solo en /tmp;
no se instaló ni arrancó servicio global. Conector 9.0.0 en .venv.

APROBADOS: ACTIVO, BLOQUEADO, inexistente y bench-* desconocido; no se crean
clientes desconocidos. Cuarenta llamadas concurrentes al mismo ID conservan un
solo dictamen; el mismo ID con otro cliente se rechaza. Cambiar el estado de
cliente después no modifica el dictamen original de esa solicitud.

La migración deja id_cliente declarado como dato auditable y cliente_registrado
como FK nullable para clientes reales. No se desactiva integridad global ni se
sobrescriben veredictos con ON DUPLICATE KEY UPDATE.

## F. RabbitMQ: flujo completo

RabbitMQ existente real (paquete 4.4.0, Erlang paquete 27.3.4.19), Pika 1.3.2 y
cliente Java incluido. Solo se crearon/eliminaron colas con UUID del experimento.

APROBADOS: validación -> inferencia -> solicitud de persistencia -> confirmación
correlacionada; 10, 50 y 100 solicitudes simultáneas con COMMIT confirmado e ID
conservado; duplicados concurrentes; mensajes de versión inválida y cliente null;
reintentos acotados; desconexión separada de validador, IA y persistencia.

Los errores observados son validation_timeout, inference_timeout y
persistence_pending según la etapa. El último no declara éxito ni que no haya
COMMIT: la persistencia puede completarse tras reconectar. No se promete
exactly-once de mensajes; unicidad SQL y outbox evitan repetir efectos durables.

## G. Android

Implementado: proyecto Gradle, app Kotlin/Activity, permiso INTERNET, chat,
cliente/host/puerto editables, selector del sistema, preview PNG/JPEG, botón,
Socket fuera del hilo principal, deadline/cierre, errores y parseo correlacionado.
No hay IP fija ni frameworks de red.

APROBADO: Gradle Wrapper 8.9 y :protocol:contractTest, tres tareas ejecutadas.
También framing/IDs/errores/probabilidades con Javac y el mismo Protocol.java
contra backend FULL real, con clasificación registrada en PostgreSQL.

NO VERIFICADO: APK y Activity en emulador/dispositivo. El intento real
:app:assembleDebug FALLÓ con `SDK location not found`. No se aceptaron licencias
ni se instaló un SDK global. Una prueba Java del protocolo NO acredita Android
funcionando. Ver [README Android](../../clients/android/README.md).

## H. Desktop

APROBADOS: compilación JDK 21, regresiones Swing headless de Fase I y flujo FULL
usando ImageClient.identifyImage. La prueba también acciona OpenAICubesPanel en
el EDT: carga imagen, introduce cliente, pulsa envío, recibe resultado y verifica
en PostgreSQL el ID generado por la UI. La selección mantiene un snapshot de la
imagen para evitar cambiarla durante consultas concurrentes.

Se añadió identificación editable y mensajes diferenciados de rechazo/persistencia.
NO VERIFICADO: ventana real en Windows y comunicación física por Tailscale.

## I. Web

APROBADOS: gateway oficial Python con sockets, HTTP -> TCP IDENTIFY2 -> flujo SQL
real -> HTTP, cliente ACTIVO, bloqueado e inexistente, correlación y probabilidades.
Se registró client-web como COMPLETADA y se compararon los dos SQL.
Gateway limita conexiones, cuerpos y deadlines, y valida cabeceras básicas.
El navegador no accede a RabbitMQ. El gateway Java alternativo se conservó pero
no se declara oficial ni integrado a V2.

NO VERIFICADO: sesión de navegador real en Windows. La integración HTTP se
probó mediante cliente HTTP automatizado sobre sockets reales.

## J. Pruebas aprobadas, fallidas y omitidas

| Ejecución final | Resultado |
|---|---|
| Unitarios sin servicios | 63 aprobados |
| Regresión general de construcción/TCP/IA/entrenamiento/workers/clientes | 159 descubiertas: 135 aprobadas, 24 omitidas |
| Integración real Fase II | 8 casos aprobados, 0 fallidos, 0 omitidos |
| Lotes concurrentes incluidos en los 8 casos | 10/10, 50/50 y 100/100 persistidos |
| Contratos Fase II unitarios | 6 aprobados, incluidos arriba |
| Android :protocol:contractTest | BUILD SUCCESSFUL |
| Android :app:assembleDebug | Fallo de entorno: falta SDK; APK NO VERIFICADO |

Los conjuntos se superponen: no sumarlos como casos distintos.
Las 24 omisiones generales son 15 opt-in AMQP/entrenamiento de Fase I, 1 perfil
que requiere seis núcleos físicos disjuntos, y los 8 de SQL real que se ejecutaron
por separado con sus servicios. Entrenamiento AMQP, reinicio/control del broker
compartido y ese perfil físico no fueron ejecutados en esta fase.
No se quitaron pruebas fallidas; los fallos intermedios se corrigieron y se
repitieron las comprobaciones afectadas.

Evidencia final en [evidencias/fase2](evidencias/fase2/): REGRESION_COMPLETA.txt,
SQL_RABBIT_CLIENTES.txt, ANDROID_JVM_GRADLE.txt, ANDROID_APK_NO_VERIFICADO.txt,
CONTRATOS_UNITARIOS.txt, trazas por componente y SOLICITUD_COMPLETA.json.
COMANDOS.txt registra los comandos y el alcance. CI está preparado, no ejecutado
remotamente; validar YAML localmente no equivale a GitHub Actions aprobado.

## K. Comandos Windows y Ubuntu

Comandos de cada servicio, SQL, Android y orden de arranque en
[FASE2_SISTEMA_COMPLETO](FASE2_SISTEMA_COMPLETO.md#arranque-por-integrante).

```powershell
# Perfil 1: JDK 21, backend; perfil 3: Java Desktop y .NET 8.
./scripts/Check-Integration.ps1 -Member 1
./scripts/Check-Integration.ps1 -Member 3
# Después de completar .env de su nodo, cada servicio en su terminal:
python scripts/run_env.py .env java -cp 'build;lib/*' db.PersistenceWorker
python scripts/run_env.py .env java -cp 'build;lib/*' CentralServer
python scripts/run_env.py .env python databases/mariadb/validator_worker.py
python scripts/run_env.py .env python web-server/http_gateway.py
python scripts/run_env.py .env java -cp 'build;lib/*' OpenAICubesGUI
./clients/android/gradlew.bat -p clients/android :app:assembleDebug
```

```bash
. .venv/bin/activate
bash scripts/check_integration.sh --member 2
python scripts/run_env.py .env python workers/python/rabbit_worker.py
# Revisión de todos los módulos en Linux con los runtimes disponibles:
bash scripts/check_integration.sh --tcp
# Solo con dos bases de prueba propias pc3_test_*:
python scripts/run_env.py .env python scripts/phase2_integration.py
# Alternativa Linux con SQL temporal y binarios ya disponibles:
python scripts/phase2_integration.py --isolated --postgres-bin /RUTA/PG/bin --mariadb-base /RUTA/MARIA
```

Los comandos de prueba real requieren broker. Los unitarios no requieren otros
integrantes. En Windows usar el python de .venv, como explica instalación.

## L. Dependencias y servicios

JDK 21, Python 3.10+ (aquí 3.14.4), .NET 8 para worker C# (aquí SDK 8.0.428),
Pika 1.3.2, mysql-connector-python 9.0.0; JAR existentes en lib/.
Nodo 1 posee PostgreSQL y broker/Erlang; nodo 3 MariaDB. Android requiere SDK 35,
Gradle Wrapper 8.9/Kotlin 2.0.21/AGP 8.7.3 fijados en el proyecto.
No se añadieron Spring, Flask, Django, WebSocket, Socket.IO, TensorFlow ni PyTorch.
No se instaló servicio global ni se cambió firewall.

## M. Variables de entorno

Ejemplos sin secretos: config/phase2.local.example.env y
config/phase2.distributed.example.env. SYSTEM_PIPELINE=FULL,
INFERENCE_TRANSPORT=RABBITMQ, CLIENT_PROTOCOL=V2 y CLIENT_ID para clientes.
BACKEND_*, WORKER_*, RABBITMQ_*, POSTGRES_*, MARIADB_* y colas configurables.
VALIDATION_TIMEOUT_MS=10000, RABBITMQ_REQUEST_TIMEOUT_MS=25000,
PERSISTENCE_TIMEOUT_MS=10000; BACKEND_CLIENT_TIMEOUT_MS y CLIENT_TIMEOUT_MS=80000.
WEB_BACKEND_TIMEOUT_SECONDS=80. BACKEND_MAX_CLIENTS=256 admite la prueba de 100
conexiones. No usar IP privada ajena como bind local ni localhost como otro nodo.

## N. Evidencia de una solicitud completa

[SOLICITUD_COMPLETA.json](evidencias/fase2/SOLICITUD_COMPLETA.json) proviene de
consultas reales a las dos bases temporales:

- idSolicitud: client-web; idCliente: cliente-web-01.
- MariaDB: aprobado=1, CLIENTE_ACTIVO_AUTORIZADO.
- PostgreSQL: estado COMPLETADA, etiqueta circulo.
- Probabilidades: [0.9999982471200074, 9.965471289921848e-9, 1.7429145213097573e-6].
- SHA-256: 9ed827285ae1e9922b63d8351086c1680abd5af23052859ecb8f56c035afdd73.
- Un historial y una confirmación en outbox para ese mismo ID.

Las trazas BACKEND/IA/MARIADB/POSTGRES_TRAZA.txt muestran ese ID entre etapas.
Los datos de prueba se retiraron junto con los procesos/directorios temporales;
se conserva evidencia sin credenciales. No implica red entre computadoras.

## O. Errores y limitaciones pendientes

Android APK/dispositivo; scripts y GUI en Windows; navegador real; Tailscale
físico; GitHub Actions remoto; revisión del PDF ausente. Dos motores SQL locales
sí se verificaron, pero no las instalaciones Windows de los compañeros.

Identificación no equivale a autenticación de usuario. Red privada, cuentas
restringidas y permisos los configura cada dueño. No hay API de historial SQL
ni escalado de varios backends sobre la misma cola de respuestas. Los timeouts
pueden dejar persistencia pendiente; hay recuperación por reentrega y outbox,
no exactly-once de mensajes. El worker PostgreSQL necesita reinicio al perder
su canal AMQP; el input durable y su confirmación permiten recuperar efectos.

Para modo matemático DISTRIBUTED opcional, IA debe usar coordinador TCP LEGACY
privado separado; no el puerto FULL, que impide saltarse validación. La ejecución
física DISTRIBUTED de Fase II puede usar SEQUENTIAL por RabbitMQ.

## P. Git y commit recomendado

Se verificó integration antes de editar. main y las ramas no se modificaron;
no hubo commit, push, merge ni rebase. Se preservó el trabajo anterior de Fase I.
Base HEAD: 9a4eda3. Todos los cambios permanecen locales para revisión.
Comprobar `git status`, `git diff` y archivos nuevos; después, si el equipo decide,
hacer MANUALMENTE un commit como:
`feat: integrar validacion BD2 persistencia BD1 y clientes fase II`.
No se ejecutó ese commit ni se propone hacerlo automáticamente.

## Q. Preparación para Fase III y explicación Feynman

Quedan implementados el flujo, contratos, SQL, idempotencia, clientes y pruebas
locales, pero Fase II sigue PARCIAL hasta validar Android y los entornos reales
pendientes. No se iniciaron benchmarks finales ni despliegue de tres SO.

Piensa en una imagen como un paquete con dos etiquetas: quién lo envía y qué
operación representa. Android/Desktop lo mandan por TCP; Web lo entrega primero
al gateway HTTP, que lo pasa por TCP. Java pregunta por RabbitMQ a MariaDB si
ese cliente puede participar. Si no puede, el paquete se detiene allí.

Si está autorizado, Python recibe la imagen ya preparada y la CNN calcula sus
probabilidades. Java pide después a PostgreSQL guardar resultado y estado en
una sola operación: se guarda todo o nada. Solo al volver el recibo PERSISTIDA
se entrega éxito al cliente. Si el recibo se pierde después de guardar, el
outbox permite enviarlo otra vez sin crear otra clasificación para el mismo ID.
