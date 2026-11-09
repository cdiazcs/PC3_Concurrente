# Trabajo GitHub Flow de 3 integrantes — SIN `develop`

## Decisión

- **`main`:** única rama permanente, siempre compila y pasa las pruebas disponibles.
- Cada uno crea desde `main` una rama `feature/...` por tarea; las ramas son **temporales**.
- Cada cambio se integra con **Pull Request (PR)** a `main`; al cerrar una tarea, crear una rama nueva desde el último `main`.
- No copiar `.git/` de un ZIP antiguo, pues había un merge inconcluso en el material de origen.

## Publicar el ZIP base en GitHub, solo una vez

```bash
git init -b main
git add .
git commit -m "chore: base comun OpenAI Cubes PC3"
git remote add origin URL_NUEVO_REPOSITORIO
git push -u origin main
```

Si el repositorio de GitHub **ya existe con historial**, NO hacer `git init` ni sobrescribirlo: clonar el repositorio, copiar los archivos de esta base sobre su carpeta, revisar `git status`, hacer un commit en una rama y fusionar vía PR. Confirmar que el repositorio remoto no tenga un merge pendiente.

## Primera tarea por integrante

- **1 — Backend/Rabbit:** `feature/backend-rabbitmq`. Mantener TCP de clientes, publicar solicitudes en colas, consumir resultados por `idSolicitud`, implementar timeouts, reintentos e idempotencia; luego `feature/bd1-postgresql` para nodo persistencia BD1.
- **2 — IA:** `feature/ai-distributed`. Adaptar CNN/MLP para recibir/publicar tareas de RabbitMQ; entrenamiento y prueba concurrentes, paralelos y distribuidos. Conservar equivalencia matemática de resultados. Luego `feature/performance` para métricas de cuatro escenarios.
- **3 — Clientes/BD2:** `feature/clients`. Crear cliente Android Kotlin, cliente Web con servidor HTTP por sockets propios, y mantener Desktop. Luego `feature/bd2-mariadb` para validación del cliente a través de RabbitMQ.

## Comandos cotidianos

Crear una rama nueva desde la última main:

```bash
git switch main
git pull --ff-only origin main
git switch -c feature/mi-tarea
```

Guardar y subir:

```bash
git add ruta/que/modificaste
git commit -m "feat: describir implementacion"
git push -u origin feature/mi-tarea
```

Abrir un PR **base: main** / **compare: feature/mi-tarea** en GitHub. Solicitar revisión a otro integrante.

Si cambió main mientras trabajas:

```bash
git fetch origin
git merge origin/main
# Resolver conflictos si aparecen, ejecutar pruebas y enviar cambios.
git push
```

Después del merge:

```bash
git switch main
git pull --ff-only origin main
git branch -d feature/mi-tarea
```

## Reglas mínimas para PR

1. Breve descripción de qué cambia, qué no cambia y rutas afectadas.
2. Evidencia (comandos + salida) de pruebas relevantes y capturas si afectan interfaz/red.
3. Ninguna contraseña, `build/`, `bin/`, `obj/` ni `.git/` dentro del ZIP.
4. Contratos TCP y RabbitMQ no se cambian sin acuerdo de los tres.
5. Mantener compatibilidad con el protocolo TCP actual hasta que los tres clientes migren.
6. Un PR se integra solo si otro compañero lo revisa; proteger main en GitHub (PR obligatorio, 1 approval, checks).
7. Si el PR depende de otro, integrar primero la dependencia; evitar merges masivos.

## Integración incremental

`main v0` núcleo heredado → `PR RabbitMQ` → `PR IA RabbitMQ` → `PR BD1` → `PR BD2` → `PR Android` → `PR Web` → `PR experimentos` → `main PC3 verificada`.

El orden se ajusta a las dependencias. Se permiten ramas simultáneas, pero no declarar una etapa completada sin pruebas de extremo a extremo.
