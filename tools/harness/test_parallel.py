#!/usr/bin/env python3
"""Tests for tools/harness/parallel.py (docs/harness/PARALLEL.md).

    python tools/harness/test_parallel.py            # unit tests, fake child commands only (~1 minute)
    python tools/harness/test_parallel.py --smoke    # + one real check: title x3, determinism, side by
                                                      #   side vs one after another (about 1 minute)

The fake children are small Python scripts: they sleep, allocate memory, report their own priority
class and their grandchild's, and write their pids, so the pool's limits can be checked without the
game. Scratch: build/parallel/test-*/ (removed at the end).
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import parallel as par  # noqa: E402

TMP = os.path.join(par.OUT, "test-unit")
FAKE = os.path.join(TMP, "fake_child.py")
FAKE_CODE = r'''import ctypes, json, os, subprocess, sys, time
cfg = json.loads(sys.argv[1])
t0 = time.time()


def prio():
    if os.name != "nt":
        return None
    k = ctypes.WinDLL("kernel32")
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.GetPriorityClass.argtypes = [ctypes.c_void_p]
    return k.GetPriorityClass(k.GetCurrentProcess())


if cfg.get("role") == "prio":
    print(prio())
    sys.exit(0)
if cfg.get("role") == "sleeper":
    os.makedirs(cfg["pids"], exist_ok=True)
    open(os.path.join(cfg["pids"], str(os.getpid())), "w").close()
    time.sleep(120)
    sys.exit(0)
blob = []
for _ in range(cfg.get("alloc_mb", 0) // 10):
    blob.append(bytearray(10 << 20))
    time.sleep(cfg.get("alloc_pause", 0.0))
gprio = None
if cfg.get("grandchild_prio"):
    gprio = int(subprocess.run([sys.executable, __file__, json.dumps({"role": "prio"})],
                               capture_output=True, text=True).stdout.strip())
if cfg.get("pids"):  # one file per process (appends from several processes can lose lines)
    os.makedirs(cfg["pids"], exist_ok=True)
    open(os.path.join(cfg["pids"], str(os.getpid())), "w").close()
    if cfg.get("sleeper"):
        subprocess.Popen([sys.executable, __file__, json.dumps({"role": "sleeper", "pids": cfg["pids"]})])
time.sleep(cfg.get("sleep", 0))
if cfg.get("out"):
    with open(cfg["out"], "w") as fh:
        json.dump({"start": t0, "end": time.time(), "prio": prio(), "gprio": gprio, "pid": os.getpid()}, fh)
sys.exit(cfg.get("rc", 0))
'''


def quiet(*_a, **_k):
    pass


def lim(jobs=6, prio="below_normal", mem_gb=8.0) -> par.Limits:
    return par.Limits(jobs, prio, mem_gb)


def fake(name: str, timeout: float = 120, **cfg) -> par.Job:
    out = os.path.join(TMP, f"{name}.json")
    if os.path.exists(out):
        os.remove(out)
    cfg.setdefault("out", out)
    return par.Job(name, [sys.executable, FAKE, json.dumps(cfg)], cwd=TMP, log_file=os.path.join(TMP, f"{name}.log"),
                   result_file=cfg["out"], timeout=timeout)


def overlap(results: list[dict]) -> int:
    """Most fake children alive at the same moment, from their own start/end times."""
    ev = []
    for r in results:
        if r["result"]:
            ev += [(r["result"]["start"], 1), (r["result"]["end"], -1)]
    n = best = 0
    for _t, d in sorted(ev, key=lambda x: (x[0], x[1])):
        n += d
        best = max(best, n)
    return best


def read_pids(path: str) -> list[int]:
    try:
        return [int(x) for x in os.listdir(path) if x.isdigit()]
    except OSError:
        return []


def fresh_dir(path: str) -> str:
    if os.path.isdir(path):
        par.rmtree_own(path)
    return path


def wait_dead(pids: list[int], secs: float = 10) -> list[int]:
    end = time.time() + secs
    while time.time() < end:
        alive = [p for p in pids if par.pid_alive(p)]
        if not alive:
            return []
        time.sleep(0.2)
    return [p for p in pids if par.pid_alive(p)]


class PoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(TMP, exist_ok=True)
        with open(FAKE, "w", encoding="utf-8") as fh:
            fh.write(FAKE_CODE)

    @classmethod
    def tearDownClass(cls):
        par.rmtree_own(TMP)

    # -- budget
    def test_limits_from_resources_and_env(self):
        res = os.path.join(TMP, "resources.json")
        with open(res, "w") as fh:
            json.dump({"max_parallel_runs": 6, "priority": "below_normal", "max_total_memory_gb": 8,
                       "builds": {"parallel": 1, "priority": "below_normal"}}, fh)
        L = par.load_limits(res, env={})
        self.assertEqual((L.jobs, L.priority, L.mem_gb, L.build_jobs), (6, "below_normal", 8.0, 1))
        L = par.load_limits(res, env={"FEF_ROBOT_JOBS": "2", "FEF_ROBOT_PRIORITY": "idle", "FEF_ROBOT_MEM_GB": "3.5"})
        self.assertEqual((L.jobs, L.priority, L.mem_gb, L.build_priority), (2, "idle", 3.5, "idle"))
        L = par.load_limits(res, env={"FEF_ROBOT_JOBS": "0", "FEF_ROBOT_PRIORITY": "realtime", "FEF_ROBOT_MEM_GB": "x"})
        self.assertEqual((L.jobs, L.priority, L.mem_gb), (6, "below_normal", 8.0), "bad overrides are ignored")
        self.assertEqual(len(L.notes), 3)
        self.assertEqual(par.load_limits(res, env={}, cli_jobs=3).jobs, 3, "--jobs lowers")
        self.assertEqual(par.load_limits(res, env={"FEF_ROBOT_JOBS": "2"}, cli_jobs=5).jobs, 2, "--jobs never raises")
        self.assertEqual(par.load_limits(os.path.join(TMP, "none.json"), env={}).jobs, 1, "no file: 1 run")
        real = par.load_limits(env={})
        self.assertLessEqual(real.jobs, 6)

    # -- concurrency
    def test_concurrency_cap_is_honoured(self):
        pool = par.Pool(lim(jobs=2), mem_per_run_gb=0.05, reserve_gb=0, say=quiet, tick=0.05, adapt=False)
        t = time.time()
        res = pool.run([fake(f"cc{i}", sleep=0.8) for i in range(6)])
        self.assertEqual(len(res), 6)
        self.assertTrue(all(r["exit_code"] == 0 for r in res))
        self.assertEqual(pool.max_running, 2)
        self.assertLessEqual(overlap(res), 2)
        self.assertGreaterEqual(time.time() - t, 3 * 0.8, "three waves of two")
        self.assertGreater(pool.waits["jobs"], 0)

    # -- priority
    @unittest.skipUnless(par.WIN, "Windows priority classes")
    def test_priority_class_on_child_and_grandchild(self):
        for name, cls in (("below_normal", 0x4000), ("idle", 0x40)):
            pool = par.Pool(lim(prio=name), mem_per_run_gb=0.05, reserve_gb=0, say=quiet, tick=0.05)
            self.assertTrue(pool.creationflags() & par.PRIORITY[name])
            self.assertTrue(pool.creationflags() & par.CREATE_NO_WINDOW)
            r = pool.run([fake(f"pr-{name}", grandchild_prio=True)])[0]
            self.assertEqual(r["result"]["prio"], cls, f"{name}: the child")
            self.assertEqual(r["result"]["gprio"], cls, f"{name}: its own child (boot.exe's place)")

    @unittest.skipUnless(par.WIN, "Windows priority classes")
    def test_priority_seen_from_outside(self):
        pids = fresh_dir(os.path.join(TMP, "prio-pids"))
        seen = {}

        def tick(pool):
            for p in read_pids(pids):
                seen.setdefault(p, par.priority_of(p))

        par.Pool(lim(), mem_per_run_gb=0.05, reserve_gb=0, say=quiet, tick=0.05,
                 on_tick=tick).run([fake("pr-out", pids=pids, sleep=1.0)])
        self.assertTrue(seen and all(v == 0x4000 for v in seen.values()), seen)

    # -- memory
    @unittest.skipUnless(par.WIN, "job-object memory accounting")
    def test_peak_memory_is_measured(self):
        r = par.Pool(lim(), mem_per_run_gb=0.05, reserve_gb=0, say=quiet, tick=0.05).run(
            [fake("mem60", alloc_mb=60, sleep=0.3)])[0]
        self.assertEqual(r["exit_code"], 0)
        self.assertGreaterEqual(r["peak_mem_mb"], 60)
        self.assertLess(r["peak_mem_mb"], 400)

    @unittest.skipUnless(par.WIN, "job-object memory accounting")
    def test_memory_cap_stops_a_run(self):
        pool = par.Pool(lim(), mem_per_run_gb=0.05, run_cap_gb=0.15, reserve_gb=0, say=quiet, tick=0.05)
        r = pool.run([fake("memcap", alloc_mb=600, alloc_pause=0.1, sleep=5)])[0]
        self.assertEqual(r["killed"], "memory cap")
        self.assertNotEqual(r["exit_code"], 0)
        self.assertGreaterEqual(r["peak_mem_mb"], 140)
        self.assertTrue(any("memcap: stopped" in e for e in pool.events))

    @unittest.skipUnless(par.WIN, "job objects")
    def test_hard_ceiling_of_the_job_object(self):
        tree = par.TreeJob("hard", "below_normal", 100 * par.MB)
        p = subprocess.Popen([sys.executable, FAKE, json.dumps({"alloc_mb": 300})], stdin=subprocess.PIPE,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=par.CREATE_NO_WINDOW | par.PRIORITY["below_normal"])
        self.assertTrue(tree.assign(p), tree.note)
        p.stdin.close()
        rc = p.wait(60)
        peak = tree.peak()
        tree.close()
        self.assertNotEqual(rc, 0, "the allocation past the ceiling fails")
        # the ceiling holds new commits; what Python committed before it joined the job counts on top
        self.assertLessEqual(peak, 100 * par.MB + 40 * par.MB)

    def test_memory_budget_limits_how_many_start(self):
        pool = par.Pool(lim(jobs=6, mem_gb=0.5), mem_per_run_gb=0.2, reserve_gb=0, say=quiet, tick=0.05,
                        free_mem=lambda: 64 * par.GB, adapt=False)
        res = pool.run([fake(f"mb{i}", sleep=0.6) for i in range(5)])
        self.assertTrue(all(r["exit_code"] == 0 for r in res))
        self.assertEqual(pool.max_running, 2, "0.5 GB / 0.2 GB a run")
        self.assertGreater(pool.waits["budget"], 0)

    def test_free_memory_limits_how_many_start(self):
        pool = par.Pool(lim(jobs=6, mem_gb=8), mem_per_run_gb=0.2, reserve_gb=0.2, say=quiet, tick=0.05,
                        free_mem=lambda: int(0.3 * par.GB), adapt=False)
        res = pool.run([fake(f"fm{i}", sleep=0.4) for i in range(3)])
        self.assertEqual(len(res), 3)
        self.assertEqual(pool.max_running, 1, "one always runs; a second would eat the reserve")
        self.assertGreater(pool.waits["free_memory"], 0)

    @unittest.skipUnless(par.WIN, "job-object memory accounting")
    def test_estimate_adapts_to_measured_peaks(self):
        pool = par.Pool(lim(jobs=6, mem_gb=0.65), mem_per_run_gb=0.3, reserve_gb=0, say=quiet, tick=0.05,
                        free_mem=lambda: 64 * par.GB)
        res = pool.run([fake(f"ad{i}", sleep=0.6) for i in range(10)])
        self.assertTrue(all(r["exit_code"] == 0 for r in res))
        self.assertLess(pool.est, int(0.3 * par.GB), "small real peaks lower the estimate")
        self.assertGreater(pool.max_running, 2, "so more runs fit than the first estimate allowed")

    @unittest.skipUnless(par.WIN, "job-object memory accounting")
    def test_over_budget_run_is_requeued(self):
        pool = par.Pool(lim(jobs=4, mem_gb=0.3), mem_per_run_gb=0.01, reserve_gb=0, say=quiet, tick=0.05,
                        free_mem=lambda: 64 * par.GB, adapt=False)
        res = pool.run([fake(f"rq{i}", alloc_mb=120, sleep=1.5) for i in range(4)])
        self.assertEqual(len(res), 4)
        self.assertTrue(all(r["exit_code"] == 0 and not r["killed"] for r in res), res)
        self.assertTrue(any(r["requeued"] for r in res))
        self.assertTrue(any("requeued" in e for e in pool.events))

    # -- results, timeout
    def test_results_are_collected(self):
        res = par.Pool(lim(), mem_per_run_gb=0.05, reserve_gb=0, say=quiet, tick=0.05).run(
            [fake("ok", rc=0), fake("fail", rc=1), fake("setup", rc=3)])
        by = {r["name"]: r for r in res}
        self.assertEqual({k: v["exit_code"] for k, v in by.items()}, {"ok": 0, "fail": 1, "setup": 3})
        for r in res:
            self.assertIsInstance(r["result"], dict)
            self.assertIn("pid", r["result"])
            self.assertGreater(r["wall_seconds"], 0)
            self.assertIsNone(r["killed"])

    def test_timeout_kills(self):
        t = time.time()
        r = par.Pool(lim(), mem_per_run_gb=0.05, reserve_gb=0, say=quiet, tick=0.05).run(
            [fake("slow", sleep=30, timeout=1.0)])[0]
        self.assertEqual(r["killed"], "timeout")
        self.assertLess(time.time() - t, 10)

    # -- Ctrl-C
    def test_interrupt_kills_children_and_grandchildren(self):
        pids = fresh_dir(os.path.join(TMP, "int-pids"))

        def tick(pool):
            if len(read_pids(pids)) >= 6:
                raise KeyboardInterrupt

        pool = par.Pool(lim(jobs=3), mem_per_run_gb=0.05, reserve_gb=0, say=quiet, tick=0.05, on_tick=tick)
        with self.assertRaises(KeyboardInterrupt):
            pool.run([fake(f"int{i}", pids=pids, sleeper=True, sleep=60) for i in range(3)])
        got = read_pids(pids)
        self.assertGreaterEqual(len(got), 6)
        self.assertEqual(wait_dead(got), [], "every child and grandchild is gone")
        self.assertEqual(pool.running, {})

    def test_run_timeout_scales_with_route_and_load(self):
        """Round 9: the default timeout grows with frames and with runs above 6; --timeout wins."""
        short, long_ = {"frames": 3000}, {"frames": 141000}
        self.assertEqual(par.run_timeout(short, "capture", 12), 900.0, "floor")
        self.assertEqual(par.run_timeout(long_, "capture", 6), 120 + 141000 * 0.012)
        self.assertEqual(par.run_timeout(long_, "capture", 12), 120 + 141000 * 0.012 * 2)
        self.assertEqual(par.run_timeout(long_, "capture", 3), par.run_timeout(long_, "capture", 6), "no cut below 6")
        self.assertLess(par.run_timeout(long_, "original", 6), par.run_timeout(long_, "capture", 6))
        self.assertGreater(par.run_timeout({"frames": 78900}, "capture", 12), 900, "round 8's bt-ch8 at 12 runs")
        self.assertEqual(par.run_timeout({"frames": 10 ** 8}, "capture", 12), 4 * 3600.0, "cap")
        self.assertEqual(par.run_timeout(long_, "capture", 12, given=900), 900.0, "--timeout wins")
        self.assertEqual(par.run_timeout({}, "capture", 12), 900.0, "no frames: the floor")

    @unittest.skipUnless(par.WIN, "Ctrl-Break to a process group")
    def test_ctrl_break_on_the_command_line(self):
        pids = fresh_dir(os.path.join(TMP, "brk-pids"))
        sdir = os.path.join(par.OUT, "test-break")
        p = subprocess.Popen([sys.executable, par.SELF, "_fake", "--copies", "3", "--sleep", "60", "--pids", pids,
                              "--session", "test-break", "--jobs", "3"], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True,
                             creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        # round 9: robust under load (12 robot runs beside the tests): generous start and stop waits, and the
        # break sent again if the first one did not arrive (a console event can be lost while the parent starts)
        end = time.time() + 180
        while len(read_pids(pids)) < 6 and time.time() < end and p.poll() is None:
            time.sleep(0.2)
        got = read_pids(pids)
        if len(got) < 6:
            p.kill()
            out, _ = p.communicate(timeout=60)
            self.fail(f"3 children + 3 grandchildren started: only {len(got)} in 180 s; output:\n{out}")
        self.assertTrue(os.path.isdir(sdir))
        out = None
        for wait in (60, 120):
            os.kill(p.pid, signal.CTRL_BREAK_EVENT)
            try:
                out, _ = p.communicate(timeout=wait)
                break
            except subprocess.TimeoutExpired:
                continue
        if out is None:
            p.kill()
            out, _ = p.communicate(timeout=60)
            self.fail(f"no exit within 180 s of Ctrl-Break; output:\n{out}")
        self.assertEqual(p.returncode, 130, out)
        self.assertEqual(wait_dead(got, secs=60), [], "every child and grandchild is gone")
        self.assertFalse(os.path.exists(sdir), "its scratch folder is removed")

    # -- builds
    @unittest.skipUnless(par.WIN, "Windows priority classes")
    def test_builds_one_at_a_time_below_normal(self):
        lock = os.path.join(TMP, "build.lock")
        outs = [os.path.join(TMP, f"build{i}.json") for i in range(2)]
        rcs = []

        def go(i):
            cmd = [sys.executable, FAKE, json.dumps({"out": outs[i], "sleep": 1.0, "grandchild_prio": True})]
            rcs.append(par.run_build([], lim(), cmd=cmd, say=quiet, lock=lock,
                                     log=os.path.join(TMP, f"build{i}.log")))

        th = [threading.Thread(target=go, args=(i,)) for i in range(2)]
        for t in th:
            t.start()
        for t in th:
            t.join(60)
        self.assertEqual(rcs, [0, 0])
        a, b = (json.load(open(o)) for o in outs)
        self.assertTrue(a["end"] <= b["start"] or b["end"] <= a["start"], "the two builds did not overlap")
        self.assertEqual((a["prio"], a["gprio"]), (0x4000, 0x4000))
        self.assertFalse(os.path.exists(lock))

    def test_stale_build_lock_is_taken_over(self):
        lock = os.path.join(TMP, "stale.lock")
        for left in ("999999", ""):  # a dead holder's pid, or an empty file: not locked by anyone, so free
            with open(lock, "w") as fh:
                fh.write(left)
            held = par.acquire_build_lock(lock, say=quiet, wait=5)
            self.assertEqual(open(lock).read(), str(os.getpid()))
            held.release()
            self.assertFalse(os.path.exists(lock))


class PartsTests(unittest.TestCase):
    def test_determinism_verdict_uses_h4a_comparison(self):
        hl = par.headless_module()
        mem = [bytes([k]) * (64 + k) for k in range(4)]
        names = ["<p>/jobs/d-1/data/d-1", "<p>/jobs/d-22/data/d-22"]
        sa = hl.fake_state(b"\x02FS\x05Mutex\x0e" + names[0].encode() + b"/user", mem)
        sb = hl.fake_state(b"\x05Mutex\x02FS\x10" + names[1].encode() + b"/user", mem)  # map order, longer name
        da, db = hl.state_digest(sa, [names[0]]), hl.state_digest(sb, [names[1]])
        ma = hl.strip_meta(hl.state_sections(sa)[1][0], [names[0]])
        mb = hl.strip_meta(hl.state_sections(sb)[1][0], [names[1]])
        rows = [{"run": "d-1", "instructions": 100}, {"run": "d-22", "instructions": 100},
                {"run": "d-3", "instructions": 100}]
        v = par.determinism_verdict(rows, [da, db, da], [ma, mb, ma])
        self.assertEqual(v["verdict"], "DETERMINISTIC", v)
        self.assertIn("reordered in pieces", v["pairs"][0]["line"])
        changed = list(mem)
        changed[1] = b"\x99" + mem[1][1:]
        dc = hl.state_digest(hl.fake_state(b"\x02FS\x05Mutex\x0e" + names[0].encode() + b"/user", changed), [names[0]])
        v = par.determinism_verdict(rows, [da, db, dc], [ma, mb, ma])
        self.assertEqual(v["verdict"], "DIVERGED")
        self.assertIn("DIFFERS (vram)", v["pairs"][1]["line"])
        rows[2]["instructions"] = 101
        v = par.determinism_verdict(rows, [da, db, da], [ma, mb, ma])
        self.assertEqual(v["verdict"], "DIVERGED", "another instruction count diverges, as in h4a")
        self.assertEqual(par.determinism_verdict(rows[:1], [da], [ma])["verdict"], "NOT CHECKED")

    def test_search_ranking(self):
        mk = lambda cur, classes=(): {"current": cur, "classes": list(classes)}  # noqa: E731
        sets = [{"4400": mk("A"), "4600": mk("Target")},
                {"4400": mk("B", ["Target"]), "4600": mk("Target")},
                {"4400": mk("A"), "4600": None},
                {"4400": mk("Target")}]
        rows = [{"run": "r1", "variant": "slow", "ok": True, "inputs_count": 9},
                {"run": "r2", "variant": "live", "ok": True, "inputs_count": 9},
                {"run": "r3", "variant": "never", "ok": True, "inputs_count": 9},
                {"run": "r4", "variant": "failed", "ok": False, "inputs_count": 1}]
        ranked = par.rank_search(rows, sets, "Target", current_only=False)
        self.assertEqual([x["variant"] for x in ranked], ["live", "slow", "never", "failed"])
        self.assertEqual(ranked[0]["first_frame"], 4400)
        ranked = par.rank_search(rows, sets, "Target", current_only=True)
        self.assertEqual(ranked[0]["first_frame"], 4600)
        self.assertIsNone(par.first_hit(None, "Target"))

    def test_variants(self):
        class A:
            variant = ["a=+4300:A", "b=4300:B", "5000:X,5100:Y"]
            variants = None
        base = {"input": "400:A,800:A"}
        self.assertEqual(par.parse_variants(A, base),
                         [("a", "400:A,800:A,4300:A"), ("b", "4300:B"), ("v3", "5000:X,5100:Y")])
        A.variant = ["a=1:A", "a=2:A"]
        with self.assertRaises(par.Stop):
            par.parse_variants(A, base)
        A.variant = ["../x=1:A"]
        with self.assertRaises(par.Stop):
            par.parse_variants(A, base)

    def test_appdata_snapshot_sees_a_change(self):
        d = os.path.join(TMP, "appdata-probe")
        os.makedirs(os.path.join(d, "sub"), exist_ok=True)
        f = os.path.join(d, "sub", "file.bin")
        with open(f, "wb") as fh:
            fh.write(b"1")
        before = par.snapshot([d, os.path.join(TMP, "absent")])
        self.assertEqual(par.snapshot_diff(before, par.snapshot([d, os.path.join(TMP, "absent")])), [])
        t = time.time() + 5
        os.utime(f, (t, t))
        self.assertIn(f, par.snapshot_diff(before, par.snapshot([d, os.path.join(TMP, "absent")])))
        os.makedirs(os.path.join(TMP, "absent"))
        self.assertIn(os.path.join(TMP, "absent"),
                      par.snapshot_diff(before, par.snapshot([d, os.path.join(TMP, "absent")])))
        par.rmtree_own(os.path.join(TMP, "absent"))
        self.assertEqual(sorted(par.appdata_dirs()) and [os.path.basename(x) for x in par.appdata_dirs()],
                         ["zakuro", "3dsrecomp"])

    def test_own_scratch_only(self):
        for bad in (par.HARNESS_BUILD, os.path.join(par.HARNESS_BUILD, "runs"), par.OUT,
                    os.path.join(par.OUT, "..", "harness")):
            with self.assertRaises(par.Stop):
                par.rmtree_own(bad)

    def test_job_folders_are_below_build_parallel(self):
        try:
            sess = par.Session("test-layout", "new-game-empty", say=quiet)
        except par.Stop as e:
            self.skipTest(f"no start save: {e}")
        os.makedirs(os.path.join(sess.dir, "jobs"), exist_ok=True)
        sess.boot, sess.lib = os.path.join(sess.dir, "bin", "boot.exe"), os.path.join(sess.dir, "lib", "x.dll")
        try:
            job = sess.job("test-layout-1", "title", sess.routes["title"])
            spec = json.load(open(job.cmd[-1]))
            for k in ("root", "routes", "save", "result", "boot", "lib"):
                self.assertTrue(par.below(spec[k], par.OUT), f"{k}: {spec[k]}")
                self.assertFalse(par.below(spec[k], par.HARNESS_BUILD), f"{k}: {spec[k]}")
            self.assertTrue(par.below(job.env["APPDATA"], par.OUT), "the child's APPDATA is its own folder")
            self.assertEqual(job.cmd[1:3], [par.SELF, "--worker"])
            with self.assertRaises(par.Stop):  # headless's own route rules apply before anything runs
                sess.job("test-layout-2", "title", dict(sess.routes["title"], save_at=99999))
        finally:
            par.rmtree_own(sess.dir)


    def test_route_save_is_used_without_save_arg(self):
        """A route's own "save" (bt-* routes) is its start save unless --save is given (round 3 fix:
        the default new-game-empty used to override it, so bt-* runs started from an empty save)."""
        try:
            sess = par.Session("test-save", None, say=quiet)
            forced = par.Session("test-save-f", "new-game-empty", say=quiet)
        except par.Stop as e:
            self.skipTest(f"no start save: {e}")
        named = next((n for n, r in sess.routes.items() if r.get("save")), None)
        if named is None:
            self.skipTest("no route names a save")
        try:
            for s_ in (sess, forced):
                os.makedirs(os.path.join(s_.dir, "jobs"), exist_ok=True)
                s_.boot, s_.lib = os.path.join(s_.dir, "bin", "boot.exe"), os.path.join(s_.dir, "lib", "x.dll")
            spec = json.load(open(sess.job("test-save-1", named, sess.routes[named]).cmd[-1]))
            self.assertEqual(os.path.basename(spec["save"]), sess.routes[named]["save"] + ".zip")
            spec = json.load(open(sess.job("test-save-2", "title", sess.routes["title"]).cmd[-1]))
            self.assertEqual(os.path.basename(spec["save"]), par.DEFAULT_SAVE + ".zip")
            spec = json.load(open(forced.job("test-save-f-1", named, forced.routes[named]).cmd[-1]))
            self.assertEqual(os.path.basename(spec["save"]), "new-game-empty.zip", "--save wins")
        finally:
            par.rmtree_own(sess.dir)
            par.rmtree_own(forced.dir)


SUMMARY_HEAD = ("address\tkind\tverdict\tcalls\trecords\tmatch\tmismatch_r0\tmismatch_mem\tmismatch_calls\tgave_up\t"
                "b_escaped\tfaithful\tunfaithful\tincomplete\tescaped\thostmem\ttruncated\tcold\twarm\tdeep\tkept\tpaths\t"
                "signatures\n")


def writers_line(**counts) -> str:
    """capture.c's "# writers:" line (src/readable/core/fe_writer.h FE_WT_* order), every count 0 unless given."""
    return "# writers:" + ";".join(f" {k} {counts.get(k, 0)}" for k in par.WRITER_KEYS) + "\n"


def summary_tsv(path: str, rows: list[dict], writers: str | None = None) -> None:
    """A summary.tsv in capture.c's layout (two comment lines, the writers line when given, the header, one row per
    function)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cols = SUMMARY_HEAD.rstrip("\n").split("\t")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# fe-capture summary (test)\n# verdict = this session only\n" + (writers or "") + SUMMARY_HEAD)
        for r in rows:
            fh.write("\t".join(str(r.get(c, 0)) for c in cols) + "\n")


class StoreKeepTests(unittest.TestCase):
    """Round 7: `runs --mode capture --only ... --store-keep` keeps game records for h56.py (H5/H6)."""

    def test_only_addresses(self):
        every = par.only_addresses("all").split(",")
        self.assertGreater(len(every), 50)
        self.assertTrue(all(len(x) == 10 and x.startswith("0x") and int(x, 16) % 2 == 0 for x in every))
        self.assertIn("0x003BA88C", every)  # config_item_value
        self.assertEqual(par.only_addresses("config_item_value,0x003bc358"), "0x003BA88C,0x003BC358")
        self.assertIsNone(par.only_addresses(None))
        with self.assertRaises(par.Stop):
            par.only_addresses("not_a_reader")
        with self.assertRaises(par.Stop):
            par.only_addresses("0x00100000")

    def test_store_keep_needs_capture_and_only(self):
        for argv in (["runs", "--route", "title", "--store-keep"],
                     ["runs", "--route", "title", "--mode", "capture", "--store-keep"],
                     ["runs", "--route", "title", "--only", "all"]):
            self.assertEqual(par.main(argv + ["--session", "test-storekeep"]), 3, argv)
        self.assertFalse(os.path.isdir(os.path.join(par.OUT, "test-storekeep", "jobs")))


class CaptureVerdictTests(unittest.TestCase):
    """Round 6 (review round 5, MAJOR): a capture run with mismatch records in summary.tsv printed PASS (a planted
    unit_has_skill returning 2 gave 52 mismatch_r0 records; the boot.log had no MISMATCH line)."""

    def test_summary_is_read_and_bad_kinds_counted(self):
        path = os.path.join(TMP, "cap", "summary.tsv")
        os.makedirs(TMP, exist_ok=True)
        summary_tsv(path, [{"address": "0x0052DD05", "kind": "override", "verdict": "MISMATCH", "calls": 70,
                            "records": 70, "match": 18, "mismatch_r0": 52, "signatures": ""},
                           {"address": "0x00175900", "kind": "override", "verdict": "PARTIAL", "calls": 9,
                            "records": 9, "match": 8, "gave_up": 1, "signatures": ""},
                           {"address": "0x00175904", "kind": "override", "verdict": "SHALLOW", "calls": 3,
                            "records": 0, "signatures": ""}])
        one = par.read_capture_summary(path)
        self.assertEqual((one["functions"], one["records"], one["match"], one["mismatch_r0"], one["gave_up"], one["bad"]),
                         (2, 79, 26, 52, 1, 52))
        self.assertEqual(one["bad_functions"], ["0x0052DD05"])
        for kind in ("mismatch_mem", "mismatch_calls", "b_escaped", "unfaithful", "escaped"):
            summary_tsv(path, [{"address": "0x1", "kind": "override", "records": 2, "match": 1, kind: 1,
                                "signatures": ""}])
            cap = par.capture_totals([path])
            self.assertEqual(cap["bad"], 1, kind)
            self.assertIn(f"1 {kind}", par.capture_problem(cap))
        self.assertEqual(par.capture_problem(par.capture_totals([])), "no summary.tsv (capture wrote nothing)")
        summary_tsv(path, [{"address": "0x1", "kind": "override", "records": 5, "match": 4, "gave_up": 1,
                            "incomplete": 0, "signatures": ""}])
        self.assertIsNone(par.capture_problem(par.capture_totals([path])))

    def test_writer_totals_are_read(self):
        """Round 8: capture.c writes the writer gate's run totals into summary.tsv ("# writers: ..."), so "no writer
        stored anything" is read from the run itself; a store in a capture run fails it; no line (an older library)
        is reported as not reported, never as clean."""
        path = os.path.join(TMP, "capw", "summary.tsv")
        row = [{"address": "0x1", "kind": "override", "records": 5, "match": 5, "signatures": ""}]
        summary_tsv(path, row, writers_line(refusals=3, mode_refusals=3))
        cap = par.capture_totals([path])
        self.assertEqual(cap["writers"]["refusals"], 3)
        self.assertEqual(cap["writers"]["stores"], 0)
        self.assertIsNone(par.capture_problem(cap), "refusals only: clean")
        t = par.writers_total([{"capture": cap}])
        self.assertEqual(t["verdict"], "no writer stored anything")
        self.assertIn("no writer stored anything", par.writers_line(t))
        for k in ("stores", "log", "sessions"):  # planted: a writer that stored in a capture run
            summary_tsv(path, row, writers_line(**{k: 1}))
            cap = par.capture_totals([path])
            self.assertIn("writer gate stored", par.capture_problem(cap) or "", k)
            self.assertEqual(par.writers_total([{"capture": cap}])["verdict"], "WRITER STORED", k)
        summary_tsv(path, row)  # no line: an older library
        cap = par.capture_totals([path])
        self.assertIsNone(cap["writers"])
        self.assertIsNone(par.capture_problem(cap))
        self.assertTrue(par.writers_total([{"capture": cap}])["verdict"].startswith("NOT REPORTED"))
        # two stages of a cheat run: the totals add
        p2 = os.path.join(TMP, "capw", "stage0", "summary.tsv")
        summary_tsv(path, row, writers_line(refusals=2))
        summary_tsv(p2, row, writers_line(refusals=5, stray=1))
        cap = par.capture_totals([path, p2])
        self.assertEqual((cap["writers"]["refusals"], cap["writers"]["stray"]), (7, 1))
        # a damaged line is not taken for totals
        self.assertIsNone(par.parse_writers_line("# writers: log x; stores 0"))
        self.assertIsNone(par.parse_writers_line("# writers: log 0"))

    def test_capture_runs_with_a_mismatch_fail_and_are_totalled(self):
        """End to end through execute(): three finished capture runs (child exit 0, a savestate), one clean, one
        with a planted summary.tsv of 52 mismatch_r0 records, one a cheat route split in two stages (two
        summary.tsv files). The planted run FAILs, the session exits 1, the CAPTURE FAIL line names it, and the
        totals table counts the cheat run apart."""
        try:
            sess = par.Session("test-capture", None, say=quiet)
        except par.Stop as e:
            self.skipTest(str(e))
        said: list[str] = []
        sess.say = said.append
        try:
            for d in ("jobs", "results", "shots", "logs"):
                os.makedirs(os.path.join(sess.dir, d), exist_ok=True)
            os.makedirs(TMP, exist_ok=True)
            with open(FAKE, "w", encoding="utf-8") as fh:
                fh.write(FAKE_CODE)
            jobs = []
            plan = {"clean": ([{"address": "0x00532DC5", "records": 40, "match": 39, "gave_up": 1}], False),
                    "planted": ([{"address": "0x0052DD05", "records": 70, "match": 18, "mismatch_r0": 52}], False),
                    "cheat": ([{"address": "0x0052DD05", "records": 5, "match": 5}], True)}
            for name, (srows, cheat) in plan.items():
                run = f"test-capture-{name}"
                root = os.path.join(sess.dir, "jobs", run)
                for r in srows:
                    r.update(kind="override", verdict="x", calls=r["records"], signatures="")
                summary_tsv(os.path.join(root, "runs", run, "summary.tsv"), srows, writers_line(refusals=1))
                if cheat:  # the stage before the poke keeps its own summary.tsv
                    summary_tsv(os.path.join(root, "runs", run, "stage0", "summary.tsv"),
                                [{"address": "0x00532DC5", "kind": "override", "records": 3, "match": 3,
                                  "signatures": ""}])
                result = os.path.join(root, "result.json")
                with open(result, "w", encoding="utf-8") as fh:
                    json.dump({"run_json": {"exit_code": 0, "outcome": "Completed", "state": {"memory": "ab" * 32}}}, fh)
                jobs.append(par.Job(run, [sys.executable, FAKE, json.dumps({})], cwd=root, result_file=result,
                                    log_file=os.path.join(root, "worker.log"),
                                    info={"route": "bt-x" if not cheat else "cheat-x", "mode": "capture",
                                          "cheat": cheat}))
            a = type("A", (), {"command": "runs", "mem_per_run_gb": 0.05, "reserve_gb": 0})()
            summary, rc = par.execute(sess, jobs, lim(), a)
            self.assertEqual(rc, 1, "a mismatch record fails the session")
            ok = {r["run"].rsplit("-", 1)[1]: r["ok"] for r in summary["runs"]}
            self.assertEqual(ok, {"clean": True, "planted": False, "cheat": True})
            honest, cheat = summary["capture_totals"]["honest"], summary["capture_totals"]["cheat"]
            self.assertEqual((honest["records"], honest["mismatch_r0"], honest["verdict"]), (110, 52, "FAIL"))
            self.assertEqual((cheat["records"], cheat["match"], cheat["runs"], cheat["verdict"]), (8, 8, 1, "PASS"))
            self.assertEqual(summary["cheat_runs"], ["test-capture-cheat"])
            self.assertEqual(summary["writers"]["verdict"], "no writer stored anything", summary["writers"])
            self.assertEqual((summary["writers"]["reported_runs"], summary["writers"]["refusals"]), (3, 3))
            self.assertTrue(any("writers: no writer stored anything" in x for x in said), said)
            cheat_row = next(r for r in summary["runs"] if r["cheat"])
            self.assertEqual((cheat_row["capture"]["functions"], cheat_row["capture"]["summary_files"]), (2, 2),
                             "a function is counted once over the stages' summary files")
            self.assertTrue(any("CAPTURE FAIL test-capture-planted" in x and "52 mismatch_r0" in x for x in said),
                            said)
            self.assertTrue(any("CHEAT runs" in x for x in said))
            self.assertTrue(os.path.isfile(os.path.join(sess.dir, "results", "test-capture-planted.summary.tsv")),
                            "the summary.tsv is kept with the results (job folders are deleted)")
        finally:
            par.rmtree_own(sess.dir)


class LockTests(unittest.TestCase):
    """Round 6 (review round 5): the look-ahead lock (robot/budget.py) and the build lock used O_CREAT|O_EXCL and
    then wrote the pid; a waiter that read the file in between saw it empty, took it for a dead holder's, removed
    it and ran too. Both now use parallel.OsLock (held by the OS, freed when the holder dies)."""

    CHILD = r"""import json, os, sys, time
sys.path.insert(0, sys.argv[1])
import budget
budget.LOCK = sys.argv[2]
with budget.run_slot(wait=60):
    t0 = time.time()
    if len(sys.argv) > 5:
        open(sys.argv[5], "w").close()  # "I hold it now"
    time.sleep(float(sys.argv[4]))
    t1 = time.time()
with open(sys.argv[3], "w") as fh:
    json.dump({"start": t0, "end": t1, "pid": os.getpid()}, fh)
"""

    WAITER = r"""import sys
sys.path.insert(0, sys.argv[1])
import budget
budget.LOCK = sys.argv[2]
with budget.run_slot(wait=1.0):
    print("TOOK IT")
"""

    def setUp(self):
        self.dir = fresh_dir(os.path.join(TMP, "locks"))
        os.makedirs(self.dir, exist_ok=True)
        self.child = os.path.join(self.dir, "child.py")
        with open(self.child, "w", encoding="utf-8") as fh:
            fh.write(self.CHILD)
        self.robot = os.path.join(HERE, "robot")
        self.lock = os.path.join(self.dir, "probe.lock")

    def tearDown(self):
        par.rmtree_own(self.dir)

    def spawn(self, out: str, secs: float, flag: str | None = None) -> subprocess.Popen:
        return subprocess.Popen([sys.executable, self.child, self.robot, self.lock, out, str(secs)]
                                + ([flag] if flag else []))

    def test_empty_lock_file_is_not_a_dead_holder(self):
        """The old race: the holder's lock file is empty (between its creation and its pid write). A waiter must
        not take the lock then."""
        flag = os.path.join(self.dir, "held")
        p = self.spawn(os.path.join(self.dir, "a.json"), 4.0, flag)
        t0 = time.time()
        while not os.path.exists(flag) and time.time() - t0 < 30:
            time.sleep(0.05)
        self.assertTrue(os.path.exists(flag), "the child took the lock")
        with open(self.lock, "r+b") as fh:  # the window of the old code: an empty lock file
            fh.truncate(0)
        other = par.OsLock(self.lock)
        self.assertFalse(other.try_acquire(), "an empty lock file while the holder lives is still held")
        # and budget.run_slot itself, in a second process, waits instead of taking it (the old code removed the
        # empty file as a dead holder's and ran beside the holder)
        waiter = subprocess.run([sys.executable, "-c", self.WAITER, self.robot, self.lock], capture_output=True,
                                text=True, timeout=60)
        self.assertIn("held by pid", waiter.stdout + waiter.stderr, waiter.stdout + waiter.stderr)
        self.assertNotIn("TOOK IT", waiter.stdout)
        p.wait(30)
        self.assertTrue(other.try_acquire(), "free once the holder is gone")
        other.release()

    def test_look_aheads_never_overlap(self):
        open(self.lock, "w").close()  # an empty file left from before: free, not a reason to wait or to share
        outs = [os.path.join(self.dir, f"r{i}.json") for i in range(4)]
        procs = [self.spawn(o, 0.4) for o in outs]
        for p in procs:
            self.assertEqual(p.wait(60), 0)
        spans = []
        for o in outs:
            with open(o, encoding="utf-8") as fh:
                d = json.load(fh)
            spans.append((d["start"], d["end"]))
        spans.sort()
        for (s0, e0), (s1, e1) in zip(spans, spans[1:]):
            self.assertLessEqual(e0, s1, f"two look-aheads overlapped: {spans}")
        self.assertFalse(os.path.exists(self.lock), "the last holder removes the lock file")

    def test_a_killed_holder_frees_the_lock(self):
        flag = os.path.join(self.dir, "held")
        p = self.spawn(os.path.join(self.dir, "k.json"), 60.0, flag)
        t0 = time.time()
        while not os.path.exists(flag) and time.time() - t0 < 30:
            time.sleep(0.05)
        other = par.OsLock(self.lock)
        self.assertFalse(other.try_acquire())
        self.assertEqual(other.holder(), p.pid, "the holder's pid is readable while it holds the lock")
        p.kill()
        p.wait(30)
        self.assertTrue(other.try_acquire(), "the OS freed the dead holder's lock (no stale file to take over)")
        other.release()


class LaunderTests(unittest.TestCase):
    """Review round 6 (major): `runs --route title --save cheat-castle-katana` ran as real play and its save packed
    under a plain name, so cheat state could start a bt-* route. A cheat save is now known by its name, by the mark
    pack_save writes into it, or by its save files; it never starts a real-play run, and a run that started from one
    packs only as cheat-*."""

    def setUp(self):
        import shutil
        import zipfile
        self.hl = hl = par.headless_module()
        self.d = os.path.join(hl.BUILD, "test-launder")  # below build/harness/: find_backup accepts it
        shutil.rmtree(self.d, ignore_errors=True)
        os.makedirs(self.d)
        self.old_saves, hl.SAVES = hl.SAVES, self.d
        chap = f"savedata/{hl.TITLE}/Chapter0"

        def zp(name, data, mark=False):
            path = os.path.join(self.d, name)
            with zipfile.ZipFile(path, "w") as z:
                z.writestr(chap, data)
                if mark:
                    z.writestr(hl.CHEAT_MARK, '{"cheat": true}')
            return path
        self.honest = zp("honest.zip", b"real play")
        self.cheat = zp("cheat-k.zip", b"one pearl poked", mark=True)
        self.copy = os.path.join(self.d, "k-copy.zip")
        shutil.copy2(self.cheat, self.copy)
        self.strip = zp("k-strip.zip", b"one pearl poked")  # repacked without the mark
        self.oldname = zp("cheat-old.zip", b"packed before the mark")  # round-6 saves have no mark
        self.oldcopy = zp("old-copy.zip", b"packed before the mark")

    def tearDown(self):
        import shutil
        self.hl.SAVES = self.old_saves
        shutil.rmtree(self.d, ignore_errors=True)
        shutil.rmtree(os.path.join(par.OUT, "test-launder"), ignore_errors=True)

    def test_save_is_cheat(self):
        hl = self.hl
        self.assertIsNone(hl.save_is_cheat(self.honest))
        self.assertIn("named cheat-*", hl.save_is_cheat(self.cheat))
        self.assertIn("cheat mark", hl.save_is_cheat(self.copy), "a renamed copy keeps the mark")
        self.assertIn("same save files", hl.save_is_cheat(self.strip), "repacked without the mark")
        self.assertIn("same save files", hl.save_is_cheat(self.oldcopy), "a copy of an unmarked cheat-* save")
        names = hl.lay_save(self.copy, os.path.join(self.d, "lay"))
        self.assertNotIn(hl.CHEAT_MARK, names, "the mark is never laid out for the game")
        self.assertFalse(os.path.exists(os.path.join(self.d, "lay", "user", hl.CHEAT_MARK)))

    def test_run_refuses_a_cheat_start_save(self):
        import inspect
        hl = self.hl
        for z in (self.cheat, self.copy, self.strip, self.oldcopy):
            with self.assertRaises(hl.Stop, msg=z):
                hl.check_start_save("title", {"frames": 10}, z)
            self.assertTrue(hl.check_start_save("cheat-x", {"cheat": True}, z), "a cheat route may start from it")
        self.assertIsNone(hl.check_start_save("title", {"frames": 10}, self.honest))
        src = inspect.getsource(hl.run)
        self.assertIn("check_start_save(route_name, route, backup)", src, "run() checks the save it lays, --save or not")
        self.assertLess(src.index("check_start_save(route_name"), src.index("lay_save(backup"))
        self.assertIn('"start_save_cheat": start_cheat', src)

    def test_session_refuses_the_reviewers_launder(self):
        """runs --route title --save <a cheat save under any name>: refused before any job starts."""
        for z in (self.cheat, self.copy, self.strip):
            sess = par.Session("test-launder", z, say=quiet)
            try:
                os.makedirs(os.path.join(sess.dir, "jobs"), exist_ok=True)
                sess.boot, sess.lib = os.path.join(sess.dir, "bin", "boot.exe"), os.path.join(sess.dir, "lib", "x.dll")
                with self.assertRaises(par.Stop, msg=z):
                    sess.job("tl-1", "title", sess.routes["title"])
            finally:
                par.rmtree_own(sess.dir)
        sess = par.Session("test-launder", self.honest, say=quiet)
        try:
            os.makedirs(os.path.join(sess.dir, "jobs"), exist_ok=True)
            sess.boot, sess.lib = os.path.join(sess.dir, "bin", "boot.exe"), os.path.join(sess.dir, "lib", "x.dll")
            job = sess.job("tl-2", "title", sess.routes["title"])
            self.assertFalse(job.info["cheat"])
        finally:
            par.rmtree_own(sess.dir)

    def test_pack_carries_the_taint(self):
        import zipfile
        hl = self.hl
        sess, run = "test-launder", "r1"
        job = fresh_dir(os.path.join(par.OUT, sess, "jobs", run))
        save = os.path.join(job, "data", run, "user", "savedata", hl.TITLE)
        os.makedirs(save)
        with open(os.path.join(save, "Chapter0"), "wb") as fh:
            fh.write(b"after the cheat")
        time.sleep(0.05)
        os.makedirs(os.path.join(job, "runs", run))
        rj = os.path.join(job, "runs", run, "run.json")
        out = os.path.join(self.d, "packed")
        for record in ({"outcome": "Completed", "route": "title", "cheat": True, "start_save_cheat": "cheat mark"},
                       {"outcome": "Completed", "route": "title", "save_backup": hl.rel(self.copy)}):  # no flag kept
            with open(rj, "w") as fh:
                json.dump(record, fh)
            with self.assertRaises(par.Stop, msg=record):  # the reviewer's `pack ... rv6-laundered`
                par.cmd_pack([sess, run, "laundered"], saves=out)
            par.cmd_pack([sess, run, "cheat-ok"], saves=out)
            with zipfile.ZipFile(os.path.join(out, "cheat-ok.zip")) as z:
                self.assertIn(hl.CHEAT_MARK, z.namelist(), "a cheat save carries the mark")
        with open(rj, "w") as fh:  # its start save gone: cannot tell, so refused
            json.dump({"outcome": "Completed", "save_backup": "build/harness/test-launder/gone.zip"}, fh)
        with self.assertRaises(par.Stop):
            par.cmd_pack([sess, run, "plain"], saves=out)
        with open(rj, "w") as fh:
            json.dump({"outcome": "Completed", "cheat": False, "start_save_cheat": None}, fh)
        info = par.cmd_pack([sess, run, "plain"], saves=out)
        self.assertNotIn(hl.CHEAT_MARK, info["members"], "a real-play save has no mark")


class OptionsEnvTests(unittest.TestCase):
    """docs/OPTIONS_WIRING.md section 6: no robot run, capture or recapture child sees the PC options file's path
    (FE_OPTIONS, or the game's own FEF_OPTIONS), as tools/play/play.py capture_env. Each check also runs once with
    the drop planted out, and must then see the leak."""

    NAMES = ("FE_OPTIONS", "FEF_OPTIONS")

    def setUp(self):
        self.hl = par.headless_module()
        self.saved = {k: os.environ.get(k) for k in self.NAMES}
        for k in self.NAMES:
            os.environ[k] = os.path.join(self.hl.BUILD, "selftest", "fe14-options.txt")
        self.build = self.hl.BUILD

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_names(self):
        self.assertEqual(set(self.hl.OPTIONS_ENVS), set(self.NAMES))

    def test_headless_boot_env(self):
        route = {"frames": 100, "input": "10:A", "save_at": 50, "shots": [20]}
        d = os.path.join(self.build, "data", "t")
        for mode in ("original", "capture"):
            env = self.hl.boot_env(route, d, d, d, mode, "ab", True, self.hl.LIB, "s")
            self.assertEqual(self.hl.options_leak(env), [], mode)
        real = self.hl.child_env
        try:  # planted: the old filter (FE_ prefix only, case-sensitive) lets FEF_OPTIONS through
            self.hl.child_env = lambda base=None: {k: v for k, v in os.environ.items() if not k.startswith(("ZAKURO_", "FE_"))}
            env = self.hl.boot_env(route, d, d, d, "capture", "ab", True, self.hl.LIB, "s")
            self.assertEqual(self.hl.options_leak(env), ["FEF_OPTIONS"], "planted removal not seen")
        finally:
            self.hl.child_env = real

    def test_recapture_replay_env(self):
        sys.path.insert(0, HERE)
        import recapture  # noqa: E402
        d = os.path.join(self.build, "data", "t")
        for mode in ("original", "capture"):
            env = recapture.replay_env({}, d, d, d, mode, "ab", "x.rec", "lib.dll", "s", 50)
            self.assertEqual(self.hl.options_leak(env), [], mode)
            self.assertEqual(env["FE_READABLE"], mode)
        real = recapture.hl.child_env
        try:
            recapture.hl.child_env = lambda base=None: dict(os.environ)  # planted: nothing dropped
            env = recapture.replay_env({}, d, d, d, "capture", "ab", "x.rec", "lib.dll", "s", 50)
            self.assertEqual(self.hl.options_leak(env), sorted(self.NAMES), "planted removal not seen")
        finally:
            recapture.hl.child_env = real

    def test_parallel_worker_env(self):
        try:
            sess = par.Session("test-optenv", "new-game-empty", say=quiet)
        except par.Stop as e:
            self.skipTest(f"no start save: {e}")
        os.makedirs(os.path.join(sess.dir, "jobs"), exist_ok=True)
        sess.boot, sess.lib = os.path.join(sess.dir, "bin", "boot.exe"), os.path.join(sess.dir, "lib", "x.dll")
        try:
            job = sess.job("test-optenv-1", "title", sess.routes["title"])
            self.assertEqual(self.hl.options_leak(job.env), [])
        finally:
            par.rmtree_own(sess.dir)


class PackTest(unittest.TestCase):
    def test_pack_a_kept_run(self):
        """pack SESSION RUN NAME packs a kept job's in-game save through headless.pack_save (zip to a test folder)."""
        hl = par.headless_module()
        sess, run = "test-pack", "r1"
        job = fresh_dir(os.path.join(par.OUT, sess, "jobs", run))
        try:
            save = os.path.join(job, "data", run, "user", "savedata", hl.TITLE)
            os.makedirs(save)
            with open(os.path.join(save, "Chapter0"), "wb") as fh:
                fh.write(bytes(1) * 64)
            time.sleep(0.05)
            os.makedirs(os.path.join(job, "runs", run))
            with open(os.path.join(job, "runs", run, "run.json"), "w") as fh:
                json.dump({"outcome": "Completed"}, fh)
            out = os.path.join(par.OUT, sess, "saves")
            info = par.cmd_pack([sess, run, "unit-pack"], saves=out)
            self.assertEqual(info["members"], {f"savedata/{hl.TITLE}/Chapter0": 64})
            self.assertTrue(os.path.isfile(os.path.join(out, "unit-pack.zip")))
            self.assertEqual(hl.SAVES, os.path.join(hl.BUILD, "saves"), "headless folders put back")
            with self.assertRaises(par.Stop):  # a real-play run's save may not be named cheat-*
                par.cmd_pack([sess, run, "cheat-unit"], saves=out)
            with open(os.path.join(job, "runs", run, "run.json"), "w") as fh:
                json.dump({"outcome": "Completed", "cheat": True}, fh)
            time.sleep(0.05)
            with self.assertRaises(par.Stop):  # docs/CHEATS.md: a cheat run's save is named cheat-*, always
                par.cmd_pack([sess, run, "unit-pack-2"], saves=out)
            members = par.cmd_pack([sess, run, "cheat-unit"], saves=out)["members"]
            self.assertEqual({k: v for k, v in members.items() if k != hl.CHEAT_MARK},
                             {f"savedata/{hl.TITLE}/Chapter0": 64})
            self.assertIn(hl.CHEAT_MARK, members, "a cheat run's save carries the cheat mark")
            ext = os.path.join(job, "data", run, "user", "extdata", "0000000000001794")
            os.makedirs(ext)
            with open(os.path.join(ext, "Map0.bak"), "wb") as fh:  # a battle save lives in the game's extra data
                fh.write(bytes(8))
            os.utime(os.path.join(job, "runs", run, "run.json"))
            info = par.cmd_pack([sess, run, "cheat-unit-map", "extdata"], saves=out)
            self.assertIn("extdata/0000000000001794/Map0.bak", info["members"])
            self.assertNotIn("extdata/0000000000001794/Map0.bak",
                             par.cmd_pack([sess, run, "cheat-unit-2"], saves=out)["members"], "extdata only when asked")
            laid = hl.lay_save(os.path.join(out, "cheat-unit-map.zip"), os.path.join(par.OUT, sess, "lay"))
            self.assertIn("extdata/0000000000001794/Map0.bak", laid)
            with self.assertRaises(par.Stop):
                par.cmd_pack([sess, "missing", "x"], saves=out)
            with self.assertRaises(par.Stop):
                par.cmd_pack([sess, "../r1", "x"], saves=out)
        finally:
            import shutil
            shutil.rmtree(os.path.join(par.OUT, sess), ignore_errors=True)


def smoke() -> int:
    """The one real check: title x3 side by side (determinism, h4a's comparison), then the same three
    one after another; both must be DETERMINISTIC with one memory hash, %APPDATA% untouched."""
    name = "smoke-title"
    cmd = [sys.executable, par.SELF, "determinism", "--route", "title", "--copies", "3", "--jobs", "3",
           "--serial-too", "--session", name]
    print("smoke:", " ".join(cmd[1:]))
    rc = subprocess.run(cmd).returncode
    try:
        par_s = json.load(open(os.path.join(par.OUT, name + "-par", "summary.json")))
        ser_s = json.load(open(os.path.join(par.OUT, name + "-ser", "summary.json")))
    except OSError as e:
        print(f"smoke: FAIL (no summary: {e})")
        return 1
    ok = (rc == 0 and par_s["determinism"]["verdict"] == "DETERMINISTIC"
          and ser_s["determinism"]["verdict"] == "DETERMINISTIC" and par_s["appdata"]["unchanged"]
          and ser_s["appdata"]["unchanged"] and par_s["speedup"]["one_memory_hash"])
    sp = par_s["speedup"]
    print(f"smoke: {'PASS' if ok else 'FAIL'}: side by side {sp['parallel_s']} s, one after another {sp['serial_s']} s "
          f"(x{sp['factor']}); peaks {[r['peak_mem_mb'] for r in par_s['runs']]} MB; memory "
          f"{par_s['runs'][0]['memory'][:16] if par_s['runs'] and par_s['runs'][0]['memory'] else '-'}")
    return 0 if ok else 1


if __name__ == "__main__":
    want_smoke = "--smoke" in sys.argv
    argv = [a for a in sys.argv if a != "--smoke"]
    prog = unittest.main(argv=argv, exit=False, verbosity=1)
    rc = 0 if prog.result.wasSuccessful() else 1
    if want_smoke and rc == 0:
        rc = smoke()
    sys.exit(rc)
