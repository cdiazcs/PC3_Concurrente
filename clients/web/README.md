# Cliente Web — integrante 3

**No implementado aún.** Crear HTML/JS con chat, carga de imagen y resultado. El navegador **NO abre TCP nativo**: `fetch()` a un servidor HTTP propio implementado con sockets estándar; ese servidor reenvía por TCP al backend. Prohibidos Flask/Django/Spring Boot, Socket.IO y WebSocket por el enunciado.

Agregar flujo Base64 y preprocesamiento 16×16 compatible con la CNN, con controles de tamaño. El HTTP gateway se desarrolla en `web-server/`.

## Fase II

Usar el gateway oficial `web-server/http_gateway.py` con CLIENT_PROTOCOL=V2.
El campo clientId se envía al backend: no se autoriza un usuario inexistente.
El backend valida en MariaDB y espera la confirmación PostgreSQL antes de
responder éxito. Ver docs/integration/FASE2_SISTEMA_COMPLETO.md para arranque.
El gateway conserva el vector legado del navegador en el API, pero V2 transmite
el archivo Base64 y el preprocesamiento real lo hace el backend compartido.
