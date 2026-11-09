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
