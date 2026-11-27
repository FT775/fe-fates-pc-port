"""Synthetic selftest of tools/harness/smoke.py (round 67, goal 5). No game, no robot, no window: the task pool runs
tiny `python -c` children, the window watcher is a fake, and the judges get invented results.

Cases: pass, fail, timeout, missing input, wrong-sha input, window, STOP_ROUND, lanes cap, dependency failed, the
round-59 job rules, the memory judge, and a baseline hash mismatch that names the job and the frame."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
import smoke as S  # noqa: E402

PY = sys.executable


def quiet(*_a, **_k):
    pass


class Pool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="smoke_selftest_")
        self.stop = os.path.join(self.tmp, "STOP_ROUND")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def task(self, name, code, timeout=60, deps=()):
        return S.Task(name, [PY, "-c", code], os.path.join(self.tmp, name), None, timeout, deps,
                      log=os.path.join(self.tmp, name + ".log"))

    def run_pool(self, tasks, lanes=5, windows=lambda pids: []):
        return S.run_tasks(tasks, lanes, windows=windows, stop_file=self.stop, poll=0.05, say=quiet)

    def test_pass_and_fail(self):
        res = self.run_pool([self.task("good", "pass"), self.task("bad", "import sys; sys.exit(4)")])
        self.assertEqual(res["outcomes"]["good"]["status"], "ok")
        self.assertEqual(res["outcomes"]["bad"]["status"], "exit 4")
        self.assertFalse(res["stopped"])
        self.assertIsNone(res["window"])

    def test_timeout_kills(self):
        t0 = time.time()
        res = self.run_pool([self.task("slow", "import time; time.sleep(60)", timeout=1)])
        self.assertEqual(res["outcomes"]["slow"]["status"], "timeout")
        self.assertLess(time.time() - t0, 30)

    def test_window_kills_everything(self):
        seen = {}

        def fake_windows(pids):
            if pids:
                seen["pids"] = set(pids)
                return [(sorted(pids)[0], "a test window")]
            return []
        tasks = [self.task("a", "import time; time.sleep(60)"), self.task("b", "import time; time.sleep(60)"),
                 self.task("c", "pass")]
        t0 = time.time()
        res = self.run_pool(tasks, lanes=2, windows=fake_windows)
        self.assertIn("visible window", res["window"])
        st = {n: o["status"] for n, o in res["outcomes"].items()}
        self.assertEqual(sorted(st), ["a", "b", "c"])
        self.assertIn("window", [st["a"], st["b"]])
        self.assertTrue(st["c"].startswith("not started"))
        self.assertLess(time.time() - t0, 30)

    def test_stop_round_starts_nothing(self):
        open(self.stop, "w").close()
        res = self.run_pool([self.task("x", "pass")])
        self.assertTrue(res["stopped"])
        self.assertEqual(res["outcomes"]["x"]["status"], "not started (STOP_ROUND)")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "x.log")))

    def test_stop_round_while_running(self):
        code = f"import time, pathlib; time.sleep(0.5); pathlib.Path({self.stop!r}).touch(); time.sleep(60)"
        res = self.run_pool([self.task("long", code), self.task("later", "pass", deps=("long",))], lanes=1)
        self.assertTrue(res["stopped"])
        self.assertEqual(res["outcomes"]["long"]["status"], "stopped")
        self.assertIn("STOP_ROUND", res["outcomes"]["later"]["status"])

    def test_lanes_cap_and_max(self):
        tasks = [self.task(f"t{i}", "import time; time.sleep(0.4)") for i in range(6)]
        res = self.run_pool(tasks, lanes=2)
        self.assertLessEqual(res["peak_lanes"], 2)
        self.assertTrue(all(o["status"] == "ok" for o in res["outcomes"].values()))
        tasks = [self.task(f"u{i}", "import time; time.sleep(0.6)") for i in range(8)]
        res = self.run_pool(tasks, lanes=99)
        self.assertLessEqual(res["peak_lanes"], S.LANES_MAX)

    def test_failed_dependency_is_not_started(self):
        res = self.run_pool([self.task("make", "import sys; sys.exit(2)"), self.task("job", "pass", deps=("make",))])
        self.assertEqual(res["outcomes"]["job"]["status"], "needs make (failed)")


class Inputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="smoke_inputs_")
        os.makedirs(os.path.join(self.tmp, "fx", "d"))
        with open(os.path.join(self.tmp, "fx", "a.bin"), "wb") as fh:
            fh.write(b"abc")
        with open(os.path.join(self.tmp, "fx", "d", "x.txt"), "wb") as fh:
            fh.write(b"x")
        tsha, n = S.tree_sha(os.path.join(self.tmp, "fx", "d"))
        self.cfg = {"fixtures_dir": "fx", "inputs": {
            "a": {"file": "a.bin", "sha256": S.sha256_file(os.path.join(self.tmp, "fx", "a.bin"))},
            "d": {"kind": "tree", "file": "d", "sha256": tsha, "files": n}}}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_all_present(self):
        paths, problems = S.check_inputs(self.cfg, self.tmp)
        self.assertEqual(problems, [])
        self.assertTrue(paths["a"].endswith("a.bin"))

    def test_missing_input_is_a_fail(self):
        os.remove(os.path.join(self.tmp, "fx", "a.bin"))
        _p, problems = S.check_inputs(self.cfg, self.tmp)
        self.assertEqual(len(problems), 1)
        self.assertIn("input a: missing file", problems[0])
        code, summary = S.final_exit(problems, {}, 0, {"ok": True}, [], False, False, None)
        self.assertEqual(code, S.EXIT_FAIL)
        self.assertIn("input problem", summary)

    def test_wrong_sha_is_a_fail(self):
        with open(os.path.join(self.tmp, "fx", "d", "x.txt"), "wb") as fh:
            fh.write(b"changed")
        _p, problems = S.check_inputs(self.cfg, self.tmp)
        self.assertEqual(len(problems), 1)
        self.assertIn("tree sha256", problems[0])


class BinSwap(unittest.TestCase):
    """--bin DIR (round 68): staged exe / boot-server / library replace the frozen copies, sha-listed"""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="smoke_bin_")
        self.fx = os.path.join(self.root, "build", "fx")
        os.makedirs(os.path.join(self.fx, "robot"))
        os.makedirs(os.path.join(self.fx, "game"))
        self.files = {"exe": "game/Fire Emblem Fates.exe", "srv": "robot/boot-server.exe",
                      "lib": "robot/0004000000179800.dll"}
        inputs = {}
        for k, f in self.files.items():
            p = os.path.join(self.fx, *f.split("/"))
            with open(p, "wb") as fh:
                fh.write(b"frozen " + k.encode())
            inputs[k] = {"file": f, "sha256": S.sha256_file(p)}
        self.cfg = {"fixtures_dir": "build/fx", "inputs": inputs, "memory": {"exe": "exe"},
                    "robot": {"server": "srv", "lib": "lib"}}
        self.stage = os.path.join(self.root, "build", "release", "r99", "bin")
        os.makedirs(self.stage)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_staged_exe_replaces_frozen_and_is_sha_listed(self):
        with open(os.path.join(self.stage, "Fire Emblem Fates.exe"), "wb") as fh:
            fh.write(b"new exe")
        new, used, problems = S.bin_set(self.cfg, self.stage, self.root)
        self.assertEqual(problems, [])
        self.assertTrue(used["exe"]["staged"])
        self.assertEqual(used["exe"]["sha256"], S.sha256_file(os.path.join(self.stage, "Fire Emblem Fates.exe")))
        self.assertEqual(used["exe"]["frozen_sha256"], self.cfg["inputs"]["exe"]["sha256"])
        self.assertFalse(used["srv"]["staged"])  # not staged: the frozen copy stays
        paths, prob = S.check_inputs(new, self.root)
        self.assertEqual(prob, [])
        self.assertEqual(paths["exe"], os.path.join(self.stage, "Fire Emblem Fates.exe"))
        self.assertEqual(paths["srv"], os.path.join(self.fx, "robot", "boot-server.exe"))
        self.assertNotIn("staged_path", self.cfg["inputs"]["exe"])  # the tracked set is never changed

    def test_empty_bin_is_a_fail(self):
        _n, _u, problems = S.bin_set(self.cfg, self.stage, self.root)
        self.assertEqual(len(problems), 1)
        self.assertIn("none of", problems[0])

    def test_play_or_outside_build_refused(self):
        play = os.path.join(self.root, "play", "game")
        os.makedirs(play)
        for d in (play, self.root):
            _n, _u, problems = S.bin_set(self.cfg, d, self.root)
            self.assertTrue(problems and "under build/" in problems[0], problems)

    def test_staged_file_changed_after_swap_is_a_fail(self):
        p = os.path.join(self.stage, "boot-server.exe")
        with open(p, "wb") as fh:
            fh.write(b"server v2")
        new, _u, _p = S.bin_set(self.cfg, self.stage, self.root)
        with open(p, "wb") as fh:
            fh.write(b"server v3")
        _paths, problems = S.check_inputs(new, self.root)
        self.assertEqual(len(problems), 1)
        self.assertIn("input srv", problems[0])

    def test_write_baseline_refused_with_bin(self):
        code = S.run_smoke(S.SET_FILE, os.path.join(S.BUILD_TOP, "never-made"), 1, S.BASELINE_FILE, True,
                           say=quiet, bin_dir=self.stage)
        self.assertEqual(code, S.EXIT_USAGE)
        self.assertFalse(os.path.exists(os.path.join(S.BUILD_TOP, "never-made")))


def fake_result(run=None, ok=True, laid=None, players=3, status="", faults=()):
    units = [{"force": 0, "pid": f"P{i}", "jid": "J", "x": i, "y": 1, "hp": 20, "items": []} for i in range(players)]
    rb = {"gd_by_file": {"g.bin": {"cells": 10, "wrong": 0}}, "dispos": {"name": "X", "cells": {"cells": 4, "wrong": 0}},
          "person_files": {}, "units": units}
    return {"job": {"name": "j", "chapter": "A011", "run": run}, "ok": ok, "error": None if ok else "stuck",
            "exe_sha": {"boot-server.exe": "s", "0004000000179800.dll": "l"}, "log_faults": list(faults),
            "readback_map": rb, "readback_reload": rb, "steps": {"save_reload": {"units_equal": True}, "map": {"frame": 6058}},
            "rando_log": [f"fates_rando: {n} GameData cells laid" for n in (laid or [])], "status_at_start": status,
            "seconds": 40.0}


WANT = {"boot-server.exe": "s", "0004000000179800.dll": "l"}


class Judges(unittest.TestCase):
    def test_off_and_run_pass(self):
        self.assertTrue(S.judge_job(fake_result(), WANT, None)["ok"])
        v = S.judge_job(fake_result(run="r1-abc", laid=[12, 12], status="run r1-abc active"), WANT, 12)
        self.assertTrue(v["ok"], v["why"])

    def test_job_failures(self):
        self.assertFalse(S.judge_job(fake_result(ok=False), WANT, None)["ok"])
        self.assertIn("log faults", " ".join(S.judge_job(fake_result(faults=["server.log: panic"]), WANT, None)["why"]))
        self.assertIn("not the frozen", " ".join(S.judge_job(fake_result(), {"boot-server.exe": "other"}, None)["why"]))
        v = S.judge_job(fake_result(run="r1-abc", laid=[11], status="run r1-abc"), WANT, 12)
        self.assertIn("GameData cells laid [11], patch has 12", " ".join(v["why"]))
        self.assertIn("off run laid", " ".join(S.judge_job(fake_result(laid=[5]), WANT, None)["why"]))
        r = fake_result()
        r["readback_map"]["gd_by_file"]["g.bin"]["wrong"] = 2
        self.assertIn("2 of 10 wrong", " ".join(S.judge_job(r, WANT, None)["why"]))

    def test_missing_unit_rule(self):
        jobs = [{"name": "a-off", "game": "fates", "chapter": "A011", "run": None},
                {"name": "a-all1", "game": "fates", "chapter": "A011", "run": "k"}]
        v = {"a-off": S.judge_job(fake_result(players=3), WANT, None),
             "a-all1": S.judge_job(fake_result(run="r", laid=[1], status="r", players=2), WANT, 1)}
        S.judge_all(jobs, v)
        self.assertFalse(v["a-all1"]["ok"])
        self.assertIn("player units on the map 2, off run 3", v["a-all1"]["why"][-1])

    def test_memory_judge(self):
        ev = [{"event": "boot", "game_frame": 0, "fatal_errors": 0, "sha256": ["a"]},
              {"event": "at", "game_frame": 3000, "fatal_errors": 0, "sha256": ["b"]},
              {"event": "end", "game_frame": 3000, "fatal_errors": 0, "sha256": ["b"]}]
        self.assertTrue(S.judge_memory(ev, [3000], 0)["ok"])
        self.assertFalse(S.judge_memory(ev, [3000, 4600], 0)["ok"])
        self.assertFalse(S.judge_memory(ev[:2], [3000], 0)["ok"])
        self.assertFalse(S.judge_memory(ev, [3000], 1)["ok"])

    def test_hash_mismatch_names_job_and_frame(self):
        base = {"runs": {"fates-all1": {"id": "r-1", "patch_sha256": "aa"}},
                "jobs": {"bt-A011-off": {"verdict": "PASS", "map_frame": 6058,
                                         "hashes": {"units_map": "u1", "cells_map": "c", "units_reload": "r",
                                                    "cells_reload": "c"}}},
                "memory": {"mem-off": [{"event": "at", "game_frame": 4600, "fatal_errors": 0, "sha256": ["x", "y"]}]}}
        same = json.loads(json.dumps(base))
        self.assertEqual(S.compare_baseline(base, same), [])
        obs = json.loads(json.dumps(base))
        obs["jobs"]["bt-A011-off"]["hashes"]["units_map"] = "u2"
        obs["memory"]["mem-off"][0]["sha256"][1] = "z"
        obs["runs"]["fates-all1"]["patch_sha256"] = "bb"
        bad = S.compare_baseline(base, obs)
        self.assertEqual(len(bad), 3, bad)
        self.assertTrue(any("bt-A011-off" in b and "units_map" in b and "6058" in b for b in bad))
        self.assertTrue(any("mem-off" in b and "frame 4600" in b and "range 1" in b for b in bad))
        self.assertTrue(any("fates-all1" in b and "patch_sha256" in b for b in bad))
        code, _s = S.final_exit([], {"bt-A011-off": {"ok": True}}, 1, {"ok": True}, bad, False, False, None)
        self.assertEqual(code, S.EXIT_FAIL)

    def test_exit_codes(self):
        ok = {"j": {"ok": True}}
        self.assertEqual(S.final_exit([], ok, 1, {"ok": True}, [], False, False, None)[0], S.EXIT_PASS)
        self.assertEqual(S.final_exit([], {"j": {"ok": False}}, 1, {"ok": True}, [], False, False, None)[0], S.EXIT_FAIL)
        self.assertEqual(S.final_exit([], ok, 1, {"ok": False}, [], False, False, None)[0], S.EXIT_FAIL)
        self.assertEqual(S.final_exit([], ok, 1, {"ok": True}, [], True, False, None)[0], S.EXIT_FAIL)
        self.assertEqual(S.final_exit([], ok, 1, {"ok": True}, [], False, False, "a visible window")[0], S.EXIT_FAIL)
        self.assertEqual(S.final_exit([], ok, 1, {"ok": True}, [], False, True, None)[0], S.EXIT_STOP)

    def test_a_set_without_a_memory_compare(self):
        """round 84 (F-072): the Seal set has no memory compare ("memory": null); its PASS line says so, a failed job
        still fails, and the missing-baseline line names the set's own baseline file"""
        ok = {"j": {"ok": True}}
        code, summary = S.final_exit([], ok, 1, {"ok": True}, [], False, False, None, has_memory=False)
        self.assertEqual(code, S.EXIT_PASS)
        self.assertEqual(summary, "PASS: jobs 1/1, baseline equal (no memory compare in this set)")
        self.assertEqual(S.final_exit([], ok, 1, None, [], False, False, None, has_memory=False)[0], S.EXIT_PASS)
        self.assertEqual(S.final_exit([], {"j": {"ok": False}}, 1, None, [], False, False, None,
                                      has_memory=False)[0], S.EXIT_FAIL)
        _c, why = S.final_exit([], ok, 1, None, [], True, False, None, has_memory=False,
                               baseline_name="config/seal/smoke_baseline.json")
        self.assertIn("no baseline (config/seal/smoke_baseline.json)", why)
        self.assertIsNone(S.memory_of({"memory": None}))
        self.assertEqual(S.bin_keys({"memory": None, "robot": {"server": "srv", "lib": "lib"}}), ["srv", "lib"])
        self.assertEqual(S.baseline_of({}), S.BASELINE_FILE)
        self.assertEqual(S.baseline_of({"baseline": "config/seal/smoke_baseline.json"}),
                         os.path.join(S.ROOT, "config", "seal", "smoke_baseline.json"))

    def test_two_lanes_by_default(self):
        """round 84 (F-072, round 83's carry-over): at most 3 robot games in a round, so smoke runs 2 lanes unless
        told otherwise"""
        self.assertEqual(S.LANES_DEFAULT, 2)
        self.assertIn("default 2", S.__doc__)

    def test_partial_run_never_exits_0(self):
        # an --only run that passed its part is PARTIAL (4): exit 0 means the whole set (8/8 and the compare)
        code, summary = S.partial_exit(S.EXIT_PASS, "PASS: jobs 1/1", {"bt-A011-off"})
        self.assertEqual(code, S.EXIT_PARTIAL)
        self.assertNotEqual(code, S.EXIT_PASS)
        self.assertTrue(summary.startswith("PARTIAL (--only bt-A011-off"), summary)
        self.assertEqual(S.partial_exit(S.EXIT_FAIL, "FAIL: x", {"bt-A011-off"}), (S.EXIT_FAIL, "FAIL: x"))
        self.assertEqual(S.partial_exit(S.EXIT_PASS, "PASS: all", None), (S.EXIT_PASS, "PASS: all"))


class TrackedSet(unittest.TestCase):
    """the tracked set itself (the Vanilla+ set since round 84, F-072): 6 jobs (3 paths x off/all1) and the memory
    compare, every input with a sha256 under build/, no game values, nothing of the Seal edition (its 2 jobs are
    config/seal/smoke_set.json, checked in tests/seal/test_smoke_seal.py)"""

    def test_set_shape(self):
        cfg = S.load_set()
        self.assertEqual(len(cfg["jobs"]), 6)
        self.assertEqual(sorted({j["chapter"] for j in cfg["jobs"]}), ["A011", "B016", "C012"])
        self.assertEqual(sum(1 for j in cfg["jobs"] if j.get("run")), 3)
        self.assertEqual({j["game"] for j in cfg["jobs"]} | {r["game"] for r in cfg["runs"].values()}, {"fates"})
        self.assertNotIn("sealmod", cfg["inputs"])
        self.assertNotIn("sealmod", cfg["robot"])
        self.assertEqual(cfg["baseline"], "config/harness/smoke_baseline.json")
        self.assertEqual(S.baseline_of(cfg), S.BASELINE_FILE)
        self.assertEqual(cfg["lanes"]["default"], S.LANES_DEFAULT)
        self.assertEqual(cfg["memory"]["hash_at"], [3000, 4600, 5200])
        self.assertTrue(cfg["fixtures_dir"].startswith("build/"))
        for k, spec in cfg["inputs"].items():
            self.assertRegex(spec["sha256"], r"^[0-9a-f]{64}$", k)
        for j in cfg["jobs"]:
            self.assertIn(j["base"], cfg["inputs"])
            for r in (j.get("run"), j.get("ref_run")):
                if r:
                    self.assertIn(r, cfg["runs"])

    def test_baseline_has_hashes_and_verdicts_only(self):
        if not os.path.isfile(S.BASELINE_FILE):
            self.skipTest("no baseline yet (smoke.py run --write-baseline)")
        bl = S.load_json(S.BASELINE_FILE)
        cfg = S.load_set()
        self.assertEqual(sorted(bl["jobs"]), sorted(j["name"] for j in cfg["jobs"]), "the baseline is this set's")
        self.assertEqual(sorted(bl["runs"]), sorted(cfg["runs"]))
        for name, j in bl["jobs"].items():
            self.assertIn(j["verdict"], ("PASS", "FAIL"))
            for h in j["hashes"].values():
                self.assertRegex(h, r"^[0-9a-f]{64}$", name)
        for ev in bl["memory"].values():
            for e in ev:
                for h in e["sha256"]:
                    self.assertRegex(h, r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
