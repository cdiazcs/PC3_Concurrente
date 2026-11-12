# Ejecución local

Instalar las dependencias de [instalación](INSTALACION_EQUIPO.md).
Desde la raíz, copiar `config/local.example.env` a `.env`. El cargador
`scripts/run_env.py` acepta KEY=VALUE literal; no ejecuta código shell ni
expande variables. No añadir secretos al repositorio.

Compilación y unitarios Ubuntu:

```bash
. .venv/bin/activate
bash scripts/build.sh
bash scripts/check_integration.sh
```

Windows:

```powershell
./scripts/Build-Java.ps1
./scripts/Check-Integration.ps1
```

Estos comandos no requieren nodos externos. Si .NET falta se informa C#
NO VERIFICADO; no se cuenta como compilación exitosa de ese módulo.
Para exigir toda la matriz de runtimes, instalar JDK 21+, Python y SDK .NET 8.

## TCP local sin bases de datos ni RabbitMQ

En terminales separadas (en Windows usar `python` en vez de `python3` y
`build;lib/*` en vez de `build:lib/*`):

```bash
python3 scripts/run_env.py .env python3 workers/python/worker.py
python3 scripts/run_env.py .env java -cp 'build:lib/*' WorkerJava
python3 scripts/run_env.py .env dotnet run --project workers/csharp/Worker.csproj
python3 scripts/run_env.py .env java -cp 'build:lib/*' CentralServer
python3 scripts/run_env.py .env java -cp 'build:lib/*' ClientCli 127.0.0.1 9000 IDENTIFY model/examples/circulo-0.png local-1 SEQUENTIAL
python3 scripts/run_env.py .env java -cp 'build:lib/*' OpenAICubesGUI
```

Para una prueba mínima solo se necesita worker Python y backend con destino
explícito: `java -cp 'build:lib/*' CentralServer 9000 127.0.0.1:9102`.
`DISTRIBUTED` requiere suficientes workers con capacidad de operaciones JOB;
la CNN se divide mediante DistributedCnn. Con todos en loopback se comprueba
partición y protocolo, pero no distribución entre equipos físicos.

## Inferencia RabbitMQ real

Iniciar el broker por los mecanismos del dueño del servicio; estos scripts no
lo instalan ni reinician. Completar credenciales y poner
`INFERENCE_TRANSPORT=RABBITMQ` en `.env`. Ejecutar:

```bash
python3 scripts/run_env.py .env python3 workers/python/rabbit_worker.py
python3 scripts/run_env.py .env java -cp 'build:lib/*' CentralServer
python3 scripts/run_env.py .env java -cp 'build:lib/*' ClientCli 127.0.0.1 9000 IDENTIFY model/examples/circulo-0.png rabbit-1 SEQUENTIAL
```

La CNN AMQP no requiere worker TCP para SEQUENTIAL. El backend sigue recibiendo
una lista de destinos TCP para CONFIG/JOB/DISTRIBUTED; los valores por defecto
se obtienen del entorno. PostgreSQL está desactivado para integración de IA;
para habilitar el gestor existente, definir `POSTGRES_ENABLED=true` y completar
POSTGRES_* tras aplicar el esquema. La validación SQL sigue pendiente.

## Pruebas reproducibles

```bash
python3 scripts/unit_tests.py
python3 scripts/smoke_main.py
bash scripts/check_integration.sh --tcp
python3 scripts/run_env.py .env python3 scripts/check_integration.py --rabbit
```

```powershell
./scripts/Check-Integration.ps1 -Tcp
python scripts/run_env.py .env python scripts/check_integration.py --rabbit
```

`--tcp` ejecuta la suite completa, incluyendo pruebas de regresión existentes
que usan procesos y puertos libres; no ejecuta los experimentos finales de
rendimiento. `--rabbit` utiliza colas con UUID y las elimina al terminar; no usar
un broker de producción. Comprueba diez solicitudes desde Java, equivalencia con
CNN, IDs, mensaje inválido y desconexión/timeout. Las pruebas opt-in del broker
comprueban además reintentos, duplicados, persistencia y reinicio del worker.
No habilitar PC3_RABBIT_ALLOW_CONTROL en un broker compartido.

Los procesos iniciados manualmente se detienen con Ctrl+C. Los scripts de prueba
cierran sus propios procesos. No modifican firewall ni servicios de otros usuarios.

## Perfiles locales y servicios separados

`--member 1` compila Java y prueba contratos; `--member 2` comprueba Python,
CNN/MLP y, con `--tcp`, su worker local; `--member 3` compila Java Desktop y C#,
y con `--tcp` ejecuta las pruebas de clientes. Ver los comandos completos en
[instalación por integrante](INSTALACION_EQUIPO.md#comandos-de-validación-por-integrante).

Las comprobaciones remotas ya no se ejecutan implícitamente al elegir perfil:
se habilitan con `--services` / `-Services`. No se necesita que otros integrantes
estén conectados para ejecutar el perfil local. Una prueba de inferencia AMQP
completa se solicita con `--rabbit` para perfil all o 1; `--member 2 --services`
solo autentica el acceso al broker, sin necesitar Java.

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
