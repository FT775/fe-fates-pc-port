#!/usr/bin/env python3
"""Export the function registry (config/functions.csv) for other tools. Everything is
written under build/ (gitignored: the names are labels, but keep exports with the build).

    python tools/export_symbols.py               all three files
    python tools/export_symbols.py --qualified   symbols.txt uses C++-style names
                                                 (nn::fs::File::Read) instead of the
                                                 assembler-safe ones (nn__fs__File__Read)

Writes:
    build/symbols.txt        "name 0xADDR f" per line: the format Ghidra's bundled
                             ImportSymbolsScript.py reads (f = create/rename a function).
                             Names never contain whitespace.
    build/symbols_luma.txt   "ADDR  signature" sorted by address (crash-address lookup:
                             find the last line <= the PC)
    build/symbols_full.tsv   addr, end, mode, library, name, qualified, signature: input
                             for tools/fates/ghidra_import.py (namespaces, Thumb mode,
                             signatures as comments)

Thumb functions (mode THUMB) need the TMode context set before Ghidra disassembles them;
ImportSymbolsScript cannot do that, tools/fates/ghidra_import.py does.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "config" / "functions.csv"
BUILD = ROOT / "build"
sys.path.insert(0, str(ROOT / "tools" / "fates"))
import symbols as S  # noqa: E402


def qualified(sig: str, fallback: str) -> str:
    """'virtual A::B::f(int) const' -> 'A::B::f'; whitespace inside (operator new,
    conversion operators) becomes '_'."""
    if not sig:
        return fallback
    _, qual, _ = S.split_signature(sig)
    q = re.sub(r"\s+", "_", qual.strip())
    return q or fallback


def main() -> int:
    if not REGISTRY.is_file():
        sys.exit("config/functions.csv missing: python tools/fates/symbols.py")
    use_q = "--qualified" in sys.argv
    with REGISTRY.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    ghidra, luma, tsv = [], [], ["addr\tend\tmode\tlibrary\tname\tqualified\tsignature"]
    for r in rows:
        a = int(r["addr"], 16)
        name = r["name"]
        q = qualified(r["signature"], name)
        label = q if use_q else name
        assert not re.search(r"\s", label), label
        ghidra.append(f"{label} 0x{a:08X} f")
        luma.append(f"{a:08X}  {r['signature'] or name}")
        tsv.append("\t".join([f"0x{a:08X}", r["end"], r["mode"], r["library"], name, q,
                              r["signature"].replace("\t", " ")]))
    BUILD.mkdir(exist_ok=True)
    (BUILD / "symbols.txt").write_text("\n".join(ghidra) + "\n", encoding="utf-8")
    (BUILD / "symbols_luma.txt").write_text("\n".join(luma) + "\n", encoding="utf-8")
    (BUILD / "symbols_full.tsv").write_text("\n".join(tsv) + "\n", encoding="utf-8")
    print(f"wrote {len(ghidra)} symbols to build/symbols.txt, build/symbols_luma.txt, build/symbols_full.tsv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
