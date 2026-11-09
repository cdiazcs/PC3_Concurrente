# Plan de PRs (sin `develop`)

1. `feature/contracts-v1`: acordar formatos, flujos y matriz de compatibilidad con servidor heredado. PR 1.
2. `feature/backend-rabbitmq`: conectar broker, solicitudes y resultados. Registrar `idSolicitud`, publisher confirm, ack y DLQ según decisión técnica. PR 2.
3. `feature/ai-distributed`: workers reciben trabajos vía colas y emiten resultado. Comprobar que el resultado coincide con el pipeline legado. PR 3.
4. `feature/bd1-postgresql`: esquema y consumidor que escribe clasificación e historial de forma idempotente. PR 4.
5. `feature/bd2-mariadb`: validación real con cola; registrar decisiones y cambios de estado. PR 5.
6. `feature/clients`: cliente Android, cliente Web + gateway HTTP socket, Desktop compatible. Descomponer en PR por cliente. PR 6–8.
7. `feature/benchmark-1000`: modos secuencial/paralelo/distribuido/paralelo-distribuido, 1000 solicitudes por cliente, delays y recursos. PR 9.
8. `feature/docs-entrega`: informe y presentación PDF + documentación de evidencias y demo. PR 10.

## Pruebas de aceptación comunes

- `idSolicitud` se mantiene idéntico de extremo a extremo.
- Sin corrupción al realizar escrituras en paralelo; idempotencia ante reintentos.
- Pérdida/reinicio de worker y RabbitMQ producen respuestas coherentes, sin bloqueos ilimitados.
- La CNN y el MLP siguen computando las mismas probabilidades dentro de tolerancia numérica.
- Probar desde Android, Desktop y Web reales conectados por LAN a distintos nodos.
- No simular nodos como si fuesen servidores físicos diferentes.
