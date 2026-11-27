"""Self-tests for the randomizer's promotions track (tools/randomizer/promotions.py; docs/rando/PROMOTIONS.md).

    python -m unittest tests.test_rando_promotions          (from the repo root)

Made-up tables first (no game data); the last class runs on the user's own extracted RomFS when it is there
(skipped otherwise): many seeds and every option through every guard, and the mods tool accepts the folder.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
import randolib as R  # noqa: E402
import promotions as P  # noqa: E402

try:
    import gamedata as GD  # noqa: E402
    if GD.available():
        GD = None
except Exception:  # noqa: BLE001
    GD = None

N = "JID_無し男"
RULES = R.load_rules()
ON_OPTS = [{"promotions": a, "reclass": b, "sides": c} for a in P.PROMO_MODES for b in P.RECLASS_MODES
           for c in P.SIDE_MODES if (a, b) != ("off", "keep")]


def job(ix, label, *, female=False, promoted=False, promo=(N, N), w=(), gp=N, origin="2", flags="", category=""):
    f = [x for x in (flags, "SPID_女性" if female else "", "SPID_上級職" if promoted else "") if x]
    j = {"index": str(ix), "label": label, "flags": "|".join(f), "category": category, "origin": origin,
         "mjid_name": "MJID_" + label, "promotion.1": promo[0], "promotion.2": promo[1], "gender_pair": gp}
    for s in R.STATS:
        j[f"base.{s}"], j[f"max.{s}"] = "2", "40"
    for k in R.KINDS:
        j[f"max_weapon_exp.{k}"] = "0"
    for k, v in w:
        j[f"max_weapon_exp.{k}"] = str(v)
    return j


def pair(ix, name, **kw):
    """male + female rows of one class (labels JID_<name>男 / 女)."""
    m, fm = f"JID_{name}男", f"JID_{name}女"
    pm = kw.pop("promo", (N, N))
    pf = kw.pop("promo_f", tuple(x[:-1] + "女" if x != N else N for x in pm))
    return [job(ix, m, gp=fm, promo=pm, **kw), job(ix + 1, fm, female=True, gp=m, promo=pf, **kw)]


SW, LA, AX, DA, ST, TO, STONE = "sword", "lance", "axe", "dagger", "staff", "tome", "stone"


def fake_jobs():
    J = [job(0, N)]
    J += [job(1, "JID_ダークプリンス男", promo=("JID_ダークブラッド男", N), w=((SW, 96),), category="JCID_マムクート"),
          job(2, "JID_ダークブラッド男", promoted=True, w=((SW, 161),), category="JCID_マムクート"),
          job(3, "JID_歌姫女", female=True, w=((LA, 51),), flags="SPID_再行動コマンド")]
    J += pair(10, "ソシアルナイト", promo=("JID_パラディン男", "JID_グレートナイト男"), w=((SW, 96), (LA, 96)))
    J += pair(12, "アクスファイター", promo=("JID_バーサーカー男", "JID_ブレイブヒーロー男"), w=((AX, 96),))
    J += pair(14, "マーシナリー", promo=("JID_ブレイブヒーロー男", "JID_剣聖男"), w=((SW, 96),), origin="1")
    J += pair(18, "アーマーナイト", promo=("JID_グレートナイト男", "JID_パラディン男"), w=((LA, 96),))
    J += [job(16, "JID_ロッドナイト男", promo=("JID_ストラテジスト男", "JID_バトラー男"), w=((ST, 96),), gp="JID_ロッドナイト女"),
          job(17, "JID_ロッドナイト女", female=True, promo=("JID_ストラテジスト女", "JID_メイド女"), w=((ST, 96),),
              gp="JID_ロッドナイト男")]
    J += pair(20, "パラディン", promoted=True, w=((SW, 161), (LA, 161)))
    J += pair(22, "グレートナイト", promoted=True, w=((SW, 96), (LA, 161), (AX, 96)))
    J += pair(24, "バーサーカー", promoted=True, w=((AX, 251),))
    J += pair(26, "ブレイブヒーロー", promoted=True, w=((SW, 161), (AX, 96)))
    J += pair(28, "剣聖", promoted=True, w=((SW, 251),), origin="1")
    J += pair(30, "ストラテジスト", promoted=True, w=((TO, 96), (ST, 161)))
    J += [job(32, "JID_バトラー男", promoted=True, w=((DA, 96), (ST, 251)), gp="JID_メイド女"),
          job(33, "JID_メイド女", promoted=True, female=True, w=((DA, 96), (ST, 251)), gp="JID_バトラー男")]
    J += pair(34, "大商人", promoted=True, w=((LA, 96), ("bow", 161)), origin="1")
    J += pair(36, "兵法者", promoted=True, w=((SW, 161), (LA, 96), (AX, 96)), origin="1")
    J += pair(40, "妖狐", promo=("JID_九尾の狐男", N), w=((STONE, 96),), category="JCID_獣|JCID_ラグズ", origin="1")
    J += pair(42, "九尾の狐", promoted=True, w=((STONE, 251),), category="JCID_獣|JCID_ラグズ", origin="1")
    J += pair(44, "村人", promo=("JID_大商人男", "JID_ブレイブヒーロー男"), w=((LA, 51),), origin="1")
    J += [job(50, "JID_魔戦士男", promoted=False, w=((SW, 161),)),
          job(51, "JID_ノスフェラトゥ男", promoted=True, w=((STONE, 161),), flags="SPID_敵専用")]
    return J


def person(ix, label, jid, low, *, flags="", rc=(N, N), belong="BID_マイユニット軍"):
    p = {"index": str(ix), "label": label, "flags": flags, "belong": belong, "job": jid, "job_low": low,
         "child_id": "65535", "mpid_name": "MPID_" + label, "reclass.1": rc[0], "reclass.2": rc[1], "unit_kind": "1"}
    for s in R.STATS:
        p[f"base.{s}"], p[f"growth.{s}"], p[f"limit_mod.{s}"] = "2", "40", "0"
    for k in R.KINDS:
        p[f"weapon_exp.{k}"] = "0"
    return p


def fake_facts():
    persons = [person(0, "PID_無し", N, N),
               person(1, "PID_プレイヤー男", "JID_ダークプリンス男", "JID_ダークブラッド男",
                      flags="SPID_主人公|SPID_マムクート"),
               person(2, "PID_アクア", "JID_歌姫女", N, flags="SPID_女性", rc=("JID_ロッドナイト女", N)),
               person(3, "PID_A", "JID_ソシアルナイト男", "JID_パラディン男", rc=("JID_マーシナリー男", "JID_アクスファイター男")),
               person(4, "PID_B", "JID_グレートナイト男", "JID_ソシアルナイト男", rc=("JID_アクスファイター男", N)),
               person(5, "PID_C", "JID_アクスファイター女", "JID_バーサーカー女", flags="SPID_女性",
                      rc=("JID_ロッドナイト女", N)),
               person(6, "PID_D", "JID_メイド女", "JID_ロッドナイト女", flags="SPID_女性", rc=("JID_マーシナリー女", N)),
               person(7, "PID_E", "JID_ブレイブヒーロー男", "JID_アクスファイター男", rc=("JID_ソシアルナイト男", N)),
               person(8, "PID_FOX", "JID_妖狐男", "JID_九尾の狐男", flags="SPID_ラグズ", rc=("JID_マーシナリー男", N)),
               person(9, "PID_MOZ", "JID_村人女", "JID_大商人女", flags="SPID_女性", rc=("JID_マーシナリー女", N)),
               person(10, "PID_BAD", "JID_ノスフェラトゥ男", N, flags="SPID_敵専用"),
               person(11, "PID_KID", "JID_ソシアルナイト男", "JID_パラディン男", rc=(N, N))]
    persons[11]["child_id"] = "3"
    return R.Facts(persons, fake_jobs(), [], [], [], RULES, {})


def base_plan(f, moves):
    out = []
    for p in f.persons:
        if f.in_scope(p):
            j, low = moves.get(p["label"], (p["job"], p["job_low"]))
            out.append({"pid": p["label"], "job": j, "job_low": low, "old_job": p["job"]})
    return {"persons": out}


def all_ok(g):
    return all(v["ok"] for v in g.values())


class PromotionsTests(unittest.TestCase):
    def setUp(self):
        self.f = fake_facts()

    def test_default_is_no_edits(self):
        self.assertEqual(P.plan_promotions(self.f, "s1", {}), ([], []))
        self.assertEqual(P.plan_promotions(self.f, "s1", None), ([], []))
        self.assertEqual(P.plan_promotions(self.f, "s1", {"promotions": "off", "reclass": "keep",
                                                          "sides": "own"}), ([], []))

    def test_three_choices_refused_plainly(self):
        with self.assertRaises(R.RandoError) as cm:
            P.check_opts({"choices": "3"})
        self.assertIn("game-code change", str(cm.exception))
        for bad in ({"promotions": "maybe"}, {"reclass": "x"}, {"sides": "x"}, {"choices": "4"}):
            with self.assertRaises(R.RandoError):
                P.check_opts(bad)

    def test_same_seed_same_output_and_seed_matters(self):
        o = {"promotions": "on", "reclass": "random"}
        a = P.plan_promotions(self.f, "s1", o)
        self.assertEqual(a, P.plan_promotions(self.f, "s1", o))
        outs = {repr(P.plan_promotions(self.f, f"s{n}", o)[0]) for n in range(20)}
        self.assertGreater(len(outs), 1)

    def test_guards_pass_many_seeds_every_option(self):
        for n in range(60):
            for o in ON_OPTS:
                e, lines = P.plan_promotions(self.f, f"x{n}", o)
                g = P.run_guards(self.f, e, o)
                self.assertTrue(all_ok(g), (n, o, {k: v for k, v in g.items() if not v["ok"]}))

    def test_every_base_class_keeps_legal_promotions_no_dead_ends(self):
        pf = P.PromoFacts(self.f)
        for n in range(40):
            e, _ = P.plan_promotions(self.f, f"d{n}", {"promotions": "on"})
            after = P._promotions_after(pf, e)
            for src in pf.sources:
                filled = [x for x in after[src] if x != N]
                self.assertEqual(len(filled), 2, src)
                self.assertEqual(len(set(filled)), 2, src)
                for t in filled:
                    self.assertIsNone(pf.legal_target(src, t, "any"), (src, t))
                    self.assertTrue(self.f.promoted(self.f.jobs[t]))
                    self.assertEqual(after[t], [N, N], f"{t} would promote again")
            # every normal promoted class stays reachable here (enough slots)
            reach = {x for s in pf.sources for x in after[s]}
            self.assertTrue(set(pf.targets) <= reach, set(pf.targets) - reach)

    def test_special_rows_untouched(self):
        for n in range(30):
            e, _ = P.plan_promotions(self.f, f"k{n}", {"promotions": "on", "reclass": "random"})
            labels = {(x["table"], x["label"]) for x in e}
            for jid in ("JID_ダークプリンス男", "JID_歌姫女", "JID_妖狐男", "JID_妖狐女", "JID_魔戦士男",
                        "JID_パラディン男", "JID_ノスフェラトゥ男"):
                self.assertNotIn(("Job", jid), labels)
            for pid in ("PID_プレイヤー男", "PID_アクア", "PID_BAD", "PID_KID", "PID_無し"):
                self.assertNotIn(("Person", pid), labels)
            for x in e:
                self.assertNotIn(x["new"], ("JID_九尾の狐男", "JID_九尾の狐女", "JID_ダークブラッド男", "JID_魔戦士男",
                                            "JID_村人男", "JID_村人女", "JID_ノスフェラトゥ男"))

    def test_weapon_kind_kept(self):
        pf = P.PromoFacts(self.f)
        for n in range(30):
            e, _ = P.plan_promotions(self.f, f"w{n}", {"promotions": "on"})
            after = P._promotions_after(pf, e)
            for t in after["JID_アクスファイター男"]:
                self.assertGreaterEqual(R.ival(self.f.jobs[t]["max_weapon_exp.axe"]), 96)
            for t in after["JID_ロッドナイト女"]:
                self.assertGreater(R.ival(self.f.jobs[t]["max_weapon_exp.staff"]), 0)
                self.assertTrue(self.f.female(self.f.jobs[t]))
            for t in after["JID_村人女"]:
                self.assertGreater(R.ival(self.f.jobs[t]["max_weapon_exp.lance"]), 0)

    def test_gender_lines_mirrored(self):
        for n in range(20):
            e, _ = P.plan_promotions(self.f, f"g{n}", {"promotions": "on"})
            pf = P.PromoFacts(self.f)
            after = P._promotions_after(pf, e)
            m, fm = after["JID_ソシアルナイト男"], after["JID_ソシアルナイト女"]
            self.assertEqual([self.f.jobs[x]["gender_pair"] for x in m], fm)

    def test_sides_own(self):
        pf = P.PromoFacts(self.f)
        for n in range(20):
            e, _ = P.plan_promotions(self.f, f"o{n}", {"promotions": "on", "sides": "own"})
            after = P._promotions_after(pf, e)
            for t in after["JID_マーシナリー男"]:
                self.assertEqual(self.f.jobs[t]["origin"], "1")

    def test_sides_own_short_line_falls_back(self):
        self.f.jobs["JID_兵法者男"]["origin"] = "2"
        self.f.jobs["JID_兵法者女"]["origin"] = "2"
        o = {"promotions": "on", "sides": "own"}
        e, lines = P.plan_promotions(self.f, "fb", o)
        self.assertTrue([x for x in lines if "drawn from both sides" in x])
        self.assertTrue(all_ok(P.run_guards(self.f, e, o)))

    def test_reclass_rules(self):
        for n in range(40):
            e, _ = P.plan_promotions(self.f, f"r{n}", {"reclass": "random"})
            self.assertFalse([x for x in e if x["table"] == "Job"])
            for x in e:
                self.assertIn(x["cell"], P.RECLASS_CELLS)
                self.assertNotEqual(x["new"], N)
                p = self.f.by_pid[x["label"]]
                self.assertEqual(self.f.female(self.f.jobs[x["new"]]), self.f.female(p))
                self.assertFalse(self.f.promoted(self.f.jobs[x["new"]]))
                self.assertNotEqual(x["new"], P.own_base(self.f, p["job"], p["job_low"]))
            # B and E had one Heart Seal class: still one
            self.assertFalse([x for x in e if x["label"] in ("PID_B", "PID_E") and x["cell"] == "reclass.2"])

    def test_reclass_avoids_new_class_from_base_plan(self):
        bp = base_plan(self.f, {"PID_A": ("JID_マーシナリー男", "JID_剣聖男")})
        for n in range(40):
            o = {"reclass": "random", "base_plan": bp}
            e, _ = P.plan_promotions(self.f, f"b{n}", o)
            for x in e:
                if x["label"] == "PID_A":
                    self.assertNotIn(x["new"], ("JID_マーシナリー男", "JID_ソシアルナイト男"))
            self.assertTrue(all_ok(P.run_guards(self.f, e, o)))

    def test_job_low_follows_new_promotions(self):
        bp = base_plan(self.f, {"PID_E": ("JID_パラディン男", "JID_ソシアルナイト男")})
        pf = P.PromoFacts(self.f)
        for n in range(40):
            o = {"promotions": "on", "base_plan": bp}
            e, _ = P.plan_promotions(self.f, f"j{n}", o)
            after = P._promotions_after(pf, e)
            low = {x["label"]: x for x in e if x["cell"] == "job_low"}
            if "PID_E" in low:
                self.assertEqual(low["PID_E"]["old"], "JID_ソシアルナイト男")
                self.assertIn("JID_パラディン男", after[low["PID_E"]["new"]])
            else:
                self.assertIn("JID_パラディン男", after["JID_ソシアルナイト男"])
            self.assertTrue(all_ok(P.run_guards(self.f, e, o)))

    def test_low_also_rows_follow_without_heart_seal(self):
        """Round W1: opts["low_also"] (the children when the children track is off) get a job_low that follows the
        new promotions; their Heart Seal cells are never touched; the guard accepts exactly those cells."""
        f = self.f
        outside = [p for p in f.persons if not f.in_scope(p) and p["job"] in P.PromoFacts(f).sources]
        if not outside:
            self.skipTest("the made-up tables have no out-of-scope row with a base class")
        pid = outside[0]["label"]
        seen = 0
        for n in range(40):
            o = {"promotions": "on", "reclass": "random", "low_also": [pid]}
            e, _ = P.plan_promotions(f, f"la{n}", o)
            mine = [x for x in e if x["label"] == pid]
            self.assertTrue(all(x["cell"] == "job_low" for x in mine), mine)
            seen += len(mine)
            self.assertTrue(all_ok(P.run_guards(f, e, o)), n)
            self.assertFalse(all_ok(P.run_guards(f, e, {"promotions": "on", "reclass": "random"})) and mine, n)
        self.assertGreater(seen, 0)

    def test_guard_catches_bad_edits(self):
        cav = self.f.jobs["JID_ソシアルナイト男"]

        def ed(cell, old, new, label="JID_ソシアルナイト男", table="Job", ix=None):
            return {"table": table, "index": R.ival(cav["index"]) if ix is None else ix, "label": label,
                    "cell": cell, "old": old, "new": new}

        cases = [
            [ed("promotion.1", "JID_パラディン男", "JID_パラディン女")],                 # other gender
            [ed("promotion.1", "JID_パラディン男", "JID_バーサーカー男")],               # no sword/lance
            [ed("promotion.1", "JID_パラディン男", "JID_グレートナイト男")],             # twice in one menu
            [ed("promotion.1", "JID_パラディン男", N)],                                 # dead end slot
            [ed("promotion.1", "JID_パラディン男", "JID_九尾の狐男")],                    # beast class
            [ed("promotion.1", "JID_パラディン男", "JID_ノスフェラトゥ男")],              # enemy-only
            [ed("promotion.1", "JID_無し男", "JID_ブレイブヒーロー男", label="JID_パラディン男", ix=20)],  # promoted row
            [ed("reclass.1", N, "JID_マーシナリー女", label="PID_アクア", table="Person", ix=2)],
            [ed("reclass.1", "JID_ロッドナイト女", "JID_マーシナリー女", label="PID_アクア", table="Person", ix=2)],
            [ed("reclass.1", "JID_マーシナリー男", "JID_ソシアルナイト男", label="PID_A", table="Person", ix=3)],
            [ed("reclass.1", "JID_マーシナリー男", "JID_アクスファイター男", label="PID_A", table="Person", ix=3)],
            [ed("reclass.1", "JID_マーシナリー男", "JID_パラディン男", label="PID_A", table="Person", ix=3)],
            [ed("reclass.2", "JID_アクスファイター男", N, label="PID_A", table="Person", ix=3)],
        ]
        for c in cases:
            self.assertFalse(all_ok(P.run_guards(self.f, c, {"promotions": "on"})), c)
        # Paladin no longer reached: the Paladin start (via plan) is flagged, and so is a stale job_low
        kn = self.f.jobs["JID_アーマーナイト男"]
        e = [ed("promotion.1", "JID_パラディン男", "JID_ブレイブヒーロー男"),
             ed("promotion.2", "JID_パラディン男", "JID_ブレイブヒーロー男", label="JID_アーマーナイト男",
                ix=R.ival(kn["index"]))]
        bp = base_plan(self.f, {"PID_E": ("JID_パラディン男", "JID_ソシアルナイト男")})
        g = P.run_guards(self.f, e, {"base_plan": bp})
        self.assertFalse(g["every promoted class a playable person starts in stays reachable"]["ok"])
        self.assertFalse(g["job_low matches the promotions (the game's own pattern)"]["ok"])

    def test_track_streams_independent_of_other_tracks(self):
        import random
        a = P.plan_promotions(self.f, "s9", {"promotions": "on"})[0]
        random.seed(1)
        random.random()
        self.assertEqual(a, P.plan_promotions(self.f, "s9", {"promotions": "on"})[0])
        self.assertTrue(P.plan_promotions(self.f, random.Random(5), {"promotions": "on"})[0])

    def test_files_with_edits(self):
        import csv
        import io
        bp = base_plan(self.f, {})
        e, _ = P.plan_promotions(self.f, "csv1", {"promotions": "on", "reclass": "random", "base_plan": bp})
        s1 = {"tables/Person.csv": R._csv([["index", "label", "job", "job_low"], ["3", "PID_A", "JID_ソシアルナイト男",
                                                                                 "JID_パラディン男"]])}
        files = P.files_with_edits(self.f, s1, e)
        jobs = list(csv.reader(io.StringIO(files["tables/Job.csv"].decode("utf-8").lstrip("﻿"))))
        self.assertEqual(jobs[0], ["index", "label", "promotion.1", "promotion.2"])
        want = {x["label"] for x in e if x["table"] == "Job"}
        self.assertEqual({r[1] for r in jobs[1:]}, want)
        per = list(csv.reader(io.StringIO(files["tables/Person.csv"].decode("utf-8").lstrip("﻿"))))
        head = per[0]
        self.assertEqual(head[:4], ["index", "label", "job", "job_low"])
        rows = {r[1]: dict(zip(head, r)) for r in per[1:]}
        for x in e:
            if x["table"] == "Person":
                self.assertEqual(rows[x["label"]][x["cell"]], x["new"])
        self.assertEqual(P.files_with_edits(self.f, s1, []), s1)


@unittest.skipIf(GD is None, "no extracted RomFS / table layouts here")
class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = GD.load_facts()

    def test_every_option_many_seeds(self):
        pf = P.PromoFacts(self.f)
        self.assertEqual(len(pf.sources), 36)         # 17 base class lines x 2 genders + Villager x 2
        for n in range(15):
            plan = R.make_plan(self.f, f"real{n}", {})
            for o in ON_OPTS:
                o = dict(o, base_plan=plan)
                e, lines = P.plan_promotions(self.f, f"real{n}", o)
                g = P.run_guards(self.f, e, o)
                self.assertTrue(all_ok(g), (n, o["promotions"], o["reclass"], o["sides"],
                                            {k: v for k, v in g.items() if not v["ok"]}))
                self.assertFalse([x for x in lines if "could not keep" in x], (n, o["sides"]))
                self.assertEqual(e, P.plan_promotions(self.f, f"real{n}", o)[0])
                if o["promotions"] == "on":
                    after = P._promotions_after(pf, e)
                    reach = {x for s in pf.sources for x in after[s]}
                    self.assertTrue(set(pf.targets) <= reach, (n, set(pf.targets) - reach))

    def test_off_is_no_edits(self):
        self.assertEqual(P.plan_promotions(self.f, "real0", {"base_plan": R.make_plan(self.f, "real0", {})}), ([], []))

    def test_mods_tool_accepts_the_folder(self):
        sys.path.insert(0, os.path.join(ROOT, "tools", "mods"))
        import mods as M
        os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
        with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, "build")) as d:
            folder, guards, edits = P.make_folder("r55test", {"promotions": "on", "reclass": "random"},
                                                  os.path.join(d, "mods"), facts=self.f)
            self.assertTrue(all(v["ok"] for v in guards.values()), guards)
            self.assertTrue(os.path.isfile(os.path.join(folder, "tables", "Job.csv")))
            ctx = M.Ctx(mods_dir=os.path.join(d, "mods"), stage_dir=os.path.join(d, "stage"),
                        zakuro_dir=os.path.join(d, "zak"))
            r = M.compute(ctx)
            self.assertFalse(r.errors, r.errors[:5])


if __name__ == "__main__":
    unittest.main()
