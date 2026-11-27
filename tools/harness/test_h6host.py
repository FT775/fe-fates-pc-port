#!/usr/bin/env python3
"""Tests for tools/harness/h6host.py: the driver time limit reaches borrowed code (round 18).

    python tools/harness/test_h6host.py        # a few seconds; no C compiler, no text.bin needed

Round 17: two runaway planted bugs hung for 15 minutes, because ai_perm_diff runs its driver through
move_diff.compare, and only the diff script's own module had the time-limited subprocess.run. These tests check
that (1) a made-up helper module, imported by a made-up diff module, has its runaway "driver" stopped by the limit,
(2) a module outside the patched folder is left alone, and (3) the real borrowed modules (move_diff, leaf_diff,
sheet_diff) get the limited run when h6host loads ai_perm_diff, flags_diff and item_diff. Made-up files live under
build/h6host/test-<pid>/ (removed at the end).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import h6host as H  # noqa: E402

TMP = os.path.join(H.ROOT, "build", "h6host", f"test-{os.getpid()}")
HELPER = '''import subprocess, sys
def run_driver():
    # a "driver" that never ends: python reading this loop from stdin
    return subprocess.run([sys.executable], input="while True: pass\\n", capture_output=True, text=True)
'''
DIFF = '''import subprocess
import h6t_helper_{tag} as HELP
def compare():
    return HELP.run_driver()
'''


def _make(folder: str, tag: str) -> None:
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"h6t_helper_{tag}.py"), "w", encoding="utf-8") as fh:
        fh.write(HELPER)
    with open(os.path.join(folder, f"h6t_diff_{tag}.py"), "w", encoding="utf-8") as fh:
        fh.write(DIFF.format(tag=tag))


class BorrowedDriverLimit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inside = os.path.join(TMP, "readable")
        cls.outside = os.path.join(TMP, "other")
        _make(cls.inside, "in")
        _make(cls.outside, "out")
        sys.path[:0] = [cls.inside, cls.outside]

    @classmethod
    def tearDownClass(cls):
        for p in (cls.inside, cls.outside):
            if p in sys.path:
                sys.path.remove(p)
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        self.old_limit = H.DRIVER_TIMEOUT
        H.DRIVER_TIMEOUT = 2

    def tearDown(self):
        H.DRIVER_TIMEOUT = self.old_limit

    def test_runaway_in_borrowed_module_is_stopped(self):
        import h6t_diff_in as diff  # noqa: F401  (imports its helper, which holds the real subprocess)
        helper = sys.modules["h6t_helper_in"]
        helper.subprocess = diff.subprocess = subprocess  # as freshly imported (another test may have patched)
        patched = H.patch_helpers((self.inside,))
        self.assertIn("h6t_helper_in", patched)
        self.assertIn("h6t_diff_in", patched)
        self.assertIs(helper.subprocess.run, H._run)
        t0 = time.time()
        with self.assertRaises(subprocess.TimeoutExpired):
            diff.compare()
        self.assertLess(time.time() - t0, 30)
        self.assertEqual(H.patch_helpers((self.inside,)), [])  # a second pass changes nothing

    def test_module_outside_the_folder_is_left_alone(self):
        import h6t_diff_out  # noqa: F401
        H.patch_helpers((self.inside,))
        self.assertIs(sys.modules["h6t_helper_out"].subprocess, subprocess)

    def test_judge_reports_borrowed_runaway_as_caught(self):
        import h6t_diff_in  # noqa: F401
        helper = sys.modules["h6t_helper_in"]
        helper.subprocess = subprocess  # as if freshly imported, unpatched

        class Mod:  # a diff module whose compare is borrowed from the helper
            @staticmethod
            def compare(exe, cc, lines, expected, show, quiet=False):
                helper.run_driver()
                return {}

        real = H.patch_helpers
        H.patch_helpers = lambda roots=None: real((self.inside,))
        try:
            self.assertEqual(H.judge(Mod, "cc", [], [], "exe"), ("caught", "runaway", None))
        finally:
            H.patch_helpers = real


class RealBorrowedModules(unittest.TestCase):
    def test_ai_perm_and_flags_helpers_get_the_limit(self):
        # ai_perm_diff borrows move_diff (round 17's two runaways); flags_diff borrows leaf_diff; item_diff
        # borrows sheet_diff (round 14's two item_record runaways, 54 minutes, stopped by hand)
        for batch, stem in (("ai", "ai_items"), ("event", "flags"), ("item", "")):
            try:
                mod, _, _ = H.load(batch, stem)
            except SystemExit as e:  # pragma: no cover
                self.skipTest(f"{stem}: diff script could not load ({e})")
            self.assertIs(mod.subprocess.run, H._run)
        for name in ("move_diff", "leaf_diff", "sheet_diff"):
            self.assertIn(name, sys.modules)
            self.assertIs(sys.modules[name].subprocess.run, H._run, name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
