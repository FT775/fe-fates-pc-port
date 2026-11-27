#!/usr/bin/env python3
"""The step-4 look: one mod, `mods/LookStep4`, with one easy-to-see edit in each of the four
stat tables (people, classes, items, skills) and one castle edit (docs/LOOK_STEP4.md).

    python tools/mods/look_step4.py install      make mods/LookStep4 if it is missing, then
                                                 build and install it (tools/mods/mods.py install)
    python tools/mods/look_step4.py make         only make mods/LookStep4 (prints every edit)
    python tools/mods/look_step4.py check        build into a scratch folder, read every edited
                                                 field back from the built files, install into a
                                                 scratch Zakuro-style folder under build/look_step4/check/ and
                                                 uninstall back byte-identical (never %APPDATA%)
    python tools/mods/mods.py uninstall          takes it out again

The edits (rows are found at run time by their English names in your own game files, so no
game data is stored in this repository):

  Person  both avatar rows (Corrin, male and female)  base.hp     +5
  Job     the six Corrin classes (Nohr Prince/Princess, Nohr Noble, Hoshido Noble)  mov  +2
  Item    Bronze Sword                                might       +10
  Skill   Supportive (Corrin's personal skill)        icon        -> Nobility's icon
  Castle  DiningData_Dish, every dish                 lck         0 -> +2 (no dish gives Luck in the game)

Standard library only. Writes only into the mods folder (default mods/), the stage folder
and, for `install`, Zakuro's mod folder for Fates - exactly like tools/mods/mods.py.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

MOD_NAME = "LookStep4"
AVATAR_PIDS_SUFFIX = ("男", "女")          # PID_<player>男 / 女: the two avatar rows
AVATAR_PID_PREFIX = "PID_プレイヤー"
PERSON_COL, PERSON_DELTA = "base.hp", 5
JOB_NAMES = ("Nohr Prince", "Nohr Princess", "Nohr Noble", "Hoshido Noble")
JOB_COL, JOB_DELTA = "mov", 2
ITEM_NAME, ITEM_COL, ITEM_DELTA = "Bronze Sword", "might", 10
SKILL_NAME, SKILL_ICON_FROM, SKILL_COL = "Supportive", "Nobility", "icon"
CASTLE_FILE, CASTLE_SHEET, CASTLE_COL, CASTLE_VALUE = "DiningData", "DiningData_Dish", "lck", 2


def load_mods():
    spec = importlib.util.spec_from_file_location("fe14_mods_for_look", os.path.join(HERE, "mods.py"))
    M = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = M
    spec.loader.exec_module(M)
    return M


def english_names(M, ctx) -> dict[str, str]:
    arc = M.TX.archive(M.NAME_ARCHIVE, ctx.romfs)
    return {M.T.text(lab): arc.text_of[lab] for lab, _v, a in arc.entries if not a}


def plan(M, ctx) -> list[dict]:
    """Every edit: table, row key, column, old, new, and a plain description."""
    why = M.tables_status()
    if why:
        raise M.ModError(f"the look needs the table layouts: {why}")
    van = M.vanilla()
    names = english_names(M, ctx)
    out = []

    def rows_named(table, namecol, wanted):
        head, rows = van[table]
        ix = {c: i for i, c in enumerate(head)}
        return head, ix, [r for r in rows if names.get(r[ix[namecol]]) in wanted]

    def add(table, head, ix, r, col, new, what):
        old = int(r[ix[col]], 0)
        f, _k = M.cells_of(table).info[col]
        lo, hi = M.int_range(f.width, f.signed)
        if not lo <= new <= hi:
            raise M.ModError(f"{table} {col}: {new} does not fit ({lo}..{hi})")
        out.append({"table": table, "key": M.row_key(table, r), "row": r, "head": head, "col": col,
                    "old": old, "new": new, "what": what})

    # Person: the two avatar rows (labels PID_<player>男/女), in the main file
    head, rows = van["Person"]
    ix = {c: i for i, c in enumerate(head)}
    first = M.reg()["Person"].files()[0]
    av = [r for r in rows if r[ix["label"]] in {AVATAR_PID_PREFIX + s for s in AVATAR_PIDS_SUFFIX}
          and M.row_rel("Person", M.row_key("Person", r)) == first]
    if len(av) != 2:
        raise M.ModError(f"expected the two avatar rows in {first}, found {len(av)}")
    for r, who in zip(av, ("Corrin (male)", "Corrin (female)")):
        add("Person", head, ix, r, PERSON_COL, int(r[ix[PERSON_COL]]) + PERSON_DELTA,
            f"{who}: personal HP {PERSON_COL}")
    # Job: the Corrin classes
    head, ix, hit = rows_named("Job", "mjid_name", set(JOB_NAMES))
    if len(hit) != 6:
        raise M.ModError(f"expected 6 Corrin class rows ({', '.join(JOB_NAMES)}), found {len(hit)}")
    for r in hit:
        add("Job", head, ix, r, JOB_COL, int(r[ix[JOB_COL]]) + JOB_DELTA,
            f"class {names[r[ix['mjid_name']]]} ({r[ix['label']]}): movement")
    # Item: the Bronze Sword (lowest-numbered row of that name)
    head, ix, hit = rows_named("Item", "miid_name", {ITEM_NAME})
    if not hit:
        raise M.ModError(f"no Item named {ITEM_NAME!r}")
    r = hit[0]
    add("Item", head, ix, r, ITEM_COL, int(r[ix[ITEM_COL]]) + ITEM_DELTA, f"item {ITEM_NAME}: might")
    # Skill: Supportive shows Nobility's icon
    head, ix, hit = rows_named("Skill", "mseid_name", {SKILL_NAME, SKILL_ICON_FROM})
    by = {names[r[ix["mseid_name"]]]: r for r in hit}
    if set(by) != {SKILL_NAME, SKILL_ICON_FROM} or len(hit) != 2:
        raise M.ModError(f"expected one Skill row each for {SKILL_NAME!r} and {SKILL_ICON_FROM!r}")
    add("Skill", head, ix, by[SKILL_NAME], SKILL_COL, int(by[SKILL_ICON_FROM][ix[SKILL_COL]]),
        f"skill {SKILL_NAME}: icon number (now the same as {SKILL_ICON_FROM})")
    return out


def make(M, ctx) -> list[str]:
    edits = plan(M, ctx)
    m = M.new_mod(ctx, MOD_NAME, "The step-4 look (docs/LOOK_STEP4.md): Corrin HP +5, Corrin classes "
                  "Mov +2, Bronze Sword might +10, Supportive shows Nobility's icon, every dish gives Luck +2",
                  tables=[])
    lines = []
    try:
        for table in ("Person", "Job", "Item", "Skill"):
            mine = [e for e in edits if e["table"] == table]
            head = mine[0]["head"]
            ids = [h for h in head if h in M.ID_COLS]
            cols = sorted({e["col"] for e in mine}, key=head.index)
            rows = []
            for e in mine:
                r = e["row"]
                rows.append([r[head.index(h)] for h in ids] + [str(e["new"]) if c == e["col"] else r[head.index(c)]
                                                              for c in cols])
                lines.append(f"{table} #{r[head.index('index')]} {e['what']}: {e['old']} -> {e['new']}")
            M.write_table_csv(os.path.join(m.dir, "tables", f"{table}.csv"), ids + cols, rows)
        d = M.add_castle(ctx, m, CASTLE_FILE, [CASTLE_SHEET])
        p = os.path.join(d, f"{CASTLE_SHEET}.csv")
        L = M.CM.castle().L
        head, rows = L.read_csv(p)
        j = head.index(CASTLE_COL)
        olds = sorted({int(r[j], 0) for r in rows})
        for r in rows:
            r[j] = str(CASTLE_VALUE)
        L.write_csv(p, head, rows)
        lines.append(f"Castle {CASTLE_SHEET}: {CASTLE_COL} of all {len(rows)} dishes {olds} -> {CASTLE_VALUE}")
    except Exception:
        shutil.rmtree(m.dir, ignore_errors=True)
        raise
    return lines


def tree_hash(top: str) -> dict[str, str]:
    out = {}
    for dp, _dn, fn in os.walk(top):
        for f in fn:
            p = os.path.join(dp, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, top)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def check(M) -> int:
    """Scratch proof: make, build, read back every edited field from the built files,
    install into a scratch Zakuro folder (with an unrelated file of 'the owner' in it),
    uninstall back byte-identical. Everything lives under build/look_step4/check/."""
    top = os.path.join(ROOT, "build", "look_step4", "check")
    shutil.rmtree(top, ignore_errors=True)
    zak = os.path.join(top, "zakuro")
    ctx = M.Ctx(mods_dir=os.path.join(top, "mods"), stage_dir=os.path.join(top, "stage"), zakuro_dir=zak)
    assert os.path.abspath(ctx.zakuro_dir).startswith(os.path.abspath(top)), "scratch only"
    os.makedirs(ctx.mods_dir)
    bad = []
    for line in make(M, ctx):
        print("  edit:", line)
    r = M.build(ctx)
    if r.errors:
        for e in r.errors:
            print("  build error:", e)
        return 1
    files = r.paths()
    print(f"  built {len(files)} file(s): {', '.join(files)}")
    built = ctx.stage_romfs
    # read back every table from the built files with tools/tables: exactly the planned cells differ
    edits = plan(M, ctx)
    want = {(e["table"], e["key"], e["col"]): e for e in edits}
    seen = set()
    for table in ("Person", "Job", "Item", "Skill"):
        head, vrows = M.vanilla()[table]
        got = decode_built(M, table, built)
        if got is None:
            bad.append(f"{table}: its file was not built"); continue
        if len(got) != len(vrows):
            bad.append(f"{table}: {len(got)} rows built, {len(vrows)} in the game"); continue
        for g, v in zip(got, vrows):
            key = M.row_key(table, v)
            for j, c in enumerate(head):
                if g[j] == v[j]:
                    continue
                e = want.get((table, key, c))
                if e is None or int(g[j], 0) != e["new"] or int(v[j], 0) != e["old"]:
                    bad.append(f"{table} {M.key_text(table, key)} {c}: {v[j]} -> {g[j]} (not planned)")
                else:
                    seen.add((table, key, c))
                    print(f"  read back {table} #{v[head.index('index')]} {e['what']}: game {e['old']}, "
                          f"built file {g[j]} OK")
    for k, e in want.items():
        if k not in seen:
            bad.append(f"{e['table']} {e['what']}: not changed in the built file")
    # castle read back through tools/castle
    rel = f"GameData/Castle/{CASTLE_FILE}.bin.lz"
    if rel not in files:
        bad.append(f"{rel} not built")
    else:
        with open(os.path.join(built, *rel.split("/")), "rb") as fh:
            raw = fh.read()
        L = M.CM.castle().L
        gt = M.CM.vanilla(rel, L.T.Container(rel, raw))[0]
        vt = M.CM.vanilla(rel)[0]
        for key in vt:
            h, vrows = vt[key]
            _h, grows = gt[key]
            diff = [(i, h[j]) for i, (g, v) in enumerate(zip(grows, vrows)) for j in range(len(h)) if g[j] != v[j]]
            if key != CASTLE_SHEET:
                if diff or len(grows) != len(vrows):
                    bad.append(f"castle {key} changed")
                continue
            j = h.index(CASTLE_COL)
            ok = (len(grows) == len(vrows) and {c for _i, c in diff} <= {CASTLE_COL}
                  and all(int(g[j], 0) == CASTLE_VALUE for g in grows))
            print(f"  read back castle {key}: {CASTLE_COL} = {sorted({int(g[j], 0) for g in grows})} in all "
                  f"{len(grows)} dishes (game {sorted({int(v[j], 0) for v in vrows})}), no other cell changed "
                  f"{'OK' if ok else 'BAD'}")
            if not ok:
                bad.append("castle dish sheet")
    # install / uninstall in a scratch Zakuro folder
    tdir = ctx.title_dir()
    os.makedirs(os.path.join(tdir, "romfs"), exist_ok=True)
    with open(os.path.join(tdir, "owner-note.txt"), "w") as fh:
        fh.write("a file that is not ours\n")
    before = tree_hash(zak)
    for line in M.install(ctx):
        print("  install:", line)
    inst = tree_hash(zak)
    for f in files:
        k = os.path.relpath(os.path.join(tdir, "romfs", *f.split("/")), zak)
        src = os.path.join(built, *f.split("/"))
        with open(src, "rb") as fh:
            if inst.get(k) != hashlib.sha256(fh.read()).hexdigest():
                bad.append(f"installed {f} differs from the build")
    print(f"  installed {len(files)} file(s) into {os.path.relpath(tdir, ROOT)}")
    ok, msgs = M.uninstall(ctx)
    for line in msgs:
        print("  uninstall:", line)
    after = tree_hash(zak)
    same = ok and after == before
    print(f"  uninstall back byte-identical: {'OK' if same else 'BAD'} ({len(before)} file(s) before, "
          f"{len(after)} after)")
    if not same:
        bad.append("uninstall not byte-identical")
    print("CHECK", "PASS" if not bad else "FAIL: " + "; ".join(bad))
    return 0 if not bad else 1


def decode_built(M, table, built):
    """Every row of TABLE decoded from the built file(s) (falling back to the game's file
    for a file the build did not change), with the same columns as M.vanilla()."""
    T = M.T
    t = M.reg()[table]
    cd = M.codec(table)
    rows = []
    any_built = False
    for rel in t.files():
        p = os.path.join(built, *rel.split("/"))
        if os.path.exists(p):
            with open(p, "rb") as fh:
                c = T.Container(rel, fh.read())
            any_built = True
        else:
            c = T.container(rel)
        start, count = T.locate(t, c)
        labels = T.record_labels(t, c, start, count)
        rows += [cd.decode(c, i, start + i * t.size, labels[i]) for i in range(count)]
    return rows if any_built else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=("make", "install", "check"))
    ap.add_argument("--mods-dir"); ap.add_argument("--stage-dir"); ap.add_argument("--zakuro-dir")
    a = ap.parse_args(argv)
    M = load_mods()
    try:
        if a.cmd == "check":
            return check(M)
        ctx = M.Ctx(mods_dir=a.mods_dir, stage_dir=a.stage_dir, zakuro_dir=a.zakuro_dir)
        if a.cmd == "make" or not os.path.isdir(os.path.join(ctx.mods_dir, MOD_NAME)):
            for line in make(M, ctx):
                print("made:", line)
        if a.cmd == "install":
            fwd = ["install"] + sum(([f"--{k.replace('_', '-')}", v] for k, v in
                                     (("mods_dir", a.mods_dir), ("stage_dir", a.stage_dir),
                                      ("zakuro_dir", a.zakuro_dir)) if v), [])
            return M.main(_global_first(fwd))
    except M.ModError as e:
        print(f"ERROR: {e}")
        return 1
    return 0


def _global_first(argv: list[str]) -> list[str]:
    """mods.py takes its --mods-dir/--stage-dir/--zakuro-dir before the command."""
    return argv[1:] + argv[:1]


if __name__ == "__main__":
    sys.exit(main())
