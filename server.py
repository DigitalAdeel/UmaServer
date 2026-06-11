#!/usr/bin/env python3
# UmaServer (python) — servidor privado Umamusume con ESTADO PERSISTENTE.
# El cliente (proxy en modo live) habla MessagePack plano. Python re-serializa
# byte-fiel al oficial, asi que podemos generar respuestas DINAMICAS que el
# cliente acepta -> guardado real del estado de cuenta.
#
# Estado persistente: account_state.mp (el "data" de load/index). Se inicializa
# del seed oficial + overrides de account.db. Las mutaciones (gacha, perfil,
# mazos...) se guardan a disco.
import os, time, msgpack, sqlite3, threading, random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
SEEDS = os.path.join(BASE, "seeds")
STATE_FILE = os.path.join(BASE, "account_state.mp")
DB = os.path.join(BASE, "account.db")
LOCK = threading.Lock()

def seed_path(rel): return os.path.join(SEEDS, rel.replace("/", "_") + ".resp.bin")
def load_seed(rel):
    p = seed_path(rel)
    if os.path.exists(p):
        return msgpack.unpackb(open(p, "rb").read(), raw=False, strict_map_key=False)
    return None

def db_overrides():
    ov = {"carats": 999999, "cards": [], "support_cards": [], "items": {}}
    if os.path.exists(DB):
        con = sqlite3.connect(DB)
        r = con.execute("SELECT value FROM kv WHERE key='carats'").fetchone()
        if r: ov["carats"] = r[0]
        ov["cards"] = [row for row in con.execute("SELECT card_id,rarity,talent_level FROM cards")]
        ov["support_cards"] = [row for row in con.execute("SELECT support_card_id,exp,limit_break_count FROM support_cards")]
        ov["items"] = {row[0]: row[1] for row in con.execute("SELECT item_id,number FROM items")}
        con.close()
    return ov

def init_state():
    """Estado = data de load/index oficial + overrides de account.db."""
    base = load_seed("load_index.official") or load_seed("load_index")
    data = base["data"]
    ov = db_overrides()
    data.setdefault("coin_info", {})["fcoin"] = ov["carats"]
    NOW = "2026-06-10 00:00:00"
    owned = {c["card_id"] for c in data.get("card_list", [])}
    for (cid, r, t) in ov["cards"]:
        if cid not in owned:
            data["card_list"].append({"card_id": cid, "rarity": 5, "talent_level": 5,
                                      "create_time": NOW, "skill_data_array": []})
    # chara_list: todos los charas (chara_id = card_id//100) -> seccion "Umas"
    all_charas = sorted(set(c["card_id"] // 100 for c in data.get("card_list", [])))
    hch = {c["chara_id"] for c in data.get("chara_list", [])}
    for ch in all_charas:
        if ch not in hch:
            data.setdefault("chara_list", []).append({"chara_id": ch, "training_num": 0,
                "love_point": 0, "fan": 1, "max_grade": 5, "dress_id": 2, "mini_dress_id": 2})
    vid = data.get("user_info", {}).get("viewer_id", 0)
    osup = {s["support_card_id"] for s in data.get("support_card_list", [])}
    for (sid, exp, lb) in ov["support_cards"]:
        if sid not in osup:
            data["support_card_list"].append({"viewer_id": vid, "support_card_id": sid, "exp": exp,
                "limit_break_count": lb, "favorite_flag": 0, "stock": 0,
                "possess_time": NOW, "create_time": NOW})
    if ov["items"]:
        present = {it["item_id"]: it for it in data.get("item_list", [])}
        for iid, num in ov["items"].items():
            if iid in present: present[iid]["number"] = num
            else: data["item_list"].append({"item_id": iid, "number": num})
    return base   # envelope completo (data_headers + data)

def load_state():
    if os.path.exists(STATE_FILE):
        return msgpack.unpackb(open(STATE_FILE, "rb").read(), raw=False, strict_map_key=False)
    st = init_state(); save_state(st); return st

def save_state(st):
    tmp = STATE_FILE + ".tmp"
    open(tmp, "wb").write(msgpack.packb(st, use_bin_type=True))
    os.replace(tmp, STATE_FILE)

STATE = load_state()

def fresh_headers(src_headers=None):
    h = dict(src_headers) if src_headers else {}
    h["servertime"] = int(time.time())
    h.setdefault("result_code", 1)
    return h

def pack(o): return msgpack.packb(o, use_bin_type=True)

# ---------------- handlers ----------------
def h_load_index(req):
    with LOCK:
        STATE["data_headers"] = fresh_headers(STATE.get("data_headers"))
        return pack(STATE)

def h_gacha_exec(req):
    dn = int(req.get("draw_num", 1))
    seed = load_seed(f"gacha_exec.d{dn}") or load_seed("gacha_exec")
    if not seed: return None
    data = seed["data"]
    with LOCK:
        # personajes que ya posees -> variar entre ellos (no congela)
        owned = [c["card_id"] for c in STATE["data"].get("card_list", [])]
        if owned and data.get("gacha_result_list"):
            for e in data["gacha_result_list"]:
                cid = random.choice(owned); e["card_id"] = cid; e["piece_id"] = cid; e["new_flag"] = 0
        # carats siempre 999999
        if "coin_info" in data: data["coin_info"]["fcoin"] = 999999
        seed["data_headers"] = fresh_headers(seed.get("data_headers"))
    return pack(seed)

def mut_user_info(updates):
    with LOCK:
        ui = STATE["data"].setdefault("user_info", {})
        for k, v in updates.items():
            if v is not None: ui[k] = v
        save_state(STATE)

def mut_data(key, value):
    if value is None: return
    with LOCK:
        STATE["data"][key] = value
        save_state(STATE)

def ack(rel, data_overrides=None):
    """Respuesta de confirmacion (captura del endpoint, headers frescos). data_overrides
    sustituye claves en data por los valores NUEVOS, para que el cliente refleje el cambio."""
    seed = load_seed(rel) or {"response_code": 1, "data_headers": {}, "data": {}}
    if isinstance(seed, dict):
        seed["data_headers"] = fresh_headers(seed.get("data_headers"))
        d = seed.setdefault("data", {})
        if "coin_info" in d: d["coin_info"]["fcoin"] = 999999
        if data_overrides:
            for k, v in data_overrides.items():
                if v is not None: d[k] = v
    return pack(seed)

# rutas -> handler (las que mutan estado se guardan a disco)
def dispatch(rel, req):
    if rel == "load/index": return h_load_index(req)
    if rel == "gacha/exec": return h_gacha_exec(req)

    # --- acciones de perfil/usuario que PERSISTEN ---
    if rel == "user/change_name":            mut_user_info({"name": req.get("name")}); return ack(rel)
    if rel == "user/change_comment":         mut_user_info({"comment": req.get("comment")}); return ack(rel)
    if rel == "user/change_leader_card":     mut_user_info({"leader_chara_id": req.get("chara_id"), "leader_chara_dress_id": req.get("dress_id")}); return ack(rel, {"user_info": STATE["data"].get("user_info")})
    if rel == "user/change_support_card":    mut_user_info({"support_card_id": req.get("support_card_id")}); return ack(rel, {"user_info": STATE["data"].get("user_info")})
    if rel == "user/change_practice_partner":mut_user_info({"partner_chara_id": req.get("trained_chara_id")}); return ack(rel, {"user_info": STATE["data"].get("user_info")})
    if rel == "honor/change_honor":          mut_user_info({"honor_id": req.get("honor_id")}); return ack(rel, {"user_info": STATE["data"].get("user_info")})
    if rel == "user/change_favorite_character":
        spi = req.get("set_position_info")
        valid_ch = {c["card_id"] // 100 for c in STATE["data"].get("card_list", [])}
        if isinstance(spi, dict):  # solo aceptar charas que existen en el roster (evita Now Loading)
            for k in [k for k in spi if k.endswith("_chara_id")]:
                if spi[k] not in valid_ch: spi[k] = 0
        mut_data("home_position_info", spi); return ack(rel, {"home_position_info": spi})
    if rel == "support_card_deck/change_party": mut_data("support_card_deck_array", req.get("support_card_deck_array")); return ack(rel)

    # fallback: servir seed crudo (carats parcheados + servertime fresco)
    seed = load_seed(rel)
    if seed is not None:
        if isinstance(seed, dict):
            if "coin_info" in seed.get("data", {}): seed["data"]["coin_info"]["fcoin"] = 999999
            seed["data_headers"] = fresh_headers(seed.get("data_headers"))
        return pack(seed)
    return pack({"response_code": 1, "data_headers": fresh_headers(), "data": {}})

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"UmaServer python OK")
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n) if n else b""
        rel = self.path.lstrip("/")
        if rel.startswith("umamusume/"): rel = rel[len("umamusume/"):]
        try: req = msgpack.unpackb(body, raw=False, strict_map_key=False) if body else {}
        except Exception: req = {}
        if not isinstance(req, dict): req = {}
        try:
            lrd = os.path.join(BASE, "live_requests"); os.makedirs(lrd, exist_ok=True)
            open(os.path.join(lrd, rel.replace("/", "_") + ".req.bin"), "wb").write(body)
        except Exception: pass
        try: resp = dispatch(rel, req)
        except Exception as e:
            print("ERR", rel, e); resp = pack({"response_code":1,"data_headers":fresh_headers(),"data":{}})
        print(f"{rel} -> {len(resp)}B")
        self.send_response(200); self.send_header("Content-Type","application/x-msgpack")
        self.send_header("Content-Length", str(len(resp))); self.end_headers(); self.wfile.write(resp)

if __name__ == "__main__":
    print(f"UmaServer python :5090  cards={len(STATE['data'].get('card_list',[]))} carats={STATE['data'].get('coin_info',{}).get('fcoin')}")
    ThreadingHTTPServer(("0.0.0.0", 5090), H).serve_forever()
