# Propuesta de contrato RabbitMQ — pendientes de implementar

RabbitMQ no está conectado a ningún consumidor/publicador en este `main` de partida.

| Cola propuesta | Publicador | Consumidor | Objetivo |
| --- | --- | --- | --- |
| `cola_modeloA` | Backend | nodo IA A | solicitudes IA |
| `cola_modeloB` | Backend | nodo IA B | opción modelo B; confirmar docente |
| `cola_resultadosA` | IA A | Backend / orquestación | resultados de inferencia |
| `cola_resultadosB` | IA B | Backend / orquestación | resultados modelo B, si se implementa |
| `cola_validacion` | Backend | BD2 | solicitud de validación |
| `cola_resultados_validacion` | BD2 | Backend | validación realizada |
| `cola_persistencia` | Backend / IA | BD1 | resultado/historial |
| `cola_resultados_bd` | BD1 | Backend | confirmación de persistencia |
| `cola_control_heartbeat` | nodos | monitor | salud |
| `cola_logs` | nodos | observador | trazabilidad |

Se recomienda JSON UTF-8 en RabbitMQ con `schemaVersion=1`, `idSolicitud`, `idCliente`, `timestamp` UTC ISO8601, `tipo`, `modeloDestino`, `imagenBase64` (o referencia segura), `intento` y `payload` específico. Ver `contracts/examples/`.

Reglas a implementar: colas durables, mensajes persistentes si procede, acknowledge tras operación, idempotencia por `idSolicitud`, reintentos acotados, TTL/DLQ acordados, validación de tamaño y formatos de imagen y no registrar contenido sensible de imágenes en logs. **El propio protocolo AMQP utiliza el cliente RabbitMQ permitido, no WebSocket.**
