"""Round 62 (F-049) host tests for the randomizer: the growth floor, the one-step weapon ladder by difficulty,
tier-matched boss classes (story bosses included, with the never-change list) and the tougher-bosses boost scaled
by the difficulty (Conquest's chapter-only bosses who join on other routes included, chapter row only).

    python -m unittest tests.test_rando_r62            (from the repo root)

Every test runs on the user's own extracted RomFS (skipped when it is not there): no game data is tracked.
"""
from __future__ import annotations

import copy
import csv
import io
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
sys.path.insert(0, ROOT)
import randolib as R  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _edition as E  # noqa: E402  (round 84: Seal legs run only in the Seal edition)

try:
    import gamedata as GD  # noqa: E402
    NOGAME = GD.available()
except Exception as e:  # noqa: BLE001
    NOGAME = str(e)


def rows_of(data: bytes) -> list[dict]:
    if not data:
        return []
    rd = list(csv.reader(io.StringIO(data.decode("utf-8").lstrip(chr(0xFEFF)))))
    return [dict(zip(rd[0], r)) for r in rd[1:]]


@unittest.skipIf(NOGAME, f"the game's tables are not available: {NOGAME}")
class GrowthFloorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tracks as TR
        import growth as G
        cls.TR, cls.G = TR, G
        cls.facts = GD.load_facts()

    def totals(self, files):
        persons, jobs = self.G.final_rows(self.facts, files)
        out = {}
        for pid in self.G.floor_people(self.facts):
            p = persons[pid]
            j = jobs[p["job"]]
            out[pid] = [R.ival(p[f"growth.{s}"]) + R.ival(j[f"growth.{s}"]) for s in R.STATS]
        return out

    def test_floor_holds_on_every_total(self):
        """20..100 on every total of the army and the children (zeros included) over seeds and option sets that
        push growths to their edges; the guard passes; Move is never written."""
        sets = [({}, {}),
                ({}, {"growth_mode": "full", "growth_min": 0, "growth_max": 125}),
                ({}, {"growth_mode": "delta", "growth_variance": 100, "growth_min": 0, "growth_max": 125,
                      "class_growths": "delta", "class_growth_variance": 50}),
                ({}, {"children": True, "class_growths": "delta", "class_growth_variance": 50}),
                ({"classes": False}, {"growth_mode": "full", "growth_min": 0, "growth_max": 10})]
        for sw, o in sets:
            for seed in ("f1", "f2", "f3"):
                plan, files = self.TR.make_all(self.facts, seed, sw, o)
                self.assertTrue(plan["guards"]["growth: floor 20-100"]["ok"], (sw, o, seed))
                for pid, tot in self.totals(files).items():
                    for s, v in zip(R.STATS, tot):
                        self.assertTrue(20 <= v <= 100, (sw, o, seed, pid, s, v))
                for r in rows_of(files.get("tables/Job.csv")):
                    self.assertNotIn("mov", [k for k, v in r.items() if k == "mov" and v != self.facts.jobs[r["label"]]["mov"]])

    def test_zero_totals_are_raised(self):
        """A stat whose total was 0 (growth min 0, max 0 on every personal growth) ends at 20 (owner: min 20 always)."""
        plan, files = self.TR.make_all(self.facts, "z0", {"classes": False}, {"growth_mode": "full", "growth_min": 0,
                                                                                "growth_max": 0})
        raised = 0
        persons, jobs = self.G.final_rows(self.facts, files)
        for pid in self.G.floor_people(self.facts):
            p = persons[pid]
            if not self.facts.in_scope(self.facts.by_pid[pid]):
                continue                        # the children keep their own growths (no growth mode there)
            for s in R.STATS:
                if R.ival(jobs[p["job"]][f"growth.{s}"]) == 0:
                    self.assertEqual(R.ival(p[f"growth.{s}"]), 20, (pid, s))
                    raised += 1
        self.assertGreater(raised, 0)

    def test_spoiler_and_tables_agree(self):
        """The spoiler's final growth table is the laid Person.csv + Job.csv, person by person."""
        plan, files = self.TR.make_all(self.facts, "agree", {}, {"growth_mode": "full", "growth_min": 0,
                                                                  "class_growths": "delta"})
        sp = files["spoiler.txt"].decode("utf-8")
        table = sp[sp.index("Final growths as laid"):]
        for pid, tot in self.totals(files).items():
            line = next(ln for ln in table.splitlines() if f"[{pid}]" in ln)
            got = [int(x.split("=")[1]) for x in line.split(": ", 1)[1].split()]
            self.assertEqual(got, tot, pid)
        self.assertEqual(json.loads(files["plan.json"])["floor"], plan["floor"])

    def test_growths_off_no_floor(self):
        """Growths not randomized (every growth switch and option off): the files are slice 1's, byte for byte,
        with no floor guard (the original growths stay)."""
        sw = {"growths": False}
        plan, files = self.TR.make_all(self.facts, "nofloor", sw, {})
        base = R.make_plan(self.facts, "nofloor", sw)
        self.assertEqual(files, R.render(self.facts, base))
        self.assertNotIn("growth: floor 20-100", plan["guards"])


@unittest.skipIf(NOGAME, f"the game's tables are not available: {NOGAME}")
class LadderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import enemies as E
        import weapons as W
        cls.E, cls.W = E, W
        cls.t = E.load_tables()
        cls.wv = W.WeaponView(cls.t.f)
        cls.lines = W.ladder_lines(cls.wv)
        cls.refine = W.load_refine()

    def run_w(self, o, seed="l1", extra=None):
        full = dict(o, enemies_edits=[], refine=self.refine, **(extra or {}))
        e, lines = self.W.plan_weapons(self.t, self.W.sub_rng(seed, o), full)
        return e, lines, self.W.check_weapons(self.t, e, full)

    def test_ladders_from_the_tables(self):
        """Twelve ladders (six kinds x two sides), each E -> D -> C -> B, might rising, Rating never falling."""
        f = self.t.f
        self.assertEqual(len(self.lines), 12)
        for key, run in self.lines.items():
            self.assertEqual([f.item_rank(i) for i in run], list(R.RANKS[:4]), key)
            for a, b in zip(run, run[1:]):
                self.assertGreater(self.wv.v(b, "might"), self.wv.v(a, "might"))
                self.assertGreaterEqual(self.W.rating(self.wv, b), self.W.rating(self.wv, a))
                self.assertEqual(f.items[a]["weapon_kind"], f.items[b]["weapon_kind"])     # same line, same side

    def test_per_difficulty(self):
        """Easy forges only (+1); Normal tiers up (else +1 forge); Hard tiers up and forges (+1, else +2); every
        guard passes; no tier step is a sidegrade by the Rating or the might; bosses stay in their own rank."""
        f = self.t.f
        seen = {}
        for diff in ("easy", "normal", "hard"):
            e, _l, g = self.run_w({"enemy_upgrade": 100, "difficulty": diff})
            self.assertTrue(all(v["ok"] for v in g.values()), (diff, {k: v["detail"][:3] for k, v in g.items() if not v["ok"]}))
            tiers = [x for x in e if not "_forge." in x["column"]]
            forges = [x for x in e if "_forge." in x["column"]]
            seen[diff] = (len(tiers), len(forges))
            for x in tiers:
                self.assertEqual(self.W.next_rung(self.lines, x["old"]), x["new"])
                self.assertGreaterEqual(self.W.rating(self.wv, x["new"]), self.W.rating(self.wv, x["old"]))
                self.assertGreater(self.wv.v(x["new"], "might"), self.wv.v(x["old"], "might"))
            by = {}
            for x in forges:
                by.setdefault((x["file"], x["index"], x["column"].split("_forge")[0]), []).append(R.ival(x["new"]) - R.ival(x["old"]))
            tiered = {(x["file"], x["index"], x["column"]) for x in tiers}
            for (fi, ix, col), ds in by.items():
                n = max(ds)
                if diff == "easy":
                    self.assertEqual(n, 1)
                elif diff == "normal":
                    self.assertEqual(n, 1)
                    self.assertNotIn((fi, ix, col), tiered)
                else:
                    self.assertEqual(n, 1 if (fi, ix, col) in tiered else 2)
        self.assertEqual(seen["easy"][0], 0)
        self.assertGreater(seen["normal"][0], 0)
        self.assertEqual(seen["normal"][0], seen["hard"][0])

    def test_kept_weapons_never_move(self):
        """Yato, legendaries, personal and precious weapons, staves, stones and drops: never a new tier nor a forge;
        Killer, Brave and 'effective' weapons only forge."""
        f = self.t.f
        for diff in ("normal", "hard"):
            e, _l, _g = self.run_w({"enemy_upgrade": 100, "difficulty": diff}, extra={"boss_forge": 3,
                                    "boss_rows": __import__("stats").boost_rows(__import__("stats").load_tables(names=False), {"boss_stats": "linear"})})
            by = {(d["file"], R.ival(d["index"])): d for d in self.t.dispos}
            for x in e:
                d = by[(x["file"], x["index"])]
                s = int(x["column"].split("_")[1])
                iid = d[f"item_{s}"]
                self.assertIsNone(self.wv.kept(iid), (x, iid))
                self.assertNotIn(f.item_kind(iid), (f.rules["staff_kind"], f.rules["stone_kind"]))
                self.assertFalse(R.ival(d.get(f"item_{s}_flags", 0)) & 1)
                if not "_forge." in x["column"]:
                    self.assertTrue(self.W.on_ladder(self.lines, iid))

    def test_off_no_dispos_edits(self):
        """Upgrades 0 and no boss forge: no DisposUnit edit at all, whatever the difficulty."""
        for diff in ("easy", "normal", "hard"):
            e, _l, _g = self.run_w({"enemy_upgrade": 0, "difficulty": diff, "stats": True})
            self.assertFalse([x for x in e if x["table"] == "DisposUnit"])

    def test_guard_catches_a_sidegrade_and_a_leap(self):
        e, _l, _g = self.run_w({"enemy_upgrade": 100, "difficulty": "normal"})
        x = next(x for x in e if not "_forge." in x["column"])
        run = next(r for r in self.lines.values() if x["old"] in r)
        f = self.t.f
        leap = [dict(x, new=run[-1])] if run.index(x["old"]) + 2 < len(run) else []
        killer = next(i for i in f.item_list if "ISID_必殺倍率＋" in R.flags(i.get("flags", "")) and f.item_kind(i["label"]) == f.item_kind(x["old"]))
        side = [dict(x, new=killer["label"])]
        for bad in [b for b in (leap, side) if b]:
            g = self.W.check_weapons(self.t, bad, {"enemy_upgrade": 100, "difficulty": "normal", "enemies_edits": []})
            self.assertFalse(g["enemy_upgrades_legal"]["ok"], bad)


@unittest.skipIf(NOGAME, f"the game's tables are not available: {NOGAME}")
class BossTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import enemies as E
        import stats as ST
        cls.E, cls.ST = E, ST
        cls.t = E.load_tables(names=False)
        cls.st = ST.load_tables(names=False)

    def proven_tables(self, chapters):
        """chapters: every boss of these chapters counts as robot-proven (rules boss_classes.proven_bosses)."""
        t = copy.copy(self.t)
        t.boss_proven = {d["pid"] for d in self.t.dispos if self.E.chapter_of(d["file"])[:4] in set(chapters)}
        for k in ("_cand_memo",):
            if hasattr(t, k):
                delattr(t, k)
        return t

    def plan(self, t, seed="b1"):
        o = {"gear": False, "enemy_classes": False, "boss_classes": True, "trees": "own"}
        e, _l = self.E.plan_enemies(t, self.E.track_rng(seed, o), o)
        return e, self.E.run_guards(t, e, o), o

    def test_story_bosses_tier_matched_and_never_list(self):
        chs = sorted({self.E.chapter_of(d["file"])[:4] for d in self.t.dispos})
        t = self.proven_tables(chs)
        f = t.f
        by = {(d["file"], R.ival(d["index"])): d for d in t.dispos}
        story = 0
        for seed in ("b1", "b2", "b3"):
            e, g, _o = self.plan(t, seed)
            self.assertTrue(all(v["ok"] for v in g.values()), {k: v["detail"][:3] for k, v in g.items() if not v["ok"]})
            for x in e:
                self.assertEqual(x["column"], "jid")
                d = by[(x["file"], x["index"])]
                old, new = t.unit_job(d), x["new"]
                jo, jn = f.jobs[old], f.jobs[new]
                self.assertEqual(f.promoted(jo), f.promoted(jn))
                self.assertEqual(f.female(jo), f.female(jn))
                self.assertEqual(R.ival(jo["origin"]), R.ival(jn["origin"]))
                self.assertNotIn(d["pid"], t.boss_never)
                self.assertNotIn(self.E.chapter_of(d["file"])[:4], t.guarded)
                self.assertFalse(t.script_names_classes(d) and t.scripted(d))
                story += bool(t.scripted(d))
        self.assertGreater(story, 0)

    def test_unproven_story_bosses_kept(self):
        """No proven chapter: no story boss changes (only the bosses with no story role, as before)."""
        t = self.proven_tables([])
        e, g, _o = self.plan(t)
        by = {(d["file"], R.ival(d["index"])): d for d in t.dispos}
        self.assertTrue(all(v["ok"] for v in g.values()))
        self.assertFalse([x for x in e if t.scripted(by[(x["file"], x["index"])])])

    def test_never_list_and_guard(self):
        """Garon, Anankos and a possessed royal never change; a hand-made change of one is caught by the guard."""
        t = self.proven_tables(sorted({self.E.chapter_of(d["file"])[:4] for d in self.t.dispos}))
        for pid in ("PID_B028_ボス", "PID_A027_ボス", "PID_C028_ボス"):
            d = next(d for d in t.dispos if d["pid"] == pid and t.out_of_scope(d) is None)
            self.assertIsNotNone(t.boss_class_block(d))
            old = t.unit_job(d)
            other = next(j for j in t.f.jobs if j != old and t.kept_job(j) is None)
            bad = [{"table": "DisposUnit", "file": d["file"], "index": R.ival(d["index"]), "label": d.get("label", ""),
                    "column": "jid", "old": d.get("jid", ""), "new": other}]
            g = self.E.run_guards(t, bad, {"boss_classes": True, "trees": "own"})
            self.assertFalse(g["legal_class_weapons_terrain"]["ok"] and g["only_unscripted_enemies"]["ok"], pid)

    def test_the_singer_never_changes(self):
        """Goal 4 (assemble fix): the singer is on the never-change list, so a boss row of hers keeps its class."""
        self.assertIn("PID_アクア", self.t.boss_never)
        d = {"pid": "PID_アクア", "file": "A010", "index": "0"}
        t = copy.copy(self.t)
        t.is_boss = lambda _d: True
        self.assertIn("singer", t.boss_class_block(d))

    def test_boost_hp_by_difficulty(self):
        """HP +10% x step (rounded up, never past the cap) on every boss row; Conquest's chapter-only army bosses
        get the HP part on their chapter row only; the main Person rows are never written."""
        ST = self.ST
        for diff, step in (("easy", 1), ("normal", 2), ("hard", 3)):
            o = {"boss_stats": "linear", "difficulty": diff}
            e, _l = ST.plan_stats(self.st, "boost", o)
            g = ST.run_guards(self.st, e, o)
            self.assertTrue(all(v["ok"] for v in g.values()), (diff, {k: v["detail"][:3] for k, v in g.items() if not v["ok"]}))
            army = [x for x in e if x["table"] == "PersonChapter" and self.st.is_army_boss(
                next(r for r in self.st.pc if r["file"] == x["file"] and R.ival(r["index"]) == x["index"]))]
            self.assertTrue(army, diff)
            for x in army:
                self.assertEqual(x["cell"], "base.hp")
                self.assertTrue(x["file"].replace("\\", "/").split("/")[-1].startswith("B"))
                r = next(r for r in self.st.pc if r["file"] == x["file"] and R.ival(r["index"]) == x["index"])
                want = ST.with_hp(self.st, r, [R.ival(r["base.hp"])], ST.hp_boost(self.st, r, step))[0]
                self.assertEqual(R.ival(x["new"]), want)
            self.assertFalse([x for x in e if x["table"] == "Person"])

    def test_boss_forge_by_difficulty(self):
        """The weapon part: forge levels whose added might reaches the step (refine table), on boss weapons only."""
        import weapons as W
        rows = self.ST.boost_rows(self.st, {"boss_stats": "linear"})
        refine = W.load_refine()
        t = self.E.load_tables()
        wv = W.WeaponView(t.f)
        for step in (1, 2, 3):
            o = {"boss_forge": step, "difficulty": "normal"}
            full = dict(o, enemies_edits=[], boss_rows=rows, refine=refine)
            e, _l = W.plan_weapons(t, W.sub_rng("bf", o), full)
            g = W.check_weapons(t, e, full)
            self.assertTrue(all(v["ok"] for v in g.values()), {k: v["detail"][:3] for k, v in g.items() if not v["ok"]})
            self.assertTrue(e)
            by = {(d["file"], R.ival(d["index"])): d for d in t.dispos}
            for x in e:
                self.assertIn("_forge.", x["column"])
                d = by[(x["file"], x["index"])]
                self.assertIn((self.E.chapter_of(d["file"])[:4], d["pid"]), {(a[:4], b) for a, b in rows})
                s = int(x["column"].split("_")[1])
                iid = d[f"item_{s}"]
                cur, new = R.ival(x["old"]), R.ival(x["new"])
                gain = W.refine_might(refine, wv.v(iid, "refine_index"), new) - W.refine_might(refine, wv.v(iid, "refine_index"), cur)
                self.assertTrue(gain >= step or new == W.FORGE_TOP, (x, gain))


@unittest.skipIf(NOGAME, f"the game's tables are not available: {NOGAME}")
class PageTests(unittest.TestCase):
    def test_rows(self):
        import ingame as IG
        rows = {r["key"]: r for r in IG.schema()["rows"]}
        self.assertEqual(rows["difficulty"]["choices"], ["easy", "normal", "hard"])
        self.assertEqual(rows["difficulty"]["default"], "normal")
        # round 62b (F-049 addendum): the row does not exist on the Seal page (hide_for, no longer grey_for)
        with self.subTest(game="seal"):
            E.need_seal(self)
            self.assertEqual(rows["children"]["hide_for"], {"seal": "no child in Seal of Flames"})
        self.assertTrue(rows["upgrade_rank"].get("fixed"))
        args = IG.make_args({"seed": "p1", "difficulty": "hard"})
        self.assertEqual(args[args.index("--difficulty") + 1], "hard")


if __name__ == "__main__":
    unittest.main()
