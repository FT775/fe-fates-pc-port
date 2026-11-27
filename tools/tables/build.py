#!/usr/bin/env python3
"""Rebuild the table containers from the spreadsheets written by dump.py.

Standard library only. For every RomFS file that holds at least one table with a layout,
start from the original container (extracted/romfs/), write every record of every table
in that file from build/tables/<table>.csv through its layout (integers, strings
re-pooled, pointers re-resolved by label or #record), rebuild the
container with tools/assets/isbin.py's string-pool rule and the original relocation
order, and LZ-recompress it like the original (tools/assets/lz.py). Bytes outside the
tables are carried over unchanged.

    --check   compare each rebuilt file with the original RomFS file (the round-trip
              proof: an unedited dump must give back the identical file); exit 1 on any
              difference
    --out DIR write rebuilt files under DIR (default build/tables/rebuilt/), keeping
              RomFS paths, for use as LayeredFS-style overrides

Usage:
    python tools/tables/dump.py && python tools/tables/build.py --check
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tablelib as T  # noqa: E402


_FRESH: set[str] = set()


def load_rows(name: str) -> tuple[list[str], list[list[str]]]:
    """Rows of build/tables/<name>.csv; when that dump does not exist (yet), the vanilla
    rows decoded from the RomFS (said once per table)."""
    path = os.path.join(T.OUTDIR, f"{name}.csv")
    if not os.path.exists(path):
        if name not in _FRESH:
            _FRESH.add(name)
            print(f"note: no {os.path.relpath(path, T.ROOT)}; using the vanilla rows for {name}")
        return dump_rows(T.registry(), name)
    with open(path, newline="", encoding="utf-8-sig") as fh:
        r = list(csv.reader(fh))
    return r[0], r[1:]


# rel -> [(data offset, bytes)] of the insertions the last build_file of that file made
# (empty when it appended nothing); callers that compare decoded rows with what they
# asked for pass it to shift_cells first
LAST_MOVES: dict[str, list[tuple[int, int]]] = {}


def shift_cells(reg, name: str, rows: list[list[str]], moves: list[tuple[int, int]]) -> list[list[str]]:
    """rows with every raw data offset cell (@0x... in a ptr / ptr:T column) moved by the
    insertions [(offset, bytes)], in order: what the rows read back as after an append."""
    if not moves:
        return rows
    codec = T.Codec(reg, name)
    skip = 3 if reg[name].multi else 2
    ptrcols = {f.name for f in codec.fields if f.kind in ("ptr", "lptr")}
    pos = [skip + k for k, col in enumerate(codec.columns()[skip:]) if col in ptrcols]
    if not pos:
        return rows
    out = []
    for row in rows:
        row = list(row)
        for p in pos:
            if row[p].startswith("@0x"):
                v = int(row[p][1:], 16)
                for at, n in moves:
                    v = v + n if v >= at else v
                row[p] = f"@0x{v:X}"
        out.append(row)
    return out


def build_file(reg, rel: str, tables: list[str], override: dict | None = None,
               policies: dict | None = None) -> bytes:
    """Stored bytes of RomFS file rel rebuilt from the rows of every table in it. A table
    with more rows than the file has records gets the extra rows appended when
    config/tables/appends.csv allows it (tablelib.append_records: new records after the
    last one, labels exported, count raised, everything after them moved); fewer rows
    are always refused (a game record is never deleted)."""
    c = T.container(rel)
    mine_of: dict[str, list[list[str]]] = {}
    codecs: dict[str, T.Codec] = {}
    for name in tables:
        t = reg[name]
        codecs[name] = T.Codec(reg, name)
        head, rows = override[name] if override and name in override else load_rows(name)
        if head != codecs[name].columns():
            raise T.LayoutError(f"{name}.csv: columns do not match the layout (re-run dump.py)")
        mine_of[name] = [r for r in rows if (r[0] == rel if t.multi else True)]
    moves: list[tuple[int, int]] = []           # (offset, bytes) of each insertion, in order
    for name in tables:
        t = reg[name]
        mine = mine_of[name]
        start, count = T.locate(t, c)
        if len(mine) < count:
            raise T.LayoutError(f"{name}: {len(mine)} rows for {rel}, the file has {count} records "
                                "(removing records is refused: a game record is never deleted)")
        if len(mine) > count:
            why = T.append_refusal(t, policies)
            if why:
                raise T.LayoutError(f"{name}: {len(mine)} rows for {rel}, the file has {count} records "
                                    f"(adding records: {why})")
            skip = 3 if t.multi else 2
            c = T.append_records(reg, name, c, [r[skip - 2:] for r in mine[count:]], policies)
            moves.append((start + count * t.size, (len(mine) - count) * t.size))
    LAST_MOVES[rel] = moves
    if moves:
        # raw data offsets in cells (@0x...) were taken from the original layout: move
        # the ones at or after each insertion like the pointers they stand for
        for name in tables:
            mine_of[name] = shift_cells(reg, name, mine_of[name], moves)
    data = bytearray(c.data)
    ptrs: dict[int, tuple[str, object]] = {}
    # while encoding, the grown container stands in for the original so that references
    # by label (#N, ref, ptr) resolve against the new records too
    saved = T._CACHE.get(rel)
    T._CACHE[rel] = c
    try:
        for name in tables:
            t = reg[name]
            start, _count = T.locate(t, c)
            skip = 3 if t.multi else 2
            for row in mine_of[name]:
                i = int(row[skip - 2])
                codecs[name].encode(c, data, i, start + i * t.size, row[skip:], ptrs)
        return T.rebuild(c, data, ptrs)
    finally:
        if saved is None:
            T._CACHE.pop(rel, None)
        else:
            T._CACHE[rel] = saved


def dump_rows(reg, name: str) -> tuple[list[str], list[list[str]]]:
    """The rows dump.py would write for a table, decoded fresh from the RomFS (no CSV)."""
    codec = T.Codec(reg, name)
    t = reg[name]
    rows = []
    for rel in t.files():
        c = T.container(rel)
        start, count = T.locate(t, c)
        labels = T.record_labels(t, c, start, count)
        rows += [codec.decode(c, i, start + i * t.size, labels[i]) for i in range(count)]
    return codec.columns(), rows


def tables_in(reg, rel: str) -> list[str]:
    return [n for n in reg if os.path.exists(T.layout_path(n)) and rel in reg[n].files()]


def edit_rebuild(reg, name: str, rel: str, changes: dict[str, str], k: int = 1):
    """Edit cells of record k (in file rel) of table name in memory and rebuild that file.
    Returns (original container, rebuilt container, record start offset, head, edited rows)."""
    t = reg[name]
    head, rows = dump_rows(reg, name)
    col = {h: n for n, h in enumerate(head)}
    idx = [j for j, r in enumerate(rows) if (r[0] == rel if t.multi else True)]
    edited = [list(r) for r in rows]
    for h, v in changes.items():
        edited[idx[k]][col[h]] = v
    out = build_file(reg, rel, tables_in(reg, rel), override={name: (head, edited)})
    c0 = T.container(rel)
    nc = T.Container(rel, out)
    return c0, nc, head, [edited[j] for j in idx]


def edit_test(reg) -> bool:
    """Edit cells in memory, rebuild, parse the result and check that exactly those cells
    changed: an integer (Person base stat, Job move), a string (the pool is rebuilt and
    every other string pointer must still resolve), a class reference (re-resolved by
    label), a Dispos position in a per-chapter file, an Arena entry (class and weapon
    references) and a Tutorial message ID."""
    ok = True
    cases = [
        ("Person", None, lambda r, col: {"base.str": str(int(r[col["base.str"]]) + 1),
                                          "mpid_help": r[col["mpid_help"]] + "_EDIT",
                                          "job": "JID_パラディン男"}),
        ("Job", None, lambda r, col: {"mov": str(int(r[col["mov"]]) + 1), "promotion.1": r[col["label"]]}),
        ("DisposUnit", "GameData/Dispos/A001.bin.lz", lambda r, col: {"pos.x": str(int(r[col["pos.x"]]) + 1),
                                                                  "item_1": "IID_鉄の剣"}),
        ("ArenaLow", None, lambda r, col: {"job": "JID_パラディン男", "weapon": "IID_鉄の剣",
                                           "weight": str(int(r[col["weight"]]) + 1)}),
        ("Tutorial", None, lambda r, col: {"mtutid_help": r[col["mtutid_help"]] + "_EDIT"}),
    ]
    for name, rel, mk in cases:
        t = reg[name]
        rel = rel or t.files()[0]
        head, rows = dump_rows(reg, name)
        col = {h: n for n, h in enumerate(head)}
        idx = [j for j, r in enumerate(rows) if (r[0] == rel if t.multi else True)]
        changes = mk(rows[idx[1]], col)
        c0, nc, head, want = edit_rebuild(reg, name, rel, changes)
        codec = T.Codec(reg, name)
        start, count = T.locate(t, nc)
        labels = T.record_labels(t, nc, start, count)
        got = [codec.decode(nc, i, start + i * t.size, labels[i]) for i in range(count)]
        if got != want:
            bad = [(i, h) for i in range(count) for h in head if got[i][col[h]] != want[i][col[h]]]
            print(f"edit test {name} ({rel}): FAILED, cells differ: {bad[:10]}")
            ok = False
            continue
        for other in [n for n in tables_in(reg, rel) if n != name]:
            oc, ot = T.Codec(reg, other), reg[other]
            s0, n0 = T.locate(ot, c0)
            s1, n1 = T.locate(ot, nc)
            l0, l1 = T.record_labels(ot, c0, s0, n0), T.record_labels(ot, nc, s1, n1)
            if [oc.decode(c0, i, s0 + i * ot.size, l0[i]) for i in range(n0)] !=                     [oc.decode(nc, i, s1 + i * ot.size, l1[i]) for i in range(n1)]:
                print(f"edit test {name}: table {other} changed")
                ok = False
        print(f"edit test {name} ({rel}): {len(changes)} cells edited ({', '.join(changes)}); "
              f"rebuilt file parses and decodes to exactly the edit")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out", default=os.path.join(T.OUTDIR, "rebuilt"))
    ap.add_argument("--no-write", action="store_true", help="with --check: compare only")
    ap.add_argument("--edit-test", action="store_true",
                    help="also edit a few cells in memory and verify the rebuilt file decodes to exactly that edit")
    a = ap.parse_args()
    reg = T.registry()
    if a.edit_test and not edit_test(reg):
        return 1
    try:
        return run(a, reg)
    except (T.LayoutError, ValueError, KeyError) as e:
        print(f"error: {e}")
        return 1


def run(a, reg) -> int:
    by_file: dict[str, list[str]] = defaultdict(list)
    for name in reg:
        if os.path.exists(T.layout_path(name)):
            for rel in reg[name].files():
                by_file[rel].append(name)
    same = 0
    for rel in sorted(by_file):
        out = build_file(reg, rel, by_file[rel])
        c = T.container(rel)
        ok = out == c.raw
        same += ok
        if not a.no_write:
            dst = os.path.join(a.out, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as fh:
                fh.write(out)
        if a.check and not ok:
            print(f"DIFFERENT: {rel} ({', '.join(by_file[rel])})")
    n = len(by_file)
    print(f"rebuilt {n} container file(s) from {sum(len(v) for v in by_file.values())} table dumps: "
          f"{same}/{n} byte-identical to the original RomFS files")
    return 0 if (same == n or not a.check) else 1


if __name__ == "__main__":
    sys.exit(main())
