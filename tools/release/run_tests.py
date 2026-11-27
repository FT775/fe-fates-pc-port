"""The unit test runner for the release core (round 67, release part A, goal 1).

    python tools/release/run_tests.py --core            the core: every test except those in tests/heavy.txt
    python tools/release/run_tests.py --full            every test (the same set as plain unittest discover)
    python tools/release/run_tests.py --core --list     print the test ids the profile runs (nothing runs)
    python tools/release/run_tests.py --check-lists     tests/heavy.txt and tests/core.txt name real tests, and no
                                                        quick guard is heavy
    options: --lanes N (default 4)  --modules test_a,test_b  --out DIR  --lane-timeout S (default 1800)

Lanes: whole test modules, longest first by the measured times (config/release/test_times.json, then the last run's
build/release/test_times.json), each lane on the module that has the least work so far. Each lane is its own
`python run_tests.py --lane-worker SPEC` process (no window, below-normal priority) that uses unittest's own
discovery for its modules, leaves out the heavy ids in --core, and writes a JSON result. The summary is a plain table;
the exit code is 0 only when every lane finished, at least one test ran, and nothing failed or errored.
Plain `python -m unittest discover -s tests -t .` is unchanged and still runs everything.
Round 83 (F-070): the Seal of Flames edition's own tests live in tests/seal/ (a package); their module names here are
`seal.<file>` (test ids `tests.seal.<file>.<Class>.<test>`), e.g. --modules seal.test_sof_path.
Round 84 (edition-aware): in a folder without tests/seal (the Vanilla+ edition) the `tests.seal.*` ids named in
tests/core.txt and tests/heavy.txt and the `seal.*` modules in config/release/test_times.json are skipped, never
failed, and every run, --list and --check-lists prints how many ("Seal edition not here ...").
"""
from __future__ import annotations

import argparse
import fnmatch
import glob
import io
import json
import os
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TESTS = os.path.join(ROOT, "tests")
HEAVY = os.path.join(TESTS, "heavy.txt")
CORE = os.path.join(TESTS, "core.txt")
TIMES_TRACKED = os.path.join(ROOT, "config", "release", "test_times.json")
TIMES_LAST = os.path.join(ROOT, "build", "release", "test_times.json")
OUT_TOP = os.path.join(ROOT, "build", "release", "tests")
SUBDIRS = ("seal",)   # round 83 (F-070): test packages below tests/ whose modules are named "<sub>.<file>"
SEAL_SUB = "seal"     # round 84: the Seal edition's test package (absent in the Vanilla+ edition)
SEAL_ID = "tests.seal."
SEAL_MODULE = "seal."
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
BELOW_NORMAL = 0x00004000 if os.name == "nt" else 0


# ------------------------------------------------------------------------------------------------ editions
def seal_here(tests_dir: str | None = None) -> bool:
    """round 84: the Seal edition's tests are here (tests/seal/__init__.py)"""
    return os.path.isfile(os.path.join(tests_dir or TESTS, SEAL_SUB, "__init__.py"))


def _edition_filter(items: list, tid_of=lambda x: x) -> list:
    """the list without the tests.seal.* ids when tests/seal is not here (the Vanilla+ edition)"""
    if seal_here():
        return items
    return [x for x in items if not tid_of(x).startswith(SEAL_ID)]


def seal_skipped(heavy: str = HEAVY, core: str = CORE, times: str = TIMES_TRACKED) -> dict[str, int]:
    """{list name: Seal ids it names} for the lists a Vanilla+ folder leaves out (empty when tests/seal is here):
    tests/core.txt and tests/heavy.txt ids tests.seal.*, config/release/test_times.json modules seal.*"""
    if seal_here():
        return {}
    out: dict[str, int] = {}

    def lines(path):
        if not os.path.isfile(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return [ln.split("#", 1)[0].strip() for ln in fh]
    out[os.path.basename(heavy)] = sum(1 for ln in lines(heavy) if ln.startswith(SEAL_ID))
    out[os.path.basename(core)] = sum(1 for ln in lines(core) if ln and ln.split()[-1].startswith(SEAL_ID))
    mods: set[str] = set()
    if os.path.isfile(times):
        try:
            with open(times, encoding="utf-8") as fh:
                d = json.load(fh)
            for prof in d.values():
                if isinstance(prof, dict):
                    mods |= {k for k in prof if k.startswith(SEAL_MODULE)}
        except (OSError, ValueError):
            pass
    out[os.path.basename(times)] = len(mods)
    return {k: v for k, v in out.items() if v}


def seal_note() -> str:
    """one plain line when Seal ids are skipped (empty in the Seal edition and on the dev machine)"""
    s = seal_skipped()
    if not s:
        return ""
    parts = ", ".join(f"{k} {v}" for k, v in sorted(s.items()))
    return (f"Seal edition not here (no tests/seal): skipped {sum(s.values())} Seal test ids "
            f"({parts}); they are not failures")


# ------------------------------------------------------------------------------------------------ lists
def read_heavy(path: str = HEAVY) -> list[str]:
    """the heavy test ids / fnmatch patterns ('#' comments and blank lines skipped); without tests/seal the
    tests.seal.* entries are left out and counted (round 84)"""
    out = []
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.split("#", 1)[0].strip()
            if ln:
                out.append(ln)
    return _edition_filter(out)


def read_core(path: str = CORE) -> list[tuple[str, str]]:
    """the quick-guard list: [(track, test id)]; without tests/seal the tests.seal.* ids are left out and counted"""
    out = []
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.split("#", 1)[0].strip()
            if ln:
                track, tid = ln.split()
                out.append((track, tid))
    return _edition_filter(out, lambda x: x[1])


def is_heavy(tid: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(tid, p) for p in patterns)


def modules(names: list[str] | None = None) -> list[str]:
    """tests/test_*.py as "test_x" and tests/<sub>/test_*.py as "<sub>.test_x" (SUBDIRS; round 83)"""
    found = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(TESTS, "test_*.py")))
    for sub in SUBDIRS:
        if os.path.isfile(os.path.join(TESTS, sub, "__init__.py")):
            subs = sorted(os.path.splitext(os.path.basename(p))[0]
                          for p in glob.glob(os.path.join(TESTS, sub, "test_*.py")))
            twice = sorted(set(subs) & set(found))
            if twice:   # one file name in both places would run twice (discover walks into the package)
                raise SystemExit(f"test module in both tests/ and tests/{sub}/: {', '.join(twice)}")
            found += [f"{sub}.{m}" for m in subs]
    if names:
        bad = sorted(set(names) - set(found))
        if bad:
            raise SystemExit(f"no such test module: {', '.join(bad)}")
        found = [m for m in found if m in names]
    return found


# ------------------------------------------------------------------------------------------------ suites
def iter_tests(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from iter_tests(t)
        else:
            yield t


def filtered(suite: unittest.TestSuite, exclude: list[str]) -> unittest.TestSuite:
    """the same suite tree without the tests whose id matches an exclude pattern (loader errors are kept)"""
    out = unittest.TestSuite()
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            sub = filtered(t, exclude)
            if sub.countTestCases():
                out.addTest(sub)
        elif not is_heavy(t.id(), exclude):
            out.addTest(t)
    return out


def load_module(loader: unittest.TestLoader, module: str, tests_dir: str = TESTS, top: str = ROOT) -> unittest.TestSuite:
    """unittest's own discovery, limited to one module file ("<sub>.test_x" = tests/<sub>/test_x.py)"""
    if "." in module:
        sub, name = module.rsplit(".", 1)
        return loader.discover(os.path.join(tests_dir, *sub.split(".")), pattern=f"{name}.py", top_level_dir=top)
    return loader.discover(tests_dir, pattern=f"{module}.py", top_level_dir=top)


def selected_ids(mods: list[str], exclude: list[str]) -> dict[str, list[str]]:
    loader = unittest.TestLoader()
    return {m: [t.id() for t in iter_tests(filtered(load_module(loader, m), exclude))] for m in mods}


def check_lists() -> list[str]:
    """problems with tests/heavy.txt and tests/core.txt (empty = fine)"""
    heavy, core = read_heavy(), read_core()
    ids = {t for v in selected_ids(modules(), []).values() for t in v}
    bad = [f"heavy.txt: '{p}' matches no test" for p in heavy if not any(fnmatch.fnmatchcase(t, p) for t in ids)]
    bad += [f"core.txt: {tr} '{t}' is not a test" for tr, t in core if t not in ids]
    bad += [f"core.txt: {tr} '{t}' is in heavy.txt" for tr, t in core if is_heavy(t, heavy)]
    tracks = [tr for tr, _t in core]
    bad += [f"core.txt: track '{tr}' listed twice" for tr in sorted(set(tracks)) if tracks.count(tr) > 1]
    return bad


# ------------------------------------------------------------------------------------------------ lanes
def measured_times(profile: str = "full") -> dict[str, float]:
    """module -> seconds for this profile: the tracked measurements, then the last run's (a module with no core
    time uses its full time)"""
    times: dict[str, float] = {}
    for p in (TIMES_TRACKED, TIMES_LAST):
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    d = json.load(fh)
                times.update({k: float(v) for k, v in d.get("full", {}).items()})
                if profile == "core":
                    times.update({k: float(v) for k, v in d.get("core", {}).items()})
            except (OSError, ValueError):
                pass
    if not seal_here():   # round 84: the Vanilla+ edition has no seal.* modules to plan
        times = {k: v for k, v in times.items() if not k.startswith(SEAL_MODULE)}
    return times


def plan_lanes(mods: list[str], n: int, times: dict[str, float]) -> list[list[str]]:
    """longest first, each module to the lane with the least work so far (unknown modules count 30 s)"""
    n = max(1, min(n, len(mods)))
    lanes: list[list[str]] = [[] for _ in range(n)]
    load = [0.0] * n
    for m in sorted(mods, key=lambda m: (-times.get(m, 30.0), m)):
        i = min(range(n), key=lambda j: (load[j], j))
        lanes[i].append(m)
        load[i] += times.get(m, 30.0)
    return [ln for ln in lanes if ln]


class _Result(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.times: dict[str, float] = {}
        self._t0 = 0.0

    def startTest(self, test):
        self._t0 = time.monotonic()
        super().startTest(test)

    def stopTest(self, test):
        self.times[test.id()] = round(time.monotonic() - self._t0, 3)
        super().stopTest(test)


def lane_worker(spec_path: str) -> int:
    """run one lane: {modules, exclude, result, log}; writes the result JSON"""
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    loader = unittest.TestLoader()
    res = {"modules": {}, "tests": {}}
    with open(spec["log"], "w", encoding="utf-8", errors="backslashreplace") as log:
        for m in spec["modules"]:
            t0 = time.monotonic()
            suite = filtered(load_module(loader, m, spec.get("tests_dir", TESTS), spec.get("top", ROOT)),
                             spec["exclude"])
            log.write(f"===== {m} ({suite.countTestCases()} tests)\n")
            log.flush()
            runner = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=_Result)
            r = runner.run(suite)
            res["modules"][m] = {
                "ran": r.testsRun, "seconds": round(time.monotonic() - t0, 2),
                "failures": [[t.id(), tb[-3000:]] for t, tb in r.failures],
                "errors": [[t.id(), tb[-3000:]] for t, tb in r.errors],
                "skipped": [[t.id(), why] for t, why in r.skipped],
                "unexpected_successes": [t.id() for t in r.unexpectedSuccesses],
                "expected_failures": len(r.expectedFailures)}
            res["tests"].update(r.times)
            with open(spec["result"] + ".tmp", "w", encoding="utf-8") as fh:
                json.dump(res, fh, indent=1)
            os.replace(spec["result"] + ".tmp", spec["result"])
    return 0


def kill_tree(p: subprocess.Popen):
    if p.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True,
                       creationflags=NO_WINDOW)
    else:
        p.kill()


def run(profile: str, mods: list[str], lanes_n: int, out: str, lane_timeout: int, exclude: list[str] | None = None,
        tests_dir: str = TESTS, top: str = ROOT, save_times: bool = True) -> dict:
    """run the modules in lanes; exclude/tests_dir/top are for the runner's own self-test"""
    if exclude is None:
        exclude = read_heavy() if profile == "core" else []
    os.makedirs(out, exist_ok=True)
    plan = plan_lanes(mods, lanes_n, measured_times(profile))
    procs = []
    t0 = time.monotonic()
    try:
        for i, lane in enumerate(plan, 1):
            spec = {"modules": lane, "exclude": exclude, "result": os.path.join(out, f"lane{i}.json"),
                    "log": os.path.join(out, f"lane{i}.log"), "tests_dir": tests_dir, "top": top}
            sp = os.path.join(out, f"lane{i}.spec.json")
            with open(sp, "w", encoding="utf-8") as fh:
                json.dump(spec, fh, indent=1)
            fo = open(os.path.join(out, f"lane{i}.out"), "w", encoding="utf-8", errors="backslashreplace")
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--lane-worker", sp], cwd=ROOT,
                                 stdout=fo, stderr=subprocess.STDOUT, env=env, creationflags=NO_WINDOW | BELOW_NORMAL)
            procs.append((i, lane, p, fo, spec))
        deadline = time.monotonic() + lane_timeout
        for _i, _lane, p, _fo, _spec in procs:
            try:
                p.wait(timeout=max(1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                kill_tree(p)
    except KeyboardInterrupt:
        for _i, _lane, p, _fo, _spec in procs:
            kill_tree(p)
        raise
    finally:
        for _i, _lane, p, fo, _spec in procs:
            kill_tree(p)
            fo.close()
    wall = round(time.monotonic() - t0, 1)
    summary = {"profile": profile, "wall": wall, "lanes": [], "modules": {}, "problems": []}
    for i, lane, p, _fo, spec in procs:
        got = {}
        if os.path.isfile(spec["result"]):
            with open(spec["result"], encoding="utf-8") as fh:
                got = json.load(fh)
        done = got.get("modules", {})
        summary["lanes"].append({"lane": i, "modules": lane, "rc": p.returncode,
                                 "seconds": round(sum(v["seconds"] for v in done.values()), 1)})
        for m in lane:
            if m in done:
                summary["modules"][m] = dict(done[m], lane=i)
            else:
                summary["problems"].append(f"lane {i}: {m} did not finish (rc {p.returncode}; see {spec['log']})")
        if p.returncode not in (0, None):
            summary["problems"].append(f"lane {i} exited with {p.returncode} (see {os.path.join(out, f'lane{i}.out')})")
    ran = sum(v["ran"] for v in summary["modules"].values())
    fails = sum(len(v["failures"]) + len(v["errors"]) + len(v["unexpected_successes"])
                for v in summary["modules"].values())
    summary.update(ran=ran, failed=fails, skipped=sum(len(v["skipped"]) for v in summary["modules"].values()))
    summary["ok"] = not summary["problems"] and fails == 0 and ran > 0
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    if save_times and not summary["problems"]:
        _save_times(summary)
    return summary


def _save_times(summary: dict):
    """the last measured module times per profile, for the next lane plan (build/, never tracked)"""
    data = {}
    if os.path.isfile(TIMES_LAST):
        try:
            with open(TIMES_LAST, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = {}
    prof = dict(data.get(summary["profile"], {}))
    prof.update({m: v["seconds"] for m, v in summary["modules"].items()})
    data[summary["profile"]] = prof
    data["note"] = "last run_tests.py module walls in seconds, per profile"
    os.makedirs(os.path.dirname(TIMES_LAST), exist_ok=True)
    with open(TIMES_LAST, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)


def report(summary: dict, out: str) -> str:
    buf = io.StringIO()
    w = max([len(m) for m in summary["modules"]] + [20])
    buf.write(f"{'module':<{w}} lane  tests  fail  skip   secs\n")
    for m, v in sorted(summary["modules"].items(), key=lambda kv: -kv[1]["seconds"]):
        f = len(v["failures"]) + len(v["errors"]) + len(v["unexpected_successes"])
        buf.write(f"{m:<{w}} {v['lane']:>4} {v['ran']:>6} {f:>5} {len(v['skipped']):>5} {v['seconds']:>6.1f}\n")
    for ln in summary["lanes"]:
        buf.write(f"lane {ln['lane']}: {ln['seconds']:.1f} s, {len(ln['modules'])} modules, rc {ln['rc']}\n")
    for m, v in sorted(summary["modules"].items()):
        for tid, tb in v["failures"] + v["errors"]:
            last = [x for x in tb.strip().splitlines() if x.strip()][-1:] or [""]
            buf.write(f"FAILED {tid}: {last[0][:300]}\n")
        for tid in v["unexpected_successes"]:
            buf.write(f"FAILED {tid}: unexpected success\n")
        for tid, why in v["skipped"]:
            buf.write(f"skipped {tid}: {why}\n")
    for p in summary["problems"]:
        buf.write(f"PROBLEM {p}\n")
    verdict = "PASS" if summary["ok"] else "FAIL"
    buf.write(f"{verdict}: {summary['profile']} - {summary['ran']} tests in {len(summary['modules'])} modules, "
              f"{summary['failed']} failed, {summary['skipped']} skipped, {summary['wall']} s wall on "
              f"{len(summary['lanes'])} lanes (logs: {os.path.relpath(out, ROOT)})\n")
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--core", action="store_true", help="every test except tests/heavy.txt (the default)")
    g.add_argument("--full", action="store_true", help="every test")
    ap.add_argument("--list", action="store_true", help="print the test ids the profile runs; run nothing")
    ap.add_argument("--check-lists", action="store_true", help="check tests/heavy.txt and tests/core.txt")
    ap.add_argument("--lanes", type=int, default=4)
    ap.add_argument("--modules", default=None, help="comma-separated module names (default: every tests/test_*.py and "
                                                     "tests/seal/test_*.py as seal.test_x)")
    ap.add_argument("--out", default=None, help="log folder (default build/release/tests/<time>-<profile>)")
    ap.add_argument("--lane-timeout", type=int, default=1800)
    ap.add_argument("--lane-worker", default=None, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.lane_worker:
        return lane_worker(a.lane_worker)
    profile = "full" if a.full else "core"
    if a.check_lists:
        bad = check_lists()
        for b in bad:
            print(b)
        if seal_note():
            print(seal_note())
        print(("FAIL: " if bad else "PASS: ") + f"tests/heavy.txt {len(read_heavy())} entries, "
              f"tests/core.txt {len(read_core())} quick guards")
        return 1 if bad else 0
    mods = modules([m.strip() for m in a.modules.split(",")] if a.modules else None)
    if a.list:
        exclude = read_heavy() if profile == "core" else []
        ids = selected_ids(mods, exclude)
        for m in mods:
            for t in ids[m]:
                print(t)
        print(f"# {profile}: {sum(len(v) for v in ids.values())} tests in {len(mods)} modules"
              + (f" ({len(read_heavy())} heavy entries left out)" if profile == "core" else ""))
        if seal_note():
            print("# " + seal_note())
        return 0
    if a.lanes < 1:
        print("ERROR: --lanes must be 1 or more")
        return 2
    out = os.path.abspath(a.out) if a.out else os.path.join(OUT_TOP, f"{time.strftime('%Y%m%d-%H%M%S')}-{profile}")
    lanes = plan_lanes(mods, a.lanes, measured_times(profile))
    print(f"{profile}: {len(mods)} modules on {len(lanes)} lanes: "
          + "; ".join(f"[{', '.join(ln)}]" for ln in lanes), flush=True)
    summary = run(profile, mods, a.lanes, out, a.lane_timeout)
    print(report(summary, out), end="")
    if seal_note():
        print(seal_note())
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
