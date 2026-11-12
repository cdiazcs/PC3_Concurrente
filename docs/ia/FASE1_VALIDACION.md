# Fase 1 — Validación CNN y MLP

Confirmación posterior contra el adjunto específico: ver [FASE1_CNN_MLP.md](FASE1_CNN_MLP.md) y [FASE1_RESULTADOS.md](FASE1_RESULTADOS.md). Los resultados que siguen corresponden a la ejecución original de fase I; la confirmación añade dos pruebas y metadatos de evaluación, conservando los pendientes externos.

Fecha: 2026-11-12 (America/Lima). Rama feature/ai-distributed. Sólo módulo IA, pruebas y documentación; sin RabbitMQ, workers nuevos, entrenamiento distribuido ni modificación de contratos. Los documentos de fase 0 seguían sin versionar al iniciar esta fase y se conservaron.

## Cambios

1. `cnn_python/model.py`: se añadió cross_entropy(logits, label), compartida por backward, entrenamiento y evaluación. La fórmula anterior `max + log(sum(exp(z-max))) - z_y` pierde precisión con un offset grande: para z=[1e16,1e16,1e16] devolvía 2.0 en vez de ln(3). La nueva agrupa primero `(max-z_y) + log(sum(exp(z-max)))`. También evita calcular log de probabilidades que hayan redondeado a cero.
2. `cnn_python/evaluate.py`: ahora publica cross_entropy junto con accuracy/confusión/recall; calcula todo desde un único forward por imagen y valida la etiqueta antes de usarla como índice. No se cambió el formato CSV de predicciones.
3. `cnn_python/train.py`: usa la misma función loss y rechaza evaluación vacía explícitamente. No se alteraron el optimizador, gradientes, arquitectura o hiperparámetros.
4. `tests/test_cnn_phase1.py`: siete pruebas adicionales, independientes de .NET/broker/BD. Comprueban estabilidad de loss, gradientes completos con dos semillas adicionales, convenciones de derivada, selección de checkpoint/batch incompleto y paridad Java/Python.
5. `scripts/validate_phase1.py`: regenera dataset, compara contenidos, ejecuta dos entrenamientos completos separados de 60 épocas, evalúa cada checkpoint, compara pesos/historia y registra hashes de fuentes/datos/pesos. Rechaza directorios de salida existentes y comprueba que los artefactos oficiales permanezcan intactos.

No se reescribió la CNN. Se conserva la arquitectura 16×16×1 → 2 filtros 3×3 → 2×14×14 → ReLU → pooling 2×2 → 2×7×7 → flatten 98 → Dense 8/ReLU → Dense 3/Softmax. Total: 18+784+8+24+3=837 parámetros; sin bias convolucional.

## Referencia matemática

La operación llamada convolución usa correlación cruzada válida (kernel sin invertir), convención habitual de CNN: `C[f,r,c] = sum(I[r+i,c+j] K[f,i,j])`. ReLU conserva valores positivos; pooling selecciona el máximo de cada bloque 2×2 y recuerda su posición. El vector concatena primero un canal y luego el otro, en orden por filas.

Para la MLP: h=ReLU(W1 x+b1), z=W2 h+b2, p=softmax(z). La pérdida de una muestra etiquetada y es `L = log(sum(exp(z_j))) - z_y`, calculada con desplazamiento estable. Gradientes: `dL/dz = p-onehot(y)`, `dW2 = dz h^T`, `dh = W2^T dz`, `da = dh * 1[prehidden>0]`, `dW1 = da x^T`, `dx = W1^T da`. El backward del pooling enruta dx al ganador; el filtro recibe la suma de delta por el parche de entrada correspondiente. ReLU'(0)=0 y, ante empates de pooling, se elige el primer elemento. En esos puntos no diferenciables se verifica la convención analíticamente; no se exige que diferencias centrales coincidan con ella.

El entrenamiento promedia gradientes por el tamaño real del minibatch (incluido el último incompleto), recorta su norma global a 5 y actualiza con Adam (beta1=.9, beta2=.999, epsilon=1e-8) y corrección de sesgo. Los momentos y el contador avanzan una vez por minibatch. El checkpoint se selecciona con validation, nunca con test.

## Pruebas

```bash
python3 -m unittest discover -s tests -p 'test_cnn*.py' -v
python3 scripts/check_main.py
python3 -m cnn_python.evaluate --output build/phase1-official-evaluation
python3 scripts/validate_phase1.py --output build/phase1-reproduction
```

El primer comando se ejecutó con permiso para sockets locales: **31/31 OK, 0 fallos/errores, 6.789 s**. Las siete pruebas nuevas por separado pasaron en 5.840 s. La comparación Java/Python compila ClientCli y un probe temporal, usa `-Djava.awt.headless=true` y no necesita servidor ni C#.

- Gradientes: 837 parámetros por caso × 3 casos = 2511 comparaciones centrales; epsilon=1e-5 y tolerancia absoluta 2e-6. Se cubren las tres etiquetas con pesos/inputs distintos. Es validación local numérica, no prueba universal de todos los inputs.
- Pooling empatado: backward coincide con la convención del primer ganador en fixture controlado. ReLU cero/negativa bloquea gradientes según lo documentado.
- Loss: invariancia ante desplazamientos representables, logits grandes iguales, probabilidad correcta bajo flujo a cero, rechazo de etiquetas inválidas/no finitos y conjunto vacío.
- Entrenamiento pequeño: minibatch final incompleto, loss desciende, pesos finitos y checkpoint corresponde al mínimo validation. Las muestras compartidas entre train/validation en ese fixture artificial sólo prueban el mecanismo; no constituyen evaluación de generalización.
- Preprocesamiento: 13 archivos × 256 valores Java/Python, tolerancia 1e-12; formatos PNG gris, RGBA y PGM, con redimensión.

El primer intento de reproducción se detuvo antes de entrenar por exigir igualdad binaria del ZIP. La investigación comparó todas las entradas: cero diferencias de nombres/contenido, incluido manifest. Se corrigió el verificador para distinguir identidad del contenedor e identidad de datos. No se alteró el generador ni el dataset oficial. Los artefactos de ese intento quedan ignorados en build/phase1-validation; no se declaran una reproducción exitosa.

## Dataset y generalización

Ver DATASET_Y_VALIDACION.md para procedencia, semillas, particiones, riesgos y protocolo externo. El usuario confirmó que sólo existen imágenes sintéticas. La familia geometry-v1 presenta las mismas reglas geométricas en train/validation/test; no hay duplicados exactos, pero sí un dominio compartido. Obtener y evaluar un conjunto externo con procedencia/permiso sigue PENDIENTE. El PDF oficial, aceptación docente del dataset y aclaración sobre uno/dos modelos siguen sin verificarse.

## Explicación sencilla

Los filtros son dos detectores pequeños que recorren la imagen. Pooling resume dónde respondieron con más fuerza; el MLP combina esos resúmenes para elegir la figura. Backpropagation recorre ese camino al revés y calcula cuánto conviene cambiar cada peso. Adam usa esos cambios para aprender. Esta fase comprueba las cuentas y que repetir el entrenamiento produzca el mismo resultado; repartir esas cuentas entre máquinas pertenece a fases posteriores.

## Reproducción completa y métricas observadas

`validate_phase1.py` terminó correctamente en 93.27 s totales en Ubuntu/Python 3.14.4. Entrenamiento 1: 46.32 s; entrenamiento 2: 42.69 s. Ambos ejecutaron las 60 épocas y seleccionaron época 60. Semilla 20261022, batch 24, learning rate .003, patience 12; parámetros originales, sin ajustar contra test.

| Resultado | Train (720) | Validation (180) | Test (300) |
| --- | --- | --- | --- |
| Accuracy de ambos runs | 1.0 | 1.0 | 1.0 |
| Cross-entropy de ambos runs | .0001089893962882659 | .00010946370327824087 | .0002303936675979407 |

Matriz test, filas reales/columnas predichas, orden circulo/cruz/triangulo: `[[100,0,0],[0,100,0],[0,0,100]]`. Validación inicial accuracy .3166667 y loss aproximadamente 1.0919184; todas las secciones de parámetros cambiaron durante el entrenamiento.

Los dos runs producen pesos **idénticos byte a byte** e historias CSV idénticas. SHA256 nuevo: `688f36bd68f140fbf387149d13b50d056ad2db8b11bc70b17be942da3d26be51`. Frente al modelo oficial la máxima diferencia absoluta por peso es 4.440892098500626e-16, y por probabilidad en test es 2.688821387764051e-17. Son equivalentes numéricamente en estos datos, pero NO son el mismo artefacto binario. No se atribuye la causa exacta de esa diferencia sin evidencia. Los hashes del informe histórico siguen sin explicar la procedencia exacta de sus fuentes.

Dataset regenerado: SHA256 ZIP `31304fe48519a699177f7e3d30e0d2189cf81af62516c4eb875bc481ee0cd3a8`; el ZIP oficial conserva `b9130514dca3a0b0bb3ae34cf23a59d1c5f455576ad41fce73118b6112143d81`. Todas las entradas descomprimidas son idénticas. El verificador preserva ambos hechos sin afirmar igualdad binaria.

Evidencia conservada en `docs/ia/evidencias/FASE1_REPRODUCCION.json`: entorno, hashes de todas las fuentes Python IA y del verificador, comprobación de integridad de artefactos oficiales, comparación de fuentes históricas, métricas por ejecución y comandos exactos. Los modelos nuevos, historias completas, logs y ZIP regenerado quedan bajo `build/phase1-reproduction/` (ignorado por Git). No se agregan duplicados binarios al repositorio. Para reproducir de nuevo, usar otro directorio de salida; el script rechaza sobrescribir evidencia previa.

El comando de evaluación del modelo oficial produjo el nuevo campo cross_entropy y la misma confusión en `build/phase1-official-evaluation/`, sin sobrescribir model/evaluation. `scripts/check_main.py` salió con código 0 y verificó inferencia/compilación Java; mantuvo explícito que C# no está verificado. En esta fase no se repitió la suite integral dependiente de .NET, ya bloqueada en fase 0: no hay evidencia nueva de distribución ni AMQP.

## Aceptación y cierre

| Criterio fase 1 | Estado |
| --- | --- |
| Dimensiones, 837 parámetros y gradientes de todas las capas | VERIFICADO localmente |
| Convenciones pooling/ReLU y estabilidad de loss | VERIFICADO |
| Entrenamiento completo repetible con fuentes identificadas | VERIFICADO, dos runs actuales |
| Dataset regenerado con contenido idéntico y splits sin duplicados exactos | VERIFICADO |
| Accuracy/loss/confusión del test sintético | VERIFICADO |
| Preprocesamiento Java/Python | VERIFICADO en 13 archivos; Android/Web pendientes de implementación |
| Pesos/dataset/informes oficiales preservados | VERIFICADO por hashes antes/después |
| Causa exacta de fuentes históricas desactualizadas | NO RESUELTA; nueva procedencia registrada |
| Imágenes externas documentadas y evaluación externa | PENDIENTE, no disponibles según usuario |
| Aceptación docente de dataset y requisitos oficiales | NO VERIFICADO, falta PDF/aclaración |

**Cierre: validación técnica sobre el dataset sintético completada; fase 1 PARCIAL respecto al plan completo por falta de conjunto externo y validación docente.** No se presenta 100% sintético como generalización ni se promocionan pesos nuevos automáticamente. No se inició fase 2. Para cerrar el pendiente externo se requiere obtener datos independientes documentados y ejecutar el protocolo indicado en DATASET_Y_VALIDACION.md; no hace falta reescribir la CNN para ello.

Detalle del contenedor ZIP: las 1201 entradas difieren únicamente en `create_system` (0 en el archivo heredado, 3 en Linux). Se comprobó en memoria que normalizar sólo ese byte del directorio central produce exactamente los bytes originales. No se modificó ninguno de los ZIP en disco. Así, la diferencia de hash del dataset queda explicada por metadatos de plataforma, no por imágenes distintas.
