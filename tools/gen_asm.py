#!/usr/bin/env python3
"""M1: generate re-assemblable GNU as sources for the whole code.bin.

Output (all gitignored, regenerated from the user's own extracted/code.bin):
    asm/text/text_XXXXXXXX.s   one section per function (.text.f_XXXXXXXX), ~64 KB per file
    asm/func/func_XXXXXXXX.s   functions listed in config/src_map.csv, one file each:
                               status nonmatching -> assembled in the matching build;
                               status matched     -> reference only (diff_func.py, shift
                                                     test); the compiled C++ is linked
    asm/data/{rodata,data,bss}_XXXXXXXX.s
                               one section per data unit (config/naming/data_units.csv):
                               .rodata.u_XXXXXXXX / .data.u_XXXXXXXX / .bss.u_XXXXXXXX,
                               several units per file (~64 KB), address order
    asm/dunit/<unit_id>.s      units listed in config/data_map.csv, one file each
                               (nonmatching -> assembled; matched -> reference only,
                               the C++ object's data is linked there)
    asm/link_layout.json       ordered .text and data placement (asm files, src_map
                               functions, data units) that build.py turns into the
                               linker script
    asm/sections.txt           addresses that start an asm section (shift-test points)
    build/gen_report.txt       counts: raw instructions, symbolized pointers, rejects

Usage: python tools/gen_asm.py   (normally via `python tools/build.py gen`)

Every word comes out either as an instruction (objdump text, rewritten so branch
targets are symbols) or as `.word`/`.inst` with the original value. Pointers in literal
pools, jump tables, .rodata and .data become symbol expressions so the image is shiftable.
Addresses listed in config/raw_insns.txt are always emitted as `.inst` (round-trip
failures found by `build.py fixraw`).

Thumb (the registry's `mode` column; docs/SYMBOLS.md): Thumb rows, and the Thumb body
that follows an ARM->Thumb entry stub (`add ip, pc, #1 ; bx ip`) inside an ARM row, are
emitted in `.thumb` mode, halfword by halfword, inside the section of the preceding ARM
function (a Thumb row never starts a section, so halfword-aligned starts need no
padding). Each Thumb instruction is written as text only if GNU as gives back exactly
its bytes (checked here, in one assembler run with a listing). BL/BLX (the only 32-bit
Thumb instructions on the ARMv6K) are written `bl NAME` / `blx NAME` so the linker
re-aims them (build.py links with --use-blx); short branches, PC-relative instructions
and anything as rejects or re-encodes stay `.inst.n`. Literal
words (targets of Thumb `ldr rX, [pc, #N]`, and ARM-analysis pool words) are `.word`.
Thumb instruction lines end in `@ XXXXXXXX T` so tools that read ARM words from the
`@ XXXXXXXX` tag (m1_tests.py) leave them alone. Thumb function symbols are plain
global labels (no `.thumb_func`/`%function`): a typed Thumb symbol would make the
linker set bit 0 in `.word sym` references and turn BL into BLX, changing bytes.
"""
from __future__ import annotations

import bisect
import csv
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "extracted"
ASM = ROOT / "asm"
BUILD = ROOT / "build"
CACHE = BUILD / "cache" / "analysis.json"
# Words forced to `.inst` (build.py fixraw). FE_RAW_INSNS points elsewhere (e.g. while
# trying a new game's first round trip in build/codetools/ before the list is reviewed).
RAW_LIST = Path(os.environ.get("FE_RAW_INSNS", ROOT / "config" / "raw_insns.txt"))
ASM_NAME = re.compile(r"[A-Za-z_.$][A-Za-z0-9_.$]*")
GROUP_BYTES = 0x10000
DATA_SECTION = {"rodata": ('.rodata.u_{:08X}', '"a",%progbits'),
                "data": ('.data.u_{:08X}', '"aw",%progbits'),
                "bss": ('.bss.u_{:08X}', '"aw",%nobits')}

sys.path.insert(0, str(ROOT / "tools" / "analysis"))
sys.path.insert(0, str(ROOT / "tools"))
import compile as CX  # noqa: E402  (src_map reader; tools/compile.py)


def load_layout():
    lay = json.loads((EXT / "layout.json").read_text())
    seg = {}
    for k in ("text", "rodata", "data"):
        s = lay[k]
        seg[k] = (s["addr"], s["addr"] + s["size"], s["file_offset"])
    d0, d1, _ = seg["data"]
    seg["bss"] = (d1, d1 + lay["bss_size"], None)
    return lay, seg


# ------------------------------------------------------------------ analysis cache
def analysis(code_sha1: str) -> dict:
    if CACHE.is_file():
        c = json.loads(CACHE.read_text())
        if c.get("sha1") == code_sha1:
            return c
    import funcmap  # tools/analysis/funcmap.py
    # funcmap's segment constants must be this game's (it reads config/game.json); check
    # them against the extracted layout so a stale or mismatched config cannot silently
    # analyse the wrong ranges.
    lay, seg = load_layout()
    want = {"TEXT_VA": seg["text"][0], "TEXT_SIZE": lay["text"]["size"],
            "RODATA_VA": seg["rodata"][0], "RODATA_SIZE": lay["rodata"]["size"],
            "DATA_VA": seg["data"][0], "DATA_SIZE": lay["data"]["size"]}
    wrong = {k: v for k, v in want.items() if getattr(funcmap, k, v) != v}
    if wrong:
        sys.exit("tools/analysis/funcmap.py segment constants disagree with extracted/layout.json: "
                 + ", ".join(f"{k}={getattr(funcmap, k):#x} (layout {v:#x})" for k, v in wrong.items()))
    print("running funcmap analyzer (~30-60 s, cached afterwards)...", flush=True)
    img = funcmap.Image(funcmap.CODE_BIN)
    an = funcmap.Analyzer(img)
    an.run()
    code = sorted(a for a, m in an.code.items() if m == "A")
    ranges = []
    for a in code:
        if ranges and ranges[-1][1] == a:
            ranges[-1][1] = a + 4
        else:
            ranges.append([a, a + 4])
    c = {
        "sha1": code_sha1,
        "funcs": sorted(f["start"] for f in an.funcs),
        "code_ranges": ranges,
        "lits": sorted([a, s] for a, s in an.lits.items()),
        "jt_lits": sorted(an.jt_lits),
    }
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(c))
    return c


# ------------------------------------------------------------------ objdump
LINE = re.compile(r"^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(.*)$")
COND = "(?:eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al)?"
BRANCH = re.compile(rf"^(b|bl){COND}\s+(?:0x)?([0-9a-f]+)$")
BAD = ("<UNDEFINED>", "UNPREDICTABLE", "<illegal", "undefined", "(bad)")


def objdump_text(objdump: str, text_va: int) -> dict[int, str]:
    out = subprocess.run(
        [objdump, "-D", "-b", "binary", "-marm", "-Mreg-names-std",
         f"--adjust-vma=0x{text_va:x}", str(EXT / "text.bin")],
        capture_output=True, text=True, check=True).stdout
    ins = {}
    for line in out.splitlines():
        m = LINE.match(line)
        if not m:
            continue
        txt = m.group(3)
        # strip trailing objdump comments ("@ 0x...", "; ...")
        txt = re.split(r"\s+[@;]\s", txt, maxsplit=1)[0].strip()
        ins[int(m.group(1), 16)] = txt
    return ins


def _ror(v: int, r: int) -> int:
    return ((v >> r) | (v << (32 - r))) & 0xFFFFFFFF if r else v


def pcrel_target(w: int, a: int) -> int | None:
    """Target of a PC-relative load/store/ADR (ARM mode) at address a, else None."""
    if (w >> 28) == 0xF or ((w >> 16) & 0xF) != 15:
        return None
    up = (w >> 23) & 1
    if (w >> 26) & 3 == 1 and not (w >> 25) & 1:                     # LDR/STR(B) imm
        off = w & 0xFFF
    elif ((w >> 25) & 7 == 0 and (w >> 22) & 1 and (w >> 7) & 1 and (w >> 4) & 1
          and (w >> 5) & 3):                                          # LDRH/LDRSB/LDRD/... imm
        off = ((w >> 4) & 0xF0) | (w & 0xF)
    elif (w >> 24) & 0xF == 0xD and (w >> 8) & 0xE == 0xA:              # VLDR/VSTR
        off = (w & 0xFF) * 4
    elif (w >> 25) & 7 == 1 and (w >> 21) & 0xF in (2, 4):              # ADR = SUB/ADD rd, pc, #imm
        imm = _ror(w & 0xFF, 2 * ((w >> 8) & 0xF))
        return (a + 8 + imm if (w >> 21) & 0xF == 4 else a + 8 - imm) & 0xFFFFFFFF
    else:
        return None
    return a + 8 + off if up else a + 8 - off


# Thumb (objdump -Mforce-thumb on a blob of the Thumb instructions only)
THUMB_LINE = re.compile(r"^\s*([0-9a-f]+):\s+([0-9a-f]{4}(?: [0-9a-f]{4})?)\s+(.*)$")
T_BRANCH = re.compile(rf"^(b|bl|blx|cbz|cbnz){COND}(\.[nw])?\s")
STUB = struct.pack("<II", 0xE28FC001, 0xE12FFF1C)     # add ip, pc, #1 ; bx ip
LISTING = re.compile(r"^\s*(\d+) (?:[0-9a-f?]{4}) ([0-9A-F]+)\s")


def thumb32(hw: int) -> bool:
    """First halfword of a 32-bit Thumb encoding (objdump's sizing rule too)."""
    return (hw >> 11) in (0x1D, 0x1E, 0x1F)


CP = re.compile(r"^(mrc2?|mcr2?)(\w*) (\d+), (\d+), (\w+), cr(\d+), cr(\d+), \{(\d+)\}$")


def normalize(txt: str, word: int) -> str:
    """Turn objdump spellings into ones GNU as re-assembles to the same bytes."""
    txt = re.sub(r"\s+", " ", txt.replace("\t", " ")).strip()
    if txt == "nop {0}":
        return "nop"                      # E320F000 (v6K hint) with -mcpu=mpcore
    if txt == "nop" and word == 0xE1A00000:
        return "mov r0, r0"               # legacy NOP; `nop` would assemble to E320F000
    m = CP.match(txt)
    if m:
        op, cond, cp, op1, rt, crn, crm, op2 = m.groups()
        return f"{op}{cond} p{cp}, {op1}, {rt}, c{crn}, c{crm}, {op2}"
    return txt


# ------------------------------------------------------------------ names
def asm_safe(name: str, addr: int) -> str:
    """config/functions.csv names become assembler symbols. Names made by make_config.py
    are already safe; a raw demangled name (`Unit::GetStr() const`, from the symbol map)
    is not, and falls back to func_XXXXXXXX rather than breaking the assembler."""
    name = (name or "").strip()
    return name if ASM_NAME.fullmatch(name) else f"func_{addr:08X}"


def thumb_pair(h1: int, h2: int) -> bool:
    """A BL/BLX prefix + suffix: the only 32-bit Thumb encodings on the ARM11 (ARMv6K has
    no Thumb-2), so the sweep makes 4-byte items of these alone (Fates 0x00100382: 0xFFFF
    padding would otherwise swallow the next function's first halfword)."""
    return h1 & 0xF800 == 0xF000 and h2 & 0xE800 == 0xE800


def read_function_names(path: Path, thumb: dict[int, tuple[int, str]] | None = None) -> dict[int, str]:
    """addr -> unique asm-safe name, ARM functions only (they start .text sections).
    Rows marked THUMB in the `mode` column (and any halfword-aligned start, which can only
    be Thumb) go to `thumb` instead, as addr -> (end, name): they are emitted in .thumb
    mode inside the preceding ARM function's section. Duplicate names (over both modes)
    get an _XXXXXXXX suffix."""
    names: dict[int, str] = {}
    seen: dict[str, int] = {}
    unsafe = dup = 0
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            a = int(r["addr"], 16)
            is_thumb = bool(a & 3) or (r.get("mode") or "ARM").strip().upper() == "THUMB"
            n = asm_safe(r["name"], a)
            unsafe += n != (r["name"] or "").strip()
            if n in seen and seen[n] != a:
                n = f"{n}_{a:08X}"
                dup += 1
            seen[n] = a
            if is_thumb:
                if thumb is not None:
                    thumb[a] = (int(r["end"], 16) if r.get("end") else a, n)
                continue
            names[a] = n
    if unsafe or dup:
        print(f"note: {path.name}: {unsafe} name(s) not assembler-safe (func_XXXXXXXX used), "
              f"{dup} duplicate(s) suffixed with the address", flush=True)
    return names


# ------------------------------------------------------------------ generator
class Gen:
    def __init__(self):
        self.lay, self.seg = load_layout()
        self.code = (EXT / "code.bin").read_bytes()
        cfg = json.loads((ROOT / "tools" / "config.local.json").read_text())
        self.bin = Path(cfg["binutils_dir"])
        self.an = analysis(hashlib.sha1(self.code).hexdigest())
        self.t0, self.t1, _ = self.seg["text"]
        # Function starts and names: config/functions.csv (from tools/make_config.py) is
        # the source of truth once it exists; the raw analysis cache is the fallback.
        self.fnames: dict[int, str] = {}
        self.dnames: dict[int, str] = {}
        self.overrides: dict[int, str] = {}
        self.thumb_rows: dict[int, tuple[int, str]] = {}    # Thumb start -> (end, name)
        fcsv = ROOT / "config" / "functions.csv"
        if fcsv.is_file():
            self.fnames = read_function_names(fcsv, self.thumb_rows)
            self.funcs = sorted(a for a in self.fnames if self.t0 <= a < self.t1)
        else:
            # 4-aligned starts only: Thumb functions (2-aligned) stay inside the
            # preceding section and come out as data words (Fates has a few near crt0).
            self.funcs = [f for f in self.an["funcs"] if self.t0 <= f < self.t1 and not f & 3]
        if self.funcs[0] != self.t0:
            self.funcs.insert(0, self.t0)
        dcsv = ROOT / "config" / "data_symbols.csv"
        if dcsv.is_file():
            with dcsv.open(newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    a = int(r["addr"], 16)
                    if a % 4 == 0 and ASM_NAME.fullmatch(r["name"].strip()):
                        self.dnames[a] = r["name"].strip()
        ocsv = ROOT / "config" / "naming" / "pointer_overrides.csv"
        if ocsv.is_file():
            with ocsv.open(newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if (r.get("confidence") or "").strip().lower() in ("high", "medium"):
                        self.overrides[int(r["word_addr"], 16)] = (
                            r["action"].strip().lower(), (r.get("target") or "").strip())
        self.funcset = set(self.funcs)
        self.is_code = set()
        for a, b in self.an["code_ranges"]:
            self.is_code.update(range(a, b, 4))
        self.pool = set()
        for a, s in self.an["lits"]:
            for w in range(a & ~3, a + s, 4):
                self.pool.add(w)
        self.jt = set(self.an["jt_lits"])
        self.raw = set()
        if RAW_LIST.is_file():
            for line in RAW_LIST.read_text().split():
                self.raw.add(int(line, 16))
        self.labels: dict[int, str] = {}     # aligned address -> label name
        # config/src_map.csv: functions that have C++ (matched or nonmatching)
        self.src_rows: dict[int, CX.Row] = {}
        bad = []
        self.src_aliases: list[list[str]] = []    # status asm: [C++ symbol, asm name]
        for r in CX.read_src_map():
            if r.status == "asm":
                if self.fnames.get(r.addr) != r.name:
                    bad.append(f"src_map.csv:{r.line}: name {r.name} != config name {self.fnames.get(r.addr)}")
                elif r.symbol != r.name:
                    self.src_aliases.append([r.symbol, r.name])
                continue
            if r.status not in ("matched", "nonmatching"):
                continue
            if r.addr in self.thumb_rows:
                bad.append(f"src_map.csv:{r.line}: {r.addr:#010x} is a Thumb function (C++ "
                           "replacement of Thumb code is not supported)")
            elif r.addr not in self.funcset:
                bad.append(f"src_map.csv:{r.line}: {r.addr:#010x} is not a function start")
            elif self.fnames.get(r.addr, f"func_{r.addr:08X}") != r.name:
                bad.append(f"src_map.csv:{r.line}: name {r.name} != config name "
                           f"{self.fnames.get(r.addr)} (update src_map after a rename)")
            self.src_rows[r.addr] = r
        if bad:
            sys.exit("\n".join(bad))
        self.load_units()
        self.stats = {k: 0 for k in (
            "section_merge_refs", "functions_joined", "insn", "insn_raw_forced", "insn_raw_bad", "insn_raw_branch", "data_words",
            "ptr_text", "ptr_data", "ptr_reject_round", "ptr_reject_utf16", "ptr_reject_midcode",
            "ptr_reject_jt_target", "ptr_reject_override_raw", "ptr_reject_override_pcrel_mismatch", "ptr_override_symbolize",
            "ptr_override_pcrel", "jt_entries", "ptr_data_pool_utf16_shape",
            "thumb_functions", "thumb_stub_bodies", "thumb_bytes", "thumb_insn", "thumb_raw",
            "thumb_raw_branch", "thumb_raw_pcrel", "thumb_raw_rejected", "thumb_words",
            "thumb_literal_refs", "thumb_calls", "thumb_calls_into_arm_rows")}
        self.rejects: list[tuple[int, int, str]] = []

    def load_units(self) -> None:
        """Data units (config/naming/data_units.csv) and their C++ owners (config/data_map.csv).
        The units must tile each segment exactly with 4-aligned starts; a bad table is
        reported, never patched here (the table belongs to tools/m2/data_objects.py)."""
        units, self.units_digest = CX.data_units()
        if self.units_digest.startswith("synthetic"):
            print(f"note: {CX.DATA_UNITS.relative_to(ROOT)} missing: using synthetic "
                  f"{CX.SYNTH_UNIT_BYTES:#x}-byte data units (fine for M1; run tools/m2/data_objects.py "
                  "before any C++ owns data)", flush=True)
        self.units: dict[str, list] = {k: [] for k in CX.SEGMENTS}
        bad = []
        for u in units:
            if u.seg not in self.units:
                bad.append(f"data_units.csv: {u.unit_id}: unknown segment {u.seg!r}")
                continue
            self.units[u.seg].append(u)
        ids = set()
        for k, us in self.units.items():
            s0, s1, _ = self.seg[k]
            us.sort(key=lambda u: u.start)
            pos = s0
            for u in us:
                if u.unit_id in ids:
                    bad.append(f"data_units.csv: duplicate unit_id {u.unit_id}")
                ids.add(u.unit_id)
                if u.start != pos:
                    bad.append(f"data_units.csv: {u.unit_id} starts at {u.start:08X}, previous unit ends at {pos:08X}")
                if u.start % 4 or u.end <= u.start:
                    bad.append(f"data_units.csv: {u.unit_id} [{u.start:08X},{u.end:08X}) is empty or not 4-aligned")
                if u.unit_id != f"{k}_{u.start:08X}":
                    bad.append(f"data_units.csv: unit_id {u.unit_id} does not match {k}_{u.start:08X}")
                pos = u.end
            if pos != s1:
                bad.append(f"data_units.csv: {k} units end at {pos:08X}, segment ends at {s1:08X}")
        self.data_rows: dict[str, CX.DataRow] = {}
        for d in CX.read_data_map():
            if d.unit_id not in ids:
                bad.append(f"data_map.csv:{d.line}: unit {d.unit_id} is not in data_units.csv")
            elif d.status in CX.DATA_STATUSES:
                self.data_rows[d.unit_id] = d
        if bad:
            sys.exit("\n".join(bad[:40]) + (f"\n... {len(bad)} problems" if len(bad) > 40 else ""))

    # address helpers
    def word(self, va: int) -> int:
        for k in ("text", "rodata", "data"):
            s0, s1, off = self.seg[k]
            if s0 <= va < s1:
                return struct.unpack_from("<I", self.code, off + va - s0)[0]
        raise ValueError(hex(va))

    def label_for(self, a: int) -> str:
        if a in self.labels:
            return self.labels[a]
        if self.t0 <= a <= self.t1:
            if a in self.funcset:
                name = self.fnames.get(a, f"func_{a:08X}")
            elif a in self.thumb_rows:
                name = self.thumb_rows[a][1]
            else:
                name = f"lab_{a:08X}"
        else:
            name = self.dnames.get(a, f"D_{a:08X}")
        self.labels[a] = name
        return name

    def in_data_segs(self, v: int) -> bool:
        return any(s0 <= v <= s1 for s0, s1, _ in (self.seg["rodata"], self.seg["data"], self.seg["bss"]))

    def reject(self, at: int, v: int, why: str) -> None:
        self.stats[f"ptr_reject_{why}"] += 1
        self.rejects.append((at, v, why))

    def ptr_expr(self, v: int, from_jt: bool = False, at: int = 0) -> str | None:
        """Symbol expression for a word value, or None to keep it raw.

        Every in-range value that stays raw is logged to build/ptr_unresolved.txt
        with a reason, so the choice can be reviewed."""
        ov, ov_target = self.overrides.get(at, (None, "")) if at else (None, "")
        if ov == "pcrel":
            # word holds T - (A + 8) for `add/ldr rX, pc, rX` at A: keep it relative
            m = re.fullmatch(r"(?:0x)?([0-9A-Fa-f]{8})@(?:0x)?([0-9A-Fa-f]{8})", ov_target)
            if m:
                t, ins = int(m.group(1), 16), int(m.group(2), 16)
                if (t - (ins + 8)) & 0xFFFFFFFF == v:
                    self.stats["ptr_override_pcrel"] += 1
                    ta = t & ~3
                    tn = self.label_for(ta) + (f"+{t - ta}" if t != ta else "")
                    return f"{tn} - ({self.label_for(ins)} + 8)"
            self.reject(at, v, "override_pcrel_mismatch")
            return None
        in_text = self.t0 <= v <= self.t1
        if not in_text and not self.in_data_segs(v):
            return None
        if ov == "raw":
            self.reject(at, v, "override_raw")
            return None
        if ov == "symbolize":
            self.stats["ptr_override_symbolize"] += 1
            a = v & ~3
            name = self.label_for(a)
            return name if v == a else f"{name}+{v - a}"
        if from_jt:
            if in_text and v in self.is_code:
                self.stats["jt_entries"] += 1
                return self.label_for(v)
            self.reject(at, v, "jt_target")
            return None
        if in_text and v in self.funcset:
            self.stats["ptr_text"] += 1
            return self.label_for(v)
        lo = v & 0xFFFF
        if 0x20 <= lo <= 0x7E and not in_text and self.t0 <= at < self.t1:
            # A .text literal-pool word that points into .rodata/.data/.bss is an address
            # constant even when it is UTF-16 shaped: code does not load character pairs
            # from a pool. Found by the data shift test (m1_tests.py shift): all 12 such
            # words were 4-aligned and used as pointers (vptr stores `str rX, [r0]` into
            # COMDAT vtables at 0x0049xxxx, `this`/string arguments in r0).
            self.stats["ptr_data_pool_utf16_shape"] += 1
        elif 0x20 <= lo <= 0x7E:          # looks like a UTF-16 character pair
            self.reject(at, v, "utf16")
            return None
        if in_text:
            if lo == 0 and (v & 0xFFFFF) == 0:   # round sizes like 0x00200000
                self.reject(at, v, "round")
                return None
            a = v & ~3
            if a in self.is_code:
                # Into the middle of code but not a function start: far more often an
                # integer that happens to fall in range than a real code pointer.
                self.reject(at, v, "midcode")
                return None
            self.stats["ptr_text"] += 1
        else:
            self.stats["ptr_data"] += 1
        a = v & ~3
        name = self.label_for(a)
        return name if v == a else f"{name}+{v - a}"

    # ---------------------------------------------------------------- Thumb
    def hw(self, va: int) -> int:
        return struct.unpack_from("<H", self.code, self.seg["text"][2] + va - self.t0)[0]

    def text_bytes(self, va: int, n: int) -> bytes:
        o = self.seg["text"][2] + va - self.t0
        return self.code[o: o + n]

    def thumb_runs(self) -> list[tuple[int, int]]:
        """Contiguous Thumb ranges: registry Thumb rows plus the Thumb body after each
        ARM->Thumb stub inside an ARM row (the stub's `bx ip` lands on stub+8 | 1)."""
        spans = []
        for a, (e, _) in self.thumb_rows.items():
            if self.t0 <= a < self.t1 and e > a:
                spans.append((a, min(e, self.t1)))
                self.label_for(a)
                self.stats["thumb_functions"] += 1
        starts = sorted(set(self.funcs) | set(self.thumb_rows) | {self.t1})
        text = self.text_bytes(self.t0, self.t1 - self.t0)
        i = text.find(STUB)
        while i >= 0:
            s = self.t0 + i
            if not s & 3:
                j = bisect.bisect_right(starts, s)
                f, end = starts[j - 1], starts[j]
                if f in self.funcset and s + 8 < end:
                    spans.append((s + 8, end))
                    self.stats["thumb_stub_bodies"] += 1
            i = text.find(STUB, i + 4)
        runs: list[list[int]] = []
        for a, e in sorted(spans):
            if runs and a <= runs[-1][1]:
                runs[-1][1] = max(runs[-1][1], e)
            else:
                runs.append([a, e])
        return [(a, e) for a, e in runs]

    def thumb_sweep(self, s: int, e: int, data: set[int]) -> list[tuple[int, int, str]]:
        out, a = [], s
        while a < e:
            if a in data:
                out.append((a, 4, "word"))
                a += 4
            elif thumb_pair(self.hw(a), self.hw(a + 2)) and a + 4 <= e and a + 2 not in data:
                out.append((a, 4, "ins"))
                a += 4
            else:
                out.append((a, 2, "ins"))
                a += 2
        return out

    def thumb_analyse(self, objdump: str) -> None:
        """Decide every Thumb halfword: instruction text, raw .inst.n/.inst.w, or a literal
        .word. Fills thumb_hw, thumb_run_at, thumb_items and thumb_pcrel."""
        runs = self.thumb_runs()
        self.thumb_hw: set[int] = set()
        self.thumb_run_at: dict[int, int] = {}
        self.thumb_items: dict[int, tuple] = {}
        self.thumb_pcrel: list[tuple[int, int]] = []
        layout = []
        tstarts = sorted(set(self.funcs) | set(self.thumb_rows))
        for s, e in runs:
            self.thumb_hw.update(range(s, e, 2))
            self.thumb_run_at[s] = e
            self.stats["thumb_bytes"] += e - s
            # literal words: ARM-analysis pool words, then targets of Thumb literal loads
            # (iterated: a pool swept as instructions can hide the next boundary)
            data = {a for a in range((s + 3) & ~3, e - 3, 4) if a in self.pool or a in self.jt}
            for _ in range(4):
                items = self.thumb_sweep(s, e, data)
                new = set()
                for a, size, kind in items:
                    if kind == "ins" and size == 2 and self.hw(a) & 0xF800 == 0x4800:   # ldr rX, [pc, #N]
                        t = ((a + 4) & ~3) + (self.hw(a) & 0xFF) * 4
                        # not past the start of a later function: a "load" that reaches
                        # into the next function is data swept as code (Fates 0x00103A16:
                        # the text "POSI" read as `ldr r1, [pc, #332]`)
                        nxt = bisect.bisect_right(tstarts, a)
                        later = nxt < len(tstarts) and tstarts[nxt] <= t
                        if s <= t and t + 4 <= e and not later:
                            new.add(t)
                if new <= data:
                    break
                data |= new
            for a, size, kind in items:
                if kind == "ins" and size == 2 and self.hw(a) & 0xF800 in (0x4800, 0xA000):  # ldr literal / adr
                    self.thumb_pcrel.append((a, ((a + 4) & ~3) + (self.hw(a) & 0xFF) * 4))
                    self.stats["thumb_literal_refs"] += 1
            layout += items
        # one objdump run over the instructions only (literal words left out, so its
        # linear sweep stays on our boundaries)
        blob, where = bytearray(), {}
        for a, size, kind in layout:
            if kind != "ins":
                continue
            where[len(blob)] = a
            if size == 2 and thumb32(self.hw(a)):
                blob += b"\x00\x00"            # a lone 32-bit prefix: placeholder, kept raw
            else:
                blob += self.text_bytes(a, size)
        dis: dict[int, str] = {}
        cand: list[tuple[int, str]] = []
        hdr = [".syntax unified", ".cpu mpcore", ".fpu vfpv2", ".thumb"]
        got: dict[int, str] = {}
        BUILD.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=BUILD) as td:
            bp = Path(td) / "thumb.bin"
            bp.write_bytes(bytes(blob))
            if blob:
                out = subprocess.run([objdump, "-D", "-b", "binary", "-marm", "-Mforce-thumb",
                                      "-Mreg-names-std", str(bp)],
                                     capture_output=True, text=True, check=True).stdout
                for line in out.splitlines():
                    m = THUMB_LINE.match(line)
                    if m and int(m.group(1), 16) in where:
                        txt = re.split(r"\s+[@;]\s", m.group(3), maxsplit=1)[0]
                        dis[where[int(m.group(1), 16)]] = re.sub(r"\s+", " ", txt.replace("\t", " ")).strip()
            # candidates: everything position-independent that objdump could spell
            for a, size, kind in layout:
                if kind == "word":
                    w = self.word(a)
                    self.thumb_items[a] = ("word", w, self.ptr_expr(w, at=a))
                    self.stats["thumb_words"] += 1
                    continue
                raw = (self.hw(a) << 16 | self.hw(a + 2)) if size == 4 else self.hw(a)
                txt = dis.get(a)
                why = None
                if txt is None or (size == 2 and thumb32(self.hw(a))) or any(b in txt for b in BAD):
                    why = "rejected"
                elif (size == 4 and self.hw(a) & 0xF800 == 0xF000) or T_BRANCH.match(txt):
                    why = "branch"
                elif re.search(r"\bpc\b", re.sub(r"\{[^}]*\}", "", txt.partition(" ")[2])):
                    why = "pcrel"
                self.thumb_items[a] = ("tinst", raw, size, why or "rejected")
                if why is None:
                    cand.append((a, txt))
            # keep only the spellings GNU as turns back into exactly the original bytes
            if cand:
                sp, lp = Path(td) / "thumb.s", Path(td) / "thumb.lst"
                sp.write_text("\n".join(hdr + [f"\t{t}" for _, t in cand]) + "\n")
                exe = ".exe" if os.name == "nt" else ""
                subprocess.run([str(self.bin / f"arm-none-eabi-as{exe}"),
                                "-mcpu=mpcore", "-mfpu=vfpv2", "-mfloat-abi=softfp", f"-al={lp}",
                                "-o", str(Path(td) / "thumb.o"), str(sp)], capture_output=True, text=True)
                if lp.is_file():
                    for line in lp.read_text(errors="replace").splitlines():
                        m = LISTING.match(line)
                        if m:
                            got[int(m.group(1))] = m.group(2)
        for i, (a, txt) in enumerate(cand):
            size = self.thumb_items[a][2]
            if got.get(len(hdr) + 1 + i) == self.text_bytes(a, size).hex().upper():
                self.thumb_items[a] = ("t", txt, size)
        self.thumb_symbolize_calls()
        for it in self.thumb_items.values():
            if it[0] == "t":
                self.stats["thumb_insn"] += 1
            elif it[0] == "tinst":
                self.stats["thumb_raw"] += 1
                self.stats[f"thumb_raw_{it[3]}"] += 1

    def thumb_symbolize_calls(self) -> None:
        """Thumb BL / BLX (the only 32-bit Thumb instructions on the ARM11) become
        `bl SYM` / `blx SYM`, so the linker re-aims them when code moves (most calls
        leave their section). BL must land on the start of a Thumb item, BLX on a
        4-aligned ARM instruction; anything else stays raw (m1_tests.py shift checks
        that no raw Thumb branch crosses an insertion point). The labels are untyped, so
        the linker keeps the instruction as written (no BL<->BLX rewrite, no bit 0)."""
        starts = set(self.thumb_items)
        self.thumb_suspects: set[int] = set()
        for a, it in list(self.thumb_items.items()):
            if it[0] != "tinst" or it[2] != 4:
                continue
            h1, h2 = self.hw(a), self.hw(a + 2)
            if h1 & 0xF800 != 0xF000:
                continue
            off = ((h1 & 0x7FF) << 12) | ((h2 & 0x7FF) << 1)
            off -= (1 << 23) if off & (1 << 22) else 0
            if h2 & 0xF800 == 0xF800:
                op, t = "bl", a + 4 + off
                ok = t in starts and self.thumb_items[t][0] != "word"
                # or the second half of a 4-byte item (a start the sweep did not see):
                # the label splits that item into two raw halves (thumb_lines)
                ok = ok or (t - 2 in starts and self.thumb_items[t - 2][0] != "word"
                            and self.thumb_items[t - 2][2] == 4)
                if not ok and not t & 3 and t not in self.thumb_hw and t not in self.funcset:
                    # into an ARM row (every 4-aligned ARM-side address gets its label):
                    # a Thumb function the registry misses (Fates: 0x0030119C, 0x00301A10,
                    # 0x00301A1C sit inside ARM rows). Not an ARM function start, whose
                    # %function symbol would make ld rewrite the BL into a BLX.
                    ok = True
                    self.stats["thumb_calls_into_arm_rows"] += 1
                    self.thumb_suspects.add(t)
            elif h2 & 0xF800 == 0xE800:
                op, t = "blx", ((a + 4) & ~3) + off
                ok = not t & 3 and t in self.is_code and t not in self.thumb_hw
            else:
                continue
            if ok and self.t0 <= t < self.t1:
                self.thumb_items[a] = ("tcall", f"{op} {self.label_for(t)}", 4, t)
                self.stats["thumb_calls"] += 1

    def thumb_lines(self, s: int, e: int, f: int) -> list[str]:
        """The Thumb run [s, e) inside the section of ARM function f."""
        lines = [".thumb"]
        a = s
        while a < e:
            if a in self.thumb_rows:
                end, name = self.thumb_rows[a]
                lines.append(f"@ THUMB function {name} ({end - a} bytes)")
            if a != f:
                lines += self.label_lines(a)
            it = self.thumb_items[a]
            size = 4 if it[0] == "word" else it[2]
            if size == 4 and (a + 2) in self.labels:
                # a label inside the 4 bytes (a start the sweep did not see): two halves
                lines.append(f"\t.inst.n 0x{self.hw(a):04X} @ {a:08X} T")
                lines += self.label_lines(a + 2)
                lines.append(f"\t.inst.n 0x{self.hw(a + 2):04X} @ {a + 2:08X} T")
            elif it[0] == "word":
                val = it[2] if it[2] else f"0x{it[1]:08X}"
                lines.append(f"\t.word {val} @ {a:08X}")
            elif it[0] in ("t", "tcall"):
                lines.append(f"\t{it[1]} @ {a:08X} T")
            elif size == 4:
                lines.append(f"\t.inst.w 0x{it[1]:08X} @ {a:08X} T")
            else:
                lines.append(f"\t.inst.n 0x{it[1]:04X} @ {a:08X} T")
            a += size
        lines.append(".arm")
        return lines

    # ---------------------------------------------------------------- passes
    def run(self):
        objdump = str(self.bin / "arm-none-eabi-objdump.exe" if os.name == "nt" else self.bin / "arm-none-eabi-objdump")
        self.ins = objdump_text(objdump, self.t0)
        for f in self.funcs:
            self.label_for(f)
        self.thumb_analyse(objdump)
        for a in self.dnames:          # named data (typeinfo, vtables, ...) even if unreferenced
            if self.in_data_segs(a):
                self.label_for(a)
        # pass 1: decide every text word, collect labels
        text_items = {}
        for a in range(self.t0, self.t1, 4):
            w = self.word(a)
            if a in self.thumb_hw:
                continue                   # emitted by the Thumb writer (thumb_items)
            if a in self.is_code:
                txt = self.ins.get(a)
                if a in self.raw:
                    text_items[a] = ("inst", w, "forced")
                    continue
                if txt is None or any(b in txt for b in BAD):
                    text_items[a] = ("inst", w, "bad")
                    continue
                txt = normalize(txt, w)
                m = BRANCH.match(txt)
                if m:
                    tgt = int(m.group(2), 16)
                    if self.t0 <= tgt < self.t1 and tgt in self.is_code:
                        sym = self.label_for(tgt)
                        txt = txt[: m.start(2)].rstrip()
                        txt = re.sub(r"0x$", "", txt).rstrip() + " " + sym
                    else:
                        text_items[a] = ("inst", w, "branch")
                        continue
                elif re.match(rf"^blx{COND}\s+(?:0x)?[0-9a-f]+$", txt):
                    text_items[a] = ("inst", w, "branch")
                    continue
                text_items[a] = ("insn", txt)
            elif a in self.jt:
                e = self.ptr_expr(w, from_jt=True, at=a)
                text_items[a] = ("word", w, e)
            elif a in self.pool:
                text_items[a] = ("word", w, self.ptr_expr(w, at=a))
            else:
                text_items[a] = ("word", w, None)
        data_items = {}
        for k in ("rodata", "data"):
            s0, s1, _ = self.seg[k]
            for a in range(s0, s1, 4):
                w = self.word(a)
                data_items[a] = (w, self.ptr_expr(w, at=a))
        self.text_items, self.data_items = text_items, data_items
        self.write_text()
        self.write_data()
        self.write_ldscript()
        self.write_report()

    # ---------------------------------------------------------------- writers
    def header(self) -> list[str]:
        return ["@ GENERATED by tools/gen_asm.py from the user's code.bin. Do not edit or commit.",
                ".syntax unified", ".arm", ".cpu mpcore", ".fpu vfpv2", ""]

    def label_lines(self, a: int, skip: str | None = None) -> list[str]:
        name = self.labels.get(a)
        if not name or name == skip:
            return []
        return [f".global {name}", f"{name}:"]

    def section_joins(self) -> set[int]:
        """Function starts that must NOT begin a new section.

        A PC-relative access (literal load, ADR) from one detected function into another
        means the two cannot be separated without breaking the access: either the finder
        split one function, or neighbours share a pool. Everything between source and
        target is kept in one section. Logged to build/section_merges.txt for M2 review."""
        joins, log = set(), []
        pairs = [(a, pcrel_target(self.word(a), a)) for a in sorted(self.is_code)] + self.thumb_pcrel
        for a, t in pairs:
            if t is None or not (self.t0 <= t < self.t1):
                continue
            i = bisect.bisect_right(self.funcs, a) - 1
            j = bisect.bisect_right(self.funcs, t) - 1
            if i == j:
                continue
            lo, hi = min(i, j), max(i, j)
            joins.update(self.funcs[lo + 1: hi + 1])
            log.append(f"{a:08X} -> {t:08X}  joins func_{self.funcs[lo]:08X} .. func_{self.funcs[hi]:08X}")
        self.stats["section_merge_refs"] = len(log)
        self.stats["functions_joined"] = len(joins)
        BUILD.mkdir(exist_ok=True)
        (BUILD / "section_merges.txt").write_text(
            "# PC-relative references that cross detected function starts (function-boundary\n"
            "# suspects for M2). The functions listed are emitted in one section.\n"
            + "\n".join(log) + "\n")
        return joins

    def func_lines(self, f: int, end: int, joined: bool) -> list[str]:
        name = self.labels[f]
        lines = []
        if not joined:
            lines += [f'.section .text.f_{f:08X},"ax",%progbits', ".balign 4"]
        lines += [f".global {name}", f".type {name}, %function", f"{name}:"]
        a = f
        while a < end:
            if a in self.thumb_run_at or a + 2 in self.thumb_run_at:
                if a not in self.thumb_run_at:
                    # an ARM row ending on a halfword (no stub found): its last halfword raw
                    if a != f:
                        lines += self.label_lines(a)
                    lines.append(f"\t.hword 0x{self.hw(a):04X} @ {a:08X} T")
                    a += 2
                e = self.thumb_run_at[a]
                lines += self.thumb_lines(a, e, f)
                a = e                      # a run ends where an ARM row starts (4-aligned)
                continue
            if a != f:
                lines += self.label_lines(a)
            it = self.text_items[a]
            if it[0] == "insn":
                self.stats["insn"] += 1
                lines.append(f"\t{it[1]} @ {a:08X}")
            elif it[0] == "inst":
                self.stats[f"insn_raw_{it[2]}"] += 1
                lines.append(f"\t.inst 0x{it[1]:08X} @ {a:08X}")
            else:
                self.stats["data_words"] += 1
                val = it[2] if it[2] else f"0x{it[1]:08X}"
                lines.append(f"\t.word {val} @ {a:08X}")
            a += 4
        lines.append(f".size {name}, . - {name}")
        return lines

    def write_text(self):
        out_dir = ASM / "text"
        func_dir = ASM / "func"
        for d in (out_dir, func_dir):
            d.mkdir(parents=True, exist_ok=True)
            for p in d.glob("*.s"):
                p.unlink()
        joins = self.section_joins()
        bounds = self.funcs + [self.t1]
        # A function with C++ must be a section of its own: nothing may reach into it or
        # out of it PC-relatively, or the compiled replacement could not be placed.
        bad = []
        for i, f in enumerate(self.funcs):
            if f in self.src_rows and (f in joins or bounds[i + 1] in joins):
                bad.append(f"{self.src_rows[f].name} ({f:08X}) shares a section with a neighbour "
                           "(PC-relative reference across its boundary, see build/section_merges.txt); "
                           "it cannot be replaced by C++ until the boundary is fixed")
        if bad:
            sys.exit("\n".join(bad))
        # entries in address order: ("asm", [(start, end), ...]) or ("func", start, end)
        entries, cur, cur_bytes = [], [], 0
        for i, f in enumerate(self.funcs):
            end = bounds[i + 1]
            if f in self.src_rows:
                if cur:
                    entries.append(("asm", cur))
                entries.append(("func", f, end))
                cur, cur_bytes = [], 0
                continue
            # only cut files at a section boundary
            if cur_bytes >= GROUP_BYTES and f not in joins:
                entries.append(("asm", cur))
                cur, cur_bytes = [], 0
            cur.append((f, end))
            cur_bytes += end - f
        if cur:
            entries.append(("asm", cur))
        self.text_files = []
        self.section_starts = []
        self.layout_text = []
        for e in entries:
            if e[0] == "asm":
                g = e[1]
                lines = self.header()
                for f, end in g:
                    if f not in joins:
                        self.section_starts.append(f)
                    lines += self.func_lines(f, end, f in joins)
                path = out_dir / f"text_{g[0][0]:08X}.s"
                path.write_text("\n".join(lines) + "\n")
                self.text_files.append(f"text/{path.name}")
                self.layout_text.append({"kind": "asm", "file": f"text/{path.name}"})
                continue
            _, f, end = e
            r = self.src_rows[f]
            if r.status == "nonmatching":
                self.section_starts.append(f)     # an asm section in the matching build
            lines = self.header() + [
                f"@ {r.status}: C++ in {r.source} ({r.symbol}, compiler {r.compiler})"] + \
                self.func_lines(f, end, False)
            path = func_dir / f"func_{f:08X}.s"
            path.write_text("\n".join(lines) + "\n")
            inner = [[self.labels[a], a - f] for a in range(f + 2, end, 2) if a in self.labels]
            self.layout_text.append({
                "kind": "func", "addr": f"0x{f:08X}", "end": f"0x{end:08X}", "size": end - f,
                "name": r.name, "symbol": r.symbol, "source": r.source, "status": r.status,
                "compiler": r.compiler, "asm": f"func/{path.name}", "labels": inner})

    def unit_lines(self, k: str, u) -> list[str]:
        """One data unit as one section. Labels at the unit start are inside the section
        (after .balign), so they move with it; the segment-end label goes at the end of
        the last rodata/bss unit (the .data end label is the first .bss label)."""
        name, flags = DATA_SECTION[k]
        lines = [f".section {name.format(u.start)},{flags}", ".balign 4"]
        last = u.end == self.seg[k][1]
        if k != "bss":
            for a in range(u.start, u.end, 4):
                lines += self.label_lines(a)
                w, e = self.data_items[a]
                lines.append(f"\t.word {e if e else f'0x{w:08X}'} @ {a:08X}")
            if last and k == "rodata":
                lines += self.label_lines(u.end)
            return lines
        # .bss: labels at every referenced address, .space in between
        i = bisect.bisect_left(self.bss_marks, u.start)
        j = bisect.bisect_right(self.bss_marks, u.end) if last else bisect.bisect_left(self.bss_marks, u.end)
        pos = u.start
        for a in self.bss_marks[i:j]:
            if a > pos:
                lines.append(f"\t.space 0x{a - pos:X}")
                pos = a
            lines += self.label_lines(a)
        if u.end > pos:
            lines.append(f"\t.space 0x{u.end - pos:X}")
        return lines

    def write_data(self):
        out_dir, unit_dir = ASM / "data", ASM / "dunit"
        for d in (out_dir, unit_dir):
            d.mkdir(parents=True, exist_ok=True)
            for p in d.glob("*.s"):
                p.unlink()
        b0, b1, _ = self.seg["bss"]
        self.bss_marks = sorted(a for a in self.labels if b0 <= a <= b1)
        self.layout_data: list[dict] = []
        self.data_files: list[str] = []
        for k in CX.SEGMENTS:
            group: list = []           # [(layout entry, lines)] of the file being filled
            gbytes = 0
            for u in self.units[k]:
                ul = self.unit_lines(k, u)
                e = {"seg": k, "unit": u.unit_id, "start": f"0x{u.start:08X}", "end": f"0x{u.end:08X}",
                     "size": u.end - u.start, "section": DATA_SECTION[k][0].format(u.start), "file": None}
                self.layout_data.append(e)
                d = self.data_rows.get(u.unit_id)
                if d is None:
                    if gbytes >= GROUP_BYTES:
                        self.flush_data(k, group)
                        group, gbytes = [], 0
                    group.append((e, ul))
                    gbytes += u.end - u.start
                    continue
                self.flush_data(k, group)
                group, gbytes = [], 0
                path = unit_dir / f"{u.unit_id}.s"
                path.write_text("\n".join(self.header() + [
                    f"@ {d.status}: data unit owned by {d.source} (compiler {d.compiler})"] + ul) + "\n")
                last = u.end == self.seg[k][1]
                hi = u.end + (1 if last and k != "data" else 0)
                e.update({"file": f"dunit/{path.name}", "source": d.source, "status": d.status,
                          "compiler": d.compiler,
                          "labels": [[self.labels[a], a - u.start] for a in range(u.start, hi, 4)
                                     if a in self.labels]})
            self.flush_data(k, group)
        # labels pointing at text_end / data_end / segment ends that fall in no file
        text_end_lbl = self.labels.get(self.t1)
        self.text_end_label = text_end_lbl

    def flush_data(self, k: str, group: list) -> None:
        if not group:
            return
        path = ASM / "data" / f"{k}_{int(group[0][0]['start'], 16):08X}.s"
        lines = self.header()
        for e, ul in group:
            lines += ul
            e["file"] = f"data/{path.name}"
        path.write_text("\n".join(lines) + "\n")
        self.data_files.append(f"data/{path.name}")

    def write_ldscript(self):
        """asm/link_layout.json: everything build.py needs to write the linker script."""
        for stale in ("ldscript.ld", "objects.txt"):      # pre-M3 outputs
            if (ASM / stale).exists():
                (ASM / stale).unlink()
        layout = {
            "generated_by": "tools/gen_asm.py",
            "src_map_sha1": CX.src_map_sha1(),
            "data_map_sha1": CX.data_map_sha1(),
            "data_units_sha1": self.units_digest,
            "entry": self.labels[self.t0],
            "text_start": f"0x{self.t0:08X}",
            "text_end_label": self.text_end_label,
            "segments": {k: f"0x{self.seg[k][0]:08X}" for k in ("rodata", "data", "bss")},
            "segment_ends": {k: f"0x{self.seg[k][1]:08X}" for k in ("rodata", "data", "bss")},
            "text": self.layout_text,
            "asm_aliases": self.src_aliases,
            "data_files": self.data_files,
            "data": self.layout_data,
        }
        (ASM / "link_layout.json").write_text(json.dumps(layout, indent=1) + "\n")

    def write_report(self):
        BUILD.mkdir(exist_ok=True)
        s = self.stats
        lines = [f"{k:28} {v}" for k, v in s.items()]
        lines.append(f"{'functions':28} {len(self.funcs)}")
        lines.append(f"{'labels':28} {len(self.labels)}")
        lines.append(f"{'text files':28} {len(self.text_files)}")
        lines.append(f"{'src_map functions':28} {len(self.src_rows)} "
                     f"({sum(r.status == 'matched' for r in self.src_rows.values())} matched)")
        lines.append(f"{'text sections':28} {len(self.section_starts)}")
        lines.append(f"{'data units':28} " + ", ".join(f"{k} {len(self.units[k])}" for k in CX.SEGMENTS)
                     + f" ({len(self.data_rows)} in data_map, "
                     f"{sum(d.status == 'matched' for d in self.data_rows.values())} matched)")
        lines.append(f"{'data files':28} {len(self.data_files)}")
        if getattr(self, "thumb_suspects", None):
            lines.append(f"{'thumb_call_targets_in_arm':28} "
                         + " ".join(f"{t:08X}" for t in sorted(self.thumb_suspects))
                         + "  (Thumb BL targets inside ARM rows: missed Thumb starts?)")
        (ASM / "sections.txt").write_text("".join(f"{a:08X}\n" for a in self.section_starts))
        (BUILD / "gen_report.txt").write_text("\n".join(lines) + "\n")
        print("\n".join(lines))
        why_text = {
            "utf16": "low half is a printable UTF-16 code unit; probably text",
            "round": "round power-of-two-ish size in text range",
            "midcode": "points into the middle of code, not a function start; probably an integer",
            "jt_target": "jump-table entry that does not land on decoded code",
        }
        out = ["# In-range words kept raw. These will NOT move if code shifts.",
               "# Review: a real pointer here is a shiftability bug; fix the rule in gen_asm.py.",
               "# reason codes: " + "; ".join(f"{k} = {v}" for k, v in why_text.items()),
               "# word_addr  value     reason"]
        out += [f"{a:08X}  {v:08X}  {why}" for a, v, why in sorted(self.rejects)]
        (BUILD / "ptr_unresolved.txt").write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    Gen().run()
