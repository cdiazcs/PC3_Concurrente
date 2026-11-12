# Cliente Android (Kotlin — TCP Socket Binario V1)

Implementación nativa en Kotlin (`Empty Views Activity`) para Android (`minSdk 24`, `targetSdk 34`) que cumple estrictamente con `contracts/PROTOCOLO_TCP_V1.md`:

- **Transporte puro del SDK:** `java.net.Socket`, `DataOutputStream` y `DataInputStream` con cabecera de **4 bytes big-endian** + carga **UTF-8** (sin Retrofit, OkHttp ni WebSocket).
- **Concurrencia segura:** Todas las operaciones de red se ejecutan fuera del hilo principal mediante `Executors.newSingleThreadExecutor()`, con `soTimeout` configurable y validación explícita para prohibir `localhost`/`127.0.0.1` en dispositivo/emulador.
- **Entrada dual:** Lienzo táctil de `16x16` píxeles (`PixelCanvasView`) y selector de imágenes desde galería (`ActivityResultContracts.GetContent`) con escalado automático a `16x16` y normalización `0..1`.
- **Protocolo soportado:** `PING|<idSolicitud>` y `IDENTIFY|<idSolicitud>|v1,...,v256|DISTRIBUTED`.

## Cómo ejecutar en Android Studio
1. Abrir la carpeta `clients/android/` en Android Studio (**Open -> clients/android**).
2. Iniciar `CentralServer` en el PC en el puerto `9000` (o los workers).
3. En la app Android:
   - Usar `10.0.2.2` como Host si se ejecuta desde el **Emulador Android**, o la IP LAN del PC (ej. `192.168.1.11`) si se usa un teléfono físico en la misma red Wi-Fi.
   - Pulsar **Probar PING** para verificar conectividad y luego **Clasificar (IDENTIFY)**.
