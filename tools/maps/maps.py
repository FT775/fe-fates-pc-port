#!/usr/bin/env python3
"""Map editing: unit placement and terrain of every chapter as spreadsheets, and back.

Standard library only. Reads your own extracted/romfs/ (python tools/assets/romfs.py) and
writes under build/maps/ (gitignored: map packages hold game values). docs/MAPS.md is the
guide; the code facts behind every rule are there.

    python tools/maps/maps.py list                  every map: units, groups, terrain
    python tools/maps/maps.py export A007           build/maps/A007/: units.csv,
                                                    terrain.csv, tiles.csv, map.csv,
                                                    preview.png, about.txt
    python tools/maps/maps.py export --all          every map (about a minute)
    python tools/maps/maps.py check A007            check your edits, change nothing
    python tools/maps/maps.py build A007            check, then write the rebuilt
                                                    file(s) under build/maps/rebuilt/
                                                    with their RomFS paths
    python tools/maps/maps.py build --all --check   every package; say which files differ
                                                    from the game (unedited = identical)
    python tools/maps/maps.py roundtrip             all 185 Dispos + 109 Terrain files
                                                    through the spreadsheet form in
                                                    memory: every one must come back
                                                    byte-identical

Options:
    --src DIR      where the packages are (default build/maps)
    --out DIR      export: where to write packages; build: where the rebuilt files go
                   (default build/maps/rebuilt)
    --tables DIR   a folder with Item.csv / Job.csv / Skill.csv (for example a mod's
                   tables/ folder): IDs added or changed there count as existing
    --lenient      a moved unit on a tile its class cannot walk on (a door or wall a map
                   event opens) is a warning instead of an error
    --force        export over a package that already exists (your edits there are lost)
    --no-png       export without preview.png
    -v             print every note (game rows the checks would flag, left as they are)

Exit code 0 = done / all checks pass, 1 = refused or an error (the message says which
file, line and column).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import maplib as M  # noqa: E402


def _names(a, pk) -> list[str]:
    if a.all:
        return list(pk)
    if not a.names:
        raise M.MapError("name a map (python tools/maps/maps.py list) or use --all")
    bad = [n for n in a.names if n not in pk]
    if bad:
        raise M.MapError(f"no map called {', '.join(bad)} (python tools/maps/maps.py list)")
    return a.names


def cmd_list(a) -> int:
    pk = M.packages()
    print(f"{'map':10} {'units':>5} {'groups':>6}  terrain        dispos file")
    for n, p in pk.items():
        units = groups = ""
        if p["dispos"]:
            d = M.Dispos(p["dispos"])
            units, groups = str(len(d.urows)), str(len(d.groups))
        terr = M.stem(p["terrain"]) if p["terrain"] else (
            f"({M.stem(p['terrain_ref'])})" if p["terrain_ref"] else "-")
        print(f"{n:10} {units:>5} {groups:>6}  {terr:14} {p['dispos'] or '-'}")
    nd = sum(1 for p in pk.values() if p["dispos"])
    nt = sum(1 for p in pk.values() if p["terrain"])
    print(f"{len(pk)} maps: {nd} unit placement files, {nt} terrain files "
          "(a name in brackets = the terrain is edited in that map's package)")
    return 0


def cmd_export(a) -> int:
    pk = M.packages()
    names = _names(a, pk)
    out = a.out or M.OUTDIR
    world = M.World()
    if not a.force:
        mine = [n for n in names if any(os.path.isfile(os.path.join(out, n, f))
                                        for f in ("units.csv", "terrain.csv", "tiles.csv"))]
        if mine:
            raise M.MapError(f"{os.path.join(out, mine[0])} already exists ({len(mine)} package(s)); exporting again "
                             "would overwrite your edits there. Use --force to start over")
    for n in names:
        d = M.export(n, out, world, png=not a.no_png)
        if len(names) <= 5:
            print(f"{n}: wrote {os.path.relpath(d, M.ROOT)}")
    print(f"exported {len(names)} map package(s) under {os.path.relpath(out, M.ROOT)}")
    return 0


def _report(name: str, rep: M.Report, verbose: bool) -> None:
    for e in rep.errors:
        print(f"ERROR   {e}")
    for w in rep.warnings:
        print(f"warning {w}")
    if rep.notes:
        if verbose:
            for n in rep.notes:
                print(f"note    {n}")
        else:
            print(f"note    {name}: {len(rep.notes)} game row(s) that the checks would flag were left as they "
                  "are (-v lists them)")


def _run(a, write: bool) -> int:
    pk = M.packages()
    src = a.src or M.OUTDIR
    names = _names(a, pk)
    if a.all:
        names = [n for n in names if os.path.isdir(os.path.join(src, n))]
        if not names:
            raise M.MapError(f"no packages under {src}: run  python tools/maps/maps.py export --all  first")
    world = M.World(a.tables)
    if world.extra_note:
        print(f"note    {world.extra_note}")
    failed = same = changed = 0
    for n in names:
        files, rep = M.build_package(n, src, world, lenient=a.lenient)
        _report(n, rep, a.verbose)
        if not rep.ok():
            failed += 1
            print(f"{n}: REFUSED ({len(rep.errors)} error(s)); nothing written")
            continue
        for rel, data in files.items():
            orig = M.T.container(rel).raw
            if data == orig:
                same += 1
                status = "identical to the game's file"
            else:
                changed += 1
                status = "changed"
            if write:
                dst = M.write_rebuilt({rel: data}, a.out or M.REBUILT)[0]
                if len(names) <= 5 or data != orig:
                    print(f"{n}: {rel} {status} -> {os.path.relpath(dst, M.ROOT)}")
            elif len(names) <= 5 or data != orig:
                print(f"{n}: {rel} checks pass ({status})")
    verb = "rebuilt" if write else "checked"
    print(f"{verb} {len(names) - failed}/{len(names)} package(s): {same} file(s) identical to the game's, "
          f"{changed} changed, {failed} refused")
    if a.check and changed and write:
        print("(--check: files that differ are the ones you edited)")
    return 1 if failed else 0


def cmd_roundtrip(a) -> int:
    ds, dn, ts, tn, bad = M.roundtrip_all()
    print(f"Dispos: {ds}/{dn} byte-identical; Terrain: {ts}/{tn} byte-identical "
          "(decoded to the spreadsheet form, read back and rebuilt in memory)")
    for b in bad[:10]:
        print(f"DIFFERENT: {b}")
    return 0 if not bad else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["list", "export", "check", "build", "roundtrip"])
    ap.add_argument("names", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--src")
    ap.add_argument("--out")
    ap.add_argument("--tables")
    ap.add_argument("--lenient", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    if not os.path.isdir(M.T.ROMFS):
        print(f"error: {M.T.ROMFS} is missing: run  python tools/assets/romfs.py  first")
        return 1
    try:
        if a.command == "list":
            return cmd_list(a)
        if a.command == "export":
            return cmd_export(a)
        if a.command == "check":
            return _run(a, write=False)
        if a.command == "build":
            return _run(a, write=True)
        return cmd_roundtrip(a)
    except M.MapError as e:
        print(f"error: {e}")
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
