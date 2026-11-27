#!/usr/bin/env python3
"""
data_objects.py - M2: object (translation-unit) layout of .rodata/.data/.bss.

Fire Emblem: Awakening (CTR-P-AFEE), armcc/armlink build, pure ARM.
Python 3.13 standard library only.  Read-only on extracted/ and build/cache/.

Writes
    config/naming/data_objects.csv      segment,start,end,object,confidence,evidence,
                                        unit_id,tu,split_confidence
    config/naming/data_units.csv        unit_id,segment,start,end,tu,split_confidence,evidence
                                        (one row per split unit = one data_objects row)
    docs/analysis/M2_data_layout.md     findings (generated, deterministic)
    build/m2_data/*.txt|json            scratch / diagnostics (not tracked)

Method (summary; details in the generated markdown)
  1. Decode every function linearly and track registers loaded from literal
     pools (ARMv6K has no MOVW/MOVT, so every absolute address comes from a
     literal).  A literal value V that lies in .rodata/.data/.bss is a "base";
     loads/stores/ADD/LDM/VLDR through that register give touched addresses
     V+off.  Everything touched through one base belongs to the same object
     file (armcc addresses statics as section-base + offset, externs as
     symbol + offset), so [V, max touched end) is an indivisible "atom".
  2. The C++ static-init table (356 self-relative entries at 0x4595F8) gives one
     init function per translation unit.  The bases each init function uses
     rise monotonically with the table index in .data, .bss and the per-object
     .rodata region -> the table is in object (link) order, so every entry is
     an ordered TU anchor in all three segments.
  3. Functions get labels: class (virtual-function ownership, vtable address
     loads in ctors/dtors, lexical name coordinate from split_candidates.json),
     library (config/naming/library.csv), init TU.
  4. Each atom is labelled by who references it: the init TU that owns it, the
     single class/library family whose functions reference it exclusively, or
     unknown.  Runs of equally labelled atoms become object rows; gaps become
     "unknown" rows, so rows tile each segment.
"""
import sys as _sys  # noqa: E402
if "--awakening-pass" not in _sys.argv:  # Fates: names come from the shipped symbol map
    _sys.exit("tools/m2/data_objects.py is the Awakening RTTI/heuristic naming pass and still holds "
              "Awakening addresses; it would write wrong rows for Fates. Fates names come "
              "from the shipped symbol map: python tools/fates/symbols.py (docs/SYMBOLS.md).")
import bisect
import collections
import csv
import json
import os
import random
import re
import struct

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
P = lambda *a: os.path.join(ROOT, *a)
OUT_CSV = P("config", "naming", "data_objects.csv")
OUT_UNITS = P("config", "naming", "data_units.csv")
OUT_MD = P("docs", "analysis", "M2_data_layout.md")
SCRATCH = P("build", "m2_data")

TEXT_VA, TEXT_SZ, TEXT_OFF = 0x00100000, 0x359B88, 0x000000
RO_VA, RO_SZ, RO_OFF = 0x0045A000, 0x05BA88, 0x35A000
DATA_VA, DATA_SZ, DATA_OFF = 0x004B6000, 0x0314E8, 0x3B6000
BSS_VA, BSS_SZ = 0x004E74E8, 0x3BD24
TEXT_END, RO_END, DATA_END, BSS_END = (TEXT_VA + TEXT_SZ, RO_VA + RO_SZ,
                                       DATA_VA + DATA_SZ, BSS_VA + BSS_SZ)
INIT_RUNNER, INIT_LO, INIT_HI = 0x004595B8, 0x004595F8, 0x00459B88
MAX_OFF = 0x40000          # largest base+offset accepted as "same object"

code = open(P("extracted", "code.bin"), "rb").read()
assert len(code) == 4096000, "unexpected code.bin size"
ana = json.load(open(P("build", "cache", "analysis.json")))
FUNCS = ana["funcs"]
CODE_RANGES = sorted(tuple(r) for r in ana["code_ranges"])
SC = json.load(open(P("extracted", "analysis", "split_candidates.json")))


def seg_of(a):
    if TEXT_VA <= a < TEXT_END: return "text"
    if RO_VA <= a < RO_END: return "rodata"
    if DATA_VA <= a < DATA_END: return "data"
    if BSS_VA <= a < BSS_END: return "bss"
    return None


def word(a):
    if TEXT_VA <= a <= TEXT_END - 4: return struct.unpack_from("<I", code, TEXT_OFF + a - TEXT_VA)[0]
    if RO_VA <= a <= RO_END - 4: return struct.unpack_from("<I", code, RO_OFF + a - RO_VA)[0]
    if DATA_VA <= a <= DATA_END - 4: return struct.unpack_from("<I", code, DATA_OFF + a - DATA_VA)[0]
    return None


def s32(x): return x - (1 << 32) if x & 0x80000000 else x
def H(a): return "0x%08X" % a


def func_of(a):
    k = bisect.bisect_right(FUNCS, a) - 1
    return FUNCS[k] if k >= 0 else None


def func_end(f):
    k = bisect.bisect_right(FUNCS, f)
    return FUNCS[k] if k < len(FUNCS) else TEXT_END


def cstr_at(a, maxlen=200):
    """bytes of a NUL-terminated printable string at a (rodata/data), else None"""
    s = seg_of(a)
    if s == "rodata": off, end = RO_OFF + a - RO_VA, RO_OFF + RO_SZ
    elif s == "data": off, end = DATA_OFF + a - DATA_VA, DATA_OFF + DATA_SZ
    else: return None
    b = code[off:min(end, off + maxlen)]
    n = b.find(b"\0")
    if n < 4: return None
    b = b[:n]
    if all(32 <= c < 127 for c in b): return b.decode("ascii")
    return None


def u16str_at(a, maxlen=200):
    s = seg_of(a)
    if s != "rodata": return None
    off = RO_OFF + a - RO_VA
    out = []
    for k in range(maxlen):
        c = struct.unpack_from("<H", code, off + 2 * k)[0]
        if c == 0: break
        if not 32 <= c < 127: return None
        out.append(chr(c))
    return "".join(out) if len(out) >= 4 else None


# ---------------------------------------------------------------------------
# 1. linear decode: literal bases and touched addresses per function
# ---------------------------------------------------------------------------
CALLER_SAVED = (0, 1, 2, 3, 12, 14)


def rot_imm(w):
    r = ((w >> 8) & 15) * 2
    v = w & 0xFF
    return ((v >> r) | (v << (32 - r))) & 0xFFFFFFFF if r else v


def decode_all():
    touches = collections.defaultdict(list)    # f -> [(base, addr, size, kind)]
    calls = collections.defaultdict(set)       # f -> BL targets
    adr_text = collections.defaultdict(set)    # f -> text addresses loaded (ADR / literal)
    last_f = None
    regs = {}
    for lo, hi in CODE_RANGES:
        for pc in range(lo, hi, 4):
            f = func_of(pc)
            if f != last_f:
                regs = {}
                last_f = f
            w = struct.unpack_from("<I", code, TEXT_OFF + pc - TEXT_VA)[0]
            cond = w >> 28
            if cond == 0xF:
                continue
            op = (w >> 25) & 7
            rd = (w >> 12) & 15
            rn = (w >> 16) & 15
            if (w & 0x0F5F0000) == 0x051F0000:          # LDR Rd,[PC,#imm]
                imm = w & 0xFFF
                la = pc + 8 + (imm if (w >> 23) & 1 else -imm)
                v = word(la)
                if rd == 15:
                    regs = {}
                    continue
                if v is not None and seg_of(v) in ("rodata", "data", "bss"):
                    regs[rd] = (v, v)
                    touches[f].append((v, v, 0, "lit"))
                else:
                    regs.pop(rd, None)
                    if v is not None and seg_of(v) == "text":
                        adr_text[f].add(v)
                continue
            if op == 2:                                  # LDR/STR imm
                P_, U, B, W, L = (w >> 24) & 1, (w >> 23) & 1, (w >> 22) & 1, (w >> 21) & 1, (w >> 20) & 1
                imm = w & 0xFFF
                if rn in regs and P_ and U:
                    base, cur = regs[rn]
                    a = cur + imm
                    if 0 <= a - base < MAX_OFF:
                        touches[f].append((base, a, 1 if B else 4, "ld" if L else "st"))
                if W or not P_: regs.pop(rn, None)
                if L:
                    regs.pop(rd, None)
                    if rd == 15: regs = {}
                continue
            if op == 3:                                  # LDR/STR reg offset, media
                if (w >> 4) & 1:
                    regs.pop(rd, None); regs.pop(rn, None)
                    continue
                if (w >> 21) & 1 or not (w >> 24) & 1: regs.pop(rn, None)
                if (w >> 20) & 1:
                    regs.pop(rd, None)
                    if rd == 15: regs = {}
                continue
            if op == 0:
                if (w & 0x90) == 0x90 and (w & 0x60) != 0:   # extra load/store
                    P_, U, I, W, L = (w >> 24) & 1, (w >> 23) & 1, (w >> 22) & 1, (w >> 21) & 1, (w >> 20) & 1
                    sh = (w >> 5) & 3
                    if I and P_ and U and rn in regs:
                        imm = ((w >> 4) & 0xF0) | (w & 0xF)
                        size = {1: 2, 2: (1 if L else 8), 3: (2 if L else 8)}[sh]
                        base, cur = regs[rn]
                        a = cur + imm
                        if 0 <= a - base < MAX_OFF:
                            touches[f].append((base, a, size, "ld" if L or sh == 2 else "st"))
                    if W or not P_: regs.pop(rn, None)
                    if L or sh == 2:
                        regs.pop(rd, None); regs.pop(rd + 1, None)
                    continue
                if (w & 0x0FC000F0) == 0x00000090:             # MUL/MLA
                    regs.pop(rn, None); continue
                if (w & 0x0F8000F0) == 0x00800090:             # long multiply
                    regs.pop(rn, None); regs.pop(rd, None); continue
                if (w & 0x0FB00FF0) == 0x01000090:             # SWP
                    regs.pop(rd, None); continue
                if (w & 0x0F900000) == 0x01000000:             # misc
                    if (w & 0x0FFFFFF0) == 0x012FFF30:         # BLX reg
                        for r in CALLER_SAVED: regs.pop(r, None)
                    elif (w & 0x0FFFFFF0) == 0x012FFF10:       # BX
                        if cond == 0xE: regs = {}
                    else:
                        regs.pop(rd, None)
                    continue
                opc = (w >> 21) & 15
                if 8 <= opc <= 11:
                    continue
                if opc == 13 and (w & 0xFF0) == 0:              # MOV Rd,Rm
                    rm = w & 15
                    if rm in regs: regs[rd] = regs[rm]
                    else: regs.pop(rd, None)
                else:
                    regs.pop(rd, None)
                if rd == 15: regs = {}
                continue
            if op == 1:                                  # data-processing immediate
                if (w & 0x0FB00000) == 0x03200000:          # MSR imm / hints
                    continue
                opc = (w >> 21) & 15
                if 8 <= opc <= 11:
                    continue
                imm = rot_imm(w)
                if opc == 4 and rn in regs:
                    base, cur = regs[rn]
                    v = cur + imm
                    if 0 <= v - base < MAX_OFF:
                        regs[rd] = (base, v)
                        touches[f].append((base, v, 0, "add"))
                    else:
                        regs.pop(rd, None)
                elif opc == 2 and rn in regs:
                    base, cur = regs[rn]
                    v = cur - imm
                    if 0 <= v - base < MAX_OFF:
                        regs[rd] = (base, v)
                    else:
                        regs.pop(rd, None)
                else:
                    if rn == 15 and opc in (2, 4):
                        adr_text[f].add(pc + 8 + (imm if opc == 4 else -imm))
                    regs.pop(rd, None)
                if rd == 15: regs = {}
                continue
            if op == 4:                                  # LDM/STM
                P_, U, W, L = (w >> 24) & 1, (w >> 23) & 1, (w >> 21) & 1, (w >> 20) & 1
                rl = w & 0xFFFF
                n = bin(rl).count("1")
                if rn in regs and U and rn != 13:
                    base, cur = regs[rn]
                    a = cur + (4 if P_ else 0)
                    if 0 <= a - base < MAX_OFF:
                        touches[f].append((base, a, 4 * n, "ldm" if L else "stm"))
                if W: regs.pop(rn, None)
                if L:
                    for r in range(16):
                        if rl >> r & 1: regs.pop(r, None)
                    if rl & 0x8000: regs = {}
                continue
            if op == 5:                                  # B/BL
                if (w >> 24) & 1:
                    tgt = (pc + 8 + (s32((w & 0xFFFFFF) << 8) >> 6)) & 0xFFFFFFFF
                    calls[f].add(tgt)
                    for r in CALLER_SAVED: regs.pop(r, None)
                elif cond == 0xE:
                    regs = {}
                continue
            if op == 6:                                  # coprocessor load/store (VFP)
                P_, U, W, L = (w >> 24) & 1, (w >> 23) & 1, (w >> 21) & 1, (w >> 20) & 1
                cp = (w >> 8) & 15
                imm8 = w & 0xFF
                if cp in (10, 11) and rn in regs and rn != 15:
                    base, cur = regs[rn]
                    if P_ and not W and U:
                        a = cur + imm8 * 4
                        if 0 <= a - base < MAX_OFF:
                            touches[f].append((base, a, 8 if cp == 11 else 4, "vld" if L else "vst"))
                    elif not P_ and U:
                        touches[f].append((base, cur, imm8 * 4, "vldm" if L else "vstm"))
                if W: regs.pop(rn, None)
                continue
            if op == 7:
                if not (w >> 24) & 1 and (w >> 4) & 1 and (w >> 20) & 1:
                    regs.pop(rd, None)                   # MRC / VMOV core<-VFP
                continue
    return touches, calls, adr_text


TOUCHES, CALLS, ADR_TEXT = decode_all()

# ---------------------------------------------------------------------------
# 2. atoms: [base, max touched end) per base, unioned over all functions
# ---------------------------------------------------------------------------
base_end = {}
base_funcs = collections.defaultdict(set)
for f, lst in TOUCHES.items():
    for base, a, size, kind in lst:
        e = a + max(size, 1)
        if base_end.get(base, 0) < e: base_end[base] = e
        base_funcs[base].add(f)
# A base used only as an address (nothing read beyond its first byte) that points at a
# printable NUL-terminated string covers the whole string: the object runs through the NUL.
# Without this a string atom is 1 byte long and every row end after it looks like a gap.
n_str_ext = 0
for base in list(base_end):
    if base_end[base] != base + 1 or seg_of(base) not in ("rodata", "data"): continue
    s8 = cstr_at(base, 4096)
    if s8 is not None:
        base_end[base] = base + len(s8) + 1; n_str_ext += 1
        continue
    s16 = u16str_at(base, 2048)
    if s16 is not None:
        base_end[base] = base + 2 * (len(s16) + 1); n_str_ext += 1


def build_atoms(lo, hi):
    iv = sorted((b, min(e, hi)) for b, e in base_end.items() if lo <= b < hi)
    atoms = []
    for b, e in iv:
        if atoms and b < atoms[-1][1]:
            atoms[-1][1] = max(atoms[-1][1], e)
            atoms[-1][2].append(b)
        else:
            atoms.append([b, e, [b]])
    return atoms


# ---------------------------------------------------------------------------
# 3. rodata structure: per-object .constdata, COMDAT RTTI, vtables, tail
# ---------------------------------------------------------------------------
rtti = list(csv.DictReader(open(P("extracted", "analysis", "rtti_classes.csv"))))
ti_addr = {int(r["typeinfo"], 16): r for r in rtti}
vt_class = {}                       # vtable start -> class display name
for r in rtti:
    for v in filter(None, r["vtables"].split(";") if ";" in r["vtables"] else [r["vtables"]]):
        try:
            vt_class[int(v, 16)] = r["name"]
        except ValueError:
            pass
for v in SC["vtables"]:
    nm = v["name"]
    vt_class.setdefault(v["addr"], next((r["name"] for r in rtti if r["mangled"] == nm), nm))
VT_STARTS = sorted(vt_class)
VT_FUNCS = {v["addr"]: v["funcs"] for v in SC["vtables"]}

PEROBJ_RO_END = SC["comdat_rtti_region"][0]                 # 0x483E78: first COMDAT typeinfo
comdat_ti = sorted(t for t in ti_addr if t >= PEROBJ_RO_END)
ti_names = sorted(word(t + 4) for t in comdat_ti if word(t + 4) and seg_of(word(t + 4)) == "rodata")
TS_LO = ti_names[0]
last_name = ti_names[-1]
TS_END = (last_name + len(cstr_at(last_name, 400) or "") + 1 + 3) & ~3
comdat_vt = sorted(v for v in VT_STARTS if v >= PEROBJ_RO_END)
VT_LO = comdat_vt[0]
last_vt = comdat_vt[-1]
VT_END = last_vt + 8 + 4 * len(VT_FUNCS.get(last_vt, [])) if last_vt in VT_FUNCS else last_vt + 12
TI_END = TS_LO                       # typenames follow the last typeinfo directly
assert max(comdat_ti) < TS_LO


def vt_extent(s):
    """end of the vtable starting at s (ott, typeinfo, slots); slots are text pointers or 0"""
    if s in VT_FUNCS and VT_FUNCS[s]:
        return s + 8 + 4 * len(VT_FUNCS[s])
    k = bisect.bisect_right(VT_STARTS, s)
    nxt = VT_STARTS[k] if k < len(VT_STARTS) else s + 0x200
    a = s + 8
    while a < min(nxt, s + 0x200):
        x = word(a)
        if x is None or not (x == 0 or seg_of(x) == "text"): break
        a += 4
    return a


VT_END_OF = {s: vt_extent(s) for s in VT_STARTS}


def class_of_vptr(v):
    """class name if v is an address point inside a vtable (start+8 .. end)"""
    k = bisect.bisect_right(VT_STARTS, v) - 1
    if k < 0: return None
    s = VT_STARTS[k]
    if s + 8 <= v < max(VT_END_OF[s], s + 12):
        return vt_class[s]
    return None


# RTTI-less vtables in the COMDAT vtable region: "0, 0, text-ptr, text-ptr..." headers
def rttiless_vtables(lo, hi):
    out = []
    a = lo
    while a < hi - 12:
        if word(a) == 0 and word(a + 4) == 0 and seg_of(word(a + 8) or 0) == "text" \
                and seg_of(word(a + 12) or 0) == "text":
            out.append(a)
            a += 12
            while a < hi and seg_of(word(a) or 0) == "text":
                a += 4
            continue
        a += 4
    return out


RTTILESS_VT = rttiless_vtables(VT_LO, VT_END)

# ---------------------------------------------------------------------------
# 4. function labels
# ---------------------------------------------------------------------------
def top_family(name):
    """object-family key for a class display name"""
    m = re.match(r"_GLOBAL__N__\d+_(\w+?)_(cpp|c|cc)_([0-9a-f]{8})", name)
    if m:
        return "file:%s.%s" % (m.group(1), m.group(2))
    return "class:" + name.split("::")[0]


func_class = {}             # f -> (class display name, conf, how)
vf_owner = collections.defaultdict(set)
for v in SC["vtables"]:
    for fn in v["funcs"]:
        vf_owner[fn].add(vt_class.get(v["addr"], v["name"]))
for fn, s in vf_owner.items():
    if len(s) == 1:
        func_class[fn] = (next(iter(s)), "high", "vfunc")
def ctor_vptr_stores():
    """f -> set of classes whose vptr the function stores to [this,#0], 'this' being the
    incoming r0 (followed through MOV copies until overwritten or clobbered by a call).
    A real ctor/dtor (or an inlined base ctor/dtor inside one) has this pattern; a caller
    that constructs an object inline stores the vptr into a fresh pointer instead."""
    out = collections.defaultdict(list)
    last_f = None
    this, vreg = set(), {}
    for lo, hi in CODE_RANGES:
        for pc in range(lo, hi, 4):
            f = func_of(pc)
            if f != last_f:
                this, vreg, last_f = {0}, {}, f
            w = struct.unpack_from("<I", code, TEXT_OFF + pc - TEXT_VA)[0]
            if w >> 28 == 0xF: continue
            op, rd, rn = (w >> 25) & 7, (w >> 12) & 15, (w >> 16) & 15
            if (w & 0x0F5F0000) == 0x051F0000:              # LDR Rd,[PC,#imm]
                imm = w & 0xFFF
                v = word(pc + 8 + (imm if (w >> 23) & 1 else -imm))
                c = class_of_vptr(v) if v is not None else None
                this.discard(rd)
                if c: vreg[rd] = c
                else: vreg.pop(rd, None)
                continue
            if op == 2 and not (w >> 20) & 1:               # STR imm
                P_, U, W = (w >> 24) & 1, (w >> 23) & 1, (w >> 21) & 1
                if P_ and (w & 0xFFF) == 0 and rn in this and rd in vreg and not (w >> 22) & 1:
                    out[f].append(vreg[rd])
                if W or not P_: this.discard(rn); vreg.pop(rn, None)
                continue
            if op == 0 and (w & 0x0FE00FF0) == 0x01A00000:  # MOV Rd,Rm
                rm = w & 15
                if rm in this: this.add(rd)
                else: this.discard(rd)
                if rm in vreg: vreg[rd] = vreg[rm]
                else: vreg.pop(rd, None)
                continue
            if op == 5:                                      # B/BL
                if (w >> 24) & 1:
                    for r in CALLER_SAVED: this.discard(r); vreg.pop(r, None)
                continue
            if op == 4:                                      # LDM/STM
                if (w >> 21) & 1: this.discard(rn); vreg.pop(rn, None)
                if (w >> 20) & 1:
                    for r in range(16):
                        if (w >> r) & 1: this.discard(r); vreg.pop(r, None)
                continue
            if (w & 0x0FFFFFF0) == 0x012FFF30:               # BLX reg
                for r in CALLER_SAVED: this.discard(r); vreg.pop(r, None)
                continue
            if op in (6, 7):
                if op == 7 and (w >> 20) & 1 and (w >> 4) & 1: this.discard(rd); vreg.pop(rd, None)
                continue
            if op in (2, 3) and not (op == 3 and (w >> 4) & 1):        # LDR / STR (reg) forms
                if (w >> 21) & 1 or not (w >> 24) & 1: this.discard(rn); vreg.pop(rn, None)
                if (w >> 20) & 1: this.discard(rd); vreg.pop(rd, None)
                continue
            if op == 0 and (w & 0x90) == 0x90 and (w & 0x60) != 0:     # LDRH/STRH/LDRD...
                if (w >> 21) & 1 or not (w >> 24) & 1: this.discard(rn); vreg.pop(rn, None)
                if (w >> 20) & 1 or (w >> 5) & 3 == 2:
                    for r in (rd, rd + 1): this.discard(r); vreg.pop(r, None)
                continue
            if op in (0, 1) and 8 <= (w >> 21) & 15 <= 11 and (w >> 20) & 1:     # TST/TEQ/CMP/CMN
                continue
            # anything else: conservatively forget Rd (and Rn for multiplies / media ops)
            this.discard(rd); vreg.pop(rd, None)
            if op == 3 or (op == 0 and (w & 0xF0) == 0x90): this.discard(rn); vreg.pop(rn, None)
    return out


CTOR_STORES = ctor_vptr_stores()
vf_near = sorted((f, top_family(c)) for f, (c, conf, how) in func_class.items() if how == "vfunc")
vf_near_a = [a for a, _ in vf_near]


def nearest_vfunc_family(f, maxd=0x1000):
    k = bisect.bisect_left(vf_near_a, f)
    cand = []
    if k < len(vf_near): cand.append((vf_near[k][0] - f, vf_near[k][1]))
    if k > 0: cand.append((f - vf_near[k - 1][0], vf_near[k - 1][1]))
    cand = [c for c in cand if c[0] <= maxd]
    return min(cand)[1] if cand else None


# ctor/dtor: a function storing exactly one class's vptr to [this,#0] ("ctor-store"), or
# a function loading exactly one class's vptr that sits next to that class's own virtual
# functions ("vptr-near-vfunc").  A function that merely loads a vptr elsewhere is a caller
# constructing the object inline and gets no class label from it.
# Exception: an anonymous-namespace vtable is local to its TU, so any function loading only
# anon vtables of one file lies in that file ("vptr-anon").
n_vptr_rejected = 0
for f, lst in TOUCHES.items():
    if f in func_class: continue
    allc = {class_of_vptr(b) for b, a, sz, k in lst if k == "lit"} - {None}
    if allc and len({top_family(c) for c in allc}) == 1 and top_family(next(iter(allc))).startswith("file:"):
        func_class[f] = (sorted(allc)[0], "medium", "vptr-anon")
        continue
    st = set(CTOR_STORES.get(f, []))
    if len(st) == 1:
        func_class[f] = (next(iter(st)), "medium", "ctor-store")
        continue
    if len({top_family(c) for c in st}) == 1:
        # inlined base ctor/dtor of the same top-level family
        func_class[f] = (sorted(st)[0], "medium", "ctor-store")
        continue
    cls = {class_of_vptr(b) for b, a, sz, k in lst if k == "lit"} - {None}
    if len(cls) == 1:
        c = next(iter(cls))
        if not st and nearest_vfunc_family(f) == top_family(c):
            func_class[f] = (c, "medium", "vptr-near-vfunc")
        else:
            n_vptr_rejected += 1
# lexical name coordinate (on-LIS anchors on both sides with the same class)
mang2disp = {}
for r in rtti:
    m = r["mangled"]
    mang2disp["_ZN" + (m[1:-1] if m.startswith("N") and m.endswith("E") else m)] = r["name"]
lis = sorted((x["addr"], x["cls"]) for x in SC["lex_anchors"] if x["on_lis"])
lis_a = [a for a, _ in lis]
for f in FUNCS:
    if f in func_class: continue
    k = bisect.bisect_right(lis_a, f) - 1
    if k < 0 or k + 1 >= len(lis): continue
    (la, ln), (ra, rn_) = lis[k], lis[k + 1]
    if ln == rn_ and ra - la <= 0x4000 and ln in mang2disp:
        func_class[f] = (mang2disp[ln], "medium", "lex")

# library labels: config/naming/library.csv (one row per function: game, unknown or a
# library tag such as nex / ctr_sdk / molive, with a confidence).  This replaced the older
# string-keyword vote and the 64 KiB "region guess" buckets, which disagreed with the
# per-function tags (e.g. game functions inside an "sdk/lib" bucket).
LIBTAG = {}
for _r in csv.DictReader(open(P("config", "naming", "library.csv"))):
    LIBTAG[int(_r["func_addr"], 16)] = (_r["library"], _r["confidence"])
NONLIB = ("game", "unknown")


def libtag(f):
    return LIBTAG.get(f, ("unknown", "low"))


# ---------------------------------------------------------------------------
# 5. init_array: per-TU static-init functions
# ---------------------------------------------------------------------------
INIT = []
for k, ea in enumerate(range(INIT_LO, INIT_HI, 4)):
    INIT.append((ea + s32(word(ea))) & 0xFFFFFFFF)
N_INIT = len(INIT)
init_index = {f: k for k, f in enumerate(INIT)}
sti_lo, sti_hi = min(INIT), func_end(max(INIT))
sti_funcs_in_range = bisect.bisect_left(FUNCS, sti_hi) - bisect.bisect_left(FUNCS, sti_lo)

# init function -> bases per segment (rodata limited to the per-object region)
def init_bases(k):
    out = collections.defaultdict(set)
    for b, a, sz, kind in TOUCHES.get(INIT[k], []):
        s = seg_of(b)
        if s == "rodata" and b >= PEROBJ_RO_END: continue
        if s in ("rodata", "data", "bss"): out[s].add(b)
    return out


IB = [init_bases(k) for k in range(N_INIT)]


def lis_pairs(pairs):
    """pairs sorted by (k, addr); longest chain strictly increasing in addr with k
    non-decreasing (several bases of one TU allowed).  Returns the kept set."""
    seq = [a for _, a in pairs]
    tails, tails_i, prev = [], [], [-1] * len(seq)
    for i, x in enumerate(seq):
        j = bisect.bisect_left(tails, x)
        if j == len(tails): tails.append(x); tails_i.append(i)
        else: tails[j] = x; tails_i[j] = i
        prev[i] = tails_i[j - 1] if j else -1
    keep = set()
    i = tails_i[-1] if tails_i else -1
    while i >= 0:
        keep.add(pairs[i]); i = prev[i]
    return keep


own = {s: collections.defaultdict(set) for s in ("rodata", "data", "bss")}
q1 = {}
rng = random.Random(20261108)
for s in ("rodata", "data", "bss"):
    pairs = sorted((k, b) for k in range(N_INIT) for b in IB[k][s])
    keep = lis_pairs(pairs)
    for k, b in keep: own[s][k].add(b)
    # shuffled baseline: permute TU indices
    perm = list(range(N_INIT)); rng.shuffle(perm)
    sh = sorted((perm[k], b) for k, b in pairs)
    q1[s] = dict(pairs=len(pairs), tus=len({k for k, _ in pairs}), kept=len(keep),
                 tus_kept=len({k for k, _ in keep}), shuffled=len(lis_pairs(sh)))
# adjacent-TU monotonicity on min own base
def adj_mono(s):
    mins = [(k, min(own[s][k])) for k in range(N_INIT) if own[s][k]]
    ok = sum(1 for (k1, a1), (k2, a2) in zip(mins, mins[1:]) if a1 < a2)
    return ok, max(0, len(mins) - 1)


q1_adj = {s: adj_mono(s) for s in own}     # after the chain filter (true by construction)


def raw_order(s):
    """before any filtering: each TU's minimum referenced base vs table index.
    Returns (adjacent rises, adjacent pairs, pairwise concordance, TUs)."""
    mins = [min(IB[k][s]) for k in range(N_INIT) if IB[k][s]]
    up = sum(1 for a, b in zip(mins, mins[1:]) if a < b)
    conc = tot = 0
    for i in range(len(mins)):
        for j in range(i + 1, len(mins)):
            if mins[i] != mins[j]:
                tot += 1
                conc += mins[i] < mins[j]
    return up, max(0, len(mins) - 1), conc / max(1, tot), len(mins)


q1_raw = {s: raw_order(s) for s in own}
# init function address order vs table order
init_addr_rank_up = sum(1 for a, b in zip(INIT, INIT[1:]) if a < b)

# ---------------------------------------------------------------------------
# 6. label atoms
# ---------------------------------------------------------------------------
SEGS = {"rodata": (RO_VA, PEROBJ_RO_END), "data": (DATA_VA, DATA_END), "bss": (BSS_VA, BSS_END)}
ro_files = {f: tuple(v) for f, v in SC["ro_file_ranges"].items()}


def fam_of_func(f):
    """(family, conf) of a referencing function"""
    if f in init_index: return ("tu:%d" % init_index[f], "high")
    if f in func_class:
        c, conf, how = func_class[f]
        return (top_family(c), conf)
    lt, lc = libtag(f)
    if lt not in NONLIB: return ("lib:" + lt, "medium" if lc in ("high", "medium") else "low")
    return (None, None)


def origin_of_func(f):
    """census key of a referencing function: its family, else 'game' / 'unknown' from
    library.csv (an unlabelled game function is not a family, but it is not library code)"""
    fam, _ = fam_of_func(f)
    if fam is not None:
        return "init" if fam.startswith("tu:") else fam
    return libtag(f)[0]


def census_text(refs):
    """'refs-only-from-X(n)' or 'mixed(A=n,B=m,...)' over the referencing functions"""
    c = collections.Counter(origin_of_func(f) for f in refs)
    if not c: return "no-refs"
    if len(c) == 1:
        k, n = next(iter(c.items()))
        return "refs-only-from-%s(%d)" % (k, n)
    items = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
    more = ",+%d-more" % (len(items) - 6) if len(items) > 6 else ""
    return "mixed(%s%s)" % (",".join("%s=%d" % kv for kv in items[:6]), more)


ATOMS = {}
for s, (lo, hi) in SEGS.items():
    atoms = build_atoms(lo, hi)
    recs = []
    for b, e, bases in atoms:
        refs = set()
        for x in bases: refs |= base_funcs[x]
        tus = {k for k in range(N_INIT) if any(x in own[s][k] for x in bases)}
        fams = collections.Counter()
        unl = 0
        for f in refs:
            fam, _ = fam_of_func(f)
            if fam is None: unl += 1
            elif not fam.startswith("tu:"): fams[fam] += 1
        recs.append(dict(lo=b, hi=e, bases=bases, refs=refs, tus=tus, fams=fams, unl=unl))
    ATOMS[s] = recs

# anon-file rodata anchors (typeinfo / vtables of anonymous-namespace classes)
anon_ro = []
for t, r in ti_addr.items():
    if t < PEROBJ_RO_END:
        fm = top_family(r["name"])
        if fm.startswith("file:"): anon_ro.append((t, fm))
for v in VT_STARTS:
    if v < PEROBJ_RO_END:
        fm = top_family(vt_class[v])
        if fm.startswith("file:"): anon_ro.append((v, fm))
anon_ro.sort()

# TU <-> family association (weighted by atom exclusivity)
tu_fam = collections.defaultdict(collections.Counter)
for s, recs in ATOMS.items():
    for r in recs:
        if len(r["tus"]) != 1: continue
        k = next(iter(r["tus"]))
        tot = sum(r["fams"].values())
        if not tot: continue
        for fam, n in r["fams"].items():
            tu_fam[k][fam] += n / tot / max(1, len(r["fams"]))
# file anchors: TU whose own rodata bases sit inside an anon file's rodata range
# TU k's rodata span = [min own base of k, min own base of the next TU with one).
# An anon-namespace typeinfo/vtable inside the span (and inside k's touched extent)
# names the TU; a file whose RTTI lies past k's extent may be a TU without init.
tu_file = {}
tu_file_conf = {}
ro_tus = [(min(own["rodata"][k]), k) for k in range(N_INIT) if own["rodata"][k]]
ro_tu_starts = [a for a, _ in ro_tus]
tu_ro_extent = {}
for k in range(N_INIT):
    ext = 0
    for b in own["rodata"][k]:
        ext = max(ext, base_end.get(b, b + 4))
    if ext: tu_ro_extent[k] = ext
file_lo = {}
for t, fm in anon_ro:
    file_lo[fm[5:]] = min(file_lo.get(fm[5:], t), t)
files_ordered = sorted(file_lo, key=lambda f: file_lo[f])
ro_next = {}
for (a, k), nx in zip(ro_tus, ro_tus[1:] + [(PEROBJ_RO_END, None)]):
    ro_next[k] = nx[0]
ro_start = {k: a for a, k in ro_tus}


def file_score(fn, k):
    """evidence that anon file fn is init TU k: 4 = RTTI inside k's touched rodata
    extent, +2 = k's exclusively-referenced atoms belong to fn's classes,
    +1 = RTTI inside k's rodata span (up to the next anchored TU)."""
    sc, why = 0, []
    t = file_lo[fn]
    if k in ro_start:
        foreign = [r for r in ATOMS["rodata"] if ro_start[k] <= r["lo"] < t and not r["tus"]
                   and len(r["fams"]) == 1 and r["unl"] == 0 and ("file:" + fn) not in r["fams"]]
        if ro_start[k] - 0x40 <= t < tu_ro_extent.get(k, 0) + 0x100 and not foreign:
            sc += 4; why.append("rtti-in-extent")
        elif ro_start[k] <= t < ro_next[k]:
            sc += 1; why.append("rtti-in-span" + ("-after-foreign" if foreign else ""))
    fams = tu_fam.get(k)
    if fams:
        fam, v = fams.most_common(1)[0]
        if fam == "file:" + fn and v >= 0.5 * sum(fams.values()):
            sc += 2; why.append("exclusive-refs")
    return sc, "+".join(why)


# weighted order-preserving matching files <-> TUs (DP, like sequence alignment)
NF = len(files_ordered)
best = [[0] * (N_INIT + 1) for _ in range(NF + 1)]
for i in range(1, NF + 1):
    for k in range(1, N_INIT + 1):
        sc = file_score(files_ordered[i - 1], k - 1)[0]
        best[i][k] = max(best[i - 1][k], best[i][k - 1], best[i - 1][k - 1] + sc if sc else 0)
i, k = NF, N_INIT
while i > 0 and k > 0:
    sc, why = file_score(files_ordered[i - 1], k - 1)
    if sc and best[i][k] == best[i - 1][k - 1] + sc:
        tu_file[k - 1] = files_ordered[i - 1]
        tu_file_conf[k - 1] = ("high" if sc >= 4 else "medium" if sc >= 2 else "low", why)
        i -= 1; k -= 1
    elif best[i][k] == best[i - 1][k]:
        i -= 1
    else:
        k -= 1

# A match resting only on "RTTI inside TU k's rodata span" does not single out k when init TUs
# without any rodata lie between k and the next rodata-anchored TU: the file's .constdata
# sits in the same place for each of them (and for a TU without static init).  Such
# matches are withdrawn and the candidates recorded (file stays a non-init family label).
ro_tu_index = {a: kk for a, kk in ro_tus}
TU_AMBIG = {}                         # file -> (first candidate TU, [candidate TUs])
for kk, fn in sorted(tu_file.items()):
    conf, why = tu_file_conf[kk]
    if not why.startswith("rtti-in-span"): continue
    k_hi = ro_tu_index.get(ro_next[kk], N_INIT)
    cands = [j for j in range(kk, k_hi) if j == kk or j not in tu_file]
    if len(cands) > 1:
        TU_AMBIG[fn] = (kk, cands)
for fn, (kk, cands) in TU_AMBIG.items():
    del tu_file[kk], tu_file_conf[kk]

# init function constructs objects of these classes (vptr loads)
tu_vptr = {k: sorted({class_of_vptr(b) for b, a, sz, kd in TOUCHES.get(INIT[k], []) if kd == "lit"} - {None})
           for k in range(N_INIT)}
tu_libstr = {k: (libtag(INIT[k])[0] if libtag(INIT[k])[0] not in NONLIB else None) for k in range(N_INIT)}

# raw referrer census per init TU: distinct non-init functions referencing the TU's own
# atoms, by family (unlabelled functions counted separately)
tu_raw = {}
for k in range(N_INIT):
    fs = set()
    for s, recs in ATOMS.items():
        for r in recs:
            if r["tus"] == {k}: fs |= r["refs"]
    c, unl = collections.Counter(), 0
    for f in fs:
        fam, _ = fam_of_func(f)
        if fam is None: unl += 1
        elif not fam.startswith("tu:"): c[fam] += 1
    tu_raw[k] = (c, unl)

# TU names.  A class/library name needs the weighted (exclusivity) and the raw referrer
# plurality to agree and >= 60% of labelled referrers; medium only when >= 75% of >= 2
# labelled referrers agree, labelled referrers are not outnumbered by unlabelled ones and at
# most two families use the data.  Who constructs a static object (vptr loads in the init
# function) is *not* used: a TU can instantiate any class.
TU_NAME = {}
for k in range(N_INIT):
    if k in tu_file:
        TU_NAME[k] = ("file:" + tu_file[k], tu_file_conf[k][0], tu_file_conf[k][1])
        continue
    raw, unl = tu_raw[k]
    wf = tu_fam.get(k)
    if raw:
        fam, n = sorted(raw.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        tot = sum(raw.values())
        tie = sum(1 for v in raw.values() if v == n) > 1
        wtop = wf.most_common(1)[0][0] if wf else None
        if fam.startswith("file:") and fam[5:] in tu_file.values():
            # that file is already matched to another init TU: these are externs it uses
            TU_NAME[k] = ("unknown", "low", "refs-by-" + fam)
            continue
        if not tie and fam == wtop and n >= 0.6 * tot and 4 * n < tot + unl:
            # labelled referrers are a small minority: too little evidence for a name
            TU_NAME[k] = ("unknown", "low", "weak-refs(%s=%d/%d,unl=%d)" % (fam, n, tot, unl))
            continue
        if not tie and fam == wtop and n >= 0.6 * tot:
            good = (n >= 0.75 * tot and n >= 2 and tot >= unl and len(raw) <= 2
                    and not fam.startswith("lib:"))
            TU_NAME[k] = (fam, "medium" if good else "low", "refs(%d/%d,unl=%d)" % (n, tot, unl))
            continue
        if not tu_libstr[k]:
            TU_NAME[k] = ("unknown", "low", "mixed-refs(%s=%d/%d,unl=%d)" % (fam, n, tot, unl))
            continue
    if tu_libstr[k]:
        TU_NAME[k] = ("lib:" + tu_libstr[k], "low", "init-func-library-tag")
        continue
    TU_NAME[k] = ("unknown", "low", "no-label(unl=%d)" % tu_raw[k][1] if tu_raw[k][1] else "no-label")
# a file match whose neighbouring init TU (+-2) is also referenced mainly by that file's
# functions is ambiguous between the two: high -> medium
for k, (nm, conf, how) in list(TU_NAME.items()):
    if nm.startswith("file:") and conf == "high" and "exclusive-refs" not in how:
        if any(TU_NAME.get(j, ("",))[2:] == ("refs-by-" + nm,) for j in (k - 2, k - 1, k + 1, k + 2)):
            TU_NAME[k] = (nm, "medium", how + ";neighbour-also-refs-file")
# a non-file family naming several init TUs: a class is defined in one .cpp, so at most one
# of them can be right (namespaces may span files) -> all capped at low
fam_tus = collections.Counter(v[0] for v in TU_NAME.values() if v[0].startswith("class:"))
for k, (nm, conf, how) in list(TU_NAME.items()):
    if fam_tus.get(nm, 0) > 1:
        TU_NAME[k] = (nm, "low", how + ";fam-in-%d-TUs" % fam_tus[nm])
# Library-named TUs cluster in long index runs (library objects are linked together, mostly
# after the game objects).  A library name with no TU of the same library within +-3 init
# indices is an isolated per-function tag inside game objects: withdrawn.
_lib_named = {k: v[0] for k, v in TU_NAME.items() if v[0].startswith("lib:")}
for k, nm in sorted(_lib_named.items()):
    if not any(_lib_named.get(j) == nm for j in range(k - 3, k + 4) if j != k):
        TU_NAME[k] = ("unknown", "low", TU_NAME[k][2] + ";isolated-" + nm)
for fn, (kk, cands) in sorted(TU_AMBIG.items()):
    for j in cands:
        nm, conf, how = TU_NAME[j]
        TU_NAME[j] = (nm, conf, how + ";maybe-file:%s(%s)" % (fn, "|".join("#%03d" % c for c in cands)))
# init TUs per family name (file:/class:), any confidence: used for the object-order check
NAME_TUS = collections.defaultdict(list)
for k, (nm, conf, how) in TU_NAME.items():
    if nm.startswith(("file:", "class:")): NAME_TUS[nm].append(k)

# sti lexical-order test (EDG/armcc init function name __sti___<len>_<File_cpp>_<hash>)
def sti_key(fname):
    stem = fname.replace(".", "_")
    return "%d_%s" % (len(stem), stem)


named_files = sorted((INIT[k], k, TU_NAME[k][0][5:]) for k in range(N_INIT)
                     if TU_NAME[k][0].startswith("file:") and TU_NAME[k][1] != "low")
sti_seq_len = [sti_key(n) for _, _, n in named_files]
sti_seq_plain = [n.lower() for _, _, n in named_files]
sti_sorted_len = sum(1 for a, b in zip(sti_seq_len, sti_seq_len[1:]) if a <= b)
sti_sorted_plain = sum(1 for a, b in zip(sti_seq_plain, sti_seq_plain[1:]) if a <= b)

# ---------------------------------------------------------------------------
# 7. build rows per segment
# ---------------------------------------------------------------------------
def atom_label(s, r):
    """(object, conf, evidence) for one atom"""
    if len(r["tus"]) == 1:
        k = next(iter(r["tus"]))
        nm, conf, how = TU_NAME[k]
        return ("tu:%d" % k, nm, conf, "init#%03d;%s" % (k, how))
    if len(r["tus"]) > 1:
        return (None, "unknown", "low", "atom-spans-%d-init-TUs" % len(r["tus"]))
    if s == "rodata":
        for t, fm in anon_ro:
            if r["lo"] <= t < r["hi"]:
                return (fm, fm, "high", "anon-rtti")
    tot = sum(r["fams"].values())
    if tot and len(r["fams"]) == 1 and r["unl"] == 0:
        fam = next(iter(r["fams"]))
        if fam.startswith("lib:"):
            # library.csv tags: medium when >= 2 referrers all carry a high/medium tag
            conf = "medium" if tot >= 2 and all(fam_of_func(f)[1] == "medium" for f in r["refs"]) else "low"
        else:
            conf = "medium" if tot >= 2 else "low"
        return (fam, fam, conf, "only-ref-by-%s(%d)" % ("lib" if fam.startswith("lib:") else "class", tot))
    if tot and r["fams"].most_common(1)[0][1] >= 0.75 * (tot + r["unl"]) and tot >= 3:
        fam = r["fams"].most_common(1)[0][0]
        return (fam, fam, "low", "mostly-ref-by(%d/%d)" % (r["fams"][fam], tot + r["unl"]))
    # no family: the row evidence later lists the referrer census (game / mixed / ...)
    return (None, "unknown", "low", census_text(r["refs"]))


def tu_order_ok(s, recs):
    """TU-labelled atoms must rise in TU order; demote violators (LIS on TU index)"""
    idx = [(i, next(iter(r["tus"]))) for i, r in enumerate(recs) if len(r["tus"]) == 1]
    seq = [k for _, k in idx]
    tails, tails_i, prev = [], [], [-1] * len(seq)
    for i, x in enumerate(seq):
        j = bisect.bisect_right(tails, x)
        if j == len(tails): tails.append(x); tails_i.append(i)
        else: tails[j] = x; tails_i[j] = i
        prev[i] = tails_i[j - 1] if j else -1
    keep = set()
    i = tails_i[-1] if tails_i else -1
    while i >= 0:
        keep.add(idx[i][0]); i = prev[i]
    bad = [idx[i][0] for i in range(len(idx)) if idx[i][0] not in keep]
    return bad


def fam_funcs(refs, fam):
    """referencing functions usable for co-reference: unlabelled, init, or same family"""
    out = set()
    for f in refs:
        ff, _ = fam_of_func(f)
        if ff is None or ff.startswith("tu:") or ff == fam:
            out.add(f)
    return out


def family_runs(sub):
    """group atoms into runs of one family.  An unknown atom joins the preceding run if a
    function of that run also references it (co-reference) or if the same family resumes
    after it; otherwise unknown atoms form their own run."""
    runs, pending = [], []

    def flush():
        if not pending: return
        if runs and runs[-1]["key"] is None:
            runs[-1]["hi"] = max(runs[-1]["hi"], max(r["hi"] for r in pending))
            runs[-1]["n"] += len(pending)
        else:
            runs.append(dict(key=None, obj="unknown", conf="low", ev="unattributed",
                             lo=pending[0]["lo"], hi=max(r["hi"] for r in pending),
                             n=len(pending), nk=0, funcs=set()))
        pending.clear()

    for r in sub:
        key, obj, conf, ev = r["lab"]
        if key is None:
            if not pending and runs and runs[-1]["key"] is not None and r["refs"] & runs[-1]["funcs"]:
                g = runs[-1]
                g["hi"] = max(g["hi"], r["hi"]); g["n"] += 1; g["coref"] = g.get("coref", 0) + 1
                g["funcs"] |= fam_funcs(r["refs"], g["key"])
            else:
                pending.append(r)
            continue
        if runs and runs[-1]["key"] == key:
            g = runs[-1]
            for x in pending + [r]:
                g["hi"] = max(g["hi"], x["hi"]); g["n"] += 1
            g["nk"] += 1
            g["funcs"] |= fam_funcs(r["refs"], key)
            pending.clear()
            continue
        flush()
        runs.append(dict(key=key, obj=obj, conf=conf, ev=ev, lo=r["lo"], hi=r["hi"], n=1, nk=1,
                         funcs=fam_funcs(r["refs"], key)))
    flush()
    return runs


FAR_TEXT = 0x10000
GAP_SPLIT = 0x1000         # unreferenced stretch inside a non-TU run that becomes its own unit


def far_from_tu(refs, fk):
    """True if every (non-init) referrer is > FAR_TEXT away in .text from every non-init
    function already tied to the TU.  Class methods sit together (name-sorted .text), so a
    referrer far from all of them is usually another class's code.  Undecided (False) when
    the TU has no non-init referrer yet."""
    home = sorted(f for f in fk if f not in init_index)
    rr = [f for f in refs if f not in init_index]
    if not home or not rr: return False
    for f in rr:
        k = bisect.bisect_left(home, f)
        if (k < len(home) and home[k] - f <= FAR_TEXT) or (k > 0 and f - home[k - 1] <= FAR_TEXT):
            return False
    return True


CONF_RANK = {"low": 0, "medium": 1, "high": 2}


def cap(conf, mx):
    return conf if CONF_RANK[conf] <= CONF_RANK[mx] else mx


rows = []          # dict rows (split units), filled per segment below
seg_stats = {}
tu_rows = {}
ORDER_FIX = []     # family-labelled atoms that contradicted object order (now extern-used-by-...)
for s, (lo, hi) in SEGS.items():
    recs = ATOMS[s]
    bad = set(tu_order_ok(s, recs))
    for i in bad:
        recs[i]["tus"] = set()
    for r in recs:
        r["lab"] = atom_label(s, r) if not r["tus"] else (None, "unknown", "low", "")
    tu_atoms = collections.defaultdict(list)
    for i, r in enumerate(recs):
        if len(r["tus"]) == 1: tu_atoms[next(iter(r["tus"]))].append(i)
    anchors = sorted((recs[ix[0]]["lo"], k) for k, ix in tu_atoms.items())
    starts = [a for a, _ in anchors]
    anc_k = [k for _, k in anchors]
    # Object-order check.  A file:/class: family that names init TU(s) can own data only
    # between the anchors that bracket those TUs.  An atom referenced only by that family's
    # code but lying past a later TU's start (or before an earlier one's) is not the family's
    # own data: it is an extern defined in another object and used by the family's code.
    for r in recs:
        if r["tus"]: continue
        key = r["lab"][0]
        ks = NAME_TUS.get(key) if key else None
        if not ks: continue
        j = bisect.bisect_right(starts, r["lo"])
        kb = anc_k[j - 1] if j else -1
        ka = anc_k[j] if j < len(anc_k) else N_INIT
        if any(kb <= k <= ka for k in ks): continue
        where = ("after-init#%03d-start" % kb) if kb > max(ks) else ("before-init#%03d-start" % ka)
        note = "extern-used-by-%s(%s;%s)" % (key, "|".join("#%03d" % k for k in ks), where)
        ORDER_FIX.append(dict(seg=s, lo=r["lo"], hi=r["hi"], fam=key, ks=ks, kb=kb, ka=ka,
                              old=r["lab"][3], refs=sorted(r["refs"]), where=where))
        assert r["lab"][3] != "anon-rtti", ("anon RTTI out of object order", s, H(r["lo"]), key)
        r["lab"] = (None, "unknown", "low", note)
        r["note"] = note
    out = []          # run dicts
    head_end = starts[0] if starts else hi
    for g in family_runs([r for r in recs if r["lo"] < head_end]):
        out.append(g)
    for i, (a, k) in enumerate(anchors):
        nxt = starts[i + 1] if i + 1 < len(starts) else hi
        ext = max(recs[ix]["hi"] for ix in tu_atoms[k])
        name, nconf, how = TU_NAME[k]
        # a library name is a whole library (many objects): it does not tie atoms to this TU
        fam_k = name if name != "unknown" and not name.startswith("lib:") else None
        g = dict(key="tu:%d" % k, obj=name, conf=nconf if name != "unknown" else "medium",
                 ev="init#%03d;%s" % (k, how), lo=a, hi=ext, n=len(tu_atoms[k]), nk=len(tu_atoms[k]), tu=k,
                 own_hi=ext)
        sub = [r for r in recs if ext <= r["lo"] < nxt]
        fk = set()
        for ix in tu_atoms[k]:
            fk |= fam_funcs(recs[ix]["refs"], fam_k)
        j = 0
        while j < len(sub):
            key_j = sub[j]["lab"][0]
            if sub[j].get("note"):
                break                     # an extern of another object: not this TU's data
            if sub[j]["lo"] - g["hi"] > GAP_SPLIT:
                break                     # long unreferenced stretch: TU end unknown
            if key_j is not None and key_j == fam_k:
                g["own_hi"] = max(g["own_hi"], sub[j]["hi"])
            elif key_j is None and sub[j]["refs"] & fk:
                g["coref"] = g.get("coref", 0) + 1
                g["own_hi"] = max(g["own_hi"], sub[j]["hi"])
            elif key_j is None and far_from_tu(sub[j]["refs"], fk):
                # every referrer sits far (.text) from all of the TU's non-init referrers:
                # most likely another object's data -> end the TU row here
                break
            elif key_j is None:
                # referenced only by unlabelled functions with no link to this TU: kept in the
                # TU row (the TU start is the reliable boundary) but counted
                g["unattr"] = g.get("unattr", 0) + 1
                g["unattr_bytes"] = g.get("unattr_bytes", 0) + (sub[j]["hi"] - sub[j]["lo"])
            else:
                break
            g["hi"] = max(g["hi"], sub[j]["hi"]); g["n"] += 1
            fk |= fam_funcs(sub[j]["refs"], fam_k)
            j += 1
        out.append(g)
        out.extend(family_runs(sub[j:]))
    # a family run directly before a TU row of the same family is the TU's leading data
    merged = []
    for g in out:
        if merged and "tu" in g and "tu" not in merged[-1] and merged[-1]["key"] is not None \
                and merged[-1]["key"] == g["obj"] and not g["obj"].startswith("lib:"):
            prev = merged.pop()
            g["lo"] = prev["lo"]; g["n"] += prev["n"]; g["lead"] = prev["n"]
        merged.append(g)
    out = merged
    atom_lo = [r["lo"] for r in recs]

    def atoms_in(a, b):
        return recs[bisect.bisect_left(atom_lo, a):bisect.bisect_left(atom_lo, b)]

    # split non-TU runs at internal unreferenced stretches longer than GAP_SPLIT: the
    # stretch becomes its own "unreferenced-gap" unit (it may be any object's data)
    split_out = []
    for i, g in enumerate(out):
        end = out[i + 1]["lo"] if i + 1 < len(out) else hi
        if "tu" in g:
            split_out.append(g)
            if end - g["hi"] > GAP_SPLIT:
                split_out.append(dict(gap=True, key=None, lo=(g["hi"] + 3) & ~3))
            continue
        cur = None
        for r in atoms_in(g["lo"], end):
            if cur is not None and r["lo"] - cur["hi"] > GAP_SPLIT:
                split_out.append(cur)
                split_out.append(dict(gap=True, key=None, lo=(cur["hi"] + 3) & ~3))
                cur = None
            if cur is None:
                cur = dict(g, lo=r["lo"], hi=r["hi"], n=0, nk=0)
            cur["hi"] = max(cur["hi"], r["hi"]); cur["n"] += 1
            if g["key"] is not None and r["lab"][0] == g["key"]: cur["nk"] += 1
        if cur is None:
            split_out.append(g)
            continue
        if g["key"] is not None and g["conf"] == "high": cur["nk"] = max(cur["nk"], 1)
        split_out.append(cur)
        if end - cur["hi"] > GAP_SPLIT:
            split_out.append(dict(gap=True, key=None, lo=(cur["hi"] + 3) & ~3))
    out = split_out

    srows = []
    if out and out[0]["lo"] > lo:
        srows.append(dict(lo=lo, hi=out[0]["lo"], ref_hi=lo, obj="unknown", conf="low",
                          ev="unreferenced-head", kind="gap", key=None, tu=None))
    if not out:
        srows.append(dict(lo=lo, hi=hi, ref_hi=lo, obj="unknown", conf="low", ev="no-refs",
                          kind="gap", key=None, tu=None))
    for i, g in enumerate(out):
        end = out[i + 1]["lo"] if i + 1 < len(out) else hi
        if g.get("gap"):
            srows.append(dict(lo=g["lo"], hi=end, ref_hi=g["lo"], obj="unknown", conf="low",
                              ev="unreferenced-gap", kind="gap", key=None, tu=None))
            continue
        tail = end - g["hi"]
        conf = g["conf"]
        if "tu" not in g:
            if g["key"] is None: conf = "low"
            elif g["nk"] < 2 and conf != "high": conf = "low"
        if tail > 0x400: conf = cap(conf, "medium")
        ats = atoms_in(g["lo"], end)
        if "tu" in g or g["key"] is not None:
            ev = g["ev"]
        else:
            # no family: say who references the data (game / library / mixed families)
            refs = set()
            for r in ats:
                if not r.get("note"): refs |= r["refs"]
            ev = census_text(refs) if refs else "only-externs"
        notes = sorted({r["note"] for r in ats if r.get("note")})
        if notes: ev += ";" + ";".join(notes)
        ev += ";atoms=%d" % g["n"]
        if g.get("coref"): ev += ";coref=%d" % g["coref"]
        if g.get("lead"): ev += ";lead=%d" % g["lead"]
        if g.get("unattr"):
            ev += ";unattr=%d" % g["unattr"]
            ub = end - g["own_hi"]          # bytes after the TU's own/co-referenced data
            if ub > 0x400: conf = "low"
            elif ub > 0x40: conf = cap(conf, "medium")
        if tail > 0x1000: conf = "low"
        obj = g["obj"] if g["key"] is not None or "tu" in g else "unknown"
        if "tu" in g: kind = "tu"
        elif g["key"] is not None and any(r["lab"][3] == "anon-rtti" for r in ats): kind = "anon"
        elif g["key"] is not None: kind = "fam"
        else: kind = "unk"
        if obj.startswith("file:") and obj[5:] in TU_AMBIG:
            kk, cands = TU_AMBIG[obj[5:]]
            ev += ";maybe-init:%s" % "|".join("#%03d" % c for c in cands)
        if tail > 0: ev += ";tail=0x%X" % tail
        srows.append(dict(obj=obj, conf=conf, kind=kind, key=g["key"], tu=g.get("tu"),
                          lo=g["lo"], hi=end, ref_hi=g["hi"], ev=ev))
        if "tu" in g: tu_rows.setdefault(g["tu"], {})[s] = (g["lo"], end)
    # 4-byte aligned starts.  An unaligned start (a literal pointing into a string or a
    # byte field) moves down to the word boundary when the previous row's referenced data
    # ends at or before it; otherwise the two rows share a word and are merged.
    fixed = []
    for r in srows:
        if r["lo"] % 4 and fixed:
            a = r["lo"] & ~3
            p = fixed[-1]
            if a >= p["ref_hi"] and a > p["lo"]:
                r["ev"] += ";start-aligned-down-from-%s" % H(r["lo"])
                p["hi"] = a; r["lo"] = a
            else:
                p["hi"] = r["hi"]; p["ref_hi"] = max(p["ref_hi"], r["ref_hi"])
                p["ev"] += ";merged-unaligned-row@%s(%s)" % (H(r["lo"]), r["obj"])
                continue
        fixed.append(r)
    srows = fixed
    for r in srows:
        r["seg"] = s
        rows.append(r)
    seg_stats[s] = dict(atoms=len(recs), tu_atoms=sum(1 for r in recs if r["tus"]),
                        demoted=len(bad), rows=len(srows), tus=len(anchors),
                        bytes_named=sum(r["hi"] - r["lo"] for r in srows if r["obj"] != "unknown"),
                        bytes_tu=sum(r["hi"] - r["lo"] for r in srows if r["kind"] == "tu"),
                        bytes=hi - lo, multi_tu=sum(1 for r in recs if len(r["tus"]) > 1))


# rodata beyond the per-object region (structural rows).  'bconf' is the confidence of the
# row's start boundary: each COMDAT group starts at its first item.
def srow(lo_, hi_, obj, conf, ev, bconf, why):
    return dict(seg="rodata", lo=lo_, hi=hi_, ref_hi=hi_, obj=obj, conf=conf, ev=ev, kind="struct",
                key=obj, tu=None, bconf=bconf, bwhy=why)


rows.append(srow(PEROBJ_RO_END, TI_END, "comdat:typeinfo(_ZTI)", "high", "rtti-typeinfo;name-sorted",
                 "high", "first-COMDAT-typeinfo"))
if TS_LO > TI_END:
    rows.append(srow(TI_END, TS_LO, "unknown", "low", "gap-between-ZTI-and-ZTS", "medium", "end-of-last-typeinfo"))
rows.append(srow(TS_LO, TS_END, "comdat:typename(_ZTS)", "high", "rtti-typename;name-sorted",
                 "high", "first-COMDAT-typename"))
if VT_LO > TS_END:
    rows.append(srow(TS_END, VT_LO, "unknown", "low", "gap-before-vtables", "medium", "end-of-last-typename"))
rows.append(srow(VT_LO, VT_END, "comdat:vtable(_ZTV)", "high", "vtables;name-sorted;rttiless=%d" % len(RTTILESS_VT),
                 "high", "first-COMDAT-vtable"))
rows.append(srow(VT_END, RO_END, "unknown", "low", "post-vtable-tail;strings+lib-const", "medium",
                 "end-of-last-vtable(slot-count)"))
rows = [r for r in rows if r["hi"] > r["lo"]]
SEG_ORDER = {"rodata": 0, "data": 1, "bss": 2}
rows.sort(key=lambda r: (SEG_ORDER[r["seg"]], r["lo"]))
SEG_BOUNDS = (("rodata", RO_VA, RO_END), ("data", DATA_VA, DATA_END), ("bss", BSS_VA, BSS_END))
# validation: rows tile each segment exactly, starts are 4-byte aligned
for sname, slo, shi in SEG_BOUNDS:
    rr = [r for r in rows if r["seg"] == sname]
    assert rr[0]["lo"] == slo and rr[-1]["hi"] == shi, sname
    for x, y in zip(rr, rr[1:]):
        assert x["hi"] == y["lo"], (sname, H(x["hi"]), H(y["lo"]))
    assert all(r["lo"] % 4 == 0 for r in rr), [H(r["lo"]) for r in rr if r["lo"] % 4]


# ---------------------------------------------------------------------------
# 7b. split units: boundary confidence, TU grouping, unit ids
# ---------------------------------------------------------------------------
def pow2_align(a, mx=8):
    al = 1
    while al < mx and a % (al * 2) == 0: al *= 2
    return al


def ident(r):
    """strong identity of a row (init TU or anonymous-namespace file), else None"""
    if r["kind"] == "tu": return "tu:%d" % r["tu"]
    if r["kind"] == "anon":
        ks = NAME_TUS.get(r["key"])
        return ("tu:%d" % ks[0]) if ks and len(ks) == 1 else r["key"]
    return None


def boundary(L, R):
    """(confidence, reason) of the cut between consecutive rows L and R (at R.lo).
    high   = two different objects proven on both sides (init order / anon RTTI) and the
             cut is exact (no unreferenced bytes between them beyond alignment padding);
    medium = a different object provably starts at or before the cut (position uncertain
             within the gap), or two different well-attested families meet exactly;
    low    = arbitrary cut inside unknown / weakly labelled data."""
    if "bconf" in R: return R["bconf"], R["bwhy"]
    if L["kind"] == "struct": return "medium", "after-structural-row"
    B = R["lo"]
    gap = B - L["ref_hi"]
    exact = gap <= 0 or gap < pow2_align(B)
    gtxt = "exact" if exact else "gap=0x%X" % gap
    iL, iR = ident(L), ident(R)
    if iL and iR and iL != iR:
        return ("high" if exact else "medium"), "%s|%s;%s" % (iL, iR, gtxt)
    if iL and iR:
        return "low", "same-object(%s);%s" % (iL, gtxt)
    if iR:
        return "medium", "start-of-%s;%s" % (iR, gtxt)
    if iL:
        if R["kind"] == "fam" and R["conf"] != "low" and exact:
            return "medium", "end-of-%s|%s;%s" % (iL, R["key"], gtxt)
        return "low", "end-of-%s-in-[%s,%s);%s" % (iL, H(L["ref_hi"]), H(R["hi"]), gtxt)
    if L["kind"] == "fam" and R["kind"] == "fam" and L["key"] != R["key"] and exact \
            and L["conf"] != "low" and R["conf"] != "low":
        return "medium", "%s|%s;%s" % (L["key"], R["key"], gtxt)
    return "low", "cut-in-unknown-or-weak-data;%s" % gtxt


CONF_MIN = lambda a, b: a if CONF_RANK[a] <= CONF_RANK[b] else b
bstats = collections.Counter()
for sname, slo, shi in SEG_BOUNDS:
    rr = [r for r in rows if r["seg"] == sname]
    for i, r in enumerate(rr):
        if i == 0:
            r["sb"] = ("high", "segment-start")
        else:
            r["sb"] = boundary(rr[i - 1], r)
            bstats[(sname, r["sb"][0])] += 1
    for i, r in enumerate(rr):
        r["eb"] = rr[i + 1]["sb"] if i + 1 < len(rr) else ("high", "segment-end")
        r["split_conf"] = CONF_MIN(r["sb"][0], r["eb"][0])
        r["unit_id"] = "%s_%08X" % (sname, r["lo"])
        # TU grouping
        if r["kind"] == "tu":
            r["tu_label"] = "init#%03d" % r["tu"]
        elif r["obj"].startswith(("file:", "class:")) and len(NAME_TUS.get(r["obj"], [])) == 1 \
                and TU_NAME[NAME_TUS[r["obj"]][0]][1] != "low":
            r["tu_label"] = "init#%03d" % NAME_TUS[r["obj"]][0]      # order-consistent (checked)
        elif r["obj"] != "unknown":
            r["tu_label"] = r["obj"]
        else:
            r["tu_label"] = "unknown"
UNITS = rows
rows = [(r["seg"], r["lo"], r["hi"], r["obj"], r["conf"], r["ev"]) for r in UNITS]
# object-order consistency of the final table: every row named like an init TU lies between
# the anchors that bracket that TU in its segment
order_bad = []
for sname, slo, shi in SEG_BOUNDS:
    anc = sorted((r["lo"], r["tu"]) for r in UNITS if r["seg"] == sname and r["kind"] == "tu")
    st, ak = [a for a, _ in anc], [k for _, k in anc]
    assert ak == sorted(ak), sname
    for r in UNITS:
        if r["seg"] != sname or r["kind"] == "tu": continue
        ks = NAME_TUS.get(r["obj"])
        if not ks: continue
        j = bisect.bisect_right(st, r["lo"])
        kb = ak[j - 1] if j else -1
        ka = ak[j] if j < len(ak) else N_INIT
        if not any(kb <= k <= ka for k in ks):
            order_bad.append((sname, H(r["lo"]), r["obj"]))
assert not order_bad, order_bad

# ---------------------------------------------------------------------------
# 8. extra tests: unity build (Q4), sort model (Q3), RTTI-less vtables
# ---------------------------------------------------------------------------
srcfiles = list(csv.DictReader(open(P("extracted", "analysis", "rtti_source_files.csv"))))
hash_files = collections.defaultdict(list)
for r in srcfiles: hash_files[r["anon_hash"]].append(r["file"])
file_tu = {}
for k, (nm, c, how) in TU_NAME.items():
    if nm.startswith("file:"): file_tu.setdefault(nm[5:], []).append(k)
unity = []
for hsh, files in sorted(hash_files.items()):
    if len(files) < 2: continue
    rr = sorted((ro_files[f][0], ro_files[f][1], f) for f in files if f in ro_files)
    between = []
    for (a0, a1, fa), (b0, b1, fb) in zip(rr, rr[1:]):
        others = sorted({fn for fn, (lo, hi) in ro_files.items() if a1 < lo and hi < b0})
        between.append((fa, fb, others))
    unity.append(dict(hash=hsh, files=files, tus={f: file_tu.get(f, []) for f in files}, between=between))

# Q3: sort-model tests on the 53 off-LIS anchors
la = SC["lex_anchors"]
off = [x for x in la if not x["on_lis"]]
onl = [x for x in la if x["on_lis"]]


def align(a):
    for k in (32, 16, 8, 4):
        if a % k == 0: return k
    return 1


al_off = collections.Counter(align(x["addr"]) for x in off)
al_on = collections.Counter(align(x["addr"]) for x in onl)
runs = SC["lex_runs"]


def run_of(a):
    for i, r in enumerate(runs):
        if r["lo"] <= a <= r["hi"]: return i
    return None


off_in_run_sorted = 0
run_members = collections.defaultdict(list)
for x in la:
    run_members[run_of(x["addr"])].append(x)
run_lis = {}
for i, mem in run_members.items():
    names = [m["cls"] for m in sorted(mem, key=lambda m: m["addr"])]
    tails = []
    keepn = 0
    # LIS length only
    for nm in names:
        j = bisect.bisect_right(tails, nm)
        if j == len(tails): tails.append(nm)
        else: tails[j] = nm
    run_lis[i] = (len(names), len(tails))
off_by_run = collections.Counter(run_of(x["addr"]) for x in off)
off_region = collections.Counter(libtag(x["addr"])[0] for x in off)
off_thunk = sum(1 for x in off if x["ott"] != 0)
on_thunk = sum(1 for x in onl if x["ott"] != 0)
off_small = sum(1 for x in off if func_end(x["addr"]) - x["addr"] <= 16)
on_small = sum(1 for x in onl if func_end(x["addr"]) - x["addr"] <= 16)
# duplicate tiny bodies (identical bytes elsewhere)
bodies = collections.Counter()
for f in FUNCS:
    n = func_end(f) - f
    if n <= 16: bodies[code[f - TEXT_VA:f - TEXT_VA + n]] += 1
off_dup = sum(1 for x in off if func_end(x["addr"]) - x["addr"] <= 16
              and bodies[code[x["addr"] - TEXT_VA:func_end(x["addr"]) - TEXT_VA]] > 1)
# RTTI vtable names around the RTTI-less block (namespace sort test)
rtti_vts = sorted((v, vt_class[v]) for v in comdat_vt)
# largest stretch of the COMDAT vtable region without any RTTI vtable
gap_best = max(zip(rtti_vts, rtti_vts[1:]), key=lambda p: p[1][0] - p[0][0])
(gb_a, gb_an), (gb_b, gb_bn) = gap_best
gb_lo, gb_hi = VT_END_OF[gb_a], gb_b
rl_in_gap = sum(1 for a in RTTILESS_VT if gb_lo <= a < gb_hi)
rl_lo, rl_hi = gb_lo, gb_hi
k_a = [n for v, n in rtti_vts].index(gb_an)
ns_before = [n for v, n in rtti_vts[max(0, k_a - 3):k_a + 1]]
ns_after = [n for v, n in rtti_vts[k_a + 1:k_a + 4]]


def ascents_pvalue(n, k):
    """P(a random permutation of n items has >= k ascents) via Eulerian numbers"""
    E = [[0] * (n + 1) for _ in range(n + 1)]
    E[0][0] = 1
    for i in range(1, n + 1):
        for j in range(i):
            E[i][j] = (j + 1) * E[i - 1][j] + (i - j) * (E[i - 1][j - 1] if j else 0)
    tot = sum(E[n][:n])
    return sum(E[n][k:n]) / tot


sti_p_len = ascents_pvalue(len(sti_seq_len), sti_sorted_len) if len(sti_seq_len) > 1 else 1.0

# agreement with split_candidates [9] rodata boundaries (high/medium)
ro_row_edges = sorted(r[1] for r in rows if r[0] == "rodata")
agree = collections.Counter()
for bd in SC["ro_boundaries"]:
    if bd["conf"] not in ("high", "medium"): continue
    lo_, hi_ = bd["lo"], bd["hi"]
    j = bisect.bisect_right(ro_row_edges, lo_)
    hit = j < len(ro_row_edges) and ro_row_edges[j] <= hi_
    agree[(bd["conf"], hit)] += 1

# ---------------------------------------------------------------------------
# 9. outputs
# ---------------------------------------------------------------------------
os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
os.makedirs(SCRATCH, exist_ok=True)
with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh, lineterminator="\n")
    w.writerow(["segment", "start", "end", "object", "confidence", "evidence",
                "unit_id", "tu", "split_confidence"])
    for r in UNITS:
        w.writerow([r["seg"], H(r["lo"]), H(r["hi"]), r["obj"], r["conf"], r["ev"],
                    r["unit_id"], r["tu_label"], r["split_conf"]])
with open(OUT_UNITS, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh, lineterminator="\n")
    w.writerow(["unit_id", "segment", "start", "end", "tu", "split_confidence", "evidence"])
    for r in UNITS:
        ev = "start=%s(%s);end=%s(%s);object=%s(%s)" % (r["sb"][0], r["sb"][1], r["eb"][0], r["eb"][1],
                                                       r["obj"], r["conf"])
        w.writerow([r["unit_id"], r["seg"], H(r["lo"]), H(r["hi"]), r["tu_label"], r["split_conf"], ev])

# scratch: per-TU table
with open(os.path.join(SCRATCH, "init_tus.txt"), "w", encoding="utf-8") as fh:
    fh.write("idx init_func name conf how ro_min data_min bss_min vptr_classes\n")
    for k in range(N_INIT):
        mm = lambda s: H(min(own[s][k])) if own[s][k] else "-"
        fh.write("%03d %s %s %s %s %s %s %s %s\n" % (k, H(INIT[k]), TU_NAME[k][0], TU_NAME[k][1],
                                                   TU_NAME[k][2], mm("rodata"), mm("data"), mm("bss"),
                                                   ",".join(tu_vptr[k][:3])))

counts = collections.Counter((r[0], r[4]) for r in rows)
named_rows = collections.Counter(r[0] for r in rows if r[3] != "unknown")
tu_named = collections.Counter(v[1] for k, v in TU_NAME.items() if v[0] != "unknown")
tu_kinds = collections.Counter(v[0].split(":")[0] for v in TU_NAME.values())

L = []
A = L.append
A("# M2: data layout and object order (.rodata / .data / .bss)")
A("")
A("Generated by `tools/m2/data_objects.py` (deterministic; re-run to refresh). Output table:")
A("`config/naming/data_objects.csv` (%d rows; `end` is exclusive)." % len(rows))
A("")
A("## Answers")
A("")
A("### Q1. The init_array is in object (link) order [high]")
A("")
A("- %d self-relative entries at %s-%s, walked by the runner at %s. Their targets are" %
  (N_INIT, H(INIT_LO), H(INIT_HI), H(INIT_RUNNER)))
A("  exactly the %d functions in %s-%s (no other function lies in that range), and those" % (sti_funcs_in_range, H(sti_lo), H(sti_hi)))
A("  addresses are *not* in table order (%d/%d adjacent pairs rise, i.e. random): the init" % (init_addr_rank_up, N_INIT - 1))
A("  functions form their own name-sorted .text group (`__sti___...` names sort after all `_Z...`).")
A("- The data each init function addresses rises with the table index:")
A("")
A("| segment | (TU,base) pairs | TUs with refs | on monotone chain | TUs on chain | shuffled-index baseline | raw adjacent TU minima rising | raw pairwise concordance |")
A("|---|---|---|---|---|---|---|---|")
for s in ("rodata", "data", "bss"):
    d = q1[s]
    up, n, conc, nt = q1_raw[s]
    A("| %s | %d | %d | %d (%.1f%%) | %d | %d | %d/%d | %.3f |" % (s, d["pairs"], d["tus"], d["kept"],
      100.0 * d["kept"] / max(1, d["pairs"]), d["tus_kept"], d["shuffled"], up, n, conc))
A("")
A("  The raw columns use each TU's minimum referenced base with no filtering (rodata: per-object")
A("  region only). Pairwise concordance = share of TU pairs whose minima are in table order")
A("  (0.5 = random). After the chain filter, adjacent minima rise by construction (%s), so that" %
  ", ".join("%s %d/%d" % (s, q1_adj[s][0], q1_adj[s][1]) for s in ("rodata", "data", "bss")))
A("  figure is not evidence; the raw columns are.")
A("")
A("  (rodata counted only in the per-object region %s-%s; refs into the COMDAT vtable" % (H(RO_VA), H(PEROBJ_RO_END)))
A("  region are name-sorted and excluded.) Off-chain pairs are references to other TUs'")
A("  externs (e.g. a few shared words near the end of .data used by many small init TUs).")
A("- Conclusion: armlink kept input order for `.init_array`, `.data`, `.bss` and `.constdata`")
A("  (identical section names, so the name sort falls back to input order), so every init")
A("  entry is a TU-order anchor in all three segments. %d of %d TUs have a bss anchor, %d a" %
  (sum(1 for k in range(N_INIT) if own["bss"][k]), N_INIT, sum(1 for k in range(N_INIT) if own["data"][k])))
A("  data anchor, %d a per-object rodata anchor." % sum(1 for k in range(N_INIT) if own["rodata"][k]))
A("- TU names: %s (kinds: %s). Full per-TU table: `build/m2_data/init_tus.txt` (scratch)." %
  (", ".join("%s %d" % (c, n) for c, n in sorted(tu_named.items())), ", ".join("%s %d" % kv for kv in sorted(tu_kinds.items()))))
A("- Name-sort check on the init functions (file-named TUs only, ordered by init address): key")
A("  `<len>_<File_cpp>` (EDG `__sti___<len>_<File_cpp>_<hash>`) is sorted for %d/%d adjacent pairs;" %
  (sti_sorted_len, max(0, len(sti_seq_len) - 1)))
A("  plain file name for %d/%d. Order: %s." % (sti_sorted_plain, max(0, len(sti_seq_plain) - 1),
  ", ".join(n for _, _, n in named_files)))
A("  P(>= that many ascents by chance) = %.1g. So the init functions are very likely named" % sti_p_len)
A("  `__sti___<len>_<File_cpp>_<hash>` and sorted by that name: an unnamed TU's init address")
A("  brackets its file name between its named neighbours (length prefix compared as text).")
A("")
A("### Q2. Per-object boundaries")
A("")
A("Atoms: every literal base V in a segment, extended to the furthest address touched through")
A("it (V+imm via LDR/STR/LDRH/LDRD/LDM/VLDR/ADD in the same function, offsets 0..0x%X)." % MAX_OFF)
A("Overlapping atoms are merged; an object boundary can only fall between atoms. Rows:")
A("")
A("1. Each init TU anchors a row from its first atom; the row covers the atoms its init")
A("   function touches plus following atoms that are unreferenced-by-others or referenced by")
A("   the TU's own family (evidence `init#NNN`). The row stops at an atom whose referrers all")
A("   lie more than 0x%X bytes of .text away from every non-init function already tied to the" % FAR_TEXT)
A("   TU (class methods are contiguous in the name-sorted .text, so such referrers are usually")
A("   another class's code).")
A("2. Between TU rows, atoms are labelled by the anonymous-namespace RTTI inside them or by the")
A("   single class/library family whose functions reference them (library = the function's tag")
A("   in `config/naming/library.csv`); runs of one family become rows (probable TUs without")
A("   static initialisers); unknown atoms join the preceding run. A family label that would")
A("   contradict object order is replaced by `extern-used-by-...` (Q5).")
A("3. Rows with no family say who references them: `refs-only-from-game(n)` (unlabelled game")
A("   functions per library.csv), `refs-only-from-lib:X(n)`, or `mixed(fam=n,...)` listing the")
A("   families; `only-externs` when the row's only atoms are externs of other objects.")
A("4. Rows tile the segment: each runs to the next row's start. `tail=` in the evidence is the")
A("   unreferenced stretch at the end of a row, i.e. where the true boundary may lie. An")
A("   unreferenced stretch longer than 0x%X bytes becomes its own `unreferenced-gap` row." % GAP_SPLIT)
A("5. Starts are 4-byte aligned: an unaligned start moves down to the word boundary when the")
A("   previous row's referenced data ends before it, else the two rows are merged")
A("   (%d moved, %d merged; evidence `start-aligned-down-from-...` / `merged-unaligned-row@...`)." %
  (sum(1 for r in UNITS if "start-aligned-down" in r["ev"]), sum(r["ev"].count("merged-unaligned-row") for r in UNITS)))
A("   String literals referenced by address cover the string through its NUL (%d atoms)." % n_str_ext)
A("")
A("| segment | bytes | atoms | atoms owned by init TUs | init TUs anchored | multi-TU atoms | rows | bytes in init-TU rows | bytes in named rows |")
A("|---|---|---|---|---|---|---|---|---|")
for s in ("rodata", "data", "bss"):
    d = seg_stats[s]
    A("| %s | 0x%X | %d | %d | %d | %d | %d | 0x%X (%.0f%%) | 0x%X (%.0f%%) |" % (s, d["bytes"], d["atoms"], d["tu_atoms"], d["tus"],
      d["multi_tu"], d["rows"], d["bytes_tu"], 100.0 * d["bytes_tu"] / d["bytes"],
      d["bytes_named"], 100.0 * d["bytes_named"] / d["bytes"]))
A("")
A("Rows by confidence (all %d rows, including the %d structural rodata rows): " % (len(rows), sum(1 for r in rows if r[0] == "rodata" and r[1] >= PEROBJ_RO_END)) + ", ".join("%s/%s %d" % (s, c, n) for (s, c), n in sorted(counts.items())) + ".")
A("")
A("Rodata structure (armlink sorts RO data by section name, then input order):")
A("")
A("| range | content | order |")
A("|---|---|---|")
A("| %s-%s | per-object `.constdata` | object order (anchored by init TUs and anon RTTI) |" % (H(RO_VA), H(PEROBJ_RO_END)))
A("| %s-%s | COMDAT typeinfo `_ZTI*` | name |" % (H(PEROBJ_RO_END), H(TI_END)))
A("| %s-%s | COMDAT typename `_ZTS*` | name |" % (H(TS_LO), H(TS_END)))
A("| %s-%s | COMDAT vtables `_ZTV*` (%d RTTI-less vtable headers found inside) | name |" %
  (H(VT_LO), H(VT_END), len(RTTILESS_VT)))
A("| %s-%s | strings and library constants | unverified (few code refs) |" % (H(VT_END), H(RO_END)))
A("")
A("Name sort of the COMDAT vtables, checked on namespaces: the longest stretch without any RTTI")
A("vtable is %s-%s and holds %d RTTI-less vtable headers. It sits between %s (last" % (H(rl_lo), H(rl_hi), rl_in_gap, ", ".join(ns_before)))
A("before) and %s (first after). In mangled form that is `_ZTVN19...`/`_ZTVN21...` before and" % ", ".join(ns_after))
A("`_ZTVN3map...` after, exactly where `_ZTVN2nn...` (nn:: SDK/NEX/Pia classes, built without RTTI)")
A("sorts. This supports both the name sort of COMDAT sections and the `nn::` namespace for the")
A("middleware.")
A("")
A("Agreement with split_candidates.txt [9] (a CSV row edge falls inside the [9] boundary")
A("interval): " + ", ".join("%s %d/%d" % (c, agree[(c, True)], agree[(c, True)] + agree[(c, False)]) for c in ("high", "medium")) + ".")
A("Those segments now carry init-TU indices, and the same method is applied to .data and .bss.")
A("")
A("### Q3. Sort model and the 53 off-sequence RTTI anchors")
A("")
A("- Alignment-then-name is rejected: off-sequence anchors have the same start-alignment mix")
A("  as on-sequence ones (off: %s; on: %s). %d of 53 are only 4-byte aligned, which a" %
  (dict(sorted(al_off.items())), dict(sorted(al_on.items())), al_off.get(4, 0)))
A("  higher-alignment group sorted after the 4-aligned one cannot contain.")
A("- Per-library grouping does not apply: all 53 are game classes (RTTI exists only for game")
A("  code). library.csv tags of these functions: %s." % dict(sorted(off_region.items())))
A("- What does explain them: separately name-sorted groups. Runs from split_candidates (by")
A("  address): " + "; ".join("%s-%s n=%d LIS=%d off=%d" % (H(r["lo"]), H(r["hi"]), run_lis.get(i, (0, 0))[0],
  run_lis.get(i, (0, 0))[1], off_by_run.get(i, 0)) for i, r in enumerate(runs)) + ".")
A("  %d of 53 off-sequence anchors are in order *within their own run*; they are off the" %
  (53 - sum(max(0, n - l) for n, l in run_lis.values())))
A("  global LIS only because the run is a second pass through the alphabet (consistent with")
A("  `_ZNK` const methods, `_ZThn` thunks: %d off vs %d on anchors have offset-to-top != 0," % (off_thunk, on_thunk))
A("  and the `__sti___` group). The rest are tiny functions: %d/53 off vs %d/%d on are <=16 bytes, and" %
  (off_small, on_small, len(onl)))
A("  %d of the off ones have byte-identical twins elsewhere (shared stubs, so the vtable-derived" % off_dup)
A("  class name is not the symbol's real name).")
A("- Model that fits all evidence: armlink's default input-section sort (attributes, then section")
A("  name, then input order). armcc per-function sections are named after the symbol, so code and")
A("  COMDAT RTTI sort by name, while `.constdata`/`.data`/`.bss`/`.init_array` share one name each")
A("  and stay in input (object) order.")
A("")
A("### Q4. Unity-build hypothesis: rejected for the shared-hash files [medium-high]")
A("")
for u in unity:
    A("- hash `%s`: %s. Init TUs: %s." % (u["hash"], ", ".join(u["files"]),
      ", ".join("%s=%s" % (f, ("#" + ",#".join("%03d" % k for k in v)) if v else "none") for f, v in u["tus"].items())))
    for fa, fb, others in u["between"]:
        ka, kb = file_tu.get(fa, []), file_tu.get(fb, [])
        nb = ("; %d init TUs between them in object order" % (abs(kb[0] - ka[0]) - 1)) if ka and kb else ""
        A("  - between %s and %s in rodata: %s%s" % (fa, fb, ", ".join(others) if others else "no other anon file", nb))
A("")
A("Files sharing an EDG hash are *not* contiguous in .constdata (other files' data sits between")
A("them) and, where they have static initialisers, each has its own init entry. A unity TU would")
A("emit one contiguous `.constdata` and one init function. The shared hash is therefore not a")
A("TU identity (it is probably derived from something common to several compiles).")
A("")
A("### Q5. Object-order contradictions (verifier finding 1)")
A("")
A("Rule: a `file:`/`class:` family that names init TU(s) can own data only between the init")
A("anchors that bracket those TUs in that segment. Atoms referenced only by such a family but")
A("lying past a later TU's start (or before an earlier one's) are externs: the family's code")
A("uses a global defined in another object (armcc addresses externs by symbol, so nothing in")
A("the access distinguishes them). They are now `unknown` rows with")
A("`extern-used-by-<family>(...)`. Anonymous-namespace RTTI cannot be an extern; none of it is")
A("out of order (asserted). Final table: every row named like an init TU lies inside that TU's")
A("bracket and TU rows rise with the init index in all three segments (asserted).")
A("")
A("| segment | atom | used by | that family's init TU | position | referencing functions |")
A("|---|---|---|---|---|---|")
for x in ORDER_FIX:
    A("| %s | %s-%s | %s | %s | %s | %s |" % (x["seg"], H(x["lo"]), H(x["hi"]), x["fam"],
      ", ".join("#%03d" % k for k in x["ks"]), x["where"],
      ", ".join("%s (%s)" % (H(f), func_class[f][0] if f in func_class else fam_of_func(f)[0] or libtag(f)[0])
                for f in x["refs"][:3]) + (" +%d" % (len(x["refs"]) - 3) if len(x["refs"]) > 3 else "")))
A("")
A("Each of these atoms has one or a few referencing functions, all methods of the family")
A("(anonymous-namespace classes are TU-local, so those methods really are in that file), and")
A("the same functions touch other objects' data too (the MapUnitSeq.cpp function also touches")
A(".data near init #027 and between #036 and #044). So they are externs, not a reordering.")
A("")
A("File matches that rested only on 'RTTI inside TU k's rodata span' were withdrawn when init")
A("TUs without any rodata lie between k and the next rodata anchor (the file's .constdata would")
A("sit in the same place for each of them, or for a TU without static init):")
A("")
for fn, (kk, cands) in sorted(TU_AMBIG.items()):
    A("- `%s`: candidates %s (previously named #%03d). Its rows keep the `file:` label with" %
      (fn, ", ".join("#%03d" % c for c in cands), kk))
    A("  `maybe-init:...`; no init TU is named after it.")
A("")
A("For MapDebug.cpp this removes the contradiction in the finding: its .data atom 0x004D131C lies")
A("after init #032's .data start, which fits #032 (or a TU without static init) but not #031.")
A("It is *not* settled as #032: a single-referrer atom can be an extern (as the table shows).")
A("")
A("### Q6. Split units")
A("")
A("Every row of `data_objects.csv` is one split unit, also listed in `config/naming/data_units.csv`")
A("(`unit_id,segment,start,end,tu,split_confidence,evidence`). Units tile each segment exactly")
A("(end exclusive), starts are 4-byte aligned, and no cut falls inside an atom (so no base+offset")
A("access crosses a unit edge). `unit_id` = `<segment>_<start>`; it is stable as long as the")
A("unit's start does not move. `tu` = `init#NNN` for init-TU rows and for rows named after a")
A("single medium/high init-TU name; else the `file:`/`class:`/`lib:`/`comdat:` label; else")
A("`unknown`.")
A("")
A("Boundary confidence (the cut at a unit's start):")
A("")
A("- high: init order or anonymous RTTI proves different objects on both sides and the cut is")
A("  exact (no unreferenced bytes between them beyond padding to the cut's alignment, max 8);")
A("  COMDAT group starts (first `_ZTI`/`_ZTS`/`_ZTV`).")
A("- medium: a proven object starts at or before the cut (the true edge is somewhere in the")
A("  unreferenced gap before it), two proven objects with a gap between them, or two different")
A("  medium-labelled families meeting exactly.")
A("- low: a cut inside unknown or weakly labelled data, or the end of a TU whose last bytes are")
A("  unreferenced.")
A("")
A("`split_confidence` of a unit = the lower of its start and end boundary confidences.")
A("")
A("| segment | units | units high / medium / low | internal boundaries | boundaries high / medium / low |")
A("|---|---|---|---|---|")
for sname, slo, shi in SEG_BOUNDS:
    uu = [r for r in UNITS if r["seg"] == sname]
    uc = collections.Counter(r["split_conf"] for r in uu)
    A("| %s | %d | %d / %d / %d | %d | %d / %d / %d |" % (sname, len(uu), uc["high"], uc["medium"], uc["low"],
      len(uu) - 1, bstats[(sname, "high")], bstats[(sname, "medium")], bstats[(sname, "low")]))
A("")
A("Unit `tu` kinds: %s." % ", ".join("%s %d" % kv for kv in sorted(collections.Counter(
    r["tu_label"].split("#")[0].split(":")[0] for r in UNITS).items())))
A("")
A("## Revision notes (after adversarial verification)")
A("")
A("- Function class labels no longer come from \"loads exactly one vtable\": a caller that builds")
A("  an object inline (e.g. a dialog of another class) was labelled as that class. Now a vptr")
A("  label needs a store of the vptr to [this,#0] (ctor/dtor), or the function sits within")
A("  0x1000 of that class's own vfuncs, or the vtable is anonymous-namespace (TU-local).")
A("- Init-TU names: the class an init function constructs is no longer used; a class name needs")
A("  the weighted and raw referrer pluralities to agree, labelled referrers must be at least a")
A("  quarter of all referrers (else `weak-refs`), and a family naming several TUs is capped low.")
A("- Second round (2.2% of sampled rows wrong): (1) out-of-order family rows resolved (Q5);")
A("  (2) library labels now come from `config/naming/library.csv` instead of string keywords and")
A("  the 64 KiB region buckets: the previous 121 `refs-only-from-sdk-regions` rows (52 with a")
A("  game-tagged referrer by this script's count, 53 by the verifier's) became, at this revision,")
A("  80 library rows, 13 `refs-only-from-game`, 9 `mixed(...)`, 2 `refs-only-from-unknown`, 2")
A("  class rows, and 15 were absorbed into init-TU rows; (3) every unknown row names")
A("  its referrers (`refs-only-from-game`, `mixed(...)`); no `unattributed` rows remain.")
A("- Library-named init TUs: %d (all low). They cluster in long index runs (mostly after #140), as" %
  sum(1 for v in TU_NAME.values() if v[0].startswith("lib:")))
A("  library objects linked together would; a library name with no same-library TU within +-3")
A("  indices is withdrawn (%d, `isolated-lib:...`). A library name never extends a TU row or" %
  sum(1 for v in TU_NAME.values() if ";isolated-lib:" in v[2]))
A("  merges a run into it (a library is many objects).")
A("- Split-unit view added (Q6): aligned starts, gap units, boundary confidences, data_units.csv.")
A("- TU rows stop at atoms referenced only from far-away code (see Q2 rule 1).")
A("- Q1 statistics: raw (unfiltered) adjacent rises and pairwise concordance are reported; row")
A("  counts include the structural rodata rows.")
A("")
A("## Caveats")
A("")
A("- Register tracking is linear (no control flow); a base reloaded on another path can be")
A("  missed, and an ADD of an array index can over-extend an atom (bounded at 0x%X)." % MAX_OFF)
A("- TU bounds are where referenced data starts; unreferenced bytes at a TU's end are given to")
A("  that TU (`tail=` marks how much). Non-init TUs are visible only through class labels.")
A("- Class labels on functions: virtual-function ownership (high), a vptr stored to [this,#0]")
A("  (ctor/dtor, %d functions), a single vptr load next to that class's own vfuncs (%d), and the" %
  (sum(1 for v in func_class.values() if v[2] == "ctor-store"), sum(1 for v in func_class.values() if v[2] == "vptr-near-vfunc")))
A("  lexical name coordinate. %d functions that only load one class's vptr (inline construction" % n_vptr_rejected)
A("  by a caller) get no class label from it. A class's data may still live in another .cpp")
A("  (singletons defined by their user), so names below `file:` rows are best treated as low.")
A("- Init-TU class names need the weighted and raw referrer pluralities to agree; a class that")
A("  would name several TUs is capped at low (`fam-in-N-TUs`). The class an init function")
A("  constructs is not used as a TU name. Library labels are library.csv's per-function tags,")
A("  which are themselves partly low-confidence (region priors, call-graph runs).")
A("- `extern-used-by-...` is inferred from object order; an extern that happens to lie inside")
A("  its user's bracket is not detected and still carries the user's family label.")
A("- The tail of .rodata after the vtables (%s-%s) is not split." % (H(VT_END), H(RO_END)))
A("")
with open(OUT_MD, "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(L))

rows_by_seg = collections.Counter(r[0] for r in rows)
rows_by_conf = collections.Counter(r[4] for r in rows)
obj_kinds = collections.Counter(r[3].split(":")[0] for r in rows)
summary = dict(rows=len(rows), init_entries=N_INIT, q1=q1, q1_adj_after_filter=q1_adj,
               q1_raw={s: dict(adj_up=v[0], adj_pairs=v[1], concordance=round(v[2], 4), tus=v[3])
                       for s, v in q1_raw.items()}, seg_stats=seg_stats,
               rows_by_seg=dict(rows_by_seg), rows_by_conf_total=dict(rows_by_conf), row_object_kinds=dict(obj_kinds),
               func_class_how=dict(collections.Counter(v[2] for v in func_class.values())),
               vptr_only_rejected=n_vptr_rejected,
               tu_kinds=dict(tu_kinds), tu_conf=dict(tu_named), sti_sorted_len=[sti_sorted_len, len(sti_seq_len) - 1],
               sti_sorted_plain=[sti_sorted_plain, len(sti_seq_plain) - 1],
               rows_by_conf={"%s/%s" % k: v for k, v in sorted(counts.items())},
               rodata_layout=dict(perobj_end=H(PEROBJ_RO_END), ti_end=H(TI_END), ts=[H(TS_LO), H(TS_END)],
                                  vt=[H(VT_LO), H(VT_END)], rttiless=len(RTTILESS_VT)),
               off_align=dict(al_off), on_align=dict(al_on))
with open(os.path.join(SCRATCH, "summary.json"), "w", encoding="utf-8") as fh:
    json.dump(summary, fh, indent=1, sort_keys=True)
print(json.dumps(summary, indent=1, sort_keys=True))
