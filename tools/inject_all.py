#!/usr/bin/env python3
# Inyecta TODOS los card_id de release_card_array (no poseidos) en data.card_list
# del seed load/index, en UNA pasada (cirugia binaria, sin re-serializar el resto).
import msgpack, os
SEED = os.path.join(os.path.dirname(__file__), "..", "seeds", "load_index.resp.bin")
raw = bytearray(open(SEED, "rb").read())

# pool a inyectar: release_card_array - card_list actuales
o = msgpack.unpackb(bytes(raw), raw=False, strict_map_key=False)["data"]
owned = set(c["card_id"] for c in o["card_list"])
release = [c for c in o["release_card_array"] if isinstance(c, int) and c not in owned]
print("ya en card_list:", len(owned), "| a inyectar:", len(release))
if not release:
    print("nada que inyectar"); raise SystemExit

KEY = b"\xa9card_list"
idx = raw.find(KEY); ap = idx + len(KEY); hdr = raw[ap]
if hdr == 0xdc:
    count = (raw[ap+1] << 8) | raw[ap+2]; data_start = ap + 3
elif 0x90 <= hdr <= 0x9f:
    count = hdr & 0x0f; data_start = ap + 1
else:
    print("header inesperado", hex(hdr)); raise SystemExit
u = msgpack.Unpacker(raw=False, strict_map_key=False); u.feed(bytes(raw[data_start:]))
for _ in range(count): u.unpack()
end = data_start + u.tell()

blob = bytearray()
for cid in release:
    blob += msgpack.packb({"card_id": cid, "rarity": 3, "talent_level": 1,
                           "create_time": "2026-06-10 14:45:31", "skill_data_array": []},
                          use_bin_type=True)
newcount = count + len(release)
# reescribir como array16/array32
if newcount <= 0xffff:
    raw[ap:data_start] = bytes([0xdc, (newcount >> 8) & 0xff, newcount & 0xff])
else:
    raw[ap:data_start] = bytes([0xdd]) + newcount.to_bytes(4, "big")
# recomputar end por si cambio el header len
shift = (ap + (3 if newcount <= 0xffff else 5)) - data_start
end += shift
raw[end:end] = blob
open(SEED, "wb").write(raw)

o2 = msgpack.unpackb(bytes(raw), raw=False, strict_map_key=False)
print("card_list final:", len(o2["data"]["card_list"]), "| parse OK")
