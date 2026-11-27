"""Self-tests for the randomizer's skills track (tools/randomizer/skills.py; docs/rando/SKILLS.md).

    python -m unittest tests.test_rando_skills          (from the repo root)

Made-up tables first (no game data); the last class runs on the user's own extracted RomFS when it is there
(skipped otherwise): many seeds and every mode through every guard, and the mods tool accepts the folder.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
import randolib as R  # noqa: E402
import skills as SK  # noqa: E402

N, NS = "JID_無し男", SK.NONE
RULES = R.load_rules()
MODES = [(a, b) for a in SK.PERSONAL_MODES for b in SK.SLOT_MODES if (a, b) != ("keep", "keep")]


def sk(ix, label, kind=0, f2=0, price=500):
    return {"index": str(ix), "label": label, "mseid_name": "MSEID_" + label, "kind": str(kind),
            "flags_2": str(f2), "price": str(price)}


def job(ix, label, *, female=False, promoted=False, skills=(), promo=(N, N), flags=""):
    f = [x for x in (flags, "SPID_女性" if female else "", "SPID_上級職" if promoted else "") if x]
    j = {"index": str(ix), "label": label, "flags": "|".join(f), "category": "", "origin": "2",
         "mjid_name": "MJID_" + label, "promotion.1": promo[0], "promotion.2": promo[1]}
    for s in R.STATS:
        j[f"base.{s}"], j[f"max.{s}"] = "2", "40"
    for k in R.KINDS:
        j[f"max_weapon_exp.{k}"] = "96" if k == "sword" else "0"
    for i in range(1, 5):
        j[f"skill.{i}"] = skills[i - 1] if i <= len(skills) else NS
    return j


def person(ix, label, jid, low, *, flags="", slots=(), personal=NS, belong="BID_マイユニット軍"):
    p = {"index": str(ix), "label": label, "flags": flags, "belong": belong, "job": jid, "job_low": low,
         "child_id": "65535", "mpid_name": "MPID_" + label, "skill_mask": "32767", "unit_kind": "1"}
    for s in R.STATS:
        p[f"base.{s}"], p[f"growth.{s}"], p[f"limit_mod.{s}"] = "2", "40", "0"
    for k in R.KINDS:
        p[f"weapon_exp.{k}"] = "21" if k == "sword" else "0"
    for i in range(1, 6):
        p[f"skill.{i}"] = slots[i - 1] if i <= len(slots) else NS
    for c in SK.PERSONAL_CELLS:
        p[c] = personal
    return p


SKILLS = [sk(0, NS, price=0), sk(1, "SEID_A1"), sk(2, "SEID_A2"), sk(3, "SEID_P1"), sk(4, "SEID_P2"),
          sk(5, "SEID_B1"), sk(6, "SEID_B2"), sk(7, "SEID_Q1"), sk(8, "SEID_Q2"), sk(9, "SEID_鍵開け", f2=4),
          sk(10, "SEID_ENEMY", f2=5, price=0), sk(11, "SEID_DLC", kind=4, f2=4, price=0),
          sk(12, "SEID_SONG", kind=1), sk(13, "SEID_C1"), sk(14, "SEID_C2")] + \
         [sk(20 + n, f"SEID_PERS{n}", kind=4, f2=9, price=0) for n in range(8)] + \
         [sk(30, "SEID_癒しの声", kind=4, f2=9, price=0), sk(31, "SEID_不思議な魅力", kind=4, f2=9, price=0),
          sk(32, "SEID_炎の血", kind=4, f2=9, price=0)]


def fake_facts():
    jobs = [job(0, N),
            job(1, "JID_ダークプリンス男", skills=("SEID_C1", "SEID_C2")) | {"category": "JCID_マムクート"},
            job(2, "JID_歌姫女", female=True, skills=("SEID_SONG",), flags="SPID_再行動コマンド"),
            job(3, "JID_ソシアルナイト男", skills=("SEID_A1", "SEID_A2"), promo=("JID_パラディン男", N)),
            job(4, "JID_パラディン男", promoted=True, skills=("SEID_P1", "SEID_P2")),
            job(5, "JID_アクスファイター男", skills=("SEID_B1", "SEID_B2"), promo=("JID_ブレイブヒーロー男", N)),
            job(6, "JID_ブレイブヒーロー男", promoted=True, skills=("SEID_Q1", "SEID_Q2")),
            job(7, "JID_シーフ男", skills=("SEID_鍵開け", "SEID_B2"), promo=("JID_ブレイブヒーロー男", N)),
            job(8, "JID_魔戦士男", skills=("SEID_DLC",)),
            job(9, "JID_ノスフェラトゥ男", skills=("SEID_ENEMY",), flags="SPID_敵専用")]
    persons = [person(0, "PID_無し", N, N),
               person(1, "PID_プレイヤー男", "JID_ダークプリンス男", N, flags="SPID_主人公|SPID_マムクート",
                      slots=("SEID_C1",), personal="SEID_不思議な魅力"),
               person(2, "PID_アクア", "JID_歌姫女", N, flags="SPID_女性", slots=("SEID_SONG",),
                      personal="SEID_癒しの声"),
               person(3, "PID_A", "JID_ソシアルナイト男", N, slots=("SEID_A1", "SEID_A2"), personal="SEID_PERS0"),
               person(4, "PID_B", "JID_パラディン男", "JID_ソシアルナイト男", slots=("SEID_A1", "SEID_A2", "SEID_P1"),
                      personal="SEID_PERS1"),
               person(5, "PID_C", "JID_アクスファイター男", N, slots=("SEID_B1",), personal="SEID_PERS2"),
               person(6, "PID_D", "JID_シーフ男", N, slots=("SEID_鍵開け", "SEID_B2"), personal="SEID_PERS3"),
               person(7, "PID_E", "JID_ブレイブヒーロー男", "JID_アクスファイター男", slots=("SEID_B1", "SEID_Q1"),
                      personal="SEID_炎の血"),
               person(8, "PID_F", "JID_アクスファイター男", N, slots=(), personal="SEID_PERS4"),
               person(9, "PID_BAD", "JID_ノスフェラトゥ男", N, flags="SPID_敵専用", slots=("SEID_ENEMY",),
                      personal="SEID_PERS7"),
               person(10, "PID_KID", "JID_ソシアルナイト男", N, slots=("SEID_A1",), personal="SEID_PERS5")]
    persons[10]["child_id"] = "3"
    f = R.Facts(persons, jobs, [], [], [], RULES, {})
    f.skills = SKILLS
    return f


def base_plan(f, moves):
    """A stand-in slice-1 plan: {pid: (job, job_low)} for the people whose class changed."""
    out = []
    for p in f.persons:
        if f.in_scope(p):
            j, low = moves.get(p["label"], (p["job"], p["job_low"]))
            out.append({"pid": p["label"], "job": j, "job_low": low, "old_job": p["job"]})
    return {"persons": out}


class SkillsTests(unittest.TestCase):
    def setUp(self):
        self.f = fake_facts()

    def test_default_is_no_edits(self):
        self.assertEqual(SK.plan_skills(self.f, "s1", {}), ([], []))

    def test_same_seed_same_output_and_seed_matters(self):
        for mode in MODES:
            o = {"personal": mode[0], "slots": mode[1]}
            a = SK.plan_skills(self.f, "seed1", o)
            self.assertEqual(a, SK.plan_skills(self.f, "seed1", o), mode)
        outs = {repr(SK.plan_skills(self.f, f"s{n}", {"personal": "random", "slots": "random"})[0])
                for n in range(30)}
        self.assertGreater(len(outs), 5)

    def test_other_tracks_do_not_disturb(self):
        o = {"personal": "random", "slots": "random"}
        a = SK.plan_skills(self.f, "seed1", o)[0]
        import random
        r = random.Random(5)
        r.random()   # another track drawing first must not matter: the sub-seed comes from the seed text
        self.assertEqual(a, SK.plan_skills(self.f, "seed1", dict(o))[0])

    def test_guards_pass_many_seeds_every_mode(self):
        for mode in MODES:
            for n in range(40):
                bp = base_plan(self.f, {"PID_A": ("JID_アクスファイター男", N),
                                        "PID_B": ("JID_ブレイブヒーロー男", "JID_アクスファイター男"),
                                        "PID_C": ("JID_シーフ男", N)})
                e, _ = SK.plan_skills(self.f, f"g{n}", {"personal": mode[0], "slots": mode[1], "base_plan": bp})
                g = SK.run_guards(self.f, e)
                self.assertTrue(all(v["ok"] for v in g.values()), (mode, n, {k: v for k, v in g.items() if not v["ok"]}))

    def test_only_legal_ids_and_families(self):
        sf = SK.SkillFacts(self.f, SKILLS)
        self.assertNotIn("SEID_ENEMY", sf.slot_pool)
        self.assertNotIn("SEID_DLC", sf.slot_pool)
        self.assertNotIn("SEID_SONG", sf.slot_pool)
        self.assertNotIn("SEID_鍵開け", sf.slot_pool)
        self.assertNotIn("SEID_C1", sf.slot_pool)        # Corrin's line is an excluded class
        self.assertNotIn("SEID_炎の血", sf.personal_pool)
        self.assertNotIn("SEID_PERS7", sf.personal_pool)  # held only by an enemy-only person
        for n in range(30):
            e, _ = SK.plan_skills(self.f, f"l{n}", {"personal": "random", "slots": "random"})
            for ed in e:
                if ed["cell"].startswith("skill."):
                    self.assertIn(ed["new"], sf.slot_pool)
                else:
                    self.assertIn(ed["new"], sf.personal_pool)

    def test_slot_counts_unchanged(self):
        for n in range(30):
            e, _ = SK.plan_skills(self.f, f"c{n}", {"personal": "keep", "slots": "random"})
            after = {p["label"]: dict(p) for p in self.f.persons}
            for ed in e:
                after[ed["label"]][ed["cell"]] = ed["new"]
            for p in self.f.persons:
                self.assertEqual([s != NS for s in SK._slots(p)], [s != NS for s in SK._slots(after[p["label"]])])

    def test_kept_rows_lock_and_story_skills(self):
        for mode in MODES:
            for n in range(20):
                e, _ = SK.plan_skills(self.f, f"k{n}", {"personal": mode[0], "slots": mode[1]})
                touched = {ed["label"] for ed in e}
                self.assertFalse(touched & {"PID_プレイヤー男", "PID_アクア", "PID_BAD", "PID_KID", "PID_無し"})
                self.assertFalse([ed for ed in e if ed["label"] == "PID_D" and ed["cell"] == "skill.1"])
                self.assertFalse([ed for ed in e if ed["label"] == "PID_E" and ed["cell"].startswith("personal")])
                self.assertFalse([ed for ed in e if ed["new"] in SK.KEEP_PERSONAL])

    def test_class_skills_follow_new_class(self):
        bp = base_plan(self.f, {"PID_A": ("JID_アクスファイター男", N),
                                "PID_B": ("JID_ブレイブヒーロー男", "JID_アクスファイター男")})
        e, _ = SK.plan_skills(self.f, "cls", {"personal": "keep", "slots": "class", "base_plan": bp})
        got = {(ed["label"], ed["cell"]): ed["new"] for ed in e}
        self.assertEqual(got[("PID_A", "skill.1")], "SEID_B1")
        self.assertEqual(got[("PID_A", "skill.2")], "SEID_B2")
        self.assertEqual(got[("PID_B", "skill.1")], "SEID_B1")
        self.assertEqual(got[("PID_B", "skill.2")], "SEID_B2")
        self.assertEqual(got[("PID_B", "skill.3")], "SEID_Q1")
        # no class change -> nothing in class mode; a lock skill stays where it is
        self.assertFalse([k for k in got if k[0] in ("PID_C", "PID_D", "PID_E")])

    def test_class_mode_no_base_plan_is_no_slot_change(self):
        e, _ = SK.plan_skills(self.f, "cls", {"personal": "keep", "slots": "class"})
        self.assertEqual(e, [])

    def test_shuffle_is_a_permutation(self):
        e, _ = SK.plan_skills(self.f, "sh", {"personal": "shuffle", "slots": "keep"})
        after = {p["label"]: p["personal_skill.normal"] for p in self.f.persons if self.f.in_scope(p)}
        for ed in e:
            if ed["cell"] == "personal_skill.normal":
                after[ed["label"]] = ed["new"]
        before = sorted(p["personal_skill.normal"] for p in self.f.persons if self.f.in_scope(p))
        self.assertEqual(sorted(after.values()), before)

    def test_guard_catches_bad_edits(self):
        bad = [{"table": "Person", "index": 3, "label": "PID_A", "cell": "skill.1", "old": "SEID_A1", "new": "SEID_ENEMY"},
               {"table": "Person", "index": 3, "label": "PID_A", "cell": "skill.3", "old": NS, "new": "SEID_B1"},
               {"table": "Person", "index": 6, "label": "PID_D", "cell": "skill.1", "old": "SEID_鍵開け", "new": "SEID_B1"},
               {"table": "Person", "index": 1, "label": "PID_プレイヤー男", "cell": "skill.1", "old": "SEID_C1",
                "new": "SEID_A1"}]
        g = SK.run_guards(self.f, bad)
        failed = {k for k, v in g.items() if not v["ok"]}
        self.assertIn("each cell keeps its family (slot: class-taught; personal: personal family)", failed)
        self.assertIn("filled slots unchanged in number and place", failed)
        self.assertIn("lock-opening skill never taken away (door-opener guard)", failed)
        self.assertIn("Corrin and the singer untouched", failed)
        self.assertTrue(g["only the 49 people's skill cells"]["ok"])

    def test_bad_opts_refused(self):
        with self.assertRaises(R.RandoError):
            SK.plan_skills(self.f, "x", {"personal": "all"})
        with self.assertRaises(R.RandoError):
            SK.plan_skills(self.f, "x", {"slots": "new"})

    def test_csv_merge_keeps_other_rows(self):
        e = [{"table": "Person", "index": 5, "label": "PID_C", "cell": "skill.1", "old": "SEID_B1", "new": "SEID_A1"}]
        head = ["index", "label"] + R.PERSON_COLS
        p3 = self.f.by_pid["PID_A"]
        src = R._csv([head, ["3", "PID_A"] + [p3[c] for c in R.PERSON_COLS]])
        out = SK.person_csv_with_edits(self.f, src, e).decode("utf-8").lstrip("﻿").splitlines()
        self.assertEqual(len(out), 3)
        self.assertTrue(out[2].startswith("5,PID_C,"))
        self.assertIn("SEID_A1", out[2])


def _real():
    try:
        import gamedata as GD
        return None if GD.available() else GD
    except Exception:  # noqa: BLE001
        return None


GD = _real()


@unittest.skipIf(GD is None, "no extracted RomFS / table layouts here")
class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = GD.load_facts()
        cls.f.skills = SK.load_skill_rows()

    def test_every_mode_many_seeds(self):
        sf = SK.SkillFacts(self.f, self.f.skills)
        self.assertEqual(sum(1 for p in self.f.persons if self.f.in_scope(p)), 49)
        for n in range(12):
            plan = R.make_plan(self.f, f"real{n}", {})
            for mode in MODES:
                o = {"personal": mode[0], "slots": mode[1], "base_plan": plan}
                e, _ = SK.plan_skills(self.f, f"real{n}", o)
                g = SK.run_guards(self.f, e)
                self.assertTrue(all(v["ok"] for v in g.values()), (n, mode, {k: v for k, v in g.items() if not v["ok"]}))
                self.assertEqual(e, SK.plan_skills(self.f, f"real{n}", o)[0])
                for ed in e:
                    self.assertIn(ed["new"], sf.rows)

    def test_route_variant_rows_follow_their_main_row(self):
        """Round 61 (build/r60/screens/plans/SKILLS_VARIANTS.md): every HANDOVER row of a main person whose slots
        changed has the matching change (Revelation's Elise, Arthur, Effie join from those rows); keep = none."""
        rows = SK.variant_rows(self.f)
        self.assertTrue(rows)
        seen = 0
        for n in range(8):
            seed = f"realv{n}"
            plan = R.make_plan(self.f, seed, {})
            for mode in MODES:
                o = {"personal": mode[0], "slots": mode[1], "base_plan": plan}
                e, _ = SK.plan_skills(self.f, seed, o)
                main = {(ed["label"], ed["cell"]): ed["new"] for ed in e if "file" not in ed}
                var = {(ed["file"], ed["label"], ed["cell"]): ed["new"] for ed in e if "file" in ed}
                for h, p in rows:
                    old_p = SK._slots(p)
                    new_p = [main.get((p["label"], f"skill.{i + 1}"), s) for i, s in enumerate(old_p)]
                    pm = dict(zip(old_p, new_p))
                    for i, s in enumerate(SK._slots(h)):
                        if s != SK.NONE and s in pm:
                            got = var.get((h["file"], h["label"], f"skill.{i + 1}"), s)
                            self.assertEqual(got, pm[s], (seed, mode, h["label"], i))
                            seen += got != s
                    for c in SK.PERSONAL_CELLS:
                        if h.get(c) == p.get(c):
                            self.assertEqual(var.get((h["file"], h["label"], c), h.get(c)),
                                             main.get((p["label"], c), p.get(c)), (seed, mode, h["label"], c))
                self.assertTrue(all(v["ok"] for v in SK.run_guards(self.f, e).values()))
        self.assertGreater(seen, 0)

    def test_route_variant_guard_catches_a_lagging_row(self):
        plan = R.make_plan(self.f, "realv0", {})
        e, _ = SK.plan_skills(self.f, "realv0", {"personal": "keep", "slots": "random", "base_plan": plan})
        var = [ed for ed in e if "file" in ed and ed["cell"].startswith("skill.")]
        self.assertTrue(var)
        g = SK.run_guards(self.f, [ed for ed in e if ed is not var[0]])
        self.assertFalse(g["route-variant rows follow their main row (shared skills and personal skill)"]["ok"]
                         and g["route-variant rows: no skill twice in one row's slots"]["ok"])

    def test_mods_tool_accepts_the_folder(self):
        sys.path.insert(0, os.path.join(ROOT, "tools", "mods"))
        import mods as M
        with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, "build")) as d:
            folder, guards, edits = SK.make_folder("r49test", {"personal": "shuffle", "slots": "class"},
                                                   os.path.join(d, "mods"), facts=self.f)
            self.assertTrue(all(v["ok"] for v in guards.values()))
            ctx = M.Ctx(mods_dir=os.path.join(d, "mods"), stage_dir=os.path.join(d, "stage"),
                        zakuro_dir=os.path.join(d, "zak"))
            r = M.compute(ctx)
            self.assertFalse(r.errors, r.errors[:5])


if __name__ == "__main__":
    unittest.main()
