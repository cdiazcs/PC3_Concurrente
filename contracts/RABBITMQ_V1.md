# Contrato RabbitMQ V1 — Implementación Backend (Integrante 1)

## Estado Actual de la Integración
*   **Backend (Integrante 1):** ✅ **Implementado.** El servidor Java ya publica peticiones en `cola_modeloA` y se queda escuchando las respuestas en `cola_resultadosA`. Además, cuenta con un Gateway HTTP en el puerto 8080 para el cliente Web.
*   **Nodo IA (Integrante 2):** ⏳ **Pendiente.** Debe consumir de `cola_modeloA` y publicar en `cola_resultadosA`.
*   **Base de Datos y Clientes (Integrante 3):** Las colas de validación y persistencia (BD2) se integrarán en la fase final.

## Mapa de Colas
| Cola | Publicador | Consumidor | Estado | Objetivo |
| --- | --- | --- | --- | --- |
| `cola_modeloA` | Backend | Nodo IA A | ✅ Implementado | Solicitudes de inferencia (Modelo A) |
| `cola_resultadosA` | IA A | Backend | ✅ Implementado | Resultados de inferencia (Modelo A) |
| `cola_modeloB` | Backend | Nodo IA B | ⏳ Pendiente | Opción modelo B; confirmar docente |
| `cola_resultadosB` | IA B | Backend | ⏳ Pendiente | Resultados modelo B, si se implementa |
| `cola_validacion` | Backend | BD2 | ⏳ Pendiente | Solicitud de validación a MariaDB |
| `cola_resultados_validacion` | BD2 | Backend | ⏳ Pendiente | Validación realizada |
| `cola_persistencia` | Backend / IA | BD1 | ⏳ Pendiente | Resultado/historial en PostgreSQL |
| `cola_resultados_bd` | BD1 | Backend | ⏳ Pendiente | Confirmación de persistencia |
| `cola_control_heartbeat` | Nodos | Monitor | ⏳ Pendiente | Salud de los nodos |
| `cola_logs` | Nodos | Observador | ⏳ Pendiente | Trazabilidad del sistema |

## Contrato JSON Implementado (UTF-8)

El Backend implementa estrictamente el formato JSON. Cualquier mensaje que no cumpla con esta estructura será descartado o marcado como error.

### 1. JSON de Petición (Backend -> `cola_modeloA`)
El Backend envía este JSON. El campo `imagenBase64` contiene los 256 píxeles de la imagen (valores entre 0.0 y 1.0) separados por comas.

```json
{
  "schemaVersion": 1,
  "idSolicitud": "UUID-generado-por-backend",
  "idCliente": "req-001",
  "timestamp": "2026-11-09T15:30:00Z",
  "tipo": "INFERENCIA",
  "modeloDestino": "A",
  "imagenBase64": "0.1,0.5,0.2,0.8,... (256 valores)",
  "intento": 1,
  "payload": {
    "modo": "DISTRIBUTED"
  }
}