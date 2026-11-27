"""Round 74 (A6, track page): the page's share code and its two presets (docs/rando/FULL_BLOCK.md sections 6-8,
docs/ROUND74_PLAN.md calls 2 and 3). Host tests, no game run.

- the shared vectors (tests/rando_sharecode_vectors.json; the Rust page's tests read the same file): every good
  vector encodes to its code and decodes back (other spellings too), every bad one is refused with its kind and its
  one plain sentence;
- today's real schema: the code round-trips every value for both games, so the same code gives the same answer text
  and the same run id; Seal of Flames codes are refused on the Fates page and the other way round;
- the presets: Light and Wild as call 2 says, the help lines of call 3, a press resets every row to its default,
  keeps the seed, and never puts a key of its own into the answer.
"""
from __future__ import annotations

import json
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
import ingame as IG  # noqa: E402
import sharecode as S  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _edition as E  # noqa: E402  (round 84: Seal legs run only in the Seal edition)

VECTORS = os.path.join(ROOT, "tests", "rando_sharecode_vectors.json")
# today's layout of the real schema. A row added, removed or changed (a new choice, another min or max) makes every
# older share code "made by another version of the randomizer": change this on purpose, and say so in the round.
# round 75b: the hidden one-choice row rando_version (width 0) made it 57 rows and layout CE, on purpose: every
# round-74 share code is refused ("made by another version of the randomizer"); the body stays 26 characters
LIVE_LAYOUT = "CE"
LIVE_SHARE_ROWS = 57
LIVE_BODY = 26


def vectors() -> dict:
    with open(VECTORS, encoding="utf-8") as fh:
        return json.load(fh)


class Vectors(unittest.TestCase):
    def setUp(self):
        self.v = vectors()
        self.rows = self.v["rows"]

    def test_the_file_matches_the_codec(self):
        self.assertEqual(self.v["format"], 1)
        self.assertEqual(self.v["alphabet"], S.ALPHABET)
        self.assertEqual(len(set(S.ALPHABET)), 32)
        self.assertEqual(S.layout_text(self.rows), self.v["layout_text"])
        self.assertEqual(S.layout(self.rows), self.v["layout"])
        self.assertTrue(self.v["good"] and self.v["bad"])

    def test_good_codes(self):
        for g in self.v["good"]:
            with self.subTest(g["note"]):
                self.assertEqual(S.encode(self.rows, g["values"], g["seed"], g["game"]), g["code"])
                for spelling in [g["code"]] + g.get("also", []):
                    values, seed = S.decode(self.rows, spelling, g["game"])
                    self.assertEqual(seed, g["seed"])
                    want = {r["key"]: g["values"].get(r["key"], r["default"]) for r in S.share_rows(self.rows)}
                    self.assertEqual(values, want)

    def test_the_worked_example(self):
        g = self.v["good"][0]
        self.assertEqual(g["code"], "R1FXX-B1-DC-demo-7")

    def test_bad_codes(self):
        kinds = set()
        for b in self.v["bad"]:
            with self.subTest(b["note"]):
                with self.assertRaises(S.ShareCodeError) as e:
                    S.decode(self.rows, b["code"], b["game"])
                self.assertEqual(e.exception.kind, b["error"])
                self.assertEqual(str(e.exception), b["message"])
                kinds.add(b["error"])
        self.assertEqual(kinds, {"format", "check", "layout", "game", "damaged"})

    def test_every_sentence_is_one_short_plain_line(self):
        for m in list(S.MESSAGES.values()) + [S.game_message("fates"), S.game_message("seal")]:
            self.assertTrue(m.endswith(".") and "\n" not in m and len(m) < 70, m)

    def test_a_bad_seed_is_never_encoded(self):
        for seed in ("", "-x", "x" * 33, "has space"):
            with self.assertRaises(ValueError):
                S.encode(self.rows, {}, seed)


class LiveSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = IG.schema()["rows"]

    def test_todays_layout_and_length(self):
        self.assertEqual(len(S.share_rows(self.rows)), LIVE_SHARE_ROWS)
        self.assertEqual(S.body_length(self.rows), LIVE_BODY)
        self.assertEqual(S.layout(self.rows), LIVE_LAYOUT, S.layout_text(self.rows))
        defaults = {r["key"]: r["default"] for r in self.rows}
        self.assertEqual(len(S.encode(self.rows, defaults, "abcdefgh")), 44)   # an 8-character seed
        self.assertEqual(len(S.encode(self.rows, defaults, "x" * 32)), 68)     # the longest seed

    def test_share_rows_are_every_answered_row(self):
        keys = {r["key"] for r in S.share_rows(self.rows)}
        answered = {r["key"] for r in self.rows if not r.get("page_only")} - {"seed"}
        self.assertEqual(keys, answered)
        self.assertNotIn("spoiler_log", keys)
        self.assertIn("growth_min", keys)          # hidden rows travel too (an old answer keeps its run id)
        self.assertIn("recruit_look", keys)        # a fixed row too (its default)

    def value_sets(self, game):
        rows = self.rows
        defaults = {r["key"]: r["default"] for r in rows if not r.get("drives")}
        everything, _ = IG.page_everything(rows, dict(defaults, seed="ev1"), game)
        sets = [dict(defaults, randomizer=True, seed="d1"), dict(defaults, seed="off1"), everything,
                IG.page_preset(rows, {"seed": "w1"}, "wild", game)]
        rnd = random.Random(74)
        for n in range(12):
            vals = {"seed": f"rnd{n}-x_{rnd.randrange(1000)}", "randomizer": bool(n % 3)}
            for r in rows:
                if r.get("drives") or r["kind"] == "seed" or r["key"] == "randomizer":
                    continue
                if r["kind"] == "onoff":
                    vals[r["key"]] = rnd.random() < 0.5
                elif r["kind"] == "choice":
                    vals[r["key"]] = rnd.choice(r["choices"])
                else:
                    vals[r["key"]] = rnd.randint(r["min"], r["max"])
            sets.append(vals)
        # the form the page would hold (fixed and game-hidden rows at their default)
        return [IG.page_restore(rows, s, game) for s in sets]

    def test_the_same_code_gives_the_same_answer_and_run_id(self):
        for game in E.legs(self, ("fates", "seal")):
            g = None if game == "fates" else game
            for vals in self.value_sets(g):
                with self.subTest(game=game, seed=vals["seed"]):
                    code = S.page_code(self.rows, vals, "proposed1", game)
                    back = S.page_values(self.rows, code, game)
                    share = [r["key"] for r in S.share_rows(self.rows)]
                    self.assertEqual({k: back[k] for k in share + ["seed"]}, {k: vals[k] for k in share + ["seed"]})
                    a, b = IG.page_answers(self.rows, vals, g), IG.page_answers(self.rows, back, g)
                    self.assertEqual(IG.answer_text(a), IG.answer_text(b))
                    if a.get("randomizer"):
                        self.assertEqual(IG.run_id(a, g), IG.run_id(b, g))
                    # the code of the pasted form is the same code (the field shows it again)
                    self.assertEqual(S.page_code(self.rows, back, "other", game), code)

    def test_an_empty_seed_box_gives_the_proposed_seed(self):
        vals = IG.page_restore(self.rows, {"randomizer": True})
        code = S.page_code(self.rows, vals, "prop1234")
        self.assertTrue(code.endswith("-prop1234"))
        self.assertEqual(S.page_values(self.rows, code)["seed"], "prop1234")

    def test_codes_are_for_one_game(self):
        vals = IG.page_restore(self.rows, {"randomizer": True, "seed": "g1"})
        seal = S.page_code(self.rows, vals, "p", "seal")
        fates = S.page_code(self.rows, vals, "p", "fates")
        self.assertTrue(seal.startswith("R1S") and fates.startswith("R1F"))
        with self.assertRaises(S.ShareCodeError) as e:
            S.decode(self.rows, seal, "fates")
        self.assertEqual(str(e.exception), "This code is for Seal of Flames.")
        with self.assertRaises(S.ShareCodeError) as e:
            S.decode(self.rows, fates, "seal")
        self.assertEqual(str(e.exception), "This code is for Fire Emblem Fates.")

    def test_lower_case_and_spaces_are_read(self):
        vals = IG.page_restore(self.rows, {"randomizer": True, "seed": "MiXeD-1", "music": "maps"})
        code = S.page_code(self.rows, vals, "p")
        head, rest = code.split("-", 1)
        self.assertEqual(S.decode(self.rows, " " + code.lower()[:code.index("MiXeD")].lower() + "MiXeD-1 ")[1],
                         "MiXeD-1")
        self.assertEqual(S.decode(self.rows, head.lower() + "-" + rest)[0]["music"], "maps")

    def test_a_fates_code_keeps_children_on(self):
        # round 84: the Seal half (a Seal code keeps Children off) is in tests/seal (the Seal edition's)
        vals = IG.page_restore(self.rows, {"randomizer": True, "seed": "c1", "children": True})
        code = S.page_code(self.rows, vals, "p", "fates")
        self.assertTrue(S.page_values(self.rows, code, "fates")["children"])


class Presets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = IG.schema()
        cls.rows = cls.schema["rows"]
        cls.by = {r["key"]: r for r in cls.rows}

    def test_the_schema_lists_light_and_wild(self):
        p = self.schema["presets"]
        self.assertEqual([x["name"] for x in p], ["light", "wild"])
        self.assertEqual([x["label"] for x in p], ["Light", "Wild"])
        self.assertEqual(self.schema["format"], 1)
        # call 3's help lines
        self.assertEqual(p[0]["help"], "Different classes and growths. Enemies, chests, and the face stay.")
        self.assertEqual(p[1]["help"], "Light, plus enemy classes and weapons, music, and who joins. Face stays.")

    def test_every_preset_value_is_a_settable_row(self):
        for p in self.schema["presets"]:
            self.assertRegex(p["name"], r"^[a-z]+$")
            for k, v in p["values"].items():
                with self.subTest(preset=p["name"], key=k):
                    r = self.by[k]
                    self.assertFalse(r.get("page_only") or r.get("fixed") or r.get("hidden"))
                    self.assertNotEqual(r["kind"], "seed")
                    self.assertEqual(IG.page_restore(self.rows, {k: v})[k], v, "the value fits its row")

    def test_light_is_randomizer_on_and_every_default(self):
        defaults = IG.page_restore(self.rows, {})
        light = IG.page_preset(self.rows, {"seed": "s1"}, "light")
        self.assertEqual(light, dict(defaults, randomizer=True, seed="s1"))
        a = IG.page_answers(self.rows, light)
        self.assertTrue(a["classes"] and a["growths"] and a["join_stats"] and a["keep_royals"])
        self.assertEqual(a["recruit_look"], "keep")
        for k in ("enemy_classes", "enemy_weapons", "nuzlocke"):
            self.assertIs(a[k], False, k)
        self.assertNotIn("chests", a)          # off: left out of the answer (omit_default)
        self.assertNotIn("recolour", a)        # its default, "Their own colour"

    def test_wild_adds_its_rows(self):
        wild = IG.page_preset(self.rows, {"seed": "s2"}, "wild")
        light = IG.page_preset(self.rows, {"seed": "s2"}, "light")
        diff = {k: wild[k] for k in wild if wild[k] != light[k]}
        self.assertEqual(diff, {"enemy_classes": True, "enemy_weapons": True, "music": "maps", "recruit": "route"})
        a = IG.page_answers(self.rows, wild)
        self.assertEqual(a["recruit_look"], "keep")
        self.assertFalse(a["nuzlocke"])
        self.assertNotIn("chests", a)
        self.assertNotIn("recolour", a)

    def test_a_press_resets_every_row_and_keeps_the_seed(self):
        start = IG.page_restore(self.rows, {"randomizer": True, "seed": "keepme", "shops": True, "chests": True,
                                            "difficulty": "hard", "spoiler_log": False, "music": "maps+battles"})
        wild = IG.page_preset(self.rows, start, "wild")
        self.assertEqual(wild["seed"], "keepme")
        self.assertFalse(wild["shops"] or wild["chests"])
        self.assertEqual(wild["difficulty"], "normal")
        self.assertTrue(wild["spoiler_log"], "page-only switches go to their default too")
        self.assertEqual(wild["music"], "maps")
        # Light after Wild gives exactly Light
        self.assertEqual(IG.page_preset(self.rows, wild, "light"), IG.page_preset(self.rows, start, "light"))
        # an empty seed box stays empty (Start game fills it)
        self.assertEqual(IG.page_preset(self.rows, {"seed": ""}, "light")["seed"], "")

    def test_presets_never_enter_the_answer(self):
        for name in ("light", "wild"):
            a = IG.page_answers(self.rows, IG.page_preset(self.rows, {"seed": "x"}, name))
            self.assertFalse({"preset", "presets", "share", "light", "wild"} & set(a))
            self.assertEqual(set(a) - {r["key"] for r in self.rows}, set())

    # round 84: test_seal_presets_keep_children_off is in tests/seal (the Seal edition's)


if __name__ == "__main__":
    unittest.main()
