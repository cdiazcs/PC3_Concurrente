# Fase 2 — Concurrencia e inferencia distribuida

Registro de la ejecución original. La confirmación contra el adjunto específico, sus diagramas, el test de frame válido grande y las mediciones preliminares están en [FASE2_CONCURRENCIA_DISTRIBUCION.md](FASE2_CONCURRENCIA_DISTRIBUCION.md) y [FASE2_RESULTADOS.md](FASE2_RESULTADOS.md). Estado vigente: IMPLEMENTACIÓN LISTA / DESPLIEGUE DISTRIBUIDO PENDIENTE.

Fecha: 2026-11-12 (America/Lima). Rama `feature/ai-distributed`, base `798fee1`. Se conservaron todos los cambios de fase 1 y los documentos sin versionar de fases anteriores. Esta ejecución valida inferencia/coordinación TCP; no implementa RabbitMQ ni entrenamiento distribuido. El usuario confirmó que sólo dispone de este equipo: toda la evidencia es localhost en Ubuntu, no tres máquinas/SO.

## Entorno desbloqueado

JDK 21.0.13, Python 3.14.4 y SDK .NET 8.0.428/runtime 8.0.34. Se descargó el instalador oficial Microsoft y se preparó el SDK únicamente en `/tmp/pc3-dotnet8`, con `--no-path`. No hay paquetes NuGet nuevos, cambios de Worker.csproj ni configuración global. La descarga del SDK fue 217266728 bytes; instalación y compilación C# correctas. Ver WORKERS_TCP.md y su enlace a documentación oficial.

Las pruebas requieren sockets locales fuera del sandbox restrictivo. El runner usa headless para Java y crea un alias `python` sólo dentro de su entorno de hijos en POSIX, porque el sistema sólo ofrece python3. CLI/caches .NET se ubican en el directorio de evidencia. No se reutiliza la ausencia de .NET como razón para dejar Java/Python sin verificar: ahora corrieron los tres workers reales.

## Línea base: analizar y probar antes de modificar

Primero se ejecutó `python3 -m unittest discover -s tests -p test_distributed.py -v` con las herramientas preparadas: **15/15 OK**, 20.244 s de unittest (20.41 s proceso). Por tanto, chunks, barreras y ensamblado ya funcionaban: no se reescribió DistributedCnn ni se añadió un algoritmo sustituto.

Evidencia de esa línea base:

- Mismas 300 imágenes test y pesos oficiales: 300/300 correctas en SEQUENTIAL y 300/300 en DISTRIBUTED; diferencia máxima entre probabilidades 4.9948933877885793e-13.
- Tensores de cada capa comparados con Python: máximo error 2.6645352591003757e-15.
- Trazas reales de CONV y DENSE en Java, Python y CSharp, ocho chunks por inferencia con configuración predeterminada de tres workers.
- Solicitudes concurrentes con IDs externos repetidos, desorden de respuestas, barreras, caída/reinicio de worker, resultados parciales corruptos, timeout y rechazo de un único worker pasan las pruebas existentes.

La revisión adicional encontró riesgos que esa suite no cubría. Se probaron antes de corregirlos, con procesos propios y puertos locales dinámicos:

| Experimento original | Java | Python | C# |
| --- | --- | --- | --- |
| 80 conexiones abiertas, cierres/rechazos en 1 s | 0 | 0 | 0 |
| Frame incompleto de 10000 bytes, envío cada .05 s; cierre antes de 16.5 s | No | Sí, a los 15.0004 s | No |

La ausencia de límite se corroboró en fuente: Python creaba un hilo por conexión; C# creaba Task.Run por conexión; Java encolaba conexiones sin cota en un pool fijo. Java y C# tenían timeout por cada lectura; cada nuevo fragmento lo renovaba. Python ya descontaba un deadline total del frame. Además, Java con un hilo y una conexión ociosa impidió ejecutar un JOB por otra conexión: el pool de conexiones era también el pool de cálculo.

Las nuevas regresiones contra la implementación original produjeron 10 errores de subcasos y un fallo en cuatro métodos de test (28.496 s). Los tests de deadlines usan configuración corta nueva; Python también falló allí porque aún no leía esas variables, no porque careciera de deadline absoluto. El fallo de cola se identificó como fixture demasiado pequeño (un puesto para dos chunks y un hilo): se ajustó el test a dos puestos, sin modificar el coordinador ni relajar el error esperado de saturación.

## Correcciones productivas acotadas

| Archivo | Cambio | Motivo |
| --- | --- | --- |
| workers/python/worker.py | Semáforo de admisión antes de crear hilo; libera cupo en finally; configuración validada de conexiones/tiempo | Evitar handlers sin cota y permitir presupuestos explícitos sin modificar mensajes |
| workers/java/WorkerJava.java | Executor de conexiones máximo acotado y sin cola; semáforo independiente de cálculo; deadline total cabecera+cuerpo; cierre programado de escritura | Evitar cola ilimitada, que una conexión ociosa ocupe aritmética y que fragmentos lentos renueven el plazo |
| workers/csharp/Worker.cs | Reserva cupo antes de Task.Run y lo libera en finally; deadline monotónico cabecera+cuerpo; timeout configurado | Limitar tareas admitidas y cerrar frames incompletos dentro del presupuesto |

Configuración común por entorno: `PC3_WORKER_MAX_CLIENTS` (predeterminado 64; 1..1024) y `PC3_WORKER_TIMEOUT_MS` (predeterminado 15000; 100..300000). El argumento de hilos/cupos de cálculo conserva su significado y CAPS sigue anunciándolo. Las conexiones excedentes se cierran sin leer una solicitud; no se inventa un ID para emitir ERROR. El protocolo compartido y los contratos se conservaron.

Se añadieron `tests/test_worker_limits.py` y `scripts/validate_phase2.py`. El runner conserva versiones, hashes de fuentes/modelo, resultados por caso, omisiones y log. No instala herramientas, rechaza un directorio de salida existente y devuelve fallo si cambian fuentes o artefactos oficiales durante la ejecución.

No se modificaron servidor/coordinador, CNN, pesos, contratos, clientes, BD ni benchmark productivo en esta fase. Los cambios CNN visibles en Git pertenecen a fase 1.

## Regresiones nuevas

Cuatro métodos, con subcasos reales para los tres lenguajes:

1. Dos conexiones admitidas, tercera rechazada; cerrar una libera el cupo y permite otra petición.
2. Header lento y cuerpo lento: con plazo 400 ms los fragmentos no renuevan el deadline; posteriormente PING responde.
3. Con una conexión ociosa, un único cupo de cálculo sigue disponible para JOB DENSE en otra conexión.
4. Cola del coordinador saturada con un worker temporalmente retenido: devuelve coordinator_busy en tiempo acotado, libera pendientes y vuelve a producir resultados correctos.

Tras corregir workers y ajustar el fixture de cola, los cuatro métodos pasaron (11.312 s). La suite integral también los incluye. La aritmética de CONV/DENSE/POST y sus formatos no cambiaron.

## Suite integral: límite de hardware y corrección del test

Primera campaña: **99 casos, 98 OK, 0 assertion failures, 1 error**, sin skips, 109.79 s. El único error fue `test_distributed_profiles_nodes_limits_and_localhost_is_not_three_machines`, al iniciar el segundo escenario de emulación PARALLEL_DISTRIBUTED: requiere tres presupuestos disjuntos de dos núcleos, seis núcleos físicos en total. Este equipo tiene **cuatro núcleos físicos / ocho lógicos**. El error exacto fue `RuntimeError: not_enough_physical_cores`.

El escenario DISTRIBUTED del mismo test ya había terminado con 30/30 solicitudes correctas, tres workers/cupos y una máquina observada. El error no fue fallo de inferencia ni de los workers corregidos.

Se separaron ambos escenarios en `tests/test_benchmark.py` y se añadió comprobación de núcleos físicos disponibles antes de lanzarlos. Así se conserva la prueba DISTRIBUTED y se registra un skip con causa explícita para el escenario de seis núcleos. No se sustituyeron núcleos físicos por hilos lógicos ni se falseó el presupuesto. El runner integral se repitió tras este cambio.

## Cómo reproducir

```bash
# Usar otra carpeta si ya existe; SDK temporal o instalación .NET 8 disponible.
python3 scripts/validate_phase2.py --dotnet-dir /tmp/pc3-dotnet8 --output build/phase2-nueva
```

Con herramientas/headless/PATH configurados también se puede ejecutar directamente:

```bash
python3 -m unittest discover -s tests -p 'test_protocol.py' -v
python3 -m unittest discover -s tests -p 'test_identify.py' -v
python3 -m unittest discover -s tests -p 'test_distributed.py' -v
python3 -m unittest discover -s tests -p 'test_worker_limits.py' -v
```

Ver WORKERS_TCP.md para compilación/arranque manual, configuración, mensajes, trazas y límites. Los procesos y binarios temporales quedan en build/ y /tmp; no se añaden binarios al repositorio.

## Consistencia, sincronización y límites que permanecen

- El modelo de inferencia conserva pesos inmutables en Python y carga/cache protegida en Java; cada ejecución del coordinador tiene UUID+contador y sockets/estado propios.
- Las tareas llevan runId y taskId; cada respuesta se comprueba por ID, forma, cantidad de valores finitos y tiempo reportado. El ensamblado usa offset, no orden de llegada. Barreras entre convolución, capa oculta y salida se verifican con proxies de fallo que redirigen a workers reales.
- Se puede reintentar un chunk en otro endpoint dentro del deadline del coordinador; no se convierte una solicitud DISTRIBUTED en IDENTIFY completo ni se acepta un solo participante como distribución suficiente.
- Límites de conexiones/cómputo no garantizan equidad estricta entre clientes ni cancelan aritmética CPU ya iniciada. El deadline de lectura no engloba todas las etapas de una solicitud; el coordinador mantiene el presupuesto de extremo a extremo.
- Los tres workers hablan TCP directamente: esto es legado de inferencia. No prueba integración RabbitMQ, persistencia, idempotencia durable ni cálculo/agregación de gradientes remotos.
- Muchos hilos Python no garantizan CPU paralela con GIL. Los procesos independientes previstos por node_agent son un mecanismo distinto. Los futuros benchmarks deben registrar núcleos y cupos matemáticos por nodo, además de auxiliares JVM/.NET.
- Un cambio de pesos en disco no actualiza automáticamente el snapshot cacheado del coordinador: la promoción/versionado de modelo se debe coordinar en fases posteriores.
- Pruebas físicas pendientes: latencias/red real, tres nodos/SO independientes y recuperación bajo particiones entre equipos. La emulación local no las sustituye.

## Resultado final y evidencia conservada

Segunda campaña integral, tras separar el test por escenario: **100 casos, 99 aprobados, 1 omitido, 0 fallos y 0 errores**; exit 0; 108.79 s de runner (108.622 s unittest). La omisión es exclusivamente `test_parallel_distributed_profile_with_six_physical_cores`, con razón explícita de seis núcleos físicos requeridos y cuatro disponibles. Ese escenario queda **NO VERIFICADO**, no aprobado.

| Suite | Aprobadas | Omitidas | Fallos/errores |
| --- | --- | --- | --- |
| CNN original | 24 | 0 | 0 |
| Regresiones fase 1 | 7 | 0 | 0 |
| Protocolo y cliente local | 18 | 0 | 0 |
| IDENTIFY / errores / concurrencia | 18 | 0 | 0 |
| Distribución / barreras / failover | 15 | 0 | 0 |
| Workers: límites y deadlines nuevos | 4 | 0 | 0 |
| Desktop headless / TCP | 7 | 0 | 0 |
| Benchmark y comprobación de emulación | 6 | 1 | 0 |
| **Total** | **99** | **1** | **0** |

La campaña final conserva los mismos resultados de consistencia: 300/300 en ambos modos; máximo |p_seq-p_dist|=4.9948933877885793e-13; error intermedio máximo=2.6645352591003757e-15. Las probabilidades Java local secuencial/paralela frente a Python en 300 imágenes difieren como máximo 2.220446049250313e-16. Todos están por debajo de la tolerancia de integración 1e-8.

Archivos de evidencia:

- `docs/ia/evidencias/FASE2_PRUEBAS.json`: resultado final completo por caso, versiones, razón de skip, hashes de fuentes y artefactos oficiales, hash del log y tiempo. Se comprobó que las fuentes no cambiaron durante la ejecución y que todos los archivos bajo model/ conservaron sus hashes.
- `docs/ia/evidencias/FASE2_LINEA_BASE.json`: observaciones de admisión/frames antes de los cambios, hashes anteriores, resultados de distribución originales y diagnóstico de la primera suite integral.
- `build/phase2-final/tests.log` y summary.json: log completo y resultado final; `build/phase2-validation/` conserva la primera campaña con el error de hardware. Artefactos por suite en build/stage0-* incluyen compilación Java/C#, logs por proceso, CSV y trazas. Todos ignorados por Git, sin binarios nuevos versionados.
- `/tmp/pc3-phase2/` conserva logs de línea base y límites antes/después, más el probe temporal original. Su conservación depende de /tmp; la evidencia resumida queda en los JSON versionables indicados.

La evidencia de fase 1 permanece como registro histórico de aquellas fuentes. Su manifiesto identifica las fuentes CNN y el verificador de aquella ejecución: fase 1 validó CNN/entrenamiento, fase 2 produce su propio snapshot de fuentes, que incluye workers. No se retocaron resultados antiguos para ajustarlos a los cambios posteriores.

## Matriz de cierre

| Criterio fase 2 | Estado actual |
| --- | --- |
| Compilación y operaciones reales Java/Python/C# | VERIFICADO en Ubuntu localhost |
| Chunks, offsets y barreras matemáticamente consistentes | VERIFICADO, 300 imágenes y tensores |
| IDs repetidos concurrentes sin mezclar resultados | VERIFICADO, test de 48 solicitudes / 12 clientes; 36 runs DISTRIBUTED distintos |
| Desorden, parciales inválidos, caída/reinicio, timeout | VERIFICADO en pruebas locales con fallos inyectados sobre workers reales |
| Límites de admisión y recuperación de workers | VERIFICADO en tres lenguajes |
| Deadline total de lectura de cabecera+cuerpo | VERIFICADO en tres lenguajes |
| Saturación/recuperación de cola del coordinador | VERIFICADO |
| Sin fallback silencioso de DISTRIBUTED a IDENTIFY completo | VERIFICADO |
| Preservar CNN/pesos/dataset/contratos y fases previas | VERIFICADO; los archivos CNN ya modificados eran cambios previos de fase 1 |
| Emulación paralelo distribuido de seis núcleos físicos | NO VERIFICADO: prueba omitida, hardware insuficiente |
| Despliegue real entre máquinas y SO distintos | PENDIENTE: sólo hay este equipo |
| RabbitMQ / gradientes distribuidos / campaña 1000 | Fuera de fase 2; pendientes de fases 3–5 |

**Fase 2 completada en su validación local de implementación; evidencia física pendiente.** No se acredita aún el requisito PC3 de tres nodos/SO independientes ni el escenario omitido. La fase 1 mantiene pendiente su evaluación externa; el PDF y aclaraciones docentes siguen pendientes. No se inició fase 3, no se hizo commit, push, merge, rebase ni PR.
