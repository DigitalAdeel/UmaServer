# UmaServer — Plan técnico (servidor privado Umamusume Steam Global)

## Estado actual (2026-06-09)
Reconocimiento completo. Servidor base en `src/UmaServer` (puerto 5090, MessagePack, modo captura) compila.

## Cliente (recon confirmado)
- Steam Global (inglés), appid **3224770**, en `C:\Program Files (x86)\Steam\steamapps\common\UmamusumePrettyDerby`.
- Unity 2022.3.62 **IL2CPP**, global-metadata **v31.1**.
- API: `https://api.games.umamusume.com/umamusume` · Assets: `https://dmg.umamusume.jp/`.
- Auth/extra: AWS Cognito + Firebase + Anti-Cheat Toolkit (codestage).
- Crypto/red nativa = **`tempest`** en `libnative.dll` (exports `tempest_requests_create`, `tempest_register_request_raw`, `tempest_release_request`, ...). Integra mbedTLS (TLS propia) y SQLite Multiple Ciphers.
- `master.mdb` cifrado con **sqlite3mc** (`sqlite3_key`, `sqlite3mc_config_cipher`).

## El muro y la solución
- **Muro**: el `GameAssembly.dll` oculta CodeRegistration/MetadataRegistration → Cpp2IL no puede generar interops estáticos → **el enfoque managed (BepInEx/C#, como PriconneServer) NO es viable**.
- **Solución (decidida)**: apoyarse en **Hachimi** (https://github.com/Hachimi-Hachimi/Hachimi), que ya:
  - Se inyecta en el cliente Windows por **proxy DLL** (`cri_mana_vpx.dll` / `UnityPlayer.dll`).
  - Resuelve clases/métodos IL2CPP **por nombre en runtime** vía la API `il2cpp_*` (evade el anti-tamper).
  - Aplica detours con **MinHook**.
  - Expone un **plugin API** (`src/core/plugin_api.rs`): un plugin DLL exporta `hachimi_init(vtable, version)` y recibe un vtable con `interceptor_hook`, `il2cpp_get_assembly_image/get_class/get_method_addr`, field get/set, etc.

## Arquitectura objetivo
```
Cliente Umamusume (IL2CPP)
  └─ Hachimi (proxy DLL, inyección + il2cpp runtime + MinHook)
        └─ Plugin de captura/redirect (NUESTRO, usa el plugin API de Hachimi)
              ├─ hook del envío de request  -> vuelca MessagePack en claro + reescribe host -> 127.0.0.1:5090
              └─ hook de la recepción       -> vuelca MessagePack de respuesta (seeds)
                                  │
                                  ▼
        UmaServer .NET 10 (puerto 5090, MessagePack)  ← responde con seeds/lógica
```

## Pasos
1. **[pendiente] Identificar la clase/método de red en `Gallop`** (el que serializa/envía el request y el que recibe la respuesta). Vías: proyectos de emulador existentes (Trainers' Legend G), o enumeración por nombre en runtime desde el plugin.
2. **[pendiente] Escribir el plugin de captura** (DLL que exporta `hachimi_init`), hookea esos métodos y vuelca `capture/<path>.json` + redirige.
3. **[pendiente] Capturar** el protocolo real (envelope, paths de arranque) con la cuenta del usuario.
4. **[pendiente] Implementar el envelope + endpoints de arranque** en UmaServer a partir de las seeds.
5. (Opcional) Desencriptar `master.mdb` con sqlite3mc para datos reales.

## Referencia
Fuentes clave de Hachimi guardadas en `tools/hachimi_ref/` (interceptor Windows, plugin API, resolución il2cpp, hook SQLite).
BepInEx be.759 (zip) en `tools/` — quedó instalado en el juego durante el recon; **se puede desinstalar** (no se usa en el enfoque final): borrar `winhttp.dll`, `doorstop_config.ini`, `.doorstop_version`, `dotnet/`, `BepInEx/` de la carpeta del juego.
```
```
