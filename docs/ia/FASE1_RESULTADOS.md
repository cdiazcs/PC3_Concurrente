# Fase I — Resultados y confirmación

Fecha: 2026-11-12 (America/Lima). Confirmación contra el adjunto específico de Fase I. Ver FASE1_CNN_MLP.md para arquitectura, fórmulas, dataset, interfaces y aceptación. Se preserva el trabajo de fase II ya autorizado y realizado; esta revisión no implementa funcionalidades de fases posteriores.

## Comandos y evidencia

| Comando desde la raíz efectiva | Ejecución | Resultado |
| --- | --- | --- |
| `git status --short`; `git branch --show-current` | Nueva confirmación | feature/ai-distributed; cambios previos de fases I/II sin commit, conservados |
| `python3 -m unittest discover -s tests -p 'test_cnn*.py' -v` | Ejecución anterior de fase I | 31/31 OK en 6.789 s; evidencia histórica, antes de dos tests añadidos en la confirmación |
| `python3 scripts/validate_phase1.py --output build/phase1-reproduction` | Experimento anterior de fase I | Dos runs completos de 60 épocas; pesos e historia idénticos; 93.27 s totales. No se repitió en esta revisión |
| `python3 -m cnn_python.evaluate --output build/phase1-confirmation-evaluation` | **Nueva** | exit 0; 300 muestras, accuracy=1.0, cross_entropy=.0002303936675979407, métricas por clase y configuración explícita; JSON y CSV nuevos |
| `python3 scripts/validate_phase2.py --dotnet-dir /tmp/pc3-dotnet8 --output build/phase1-confirmation-regression` | **Nueva, suite integral para confirmar regresión** | exit 0; 102 casos: **101 aprobados, 1 omitido, 0 fallos, 0 errores**; 110.171 s unittest |
| Comprobación SHA256 de model.py/train.py/dataset.py contra FASE1_REPRODUCCION.json | Nueva | Los tres coinciden exactamente con las fuentes del entrenamiento anterior |
| Comprobación de todos los archivos model/ antes/después de la suite | Nueva | Todos conservados; pesos/dataset oficiales intactos |
| `git diff --check` | Nueva | Sin errores de espacios |

El script llamado validate_phase2.py se reutiliza porque ejecuta **toda** la suite y comprueba compatibilidad con backend/workers. No significa que esta confirmación implemente otra fase. Prepara PATH/headless y caches sólo para sus procesos; usa el SDK temporal disponible, sin instalar herramientas nuevas. Las pruebas de sockets se ejecutaron fuera del sandbox que los restringe.

## Conteo de la campaña nueva

| Grupo | Aprobadas | Omitidas |
| --- | --- | --- |
| CNN original | 24 | 0 |
| Fase I ampliada | 9 | 0 |
| Protocolo/cliente local | 18 | 0 |
| IDENTIFY/concurrencia/errores | 18 | 0 |
| Coordinación entre workers | 15 | 0 |
| Límites/deadlines de workers existentes | 4 | 0 |
| Desktop headless/TCP | 7 | 0 |
| Benchmarks existentes | 6 | 1 |
| **Total** | **101** | **1** |

La omisión es `test_parallel_distributed_profile_with_six_physical_cores`: necesita seis núcleos físicos disjuntos para emular tres presupuestos de dos núcleos y este equipo tiene cuatro. Es un pendiente previamente documentado de fase II/benchmark, **no una prueba aprobada ni una regresión nueva de CNN**. La evidencia física entre equipos también sigue pendiente.

Los 33 casos CNN (24+9) pasan dentro de la campaña; no se atribuye un tiempo separado a ese subconjunto. Las dos pruebas nuevas verifican Adam con fórmula escalar de dos pasos/clipping y métricas con clasificaciones incorrectas/clases ausentes. El gradient checking mantiene 2511 comparaciones numéricas, tolerancia 2e-6 y epsilon=1e-5.

## Evaluación nueva del modelo oficial

| Métrica | Resultado |
| --- | --- |
| Conjunto | geometry-v1, test, seed=31415 |
| Número de imágenes | 300; 100 por clase |
| Accuracy | 1.0 (300/300) |
| Cross-entropy media | .0002303936675979407 |
| Accuracy por clase (recall) | circulo=1.0, cruz=1.0, triangulo=1.0 |
| Matriz: filas reales, columnas predichas | `[[100,0,0],[0,100,0],[0,0,100]]` |
| Configuración | 16×16×1; dos filtros 3×3 valid/stride1; pooling2; flatten98; densas8/3; 837 parámetros |
| Dataset SHA256 | b9130514dca3a0b0bb3ae34cf23a59d1c5f455576ad41fce73118b6112143d81 |
| Pesos SHA256 | df582438e8fa66b5f606408d646b8df3025f3e9b033dd780b17e45df0c550ec4 |

Los resultados se calcularon desde predicciones reales y logits. El reporte distingue split, semillas y hashes. La accuracy por clase se define como diagonal/suma de fila, equivalente al recall; no se confunde con precisión por columna. `.85` sigue siendo un objetivo heredado del software, no un umbral oficial verificado.

## Entrenamiento anterior que sigue siendo válido

Dos ejecuciones completas previas con las mismas fuentes actuales de model.py, train.py y dataset.py: 60 épocas, mejor época 60, seed=20261022, batch=24, lr=.003, patience=12. Tiempos anteriores 46.32 y 42.69 s. Los dos modelos y los CSV de historia son idénticos entre sí; SHA256 de esos pesos alternativos: 688f36bd68f140fbf387149d13b50d056ad2db8b11bc70b17be942da3d26be51. No se promovieron a pesos oficiales.

| Split | Accuracy anterior | Loss anterior |
| --- | --- | --- |
| Train | 1.0 | .0001089893962882659 |
| Validation | 1.0 | .00010946370327824087 |
| Test | 1.0 | .0002303936675979407 |

Cambiar los metadatos del reporte de evaluación no cambia los gradientes/Adam ni requiere volver a entrenar para comprobar esos campos. Las pruebas nuevas se ejecutan sobre el código actual; la evidencia histórica se conserva identificada como tal. Los hashes de fuentes del informe original model/training/training.json siguen sin trazabilidad histórica resuelta: no se sustituyeron por hashes recientes.

## Evidencia y documentos

- FASE1_CNN_MLP.md: documento técnico con las secciones exigidas por el adjunto.
- FASE1_RESULTADOS.md: esta tabla de resultados y revisión de aceptación.
- evidencias/FASE1_CONFIRMACION.json: campaña nueva completa, versiones, hashes, resultados por caso, evaluación recalculada y referencia al experimento anterior con verificación de sus fuentes.
- evidencias/FASE1_REPRODUCCION.json y FASE1_VALIDACION.md: experimento y auditoría previos; sus conteos 31/31 son históricos.
- DATASET_Y_VALIDACION.md: generación, splits, limitaciones y propuesta de evaluación externa.
- build/phase1-confirmation-evaluation/: metrics.json y predictions.csv de esta revisión.
- build/phase1-confirmation-regression/: log completo y summary.json; procesos y compilaciones bajo build/stage0-*.

Los binarios y temporales permanecen ignorados. Los JSON conservados bajo docs/ia/evidencias son texto revisable. Ningún archivo oficial de model/ se sobrescribió.

## Aceptación del adjunto

| Criterio técnico | Evidencia / estado |
| --- | --- |
| CNN ejecuta y arquitectura documentada | VERIFICADO: forward, formas y 837 parámetros |
| Capas y MLP correctos | VERIFICADO: casos conocidos, dimensiones, entradas inválidas |
| Softmax/loss estables | VERIFICADO: offsets grandes, underflow y probabilidades |
| Gradientes numéricos | VERIFICADO: 837 parámetros × 3 casos |
| Entrenamiento actualiza correctamente | VERIFICADO: Adam de dos pasos, clipping, cambios reales, descenso y repetición |
| Evaluación con métricas reales | VERIFICADO: nueva evaluación y fixture con errores deliberados |
| Dataset documentado | VERIFICADO para la familia sintética; datos externos pendientes |
| Compatibilidad workers/backend | VERIFICADO localhost, sin cambiar APIs TCP |
| Sin nuevas regresiones | VERIFICADO: 101 aprobadas; único skip previo por hardware |
| Documentación lista para revisión | VERIFICADO: ambos documentos exigidos y evidencia actual |

**Criterios técnicos de Fase I del adjunto: COMPLETOS. Plan ampliado: mantiene pendientes externos.** No se acredita generalización a imágenes reales ni cumplimiento íntegro de la rúbrica oficial, porque falta evaluación externa y PDF/aceptación docente. El adjunto pide documentar esa limitación y proponer nuevas imágenes; ambas cosas están hechas. El plan original iba más allá y pedía reunirlas/evaluarlas: ese pendiente no se elimina.

## Git y siguiente paso

Rama feature/ai-distributed; sin commit/push/merge/rebase. En esta confirmación cambian únicamente evaluate.py, tests/test_cnn_phase1.py y documentación/evidencia IA. Los cambios previos de fases I/II se conservaron. Antes de guardar, revisar `git diff` y seleccionar porciones de archivos si se desean commits separados: evaluate.py y test_cnn_phase1.py ya incluían cambios anteriores sin commit.

Mensaje sugerido: `test: confirmar fase I CNN MLP y documentar evidencia`.

La fase II ya tiene validación local documentada; conserva pendientes de nodos reales/hardware. Esta revisión no la vuelve a implementar y no comienza fase III. El siguiente paso de revisión es decidir cómo obtener el PDF y un conjunto externo documentado, y guardar los cambios cuando el usuario lo indique.
