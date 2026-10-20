# Integraciones Android

Las siguientes son las primeras integraciones del código común, de la revisión `ff20596f137119b98844a03a75836099ac7e146b`. Esta tabla es histórica; las versiones actuales están en `updates/A.json` y `updates/B.json` de cada aplicación. A incluye todas las versiones A y B y ofrece la de mayor `versionCode`; B solo incluye las autorizadas expresamente para B.

| App | Versión A | APK |
| --- | --- | --- |
| youtube-calma | 0.1.6 | [Descargar](https://github.com/miguelcoxcaballero/youtube-calma/releases/download/v0.1.6/YouTube-Calma-0.1.6.apk) |
| ig-calma | 0.4.16 | [Descargar](https://github.com/miguelcoxcaballero/ig-calma/releases/download/v0.4.16/IG-Calma-0.4.16.apk) |
| inhousenotes | 1.0.11 | [Descargar](https://github.com/miguelcoxcaballero/inhousenotes/releases/download/android-v1.0.11/inhouse-notes-release-v1.0.11.apk) |
| inhouse-read | 1.1.11 | [Descargar](https://github.com/miguelcoxcaballero/inhouse-read/releases/download/android-v1.1.11/inhouse-read-release-v1.1.11.apk) |
| Inhouse-Photos | 3.1.102 | [Descargar](https://github.com/miguelcoxcaballero/Inhouse-Photos/releases/download/v3.1.102-a/Inhouse-Photos.apk) |

[Pruebas y límites](validation/2026-10-11.json). Los manifiestos de cada app permanecen en su propio repositorio; aquí se mantiene la implementación común. Para cambios futuros, lee `AGENTS.md` y sincroniza las seis apps con `tools/sync.py`.

Inhouse Learn (`inhouselearn`, paquete `com.inhouse.learn`) se añadió el 2026-10-20 como sexta app. Es un host nativo como Photos: `MainActivity` llama a `NativeUpdates` y el popup y los ajustes son `UpdateActivity`, con los recursos web en `android/app/src/main/assets/updates` y el proveedor `.update-provider` registrado con `UpdateFileProvider`. Su primera versión A es la 1.0.0; ver `android/README.md` en ese repositorio.
