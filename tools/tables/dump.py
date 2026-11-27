#!/usr/bin/env python3
"""Render the game's data tables as readable spreadsheets (CSV), using the layouts in
config/tables/.

Standard library only. Reads the user's own extracted/romfs/ and writes
build/tables/<table>.csv (gitignored: these files hold game values and text).
Open them in any spreadsheet program; they are UTF-8 with a byte-order mark so Excel
shows the Japanese IDs correctly.

Columns: [file] (tables spread over several files, e.g. PersonChapter, DisposUnit),
index (record number in its file), label (the record's exported label, i.e. its ID; empty
for tables without labels such as DisposUnit), then one column per field; arrays get one
column per element (name.element). Cell conventions:
    integers        decimal (signed where the layout type is signed)
    hex[n]          the n bytes as one hex string (e.g. the 32x32 terrain grid)
    str             the string; empty cell = no pointer; "" = pointer to an empty string
    ptr:TABLE       the label of the record pointed to, or #N (record N of TABLE in the
                    same file) when it has no label; empty = no pointer
    ptr             @0xOFFSET (data offset inside the container)
    flagsN:ID       set bits as ID names joined by '|' (unknown bits as bitN)
    enumN:ID        the ID name (or its number)
    refN:TABLE      the target record's label (or its number); none = all-ones
Pad fields are not shown (they are zero; check.py verifies that).

`tools/tables/build.py` turns these CSVs back into the container files.

Usage:
    python tools/tables/dump.py [TABLE ...]      default: every table with a layout
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tablelib as T  # noqa: E402


def dump_table(reg, name: str) -> tuple[str, int]:
    codec = T.Codec(reg, name)
    t = reg[name]
    rows = []
    for rel in t.files():
        c = T.container(rel)
        start, count = T.locate(t, c)
        labels = T.record_labels(t, c, start, count)
        for i in range(count):
            rows.append(codec.decode(c, i, start + i * t.size, labels[i]))
    os.makedirs(T.OUTDIR, exist_ok=True)
    path = os.path.join(T.OUTDIR, f"{name}.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(codec.columns())
        w.writerows(rows)
    return path, len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tables", nargs="*")
    a = ap.parse_args()
    reg = T.registry()
    names = a.tables or [n for n in reg if os.path.exists(T.layout_path(n))]
    for name in names:
        path, n = dump_table(reg, name)
        print(f"{name:16} {n:5} rows -> {os.path.relpath(path, T.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
