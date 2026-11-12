# Fase 0 — Auditoría técnica IA

Fecha: 2026-11-12 (America/Lima). Raíz efectiva: `PC3_Concurrente/` dentro del directorio del workspace. Rama: `feature/ai-distributed`; commit inicial observado: `798fee1 first commit`. `git status --short` inicial vacío. Auditoría sin cambios productivos, instalación, entrenamiento completo, modificación de pesos, contratos, commit, merge, rebase, push ni PR.

## Alcance y fuentes

Leídos README, docs/MATRIZ_PC3.md, ARQUITECTURA_PC3.md, EQUIPO_Y_RAMAS.md, PLAN_INTEGRACION.md, architecture.md y contratos TCP/RabbitMQ. El PDF `P3cc4P1-262_v07 (1).pdf` no apareció en el repositorio, Desktop ni adjuntos revisados: **enunciado original NO VERIFICADO**. Se usa provisionalmente la matriz; sus referencias a páginas no fueron contrastadas con el original.

IMPLEMENTADO significa código operativo con evidencia local explícita; PARCIAL significa cobertura incompleta; PENDIENTE significa funcionalidad ausente; NO VERIFICADO significa evidencia insuficiente o ejecución impedida. Una prueba existente no cuenta como aprobada hasta ejecutarse.

## 1. Entorno

| Elemento | Detección / consecuencia |
| --- | --- |
| SO / arquitectura | Ubuntu 26.04.1 LTS, Linux 7.0.0-43-generic, x86_64 |
| Python | `python3 --version`: 3.14.4; `python --version`: comando inexistente |
| JDK / javac | OpenJDK 21.0.13; javac 21.0.13 |
| C# | `dotnet --info`: comando inexistente; Worker.csproj requiere net8.0; compilación/ejecución NO VERIFICADAS |
| Pruebas | unittest, subprocess y bibliotecas estándar disponibles; sin necesidad de pip para IA/pruebas inspeccionadas |
| Dependencias IA | math, random, zipfile, zlib, threading y demás stdlib; sin framework IA |
| Automatización | scripts .ps1 orientados a PowerShell; no ejecutados en esta auditoría Linux |
| Sockets | sandbox bloquea socket(): PermissionError EPERM; pruebas locales repetidas fuera del sandbox con éxito donde no requieren .NET |
| Gráficos | DISPLAY=:0 no accesible; benchmark requiere `-Djava.awt.headless=true` en este entorno |

Se adaptó `python` a `python3` en Linux por ausencia del alias, sin cambiar scripts ni configuración global. Para benchmarks se pasó además `python=python3`, pues PhysicalConfig invoca `python` por defecto. No se instaló .NET: es necesario para verificar los tres lenguajes y desbloquear la preparación común de cinco clases de integración. RabbitMQ y motores BD no fueron comprobados como servicios: no existe todavía integración funcional en este código.

## 2. Inventario y comportamiento real

| Componente | Qué realiza y qué es correcto | Estado / límite / evidencia |
| --- | --- | --- |
| cnn_python/model.py | Convolución válida, ReLU, max pooling con índices, flatten, MLP, softmax estable; validación de valores finitos, pesos inmutables; backward completo | IMPLEMENTADO local: test_cnn, gradientes de los 837 parámetros con diferencias centrales epsilon=1e-5 y tolerancia absoluta 2e-6, en una muestra/pesos de prueba |
| cnn_python/train.py | Inicialización He, barajado determinista, minibatches, Adam con corrección de sesgo, clipping global a 5, selección por menor loss de validación | IMPLEMENTADO secuencial; entrenamiento pequeño dos veces idéntico y todas las secciones de pesos cambian. Entrenamiento completo heredado NO reproducido aquí |
| cnn_python/evaluate.py | Accuracy, matriz de confusión, recall y predicciones del test | IMPLEMENTADO; coincide con métricas guardadas. No incluye loss en metrics.json: se calculó aparte con train.metrics |
| cnn_python/dataset.py | Generador propio de figuras con ruido, escala, posición y rotación; ZIP determinista, manifest, hashes, splits | IMPLEMENTADO sintético: carga validada y semillas separadas; generalización externa PENDIENTE |
| cnn_python/images.py, predict.py | Decodificación PNG 8-bit no entrelazado y PGM, normalización/redimensión, inferencia por píxeles | IMPLEMENTADO; tests de formatos, errores, independencia del nombre de archivo y directorio |
| workers/python/worker.py | TCP con frames, CAPS, JOB CONV/DENSE/POST, operaciones heredadas CONV/MLP, IDENTIFY completo; carga fría protegida por lock; slots por semáforo | PARCIAL verificado: carga concurrente y TCP IDENTIFY pasan; JOB entre nodos no verificado aquí. Hilos Python no acreditan paralelismo CPU |
| workers/java/WorkerJava.java | TCP, CAPS, JOB y operaciones heredadas; pool de hilos | Compilación IMPLEMENTADA; operación remota y fallos NO VERIFICADOS por bloqueo común .NET |
| workers/csharp/Worker.cs | Implementación fuente TCP y JOB, tareas por conexión y SemaphoreSlim | NO VERIFICADO: falta SDK; no equivale a worker operativo |
| server-java/DistributedCnn.java | Descubre capacidades, reparte dos convoluciones y filas densas en chunks, barreras por capa y ensamblado por offsets; POST remoto opcional | PARCIAL: compila; fuente protege cada Run con ID interno UUID+contador, valida PART/IDs/dimensiones, cancela sockets, limita cola, aplica deadlines y reintenta nodos. Integración multiworker NO VERIFICADA |
| server-java/CentralServer.java | Clientes TCP concurrentes con pool acotado, delegación secuencial y coordinador distribuido | IMPLEMENTADO camino secuencial Java→Python por smoke; modo distribuido no ejecutado |
| benchmarks/LocalCnn.java | Inferencia Java secuencial o capas en pool local; CPU por hilo y contadores | IMPLEMENTADO local: BenchmarkChecks compara 300 imágenes, prueba entradas inválidas y consistencia entre 1/2 hilos |
| tests/ | Matemática/imagen/dataset; transporte, fallos, aislamiento, tensor por capa, GUI y benchmark | CNN ejecutada; suites extensas previstas, cinco clases no arrancan por dotnet. test_local.py y smoke_test.py incluyen utilidades/scripts que unittest no convierte automáticamente en casos |
| model/data, weights, training, evaluation | Dataset, pesos, historia, métricas, predicciones, informe de reproducibilidad | Dataset/pesos/evaluación comprobados; hashes de fuentes del entrenamiento desactualizados |
| messaging/, clients/android, clients/web, web-server, databases/ | Contratos/README y esquemas SQL iniciales | PENDIENTE integración; fuera de implementación de esta fase |

## 3. Resultados reproducibles de pruebas

Todos los comandos se ejecutaron desde la raíz efectiva. Los tiempos son pared y aproximados. Exit distinto de cero nunca se considera aprobación global.

| Comando | Resultado real | Tiempo / evidencia / límite |
| --- | --- | --- |
| `python3 scripts/check_main.py` | exit 0; estructura, JSON, inferencia y compilación Java correctos | 2.26 s; informa explícitamente C# NO VERIFICADO; no es una suite de N unit tests |
| `python3 -m unittest discover -s tests -p "test_cnn.py" -v` (sandbox) | 24 casos: 23 OK, 1 error EPERM al crear socket | 1.85 s; fallo de restricción del entorno |
| mismo comando fuera del sandbox | **24/24 OK**, 0 fallos/errores | unittest 2.125 s; incluye gradientes, entrenamiento pequeño y worker TCP |
| `python3 -m cnn_python.predict model/examples/circulo-0.png` | exit 0; clase circulo | 0.07 s proceso; p=(0.9999982471200074, 9.965471289921848e-09, 1.7429145213097573e-06) |
| `python3 scripts/smoke_main.py` (sandbox) | exit 1; EPERM socket | 2.09 s; integración NO VERIFICADA en ese intento |
| mismo smoke fuera del sandbox | **exit 0**; Java CLI→TCP→CentralServer→Python→circulo | 3.37 s; no cubre RabbitMQ/BD ni distribución física |
| `python3 -m unittest discover -s tests -p "test_*.py" -v` (sandbox) | exit 1; 26 casos ejecutados, 25 OK, 1 error de socket; además 5 errores setUpClass | 11.22 s; total 6 errores reportados |
| misma suite fuera del sandbox | **exit 1**; 26 casos ejecutados y OK, además **5 errores setUpClass**, 0 assertion failures | 12.40 s proceso / 12.052 s unittest; NO es suite aprobada |
| `javac --release 8 -encoding UTF-8 -d /tmp/pc3-fase0/java <todos los .java de server-java, workers/java, clients-java, frontend-java, benchmarks, tests>` | exit 0 | 3.15 s; sólo warnings por target/source Java 8 obsoleto; WorkerJava compila |
| `dotnet build workers/csharp/Worker.csproj` | NO VERIFICADO; no ejecutable dotnet | Invocación equivalente intentada por setUpClass: FileNotFoundError |
| `java -cp /tmp/pc3-fase0/java BenchmarkChecks model/weights/weights.txt` con 300 vectores test por stdin | exit 0, 300 salidas; secuencial/paralelo equivalentes a tolerancia 1e-12 | 0.48 s; diferencia máxima frente a Python 2.220446049250313e-16; peak paralelo=2 |

Las clases bloqueadas son BenchmarkTests, DistributedTests, FrontendTests, IdentifyTests y ProtocolTests: todas heredan una preparación que compila C# incondicionalmente antes de levantar workers. Sus métodos **NO VERIFICADOS**, no contados como aprobados. LocalClientTests aporta otros dos casos aprobados a los 24 de CNN.

Logs originales de esta sesión: `/tmp/pc3-fase0/test-0.log` a `test-4.log`, `results.json`, `smoke-unrestricted.log` y `full-unrestricted.log`. Son temporales locales, no artefactos versionados ni garantía de conservación futura. Las tablas y cifras de este documento conservan el resultado de la auditoría. Las suites generan clases/logs ignorados bajo build/stage0-*; no se incorporan al repositorio versionado ni se borran archivos existentes.

## 4. Modelo y dataset

Arquitectura: entrada gris normalizada 16×16×1 → dos filtros 3×3 sin bias convolucional, stride 1 sin padding → 2×14×14 → ReLU → max pooling 2×2 stride 2 → 2×7×7 → flatten 98 → Dense 8 + ReLU → Dense 3 → Softmax. Clases: circulo, cruz, triangulo. Parámetros: 9+9+98×8+8+8×3+3 = **837**.

Backward: derivada cross-entropy/softmax `p-y`, propagación por W2, ReLU oculta, W1, ganadores del pooling y ambos filtros; ReLU'(0)=0 y primer ganador en empates. Adam actualiza todos los parámetros con gradiente promedio del batch. El test numérico es evidencia fuerte local, no prueba universal en puntos no diferenciables.

Dataset propio geometry-v1: 720 train (240/clase), 180 validation (60/clase), 300 test (100/clase), total 1200. Semillas 1729/2718/31415. Entrenamiento seed 20261022, barajado seed+1. Lectura verifica dimensiones y hashes de píxeles; manifest rechaza duplicados entre conjuntos. PNG de ejemplo provienen de test: NO constituyen evaluación externa adicional. Todos los splits usan la misma familia de generador; persiste sesgo de dominio y posible sobreajuste a la familia sintética, aunque no se detectaron duplicados exactos. No se auditó historial humano de selección del dataset/hiperparámetros; no puede descartarse contaminación por selección repetida del test.

Métricas recalculadas en memoria, sin escribir pesos/informes:

| Split | Accuracy | Cross-entropy media |
| --- | --- | --- |
| train 720 | 1.0 | 0.00010898939628824335 |
| validation 180 | 1.0 | 0.00010946370327824282 |
| test 300 | 1.0 | 0.00023039366759792124 |

Matriz test (filas reales, columnas predichas; orden circulo/cruz/triangulo): `[[100,0,0],[0,100,0],[0,0,100]]`. Coincide con model/evaluation/metrics.json; train/validation coinciden con training.json. El umbral .85 es del código, no un requisito oficial confirmado.

SHA256 dataset: `b9130514dca3a0b0bb3ae34cf23a59d1c5f455576ad41fce73118b6112143d81`.
SHA256 pesos: `df582438e8fa66b5f606408d646b8df3025f3e9b033dd780b17e45df0c550ec4`.
Ambos coinciden con métricas e informe heredados. **Los tres hashes source_sha256 de model.py, dataset.py y train.py en training.json NO coinciden con las fuentes actuales.** No se conoce la causa (posibles cambios de contenido o finales de línea); se necesita comparar y registrar procedencia exacta, sin editar hashes para aparentar reproducción.

training.json declara 60 épocas, best_epoch=60, batch=24, lr=.003, patience=12, validación inicial accuracy=.3166667/loss=1.0919184. reproducibility.json declara dos entrenamientos completos idénticos en Windows/Python 3.12.11: evidencia heredada, **NO reproducida en Ubuntu/Python 3.14**. No se ejecutó train.main porque por defecto sobrescribe los pesos oficiales; sólo el test pequeño usa temporales.

## 5. Distribución y concurrencia

- Secuencial: Python CNN/train/evaluate; IDENTIFY completo del worker; LocalCnn con un hilo. Smoke confirma el camino TCP secuencial.
- Paralelismo local: LocalCnn divide capas en pool Java; verificado con BenchmarkChecks y afinidad en benchmark breve. Workers Java/C# atienden tareas con slots; C# no ejecutado. node_agent usa procesos Python independientes para CPU paralela, evitando atribuir al GIL el trabajo de múltiples núcleos.
- Distribución de inferencia: DistributedCnn envía JOB con ID interno y taskId a endpoints; recoge PART y monta capas por offsets. Tiene barreras, reintento, cancelación y límites. Código existente, ejecución multiworker pendiente por entorno de prueba; endpoints diferentes no prueban máquinas diferentes.
- Entrenamiento concurrente/paralelo/distribuido: **PENDIENTE**. train.py sólo acumula gradientes en bucles locales; no hay protocolo de gradientes, sincronización de versiones ni agregación remota.
- Evaluación distribuida: tests prevén comparar 300 imágenes y tensores; no se ejecutaron. Falta pipeline de evaluación y evidencia física reproducible.
- Estado compartido: CNN Python inmutable y carga fría con lock; Java modelo cacheado volatile/synchronized; estado Run independiente por petición reduce mezcla aun con IDs externos repetidos. Son protecciones inspeccionadas; pruebas multiworker de IDs repetidos/fallos aún no verificadas.
- Riesgos: Python crea un hilo por conexión sin límite global; C# lanza Task.Run por conexión; Java usa pool fijo con cola no acotada. Semáforos limitan cómputo pero no toda admisión/espera. C# y Java emplean timeouts de lectura por socket; revisar deadline absoluto ante fragmentos lentos. No hay idempotencia durable extremo a extremo ni persistencia de solicitudes ante reinicios.

## 6. Benchmarks: inventario y comprobaciones

| Archivos | Cobertura real / límite |
| --- | --- |
| Benchmark.java, CnnBenchmark.java | Entrada y harness IDENTIFY, carga semilla fija, retardos aleatorios, warmup, clientes, CSV, latencia/p95/throughput/errores y hashes; comparación numérica contra referencia local |
| LocalCnn.java | Inferencia secuencial/paralela local y CPU de cómputo por hilo; no mide memoria del sistema completo |
| PhysicalConfig.java | Comprueba afinidad/topología, agentes/capacidades/configuración, hashes de pesos y presupuestos antes/después; physical_cluster_verified=false, identidad declarada no certifica despliegue físico |
| configs/*.properties | Cuatro perfiles presentes; default 300 solicitudes y un cliente, IP LAN de ejemplo; no equivalen a experimentos ejecutados |
| node_agent.py, resource_probe.py | Agentes TCP de control, procesos/afinidad/topología, vigilancia de recursos asignados; no son entrenamiento distribuido ni telemetría RabbitMQ |
| Build.ps1, Start-Node.ps1, Run-Experiments.ps1 | Compilan/preparan/inician nodos y repiten cargas; requieren herramientas y nodos configurados. Valores por defecto no cumplen prueba integral de 1000 transacciones/3 aplicaciones |
| prepare_inputs.py | Extrae test y comprueba hashes; no entrena |
| GraficasBenchmark.py | Gráficas SVG de mediciones CSV; rechaza evidencia inválida/localhost salvo opción explícita; ruta histórica CONV no sustituye comparación CNN completa |

Se inspeccionaron todos los archivos versionados de benchmarks. No hay CSV de mediciones físicas versionados en esa carpeta. No se ejecutaron scripts .ps1 ni escenarios remotos. Falta telemetría CPU/memoria integral, tasas/longitud/ack de colas y gráficas RabbitMQ.

Comprobación breve adicional (no benchmark final):

```bash
# PROFILE = local-sequential y luego local-parallel
java -Djava.awt.headless=true -cp /tmp/pc3-fase0/java benchmarks.Benchmark \
  --config benchmarks/configs/PROFILE.properties python=python3 images=model/examples \
  requests=30 warmup=5 delay.min.ms=0 delay.max.ms=0 \
  output=/tmp/pc3-fase0/PROFILE.csv
```

| Perfil | Resultado | Media / p95 ms | Throughput req/s | Tiempo proceso |
| --- | --- | --- | --- | --- |
| local-sequential | 30/30, 0 errores, local_affinity_verified | .1920505 / .532571 | 5159.1982 | .66 s |
| local-parallel | 30/30, 0 errores, local_affinity_verified | .5330428 / .986951 | 1866.4532 | .56 s |

Sin headless ambos intentos salieron con código 2 por X11 (.18/.23 s). Se resolvió sólo con argumento JVM. La muestra breve de nueve ejemplos, cero delay y cinco warmups confirma funcionamiento, **no demuestra mejora de rendimiento ni cumplimiento de carga PC3**. No se produjeron gráficas ni datos ficticios. Las cuatro configuraciones están implementadas como harness de inferencia; sólo dos se comprobaron localmente. Entrenamiento distribuido no está cubierto por estos perfiles.

## 7. Matriz provisional de responsabilidad IA

| Requisito | Estado | Evidencia disponible / faltante |
| --- | --- | --- |
| CNN + MLP desde cero, forward/backward | IMPLEMENTADO | 24 tests CNN; ampliar dominios/casos límite en fase 1 |
| Entrenamiento y actualización real | IMPLEMENTADO secuencial | Test pequeño + informes heredados; falta reproducir entrenamiento completo con fuentes identificadas |
| Dataset, splits, semillas, procedencia | PARCIAL | Generador y hashes; falta validar aceptabilidad docente y test externo |
| Accuracy/loss/confusión | IMPLEMENTADO sintético | Recalculados; guardar loss test en futura evaluación, evaluación externa pendiente |
| Consistencia numérica entre implementaciones | PARCIAL | Java local/Python 300 casos <=2.22e-16; falta red/worker Java/C# |
| Workers tres lenguajes | PARCIAL | Python TCP probado, Java compila, C# NO VERIFICADO |
| Microchunks e inferencia distribuida | PARCIAL | Coordinador implementado; falta suite multiworker y despliegue real |
| Entrenar/evaluar concurrente/paralelo/distribuido | PENDIENTE | No hay agregación de gradientes ni evidencia multimaquina |
| RabbitMQ, idSolicitud, control, reintentos/idempotencia | PENDIENTE | Contrato propuesto; ids TCP heredados no acreditan AMQP |
| 3 nodos / SO / lenguajes independientes | NO VERIFICADO | Sólo entorno local; requiere inventario remoto y aprobación interpretación SO |
| Cuatro escenarios de rendimiento | PARCIAL | Harness y dos comprobaciones locales; faltan campañas físicas comparables |
| 1000 transacciones/3 clientes/delays | PENDIENTE | Harness parametrizable; falta integración apps/broker/BD y campaña |
| CPU/memoria/error/colas y gráficas | PARCIAL | CPU local, latencia/error; faltan memoria y telemetría RabbitMQ integral |
| Documentación y entrega | PARCIAL | Auditoría/plan; faltan evidencias remotas, informe/PPT PDF y ZIP validado |

## 8. Riesgos, dependencias y decisiones pendientes

Prioridad P0: obtener SDK .NET 8 y correr suites antes de declarar workers integrados; recuperar PDF oficial; aclarar exactamente dos BD frente a BD3, uno frente a dos modelos y criterio de SO con el profesor. No ampliar alcance a tres BD/dos modelos sin decisión.

Prioridad P1: integrar RabbitMQ con contratos acordados; desarrollar entrenamiento distribuido real; demostrar tres nodos independientes; reconstruir trazabilidad del entrenamiento y evaluación externa. Mantener inferencia heredada compatible. El archivo docs/architecture.md está desactualizado (Swing aparece pendiente) frente a documentación PC3; se recomienda consolidarlo en fase de integración, sin tocarlo aquí.

Integrante 1: consumidor/publicador backend, versión final contrato, rutas/colas, correlación idSolicitud, timeout, ack/retry/DLQ, persistencia PostgreSQL y trazas. Integrante 2 requiere acceso autorizado a broker y nodos, versiones de modelo y límites acordados.

Integrante 3: clientes reales Android/Web/Desktop, formato de imagen/preprocesamiento uniforme, MariaDB/validación y generación de carga coordinada. Acuerdo de 1000 globales o por cliente debe contrastarse con PDF/profesor; PLAN_INTEGRACION propone por cliente sin que aquí se haya validado oficialmente.

Evidencia disponible: pruebas matemáticas, métricas recalculadas, hashes dataset/pesos, compilación Java, smoke TCP y consistencia Java/Python. Faltan ejecución C#, trazas multiworker aprobadas, inventario físico/SO, AMQP/BD, caída/reinicio integral, entrenamiento remoto, mediciones completas y PDFs finales.

## 9. Cierre

**Fase 0 COMPLETA como auditoría**, con verificaciones pendientes explícitas por SDK/PDF/nodos ausentes. Esto no significa módulo IA PC3 terminado ni suite integral aprobada. Se completaron inspección, intentos requeridos, diagnóstico, clasificación de brechas y plan de fases 1–6. No se comenzó fase 1.
