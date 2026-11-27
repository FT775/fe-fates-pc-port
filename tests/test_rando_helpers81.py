"""Round 81 (A3, docs/ROUND81_PLAN.md; HOME_DESIGN 6): the "New Game defaults" rows are not randomizer rows. Host
tests, no game run.

- `rando.py schema` (the page's rows, sections, help and presets) names no New Game key and no New Game word: the
  four rows (Battle animations, Map speed, Enemy turn skip, HP bars) live in Zakuro's settings.toml
  (`[fates_helpers]`, patch 0039), never in an answer, a run id, a share code or a `rando.py make` flag;
- the share layout and its row count stay the ones test_rando_helpers80 pins (CE, 57 rows: round 75b's layout,
  unchanged since; round 81 adds no row), so every share code made before round 81 still works;
- the seed fingerprints row stays green: the quick-guard list still runs it, and no announced seed change names a
  New Game row (no row is a seed input; the real check is the gate's `test_seed_fingerprints.RealCheck`);
- the robot's sandbox settings writer (tools/harness/helpers_settings.py) knows exactly the program's words for the
  four rows, writes only below build/, refuses a word the program does not know, and passes its self-test;
- the page robot's `newgame` verdict (tools/harness/pagebot.py judge_newgame) passes its self-test, planted failures
  included (a missing key, a key left set, the real file's hash changed).
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
import ingame as IG  # noqa: E402
import sharecode as S  # noqa: E402

NEW_KEYS = {"battle_animations", "map_speed", "enemy_skip", "hp_bars", "danger_zone", "new_game_defaults"}
NEW_WORDS = ("new game defaults", "for every new game", "enemy turn skip", "map speed", "hp bars",
             "battle animations")
LAYOUT_BEFORE_R81 = "CE"      # tests/test_rando_sharecode.py LIVE_LAYOUT (round 75b), = test_rando_helpers80
SHARE_ROWS_BEFORE_R81 = 57
# zakuro-core fates_helpers.rs (patch 0039): the settings words of each row, Game's choice first
PROGRAM_WORDS = {
    "battle_animations": ("game", "off", "on"),
    "map_speed": ("game", "normal", "fast", "fast_while_a"),
    "enemy_skip": ("game", "off", "move", "all"),
    "hp_bars": ("game", "off", "on"),
}


def harness_module(name: str):
    """a tools/harness module by its path (tools/harness is never put on sys.path: its build.py would shadow
    tools/build.py for other tests in the same process)"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"r81_{name}", os.path.join(ROOT, "tools", "harness", name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rando_schema() -> dict:
    """the exact text the page reads: `rando.py schema`"""
    import importlib.util
    # tools/randomizer/rando.py by its path (ingame puts tools/play, which has its own rando.py, on the path)
    spec = importlib.util.spec_from_file_location("rando_r81_schema", os.path.join(ROOT, "tools", "randomizer",
                                                                                  "rando.py"))
    rando = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rando)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rando.main(["schema"])
    return json.loads(buf.getvalue())


class NewGameRowsAreNotRandomizerRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = rando_schema()
        cls.rows = cls.schema["rows"]

    def test_no_new_game_key_or_word_in_the_schema(self):
        keys = {r["key"] for r in self.rows}
        self.assertFalse(keys & NEW_KEYS, keys & NEW_KEYS)
        for r in self.rows:
            words = " ".join(str(r.get(k, "")) for k in ("label", "section", "help")).lower()
            for w in NEW_WORDS:
                self.assertNotIn(w, words, r["key"])
        for p in self.schema.get("presets", []):
            self.assertFalse(set(p.get("values", {})) & NEW_KEYS, p.get("name"))
            words = " ".join(str(p.get(k, "")) for k in ("name", "label", "help", "note")).lower()
            for w in NEW_WORDS:
                self.assertNotIn(w, words, p.get("name"))

    def test_the_rows_are_the_ingame_schema(self):
        self.assertEqual([r["key"] for r in self.rows], [r["key"] for r in IG.schema()["rows"]])

    def test_the_share_layout_is_unchanged(self):
        self.assertEqual(len(S.share_rows(self.rows)), SHARE_ROWS_BEFORE_R81)
        self.assertEqual(S.layout(self.rows), LAYOUT_BEFORE_R81, S.layout_text(self.rows))
        for k in NEW_KEYS:
            self.assertNotIn(k + ":", S.layout_text(self.rows))

    def test_an_answer_never_carries_a_new_game_row(self):
        values = {r["key"]: r["default"] for r in self.rows}
        values.update(seed="helpers81", randomizer=True)
        # even form values that (wrongly) carried a row would not reach the answer or the make flags
        values.update(battle_animations="off", map_speed="fast", enemy_skip="all", hp_bars="off")
        answer = IG.page_answers(self.rows, values, None)
        self.assertFalse(set(answer) & NEW_KEYS, answer)
        flags = " ".join(IG.make_args(answer)).lower()
        for k in NEW_KEYS:
            self.assertNotIn(k.replace("_", "-"), flags)
            self.assertNotIn(k, flags)


class SeedFingerprintsRow(unittest.TestCase):
    def test_the_quick_guard_list_still_runs_the_fingerprints(self):
        with open(os.path.join(ROOT, "tests", "core.txt"), encoding="utf-8") as fh:
            ids = [ln.split("#", 1)[0].split() for ln in fh]
        self.assertIn(["seed-fingerprints", "tests.test_seed_fingerprints.RealCheck.test_no_seed_changed_without_notice"],
                      ids)

    def test_no_announced_seed_change_names_a_new_game_row(self):
        with open(os.path.join(ROOT, "config", "release", "seed_changes.json"), encoding="utf-8") as fh:
            changes = json.load(fh)
        text = json.dumps(changes.get("changes", [])).lower()
        for w in tuple(NEW_KEYS) + NEW_WORDS:
            self.assertNotIn(w, text)


class RobotTools(unittest.TestCase):
    def test_the_sandbox_writer_knows_the_programs_words(self):
        H = harness_module("helpers_settings")
        self.assertEqual(H.NEW_GAME_ROWS, PROGRAM_WORDS)
        self.assertEqual(list(H.NEW_GAME_ROWS), ["battle_animations", "map_speed", "enemy_skip", "hp_bars"])
        # the program's words, read from the core source (a word renamed there must be renamed here)
        core = os.path.join(ROOT, "engine", "zakuro", "crates", "zakuro-core", "src", "fates_helpers.rs")
        if not os.path.isfile(core):
            # round 85 (plan section 4 item 4): a release copy or a fresh clone has no engine source until
            # `python tools/engine/engine.py fetch` brings it; the two checks above still ran
            self.skipTest("the engine source was not fetched (engine/zakuro/crates/zakuro-core/src/"
                          "fates_helpers.rs is missing; python tools/engine/engine.py fetch brings it), so the "
                          "program's words cannot be read here")
        with open(core, encoding="utf-8") as fh:
            src = fh.read()
        for enum, key in (("BattleAnimations", "battle_animations"), ("MapSpeed", "map_speed"),
                          ("EnemySkip", "enemy_skip"), ("HpBars", "hp_bars")):
            m = re.search(r"\b" + enum + r"\s*\{([^}]*)\}", src)
            self.assertIsNotNone(m, enum)
            words = re.findall(r'=\s*"([a-z_]+)"', m.group(1))
            self.assertEqual(("game", *words), PROGRAM_WORDS[key], enum)

    def test_the_sandbox_writer_flags_and_refusals(self):
        H = harness_module("helpers_settings")
        with contextlib.redirect_stdout(io.StringIO()):
            ok, n = H.selftest()
        self.assertEqual(ok, n)
        self.assertGreaterEqual(n, 40)
        # the command line: one flag per row, the program's words only
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            H.main(["write", os.path.join(H.BUILD, "r81", "py", "_never"), "--map-speed", "warp"])
        self.assertFalse(os.path.exists(os.path.join(H.BUILD, "r81", "py", "_never")))
        # outside build/: refused before anything is written
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SystemExit):
                H.write(t, rows={"enemy_skip": "all"})
            self.assertEqual(os.listdir(t), [])
        text = H.table_text("normal", False, {"battle_animations": "off", "hp_bars": "on"})
        self.assertEqual(text, '[fates_helpers]\nenemy_phase = "normal"\ntrue_hit = false\n'
                               'battle_animations = "off"\nhp_bars = "on"\n')

    def test_the_page_robot_newgame_verdict(self):
        P = harness_module("pagebot")
        self.assertIn("newgame", P.SCENARIOS)
        clicks = [s.get("click") for s in P.SCENARIOS["newgame"] if "click" in s]
        self.assertIn("helpers:newgame:section", clicks)
        for c in clicks:
            if c.startswith("helpers:opt:"):
                key, word = c[len("helpers:opt:"):].split("=")
                self.assertIn(word, PROGRAM_WORDS[key], c)
        self.assertEqual(P.NEWGAME_FILE_ROWS, {"enemy_skip": "all"})
        with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)   # older selftest cases leave files open
            ok, n = P.selftest()
        self.assertEqual(ok, n)


if __name__ == "__main__":
    unittest.main()
