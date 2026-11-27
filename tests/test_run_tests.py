"""tools/release/run_tests.py (round 67, release part A, goal 1): the core/full unit runner. Made-up test modules in a
scratch folder under build/ (no game data); the last class checks the real tests/heavy.txt and tests/core.txt.

    python -m unittest tests.test_run_tests
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "release"))
import run_tests as RT  # noqa: E402

FAKE = {
    "test_ok": """
        import unittest
        class A(unittest.TestCase):
            def test_one(self): self.assertTrue(True)
            def test_heavy_one(self): self.assertTrue(True)
            @unittest.skip("no game here")
            def test_skipped(self): pass
    """,
    "test_bad": """
        import unittest
        class B(unittest.TestCase):
            def test_fails(self): self.assertEqual(1, 2)
            def test_passes(self): pass
    """,
    "test_heavyonly": """
        import unittest
        class H(unittest.TestCase):
            def test_big(self): self.fail("a heavy test must not run in the core")
    """,
    "test_slow": """
        import time, unittest
        class S(unittest.TestCase):
            def test_sleeps(self): time.sleep(60)
    """,
}


class Fake(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
        cls.top = tempfile.mkdtemp(prefix="rt-", dir=os.path.join(ROOT, "build"))
        cls.pkg = os.path.join(cls.top, "fakepkg")
        os.makedirs(cls.pkg)
        open(os.path.join(cls.pkg, "__init__.py"), "w").close()
        for name, body in FAKE.items():
            with open(os.path.join(cls.pkg, name + ".py"), "w", encoding="utf-8") as fh:
                fh.write(textwrap.dedent(body))
        cls.exclude = ["fakepkg.test_ok.A.test_heavy_*", "fakepkg.test_heavyonly.*"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.top, ignore_errors=True)

    def run_fake(self, mods, profile="core", lanes=2, timeout=300):
        out = os.path.join(self.top, f"out-{profile}-{'-'.join(mods)}-{timeout}")
        ex = self.exclude if profile == "core" else []
        return RT.run(profile, mods, lanes, out, timeout, exclude=ex, tests_dir=self.pkg, top=self.top,
                      save_times=False), out

    def test_core_passes_and_leaves_heavy_out(self):
        s, out = self.run_fake(["test_ok", "test_heavyonly"])
        self.assertTrue(s["ok"], RT.report(s, out))
        self.assertEqual(s["modules"]["test_ok"]["ran"], 2)            # test_one + the skipped one
        self.assertEqual(s["modules"]["test_heavyonly"]["ran"], 0)
        self.assertEqual(s["skipped"], 1)
        self.assertIn("skipped fakepkg.test_ok.A.test_skipped: no game here", RT.report(s, out))
        self.assertIn("PASS: core", RT.report(s, out))

    def test_full_runs_heavy_and_a_failure_fails(self):
        s, out = self.run_fake(["test_ok", "test_heavyonly", "test_bad"], profile="full", lanes=3)
        self.assertFalse(s["ok"])
        self.assertEqual(s["modules"]["test_ok"]["ran"], 3)
        self.assertEqual(s["failed"], 2)                               # test_big and test_fails
        rep = RT.report(s, out)
        self.assertIn("FAILED fakepkg.test_bad.B.test_fails: AssertionError: 1 != 2", rep)
        self.assertIn("FAIL: full", rep)

    def test_lane_timeout_kills_and_fails(self):
        s, out = self.run_fake(["test_slow", "test_ok"], lanes=1, timeout=5)
        self.assertFalse(s["ok"])
        self.assertTrue(any("did not finish" in p for p in s["problems"]), s["problems"])
        self.assertLess(s["wall"], 50)

    def test_nothing_ran_is_not_a_pass(self):
        s, _out = self.run_fake(["test_heavyonly"], lanes=1)
        self.assertEqual(s["ran"], 0)
        self.assertFalse(s["ok"])


class Pure(unittest.TestCase):
    def test_lanes_longest_first_least_loaded(self):
        times = {"a": 100, "b": 60, "c": 50, "d": 10, "e": 5}
        lanes = RT.plan_lanes(list(times), 2, times)
        self.assertEqual(lanes, [["a", "d", "e"], ["b", "c"]])
        self.assertEqual(RT.plan_lanes(["x"], 4, {}), [["x"]])
        self.assertEqual(sorted(sum(RT.plan_lanes(list(times), 4, times), [])), sorted(times))

    def test_heavy_patterns(self):
        pats = ["tests.test_a.C.test_x", "tests.test_b.*"]
        self.assertTrue(RT.is_heavy("tests.test_a.C.test_x", pats))
        self.assertFalse(RT.is_heavy("tests.test_a.C.test_xy", pats))
        self.assertTrue(RT.is_heavy("tests.test_b.D.test_y", pats))

    def test_list_files_parse(self):
        d = tempfile.mkdtemp(dir=os.path.join(ROOT, "build"))
        try:
            h, c = os.path.join(d, "h.txt"), os.path.join(d, "c.txt")
            with open(h, "w") as fh:
                fh.write("# comment\n\ntests.test_a.C.test_x   # why\n")
            with open(c, "w") as fh:
                fh.write("# c\ngrowth  tests.test_g.G.test_q\n")
            self.assertEqual(RT.read_heavy(h), ["tests.test_a.C.test_x"])
            self.assertEqual(RT.read_core(c), [("growth", "tests.test_g.G.test_q")])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_seal_ids_skipped_and_counted_without_tests_seal(self):
        """Round 84 (F-070 split round B): a folder without tests/seal (the Vanilla+ edition) leaves the tests.seal.*
        ids of core.txt / heavy.txt and the seal.* modules of test_times.json out, counts them in one plain line, and
        never fails on them; with tests/seal they are kept and nothing is said."""
        d = tempfile.mkdtemp(dir=os.path.join(ROOT, "build"))
        old = RT.TESTS
        try:
            h, c, tm = (os.path.join(d, n) for n in ("heavy.txt", "core.txt", "test_times.json"))
            with open(h, "w") as fh:
                fh.write("tests.test_a.C.test_x\ntests.seal.test_s.S.test_heavy   # Seal\n")
            with open(c, "w") as fh:
                fh.write("growth  tests.test_g.G.test_q\nseal  tests.seal.test_s.S.test_q\nsb tests.seal.test_b.B.t\n")
            with open(tm, "w") as fh:
                fh.write('{"core": {"seal.test_s": 1.0, "test_a": 2.0}, "full": {"seal.test_s": 3.0, "seal.test_b": 1}}')
            RT.TESTS = os.path.join(d, "tests")          # no tests/seal here
            os.makedirs(RT.TESTS)
            self.assertFalse(RT.seal_here())
            self.assertEqual(RT.read_heavy(h), ["tests.test_a.C.test_x"])
            self.assertEqual(RT.read_core(c), [("growth", "tests.test_g.G.test_q")])
            self.assertEqual(RT.seal_skipped(h, c, tm), {"heavy.txt": 1, "core.txt": 2, "test_times.json": 2})
            os.makedirs(os.path.join(RT.TESTS, "seal"))
            with open(os.path.join(RT.TESTS, "seal", "__init__.py"), "w") as fh:
                fh.write("")
            self.assertTrue(RT.seal_here())                 # the Seal edition: kept, nothing to say
            self.assertEqual(len(RT.read_core(c)), 3)
            self.assertEqual(len(RT.read_heavy(h)), 2)
            self.assertEqual(RT.seal_skipped(h, c, tm), {})
            self.assertEqual(RT.seal_note(), "")
        finally:
            RT.TESTS = old
            shutil.rmtree(d, ignore_errors=True)


class RealLists(unittest.TestCase):
    def test_heavy_and_quick_guards_name_real_tests(self):
        self.assertEqual(RT.check_lists(), [])

    def test_core_is_full_minus_heavy_only(self):
        mods = RT.modules()
        full = RT.selected_ids(mods, [])
        core = RT.selected_ids(mods, RT.read_heavy())
        f = {t for v in full.values() for t in v}
        c = {t for v in core.values() for t in v}
        self.assertTrue(c < f)
        self.assertEqual({t for t in f - c if not RT.is_heavy(t, RT.read_heavy())}, set())
        for _track, tid in RT.read_core():
            self.assertIn(tid, c)


if __name__ == "__main__":
    unittest.main()
