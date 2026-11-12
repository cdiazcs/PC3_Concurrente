# Android Kotlin — Fase II

Proyecto nativo Activity/Kotlin, sin frameworks de red. Selector del sistema,
vista previa, identificación, host/puerto editables y chat de estados/resultado.
Socket TCP y lectura de imagen se ejecutan fuera del hilo principal; cierre
programado del socket a los 80 s. El cliente no habla directamente con RabbitMQ.
El perfil compartido Protocol.java implementa IDENTIFY2 y valida ID/framing/
probabilidades; la CNN permanece en Python.

Versiones fijadas: AGP 8.7.3, Kotlin 2.0.21, Gradle Wrapper 8.9 con SHA-256,
compileSdk/targetSdk 35, minSdk 26. JDK 21 del equipo; bytecode JVM 17.
La [tabla oficial AGP 8.7](https://developer.android.com/build/releases/agp-8-7-0-release-notes)
indica Gradle 8.9 y SDK máximo 35. Se eligieron versiones fijadas, no se afirma
que sean las últimas disponibles.

Desde Android Studio abrir clients/android. Instalar Android SDK Platform 35 y
Build Tools solicitadas; revisar/aceptar sus licencias personalmente. Configurar
ANDROID_HOME o un local.properties con sdk.dir, que está ignorado por Git.

```powershell
cd clients/android
./gradlew.bat :protocol:contractTest
./gradlew.bat :app:assembleDebug
# Con emulador/dispositivo y adb configurados:
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

```bash
cd clients/android
./gradlew :protocol:contractTest
./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Gradle utiliza google() y mavenCentral(); el primer build requiere Internet.
El módulo protocol puede probarse sin Android SDK; adicionalmente lo ejercitan
los tests Python/Javac del repositorio. En esta sesión el wrapper y ese módulo
compilaron; assembleDebug falló por **SDK location not found**. APK y ejecución
en dispositivo: **NO VERIFICADOS**. No confundir la prueba TCP de Protocol.java
en una JVM con la Activity ejecutándose en Android.

En la app introducir dirección privada real del backend (no localhost de otro
PC), puerto y un cliente del seed, por ejemplo cliente-android-01. Elegir PNG o
JPEG hasta 1 MB y cuatro megapíxeles. El backend FULL debe estar activo y los
nodos BD2/IA/BD1 conectados. RESULT implica persistencia confirmada; pendientes,
rechazos y fallos se muestran como errores, conservando el ID en el chat.
La selección usa ACTION_OPEN_DOCUMENT y permiso INTERNET, sin permisos generales
de almacenamiento. ID de cliente es identificación, no contraseña ni login.
