#!/usr/bin/env python3
# Correlaciona capturas (umma/capture) -> seeds (umma/seeds) emparejando el texto base64:
#   api_<seq>_req.bin (curl)  == compreq_out_<n> (HttpHelper)  -> liga URL con compreq_in (request claro)
#   api_<seq>_resp.bin (curl) == decresp_in_<n> (HttpHelper)   -> liga URL con decresp_out (response claro)
# Guarda bytes oficiales CRUDOS (primer objeto MessagePack completo).
# gacha/exec se guarda ademas con sufijo de draw_num: gacha_exec.d<N>.resp.bin
import glob, os, msgpack
CAP = os.path.join(os.path.dirname(__file__), "..", "capture")
SEED = os.path.join(os.path.dirname(__file__), "..", "seeds")
os.makedirs(SEED, exist_ok=True)
def rd(f): return open(f, "rb").read()
def first_obj(raw):
    u = msgpack.Unpacker(raw=False, strict_map_key=False); u.feed(raw)
    try: u.unpack(); return raw[:u.tell()]
    except: return raw
g = lambda pat: glob.glob(os.path.join(CAP, pat))
urls  = {f.split("_")[-2] if False else os.path.basename(f).split("_")[1]: rd(f).decode("utf8","replace").strip() for f in g("api_*_url.txt")}
creq  = {os.path.basename(f).split("_")[1]: rd(f) for f in g("api_*_req.bin")}
cresp = {os.path.basename(f).split("_")[1]: rd(f) for f in g("api_*_resp.bin")}
def keyn(f): return os.path.basename(f).split("_")[2].split(".")[0]
preq  = {keyn(f): rd(f) for f in g("compreq_in_*.bin")}
preqB = {keyn(f): rd(f) for f in g("compreq_out_*.bin")}
presp = {keyn(f): rd(f) for f in g("decresp_out_*.bin")}
prespB= {keyn(f): rd(f) for f in g("decresp_in_*.bin")}
def match(b, m):
    for k, v in m.items():
        if v == b: return k
    return None
n = 0
for s, url in sorted(urls.items(), key=lambda x: int(x[0])):
    path = url.split("/umamusume/", 1)[-1] if "/umamusume/" in url else url
    safe = path.replace("/", "_")
    rj = match(cresp.get(s, b"_"), prespB)
    pj = match(creq.get(s, b"_"), preqB)
    reqobj = None
    if pj and pj in preq:
        raw = first_obj(preq[pj]); open(os.path.join(SEED, safe + ".req.bin"), "wb").write(raw)
        try: reqobj = msgpack.unpackb(raw, raw=False, strict_map_key=False)
        except: pass
    if rj and rj in presp:
        raw = first_obj(presp[rj]); open(os.path.join(SEED, safe + ".resp.bin"), "wb").write(raw); n += 1
        # gacha/exec: guardar variante por draw_num
        if path == "gacha/exec" and isinstance(reqobj, dict) and "draw_num" in reqobj:
            dn = reqobj["draw_num"]
            open(os.path.join(SEED, f"gacha_exec.d{dn}.resp.bin"), "wb").write(raw)
            print(f"  gacha/exec draw_num={dn} -> gacha_exec.d{dn}.resp.bin")
        print(f"  {path:38} resp={len(raw)}B")
print(f"\nseeds resp: {n}")
