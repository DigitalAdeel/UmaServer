import pefile, struct
from collections import Counter

DLL = r"C:\Program Files (x86)\Steam\steamapps\common\UmamusumePrettyDerby\UnityPlayer.dll"

# Constantes CURLOPT conocidas (valor -> nombre)
CURLOPTS = {
    10002:"URL", 10015:"POSTFIELDS", 10023:"HTTPHEADER", 10018:"USERAGENT",
    10001:"WRITEDATA", 20011:"WRITEFUNCTION", 10052:"CAINFO", 10082:"COPYPOSTFIELDS",
    20056:"XFERINFOFUNCTION", 10057:"XFERINFODATA", 47:"POST", 81:"SSL_VERIFYHOST",
    64:"SSL_VERIFYPEER", 10009:"COOKIE", 84:"HTTP_VERSION", 78:"CONNECTTIMEOUT",
    13:"TIMEOUT", 19913:"NOPROGRESS",
}
pe = pefile.PE(DLL, fast_load=True)
ib = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if b'.text' in s.Name)
base_rva = text.VirtualAddress
data = text.get_data()
print(f"ImageBase 0x{ib:x}  .text RVA 0x{base_rva:x}  size 0x{len(data):x}")

# Buscar 'mov edx, imm32' = 0xBA imm32  con imm en CURLOPTS, luego 'call rel32' (0xE8) cercano.
hits = Counter()           # target_rva -> count
opt_seen = {}              # target_rva -> set de opciones
for i in range(len(data) - 5):
    if data[i] != 0xBA:
        continue
    imm = struct.unpack_from('<I', data, i+1)[0]
    if imm not in CURLOPTS:
        continue
    # buscar call E8 en los siguientes 40 bytes
    for j in range(i+5, min(i+45, len(data)-5)):
        if data[j] == 0xE8:
            rel = struct.unpack_from('<i', data, j+1)[0]
            call_rva = base_rva + j + 5 + rel       # destino
            hits[call_rva] += 1
            opt_seen.setdefault(call_rva, set()).add(CURLOPTS[imm])
            break

print("\nTop candidatos a curl_easy_setopt (call mas frecuente tras mov edx,CURLOPT):")
for rva, c in hits.most_common(8):
    opts = ",".join(sorted(opt_seen[rva]))
    print(f"  RVA 0x{rva:<8x} VA 0x{ib+rva:<12x} hits={c:<4} opts={{{opts}}}")
