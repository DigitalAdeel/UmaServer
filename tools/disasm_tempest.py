import sys, pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_MEM, CS_OP_REG, CS_OP_IMM

DLL = r"C:\Program Files (x86)\Steam\steamapps\common\UmamusumePrettyDerby\UmamusumePrettyDerby_Data\Plugins\x86_64\libnative_orig.dll"
TARGETS = sys.argv[1:] or ["tempest_register_request_raw", "tempest_query_progress_raw"]

pe = pefile.PE(DLL, fast_load=True)
pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
image_base = pe.OPTIONAL_HEADER.ImageBase

exports = {}
for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
    if e.name:
        exports[e.name.decode()] = e.address  # RVA

data = pe.get_memory_mapped_image()  # indexed by RVA
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True

ARG_REGS = ["rcx", "rdx", "r8", "r9"]
SUB32 = {"ecx":"rcx","edx":"rdx","r8d":"r8","r9d":"r9","cl":"rcx","dl":"rdx","r8b":"r8","r9b":"r9",
         "cx":"rcx","dx":"rdx","r8w":"r8","r9w":"r9"}
def norm(r): return SUB32.get(r, r)

def analyze(name):
    rva = exports.get(name)
    if rva is None:
        print(f"[!] {name}: no export"); return
    print(f"\n================= {name}  (RVA 0x{rva:x}, VA 0x{image_base+rva:x}) =================")
    code = data[rva: rva + 0x600]
    first_use = {}      # reg -> 'read'|'write' (primer uso)
    deref = set()       # regs usados como [reg...] (puntero)
    stack_args = set()  # offsets [rsp+0xNN] leidos (args 5+)
    count = 0
    for ins in md.disasm(code, image_base + rva):
        count += 1
        line = f"  0x{ins.address:x}: {ins.mnemonic} {ins.op_str}"
        print(line)
        # analisis de operandos
        regs_read, regs_written = ins.regs_access()
        for r in regs_read:
            rn = norm(ins.reg_name(r) or "")
            if rn in ARG_REGS and rn not in first_use:
                first_use[rn] = "read"
        for r in regs_written:
            rn = norm(ins.reg_name(r) or "")
            if rn in ARG_REGS and rn not in first_use:
                first_use[rn] = "write"
        for op in ins.operands:
            if op.type == CS_OP_MEM:
                base = norm(ins.reg_name(op.mem.base) or "")
                if base in ARG_REGS:
                    deref.add(base)
                if base == "rsp" and op.mem.disp >= 0x28:
                    stack_args.add(op.mem.disp)
        if ins.mnemonic == "ret":
            break
        if count > 220:
            print("   ... (cortado)")
            break
    print(f"\n  --- resumen {name} ---")
    args_in = [r for r in ARG_REGS if first_use.get(r) == "read"]
    print(f"  args entrantes (reg leido antes de escribir): {args_in}")
    print(f"  usados como puntero (deref): {sorted(deref)}")
    print(f"  stack args [rsp+off] leidos: {sorted(hex(x) for x in stack_args)}")
    nstack = len(stack_args)
    print(f"  aridad estimada: {len(args_in)} en registros + ~{nstack} en stack = ~{len(args_in)+nstack}")

for t in TARGETS:
    analyze(t)
