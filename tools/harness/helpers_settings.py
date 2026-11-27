#!/usr/bin/env python3
"""Round 80 (docs/ROUND80_PLAN.md A4): the robot's sandbox settings writer for the Fates Helpers.

The program reads the Helpers rows (Enemy phase normal / 2x / 4x, True hit off / on) from the `[fates_helpers]` table
of Zakuro's settings.toml, which is `<APPDATA>\\zakuro\\settings.toml`. (Round 80 cut 3: the program has no Enemy
phase row and nothing reads `enemy_phase`; the key stays in the table, so this writer still accepts it.) A robot run points APPDATA into its own job
folder below build/ (smoke.py, pagebot.py, parallel.py), so a proof run that needs a helper on writes that table into
its OWN sandbox file with this module before it starts the game. Never the real %APPDATA%, never play\\appdata.

    python tools/harness/helpers_settings.py write <appdata dir below build/> [--enemy-phase normal|2x|4x]
                                                   [--true-hit off|on] [--explicit]
                                                   [--battle-animations game|off|on]
                                                   [--map-speed game|normal|fast|fast_while_a]
                                                   [--enemy-skip game|off|move|all] [--hp-bars game|off|on]
    python tools/harness/helpers_settings.py read <appdata dir>
    python tools/harness/helpers_settings.py selftest

A sandbox with no settings.toml yet gets the program's own first-run picks (settings.rs `Settings::first_run`: Fire
Emblem Fates' top screen 16:9 and its two first-run enhancements), so a run with a written file starts exactly as a
run with no file would, plus the table. An existing sandbox file keeps every other line; only its `[fates_helpers]`
table is replaced. At the defaults (normal, off) no table is written unless --explicit (proof D1: "an explicit
normal / off table"). The program itself writes no table at the defaults (settings.rs, skip_serializing_if).

Round 81 (docs/ROUND81_PLAN.md A3, HOME_DESIGN 2.4 and 6; patch 0039): the four "New Game defaults" rows
(battle_animations, map_speed, enemy_skip, hp_bars). Each takes the program's own words (zakuro-core fates_helpers.rs,
Game's choice = "game" first and default). A row at Game's choice is not written (the program writes none either), so
a file with only round-80 rows stays round 80's two lines; --explicit writes all six keys, the four rows as "game"
(proof P1's "explicit all-game table"). Reading is per key, as the program reads since patch 0039 (`lenient`): a word
the program does not know gives that key's default and keeps every other key. A word this writer does not know is
refused (nothing is written).

Python 3.11+ standard library only (tomllib reads the file back).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BUILD = os.path.join(ROOT, "build")
STOP = os.path.join(BUILD, "STOP_ROUND")

PHASES = ("normal", "2x", "4x")                       # zakuro-core fates_helpers.rs EnemyPhase (serde names)
# round 81: the New Game rows, in the block's order (+0x8, +0xC, +0xD, +0x16); Game's choice ("game") first and default
NEW_GAME_ROWS = {
    "battle_animations": ("game", "off", "on"),
    "map_speed": ("game", "normal", "fast", "fast_while_a"),
    "enemy_skip": ("game", "off", "move", "all"),
    "hp_bars": ("game", "off", "on"),
}
NEW_GAME_DEFAULTS = {k: "game" for k in NEW_GAME_ROWS}
TITLE_HEX = "0004000000179800"                         # settings.rs FATES_SE_USA, game_key
# settings.rs FATES_FIRST_RUN_ENHANCEMENTS and Settings::first_run (top_shape Wide16x9, snake_case "wide16x9")
FIRST_RUN_ENHANCEMENTS = ("60 fps battles (Fates port extra)", "16:9 top screen (Fates port extra)")
FIRST_RUN = (
    f'[enhancements]\n"{TITLE_HEX}" = [\n'
    + "".join(f'    "{name}",\n' for name in FIRST_RUN_ENHANCEMENTS)
    + f']\n\n[per_game.{TITLE_HEX}]\ntop_shape = "wide16x9"\n'
)
TABLE_RX = re.compile(r"^\[fates_helpers\][^\n]*\n(?:(?!\[)[^\n]*\n?)*", re.M)


def _inside(path: str, top: str) -> bool:
    path, top = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(top))
    return path == top or path.startswith(top.rstrip("\\/") + os.sep)


def refuse_reason(appdata: str) -> str | None:
    """why this APPDATA folder may not be written (None = it may): only a folder below build/, never the real
    %APPDATA% (or anything inside it) and never the play folder's portable appdata."""
    if not _inside(appdata, BUILD) or os.path.normcase(os.path.abspath(appdata)) == os.path.normcase(BUILD):
        return "not below build/"
    real = os.environ.get("FEF_REAL_APPDATA") or os.environ.get("APPDATA")
    if real and (_inside(appdata, real) or _inside(real, appdata)):
        return "the real %APPDATA%"
    if _inside(appdata, os.path.join(ROOT, "play")):
        return "the play folder"
    return None


def settings_file(appdata: str) -> str:
    return os.path.join(appdata, "zakuro", "settings.toml")


def new_game_rows(rows: dict | None) -> dict:
    """the four New Game rows, every row named (missing = "game"); a key or word the program does not know raises
    ValueError (a planted refusal: never hand the program a value it would quietly read as Game's choice)"""
    out = dict(NEW_GAME_DEFAULTS)
    for k, v in (rows or {}).items():
        if k not in NEW_GAME_ROWS:
            raise ValueError(f"unknown New Game row {k!r}: one of {tuple(NEW_GAME_ROWS)}")
        if v not in NEW_GAME_ROWS[k]:
            raise ValueError(f"{k} must be one of {NEW_GAME_ROWS[k]}, not {v!r}")
        out[k] = v
    return out


def table_text(enemy_phase: str, true_hit: bool, rows: dict | None = None, explicit: bool = False) -> str:
    """the [fates_helpers] table: round 80's two lines, then each New Game row that is set (every row when explicit),
    in the program's field order"""
    if enemy_phase not in PHASES:
        raise ValueError(f"enemy_phase must be one of {PHASES}, not {enemy_phase!r}")
    rows = new_game_rows(rows)
    text = f'[fates_helpers]\nenemy_phase = "{enemy_phase}"\ntrue_hit = {"true" if true_hit else "false"}\n'
    for k in NEW_GAME_ROWS:
        if explicit or rows[k] != "game":
            text += f'{k} = "{rows[k]}"\n'
    return text


def merged(text: str | None, enemy_phase: str, true_hit: bool, explicit: bool, rows: dict | None = None) -> str:
    """the sandbox file's new text: the old text (or the first-run picks) without its [fates_helpers] table, then the
    table when a row is not at its default (or explicit)"""
    rows = new_game_rows(rows)
    body = FIRST_RUN if text is None else TABLE_RX.sub("", text)
    if (enemy_phase, true_hit) == ("normal", False) and rows == NEW_GAME_DEFAULTS and not explicit:
        return body
    if body and not body.endswith("\n"):
        body += "\n"
    return body + ("\n" if body else "") + table_text(enemy_phase, true_hit, rows, explicit)


def write(appdata: str, enemy_phase: str = "normal", true_hit: bool = False, explicit: bool = False,
          rows: dict | None = None) -> str:
    """writes the sandbox settings.toml; returns its path. Refuses a folder that is not a robot sandbox, and a row
    word the program does not know (before anything is written)."""
    try:
        new_game_rows(rows)
    except ValueError as e:
        raise SystemExit(f"refused: {e}")
    why = refuse_reason(appdata)
    if why:
        raise SystemExit(f"refused: {appdata}: {why}")
    if os.path.exists(STOP):
        raise SystemExit("STOP_ROUND: nothing written")
    path = settings_file(appdata)
    old = None
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            old = fh.read()
    text = merged(old, enemy_phase, true_hit, explicit, rows)
    tomllib.loads(text)  # never leave the program a file it cannot read (it would fall back to the defaults)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def read(appdata_or_file: str) -> dict:
    """the Helpers rows as the program reads them: {"enemy_phase", "true_hit", the four New Game rows, "table"};
    round 81: each key on its own (fates_helpers.rs `lenient`: a bad value gives that key's default and keeps the
    others), a table of the wrong kind or a missing file or table the defaults (settings.rs or_default)."""
    path = appdata_or_file if appdata_or_file.endswith(".toml") else settings_file(appdata_or_file)
    out = {"enemy_phase": "normal", "true_hit": False, **NEW_GAME_DEFAULTS, "table": False}
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8") as fh:
        data = tomllib.loads(fh.read())
    table = data.get("fates_helpers")
    if table is None:
        return out
    out["table"] = True
    if not isinstance(table, dict):
        return out
    phase, hit = table.get("enemy_phase", "normal"), table.get("true_hit", False)
    if isinstance(phase, str) and phase in PHASES:
        out["enemy_phase"] = phase
    if isinstance(hit, bool):
        out["true_hit"] = hit
    for k, words in NEW_GAME_ROWS.items():
        v = table.get(k, "game")
        if isinstance(v, str) and v in words:
            out[k] = v
    return out


def selftest() -> tuple[int, int]:
    import hashlib
    import shutil
    import tempfile
    n = ok = 0

    def check(cond, what):
        nonlocal n, ok
        n += 1
        ok += bool(cond)
        if not cond:
            print("FAIL", what)

    def refused(fn, what):
        try:
            fn()
        except (ValueError, SystemExit):
            check(True, what)
        else:
            check(False, what)

    dflt = {"enemy_phase": "normal", "true_hit": False, **NEW_GAME_DEFAULTS}
    # the text rules, no disk
    first = merged(None, "normal", False, False)
    check(first == FIRST_RUN and "fates_helpers" not in first, "defaults, no file: the first-run picks, no table")
    check(tomllib.loads(first)["per_game"][TITLE_HEX]["top_shape"] == "wide16x9", "first-run picks parse")
    t = merged(None, "4x", True, False)
    check(t.endswith(table_text("4x", True)) and tomllib.loads(t)["fates_helpers"] == {"enemy_phase": "4x",
                                                                                       "true_hit": True}, "4x on")
    check("fates_helpers" in merged(None, "normal", False, True), "explicit defaults write the table")
    old = 'show_fps = true\n\n[fates_helpers]\nenemy_phase = "2x"\ntrue_hit = false\n\n[keys]\na = "KeyK"\n'
    m = merged(old, "normal", True, False)
    d = tomllib.loads(m)
    check(d["show_fps"] is True and d["keys"]["a"] == "KeyK" and d["fates_helpers"]["true_hit"] is True
          and d["fates_helpers"]["enemy_phase"] == "normal" and m.count("[fates_helpers]") == 1, ("replace", m))
    check("fates_helpers" not in merged(old, "normal", False, False), "back to defaults removes the table")
    refused(lambda: table_text("8x", False), "8x refused")
    # round 81: the New Game rows
    check(table_text("normal", True) == '[fates_helpers]\nenemy_phase = "normal"\ntrue_hit = true\n',
          "True hit alone: round 80's two lines, no New Game key")
    one = merged(None, "normal", False, False, {"enemy_skip": "all"})
    check(tomllib.loads(one)["fates_helpers"] == {"enemy_phase": "normal", "true_hit": False, "enemy_skip": "all"},
          ("one row set: only that key", one))
    every = {"battle_animations": "off", "map_speed": "fast_while_a", "enemy_skip": "move", "hp_bars": "on"}
    allset = merged(None, "normal", False, False, every)
    check(tomllib.loads(allset)["fates_helpers"] == {"enemy_phase": "normal", "true_hit": False, **every},
          ("every row set", allset))
    keys = [ln.split(" = ")[0] for ln in table_text("normal", False, every).splitlines()[1:]]
    check(keys == ["enemy_phase", "true_hit", *NEW_GAME_ROWS], ("the program's field order", keys))
    check("fates_helpers" not in merged(None, "normal", False, False, dict(NEW_GAME_DEFAULTS)),
          "every row at game: no table")
    ex = tomllib.loads(merged(None, "normal", False, True))["fates_helpers"]
    check(ex == dflt, ("explicit: all six keys, the rows as game", ex))
    check("fates_helpers" not in merged(allset, "normal", False, False), "rows back to game removes the table")
    for k, words in NEW_GAME_ROWS.items():
        check(words[0] == "game" and len(words) == len(set(words)), f"{k}: Game's choice first")
        for w in words:
            check(tomllib.loads(table_text("normal", False, {k: w}, True))["fates_helpers"][k] == w, f"{k}={w}")
    # planted refusals: a word or key the program does not know
    refused(lambda: table_text("normal", False, {"map_speed": "warp"}), "map_speed warp refused")
    refused(lambda: table_text("normal", False, {"hp_bars": 3}), "hp_bars 3 refused")
    refused(lambda: table_text("normal", False, {"battle_animations": "Off"}), "a capital word refused")
    refused(lambda: table_text("normal", False, {"danger_zone": "on"}), "danger_zone (no row) refused")
    refused(lambda: merged(None, "normal", False, False, {"enemy_phase": "4x"}), "enemy_phase is not a New Game row")
    # the guards
    check(refuse_reason(os.path.join(BUILD, "r81", "s1", "appdata")) is None, "a build/ sandbox may be written")
    check(refuse_reason(os.path.join(ROOT, "play", "appdata")) is not None, "play\\appdata refused")
    check(refuse_reason(tempfile.gettempdir()) is not None, "outside build/ refused")
    check(refuse_reason(BUILD) is not None, "build/ itself refused")
    real = os.environ.get("APPDATA")
    if real:
        check(refuse_reason(real) is not None and refuse_reason(os.path.join(real, "zakuro")) is not None,
              "the real APPDATA refused")
        # planted: a write with rows set into the real APPDATA is refused before anything is touched (read only)
        rf = settings_file(real)

        def real_sha() -> str:
            if not os.path.isfile(rf):
                return "absent"
            with open(rf, "rb") as fh:
                return hashlib.sha256(fh.read()).hexdigest()
        before = real_sha()
        refused(lambda: write(real, rows={"enemy_skip": "all"}), "a real APPDATA write with rows refused")
        check(before == real_sha(), "the real settings.toml unchanged")
    refused(lambda: write(os.path.join(ROOT, "play", "appdata"), rows={"hp_bars": "off"}),
            "a play\\appdata write refused")
    # on disk, in a scratch sandbox below build/
    box = os.path.join(BUILD, "r81", "py", "_selftest_helpers")
    shutil.rmtree(box, ignore_errors=True)
    try:
        if not os.path.exists(STOP):
            app = os.path.join(box, "appdata")
            p = write(app, "2x", False)
            check(read(app) == {**dflt, "enemy_phase": "2x", "table": True}, ("written 2x", read(app)))
            write(app, "normal", False)
            check(read(app) == {**dflt, "table": False}, "rewritten defaults")
            with open(p, encoding="utf-8") as fh:
                check(tomllib.loads(fh.read())["enhancements"][TITLE_HEX], "first-run picks kept")
            write(app, "normal", True, rows={"map_speed": "fast", "hp_bars": "off"})
            check(read(app) == {**dflt, "true_hit": True, "map_speed": "fast", "hp_bars": "off", "table": True},
                  ("two rows and True hit", read(app)))
            refused(lambda: write(app, rows={"map_speed": "warp"}), "a bad word: refused on disk")
            check(read(app)["map_speed"] == "fast", "a refused write left the file as it was")
            write(app, "normal", False, explicit=True)
            check(read(app) == {**dflt, "table": True}, "explicit all-game table reads as the defaults")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write('[fates_helpers]\nenemy_phase = "8x"\ntrue_hit = true\nmap_speed = "warp"\nhp_bars = "off"\n')
            check(read(app) == {**dflt, "true_hit": True, "hp_bars": "off", "table": True},
                  ("a bad value: only that key falls back", read(app)))
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("fates_helpers = 4\n")
            check(read(app) == {**dflt, "table": True}, "a table of the wrong kind: the defaults")
            check(read(os.path.join(box, "none")) == {**dflt, "table": False}, "no file: defaults")
    finally:
        shutil.rmtree(box, ignore_errors=True)
    return ok, n


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["write", "read", "selftest"])
    ap.add_argument("appdata", nargs="?")
    ap.add_argument("--enemy-phase", default="normal", choices=PHASES)
    ap.add_argument("--true-hit", default="off", choices=("off", "on"))
    ap.add_argument("--explicit", action="store_true")
    for k, words in NEW_GAME_ROWS.items():   # round 81: --battle-animations, --map-speed, --enemy-skip, --hp-bars
        ap.add_argument("--" + k.replace("_", "-"), dest=k, default="game", choices=words)
    a = ap.parse_args(argv)
    if a.cmd == "selftest":
        ok, n = selftest()
        print(f"helpers_settings selftest: {ok}/{n}")
        return 0 if ok == n else 1
    if not a.appdata:
        ap.error("an APPDATA folder is needed")
    if a.cmd == "write":
        rows = {k: getattr(a, k) for k in NEW_GAME_ROWS}
        print(write(a.appdata, a.enemy_phase, a.true_hit == "on", a.explicit, rows))
    else:
        print(read(a.appdata))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
