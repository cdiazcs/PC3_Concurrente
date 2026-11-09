# Preparación de entrega y defensa

**Este repositorio base NO es el paquete final de UNIVIRTUAL.**

El enunciado PDF (p. 5) solicita ZIP con fuentes en lenguajes autorizados, scripts SQL, PDF informe y PDF presentación; permite datasets y comandos SQL como excepción a extensiones prohibidas. Antes de empaquetar, acordar con el docente si se permiten `.md`, `.properties`, `.xml`, `.gradle.kts`, `.csproj` y archivos de configuración de Android imprescindibles. No mezclar `README` o plantillas de GitHub en el ZIP de evaluación sin permiso.

## Demo sugerida

1. Mostrar 3 hosts/VM distintos: IP, SO, lenguaje, proceso worker activo.
2. Abrir panel RabbitMQ, colas dedicadas; identificar al menos una solicitud y su correlación.
3. Enviar imagen desde Android, Desktop y Web; recibir etiqueta/probabilidad/fecha/ID.
4. Consultar BD1 (metadatos, consulta y clasificación) y BD2 (validación cliente).
5. Ejecutar N=1000 con delay aleatorio, mostrar CSV y gráficas; explicar promedios y p95.
6. Comparar 4 configuraciones y advertir gastos por red/sincronización.
7. Simular un fallo de worker y documentar reintento/timeout/errores.

## Apartados para PDF informe

Portada, problema/alcance, restricciones, arquitectura nodos/SO/LP, contrato TCP/AMQP, implementación CNN/MLP y entrenamiento, dataset/preprocesamiento, BD1/BD2/transacciones, tres clientes, concurrencia/sincronización, metodología experimentos, resultados con gráficas, discusión, limitaciones, conclusiones y referencias.
