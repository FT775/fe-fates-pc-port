#!/usr/bin/env python
"""M2 RTTI / vtable / constructor naming.

Reads extracted/code.bin and build/cache/analysis.json (stdlib only) and writes:
  config/naming/classes.csv  one row per RTTI typeinfo (class name, bases, vtables)
  config/naming/vfuncs.csv   one row per non-zero vtable slot
  config/naming/ctors.csv    functions that store a vtable address point into an object
Scratch/diagnostics go to build/m2_rtti/.

Facts this relies on (checked by the script, see build/m2_rtti/report.txt):
  * typeinfo objects are [vptr][name*]... with vptr = one of three __cxxabiv1 vtable
    address points (class / si / vmi); all live in .rodata.
  * vtables are [offset_to_top][typeinfo*][slot0]...; armlink virtual-function
    elimination (VFE) leaves 0 in slots of eliminated virtuals, so 0 is a valid slot.
    A vtable ends at the next vtable header, typeinfo object, non-zero non-code word,
    or a code-literal reference (the address point of a following no-RTTI vtable, whose
    [0][0] header is trimmed); trailing zeros are cut only down to the slot count implied
    by the class hierarchy.
  * constructors/destructors load (vtable+8) from a literal pool and store it at
    [this,#0] (primary) or [this,#-offset_to_top] (secondary).

Extra columns beyond the M2 brief (key on typeinfo_addr: anonymous-namespace class names
repeat across .cpp files): classes.csv kind/num_zero_slots/secondary_vtables; vfuncs.csv
is_thunk/inherited/owner_class/typeinfo_addr; ctors.csv typeinfo_addr. Zero (VFE) slots are
counted in num_slots but get no vfuncs.csv row.

Run: python tools/m2/rtti_names.py   (deterministic, re-runnable)
"""
import sys as _sys  # noqa: E402
if "--awakening-pass" not in _sys.argv:  # Fates: names come from the shipped symbol map
    _sys.exit("tools/m2/rtti_names.py is the Awakening RTTI/heuristic naming pass and still holds "
              "Awakening addresses; it would write wrong rows for Fates. Fates names come "
              "from the shipped symbol map: python tools/fates/symbols.py (docs/SYMBOLS.md).")
import bisect
import collections
import csv
import json
import os
import struct
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CODE_BIN = os.path.join(ROOT, "extracted", "code.bin")
ANALYSIS = os.path.join(ROOT, "build", "cache", "analysis.json")
OUT_DIR = os.path.join(ROOT, "config", "naming")
SCRATCH = os.path.join(ROOT, "build", "m2_rtti")

SEGS = [  # name, vaddr, size, file offset
    ("text", 0x00100000, 0x359B88, 0x000000),
    ("rodata", 0x0045A000, 0x05BA88, 0x35A000),
    ("data", 0x004B6000, 0x0314E8, 0x3B6000),
]
TEXT_LO, TEXT_HI = 0x00100000, 0x00100000 + 0x359B88

with open(CODE_BIN, "rb") as _f:
    BIN = _f.read()


def foff(va):
    for _n, a, s, f in SEGS:
        if a <= va < a + s:
            return f + va - a
    return None


def u32(va):
    o = foff(va)
    if o is None or o + 4 > len(BIN):
        return None
    return struct.unpack_from("<I", BIN, o)[0]


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def cstr(va, limit=512):
    o = foff(va)
    if o is None:
        return None
    e = BIN.find(b"\0", o, o + limit)
    if e < 0:
        return None
    try:
        return BIN[o:e].decode("ascii")
    except UnicodeDecodeError:
        return None


def hx(v):
    return "0x%08X" % v


with open(ANALYSIS, "r", encoding="utf-8") as _f:
    AN = json.load(_f)
FUNCS = sorted(AN["funcs"])
FUNCSET = set(FUNCS)
LITS = {}
for a, sz in AN["lits"]:
    LITS[a] = sz
JT = set(AN["jt_lits"])


def func_end(f):
    i = bisect.bisect_right(FUNCS, f)
    return FUNCS[i] if i < len(FUNCS) else TEXT_HI


def is_code_ptr(w):
    return w is not None and TEXT_LO <= w < TEXT_HI and (w & 3) == 0


# word index over .rodata + .data: value -> [addresses]
WIDX = collections.defaultdict(list)
for _n, _a, _s, _f in SEGS[1:]:
    for _i in range(0, _s - 3, 4):
        WIDX[struct.unpack_from("<I", BIN, _f + _i)[0]].append(_a + _i)
# literal-pool words in .text: value -> [addresses]
TLIT = collections.defaultdict(list)
for _a, _sz in AN["lits"]:
    if _sz == 4:
        TLIT[u32(_a)].append(_a)

# ----------------------------------------------------------------------------
# Itanium type-name demangler (nested-name / source-name subset, EDG anon ns)
# ----------------------------------------------------------------------------
BUILTIN = {"v": "void", "b": "bool", "c": "char", "a": "signed char", "h": "unsigned char",
           "s": "short", "t": "unsigned short", "i": "int", "j": "unsigned int", "l": "long",
           "m": "unsigned long", "x": "long long", "y": "unsigned long long", "f": "float",
           "d": "double", "w": "wchar_t", "e": "long double"}


class Demangler:
    def __init__(self, s):
        self.s, self.i = s, 0
        self.anon_cpp = None

    def peek(self, n=1):
        return self.s[self.i:self.i + n]

    def number(self):
        j = self.i
        while j < len(self.s) and self.s[j].isdigit():
            j += 1
        if j == self.i:
            raise ValueError("number")
        n = int(self.s[self.i:j])
        self.i = j
        return n

    def source_name(self):
        n = self.number()
        ident = self.s[self.i:self.i + n]
        if len(ident) != n or not n:
            raise ValueError("short ident")
        self.i += n
        if ident.startswith("_GLOBAL__N"):
            # EDG: _GLOBAL__N__<len>_<file with . -> _>_<hash>; GCC: _GLOBAL__N_1
            rest = ident[len("_GLOBAL__N"):]
            if rest.startswith("__"):
                k = 2
                while k < len(rest) and rest[k].isdigit():
                    k += 1
                ln = int(rest[2:k]) if k > 2 else 0
                fname = rest[k + 1:k + 1 + ln] if ln else ""
                if fname and len(fname) == ln:
                    fl = fname
                    for ext in ("_cpp", "_cc", "_cxx", "_c"):
                        if fl.endswith(ext):
                            fl = fl[: -len(ext)] + "." + ext[1:]
                            break
                    self.anon_cpp = fl
            return "(anonymous namespace)"
        return ident

    def template_args(self):
        self.i += 1  # 'I'
        args = []
        while self.peek() != "E":
            if not self.peek():
                raise ValueError("eof in template")
            if self.peek() == "L":
                e = self.s.index("E", self.i)
                args.append(self.s[self.i + 1:e])
                self.i = e + 1
            else:
                args.append(self.type())
        self.i += 1
        return "<" + ", ".join(args) + ">"

    def nested(self):
        self.i += 1  # 'N'
        parts = []
        if self.peek(2) == "St":
            self.i += 2
            parts.append("std")
        while self.peek() != "E":
            c = self.peek()
            if c.isdigit():
                parts.append(self.source_name())
            elif c == "I" and parts:
                parts[-1] += self.template_args()
            else:
                raise ValueError("bad nested char %r" % c)
        self.i += 1
        if not parts:
            raise ValueError("empty nested")
        return "::".join(parts)

    def type(self):
        c = self.peek()
        if c in BUILTIN:
            self.i += 1
            return BUILTIN[c]
        if c in "PRK":
            self.i += 1
            t = self.type()
            return t + {"P": "*", "R": "&", "K": " const"}[c]
        if c == "N":
            return self.nested()
        if self.peek(2) == "St":
            self.i += 2
            n = "std::" + self.source_name()
            if self.peek() == "I":
                n += self.template_args()
            return n
        if c.isdigit():
            n = self.source_name()
            if self.peek() == "I":
                n += self.template_args()
            return n
        raise ValueError("bad type char %r" % c)


def demangle(s):
    d = Demangler(s)
    try:
        t = d.type()
    except (ValueError, IndexError):
        return None, None
    if d.i != len(s):
        return None, None
    return t, d.anon_cpp


# ----------------------------------------------------------------------------
# typeinfo objects
# ----------------------------------------------------------------------------
def find_typeinfo_vptrs():
    """The three __cxxabiv1 typeinfo vtable address points: the vptr values of objects
    whose second word points at a string that demangles as a type name."""
    cnt = collections.Counter()
    for _n, a, s, f in SEGS[1:2]:
        for i in range(0, s - 7, 4):
            vptr, nptr = struct.unpack_from("<II", BIN, f + i)
            if not (0x0045A000 <= vptr < 0x004E7000):
                continue
            st = cstr(nptr, 256) if 0x0045A000 <= nptr < 0x004E7000 else None
            if st and (st[0].isdigit() or st[0] == "N" or st.startswith("St")):
                if demangle(st)[0]:
                    cnt[vptr] += 1
    return [v for v, c in cnt.most_common() if c >= 3]


TI_VPTRS = find_typeinfo_vptrs()
TYPEINFO = {}  # addr -> dict
for vp in TI_VPTRS:
    for t in WIDX[vp]:
        nm = cstr(u32(t + 4) or 0, 256)
        if not nm:
            continue
        dm, anon = demangle(nm)
        if dm is None:
            continue
        TYPEINFO[t] = {"addr": t, "vptr": vp, "mangled": nm, "name": dm, "anon_cpp": anon}
# classify the vptrs structurally: si has a typeinfo at +8, vmi has [flags][n][ti]...
VP_KIND = {}
for vp in TI_VPTRS:
    mem = [t for t in TYPEINFO.values() if t["vptr"] == vp]
    si = sum(1 for t in mem if u32(t["addr"] + 8) in TYPEINFO)
    vmi = sum(1 for t in mem if 1 <= (u32(t["addr"] + 12) or 0) <= 32 and u32(t["addr"] + 16) in TYPEINFO)
    if si > 0.8 * len(mem):
        VP_KIND[vp] = "si"
    elif vmi > 0.8 * len(mem):
        VP_KIND[vp] = "vmi"
    else:
        VP_KIND[vp] = "class"
TI_INNER = set()  # word addresses inside typeinfo objects (not the start)
for t in TYPEINFO.values():
    k = VP_KIND[t["vptr"]]
    t["kind"] = k
    t["bases"] = []  # (ti_addr, offset, is_virtual, is_public)
    if k == "si":
        t["bases"] = [(u32(t["addr"] + 8), 0, False, True)]
        t["size"] = 12
    elif k == "vmi":
        nb = u32(t["addr"] + 12)
        t["flags"] = u32(t["addr"] + 8)
        for i in range(nb):
            b = u32(t["addr"] + 16 + 8 * i)
            of = u32(t["addr"] + 20 + 8 * i)
            t["bases"].append((b, s32(of) >> 8, bool(of & 1), bool(of & 2)))
        t["size"] = 16 + 8 * nb
    else:
        t["size"] = 8
    for k2 in range(4, t["size"], 4):
        TI_INNER.add(t["addr"] + k2)
TI_STARTS = set(TYPEINFO)
NAME_OF = {a: t["name"] for a, t in TYPEINFO.items()}

# ----------------------------------------------------------------------------
# vtables
# ----------------------------------------------------------------------------
def header_at(p):
    """True if p looks like a vtable header [offset_to_top][typeinfo*]."""
    ot, ti = u32(p), u32(p + 4)
    if ti not in TYPEINFO or (p + 4) in TI_INNER:
        return False
    return ot is not None and -0x10000 < s32(ot) <= 0


VTABLES = []  # dicts
for tia in sorted(TYPEINFO):
    for ref in WIDX[tia]:
        if ref in TI_INNER or not (0x0045A000 <= ref < 0x004E74E8):
            continue
        ot = u32(ref - 4)
        if ot is None or not (-0x10000 < s32(ot) <= 0):
            continue
        VTABLES.append({"addr": ref - 4, "ti": tia, "ot": s32(ot)})
VTABLES.sort(key=lambda v: v["addr"])
VT_BY_ADDR = {v["addr"]: v for v in VTABLES}
VT_STARTS = set(VT_BY_ADDR)
def is_referenced(p):
    """A code literal points at p. Data-word matches are NOT honoured: packed byte data and
    UTF-16 text inside .rodata/.data can equal a vtable-area address by accident (this cut
    MI_TeamUnitMenu and ProcCardViewer short). In practice the code literal is the address
    point (+8) of a following vtable WITHOUT RTTI, whose [0][0] header then gets trimmed."""
    return p in TLIT


def scan(v, need):
    """Raw slot scan. Hard stops: next vtable header, typeinfo object, non-zero non-code
    word. Soft stop: an address a code literal points at, honoured only once the slot
    count reaches what the base class requires (a derived vtable is never shorter)."""
    p = v["addr"] + 8
    slots, stop = [], "eof"
    while True:
        if p in VT_STARTS or header_at(p):
            stop = "next_vtable"
            break
        if p in TI_STARTS:
            stop = "typeinfo"
            break
        w = u32(p)
        if w is None:
            break
        if not (w == 0 or is_code_ptr(w)):
            stop = "non_code"
            break
        if slots and len(slots) >= need and is_referenced(p):
            stop = "referenced"
            break
        slots.append(w)
        p += 4
        if len(slots) > 600:
            stop = "overflow"
            break
    return slots, stop


# class -> primary vtable / secondary vtables
PRIM, SECS = {}, collections.defaultdict(list)
for v in VTABLES:
    if v["ot"] == 0:
        if v["ti"] in PRIM:
            v["dup"] = True  # second primary vtable for one class: unexpected
        else:
            PRIM[v["ti"]] = v
    else:
        SECS[v["ti"]].append(v)


def find_subobject(ti, off, depth=0):
    """Outermost non-virtual base class located at byte offset off inside class ti."""
    if depth > 40 or ti not in TYPEINFO:
        return None
    for b, boff, virt, _pub in TYPEINFO[ti]["bases"]:
        if b in TYPEINFO and not virt and boff == off:
            return b
    for b, boff, virt, _pub in TYPEINFO[ti]["bases"]:
        if b in TYPEINFO and not virt and 0 <= boff < off:
            r = find_subobject(b, off - boff, depth + 1)
            if r is not None:
                return r
    return None


def subobject_base(v):
    """typeinfo of the base whose subobject this vtable serves (primary: the primary base)."""
    return find_subobject(v["ti"], -v["ot"])


def base_need(b, depth=0):
    """Slot count required by base class b: its primary vtable, else its primary base's."""
    if b is None or depth > 40:
        return 0
    if b in PRIM:
        return finalize(PRIM[b])
    for bb, bboff, bvirt, _ in TYPEINFO[b]["bases"]:
        if bboff == 0 and not bvirt:
            return base_need(bb, depth + 1)
    return 0


def finalize(v):
    if "slots" in v:
        return len(v["slots"])
    v["slots"] = []  # provisional, breaks recursion
    need = base_need(subobject_base(v))
    raw, stop = scan(v, need)
    nz = len(raw)
    while nz and raw[nz - 1] == 0:
        nz -= 1
    if stop in ("next_vtable", "typeinfo"):
        n = len(raw)  # bounded by a known object: trailing zeros are VFE slots
        v["trail"] = "kept" if nz < len(raw) else "none"
    else:
        n = max(nz, min(need, len(raw)))
        v["trail"] = "trimmed" if n < len(raw) else "none"
    v["raw_slots"], v["stop"] = raw, stop
    v["slots"] = raw[:n]
    v["need"] = need
    return n


for v in VTABLES:
    finalize(v)

# Secondary vtables for a base without its own vtable: the slot count is fixed by that base,
# so use the smallest count seen for the same base and trim extra trailing zeros.
_sec_by_base = collections.defaultdict(list)
for v in VTABLES:
    if v["ot"]:
        _sec_by_base[subobject_base(v)].append(v)
for b, vs in sorted(_sec_by_base.items(), key=lambda kv: kv[0] or 0):
    hard = [len(v["slots"]) for v in vs if v["stop"] in ("next_vtable", "typeinfo")]
    want = min(hard or [len(v["slots"]) for v in vs])
    if b in PRIM:
        pv = PRIM[b]
        # a secondary vtable for b has exactly b's slot count: grow a soft-bounded primary
        if hard and len(pv["slots"]) < want <= len(pv["raw_slots"]):
            pv["slots"] = pv["raw_slots"][:want]
            pv["trail"] = "set_from_secondaries"
        want = len(pv["slots"])
    for v in vs:
        if len(v["slots"]) > want and not any(v["slots"][want:]):
            v["slots"] = v["slots"][:want]
            v["trail"] = "trimmed_to_peers"
        elif len(v["slots"]) < want <= len(v["raw_slots"]):
            v["slots"] = v["raw_slots"][:want]
            v["trail"] = "set_from_peers"
        v["need"] = max(v.get("need", 0), want)

# ----------------------------------------------------------------------------
# ARM decoding helpers
# ----------------------------------------------------------------------------
def ror(v, r):
    return ((v >> r) | (v << (32 - r))) & 0xFFFFFFFF if r else v


def dp_imm(w):
    return ror(w & 0xFF, 2 * ((w >> 8) & 0xF))


def insn_words(f):
    """(addr, word) of the instructions of function f (literal pool words skipped)."""
    out = []
    a, e = f, func_end(f)
    while a < e:
        if a in LITS or a in JT:
            a += 4
            continue
        out.append((a, u32(a)))
        a += 4
    return out


def bl_target(a, w):
    if (w & 0x0F000000) == 0x0B000000 and (w >> 28) != 0xF:
        off = (w & 0xFFFFFF) << 2
        if off & 0x2000000:
            off -= 0x4000000
        return a + 8 + off
    return None


def b_target(a, w):
    if (w & 0x0F000000) == 0x0A000000 and (w >> 28) != 0xF:
        off = (w & 0xFFFFFF) << 2
        if off & 0x2000000:
            off -= 0x4000000
        return a + 8 + off
    return None


def is_return(w):
    return (w == 0xE12FFF1E or (w & 0xFFFF8000) == 0xE8BD8000  # BX LR / LDMFD SP!,{..PC}
            or w == 0xE1A0F00E or w == 0xE49DF004)


def writes(w):
    """Registers an instruction may overwrite (coarse)."""
    cond = w >> 28
    if cond == 0xF:
        return set()
    op = (w >> 25) & 7
    if op in (0, 1):
        if op == 0 and (w & 0x0FC000F0) == 0x00000090:  # MUL/MLA
            return {(w >> 16) & 15}
        if op == 0 and (w & 0x0F8000F0) == 0x00800090:  # long multiply
            return {(w >> 16) & 15, (w >> 12) & 15}
        if op == 0 and (w & 0x0E000090) == 0x00000090:  # halfword / doubleword transfers
            if w & 0x00100000:
                return {(w >> 12) & 15}
            return set()
        if (w & 0x0FFFFFF0) == 0x012FFF10 or (w & 0x0FFFFFF0) == 0x012FFF30:  # BX/BLX reg
            return {0, 1, 2, 3, 12, 14} if (w & 0x20) else set()
        opc = (w >> 21) & 15
        if 8 <= opc <= 11:
            return set()
        return {(w >> 12) & 15}
    if op in (2, 3):
        if w & 0x00100000:
            r = {(w >> 12) & 15}
            if (w & 0x00200000) or not (w & 0x01000000):
                r.add((w >> 16) & 15)
            return r
        if (w & 0x00200000) or not (w & 0x01000000):
            return {(w >> 16) & 15}
        return set()
    if op == 4:
        r = set()
        if w & 0x00100000:
            r = {i for i in range(16) if w & (1 << i)}
        if w & 0x00200000:
            r.add((w >> 16) & 15)
        return r
    if op == 5:
        return {0, 1, 2, 3, 12, 14} if (w & 0x01000000) else set()
    if op == 7 and (w & 0x0F100F10) == 0x0E100A10:  # VMOV core <- s
        return {(w >> 12) & 15}
    if (w & 0x0FE00000) == 0x0C400000 and (w & 0x00100000):  # VMOV two core <- d
        return {(w >> 12) & 15, (w >> 16) & 15}
    return set()


# address point -> vtable
ADDR_POINT = {v["addr"] + 8: v for v in VTABLES}


def is_mov_r0_imm(w):
    return (w & 0xFFFFF000) == 0xE3A00000


def find_operator_new():
    """operator new: the call target most often fed a constant size in r0 whose result
    later receives a vtable store (counted in a first pass over vtable-storing functions)."""
    cnt = collections.Counter()
    for f in FUNCS:
        ins = insn_words(f)
        has_vt = False
        for a, w in ins:
            if (w & 0x0F7F0000) == 0x051F0000:
                lit = a + 8 + ((w & 0xFFF) if (w & 0x00800000) else -(w & 0xFFF))
                if u32(lit) in ADDR_POINT:
                    has_vt = True
                    break
        if not has_vt:
            continue
        for i in range(1, len(ins)):
            t = bl_target(*ins[i])
            if t is not None and is_mov_r0_imm(ins[i - 1][1]):
                cnt[t] += 1
    return cnt


OPNEW_CANDS = find_operator_new()
OPNEW = OPNEW_CANDS.most_common(1)[0][0] if OPNEW_CANDS else None


_RESOLVED = {}


def resolve(t, hops=4):
    """Follow functions whose body is just [NOP] B target (veneer-like wrappers)."""
    if t in _RESOLVED:
        return _RESOLVED[t]
    r = t
    for _ in range(hops):
        o = foff(r)
        if o is None or not (TEXT_LO <= r < TEXT_HI):
            break
        w0 = u32(r)
        a, w = (r + 4, u32(r + 4)) if w0 == 0xE320F000 or w0 == 0xE1A00000 else (r, w0)
        bt = b_target(a, w) if w is not None and (w >> 28) == 0xE else None
        if bt is None or bt == r:
            break
        r = bt
    _RESOLVED[t] = r
    return r


def scan_vtable_writes(f, writers0=frozenset()):
    """Linear register-state scan. State per reg: ('this',off) | ('new',off) | ('vt',ap).
    Events: ('store', idx, vtable, base_kind, eff_off) | ('call', idx, target, r0state)
            | ('tail', idx, target, r0state)."""
    st = {0: ("this", 0)}
    ev = []
    ins = insn_words(f)
    for idx, (a, w) in enumerate(ins):
        if w is None:
            continue
        cond = w >> 28
        if cond == 0xF:
            continue
        t = bl_target(a, w)
        if t is not None:
            t = resolve(t)
            pre = st.get(0)
            ev.append(("call", idx, t, pre))
            for r in (0, 1, 2, 3, 12, 14):
                st.pop(r, None)
            if t == OPNEW:
                st[0] = ("new", 0)
            elif t in writers0 and pre is not None and pre[0] in ("this", "new"):
                st[0] = pre  # ctors/dtors return `this` (ARM C++ ABI)
            continue
        bt = b_target(a, w)
        if bt is not None:
            if cond == 0xE and not (f <= bt < func_end(f)):
                ev.append(("tail", idx, resolve(bt), st.get(0)))
            continue
        if (w & 0x0F7F0000) == 0x051F0000:  # LDR Rd,[PC,#imm]
            lit = a + 8 + ((w & 0xFFF) if (w & 0x00800000) else -(w & 0xFFF))
            val = u32(lit)
            rd = (w >> 12) & 15
            st.pop(rd, None)
            if val in ADDR_POINT and cond == 0xE:
                st[rd] = ("vt", val)
            continue
        opc = (w >> 21) & 15
        if (w & 0x0E000000) == 0x02000000 and opc in (2, 4):  # ADD/SUB Rd,Rn,#imm
            rn, rd = (w >> 16) & 15, (w >> 12) & 15
            imm = dp_imm(w) * (1 if opc == 4 else -1)
            s0 = st.get(rn)
            st.pop(rd, None)
            if s0 is not None and cond == 0xE:
                if s0[0] == "vt":
                    if s0[1] + imm in ADDR_POINT:
                        st[rd] = ("vt", s0[1] + imm)
                else:
                    st[rd] = (s0[0], s0[1] + imm)
            continue
        if (w & 0x0FEF0FF0) == 0x01A00000:  # MOV Rd,Rm
            rd, rm = (w >> 12) & 15, w & 15
            s0 = st.get(rm)
            st.pop(rd, None)
            if s0 is not None and cond == 0xE:
                st[rd] = s0
            continue
        if (w & 0x0F300000) == 0x05000000 or (w & 0x0F3000F0) == 0x010000B0:  # STR/STRB/STRH imm
            rn = (w >> 16) & 15
            sb = st.get(rn)
            if sb is not None and sb[0] == "this":
                ev.append(("mstore", idx, sb[1]))
        if (w & 0x0F700000) == 0x05000000:  # STR Rd,[Rn,#imm]
            rd, rn = (w >> 12) & 15, (w >> 16) & 15
            off = (w & 0xFFF) if (w & 0x00800000) else -(w & 0xFFF)
            sd = st.get(rd)
            if sd is not None and sd[0] == "vt" and rn not in (13, 15):
                sb = st.get(rn)
                if sb is None or sb[0] == "vt":
                    ev.append(("store", idx, ADDR_POINT[sd[1]], "unk", off))
                else:
                    ev.append(("store", idx, ADDR_POINT[sd[1]], sb[0], sb[1] + off))
            continue
        for r in writes(w):
            st.pop(r, None)
    return ev


# ----------------------------------------------------------------------------
# thunks: small functions in secondary vtables that adjust r0 then branch
# ----------------------------------------------------------------------------
def thunk_info(f):
    """(adjust, target) for 'ADD/SUB r0,r0,#imm ... B target' bodies of <= 4 instructions."""
    ins = insn_words(f)
    if not ins or len(ins) > 4:
        return None
    adj = None
    for i, (a, w) in enumerate(ins):
        bt = b_target(a, w)
        if bt is not None and (w >> 28) == 0xE:
            return (adj, bt) if adj is not None else None
        if (w & 0x0FFFF000) == 0x02400000:  # SUB r0,r0,#imm
            adj = (adj or 0) - dp_imm(w)
            continue
        if (w & 0x0FFFF000) == 0x02800000:  # ADD r0,r0,#imm
            adj = (adj or 0) + dp_imm(w)
            continue
        if w == 0xE320F000:  # NOP
            continue
        return None
    return None


def adjusts_this(f, amount):
    """True if one of the first instructions computes rX = r0 - amount (inline this-adjust)."""
    for _a, w in insn_words(f)[:6]:
        if (w & 0x0FFF0000) == 0x02400000 and dp_imm(w) == amount:
            return True
    return False


# ----------------------------------------------------------------------------
# build tables
# ----------------------------------------------------------------------------
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(SCRATCH, exist_ok=True)

# distinct classes whose vtables point at a function
SHARE = collections.defaultdict(set)
for v in VTABLES:
    for f in v["slots"]:
        if f:
            SHARE[f].add(v["ti"])


def ancestors(c, depth=0):
    """c and all its transitive bases."""
    out = {c}
    if depth < 40 and c in TYPEINFO:
        for b, _o, _v, _p in TYPEINFO[c]["bases"]:
            if b in TYPEINFO:
                out |= ancestors(b, depth + 1)
    return out


DEPTH = {}


def depth_of(c, d=0):
    if c in DEPTH:
        return DEPTH[c]
    r = 0
    if d < 40:
        for b, _o, _v, _p in TYPEINFO[c]["bases"]:
            if b in TYPEINFO:
                r = max(r, depth_of(b, d + 1) + 1)
    DEPTH[c] = r
    return r


def is_ancestor(a, b):
    return a != b and a in ancestors(b)


# Pure-virtual stub: a tiny function shared by classes with no common base, where every
# class using it is itself a base class (abstract) whose derived classes override the slot.
HAS_DERIVED = {b for t in TYPEINFO.values() for b, _o, _v, _p in t["bases"]}
PURE, PURE_CANDS = None, []
for f, cls in sorted(SHARE.items(), key=lambda kv: (-len(kv[1]), kv[0])):
    if len(cls) < 2 or len(insn_words(f)) > 4:
        continue
    common = None
    for c in cls:
        common = ancestors(c) if common is None else common & ancestors(c)
    if common or not all(c in HAS_DERIVED for c in cls):
        continue
    PURE_CANDS.append(f)
if len(PURE_CANDS) == 1:
    PURE = PURE_CANDS[0]

THUNKS = {}
for v in VTABLES:
    if v["ot"] == 0:
        continue
    for f in v["slots"]:
        if f and f not in THUNKS:
            ti = thunk_info(f)
            if ti is not None:
                THUNKS[f] = ti


def base_vtable(v):
    """Primary vtable of the nearest ancestor (along the primary-base chain of the subobject
    this vtable serves) that still has a vtable: VFE removed some bases' vtables entirely."""
    b, depth = subobject_base(v), 0
    while b is not None and depth < 40:
        if b in PRIM:
            return PRIM[b]
        nb = None
        for bb, bboff, bvirt, _ in TYPEINFO[b]["bases"]:
            if bboff == 0 and not bvirt and bb in TYPEINFO:
                nb = bb
                break
        b, depth = nb, depth + 1
    return None


# owner: most-derived common ancestor (or self) of every class sharing the function
OWNER = {}
for f, cls in SHARE.items():
    common = None
    for c in cls:
        common = ancestors(c) if common is None else common & ancestors(c)
    if common:
        OWNER[f] = max(sorted(common), key=depth_of)

with open(os.path.join(OUT_DIR, "vfuncs.csv"), "w", newline="", encoding="utf-8") as fo:
    w = csv.writer(fo, lineterminator="\n")
    w.writerow(["func_addr", "class", "slot", "vtable_addr", "n_classes_sharing", "is_pure_virtual",
                "is_thunk", "inherited", "owner_class", "typeinfo_addr", "confidence", "evidence"])
    for v in VTABLES:
        bv = base_vtable(v)
        cname = NAME_OF[v["ti"]]
        soft = v["stop"] not in ("next_vtable", "typeinfo")
        for i, f in enumerate(v["slots"]):
            if not f:
                continue
            n = len(SHARE[f])
            pure = 1 if f == PURE else 0
            thunk = 1 if f in THUNKS else 0
            inh = 1 if (bv is not None and i < len(bv["slots"]) and bv["slots"][i] == f) else 0
            own = OWNER.get(f)
            ev = ["secondary_vt_ot%d" % v["ot"]] if v["ot"] else ["primary_vt"]
            if pure:
                ev.append("pure_virtual_stub")
            if thunk:
                ev.append("thunk_adj%d" % THUNKS[f][0])
            elif v["ot"] and adjusts_this(f, -v["ot"]):
                ev.append("inline_this_adjust")
            if inh:
                ev.append("inherited")
            elif bv is not None and i < len(bv["slots"]):
                ev.append("override")
            elif bv is not None:
                ev.append("new_slot")
            if n == 1:
                ev.append("single_class")
            elif own is not None:
                ev.append("shared_lca")
            else:
                ev.append("shared_unrelated")
            if f not in FUNCSET:
                ev.append("not_in_funcmap")
            beyond = soft and i >= v.get("need", 0)
            if beyond:
                ev.append("soft_vt_end")
            if f not in FUNCSET or own is None:
                conf = "low"
            elif beyond or n > 1:
                conf = "medium"
            else:
                conf = "high"
            if thunk:
                conf = "high"
            if pure:
                conf = "medium"
            w.writerow([hx(f), cname, i, hx(v["addr"]), n, pure, thunk, inh,
                        NAME_OF.get(own, "") if own is not None else "", hx(v["ti"]), conf, "+".join(ev)])

# ---------------- classes.csv
with open(os.path.join(OUT_DIR, "classes.csv"), "w", newline="", encoding="utf-8") as fo:
    w = csv.writer(fo, lineterminator="\n")
    w.writerow(["class", "ts_mangled", "typeinfo_addr", "vtable_addr", "num_slots", "base_classes",
                "anon_cpp", "kind", "num_zero_slots", "secondary_vtables", "confidence", "evidence"])
    for tia in sorted(TYPEINFO):
        t = TYPEINFO[tia]
        pv = PRIM.get(tia)
        secs = sorted(SECS.get(tia, []), key=lambda v: v["addr"])
        bases = ";".join(NAME_OF.get(b, hx(b)) + ("(virtual)" if virt else "") +
                         (("@%d" % boff) if boff else "")
                         for b, boff, virt, _ in t["bases"])
        ev = ["typeinfo_" + t["kind"]]
        conf = "high"
        if pv is not None:
            nzs = sum(1 for s in pv["slots"] if s == 0)
            ev.append("vt_end_" + pv["stop"])
            tr = pv.get("trail")
            if tr in ("trimmed", "set_from_secondaries"):
                ev.append(tr)
            if pv["stop"] not in ("next_vtable", "typeinfo") and len(pv["slots"]) > pv.get("need", 0):
                conf = "medium"  # soft end beyond what the base requires
            if TLIT.get(pv["addr"] + 8):
                ev.append("addr_point_in_code")
            if pv.get("dup"):
                ev.append("dup_primary")
                conf = "low"
        else:
            nzs = ""
            ev.append("no_vtable")
        if secs:
            ev.append("secondary_vt")
        if t["anon_cpp"]:
            ev.append("edg_anon_ns")
        w.writerow([t["name"], t["mangled"], hx(tia), hx(pv["addr"]) if pv else "",
                    len(pv["slots"]) if pv else 0, bases, t["anon_cpp"] or "", t["kind"], nzs,
                    ";".join("%s@%d" % (hx(s["addr"]), -s["ot"]) for s in secs), conf, "+".join(ev)])

# ---------------- ctors.csv
# pass 1: every function that stores any vtable address point anywhere
WRITERS0 = set()
PASS1 = {}
for f in FUNCS:
    ev = scan_vtable_writes(f)
    if any(e[0] == "store" for e in ev):
        WRITERS0.add(f)
        PASS1[f] = ev
WRITERS0 = frozenset(WRITERS0)
# pass 2: with "ctor/dtor returns this" across calls to writers
WRITERS = {f: scan_vtable_writes(f, WRITERS0) for f in sorted(WRITERS0)}

IN_VT = collections.defaultdict(list)  # func -> [(class ti, slot, ot)]
for v in VTABLES:
    for i, s in enumerate(v["slots"]):
        if s:
            IN_VT[s].append((v["ti"], i, v["ot"]))


def this_primary_classes(f):
    """Classes whose primary vtable f stores at [this,#0]."""
    return [e[2]["ti"] for e in WRITERS.get(f, []) if e[0] == "store" and e[3] == "this"
            and e[4] == 0 and e[2]["ot"] == 0]


# operator delete: the target most often called/tail-called with r0 == this by vtable-slot
# functions that store their own class's vtable into this.
OPDEL_CANDS = collections.Counter()
for f, ev in WRITERS.items():
    if f not in IN_VT or not this_primary_classes(f):
        continue
    last = [e for e in ev if e[0] in ("call", "tail") and e[3] == ("this", 0)]
    if last and last[-1][2] not in WRITERS0:
        OPDEL_CANDS[last[-1][2]] += 1
OPDEL = OPDEL_CANDS.most_common(1)[0][0] if OPDEL_CANDS else None


def most_derived(order):
    for c in order:
        if all(o == c or is_ancestor(o, c) for o in order):
            return c
    return max(order, key=lambda c: (depth_of(c), -order.index(c)))


ctor_rows = []
for f in sorted(WRITERS):
    ev = WRITERS[f]
    stores = [e for e in ev if e[0] == "store"]
    calls = [e for e in ev if e[0] in ("call", "tail")]
    tprim = [e for e in stores if e[3] == "this" and e[4] == 0 and e[2]["ot"] == 0]
    tsec = [e for e in stores if e[3] == "this" and e[2]["ot"] != 0 and e[4] == -e[2]["ot"]]
    evid = []
    if f in THUNKS:
        cls = sorted({NAME_OF[x[0]] for x in IN_VT.get(f, [])})
        ctor_rows.append([hx(f), cls[0] if cls else "", "thunk", "high", "adjust_r0_then_b"])
        continue
    if tprim or tsec:
        own = tprim or tsec
        order = [e[2]["ti"] for e in own]
        derived = most_derived(order)
        first = own[0][1]
        anc = ancestors(derived)

        def is_base_call(e):
            return (e[3] == ("this", 0) and e[2] in WRITERS0 and e[2] != f and
                    any(c in anc and c != derived for c in this_primary_classes(e[2])))

        base_before = [e for e in calls if e[1] < first and is_base_call(e)]
        base_after = [e for e in calls if e[1] > first and is_base_call(e)]
        any_before = [e for e in calls if e[1] < first]
        po = [e[2]["ti"] for e in tprim]
        asc = len(set(po)) > 1 and all(po[i] == po[i + 1] or is_ancestor(po[i], po[i + 1]) for i in range(len(po) - 1))
        desc = len(set(po)) > 1 and all(po[i] == po[i + 1] or is_ancestor(po[i + 1], po[i]) for i in range(len(po) - 1))
        calls_del = OPDEL is not None and any(e[2] == OPDEL for e in calls)
        del_this = OPDEL is not None and any(e[2] == OPDEL and e[3] == ("this", 0) for e in calls)
        slots = [x for x in IN_VT.get(f, []) if x[0] in ancestors(derived) or derived in ancestors(x[0])]
        # A function in a vtable slot belongs to the class owning that slot (the LCA of all
        # classes using it). A derived dtor often stores only the inlined BASE vtable, so the
        # stored vtable alone would name the base class.
        slot_cls = derived
        if slots:
            own_f = OWNER.get(f)
            if own_f is not None and own_f != derived:
                slot_cls = own_f
                slots = [x for x in slots if x[0] in ancestors(slot_cls) or slot_cls in ancestors(x[0])] or slots
        if del_this or (calls_del and any(x[1] != 0 for x in slots)):
            kind = "deleting_dtor"
            conf = "high" if (del_this and (slots or base_after or desc)) else "medium"
            evid.append("calls_opdel_with_this" if del_this else "calls_opdel")
            if slots:
                evid.append("vt_slot%d" % slots[0][1])
        elif slots:
            kind = "dtor"
            conf = "high" if (base_after or desc or not any_before) else "medium"
            evid.append("vt_slot%d" % slots[0][1])
            if calls_del:
                evid.append("deletes_other_object")
                conf = "medium"
        elif base_before or asc:
            kind, conf = "ctor", "high"
            evid.append("base_ctor_then_store" if base_before else "base_vt_then_derived_vt")
        elif base_after or desc:
            kind, conf = "dtor", "medium"
            evid.append("store_then_base_dtor" if base_after else "derived_vt_then_base_vt")
        elif any_before:
            kind, conf = "ctor", "medium"
            evid.append("call_then_store")
        elif any(e[0] == "mstore" and e[1] < first for e in ev):
            kind, conf = "ctor", "medium"
            evid.append("member_init_then_store")
        else:
            kind, conf = "vtable_writer", "low"
            evid.append("store_only_root" if not TYPEINFO[derived]["bases"] else "store_only")
        if tsec:
            evid.append("secondary_vptr_store")
        if len(set(order)) > 1:
            evid.append("stores_%d_vtables" % len(set(order)))
        if any(e[3] == "this" and e[4] != 0 and not (e[2]["ot"] and e[4] == -e[2]["ot"]) for e in stores):
            evid.append("member_vptr_store")
        if slot_cls != derived:
            evid.append("class_from_slot")
            evid.append("stores_base_vt" if is_ancestor(derived, slot_cls) else "stores_other_vt")
            if not is_ancestor(derived, slot_cls) and conf == "high":
                conf = "medium"
        ctor_rows.append([hx(f), NAME_OF[slot_cls], kind, conf, "+".join(evid), slot_cls])
        continue
    # vtable stored only into a fresh `new` object, a member, or an untracked pointer
    newst = [e for e in stores if e[3] == "new" and e[4] == 0]
    if newst:
        derived = most_derived([e[2]["ti"] for e in newst])
        ctor_rows.append([hx(f), NAME_OF[derived], "vtable_writer", "low", "inline_new_object", derived])
        continue
    memb = [e for e in stores if e[3] == "this"]
    pool = memb or stores
    derived = most_derived([e[2]["ti"] for e in pool])
    ctor_rows.append([hx(f), NAME_OF[derived], "vtable_writer", "low",
                      "member_subobject_vptr" if memb else "untracked_base_reg", derived])

# thunks that do not write vtables
seen = {int(r[0], 16) for r in ctor_rows}
for f in sorted(THUNKS):
    if f in seen:
        continue
    adj, tgt = THUNKS[f]
    cls = sorted({NAME_OF[x[0]] for x in IN_VT.get(f, [])})
    ctor_rows.append([hx(f), cls[0] if cls else "", "thunk", "high" if len(cls) == 1 else "medium",
                      "adjust_r0_then_b"])
ctor_rows.sort(key=lambda r: int(r[0], 16))

with open(os.path.join(OUT_DIR, "ctors.csv"), "w", newline="", encoding="utf-8") as fo:
    w = csv.writer(fo, lineterminator="\n")
    w.writerow(["func_addr", "class", "kind", "typeinfo_addr", "confidence", "evidence"])
    for r in ctor_rows:
        w.writerow([r[0], r[1], r[2], hx(r[5]) if len(r) > 5 and r[5] else "", r[3], r[4]])

# ---------------- report (scratch)
slots_all = sum(len(v["slots"]) for v in VTABLES)
slots_nz = sum(1 for v in VTABLES for s in v["slots"] if s)
rep = []
rep.append("typeinfo vptrs: %s" % {hx(k): VP_KIND[k] for k in TI_VPTRS})
rep.append("typeinfos: %d kinds %s" % (len(TYPEINFO), dict(collections.Counter(t["kind"] for t in TYPEINFO.values()))))
rep.append("vtables: %d (primary %d, secondary %d, dup primary %d)" % (
    len(VTABLES), sum(1 for v in VTABLES if v["ot"] == 0), sum(1 for v in VTABLES if v["ot"]),
    sum(1 for v in VTABLES if v.get("dup"))))
rep.append("vtables with >=1 non-zero slot: %d; first slot non-zero: %d" % (
    sum(1 for v in VTABLES if any(v["slots"])), sum(1 for v in VTABLES if v["slots"] and v["slots"][0])))
rep.append("slots: %d total, %d non-zero, %d zero (VFE)" % (slots_all, slots_nz, slots_all - slots_nz))
rep.append("distinct functions in slots: %d; single-class: %d" % (len(SHARE), sum(1 for c in SHARE.values() if len(c) == 1)))
rep.append("stop reasons: %s" % dict(collections.Counter(v["stop"] for v in VTABLES)))
rep.append("trailing: %s" % dict(collections.Counter(v.get("trail") for v in VTABLES)))
rep.append("short-of-base vtables: %d" % sum(1 for v in VTABLES if len(v["slots"]) < v.get("need", 0)))
rep.append("addr point referenced from code literal: %d" % sum(1 for v in VTABLES if TLIT.get(v["addr"] + 8)))
rep.append("pure virtual stub: %s (shared by %d classes; candidates %s)" % (hx(PURE) if PURE else None, len(SHARE.get(PURE, ())), [hx(x) for x in PURE_CANDS]))
rep.append("thunks: %d" % len(THUNKS))
rep.append("operator delete guess: %s (%s)" % (hx(OPDEL) if OPDEL else None, [(hx(a), n) for a, n in OPDEL_CANDS.most_common(5)]))
rep.append("operator new guess: %s (%s)" % (hx(OPNEW) if OPNEW else None, [(hx(a), n) for a, n in OPNEW_CANDS.most_common(5)]))
rep.append("ctors.csv kinds: %s" % dict(collections.Counter(r[2] for r in ctor_rows)))
rep.append("ctors.csv conf: %s" % dict(collections.Counter(r[3] for r in ctor_rows)))
rep.append("classes with vtable: %d / %d; anon_cpp: %d" % (len(PRIM), len(TYPEINFO), sum(1 for t in TYPEINFO.values() if t["anon_cpp"])))
rep.append("slot funcs not in funcmap: %d: %s" % (sum(1 for f in SHARE if f not in FUNCSET),
                                                 " ".join(hx(f) for f in sorted(SHARE) if f not in FUNCSET)))
_pos = collections.defaultdict(set)
for v in VTABLES:
    for i, f in enumerate(v["slots"]):
        if f:
            _pos[f].add(i)
rep.append("functions found at >1 slot index: %d (only expected for the pure stub)" % sum(1 for p in _pos.values() if len(p) > 1))
_inh = _tot = 0
for v in VTABLES:
    b = base_vtable(v)
    if b is not None:
        for i in range(len(b["slots"])):
            _tot += 1
            _inh += v["slots"][i] == b["slots"][i]
rep.append("derived slots identical to base slot (inherited): %d / %d" % (_inh, _tot))
rep.append("virtual bases: %d; classes with secondary vtables: %d" % (
    sum(1 for t in TYPEINFO.values() for b in t["bases"] if b[2]), len({v["ti"] for v in VTABLES if v["ot"]})))
# Vtables WITHOUT RTTI (outside this task's scope, counted only so totals are not misread):
# [0][0] header in .rodata/.data whose address point (+8) is a code literal and starts with
# a non-zero code pointer, not inside an RTTI vtable's kept slots. A lower bound: no-RTTI
# vtables whose first slot VFE zeroed are not counted.
_rtti_cov = set()
for v in VTABLES:
    _rtti_cov.update(range(v["addr"], v["addr"] + 8 + 4 * len(v["slots"]), 4))
_nortti = 0
for _ap in sorted(TLIT):
    _h = _ap - 8
    if not (0x0045A000 <= _h < 0x004E74E8) or _h in _rtti_cov or _h in VT_STARTS:
        continue
    if u32(_h) == 0 and u32(_h + 4) == 0 and is_code_ptr(u32(_ap)):
        _nortti += 1
rep.append("no-RTTI vtable candidates ([0][0] header, +8 loaded by code literal, slot0 code): >=%d "
           "(not in the CSVs; RTTI totals above are not all vtables / all virtual functions)" % _nortti)
rep.append("vtables whose soft end trimmed a following no-RTTI [0][0] header: %d" % sum(
    1 for v in VTABLES if v.get("trail") == "trimmed"))
if PURE:
    rep.append("pure stub insns: %s" % " ".join("%08X" % x for _a, x in insn_words(PURE)[:4]))
with open(os.path.join(SCRATCH, "report.txt"), "w", encoding="utf-8") as fo:
    fo.write("\n".join(rep) + "\n")
print("\n".join(rep))
