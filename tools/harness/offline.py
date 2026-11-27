#!/usr/bin/env python3
"""Offline capture verdicts from kept game records, instead of a repeat live capture, when only the capture
library's readable code changed (docs/collab/SPEED_AGREED.md item C, owner OK 2026-11-13; docs/harness/H56.md 8).
Standard library only; no game, no engine build: replay.exe (tools/harness/replay.c, the H5/H6 replayer) and the
host C compiler only, plus 3dsrecomp for `build-lib` (a scratch capture library, never build/harness/lib).

    python tools/harness/offline.py plan --sessions r7-h5 [--extra-sessions r12-cap-*] [--label play] [--baseline-rev REV]
                                      [--json PATH]
        which routes and overrides the kept records still decide, and which must play live: a route whose input,
        frames, save, save_at, pokes or cheat flag differ from what its records ran, whose start save zip or
        routes.json entry changed after the records were made, whose records ran another boot.exe or clock, or whose
        run did not complete; an override that has no records (NEW: its address was not captured), whose hook
        changed (another address or kind in config/harness/targets.csv than at the records' time), or that no
        longer is an override. "The records' time" is each main session's own targets.csv (round 13): the hash
        parallel.py stamps into records/<run>/run.json (capture_targets_sha256), else the targets_sha256 of the
        library's build manifest (run.json library_sha256 -> a kept harness_build.json), then the commit with that
        targets.csv. When it cannot be told the plan stops and says why; --baseline-rev REV gives one commit for all
        main sessions by hand. A name whose hook differs between the sessions' commits plays live. A store-keep run
        that kept 0 records (records/<run>/ with run.json and summary.tsv, no records.fecap; parallel.py keep-empty
        backfills older sessions) counts: its watched `only` overrides are "watched, never called" (decided, 0
        records), and replay has nothing to replay in it. Prints both plan lines (1: routes offline / live; 2: overrides decided by records /
        live, on which routes) and a LIVE TOTAL, then the parallel.py command lines for the live part.
        --extra-sessions: the batch's own capture (made after its fixes, with the library integrate checks): an
        override those runs captured (address in run.json `only`, summary kind override, route still valid) counts
        as decided by records. `replay --extra-sessions` replays those folders too.
    python tools/harness/offline.py tree --rev REV [--name N] [--plant "PATH|OLD|NEW"]
        a frozen source tree (git archive of src include config tools) in build/speed/replay/trees/N/; --plant
        replaces one exact text (it must occur once) in that copy only: a planted bug for the proof
    python tools/harness/offline.py build-lib --tree build/speed/replay/trees/N
        that tree's build.py (3dsrecomp + gcc, below-normal, one build at a time through parallel.py's build lock)
        -> build/speed/replay/trees/N/build/harness/lib/<title id>.dll; build/harness/lib is never touched
    python tools/harness/offline.py replay --sessions r7-h5 [--tree DIR | --rev REV] [--lib DLL] [--name NAME]
                                      [--routes a,b] [--jobs N] [--ignore-plan] [--no-source-gate]
        the offline capture: replay.exe built from the tree (default: the working tree), the library copied to
        build/speed/replay/<NAME>/lib/ (never loaded in place), every record folder replayed original side first
        (must be clean) then readable side; per run a summary.tsv with the live capture's columns and verdict rule
        (results/<run>.summary.tsv), the same capture table and PASS/FAIL rule as parallel.py, offline.json.
        Source gate: the tree must stage to exactly the library's build manifest (lib/harness_build.json), so the
        replayed readable code IS the library's readable code. Routes the plan sends live are left out and listed.
    python tools/harness/offline.py compare --offline NAME --live SESSION_OR_DIR [--one-side-ok]
        per route and per override: records, every verdict count (escaped included) and the verdict label, offline
        against a live capture (a parallel.py session folder with results/, an evidence folder, or a records/
        session); a route on one side only is a difference too (exit 1) unless --one-side-ok (round 9)
    python tools/harness/offline.py --selftest

Writes only below build/speed/replay/ (and a tree's own build/ folder inside it). Record folders are only read:
replay.exe's output and FE_READABLE_LOG go to build/speed/replay/<NAME>/. Never %APPDATA%, never build/harness/lib,
never boot.exe. Real play and cheat track are never mixed (h56.record_dirs, F-019).
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import glob
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import harness as H  # noqa: E402  (verdict rules: VNAMES, BAD, classify, fn_verdict; run() with the compiler's PATH)
import parallel as par  # noqa: E402  (budget, build lock, capture table and pass rule; nothing run at import)

rcheck = H.rcheck
OUT = os.path.join(ROOT, "build", "speed", "replay")
PAR = os.path.join(ROOT, "build", "parallel")
ROUTES = os.path.join(ROOT, "config", "harness", "routes.json")
TARGETS = os.path.join(ROOT, "config", "harness", "targets.csv")
SAVES = os.path.join(ROOT, "build", "harness", "saves")
NAME_RX = r"[A-Za-z0-9_.-]{1,64}"
# the route fields that change what the game does (about/verified are words; shots only take pictures)
ROUTE_KEYS = ("input", "frames", "save", "save_at", "pokes", "cheat")
COLS = ["address", "kind", "verdict", "calls", "records"] + H.VNAMES[1:] + ["mismatch_regs", "damaged", "cold", "warm",
                                                                             "deep", "kept", "paths", "signatures"]


class Stop(Exception):
    pass


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_atomic(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def own_dir(name: str) -> str:
    if not re.fullmatch(NAME_RX, name) or ".." in name:
        raise Stop(f"name {name!r}: letters, digits, _ . - only")
    return os.path.join(OUT, name)


# ------------------------------------------------------------------ git (read only)
def git(*args: str, text: bool = True):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=text)
    if r.returncode:
        raise Stop(f"git {' '.join(args)}: {(r.stderr or b'').strip() if text else r.stderr[:300]}")
    return r.stdout


def file_at(rev: str, path: str) -> str | None:
    r = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    return r.stdout if r.returncode == 0 else None


# ------------------------------------------------------------------ the plan: what may stay offline
def route_fp(route: dict | None) -> str | None:
    if route is None:
        return None
    return json.dumps({k: route.get(k) for k in ROUTE_KEYS}, sort_keys=True)


def route_history(name: str) -> list[tuple[float, str | None]]:
    """(commit time, fingerprint) of the route in every commit that touched routes.json, newest first."""
    out = []
    log = git("log", "--format=%H %ct", "--", "config/harness/routes.json").split("\n")
    for ln in filter(None, log):
        h, t = ln.split()
        text = file_at(h, "config/harness/routes.json")
        try:
            out.append((float(t), route_fp(json.loads(text)["routes"].get(name)) if text else None))
        except (ValueError, KeyError):
            out.append((float(t), None))
    return out


def route_changed_at(name: str, now_fp: str | None, history: list | None = None, routes_mtime: float | None = None) -> float:
    """When the route's run-affecting fields took their present value: routes.json's mtime when the working copy
    differs from the last commit, else the oldest commit of the newest unbroken run of equal fingerprints."""
    history = route_history(name) if history is None else history
    if not history or history[0][1] != now_fp:
        return routes_mtime if routes_mtime is not None else os.path.getmtime(ROUTES)
    when = history[0][0]
    for t, fp in history:
        if fp != now_fp:
            break
        when = t
    return when


def route_added_only(name: str, now_fp: str | None, history: list | None = None) -> bool:
    """True when the route's present value goes back to the commit that first added it (no older value to differ
    from): its "last change" is then only the commit of an entry the records may already have run."""
    history = route_history(name) if history is None else history
    if not history or history[0][1] is None:
        return now_fp is not None  # never committed: its one value is today's (the records' run.json must prove it)
    if history[0][1] != now_fp:
        return False
    for _t, fp in history:
        if fp != now_fp:
            return fp is None
    return True


def targets_rows(text: str | None) -> dict[str, dict]:
    """name -> {address (Thumb bit cleared), kind} from a targets.csv text."""
    import csv
    out = {}
    for r in csv.DictReader(io.StringIO(text or "")):
        if r.get("address", "").strip().startswith("0x"):
            out[r["name"].strip()] = {"address": int(r["address"], 16) & ~1, "kind": r["kind"].strip()}
    return out


def record_info(d: str) -> dict:
    with open(os.path.join(d, "run.json"), encoding="utf-8") as fh:
        rj = json.load(fh)
    only = {int(x, 16) & ~1 for x in str(rj.get("only") or "").split(",") if x.strip().startswith("0x")}
    met, kinds, calls = {}, {}, {}
    p = os.path.join(d, "summary.tsv")
    if os.path.isfile(p):
        for a, f in H.read_summary(p).items():
            met[int(a, 16) & ~1] = f["records"]
            kinds[int(a, 16) & ~1] = f["kind"]
            calls[int(a, 16) & ~1] = f["calls"]
    return {"dir": d, "run": os.path.basename(d), "route": rj.get("route"), "input": rj.get("input"),
            "frames": rj.get("frames"), "save": os.path.splitext(os.path.basename(str(rj.get("save_backup") or "")))[0],
            "clock": rj.get("clock"), "boot": rj.get("boot_exe_sha256"), "outcome": rj.get("outcome"),
            "exit": rj.get("exit_code"), "library": rj.get("library_sha256"), "save_at": rj.get("state_frame"), "only": only, "met": met,
            "made": os.path.getmtime(os.path.join(d, "run.json")), "cheat": bool(rj.get("cheat")),
            "stage": bool(re.search(r"\.stage\d+$", os.path.basename(d))), "kinds": kinds, "calls": calls,
            "session": os.path.basename(os.path.dirname(os.path.dirname(d))),
            # round 13: a store-keep run that kept 0 records has no records.fecap (nothing to replay); the targets.csv
            # its records ran, when parallel.py stamped it (only valid for the library its manifest describes)
            "fecap": os.path.isfile(os.path.join(d, "records.fecap")),
            "targets": rj.get("capture_targets_sha256")
            if rj.get("capture_manifest_library_sha256") == rj.get("library_sha256") else None}


def decide(records: list[dict], routes: dict, overrides_now: dict, targets_then: dict, targets_now: dict,
           changed_at: dict, save_mtime: dict, boot_now: str | None, clock_now: str | None,
           added: set | None = None, extra: list[dict] | None = None, conflicts: dict | None = None) -> dict:
    """The rule (pure, tested by the self-test). records: record_info of each run; routes: routes.json "routes";
    overrides_now: name -> address of today's readable overrides; targets_then / targets_now: targets_rows at the
    records' time and now; changed_at: route -> when its run-affecting fields last changed; save_mtime: save name ->
    mtime of build/harness/saves/<save>.zip; added: routes whose last change is only their first commit.
    extra (round 12, --extra-sessions): record_info of the batch's own capture runs (e.g. r12-cap-*, made after the
    batch's fixes with the library integrate checks). Each goes through the same route rule; an override that the
    main records do not decide (NEW, or a moved hook) is decided by the records when a still-valid extra run
    captured its address today (run.json `only`) and that run's summary.tsv, if it lists the address, lists it as an
    override. Hook evidence is the extra records' own address and kind, so a hook moved after that capture is still
    NEW. "kind now ..." always stays live.
    Round 13: an extra run that kept 0 records (no records.fecap, parallel.py keep_records / keep-empty) counts the
    same way: its run.json `only` watched the address and its summary.tsv shows no call, so the override is decided
    as "watched, never called" (0 records). An address the valid extra runs saw called but kept no record of is not
    decided by them (calls without records prove nothing). conflicts: name -> why, the overrides whose targets.csv row
    differs between the baselines of the main sessions (make_plan): always live."""
    routes_out, live_routes = {}, set()
    for rec in records:
        why = route_why(rec, routes, changed_at, save_mtime, boot_now, clock_now, added)
        name = rec["route"]
        key = rec["run"]
        routes_out[key] = {"route": name, "live": bool(why), "why": why}
        if why:
            live_routes.add(name)
    extra_ok: dict[int, set] = collections.defaultdict(set)  # address -> routes of valid extra runs that captured it
    extra_rec: collections.Counter = collections.Counter()  # address -> records those runs kept
    extra_calls: collections.Counter = collections.Counter()  # address -> calls those runs counted
    extra_live = set()
    for rec in extra or []:
        why = route_why(rec, routes, changed_at, save_mtime, boot_now, clock_now, added)
        routes_out[rec["run"]] = {"route": rec["route"], "live": bool(why), "why": why, "extra": rec.get("session")}
        if why:
            extra_live.add(rec["route"])
            continue
        for addr in rec["only"]:
            if rec.get("kinds", {}).get(addr, "override") == "override":
                extra_ok[addr].add(rec["route"])
                extra_rec[addr] += rec.get("met", {}).get(addr, 0)
                extra_calls[addr] += rec.get("calls", {}).get(addr, 0)
    captured = set().union(*(rec["only"] for rec in records)) if records else set()
    ovr = {}
    for name, addr in sorted(overrides_now.items()):
        why = []
        then, now = targets_then.get(name), targets_now.get(name)
        if addr not in captured:
            why.append("NEW: never captured (no records)")
        elif then is None:
            if not any(t["address"] == addr and t["kind"] == "override" for t in targets_then.values()):
                why.append("NEW: not in targets.csv at the records' time")
            # else: renamed, same hook address and kind: the records still are its calls
        elif then["address"] != addr:
            why.append(f"hook address 0x{then['address']:08X} -> 0x{addr:08X}")
        if now is not None and now["kind"] != "override":
            why.append(f"kind now {now['kind']}")
        if then is not None and then["kind"] != "override":
            why.append(f"kind then {then['kind']}")
        if (conflicts or {}).get(name):
            why.append(conflicts[name])
        o = {"address": f"0x{addr:08X}", "live": bool(why), "why": why}
        if why and addr in extra_ok and not any(w.startswith("kind now") for w in why)                 and not (conflicts or {}).get(name) and not (extra_calls[addr] and not extra_rec[addr]):
            o.update(live=False, why=[], by_extra=sorted(extra_ok[addr]), main_why=why, extra_records=extra_rec[addr],
                     never_called=not extra_calls[addr] and not extra_rec[addr])
        elif why and addr in extra_ok and extra_calls[addr] and not extra_rec[addr]:
            why.append(f"the batch capture saw {extra_calls[addr]} call(s) but kept 0 records")
        ovr[name] = o
    gone = sorted(n for n, t in targets_then.items() if t["kind"] == "override" and n not in overrides_now)
    return {"runs": routes_out, "live_routes": sorted(live_routes),
            "offline_routes": sorted({r["route"] for r in routes_out.values() if not r.get("extra")} - live_routes),
            "extra_live_routes": sorted(extra_live),
            "extra_routes": sorted({r["route"] for r in routes_out.values() if r.get("extra") and not r["live"]}),
            "overrides": ovr, "live_overrides": sorted(n for n, o in ovr.items() if o["live"]),
            "extra_overrides": sorted(n for n, o in ovr.items() if o.get("by_extra")),
            "never_called_overrides": sorted(n for n, o in ovr.items() if o.get("never_called")), "gone_overrides": gone}


def route_why(rec: dict, routes: dict, changed_at: dict, save_mtime: dict, boot_now: str | None,
              clock_now: str | None, added: set | None) -> list[str]:
    """Why one run's records no longer stand for its route today (empty: they do)."""
    name, why = rec["route"], []
    r = routes.get(name)
    if r is None:
        why.append("route no longer in routes.json")
    else:
        if not rec["stage"]:  # a cheat route's earlier stage carries the whole run's run.json
            if rec["input"] != r.get("input"):
                why.append("input changed")
            if rec["frames"] != r.get("frames"):
                why.append(f"frames {rec['frames']} -> {r.get('frames')}")
        want_save = r.get("save") or par.DEFAULT_SAVE
        if rec["save"] and rec["save"] != want_save:
            why.append(f"start save {rec['save']} -> {want_save}")
        if save_mtime.get(want_save) and save_mtime[want_save] > rec["made"]:
            why.append(f"start save {want_save}.zip newer than the records")
        if changed_at.get(name) and changed_at[name] > rec["made"]:
            # a route first committed after its records (it was in the working copy then) is no change when the
            # records' own run.json shows they ran today's input, frames, save and save_at, and it has no pokes
            proven = (name in (added or set()) and not r.get("pokes") and not rec["stage"]
                      and rec["input"] == r.get("input") and rec["frames"] == r.get("frames")
                      and rec.get("save_at") == r.get("save_at") and rec["save"] == want_save
                      and bool(rec["cheat"]) == bool(r.get("cheat")))
            if not proven:
                why.append("routes.json entry changed after the records")
    if rec["outcome"] != "Completed" or rec["exit"] != 0:
        why.append(f"run did not complete ({rec['outcome']}, exit {rec['exit']})")
    if boot_now and rec["boot"] and rec["boot"] != boot_now:
        why.append("records ran another boot.exe")
    if clock_now and rec["clock"] and str(rec["clock"]) != str(clock_now):
        why.append("records ran another clock")
    return why


def expand_sessions(spec: str | None, exclude: list[str] | None = None, root: str | None = None) -> list[str]:
    """A comma list of parallel.py sessions; a part with * ? [ is a pattern over build/parallel/ (sessions that have
    records/), e.g. r12-cap-*. A pattern that matches nothing stops the plan (a typo is never 'no capture')."""
    root = PAR if root is None else root
    out: list[str] = []
    for part in [x.strip() for x in (spec or "").split(",") if x.strip()]:
        if any(c in part for c in "*?["):
            found = sorted(os.path.basename(os.path.dirname(x)) for x in glob.glob(os.path.join(root, part, "records")))
            if not found:
                raise Stop(f"session pattern {part!r}: no build/parallel/<session>/records/ matches")
            out += found
        else:
            out.append(part)
    seen = set(exclude or [])
    return [x for x in out if not (x in seen or seen.add(x))]


def targets_revs() -> dict[str, str]:
    """sha256 of config/harness/targets.csv as checked out (LF, and CRLF too) -> the newest commit with that text."""
    out: dict[str, str] = {}
    for h in filter(None, git("log", "--format=%H", "--", "config/harness/targets.csv").split()):
        r = subprocess.run(["git", "show", f"{h}:config/harness/targets.csv"], cwd=ROOT, capture_output=True)
        if r.returncode:
            continue
        lf = r.stdout.replace(b"\r\n", b"\n")
        for data in (lf, lf.replace(b"\n", b"\r\n")):
            out.setdefault(hashlib.sha256(data).hexdigest(), h)
    return out


def session_baselines(recs: list[dict], find_manifest=None, revs: dict | None = None) -> tuple[dict, list[str]]:
    """Round 13: the commit whose targets.csv each main session's records ran, from the records' own run.json:
    capture_targets_sha256 (stamped by parallel.py since round 13), else the targets_sha256 in the build manifest
    of the library named by run.json library_sha256 (parallel.find_manifest), then the commit whose targets.csv has
    that hash. Returns ({rev: sorted sessions}, problems); a problem is a run whose hooks cannot be told."""
    find_manifest = par.find_manifest if find_manifest is None else find_manifest
    revs = targets_revs() if revs is None else revs
    by_session: dict[str, set] = collections.defaultdict(set)
    problems, seen_lib = [], {}
    for r in recs:
        t = r.get("targets")
        if not t:
            if r.get("library") not in seen_lib:
                m = find_manifest(r.get("library"))
                seen_lib[r.get("library")] = m.get("targets_sha256") if m else None
            t = seen_lib[r.get("library")]
        if not t:
            problems.append(f"session {r['session']}: run {r['run']} (library {str(r.get('library'))[:12]}): run.json "
                            "has no capture_targets_sha256 and no build manifest of that library is kept")
            continue
        rev = revs.get(t)
        if not rev:
            problems.append(f"session {r['session']}: run {r['run']} ran a targets.csv (sha256 {t[:12]}) that no "
                            "commit has (edited and never committed in that form)")
            continue
        by_session[r["session"]].add(rev)
    out: dict[str, list] = collections.defaultdict(list)
    for sess, rs in sorted(by_session.items()):
        for rev in sorted(rs):
            out[rev].append(sess)
    return dict(out), problems


def merged_targets(texts: dict[str, str | None]) -> tuple[dict, dict]:
    """targets_rows over several baselines (rev -> targets.csv text): the union, and name -> why for a name whose
    row (address or kind) differs between them (its records may have run either hook: decide sends it live)."""
    rows: dict[str, dict] = {}
    seen: dict[str, dict] = collections.defaultdict(dict)
    for rev, text in sorted(texts.items()):
        for name, row in targets_rows(text).items():
            seen[name][rev] = row
            rows.setdefault(name, row)
    conflicts = {}
    for name, by_rev in seen.items():
        if len({(r["address"], r["kind"]) for r in by_rev.values()}) > 1:
            conflicts[name] = "hook differs between the records' baselines (" + ", ".join(
                f"{rev[:10]}: 0x{r['address']:08X} {r['kind']}" for rev, r in sorted(by_rev.items())) + ")"
    return rows, conflicts


def make_plan(sessions: list[str], label: str, baseline_rev: str | None = None,
              extra_sessions: list[str] | None = None) -> dict:
    import h56  # noqa: E402  (record_dirs: F-019 rule)
    dirs = h56.record_dirs(sessions, label, allow_empty=True)
    recs = [record_info(d) for d in dirs]
    extra_dirs = h56.record_dirs(extra_sessions, label, allow_empty=True) if extra_sessions else []
    extra = [record_info(d) for d in extra_dirs]
    with open(ROUTES, encoding="utf-8") as fh:
        routes = json.load(fh)["routes"]
    hl = par.headless_module()
    boot_now = sha256(hl.BOOT) if os.path.isfile(hl.BOOT) else None
    made = min(r["made"] for r in recs)
    if baseline_rev:  # given by hand: one commit for every main session (the round-12 way)
        rev = git("rev-parse", baseline_rev).strip()
        baselines = {rev: sorted({r["session"] for r in recs})}
        how = "given by --baseline-rev"
    else:
        baselines, problems = session_baselines(recs)
        if problems:
            raise Stop("cannot tell which targets.csv (hooks) these records ran, so the plan cannot say which overrides "
                       "they still decide:\n  " + "\n  ".join(problems[:8])
                       + (f"\n  ... {len(problems) - 8} more" if len(problems) > 8 else "")
                       + "\nCapture those routes again with parallel.py (it stamps run.json since round 13), or, after "
                       "checking by hand which commit's targets.csv the library was built from, give --baseline-rev REV")
        how = "from each session's run.json"
    with open(TARGETS, encoding="utf-8") as fh:
        targets_now = targets_rows(fh.read())
    targets_then, conflicts = merged_targets({rev: file_at(rev, "config/harness/targets.csv") for rev in baselines})
    overrides_now = {r["name"]: int(r["address"], 16) & ~1 for r in rcheck.registry() if r["kind"].strip() == "override"}
    names = sorted({r["route"] for r in recs + extra if r["route"]})
    hist = {n: route_history(n) for n in names}
    changed = {n: route_changed_at(n, route_fp(routes.get(n)), hist[n]) for n in names}
    added = {n for n in names if route_added_only(n, route_fp(routes.get(n)), hist[n])}
    saves = {}
    for n in names:
        s = (routes.get(n) or {}).get("save") or par.DEFAULT_SAVE
        p = os.path.join(SAVES, s + ".zip")
        if os.path.isfile(p):
            saves[s] = os.path.getmtime(p)
    d = decide(recs, routes, overrides_now, targets_then, targets_now, changed, saves, boot_now, hl.CLOCK, added,
               extra, conflicts)
    d.update(sessions=sessions, extra_sessions=list(extra_sessions or []),
             extra_record_folders=[rcheck.rel(x) for x in extra_dirs],
             label=label, baseline_rev=",".join(r[:10] for r in sorted(baselines)), baselines=baselines,
             baseline_how=how, baseline_conflicts=conflicts, record_folders=[rcheck.rel(x) for x in dirs],
             zero_record_folders=[rcheck.rel(r["dir"]) for r in recs + extra if not r["fecap"]],
             records_made=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(made)),
             route_changed={n: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)) for n, t in changed.items()})
    return d


def plan_lines(p: dict) -> list[str]:
    """Both plan lines, always (round 12, docs/collab/INTEGRATE_SLOW_R11_GROK.md): line 1 the routes (replayed
    offline or played live because they changed), line 2 the overrides (decided by records, or played live on
    which routes), then one LIVE TOTAL line. "0 routes must play live" is not "nothing plays live" while line 2
    has overrides to capture."""
    out = []
    for run, r in sorted(p["runs"].items(), key=lambda x: (bool(x[1].get("extra")), x[1]["route"] or "", x[0])):
        tag = f" [extra {r['extra']}]" if r.get("extra") else ""
        out.append(f"  {run:24s} {str(r['route']):22s} {'LIVE   ' + '; '.join(r['why']) if r['live'] else 'offline'}"
                   f"{tag}")
    lo = list(p["live_overrides"])
    ex = list(p.get("extra_overrides", []))
    lr, orr = p["live_routes"], p["offline_routes"]
    out.append(f"  PLAN LINE 1, routes: {len(orr)} replay offline from their records, {len(lr)} must play live "
               f"(route changed){': ' + ', '.join(lr) if lr else ''}")
    extra_txt = ""
    nc = list(p.get("never_called_overrides", []))
    if p.get("extra_sessions"):
        extra_txt = (f" ({len(ex)} of them by the batch's own capture {','.join(p['extra_sessions'])} on "
                     f"{len(p.get('extra_routes', []))} route(s)"
                     + (f", {len(nc)} of those watched and never called (0 records)" if nc else "")
                     + (f"; its runs on {', '.join(p['extra_live_routes'])} no longer count: route changed"
                        if p.get("extra_live_routes") else "") + ")")
    out.append(f"  PLAN LINE 2, overrides: {len(p['overrides']) - len(lo)} decided by the records{extra_txt}, "
               f"{len(lo)} must play live" + (f" on {len(orr)} route(s) ({', '.join(orr)})" if lo and orr else "")
               + (" (no unchanged route to capture them on: see line 1)" if lo and not orr else ""))
    for n in lo:
        out.append(f"    live override {n} {p['overrides'][n]['address']}: {'; '.join(p['overrides'][n]['why'])}")
    for n in ex:
        o = p["overrides"][n]
        out.append(f"    decided by extra records {n} {o['address']} on {', '.join(o['by_extra'])}"
                   + (": watched, never called (0 records)" if o.get("never_called") else
                      f": {o.get('extra_records', 0)} record(s)")
                   + f" (main records: {'; '.join(o['main_why'])})")
    if p["gone_overrides"]:
        out.append(f"  overrides gone since the records (nothing to play): {p['gone_overrides']}")
    n_live = len(lr) + (len(orr) if lo else 0)
    if not n_live:
        out.append("  LIVE TOTAL: nothing plays live (0 changed routes, 0 overrides to capture)")
    else:
        out.append(f"  LIVE TOTAL: {n_live} route run(s) play live = {len(lr)} changed route(s) (line 1) + "
                   f"{len(orr) if lo else 0} unchanged route(s) to capture {len(lo)} override(s) (line 2)")
    if lr:
        out.append("  live 1: python tools/harness/parallel.py runs " + " ".join(f"--route {r}" for r in lr)
                   + " --mode capture --only all --store-keep --session <S>")
    if lo and orr:
        out.append("  live 2 (new/changed overrides on the unchanged routes): python tools/harness/parallel.py runs "
                   + " ".join(f"--route {r}" for r in orr) + f" --mode capture --only {','.join(lo)} "
                   "--store-keep --session <S>")
    if p.get("extra_sessions"):
        out.append(f"  offline replay: python tools/harness/offline.py replay --sessions {','.join(p['sessions'])} "
                   f"--extra-sessions {','.join(p['extra_sessions'])} --label {p['label']}")
    return out


def cmd_plan(a) -> int:
    main_s = expand_sessions(a.sessions)
    p = make_plan(main_s, a.label, a.baseline_rev, expand_sessions(a.extra_sessions, main_s))
    hooks = "; ".join(f"{rev[:10]} ({', '.join(ss)})" for rev, ss in sorted(p["baselines"].items()))
    print(f"offline plan ({','.join(p['sessions'])}, label {p['label']}; records made {p['records_made']}; hooks then: "
          f"targets.csv at {hooks}, {p['baseline_how']}"
          + (f"; {len(p['zero_record_folders'])} folder(s) kept 0 records (watched, never called)"
             if p["zero_record_folders"] else "")
          + (f"; extra (batch capture): {','.join(p['extra_sessions'])}" if p["extra_sessions"] else "") + ")")
    for ln in plan_lines(p):
        print(ln)
    if a.json:
        write_atomic(os.path.abspath(a.json), json.dumps(p, indent=1))
    return 0


# ------------------------------------------------------------------ frozen trees
def cmd_tree(a) -> int:
    rev = git("rev-parse", a.rev).strip()
    name = a.name or rev[:10]
    dest = os.path.join(own_dir("trees"), name)
    if os.path.exists(dest):
        raise Stop(f"{rcheck.rel(dest)} exists (a tree is never overwritten; give --name)")
    data = git("archive", "--format=tar", rev, "src", "include", "config", "tools", text=False)
    tmp = dest + f".tmp{os.getpid()}"
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        for m in tf.getmembers():
            if m.name.startswith(("/", "..")) or ".." in m.name.split("/") or not (m.isfile() or m.isdir()):
                raise Stop(f"refusing archive member {m.name}")
        if hasattr(tarfile, "data_filter"):
            tf.extractall(tmp, filter="data")
        else:
            tf.extractall(tmp)
    info = {"rev": rev, "made": time.strftime("%Y-%m-%d %H:%M:%S"), "plant": None}
    if a.plant:
        path, old, new = a.plant.split("|", 2)
        p = os.path.join(tmp, path)
        text = open(p, encoding="utf-8").read()
        if text.count(old) != 1:
            shutil.rmtree(tmp, ignore_errors=True)
            raise Stop(f"--plant: {old!r} occurs {text.count(old)} times in {path} (must be once)")
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(text.replace(old, new))
        info["plant"] = {"path": path, "old": old, "new": new}
    with open(os.path.join(tmp, "TREE.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=1)
    os.replace(tmp, dest)
    print(f"tree {rcheck.rel(dest)}: {rev[:10]}" + (f", planted in {info['plant']['path']}" if info["plant"] else ""))
    return 0


def tree_path(a) -> str:
    if getattr(a, "rev", None):
        rev = git("rev-parse", a.rev).strip()
        t = os.path.join(OUT, "trees", rev[:10])
        if not os.path.isdir(t):
            cmd_tree(argparse.Namespace(rev=rev, name=rev[:10], plant=None))
        return t
    return os.path.abspath(a.tree) if getattr(a, "tree", None) else ROOT


def cmd_build_lib(a) -> int:
    t = os.path.abspath(a.tree)
    if not par.below(t, os.path.join(OUT, "trees")):
        raise Stop("build-lib: --tree must be a tree below build/speed/replay/trees/ (never the working tree's lib)")
    sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
    import build as B  # noqa: E402  (the working tree's find_recomp / ROM lookup only)
    recomp = B.find_recomp(None)
    rom = B.verify.find_rom(None)
    lim = par.load_limits()
    log = os.path.join(t, "build", "build-lib.log")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    cmd = [sys.executable, os.path.join(t, "tools", "harness", "build.py"), "--rom", rom, "--recomp", recomp,
           "--out", os.path.join(t, "build", "harness")]
    started = time.time()
    rc = par.run_build([], lim, cmd=cmd, log=log)
    print(f"build-lib: exit {rc} in {time.time() - started:.0f} s; log {rcheck.rel(log)}")
    return rc


# ------------------------------------------------------------------ the tree's replay.exe (a child in the tree)
def tree_build(tree: str, work: str) -> dict:
    """Runs `offline.py _tree-build` with the tree's tools first on sys.path: stage (hashes), registry, replay.exe."""
    os.makedirs(work, exist_ok=True)
    out = os.path.join(work, "tree.json")
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "_tree-build", "--tree", tree, "--work", work],
                       capture_output=True, text=True)
    if r.returncode or not os.path.isfile(out):
        raise Stop(f"replay build in {rcheck.rel(tree)} failed:\n{(r.stdout + r.stderr)[-3000:]}")
    with open(out, encoding="utf-8") as fh:
        return json.load(fh)


def tree_build_child(tree: str, work: str) -> int:
    for p in (os.path.join(tree, "tools", "readable"), os.path.join(tree, "tools", "harness")):
        sys.path.insert(0, p)
    for m in ("harness", "build", "check", "gen_stubs", "stage", "verify", "gamecfg"):
        sys.modules.pop(m, None)
    import build as B  # noqa: E402  (the tree's)
    import harness as TH  # noqa: E402
    stage_dir = os.path.join(tree, "build", f"offline-stage-{os.getpid()}") if os.path.abspath(tree) != ROOT else \
        os.path.join(work, "stage")
    try:
        staged, probes = B.stage_all(stage_dir, say=lambda *_a, **_k: None)
        hashes = {os.path.basename(p): B.sha256(p) for p in staged + probes}
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
    cc = TH.rcheck.find_cc()
    lib_dir = os.path.join(work, "lib")
    ok, msg = TH.abi_gate(cc, lib_dir, os.path.join(work, "abi"))
    if not ok:
        print(msg)
        return 1
    table = os.path.join(work, "overrides_table.c")
    n = TH.write_table(table)
    exe, err = TH.build_replay(cc, os.path.join(work, "replay"), TH.readable_sources() + [table])
    if exe is None:
        print(err[-3000:])
        return 1
    reg = [{k: r[k] for k in ("name", "address", "kind", "source")} for r in TH.rcheck.registry()]
    info = {"tree": tree, "staged": hashes, "targets_sha256": B.sha256(B.gen_stubs.TARGETS), "abi": msg, "exe": exe,
            "overrides": n, "registry": reg, "wide": TH.wide_results(), "cc": cc}
    with open(os.path.join(work, "tree.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=1)
    return 0


# ------------------------------------------------------------------ replay
def summary_rows(rows: list[dict], live_calls: dict[str, int]) -> list[dict]:
    """One row per address in the live summary.tsv's shape, from offline replay rows (H.classify: the capture.c
    verdict rule without the guard-user half, as the live summary.tsv writes it)."""
    fns = H.classify(rows, set())
    out = []
    for a, f in sorted(fns.items()):
        v = f["verdicts"]
        row = {"address": a, "kind": f["kind"], "verdict": f["verdict"], "calls": live_calls.get(a, 0),
               "records": f["records"], "cold": f["cold"], "warm": f["warm"], "deep": f["deep"],
               "kept": f["records"], "paths": len(f["sigs"]),
               "signatures": ";".join(f"{s:08x}:{n}" for s, n in sorted(f["sigs"].items()))}
        for k in H.VNAMES[1:] + ["mismatch_regs", "damaged"]:
            row[k] = v.get(k, 0)
        out.append(row)
    return out


def summary_text(rows: list[dict], note: str) -> str:
    lines = [f"# fe-capture summary, OFFLINE (tools/harness/offline.py): {note}", "\t".join(COLS)]
    for r in rows:
        lines.append("\t".join(str(r.get(c, "")) for c in COLS))
    return "\n".join(lines) + "\n"


def replay_one(exe: str, lib: str, d: str, out: str, wide: list[str]) -> dict:
    """Original side (must be clean: the harness is faithful), then readable side. Record folder only read."""
    os.makedirs(out, exist_ok=True)
    res = {"dir": d, "run": os.path.basename(d)}
    for side in ("original", "readable"):
        jl = os.path.join(out, f"replay_{side}.jsonl")
        cmd = [exe, "run", "--lib", lib, "--dir", os.path.abspath(d), "--side", side, "--out", jl]
        if wide:
            cmd += ["--wide", ",".join(wide)]
        t0 = time.time()
        rc, text = H.run(cmd, {"FE_READABLE": "original", "FE_READABLE_LOG": os.path.join(out, f"fe_readable_{side}.log")},
                         timeout=3600)
        rows = []
        if os.path.isfile(jl):
            with open(jl, encoding="utf-8") as fh:
                rows = [json.loads(ln) for ln in fh if ln.strip()]
            os.remove(jl)
        res[side] = {"rc": rc, "seconds": round(time.time() - t0, 1), "rows": rows, "tail": text[-400:] if rc else ""}
    return res


def cmd_replay(a) -> int:
    import h56  # noqa: E402
    prio, jobs = h56.lower_priority()
    jobs = min(a.jobs or jobs, jobs)
    name = a.name or f"replay-{time.strftime('%Y%m%d-%H%M%S')}"
    out = own_dir(name)
    if os.path.exists(out):
        raise Stop(f"{rcheck.rel(out)} exists: give another --name")
    started = time.time()
    tree = tree_path(a)
    main_s = expand_sessions(a.sessions)
    extra_s = expand_sessions(a.extra_sessions, main_s)
    dirs = h56.record_dirs(main_s, a.label, allow_empty=True)
    extra_dirs = h56.record_dirs(extra_s, a.label, allow_empty=True) if extra_s else []
    want = set(a.routes.split(",")) if a.routes else None
    dirs = [d for d in dirs if want is None or record_info(d)["route"] in want]
    extra_dirs = [d for d in extra_dirs if want is None or record_info(d)["route"] in want]
    plan = None
    if not a.ignore_plan:
        plan = make_plan(main_s, a.label, a.baseline_rev, extra_s)
        skip = set(plan["live_routes"])
        left = [d for d in dirs if record_info(d)["route"] in skip]
        dirs = [d for d in dirs if record_info(d)["route"] not in skip]
        if left:
            print(f"offline: {len(left)} record folder(s) left out, their routes must play live: {sorted(skip)}")
        xleft = [d for d in extra_dirs if plan["runs"].get(os.path.basename(d), {}).get("live")]
        extra_dirs = [d for d in extra_dirs if d not in xleft]
        if xleft:
            print(f"offline: {len(xleft)} extra record folder(s) left out (route changed after the batch capture): "
                  f"{[os.path.basename(d) for d in xleft]}")
    dirs += extra_dirs
    empty = [d for d in dirs if not os.path.isfile(os.path.join(d, "records.fecap"))]
    if empty:  # round 13: a run that kept 0 records (watched, never called): nothing to replay
        dirs = [d for d in dirs if d not in empty]
        print(f"offline: {len(empty)} folder(s) kept 0 records (watched, never called): nothing to replay")
    if not dirs:
        raise Stop("no record folder left to replay")
    lib_src = H.find_lib(a.lib)
    if lib_src is None:
        raise Stop(f"no library {a.lib or '(build/harness/lib)'}")
    lib_dir = os.path.join(out, "lib")
    os.makedirs(lib_dir)
    lib = os.path.join(lib_dir, os.path.basename(lib_src))
    shutil.copy2(lib_src, lib)  # loaded from the copy: build/harness/lib is never held open
    for extra in ("recomp.h", "harness_build.json"):
        if os.path.isfile(os.path.join(os.path.dirname(lib_src), extra)):
            shutil.copy2(os.path.join(os.path.dirname(lib_src), extra), os.path.join(lib_dir, extra))
    lib_sha = sha256(lib)
    print(f"offline {name}: tree {rcheck.rel(tree) if tree != ROOT else '(working tree)'}, library "
          f"{rcheck.rel(lib_src)} ({lib_sha[:12]}), {len(dirs)} record folder(s), {jobs} at once, priority {prio}")
    try:
        return replay_with(a, name, out, started, tree, dirs, plan, lib_src, lib, lib_sha, jobs)
    finally:
        if os.path.isfile(lib):
            os.remove(lib)  # 120 MB; its hash stays in offline.json
        for sub in ("work", "replay"):
            shutil.rmtree(os.path.join(out, sub), ignore_errors=True)


def source_gate(man: dict, lib_sha: str, info: dict) -> list[str]:
    """Why the tree's staged code is not the library's (empty: it is). man: the library's harness_build.json;
    info: tree_build's targets_sha256 and staged hashes. Pure, tested by the self-test."""
    gate = []
    if not man.get("library_sha256") or man.get("library_sha256") != lib_sha:
        gate.append("the library is not the one its harness_build.json describes")
    if man.get("targets_sha256") != info["targets_sha256"]:
        gate.append("targets.csv of the tree differs from the library's")
    was = man.get("staged") or {}
    diff = sorted(k for k in set(was) | set(info["staged"]) if was.get(k) != info["staged"].get(k))
    if diff:
        gate.append(f"{len(diff)} staged file(s) differ from the library's build: {diff[:4]}")
    return gate


def replay_with(a, name, out, started, tree, dirs, plan, lib_src, lib, lib_sha, jobs) -> int:
    lib_dir = os.path.dirname(lib)
    info = tree_build(tree, out)
    man = {}
    if os.path.isfile(os.path.join(lib_dir, "harness_build.json")):
        with open(os.path.join(lib_dir, "harness_build.json"), encoding="utf-8") as fh:
            man = json.load(fh)
    gate = source_gate(man, lib_sha, info)
    gate_line = "replayed code = the library's readable code (staged hashes and targets.csv equal its manifest)" \
        if not gate else "NOT the library's code: " + "; ".join(gate)
    print(f"offline: source gate: {gate_line}")
    if gate and not a.no_source_gate:
        raise Stop("source gate failed (the offline verdicts would not be the library's); --no-source-gate to see them anyway")
    print(f"offline: replay.exe built from the tree in {time.time() - started:.0f} s ({info['overrides']} override(s); {info['abi']})")
    names = {int(r["address"], 16) & ~1: r["name"] for r in info["registry"] if r["kind"].strip() == "override"}
    t1 = time.time()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        futs = [ex.submit(replay_one, info["exe"], lib, d, os.path.join(out, "work", os.path.basename(d)), info["wide"])
                for d in dirs]
        for f in futs:
            results.append(f.result())
    replay_s = round(time.time() - t1, 1)
    rows_out, harness_bad, per_record = [], [], {"records": 0, "differ": 0}
    os.makedirs(os.path.join(out, "results"), exist_ok=True)
    for res in results:
        d, ri = res["dir"], record_info(res["dir"])
        o, r = res["original"], res["readable"]
        bad_o = [x for x in o["rows"] if x["verdict"] in H.BAD]
        if o["rc"] or bad_o or not o["rows"]:
            harness_bad.append(f"{rcheck.rel(d)}: original vs original rc {o['rc']}, {len(bad_o)} bad, {len(o['rows'])} row(s)")
        if r["rc"]:
            harness_bad.append(f"{rcheck.rel(d)}: readable replay rc {r['rc']}: {r['tail']}")
        live_calls = {}
        if os.path.isfile(os.path.join(d, "summary.tsv")):
            live_calls = {k: v["calls"] for k, v in H.read_summary(os.path.join(d, "summary.tsv")).items()}
        srows = summary_rows(r["rows"], live_calls)
        tsv = os.path.join(out, "results", f"{res['run']}.summary.tsv")
        write_atomic(tsv, summary_text(srows, f"records {rcheck.rel(d)}, library {lib_sha[:12]}"))
        cap = par.capture_totals([tsv])
        cap["problem"] = par.capture_problem(cap)
        differ = sum(1 for x in r["rows"] if x["verdict"] != x.get("live"))
        per_record["records"] += len(r["rows"])
        per_record["differ"] += differ
        bad_fns = sorted({names.get(int(x["address"], 16) & ~1, x["address"]) for x in r["rows"] if x["verdict"] in H.BAD})
        rows_out.append({"run": res["run"], "route": ri["route"], "ok": not cap["problem"] and not r["rc"], "capture": cap,
                         "cheat": ri["cheat"], "records_vs_their_live": differ, "bad_overrides": bad_fns,
                         "seconds": {"original": o["seconds"], "readable": r["seconds"]}})
        print(f"  {res['run']:24s} {str(ri['route']):22s} {len(r['rows']):5d} record(s) original "
              f"{'clean' if not any(rcheck.rel(d) + ':' in x for x in harness_bad) else 'NOT CLEAN'}; "
              f"{'PASS' if rows_out[-1]['ok'] else 'FAIL: ' + str(cap['problem'] or r['tail'])}"
              + (f"; bad in {bad_fns}" if bad_fns else ""))
    honest = [x for x in rows_out if not x["cheat"]]
    cheat = [x for x in rows_out if x["cheat"]]
    totals = {"honest": par.capture_table(honest, "real-play runs, OFFLINE"),
              "cheat": par.capture_table(cheat, "CHEAT runs (scored separately), OFFLINE")}
    wall = round(time.time() - started, 1)
    good = not harness_bad and all(x["ok"] for x in rows_out)
    summary = {"name": name, "tree": rcheck.rel(tree) if tree != ROOT else ".", "tree_info": {
        k: info[k] for k in ("targets_sha256", "overrides", "abi", "cc")}, "library": rcheck.rel(lib_src),
        "library_sha256": lib_sha, "source_gate": gate_line, "sessions": a.sessions.split(","), "label": a.label,
        "runs": rows_out, "capture_totals": totals, "harness_problems": harness_bad, "plan": plan,
        "records_vs_their_live": per_record, "wall_seconds": wall, "replay_seconds": replay_s, "jobs": jobs,
        "verdict": "PASS" if good else "FAIL"}
    write_atomic(os.path.join(out, "offline.json"), json.dumps(summary, indent=1))
    for p in harness_bad:
        print(f"  HARNESS PROBLEM: {p}")
    print(f"offline {name}: {summary['verdict']}; {per_record['records']} record(s), offline verdict != the verdict the "
          f"record was captured with: {per_record['differ']}; wall {wall} s (replays {replay_s} s); "
          f"{rcheck.rel(os.path.join(out, 'offline.json'))}")
    return 0 if good else 1


# ------------------------------------------------------------------ compare with a live capture
def live_tables(where: str) -> dict[str, dict]:
    """route[.stageK] -> {address: summary row} from a live capture: a session folder with results/<run>.json and
    results/<run>[.stageK].summary.tsv, or a records/ session (records/<run>/run.json, summary.tsv)."""
    for cand in (where, os.path.join(PAR, where), os.path.join(ROOT, "build", "evidence", where), os.path.join(OUT, where)):
        if os.path.isdir(cand):
            where = cand
            break
    else:
        raise Stop(f"no live capture folder {where}")
    out = {}
    if os.path.isfile(os.path.join(where, "offline.json")):  # another offline run, for offline vs offline
        with open(os.path.join(where, "offline.json"), encoding="utf-8") as fh:
            for r in json.load(fh)["runs"]:
                tag = re.search(r"(\.stage\d+)$", r["run"])
                out[r["route"] + (tag.group(1) if tag else "")] = H.read_summary(
                    os.path.join(where, "results", f"{r['run']}.summary.tsv"))
        return out
    for rj in glob.glob(os.path.join(where, "results", "*.json")):
        run = os.path.splitext(os.path.basename(rj))[0]
        with open(rj, encoding="utf-8") as fh:
            route = (json.load(fh).get("row") or {}).get("route")
        for tsv in glob.glob(os.path.join(where, "results", f"{run}*.summary.tsv")):
            tag = os.path.basename(tsv)[len(run):-len(".summary.tsv")]
            if tag and not re.fullmatch(r"\.stage\d+", tag):
                continue
            out[f"{route}{tag}"] = H.read_summary(tsv)
    for d in glob.glob(os.path.join(where, "records", "*")):
        if os.path.isfile(os.path.join(d, "summary.tsv")):
            ri = record_info(d)
            tag = re.search(r"(\.stage\d+)$", ri["run"])
            out[ri["route"] + (tag.group(1) if tag else "")] = H.read_summary(os.path.join(d, "summary.tsv"))
    return out


# round 9: escaped is compared too (a live escape the records cannot show is a difference); hostmem and truncated
# are the harness's own bookkeeping
CMP_KEYS = ["records"] + [k for k in H.VNAMES[1:] if k not in ("hostmem", "truncated")]


def compare_tables(off: dict[str, dict], live: dict[str, dict]) -> dict:
    """Per route and override: records, verdict counts (CMP_KEYS) and the verdict label must be equal."""
    common = sorted(set(off) & set(live))
    pairs = differ = 0
    details = []
    labels_bad = []
    for route in common:
        a, b = off[route], live[route]
        for addr in sorted(set(a) | set(b)):
            x, y = a.get(addr), b.get(addr)
            pairs += 1
            if x is None or y is None:
                differ += 1
                details.append(f"{route} {addr}: only {'live' if x is None else 'offline'} has it")
                continue
            dx = {k: (x["records"] if k == "records" else x["verdicts"].get(k, 0)) for k in CMP_KEYS}
            dy = {k: (y["records"] if k == "records" else y["verdicts"].get(k, 0)) for k in CMP_KEYS}
            if dx != dy or x["verdict"] != y["verdict"]:
                differ += 1
                details.append(f"{route} {addr}: offline {x['verdict']} {dict((k, v) for k, v in dx.items() if v)} vs live "
                               f"{y['verdict']} {dict((k, v) for k, v in dy.items() if v)}")
                if x["verdict"] != y["verdict"]:
                    labels_bad.append(f"{route} {addr}")
    return {"routes_compared": len(common), "only_offline": sorted(set(off) - set(live)),
            "only_live": sorted(set(live) - set(off)), "pairs": pairs, "equal": pairs - differ, "differ": differ,
            "label_differ": len(labels_bad), "details": details[:60],
            "records_offline": sum(f["records"] for r in common for f in off[r].values()),
            "records_live": sum(f["records"] for r in common for f in live[r].values())}


def compare_exit(c: dict, one_side_ok: bool = False) -> int:
    """0 only when at least one route was compared, no pair differs and (unless one_side_ok) no route is on one
    side only."""
    if not c["routes_compared"] or c["differ"]:
        return 1
    if not one_side_ok and (c["only_offline"] or c["only_live"]):
        return 1
    return 0


def cmd_compare(a) -> int:
    off = live_tables(own_dir(a.offline))
    live = live_tables(a.live)
    c = compare_tables(off, live)
    c["routes_one_side"] = len(c["only_offline"]) + len(c["only_live"])
    print(f"compare offline {a.offline} vs live {a.live}: routes_compared {c['routes_compared']}, "
          f"{c['routes_one_side']} route(s) on one side only; {c['pairs']} (route, override) "
          f"pair(s): {c['equal']} equal, {c['differ']} differ ({c['label_differ']} verdict label(s)); records "
          f"{c['records_offline']} offline vs {c['records_live']} live"
          + (f"; only offline: {c['only_offline']}" if c["only_offline"] else "")
          + (f"; only live: {c['only_live']}" if c["only_live"] else ""))
    for x in c["details"]:
        print("  " + x)
    if a.json:
        write_atomic(os.path.abspath(a.json), json.dumps(c, indent=1))
    rc = compare_exit(c, getattr(a, "one_side_ok", False))
    if c["routes_one_side"] and not getattr(a, "one_side_ok", False):
        print("compare: routes on one side only count as a difference (--one-side-ok when the plan sent them live)")
    return rc


# ------------------------------------------------------------------ self-test
def selftest() -> int:
    errs = []

    def expect(cond, what):
        if not cond:
            errs.append(what)
    r_ok = {"input": "10:A", "frames": 100, "save": "s1", "save_at": 90}
    routes = {"a": dict(r_ok), "b": dict(r_ok, input="10:B"), "c": dict(r_ok)}

    def rec(route, **kw):
        base = {"dir": f"x/{route}", "run": f"run-{route}", "route": route, "input": routes.get(route, r_ok)["input"],
                "frames": 100, "save": "s1", "clock": "1", "boot": "B", "outcome": "Completed", "exit": 0,
                "library": "L", "only": {0x100, 0x200}, "met": {0x100: 3}, "made": 1000.0, "cheat": False, "stage": False,
                "save_at": 90}
        base.update(kw)
        return base
    tt = {"f": {"address": 0x100, "kind": "override"}, "g": {"address": 0x200, "kind": "override"}}
    d = decide([rec("a"), rec("b", input="10:A"), rec("c"), rec("gone")], routes, {"f": 0x100, "g": 0x200}, tt, tt,
               {"a": 900.0, "b": 900.0, "c": 1100.0}, {"s1": 500.0}, "B", "1")
    expect(d["runs"]["run-a"]["live"] is False, "an unchanged route went live")
    expect(d["runs"]["run-b"]["live"] and "input changed" in d["runs"]["run-b"]["why"], "a changed input stayed offline")
    expect(d["runs"]["run-c"]["live"] and any("after the records" in w for w in d["runs"]["run-c"]["why"]),
           "records older than the route's last change stayed offline")
    expect(d["runs"]["run-gone"]["live"], "a route gone from routes.json stayed offline")
    expect(d["live_overrides"] == [], f"unchanged overrides went live: {d['live_overrides']}")
    d = decide([rec("c", save_at=90)], routes, {"f": 0x100}, tt, tt, {"c": 1100.0}, {}, "B", "1", {"c"})
    expect(not d["runs"]["run-c"]["live"], "a route only committed after its records (records ran it) went live")
    d = decide([rec("c", save_at=80)], routes, {"f": 0x100}, tt, tt, {"c": 1100.0}, {}, "B", "1", {"c"})
    expect(d["runs"]["run-c"]["live"], "a route committed after its records with another save_at stayed offline")
    expect(route_added_only("a", fp_ := route_fp(r_ok), [(300.0, fp_), (200.0, None)]), "first commit not seen as added")
    expect(not route_added_only("a", fp_, [(300.0, fp_), (200.0, "old")]), "a real change seen as added")
    expect(route_added_only("a", fp_, [(300.0, None)]) and route_added_only("a", fp_, []),
           "a route only in the working copy not seen as added")
    expect(not route_added_only("a", fp_, [(300.0, "old")]), "a working-copy edit of a committed route seen as added")
    d = decide([rec("c", input="10:Z")], routes, {"f": 0x100}, tt, tt, {"c": 1100.0}, {}, "B", "1", {"c"})
    expect(d["runs"]["run-c"]["live"], "an added route whose records ran another input stayed offline")
    d = decide([rec("c")], dict(routes, c=dict(r_ok, pokes=[{"frame": 1}])), {"f": 0x100}, tt, tt, {"c": 1100.0}, {},
               "B", "1", {"c"})
    expect(d["runs"]["run-c"]["live"], "an added route with pokes (not provable from run.json) stayed offline")
    d = decide([rec("a")], routes, {"f": 0x100}, tt, tt, {}, {"s1": 2000.0}, "B", "1")
    expect(d["runs"]["run-a"]["live"], "a start save newer than the records stayed offline")
    d = decide([rec("a", boot="OTHER")], routes, {"f": 0x100}, tt, tt, {}, {}, "B", "1")
    expect(d["runs"]["run-a"]["live"], "records of another boot.exe stayed offline")
    d = decide([rec("a", outcome="Timeout", exit=1)], routes, {"f": 0x100}, tt, tt, {}, {}, "B", "1")
    expect(d["runs"]["run-a"]["live"], "an incomplete run's records stayed offline")
    now = dict(tt, h={"address": 0x300, "kind": "override"}, g={"address": 0x204, "kind": "override"})
    d = decide([rec("a")], routes, {"f": 0x100, "g": 0x204, "h": 0x300}, tt, now, {}, {}, "B", "1")
    expect("h" in d["live_overrides"] and any("NEW" in w for w in d["overrides"]["h"]["why"]), "a new override stayed offline")
    expect("g" in d["live_overrides"], "a moved hook address stayed offline")
    expect("f" not in d["live_overrides"], "an unchanged override went live")
    d = decide([rec("a", only={0x100, 0x200, 0x300})], routes, {"f": 0x100, "h": 0x300}, tt,
               dict(tt, h={"address": 0x300, "kind": "override"}), {}, {}, "B", "1")
    expect("h" in d["live_overrides"], "an override not in targets.csv at the records' time stayed offline")
    d = decide([rec("a")], routes, {"f": 0x100}, tt, tt, {}, {}, "B", "1")
    expect(d["gone_overrides"] == ["g"], "a removed override was not listed")
    # route change time from history
    fp = route_fp(r_ok)
    expect(route_changed_at("a", fp, [(300.0, fp), (200.0, fp), (100.0, "old")], 999.0) == 200.0,
           "route change time: not the oldest commit of the newest equal run")
    expect(route_changed_at("a", fp, [(300.0, "other")], 999.0) == 999.0, "a working-copy change did not use the mtime")
    expect(route_fp(dict(r_ok, about="words", shots=[1])) == fp, "about/shots changed the route fingerprint")
    # offline summary rows: the live table's columns and rule
    rows = [{"address": "0x00000100", "kind": "override", "verdict": "match", "live": "match", "signature": "80001004",
             "cold": 0, "call": i, "detail": ""} for i in range(9)]
    rows.append({"address": "0x00000200", "kind": "override", "verdict": "mismatch_r0", "live": "match",
                 "signature": "80001004", "cold": 0, "call": 1, "detail": "r0"})
    s = summary_rows(rows, {"0x00000100": 40})
    expect([x["verdict"] for x in s] == ["SHALLOW", "MISMATCH"], f"offline verdict labels {[x['verdict'] for x in s]}")
    expect(s[0]["calls"] == 40 and s[0]["records"] == 9 and s[0]["match"] == 9, "offline counts")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "x.summary.tsv")
        write_atomic(p, summary_text(s, "selftest"))
        cap = par.capture_totals([p])
        expect(cap["records"] == 10 and cap["bad"] == 1 and par.capture_problem(cap), "parallel's pass rule on an offline table")
        back = H.read_summary(p)
        expect(back["0x00000200"]["verdicts"]["mismatch_r0"] == 1 and back["0x00000100"]["verdict"] == "SHALLOW",
               "an offline summary.tsv does not read back")
        c = compare_tables({"r": back}, {"r": back})
        expect(c["differ"] == 0 and c["pairs"] == 2, "a table differs from itself")
        other = json.loads(json.dumps(back))
        other["0x00000200"]["verdicts"]["mismatch_r0"] = 0
        other["0x00000200"]["verdicts"]["match"] = 1
        other["0x00000200"]["verdict"] = "SHALLOW"
        c = compare_tables({"r": back}, {"r": other})
        expect(c["differ"] == 1 and c["label_differ"] == 1, "a planted difference went unnoticed")
        expect(compare_exit(c) == 1, "compare exit 0 with a differing pair")
        # round 9: escaped counts, one-sided routes, routes_compared and the exit code
        esc = json.loads(json.dumps(back))
        esc["0x00000100"]["verdicts"]["escaped"] = 2
        c = compare_tables({"r": back}, {"r": esc})
        expect(c["differ"] == 1 and c["label_differ"] == 0, "an escaped-count difference went unnoticed")
        c = compare_tables({"r": back}, {"r": back})
        expect(compare_exit(c) == 0 and c["routes_compared"] == 1, "compare exit/routes_compared on equal tables")
        c = compare_tables({"r": back, "x": back}, {"r": back, "y": back})
        expect(c["routes_compared"] == 1 and c["only_offline"] == ["x"] and c["only_live"] == ["y"],
               "routes on one side not listed")
        expect(compare_exit(c) == 1 and compare_exit(c, one_side_ok=True) == 0, "one-sided routes: exit code")
        c = compare_tables({"x": back}, {"y": back})
        expect(c["routes_compared"] == 0 and compare_exit(c, one_side_ok=True) == 1, "nothing compared gave exit 0")
    # round 9: the source gate
    info = {"targets_sha256": "T", "staged": {"a.c": "1", "b.c": "2"}}
    man = {"library_sha256": "L", "targets_sha256": "T", "staged": {"a.c": "1", "b.c": "2"}}
    expect(source_gate(man, "L", info) == [], "source gate: the library's own tree refused")
    expect(len(source_gate(man, "OTHER", info)) == 1, "source gate: another library passed")
    expect(len(source_gate({}, "L", info)) == 3 and len(source_gate(dict(man, library_sha256=None), None, info)) == 1,
           "source gate: no manifest passed")
    expect(any("targets.csv" in g for g in source_gate(dict(man, targets_sha256="U"), "L", info)),
           "source gate: another targets.csv passed")
    g = source_gate(dict(man, staged={"a.c": "1", "b.c": "X"}), "L", info)
    expect(len(g) == 1 and "b.c" in g[0], "source gate: a changed staged file passed")
    g = source_gate(dict(man, staged={"a.c": "1"}), "L", info)
    expect(len(g) == 1 and "b.c" in g[0], "source gate: a staged file the library lacks passed")
    # round 9: decide's remaining branches
    d = decide([rec("a", frames=90)], routes, {"f": 0x100}, tt, tt, {}, {}, "B", "1")
    expect(d["runs"]["run-a"]["live"] and any(w.startswith("frames 90") for w in d["runs"]["run-a"]["why"]),
           "changed frames stayed offline")
    d = decide([rec("a", frames=90, stage=True)], routes, {"f": 0x100}, tt, tt, {}, {}, "B", "1")
    expect(not d["runs"]["run-a"]["live"], "a stage folder's whole-run frames sent it live")
    d = decide([rec("a", clock="2")], routes, {"f": 0x100}, tt, tt, {}, {}, "B", "1")
    expect(d["runs"]["run-a"]["live"] and "records ran another clock" in d["runs"]["run-a"]["why"],
           "another clock stayed offline")
    d = decide([rec("a", save="s0")], routes, {"f": 0x100}, tt, tt, {}, {}, "B", "1")
    expect(d["runs"]["run-a"]["live"] and "start save s0 -> s1" in d["runs"]["run-a"]["why"],
           "another start save name stayed offline")
    d = decide([rec("a", exit=3)], routes, {"f": 0x100}, tt, tt, {}, {}, "B", "1")
    expect(d["runs"]["run-a"]["live"], "a completed run with a non-zero exit stayed offline")
    probe_now = dict(tt, f={"address": 0x100, "kind": "probe"})
    d = decide([rec("a")], routes, {"f": 0x100}, tt, probe_now, {}, {}, "B", "1")
    expect("kind now probe" in d["overrides"]["f"]["why"], "an override that is a probe now stayed offline")
    d = decide([rec("a")], routes, {"f": 0x100}, probe_now, tt, {}, {}, "B", "1")
    expect("kind then probe" in d["overrides"]["f"]["why"], "an override that was a probe then stayed offline")
    renamed = {"f2": {"address": 0x100, "kind": "override"}, "g": tt["g"]}
    d = decide([rec("a")], routes, {"f": 0x100}, renamed, tt, {}, {}, "B", "1")
    expect(not d["overrides"]["f"]["live"], "a renamed override (same hook address and kind) went live")
    d = decide([rec("a")], routes, {"f": 0x100}, {"f2": {"address": 0x100, "kind": "probe"}}, tt, {}, {}, "B", "1")
    expect(d["overrides"]["f"]["live"] and "NEW" in d["overrides"]["f"]["why"][0],
           "a renamed probe counted as the override's records")
    d = decide([rec("a")], routes, {"f": 0x104}, tt, dict(tt, f={"address": 0x104, "kind": "override"}), {}, {}, "B", "1")
    expect(d["overrides"]["f"]["live"], "a moved hook whose new address was never captured stayed offline")
    d = decide([rec("a", only={0x100, 0x104, 0x200})], routes, {"f": 0x104}, tt,
               dict(tt, f={"address": 0x104, "kind": "override"}), {}, {}, "B", "1")
    expect(d["overrides"]["f"]["why"] == ["hook address 0x00000100 -> 0x00000104"], "the moved-hook branch")
    # round 12: --extra-sessions (the batch's own capture) and both plan lines
    now3 = dict(tt, h={"address": 0x300, "kind": "override"})
    ovr3 = {"f": 0x100, "g": 0x200, "h": 0x300}
    xrec = rec("a", run="r12-cap-a-1", session="r12-cap-a", only={0x300}, kinds={0x300: "override"}, made=2000.0,
               met={0x300: 5}, calls={0x300: 9})
    d = decide([rec("a"), rec("c")], routes, ovr3, tt, now3, {"c": 900.0}, {}, "B", "1", None, [xrec])
    expect(d["live_overrides"] == [] and d["extra_overrides"] == ["h"] and d["overrides"]["h"]["by_extra"] == ["a"]
           and "NEW" in d["overrides"]["h"]["main_why"][0], f"an override captured by the extra session went live ({d['overrides']['h']})")
    expect(d["runs"]["r12-cap-a-1"]["extra"] == "r12-cap-a" and d["offline_routes"] == ["a", "c"]
           and d["extra_routes"] == ["a"], f"the extra run is listed apart from the main routes ({d['offline_routes']})")
    lines = plan_lines(dict(d, sessions=["s"], extra_sessions=["r12-cap-a"], label="play"))
    txt = "\n".join(lines)
    expect(any(x.startswith("  PLAN LINE 1, routes: 2 replay offline") for x in lines)
           and any(x.startswith("  PLAN LINE 2, overrides: 3 decided by the records (1 of them by the batch's own "
                                "capture r12-cap-a on 1 route(s))") for x in lines)
           and "LIVE TOTAL: nothing plays live" in txt and "--extra-sessions r12-cap-a" in txt
           and "decided by extra records h 0x00000300 on a" in txt, "plan lines with the extra session:\n" + txt)
    # without the extra session the same override must play live on every unchanged route, and the total says so
    d = decide([rec("a"), rec("c")], routes, ovr3, tt, now3, {"c": 900.0}, {}, "B", "1")
    lines = plan_lines(dict(d, sessions=["s"], extra_sessions=[], label="play"))
    txt = "\n".join(lines)
    expect(d["live_overrides"] == ["h"] and "PLAN LINE 1, routes: 2 replay offline from their records, 0 must play live"
           in txt and "PLAN LINE 2, overrides: 2 decided by the records, 1 must play live on 2 route(s) (a, c)" in txt
           and "LIVE TOTAL: 2 route run(s) play live = 0 changed route(s) (line 1) + 2 unchanged route(s) to capture "
           "1 override(s) (line 2)" in txt and "live override h 0x00000300: NEW: never captured" in txt
           and "--only h " in txt and "nothing plays live" not in txt, "0 changed routes read as nothing live:\n" + txt)
    # a changed route and a new override: both counted in the total, both commands printed
    d = decide([rec("a"), rec("b", input="10:A")], routes, ovr3, tt, now3, {}, {}, "B", "1")
    txt = "\n".join(plan_lines(dict(d, sessions=["s"], extra_sessions=[], label="play")))
    expect("LIVE TOTAL: 2 route run(s) play live = 1 changed route(s) (line 1) + 1 unchanged route(s)" in txt
           and "live 1: " in txt and "live 2 " in txt, "a changed route plus a new override:\n" + txt)
    # the extra run's route changed after its capture: its records no longer decide anything
    d = decide([rec("a")], routes, ovr3, tt, now3, {"b": 3000.0}, {}, "B", "1", None,
               [dict(xrec, route="b", input="10:B")])
    expect(d["live_overrides"] == ["h"] and d["extra_live_routes"] == ["b"] and d["runs"]["r12-cap-a-1"]["live"],
           f"an extra run on a changed route still decided an override ({d['overrides']['h']})")
    # the extra run captured another address (the hook moved after the batch capture): still NEW
    d = decide([rec("a")], routes, ovr3, tt, now3, {}, {}, "B", "1", None, [dict(xrec, only={0x304}, kinds={})])
    expect(d["live_overrides"] == ["h"], "an extra capture of another address decided the override")
    # the extra run's summary lists the address as a probe: not the override's records
    d = decide([rec("a")], routes, ovr3, tt, now3, {}, {}, "B", "1", None, [dict(xrec, kinds={0x300: "probe"})])
    expect(d["live_overrides"] == ["h"], "an extra capture of the address as a probe decided the override")
    # an incomplete extra run does not count
    d = decide([rec("a")], routes, ovr3, tt, now3, {}, {}, "B", "1", None, [dict(xrec, outcome="Timeout", exit=1)])
    expect(d["live_overrides"] == ["h"], "an incomplete extra run decided the override")
    # "kind now ..." stays live even when an extra run captured the address
    d = decide([rec("a")], routes, {"f": 0x100}, tt, dict(tt, f={"address": 0x100, "kind": "probe"}), {}, {}, "B", "1",
               None, [dict(xrec, only={0x100}, kinds={})])
    expect(d["overrides"]["f"]["live"], "an override that is a probe now was decided by an extra run")
    # a moved hook whose new address the extra session captured is decided
    d = decide([rec("a")], routes, {"f": 0x104}, tt, dict(tt, f={"address": 0x104, "kind": "override"}), {}, {}, "B",
               "1", None, [dict(xrec, only={0x104}, kinds={})])
    expect(not d["overrides"]["f"]["live"] and d["overrides"]["f"]["by_extra"] == ["a"],
           "a moved hook captured at its new address by the extra session stayed live")
    # round 13: an extra run that kept 0 records (no records.fecap) watched h and never saw it called: decided
    zrec = dict(xrec, run="r12-cap-w-1", session="r12-cap-w", met={}, calls={}, kinds={}, fecap=False)
    d = decide([rec("a"), rec("c")], routes, ovr3, tt, now3, {"c": 900.0}, {}, "B", "1", None, [zrec])
    o = d["overrides"]["h"]
    expect(not o["live"] and o.get("never_called") and o.get("extra_records") == 0
           and d["never_called_overrides"] == ["h"], f"a 0-record watched override was not decided ({o})")
    txt = "\n".join(plan_lines(dict(d, sessions=["s"], extra_sessions=["r12-cap-w"], label="play")))
    expect("decided by extra records h 0x00000300 on a: watched, never called (0 records)" in txt
           and "1 of those watched and never called (0 records)" in txt and "nothing plays live" in txt,
           "plan lines for a watched, never-called override:\n" + txt)
    d = decide([rec("a")], routes, ovr3, tt, now3, {}, {}, "B", "1", None, [xrec])
    expect(d["overrides"]["h"].get("extra_records") == 5 and not d["overrides"]["h"].get("never_called"),
           "an override with extra records counted as never called")
    # called in the batch capture but no record kept: proves nothing, stays live and says so
    d = decide([rec("a")], routes, ovr3, tt, now3, {}, {}, "B", "1", None, [dict(zrec, calls={0x300: 4})])
    expect(d["overrides"]["h"]["live"] and any("4 call(s) but kept 0 records" in w for w in d["overrides"]["h"]["why"]),
           f"calls without records decided an override ({d['overrides']['h']})")
    # a hook that differs between the main sessions' baselines stays live, even with an extra capture
    d = decide([rec("a")], routes, ovr3, tt, now3, {}, {}, "B", "1", None, [xrec], {"h": "hook differs between ..."})
    expect(d["overrides"]["h"]["live"], "a hook that differs between baselines was decided by an extra run")
    d = decide([rec("a")], routes, {"f": 0x100, "g": 0x200}, tt, tt, {}, {}, "B", "1", None, None,
               {"f": "hook differs between the records' baselines (x)"})
    expect(d["live_overrides"] == ["f"], "a hook that differs between baselines stayed offline")
    # round 13: each session's baseline from its own run.json / its library's manifest
    revs = {"T1": "rev1" + "0" * 36, "T2": "rev2" + "0" * 36}
    mans = {"LIB1": {"targets_sha256": "T1"}, "LIBX": {"targets_sha256": "T9"}}
    recs = [dict(rec("a"), session="s1", library="LIB1", targets=None),
            dict(rec("a"), session="s2", library="LIB2", targets="T2"),
            dict(rec("c"), session="s2", library="LIB2", targets="T2")]
    b, probs = session_baselines(recs, mans.get, revs)
    expect(b == {revs["T1"]: ["s1"], revs["T2"]: ["s2"]} and probs == [], f"session baselines ({b}, {probs})")
    b, probs = session_baselines([dict(rec("a"), session="s3", library="LIB3", targets=None),
                                  dict(rec("a"), session="s4", library="LIBX", targets=None)], mans.get, revs)
    expect(b == {} and len(probs) == 2 and "no build manifest" in probs[0] and "no commit has" in probs[1],
           f"a session whose hooks cannot be told was not refused ({probs})")
    rows, conf = merged_targets({"r1": "name,address,kind\nf,0x100,override\ng,0x200,override\n",
                                 "r2": "name,address,kind\nf,0x100,override\ng,0x204,override\nh,0x300,override\n"})
    expect(set(rows) == {"f", "g", "h"} and list(conf) == ["g"] and "0x00000204" in conf["g"],
           f"merged baselines ({rows}, {conf})")
    # session patterns
    with tempfile.TemporaryDirectory() as td:
        for sname in ("r12-cap-a", "r12-cap-b", "r12-other"):
            os.makedirs(os.path.join(td, sname, "records"))
        os.makedirs(os.path.join(td, "r12-cap-norec"))
        got = expand_sessions("r12-cap-*,s1", ["s1"], td)
        expect(got == ["r12-cap-a", "r12-cap-b"], f"session pattern expanded wrong ({got})")
        expect(expand_sessions("a,b,a", None, td) == ["a", "b"] and expand_sessions(None, None, td) == [],
               "plain session lists")
        try:
            expand_sessions("r13-cap-*", None, td)
            expect(False, "a pattern matching nothing was taken as no capture")
        except Stop:
            pass
    for e in errs:
        print("FAIL: " + e)
    print(f"offline selftest: {'OK' if not errs else str(len(errs)) + ' failure(s)'}")
    return 1 if errs else 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["_tree-build"]:
        ap = argparse.ArgumentParser()
        ap.add_argument("x")
        ap.add_argument("--tree", required=True)
        ap.add_argument("--work", required=True)
        a = ap.parse_args(argv)
        return tree_build_child(os.path.abspath(a.tree), os.path.abspath(a.work))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", choices=["plan", "tree", "build-lib", "replay", "compare"])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--sessions", help="comma list of parallel.py sessions with records/ (store-keep runs)")
    ap.add_argument("--label", default="play", help="play (real play) or a cheat* label (cheat track); never mixed")
    ap.add_argument("--extra-sessions",
                    help="plan / replay: the batch's own capture sessions (comma list; patterns such as r12-cap-*): "
                         "an override they captured today counts as decided by records, not 'must play live'")
    ap.add_argument("--baseline-rev", help="plan / replay: the commit whose targets.csv every main session's records "
                                          "ran, given by hand (default, round 13: each session's own, from its "
                                          "run.json targets.csv hash or its library's build manifest; the plan stops "
                                          "when that cannot be told)")
    ap.add_argument("--json", help="plan/compare: also write the result here")
    ap.add_argument("--rev", help="tree: the commit; replay: replay that commit's readable code (a frozen tree)")
    ap.add_argument("--name", help="tree / replay: folder name below build/speed/replay/")
    ap.add_argument("--plant", help="tree: 'PATH|OLD|NEW', one exact replacement in the copy (a planted bug)")
    ap.add_argument("--tree", help="replay / build-lib: a source tree (default for replay: the working tree)")
    ap.add_argument("--lib", help="replay: the capture library (default build/harness/lib/<title id>.dll); copied first")
    ap.add_argument("--routes", help="replay: only these routes' record folders")
    ap.add_argument("--jobs", type=int, help="replay: record folders at once (only lowers FEF_ROBOT_JOBS)")
    ap.add_argument("--ignore-plan", action="store_true", help="replay: also the routes the plan sends live")
    ap.add_argument("--no-source-gate", action="store_true", help="replay: go on when the tree is not the library's code")
    ap.add_argument("--offline", help="compare: an offline run's --name")
    ap.add_argument("--live", help="compare: a live capture (session name or folder)")
    ap.add_argument("--one-side-ok", action="store_true", help="compare: routes on one side only are not a difference")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        if a.command == "plan":
            if not a.sessions:
                raise Stop("plan: --sessions")
            return cmd_plan(a)
        if a.command == "tree":
            if not a.rev:
                raise Stop("tree: --rev")
            return cmd_tree(a)
        if a.command == "build-lib":
            if not a.tree:
                raise Stop("build-lib: --tree")
            return cmd_build_lib(a)
        if a.command == "replay":
            if not a.sessions:
                raise Stop("replay: --sessions")
            return cmd_replay(a)
        if a.command == "compare":
            if not (a.offline and a.live):
                raise Stop("compare: --offline NAME --live SESSION")
            return cmd_compare(a)
        ap.print_help()
        return 2
    except (Stop, par.Stop) as e:
        print(f"offline: STOP: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
