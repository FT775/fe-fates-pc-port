"""Self-tests for the randomizer's stats track (tools/randomizer/stats.py; docs/rando/STATS.md).

    python -m unittest tests.test_rando_stats          (from the repo root)

Made-up tables first (no game values); the last class runs on the user's own extracted RomFS when it is there
(skipped otherwise): 50 seeds with everything on through every guard, and the mods tool accepts the folder.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
import randolib as R  # noqa: E402
import stats as S  # noqa: E402

SEEDS = [f"st{i}" for i in range(50)]
ARMY = "BID_マイユニット軍"
ALL_ON = {"class_growths": "delta", "class_growth_variance": 20, "class_bases": "delta", "class_base_variance": 3,
          "enemy_growths": "scaling", "enemy_buff": 50, "enemy_levels": 5, "boss_stats": "ease", "boss_max_boost": 10,
          "boss_variance": 3}
MODES = [{"class_growths": "delta"}, {"class_growths": "delta", "class_growth_variance": 50, "class_growth_max": 30},
         {"class_growths": "delta", "class_growth_variance": 0},
         {"class_bases": "delta"}, {"class_bases": "delta", "class_base_variance": 5},
         {"enemy_growths": "flat"}, {"enemy_growths": "flat", "enemy_buff": 100}, {"enemy_growths": "scaling"},
         {"enemy_growths": "scaling", "enemy_buff": 0},
         {"enemy_levels": 1}, {"enemy_levels": 5},
         {"boss_stats": "linear"}, {"boss_stats": "ease", "boss_max_boost": 20}, {"boss_stats": "linear", "boss_max_boost": 1, "boss_variance": 5},
         {"boss_variance": 2}, ALL_ON]


def job(ix, label, *, promoted=False, pair="", base=3, hp=18, growth=10, eg=40, mx=30, flags=""):
    f = [x for x in (flags, "SPID_上級職" if promoted else "") if x]
    j = {"index": str(ix), "label": label, "flags": "|".join(f), "gender_pair": pair, "mjid_name": "MJID_" + label}
    for n, s in enumerate(R.STATS):
        j[f"base.{s}"] = str(hp if s == "hp" else base + n % 2)
        j[f"growth.{s}"] = str(growth + 5 * (n % 3))
        j[f"enemy_growth.{s}"] = str(eg + 5 * (n % 4))
        j[f"max.{s}"] = str(mx + (30 if s == "hp" else 0))
    return j


def prow(file, ix, label, jid, *, kind="0", level=5, base=2, mpid=None, belong="BID_敵"):
    r = {"file": f"GameData/Person/{file}.bin.lz", "index": str(ix), "label": label, "job": jid, "unit_kind": kind,
         "level": str(level), "mpid_name": mpid or ("MPID_" + label), "belong": belong}
    for n, s in enumerate(R.STATS):
        r[f"base.{s}"] = str(base + n % 3)
        r[f"limit_mod.{s}"] = "0"
    return r


def disp(file, ix, pid, team):
    return {"file": f"GameData/Dispos/{file}.bin.lz", "index": str(ix), "pid": pid, "team": str(team)}


def fake_tables(**kw) -> S.StatsTables:
    jobs = [job(0, "JID_無し男"),
            job(1, "JID_剣士男", pair="JID_剣士女"), job(2, "JID_剣士女", pair="JID_剣士男"),
            job(3, "JID_剣聖男", promoted=True, base=8, hp=24, growth=15),
            job(4, "JID_重騎士男", base=10, hp=22, mx=40, eg=60),
            job(5, "JID_魔戦士男", base=9),                   # excluded (downloadable): never written
            job(6, "JID_大将男", promoted=True, base=12, hp=26, mx=35, eg=125)]
    persons = [{"index": "0", "label": "PID_無し", "belong": "BID_無し", "mpid_name": ""},
               {"index": "1", "label": "PID_HERO", "belong": ARMY, "mpid_name": "MPID_HERO"},
               {"index": "2", "label": "PID_TURNCOAT", "belong": ARMY, "mpid_name": "MPID_TURNCOAT"}]
    pc = [prow("A002", 0, "PID_A002_ボス", "JID_剣士男", kind="2", base=3),
          prow("A002", 1, "PID_A002_兵", "JID_剣士男", level=3),
          prow("A002", 2, "PID_A002_味方", "JID_剣士女", level=4),           # placed by an ally army
          prow("A/A010", 0, "PID_A010_ボス", "JID_剣聖男", kind="2", base=6),
          prow("A/A010", 1, "PID_A010_兵", "JID_剣聖男", level=8),            # promoted, below the 10/11 gate
          prow("A/A010", 2, "PID_A010_兵2", "JID_剣聖男", level=12),
          prow("A/A010", 3, "PID_A010_TURN", "JID_剣士男", kind="2", mpid="MPID_TURNCOAT"),   # joins later
          prow("A/A020", 0, "PID_A020_ボス", "JID_大将男", kind="2", base=20),
          prow("A/A020", 1, "PID_A020_兵", "JID_重騎士男", level=19),
          prow("A/A020", 2, "PID_A020_DLC", "JID_魔戦士男", level=10),
          prow("A/A028", 0, "PID_A028_ボス", "JID_大将男", kind="2", base=2),
          prow("A/A028", 1, "PID_A028_NAMED", "JID_重騎士男", kind="2"),       # unit_kind 2, enemy team only
          prow("A000", 0, "PID_A000_ボス", "JID_剣士男", kind="2"),            # story position 0
          prow("X003", 0, "PID_X003_ボス", "JID_重騎士男", kind="2"),          # paralogue: 0.5 by default
          prow("X003", 1, "PID_X003_兵", "JID_重騎士男", kind="3", level=7)]   # unit_kind 3: no level change
    dispos = [disp("A002", 0, "PID_A002_ボス", 1), disp("A002", 1, "PID_A002_兵", 1), disp("A002", 2, "PID_A002_兵", 1),
              disp("A002", 3, "PID_A002_味方", 2), disp("A/A010", 0, "PID_A010_ボス", 1),
              disp("A/A010", 1, "PID_A010_兵", 1), disp("A/A010E", 0, "PID_A010_兵2", 1),
              disp("A/A010", 2, "PID_A010_TURN", 1), disp("A/A020", 0, "PID_A020_ボス", 1),
              disp("A/A020", 1, "PID_A020_兵", 1), disp("A/A020", 2, "PID_A020_DLC", 1),
              disp("A/A028", 0, "PID_A028_ボス", 1), disp("A/A028", 1, "PID_A028_NAMED", 1),
              disp("A000", 0, "PID_A000_ボス", 1), disp("X003", 0, "PID_X003_ボス", 1), disp("X003", 1, "PID_X003_兵", 1)]
    return S.StatsTables(persons, pc, jobs, dispos, R.load_rules(), {}, **kw)


def by_cell(edits):
    return {(e["table"], e.get("file", ""), e["label"], e["cell"]): e for e in edits}


class StatsTrackTests(unittest.TestCase):
    def setUp(self):
        self.t = fake_tables()

    def test_off_is_no_edits(self):
        for seed in SEEDS:
            self.assertEqual(S.plan_stats(self.t, seed, {}), ([], []))
            self.assertEqual(S.plan_stats(self.t, seed, dict(S.DEFAULT_OPTS)), ([], []))
            self.assertEqual(S.plan_stats(self.t, seed, {"enemy_growths": "off", "enemy_buff": 90}), ([], []))
        self.assertEqual(S.edits_to_files(self.t, []), {})
        self.assertTrue(all(v["ok"] for v in S.run_guards(self.t, [], {}).values()))

    def test_every_mode_passes_every_guard_over_50_seeds(self):
        for opts in MODES:
            total = 0
            for seed in SEEDS:
                edits, lines = S.plan_stats(self.t, seed, opts)
                g = S.run_guards(self.t, edits, opts)
                self.assertTrue(all(v["ok"] for v in g.values()), (opts, seed, {k: v for k, v in g.items() if not v["ok"]}))
                total += len(edits)
                for e in edits:
                    self.assertNotEqual(e["old"], e["new"])
                    self.assertNotIn("JID_魔戦士", e["label"])          # excluded class row
                    self.assertNotEqual(e["label"], "JID_無し男")
                    self.assertNotIn(e["label"], ("PID_A002_味方", "PID_A010_TURN", "PID_X003_兵", "PID_A020_DLC"))
            if opts in ({"class_growths": "delta", "class_growth_variance": 0}, {"enemy_growths": "scaling", "enemy_buff": 0}):
                self.assertEqual(total, 0, opts)
            else:
                self.assertGreater(total, 0, opts)

    def test_same_seed_same_edits_and_parts_independent(self):
        for seed in SEEDS[:10]:
            a = S.plan_stats(self.t, seed, ALL_ON)
            self.assertEqual(a, S.plan_stats(fake_tables(), seed, ALL_ON))
            for part in ({"class_growths": "delta", "class_growth_variance": 20},
                         {"class_bases": "delta", "class_base_variance": 3}):
                alone = S.plan_stats(self.t, seed, part)[0]
                kind = "growth." if "class_growths" in part else "base."
                mine = [e for e in a[0] if e["table"] == "Job" and e["cell"].startswith(kind)]
                # a different option text changes the stream on purpose (like the growth track); same text, same draw
                self.assertEqual(S.plan_stats(self.t, seed, part)[0], alone)
                self.assertTrue(all(e["table"] == "Job" for e in alone))
                self.assertTrue(mine)

    def test_class_growths_bounds_and_pairs(self):
        for seed in SEEDS:
            for opts in ({"class_growths": "delta"}, {"class_growths": "delta", "class_growth_variance": 50, "class_growth_max": 30}):
                o = S.check_opts(opts)
                edits, _ = S.plan_stats(self.t, seed, opts)
                c = by_cell(edits)
                for s in R.STATS:
                    m = c.get(("Job", "", "JID_剣士男", f"growth.{s}"))
                    f = c.get(("Job", "", "JID_剣士女", f"growth.{s}"))
                    self.assertEqual(m and m["new"], f and f["new"], (seed, s))     # the pair shares the draw
                for e in edits:
                    v = int(e["new"])
                    self.assertEqual(v % 5, 0)
                    self.assertTrue(0 <= v <= max(o["class_growth_max"], int(e["old"])), e)
                    self.assertLessEqual(abs(v - int(e["old"])), o["class_growth_variance"])

    def test_class_bases_hp_never_lower_and_within_max(self):
        seen_down = False
        for seed in SEEDS:
            edits, _ = S.plan_stats(self.t, seed, {"class_bases": "delta", "class_base_variance": 5})
            for e in edits:
                j = self.t.jobs[e["label"]]
                s = e["cell"].split(".")[1]
                old, new = int(e["old"]), int(e["new"])
                self.assertTrue(0 <= new <= int(j[f"max.{s}"]))
                self.assertLessEqual(abs(new - old), 5)
                if s == "hp":
                    self.assertGreater(new, old)
                elif new < old:
                    seen_down = True
        self.assertTrue(seen_down)

    def test_enemy_growth_formula(self):
        self.assertEqual(S.enemy_growth_new(35, "flat", 10), 45)
        self.assertEqual(S.enemy_growth_new(35, "scaling", 50), 55)      # 52.5 -> steps of 5, half up
        self.assertEqual(S.enemy_growth_new(40, "scaling", 10), 45)      # 44 -> 45
        self.assertEqual(S.enemy_growth_new(120, "flat", 100), 125)      # at most 125
        self.assertEqual(S.enemy_growth_new(125, "flat", 10), 125)
        self.assertEqual(S.enemy_growth_new(-5, "flat", 10), -5)
        self.assertEqual(S.enemy_growth_new(0, "scaling", 100), 0)
        self.assertEqual(S.enemy_growth_new(30, "off", 50), 30)
        edits, _ = S.plan_stats(self.t, "e1", {"enemy_growths": "flat", "enemy_buff": 10})
        c = by_cell(edits)
        self.assertEqual(c[("Job", "", "JID_重騎士男", "enemy_growth.hp")]["new"], "70")
        self.assertNotIn(("Job", "", "JID_大将男", "enemy_growth.hp"), c)    # already 125

    def test_enemy_levels_only_generic_enemies_with_caps(self):
        for add in (1, 3, 5):
            edits, _ = S.plan_stats(self.t, "lv", {"enemy_levels": add})
            got = {e["label"]: (int(e["old"]), int(e["new"])) for e in edits}
            self.assertEqual(got["PID_A002_兵"], (3, 3 + add))
            self.assertEqual(got["PID_A010_兵"], (8, min(8 + add, 10)))         # promoted: stays at or below 10
            self.assertEqual(got["PID_A010_兵2"], (12, 12 + add))               # placed in the A010E variant
            self.assertEqual(got["PID_A020_兵"], (19, 20))                      # never above 20
            for no in ("PID_A002_味方", "PID_X003_兵", "PID_A020_DLC", "PID_A002_ボス", "PID_A028_NAMED"):
                self.assertNotIn(no, got)
            self.assertEqual(S.enemy_level_new(0, 3, False), 0)                 # 0 = not given: left alone

    def test_boss_buff_curve(self):
        self.assertEqual(S.boss_buff_amount("linear", 5, 0.0), 0)
        self.assertEqual(S.boss_buff_amount("linear", 5, 1.0), 5)
        self.assertEqual(S.boss_buff_amount("linear", 5, 0.5), 3)              # ceil(2.5)
        self.assertEqual(S.boss_buff_amount("ease", 5, 0.5), 3)
        self.assertEqual(S.boss_buff_amount("ease", 10, 0.1), 1)
        self.assertEqual(S.boss_buff_amount("off", 10, 0.9), 0)
        for mode in ("linear", "ease"):
            prev = 0
            for k in range(0, 29):
                b = S.boss_buff_amount(mode, 20, k / 28)
                self.assertGreaterEqual(b, prev)
                self.assertLessEqual(b, 20)
                prev = b

    def test_bosses_bounded_and_army_people_never_buffed(self):
        for seed in SEEDS:
            edits, _ = S.plan_stats(self.t, seed, {"boss_stats": "linear", "boss_max_boost": 5})
            got = {}
            for e in edits:
                got.setdefault(e["label"], {})[e["cell"]] = (int(e["old"]), int(e["new"]))
            self.assertNotIn("PID_A010_TURN", got)            # a person who joins the army
            # story start: no buff, no variance; round 62: only the HP boost (10% x the difficulty step, Normal 2)
            self.assertLessEqual(set(got.get("PID_A000_ボス", {})), {"base.hp"})
            self.assertIn("PID_A028_NAMED", got)               # unit_kind 2, enemy team only
            self.assertEqual(got["PID_A028_ボス"]["base.str"], (3, 8))     # last chapter: full boost
            self.assertEqual(got["PID_X003_ボス"]["base.str"], (3, 6))     # paralogue: half (ceil 2.5)
            for lab, cells in got.items():
                r = next(r for r in self.t.pc if r["label"] == lab)
                for cell, (old, new) in cells.items():
                    hb = S.hp_boost(self.t, r, 2) if cell == "base.hp" else 0
                    self.assertTrue(0 < new - old <= 5 + hb, (lab, cell))
            # A020's boss is near the cap: personal + class base never passes class max + limit mod
            r = next(r for r in self.t.pc if r["label"] == "PID_A020_ボス")
            j = self.t.jobs["JID_大将男"]
            for s in R.STATS:
                new = got.get("PID_A020_ボス", {}).get(f"base.{s}", (0, int(r[f"base.{s}"])))[1]
                self.assertLessEqual(new + int(j[f"base.{s}"]),
                                     max(int(r[f"base.{s}"]) + int(j[f"base.{s}"]), int(j[f"max.{s}"])))

    def test_boss_gain_follows_story_position(self):
        """Round W1 (WIRE_56 2c): the old bosses_beatable line could never fail; boss_gain_follows_story recomputes
        each boss's buff from its own chapter and catches a gain above it."""
        edits, _ = S.plan_stats(self.t, "bg1", {"boss_stats": "linear", "boss_max_boost": 5})
        g = S.run_guards(self.t, edits, {"boss_stats": "linear", "boss_max_boost": 5})
        self.assertNotIn("bosses_beatable", g)
        self.assertTrue(g["boss_gain_follows_story"]["ok"])
        r = next(r for r in self.t.pc if r["label"] == "PID_X003_ボス")        # half way: buff 3 of 5
        old = int(r["base.str"])
        bad = [{"table": "PersonChapter", "file": r["file"], "index": int(r["index"]), "label": r["label"],
                "cell": "base.str", "old": str(old), "new": str(old + 5)}]
        g = S.run_guards(self.t, bad, {"boss_stats": "linear", "boss_max_boost": 5})
        self.assertTrue(g["boss_stats_bounded"]["ok"])                      # within max boost ...
        self.assertFalse(g["boss_gain_follows_story"]["ok"])                # ... but not for its story position

    def test_boss_variance_can_lower_but_never_below_floor(self):
        down = False
        for seed in SEEDS:
            edits, _ = S.plan_stats(self.t, seed, {"boss_variance": 5})
            for e in edits:
                d = int(e["new"]) - int(e["old"])
                self.assertTrue(-5 <= d <= 5)
                down |= d < 0
                s = e["cell"].split(".")[1]
                r = next(r for r in self.t.pc if r["label"] == e["label"] and r["file"] == e["file"])
                lo, _hi = S.boss_limits(self.t, r, s)
                self.assertGreaterEqual(int(e["new"]), min(int(e["old"]), lo))
        self.assertTrue(down)

    def test_tables_object_decides_order_and_bosses(self):
        """F-047: a different story (Seal of Flames) passes its own chapter order and boss list."""
        t = fake_tables(chapter_order={"A028": 0.0, "A002": 1.0}, boss_pids={"PID_A002_ボス", "PID_A028_ボス"})
        edits, _ = S.plan_stats(t, "sof", {"boss_stats": "linear", "boss_max_boost": 4})
        labs = {e["label"] for e in edits if e["cell"] != "base.hp"}
        self.assertEqual(labs, {"PID_A002_ボス"})              # A028 now sits at the start: no buff (round 62: HP boost only)
        self.assertTrue(all(v["ok"] for v in S.run_guards(t, edits, {"boss_stats": "linear", "boss_max_boost": 4}).values()))

    def test_guards_catch_bad_edits(self):
        edits, _ = S.plan_stats(self.t, "bad", ALL_ON)
        cases = []
        for e in edits:
            if e["table"] == "Job" and e["cell"].startswith("growth."):
                cases.append(("class_growths_bounded", dict(e, new=str(int(e["old"]) + 3))))
                break
        for e in edits:
            if e["table"] == "Job" and e["cell"].startswith("base."):     # round 62: any class base (the draws moved)
                bad_new = int(e["old"]) - 1 if e["cell"] == "base.hp" else int(e["old"]) + 4
                cases.append(("class_bases_bounded", dict(e, new=str(bad_new))))
                break
        for e in edits:
            if e["cell"].startswith("enemy_growth."):
                cases.append(("enemy_growths_formula", dict(e, new=str(int(e["new"]) + 5))))
                break
        for e in edits:
            if e["cell"] == "level":
                cases.append(("enemy_levels_bounded", dict(e, new=str(int(e["old"]) + 6))))
                break
        for e in edits:
            if e["cell"].startswith("base.") and e["cell"] != "base.hp" and e["table"] == "PersonChapter":
                cases.append(("boss_stats_bounded", dict(e, new=str(int(e["old"]) + 11))))
                break
        cases.append(("only_stat_cells", {"table": "Job", "index": 1, "label": "JID_剣士男", "cell": "mov",
                                          "old": "5", "new": "9"}))
        cases.append(("only_stat_cells", {"table": "PersonChapter", "file": "GameData/Person/A002.bin.lz", "index": 1,
                                          "label": "PID_A002_兵", "cell": "job", "old": "x", "new": "y"}))
        self.assertEqual(len(cases), 7)
        for name, bad in cases:
            g = S.run_guards(self.t, [bad], ALL_ON)
            self.assertFalse(g[name]["ok"], (name, bad))
        g = S.run_guards(self.t, edits, {})
        self.assertFalse(g["off_means_no_edits"]["ok"])

    def test_bad_options_refused(self):
        for bad in ({"class_growths": "full"}, {"enemy_buff": 101}, {"enemy_levels": 6}, {"boss_max_boost": 0},
                    {"boss_stats": "steep"}, {"class_base_variance": "x"}):
            with self.assertRaises(R.RandoError):
                S.check_opts(bad)
        self.assertEqual(S.check_opts({"enemy_buff": "25%"})["enemy_buff"], 25)

    def test_files(self):
        edits, _ = S.plan_stats(self.t, "files", ALL_ON)
        f = S.edits_to_files(self.t, edits)
        self.assertEqual(set(f), {"tables/Job.csv", "tables/PersonChapter.csv"})
        job = f["tables/Job.csv"].decode("utf-8").lstrip("﻿").splitlines()
        self.assertTrue(job[0].startswith("index,label,base."))
        pc = f["tables/PersonChapter.csv"].decode("utf-8").lstrip("﻿").splitlines()
        self.assertTrue(pc[0].startswith("file,index,label,level"))
        self.assertEqual(f, S.edits_to_files(fake_tables(), S.plan_stats(fake_tables(), "files", ALL_ON)[0]))


try:
    import gamedata as GD
    _WHY = GD.available()
except Exception as _e:  # noqa: BLE001
    _WHY = str(_e)


@unittest.skipIf(_WHY, f"the user's own game tables are not here: {_WHY}")
class RealTablesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = S.load_tables(names=False)

    def test_off_is_no_edits(self):
        self.assertEqual(S.plan_stats(self.t, "real0", {}), ([], []))

    def test_50_seeds_every_guard(self):
        for opts in (ALL_ON, {"enemy_growths": "flat"}, {"boss_stats": "linear", "boss_variance": 5},
                     {"class_bases": "delta", "class_base_variance": 5}):
            for seed in SEEDS:
                edits, _ = S.plan_stats(self.t, seed, opts)
                g = S.run_guards(self.t, edits, opts)
                self.assertTrue(all(v["ok"] for v in g.values()), (opts, seed, {k: v for k, v in g.items() if not v["ok"]}))
                self.assertTrue(edits)

    def test_mods_tool_accepts_the_folder(self):
        sys.path.insert(0, os.path.join(ROOT, "tools", "mods"))
        import mods as M
        os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
        with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, "build")) as d:
            folder, guards, edits = S.make_folder("r56test", ALL_ON, os.path.join(d, "mods"), tables=self.t)
            self.assertTrue(all(v["ok"] for v in guards.values()), guards)
            ctx = M.Ctx(mods_dir=os.path.join(d, "mods"), stage_dir=os.path.join(d, "stage"),
                        zakuro_dir=os.path.join(d, "zak"))
            r = M.compute(ctx)
            self.assertFalse(r.errors, r.errors[:5])


if __name__ == "__main__":
    unittest.main()
