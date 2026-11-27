#!/usr/bin/env python3
"""Verify every table layout in config/tables/ against every record of the user's RomFS.

Standard library only. For each table in config/tables/tables.csv that has a layout file
(config/tables/<table>.csv), in every file the table lives in:

  * the fields tile the record exactly (no gap, no overlap, sum = record size);
  * pointer fields (str, ptr, ptr:T) hold a relocated word or 0 in every record, and no
    other field ever contains a relocation;
  * str fields point at a NUL-terminated string that decodes as Shift-JIS (cp932);
    str:self fields equal a label exported at the record's start;
  * ptr:T fields point at the start of a record of table T in the same file;
  * flagsN:ID fields only use bit numbers that exist in the ID-list table ID, and
    enumN:ID fields only hold numbers that exist there;
  * refN:T fields are < T's record count (or all-ones = none);
  * pad fields are zero;
  * cross-table rules (extra_checks): the GameData header counts equal the located
    tables, Dispos groups are contiguous and cover every unit, terrain grids only use
    tile numbers that exist in the same file, the ExpTable / AchieveBonus / Arena
    sub-tables follow each other, TerrainCost rows are as wide as the header says and
    every terrain file's cost columns fit, ID numbers equal record indexes;
  * tables with count fixed:N (no stored count) end exactly where the next pointer
    target or label begins, with only zero bytes in between, and nothing points inside
    one of their records.

`--stats TABLE` prints per-field value statistics (min/max/distinct/zero count) to the
console only, to help write layouts; nothing is written to tracked files.

`--selftest` mutates every layout (drop a field, read a pointer as u32, call a used field
padding, swap the ID string with the next word), gives every fixed:N table the counts
N-1 and N+1, and requires each mutation to fail.

Usage:
    python tools/tables/check.py [TABLE ...] [--stats TABLE] [--selftest]
Exit status 0 when every layout passes.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tablelib as T  # noqa: E402


def record_starts(reg, name, rel):
    t = reg[name]
    c = T.container(rel)
    start, count = T.locate(t, c)
    return {start + i * t.size for i in range(count)}, count


def check_table(reg, name: str, fields=None) -> tuple[int, list[str]]:
    t = reg[name]
    mutated = fields is not None
    fields = T.load_layout(name) if fields is None else fields
    errs = [f"{name}: {e}" for e in T.tile_errors(fields, t.size)]
    nrec = 0
    counts_cache: dict[str, int] = {}
    idbits_cache: dict[str, int] = {}
    files = t.files()
    if not files:
        errs.append(f"{name}: no input file matches {t.file}")
    for rel in files:
        c = T.container(rel)
        try:
            start, count = T.locate(t, c)
        except T.LayoutError as e:
            errs.append(str(e))
            continue
        nrec += count
        ptr_offsets = {f.offset for f in fields if f.kind in ("str", "ptr", "lptr")}
        targets_cache: dict[str, set[int]] = {}
        for i in range(count):
            base = start + i * t.size
            where = f"{name}[{i}] in {rel}"
            # relocations must sit exactly on pointer fields
            for r in range(base, base + t.size, 4):
                if r in c.relset and (r - base) not in ptr_offsets:
                    errs.append(f"{where}: relocation at +{r - base:#x} is not a pointer field")
            for f in fields:
                o = base + f.offset
                if f.kind in ("str", "ptr", "lptr"):
                    v = c.u32(o)
                    if o not in c.relset:
                        if v != 0:
                            errs.append(f"{where}: {f.name} (+{f.offset:#x}) not relocated but non-zero")
                        continue
                    if f.kind == "str":
                        s = c.string_at(v)
                        if s is None:
                            errs.append(f"{where}: {f.name} string pointer runs off the table")
                        else:
                            try:
                                if s.decode("cp932").encode("cp932") != s:
                                    raise UnicodeError
                            except UnicodeError:
                                errs.append(f"{where}: {f.name} string is not clean Shift-JIS")
                            if f.ref == "self" and s not in c.labels_at.get(base, []):
                                errs.append(f"{where}: {f.name} is not a label of this record")
                    elif f.kind == "lptr":
                        if f.ref not in targets_cache:
                            try:
                                targets_cache[f.ref], _ = record_starts(reg, f.ref, rel)
                            except (T.LayoutError, KeyError) as e:
                                errs.append(f"{where}: {f.name}: target table {f.ref}: {e}")
                                targets_cache[f.ref] = set()
                        if v not in targets_cache[f.ref]:
                            errs.append(f"{where}: {f.name} points at {v:#x}, not a {f.ref} record")
                    elif v > len(c.data):
                        errs.append(f"{where}: {f.name} data pointer past the data region")
                elif f.kind == "pad":
                    if any(c.data[o:o + f.size]):
                        errs.append(f"{where}: pad +{f.offset:#x} is not zero")
                elif f.kind == "enum":
                    v = int.from_bytes(c.data[o:o + f.width], "little")
                    if f.ref not in idbits_cache:
                        idbits_cache[f.ref] = len(T.id_names(f.ref, reg))
                    if v >= idbits_cache[f.ref]:
                        errs.append(f"{where}: {f.name} = {v}, {f.ref} has {idbits_cache[f.ref]} values")
                elif f.kind == "flags":
                    v = int.from_bytes(c.data[o:o + f.width], "little")
                    if f.ref not in idbits_cache:
                        idbits_cache[f.ref] = len(T.id_names(f.ref, reg))
                    if v >> idbits_cache[f.ref]:
                        errs.append(f"{where}: {f.name} uses bit {v.bit_length() - 1}, "
                                    f"{f.ref} has {idbits_cache[f.ref]} names")
                elif f.kind == "ref":
                    if f.ref not in counts_cache:
                        rt = reg[f.ref]
                        counts_cache[f.ref] = T.locate(rt, T.container(rt.files()[0]))[1]
                    for k in range(f.n):
                        v = int.from_bytes(c.data[o + k * f.width:o + (k + 1) * f.width], "little")
                        if v >= counts_cache[f.ref] and v != (1 << (8 * f.width)) - 1:
                            errs.append(f"{where}: {f.name}[{k}] = {v} >= {f.ref} count {counts_cache[f.ref]}")
    return nrec, errs + (extra_checks(reg, name) if not mutated else [])


def boundaries(c: T.Container) -> list[int]:
    """Sorted data offsets something points at or labels (relocation targets inside the
    data region, exported labels) plus the end of the data region."""
    out = {len(c.data)}
    out.update(o for o in c.labels_at)
    for r in c.b.relocs:
        v = c.u32(r)
        if v < len(c.data):
            out.add(v)
    return sorted(out)


def fixed_count_errors(reg, name: str) -> list[str]:
    """A table with count fixed:N has no stored count, so prove N against the file: no
    pointer target or label may fall inside the table after its first record, except a
    label exported at one of its own record starts (N is not too large: the next table
    is pointed at), and only zero bytes may lie between its end and the next pointer
    target or label (N is not too small: a further record would be non-zero)."""
    import bisect
    t = reg[name]
    errs = []
    for rel in t.files():
        c = T.container(rel)
        start, n = T.locate(t, c)
        end = start + n * t.size
        bs = boundaries(c)
        inner = [b for b in bs[bisect.bisect_right(bs, start):bisect.bisect_left(bs, end)]
                 if (b - start) % t.size or b not in c.labels_at]
        if inner:
            errs.append(f"{name} in {rel}: something points inside a record at {inner[0]:#x} "
                        f"(count {t.count} too large?)")
        nxt = bs[bisect.bisect_left(bs, end)]
        if any(c.data[end:nxt]):
            errs.append(f"{name} in {rel}: non-zero bytes between the table end {end:#x} and the next "
                        f"pointer target {nxt:#x} (count {t.count} too small?)")
    return errs


NUMBER_IS_INDEX = {"Personality": (0x0, 4), "ItemKind": (0x0, 4), "ItemSubKind": (0x0, 1),
                   "Tutorial": (0x4, 2)}


def extra_checks(reg, name: str) -> list[str]:
    """Rules that tie several tables (or a table and its file) together."""
    errs: list[str] = []
    if reg[name].count.startswith("fixed:"):
        errs += fixed_count_errors(reg, name)
    if name in NUMBER_IS_INDEX:
        off, w = NUMBER_IS_INDEX[name]
        c = T.container(reg[name].files()[0])
        s, n = T.locate(reg[name], c)
        bad = [i for i in range(n)
               if int.from_bytes(c.data[s + i * reg[name].size + off:s + i * reg[name].size + off + w], "little") != i]
        if bad:
            errs.append(f"{name}: the number at +{off:#x} differs from the record index in records {bad[:5]}")
    if name == "TerrainCost":
        c = T.container(reg[name].files()[0])
        cols = c.u32(T.locate(reg["TerrainCostHeader"], c)[0])
        if cols != reg[name].size:
            errs.append(f"{name}: TerrainCostHeader.columns = {cols}, the layout has {reg[name].size} columns per row")
        tt = reg["TerrainTile"]
        for rel in tt.files():
            tc = T.container(rel)
            ts, tn = T.locate(tt, tc)
            hi = max((tc.data[ts + i * tt.size + 0x10] for i in range(tn)), default=0)
            if hi >= cols:
                errs.append(f"{name}: {rel} uses terrain cost column {hi}, rows have {cols}")
    if name == "ExpTableHeader":
        c = T.container(reg[name].files()[0])
        pos = None
        for sub in ("ExpBattle", "ExpBattleFloor", "ExpRod", "ExpRodHigh", "ExpDance", "ExpSupport"):
            s, n = T.locate(reg[sub], c)
            if pos is not None and s != pos:
                errs.append(f"{name}: {sub} starts at {s:#x}, the previous sub-table ends at {pos:#x}")
            pos = s + n * reg[sub].size
    if name in ("AchieveBonusHeader", "ArenaHeader"):
        c = T.container(reg[name].files()[0])
        hs = T.locate(reg[name], c)[0]
        subs = ([f"AchieveBonus{k}" for k in ("Route", "Battle", "Visit", "List4")] if name == "AchieveBonusHeader"
                else ["ArenaLow", "ArenaHigh"])
        pos = hs + reg[name].size
        for sub in subs:
            s, n = T.locate(reg[sub], c)
            if s != pos:
                errs.append(f"{name}: {sub} starts at {s:#x}, expected {pos:#x} (lists follow each other)")
            pos = s + n * reg[sub].size
        nxt = [b for b in boundaries(c) if b >= pos][0]
        if any(c.data[pos:nxt]):
            errs.append(f"{name}: non-zero bytes after the last list ({pos:#x}..{nxt:#x})")
    if name == "GameDataHeader":
        c = T.container(reg[name].files()[0])
        for off, tname in ((0x04, "Chapter"), (0x18, "Skill"), (0x28, "Belong"), (0x58, "Tutorial")):
            n = T.locate(reg[tname], c)[1]
            if c.u32(off) != n or n != len(T.record_labels(reg[tname], c, *T.locate(reg[tname], c))):
                errs.append(f"{name}: count at +{off:#x} = {c.u32(off)}, {tname} has {n} records")
        for tname, prefix in (("Chapter", b"CID_"), ("Person", b"PID_"), ("Job", b"JID_"), ("Skill", b"SEID_"),
                              ("Belong", b"BID_"), ("Item", b"IID_"), ("Tutorial", b"TUTID_")):
            n = T.locate(reg[tname], c)[1]
            if n != len(c.family(prefix)):
                errs.append(f"{name}: {tname} has {n} records but the file exports {len(c.family(prefix))} {prefix.decode()} labels")
    elif name == "DisposFaction":
        ut = reg["DisposUnit"]
        for rel in reg[name].files():
            c = T.container(rel)
            s, n = T.locate(reg[name], c)
            us, un = T.locate(ut, c)
            pos = us
            for i in range(n):
                o = s + i * 12
                first, cnt = c.u32(o + 4), c.u32(o + 8)
                if cnt and first != pos:
                    errs.append(f"{name}[{i}] in {rel}: group starts at {first:#x}, expected {pos:#x}")
                pos += cnt * ut.size
            if pos != us + un * ut.size:
                errs.append(f"{name} in {rel}: groups cover {(pos - us) // ut.size} units, the file has {un}")
            if us != s + (n + 1) * 12:
                errs.append(f"{name} in {rel}: units do not start right after the group list terminator")
    elif name == "TerrainGrid":
        tt, th = reg["TerrainTile"], reg["TerrainHeader"]
        for rel in reg[name].files():
            c = T.container(rel)
            s, _n = T.locate(reg[name], c)
            ntile = T.locate(tt, c)[1]
            if c.u32(T.locate(th, c)[0] + 4) != len(c.family(b"TID_")):
                errs.append(f"{name} in {rel}: tile_count does not match the TID_ labels")
            bad = sorted({b for b in c.data[s + 0x18:s + 0x418] if b >= ntile})
            if bad:
                errs.append(f"{name} in {rel}: grid uses tile numbers {bad} but the file has {ntile} tiles")
    return errs


def stats(reg, name: str) -> None:
    t = reg[name]
    try:
        fields = T.load_layout(name)
    except FileNotFoundError:
        fields = [T.Field({"offset": hex(o), "size": "1", "type": "u8", "name": f"b{o:X}",
                           "confidence": "low", "evidence": ""}, name) for o in range(t.size)]
    per: dict[str, Counter] = {}
    rel_n: Counter = Counter()
    n = 0
    for rel in t.files():
        c = T.container(rel)
        start, count = T.locate(t, c)
        for i in range(count):
            n += 1
            base = start + i * t.size
            for f in fields:
                o = base + f.offset
                if f.kind in ("int", "flags", "ref", "pad", "enum", "hex"):
                    w = f.width if f.kind not in ("pad", "hex") else f.size
                    for k in range(f.n if f.kind in ("int", "ref") else 1):
                        raw = c.data[o + k * w:o + (k + 1) * w]
                        v = int.from_bytes(raw, "little", signed=f.signed and f.kind == "int")
                        per.setdefault(f"{f.offset + k * w:#05x} {f.name}[{k}]" if f.n > 1 else
                                       f"{f.offset:#05x} {f.name}", Counter())[v] += 1
                else:
                    rel_n[f"{f.offset:#05x} {f.name}"] += (o in c.relset)
                    per.setdefault(f"{f.offset:#05x} {f.name}", Counter())[c.u32(o) != 0] += 1
    print(f"{name}: {n} records")
    for k, cnt in per.items():
        vals = sorted(cnt)
        extra = f" relocated={rel_n[k]}" if k in rel_n else ""
        print(f"  {k:32} min={vals[0]} max={vals[-1]} distinct={len(vals)} zero={cnt.get(0, 0)}{extra}")


def selftest(reg) -> int:
    """Negative controls: each mutated layout must fail. Returns the number of mutations
    that were (wrongly) accepted."""
    import copy
    accepted = 0
    tried = 0
    for name in [n for n in reg if os.path.exists(T.layout_path(n))]:
        base = T.load_layout(name)
        muts = []
        muts.append(("drop first field", base[1:]))
        for f in base:
            if f.kind in ("str", "ptr", "lptr"):
                g = copy.copy(f)
                g.kind, g.type = "int", "u32"
                muts.append((f"pointer {f.name} as u32", [g if x is f else x for x in base]))
                break
        t = reg[name]
        c = T.container(t.files()[0])
        start, count = T.locate(t, c)

        def used(f):
            return any(any(c.data[start + i * t.size + f.offset:start + i * t.size + f.offset + f.size])
                       for i in range(count))
        for f in base:
            if f.kind == "int" and used(f):
                g = copy.copy(f)
                g.kind, g.type = "pad", "pad"
                muts.append((f"{f.name} as pad", [g if x is f else x for x in base]))
                break
        for f in base:
            if f.kind == "str" and f.ref == "self":
                g = copy.copy(f)
                g.offset += 4
                h = [x for x in base if x.offset == f.offset + 4]
                if h and h[0].size == 4:
                    k = copy.copy(h[0])
                    k.offset -= 4
                    muts.append((f"{f.name} swapped with the next word", [k if x is h[0] else g if x is f else x for x in base]))
                break
        for label, fields in muts:
            fields = sorted(fields, key=lambda x: x.offset)
            tried += 1
            _, errs = check_table(reg, name, fields)
            if not errs:
                accepted += 1
                print(f"  NOT DETECTED: {name}: {label}")
        if t.count.startswith("fixed:"):
            n = int(t.count[6:], 0)
            for wrong in (n - 1, n + 1):
                bad = copy.copy(t)
                bad.count = f"fixed:{wrong}"
                tried += 1
                if not fixed_count_errors(dict(reg, **{name: bad}), name):
                    accepted += 1
                    print(f"  NOT DETECTED: {name}: count fixed:{wrong}")
    print(f"self-test: {tried - accepted}/{tried} mutated layouts rejected")
    return accepted


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tables", nargs="*")
    ap.add_argument("--stats")
    ap.add_argument("--selftest", action="store_true", help="also check that broken layouts are rejected")
    a = ap.parse_args()
    reg = T.registry()
    if a.stats:
        stats(reg, a.stats)
        return 0
    names = a.tables or [n for n in reg if os.path.exists(T.layout_path(n))]
    bad = 0
    total_fields = 0
    for name in names:
        nrec, errs = check_table(reg, name)
        nf = len(T.load_layout(name))
        total_fields += nf
        status = "OK" if not errs else f"FAIL ({len(errs)})"
        print(f"{name:16} {len(reg[name].files()):3} file(s) {nrec:5} records x {reg[name].size:#5x} "
              f"bytes, {nf:3} fields: {status}")
        for e in errs[:20]:
            print("    " + e)
        bad += bool(errs)
    print(f"{len(names) - bad}/{len(names)} layouts pass ({total_fields} fields)")
    if a.selftest and selftest(reg):
        bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
