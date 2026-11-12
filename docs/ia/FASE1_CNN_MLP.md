# Fase I — CNN + MLP desde cero

Fecha de confirmación: 2026-11-12 (America/Lima). Rama `feature/ai-distributed`. Este documento responde al adjunto específico de Fase I y complementa FASE1_VALIDACION.md y DATASET_Y_VALIDACION.md. La fase II se había ejecutado previamente por instrucción del usuario; esta revisión conserva ese trabajo y no añade distribución ni RabbitMQ.

## 1. Objetivo y fuentes

Validar matemáticas, entrenamiento, evaluación, reproducibilidad, APIs y documentación del núcleo CNN/MLP sin frameworks de IA. Se revisaron FASE0_AUDITORIA.md, PLAN_IMPLEMENTACION.md, MATRIZ_PC3.md, ARQUITECTURA_PC3.md y contratos TCP/RabbitMQ, además de las fuentes y pruebas reales. El PDF oficial no está disponible en el repositorio: cumplimiento docente se interpreta provisionalmente desde la matriz, sin garantizar calificación.

El análisis de imports de cnn_python/ sólo encuentra biblioteca estándar Python: math, random, dataclasses, types, pathlib, zipfile, zlib, csv, json y utilidades de CLI/hash/tiempo. No se usa TensorFlow, PyTorch, NumPy ni una biblioteca que ejecute las operaciones IA.

## 2. Arquitectura, dimensiones y parámetros

| Capa | Operación / configuración | Entrada → salida | Parámetros |
| --- | --- | --- | --- |
| Entrada | Gris normalizado [0,1] | Imagen → 16×16×1 | 0 |
| CONV | Dos filtros 3×3, stride 1, padding valid, sin bias | 16×16×1 → 2×14×14 | 2×3×3=18 |
| ReLU | max(0,x) | 2×14×14 → igual | 0 |
| Max pooling | 2×2, stride 2 | 2×14×14 → 2×7×7 | 0 |
| Flatten | Canal primero, filas dentro del canal | 2×7×7 → 98 | 0 |
| Dense 1 | W1 de 8×98, B1 de 8; ReLU | 98 → 8 | 784+8=792 |
| Dense 2 | W2 de 3×8, B2 de 3; logits | 8 → 3 | 24+3=27 |
| Softmax | Exponenciales desplazadas por máximo | 3 → 3 probabilidades | 0 |
| **Total** | Secciones FILTER1/FILTER2/W1/B1/W2/B2 | **Clases: circulo, cruz, triangulo** | **837** |

Cálculo espacial: `(16-3)/1+1=14`, pooling `14/2=7`, flatten `2×7×7=98`. Coincide con SHAPES y los pesos cargados. El test de forward comprueba cada dimensión, la coincidencia con convolve_valid y el orden de flatten. La implementación llamada convolución usa correlación cruzada (sin invertir kernel): convención consistente entre entrenamiento, inferencia y workers.

## 3. MLP, logits y predicción

`a=W1 x+B1`, `h=ReLU(a)`, `z=W2 h+B2`. Cada fila representa una neurona de salida de la capa. `softmax(z)_j = exp(z_j-max(z))/sum_k exp(z_k-max(z))`. El índice de mayor probabilidad selecciona CLASSES; en empate se toma el primer índice. Las probabilidades deben ser finitas, no negativas y sumar aproximadamente uno.

MathTests.test_mlp_reference compara casos conocidos de Dense/ReLU/Softmax sin depender del forward convolucional. Los tests de softmax incluyen logits 1000, -10000 y valores no finitos. Se verifica además que el nombre del archivo no determina la clase: sólo los píxeles.

## 4. Pérdida y defecto corregido

Cross-entropy para clase verdadera y:

`L = (max(z)-z_y) + log(sum_j exp(z_j-max(z)))`.

La fórmula anterior sumaba primero max(z) y restaba z_y al final; con logits iguales a 1e16 devolvía 2.0 en vez de ln(3). La función compartida cross_entropy evita esa cancelación. Calcular desde logits también evita log(0) cuando una probabilidad muy pequeña se redondea a cero: con logits [1000,0,-1000], etiqueta 2, loss=2000 finita.

No se cambió el forward ni el gradiente softmax-cross-entropy. La nueva loss se utiliza en backward, train.metrics y evaluate para mantener una referencia común.

## 5. Backpropagation y gradient checking

- Salida: `dz = p-onehot(y)`, `dW2 = dz h^T`, `dB2 = dz`.
- Oculta: `da = (W2^T dz) * 1[a>0]`, `dW1 = da x^T`, `dB1 = da`.
- Flatten: `dx = W1^T da`, reorganizado por canal/fila.
- Pooling: envía el gradiente a la posición ganadora de cada bloque.
- ReLU convolucional: bloquea gradientes si la convolución es <=0.
- Filtro: suma `delta[r,c] * image[r+i,c+j]` para sus nueve coeficientes, en todos los bloques ganadores que dependen del filtro.

Se adopta ReLU'(0)=0 y el primer ganador ante empates. Los tests analíticos de empates y ceros comprueban esas convenciones sin exigir una derivada central inexistente en puntos no diferenciables.

Gradient checking: `(L(theta+epsilon)-L(theta-epsilon))/(2 epsilon)` frente a derivada analítica, epsilon=1e-5 y tolerancia absoluta 2e-6. Se verifican los **837 parámetros en tres combinaciones de pesos/imagen que cubren las tres etiquetas: 2511 comparaciones**. El test original usa pesos seed=23 e imagen seed=701; los adicionales usan pesos seed=47/89 e imágenes seed=147/189. No basta con observar descenso de loss: estas comparaciones verifican los gradientes directamente.

## 6. Entrenamiento y validación independiente de Adam

Inicialización gaussiana He con seed=20261022; B1=.05 y B2=0. Barajado con seed+1. Configuración completa reproducida: 60 épocas, minibatch 24, learning rate .003, patience=12. El gradiente de cada batch se promedia por su tamaño real y se recorta a norma global máxima 5.

Adam implementado a mano:

`m_t=.9 m_(t-1)+.1 g_t`; `v_t=.999 v_(t-1)+.001 g_t²`;
`mhat=m_t/(1-.9^t)`; `vhat=v_t/(1-.999^t)`;
`theta_t=theta_(t-1)-lr*mhat/(sqrt(vhat)+1e-8)`.

El contador aumenta una vez por minibatch; los momentos se conservan entre batches. Se selecciona el checkpoint con menor cross-entropy de validation. Test no participa en gradientes ni selección.

La confirmación añade un test escalar de **dos pasos** con gradientes controlados: primero 2 y luego -1; también primero 10 (recortado a 5) y luego -1. Compara el peso final con la fórmula cerrada independiente, tolerancia 1e-15. Esto detecta errores de momentos, contador/corrección de sesgo y clipping que el simple descenso de loss podría ocultar. Los gradientes se inyectan sólo en ese test del optimizador; los tests matemáticos de CNN utilizan backward real.

Las pruebas pequeñas verifican reproducibilidad, modificación de todas las secciones, parámetros finitos, descenso de loss, último batch incompleto y selección del checkpoint. El generador de ese fixture no es un conjunto externo de evaluación.

## 7. Dataset, preprocesamiento y fuga de información

geometry-v1 es sintético, generado por distancias geométricas con variaciones de posición, radio, grosor, rotación, intensidad y ruido; se guarda como PGM 16×16. Semillas y balance:

| Split | Semilla | Por clase | Total |
| --- | --- | --- | --- |
| Train | 1729 | 240 | 720 |
| Validation | 2718 | 60 | 180 |
| Test | 31415 | 100 | 300 |

Normalización gris/255; redimensión por centro de celda; RGB por luminancia y alfa contra negro. Manifest y cargador validan etiquetas, dimensiones, conteos y hashes de píxeles. No hay duplicados exactos entre splits. Java/Python coinciden a tolerancia 1e-12 en 13 archivos PNG/PGM/RGBA de referencia.

Todos los splits provienen de la misma familia sintética. La separación impide duplicados exactos, pero no demuestra generalización de dominio ni elimina sesgo del generador. Los nueve ejemplos visibles proceden del test. El test ya ha sido observado; no se presenta como nueva evaluación ciega. El usuario sólo dispone de estos datos: evaluación externa independiente pendiente. DATASET_Y_VALIDACION.md especifica procedencia/permiso, congelación, etiquetado y evaluación recomendada para imágenes nuevas.

## 8. Experimentos y evaluación real

Se conserva como **experimento anterior verificable** la ejecución de dos entrenamientos de 60 épocas documentada en FASE1_REPRODUCCION.json: pesos e historial idénticos entre sí. Las fuentes model.py, train.py y dataset.py conservan en esta revisión exactamente los hashes de ese experimento; por ello no se repitió un entrenamiento de 93 s sólo por añadir metadatos al reporte. El cambio actual en evaluate.py no afecta al optimizador ni a la selección de checkpoints. La revisión recalcula evaluación con pesos oficiales y ejecuta regresiones nuevas.

| Fuente | Train accuracy/loss | Validation accuracy/loss | Test accuracy/loss |
| --- | --- | --- | --- |
| Dos runs previos de fase I | 1.0 / .0001089893962882659 | 1.0 / .00010946370327824087 | 1.0 / .0002303936675979407 |
| Evaluación nueva del modelo oficial | No recalculado en este comando | No recalculado en este comando | 1.0 / .0002303936675979407 |

Matriz test (filas verdaderas/columnas predichas, circulo/cruz/triangulo): `[[100,0,0],[0,100,0],[0,0,100]]`. Accuracy por clase=1.0 para cada clase; se define explícitamente como correctos/ejemplos verdaderos de esa clase, equivalente a recall. Una clase ausente devuelve null, no accuracy inventada.

El evaluador conserva los campos previos y añade model_configuration (forma de entrada, filtros/kernel/stride/padding, pooling, flatten, densas/activaciones y 837 parámetros) y per_class_accuracy, conservando per_class_recall. La CLI identifica split test, semilla, hashes de dataset y pesos. Escribe metrics.json y predictions.csv a salida alternativa, sin modificar model/evaluation oficial.

Se añade un test de métricas con errores deliberados: cuatro ejemplos, predicción siempre circulo, etiquetas [0,1,2,1]; accuracy=.25, loss=ln(3), matriz `[[1,0,0],[2,0,0],[1,0,0]]`. Así se verifica que la matriz y las tasas se calculan correctamente incluso fuera del caso perfecto.

## 9. Interfaces actuales y evolución distribuida

| Función actual | Responsabilidad | Uso futuro / límite |
| --- | --- | --- |
| CNN.trace(pixels) | Forward validado, devuelve tensores | Misma versión inmutable de pesos por operación |
| CNN.predict(pixels) | Inferencia sin modificar pesos | Reutilizada por worker Python; sin clasificador nuevo |
| cross_entropy(logits,label) | Loss estable | Referencia única para métricas/backward |
| loss_and_gradients(weights,image,label) | Loss y gradientes por muestra; no actualiza pesos | Reutilizable en workers de gradientes |
| load_weights / save_weights | Serialización validada | Transporte/checkpoints identificados por hash/versión |
| train(...) | Batches, acumulación, clipping y Adam | Agregación y actualización están todavía dentro del bucle secuencial |

Diseño futuro, **no implementado en esta fase**: acumular sumas de gradientes y sample_count por snapshot/versionId; coordinador rechaza versiones diferentes y duplicados, divide la suma total por el número total de muestras y aplica clipping/Adam una sola vez por paso global. Mantener momentos/contador en un actualizador único. Se podrá extraer agregación y aplicación de Adam a funciones separadas sin reescribir forward/backward; no hay necesidad de introducir ahora un protocolo o entrenamiento multiproceso.

El MLP completo del worker Python utiliza el mismo CNN, sin duplicarlo para IDENTIFY. Los kernels TCP CONV/MLP/DENSE existentes en Java/C# siguen siendo implementaciones por lenguaje necesarias para interoperabilidad, verificadas contra la referencia; esta revisión no agrega otra copia del clasificador.

## 10. Pruebas, evidencia y cierre técnico

Ver FASE1_RESULTADOS.md para comandos, conteos, tiempos y distinción entre evidencia histórica y nueva. Se ejecutan nuevas pruebas Adam/métricas y suite integral para comprobar que los campos añadidos no rompen consumidores existentes. Se conservan las APIs y los formatos TCP; no se modifican workers ni coordinador en esta confirmación.

Los criterios técnicos del adjunto (CNN/MLP funcional, matemáticas, gradientes, entrenamiento, métricas reales, dataset documentado, compatibilidad y revisión) se comprueban mediante código, tests y artefactos identificados. La calificación/cumplimiento completo del enunciado NO se acredita por ellos: falta el PDF/aclaración docente. El plan ampliado conserva pendiente la evaluación externa. El cierre técnico debe leerse junto con esas limitaciones, sin renombrar datos sintéticos como reales.

## 11. Explicación Feynman

Imagina que los dos filtros miran la imagen con una ventanita de 3×3. Cada uno produce un mapa de respuestas. ReLU descarta respuestas negativas y pooling guarda la más fuerte de cada cuadrado pequeño. Flatten ordena esos resúmenes en una lista. Ocho neuronas los combinan y tres salidas asignan probabilidades a las figuras.

Al entrenar, la etiqueta indica cuál salida debió ganar. Backpropagation calcula cuánto influyó cada peso en el error; Adam usa esas pendientes y su historial para ajustar los pesos. Gradient checking mueve un peso un poquito hacia cada lado y comprueba que el cambio de error coincide con la pendiente calculada.
