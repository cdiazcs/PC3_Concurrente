> Fase I: usar las instrucciones actualizadas en [EJECUCION_LOCAL](../docs/EJECUCION_LOCAL.md)
> e [INSTALACION_EQUIPO](../docs/INSTALACION_EQUIPO.md). Los comandos históricos
> siguientes no acreditan integración; credenciales se configuran por entorno.

# Avance Backend y Middleware (Integrante 1)

Este documento detalla la implementación del núcleo del sistema (Backend), la integración con RabbitMQ, la base de datos PostgreSQL y el Gateway HTTP.

**El flujo del servidor está 100% funcional y probado.**

## 🏗️ 1. Arquitectura Implementada

El sistema ya no usa sockets directos para la IA. Ahora el flujo es:

1. **Cliente (TCP o Web):** envía la petición al **CentralServer** (Puerto `9000`) o al **WebGateway** (Puerto `8080`).
2. El servidor guarda la solicitud en **PostgreSQL** (estado `RECIBIDA`).
3. El servidor publica un JSON en la cola de RabbitMQ **`cola_modeloA`**.
4. El servidor se queda esperando la respuesta en la cola **`cola_resultadosA`** (con un timeout de 25 segundos).
5. Al recibir la respuesta, la guarda en **PostgreSQL** (estado `COMPLETADA`) y se la envía de vuelta al cliente original.

---

## 📦 2. Requisitos Previos (Configuración del Entorno)

Para que el código funcione, se deben tener estas herramientas:

### A. RabbitMQ

Debe estar corriendo en el puerto `5672`. Si usan Docker, el comando es:

```bash
docker run -d --name rabbitmq-pc3 -p 5672:5672 -p 15672:15672 rabbitmq:3-management
```

**Panel de control:** http://localhost:15672

**Credenciales:**
- Usuario: `guest`
- Contraseña: `guest`

### B. PostgreSQL (BD1)

- **Base de Datos:** Crear una BD llamada `pc3_concurrente`.
- **Esquema:** Ejecutar el script `databases/postgresql/01_schema.sql` dentro de esa BD.
- **Credenciales actuales en el código:**
  - Usuario: `postgres`
  - Contraseña: `postgresql17`
  - Puerto: `5432`

> **Nota:** Si alguien cambia la contraseña, debe actualizarla en `db/PostgresManager.java`.

### C. Librerías Java (`.jar`)

Se agregó la carpeta `lib/` en la raíz del proyecto con las siguientes dependencias (necesarias para compilar y ejecutar):

- `amqp-client-5.36.0.jar` (RabbitMQ).
- `slf4j-api-2.0.13.jar` (Dependencia de RabbitMQ).
- `postgresql-42.7.14.jar` (Base de datos).
- `gson-2.14.0.jar` (Manejo de JSON).

---

## 📂 3. Nuevos Archivos Creados

- `server-java/models/MensajesRabbit.java`: Estructuras (DTOs) para el JSON.
- `server-java/messaging/RabbitMQManager.java`: Productor y consumidor de RabbitMQ.
- `server-java/db/PostgresManager.java`: Conexión JDBC y consultas SQL.
- `server-java/WebGateway.java`: Servidor HTTP (Puerto 8080) para el Integrante 3.
- `server-java/CentralServer.java`: Modificado para usar RabbitMQ en lugar de los workers por socket.

---

## 🛠️ 4. Instrucciones para el Integrante 2 (Nodo IA)

**¡Tu turno!** Ya tienes las tareas llegando a RabbitMQ. Debes hacer lo siguiente en tu código Python (`cnn_python` o `workers/`):

1. **Consumir:** Conéctate a RabbitMQ y consume de la cola `cola_modeloA`.
2. **Leer JSON:** El mensaje es un JSON (ver `contracts/RABBITMQ_V1.md`). El vector viene en `payload.imagen.valores`, con formato `VECTOR_NORMALIZADO`, 16×16 y 256 números en [0,1]. No es Base64.
3. **Procesar:** Convierte ese string a un arreglo de floats, pásalo por tu modelo CNN y obtén las probabilidades.
4. **Responder:** Publica el resultado en la cola `cola_resultadosA` usando **exactamente** este formato JSON:

```json
{
  "schemaVersion": 1,
  "idSolicitud": "EL_MISMO_ID_QUE_RECIBISTE",
  "timestamp": "2026-11-09T15:30:02Z",
  "estado": "COMPLETADA",
  "payload": {
    "etiqueta": "circulo",
    "probabilidad": 0.95,
    "probabilidades": [0.95, 0.03, 0.02],
    "duracionMs": 1500
  },
  "error": null
}
```

---

## 🖥️ 5. Instrucciones para el Integrante 3 (Clientes y Web)

Tienes dos formas de conectarte a mi backend, dependiendo de tu cliente:

### A. Cliente Web (JavaScript / HTML)

No uses sockets directos. Haz una petición HTTP POST al Gateway:

- **URL:** `http://localhost:8080/api/predict`
- **Método:** `POST`
- **Body (Texto plano):** Los 256 píxeles de la imagen separados por comas.
- **Respuesta:** Recibirás un JSON con las probabilidades.

> **Nota:** Ya tiene CORS habilitado para que no tengas problemas desde el navegador.

### B. Clientes Desktop (Java Swing) y Android (Kotlin)

Sigan usando el socket TCP original. El `CentralServer` sigue escuchando en el puerto `9000` y acepta el protocolo antiguo:

```text
IDENTIFY|req-001|pixeles|DISTRIBUTED
```

La respuesta será la misma de siempre:

```text
RESULT|...
```

---

## ⚙️ 6. Comandos para Compilar y Ejecutar

Todos los comandos deben ejecutarse desde la raíz del proyecto `PC3_Concurrente`.

### Compilar TODO el backend

```powershell
javac -cp "lib/*" -d build server-java/models/MensajesRabbit.java server-java/messaging/RabbitMQManager.java server-java/db/PostgresManager.java server-java/DistributedCnn.java server-java/CentralServer.java server-java/WebGateway.java
```

### Ejecutar el Servidor TCP (Terminal 1)

```powershell
java -cp "build;lib/*" CentralServer 9000 127.0.0.1:9102
```

### Ejecutar el Gateway HTTP para la Web (Terminal 2)

```powershell
java -cp "build;lib/*" WebGateway
```

---

## 📌 7. ¿Dónde lo pongo?

1. Crea la carpeta `docs/` si no existe.
2. Dentro de `docs/`, crea un archivo llamado `AVANCE_INTEGRANTE_1.md`.
3. Pega todo el contenido de este documento.
4. Abre el `README.md` principal del proyecto y, en la sección **Organización del trabajo**, añade el siguiente enlace:

```markdown
Ver detalles de la implementación del Backend aquí: [docs/AVANCE_INTEGRANTE_1.md](docs/AVANCE_INTEGRANTE_1.md)
```

---
