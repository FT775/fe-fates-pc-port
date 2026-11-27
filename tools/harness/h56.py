#!/usr/bin/env python3
"""H5 and H6 on kept game records (docs/HARNESS.md 4 "In order" step 3; the Awakening port's H5/H6 are the
reference). Standard library only; offline: no game, no engine build, only the host C compiler.

    python tools/harness/h56.py h5 --sessions r7-h5 [--label play] [--run-id ID] [--jobs N] [--merge auto|gcov-tool|python]
        H5, real-state coverage: replay.exe built with gcov (src/readable compiled natively), every kept record of
        the sessions' store-keep runs replayed (original side first: it must be clean, else the harness is wrong;
        then the readable side, whose offline verdict must equal the live one), then gcov per override: records,
        path signatures, distinct results, lines and branches of the override's own body (and of the static helpers
        of its file it calls directly) that real play ran. -> build/harness/h56/<label>/runs/<id>/h5.json, h5.tsv
        First pass in N lanes (round 12; --jobs, default and cap FEF_ROBOT_JOBS / max_parallel_runs; 1 = serial):
        N record folders at once, each lane's gcov counters in its own folder (GCOV_PREFIX), then one merge
        (gcov-tool merge; python sum of each lane's gcov if gcov-tool is missing or --merge python) before gcov reads
        them. Same result as serial (docs/harness/H56.md 10). The per-override exact pass stays serial.
    python tools/harness/h56.py h6 --sessions r7-h5 [--label play] [--functions a,b] [--jobs N] [--files-at-once K]
        H6, planted bugs on game records: tools/harness/mutate.py's operators on each override met with at least one
        MATCH record, one source file at a time, each mutant replayed on the kept records of that file's overrides
        (only the record folders that hold any). caught/judged per override. -> build/harness/h56/<label>/runs/<id>/h6.json,
        h6.tsv. Up to K source files side by side (default: --jobs), with at most --jobs compiler / replay.exe
        processes at once over all of them; --files-at-once 1 is the old one-file-at-a-time order.
        --cache: reuse a source file's mutant verdicts when nothing it depends on changed (tools/harness/h6cache.py:
        key = preprocessed source + callee files + records + tools + compiler/flags + operators; entries older than
        7 days refused); --no-cache: every file cold, entries refreshed. Neither: no cache at all (the old path).
    python tools/harness/h56.py h6 --sample [--sample-n N] [--budget-min M] --sessions r10-capb [--label play] ...
        H6 on a SAMPLE of the records (owner F-024; docs/harness/H56.md section 9; tools/harness/h6sample.py): per
        override, a greedy cover of every readable block its records reached, then more distinct input signatures up
        to N (default 64); one sample folder per source file. With --cache the key holds the file's sampled-record
        digest (not the folders), so new records of other files' overrides do not make it miss. Results go to
        <run>/h6_sample.json / .tsv and, when complete, <label>/h6_sample.json (the full-record <label>/h6.json is
        never touched by a sampled run).
        --budget-min M (any h6 run): stop cleanly M minutes after the start: mutants not started by then are
        `unjudged` (not counted), files not started are listed; the run is then PARTIAL (never published, never
        cached) and says so. With a budget the mutants of a file start in a fixed scrambled order.

Output: every run writes its own folder build/harness/h56/<label>/runs/<id>/ (id: --run-id, else the start time and
the command), so a partial run never overwrites another's results. Only a COMPLETE run (h5: exact coverage, no
harness problem, no bad record; h6: every met override, no --functions, no problem) is also copied to
build/harness/h56/<label>/h5.json / h6.json (the "latest complete" view that check_all and h6's h5 input read), and
<label>/latest.json says which run that was.

Labels: any name of letters, digits, _ . - (a session name, a round, ...). A label starting with "cheat" is the cheat
track and takes cheat-track records only; any other label takes real-play records only (F-019, never mixed).
    python tools/harness/h56.py --selftest
        the record-folder rules and the gcov JSON reading on invented data

Records: `parallel.py runs --mode capture --only all --store-keep --session S` keeps every run's records in
build/parallel/S/records/<run>/ (game memory: build/ only, never tracked). F-019: a session's folders are either all
real play or all cheat track (run.json `cheat` / `start_save_cheat`); `--label cheat` is required for cheat records
and refused for real play, so the two are never mixed in one report.

Budget: the priority class of config/harness/resources.json (FEF_ROBOT_PRIORITY honoured) is set on this process
and every compiler and replay.exe child inherits it; `--jobs` defaults to FEF_ROBOT_JOBS / max_parallel_runs.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import csv
import ctypes
import glob
import gzip
import io
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import harness as H  # noqa: E402  (same folder: replay build and run, ABI gate, registry)
import mutate  # noqa: E402
import h6cache  # noqa: E402  (owner OK A: per-file mutant result cache, off unless --cache / --no-cache)
import h6sample  # noqa: E402  (F-024: the sampled mode, --sample)

rcheck = H.rcheck
OUT = os.path.join(ROOT, "build", "harness", "h56")
PAR = os.path.join(ROOT, "build", "parallel")


class Stop(Exception):
    pass


LABEL_RX = r"[A-Za-z0-9_.-]{1,64}"


def is_cheat_label(label: str) -> bool:
    """The cheat track's labels start with "cheat" (cheat, cheat-r8, ...); every other label is real play."""
    return label.lower().startswith("cheat")


def check_label(label: str) -> str:
    if not re.fullmatch(LABEL_RX, label) or label in (".", "..", "runs") or ".." in label:
        raise Stop(f"label {label!r}: 1-64 letters, digits, _ . - (not 'runs', no '..')")
    return label


def run_dir(label: str, command: str, run_id: str | None = None, root: str = OUT) -> tuple[str, str]:
    """(id, build/harness/h56/<label>/runs/<id>/), a fresh folder: an existing id is refused, never overwritten."""
    rid = run_id or f"{time.strftime('%Y%m%d-%H%M%S')}-{command}"
    if not re.fullmatch(LABEL_RX, rid) or rid in (".", "..") or ".." in rid:
        raise Stop(f"run id {rid!r}: letters, digits, _ . - only")
    d = os.path.join(root, check_label(label), "runs", rid)
    if os.path.exists(d):
        raise Stop(f"{rcheck.rel(d)} exists: give another --run-id (a run never overwrites another)")
    os.makedirs(d)
    return rid, d


def publish(label: str, rid: str, d: str, names: tuple[str, ...], complete: bool, why: str, root: str = OUT) -> str:
    """Copy a complete run's files up to <label>/ (the latest-complete view) and note it in <label>/latest.json.
    A partial run is only listed there. Returns a line for the log."""
    top = os.path.join(root, label)
    latest_path = os.path.join(top, "latest.json")
    try:
        with open(latest_path, encoding="utf-8") as fh:
            latest = json.load(fh)
        if not isinstance(latest, dict):
            latest = {}
    except (OSError, ValueError):
        latest = {}
    kind = names[0].split(".")[0]  # "h5" or "h6"
    partial = latest.setdefault("partial", {})
    if complete:
        for n in names:
            tmp = os.path.join(top, n + ".tmp")
            shutil.copyfile(os.path.join(d, n), tmp)
            os.replace(tmp, os.path.join(top, n))
        latest[kind] = {"run": rid, "folder": rcheck.rel(d), "when": time.strftime("%Y-%m-%d %H:%M:%S")}
        partial.pop(rid, None)
    else:
        partial[rid] = why
    tmp = latest_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(latest, fh, indent=1)
    os.replace(tmp, latest_path)
    if complete:
        return f"{kind}: COMPLETE run {rid}: " + ", ".join(rcheck.rel(os.path.join(top, n)) for n in names) + " updated"
    return (f"{kind}: PARTIAL run {rid} ({why}): results stay in {rcheck.rel(d)}; "
            f"{rcheck.rel(os.path.join(top, names[0]))} not touched")


# ------------------------------------------------------------------ record folders
def record_dirs(sessions: list[str], label: str, root: str | None = None, allow_empty: bool = False) -> list[str]:
    """The kept record folders of the sessions; refuses a mix of real play and cheat track (F-019).
    allow_empty (round 13, offline.py plan): also the folders of a store-keep run that kept 0 records (run.json and
    summary.tsv, no records.fecap: parallel.py keeps them so its watched `only` list counts as "watched, never
    called"). H5/H6 never ask for them (nothing to replay)."""
    root = PAR if root is None else root
    dirs = []
    for s in sessions:
        found = sorted(d for d in glob.glob(os.path.join(root, s, "records", "*"))
                       if os.path.isfile(os.path.join(d, "records.fecap"))
                       or (allow_empty and os.path.isfile(os.path.join(d, "run.json"))))
        if not found:
            raise Stop(f"session {s}: no records/<run>/records.fecap (parallel.py runs --mode capture --only ... --store-keep)")
        dirs += found
    kinds = {}
    cheat_label = is_cheat_label(check_label(label))
    for d in dirs:
        rj = {}
        try:
            with open(os.path.join(d, "run.json"), encoding="utf-8") as fh:
                rj = json.load(fh)
            if not isinstance(rj, dict):
                raise ValueError("not an object")
        except (OSError, ValueError):
            raise Stop(f"{rcheck.rel(d)}: no run.json: cannot tell real play from the cheat track") from None
        cheat = rj.get("cheat") or rj.get("start_save_cheat") or str(rj.get("route") or "").startswith("cheat-")
        kinds[d] = "cheat" if cheat else "play"
    if allow_empty:  # a 0-record folder of the other track holds no records to mix: left out, not refused
        for d in [d for d, k in kinds.items() if (k == "cheat") != cheat_label
                  and not os.path.isfile(os.path.join(d, "records.fecap"))]:
            del kinds[d]
            dirs.remove(d)
        if not dirs:
            raise Stop(f"label {label}: no record folder of this track in sessions {','.join(sessions)}")
    if set(kinds.values()) - {"cheat" if cheat_label else "play"}:
        wrong = [rcheck.rel(d) for d, k in kinds.items() if (k == "cheat") != cheat_label]
        raise Stop(f"label {label}: these record folders are the other track (F-019, never mixed; a cheat-track "
                   f"label starts with 'cheat'): {wrong[:4]}")
    return dirs


def route_of(d: str) -> str:
    try:
        with open(os.path.join(d, "run.json"), encoding="utf-8") as fh:
            return json.load(fh).get("route") or "?"
    except (OSError, ValueError):
        return "?"


def summary_addresses(d: str) -> dict[str, int]:
    """address -> records kept, from the run's summary.tsv."""
    out = {}
    p = os.path.join(d, "summary.tsv")
    if not os.path.isfile(p):
        return out
    with open(p, encoding="utf-8") as fh:
        head = None
        for ln in fh:
            if ln.startswith("#"):
                continue
            cols = ln.rstrip("\n").split("\t")
            if head is None:
                head = cols
                continue
            row = dict(zip(head, cols))
            if row.get("address", "").startswith("0x"):
                out[row["address"].upper().replace("0X", "0x")] = int(row.get("records") or 0)
    return out


# ------------------------------------------------------------------ budget
def lower_priority() -> tuple[str, int]:
    import parallel as par  # noqa: E402  (load_limits, PRIORITY; nothing written)
    lim = par.load_limits()
    if os.name == "nt":
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        k32.SetPriorityClass(k32.GetCurrentProcess(), par.PRIORITY.get(lim.priority, par.PRIORITY["below_normal"]))
    return lim.priority, lim.jobs


# ------------------------------------------------------------------ gcov JSON
def gcov_json(obj_dir: str, work: str) -> dict[str, dict]:
    """{normcase source path: {"lines": {n: (count, [branch counts])}, "functions": {name: (start, end, count)}}}
    from `gcov -j -b` of every .gcda in obj_dir (sections of other files, e.g. headers, are kept apart)."""
    gcov = shutil.which("gcov") or os.path.join(os.path.dirname(rcheck.find_cc() or ""), "gcov" + H.EXE)
    os.makedirs(work, exist_ok=True)
    out: dict[str, dict] = {}
    for gcda in sorted(glob.glob(os.path.join(obj_dir, "*.gcda"))):
        subprocess.run([gcov, "-j", "-b", "-o", obj_dir, gcda], cwd=work, capture_output=True, text=True)
    for jz in glob.glob(os.path.join(work, "*.gcov.json.gz")):
        with gzip.open(jz, "rt", encoding="utf-8") as fh:
            data = json.load(fh)
        for f in data.get("files", []):
            merge_gcov_file(out, f, data.get("current_working_directory") or work)
        os.remove(jz)
    return out


def merge_gcov_file(out: dict, f: dict, cwd: str) -> None:
    path = f["file"] if os.path.isabs(f["file"]) else os.path.join(cwd, f["file"])
    key = os.path.normcase(os.path.abspath(path))
    e = out.setdefault(key, {"lines": {}, "functions": {}})
    for ln in f.get("lines", []):
        n = ln["line_number"]
        c, br = e["lines"].get(n, (0, []))
        b = [x.get("count", 0) for x in ln.get("branches", [])]
        if br and len(br) == len(b):
            b = [x + y for x, y in zip(br, b)]
        e["lines"][n] = (c + ln.get("count", 0), b or br)
    for fn in f.get("functions", []):
        name = fn.get("demangled_name") or fn["name"]
        s0, e0, c0 = e["functions"].get(name, (fn["start_line"], fn["end_line"], 0))
        e["functions"][name] = (s0, e0, c0 + fn.get("execution_count", 0))


def span_cover(cov: dict, start: int, end: int) -> dict:
    lines = [(n, v) for n, v in cov["lines"].items() if start <= n <= end]
    branches = [c for _n, (_c, b) in lines for c in b]
    return {"lines": len(lines), "lines_run": sum(1 for _n, (c, _b) in lines if c), "branches": len(branches),
            "branches_taken": sum(1 for c in branches if c),
            "never_taken": sorted({n for n, (c, b) in lines if any(x == 0 for x in b)}),
            "never_run": sorted(n for n, (c, _b) in lines if not c)}


def function_lines(source: str, name: str) -> tuple[int, int] | None:
    """1-based first and last line of name's definition (mutate.find_function on stripped code)."""
    text = open(source, encoding="utf-8").read()
    code = rcheck.strip_code(text)
    f = mutate.find_function(code, name)
    if f is None:
        return None
    return text.count("\n", 0, f[0]) + 1, text.count("\n", 0, f[1]) + 1


def override_cover(cov: dict, source: str, name: str) -> dict | None:
    c = cov.get(os.path.normcase(os.path.abspath(source)))
    span = function_lines(source, name)
    if c is None or span is None:
        return None
    own = span_cover(c, *span)
    text = open(source, encoding="utf-8").read()
    code = rcheck.strip_code(text)
    f = mutate.find_function(code, name)
    helpers = mutate.static_helpers(code, f[0], f[1], name) if f else []
    tot = dict(own)
    for h in helpers:
        hs = function_lines(source, h)
        if hs:
            x = span_cover(c, *hs)
            for k in ("lines", "lines_run", "branches", "branches_taken"):
                tot[k] += x[k]
    return {"own": own, "with_helpers": {k: tot[k] for k in ("lines", "lines_run", "branches", "branches_taken")},
            "helpers": helpers, "span": list(span)}


# ------------------------------------------------------------------ the readable call graph (static, one source tree)
DEF_RX = mutate.re.compile(r"^[A-Za-z_][\w \t\*]*?\b([A-Za-z_]\w*)\s*\(", mutate.re.M)
CALL_RX = mutate.re.compile(r"\b([A-Za-z_]\w*)\s*\(")


def definitions(sources: list[str]) -> dict[str, tuple[str, int, int, str]]:
    """name -> (source, first line, last line, body code) of every function defined in the readable sources outside
    src/readable/core/ (the capture and runtime machinery). A name defined twice keeps its first non-static definition."""
    out: dict = {}
    core = os.path.normcase(os.path.join("src", "readable", "core"))
    for src in sources:
        if core in os.path.normcase(src):
            continue
        text = open(src, encoding="utf-8").read()
        code = rcheck.strip_code(text)
        for m in DEF_RX.finditer(code):
            name = m.group(1)
            if name in mutate.KEYWORDS or (name in out and not out[name][4]):
                continue
            f = mutate.find_function(code, name)
            if f is None:
                continue
            out[name] = (src, text.count("\n", 0, f[0]) + 1, text.count("\n", 0, f[1]) + 1, code[f[0]:f[1]], f[2])
    return {k: v[:4] for k, v in out.items()}


def closure(defs: dict, name: str, depth: int = 6) -> list[str]:
    """name and every readable function it calls, directly or through others (up to depth calls deep)."""
    seen, todo = [name], [(name, 0)]
    while todo:
        n, d = todo.pop()
        if d >= depth or n not in defs:
            continue
        for m in CALL_RX.finditer(defs[n][3]):
            c = m.group(1)
            if c in defs and c not in seen:
                seen.append(c)
                todo.append((c, d + 1))
    return [n for n in seen if n in defs]


def closure_cover(cov: dict, defs: dict, names: list[str]) -> dict:
    tot = {"lines": 0, "lines_run": 0, "branches": 0, "branches_taken": 0}
    for n in names:
        src, a, b, _ = defs[n]
        c = cov.get(os.path.normcase(os.path.abspath(src)))
        if c is None:
            continue
        x = span_cover(c, a, b)
        for k in tot:
            tot[k] += x[k]
    return tot


def exact_cover(cexe: str, lib: str, obj_dir: str, work: str, addr: str, dirs: list[str], defs: dict,
                name: str):
    """Coverage of one override from its own records only: the gcov data cleared, its records replayed
    (--only), gcov of the files of its call closure. (own body, whole closure) or None."""
    for f in glob.glob(os.path.join(obj_dir, "*.gcda")):
        os.remove(f)
    for d in dirs:
        H.replay(cexe, lib, d, "readable", only=addr)
        for f in glob.glob(os.path.join(d, "replay_*.jsonl")) + glob.glob(os.path.join(d, "fe_readable.log")):
            os.remove(f)
    if name not in defs:
        return None
    names = closure(defs, name)
    files = {os.path.splitext(os.path.basename(defs[n][0]))[0] for n in names}
    for g in glob.glob(os.path.join(obj_dir, "*.gcda")):
        if os.path.basename(g).rsplit("_", 1)[0] not in files:
            os.remove(g)
    cov = gcov_json(obj_dir, work)
    src, a, b, _ = defs[name]
    c = cov.get(os.path.normcase(os.path.abspath(src)))
    own = span_cover(c, a, b) if c else None
    return own, dict(closure_cover(cov, defs, names), functions=names)


# ------------------------------------------------------------------ H5
def h5_folder(exe: str, cexe: str, lib: str, d: str, i: int, env: dict | None) -> dict:
    """One record folder: original vs original (plain replay.exe), then the readable side (gcov build; env: the
    lane's GCOV_PREFIX). The record folder keeps only what parallel.py kept."""
    rc, text, rows = H.replay(exe, lib, d, "original")
    bad = [r for r in rows if r["verdict"] in H.BAD]
    orig_bad = bool(rc or bad)
    problems = [f"{rcheck.rel(d)}: original vs original rc {rc}, {len(bad)} bad"] if orig_bad else []
    orig_n = len(rows)
    rc, text, rows = H.replay(cexe, lib, d, "readable", env_extra=env)
    if rc:
        problems.append(f"{rcheck.rel(d)}: readable replay rc {rc}: {text[-300:]}")
    for f in glob.glob(os.path.join(d, "replay_*.jsonl")) + glob.glob(os.path.join(d, "fe_readable.log")):
        os.remove(f)  # small, but the record folder stays what parallel.py kept
    return {"i": i, "dir": d, "route": route_of(d), "orig_n": orig_n, "clean": not problems, "problems": problems,
            "rows": rows}


def h5_add(per, harness_bad: list, res: dict) -> None:
    """Adds one folder's readable rows to the per-override totals (counts and sets: the order does not matter)."""
    route, rows = res["route"], res["rows"]
    harness_bad += res["problems"]
    for r in rows:
        p = per[int(r["address"], 16)]
        p["records"] += 1
        p["verdicts"][r["verdict"]] += 1
        p["live"][r["live"]] += 1
        p["signatures"].add(r.get("signature"))
        p["results"].add(r.get("r0"))
        p["routes"].add(route)
        p["cold"] += 1 if r.get("cold") else 0
        p["offline_vs_live_differ"] += 1 if r["verdict"] != r["live"] else 0
    print(f"  {route:18s} {res['orig_n']:5d} record(s): original vs original "
          f"{'clean' if res['clean'] else 'NOT CLEAN'}; readable "
          + ", ".join(f"{k} {v}" for k, v in sorted(collections.Counter(r['verdict'] for r in rows).items())),
          flush=True)


def gcov_tool() -> str | None:
    t = shutil.which("gcov-tool")
    if t:
        return t
    cc = rcheck.find_cc()
    p = os.path.join(os.path.dirname(cc or ""), "gcov-tool" + H.EXE)
    return p if cc and os.path.isfile(p) else None


def add_cov(out: dict, cov: dict) -> None:
    """Sums one gcov_json result into another (the python merge of lane counters: line, branch and function counts
    add up, as libgcov adds the runs that write one counter folder)."""
    for key, e in cov.items():
        o = out.setdefault(key, {"lines": {}, "functions": {}})
        for n, (c, b) in e["lines"].items():
            c0, b0 = o["lines"].get(n, (0, []))
            o["lines"][n] = (c0 + c, [x + y for x, y in zip(b0, b)] if b0 and len(b0) == len(b) else (list(b) or b0))
        for name, (s0, e0, c) in e["functions"].items():
            a0, z0, k0 = o["functions"].get(name, (s0, e0, 0))
            o["functions"][name] = (a0, z0, k0 + c)


def merge_lanes(lane_dirs: list[str], obj_dir: str, work: str, how: str = "auto") -> tuple[str, dict | None]:
    """The lanes' counters as one. gcov-tool (GCC's profile merge; default when found beside the host compiler):
    the lanes' .gcda merged one after another and copied into obj_dir (where the .gcno are), so gcov reads them as
    one serial run; returns (how, None). "python" (or no gcov-tool): each lane read by gcov on its own and the
    counts summed (add_cov); returns (how, coverage)."""
    full = [ld for ld in lane_dirs if glob.glob(os.path.join(ld, "*.gcda"))]
    for g in glob.glob(os.path.join(obj_dir, "*.gcda")):
        os.remove(g)
    if not full:
        return "no lane wrote counters", None
    tool = gcov_tool() if how in ("auto", "gcov-tool") else None
    if how == "gcov-tool" and tool is None:
        raise Stop("--merge gcov-tool: gcov-tool not found beside the host compiler")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    if tool:
        acc = full[0]
        for k, ld in enumerate(full[1:]):
            dst = os.path.join(work, f"m{k:02d}")
            rc, text = H.run([tool, "merge", acc, ld, "-o", dst], timeout=600)
            if rc or not glob.glob(os.path.join(dst, "*.gcda")):
                raise Stop(f"gcov-tool merge {rcheck.rel(acc)} {rcheck.rel(ld)}: rc {rc}: {text[-500:]}")
            acc = dst
        for g in glob.glob(os.path.join(acc, "*.gcda")):
            shutil.copy2(g, os.path.join(obj_dir, os.path.basename(g)))
        return f"gcov-tool merge of {len(full)} lane(s)", None
    total: dict = {}
    for k, ld in enumerate(full):
        for gcno in glob.glob(os.path.join(obj_dir, "*.gcno")):
            shutil.copy2(gcno, os.path.join(ld, os.path.basename(gcno)))
        add_cov(total, gcov_json(ld, os.path.join(work, f"g{k:02d}")))
    return f"python sum of {len(full)} lane(s)", total


def cmd_h5(a) -> int:
    prio, _jobs = lower_priority()
    dirs = record_dirs(a.sessions.split(","), a.label)
    rid, out = run_dir(a.label, "h5", a.run_id)
    print(f"h5 ({a.label}): run {rid} -> {rcheck.rel(out)}")
    cc = rcheck.find_cc()
    lib = H.find_lib(a.lib)
    if cc is None or lib is None:
        raise Stop("no host C compiler or no library (build/harness/lib)")
    ok, msg = H.abi_gate(cc, os.path.dirname(lib), os.path.join(H.BUILD, "abi"))
    print(msg)
    if not ok:
        return 1
    plain_dir, cov_dir = os.path.join(out, "replay"), os.path.join(out, "cov")
    table = os.path.join(out, "overrides_table.c")
    n = H.write_table(table)
    exe, err = H.build_replay(cc, plain_dir, H.readable_sources() + [table])
    if exe is None:
        print(err[-3000:])
        return 1
    cexe, err = H.build_replay(cc, cov_dir, H.readable_sources() + [table], coverage=True)
    if cexe is None:
        print(err[-3000:])
        return 1
    print(f"h5: replay.exe and a gcov build with {n} override(s); {len(dirs)} record folder(s); priority {prio}")
    reg = {int(r["address"], 16) & ~1: r for r in rcheck.registry() if r["kind"].strip() == "override"}
    per = collections.defaultdict(lambda: {"records": 0, "verdicts": collections.Counter(), "live": collections.Counter(),
                                           "signatures": set(), "results": set(), "routes": set(), "cold": 0,
                                           "offline_vs_live_differ": 0})
    harness_bad = []
    budget = _jobs
    jobs = a.jobs if (a.jobs_over_budget and a.jobs) else min(a.jobs or budget, budget)
    lanes = max(1, min(jobs, len(dirs)))
    obj_dir = os.path.join(cov_dir, "obj")
    t0 = time.time()
    lane_dirs: list[str] = []
    if lanes == 1:  # the serial path: one replay.exe at a time, counters straight into the build's obj folder
        for i, d in enumerate(dirs):
            h5_add(per, harness_bad, h5_folder(exe, cexe, lib, d, i, None))
    else:  # fan-out: N lanes, each with its OWN counter folder (GCOV_PREFIX), one merge afterwards
        lane_dirs = [os.path.join(out, "lanes", f"lane{k:02d}") for k in range(lanes)]
        free: queue.Queue = queue.Queue()
        for ld in lane_dirs:
            os.makedirs(ld, exist_ok=True)
            free.put(ld)

        def one(item):
            i, d = item
            ld = free.get()  # a lane is held by one replay at a time: its .gcda files are never written twice at once
            try:
                return h5_folder(exe, cexe, lib, d, i, {"GCOV_PREFIX": ld, "GCOV_PREFIX_STRIP": "99"})
            finally:
                free.put(ld)
        with concurrent.futures.ThreadPoolExecutor(max_workers=lanes) as pool:
            for res in pool.map(one, list(enumerate(dirs))):  # results in folder order: same printout as serial
                h5_add(per, harness_bad, res)
    t1 = time.time()
    how, cov = "serial (one counter folder)", None
    if lane_dirs:
        how, cov = merge_lanes(lane_dirs, obj_dir, os.path.join(out, "merge"), a.merge)
    t2 = time.time()
    if cov is None:
        cov = gcov_json(obj_dir, os.path.join(out, "gcov"))
    t3 = time.time()
    lane_info = {"lanes": lanes, "counters": how, "replay_seconds": round(t1 - t0, 1),
                 "merge_seconds": round(t2 - t1, 1), "gcov_seconds": round(t3 - t2, 1)}
    print(f"h5: first pass {len(dirs)} folder(s) in {lanes} lane(s): replay {t1 - t0:.1f} s, counters {how} "
          f"{t2 - t1:.1f} s, gcov {t3 - t2:.1f} s")
    defs = definitions(H.readable_sources())
    exact = {}
    if not a.no_exact:  # each override from its own records only (the aggregate counts a shared helper's branch
        # for every override when any record ran it; the readable code also calls overrides natively)
        holders = collections.defaultdict(list)
        for d in dirs:
            for ad, k in summary_addresses(d).items():
                if k:
                    holders[int(ad, 16)].append(d)
        for addr, r in sorted(reg.items()):
            if addr in per and holders.get(addr):
                exact[addr] = exact_cover(cexe, lib, os.path.join(cov_dir, "obj"), os.path.join(out, "gcov"),
                                          f"0x{addr:08X}", holders[addr], defs, r["name"])
        print(f"h5: exact coverage of {len(exact)} override(s), each from its own records")
    rows_out = []
    for addr, r in sorted(reg.items(), key=lambda x: (x[1]["source"], x[1]["name"])):
        p = per.get(addr)
        src = os.path.join(ROOT, r["source"])
        c = override_cover(cov, src, r["name"]) if p else None
        row = {"name": r["name"], "address": f"0x{addr:08X}", "source": r["source"], "met": bool(p)}
        if p:
            row.update(records=p["records"], match=p["verdicts"].get("match", 0), gave_up=p["verdicts"].get("gave_up", 0),
                       other=sum(v for k, v in p["verdicts"].items() if k not in ("match", "gave_up")),
                       bad=sum(v for k, v in p["verdicts"].items() if k in H.BAD),
                       offline_vs_live_differ=p["offline_vs_live_differ"], signatures=len(p["signatures"]),
                       results=len(p["results"]), cold=p["cold"], routes=sorted(p["routes"]))
            if c:
                row.update(lines=c["own"]["lines"], lines_run=c["own"]["lines_run"], branches=c["own"]["branches"],
                           branches_taken=c["own"]["branches_taken"], never_taken_lines=c["own"]["never_taken"],
                           never_run_lines=c["own"]["never_run"], helpers=c["helpers"], with_helpers=c["with_helpers"],
                           span=c["span"], coverage="aggregate")
            ex = exact.get(addr)
            if ex and ex[0]:
                own, clo = ex
                row.update(lines=own["lines"], lines_run=own["lines_run"], branches=own["branches"],
                           branches_taken=own["branches_taken"], never_taken_lines=own["never_taken"],
                           never_run_lines=own["never_run"], closure=clo, coverage="exact")
        rows_out.append(row)
    met = [x for x in rows_out if x["met"]]
    tb = sum(x.get("branches", 0) for x in met)
    tt = sum(x.get("branches_taken", 0) for x in met)
    tl = sum(x.get("lines", 0) for x in met)
    tlr = sum(x.get("lines_run", 0) for x in met)
    cb = sum(x.get("closure", {}).get("branches", 0) for x in met)
    ct = sum(x.get("closure", {}).get("branches_taken", 0) for x in met)
    full = [x["name"] for x in met if x.get("branches") and x["branches_taken"] == x["branches"]]
    nobr = [x["name"] for x in met if not x.get("branches")]
    total = {"label": a.label, "record_folders": [rcheck.rel(d) for d in dirs], "overrides": len(rows_out),
             "met": len(met), "records": sum(x["records"] for x in met),
             "match": sum(x["match"] for x in met), "gave_up": sum(x["gave_up"] for x in met),
             "bad": sum(x["bad"] for x in met), "offline_vs_live_differ": sum(x["offline_vs_live_differ"] for x in met),
             "lines": tl, "lines_run": tlr, "branches": tb, "branches_taken": tt,
             "all_branches_taken": len(full), "no_branches": len(nobr), "harness_problems": harness_bad,
             "closure_branches": cb, "closure_branches_taken": ct, "exact": len(exact),
             "library": rcheck.rel(lib), **lane_info}
    with open(os.path.join(out, "h5.json"), "w", encoding="utf-8") as fh:
        json.dump({"total": total, "overrides": rows_out}, fh, indent=1)
    for x in rows_out:
        if x.get("closure"):
            x["closure_branches_taken"], x["closure_branches"] = x["closure"]["branches_taken"], x["closure"]["branches"]
    cols = ["name", "address", "met", "records", "match", "gave_up", "bad", "offline_vs_live_differ", "signatures",
            "results", "lines_run", "lines", "branches_taken", "branches", "closure_branches_taken", "closure_branches",
            "never_taken_lines", "coverage", "routes"]
    with open(os.path.join(out, "h5.tsv"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\t".join(cols) + "\n")
        for x in rows_out:
            fh.write("\t".join(" ".join(map(str, x.get(k, ""))) if isinstance(x.get(k), list) else str(x.get(k, ""))
                               for k in cols) + "\n")
    for x in met:
        print(f"  {x['name']:38s} rec {x['records']:4d} match {x['match']:4d} sig {x['signatures']:2d} "
              f"res {x['results']:3d} lines {x.get('lines_run', '?')}/{x.get('lines', '?')} "
              f"branches {x.get('branches_taken', '?')}/{x.get('branches', '?')}"
              + (f" closure {x['closure']['branches_taken']}/{x['closure']['branches']} in {len(x['closure']['functions'])} fn"
                 if x.get("closure") else ""))
    print(f"h5 ({a.label}): {len(met)} of {len(rows_out)} overrides met, {total['records']} records "
          f"({total['match']} match, {total['gave_up']} gave up, {total['bad']} bad; offline != live: "
          f"{total['offline_vs_live_differ']}); lines run {tlr}/{tl}, branches taken {tt}/{tb}"
          + (f" ({100 * tt / tb:.1f}%)" if tb else "") + f"; every branch taken: {len(full)}, no branch: {len(nobr)}; "
          f"never met: {len(rows_out) - len(met)}; with every readable callee (exact, own records): branches "
          f"{ct}/{cb}" + (f" ({100 * ct / cb:.1f}%)" if cb else ""))
    for p in harness_bad:
        print(f"  HARNESS PROBLEM: {p}")
    print(f"h5: {rcheck.rel(os.path.join(out, 'h5.json'))}, {rcheck.rel(os.path.join(out, 'h5.tsv'))}")
    why = ", ".join(x for x in ("--no-exact (aggregate coverage only)" if a.no_exact else "",
                                 f"{len(harness_bad)} harness problem(s)" if harness_bad else "",
                                 f"{total['bad']} bad record(s)" if total["bad"] else "") if x)
    print(publish(a.label, rid, out, ("h5.json", "h5.tsv"), not why, why))
    for sub in ("replay", "cov", "gcov", "lanes", "merge"):  # rebuilt by every run (seconds): the run folder keeps its results only
        shutil.rmtree(os.path.join(out, sub), ignore_errors=True)
    return 1 if harness_bad or total["bad"] else 0


# ------------------------------------------------------------------ H6
def cmd_h6(a) -> int:
    prio, jobs = lower_priority()
    jobs = a.jobs if (a.jobs_over_budget and a.jobs) else min(a.jobs or jobs, jobs)
    dirs = record_dirs(a.sessions.split(","), a.label)
    rid, out = run_dir(a.label, "h6", a.run_id)
    cc = rcheck.find_cc()
    lib = H.find_lib(a.lib)
    if cc is None or lib is None:
        raise Stop("no host C compiler or no library (build/harness/lib)")
    reg = {r["name"]: r for r in rcheck.registry() if r["kind"].strip() == "override"}
    have: dict[str, list[str]] = collections.defaultdict(list)  # address -> record folders holding it
    for d in dirs:
        for addr, n in summary_addresses(d).items():
            if n:
                have[addr].append(d)
    h5 = a.h5 or os.path.join(OUT, a.label, "h5.json")  # the latest COMPLETE h5 of this label
    matched = None
    if os.path.isfile(h5):
        with open(h5, encoding="utf-8") as fh:
            matched = {x["name"] for x in json.load(fh)["overrides"] if x.get("match")}
    if a.functions:
        names = a.functions.split(",")
        for n in names:
            if n not in reg:
                raise Stop(f"{n}: not a readable override")
    else:
        names = sorted(n for n, r in reg.items()
                       if have.get(f"0x{int(r['address'], 16) & ~1:08X}") and (matched is None or n in matched))
    if a.writer_callees:  # a writer H6: only the readable callees of the HOOK_LIST writer slots (a partial run)
        got = mutate.writer_callees()
        if got is None:
            raise Stop("no hook list (docs/harness/HOOK_LIST.md): writer callees unknown")
        wanted = {reg_n for reg_n, r in reg.items() if int(r["address"], 16) & ~1 in got[1]}
        print(f"h6: writer H6: {len(wanted)} readable callee(s) of {len(got[0])} writer slot(s): "
              f"{', '.join(sorted(wanted))}; with records here: {', '.join(sorted(wanted & set(names))) or 'none'}")
        names = sorted(wanted & set(names))
    by_file = collections.defaultdict(list)
    for n in names:
        r = reg[n]
        by_file[r["source"]].append(mutate.Target(n, f"0x{int(r['address'], 16) & ~1:08X}", os.path.join(ROOT, r["source"])))
    if not by_file:  # round 11: a run with nothing to mutate was published as a COMPLETE (empty) result
        raise Stop("no override to mutate: no record folder's summary.tsv lists an override met with a MATCH "
                   "record (or --functions / --writer-callees left none)")
    table = os.path.join(out, "h6_overrides_table.c")
    H.write_table(table)
    sources = [os.path.join(HERE, "replay.c")] + H.readable_sources() + [table]
    at_once = max(1, min(a.files_at_once or jobs, len(by_file) or 1))
    print(f"h6 ({a.label}): run {rid} -> {rcheck.rel(out)}; {len(names)} override(s) in {len(by_file)} file(s), "
          f"{at_once} file(s) side by side, at most {jobs} process(es) at once, priority {prio}"
          + (f"; SAMPLED, N={a.sample_n}" if a.sample else "")
          + (f"; time budget {a.budget_min:g} min" if a.budget_min else ""))
    started = time.time()
    deadline = started + 60.0 * a.budget_min if a.budget_min else None
    sample = None
    sampled_keys = None
    if a.sample:  # F-024: replay a per-function sample (h6sample.py); one sample folder per source file
        if a.sample_n < 1:
            raise Stop("--sample-n: 1 or more")
        try:
            sample = h6sample.make_samples(cc, lib, dirs, by_file, sources, os.path.join(out, "sample"), jobs,
                                           a.sample_n, a.label)
        except h6sample.SampleError as e:
            raise Stop(f"sample: {e}") from None
        have = collections.defaultdict(list)
        for src, targets in by_file.items():
            if src in sample["folders"]:
                for t in targets:
                    have[t.address] = [sample["folders"][src]]
        sampled_keys = {src: {"digest": dg, "n": sample["n"], "rule": sample["rule"]}
                        for src, dg in sample["digests"].items()}
    cache = None
    if a.cache or a.no_cache:
        core_dir = os.path.normcase(os.path.join(ROOT, "src", "readable", "core"))
        rs = H.readable_sources()
        cache = h6cache.Cache(cc, H.CFLAGS, H.INCS, lib, rs,
                              [x for x in rs if os.path.normcase(x).startswith(core_dir)] + [os.path.join(HERE, "replay.c")],
                              a.cache_dir or (os.path.join(h6cache.DEFAULT_DIR, "sampled") if a.sample else h6cache.DEFAULT_DIR),
                              enabled=not a.no_cache, jobs=jobs,
                              equiv=mutate.EQUIV, cap=mutate.MUTANT_CAP)
        print(f"h6: cache {'on' if cache.enabled else 'off (--no-cache: every file cold, entries refreshed)'}, "
              f"{rcheck.rel(cache.dir)}; key prep {round(time.time() - started, 1)} s")
    budget: dict = {}
    results, problems = h6_files(rid, a.label, by_file, have, lib, cc, sources, jobs, at_once, cache, a.obj_prefix,
                                 sampled=sampled_keys, deadline=deadline, budget=budget)
    wall = round(time.time() - started, 1)
    caught = sum(s["caught"] for s in results.values())
    judged = sum(s["judged"] for s in results.values())
    unjudged = sum(s.get("unjudged", 0) for s in results.values())
    total = {"label": a.label, "run": rid, "mode": "sampled" if sample else "full", "functions": len(results),
             "caught": caught, "judged": judged, "rate": round(100.0 * caught / judged, 1) if judged else 0.0,
             "equivalent": sum(s["equivalent"] for s in results.values()),
             "stillborn": sum(s["stillborn"] for s in results.values()), "unjudged": unjudged,
             "files_not_started": budget.get("not_started", []), "files_cut": budget.get("cut", []),
             "budget_minutes": a.budget_min, "problems": problems,
             "record_folders": [rcheck.rel(d) for d in dirs], "h5_input": rcheck.rel(h5) if matched is not None else None,
             "jobs": jobs, "files_at_once": at_once, "wall_seconds": wall}
    if sample:
        for fn, st in sample["per_function"].items():
            if fn in results:
                results[fn]["sample"] = st
        total["sample"] = {k: sample[k] for k in ("n", "rule", "records_total", "records_kept", "seconds")}
        total["sample"]["over_n"] = sorted(fn for fn, st in sample["per_function"].items() if st["over_n"])
        total["sample"]["blocks"] = sum(st["blocks"] for st in sample["per_function"].values())
        total["sample"]["blocks_kept"] = sum(st["blocks_kept"] for st in sample["per_function"].values())
    if cache is not None:
        total["cache"] = cache.summary()
    stem = "h6_sample" if sample else "h6"
    with open(os.path.join(out, stem + ".json"), "w", encoding="utf-8") as fh:
        json.dump({"total": total, "functions": results}, fh, indent=1)
    with open(os.path.join(out, stem + ".tsv"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("function\tsource\tcaught\tjudged\trate\tvia_caller\tequivalent\tstillborn\tsurvivors"
                 + ("\tunjudged\tsample_kept\tsample_records\tsample_signatures" if sample else "") + "\n")
        for fn, s in sorted(results.items()):
            fh.write(f"{fn}\t{s['source']}\t{s['caught']}\t{s['judged']}\t{s['rate']:.1f}\t{s['caught_via_caller']}\t"
                     f"{s['equivalent']}\t{s['stillborn']}\t{' '.join(s['survivors'])}"
                     + (f"\t{s.get('unjudged', 0)}\t{s.get('sample', {}).get('kept', '')}\t"
                        f"{s.get('sample', {}).get('records', '')}\t{s.get('sample', {}).get('signatures', '')}"
                        if sample else "") + "\n")
    print(f"h6 ({a.label}): {caught}/{judged} caught ({total['rate']}%) over {len(results)} override(s); "
          f"equivalent {total['equivalent']}, stillborn {total['stillborn']}; problems: {problems or 'none'}; "
          f"wall {wall} s" + (f"; SAMPLED (N={sample['n']}, {sample['records_kept']} of {sample['records_total']} "
                              f"records)" if sample else ""))
    if unjudged or total["files_not_started"]:
        print(f"h6: TIME BUDGET ({a.budget_min:g} min) reached: {unjudged} mutant(s) unjudged (not counted) in "
              f"{len(total['files_cut'])} file(s) cut short; {len(total['files_not_started'])} file(s) not started"
              + (f": {', '.join(total['files_not_started'])}" if total["files_not_started"] else "")
              + f". The rate above is over the judged mutants only: PARTIAL.")
    if cache is not None:
        cs = total["cache"]
        print(f"h6: cache: {cs['hits']} hit(s), {cs['misses']} miss(es), {cs['mutants_reused']} mutant verdict(s) reused")
        for f, why in cs["miss_reasons"].items():
            print(f"  miss {f}: {why}")
    print(f"h6: {rcheck.rel(os.path.join(out, stem + '.json'))}, {rcheck.rel(os.path.join(out, stem + '.tsv'))}")
    why = ", ".join(x for x in ("--functions (a subset)" if a.functions else "",
                                 "--writer-callees (a subset)" if a.writer_callees else "",
                                 f"time budget: {unjudged} mutant(s) unjudged, {len(total['files_not_started'])} "
                                 f"file(s) not started" if unjudged or total["files_not_started"] else "",
                                 f"{len(problems)} problem(s)" if problems else "") if x)
    print(publish(a.label, rid, out, (stem + ".json", stem + ".tsv"), not why, why))
    if sample and not a.keep_sample:  # hard links and copies of game memory: the run keeps its results only
        shutil.rmtree(os.path.join(out, "sample"), ignore_errors=True)
    return 1 if problems else 0


def h6_files(rid: str, label: str, by_file: dict, have: dict, lib: str, cc: str, sources: list[str], jobs: int,
             at_once: int, cache: "h6cache.Cache | None" = None, prefix: str = "game", sampled: dict | None = None,
             deadline: float | None = None, budget: dict | None = None) -> tuple[dict, list[str]]:
    """mutate.mutate per source file. at_once 1: one file after another, each with `jobs` threads, the baseline
    replays one after another (the order before round 8). at_once > 1: up to at_once files side by side, the object
    cache built once first, the baseline replays side by side, and at most `jobs` child processes at once over all
    files (mutate.set_process_limit). Every file's log is printed in one piece when it ends; results are the same
    either way (the mutants, the records and the verdict rule do not depend on the order).
    sampled: source -> sampled-record key (h56.py h6 --sample), used in the cache key instead of the folders.
    deadline: a file not started by then is skipped (budget["not_started"]); a file cut short by it (mutants
    unjudged) is listed in budget["cut"] and never stored in the cache."""
    results, problems = {}, []
    budget = {} if budget is None else budget
    budget.setdefault("not_started", [])
    budget.setdefault("cut", [])
    lock = threading.Lock()
    pre: dict[str, tuple] = {}  # source -> (key parts, cached rows or None, why missed); looked up before any work
    if cache is not None:
        for src, targets in sorted(by_file.items()):
            runs = sorted({d for t in targets for d in have.get(t.address, [])})
            muts = [[m.mid, m.op, m.line, m.col, m.old, m.new, h6cache.sha_bytes(m.text.encode())]
                    for t in targets for m in mutate.make_mutants(t.source, t.function, say=lambda *_: None)]
            parts = cache.parts(os.path.join(ROOT, src), [(t.function, t.address) for t in targets], muts, runs,
                                sampled=(sampled or {}).get(src) if sampled is not None else None)
            rows, why = cache.lookup(os.path.join(ROOT, src), parts)
            pre[src] = (parts, rows, why)

    def one(item):
        src, targets = item
        runs = sorted({d for t in targets for d in have.get(t.address, [])})
        mlabel = f"{prefix}-h6{label}-{rid}-" + os.path.splitext(os.path.basename(src))[0]
        buf = io.StringIO()
        say = (lambda m: buf.write(str(m) + "\n")) if at_once > 1 else print
        say(f"[{src}] {', '.join(t.function for t in targets)}: {len(runs)} record folder(s)")
        t0 = time.time()
        parts, rows, why = pre.get(src, (None, None, ""))
        if cache is not None:
            say(f"[{src}] cache " + (f"HIT: {len(rows)} mutant verdict(s) reused" if rows is not None else
                                     "miss: " + why))
        if rows is not None:
            rc, summary = 0, cached_summary(mlabel, rows, runs)
        elif deadline is not None and time.time() > deadline:
            say(f"[{src}] not started: time budget reached")
            with lock:
                if at_once > 1:
                    print(buf.getvalue(), end="", flush=True)
                budget["not_started"].append(src)
            return
        else:
            rc, summary = mutate.mutate(mlabel, targets, runs, lib, cc, H.CFLAGS, H.INCS, sources, None, jobs, say=say,
                                        par_baseline=at_once > 1, deadline=deadline)
            if rc == 0 and summary.get("_total", {}).get("unjudged"):
                with lock:
                    budget["cut"].append(src)
            elif cache is not None and rc == 0:
                csv_p = os.path.join(mutate.MUT_DIR, mlabel, "mutants.csv")
                with open(csv_p, newline="", encoding="utf-8") as fh:
                    cache.store(os.path.join(ROOT, src), parts, list(csv.DictReader(fh)), round(time.time() - t0, 1),
                                warn=say)  # round 9: never raises; a failed store is a warning, the result is kept
        say(f"[{src}] {round(time.time() - t0, 1)} s")
        with lock:
            if at_once > 1:
                print(buf.getvalue(), end="", flush=True)
            if rc:
                problems.append(f"{src}: mutate rc {rc}")
                return
            for fn, s in summary.items():
                if not fn.startswith("_"):
                    results[fn] = dict(s, source=src, record_folders=len(runs),
                                       mutants_csv=rcheck.rel(os.path.join(mutate.MUT_DIR, mlabel, "mutants.csv")))

    items = sorted(by_file.items())
    if at_once <= 1:
        mutate.set_process_limit(None)
        for it in items:
            one(it)
        return results, problems
    # the shared object cache (cache-game) once, before any file starts: files side by side must never compile the
    # same object at the same time
    if cache is not None and all(pre[src][1] is not None for src, _ in items):
        for it in items:  # every file a hit: no object cache, no compiler, no replay
            one(it)
        return results, problems
    b = mutate.Builder(cc, H.CFLAGS, H.INCS, sources, os.path.join(mutate.MUT_DIR, "cache-" + prefix))
    stamp = mutate.header_stamp(H.INCS)
    for o in b.objs.values():
        if os.path.isfile(o) and os.path.getmtime(o) < stamp:
            os.remove(o)
    err = b.compile_all(jobs)
    if err:
        return results, [f"object cache does not build: {err[:500]}"]
    mutate.set_process_limit(jobs)
    try:
        # the biggest files first (most mutants), so the last one to finish is a small one
        items.sort(key=lambda it: -sum(len(mutate.make_mutants(t.source, t.function, say=lambda *_: None))
                                       for t in it[1]))
        with concurrent.futures.ThreadPoolExecutor(at_once) as ex:
            list(ex.map(one, items))
    finally:
        mutate.set_process_limit(None)
    problems.sort()
    budget["not_started"].sort()
    budget["cut"].sort()
    return results, problems


def cached_summary(mlabel: str, rows: list[dict], runs: list[str]) -> dict:
    """A cache hit: the stored verdict rows written back as this run's mutants.csv / mutate.json (the same files a
    cold mutate.mutate writes), and summarized the same way."""
    work = os.path.join(mutate.MUT_DIR, mlabel)
    os.makedirs(work, exist_ok=True)
    fields = list(rows[0].keys()) if rows else ["id", "function", "address", "result"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)  # "\r\n" rows, as mutate.py's csv writer
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in fields})
    h6cache.write_atomic(os.path.join(work, "mutants.csv"), buf.getvalue())
    summary = mutate.summarize([dict(r) for r in rows])
    summary["_meta"] = {"label": mlabel, "runs": [rcheck.rel(r) for r in runs], "from_cache": True}
    h6cache.write_atomic(os.path.join(work, "mutate.json"), json.dumps(summary, indent=1))
    return summary


# ------------------------------------------------------------------ self-test
def selftest() -> int:
    import tempfile
    errors, n = [], 0

    def ok(cond, what):
        nonlocal n
        n += 1
        if not cond:
            errors.append(what)

    base = os.path.join(ROOT, "build", "harness", "h56", "selftest")
    shutil.rmtree(base, ignore_errors=True)
    for sess, runs in (("sp", {"a": {"route": "bt-ch2"}, "b": {"route": "bt-ch3"}}),
                       ("sc", {"c": {"route": "cheat-family", "cheat": True}}),
                       ("sx", {"d": {"route": "bt-ch2"}, "e": {"route": "bt-ch2", "start_save_cheat": "cheat-x"}})):
        for run, rj in runs.items():
            d = os.path.join(base, sess, "records", run)
            os.makedirs(d)
            open(os.path.join(d, "records.fecap"), "wb").close()
            with open(os.path.join(d, "run.json"), "w", encoding="utf-8") as fh:
                json.dump(rj, fh)
    ok(len(record_dirs(["sp"], "play", base)) == 2, "real-play session read as play")
    for sess, label in (("sc", "play"), ("sp", "cheat"), ("sx", "play"), ("sx", "cheat")):
        try:
            record_dirs([sess], label, base)
            ok(False, f"{sess} under label {label} refused (F-019)")
        except Stop:
            ok(True, "")
    ok(len(record_dirs(["sc"], "cheat", base)) == 1, "cheat session read under label cheat")
    # round 13: a store-keep run that kept 0 records (run.json, no records.fecap) only for offline.py plan
    d0 = os.path.join(base, "s0", "records", "z")
    os.makedirs(d0)
    with open(os.path.join(d0, "run.json"), "w", encoding="utf-8") as fh:
        json.dump({"route": "bt-ch2", "only": "0x100"}, fh)
    ok(record_dirs(["s0"], "play", base, allow_empty=True) == [d0], "a 0-record folder read with allow_empty")
    try:
        record_dirs(["s0"], "play", base)
        ok(False, "a session of 0-record folders only taken by H5/H6")
    except Stop:
        ok(True, "")
    # a 0-record cheat-route folder in a mixed batch session is left out under a real-play label, used under cheat
    dc = os.path.join(base, "s0", "records", "zc")
    os.makedirs(dc)
    with open(os.path.join(dc, "run.json"), "w", encoding="utf-8") as fh:
        json.dump({"route": "cheat-family", "cheat": True, "only": "0x100"}, fh)
    ok(record_dirs(["s0"], "play", base, allow_empty=True) == [d0], "a 0-record other-track folder not left out")
    ok(record_dirs(["s0"], "cheat", base, allow_empty=True) == [dc], "a 0-record cheat folder not read under cheat")
    ok(len(record_dirs(["s0", "sp"], "play", base, allow_empty=True)) == 3, "0-record and kept folders together")
    try:  # a kept (records.fecap) folder of the other track is still refused with allow_empty
        record_dirs(["s0", "sc"], "play", base, allow_empty=True)
        ok(False, "allow_empty let a cheat record folder into real play")
    except Stop:
        ok(True, "")
    # any label: a real-play label of any name takes real play only, a cheat* label the cheat track only
    ok(len(record_dirs(["sp"], "r8-opt", base)) == 2, "any real-play label (r8-opt) reads real play")
    ok(len(record_dirs(["sc"], "cheat-r8", base)) == 1, "a cheat-r8 label reads the cheat track")
    for sess, label in (("sc", "r8-opt"), ("sp", "cheat-r8")):
        try:
            record_dirs([sess], label, base)
            ok(False, f"{sess} under label {label} refused (F-019)")
        except Stop:
            ok(True, "")
    for bad in ("../x", "a/b", "runs", "", "x" * 65):
        try:
            check_label(bad)
            ok(False, f"label {bad!r} refused")
        except Stop:
            ok(True, "")
    # a route named cheat-* is the cheat track even when run.json forgot the flag
    d = os.path.join(base, "sy", "records", "f")
    os.makedirs(d)
    open(os.path.join(d, "records.fecap"), "wb").close()
    with open(os.path.join(d, "run.json"), "w", encoding="utf-8") as fh:
        json.dump({"route": "cheat-family"}, fh)
    try:
        record_dirs(["sy"], "play", base)
        ok(False, "a cheat-* route without the flag taken as real play")
    except Stop:
        ok(True, "")
    # per-run folders: a run never overwrites another; only a complete run updates <label>/h5.json
    outs = os.path.join(base, "out")
    rid1, d1 = run_dir("lab", "h5", "one", outs)
    try:
        run_dir("lab", "h5", "one", outs)
        ok(False, "an existing run id refused")
    except Stop:
        ok(True, "")
    for dd, txt in ((d1, "complete"),):
        for fname in ("h5.json", "h5.tsv"):
            with open(os.path.join(dd, fname), "w", encoding="utf-8") as fh:
                fh.write(txt)
    publish("lab", rid1, d1, ("h5.json", "h5.tsv"), True, "", outs)
    rid2, d2 = run_dir("lab", "h5", "two", outs)
    for fname in ("h5.json", "h5.tsv"):
        with open(os.path.join(d2, fname), "w", encoding="utf-8") as fh:
            fh.write("partial")
    line = publish("lab", rid2, d2, ("h5.json", "h5.tsv"), False, "--no-exact", outs)
    top = open(os.path.join(outs, "lab", "h5.json"), encoding="utf-8").read()
    latest = json.load(open(os.path.join(outs, "lab", "latest.json"), encoding="utf-8"))
    ok(top == "complete" and "PARTIAL" in line and latest["h5"]["run"] == "one" and latest["partial"] == {"two": "--no-exact"},
       f"a partial run leaves <label>/h5.json alone ({top!r}, {latest})")
    ok(open(os.path.join(d2, "h5.json"), encoding="utf-8").read() == "partial", "the partial run keeps its own results")
    rid3, d3 = run_dir("lab", "h6", None, outs)
    ok(rid3.endswith("-h6") and os.path.isdir(d3), f"default run id is time + command ({rid3})")
    try:
        record_dirs(["nothing"], "play", base)
        ok(False, "a session without records refused")
    except Stop:
        ok(True, "")
    d = os.path.join(base, "sp", "records", "a")
    with open(os.path.join(d, "summary.tsv"), "w", encoding="utf-8") as fh:
        fh.write("# x\naddress\tkind\trecords\n0x003ba88c\toverride\t24\n0x00532DC4\toverride\t0\n")
    ok(summary_addresses(d) == {"0x003BA88C": 24, "0x00532DC4": 0}, f"summary.tsv addresses ({summary_addresses(d)})")
    # gcov JSON: two objects covering one file add up; another file's section stays apart
    cov: dict = {}
    f1 = {"file": "/x/a.c", "lines": [{"line_number": 3, "count": 2, "branches": [{"count": 2}, {"count": 0}]},
                                       {"line_number": 4, "count": 0, "branches": []}],
          "functions": [{"name": "f", "start_line": 2, "end_line": 5, "execution_count": 2}]}
    f2 = {"file": "/x/a.c", "lines": [{"line_number": 3, "count": 1, "branches": [{"count": 0}, {"count": 1}]}],
          "functions": [{"name": "f", "start_line": 2, "end_line": 5, "execution_count": 1}]}
    merge_gcov_file(cov, f1, "/")
    merge_gcov_file(cov, f2, "/")
    merge_gcov_file(cov, {"file": "/x/b.h", "lines": [{"line_number": 3, "count": 9, "branches": []}]}, "/")
    e = cov[os.path.normcase(os.path.abspath("/x/a.c"))]
    ok(e["lines"][3] == (3, [2, 1]) and e["functions"]["f"] == (2, 5, 3), f"gcov counts add up ({e})")
    sc = span_cover(e, 2, 5)
    ok(sc == {"lines": 2, "lines_run": 1, "branches": 2, "branches_taken": 2, "never_taken": [], "never_run": [4]},
       f"span cover ({sc})")
    e2 = {"lines": {3: (1, [1, 0]), 7: (1, [0, 0])}, "functions": {}}
    ok(span_cover(e2, 1, 5)["never_taken"] == [3] and span_cover(e2, 1, 5)["branches"] == 2,
       "lines outside the span are not counted")
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, "build")) as t:
        src = os.path.join(t, "s.c")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write("static int h(int x) {\n  return x + 1;\n}\n\nint g(int x) {\n  if (x)\n    return h(x);\n"
                     "  return 0;\n}\n")
        ok(function_lines(src, "g") == (5, 9) and function_lines(src, "h") == (1, 3), "function line spans")
        cv = {os.path.normcase(os.path.abspath(src)): {"lines": {2: (1, []), 6: (2, [1, 1]), 7: (1, []), 8: (1, [])},
                                                        "functions": {}}}
        oc = override_cover(cv, src, "g")
        ok(oc and oc["helpers"] == ["h"] and oc["own"]["branches_taken"] == 2 and oc["with_helpers"]["lines"] == 4,
           f"override cover with a static helper ({oc})")
        defs = definitions([src])
        ok(set(defs) == {"g", "h"} and closure(defs, "g") == ["g", "h"] and closure(defs, "h") == ["h"],
           f"definitions and call closure ({sorted(defs)})")
        ok(closure_cover(cv, defs, ["g", "h"])["lines"] == 4, "closure cover adds the callee's lines")
    rows = [{"id": "g_rel_1", "function": "g", "address": "0x00001000", "result": "caught", "by": "mismatch_r0@0x00001000"},
            {"id": "g_const_2", "function": "g", "address": "0x00001000", "result": "survived", "by": ""},
            {"id": "g_named_3", "function": "g", "address": "0x00001000", "result": "caught", "by": "mismatch_r0@0x00002000"}]
    cs = cached_summary("selftest-h6cache", rows, [])
    work = os.path.join(mutate.MUT_DIR, "selftest-h6cache")
    with open(os.path.join(work, "mutants.csv"), newline="", encoding="utf-8") as fh:
        back = list(csv.DictReader(fh))
    ok(back == rows and cs["g"]["caught"] == 2 and cs["g"]["caught_via_caller"] == 1 and cs["g"]["judged"] == 3,
       f"a cache hit writes the stored rows back and summarizes them as mutate does ({cs.get('g')})")
    shutil.rmtree(work, ignore_errors=True)
    # time budget (F-024): an unjudged mutant is not counted; a file not started by the deadline is listed, no work
    sm = mutate.summarize(rows + [{"id": "g_rel_4", "function": "g", "address": "0x00001000", "result": "unjudged",
                                   "by": "time budget"}])
    ok(sm["g"]["judged"] == 3 and sm["g"]["unjudged"] == 1 and sm["_total"]["unjudged"] == 1,
       f"an unjudged mutant is not judged ({sm['g']})")
    bud: dict = {}
    res, probs = h6_files("st", "selftest", {"src/x.c": [mutate.Target("g", "0x00001000", os.path.join(ROOT, "src/x.c"))]},
                          {}, "", "", [], 1, 1, None, "selftest", deadline=time.time() - 1, budget=bud)
    ok(res == {} and probs == [] and bud.get("not_started") == ["src/x.c"] and bud.get("cut") == [],
       f"a file not started before the deadline is listed and not run ({bud}, {probs})")
    shutil.rmtree(os.path.join(mutate.MUT_DIR, "selftest-h6selftest-st-x"), ignore_errors=True)
    # round 12 lanes: python sum of two gcov results = one result with both runs
    acc: dict = {}
    add_cov(acc, {"k": {"lines": {3: (2, [2, 0])}, "functions": {"f": (2, 5, 2)}}})
    add_cov(acc, {"k": {"lines": {3: (1, [0, 1]), 4: (1, [])}, "functions": {"f": (2, 5, 1)}}})
    ok(acc == {"k": {"lines": {3: (3, [2, 1]), 4: (1, [])}, "functions": {"f": (2, 5, 3)}}}, f"add_cov sums ({acc})")
    # round 12 lanes on a real gcov build: three runs into one counter folder (serial) give exactly the counts of the
    # same runs spread over lanes (GCOV_PREFIX, one folder each, one empty) and merged, by gcov-tool and by python
    cc = rcheck.find_cc()
    if cc:
        with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, "build")) as t:
            src, obj = os.path.join(t, "lanes.c"), os.path.join(t, "obj")
            os.makedirs(obj)
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("#include <stdlib.h>\nint main(int c, char **v) {\n  int n = atoi(v[1]), s = 0;\n"
                         "  for (int i = 0; i < n; i++) {\n    if (i % 3)\n      s++;\n    else\n      s--;\n  }\n"
                         "  return s & 1;\n}\n")
            exe = os.path.join(t, "lanes" + H.EXE)
            rc1, t1 = H.run([cc, "--coverage", "-c", src, "-o", os.path.join(obj, "lanes_0001.o")], timeout=120)
            rc2, t2 = H.run([cc, "--coverage", os.path.join(obj, "lanes_0001.o"), "-o", exe], timeout=120)
            ok(rc1 == 0 and rc2 == 0, f"lanes test program builds ({t1[-200:]} {t2[-200:]})")
            for n_ in ("5", "7", "9"):
                H.run([exe, n_])
            serial = gcov_json(obj, os.path.join(t, "gs"))
            for g in glob.glob(os.path.join(obj, "*.gcda")):
                os.remove(g)
            lanes_ = [os.path.join(t, f"lane{k}") for k in range(3)]
            for ld in lanes_:
                os.makedirs(ld)
            for ld, n_ in ((lanes_[0], "5"), (lanes_[1], "7"), (lanes_[1], "9")):
                H.run([exe, n_], {"GCOV_PREFIX": ld, "GCOV_PREFIX_STRIP": "99"})
            ok(not glob.glob(os.path.join(obj, "*.gcda")) and len(glob.glob(os.path.join(lanes_[1], "*.gcda"))) == 1,
               "GCOV_PREFIX sends the counters to the lane folder, not the build's")
            key = os.path.normcase(os.path.abspath(src))
            ok(key in serial and serial[key]["functions"].get("main", (0, 0, 0))[2] == 3,
               f"serial gcov counts three runs ({serial.get(key, {}).get('functions')})")
            if gcov_tool():
                how, cv = merge_lanes(lanes_, obj, os.path.join(t, "m"), "gcov-tool")
                merged = gcov_json(obj, os.path.join(t, "gm"))
                ok(cv is None and "gcov-tool" in how and merged == serial,
                   f"gcov-tool merge of the lanes = the serial counters ({how})")
            how, cv = merge_lanes(lanes_, obj, os.path.join(t, "p"), "python")
            ok(cv == serial and "python" in how, f"python sum of the lanes = the serial counters ({how})")
    # a session whose folders list no override (no summary.tsv) is refused, never published as an empty COMPLETE run
    rd = os.path.join(base, "sz", "records", "z")
    os.makedirs(rd)
    open(os.path.join(rd, "records.fecap"), "wb").close()
    with open(os.path.join(rd, "run.json"), "w", encoding="utf-8") as fh:
        json.dump({"route": "bt-ch2"}, fh)
    global PAR
    old_par, PAR = PAR, base
    said = io.StringIO()
    try:
        import contextlib
        with contextlib.redirect_stdout(said):
            fake_lib = os.path.join(base, "fake.dll")  # never loaded: the run must stop before any build
            open(fake_lib, "wb").close()
            rc = main(["h6", "--sessions", "sz", "--label", "selftest-empty", "--run-id", "st-empty", "--h5",
                       os.path.join(base, "none.json"), "--lib", fake_lib])
    finally:
        PAR = old_par
    ok(rc == 3 and "no override to mutate" in said.getvalue(),
       f"an h6 run with no override to mutate is refused (rc {rc}: {said.getvalue()[-200:]!r})")
    shutil.rmtree(os.path.join(OUT, "selftest-empty"), ignore_errors=True)
    shutil.rmtree(base, ignore_errors=True)
    for e in errors:
        print(f"  FAIL  {e}")
    print(f"h56 self-test: {n - len(errors)}/{n} checks passed")
    return 1 if errors else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", choices=["h5", "h6"])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--sessions", help="comma list of parallel.py sessions with records/")
    ap.add_argument("--label", default="play", help="any name (letters, digits, _ . -); one starting with 'cheat' is "
                                                     "the cheat track (F-019)")
    ap.add_argument("--run-id", help="this run's folder name under <label>/runs/ (default: start time + command)")
    ap.add_argument("--functions", help="h6: these overrides only (a partial run)")
    ap.add_argument("--jobs", type=int, help="h5: record folders at once, each lane with its own gcov counter "
                                              "folder (1 = serial); h6: compiler / replay.exe processes; default "
                                              "and cap FEF_ROBOT_JOBS / max_parallel_runs")
    ap.add_argument("--jobs-over-budget", action="store_true",
                    help="h5 and h6: take --jobs as given even above FEF_ROBOT_JOBS / max_parallel_runs (h5: that "
                         "many lanes, each with its own gcov counter folder; h6: that many compiler / replay.exe "
                         "processes; spare cores, below-normal priority)")
    ap.add_argument("--files-at-once", type=int, help="h6: source files side by side (default --jobs; 1 = the old "
                                                      "one-at-a-time order)")
    ap.add_argument("--writer-callees", action="store_true",
                    help="h6: only the readable callees of the writer slots of docs/harness/HOOK_LIST.md (a writer H6)")
    ap.add_argument("--h5", help="h6: the h5.json whose MATCH overrides are mutated (default <label>/h5.json)")
    ap.add_argument("--cache", action="store_true",
                    help="h6: reuse each source file's mutant verdicts when its cache key is unchanged (h6cache.py)")
    ap.add_argument("--no-cache", action="store_true",
                    help="h6: every file cold (no hit), the cache entries refreshed (the weekly clean run)")
    ap.add_argument("--cache-dir", help="h6: cache folder (default build/harness/h56/h6cache; with --sample its "
                                         "sampled/ subfolder)")
    ap.add_argument("--obj-prefix", default="game",
                    help="h6: prefix of the mutate work folders and object cache (default game: cache-game)")
    ap.add_argument("--sample", action="store_true",
                    help="h6: replay a per-function sample of the records (h6sample.py; F-024): a cover of every "
                         "block met, then distinct input signatures up to --sample-n")
    ap.add_argument("--sample-n", type=int, default=h6sample.DEFAULT_N,
                    help=f"h6 --sample: input signatures kept per override (default {h6sample.DEFAULT_N}; the "
                         "block cover is always kept, even past N)")
    ap.add_argument("--keep-sample", action="store_true", help="h6 --sample: keep the sample folders in the run")
    ap.add_argument("--budget-min", type=float,
                    help="h6: stop cleanly after this many minutes (mutants not started: unjudged, run PARTIAL)")
    ap.add_argument("--lib")
    ap.add_argument("--no-exact", action="store_true", help="h5: aggregate coverage only (faster)")
    ap.add_argument("--merge", choices=["auto", "gcov-tool", "python"], default="auto",
                    help="h5 with more than one lane: how the lanes' counters are merged (auto: gcov-tool when found "
                         "beside the host compiler, else python)")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.command or not a.sessions:
        ap.print_help()
        return 2
    try:
        return cmd_h5(a) if a.command == "h5" else cmd_h6(a)
    except Stop as e:
        print(f"h56: SETUP: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
