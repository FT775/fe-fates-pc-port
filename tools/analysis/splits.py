#!/usr/bin/env python3
"""
splits.py - gather evidence about how armlink laid out .text/.rodata in
Fire Emblem: Awakening (CTR-P-AFEE) code.bin, to plan object-file splits.

Standard library only.  Read-only on extracted/code.bin.
Writes:
    extracted/analysis/split_candidates.txt   (human readable report)
    extracted/analysis/split_candidates.json  (machine readable: anchors, atoms, cuts)

Evidence sources
  1. C++ RTTI.  EDG/ARMCC mangles anonymous-namespace types as
     _GLOBAL__N__<len>_<File_cpp>_<hash8>, which leaks the *source file name*.
     typeinfo objects -> vtables -> virtual functions gives text addresses that
     belong to a named .cpp file.  Functions that load those vtables/typeinfos
     through literal pools (ctors/dtors) are attributed too.
  2. Literal pools.  ARMv6K has no MOVW/MOVT, so every absolute address the code
     uses goes through an `LDR Rd,[PC,#imm]` literal.  Mapping function -> rodata
     targets lets us test whether .rodata is in the same object order as .text
     and find "cuts" that no rodata span crosses (necessary condition for an
     object boundary when both sections follow link order).
  3. Padding / NOP / zero runs between functions.
  4. Pointer tables (vtables, init_array-like tables, exidx-like tables).
  5. Assert / log strings and any source-file-name strings.
"""
import sys as _sys  # noqa: E402
if "--awakening-pass" not in _sys.argv:  # Fates: TU boundaries come from the symbol map
    _sys.exit("tools/analysis/splits.py holds Awakening segment constants and conclusions. For Fates, "
              "object boundaries are better read from the shipped symbol map (__sti___<n>_<file>_cpp "
              "names, docs/SYMBOLS.md); this pass has not been ported.")
import array
import bisect
import collections
import json
import os
import re
import statistics
import struct
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CODE = os.path.join(ROOT, "extracted", "code.bin")
OUTDIR = os.path.join(ROOT, "extracted", "analysis")
OUT_TXT = os.path.join(OUTDIR, "split_candidates.txt")
OUT_JSON = os.path.join(OUTDIR, "split_candidates.json")

TEXT_VA, TEXT_SZ, TEXT_OFF = 0x00100000, 0x359B88, 0x000000
RO_VA, RO_SZ, RO_OFF = 0x0045A000, 0x05BA88, 0x35A000
DATA_VA, DATA_SZ, DATA_OFF = 0x004B6000, 0x0314E8, 0x3B6000
BSS_VA = DATA_VA + DATA_SZ
BSS_SZ = 0x3BD24
TEXT_END, RO_END, DATA_END, BSS_END = (TEXT_VA + TEXT_SZ, RO_VA + RO_SZ,
                                       DATA_VA + DATA_SZ, BSS_VA + BSS_SZ)

code = open(CODE, "rb").read()
assert len(code) == 4096000, "unexpected code.bin size"
TW = array.array("I", code[TEXT_OFF:TEXT_OFF + TEXT_SZ])
NTW = len(TW)


def in_text(a): return TEXT_VA <= a < TEXT_END
def in_ro(a): return RO_VA <= a < RO_END
def in_data(a): return DATA_VA <= a < DATA_END
def in_bss(a): return BSS_VA <= a < BSS_END


def sec_of(a):
    if in_text(a): return "text"
    if in_ro(a): return "rodata"
    if in_data(a): return "data"
    if in_bss(a): return "bss"
    return None


def rd(a):
    if in_text(a): return TW[(a - TEXT_VA) >> 2]
    if in_ro(a): return struct.unpack_from("<I", code, RO_OFF + a - RO_VA)[0]
    if in_data(a): return struct.unpack_from("<I", code, DATA_OFF + a - DATA_VA)[0]
    return None


def s32(x): return x - (1 << 32) if x & 0x80000000 else x


def ti(a): return (a - TEXT_VA) >> 2          # text word index
def ta(i): return TEXT_VA + (i << 2)          # text address


log_lines = []


def out(s=""):
    log_lines.append(s)


# ---------------------------------------------------------------------------
# 1. literal pools (two passes so literal words are not decoded as code)
# ---------------------------------------------------------------------------
def scan_literals(skip):
    lits = {}       # literal word address -> list of insn addrs
    for i in range(NTW):
        if i in skip:
            continue
        w = TW[i]
        if w >> 28 == 0xF:
            continue
        a = ta(i)
        if (w & 0x0F7F0000) == 0x051F0000:              # LDR Rd,[PC,#+-imm12]
            off = w & 0xFFF
            t = a + 8 + off if w & 0x00800000 else a + 8 - off
            if in_text(t) and not t & 3:
                lits.setdefault(t, []).append(a)
        elif (w & 0x0F3F0E00) == 0x0D1F0A00:            # VLDR s/d,[PC,#+-imm8*4]
            off = (w & 0xFF) << 2
            t = a + 8 + off if w & 0x00800000 else a + 8 - off
            if in_text(t) and not t & 3:
                lits.setdefault(t, []).append(a)
                if w & 0x100:                           # double: 2 words
                    lits.setdefault(t + 4, []).append(a)
    return lits


lits1 = scan_literals(set())
skip = {ti(t) for t in lits1}
lits = scan_literals(skip)
LIT = {ti(t) for t in lits}
lit_values = {t: rd(t) for t in lits}

# ---------------------------------------------------------------------------
# 2. function starts
# ---------------------------------------------------------------------------
def is_terminator(w):
    if w == 0xE12FFF1E: return True                     # bx lr
    if (w & 0xFFFFFFF0) == 0xE12FFF10: return True      # bx rN
    if (w & 0xFFFF8000) == 0xE8BD8000: return True      # ldmfd sp!,{..,pc}
    if w == 0xE49DF004: return True                     # pop {pc}
    if (w & 0xFF000000) == 0xEA000000: return True      # b (always)
    if (w & 0xFFFFF000) == 0xE59FF000: return True      # ldr pc,=x
    if (w & 0x0FFFF000) == 0x01A0F000 and w >> 28 == 0xE: return True  # mov pc,..
    return False


NOPS = {0xE320F000, 0xE1A00000}
bl_targets = collections.Counter()
b_targets = collections.Counter()
for i in range(NTW):
    if i in LIT:
        continue
    w = TW[i]
    op = w >> 24
    if op in (0xEB, 0xEA) or (op & 0x0F) == 0x0B:
        imm = w & 0xFFFFFF
        if imm & 0x800000: imm -= 0x1000000
        t = ta(i) + 8 + imm * 4
        if in_text(t) and ti(t) not in LIT:
            if (op & 0x0F) == 0x0B: bl_targets[t] += 1
            elif op == 0xEA: b_targets[t] += 1

starts_src = collections.defaultdict(set)
starts_src[TEXT_VA].add("entry")
for t in bl_targets: starts_src[t].add("bl")
for t, v in lit_values.items():
    if in_text(v) and not v & 3 and ti(v) not in LIT:
        starts_src[v].add("litptr")
# prologue after terminator / literal pool
for i in range(1, NTW):
    w = TW[i]
    if (w & 0xFFFF4000) == 0xE92D4000 or (w & 0xFFFF0000) == 0xE92D0000:
        j = i - 1
        while j > 0 and TW[j] in NOPS and j not in LIT:
            j -= 1
        if j in LIT or is_terminator(TW[j]) or TW[j] == 0:
            if i not in LIT:
                starts_src[ta(i)].add("prologue")

# data-side pointers (vtables and tables) are added after RTTI pass below.

# ---------------------------------------------------------------------------
# 3. strings in rodata/data
# ---------------------------------------------------------------------------
strings = {}
for va, sz, off in ((RO_VA, RO_SZ, RO_OFF), (DATA_VA, DATA_SZ, DATA_OFF)):
    blob = code[off:off + sz]
    for m in re.finditer(rb"[\x20-\x7e\t\n\r]{4,}\x00", blob):
        strings[va + m.start()] = m.group()[:-1].decode("latin-1")
string_addrs = sorted(strings)

# ---------------------------------------------------------------------------
# 4. RTTI: type names, typeinfo objects, vtables
# ---------------------------------------------------------------------------
MANGLED = re.compile(r"^(?:N|St|Z)?\d+[A-Za-z_].*|^N\d+.*E$")
name_addr = {a: s for a, s in strings.items() if in_ro(a) or in_data(a)}
name_set = set(name_addr)


def ro_data_words():
    for va, sz, off in ((RO_VA, RO_SZ, RO_OFF), (DATA_VA, DATA_SZ, DATA_OFF)):
        for k in range(0, sz - 3, 4):
            yield va + k, struct.unpack_from("<I", code, off + k)[0]


RODATA_WORDS = list(ro_data_words())
WORD_AT = dict(RODATA_WORDS)

cand_ti = {}
for a, w in RODATA_WORDS:
    if w in name_set and MANGLED.match(name_addr[w]):
        cand_ti[a - 4] = w
vptr_count = collections.Counter(WORD_AT.get(t) for t in cand_ti)
TI_VPTRS = {v for v, n in vptr_count.items() if v is not None and n >= 3 and (in_ro(v) or in_data(v))}
typeinfo = {t: name_addr[n] for t, n in cand_ti.items() if WORD_AT.get(t) in TI_VPTRS}

ANON = re.compile(r"_GLOBAL__N__(\d+)_")


def anon_file(name):
    m = ANON.search(name)
    if not m:
        return None
    L = int(m.group(1))
    f = name[m.end():m.end() + L]
    # File_cpp -> File.cpp
    for ext in ("_cpp", "_c", "_cc", "_cxx"):
        if f.endswith(ext):
            return f[: -len(ext)] + "." + ext[1:]
    return f


ti_file = {t: anon_file(n) for t, n in typeinfo.items()}

vtables = {}   # address-of-typeinfo-slot -> dict
for a, w in RODATA_WORDS:
    if w in typeinfo:
        ott = WORD_AT.get(a - 4)
        first = WORD_AT.get(a + 4)
        if ott is None or first is None:
            continue
        if not (-0x10000 <= s32(ott) <= 0):
            continue
        if not in_text(first):
            continue
        funcs = []
        k = a + 4
        while True:
            v = WORD_AT.get(k)
            if v is None or not in_text(v) or k in typeinfo or (k + 4) in typeinfo and False:
                break
            # stop if next slot is a new vtable's offset-to-top+typeinfo pair
            if WORD_AT.get(k + 4) in typeinfo and -0x10000 <= s32(v) <= 0:
                break
            funcs.append(v)
            k += 4
        vtables[a] = dict(ti=w, ott=s32(ott), start=a - 4, end=k, funcs=funcs,
                          file=ti_file[w], name=typeinfo[w])

for vt in vtables.values():
    for f in vt["funcs"]:
        if not f & 1:
            starts_src[f].add("vtable")

starts = sorted(a for a in starts_src if in_text(a) and ti(a) not in LIT)
starts_idx = {a: k for k, a in enumerate(starts)}


def func_of(a):
    k = bisect.bisect_right(starts, a) - 1
    return starts[k] if k >= 0 else None


# literal refs per function
func_refs = collections.defaultdict(list)      # func -> [(target, insn)]
target_funcs = collections.defaultdict(set)    # target -> funcs
for lt, users in lits.items():
    v = lit_values[lt]
    for u in users:
        f = func_of(u)
        func_refs[f].append(v)
        target_funcs[v].add(f)

# ---------------------------------------------------------------------------
# 5. padding / gap statistics
# ---------------------------------------------------------------------------
def runs_of(val):
    res = []
    i = 0
    while i < NTW:
        if TW[i] == val and i not in LIT:
            j = i
            while j < NTW and TW[j] == val and j not in LIT:
                j += 1
            res.append((ta(i), j - i))
            i = j
        else:
            i += 1
    return res


pad_stats = {}
for name, val in (("zero", 0), ("nop_hint", 0xE320F000), ("mov_r0_r0", 0xE1A00000)):
    rs = runs_of(val)
    before_start = sum(1 for a, n in rs if (a + 4 * n) in starts_idx)
    hist = collections.Counter(n for a, n in rs)
    pad_stats[name] = dict(runs=len(rs), words=sum(n for a, n in rs),
                           runs_followed_by_func_start=before_start,
                           len_hist=sorted(hist.items())[:10])

align_hist = collections.Counter()
for a in starts:
    for al in (32, 16, 8):
        if a % al == 0:
            align_hist[al] += 1
            break
    else:
        align_hist[4] += 1

# ---------------------------------------------------------------------------
# 6. init_array / exidx style tables
# ---------------------------------------------------------------------------
start_set = set(starts)
table_runs = []
for mode in ("abs", "rel"):
    run = []
    prev_a = None
    for a, w in RODATA_WORDS:
        t = w if mode == "abs" else (a + w) & 0xFFFFFFFF
        ok = t in start_set
        if ok and (prev_a is None or a == prev_a + 4) and run:
            run.append((a, t))
        elif ok:
            if len(run) >= 4: table_runs.append((mode, run))
            run = [(a, t)]
        else:
            if len(run) >= 4: table_runs.append((mode, run))
            run = []
        prev_a = a
    if len(run) >= 4: table_runs.append((mode, run))


def classify_table(run):
    targets = [t for a, t in run]
    distinct = len(set(targets))
    inc = sum(1 for x, y in zip(targets, targets[1:]) if y > x)
    return distinct, inc


tables = []
for mode, run in table_runs:
    a0 = run[0][0]
    if a0 in vtables or (a0 - 4) in vtables:
        pass
    in_vt = any(vt["start"] <= a0 < vt["end"] for vt in vtables.values())
    distinct, inc = classify_table(run)
    tables.append(dict(mode=mode, addr=a0, n=len(run), distinct=distinct,
                       increasing=inc, inside_vtable=in_vt,
                       targets=[t for _, t in run]))
tables.sort(key=lambda d: -d["n"])

# Look for crt-style table walkers: functions with two literals A<B into ro/data
# where [A,B) is entirely pointers (abs or rel) to function starts.
init_candidates = []
for f, refs in func_refs.items():
    rr = sorted({r for r in refs if (in_ro(r) or in_data(r)) and not r & 3})
    for x in range(len(rr)):
        for y in range(x + 1, min(x + 4, len(rr))):
            A, B = rr[x], rr[y]
            n = (B - A) // 4
            if n < 2 or n > 4000:
                continue
            for mode in ("abs", "rel"):
                good = 0
                for k in range(n):
                    w = WORD_AT.get(A + 4 * k)
                    if w is None: break
                    t = w if mode == "abs" else (A + 4 * k + w) & 0xFFFFFFFF
                    if t in start_set: good += 1
                    else: break
                if good == n:
                    init_candidates.append(dict(walker=f, base=A, limit=B, n=n, mode=mode))
init_candidates.sort(key=lambda d: -d["n"])

# ---------------------------------------------------------------------------
# 7. anonymous-namespace file anchors
# ---------------------------------------------------------------------------
files = collections.defaultdict(lambda: dict(ro=set(), text=set(), text_src=collections.Counter(),
                                             classes=set()))
for t, n in typeinfo.items():
    f = ti_file[t]
    if f:
        files[f]["ro"].update((t, cand_ti[t]))
        files[f]["classes"].add(n)

# vfunc ownership
vfunc_owners = collections.defaultdict(set)
for vt in vtables.values():
    for fn in vt["funcs"]:
        vfunc_owners[fn].add(vt["file"])          # None for global classes
for vt in vtables.values():
    if vt["file"]:
        files[vt["file"]]["ro"].add(vt["start"])
        files[vt["file"]]["ro"].add(vt["end"] - 4)
        for fn in vt["funcs"]:
            if vfunc_owners[fn] == {vt["file"]}:
                files[vt["file"]]["text"].add(fn)
                files[vt["file"]]["text_src"]["vfunc"] += 1

# functions that load an anon vtable / typeinfo via literal pool
vt_addrpoint = {}
for vt in vtables.values():
    if vt["file"]:
        vt_addrpoint[vt["start"] + 8] = vt["file"]
        vt_addrpoint[vt["start"] + 4] = vt["file"]
ti_by_file = {t: f for t, f in ti_file.items() if f}
for f, refs in func_refs.items():
    for r in refs:
        fl = vt_addrpoint.get(r) or ti_by_file.get(r)
        if fl:
            files[fl]["text"].add(f)
            files[fl]["text_src"]["vt/ti-load"] += 1

anchor_rows = []
for f, d in files.items():
    if not d["text"]:
        anchor_rows.append(dict(file=f, ro_min=min(d["ro"]), ro_max=max(d["ro"]), text=[], n_text=0,
                                n_classes=len(d["classes"])))
        continue
    tx = sorted(d["text"])
    anchor_rows.append(dict(file=f, ro_min=min(d["ro"]), ro_max=max(d["ro"]),
                            text=tx, t_min=tx[0], t_max=tx[-1], t_med=statistics.median(tx),
                            n_text=len(tx), n_classes=len(d["classes"]),
                            src=dict(d["text_src"])))
anchored = [r for r in anchor_rows if r["n_text"]]
anchored.sort(key=lambda r: r["t_med"])

# ordering consistency between text order and rodata order (Kendall-like)
pairs = conc = 0
for i in range(len(anchored)):
    for j in range(i + 1, len(anchored)):
        pairs += 1
        if (anchored[j]["ro_min"] > anchored[i]["ro_min"]):
            conc += 1
kendall_frac = conc / pairs if pairs else float("nan")

# text range overlaps among anchored files
overlaps = 0
for x, y in zip(anchored, anchored[1:]):
    if y["t_min"] <= x["t_max"]:
        overlaps += 1

# ---------------------------------------------------------------------------
# 8. rodata monotonicity + zero-violation cut analysis
# ---------------------------------------------------------------------------
# global COMDAT-ish RTTI region: rodata area where global typeinfo names are sorted
# alphabetically (not object order).  Detect: longest stretch of global (non-anon)
# typeinfos/vtables -> treat targets inside it as "shared".
global_ro = sorted([t for t, f in ti_file.items() if not f and in_ro(t)] +
                   [vt["start"] for vt in vtables.values() if not vt["file"]])
# cluster
clusters = []
for a in global_ro:
    if clusters and a - clusters[-1][1] < 0x400:
        clusters[-1][1] = a
        clusters[-1][2] += 1
    else:
        clusters.append([a, a, 1])
clusters.sort(key=lambda c: -c[2])
COMDAT_RO = (clusters[0][0], clusters[0][1] + 0x2000) if clusters else (0, 0)
# extend through sorted global name block
names_after = [a for a, s in strings.items() if in_ro(a) and COMDAT_RO[1] - 0x2000 <= a < COMDAT_RO[1] + 0x10000
               and MANGLED.match(s) and "_GLOBAL__N" not in s]
if names_after:
    COMDAT_RO = (COMDAT_RO[0], max(names_after) + 64)

SPAN_LIMIT = 0x8000   # a target referenced from functions further apart than this is "shared"
ro_points = []         # (func, target)
shared_targets = set()
for t, fs in target_funcs.items():
    if not in_ro(t):
        continue
    if COMDAT_RO[0] <= t < COMDAT_RO[1]:
        shared_targets.add(t)
        continue
    if max(fs) - min(fs) > SPAN_LIMIT:
        shared_targets.add(t)
        continue
    for f in fs:
        ro_points.append((f, t))
ro_points.sort()

# Spearman-ish: rank correlation between func addr and median target
fmed = collections.defaultdict(list)
for f, t in ro_points:
    fmed[f].append(t)
fl = sorted(fmed)
meds = [statistics.median(fmed[f]) for f in fl]


def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0] * len(xs)
    for k, i in enumerate(order):
        r[i] = k
    return r


def spearman(x, y):
    n = len(x)
    if n < 3: return float("nan")
    rx, ry = ranks(x), ranks(y)
    d2 = sum((a - b) ** 2 for a, b in zip(rx, ry))
    return 1 - 6 * d2 / (n * (n * n - 1))


rho_all = spearman(fl, meds)
# local monotonicity: fraction of consecutive ref-functions whose median increases
inc_frac = sum(1 for a, b in zip(meds, meds[1:]) if b >= a) / max(1, len(meds) - 1)

# zero-violation cuts between consecutive ref-functions
fmin = [min(fmed[f]) for f in fl]
fmax = [max(fmed[f]) for f in fl]
pref = []
m = -1
for x in fmax:
    m = max(m, x)
    pref.append(m)
suf = [0] * len(fl)
m = 1 << 40
for k in range(len(fl) - 1, -1, -1):
    m = min(m, fmin[k])
    suf[k] = m
cuts = []   # (left_func, right_func, ro_gap)
for k in range(len(fl) - 1):
    if pref[k] < suf[k + 1]:
        cuts.append((fl[k], fl[k + 1], pref[k], suf[k + 1]))
# atoms: maximal runs of ref-functions with no valid cut inside
atoms = []
cur = [fl[0]] if fl else []
cut_after = {c[0] for c in cuts}
for k in range(len(fl) - 1):
    if fl[k] in cut_after:
        atoms.append(cur)
        cur = [fl[k + 1]]
    else:
        cur.append(fl[k + 1])
if cur:
    atoms.append(cur)

# per-atom anchor files (contradiction test)
func_file = {}
for r in anchored:
    for t in r["text"]:
        func_file.setdefault(t, set()).add(r["file"])
atom_info = []
contradict = 0
for at in atoms:
    lo, hi = at[0], at[-1]
    fs = collections.Counter()
    for t, ff in func_file.items():
        if lo <= t <= hi:
            for x in ff:
                fs[x] += 1
    if len(fs) > 1:
        contradict += 1
    atom_info.append(dict(lo=lo, hi=hi, n_funcs=len(at), files=dict(fs)))

# within each anchored file, count valid cuts strictly inside its text range
cut_lefts = [c[0] for c in cuts]
inside_cuts = []
for r in anchored:
    lo, hi = r["t_min"], r["t_max"]
    k0 = bisect.bisect_left(cut_lefts, lo)
    k1 = bisect.bisect_left(cut_lefts, hi)
    inside_cuts.append(k1 - k0)

# ---------------------------------------------------------------------------
# 9. boundaries between consecutive anchored files
# ---------------------------------------------------------------------------
boundaries = []
for x, y in zip(anchored, anchored[1:]):
    if y["t_min"] <= x["t_max"]:
        boundaries.append(dict(left=x["file"], right=y["file"], lo=x["t_max"], hi=y["t_min"],
                               conf="conflict", cut=None, note="text ranges overlap"))
        continue
    gap_cuts = [c for c in cuts if x["t_max"] <= c[0] and c[1] <= y["t_min"]]
    ro_ok = x["ro_max"] < y["ro_min"]
    if len(gap_cuts) == 1 and ro_ok:
        conf = "high"
        chosen = gap_cuts[0]
    elif gap_cuts and ro_ok:
        conf = "medium"
        # pick the cut whose rodata gap straddles the anchors' rodata gap
        straddle = [c for c in gap_cuts if c[2] <= max(x["ro_max"], c[2]) and c[3] >= y["ro_min"] - 0x0] or gap_cuts
        # prefer cut where rodata jumps past x's last anchor and before y's first anchor
        best = None
        for c in gap_cuts:
            if c[2] >= x["ro_max"] - 0x40 and c[3] <= y["ro_min"] + 0x40:
                best = c
                break
        chosen = best or gap_cuts[0]
        if best is None:
            conf = "medium-low"
    elif not gap_cuts and ro_ok:
        conf = "low"
        chosen = None
    else:
        conf = "low"
        chosen = gap_cuts[0] if gap_cuts else None
    span_funcs = bisect.bisect_left(starts, y["t_min"]) - bisect.bisect_left(starts, x["t_max"])
    boundaries.append(dict(left=x["file"], right=y["file"], lo=x["t_max"], hi=y["t_min"], conf=conf,
                           cut=(chosen[0], chosen[1]) if chosen else None,
                           n_gap_cuts=len(gap_cuts), funcs_in_gap=span_funcs, ro_order_ok=ro_ok))

# ---------------------------------------------------------------------------
# 9b. LEXICAL ORDER TEST: is .text sorted by mangled symbol name?
#     Anchor = (vfunc address, mangled class prefix "_ZN<class>") for vfuncs that
#     appear only in one class's vtable(s).  If armlink sorted per-function
#     sections by name, anchor names are non-decreasing with address.
# ---------------------------------------------------------------------------
def mprefix(tname):
    if tname.startswith("N") and tname.endswith("E"):
        return "_ZN" + tname[1:-1]
    return "_ZN" + tname


vf_owner = collections.defaultdict(set)
for vt in vtables.values():
    for fn in vt["funcs"]:
        vf_owner[fn].add((mprefix(vt["name"]), vt["ott"]))
lex_anchors = sorted((f, next(iter(s))[0], next(iter(s))[1]) for f, s in vf_owner.items()
                     if len({x[0] for x in s}) == 1 and not f & 1)


def lis_members(seq):
    """indices of one longest non-decreasing subsequence"""
    tails, tails_i, prev = [], [], [-1] * len(seq)
    for i, x in enumerate(seq):
        k = bisect.bisect_right(tails, x)
        if k == len(tails):
            tails.append(x); tails_i.append(i)
        else:
            tails[k] = x; tails_i[k] = i
        prev[i] = tails_i[k - 1] if k else -1
    out_ = []
    i = tails_i[-1] if tails_i else -1
    while i >= 0:
        out_.append(i); i = prev[i]
    return set(out_)


lex_names = [n for _, n, _ in lex_anchors]
lis_set = lis_members(lex_names)
import random as _r
_sh = lex_names[:]
_r.seed(12345)
_r.shuffle(_sh)
lis_shuffled = len(lis_members(_sh))
lis_len = len(lis_set)
lex_adjacent_sorted = sum(1 for a, b in zip(lex_names, lex_names[1:]) if a <= b)

# sorted runs: split anchor sequence where the name "wraps" back toward the start of
# the alphabet and stays there (>=3 following anchors all below the previous run max).
runs = []
cur = [0] if lex_anchors else []
for k in range(1, len(lex_anchors)):
    prevmax = max(lex_names[i] for i in cur[-8:])
    nxt = lex_names[k:k + 3]
    wrap = lex_names[k] < prevmax and len(nxt) == 3 and all(x < prevmax for x in nxt) and \
        lex_names[k][3] < prevmax[3]          # length-prefix first digit wrapped (e.g. 9 -> 1)
    if wrap and len(cur) >= 3:
        runs.append(cur); cur = [k]
    else:
        cur.append(k)
if cur:
    runs.append(cur)
lex_runs = []
for r in runs:
    names_r = [lex_names[i] for i in r]
    lis_r = len(lis_members(names_r))
    lex_runs.append(dict(lo=lex_anchors[r[0]][0], hi=lex_anchors[r[-1]][0], n=len(r), lis=lis_r,
                         first=names_r[0], last=names_r[-1],
                         thunks=sum(1 for i in r if lex_anchors[i][2] != 0)))

# 64 KiB text chunk table
chunk_tab = []
for c0 in range(TEXT_VA, TEXT_END, 0x10000):
    idx = [k for k, (f, n, o) in enumerate(lex_anchors) if c0 <= f < c0 + 0x10000]
    if not idx:
        chunk_tab.append((c0, 0, 0, "", ""))
        continue
    inl = [k for k in idx if k in lis_set]
    nm = [lex_names[k] for k in (inl or idx)]
    chunk_tab.append((c0, len(idx), len(inl), nm[0], nm[-1]))

# name coordinate of every function: label = class prefix shared by the nearest
# LIS anchors on both sides (same class => confident label)
lis_pts = sorted((lex_anchors[k][0], lex_names[k]) for k in lis_set)
lis_addr = [a for a, _ in lis_pts]


def common_prefix(a, b):
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return a[:n]


def func_label(f):
    k = bisect.bisect_right(lis_addr, f) - 1
    if k < 0 or k + 1 >= len(lis_pts):
        return None
    left, right = lis_pts[k], lis_pts[k + 1]
    if left[0] == f:
        return left[1]
    if right[0] - left[0] > 0x4000:
        return None
    cp = common_prefix(left[1], right[1])
    return cp if len(cp) > 5 else None


# ---------------------------------------------------------------------------
# 9c. RODATA per-object region segmentation
#     .constdata of each object is contiguous and in link (object) order.
#     Label each referenced rodata target with the class label of its referencing
#     functions (from the lexical name coordinate), plus anon-namespace file anchors.
# ---------------------------------------------------------------------------
PEROBJ_RO = (RO_VA, COMDAT_RO[0])
ro_items = {}     # addr -> dict(labels Counter, file)
for t, fs in target_funcs.items():
    if PEROBJ_RO[0] <= t < PEROBJ_RO[1]:
        labs = collections.Counter()
        for f in fs:
            lb = func_label(f)
            if lb:
                # reduce to top-level namespace/class component "_ZN<len><name>"
                m = re.match(r"_ZN(\d+)", lb)
                if "_GLOBAL__N__" in lb and anon_file(lb):
                    lb = "file:" + anon_file(lb)       # anon-namespace class => its .cpp
                elif m:
                    L = int(m.group(1))
                    lb = lb[: 3 + len(m.group(1)) + L]
                labs[lb] += 1
        ro_items[t] = dict(labels=labs, file=None, n_refs=len(fs))
for t, f in ti_file.items():
    if f and PEROBJ_RO[0] <= t < PEROBJ_RO[1]:
        ro_items.setdefault(t, dict(labels=collections.Counter(), file=None, n_refs=0))["file"] = f
for vt in vtables.values():
    if vt["file"] and PEROBJ_RO[0] <= vt["start"] < PEROBJ_RO[1]:
        ro_items.setdefault(vt["start"], dict(labels=collections.Counter(), file=None, n_refs=0))["file"] = vt["file"]

ro_seq = sorted(ro_items.items())
# file anchor ranges inside rodata
ro_file_rng = {}
for a, it in ro_seq:
    if it["file"]:
        lo, hi = ro_file_rng.get(it["file"], (a, a))
        ro_file_rng[it["file"]] = (min(lo, a), max(hi, a))
ro_file_order = sorted(ro_file_rng.items(), key=lambda kv: kv[1][0])
ro_file_overlap = sum(1 for (f1, r1), (f2, r2) in zip(ro_file_order, ro_file_order[1:]) if r2[0] <= r1[1])

# segment: consecutive items whose dominant label (or file) agrees
segs = []
for a, it in ro_seq:
    key = ("file:" + it["file"]) if it["file"] else (it["labels"].most_common(1)[0][0] if it["labels"] else None)
    if key is None:
        if segs: segs[-1]["n_unlabeled"] += 1
        continue
    if segs and segs[-1]["key"] == key:
        segs[-1]["hi"] = a; segs[-1]["n"] += 1
    else:
        segs.append(dict(key=key, lo=a, hi=a, n=1, n_unlabeled=0))
# map file segments to class labels: class labels of functions that reference that file's rodata
file_classes = collections.defaultdict(collections.Counter)
for a, it in ro_seq:
    if it["file"]:
        continue
    # a labelled item that sits inside a file's rodata range
    for fl_, (lo, hi) in ro_file_rng.items():
        if lo - 0x200 <= a <= hi + 0x200:
            file_classes[fl_].update(it["labels"])

# merge tiny flip-flops: boundaries where both neighbours have n>=2
ro_bounds = []
for s1, s2 in zip(segs, segs[1:]):
    strong = s1["n"] >= 2 and s2["n"] >= 2
    if s1["key"].startswith("file:") or s2["key"].startswith("file:"):
        conf = "high" if strong else "medium"
    else:
        conf = "medium" if strong else "low"
    ro_bounds.append(dict(lo=s1["hi"], hi=s2["lo"], left=s1["key"], right=s2["key"], conf=conf,
                          nl=s1["n"], nr=s2["n"]))

# are global (COMDAT) vtables / typeinfos / type-name strings themselves name-sorted?
def lis_frac(pairs):
    pairs = sorted(pairs)
    nm = [n for _, n in pairs]
    return len(lis_members(nm)), len(nm), (pairs[0][0] if pairs else 0), (pairs[-1][0] if pairs else 0)


# symbol names are _ZTV<type> / _ZTI<type> / _ZTS<type>: sort key = raw mangled type name
gvt = [(v["start"], v["name"]) for v in vtables.values() if not v["file"] and v["ott"] == 0]
gti = [(t, n) for t, n in typeinfo.items() if not ti_file[t]]
gtn = [(a, s) for a, s in strings.items() if COMDAT_RO[0] <= a < COMDAT_RO[1] and MANGLED.match(s)]
comdat_sorted = dict(vtables=lis_frac(gvt), typeinfos=lis_frac(gti), typenames=lis_frac(gtn))

# per text region: does the region look object-ordered (data targets rise with text)?
text_regions = []
_edges = [TEXT_VA] + [r["lo"] for r in lex_runs if r["n"] >= 20] + [TEXT_END]
# finer, fixed edges derived from the run table (start of main run, gaps without anchors, tails)
_cand = sorted(set([TEXT_VA, TEXT_END] + [r["lo"] for r in lex_runs] + [r["hi"] + 4 for r in lex_runs]))
for lo, hi in zip(_cand, _cand[1:]):
    if hi - lo < 0x4000:
        continue
    res = {}
    for nm_, (tlo, thi) in (("rodata", PEROBJ_RO), ("data", (DATA_VA, DATA_END)), ("bss", (BSS_VA, BSS_END))):
        xs, ys = [], []
        for f in sorted(func_refs):
            if not (lo <= f < hi):
                continue
            rr = [r for r in func_refs[f] if tlo <= r < thi and max(target_funcs[r]) - min(target_funcs[r]) < SPAN_LIMIT]
            if rr:
                xs.append(f); ys.append(statistics.median(rr))
        res[nm_] = (len(xs), spearman(xs, ys) if len(xs) > 5 else float("nan"))
    nanch = sum(1 for f, _, _ in lex_anchors if lo <= f < hi)
    nlis = sum(1 for k, (f, _, _) in enumerate(lex_anchors) if lo <= f < hi and k in lis_set)
    text_regions.append(dict(lo=lo, hi=hi, anchors=nanch, lis=nlis, **{k: v for k, v in res.items()}))

# rodata structural map (4 KiB blocks)
ro_struct = []
for b0 in range(RO_VA, RO_END, 0x1000):
    blob = code[RO_OFF + b0 - RO_VA: RO_OFF + min(b0 + 0x1000, RO_END) - RO_VA]
    nstr = sum(len(s) + 1 for a, s in strings.items() if b0 <= a < b0 + 0x1000)
    nti = sum(1 for t in typeinfo if b0 <= t < b0 + 0x1000)
    nvt = sum(1 for v in vtables.values() if b0 <= v["start"] < b0 + 0x1000)
    ntp = sum(1 for k in range(0, len(blob) - 3, 4) if in_text(struct.unpack_from("<I", blob, k)[0]))
    nref = sum(len(target_funcs[t]) for t in target_funcs if b0 <= t < b0 + 0x1000)
    ro_struct.append((b0, round(nstr / max(1, len(blob)), 2), nti, nvt, ntp, nref))

# ---------------------------------------------------------------------------
# 10. strings: source names, asserts, code references
# ---------------------------------------------------------------------------
src_name_re = re.compile(r"[\w/\\.-]+\.(?:c|cpp|cc|cxx|h|hpp|inl|s)\b", re.I)
src_strings = [(a, s) for a, s in strings.items() if src_name_re.search(s) and "_GLOBAL__N" not in s]
assert_like = [(a, s) for a, s in strings.items()
               if ("::" in s or re.search(r"(?i)assert|failed|error|warning|invalid|not attached", s))
               and not MANGLED.match(s)]
str_refd = {a for a in strings if a in target_funcs}
assert_refd = [(a, s, sorted(target_funcs.get(a, ()))) for a, s in assert_like]

# coarse map: rodata 16 KiB block -> median referencing function
block_map = []
by_block = collections.defaultdict(list)
for t, fs in target_funcs.items():
    if in_ro(t):
        by_block[(t - RO_VA) // 0x4000].extend(fs)
for b in sorted(by_block):
    fs = by_block[b]
    block_map.append((RO_VA + b * 0x4000, len(fs), min(fs), int(statistics.median(fs)), max(fs)))

# libraries hint: text regions referencing graphics-shader uniform names (dmp_*) / runtime
lib_hints = collections.defaultdict(list)
for a, s in strings.items():
    if s.startswith("dmp_"): key = "dmp_* shader uniforms (nn::gr / nw4c)"
    elif "runtime error" in s or s.startswith("__"): key = "C/C++ runtime"
    elif re.match(r"^[a-z]+:[A-Za-z]+$", s) or s in ("APT:U", "hid:USER"): key = "service names (nn:: SDK)"
    else: continue
    for f in target_funcs.get(a, ()):
        lib_hints[key].append(f)

# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
H = lambda x: "0x%08X" % x
out("Fire Emblem: Awakening (CTR-P-AFEE) - object split evidence")
out("generated by tools/analysis/splits.py  (heuristic; see confidence tags)")
out("=" * 78)
out("")
out("[SUMMARY NUMBERS]")
nums = collections.OrderedDict()
nums["text_words"] = NTW
nums["literal_pool_words"] = len(LIT)
nums["literal_targets_text"] = sum(1 for v in lit_values.values() if in_text(v))
nums["literal_targets_rodata"] = sum(1 for v in lit_values.values() if in_ro(v))
nums["literal_targets_data"] = sum(1 for v in lit_values.values() if in_data(v))
nums["literal_targets_bss"] = sum(1 for v in lit_values.values() if in_bss(v))
nums["function_starts"] = len(starts)
src_c = collections.Counter()
for a in starts:
    for s in starts_src[a]:
        src_c[s] += 1
nums["function_start_sources"] = dict(src_c)
nums["func_start_alignment_hist"] = {str(k): v for k, v in sorted(align_hist.items())}
nums["strings_rodata_data"] = len(strings)
nums["strings_referenced_by_code_literal"] = len(str_refd)
nums["typeinfo_vptrs"] = [H(v) for v in sorted(TI_VPTRS)]
nums["typeinfo_objects"] = len(typeinfo)
nums["typeinfo_anon_namespace"] = sum(1 for f in ti_file.values() if f)
nums["vtables"] = len(vtables)
nums["vtables_anon"] = sum(1 for v in vtables.values() if v["file"])
nums["vfunc_slots"] = sum(len(v["funcs"]) for v in vtables.values())
nums["anon_source_files"] = len(files)
nums["anon_files_with_text_anchors"] = len(anchored)
nums["anchor_text_funcs"] = sum(r["n_text"] for r in anchored)
nums["anchor_order_concordance_text_vs_rodata"] = round(kendall_frac, 4)
nums["anchor_text_range_overlaps"] = overlaps
nums["comdat_rtti_region"] = [H(COMDAT_RO[0]), H(COMDAT_RO[1])]
nums["ro_ref_functions"] = len(fl)
nums["ro_points"] = len(ro_points)
nums["ro_shared_targets_excluded"] = len(shared_targets)
nums["spearman_func_vs_median_ro_target"] = round(rho_all, 4)
nums["consecutive_ref_funcs_ro_nondecreasing_frac"] = round(inc_frac, 4)
nums["zero_violation_cuts"] = len(cuts)
nums["atoms"] = len(atoms)
nums["atoms_with_conflicting_anchor_files"] = contradict
nums["anchored_files_with_no_internal_cut"] = sum(1 for x in inside_cuts if x == 0)
nums["anchored_files_internal_cuts_median"] = statistics.median(inside_cuts) if inside_cuts else 0
nums["boundaries_between_anchor_files"] = collections.Counter(b["conf"] for b in boundaries)
nums["pointer_tables_ge4"] = len(tables)
nums["init_array_walker_candidates"] = len(init_candidates)
nums["source_filename_strings"] = len(src_strings)
nums["assert_like_strings"] = len(assert_like)
nums["assert_like_strings_code_referenced"] = sum(1 for a, s, f in assert_refd if f)
nums["padding"] = pad_stats
nums["lex_anchors"] = len(lex_anchors)
nums["lex_adjacent_sorted"] = lex_adjacent_sorted
nums["lex_LIS"] = lis_len
nums["lex_LIS_frac"] = round(lis_len / max(1, len(lex_anchors)), 4)
nums["lex_LIS_shuffled_baseline"] = lis_shuffled
nums["lex_sorted_runs"] = len(lex_runs)
nums["ro_perobject_items"] = len(ro_seq)
nums["ro_segments"] = len(segs)
nums["ro_boundaries_by_conf"] = dict(collections.Counter(b["conf"] for b in ro_bounds))
nums["ro_anon_file_ranges_overlapping"] = ro_file_overlap
for k, v in nums.items():
    out("  %-48s %s" % (k, v))
out("")

out("[1] PADDING / ALIGNMENT  (object boundaries via gaps?)")
out("  Function starts by largest power-of-two alignment: %s" % dict(sorted(align_hist.items())))
out("  Random 4-aligned addresses would give ~12.5%% 32B, 12.5%% 16B, 25%% 8B, 50%% 4B.")
for k, v in pad_stats.items():
    out("  %-10s runs=%d words=%d followed-by-func-start=%d len-hist=%s" %
        (k, v["runs"], v["words"], v["runs_followed_by_func_start"], v["len_hist"]))
out("  Interpretation: NOP hints (E320F000) are scheduler fillers inside functions (mostly single,")
out("  interleaved with BL), not inter-object padding.  No alignment padding -> gaps are NOT a")
out("  usable boundary signal (confidence: high).")
out("")

out("[2] SOURCE FILE NAMES")
out("  Plain source-file-name strings (*.c/*.cpp/*.h) in rodata/data: %d" % len(src_strings))
for a, s in src_strings[:20]:
    out("    %s %r" % (H(a), s[:80]))
out("  But anonymous-namespace RTTI names leak %d distinct .cpp names (see [4])." % len(files))
out("")

out("[3] ASSERT / LOG STRINGS  (%d candidates, %d referenced by code literals)" %
    (len(assert_like), sum(1 for a, s, f in assert_refd if f)))
for a, s, fs in sorted(assert_refd)[:60]:
    out("    %s refs=%-3d %s %r" % (H(a), len(fs), ",".join(H(f) for f in fs[:3]), s[:70]))
out("")

out("[4] ANONYMOUS-NAMESPACE FILE ANCHORS (sorted by median text address)")
out("  file                              n_cls n_txt  text_min    text_max    ro_min      ro_max      src")
for r in anchored:
    out("  %-34s %4d %5d  %s  %s  %s  %s  %s" % (r["file"][:34], r["n_classes"], r["n_text"],
        H(r["t_min"]), H(r["t_max"]), H(r["ro_min"]), H(r["ro_max"]), r.get("src")))
noanch = [r for r in anchor_rows if not r["n_text"]]
if noanch:
    out("  files with RTTI but no text anchor: " + ", ".join(r["file"] for r in noanch))
out("  Pairwise order concordance (text order vs rodata order): %.3f (1.0 = identical order)" % kendall_frac)
out("  Adjacent anchored files whose text ranges overlap: %d of %d" % (overlaps, max(0, len(anchored) - 1)))
out("")

out("[5] RODATA ORDER vs TEXT ORDER")
out("  Functions with private rodata refs: %d, points: %d (excluded %d shared targets: COMDAT RTTI region"
    % (len(fl), len(ro_points), len(shared_targets)))
out("  %s-%s and targets referenced from >0x%X apart)" % (H(COMDAT_RO[0]), H(COMDAT_RO[1]), SPAN_LIMIT))
out("  Spearman(func addr, median rodata target) = %.4f" % rho_all)
out("  Consecutive ref-functions with non-decreasing median target: %.1f%%" % (100 * inc_frac))
out("  Zero-violation cuts (no rodata span crosses): %d -> %d atoms (minimum object fragments)" %
    (len(cuts), len(atoms)))
out("  Atoms containing anchors from >1 file (contradictions): %d" % contradict)
out("  Anchored files with 0 cuts inside their anchor text range: %d / %d" %
    (sum(1 for x in inside_cuts if x == 0), len(inside_cuts)))
out("  Coarse map  rodata 16KiB block -> referencing functions (count, min, median, max):")
for b, n, lo, md, hi in block_map:
    out("    %s  n=%-5d %s %s %s" % (H(b), n, H(lo), H(md), H(hi)))
out("")

out("[6] POINTER TABLES (>=4 consecutive pointers to function starts)")
for t in tables[:25]:
    out("  %s %s n=%-4d distinct=%-4d increasing=%-4d inside_vtable=%s first=%s" %
        (t["mode"], H(t["addr"]), t["n"], t["distinct"], t["increasing"], t["inside_vtable"],
         H(t["targets"][0])))
out("  init_array walker candidates (func with literals Base<Limit bracketing a fn-ptr table):")
for c in init_candidates[:10]:
    out("    walker %s base %s limit %s n=%d mode=%s" % (H(c["walker"]), H(c["base"]), H(c["limit"]),
                                                     c["n"], c["mode"]))
if not init_candidates:
    out("    none found (no ARMCC __sti__/init_array signal; confidence medium)")
out("  Library hints (functions referencing library-typical strings):")
for k, fs in lib_hints.items():
    out("    %-40s n=%-4d text %s..%s median %s" % (k, len(fs), H(min(fs)), H(max(fs)),
                                                  H(int(statistics.median(fs)))))
out("")

out("[7] KEY RESULT: .text IS SORTED BY MANGLED SYMBOL NAME (per-function sections)")
out("  Anchors: %d vfuncs owned by exactly one class (name = _ZN<class> prefix)." % len(lex_anchors))
out("  Adjacent anchor pairs already in lexical order: %d / %d (%.1f%%)" %
    (lex_adjacent_sorted, max(1, len(lex_anchors) - 1), 100.0 * lex_adjacent_sorted / max(1, len(lex_anchors) - 1)))
out("  Longest non-decreasing subsequence: %d / %d = %.1f%%   (same names shuffled: %d = %.1f%%)" %
    (lis_len, len(lex_anchors), 100.0 * lis_len / max(1, len(lex_anchors)), lis_shuffled,
     100.0 * lis_shuffled / max(1, len(lex_anchors))))
out("  Anonymous-namespace classes appear in text ordered by the *length prefix* of")
out("  _ZN<NN>_GLOBAL__N__<len>_<File>_cpp_<hash>  (35 DLC_Seq < 36 MapDebug < 37 MyTeamSeq < 38 RecvBoxSeq <")
out("  39 DLC_MenuSeq < 40 GlobalMapSeq < 41 MyUnitListSeq) i.e. pure string order, not file order.")
out("  => armlink placed one input section per function and ordered them lexically (RVCT armlink")
out("     --sort=Lexical-like behaviour, compiled with --split_sections or per-function COMDAT).")
out("  => There are NO object-file boundaries to recover inside these .text runs.  For matching,")
out("     reproduce the order by name: compile with per-function sections and link with the same")
out("     lexical sort (or emit a generated linker order file listing every symbol).  Source files can")
out("     then be organised freely (by class), unlike GBA decomps where ldscript order == file order.")
out("     (confidence: high for the game-code runs listed below)")
out("")
out("  Sorted runs (split where the name wraps back to the start of the alphabet):")
out("    lo          hi          anchors  in-run-LIS  ott!=0  first-name .. last-name")
for r in lex_runs:
    out("    %s  %s  %6d  %6d  %6d   %s .. %s" % (H(r["lo"]), H(r["hi"]), r["n"], r["lis"], r["thunks"],
                                                  r["first"][:40], r["last"][:40]))
out("  Interpretation (medium/low confidence): run boundaries are the only real 'split' points in")
out("  .text: separate input-section-name classes (e.g. normal functions vs COMDAT/inline vs thunks")
out("  _ZThn.. / templates) or separately linked groups.  Regions with few/no anchors (SDK, NW4C,")
out("  middleware MoLive/Mobiclip, C runtime) are unverified; they have no RTTI to test with.")
out("")
out("  64 KiB text chunks: anchors, anchors on the global LIS, first..last anchor name on LIS")
for c0, n, nl, a, b in chunk_tab:
    tag = "" if n == 0 else ("  <-- mostly off-LIS (unsorted / other group / misattributed)" if nl < n / 2 else "")
    out("    %s  n=%-4d lis=%-4d %s .. %s%s" % (H(c0), n, nl, a[:34], b[:34], tag))
out("")

out("[8] ANON FILE ANCHORS INSIDE RODATA (per-object .constdata region %s-%s)" % (H(PEROBJ_RO[0]), H(PEROBJ_RO[1])))
out("  Rodata keeps object (link) order; global RTTI/vtables are COMDAT and were moved to the")
out("  lexically sorted region %s-%s (global type-name strings sorted: see [4]/summary)." %
    (H(COMDAT_RO[0]), H(COMDAT_RO[1])))
out("  file                              ro_lo       ro_hi       classes referencing (top labels)")
for f, (lo, hi) in ro_file_order:
    out("  %-34s %s  %s  %s" % (f[:34], H(lo), H(hi),
                                ", ".join("%s:%d" % (k[3:30], v) for k, v in file_classes[f].most_common(3))))
out("  overlapping file ranges in rodata: %d of %d adjacent pairs (0 => each file's RTTI is contiguous)" %
    (ro_file_overlap, max(0, len(ro_file_order) - 1)))
out("")

out("[9] RODATA OBJECT BOUNDARY CANDIDATES (label = referencing class / anon file)")
out("  Items: %d referenced or RTTI items in per-object region; segments: %d; boundaries: %d" %
    (len(ro_seq), len(segs), len(ro_bounds)))
out("  conf: high = file-anchored segment on one side, >=2 items each side; medium = >=2 items both")
out("        sides (class labels from the lexical name coordinate); low = single-item flip (noise likely)")
cc = collections.Counter(b["conf"] for b in ro_bounds)
out("  counts: %s" % dict(cc))
out("  boundary_between            conf    left_label (n) -> right_label (n)")
for b in ro_bounds:
    if b["conf"] == "low":
        continue
    out("  %s..%s  %-7s %s (%d) -> %s (%d)" % (H(b["lo"]), H(b["hi"]), b["conf"], b["left"][:38], b["nl"],
                                                 b["right"][:38], b["nr"]))
out("  (%d low-confidence single-item flips omitted; see split_candidates.json)" % cc.get("low", 0))
out("")

out("[9b] ARE THE COMDAT RTTI OBJECTS NAME-SORTED?  (LIS / n, address span)")
for k, (l_, n_, lo_, hi_) in comdat_sorted.items():
    out("  %-10s %4d / %-4d = %5.1f%%   %s..%s" % (k, l_, n_, 100.0 * l_ / max(1, n_), H(lo_), H(hi_)))
out("  (high LIS => COMDAT sections were sorted by symbol name too, like .text)")
out("")

out("[10] RODATA STRUCTURE MAP (4 KiB blocks): str_frac, typeinfos, vtables, text-ptr words, code refs")
for b0, sf, nti, nvt, ntp, nref in ro_struct:
    out("  %s  str=%.2f ti=%-3d vt=%-3d tptr=%-4d refs=%-4d%s" % (H(b0), sf, nti, nvt, ntp, nref,
        "  [COMDAT RTTI]" if COMDAT_RO[0] <= b0 < COMDAT_RO[1] else ""))
out("")

out("[11] OBJECT-ORDER ASSUMPTION TEST (kept for the record)")
out("  If .text were in object order, rodata targets would rise with text address.  Observed:")
out("  Spearman %.4f, %d zero-violation cuts, anchor-file concordance %.3f, %d/%d adjacent anchor files" %
    (rho_all, len(cuts), kendall_frac, overlaps, max(0, len(anchored) - 1)))
out("  overlap in text.  => .text is NOT in object order (consistent with [7]).")
out("  Per text region (edges from [7] runs): anchors / on-LIS, and Spearman(text addr, median target)")
out("  for private refs into per-object rodata, .data, .bss.  Positive rho in a region => that region")
out("  may be whole-object sections in link order (classic file splits apply there).")
for r in text_regions:
    def _f(x): return "n=%-4d rho=%6.3f" % (x[0], x[1]) if x[0] > 5 else "n=%-4d rho=   n/a" % x[0]
    out("    %s-%s anch=%-4d lis=%-4d ro[%s] data[%s] bss[%s]" % (H(r["lo"]), H(r["hi"]), r["anchors"], r["lis"],
        _f(r["rodata"]), _f(r["data"]), _f(r["bss"])))
out("  Boundaries between anchored files under the object-order assumption (all rejected):")
for b in boundaries:
    out("    %-24s -> %-24s %-9s [%s..%s]" % (b["left"][:24], b["right"][:24], b["conf"], H(b["lo"]), H(b["hi"])))
out("")

concl = [
    "[0] CONCLUSIONS / FEASIBILITY OF AUTOMATIC SPLITTING",
    "  A. .text is ordered by mangled symbol name, not by object file (HIGH): %d/%d (%.1f%%) single-class"
    % (lis_len, len(lex_anchors), 100.0 * lis_len / max(1, len(lex_anchors))),
    "     vfunc anchors lie on one lexically sorted sequence (shuffled baseline %.1f%%)."
    % (100.0 * lis_shuffled / max(1, len(lex_anchors))),
    "     COMDAT RTTI in rodata is sorted the same way: _ZTI* %s, then _ZTS* %s, then _ZTV* %s, each 100%% sorted."
    % (H(comdat_sorted["typeinfos"][2]), H(comdat_sorted["typenames"][2]), H(comdat_sorted["vtables"][2])),
    "     => armlink sorted input sections by name (one section per function).  GBA-style 'asm/+src/ file",
    "        splits' do not exist in .text: the unit of splitting is the FUNCTION, and link order is",
    "        recomputable from symbol names.  Use the CTR-SDK toolchain (armcc/armlink 4.x) with per-function",
    "        sections, or generate an explicit order file; source files can be organised by class freely.",
    "  B. A function's position predicts its mangled name (HIGH for game runs): every function between two",
    "     anchors of class C is a member of C (or sorts between) - a strong symbol-recovery tool.",
    "  C. .rodata/.data keep object (link) order for non-COMDAT data (HIGH for 0x45A000-0x466260): the 15",
    "     anon-namespace .cpp files' RTTI blocks are contiguous and non-overlapping in rodata; %d rodata"
    % sum(1 for b in ro_bounds if b["conf"] in ("high", "medium")),
    "     boundary candidates (high/medium) found in [9].  Rodata after ~0x466260 up to %s is library/" % H(PEROBJ_RO[1]),
    "     middleware data referenced from unanchored code (LOW: unlabeled).",
    "  D. Not usable as boundary signals: alignment/padding (function starts are 4-byte aligned at random-",
    "     like ratios; NOP E320F000 runs are intra-function), plain source-file-name strings (0 found),",
    "     init_array tables (no walker/table found; LOW-MEDIUM).",
    "  E. Unresolved (LOW): text 0x00100000-0x00158B28 (crt/SDK/free functions?), 0x00215D2C-0x00388E9C",
    "     (~1.5 MiB of game code with no RTTI anchors; possibly anon-namespace or other names sorting between",
    "     _ZN25.. and _ZN35_GLOBAL.., not verified), and tails after 0x003EE900 (const methods/COMDAT/thunks/",
    "     templates/middleware: separate sorted groups; some tails show object-order correlation, see [11]).",
    "  Feasibility: automatic splitting into per-function units is EASY (function boundaries + lexical model);",
    "  recovering original .cpp boundaries is only needed for rodata/data/bss, and is PARTIAL (anchored game",
    "  objects + class-labelled segments), LOW for library regions.",
    "",
]
log_lines[3:3] = concl

os.makedirs(OUTDIR, exist_ok=True)
with open(OUT_TXT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(log_lines) + "\n")

js = dict(
    numbers={k: (v if not isinstance(v, collections.Counter) else dict(v)) for k, v in nums.items()},
    comdat_rtti_region=list(COMDAT_RO),
    anchors=[dict(file=r["file"], text=r["text"], ro_min=r["ro_min"], ro_max=r["ro_max"])
             for r in anchored],
    boundaries=boundaries,
    cuts=[dict(left=l, right=r, ro_left_max=p, ro_right_min=s) for l, r, p, s in cuts],
    atoms=atom_info,
    vtables=[dict(addr=v["start"], file=v["file"], name=v["name"], funcs=v["funcs"])
             for v in sorted(vtables.values(), key=lambda v: v["start"])],
    pointer_tables=[{k: t[k] for k in ("mode", "addr", "n", "distinct", "increasing", "inside_vtable")}
                    for t in tables],
    function_starts=starts,
    lex_anchors=[dict(addr=f, cls=n, ott=o, on_lis=(k in lis_set)) for k, (f, n, o) in enumerate(lex_anchors)],
    lex_runs=lex_runs,
    ro_file_ranges={f: list(r) for f, r in ro_file_rng.items()},
    ro_segments=segs,
    ro_boundaries=ro_bounds,
)
with open(OUT_JSON, "w", encoding="utf-8") as fh:
    json.dump(js, fh, default=lambda o: sorted(o) if isinstance(o, set) else str(o))

print("\n".join(log_lines[:60]))
print("... wrote", OUT_TXT, "and", OUT_JSON)
