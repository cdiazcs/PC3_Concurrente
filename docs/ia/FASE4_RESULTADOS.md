# Fase IV — Resultados verificables

Fecha: 2026-11-12. Rama: feature/ai-distributed; base 798fee1. **IMPLEMENTACIÓN DISPONIBLE — VALIDACIÓN DISTRIBUIDA PENDIENTE**.

## Entorno y alcance

Linux x86_64, Ubuntu 26.04, Intel Core i5-1035G1: 4 núcleos físicos, 8 procesadores lógicos. Python 3.14.4, Java 21, .NET SDK 8.0.428 temporal, RabbitMQ 4.4.0 aislado y Pika 1.3.2. Todos los procesos y broker estuvieron en este equipo. No se asignaron núcleos físicos exclusivos; cantidad de procesos no demuestra afinidad. Windows y nodos remotos pendientes. Java/C# siguen participando en inferencia, no implementan backward de entrenamiento.

Sólo dataset sintético propio: 720 train, 180 validation y 300 test. Sin imágenes externas; estas métricas no prueban generalización a fotografías reales. Los pesos oficiales no se sustituyeron. SHA256 de pesos originales: df582438e8fa66b5f606408d646b8df3025f3e9b033dd780b17e45df0c550ec4. Dataset ZIP: b9130514dca3a0b0bb3ae34cf23a59d1c5f455576ad41fce73118b6112143d81.

## Configuración y reproducción

Cuatro ejecuciones, una por configuración, con 3 épocas, batch global 24, seed 20261022, learning rate 0.003 y 90 actualizaciones. Mismos pesos iniciales, barajado y splits. Mejor época seleccionada por validation: 3; test evaluado al finalizar.

```bash
python3 -m cnn_python.train_synchronous --mode sequential --epochs 3 --batch-size 24 --seed 20261022 --output build/repro-sequential
python3 -m cnn_python.train_synchronous --mode parallel --processes 2 --epochs 3 --batch-size 24 --seed 20261022 --output build/repro-parallel
# Iniciar dos training_worker.py con las variables privadas del broker y dataset común.
python3 -m cnn_python.train_synchronous --mode amqp --processes 2 --epochs 3 --batch-size 24 --seed 20261022 --output build/repro-amqp
# Repetir con IA_TRAIN_LOCAL_PROCESSES=2 en cada uno de los dos workers.
python3 -m cnn_python.train_synchronous --mode amqp --processes 2 --epochs 3 --batch-size 24 --seed 20261022 --output build/repro-amqp-pools
```

La guía de configuración y los diagramas de arquitectura/secuencia están en [FASE4_ENTRENAMIENTO_DISTRIBUIDO.md](FASE4_ENTRENAMIENTO_DISTRIBUIDO.md). Los comandos exactos de las mediciones, configuración, historial, versiones, procesos y hashes de artefactos están en [FASE4_EXPERIMENTOS.json](evidencias/FASE4_EXPERIMENTOS.json). Los informes originales locales están en build/phase4-experiments/; build es una salida temporal excluida de Git.

## Comparación numérica

Prueba fundamental: minibatch de 7 ejemplos, particiones desiguales 3/2/2, respuestas invertidas; ponderación n_i/N. Diferencia máxima de gradientes: **2.7755575615628914e-17**; diferencia de loss: **0**; diferencia máxima tras un único Adam: **2.7755575615628914e-17**, tolerancia 1e-12. Snapshot original intacto. Evidencia: [FASE4_MATEMATICA.json](evidencias/FASE4_MATEMATICA.json). Se conserva el backward ya contrastado mediante diferencias finitas en fase I.

La extracción de compute_gradients/Adam preservó exactamente los pesos del entrenador anterior en la referencia de 24 ejemplos, 3 épocas, batch 5 y seed 23: diferencia máxima 0.0. El cálculo paralelo cambia el orden de sumas, por lo que se compara con tolerancia y no por hash idéntico.

## Mediciones preliminares

| Modo real | Procesos de gradientes | Tiempo lanzamiento (s) | Bucle entrenamiento (s) | Máx. RSS KiB | Máx. diferencia pesos vs secuencial |
|---|---:|---:|---:|---:|---:|
| Secuencial | 1 | 11.2782 | 10.0792 | 37864 | 0 |
| Paralelo local | 2 | 10.3645 | 8.9140 | 39408 | 1.1103e-16 |
| AMQP localhost | 2 workers | 11.3322 | 10.0503 | 42936 | 1.1103e-16 |
| AMQP localhost con pools | 2 workers × 2 hijos | 11.1061 | 10.0524 | 43068 | 1.1623e-16 |

Tiempo de lanzamiento medido externamente, incluye arranque CLI y evaluación final. En AMQP los workers se iniciaron previamente, por lo que excluye su arranque y el del broker. RSS de GNU time corresponde al lanzamiento observado; en AMQP excluye los workers/broker externos y no representa memoria total del sistema.

Speedup preliminar local de dos procesos = 11.278151387/10.364549537 = **1.08815**; eficiencia descriptiva por dos procesos = **0.54407**. No mide eficiencia por dos núcleos físicos reservados. Los cocientes localhost AMQP son 0.99523 y 1.01549; no son evidencia de speedup entre nodos. Un ensayo breve no permite concluir escalabilidad. Checkpoint/fsync y evaluación representan una parte considerable del tiempo; IPC, serialización, transporte y particiones pequeñas añaden sobrecoste.

En paralelo local se observaron dos PIDs distintos, suma de CPU de gradientes 3.6884 s frente a map 2.0130 s: ejecución de cálculo concurrente real. En AMQP se observaron dos PIDs de workers; con pools, dos padres y cuatro hijos distintos. Registros completos en la evidencia JSON.

mapSeconds mezcla cálculo y transporte. receiveSeconds incluye espera del cálculo; no se interpreta como latencia pura de red. stepSeconds excluye el checkpoint posterior, el bucle sí lo incluye. La suma de wall de workers puede superar el tiempo transcurrido por solapamiento. La CPU del modo con pools suma CPU de hijos, no CPU total de broker/coordinador.

| Métrica del modelo seleccionado | Resultado en los cuatro modos |
|---|---:|
| Accuracy train | 719/720 = 99.8611% |
| Cross entropy train | 0.05078986861665274 (variaciones de redondeo) |
| Accuracy validation | 180/180 = 100% |
| Cross entropy validation | 0.04674407442731196 |
| Accuracy test | 300/300 = 100% |
| Cross entropy test | 0.05451329364169657 |
| Confusión test | Diagonal 100/100/100; fuera de diagonal 0 |
| Versión final / pasos Adam | 90 / 90 |

## Pruebas y recuperación

La suite cubre gradientes ponderados, particiones desiguales, NaN/Inf, formas, metadatos, versión antigua, respuestas faltantes, duplicadas y contradictorias; 24 commits concurrentes producen una sola actualización. Dos procesos reales reproducen entrenamiento secuencial; excepciones de worker abortan el paso sin actualización parcial.

Seis pruebas con RabbitMQ real verificaron cálculo, entrenamiento corto equivalente, duplicados/versiones antiguas, timeout sin consumidores con checkpoint versión 0, dataset incorrecto, mensajes malformados, pools locales y desconexión real de un worker con reentrega al superviviente. El test de desconexión usa señales POSIX y se omite en Windows. La cola de inferencia de fase III sigue separada.

CLI de recuperación: pausa después de 3 pasos, reanudación con 87 pasos nuevos hasta versión/Adam 90; pesos finales idénticos byte por byte a la ejecución secuencial ininterrumpida. Checksum corrupto se rechaza. El lease exclusivo impide dos coordinadores escribiendo la misma salida. Tras terminación abrupta puede quedar lease: comprobar PID/host antes de retirarlo manualmente. Evidencia: [FASE4_RECUPERACION.json](evidencias/FASE4_RECUPERACION.json).

La regresión integral se ejecuta con el broker aislado, variables privadas cargadas fuera del repositorio, PC3_RABBIT_INTEGRATION=1 y PC3_RABBIT_ALLOW_CONTROL=1:

```bash
PYTHONPATH=/tmp/pc3-amqp-deps python3 scripts/validate_phase2.py --dotnet-dir /tmp/pc3-dotnet8 --output build/phase4-final
```

Resultado final: **142 pruebas ejecutadas; 141 aprobadas, 0 fallidas, 0 errores y 1 omitida** (escenario previo de seis núcleos físicos, no disponibles). Duración del runner: 122.97 s; model_unchanged=True.

El resultado final y manifiesto de fuentes/artefactos protegidos se conservan en [FASE4_PRUEBAS.json](evidencias/FASE4_PRUEBAS.json).

Durante desarrollo se corrigieron una fixture que intentaba mutar una tupla, una configuración de prueba que reutilizaba una cola retry con otro DLX y la captura de TimeoutError antes de OSError. No se ocultan como resultados exitosos de las primeras ejecuciones; la aceptación corresponde a las ejecuciones finales posteriores a las correcciones.

## Cumplimiento y límites

Demostrados: separación matemática/actualización, agregación ponderada, snapshot/versiones/hash, procesos reales, transporte AMQP real, una actualización Adam por batch, idempotencia, checkpoint/reanudación y evaluación. No se modificaron contratos compartidos ni backend/clientes.

Pendientes: máquinas independientes y red real, Windows y combinación de SO, asignación física de recursos, particiones de red, campañas repetidas y saturación PC3, integración contractual con el equipo y aceptación del PDF/profesor. La implementación de entrenamiento es Python; no se atribuye entrenamiento a Java/C#. No se valida generalización externa. El número de casos de prueba no sustituye estas evidencias.

La fase V no se inició. Requerirá nodos autorizados, broker accesible, dataset/código idénticos, reloj/telemetría, afinidad o cuotas documentadas y cargas repetidas con latencia, throughput, errores, colas, CPU, memoria y coste de comunicación medidos.
