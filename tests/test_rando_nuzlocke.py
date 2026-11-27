"""Self-tests for the randomizer's nuzlocke track (tools/randomizer/nuzlocke.py; docs/rando/NUZLOCKE.md).

    python -m unittest tests.test_rando_nuzlocke          (from the repo root)

Made-up tables and graveyard files under a temp folder (no game data); the last class reads the user's own
extracted RomFS when it is there (skipped otherwise). Nothing here starts the game.
"""
from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
import randolib as R  # noqa: E402
import nuzlocke as NZ  # noqa: E402

N = "JID_無し男"
RULES = R.load_rules()
ARMY = "BID_マイユニット軍"


def job(ix, label, flags=""):
    j = {"index": str(ix), "label": label, "flags": flags, "mjid_name": "MJID_" + label}
    return j


def person(ix, label, jid, flags="", belong=ARMY):
    return {"index": str(ix), "label": label, "flags": flags, "belong": belong, "job": jid, "job_low": N,
            "child_id": "65535", "mpid_name": "MPID_" + label}


def fake_facts():
    jobs = [job(0, N), job(1, "JID_ダークプリンス男"), job(2, "JID_歌姫女", "SPID_女性|SPID_再行動コマンド"),
            job(3, "JID_ソシアルナイト男")]
    persons = [person(0, "PID_無し", N),
               person(1, "PID_プレイヤー男", "JID_ダークプリンス男", "SPID_主人公|SPID_マムクート"),
               person(2, "PID_アクア", "JID_歌姫女", "SPID_女性"),
               person(3, "PID_A", "JID_ソシアルナイト男"),
               person(4, "PID_B", "JID_ソシアルナイト男"),
               person(5, "PID_DRAGON", "JID_ソシアルナイト男", "SPID_マムクート"),
               person(6, "PID_FOE", "JID_ソシアルナイト男", belong="BID_敵軍")]
    return R.Facts(persons, jobs, [], [], [], RULES, {"MPID_PID_A": "Arden"})


class OptionsAndPlan(unittest.TestCase):
    def setUp(self):
        self.f = fake_facts()

    def test_off_is_no_edits_no_lines_no_rules(self):
        for o in (None, {}, {"nuzlocke": False}, {"nuzlocke": "off", "recruits": "first"}):
            self.assertEqual(NZ.plan_nuzlocke(self.f, "seed", o), ([], []), o)
            self.assertIsNone(NZ.make_rules(self.f, o), o)

    def test_on_never_edits_a_table(self):
        for rec in NZ.RECRUIT_MODES:
            edits, lines = NZ.plan_nuzlocke(self.f, "seed", {"nuzlocke": True, "recruits": rec})
            self.assertEqual(edits, [])
            self.assertTrue(lines and lines[0].startswith("Nuzlocke (rando-nuzlocke-v1): nuzlocke=on"))

    def test_seed_independent_and_rng_untouched(self):
        o = {"nuzlocke": True, "recruits": "first"}
        self.assertEqual(NZ.plan_nuzlocke(self.f, "a", o), NZ.plan_nuzlocke(self.f, "b", o))
        rng, ref = random.Random(7), random.Random(7)
        NZ.plan_nuzlocke(self.f, rng, o)
        self.assertEqual(rng.random(), ref.random())  # nothing drawn: other tracks never move

    def test_bad_options(self):
        with self.assertRaises(R.RandoError):
            NZ.check_opts({"recruits": "seeded"})
        with self.assertRaises(R.RandoError):
            NZ.check_opts({"nuzlocke": "maybe"})
        self.assertTrue(NZ.check_opts({"nuzlocke": "on"})["nuzlocke"])

    def test_mode_check(self):
        on = {"nuzlocke": True}
        self.assertIsNone(NZ.check_mode(NZ.MODE_CLASSIC, on))
        self.assertIn("Casual", NZ.check_mode(NZ.MODE_CASUAL, on))
        self.assertIn("Phoenix", NZ.check_mode(NZ.MODE_PHOENIX, on))
        for m in (0, 1, 2):
            self.assertIsNone(NZ.check_mode(m, {"nuzlocke": False}))

    def test_always_allowed(self):
        aa = {a["pid"]: a["why"] for a in NZ.always_allowed(self.f)}
        self.assertEqual(set(aa), {"PID_プレイヤー男", "PID_アクア", "PID_DRAGON"})
        self.assertEqual(aa["PID_プレイヤー男"], "Corrin (the avatar)")
        self.assertEqual(aa["PID_アクア"], "the singer")
        r = NZ.make_rules(self.f, {"nuzlocke": True, "recruits": "first"})
        self.assertEqual(r["game_over_not_recorded"], ["PID_プレイヤー男"])
        self.assertEqual((r["mode_required"], r["record_force"], r["bench_bit"]), (2, 4, 0x800))
        json.dumps(r)  # the core reads it as JSON

    def test_rules_name_the_army(self):
        """round 61: [key, name] pairs for the core's graveyard (fates_nuzlocke.rs name_of)"""
        r = NZ.make_rules(self.f, {"nuzlocke": True, "recruits": "all"})
        names = dict(map(tuple, r["names"]))
        self.assertIn(NZ.pid_key("PID_プレイヤー男"), names)
        self.assertTrue(all(isinstance(k, str) and isinstance(v, str) and v for k, v in names.items()))
        self.assertEqual(len(names), len(r["names"]), "one pair per person")


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = fake_facts()

    def tearDown(self):
        self.tmp.cleanup()

    def new(self, recruits="all", gid="00ab"):
        rules = NZ.make_rules(self.f, {"nuzlocke": True, "recruits": recruits})
        return NZ.Ledger.new_game(NZ.ledger_path(self.tmp.name, gid), gid, "seed1-0badcafe", rules)

    def test_path_and_ids(self):
        p = NZ.ledger_path("D", "ABCDEF01")
        self.assertTrue(p.replace("\\", "/").endswith("rando/0004000000179800/nuzlocke/abcdef01.json"))
        for bad in ("", "xyz", "../x", "1" * 33):
            with self.assertRaises(R.RandoError):
                NZ.ledger_path("D", bad)
        g = NZ.new_game_id(random.Random(1))
        self.assertEqual(len(g), 16)
        self.assertEqual(g, NZ.new_game_id(random.Random(1)))

    def test_off_has_no_graveyard(self):
        with self.assertRaises(R.RandoError):
            NZ.Ledger.new_game(os.path.join(self.tmp.name, "x.json"), "1", "r", None)

    def test_death_is_written_at_once_and_survives_reload(self):
        led = self.new()
        self.assertTrue(led.on_death("PID_A", "A007", 3, name="Arden"))
        again = NZ.Ledger.load(led.path)  # a reset: the file is already there
        self.assertEqual(again.dead_pids(), ["PID_A"])
        self.assertFalse(again.on_death("PID_A", "A007", 3))  # once only
        self.assertEqual(again.on_load(["PID_A", "PID_B"]), {"kill": ["PID_A"], "bench": []})

    def test_deaths_not_recorded(self):
        led = self.new()
        self.assertFalse(led.on_death("PID_プレイヤー男", "A007", 1))         # Corrin: game over
        self.assertFalse(led.on_death("PID_B", "A007", 1, ends_game=True))   # must-survive: game over
        self.assertFalse(led.on_death("PID_FOE", "A007", 1, player_unit=False))
        self.assertEqual(led.dead_pids(), [])

    def test_dead_unit_joining_again_dies(self):
        led = self.new()
        led.on_death("PID_A", "A008", 2)
        self.assertEqual(led.on_join("PID_A", "A006", "story"), "dead")  # an older save from before it joined

    def test_recruits_all_fields_everyone(self):
        led = self.new("all")
        self.assertEqual([led.on_join(p, "A008") for p in ("PID_A", "PID_B")], ["field", "field"])
        self.assertEqual(led.benched_pids(), [])

    def test_first_recruit_per_chapter(self):
        led = self.new("first")
        self.assertEqual(led.on_join("PID_A", "A008"), "field")
        self.assertEqual(led.on_join("PID_B", "A008"), "bench")
        self.assertEqual(led.on_join("PID_アクア", "A008"), "field")       # the singer: never benched
        self.assertEqual(led.on_join("PID_DRAGON", "A008"), "field")
        self.assertEqual(led.on_join("PID_B", "A009"), "bench")           # first decision stands
        self.assertEqual(led.on_join("PID_B", "A012", forced=True), "field")  # story deploy: that chapter only
        self.assertEqual(led.benched_pids(), ["PID_B"])
        self.assertEqual(led.on_load(["PID_A", "PID_B"]), {"kill": [], "bench": ["PID_B"]})
        led2 = NZ.Ledger.load(led.path)
        self.assertEqual(led2.d["first_recruit"], {"A008": "PID_A"})

    def test_capture_counts_as_chapter_recruit(self):
        led = self.new("first")
        self.assertEqual(led.on_join("PID_FOE", "A010", "capture"), "field")
        self.assertEqual(led.on_join("PID_A", "A010", "story"), "bench")

    def test_forced_story_deploy_does_not_use_the_slot(self):
        led = self.new("first")
        self.assertEqual(led.on_join("PID_A", "A011", forced=True), "field")
        self.assertEqual(led.on_join("PID_B", "A011"), "field")

    def test_benched_unit_that_dies_is_dead_not_benched(self):
        led = self.new("first")
        led.on_join("PID_A", "A008")
        led.on_join("PID_B", "A008")
        led.on_death("PID_B", "A012", 4)
        self.assertEqual(led.benched_pids(), [])
        self.assertEqual(led.on_load(["PID_B"])["kill"], ["PID_B"])

    def test_mode_change_voids(self):
        led = self.new()
        self.assertFalse(led.on_mode_change(NZ.MODE_CLASSIC))
        self.assertTrue(led.on_mode_change(NZ.MODE_CASUAL))
        self.assertFalse(led.on_mode_change(NZ.MODE_PHOENIX))  # once
        self.assertFalse(led.on_death("PID_A", "A009", 1))   # a voided run records no more
        self.assertIn("VOIDED: switched to Casual", led.text())

    def test_two_games_two_graveyards(self):
        a, b = self.new(gid="aa"), self.new(gid="bb")
        a.on_death("PID_A", "A007", 1)
        self.assertEqual(NZ.Ledger.load(b.path).dead_pids(), [])
        c = self.new(gid="aa")  # a new game with that id starts empty
        self.assertEqual(c.dead_pids(), [])

    def test_text_log_and_cli(self):
        led = self.new("first")
        led.on_join("PID_A", "A008", name="Arden")
        led.on_death("PID_A", "A009", 5, name="Arden")
        t = led.text()
        self.assertIn("Graveyard (1):", t)
        self.assertIn("Arden: A009, turn 5 (battle)", t)
        self.assertIn("[dead]", t)
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(NZ.main(["log", led.path]), 0)
        self.assertEqual(out.getvalue(), t)

    def test_wrong_file_refused_and_no_temp_left(self):
        p = os.path.join(self.tmp.name, "other.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"version": 9}, fh)
        with self.assertRaises(R.RandoError):
            NZ.Ledger.load(p)
        led = self.new()
        led.on_death("PID_A", "A007", 1)
        left = [n for n in os.listdir(os.path.dirname(led.path)) if n.startswith(".nuz-")]
        self.assertEqual(left, [])


class RealTables(unittest.TestCase):
    """On the user's own extracted RomFS (read only), when it is there."""

    @classmethod
    def setUpClass(cls):
        import gamedata as GD
        why = GD.available()
        if why:
            raise unittest.SkipTest(f"tables not available: {why}")
        cls.f = GD.load_facts(names=False)

    def test_rules_on_real_tables(self):
        r = NZ.make_rules(self.f, {"nuzlocke": True, "recruits": "first"})
        aa = NZ.always_allowed(self.f)
        whys = {a["why"] for a in aa}
        self.assertIn("Corrin (the avatar)", whys)
        self.assertIn("the singer", whys)
        self.assertTrue(r["game_over_not_recorded"])
        self.assertTrue(set(r["game_over_not_recorded"]) <= set(r["always_allowed"]))
        edits, lines = NZ.plan_nuzlocke(self.f, "anything", {"nuzlocke": True, "recruits": "first"})
        self.assertEqual(edits, [])
        self.assertTrue(any(line.startswith("  Never benched:") for line in lines))


class CoreKeys(unittest.TestCase):
    """Engine round E2: the core keys people by their labels' cp932 bytes (fates_nuzlocke.rs label_key)."""

    def test_pid_key_matches_the_core(self):
        self.assertEqual(NZ.pid_key("PID_A1"), "PID_A1")
        self.assertEqual(NZ.pid_key("PID_A%\""), "PID_A%25%22")
        k = NZ.pid_key("PID_プレイヤー男")
        self.assertEqual(k, "PID_%83v%83%8C%83C%83%84%81[%92j")   # the bytes the game holds, ASCII trail bytes kept
        self.assertEqual(NZ.key_label(k), "PID_プレイヤー男")
        self.assertEqual(NZ.key_label("PID_A1"), "PID_A1")
        self.assertEqual(NZ.key_label("bad%zz"), "bad%zz")


if __name__ == "__main__":
    unittest.main()
