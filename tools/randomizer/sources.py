#!/usr/bin/env python3
"""Which game's tables the randomizer reads (F-047): Fire Emblem Fates, or the optional fan mod Seal of Flames by
Laz14 (gamebanana.com/mods/656034, CC BY-NC-ND 4.0), which shares Fates' title id.

    fates  the user's own extracted RomFS (extracted/romfs/), exactly as before: activate("fates") changes nothing.
    seal   the same RomFS with the mod's files laid over it, the way the game sees it when Seal of Flames is played
           from its own profile (play/seal-of-flames/data/mods/0004000000179800/romfs/).

The layered view is a folder build/sources/seal/romfs-<stamp>-<n>/ (gitignored, on the owner's machine only): the parts of
the base RomFS the randomizer reads (GameData, Scripts, m, map/config, talk, sound) copied, then the mod's own files
copied over them, plus the mod-only folders (exalt). The large sound streams are hard links to the base files
(read-only use; nothing in tools/randomizer or tools/tables writes into a RomFS folder), else copies. A stamp
(paths, sizes and times of every source file) picks the folder; a new one is built only when no finished folder has
that stamp, and a finished folder is never changed in place (round 73b: readers are safe while another run builds).

activate(game) points the table tools at that game's RomFS (tools/tables tablelib.ROMFS, tools/mods mods.ROMFS and
every cache reset) and makes randolib.load_rules() return that game's rules (config/randomizer/rules.json for fates,
config/seal/seal_rules.json for seal). Every module reads its tables through gamedata / tablelib and its rules
through randolib.load_rules(), so after activate() every module plans on that game's own tables and rules without a
change of its own.

    python tools/randomizer/sources.py status [--game seal] [--seal-romfs DIR]
    python tools/randomizer/sources.py layer  [--seal-romfs DIR] [--force]
    python tools/randomizer/sources.py rules  [--seal-romfs DIR]     rebuild config/seal/seal_rules.json
                                     (round 84: forwards to tools/seal/seal_rules.py, the Seal edition's builder)

The mod's licence holds: its files and anything made from them stay on the owner's machine (build/ or the Seal
profile), are never committed or shared, and are never sent to anyone.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

GAMES = ("fates", "seal")
TITLE_HEX = "0004000000179800"
BASE_ROMFS = os.path.join(ROOT, "extracted", "romfs")
SEAL_PROFILE = os.path.join(ROOT, "play", "seal-of-flames")
LAYER_TOP = os.path.join(ROOT, "build", "sources")
RULES = {"fates": os.path.join(ROOT, "config", "randomizer", "rules.json"),
         "seal": os.path.join(ROOT, "config", "seal", "seal_rules.json")}   # round 83: the Seal edition's data
CREDIT = {"fates": "Fire Emblem Fates",
          "seal": "Seal of Flames by Laz14 (gamebanana.com/mods/656034), CC BY-NC-ND 4.0"}
# base RomFS parts the randomizer and the table tools read (copied); sound/stream is linked (large)
COPY_PARTS = ("GameData", "Scripts", "m", "map/config", "talk", "sound/IRON15_sound.bcsar")
LINK_PARTS = ("sound/stream",)
# mod parts with no base counterpart that are still worth having in the view (event scripts of the new format)
MOD_ONLY_PARTS = ("exalt",)
LAYER_FORMAT = 1


class SourceError(Exception):
    """A problem the user can fix (missing mod, unknown game); printed without a traceback."""


# ------------------------------------------------------------------ where things are
def seal_romfs(path: str | None = None) -> str:
    """The Seal of Flames mod's romfs folder: the argument, else FEF_SEAL_ROMFS, else the profile's
    data/mods/<title>/romfs (either case of the title id)."""
    if path:
        return os.path.abspath(path)
    env = os.environ.get("FEF_SEAL_ROMFS")
    if env:
        return os.path.abspath(env)
    mods = os.path.join(SEAL_PROFILE, "data", "mods")
    for t in (TITLE_HEX, TITLE_HEX.lower()):
        p = os.path.join(mods, t, "romfs")
        if os.path.isdir(p):
            return p
    return os.path.join(mods, TITLE_HEX, "romfs")


def check_game(game: str) -> str:
    g = (game or "fates").strip().lower()
    g = {"sof": "seal", "seal-of-flames": "seal", "seal of flames": "seal", "fe14": "fates"}.get(g, g)
    if g not in GAMES:
        raise SourceError(f"unknown game {game!r} (fates or seal)")
    return g


def _walk(top: str):
    """(relative path with /, absolute path, size, mtime_ns) of every file under top, sorted."""
    out = []
    if os.path.isfile(top):
        st = os.stat(top)
        return [("", top, st.st_size, st.st_mtime_ns)]
    for dp, dn, fs in os.walk(top):
        dn.sort()
        for f in sorted(fs):
            p = os.path.join(dp, f)
            st = os.stat(p)
            out.append((os.path.relpath(p, top).replace(os.sep, "/"), p, st.st_size, st.st_mtime_ns))
    return out


def _plan(mod: str) -> list[tuple[str, str, str]]:
    """[(layer rel, source path, 'copy'|'link')]: base parts first, the mod's files replacing them."""
    files: dict[str, tuple[str, str]] = {}
    for part in COPY_PARTS + LINK_PARTS:
        how = "link" if part in LINK_PARTS else "copy"
        src = os.path.join(BASE_ROMFS, *part.split("/"))
        for rel, p, _s, _m in _walk(src) if os.path.exists(src) else []:
            files[(part + "/" + rel) if rel else part] = (p, how)
    for part in COPY_PARTS + LINK_PARTS + MOD_ONLY_PARTS:
        src = os.path.join(mod, *part.split("/"))
        for rel, p, _s, _m in _walk(src) if os.path.exists(src) else []:
            files[(part + "/" + rel) if rel else part] = (p, "copy")     # the mod's own files are always copies
    return [(k, v[0], v[1]) for k, v in sorted(files.items())]


def _stamp(plan: list[tuple[str, str, str]]) -> str:
    h = hashlib.sha256(f"layer {LAYER_FORMAT}\n".encode())
    for rel, p, how in plan:
        st = os.stat(p)
        h.update(f"{rel}\t{how}\t{os.path.normcase(p)}\t{st.st_size}\t{st.st_mtime_ns}\n".encode("utf-8", "replace"))
    return h.hexdigest()


def layer_dir(game: str = "seal") -> str:
    """The folder that holds the game's layered views (build/sources/seal): one romfs-<stamp>-<n> folder per build."""
    return os.path.join(LAYER_TOP, check_game(game))


# Round 73b: a layer folder is never changed or removed in place once it is made. Round 73's first smoke try read
# the shared build/sources/seal/romfs while the core tests rebuilt it (5 Seal mismatches): the smoke lays from its
# own copy of the mod (build/fixtures/smoke/sealmod) and the core tests from the profile's mod, so each saw the
# other's stamp as stale and wiped the one folder the other was reading. Now every build goes to a temporary folder
# and is renamed (atomic on Windows too) to a new, never-reused name romfs-<stamp16>-<n>; its marker
# romfs-<stamp16>-<n>.json is written last. A reader takes the newest finished folder whose marker holds its own
# stamp, so two mod sources live side by side and a rebuild never touches a folder someone is reading. Old folders
# are removed only by a builder (under the lock) once their marker has not been used for PRUNE_S seconds; a reader
# marks use by touching the marker and keeps it open while it runs (on Windows an open file cannot be renamed), and
# the pruner moves the marker aside before it looks at its time, so a folder in use is kept instead of removed.
PRUNE_S = 12 * 3600


def _find_layer(top: str, stamp: str) -> str | None:
    """The newest finished layer folder under top made for this stamp, marked as used now; None if there is none."""
    pre = f"romfs-{stamp[:16]}-"
    try:
        names = sorted((n for n in os.listdir(top) if n.startswith(pre) and n.endswith(".json")),
                       key=lambda n: int(n[len(pre):-5], 16) if re.fullmatch(r"[0-9a-f]+", n[len(pre):-5]) else -1,
                       reverse=True)
    except OSError:
        return None
    for n in names:
        marker = os.path.join(top, n)
        out = marker[:-5]
        try:
            with open(marker, encoding="utf-8") as fh:
                if json.load(fh).get("stamp") != stamp:
                    continue
        except (OSError, ValueError):
            continue
        if not os.path.isdir(out):
            continue
        try:
            os.utime(marker)        # in use: the commit point a pruner checks (it fails if the marker was moved aside)
        except OSError:
            continue
        _hold(marker)
        return out
    return None


_HELD: dict = {}


def _hold(marker: str) -> None:
    """Keeps the marker open for the rest of this process: on Windows an open file cannot be renamed, so a pruner in
    another process cannot move it aside and the folder stays while this process may still read it."""
    if marker not in _HELD:
        try:
            _HELD[marker] = open(marker, "rb")  # noqa: SIM115  (held on purpose until the process ends)
        except OSError:
            return
        if len(_HELD) == 1:
            import atexit
            atexit.register(lambda: [fh.close() for fh in _HELD.values()])


def build_layer(mod: str | None = None, force: bool = False, quiet: bool = True) -> str:
    """The Seal of Flames view of the RomFS (build/sources/seal/romfs-<stamp>-<n>), found or made. Returns its path;
    the folder never changes while it exists."""
    mod = seal_romfs(mod)
    if not os.path.isdir(os.path.join(mod, "GameData")):
        raise SourceError(f"Seal of Flames is not installed: {mod} has no GameData folder "
                          "(install it from the Choose your game page or tools/seal/sof.py install)")
    if not os.path.isdir(os.path.join(BASE_ROMFS, "GameData")):
        raise SourceError("no extracted/romfs/ (python tools/assets/romfs.py; it reads the .cci in roms/)")
    plan = _plan(mod)
    stamp = _stamp(plan)
    top = layer_dir("seal")
    if not force:
        got = _find_layer(top, stamp)
        if got:
            return got
    # Several test lanes may ask for the layer at once (release core, 2026-11-24: two lanes rebuilt it into the
    # same .tmp folder and left it half-written under a current stamp). One builder at a time, each in its own
    # temporary folder; a waiter re-checks once it holds the lock.
    with _layer_lock(top):
        if not force:
            got = _find_layer(top, stamp)
            if got:
                return got
        _prune_layers(top)
        return _build_layer_locked(plan, stamp, mod, top, quiet)


def _prune_layers(top: str, max_idle_s: float | None = None) -> list[str]:
    """Removes layer folders not used for max_idle_s (default PRUNE_S), leftover temporary folders of that age, and
    the round-73 single folder (romfs + layer.json). Call only while holding the lock. Returns what it removed."""
    import time
    idle = PRUNE_S if max_idle_s is None else max_idle_s
    now = time.time()
    gone = []
    try:
        names = os.listdir(top)
    except OSError:
        return gone
    for n in names:
        p = os.path.join(top, n)
        if (".tmp-" in n or ".drop-" in n) and os.path.isdir(p):
            try:
                old = ".drop-" in n or now - os.path.getmtime(p) > idle
            except OSError:
                continue
            if old:
                shutil.rmtree(p, ignore_errors=True)
                gone.append(n)
            continue
        if (".drop-" in n or n.endswith(".json.part")) and os.path.isfile(p):   # left by a killed run
            marker = os.path.join(top, n.split(".drop-")[0])
            if (".drop-" in n and n.startswith("romfs-") and marker.endswith(".json") and not os.path.exists(marker)
                    and os.path.isdir(marker[:-5])):
                try:                         # a pruner killed between marker and folder: put the marker back, so
                    os.replace(p, marker)    # the folder is pruned by the normal rule below (round 73b review)
                except OSError:
                    pass
                continue
            try:
                if now - os.path.getmtime(p) > idle:
                    os.remove(p)
            except OSError:
                pass
            continue
        if n.startswith("romfs-") and "." not in n and os.path.isdir(p):
            # a finished folder with no marker in any form (a builder killed before its marker): no reader can take
            # it, and builders hold the lock as we do, so it is removed once it is past the idle time
            if (os.path.exists(p + ".json") or os.path.exists(p + ".json.part")
                    or glob.glob(glob.escape(p) + ".json.drop-*")):
                continue
            try:
                if now - os.path.getmtime(p) <= idle:
                    continue
                dropped = f"{p}.drop-{os.getpid()}"
                os.replace(p, dropped)       # fails on Windows while a file in it is open: then keep it
            except OSError:
                continue
            shutil.rmtree(dropped, ignore_errors=True)
            gone.append(n)
            continue
        if not (n.endswith(".json") and n.startswith("romfs-")) and n != "layer.json":
            continue
        folder = os.path.join(top, "romfs") if n == "layer.json" else p[:-5]
        aside = f"{p}.drop-{os.getpid()}"
        try:
            os.replace(p, aside)             # readers can no longer take it (their touch fails)
        except OSError:
            continue
        try:
            fresh = now - os.path.getmtime(aside) <= idle
        except OSError:
            fresh = True
        if fresh:                            # a reader touched it just before it was moved aside: keep it
            try:
                os.replace(aside, p)
            except OSError:
                pass
            continue
        dropped = f"{folder}.drop-{os.getpid()}"
        try:
            if os.path.isdir(folder):
                os.replace(folder, dropped)  # fails on Windows while a file in it is open: then keep it
        except OSError:
            try:
                os.replace(aside, p)
            except OSError:
                pass
            continue
        shutil.rmtree(dropped, ignore_errors=True)
        try:
            os.remove(aside)
        except OSError:
            pass
        gone.append(os.path.basename(folder))
    return gone


class _layer_lock:
    """An exclusive lock file next to the layer (O_EXCL). Waits up to 20 min; a lock older than 30 min is
    taken as left over from a killed run and removed."""

    def __init__(self, top: str, wait_s: float = 1200.0, stale_s: float = 1800.0):
        self.path = os.path.join(top, "layer.lock")
        self.wait_s, self.stale_s = wait_s, stale_s

    def __enter__(self):
        import time
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        t0 = time.monotonic()
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{os.getpid()}\n".encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.path) > self.stale_s:
                        os.remove(self.path)
                        continue
                except OSError:
                    continue
                if time.monotonic() - t0 > self.wait_s:
                    raise SourceError(f"another run is still building the Seal of Flames layer ({self.path}); "
                                      "wait for it, or delete that file if no run is going")
                time.sleep(0.5)

    def __exit__(self, *exc):
        try:
            os.remove(self.path)
        except OSError:
            pass
        return False


def _build_layer_locked(plan, stamp: str, mod: str, top: str, quiet: bool) -> str:
    import time
    tmp = os.path.join(top, f"romfs.tmp-{os.getpid()}")
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    links = copies = 0
    for rel, src, how in plan:
        dst = os.path.join(tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if how == "link":
            try:
                os.link(src, dst)
                links += 1
                continue
            except OSError:
                pass
        shutil.copyfile(src, dst)
        copies += 1
    out = os.path.join(top, f"romfs-{stamp[:16]}-{time.time_ns():x}")
    os.replace(tmp, out)                     # a new name: nothing anyone is reading is touched
    marker = f"{out}.json"
    with open(f"{marker}.part", "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"stamp": stamp, "mod": mod, "base": BASE_ROMFS, "files": len(plan), "links": links,
                   "copies": copies, "credit": CREDIT["seal"],
                   "note": "made by tools/randomizer/sources.py; the mod's files: never commit or share"}, fh, indent=1)
        fh.write("\n")
    os.replace(f"{marker}.part", marker)     # finished: readers may take it from now on
    _hold(marker)
    if not quiet:
        print(f"layered {len(plan)} files into {out} ({copies} copied, {links} linked)")
    return out


# ------------------------------------------------------------------ switching the tools over
_STATE: dict = {"game": "fates", "romfs": BASE_ROMFS, "orig_load_rules": None}


def _tools():
    import gamedata as GD  # noqa: F401  (puts tools/mods and tools/tables on the path)
    import mods as M
    import randolib as R
    return M, M.T, R


def romfs_of(game: str, mod: str | None = None) -> str:
    return BASE_ROMFS if check_game(game) == "fates" else build_layer(mod)


def activate(game: str = "fates", mod: str | None = None) -> str:
    """Points every table read and randolib.load_rules() at this game. Returns the RomFS folder in use.
    activate("fates") is the original state (extracted/romfs, rules.json)."""
    game = check_game(game)
    if game == "seal" and not os.path.isfile(RULES["seal"]):   # round 84: the Vanilla+ edition has no config/seal
        raise SourceError(f"{SEAL_EDITION_MISSING} ({os.path.relpath(RULES['seal'], ROOT)} is missing)")
    romfs = romfs_of(game, mod)
    M, T, R = _tools()
    if T is None:
        raise SourceError(M.tables_status() or "tools/tables could not be loaded")
    T.ROMFS = romfs
    M.ROMFS = romfs
    M.reset_tables()
    if _STATE["orig_load_rules"] is None:
        _STATE["orig_load_rules"] = R.load_rules
    orig = _STATE["orig_load_rules"]
    if game == "fates":
        R.load_rules = orig
    else:
        R.load_rules = lambda p=None, g=game: orig(p) if p else load_rules(g)   # noqa: E731  (a path still wins)
    _STATE.update(game=game, romfs=romfs)
    return romfs


def current() -> str:
    return _STATE["game"]


def rules_path(game: str | None = None) -> str:
    return RULES[check_game(game or _STATE["game"])]


def tables(game: str = "fates", mod: str | None = None, names: bool = True):
    """The randolib.Facts of this game (activates it first)."""
    activate(game, mod)
    import gamedata as GD
    return GD.load_facts(names=names)


# ------------------------------------------------------------------ chapters (route rules are built from these)
def chapters(game: str | None = None) -> list[dict]:
    """Chapter rows (CID_, route, prep...) of the active (or given) game, through the table layouts."""
    if game:
        activate(game)
    import gamedata as GD
    return GD._load("Chapter")


def dispos_files(romfs: str | None = None) -> list[str]:
    """Every chapter placement file (GameData/Dispos/**) in the active RomFS view, relative, sorted."""
    top = os.path.join(romfs or _STATE["romfs"], "GameData", "Dispos")
    out = []
    for dp, _dn, fs in os.walk(top):
        for f in fs:
            if f.endswith(".bin.lz"):
                out.append(os.path.relpath(os.path.join(dp, f), romfs or _STATE["romfs"]).replace(os.sep, "/"))
    return sorted(out)


# ------------------------------------------------------------------ Seal of Flames rules: moved to tools/seal (round 84)
# The Seal rules builder (reachable_chapters, the Seal route and boss consts, chapter_door_events, seal_rolls,
# seal_guarantees, seal_boss_classes, build_seal_rules, write_seal_rules) lives in tools/seal/seal_rules.py, the Seal
# of Flames edition's own folder (F-070 split round B). For one round these thin names still answer here
# (sources.build_seal_rules, sources.seal_guarantees ...) by forwarding there; `sources.py rules` forwards too.
# Nothing in a make uses them: the make reads the finished config/seal/seal_rules.json through load_rules().
SEAL_RULES_TOOL = os.path.join(ROOT, "tools", "seal", "seal_rules.py")
SEAL_EDITION_MISSING = "The Seal of Flames edition is not installed."
_SEAL_RULES_NAMES = frozenset((
    "reachable_chapters", "SEAL_ROUTE", "SEAL_ROUTE_NAME", "SEAL_BOSSES", "GUARANTEES_FORMAT", "RETAINER_SLOT",
    "DOOR_KINDS", "SCENE_ONLY_FLAGS", "chapter_door_events", "seal_rolls", "_slot_roll", "seal_guarantees",
    "seal_boss_classes", "build_seal_rules", "write_seal_rules"))


def seal_rules_module():
    """tools/seal/seal_rules.py (the Seal of Flames edition only); SourceError when the edition is not here."""
    if not os.path.isfile(SEAL_RULES_TOOL):
        raise SourceError(f"{SEAL_EDITION_MISSING} ({os.path.relpath(SEAL_RULES_TOOL, ROOT)} is missing)")
    if __name__ == "__main__":      # `python sources.py rules`: let tools/seal see this very module as `sources`
        sys.modules.setdefault("sources", sys.modules[__name__])
    d = os.path.dirname(SEAL_RULES_TOOL)
    if d not in sys.path:
        sys.path.insert(0, d)
    import seal_rules
    return seal_rules


def __getattr__(name: str):
    """The old names of the Seal rules builder, forwarded to tools/seal/seal_rules.py for one round (round 84)."""
    if name in _SEAL_RULES_NAMES:
        try:
            return getattr(seal_rules_module(), name)
        except SourceError as e:
            raise AttributeError(f"sources.{name}: {e}") from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


MERGED_BLOCKS = ("scope", "recruit", "tracks")


def merge_rules(base: dict, over: dict) -> dict:
    """rules.json with a game's rules file laid over it: top-level keys replaced, except the blocks in MERGED_BLOCKS,
    whose keys are replaced one by one (so rules.json's other keys there, such as scope.job_pairs, still hold)."""
    out = json.loads(json.dumps(base))
    for k, v in over.items():
        if k in MERGED_BLOCKS and isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = dict(out[k], **v)
        else:
            out[k] = v
    return out


def load_rules(game: str = "fates") -> dict:
    """The rules a game plans with: rules.json for fates; rules.json with seal_rules.json laid over it for seal."""
    with open(RULES["fates"], encoding="utf-8") as fh:
        base = json.load(fh)
    game = check_game(game)
    if game == "fates":
        return base
    with open(RULES[game], encoding="utf-8") as fh:
        return merge_rules(base, json.load(fh))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("--game", default="seal")
    s.add_argument("--seal-romfs")
    s = sub.add_parser("layer")
    s.add_argument("--seal-romfs")
    s.add_argument("--force", action="store_true")
    s = sub.add_parser("rules", help="rebuild config/seal/seal_rules.json from the mod's tables "
                                     "(forwards to tools/seal/seal_rules.py, the Seal of Flames edition)")
    s.add_argument("--seal-romfs")
    a = p.parse_args(argv)
    try:
        if a.cmd == "rules":   # round 84: the builder is the Seal edition's (tools/seal/seal_rules.py)
            return seal_rules_module().main(["--seal-romfs", a.seal_romfs] if a.seal_romfs else [])
        if a.cmd == "layer":
            build_layer(a.seal_romfs, force=a.force, quiet=False)
            return 0
        romfs = activate(a.game, a.seal_romfs)
        rows = chapters()
        print(f"game {a.game} ({CREDIT[check_game(a.game)]}): RomFS {romfs}")
        print(f"  {len(rows)} Chapter rows, {len(dispos_files())} placement files, rules {rules_path()}")
        return 0
    except SourceError as e:
        print(f"sources: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
