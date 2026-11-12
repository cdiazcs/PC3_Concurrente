# Fase I — cierre multiplataforma y RabbitMQ

Fecha: 12 de noviembre de 2026, zona America/Lima.
Entorno comprobado: Ubuntu 26.04.1 LTS; rama de trabajo **integration**.

## 1. Estado: FASE I PARCIAL

Java/Python/C#, contratos, CNN/MLP, TCP y RabbitMQ real fueron verificados aquí.
Los tres integrantes disponen de perfiles reproducibles y configuración por
entorno. Faltan la ejecución de esos perfiles en los dos Windows, Fedora,
Tailscale entre computadoras, SQL autenticado/persistencia y GitHub Actions.
No se declara distribución física ni compatibilidad Windows probada.
No se implementó Fase II ni benchmarks finales.

## 2. Trabajo preservado y archivos modificados

Al comenzar había 55 archivos modificados/nuevos sin commit en
fix/phase1-multiplatform. Se respaldaron en
`/tmp/pc3-fase1-respaldo-d1gwc45p/cambios.tar.gz`, con manifest SHA-256.
HEAD de ambas ramas era 9a4eda3. Se ejecutó `git switch integration` y se
verificaron los 55 hashes: no se perdió contenido. No se creó ninguna rama.
Este es el procedimiento usado para incorporar los cambios locales a integration:
respaldo, comprobación de base idéntica, cambio de rama sin descartar y
comprobación de contenido. No fue necesario stash, merge, rebase ni commit.

Cambios acumulados de Fase I:

- Backend: CentralServer.java, WebGateway.java, models/MensajesRabbit.java,
  messaging/RabbitMQManager.java, db/PostgresManager.java y README_BACKEND.md.
- Clientes: clients-java/ClientCli.java, frontend-java/OpenAICubesGUI.java y
  OpenAICubesPanel.java.
- Workers: workers/java/WorkerJava.java, workers/csharp/Worker.cs,
  workers/python/worker.py y rabbit_messages.py.
- BD2: databases/mariadb/validator_worker.py (configuración, sin cambios SQL).
- Scripts existentes: Build-Java.ps1, check_main.py, smoke_main.py. Nuevos:
  build.py, build.sh, Check-Integration.ps1, check_integration.py,
  check_integration.sh, check_node.py, unit_tests.py, run_env.py y
  rabbit_java_integration.py.
- Tests: test_protocol.py, test_benchmark.py, test_distributed.py,
  test_frontend.py, test_identify.py, test_worker_limits.py,
  test_rabbit_messages.py; nuevos ContractChecks.java y test_cross_language.py.
- Portabilidad del helper existente: benchmarks/PhysicalConfig.java.
- CI: .github/workflows/ci-main.yml.
- Configuración y documentación: config/local.example.env,
  config/distributed.example.env, contracts/RABBITMQ_V1.md, README.md,
  docs/INSTALACION_EQUIPO.md, EJECUCION_LOCAL.md, EJECUCION_DISTRIBUIDA.md,
  integration/FASE1_MULTIPLATAFORMA.md, este informe y evidencias/.

Pesos, dataset, algoritmos CNN/MLP, Worker.csproj, requirements y esquemas SQL
oficiales permanecen sin modificaciones.

## 3. Problemas corregidos

La revisión confirmó que ya funcionaban compilación recursiva, classpath JAR,
payload explícito, ID correlacionado, selección de worker Python, validación de
respuestas TCP y coordinación DISTRIBUTED sin republicar IDENTIFY.
Se conservaron esas implementaciones y se completó lo siguiente:

- JDK 21 como herramienta de construcción y de CI, conservando bytecode release 17.
- Perfiles que seleccionan los componentes necesarios: IA no exige Java/.NET;
  backend no exige .NET; clientes exige Java y .NET 8.
- Separación explícita de unitarios/local TCP y servicios externos con --services.
- Verificación de versiones Pika/conector MariaDB; compilación C# con fallo real
  si falta SDK en el perfil que lo necesita.
- Login RabbitMQ sin declarar colas; PostgreSQL/MariaDB con SELECT 1 READ ONLY y
  rollback. El antiguo main de prueba PostgreSQL insertaba filas y fue reemplazado.
- Timeouts Java configurables por entorno y rechazo de límites incoherentes del
  backend AMQP antes de abrir la conexión.
- CLI/Desktop esperaban 15 s frente a los 25 s de RabbitMQ: ahora esperan 30 s
  por defecto, configurables; modo inicial también configurable por entorno.
- Pruebas locales aisladas de bind/timeouts de despliegue remoto; validado
  ejecutando perfil IA con un bind no local y timeout incompatible en el entorno.
- CI usa una cuenta efímera del broker para evitar depender de guest por NAT.
- Guías por integrante y evidencia actualizada exclusivamente sobre integration.

## 4. Compilación

| Módulo | Resultado real en Ubuntu |
|---|---|
| Java backend/worker/CLI/Swing | APROBADO: JDK 21.0.13, --release 17, lib/* |
| Python | APROBADO: Python 3.14.4, sintaxis e inferencia; stdlib para CNN/MLP |
| C# net8.0 | APROBADO: SDK 8.0.428, cero warnings y errores |

.NET está instalado temporalmente en `/tmp/pc3-phase1-dotnet`; no se exige esa
ruta en el código ni en los scripts de despliegue. Pika y mysql-connector se
instalaron en `.venv`, no globalmente. Los perfiles también ejercitaron los
workers Java/Python/C# reales en sockets locales.

## 5. Pruebas aprobadas, fallidas y omitidas

| Ejecución | Aprobadas | Fallidas | Omitidas |
|---|---:|---:|---:|
| Revalidación inicial, 144 descubiertas | 128 | 0 | 16 |
| Unitarios finales sin servicios | 57 | 0 | 0 |
| Regresión final completa, 144 descubiertas | 128 | 0 | 16 |
| Smoke Java CLI -> backend TCP -> Python CNN | 1 flujo | 0 | 0 |
| Perfil 1 local: contrato Java/Python | 1 | 0 | 0 |
| Perfil 2 sin Java/.NET: unitarios | 55 | 0 | 0 |
| Perfil 2: suite CNN y worker TCP Python | 24 | 0 | 0 |
| Perfil 3: contrato y Desktop/TCP headless | 1 + 7 | 0 | 0 |
| Regresión adicional modo/timeout CLI por entorno | 1 | 0 | 0 |
| Suite RabbitMQ real, 8 descubiertas | 6 | 0 | 2 |
| RabbitMQ -> coordinador -> Java/Python/C# | 1 | 0 | 0 |
| Login RabbitMQ sin declarar colas | 1 comprobación | 0 | 0 |

Los conjuntos se superponen: no sumar sus recuentos como pruebas distintas.
La nueva prueba de entorno se añadió después de cargar la suite completa y se
acreditó por separado; la siguiente discovery encontrará 145 casos. La antigua
cifra 143 excluía el caso de vector estricto agregado al final de la primera sesión;
la revalidación de esta sesión encontró 144 antes del nuevo caso de entorno.

Las 16 omisiones generales son 15 casos opt-in AMQP/entrenamiento y 1 perfil
con seis núcleos físicos disjuntos (solo cuatro disponibles). Las pruebas de
inferencia AMQP se ejecutaron por separado contra el broker real. Las dos
omisiones de esa suite requieren controlar conexiones/reiniciar el broker
compartido y no se habilitaron. Entrenamiento AMQP y ese control del broker siguen
NO VERIFICADOS. Se ejecutaron las regresiones de benchmarks existentes; no se
crearon ni corrieron los experimentos finales de Fase III.

Los probes SQL devolvieron código 1 por credenciales ausentes. Esto se registra
como integración NO VERIFICADA, no como una prueba SQL aprobada ni como un fallo
numérico de los módulos. No se intentó insertar datos ni configurar cuentas.

## 6. Evidencia RabbitMQ real

Broker local existente, paquete RabbitMQ 4.4.0 con Erlang/OTP paquete 27.3.4.19.
No se instaló ni reinició el servicio. Pika 1.3.2.

- Diez solicitudes simultáneas reales Java -> RabbitMQ -> CNN Python ->
  RabbitMQ -> Java, con IDs conservados y probabilidades comparadas con CNN.
- Mensaje TCP inválido rechazado.
- Worker propio detenido: Java responde timeout_ia a los 25.0 s.
- Suite de broker: correlación, ACK, publicación persistente, perfiles de imagen,
  duplicados/conflictos, JSON inválido, reintentos acotados, 50 solicitudes,
  control heartbeat y reinicio del worker.
- Ruta AMQP DISTRIBUTED usando coordinador Java y workers de los tres lenguajes
  completada sin ciclo de IDENTIFY.

Se usaron colas con UUID y se eliminaron únicamente las colas propias.
Autenticación y pruebas usaron la cuenta stock local de desarrollo por loopback,
sin guardar credenciales de despliegue. Tailscale requiere una cuenta restringida.

Evidencia actual: [evidencias/cierre](evidencias/cierre/), con logs completos de
regresión, perfiles, servicios y broker. [COMANDOS.txt](evidencias/cierre/COMANDOS.txt)
registra cómo se ejecutó. Las evidencias fuera de cierre/ corresponden a la
primera sesión y se conservan como históricas, no acreditan Windows ni red física.

## 7. Integrante 1 — Windows backend

Con JDK 21 y Python/venv instalados, desde integration:

```powershell
$env:PYTHON = "$PWD/.venv/Scripts/python.exe"
& $env:PYTHON -m pip install -r workers/python/requirements-amqp.txt
./scripts/Check-Integration.ps1 -Member 1
# Opcional: suite local de tres runtimes; necesita SDK .NET 8.
./scripts/Check-Integration.ps1 -Member 1 -Tcp
# Con .env completado, broker y PostgreSQL activos:
& $env:PYTHON scripts/run_env.py .env $env:PYTHON scripts/check_integration.py --member 1 --services
& $env:PYTHON scripts/run_env.py .env $env:PYTHON scripts/check_integration.py --member 1 --rabbit
& $env:PYTHON scripts/run_env.py .env java -cp 'build;lib/*' CentralServer
```

## 8. Integrante 2 — Ubuntu IA

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r workers/python/requirements-amqp.txt
bash scripts/check_integration.sh --member 2
bash scripts/check_integration.sh --member 2 --tcp
# Con .env completado y broker accesible:
python scripts/run_env.py .env python scripts/check_integration.py --member 2 --services
# Cada worker en su terminal:
python scripts/run_env.py .env python workers/python/worker.py
python scripts/run_env.py .env python workers/python/rabbit_worker.py
```

No requiere Java/.NET para su perfil. Para verificar el proyecto completo,
instalar JDK 21 y SDK .NET 8 y ejecutar `bash scripts/check_integration.sh --tcp`.

## 9. Integrante 3 — Windows clientes

```powershell
$env:PYTHON = "$PWD/.venv/Scripts/python.exe"
& $env:PYTHON -m pip install -r databases/mariadb/requirements.txt
./scripts/Check-Integration.ps1 -Member 3
./scripts/Check-Integration.ps1 -Member 3 -Tcp
# Con .env completado y MariaDB activo:
& $env:PYTHON scripts/run_env.py .env $env:PYTHON scripts/check_integration.py --member 3 --services
& $env:PYTHON scripts/run_env.py .env dotnet run --project workers/csharp/Worker.csproj
& $env:PYTHON scripts/run_env.py .env java -cp 'build;lib/*' OpenAICubesGUI
```

Los comandos PowerShell están preparados, pero no ejecutados en Windows aquí.
El perfil 3 sí se ejecutó desde bash en Ubuntu y eso solo acredita ese entorno.

## 10. Dependencias necesarias

[Instalación detallada](../INSTALACION_EQUIPO.md).
Todos: Git, Python 3.10+, pip/venv y Tailscale cuando prueben red.
Nodo 1: JDK 21, Pika 1.3.2, RabbitMQ/Erlang compatible y PostgreSQL.
Nodo 2: Python y Pika 1.3.2; Java/.NET solo para pruebas cruzadas opcionales.
Nodo 3: JDK 21, SDK .NET 8, MariaDB, Pika 1.3.2 y mysql-connector-python 9.0.0.
Los JAR RabbitMQ/Gson/JDBC/SLF4J están incluidos en lib/.
No exigir a todos instalar ambos motores SQL o un broker propio.
Android solo tiene README; faltan proyecto Gradle, SDK/API objetivo y aplicación.

## 11. Puertos y variables

Backend 9000; workers Java/Python/C# 9101/9102/9103; RabbitMQ 5672;
PostgreSQL 5432; MariaDB 3306; gateway opcional 8080; management RabbitMQ 15672
solo si está habilitado. No exponer estos servicios a Internet.

BACKEND_HOST/PORT es destino; BACKEND_BIND_HOST es interfaz local.
WORKER_*_HOST/PORT, RABBITMQ_*, POSTGRES_* y MARIADB_* se cargan del entorno.
INFERENCE_TRANSPORT=TCP|RABBITMQ selecciona transporte; INFERENCE_MODE=
SEQUENTIAL|DISTRIBUTED selecciona modo inicial de clientes. POSTGRES_ENABLED=false
permite probar IA sin SQL. Los timeouts están en los dos example.env y en
[EJECUCION_DISTRIBUIDA](../EJECUCION_DISTRIBUIDA.md#timeouts-y-modos-por-entorno).

Usar IP/MagicDNS reales de Tailscale, nunca loopback para otro equipo. El HOST
del worker, al iniciar ese worker, debe ser una dirección asignada a ese nodo.
No se cambió firewall ni se habilitaron listeners públicos.

## 12. Pendientes exactos

- Windows 1: ejecutar PS1/perfil 1, backend y broker reales, probe PostgreSQL.
- Windows 3: ejecutar PS1/perfil 3, worker C#, Desktop con ventana real, probe MariaDB.
- PostgreSQL/MariaDB: credenciales ausentes aquí; autenticación SELECT 1 y
  persistencia de solicitudes/resultados aún no acreditadas.
- Fedora: compilación/ejecución no realizadas; aceptación de tercer SO por profesor.
- Tailscale: interconexión real entre computadoras/redes, logs e IDs por nodo.
- GitHub Actions: workflow preparado para PR integration/main, JDK 21 y matriz
  Ubuntu/Windows, pero no ejecutado remotamente en esta sesión.
- GUI con pantalla real y endpoint HTTP Java: no se acreditan con los tests headless.
- Entrenamiento AMQP, reinicio/control broker compartido y seis núcleos físicos:
  omitidos explícitamente según los motivos anteriores.
- Android y rediseño SQL: Fase II, no implementados.

No hay garantía exactly-once ni cache de deduplicación persistente tras reinicio.
Un timeout no retira tareas ya publicadas; pueden existir resultados tardíos.
Cada pareja de colas de IA soporta un backend consumidor. Los gestores de
persistencia existentes registran errores SQL por stderr: una clasificación
exitosa no acredita su guardado en BD.

## 13. Commit manual en integration

No se ejecutó commit, push, merge ni rebase. main y los commits previos no se
modificaron. Los cambios continúan sin stage para revisión del equipo.

Solo cuando el equipo revise y decida guardar el trabajo, ejecutar manualmente:

```bash
git branch --show-current
# Debe mostrar integration. Si no, detenerse y revisar antes de continuar.
git status
git diff --check
git diff
# Revisar los archivos nuevos antes de añadirlos.
git add README.md .github/workflows/ci-main.yml scripts config docs contracts
git add server-java clients-java frontend-java workers tests databases/mariadb/validator_worker.py benchmarks/PhysicalConfig.java
git diff --cached --stat
git diff --cached
git commit -m "fix: cerrar integracion multiplataforma y contratos de fase I"
```

Estos comandos no fueron ejecutados por Codex. No crear ramas nuevas ni hacer
push/merge/rebase automático. No se propone modificar main.

## 14. Preparación para Fase II

Quedan disponibles build común, contratos ejecutados, workers, pruebas de errores,
perfiles por integrante y configuraciones LOCAL/DISTRIBUTED. La Fase I sigue
PARCIAL hasta recibir las validaciones externas. No se inició Android ni rediseño
SQL ni benchmarks finales.

Compilar es fabricar piezas que funcionan en una computadora. Distribuir es
poner esas piezas en computadoras distintas y comprobar que se comunican,
conservan IDs y responden de forma controlada cuando una conexión o un worker
falla. Las pruebas locales comprueban componentes y protocolos; la prueba real
entre los tres equipos debe aportar la evidencia física que todavía falta.
