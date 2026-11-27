#!/usr/bin/env python3
"""Per-function diff: compiled C++ vs the original bytes (stdlib + GNU objdump).

    python tools/diff_func.py NAME|ADDR|SYMBOL [options]
    python tools/diff_func.py --all [options]          one line per src_map row

The function is looked up in config/src_map.csv (by config name, address or object
symbol). Its source is compiled on its own (objects under build/diff_func/), the
function's section is "linked" at the original address in Python: every relocation is
applied using the addresses we know (config/functions.csv, config/data_symbols.csv,
src_map symbols, and the address embedded in func_/D_/lab_XXXXXXXX names). The result is
compared word for word with extracted/text.bin and shown side by side:

    ' '  identical          'r'  identical after applying a relocation
    '!'  different          '?'  relocation against an unknown symbol: compared with
                                 the relocated field masked (opcode bits only)

Exit status 0 = MATCH, 1 = differences, 2 = usage/lookup error.

Options:
    --compiler NAME     compile with this profile (default: the row's, else the default
                        profile from tools/config.local.json; see tools/compile.py)
    --flags "..."       extra compiler flags for an experiment (space separated)
    --nonmatching       compile with -DNONMATCHING (automatic for nonmatching rows)
    --source FILE --symbol SYM
                        try a function that has no src_map row yet (ADDR required);
                        --symbol may be omitted if the object defines one function
    --linked            no compile: compare the linked image (build/text.bin, from the
                        last `build.py build`) at the function's address instead
    --quiet             summary line only
"""
from __future__ import annotations

import csv
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import compile as CX  # noqa: E402
import build as B  # noqa: E402

OUT = B.BUILD / "diff_func"
NAME_ADDR = re.compile(r"^(?:func|D|lab)_([0-9A-Fa-f]{8})$")


def data_range() -> tuple[int, int]:
    """[.rodata start, .bss end) of this game's image (extracted/layout.json)."""
    lay = B.layout()
    data_end = lay["data"]["addr"] + lay["data"]["size"]
    return lay["rodata"]["addr"], data_end + lay["bss_size"]


# ----------------------------------------------------------------------------- symbols
class Symbols:
    def __init__(self):
        self.addr: dict[str, int] = {}
        self.name: dict[int, str] = {}
        self.d0, self.d1 = data_range()
        funcs = CX.read_functions() if CX.FUNCS_CSV.is_file() else {}
        for a, (_end, n) in funcs.items():
            self.addr[n] = a
            self.name[a] = n
        if CX.DATA_CSV.is_file():
            with CX.DATA_CSV.open(newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    a = int(r["addr"], 16)
                    self.addr[r["name"]] = a
                    self.name.setdefault(a, r["name"])
        for r in CX.read_src_map():
            self.addr.setdefault(r.symbol, r.addr)

    def lookup(self, sym: str) -> int | None:
        if sym in self.addr:
            return self.addr[sym]
        m = NAME_ADDR.match(sym)
        return int(m.group(1), 16) if m else None

    def label(self, a: int) -> str:
        if a in self.name:
            return self.name[a]
        if self.d0 <= a < self.d1 and a % 4 == 0:
            return f"D_{a:08X}"           # the generator's default data label
        return f"{a:#x}"


# ----------------------------------------------------------------------------- relocate
def sext(v: int, bits: int) -> int:
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def relocate(fs: CX.FuncSection, base: int, syms: Symbols) -> tuple[list[int], dict[int, str], list[str]]:
    """Apply fs.relocs as if the section were linked at `base`.
    Returns (words, {word_index: 'r'|'?'}, notes)."""
    data = bytearray(fs.data)
    marks, notes = {}, []
    for r in fs.relocs:
        if r.tname in ("V4BX", "NONE"):
            continue                         # markers only: no field to relocate or mask
        i = r.offset // 4
        w = struct.unpack_from("<I", data, r.offset)[0]
        s = syms.lookup(r.sym.name)
        p = base + r.offset
        if s is None:
            marks[i] = "?"
            notes.append(f"+{r.offset:#x}: {r.tname} against unknown symbol {r.sym.name!r} (masked)")
            continue
        if r.tname in ("CALL", "JUMP24", "PC24"):
            a = r.addend if r.addend is not None else sext(w & 0xFFFFFF, 24) << 2
            w = (w & 0xFF000000) | (((s + a - p) >> 2) & 0xFFFFFF)
        elif r.tname == "ABS32":
            a = r.addend if r.addend is not None else w
            w = (s + a) & 0xFFFFFFFF
        elif r.tname == "REL32":
            a = r.addend if r.addend is not None else w
            w = (s + a - p) & 0xFFFFFFFF
        elif r.tname in ("MOVW_ABS_NC", "MOVT_ABS"):
            a = r.addend if r.addend is not None else sext(((w >> 4) & 0xF000) | (w & 0xFFF), 16)
            v = (s + a) & 0xFFFFFFFF
            v = v & 0xFFFF if r.tname == "MOVW_ABS_NC" else v >> 16
            w = (w & 0xFFF0F000) | ((v & 0xF000) << 4) | (v & 0xFFF)
        else:
            marks[i] = "?"
            notes.append(f"+{r.offset:#x}: unsupported relocation {r.tname} ({r.sym.name}) (masked)")
            continue
        struct.pack_into("<I", data, r.offset, w)
        marks[i] = "r"
        if r.tname == "ABS32":
            marks[i] = "rw"                  # a data word (literal pool / table)
    n = len(data) // 4
    return list(struct.unpack(f"<{n}I", bytes(data[:n * 4]))), marks, notes


def masked(w: int) -> int:
    """Field-masked form for words with an unresolvable relocation."""
    if (w >> 25) & 7 == 5:          # B/BL: keep cond + opcode
        return w & 0xFF000000
    return 0                        # data word / other: ignore entirely


# ----------------------------------------------------------------------------- disasm
DIS = re.compile(r"^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(.*)$")


def disasm(words: list[int], base: int, tag: str, syms: Symbols) -> dict[int, str]:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{tag}.bin"
    p.write_bytes(struct.pack(f"<{len(words)}I", *words))
    out = subprocess.run([B.tool("objdump"), "-D", "-b", "binary", "-marm", "-Mreg-names-std",
                          f"--adjust-vma={base:#x}", str(p)], capture_output=True, text=True).stdout
    res = {}
    for line in out.splitlines():
        m = DIS.match(line)
        if m:
            txt = re.sub(r"\s+", " ", m.group(3)).strip()
            txt = re.split(r" [@;] ", txt)[0]
            # symbolize branch targets
            bm = re.match(r"^(bl?x?\w*) (?:0x)?([0-9a-f]+)(?: <.*>)?$", txt)
            if bm and bm.group(1)[:1] == "b":
                txt = f"{bm.group(1)} {syms.label(int(bm.group(2), 16))}"
            res[int(m.group(1), 16)] = txt
    return res


def literal_pool_words() -> set[int]:
    """Addresses of literal-pool / jump-table words (build/cache/analysis.json, if present)."""
    p = B.BUILD / "cache" / "analysis.json"
    if not p.is_file():
        return set()
    import json
    c = json.loads(p.read_text())
    pool = set(c.get("jt_lits", []))
    for a, sz in c.get("lits", []):
        pool.update(range(a & ~3, a + sz, 4))
    return pool


# ----------------------------------------------------------------------------- driver
def find_row(key: str, rows: list[CX.Row]) -> CX.Row | None:
    for r in rows:
        if key in (r.name, r.symbol):
            return r
    try:
        a = int(key, 16)
    except ValueError:
        return None
    return next((r for r in rows if r.addr == a), None)


def diff(addr: int, words_c: list[int], marks: dict[int, str], syms: Symbols, quiet: bool,
         title: str, notes: list[str]) -> bool:
    funcs = CX.read_functions()
    end = funcs[addr][0]
    text = (B.EXT / "text.bin").read_bytes()
    t0 = B.layout()["text"]["addr"]
    words_o = list(struct.unpack_from(f"<{(end - addr) // 4}I", text, addr - t0))
    n = max(len(words_o), len(words_c))
    status, first = [], None
    for i in range(n):
        o = words_o[i] if i < len(words_o) else None
        c = words_c[i] if i < len(words_c) else None
        if o is None or c is None:
            st = "!"
        elif marks.get(i) == "?":
            st = "?" if masked(o) == masked(c) else "!"
        elif o == c:
            st = "r" if marks.get(i, "").startswith("r") else " "
        else:
            st = "!"
        status.append(st)
        if st == "!" and first is None:
            first = i
    ok = first is None
    unresolved = status.count("?")
    if not quiet:
        do = disasm(words_o, addr, "orig", syms)
        dc = disasm(words_c, addr, "comp", syms) if words_c else {}
        # data words: literal-pool words known to the analyzer, and relocated data words
        pool = literal_pool_words()
        for i in range(n):
            a = addr + 4 * i
            if i < len(words_o) and (a in pool or marks.get(i) == "rw"):
                do[a] = f".word {syms.label(words_o[i])}"
            if i < len(words_c) and (marks.get(i) == "rw" or (a in pool and words_c[i] == (words_o[i] if i < len(words_o) else None))):
                dc[a] = f".word {syms.label(words_c[i])}"
        print(f"== {title}")
        print(f"   original {end - addr:#x} bytes at {addr:08X}, compiled {len(words_c) * 4:#x} bytes")
        print(f"   {'addr':8}  {'original':44} {'':1} compiled")
        for i in range(n):
            a = addr + 4 * i
            lo = f"{words_o[i]:08X} {do.get(a, '')}" if i < len(words_o) else ""
            lc = f"{words_c[i]:08X} {dc.get(a, '')}" if i < len(words_c) else ""
            print(f"   {a:08X}  {lo:44.44} {status[i]} {lc}")
        for nline in notes:
            print(f"   note {nline}")
    if ok and unresolved:
        # A relocation against a symbol we cannot resolve leaves its word fully masked, so
        # any value would "match". Never report that as MATCH (verifier finding).
        ok = False
        msg = (f"UNRESOLVED: {unresolved} word(s) depend on unknown symbols; cannot confirm "
               f"a match (declare them in src_map.csv or fix the extern name)")
    elif ok:
        msg = "MATCH"
    else:
        a = addr + 4 * first
        msg = (f"DIFF at +{4 * first:#x} ({a:08X}): {status.count('!')} differing word(s)"
               + (f", size {len(words_c) * 4:#x} vs {len(words_o) * 4:#x}" if len(words_c) != len(words_o) else ""))
    print(f"{title}: {msg}")
    return ok


def run_one(row: CX.Row | None, addr: int, source: str, symbol: str | None, opts: dict, syms: Symbols) -> bool:
    funcs = CX.read_functions()
    if addr not in funcs:
        print(f"{addr:#010x} is not a function start in config/functions.csv")
        return False
    title = f"{funcs[addr][1]} ({addr:08X})"
    if opts["linked"]:
        got = (B.BUILD / "text.bin").read_bytes()
        t0 = B.layout()["text"]["addr"]
        a_sym = dict((n, a) for a, n in B.sym_map(B.BUILD)).get(symbol or funcs[addr][1])
        if a_sym is None:
            print(f"{title}: not found in build/fe1.elf")
            return False
        size = funcs[addr][0] - addr
        words = list(struct.unpack_from(f"<{size // 4}I", got, a_sym - t0))
        return diff(addr, words, {}, syms, opts["quiet"], title + " [linked image]", [])
    comp = opts["compiler"] or (row.compiler if row and row.compiler else CX.default_profile_name())
    mode = "nonmatching" if opts["nonmatching"] or (row and row.status == "nonmatching") else "matching"
    objs = CX.compile_sources({source: comp}, OUT, mode, extra_flags=opts["flags"])
    elf = CX.Elf(objs[source])
    if symbol is None:
        fn = [s.name for s in elf.symbols if s.type == CX.STT_FUNC and s.shndx and s.shndx < len(elf.sections)]
        if len(fn) != 1:
            print(f"{source}: defines {len(fn)} functions ({', '.join(fn)}); pass --symbol")
            return False
        symbol = fn[0]
    try:
        fs = CX.function_section(elf, symbol)
    except LookupError as ex:
        print(f"{title}: {ex}")
        return False
    words, marks, notes = relocate(fs, addr, syms)
    return diff(addr, words, marks, syms, opts["quiet"], f"{title} [{comp}, {mode}]", notes)


def main(argv: list[str]) -> int:
    opts = {"compiler": None, "flags": [], "nonmatching": False, "linked": False, "quiet": False}
    source = symbol = None
    keys, run_all = [], False
    it = iter(argv)
    for a in it:
        if a == "--compiler":
            opts["compiler"] = next(it)
        elif a == "--flags":
            opts["flags"] = next(it).split()
        elif a == "--nonmatching":
            opts["nonmatching"] = True
        elif a == "--linked":
            opts["linked"] = True
        elif a == "--quiet":
            opts["quiet"] = True
        elif a == "--source":
            source = Path(next(it)).resolve().relative_to(ROOT).as_posix()
        elif a == "--symbol":
            symbol = next(it)
        elif a == "--all":
            run_all = True
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            keys.append(a)
    syms = Symbols()
    rows = CX.read_src_map()
    if run_all:
        todo = [r for r in rows if r.status in ("matched", "nonmatching")]
        results = []
        for r in todo:
            ok = run_one(r, r.addr, r.source, r.symbol, dict(opts, quiet=True), syms)
            results.append((r, ok))
        bad = [r for r, ok in results if r.status == "matched" and not ok]
        nm_match = [r for r, ok in results if r.status == "nonmatching" and ok]
        print(f"summary: {sum(ok for _, ok in results)}/{len(results)} match; "
              f"{len(bad)} matched row(s) failing; {len(nm_match)} nonmatching row(s) now match"
              + (" (promote them to matched)" if nm_match else ""))
        return 1 if bad else 0
    if len(keys) != 1:
        print(__doc__)
        return 2
    row = find_row(keys[0], rows)
    if source:
        try:
            addr = row.addr if row else int(keys[0], 16)
        except ValueError:
            print("--source needs an address (or a src_map row)")
            return 2
    elif row is None or not row.source:
        print(f"{keys[0]}: no src_map row with a source (use --source FILE [--symbol SYM])")
        return 2
    else:
        addr, source, symbol = row.addr, row.source, symbol or row.symbol
    return 0 if run_one(row, addr, source, symbol, opts, syms) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
