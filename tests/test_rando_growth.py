"""Self-tests for the randomizer's growth track (tools/randomizer/growth.py; docs/rando/GROWTH.md).

    python -m unittest tests.test_rando_growth          (from the repo root)

Made-up tables first (the same small cast as tests/test_randomizer.py); the last class runs on the user's own
extracted RomFS when it is there (skipped otherwise).
"""
from __future__ import annotations

import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
sys.path.insert(0, ROOT)
import randolib as R  # noqa: E402
import growth as G  # noqa: E402
from tests.test_randomizer import fake_facts  # noqa: E402

SEEDS = [f"g{i}" for i in range(50)]
MODES = [{"growths": "redistribute"}, {"growths": "redistribute", "adjust_hp": True, "growth_variance": 100},
         {"growths": "delta"}, {"growths": "delta", "adjust_hp": True, "growth_variance": 10},
         {"growths": "full"}, {"growths": "full", "adjust_hp": True, "growth_min": 0, "growth_max": 125},
         {"growths": "full", "growth_min": 7, "growth_max": 33},
         {"bases": "redistribute"}, {"bases": "redistribute", "base_variance": 10, "scale_to_level": False},
         {"bases": "delta"}, {"bases": "delta", "base_variance": 1},
         {"growths": "full", "bases": "redistribute"}, {"growths": "delta", "bases": "delta"}]


def run(f, seed, opts, switches=None):
    base = R.make_plan(f, seed, switches)
    edits, lines = G.plan_growth(f, seed, dict(opts, base_plan=base))
    return base, edits, lines, G.apply_edits(base, edits, opts)


class GrowthTrackTests(unittest.TestCase):
    def setUp(self):
        self.f = fake_facts()

    def test_default_is_slice1_byte_identical(self):
        for seed in SEEDS:
            for sw in ({}, {"growths": False}, {"trees": "any", "join_stats": False}):
                base, edits, lines, plan = run(self.f, seed, {}, sw)
                self.assertEqual(edits, [])
                self.assertEqual(lines, [])
                self.assertIs(plan, base)
                self.assertEqual(R.render(self.f, plan), R.render(fake_facts(), R.make_plan(fake_facts(), seed, sw)))
                files, plan2, _ = G.build_files(self.f, seed, dict(G.DEFAULT_OPTS), sw)
                self.assertEqual(files, R.render(self.f, R.make_plan(self.f, seed, sw)))

    def test_each_mode_bounds_hold_over_50_seeds(self):
        for opts in MODES:
            o = G.check_opts(opts)
            lo, hi = G.growth_bounds(o)
            changed = 0
            for seed in SEEDS:
                base, edits, lines, plan = run(self.f, seed, opts)
                self.assertEqual(G.check_bounds(self.f, plan, opts), [], (opts, seed))
                changed += len(edits)
                for e in plan["persons"]:
                    p = self.f.by_pid[e["pid"]]
                    og = [R.ival(p[f"growth.{s}"]) for s in R.STATS]
                    ob = [R.ival(p[f"base.{s}"]) for s in R.STATS]
                    if o["growths"] != "slice1":
                        self.assertTrue(all(lo <= g <= hi and g % 5 == 0 for g in e["growth"]), (opts, seed, e))
                        if o["growths"] == "redistribute":
                            self.assertLessEqual(abs(sum(e["growth"]) - sum(og)), o["growth_variance"], (opts, seed))
                        if o["growths"] == "delta":
                            for a, b in zip(og, e["growth"]):
                                self.assertLessEqual(abs(a - b), max(o["growth_variance"], lo - a), (opts, seed))
                            if o["adjust_hp"]:
                                self.assertGreaterEqual(e["growth"][0], og[0])
                    else:
                        self.assertEqual(e["growth"], next(x for x in base["persons"] if x["pid"] == e["pid"])["growth"])
                    if o["bases"] != "slice1":
                        lb, hb = G.base_bounds(self.f, p, e["job"])
                        self.assertTrue(all(lb[n] <= e["base"][n] <= hb[n] for n in range(8)), (opts, seed, e))
                        var = G.base_variance_for(o, G.join_level(self.f, p))
                        if o["bases"] == "redistribute":
                            self.assertLessEqual(sum(e["base"]), sum(ob) + var)
                        if o["bases"] == "delta":
                            for a, b in zip(ob, e["base"]):
                                self.assertLessEqual(abs(a - b), var)
                    # class, weapon exp and items stay exactly slice 1's
                    be = next(x for x in base["persons"] if x["pid"] == e["pid"])
                    self.assertEqual((e["job"], e["job_low"], e["wexp"]), (be["job"], be["job_low"], be["wexp"]))
                self.assertEqual(plan["dispos"], base["dispos"])
                self.assertTrue(all(ed["table"] == "Person" and ed["cell"].split(".")[0] in ("growth", "base")
                                    for ed in edits))
            self.assertGreater(changed, 0, opts)

    def test_full_spread_and_adjust_hp(self):
        vals, hp_plain, hp_adj = set(), [], []
        for seed in SEEDS:
            _, _, _, a = run(self.f, seed, {"growths": "full"})
            _, _, _, b = run(self.f, seed, {"growths": "full", "adjust_hp": True})
            for e in a["persons"]:
                vals |= set(e["growth"])
                hp_plain.append(e["growth"][0])
            hp_adj += [e["growth"][0] for e in b["persons"]]
        self.assertEqual(min(vals), 5)
        self.assertEqual(max(vals), 80)
        self.assertGreater(sum(hp_adj), sum(hp_plain))
        self.assertTrue(all(h >= 5 + 35 for h in hp_adj))

    def test_same_seed_same_edits_other_seed_differs(self):
        for opts in MODES:
            self.assertEqual(run(self.f, "abc", opts)[1], run(fake_facts(), "abc", opts)[1])
            self.assertNotEqual(run(self.f, "abc", opts)[1], run(self.f, "abd", opts)[1], opts)

    def test_own_sub_seed(self):
        """The track's draws depend on the run seed and its own options only: slice 1's switches (which change
        every slice-1 stream) leave the growth draws alone, and a Random gives a stable key too."""
        a = run(self.f, "abc", {"growths": "full"})[3]
        b = run(self.f, "abc", {"growths": "full"}, {"classes": False, "join_stats": False})[3]
        self.assertEqual([e["growth"] for e in a["persons"]], [e["growth"] for e in b["persons"]])
        self.assertNotEqual(G.track_key("abc"), G.track_key("abd"))
        self.assertEqual(G.track_key(random.Random(5)), G.track_key(random.Random(5)))
        g1 = run(self.f, "abc", {"growths": "full", "bases": "delta"})[3]
        g2 = run(self.f, "abc", {"growths": "full", "bases": "redistribute"})[3]
        self.assertEqual([e["growth"] for e in g1["persons"]], [e["growth"] for e in g2["persons"]])

    def test_bad_options_refused(self):
        for bad in ({"growths": "chaos"}, {"bases": "full"}, {"growth_variance": 101}, {"growth_max": 126},
                    {"growth_min": 12, "growth_max": 14, "growths": "full"}, {"base_variance": 0},
                    {"growth_min": "x"}):
            with self.assertRaises(R.RandoError, msg=bad):
                G.check_opts(bad)
        self.assertEqual(G.check_opts({"growth_variance": "40%"})["growth_variance"], 40)

    def test_level_scaling(self):
        o = G.check_opts({"bases": "delta"})
        self.assertEqual(G.base_variance_for(o, 1), 5)
        self.assertEqual(G.base_variance_for(o, 11), 8)
        self.assertEqual(G.base_variance_for(o, 21), 10)
        self.assertEqual(G.base_variance_for(dict(o, scale_to_level=False), 30), 5)
        p = dict(self.f.by_pid["PID_H"], level="4", internal_level="-1")   # promoted class
        self.assertEqual(G.join_level(self.f, p), 24)
        p = dict(p, internal_level="15")
        self.assertEqual(G.join_level(self.f, p), 19)

    def test_spoiler_and_render(self):
        files, plan, lines = G.build_files(self.f, "abc", {"growths": "redistribute", "bases": "delta"})
        text = files["spoiler.txt"].decode("utf-8")
        self.assertIn("Growth track (rando-growth-v1): growths=redistribute variance=30", text)
        self.assertIn("bases=delta variance=5", text)
        self.assertIn("growth", plan["tracks"])
        rows = files["tables/Person.csv"].decode("utf-8-sig").strip().split("\n")
        self.assertEqual(rows[0].split(","), ["index", "label"] + R.PERSON_COLS)


def _real():
    try:
        import gamedata as GD
        return None if GD.available() else GD
    except Exception:  # noqa: BLE001
        return None


GD = _real()


@unittest.skipIf(GD is None, "no extracted RomFS / table layouts here")
class RealDataGrowthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = GD.load_facts()

    def test_real_default_byte_identical(self):
        for seed in ("same", "r47robot", "x1"):
            files, _, _ = G.build_files(self.f, seed, {})
            self.assertEqual(files, R.render(self.f, R.make_plan(self.f, seed)))

    def test_real_modes_bounds_and_slice1_guards(self):
        for opts in MODES:
            for i in range(10):
                _, plan, _ = G.build_files(self.f, f"real{i}", opts)
                self.assertEqual(G.check_bounds(self.f, plan, opts), [], (opts, i))
                g = R.run_guards(self.f, plan)
                for k, v in g.items():
                    if k == "stats_within_caps" and G.check_opts(opts)["bases"] != "slice1":
                        # the only slice-1 rule a bases mode may break on purpose: the total may grow by up to
                        # the variance (FE8 port semantics); every other line of that guard must still hold
                        self.assertTrue(all("total grew" in d for d in v["detail"]), (opts, i, v["detail"][:3]))
                    else:
                        self.assertTrue(v["ok"], (opts, i, k, v["detail"][:3]))


if __name__ == "__main__":
    unittest.main()
