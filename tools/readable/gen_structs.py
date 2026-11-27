#!/usr/bin/env python3
"""Generate the guest-struct headers of the readable layer (docs/READABLE.md).

Standard library only. Layout only: no game values.

    python tools/readable/gen_structs.py gen     write include/readable/generated/*.h
    python tools/readable/gen_structs.py check   exit 1 if the headers are out of date

Inputs
    config/tables/tables.csv, config/tables/<Table>.csv   data-table layouts (docs/TABLES.md)
    config/readable/structs.csv, structs/<Name>.csv       runtime structs (Unit, ...), same
                                                          columns plus the type struct:NAME[n]
    config/readable/globals.csv                           hand-found global addresses
    config/readable/enums.csv                             enums built from array element names

Outputs (C11, for the host side of 3dsrecomp overrides)
    include/readable/generated/fe_structs.h   one packed struct per record: the guest's
        32-bit pointers are `gaddr` (uint32_t), never host pointers; every offset and every
        known size is a _Static_assert, so a wrong layout cannot compile
    include/readable/generated/fe_globals.h   G_<Table>Data / G_<Table>DataNum (the globals
        that hold each table's base and count, from tables.csv) and config/readable/globals.csv
    include/readable/generated/fe_game.h      per-game constants (title id, the one-time guard
        routine and its override literal) from config/game.json + config/readable/addresses.json

The headers live in include/readable/generated/ and not in include/generated/:
tools/gen_headers.py deletes every file in include/generated/ that it did not write.
"""
from __future__ import annotations

import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "tables"))
import tablelib as T  # noqa: E402

CONFIG = os.path.join(ROOT, "config", "readable")
OUT = os.path.join(ROOT, "include", "readable", "generated")
STRUCTS_H = os.path.join(OUT, "fe_structs.h")
GLOBALS_H = os.path.join(OUT, "fe_globals.h")
GAME_H = os.path.join(OUT, "fe_game.h")
sys.path.append(os.path.join(ROOT, "tools"))  # gamecfg (appended: tools/build.py must not shadow tools/harness/build.py)
sys.path.insert(0, HERE)

CTYPE = {(1, False): "uint8_t", (1, True): "int8_t", (2, False): "uint16_t", (2, True): "int16_t",
         (4, False): "uint32_t", (4, True): "int32_t", (8, False): "uint64_t"}


class Member:
    """One struct member: from a tablelib.Field, or a struct:NAME[n] row of a runtime struct."""

    def __init__(self, offset, size, ctype, name, count, note, elements):
        self.offset, self.size, self.ctype, self.name = offset, size, ctype, name
        self.count, self.note, self.elements = count, note, elements

    def decl(self) -> str:
        return f"{self.ctype} {self.name}[{self.count}];" if self.count > 1 else f"{self.ctype} {self.name};"


def member_from_field(f: T.Field) -> Member:
    if f.kind in ("int", "enc"):
        ctype = CTYPE[(f.width, f.signed and f.kind == "int")]
        note = f"{f.type}: encoded, see data/growth.c" if f.kind == "enc" else f.type
        return Member(f.offset, f.size, ctype, f.name, f.n, note, f.elements)
    if f.kind == "ref":
        return Member(f.offset, f.size, CTYPE[(f.width, False)], f.name, f.n, f.type, f.elements)
    if f.kind in ("flags", "enum"):
        return Member(f.offset, f.size, CTYPE[(f.width, False)], f.name, 1, f.type, [])
    if f.kind in ("str", "ptr", "lptr"):
        return Member(f.offset, f.size, "gaddr", f.name, 1, f.type, [])
    if f.kind == "pad":
        return Member(f.offset, f.size, "uint8_t", f.name, f.size, "pad", [])
    if f.kind == "hex":      # raw bytes shown as hex by the table tools (n bytes)
        return Member(f.offset, f.size, "uint8_t", f.name, f.size, f.type, [])
    raise ValueError(f"{f.name}: field kind {f.kind!r} has no C mapping (tools/readable/gen_structs.py)")


def read_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if (next(iter(r.values())) or "").strip()
                and not next(iter(r.values())).startswith("#")]


def runtime_members(name: str) -> list[tuple[Member, str]]:
    """config/readable/structs/<name>.csv: tablelib types, plus struct:NAME[n]."""
    out = []
    for row in read_csv(os.path.join(CONFIG, "structs", f"{name}.csv")):
        m = re.fullmatch(r"struct:(\w+)(?:\[(\d+)\])?", row["type"].strip())
        if m:
            el = (row.get("elements") or "").strip()
            mem = Member(int(row["offset"], 0), int(row["size"], 0), m.group(1), row["name"].strip(),
                         int(m.group(2) or 1), row["type"].strip(), el.split("|") if el else [])
        else:
            mem = member_from_field(T.Field(row, name))
        out.append((mem, row["confidence"].strip()))
    out.sort(key=lambda x: x[0].offset)
    return out


def cmt(text: str) -> str:
    """Text safe inside a C comment: no comment opener or closer (gcc -Wcomment)."""
    return text.replace("/*", "/<*>").replace("*/", "*<>/")


def emit_struct(lines: list[str], name: str, members: list[tuple[Member, str]], size: int | None,
                header: str, sizes: dict[str, int]) -> None:
    lines.append(f"/* {cmt(header)} */")
    lines.append(f"typedef struct {name} {{")
    body, at = [], 0
    for m, conf in members:
        if m.ctype in sizes and sizes[m.ctype] * m.count != m.size:
            raise SystemExit(f"{name}.{m.name}: {m.count} x {m.ctype} is not {m.size:#x} bytes")
        if m.offset < at:
            raise SystemExit(f"{name}.{m.name} at {m.offset:#x} overlaps the previous member (ends {at:#x})")
        if m.offset > at:
            body.append((f"uint8_t unknown_{at:03X}[0x{m.offset - at:X}];", f"+0x{at:03X} not described yet"))
        el = f" ({', '.join(m.elements)})" if m.elements else ""
        body.append((m.decl(), f"+0x{m.offset:03X} {m.note}{el} [{conf}]"))
        at = m.offset + m.size
    if size is not None and at < size:
        body.append((f"uint8_t unknown_{at:03X}[0x{size - at:X}];", f"+0x{at:03X} not described yet"))
    width = max(len(d) for d, _ in body)
    for d, c in body:
        lines.append(f"    {d:<{width}}  /* {cmt(c)} */")
    lines.append(f"}} {name};")
    if size is not None:
        lines.append(f"_Static_assert(sizeof({name}) == 0x{size:X}, \"{name} size\");")
    for m, _ in members:
        lines.append(f"_Static_assert(offsetof({name}, {m.name}) == 0x{m.offset:X}, \"{name}.{m.name}\");")
    lines.append("")


def gen_structs() -> str:
    reg = T.registry()
    lines = [
        "/* GENERATED by tools/readable/gen_structs.py from config/tables/<Table>.csv and",
        "   config/readable/structs/<Name>.csv -- do not edit. Layout only: no game values.",
        "   Guest view: every pointer is a 32-bit guest address (gaddr), read with",
        "   READ_FIELD() from fe_guest.h; never dereference these structs on the host.",
        "   Confidence per member in [brackets]; evidence in the CSV the struct comes from. */",
        "",
        "#ifndef FE_STRUCTS_H",
        "#define FE_STRUCTS_H",
        "",
        "#include <stddef.h>",
        "#include <stdint.h>",
        "",
        "#include \"fe_types.h\"",
        "",
        "#pragma pack(push, 1)",
        "",
    ]
    sizes: dict[str, int] = {}
    # runtime structs first: a table never contains one, but Unit contains UnitItem, so
    # they are emitted in dependency order (a struct before the structs that embed it)
    rt = read_csv(os.path.join(CONFIG, "structs.csv"))
    rt_members = {r["name"]: runtime_members(r["name"]) for r in rt}
    done: set[str] = set()

    def emit_rt(row):
        n = row["name"]
        if n in done:
            return
        for m, _ in rt_members[n]:
            if m.ctype in rt_members and m.ctype not in done:
                emit_rt(next(r for r in rt if r["name"] == m.ctype))
        size = int(row["size"], 0) if row["size"].strip() else None
        emit_struct(lines, n, rt_members[n], size, f"{n}: {row['description']} (config/readable/structs/{n}.csv)",
                    sizes)
        if size is not None:
            sizes[n] = size
        done.add(n)

    for row in rt:
        emit_rt(row)
    for n, t in reg.items():
        if not os.path.exists(T.layout_path(n)):
            continue
        fields = [(member_from_field(f), f.confidence) for f in T.load_layout(n)]
        emit_struct(lines, f"{n}Data", fields, t.size,
                    f"{n}: {t.file}, record 0x{t.size:X} bytes. {t.description} (config/tables/{n}.csv)", sizes)
    lines.append("#pragma pack(pop)")
    lines.append("")
    # enums from element names
    for row in read_csv(os.path.join(CONFIG, "enums.csv")):
        fields = {f.name: f for f in T.load_layout(row["table"])}
        f = fields[row["field"]]
        if not f.elements:
            raise SystemExit(f"enums.csv: {row['table']}.{row['field']} has no element names")
        lines.append(f"/* {cmt(row['description'])} (element names of {row['table']}.{row['field']}) */")
        lines.append("enum {")
        for i, e in enumerate(f.elements):
            lines.append(f"    {row['prefix']}_{e.upper()} = {i},")
        lines.append(f"    {row['count_name']} = {len(f.elements)}")
        lines.append("};")
        lines.append("")
    lines.append("#endif /* FE_STRUCTS_H */")
    return "\n".join(lines) + "\n"


def gen_globals() -> str:
    lines = [
        "/* GENERATED by tools/readable/gen_structs.py from config/tables/tables.csv and",
        "   config/readable/globals.csv -- do not edit. Guest addresses of globals; read",
        "   the pointer they hold with guest_ptr(ctx, G_...). */",
        "",
        "#ifndef FE_GLOBALS_H",
        "#define FE_GLOBALS_H",
        "",
        "/* table base pointers and record counts (config/tables/tables.csv code_global / count_global) */",
    ]
    reg = T.registry()
    with open(os.path.join(T.CONFIG, "tables.csv"), newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        if (r.get("code_global") or "").strip():
            a = int(r["code_global"].strip()[2:], 16)
            lines.append(f"#define G_{r['table']}Data 0x{a:08X}u  /* {r['table']}Data*: base of the {r['table']} table */")
        if (r.get("count_global") or "").strip():
            a = int(r["count_global"].strip()[2:], 16)
            lines.append(f"#define G_{r['table']}DataNum 0x{a:08X}u  /* u32: number of {r['table']} records */")
    assert reg  # registry parsed (same file)
    lines.append("")
    lines.append("/* found by hand (config/readable/globals.csv) */")
    for r in read_csv(os.path.join(CONFIG, "globals.csv")):
        a = int(r["address"], 0)
        lines.append(f"#define {r['name']} 0x{a:08X}u  /* {cmt(r['type'])} [{r['confidence']}] */")
    lines.append("")
    lines.append("#endif /* FE_GLOBALS_H */")
    return "\n".join(lines) + "\n"


def gen_game() -> str:
    """fe_game.h: per-game constants the C side needs (config/game.json and
    config/readable/addresses.json). The capture library's default guard is the guard's
    entry as 3dsrecomp names it: address | 1 for a Thumb routine."""
    from gamecfg import GAME
    import gameaddr
    g = gameaddr.entry("guard")
    guard = int(g["address"], 16) if g.get("address") else 0
    entry = guard | 1 if guard and g.get("isa") == "thumb" else guard
    return "\n".join([
        "/* GENERATED by tools/readable/gen_structs.py from config/game.json and",
        "   config/readable/addresses.json -- do not edit. Per-game constants of the C side. */",
        "",
        "#ifndef FE_GAME_H",
        "#define FE_GAME_H",
        "",
        f"#define FE_GAME_KEY \"{GAME.key}\"",
        f"#define FE_GAME_TITLE_ID \"{GAME.title_id}\"",
        f"/* one-time guard routine ({cmt(g.get('symbol') or 'unnamed')}, {g.get('isa', '?')}); 0 = not known */",
        f"#define FE_GAME_GUARD 0x{guard:08X}u",
        "/* the guard as an override / probe literal: odd for a Thumb routine (3dsrecomp's rule) */",
        f"#define FE_GAME_GUARD_ENTRY 0x{entry:08X}u",
        "",
        "#endif /* FE_GAME_H */",
        "",
    ])


def outputs() -> dict[str, str]:
    return {STRUCTS_H: gen_structs(), GLOBALS_H: gen_globals(), GAME_H: gen_game()}


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "gen"
    if cmd not in ("gen", "check"):
        print(__doc__)
        return 2
    stale = []
    for path, text in outputs().items():
        old = None
        if os.path.exists(path):
            with open(path, encoding="utf-8", newline="") as fh:
                old = fh.read()
        if old == text:
            continue
        if cmd == "check":
            stale.append(os.path.relpath(path, ROOT))
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            print(f"wrote {os.path.relpath(path, ROOT)}")
    if stale:
        for s in stale:
            print(f"out of date: {s} (run python tools/readable/gen_structs.py gen)")
        return 1
    if cmd == "check":
        print("gen_structs: up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
