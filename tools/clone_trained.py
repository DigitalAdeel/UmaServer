#!/usr/bin/env python3
# Genera trained_chara (umas entrenadas, para CARRERAS/Team Stadium) para TODOS los
# card_id del card_list, clonando un template real y maximizando stats. Preserva los reales.
import msgpack, os, copy
BASE = os.path.join(os.path.dirname(__file__), "..")
STATE = os.path.join(BASE, "account_state.mp")
st = msgpack.unpackb(open(STATE, "rb").read(), raw=False, strict_map_key=False)
d = st["data"]
tc = d.get("trained_chara", [])
if not tc:
    print("no hay trained_chara template"); raise SystemExit
tmpl = tc[0]
vid = d.get("user_info", {}).get("viewer_id", 0)
existing_cards = {t.get("card_id") for t in tc}
next_id = max(t.get("trained_chara_id", 0) for t in tc) + 1

all_cards = sorted(c["card_id"] for c in d.get("card_list", []))
added = 0
for cid in all_cards:
    if cid in existing_cards: continue
    e = copy.deepcopy(tmpl)
    e["trained_chara_id"] = next_id
    e["owner_viewer_id"] = vid
    e["owner_trained_chara_id"] = next_id
    e["viewer_id"] = vid
    e["card_id"] = cid
    e["single_mode_chara_id"] = cid // 100
    # stats al maximo
    for s in ("speed", "stamina", "power", "wiz", "guts"):
        if s in e: e[s] = 1200
    e["rank_score"] = 20000
    e["rank"] = 1
    e["fans"] = 9999999
    e["rarity"] = 5
    e["talent_level"] = 5
    e["chara_grade"] = 6 if "chara_grade" in e else e.get("chara_grade")
    e["is_saved"] = 1
    e["is_locked"] = 0
    e["wins"] = 99
    next_id += 1; added += 1
    d["trained_chara"].append(e)

open(STATE, "wb").write(msgpack.packb(st, use_bin_type=True))
print(f"trained_chara: +{added} (total {len(d['trained_chara'])}) — umas entrenadas para correr, stats max")
