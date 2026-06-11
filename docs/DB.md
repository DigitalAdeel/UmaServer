# UmaServer — Base de datos de overrides (persistente, editable)

Por la restricción del cliente (rechaza respuestas re-serializadas; solo acepta bytes
oficiales + parches binarios), el estado se gestiona como **overrides** sobre el seed
oficial de `load/index`, guardados en **`account.db`** (SQLite). Es persistente y editable.

## Archivos
- `account.db` — tu estado deseado (fuente de verdad).
- `seeds/load_index.official.resp.bin` — baseline oficial (campos del juego).
- `seeds/load_index.resp.bin` — seed SERVIDO (generado: baseline + overrides).
- `tools/db_init.py` — crea/repuebla `account.db` desde el seed actual.
- `tools/apply_overrides.py` — aplica `account.db` → `load_index.resp.bin`.

## Tablas de account.db
- `kv(key,value)` — escalares. `carats` = 999999 (moneda de gacha).
- `cards(card_id,rarity,talent_level)` — personajes poseídos (los 84 del juego).
- `support_cards(support_card_id,exp,limit_break_count)` — support cards.
- `items(item_id,number)` — items / recursos.

## Editar (ejemplos)
```bash
# cambiar carats
sqlite3 account.db "UPDATE kv SET value=500000 WHERE key='carats'"
# dar/maximizar un item (recurso)
sqlite3 account.db "INSERT OR REPLACE INTO items VALUES(140, 999999)"
# añadir una support card
sqlite3 account.db "INSERT OR REPLACE INTO support_cards VALUES(30028, 999999, 4)"
# aplicar los cambios al seed servido
python tools/apply_overrides.py
```
Tras `apply_overrides.py`, en el próximo arranque del juego se reflejan los cambios.
No hace falta reiniciar el server (lee el seed por petición); sí reinícialo si quieres
recargar el pool de gacha (varía entre los personajes de `card_list`).

## Límite conocido
No se pueden auto-guardar cambios hechos dentro del juego (el cliente rechaza
respuestas dinámicas re-serializadas). La persistencia es vía estos overrides.
