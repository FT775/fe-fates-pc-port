#!/usr/bin/env python3
"""
fingerprint.py - toolchain / library fingerprinting for the game's decrypted 3DS
code.bin (segments from extracted/layout.json, written by tools/extract_rom.py).

Standard library only. Read-only on inputs. Writes to extracted/analysis/:
  fingerprint.json          machine-readable results
  fingerprint_report.txt    human-readable summary
  rtti_classes.csv          every RTTI typeinfo found (name, kind, bases, vtable, vfunc range)
  rtti_source_files.csv     source files leaked through EDG anonymous-namespace names
  string_xref_buckets.csv   per-64KB .text bucket: game vs SDK string references

Usage:  python tools/analysis/fingerprint.py [project_root]
"""
import collections
import csv
import json
import os
import re
import struct
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else
                       os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EXT = os.path.join(ROOT, "extracted")
OUT = os.path.join(EXT, "analysis")

# ----------------------------------------------------------------------------
# Segments
# ----------------------------------------------------------------------------
with open(os.path.join(EXT, "layout.json"), "r", encoding="utf-8") as f:
    LAYOUT = json.load(f)
with open(os.path.join(EXT, "code.bin"), "rb") as f:
    CODE = f.read()

SEGS = {}
for name in ("text", "rodata", "data"):
    s = LAYOUT[name]
    SEGS[name] = (s["addr"], s["size"], s["file_offset"])

TEXT_VA, TEXT_SZ, TEXT_OFF = SEGS["text"]
RO_VA, RO_SZ, RO_OFF = SEGS["rodata"]
DATA_VA, DATA_SZ, DATA_OFF = SEGS["data"]
BSS_SZ = LAYOUT.get("bss_size", 0)


def seg_of_va(va):
    for n, (a, sz, _) in SEGS.items():
        if a <= va < a + sz:
            return n
    if DATA_VA + DATA_SZ <= va < DATA_VA + DATA_SZ + BSS_SZ + 0x1000:
        return "bss"
    return None


def va2off(va):
    for n, (a, sz, off) in SEGS.items():
        if a <= va < a + sz:
            return va - a + off
    return None


def off2va(off):
    for n, (a, sz, o) in SEGS.items():
        if o <= off < o + sz:
            return off - o + a
    return None


def seg_bytes(name):
    a, sz, off = SEGS[name]
    return CODE[off:off + sz]


def u32(va):
    o = va2off(va)
    if o is None or o + 4 > len(CODE):
        return None
    return struct.unpack_from("<I", CODE, o)[0]


def in_text(v):
    return TEXT_VA <= v < TEXT_VA + TEXT_SZ


def cstr(va, maxlen=512):
    o = va2off(va)
    if o is None:
        return None
    e = CODE.find(b"\0", o, o + maxlen)
    if e < 0:
        return None
    return CODE[o:e]


# word index: value -> list of VAs holding that aligned word (rodata+data+text)
def build_word_index(segnames):
    idx = collections.defaultdict(list)
    for n in segnames:
        a, sz, off = SEGS[n]
        b = CODE[off:off + sz]
        cnt = sz // 4
        words = struct.unpack_from("<%dI" % cnt, b, 0)
        for i, w in enumerate(words):
            idx[w].append(a + i * 4)
    return idx


WIDX_ROD = build_word_index(["rodata", "data"])
WIDX_TEXT = build_word_index(["text"])

# ----------------------------------------------------------------------------
# 1. Strings
# ----------------------------------------------------------------------------
STR_RE = re.compile(rb"[\x20-\x7e\t\n\r]{4,}\x00")


def ascii_strings():
    res = []
    for n in ("text", "rodata", "data"):
        a, sz, off = SEGS[n]
        b = CODE[off:off + sz]
        for m in STR_RE.finditer(b):
            s = m.group()[:-1]
            # require at least 3 letters to drop most instruction-byte noise
            if sum(1 for c in s if 65 <= c <= 90 or 97 <= c <= 122) < 3:
                continue
            res.append((a + m.start(), n, s.decode("latin-1")))
    return res


STRINGS = ascii_strings()
STR_BY_VA = {va: s for va, _, s in STRINGS}

U16_RE = re.compile(rb"(?:[\x20-\x7e]\x00){4,}\x00\x00")


def utf16_strings():
    res = []
    for n in ("rodata", "data", "text"):
        a, sz, off = SEGS[n]
        b = CODE[off:off + sz]
        for m in U16_RE.finditer(b):
            if (m.start() & 1):
                continue
            res.append((a + m.start(), n, m.group()[:-2].decode("utf-16-le")))
    return res


U16 = utf16_strings()

# ----------------------------------------------------------------------------
# 2. Itanium-ABI mangled type names (RTTI typeinfo names)
# ----------------------------------------------------------------------------
BUILTIN = set("vwbcahstijlmxynofdegz")


class P:
    def __init__(self, s):
        self.s, self.i = s, 0

    def peek(self):
        return self.s[self.i] if self.i < len(self.s) else ""


def p_source_name(p):
    m = re.match(r"\d+", p.s[p.i:])
    if not m:
        return None
    n = int(m.group())
    if n == 0:
        return None
    st = p.i + len(m.group())
    ident = p.s[st:st + n]
    if len(ident) != n or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", ident):
        return None
    p.i = st + n
    return ident


def p_template_args(p):
    if p.peek() != "I":
        return ""
    p.i += 1
    args = []
    while p.peek() and p.peek() != "E":
        if p.peek() == "L":  # literal
            e = p.s.find("E", p.i)
            if e < 0:
                return None
            args.append(p.s[p.i + 1:e])
            p.i = e + 1
            continue
        t = p_type(p)
        if t is None:
            return None
        args.append(t)
    if p.peek() != "E":
        return None
    p.i += 1
    return "<" + ",".join(args) + ">"


def p_type(p):
    c = p.peek()
    if c in BUILTIN:
        p.i += 1
        return {"v": "void", "b": "bool", "c": "char", "a": "schar", "h": "uchar", "s": "short",
                "t": "ushort", "i": "int", "j": "uint", "l": "long", "m": "ulong", "x": "llong",
                "y": "ullong", "f": "float", "d": "double", "w": "wchar_t", "n": "int128",
                "o": "uint128", "e": "ldouble", "g": "float128", "z": "..."}[c]
    if c in "PRK":
        p.i += 1
        t = p_type(p)
        return None if t is None else t + {"P": "*", "R": "&", "K": " const"}[c]
    if c == "N":
        return p_nested(p)
    if c == "S" and p.s[p.i:p.i + 2] == "St":
        p.i += 2
        n = p_source_name(p)
        if n is None:
            return None
        ta = p_template_args(p)
        return None if ta is None else "std::" + n + ta
    if c.isdigit():
        n = p_source_name(p)
        if n is None:
            return None
        ta = p_template_args(p)
        return None if ta is None else n + ta
    return None


def p_nested(p):
    if p.peek() != "N":
        return None
    p.i += 1
    parts = []
    if p.s[p.i:p.i + 2] == "St":
        p.i += 2
        parts.append("std")
    while p.peek() and p.peek() != "E":
        if p.peek().isdigit():
            n = p_source_name(p)
            if n is None:
                return None
            parts.append(n)
        elif p.peek() == "I" and parts:
            ta = p_template_args(p)
            if ta is None:
                return None
            parts[-1] += ta
        else:
            return None
    if p.peek() != "E" or not parts:
        return None
    p.i += 1
    return "::".join(parts)


def demangle_type_name(s):
    p = P(s)
    t = p_type(p)
    if t is None or p.i != len(s):
        return None
    return t


# ----------------------------------------------------------------------------
# 3. RTTI typeinfo objects and vtables
# ----------------------------------------------------------------------------
def find_typeinfos():
    cands = {}
    for va, seg, s in STRINGS:
        if seg not in ("rodata", "data"):
            continue
        if not (s[0].isdigit() or s.startswith("N") or s.startswith("St")):
            continue
        dm = demangle_type_name(s)
        if dm is None:
            continue
        cands[va] = (s, dm)
    # typeinfo object: [vptr][name ptr] ...
    raw = []
    for nva, (s, dm) in cands.items():
        for ref in WIDX_ROD.get(nva, []):
            ti = ref - 4
            vptr = u32(ti)
            if vptr is None:
                continue
            raw.append((ti, vptr, nva, s, dm))
    vcount = collections.Counter(r[1] for r in raw)
    # The typeinfo vtables are the few vptr values shared by many objects.
    common = [v for v, c in vcount.most_common() if c >= 3]
    tis = {}
    for ti, vptr, nva, s, dm in raw:
        if vptr in common:
            tis[ti] = {"addr": ti, "vptr": vptr, "name_addr": nva, "mangled": s, "name": dm}
    # classify vptr groups structurally
    ti_addrs = set(tis)
    kinds = {}
    for v in common:
        members = [t for t in tis.values() if t["vptr"] == v]
        si = sum(1 for t in members if u32(t["addr"] + 8) in ti_addrs)
        vmi = sum(1 for t in members
                  if (u32(t["addr"] + 12) or 0) in range(1, 16) and u32(t["addr"] + 16) in ti_addrs)
        n = len(members)
        if n and si / n > 0.8:
            kinds[v] = "si"
        elif n and vmi / n > 0.8:
            kinds[v] = "vmi"
        else:
            kinds[v] = "class"
    for t in tis.values():
        k = kinds.get(t["vptr"], "?")
        t["kind"] = k
        t["bases"] = []
        if k == "si":
            b = u32(t["addr"] + 8)
            t["bases"] = [b]
            t["size"] = 12
        elif k == "vmi":
            nb = u32(t["addr"] + 12)
            t["flags"] = u32(t["addr"] + 8)
            t["bases"] = [u32(t["addr"] + 16 + 8 * i) for i in range(nb)]
            t["size"] = 16 + 8 * nb
        else:
            t["size"] = 8
    return tis, kinds, cands


TIS, TI_KINDS, MANGLED_CANDS = find_typeinfos()


def find_vtables():
    """vtable layout (Itanium/ARM C++ ABI): [offset_to_top][typeinfo*][vfunc0]..."""
    ti_ranges = [(t["addr"], t["addr"] + t["size"]) for t in TIS.values()]
    ti_ranges.sort()

    def inside_ti(va):
        # binary search
        lo, hi = 0, len(ti_ranges)
        while lo < hi:
            mid = (lo + hi) // 2
            if ti_ranges[mid][1] <= va:
                lo = mid + 1
            else:
                hi = mid
        return lo < len(ti_ranges) and ti_ranges[lo][0] <= va < ti_ranges[lo][1]

    vts = []
    for tia, t in TIS.items():
        for ref in WIDX_ROD.get(tia, []):
            if inside_ti(ref):
                continue
            off_top = u32(ref - 4)
            if off_top is None:
                continue
            ot = off_top - (1 << 32) if off_top & 0x80000000 else off_top
            if not (-0x10000 < ot <= 0):
                continue
            funcs = []
            p = ref + 4
            while True:
                w = u32(p)
                if w is None:
                    break
                # pure virtual / deleted entries also point into text; 0 = abstract hole (rare)
                if in_text(w & ~1):
                    funcs.append(w)
                    p += 4
                    if len(funcs) > 400:
                        break
                else:
                    break
            vts.append({"addr": ref - 4, "typeinfo": tia, "offset_to_top": ot, "vfuncs": funcs})
    return vts


VTABLES = find_vtables()


def mark_own_vfuncs():
    """A vfunc slot is 'own' if it differs from the same slot of the (primary) base's
    primary vtable. Inherited, un-overridden slots point at base-class code elsewhere."""
    prim = {}
    for v in VTABLES:
        if v["offset_to_top"] == 0:
            prim.setdefault(v["typeinfo"], v)
    for v in VTABLES:
        t = TIS[v["typeinfo"]]
        basev = None
        if t["bases"] and t["bases"][0] in prim:
            basev = prim[t["bases"][0]]["vfuncs"]
        own = []
        for i, f in enumerate(v["vfuncs"]):
            if basev is not None and i < len(basev) and basev[i] == f:
                continue
            own.append(f)
        v["own"] = own
    # functions shared by >=3 unrelated vtables (pure-virtual stub, empty dtor, ...) are not own
    share = collections.Counter(f for v in VTABLES for f in set(v["own"]))
    for v in VTABLES:
        v["own"] = [f for f in v["own"] if share[f] < 3]
    return share


VFUNC_SHARE = mark_own_vfuncs()

# ----------------------------------------------------------------------------
# 4. EDG anonymous namespaces -> source files
# ----------------------------------------------------------------------------
ANON_RE = re.compile(r"_GLOBAL__N__\d+_([A-Za-z0-9_]+?)_(cpp|cc|cxx|c|h|hpp)_([0-9a-f]{8})")


def source_files_from_anon():
    files = collections.OrderedDict()
    for va, seg, s in STRINGS:
        for m in ANON_RE.finditer(s):
            key = m.group(1) + "." + m.group(2)
            e = files.setdefault(key, {"file": key, "hash": set(), "classes": set(), "name_addrs": []})
            e["hash"].add(m.group(3))
            e["name_addrs"].append(va)
    return files


SRCFILES = source_files_from_anon()

# ----------------------------------------------------------------------------
# 5. Code statistics (ARM11 / armcc fingerprints)
# ----------------------------------------------------------------------------
TEXT = seg_bytes("text")
NW = len(TEXT) // 4
TW = struct.unpack_from("<%dI" % NW, TEXT, 0)


def classify_chunks(chunk=256):
    """Return per-chunk mode: 'arm', 'thumb', 'data'. ARM code has cond=0xE on most words."""
    modes = []
    for c in range(0, NW, chunk // 4):
        ws = TW[c:c + chunk // 4]
        n = len(ws)
        e = sum(1 for w in ws if (w >> 28) == 0xE)
        # thumb hints: push/pop/bx lr halfwords, BL pairs
        hs = struct.unpack_from("<%dH" % (n * 2), TEXT, c * 4)
        th = 0
        for i, h in enumerate(hs):
            if (h & 0xFF00) in (0xB500, 0xBD00) or h == 0x4770:
                th += 1
            if (h & 0xF800) == 0xF000 and i + 1 < len(hs) and (hs[i + 1] & 0xE800) == 0xE800:
                th += 1
        if e / n >= 0.45:
            modes.append("arm")
        elif th >= max(3, n // 16):
            modes.append("thumb")
        else:
            modes.append("data")
    return modes


CHUNK = 256
MODES = classify_chunks(CHUNK)


def mode_at(va):
    return MODES[(va - TEXT_VA) // CHUNK]


PATTERNS = {
    # name: (mask, value)
    "arm_prologue_stmfd_lr": (0xFFFF4000, 0xE92D4000),
    "arm_epilogue_ldmfd_pc": (0xFFFF8000, 0xE8BD8000),
    "arm_bx_lr": (0xFFFFFFFF, 0xE12FFF1E),
    "arm_str_lr_predec": (0xFFFFFFFF, 0xE52DE004),
    "arm_ldr_pc_postinc": (0xFFFFFFFF, 0xE49DF004),
    "arm_bl": (0xFF000000, 0xEB000000),
    "arm_blx_imm": (0xFE000000, 0xFA000000),
    "arm_svc": (0xFF000000, 0xEF000000),
    "switch_add_pc_pc_rn_lsl2 (branch table of B)": (0x0FFFFFF0, 0x008FF100),
    "switch_ldr_pc_pc_rn_lsl2 (address table)": (0x0FFFFFF0, 0x079FF100),
    "nop_v6k (E320F000)": (0xFFFFFFFF, 0xE320F000),
    "mov_pc_lr (non-interworking return)": (0xFFFFFFFF, 0xE1A0F00E),
    "mov_r0_r0 (legacy nop)": (0xFFFFFFFF, 0xE1A00000),
    "veneer_ldr_pc_pc_m4": (0xFFFFFFFF, 0xE51FF004),
    "clz": (0x0FFF0FF0, 0x016F0F10),
    "ldrex": (0x0FF00FFF, 0x01900F9F),
    "strex": (0x0FF00FF0, 0x01800F90),
    "ldrexb/h/d (v6K)": (0x0F900FFF, 0x01900F9F),  # refined below
    "clrex (v6K)": (0xFFFFFFFF, 0xF57FF01F),
    "yield (v6K)": (0xFFFFFFFF, 0xE320F001),
    "wfe (v6K)": (0xFFFFFFFF, 0xE320F002),
    "wfi (v6K)": (0xFFFFFFFF, 0xE320F003),
    "sev (v6K)": (0xFFFFFFFF, 0xE320F004),
    "pld": (0xFD70F000, 0xF550F000),
    "rev": (0x0FFF0FF0, 0x06BF0F30),
    "uxtb/uxth/sxtb/sxth": (0x0F8F03F0, 0x068F0070),
    "smulxy": (0x0FF00090, 0x01600080),
    "umull/smull": (0x0F8000F0, 0x00800090),
    "vfp_cdp_single (cp10)": (0x0F000F10, 0x0E000A00),
    "vfp_cdp_double (cp11)": (0x0F000F10, 0x0E000B00),
    "vfp_ldst_single": (0x0E000F00, 0x0C000A00),
    "vfp_ldst_double": (0x0E000F00, 0x0C000B00),
    "vmrs_apsr_fpscr (fmstat)": (0x0FFFFFFF, 0x0EF1FA10),
    "mrc_p15_tls (c13,c0,3)": (0x0FFF0FFF, 0x0E1D0F70),
    "mcr_mrc_p15_any": (0x0F000F10, 0x0E000F10),
}


def code_stats():
    cnt = collections.Counter()
    svc = collections.Counter()
    svc_sites = collections.defaultdict(list)
    blt = collections.Counter()
    ldrex_ext = collections.Counter()
    for i, w in enumerate(TW):
        va = TEXT_VA + i * 4
        if MODES[i * 4 // CHUNK] != "arm":
            continue
        for k, (m, v) in PATTERNS.items():
            if (w & m) == v:
                cnt[k] += 1
        if (w & 0xFF000000) == 0xEF000000:
            n = w & 0xFFFFFF
            if n < 0x100:
                svc[n] += 1
                svc_sites[n].append(va)
        if (w & 0x0F000000) == 0x0B000000 and (w >> 28) != 0xF:
            off = w & 0xFFFFFF
            if off & 0x800000:
                off -= 0x1000000
            t = va + 8 + off * 4
            if in_text(t):
                blt[t] += 1
        if (w & 0x0F800FFF) == 0x01800F9F and (w & 0x00100000):
            ldrex_ext[{0: "ldrex", 1: "ldrexd", 2: "ldrexb", 3: "ldrexh"}[(w >> 21) & 3]] += 1
    cnt.pop("ldrexb/h/d (v6K)", None)
    # thumb-specific
    thumb = collections.Counter()
    hs = struct.unpack_from("<%dH" % (len(TEXT) // 2), TEXT, 0)
    for i, h in enumerate(hs):
        if MODES[i * 2 // CHUNK] != "thumb":
            continue
        if (h & 0xFF00) == 0xB500:
            thumb["push_lr"] += 1
        if (h & 0xFF00) == 0xBD00:
            thumb["pop_pc"] += 1
        if h == 0x4770:
            thumb["bx_lr"] += 1
        if h == 0x4778 and i + 1 < len(hs) and hs[i + 1] == 0x46C0:
            thumb["bx_pc_nop_veneer"] += 1
    return cnt, svc, svc_sites, blt, ldrex_ext, thumb


CNT, SVC, SVC_SITES, BL_TARGETS, LDREX_EXT, THUMB = code_stats()


def func_features(va, maxw=64):
    """Crude features of a function body for identifying runtime helpers."""
    feats = collections.Counter()
    words = []
    for k in range(maxw):
        w = u32(va + 4 * k)
        if w is None:
            break
        words.append(w)
        if (w & 0x0FFF0FF0) == 0x016F0F10:
            feats["clz"] += 1
        if (w & 0x0FE00000) == 0x00A00000 or (w & 0x0FE00000) == 0x02A00000:
            feats["adc"] += 1
        if (w & 0x0FE00000) == 0x00400000 or (w & 0x0FE00000) == 0x02400000:
            feats["sub"] += 1
        if (w & 0x0E100000) == 0x08100000 and (w & 0x0E000000) == 0x08000000:
            feats["ldm"] += 1
        if (w & 0x0E100000) == 0x08000000:
            feats["stm"] += 1
        if (w & 0x0F000F10) == 0x0E000A00 or (w & 0x0F000F10) == 0x0E000B00:
            feats["vfp"] += 1
        if (w & 0x0FFFFFF0) == 0x012FFF10:
            feats["bx"] += 1
            break
        if (w & 0xFFFF8000) == 0xE8BD8000:
            feats["ret_ldm"] += 1
            break
    return words, feats


# ----------------------------------------------------------------------------
# 6. ARM EH tables (.ARM.exidx) and init_array detection
# ----------------------------------------------------------------------------
def prel31(word, at):
    off = word & 0x7FFFFFFF
    if off & 0x40000000:
        off -= 0x80000000
    return (at + off) & 0xFFFFFFFF


def find_exidx():
    best = []
    for seg in ("rodata", "data", "text"):
        a, sz, off = SEGS[seg]
        n = sz // 4
        ws = struct.unpack_from("<%dI" % n, CODE, off)
        i = 0
        while i + 1 < n:
            run = 0
            last = -1
            j = i
            while j + 1 < n:
                w0, w1 = ws[j], ws[j + 1]
                if w0 & 0x80000000:
                    break
                t = prel31(w0, a + j * 4)
                if not in_text(t) or t <= last:
                    break
                if not (w1 == 1 or (w1 & 0x80000000) or seg_of_va(prel31(w1, a + j * 4 + 4)) in ("rodata", "data", "text")):
                    break
                last = t
                run += 1
                j += 2
            if run >= 16:
                best.append({"segment": seg, "start": a + i * 4, "entries": run,
                             "first_fn": prel31(ws[i], a + i * 4), "last_fn": last})
                i = j
            else:
                i += 1
    return best


EXIDX = find_exidx()


def find_ptr_runs(minrun=8):
    """Runs of absolute pointers into .text (vtables excluded) and relative (init_array-ish) runs."""
    runs_abs, runs_rel = [], []
    vt_words = set()
    for v in VTABLES:
        for k in range(len(v["vfuncs"]) + 2):
            vt_words.add(v["addr"] + 4 * k)
    for seg in ("rodata", "data"):
        a, sz, off = SEGS[seg]
        n = sz // 4
        ws = struct.unpack_from("<%dI" % n, CODE, off)
        i = 0
        while i < n:
            j = i
            while j < n and in_text(ws[j] & ~1) and (a + 4 * j) not in vt_words:
                j += 1
            if j - i >= minrun:
                runs_abs.append((a + 4 * i, j - i))
            i = max(j, i + 1)
        # relative (RVCT .init_array uses offsets relative to the entry)
        i = 0
        while i < n:
            j = i
            while j < n and ws[j] != 0 and in_text((a + 4 * j + ws[j]) & 0xFFFFFFFF) and not in_text(ws[j]):
                j += 1
            if j - i >= 4:
                runs_rel.append((a + 4 * i, j - i))
            i = max(j, i + 1)
    return runs_abs, runs_rel


PTR_RUNS_ABS, PTR_RUNS_REL = find_ptr_runs()

# ----------------------------------------------------------------------------
# 7. Library fingerprints from strings
# ----------------------------------------------------------------------------
NEX_PAT = (r"Duplica|ElectNewMaster|ConfirmElection|DeclinePromotion|SynchronizeTermination|"
           r"RequestIDRangeFromMaster|SignalAsFaulty|RetrieveURLs|^Sync(Request|Response)$|"
           r"^(Set|Reset)SyncCount$|^SetAnswer$")
EC_PAT = (r"ContentInfoArchive|MetaDataContentHeader|PricingSelection|PURCHASABLE|^TitleVersion$|"
          r"sys\.ItemCode|/icons/%u\.icn")
ZLIB_PAT = (r"need dictionary|stream end|file error|stream error|data error|insufficient memory|buffer error|"
            r"incompatible version|incorrect (header|data|length) check|"
            r"invalid (block type|window size|distance|stored block|code lengths|bit length|literal)|"
            r"unknown compression method|unknown header flags set|header crc mismatch|"
            r"too many length or distance symbols")

LIB_RULES = [
    # (library, regex over string)
    ("CTR-SDK srv service name", re.compile(r"^(?:[a-z]{2,5}:[A-Za-z]{1,5}|[a-z]{2,5}::[A-Za-z]{2,5}|APT:[AUS]|\$hio\w+|\$hostio\d)$")),
    ("CTR-SDK nn::gr / DMP GL shader uniforms (dmp_*)", re.compile(r"^dmp_\w")),
    ("zlib (z_errmsg + inflate messages)", re.compile(ZLIB_PAT)),
    ("C++ runtime / std library messages", re.compile(r"(bad_alloc|unexpected exception|unknown exception|runtime error|underflow error|overflow error|range error|invalid argument|length error|out of range|domain error|locale|bad_cast|bad_typeid|logic error|Exception: )")),
    ("Local-play (UDS) networking wrapper (Uds*)", re.compile(r"\bUds[A-Z]\w*")),
    ("RTTI: __cxxabiv1 / std typeinfo", re.compile(r"^(N10__cxxabiv1|St\d)")),
    ("NintendoWare-style resource formats", re.compile(r"\.(bcres|bcmdl|bctex|bclim|bcfnt|bcsar|bcstm|bcwav|bcenv|bcptl|bcmata|bcskla|bcmcla)\b", re.I)),
    ("CTR texture package / Intelligent Systems formats", re.compile(r"\.(ctpk|bch|arc|lz|bin\.lz|cgfx)\b", re.I)),
    ("CRI middleware", re.compile(r"\bCRI[A-Z_]|criware|\.acb\b|\.awb\b|\.usm\b|\.cpk\b", re.I)),
    ("Havok", re.compile(r"\bhk[A-Z][a-z]|Havok", re.I)),
    ("NEX / Pia / online", re.compile(r"\b(nex|pia|NEX|Pia|QuazalOnline|Rendez[vV]ous)\b")),
    ("NEX (Quazal Net-Z / Rendez-Vous) RMC/DO method names", re.compile(NEX_PAT)),
    ("NintendoWare for CTR (NW4C) gfx", re.compile(r"nwgfx|nw4c|NW4C|nw::")),
    ("nn::ec / eShop DLC metadata", re.compile(EC_PAT)),
    ("ARM C library printf/strtod tokens", re.compile(r"^(INFINITY|INF|NAN|nan|inf|infinity)$")),
    ("SDK version tag", re.compile(r"\[SDK\+|SDK_|CTR_SDK|NW4C|NintendoWare|CTR-SDK")),
    ("Source-file names (__FILE__-like)", re.compile(r"[\w/\\.-]+\.(cpp|cc|cxx|c|h|hpp|inl|s)$", re.I)),
    ("Absolute / build paths", re.compile(r"^[A-Za-z]:[\\/]|/home/|/Users/|\\\\Project|/cygdrive/|\\\\proj", re.I)),
    ("Assert / panic text", re.compile(r"(assert|ASSERT|panic|PANIC|Failed|failed|halt|HALT)")),
]


def lib_fingerprints():
    hits = collections.defaultdict(list)
    for va, seg, s in STRINGS:
        for lib, rx in LIB_RULES:
            if rx.search(s):
                hits[lib].append((va, seg, s))
    return hits


LIB_HITS = lib_fingerprints()

VERSION_RE = re.compile(r"(?<![\d.])\d{1,2}\.\d{1,2}(?:\.\d{1,3})?(?:[a-z])?(?![\d.])")
VERSIONS = [(va, seg, s) for va, seg, s in STRINGS if VERSION_RE.search(s) and len(s) < 80]
VERSIONS += [(va, seg, s) for va, seg, s in U16 if VERSION_RE.search(s) and len(s) < 80]
# also short tokens the ASCII scanner drops (fewer than 3 letters), e.g. "1.2.3"
for m in re.finditer(rb"(?<=\x00)(\d{1,2}\.\d{1,2}\.\d{1,3})\x00", CODE):
    va = off2va(m.start())
    if va is not None:
        VERSIONS.append((va, seg_of_va(va), m.group(1).decode()))

# ----------------------------------------------------------------------------
# 8. Game vs SDK classification of string references -> .text partition
# ----------------------------------------------------------------------------
GAME_RX = re.compile(r"(^(SE|STRM|EFF|PID|IID|JID|MID|CID|MCID|SID|MPID|GID|BID|PLAYER)_)|Proc[A-Z]|Seq\b|Seq[A-Z]|Menu|Unit|Map|Battle|Sortie|Chapter|Dual|Face|Event|"
                     r"\.(ctpk|bch|arc|lz|bin)\b|^data/|^m/|SAVE_|MEC_|debug|Debug|%s")
SDK_RX = re.compile(r"^(dmp_|APT:|\$h)|^[a-z]{2,5}:{1,2}[A-Za-z]{1,5}$|Uds[A-Z]|need dictionary|stream error|insufficient memory|buffer error|"
                    r"bad_alloc|unexpected exception|unknown exception|runtime error|underflow error|overflow error|locale|^%s: |"
                    r"nwgfx|^INFINITY$|pia (local|common) heap|" + NEX_PAT + "|" + EC_PAT + "|" + ZLIB_PAT)


def classify_string(s):
    if SDK_RX.search(s):
        return "sdk"
    if GAME_RX.search(s):
        return "game"
    return None


def build_adr_index():
    """ADR (ADD/SUB Rd, PC, #imm) targets -> sites. armcc addresses strings that it
    placed next to the function with ADR rather than through a literal-pool word."""
    idx = collections.defaultdict(list)
    for i, w in enumerate(TW):
        op = w & 0x0FFF0000
        if op not in (0x028F0000, 0x024F0000):
            continue
        rot = ((w >> 8) & 0xF) * 2
        imm = w & 0xFF
        imm = ((imm >> rot) | (imm << (32 - rot))) & 0xFFFFFFFF if rot else imm
        pc = TEXT_VA + 4 * i + 8
        t = (pc + imm) if op == 0x028F0000 else (pc - imm)
        idx[t & 0xFFFFFFFF].append(TEXT_VA + 4 * i)
    return idx


ADR_IDX = build_adr_index()


def xref_partition(bucket=0x10000):
    b = collections.defaultdict(lambda: collections.Counter())
    detail = []
    stats = collections.Counter()
    for va, seg, s in STRINGS:
        refs_pool = WIDX_TEXT.get(va, [])
        refs_adr = ADR_IDX.get(va, [])
        stats["%s_pool" % seg] += bool(refs_pool)
        stats["%s_adr" % seg] += bool(refs_adr)
        stats["%s_unref" % seg] += not (refs_pool or refs_adr)
        c = classify_string(s)
        if not c:
            continue
        for r in refs_pool + refs_adr:
            b[(r - TEXT_VA) // bucket][c] += 1
            detail.append((r, c, s))
    return b, detail, stats


XB, XDETAIL, XSTATS = xref_partition()

# ----------------------------------------------------------------------------
# 9. Exheader (services, kernel version) for cross-checking
# ----------------------------------------------------------------------------
def exheader():
    p = os.path.join(EXT, "exheader.bin")
    if not os.path.exists(p):
        return {}
    d = open(p, "rb").read()
    services = []
    for i in range(0x250, 0x250 + 34 * 8, 8):
        s = d[i:i + 8].rstrip(b"\0")
        if s:
            services.append(s.decode("latin-1"))
    kver = None
    for i in range(0x370, 0x370 + 28 * 4, 4):
        w = struct.unpack_from("<I", d, i)[0]
        if (w & 0xFE000000) == 0xFC000000:
            kver = "%d.%d" % ((w >> 8) & 0xFF, w & 0xFF)
    return {"services": services, "kernel_version_descriptor": kver,
            "app_title": d[0:8].rstrip(b"\0").decode("latin-1")}


EXH = exheader()

# ----------------------------------------------------------------------------
# Aggregate RTTI
# ----------------------------------------------------------------------------
def rtti_summary():
    ns_counter = collections.Counter()
    top_counter = collections.Counter()
    kinds = collections.Counter(t["kind"] for t in TIS.values())
    vt_by_ti = collections.defaultdict(list)
    for v in VTABLES:
        vt_by_ti[v["typeinfo"]].append(v)
    rows = []
    for tia in sorted(TIS):
        t = TIS[tia]
        name = t["name"]
        parts = name.split("::")
        ns = "::".join(parts[:-1]) if len(parts) > 1 else "(global)"
        if ns.startswith("_GLOBAL__N__"):
            m = ANON_RE.match(ns.split("::")[0])
            ns_disp = "(anon:%s.%s)" % (m.group(1), m.group(2)) if m else "(anon)"
            top = "(anonymous namespaces)"
            if m:
                key = m.group(1) + "." + m.group(2)
                if key in SRCFILES:
                    SRCFILES[key]["classes"].add(name)
        else:
            ns_disp = ns
            top = parts[0] if len(parts) > 1 else "(global)"
        ns_counter[ns_disp] += 1
        top_counter[top] += 1
        vts = vt_by_ti.get(tia, [])
        funcs = sorted(f & ~1 for v in vts for f in v.get("own", []))
        rows.append({
            "typeinfo": "0x%08X" % tia, "kind": t["kind"], "mangled": t["mangled"], "name": name,
            "bases": ";".join(TIS[b]["name"] if b in TIS else ("0x%08X" % b if b else "?") for b in t["bases"]),
            "vtables": ";".join("0x%08X" % v["addr"] for v in vts),
            "n_vfuncs": sum(len(v["vfuncs"]) for v in vts),
            "n_own_vfuncs": len(funcs),
            "own_vfunc_min": "0x%08X" % funcs[0] if funcs else "",
            "own_vfunc_median": "0x%08X" % funcs[len(funcs) // 2] if funcs else "",
            "own_vfunc_max": "0x%08X" % funcs[-1] if funcs else "",
        })
    return ns_counter, top_counter, kinds, rows


NS_COUNTER, TOP_COUNTER, KIND_COUNTER, RTTI_ROWS = rtti_summary()


def srcfile_ranges():
    rows = []
    name2row = {r["name"]: r for r in RTTI_ROWS}
    for key, e in SRCFILES.items():
        mins, maxs, meds = [], [], []
        for c in e["classes"]:
            r = name2row.get(c)
            if r and r["own_vfunc_min"]:
                mins.append(int(r["own_vfunc_min"], 16))
                maxs.append(int(r["own_vfunc_max"], 16))
                meds.append(int(r["own_vfunc_median"], 16))
        meds.sort()
        rows.append({"file": key, "anon_hash": ";".join(sorted(e["hash"])), "n_classes": len(e["classes"]),
                     "own_vfunc_min": "0x%08X" % min(mins) if mins else "",
                     "own_vfunc_median": "0x%08X" % meds[len(meds) // 2] if meds else "",
                     "own_vfunc_max": "0x%08X" % max(maxs) if maxs else ""})
    rows.sort(key=lambda r: r["own_vfunc_median"] or "z")
    return rows


SRC_ROWS = srcfile_ranges()

# ----------------------------------------------------------------------------
# Game/SDK boundary estimate from vtables: which text ranges hold vfuncs of
# game classes vs runtime classes, and where SVC stubs and SDK string refs are.
# ----------------------------------------------------------------------------
def boundary_estimate():
    game_vf, rt_vf = [], []
    for v in VTABLES:
        t = TIS[v["typeinfo"]]
        target = rt_vf if (t["name"].startswith("__cxxabiv1") or t["name"].startswith("std::")) else game_vf
        target.extend(f & ~1 for f in v.get("own", []))
    svc_va = sorted(va for vs in SVC_SITES.values() for va in vs)
    sdk_refs = sorted(r for r, c, s in XDETAIL if c == "sdk")
    game_refs = sorted(r for r, c, s in XDETAIL if c == "game")

    def pct(xs, q):
        if not xs:
            return None
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(q * len(xs)))]

    return {
        "game_class_vfuncs": {"n": len(game_vf), "min": pct(game_vf, 0), "p01": pct(game_vf, 0.01),
                              "p99": pct(game_vf, 0.99), "max": pct(game_vf, 1)},
        "runtime_class_vfuncs": {"n": len(rt_vf), "min": pct(rt_vf, 0), "max": pct(rt_vf, 1)},
        "svc_sites": {"n": len(svc_va), "min": pct(svc_va, 0), "p05": pct(svc_va, 0.05),
                      "median": pct(svc_va, 0.5), "max": pct(svc_va, 1)},
        "sdk_string_refs": {"n": len(sdk_refs), "min": pct(sdk_refs, 0), "p10": pct(sdk_refs, 0.1),
                            "median": pct(sdk_refs, 0.5), "max": pct(sdk_refs, 1)},
        "game_string_refs": {"n": len(game_refs), "min": pct(game_refs, 0), "p90": pct(game_refs, 0.9),
                             "p99": pct(game_refs, 0.99), "max": pct(game_refs, 1)},
    }


BOUND = boundary_estimate()


# Thumb/ARM/data chunk totals
def mode_totals():
    c = collections.Counter(MODES)
    return {k: {"chunks": v, "bytes": v * CHUNK, "pct": round(100.0 * v / len(MODES), 2)} for k, v in c.items()}


MODE_TOT = mode_totals()


# Find where data (non-code) chunks cluster at the end of .text (literal-only tail?)
def mode_runs():
    runs = []
    cur, start = None, 0
    for i, m in enumerate(MODES):
        if m != cur:
            if cur is not None:
                runs.append((cur, TEXT_VA + start * CHUNK, (i - start) * CHUNK))
            cur, start = m, i
    runs.append((cur, TEXT_VA + start * CHUNK, (len(MODES) - start) * CHUNK))
    return [r for r in runs if r[0] != "arm" and r[2] >= 4096]


MODE_RUNS = mode_runs()


# ----------------------------------------------------------------------------
# Per-64KB bucket features and a coarse SDK/game region guess
# ----------------------------------------------------------------------------
def bucket_rows(bsz=0x10000):
    nb = (TEXT_SZ + bsz - 1) // bsz
    feat = collections.defaultdict(collections.Counter)
    for i, w in enumerate(TW):
        b = (4 * i) // bsz
        if (w & 0xFF000000) == 0xEF000000 and (w & 0xFFFFFF) < 0x80:
            feat[b]["svc"] += 1
        elif (w & 0x0FFF0FFF) == 0x0E1D0F70:
            feat[b]["tls"] += 1
        elif w == 0xE1A0F00E:
            feat[b]["movpc"] += 1
        elif w == 0xE320F000:
            feat[b]["nop"] += 1
        elif (w & 0x0F000E10) == 0x0E000A00:
            feat[b]["vfp"] += 1
    for v in VTABLES:
        if not TIS[v["typeinfo"]]["name"].startswith(("__cxxabiv1", "std")):
            for fn in v.get("own", []):
                feat[((fn & ~1) - TEXT_VA) // bsz]["gvf"] += 1
    rows = []
    for b in range(nb):
        ms = collections.Counter(MODES[b * (bsz // CHUNK):(b + 1) * (bsz // CHUNK)])
        f = feat[b]
        g, sd = XB[b]["game"], XB[b]["sdk"]
        game_score = g + f["gvf"]
        sdk_score = 4 * f["svc"] + 2 * f["tls"] + 4 * sd + f["movpc"]
        if game_score == 0 and sdk_score == 0:
            guess = "unknown"
        elif sdk_score > 2 * game_score:
            guess = "sdk/lib"
        elif game_score > 2 * sdk_score:
            guess = "game"
        else:
            guess = "mixed"
        rows.append(["0x%08X" % (TEXT_VA + b * bsz), g, sd, ms["arm"], ms["thumb"], ms["data"],
                     f["svc"], f["tls"], f["movpc"], f["nop"], f["vfp"], f["gvf"], guess])
    return rows


BUCKET_ROWS = bucket_rows()
REGION_GUESS = collections.Counter(r[-1] for r in BUCKET_ROWS)


def nop_context():
    prev, nxt = collections.Counter(), collections.Counter()

    def cls(x):
        if (x & 0x0F000000) == 0x0B000000 and (x >> 28) != 0xF:
            return "BL"
        if (x & 0x0F000000) == 0x0A000000 and (x >> 28) != 0xF:
            return "B" if (x >> 28) == 0xE else "Bcond"
        if (x & 0x0DF00000) in (0x01500000, 0x01700000):
            return "CMP/CMN"
        if x == 0xE320F000:
            return "NOP"
        if (x & 0x0C000000) == 0x04000000:
            return "LDR/STR"
        return "other"
    total = 0
    for i, w in enumerate(TW[1:-1], 1):
        if w == 0xE320F000:
            total += 1
            prev[cls(TW[i - 1])] += 1
            nxt[cls(TW[i + 1])] += 1
    return {"total": total, "prev": dict(prev.most_common()), "next": dict(nxt.most_common())}


NOP_CTX = nop_context()


def find_div_helpers():
    """Unrolled shift-subtract division: runs of RSBS rX,r1,r0,LSR #k (RVCT/ARM rt_udiv style)."""
    hits = [i for i, w in enumerate(TW) if (w & 0x0FF00070) == 0x00700020]
    res = []
    i = 0
    while i < len(hits):
        j = i
        while j + 1 < len(hits) and hits[j + 1] - hits[j] <= 4:
            j += 1
        if j - i + 1 >= 8:
            start = TEXT_VA + 4 * hits[i]
            # walk back to the nearest BL-target (function entry) within 0x80 bytes
            entry = None
            for back in range(0, 0x80, 4):
                if BL_TARGETS.get(start - back):
                    entry = start - back
                    break
            res.append({"first_rsbs": "0x%08X" % start, "rsbs_count": j - i + 1,
                        "entry_guess": "0x%08X" % entry if entry else None,
                        "bl_calls_to_entry": BL_TARGETS.get(entry, 0) if entry else 0})
        i = j + 1
    return res


DIV_HELPERS = find_div_helpers()


def lib_xref_ranges():
    """Where in .text is each string-identified library referenced from?"""
    out = {}
    for lib, hs in LIB_HITS.items():
        sites = []
        for va, seg, s in hs:
            sites += WIDX_TEXT.get(va, []) + ADR_IDX.get(va, [])
        # strings that live in .text themselves sit right after their function
        inline = [va for va, seg, s in hs if seg == "text"]
        sites = sorted(set(sites))
        b = collections.Counter("0x%08X" % (TEXT_VA + ((x - TEXT_VA) // 0x10000) * 0x10000) for x in sites)
        out[lib] = {"ref_sites": len(sites), "min": "0x%08X" % sites[0] if sites else None,
                    "max": "0x%08X" % sites[-1] if sites else None, "by_64KB": dict(sorted(b.items())),
                    "inline_text_strings": len(inline)}
    return out


LIB_XREFS = lib_xref_ranges()

# ----------------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------------
os.makedirs(OUT, exist_ok=True)


def hx(v):
    return None if v is None else "0x%08X" % v


def hxd(d):
    return {k: (hx(v) if isinstance(v, int) and k != "n" else v) for k, v in d.items()}


top_bl = []
for t, n in BL_TARGETS.most_common(25):
    words, feats = func_features(t)
    top_bl.append({"target": hx(t), "calls": n, "first_words": " ".join("%08X" % w for w in words[:8]),
                   "len_words_scanned": len(words), "features": dict(feats)})

lib_summary = {}
for lib, hs in LIB_HITS.items():
    uniq = sorted(set(s for _, _, s in hs))
    lib_summary[lib] = {"count": len(hs), "unique": len(uniq),
                        "segments": dict(collections.Counter(seg for _, seg, _ in hs)),
                        "first_addr": hx(min(va for va, _, _ in hs)), "last_addr": hx(max(va for va, _, _ in hs)),
                        "examples": uniq[:40]}

result = {
    "input": {"code_bin": os.path.join(EXT, "code.bin"), "size": len(CODE),
              "segments": {k: {"va": hx(a), "size": sz, "file_off": off} for k, (a, sz, off) in SEGS.items()}},
    "strings": {"ascii_total": len(STRINGS),
                "ascii_by_segment": dict(collections.Counter(seg for _, seg, _ in STRINGS)),
                "utf16_total": len(U16),
                "utf16_by_segment": dict(collections.Counter(seg for _, seg, _ in U16))},
    "rtti": {
        "mangled_name_strings": len(MANGLED_CANDS),
        "typeinfo_objects": len(TIS),
        "typeinfo_vptrs": {hx(v): k for v, k in TI_KINDS.items()},
        "by_kind": dict(KIND_COUNTER),
        "vtables": len(VTABLES),
        "vtables_secondary (offset_to_top<0)": sum(1 for v in VTABLES if v["offset_to_top"] < 0),
        "vfunc_slots_total": sum(len(v["vfuncs"]) for v in VTABLES),
        "typeinfo_addr_range": [hx(min(TIS)), hx(max(TIS))] if TIS else None,
        "vtable_addr_range": [hx(min(v["addr"] for v in VTABLES)), hx(max(v["addr"] for v in VTABLES))] if VTABLES else None,
        "top_level_namespace_counts": dict(TOP_COUNTER.most_common()),
        "namespace_counts_top60": dict(NS_COUNTER.most_common(60)),
        "runtime_typeinfos": sorted(t["name"] for t in TIS.values()
                                    if t["name"].startswith("__cxxabiv1") or t["name"].startswith("std")),
        "non_typeinfo_mangled_strings_examples": sorted(set(s for va, (s, dm) in MANGLED_CANDS.items()
                                                            if not WIDX_ROD.get(va)))[:30],
    },
    "source_files_from_anon_namespaces": {"count": len(SRCFILES),
                                         "distinct_hashes": len(set(h for e in SRCFILES.values() for h in e["hash"])),
                                         "files": [r["file"] for r in SRC_ROWS]},
    "code": {
        "chunk_size": CHUNK,
        "mode_totals": MODE_TOT,
        "non_arm_runs_ge_4KB": [{"mode": m, "va": hx(a), "size": s} for m, a, s in MODE_RUNS],
        "arm_pattern_counts": dict(CNT),
        "ldrex_variants": dict(LDREX_EXT),
        "thumb_pattern_counts": dict(THUMB),
        "svc_histogram": {"0x%02X" % k: v for k, v in sorted(SVC.items())},
        "svc_distinct": len(SVC),
        "bl_distinct_targets": len(BL_TARGETS),
        "bl_top25": top_bl,
        "nop_v6k_context": NOP_CTX,
        "division_helpers": DIV_HELPERS,
    },
    "string_xref_stats": dict(XSTATS),
    "region_guess_64KB_buckets": dict(REGION_GUESS),
    "eh_tables_exidx_like": [{**e, "start": hx(e["start"]), "first_fn": hx(e["first_fn"]), "last_fn": hx(e["last_fn"])} for e in EXIDX],
    "pointer_runs": {
        "abs_text_ptr_runs_ge8_nonvtable": len(PTR_RUNS_ABS),
        "abs_longest": [(hx(a), n) for a, n in sorted(PTR_RUNS_ABS, key=lambda x: -x[1])[:10]],
        "rel_text_offset_runs_ge4 (init_array-like)": [(hx(a), n) for a, n in sorted(PTR_RUNS_REL, key=lambda x: -x[1])[:10]],
    },
    "libraries_from_strings": lib_summary,
    "library_xref_ranges": LIB_XREFS,
    "version_like_strings": sorted(set((hx(va), seg, s) for va, seg, s in VERSIONS))[:60],
    "exheader": EXH,
    "boundary": {k: hxd(v) for k, v in BOUND.items()},
}

with open(os.path.join(OUT, "fingerprint.json"), "w", encoding="utf-8") as f:
    json.dump(result, f, indent=1)

with open(os.path.join(OUT, "rtti_classes.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(RTTI_ROWS[0].keys()) if RTTI_ROWS else ["typeinfo"])
    w.writeheader()
    w.writerows(RTTI_ROWS)

with open(os.path.join(OUT, "rtti_source_files.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["file", "anon_hash", "n_classes", "own_vfunc_min", "own_vfunc_median", "own_vfunc_max"])
    w.writeheader()
    w.writerows(SRC_ROWS)

with open(os.path.join(OUT, "string_xref_buckets.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    keys = ["game", "sdk"]
    w.writerow(["bucket_va", "game_str_refs", "sdk_str_refs", "arm_chunks", "thumb_chunks", "data_chunks",
                "svc_sites", "tls_mrc", "mov_pc_lr", "nop_v6k", "vfp_cdp", "game_own_vfuncs", "region_guess"])
    for row in BUCKET_ROWS:
        w.writerow(row)

# text report
L = []
P_ = L.append
P_("%s (%s) toolchain fingerprint" % (LAYOUT.get("app_title", "?"), LAYOUT.get("product_code", "?")))
P_("=" * 60)
P_("strings: ascii=%d %s  utf16=%d %s" % (len(STRINGS), dict(collections.Counter(s for _, s, _ in STRINGS)),
                                         len(U16), dict(collections.Counter(s for _, s, _ in U16))))
P_("")
P_("[RTTI]")
P_("  mangled type-name strings: %d; typeinfo objects: %d; kinds: %s" % (len(MANGLED_CANDS), len(TIS), dict(KIND_COUNTER)))
P_("  typeinfo vptrs: %s" % {hx(v): k for v, k in TI_KINDS.items()})
P_("  vtables: %d (secondary %d), vfunc slots %d" % (len(VTABLES), sum(1 for v in VTABLES if v["offset_to_top"] < 0),
                                                     sum(len(v["vfuncs"]) for v in VTABLES)))
P_("  top-level namespaces: %s" % dict(TOP_COUNTER.most_common(30)))
P_("  runtime typeinfos: %s" % result["rtti"]["runtime_typeinfos"])
P_("  source files from EDG anon namespaces: %d (distinct hashes %d)" % (len(SRCFILES), result["source_files_from_anon_namespaces"]["distinct_hashes"]))
for r in SRC_ROWS:
    P_("    %-24s classes=%-3d own vfuncs %s..%s (median %s) hash=%s" % (r["file"], r["n_classes"], r["own_vfunc_min"], r["own_vfunc_max"], r["own_vfunc_median"], r["anon_hash"]))
P_("")
P_("[Code]")
P_("  mode totals (256B chunks): %s" % MODE_TOT)
P_("  non-ARM runs >=4KB: %s" % [(m, hx(a), s) for m, a, s in MODE_RUNS])
for k, v in sorted(CNT.items(), key=lambda x: -x[1]):
    P_("  %-40s %d" % (k, v))
P_("  ldrex variants: %s" % dict(LDREX_EXT))
P_("  thumb: %s" % dict(THUMB))
P_("  SVC histogram: %s" % {"0x%02X" % k: v for k, v in sorted(SVC.items())})
P_("  BL distinct targets: %d. Top 25:" % len(BL_TARGETS))
for e in top_bl:
    P_("    %s calls=%-5d %s feats=%s" % (e["target"], e["calls"], e["first_words"], e["features"]))
P_("  NOP context: %s" % NOP_CTX)
P_("  division helpers: %s" % DIV_HELPERS)
P_("  string xref stats (strings with >=1 literal-pool / ADR ref, or none): %s" % dict(XSTATS))
P_("  64KB region guesses: %s" % dict(REGION_GUESS))
P_("")
P_("[EH tables (.ARM.exidx-like)] %s" % result["eh_tables_exidx_like"])
P_("[pointer runs] %s" % result["pointer_runs"])
P_("")
P_("[Libraries from strings]")
for lib, s in lib_summary.items():
    P_("  %s: count=%d unique=%d seg=%s range=%s..%s" % (lib, s["count"], s["unique"], s["segments"], s["first_addr"], s["last_addr"]))
    P_("     e.g. %s" % s["examples"][:12])
    P_("     referenced from: %s" % LIB_XREFS.get(lib))
P_("")
P_("[version-like strings] %s" % result["version_like_strings"][:30])
P_("[exheader] %s" % EXH)
P_("")
P_("[boundary estimate]")
for k, v in result["boundary"].items():
    P_("  %s: %s" % (k, v))
with open(os.path.join(OUT, "fingerprint_report.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(L) + "\n")
print("\n".join(L))
