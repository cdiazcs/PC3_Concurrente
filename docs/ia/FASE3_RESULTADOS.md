# Fase III — Resultados reales

Fecha: 2026-11-12 (America/Lima). Rama feature/ai-distributed. **Nodo IA y flujo AMQP real verificados en localhost; integración del backend/BD del equipo pendiente.** No se inicia fase IV.

## 1. Entorno y alcance

Python 3.14.4, Pika 1.3.2 instalado sólo en /tmp/pc3-amqp-deps, RabbitMQ 4.4.0/Erlang ya instalados; JDK 21.0.13 y SDK .NET 8 temporal para regresiones. CNN sin dependencias IA. El broker de pruebas se inició como proceso independiente, nodo pc3_ia_isolated@localhost, AMQP ligado a 127.0.0.1 y puertos propios. Configuración, datos, logs y credenciales aleatorias (archivos 0600) bajo /tmp/pc3-rabbit-local; no se incorporan a Git ni se imprimen credenciales.

El equipo ya tenía otra instancia RabbitMQ. Un intento de consultar versión con rabbitmq-server --version intentó iniciar y falló; el primer arranque aislado chocó con el puerto de distribución 25672. Se corrigió especificando RABBITMQ_DIST_PORT propio y ubicaciones privadas. No se detuvo ni reconfiguró el broker ajeno. Los intentos fallidos no se cuentan como pruebas aprobadas.

El backend AMQP existe en el commit 8901cfb de otra referencia, no en esta rama. Sólo se inspeccionó su DTO/contrato y se probaron sus mensajes reales con productor aislado, tal como autorizó el usuario. No se ejecutó PostgreSQL ni se declara validado backend→BD→cliente.

## 2. Comandos ejecutados

| Comando / operación | Resultado |
| --- | --- |
| git status --short / branch --show-current / log | feature/ai-distributed, base 798fee1; cambios anteriores conservados |
| `git show 8901cfb:contracts/RABBITMQ_V1.md` y DTO/manager backend | Diferencia CSV/Base64 y respuesta lista/objeto identificada; sin merge ni cambios al contrato |
| `python3 -m pip install --target /tmp/pc3-amqp-deps --no-cache-dir pika==1.3.2` | Instalación aislada correcta; sin paquetes globales |
| Pruebas unitarias iniciales `python3 -m unittest discover -s tests -p 'test_rabbit_*.py' -v` antes de añadir broker tests | 12/12 OK; simuladas, no evidencia de broker |
| Integración inicial contra broker real | 5/5 OK; perfiles, duplicados, errores, TTL, 50 mensajes y reinicio del proceso |
| Integración con controles reales añadidos | 7/7 OK en 6.816 s; desconexión y stop_app/start_app |
| `python3 -m unittest discover -s tests -p 'test_rabbit_*.py' -v` sobre topología final | **23/23 OK**, 15.516 s; incluye 14 unitarias y 9 casos reales (8 de integración/control y 1 AMQP→coordinador→tres lenguajes) |
| `python3 scripts/validate_phase2.py --dotnet-dir /tmp/pc3-dotnet8 --output build/phase3-final` con opt-in broker/control aislado | **126 casos: 125 aprobados, 1 omitido, 0 fallos/errores**; exit 0; 121.92 s runner / 121.758 s unittest |
| `python3 scripts/probe_rabbit_ia.py --requests 1 10 50 100 1000 --output build/phase3-load-c1` | 1161/1161, 0 errores, un consumidor |
| Mismo probe, output phase3-load-c2 / IA_WORKER_CONCURRENCY=2 | 1161/1161, 0 errores |
| Mismo probe, output phase3-load-c4 / IA_WORKER_CONCURRENCY=4 | 1161/1161, 0 errores |
| Demostración adicional id=phase3-demo-real | Resultado real circulo, duracionMs=1.1536570000316715; correlación y delivery_mode=2 |
| Integridad / git diff --check | Artefactos oficiales y fuentes de campaña conservados; sin errores de espacios |

Las invocaciones usan PYTHONPATH=/tmp/pc3-amqp-deps y PYTHONDONTWRITEBYTECODE=1 en esta sesión. Las credenciales se inyectaron desde el archivo privado temporal hacia el entorno de los hijos; no forman parte de los comandos registrados. La suite integral se reutiliza como regresión de fases I/II/III, no añade funcionalidades de fase II.

La única omisión es la prueba previa que requiere seis núcleos físicos disjuntos para la emulación paralelo distribuida; el equipo dispone de cuatro. No es una prueba aprobada de RabbitMQ ni una regresión nueva.

## 3. Detalle de campaña final

| Grupo | Aprobadas | Omitidas |
| --- | --- | --- |
| CNN fases I / ampliación | 33 | 0 |
| Protocolo/cliente local | 18 | 0 |
| IDENTIFY | 18 | 0 |
| Chunks/coordinador | 15 | 0 |
| Límites/deadlines/frame grande | 5 | 0 |
| Desktop | 7 | 0 |
| Benchmark existente | 6 | 1 |
| Mensajes/cache/config IA | 7 | 0 |
| Ack/publicaciones/retry simulados | 7 | 0 |
| Integración broker real, control y recuperación | 8 | 0 |
| AMQP→coordinador Java→Java/Python/C# | 1 | 0 |
| **Total** | **125** | **1** |

Las pruebas reales usan colas con prefijos UUID y las eliminan al finalizar. Los controles close_all_user_connections y stop_app/start_app se habilitan exclusivamente para el nodo de pruebas aislado, nunca automáticamente contra un broker ajeno. Sin PC3_RABBIT_INTEGRATION=1 los tests reales se omiten explícitamente, no se convierten en aprobados mediante mocks.

## 4. Casos demostrados

- Base64 PNG y CSV backend producen las probabilidades de la referencia secuencial; correlación conservada y mensajes persistentes.
- JSON/IDs/modelo/correlación/Base64/MIME/tamaños/píxeles inválidos se rechazan con errores controlados.
- Resultados sólo ack después de publicación confirmada. Las pruebas con canal simulado fuerzan fallo de publicación de resultado y de error: ninguno confirma la entrada.
- Duplicados simultáneos se coalescen; duplicados terminados reutilizan exactamente el resultado; mismo ID con cliente/contenido distinto da idempotency_conflict.
- Error temporal de coordinador no configurado genera dos eventos REINTENTO y termina con ERROR al tercer intento. Se utiliza TTL real y DLX de la cola privada quorum en la configuración final.
- Error inválido sin ID sólo genera diagnóstico sanitizado, sin copiar la imagen a logs/DLQ.
- Tres consumidores procesan 50 IDs reales distintos sin mezcla; las cargas amplían a 1/2/4 consumidores.
- El consumidor recupera entrada durable tras reiniciar su proceso; también reconecta tras cierre de conexiones por el broker y tras stop_app/start_app del broker aislado.
- Heartbeat de dominio y log de conexión se publican en sus colas opcionales reales.
- Un mensaje AMQP DISTRIBUTED usa CONFIG/hash + IDENTIFY del coordinador existente y genera tareas reales en los tres lenguajes, equivalentes a Python dentro de 1e-8. Todo en localhost, no prueba de tres máquinas.

No se probaron pérdida permanente de discos, caída de un cluster quorum real, red entre equipos, Windows ni el flujo del backend con PostgreSQL. Se mantienen como NO VERIFICADOS.

## 5. Mensaje de demostración real

`evidencias/FASE3_DEMO.json` conserva solicitud sanitizada con archivo fuente/hash, resultado realmente recibido, correlation_id y delivery_mode. Se utilizó model/examples/circulo-0.png, procedente del conjunto test. La imagen Base64 se omite de la evidencia para no duplicar/loguear contenido de imágenes; no se reemplaza por datos inventados.

Respuesta observada: idSolicitud=phase3-demo-real, estado=COMPLETADA, etiqueta=circulo, probabilidades del modelo oficial, duracionMs=1.1536570000316715. Ese tiempo es de inferencia local, no latencia de cliente. La respuesta incluye timestamp UTC y SHA256 de los pesos oficiales.

## 6. Carga preliminar AMQP real

Tres procesos de consumidor configurados **por experimentos separados**: uno con 1 hilo/conexión, otro con 2 y otro con 4. Un proceso productor/consumidor de resultados por experimento; RabbitMQ aislado como proceso broker. No hay nodos físicos distintos ni inferencia Python multiproceso en estos experimentos. Prefetch=1 por consumidor; ventana de productor=32 mensajes; ambos perfiles alternados y nueve imágenes test de ejemplo, no 3483 imágenes independientes.

Cada fila es una medición, sin repeticiones estadísticas; no se comparan como benchmark definitivo. Tiempo cliente incluye publicación confirmada, espera de cola/inferencia/publicación de resultado, polling e instrumentación queue.declare. El pico observado sólo cuenta mensajes listos, no unacked.

| Consumidores | Solicitudes | Correctas/errores | Media ms | p95 ms | Throughput req/s | Total s | Pico ready observado |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 1/0 | 7.79 | 7.79 | 120.81 | .0083 | 0 |
| 1 | 10 | 10/0 | 14.74 | 26.03 | 310.41 | .0322 | 7 |
| 1 | 50 | 50/0 | 63.01 | 103.14 | 306.33 | .1632 | 30 |
| 1 | 100 | 100/0 | 82.81 | 114.27 | 308.38 | .3243 | 31 |
| 1 | 1000 | 1000/0 | 119.47 | 133.20 | 261.40 | 3.8255 | 31 |
| 2 | 1 | 1/0 | 8.51 | 8.51 | 109.75 | .0091 | 0 |
| 2 | 10 | 10/0 | 13.84 | 20.53 | 351.31 | .0285 | 6 |
| 2 | 50 | 50/0 | 53.97 | 85.66 | 359.62 | .1390 | 30 |
| 2 | 100 | 100/0 | 71.71 | 92.86 | 356.95 | .2801 | 30 |
| 2 | 1000 | 1000/0 | 99.97 | 115.59 | 311.76 | 3.2076 | 31 |
| 4 | 1 | 1/0 | 9.00 | 9.00 | 104.51 | .0096 | 0 |
| 4 | 10 | 10/0 | 13.75 | 22.82 | 354.59 | .0282 | 6 |
| 4 | 50 | 50/0 | 53.94 | 85.06 | 356.54 | .1402 | 27 |
| 4 | 100 | 100/0 | 79.88 | 106.49 | 326.48 | .3063 | 29 |
| 4 | 1000 | 1000/0 | 104.02 | 131.30 | 299.58 | 3.3380 | 30 |

**Total de carga: 3483 enviadas/recibidas/correctas, 0 fallidas**. Los mensajes de tests y demo son adicionales, no se mezclan en ese total. En cada carga se comprobó consumer_count=concurrencia configurada, correlación, finitud/normalización/equivalencia de probabilidades y versión de pesos.

No se miden mensajes unacked ni tasas internas de RabbitMQ: management API no habilitada en el broker aislado. No se presenta el throughput del cliente como tasa interna del broker. Tampoco es la prueba integral de 1000 transacciones desde Android/Desktop/Web con BD. Más consumidores no garantizan mejora, especialmente con GIL y coste de confirmaciones/I/O: cuatro no superaron a dos en el lote de 1000 observado.

## 7. Evidencia conservada

- evidencias/FASE3_PRUEBAS.json: campaña integral final con resultados por caso, versiones, hashes y límites; añade hashes del probe, requisitos AMQP y ejemplo de entorno sin secretos.
- evidencias/FASE3_CARGA.json: las 15 mediciones reales/configuraciones públicas y hash de cada CSV, sin passwords.
- evidencias/FASE3_DEMO.json: ejemplo de resultado real/correlación/tiempo y solicitud sanitizada.
- build/phase3-final/: log completo y summary.json. build/phase3-regression/ conserva la campaña anterior al refuerzo de la cola retry; no se presenta como la topología final.
- build/phase3-load-c1/c2/c4/: CSV por solicitud, eventos JSONL, logs y summary.json. Las colas temporales se eliminaron y los consumidores se detuvieron.
- build/rabbit-integration-*/ y build/stage0-*: logs/compilación/trazas de las pruebas.
- /tmp/pc3-rabbit-local: configuración privada y datos de broker aislado, intentos fallidos y logs adicionales; no versionados. El broker de prueba se detiene al finalizar, sin tocar la instancia ajena.

Artefactos bajo model/ conservan hashes oficiales. Ningún binario nuevo ni archivo .env con secretos se incorpora al repositorio.

## 8. Reproducir

1. Usar un RabbitMQ de pruebas y usuario/vhost/permisos propios. Instalar Pika en un entorno virtual según FASE3_RABBITMQ.md y exportar RABBITMQ_*.
2. Unitarias sin broker: `python -m unittest discover -s tests -p 'test_rabbit_messages.py' -v` y patrón test_rabbit_worker.py.
3. Broker real: activar PC3_RABBIT_INTEGRATION=1 y ejecutar patrón test_rabbit_*.py. El puente distribuido requiere JDK/.NET además de Pika.
4. Las pruebas de control sólo se habilitan con PC3_RABBIT_ALLOW_CONTROL=1, PC3_RABBIT_CTL y PC3_RABBIT_NODE, y credencial Erlang configurada **para un nodo aislado propio**. Sin esos valores se omiten los dos casos de control; no se debe habilitar sobre usuario/broker compartido.
5. Carga: `python scripts/probe_rabbit_ia.py --requests 1 10 50 100 1000 --output build/nueva-carga`. IA_WORKER_CONCURRENCY fija consumidores. La salida debe ser nueva. El probe inicia/detiene su nodo IA, declara/elimina sólo colas UUID propias y no inicia ni reconfigura el broker.

No hace falta habilitar controles Erlang para usar el consumidor o el probe normales. Configuración Windows/Ubuntu y detención con Ctrl+C están documentadas en FASE3_RABBITMQ.md. Windows sigue NO VERIFICADO en esta sesión.

## 9. Cierre y dependencias de equipo

**Implementación del nodo IA y flujo RabbitMQ real verificados localmente. Cierre integral con backend/BD pendiente.** Se satisface el comportamiento local de consumo, validación, CNN, respuestas, confirms/ack, retries, duplicados, concurrencia, recuperación, métricas y regresiones. No se declara cumplida la arquitectura PC3 completa ni la interpretación docente sin PDF.

Coordinar con integrante 1: perfiles/estado/lista de probabilidades, colas auxiliares quorum y feature flags, permisos/vhost/TLS, control/logs, idempotencia durable del backend/BD y timeout global. Su espera de 25 s no cubre necesariamente tres intentos RPC de 10 s más TTL y publicaciones; alinear presupuestos antes de integrar. Integrante 3 mantiene clientes y validación BD2.

Rama feature/ai-distributed; sin commit, push, merge, rebase ni PR. Commit sugerido después de revisión: `feat: integrar nodo IA con RabbitMQ y pruebas reales`. Revisar y añadir únicamente workers/python/rabbit_*.py, ia_service.py, requirements-amqp.txt, .env.example, tests/test_rabbit_*.py, scripts/probe_rabbit_ia.py y docs/evidencias de fase III; los cambios anteriores de CNN/workers TCP permanecen pendientes por separado.
