"""Castle mods for tools/mods/mods.py: mods/<Name>/castle/<File>/<Sheet>.csv.
Standard library only.

castle/<File>/   <File> is the name of a castle data file without its folder and
                 extension (DiningData for GameData/Castle/DiningData.bin.lz, AcceShop,
                 JobIntro, CastlePerson ...; `python tools/mods/mods.py castle NAME FILE`
                 writes the folder). Inside it go the spreadsheets that
                 `python tools/castle/castle.py dump` writes for that file: <KEY>.csv for a
                 sheet (DiningData_Dish.csv) and <KEY>__<LIST>.csv for the items of a list
                 column (JobIntro_Group__JobIntro_Unit.csv). A missing CSV means "unchanged".

Only cells that differ from the game count (numbers compare by value, so 0x10 = 16).
Rows past the sheet's end are new rows, accepted only where config/tables/castle/sheets.csv
says "allow" (today the two dining sheets; docs/DECISIONS.md F-016) and each needs its own
label. Two mods that set the same cell to different values conflict unless the later one
has "override": true; new rows from several mods are kept in mod order and renumbered.

The build runs tools/castle/castle.build_file on the merged cells, then reads the result
back: the same LZ format, and every sheet and list of the file decodes to exactly the merged
spreadsheet (unedited sheets included). Only then is the file staged; install, uninstall
and recover treat it like every other staged file (mods.py does that part).
"""
from __future__ import annotations

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CASTLE_DIR = "castle"

_C = None
_C_ERR = ""


def castle():
    """tools/castle/castle.py (with .L = sheetlib), or None (status() says why)."""
    global _C, _C_ERR
    if _C is None and not _C_ERR:
        try:
            sys.path.insert(0, os.path.join(ROOT, "tools", "castle"))
            spec = importlib.util.spec_from_file_location("fates_mods_castle",
                                                          os.path.join(ROOT, "tools", "castle", "castle.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.reg = mod.L.registry()
            _C = mod
        except Exception as e:          # a tool being rewritten must not break other mods
            _C_ERR = f"{type(e).__name__}: {e}"
    return _C


def status() -> str | None:
    return None if castle() is not None else f"tools/castle could not be loaded ({_C_ERR})"


def stem(rel: str) -> str:
    """The folder name of a castle file: its name without folder and extension."""
    n = rel.rsplit("/", 1)[-1]
    for ext in (".lz", ".bin"):
        if n.lower().endswith(ext):
            n = n[: -len(ext)]
    return n


def file_folders() -> dict[str, str]:
    """{folder name: RomFS path} of every file that holds a registered sheet."""
    C = castle()
    out: dict[str, str] = {}
    for rel in C.L.files(C.reg):
        s = stem(rel)
        if s in out:
            raise ValueError(f"two castle files share the folder name {s}: {out[s]}, {rel}")
        out[s] = rel
    return out


def packages(mod_dir: str) -> list[tuple[str, str]]:
    """[(folder name, folder)] under castle/ that hold at least one CSV."""
    top = os.path.join(mod_dir, CASTLE_DIR)
    if not os.path.isdir(top):
        return []
    return [(n, os.path.join(top, n)) for n in sorted(os.listdir(top))
            if os.path.isdir(os.path.join(top, n))
            and any(f.lower().endswith(".csv") for f in os.listdir(os.path.join(top, n)))]


def files_to_hash(mod_dir: str) -> list[tuple[str, str]]:
    out = []
    for name, d in packages(mod_dir):
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(".csv"):
                out.append((f"{CASTLE_DIR}/{name}/{f}", os.path.join(d, f)))
    return out


# ------------------------------------------------------------------ the game's sheets
def vanilla(rel: str, c=None) -> tuple[dict, dict]:
    """({key: (header, rows)}, {(key, sub): (header, items)}) of one file as dumped."""
    C = castle()
    c = c or C.L.container(rel)
    tables, items = {}, {}
    for d in C.defs_by_file(C.reg)[rel]:
        cod = C.codec(c, d)
        tables[d.key] = (C.L.columns(cod.fields), cod.rows())
        for f in cod.fields:
            if f.kind == "list":
                items[(d.key, f.sub)] = (C.L.sub_columns(cod.subs[f.sub]), cod.items(f))
    return tables, items


def same_value(a: str, b: str) -> bool:
    """Equal cells: the same text, or the same number (0x10 = 16, 1.0 = 1)."""
    a, b = a.strip(), b.strip()
    if a == b:
        return True
    try:
        return int(a, 0) == int(b, 0)
    except ValueError:
        pass
    try:
        return float(a) == float(b)
    except ValueError:
        return False


def write_folder(mod_dir: str, name: str, keys: list[str] | None = None) -> str:
    """mods/<Name>/castle/<name>/ with the game's sheets (all of the file, or `keys`)."""
    C = castle()
    folders = file_folders()
    if name not in folders:
        raise ValueError(f"no castle file called {name}; one of: {', '.join(sorted(folders))}")
    rel = folders[name]
    tables, items = vanilla(rel)
    d = os.path.join(mod_dir, CASTLE_DIR, name)
    os.makedirs(d, exist_ok=True)
    for key, (h, rows) in tables.items():
        if keys and key not in keys:
            continue
        C.L.write_csv(os.path.join(d, f"{key}.csv"), h, rows)
    for (key, sub), (h, rows) in items.items():
        if keys and key not in keys:
            continue
        C.L.write_csv(os.path.join(d, f"{key}__{sub}.csv"), h, rows)
    return d


# ------------------------------------------------------------------ one mod
def diff_mod(mod) -> tuple[dict, dict, list[str], list[str]]:
    """One mod's castle/ folders. Returns (cells {(rel, sheet, row, item, col): (value, where)},
    new rows {(rel, key): [row, ...]}, errors, notes). `sheet` is a KEY or KEY__LIST;
    item is -1 for sheet rows."""
    C = castle()
    cells: dict = {}
    new: dict = {}
    errors, notes = [], []
    folders = file_folders()
    for name, d in packages(mod.dir):
        where = f"{mod.name}/{CASTLE_DIR}/{name}"
        if name not in folders:
            errors.append(f"{where}: no castle file called {name}; the folder name must be one of "
                          f"{', '.join(sorted(folders))}")
            continue
        rel = folders[name]
        try:
            tables, items = vanilla(rel)
        except (C.L.SheetError, C.T.LayoutError, OSError) as e:
            errors.append(f"{where}: {rel} cannot be read: {e}")
            continue
        known = {f"{k}.csv": (k, None) for k in tables}
        known.update({f"{k}__{s}.csv": (k, s) for (k, s) in items})
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith(".csv"):
                continue
            w = f"{where}/{f}"
            if f not in known:
                errors.append(f"{w}: not a sheet of {rel}; the file names are {', '.join(sorted(known))} "
                              "(as python tools/castle/castle.py dump writes them)")
                continue
            key, sub = known[f]
            try:
                head, rows = C.L.read_csv(os.path.join(d, f))
            except (C.L.SheetError, OSError, UnicodeError) as e:
                errors.append(f"{w}: {e}")
                continue
            vhead, vrows = tables[key] if sub is None else items[(key, sub)]
            if head != vhead:
                errors.append(f"{w}: the columns are not the dumped ones ({', '.join(vhead)})")
                continue
            sheet = key if sub is None else f"{key}__{sub}"
            nfix = 2 if sub is None else 3        # index, label (, item): not editable cells
            if sub is not None and len(rows) != len(vrows):
                errors.append(f"{w}: {len(rows)} items, the game has {len(vrows)}; list items can be edited "
                              "but not added or removed (docs/CASTLE.md)")
                continue
            if len(rows) < len(vrows):
                errors.append(f"{w}: {len(rows)} rows, the game has {len(vrows)}; rows cannot be removed "
                              "(the game finds rows by number)")
                continue
            bad = False
            for i, (r, v) in enumerate(zip(rows, vrows)):
                if len(r) != len(vhead):
                    errors.append(f"{w} row {i}: {len(r)} cells, need {len(vhead)}")
                    bad = True
                    break
                if [x.strip() for x in r[:nfix]] != v[:nfix]:
                    errors.append(f"{w} line {i + 2}: the {'/'.join(vhead[:nfix])} columns must stay as "
                                  f"dumped ({', '.join(v[:nfix])}); rows cannot be moved or renamed")
                    bad = True
                    break
                for j in range(nfix, len(vhead)):
                    if not same_value(r[j], v[j]):
                        item = int(v[2]) if sub is not None else -1
                        cells[(rel, sheet, int(v[0]), item, vhead[j])] = (r[j].strip(), w)
            if bad:
                continue
            extra = rows[len(vrows):]
            if extra:
                dfn = C.reg[key]
                if dfn.append != "allow":
                    errors.append(f"{w}: {len(extra)} row(s) past the end, but adding rows to {key} is "
                                  f"refused: {dfn.evidence}")
                    continue
                for k, r in enumerate(extra):
                    if len(r) != len(vhead):
                        errors.append(f"{w} new row {len(vrows) + k}: {len(r)} cells, need {len(vhead)}")
                        bad = True
                    elif r[0].strip() != str(len(vrows) + k):
                        errors.append(f"{w}: new rows must be numbered {len(vrows)}, {len(vrows) + 1}, ... "
                                      f"(found {r[0]!r} where {len(vrows) + k} belongs)")
                        bad = True
                if not bad:
                    new[(rel, key)] = [[x.strip() for x in r] for r in extra]
    return cells, new, errors, notes


# ------------------------------------------------------------------ all mods
def merge_castle(ctx, mods: list) -> tuple[dict, dict, list, list, list]:
    """Enabled mods' castle/ folders in order, rebuilt and read back. Returns
    (files {RomFS path: (bytes, mod names)}, per-mod changed-cell counts, errors, warnings,
    notes)."""
    out: dict[str, tuple[bytes, str]] = {}
    counts: dict[str, int] = {}
    errors, warnings, notes = [], [], []
    users = [m for m in mods if m.enabled and packages(m.dir)]
    if not users:
        return out, counts, errors, warnings, notes
    why = status()
    if why:
        return out, counts, [f"{m.name}: castle mods are not available: {why}" for m in users], [], []
    C = castle()
    merged: dict = {}                     # (rel, sheet, row, item, col) -> (value, mod)
    new_rows: dict = {}                   # (rel, key) -> [(row, mod)]
    for m in users:
        cells, new, errs, nts = diff_mod(m)
        errors += errs
        notes += nts
        counts[m.name] = len(cells) + sum(len(v) for v in new.values())
        for k, (v, _w) in cells.items():
            prev = merged.get(k)
            if prev is None or same_value(prev[0], v):
                merged[k] = (v, prev[1] if prev else m.name)
            elif m.override:
                notes.append(f"castle {k[1]} row {k[2]} {k[4]}: {m.name} overrides {prev[1]}")
                merged[k] = (v, m.name)
            else:
                errors.append(f"conflict: castle {k[1]} row {k[2]}" + (f" item {k[3]}" if k[3] >= 0 else "")
                              + f" {k[4]} is set to {prev[0]} by {prev[1]} and to {v} by {m.name} (set "
                              f"\"override\": true in {m.name}/mod.json to let the later mod win)")
        for k, rows in new.items():
            if k in new_rows:
                notes.append(f"castle {k[1]}: new rows from {m.name} go after those of "
                             f"{', '.join(sorted({x[1] for x in new_rows[k]}))} (renumbered)")
            new_rows.setdefault(k, []).extend((r, m.name) for r in rows)
    if errors:
        return {}, counts, errors, warnings, notes
    for rel in sorted({k[0] for k in merged} | {k[0] for k in new_rows}):
        try:
            orig = C.L.container(rel)
            tables, items = vanilla(rel, orig)
        except (C.L.SheetError, C.T.LayoutError, OSError) as e:
            errors.append(f"castle {rel}: cannot be read: {e}")
            continue
        who: set[str] = set()
        want_t = {k: (h, [list(r) for r in rows]) for k, (h, rows) in tables.items()}
        want_i = {k: (h, [list(r) for r in rows]) for k, (h, rows) in items.items()}
        edited_t, edited_i = set(), set()
        for (r_, sheet, row, item, col), (v, m) in merged.items():
            if r_ != rel:
                continue
            who.add(m)
            if "__" in sheet:
                key, sub = sheet.split("__", 1)
                h, rows = want_i[(key, sub)]
                ix = next(n for n, x in enumerate(rows) if x[0] == str(row) and x[2] == str(item))
                rows[ix][h.index(col)] = v
                edited_i.add((key, sub))
            else:
                h, rows = want_t[sheet]
                rows[row][h.index(col)] = v
                edited_t.add(sheet)
        for (r_, key), lst in new_rows.items():
            if r_ != rel:
                continue
            h, rows = want_t[key]
            for r, m in lst:
                rows.append([str(len(rows))] + r[1:])
                who.add(m)
            edited_t.add(key)
        mods_s = ", ".join(sorted(who))
        try:
            data = C.build_file(C.reg, rel, {k: want_t[k] for k in edited_t},
                                {k: want_i[k] for k in edited_i}, orig)
        except (C.L.SheetError, C.T.LayoutError, ValueError, KeyError, IndexError) as e:
            errors.append(f"castle {rel} [{mods_s}]: {e}")
            continue
        if data == orig.raw:
            notes.append(f"castle {rel}: the edits give back the game's file; not staged")
            continue
        lzt = lambda b: b[0] if b and b[0] in (0x10, 0x11, 0x13) else None   # noqa: E731
        if lzt(data) != lzt(orig.raw):
            errors.append(f"castle {rel}: rebuilt file is not in the game's LZ format")
            continue
        try:
            got_t, got_i = vanilla(rel, C.T.Container(rel, data))
        except Exception as e:          # any failure to read back refuses the file
            errors.append(f"castle {rel}: rebuilt file does not read back ({type(e).__name__}: {e})")
            continue
        norm = lambda rows: [[x.strip() for x in r] for r in rows]   # noqa: E731
        for k, (h, rows) in want_t.items():
            g = got_t[k][1]
            if len(g) != len(rows) or any(not all(same_value(a, b) for a, b in zip(x, y))
                                          for x, y in zip(g, norm(rows))):
                errors.append(f"castle {rel}: {k} does not decode back to the edit")
        for k, (h, rows) in want_i.items():
            g = got_i[k][1]
            if len(g) != len(rows) or any(not all(same_value(a, b) for a, b in zip(x, y))
                                          for x, y in zip(g, norm(rows))):
                errors.append(f"castle {rel}: {k[0]}__{k[1]} does not decode back to the edit")
        if errors:
            continue
        out[rel] = (data, mods_s)
    if errors:
        return {}, counts, errors, warnings, notes
    return out, counts, errors, warnings, notes


# ------------------------------------------------------------------ the demo
def example_dish(rows: list[list[str]], head: list[str], ingredient: int) -> int:
    """The row of the dish made from `ingredient` alone (ingredient_2 = 255 = none)."""
    h = {c: i for i, c in enumerate(head)}
    hits = [i for i, r in enumerate(rows)
            if int(r[h["ingredient_1"]], 0) == ingredient and int(r[h["ingredient_2"]], 0) == 255]
    if len(hits) != 1:
        raise ValueError(f"expected one dish made from ingredient {ingredient} alone, found {len(hits)}")
    return hits[0]
