# Plan de implementación IA — Fases 1 a 6

Fecha: 2026-11-12. Base: auditoría FASE0_AUDITORIA.md, rama feature/ai-distributed. **Fases 1–4 autorizadas y ejecutadas dentro del alcance local; fases 5–6 pendientes de autorización.** Mantener cambios pequeños, contratos compatibles y pesos oficiales protegidos. No merge/rebase/push/PR sin indicación previa. No instalar dependencias sin explicar necesidad. PDF oficial pendiente de recuperar; matriz del repositorio es provisional.

## Orden y prioridades

1. P0: recuperar enunciado, resolver BD/modelos/SO y habilitar .NET 8 para ejecutar las suites existentes. Verificar Python/JDK/.NET en cada equipo.
2. P1: fase 1 fija referencia matemática y trazabilidad; fase 2 valida distribución de inferencia existente sin reescribirla.
3. P1: fase 3 integra contrato AMQP con integrante 1; fase 4 introduce gradientes/versiones y entrenamiento distribuido real.
4. P1: fase 5 mide sólo sistemas integrados, después de fijar datasets, modelos, semilla y presupuesto CPU.
5. P2: fase 6 consolida evidencias y prepara entrega/PR revisable; publicación sólo con indicación del usuario.

## Fase 1 — Validación CNN/MLP y modelo

- Tareas: identificar causas de hashes de fuentes desactualizados; reproducir entrenamiento completo en salida alternativa, registrar entorno y hashes; revisar gradientes ante empates/ReLU y estabilidad; agregar loss al informe de evaluación; reunir conjunto externo independiente y justificar procedencia/licencia/aceptación del dataset propio.
- Archivos previstos: cnn_python/model.py, train.py, evaluate.py, dataset.py, images.py sólo si se demuestra defecto; tests/test_cnn.py; model/training y model/evaluation mediante artefactos alternativos antes de promover pesos; docs/ia/.
- Pruebas: conservar 24 tests, diferencias finitas con más semillas/casos diferenciables, descenso de loss, parámetros finitos, repetición de semilla, hashes y no solapamiento; comparar PNG/PGM/preprocesamiento de clientes.
- Aceptación: referencia matemática documentada, 837 parámetros coherentes, reproducción trazable, evaluación sin usar test para elegir checkpoint, loss/accuracy/confusión publicados con alcance sintético/externo separado. Umbral de accuracy por acordar según enunciado; .85 actual no es requisito docente confirmado.
- Dependencias: PDF/profesor (dataset/modelos), integrantes 1 y 3 para formato de imagen. Riesgo: excelente test sintético sin generalización.

## Fase 2 — Concurrencia e inferencia distribuida

- Tareas: ejecutar primero tests/test_protocol.py, test_identify.py y test_distributed.py con .NET disponible; corregir sólo fallos demostrados. Validar CAPS/JOB/PART, chunks, offsets/barreras y equivalencia por tensor. Revisar admisión de conexiones/colas y deadlines absolutos; documentar procesos Python frente a GIL.
- Archivos previstos: workers/python/worker.py, workers/java/WorkerJava.java, workers/csharp/Worker.cs y Worker.csproj; server-java/DistributedCnn.java en coordinación con integrante 1; tests/test_protocol.py, test_identify.py, test_distributed.py.
- Pruebas: tres lenguajes, 300 imágenes, IDs externos repetidos simultáneos, respuestas desordenadas, fragmentadas/malformadas, worker caído/lento, carga fría, saturación y recuperación; comparar contra CNN Python con tolerancia explícita (harness actual 1e-8).
- Aceptación: suites integrales verdes, resultados sin mezcla, tiempos acotados y sin fallback silencioso a inferencia íntegra; evidencia real de más de un worker. Distinguir prueba localhost de distribución entre máquinas.
- Dependencias: .NET 8, JDK, Python y nodos/red autorizados; integrante 1 para coordinador. Riesgo: preparación común impide probar Java/Python si falta C#; desacoplarla sólo en cambio revisable sin ocultar pruebas faltantes.

## Fase 3 — Nodo IA RabbitMQ

- Tareas: acordar contrato final sin modificar unilateralmente contracts/; seleccionar cliente AMQP permitido por enunciado antes de añadir dependencia; implementar consumidor/publicador IA, correlación idSolicitud, modelo/versiones, validación imagen, errores/timeout, ack, reintentos acotados, idempotencia y heartbeat según contrato.
- Archivos previstos: nuevo adaptador bajo cnn_python/ o workers/python/ según acuerdo, messaging/ sólo en coordinación, pruebas nuevas de integración AMQP y docs/ia/. Preservar TCP legado.
- Pruebas: mensaje válido/inválido/duplicado, reinicio del consumidor/broker, correlación y publicación confirmada, no perder resultado antes de ack, reentrega sin efectos duplicados, TTL/DLQ según contrato.
- Aceptación: backend→RabbitMQ→IA→RabbitMQ→backend operativo con probabilidades equivalentes a referencia y trazas por ID; integración BD confirmada con responsables, sin alegar que TCP prueba AMQP.
- Dependencias: integrante 1 entrega broker/configuración/contrato/observabilidad; integrante 3 normaliza imágenes y flujo de validación; profesor aclara modelo A/B y bibliotecas permitidas.

## Fase 4 — Entrenamiento concurrente, paralelo y distribuido

- Tareas: definir minibatch global y división sin repetir muestras; cálculo independiente de gradientes con snapshot inmutable y versión de pesos; agregación ponderada por cantidad de muestras; barrera por paso y actualización Adam única (incluye momentos/contador); checkpoint/versionado y tratamiento de worker caído o gradiente duplicado/obsoleto. Precisar transporte de entrenamiento compatible con arquitectura aprobada.
- Archivos previstos: cnn_python/train.py/model.py y módulos nuevos de coordinación/gradientes; workers/ sólo en operaciones necesarias; tests de entrenamiento y docs/ia/. No mezclar protocolo gradientes con forward existente sin versionado.
- Pruebas: mismo minibatch en secuencial/paralelo/remoto; comparar gradiente agregado, actualización y loss con tolerancias justificadas; último batch desigual, retrasos/desorden, fallo/reintento, seed fija, duplicados y checkpoints.
- Aceptación: versiones consistentes y equivalencia numérica; entrenamiento/evaluación concurrente/paralela/distribuida demostrados con logs y nodos reales. No afirmar entrenamiento distribuido por disponer de inferencia distribuida.
- Dependencias: fases 1–3, nodos y presupuesto de CPU, coordinación AMQP con integrante 1. Riesgos: gradientes duplicados, pesos mezclados, Adam divergente y sumas flotantes en distinto orden.

## Fase 5 — Experimentos y rendimiento

- Tareas: fijar cuatro perfiles y presupuestos; adaptar invocaciones Linux/headless sin instalar alias global; preparar dataset común y pesos idénticos; campañas repetidas de inferencia y entrenamiento por separado; coordinar 1000 transacciones con retardos y clientes reales; medir CPU/memoria/latencia/p95/throughput/error/colas; conservar mediciones brutas y generar gráficas sin datos inventados.
- Archivos previstos: benchmarks/CnnBenchmark.java, PhysicalConfig.java, LocalCnn.java, node_agent.py, resource_probe.py, configs/, scripts .ps1 o equivalentes multiplataforma, GraficasBenchmark.py; tests/test_benchmark.py; docs/ia/ y destino de evidencias acordado.
- Pruebas: carga/semilla/hash idénticos, resultados correctos, afinidad y slots antes/después, tiempos comparables, rechazo de localhost como prueba física, errores contabilizados, scripts de gráficas reproducibles.
- Aceptación: secuencial 1 proceso/1 hilo de cálculo; paralelo multinúcleo local; distribuido varias máquinas 1 núcleo/1 hilo de cálculo por nodo; paralelo distribuido con CPU local múltiple. Documentar hilos auxiliares JVM/control por separado y validar interpretación docente. Tres nodos/SO/lenguajes con evidencia independiente. Número exacto de transacciones por cliente/global confirmado con PDF. Gráficas latencia vs nodos, throughput vs configuración y colas bajo carga, con repeticiones y alcance.
- Dependencias: fases 2–4, backend/broker/BD de integrante 1, clientes/BD2 de integrante 3; disponibilidad de máquinas. Riesgo: muestra breve o 300 requests por defecto confundidas con experimento final; memoria/colas aún sin instrumentar.

## Fase 6 — Integración y entrega

- Tareas: repetir suite completa y pruebas extremo a extremo con tres clientes; consolidar diagramas actuales/objetivo, versiones y guía de reproducción; informe y presentación PDF, manifiesto de entrega y ZIP separado conforme a extensiones oficiales; preparar descripción/diff del PR revisable.
- Archivos previstos: docs/ia/, documentación compartida bajo coordinación, guías y scripts de pruebas/empaquetado, entregables en destino acordado. No tocar bases de datos/clientes para suplir trabajo ajeno sin necesidad de integración acordada.
- Pruebas: instalación limpia según guía, fuentes compilables, dataset/pesos/checksums, fallos y recuperación, trazabilidad IA→BD→respuesta y escrituras concurrentes/idempotentes con responsables; inspección de ZIP sin temporales ni secretos.
- Aceptación: matriz con evidencias verificables por requisito, limitaciones expresas, código/dataset/SQL/PDF completos y paquete válido según PDF. PR/push/merge sólo tras instrucción del usuario y revisión requerida por el equipo.
- Dependencias: integrantes 1 y 3, decisiones del profesor y resultados de fases previas. No prometer calificación.

## Criterio de avance

Fase 0 cerrada como diagnóstico. Fase 1: criterios técnicos confirmados contra el adjunto específico (FASE1_CNN_MLP.md y FASE1_RESULTADOS.md), 33 pruebas CNN correctas dentro de la campaña de 101 aprobadas/1 omitida; reproducción anterior verificada por hashes. El plan ampliado mantiene evaluación externa y aceptación docente pendientes (DATASET_Y_VALIDACION.md). Fase 2: coordinación y workers Java/Python/C# verificados localmente, límites/deadlines corregidos; confirmación integral 102 aprobadas y una omitida por hardware, sin fallos/errores; 12 mediciones locales de 1000 solicitudes cada una con cero errores (FASE2_CONCURRENCIA_DISTRIBUCION.md y FASE2_RESULTADOS.md). Estado: IMPLEMENTACIÓN LISTA / DESPLIEGUE DISTRIBUIDO PENDIENTE. SDK .NET 8 disponible temporalmente en /tmp; despliegue entre equipos, escenario local de seis núcleos, PDF y aclaraciones docentes pendientes. Fase 3: nodo IA AMQP implementado; broker real, 125 pruebas correctas/1 omitida y 3483 solicitudes de carga sin errores (FASE3_RABBITMQ.md y FASE3_RESULTADOS.md). Integración con backend/BD, acuerdos definitivos de contratos/timeout y PDF pendientes. Fase 4: gradientes separados, agregación ponderada, procesos locales, transporte AMQP, Adam único y recuperación implementados; evidencias en FASE4_ENTRENAMIENTO_DISTRIBUIDO.md y FASE4_RESULTADOS.md. Estado: IMPLEMENTACIÓN DISPONIBLE — VALIDACIÓN DISTRIBUIDA PENDIENTE. Esperar solicitud del usuario antes de comenzar fase 5.
