#!/usr/bin/env python3
"""M3: compile C++ from src/ for the matching build (stdlib only).

Owns: compiler profiles, config/src_map.csv parsing and lint, cached compilation, and a
small ELF32 reader (sections, symbols, relocations) used by build.py and diff_func.py.

    python tools/compile.py lint                  check src_map.csv + NONMATCHING spelling
    python tools/compile.py list                  show src_map rows and their profiles
    python tools/compile.py SRC.cpp [...]         compile (matching mode) and list sections
          [--nonmatching] [--compiler NAME] [--out DIR]
    python tools/compile.py profiles              show resolved compiler profiles
    python tools/compile.py use gcc|armcc [PATH]  set the default profile (and armcc's
                                                  path) in tools/config.local.json

Data owned by C++: config/data_map.csv (unit_id,source,status,compiler) is read and
linted here too; units come from config/naming/data_units.csv (docs/DATA_SPLITS.md).

Compiler profiles (docs/MATCHING.md section 3). A src_map row's `compiler` column names a
profile; every source file is compiled by exactly one profile.

    gcc-standin  kind gcc, the bundled arm-none-eabi-g++ (path derived from binutils_dir).
                 A stand-in only: it matches trivial leaf functions, nothing more.
    armcc        kind armcc, the original compiler. Not bundled; the user supplies the
                 path. Flags are the STRATEGY.md 3.1 hypothesis plus --split_sections.

tools/config.local.json may carry a "cxx" entry that overrides a profile's path/flags:

    "cxx": {"kind": "armcc", "path": "C:/ARM/RVCT/bin/armcc.exe", "flags": [...]}

(or a list of such objects). kind gcc -> profile gcc-standin, kind armcc -> profile armcc.
"flags" replaces the default flags of that profile; "extra_flags" appends. The first
entry's kind is the default profile for new work (diff_func.py without --compiler).

Objects are cached under <out>/obj/cxx/<mode>/... with a JSON stamp holding the exact
command line and the SHA-1 of the source and of every header under include/ and src/
(conservative: any header change recompiles everything, so an object is never stale).
"""
from __future__ import annotations

import concurrent.futures as cf
import csv
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
INCLUDE = ROOT / "include"
SRC_MAP = ROOT / "config" / "src_map.csv"
DATA_MAP = ROOT / "config" / "data_map.csv"
DATA_UNITS = ROOT / "config" / "naming" / "data_units.csv"
FUNCS_CSV = ROOT / "config" / "functions.csv"
DATA_CSV = ROOT / "config" / "data_symbols.csv"
CONFIG = ROOT / "tools" / "config.local.json"
EXE = ".exe" if os.name == "nt" else ""

STATUSES = ("matched", "nonmatching", "asm")
SRC_MAP_FIELDS = ["addr", "name", "symbol", "source", "status", "compiler"]
DATA_STATUSES = ("matched", "nonmatching")
DATA_MAP_FIELDS = ["unit_id", "source", "status", "compiler"]
SEGMENTS = ("rodata", "data", "bss")
SAFE_PATH = re.compile(r"^src/[A-Za-z0-9_./-]+\.(cpp|cc|c)$")

# ----------------------------------------------------------------------------- profiles
# Default flags. gcc: stand-in that mirrors the armcc hypothesis where gcc has an equivalent.
# -mfloat-abi=hard, not softfp: the binary returns floats in s0 (ishii__MovableObject__vf05
# = `vldr s0,[r0,#4]; bx lr`), takes float arguments in s0 (nine `vstr s0,[r0,#N]; bx lr`
# setters at 0x380468-0x380524) and passes s0 to virtual calls (GameMenu__vf41). That is
# the VFP (hard-float) calling convention; armcc's `--fpu=VFPv2` is expected to imply it
# (docs/MATCHING.md 3.2).
GCC_FLAGS = ["-marm", "-mcpu=mpcore", "-mfpu=vfpv2", "-mfloat-abi=hard", "-O2",
             "-ffunction-sections", "-fdata-sections", "-fno-exceptions", "-fno-rtti",
             "-fno-unwind-tables", "-fno-asynchronous-unwind-tables", "-fno-common",
             "-fno-threadsafe-statics", "-ffreestanding", "-g0", "-std=gnu++17",
             "-Wall", "-Werror=return-type"]
# armcc: STRATEGY.md 3.1 starting hypothesis (every flag [low] until spike S1).
ARMCC_FLAGS = ["--cpp", "--arm", "--cpu=MPCore", "--fpu=VFPv2", "-O3", "-Otime",
               "--split_sections", "--rtti", "--no_exceptions"]


@dataclass
class Profile:
    name: str
    kind: str                      # gcc | armcc
    path: str | None
    flags: list[str]
    extra_flags: list[str] = field(default_factory=list)

    def available(self) -> bool:
        return bool(self.path) and Path(self.path).is_file()

    def command(self, src: Path, obj: Path, defines: list[str], includes: list[Path]) -> list[str]:
        """Full compile command. Paths are absolute; no shell is involved."""
        inc = [f"-I{p}" for p in includes]
        dfs = [f"-D{d}" for d in defines]
        if self.kind == "gcc":
            return [self.path, *self.flags, *self.extra_flags, *dfs, *inc, "-c", str(src), "-o", str(obj)]
        if self.kind == "armcc":
            return [self.path, *self.flags, *self.extra_flags, *dfs, *inc, "-c", str(src), "-o", str(obj)]
        raise ValueError(f"unknown compiler kind {self.kind!r}")


def local_config() -> dict:
    return json.loads(CONFIG.read_text()) if CONFIG.is_file() else {}


def profiles() -> dict[str, Profile]:
    cfg = local_config()
    gxx = None
    if cfg.get("binutils_dir"):
        gxx = str(Path(cfg["binutils_dir"]) / f"arm-none-eabi-g++{EXE}")
    prof = {
        "gcc-standin": Profile("gcc-standin", "gcc", gxx, list(GCC_FLAGS)),
        "armcc": Profile("armcc", "armcc", None, list(ARMCC_FLAGS)),
    }
    entries = cfg.get("cxx") or []
    if isinstance(entries, dict):
        entries = [entries]
    for e in entries:
        kind = e.get("kind", "gcc")
        name = e.get("profile") or {"gcc": "gcc-standin", "armcc": "armcc"}.get(kind)
        if name is None:
            sys.exit(f"config.local.json cxx: unknown kind {kind!r}")
        p = prof.setdefault(name, Profile(name, kind, None, []))
        p.kind = kind
        if e.get("path"):
            p.path = e["path"]
        if "flags" in e:
            p.flags = list(e["flags"])
        p.extra_flags = list(e.get("extra_flags", []))
    return prof


def default_profile_name() -> str:
    entries = local_config().get("cxx") or []
    if isinstance(entries, dict):
        entries = [entries]
    if entries:
        e = entries[0]
        return e.get("profile") or {"gcc": "gcc-standin", "armcc": "armcc"}[e.get("kind", "gcc")]
    return "gcc-standin"


# ----------------------------------------------------------------------------- src_map
@dataclass
class Row:
    addr: int
    name: str
    symbol: str
    source: str        # repo-relative, e.g. src/game/MI_DualTag.cpp
    status: str
    compiler: str
    line: int = 0


def read_src_map(path: Path = SRC_MAP) -> list[Row]:
    if not path.is_file():
        return []
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        if rd.fieldnames != SRC_MAP_FIELDS:
            sys.exit(f"{path.name}: header must be {','.join(SRC_MAP_FIELDS)}")
        for i, r in enumerate(rd, start=2):
            rows.append(Row(int(r["addr"], 16), r["name"].strip(), r["symbol"].strip(),
                            r["source"].strip(), r["status"].strip(), r["compiler"].strip(), i))
    return rows


def src_map_sha1(path: Path = SRC_MAP) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest() if path.is_file() else ""


@dataclass
class DataRow:
    unit_id: str       # config/naming/data_units.csv unit_id, e.g. bss_00505D54
    source: str        # repo-relative src/....cpp that defines the unit's data
    status: str        # matched | nonmatching
    compiler: str      # profile name; one compiler per source (shared with src_map.csv)
    line: int = 0


def read_data_map(path: Path = DATA_MAP) -> list[DataRow]:
    """config/data_map.csv: data units owned by a C++ translation unit (docs/DATA_SPLITS.md)."""
    if not path.is_file():
        return []
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        if rd.fieldnames != DATA_MAP_FIELDS:
            sys.exit(f"{path.name}: header must be {','.join(DATA_MAP_FIELDS)}")
        for i, r in enumerate(rd, start=2):
            rows.append(DataRow(r["unit_id"].strip(), r["source"].strip(), r["status"].strip(),
                                r["compiler"].strip(), i))
    return rows


def data_map_sha1(path: Path = DATA_MAP) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest() if path.is_file() else ""


@dataclass
class DataUnit:
    unit_id: str
    seg: str
    start: int
    end: int           # exclusive
    tu: str


def read_data_units(path: Path = DATA_UNITS) -> list[DataUnit]:
    """config/naming/data_units.csv (tools/m2/data_objects.py), in file order."""
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [DataUnit(r["unit_id"], r["segment"], int(r["start"], 16), int(r["end"], 16), r["tu"])
                for r in csv.DictReader(f)]


SYNTH_UNIT_BYTES = 0x10000


def synthetic_data_units(layout_path: Path = ROOT / "extracted" / "layout.json",
                         chunk: int = SYNTH_UNIT_BYTES) -> list[DataUnit]:
    """Stand-in data units before tools/m2/data_objects.py has run for this game (a new
    port): each of .rodata/.data/.bss cut into 4-aligned chunks of `chunk` bytes. Enough
    for the M1 byte-identical round trip (nothing moves); no C++ can own such a unit, so
    data_map.csv rows are refused against them (their unit ids do not exist)."""
    lay = json.loads(Path(layout_path).read_text())
    segs = {k: (lay[k]["addr"], lay[k]["addr"] + lay[k]["size"]) for k in ("rodata", "data")}
    segs["bss"] = (segs["data"][1], segs["data"][1] + lay["bss_size"])
    out = []
    for k in SEGMENTS:
        a, end = segs[k]
        while a < end:
            b = min(end, a + chunk)
            out.append(DataUnit(f"{k}_{a:08X}", k, a, b, "synthetic"))
            a = b
    return out


def data_units(path: Path = DATA_UNITS) -> tuple[list[DataUnit], str]:
    """(units, digest): the real table when it exists, else synthetic chunks. The digest
    goes into asm/link_layout.json so build.py notices when the table appears or changes."""
    if path.is_file():
        units = read_data_units(path)
        if units:
            return units, hashlib.sha1(path.read_bytes()).hexdigest()
    units = synthetic_data_units()
    return units, f"synthetic-{SYNTH_UNIT_BYTES:#x}"


def data_section_kind(sec: "Section") -> str | None:
    """Segment an allocated, non-executable object section belongs to (compiler-neutral:
    by ELF type and flags, not by name): bss (NOBITS), data (writable), rodata (else)."""
    if not sec.flags & SHF_ALLOC or sec.flags & SHF_EXECINSTR:
        return None
    if sec.type == SHT_NOBITS:
        return "bss"
    return "data" if sec.flags & SHF_WRITE else "rodata"


def read_functions() -> dict[int, tuple[int, str]]:
    """addr -> (end, name) from config/functions.csv."""
    out = {}
    with FUNCS_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[int(r["addr"], 16)] = (int(r["end"], 16), r["name"])
    return out


def source_path(source: str, src_root: Path = SRC) -> Path:
    """Map a src_map `source` (repo-relative, starting with src/) into src_root."""
    rel = Path(source).relative_to("src")
    return src_root / rel


# ----------------------------------------------------------------------------- ELF32
SHT_SYMTAB, SHT_RELA, SHT_NOBITS, SHT_REL = 2, 4, 8, 9
SHF_WRITE, SHF_ALLOC, SHF_EXECINSTR = 0x1, 0x2, 0x4
STT_OBJECT, STT_FUNC, STT_SECTION = 1, 2, 3
R_ARM = {0: "NONE", 1: "PC24", 2: "ABS32", 3: "REL32", 28: "CALL", 29: "JUMP24", 40: "V4BX",
         42: "PREL31", 43: "MOVW_ABS_NC", 44: "MOVT_ABS"}


@dataclass
class Section:
    index: int
    name: str
    type: int
    flags: int
    offset: int
    size: int
    link: int
    info: int
    align: int
    entsize: int
    addr: int = 0


@dataclass
class Symbol:
    name: str
    value: int
    size: int
    type: int
    bind: int
    shndx: int


@dataclass
class Reloc:
    offset: int
    type: int
    sym: Symbol
    addend: int | None      # None for REL (addend is implicit in the word)

    @property
    def tname(self) -> str:
        return R_ARM.get(self.type, str(self.type))


class Elf:
    """Minimal little-endian ELF32 relocatable reader (enough for compiler objects)."""

    def __init__(self, path: Path):
        self.path = path
        d = self.d = path.read_bytes()
        if d[:4] != b"\x7fELF" or d[4] != 1 or d[5] != 1:
            raise ValueError(f"{path}: not a little-endian ELF32 file")
        (self.e_type, self.e_machine, _, _, _, shoff, self.e_flags, _, _, _, shentsize,
         shnum, shstrndx) = struct.unpack_from("<HHIIIIIHHHHHH", d, 16)
        raw = [struct.unpack_from("<IIIIIIIIII", d, shoff + i * shentsize) for i in range(shnum)]
        stro = raw[shstrndx][4]
        self.sections = [Section(i, self._str(stro, r[0]), r[1], r[2], r[4], r[5], r[6], r[7], r[8], r[9], r[3])
                         for i, r in enumerate(raw)]
        self.symbols: list[Symbol] = []
        for s in self.sections:
            if s.type == SHT_SYMTAB:
                so = self.sections[s.link].offset
                for i in range(s.size // 16):
                    nm, val, sz, info, _oth, shndx = struct.unpack_from("<IIIBBH", d, s.offset + 16 * i)
                    self.symbols.append(Symbol(self._str(so, nm), val, sz, info & 0xF, info >> 4, shndx))
                break
        for sym in self.symbols:       # section symbols get the section's name
            if sym.type == STT_SECTION and not sym.name and sym.shndx < len(self.sections):
                sym.name = self.sections[sym.shndx].name

    def _str(self, off: int, i: int) -> str:
        e = self.d.index(b"\0", off + i)
        return self.d[off + i:e].decode("utf-8", "replace")

    def data(self, sec: Section) -> bytes:
        return b"\0" * sec.size if sec.type == SHT_NOBITS else self.d[sec.offset:sec.offset + sec.size]

    def relocs(self, sec: Section) -> list[Reloc]:
        out = []
        for r in self.sections:
            if r.type in (SHT_REL, SHT_RELA) and r.info == sec.index:
                ent = 12 if r.type == SHT_RELA else 8
                for i in range(r.size // ent):
                    if r.type == SHT_RELA:
                        off, info, add = struct.unpack_from("<IIi", self.d, r.offset + ent * i)
                    else:
                        (off, info), add = struct.unpack_from("<II", self.d, r.offset + ent * i), None
                    out.append(Reloc(off, info & 0xFF, self.symbols[info >> 8], add))
        return sorted(out, key=lambda x: x.offset)

    def defined(self, name: str) -> Symbol | None:
        for s in self.symbols:
            if s.name == name and s.shndx not in (0, 0xFFF1, 0xFFF2) and s.shndx < len(self.sections):
                return s
        return None

    def code_sections(self) -> list[Section]:
        """Allocated sections with bytes in them (anything that would land in the image)."""
        return [s for s in self.sections if s.flags & SHF_ALLOC and s.size > 0]


@dataclass
class FuncSection:
    obj: Path
    section: str
    size: int
    align: int
    data: bytes
    relocs: list[Reloc]


def function_section(elf: Elf, symbol: str) -> FuncSection:
    """The section holding `symbol`. It must start the section and be alone in it
    (one function per section: gcc -ffunction-sections / armcc --split_sections)."""
    s = elf.defined(symbol)
    if s is None:
        have = sorted(x.name for x in elf.symbols if x.type == STT_FUNC and x.shndx)
        raise LookupError(f"{elf.path.name}: symbol {symbol} not defined (functions here: {', '.join(have) or 'none'})")
    sec = elf.sections[s.shndx]
    if s.value != 0:
        raise LookupError(f"{elf.path.name}: {symbol} is at +{s.value:#x} in {sec.name}, not at its start "
                          "(compile with function sections)")
    others = [x.name for x in elf.symbols if x.shndx == s.shndx and x is not s and x.type == STT_FUNC]
    if others:
        raise LookupError(f"{elf.path.name}: {sec.name} also holds {others}; need one function per section")
    return FuncSection(elf.path, sec.name, sec.size, sec.align, elf.data(sec), elf.relocs(sec))


# ----------------------------------------------------------------------------- compile
def header_digest(src_root: Path = SRC) -> str:
    """SHA-1 over every header in include/ and the source tree (conservative dependency)."""
    h = hashlib.sha1()
    for base in (INCLUDE, src_root):
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.suffix in (".h", ".hpp", ".inc", ".inl"):
                h.update(p.relative_to(base).as_posix().encode())
                h.update(p.read_bytes())
    return h.hexdigest()


_COMPILER_ID: dict[str, str] = {}


def compiler_identity(exe: str) -> str:
    """SHA-1 of the compiler binary, so replacing a compiler at the same path (e.g. a
    different armcc build) invalidates every cached object."""
    if exe not in _COMPILER_ID:
        p = Path(exe)
        if not p.is_file():
            found = shutil.which(exe)
            p = Path(found) if found else p
        _COMPILER_ID[exe] = hashlib.sha1(p.read_bytes()).hexdigest() if p.is_file() else f"missing:{exe}"
    return _COMPILER_ID[exe]


def object_path(out: Path, source: str, mode: str) -> Path:
    rel = Path(source).relative_to("src").with_suffix(".o")
    return out / "obj" / "cxx" / mode / rel


def compile_one(prof: Profile, src: Path, obj: Path, mode: str, hdr: str, src_root: Path) -> str:
    """Compile if the stamp differs. Returns '' on success, else the compiler output."""
    defines = ["DECOMP_MATCHING=1"] + (["NONMATCHING=1"] if mode == "nonmatching" else [])
    includes = [INCLUDE, src_root]
    cmd = prof.command(src, obj, defines, includes)
    stamp = obj.with_suffix(".stamp.json")
    key = {"cmd": cmd, "src": hashlib.sha1(src.read_bytes()).hexdigest(), "headers": hdr,
           "compiler": compiler_identity(cmd[0])}
    if obj.is_file() and stamp.is_file():
        try:
            if json.loads(stamp.read_text()) == key:
                return ""
        except ValueError:
            pass
    obj.parent.mkdir(parents=True, exist_ok=True)
    if stamp.exists():
        stamp.unlink()
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        return f"{src}: compile failed ({prof.name})\n  {' '.join(cmd)}\n{r.stdout}{r.stderr}"
    stamp.write_text(json.dumps(key, indent=1) + "\n")
    return ""


def compile_sources(jobs: dict[str, str], out: Path, mode: str = "matching",
                    src_root: Path = SRC, extra_flags: list[str] | None = None) -> dict[str, Path]:
    """jobs: source (repo-relative) -> profile name. Returns source -> object path.
    extra_flags are appended for every profile (diff_func.py --flags experiments).
    Exits with the compiler output on any failure."""
    prof = profiles()
    if extra_flags:
        for p in prof.values():
            p.extra_flags = p.extra_flags + list(extra_flags)
    for s, pn in sorted(jobs.items()):
        if pn not in prof:
            sys.exit(f"{s}: unknown compiler profile {pn!r} (known: {', '.join(prof)})")
        if not prof[pn].available():
            sys.exit(f"{s}: compiler profile {pn!r} has no usable path ({prof[pn].path!r}); "
                     "set \"cxx\" in tools/config.local.json (docs/MATCHING.md 3)")
    hdr = header_digest(src_root)
    objs = {s: object_path(out, s, mode) for s in jobs}
    with cf.ThreadPoolExecutor(max_workers=max(2, os.cpu_count() or 4)) as ex:
        futs = {s: ex.submit(compile_one, prof[jobs[s]], source_path(s, src_root), objs[s], mode, hdr, src_root)
                for s in sorted(jobs)}
        errs = [futs[s].result() for s in sorted(jobs)]
    errs = [e for e in errs if e]
    if errs:
        print("\n".join(errs))
        sys.exit("C++ compile failed")
    return objs


def jobs_for(rows: list[Row], statuses=("matched", "nonmatching"), force: str | None = None) -> dict[str, str]:
    """source -> profile for every source that has a row with one of `statuses`."""
    jobs: dict[str, str] = {}
    for r in rows:
        if r.status in statuses:
            jobs.setdefault(r.source, force or r.compiler)
    return jobs


# ----------------------------------------------------------------------------- lint
NM_BAD = [
    (re.compile(r"#\s*if\s*!\s*(defined\s*\(?\s*)?NONMATCHING"), "use `#ifdef NONMATCHING ... #else ASM_FUNC(...) #endif`"),
    (re.compile(r"#\s*ifndef\s+NONMATCHING"), "use `#ifdef NONMATCHING` (C++ first, ASM_FUNC in #else)"),
    (re.compile(r"#\s*if\s+NONMATCHING\b"), "use `#ifdef NONMATCHING`"),
    (re.compile(r"#\s*if\s+defined\s*\(?\s*NONMATCHING"), "use `#ifdef NONMATCHING`"),
    (re.compile(r"\bNON_MATCHING\b|\bNONMATCH\b|\bNON_MATCH\b"), "the only spelling is NONMATCHING"),
]
ASM_FUNC_RE = re.compile(r"\bASM_FUNC\s*\(\s*(0x[0-9A-Fa-f]+)\s*,\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")


def lint(rows: list[Row] | None = None, src_root: Path = SRC) -> list[str]:
    """Problems as strings (empty = clean)."""
    rows = read_src_map() if rows is None else rows
    errs = []
    funcs = read_functions()
    prof = profiles()
    seen_addr, seen_sym, src_comp = {}, {}, {}
    for r in rows:
        at = f"src_map.csv:{r.line}"
        if r.addr not in funcs:
            errs.append(f"{at}: {r.addr:#010x} is not a function start in config/functions.csv")
        elif funcs[r.addr][1] != r.name:
            errs.append(f"{at}: name {r.name} != config name {funcs[r.addr][1]} (renamed? update src_map)")
        if r.status not in STATUSES:
            errs.append(f"{at}: status {r.status!r} not in {STATUSES}")
        # status asm: a C++ symbol bound to code that is still asm; source/compiler optional
        is_asm = r.status == "asm"
        if r.compiler not in prof and not (is_asm and not r.compiler):
            errs.append(f"{at}: compiler {r.compiler!r} not a profile ({', '.join(prof)})")
        if is_asm and not r.source:
            pass
        elif not SAFE_PATH.match(r.source):
            errs.append(f"{at}: source {r.source!r} must be src/<path>.cpp with [A-Za-z0-9_./-] only")
        elif not is_asm and not source_path(r.source, src_root).is_file():
            errs.append(f"{at}: source {r.source} does not exist")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.$]*", r.symbol):
            errs.append(f"{at}: symbol {r.symbol!r} is not a plain object-file symbol")
        if r.addr in seen_addr:
            errs.append(f"{at}: address {r.addr:#010x} already mapped on line {seen_addr[r.addr]}")
        seen_addr[r.addr] = r.line
        if r.symbol in seen_sym:
            errs.append(f"{at}: symbol {r.symbol} already used on line {seen_sym[r.symbol]}")
        seen_sym[r.symbol] = r.line
        if r.status != "asm":
            prev = src_comp.setdefault(r.source, r.compiler)
            if prev != r.compiler:
                errs.append(f"{at}: {r.source} is compiled by {prev} elsewhere; one compiler per source file")
    # config/data_map.csv: data units owned by C++ (docs/DATA_SPLITS.md)
    units = {u.unit_id: u for u in read_data_units()}
    seen_unit = {}
    for d in read_data_map():
        at = f"data_map.csv:{d.line}"
        if d.unit_id not in units:
            errs.append(f"{at}: unit {d.unit_id!r} is not in config/naming/data_units.csv")
        if d.status not in DATA_STATUSES:
            errs.append(f"{at}: status {d.status!r} not in {DATA_STATUSES}")
        if d.compiler not in prof:
            errs.append(f"{at}: compiler {d.compiler!r} not a profile ({', '.join(prof)})")
        if not SAFE_PATH.match(d.source):
            errs.append(f"{at}: source {d.source!r} must be src/<path>.cpp with [A-Za-z0-9_./-] only")
        elif not source_path(d.source, src_root).is_file():
            errs.append(f"{at}: source {d.source} does not exist")
        else:
            txt = source_path(d.source, src_root).read_text(encoding="utf-8")
            if d.unit_id not in txt:
                errs.append(f"{d.source}: must mention {d.unit_id} (comment above the unit's data)")
        if d.unit_id in seen_unit:
            errs.append(f"{at}: unit {d.unit_id} already mapped on line {seen_unit[d.unit_id]}")
        seen_unit[d.unit_id] = d.line
        prev = src_comp.setdefault(d.source, d.compiler)
        if prev != d.compiler:
            errs.append(f"{at}: {d.source} is compiled by {prev} elsewhere; one compiler per source file")
    # per-source text checks
    by_src: dict[str, list[Row]] = {}
    for r in rows:
        if r.source:
            by_src.setdefault(r.source, []).append(r)
    for s, rs in sorted(by_src.items()):
        p = source_path(s, src_root) if SAFE_PATH.match(s) else None
        if not p or not p.is_file():
            continue
        txt = p.read_text(encoding="utf-8")
        marks = {(int(a, 16), n) for a, n in ASM_FUNC_RE.findall(txt)}
        for r in rs:
            tag = f"0x{r.addr:08X}"
            if r.status == "asm":
                continue
            if tag not in txt:
                errs.append(f"{s}: must mention {tag} (address comment above {r.name})")
            has_mark = (r.addr, r.name) in marks
            if r.status == "nonmatching" and not has_mark:
                errs.append(f"{s}: nonmatching {r.name} needs `#else ASM_FUNC({tag}, {r.name})` under #ifdef NONMATCHING")
            if r.status == "matched" and has_mark:
                errs.append(f"{s}: matched {r.name} must not have an ASM_FUNC marker")
        known = {(r.addr, r.name) for r in rs if r.status in ("nonmatching", "asm")}
        for a, n in sorted(marks - known):
            errs.append(f"{s}: ASM_FUNC(0x{a:08X}, {n}) has no nonmatching/asm row in src_map.csv")
    # NONMATCHING spelling over every source and header we own
    for base in (src_root, INCLUDE):
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.suffix not in (".c", ".cc", ".cpp", ".h", ".hpp", ".inc"):
                continue
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                for rx, why in NM_BAD:
                    if rx.search(line) and "lint-ok" not in line:
                        shown = p.relative_to(ROOT) if p.is_relative_to(ROOT) else p
                        errs.append(f"{shown.as_posix()}:{i}: {why}")
    return errs


# ----------------------------------------------------------------------------- CLI
def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "lint":
        errs = lint()
        for e in errs:
            print(e)
        print(f"lint: {'OK' if not errs else f'{len(errs)} problem(s)'} ({len(read_src_map())} src_map rows, "
              f"{len(read_data_map())} data_map rows)")
        return 1 if errs else 0
    if cmd == "use":
        # python tools/compile.py use gcc | use armcc PATH: make that kind the default
        # profile in tools/config.local.json (other keys and entries are kept)
        if len(argv) < 2 or argv[1] not in ("gcc", "armcc") or (argv[1] == "armcc" and len(argv) < 3):
            print("usage: compile.py use gcc | use armcc PATH_TO_ARMCC")
            return 2
        cfg = local_config()
        entries = cfg.get("cxx") or []
        entries = [entries] if isinstance(entries, dict) else list(entries)
        old = next((e for e in entries if e.get("kind") == argv[1]), {"kind": argv[1]})
        if len(argv) > 2:
            if not Path(argv[2]).is_file():
                print(f"{argv[2]}: not a file")
                return 2
            old["path"] = str(Path(argv[2]).resolve())
        cfg["cxx"] = [old] + [e for e in entries if e is not old]
        CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")
        print(f"default compiler profile: {default_profile_name()} (tools/config.local.json)")
        return 0
    if cmd == "profiles":
        dflt = default_profile_name()
        for p in profiles().values():
            print(f"{p.name:12} kind={p.kind:6} available={p.available()} default={p.name == dflt}")
            print(f"{'':12} path={p.path}")
            print(f"{'':12} flags={' '.join(p.flags + p.extra_flags)}")
        return 0
    if cmd == "list":
        for r in read_src_map():
            print(f"{r.addr:08X} {r.status:11} {r.compiler:12} {r.name:45} {r.symbol}  ({r.source})")
        for d in read_data_map():
            print(f"{'data':8} {d.status:11} {d.compiler:12} {d.unit_id:45} ({d.source})")
        return 0
    mode, force, out, srcs = "matching", None, ROOT / "build", []
    it = iter(argv)
    for a in it:
        if a == "--nonmatching":
            mode = "nonmatching"
        elif a == "--compiler":
            force = next(it)
        elif a == "--out":
            out = Path(next(it)).resolve()
        else:
            p = Path(a).resolve()
            srcs.append(p.relative_to(ROOT).as_posix())
    rows = read_src_map()
    jobs = {}
    for s in srcs:
        comp = force or next((r.compiler for r in rows if r.source == s and r.status != "asm"),
                             next((d.compiler for d in read_data_map() if d.source == s), default_profile_name()))
        jobs[s] = comp
    objs = compile_sources(jobs, out, mode)
    for s, o in objs.items():
        elf = Elf(o)
        print(f"{s} -> {o.relative_to(ROOT).as_posix() if o.is_relative_to(ROOT) else o}  [{jobs[s]}, {mode}]")
        for sec in elf.code_sections():
            fn = [x.name for x in elf.symbols if x.shndx == sec.index and x.type in (STT_FUNC, STT_OBJECT)]
            kind = data_section_kind(sec) or "text"
            print(f"   {sec.name:50} {sec.size:#6x} align {sec.align}  {kind:6} {' '.join(fn)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
