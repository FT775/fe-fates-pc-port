"""Round 75b: the seed guarantees inside the randomizer (docs/SEED_GUARANTEES_PLAN.md, which says 'round 79': read it
as round 75b). Section 7's tests, the no-repeated-class tests (G2b) and a few real-data checks.

Host only. Made-up tables (tests/test_randomizer.fake_facts plus a 'guarantees' block in the rules) for the unit tests;
the real-data class skips when the game's RomFS is not extracted. The big seed sweep (1,000 + 3 x 200 seeds) is the
round's own run (build/r75b/tests/sweep.py), not part of this file; RealData.test_sweep_small runs 12 seeds each.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
import randolib as R  # noqa: E402
import guarantees as GU  # noqa: E402
from tests import test_randomizer as T  # noqa: E402

N = "JID_無し男"
SEEDS = [f"g6s{i}" for i in range(60)]
CORRIN = "PID_プレイヤー男"
AZURA = "PID_アクア"
XANDER = "PID_マークス"           # a royal with a legendary weapon (SPID_マークス)
GUNTER = "PID_ギュンター"         # rules.json recruit_fixed
NYX, SHURA = "PID_ニュクス", "PID_アシュラ"   # rules.json recruit_hold
FLIER_M = "JID_ペガサス男"         # a made-up male flying class (category JCID_飛行) for these tests only
STAFF_FLIER_M = "JID_天馬僧男"     # a made-up male class that flies AND has a staff rank
FLIER2_M = "JID_天馬剣男"          # a second made-up male flying class (no staff)


def facts_with(table, extra_persons=(), extra_dispos=(), extra_jobs=(), drop_dispos=(), staff_flier=True):
    """fake_facts plus a second male staff class (JID_モンク男), male flier classes (one of them also with a staff rank,
    unless staff_flier=False) and a 'guarantees' block in the rules."""
    f = T.fake_facts()
    jobs = list(f.job_list) + [
        T.job(21, "JID_モンク男", kinds=("staff", "tome"), promo=("JID_ストラテジスト男", N)),
        T.job(22, FLIER_M, kinds=("lance",), cat="JCID_飛行", promo=("JID_パラディン男", N)),
        T.job(24, FLIER2_M, kinds=("sword",), cat="JCID_飛行", promo=("JID_パラディン男", N)),
    ] + ([T.job(23, STAFF_FLIER_M, kinds=("staff",), cat="JCID_飛行", promo=("JID_ストラテジスト男", N))]
         if staff_flier else []) + list(extra_jobs)
    persons = list(f.persons) + list(extra_persons)
    dispos = [d for d in f.dispos if (d["file"], d["index"]) not in drop_dispos] + list(extra_dispos)
    subs = [{"index": str(k), "kind": str(v), "origin": str(f.sub_origin.get(k, 0))} for k, v in f.sub_kind.items()]
    rules = dict(T.RULES, guarantees=table)
    return R.Facts(persons, jobs, list(f.items.values()), subs, dispos, rules, {})


def need(role, by, army, story="A"):
    return {"stories": {story: {"name": "Story " + story, "needs": [{"role": role, "by": by, "army": army}]}}}


def two_needs(first, second, story="A"):
    return {"stories": {story: {"name": "Story " + story, "needs": [first, second]}}}


def jobs_of(plan) -> dict:
    return {e["pid"]: e["job"] for e in plan["persons"]}


def tables_only(files: dict) -> dict:
    return {k: v for k, v in files.items() if k not in ("plan.json", "spoiler.txt", "mod.json")}


# ====================================================================== plan section 7
class Section7(unittest.TestCase):
    def test_met_seed_unchanged(self):
        """A seed that already meets every need: every table byte as slice 1 without the pass (no needs at all)."""
        extra = [T.person(20, "PID_P", "JID_ロッドナイト男", N, wexp={"staff": 1})]
        dis = [T.disp("A001", 5, "PID_P", 0)]
        classes = {"PID_P": "JID_ロッドナイト男", "PID_B": "JID_ソシアルナイト女"}
        with_need = facts_with(need("staff", "A007", ["PID_P"]), extra, dis)
        without = facts_with({}, extra, dis)
        for s in SEEDS[:20]:
            p1 = R.make_plan(with_need, s, None, classes=classes)
            p0 = R.make_plan(without, s, None, classes=classes)
            self.assertEqual(p1["guarantees"]["repairs"], [], s)
            self.assertTrue(p1["guarantees"]["needs"][0]["ok"], s)
            self.assertEqual(p0["guarantees"]["needs"], [], s)
            self.assertEqual(tables_only(R.render(with_need, p1)), tables_only(R.render(without, p0)), s)
            self.assertEqual(jobs_of(p1), jobs_of(p0))

    def test_repair_one_person(self):
        """A need nobody covers: exactly one pool person changes, to a class with the role; deterministic."""
        extra = [T.person(20, "PID_P", "JID_ソシアルナイト男", N, wexp={"sword": 1}),
                 T.person(21, "PID_Q", "JID_ソシアルナイト男", N, wexp={"sword": 1}),
                 T.person(22, "PID_O", "JID_ロッドナイト男", N, wexp={"staff": 1})]   # the original cover (not in army
        dis = [T.disp("A001", 5, "PID_P", 0), T.disp("A002", 5, "PID_Q", 0), T.disp("A009", 5, "PID_O", 0)]
        f = facts_with(need("staff", "A007", ["PID_P", "PID_Q", "PID_O"]), extra, dis)
        classes = {"PID_P": "JID_アクスファイター男", "PID_Q": "JID_ソシアルナイト男", "PID_O": "JID_アクスファイター男",
                   "PID_B": "JID_ソシアルナイト女"}
        for s in SEEDS:
            p = R.make_plan(f, s, None, classes=classes)
            reps = p["guarantees"]["repairs"]
            self.assertEqual(len(reps), 1, (s, reps))
            r = reps[0]
            self.assertTrue(GU.role_of(f, f.by_pid[r["pid"]], r["to"], "staff"), r)
            self.assertEqual(jobs_of(p)[r["pid"]], r["to"])
            changed = [pid for pid in ("PID_P", "PID_Q", "PID_O") if jobs_of(p)[pid] != classes[pid]]
            self.assertEqual(changed, [r["pid"]], s)
            # the earliest joiner whose drawn class changed comes first (P: A001, class changed by the draw)
            self.assertEqual(r["pid"], "PID_P", s)
            self.assertEqual(p, R.make_plan(f, s, None, classes=classes), "same seed, same plan")
            self.assertTrue(GU.check(f, p)["ok"], s)

    def test_never_kept_or_held(self):
        """Corrin, Azura, Gunter, the royals, Nyx and Shura are never repaired while a pool person can take the role.
        Round 75b's one named exception (the code part's 'last resort', a departure from the plan's 'never Gunter' that
        the report states for the owner): when NOBODY in the first-choice pool can take the role, the shuffle's fixed
        people (rules.json recruit_fixed: Gunter only) may be repaired, marked last_resort. Nyx, Shura, the royals,
        Corrin and Azura stay untouched even then."""
        # the original cover is Nyx (a healer in the original tables, drawn into a lance class here)
        extra = [T.person(20, GUNTER, "JID_ソシアルナイト男", N, wexp={"sword": 1}),
                 T.person(21, NYX, "JID_ロッドナイト女", N, female=True, wexp={"staff": 1}),
                 T.person(22, SHURA, "JID_ソシアルナイト男", N, wexp={"sword": 1}),
                 T.person(23, "PID_P", "JID_ソシアルナイト男", N, wexp={"sword": 1})]
        dis = [T.disp("A001", 5, GUNTER, 0), T.disp("A001", 6, NYX, 0), T.disp("A001", 7, SHURA, 0),
               T.disp("A005", 5, "PID_P", 0)]
        held = [CORRIN, AZURA, XANDER, GUNTER, NYX, SHURA]
        classes = {GUNTER: "JID_ソシアルナイト男", NYX: "JID_ソシアルナイト女", SHURA: "JID_ソシアルナイト男",
                   "PID_P": "JID_ソシアルナイト男", "PID_B": "JID_ソシアルナイト女"}
        f = facts_with(need("staff", "A007", held + ["PID_P"]), extra, dis)
        for s in SEEDS:
            p = R.make_plan(f, s, None, classes=classes)
            reps = p["guarantees"]["repairs"]
            self.assertEqual([r["pid"] for r in reps], ["PID_P"], s)   # P joins after the held, but only P is pool
            self.assertFalse(any(r.get("last_resort") for r in reps))
            self.assertTrue(GU.check(f, p)["ok"], s)
        # the only pool person is a beast (no staff class is legal for a beast): the last resort repairs Gunter only
        f2 = facts_with(need("staff", "A007", held + ["PID_F"]), extra, dis)
        for s in SEEDS[:20]:
            p = R.make_plan(f2, s, None, classes=classes)
            reps = p["guarantees"]["repairs"]
            self.assertEqual([r["pid"] for r in reps], [GUNTER], s)
            self.assertTrue(reps[0]["last_resort"], s)
            self.assertIn("last resort", "\n".join(p["forced"]))
            self.assertTrue(GU.check(f2, p)["ok"], s)
        # with no Gunter in the army either: no repair at all, and the backstop refuses the seed (section 3 step 5)
        f3 = facts_with(need("staff", "A007", [CORRIN, AZURA, XANDER, NYX, SHURA, "PID_F"]), extra, dis)
        p = R.make_plan(f3, SEEDS[0], None, classes=classes)
        self.assertEqual(p["guarantees"]["repairs"], [])
        self.assertFalse(p["guards"]["guarantees: timing"]["ok"])
        self.assertIn("no repair found", "\n".join(p["guarantees"]["notes"]))

    def test_retainer_slot(self):
        """The retainer slot covers only when both have the role, and both are repaired together."""
        extra = [T.person(20, "PID_X", "JID_ロッドナイト男", N, wexp={"staff": 1}),
                 T.person(21, "PID_Y", "JID_ロッドナイト女", N, female=True, wexp={"staff": 1})]
        f = facts_with(need("staff", "A007", [["PID_X", "PID_Y"]]), extra,
                       [T.disp("A002", 5, "PID_X", 0), T.disp("A002", 6, "PID_Y", 0)])
        # one of the two with the role is not enough
        half = {"PID_X": "JID_ロッドナイト男", "PID_Y": "JID_ソシアルナイト女"}
        self.assertEqual(GU.met(f, half, GU.needs(f.rules)[0]), [])
        self.assertTrue(GU.met(f, dict(half, PID_Y="JID_ロッドナイト女"), GU.needs(f.rules)[0]))
        for s in SEEDS[:30]:
            p = R.make_plan(f, s, None, classes={"PID_X": "JID_アクスファイター男", "PID_Y": "JID_ソシアルナイト女",
                                                 "PID_B": "JID_ソシアルナイト女"})
            got = jobs_of(p)
            self.assertTrue(GU.role_of(f, f.by_pid["PID_X"], got["PID_X"], "staff"), s)
            self.assertTrue(GU.role_of(f, f.by_pid["PID_Y"], got["PID_Y"], "staff"), s)
            self.assertEqual(sorted(r["pid"] for r in p["guarantees"]["repairs"]), ["PID_X", "PID_Y"])

    def test_leaver_not_counted(self):
        """A person absent from the chapter's roll does not cover it, even with the role (B is a healer but not in
        this army: someone in the army is repaired)."""
        extra = [T.person(20, "PID_P", "JID_ソシアルナイト男", N, wexp={"sword": 1}),
                 T.person(21, "PID_O", "JID_ロッドナイト男", N, wexp={"staff": 1})]
        f = facts_with(need("staff", "A007", ["PID_P", "PID_O"]), extra,
                       [T.disp("A001", 5, "PID_P", 0), T.disp("A009", 5, "PID_O", 0)])
        for s in SEEDS[:30]:
            p = R.make_plan(f, s, None, classes={"PID_P": "JID_ソシアルナイト男", "PID_O": "JID_アクスファイター男",
                                                 "PID_B": "JID_ロッドナイト女"})
            self.assertEqual(jobs_of(p)["PID_B"], "JID_ロッドナイト女")          # a healer, but not in the roll
            got = [r["pid"] for r in p["guarantees"]["repairs"]]
            self.assertEqual(len(got), 1, s)
            self.assertIn(got[0], ("PID_P", "PID_O"), s)
            self.assertNotIn(["PID_B"], p["guarantees"]["needs"][0]["covered_by"])

    def test_earlier_need_kept(self):
        """A repair never takes away the only cover of an earlier need. P (A001, first in the repair order: the earliest
        joiner whose drawn class changed) is the only cover of the A005 flier need; R (A004, a healer in the original)
        is the other candidate for the A007 healer need. With no class that both flies and heals, R is repaired and P
        keeps flying; without the flier need, P would be the one repaired."""
        def make(tbl, staff_flier):
            extra = [T.person(20, "PID_P", FLIER2_M, N, wexp={"sword": 1}),
                     T.person(21, "PID_R", "JID_ロッドナイト男", N, wexp={"staff": 1})]
            dis = [T.disp("A001", 5, "PID_P", 0), T.disp("A004", 5, "PID_R", 0)]
            return facts_with(tbl, extra, dis, staff_flier=staff_flier)
        flier = {"role": "flier", "by": "A005", "army": ["PID_P"]}
        staff = {"role": "staff", "by": "A007", "army": ["PID_P", "PID_R"]}
        classes = {"PID_P": FLIER_M, "PID_R": "JID_ソシアルナイト男", "PID_B": "JID_ソシアルナイト女"}
        both = make(two_needs(flier, staff), False)
        only_staff = make(need("staff", "A007", ["PID_P", "PID_R"]), False)
        for s in SEEDS:
            p = R.make_plan(both, s, None, classes=classes)
            self.assertEqual(jobs_of(p)["PID_P"], FLIER_M, s)
            self.assertEqual([r["pid"] for r in p["guarantees"]["repairs"]], ["PID_R"], s)
            self.assertTrue(all(x["ok"] for x in p["guarantees"]["needs"]), s)
            q = R.make_plan(only_staff, s, None, classes=classes)
            self.assertEqual([r["pid"] for r in q["guarantees"]["repairs"]], ["PID_P"], s)
        # with a class that flies AND heals, P may take it (it keeps the earlier need met); P never stops flying
        fly_heal = make(two_needs(flier, staff), True)
        for s in SEEDS:
            p = R.make_plan(fly_heal, s, None, classes=classes)
            got = jobs_of(p)
            self.assertTrue(GU.role_of(fly_heal, fly_heal.by_pid["PID_P"], got["PID_P"], "flier"), s)
            self.assertTrue(all(x["ok"] for x in p["guarantees"]["needs"]), s)

    def test_healer_holds_staff(self):
        """A repaired healer's join placement carries a staff the class can use (the cheapest of the lowest rank)."""
        extra = [T.person(20, "PID_P", "JID_ロッドナイト男", N, wexp={"staff": 1})]
        f = facts_with(need("staff", "A007", ["PID_P"]), extra, [T.disp("A001", 5, "PID_P", 0)])
        cls = {"PID_P": "JID_アクスファイター男", "PID_B": "JID_ソシアルナイト女"}
        for s in SEEDS[:20]:
            p = R.make_plan(f, s, None, classes=cls)
            self.assertEqual(p, R.make_plan(f, s, None, classes=cls))
            self.assertIn(jobs_of(p)["PID_P"], ("JID_ロッドナイト男", "JID_モンク男", STAFF_FLIER_M))
            ed = p["dispos"]["GameData/Dispos/A001.bin.lz#5"]
            self.assertEqual(ed["item_1"], "IID_ライブ")
            self.assertTrue(p["guards"]["weapons_usable"]["ok"], p["guards"]["weapons_usable"])
            self.assertTrue(GU.check(f, p)["ok"])
        # the backstop catches a repaired healer without a staff
        p = R.make_plan(f, SEEDS[0], None, classes=cls)
        p["dispos"]["GameData/Dispos/A001.bin.lz#5"]["item_1"] = ""
        g = GU.check(f, p)
        self.assertFalse(g["ok"])
        self.assertIn("joins without a staff", "\n".join(g["detail"]))

    def test_never_stricter(self):
        """Nobody in the army has the role in the original tables: not a need."""
        f = facts_with(need("staff", "A007", ["PID_A", "PID_C"]))
        p = R.make_plan(f, "x1")
        self.assertEqual(p["guarantees"]["needs"], [])
        self.assertEqual(p["guarantees"]["repairs"], [])
        self.assertIn("never stricter", p["guarantees"]["skipped"][0]["why"])
        # with the character shuffle, "the original" is the rows before the shuffle (facts.original_facts)
        f2 = facts_with(need("staff", "A007", ["PID_A", "PID_B"]))
        ok, _why = GU.applies(f2, GU.needs(f2.rules)[0])
        self.assertTrue(ok)
        f3 = facts_with(need("staff", "A007", ["PID_A", "PID_B"]))
        f3.original_facts = facts_with(need("staff", "A007", ["PID_A", "PID_C"]))
        f3.original_facts.by_pid["PID_B"] = dict(f3.by_pid["PID_B"], job="JID_ソシアルナイト女")
        self.assertFalse(GU.applies(f3, GU.needs(f3.rules)[0])[0])

    def test_version_row(self):
        """The hidden row is answered, changes the run id, is not in Randomize everything, has no flag, and a restored
        old answer gets "2" (the full set is in tests/test_rando_page62b.VersionRowTests)."""
        import ingame as IG
        rows = IG.schema()["rows"]
        row = next(r for r in rows if r["key"] == IG.VERSION_KEY)
        self.assertEqual(IG.rando_version(), GU.RANDO_VERSION)
        self.assertEqual(GU.RANDO_VERSION, 2)
        self.assertEqual((row["choices"], row["default"]), (["2"], "2"))
        self.assertTrue(row["hidden"] and row["fixed"])
        self.assertNotIn("flag", row)
        a = IG.page_answers(rows, IG.page_restore(rows, {"randomizer": True, "seed": "g6v"}))
        self.assertEqual(a[IG.VERSION_KEY], "2")
        old = {k: v for k, v in a.items() if k != IG.VERSION_KEY}
        self.assertNotEqual(IG.run_id(a), IG.run_id(old))
        self.assertEqual(IG.make_args(a), IG.make_args(old))
        out, turned = IG.page_everything(rows, IG.page_restore(rows, {"seed": "g6e"}))
        self.assertEqual(out[IG.VERSION_KEY], "2")
        self.assertNotIn(row["label"], turned)
        self.assertEqual(IG.page_restore(rows, {"randomizer": True, IG.VERSION_KEY: "1"})[IG.VERSION_KEY], "2")

    def test_check_refuses_v1_folder(self):
        """rando.py check on a folder made before round 75b: the plain sentence, exit 3."""
        import importlib.util
        # loaded by path: a plain 'import rando' can find tools/play/rando.py first when another test module in the
        # same lane put tools/play on sys.path (seen in the core run of 2026-11-25 10:52: check returned 0)
        spec = importlib.util.spec_from_file_location("rando_r75b_check",
                                                      os.path.join(ROOT, "tools", "randomizer", "rando.py"))
        rando = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rando)
        top = os.path.join(ROOT, "build")
        os.makedirs(top, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=top) as t:
            d = os.path.join(t, "Rando-g6old")
            os.makedirs(d)
            with open(os.path.join(d, "plan.json"), "w", encoding="utf-8") as fh:
                json.dump({"seed": "g6old", "switches": {}, "tool": "rando-slice1-v1"}, fh)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = rando.main(["check", d])
            self.assertEqual(code, 3)
            self.assertIn("made by randomizer 1 (before round 75b)", buf.getvalue())
            self.assertNotIn("Traceback", buf.getvalue())

    # round 84: the two Seal guarantees tests (the rules block, the committed rules file) are the Seal
    # edition's (tests/seal; the builder moved to tools/seal)


# ====================================================================== G2b
class NoRepeatedClass(unittest.TestCase):
    """G2b (owner 2026-11-25, "Yes, add it"): one role class free and one taken -> the free one; all taken -> still a
    repair (marked no_repeat False)."""

    def setUp(self):
        self.extra = [T.person(20, "PID_P", "JID_ロッドナイト男", N, wexp={"staff": 1}),
                      T.person(21, "PID_X", "JID_ソシアルナイト男", N, wexp={"sword": 1}),
                      T.person(22, "PID_Y", "JID_ソシアルナイト男", N, wexp={"sword": 1})]
        self.dispos = [T.disp("A001", 5, "PID_P", 0), T.disp("A002", 5, "PID_X", 0), T.disp("A002", 6, "PID_Y", 0)]
        self.classes = {"PID_P": "JID_アクスファイター男", "PID_X": "JID_ロッドナイト男", "PID_Y": "JID_ソシアルナイト男",
                        "PID_B": "JID_ソシアルナイト女"}

    def test_free_class_picked(self):
        # the slot [X, Y] has X's Troubadour (taken) but does not cover (Y has none); P must get a free staff class
        f = facts_with(need("staff", "A007", ["PID_P", ["PID_X", "PID_Y"]]), self.extra, self.dispos)
        for s in SEEDS:
            p = R.make_plan(f, s, None, classes=self.classes)
            reps = p["guarantees"]["repairs"]
            self.assertEqual([r["pid"] for r in reps], ["PID_P"], s)
            self.assertIn(jobs_of(p)["PID_P"], ("JID_モンク男", STAFF_FLIER_M), s)   # never X's Troubadour line
            self.assertTrue(reps[0]["no_repeat"])
            self.assertTrue(p["guarantees"]["needs"][0]["ok"])

    def test_all_taken_still_repairs(self):
        z = T.person(23, "PID_Z", "JID_モンク男", N, flags="SPID_マークス", wexp={"staff": 1})
        w = T.person(24, "PID_W", STAFF_FLIER_M, N, flags="SPID_リョウマ", wexp={"staff": 1})
        f = facts_with(need("staff", "A007", ["PID_P", ["PID_X", "PID_Y"], ["PID_Z", "PID_Y"], ["PID_W", "PID_Y"]]),
                       self.extra + [z, w], self.dispos + [T.disp("A002", 7, "PID_Z", 0), T.disp("A002", 8, "PID_W", 0)])
        for s in SEEDS:
            p = R.make_plan(f, s, None, classes=self.classes)
            r = p["guarantees"]["repairs"][0]
            self.assertEqual(r["pid"], "PID_P")
            self.assertFalse(r["no_repeat"], s)
            self.assertIn("every role class already in the army", "\n".join(p["forced"]))
            self.assertTrue(p["guarantees"]["needs"][0]["ok"])


# ====================================================================== the other parts
class Basics(unittest.TestCase):
    def test_real_table_with_made_up_people(self):
        """The real guarantees.json on made-up tables: none of its armies are there, so nothing is repaired and the
        block still carries the version."""
        f = T.fake_facts()
        for s in SEEDS[:10]:
            p = R.make_plan(f, s)
            self.assertEqual(p["guarantees"]["repairs"], [])
            self.assertEqual(p["rando_version"], GU.RANDO_VERSION)
            self.assertEqual(p["guarantees"]["round"], "75b")
            self.assertTrue(all(x["why"] for x in p["guarantees"]["skipped"]))

    def test_table_shape(self):
        t = GU.load_table()
        self.assertEqual(t["round"], "75b")
        self.assertEqual(t["retainer_slot"], ["PID_フェリシア", "PID_ジョーカー"])
        got = {(n["story"], n["role"], n["by"]) for n in GU.needs(T.RULES)}
        self.assertEqual(got, {("A", "vein", "every"), ("B", "vein", "every"), ("C", "vein", "every"),
                               ("A", "door", "A007"), ("A", "staff", "A007"), ("A", "flier", "A010"),
                               ("B", "staff", "B007"), ("B", "door", "B009"),
                               ("C", "staff", "C007"), ("C", "door", "C009"), ("C", "flier", "C011")})
        text = json.dumps(t, ensure_ascii=False)
        for n in GU.needs(T.RULES):
            for e in n["army"]:
                for pid in GU.members(e):
                    self.assertTrue(pid.startswith("PID_"), pid)      # ids only
        self.assertNotIn("\\u", text)

    def test_unknown_role_refused(self):
        with self.assertRaises(GU.GuaranteeError):
            GU.needs({"guarantees": {"stories": {"A": [{"role": "archer", "by": "A007", "army": []}]}}})

    def test_spoiler_section(self):
        extra = [T.person(20, "PID_P", "JID_ロッドナイト男", N, wexp={"staff": 1})]
        f = facts_with(need("staff", "A007", ["PID_P"]), extra, [T.disp("A001", 5, "PID_P", 0)])
        p = R.make_plan(f, "sp1", None, classes={"PID_P": "JID_アクスファイター男", "PID_B": "JID_ソシアルナイト女"})
        text = R.render(f, p)["spoiler.txt"].decode("utf-8")
        self.assertIn("Guarantees (round 75b, always on; randomizer 2):", text)
        self.assertIn("repaired: ", text)

    def test_where_labels(self):
        """Fates ids carry the shown chapter number; Seal's R ids are printed as ids (R002 is not chapter 2)."""
        self.assertEqual(GU.where({"story_name": "Birthright", "by": "A007"}), "Birthright 7")
        self.assertEqual(GU.where({"story_name": "Revelation", "by": "every"}), "Revelation every chapter")
        self.assertEqual(GU.where({"story_name": "Seal of Flames", "by": "R002"}), "Seal of Flames chapter id R002")


# ====================================================================== real data
def _real():
    import gamedata as GD
    why = GD.available()
    return (None, why) if why else (GD, None)


GDM, WHY = _real()


@unittest.skipIf(GDM is None, f"no game data: {WHY}")
class RealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = GDM.load_facts()

    def test_facts_command(self):
        """guarantees.py facts agrees with the table (scripts kinds 9/10 and, when on disk, round 72's armies)."""
        rep = GU.facts_report()
        self.assertTrue(rep["ok"], rep["disagree"])

    def test_route_roles_still_kept(self):
        """The round-47 route guards (one healer, opener and vein user per route) stay green on top of the timing."""
        for s in ("g6r1", "g6r2", "g6r3"):
            p = R.make_plan(self.f, s)
            for g in ("staff_user_per_route", "door_opener_per_route", "vein_user_per_route", "guarantees: timing"):
                self.assertTrue(p["guards"][g]["ok"], (s, g))

    def test_sweep_small(self):
        """12 seeds each: page defaults, the shuffle within story and across stories: 0 misses after the pass."""
        import tracks as TR
        for ro in ({}, {"recruit": "route"}, {"recruit": "any"}):
            for i in range(12):
                seed = f"g6small{i}"
                plan, _files = TR.make_all(self.f, seed, {}, {}, ropts=ro or None)
                bad = {k: v["detail"][:3] for k, v in plan["guards"].items() if not v["ok"]}
                self.assertFalse(bad, (ro, seed, bad))
                self.assertTrue(all(x["ok"] for x in plan["guarantees"]["needs"]), (ro, seed))

    def test_r63fboss1_seed_has_no_repair(self):
        """The guarded boss seed (classes off): no repair, so only plan.json and the spoiler can differ."""
        p = R.make_plan(self.f, "r63fboss1", {"classes": False})
        self.assertEqual(p["guarantees"]["repairs"], [])

    def test_classes_off_with_shuffle_may_repair(self):
        """Pins today's behaviour (owner call in F-061): with Classes off and the shuffle on, a stand-in who keeps
        their own class may still be re-classed by a guarantee; every need is met and every guard passes."""
        import tracks as TR
        plan, _files = TR.make_all(self.f, "rvclas2", {"classes": False}, {}, ropts={"recruit": "route"})
        self.assertFalse({k for k, v in plan["guards"].items() if not v["ok"]})
        self.assertTrue(all(x["ok"] for x in plan["guarantees"]["needs"]))
        self.assertTrue(plan["guarantees"]["repairs"])

    def test_keys_never_behind_doors(self):
        """Chests on: no door or chest key is placed anywhere (keys never move: chests.STORY_ITEMS)."""
        import chests as CH
        import tracks as TR
        keys = ("IID_扉の鍵", "IID_宝の鍵")
        self.assertTrue(all(k in CH.STORY_ITEMS for k in keys))
        for s in ("g6k1", "g6k2", "g6k3"):
            plan, files = TR.make_all(self.f, s, {}, {"chests": True})
            ents = plan.get("chests") or []
            self.assertTrue(ents, "the chests track made entries")
            for e in ents:
                self.assertFalse(any(str(e.get("new", "")).startswith(k) for k in keys), e)
                self.assertFalse(any(str(e.get("orig", "")).startswith(k) for k in keys), e)
            self.assertTrue(plan["guards"]["chests: story_and_key_items_kept"]["ok"])
            txt = files.get("chests.txt", b"").decode("utf-8", "replace")
            self.assertFalse(any(k in txt for k in keys))


if __name__ == "__main__":
    unittest.main()
