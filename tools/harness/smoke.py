#!/usr/bin/env python3
"""The headless SMOKE set (round 67, release part A, goal 5; docs/harness/SMOKE.md). Standard library only.

It replaces the hand-made round scripts that were copied forward from round to round (build/r6x/smoke/brk.py,
mkruns.py, classify.py, extra.py, and the memory compare of build/r62b/build/smoke/smoke.py + compare.py; they read
untracked drivers in build/r58 and build/r59). The set is config/harness/smoke_set.json (round 84, F-072: the Vanilla+ set; the Seal edition's 2 jobs are their own
set, config/seal/smoke_set.json, run with --set as part of the small Seal check, docs/seal/CHECK.md):

  * 1 randomizer run RE-MADE with today's code (Fates, every row on, the 'all1' answer), cache OFF;
  * 6 robot jobs: Birthright A011, Conquest B016, Revelation C012, each with the randomizer off and with
    the everything-on run laid as the loaded save's side file. Each job: chapter select from a base save, the
    preparations, the map (memory readback: every patch cell holds its NEW value, or its OLD value on the off run),
    one enemy looked at, the first enemy phase, a battle save, and its reload in a fresh server (units equal);
  * 1 memory compare: the installed game exe (frozen copy), randomizer off, the new-game replay for 5200 frames, the
    RAM hashed at boot and at frames 3000, 4600, 5200 and the end. A set may have no memory compare ("memory": null,
    as the Seal set: the compare boots Fates, so it lives in the Vanilla+ set only); its PASS line then says so.

Every input (frozen exe/boot-server/capture library, base saves, replay, answer file; the Seal set's mod copy) is a
COPY in build/fixtures/smoke/ (git-ignored, never game data in git), listed with its sha256 in smoke_set.json. A missing or
wrong-sha input is a FAIL with a plain message, never a skip. The ROM is found and checked by tools/paths.find_rom.

Runs: every task is its own process (no window: CREATE_NO_WINDOW; below-normal priority through subprocess flags,
never 'start /belownormal'), inside its own Windows job object (kill-the-tree; anything left dies with this
process), with APPDATA/LOCALAPPDATA/TMP and the game's data folder under the task's folder in the output dir.
build/STOP_ROUND is checked before every start and while running (everything is killed, exit 3). A visible window
from any task = everything is killed and the run FAILS. Each task has a timeout. --lanes N (default 2, at most 6;
round 84: 2 keeps a round's robot games at 3 or fewer beside one other robot lane) tasks at once. Nothing is ever
retried.

Baseline: the set's "baseline" file (config/harness/smoke_baseline.json; the Seal set's config/seal/smoke_baseline.json;
--baseline FILE overrides it): hashes and verdicts only (each run's patch sha, each job's verdict and sha256 of its
readback, the memory hashes). A mismatch is a FAIL that names the job and the frame. --write-baseline writes that
same file.

    python tools/harness/smoke.py fixtures [--refresh]     copy the inputs once into build/fixtures/smoke (copies)
    python tools/harness/smoke.py check                    inputs present with the right sha256? (no game)
    python tools/harness/smoke.py run [--out DIR] [--lanes N] [--write-baseline] [--baseline FILE] [--only a,b]
                                   [--bin DIR]
    python tools/harness/smoke.py --set config/seal/smoke_set.json run --lanes 2   the Seal edition's 2 jobs
          --bin DIR: run on a STAGED game exe / boot-server / capture library (round 68, the release command's
          engine step) instead of the frozen copies: each of 'Fire Emblem Fates.exe', 'boot-server.exe' and
          '0004000000179800.dll' found in DIR replaces its frozen input (the others stay frozen); the sha256 of
          every file used is listed in results.json ("bin"). DIR must be under build/ and never play/. The
          baseline is still compared (a mismatch is a FAIL for the owner to look at); --write-baseline is
          refused with --bin.
    python tools/harness/smoke.py record --jobs DIR --runs DIR --memory REPORT --out FILE
                                   a finished hand-made smoke (e.g. build/r66/smoke) judged by these rules
    python tools/harness/smoke.py --list                   the set: runs, jobs, memory compare, inputs
    python tools/harness/smoke.py selftest                 tests/test_smoke.py (synthetic: fake runner, no game)

Exit codes: 0 PASS (every job PASS, the memory compare PASS, and everything equal to the baseline);
1 FAIL (a job, the compare, an input, a window, a timeout, a baseline mismatch, or no baseline);
2 usage error; 3 build/STOP_ROUND (everything was killed); 4 PARTIAL: an --only run whose part passed (never 0,
because 0 means the whole set: 6/6 jobs and the memory compare; 2/2 for the Seal set).
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SET_FILE = os.path.join(ROOT, "config", "harness", "smoke_set.json")
BASELINE_FILE = os.path.join(ROOT, "config", "harness", "smoke_baseline.json")
STOP_FILE = os.path.join(ROOT, "build", "STOP_ROUND")
BUILD_TOP = os.path.join(ROOT, "build")
TITLE = "0004000000179800"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
BELOW_NORMAL = 0x00004000 if os.name == "nt" else 0
EXIT_PASS, EXIT_FAIL, EXIT_USAGE, EXIT_STOP, EXIT_PARTIAL = 0, 1, 2, 3, 4
LANES_DEFAULT, LANES_MAX = 2, 6     # round 84 (F-072): 2 by default (was 5; at most 3 robot games in a round)


# ------------------------------------------------------------------ small helpers
def rel(p: str) -> str:
    try:
        return os.path.relpath(p, ROOT).replace("\\", "/")
    except ValueError:
        return p


def below(p: str, top: str) -> bool:
    p, top = os.path.normcase(os.path.abspath(p)), os.path.normcase(os.path.abspath(top))
    return p == top or p.startswith(top.rstrip("\\/") + os.sep)


def sha256_file(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_sha(d: str) -> tuple[str, int]:
    """sha256 over every file below d: its path (relative, '/') and its own sha256, sorted by path"""
    rows = []
    for top, _dirs, files in os.walk(d):
        for fn in files:
            p = os.path.join(top, fn)
            rows.append(f"{os.path.relpath(p, d).replace(os.sep, '/')}\0{sha256_file(p)}\n")
    rows.sort()
    return hashlib.sha256("".join(rows).encode("utf-8")).hexdigest(), len(rows)


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=True, default=str).encode()).hexdigest()


def load_json(p: str):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(p: str, obj) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False, sort_keys=False)
        fh.write("\n")
    os.replace(tmp, p)


def load_set(path: str = SET_FILE) -> dict:
    cfg = load_json(path)
    for k in ("fixtures_dir", "inputs", "runs", "jobs", "memory"):
        if k not in cfg:
            raise SystemExit(f"{rel(path)}: no '{k}'")
    if cfg["memory"] is not None and not isinstance(cfg["memory"], dict):
        raise SystemExit(f"{rel(path)}: 'memory' must be the compare or null")
    if any(x.get("game") == "seal" for x in [*cfg["jobs"], *cfg["runs"].values()]) and not cfg["robot"].get("sealmod"):
        raise SystemExit(f"{rel(path)}: a Seal job or run needs robot.sealmod (the Seal set, config/seal/smoke_set.json)")
    return cfg


def memory_of(cfg: dict) -> dict | None:
    """the set's memory compare, or None (round 84: the Seal set has none; "memory": null)"""
    return cfg.get("memory") or None


def baseline_of(cfg: dict) -> str:
    """the set's baseline file: its "baseline" (repo-relative), else config/harness/smoke_baseline.json"""
    b = cfg.get("baseline")
    return os.path.join(ROOT, *b.split("/")) if b else BASELINE_FILE


def fixtures_top(cfg: dict, root: str = ROOT) -> str:
    return os.path.join(root, *cfg["fixtures_dir"].split("/"))


# ------------------------------------------------------------------ inputs
def input_path(cfg: dict, key: str, root: str = ROOT) -> str:
    spec = cfg["inputs"][key]
    if spec.get("staged_path"):  # --bin: a staged file under build/, repo-relative (bin_set; no private path kept)
        sp = spec["staged_path"]
        return sp if os.path.isabs(sp) else os.path.join(root, *sp.split("/"))
    return os.path.join(fixtures_top(cfg, root), *spec["file"].split("/"))


def bin_keys(cfg: dict) -> list[str]:
    """the inputs --bin may replace: the game exe of the memory compare, the robot's boot-server and library"""
    mem = memory_of(cfg)
    return ([mem["exe"]] if mem else []) + [cfg["robot"]["server"], cfg["robot"]["lib"]]


def bin_set(cfg: dict, bin_dir: str, root: str = ROOT) -> tuple[dict, dict, list[str]]:
    """(a copy of cfg whose binary inputs point at bin_dir's files with their own sha256, {key: what was used},
    problems). A file missing from bin_dir keeps its frozen copy; no file at all is a problem."""
    import copy
    new = copy.deepcopy(cfg)
    used, problems = {}, []
    bin_dir = os.path.abspath(bin_dir)
    play = os.path.join(root, "play")
    if not os.path.isdir(bin_dir):
        return new, used, [f"--bin {bin_dir}: no such folder"]
    if not below(bin_dir, os.path.join(root, "build")) or below(bin_dir, play):
        return new, used, [f"--bin {bin_dir}: must be a folder under build/ (never play/)"]
    for key in bin_keys(cfg):
        spec = new["inputs"][key]
        name = spec["file"].split("/")[-1]
        p = os.path.join(bin_dir, name)
        if os.path.isfile(p):
            sha = sha256_file(p)
            used[key] = {"file": rel(p), "sha256": sha, "frozen_sha256": spec["sha256"], "staged": True}
            spec["frozen_sha256"], spec["sha256"], spec["staged_path"] = (spec["sha256"], sha,
                                                                         os.path.relpath(p, root).replace(os.sep, "/"))
        else:
            used[key] = {"file": rel(input_path(cfg, key, root)), "sha256": spec["sha256"], "staged": False}
    if not any(u["staged"] for u in used.values()):
        problems.append(f"--bin {rel(bin_dir)}: none of " + ", ".join(
            cfg["inputs"][k]["file"].split("/")[-1] for k in bin_keys(cfg)) + " is in it")
    return new, used, problems


def check_inputs(cfg: dict, root: str = ROOT) -> tuple[dict, list[str]]:
    """{key: path} and the problems (a missing input or a wrong sha256 is a problem, never a skip)"""
    paths, problems = {}, []
    for key, spec in cfg["inputs"].items():
        p = input_path(cfg, key, root)
        paths[key] = p
        kind = spec.get("kind", "file")
        if kind == "tree":
            if not os.path.isdir(p):
                problems.append(f"input {key}: missing folder {rel(p)} (copy it once: python tools/harness/smoke.py "
                                f"fixtures)")
                continue
            got, n = tree_sha(p)
            if got != spec["sha256"] or n != spec.get("files", n):
                problems.append(f"input {key}: folder {rel(p)} has tree sha256 {got[:12]}... over {n} files, "
                                f"smoke_set.json wants {spec['sha256'][:12]}... over {spec.get('files')} files")
            continue
        if not os.path.isfile(p):
            problems.append(f"input {key}: missing file {rel(p)} (copy it once: python tools/harness/smoke.py fixtures)")
            continue
        got = sha256_file(p)
        if got != spec["sha256"]:
            problems.append(f"input {key}: {rel(p)} has sha256 {got[:12]}..., smoke_set.json wants "
                            f"{spec['sha256'][:12]}...")
    return paths, problems


def cmd_fixtures(cfg: dict, refresh: bool = False) -> int:
    """copies (never moves) every input from its source once; an existing right copy is kept"""
    bad = 0
    for key, spec in cfg["inputs"].items():
        dst = input_path(cfg, key)
        src = os.path.join(ROOT, *spec["src"].split("/"))
        kind = spec.get("kind", "file")
        have = (os.path.isdir(dst) if kind == "tree" else os.path.isfile(dst))
        if have and not refresh:
            got = tree_sha(dst)[0] if kind == "tree" else sha256_file(dst)
            if got == spec["sha256"]:
                print(f"kept    {key}: {rel(dst)}")
                continue
            print(f"WRONG   {key}: {rel(dst)} has {got[:12]}..., wants {spec['sha256'][:12]}... (use --refresh)")
            bad += 1
            continue
        if not (os.path.isdir(src) if kind == "tree" else os.path.isfile(src)):
            print(f"MISSING {key}: the source {rel(src)} is not there")
            bad += 1
            continue
        got_src = tree_sha(src)[0] if kind == "tree" else sha256_file(src)
        if got_src != spec["sha256"]:
            print(f"REFUSED {key}: the source {rel(src)} has {got_src[:12]}..., smoke_set.json wants "
                  f"{spec['sha256'][:12]}...")
            bad += 1
            continue
        if not below(dst, BUILD_TOP):
            raise SystemExit(f"{dst}: not below build/")
        if kind == "tree":
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        print(f"copied  {key}: {rel(src)} -> {rel(dst)}")
    return EXIT_FAIL if bad else EXIT_PASS


# ------------------------------------------------------------------ the answers (round 59's all1 recipe)
def answer_for(cfg: dict, key: str, paths: dict) -> dict:
    spec = cfg["runs"][key]
    a = load_json(paths[spec["answer_base"]])
    for k in spec.get("drop", []):
        a.pop(k, None)
    a = dict(a, **spec["overlay"])
    a["seed"] = spec["seed"]
    return a


def run_id(a: dict) -> str:
    return f"{a['seed']}-{hashlib.sha256(json.dumps(a, sort_keys=True).encode()).hexdigest()[:8]}"


# ------------------------------------------------------------------ the task pool (lanes, timeouts, windows, stop)
class Task:
    def __init__(self, name: str, cmd: list, cwd: str, env: dict | None = None, timeout: float = 600,
                 deps: tuple = (), log: str | None = None, kind: str = "task"):
        self.name, self.cmd, self.cwd, self.env, self.timeout = name, cmd, cwd, env, timeout
        self.deps, self.log, self.kind = tuple(deps), log, kind


def _tree_job(name: str):
    try:
        import parallel as par  # tools/harness: a job object (priority, KILL_ON_JOB_CLOSE, kill-the-tree)
        return par.TreeJob(name, "below_normal", None)
    except Exception:  # noqa: BLE001
        return None


def find_windows(pids: set[int]) -> list[tuple[int, str]]:
    """visible top-level windows owned by any of pids: [(pid, title)]"""
    if os.name != "nt" or not pids:
        return []
    import ctypes
    import ctypes.wintypes as W
    u = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(h, _):
        q = W.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(q))
        if q.value in pids and u.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(200)
            u.GetWindowTextW(h, buf, 200)
            found.append((int(q.value), buf.value))
        return True
    u.EnumWindows(cb, 0)
    return found


class _Running:
    def __init__(self, task: Task, proc, tree, logfh):
        self.task, self.proc, self.tree, self.logfh = task, proc, tree, logfh
        self.t0 = time.time()

    def pids(self) -> set[int]:
        out = {self.proc.pid}
        if self.tree is not None:
            out.update(self.tree.pids())
        return out

    def kill(self) -> None:
        if self.tree is not None:
            self.tree.kill(self.proc)
        else:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True,
                               creationflags=NO_WINDOW)
            try:
                self.proc.kill()
            except OSError:
                pass
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass
        self.close()

    def close(self) -> None:
        if self.tree is not None:
            self.tree.close()
            self.tree = None
        if self.logfh:
            self.logfh.close()
            self.logfh = None


def run_tasks(tasks: list[Task], lanes: int = LANES_DEFAULT, windows=find_windows, stop_file: str = STOP_FILE,
              poll: float = 0.5, say=print) -> dict:
    """runs tasks, at most `lanes` at once, in list order once their deps are done and ok.
    Returns {"outcomes": {name: {"status", "rc", "seconds", "started", "ended"}}, "stopped": bool, "window": str|None,
    "peak_lanes": int}. status: ok | exit N | timeout | window | stopped | killed (window elsewhere) | not started
    (...) | needs X (failed)."""
    lanes = max(1, min(int(lanes), LANES_MAX))
    pending = list(tasks)
    running: list[_Running] = []
    out = {"outcomes": {}, "stopped": False, "window": None, "peak_lanes": 0}
    t_start = time.time()

    def finish(rn: _Running, status: str, rc=None):
        rn.close()
        out["outcomes"][rn.task.name] = {"status": status, "rc": rc, "seconds": round(time.time() - rn.t0, 1),
                                         "started": round(rn.t0 - t_start, 1), "ended": round(time.time() - t_start, 1)}

    def kill_all(status: str):
        for rn in list(running):
            rn.kill()
            finish(rn, status)
        running.clear()

    try:
        while pending or running:
            if os.path.exists(stop_file):
                say("build/STOP_ROUND exists: everything is killed")
                kill_all("stopped")
                for t in pending:
                    out["outcomes"][t.name] = {"status": "not started (STOP_ROUND)", "rc": None, "seconds": 0}
                pending.clear()
                out["stopped"] = True
                break
            for rn in list(running):
                rc = rn.proc.poll()
                if rc is not None:
                    running.remove(rn)
                    finish(rn, "ok" if rc == 0 else f"exit {rc}", rc)
                elif time.time() - rn.t0 > rn.task.timeout:
                    running.remove(rn)
                    say(f"{rn.task.name}: timeout after {rn.task.timeout:.0f} s: killed")
                    rn.kill()
                    finish(rn, "timeout")
            allp = set()
            owner = {}
            for rn in running:
                for p in rn.pids():
                    allp.add(p)
                    owner[p] = rn.task.name
            seen = windows(allp) if allp else []
            if seen:
                pid, title = seen[0]
                who = owner.get(pid, "?")
                out["window"] = f"a visible window appeared (task {who}, pid {pid}, title {title!r})"
                say(f"FAIL: {out['window']}: everything is killed")
                for rn in list(running):
                    rn.kill()
                    finish(rn, "window" if rn.task.name == who else "killed (a window appeared elsewhere)")
                running.clear()
                for t in pending:
                    out["outcomes"][t.name] = {"status": "not started (a window appeared)", "rc": None, "seconds": 0}
                pending.clear()
                break
            for t in list(pending):
                if len(running) >= lanes:
                    break
                failed = [d for d in t.deps if d in out["outcomes"] and out["outcomes"][d]["status"] != "ok"]
                if failed:
                    pending.remove(t)
                    out["outcomes"][t.name] = {"status": f"needs {', '.join(failed)} (failed)", "rc": None,
                                               "seconds": 0}
                    continue
                if any(d not in out["outcomes"] for d in t.deps):
                    continue
                if os.path.exists(stop_file):
                    break  # the loop top kills and stops
                pending.remove(t)
                os.makedirs(t.cwd, exist_ok=True)
                logfh = open(t.log, "w", encoding="utf-8", errors="replace") if t.log else subprocess.DEVNULL
                proc = subprocess.Popen(t.cmd, cwd=t.cwd, env=t.env, stdin=subprocess.DEVNULL, stdout=logfh,
                                        stderr=subprocess.STDOUT, creationflags=NO_WINDOW | BELOW_NORMAL)
                tree = _tree_job(t.name)
                if tree is not None and not tree.assign(proc):
                    tree = None
                running.append(_Running(t, proc, tree, logfh if t.log else None))
                out["peak_lanes"] = max(out["peak_lanes"], len(running))
            if pending or running:
                time.sleep(poll)
    except KeyboardInterrupt:
        say("Ctrl+C: everything is killed")
        kill_all("killed (Ctrl+C)")
        raise
    finally:
        kill_all("killed")
    return out


# ------------------------------------------------------------------ judging (pure functions, self-tested)
def cells_summary(rb: dict | None) -> dict:
    rb = rb or {}
    return {"gamedata": {f: [v.get("cells"), v.get("wrong")] for f, v in sorted((rb.get("gd_by_file") or {}).items())},
            "dispos": (rb.get("dispos") or {}).get("cells"),
            "person": {f: [v.get("cells"), v.get("wrong")] for f, v in sorted((rb.get("person_files") or {}).items())}}


def units_key(rb: dict | None) -> list:
    return sorted([u.get("pid"), u.get("jid"), u.get("force"), u.get("x"), u.get("y"), u.get("hp"),
                   json.dumps(u.get("items"))] for u in (rb or {}).get("units") or [])


def rb_wrong(rb: dict | None) -> list[str]:
    bad = []
    if not rb:
        return ["no readback"]
    for f, v in (rb.get("gd_by_file") or {}).items():
        if v.get("wrong"):
            bad.append(f"{f}: {v['wrong']} of {v['cells']} wrong")
    d = rb.get("dispos") or {}
    if isinstance(d.get("cells"), dict) and d["cells"].get("wrong"):
        bad.append(f"placement {d.get('name')}: {d['cells']['wrong']} wrong")
    for f, v in (rb.get("person_files") or {}).items():
        if v.get("wrong"):
            bad.append(f"{f}: {v['wrong']} of {v.get('cells')} wrong")
        if v.get("error") and "FileNotFoundError" not in v["error"]:
            bad.append(f"{f}: {v['error']}")   # FileNotFoundError: a base-game person file the Seal mod does not
            # carry (a checker limit: such a file is another chapter's, not loaded here)
    return bad


def judge_job(r: dict, want_sha: dict, patch_cells: int | None) -> dict:
    """round 59's rules (classify.py): ran to the end, no fault in any log, the frozen exe/lib, every patch cell NEW
    (run) or OLD (off) on the map and after the reload, the 'GameData cells laid' count equal to the patch's GameData
    + recolour cells, the status naming the run, the reload with equal units. The off-run player count rule is
    applied across jobs by judge_all."""
    j = r.get("job") or {}
    why = []
    if r.get("exe_sha") != want_sha:
        why.append(f"not the frozen exe/lib ({r.get('exe_sha')})")
    if not r.get("ok"):
        why.append(f"run: {r.get('error')}")
    if r.get("log_faults"):
        why.append(f"log faults {r['log_faults']}")
    for k in ("readback_map", "readback_reload"):
        if k == "readback_reload" and not r.get("ok"):
            continue
        why += [f"{k[9:]}: {x}" for x in rb_wrong(r.get(k))]
    sr = (r.get("steps") or {}).get("save_reload") or {}
    if r.get("ok") and sr.get("units_equal") is not True:
        why.append(f"reload units equal: {sr.get('units_equal')}")
    laid = [int(m.group(1)) for ln in r.get("rando_log", []) for m in [re.search(r"(\d+) GameData cells laid", ln)] if m]
    if j.get("run"):
        if not laid:
            why.append("no 'GameData cells laid' line")
        elif patch_cells is None or any(x != patch_cells for x in laid):
            why.append(f"GameData cells laid {laid}, patch has {patch_cells} (GameData + recolour)")
        st = str(r.get("status_at_start", ""))
        if j["run"] not in st:
            why.append(f"status at start does not name the run ({st[:80]})")
    elif laid:
        why.append(f"off run laid cells {laid}")
    kept = sorted({ln.split("fates_rando: ")[-1].split(":")[0] for ln in r.get("rando_log", [])
                   if "chapter people kept original" in ln})
    if kept:  # the core's guard declined a chapter person file: memory keeps the original cells; listed apart
        why = [w for w in why if not any(k in w for k in kept)]
    units = (r.get("readback_map") or {}).get("units") or []
    return {"ok": not why, "why": why, "seconds": r.get("seconds"), "laid": laid, "kept_original": kept,
            "players": sum(1 for u in units if u.get("force") == 0),
            "map_frame": ((r.get("steps") or {}).get("map") or {}).get("frame"),
            "hashes": {"units_map": digest(units_key(r.get("readback_map"))),
                       "units_reload": digest(units_key(r.get("readback_reload"))),
                       "cells_map": digest(cells_summary(r.get("readback_map"))),
                       "cells_reload": digest(cells_summary(r.get("readback_reload")))}}


def judge_all(jobs: list[dict], verdicts: dict) -> dict:
    """no missing unit: an everything-on job has as many player units on the map as the off job of its chapter"""
    for j in jobs:
        v = verdicts.get(j["name"])
        if not v or not j.get("run"):
            continue
        off = next((verdicts.get(o["name"]) for o in jobs if o["chapter"] == j["chapter"] and o["game"] == j["game"]
                    and not o.get("run")), None)
        if off and off["ok"] and v["players"] != off["players"]:
            v["ok"] = False
            v["why"].append(f"player units on the map {v['players']}, off run {off['players']}")
    return verdicts


def memory_events(report: list) -> list[dict]:
    return [{"event": e.get("event"), "game_frame": e.get("game_frame"), "fatal_errors": e.get("fatal_errors"),
             "sha256": [x.get("sha256") for x in e.get("hashes") or []]} for e in report]


def judge_memory(events: list[dict], frames: list[int], rc) -> dict:
    why = []
    if rc != 0:
        why.append(f"the game exited with {rc}")
    got = [e["game_frame"] for e in events if e["event"] == "at"]
    if got != list(frames):
        why.append(f"hashes at frames {got}, wanted {list(frames)}")
    if not any(e["event"] == "boot" for e in events):
        why.append("no boot hash")
    if not any(e["event"] == "end" for e in events):
        why.append("no end hash (the run did not finish)")
    if any(e["fatal_errors"] for e in events):
        why.append(f"fatal errors {[e['fatal_errors'] for e in events]}")
    if any(not e["sha256"] for e in events):
        why.append("an event without hashes")
    return {"ok": not why, "why": why}


def compare_baseline(base: dict, obs: dict) -> list[str]:
    """every difference between the baseline and this run, each naming the run/job/compare and the frame"""
    bad = []
    for k, b in sorted((base.get("runs") or {}).items()):
        o = (obs.get("runs") or {}).get(k)
        if not o:
            bad.append(f"run {k}: not made in this smoke")
            continue
        for f in ("id", "patch_sha256"):
            if b.get(f) != o.get(f):
                bad.append(f"run {k}: {f} differs (baseline {str(b.get(f))[:16]}, now {str(o.get(f))[:16]}); a seed "
                           f"change announced in config/release/seed_changes.json needs a new baseline "
                           f"(--write-baseline in the round)")
    for name, b in sorted((base.get("jobs") or {}).items()):
        o = (obs.get("jobs") or {}).get(name)
        if not o:
            bad.append(f"job {name}: not run in this smoke")
            continue
        if b.get("verdict") != o.get("verdict"):
            bad.append(f"job {name}: verdict {o.get('verdict')}, baseline {b.get('verdict')}")
        if not o.get("hashes"):
            bad.append(f"job {name}: no readback to compare (the job left no result)")
            continue
        if b.get("map_frame") != o.get("map_frame"):
            bad.append(f"job {name}: the map was read at frame {o.get('map_frame')}, baseline frame {b.get('map_frame')}")
        for h in ("units_map", "cells_map", "units_reload", "cells_reload"):
            if (b.get("hashes") or {}).get(h) != (o.get("hashes") or {}).get(h):
                where = "the map" if h.endswith("map") else "the reload"
                bad.append(f"job {name}: {h} differs at {where} (map frame {o.get('map_frame')}; baseline "
                           f"{str((b.get('hashes') or {}).get(h))[:12]}, now {str((o.get('hashes') or {}).get(h))[:12]})")
    for name, b in sorted((base.get("memory") or {}).items()):
        o = (obs.get("memory") or {}).get(name)
        if o is None:
            bad.append(f"memory {name}: not run in this smoke")
            continue
        if len(o) != len(b):
            bad.append(f"memory {name}: {len(o)} hash points, baseline {len(b)}")
        for eb, eo in zip(b, o):
            if (eb["event"], eb["game_frame"]) != (eo["event"], eo["game_frame"]):
                bad.append(f"memory {name}: point {eo['event']} frame {eo['game_frame']}, baseline {eb['event']} "
                           f"frame {eb['game_frame']}")
                continue
            for i, (hb, ho) in enumerate(zip(eb["sha256"], eo["sha256"])):
                if hb != ho:
                    bad.append(f"memory {name}: {eo['event']} frame {eo['game_frame']} range {i} differs (baseline "
                               f"{str(hb)[:12]}, now {str(ho)[:12]})")
            if len(eb["sha256"]) != len(eo["sha256"]):
                bad.append(f"memory {name}: {eo['event']} frame {eo['game_frame']}: {len(eo['sha256'])} ranges, "
                           f"baseline {len(eb['sha256'])}")
    return bad


def final_exit(problems: list, job_verdicts: dict, n_jobs: int, memory: dict | None, mismatches: list,
               baseline_missing: bool, stopped: bool, window: str | None, has_memory: bool = True,
               baseline_name: str = "config/harness/smoke_baseline.json") -> tuple[int, str]:
    if stopped:
        return EXIT_STOP, "STOPPED (build/STOP_ROUND)"
    passed = sum(1 for v in job_verdicts.values() if v["ok"])
    why = []
    if problems:
        why.append(f"{len(problems)} input problem(s)")
    if window:
        why.append(window)
    if passed != n_jobs:
        why.append(f"jobs {passed}/{n_jobs} PASS")
    if has_memory and (not memory or not memory.get("ok")):
        why.append("memory compare FAIL")
    if mismatches:
        why.append(f"{len(mismatches)} baseline mismatch(es)")
    if baseline_missing:
        why.append(f"no baseline ({baseline_name}): take one with --write-baseline")
    if why:
        return EXIT_FAIL, "FAIL: " + "; ".join(why)
    if not has_memory:
        return EXIT_PASS, f"PASS: jobs {passed}/{n_jobs}, baseline equal (no memory compare in this set)"
    return EXIT_PASS, f"PASS: jobs {passed}/{n_jobs}, memory compare equal, baseline equal"


def partial_exit(code: int, summary: str, only: set | None) -> tuple[int, str]:
    """An --only run is a part of the set: a passing part exits 4 (PARTIAL), never 0 (0 = the whole set passed)."""
    if only and code == EXIT_PASS:
        return EXIT_PARTIAL, "PARTIAL (--only " + ",".join(sorted(only)) + "; not the whole set): " + summary
    return code, summary


def cmd_selftest() -> int:
    """tests/test_smoke.py in this process (synthetic: fake runner and window watcher, no game, no window)."""
    import unittest
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_smoke")
    res = unittest.TextTestRunner(stream=sys.stdout, verbosity=1).run(suite)
    n, bad = res.testsRun, len(res.failures) + len(res.errors) + len(res.unexpectedSuccesses)
    ok = res.wasSuccessful() and n > 0
    print(f"smoke selftest: {n - bad}/{n} ok" + ("" if ok else " FAIL"))
    return EXIT_PASS if ok else EXIT_FAIL


# ------------------------------------------------------------------ worker: one randomizer run (round 59 mkruns)
def worker_make(cfg: dict, key: str, out: str) -> int:
    paths, problems = check_inputs(cfg)
    res_path = os.path.join(out, "make", key, "make.json")
    if problems:
        write_json(res_path, {"key": key, "ok": False, "error": "; ".join(problems)})
        return 1
    spec = cfg["runs"][key]
    game = spec["game"]
    a = answer_for(cfg, key, paths)
    rid = run_id(a)
    os.environ.pop("FEF_RANDO_CACHE", None)  # a fresh make, never the cache
    sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
    import rando  # noqa: I001  (first: ingame puts tools/play, which has its own rando.py, on the path)
    import ingame
    work = os.path.join(out, "make", key)
    shutil.rmtree(os.path.join(work, "mod"), ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    sealromfs = os.path.join(paths[cfg["robot"]["sealmod"]], "romfs") if game == "seal" else None
    if game == "seal":
        import sources
        sources.activate("seal", sealromfs)
    args = ["make"] + ingame.make_args(a) + ["--out", os.path.join(work, "mod"), "--patch-out",
                                             os.path.join(work, "patch.txt")]
    if game == "seal":
        args += ["--game", "seal", "--seal-romfs", sealromfs]
    buf = io.StringIO()
    t0 = time.time()
    with contextlib.redirect_stdout(buf):
        code = rando.main(args)
    log = buf.getvalue()
    with open(os.path.join(work, "make.log"), "w", encoding="utf-8") as fh:
        fh.write(log)
    fails = [ln for ln in log.splitlines() if "FAIL" in ln]
    res = {"key": key, "game": game, "id": rid, "expect_id": spec.get("expect_id"), "code": code,
           "fails": fails[:5], "seconds": round(time.time() - t0, 1)}
    if code != 0 or not os.path.isfile(os.path.join(work, "patch.txt")):
        res.update(ok=False, error=f"rando.py make returned {code}", tail=log[-600:])
        write_json(res_path, res)
        return 2
    dst = os.path.join(out, "runs", game, rid)
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(dst)
    with open(os.path.join(dst, "options.json"), "w") as fh:
        json.dump(a, fh, sort_keys=True)
    for r, _d, fs in os.walk(os.path.join(work, "mod")):
        for fn in ("spoiler.txt", "plan.json"):
            if fn in fs and not os.path.exists(os.path.join(dst, fn)):
                shutil.copy2(os.path.join(r, fn), os.path.join(dst, fn))
    shutil.copy2(os.path.join(work, "patch.txt"), os.path.join(dst, "patch.txt"))
    if os.path.isfile(os.path.join(work, "nuzlocke.json")):
        shutil.copy2(os.path.join(work, "nuzlocke.json"), os.path.join(dst, "nuzlocke.json"))
    shutil.rmtree(os.path.join(work, "mod"), ignore_errors=True)
    res["patch_sha256"] = sha256_file(os.path.join(dst, "patch.txt"))
    res["ok"] = not fails and (not spec.get("expect_id") or rid == spec["expect_id"])
    if spec.get("expect_id") and rid != spec["expect_id"]:
        res["error"] = f"run id {rid}, the set wants {spec['expect_id']} (the answer changed)"
    elif fails:
        res["error"] = f"{len(fails)} FAIL line(s) in the make log"
    res["pass_lines"] = sum(1 for ln in log.splitlines() if "PASS" in ln)
    write_json(res_path, res)
    return 0 if res["ok"] else 2


# ------------------------------------------------------------------ worker: one robot job (round 58 check driver)
def worker_job(cfg: dict, name: str, out: str) -> int:
    """one job, as build/r58/check/rcheck.py + build/r59/e1/smoke.py + build/r6x/smoke/brk.py did it (their logic, now
    tracked): chapter select, preparations, map readback, one enemy looked at, enemy phase, battle save and reload"""
    job = next(j for j in cfg["jobs"] if j["name"] == name)
    jobdir = os.path.join(out, "jobs", name)
    paths, problems = check_inputs(cfg)
    if problems:
        os.makedirs(jobdir, exist_ok=True)
        write_json(os.path.join(jobdir, "result.json"), {"job": job, "ok": False, "error": "; ".join(problems)})
        return 1
    sys.path.insert(0, HERE)
    sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
    import chapsel as C
    import headless as hl
    import ingame as IG
    import server as sv

    srv_exe, lib = paths[cfg["robot"]["server"]], paths[cfg["robot"]["lib"]]
    want = {"boot-server.exe": cfg["inputs"][cfg["robot"]["server"]]["sha256"],
            f"{TITLE}.dll": cfg["inputs"][cfg["robot"]["lib"]]["sha256"]}
    got = {"boot-server.exe": sha256_file(srv_exe), f"{TITLE}.dll": sha256_file(lib)}
    if got != want:
        raise SystemExit(f"refused: the frozen exe/lib is not the set's ({got})")
    sv.SERVER_EXE, hl.LIB = srv_exe, lib
    C.OUT_TOP = os.path.join(out, "jobs")
    fx = fixtures_top(cfg)
    orig_find = hl.find_backup

    def find_backup(arg):  # the base saves are copies in build/fixtures/smoke/saves
        if arg and os.path.isabs(arg) and below(arg, fx) and os.path.isfile(arg):
            return os.path.abspath(arg)
        return orig_find(arg)
    hl.find_backup = find_backup
    modcopy = paths[cfg["robot"]["sealmod"]] if cfg["robot"].get("sealmod") else None   # the Seal set only
    sealromfs = os.path.join(modcopy, "romfs") if modcopy else None
    runs_top = os.path.join(out, "runs")
    DISPOS, POOL = 0x006D6DC8, 0x006D9F40

    class Mem:
        def __init__(self, s):
            self.s = s

        def u32(self, a):
            if not a:
                return 0
            try:
                return struct.unpack("<I", self.s.peek1(a, 4))[0]
            except Exception:  # noqa: BLE001
                return 0

        def raw(self, a, n):
            return self.s.peek1(a, n) if a else b""

        def start(self, arch):
            a = self.u32(arch + 4) if arch else 0
            b = self.u32(a + 112) if a else 0
            return b + 32 if b else 0

        def cstr(self, a, n=64):
            if not a:
                return None
            try:
                b = self.s.peek1(a, n)
            except Exception:  # noqa: BLE001
                return None
            e = b.find(b"\0")
            return None if e < 0 else b[:e]

    def cells_check(m, base, f, want_new):
        bad = []
        for off, old, new in f["v"]:
            w = new if want_new else old
            if m.raw(base + off, len(w)) != w:
                bad.append(off)
        for off, old, new, _where, _l, _o in f["p"]:
            w = new if want_new else old
            cur = m.u32(base + off)
            if (w is None and cur != 0) or (w is not None and m.cstr(cur) != w):
                bad.append(off)
        changed = sum(1 for _o, a, b in f["v"] if a != b) + sum(1 for x in f["p"] if x[1] != x[2])
        return {"cells": len(f["v"]) + len(f["p"]), "changed": changed, "wrong": len(bad),
                "first": [f"{o:#x}" for o in bad[:6]]}

    def s8(b):
        return b - 256 if b > 127 else b

    def units(m):
        fp = m.u32(POOL + 4)
        res = []
        for f in range(3):
            u, n = m.u32(fp + 12 * f), 0
            while u and n < 120:
                n += 1
                ub = m.raw(u, 0x140)
                per, jb_ = struct.unpack_from("<II", ub, 0x9C)
                pb, jb = m.raw(per, 0x98), m.raw(jb_, 0x80)
                res.append({"force": f, "pid": (m.cstr(struct.unpack_from("<I", pb, 8)[0]) or b"").decode("latin-1"),
                            "jid": (m.cstr(struct.unpack_from("<I", jb, 8)[0]) or b"").decode("latin-1"),
                            "level": ub[0xF1], "x": ub[0xF4], "y": ub[0xF5], "hp": ub[0xF3],
                            "items": [list(struct.unpack_from("<HH", ub, 0x108 + 4 * i)) for i in range(5)],
                            "skills": list(struct.unpack_from("<5H", ub, 0xFC)),
                            "person_base": [s8(x) for x in pb[0x38:0x40]], "growth": [s8(x) for x in pb[0x40:0x48]],
                            "job_base": [s8(x) for x in jb[0x1C:0x24]]})
                u = struct.unpack_from("<I", ub, 0x14)[0]
        return res

    def base_readback(s, game, patch, want_new):
        m = Mem(s)
        e = {"frame": s.frame, "status": str(s.cmd("rando-status"))}
        gd = m.start(m.u32(C.GD_ARCH))
        e["gd_base"] = f"{gd:08x}"
        if patch and gd:
            e["gd_by_file"] = {}
            for f in patch["files"]:
                if f["kind"] != "dispos":
                    e["gd_by_file"][f["rel"]] = cells_check(m, gd, f, want_new)
        dobj = m.u32(DISPOS)
        dn = m.cstr(dobj, 16) if dobj else None
        if dn:
            dn = dn.decode("latin-1")
            dbase = m.start(m.u32(dobj + 16))
            de = {"name": dn, "base": f"{dbase:08x}"}
            if patch and dbase:
                fxp = next((x for x in patch["files"] if x["kind"] == "dispos"
                            and os.path.basename(x["rel"]).split(".")[0].lower() == dn.lower()), None)
                de["cells"] = cells_check(m, dbase, fxp, want_new) if fxp else "no cells for this file"
            e["dispos"] = de
        try:
            e["units"] = units(m)
        except Exception as ex:  # noqa: BLE001
            e["units_error"] = repr(ex)
        return e

    def person_files(m, game, patch, us, want_new):
        T = IG._T()
        res = {}
        for f in patch["files"]:
            if f["kind"] != "person":
                continue
            try:
                if game == "seal":
                    with open(os.path.join(sealromfs, *f["rel"].split("/")), "rb") as fh:
                        c = T.Container(f["rel"], fh.read())
                else:
                    c = T.container(f["rel"])
            except OSError as ex:
                res[f["rel"]] = {"error": repr(ex)}
                continue
            cnt = struct.unpack_from("<H", c.data, 4)[0]
            rows = {}
            for i in range(cnt):
                off = 0x10 + i * 0x98
                lab = c.string_at(c.u32(off + 8)) if (off + 8) in c.relset else None
                if lab:
                    rows[lab.decode("latin-1")] = off
            base = None
            for u in us:
                if u.get("person_ptr") and u["pid"] in rows:
                    cand = u["person_ptr"] - rows[u["pid"]]
                    if m.cstr(m.u32(cand + rows[u["pid"]] + 8)) == u["pid"].encode("latin-1"):
                        base = cand
                        break
            if base is None:
                continue
            res[f["rel"]] = dict(cells_check(m, base, f, want_new), base=f"{base:08x}")
        return res

    def readback(s, game, patch, want_new):
        small = dict(patch, files=[f for f in patch["files"] if f["kind"] in ("gamedata", "dispos")]) if patch else None
        e = base_readback(s, game, small, want_new)
        m = Mem(s)
        fp = m.u32(POOL + 4)
        us = []
        for force in range(3):
            u, n = m.u32(fp + 12 * force), 0
            while u and n < 120:
                n += 1
                ub = m.raw(u, 0x140)
                per = struct.unpack_from("<I", ub, 0x9C)[0]
                us.append({"pid": (m.cstr(m.u32(per + 8)) or b"").decode("latin-1"), "person_ptr": per, "force": force})
                u = struct.unpack_from("<I", ub, 0x14)[0]
        if patch:
            e["person_files"] = person_files(m, game, patch, us, want_new)
        return e

    UNIT_CALLS, RELOAD = [], {}
    orig_units = C.Live.units

    def units_logged(self):
        res = orig_units(self)
        UNIT_CALLS.append(res)
        # the reload server (chapsel names it <job>-reload): its cells, read while it is alive
        if str(getattr(self.s, "name", "")).endswith("-reload") and RELOAD.get("want") is not None:
            RELOAD["rb"] = readback(self.s, RELOAD["game"], RELOAD["patch"], RELOAD["want"])
        return res
    C.Live.units = units_logged

    class CheckRun(C.Run):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.patch, self.want_new = None, True

        def look_enemy(self):
            """cursor onto the nearest enemy (the map's unit panel), its page, back to the map and the cursor back"""
            s = self.s
            b = s.board()
            cur = b.get("cursor")
            ens = [u for u in b["units"] if u.get("force") == 1]
            if not cur or not ens:
                self.res["steps"]["enemy_look"] = {"skipped": "no cursor or no enemy"}
                return
            info = {"looked": []}
            e = min(ens, key=lambda u: abs(u["x"] - cur[0]) + abs(u["y"] - cur[1]))
            dx, dy = e["x"] - cur[0], e["y"] - cur[1]
            for key in (["RIGHT"] * dx if dx > 0 else ["LEFT"] * -dx) + (["DOWN"] * dy if dy > 0 else ["UP"] * -dy):
                self.press(key, gap=10)
                self.wait(14)
            self.wait(40)
            b2 = s.board()
            self.shot("enemyhover")
            info["looked"].append([e["x"], e["y"], b2.get("cursor")])
            self.press("R")
            sc = self.wait(80)
            self.shot("enemypage")
            info["page_screen"] = sc["current"]
            for _ in range(3):
                if self.screen()["current"] == C.HUMAN:
                    break
                self.press("B")
                self.wait(50)
            info["back"] = self.screen()["current"]
            b3 = s.board()
            c3, c0 = b3.get("cursor"), b.get("cursor")
            if c3 and c0:
                dx, dy = c0[0] - c3[0], c0[1] - c3[1]
                for key in (["RIGHT"] * dx if dx > 0 else ["LEFT"] * -dx) + (["DOWN"] * dy if dy > 0 else ["UP"] * -dy):
                    self.press(key, gap=10)
                    self.wait(14)
                self.wait(30)
                info["cursor_back"] = s.board().get("cursor")
            self.res["steps"]["enemy_look"] = info
            if info["back"] != C.HUMAN:
                raise C.Stop(f"could not return to the map after the enemy page ({info['back']})")

        def map_and_enemy_phase(self):
            sc = self.wait(20)
            if sc["current"] != C.HUMAN:
                self.drive({C.HUMAN}, max_steps=100)
            self.res["readback_map"] = readback(self.s, self.game, self.patch, self.want_new)
            self.look_enemy()
            super().map_and_enemy_phase()

    C.stop_check()
    game = job.get("game", "fates")
    base = paths[job["base"]]
    t0 = time.time()
    r = CheckRun(job["chapter"], base, name, game, job.get("route_byte"), "all", float(cfg["robot"].get("server_timeout", 900)))
    if os.path.isdir(r.dir):
        shutil.rmtree(r.dir)
    os.makedirs(r.dir)
    r.res["job"] = job
    srv_root = os.path.join(r.dir, "server")
    run_key, ref_key = job.get("run"), job.get("ref_run")

    def made(key):
        mk = load_json(os.path.join(out, "make", key, "make.json"))
        return mk["id"], os.path.join(runs_top, cfg["runs"][key]["game"], mk["id"])
    rid, run_src = made(run_key) if run_key else (None, None)
    r.res["job"] = dict(job, run=rid, ref_run=made(ref_key)[0] if ref_key else None)
    if rid:
        r.patch, r.want_new = IG.parse_patch(open(os.path.join(run_src, "patch.txt"), encoding="ascii").read()), True
    elif ref_key:
        r.patch, r.want_new = IG.parse_patch(open(os.path.join(made(ref_key)[1], "patch.txt"), encoding="ascii").read()), False
    extra_env = {"FEF_RANDO_TOOL": os.path.join(ROOT, "tools", "randomizer"), "FEF_PYTHON": sys.executable,
                 "RUST_LOG": "info"}
    if game == "seal":
        extra_env["FEF_RANDO_GAME"] = "seal"
    first = {}

    def lay_common(data_dir):
        if not below(data_dir, BUILD_TOP):
            raise C.Stop(f"{data_dir}: not below build/")
        if game == "seal":
            dst = os.path.join(data_dir, "mods", TITLE)
            if not os.path.isdir(dst):
                shutil.copytree(modcopy, dst)
    orig_lay = hl.lay_save

    def lay(zip_path, data_dir):
        names = orig_lay(zip_path, data_dir)
        lay_common(data_dir)
        if rid:
            shutil.copytree(run_src, os.path.join(data_dir, "rando", TITLE, "runs", rid))
            sl = os.path.join(data_dir, "rando", TITLE, "slots")
            os.makedirs(sl, exist_ok=True)
            with open(os.path.join(sl, "Chapter0.json"), "w") as fh:
                fh.write(json.dumps({"format": 1, "run": rid, "save": "Chapter0.json"}) + "\n")
        first["data"] = data_dir
        return names

    def lay_reload(data_dir):  # the reload server: the first server's rando folder as the game left it
        lay_common(data_dir)
        src = os.path.join(first["data"], "rando")
        if os.path.isdir(src):
            dst = os.path.join(data_dir, "rando")
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)
        sl = os.path.join(data_dir, "rando", TITLE, "slots")
        r.res["reload_slot_files"] = {x: open(os.path.join(sl, x)).read().strip()
                                      for x in os.listdir(sl)} if os.path.isdir(sl) else {}

    RELOAD.update(game=game, patch=r.patch, want=r.want_new)
    hl.lay_save = lay
    try:
        with sv.Server(name, save=base, root=srv_root, timeout=r.timeout, cheat=True, extra_env=extra_env) as s:
            r.res["server_dir"] = rel(s.dir)
            r.select(s)
            r.res["status_at_start"] = str(s.cmd("rando-status"))
            r.prep()
            r.map_and_enemy_phase()
            hl.lay_save = orig_lay
            r.save_and_reload(srv_root, extra_env, lay_reload)
            r.res["readback_reload"] = RELOAD.get("rb") or {"status": "not read (reload server)"}
            r.res["ok"] = True
    except C.Stop as e:
        r.res["ok"], r.res["error"] = False, str(e)
    except Exception as e:  # noqa: BLE001
        r.res["ok"], r.res["error"] = False, f"{type(e).__name__}: {e}"
        r.res["trace"] = traceback.format_exc()
    finally:
        hl.lay_save = orig_lay
        r.res["seconds"] = round(time.time() - t0, 1)
        if RELOAD.get("rb") and "readback_reload" not in r.res:
            r.res["readback_reload"] = RELOAD["rb"]
        if "reload differs" in str(r.res.get("error")) and len(UNIT_CALLS) >= 2:
            r.res["units_before_save"], r.res["units_after_reload"] = UNIT_CALLS[-2], UNIT_CALLS[-1]
        faults, notices = [], []
        for top, _d, fs in os.walk(srv_root):
            for fn in fs:
                if fn.endswith(".log"):
                    try:
                        txt = open(os.path.join(top, fn), "rb").read().decode("utf-8", "replace")
                    except OSError:
                        continue
                    low = txt.lower()
                    faults += [f"{fn}: {w}" for w in ("panic", "guest fault", "data abort", "prefetch abort",
                                                      "undefined instruction") if w in low]
                    notices += [ln.strip()[:240] for ln in txt.splitlines() if "fates_rando" in ln][-30:]
        r.res["log_faults"] = sorted(set(faults))
        r.res["rando_log"] = notices[-30:]
        r.res["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        r.res["exe_sha"] = got
        write_json(os.path.join(r.dir, "result.json"), r.res)
        shutil.rmtree(srv_root, ignore_errors=True)  # disk: PNGs and result.json stay
        shutil.rmtree(os.path.join(r.dir, "saved-user"), ignore_errors=True)
    return 0


# ------------------------------------------------------------------ the run
def child_env(base_dir: str, extra: dict | None = None, drop_prefixes=("FEF_", "ZAKURO_")) -> dict:
    """the environment of a task: APPDATA/LOCALAPPDATA/TMP under its own folder, no rando cache, no inherited
    FEF_/ZAKURO_ switches"""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(drop_prefixes)}
    env.pop("RUST_LOG", None)
    for k, sub in (("APPDATA", "appdata"), ("LOCALAPPDATA", "localappdata"), ("TMP", "tmp"), ("TEMP", "tmp")):
        env[k] = os.path.join(base_dir, "env", sub)
        os.makedirs(env[k], exist_ok=True)
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra or {})
    return env


def build_tasks(cfg: dict, paths: dict, out: str, set_path: str, only: set | None = None) -> list[Task]:
    me = os.path.abspath(__file__)
    py = sys.executable
    tm = cfg.get("timeouts", {})
    tasks = []
    need_runs = set()
    for j in cfg["jobs"]:
        if only and j["name"] not in only:
            continue
        need_runs.update(k for k in (j.get("run"), j.get("ref_run")) if k)
    mem = memory_of(cfg)
    if mem and (not only or mem["name"] in only):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import paths as P  # tools/paths.py: the ROM in roms/, checked (full check, cached)
        rom = str(P.find_rom())
        d = os.path.join(out, mem["name"])
        os.makedirs(os.path.join(d, "data"), exist_ok=True)
        env = child_env(d, {"ZAKURO_REPLAY": paths[mem["replay"]], "FEF_HEADLESS_REPORT": os.path.join(d, "report.json"),
                            "FEF_HEADLESS_RANGES": mem["ranges"],
                            "FEF_HEADLESS_HASH_AT": ",".join(str(f) for f in mem["hash_at"])})
        tasks.append(Task(mem["name"], [paths[mem["exe"]], rom, "--headless", str(mem["frames"]), "--mute", "--data",
                                        os.path.join(d, "data")], d, env, tm.get("memory", 300),
                          log=os.path.join(d, "stdout.txt"), kind="memory"))
    for key in sorted(need_runs):
        d = os.path.join(out, "make", key)
        os.makedirs(d, exist_ok=True)
        tasks.append(Task(f"make-{key}", [py, me, "--set", set_path, "_make", "--key", key, "--out", out], d,
                          child_env(d), tm.get("make", 600), log=os.path.join(d, "worker.log"), kind="make"))
    for j in cfg["jobs"]:
        if only and j["name"] not in only:
            continue
        d = os.path.join(out, "jobs", j["name"])
        deps = [f"make-{k}" for k in (j.get("run"), j.get("ref_run")) if k]
        tasks.append(Task(j["name"], [py, me, "--set", set_path, "_job", "--job", j["name"], "--out", out],
                          os.path.join(out, "lanes", j["name"]), child_env(os.path.join(out, "lanes", j["name"])),
                          tm.get("job", 480), deps=sorted(set(deps)),
                          log=os.path.join(out, "lanes", j["name"] + ".log"), kind="job"))
    return tasks


def evaluate(cfg: dict, out: str, outcomes: dict, only: set | None = None) -> dict:
    """judges what the tasks left in out/ -> {"runs", "jobs", "memory", "verdicts", "memory_verdict"}"""
    sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
    obs = {"runs": {}, "jobs": {}, "memory": {}}
    run_notes = {}
    patch_cells = {}
    want_sha = {"boot-server.exe": cfg["inputs"][cfg["robot"]["server"]]["sha256"],
                f"{TITLE}.dll": cfg["inputs"][cfg["robot"]["lib"]]["sha256"]}
    for key in cfg["runs"]:
        p = os.path.join(out, "make", key, "make.json")
        if not os.path.isfile(p):
            continue
        mk = load_json(p)
        run_notes[key] = mk
        if mk.get("patch_sha256"):
            obs["runs"][key] = {"id": mk.get("id"), "patch_sha256": mk.get("patch_sha256")}
            patch_cells[key] = count_patch_cells(os.path.join(out, "runs", mk["game"], mk["id"], "patch.txt"))
    verdicts = {}
    for j in cfg["jobs"]:
        if only and j["name"] not in only:
            continue
        rp = os.path.join(out, "jobs", j["name"], "result.json")
        oc = outcomes.get(j["name"], {})
        if not os.path.isfile(rp):
            verdicts[j["name"]] = {"ok": False, "why": [f"no result.json (task: {oc.get('status', 'not run')})"],
                                   "seconds": oc.get("seconds"), "players": None, "map_frame": None, "hashes": {}}
            continue
        r = load_json(rp)
        v = judge_job(r, want_sha, patch_cells.get(j.get("run")) if j.get("run") else None)
        if oc and oc.get("status") != "ok":
            v["ok"] = False
            v["why"].insert(0, f"task {oc.get('status')}")
        verdicts[j["name"]] = v
    judge_all([j for j in cfg["jobs"] if j["name"] in verdicts], verdicts)
    for n, v in verdicts.items():
        obs["jobs"][n] = {"verdict": "PASS" if v["ok"] else "FAIL", "map_frame": v.get("map_frame"),
                          "hashes": v.get("hashes", {})}
    mem = memory_of(cfg)
    mv = None
    if mem and (not only or mem["name"] in only):
        rp = os.path.join(out, mem["name"], "report.json")
        oc = outcomes.get(mem["name"], {})
        if os.path.isfile(rp):
            ev = memory_events(load_json(rp))
            obs["memory"][mem["name"]] = ev
            mv = judge_memory(ev, mem["hash_at"], oc.get("rc", 0) if oc else 0)
            if oc and oc.get("status") != "ok":
                mv["ok"] = False
                mv["why"].insert(0, f"task {oc.get('status')}")
        else:
            mv = {"ok": False, "why": [f"no report.json (task: {oc.get('status', 'not run')})"]}
    return {"obs": obs, "verdicts": verdicts, "memory_verdict": mv, "runs": run_notes}


def count_patch_cells(patch_path: str) -> int | None:
    """GameData + recolour (asset, face) cells of a patch: what the core's 'GameData cells laid' line must count"""
    if not os.path.isfile(patch_path):
        return None
    sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
    import ingame
    p = ingame.parse_patch(open(patch_path, encoding="ascii").read())
    return sum(len(f["v"]) + len(f["p"]) for f in p["files"] if f["kind"] in ("gamedata", "asset", "face"))


def table(cfg: dict, ev: dict, outcomes: dict, out: str) -> str:
    rows = ["| task | result | seconds | evidence / why |", "|---|---|---|---|"]
    for key, mk in sorted(ev["runs"].items()):
        oc = outcomes.get(f"make-{key}", {})
        rows.append(f"| make {key} ({mk.get('id')}) | {'PASS' if mk.get('ok') else 'FAIL'} | {oc.get('seconds', '')} | "
                    f"patch {str(mk.get('patch_sha256'))[:12]} {mk.get('error') or ''} |")
    for j in cfg["jobs"]:
        v = ev["verdicts"].get(j["name"])
        if v is None:
            continue
        evid = rel(os.path.join(out, "jobs", j["name"], "result.json"))
        rows.append(f"| {j['name']} | {'PASS' if v['ok'] else 'FAIL'} | {outcomes.get(j['name'], {}).get('seconds', '')} "
                    f"| {evid}{' ; ' + '; '.join(v['why'][:3]) if v['why'] else ''} |")
    mv = ev["memory_verdict"]
    if mv is not None and memory_of(cfg):
        mem = memory_of(cfg)
        rows.append(f"| {mem['name']} (frames 0/{'/'.join(str(f) for f in mem['hash_at'])}) | "
                    f"{'PASS' if mv['ok'] else 'FAIL'} | {outcomes.get(mem['name'], {}).get('seconds', '')} | "
                    f"{rel(os.path.join(out, mem['name'], 'report.json'))}{' ; ' + '; '.join(mv['why']) if mv['why'] else ''} |")
    return "\n".join(rows)


def run_smoke(set_path: str, out: str, lanes: int, baseline_path: str | None, write_baseline: bool,
              only: set | None = None, say=print, bin_dir: str | None = None) -> int:
    cfg = load_set(set_path)
    baseline_path = baseline_path or baseline_of(cfg)
    if bin_dir and write_baseline:
        say("refused: --write-baseline with --bin (a baseline is taken from the installed copies inside a round)")
        return EXIT_USAGE
    if os.path.exists(STOP_FILE):
        say("build/STOP_ROUND exists: nothing started")
        return EXIT_STOP
    if not below(out, BUILD_TOP):
        say(f"refused: the output folder {out} is not below build/")
        return EXIT_USAGE
    if os.path.isdir(out) and os.listdir(out):
        say(f"refused: the output folder {rel(out)} is not empty (one run per folder, never a second copy)")
        return EXIT_USAGE
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    used_bin = None
    if bin_dir:
        cfg, used_bin, bin_problems = bin_set(cfg, bin_dir)
        if bin_problems:
            for p in bin_problems:
                say(f"FAIL: {p}")
            write_json(os.path.join(out, "results.json"), {"set": rel(set_path), "out": rel(out), "bin": used_bin,
                                                           "problems": bin_problems, "verdict": "FAIL",
                                                           "exit": EXIT_FAIL, "summary": "FAIL: --bin"})
            return EXIT_FAIL
        set_path = os.path.join(out, "set-bin.json")  # the workers read the same swapped set
        write_json(set_path, cfg)
        for k, u in used_bin.items():
            say(f"smoke --bin: {k}: {u['file']} sha256 {u['sha256'][:16]}... ({'STAGED' if u['staged'] else 'frozen'})")
    paths, problems = check_inputs(cfg)
    results = {"set": rel(set_path), "out": rel(out), "started": time.strftime("%Y-%m-%d %H:%M:%S"),
               "lanes": max(1, min(lanes, LANES_MAX)), "problems": problems, "bin": used_bin}
    if problems:
        for p in problems:
            say(f"FAIL: {p}")
        results.update(verdict="FAIL", exit=EXIT_FAIL, summary=f"FAIL: {len(problems)} input problem(s)")
        write_json(os.path.join(out, "results.json"), results)
        return EXIT_FAIL
    tasks = build_tasks(cfg, paths, out, set_path, only)
    say(f"smoke: {len(tasks)} tasks, {results['lanes']} lanes, output {rel(out)}")
    pool = run_tasks(tasks, lanes, say=say)
    ev = evaluate(cfg, out, pool["outcomes"], only)
    base_missing = False
    mism: list[str] = []
    base = None
    if os.path.isfile(baseline_path):
        base = load_json(baseline_path)
        if only:
            base = {"runs": {k: v for k, v in base.get("runs", {}).items() if k in ev["obs"]["runs"]},
                    "jobs": {k: v for k, v in base.get("jobs", {}).items() if k in only},
                    "memory": {k: v for k, v in base.get("memory", {}).items() if k in only}}
        mism = compare_baseline(base, ev["obs"])
    elif not write_baseline:
        base_missing = True
    n_jobs = len([j for j in cfg["jobs"] if not only or j["name"] in only])
    mem = memory_of(cfg)
    mv = ev["memory_verdict"] if (mem and (not only or mem["name"] in only)) else {"ok": True}
    code, summary = final_exit([], ev["verdicts"], n_jobs, mv, mism, base_missing, pool["stopped"], pool["window"],
                               has_memory=mem is not None, baseline_name=rel(baseline_path))
    full_pass = code == EXIT_PASS
    code, summary = partial_exit(code, summary, only)
    wrote = None
    if write_baseline:
        if full_pass and not only:
            bl = {"status": "NEW", "written": time.strftime("%Y-%m-%d %H:%M:%S"), "from": rel(out),
                  "compared_with": rel(baseline_path) if base is not None else None,
                  "note": "hashes and verdicts only (no game values); re-take inside a round commit with --write-baseline",
                  **ev["obs"]}
            write_json(baseline_path, bl)
            wrote = rel(baseline_path)
            say(f"baseline written: {wrote} (NEW)")
        else:
            say("baseline NOT written: the run did not pass" + (" (or ran only part of the set)" if only else ""))
    tab = table(cfg, ev, pool["outcomes"], out)
    results.update(outcomes=pool["outcomes"], peak_lanes=pool["peak_lanes"], window=pool["window"],
                   stopped=pool["stopped"], verdicts=ev["verdicts"], memory_verdict=mv, runs=ev["runs"],
                   observed=ev["obs"], baseline=rel(baseline_path) if base is not None else None,
                   baseline_mismatches=mism, baseline_written=wrote, seconds=round(time.time() - t0, 1),
                   verdict="PASS" if code == EXIT_PASS else ("STOPPED" if code == EXIT_STOP else
                                                          ("PARTIAL" if code == EXIT_PARTIAL else "FAIL")),
                   exit=code, summary=summary)
    write_json(os.path.join(out, "results.json"), results)
    with open(os.path.join(out, "table.md"), "w", encoding="utf-8") as fh:
        fh.write(tab + "\n\n" + summary + "\n" + "".join(f"- {m}\n" for m in mism))
    say(tab)
    for m in mism:
        say(f"MISMATCH: {m}")
    say(f"{summary} ({results['seconds']} s)")
    return code


def record(set_path: str, jobs_dir: str, runs_dir: str, memory_report: str | None, out_file: str) -> int:
    """judges a finished hand-made smoke (its jobs/<name>/result.json and runs/<game>/<id>/patch.txt) by these rules,
    into the baseline format: what a real run must agree with"""
    cfg = load_set(set_path)
    want_sha = {"boot-server.exe": cfg["inputs"][cfg["robot"]["server"]]["sha256"],
                f"{TITLE}.dll": cfg["inputs"][cfg["robot"]["lib"]]["sha256"]}
    obs = {"runs": {}, "jobs": {}, "memory": {}}
    cells_of = {}
    for key, spec in cfg["runs"].items():
        p = os.path.join(runs_dir, spec["game"], spec["expect_id"], "patch.txt")
        if os.path.isfile(p):
            obs["runs"][key] = {"id": spec["expect_id"], "patch_sha256": sha256_file(p)}
            cells_of[key] = count_patch_cells(p)
    verdicts = {}
    for j in cfg["jobs"]:
        rp = os.path.join(jobs_dir, j["name"], "result.json")
        if os.path.isfile(rp):
            verdicts[j["name"]] = judge_job(load_json(rp), want_sha, cells_of.get(j.get("run")) if j.get("run") else None)
    judge_all(cfg["jobs"], verdicts)
    for n, v in verdicts.items():
        obs["jobs"][n] = {"verdict": "PASS" if v["ok"] else "FAIL", "map_frame": v.get("map_frame"),
                          "hashes": v.get("hashes", {})}
    if memory_report and os.path.isfile(memory_report) and memory_of(cfg):
        obs["memory"][memory_of(cfg)["name"]] = memory_events(load_json(memory_report))
    rec = {"status": "RECORD", "written": time.strftime("%Y-%m-%d %H:%M:%S"),
           "from": {"jobs": rel(jobs_dir), "runs": rel(runs_dir), "memory": rel(memory_report) if memory_report else None},
           "why": {n: v["why"] for n, v in verdicts.items() if v["why"]}, **obs}
    write_json(out_file, rec)
    for n, v in verdicts.items():
        print(f"{n}: {'PASS' if v['ok'] else 'FAIL'} {v['why'][:2]}")
    print(f"recorded {len(verdicts)} jobs, {len(obs['runs'])} runs, {len(obs['memory'])} memory compare -> {rel(out_file)}")
    return EXIT_PASS


def list_set(cfg: dict) -> None:
    print("runs (re-made with today's code, cache off):")
    for k, s in cfg["runs"].items():
        print(f"  {k}: {s['game']} seed {s['seed']} (expect id {s.get('expect_id')})")
    print("robot jobs:")
    for j in cfg["jobs"]:
        print(f"  {j['name']}: {j['game']} {j['chapter']} from {j['base']} run {j.get('run') or 'off'}")
    m = memory_of(cfg)
    if m:
        print(f"memory compare: {m['name']}: {m['exe']} {m['frames']} frames, hashes at boot/{m['hash_at']}/end")
    else:
        print("memory compare: none in this set")
    print(f"baseline: {rel(baseline_of(cfg))}")
    print("inputs (copies in " + cfg["fixtures_dir"] + "):")
    for k, s in cfg["inputs"].items():
        print(f"  {k}: {s['file']} sha256 {s['sha256'][:16]}...{' (' + str(s.get('files')) + ' files)' if s.get('kind') == 'tree' else ''}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="smoke.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--list", action="store_true", help="print the set and exit")
    ap.add_argument("--set", default=SET_FILE)
    sub = ap.add_subparsers(dest="cmd")
    f = sub.add_parser("fixtures")
    f.add_argument("--refresh", action="store_true")
    sub.add_parser("check")
    sub.add_parser("selftest")
    r = sub.add_parser("run")
    r.add_argument("--out")
    r.add_argument("--lanes", type=int, default=LANES_DEFAULT)
    r.add_argument("--baseline", default=None, help="default: the set's baseline (config/harness/smoke_baseline.json)")
    r.add_argument("--write-baseline", action="store_true")
    r.add_argument("--only", help="comma-separated job / memory names (a part of the set; never writes a baseline)")
    r.add_argument("--bin", help="a folder under build/ with a staged game exe / boot-server.exe / capture library "
                   "to run instead of the frozen copies (sha-listed in results.json)")
    rc = sub.add_parser("record")
    rc.add_argument("--jobs", required=True)
    rc.add_argument("--runs", required=True)
    rc.add_argument("--memory")
    rc.add_argument("--out", required=True)
    for name, key in (("_make", "--key"), ("_job", "--job")):
        w = sub.add_parser(name)
        w.add_argument(key, required=True)
        w.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    set_path = os.path.abspath(a.set)
    if a.list:
        list_set(load_set(set_path))
        return EXIT_PASS
    if a.cmd == "fixtures":
        return cmd_fixtures(load_set(set_path), a.refresh)
    if a.cmd == "check":
        _p, problems = check_inputs(load_set(set_path))
        for p in problems:
            print(f"FAIL: {p}")
        print("inputs OK" if not problems else f"FAIL: {len(problems)} input problem(s)")
        return EXIT_FAIL if problems else EXIT_PASS
    if a.cmd == "selftest":
        return cmd_selftest()
    if a.cmd == "run":
        if a.lanes < 1 or a.lanes > LANES_MAX:
            print(f"--lanes must be 1..{LANES_MAX}")
            return EXIT_USAGE
        out = os.path.abspath(a.out or os.path.join(BUILD_TOP, "smoke", time.strftime("%Y%m%d-%H%M%S")))
        only = set(x for x in a.only.split(",") if x) if a.only else None
        return run_smoke(set_path, out, a.lanes, os.path.abspath(a.baseline) if a.baseline else None,
                         a.write_baseline, only,
                         bin_dir=os.path.abspath(a.bin) if a.bin else None)
    if a.cmd == "record":
        return record(set_path, os.path.abspath(a.jobs), os.path.abspath(a.runs),
                      os.path.abspath(a.memory) if a.memory else None, os.path.abspath(a.out))
    if a.cmd == "_make":
        return worker_make(load_set(set_path), a.key, os.path.abspath(a.out))
    if a.cmd == "_job":
        return worker_job(load_set(set_path), a.job, os.path.abspath(a.out))
    ap.print_help()
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
