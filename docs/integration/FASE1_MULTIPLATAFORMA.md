# Fase I: compilación e integración multiplataforma

## Inspección y problemas reproducidos

Se inventariaron todos los archivos versionados y los directorios solicitados:
Java backend, workers, CLI y Swing; CNN/MLP/entrenamiento Python; worker C#;
contratos, mensajería, SQL, clientes, benchmarks, scripts, CI y documentos.
No existe `P3cc4P1-262_v07.pdf` en este repositorio. Los requisitos proporcionados
para esta fase guían el trabajo; no se certifica conformidad con un PDF ausente.

La ejecución inicial de `python3 scripts/check_main.py` falló: faltaban packages
models/messaging/db. Build-Java.ps1 omitía lib/*; check_main/smoke_main además
solo buscaban fuentes Java del primer nivel. Las suites heredadas seguían
compilando contra Java 8 y sin dependencias de los paquetes añadidos por merge.

El backend iniciaba RabbitMQ obligatoriamente, tenía credenciales PostgreSQL
fijas y publicaba `INFERENCIA` sin payload. El worker Python ya implementaba
adaptación al CSV histórico y Base64 real; no se sustituyó esa lógica correcta.
Se agregó el formato explícito VECTOR_NORMALIZADO y se preservó entrada legacy.
El merge había quitado selección por capacidad, validación de respuestas y
límites configurables IDENTIFY; se restauraron del commit `65ff5cd`, conservando
la integración RabbitMQ como transporte seleccionable.

## Correcciones

- Construcción Java recursiva, classpath de JAR incluidos, release 17; verificación
  de sintaxis Python y compilación C# real cuando existe SDK.
- Scripts oficiales bash/PowerShell con raíz automática, códigos de error y
  separación de unitarios, integración TCP y broker real.
- Prueba ejecutada de serialización Gson -> validación/CNN Python -> Gson.
- RabbitMQ: credenciales/vhost/colas por entorno; canal publicador sincronizado,
  confirms, mensajes persistentes, correlation_id, acknowledgements manuales,
  rechazo de JSON/correlación inválidos, timeout y limpieza de futuros.
- ID TCP conservado en AMQP; payload obligatorio con modo y vector 16×16 explícito.
  No se modificaron los pesos ni algoritmos oficiales.
- DISTRIBUTED usa el coordinador JOB sin republicar IDENTIFY en RabbitMQ; el
  worker AMQP puede consultar ese coordinador sin ciclo.
- PostgreSQL opcional por entorno; MariaDB utiliza RABBITMQ_PASSWORD y elimina
  contraseña predeterminada. No se rediseñaron esquemas ni transacciones.
- Variables de host/puerto para backend, CLI, Swing y workers; bind local por
  defecto. WebGateway Java consulta backend TCP en otro proceso en lugar de
  usar gestores estáticos no inicializados.
- Configuraciones de ejemplo y cargador KEY=VALUE común, sin secretos ni IP
  inventadas. Perfiles por integrante comprueban los puertos de sus servicios.
- CI en Ubuntu/Windows para PR a integration/main; broker real en job separado.
  Su aprobación solo se conocerá cuando GitHub ejecute el workflow.

## Alcance y límites

El transporte se selecciona con INFERENCE_TRANSPORT=TCP o RABBITMQ; no confundir
esa selección con modo de cálculo SEQUENTIAL/DISTRIBUTED ni distribución física.
Sin .NET se informa omisión de suites que necesitan tres lenguajes. Fallos de
prueba no se convierten en omisiones. Los unitarios y el smoke Python/Java
siguen funcionando sin bases de datos.

Las colas de resultados compartidas soportan un backend consumidor. Para varios
backends hacen falta colas por instancia; esto no se presenta como escalado
horizontal resuelto. La deduplicación Python es de proceso/TTL, no persistente.
Los futuros vencidos se liberan, pero un timeout no retira mensajes del broker.
El backend mantiene el gestor PostgreSQL existente, que registra fallos SQL por
stderr; una inferencia exitosa no demuestra persistencia SQL.

No se implementó Android, rediseño SQL, ni benchmarks finales de Fase III.
Las pruebas de regresión de benchmarks existentes solo verifican que el merge
no rompió funcionalidad previa. Windows, Fedora y Tailscale entre equipos
requieren evidencia de sus respectivos dueños.

## Cierre solicitado: trabajo exclusivo en integration

Se respaldaron 55 archivos modificados/nuevos y sus hashes fuera del repositorio.
Ambas ramas apuntaban a 9a4eda3; `git switch integration` conservó todos los
archivos, verificado por SHA-256. No hubo commit, merge, rebase ni rama nueva.

El cierre usa JDK 21 y conserva bytecode release 17. Se reutilizan scripts:
los perfiles ahora compilan solo componentes necesarios y separan `--services`
de unitarios; perfil IA funciona incluso sin Java/.NET en PATH. La antigua
prueba main de PostgresManager que insertaba datos fue reemplazada por SELECT 1
READ ONLY y rollback. El probe MariaDB hace lo mismo; la comprobación RabbitMQ
solo autentica y cierra conexión/canal. No se modificaron esquemas SQL.

Los timeouts Java ahora admiten entorno, preservando -D como prioridad.
CLI/Desktop esperan 30 s por defecto, permitiendo recibir timeout_ia a los 25 s;
el modo inicial también es configurable. Configuraciones incoherentes del
backend AMQP se rechazan antes de abrir conexión al broker.

Las pruebas locales fuerzan binds loopback/transporte TCP y límites de prueba
para no heredar el entorno de un despliegue remoto. Las comprobaciones
--services/--rabbit conservan la configuración real solicitada. La cuenta de
CI del broker es desechable, con contraseña derivada del run; evita restricciones
guest al atravesar NAT del contenedor y no almacena secretos de despliegue.
