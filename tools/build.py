#!/usr/bin/env python3
"""Build driver (stdlib only; no make, safe with spaces in paths).

    python tools/build.py config       merge config/naming/*.csv + config/names.csv into
                                       config/functions.csv and config/data_symbols.csv
    python tools/build.py gen          regenerate asm/ from extracted/code.bin
    python tools/build.py build        compile src/ (C++), assemble asm/, link, split segments
    python tools/build.py compare      hash gate: per segment, then the padded code.bin
    python tools/build.py all          lint + gen + build + compare (default)
    python tools/build.py lint         config/src_map.csv + NONMATCHING spelling (compile.py lint)
    python tools/build.py nonmatching  NONMATCHING build into build/nonmatching/: C++ of
                                       nonmatching functions linked in place of their asm
                                       (relinks, shifts; never expected to hash-match)
    python tools/build.py clean        delete this script's outputs in build/ (objects, ELF,
                                       binaries, linker script); analysis reports are kept
    python tools/build.py fixraw       loop gen/build/compare, forcing mismatching
                                       instructions to raw .inst (config/raw_insns.txt)

Options for build/all/nonmatching: --compiler NAME compiles every source with that
profile instead of each src_map row's own (re-verification after switching compilers).

C++ (M3, docs/MATCHING.md): rows of config/src_map.csv with status `matched` have no asm
body; their compiled section is placed at the function's address by the linker script
(written here from asm/link_layout.json), and the config name and any inner labels are
bound to the compiled symbol, so asm references keep working. `nonmatching` rows keep
their asm in the matching build.

Data (docs/DATA_SPLITS.md): .rodata/.data/.bss are one input section per data unit
(config/naming/data_units.csv), placed explicitly in address order. A unit listed in
config/data_map.csv with status `matched` has no asm; the data sections of its C++ object
are placed there instead, checked for alignment, size and every label's offset.
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASM = ROOT / "asm"
BUILD = ROOT / "build"
EXT = ROOT / "extracted"
SRC = ROOT / "src"
RAW_LIST = Path(os.environ.get("FE_RAW_INSNS", ROOT / "config" / "raw_insns.txt"))   # same as gen_asm.py
EXE = ".exe" if os.name == "nt" else ""
PAGE = 0x1000
NOP = 0xE320F000

sys.path.insert(0, str(ROOT / "tools"))
import compile as CX  # noqa: E402


def tool(name: str) -> str:
    cfg_path = ROOT / "tools" / "config.local.json"
    if not cfg_path.is_file():
        sys.exit("run `python tools/toolchain.py` first")
    d = Path(json.loads(cfg_path.read_text())["binutils_dir"])
    return str(d / f"arm-none-eabi-{name}{EXE}")


def layout() -> dict:
    return json.loads((EXT / "layout.json").read_text())


def gen() -> None:
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "gen_asm.py")])
    if r.returncode:
        sys.exit("gen failed")


ERR = re.compile(r"^(.*?\.s):(\d+): Error: (.*)$")


def assemble_one(src: Path, obj: Path) -> tuple[Path, str]:
    obj.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([tool("as"), "-mcpu=mpcore", "-mfpu=vfpv2", "-mfloat-abi=softfp",
                        "-o", str(obj), str(src)], capture_output=True, text=True)
    return src, (r.stderr if r.returncode else "")


def link_layout(asm: Path) -> dict:
    p = asm / "link_layout.json"
    if not p.is_file():
        sys.exit(f"{p} missing: run `python tools/build.py gen`")
    lay = json.loads(p.read_text())
    for key, now, what in (("src_map_sha1", CX.src_map_sha1(), "config/src_map.csv"),
                           ("data_map_sha1", CX.data_map_sha1(), "config/data_map.csv"),
                           ("data_units_sha1", CX.data_units()[1], "config/naming/data_units.csv")):
        if lay.get(key) != now:
            sys.exit(f"{what} changed since asm/ was generated: run `python tools/build.py gen` (or `all`)")
    return lay


class DataPlacement:
    """The C++ data sections linked into one data unit, in placement order."""

    def __init__(self, unit: dict, obj: Path):
        self.unit = unit
        self.obj = obj
        self.sections: list[tuple[CX.Section, list[CX.Symbol]]] = []


def place_data(lay: dict, cobjs: dict[str, Path], linked_units: list[dict],
               mode: str) -> tuple[dict[str, DataPlacement], set[tuple[Path, str]], list[str], list[str]]:
    """Assign every allocated data section of the C++ objects to the data unit whose label
    it defines; check alignment, every label's offset and the unit's size.
    Returns (unit -> placement, placed (obj, section) pairs, problems, notes)."""
    problems, notes = [], []
    owner: dict[str, tuple[dict, int]] = {}       # label -> (unit entry, offset in unit)
    for e in linked_units:
        for name, off in e["labels"]:
            owner[name] = (e, off)
    placements: dict[str, DataPlacement] = {}
    placed: set[tuple[Path, str]] = set()
    for e in linked_units:
        placements[e["unit"]] = DataPlacement(e, cobjs[e["source"]])
    order: dict[str, list[tuple[int, CX.Section, list[CX.Symbol]]]] = {u: [] for u in placements}
    for src, o in sorted(cobjs.items()):
        elf = CX.Elf(o)
        for sec in elf.code_sections():
            kind = CX.data_section_kind(sec)
            if kind is None:
                continue
            syms = [x for x in elf.symbols if x.shndx == sec.index and x.name and not x.name.startswith("$")
                    and x.type not in (CX.STT_SECTION, 4)]
            hits = {(owner[x.name][0]["unit"], owner[x.name][1] - x.value) for x in syms
                    if x.name in owner and owner[x.name][0]["source"] == src}
            if not hits:
                continue                   # reported by the unplaced-section check
            units = {u for u, _ in hits}
            if len(units) > 1 or len(hits) > 1:
                problems.append(f"{src}: section {sec.name} defines labels of {sorted(units)} at inconsistent "
                                f"offsets ({sorted(hits)}): one section must sit at one place in one unit")
                continue
            (unit, base), = hits
            ue = placements[unit].unit
            if kind != ue["seg"]:
                problems.append(f"{src}: section {sec.name} holds .{kind} data but unit {unit} is in .{ue['seg']}")
                continue
            order[unit].append((base, sec, syms))
            placed.add((o, sec.name))
    for unit, pl in placements.items():
        e = pl.unit
        start, size = int(e["start"], 16), e["size"]
        defined = set()
        pos = 0
        for base, sec, syms in sorted(order[unit], key=lambda t: t[0]):
            if base != pos:
                problems.append(f"data unit {unit}: {sec.name} of {e['source']} would start at +{pos:#x}, "
                                f"its labels say +{base:#x} (missing or extra data before it)")
            if sec.align > 1 and (start + base) % sec.align:
                problems.append(f"data unit {unit}: {sec.name} wants {sec.align}-byte alignment, its original "
                                f"address {start + base:08X} is not (the linker would pad)")
            pl.sections.append((sec, syms))
            defined.update(x.name for x in syms)
            pos = base + sec.size
        missing = [n for n, off in e["labels"] if n not in defined and off < size]
        if missing:
            problems.append(f"data unit {unit}: label(s) {', '.join(missing[:6])} not defined by {e['source']} "
                            "(define them there with the asm names, extern \"C\")")
        if pos != size:
            msg = f"data unit {unit} ({e['seg']}, {e['start']}): compiled {pos:#x} bytes, original {size:#x}"
            (problems if mode == "matching" else notes).append(msg)
    return placements, placed, problems, notes


def ld_sym(name: str) -> str:
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else f'"{name}"'


def posix(p: Path) -> str:
    return p.resolve().as_posix()


def obj_pattern(obj: Path, out: Path) -> str:
    """Linker-script file pattern for an object under `out`: `*/obj/...` (no spaces)."""
    rel = obj.relative_to(out).as_posix()
    assert re.fullmatch(r"[A-Za-z0-9_./-]+", rel), rel
    return f"*/{rel}"


def build(asm: Path = ASM, out: Path = BUILD, check_layout: bool = True, src_root: Path = SRC,
          mode: str = "matching", pad_before: set[str] | frozenset = frozenset(),
          force_compiler: str | None = None,
          pad_data_before: set[str] | frozenset = frozenset()) -> list[tuple[str, int, str]]:
    """Compile src/, assemble `asm` and link into `out`. Returns assembler errors as
    (file, line, message); exits on compile/link errors.

    check_layout=False skips padding the image to the original page counts and the
    segment-address asserts (shift test and NONMATCHING builds, where .text may grow).
    mode="nonmatching" links the C++ of nonmatching functions instead of their asm.
    pad_before: symbols of compiled functions to precede with one NOP (shift test).
    pad_data_before: data unit ids to precede with one zero word (shift test)."""
    assert mode in ("matching", "nonmatching")
    out.mkdir(parents=True, exist_ok=True)
    lay = link_layout(asm)
    funcs = [e for e in lay["text"] if e["kind"] == "func"]
    linked = [e for e in funcs if e["status"] == "matched" or mode == "nonmatching"]
    linked_syms = {e["symbol"] for e in linked}
    owned_units = [e for e in lay["data"] if e.get("source")]
    linked_units = [e for e in owned_units if e["status"] == "matched" or mode == "nonmatching"]
    linked_unit_ids = {e["unit"] for e in linked_units}

    # --- C++: compile every source that has a matched/nonmatching row (code or data)
    jobs: dict[str, str] = {}
    for e in funcs + owned_units:
        prev = jobs.setdefault(e["source"], force_compiler or e["compiler"])
        if prev != (force_compiler or e["compiler"]):
            sys.exit(f"{e['source']}: rows disagree on the compiler ({prev} vs {e['compiler']})")
    cobjs = CX.compile_sources(jobs, out, mode, src_root) if jobs else {}
    placed: dict[str, CX.FuncSection] = {}
    problems, size_notes = [], []
    for e in linked:
        elf = CX.Elf(cobjs[e["source"]])
        try:
            fs = CX.function_section(elf, e["symbol"])
        except LookupError as ex:
            problems.append(f"{e['name']} ({e['addr']}): {ex}")
            continue
        placed[e["symbol"]] = fs
        addr = int(e["addr"], 16)
        if fs.align and addr % fs.align:
            problems.append(f"{e['name']}: section {fs.section} wants {fs.align}-byte alignment, "
                            f"original address {addr:08X} is not")
        if fs.size != e["size"]:
            size_notes.append(f"{e['name']} ({e['addr']}): compiled {fs.size:#x} bytes, original {e['size']:#x}")
    # C++ data: sections defining the labels of linked data units
    dplace, dplaced, dproblems, dnotes = place_data(lay, cobjs, linked_units, mode)
    problems += dproblems
    # nothing else from the C++ objects may land in the image: an unplaced function or
    # string literal would silently move code/data (orphan placement)
    for src, o in sorted(cobjs.items()):
        elf = CX.Elf(o)
        mine = {placed[s].section for s in placed if placed[s].obj == o}
        mine |= {n for ob, n in dplaced if ob == o}
        for sec in elf.code_sections():
            if sec.name not in mine:
                what = [x.name for x in elf.symbols if x.shndx == sec.index and x.type in (CX.STT_FUNC, CX.STT_OBJECT)]
                rows = "matched" if mode == "matching" else "matched/nonmatching"
                if CX.data_section_kind(sec):
                    hint = (f"is not placed by any {rows} config/data_map.csv unit (define only the labels of an "
                            "owned unit, move it under #ifdef NONMATCHING, or add a data_map row)")
                else:
                    hint = (f"is not placed by any {rows} src_map row (make it static inline, put it under "
                            "#ifdef NONMATCHING, or add a row)")
                problems.append(f"{src}: section {sec.name} ({sec.size:#x} bytes{', ' + ' '.join(what) if what else ''}) "
                                + hint)
    if problems:
        print("\n".join(problems))
        sys.exit("C++ placement failed")
    if size_notes:
        print(("size mismatch (the image cannot match):\n   " if mode == "matching" else
               "nonmatching size differences (expected):\n   ") + "\n   ".join(size_notes))
    if dnotes:
        print("nonmatching data size differences (expected):\n   " + "\n   ".join(dnotes))

    # --- asm: every asm file, plus src_map functions not replaced by C++
    asm_files = [e["file"] for e in lay["text"] if e["kind"] == "asm"]
    asm_files += [e["asm"] for e in funcs if e["symbol"] not in linked_syms]
    asm_files += lay["data_files"]
    asm_files += [e["file"] for e in owned_units if e["unit"] not in linked_unit_ids]
    srcs = [asm / s for s in asm_files]
    objs = {s: out / "obj" / Path(s).with_suffix(".o") for s in asm_files}
    errors = []
    with cf.ThreadPoolExecutor(max_workers=max(2, (os.cpu_count() or 4))) as ex:
        for src, err in ex.map(lambda p: assemble_one(*p), zip(srcs, objs.values())):
            for line in err.splitlines():
                m = ERR.match(line)
                if m:
                    errors.append((m.group(1), int(m.group(2)), m.group(3)))
            if err and not errors:
                print(err)
    if errors:
        return errors

    # --- linker script, in address order
    text = []
    for e in lay["text"]:
        if e["kind"] == "asm":
            text.append(f"    {obj_pattern(objs[e['file']], out)}(.text.*)")
        elif e["symbol"] not in linked_syms:
            text.append(f"    {obj_pattern(objs[e['asm']], out)}(.text.*)   /* {e['status']}: asm */")
            if e["name"] != e["symbol"]:          # C++ callers use the C++ symbol
                text.append(f"    {ld_sym(e['symbol'])} = {ld_sym(e['name'])};")
        else:
            fs = placed[e["symbol"]]
            if e["symbol"] in pad_before:
                text.append(f"    LONG(0x{NOP:08X})   /* shift test */")
            text.append(f"    KEEP({obj_pattern(fs.obj, out)}({fs.section}))   /* {e['addr']} {e['status']} */")
            sym = ld_sym(e["symbol"])
            if e["name"] != e["symbol"]:
                text.append(f"    {ld_sym(e['name'])} = {sym};")
            for lname, off in e["labels"]:
                text.append(f"    {ld_sym(lname)} = {sym} + {off:#x};")
            if e["labels"] and e["status"] == "nonmatching":
                # the compiled code differs, so an inner label at its original offset is
                # only right if nothing outside the function uses it
                print(f"note: {e['name']}: {len(e['labels'])} inner label(s) bound at their original "
                      f"offsets ({', '.join(n for n, _ in e['labels'][:3])}); only valid if unused elsewhere")
    text.append("    *(.text)")
    # src_map status=asm rows: let C++ call still-asm functions by their C++ symbol
    for sym, name in lay.get("asm_aliases", []):
        text.append(f"    {ld_sym(sym)} = {ld_sym(name)};")
    if lay.get("text_end_label"):
        text.append(f"    {ld_sym(lay['text_end_label'])} = .;")
    seg = {k: int(v, 16) for k, v in lay["segments"].items()}
    asserts = "".join(f'  ASSERT(ADDR(.{k}) == 0x{v:08X}, "{k} moved")\n' for k, v in seg.items()) \
        if check_layout else ""
    # --- data: one input section per unit, in address order
    dlines: dict[str, list[str]] = {k: [] for k in CX.SEGMENTS}
    for e in lay["data"]:
        L = dlines[e["seg"]]
        if check_layout:
            L.append(f'    ASSERT(ABSOLUTE(.) == {e["start"]}, "data unit {e["unit"]} moved");')
        if e["unit"] in pad_data_before:
            L.append("    . += 4;   /* shift test */" if e["seg"] == "bss" else "    LONG(0)   /* shift test */")
        if e["unit"] in linked_unit_ids:
            pl = dplace[e["unit"]]
            L.append(f"    /* {e['unit']} {e['status']}: C++ {e['source']} */")
            for sec, _syms in pl.sections:
                if sec.align > 1:
                    L.append(f'    ASSERT((ABSOLUTE(.) & {sec.align - 1:#x}) == 0, '
                             f'"{e["unit"]}: {sec.name} needs {sec.align}-byte alignment");')
                L.append(f"    KEEP({obj_pattern(pl.obj, out)}({sec.name}))")
            for name, off in e["labels"]:
                if off == e["size"]:               # segment-end label after the last unit
                    L.append(f"    {ld_sym(name)} = .;")
        else:
            L.append(f"    {obj_pattern(objs[e['file']], out)}({e['section']})")
    if check_layout:
        for k, v in lay["segment_ends"].items():
            dlines[k].append(f'    ASSERT(ABSOLUTE(.) == {v}, "{k} end moved");')
    script = (f"/* GENERATED by tools/build.py from asm/link_layout.json ({mode} build) */\n"
              "OUTPUT_ARCH(arm)\n"
              f"ENTRY({ld_sym(lay['entry'])})\n"
              "SECTIONS\n{\n"
              f"  . = {lay['text_start']};\n"
              "  .text : {\n" + "\n".join(text) + "\n  }\n"
              "  . = ALIGN(0x1000);\n"
              "  .rodata : {\n" + "\n".join(dlines["rodata"]) + "\n  }\n"
              "  . = ALIGN(0x1000);\n"
              "  .data : {\n" + "\n".join(dlines["data"]) + "\n  }\n"
              "  .bss (NOLOAD) : {\n" + "\n".join(dlines["bss"]) + "\n  }\n"
              # linker-generated sections; any content here (veneers, glue) would not
              # exist in the original, so it must stay empty
              "  .linker_stubs : { *(.glue_7) *(.glue_7t) *(.vfp11_veneer) *(.v4_bx) *(.iplt) *(.igot.plt) "
              "*(.rel.iplt) *(.rel.dyn) }\n"
              '  ASSERT(SIZEOF(.linker_stubs) == 0, "linker generated veneers/glue")\n'
              # the assembler's default .data/.bss in every object; data lives only in
              # per-unit sections, so these must stay empty
              "  .default_data (NOLOAD) : { *(.data) *(.bss) }\n"
              '  ASSERT(SIZEOF(.default_data) == 0, "data outside the per-unit sections")\n'
              "  .ARM.attributes 0 : { KEEP(*(.ARM.attributes)) }\n"
              "  /DISCARD/ : { *(.comment) *(.note*) */obj/cxx/*(*) }\n"
              f"{asserts}}}\n")
    ldscript = out / "ldscript.ld"
    ldscript.write_text(script)

    elf = out / "fe1.elf"
    link_objs = [objs[s] for s in asm_files] + sorted(set(cobjs.values()))
    r = subprocess.run([tool("ld"), "-T", str(ldscript), "-nostdlib",
                        # every input section must be placed by the script: an orphan
                        # would be appended somewhere and shift the image
                        "--no-warn-rwx-segments", "--orphan-handling=error",
                        # Thumb `blx SYM` to ARM code stays a BLX: by default ld (with its
                        # ARM1176 erratum fix on a v6K object) routes Thumb->ARM calls
                        # through added stubs, which would grow .text
                        "--use-blx",
                        "-Map", str(out / "fe1.map"),
                        "-o", str(elf)] + [posix(o) for o in link_objs], capture_output=True, text=True)
    if r.returncode:
        print(r.stderr)
        sys.exit("link failed")
    for sec in ("text", "rodata", "data"):
        subprocess.run([tool("objcopy"), "-O", "binary", "-j", f".{sec}", str(elf),
                        str(out / f"{sec}.bin")], check=True)
    if dplace:
        addrs = dict((n, a) for a, n in sym_map(out))
        moved = []
        for pl in dplace.values():
            e = pl.unit
            for name, off in e["labels"]:
                got = addrs.get(name)
                if got is None:
                    moved.append(f"{name} ({e['unit']}) missing from the link")
                elif check_layout and not pad_data_before and got != int(e["start"], 16) + off:
                    moved.append(f"{name} ({e['unit']}) linked at {got:08X}, original {int(e['start'], 16) + off:08X}")
        if moved:
            print("C++ data placement check:\n   " + "\n   ".join(moved))
            if check_layout and mode == "matching":
                sys.exit("C++ data not at its original addresses")
        print(f"linked {len(dplace)} C++ data unit(s) ({mode} build): "
              + ", ".join(f"{u} <- {pl.unit['source']}" for u, pl in sorted(dplace.items())))
    if placed:
        addrs = dict((n, a) for a, n in sym_map(out))
        moved = []
        for e in linked:
            got = addrs.get(e["symbol"])
            if got is None:
                moved.append(f"{e['symbol']} missing from the link")
            elif check_layout and not pad_before and got != int(e["addr"], 16):
                moved.append(f"{e['name']} linked at {got:08X}, original {e['addr']}")
        if moved:
            print("C++ placement check:\n   " + "\n   ".join(moved))
            if check_layout and mode == "matching":
                sys.exit("C++ functions not at their original addresses")
        print(f"linked {len(placed)} C++ function(s) ({mode} build): "
              f"{sum(e['status'] == 'matched' for e in linked)} matched, "
              f"{sum(e['status'] == 'nonmatching' for e in linked)} nonmatching")
    if check_layout:
        lay = layout()
        img = bytearray()
        for sec in ("text", "rodata", "data"):
            b = (out / f"{sec}.bin").read_bytes()
            img += b + bytes(max(0, lay[sec]["pages"] * PAGE - len(b)))
        (out / "code.bin").write_bytes(img)
    return []


def sym_map(out: Path = BUILD) -> list[tuple[int, str]]:
    res = subprocess.run([tool("nm"), "-n", str(out / "fe1.elf")], capture_output=True, text=True).stdout
    syms = []
    for line in res.splitlines():
        p = line.split()
        if len(p) == 3 and not p[2].startswith("$"):
            syms.append((int(p[0], 16), p[2]))
    return syms


def nearest(syms, va):
    """'func_X+0xN' for the containing function (or data label), plus the nearest label."""
    best = func = None
    for a, n in syms:
        if a > va:
            break
        best = (a, n)
        if not n.startswith("lab_"):
            func = (a, n)
    if not best:
        return hex(va)
    s = f"{func[1]}+0x{va - func[0]:X}" if func else ""
    if best != func:
        s += f", near {best[1]}+0x{va - best[0]:X}"
    return s


def compare(verbose=True, out: Path = BUILD) -> list[int]:
    """Returns mismatching .text word addresses (empty = OK)."""
    lay = layout()
    ok = True
    bad_words = []
    for sec in ("text", "rodata", "data"):
        if not (out / f"{sec}.bin").is_file():
            if verbose:
                print(f"{sec:7} MISSING ({out / f'{sec}.bin'} not built: run `python tools/build.py build`)")
            return [-1]
        got = (out / f"{sec}.bin").read_bytes()
        want = (EXT / f"{sec}.bin").read_bytes()
        good = hashlib.sha1(got).hexdigest() == lay[sec]["sha1"]
        ok &= good
        if verbose:
            print(f"{sec:7} {'OK' if good else 'FAIL'}  ({len(got):#x} bytes, want {len(want):#x})")
        if not good:
            n = min(len(got), len(want))
            diffs = [i for i in range(0, n - n % 4, 4) if got[i:i + 4] != want[i:i + 4]]
            if len(got) != len(want):
                diffs.append(n - n % 4)
            base = lay[sec]["addr"]
            if verbose and diffs:
                syms = sym_map(out)
                for i in diffs[:10]:
                    g = struct.unpack_from("<I", got, i)[0] if i + 4 <= len(got) else None
                    w = struct.unpack_from("<I", want, i)[0] if i + 4 <= len(want) else None
                    print(f"   first diffs: {base + i:08X} ({nearest(syms, base + i)}) got {g and f'{g:08X}'} want {w and f'{w:08X}'}")
                print(f"   {len(diffs)} differing words")
            if sec == "text":
                bad_words = [base + i for i in diffs]
    full = hashlib.sha1((out / "code.bin").read_bytes()).hexdigest()
    good = full == lay["code_bin"]["sha1"]
    if verbose:
        print(f"code.bin {'OK' if good else 'FAIL'}  sha1 {full}")
    return [] if (ok and good) else (bad_words or [-1])


def add_raw(addrs: set[int]) -> None:
    RAW_LIST.parent.mkdir(exist_ok=True)
    cur = set()
    if RAW_LIST.is_file():
        cur = {int(x, 16) for x in RAW_LIST.read_text().split()}
    cur |= addrs
    RAW_LIST.write_text("".join(f"{a:08X}\n" for a in sorted(cur)))


def addr_of_error(f: str, line: int) -> int | None:
    try:
        txt = Path(f).read_text().splitlines()[line - 1]
    except (OSError, IndexError):
        return None
    m = re.search(r"@ ([0-9A-F]{8})\s*$", txt)
    return int(m.group(1), 16) if m else None


def fixraw(rounds: int = 6) -> int:
    for r in range(rounds):
        gen()
        errs = build()
        if errs:
            addrs = {a for a in (addr_of_error(f, l) for f, l, _ in errs) if a is not None}
            msgs = {}
            for _, _, m in errs:
                k = re.sub(r"`.*'", "`...'", m)
                msgs[k] = msgs.get(k, 0) + 1
            print(f"round {r}: {len(errs)} assembler errors -> {len(addrs)} raw; top: {sorted(msgs.items(), key=lambda x: -x[1])[:5]}")
            if not addrs:
                for e in errs[:20]:
                    print(e)
                return 1
            add_raw(addrs)
            continue
        bad = compare(verbose=False)
        if not bad:
            compare()
            print(f"round {r}: MATCH")
            return 0
        if bad == [-1]:
            compare()
            print("mismatch outside .text instructions; fix the generator")
            return 1
        print(f"round {r}: {len(bad)} mismatching text words -> raw")
        add_raw(set(bad))
    compare()
    return 1


def lint() -> bool:
    errs = CX.lint()
    for e in errs:
        print(e)
    print(f"lint: {'OK' if not errs else f'{len(errs)} problem(s)'}")
    return not errs


def nonmatching(force_compiler: str | None = None) -> int:
    """Link every nonmatching function's C++ in place of its asm (build/nonmatching/)."""
    out = BUILD / "nonmatching"
    errs = build(ASM, out, check_layout=False, mode="nonmatching", force_compiler=force_compiler)
    if errs:
        for e in errs[:30]:
            print(e)
        return 1
    lay = layout()
    for sec in ("text", "rodata", "data"):
        got = (out / f"{sec}.bin").read_bytes()
        same = hashlib.sha1(got).hexdigest() == lay[sec]["sha1"]
        print(f"{sec:7} {'same as original' if same else 'differs'} ({len(got):#x} bytes, original {lay[sec]['size']:#x})")
    print("NONMATCHING build linked (it is not expected to hash-match)")
    return 0


def clean() -> int:
    """Remove only what build() writes into build/ (never analysis reports or caches)."""
    for d in (BUILD / "obj", BUILD / "nonmatching"):
        if d.exists():
            shutil.rmtree(d)
    for n in ("fe1.elf", "fe1.map", "ldscript.ld", "text.bin", "rodata.bin", "data.bin", "code.bin"):
        if (BUILD / n).exists():
            (BUILD / n).unlink()
    print("cleaned build/obj, build/nonmatching and the link outputs")
    return 0


def main() -> int:
    args = sys.argv[1:]
    force = None
    if "--compiler" in args:
        i = args.index("--compiler")
        force = args[i + 1]
        del args[i:i + 2]
    cmd = args[0] if args else "all"
    if cmd == "config":
        return subprocess.run([sys.executable, str(ROOT / "tools" / "make_config.py")]).returncode
    if cmd == "gen":
        gen()
    elif cmd == "build":
        errs = build(force_compiler=force)
        for e in errs[:30]:
            print(e)
        return 1 if errs else 0
    elif cmd == "compare":
        return 0 if not compare() else 1
    elif cmd == "fixraw":
        return fixraw()
    elif cmd == "lint":
        return 0 if lint() else 1
    elif cmd == "nonmatching":
        return nonmatching(force)
    elif cmd == "clean":
        return clean()
    elif cmd == "all":
        if not lint():
            return 1
        gen()
        errs = build(force_compiler=force)
        if errs:
            for e in errs[:30]:
                print(e)
            return 1
        return 0 if not compare() else 1
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
