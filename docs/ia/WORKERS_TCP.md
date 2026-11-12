# Workers IA: ejecución, concurrencia y diagnóstico

## Herramientas y ejecución local

Desde la raíz efectiva del repositorio, con Python 3, JDK y SDK .NET 8 disponibles:

```bash
mkdir -p build/phase2-manual
javac --release 8 -encoding UTF-8 -d build/phase2-manual \
  server-java/*.java workers/java/*.java clients-java/*.java
dotnet build workers/csharp/Worker.csproj --nologo -o build/phase2-manual/csharp
```

En terminales distintas, con el mismo directorio de trabajo:

```bash
java -cp build/phase2-manual WorkerJava 9101 4
python3 workers/python/worker.py 9102 1
dotnet build/phase2-manual/csharp/Worker.dll 9103 4
java -cp build/phase2-manual CentralServer 9000 \
  127.0.0.1:9101 127.0.0.1:9102 127.0.0.1:9103
```

Prueba de inferencia (headless evita depender de X11):

```bash
java -Djava.awt.headless=true -cp build/phase2-manual ClientCli \
  127.0.0.1 9000 IDENTIFY model/examples/circulo-0.png demo-fase2 DISTRIBUTED
```

Los puertos son ejemplos y deben estar libres. Los scripts de pruebas asignan puertos locales dinámicos y detienen sólo sus propios procesos. Para diagnosticar se puede ejecutar `python3 tests/smoke_test.py 127.0.0.1:9101 127.0.0.1:9102 127.0.0.1:9103`.

En la validación de esta fase se preparó SDK 8.0.428/runtime 8.0.34 en `/tmp/pc3-dotnet8` mediante el [instalador oficial de Microsoft](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-install-script), con `--channel 8.0 --install-dir /tmp/pc3-dotnet8 --no-path`. Es una herramienta temporal; no un paquete añadido a Worker.csproj. No se modificaron PATH global, perfiles de shell ni paquetes del sistema. Tras borrar /tmp puede dejar de estar disponible. No se requiere instalarlo para usar una instalación .NET 8 ya disponible.

## Límites de los workers

| Configuración | Predeterminado | Rango | Alcance |
| --- | --- | --- | --- |
| Argumento 1 | Puerto específico del worker | Puerto TCP válido | Puerto de escucha |
| Argumento 2 | Python 1, Java/C# 4 | 1..256 | Cupos simultáneos de cálculo, anunciados en CAPS |
| PC3_WORKER_MAX_CLIENTS | 64 | 1..1024 | Conexiones admitidas por proceso, incluyendo las ociosas |
| PC3_WORKER_TIMEOUT_MS | 15000 | 100..300000 | Presupuesto total de lectura de un frame y espera máxima de un cupo de cálculo |

Las variables se leen al arrancar. Configuración fuera de rango detiene el inicio. Ejemplo Bash: `PC3_WORKER_MAX_CLIENTS=32 PC3_WORKER_TIMEOUT_MS=10000 python3 workers/python/worker.py 9102 1`. En PowerShell usar `$env:PC3_WORKER_MAX_CLIENTS='32'` y `$env:PC3_WORKER_TIMEOUT_MS='10000'` antes de iniciar el proceso.

Una conexión excedente se cierra antes de leer su solicitud: no hay ID conocido al que asociar un ERROR. El backlog del SO es distinto del conjunto de conexiones admitidas por la aplicación. Cliente/coordinador deben tratar EOF/reset como indisponibilidad y respetar sus propios plazos/reintentos acotados.

Python y C# reservan un cupo de conexión antes de crear el handler/tarea y lo liberan en finally. Java usa un executor máximo acotado sin cola de conexiones y un semáforo separado para el cálculo. Una conexión ociosa no ocupa el cupo de aritmética. PING/CAPS no consumen cupo de cálculo, pero sí conexión/handler. JOB y operaciones aritméticas sí lo consumen; Python incluye IDENTIFY. Al no conseguir un cupo dentro del plazo se devuelve worker_busy.

Java/C# ahora descuentan el tiempo transcurrido de un único deadline monotónico para cabecera y cuerpo completos. Mandar otro fragmento no renueva el plazo. Python ya implementaba esa política. Java además cierra el socket si una escritura supera su presupuesto; Python sendall y C# SendTimeout limitan escrituras. Estos presupuestos no son un deadline único para lectura+espera+cálculo+respuesta: el coordinador aplica su deadline de solicitud independiente. No hay preempción de una operación matemática CPU ya iniciada al desconectarse su cliente.

El cambio Java permite hasta MAX_CLIENTS handlers de conexión; su cantidad ya no coincide con el segundo argumento. CAPS sigue anunciando **cupos de cálculo**, no todos los hilos del runtime. En Python varios hilos de aritmética no acreditan uso simultáneo de varios núcleos en una ejecución con GIL. Para CPU paralela el agente existente inicia varios procesos Python con un hilo de cálculo cada uno. Los hilos auxiliares de Java/.NET, GC/JIT y control deben distinguirse en los futuros presupuestos experimentales.

## Mensajes implementados (referencia del código, sin cambiar contratos)

Frames: longitud positiva de cuatro bytes big-endian + UTF-8, máximo 2,000,000 bytes. Ver contracts/PROTOCOLO_TCP_V1.md para el contrato compartido. Las siguientes operaciones ya existían; esta fase conserva sus campos:

```text
CAPS|id
CAPS|id|Java/Python/CSharp|CONV,DENSE,POST[,IDENTIFY]|computeSlots

JOB|runId|taskId|CONV|rows|cols|kernelRows|kernelCols|imageCsv|kernelCsv
JOB|runId|taskId|DENSE|inputCount|outputCount|inputCsv|weightsCsv|biasCsv
JOB|runId|taskId|POST|POOL/RELU/SOFTMAX|rows|cols|valuesCsv
PART|runId|taskId|rows|cols|valuesCsv|computeNs
ERROR|runId|taskId|code
```

CONV devuelve un mapa válido por filtro. DENSE devuelve un bloque de filas lineales de W x+b; no aplica la ReLU de la capa siguiente. POST/POOL incluye ReLU y max pooling. El coordinador mantiene el ensamblado y las barreras entre capas; POST remoto se activa con `-Dopenaicubes.remotePostprocess=true`.

No confundir runId interno TCP con el futuro idSolicitud de RabbitMQ. El coordinador genera UUID+contador por ejecución, conserva el ID externo al responder, valida ambos IDs de cada PART y ensambla por offsets. Dos solicitudes con el mismo ID externo no comparten tensores. No hay todavía idempotencia durable extremo a extremo ni entrenamiento remoto de gradientes.

## Coordinación, fallos y observabilidad

DistributedCnn descubre CAPS, exige al menos dos workers capaces de CONV/DENSE y divide dos convoluciones y filas densas. No usa IDENTIFY completo como fallback silencioso del modo DISTRIBUTED. Si falla un chunk puede reintentarlo en otro nodo descubierto, dentro del plazo original; no publica resultados parcialmente mezclados. Si sólo participa un nodo devuelve insufficient_workers, incluso si ese nodo consiguió calcular todo.

La cola de chunks del coordinador es acotada: `openaicubes.taskThreads` y `openaicubes.maxQueuedChunks`. Si no admite trabajo devuelve coordinator_busy y cancela los pendientes de esa petición. Una cola demasiado pequeña puede rechazar incluso una solicitud aislada al cambiar de capa; configurar espacio acorde al número de chunks concurrentes. La regresión de saturación usa un hilo y dos puestos de cola para una capa de dos chunks, bloquea temporalmente un worker y comprueba rechazo y posterior recuperación.

Los logs NODE/TASK registran ID externo, run interno, chunk, endpoint, lenguaje, operación, tiempo de cálculo reportado, tiempo de RPC y estado. TENSOR sólo se activa con `openaicubes.traceValues=true`; permite comparar cada capa con la referencia Python. Es diagnóstico, no telemetría de CPU: computeNs de worker es tiempo pared del cálculo, no CPU agregado ni latencia de usuario.

## Pruebas reproducibles

```bash
python3 scripts/validate_phase2.py --dotnet-dir /tmp/pc3-dotnet8 --output build/phase2-nueva
```

Si dotnet está en PATH, omitir --dotnet-dir. El directorio debe ser nuevo. El script requiere las herramientas disponibles, no las instala. Usa el intérprete activo, crea un alias `python` sólo para sus hijos en POSIX cuando prepara la ejecución, activa headless y coloca caches CLI/NuGet bajo su salida. Ejecuta unittest completo y conserva tests.log/summary.json con versiones, resultados e integridad del modelo. Requiere que el entorno permita sockets locales y afinidad de procesos para las pruebas de benchmark existentes.

El usuario confirmó que por ahora sólo hay este equipo. **Tres lenguajes/procesos en localhost no son evidencia de tres máquinas ni de SO distintos.** La futura prueba remota debe registrar nodos reales, IP/SO, configuración CPU, hashes de pesos y trazas por tarea. No presentar las emulaciones localhost de los tests de benchmark como campaña distribuida física.
