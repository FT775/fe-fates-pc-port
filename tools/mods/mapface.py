"""Map and portrait mods for tools/mods/mods.py: mods/<Name>/maps/<MAP>/ and
mods/<Name>/faces/<character>/. Standard library only.

maps/<MAP>/   a map package as tools/maps/maps.py export writes it (units.csv, and for
              maps that own their terrain terrain.csv / tiles.csv / map.csv; preview.png and
              about.txt are ignored). <MAP> is the map's file name, e.g. A007. The build
              runs tools/maps/maplib.build_package on it: every check of docs/MAPS.md
              (positions, walkable tiles, IDs, the 50-unit army limit, refused additions),
              with the IDs of rows any enabled mod adds in its tables/ folder (Item.csv,
              Job.csv, Skill.csv) counted as existing. The rebuilt Dispos / Terrain file
              keeps the game's LZ format and is read back before it is staged.
faces/<NAME>/ a portrait folder as tools/assets/portrait.py export writes it (portrait.json
              plus one folder of PNGs per file). <NAME> is any name you like. The build
              runs portrait.check_sizes + rebuild_source: only PNGs that differ from the
              game change anything; every rebuilt .arc / .bch is parsed again (each member,
              each texture) before it is staged. A PNG of a different size is refused
              unless mod.json has "allow_face_resize": true, and even then only where
              docs/ASSETS.md section 3.3.2 says it is safe (powers of two from 8 to 1024,
              every expression of one package the same size).

Both give whole RomFS files, staged, installed and uninstalled exactly like the other
mod kinds (same manifest, backups and atomic copies; mods.py does that part).
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MAPS_DIR = "maps"
FACES_DIR = "faces"
MAP_FILES = ("units.csv", "terrain.csv", "tiles.csv", "map.csv")   # what a map package edits

_MAPLIB = None
_MAPLIB_ERR = ""
_PORTRAIT = None
_PORTRAIT_ERR = ""


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def maplib():
    """tools/maps/maplib.py, or None (maplib_status() says why)."""
    global _MAPLIB, _MAPLIB_ERR
    if _MAPLIB is None and not _MAPLIB_ERR:
        try:
            _MAPLIB = _load("fates_mods_maplib", os.path.join(ROOT, "tools", "maps", "maplib.py"))
        except Exception as e:          # a tool being rewritten must not break other mods
            _MAPLIB_ERR = f"{type(e).__name__}: {e}"
    return _MAPLIB


def portrait():
    """tools/assets/portrait.py, or None (portrait_status() says why)."""
    global _PORTRAIT, _PORTRAIT_ERR
    if _PORTRAIT is None and not _PORTRAIT_ERR:
        try:
            sys.path.insert(0, os.path.join(ROOT, "tools", "assets"))
            _PORTRAIT = _load("fates_mods_portrait", os.path.join(ROOT, "tools", "assets", "portrait.py"))
        except Exception as e:
            _PORTRAIT_ERR = f"{type(e).__name__}: {e}"
    return _PORTRAIT


def maplib_status() -> str | None:
    return None if maplib() is not None else f"tools/maps/maplib.py could not be loaded ({_MAPLIB_ERR})"


def portrait_status() -> str | None:
    return None if portrait() is not None else f"tools/assets/portrait.py could not be loaded ({_PORTRAIT_ERR})"


# ------------------------------------------------------------------ folders in a mod
def map_packages(mod_dir: str) -> list[tuple[str, str]]:
    """[(map name, folder)] under maps/: folders that hold at least one editable file."""
    top = os.path.join(mod_dir, MAPS_DIR)
    if not os.path.isdir(top):
        return []
    return [(n, os.path.join(top, n)) for n in sorted(os.listdir(top))
            if os.path.isdir(os.path.join(top, n))
            and any(os.path.isfile(os.path.join(top, n, f)) for f in MAP_FILES)]


def face_packages(mod_dir: str) -> list[tuple[str, str]]:
    """[(name, folder)] under faces/: folders with a portrait.json."""
    top = os.path.join(mod_dir, FACES_DIR)
    if not os.path.isdir(top):
        return []
    return [(n, os.path.join(top, n)) for n in sorted(os.listdir(top))
            if os.path.isfile(os.path.join(top, n, "portrait.json"))]


def files_to_hash(mod_dir: str) -> list[tuple[str, str]]:
    """[(name in the fingerprint, path)] of every file a map or face build reads."""
    out = []
    for name, d in map_packages(mod_dir):
        for f in MAP_FILES:
            p = os.path.join(d, f)
            if os.path.isfile(p):
                out.append((f"maps/{name}/{f}", p))
    for name, d in face_packages(mod_dir):
        for dp, dn, fn in os.walk(d):
            dn.sort()
            for f in sorted(fn):
                if f == "portrait.json" or f == "bch.json" or f.lower().endswith(".png"):
                    p = os.path.join(dp, f)
                    out.append((f"faces/{name}/" + os.path.relpath(p, d).replace(os.sep, "/"), p))
    return out


# ------------------------------------------------------------------ maps
def _same_lz_format(orig: bytes, new: bytes) -> bool:
    lzt = lambda b: b[0] if b and b[0] in (0x10, 0x11, 0x13) else None   # noqa: E731
    return lzt(orig) == lzt(new)


def make_world(mods: list) -> tuple[object, list[str]]:
    """The tables the map checks use, plus every enabled mod's tables/ folder (so items,
    classes and skills a mod adds count as existing). Returns (world, notes)."""
    M = maplib()
    world = M.World()
    notes = []
    for m in mods:
        if not m.enabled:
            continue
        d = os.path.join(m.dir, "tables")
        if os.path.isdir(d):
            world.add_extra(d)
            if world.extra_note:
                notes.append(f"maps: {m.name}: {world.extra_note}")
    return world, notes


def diff_mod_maps(mod, world) -> tuple[dict[str, bytes], list[str], list[str], list[str]]:
    """One mod's maps/ folders. Returns ({RomFS path: rebuilt bytes}, errors, warnings, notes);
    files whose rebuild equals the game's file are left out (a note says so)."""
    out: dict[str, bytes] = {}
    errors, warnings, notes = [], [], []
    pk_all = None
    for name, d in map_packages(mod.dir):
        where = f"{mod.name}/{MAPS_DIR}/{name}"
        why = maplib_status()
        if why:
            errors.append(f"{where}: map mods are not available: {why}")
            continue
        M = maplib()
        if pk_all is None:
            pk_all = M.packages()
        if name not in pk_all:
            errors.append(f"{where}: no map called {name}; the folder name must be a map name "
                          "(python tools/maps/maps.py list)")
            continue
        lenient = bool(mod.meta.get("lenient_maps", False))
        try:
            files, rep = M.build_package(name, os.path.join(mod.dir, MAPS_DIR), world, lenient=lenient)
        except (M.MapError, ValueError, KeyError) as e:
            errors.append(f"{where}: {e}")
            continue
        errors += [f"{mod.name}/{MAPS_DIR}/: {e}" if not e.startswith(name) else f"{mod.name}/{MAPS_DIR}/{e}"
                   for e in rep.errors]
        warnings += [f"{mod.name}/{MAPS_DIR}/{w}" if w.startswith(name) else f"{where}: {w}" for w in rep.warnings]
        if rep.notes:
            notes.append(f"{where}: {len(rep.notes)} game row(s) the checks would flag, left as the game has "
                         f"them (python tools/maps/maps.py check {name} --src {os.path.join(mod.dir, MAPS_DIR)} -v)")
        if rep.errors:
            continue
        for rel, data in files.items():
            orig = M.T.container(rel)
            if data == orig.raw:
                notes.append(f"{where}: {rel} is the same as the game's; not staged")
                continue
            # read back: the same LZ format, and it decodes as a map file again
            if not _same_lz_format(orig.raw, data):
                errors.append(f"{where}: rebuilt {rel} is not in the game's LZ format")
                continue
            try:
                nc = M.T.Container(rel, data)
                if "/Dispos/" in rel:
                    back = M.Dispos(rel, nc)
                    if [g for g, _f, _n in back.groups] != [g for g, _f, _n in M.Dispos(rel).groups]:
                        raise M.MapError("the groups changed")
                else:
                    M.Terrain(rel, nc)
            except Exception as e:      # any failure to read back refuses the file
                errors.append(f"{where}: rebuilt {rel} does not read back ({type(e).__name__}: {e})")
                continue
            out[rel] = data
    return out, errors, warnings, notes


def merge_maps(ctx, mods: list) -> tuple[dict, dict, list, list, list]:
    """Enabled mods' maps/ in order. Returns (merged {RomFS path: (bytes, mod name)},
    per-mod file counts, errors, warnings, notes). The same file from two mods is a
    conflict unless the later mod has "override": true (then its whole file wins)."""
    merged: dict[str, tuple[bytes, str]] = {}
    counts: dict[str, int] = {}
    errors, warnings, notes = [], [], []
    users = [m for m in mods if m.enabled and map_packages(m.dir)]
    if not users:
        return merged, counts, errors, warnings, notes
    why = maplib_status()
    if why:
        return merged, counts, [f"{m.name}: map mods are not available: {why}" for m in users], [], []
    try:
        world, wnotes = make_world(mods)
    except Exception as e:
        return merged, counts, [f"map checks cannot start: {type(e).__name__}: {e}"], [], []
    notes += wnotes
    for m in users:
        files, errs, warns, nts = diff_mod_maps(m, world)
        errors += errs
        warnings += warns
        notes += nts
        counts[m.name] = len(files)
        for rel, data in files.items():
            prev = merged.get(rel)
            if prev is None:
                merged[rel] = (data, m.name)
            elif prev[0] == data:
                notes.append(f"map {rel}: {m.name} and {prev[1]} make the same file")
            elif m.override:
                notes.append(f"map {rel}: {m.name} overrides {prev[1]} (its whole file wins)")
                merged[rel] = (data, m.name)
            else:
                errors.append(f"conflict: map {rel} is edited by both {prev[1]} and {m.name} (put both edits "
                              f"into one mod, or set \"override\": true in {m.name}/mod.json to let the later "
                              "mod's file win)")
    return merged, counts, errors, warnings, notes


# ------------------------------------------------------------------ faces
def _reparse(P, rel: str, data: bytes) -> str | None:
    """None when every BCH in the file parses and has its textures, else the problem."""
    bch, arc = P.bch, P.arc
    try:
        blobs = [m["data"] for m in arc.parse_full(data)[0]] if rel.endswith(".arc") else [data]
        for b in blobs:
            d, _w = bch.unwrap(b)
            bb = bch.Bch(d)
            for t in bb.textures():
                bb.levels(t)
    except Exception as e:
        return f"{type(e).__name__}: {e}"
    return None


def diff_mod_faces(ctx, mod) -> tuple[dict[str, bytes], list[str], list[str], list[str]]:
    """One mod's faces/ folders. Returns ({RomFS path: rebuilt bytes}, errors, warnings,
    notes); only files with a changed PNG are returned."""
    out: dict[str, bytes] = {}
    src_of: dict[str, str] = {}
    errors, warnings, notes = [], [], []
    allow = bool(mod.meta.get("allow_face_resize", False))
    for name, d in face_packages(mod.dir):
        where = f"{mod.name}/{FACES_DIR}/{name}"
        why = portrait_status()
        if why:
            errors.append(f"{where}: face mods are not available: {why}")
            continue
        P = portrait()
        P.ROMFS = ctx.romfs                 # the game files this build compares against
        try:
            with open(os.path.join(d, "portrait.json"), encoding="utf-8") as fh:
                man = json.load(fh)
            resized = P.check_sizes(d, man, allow)
        except (OSError, ValueError) as e:
            msg = str(e)
            if not allow and "--allow-resize" in msg:
                msg = msg.replace("pass --allow-resize", "set \"allow_face_resize\": true in mod.json")
            errors.append(f"{where}: {msg}")
            continue
        for r in resized:
            warnings.append(f"{where}: resized {r}. The 3DS draws a portrait at its pixel size: it will show "
                            "bigger or smaller, not sharper, and the sweat/blush overlays stay where they were")
        for ent in man.get("sources", []):
            try:
                raw, new, changed = P.rebuild_source(d, ent, allow)
            except (P.PortraitError, P.bch.BchError, ValueError, KeyError, OSError) as e:
                msg = str(e)
                if not allow and "--allow-resize" in msg:
                    msg = msg.replace("--allow-resize", "\"allow_face_resize\": true in mod.json")
                errors.append(f"{where}: {msg}")
                continue
            if new == raw:
                continue
            rel = ent["src"]
            if raw[:1] != new[:1] and raw[:1] in (b"\x10", b"\x11", b"\x13"):
                errors.append(f"{where}: rebuilt {rel} is not in the game's LZ format")
                continue
            bad = _reparse(P, rel, new)
            if bad:
                errors.append(f"{where}: rebuilt {rel} does not read back ({bad})")
                continue
            if rel in out and out[rel] != new:
                errors.append(f"{where}: {rel} is also edited, differently, by {src_of[rel]} in this mod "
                              "(keep the edit in one folder)")
                continue
            out[rel] = new
            src_of[rel] = where
            notes.append(f"{where}: {rel}: {len(changed)} picture(s) changed")
    return out, errors, warnings, notes


def merge_faces(ctx, mods: list) -> tuple[dict, dict, list, list, list]:
    """Enabled mods' faces/ in order, with the same conflict rule as maps."""
    merged: dict[str, tuple[bytes, str]] = {}
    counts: dict[str, int] = {}
    errors, warnings, notes = [], [], []
    for m in mods:
        if not m.enabled or not face_packages(m.dir):
            continue
        files, errs, warns, nts = diff_mod_faces(ctx, m)
        errors += errs
        warnings += warns
        notes += nts
        counts[m.name] = len(files)
        for rel, data in files.items():
            prev = merged.get(rel)
            if prev is None:
                merged[rel] = (data, m.name)
            elif prev[0] == data:
                notes.append(f"face {rel}: {m.name} and {prev[1]} make the same file")
            elif m.override:
                notes.append(f"face {rel}: {m.name} overrides {prev[1]} (its whole file wins)")
                merged[rel] = (data, m.name)
            else:
                errors.append(f"conflict: face {rel} is edited by both {prev[1]} and {m.name} (set \"override\": "
                              f"true in {m.name}/mod.json to let the later mod's file win)")
    return merged, counts, errors, warnings, notes


# ------------------------------------------------------------------ demo helpers
def example_map_edit(pkg_dir: str, name: str, world, tries: list[tuple[int, int]] | None = None):
    """Move one enemy of the map's first enemy group (on the map in all three difficulties)
    by two tiles to a free tile the checks accept. Edits pkg_dir/units.csv in place and
    returns (pid, jid, (x, y), (new x, new y)). Candidates are tried in order: the first
    enemy with a move that builds without errors wins (found at run time, by IDs)."""
    M = maplib()
    tries = tries or [(2, 0), (-2, 0), (0, 2), (0, -2), (1, 1), (-1, -1), (1, -1), (-1, 1)]
    path = os.path.join(pkg_dir, "units.csv")
    head, rows = M.read_csv(path)
    h = {c: i for i, c in enumerate(head)}
    root = os.path.dirname(pkg_dir)
    taken = {(r[h["x"]], r[h["y"]]) for r in rows}
    groups = []
    for r in rows:
        if r[h["group"]] not in groups:
            groups.append(r[h["group"]])
    enemy_group = next((g for g in groups if any(r[h["group"]] == g and r[h["side"]] == "enemy" for r in rows)
                        and not g.lower().startswith(("reinforce", "event", "support", "mob"))), None)
    if enemy_group is None:
        raise ValueError(f"{name}: no enemy group to move a unit in")
    for k, r in enumerate(rows):
        if r[h["group"]] != enemy_group or r[h["side"]] != "enemy":
            continue
        if not all(r[h[dn]] == "1" for dn in ("normal", "hard", "lunatic")):
            continue
        if r[h["start_x"]] != r[h["x"]] or r[h["start_y"]] != r[h["y"]]:
            continue
        x, y = int(r[h["x"]]), int(r[h["y"]])
        for dx, dy in tries:
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or (str(nx), str(ny)) in taken:
                continue
            new = [list(x_) for x_ in rows]
            for c, v in (("x", nx), ("start_x", nx), ("y", ny), ("start_y", ny)):
                new[k][h[c]] = str(v)
            M.write_csv(path, head, new)
            try:
                files, rep = M.build_package(name, root, world)
            except M.MapError:
                rep = None
            if rep is not None and rep.ok() and files:
                return r[h["pid"]], r[h["jid"]], (x, y), (nx, ny)
        M.write_csv(path, head, rows)
    M.write_csv(path, head, rows)
    raise ValueError(f"{name}: no enemy of group {enemy_group} could be moved two tiles to a free, walkable tile")


def tint_png(P, path: str) -> tuple[int, int]:
    """Our own procedural recolour of one PNG, in place: every visible pixel shifted
    towards blue (red x0.55, green x0.8, blue + 70). Returns the picture size."""
    w, h, rgba = P.tex3ds.read_png(path)
    px = bytearray(rgba)
    for i in range(0, len(px), 4):
        if px[i + 3]:
            px[i] = px[i] * 55 // 100
            px[i + 1] = px[i + 1] * 80 // 100
            px[i + 2] = min(255, px[i + 2] + 70)
    P.tex3ds.write_png(path, w, h, bytes(px))
    return w, h
