# Fase II — Resultados de confirmación y rendimiento preliminar

Fecha: 2026-11-12 (America/Lima). Rama feature/ai-distributed, base 798fee1. Estado: **IMPLEMENTACIÓN LISTA / DESPLIEGUE DISTRIBUIDO PENDIENTE**. Se conserva el código y la evidencia de fases anteriores; no se comienza RabbitMQ ni entrenamiento distribuido.

## 1. Cambios de esta confirmación

- tests/test_worker_limits.py: nueva prueba de JOB DENSE válido de aproximadamente 1.8 MB, con 100000 entradas/pesos, resultado conocido cero, IDs/forma correctos y tiempo no negativo, para los tres workers.
- FASE2_CONCURRENCIA_DISTRIBUCION.md: documento técnico exigido, arquitectura y secuencia Mermaid, política de reparto, sincronización, errores, preparación futura AMQP y límites.
- Este documento y evidencias JSON: campaña nueva y mediciones reales. Se actualizan referencias del plan/documento anterior.

No se modifica código productivo en esta confirmación: el coordinador y las correcciones previas de admisión/deadlines ya cumplen las comprobaciones locales. Tampoco se sustituyen los resultados de fases anteriores por los nuevos.

## 2. Pruebas automatizadas

| Comando / comprobación | Resultado real |
| --- | --- |
| `git status --short`; `git branch --show-current`; `git log -3 --oneline` | Rama feature/ai-distributed; base 798fee1; cambios anteriores conservados, sin commits nuevos |
| `python3 scripts/validate_phase2.py --dotnet-dir /tmp/pc3-dotnet8 --output build/phase2-confirmation` | exit 0; **103 casos: 102 aprobados, 1 omitido, 0 fallos/errores**; 131.00 s runner / 130.786 s unittest |
| `python3 benchmarks/prepare_inputs.py --output build/phase2-preliminary/images` | 300 imágenes test extraídas con hashes comprobados |
| `javac --release 8 -encoding UTF-8 -d build/phase2-preliminary/classes clients-java/*.java server-java/*.java workers/java/*.java benchmarks/*.java tests/BenchmarkChecks.java` | exit 0; tres advertencias de source/target Java 8 obsoleto |
| Campaña Benchmark/CnnBenchmark, 12 ejecuciones de 1000 solicitudes | 12000/12000 filas OK, 0 errores; comandos/configuración exactos en FASE2_RENDIMIENTO_PRELIMINAR.json |
| Validación posterior CSV | 1000 filas e IDs distintos por ejecución; hash CSV correcto; misma huella de carga para concurrente/paralelo en cada repetición |
| Integridad | Todas las fuentes y todos los artefactos oficiales model/ conservados durante la suite; pesos oficiales también idénticos después del benchmark |
| `git diff --check` | Sin errores de espacios |

La campaña usa sockets localhost y SDK temporal .NET 8.0.428/runtime 8.0.34; Python 3.14.4 y OpenJDK/javac 21.0.13. El runner prepara headless/PATH/caches sólo para sus hijos. No instala dependencias ni modifica configuraciones globales.

| Suite | Aprobadas | Omitidas |
| --- | --- | --- |
| CNN original | 24 | 0 |
| Fase I ampliada | 9 | 0 |
| Protocolo/cliente local | 18 | 0 |
| IDENTIFY/concurrencia/errores | 18 | 0 |
| Coordinador/chunks/fallos | 15 | 0 |
| Límites/deadlines/frame grande | 5 | 0 |
| Desktop headless/TCP | 7 | 0 |
| Benchmark existente | 6 | 1 |
| **Total** | **102** | **1** |

La prueba omitida es test_parallel_distributed_profile_with_six_physical_cores: necesita seis núcleos físicos disjuntos, este equipo tiene cuatro. No es un test aprobado ni una regresión nueva. Los 33 tests CNN pasan; también se conservan interfaces TCP y compatibilidad Desktop. Los casos de cancelación, saturación, IDs repetidos, respuestas fuera de orden, corrupción, frame parcial/grande, caída/reinicio y timeout se ejecutaron realmente.

## 3. Equivalencia matemática

La campaña usa pesos oficiales congelados. Los tests de 300 imágenes comparan etiqueta **y cada probabilidad** con la referencia Python, además de tensores intermedios y barreras con respuestas reordenadas.

| Comparación | Resultado |
| --- | --- |
| SEQUENTIAL vs DISTRIBUTED entre procesos localhost | 300/300 correctos por modo; máximo error absoluto de probabilidades 4.9948933877885793e-13 |
| Tensores intermedios del coordinador vs Python | Máximo error absoluto 2.6645352591003757e-15 |
| Java local secuencial/paralelo vs Python | 300/300; máximo error 2.220446049250313e-16 |
| Solicitudes simultáneas con ID externo repetido | 48 solicitudes / 12 clientes; 36 runs DISTRIBUTED independientes, ocho chunks cada uno, sin mezcla |
| Tres lenguajes | Operaciones y validación JOB/CONV/DENSE/POST reales, tolerancia TCP 1e-8; consistencia local Java/Python 1e-12 |

No se llama distribución física a la comparación entre procesos localhost. El harness valida cada respuesta de rendimiento contra LocalCnn con tolerancia 1e-8; esa referencia ya fue contrastada con Python. Los ceros de error del benchmark significan respuesta numéricamente válida frente a referencia, no un test independiente nuevo de accuracy del dataset.

## 4. Diseño de las mediciones nuevas

Hardware: Intel Core i5-1035G1 @ 1.00 GHz (nombre reportado, no frecuencia efectiva medida), cuatro núcleos físicos/ocho lógicos, Ubuntu x86_64. Se verificó afinidad local por proceso; no se declara haber aislado el resto del SO/aplicaciones. La suite integral terminó antes de iniciar mediciones.

Datos: 300 imágenes test 16×16, normalizadas y precargadas. Por configuración se realizaron tres repeticiones de 1000 solicitudes (no 1000 imágenes únicas), warmup=100, seed=42, retardos uniformes enteros 1..3 ms, timeout=15000 ms. Mismos pesos, muestras y delays en concurrente/paralelo: load.sha256 idéntico por repetición. Se conservaron los hashes y las configuraciones exactas.

| Nombre | Ruta | Emisores | Procesos de aplicación / cálculo | Hilos matemáticos / núcleos |
| --- | --- | --- | --- | --- |
| sequential | LocalCnn Java | 1 | 1 JVM / 1 cálculo | 1 / 1 físico, afinidad verificada |
| concurrent | LocalCnn serial con cola de cálculo | 8 | 1 JVM / 1 cálculo | 1 / 1 físico, afinidad verificada |
| parallel | LocalCnn con pool de capas | 8 | 1 JVM / 1 cálculo | 2 / 2 físicos, afinidad verificada |
| tcp-concurrent | Benchmark JVM→CentralServer JVM→worker Python | 8 | 3 procesos; sólo Python calcula la CNN | 1 cupo Python; afinidad no fijada ni núcleos observados durante esta ruta |

Los hilos de emisión/JVM/GC/JIT son adicionales: por ejemplo, la primera repetición registra jvm.total.threads.after=8/17/18/15 respectivamente en el JVM de benchmark. No se atribuyen esos valores a todos los procesos del pipeline. En las tres repeticiones, sequential/concurrent tienen peak matemático=1; parallel=2 y dos IDs de hilos distintos. Las máscaras locales son 0x1 y 0x3. Esto demuestra ejecución matemática local concurrente en dos hilos con presupuesto de dos núcleos, sin implicar que todos los ciclos de ambos núcleos se ocupen continuamente.

GNU time es un proceso observador adicional y los probes de afinidad se ejecutan antes/después de la medición. Los conteos de procesos de la tabla describen aplicaciones/cálculo; no excluyen la existencia del observador ni auxiliares del runtime.

## 5. Resultados preliminares reales

Cifras = media de las métricas de tres repeticiones. Cada fila agrega 3000 respuestas correctas / 0 fallidas. El p95 mostrado es **media de los tres p95**, no percentil combinado de las 3000 filas.

| Configuración | Latencia media ms | Media p95 ms | Throughput req/s | Duración carga s |
| --- | --- | --- | --- | --- |
| Secuencial local, 1 emisor | .056325 | .091326 | 461.55 | 2.166620 |
| Concurrente local, 8 emisores/1 cálculo | .117361 | .273813 | 3448.54 | .290008 |
| Paralelo local, 8 emisores/2 cálculos | .231709 | .536281 | 3297.62 | .303259 |
| TCP concurrente, 8 emisores/worker Python | 12.252654 | 19.444050 | 550.53 | 1.822741 |

Throughput mínimo–máximo por repetición: secuencial 461.37–461.77; concurrente 3402.87–3488.85; paralelo 3279.56–3323.42; TCP 518.26–595.58 req/s. Son tres repeticiones descriptivas, sin inferencia estadística de mejora garantizada.

| Recursos | Secuencial | Concurrente | Paralelo | TCP concurrente |
| --- | --- | --- | --- | --- |
| CPU pura de cálculo, media ms por 1000 solicitudes | 31.6915 | 18.4796 | 35.0780 | No medida remotamente |
| Máximo RSS GNU time, máximo entre repeticiones, KiB | 137812 | 148156 | 118724 | 159176 (sólo lanzamiento de benchmark) |

CPU pura es suma de tiempo CPU de hilos aritméticos Java excluyendo warmup/colas/red; su resolución y JIT influyen, no es porcentaje de CPU global. RSS es el valor máximo reportado por GNU time para el lanzamiento completo (incluye preparación/warmup), **no memoria media ni suma del pipeline**. En TCP excluye backend y Python, iniciados separadamente. No hay aquí medición de memoria/CPU de todo el sistema distribuido.

Interpretación: ocho emisores solapan los delays de 1..3 ms y elevan throughput incluso con un solo hilo matemático; eso no demuestra aceleración aritmética. Con esta CNN pequeña, parallel resultó más lento que concurrent en las tres mediciones: no se demuestra speedup por paralelizar. El coste de coordinación puede superar el trabajo útil. La ruta TCP incluye runtimes y transporte distintos; no se interpreta su diferencia como penalización pura de distribución entre máquinas.

No se ejecutó inferencia en nodos físicos independientes. Los casos localhost de coordinador prueban consistencia y fallos, no rendimiento de una red remota. Estas 12000 solicitudes tampoco sustituyen la prueba final Android/Desktop/Web→RabbitMQ→IA/BD de 1000 transacciones.

## 6. Comandos y reproducción

El código productivo de benchmark se reutilizó sin cambios. Ejemplo de **comandos de las mediciones**, expresados con rutas relativas equivalentes a las absolutas registradas:

```bash
/usr/bin/time -v -o build/phase2-preliminary/sequential-r1.time.txt \
  java -Djava.awt.headless=true -cp build/phase2-preliminary/classes \
  benchmarks.Benchmark --config build/phase2-preliminary/sequential-r1.properties
/usr/bin/time -v -o build/phase2-preliminary/concurrent-r1.time.txt \
  java -Djava.awt.headless=true -cp build/phase2-preliminary/classes \
  benchmarks.Benchmark --config build/phase2-preliminary/concurrent-r1.properties
/usr/bin/time -v -o build/phase2-preliminary/parallel-r1.time.txt \
  java -Djava.awt.headless=true -cp build/phase2-preliminary/classes \
  benchmarks.Benchmark --config build/phase2-preliminary/parallel-r1.properties
```

Se repitieron con r2/r3. Cada properties fue escrito con la configuración indicada arriba, escenario LOCAL_SEQUENTIAL o LOCAL_PARALLEL, python=python3 y rutas explícitas de pesos/imágenes/salida. Parallel usa como baseline concurrent del mismo número de repetición, no el caso de un solo emisor (tienen huellas de carga distintas).

Para la ruta TCP se iniciaron procesos propios con puertos libres dinámicos:

```text
python3 workers/python/worker.py <worker_port> 1
java -Djava.awt.headless=true -cp build/phase2-preliminary/classes CentralServer <server_port> 127.0.0.1:<worker_port>
/usr/bin/time -v -o <tcp-time.txt> java -Djava.awt.headless=true -cp build/phase2-preliminary/classes benchmarks.Benchmark --config <tcp-properties>
```

Los tcp-properties usan escenario SOCKET_CONTROL, host=127.0.0.1, puerto del servidor y los mismos 1000 requests/8 emisores/seed42/warmup100/delays1..3. SOCKET_CONTROL envía IDENTIFY SEQUENTIAL; no se hace pasar por DISTRIBUTED. Ambos procesos se detuvieron y se esperó su salida al acabar.

Los **12 comandos exactos, puertos, properties completos, resúmenes, load/hash/CSV, tiempos y recursos** están conservados en `evidencias/FASE2_RENDIMIENTO_PRELIMINAR.json`. Para repetir sin sobrescribir, escribir sus diccionarios configuration en una carpeta nueva, actualizar sus rutas output/images/baseline y usar puertos libres. Las fuentes y pasos ya documentados permiten reconstruir las salidas; no es necesario crear otro harness.

## 7. Evidencia y aceptación

- evidencias/FASE2_CONFIRMACION_PRUEBAS.json: 103 casos y resultado por test, hashes de fuentes/modelo, versiones y log. La omisión aparece con su causa; las fuentes no cambiaron durante la campaña.
- evidencias/FASE2_RENDIMIENTO_PRELIMINAR.json: datos de las 12 mediciones, configuraciones, CPU/memoria de alcance explícito y agregados.
- build/phase2-confirmation/: log y resumen de pruebas; build/stage0-* conserva compilación/trazas por proceso.
- build/phase2-preliminary/: 12 CSV crudos, summaries, properties, informes GNU time, logs, imágenes extraídas y clases compiladas. Ignorados por Git; no se añaden binarios al repositorio.
- FASE2_DISTRIBUCION.md / FASE2_PRUEBAS.json: campañas previas (99 pruebas aprobadas/1 omitida antes de ampliaciones), identificadas como históricas.

| Criterio del adjunto | Estado |
| --- | --- |
| Secuencial determinista / CNN fase I | VERIFICADO |
| Múltiples solicitudes y correlación sin mezcla | VERIFICADO localhost |
| Paralelismo local real con recursos explícitos | VERIFICADO, 2 hilos activos y afinidad de 2 núcleos; sin mejora demostrada |
| Tres workers y TCP nativo/framing/límites | VERIFICADO, incluido frame válido grande |
| Chunks, barreras, recuperación y equivalencia | VERIFICADO entre procesos locales |
| Automatización y Desktop sin regresiones | VERIFICADO: 102 aprobadas, 1 omitida previa |
| Documentación y diagramas exigidos | COMPLETOS |
| Despliegue distribuido en tres máquinas/SO | PENDIENTE: equipos no disponibles |
| Escenario de seis núcleos disjuntos | NO VERIFICADO: hardware insuficiente |
| PDF oficial y decisiones del profesor | PENDIENTES |

**IMPLEMENTACIÓN LISTA / DESPLIEGUE DISTRIBUIDO PENDIENTE**. No se marca una prueba remota como completa por ejecutar procesos localhost. No se implementa fase III. La fase I mantiene pendiente evaluar imágenes externas documentadas.

## 8. Git y commit propuesto

Sin commit, push, merge ni rebase. Rama feature/ai-distributed. La confirmación agrega un test y documentación/evidencia; los cambios productivos de workers y tests anteriores ya estaban presentes y se conservaron.

Para revisar y guardar una unidad coherente de fase II (sin incluir automáticamente las modificaciones CNN de fase I):

```bash
git diff -- workers tests/test_benchmark.py
git add workers/python/worker.py workers/java/WorkerJava.java workers/csharp/Worker.cs \
  tests/test_worker_limits.py tests/test_benchmark.py scripts/validate_phase2.py \
  docs/ia/FASE2*.md docs/ia/WORKERS_TCP.md docs/ia/evidencias/FASE2*.json
git diff --cached
git commit -m "feat: validar concurrencia y microchunks IA con evidencia local"
```

Revisar primero el índice si ya hay otros cambios preparados. El plan compartido y la documentación de fases I/0 pueden guardarse por separado; no se añade todo el árbol sin revisar. Los comandos son sugerencias, no ejecutados por el asistente.
