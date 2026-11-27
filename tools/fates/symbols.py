#!/usr/bin/env python3
"""Function registry for Fire Emblem Fates from the symbol map shipped in the RomFS.

The Fates RomFS carries a debug symbol map (romfs/debug/, paths in config/game.json
"romfs.symbol_map"):

    name.StackTrace   NUL-separated demangled C++ names, in address order
    addr.StackTrace   (u32 address, u32 byte offset into name.StackTrace) pairs, ending
                      with a (0, 0) terminator; addresses are ascending

This tool parses the map, merges it with the function starts found by
tools/analysis/funcmap.py (extracted/analysis/functions.csv) and writes the single
function registry every other tool reads:

    config/functions.csv   addr,end,size,name,class,library,source,kind,confidence,mode,
                           library_by,signature,aliases
        addr/end/size  start, next start (end of .text for the last one), end - addr.
                       The map has no sizes, so size = distance to the next start of
                       the merged list (symbol starts + the funcmap-only starts that
                       pass vet_starts, + starts vet_starts finds itself).
        name           assembler-safe, unique symbol made from the demangled name
                       (`nn::fs::Foo(int)` -> `nn__fs__Foo`); overloads that collide
                       get an `_XXXXXXXX` address suffix. Unnamed starts: func_XXXXXXXX.
        class          enclosing scope of the name (class or namespace path), "" for
                       free C functions
        library        game, ctr_sdk, nex, pia, nw4c, live2d, molive, pead, rvct_clib,
                       cxx_runtime, zlib, crt0 or unknown (same tags as the Awakening
                       port; molive = Mobiclip mw::mo, ctr_sdk = nn::)
        source         symbol_map | funcmap:<tier> | flow | hand  (flow: found by
                       vet_starts: an uncovered BL/BLX target or code after a reached end)
        kind           func | ctor | dtor | operator | thunk | static_init | linker |
                       local | unnamed
        confidence     confidence that addr is a real function start: high for
                       symbol-map and hand rows, funcmap's tier otherwise
        mode           ARM | THUMB (addresses never carry the Thumb bit)
        library_by     name (tagged from the name itself) | neighbor (the nearest
                       name-tagged functions on both sides agree) | calls (vote of the
                       tagged callees, callers and neighbours) | file_name (static
                       initialisers: from the __sti___<n>_<file>_cpp name) | hand | none
        signature      the full demangled name from the map ("" for unnamed)
        aliases        other map names at the same address (identical-code folding),
                       joined with " | "
    build/symbols/symbols_report.txt   counts (libraries, reconcile, modes)

funcmap-only starts are not trusted inside a named function: vet_starts() walks the
named code with tools/fates/flow.py and drops starts that code reaches (false
'push' prologues after an 'ldr r0,=x', Thumb guesses inside ARM instructions or ADR'd
text) unless something calls them. See docs/SYMBOLS.md, "Function boundaries".

config/names.csv (hand names, columns addr,name[,library,class,note]) always wins.

Usage:
    python tools/fates/symbols.py              build config/functions.csv
    python tools/fates/symbols.py --funcmap    re-run tools/analysis/funcmap.py first
    python tools/fates/symbols.py --check      rebuild in memory, exit 1 if the
                                               tracked config/functions.csv differs
    python tools/fates/symbols.py --selftest   parser/classifier tests on synthetic data
"""
from __future__ import annotations

import argparse
import bisect
import csv
import io
import re
import struct
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from gamecfg import GAME  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))

EXT = ROOT / "extracted"
ROMFS = EXT / "romfs"
FUNCMAP_CSV = EXT / "analysis" / "functions.csv"
OUT_CSV = ROOT / "config" / "functions.csv"
NAMES_CSV = ROOT / "config" / "names.csv"
SCRATCH = ROOT / "build" / "symbols"
COLUMNS = ["addr", "end", "size", "name", "class", "library", "source", "kind", "confidence",
           "mode", "library_by", "signature", "aliases"]
LIBRARIES = ["game", "ctr_sdk", "nex", "pia", "nw4c", "live2d", "molive", "pead", "rvct_clib",
             "cxx_runtime", "zlib", "crt0", "unknown"]
MAX_NAME = 200


# ------------------------------------------------------------------ map parsing
@dataclass
class MapEntry:
    addr: int            # even; Thumb bit stripped
    thumb_bit: bool      # the map stored an odd address
    names: list = field(default_factory=list)


def parse_map(names: bytes, addrs: bytes) -> tuple[list[MapEntry], dict]:
    """Parse the two StackTrace files. Returns entries (one per distinct address, in
    address order, names in map order) and stats. Raises ValueError on a malformed map."""
    if len(addrs) % 8:
        raise ValueError(f"addr.StackTrace size {len(addrs)} is not a multiple of 8")
    pairs = list(struct.iter_unpack("<II", addrs))
    stats = {"pairs": len(pairs), "terminator": False}
    if pairs and pairs[-1][0] == 0:
        pairs.pop()
        stats["terminator"] = True
    starts = {0}
    starts.update(i + 1 for i, c in enumerate(names) if c == 0)
    out: list[MapEntry] = []
    last = -1
    for a, off in pairs:
        if off >= len(names) or off not in starts:
            raise ValueError(f"name offset {off:#x} for {a:#010x} is not the start of a string")
        end = names.index(b"\0", off) if b"\0" in names[off:] else len(names)
        nm = names[off:end].decode("latin-1")
        thumb = bool(a & 1)
        a &= ~1
        if a < last:
            raise ValueError(f"addresses not ascending at {a:#010x}")
        if out and out[-1].addr == a:
            out[-1].names.append(nm)
            out[-1].thumb_bit |= thumb
        else:
            out.append(MapEntry(a, thumb, [nm]))
        last = a
    stats["names"] = sum(len(e.names) for e in out)
    stats["addresses"] = len(out)
    stats["shared_addresses"] = sum(1 for e in out if len(e.names) > 1)
    stats["thumb_bit_set"] = sum(1 for e in out if e.thumb_bit)
    stats["halfword_aligned"] = sum(1 for e in out if e.addr & 2)
    return out, stats


def read_map() -> tuple[list[MapEntry], dict]:
    sm = GAME.romfs.symbol_map
    n, a = ROMFS / sm.names, ROMFS / sm.addrs
    if not n.is_file() or not a.is_file():
        sys.exit(f"symbol map not found ({n}, {a}); run python tools/extract_rom.py first")
    entries, stats = parse_map(n.read_bytes(), a.read_bytes())
    ts = n.parent / "TimeStamp.txt"
    stats["timestamp"] = ts.read_text(encoding="latin-1").strip() if ts.is_file() else ""
    return entries, stats


# ------------------------------------------------------------------ demangled-name parsing
QUAL_SUFFIXES = (" const", " volatile")


def split_signature(sig: str) -> tuple[str, str, str]:
    """'virtual A::B<int>::f(int,char) const' -> ('virtual ', 'A::B<int>::f', '(int,char) const').
    Names without a parameter list come back with params ''."""
    prefix = ""
    s = sig
    for p in ("virtual ",):
        if s.startswith(p):
            prefix, s = p, s[len(p):]
    tail = ""
    core = s
    for q in QUAL_SUFFIXES:
        while core.endswith(q):
            core = core[: -len(q)]
            tail = q + tail
    if not core.endswith(")"):
        return prefix, s, ""
    depth = 0
    for i in range(len(core) - 1, -1, -1):
        c = core[i]
        if c == ")":
            depth += 1
        elif c == "(":
            depth -= 1
            if depth == 0:
                qual = core[:i]          # 'A::operator()(int)': the last group is the list
                if not qual:
                    return prefix, s, ""
                return prefix, qual, core[i:] + tail
    return prefix, s, ""


def split_scope(qual: str) -> tuple[str, str]:
    """'nn::fs::File::Read' -> ('nn::fs::File', 'Read'); template arguments and operator
    names are not split ('A<B::C>::operator<' -> ('A<B::C>', 'operator<'))."""
    depth = 0
    last = -1
    i = 0
    n = len(qual)
    while i < n:
        if qual.startswith("operator", i) and (i == 0 or qual[i - 1] in ":~ ") and depth == 0:
            break                                   # rest is the operator name
        c = qual[i]
        if c in "<(":
            depth += 1
        elif c in ">)":
            depth -= 1
        elif c == ":" and depth == 0 and qual.startswith("::", i):
            last = i
            i += 2
            continue
        i += 1
    if last < 0:
        return "", qual
    return qual[:last], qual[last + 2:]


def strip_templates(s: str) -> str:
    out, depth = [], 0
    for c in s:
        if c == "<":
            depth += 1
        elif c == ">":
            depth -= 1
        elif depth == 0:
            out.append(c)
    return "".join(out)


OPS = {"==": "eq", "!=": "ne", "<=": "le", ">=": "ge", "<<=": "shl_assign", ">>=": "shr_assign",
       "<<": "shl", ">>": "shr", "<": "lt", ">": "gt", "()": "call", "[]": "index",
       "->*": "arrow_star", "->": "arrow", "++": "inc", "--": "dec", "+=": "add_assign",
       "-=": "sub_assign", "*=": "mul_assign", "/=": "div_assign", "%=": "mod_assign",
       "&=": "and_assign", "|=": "or_assign", "^=": "xor_assign", "&&": "land", "||": "lor",
       "+": "add", "-": "sub", "*": "mul", "/": "div", "%": "mod", "&": "and", "|": "or",
       "^": "xor", "~": "compl", "!": "not", "=": "assign", ",": "comma",
       "new[]": "new_array", "delete[]": "delete_array", "new": "new", "delete": "delete"}


def safe_part(s: str) -> str:
    m = re.match(r"^operator\s*(.*)$", s)
    if m:
        op = m.group(1).replace(" ", "")
        s = "operator_" + OPS.get(op, op)          # conversion: operator_unsignedlong
    s = s.replace("~", "dtor_")
    s = re.sub(r"[^A-Za-z0-9_]+$", "", s)          # 'copy<A*>' -> 'copy_A', not 'copy_A__'
    s = re.sub(r"[^A-Za-z0-9_]+", "_", s)
    return s


def asm_name(qual: str) -> str:
    """Assembler-safe symbol from a qualified name (no parameter list)."""
    parts = []
    scope, base = split_scope(qual)
    while True:
        parts.insert(0, safe_part(base))
        if not scope:
            break
        scope, base = split_scope(scope)
    s = "__".join(parts)
    s = re.sub(r"_{3,}", "__", s).strip("_")
    if not s:
        s = "anon"
    if s[0].isdigit():
        s = "sym_" + s
    return s


# ------------------------------------------------------------------ library tags
C_RUNTIME = {"abort", "fputc", "free", "malloc", "frexp", "catgets", "catopen", "_is_digit",
             "memcpy", "memset", "memmove", "memcmp", "strlen", "strcmp", "strncmp", "strcpy",
             "strncpy", "strchr", "strrchr", "strstr", "sprintf", "snprintf", "vsnprintf",
             "printf", "puts", "putchar", "fopen", "fclose", "fwrite", "fread", "exit",
             "atexit", "calloc", "realloc", "qsort", "bsearch", "strtol", "strtoul", "atoi",
             "wcslen", "wcscmp", "wcscpy", "mbstowcs", "wcstombs", "toupper", "tolower",
             "setlocale", "localeconv", "abs", "labs", "div", "ldiv", "rand", "srand"}
ZLIB = {"build_tree", "compress_block", "crc32_big", "crc32_little", "deflate", "deflateBound",
        "deflateEnd", "deflateInit2_", "deflateInit_", "deflateReset", "deflate_fast",
        "deflate_slow", "deflate_stored", "fill_window", "flush_pending", "adler32", "crc32",
        "inflate", "inflateEnd", "inflateInit2_", "inflateInit_", "inflateReset", "zcalloc",
        "zcfree", "_tr_init", "_tr_align", "_tr_flush_block", "_tr_stored_block", "longest_match",
        "gen_bitlen", "gen_codes", "pqdownheap", "scan_tree", "send_tree", "bi_flush",
        "bi_windup", "init_block", "lm_init", "putShortMSB", "read_buf", "send_all_trees",
        "build_bl_tree", "compare_code"}
CXX_RT_PREFIX = ("__cxa_", "__aeabi_vec", "__dynamic_cast", "__derived_to_base",
                 "derived_to_base_conversion", "find_base_class", "__ARM_common_get_typeid",
                 "__ARM_array_new", "__rt_eh_", "__rt_raise", "__gxx_", "__cxx_")
CLIB_PREFIX = ("__aeabi_", "x$fpl$", "CL$$", ".ARM.Collect$$", "__hardfp_", "__mathlib_",
               "__ARM_", "_sys_", "__rt_", ".text_udiv", "__support_", "locale$$", "_printf",
               "__printf", "_fp_", "__fp", "__ieee", "__scatterload", "__main", "__rt_entry",
               "_ll_", "__user_", "_sputc", "_fputc", "__I$use", "_scanf", "__vfscanf",
               "__0printf", "__0sprintf", "_btod", "_dtoa", "_ftoa", "__strtod")
SDK_C = re.compile(r"^(nn[a-z]+[A-Z_]|\.nn\.|\$Sub\$\$_ZN2nn|\"math_|__(fb|fbv|shm|shv|sta|tx|txv|"
                   r"vb|vbv|vldtr|cb)_|gd[A-Z]|gl[A-Z]|fb_)")
MOLIVE_C = re.compile(r"^(mwmo|VX2|DEBLOCK|FASTAUDIO|MoDeblock|ImaAdpcm)")
NEX_C = re.compile(r"^(Quazal|quazal_|PRUDP)")


def classify(sig: str) -> tuple[str | None, str, str, str]:
    """-> (library or None when the name alone does not tell, class/scope, base, kind)."""
    prefix, qual, params = split_signature(sig)
    scope, base = split_scope(qual)
    plain_scope = strip_templates(scope)
    last = plain_scope.rsplit("::", 1)[-1] if plain_scope else ""
    if prefix == "virtual ":
        kind = "thunk"
    elif sig.startswith("__sti___"):
        kind = "static_init"
    elif sig.startswith((".ARM.Collect$$", "$Sub$$")):
        kind = "linker"
    elif re.match(r"^(t|i|ei)\._Z", sig) or re.match(r'^"[^"]+"\.\d+$', sig) or re.match(r"^<Func\d+>$", sig):
        kind = "local"
    elif base.startswith("~"):
        kind = "dtor"
    elif last and strip_templates(base) == last:
        kind = "ctor"
    elif base.startswith("operator"):
        kind = "operator"
    else:
        kind = "func"

    q = qual
    lib = None
    if q.startswith("nn::nex::"):
        lib = "nex"
    elif q.startswith("nn::pia::"):
        lib = "pia"
    elif q.startswith("nn::"):
        lib = "ctr_sdk"
    elif q.startswith("nw::"):
        lib = "nw4c"
    elif q.startswith("live2d::"):
        lib = "live2d"
    elif q.startswith("mw::"):
        lib = "molive"
    elif q.startswith("pead::"):
        lib = "pead"
    elif q.startswith(("std::", "__rw::", "sut::")) or q in ("operator new", "operator new[]",
                                                              "operator delete", "operator delete[]"):
        lib = "cxx_runtime"
    elif q.startswith(CXX_RT_PREFIX):
        lib = "cxx_runtime"
    elif "::" not in q and (q.startswith(CLIB_PREFIX) or q in C_RUNTIME):
        lib = "rvct_clib"
    elif q == "nnMain":
        lib = "game"
    elif SDK_C.match(q) or "_ZN2nn" in q or "_ZN4Pica" in q or q.startswith("Pica::"):
        lib = "ctr_sdk"
    elif MOLIVE_C.match(q):
        lib = "molive"
    elif NEX_C.match(q):
        lib = "nex"
    elif q in ZLIB:
        lib = "zlib"
    elif q.startswith("_ZSt") or q.startswith("t._ZSt"):
        lib = "cxx_runtime"
    elif kind in ("static_init", "local") or q.startswith("anonymous_namespace::"):
        lib = None                     # TU-local: take it from the neighbours
    elif "::" in q:
        lib = "game"                   # any other namespace/class: game code (incl. util::, prim::)
    else:
        lib = None                     # plain C name: could be game or middleware
    return lib, scope, base, kind


NO_VOTE = {"cxx_runtime", "unknown"}   # std:: templates are emitted inside any TU


def neighbor_fill(addrs: list[int], libs: list[str | None],
                  calls: dict[int, list[int]] | None = None,
                  unnamed: set[int] | None = None,
                  plain: set[int] | None = None,
                  thumb: set[int] | None = None,
                  thumb_calls_of: dict[int, list[int]] | None = None) -> list[tuple[str, str]]:
    """Tag the entries whose name does not tell (None).

    1. neighbours: the nearest name-tagged entry on each side (cxx_runtime ignored, since
       template instantiations land in any TU). Same tag on both sides, or only one side
       exists -> that tag ("neighbor").
    2. otherwise, if `calls` (addr -> BL/BLX targets) is given: a vote of the name-tagged
       callees and callers plus both neighbours; a strict winner -> "calls".
    3. otherwise "unknown" ("none").
    Indices in `unnamed` (funcmap-only starts, no symbol) are usually local helpers of
    the code just before them, so they take the previous side's tag when there is one.
    Indices in `plain` (extern "C" names) try the callee/caller vote first: armcc puts
    C-linkage functions of several libraries into one block, so their address
    neighbours are often unrelated.
    Indices in `thumb` (Thumb code) never take `game` from a neighbour: armcc built the
    game's own code as ARM only, so a Thumb function next to game code is a library
    helper packed there (0x30119C after func_00301148). Such an entry takes the vote of
    its Thumb calls (`thumb_calls_of`, callees and callers) or else the non-game side."""
    n = len(libs)
    voter = [l if l is not None and l not in NO_VOTE else None for l in libs]
    prev = [None] * n
    nxt = [None] * n
    cur = None
    for i in range(n):
        prev[i] = cur
        if voter[i] is not None:
            cur = voter[i]
    cur = None
    for i in range(n - 1, -1, -1):
        nxt[i] = cur
        if voter[i] is not None:
            cur = voter[i]
    idx = {a: i for i, a in enumerate(addrs)}

    def _callers(cm: dict[int, list[int]]) -> dict[int, list[int]]:
        out: dict[int, list[int]] = {}
        for src, ts in cm.items():
            for t in ts:
                if t in idx:
                    out.setdefault(t, []).append(src)
        return out
    callers = _callers(calls) if calls else {}
    def vote(i: int, sides: tuple, extra: dict[int, list[int]] | None = None) -> str | None:
        votes: Counter = Counter()
        cm = calls if extra is None else {**calls, **extra}
        cl = callers if extra is None else _callers(cm)
        for t in cm.get(addrs[i], []):
            j = idx.get(t)
            if j is not None and voter[j]:
                votes[voter[j]] += 1
        for src in cl.get(addrs[i], []):
            j = idx.get(src)
            if j is not None and voter[j]:
                votes[voter[j]] += 1
        for side in sides:
            if side:
                votes[side] += 1
        top = votes.most_common(2)
        return top[0][0] if top and (len(top) == 1 or top[0][1] > top[1][1]) else None

    out = []
    for i in range(n):
        if libs[i] is not None:
            out.append((libs[i], "name"))
            continue
        p, q = prev[i], nxt[i]
        if plain and i in plain and calls is not None:
            w = vote(i, ())
            if w:
                out.append((w, "calls"))
                continue
        if thumb and i in thumb and "game" in (p, q):
            w = vote(i, (), thumb_calls_of) if thumb_calls_of is not None else None
            if w and w != "game":
                out.append((w, "calls"))
                continue
            p = p if p != "game" else None
            q = q if q != "game" else None
        if unnamed and i in unnamed and p:
            out.append((p, "neighbor"))
            continue
        if p and q and p == q or (p and not q) or (q and not p):
            out.append((p or q, "neighbor"))
            continue
        if calls is not None:
            w = vote(i, (p, q))
            if w:
                out.append((w, "calls"))
                continue
        out.append(("unknown", "none"))
    return out


def thumb_calls(code: bytes, text_va: int, a: int, e: int) -> list[int]:
    """BL / BLX-immediate targets of the Thumb halfwords in [a, e) (BLX targets word-aligned)."""
    ts = []
    pc = a
    while pc + 4 <= e:
        h1 = int.from_bytes(code[pc - text_va: pc - text_va + 2], "little")
        h2 = int.from_bytes(code[pc + 2 - text_va: pc + 4 - text_va], "little")
        if h1 >> 11 == 0b11110 and h2 >> 11 in (0b11111, 0b11101):
            s_ = (h1 >> 10) & 1
            i1 = 1 - (((h2 >> 13) & 1) ^ s_)
            i2 = 1 - (((h2 >> 11) & 1) ^ s_)
            off = (s_ << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1)
            off -= (s_ << 25)
            t = pc + 4 + off
            ts.append(t & ~3 if h2 >> 11 == 0b11101 else t)
            pc += 4
        else:
            pc += 2
    return ts


def call_targets(code: bytes, text_va: int, rows: list[tuple[int, int, str]]) -> dict[int, list[int]]:
    """addr -> BL/BLX-immediate targets inside [addr, end) for ARM functions (literal-pool
    words that happen to decode as BL add a little noise; only function starts count).
    Thumb rows: see thumb_call_targets."""
    starts = {a for a, _, _ in rows}
    out = {}
    for a, e, mode in rows:
        if mode != "ARM":
            continue
        ts = []
        for pc in range(a, e - 3, 4):
            w = int.from_bytes(code[pc - text_va: pc - text_va + 4], "little")
            if (w & 0x0F000000) == 0x0B000000 and (w >> 28) != 0xF:          # BL
                off = (w & 0xFFFFFF) - ((w & 0x800000) << 1)
                t = pc + 8 + off * 4
            elif (w & 0xFE000000) == 0xFA000000:                             # BLX imm
                off = (w & 0xFFFFFF) - ((w & 0x800000) << 1)
                t = pc + 8 + off * 4 + ((w >> 23) & 2)
            else:
                continue
            if t in starts and t != a:
                ts.append(t)
        out[a] = ts
    return out



def thumb_call_targets(code: bytes, text_va: int, rows: list[tuple[int, int, str]]) -> dict[int, list[int]]:
    """Like call_targets, for the Thumb rows only. Kept apart: it is used only to tag a
    Thumb function whose neighbours say `game` (see neighbor_fill), so it cannot move
    any other tag."""
    starts = {a for a, _, _ in rows}
    return {a: [t for t in thumb_calls(code, text_va, a, e) if t in starts and t != a]
            for a, e, mode in rows if mode != "ARM"}

SDK_TU = {"ac", "act", "am", "applet", "boss", "cam", "cec", "cfg", "cx", "dbg", "dlp", "dsp", "ec",
          "err", "fnd", "friends", "fs", "gd", "gr", "gx", "hid", "http", "init", "ir", "ism", "math",
          "mic", "ndm", "news", "nfp", "ngc", "os", "phtsel", "ptm", "qtm", "snd", "socket", "srv",
          "ssl", "svc", "swkbd", "uds", "ulcd", "util", "y2r", "erreula", "crypto", "pl", "nwm",
          "camera", "nim", "aacdec", "sndaac", "gxlow", "gxi"}
NW_TU = {"eft", "ut", "io", "lyt", "font", "gfx", "dev", "anim"}
MOLIVE_TU = {"mobiclip", "helper"}
RT_TU = {"locale", "rwcats", "char"}
PIA_TU = {"transport", "session", "local", "inet", "common", "mesh", "sync", "clone", "reckoning",
          "lan", "framework", "plugin", "chat", "photon", "nat"}


def tu_class_lib(tu: str, class_libs: dict[str, Counter]) -> str | None:
    """'snd_SoundSystem_cpp' -> the library of the class/namespace path ending in
    snd::SoundSystem, when one exists in the map (nw::snd::SoundSystem -> nw4c)."""
    m = re.match(r"^([a-z][a-z0-9]*)_([A-Za-z0-9]+)_cpp$", tu)
    if not m:
        return None
    c = class_libs.get(f"{m.group(1)}::{m.group(2)}")
    return c.most_common(1)[0][0] if c else None


def static_init_tags(addrs: list[int], rows: dict[int, dict], libs: list,
                     calls: dict[int, list[int]] | None) -> dict[int, tuple[str, str]]:
    """armcc puts every TU's static initialiser (__sti___<n>_<file>_cpp) in one block
    sorted by file name, so neighbours say nothing. Tag each one (and the unnamed bodies
    funcmap split off after it) from what it calls; failing that, from the file name:
    Nintendo SDK/Pia sources are named module_File.cpp, the game's own CamelCase.cpp."""
    out = {}
    idx = {a: i for i, a in enumerate(addrs)}
    class_libs: dict[str, Counter] = {}
    for k, a in enumerate(addrs):
        sc = strip_templates(rows[a]["class"])
        if libs[k] and libs[k] not in NO_VOTE and sc.count("::") >= 1:
            parts = sc.split("::")
            for mod in set(parts[:-1]):          # nw::snd::internal::BasicSound -> snd::BasicSound
                class_libs.setdefault(f"{mod}::{parts[-1]}", Counter())[libs[k]] += 1
    i = 0
    n = len(addrs)
    while i < n:
        r = rows[addrs[i]]
        if r["kind"] != "static_init":
            i += 1
            continue
        group = [i]
        j = i + 1
        while j < n and rows[addrs[j]]["kind"] == "unnamed":
            group.append(j)
            j += 1
        votes: Counter = Counter()
        if calls:
            for g in group:
                for t in calls.get(addrs[g], []):
                    k = idx.get(t)
                    if k is not None and libs[k] and libs[k] not in NO_VOTE | {"rvct_clib"}:
                        votes[libs[k]] += 1
        top = votes.most_common(2)
        winner = top[0][0] if top and (len(top) == 1 or top[0][1] > top[1][1]) else None
        tu = re.sub(r"^__sti___\d+_", "", r["signature"])
        mod = tu.split("_", 1)[0]
        # The file name decides first: game TUs construct plenty of nw::/nn:: objects, so
        # their callees vote for the library. CamelCase files are game code, except the
        # NEX DDL clients (*_Blob.cpp), which call into nex.
        # Lower-case module_File names are library code; there the callees decide first
        # (snd_ is both nn::snd and nw::snd), then the module name.
        if tu[:1].isupper():
            tag = ("nex", "calls") if winner == "nex" else ("game", "file_name")
        elif tu_class_lib(tu, class_libs):
            tag = (tu_class_lib(tu, class_libs), "file_name")
        elif winner:
            tag = (winner, "calls")
        elif mod in RT_TU:
            tag = ("cxx_runtime", "file_name")
        elif mod in NW_TU:
            tag = ("nw4c", "file_name")
        elif mod in MOLIVE_TU:
            tag = ("molive", "file_name")
        elif mod in SDK_TU:
            tag = ("ctr_sdk", "file_name")
        elif mod in PIA_TU:
            tag = ("pia", "file_name")
        elif mod.startswith("sead"):
            tag = ("pead", "file_name")
        else:
            tag = ("unknown", "none")
        for g in group:
            out[g] = tag
        i = j
    return out


def guess_mode(code: bytes, text_va: int, a: int, end: int) -> str | None:
    """For a start funcmap does not know: 'THUMB' when the first ARM words do not decode
    but the same bytes are valid Thumb, else None (keep the other evidence)."""
    sys.path.insert(0, str(ROOT / "tools" / "analysis"))
    import funcmap as FM
    n = min(end, a + 16)
    words = [int.from_bytes(code[pc - text_va: pc - text_va + 4], "little") for pc in range(a, n - 3, 4)]
    if not words or all(FM.decode_arm(w, a + 4 * i)[0] != FM.K_INVALID for i, w in enumerate(words)):
        return None
    pc = a
    while pc + 2 <= n:
        h = int.from_bytes(code[pc - text_va: pc - text_va + 2], "little")
        h2 = int.from_bytes(code[pc + 2 - text_va: pc + 4 - text_va], "little") if pc + 4 <= len(code) + text_va else None
        k, _, _, _, ln = FM.decode_thumb(h, h2, pc)
        if k == FM.K_INVALID:
            return None
        pc += ln
    return "THUMB"


# ------------------------------------------------------------------ funcmap input
def read_funcmap(path: Path = FUNCMAP_CSV) -> dict[int, dict]:
    if not path.is_file():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        return {int(r["start"], 16): r for r in csv.DictReader(f)}


def run_funcmap() -> None:
    print("running tools/analysis/funcmap.py (~30 s)...", flush=True)
    subprocess.run([sys.executable, str(ROOT / "tools" / "analysis" / "funcmap.py")], check=True,
                   stdout=subprocess.DEVNULL)


def read_hand_names(path: Path = NAMES_CSV) -> dict[int, dict]:
    if not path.is_file():
        return {}
    out = {}
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("addr") or "").strip():
                out[int(r["addr"], 16)] = {k: (v or "").strip() for k, v in r.items() if k}
    return out


# ------------------------------------------------------------------ primary-name choice
def primary_index(names: list[str]) -> int:
    """At a shared address prefer a real C++/C name over linker collect fragments."""
    for i, n in enumerate(names):
        if not n.startswith((".ARM.Collect$$", "<Func")):
            return i
    return 0


# ------------------------------------------------------------------ start vetting
def thumb_tail(code: bytes, text_va: int, a: int, n: int) -> bool:
    """[a, n) decodes as straight Thumb code (no invalid halfword, no 0x0000/0xFFFF fill
    inside) whose last instruction is an unconditional return or branch: a small Thumb
    function packed between an ARM function's literal pool and the next Thumb function."""
    import flow as F
    pc, last = a, None
    if n - a < 2 or n - a > 256:
        return False
    while pc < n:
        h = int.from_bytes(code[pc - text_va: pc - text_va + 2], "little")
        if h in (0x0000, 0xFFFF):
            break
        h2 = int.from_bytes(code[pc + 2 - text_va: pc + 4 - text_va], "little") if pc + 4 <= n else None
        k, cond, _, _, ln = F.FM.decode_thumb(h, h2, pc)
        if k == F.FM.K_INVALID:
            return False
        last = (k, cond)
        pc += ln
    while pc < n:                                       # only fill may follow
        if int.from_bytes(code[pc - text_va: pc - text_va + 2], "little") not in (0x0000, 0xFFFF):
            return False
        pc += 2
    return last is not None and last[1] == 14 and last[0] in (F.FM.K_RET, F.FM.K_B, F.FM.K_BX)


PAD_ARM = {0x00000000, 0xE1A00000, 0xE320F000}    # zero fill, mov r0,r0, nop
PAD_THUMB = {0x0000, 0x46C0, 0xFFFF}                 # zero fill, mov r8,r8, 0xFFFF fill (the
                                                     # one thumb_tail allows; 0x10305E)


def vet_starts(code: bytes, text_va: int, text_end: int, sym_thumb: dict[int, bool],
               fm: dict[int, dict]) -> tuple[dict[int, tuple[bool, str]], Counter, dict]:
    """Decide which funcmap-only starts are real functions, and find starts the map and
    funcmap both miss right after a named function.

    funcmap's gap scan takes any STMFD/PUSH {..lr} as a prologue, and its Thumb pass takes
    pointers with bit 0 set as Thumb entries. Inside a named function both are often wrong:
    armcc opens many functions with 'ldr r0,=x' or one ALU op before the push, and an odd
    word in a literal pool can point into the middle of an ARM instruction. So a
    funcmap-only start X inside the window of a named function S (S up to the next map
    start) is kept only when
      * code entered at S (or at an already kept start in the window) cannot reach X by
        fall-through or local branch, X is not inside a reached instruction and not a
        literal (flow.reach), or
      * X is the target of a BL/BLX from reached code (a real entry point even when another
        function also runs into it: armcc drops the tail branch when the callee comes next).
    Then, after every start, if the reached code (and its literals) ends before the next
    start and the first non-padding instruction after it is a PUSH {..lr} in the same mode,
    that address is added as a start ('flow' source).

    Returns ({addr: (is_thumb, source)} of added starts, Counter of decisions,
             {addr: reason} of rejected funcmap starts)."""
    import flow as F
    ss = sorted(sym_thumb)
    windows: dict[int, list[int]] = {}
    added: dict[int, tuple[bool, str]] = {}
    for a in sorted(x for x in fm if text_va <= x < text_end and x not in sym_thumb):
        i = bisect.bisect_right(ss, a) - 1
        if i < 0:
            added[a] = (fm[a]["mode"].upper().startswith("T"), "funcmap")
            continue
        windows.setdefault(i, []).append(a)
    cache: dict[tuple[int, bool, int], object] = {}

    def R(a: int, th: bool, lim: int):
        k = (a, th, lim)
        if k not in cache:
            cache[k] = F.reach(code, text_va, a, lim, th)
        return cache[k]

    def lim_of(i: int) -> int:
        return ss[i + 1] if i + 1 < len(ss) else text_end

    known = sorted(set(ss) | {a for a in fm if text_va <= a < text_end})
    calls = set()
    for i, s in enumerate(ss):
        calls.update(R(s, sym_thumb[s], lim_of(i)).calls)
    decisions: Counter = Counter()
    rejected: dict[int, str] = {}
    for _ in range(6):                                 # until the call set is stable
        kept: dict[int, tuple[bool, str]] = {}
        decisions = Counter()
        rejected = {}
        for i, xs in windows.items():
            lim = lim_of(i)
            rs = [R(ss[i], sym_thumb[ss[i]], lim)]
            for x in xs:
                xth = fm[x]["mode"].upper().startswith("T")
                called = xth if (x, xth) in calls else (not xth) if (x, not xth) in calls else None
                covered = any(r.covers(x, known) for r in rs)
                if covered and called is None:
                    decisions["rejected: reached from the named function"] += 1
                    rejected[x] = "reached"
                    continue
                th = xth if called is None else called
                r = R(x, th, lim)
                if not r.insns:
                    decisions["rejected: does not decode"] += 1
                    rejected[x] = "invalid"
                    continue
                decisions["kept: call target" if called is not None else "kept: unreachable from the named function"] += 1
                kept[x] = (th, "funcmap")
                rs.append(r)
        new_calls = set(calls)
        for x, (th, _) in kept.items():
            i = bisect.bisect_right(ss, x) - 1
            new_calls.update(R(x, th, lim_of(i)).calls)
        if new_calls == calls:
            break
        calls = new_calls
    added.update(kept)

    def first_valid(a: int, th: bool) -> bool:
        if th:
            h = int.from_bytes(code[a - text_va: a - text_va + 2], "little")
            h2 = int.from_bytes(code[a + 2 - text_va: a + 4 - text_va], "little")
            return F.FM.decode_thumb(h, h2, a)[0] != F.FM.K_INVALID
        if a & 3:
            return False
        return F.FM.decode_arm(int.from_bytes(code[a - text_va: a - text_va + 4], "little"), a)[0] != F.FM.K_INVALID

    def window_covers(e: int) -> bool:
        """e is inside code reached from the named start of its window or from a start
        kept in that window (window limit = next map start, so branches past nearer
        unnamed starts count)."""
        i = bisect.bisect_right(ss, e) - 1
        if i < 0:
            return False
        lim = lim_of(i)
        if R(ss[i], sym_thumb[ss[i]], lim).covers(e, known):
            return True
        return any(R(x, added[x][0], lim).covers(e, known) for x in windows.get(i, ()) if x in added and x < e)

    # The two passes below feed each other (a start found after a reached end can hold
    # calls to targets that are not starts yet, e.g. the Thumb stdio init at 0x103060
    # calling 0x30119C / 0x301A10 / 0x301A1C), so repeat both until neither adds one.
    while True:
        grew = False
        # direct call targets that are not starts yet (code calls into the middle of a
        # funcmap extent, or a small function after a literal pool that nothing else found)
        while True:
            allm = {a: th for a, th in sym_thumb.items()}
            allm.update({a: th for a, (th, _) in added.items()})
            order = sorted(allm)
            new = {}
            for j, a in enumerate(order):
                n = order[j + 1] if j + 1 < len(order) else text_end
                for c, th in R(a, allm[a], n).calls:
                    if text_va <= c < text_end and c not in allm and c not in new and first_valid(c, th):
                        new[c] = (th, "flow")
            if not new:
                break
            grew = True
            decisions["added: BL/BLX target that was not a start"] += len(new)
            added.update(new)

        # starts after the reached end of a function (map and funcmap both missed them)
        while True:
            allm = {a: th for a, th in sym_thumb.items()}
            allm.update({a: th for a, (th, _) in added.items()})
            order = sorted(allm)
            extra = {}
            for j, a in enumerate(order):
                n = order[j + 1] if j + 1 < len(order) else text_end
                th = allm[a]
                r = R(a, th, n)
                if r.incomplete or r.invalid or not r.insns:
                    continue
                step = 2 if th else 4
                e = r.end()
                e += (-e) % step
                while e < n:
                    v = int.from_bytes(code[e - text_va: e - text_va + step], "little")
                    if v not in (PAD_THUMB if th else PAD_ARM):
                        break
                    e += step
                if e >= n or r.covers(e, known):
                    continue
                if th:
                    h2 = int.from_bytes(code[e + 2 - text_va: e + 4 - text_va], "little")
                    k, _, _, b, _ = F.FM.decode_thumb(int.from_bytes(code[e - text_va: e + 2 - text_va], "little"), h2, e)
                else:
                    k, _, _, b = F.FM.decode_arm(int.from_bytes(code[e - text_va: e + 4 - text_va], "little"), e)
                if k == F.FM.K_PUSH and b == 1:
                    extra[e] = (th, "flow")
                elif not th and j + 1 < len(order) and allm[n] and thumb_tail(code, text_va, e, n):
                    extra[e] = (True, "flow")             # Thumb helper between ARM code and Thumb code
            extra = {a: v for a, v in extra.items()
                     if a not in added and a not in sym_thumb and not window_covers(a)}
            if not extra:
                break
            grew = True
            decisions["added: start after the reached end (push, or Thumb helper)"] += len(extra)
            added.update(extra)
        if not grew:
            break
    return added, decisions, rejected


# ------------------------------------------------------------------ build
def build(entries: list[MapEntry], fm: dict[int, dict], hand: dict[int, dict],
          text_va: int, text_end: int, code: bytes | None = None) -> tuple[list[dict], list[str]]:
    rows: dict[int, dict] = {}
    for e in entries:
        if not (text_va <= e.addr < text_end):
            continue
        k = primary_index(e.names)
        sig = e.names[k]
        lib, scope, base, kind = classify(sig)
        rows[e.addr] = {"addr": e.addr, "signature": sig, "aliases": [n for i, n in enumerate(e.names) if i != k],
                        "lib": lib, "class": scope, "kind": kind, "source": "symbol_map",
                        "confidence": "high", "thumb_bit": e.thumb_bit}
    sym_starts = set(rows)
    fm_starts = {a for a in fm if text_va <= a < text_end}
    fm_sorted = sorted(fm_starts)
    for a, h in hand.items():
        if text_va <= a < text_end and a not in rows:
            rows[a] = {"addr": a, "signature": "", "aliases": [], "lib": None, "class": "", "kind": "func",
                       "source": "hand", "confidence": "high", "thumb_bit": False}

    def mode_of(a: int, r: dict, nxt: int) -> str:
        if a in fm:
            return "THUMB" if fm[a]["mode"].upper().startswith("T") else "ARM"
        if (a & 2) or r["thumb_bit"]:
            return "THUMB"
        if code is not None and a - 8 >= text_va and                 code[a - 8 - text_va: a - text_va] == bytes.fromhex("01c08fe21cff2fe1"):
            return "THUMB"                             # after an 'add ip,pc,#1 ; bx ip' stub
        if code is not None:
            guess = guess_mode(code, text_va, a, nxt)
            if guess:
                return guess
        i = bisect.bisect_right(fm_sorted, a) - 1     # inside a funcmap function's extent
        if i >= 0:
            f = fm[fm_sorted[i]]
            if a < int(f["end_guess"], 16):
                return "THUMB" if f["mode"].upper().startswith("T") else "ARM"
        return "ARM"

    named = sorted(rows)                               # map + hand starts
    modes = {a: mode_of(a, rows[a], named[i + 1] if i + 1 < len(named) else text_end)
             for i, a in enumerate(named)}
    if code is not None:
        added, decisions, rejected = vet_starts(code, text_va, text_end,
                                                {a: modes[a] == "THUMB" for a in named}, fm)
    else:                                              # no code: trust funcmap
        added = {a: (fm[a]["mode"].upper().startswith("T"), "funcmap") for a in fm_starts - sym_starts}
        decisions, rejected = Counter(), {}
    for a, (th, src) in added.items():
        if a in rows:
            continue
        tier = fm[a].get("confidence") or "low" if a in fm else "low"
        rows[a] = {"addr": a, "signature": "", "aliases": [], "lib": None, "class": "", "kind": "unnamed",
                   "source": f"funcmap:{tier}" if src == "funcmap" else "flow",
                   "confidence": tier, "thumb_bit": False}
        modes[a] = "THUMB" if th else "ARM"

    addrs = sorted(rows)
    ends = {a: (addrs[i + 1] if i + 1 < len(addrs) else text_end) for i, a in enumerate(addrs)}
    calls = call_targets(code, text_va, [(a, ends[a], modes[a]) for a in addrs]) if code else None
    libs = [rows[a]["lib"] for a in addrs]
    tags = neighbor_fill(addrs, libs, calls,
                         {i for i, a in enumerate(addrs) if rows[a]["kind"] == "unnamed"},
                         {i for i, a in enumerate(addrs) if rows[a]["signature"]
                          and "::" not in split_signature(rows[a]["signature"])[1]},
                         {i for i, a in enumerate(addrs) if modes[a] == "THUMB"},
                         thumb_call_targets(code, text_va, [(a, ends[a], modes[a]) for a in addrs])
                         if code else None)
    for i, lib_by in static_init_tags(addrs, rows, libs, calls).items():
        tags[i] = lib_by
    out = []
    for i, a in enumerate(addrs):
        r = rows[a]
        end = ends[a]
        lib, by = tags[i]
        if a == text_va and r["lib"] is None and not r["signature"]:
            lib, by = "crt0", "name"
        if r["signature"]:
            _, qual, _ = split_signature(r["signature"])
            name = asm_name(qual)
        else:
            name = f"func_{a:08X}"
        h = hand.get(a)
        if h:
            name = h.get("name") or name
            if h.get("library"):
                lib, by = h["library"], "hand"
            if h.get("class"):
                r["class"] = h["class"]
            r["source"] = "hand" if not r["signature"] else "symbol_map+hand"
            if r["kind"] == "unnamed" and h.get("name"):
                r["kind"] = "func"
        out.append({"addr": a, "end": end, "size": end - a, "name": name, "class": r["class"],
                    "library": lib, "source": r["source"], "kind": r["kind"],
                    "confidence": r["confidence"], "mode": modes[a], "library_by": by,
                    "signature": r["signature"], "aliases": " | ".join(r["aliases"]),
                    "_hand": bool(h and h.get("name"))})

    # assembler-safe, unique names
    for r in out:
        if len(r["name"]) > MAX_NAME:
            r["name"] = r["name"][: MAX_NAME - 10].rstrip("_") + f"_{r['addr']:08X}"
    cnt = Counter(r["name"] for r in out)
    for r in out:
        if cnt[r["name"]] > 1 and not r["_hand"] and not r["name"].endswith(f"{r['addr']:08X}"):
            r["name"] = f"{r['name']}_{r['addr']:08X}"
    cnt = Counter(r["name"] for r in out)
    dups = [n for n, c in cnt.items() if c > 1]
    if dups:
        raise ValueError(f"duplicate names after suffixing: {dups[:5]}")
    bad = [r["name"] for r in out if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", r["name"])]
    if bad:
        raise ValueError(f"names that are not assembler-safe: {bad[:5]}")

    # report
    rep = []
    eq = sym_starts & fm_starts
    rep.append(f"symbol map starts in .text: {len(sym_starts)}; funcmap starts: {len(fm_starts)}")
    rep.append(f"reconcile: equal {len(eq)}, symbol-only {len(sym_starts - fm_starts)}, "
               f"funcmap-only {len(fm_starts - sym_starts)}")
    tiers = Counter(fm[a].get("confidence") or "low" for a in fm_starts - sym_starts)
    rep.append(f"  funcmap-only by funcmap tier: {dict(sorted(tiers.items()))}")
    tiers = Counter(fm[a].get("confidence") or "low" for a in eq)
    rep.append(f"  equal by funcmap tier:        {dict(sorted(tiers.items()))}")
    rep.append(f"vetting of funcmap-only starts inside named functions (flow.reach):")
    for k, v in sorted(decisions.items()):
        rep.append(f"  {k}: {v}")
    rep.append(f"  funcmap-only starts kept in the registry: {sum(1 for a in fm_starts - sym_starts if a in rows)}")
    rep.append(f"registry rows: {len(out)}; named from the map: {sum(1 for r in out if r['signature'])}; "
               f"unnamed: {sum(1 for r in out if not r['signature'] and not r['_hand'])}; hand: "
               f"{sum(1 for r in out if r['_hand'])}")
    rep.append(f"modes: {dict(Counter(r['mode'] for r in out))}")
    rep.append(f"kinds: {dict(Counter(r['kind'] for r in out).most_common())}")
    rep.append(f"library tag source: {dict(Counter(r['library_by'] for r in out))}")
    rep.append("")
    rep.append("| Library | Functions | Named | Bytes |")
    rep.append("|---|---:|---:|---:|")
    by = {}
    for r in out:
        g = by.setdefault(r["library"], [0, 0, 0])
        g[0] += 1
        g[1] += bool(r["signature"]) or r["_hand"]
        g[2] += r["size"]
    for lib in sorted(by, key=lambda k: -by[k][0]):
        g = by[lib]
        rep.append(f"| {lib} | {g[0]:,} | {g[1]:,} | {g[2]:,} |")
    return out, rep


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLUMNS)
    for r in rows:
        w.writerow([f"0x{r['addr']:08X}", f"0x{r['end']:08X}", r["size"], r["name"], r["class"],
                    r["library"], r["source"], r["kind"], r["confidence"], r["mode"], r["library_by"],
                    r["signature"], r["aliases"]])
    return buf.getvalue()


# ------------------------------------------------------------------ selftest
def selftest() -> int:
    fails = 0

    def check(what, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {what}: {got!r}" + ("" if ok else f" (want {want!r})"))

    # split_signature / split_scope
    check("sig plain", split_signature("nn::fs::File::Read(void*,int)"), ("", "nn::fs::File::Read", "(void*,int)"))
    check("sig const", split_signature("A::B::Get(void) const"), ("", "A::B::Get", "(void) const"))
    check("sig virtual", split_signature("virtual X::OnReplace(void)"), ("virtual ", "X::OnReplace", "(void)"))
    check("sig call op", split_signature("Foo::operator()(int)"), ("", "Foo::operator()", "(int)"))
    check("sig no params", split_signature("__cxa_vec_new"), ("", "__cxa_vec_new", ""))
    check("sig fnptr param", split_signature("f(void(*)(int),int)"), ("", "f", "(void(*)(int),int)"))
    check("sig template", split_signature("std::copy<A**,A**>(A**,A**,A**)"), ("", "std::copy<A**,A**>", "(A**,A**,A**)"))
    check("scope template", split_scope("A<B::C>::f"), ("A<B::C>", "f"))
    check("scope operator<", split_scope("A::operator<"), ("A", "operator<"))
    check("scope operator<<", split_scope("A<int>::operator<<"), ("A<int>", "operator<<"))
    check("scope conv", split_scope("nn::nex::DateTime::operator unsigned long"),
          ("nn::nex::DateTime", "operator unsigned long"))
    check("scope dtor", split_scope("a::B::~B"), ("a::B", "~B"))
    check("scope free", split_scope("fputc"), ("", "fputc"))
    # asm names
    check("asm plain", asm_name("nn::fs::File::Read"), "nn__fs__File__Read")
    check("asm dtor", asm_name("a::B::~B"), "a__B__dtor_B")
    check("asm op", asm_name("A::operator=="), "A__operator_eq")
    check("asm new[]", asm_name("operator new[]"), "operator_new_array")
    check("asm collect", asm_name(".ARM.Collect$$libinit$$0000000F"), "ARM_Collect_libinit_0000000F")
    check("asm digit", asm_name('"math_Matrix34.cpp".30'), "math_Matrix34_cpp_30")
    check("asm template", asm_name("std::copy<A**,A**>"), "std__copy_A_A")
    # classify
    for sig, lib, kind in [("nn::nex::Foo::Bar(void)", "nex", "func"),
                           ("nn::pia::common::X::X(void)", "pia", "ctor"),
                           ("nn::os::Thread::~Thread(void)", "ctr_sdk", "dtor"),
                           ("nw::snd::SoundSystem::AppendEffect(int)", "nw4c", "func"),
                           ("live2d::LDObject::operator new(unsigned int)", "live2d", "operator"),
                           ("mw::mo::helper::Player::PausePlayback(void)", "molive", "func"),
                           ("pead::allocateFromSeadHeap(unsigned int,pead::Heap*)", "pead", "func"),
                           ("std::string::operator=(const char*)", "cxx_runtime", "operator"),
                           ("operator new(unsigned int)", "cxx_runtime", "operator"),
                           ("__cxa_guard_release", "cxx_runtime", "func"),
                           ("x$fpl$ffixu", "rvct_clib", "func"),
                           (".ARM.Collect$$libinit$$00000013", "rvct_clib", "linker"),
                           ("fputc", "rvct_clib", "func"),
                           (".nn.svc.SleepThread", "ctr_sdk", "func"),
                           ("nngxFinalize", "ctr_sdk", "func"),
                           ("nnMain", "game", "func"),
                           ("mwmomobiclipDecoderCreate", "molive", "func"),
                           ("deflate_slow", "zlib", "func"),
                           ("quazal_zcalloc", "nex", "func"),
                           ("Unit::GetMovePower(bool,int) const", "game", "func"),
                           ("castle::Food::Data::GetName(void) const", "game", "func"),
                           ("virtual nn::nex::A::B(void)", "nex", "thunk"),
                           ("__sti___26_SortieSkillMenuCurrent_cpp", None, "static_init"),
                           ("anonymous_namespace::GetToken(const char*&)", None, "func"),
                           ("<Func5>", None, "local"),
                           ("BattleStart", None, "func")]:
        got = classify(sig)
        check(f"classify {sig[:40]}", (got[0], got[3]), (lib, kind))
    # neighbor fill
    check("fill", neighbor_fill([1, 2, 3, 4, 5, 6], ["game", None, "game", "nex", None, None]),
          [("game", "name"), ("game", "neighbor"), ("game", "name"), ("nex", "name"),
           ("nex", "neighbor"), ("nex", "neighbor")])
    check("fill disagree", neighbor_fill([1, 2, 3], ["game", None, "nex"])[1], ("unknown", "none"))
    check("fill skips templates", neighbor_fill([1, 2, 3, 4], ["game", "cxx_runtime", None, "game"])[2],
          ("game", "neighbor"))
    check("fill calls vote", neighbor_fill([1, 2, 3, 4], ["game", None, "nex", "nex"], {2: [3, 4]})[1],
          ("nex", "calls"))
    check("fill unnamed takes prev", neighbor_fill([1, 2, 3], ["molive", None, "game"], None, {1})[1],
          ("molive", "neighbor"))
    check("fill calls tie", neighbor_fill([1, 2, 3], ["game", None, "nex"], {2: []})[1], ("unknown", "none"))
    blw = (0xEB000000 | ((0x100010 - 0x100000 - 8) // 4)).to_bytes(4, "little")
    check("call_targets", call_targets(blw + bytes(28), 0x100000, [(0x100000, 0x100010, "ARM"),
                                                                  (0x100010, 0x100020, "ARM")]),
          {0x100000: [0x100010], 0x100010: []})
    # map parsing: two names at one address, a Thumb-bit entry, terminator
    names = b"a::f(void)\0.ARM.Collect$$x\0b::g(int)\0t\0"
    addrs = struct.pack("<8I", 0x100000, 11, 0x100000, 0, 0x100011, 27, 0, 0)
    ents, st = parse_map(names, addrs)
    check("map entries", [(e.addr, e.thumb_bit, e.names) for e in ents],
          [(0x100000, False, [".ARM.Collect$$x", "a::f(void)"]), (0x100010, True, ["b::g(int)"])])
    check("map stats", (st["terminator"], st["names"], st["shared_addresses"], st["thumb_bit_set"]),
          (True, 3, 1, 1))
    try:
        parse_map(names, struct.pack("<2I", 0x100000, 3))
        check("bad offset rejected", False, True)
    except ValueError:
        check("bad offset rejected", True, True)
    # build: union, sizes, collisions, hand names, primary choice
    fm = {0x100000: {"mode": "ARM", "confidence": "high", "end_guess": "0x00100008"},
          0x100020: {"mode": "ARM", "confidence": "low", "end_guess": "0x00100030"},
          0x100040: {"mode": "THUMB", "confidence": "high", "end_guess": "0x00100048"}}
    ents = [MapEntry(0x100000, False, [".ARM.Collect$$x", "a::f(void)"]),
            MapEntry(0x100010, False, ["a::f(int)"]), MapEntry(0x100040, False, ["b::h(void)"]),
            MapEntry(0x100046, False, ["b::k(void)"])]
    hand = {0x100020: {"addr": "0x100020", "name": "my_name", "library": "game"}}
    rows, _ = build(ents, fm, hand, 0x100000, 0x100050)
    check("build addrs", [r["addr"] for r in rows], [0x100000, 0x100010, 0x100020, 0x100040, 0x100046])
    check("build sizes", [r["size"] for r in rows], [0x10, 0x10, 0x20, 6, 10])
    check("build names", [r["name"] for r in rows],
          ["a__f_00100000", "a__f_00100010", "my_name", "b__h", "b__k"])
    check("build alias", rows[0]["aliases"], ".ARM.Collect$$x")
    check("build modes", [r["mode"] for r in rows], ["ARM", "ARM", "ARM", "THUMB", "THUMB"])
    check("build sources", [r["source"] for r in rows],
          ["symbol_map", "symbol_map", "hand", "symbol_map", "symbol_map"])
    check("csv header", to_csv(rows).splitlines()[0], ",".join(COLUMNS))
    # vetting with code: named f = 'ldr r0,=lit ; push {r4,lr} ; bl g ; pop {r4,pc} ; .word lit',
    # then unnamed g = 'push {r4,lr} ; pop {r4,pc}' (called), then an ARM->Thumb packed helper.
    # funcmap proposes f+4 (the push: false split) and g (real).
    words = [0xE59F0008, 0xE92D4010, 0xEB000001, 0xE8BD8010, 0x12345678, 0xE92D4010, 0xE8BD8010]
    code = struct.pack(f"<{len(words)}I", *words) + struct.pack("<2H", 0x2000, 0x4770)  # movs r0,#0 ; bx lr
    fm = {0x100004: {"mode": "ARM", "confidence": "medium", "end_guess": "0x00100014", "sources": "prologue"},
          0x100014: {"mode": "ARM", "confidence": "high", "end_guess": "0x0010001C", "sources": "bl"}}
    code += struct.pack("<2H", 0x4770, 0x0000)                     # h (Thumb, named): bx lr
    ents2 = [MapEntry(0x100000, False, ["f(void)"]), MapEntry(0x100020, True, ["h(void)"])]
    rows, rep = build(ents2, fm, {}, 0x100000, 0x100000 + len(code), code)
    check("vet: false split at the push rejected", [r["addr"] for r in rows][:2], [0x100000, 0x100014])
    check("vet: named body kept whole", rows[0]["size"], 0x14)
    check("vet: Thumb helper after ARM code found", [(r["addr"], r["mode"]) for r in rows][2:3], [(0x10001C, "THUMB")])
    print("selftest failures:", fails)
    return 1 if fails else 0


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--funcmap", action="store_true", help="re-run funcmap.py first")
    ap.add_argument("--check", action="store_true", help="exit 1 if config/functions.csv is stale")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    code = EXT / "code.bin"
    if a.funcmap or not FUNCMAP_CSV.is_file() or (code.is_file() and FUNCMAP_CSV.stat().st_mtime < code.stat().st_mtime):
        run_funcmap()
    entries, stats = read_map()
    fm = read_funcmap()
    hand = read_hand_names()
    t = GAME.seg("text")
    rows, rep = build(entries, fm, hand, t.vaddr, t.end, code.read_bytes())
    head = [f"symbol map: {stats['timestamp']}",
            f"  {stats['names']} names at {stats['addresses']} addresses "
            f"({stats['shared_addresses']} addresses carry several names), terminator: {stats['terminator']}, "
            f"Thumb bit set: {stats['thumb_bit_set']}, halfword-aligned (Thumb) starts: {stats['halfword_aligned']}"]
    text = to_csv(rows)
    if a.check:
        cur = OUT_CSV.read_text(encoding="utf-8") if OUT_CSV.is_file() else ""
        if cur != text:
            print("config/functions.csv is stale: run python tools/fates/symbols.py")
            return 1
        print(f"config/functions.csv up to date ({len(rows)} rows)")
        return 0
    OUT_CSV.write_text(text, encoding="utf-8", newline="")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "symbols_report.txt").write_text("\n".join(head + rep) + "\n", encoding="utf-8")
    print("\n".join(head + rep))
    print(f"wrote {OUT_CSV.relative_to(ROOT)} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
