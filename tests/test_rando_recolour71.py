"""Round 71 (A6): the page's own Recolour row and the "Easier to see" battle hair (tools/randomizer/colours.py
clear_hair; tools/randomizer/ingame.py RECOLOUR_ROW; tools/randomizer/rando.py --recolour; docs/rando/COLOURS.md
section 9).

    python -m unittest tests.test_rando_recolour71          (from the repo root)

Made-up tables and colours first; the last class runs on the user's own extracted RomFS and is skipped otherwise.
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import colours as C  # noqa: E402
import ingame as IG  # noqa: E402
from test_rando_colours import fake_tables  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _edition as E  # noqa: E402  (round 84: Seal legs run only in the Seal edition)

ROMFS = os.path.isfile(os.path.join(ROOT, "extracted", "romfs", "asset", "ROM3.lz"))


def lch(rgb: int) -> tuple[float, float, float]:
    L, a, b = C.rgb_to_lab(rgb)
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a))


def hue_gap(h1: float, h2: float) -> float:
    d = abs(h1 - h2) % 360.0
    return min(d, 360.0 - d)


class ClearHair(unittest.TestCase):
    def test_lab_round_trip(self):
        for c in (0x000000, 0xFFFFFF, 0xAF5454, 0x7D9682, 0x123456, 0xFEEAB7):
            self.assertEqual(C.lab_to_rgb(C.rgb_to_lab(c))[0], c)
        self.assertAlmostEqual(C.rgb_to_lab(0xFFFFFF)[0], 100.0, places=2)
        self.assertEqual(C.delta_e(0xAF5454, 0xAF5454), 0.0)

    def test_same_colour_and_range(self):
        self.assertEqual(C.clear_hair(0xAF5454, 0xAF5454), 0xAF5454)
        self.assertTrue(0 <= C.clear_hair(0x000000, 0x00FF00) <= 0xFFFFFF)

    def test_rules_over_many_pairs(self):
        rng = random.Random(71)
        for _ in range(1500):
            src, dst = rng.randrange(1 << 24), rng.randrange(1 << 24)
            new = C.clear_hair(src, dst)
            L, Cr, h = lch(dst)
            L2, Cr2, h2 = lch(new)
            # never fainter than the plain colour
            self.assertGreaterEqual(C.delta_e(src, new) + 1e-9, C.delta_e(src, dst), (hex(src), hex(dst), hex(new)))
            if new == dst:
                continue
            if Cr >= C.CLEAR_MIN_CHROMA:
                # the new person's hue, a lightness inside the band, moved at most the step from the clamped one
                if Cr2 > 3:
                    self.assertLessEqual(hue_gap(h, h2), 3.0, (hex(dst), hex(new)))
                lo, hi = C.CLEAR_L
                self.assertTrue(lo - 1 <= L2 <= hi + 1, (hex(dst), hex(new), L2))
                self.assertLessEqual(abs(L2 - min(hi, max(lo, L))), C.CLEAR_L_STEP + 1)
            else:
                # Grok: grey, white and black hair never gain a colour; the lightness moves at most the grey step
                self.assertLessEqual(Cr2, Cr + 2.0, (hex(dst), hex(new)))
                self.assertLessEqual(abs(L2 - L), C.CLEAR_GREY_STEP + 1)

    def test_faint_pairs_get_clearer(self):
        # round 59's faint pairs: lavender -> blue-grey (Silas, seen only zoomed), pastel pairs
        for src, dst in ((0xAAB4B4, 0x7D9682), (0x914343, 0x8B5A5C), (0x64708C, 0x5B7396), (0xA58D7B, 0xF5EDDC)):
            new = C.clear_hair(src, dst)
            self.assertGreater(C.delta_e(src, new), C.delta_e(src, dst) + 5, (hex(src), hex(dst), hex(new)))

    def test_deterministic(self):
        self.assertEqual(C.clear_hair(0xAAB4B4, 0x7D9682), C.clear_hair(0xAAB4B4, 0x7D9682))


class PlanWithRow(unittest.TestCase):
    def setUp(self):
        self.t = fake_tables()
        self.plan = {"look": "keep", "swaps": [["PID_A", "PID_B"], ["PID_B", "PID_A"]], "classes": {}}

    def test_on_is_unchanged_and_clear_changes_battle_hair_only(self):
        on = C.plan_colours(self.t, self.plan, {"boss_copies": "follow", "own_colours": "off"})
        default = C.plan_colours(self.t, self.plan, {"boss_copies": "follow", "own_colours": "off",
                                                     "recolour": "on"})
        self.assertEqual(on, default)
        clear, lines = C.plan_colours(self.t, self.plan, {"boss_copies": "follow", "own_colours": "off",
                                                          "recolour": "clear"})
        hair_on = {x["spot"]: x["new"] for x in on[0] if x["table"] == "AssetTable"}
        hair = {x["spot"]: x["new"] for x in clear if x["table"] == "AssetTable"}
        self.assertEqual(hair["PID_A"], C.clear_hair(0xAA0000, 0x00BB00))
        self.assertEqual(hair["PID_B"], C.clear_hair(0x00BB00, 0xAA0000))
        self.assertEqual(set(hair), set(hair_on))
        # the FaceData colour stays the new person's own (battle hair only)
        face_on = [x for x in on[0] if x["table"] == "FaceData"]
        face = [x for x in clear if x["table"] == "FaceData"]
        self.assertEqual(face, face_on)
        self.assertTrue(any("Easier to see" in ln for ln in lines))
        g = C.run_guards(self.t, clear, self.plan, {"boss_copies": "follow", "recolour": "clear"})
        self.assertTrue(all(v["ok"] for v in g.values()), g)
        # the guard knows which colour each choice wants
        if hair != hair_on:
            g = C.run_guards(self.t, clear, self.plan, {"boss_copies": "follow"})
            self.assertFalse(g["colour: filler's own colour"]["ok"])

    def test_off_changes_nothing(self):
        self.assertEqual(C.plan_colours(self.t, self.plan, {"recolour": "off", "own_colours": "off"}), ([], []))

    def test_bad_choice(self):
        with self.assertRaises(ValueError):
            C.check_opts({"recolour": "strong"})


class PageRow(unittest.TestCase):
    """The row on the New Game page, left out of the answer, the run id and the flags at its default."""

    @classmethod
    def setUpClass(cls):
        cls.rows = IG.schema()["rows"]

    def row(self):
        return next(r for r in self.rows if r["key"] == "recolour")

    def test_row(self):
        r = self.row()
        self.assertEqual((r["kind"], r["choices"], r["default"], r["all"]), ("choice", ["on", "clear", "off"], "on",
                                                                              "on"))
        self.assertTrue(r["omit_default"] and r["flag"] == "--recolour" and not r.get("fixed"))
        self.assertEqual(r["section"], "Characters")
        self.assertEqual(r["choice_labels"], {"on": "Their own colour", "clear": "Easier to see", "off": "Off"})
        keys = [x["key"] for x in self.rows]
        self.assertEqual(keys.index("recolour"), keys.index("recruit_stats") + 1)

    def test_default_is_not_answered(self):
        for game in E.legs(self, (None, "seal")):
            vals = IG.page_restore(self.rows, {"randomizer": True, "seed": "r71", "recruit": "route"}, game)
            self.assertEqual(vals["recolour"], "on")
            a = IG.page_answers(self.rows, vals, game)
            self.assertNotIn("recolour", a)
            self.assertNotIn("--recolour", IG.make_args(a))
            # the same text, run id and flags as the page without the row
            old_rows = [r for r in self.rows if r["key"] != "recolour"]
            self.assertEqual(a, IG.page_answers(old_rows, vals, game))
            self.assertEqual(IG.run_id(a, game), IG.run_id(IG.page_answers(old_rows, vals, game), game))
            # Randomize everything keeps it at its default (Grok, round-71 consult)
            ev, _turned = IG.page_everything(self.rows, vals, game)
            self.assertNotIn("recolour", IG.page_answers(self.rows, ev, game))

    def test_other_choices_are_answered(self):
        for v in ("clear", "off"):
            vals = IG.page_restore(self.rows, {"randomizer": True, "seed": "r71", "recolour": v})
            a = IG.page_answers(self.rows, vals)
            self.assertEqual(a["recolour"], v)
            args = IG.make_args(a)
            self.assertEqual(args[args.index("--recolour") + 1], v)
        # a value the row does not have stays at the default
        vals = IG.page_restore(self.rows, {"randomizer": True, "seed": "r71", "recolour": "strong"})
        self.assertEqual(vals["recolour"], "on")

    def test_rando_takes_the_flag(self):
        import contextlib
        import importlib.util
        import io
        # tools/randomizer/rando.py by path (ingame puts tools/play, whose rando.py is PLAY RANDOMIZED, on the path)
        spec = importlib.util.spec_from_file_location("fef_rando_r71", os.path.join(ROOT, "tools", "randomizer",
                                                                                   "rando.py"))
        RD = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(RD)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            RD.main(["make", "--seed", "x", "--recolour", "strong"])
        self.assertTrue(callable(RD._mark_recolour))
        plan, files = RD._mark_recolour({"seed": "x"}, {"plan.json": json.dumps({"seed": "x"}).encode()}, "clear")
        self.assertEqual(plan["recolour"], "clear")
        self.assertEqual(json.loads(files["plan.json"])["recolour"], "clear")


@unittest.skipUnless(ROMFS, "no extracted RomFS")
class RealTables(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = C.load_tables("fates")

    def test_clear_seeds_pass_every_guard_and_get_clearer(self):
        clearer = same = 0
        for i in range(4):
            plan = C._recruit_plan(self.t, f"r71c{i}", "route", "fates")
            co = {"recolour": "clear", "pictures": "off"}
            e, _ = C.plan_colours(self.t, plan, co)
            g = C.run_guards(self.t, e, plan, co)
            self.assertTrue(all(v["ok"] for v in g.values()), {k: v for k, v in g.items() if not v["ok"]})
            on, _ = C.plan_colours(self.t, plan, {"pictures": "off"})
            # the same swapped spots as "on"; only the battle hair values may differ, the face data never
            self.assertEqual({x["spot"] for x in e if x["table"] == "AssetTable"},
                             {x["spot"] for x in on if x["table"] == "AssetTable"})
            self.assertEqual([x for x in e if x["table"] == "FaceData"], [x for x in on if x["table"] == "FaceData"])
            for _name, src, dst, clr in C.swatch_rows(self.t, plan):
                self.assertGreaterEqual(C.delta_e(src, clr) + 1e-9, C.delta_e(src, dst))
                clearer += clr != dst
                same += clr == dst
        self.assertGreater(clearer, same)


if __name__ == "__main__":
    unittest.main()
