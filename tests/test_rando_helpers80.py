"""Round 80 (A4, docs/ROUND80_PLAN.md; HOME_DESIGN U11): the Helpers are not randomizer rows. Host tests, no game run.

- `rando.py schema` (the page's rows and presets) names no helper key and no helper word: Enemy phase and True hit
  live in Zakuro's settings.toml (`[fates_helpers]`, patch 0037), never in an answer, a run id or a share code;
- the share layout stays today's (CE, 57 rows: round 75b's layout, unchanged since; round 80 adds no row), so every
  share code made before round 80 still works;
- the robot's sandbox settings writer (tools/harness/helpers_settings.py) and the page robot's "helpers" verdict
  (tools/harness/pagebot.py judge_helpers) pass their own self-tests.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import unittest
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
import ingame as IG  # noqa: E402
import sharecode as S  # noqa: E402

HELPER_KEYS = {"fates_helpers", "helpers", "enemy_phase", "true_hit", "enemy_speed", "ai_skip"}
HELPER_WORDS = ("enemy phase", "true hit", "helpers")
LAYOUT_BEFORE_R80 = "CE"      # tests/test_rando_sharecode.py LIVE_LAYOUT (round 75b)
SHARE_ROWS_BEFORE_R80 = 57


def harness_module(name: str):
    """a tools/harness module by its path (tools/harness is never put on sys.path: its build.py would shadow
    tools/build.py for other tests in the same process)"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"r80_{name}", os.path.join(ROOT, "tools", "harness", name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rando_schema() -> dict:
    """the exact text the page reads: `rando.py schema`"""
    import importlib.util
    # tools/randomizer/rando.py by its path (ingame puts tools/play, which has its own rando.py, on the path)
    spec = importlib.util.spec_from_file_location("rando_r80_schema", os.path.join(ROOT, "tools", "randomizer",
                                                                                  "rando.py"))
    rando = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rando)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rando.main(["schema"])
    return json.loads(buf.getvalue())


class HelpersAreNotRandomizerRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = rando_schema()
        cls.rows = cls.schema["rows"]

    def test_no_helper_key_or_word_in_the_schema(self):
        keys = {r["key"] for r in self.rows}
        self.assertFalse(keys & HELPER_KEYS, keys & HELPER_KEYS)
        for r in self.rows:
            words = " ".join(str(r.get(k, "")) for k in ("label", "section", "help")).lower()
            for w in HELPER_WORDS:
                self.assertNotIn(w, words, r["key"])
        for p in self.schema.get("presets", []):
            self.assertFalse(set(p.get("values", {})) & HELPER_KEYS, p.get("name"))

    def test_the_rows_are_the_ingame_schema(self):
        self.assertEqual([r["key"] for r in self.rows], [r["key"] for r in IG.schema()["rows"]])

    def test_the_share_layout_is_unchanged(self):
        self.assertEqual(len(S.share_rows(self.rows)), SHARE_ROWS_BEFORE_R80)
        self.assertEqual(S.layout(self.rows), LAYOUT_BEFORE_R80, S.layout_text(self.rows))
        for k in HELPER_KEYS:
            self.assertNotIn(k + ":", S.layout_text(self.rows))

    def test_an_answer_never_carries_a_helper(self):
        defaults = {r["key"]: r["default"] for r in self.rows}
        defaults["seed"] = "helpers80"
        answer = IG.page_answers(self.rows, defaults, None)
        self.assertFalse(set(answer) & HELPER_KEYS, answer)


class RobotTools(unittest.TestCase):
    def test_the_sandbox_settings_writer(self):
        H = harness_module("helpers_settings")
        with contextlib.redirect_stdout(io.StringIO()):
            ok, n = H.selftest()
        self.assertEqual(ok, n)
        self.assertGreaterEqual(n, 15)

    def test_the_page_robot_helpers_verdict(self):
        P = harness_module("pagebot")
        self.assertIn("helpers", P.SCENARIOS)
        with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)   # older selftest cases leave files open
            ok, n = P.selftest()
        self.assertEqual(ok, n)


if __name__ == "__main__":
    unittest.main()
