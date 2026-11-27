"""Self-tests for the randomizer's character shuffle track (tools/randomizer/recruit.py; docs/rando/RECRUIT.md).

    python -m unittest tests.test_rando_recruit          (from the repo root)

A few pure checks first (the permutation helper, options); the rest runs on the user's own extracted RomFS when
it is there (skipped otherwise): guards R1-R9 plus "weapons usable" over 50 seeds for each of the 16 option sets
(route/any x keep/full x own/slot x autolevel/slot), off = no edits, determinism, the autolevel identity, the
Revelation 9 Hayato placements, the flier guard catching a bad map, and the CLI.
"""
from __future__ import annotations

import contextlib
import io
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
sys.path.insert(0, ROOT)
import randolib as R  # noqa: E402
import recruit as RC  # noqa: E402

SEEDS = [f"r{i}" for i in range(50)]
SAMPLE_SEEDS = ["r0", "r1"]          # round 67: the core test's fixed sample of SEEDS
_T = None


def tables():
    global _T
    if _T is None:
        _T = RC.load_tables()
    return _T


def have_tables() -> bool:
    try:
        import gamedata as G
        return G.available() is None
    except Exception:  # noqa: BLE001
        return False


class Pure(unittest.TestCase):
    def test_permute_is_a_permutation_and_one_stays(self):
        for n in range(1, 9):
            m = [f"P{i}" for i in range(n)]
            for s in range(20):
                got = RC.permute(m, random.Random(s))
                self.assertEqual(sorted(got), m)
                self.assertEqual(sorted(got.values()), m)
        self.assertEqual(RC.permute(["solo"], random.Random(1)), {"solo": "solo"})

    def test_options(self):
        self.assertEqual(RC.check_opts(None), RC.DEFAULT_OPTS)
        self.assertEqual(RC.check_opts({"recruit_look": "keep_face"})["recruit_look"], "keep")
        with self.assertRaises(R.RandoError):
            RC.check_opts({"recruit": "everyone"})
        self.assertEqual(len(RC.all_option_sets()), 16)

    def test_sub_seed_is_stable_and_own(self):
        self.assertEqual(RC.sub_seed("abc"), RC.sub_seed("abc"))
        self.assertNotEqual(RC.sub_seed("abc"), RC.sub_seed("abd"))
        # not the slice-1 key or another track's: the tool name and track name are part of it
        self.assertNotEqual(RC.sub_seed("abc")[:38], "ch" + RC.sub_seed("abc")[:36])


@unittest.skipUnless(have_tables(), "the user's extracted RomFS is not available")
class RealTables(unittest.TestCase):
    def test_off_makes_no_edits(self):
        t = tables()
        for s in SEEDS[:10]:
            e, lines = RC.plan_recruit(t, s, {"recruit": "off", "recruit_look": "full", "recruit_class": "slot"})
            self.assertEqual((e, lines), ([], []))
            self.assertIs(RC.shuffled_facts(t.facts, e), t.facts)
        g = RC.run_guards(t, [], {"recruit": "off"})
        self.assertTrue(g["R8_off_no_edits"]["ok"])

    def test_guards_over_50_seeds_every_option_set(self):
        self._guards_over(SEEDS)

    def test_guards_over_2_seeds_every_option_set(self):
        """Round 67 core sample (the 50-seed test is in tests/heavy.txt): the same guards on a fixed 2 seeds."""
        self._guards_over(SAMPLE_SEEDS)

    def _guards_over(self, seeds):
        t = tables()
        for o in RC.all_option_sets():
            for s in seeds:
                e, _ = RC.plan_recruit(t, s, o)
                g = RC.run_guards(t, e, o)
                bad = {k: v["detail"][:3] for k, v in g.items() if not v["ok"]}
                self.assertEqual(bad, {}, f"{RC.opts_text(RC.check_opts(o))} seed {s}")
                self.assertTrue(e, f"{o} seed {s}: nobody moved")
                # keep the face never carries a full-identity cell or record; full always does
                full = [x for x in e if x.get("look") == "full" or x["table"] in ("FaceData", "Message")]
                if o["recruit_look"] == "keep":
                    self.assertEqual(full, [])
                else:
                    self.assertTrue(full)
                if o["recruit_class"] == "slot":
                    self.assertFalse([x for x in e if x.get("cell") in RC.CLASS_CELLS or x.get("column") == "jid"])

    def test_same_seed_same_plan_and_seeds_differ(self):
        t = tables()
        o = {"recruit": "route"}
        a, la = RC.plan_recruit(t, "same", o)
        b, lb = RC.plan_recruit(t, "same", o)
        self.assertEqual((a, la), (b, lb))
        maps = {tuple(sorted(RC.mapping_of(RC.plan_recruit(t, s, o)[0]).items())) for s in SEEDS[:10]}
        self.assertGreater(len(maps), 5)

    def test_tables_untouched_and_slice1_unmoved(self):
        t = tables()
        before = [dict(p) for p in t.facts.persons], [dict(h) for h in t.handover]
        plan1 = R.make_plan(t.facts, "slice", None)
        RC.plan_recruit(t, "slice", {"recruit": "any", "recruit_look": "full"})
        self.assertEqual(([dict(p) for p in t.facts.persons], [dict(h) for h in t.handover]), before)
        self.assertEqual(R.make_plan(t.facts, "slice", None), plan1)

    def test_shuffled_facts_carry_the_filler(self):
        t = tables()
        e, _ = RC.plan_recruit(t, "view", {"recruit": "route"})
        sf = RC.shuffled_facts(t.facts, e)
        for spot, filler in RC.mapping_of(e).items():
            self.assertEqual(sf.by_pid[spot]["personal_skill.normal"], t.facts.by_pid[filler]["personal_skill.normal"])
            self.assertEqual(sf.by_pid[spot]["growth.str"], t.facts.by_pid[filler]["growth.str"])

    def test_autolevel_identity(self):
        t = tables()
        f = t.facts
        pl, _ = RC.pools(t, "route")
        for members in pl.values():
            for pid in members:
                p = f.by_pid[pid]
                got = RC.autolevel(t, p, p["job"], RC.eff_level(t, p["level"], p["job"]))
                self.assertEqual(got, [R.ival(p[f"base.{s}"]) for s in R.STATS], pid)

    def test_pools_follow_the_rows(self):
        t = tables()
        f = t.facts
        pl, fixed = RC.pools(t, "route")
        pooled = [p for m in pl.values() for p in m]
        self.assertEqual(len(pooled), len(set(pooled)))
        for pid in pooled:
            self.assertNotIn(pid, fixed)
        for pid in t.rules["recruit_hold"] + t.rules["recruit_fixed"]:
            self.assertNotIn(pid, pooled)
        bits = {"A": 1, "B": 2, "C": 4}
        for key, members in pl.items():
            group = key.split("/")[0]
            for pid in members:
                self.assertEqual(f.female(f.by_pid[pid]), key.endswith("/F"))
                if group != "castle":
                    # the route group worked out from the placements equals the Person row's own route mask
                    self.assertEqual(sum(bits[c] for c in group), R.ival(f.by_pid[pid]["support_route"]), pid)
        anyp, _ = RC.pools(t, "any")
        self.assertEqual(sorted(k for k in anyp), ["any/F", "any/M", "castle/F", "castle/M"])

    def test_revelation_9_two_placements_same_filler(self):
        t = tables()
        f = t.facts
        rows = [h for hs in t.variants.values() for h in hs]
        twice = {}
        for d in f.dispos:
            if d["pid"] in {h["label"] for h in rows}:
                twice.setdefault((d["file"], d["pid"]), []).append(d)
        doubles = [k for k, v in twice.items() if len(v) > 1 and "/C/" in k[0]]
        self.assertTrue(doubles, "no route row placed twice in one Revelation chapter")
        for s in SEEDS[:20]:
            e, _ = RC.plan_recruit(t, s, {"recruit": "route"})
            for file, pid in doubles:
                jids = {x["new"] for x in e if x["table"] == "DisposUnit" and x["file"] == file and x["label"] == pid
                        and x["column"] == "jid"}
                self.assertLessEqual(len(jids), 1)
                fl = {x["filler"] for x in e if x.get("label") == pid}
                self.assertLessEqual(len(fl), 1)

    def test_flier_guard_catches_a_bad_map(self):
        t = tables()
        f = t.facts
        o = RC.check_opts({"recruit": "route"})
        joins = RC.spot_joins(t)
        cat = t.rules["flier_job_category"]
        pl, _ = RC.pools(t, "route")
        # every flier spot that joins Revelation before C011 swaps with a non-flier of its pool
        mapping = {p: p for m in pl.values() for p in m}
        for key, members in pl.items():
            fl = [p for p in members if cat in R.flags(f.jobs[f.by_pid[p]["job"]]["category"])
                  and joins.get(p, {}).get("C", 99) < 11]
            ground = [p for p in members if cat not in R.flags(f.jobs[f.by_pid[p]["job"]]["category"])]
            for a, b in zip(fl, ground):
                mapping[a], mapping[b] = b, a
        e = RC.build_edits(t, mapping, o, RC.sub_seed("bad"))
        g = RC.run_guards(t, e, o)
        self.assertFalse(g["R6_flier_before_ninja_doors"]["ok"])
        # and the same map with the spot's own class is fine
        o2 = RC.check_opts({"recruit": "route", "recruit_class": "slot"})
        g2 = RC.run_guards(t, RC.build_edits(t, mapping, o2, RC.sub_seed("bad")), o2)
        self.assertTrue(g2["R6_flier_before_ninja_doors"]["ok"])

    def test_guard_catches_a_cross_sex_or_fixed_swap(self):
        t = tables()
        f = t.facts
        o = RC.check_opts({"recruit": "any"})
        pl, fixed = RC.pools(t, "any")
        m, w = pl["any/M"][0], pl["any/F"][0]
        e = RC.build_edits(t, {m: w, w: m}, o, RC.sub_seed("x"))
        g = RC.run_guards(t, e, o)
        self.assertFalse(g["R4_same_sex"]["ok"])
        self.assertFalse(g["R1_permutation"]["ok"])
        held = t.rules["recruit_hold"][0]
        e = RC.build_edits(t, {held: m, m: held}, o, RC.sub_seed("x"))
        self.assertFalse(RC.run_guards(t, e, o)["R2_fixed_stay"]["ok"])

    def test_cli(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = RC.main(["plan", "--seed", "cli", "--recruit", "route"])
        self.assertEqual(rc, 0)
        self.assertIn("Character shuffle", buf.getvalue())
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stdout(io.StringIO()):
                RC.main(["plan", "--seed", "cli", "--json", os.path.join(ROOT, "docs", "x.json")])


if __name__ == "__main__":
    unittest.main()
