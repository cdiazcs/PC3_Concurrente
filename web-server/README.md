# Gateway HTTP oficial — Fase II

El gateway oficial es `http_gateway.py`: HTTP/1.1 implementado con socket de
Python, biblioteca estándar. Sirve clients/web/ y traduce POST /api/classify a
TCP con framing de cuatro bytes. El navegador usa fetch HTTP; nunca RabbitMQ,
WebSocket, Flask o Django.

```bash
python scripts/run_env.py .env python web-server/http_gateway.py
```

En Windows reemplazar python por el ejecutable del venv cuando corresponda.
Usar CLIENT_PROTOCOL=V2 y el ejemplo config/phase2.local.example.env; configuran
host/puerto del backend, bind loopback y timeout de 80 s. El gateway tiene límite
WEB_MAX_CLIENTS (128 por defecto), deadlines de lectura HTTP y respuesta TCP,
límite de cuerpos y rechazo de cabeceras duplicadas/transfer-encoding no soportado.

IDENTIFY2 transmite imagen Base64 real e idCliente al backend, que realiza el
preprocesamiento autoritativo. payload.pixels del navegador se mantiene por
compatibilidad del API Web, pero no decide lo que clasifica el backend V2.
La respuesta mantiene idSolicitud, etiqueta/probabilidades; los rechazos backend
son HTTP 422, errores de transporte HTTP 502. persistence_pending no es éxito.

El gateway alternativo server-java/WebGateway.java se conserva por el trabajo
del equipo, pero NO es el oficial de Fase II: usa HttpServer del JDK y su endpoint
legado no implementa el flujo de identidad V2. No levantar ambos en 8080.
No exponer el gateway públicamente en esta fase; utilizar la interfaz privada
configurada para Tailscale cuando el equipo valide la red.
