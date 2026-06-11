# UmaServer

Servidor privado (sandbox de **colección**) para **Umamusume: Pretty Derby** (cliente **Steam Global**), en Python. El cliente real se conecta a un servidor local que sirve tu cuenta desde un estado persistente y editable.

> ⚠️ **Aviso**: proyecto educativo / de ingeniería inversa. No incluye datos del juego ni de cuentas (debes capturarlos tú). Úsalo solo con tu cuenta y bajo tu responsabilidad. No afiliado a Cygames. Va contra los ToS del juego.

---

## Qué hace (y qué NO)

**✅ Funciona (sandbox de colección):**
- El cliente conecta a tu servidor local (sin DMM, sin tocar archivos verificados por Steam).
- Estado de cuenta **persistente y editable**: todos los personajes (★5), support cards, items, carats, team rank, perfil.
- Cambios de perfil (nombre, etc.) se **guardan**.

**❌ NO es posible (límite del cliente, no del servidor):**
- Jugar de verdad **carreras / modo carrera / entrenamiento** con personajes fabricados. Eso es **simulación del backend de Cygames** (no existe fuera de sus servidores) y el cliente filtra/valida el contenido con código **cifrado**. Las pantallas de colección muestran todo; las de gameplay ejecutan simulación que no tenemos.

Es decir: **vitrina de colección completa**, no un juego jugable al 100%.

---

## Cómo funciona

```
Cliente Umamusume (IL2CPP)
  └─ libnative.dll PROXY (nuestro)        ← reemplaza el plugin nativo del juego
        ├─ reenvía los exports reales a libnative_orig.dll
        ├─ hook curl_easy_setopt (UnityPlayer.dll): reescribe la URL del API → 127.0.0.1:5090
        └─ hook HttpHelper.CompressRequest/DecompressResponse (Coneshell): bypass → MessagePack plano
                                  │  (HTTP plano, MessagePack)
                                  ▼
        server.py (Python, :5090)
          ├─ account_state.mp  (tu estado persistente = data de load/index)
          ├─ account.db        (overrides editables: carats, cards, support, items)
          └─ seeds/            (respuestas capturadas de tu cuenta, por endpoint)
```

El API real va cifrado con **Coneshell** (compress+encrypt) sobre MessagePack. El proxy lo **bypassea** en el borde managed, así el servidor solo trabaja con MessagePack plano. Python re-serializa **byte-fiel** al oficial, por eso el cliente acepta respuestas dinámicas.

---

## Requisitos
- **Cliente Steam** de Umamusume: Pretty Derby (appid 3224770) instalado.
- **Python 3** + `pip install msgpack`.
- **MSVC** (Visual Studio Build Tools, C++ x64) para compilar el proxy.
- **MinHook** en `tools/minhook/` (clónalo: `git clone https://github.com/TsudaKageyu/minhook tools/minhook`).

## Puesta en marcha

### 1. Compilar el proxy
```bat
:: genera exports.h desde TU libnative del juego (sus 65 forwarders) y compila
cd src\UmaProxy
build.cmd        :: produce libnative.dll
```
> `exports.h` y la RVA de `curl_easy_setopt` (en `dllmain.cpp`, `CURL_SETOPT_RVA`) dependen de la versión del juego. Si cambian, regenéralos: `python tools/find_curl_setopt.py` para la RVA, y un dump de exports de tu `libnative.dll` para `exports.h`.

### 2. Instalar el proxy en el juego
En `...\steamapps\common\UmamusumePrettyDerby\UmamusumePrettyDerby_Data\Plugins\x86_64\`:
```
copy libnative.dll  libnative_orig.dll      :: respaldo del original
copy <nuestro> libnative.dll                 :: instala el proxy
```

### 3. Capturar TU cuenta (seeds)
- Arranca **sin** el flag `REDIRECT` (modo captura): el proxy habla con el oficial y vuelca request/response en claro a `capture/`.
- Juega/navega (home, gacha, etc.) para capturar endpoints.
- Correlaciona a seeds: `python tools/correlate.py`  → `seeds/`
- Guarda un baseline: copia `seeds/load_index.resp.bin` → `seeds/load_index.official.resp.bin`

### 4. (Opcional) Editar tu colección
```bash
python tools/db_init.py          # crea account.db desde el seed
python tools/inject_all.py       # todos los personajes en card_list
python tools/migrate_state.py    # chara_list (Umas) + support cards + cards
# editar carats/items: sqlite3 account.db "..."  (ver docs/DB.md)
```

### 5. Arrancar el servidor y jugar
```bash
python -u server.py              # escucha en :5090
type nul > REDIRECT              # activa modo LIVE (bypass + redirect)
```
Lanza el juego desde Steam → conecta a tu servidor local.

Para volver al oficial: borra `REDIRECT` y restaura `libnative.dll` (copia `libnative_orig.dll`).

---

## Estructura
```
server.py             servidor dinámico (Python + msgpack), estado persistente
src/UmaProxy/         proxy nativo de libnative.dll (C++/MSVC): redirect + bypass Coneshell
src/UmaServer/        servidor C# anterior (OBSOLETO: C# no genera MessagePack que el cliente acepte)
tools/                scripts: captura/correlación, edición de colección, RE (find_curl_setopt, disasm)
docs/                 PLAN.md (arquitectura/RE), DB.md (overrides)
```

## Licencia
Código bajo MIT (ver `LICENSE`). Datos y assets del juego son de Cygames y **no** se distribuyen aquí.
