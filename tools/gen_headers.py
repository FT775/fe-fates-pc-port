#!/usr/bin/env python3
"""Generate clean-room C++ class declarations from RTTI, and check them with GCC.

Usage (from anywhere; paths resolve from this file):

    python tools/gen_headers.py gen     write include/generated/ (headers, class_table.csv,
                                        check TUs, README.md); diagnostics in
                                        build/gen_headers/
    python tools/gen_headers.py check   compile the generated headers with the bundled
                                        arm-none-eabi-g++ (-std=gnu++11 -marm -mcpu=mpcore):
                                        1) -fsyntax-only, 2) -S -fdump-lang-class, then
                                        compare GCC's class layout dump with the binary
                                        (sizes, base offsets, primary vtable slot counts,
                                        secondary vtable counts, mangled vtable names).
                                        Report: build/gen_headers/check_report.txt.
                                        Exit code 1 on any mismatch.
    python tools/gen_headers.py all     gen + check (default)

Inputs (read only): config/naming/classes.csv, vfuncs.csv, ctors.csv, class_members.csv,
config/functions.csv, extracted/code.bin, tools/config.local.json (binutils_dir; the g++
driver is looked up in the same directory).

What is generated, and from what:
  * Names come only from RTTI (classes.csv, demangled typeinfo names). No code is copied.
  * Bases (order, offsets, public/virtual flags) are parsed from the typeinfo objects in
    code.bin (__si_class_type_info / __vmi_class_type_info layout).
  * Virtual functions: one placeholder per primary vtable slot, in slot order, read from
    code.bin at classes.csv vtable_addr for num_slots words. Slots equal to the primary
    base's slot are inherited (comment only); differing slots are overrides; slots past
    the base's count are new. Names are vfNN (NN = slot index); families that are also
    used as a non-primary base get vfNN_<Root> so they cannot override a primary-chain
    slot by accident. A pair of slots shown by ctors.csv (dtor at k / deleting dtor at
    k+1, medium/high) becomes "virtual ~X();" (the ARM C++ ABI gives a virtual dtor two
    slots, complete then deleting, like GCC). Pure-virtual stub slots become "= 0".
  * Sizes from operator new (config/readable/addresses.json operator_new; Fates 0x002FDC68): the size argument must be a constant (MOV/MVN/
    LDR-literal/ADD into r0, simulated over straight-line code with no branch target in
    between). The new object is then traced on the fall-through path (null check not
    taken, unconditional branches followed): registers holding object+offset, stack
    spills (through push/pop/sp adjustments) and constants are tracked. Events: a call
    of a constructor with r0 = object (ctors.csv kind=ctor, or a function whose last
    store to [this,#0] is a class's primary vtable address point; constructors return
    this, as do some helpers, so r0 stays tracked across calls), a store of a primary
    vtable address point to [object,#0], or any other store there. The last event wins
    (an inline derived constructor calls the base constructor, then stores its own
    vptr); earlier constructor/vtable events must be bases at offset 0 of the final
    class. A site is rejected when the last store to [object,#0] is not a known vtable,
    when any store goes past the size, or when the trace ends uncertainly (step limit,
    lost register, unknown branch) unless it had "settled" (a call that is not a base
    constructor call happened after the last event: a derived vptr store always comes
    right after the base constructors, before any other call). All accepted sites of a
    class must agree. Then two independent checks, either failure drops the size:
    constructors store only inside the object, and every function in the class's
    primary vtable loads/stores only inside sizeof(class) (linear scan, this = r0).
  * Sizes from base offsets: in a multiple-inheritance typeinfo, a base B at o followed
    (in offset order) by another base at o2 bounds B's data size: dsize(B) <= o2 - o.
    Bases sharing an offset: the dynamic one owns the gap (the others are empty). The
    tightest bound becomes B's dsize; sizeof is dsize rounded up to the alignment (the
    ARM C++ ABI, like GCC, reuses a non-POD base's tail padding: ProcInst dsize 0x2A,
    sizeof 0x2C, with a 2-aligned base at 42 in Effect). Combined with an operator-new
    size when both exist. Padding makes GCC reproduce dsize, sizeof and the offsets.
  * Emitted as u8 _unk[] padding plus static_assert(sizeof(C) == SIZE). Classes without
    a known size are emitted at their minimal layout (vptr + bases); a derived class's
    _unk then also covers base fields. A non-dynamic base that must sit at a non-zero
    offset gets a 1-byte placeholder so GCC does not apply the empty-base optimisation.
    No static_assert for those. Known limit: an object that is a non-polymorphic wrapper
    holding C at offset 0 would be indistinguishable from a C (too large a size); the
    access check only catches sizes that are too small.
  * A base is dynamic when it has a vtable, a dynamic base, no base at offset 0 in a
    vmi typeinfo (vptr first), or when a derived class has a secondary vtable at its
    offset (placeholder slots: highest non-zero slot seen there, a lower bound).
  * std:: and __cxxabiv1:: classes (C++ runtime) are skipped.

Output layout (include/generated/):
  fwd.h                   forward declarations (non-nested classes, template primaries)
  ns_<namespace>.h        classes in a named top-level namespace
  cls_<Root>.h            global classes whose offset-0 base chain ends at Root (>= 2)
  mixins.h                other global classes without bases (mostly mixin bases)
  misc.h                  other global classes
  anon/<file>_cpp.h       anonymous-namespace classes, per leaked .cpp file name
  all.h                   includes everything except anon/ (anonymous-namespace names
                          repeat across .cpp files, so each anon header is its own TU)
  class_table.csv         per class: header, size, size evidence, slot counts
  check/*.cpp             test TUs used by "check"
Header include cycles are broken by merging the headers of a strongly connected component.

Deterministic: same inputs give byte-identical output. Python 3 stdlib only.
"""
from __future__ import annotations

import collections
import csv
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMING = ROOT / "config" / "naming"
CODE_BIN = ROOT / "extracted" / "code.bin"
FUNCS_CSV = ROOT / "config" / "functions.csv"
OUT = ROOT / "include" / "generated"
SCRATCH = ROOT / "build" / "gen_headers"
LOCAL_CFG = ROOT / "tools" / "config.local.json"

# Per-game constants: segments and the code.bin hash from extracted/layout.json (written by
# tools/extract_rom.py for this game's ROM), operator new from config/readable/addresses.json.
sys.path.insert(0, str(ROOT / "tools" / "readable"))
import gameaddr  # noqa: E402


def _layout() -> dict:
    p = ROOT / "extracted" / "layout.json"
    if not p.is_file():
        raise SystemExit("missing extracted/layout.json (run tools/extract_rom.py first)")
    return json.loads(p.read_text())


_LAY = _layout()
OPERATOR_NEW = gameaddr.addr("operator_new")
CODE_SHA1 = _LAY["code_bin"]["sha1"]  # the extracted base revision (updates are refused, D-002)
SEGS = [(_LAY[k]["addr"], _LAY[k]["size"], _LAY[k]["file_offset"]) for k in ("text", "rodata", "data")]
TEXT_LO, TEXT_HI = _LAY["text"]["addr"], _LAY["text"]["addr"] + _LAY["text"]["size"]
SKIP_TOP = ("std", "__cxxabiv1")
GXX_FLAGS = ["-std=gnu++11", "-marm", "-mcpu=mpcore"]

BIN = b""


def u32(va):
    for a, s, f in SEGS:
        if a <= va <= a + s - 4:
            return struct.unpack_from("<I", BIN, f + va - a)[0]
    return None


def h(v):
    return "0x%08X" % v


def read_csv(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def split_scope(name):
    """Split a demangled name on '::' at template depth 0."""
    parts, depth, cur, i = [], 0, "", 0
    while i < len(name):
        c = name[i]
        if c == "<":
            depth += 1
        elif c == ">":
            depth -= 1
        if depth == 0 and name.startswith("::", i):
            parts.append(cur)
            cur = ""
            i += 2
            continue
        cur += c
        i += 1
    parts.append(cur)
    return parts


def split_targs(s):
    out, depth, cur = [], 0, ""
    for c in s:
        if c == "<":
            depth += 1
        elif c == ">":
            depth -= 1
        if c == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += c
    if cur.strip():
        out.append(cur.strip())
    return out


def ident(s):
    return re.sub(r"[^A-Za-z0-9_]", "_", s)


ANON = "(anonymous namespace)"


# ----------------------------------------------------------------------------
# Model
# ----------------------------------------------------------------------------
class Cls:
    def __init__(self, row):
        self.row = row
        self.name = row["class"]
        self.ti = int(row["typeinfo_addr"], 16)
        self.vt = int(row["vtable_addr"], 16) if row["vtable_addr"] else None
        self.num_slots = int(row["num_slots"] or 0)
        self.kind = row["kind"]
        self.mangled = row["ts_mangled"]
        self.anon_cpp = row["anon_cpp"]
        self.parts = split_scope(self.name)
        self.anon = ANON in self.parts
        self.bases = []          # (Cls|None, offset, virtual, public, base_ti)
        self.secondary = []      # (vtable addr, offset)
        for sv in filter(None, row["secondary_vtables"].split(";")):
            a, o = sv.split("@")
            self.secondary.append((int(a, 16), int(o)))
        self.slots = []
        self.outer = None        # enclosing class (nested)
        self.nested = []
        self.ns = []             # namespace components (may include ANON)
        self.local = self.name   # spelling relative to its namespace scope
        self.header = None
        self.dynamic = False
        self.vptr_inferred = False
        self.size_new = None
        self.size_new_ev = []
        self.size_gap = None
        self.size_gap_ev = []
        self.target = None
        self.target_src = ""
        self.size_conflict = ""
        self.emitted = None      # sizeof as emitted
        self.dsize = 0           # data size as a base (0 for empty)
        self.pad = 0
        self.placeholder = False
        self.decl_slots = 0      # primary slot count GCC should produce
        self.eff = []            # effective primary slots (values; None = unknown)
        self.dtor_k = None       # dtor pair introduced here
        self.anon_stem = ""
        self.template = None     # (template name, [args]) for specialisations

    def key(self):
        return self.ti


def load():
    global BIN
    if not CODE_BIN.exists():
        raise SystemExit("missing %s (run tools/extract_rom.py first)" % CODE_BIN)
    BIN = CODE_BIN.read_bytes()
    got = hashlib.sha1(BIN).hexdigest()
    if got != CODE_SHA1:
        raise SystemExit("extracted/code.bin SHA-1 %s != extracted/layout.json %s (re-extract the "
                         "base revision; updates are not supported)" % (got, CODE_SHA1))
    need = [NAMING / n for n in ("classes.csv", "vfuncs.csv", "ctors.csv", "class_members.csv")]
    missing = [p.name for p in need if not p.is_file()]
    if missing:
        raise SystemExit("config/naming/ is missing %s: run the M2 naming tools for this game first "
                         "(tools/m2/rtti_names.py, class_members.py)" % ", ".join(missing))
    rows = read_csv(NAMING / "classes.csv")
    allc = [Cls(r) for r in rows]
    by_ti = {c.ti: c for c in allc}
    vf = read_csv(NAMING / "vfuncs.csv")
    ctors = read_csv(NAMING / "ctors.csv")
    members = read_csv(NAMING / "class_members.csv")
    funcs = read_csv(FUNCS_CSV)
    return allc, by_ti, vf, ctors, members, funcs


def parse_bases(c, by_ti):
    ti = c.ti
    if c.kind == "si":
        b = u32(ti + 8)
        c.bases = [(by_ti.get(b), 0, False, True, b)]
    elif c.kind == "vmi":
        n = u32(ti + 12)
        for i in range(n):
            b = u32(ti + 16 + 8 * i)
            of = u32(ti + 20 + 8 * i)
            off = struct.unpack("<i", struct.pack("<I", of))[0] >> 8
            c.bases.append((by_ti.get(b), off, bool(of & 1), bool(of & 2), b))
    else:
        c.bases = []


# ----------------------------------------------------------------------------
# ARM decoding (just enough for the operator new size scan)
# ----------------------------------------------------------------------------
def ror(v, r):
    return ((v >> r) | (v << (32 - r))) & 0xFFFFFFFF if r else v


def dp_imm(w):
    return ror(w & 0xFF, 2 * ((w >> 8) & 0xF))


def branch_target(a, w):
    off = w & 0xFFFFFF
    if off & 0x800000:
        off -= 0x1000000
    return (a + 8 + off * 4) & 0xFFFFFFFF


def written_regs(w):
    """Core registers an instruction may write (conservative superset) and its control
    kind: None, 'b', 'bl', 'blx', 'ret', 'pcwrite' or 'unknown'."""
    cond = w >> 28
    if cond == 0xF:
        return set(range(16)), "unknown"
    cls = (w >> 25) & 7
    if cls == 5:
        return ({14, 0, 1, 2, 3, 12} if (w >> 24) & 1 else set()), ("bl" if (w >> 24) & 1 else "b")
    if (w & 0x0FFFFFF0) == 0x012FFF10:  # BX
        return set(), ("ret" if (w & 0xF) == 14 else "pcwrite")
    if (w & 0x0FFFFFF0) == 0x012FFF30:  # BLX reg
        return {14, 0, 1, 2, 3, 12}, "blx"
    if cls in (0, 1):
        if cls == 0 and (w & 0x90) == 0x90:  # multiply / extra load-store / swap / ldrex
            if (w & 0x60) and not (w >> 20) & 1:  # STRH/STRD/LDRD (L=0 encodings)
                regs = set()
                if (w & 0xF0) == 0xD0:  # LDRD
                    rd = (w >> 12) & 15
                    regs |= {rd, rd + 1}
                if (w >> 21) & 1 or not (w >> 24) & 1:
                    regs.add((w >> 16) & 15)
                return regs, None
            regs = {(w >> 12) & 15, (w >> 16) & 15}
            return regs - {15}, ("pcwrite" if 15 in regs and (w & 0x00100000) else None)
        op = (w >> 21) & 0xF
        s = (w >> 20) & 1
        if 8 <= op <= 11 and not s:
            if cls == 1:
                if op in (8, 10):  # MOVW / MOVT
                    return {(w >> 12) & 15}, None
                return set(), None  # MSR immediate, NOP/YIELD/WFE/WFI/SEV hints
            if (w & 0x0FBF0FFF) == 0x010F0000 or (w & 0x0FFF0FF0) == 0x016F0F10:  # MRS, CLZ
                return {(w >> 12) & 15}, None
            if (w & 0x0F900FF0) == 0x01000050:  # QADD etc.
                return {(w >> 12) & 15}, None
            return set(), None  # MSR register, BKPT, ...
        if 8 <= op <= 11:
            return set(), None  # TST/TEQ/CMP/CMN
        rd = (w >> 12) & 15
        if rd == 15:
            if (w & 0x0FFFFFFF) == 0x01A0F00E:  # MOV pc, lr
                return set(), "ret"
            return set(), "pcwrite"
        return {rd}, None
    if cls in (2, 3):
        if cls == 3 and (w & 0x10):  # media
            return {(w >> 12) & 15, (w >> 16) & 15} - {15}, None
        L = (w >> 20) & 1
        P = (w >> 24) & 1
        W = (w >> 21) & 1
        rn = (w >> 16) & 15
        rd = (w >> 12) & 15
        regs = set()
        if L:
            regs.add(rd)
        if W or not P:
            regs.add(rn)
        if 15 in regs:
            return regs - {15}, ("ret" if rn == 13 and L and rd == 15 else "pcwrite")
        return regs, None
    if cls == 4:
        L = (w >> 20) & 1
        W = (w >> 21) & 1
        rn = (w >> 16) & 15
        regs = set()
        if L:
            regs |= {i for i in range(16) if w >> i & 1}
        if W:
            regs.add(rn)
        if 15 in regs:
            return regs - {15}, "ret"
        return regs, None
    # coprocessor / VFP
    if (w & 0x0F100010) == 0x0E100010:  # MRC / VMOV core<-S / VMRS
        rd = (w >> 12) & 15
        return ({rd} if rd != 15 else set()), None
    if (w & 0x0FF00000) == 0x0C500000:  # MRRC / VMOV two cores
        return {(w >> 12) & 15, (w >> 16) & 15}, None
    if cls == 6 and (w >> 21) & 1:
        return {(w >> 16) & 15}, None
    return set(), None


def is_branch_any(w):
    return (w >> 28) != 0xF and ((w >> 25) & 7) == 5


def mem_access(w):
    """Single/dual/multiple store or load with an immediate address form.
    -> dict(L, rn, regs:[(reg, offset_from_address)], addr_off, wb) or None.
    addr_off: offset added to rn for the access; wb: new rn offset delta or None."""
    cls = (w >> 25) & 7
    if cls == 2:
        P, U, W, L = (w >> 24) & 1, (w >> 23) & 1, (w >> 21) & 1, (w >> 20) & 1
        imm = (w & 0xFFF) * (1 if U else -1)
        width = 1 if (w >> 22) & 1 else 4
        return dict(L=L, rn=(w >> 16) & 15, regs=[((w >> 12) & 15, 0)], width=width,
                    addr_off=imm if P else 0, wb=(imm if (W or not P) else None))
    if cls == 0 and (w & 0x90) == 0x90 and (w & 0x60) and (w >> 22) & 1:  # imm halfword/dual
        P, U, W, L = (w >> 24) & 1, (w >> 23) & 1, (w >> 21) & 1, (w >> 20) & 1
        imm = (((w >> 4) & 0xF0) | (w & 0xF)) * (1 if U else -1)
        rd = (w >> 12) & 15
        sh = (w >> 5) & 3
        if not L and sh == 3:  # STRD
            regs, width = [(rd, 0), (rd + 1, 4)], 4
        elif not L and sh == 2:  # LDRD
            regs, width, L = [(rd, 0), (rd + 1, 4)], 4, 1
        else:
            regs, width = [(rd, 0)], 2
        return dict(L=L, rn=(w >> 16) & 15, regs=regs, width=width,
                    addr_off=imm if P else 0, wb=(imm if (W or not P) else None))
    if cls == 4:
        P, U, W, L = (w >> 24) & 1, (w >> 23) & 1, (w >> 21) & 1, (w >> 20) & 1
        rl = [i for i in range(16) if w >> i & 1]
        n = len(rl)
        if U:
            start = 4 if P else 0
        else:
            start = -4 * n if P else -4 * n + 4
        regs = [(r, start + 4 * j) for j, r in enumerate(rl)]
        return dict(L=L, rn=(w >> 16) & 15, regs=regs, width=4, addr_off=0,
                    wb=((4 * n if U else -4 * n) if W else None))
    return None


class Machine:
    """Tracks registers holding (object + offset), constants and stack spills."""

    def __init__(self, regs, retain_unknown):
        self.retain_unknown = retain_unknown  # keep r0 tracked across unknown calls
        self.regs = dict(regs)   # reg -> offset from object start
        self.consts = {}
        self.stack = {}          # sp offset -> object offset
        self.max_store = 0
        self.max_access = 0      # loads and stores through the object pointer

    def alive(self):
        return bool(self.regs or self.stack)


class SizeScanner:
    MAX_STEPS = 600

    def __init__(self, classes, by_ti, ctors, funcs):
        self.by_ti = by_ti
        self.ap = {}  # vtable address point -> Cls (primary)
        for c in classes:
            if c.vt:
                self.ap[c.vt + 8] = c
        self.sec_ap = set()
        for c in classes:
            for a, _o in c.secondary:
                self.sec_ap.add(a + 8)
        self.ctor_csv = {}
        for r in ctors:
            if r["kind"] == "ctor" and r["confidence"] in ("high", "medium"):
                c = by_ti.get(int(r["typeinfo_addr"], 16))
                if c:
                    self.ctor_csv[int(r["func_addr"], 16)] = c
        self.fend = {int(r["addr"], 16): int(r["end"], 16) for r in funcs}
        self.fstarts = sorted(self.fend)
        self.targets = set(self.fstarts)
        for a in range(TEXT_LO, TEXT_HI, 4):
            w = u32(a)
            if is_branch_any(w):
                self.targets.add(branch_target(a, w))
        self.sites = []
        self._inf = {}
        self._rt = {}
        self._acc = {}
        self.ctor_max = {}   # func -> max this-relative store end
        self.disagree = []   # ctors.csv vs inference

    def func_start(self, a):
        import bisect
        i = bisect.bisect_right(self.fstarts, a) - 1
        return self.fstarts[i] if i >= 0 else TEXT_LO

    # -- constructor inference -------------------------------------------------
    def ctor_class(self, f, depth=0):
        """Class constructed by function f (this in r0): ctors.csv, else the last primary
        vtable address point f stores to [this,#0] (linear scan of f's body). None if f
        stores nothing or an unknown value there last."""
        if f in self._inf:
            return self._inf[f]
        if depth > 24:
            return None
        self._inf[f] = None  # recursion guard
        inferred, max_store = self._infer(f, depth)
        self.ctor_max[f] = max_store
        res = inferred
        if f in self.ctor_csv:
            if inferred is not None and inferred is not self.ctor_csv[f]:  # inference wins
                self.disagree.append("%s: ctors.csv says %s, vtable stores say %s" % (
                    h(f), self.ctor_csv[f].name, inferred.name))
            else:
                res = self.ctor_csv[f]
        self._inf[f] = res
        return res

    def linear(self, mc, f, end, depth):
        """Linear walk of a function body yielding (addr, event). After an unconditional
        return or branch, words are skipped until the next branch target (literal pools
        and other data after a return are never decoded)."""
        dead = False
        snap = {}  # forward branch target -> register state at the (first) branch
        for a in range(f, min(end, f + 4 * 600), 4):
            if dead:
                if a not in self.targets:
                    continue
                dead = False
                if a in snap:
                    mc.regs, mc.consts, mc.stack = (dict(x) for x in snap[a])
            ev = self.step(mc, a, u32(a), depth + 1)
            if ev is None:
                continue
            if ev[0] == "b" and a < ev[1] < end and ev[1] not in snap:
                snap[ev[1]] = (dict(mc.regs), dict(mc.consts), dict(mc.stack))
            if ev[0] in ("ret", "b") and ev[-1] == 0xE:
                dead = True
            yield a, ev

    def this_access(self, f):
        """Highest this-relative byte (exclusive) f loads or stores, by a linear scan with
        this = r0 at entry (strict: r0 is dropped across calls that do not return this)."""
        if f in self._acc:
            return self._acc[f]
        end = self.fend.get(f)
        if end is None or not (TEXT_LO <= f < TEXT_HI):
            self._acc[f] = 0
            return 0
        mc = Machine({0: 0}, False)
        for _a, _ev in self.linear(mc, f, end, 0):
            pass
        self._acc[f] = mc.max_access
        return mc.max_access

    def returns_this(self, f, depth=0):
        """f returns its incoming r0 on every return found by a linear scan of its body
        (member constructors without RTTI, helpers). Tail branches out of f must also go
        to a function that returns this."""
        if f in self._rt:
            return self._rt[f]
        if depth > 24:
            return False
        self._rt[f] = False
        end = self.fend.get(f)
        if end is None or not (TEXT_LO <= f < TEXT_HI):
            return False
        mc = Machine({0: 0}, False)
        rets = 0
        ok = True
        for a, ev in self.linear(mc, f, end, depth):
            if ev[0] == "ret":
                rets += 1
                if mc.regs.get(0) != 0:
                    ok = False
                    break
            elif ev[0] == "b" and not (f <= ev[1] < end):
                rets += 1
                if mc.regs.get(0) != 0 or not self.returns_this(ev[1], depth + 1):
                    ok = False
                    break
            elif ev[0] == "pcwrite":
                ok = False
                break
        res = ok and rets > 0
        self._rt[f] = res
        return res

    def _infer(self, f, depth):
        end = self.fend.get(f)
        if end is None or not (TEXT_LO <= f < TEXT_HI):
            return None, 0
        mc = Machine({0: 0}, False)
        last = None
        for a, ev in self.linear(mc, f, end, depth):
            kind = ev[0]
            if kind == "vt":
                last = ev[1]
            elif kind == "store0":
                last = "unknown"
            elif kind in ("ret", "b"):
                continue
        if last == "unknown":
            last = None
        return last, mc.max_store

    # -- one instruction ---------------------------------------------------------
    def step(self, mc, a, w, depth):
        """Apply instruction w at a to machine mc. Returns an event tuple or None:
        ('vt', Cls) / ('store0', value) store to [object,#0]; ('ctor', Cls) call of a
        constructor on the object; ('call', target); ('escape',) object pointer stored to
        memory; ('published',) passed as r1-r3; ('ret',), ('b', target, cond),
        ('pcwrite',), ('lost',) a tracked register changed in an unmodelled way."""
        cond = w >> 28
        regs, kind = written_regs(w)
        if kind == "b":
            return ("b", branch_target(a, w), cond)
        if kind == "bl":
            t = branch_target(a, w)
            r0 = mc.regs.get(0)
            ev = None
            keep = None
            if t != OPERATOR_NEW and r0 is not None:
                # Constructors return this (ARM C++ ABI). Other callees may too (member
                # constructors without RTTI, helpers returning their argument), so r0
                # stays tracked: a later store through it is then seen, never missed.
                cc = self.ctor_class(t, depth)
                if cc is not None or mc.retain_unknown or self.returns_this(t, depth):
                    keep = r0
                if cc is not None:
                    if r0 == 0:
                        ev = ("ctor", cc)
                elif r0 == 0:
                    ev = ("call", t)
            if ev is None and keep is None and any(r in mc.regs for r in (1, 2, 3)):
                ev = ("published",)
            for r in regs:
                mc.regs.pop(r, None)
                mc.consts.pop(r, None)
            if keep is not None:
                mc.regs[0] = keep
            return ev
        if kind == "blx":
            ev = ("published",) if any(r in mc.regs for r in (0, 1, 2, 3)) else None
            for r in regs:
                mc.regs.pop(r, None)
                mc.consts.pop(r, None)
            return ev
        if kind == "ret":
            return ("ret", cond)
        if kind in ("pcwrite", "unknown"):
            return ("pcwrite",)

        ev = None
        ma = mem_access(w)
        new_regs, new_consts = {}, {}
        definite = set()  # registers overwritten with an unrelated value (not "lost")
        sp_new = None  # stack map after an sp-relative access with writeback
        if ma is not None:
            rn = ma["rn"]
            base = mc.regs.get(rn)
            wb = ma["wb"] or 0
            if rn == 13 and base is None:
                # keys are offsets from the current sp; writeback moves sp by wb
                sp_new = {k - wb: v for k, v in mc.stack.items()}
            if not ma["L"]:
                for r, o in ma["regs"]:
                    if r in mc.regs:
                        if sp_new is not None:
                            sp_new[ma["addr_off"] + o - wb] = mc.regs[r]  # spill / push
                        else:
                            ev = ("escape",)
                    if base is not None:
                        eff = base + ma["addr_off"] + o
                        mc.max_store = max(mc.max_store, eff + ma["width"])
                        mc.max_access = max(mc.max_access, eff + ma["width"])
                        if eff == 0 and ev is None:
                            v = mc.consts.get(r)
                            if ma["width"] == 4 and v is not None and v in self.ap:
                                ev = ("vt", self.ap[v])
                            else:
                                ev = ("store0", v)
            else:
                for r, o in ma["regs"]:
                    definite.add(r)
                    if base is not None:
                        mc.max_access = max(mc.max_access, base + ma["addr_off"] + o + ma["width"])
                    if sp_new is not None:
                        so = ma["addr_off"] + o
                        if so in mc.stack:
                            new_regs[r] = mc.stack[so]  # reload / pop
                        sp_new.pop(so - wb, None)
                    if rn == 15 and (w >> 25) & 7 == 2 and ma["width"] == 4 and cond == 0xE:
                        v = u32(a + 8 + ma["addr_off"])
                        if v is not None:
                            new_consts[r] = v
            if ma["wb"] is not None and base is not None:
                new_regs[rn] = base + ma["wb"]
        elif (w >> 25) & 7 == 6:  # coprocessor / VFP load-store (VLDR/VSTR/VLDM/VSTM)
            rn = (w >> 16) & 15
            base = mc.regs.get(rn)
            P, U, W, L = (w >> 24) & 1, (w >> 23) & 1, (w >> 21) & 1, (w >> 20) & 1
            n = w & 0xFF
            if (w & 0x0FE00000) in (0x0C400000,):  # VMOV two cores <-> D (MCRR/MRRC)
                if not L and (((w >> 12) & 15) in mc.regs or ((w >> 16) & 15) in mc.regs):
                    ev = ("escape",)
            elif base is not None:
                if P and not W:  # VSTR / VLDR
                    lo = base + (4 * n if U else -4 * n)
                    hi = lo + (8 if (w >> 8) & 1 else 4)
                else:
                    lo = base + (0 if U else -4 * n)
                    hi = lo + 4 * n
                    if W:
                        new_regs[rn] = base + (4 * n if U else -4 * n)
                mc.max_access = max(mc.max_access, hi)
                if not L:
                    mc.max_store = max(mc.max_store, hi)
                    if lo <= 0 < hi:
                        ev = ("store0", None)
        else:
            rd = (w >> 12) & 15
            rn = (w >> 16) & 15
            if (w & 0x0FEF0FF0) == 0x01A00000:  # MOV(S) rd, rm
                rm = w & 15
                definite.add(rd)
                if rm in mc.regs:
                    new_regs[rd] = mc.regs[rm]
                elif rm in mc.consts and cond == 0xE:
                    new_consts[rd] = mc.consts[rm]
            elif (w & 0x0FEF0000) == 0x03A00000:  # MOV rd,#imm
                definite.add(rd)
                if cond == 0xE:
                    new_consts[rd] = dp_imm(w)
            elif (w & 0x0FEF0000) == 0x03E00000:  # MVN rd,#imm
                definite.add(rd)
                if cond == 0xE:
                    new_consts[rd] = (~dp_imm(w)) & 0xFFFFFFFF
            elif (w & 0x0FE00000) in (0x02800000, 0x02400000):  # ADD/SUB(S) rd, rn, #imm
                im = dp_imm(w) * (1 if (w & 0x0FE00000) == 0x02800000 else -1)
                if rd == 13 and rn == 13:
                    sp_new = {k - im: v for k, v in mc.stack.items()}
                    definite.add(13)
                elif rn in mc.regs:
                    new_regs[rd] = mc.regs[rn] + im
                elif rn in mc.consts and cond == 0xE:
                    new_consts[rd] = (mc.consts[rn] + im) & 0xFFFFFFFF
                    definite.add(rd)
                elif rn == 15 and cond == 0xE:  # ADR
                    new_consts[rd] = (a + 8 + im) & 0xFFFFFFFF
                    definite.add(rd)
                else:
                    definite.add(rd)
            elif (w & 0x0FF00000) in (0x03000000, 0x03400000):  # MOVW / MOVT
                definite.add(rd)
        # an unmodelled write is a loss only if the instruction reads a tracked register
        reads = set()
        if (w >> 25) & 7 in (0, 1) and ma is None:
            reads = {(w >> 16) & 15}
            if not (w >> 25) & 1:
                reads |= {w & 15, (w >> 8) & 15}
        tracked_read = bool(reads & set(mc.regs))
        lost = False
        for r in regs:
            if r == 13:
                if sp_new is None and mc.stack:
                    mc.stack = {}
                    lost = lost or not mc.regs
            if r in mc.regs:
                del mc.regs[r]
                if r not in definite and r not in new_regs and (tracked_read or ma is not None):
                    lost = True
            mc.consts.pop(r, None)
        if sp_new is not None:
            mc.stack = sp_new
        mc.regs.update(new_regs)
        mc.consts.update(new_consts)
        if lost and ev is None:
            ev = ("lost",)
        return ev

    # -- operator new sites --------------------------------------------------------
    def const_r0(self, bl):
        start = max(self.func_start(bl), bl - 16 * 4)
        consts = {}
        for a in range(start, bl + 4, 4):
            if a in self.targets and a != start:
                consts = {}
            if a == bl:
                break
            w = u32(a)
            regs, kind = written_regs(w)
            cond = w >> 28
            new = None
            rd = (w >> 12) & 15
            if cond == 0xE:
                if (w & 0x0FEF0000) == 0x03A00000:      # MOV rd,#imm
                    new = (rd, dp_imm(w))
                elif (w & 0x0FEF0000) == 0x03E00000:    # MVN rd,#imm
                    new = (rd, (~dp_imm(w)) & 0xFFFFFFFF)
                elif (w & 0x0F7F0000) == 0x051F0000:    # LDR rd,[pc,#imm]
                    off = w & 0xFFF
                    la = a + 8 + (off if (w >> 23) & 1 else -off)
                    v = u32(la)
                    if v is not None:
                        new = (rd, v)
                elif (w & 0x0FE00000) in (0x02800000, 0x02400000, 0x03800000):  # ADD/SUB/ORR imm
                    rn = (w >> 16) & 15
                    if rn in consts:
                        op = (w >> 21) & 0xF
                        v = consts[rn]
                        im = dp_imm(w)
                        v = (v + im) if op == 4 else (v - im) if op == 2 else (v | im)
                        new = (rd, v & 0xFFFFFFFF)
                elif (w & 0x0FEF0FF0) == 0x01A00000:    # MOV rd,rm
                    rm = w & 15
                    if rm in consts:
                        new = (rd, consts[rm])
            if kind in ("b", "bl", "blx", "ret", "pcwrite", "unknown"):
                consts = {}
                continue
            for r in regs:
                consts.pop(r, None)
            if new and new[0] != 15:
                consts[new[0]] = new[1]
        return consts.get(0)

    def trace(self, bl):
        """Follow the object returned by operator new on the fall-through path.

        'settled': after the last constructor/vtable event, a call was made that is not a
        constructor call on a base subobject (r0 untracked, or r0 = object start and the
        callee is not a constructor). A derived class's vptr store comes right after its
        base-class constructors and before any other call, so no later vptr store can
        follow; an otherwise uncertain end (step limit, lost register) is then accepted."""
        mc = Machine({0: 0}, True)
        events = []
        a = bl + 4
        follows = 0
        end = "limit"
        settled = False
        for _ in range(self.MAX_STEPS):
            if not (TEXT_LO <= a < TEXT_HI):
                end = "eof"
                break
            w = u32(a)
            settle_here = False
            if (w & 0x0F000000) == 0x0B000000 and (w >> 28) != 0xF and events:
                r0 = mc.regs.get(0)
                t = branch_target(a, w)
                if r0 is None or (r0 == 0 and self.ctor_class(t) is None):
                    settle_here = True
            ev = self.step(mc, a, w, 0)
            if ev is not None and ev[0] in ("ctor", "vt", "store0"):
                settled = False
            elif settle_here and any(e[0] in ("ctor", "vt") for e in events):
                settled = True
            if ev is not None:
                k = ev[0]
                if k == "b":
                    if ev[2] == 0xE:
                        follows += 1
                        if follows > 16:
                            end = "branch_limit"
                            break
                        a = ev[1]
                        continue
                elif k == "ret":
                    if ev[1] == 0xE:
                        end = "return"
                        break
                elif k in ("escape", "published", "pcwrite", "lost"):
                    end = {"pcwrite": "unknown_branch"}.get(k, k)
                    break
                else:
                    events.append(ev + (a,))
            if not mc.alive():
                end = "dead"
                break
            a += 4
        if settled and end not in self.ACCEPT_END:
            end += "+settled"
        return events, end, mc.max_store

    def scan(self):
        for a in range(TEXT_LO, TEXT_HI, 4):
            w = u32(a)
            if (w & 0x0F000000) != 0x0B000000 or (w >> 28) == 0xF:
                continue
            if branch_target(a, w) != OPERATOR_NEW:
                continue
            size = self.const_r0(a)
            events, end, max_store = self.trace(a)
            self.sites.append((a, size, events, end, max_store))

    ACCEPT_END = ("return", "escape", "published", "dead")

    def decide(self, is_base_of):
        """-> per-class size votes; site log lines; verdict counts."""
        votes = collections.defaultdict(list)
        log = []
        stats = collections.Counter()
        for a, size, events, end, max_store in self.sites:
            typed = [e for e in events if e[0] in ("ctor", "vt", "store0")]
            last = typed[-1] if typed else None
            verdict, cls = None, None
            if size is None:
                verdict = "no_const_size"
            elif last is None:
                verdict = "no_class_event"
            elif last[0] == "store0":
                verdict = "unknown_vtable_store"
            elif end not in self.ACCEPT_END and not end.endswith("+settled"):
                verdict = "uncertain_end:" + end
            elif max_store > size:
                verdict = "store_beyond_size"
            else:
                cls = last[1]
                # earlier stores to [object,#0] are overwritten by the final vptr store
                # (value-initialisation zeroing, intermediate vptrs): only the order of
                # the constructor / vtable events is checked
                bad = [e for e in typed[:-1] if e[0] != "store0" and not is_base_of(e[1], cls)]
                if bad:
                    verdict = "inconsistent_chain"
                    cls = None
                else:
                    verdict = "ok"
            stats[verdict.split(":")[0]] += 1
            evs = " ".join(
                "%s:%s@%s" % (e[0], e[1].name if isinstance(e[1], Cls) else
                              (h(e[1]) if isinstance(e[1], int) else "?"), h(e[-1]))
                for e in events[:8])
            log.append("%s size=%s end=%s max_store=0x%X verdict=%s class=%s events=[%s]" % (
                h(a), ("0x%X" % size) if size is not None else "?", end, max_store, verdict,
                cls.name if cls else "-", evs))
            if verdict == "ok":
                votes[cls.ti].append((size, a, last[0]))
        return votes, log, stats



# ----------------------------------------------------------------------------
# Generation
# ----------------------------------------------------------------------------
def build_model():
    allc, by_ti, vf, ctors, members, funcs = load()
    report = []
    skipped = [c for c in allc if c.parts[0] in SKIP_TOP]
    classes = [c for c in allc if c.parts[0] not in SKIP_TOP]
    by_ti = {c.ti: c for c in classes}
    for c in classes:
        parse_bases(c, by_ti)
        for b, off, virt, pub, bti in c.bases:
            if b is None:
                raise SystemExit("base typeinfo %s of %s not a generated class" % (h(bti), c.name))
    funcname = {int(r["addr"], 16): r["name"] for r in funcs}
    pure = {int(r["func_addr"], 16) for r in vf if r["is_pure_virtual"] == "1"}

    # anonymous .cpp stem
    for c in classes:
        if c.anon:
            m = re.search(r"_GLOBAL__N__\d+_(\w+?)_([0-9a-f]{8})", c.mangled)
            c.anon_stem = ident(c.anon_cpp.replace(".", "_")) if c.anon_cpp else (
                m.group(1) if m else "unknown")
            c.anon_hash = m.group(2) if m else ""
    stems = collections.defaultdict(set)
    for c in classes:
        if c.anon:
            stems[c.anon_stem].add(c.anon_hash)
    for c in classes:
        if c.anon and len(stems[c.anon_stem]) > 1:
            c.anon_stem += "_" + c.anon_hash

    # scopes: class prefixes become nesting, others namespaces
    def scope_key(c, parts):
        return (c.anon_stem if c.anon else "", "::".join(parts))
    by_scope = {scope_key(c, c.parts): c for c in classes}
    for c in classes:
        # the longest prefix that is itself an RTTI class makes c a nested class
        outer = None
        for k in range(len(c.parts) - 1, 0, -1):
            o = by_scope.get(scope_key(c, c.parts[:k]))
            if o is not None:
                outer = o
                break
        if outer:
            c.outer = outer
            outer.nested.append(c)
        else:
            c.ns = c.parts[:-1]
    for c in classes:
        if c.outer:
            o = c.outer
            chain = [c.parts[-1]]
            while o.outer:
                chain.append(o.parts[-1])
                o = o.outer
            c.ns = o.ns
            chain.append(o.parts[-1])
            c.local = "::".join(reversed(chain))
        else:
            c.local = c.parts[-1]
        m = re.match(r"^([A-Za-z_]\w*)<(.*)>$", c.parts[-1])
        if m:
            c.template = (m.group(1), split_targs(m.group(2)))

    # dynamic-ness
    def is_dyn(c, seen=()):
        if c.vt or c.vptr_inferred:
            return True
        return any(is_dyn(b, seen + (c.ti,)) for b, *_ in c.bases if b.ti not in seen)
    for c in classes:
        if c.kind == "vmi" and c.bases and min(o for _b, o, *_ in c.bases) > 0:
            c.vptr_inferred = True
            c.vptr_why = "no base at offset 0 in the typeinfo"
    # a secondary vtable at offset o means the base at o is dynamic; its slot count is at
    # least the highest non-zero slot seen in any such secondary vtable (vfuncs.csv)
    sec_max = collections.defaultdict(int)
    for r in vf:
        sec_max[int(r["vtable_addr"], 16)] = max(sec_max[int(r["vtable_addr"], 16)], int(r["slot"]) + 1)
    for c in classes:
        for a, o in c.secondary:
            grp = [b for b, off, virt, *_ in c.bases if off == o and not virt]
            if len(grp) == 1 and not grp[0].vt:
                b = grp[0]
                b.sec_slots = max(getattr(b, "sec_slots", 1), sec_max.get(a, 0))
                if not b.bases:
                    b.vptr_inferred = True
                    b.vptr_why = "secondary vtable at +%d in %s" % (o, c.name)
    for c in classes:
        c.dynamic = is_dyn(c)

    def primary_base(c):
        for b, off, virt, pub, _ in c.bases:
            if not virt and b.dynamic:
                return b, off
        return None, None

    for c in classes:
        pb, off = primary_base(c)
        if pb is not None and off != 0:
            report.append("WARN primary base %s of %s at offset %d (GCC puts it at 0)" % (
                pb.name, c.name, off))

    def is_base_of(b, c, depth=0):
        """b is c or a base of c at offset 0 (any depth)."""
        if b is c:
            return True
        if depth > 40:
            return False
        return any(off == 0 and is_base_of(b, bb, depth + 1) for bb, off, *_ in c.bases)

    # slots
    for c in classes:
        if c.vt:
            c.slots = [u32(c.vt + 8 + 4 * i) for i in range(c.num_slots)]

    order = topo(classes, lambda c: [b for b, *_ in c.bases])
    for c in order:
        pb, _ = primary_base(c)
        if c.vt:
            c.eff = list(c.slots)
        elif pb is not None:
            c.eff = list(pb.eff)
        elif c.dynamic:
            # vptr needed: placeholder slots (count is a lower bound, unverifiable)
            c.eff = [None] * getattr(c, "sec_slots", 1)
        else:
            c.eff = []
        if c.dynamic and not c.eff and (pb is None):
            c.eff = [None]

    # root families + secondary usage
    def root_of(c):
        pb, _ = primary_base(c)
        while pb is not None:
            c = pb
            pb, _ = primary_base(c)
        return c
    sec_roots = set()
    for c in classes:
        pb, _ = primary_base(c)
        for b, off, virt, pub, _ in c.bases:
            if b is not pb and b.dynamic:
                sec_roots.add(root_of(b).ti)
    by_name = collections.Counter(c.name for c in classes)

    def slot_name(c, i):
        r = root_of(c)
        if r.ti in sec_roots:
            return "vf%02d_%s" % (i, ident(r.parts[-1] if not r.anon else r.local))
        return "vf%02d" % i

    # destructor slot pairs from ctors.csv
    dtor_fn = {}
    for r in ctors:
        if r["kind"] in ("dtor", "deleting_dtor") and r["confidence"] in ("high", "medium"):
            dtor_fn[int(r["func_addr"], 16)] = r["kind"]

    def introducer(c, k):
        x = c
        while True:
            pb, _ = primary_base(x)
            if pb is None or len(pb.eff) <= k:
                return x
            x = pb
    dtor_conf = []
    for c in classes:
        for s, f in enumerate(c.slots):
            kd = dtor_fn.get(f)
            if not kd:
                continue
            k = s if kd == "dtor" else s - 1
            if k < 0:
                continue
            x = introducer(c, k)
            pbx, _ = primary_base(x)
            nb = len(pbx.eff) if pbx else 0
            if not (k >= nb and k + 1 < len(x.eff)):
                dtor_conf.append("dtor evidence %s slot %d of %s: pair does not start in one class" % (
                    h(f), s, c.name))
                continue
            if x.dtor_k is not None and x.dtor_k != k:
                dtor_conf.append("conflicting dtor pairs in %s: %d vs %d" % (x.name, x.dtor_k, k))
                continue
            x.dtor_k = k

    def dtor_pair(c):
        x = c
        while x is not None:
            if x.dtor_k is not None:
                return x.dtor_k
            x, _ = primary_base(x)
        return None

    # sizes: operator new
    print("scanning operator new call sites ...", file=sys.stderr)
    sc = SizeScanner(classes, by_ti, ctors, funcs)
    sc.scan()
    votes, site_log, site_stats = sc.decide(is_base_of)
    size_conflicts = []
    c_stats = {}
    for ti, vs in sorted(votes.items()):
        c = by_ti[ti]
        sizes = sorted({v[0] for v in vs})
        if len(sizes) == 1:
            c.size_new = sizes[0]
            c.size_new_ev = sorted(vs, key=lambda v: v[1])
        else:
            size_conflicts.append("%s: operator new sizes disagree: %s" % (
                c.name, ", ".join("0x%X@%s" % (v[0], h(v[1])) for v in sorted(vs, key=lambda v: v[1]))))
    # Independent checks of operator-new sizes, before layout; a failing class loses its
    # size (reported as a conflict). (1) constructors store only inside the object.
    # (2) every function in a class's primary vtable is called with an object of that
    # class (or of a derived class, for inherited slots), so its this-relative loads and
    # stores stay inside sizeof(class).
    for f in sorted(sc.ctor_csv):
        sc.ctor_class(f)
    ctor_checked = 0
    for f, cc in sorted(sc._inf.items(), key=lambda kv: kv[0]):
        if cc is None or cc.size_new is None:
            continue
        ctor_checked += 1
        mx = sc.ctor_max.get(f, 0)
        if mx > cc.size_new:
            size_conflicts.append("%s: constructor %s stores up to 0x%X > operator new size 0x%X" % (
                cc.name, h(f), mx, cc.size_new))
            cc.size_conflict = "constructor stores beyond size"
    report.append("constructors checked against operator-new sizes (stores inside object): %d" % ctor_checked)
    vf_checked = vf_pairs = 0
    slack = []
    for c in classes:
        if c.size_new is None or not c.slots:
            continue
        vf_checked += 1
        mx = 0
        for f in sorted(set(c.slots)):
            if not f or f in pure:
                continue
            vf_pairs += 1
            acc = sc.this_access(f)
            mx = max(mx, acc)
            if acc > c.size_new:
                size_conflicts.append("%s: vtable function %s accesses this+0x%X > operator new size 0x%X" % (
                    c.name, h(f), acc, c.size_new))
                c.size_conflict = "vtable function accesses beyond size"
        slack.append(c.size_new - mx)
    for c in classes:
        if c.size_conflict:
            c.size_new = None
    c_stats["vf_checked"], c_stats["vf_pairs"] = vf_checked, vf_pairs
    c_stats["slack"] = sorted(slack)
    report.append("classes with an operator-new size whose vtable functions were checked: %d "
                  "(%d function/class pairs)" % (vf_checked, vf_pairs))
    if slack:
        slack.sort()
        report.append("size minus highest vtable-function access: min %d, median %d, max %d bytes; "
                      "reached exactly (slack < 4) in %d classes" % (
                          slack[0], slack[len(slack) // 2], slack[-1], sum(1 for x in slack if x < 4)))

    # sizes: gaps in vmi base offsets. A base at o1 followed (in offset order) by another
    # at o2 bounds the first base's data size (dsize): dsize <= o2 - o1. sizeof may be
    # larger (tail padding reused by a less-aligned next base, e.g. ProcInst 42/44).
    # Bases sharing an offset: at most one is non-empty (a dynamic one if any); the
    # others are empty classes. If none of the group is dynamic the owner is ambiguous.
    gaps = collections.defaultdict(list)
    for c in classes:
        groups = collections.OrderedDict()
        for b, off, virt, pub, _ in c.bases:
            if not virt:
                groups.setdefault(off, []).append(b)
        offs = sorted(groups)
        for o1, o2 in zip(offs, offs[1:]):
            grp = groups[o1]
            owner = grp[0] if len(grp) == 1 else None
            if owner is None:
                dyn = [b for b in grp if b.dynamic]
                if len(dyn) == 1:
                    owner = dyn[0]
            if owner is None:
                report.append("ambiguous base-offset gap in %s at %d: %s" % (
                    c.name, o1, ", ".join(b.name for b in grp)))
                continue
            gaps[owner.ti].append((o2 - o1, c))
    for ti, gl in gaps.items():
        c = by_ti[ti]
        c.size_gap = min(g for g, _ in gl)
        c.size_gap_ev = sorted({"%s(%d)" % (d.name, g) for g, d in gl})

    # nonzero-offset requirement for non-dynamic bases
    need_nonempty = set()
    for c in classes:
        for b, off, *_ in c.bases:
            if off > 0:
                need_nonempty.add(b.ti)

    def rup(v, a):
        return v + (-v) % a

    # layout: per class dsize (data end, what a following base or field sees) and sizeof
    for c in order:
        end = 0
        align = 1
        pb, _ = primary_base(c)
        if c.dynamic and pb is None:
            end = 4
            align = 4
        for b, off, virt, pub, _ in c.bases:
            if b.dsize:
                end = max(end, off + b.dsize)
            align = max(align, b.align)
        c.align = align
        c.base_end = end
        S = D = None
        if c.size_new is not None:
            S = c.size_new
            D = S if c.size_gap is None else min(S, c.size_gap)
            c.target_src = "new" if c.size_gap is None else "new+base_offset"
            if rup(D, align) != S:
                size_conflicts.append("%s: operator new size 0x%X vs base-offset dsize bound 0x%X" % (
                    c.name, S, c.size_gap))
                c.size_conflict = "new/base-offset disagree"
                S = D = None
        elif c.size_gap is not None:
            D = c.size_gap
            S = rup(D, align)
            c.target_src = "base_offset"
        if D is not None and D < end:
            size_conflicts.append("%s: size 0x%X (dsize 0x%X) below minimal layout 0x%X" % (
                c.name, S, D, end))
            c.size_conflict = "below minimal layout"
            S = D = None
        if S is not None:
            c.target = S
            c.pad = D - end
            c.emitted = S
            c.dsize = D
        else:
            c.target_src = ""
            if end == 0 and c.ti in need_nonempty:
                c.placeholder = True
                c.pad = 1
                end = 1
            c.dsize = end
            c.emitted = rup(end, align) if end else 1

    # validation: derived >= base, offsets inside the object, constructor stores inside
    for c in classes:
        for b, off, *_ in c.bases:
            if c.target is not None and b.target is not None and off + b.dsize > c.target:
                size_conflicts.append("CHECK %s (0x%X) smaller than base %s at %d (dsize 0x%X)" % (
                    c.name, c.target, b.name, off, b.dsize))
        for _a, o in c.secondary:
            if c.target is not None and o + 4 > c.target:
                size_conflicts.append("CHECK %s: secondary vptr at %d outside size 0x%X" % (
                    c.name, o, c.target))
    # declared slots and member text
    for c in classes:
        c.decl_slots = len(c.eff)
        c.ctor_funcs = sorted(f for f, cc in sc._inf.items() if cc is c)
        c.member_funcs = []
    for r in members:
        if r["confidence"] in ("high", "medium"):
            c = by_ti.get(int(r["typeinfo_addr"], 16))
            if c is not None:
                c.member_funcs.append(int(r["func_addr"], 16))
    for c in classes:
        c.member_funcs.sort()

    model = dict(classes=classes, by_ti=by_ti, order=order, skipped=skipped,
                 funcname=funcname, pure=pure, primary_base=primary_base, slot_name=slot_name,
                 dtor_pair=dtor_pair, report=report, size_conflicts=size_conflicts,
                 site_log=site_log, site_stats=site_stats, dtor_conf=dtor_conf,
                 ctor_disagree=sc.disagree, c_stats=c_stats,
                 members=members, sec_roots=sec_roots, by_name=by_name)
    return model


def topo(items, deps):
    """Deterministic topological order (stable by typeinfo address)."""
    items = sorted(items, key=lambda c: c.ti)
    idx = {c.ti: c for c in items}
    state = {}
    out = []

    def visit(c, stack):
        s = state.get(c.ti)
        if s == 2:
            return
        if s == 1:
            raise SystemExit("dependency cycle: " + " -> ".join(x.name for x in stack + [c]))
        state[c.ti] = 1
        for d in sorted(deps(c), key=lambda x: x.ti):
            if d.ti in idx:
                visit(d, stack + [c])
        state[c.ti] = 2
        out.append(c)
    for c in items:
        visit(c, [])
    return out


def class_deps(c):
    d = [b for b, *_ in c.bases]
    if c.outer:
        d.append(c.outer)
    return d


def qual(c):
    """Spelling of c usable from inside another class's namespace scope."""
    if c.anon:
        return c.local  # only referenced from within the same anonymous namespace
    return "::" + "::".join(c.ns + [c.local])


def assign_headers(m):
    classes = m["classes"]
    pb = m["primary_base"]

    def top(c):
        while c.outer:
            c = c.outer
        return c

    def chain_root(c):
        x = c
        while True:
            nxt = None
            for b, off, virt, *_ in x.bases:
                if off == 0 and not virt and not b.ns and not b.outer and not b.anon:
                    nxt = b
                    break
            if nxt is None:
                return x
            x = nxt
    fam = collections.defaultdict(list)
    for c in classes:
        t = top(c)
        if t.anon:
            c.header = "anon/%s.h" % t.anon_stem
        elif t.ns:
            c.header = "ns_%s.h" % ident(t.ns[0])
        else:
            r = chain_root(t)
            fam[r.ti].append(c)
            c.header = None
            c._root = r
    for rti, cl in fam.items():
        tops = [c for c in cl if not c.outer]
        if len(tops) >= 2:
            name = "cls_%s.h" % ident(cl[0]._root.parts[-1])
        elif not tops[0].bases:
            name = "mixins.h"  # stand-alone global classes without bases (mostly mixin bases)
        else:
            name = "misc.h"
        for c in cl:
            c.header = name
    # merge header SCCs (non-anon)
    while True:
        g = collections.defaultdict(set)
        for c in classes:
            for d in class_deps(c) + targ_deps(c, m):
                if d.header != c.header:
                    g[c.header].add(d.header)
        sccs = tarjan(sorted({c.header for c in classes}), g)
        merged = False
        for comp in sccs:
            if len(comp) > 1:
                comp = sorted(comp)
                tgt = comp[0]
                m["report"].append("merged headers (include cycle): %s -> %s" % (", ".join(comp), tgt))
                for c in classes:
                    if c.header in comp:
                        c.header = tgt
                merged = True
        if not merged:
            return g


def targ_deps(c, m):
    """Template arguments that are nested classes need their enclosing class defined."""
    out = []
    if c.template:
        for a in c.template[1]:
            for x in m["classes"]:
                if not x.anon and "::".join(x.ns + [x.local]) == a and x.outer:
                    out.append(x.outer)
    return out


def tarjan(nodes, g):
    index, low, on, st, out = {}, {}, set(), [], []
    counter = [0]

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        st.append(v)
        on.add(v)
        for w in sorted(g.get(v, ())):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = st.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            out.append(comp)
    sys.setrecursionlimit(10000)
    for v in nodes:
        if v not in index:
            strong(v)
    return out


def emit_class(c, m):
    """Return lines for the class definition (relative to its namespace scope)."""
    pbase, _ = m["primary_base"](c)
    slot_name = m["slot_name"]
    fn = m["funcname"]
    pure = m["pure"]
    L = []

    def fdesc(v):
        if v is None:
            return "unknown"
        if v == 0:
            return "0 (eliminated)"
        n = fn.get(v)
        s = h(v)
        if v in pure:
            s += " pure"
        if n and not n.startswith("func_"):
            s += " " + n
        return s

    # header comment
    src = []
    if c.target is not None:
        src.append("size 0x%X (%s)" % (c.target, c.target_src))
    elif c.size_conflict:
        src.append("size unknown (%s)" % c.size_conflict)
    else:
        src.append("size unknown")
    L.append("// %s  typeinfo %s%s" % (c.name, h(c.ti), ("  vtable " + h(c.vt)) if c.vt else ""))
    L.append("// %s; primary vtable slots: %s" % (
        "; ".join(src), str(c.num_slots) if c.vt else ("none found" if c.dynamic else "n/a")))
    if c.size_new_ev:
        ev = ", ".join("%s(%s)" % (h(a), k) for _s, a, k in c.size_new_ev[:6])
        more = len(c.size_new_ev) - 6
        L.append("// operator new sites: %s%s" % (ev, (" +%d more" % more) if more > 0 else ""))
    if c.size_gap_ev:
        L.append("// size from base offsets in: %s" % ", ".join(c.size_gap_ev[:6]))
    if c.ctor_funcs:
        L.append("// constructors: %s" % ", ".join(h(f) for f in c.ctor_funcs[:8]) + (
            " +%d more" % (len(c.ctor_funcs) - 8) if len(c.ctor_funcs) > 8 else ""))
    if c.member_funcs:
        L.append("// other members (class_members.csv, high/medium): %d: %s" % (
            len(c.member_funcs), ", ".join(h(f) for f in c.member_funcs[:8]) + (
                " ..." if len(c.member_funcs) > 8 else "")))
    def subobj(x, o, path):
        """Outermost dynamic base subobject starting at offset o (o > 0) and its path."""
        for bb, off, virt, *_ in x.bases:
            if off == o and bb.dynamic:
                return bb, path
        for bb, off, virt, *_ in x.bases:
            if 0 <= off < o:
                r = subobj(bb, o - off, path + [bb])
                if r[0] is not None:
                    return r
        return None, path
    for a, o in c.secondary:
        b, path = subobj(c, o, [])
        via = (" via " + " -> ".join(p.name for p in path)) if path else ""
        L.append("// secondary vtable at +%d (%s%s): %s" % (o, b.name if b else "?", via, h(a)))
    # declaration
    bl = []
    for b, off, virt, pub, _ in c.bases:
        s = ("public " if pub else "private ") + ("virtual " if virt else "") + qual(b)
        bl.append(s)
    if c.template:
        head = "template <> class %s" % c.local
    else:
        head = "class %s" % c.local
    if bl:
        offs = ", ".join("%s@%d" % (b.local if b.anon else b.name, off) for b, off, *_ in c.bases)
        L.append("%s" % head)
        L.append("    : " + ", ".join(bl) + "  // " + offs)
        L.append("{")
    else:
        L.append(head + " {")
    L.append("public:")
    for n in sorted(c.nested, key=lambda x: x.ti):
        L.append("    class %s;" % n.parts[-1])
    base_eff = pbase.eff if pbase is not None else []
    k = m["dtor_pair"](c)
    i = 0
    inh = []

    def flush():
        if inh:
            a, b = inh[0], inh[-1]
            rng = ("[%02d]" % a) if a == b else ("[%02d-%02d]" % (a, b))
            L.append("    // %s inherited from %s" % (rng, pbase.name if pbase else "?"))
            del inh[:]
    if c.vptr_inferred and not c.vt:
        L.append("    // vptr inferred: %s; %d placeholder slot(s), a lower bound" % (
            c.vptr_why, len(c.eff)))
    while i < len(c.eff):
        v = c.eff[i]
        inherited = i < len(base_eff)
        if k is not None and i == k and k + 1 < len(c.eff):
            v2 = c.eff[k + 1]
            if inherited and k + 1 < len(base_eff) and base_eff[k] == v and base_eff[k + 1] == v2:
                inh.extend([k, k + 1])
            else:
                flush()
                tag = "override" if inherited else "new"
                L.append("    virtual ~%s();  // [%02d] %s, [%02d] deleting %s (%s)" % (
                    re.sub(r"<.*", "", c.parts[-1]), k, fdesc(v), k + 1, fdesc(v2), tag))
            i += 2
            continue
        if inherited and base_eff[i] == v:
            inh.append(i)
        else:
            flush()
            tag = "override" if inherited else "new"
            if not c.vt:
                tag += ", slot count unverifiable"
            if inherited:
                tag += " of %s" % fdesc(base_eff[i])
            pv = " = 0" if v in pure else ""
            L.append("    virtual void %s()%s;  // [%02d] %s (%s)" % (slot_name(c, i), pv, i, fdesc(v), tag))
        i += 1
    flush()
    if c.pad:
        if c.placeholder:
            L.append("    u8 _unk[1];  // placeholder: real size unknown; non-empty because it sits at a non-zero base offset")
        elif c.dsize != c.target:
            L.append("    u8 _unk[0x%X];  // offset 0x%X..0x%X: unknown fields (dsize 0x%X from a base offset; sizeof 0x%X)" % (
                c.pad, c.base_end, c.dsize, c.dsize, c.target))
        else:
            L.append("    u8 _unk[0x%X];  // offset 0x%X..0x%X: unknown fields" % (c.pad, c.base_end, c.target))
    L.append("};")
    if c.target is not None:
        L.append('static_assert(sizeof(%s) == 0x%X, "%s: size (%s)");' % (
            c.local, c.target, c.name.replace('"', ""), c.target_src))
    return L


HDR_NOTE = """// GENERATED by tools/gen_headers.py from RTTI in the user's code.bin -- do not edit.
// Regenerate: python tools/gen_headers.py gen
// Names come only from RTTI typeinfo names; layouts are placeholders (see README.md)."""


def guard(name):
    return "AW_GENERATED_" + ident(name).upper()


def ns_open(ns):
    out = []
    for n in ns:
        out.append("namespace {" if n == ANON else "namespace %s {" % n)
    return out


def ns_close(ns):
    return ["}" + ("  // anonymous namespace" if n == ANON else "  // namespace %s" % n) for n in reversed(ns)]


def write(path, text, written):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.replace("\r\n", "\n").encode("utf-8")
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)
    written.add(path.resolve())


def generate():
    m = build_model()
    classes = m["classes"]
    g = assign_headers(m)
    written = set()

    # fwd.h
    fwd = [HDR_NOTE, "#ifndef AW_GENERATED_FWD_H", "#define AW_GENERATED_FWD_H", ""]
    templates = collections.OrderedDict()
    known_spell = {"::".join(c.ns + [c.local]) for c in classes if not c.anon}
    extra_fwd = set()
    for c in sorted(classes, key=lambda x: x.ti):
        if c.template and not c.anon:
            key = tuple(c.ns + [c.template[0]])
            templates.setdefault(key, []).append(c)
            for a in c.template[1]:
                if re.match(r"^[A-Za-z_][\w:]*$", a) and a not in known_spell and a not in (
                        "int", "float", "double", "char", "bool", "short", "long"):
                    extra_fwd.add(a)
    decls = []
    for c in sorted(classes, key=lambda x: x.ti):
        if c.anon or c.outer or c.template:
            continue
        decls.append((tuple(c.ns), "class %s;" % c.local))
    for key, insts in templates.items():
        n = len(insts[0].template[1])
        for x in insts:
            if len(x.template[1]) != n:
                raise SystemExit("template %s used with different arities" % "::".join(key))
        params = []
        for j in range(n):
            isint = [re.match(r"^-?\d+[uUlL]*$", x.template[1][j]) is not None for x in insts]
            if all(isint):
                params.append("int N%d" % j)
            elif not any(isint):
                params.append("typename T%d" % j)
            else:
                raise SystemExit("template %s mixes type and value arguments" % "::".join(key))
        decls.append((key[:-1], "template <%s> class %s;" % (", ".join(params), key[-1])))
    for a in sorted(extra_fwd):
        p = split_scope(a)
        decls.append((tuple(p[:-1]), "class %s;  // template argument without RTTI" % p[-1]))
    decls.sort(key=lambda d: (d[0], d[1]))
    for ns, grp in itertools_groupby(decls, lambda d: d[0]):
        fwd += ns_open(list(ns))
        fwd += [d[1] for d in grp]
        fwd += ns_close(list(ns))
    fwd += ["", "#endif", ""]
    write(OUT / "fwd.h", "\n".join(fwd), written)

    # headers
    order_all = topo(classes, lambda c: class_deps(c) + targ_deps(c, m))
    pos = {c.ti: i for i, c in enumerate(order_all)}
    by_header = collections.defaultdict(list)
    for c in order_all:
        by_header[c.header].append(c)
    hdr_order = []
    # header order for all.h: topological over g
    seen = set()

    def hv(x):
        if x in seen:
            return
        seen.add(x)
        for d in sorted(g.get(x, ())):
            hv(d)
        hdr_order.append(x)
    for x in sorted(by_header):
        hv(x)
    for hname, cl in sorted(by_header.items()):
        rel_types = "../" * (hname.count("/") + 1) + "types.h"
        rel_up = "../" * hname.count("/")
        lines = [HDR_NOTE, "#ifndef %s" % guard(hname), "#define %s" % guard(hname), "",
                 '#include "%s"' % rel_types, '#include "%sfwd.h"' % rel_up]
        deps = sorted(g.get(hname, ()))
        for d in deps:
            lines.append('#include "%s%s"' % (rel_up, d))
        lines.append("")
        anon = hname.startswith("anon/")
        if anon:
            cpp = cl[0].anon_cpp or cl[0].anon_stem
            lines.append("// Anonymous-namespace classes of %s (one TU only; not in all.h)." % cpp)
            lines.append("")
        cur_ns = None
        for c in cl:
            if c.ns != cur_ns:
                if cur_ns:
                    lines += ns_close(cur_ns)
                    lines.append("")
                lines += ns_open(c.ns)
                cur_ns = c.ns
            lines.append("")
            lines += emit_class(c, m)
        if cur_ns:
            lines += ns_close(cur_ns)
        lines += ["", "#endif", ""]
        write(OUT / hname, "\n".join(lines), written)

    non_anon = [x for x in hdr_order if not x.startswith("anon/")]
    allh = [HDR_NOTE, "#ifndef AW_GENERATED_ALL_H", "#define AW_GENERATED_ALL_H", "",
            '#include "../types.h"', '#include "fwd.h"']
    allh += ['#include "%s"' % x for x in non_anon]
    allh += ["", "// Anonymous-namespace headers (include only from their own .cpp):"]
    allh += ["//   %s" % x for x in sorted(by_header) if x.startswith("anon/")]
    allh += ["", "#endif", ""]
    write(OUT / "all.h", "\n".join(allh), written)

    # check TUs: all.h, then anon headers batched so names do not collide
    chk = [HDR_NOTE, "// Test TU: every non-anonymous generated header.", '#include "../all.h"', ""]
    write(OUT / "check" / "check_all.cpp", "\n".join(chk), written)
    anon_hdrs = sorted(x for x in by_header if x.startswith("anon/"))
    batches = []
    for x in anon_hdrs:
        names = {c.local for c in by_header[x]}
        for b in batches:
            if not (b[1] & names):
                b[0].append(x)
                b[1] |= names
                break
        else:
            batches.append([[x], set(names)])
    for i, (hs, _n) in enumerate(batches):
        t = [HDR_NOTE, "// Test TU: anonymous-namespace headers whose class names do not collide.",
             '#include "../all.h"'] + ['#include "../%s"' % x for x in hs] + [""]
        write(OUT / "check" / ("check_anon_%02d.cpp" % i), "\n".join(t), written)

    # class table
    rows = []
    for c in sorted(classes, key=lambda x: x.ti):
        rows.append([c.name, h(c.ti), h(c.vt) if c.vt else "", c.header,
                     "0x%X" % c.target if c.target is not None else "",
                     c.target_src, "0x%X" % c.size_new if c.size_new is not None else "",
                     len(c.size_new_ev), "0x%X" % c.size_gap if c.size_gap is not None else "",
                     c.size_conflict, c.num_slots if c.vt else "", c.decl_slots,
                     len(c.secondary), "1" if c.dynamic else "0",
                     ";".join("%s@%d" % (h(b.ti), off) for b, off, *_ in c.bases)])
    tp = OUT / "class_table.csv"
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["class", "typeinfo_addr", "vtable_addr", "header", "size", "size_source",
                "size_new", "new_sites", "size_base_offset", "size_conflict", "num_slots",
                "declared_slots", "secondary_vtables", "dynamic", "bases"])
    w.writerows(rows)
    write(tp, buf.getvalue(), written)

    # README
    stats = collections.Counter()
    for c in classes:
        stats["classes"] += 1
        if c.target is not None:
            stats["sized_" + c.target_src] += 1
            stats["sized"] += 1
        if c.vt:
            stats["with_vtable"] += 1
    write(OUT / "README.md", readme(m, stats, sorted(by_header), batches), written)

    # stale generated files
    for p in sorted(OUT.rglob("*")):
        if p.is_file() and p.resolve() not in written:
            p.unlink()
    for p in sorted(OUT.rglob("*"), reverse=True):
        if p.is_dir() and not any(p.iterdir()):
            p.rmdir()

    # diagnostics
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "new_sites.txt").write_text("\n".join(m["site_log"]) + "\n", encoding="utf-8")
    rep = ["gen_headers report", ""]
    rep.append("classes generated: %d (skipped runtime classes: %s)" % (
        len(classes), ", ".join(c.name for c in m["skipped"])))
    rep.append("operator new call sites: %d; verdicts: %s" % (
        len(m["site_log"]), dict(sorted(m["site_stats"].items()))))
    rep.append("proven sizes: %d (new %d, new+base_offset %d, base_offset %d)" % (
        stats["sized"], stats["sized_new"], stats["sized_new+base_offset"], stats["sized_base_offset"]))
    rep.append("classes with a size from operator new (before conflicts): %d" % sum(
        1 for c in classes if c.size_new is not None))
    rep.append("dtor pairs declared: %d" % sum(1 for c in classes if c.dtor_k is not None))
    rep.append("ctors.csv rows overridden by vtable-store inference: %d" % len(m["ctor_disagree"]))
    rep += ["  " + s for s in m["ctor_disagree"]]
    rep.append("")
    rep += ["size conflicts:"] + ["  " + s for s in m["size_conflicts"]] + [""]
    rep += ["dtor evidence problems:"] + ["  " + s for s in m["dtor_conf"]] + [""]
    rep += ["notes:"] + ["  " + s for s in m["report"]] + [""]
    (SCRATCH / "gen_report.txt").write_text("\n".join(rep), encoding="utf-8")
    print("\n".join(rep[:8]))
    print("wrote %d files under %s" % (len(written), OUT))
    return m


def itertools_groupby(seq, key):
    import itertools
    return itertools.groupby(seq, key)


def readme(m, stats, headers, batches):
    return """# include/generated/ -- GENERATED, do not edit

Everything in this directory is written by `tools/gen_headers.py` from RTTI in your own
`extracted/code.bin` plus `config/naming/*.csv`. Hand edits are lost on regeneration.

    python tools/gen_headers.py gen     # regenerate this directory
    python tools/gen_headers.py check   # compile with arm-none-eabi-g++ and cross-check
    python tools/gen_headers.py all     # both

## What the headers contain

- One class per RTTI typeinfo (%(classes)d classes; the C++ runtime's `std::` and
  `__cxxabiv1::` classes are skipped). Names come only from typeinfo names.
- Bases in declaration order with the offsets from the typeinfo (comment after the base
  list). `check` verifies GCC places every base at that offset.
- Virtual functions as placeholders, one per primary vtable slot, in slot order:
  `virtual void vfNN();  // [NN] 0xADDR name (new|override)`. Inherited slots are a
  comment. A slot pair shown by `config/naming/ctors.csv` becomes `virtual ~X();`
  (complete + deleting destructor). Pure-virtual stub slots are `= 0`. Families that are
  also used as a non-primary base name their slots `vfNN_<Root>`.
- Sizes: `u8 _unk[N]` padding and `static_assert(sizeof(X) == SIZE)` only where a size is
  known: %(sized)d classes (%(sized_new)d from `operator new` + constructor/vtable store,
  %(sized_new+base_offset)d from both that and a base offset, %(sized_base_offset)d from base offsets in a
  multiple-inheritance typeinfo only). See `tools/gen_headers.py` docstring for the rules.
  Every operator-new size was also checked against the class's own code: constructors
  store, and the %(vf_checked)d sized classes' vtable functions (%(vf_pairs)d function/class pairs) load
  and store, only inside the object; in %(exact)d classes some vtable function touches the
  last word, i.e. the size is reached exactly. A failing class gets no size.
- Classes without a known size have only their vptr/bases; their fields are not modelled
  (a derived class's `_unk` then also covers base-class fields).
- `class_table.csv`: per class header, size and evidence, slot counts (`num_slots` from
  classes.csv vs `declared_slots` in the header), dynamic flag, bases.

## Files

- `fwd.h` forward declarations; `all.h` includes every non-anonymous header.
- `anon/*.h` anonymous-namespace classes, one header per leaked `.cpp` name. They are not
  in `all.h` because the same class name repeats across `.cpp` files; include each one
  from its own translation unit.
- `check/*.cpp` test translation units used by `gen_headers.py check`: it compiles them
  (`-std=gnu++11 -marm -mcpu=mpcore`, `-fsyntax-only` then `-fdump-lang-class`) and
  compares GCC's layout with the binary: every `static_assert` size, every base offset
  from the typeinfo, primary vtable slot count against `classes.csv` `num_slots`,
  secondary vtable count, and the mangled vtable name against the typeinfo name.
  Report: `build/gen_headers/check_report.txt`.

Headers: %(nh)d.
""" % dict(stats, nh=len(headers), vf_checked=m["c_stats"]["vf_checked"],
           vf_pairs=m["c_stats"]["vf_pairs"],
           exact=sum(1 for x in m["c_stats"]["slack"] if x < 4))


# ----------------------------------------------------------------------------
# Check
# ----------------------------------------------------------------------------
def gxx_path():
    cfg = json.loads(LOCAL_CFG.read_text(encoding="utf-8"))
    d = Path(cfg["binutils_dir"])
    for n in ("arm-none-eabi-g++.exe", "arm-none-eabi-g++"):
        if (d / n).exists():
            return d / n
    raise SystemExit("arm-none-eabi-g++ not found in %s" % d)


def anon_norm(s):
    """Replace anonymous-namespace source names (EDG or GCC style) with a token."""
    out, i = "", 0
    while i < len(s):
        mm = re.match(r"(\d+)_GLOBAL__N_", s[i:])
        if mm and (i == 0 or not s[i - 1].isdigit()):
            n = int(mm.group(1))
            out += "@ANON@"
            i += len(mm.group(1)) + n
            continue
        out += s[i]
        i += 1
    return out


def gcc_name(n):
    return n.replace("{anonymous}", ANON)


def parse_dump(text):
    """-> {class name: dict(size, align, vt_mangled, entries, bases[(name, off)])}"""
    res = {}
    lines = text.splitlines()
    i = 0
    vt = {}
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("Vtable for "):
            name = gcc_name(ln[len("Vtable for "):].strip())
            mm = re.match(r"^(.*)::(_ZTV\S+): (\d+) entries", lines[i + 1])
            ents = []
            j = i + 2
            while j < len(lines) and re.match(r"^\d+\s+", lines[j]):
                ents.append(re.sub(r"^\d+\s+", "", lines[j]).strip())
                j += 1
            vt[name] = (mm.group(2) if mm else "", ents)
            i = j
            continue
        if ln.startswith("Class "):
            name = gcc_name(ln[len("Class "):].strip())
            mm = re.match(r"\s+size=(\d+) align=(\d+)", lines[i + 1])
            d = dict(size=int(mm.group(1)), align=int(mm.group(2)), bases=[])
            j = i + 3
            while j < len(lines) and lines[j].strip():
                bm = re.match(r"^\s*(.+?) \(0x[0-9a-fx]+\) (\d+)", lines[j])
                if bm:
                    d["bases"].append((gcc_name(bm.group(1)), int(bm.group(2))))
                j += 1
            res[name] = d
            i = j
            continue
        i += 1
    for name, (mg, ents) in vt.items():
        res.setdefault(name, dict(size=None, align=None, bases=[]))
        res[name]["vt_mangled"] = mg
        res[name]["entries"] = ents
    return res


def primary_count(ents):
    nsec = 0
    prim = None
    for idx, e in enumerate(ents):
        if idx >= 2 and re.match(r"^\(int \(\*\)\(\.\.\.\)\)-?\d+$", e):
            if prim is None:
                prim = idx - 2
            nsec += 1
    if prim is None:
        prim = len(ents) - 2
    # every secondary vtable starts with offset-to-top then typeinfo
    nsec = sum(1 for idx, e in enumerate(ents) if idx >= 2 and re.match(
        r"^\(int \(\*\)\(\.\.\.\)\)-?\d+$", e) and idx + 1 < len(ents) and "_ZTI" in ents[idx + 1])
    return prim, nsec


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def check():
    gxx = gxx_path()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    tus = sorted((OUT / "check").glob("*.cpp"))
    if not tus:
        raise SystemExit("no check TUs; run gen first")
    log = []
    ok = True
    dumps = {}
    for tu in tus:
        rc, out = run([str(gxx)] + GXX_FLAGS + ["-fsyntax-only", "-Wall", "-Wextra", str(tu)])
        log.append("== %s -fsyntax-only: rc=%d" % (tu.name, rc))
        if out.strip():
            log.append(out.strip())
        if rc:
            ok = False
            continue
        dp = SCRATCH / (tu.stem + ".class")
        if dp.exists():
            dp.unlink()
        rc, out = run([str(gxx)] + GXX_FLAGS + ["-S", "-o", os.devnull,
                                                 "-fdump-lang-class=" + str(dp), str(tu)])
        log.append("== %s -fdump-lang-class: rc=%d" % (tu.name, rc))
        if rc:
            log.append(out.strip())
            ok = False
            continue
        for k, v in parse_dump(dp.read_text(encoding="utf-8", errors="replace")).items():
            dumps.setdefault(tu.stem, {})[k] = v

    rows = read_csv(OUT / "class_table.csv")
    cls_rows = {r["typeinfo_addr"]: r for r in read_csv(NAMING / "classes.csv")}
    res = collections.Counter()
    problems = []
    for r in rows:
        name = r["class"]
        cr = cls_rows[r["typeinfo_addr"]]
        anon = ANON in name
        d = None
        for stem, dd in sorted(dumps.items()):
            if anon and stem == "check_all":
                continue
            if name in dd:
                if anon:
                    # disambiguate by header: the TU that includes this header
                    tu_text = (OUT / "check" / (stem + ".cpp")).read_text(encoding="utf-8")
                    if r["header"] not in tu_text:
                        continue
                d = dd[name]
                break
        if d is None:
            problems.append("missing from GCC dump: %s" % name)
            res["missing"] += 1
            continue
        res["found"] += 1
        # size
        if r["size"]:
            res["size_checked"] += 1
            if d["size"] != int(r["size"], 16):
                problems.append("size %s: gcc %s != %s" % (name, d["size"], r["size"]))
                res["size_bad"] += 1
            else:
                res["size_ok"] += 1
        # bases
        for bspec in filter(None, r["bases"].split(";")):
            bti, off = bspec.split("@")
            bname = cls_rows[bti]["class"]
            res["base_checked"] += 1
            if (bname, int(off)) in d["bases"]:
                res["base_ok"] += 1
            else:
                problems.append("base %s of %s: not at offset %s in GCC layout (%s)" % (
                    bname, name, off, [b for b in d["bases"] if b[0] == bname]))
                res["base_bad"] += 1
        # vtable
        if r["dynamic"] == "1":
            ents = d.get("entries")
            if ents is None:
                problems.append("dynamic class without vtable in GCC dump: %s" % name)
                res["vt_missing"] += 1
                continue
            prim, nsec = primary_count(ents)
            if r["num_slots"]:
                res["slots_checked"] += 1
                if prim == int(r["num_slots"]):
                    res["slots_ok"] += 1
                else:
                    problems.append("slots %s: gcc %d != classes.csv num_slots %s" % (
                        name, prim, r["num_slots"]))
                    res["slots_bad"] += 1
            else:
                res["slots_unverifiable"] += 1
                if prim != int(r["declared_slots"]):
                    problems.append("slots %s: gcc %d != declared %s" % (name, prim, r["declared_slots"]))
                    res["slots_bad"] += 1
            nsec_exp = int(r["secondary_vtables"])
            if r["vtable_addr"]:
                res["secondary_checked"] += 1
                if nsec == nsec_exp:
                    res["secondary_ok"] += 1
                else:
                    problems.append("secondary vtables %s: gcc %d != classes.csv %d" % (name, nsec, nsec_exp))
                    res["secondary_bad"] += 1
            mg = d.get("vt_mangled", "")
            want = "_ZTV" + cr["ts_mangled"]
            res["mangle_checked"] += 1
            if anon_norm(mg) == anon_norm(want):
                res["mangle_ok"] += 1
            else:
                problems.append("mangled vtable name %s: gcc %s != %s" % (name, mg, want))
                res["mangle_bad"] += 1
    bad = sum(v for k, v in res.items() if k.endswith("_bad") or k in ("missing", "vt_missing"))
    if bad:
        ok = False
    rep = ["gen_headers check (%s %s)" % (gxx.name, " ".join(GXX_FLAGS)), ""]
    rep.append("TUs: %d" % len(tus))
    rep += ["%s: %d" % (k, v) for k, v in sorted(res.items())]
    rep += ["", "problems (%d):" % len(problems)] + ["  " + p for p in problems]
    rep += ["", "compiler log:"] + log
    (SCRATCH / "check_report.txt").write_text("\n".join(rep) + "\n", encoding="utf-8")
    print("\n".join(rep[: 4 + len(res)]))
    print("problems: %d (see %s)" % (len(problems), SCRATCH / "check_report.txt"))
    for p in problems[:20]:
        print("  " + p)
    print("RESULT:", "PASS" if ok else "FAIL")
    return ok


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "all"
    if cmd == "gen":
        generate()
    elif cmd == "check":
        sys.exit(0 if check() else 1)
    elif cmd == "all":
        generate()
        sys.exit(0 if check() else 1)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv)
