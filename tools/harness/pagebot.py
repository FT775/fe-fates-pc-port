#!/usr/bin/env python3
"""Round 60 PAGE ROBOT (docs/tests/PAGEBOT.md): drives the REAL in-game Randomizer page of a build copy of the game,
headless, and checks the owner's rule (F-047 addendum, round 59: a guess the page made in the background is thrown
away the moment a row changes; Start game uses exactly the page's values; nothing is laid before Start game) and
times Start game to the avatar screen.

The page is egui (engine/zakuro/crates/zakuro/src/rando_page.rs) and only draws with a window. A headless run has
no page: the core answers the mode pick by itself (FEF_RANDO_ANSWER or "off"). So the robot needs the frontend hook
FEF_PAGEBOT (build/r60/screens/plans/PAGEBOT_HOOK.md, for the assemble step): in a --headless run it keeps the mode
pick waiting for the page, draws the real page each frame into a context with no window, and feeds it real egui
pointer and key events at the rectangles the page's own widgets reported that frame (rows, choices, Start game). It
writes one JSON line per event to FEF_PAGEBOT_LOG. Without the hook this robot refuses (no log, or no "hook" line).

    python tools/harness/pagebot.py calibrate            frames from the mode pick to the avatar creator (boot-server,
                                                         the recorded new-game route; no hook needed)
    python tools/harness/pagebot.py run [--exe EXE] [--seal] [--name N] [--scenario agency|quick|esc|presets|escfit|p4|helpers|newgame]
    python tools/harness/pagebot.py selftest             the verdict rules on invented logs

Rules kept (F-042): build/STOP_ROUND checked before every start and every second; every start --headless N --mute
with --data, APPDATA, LOCALAPPDATA, TMP below build/r61/pagebot/<name>/ (round 61; --top to change); below normal priority, no console window;
a visible window = the run failed (killed, reported); one run per call, never retried; never play/game's own exe
(a copy below build/ only)."""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TOP = os.environ.get("FEF_PAGEBOT_TOP") or os.path.join(ROOT, "build", "r61", "pagebot")  # --top overrides
CALIBRATE = os.path.join(ROOT, "build", "r60", "pagebot", "calibrate.json")  # round 60, frozen boot-server copy
STOP = os.path.join(ROOT, "build", "STOP_ROUND")
TITLE = "0004000000179800"
sys.path.append(os.path.join(ROOT, "tools"))
import paths  # noqa: E402  (F-048: roms/ first, then the old root place for one release)
ROM = str(paths.try_resolve_rom(repo=ROOT, check="header") or paths.roms_dir(ROOT) / paths.GAME.default_rom)
REPLAY = os.path.join(ROOT, "build", "r58", "assemble", "new-game.replay")
PLAY_EXE = os.path.join(ROOT, "play", "game", "Fire Emblem Fates.exe")
AVATAR = "title__ProcMyUnitEdit"   # markers.json: the avatar creator's process

# the agency scenario (owner's rule): everything on, wait until the background make of that guess has FINISHED,
# then change rows (a guess is now stale), press Start game at once; the laid run must equal a fresh make of the
# final values and the stale guess's folders must be gone. quick: everything on, wait for the make, Start game.
SCENARIOS = {
    "agency": [
        {"wait": "page_open"},
        {"click": "btn:everything_on"},
        {"wait": "prebuild_done"},
        {"mark": "guess_done"},
        {"pick_other": "choice"},          # the first choice row: its next choice (the robot reads the schema)
        {"pick_other": "onoff"},           # the first on/off row after Randomizer: flipped
        {"click": "btn:start", "mark": "start"},
        {"wait": "laid"},
        {"wait": "avatar"},
    ],
    "quick": [
        {"wait": "page_open"},
        {"click": "btn:everything_on"},
        {"wait": "prebuild_done"},
        {"click": "btn:start", "mark": "start"},
        {"wait": "laid"},
        {"wait": "avatar"},
    ],
    # round 72: the Esc menu's Randomizer window, its Next New Game part (patch 0032), judged by its OWN check list
    # (judge_esc), not the New Game page's guess / stale / exact. A randomized game is started, then over the game:
    # a change that is never kept (the window closed), the window again (the change must be gone), Keep with no
    # change (last.json = Start game's values), one row changed and kept (last.json differs in that row only), the
    # background guess for the next New Game left to finish, the window closed.
    # The game is started with Randomizer on, every other row at its default and the spoiler log off: This run is
    # then two short lines. The hook draws the page into an 800 x 480 screen (pagebot.rs), half the default window
    # (stacked, scale 2: 800 x 960); after Everything on, This run lists every changed row and pushes the Next New
    # Game part below y 480, where no click lands (round 72 first try: Keep at y 697, the run timed out).
    "esc": [
        {"wait": "page_open"},
        {"click": "opt:randomizer=on"},
        {"click": "opt:spoiler_log=off"},
        {"wait": "prebuild_done"},
        {"click": "btn:start", "mark": "start"},
        {"wait": "laid"},
        {"esc": "randomizer"},
        {"wait": "next_open"},
        {"click": "next:opt:randomizer=off", "mark": "unkept_change"},
        {"esc": "close"},
        {"esc": "randomizer"},
        {"wait": "next_open"},
        {"expect_last": {"randomizer": True}},
        {"click": "next:btn:keep", "mark": "keep_same"},
        {"expect_last": {"randomizer": True}},
        {"click": "next:row:difficulty"},
        {"click": "next:opt:difficulty=hard"},
        {"click": "next:btn:keep", "mark": "keep_changed"},
        {"expect_last": {"randomizer": True, "difficulty": "hard"}},
        {"wait": "prebuild_done"},
        {"esc": "close"},
    ],
}
ESC_CHANGED = {"difficulty": "hard"}   # the one row the esc scenario keeps changed
ESC_KEPT_NOTE = "Kept for the next New Game."

# Round 74 (P4, docs/ROUND74_PLAN.md; docs/rando/FULL_BLOCK.md sections 6, 7 and 9; patch 0036): the preset buttons
# and the Share code field on the New Game page, and the Esc window's Keep with This run full, judged by values (the
# page draws no picture without a window). Placeholders resolved from the live schema by resolve():
#   {"expect_preset": name}  -> {"expect": every answer key but the seed} of that preset pressed on default values
#   {"paste_made": "good"}   -> {"paste": a code made by tools/randomizer/sharecode.py} (MADE values, MADE_SEED)
#   {"paste_made": "typo"}   -> the same code with its seed's last character changed (the check refuses it)
#   {"expect_made": "good"}  -> {"expect": the made code's whole answer, seed included}
# The judge (judge_p4) compares whole answer texts, so a row the expect step cannot name (one left out of the answer
# at its default) is checked too.
PRESET_STEPS = [
    {"wait": "page_open"},
    {"click": "btn:preset:light"},
    {"expect_preset": "light"},
    {"click": "btn:preset:wild"},
    {"expect_preset": "wild"},
    {"click": "btn:preset:light"},
    {"expect_preset": "light"},
    {"click": "btn:preset:wild"},
    {"click": "btn:share:copy", "mark": "copy"},
    {"click": "btn:preset:light"},
    {"click": "btn:random"},                     # another seed in the box: the pasted code must bring its own
    {"click": "row:share"},
    {"paste_copied": True, "mark": "paste_copied"},
    {"expect_preset": "wild"},
    {"click": "btn:defaults"},
    {"click": "row:share"},
    {"paste_made": "good", "mark": "paste_made"},
    {"expect_made": "good"},
    {"click": "row:share"},
    {"paste_made": "typo", "mark": "paste_typo"},
    {"expect_made": "good"},
]
# the Esc window with This run full (Randomize everything changes about 22 shown rows; the spoiler log stays on, so
# its button is there too) at the hook's 800 x 480 screen: Keep must be drawn wholly on it, and a click on it keeps
ESCFIT_STEPS = [
    {"click": "btn:everything_on"},
    {"wait": "prebuild_done"},
    {"click": "btn:start", "mark": "start"},
    {"wait": "laid"},
    {"esc": "randomizer"},
    {"wait": "next_open"},
    {"expect_target": "next:btn:keep", "mark": "keep_reachable"},
    {"click": "next:btn:keep", "mark": "keep"},
    {"expect_last": {"randomizer": True}},
    {"esc": "close"},
]
SCENARIOS["presets"] = PRESET_STEPS
SCENARIOS["escfit"] = [{"wait": "page_open"}] + ESCFIT_STEPS
SCENARIOS["p4"] = PRESET_STEPS + ESCFIT_STEPS          # one job (the plan's one P4 lane)
MADE_SEED = "p4share-74"
MADE_SET = {"difficulty": "hard", "enemy_levels": 3, "growth_variance": 45, "chests": True, "recolour": "clear"}
SHARE_USED = "Share code used: every setting and the seed come from it."     # rando_page.rs SHARE_USED
SHARE_TYPO = "This code has a typo."                                         # rando_page.rs SHARE_TYPO
THIS_RUN_FULL = 15     # This run counts as full from this many listed rows (Randomize everything: about 22)

# Round 80 (S1 / H7, docs/ROUND80_PLAN.md; patch 0037): the Paused window's Helpers rows save. The original game is
# started (Randomizer stays off), then over the game the Helpers part of the Esc window is opened, True hit On is
# clicked (round 80 cut 3: no Enemy phase row, so no 4x click), and the job's OWN settings.toml (its APPDATA below the job folder) must hold the [fates_helpers] table;
# before the clicks the defaults are there and no table is written. The real %APPDATA%\zakuro\settings.toml must
# hash the same before and after (run() reads it, never writes it). Judged by judge_helpers.
HELPERS_STEPS = [
    {"wait": "page_open"},
    {"click": "btn:start", "mark": "start"},
    {"wait": "laid"},
    {"esc": "paused"},
    {"expect_settings": {"enemy_phase": "normal", "true_hit": False}, "mark": "before"},
    {"click": "helpers:opt:true_hit=on", "mark": "true_hit"},
    {"expect_settings": {"enemy_phase": "normal", "true_hit": True}, "mark": "after"},
    {"expect_target": "helpers:opt:true_hit=on", "mark": "on_screen"},
    {"esc": "close"},
]
SCENARIOS["helpers"] = HELPERS_STEPS
HELPERS_SAVED = {"enemy_phase": "normal", "true_hit": True}     # enemy_phase stays in the table, unread (cut 3)

# Round 81 (S1, docs/ROUND81_PLAN.md; HOME_DESIGN 6; patch 0039): the "New Game defaults" rows save. As "helpers":
# the original game, then the Esc window's Helpers part; the collapsing line is opened, Battle animations Off and
# Enemy turn skip All are clicked, Battle animations is put back to Game's choice. The job's OWN settings.toml must
# end with exactly enemy_skip = "all" among the four New Game keys (a row at Game's choice is not written; pagebot.rs
# reads an expected "game" as an absent key), and the real %APPDATA%\zakuro\settings.toml must hash the same before
# and after. Judged by judge_newgame.
NEW_GAME_KEYS = ("battle_animations", "map_speed", "enemy_skip", "hp_bars")
NEWGAME_STEPS = [
    {"wait": "page_open"},
    {"click": "btn:start", "mark": "start"},
    {"wait": "laid"},
    {"esc": "paused"},
    {"expect_settings": {"battle_animations": "game", "map_speed": "game", "enemy_skip": "game", "hp_bars": "game",
                         "true_hit": False}, "mark": "before"},
    {"click": "helpers:newgame:section", "mark": "open"},
    {"click": "helpers:opt:battle_animations=off", "mark": "battle_off"},
    {"click": "helpers:opt:enemy_skip=all", "mark": "skip_all"},
    {"expect_settings": {"battle_animations": "off", "enemy_skip": "all", "map_speed": "game"}, "mark": "set"},
    {"click": "helpers:opt:battle_animations=game", "mark": "battle_game"},
    {"expect_settings": {"battle_animations": "game", "enemy_skip": "all", "map_speed": "game", "hp_bars": "game",
                         "true_hit": False}, "mark": "back"},
    {"expect_target": "helpers:opt:hp_bars=on", "mark": "on_screen"},
    {"esc": "close"},
]
SCENARIOS["newgame"] = NEWGAME_STEPS
NEWGAME_ROW_CLICKS = ["helpers:opt:battle_animations=off", "helpers:opt:enemy_skip=all",
                      "helpers:opt:battle_animations=game"]
NEWGAME_BASE = {"enemy_phase": "normal", "true_hit": False}      # the program's JSON of Helpers at the defaults
NEWGAME_CHANGES = [dict(NEWGAME_BASE, battle_animations="off"),
                   dict(NEWGAME_BASE, battle_animations="off", enemy_skip="all"),
                   dict(NEWGAME_BASE, enemy_skip="all")]
NEWGAME_SET = NEWGAME_CHANGES[1]
NEWGAME_SAVED = NEWGAME_CHANGES[2]
NEWGAME_FILE_ROWS = {"enemy_skip": "all"}                         # the four New Game keys the file must end with


def stop_check() -> None:
    if os.path.exists(STOP):
        raise SystemExit("STOP_ROUND exists: stopped")


def sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def below_build(path: str) -> bool:
    b = os.path.abspath(os.path.join(ROOT, "build"))
    return os.path.commonpath([os.path.abspath(path), b]) == b


# ------------------------------------------------------------------ the schema and the scenario
def schema(seal: bool) -> list[dict]:
    """rando.py schema: the page's rows (the same text the page reads)."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
    import rando  # noqa: E402
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rando.main(["schema"])   # one page for both games (the page shows the same rows)
    return json.loads(buf.getvalue())["rows"]


def _ig():
    sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
    import ingame  # noqa: E402
    import sharecode  # noqa: E402
    return ingame, sharecode


def preset_answer(rows: list[dict], name: str, seal: bool = False) -> dict:
    """round 74: the answer after a press of preset `name` on the page (seed box empty: no seed key)"""
    IG, _S = _ig()
    game = "seal" if seal else None
    vals = IG.page_preset(rows, {"seed": ""}, name, game)
    vals["seed"] = "x"
    a = IG.page_answers(rows, vals, game)
    a.pop("seed", None)
    return a


def made_code(rows: list[dict], seal: bool = False, typo: bool = False) -> str:
    """round 74: the share code sharecode.py makes for the MADE values (Wild + MADE_SET, MADE_SEED)"""
    IG, S = _ig()
    game = "seal" if seal else None
    vals = IG.page_preset(rows, {"seed": MADE_SEED}, "wild", game)
    vals = IG.page_restore(rows, dict(vals, **MADE_SET), game)
    code = S.encode(rows, vals, MADE_SEED, "seal" if seal else "fates")
    return code[:-1] + ("5" if code[-1] != "5" else "6") if typo else code


def made_answer(rows: list[dict], seal: bool = False) -> dict:
    """round 74: the page's answer after the made code is pasted (sharecode.page_values, then the page's rules)"""
    IG, S = _ig()
    game = "seal" if seal else "fates"
    vals = S.page_values(rows, made_code(rows, seal), game)
    return IG.page_answers(rows, vals, None if game == "fates" else game)


def resolve(steps: list[dict], rows: list[dict], seal: bool = False) -> list[dict]:
    """pick_other steps -> concrete clicks on the page's own targets ("opt:<key>=<value>"); round 74: the P4
    placeholders (expect_preset, paste_made, expect_made) -> expect / paste steps."""
    out = []
    all_on = {r["key"]: r.get("all", r.get("default")) for r in rows}
    used = set()
    for st in steps:
        if "expect_preset" in st:
            out.append({"expect": preset_answer(rows, st["expect_preset"], seal)})
            continue
        if "paste_made" in st:
            step = {"paste": made_code(rows, seal, typo=st["paste_made"] == "typo")}
            if "mark" in st:
                step["mark"] = st["mark"]
            out.append(step)
            continue
        if "expect_made" in st:
            out.append({"expect": made_answer(rows, seal)})
            continue
        if "pick_other" not in st:
            out.append(st)
            continue
        kind = st["pick_other"]
        # round 62b: hidden rows are not drawn, page-only rows are never in the answer, a switch row has no list
        row = next(r for r in rows if r.get("kind") == kind and not r.get("fixed") and r["key"] not in used
                   and r["key"] not in ("randomizer", "seed") and not r.get("hidden") and not r.get("page_only")
                   and not r.get("switch") and not (seal and "seal" in (r.get("hide_for") or {})))
        used.add(row["key"])
        cur = all_on.get(row["key"])
        if kind == "choice":
            ch = row["choices"]
            new = ch[(ch.index(cur) + 1) % len(ch)] if cur in ch else ch[0]
            out.append({"click": f"row:{row['key']}"})                  # opens the list
            out.append({"click": f"opt:{row['key']}={new}"})
        else:
            new = not bool(cur)
            out.append({"click": f"opt:{row['key']}={'on' if new else 'off'}"})
        out.append({"expect": {row["key"]: new}})
    return out


# ------------------------------------------------------------------ calibration (boot-server, no hook)
def calibrate(name: str = "calibrate") -> dict:
    """The recorded new-game route on a headless boot-server copy: the frame the core saw the mode pick (its log)
    and the first frame the avatar creator shows (markers). Writes <top>/calibrate.json (round 60: build/r60/pagebot/calibrate.json)."""
    sys.path.insert(0, HERE)
    import server as sv  # noqa: E402
    stop_check()
    route = json.load(open(os.path.join(ROOT, "config", "harness", "routes.json"), encoding="utf-8"))["routes"]["new-game"]
    root = os.path.join(TOP, name)
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    res = {"route": "new-game", "frames": []}
    bin_dir = os.path.join(ROOT, "build", "r60", "screens", "bin")
    kw = {}
    if os.path.isfile(os.path.join(bin_dir, "boot-server.exe")):
        kw = {"exe": os.path.join(bin_dir, "boot-server.exe"), "lib": os.path.join(bin_dir, f"{TITLE}.dll")}
        res["exe_sha"] = sha(kw["exe"])
    with sv.Server(name, save=route.get("save", "new-game-empty"), root=root, timeout=600,
                   extra_env={"RUST_LOG": "info", "FEF_RANDO_TOOL": os.path.join(ROOT, "tools", "randomizer")}, **kw) as s:
        s.inputs_set(route["input"])
        last, avatar = None, None
        for f in range(3000, int(route["frames"]) + 1, 5):
            stop_check()
            s.step_to(f)
            cur = s.markers().get("current")
            if cur != last:
                res["frames"].append([f, cur])
                last = cur
            if cur == AVATAR:
                avatar = f
                break
        log = open(s.log_path, "rb").read().decode("utf-8", "replace")
    res["avatar_frame"] = avatar
    res["rando_log"] = [ln[-160:] for ln in log.splitlines() if "rando" in ln.lower()][:20]
    import re
    pick = next((int(m.group(1)) for ln in res["rando_log"] for m in [re.search(r"mode picked at frame (\d+)", ln)]
                 if m), None)
    res["pick_frame"] = pick
    res["pick_to_avatar"] = (avatar - pick) if (avatar and pick) else None
    shutil.rmtree(os.path.join(root, name), ignore_errors=True)
    json.dump(res, open(os.path.join(TOP, "calibrate.json"), "w"), indent=1)
    return res


# ------------------------------------------------------------------ the run (needs the FEF_PAGEBOT hook)
def visible_windows(pid: int) -> list:
    import ctypes.wintypes as W
    u = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(h, _):
        q = W.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(q))
        if q.value == pid and u.IsWindowVisible(h):
            found.append(h)
        return True
    u.EnumWindows(cb, 0)
    return found


def run(exe: str, name: str, seal: bool, scenario: str, frames: int, avatar_after: int | None) -> dict:
    stop_check()
    exe = os.path.abspath(exe)
    if os.path.normcase(exe) == os.path.normcase(os.path.abspath(PLAY_EXE)) or not below_build(exe):
        raise SystemExit("refused: the robot runs only a copy of the game below build/, never play/game's own exe")
    d = os.path.join(TOP, name)
    if not below_build(d):
        raise SystemExit("refused: job folder not below build/")
    shutil.rmtree(d, ignore_errors=True)
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("FEF_", "ZAKURO_", "RUST_LOG"))}
    env.update(APPDATA=os.path.join(d, "appdata"), LOCALAPPDATA=os.path.join(d, "localappdata"),
               TMP=os.path.join(d, "tmp"), TEMP=os.path.join(d, "tmp"))
    for k in ("APPDATA", "LOCALAPPDATA", "TMP"):
        os.makedirs(env[k], exist_ok=True)
    data = os.path.join(d, "data")
    os.makedirs(data)
    rows = schema(seal)
    steps = resolve(SCENARIOS[scenario], rows, seal)
    script = os.path.join(d, "script.json")
    json.dump({"steps": steps, "avatar_after": avatar_after}, open(script, "w"), indent=1)
    log = os.path.join(d, "pagebot.jsonl")
    env.update(FEF_PAGEBOT=script, FEF_PAGEBOT_LOG=log, ZAKURO_REPLAY=REPLAY, FEF_HEADLESS_PACE="60",
               FEF_RANDO_TOOL=os.path.join(ROOT, "tools", "randomizer"), FEF_PYTHON=sys.executable, RUST_LOG="info")
    cmd = [exe, ROM, "--headless", str(frames), "--mute", "--data", data]
    if seal:
        prof = os.path.join(d, "seal-profile")
        src = os.path.join(ROOT, "play", "seal-of-flames")
        os.makedirs(os.path.join(prof, "data"))
        for f in ("manifest.json", "profile.json", "game-settings.toml"):
            if os.path.isfile(os.path.join(src, f)):
                shutil.copy2(os.path.join(src, f), prof)
        shutil.copytree(os.path.join(src, "data", "mods"), os.path.join(prof, "data", "mods"))
        cmd += ["--game", "seal", "--seal-profile", prof]
    res = {"name": name, "exe": os.path.relpath(exe, ROOT), "exe_sha": sha(exe), "scenario": scenario, "steps": steps,
           "seal": seal}
    real_before = real_settings_sha()   # round 80: the owner's settings file, read only
    t0 = time.time()
    p = subprocess.Popen(cmd, env=env, cwd=d, creationflags=0x4000 | 0x08000000, stdin=subprocess.DEVNULL,
                         stdout=open(os.path.join(d, "stdout.txt"), "w"), stderr=subprocess.STDOUT)
    res["pid"] = p.pid
    status = None
    while p.poll() is None:
        if visible_windows(p.pid):
            p.kill()
            status = "FAILED: a visible window appeared"
            break
        if time.time() - t0 > 900:
            p.kill()
            status = "FAILED: timeout"
            break
        if os.path.exists(STOP):
            p.kill()
            status = "STOPPED"
            break
        time.sleep(1)
    p.wait()
    res["exit"], res["status"], res["seconds"] = p.returncode, status, round(time.time() - t0, 1)
    events = []
    if os.path.isfile(log):
        events = [json.loads(ln) for ln in open(log, encoding="utf-8") if ln.strip()]
    res["events"] = len(events)
    res["real_settings_before"], res["real_settings_after"] = real_before, real_settings_sha()
    res.update(judge(events, data, seal, scenario=scenario, real=(res["real_settings_before"],
                                                                  res["real_settings_after"])))
    json.dump(res, open(os.path.join(d, "result.json"), "w"), indent=1, ensure_ascii=False)
    return res


def real_settings_file() -> str | None:
    """round 80: the owner's own Zakuro settings file (this process's APPDATA, never a job's)"""
    base = os.environ.get("APPDATA")
    return os.path.join(base, "zakuro", "settings.toml") if base else None


def real_settings_sha() -> str | None:
    """round 80: sha256 of the owner's settings file, or "absent" (read only; the robot never writes it)"""
    f = real_settings_file()
    if not f:
        return None
    return sha(f) if os.path.isfile(f) else "absent"


def fresh_make(answer_text: str, seal: bool, work: str) -> str | None:
    """rando.py make --patch-out of exactly this answer, no cache, in an empty folder (as the core makes it)."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
    import ingame  # noqa: E402
    # tools/randomizer/rando.py, not tools/play/rando.py (ingame puts tools/play on the path)
    want = os.path.normcase(os.path.join(ROOT, "tools", "randomizer", "rando.py"))
    if "rando" in sys.modules and os.path.normcase(getattr(sys.modules["rando"], "__file__", "") or "") != want:
        del sys.modules["rando"]
    sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
    import rando  # noqa: E402
    a = json.loads(answer_text)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    args = ["make"] + ingame.make_args(a) + ["--out", os.path.join(work, "mod"), "--patch-out",
                                             os.path.join(work, "patch.txt")]
    if seal:
        import sources  # noqa: E402
        # round 61: the robot's own Seal layer (never the shared build/sources/seal, which other jobs and tracks
        # rebuild for their own mod or base folder)
        sources.LAYER_TOP = os.path.join(TOP, "_sources")
        romfs = os.path.join(ROOT, "build", "r58", "chapsel", "_sealmod", TITLE, "romfs")
        sources.activate("seal", romfs)
        args += ["--game", "seal", "--seal-romfs", romfs]
    with contextlib.redirect_stdout(io.StringIO()):
        code = rando.main(args)
    p = os.path.join(work, "patch.txt")
    return sha(p) if code == 0 and os.path.isfile(p) else None


def judge(events: list[dict], data: str, seal: bool, make=fresh_make, scenario: str = "agency",
          real: tuple | None = None) -> dict:
    """The verdict from the hook's log (pure apart from make, self-tested):
    hook       the exe has the FEF_PAGEBOT hook (its first line)
    guess      a background make of the first values FINISHED before the rows changed (the rule needs a stale one)
    stale      after the change, that guess was thrown away (a 'discarded' event names its id) and its run folder
               is gone at the end
    exact      Start game's answer text equals the page's values after the change (the hook logs both), and the
               laid run's patch.txt is byte-identical to a fresh make of that text
    nothing_before_start  no 'laid' event before the Start game click
    timing     ms from the Start game click to 'laid' and to the avatar creator (game frames run since the answer)"""
    if scenario == "esc":
        return judge_esc(events, data, seal, make)
    if scenario == "helpers":
        return judge_helpers(events, data, real)
    if scenario == "newgame":
        return judge_newgame(events, data, real)
    if scenario in ("presets", "escfit", "p4"):
        return judge_p4(events, seal, scenario)
    out = {"checks": {}}
    ev = {e.get("event"): e for e in events}
    c = out["checks"]
    c["hook"] = bool(events) and events[0].get("event") == "hook"
    if not c["hook"]:
        out["verdict"] = "REFUSED: this exe has no FEF_PAGEBOT hook (build/r60/screens/plans/PAGEBOT_HOOK.md)"
        return out
    done = [e for e in events if e.get("event") == "prebuild_done"]
    start = next((e for e in events if e.get("event") == "click" and e.get("target") == "btn:start"), None)
    answer = ev.get("answer")
    laid = ev.get("laid")
    c["guess"] = bool(done) and start is not None and done[0]["ms"] < start["ms"]
    guess_id = done[0].get("id") if done else None
    disc = [e for e in events if e.get("event") == "discarded"]
    run_dir = os.path.join(data, "rando", TITLE, "runs")
    if seal:  # Seal of Flames plays from its profile's data folder (game_pick::profile_data)
        run_dir = os.path.join(os.path.dirname(data), "seal-profile", "data", "rando", TITLE, "runs")
    left = sorted(os.listdir(run_dir)) if os.path.isdir(run_dir) else []
    laid_id = (laid or {}).get("id")
    c["stale"] = bool(guess_id) and guess_id != laid_id and any(e.get("id") == guess_id for e in disc) and \
        guess_id not in left
    c["only_laid_left"] = left == ([laid_id] if laid_id else [])
    c["nothing_before_start"] = laid is not None and start is not None and events.index(laid) > events.index(start)         and (answer is None or events.index(answer) > events.index(start))
    ans = (answer or {}).get("text")
    c["answer_is_page_values"] = bool(ans) and ans == (start or {}).get("page_values")
    out["left_runs"] = left
    if laid_id and ans:
        laid_patch = os.path.join(run_dir, laid_id, "patch.txt")
        got = sha(laid_patch) if os.path.isfile(laid_patch) else None
        want = make(ans, seal, os.path.join(os.path.dirname(data), "fresh"))
        out["laid_patch_sha"], out["fresh_patch_sha"] = got, want
        c["exact"] = bool(got) and got == want
    else:
        c["exact"] = False
    av = ev.get("avatar")
    if start and laid:
        out["ms_start_to_laid"] = laid["ms"] - start["ms"]
    exp = [e for e in events if e.get("event") == "expect"]
    c["expects_ok"] = all(e.get("ok", True) for e in exp)
    out["rows_changed"] = [e.get("expect") for e in exp]
    if start and av:
        out["ms_start_to_avatar"] = av["ms"] - start["ms"]
        c["under_2s"] = out["ms_start_to_avatar"] < 2000
    # quick (timing): no row changes, so no stale guess to throw away; everything else must hold
    need = ("hook", "guess", "stale", "only_laid_left", "nothing_before_start", "answer_is_page_values", "exact",
            "expects_ok") if scenario != "quick" else ("hook", "guess", "only_laid_left", "nothing_before_start",
                                                        "answer_is_page_values", "exact")
    out["scenario_checks"] = list(need)
    out["verdict"] = "PASS" if all(c.get(k) for k in need) else "FAIL"
    return out


ESC_CHECKS = ("hook", "game_laid_first", "next_shown", "steps_known", "game_untouched", "laid_run_kept",
              "unkept_thrown", "keep_same_equal", "keep_changed_one_row", "kept_note", "disk_last", "next_guess",
              "runs_left_ok", "expects_ok")


def _data_root(data: str, seal: bool) -> str:
    """the data folder the page writes to: Seal of Flames plays from its profile's data folder"""
    return os.path.join(os.path.dirname(data), "seal-profile", "data") if seal else data


def judge_esc(events: list[dict], data: str, seal: bool, make=fresh_make) -> dict:
    """Round 72: the Esc Randomizer window's Next New Game part (patch 0032), its own check list (pure apart from
    make and the job's data folder, self-tested). Scenario "esc" (SCENARIOS):
    hook                 the exe has the FEF_PAGEBOT hook
    game_laid_first      a randomized game was laid (a run id) before the Esc window first opened: the part is
                         looked at over a game being played
    next_shown           every opening of the window showed the Next New Game part (wait next_open done)
    steps_known          the hook knew every step (no unknown_step) and the script ran to its end
    game_untouched       no answer and no lay after the window first opened (the game playing never changes)
    laid_run_kept        the laid run's patch.txt is still there at the end and equals a fresh make of the Start
                         game answer (exact): nothing the window did touched the game's own run
    unkept_thrown        the change made before closing the window without Keep is not in last.json when the
                         window is open again (randomizer still true) ...
    keep_same_equal      ... and Keep with no change writes exactly the values Start game wrote (the thrown change
                         did not come back in the new draft)
    keep_changed_one_row Keep after one row changed writes last.json that differs from Start game's values in that
                         row only, to the new value (ESC_CHANGED)
    kept_note            the part's note after that Keep is "Kept for the next New Game."
    disk_last            <data>/rando/last.json on disk at the end equals what the hook read after the last Keep
    next_guess           the background guess started after the last Keep is of the kept values (its answer text
                         holds ESC_CHANGED) and finished without error
    runs_left_ok         the runs folder holds the laid run and otherwise only guesses started after the window
                         opened (the next New Game's guess), nothing else
    expects_ok           every expect_last step was ok"""
    out = {"checks": {}, "scenario_checks": list(ESC_CHECKS)}
    c = out["checks"]
    c["hook"] = bool(events) and events[0].get("event") == "hook"
    if not c["hook"]:
        out["verdict"] = "REFUSED: this exe has no FEF_PAGEBOT hook (build/r60/screens/plans/PAGEBOT_HOOK.md)"
        return out
    idx = {id(e): i for i, e in enumerate(events)}
    named = lambda n: [e for e in events if e.get("event") == n]  # noqa: E731
    opens = [e for e in named("esc") if e.get("window") == "open"]
    first_open = idx[id(opens[0])] if opens else len(events)
    laid = next((e for e in named("laid")), None)
    answer = next((e for e in named("answer")), None)
    laid_id = (laid or {}).get("id")
    c["game_laid_first"] = bool(laid_id) and bool(opens) and idx[id(laid)] < first_open
    next_done = [e for e in named("wait_done") if e.get("wait") == "next_open"]
    c["next_shown"] = bool(opens) and len(next_done) == len(opens)
    hook_steps = events[0].get("steps")
    c["steps_known"] = not named("unknown_step") and not named("rows_missing") and bool(named("end")) and \
        len(named("esc")) >= 2 and (hook_steps is None or hook_steps == len(SCENARIOS["esc"]))
    after = events[first_open:]
    c["game_untouched"] = bool(opens) and not any(e.get("event") in ("answer", "laid") for e in after)
    root = _data_root(data, seal)
    run_dir = os.path.join(root, "rando", TITLE, "runs")
    left = sorted(os.listdir(run_dir)) if os.path.isdir(run_dir) else []
    out["left_runs"] = left
    ans = (answer or {}).get("text")
    if laid_id and ans:
        laid_patch = os.path.join(run_dir, laid_id, "patch.txt")
        got = sha(laid_patch) if os.path.isfile(laid_patch) else None
        want = make(ans, seal, os.path.join(os.path.dirname(data), "fresh"))
        out["laid_patch_sha"], out["fresh_patch_sha"] = got, want
        c["laid_run_kept"] = bool(got) and got == want
    else:
        c["laid_run_kept"] = False
    exl = named("expect_last")
    out["expect_last"] = [{"expect": e.get("expect"), "ok": e.get("ok"), "note": e.get("note")} for e in exl]
    c["expects_ok"] = len(exl) == 3 and all(e.get("ok") for e in exl)
    lasts = [e.get("last") if isinstance(e.get("last"), dict) else None for e in exl]
    first, same, changed = (lasts + [None, None, None])[:3]
    reopened = len(opens) >= 2 and bool(exl) and idx[id(exl[0])] > idx[id(opens[1])]
    c["unkept_thrown"] = reopened and bool(first) and first.get("randomizer") is True
    c["keep_same_equal"] = bool(first) and same == first
    diff = sorted(k for k in set(first or {}) | set(changed or {}) if (first or {}).get(k) != (changed or {}).get(k))
    out["kept_diff"] = diff
    c["keep_changed_one_row"] = bool(first) and bool(changed) and diff == sorted(ESC_CHANGED) and \
        all(changed.get(k) == v for k, v in ESC_CHANGED.items())
    c["kept_note"] = len(exl) == 3 and exl[2].get("note") == ESC_KEPT_NOTE
    disk = os.path.join(root, "rando", "last.json")
    try:
        on_disk = json.load(open(disk, encoding="utf-8"))
    except (OSError, ValueError):
        on_disk = None
    c["disk_last"] = bool(changed) and on_disk == changed
    keep_clicks = [e for e in named("click") if e.get("target") == "next:btn:keep"]
    last_keep = idx[id(keep_clicks[-1])] if keep_clicks else len(events)
    guesses = [e for e in events[last_keep:] if e.get("event") == "prebuild_start"]
    guess = guesses[-1] if guesses else None
    done = next((e for e in events[last_keep:] if e.get("event") == "prebuild_done" and guess and
                 e.get("id") == guess.get("id")), None)
    try:
        gtext = json.loads((guess or {}).get("text") or "null") or {}
    except ValueError:
        gtext = {}
    out["next_guess_id"] = (guess or {}).get("id")
    c["next_guess"] = bool(guess) and all(gtext.get(k) == v for k, v in ESC_CHANGED.items()) and \
        bool(done) and done.get("ok") is True and guess.get("id") != laid_id
    allowed = {laid_id} | {e.get("id") for e in after if e.get("event") == "prebuild_start"}
    c["runs_left_ok"] = bool(laid_id) and laid_id in left and set(left) <= allowed
    out["verdict"] = "PASS" if all(c.get(k) for k in ESC_CHECKS) else "FAIL"
    return out


PRESET_CHECKS = ("hook", "steps_known", "expects_ok", "light_values", "wild_values", "light_after_wild",
                 "copy_is_the_values", "paste_copied_equal", "made_code_equal", "typo_refused")
ESCFIT_CHECKS = ("hook", "steps_known", "game_laid_first", "this_run_full", "keep_on_screen", "keep_clicked")


def this_run_count(rows: list[dict], answer: dict) -> int:
    """the lines This run lists for this answer (rando_page.rs RandoForm::changed): every shown row but Randomizer
    and the seed whose value is not its default (a switch from the row it drives)."""
    n = 0
    for r in rows:
        if r.get("hidden") or r["key"] in ("randomizer", "seed"):
            continue
        d = r.get("drives")
        if d:
            v = answer.get(d["key"], d["off"]) != d["off"]
        elif r.get("page_only") or r["key"] not in answer:
            continue
        else:
            v = answer[r["key"]]
        n += v != r["default"]
    return n


def judge_p4(events: list[dict], seal: bool, scenario: str = "p4", rows: list[dict] | None = None) -> dict:
    """Round 74 (P4): the preset buttons, the Share code field and the Esc window's fit, from the hook's log (pure
    apart from the live schema; self-tested). Scenario presets / escfit / p4 (SCENARIOS):
    hook               the exe has the FEF_PAGEBOT hook
    steps_known        the hook knew every step (no unknown_step, no rows_missing) and ran the whole script
    expects_ok         every expect step was ok in the run (the keys it names)
    light_values       after Light: the whole answer but the seed is the Light preset's (ingame.page_preset)
    wild_values        after Wild: the same for Wild
    light_after_wild   Light pressed after Wild gives exactly the first Light's answer text (seed included)
    copy_is_the_values the copied text is the code the field showed, and sharecode.py reads it back as exactly the
                       values (and the seed) the page had when Copy was pressed (the Rust encoder against the Python
                       decoder)
    paste_copied_equal after other values and another seed, the copied code pasted gives the values at Copy again,
                       the same text (the seed too), and the help line says the code was used
    made_code_equal    a code made by sharecode.py pasted into the page gives exactly the answer sharecode.py reads
                       from it, seed included (the Python encoder against the Rust decoder)
    typo_refused       that code with a typo changes nothing and the help line says "This code has a typo."
    game_laid_first    (escfit) a randomized game was laid before the Esc window opened
    this_run_full      (escfit) This run listed as many rows as the laid answer changes, at least THIS_RUN_FULL
    keep_on_screen     (escfit) Keep was drawn wholly on the hook's 800 x 480 screen
    keep_clicked       (escfit) the click on Keep landed: expect_last after it was ok (last.json written)"""
    need = {"presets": PRESET_CHECKS, "escfit": ESCFIT_CHECKS}.get(scenario) or \
        tuple(dict.fromkeys(PRESET_CHECKS + ESCFIT_CHECKS))
    out = {"checks": {}, "scenario_checks": list(need)}
    c = out["checks"]
    c["hook"] = bool(events) and events[0].get("event") == "hook"
    if not c["hook"]:
        out["verdict"] = "REFUSED: this exe has no FEF_PAGEBOT hook (build/r60/screens/plans/PAGEBOT_HOOK.md)"
        return out
    if rows is None:
        rows = schema(seal)
    _IG, S = _ig()
    game = "seal" if seal else "fates"
    named = lambda n: [e for e in events if e.get("event") == n]  # noqa: E731
    idx = {id(e): i for i, e in enumerate(events)}
    hook_steps = events[0].get("steps")
    want_steps = len(SCENARIOS.get(scenario, []))
    c["steps_known"] = not named("unknown_step") and not named("rows_missing") and \
        (hook_steps is None or hook_steps == want_steps)
    exp = named("expect")
    c["expects_ok"] = bool(exp) and all(e.get("ok") for e in exp)

    def parsed(e):
        try:
            return json.loads((e or {}).get("values") or "null") or {}
        except ValueError:
            return {}

    def no_seed(a):
        return {k: v for k, v in a.items() if k != "seed"}
    if scenario in ("presets", "p4"):
        e6 = (exp + [None] * 6)[:6]
        light, wild = preset_answer(rows, "light", seal), preset_answer(rows, "wild", seal)
        out["preset_answers"] = {"light": light, "wild": wild}
        c["light_values"] = bool(e6[0]) and no_seed(parsed(e6[0])) == light
        c["wild_values"] = bool(e6[1]) and no_seed(parsed(e6[1])) == wild
        c["light_after_wild"] = bool(e6[2]) and bool(e6[0]) and e6[2].get("values") == e6[0].get("values")
        clicks = named("click")
        copy = next((e for e in clicks if e.get("target") == "btn:share:copy"), None)
        copied = [e for e in named("copied") if copy and idx[id(e)] > idx[id(copy)]]
        text = (copied[0] if copied else {}).get("text")
        out["copied"] = text
        try:
            back = S.page_values(rows, text or "", game)
            back_answer = _IG.page_answers(rows, back, None if game == "fates" else game)
        except (S.ShareCodeError, ValueError) as err:
            back_answer, out["copied_error"] = None, str(err)
        c["copy_is_the_values"] = bool(copy) and bool(text) and text == copy.get("share") and \
            back_answer is not None and back_answer == parsed(copy)
        pastes = named("paste")
        pc = next((e for e in pastes if e.get("copied")), None)
        c["paste_copied_equal"] = bool(copy) and bool(pc) and bool(e6[3]) and pc.get("text") == text and \
            e6[3].get("values") == copy.get("values") and parsed(pc) != parsed(copy) and \
            e6[3].get("note") == SHARE_USED
        made = made_answer(rows, seal)
        out["made_code"] = made_code(rows, seal)
        c["made_code_equal"] = bool(e6[4]) and parsed(e6[4]) == made and e6[4].get("note") == SHARE_USED and \
            any(e.get("text") == out["made_code"] for e in pastes)
        c["typo_refused"] = bool(e6[5]) and bool(e6[4]) and e6[5].get("values") == e6[4].get("values") and \
            e6[5].get("note") == SHARE_TYPO and any(e.get("text") == made_code(rows, seal, typo=True) for e in pastes)
    if scenario in ("escfit", "p4"):
        laid = next(iter(named("laid")), None)
        answer = next(iter(named("answer")), None)
        opens = [e for e in named("esc") if e.get("window") == "open"]
        c["game_laid_first"] = bool(laid) and bool(laid.get("id")) and bool(opens) and idx[id(laid)] < idx[id(opens[0])]
        fit = next(iter(named("expect_target")), None)
        try:
            ans = json.loads((answer or {}).get("text") or "null") or {}
        except ValueError:
            ans = {}
        want = this_run_count(rows, ans) if ans else None
        out["this_run_lines"], out["this_run_expected"] = (fit or {}).get("this_run_lines"), want
        c["this_run_full"] = bool(fit) and want is not None and fit.get("this_run_lines") == want and \
            want >= THIS_RUN_FULL
        c["keep_on_screen"] = bool(fit) and fit.get("ok") is True and fit.get("target") == "next:btn:keep"
        out["keep_rect"] = (fit or {}).get("rect")
        keep = next((e for e in named("click") if e.get("target") == "next:btn:keep"), None)
        exl = [e for e in named("expect_last") if keep and idx[id(e)] > idx[id(keep)]]
        c["keep_clicked"] = bool(keep) and bool(exl) and exl[0].get("ok") is True
    out["verdict"] = "PASS" if all(c.get(k) for k in need) else "FAIL"
    return out


HELPERS_CHECKS = ("hook", "steps_known", "game_first", "opened", "before_default", "no_table_at_defaults",
                  "clicked", "changed_once", "after_saved", "table_written", "own_settings_file", "on_screen",
                  "closed", "ended", "real_settings_unchanged")


def judge_helpers(events: list[dict], data: str, real: tuple | None) -> dict:
    """Round 80 (S1 / H7): the Helpers rows save, from the hook's log (pure, self-tested). Scenario "helpers":
    hook / steps_known       the exe has the hook (and the Helpers steps: no unknown_step, all steps run)
    game_first               the original game was laid (Start game) before the Esc window opened
    opened / closed / ended  {"esc": "paused"} opened, {"esc": "close"} closed, the run ended by itself
    before_default           before any click the job's settings.toml reads normal / off ...
    no_table_at_defaults     ... with no [fates_helpers] table in it (nothing written at the defaults)
    clicked / changed_once   one click on a helpers: target (True hit On), and it changed the row (helpers_changed)
    after_saved / table_written   after it the file holds true_hit true (enemy_phase "normal") in [fates_helpers]
    own_settings_file        the file read is the job's own (below the job folder), never the owner's
    on_screen                True hit's On is drawn wholly on the 800 x 480 screen
    real_settings_unchanged  the owner's %APPDATA%\\zakuro\\settings.toml hashed the same before and after"""
    out = {"checks": {}}
    c = out["checks"]
    c["hook"] = bool(events) and events[0].get("event") == "hook"
    if not c["hook"]:
        out["verdict"] = "REFUSED: this exe has no FEF_PAGEBOT hook (build/r60/screens/plans/PAGEBOT_HOOK.md)"
        return out

    def named(name: str) -> list[dict]:
        return [e for e in events if e.get("event") == name]
    hook_steps = events[0].get("steps")
    c["steps_known"] = not named("unknown_step") and (hook_steps is None or hook_steps == len(HELPERS_STEPS))
    idx = {id(e): i for i, e in enumerate(events)}
    laid = named("laid")
    opens = [e for e in named("esc") if e.get("window") == "open" and e.get("what", "paused") == "paused"]
    closes = [e for e in named("esc") if e.get("window") == "closed"]
    c["game_first"] = bool(laid) and bool(opens) and idx[id(laid[0])] < idx[id(opens[0])]
    c["opened"] = len(opens) == 1
    c["closed"] = bool(closes) and bool(opens) and idx[id(closes[-1])] > idx[id(opens[0])]
    c["ended"] = bool(named("end"))
    exp = named("expect_settings")
    before = next((e for e in exp if e.get("mark") == "before"), None)
    after = next((e for e in exp if e.get("mark") == "after"), None)
    clicks = [e for e in named("click") if str(e.get("target", "")).startswith("helpers:")]
    changed = named("helpers_changed")
    c["before_default"] = bool(before) and before.get("ok") is True and \
        before.get("saved") == {"enemy_phase": "normal", "true_hit": False}
    c["no_table_at_defaults"] = bool(before) and before.get("table") is False
    c["clicked"] = len(clicks) == 1 and bool(before) and all(idx[id(k)] > idx[id(before)] for k in clicks)
    c["changed_once"] = len(changed) == 1 and (changed[-1].get("helpers") == HELPERS_SAVED)
    c["after_saved"] = bool(after) and after.get("ok") is True and after.get("saved") == HELPERS_SAVED and \
        bool(clicks) and idx[id(after)] > idx[id(clicks[-1])]
    c["table_written"] = bool(after) and after.get("table") is True
    job = os.path.dirname(os.path.abspath(data))
    files = [e.get("file") for e in exp]
    c["own_settings_file"] = bool(files) and all(
        f and os.path.normcase(os.path.abspath(f)).startswith(os.path.normcase(job) + os.sep) for f in files)
    fit = [e for e in named("expect_target") if e.get("target") == "helpers:opt:true_hit=on"]
    c["on_screen"] = bool(fit) and fit[0].get("ok") is True
    c["real_settings_unchanged"] = bool(real) and real[0] is not None and real[0] == real[1]
    out["saved"] = after.get("saved") if after else None
    out["settings_file"] = files[-1] if files else None
    out["scenario_checks"] = list(HELPERS_CHECKS)
    out["verdict"] = "PASS" if all(c.get(k) for k in HELPERS_CHECKS) else "FAIL"
    return out


NEWGAME_CHECKS = ("hook", "steps_known", "game_first", "opened", "before_default", "no_table_at_defaults",
                  "section_opened", "row_clicks", "changed_three_times", "set_saved", "back_saved", "table_written",
                  "file_rows_exact", "file_others_kept", "own_settings_file", "on_screen", "closed", "ended",
                  "real_settings_unchanged")


def sandbox_table(data: str) -> dict | None:
    """round 81: the [fates_helpers] table of the job's OWN settings.toml (<job>/appdata/zakuro/settings.toml, the
    APPDATA run() gives the game), read after the run; None when the file or the table is missing or unreadable"""
    import tomllib
    f = os.path.join(os.path.dirname(os.path.abspath(data)), "appdata", "zakuro", "settings.toml")
    try:
        with open(f, "rb") as fh:
            table = tomllib.load(fh).get("fates_helpers")
    except (OSError, ValueError):
        return None
    return table if isinstance(table, dict) else None


def judge_newgame(events: list[dict], data: str, real: tuple | None, final: dict | None | str = "read") -> dict:
    """Round 81 (S1): the New Game defaults rows save, from the hook's log and the job's own settings file (pure
    apart from reading that file; self-tested). Scenario "newgame":
    hook / steps_known       the exe has the hook and knew every step (no unknown_step, all steps run)
    game_first               the original game was laid (Start game) before the Esc window opened
    opened / closed / ended  {"esc": "paused"} opened once, {"esc": "close"} closed it, the run ended by itself
    before_default           before any click the file reads the defaults: no New Game key, True hit off ...
    no_table_at_defaults     ... and no [fates_helpers] table (nothing written at the defaults)
    section_opened           the "New Game defaults" line was clicked after "before" and before any row click
    row_clicks               exactly the three row clicks, in order (Battle animations Off, Enemy turn skip All,
                             Battle animations Game's choice), each after the line was opened
    changed_three_times      the opening click saved nothing; each row click saved once, the rows as expected
    set_saved / back_saved   the file read after the two set rows, and after the put-back, holds exactly those rows
    table_written            the file has its [fates_helpers] table at the end
    file_rows_exact          after the run the file holds exactly enemy_skip = "all" among the four New Game keys
    file_others_kept         ... and True hit off, enemy phase normal (nothing else changed in the table)
    own_settings_file        every file read is the job's own (below the job folder), never the owner's
    on_screen                the lowest row's last choice (HP bars On) is drawn wholly on the 800 x 480 screen
    real_settings_unchanged  the owner's %APPDATA%\\zakuro\\settings.toml hashed the same before and after
    final: the job file's [fates_helpers] table after the run ("read" = read it with sandbox_table(data))."""
    out = {"checks": {}}
    c = out["checks"]
    c["hook"] = bool(events) and events[0].get("event") == "hook"
    if not c["hook"]:
        out["verdict"] = "REFUSED: this exe has no FEF_PAGEBOT hook (build/r60/screens/plans/PAGEBOT_HOOK.md)"
        return out
    if final == "read":
        final = sandbox_table(data)

    def named(name: str) -> list[dict]:
        return [e for e in events if e.get("event") == name]
    hook_steps = events[0].get("steps")
    c["steps_known"] = not named("unknown_step") and (hook_steps is None or hook_steps == len(NEWGAME_STEPS))
    idx = {id(e): i for i, e in enumerate(events)}
    laid = named("laid")
    opens = [e for e in named("esc") if e.get("window") == "open" and e.get("what", "paused") == "paused"]
    closes = [e for e in named("esc") if e.get("window") == "closed"]
    c["game_first"] = bool(laid) and bool(opens) and idx[id(laid[0])] < idx[id(opens[0])]
    c["opened"] = len(opens) == 1
    c["closed"] = bool(closes) and bool(opens) and idx[id(closes[-1])] > idx[id(opens[0])]
    c["ended"] = bool(named("end"))
    exp = named("expect_settings")
    mark = {m: next((e for e in exp if e.get("mark") == m), None) for m in ("before", "set", "back")}
    before, setx, back = mark["before"], mark["set"], mark["back"]
    clicks = [e for e in named("click") if str(e.get("target", "")).startswith("helpers:")]
    section = [e for e in clicks if e.get("target") == "helpers:newgame:section"]
    rows = [e for e in clicks if e.get("target") != "helpers:newgame:section"]
    changed = named("helpers_changed")
    c["before_default"] = bool(before) and before.get("ok") is True and before.get("saved") == NEWGAME_BASE
    c["no_table_at_defaults"] = bool(before) and before.get("table") is False
    c["section_opened"] = len(section) == 1 and bool(before) and idx[id(section[0])] > idx[id(before)] and \
        all(idx[id(r)] > idx[id(section[0])] for r in rows)
    c["row_clicks"] = [e.get("target") for e in rows] == NEWGAME_ROW_CLICKS and bool(section) and \
        all(idx[id(r)] > idx[id(section[0])] for r in rows)
    # a save follows its click: one helpers_changed after each row click, none after the opening click alone
    after_click = []
    for i, k in enumerate(rows):
        stop = idx[id(rows[i + 1])] if i + 1 < len(rows) else len(events)
        after_click.append([e for e in changed if idx[id(k)] < idx[id(e)] < stop])
    c["changed_three_times"] = len(changed) == len(NEWGAME_CHANGES) and \
        [e.get("helpers") for e in changed] == NEWGAME_CHANGES and all(len(a) == 1 for a in after_click) and \
        bool(section) and not any(idx[id(section[0])] < idx[id(e)] < idx[id(rows[0])] for e in changed if rows)
    c["set_saved"] = bool(setx) and setx.get("ok") is True and setx.get("saved") == NEWGAME_SET and \
        len(rows) >= 2 and idx[id(setx)] > idx[id(rows[1])] and (len(rows) < 3 or idx[id(setx)] < idx[id(rows[2])])
    c["back_saved"] = bool(back) and back.get("ok") is True and back.get("saved") == NEWGAME_SAVED and \
        bool(rows) and idx[id(back)] > idx[id(rows[-1])]
    c["table_written"] = bool(back) and back.get("table") is True and isinstance(final, dict)
    fin = final if isinstance(final, dict) else {}
    c["file_rows_exact"] = isinstance(final, dict) and {k: fin[k] for k in NEW_GAME_KEYS if k in fin} == \
        NEWGAME_FILE_ROWS
    c["file_others_kept"] = isinstance(final, dict) and fin.get("true_hit", False) is False and \
        fin.get("enemy_phase", "normal") == "normal" and not (set(fin) - {"enemy_phase", "true_hit", *NEW_GAME_KEYS})
    job = os.path.dirname(os.path.abspath(data))
    files = [e.get("file") for e in exp]
    c["own_settings_file"] = bool(files) and all(
        f and os.path.normcase(os.path.abspath(f)).startswith(os.path.normcase(job) + os.sep) for f in files)
    fit = [e for e in named("expect_target") if e.get("target") == "helpers:opt:hp_bars=on"]
    c["on_screen"] = bool(fit) and fit[0].get("ok") is True
    c["real_settings_unchanged"] = bool(real) and real[0] is not None and real[0] == real[1]
    out["saved"] = back.get("saved") if back else None
    out["file_table"] = final if isinstance(final, dict) else None
    out["settings_file"] = files[-1] if files else None
    out["scenario_checks"] = list(NEWGAME_CHECKS)
    out["verdict"] = "PASS" if all(c.get(k) for k in NEWGAME_CHECKS) else "FAIL"
    return out


def selftest() -> tuple[int, int]:
    import tempfile
    ok = n = 0

    def check(cond, what):
        nonlocal ok, n
        n += 1
        ok += bool(cond)
        if not cond:
            print("FAIL", what)
    with tempfile.TemporaryDirectory() as t:
        data = os.path.join(t, "data")
        rd = os.path.join(data, "rando", TITLE, "runs", "B-1")
        os.makedirs(rd)
        open(os.path.join(rd, "patch.txt"), "w").write("p")
        good = [{"event": "hook", "ms": 0}, {"event": "prebuild_done", "id": "A-1", "ms": 100},
                {"event": "discarded", "id": "A-1", "ms": 150},
                {"event": "click", "target": "btn:start", "ms": 200, "page_values": '{"x":1}'},
                {"event": "answer", "text": '{"x":1}', "ms": 240},
                {"event": "laid", "id": "B-1", "ms": 260}, {"event": "avatar", "ms": 1500}]
        mk = lambda a, s, w: sha(os.path.join(rd, "patch.txt"))  # noqa: E731
        v = judge(good, data, False, mk)
        check(v["verdict"] == "PASS" and v["ms_start_to_avatar"] == 1300 and v["checks"]["under_2s"], ("good", v))
        check(judge([], data, False, mk)["verdict"].startswith("REFUSED"), "no hook refused")
        bad = [dict(e) for e in good]
        bad[4]["text"] = '{"x":2}'
        check(judge(bad, data, False, mk)["verdict"] == "FAIL", "answer differs from page values")
        check(judge(good[:2] + good[3:], data, False, mk)["verdict"] == "FAIL", "stale guess never discarded")
        check(judge(good[:2] + good[3:], data, False, mk, scenario="quick")["verdict"] == "PASS",
              "quick (timing) needs no stale guess")
        os.makedirs(os.path.join(data, "rando", TITLE, "runs", "A-1"))
        check(judge(good, data, False, mk)["verdict"] == "FAIL", "stale guess folder left")
        os.rmdir(os.path.join(data, "rando", TITLE, "runs", "A-1"))
        early = [good[0], good[1], good[2], good[5], good[3], good[4], good[6]]
        check(judge(early, data, False, mk)["verdict"] == "FAIL", "laid before Start game")
        check(judge(good, data, False, lambda a, s, w: "other")["verdict"] == "FAIL", "laid patch differs from fresh")
        late = [dict(e) for e in good]
        late[1]["ms"] = 300
        check(judge(late, data, False, mk)["verdict"] == "FAIL", "guess not finished before Start game")
    # round 72: the Esc window's own check list (judge_esc)
    with tempfile.TemporaryDirectory() as t:
        data = os.path.join(t, "data")
        runs = os.path.join(data, "rando", TITLE, "runs")
        os.makedirs(os.path.join(runs, "L-1"))
        os.makedirs(os.path.join(runs, "N-1"))
        open(os.path.join(runs, "L-1", "patch.txt"), "w").write("laid")
        start_vals = {"randomizer": True, "difficulty": "normal", "classes": True}
        kept_vals = dict(start_vals, **ESC_CHANGED)
        json.dump(kept_vals, open(os.path.join(data, "rando", "last.json"), "w"))
        mk = lambda a, s, w: sha(os.path.join(runs, "L-1", "patch.txt"))  # noqa: E731
        st = '{"randomizer":true,"difficulty":"normal","classes":true}'
        esc = [{"event": "hook", "ms": 0, "steps": len(SCENARIOS["esc"])},
               {"event": "prebuild_done", "id": "L-1", "ok": True, "ms": 10},
               {"event": "click", "target": "btn:start", "ms": 20},
               {"event": "answer", "text": st, "ms": 30}, {"event": "laid", "id": "L-1", "ms": 40},
               {"event": "esc", "window": "open", "ms": 50}, {"event": "wait_done", "wait": "next_open", "ms": 51},
               {"event": "click", "target": "next:opt:randomizer=off", "ms": 52},
               {"event": "esc", "window": "closed", "ms": 53},
               {"event": "esc", "window": "open", "ms": 54}, {"event": "wait_done", "wait": "next_open", "ms": 55},
               {"event": "expect_last", "ok": True, "last": dict(start_vals), "note": None, "ms": 56},
               {"event": "click", "target": "next:btn:keep", "ms": 57},
               {"event": "expect_last", "ok": True, "last": dict(start_vals), "note": ESC_KEPT_NOTE, "ms": 58},
               {"event": "click", "target": "next:btn:keep", "ms": 59},
               {"event": "expect_last", "ok": True, "last": dict(kept_vals), "note": ESC_KEPT_NOTE, "ms": 60},
               {"event": "prebuild_start", "id": "N-1", "text": json.dumps(kept_vals), "ms": 61},
               {"event": "prebuild_done", "id": "N-1", "ok": True, "ms": 62},
               {"event": "esc", "window": "closed", "ms": 63}, {"event": "end", "ms": 64}]
        v = judge(esc, data, False, mk, scenario="esc")
        check(v["verdict"] == "PASS" and v["kept_diff"] == sorted(ESC_CHANGED), ("esc good", v))
        check(judge_esc([], data, False, mk)["verdict"].startswith("REFUSED"), "esc: no hook refused")

        def bad(what, fn, mkf=mk):
            ev = [dict(e) for e in esc]
            fn(ev)
            r = judge_esc(ev, data, False, mkf)
            check(r["verdict"] == "FAIL", (what, r["checks"]))
        bad("lay after the window opened", lambda ev: ev.insert(8, {"event": "laid", "id": "X-1", "ms": 52}))
        bad("the unkept change is in last.json", lambda ev: ev[11].update(last=dict(start_vals, randomizer=False)))
        bad("keep with no change wrote other values", lambda ev: ev[13].update(last=dict(start_vals, classes=False)))
        bad("kept two rows", lambda ev: ev[15].update(last=dict(kept_vals, classes=False)))
        bad("no kept note", lambda ev: ev[15].update(note="Not kept yet: press Keep for next New Game."))
        bad("an expect_last not ok", lambda ev: ev[15].update(ok=False))
        bad("the guess is of the old values", lambda ev: ev[16].update(text=st))
        bad("the guess failed", lambda ev: ev[17].update(ok=False))
        bad("a step the hook did not know", lambda ev: ev.insert(19, {"event": "unknown_step", "ms": 63}))
        bad("the window never showed the part", lambda ev: ev.pop(10))
        bad("no randomized game before the window", lambda ev: ev[4].update(id=None))
        bad("the laid run differs from a fresh make", lambda ev: None, lambda a, s, w: "other")
        os.makedirs(os.path.join(runs, "Z-9"))
        bad("a run folder nobody made after the window opened", lambda ev: None)
        os.rmdir(os.path.join(runs, "Z-9"))
        json.dump(start_vals, open(os.path.join(data, "rando", "last.json"), "w"))
        bad("last.json on disk is not what Keep wrote", lambda ev: None)
        json.dump(kept_vals, open(os.path.join(data, "rando", "last.json"), "w"))
        check(judge_esc(esc, data, False, mk)["verdict"] == "PASS", "esc good again after the bad cases")
    # round 74: judge_p4 on invented logs (the live schema's rows, codes made by sharecode.py)
    IG, S = _ig()
    live = IG.schema()["rows"]
    for seal in (False, True):
        game = "seal" if seal else "fates"
        g = "seal" if seal else None
        steps = resolve(SCENARIOS["p4"], live, seal)
        check(len(steps) == len(SCENARIOS["p4"]) and not any(
            k in st for st in steps for k in ("expect_preset", "paste_made", "expect_made")), ("p4 resolved", seal))
        check(any(st.get("paste") == made_code(live, seal) for st in steps) and
              any(st.get("paste") == made_code(live, seal, typo=True) for st in steps), ("p4 pastes", seal))
        check(made_code(live, seal) != made_code(live, seal, typo=True), "the typo code differs")
        try:
            S.decode(live, made_code(live, seal, typo=True), game)
            check(False, "the typo code is refused")
        except S.ShareCodeError as err:
            check(err.kind == "check", ("typo kind", err.kind))
        prop = "prop1234"

        def ans_text(vals):
            return IG.answer_text(IG.page_answers(live, dict(vals, seed=vals.get("seed") or prop), g))
        light_v = IG.page_preset(live, {"seed": ""}, "light", g)
        wild_v = IG.page_preset(live, {"seed": ""}, "wild", g)
        light_t, wild_t = ans_text(light_v), ans_text(wild_v)
        wild_code = S.page_code(live, wild_v, prop, game)
        other_t = ans_text(dict(light_v, seed="rnd99"))
        made_t = IG.answer_text(made_answer(live, seal))
        everything, _turned = IG.page_everything(live, dict(made_answer(live, seal)), g)
        ev_answer = IG.page_answers(live, dict(everything, seed=MADE_SEED), g)
        n_lines = this_run_count(live, ev_answer)
        check(n_lines >= THIS_RUN_FULL, ("Randomize everything fills This run", n_lines))
        p4 = [{"event": "hook", "ms": 0, "steps": len(SCENARIOS["p4"])},
              {"event": "click", "target": "btn:preset:light", "values": "{}", "share": ""},
              {"event": "expect", "ok": True, "values": light_t, "note": "Light: x"},
              {"event": "click", "target": "btn:preset:wild", "values": light_t, "share": ""},
              {"event": "expect", "ok": True, "values": wild_t, "note": "Wild: x"},
              {"event": "expect", "ok": True, "values": light_t, "note": "Light: x"},
              {"event": "click", "target": "btn:share:copy", "values": wild_t, "share": wild_code},
              {"event": "copied", "text": wild_code},
              {"event": "paste", "text": wild_code, "copied": True, "values": other_t},
              {"event": "expect", "ok": True, "values": wild_t, "note": SHARE_USED},
              {"event": "paste", "text": made_code(live, seal), "copied": False, "values": "{}"},
              {"event": "expect", "ok": True, "values": made_t, "note": SHARE_USED},
              {"event": "paste", "text": made_code(live, seal, typo=True), "copied": False, "values": made_t},
              {"event": "expect", "ok": True, "values": made_t, "note": SHARE_TYPO},
              {"event": "click", "target": "btn:start", "values": "{}", "share": ""},
              {"event": "answer", "text": IG.answer_text(ev_answer)},
              {"event": "laid", "id": "L-1"},
              {"event": "esc", "window": "open"}, {"event": "wait_done", "wait": "next_open"},
              {"event": "expect_target", "target": "next:btn:keep", "ok": True, "rect": [1, 2, 3, 4],
               "this_run_lines": n_lines},
              {"event": "click", "target": "next:btn:keep", "values": "{}", "share": ""},
              {"event": "expect_last", "ok": True}, {"event": "esc", "window": "closed"}, {"event": "end"}]
        v = judge_p4(p4, seal, "p4", live)
        check(v["verdict"] == "PASS", ("p4 good", seal, v["checks"]))
        check(judge_p4([], seal, "p4", live)["verdict"].startswith("REFUSED"), "p4: no hook refused")
        pre = [e for e in p4[:14]]
        pre[0] = dict(pre[0], steps=len(SCENARIOS["presets"]))
        check(judge_p4(pre, seal, "presets", live)["verdict"] == "PASS", ("presets alone", seal))

        def bad_p4(what, fn, scen="p4"):
            ev = [dict(e) for e in p4]
            fn(ev)
            r = judge_p4(ev, seal, scen, live)
            check(r["verdict"] == "FAIL", (what, seal, r["checks"]))
        bad_p4("Light gave other values", lambda ev: ev[2].update(values=wild_t))
        bad_p4("Wild gave other values", lambda ev: ev[4].update(values=light_t))
        bad_p4("Light after Wild differs", lambda ev: ev[5].update(values=other_t))
        bad_p4("the copy is not the field's code", lambda ev: ev[7].update(text=made_code(live, seal)))
        bad_p4("the pasted copy gave other values", lambda ev: ev[9].update(values=other_t))
        bad_p4("the pasted copy was not used", lambda ev: ev[9].update(note=SHARE_TYPO))
        bad_p4("the page already had the copied values", lambda ev: ev[8].update(values=wild_t))
        bad_p4("the made code gave other values", lambda ev: ev[11].update(values=wild_t))
        bad_p4("the typo changed the values", lambda ev: ev[13].update(values=wild_t))
        bad_p4("the typo was not refused", lambda ev: ev[13].update(note=SHARE_USED))
        bad_p4("an expect was not ok", lambda ev: ev[2].update(ok=False))
        bad_p4("a step the hook did not know", lambda ev: ev.insert(3, {"event": "unknown_step"}))
        bad_p4("Keep off the screen", lambda ev: ev[19].update(ok=False))
        bad_p4("This run not full", lambda ev: ev[19].update(this_run_lines=n_lines - 1))
        bad_p4("the Keep click did not keep", lambda ev: ev[21].update(ok=False))
        bad_p4("no game laid before the window", lambda ev: ev.pop(16))
    rows = [{"key": "randomizer", "kind": "onoff", "all": True}, {"key": "seed", "kind": "seed"},
            {"key": "classes", "kind": "onoff", "all": True}, {"key": "trees", "kind": "choice", "choices": ["own", "any"],
                                                               "all": "own"}]
    st = resolve(SCENARIOS["agency"], rows)
    check({"click": "opt:trees=any"} in st and {"click": "opt:classes=off"} in st and
          st.index({"click": "row:trees"}) < st.index({"click": "opt:trees=any"}), ("resolve", st))
    # round 80: the Helpers rows save (judge_helpers), on an invented log of the patch-0037 hook
    check(resolve(SCENARIOS["helpers"], rows) == HELPERS_STEPS, "helpers: the steps go to the hook as written")
    with tempfile.TemporaryDirectory() as t:
        data = os.path.join(t, "job", "data")
        own = os.path.join(t, "job", "appdata", "zakuro", "settings.toml")
        hv = [{"event": "hook", "ms": 0, "steps": len(HELPERS_STEPS)},
              {"event": "page_open", "frame": 300},
              {"event": "click", "target": "btn:start", "mark": "start"},
              {"event": "answer", "text": '{"randomizer":false}'},
              {"event": "laid", "id": None, "frame": 320},
              {"event": "esc", "window": "open", "what": "paused"},
              {"event": "expect_settings", "ok": True, "saved": {"enemy_phase": "normal", "true_hit": False},
               "table": False, "file": own, "mark": "before"},
              {"event": "click", "target": "helpers:opt:true_hit=on", "mark": "true_hit",
               "helpers": {"enemy_phase": "normal", "true_hit": False}},
              {"event": "helpers_changed", "helpers": {"enemy_phase": "normal", "true_hit": True}},
              {"event": "expect_settings", "ok": True, "saved": HELPERS_SAVED, "table": True, "file": own,
               "mark": "after"},
              {"event": "expect_target", "target": "helpers:opt:true_hit=on", "ok": True, "rect": [1, 2, 3, 4]},
              {"event": "esc", "window": "closed", "what": "close"}, {"event": "end", "frame": 330}]
        same = ("abc", "abc")
        v = judge(hv, data, False, scenario="helpers", real=same)
        check(v["verdict"] == "PASS" and v["saved"] == HELPERS_SAVED, ("helpers good", v))
        check(judge_helpers([], data, same)["verdict"].startswith("REFUSED"), "helpers: no hook refused")

        def bad_h(what, fn, real=same, d=data):
            ev = [dict(e) for e in hv]
            fn(ev)
            r = judge_helpers(ev, d, real)
            check(r["verdict"] == "FAIL", (what, r["checks"]))
        bad_h("the owner's settings file changed", lambda ev: None, real=("abc", "abd"))
        bad_h("the owner's settings file not read", lambda ev: None, real=(None, None))
        bad_h("a table at the defaults", lambda ev: ev[6].update(table=True))
        bad_h("not the defaults before", lambda ev: ev[6].update(saved={"enemy_phase": "2x", "true_hit": False}))
        bad_h("True hit not saved", lambda ev: ev[9].update(saved={"enemy_phase": "normal", "true_hit": False}, ok=False))
        bad_h("no table after", lambda ev: ev[9].update(table=False))
        bad_h("a click changed nothing", lambda ev: ev.pop(8))
        bad_h("the file read is not the job's own", lambda ev: ev[9].update(file=os.path.join(t, "elsewhere.toml")))
        bad_h("On off the screen", lambda ev: ev[10].update(ok=False))
        bad_h("a second (4x) click", lambda ev: ev.insert(7, {"event": "click", "target": "helpers:opt:enemy_phase=4x"}))
        bad_h("the window opened before the game", lambda ev: ev.insert(1, ev.pop(5)))
        bad_h("a step the hook did not know", lambda ev: ev.insert(3, {"event": "unknown_step"}))
        bad_h("never closed", lambda ev: ev.pop(11))
        bad_h("did not end by itself", lambda ev: ev.pop(12))
        bad_h("the after check came before the clicks", lambda ev: ev.insert(7, ev.pop(9)))
    # round 81: the New Game defaults rows save (judge_newgame), on an invented log of the patch-0039 hook
    check(resolve(SCENARIOS["newgame"], rows) == NEWGAME_STEPS, "newgame: the steps go to the hook as written")
    check([s["click"] for s in NEWGAME_STEPS if str(s.get("click", "")).startswith("helpers:opt:")] ==
          NEWGAME_ROW_CLICKS, "newgame: the row clicks are the judged ones")
    with tempfile.TemporaryDirectory() as t:
        data = os.path.join(t, "job", "data")
        own = os.path.join(t, "job", "appdata", "zakuro", "settings.toml")
        base = dict(NEWGAME_BASE)
        ng = [{"event": "hook", "ms": 0, "steps": len(NEWGAME_STEPS)},                                       # 0
              {"event": "page_open", "frame": 300},                                                          # 1
              {"event": "click", "target": "btn:start", "mark": "start"},                                    # 2
              {"event": "answer", "text": '{"randomizer":false}'},                                           # 3
              {"event": "laid", "id": None, "frame": 320},                                                   # 4
              {"event": "esc", "window": "open", "what": "paused"},                                          # 5
              {"event": "expect_settings", "ok": True, "saved": base, "table": False, "file": own,
               "mark": "before"},                                                                            # 6
              {"event": "click", "target": "helpers:newgame:section", "mark": "open", "helpers": base},       # 7
              {"event": "click", "target": "helpers:opt:battle_animations=off", "helpers": base},            # 8
              {"event": "helpers_changed", "helpers": NEWGAME_CHANGES[0]},                                   # 9
              {"event": "click", "target": "helpers:opt:enemy_skip=all", "helpers": NEWGAME_CHANGES[0]},     # 10
              {"event": "helpers_changed", "helpers": NEWGAME_CHANGES[1]},                                   # 11
              {"event": "expect_settings", "ok": True, "saved": NEWGAME_SET, "table": True, "file": own,
               "mark": "set"},                                                                               # 12
              {"event": "click", "target": "helpers:opt:battle_animations=game", "helpers": NEWGAME_SET},    # 13
              {"event": "helpers_changed", "helpers": NEWGAME_CHANGES[2]},                                   # 14
              {"event": "expect_settings", "ok": True, "saved": NEWGAME_SAVED, "table": True, "file": own,
               "mark": "back"},                                                                              # 15
              {"event": "expect_target", "target": "helpers:opt:hp_bars=on", "ok": True, "rect": [1, 2, 3, 4],
               "mark": "on_screen"},                                                                         # 16
              {"event": "esc", "window": "closed", "what": "close"}, {"event": "end", "frame": 330}]          # 17 18
        same = ("abc", "abc")
        fin = dict(NEWGAME_SAVED)
        v = judge_newgame(ng, data, same, fin)
        check(v["verdict"] == "PASS" and v["saved"] == NEWGAME_SAVED, ("newgame good", v))
        check(judge_newgame([], data, same, fin)["verdict"].startswith("REFUSED"), "newgame: no hook refused")
        # the file read from the job folder itself (judge's own path: final = "read")
        check(judge(ng, data, False, scenario="newgame", real=same)["checks"]["file_rows_exact"] is False,
              "newgame: no job file, no pass")
        os.makedirs(os.path.dirname(own))
        with open(own, "w", encoding="utf-8") as fh:
            fh.write('[per_game.0004000000179800]\ntop_shape = "wide16x9"\n\n[fates_helpers]\nenemy_phase = '
                     '"normal"\ntrue_hit = false\nenemy_skip = "all"\n')
        check(sandbox_table(data) == NEWGAME_SAVED, ("newgame: sandbox_table", sandbox_table(data)))
        check(judge(ng, data, False, scenario="newgame", real=same)["verdict"] == "PASS", "newgame: judged from file")

        def bad_n(what, fn=lambda ev: None, real=same, final=None, d=data):
            ev = [dict(e) for e in ng]
            fn(ev)
            r = judge_newgame(ev, d, real, dict(fin) if final is None else final)
            check(r["verdict"] == "FAIL", (what, r["checks"]))
        # planted failures named by HOME_DESIGN 6: a missing key, a key left set, the real file's hash changed
        bad_n("the set key missing from the file", final=dict(NEWGAME_BASE))
        bad_n("a key left set in the file", final=dict(NEWGAME_SAVED, battle_animations="off"))
        bad_n("a key written at game's choice", final=dict(NEWGAME_SAVED, hp_bars="game"))
        bad_n("True hit changed in the file", final=dict(NEWGAME_SAVED, true_hit=True))
        bad_n("a stray key in the table", final=dict(NEWGAME_SAVED, danger_zone="on"))
        bad_n("no table in the file", final={})
        bad_n("the owner's settings file changed", real=("abc", "abd"))
        bad_n("the owner's settings file not read", real=(None, None))
        bad_n("a table at the defaults", lambda ev: ev[6].update(table=True))
        bad_n("a New Game key before any click", lambda ev: ev[6].update(saved=dict(base, map_speed="fast")))
        bad_n("the line never opened", lambda ev: ev.pop(7))
        bad_n("the line opened twice", lambda ev: ev.insert(8, dict(ev[7])))
        bad_n("a row clicked before the line opened", lambda ev: ev.insert(7, ev.pop(8)))
        bad_n("the put-back click missing", lambda ev: (ev.pop(14), ev.pop(13)))
        bad_n("an extra row click", lambda ev: ev.insert(13, {"event": "click", "target": "helpers:opt:hp_bars=off"}))
        bad_n("the opening click saved", lambda ev: ev.insert(8, {"event": "helpers_changed", "helpers": base}))
        bad_n("a row click saved nothing", lambda ev: ev.pop(11))
        bad_n("a row click saved twice", lambda ev: ev.insert(10, dict(ev[9])))
        bad_n("the set rows not saved", lambda ev: ev[12].update(ok=False, saved=NEWGAME_CHANGES[0]))
        bad_n("the put-back not saved", lambda ev: ev[15].update(ok=False, saved=NEWGAME_SET))
        bad_n("the set check came after the put-back", lambda ev: ev.insert(14, ev.pop(12)))
        bad_n("no table at the end", lambda ev: ev[15].update(table=False))
        bad_n("the file read is not the job's own", lambda ev: ev[15].update(file=os.path.join(t, "elsewhere.toml")))
        bad_n("HP bars On off the screen", lambda ev: ev[16].update(ok=False))
        bad_n("the window opened before the game", lambda ev: ev.insert(1, ev.pop(5)))
        bad_n("a step the hook did not know", lambda ev: ev.insert(3, {"event": "unknown_step"}))
        bad_n("the hook ran another step count", lambda ev: ev[0].update(steps=len(HELPERS_STEPS)))
        bad_n("never closed", lambda ev: ev.pop(17))
        bad_n("did not end by itself", lambda ev: ev.pop(18))
    return ok, n


def main(argv: list[str]) -> int:
    global TOP
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["calibrate", "run", "selftest", "judge"])
    ap.add_argument("--exe", default=os.path.join(TOP, "bin", "Fire Emblem Fates.exe"))
    ap.add_argument("--name", default="agency")
    ap.add_argument("--seal", action="store_true")
    ap.add_argument("--scenario", default="agency", choices=sorted(SCENARIOS))
    ap.add_argument("--frames", type=int, default=9000)
    ap.add_argument("--top", help="job folders below this (default build/r61/pagebot)")
    a = ap.parse_args(argv)
    if a.top:
        TOP = os.path.abspath(a.top)
        if not below_build(TOP):
            raise SystemExit("refused: --top not below build/")
    if a.cmd == "selftest":
        ok, n = selftest()
        print(f"pagebot selftest: {ok}/{n}")
        return 0 if ok == n else 1
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    if a.cmd == "calibrate":
        print(json.dumps(calibrate(), indent=1)[:3000])
        return 0
    if a.cmd == "judge":
        # round 61: the verdict again for a finished job folder (no game is started), e.g. after the fresh make
        # failed for a reason outside the game
        d = os.path.join(TOP, a.name)
        res = json.load(open(os.path.join(d, "result.json"), encoding="utf-8")) if os.path.isfile(
            os.path.join(d, "result.json")) else {"name": a.name, "seal": a.seal}
        events = [json.loads(ln) for ln in open(os.path.join(d, "pagebot.jsonl"), encoding="utf-8") if ln.strip()]
        res["events"] = len(events)
        res.update(judge(events, os.path.join(d, "data"), a.seal, scenario=res.get("scenario", a.scenario)))
        res["judged_again"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        json.dump(res, open(os.path.join(d, "result.json"), "w"), indent=1, ensure_ascii=False)
        print(json.dumps({k: v for k, v in res.items() if k != "steps"}, indent=1, ensure_ascii=False)[:4000])
        return 0 if res.get("verdict") == "PASS" else 1
    cal = os.path.join(TOP, "calibrate.json")
    if not os.path.isfile(cal):
        cal = CALIBRATE
    after = json.load(open(cal)).get("pick_to_avatar") if os.path.isfile(cal) else None
    res = run(a.exe, a.name, a.seal, a.scenario, a.frames, after)
    print(json.dumps({k: v for k, v in res.items() if k != "steps"}, indent=1, ensure_ascii=False)[:4000])
    return 0 if res.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
