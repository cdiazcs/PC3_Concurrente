# Instalación del equipo — Fase I

Trabajo exclusivamente en `integration`, con cambios locales sin commit.
No crear ramas ni realizar merge/rebase/push automático. No se requieren bases de datos ni broker para unitarios.
Los comandos siguientes son instrucciones para que cada dueño instale las
herramientas; los scripts del repositorio no instalan servicios globales.

| Herramienta | Versión / alcance |
|---|---|
| Git | 2.x; sin mínimo especial detectado |
| Java | JDK 21+ para compilar; bytecode `--release 17` conservado |
| Python | 3.10+ por anotaciones y APIs usadas; CI 3.12; ejecución local 3.14.4 |
| pip / venv | Del Python elegido; sin mínimo adicional identificado |
| .NET | SDK 8.0.x y runtime 8, proyecto `net8.0`, sin NuGet externos |
| RabbitMQ | Nodo 1; colas quorum con reintento at-least-once requieren 3.10+; referencia de esta fase 4.4.0 |
| Erlang/OTP | Solo dueño del broker; elegir par compatible con la versión exacta de RabbitMQ |
| PostgreSQL | Nodo 1; esquema usa SQL PostgreSQL, no se ha demostrado mínimo de servidor |
| MariaDB | Nodo 3; validar esquema existente en su versión instalada, mínimo no certificado |
| Tailscale | Cliente estable en cada nodo; versión mínima de proyecto no identificada |
| Android SDK | Fase II; no se necesita ni se instala en Fase I |

Dependencias incluidas: `lib/amqp-client-5.36.0.jar`, `gson-2.14.0.jar`,
`postgresql-42.7.14.jar`, `slf4j-api-2.0.13.jar`. Se usan todas mediante `lib/*`.
CNN, MLP, imágenes y entrenamiento usan biblioteca estándar Python.
AMQP Python requiere `pika==1.3.2`; BD2 añade `mysql-connector-python==9.0.0`.
No se usan Spring, Hibernate, NumPy ni frameworks de aprendizaje.

## Ubuntu — integrante 2

```bash
sudo apt update
sudo apt install git python3 python3-pip python3-venv
# Opcional para integración cruzada Java: sudo apt install openjdk-21-jdk
# Se usa JDK 21; release 17 es el formato de bytecode, no el JDK de construcción.
git clone https://github.com/cdiazcs/PC3_Concurrente.git
cd PC3_Concurrente
git switch integration
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r workers/python/requirements-amqp.txt
bash scripts/build.sh --component python
bash scripts/check_integration.sh --member 2
# Worker TCP Python local; no requiere Java ni .NET:
bash scripts/check_integration.sh --member 2 --tcp
# Solo con RabbitMQ configurado y accesible:
python scripts/run_env.py .env python scripts/check_integration.py --services --member 2
```

El integrante 2 no necesita instalar RabbitMQ, PostgreSQL ni MariaDB. Para probar
los tres lenguajes puede instalar .NET 8 opcionalmente según la
[guía oficial Ubuntu](https://learn.microsoft.com/en-us/dotnet/core/install/linux-ubuntu-install).
La prueba se ejecutó aquí con SDK temporal en `/tmp`, no una instalación global.

## Windows — integrantes 1 y 3

En PowerShell, instalar herramientas faltantes con los instaladores oficiales o:

```powershell
winget install --id Git.Git -e
winget install --id EclipseAdoptium.Temurin.21.JDK -e
winget install --id Python.Python.3.12 -e
winget install --id Microsoft.DotNet.SDK.8 -e
winget install --id Tailscale.Tailscale -e
# Abrir una consola nueva después de instalar.
git clone https://github.com/cdiazcs/PC3_Concurrente.git
cd PC3_Concurrente
git switch integration
py -3.12 -m venv .venv
$env:PYTHON = "$PWD/.venv/Scripts/python.exe"
& $env:PYTHON -m pip install -r workers/python/requirements-amqp.txt
./scripts/Build-Java.ps1
./scripts/Check-Integration.ps1
./scripts/Check-Integration.ps1 -Tcp
```

Integrante 1: además instalar PostgreSQL y RabbitMQ con Erlang compatible,
crear cuentas restringidas y aplicar `databases/postgresql/01_schema.sql`
con su administrador. No instalar MariaDB.
Integrante 3: instalar MariaDB y aplicar `databases/mariadb/01_schema.sql` y
`02_seed_clientes.sql` cuando corresponda. Instalar sus dependencias:

```powershell
& $env:PYTHON -m pip install -r databases/mariadb/requirements.txt
dotnet build workers/csharp/Worker.csproj
dotnet run --project workers/csharp/Worker.csproj -- 9103
# En otra consola, con .env completado; comprueba puertos reales:
& $env:PYTHON scripts/run_env.py .env $env:PYTHON scripts/check_node.py 3
```

Los perfiles locales se seleccionan con `--member 1|2|3` o `-Member 1|2|3`.
`--member 2` solo exige Python y Pika; no exige JDK ni .NET. `--member 1`
compila Java y verifica contratos con Python/Pika, sin requerir .NET.
`--member 3` exige JDK 21, SDK .NET 8, Python, Pika y el conector MariaDB.
Ningún perfil local exige broker, SQL ni compañeros conectados.

`--services` / `-Services` añade autenticación de los servicios del perfil:
1 comprueba RabbitMQ y PostgreSQL; 2 RabbitMQ; 3 MariaDB. Las consultas SQL son
`SELECT 1` dentro de una transacción READ ONLY seguida de rollback; RabbitMQ
solo abre/cierra conexión y canal, sin declarar colas. Una credencial vacía o
un servicio inaccesible devuelve error, no aprobación.
`--rabbit` / `-Rabbit` prueba inferencia completa Java/Python con colas temporales;
usarlo con perfil all o 1. Un login exitoso no acredita persistencia de resultados.

## Fedora — futura validación

```bash
sudo dnf install git java-21-openjdk-devel python3 python3-pip
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r workers/python/requirements-amqp.txt
# Opcional, cuando el repositorio Fedora correspondiente lo ofrezca:
sudo dnf install dotnet-sdk-8.0
bash scripts/check_integration.sh --tcp
```

Si no existe .NET 8 en la versión
Fedora elegida, seguir el instalador oficial de Microsoft en un directorio de
usuario. Fedora todavía NO VERIFICADO y no cuenta como tercer SO acreditado.

## Verificación de versiones

```text
git --version
java -version
javac -version
python --version
python -m pip --version
python -m venv --help
dotnet --list-sdks
dotnet --list-runtimes
rabbitmq-diagnostics server_version
erl -noshell -eval 'io:format("~s~n", [erlang:system_info(otp_release)]), halt().'
psql --version
mariadb --version
tailscale version
```

Solo ejecutar los comandos de servicios en el nodo que los posee. Versiones
observadas aquí: Java 21.0.13, Python 3.14.4, .NET SDK 8.0.428, RabbitMQ
paquete 4.4.0, Erlang paquete 27.3.4.19. PostgreSQL paquete 18 instalado no
significa integración SQL validada. Cliente Tailscale 1.104.5 instalado tampoco
acredita conexión entre equipos.

Referencias: [instalación RabbitMQ](https://www.rabbitmq.com/docs/download),
[matriz oficial Erlang](https://www.rabbitmq.com/docs/which-erlang),
[.NET 8](https://dotnet.microsoft.com/en-us/download/dotnet/8.0),
[Tailscale Windows](https://tailscale.com/docs/install/windows).
Consultar la matriz del broker antes de actualizar Erlang; no elegir ambos
paquetes independientemente.

## Errores frecuentes

- `package models/messaging/db does not exist`: compilación parcial antigua;
  ejecutar el script oficial que recorre los subdirectorios.
- `com.rabbitmq` o `Gson` ausente: conservar los JAR de `lib/` y usar classpath
  `build:lib/*` en Linux o `build;lib/*` en Windows (entre comillas).
- `UnsupportedClassVersionError`: usar Java 17+ también al ejecutar.
- `dotnet` ausente: C# y suites que requieren tres runtimes quedan NO VERIFICADAS.
- `pika` ausente: activar el venv e instalar requirements-amqp.txt.
- `ACCESS_REFUSED`: usuario, contraseña, vhost o permisos incorrectos; la cuenta
  guest solo sirve para loopback de desarrollo, no Tailscale.
- `PRECONDITION_FAILED`: cola existente con argumentos distintos; usar colas
  nuevas de prueba. No borrar colas compartidas para resolverlo.
- `timeout_ia`: worker detenido, sin consumidores o resultado no recibido.
- PowerShell bloquea scripts: revisar la política del equipo; puede ejecutar
  directamente `python scripts/check_integration.py --tcp` sin cambiarla.
- Sin sockets por aislamiento: ejecutar pruebas TCP en una terminal local con
  permiso de red. No equivale a un defecto numérico de la CNN.

## Comandos de validación por integrante

No utilizar los servicios de otro integrante para unitarios. Desde un clon en
`integration`, con dependencias instaladas, se dispone de estos tres perfiles.
Los ejemplos de shell cambian únicamente entre PowerShell y bash; el código es
el mismo.

### Perfil 1 — Windows backend

```powershell
$env:PYTHON = "$PWD/.venv/Scripts/python.exe"
& $env:PYTHON -m pip install -r workers/python/requirements-amqp.txt
./scripts/Check-Integration.ps1 -Member 1
# Integración TCP local amplia; para los tres lenguajes necesita SDK .NET 8:
./scripts/Check-Integration.ps1 -Member 1 -Tcp
# Completar .env antes: login RabbitMQ y SELECT 1 PostgreSQL sin modificar datos.
& $env:PYTHON scripts/run_env.py .env $env:PYTHON scripts/check_integration.py --member 1 --services
# Flujo real de inferencia Java/Python a través del broker:
& $env:PYTHON scripts/run_env.py .env $env:PYTHON scripts/check_integration.py --member 1 --rabbit
```

No ejecutar métodos guardarSolicitud/guardarResultado para comprobar conexión.
El entry point `db.PostgresManager` ahora solo realiza SELECT 1 READ ONLY.

### Perfil 2 — Ubuntu IA

```bash
. .venv/bin/activate
python -m pip install -r workers/python/requirements-amqp.txt
bash scripts/check_integration.sh --member 2
bash scripts/check_integration.sh --member 2 --tcp
# Login broker, sin declarar colas ni alterar servicios:
python scripts/run_env.py .env python scripts/check_integration.py --member 2 --services
# Procesos del nodo IA, cada uno en una terminal:
python scripts/run_env.py .env python workers/python/worker.py
python scripts/run_env.py .env python workers/python/rabbit_worker.py
```

El perfil 2 se comprobó con PATH sin Java/.NET. `--tcp` inicia y detiene su
worker Python en un puerto libre. No necesita levantar un backend remoto.
Para la prueba cruzada completa usar perfil all con JDK 21 y SDK .NET 8 opcional.

### Perfil 3 — Windows clientes / C# / MariaDB

```powershell
$env:PYTHON = "$PWD/.venv/Scripts/python.exe"
& $env:PYTHON -m pip install -r databases/mariadb/requirements.txt
./scripts/Check-Integration.ps1 -Member 3
./scripts/Check-Integration.ps1 -Member 3 -Tcp
# Autenticación MariaDB, SELECT 1 READ ONLY y rollback:
& $env:PYTHON scripts/run_env.py .env $env:PYTHON scripts/check_integration.py --member 3 --services
# Cada proceso en su terminal:
& $env:PYTHON scripts/run_env.py .env dotnet run --project workers/csharp/Worker.csproj
& $env:PYTHON scripts/run_env.py .env java -cp 'build;lib/*' OpenAICubesGUI
& $env:PYTHON scripts/run_env.py .env $env:PYTHON databases/mariadb/validator_worker.py
```

`--tcp` del perfil 3 prueba Desktop en headless con procesos Java/Python/C#
locales; no reemplaza abrir la ventana en Windows y usarla manualmente.
Android Fase II tiene proyecto Kotlin/Gradle, SDK objetivo 35 y contrato JVM
probado. El APK y la prueba de dispositivo siguen pendientes por falta de SDK
en este entorno; ver clients/android/README.md.

### Evidencia que debe entregar cada integrante

Guardar salida completa de compilación, pruebas, versiones y `git rev-parse HEAD`;
registrar SO y rama con `git branch --show-current`. Para PowerShell:

```powershell
./scripts/Check-Integration.ps1 -Member 1 -Tcp *> evidencia-perfil1.txt
$codigo = $LASTEXITCODE
Get-Content evidencia-perfil1.txt
Write-Host "Codigo de salida: $codigo"
```

Cambiar Member/archivo según integrante. En bash, conservar salida y estado:

```bash
bash scripts/check_integration.sh --member 2 --tcp > evidencia-perfil2.txt 2>&1
codigo=$?
cat evidencia-perfil2.txt
printf 'Codigo de salida: %s\n' "$codigo"
```

Las evidencias de red deben mostrar los mismos IDs en backend y worker, junto
con los equipos que realmente participaron. No incluir contraseñas ni volcar
variables de entorno completas en los registros.

## Fase II: bases de datos y clientes

Usar config/phase2.local.example.env o phase2.distributed.example.env. El backend
FULL exige validación MariaDB, inferencia AMQP y confirmación PostgreSQL. Los
servicios SQL deben aplicar sus migraciones antes de arrancar los consumidores.
PostgreSQL usa el JAR JDBC incluido; MariaDB mantiene requirements.txt existente.
No hay nuevas dependencias de Python para CNN/MLP. Android usa el Gradle Wrapper
8.9 incluido, Kotlin 2.0.21, AGP 8.7.3 y Android SDK 35 (minSdk 26).

La [guía completa de Fase II](integration/FASE2_SISTEMA_COMPLETO.md) contiene
SOURCE/psql, orden de arranque, comandos de cada integrante y pruebas reales
sobre bases pc3_test_*. El modo aislado no instala servicios globales; necesita
binarios PostgreSQL/MariaDB previamente disponibles en rutas indicadas.
`--phase2`/`-Phase2` ejecuta integración SQL real; `--android`/`-Android`
construye APK y devuelve error si falta SDK. Los unitarios siguen sin requerir
servicios remotos. No habilitar integración en bases de otros integrantes.
