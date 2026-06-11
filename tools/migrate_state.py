#!/usr/bin/env python3
# Migra account_state.mp (preservando cambios del usuario) para que tenga:
#  - card_list: todos los personajes (release_card_array)
#  - chara_list: todos los charas (chara_id = card_id//100)  <- la seccion "Umas"
#  - support_card_list: todos los support cards vistos en capturas (catalogo)
import msgpack, os, glob
BASE = os.path.join(os.path.dirname(__file__), "..")
STATE = os.path.join(BASE, "account_state.mp")
NOW = "2026-06-10 00:00:00"

st = msgpack.unpackb(open(STATE, "rb").read(), raw=False, strict_map_key=False)
d = st["data"]
vid = d.get("user_info", {}).get("viewer_id", 0)

# catalogo de cards
of = msgpack.unpackb(open(os.path.join(BASE, "seeds", "load_index.official.resp.bin"), "rb").read(),
                     raw=False, strict_map_key=False)["data"]
all_cards = sorted(set(of.get("release_card_array", [])) | {c["card_id"] for c in d.get("card_list", [])})

# 1) card_list
have = {c["card_id"] for c in d["card_list"]}
for cid in all_cards:
    if cid not in have:
        d["card_list"].append({"card_id": cid, "rarity": 5, "talent_level": 5,
                               "create_time": NOW, "skill_data_array": []})

# 2) chara_list (todos los charas) — dress_id 2 = default (como la mayoria)
all_charas = sorted(set(c // 100 for c in all_cards))
hch = {c["chara_id"] for c in d.get("chara_list", [])}
for ch in all_charas:
    if ch not in hch:
        d["chara_list"].append({"chara_id": ch, "training_num": 0, "love_point": 0, "fan": 1,
                                "max_grade": 5, "dress_id": 2, "mini_dress_id": 2})

# 3) support_card_list — catalogo visto en capturas
sup = set()
for f in glob.glob(os.path.join(BASE, "seeds", "*.bin")) + glob.glob(os.path.join(BASE, "capture", "decresp_out_*.bin")):
    try: o = msgpack.unpackb(open(f, "rb").read(), raw=False, strict_map_key=False)
    except: continue
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "support_card_id" and isinstance(v, int) and v > 0: sup.add(v)
                walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(o)
hs = {s["support_card_id"] for s in d.get("support_card_list", [])}
for sid in sorted(sup):
    if sid not in hs:
        d["support_card_list"].append({"viewer_id": vid, "support_card_id": sid, "exp": 999999,
            "limit_break_count": 4, "favorite_flag": 0, "stock": 0,
            "possess_time": NOW, "create_time": NOW})

open(STATE, "wb").write(msgpack.packb(st, use_bin_type=True))
print("migrado:")
print("  card_list:", len(d["card_list"]), "chara_list:", len(d["chara_list"]),
      "support_card_list:", len(d["support_card_list"]))
print("  nombre preservado:", d.get("user_info", {}).get("name"))
