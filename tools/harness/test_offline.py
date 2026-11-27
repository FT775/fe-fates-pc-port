#!/usr/bin/env python3
"""Tests for the round-9 speed items in tools/harness/offline.py and tools/harness/parallel.py
(docs/harness/PARALLEL.md 6, docs/harness/H56.md 8). Fake children and invented data only (about 20 s):

    python tools/harness/test_offline.py

- offline.py --selftest: the live/offline rule (route input, frames, save, save_at, start save, routes.json entry,
  boot.exe, clock, incomplete run; new, moved, gone overrides), the offline summary.tsv read back by parallel.py's
  pass rule, the table compare (a planted difference is seen);
- parallel.py: the measured first memory estimate (item 3: two 0.72 GB copies side by side in a 2.7 GB budget, one
  at a time with the old 1.5 GB guess), longest-first order (item 6), --capture-jobs (never below the normal cap,
  held back by other boot.exe processes, held to the owner's night maximum), --lib copied into the session.
Scratch: build/speed/replay/test-*/ and build/parallel/sp-replay-test-*/ (removed at the end).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import offline  # noqa: E402
import parallel as par  # noqa: E402

SLEEP = [sys.executable, "-c", "import time; time.sleep(1.5)"]


def quiet(*_a, **_k):
    pass


def lim(jobs=3, mem_gb=2.7):
    return par.Limits(jobs, "below_normal", mem_gb)


def job(name, route, mode="original"):
    return par.Job(name, list(SLEEP), info={"route": route, "mode": mode})


class OfflineRuleTests(unittest.TestCase):
    def test_selftest(self):
        self.assertEqual(offline.selftest(), 0)


class MemoryEstimateTests(unittest.TestCase):
    PAST = [{"route": "bt-ch10", "mode": "original", "ok": True, "peak_mem_mb": 722.8, "wall_seconds": 343, "_when": 2},
            {"route": "bt-ch10", "mode": "original", "ok": True, "peak_mem_mb": 722.1, "wall_seconds": 345, "_when": 1},
            {"route": "bt-ch10", "mode": "capture", "ok": True, "peak_mem_mb": 380.0, "wall_seconds": 400, "_when": 1},
            {"route": "bt-ch10", "mode": "original", "ok": False, "peak_mem_mb": 4000.0, "wall_seconds": 9, "_when": 3},
            {"route": "title", "mode": "original", "ok": True, "peak_mem_mb": 330.0, "wall_seconds": 11, "_when": 1}]

    def test_peak_of_the_same_route_and_mode(self):
        mb, note = par.measured_peak_mb(["bt-ch10", "bt-ch10"], "original", self.PAST)
        self.assertEqual(mb, 722.8)  # a failed run's peak is not used
        self.assertIn("bt-ch10", note)
        self.assertEqual(par.measured_peak_mb(["bt-ch10"], "capture", self.PAST)[0], 380.0)
        self.assertEqual(par.measured_peak_mb(["title", "bt-ch10"], "original", self.PAST)[0], 722.8)

    def test_unmeasured_route_keeps_the_old_guess(self):
        self.assertIsNone(par.measured_peak_mb(["bt-ch10", "new-route"], "original", self.PAST)[0])
        self.assertIsNone(par.measured_peak_mb(["cq-ch8"], "original", self.PAST)[0], "no cq route measured")

    def test_new_route_uses_its_family(self):
        """Round 10: bt-ch12 never ran; bt-ch10's peak (same family, same mode) is the first estimate, so two copies
        fit side by side instead of one after the other on the 1.5 GB guess (round 9: 366 MB peaks, run serially)."""
        mb, note = par.measured_peak_mb(["bt-ch12"], "original", self.PAST)
        self.assertEqual(mb, 722.8)
        self.assertIn("like bt-ch10", note)
        self.assertEqual(par.measured_peak_mb(["bt-ch12"], "capture", self.PAST)[0], 380.0, "same mode only")
        self.assertEqual(par.route_family("bt-ch12-clear"), "bt")
        self.assertEqual(par.route_family("rv-ch9"), "rv")
        self.assertEqual(par.route_family("title"), "title")

    def test_session_job_default_timeout_is_run_timeout(self):
        """Round 10: Session.job without timeout= uses run_timeout (was a flat 900 s), the pool adds 120 s."""
        import inspect
        self.assertIsNone(inspect.signature(par.Session.job).parameters["timeout"].default)
        self.assertIn("run_timeout(route, mode, 1)", inspect.getsource(par.Session.job))

    def test_two_copies_side_by_side(self):
        """Item 3: budget 2.7 GB (FEF_ROBOT_MEM_GB of the robot's determinism runs): 1.5 GB each -> one at a time;
        the measured 0.72 GB + 15% -> both at once."""
        est = round(722.8 * par.MEM_MARGIN / 1024, 3)
        for gb, want in ((1.5, 1), (est, 2)):
            pool = par.Pool(lim(jobs=3, mem_gb=2.7), mem_per_run_gb=gb, reserve_gb=0, say=quiet, tick=0.05, adapt=False)
            pool.run([job("a", "bt-ch10"), job("b", "bt-ch10")])
            self.assertEqual(pool.max_running, want, f"estimate {gb} GB")

    def test_execute_uses_the_measured_peak(self):
        a = type("A", (), {"command": "runs", "mem_per_run_gb": None, "reserve_gb": 0})()
        old = par.past_runs
        par.past_runs = lambda roots=None: list(self.PAST)
        try:
            class S:  # the smallest Session execute() needs
                name, say, routes = "sp-replay-test-exec", staticmethod(quiet), {}
                save_src, saves_used = None, set()
                dir = os.path.join(par.OUT, "sp-replay-test-exec")

                def collect(self, results):
                    return [{"run": r["name"], "ok": r["exit_code"] == 0, "peak_mem_mb": r["peak_mem_mb"],
                             "wall_seconds": r["wall_seconds"], "exit_code": r["exit_code"], "route": "bt-ch10"}
                            for r in results]

                def cleanup(self):
                    pass
            os.makedirs(S.dir, exist_ok=True)
            summary, _rc = par.execute(S(), [job("x1", "bt-ch10"), job("x2", "bt-ch10")], lim(jobs=3, mem_gb=2.7), a)
            self.assertIn("measured peak 723 MB", summary["memory_estimate"])
            self.assertEqual(summary["pool"]["max_running"], 2)
        finally:
            par.past_runs = old
            shutil.rmtree(os.path.join(par.OUT, "sp-replay-test-exec"), ignore_errors=True)


class OrderTests(unittest.TestCase):
    def test_longest_first(self):
        past = [{"route": "short", "mode": "capture", "ok": True, "wall_seconds": 30, "_when": 1},
                {"route": "long", "mode": "capture", "ok": True, "wall_seconds": 600, "_when": 1},
                {"route": "long", "mode": "capture", "ok": True, "wall_seconds": 650, "_when": 2},
                {"route": "mid", "mode": "capture", "ok": True, "wall_seconds": 200, "_when": 1}]
        routes = {"new-long": {"frames": 200000}, "new-short": {"frames": 1000}}
        jobs = [job(n, n, "capture") for n in ("short", "new-short", "mid", "long", "new-long")]
        got = [j.name for j in par.longest_first(jobs, past, routes)]
        self.assertEqual(got, ["new-long", "long", "mid", "short", "new-short"])
        self.assertEqual(par.last_wall("long", "capture", past), 650)  # the newest run, not the largest

    def test_default_order_unchanged(self):
        a = par.main.__code__.co_consts  # the flag exists and is off unless given
        self.assertTrue(any("--longest-first" in str(c) for c in a))


class CaptureJobsTests(unittest.TestCase):
    def run_pool(self, others, floor=2, jobs=5, n=5):
        pool = par.Pool(lim(jobs=jobs, mem_gb=8), mem_per_run_gb=0.05, reserve_gb=0, say=quiet, tick=0.05,
                        others=others, floor_jobs=floor)
        pool.run([job(f"c{k}", "r", "capture") for k in range(n)])
        return pool.max_running

    def test_free_slots_are_used(self):
        self.assertEqual(self.run_pool(lambda p: 0), 5)

    def test_other_runs_hold_slots(self):
        self.assertEqual(self.run_pool(lambda p: 2), 3)

    def test_never_below_the_normal_cap(self):
        self.assertEqual(self.run_pool(lambda p: 12), 2)

    def test_count_failure_means_normal_cap(self):
        def broken(_p):
            raise OSError("no process list")
        self.assertEqual(self.run_pool(broken), 2)

    def test_no_others_is_the_old_pool(self):
        pool = par.Pool(lim(jobs=2, mem_gb=8), mem_per_run_gb=0.05, reserve_gb=0, say=quiet, tick=0.05)
        self.assertEqual(pool.job_cap(), 2)

    def test_other_game_runs_excludes_own(self):
        class R:
            def __init__(self, pid):
                self.proc = type("P", (), {"pid": pid})()
                self.tree = type("T", (), {"pids": lambda s: [pid, pid + 1]})()
        pool = type("Pool", (), {"running": {"a": R(100)}})()
        names = lambda: {100: "python.exe", 101: "boot.exe", 200: "boot.exe", 201: "BOOT.EXE", 300: "zakuro.exe"}
        self.assertEqual(par.other_game_runs(pool, names), 2)
        self.assertIsInstance(par.process_names(), dict)

    def test_held_to_the_night_maximum(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "r.json")
            with open(p, "w") as fh:
                json.dump({"max_parallel_runs": 6, "night": {"max_parallel_runs": 12}}, fh)
            self.assertEqual(par.capture_jobs_cap(20, p), 12)
            self.assertEqual(par.capture_jobs_cap(10, p), 10)
            with open(p, "w") as fh:
                json.dump({"max_parallel_runs": 6}, fh)
            self.assertEqual(par.capture_jobs_cap(10, p), 6)

    def test_flag_needs_capture_mode(self):
        out = subprocess.run([sys.executable, par.SELF, "runs", "--route", "title", "--capture-jobs", "8"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 3)
        self.assertIn("--capture-jobs is for --mode capture", out.stdout)


class LibTests(unittest.TestCase):
    def test_lib_is_copied_into_the_session(self):
        hl = par.headless_module()
        if not os.path.isfile(hl.BOOT):
            self.skipTest("no boot.exe")
        d = os.path.join(offline.OUT, "test-lib")
        os.makedirs(d, exist_ok=True)
        fake = os.path.join(d, "fake.dll")
        with open(fake, "wb") as fh:
            fh.write(b"MZ test library")
        with open(os.path.join(d, "harness_build.json"), "w") as fh:
            fh.write("{}")
        sess = par.Session("sp-replay-test-lib", None, say=quiet, lib=fake)
        try:
            sess.stage()
            with open(sess.lib, "rb") as fh:
                self.assertEqual(fh.read(), b"MZ test library")
            self.assertTrue(os.path.isfile(os.path.join(sess.dir, "lib", "harness_build.json")))
            self.assertEqual(par.Session("sp-replay-test-lib2", None, say=quiet).lib_src, None)
        finally:
            par.rmtree_own(sess.dir)
            shutil.rmtree(d, ignore_errors=True)


def write_tsv(path: str, rows: list[tuple[str, int, int]]) -> None:
    """A capture summary.tsv with (address, calls, records) rows."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# fe-capture summary (test)\naddress\tkind\tverdict\tcalls\trecords\tmatch\tcold\twarm\tdeep\tkept\t"
                 "paths\tsignatures\n")
        for a, c, r in rows:
            fh.write(f"{a}\toverride\t{'NO-DATA' if not r else 'SHALLOW'}\t{c}\t{r}\t{r}\t0\t0\t0\t{r}\t0\t\n")


class ZeroRecordTests(unittest.TestCase):
    """Round 13: a store-keep capture run that kept 0 records still leaves records/<run>/run.json (its watched `only`
    list, the library hash, the targets.csv stamp) so offline.py plan sees "watched, never called"."""

    def test_keep_records_writes_a_zero_record_folder(self):
        with tempfile.TemporaryDirectory() as td:
            kept = os.path.join(td, "runs", "r-1")
            os.makedirs(os.path.join(kept, "stage0"))
            os.makedirs(os.path.join(kept, "stage1"))
            rj = {"route": "bt-ch2", "only": "0x100,0x200", "library_sha256": "L", "outcome": "Completed"}
            with open(os.path.join(kept, "run.json"), "w") as fh:
                json.dump(rj, fh)
            os.utime(os.path.join(kept, "run.json"), (1000.0, 1000.0))
            write_tsv(os.path.join(kept, "summary.tsv"), [("0x00000300", 5, 0)])
            write_tsv(os.path.join(kept, "stage0", "summary.tsv"), [])  # a stage with a summary, 0 records
            stamp = {"capture_targets_sha256": "T", "capture_manifest_library_sha256": "L", "capture_git_head": "H"}
            got = par.keep_records(kept, "r-1", os.path.join(td, "records"), stamp)
            self.assertEqual([os.path.basename(x) for x in got], ["r-1", "r-1.stage0"], "stage1 has no summary")
            d = os.path.join(td, "records", "r-1")
            self.assertFalse(os.path.exists(os.path.join(d, "records.fecap")))
            with open(os.path.join(d, "run.json")) as fh:
                back = json.load(fh)
            self.assertEqual(back["only"], "0x100,0x200")
            self.assertEqual(back["library_sha256"], "L")
            self.assertEqual(back["capture_targets_sha256"], "T")
            self.assertIs(back["capture_records_fecap"], False)
            self.assertEqual(os.path.getmtime(os.path.join(d, "run.json")), 1000.0, "the run's own time is kept")
            ri = offline.record_info(d)
            self.assertFalse(ri["fecap"])
            self.assertEqual(ri["targets"], "T")
            self.assertEqual(ri["only"], {0x100, 0x200})
            self.assertEqual(ri["calls"], {0x300: 5})
            # a stamp of another library's manifest is not taken as this run's targets.csv
            with open(os.path.join(kept, "run.json"), "w") as fh:
                json.dump(dict(rj, library_sha256="OTHER"), fh)
            par.keep_records(kept, "r-1", os.path.join(td, "records2"), stamp)
            self.assertIsNone(offline.record_info(os.path.join(td, "records2", "r-1"))["targets"])
            # a run with records keeps them as before (and is stamped records.fecap true)
            with open(os.path.join(kept, "records.fecap"), "wb") as fh:
                fh.write(b"x")
            par.keep_records(kept, "r-1", os.path.join(td, "records3"), stamp)
            self.assertTrue(os.path.isfile(os.path.join(td, "records3", "r-1", "records.fecap")))
            with open(os.path.join(td, "records3", "r-1", "run.json")) as fh:
                self.assertIs(json.load(fh)["capture_records_fecap"], True)

    def test_keep_empty_backfills_from_results(self):
        with tempfile.TemporaryDirectory() as td:
            res = os.path.join(td, "s", "results")
            os.makedirs(res)

            def result(run, mode="capture", store="keep", only="0x100"):
                with open(os.path.join(res, f"{run}.json"), "w") as fh:
                    json.dump({"row": {"mode": mode}, "run_json": {"route": "bt-ch2", "only": only, "store": store,
                                                                   "library_sha256": "NOPE"}}, fh)
            for run in ("s-1", "s-10", "s-2", "s-3", "s-4"):
                result(run, store="keep" if run != "s-4" else False)
            write_tsv(os.path.join(res, "s-1.summary.tsv"), [("0x00000300", 7, 0)])
            write_tsv(os.path.join(res, "s-1.stage0.summary.tsv"), [])
            write_tsv(os.path.join(res, "s-10.summary.tsv"), [])
            write_tsv(os.path.join(res, "s-2.summary.tsv"), [("0x00000100", 3, 3)])  # records, but no folder kept
            write_tsv(os.path.join(res, "s-3.summary.tsv"), [])
            write_tsv(os.path.join(res, "s-4.summary.tsv"), [])  # not a store-keep run
            os.makedirs(os.path.join(td, "s", "records", "s-3"))  # an existing folder is never touched
            said = []
            made = par.keep_empty("s", root=td, say=said.append)
            self.assertEqual(sorted(os.path.basename(x) for x in made), ["s-1", "s-1.stage0", "s-10"])
            self.assertTrue(any("s-2: summary.tsv counts 3 record(s)" in x for x in said), said)
            self.assertEqual(os.listdir(os.path.join(td, "s", "records", "s-3")), [])
            with open(os.path.join(td, "s", "records", "s-1", "run.json")) as fh:
                rj = json.load(fh)
            self.assertIs(rj["capture_records_fecap"], False)
            self.assertNotIn("capture_targets_sha256", rj, "no manifest of library NOPE: no stamp invented")
            self.assertEqual(par.keep_empty("s", root=td, say=said.append), [], "a second run writes nothing")
            with self.assertRaises(par.Stop):
                par.keep_empty("../x", root=td)

    def test_plan_refuses_unknown_hooks(self):
        """Round 13: without --baseline-rev the plan takes each session's targets.csv from its records' run.json (or
        the library's build manifest); a session whose hooks cannot be told stops the plan with a clear message."""
        name = "sp-replay-test-nobase"
        d = os.path.join(par.OUT, name, "records", f"{name}-1")
        os.makedirs(d, exist_ok=True)
        try:
            open(os.path.join(d, "records.fecap"), "wb").close()
            with open(os.path.join(d, "run.json"), "w") as fh:
                json.dump({"route": "title", "only": "0x100", "library_sha256": "0" * 64, "outcome": "Completed",
                           "exit_code": 0}, fh)
            import contextlib
            import io
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = offline.main(["plan", "--sessions", name, "--label", "play"])
            self.assertEqual(rc, 3, buf.getvalue())
            self.assertIn("cannot tell which targets.csv", buf.getvalue())
            self.assertIn("no build manifest of that library", buf.getvalue())
            self.assertIn("--baseline-rev", buf.getvalue())
        finally:
            par.rmtree_own(os.path.join(par.OUT, name))


if __name__ == "__main__":
    unittest.main(verbosity=1)
