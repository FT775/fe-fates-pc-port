#!/usr/bin/env python3
"""The robot's options track (docs/OPTIONS_WIRING.md section 7; F-032, F-034): routes that run with a PC options file
and the options writers armed, in the robot's OWN test game only, scored apart like the cheat track (F-019).
Standard library only.

A route of this track is named opt-* and carries "options": {...} in config/harness/routes.json, the page's own
lines (tools/zakuro-options patch 0002):

    "options": {"danger_zone": 1, "anim_speed": 3}      danger_zone, hp_bars, animation_skip 0..2; anim_speed 0..3
    "options": {}                                       armed, no line set (OPTIONS_WIRING T1: no options file)

The opt-* routes WITHOUT "options" (opt-ch8-set, opt-ch8-reload: the game's own options screen) stay real play.

Rules (headless.load_routes runs check_routes; headless.run / pack_save / parallel.py and the reports apply the rest):
  1. a route with "options" is named opt-*, is not a cheat route, and its options are the page's keys and ranges;
  2. a save made by an options run carries the options mark (OPTIONS_MARK, written by headless.pack_save, never laid
     out for the game) and is named opts-*, and only such a save is;
  3. an options save never starts a route without "options" (real play or cheat): the name opts-*, the mark, or the
     same save files as a marked save in build/harness/saves/ (save_is_options), whatever names it;
  4. options runs are kept out of the real-play totals (harness.py report, parallel.py's tables, recapture);
  5. until the OK A test library exists (built in its own tree below build/oka/, never build/harness/lib),
     headless.run refuses every options route: the shared capture library has every writer OFF, so such a run
     would prove nothing and could be mistaken for one.

    python tools/harness/options_track.py --selftest   invented routes and save zips (below build/), no game
    python tools/harness/options_track.py --check      the options routes of config/harness/routes.json
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OPTIONS_MARK = "harness-options.json"
SAVE_PREFIX = "opts-"
ROUTE_PREFIX = "opt-"
PAGE = {"danger_zone": 2, "hp_bars": 2, "animation_skip": 2, "anim_speed": 3}  # key -> last value (patch 0002)
REFUSE_RUN = ("the options track needs the OK A test library (docs/OPTIONS_WIRING.md section 10 item 1: W1, W2 and "
              "config_write_options armed in a tree below build/oka/); the shared capture library has every writer "
              "OFF, so this route is not run here")


def is_options(route: dict) -> bool:
    return "options" in route


def check_routes(routes: dict) -> list[str]:
    bad = []
    for name, r in routes.items():
        if not is_options(r):
            if str(r.get("save", "")).startswith(SAVE_PREFIX):
                bad.append(f"route {name}: a route without \"options\" may not start from an options save ({r['save']})")
            continue
        if not name.startswith(ROUTE_PREFIX):
            bad.append(f"route {name}: a route with \"options\" is named {ROUTE_PREFIX}*")
        if r.get("cheat") or r.get("pokes"):
            bad.append(f"route {name}: the options track and the cheat track are never mixed")
        opts = r.get("options")
        if not isinstance(opts, dict):
            bad.append(f"route {name}: \"options\" is an object of the page's lines")
            continue
        for k, v in opts.items():
            if k not in PAGE:
                bad.append(f"route {name}: options key {k!r} is not one of {', '.join(PAGE)}")
            elif not isinstance(v, int) or isinstance(v, bool) or not (0 <= v <= PAGE[k]):
                bad.append(f"route {name}: options {k} = {v!r}, want 0 .. {PAGE[k]}")
    return bad


def file_text(route: dict) -> str:
    """The options file an options run gets (the page's own form, every game line written)."""
    opts = route.get("options") or {}
    return "# FE options (robot options track). 0 is off, and off is the original game.\n" + "".join(
        f"{k} = {int(opts.get(k, 0))}\n" for k in PAGE)


def fingerprint(zip_path: str, skip: tuple[str, ...]) -> str:
    h = hashlib.sha256()
    with zipfile.ZipFile(zip_path) as z:
        for n in sorted(i.filename for i in z.infolist() if not i.is_dir() and i.filename not in skip):
            data = z.read(n)
            h.update(n.encode() + b"\0" + str(len(data)).encode() + b"\0" + data)
    return h.hexdigest()


def save_is_options(zip_path: str, folders: list[str], skip: tuple[str, ...] = ()) -> str | None:
    """Why a save carries options-track state (rule 3), or None. skip: other marks left out of the fingerprint."""
    skip = tuple(skip) + (OPTIONS_MARK,)
    if os.path.basename(zip_path).startswith(SAVE_PREFIX):
        return f"named {SAVE_PREFIX}*"
    with zipfile.ZipFile(zip_path) as z:
        if OPTIONS_MARK in z.namelist():
            return f"carries the options mark ({OPTIONS_MARK})"
    fp = None
    for folder in dict.fromkeys(folders):
        for other in sorted(glob.glob(os.path.join(folder, "*.zip"))):
            if os.path.abspath(other) == os.path.abspath(zip_path):
                continue
            try:
                with zipfile.ZipFile(other) as z:
                    marked = OPTIONS_MARK in z.namelist()
                if marked or os.path.basename(other).startswith(SAVE_PREFIX):
                    fp = fp or fingerprint(zip_path, skip)
                    if fingerprint(other, skip) == fp:
                        return f"same save files as the options save {os.path.relpath(other, ROOT)}"
            except (OSError, zipfile.BadZipFile, ValueError):
                continue
    return None


def mark_text(run_json: dict, run: str) -> str:
    return json.dumps({"options_track": True, "run": run, "route": run_json.get("route"),
                       "options": run_json.get("options"), "start_save": run_json.get("save_backup")}, indent=1)


# ------------------------------------------------------------------ self-test
def selftest() -> tuple[list[str], str]:
    errors: list[str] = []
    checks = 0

    def ok(cond: bool, what: str) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            errors.append(f"options_track: {what}")

    sys.path.insert(0, HERE)
    import headless  # noqa: E402
    sys.path.remove(HERE)
    base = {"frames": 100, "save_at": 90, "input": "1:A", "shots": [10], "save": "bt-ch8-clear"}
    good = dict(base, options={"danger_zone": 1, "anim_speed": 3})
    ok(check_routes({"opt-a": good, "opt-b": dict(base, options={}), "opt-ch8-set": dict(base)}) == [],
       "good options routes, an empty options object and a real-play opt-* route pass")
    rules = check_routes({"x-a": good, "opt-c": dict(good, cheat=True), "opt-d": dict(base, options={"danger_zone": 3}),
                          "opt-e": dict(base, options={"hp_bars": True}), "opt-f": dict(base, options={"zoom": 1}),
                          "opt-g": dict(base, options=[1]), "bt-x": dict(base, save="opts-a"),
                          "cheat-x": dict(base, cheat=True, save="opts-a")})
    for frag in ("named opt-*", "never mixed", "danger_zone = 3", "hp_bars = True", "'zoom'", "an object",
                 "route bt-x: a route without", "route cheat-x: a route without"):
        ok(any(frag in r for r in rules), f"the rules name: {frag} ({rules})")
    ok(len(rules) == 8, f"one rule per broken route ({len(rules)})")
    ok(file_text(good).splitlines()[1:] == ["danger_zone = 1", "hp_bars = 0", "animation_skip = 0", "anim_speed = 3"],
       "the options file is the page's form")
    # headless's route loader applies the rules
    build = os.path.join(ROOT, "build", "harness")
    os.makedirs(build, exist_ok=True)
    td = tempfile.mkdtemp(prefix="options_track_selftest_", dir=build)
    try:
        rp = os.path.join(td, "routes.json")
        with open(rp, "w", encoding="utf-8") as fh:
            json.dump({"routes": {"bt-y": dict(base, save="opts-z")}}, fh)
        try:
            headless.load_routes(rp)
            ok(False, "headless.load_routes refuses a real-play route that starts from an options save")
        except headless.Stop as e:
            ok("options save" in str(e), f"headless.load_routes names the rule ({e})")
        # saves: the mark, the name, a copy without the mark, a copy under a new name
        saves = os.path.join(td, "saves")
        os.makedirs(saves)

        def zip_(name, members):
            p = os.path.join(saves, name + ".zip")
            with zipfile.ZipFile(p, "w") as z:
                for n, d in members.items():
                    z.writestr(n, d)
            return p

        real = zip_("bt-real", {f"savedata/{headless.TITLE}/a": b"real"})
        member = f"savedata/{headless.TITLE}/a"
        marked = zip_("opt-run-save", {member: b"set", OPTIONS_MARK: "{}"})
        copy = zip_("bt-copy", {member: b"set"})
        named = zip_("opts-thing", {member: b"named"})
        ok(save_is_options(real, [saves]) is None, "a real-play save is not an options save")
        ok("mark" in (save_is_options(marked, [saves]) or ""), "the mark is found under any name")
        ok("same save files" in (save_is_options(copy, [saves]) or ""), "a copy without the mark is still found")
        ok("named" in (save_is_options(named, [saves]) or ""), "the name opts-* is enough")
        # headless.check_start_save: an options save never starts a real-play (or cheat) route
        real_saves, hl_saves = headless._REPO_SAVES, headless.SAVES
        headless._REPO_SAVES = headless.SAVES = saves
        try:
            for route, zp, want_stop in ((dict(base), copy, True), (dict(base, cheat=True), marked, True),
                                         (good, marked, False), (dict(base), real, False)):
                try:
                    headless.check_start_save("r", route, zp)
                    ok(not want_stop, f"check_start_save lets {os.path.basename(zp)} start {route.get('options')}")
                except headless.Stop as e:
                    ok(want_stop and "options save" in str(e), f"check_start_save on {os.path.basename(zp)}: {e}")
        finally:
            headless._REPO_SAVES, headless.SAVES = real_saves, hl_saves
        # the mark is never laid out for the game
        data = os.path.join(td, "data")
        laid = headless.lay_save(marked, data)
        ok(OPTIONS_MARK not in laid and not os.path.exists(os.path.join(data, "user", OPTIONS_MARK)),
           "the options mark is not laid out")
    finally:
        shutil.rmtree(td, ignore_errors=True)
    # the reports keep options runs apart
    sys.path.insert(0, HERE)
    import harness  # noqa: E402
    sys.path.remove(HERE)
    td2 = tempfile.mkdtemp(prefix="options_track_runs_", dir=build)
    try:
        for name, meta in (("r1", {"route": "bt-ch1"}), ("r2", {"route": "opt-a", "options_run": True}),
                           ("r3", {"route": "bt-ch2", "start_save_options": "named opts-*"})):
            os.makedirs(os.path.join(td2, name))
            with open(os.path.join(td2, name, "run.json"), "w", encoding="utf-8") as fh:
                json.dump(meta, fh)
        names, skipped = harness.default_report_runs(td2)
        ok(names == ["r1"] and skipped == ["r2", "r3"], f"harness report keeps options runs out ({names}, {skipped})")
    finally:
        shutil.rmtree(td2, ignore_errors=True)
    # headless.run refuses an options route while no OK A library exists (rule 5)
    # (boot.exe and the library are pointed at paths that do not exist, so a run that got past the refusal would stop
    # at its setup checks: this self-test never starts a game, even with the refusal planted away)
    real_load, real_boot = headless.load_routes, headless.BOOT
    try:
        headless.load_routes = lambda path=None: {"opt-a": good}
        headless.BOOT = os.path.join(ROOT, "build", "harness", "no-such-boot.exe")
        headless.run("optcheck-selftest", "opt-a", "original", lib=os.path.join(ROOT, "build", "harness", "no-such.dll"))
        ok(False, "headless.run refuses an options route")
    except headless.Stop as e:
        ok("OK A test library" in str(e), f"headless.run's refusal names the reason ({e})")
    finally:
        headless.load_routes, headless.BOOT = real_load, real_boot
    return errors, f"options track self-test: {checks - len(errors)}/{checks} checks passed"


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        errs, line = selftest()
        for e in errs:
            print(f"  FAIL  {e}")
        print(line)
        return 1 if errs else 0
    if argv == ["--check"]:
        sys.path.insert(0, HERE)
        import headless  # noqa: E402
        try:
            routes = headless.load_routes()  # runs check_routes
        except headless.Stop as e:
            print(f"options_track: {e}")
            return 1
        opt = {n: r for n, r in routes.items() if is_options(r)}
        for n, r in opt.items():
            print(f"{n}: from {r.get('save')}, options {r['options']}")
        tainted = []
        for n, r in routes.items():
            zp = os.path.join(headless.SAVES, f"{r['save']}.zip") if r.get("save") and not is_options(r) else None
            if zp and os.path.isfile(zp):
                why = save_is_options(zp, [headless.SAVES], (headless.CHEAT_MARK,))
                if why:
                    tainted.append(f"route {n}: start save {r['save']} is an options save ({why})")
        for t in tainted:
            print(f"options_track: {t}")
        print(f"options_track: {len(opt)} options route(s), rules {'OK' if not tainted else 'BROKEN'}")
        return 1 if tainted else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
