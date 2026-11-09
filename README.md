# OpenAI Cubes — PC3 2026-II | Main de partida

**Curso:** CC4P1 Programación Concurrente y Distribuida — UNI.

Este repositorio conserva el núcleo de `OpenAICubesCodigo.zip` de la etapa anterior y añade una **base común de trabajo para PC3**. **No se declara terminada la PC3**: el camino con RabbitMQ, PostgreSQL/MariaDB, Android y Web todavía debe desarrollarse e integrarse, y la distribución real en máquinas/SO diferentes debe demostrarse.

## Con qué se inicia

- CNN + MLP implementada con Python estándar, dataset de figuras sintéticas y pesos entrenados.
- `server-java/`: `CentralServer` y coordinador `DistributedCnn` vía sockets TCP.
- `workers/`: workers Java, Python y C# (.NET 8) para micro-chunks de inferencia.
- `clients-java/` y `frontend-java/`: cliente CLI y cliente Desktop Swing.
- `benchmarks/` y `tests/`: herramientas de medición y pruebas heredadas.
- `contracts/`, `databases/`, `docs/`: contratos, esquema inicial SQL y planificación de integración PC3.
- `clients/android/`, `clients/web/`, `messaging/`, `web-server/`: espacios de trabajo asignados; **no son aplicaciones finales**.

## Acordar antes de empezar

1. Revisar [responsabilidades y GitHub Flow sin develop](docs/EQUIPO_Y_RAMAS.md).
2. Revisar [arquitectura actual y objetivo](docs/ARQUITECTURA_PC3.md).
3. Congelar el [protocolo heredado TCP](contracts/PROTOCOLO_TCP_V1.md) y acordar los [mensajes RabbitMQ previstos](contracts/RABBITMQ_V1.md).
4. Consultar al profesor dos discrepancias del PDF: *exactamente 2 BD* frente a *BD1/BD2/BD3*, y *un modelo por grupo* frente a colas A/B y dos modelos; ver [matriz de requisitos](docs/MATRIZ_PC3.md).

## Comprobar rápidamente el código existente

Desde la carpeta `OpenAICubes/`:

```bash
python -m cnn_python.predict model/examples/circulo-0.png
python -m unittest discover -s tests -p 'test_cnn.py' -v
python scripts/check_main.py
python scripts/smoke_main.py
```

`check_main.py` valida archivos principales, prueba inferencia local, compila Java si hay `javac` y comprueba la fuente C#; si no está instalado `.NET`, informa el límite (no proclama una prueba C# aprobada).

Para compilar Java de forma manual:

```bash
mkdir -p build
javac -encoding UTF-8 -d build clients-java/*.java frontend-java/*.java server-java/*.java workers/java/*.java
```

En Windows, ejecutar `powershell -ExecutionPolicy Bypass -File scripts/Build-Java.ps1` (JDK disponible en PATH).

### Demostración heredada (sin RabbitMQ)

Iniciar en terminales diferentes:

```bash
python workers/python/worker.py 9102
java -cp build CentralServer 9000 127.0.0.1:9102
java -cp build ClientCli 127.0.0.1 9000 IDENTIFY model/examples/circulo-0.png demo1 SEQUENTIAL
```

El modo `SEQUENTIAL` funciona con worker Python. Para las operaciones `DISTRIBUTED` se pueden añadir los workers Java y C# en los puertos configurados. La interfaz Java puede lanzarse con `java -cp build OpenAICubesGUI 127.0.0.1 9000` en un entorno gráfico. **Este camino es el legado, no el diseño definitivo exigido con RabbitMQ.**

## Organización del trabajo

| Integrante | Rama(s) a abrir desde `main` | Carpeta principal |
| --- | --- | --- |
| 1 | `feature/backend-rabbitmq`, después `feature/bd1-postgresql` | `server-java/`, `messaging/`, `databases/postgresql/` |
| 2 | `feature/ai-distributed`, después `feature/performance` | `cnn_python/`, `workers/`, `benchmarks/` |
| 3 | `feature/clients`, después `feature/bd2-mariadb` | `clients/`, `frontend-java/`, `web-server/`, `databases/mariadb/` |

**Regla:** nunca se trabaja directo sobre `main`, ninguna rama `develop`. Usar PRs breves con revisión cruzada y pruebas. Consultar `docs/EQUIPO_Y_RAMAS.md`.

## Antes de entregar a UNIVIRTUAL

Este ZIP es **base de desarrollo/GitHub**, NO el ZIP final de evaluación: conserva README, `.github/`, archivos `.properties` y documentos `.md` de coordinación. La rúbrica exige un paquete específico de código fuente, SQL, dataset y PDF. Preparar el ZIP final por separado y verificar restricciones con el profesor.

## Procedencia

El núcleo del código, dataset, pesos y tests se reutiliza del archivo original entregado por el equipo. Los documentos, esquemas SQL y estructura de ramas de esta versión son nuevos y no significan que las integraciones estén hechas.
