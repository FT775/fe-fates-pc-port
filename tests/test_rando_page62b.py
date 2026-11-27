"""Round 62b (F-049 addendum, F-050): the randomizer page cleanup, host tests (no game run).

- the schema: Grok's sections in order, a short label and one plain sentence of help on every visible row, no
  "slice1" (or min/max rows) on the page, leftover rows hidden but still answered, Children not on the Seal page
  (hide_for, not grey), every default unchanged;
- SEEDS UNCHANGED: for every round-62 check run (build/r62/check/runs, both games) and the off / everything-on sets,
  the round-62 page and the round-62b page give the same answer text, the same run id and the same `rando.py make`
  flags (the frozen round-62 schema is tests/test_rando_page_r62_schema.json; the round-62 make_args is git HEAD's
  ingame.py when git is there);
- round 75b (seed guarantees, docs/SEED_GUARANTEES_PLAN.md section 5): the promise is now "an old answer keeps its
  run folder; a new answer gets a version-2 run id". The schema copy gained the hidden version row rando_version, so
  apart from it the answers are still the same; without it (the round-62 page as it was) a new answer differs by
  exactly "rando_version":"2", the run id changes (a new game never re-uses a folder made before the guarantees), the
  make flags do not; a saved answer still names its own folder. VersionRowTests: the row itself, the share code's
  width-0 vectors and layout change, and rando.py check's plain refusal of an old folder (exit 3);
- Spoiler log: a page-only row, never in the answer (so never in the run id or the flags); rando.py make --spoiler off
  writes no spoiler.txt and nothing else changes (the real make: build/r62b/implement/remake.py, run by the round);
- Randomize everything: the safe rows only (never Nuzlocke, Children, the full swap, a row hidden for the game), the
  seed kept; the two switches drive the hidden enemy_upgrade / boss_stats rows the same way round 62's Everything on
  did.
"""
from __future__ import annotations

import glob
import importlib.util
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
import ingame as IG  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _edition as E  # noqa: E402  (round 84: Seal legs run only in the Seal edition)

OLD_SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_rando_page_r62_schema.json")
RUNS = os.path.join(ROOT, "build", "r62", "check", "runs")
OLD_TAG = "258da34"          # round 62's commit: its ingame.py is the "before" make_args


def old_rows() -> list[dict]:
    """the round-62 copy as the tests use it: with the round-75b version row (the copy gained it on purpose)"""
    with open(OLD_SCHEMA, encoding="utf-8") as fh:
        return json.load(fh)["rows"]


def r62_rows() -> list[dict]:
    """the round-62 page as it was before round 75b: the copy without the version row"""
    return [r for r in old_rows() if r["key"] != IG.VERSION_KEY]


def new_rows() -> list[dict]:
    return IG.schema()["rows"]


def old_ingame():
    """round 62's ingame.py (git show 258da34:tools/randomizer/ingame.py), or None without git."""
    try:
        text = subprocess.run(["git", "show", f"{OLD_TAG}:tools/randomizer/ingame.py"], cwd=ROOT, capture_output=True,
                              text=True, encoding="utf-8", timeout=60,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    if "def make_args" not in text:
        return None
    d = os.path.join(ROOT, "build", "r62b", "tests")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "ingame_r62.py")
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    spec = importlib.util.spec_from_file_location("ingame_r62", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.ROOT = ROOT
    return m


def answer_sets() -> list[tuple[str, str | None, dict]]:
    """(name, game, saved answer): every round-62 check run, plus Randomizer off and the Everything-on sets."""
    out = []
    for f in sorted(glob.glob(os.path.join(RUNS, "*", "*", "options.json"))):
        game = os.path.basename(os.path.dirname(os.path.dirname(f)))
        if game != "fates" and not E.seal_edition():   # round 84: Seal runs only in the Seal edition
            continue
        with open(f, encoding="utf-8") as fh:
            a = json.load(fh)
        a.pop("game", None)
        out.append((f"{game}/{os.path.basename(os.path.dirname(f))}", None if game == "fates" else game, a))
    old = old_rows()
    every = {r["key"]: r.get("all", r["default"]) for r in old}
    for game in ((None, "seal") if E.seal_edition() else (None,)):
        out.append((f"{game or 'fates'}/off", game, {"randomizer": False}))
        out.append((f"{game or 'fates'}/defaults-on", game, {"randomizer": True, "seed": "r62bdef"}))
        for i, extra in enumerate(({}, {"recruit": "any", "recruit_class": "slot", "recruit_stats": "slot",
                                        "boss_stats": "ease"},
                                   {"recruit": "any", "nuzlocke": True, "difficulty": "hard"}), 1):
            out.append((f"{game or 'fates'}/all{i}", game, dict(every, randomizer=True, seed=f"r62ball{i}", **extra)))
    return out


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.rows = new_rows()
        self.by = {r["key"]: r for r in self.rows}
        self.visible = [r for r in self.rows if not r.get("hidden")]

    def test_sections_in_grok_order(self):
        secs = [r["section"] for r in self.visible]
        order = [s for i, s in enumerate(secs) if i == 0 or secs[i - 1] != s]
        self.assertEqual(order, list(IG.SECTIONS), "each section once, in Grok's order")
        self.assertEqual([r["key"] for r in self.visible], list(IG.PAGE))

    def test_every_visible_row_has_a_label_and_one_sentence_of_help(self):
        for r in self.visible:
            self.assertTrue(r["label"] and r["help"], r["key"])
            base = r["label"].split(" (")[0]
            self.assertLessEqual(len(base), 24, r["key"])
            h = r["help"]
            self.assertTrue(h.endswith("."), r["key"])
            self.assertNotIn(". ", h[:-1], f"{r['key']}: one sentence")
            self.assertLessEqual(len(h), 170, r["key"])

    def test_nothing_from_the_lab_notebook_on_the_page(self):
        for r in self.visible:
            shown = [r["label"], r.get("help", "")] + list((r.get("choice_labels") or {}).values())
            for text in shown:
                self.assertNotIn("slice1", text, r["key"])
            if r["kind"] == "choice" and not r.get("switch"):
                for c in r["choices"]:
                    self.assertIn(c, r["choice_labels"], f"{r['key']}={c} has plain words")
        for k in ("growth_min", "growth_max", "upgrade_rank", "enemy_upgrade", "boss_stats", "boss_max_boost",
                  "boss_variance"):
            self.assertTrue(self.by[k].get("hidden"), k)
            self.assertIn("flag", self.by[k], f"{k}: still answered and passed on")

    def test_defaults_unchanged(self):
        old = {r["key"]: r for r in old_rows()}
        for k, r in old.items():
            self.assertEqual(self.by[k]["default"], r["default"], k)
            self.assertEqual(self.by[k].get("flag"), r.get("flag"), k)
            if k != "recruit_look":     # round 76 (F-062): the full swap look is offered (default still "keep")
                self.assertEqual(bool(self.by[k].get("fixed")), bool(r.get("fixed")), k)
            self.assertEqual(self.by[k]["kind"], r["kind"], k)
            self.assertEqual(self.by[k].get("choices"), r.get("choices"), k)
        self.assertEqual(self.by["promotion_sides"]["default"], "any")
        self.assertEqual(self.by["difficulty"]["default"], "normal")
        new_keys = set(self.by) - set(old)
        # round 71: a later row is left out of the answer at its default (omit_default), so old answers keep their
        # text, run id and make flags (Recolour, Chest and village items)
        late = {k for k in new_keys if self.by[k].get("omit_default")}
        self.assertEqual(new_keys - late, {"spoiler_log", "stronger_weapons", "tougher_bosses"})
        for k in new_keys - late:
            self.assertTrue(self.by[k].get("page_only") and "flag" not in self.by[k], k)

    # round 84: test_seal_children_row_does_not_exist is in tests/seal (the Seal edition's)

    def test_promotions_and_weapon_stats_are_switches(self):
        for k in ("promotions", "weapon_stats"):
            self.assertTrue(self.by[k]["switch"])
            self.assertEqual(self.by[k]["choices"], ["off", "on"])

    def test_full_look_offered_on_fates_grey_on_seal(self):
        """round 76 (F-062, THE PAGE rule of F-060): offered on Fates with both choices, "Keep the face" the default
        and out of Randomize everything; grey on Seal of Flames (scene name plates keep the old name); the help line
        says what the full swap does and that movies and My Room keep the old person, castle join scenes the new."""
        r = self.by["recruit_look"]
        self.assertFalse(r.get("fixed"))
        self.assertEqual((r["default"], r["all"], r["choices"]), ("keep", "keep", ["keep", "full"]))
        self.assertEqual(r["choice_labels"], {"keep": "Keep the face", "full": "Full swap"})
        self.assertEqual(r["label"], "How they look")
        for part in ("Full swap", "movies and My Room keep the old person", "castle join scenes show the new one"):
            self.assertIn(part, r["help"])
        with self.subTest(game="seal"):
            E.need_seal(self)
            self.assertIn("name plates", r["grey_for"]["seal"])
        rows = new_rows()
        want_of = {None: "full", "seal": "keep"}
        for game in E.legs(self, (None, "seal")):
            want = want_of[game]
            v = dict(IG.page_restore(rows, {"recruit": "route", "recruit_look": "full"}, game), randomizer=True,
                     seed="s")
            self.assertEqual(IG.page_answers(rows, v, game)["recruit_look"], want, game)
            self.assertEqual(IG.page_everything(rows, v, game)[0]["recruit_look"], "keep", game)

    def test_help_texts_carry_the_owner_corrections(self):
        self.assertIn("Garon, Anankos and a few story bosses keep theirs", self.by["boss_classes"]["help"])
        d = self.by["difficulty"]["help"]
        for part in ("Easy is +1 forge", "Normal the next weapon tier", "Hard the next tier +1", "10% HP",
                     "+1 might per step"):
            self.assertIn(part, d)


class PageModelTests(unittest.TestCase):
    def test_off_is_randomizer_false_only(self):
        rows = new_rows()
        v = IG.page_restore(rows, {"randomizer": False, "classes": False})
        self.assertEqual(IG.page_answers(rows, v), {"randomizer": False})

    def test_page_only_rows_never_in_the_answer(self):
        rows = new_rows()
        v = IG.page_restore(rows, {"randomizer": True, "seed": "x1", "spoiler_log": False})
        a = IG.page_answers(rows, v)
        for k in ("spoiler_log", "stronger_weapons", "tougher_bosses"):
            self.assertNotIn(k, a)
        v2 = dict(v, spoiler_log=True)
        self.assertEqual(IG.answer_text(IG.page_answers(rows, v2)), IG.answer_text(a))
        self.assertEqual(IG.run_id(IG.page_answers(rows, v2)), IG.run_id(a))
        self.assertEqual(IG.make_args(IG.page_answers(rows, v2)), IG.make_args(a))

    def test_switches_show_and_drive_the_hidden_rows(self):
        rows = new_rows()
        by = {r["key"]: r for r in rows}
        v = IG.page_restore(rows, {"randomizer": True, "seed": "x", "enemy_upgrade": 50, "boss_stats": "ease"})
        self.assertTrue(IG.page_value(rows, v, by["stronger_weapons"]))
        self.assertTrue(IG.page_value(rows, v, by["tougher_bosses"]))
        a = IG.page_answers(rows, v)
        self.assertEqual((a["enemy_upgrade"], a["boss_stats"]), (50, "ease"), "an old answer is kept as it was")
        v = IG.page_restore(rows, {"randomizer": True, "seed": "x"})
        self.assertFalse(IG.page_value(rows, v, by["stronger_weapons"]))
        self.assertEqual(by["stronger_weapons"]["drives"], {"key": "enemy_upgrade", "off": 0, "on": 25})
        self.assertEqual(by["tougher_bosses"]["drives"], {"key": "boss_stats", "off": "off", "on": "linear"})

    def test_fates_answers_children_as_given(self):
        # round 84: the Seal half (Seal answers Children at its default) is in tests/seal (the Seal edition's)
        rows = new_rows()
        v = IG.page_restore(rows, {"randomizer": True, "seed": "s", "children": True})
        self.assertIs(IG.page_answers(rows, v)["children"], True)

    def test_run_id_is_the_cores(self):
        # fates_rando_session::run_id: "<seed>-<fnv1a32 of the answer text>"; Seal puts "game" first
        a = {"randomizer": True, "seed": "abc"}
        text = '{"randomizer":true,"seed":"abc"}'
        h = 0x811C9DC5
        for b in text.encode():
            h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
        self.assertEqual(IG.run_id(a), f"abc-{h:08x}")
        # round 84: the Seal run id ("game" first) is in tests/seal (the Seal edition's)


class SeedsUnchangedTests(unittest.TestCase):
    """Goal 5: every answer the round-62 page could give (the check runs and the off / everything-on sets) gives the
    same text, run id and make flags on the round-62b page."""

    @classmethod
    def setUpClass(cls):
        cls.old = old_rows()
        cls.new = new_rows()
        cls.sets = answer_sets()
        cls.old_ig = old_ingame()

    def test_enough_sets(self):
        n = sum(1 for name, _g, _a in self.sets if "/r59" in name or "/r60" in name or "/r62" in name)
        if os.path.isdir(RUNS) and E.seal_edition():
            self.assertGreaterEqual(n, 78, "the round-62 check runs are all here")
        E.legs(self, ("seal",))      # round 84: without the Seal edition its sets are left out (one skipped subtest)
        self.assertGreaterEqual(len(self.sets), 10 if E.seal_edition() else 5)

    def test_old_answer_keeps_its_folder_new_answer_gets_a_version_2_run_id(self):
        """round 75b: the round-62 page (no version row) vs today's: the new answer is the old one plus
        "rando_version":"2", so its run id differs (a fresh folder, made with the guarantees), the make flags are the
        same, Randomizer off stays {"randomizer": false}; the saved answer itself still gives its own old id (a save
        names its run folder, which is kept)."""
        r62 = r62_rows()
        v = str(IG.rando_version())
        for name, game, saved in self.sets:
            before = IG.page_answers(r62, IG.page_restore(r62, saved, game), game)
            after = IG.page_answers(self.new, IG.page_restore(self.new, saved, game), game)
            if not before.get("randomizer"):
                self.assertEqual(after, {"randomizer": False}, name)
                continue
            self.assertNotIn(IG.VERSION_KEY, before, name)
            self.assertEqual(after, dict(before, **{IG.VERSION_KEY: v}), name)
            self.assertNotEqual(IG.run_id(after, game), IG.run_id(before, game), name)
            self.assertEqual(IG.make_args(after), IG.make_args(before), name)
            self.assertEqual(IG.run_id(before, game), IG.run_id(dict(before), game), name)

    def test_same_answer_text_and_run_id(self):
        # the copy carries the round-75b version row too: every OTHER row still answers as on the round-62 page
        for name, game, saved in self.sets:
            before = IG.page_answers(self.old, IG.page_restore(self.old, saved, game), game)
            after = IG.page_answers(self.new, IG.page_restore(self.new, saved, game), game)
            self.assertEqual(IG.answer_text(after), IG.answer_text(before), name)
            if before.get("randomizer"):
                self.assertEqual(IG.run_id(after, game), IG.run_id(before, game), name)

    def test_last_json_with_page_only_rows_gives_the_same_answer(self):
        # last.json holds the form's values; the new page also keeps spoiler_log there
        for name, game, saved in self.sets:
            before = IG.page_answers(self.old, IG.page_restore(self.old, saved, game), game)
            for sp in (True, False):
                v = IG.page_restore(self.new, dict(saved, spoiler_log=sp), game)
                self.assertEqual(IG.page_answers(self.new, v, game), before, name)

    def test_same_make_flags(self):
        if self.old_ig is None:
            self.skipTest("git (round 62's ingame.py) is not available")
        for name, game, saved in self.sets:
            before = IG.page_answers(self.old, IG.page_restore(self.old, saved, game), game)
            if not before.get("randomizer"):
                continue
            after = IG.page_answers(self.new, IG.page_restore(self.new, saved, game), game)
            self.assertEqual(IG.make_args(after), self.old_ig.make_args(before), name)
            # the run folders were made from the saved (partial) answer directly: the same flags too
            self.assertEqual(IG.make_args(saved), self.old_ig.make_args(saved), name)

    def test_switch_on_gives_round_62_everything_on_values(self):
        old_all = {r["key"]: r.get("all") for r in self.old}
        by = {r["key"]: r for r in self.new}
        self.assertEqual(by["stronger_weapons"]["drives"]["on"], old_all["enemy_upgrade"])
        self.assertEqual(by["tougher_bosses"]["drives"]["on"], old_all["boss_stats"])


class RandomizeEverythingTests(unittest.TestCase):
    def test_safe_rows_only_and_the_seed_kept(self):
        rows = new_rows()
        for game in E.legs(self, (None, "seal")):
            v = IG.page_restore(rows, {"seed": "keepme"}, game)
            v2, turned = IG.page_everything(rows, v, game)
            self.assertEqual(v2["seed"], "keepme")
            self.assertTrue(v2["randomizer"])
            self.assertIs(v2["children"], False)
            self.assertIs(v2["nuzlocke"], False)
            self.assertEqual(v2["recruit_look"], "keep")
            self.assertEqual(v2["recruits"], "all")
            self.assertEqual((v2["enemy_upgrade"], v2["boss_stats"]), (25, "linear"))
            self.assertTrue(v2["spoiler_log"])
            for label in ("Randomizer", "Spread classes", "Stronger enemy weapons",
                          "Tougher bosses", "Music"):
                self.assertIn(label, turned, game)
            self.assertNotIn("Children", turned)
            self.assertNotIn("Nuzlocke", turned)
            a = IG.page_answers(rows, v2, game)
            self.assertNotIn("spoiler_log", a)
            args = IG.make_args(a)
            self.assertEqual(args[args.index("--children") + 1], "off")
            self.assertEqual(args[args.index("--nuzlocke") + 1], "off")
            self.assertEqual(args[args.index("--recruit-look") + 1], "keep")


class SpoilerFlagTests(unittest.TestCase):
    def test_make_takes_spoiler_off(self):
        spec = importlib.util.spec_from_file_location("rando_r62b", os.path.join(ROOT, "tools", "randomizer",
                                                                                 "rando.py"))
        rando = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rando)
        out = io_run(lambda: rando.main(["make", "--help"]))
        self.assertIn("--spoiler", out)

    def test_page_command_never_carries_the_spoiler(self):
        a = IG.page_answers(new_rows(), IG.page_restore(new_rows(), {"randomizer": True, "seed": "x",
                                                                    "spoiler_log": False}))
        self.assertNotIn("--spoiler", IG.make_args(a))


def load_rando():
    """tools/randomizer/rando.py by path (tools/play/rando.py has the same module name)"""
    spec = importlib.util.spec_from_file_location("rando_r75b", os.path.join(ROOT, "tools", "randomizer", "rando.py"))
    rando = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rando)
    return rando


# round 73's play-evening answer (build/r73/seed/check/answer-c1.json; our own option keys only): the owner's run
# hoshido73-6ab5ad56. Round 75b must give a new game with the same settings a new run id, and leave the old one alone.
HOSHIDO73 = {"adjust_hp": False, "assign_evenly": True, "base_variance": 5, "bases_mode": "redistribute",
             "boss_classes": True, "boss_max_boost": 5, "boss_stats": "linear", "boss_variance": 0, "children": False,
             "class_base_variance": 2, "class_bases": "delta", "class_growth_variance": 10, "class_growths": "delta",
             "class_move": "small", "classes": True, "difficulty": "normal", "enemy_buff": 10, "enemy_classes": True,
             "enemy_drops": 10, "enemy_growths": "flat", "enemy_levels": 0, "enemy_trees": "own", "enemy_upgrade": 25,
             "enemy_weapons": True, "growth_max": 80, "growth_min": 5, "growth_mode": "redistribute",
             "growth_variance": 30, "growths": True, "join_stats": True, "keep_royals": True, "music": "maps+battles",
             "nuzlocke": False, "personal_skills": "shuffle", "promotion_sides": "any", "promotions": "on",
             "randomizer": True, "reclass": "random", "recruit": "route", "recruit_class": "own",
             "recruit_look": "keep", "recruit_stats": "autolevel", "recruits": "all", "rewards": True,
             "scale_to_level": True, "seed": "hoshido73", "shop_sides": "own", "shops": True, "skill_slots": "class",
             "starting_items": True, "trees": "own", "upgrade_rank": "same", "weapon_stats": "on",
             "weapon_traits": 25, "wild_traits": False}
HOSHIDO73_RUN = "hoshido73-6ab5ad56"
HOSHIDO73_RUN_V2 = "hoshido73-439f92bf"       # the same settings on today's page (rando_version "2")
R74_LAYOUT = "25"                              # the share code layout of rounds 74-75 (tests/test_rando_sharecode.py)
VECTORS = os.path.join(ROOT, "tests", "rando_sharecode_vectors.json")


class VersionRowTests(unittest.TestCase):
    """Round 75b (docs/SEED_GUARANTEES_PLAN.md section 5; the plan says round 79): the hidden version row."""

    def setUp(self):
        self.rows = new_rows()
        self.by = {r["key"]: r for r in self.rows}
        self.row = self.by[IG.VERSION_KEY]
        self.v = str(IG.rando_version())

    def test_the_version_is_the_code_parts(self):
        try:
            import guarantees as G
        except ImportError:
            self.assertEqual(IG.rando_version(), 2)
            self.skipTest("tools/randomizer/guarantees.py is not there yet: the page uses version 2")
        self.assertEqual(IG.rando_version(), G.RANDO_VERSION)
        self.assertEqual(G.RANDO_VERSION, 2)

    def test_the_row_is_hidden_fixed_one_choice_and_has_no_flag(self):
        r = self.row
        self.assertEqual((r["kind"], r["choices"], r["default"], r["all"]), ("choice", [self.v], self.v, self.v))
        self.assertTrue(r["hidden"] and r["fixed"])
        for k in ("flag", "page_only", "omit_default", "drives", "section"):
            self.assertNotIn(k, r)
        self.assertNotIn(IG.VERSION_KEY, IG.PAGE)
        self.assertNotIn(IG.VERSION_KEY, IG.ARG_ORDER)

    def test_answered_and_the_run_id_changes(self):
        vals = IG.page_restore(self.rows, {"randomizer": True, "seed": "v1"})
        a = IG.page_answers(self.rows, vals)
        self.assertEqual(a[IG.VERSION_KEY], self.v)
        self.assertIn(f'"rando_version":"{self.v}"', IG.answer_text(a))
        old = {k: x for k, x in a.items() if k != IG.VERSION_KEY}
        self.assertNotEqual(IG.run_id(a), IG.run_id(old))
        self.assertNotEqual(IG.run_id(a, "seal"), IG.run_id(old, "seal"))
        self.assertEqual(IG.page_answers(self.rows, dict(vals, randomizer=False)), {"randomizer": False})

    def test_hoshido73_gets_a_new_run_and_keeps_its_old_one(self):
        self.assertEqual(IG.run_id(HOSHIDO73), HOSHIDO73_RUN, "the saved answer still names its own folder")
        a = IG.page_answers(self.rows, IG.page_restore(self.rows, HOSHIDO73))
        self.assertEqual(a, dict(HOSHIDO73, **{IG.VERSION_KEY: self.v}))
        self.assertNotEqual(IG.run_id(a), HOSHIDO73_RUN)
        if self.v == "2":
            self.assertEqual(IG.run_id(a), HOSHIDO73_RUN_V2)
        self.assertEqual(IG.make_args(a), IG.make_args(HOSHIDO73), "the make command is the same")
        on_disk = os.path.join(ROOT, "build", "r73", "seed", "check", "runs", "fates", HOSHIDO73_RUN, "options.json")
        if os.path.isfile(on_disk):
            with open(on_disk, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), HOSHIDO73)

    def test_a_restored_old_answer_gets_the_current_version(self):
        for last in ({"randomizer": True}, {"randomizer": True, IG.VERSION_KEY: "1"},
                     {"randomizer": True, IG.VERSION_KEY: 1}, {"randomizer": True, IG.VERSION_KEY: "3"}):
            for game in E.legs(self, (None, "seal")):
                vals = IG.page_restore(self.rows, last, game)
                self.assertEqual(vals[IG.VERSION_KEY], self.v, (last, game))
                self.assertEqual(IG.page_answers(self.rows, vals, game)[IG.VERSION_KEY], self.v)
        # a form value that does not fit (the page never holds one) is still answered at the version
        self.assertEqual(IG.page_answers(self.rows, {"randomizer": True, "seed": "x", IG.VERSION_KEY: "1"})
                         [IG.VERSION_KEY], self.v)

    def test_not_in_randomize_everything_and_no_preset_touches_it(self):
        for game in E.legs(self, (None, "seal")):
            vals = IG.page_restore(self.rows, {"seed": "ev"}, game)
            out, turned = IG.page_everything(self.rows, vals, game)
            self.assertEqual(out[IG.VERSION_KEY], self.v)
            self.assertNotIn(self.row["label"], turned)
            for p in IG.PRESETS:
                self.assertNotIn(IG.VERSION_KEY, p["values"])
                self.assertEqual(IG.page_preset(self.rows, vals, p["name"], game)[IG.VERSION_KEY], self.v)

    def test_no_command_line_flag(self):
        a = IG.page_answers(self.rows, IG.page_restore(self.rows, {"randomizer": True, "seed": "f1"}))
        args = IG.make_args(a)
        self.assertFalse(any("version" in x for x in args), args)
        out = io_run(lambda: load_rando().main(["make", "--help"]))
        self.assertIn("--seed", out)
        self.assertNotIn("rando-version", out)
        self.assertNotIn("rando_version", out)

    def test_old_share_codes_are_refused(self):
        import sharecode as S
        live = S.layout(self.rows)
        self.assertNotEqual(live, R74_LAYOUT, "the version row changes the layout")
        old_rows_ = [r for r in self.rows if r["key"] != IG.VERSION_KEY]
        self.assertEqual(S.layout(old_rows_), R74_LAYOUT, "without the row: the round-74 page")
        self.assertEqual(S.body_length(self.rows), S.body_length(old_rows_), "a one-choice row takes 0 bits")
        self.assertEqual(S.width(self.row), 0)
        vals = IG.page_restore(old_rows_, {"randomizer": True, "music": "maps"})
        for game in E.legs(self, ("fates", "seal")):
            old_code = S.encode(old_rows_, vals, "old74", game)
            with self.assertRaises(S.ShareCodeError) as e:
                S.decode(self.rows, old_code, game)
            self.assertEqual(e.exception.kind, "layout")
            self.assertEqual(str(e.exception), "This code was made by another version of the randomizer.")
            new_code = S.encode(self.rows, vals, "new75b", game)
            self.assertEqual(S.decode(self.rows, new_code, game)[0][IG.VERSION_KEY], self.v)

    def test_width0_vectors(self):
        import sharecode as S
        with open(VECTORS, encoding="utf-8") as fh:
            w = json.load(fh)["width0"]
        rows = w["rows"]
        one = [r for r in S.share_rows(rows) if r["kind"] == "choice" and len(r["choices"]) == 1]
        self.assertEqual([r["key"] for r in one], [IG.VERSION_KEY])
        self.assertEqual(S.width(one[0]), 0)
        self.assertEqual(S.layout_text(rows), w["layout_text"])
        self.assertEqual(S.layout(rows), w["layout"])
        for g in w["good"]:
            with self.subTest(g["note"]):
                self.assertEqual(S.encode(rows, g["values"], g["seed"], g["game"]), g["code"])
                values, seed = S.decode(rows, g["code"], g["game"])
                self.assertEqual(seed, g["seed"])
                self.assertEqual(values, {r["key"]: g["values"].get(r["key"], r["default"])
                                          for r in S.share_rows(rows)})
        for b in w["bad"]:
            with self.subTest(b["note"]):
                with self.assertRaises(S.ShareCodeError) as e:
                    S.decode(rows, b["code"], b["game"])
                self.assertEqual((e.exception.kind, str(e.exception)), (b["error"], b["message"]))


class CheckOldFolderTests(unittest.TestCase):
    """Round 75b: rando.py check on a folder made before the guarantees says so plainly and exits 3."""

    def test_folder_version(self):
        rando = load_rando()
        self.assertEqual(rando.folder_version({"seed": "x"}), 1)
        self.assertEqual(rando.folder_version({"seed": "x", "guarantees": {"version": 1}}), 2)
        self.assertEqual(rando.folder_version({"seed": "x", "rando_version": 2}), 2)
        self.assertEqual(rando.folder_version({"seed": "x", "rando_version": "2"}), 2)
        self.assertEqual(rando.folder_version({"seed": "x", "rando_version": "nonsense"}), 0)

    def test_check_refuses_a_version_1_folder(self):
        import tempfile
        rando = load_rando()
        top = os.path.join(ROOT, "build")
        os.makedirs(top, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=top) as t:
            d = os.path.join(t, "Rando-old74")
            os.makedirs(d)
            with open(os.path.join(d, "plan.json"), "w", encoding="utf-8") as fh:
                json.dump({"seed": "old74", "switches": {}, "tool": "rando-slice1-v1"}, fh)
            out = io_run(lambda: self.assertEqual(rando.main(["check", d]), 3))
            now = rando.rando_version()
            self.assertIn(f"made by randomizer 1 (before round 75b); this tool makes randomizer {now}, so a remake "
                          f"would differ", out)
            self.assertNotIn("FAIL", out)
            self.assertNotIn("Traceback", out)

    def test_mark_version_adds_only_what_is_missing(self):
        rando = load_rando()
        now = rando.rando_version()
        plan = {"seed": "m1", "guarantees": {"version": 1, "needs": []}}
        files = {"plan.json": (json.dumps(plan, indent=1, ensure_ascii=False, sort_keys=True) + "\n").encode(),
                 "mod.json": (json.dumps({"title": "Rando-m1", "randomizer": {"seed": "m1"}}, indent=2) + "\n")
                 .encode()}
        p2, f2 = rando._mark_version(dict(plan), files)
        self.assertEqual(p2["rando_version"], now)
        pj, mj = json.loads(f2["plan.json"]), json.loads(f2["mod.json"])
        self.assertEqual(pj["rando_version"], now)
        self.assertEqual(mj["randomizer"], {"seed": "m1", "rando_version": now, "guarantees": plan["guarantees"]})
        _p3, f3 = rando._mark_version(p2, f2)
        self.assertEqual(f3, f2, "a second pass changes no byte")


def io_run(fn) -> str:
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            fn()
        except SystemExit:
            pass
    return buf.getvalue()


if __name__ == "__main__":
    unittest.main()
