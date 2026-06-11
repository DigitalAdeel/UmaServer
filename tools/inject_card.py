#!/usr/bin/env python3
# Inyecta un card_id en data.card_list del seed load/index por CIRUGIA BINARIA
# (sin re-serializar el resto: el cliente valida los bytes oficiales).
# Uso: python inject_card.py <card_id> [rarity] [talent_level]
import sys, msgpack, os
SEED = os.path.join(os.path.dirname(__file__), "..", "seeds", "load_index.resp.bin")
card_id = int(sys.argv[1]); rarity = int(sys.argv[2]) if len(sys.argv) > 2 else 3
talent = int(sys.argv[3]) if len(sys.argv) > 3 else 1

raw = bytearray(open(SEED, "rb").read())
KEY = b"\xa9card_list"          # 0xa9 + "card_list"
idx = raw.find(KEY)
if idx < 0: print("card_list no encontrado"); sys.exit(1)
ap = idx + len(KEY)             # posicion del header de array
hdr = raw[ap]
if hdr == 0xdc:                 # array16: 0xdc + uint16 count
    count = (raw[ap+1] << 8) | raw[ap+2]; data_start = ap + 3; hdrlen = 3
elif 0x90 <= hdr <= 0x9f:       # fixarray
    count = hdr & 0x0f; data_start = ap + 1; hdrlen = 1
else:
    print("header de array inesperado:", hex(hdr)); sys.exit(1)
print("card_list count actual:", count)

# consumir 'count' elementos para hallar el fin del array
u = msgpack.Unpacker(raw=False, strict_map_key=False); u.feed(bytes(raw[data_start:]))
for _ in range(count): u.unpack()
end = data_start + u.tell()     # offset donde termina el array (insertamos aqui)

# ya existe?
existing = msgpack.unpackb(bytes(raw[data_start:end]) if False else b"\x90")  # noop
# nuevo elemento (mismo formato que card_list[0])
entry = {"card_id": card_id, "rarity": rarity, "talent_level": talent,
         "create_time": "2026-06-10 14:45:31", "skill_data_array": []}
elem = msgpack.packb(entry, use_bin_type=True)

# incrementar count
newcount = count + 1
if hdr == 0xdc:
    raw[ap+1] = (newcount >> 8) & 0xff; raw[ap+2] = newcount & 0xff
else:
    if newcount <= 15: raw[ap] = 0x90 | newcount
    else:  # promover fixarray->array16
        raw[ap:ap+1] = bytes([0xdc, (newcount >> 8) & 0xff, newcount & 0xff]); end += 2
# insertar elemento al final del array
raw[end:end] = elem
open(SEED, "wb").write(raw)

# verificar
o = msgpack.unpackb(bytes(raw), raw=False, strict_map_key=False)
ids = [c.get("card_id") for c in o["data"]["card_list"]]
print("card_list nuevo count:", len(ids), "| incluye", card_id, ":", card_id in ids)
