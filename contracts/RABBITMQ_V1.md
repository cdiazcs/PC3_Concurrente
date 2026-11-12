# RabbitMQ V1 — contratos implementados

Mensajes UTF-8 JSON, schemaVersion numérico 1, idSolicitud único por operación,
idCliente separado, modeloDestino=A y timestamp ISO-8601 UTC. correlation_id y
message_id AMQP son idSolicitud. Los cuerpos tienen límite de 2 MB. Los
consumidores validan versión/identidad y no ejecutan SQL/CNN ante un mensaje
inválido. No se incluyen credenciales ni direcciones en mensajes.

| Solicitud | Respuesta | Servicio |
|---|---|---|
| cola_validacion | cola_resultados_validacion | MariaDB, validación |
| cola_modeloA | cola_resultadosA | CNN Python |
| cola_persistencia | cola_resultados_bd | PostgreSQL, persistencia |

Las variables QUEUE_VALIDATION/QUEUE_VALIDATION_RESULTS,
IA_REQUEST_QUEUE/IA_RESULT_QUEUE y QUEUE_PERSISTENCE/QUEUE_PERSISTENCE_RESULTS
permiten aislar el mismo contrato por instancia. Mantener un backend consumidor
por pareja de colas de respuesta; no escalar backends compartiendo estas colas.
Modelo B no está entrenado ni implementado; no se declara funcional.

## Validación

```json
{"schemaVersion":1,"tipo":"VALIDAR_CLIENTE","idSolicitud":"req-1","idCliente":"cliente-demo-01","modeloDestino":"A","timestamp":"2026-11-12T00:00:00Z","payload":{}}
```

Respuesta RESULTADO_VALIDACION conserva IDs/modelo y añade estado=VALIDADA,
payload.aprobado booleano y payload.motivo. ACTIVO se aprueba; BLOQUEADO e
inexistente se rechazan. El rechazo NO ejecuta CNN. Un error de mensaje/SQL usa
estado=ERROR y error textual. Duplicado del mismo ID/cliente devuelve el dictamen
original; otro cliente con el mismo ID produce idempotency_conflict.
Nunca se registra automáticamente a un cliente desconocido, ni siquiera bench-*.

## Inferencia

Backend publica tipo=INFERENCIA e intento=1. El payload contiene:

```json
{"modo":"SEQUENTIAL","imagen":{"formato":"VECTOR_NORMALIZADO","ancho":16,"alto":16,"valores":[0.0,0.5,1.0]}}
```

El ejemplo abrevia valores: son exactamente 256 números finitos en [0,1] por
filas. No son Base64. Python acepta como entrada histórica el CSV llamado
imagenBase64 de INFERENCIA, pero Java ya no lo emite. El otro perfil existente,
CLASIFICAR_IMAGEN, sí contiene Base64 real en payload.imagenBase64 y mimeType.

Python responde tipo=RESULTADO_CLASIFICACION, estado=COMPLETADA, error=null,
payload.etiqueta, probabilidad, probabilidades y duracionMs. Para INFERENCIA,
probabilidades es lista en orden circulo/cruz/triangulo; el perfil de archivo
CLASIFICAR_IMAGEN conserva el mapa histórico. Errores usan estado=ERROR.
Java verifica versión, correlación, cliente/modelo y validez de probabilidades.

## Persistencia

Tipo GUARDAR_RESULTADO, con envelope común y payload:

```json
{"etiqueta":"circulo","probabilidad":0.8,"probabilidades":[0.8,0.1,0.1],"duracionMs":12.5,"imagen":{"nombre":"req-1","mimeType":"image/png","ancho":16,"alto":16,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}
```

El servicio PostgreSQL confirma tipo=RESULTADO_PERSISTENCIA, estado=PERSISTIDA,
los mismos IDs, timestamp y payload={}. Si falla, estado=ERROR y error textual.
Backend no devuelve RESULT hasta recibir PERSISTIDA. Un timeout de persistencia
se comunica como persistence_pending: pudo haber COMMIT y confirmación tardía.

La transacción guarda solicitud/metadatos, clasificación/probabilidades,
estado COMPLETADA, historial y outbox_persistencia. La confirmación se almacena
en ese outbox antes del COMMIT. ACK del input solo sigue a publicación confirmada.
Si el proceso cae entre COMMIT y publicación, el input durable no confirmado se
reentrega; se verifica huella canónica, se lee outbox y se republica sin repetir
los efectos SQL. El orden de claves JSON y la duración recalculada no cambian
la identidad; cambiar cliente/imagen/resultado produce conflicto. No hay una
promesa exactly-once de mensajes: pueden recibirse confirmaciones duplicadas.

## ACK, fallos y reintentos

Colas durables, mensajes persistentes y publisher confirms. MariaDB reutiliza
el transporte IA con conexión/canal por hilo: prefetch=1, retries quorum con TTL
y DLQ `<cola>.errores`; hasta tres entregas AMQP y hasta tres intentos SQL para
carreras/deadlock por entrega. Header x-db-attempt acota reintentos. PostgreSQL
republica hasta tres veces errores de conexión/serialización/deadlock; errores
permanentes van a su respuesta ERROR y `<cola>.errores`.
Ante publicación no confirmada no se da ACK. El worker PostgreSQL sale con error
si pierde la conexión de publicación y debe reiniciarse; la reentrega recupera
el outbox. El worker MariaDB reconecta con backoff acotado. El cuerpo de imagen
no se guarda en logs/DLQ, solo identificación y error saneado.

## LOCAL, FULL y DISTRIBUTED

SYSTEM_PIPELINE=LEGACY conserva las pruebas Fase I. FULL exige RabbitMQ y el
flujo BD2 -> IA -> BD1; no permite saltarlo usando IDENTIFY legado.
La configuración física DISTRIBUTED no obliga a partir matemáticamente la CNN:
SEQUENTIAL también cruza equipos por RabbitMQ. Para inferencia matemática
DISTRIBUTED del worker IA, configurar un coordinador TCP LEGACY privado separado
(por ejemplo puerto 9001) mediante IA_COORDINATOR_HOST/PORT. No apuntarlo al
puerto FULL: ese puerto rechaza IDENTIFY sin identidad para impedir bypass.
