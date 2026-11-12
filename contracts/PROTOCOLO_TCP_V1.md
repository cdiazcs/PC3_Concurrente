# Protocolo TCP real del código original (NO confundir con RabbitMQ)

- Transporte: TCP `Socket` propio del SDK, con **4 bytes big-endian** de longitud + cuerpo UTF-8.
- Límite en servidores/workers actuales: **2,000,000 bytes** por mensaje.
- El cuerpo actual es texto `|`-delimitado, no JSON.
- Ejemplo: `PING|req123` → `PONG|req123`.
- Inferencia: `IDENTIFY|req123|v1,v2,...,v256|SEQUENTIAL` o `DISTRIBUTED`, con cada valor `0..1`.
- Resultado: `RESULT|req123|1|3|pCirculo,pCruz,pTriangulo`.
- Error: `ERROR|req123|codigo`.
- Algunas tareas de worker: `CONV`, `MLP`, `JOB`; ver clases existentes y pruebas (`tests/test_protocol.py`).

**Importante:** la PC3 plantea `imagen` en Base64. Se propone contrato v2 con conversión en la frontera que mantenga temporalmente compatibilidad v1. No cambiar el formato del protocolo hasta la aprobación grupal.

## Extensión Fase II compatible: IDENTIFY2

La entrada nueva es aditiva; framing, respuestas y todas las operaciones V1
permanecen iguales. El usuario autorizó esta extensión al solicitar Fase II.

```text
IDENTIFY2|idSolicitud|idCliente|SEQUENTIAL|image/png|Base64Real
```

Se permite SEQUENTIAL/DISTRIBUTED y PNG/JPEG/PGM (MIME
image/png, image/jpeg, image/x-portable-graymap). ID de operación y cliente son
ASCII `[A-Za-z0-9_.:-]{1,128}`. Archivo máximo 1 MB, dimensiones hasta 4 megapíxeles,
frame hasta 2 MB. El backend comprueba firma y decodifica la imagen utilizando
el preprocesamiento compartido Java probado contra Python; no confía en un
vector enviado por el navegador. Guarda hash SHA-256 del archivo recibido.

Respuesta exitosa solo tras persistencia: RESULT|idSolicitud|1|3|p0,p1,p2.
Errores: client_rejected, validation_timeout/failed, inference_timeout/failed,
persistence_pending/failed, idempotency_conflict e invalid_image/identify2.
En modo FULL, IDENTIFY V1 devuelve client_identity_required; en LEGACY conserva
el comportamiento original. La identidad declarada no es autenticación de usuario:
el despliegue se limita a la red privada acordada y registro de clientes BD2.
