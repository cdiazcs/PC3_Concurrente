# Dataset y protocolo de validación IA

## Procedencia y alcance

El dataset `model/data/geometry-v1.zip` se genera localmente con `cnn_python/dataset.py`; no se descargó de un tercero. El código dibuja círculos, cruces ortogonales y triángulos de contorno mediante distancias geométricas. No hay datos personales. La autoría/licencia jurídica del repositorio debe documentarla el equipo; esta descripción técnica no concede ni presume una licencia. La aceptación de datos sintéticos por el profesor sigue pendiente de contrastar con el PDF oficial.

El usuario confirmó que sólo dispone de este dataset sintético. **No existe un conjunto externo documentado y no se acredita generalización externa.** Semillas diferentes del mismo generador son particiones independientes de esa familia, no dominios externos.

## Generación y preprocesamiento

- Imagen gris 16×16, fondo oscuro y figura clara; muestras enteras 0..255 en PGM P5.
- Centro desplazado hasta ±1.25 píxeles; radio 3.7..5.3; grosor .9..1.7; rotación ±.16 radianes.
- Intensidad de figura .8..1, fondo 0...06, ruido gaussiano .015...07; probabilidad .002 de sustituir un píxel por ruido uniforme.
- Antialias por cuatro submuestras por píxel; intensidades recortadas y redondeadas a 8 bits.
- Normalización: gris/255. Las imágenes mayores se remuestrean tomando el centro de cada celda de una rejilla 16×16. RGB usa luminancia .299R+.587G+.114B; alfa se aplica contra negro.
- Las pruebas de fase 1 comparan los 256 valores Java/Python en nueve ejemplos y cuatro fixtures (PNG gris redimensionado, PGM P2/P5 y RGBA). Android/Web aún requieren verificar sus implementaciones futuras.

| Partición | Semilla | Por clase | Total | Uso |
| --- | --- | --- | --- | --- |
| train | 1729 | 240 | 720 | Gradientes y actualización |
| validation | 2718 | 60 | 180 | Selección del checkpoint / early stopping |
| test | 31415 | 100 | 300 | Evaluación posterior, sin gradientes |

El manifest registra clases, dimensiones, semillas, etiquetas, rutas y SHA256 de píxeles. El cargador comprueba hashes y conteos; las pruebas verifican no solapamiento exacto entre las tres particiones. Las nueve imágenes de model/examples son extraídas del test: no deben contarse como datos externos.

## Cómo evaluar sin contaminar la selección

1. Fijar arquitectura, semillas, hiperparámetros y particiones antes de observar el test.
2. Entrenar exclusivamente con train; comparar checkpoints exclusivamente con validation.
3. Seleccionar el mínimo de cross-entropy de validación. Adam utiliza medias del minibatch y clipping global; test no participa en train.main.
4. Evaluar el checkpoint congelado con test y publicar accuracy, cross-entropy, matriz de confusión y recall por clase. El test sintético ya fue observado en fases anteriores; no es una nueva prueba ciega.
5. Para cualquier cambio posterior basado en resultados de test, declarar ese uso y reservar otro conjunto intacto para la evaluación final.

`minimum_accuracy=.85` es un objetivo heredado del software, no un umbral oficial confirmado. Tener 100% en el test sintético no prueba que fotografías o dibujos manuales se clasifiquen correctamente.

## Pendiente: conjunto externo

Reunir imágenes independientes del generador actual con etiqueta, fuente/autor, licencia o permiso, fecha, identificador y checksum de archivo y píxeles. Congelar su selección antes de evaluar, revisar duplicados y casi duplicados contra train/validation/test, y acordar significado de las clases (por ejemplo cruz ortogonal frente a X), polaridad y tratamiento de fondo. Fotografías con perspectiva/fondos/texturas y trazos manuales pueden cambiar radicalmente el dominio. No incorporar estas imágenes al entrenamiento y seguir llamándolas test externo.

Publicar separadamente el tamaño y balance por clase, condiciones de captura, preprocesamiento, accuracy, loss y confusión externos, incluso si son peores. No fijar un resultado ni fabricar imágenes como si fueran datos externos observados. Su procedencia y uso académico deben validarse con el profesor.

## Reproducción y trazabilidad

La regeneración en Ubuntu/Python 3.14 reconstruye exactamente el contenido descomprimido del ZIP oficial; el contenedor ZIP no es idéntico en bytes. No usar exclusivamente el hash del ZIP como criterio de igualdad de datos entre plataformas: comparar también nombres, manifest y contenido de cada entrada. El hash del ZIP sigue siendo obligatorio para identificar el artefacto exacto usado al entrenar.

Los hashes de fuentes del informe heredado no coinciden con las fuentes que había al iniciar fase 1, ni al probar LF/CRLF y BOM. No se ha demostrado la causa. Se conserva el informe original y se crea evidencia nueva que identifica las fuentes actuales; no se sustituyen hashes antiguos para aparentar una reproducción histórica.

Detalle del contenedor ZIP: las 1201 entradas difieren únicamente en `create_system` (0 en el archivo heredado, 3 en Linux). Se comprobó en memoria que normalizar sólo ese byte del directorio central produce exactamente los bytes originales. No se modificó ninguno de los ZIP en disco. Así, la diferencia de hash del dataset queda explicada por metadatos de plataforma, no por imágenes distintas.
