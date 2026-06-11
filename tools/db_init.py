#!/usr/bin/env python3
# Crea account.db (SQLite) con el estado de overrides deseado, poblada desde el
# seed load/index actual. Editable luego a mano o con SQL. apply_overrides.py lo aplica.
import sqlite3, os, msgpack
BASE = os.path.join(os.path.dirname(__file__), "..")
DB = os.path.join(BASE, "account.db")
SEED = os.path.join(BASE, "seeds", "load_index.resp.bin")

o = msgpack.unpackb(open(SEED, "rb").read(), raw=False, strict_map_key=False)["data"]
con = sqlite3.connect(DB); c = con.cursor()
c.executescript("""
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value INTEGER);
CREATE TABLE IF NOT EXISTS cards(card_id INTEGER PRIMARY KEY, rarity INTEGER, talent_level INTEGER);
CREATE TABLE IF NOT EXISTS support_cards(support_card_id INTEGER PRIMARY KEY, exp INTEGER, limit_break_count INTEGER);
CREATE TABLE IF NOT EXISTS items(item_id INTEGER PRIMARY KEY, number INTEGER);
""")
# carats
c.execute("INSERT OR REPLACE INTO kv VALUES('carats',999999)")
# personajes (todos los del catalogo release_card_array)
allcards = set(o.get("release_card_array", [])) | set(x["card_id"] for x in o.get("card_list", []))
for cid in sorted(allcards):
    c.execute("INSERT OR REPLACE INTO cards VALUES(?,?,?)", (cid, 3, 1))
# support cards actuales (maximizadas)
for s in o.get("support_card_list", []):
    c.execute("INSERT OR REPLACE INTO support_cards VALUES(?,?,?)", (s["support_card_id"], 999999, 4))
# items actuales (maximizados a 999999)
for it in o.get("item_list", []):
    c.execute("INSERT OR REPLACE INTO items VALUES(?,?)", (it["item_id"], 999999))
con.commit()
print("account.db creada:")
print(" carats:", c.execute("SELECT value FROM kv WHERE key='carats'").fetchone()[0])
print(" cards:", c.execute("SELECT COUNT(*) FROM cards").fetchone()[0])
print(" support_cards:", c.execute("SELECT COUNT(*) FROM support_cards").fetchone()[0])
print(" items:", c.execute("SELECT COUNT(*) FROM items").fetchone()[0])
con.close()
