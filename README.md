# Fase II — bases de datos y clientes

Trabajo exclusivamente en `integration`, sin commit/push/merge automáticos.
El flujo BD2 MariaDB → CNN Python → BD1 PostgreSQL está implementado por RabbitMQ
con validación previa y confirmación transaccional antes de responder éxito.

- [Arquitectura, contratos y comandos por integrante](docs/integration/FASE2_SISTEMA_COMPLETO.md)
- [Resultados y pendientes reales de Fase II](docs/integration/FASE2_RESULTADOS.md)
- [Android Kotlin: proyecto y contrato JVM; APK pendiente](clients/android/README.md)

Configuración: config/phase2.local.example.env o phase2.distributed.example.env.
Pruebas sin servicios: `python scripts/unit_tests.py`. Integración completa solo
en bases pc3_test_* propias: `python scripts/phase2_integration.py`.
No se declara APK Android, Windows ni despliegue distribuido físico verificados.

---

# Fase I — integración multiplataforma

Estado y evidencia actual: [resultados](docs/integration/FASE1_RESULTADOS.md).
Trabajar exclusivamente sobre `integration`, sin crear ramas ni realizar
commit/push/merge/rebase automáticamente; no usar instrucciones
históricas de inicialización Git sobre este repositorio existente.

- [Instalación por integrante y SO](docs/INSTALACION_EQUIPO.md)
- [Compilación y ejecución local](docs/EJECUCION_LOCAL.md)
- [Tres nodos y Tailscale](docs/EJECUCION_DISTRIBUIDA.md)
- [Cambios y alcance de Fase I](docs/integration/FASE1_MULTIPLATAFORMA.md)

Ubuntu: `bash scripts/check_integration.sh`; Windows:
`./scripts/Check-Integration.ps1`. Agregar `--tcp` / `-Tcp` para sockets locales.
Las pruebas de broker real son opt-in: `--rabbit` / `-Rabbit`, con credenciales
en el entorno. Una prueba omitida se informa como NO VERIFICADA.

---

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
