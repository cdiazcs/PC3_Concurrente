# Arquitectura actual — Fase II

El flujo RabbitMQ con validación MariaDB y persistencia PostgreSQL está
implementado y probado localmente. Consultar el [diagrama y alcance actual](integration/FASE2_SISTEMA_COMPLETO.md)
y los [resultados](integration/FASE2_RESULTADOS.md). Android tiene proyecto Kotlin
sin APK verificado. La sección siguiente conserva la fotografía anterior a
integración; no representa el estado actual de Fase II.

---

# Arquitectura — estado actual vs objetivo PC3

## ACTUAL (núcleo existente que arranca)

```text
Java Swing / CLI (TCP con longitud prefijada, protocolo texto)
                 |
                 v
       CentralServer.java
                 |
      sockets TCP directos
          /      |      \
       Java    Python    C#    (workers CONV, JOB, MLP, IDENTIFY)
```

La CNN/MLP existente utiliza 16 x 16 y tres clases sintéticas. El sistema **no integra RabbitMQ ni BD** aún.

## OBJETIVO (implementar en ramas; aún no está completo)

```text
Android(Kotlin) --- TCP propio ---+
Desktop(Java)  --- TCP propio -----+--> Backend(Java) ---- RabbitMQ
Web (JS) -- HTTP servidor propio -+                     |    |    |
             usando sockets                    IA modelA  BD1  BD2
                                                Python     PG   MariaDB
                                                | RabbitMQ | RabbitMQ
                                                +----- respuesta ----> Backend ---> Cliente
```

Los clientes Android y Desktop abren conexiones TCP hechas con SDK del lenguaje. En Web **el navegador usa HTTP**, un gateway sirve HTML/JS y habla TCP con backend; no usa WebSocket, Socket.IO ni Flask/Django/Spring Boot. Entre backend, IA y BD se utiliza RabbitMQ. El middleware y los nodos se despliegan de forma separada.

## Decisiones que deben quedar documentadas antes del PR 1

- Protocolo heredado `IDENTIFY|id|pixelsCsv|SEQUENTIAL` **no** es el contrato PC3 de imágenes Base64. Integrar una versión v2 sin romper pruebas heredadas.
- Mensajes por RabbitMQ: `idSolicitud`, `idCliente`, `timestamp`, `modeloDestino`, imagenBase64 o referencia validada, resultado, intento e idempotencia.
- Un modelo vs dos: el documento de PC3 pone ejemplos A/B y exige colas A/B; requiere confirmación docente si cada grupo debe aportar uno o ambos.
- `BD1/BD2` son exactamente dos motores distintos según el enunciado formal; una sección de página 4 menciona BD3, inconsistencia a consultar.
- SO1, SO2 y SO3 deben ser diferentes conforme al criterio docente. Una sola computadora con tres procesos NO acredita distribución.
- No confundir RabbitMQ (cola de trabajo) con Raft (consenso): este proyecto no incluye Raft si no se solicita explícitamente.

## Protocolo de informe exigido

Cliente → Backend → RabbitMQ → Nodo IA → RabbitMQ → Nodo BD → RabbitMQ → Backend → Cliente.

Recomendar diagramas adicionales: despliegue físico con IP/SO y tabla de colas consumidores/publicadores.
