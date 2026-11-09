# Matriz de cumplimiento PC3 (enunciado P3cc4P1-262_v07)

**Criterios de cierre:** `BASE` = existe en el ZIP de etapa anterior, `ESQUELETO` = diseño/scripts iniciales sin integración, `PENDIENTE` = requiere implementación y/o evidencia.

| Requisito (página del PDF) | Estado en este `main` | Prueba/evidencia obligatoria | Responsable |
| --- | --- | --- | --- |
| CNN sin TensorFlow/PyTorch, MLP, ReLU, pooling (1–2) | BASE | salida entrenada, accuracy/loss, matriz, código | 2 |
| Datos propios + procedencia/preprocesamiento (2) | BASE parcial | justificar generador propio y test externo | 2 |
| Entrenar y testear concurrente/paralelo/distribuido (2) | PENDIENTE | logs y comparación de ejecuciones | 2 |
| Sockets TCP propios entre clientes-backend (1,3) | BASE Desktop/CLI | captura paquetes, logs y 3 clientes | 1 y 3 |
| RabbitMQ backend-IA-BD; colas A/B/resultados/control (3) | ESQUELETO contrato | colas activas, trazas con ids | 1 y 2 |
| Android Kotlin (3) | PENDIENTE | envío/recepción real por TCP | 3 |
| Desktop Java (3) | BASE | demostración remota, chat y errores | 3 |
| Web HTML/JS + HTTP sobre sockets propios (3) | PENDIENTE | fetch→gateway→backend→respuesta | 3 |
| BD1 modelo y metadatos/resultados/historial (2,4) | ESQUELETO SQL | script aplicado, consultas, AMQP | 1 |
| BD2 distinta, validación contra BD1 por RabbitMQ (2,4) | ESQUELETO SQL | validación real, consultas, AMQP | 3 |
| Escrituras concurrentes seguras (4) | PENDIENTE | transacciones, upsert, stress | 1 y 3 |
| 3 nodos / SO distintos / lenguajes distintos (2,4) | PENDIENTE | IP, SO, lenguajes, captura de despliegue | los 3 |
| Diagramas de arquitectura y protocolo (4) | ESQUELETO | versiones finales con IP/colas | 1 |
| Secuencial, paralelo, distribuido, paralelo distribuido (5) | BASE parcial | pruebas comparables, N/M/H explícitos | 2 |
| 1000 transacciones con delay aleatorio, 3 clientes (5) | PENDIENTE | CSV, muestra de errores y colas | 2 y 3 |
| Latencia, throughput, CPU/memoria, tasa error y colas (5) | BASE parcial | instrumentación conjunta y gráficas | 2 |
| ZIP UNIVIRTUAL: fuentes autorizadas, SQL, PDF informe/PPT (5) | PENDIENTE | manifest y ZIP final separado | los 3 |

## Dos contradicciones internas del propio PDF para consultar

1. Página 4 pide "exactamente 2 bases de datos" y luego menciona BD3 / BD1 <> BD2 <> BD3.
2. Se pide seleccionar una CNN por grupo, pero aparecen "modelo A" y "modelo B" y colas para ambos.

**No se prometen 20 puntos**: el objetivo es verificar cada criterio y sostenerlo con evidencia.
