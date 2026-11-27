"""Round 71 (A5): the page's rows from the REAL tool, every core run.

The Rust page test `rando_page::tests::the_real_tool_gives_its_rows` is switched off (#[ignore]: it needs
FEF_RANDO_TOOL and a Python), so it ran only when someone asked for it, and it went out of date once unseen (round 62:
"children" moved from fixed to hide_for and the ignored test still asked for fixed; round 62b fixed it by hand). This
module is its always-on twin: it starts `tools/randomizer/rando.py schema` the way the page does (a separate Python,
no window, a time limit), parses the printed JSON and checks what the Rust test checks, plus what the page's
parse_schema needs from every row. The Rust test stays as the opt-in end-to-end check of the Rust parser
(`FEF_RANDO_TOOL=<repo>/tools/randomizer cargo test -p zakuro --lib -- --ignored real_tool`).

    python -m unittest tests.test_rando_page_tool          (from the repo root)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "randomizer", "rando.py")
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
import ingame as IG  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _edition as E  # noqa: E402  (round 84: Seal legs run only in the Seal edition)

# the keys the Rust test asks for (rando_page.rs the_real_tool_gives_its_rows)
RUST_KEYS = ("randomizer", "seed", "classes", "growths", "join_stats", "trees", "keep_royals", "children",
             "growth_mode", "starting_items", "shops", "rewards", "enemy_weapons", "enemy_classes", "boss_classes")
KINDS = ("onoff", "seed", "choice", "number")


def run_schema() -> tuple[dict, float]:
    """`rando.py schema` in its own Python, hidden (CREATE_NO_WINDOW), as the page starts it."""
    flags = 0x08000000 if os.name == "nt" else 0
    t0 = time.monotonic()
    r = subprocess.run([sys.executable, TOOL, "schema"], capture_output=True, text=True, encoding="utf-8",
                       timeout=60, creationflags=flags, cwd=ROOT)
    took = time.monotonic() - t0
    if r.returncode != 0:
        raise AssertionError(f"rando.py schema exit {r.returncode}: {(r.stdout + r.stderr)[-800:]}")
    return json.loads(r.stdout), took


class RealToolRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema, cls.took = run_schema()
        cls.rows = cls.schema["rows"]
        cls.by = {r["key"]: r for r in cls.rows}

    def test_same_as_in_process(self):
        self.assertEqual(self.schema, json.loads(json.dumps(IG.schema())))
        self.assertEqual(self.schema["format"], 1)
        # the page waits 5 s for the answer (rando_page.rs ANSWER_WITHIN); a cold start here is far below that
        self.assertLess(self.took, 30.0)

    def test_the_rust_tests_keys_and_rules(self):
        for k in RUST_KEYS:
            self.assertIn(k, self.by)
        self.assertEqual(self.by["randomizer"]["default"], False)                     # RandoForm::new: off
        with self.subTest(game="seal"):
            E.need_seal(self)
            self.assertIn("seal", self.by["children"].get("hide_for", {}))
        for r in self.rows:
            if not r.get("hidden"):
                self.assertTrue(r.get("help") and r.get("section"), r["key"])
                self.assertIn(r["section"], IG.SECTIONS)
        vals = IG.page_restore(self.rows, {})
        ev, turned = IG.page_everything(self.rows, vals)                             # form.everything_on()
        self.assertIs(ev["starting_items"], True)
        self.assertIs(ev["enemy_classes"], True)
        self.assertIs(ev["randomizer"], True)
        self.assertTrue(turned)

    def test_every_row_parses_on_the_page(self):
        keys = [r["key"] for r in self.rows]
        self.assertEqual(len(keys), len(set(keys)))
        for r in self.rows:
            k = r["key"]
            self.assertIn(r["kind"], KINDS, k)
            self.assertTrue(r.get("label"), k)
            self.assertIn("default", r, k)
            if r["kind"] == "onoff":
                self.assertIsInstance(r["default"], bool, k)
                self.assertIsInstance(r.get("all", r["default"]), bool, k)
            elif r["kind"] == "choice":
                self.assertIn(r["default"], r["choices"], k)
                self.assertIn(r.get("all", r["default"]), r["choices"], k)
                for v in r.get("choice_labels", {}):
                    self.assertIn(v, r["choices"], k)
            elif r["kind"] == "number":
                self.assertTrue(r["min"] <= r["default"] <= r["max"], k)
                self.assertTrue(r["min"] <= r.get("all", r["default"]) <= r["max"], k)
            if r.get("drives"):
                d = r["drives"]
                self.assertTrue(r.get("page_only"), k)
                self.assertTrue(self.by[d["key"]].get("hidden"), k)
            if r.get("omit_default"):
                # round 71: a late row left out of the answer at its default never is page-only or fixed, and has
                # a flag (it reaches rando.py only when it is not at its default)
                self.assertFalse(r.get("page_only") or r.get("fixed"), k)
                self.assertTrue(r.get("flag"), k)

    def test_off_and_defaults_answers(self):
        self.assertEqual(IG.page_answers(self.rows, IG.page_restore(self.rows, {})), {"randomizer": False})
        a = IG.page_answers(self.rows, IG.page_restore(self.rows, {"randomizer": True, "seed": "r71a5"}))
        self.assertFalse([r["key"] for r in self.rows if r.get("omit_default") and r["key"] in a])
        self.assertFalse([r["key"] for r in self.rows if r.get("page_only") and r["key"] in a])


if __name__ == "__main__":
    unittest.main()
