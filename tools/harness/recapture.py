#!/usr/bin/env python3
"""Re-capture from a recorded session (docs/HARNESS.md 4.3, milestone H4b). Standard library only.

A session is a folder build/harness/sessions/<id>/ made by `PLAY.bat --capture` (tools/play/play.py)
or by `synth` below: session.json, start-save.zip (the save it started from) and input.rec (what
Zakuro's ZAKURO_RECORD wrote). This tool replays input.rec headless in the existing windowless runner
(engine/target/zakuro-test/release/examples/boot.exe, started with CREATE_NO_WINDOW, hardware
rasterizer as every headless run, risk 20) with ZAKURO_REPLAY, on a fresh copy of start-save.zip and
the current capture library, once with FE_READABLE=original and once with FE_READABLE=capture, saves
the state at one frame (ZAKURO_SAVE_AT) in both, and compares the two with headless.py's own
state_digest / compare_digests / compare_meta (imported, not copied). Equal: the session's records
can be re-captured whenever targets or readable code change. Different: DIVERGED, with a frame
bisection plan (`bisect` runs it): records are used only from before the divergence.

What Zakuro does, read from its source (engine/zakuro, v0.2.32, read only):
  * input.rec: first line "clock <ms since 1900>", then one line per change of input:
    "<frame> <buttons, hex> <circle x> <circle y> <touch x> <touch y> <tilt x> <tilt y>
    <c-stick x> <c-stick y>", the floats in Rust's Debug form, touch -1 -1 for none; frame 0 is the
    first frame the game ran; old recordings stop after the touch or the tilt
    (crates/zakuro-core/src/replay.rs:1-4, 20-48 Recorder, 58-95 Replay::open, 103-112 input).
  * the frontend (zakuro.exe) honours ZAKURO_RECORD (crates/zakuro/src/lib.rs:836-841, 868-875,
    1798-1799) and ZAKURO_REPLAY (lib.rs:843-850, 1744-1745); boot.exe honours ZAKURO_REPLAY only
    (crates/zakuro-core/examples/boot.rs:69-77: the replay's clock replaces ZAKURO_CLOCK;
    boot.rs:269-270: the frame's input, in place of ZAKURO_INPUT), not ZAKURO_RECORD (no such
    variable in boot.rs), so a recording is always made in the frontend.
  * boot.exe saves the state at the top of the frame loop, before that frame runs (boot.rs:233-241),
    so ZAKURO_SAVE_AT=F needs at least F+1 frames.

    python tools/harness/recapture.py plan SESSION              what would run (no game)
    python tools/harness/recapture.py run SESSION [--frames N] [--save-at F] [--live ab|a]
                                     [--determinism] [--expect-run RUN] [--timeout S]
    python tools/harness/recapture.py bisect SESSION --hi F [--lo 0] [--min-gap 1]
    python tools/harness/recapture.py synth --from-run RUN --session ID
                                     a synthetic session from a headless route run: its save and its
                                     ZAKURO_INPUT written as input.rec (the GPU check of this tool)

Writes only below build/harness/: runs/<name>/ (run.json, boot.log, capture summaries), the
report recapture/<session>.json and one PNG sheet per run in shots/<name>/; the savestates, PPMs,
scratch data and tmp folders are deleted after use (storage policy).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "play"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from gamecfg import GAME  # noqa: E402  (config/game.json: title id)
import headless as hl  # noqa: E402  (state_digest, compare_digests, strip_meta, BOOT, LIB, ...)
import play  # noqa: E402  (check_fresh, check_save_zip, extract_save_zip, copy_start_save)

Stop = hl.Stop
TITLE_HEX = f"{GAME.title_id_int:016X}"     # the save folder name (config/game.json title_id)
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
TAIL = 600          # frames run after the last change of input when the session gives no count
SHOT_TAIL = 10      # ZAKURO_SAVE_AT = frames - SHOT_TAIL by default, as the routes do

# boot.rs:668-690 (ZAKURO_INPUT names) with crates/zakuro-core/src/services/hid.rs:34-59 (bits)
BUTTONS = {
    "A": 1 << 0, "B": 1 << 1, "SELECT": 1 << 2, "START": 1 << 3, "RIGHT": 1 << 4, "LEFT": 1 << 5,
    "UP": 1 << 6, "DOWN": 1 << 7, "R": 1 << 8, "L": 1 << 9, "X": 1 << 10, "Y": 1 << 11,
    "ZL": 1 << 14, "ZR": 1 << 15, "CSRIGHT": 1 << 24, "CSLEFT": 1 << 25, "CSUP": 1 << 26,
    "CSDOWN": 1 << 27, "CRIGHT": 1 << 28, "CLEFT": 1 << 29, "CUP": 1 << 30, "CDOWN": 1 << 31,
}
HOLD = 6  # boot.rs:272-273: each ZAKURO_INPUT entry is held for frames start..start+6


# ------------------------------------------------------------------ input.rec
def parse_script(spec: str) -> list[tuple[int, int, tuple[int, int] | None]]:
    """ZAKURO_INPUT as boot.rs parse_input_script reads it (boot.rs:658-701): an entry with an
    unknown button or a bad number is dropped whole."""
    out = []
    for entry in spec.split(","):
        frame, sep, names = entry.strip().partition(":")
        if not sep:
            continue
        bits, touch, ok = 0, None, True
        for name in names.split("+"):
            name = name.strip()
            if name.startswith("@") and "x" in name:
                x, _, y = name[1:].partition("x")
                if x.isdigit() and y.isdigit():
                    touch = (int(x), int(y))
                    continue
                ok = False
                break
            if name.upper() not in BUTTONS:
                ok = False
                break
            bits |= BUTTONS[name.upper()]
        if ok and frame.strip().isdigit():
            out.append((int(frame), bits, touch))
    return out


def script_input(entries, frame: int) -> tuple:
    """The input boot.rs gives frame `frame` from a script (boot.rs:271-285): held buttons OR'ed, the
    first held touch, the circle pad and C-stick pushed all the way by their direction buttons."""
    held = [e for e in entries if e[0] <= frame < e[0] + HOLD]
    bits = 0
    for e in held:
        bits |= e[1]
    touch = next((e[2] for e in held if e[2] is not None), None)

    def axis(plus: str, minus: str) -> float:
        return float(bool(bits & BUTTONS[plus])) - float(bool(bits & BUTTONS[minus]))
    return (bits, axis("CRIGHT", "CLEFT"), axis("CUP", "CDOWN"), touch, (0.0, 0.0),
            axis("CSRIGHT", "CSLEFT"), axis("CSUP", "CSDOWN"))


def rust_f32(x: float) -> str:
    """Rust's {:?} of the f32 values a script makes (-1, 0, 1) and simple fractions: 1.0, -0.5."""
    return repr(float(x))


def rec_line(frame: int, state: tuple) -> str:
    bits, cx, cy, touch, tilt, sx, sy = state
    tx, ty = touch if touch is not None else (-1, -1)
    return (f"{frame} {bits:x} {rust_f32(cx)} {rust_f32(cy)} {tx} {ty} {rust_f32(tilt[0])} {rust_f32(tilt[1])} "
            f"{rust_f32(sx)} {rust_f32(sy)}")


def route_to_rec(spec: str, frames: int, clock: int) -> str:
    """input.rec text that makes boot.exe's ZAKURO_REPLAY give every frame the input its ZAKURO_INPUT
    would (as Recorder::record writes it: a line when the input differs from the last one, the
    first frame always)."""
    entries = parse_script(spec)
    lines, last = [f"clock {clock}"], None
    for frame in range(frames):
        state = script_input(entries, frame)
        if state != last:
            lines.append(rec_line(frame, state))
            last = state
    return "\n".join(lines) + "\n"


def parse_rec(text: str) -> dict:
    """Checks input.rec as Replay::open does (replay.rs:58-95): {clock, changes, last_frame}."""
    lines = text.splitlines()
    if not lines:
        raise Stop("input.rec: empty")
    first = lines[0]
    if not first.startswith("clock ") or not first[6:].strip().isdigit():
        raise Stop("input.rec: no clock on the first line")
    changes = []
    for n, line in enumerate(lines[1:], 2):
        f = line.split()
        if len(f) not in (6, 8, 10):
            raise Stop(f"input.rec line {n}: {len(f)} fields (6, 8 or 10 expected)")
        try:
            frame = int(f[0])
            int(f[1], 16)
            for v in f[2:4] + f[6:]:
                float(v)
            int(f[4]), int(f[5])
        except ValueError:
            raise Stop(f"input.rec line {n}: not a recording line: {line!r}")
        if changes and frame < changes[-1]:
            raise Stop(f"input.rec line {n}: frame {frame} before {changes[-1]}")
        changes.append(frame)
    return {"clock": int(first[6:].strip()), "changes": changes, "last_frame": changes[-1] if changes else 0}


# ------------------------------------------------------------------ sessions
def session_dir(sid: str, build: str = hl.BUILD) -> str:
    if not NAME.fullmatch(sid or ""):
        raise Stop(f"session {sid}: letters, digits, _ . - only")
    path = os.path.join(build, "sessions", sid)
    if not hl.below(path, os.path.join(build, "sessions")):
        raise Stop(f"{path}: not below build/harness/sessions/")
    return path


def load_session(sid: str, build: str = hl.BUILD) -> dict:
    """A session folder, checked: session.json, input.rec (parsed as Replay::open would), start-save.zip
    (a PLAY save zip)."""
    folder = session_dir(sid, build)
    paths = {k: os.path.join(folder, n) for k, n in
             (("json", "session.json"), ("rec_path", "input.rec"), ("save", "start-save.zip"))}
    for path in paths.values():
        if not os.path.isfile(path):
            raise Stop(f"session {sid}: no {os.path.basename(path)} in {hl.rel(folder)}")
    with open(paths["json"], encoding="utf-8") as fh:
        meta = json.load(fh)
    with open(paths["rec_path"], encoding="utf-8") as fh:
        rec = parse_rec(fh.read())
    play.check_save_zip(Path(paths["save"]))
    return {"id": sid, "folder": folder, "meta": meta, "clock": rec["clock"], "changes": rec["changes"],
            "last_frame": rec["last_frame"], **paths}


def replay_env(settings: dict, data_dir: str, tmp_dir: str, run_dir: str, mode: str, live: str, rec: str,
               lib: str, state_file: str, save_at: int, build: str = hl.BUILD, dump: bool = True) -> dict:
    """boot.exe's environment for one replay. Inherited ZAKURO_ / FE_ settings are dropped (a stray
    ZAKURO_INPUT, ZAKURO_LOAD or FE_CAPTURE_ONLY would change the run). The session's Zakuro settings
    that reach the game are passed on: language, nickname (boot.exe derives the console id from it,
    boot.rs:22-27, so the owner's own console id is NOT reproduced), enhancements, resolution and the
    3D slider (ZAKURO_3D, boot.rs:57-59; the frontend writes settings.slider_3d() to the shared page
    every frame, crates/zakuro/src/lib.rs:1282-1286). dump=False leaves out ZAKURO_DUMP_AT (no PPMs,
    so no PNG sheet: bisection probes)."""
    if mode not in ("original", "capture"):
        raise Stop(f"mode {mode}: original or capture")
    for d in (data_dir, tmp_dir, run_dir):
        if not hl.below(d, build):
            raise Stop(f"{d}: not below build/harness/")
    env = hl.child_env()  # also drops the options file's path (FE_OPTIONS, FEF_OPTIONS: OPTIONS_WIRING section 6)
    env.update(ZAKURO_DATA=data_dir, TMP=tmp_dir, TEMP=tmp_dir, ZAKURO_RECOMPILED=lib,
               ZAKURO_RASTERIZER="hardware", ZAKURO_REPLAY=rec, ZAKURO_SAVE_AT=f"{save_at}:{state_file}",
               FE_READABLE=mode)
    if dump:
        env["ZAKURO_DUMP_AT"] = str(save_at)
    if settings.get("language_code") is not None:
        env["ZAKURO_LANGUAGE"] = str(int(settings["language_code"]))
    if settings.get("nickname"):
        env["ZAKURO_NICK"] = str(settings["nickname"])
    if settings.get("enhancements"):
        env["ZAKURO_ENHANCE"] = ",".join(settings["enhancements"])
    if settings.get("resolution") not in (None, "", 0):
        env["ZAKURO_RESOLUTION"] = str(int(settings["resolution"]))
    if settings.get("new3ds"):
        env["ZAKURO_NEW3DS"] = "1"
    try:
        slider = float(settings.get("slider_3d") or 0.0)
    except (TypeError, ValueError):
        raise Stop(f"session slider_3d {settings.get('slider_3d')!r} is not a number")
    if slider > 0:
        env["ZAKURO_3D"] = repr(min(1.0, slider))
    if mode == "capture":
        env.update(FE_CAPTURE_DIR=run_dir, FE_CAPTURE_LIVE=live, FE_CAPTURE_LATE="1")
    return env


def boot_runner(cmd: list[str], env: dict, cwd: str, log_path: str, timeout: float) -> int:
    """The only place a process starts: boot.exe, windowless (CREATE_NO_WINDOW)."""
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        try:
            return subprocess.run(cmd, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout,
                                  creationflags=hl.CREATE_NO_WINDOW if os.name == "nt" else 0).returncode
        except subprocess.TimeoutExpired:
            return -1


def run_one(session: dict, name: str, mode: str, frames: int, save_at: int, live: str = "ab", *,
            rom: str, boot: str, lib: str, runner=boot_runner, timeout: float = 3600,
            build: str = hl.BUILD, say=print, dump: bool = True) -> dict:
    """One replay of the session. Returns run.json's content plus "_meta" (the stripped metadata
    section, kept in memory only for compare_meta)."""
    if not NAME.fullmatch(name):
        raise Stop(f"run name {name}: letters, digits, _ . - only")
    if not 0 < save_at < frames:
        raise Stop(f"save_at {save_at} must lie inside the run of {frames} frames")
    data_dir, tmp_dir, run_dir = (os.path.join(build, d, name) for d in ("data", "tmp", "runs"))
    for d in (data_dir, tmp_dir, run_dir):
        if not hl.below(d, build):
            raise Stop(f"{d}: not below build/harness/")
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)
    laid = play.extract_save_zip(Path(session["save"]), Path(data_dir) / "user")
    state_file = os.path.join(tmp_dir, "state.bin")
    env = replay_env(session["meta"].get("settings") or {}, data_dir, tmp_dir, run_dir, mode, live,
                     session["rec_path"], lib, state_file, save_at, build, dump)
    log_path = os.path.join(run_dir, "boot.log")
    started = time.time()
    rc = runner([boot, rom, str(frames)], env, tmp_dir, log_path, timeout)
    secs = round(time.time() - started, 1)
    text = ""
    if os.path.isfile(log_path):
        with open(log_path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    m = re.search(r"outcome:\s+(\w+) after (\d+) frames", text)
    instr = re.search(r"^instructions:\s+(\d+)", text, re.M)
    result = {"source": "replay", "session": session["id"], "session_kind": session["meta"].get("kind"),
              "run": name, "mode": mode,
              "live": live if mode == "capture" else None, "exit_code": rc, "seconds": secs,
              "outcome": m.group(1) if m else None, "frames": int(m.group(2)) if m else None,
              "instructions": int(instr.group(1)) if instr else None, "frames_asked": frames,
              "save_files": laid, "library": hl.rel(lib), "rasterizer": "hardware",
              "replay": hl.rel(session["rec_path"]), "replay_clock": session["clock"],
              "env": {k: v for k, v in env.items() if k.startswith(("ZAKURO_LANGUAGE", "ZAKURO_NICK",
                                                                     "ZAKURO_ENHANCE", "ZAKURO_RESOLUTION",
                                                                     "ZAKURO_NEW3DS", "ZAKURO_3D", "FE_"))
                      and k != "FE_CAPTURE_DIR"}}
    meta = None
    if os.path.isfile(state_file):
        with open(state_file, "rb") as fh:
            data = fh.read()
        own = [data_dir, name]
        result["state_frame"] = save_at
        result["state_bytes"] = len(data)
        try:
            result["state"] = hl.state_digest(data, own)
            meta = hl.strip_meta(hl.state_sections(data)[1][0], own)
        except ValueError as error:
            result["state_error"] = str(error)
        os.remove(state_file)
    sheet = None
    if any(n.endswith(".ppm") for n in os.listdir(tmp_dir)):
        sheet = hl.contact_sheet(tmp_dir, [save_at], os.path.join(build, "shots", name, "checkpoints.png"))
    result["shots"] = hl.rel(sheet) if sheet else None
    result["fe_capture_log"] = [ln for ln in text.splitlines() if ln.startswith("[fe-capture]")][:40]
    result["saves_after"] = save_hashes(os.path.join(data_dir, "user"))
    with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    shutil.rmtree(data_dir, ignore_errors=True)
    say(f"[{name}] {mode}: exit {rc}, {result['outcome']} after {result['frames']} frames in {secs} s, state "
        f"{'memory ' + result['state']['memory'][:16] if 'state' in result else 'MISSING'}")
    result["_meta"] = meta
    return result


def save_hashes(user_dir: str) -> dict:
    """{path below user/: sha256} of the game's save files (savedata/<title>, extdata) in a Zakuro
    user folder: what the game wrote, for comparing a replay with the session it replays."""
    out = {}
    for top in (os.path.join(user_dir, "savedata"), os.path.join(user_dir, "extdata")):
        for here, _, files in os.walk(top):
            for f in files:
                path = os.path.join(here, f)
                name = os.path.relpath(path, user_dir).replace(os.sep, "/")
                if name.startswith("savedata/") and not name.startswith(f"savedata/{TITLE_HEX}"):
                    continue
                with open(path, "rb") as fh:
                    out[name] = hashlib.sha256(fh.read()).hexdigest()
    return out


def session_fidelity(session: dict, original: dict) -> dict:
    """An owner session's own data/user (what the game saved while the owner played) against the
    original replay's save files. The only check that a frontend recording replays the same in
    boot.exe (console id, audio draining and the frontend's frame loop differ, HARNESS.md 4.3)."""
    user = os.path.join(session["folder"], "data", "user")
    if not os.path.isdir(user):
        return {"verdict": "NOT-CHECKED", "why": "the session has no data/user (synthetic session)"}
    want, got = save_hashes(user), original.get("saves_after") or {}
    differ = sorted(n for n in set(want) | set(got) if want.get(n) != got.get(n))
    if not differ:
        return {"verdict": "SAVES-EQUAL", "files": len(want),
                "why": "the replay wrote the same save files the session did"}
    return {"verdict": "SAVES-DIFFER", "differ": differ[:40],
            "why": "the replay did not reproduce the session's saves (or ran too few frames to reach the "
                   "in-game save): the session does not replay faithfully in boot.exe"}


def usable(r: dict) -> bool:
    return r.get("outcome") == "Completed" and "state" in r


def compare_runs(a: dict, b: dict) -> tuple[bool, str]:
    return hl.compare_digests(a["state"], b["state"], a.get("_meta"), b.get("_meta"))


def bisection_plan(sid: str, lo: int, hi: int, changes: list[int], min_gap: int = 1) -> dict:
    """How to find the first frame where capture and original part: states are equal at lo (frame 0
    is before anything ran) and differ at hi. Each probe is one original and one capture replay up
    to frame m (ZAKURO_SAVE_AT=m, m+1 frames); about log2((hi-lo)/min_gap) probes."""
    span = max(1, hi - lo)
    steps = max(1, math.ceil(math.log2(max(2, span / max(1, min_gap)))))
    m = (lo + hi) // 2
    inside = [f for f in changes if lo <= f < hi]
    return {
        "lo": lo, "hi": hi, "min_gap": min_gap, "probes_max": steps, "first_probe": m,
        "input_changes_inside": len(inside),
        "auto": f"python tools/harness/recapture.py bisect {sid} --lo {lo} --hi {hi} --min-gap {min_gap}",
        "manual_probe": f"python tools/harness/recapture.py run {sid} --save-at {m} --frames {m + 1}",
        "text": (f"States are taken as equal at frame {lo} and different at frame {hi} (`bisect` probes both "
                 f"first). Probe the middle frame m "
                 f"(first {m}): replay original and capture to m (ZAKURO_SAVE_AT=m, m+1 frames) and compare; "
                 f"equal -> lo=m, different -> hi=m; at most {steps} probes until hi-lo <= {min_gap}. "
                 f"The divergence happens while frames lo..hi-1 run; only records from runs that stop at "
                 f"lo (run --frames lo+1 --save-at lo) are used, and the function called in those frames "
                 f"is the first suspect ({len(inside)} input changes lie in the range now)."),
    }


def resolve(rom: str | None, boot: str | None, lib: str | None, fresh) -> tuple[str, str, str, str]:
    lib = lib or hl.LIB
    boot = boot or hl.BOOT
    if not os.path.isfile(boot):
        raise Stop(f"no {hl.rel(boot)} (the existing zakuro-test build)")
    if not os.path.isfile(lib):
        raise Stop(f"no library {hl.rel(lib)}: run tools/harness/build.py")
    ok, line = fresh()
    if not ok:
        raise Stop(f"the capture library is not fresh ({line}): rebuild it with tools/harness/build.py first")
    return rom or hl.find_rom(), boot, lib, line


def frames_for(session: dict, frames: int | None, save_at: int | None, tail: int = TAIL) -> tuple[int, int]:
    meta = session["meta"]
    frames = frames or meta.get("frames") or session["last_frame"] + tail
    save_at = save_at if save_at is not None else meta.get("save_at") or frames - SHOT_TAIL
    if not 0 < save_at < frames:
        raise Stop(f"save_at {save_at} must lie inside the run of {frames} frames")
    return int(frames), int(save_at)


def recapture(sid: str, frames: int | None = None, save_at: int | None = None, live: str = "ab",
              determinism: bool = False, expect_run: str | None = None, *, runner=boot_runner,
              rom: str | None = None, boot: str | None = None, lib: str | None = None, fresh=play.check_fresh,
              timeout: float = 3600, build: str = hl.BUILD, say=print) -> dict:
    """original and capture replays of a session; the verdict and report (recapture/<sid>.json)."""
    session = load_session(sid, build)
    rom, boot, lib, fresh_line = resolve(rom, boot, lib, fresh)
    frames, save_at = frames_for(session, frames, save_at)
    kw = dict(rom=rom, boot=boot, lib=lib, runner=runner, timeout=timeout, build=build, say=say)
    runs = {"original": run_one(session, f"{sid}-orig", "original", frames, save_at, **kw)}
    if determinism:
        runs["original2"] = run_one(session, f"{sid}-orig2", "original", frames, save_at, **kw)
    runs["capture"] = run_one(session, f"{sid}-cap", "capture", frames, save_at, live, **kw)
    report = {"session": sid, "frames": frames, "save_at": save_at, "library_fresh": fresh_line,
              "runs": {k: f"build/harness/runs/{v['run']}/run.json" for k, v in runs.items()},
              "input_changes": len(session["changes"]), "clock": session["clock"]}
    bad = [k for k, v in runs.items() if not usable(v)]
    if bad:
        report.update(verdict="FAILED", why=f"{', '.join(bad)}: no state at frame {save_at} or the run did not complete "
                                            f"({'; '.join(str(runs[k].get('outcome')) for k in bad)})")
    else:
        if determinism:
            same, line = compare_runs(runs["original"], runs["original2"])
            report["determinism"] = line
            if not same:
                report.update(verdict="NOT-DETERMINISTIC",
                              why="two original replays differ: use the session's savestate checkpoints as "
                                  "starting points instead (HARNESS.md 4.3, last point)")
        if "verdict" not in report:
            same, line = compare_runs(runs["original"], runs["capture"])
            report["compare"] = line
            if same:
                report["verdict"] = "SAME"
            else:
                report["verdict"] = "DIVERGED"
                report["bisection"] = bisection_plan(sid, 0, save_at, session["changes"])
    if expect_run and usable(runs["original"]):
        report["expect_run"] = expected(expect_run, runs["original"], save_at, build)
    report["session_fidelity"] = session_fidelity(session, runs["original"])
    folder = os.path.join(build, "recapture")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"{sid}.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    say(f"recapture {sid}: {report['verdict']}" + (f" ({report.get('compare') or report.get('why')})"))
    return report


def expected(run: str, original: dict, save_at: int, build: str) -> dict:
    """The replay against a headless route run (synthetic sessions): same frame, same guest memory?"""
    path = os.path.join(build, "runs", run, "run.json")
    try:
        with open(path, encoding="utf-8") as fh:
            want = json.load(fh)
    except (OSError, ValueError):
        return {"run": run, "verdict": "NO-RUN", "why": f"no {hl.rel(path)}"}
    if want.get("state_frame") != save_at or "state" not in want:
        return {"run": run, "verdict": "NOT-COMPARABLE",
                "why": f"its state is at frame {want.get('state_frame')}, the replay's at {save_at}"}
    same, line = hl.compare_digests(want["state"], original["state"])
    return {"run": run, "verdict": "SCRIPT-EQUIVALENT" if same else "SCRIPT-DIFFERS", "compare": line,
            "library_sha256_then": want.get("library_sha256")}


def bisect(sid: str, hi: int, lo: int = 0, min_gap: int = 1, live: str = "ab", *, runner=boot_runner,
           rom: str | None = None, boot: str | None = None, lib: str | None = None, fresh=play.check_fresh,
           timeout: float = 3600, build: str = hl.BUILD, say=print) -> dict:
    """Runs the bisection plan: the first frame range [lo, hi) in which capture parts from original.
    The endpoints are probed first (hi must differ; lo > 0 must match; frame 0 is before anything ran).
    Probes save no PPMs, and their run folders are deleted at the end: the report keeps each result."""
    session = load_session(sid, build)
    rom, boot, lib, _ = resolve(rom, boot, lib, fresh)
    if not 0 <= lo < hi:
        raise Stop(f"bisect needs 0 <= lo < hi (got {lo}, {hi})")
    kw = dict(rom=rom, boot=boot, lib=lib, runner=runner, timeout=timeout, build=build, say=say, dump=False)
    names: list[str] = []

    def probe(m: int) -> dict:
        a = run_one(session, f"{sid}-b{m}-orig", "original", m + 1, m, **kw)
        b = run_one(session, f"{sid}-b{m}-cap", "capture", m + 1, m, live, **kw)
        names.extend((a["run"], b["run"]))
        if not (usable(a) and usable(b)):
            return {"frame": m, "verdict": "FAILED"}
        same, line = compare_runs(a, b)
        return {"frame": m, "same": same, "compare": line}

    probes: list[dict] = []
    endpoints = [probe(hi)] + ([probe(lo)] if lo > 0 else [])
    report = None
    for e in endpoints:
        if e.get("verdict") == "FAILED":
            report = {"verdict": "FAILED", "why": f"probe at frame {e['frame']} failed"}
    if report is None and endpoints[0]["same"]:
        report = {"verdict": "NO-DIVERGENCE-AT-HI",
                  "why": f"original and capture are equal at frame {hi}: nothing to bisect below it"}
    if report is None and lo > 0 and not endpoints[1]["same"]:
        report = {"verdict": "DIVERGED-BEFORE-LO",
                  "why": f"original and capture differ already at frame {lo}: lower --lo"}
    while report is None and hi - lo > max(1, min_gap):
        m = (lo + hi) // 2
        result = probe(m)
        probes.append(result)
        if result.get("verdict") == "FAILED":
            report = {"verdict": "FAILED", "why": f"probe at frame {m} failed"}
            break
        lo, hi = (m, hi) if result["same"] else (lo, m)
    if report is None:
        report = {"verdict": "BISECTED",
                  "text": f"equal at frame {lo}, different at frame {hi}: the divergence happens while frames "
                          f"{lo}..{hi - 1} run; use records only from runs that stop at frame {lo}"}
    report = {"session": sid, **report, "lo": lo, "hi": hi, "endpoints": endpoints, "probes": probes}
    for name in names:   # storage policy: the report keeps every probe's result
        for top in ("runs", "shots"):
            path = os.path.join(build, top, name)
            if hl.below(path, build):
                shutil.rmtree(path, ignore_errors=True)
    folder = os.path.join(build, "recapture")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"{sid}-bisect.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    say(f"bisect {sid}: {report['verdict']} lo={report['lo']} hi={report['hi']} after {len(probes)} probes "
        f"(+{len(endpoints)} endpoint checks)")
    return report


def synth(from_run: str, sid: str, build: str = hl.BUILD, routes: dict | None = None) -> dict:
    """A synthetic session from a headless route run: the run's save (through PLAY's copy logic),
    its ZAKURO_INPUT as input.rec from headless.py's fixed clock. For the GPU check: replayed, it
    must reach the run's state (SCRIPT-EQUIVALENT), and original and capture must be SAME."""
    path = os.path.join(build, "runs", from_run, "run.json")
    try:
        with open(path, encoding="utf-8") as fh:
            run = json.load(fh)
    except (OSError, ValueError):
        raise Stop(f"no {hl.rel(path)}")
    for key in ("route", "input", "save_backup", "state_frame"):
        if run.get(key) in (None, ""):
            raise Stop(f"{hl.rel(path)} has no {key}")
    if run.get("cheat") or run.get("start_save_cheat"):  # docs/CHEATS.md: pokes happen between boot.exe stages,
        raise Stop(f"{hl.rel(path)} is a cheat run: not replayed as a session")  # which a session cannot replay
    if run.get("options_run") or run.get("start_save_options"):  # options track: scored apart, never a session
        raise Stop(f"{hl.rel(path)} is an options-track run: not replayed as a session")
    routes = routes if routes is not None else hl.load_routes()
    if run["route"] not in routes:
        raise Stop(f"route {run['route']} is not in routes.json")
    frames = int(routes[run["route"]]["frames"])
    folder = session_dir(sid, build)
    if os.path.exists(folder):
        raise Stop(f"session {sid} exists already; a session is never reused")
    save = Path(run["save_backup"])
    save = save if save.is_absolute() else Path(ROOT) / save
    os.makedirs(folder)
    try:
        play.copy_start_save(save, Path(folder))
        with open(os.path.join(folder, "input.rec"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(route_to_rec(run["input"], frames, int(hl.CLOCK)))
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    meta = {"session": sid, "kind": "synthetic", "from_run": from_run, "route": run["route"],
            "frames": frames, "save_at": int(run["state_frame"]), "expect_run": from_run,
            "start_save": "start-save.zip", "source": run["save_backup"],
            "settings": {"language_code": None, "nickname": None, "enhancements": [], "resolution": None},
            "about": "input.rec made from the route's ZAKURO_INPUT (recapture.py synth); headless defaults"}
    with open(os.path.join(folder, "session.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    return meta


def plan(sid: str, frames: int | None = None, save_at: int | None = None, build: str = hl.BUILD) -> dict:
    session = load_session(sid, build)
    frames, save_at = frames_for(session, frames, save_at)
    env = replay_env(session["meta"].get("settings") or {}, os.path.join(build, "data", f"{sid}-orig"),
                     os.path.join(build, "tmp", f"{sid}-orig"), os.path.join(build, "runs", f"{sid}-orig"),
                     "original", "ab", session["rec_path"], hl.LIB, os.path.join(build, "tmp", f"{sid}-orig", "state.bin"),
                     save_at, build)
    return {"session": sid, "kind": session["meta"].get("kind"), "clock": session["clock"],
            "input_changes": len(session["changes"]), "last_change": session["last_frame"],
            "frames": frames, "save_at": save_at,
            "env": {k: v for k, v in env.items() if k.startswith(("ZAKURO_", "FE_"))},
            "command": [hl.BOOT, "<rom>", str(frames)]}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("session")
    p.add_argument("--frames", type=int)
    p.add_argument("--save-at", type=int)
    r = sub.add_parser("run")
    r.add_argument("session")
    r.add_argument("--frames", type=int)
    r.add_argument("--save-at", type=int)
    r.add_argument("--live", choices=("a", "ab"), default="ab")
    r.add_argument("--determinism", action="store_true", help="a second original replay (run after the first) to check the replay repeats")
    r.add_argument("--expect-run", help="a headless run whose state the original replay must reach")
    r.add_argument("--timeout", type=float, default=3600)
    b = sub.add_parser("bisect")
    b.add_argument("session")
    b.add_argument("--hi", type=int, required=True)
    b.add_argument("--lo", type=int, default=0)
    b.add_argument("--min-gap", type=int, default=1)
    b.add_argument("--live", choices=("a", "ab"), default="ab")
    b.add_argument("--timeout", type=float, default=3600)
    s = sub.add_parser("synth")
    s.add_argument("--from-run", required=True)
    s.add_argument("--session", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "plan":
            out = plan(a.session, a.frames, a.save_at)
        elif a.cmd == "run":
            session = load_session(a.session, hl.BUILD)
            out = recapture(a.session, a.frames, a.save_at, a.live, a.determinism,
                            a.expect_run or session["meta"].get("expect_run"), timeout=a.timeout)
            return 0 if out["verdict"] == "SAME" else 1
        elif a.cmd == "bisect":
            out = bisect(a.session, a.hi, a.lo, a.min_gap, a.live, timeout=a.timeout)
            return 0 if out["verdict"] == "BISECTED" else 1
        else:
            out = synth(a.from_run, a.session)
        print(json.dumps(out, indent=1))
        return 0
    except (Stop, play.Stop) as e:
        print(f"recapture: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
