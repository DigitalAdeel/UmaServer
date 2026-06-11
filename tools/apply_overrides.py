#!/usr/bin/env python3
# Aplica account.db al seed load/index (carats, personajes, support cards, items)
# por reemplazo de array localizado + binpatch (sin re-serializar todo el response).
import sqlite3, os, struct, msgpack
BASE = os.path.join(os.path.dirname(__file__), "..")
DB = os.path.join(BASE, "account.db")
SEED = os.path.join(BASE, "seeds", "load_index.resp.bin")
OFFICIAL = os.path.join(BASE, "seeds", "load_index.official.resp.bin")
src = OFFICIAL if os.path.exists(OFFICIAL) else SEED

con = sqlite3.connect(DB)
carats = con.execute("SELECT value FROM kv WHERE key='carats'").fetchone()
carats = carats[0] if carats else 999999
db_cards = list(con.execute("SELECT card_id,rarity,talent_level FROM cards ORDER BY card_id"))
db_sup = list(con.execute("SELECT support_card_id,exp,limit_break_count FROM support_cards ORDER BY support_card_id"))
db_items = list(con.execute("SELECT item_id,number FROM items ORDER BY item_id"))

raw = bytearray(open(src, "rb").read())
o = msgpack.unpackb(bytes(raw), raw=False, strict_map_key=False)["data"]
viewer = o["user_info"]["viewer_id"]
NOW = "2026-06-10 00:00:00"

def find_array_span(buf, key):
    idx = buf.find(key)
    if idx < 0: return None
    ap = idx + len(key); h = buf[ap]
    if h == 0xdc: count = (buf[ap+1]<<8)|buf[ap+2]; ds = ap+3
    elif h == 0xdd: count = struct.unpack_from(">I",buf,ap+1)[0]; ds = ap+5
    elif 0x90 <= h <= 0x9f: count = h & 0x0f; ds = ap+1
    else: return None
    u = msgpack.Unpacker(raw=False, strict_map_key=False); u.feed(bytes(buf[ds:]))
    for _ in range(count): u.unpack()
    return ap, ds + u.tell()   # [array_header_start, array_end)

def replace_array(buf, key, elements):
    span = find_array_span(buf, key)
    if not span: print("  no encontrado:", key); return buf
    a0, a1 = span
    blob = msgpack.packb(elements, use_bin_type=True)  # array header + elementos
    return buf[:a0] + bytearray(blob) + buf[a1:]

# --- card_list: todos los personajes de la BD ---
cards = [{"card_id": cid, "rarity": r, "talent_level": t, "create_time": NOW, "skill_data_array": []}
         for (cid, r, t) in db_cards]
raw = replace_array(raw, b"\xa9card_list", cards)

# --- support_card_list: todas las de la BD ---
sup = [{"viewer_id": viewer, "support_card_id": sid, "exp": exp, "limit_break_count": lb,
        "favorite_flag": 0, "stock": 0, "possess_time": NOW, "create_time": NOW}
       for (sid, exp, lb) in db_sup]
raw = replace_array(raw, b"\xb1support_card_list", sup)   # 0xb1 = str17 "support_card_list"

# --- item_list: todos los items de la BD ---
items = [{"item_id": iid, "number": num} for (iid, num) in db_items]
raw = replace_array(raw, b"\xa9item_list", items)

# --- carats (fcoin) binpatch ---
def binpatch_fcoin(buf, val):
    key=b"\xa5fcoin"; out=bytearray(); i=0
    nv=b"\xce"+struct.pack(">I",val)
    while i < len(buf):
        if buf[i:i+len(key)]==key:
            out+=key; vp=i+len(key); t=buf[vp]
            w={0xcc:2,0xcd:3,0xce:5,0xcf:9,0xd0:2,0xd1:3,0xd2:5,0xd3:9}.get(t, 1 if t<0x80 or t>=0xe0 else 1)
            out+=nv; i=vp+w; continue
        out.append(buf[i]); i+=1
    return out
raw = binpatch_fcoin(raw, carats)

# verificar parse
chk = msgpack.unpackb(bytes(raw), raw=False, strict_map_key=False)["data"]
open(SEED, "wb").write(raw)
print("aplicado -> load_index.resp.bin")
print("  card_list:", len(chk["card_list"]), "support_card_list:", len(chk["support_card_list"]),
      "item_list:", len(chk["item_list"]), "fcoin:", chk["coin_info"]["fcoin"])
