#!/usr/bin/env python3
"""Castle data (and every other "sheet" file) as editable spreadsheets.

Standard library only. Reads the user's own extracted/romfs; writes only under
build/castle/. Layouts: config/tables/castle/ (sheets.csv + one CSV per sheet). The file
format and the rules are in tools/castle/sheetlib.py and docs/CASTLE.md.

    python tools/castle/castle.py dump [KEY ...]
        build/castle/<KEY>.csv for every registered sheet (or the ones named), plus
        build/castle/<KEY>__<SUB>.csv for the items of a list field (UTF-8 with BOM)
    python tools/castle/castle.py build [--check] [--no-write] [KEY ...]
        rebuild every file that holds a registered sheet from the CSVs (a missing CSV
        means "unchanged") into build/castle/rebuilt/<RomFS path>; --check compares
        with the originals and fails on any difference (use it on an unedited dump)
    python tools/castle/castle.py check
        every layout against its file: the file's own field declaration, the row size
        (and the code's, through sheets.csv), list items, row labels
    python tools/castle/castle.py survey [--all]
        every IS .bin in the RomFS with the MOD_/DAT_/SHEET_LIST shape: sheets, rows,
        and its status (editable here / generic round trip / fails); --all also
        round-trips each one with its declared types
    python tools/castle/castle.py roundtrip
        dump -> build in memory for every registered file: byte-identical
    python tools/castle/castle.py edit-test
        a few edits in memory, each proven to change exactly the edited bytes
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sheetlib as L  # noqa: E402

T = L.T


# ------------------------------------------------------------------ helpers
def defs_by_file(reg: dict[str, L.SheetDef]) -> dict[str, list[L.SheetDef]]:
    out: dict[str, list[L.SheetDef]] = {}
    for d in reg.values():
        out.setdefault(d.file, []).append(d)
    for v in out.values():
        v.sort(key=lambda d: d.sheet)
    return out


def layout_of(d: L.SheetDef) -> tuple[list[L.Field], dict[str, list[L.Field]]]:
    fields = L.load_layout(d.key)
    subs = {f.sub: L.load_layout(f.sub) for f in fields if f.kind == "list"}
    return fields, subs


def codec(c: T.Container, d: L.SheetDef) -> L.Codec:
    sheets = L.parse(c)
    if d.sheet >= len(sheets):
        raise L.SheetError(f"{d.key}: {d.file} has {len(sheets)} sheets, no sheet {d.sheet}")
    s = sheets[d.sheet]
    if s.size != d.size:
        raise L.SheetError(f"{d.key}: row size in the file is {s.size:#x}, sheets.csv (the code) says {d.size:#x}")
    fields, subs = layout_of(d)
    return L.Codec(c, s, fields, subs)


def csv_path(key: str) -> str:
    return os.path.join(L.OUTDIR, f"{key}.csv")


def sub_path(key: str, sub: str) -> str:
    return os.path.join(L.OUTDIR, f"{key}__{sub}.csv")


# ------------------------------------------------------------------ dump
def dump(reg: dict[str, L.SheetDef], keys: list[str]) -> int:
    for k in keys:
        d = reg[k]
        cod = codec(L.container(d.file), d)
        L.write_csv(csv_path(k), L.columns(cod.fields), cod.rows())
        n = f"{cod.s.count} rows"
        for f in cod.fields:
            if f.kind == "list":
                items = cod.items(f)
                L.write_csv(sub_path(k, f.sub), L.sub_columns(cod.subs[f.sub]), items)
                n += f", {len(items)} {f.sub} items"
        print(f"{k}: {n} -> {os.path.relpath(csv_path(k), L.ROOT)}")
    return 0


# ------------------------------------------------------------------ build
def load_tables(reg, keys) -> tuple[dict, dict]:
    tables, items = {}, {}
    for k in keys:
        if os.path.isfile(csv_path(k)):
            tables[k] = L.read_csv(csv_path(k))
        for f in L.load_layout(k):
            if f.kind == "list" and os.path.isfile(sub_path(k, f.sub)):
                items[(k, f.sub)] = L.read_csv(sub_path(k, f.sub))
    return tables, items


def build_file(reg: dict[str, L.SheetDef], rel: str, tables: dict, items: dict,
               c: T.Container | None = None) -> bytes:
    """The stored bytes of `rel` rebuilt from tables[key] = (header, rows) and
    items[(key, sub)] = (header, rows); a sheet or list without an entry is kept."""
    c = c or L.container(rel)
    defs = defs_by_file(reg)[rel]
    # 1. rows added at the end of a sheet (refused unless sheets.csv allows it)
    for d in defs:
        if d.key not in tables:
            continue
        hdr, rows = tables[d.key]
        cod = codec(c, d)
        if hdr != L.columns(cod.fields):
            raise L.SheetError(f"{d.key}: the columns are not the dumped ones ({', '.join(L.columns(cod.fields))})")
        s = cod.s
        if len(rows) < s.count:
            raise L.SheetError(f"{d.key}: {len(rows)} rows, the file has {s.count}; rows cannot be removed "
                               "(the game finds rows by number)")
        extra = rows[s.count:]
        if not extra:
            continue
        if d.append != "allow":
            raise L.SheetError(f"{d.key}: adding rows is refused: {d.evidence}")
        if any(f.kind in ("list", "ptr") for f in cod.fields):
            raise L.SheetError(f"{d.key}: rows with pointer fields cannot be added")
        labels = []
        have = {n for _o, n, _no in c.b.labels}
        for k, r in enumerate(extra):
            want = s.count + k
            if not r or r[0].strip() != str(want):
                raise L.SheetError(f"{d.key}: new rows must be numbered {s.count}, {s.count + 1}, ... in order "
                                   f"(found {r[0] if r else ''!r} where {want} belongs)")
            lab = T.untext(r[1].strip()) if len(r) > 1 else b""
            if d.label == "required" and not lab:
                raise L.SheetError(f"{d.key} row {want}: a new row needs a label (its key; the game finds "
                                   "these rows by name)")
            if lab:
                try:
                    lab.decode("cp932")
                except UnicodeError:
                    raise L.SheetError(f"{d.key} row {want}: label is not valid Shift-JIS") from None
                if lab in have or lab.startswith((b"MOD_", b"DAT_", b"SHEET_")):
                    raise L.SheetError(f"{d.key} row {want}: label {r[1]!r} is already used or reserved")
                have.add(lab)
            labels.append(lab)
        c = L.insert_rows(c, s, len(extra), labels)
    # 2. every cell
    data = bytearray(c.data)
    ptrs: dict = {}
    for d in defs:
        cod = codec(c, d)
        if d.key in tables:
            hdr, rows = tables[d.key]
            cod.encode(rows, data, ptrs, d.key)
        for f in cod.fields:
            if f.kind == "list" and (d.key, f.sub) in items:
                hdr, rows = items[(d.key, f.sub)]
                if hdr != L.sub_columns(cod.subs[f.sub]):
                    raise L.SheetError(f"{d.key}__{f.sub}: the columns are not the dumped ones")
                cod.encode_items(f, rows, data, ptrs, f"{d.key}__{f.sub}")
    return T.rebuild(c, data, ptrs)


def build(reg: dict[str, L.SheetDef], keys: list[str], check: bool, write: bool) -> int:
    tables, items = load_tables(reg, keys)
    bad = 0
    byfile = defs_by_file(reg)
    for rel in sorted({reg[k].file for k in keys}):
        mine = {k: v for k, v in tables.items() if reg[k].file == rel}
        mitems = {k: v for k, v in items.items() if reg[k[0]].file == rel}
        try:
            out = build_file({d.key: d for d in byfile[rel]}, rel, mine, mitems)
        except (L.SheetError, T.LayoutError) as e:
            print(f"REFUSED {rel}: {e}")
            bad += 1
            continue
        same = out == L.container(rel).raw
        if write:
            p = os.path.join(L.REBUILT, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as fh:
                fh.write(out)
        print(f"{rel}: {'identical to the original' if same else 'CHANGED'}"
              + (f" -> {os.path.relpath(os.path.join(L.REBUILT, rel), L.ROOT)}" if write else ""))
        if check and not same:
            bad += 1
    return 1 if bad else 0


# ------------------------------------------------------------------ check
def check_one(d: L.SheetDef) -> list[str]:
    errs = []
    try:
        c = L.container(d.file)
        cod = codec(c, d)
    except (L.SheetError, T.LayoutError, OSError) as e:
        return [str(e)]
    s = cod.s
    labs = L.row_labels(c, s)
    if d.label == "required" and not all(labs):
        errs.append("sheets.csv says rows are labelled, but some rows have no label")
    regions = [(s.rows, s.end, "rows")]
    for f in cod.fields:
        if f.kind == "str":
            for i in range(s.count):
                o = s.rows + i * s.size + f.offset
                if o not in c.relset and c.u32(o):
                    errs.append(f"row {i} {f.name}: a non-zero str that is not a relocated pointer")
                    break
        if f.kind != "list":
            continue
        sub = cod.subs[f.sub]
        size = sum(x.size for x in sub)
        errs += [f"{f.sub}: {e}" for e in L.tile_errors(sub, size)]
        for i in range(s.count):
            lst = L.list_at(c, s.rows + i * s.size + f.offset)
            if lst is None:
                continue
            n, at = lst
            h = c.u32(s.rows + i * s.size + f.offset)
            regions += [(h, h + 8, f"row {i} list header"), (at, at + n * size, f"row {i} items")]
            for k in range(n):
                b = at + k * size
                for x in sub:
                    o = b + x.offset
                    if x.kind in ("str", "ptr", "list"):
                        if o not in c.relset and c.u32(o):
                            errs.append(f"{f.sub} row {i} item {k} {x.name}: not a relocated pointer")
                    elif any(p in c.relset for p in range(o - o % 4, o + x.size, 4) if p + 4 > o):
                        errs.append(f"{f.sub} row {i} item {k} {x.name}: overlaps a relocated pointer")
    regions.sort()
    for (a0, a1, an), (b0, b1, bn) in zip(regions, regions[1:]):
        if b0 < a1 and b1 > b0:
            errs.append(f"{an} ({a0:#x}..{a1:#x}) overlaps {bn} ({b0:#x}..{b1:#x})")
    return errs


def check(reg: dict[str, L.SheetDef]) -> int:
    bad = 0
    for k, d in reg.items():
        errs = check_one(d)
        print(f"{k}: {'ok' if not errs else 'FAIL'}")
        for e in errs[:10]:
            print(f"    {e}")
        bad += bool(errs)
    return 1 if bad else 0


# ------------------------------------------------------------------ survey / round trips
def roundtrip(reg: dict[str, L.SheetDef]) -> int:
    """dump -> CSV text -> build for every registered file, in memory."""
    import csv
    import io
    bad = 0
    for rel, defs in sorted(defs_by_file(reg).items()):
        c = L.container(rel)
        tables, items = {}, {}
        for d in defs:
            cod = codec(c, d)

            def via_csv(h, rows):
                buf = io.StringIO()
                w = csv.writer(buf)
                w.writerow(h)
                w.writerows(rows)
                got = list(csv.reader(io.StringIO(buf.getvalue())))
                return got[0], got[1:]
            tables[d.key] = via_csv(L.columns(cod.fields), cod.rows())
            for f in cod.fields:
                if f.kind == "list":
                    items[(d.key, f.sub)] = via_csv(L.sub_columns(cod.subs[f.sub]), cod.items(f))
        out = build_file({d.key: d for d in defs}, rel, tables, items, c)
        ok = out == c.raw
        bad += not ok
        print(f"{rel}: {'byte-identical' if ok else 'DIFFERENT'} ({', '.join(d.key for d in defs)})")
    return 1 if bad else 0


def survey(reg: dict[str, L.SheetDef], full: bool) -> int:
    mine = defs_by_file(reg)
    files = L.sheet_files()
    groups: dict[str, list] = {}
    bad = 0
    for rel in files:
        c = L.container(rel)
        try:
            sheets = L.parse(c)
            note = f"{len(sheets)} sheet(s), {sum(s.count for s in sheets)} rows"
        except L.SheetError as e:
            sheets, note = [], f"unreadable: {e}"
        if rel in mine:
            status = "editable: " + ", ".join(d.key for d in mine[rel])
        else:
            status = "same shape, not registered"
        if full and sheets:
            try:
                ok, why = L.generic_roundtrip(rel)
            except (L.SheetError, T.LayoutError) as e:
                ok, why = False, str(e)
            status += "; generic round trip " + ("OK" if ok else f"FAILS ({why})")
            bad += not ok
        elif not sheets:
            status = note
            note = ""
            bad += full
        folder = rel.rsplit("/", 1)[0] if rel.startswith(("GameData/Field/", "map/config/")) else rel
        groups.setdefault(folder, []).append((rel, note, status))
    for folder, lst in groups.items():
        if len(lst) > 3:
            st = {s for _r, _n, s in lst}
            print(f"{folder}/* ({len(lst)} files): {'; '.join(sorted(st))}")
        else:
            for rel, note, status in lst:
                print(f"{rel}: {note}; {status}" if note else f"{rel}: {status}")
    print(f"{len(files)} sheet files in the RomFS" + (f", {len(files) - bad} round-trip byte-identical with their declared types" if full else ""))
    return 0


# ------------------------------------------------------------------ edit test
def edit_test(reg: dict[str, L.SheetDef]) -> int:
    """Edit one cell, rebuild in memory, decompress: exactly the edited bytes change."""
    cases = [("DiningData_Dish", 0, "str"), ("DiningData_CookTitle", 1, "def"),
             ("AcceShop", 1, "damage_up"), ("CastlePerson", 0, "hot_spring"), ("MyRoom_Release", 0, "hearts")]
    bad = 0
    for key, row, col in cases:
        d = reg[key]
        c = L.container(d.file)
        cod = codec(c, d)
        rows = cod.rows()
        hdr = L.columns(cod.fields)
        j = hdr.index(col)
        f = next(x for x in cod.fields if x.name == col)
        old = int(rows[row][j])
        new = old + 1 if old < 100 else old - 1
        rows[row][j] = str(new)
        out = build_file(reg, d.file, {key: (hdr, rows)}, {})
        dec = T.Container(d.file, out).dec
        diff = [i for i in range(len(dec)) if dec[i] != c.dec[i]] if len(dec) == len(c.dec) else None
        at = 0x20 + cod.s.rows + row * cod.s.size + f.offset
        want = [i for i in range(at, at + f.size) if (old ^ new) >> (8 * (i - at)) & 0xFF]
        ok = diff == want
        bad += not ok
        print(f"{key} row {row} {col}: {old} -> {new}: "
              + ("exactly the edited byte(s) changed" if ok else f"WRONG (changed {diff[:8] if diff else diff})"))
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("dump", "build", "check", "survey", "roundtrip", "edit-test"))
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--check", action="store_true", help="build: fail unless identical to the originals")
    ap.add_argument("--no-write", action="store_true", help="build: write nothing")
    ap.add_argument("--all", action="store_true", help="survey: also round-trip every sheet file")
    a = ap.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    if not os.path.isdir(L.ROMFS):
        print("extracted/romfs is missing: run python tools/assets/romfs.py first")
        return 1
    reg = L.registry()
    keys = a.keys or list(reg)
    for k in keys:
        if k not in reg:
            print(f"unknown sheet {k}; known: {', '.join(reg)}")
            return 1
    try:
        if a.cmd == "dump":
            return dump(reg, keys)
        if a.cmd == "build":
            return build(reg, keys, a.check, not a.no_write)
        if a.cmd == "check":
            return check({k: reg[k] for k in keys})
        if a.cmd == "survey":
            return survey(reg, a.all)
        if a.cmd == "roundtrip":
            return roundtrip(reg)
        return edit_test(reg)
    except (L.SheetError, T.LayoutError) as e:
        print(f"error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
