"""Self-tests for the randomizer's children track (tools/randomizer/children.py; docs/rando/CHILDREN.md).

    python -m unittest tests.test_rando_children          (from the repo root)

Made-up tables first (slice 1's small cast plus a few made-up children: a healer, a beast, a dragon, a door
opener and an enemy-side recruit); the last class runs on the user's own extracted RomFS when it is there
(skipped otherwise).
"""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
sys.path.insert(0, ROOT)
import randolib as R  # noqa: E402
import children as C  # noqa: E402
from tests.test_randomizer import fake_facts, person, disp, job, RULES  # noqa: E402

SEEDS = [f"k{i}" for i in range(50)]
N = "JID_無し男"
ON = {"children": True}
OPTION_SETS = [ON, dict(ON, trees="any"), dict(ON, growth_mode="full", bases_mode="redistribute"),
               dict(ON, growth_mode="delta", bases_mode="delta", adjust_hp=True),
               dict(ON, personal_skills="shuffle", skill_slots="class"), dict(ON, personal_skills="random"),
               dict(ON, classes=False, growths=False, join_stats=False, personal_skills="shuffle")]


def skill(label, flags_2=0, kind=0, price=100):
    return {"label": label, "flags_2": str(flags_2), "kind": str(kind), "price": str(price), "mseid_name": ""}


SKILLS = [skill("SEID_無し"), skill("SEID_鍵開け"), skill("SEID_剣+2"), skill("SEID_槍+2"),
          skill("SEID_P1", 9), skill("SEID_P2", 9), skill("SEID_P3", 9), skill("SEID_P4", 9), skill("SEID_P5", 9),
          skill("SEID_P6", 9), skill("SEID_P7", 9)]


def kid_facts() -> R.Facts:
    """Slice 1's cast plus children. family_index points at a parent row (index)."""
    f = fake_facts()
    jobs = [dict(j) for j in f.job_list]
    for j in jobs:
        j.setdefault("gender_pair", N)
        j.setdefault("parallel_class", N)
        j.setdefault("skill.1", "SEID_無し")
    by = {j["label"]: j for j in jobs}
    by["JID_ソシアルナイト男"]["gender_pair"] = "JID_ソシアルナイト女"
    by["JID_ソシアルナイト女"]["gender_pair"] = "JID_ソシアルナイト男"
    by["JID_ソシアルナイト男"]["skill.1"] = "SEID_剣+2"
    by["JID_アクスファイター男"]["skill.1"] = "SEID_槍+2"
    by["JID_ロッドナイト男"]["parallel_class"] = "JID_侍男"
    by["JID_ロッドナイト女"]["parallel_class"] = "JID_侍男"      # made up: a parallel class a son can take
    by["JID_ロッドナイト女"]["gender_pair"] = "JID_ロッドナイト男"
    by["JID_ロッドナイト男"]["gender_pair"] = "JID_ロッドナイト女"
    by["JID_歌姫女"]["flags"] += "|SPID_継承禁止"
    jobs.append(job(21, "JID_ガルー女", female=True, kinds=("stone",), cat="JCID_獣|JCID_ラグズ"))
    jobs.append(job(22, "JID_ダークプリンセス女", female=True, kinds=("sword", "stone"), cat="JCID_竜|JCID_マムクート"))
    for j in jobs[-2:]:
        j.update({"gender_pair": N, "parallel_class": N, "skill.1": "SEID_無し"})
    persons = [dict(p) for p in f.persons]
    for p in persons:
        p.setdefault("family_index", "0")
        p.setdefault("reclass.1", N)
        p["personal_skill.normal"] = "SEID_P" + str(1 + int(p["index"]) % 7) if p["label"] != "PID_KID" else "SEID_P7"
    persons[2]["reclass.1"] = "JID_ソシアルナイト女"      # the singer passes on her Heart Seal class
    kids = [
        person(14, "PID_KID_HEAL", "JID_ロッドナイト女", "JID_ストラテジスト女", female=True, child=True,
               wexp={"staff": 21}),
        person(15, "PID_KID_BEAST", "JID_ガルー女", N, female=True, child=True, flags="SPID_ラグズ", wexp={"stone": 1}),
        person(16, "PID_KID_DRAGON", "JID_ダークプリンセス女", N, female=True, child=True, flags="SPID_マムクート",
               wexp={"sword": 21, "stone": 21}),
        person(17, "PID_KID_THIEF", "JID_シーフ男", "JID_パラディン男", child=True, wexp={"bow": 21},
               skills=("SEID_鍵開け",)),
        person(18, "PID_KID_AXE", "JID_アクスファイター男", "JID_パラディン男", child=True, wexp={"axe": 21},
               skills=("SEID_槍+2",)),
        person(19, "PID_KID_SING", "JID_ソシアルナイト男", "JID_パラディン男", child=True, wexp={"sword": 21}),
    ]
    for n, p in enumerate(kids):
        p["family_index"] = ["5", "9", "1", "7", "6", "2"][n]
        p["reclass.1"] = N
        p["personal_skill.normal"] = ["SEID_P1", "SEID_P2", "SEID_P3", "SEID_P4", "SEID_P5", "SEID_P6"][n]
    persons[11]["family_index"] = "4"
    persons += kids
    dispos = list(f.dispos) + [
        disp("X002", 0, "PID_KID_HEAL", 2, "IID_ライブ", "IID_リライブ"),
        disp("X003", 0, "PID_KID_BEAST", 0, "IID_獣石", "IID_傷薬"),
        disp("X004", 0, "PID_KID_DRAGON", 0, "IID_鉄の剣"),
        disp("X005", 0, "PID_KID_THIEF", 2, "IID_鉄の弓"),
        disp("X006", 0, "PID_KID_AXE", 1, "IID_鉄の斧", "IID_傷薬"),
        disp("X006", 1, "PID_KID_AXE", 0, "IID_鉄の斧", "IID_鋼の斧"),
        disp("X007", 0, "PID_KID_SING", 0, "IID_鉄の剣", "IID_鉄の槍"),
    ]
    subs = [{"index": str(i), "kind": str(k), "origin": str(f.sub_origin[i])} for i, k in sorted(f.sub_kind.items())]
    out = R.Facts(persons, jobs, f.item_list, subs, dispos, RULES, {})
    out.skills = SKILLS
    return out


KIDS = {"PID_KID", "PID_KID_HEAL", "PID_KID_BEAST", "PID_KID_DRAGON", "PID_KID_THIEF", "PID_KID_AXE", "PID_KID_SING"}


def new_rows(f, edits):
    persons, dispos = C.rows_after(f, edits)
    return (lambda pid: persons.get(pid) or f.by_pid[pid]), dispos


class ChildrenTrackTests(unittest.TestCase):
    def setUp(self):
        self.f = kid_facts()

    def test_children_listed(self):
        self.assertEqual({p["label"] for p in C.children(self.f)}, KIDS)

    def test_off_means_no_edits_and_slice1_unchanged(self):
        for seed in SEEDS:
            for opts in ({}, {"children": False}, {"children": False, "growth_mode": "full",
                                                     "personal_skills": "random"}):
                self.assertEqual(C.plan_children(self.f, seed, opts), ([], []))
                self.assertTrue(C.guards_ok(C.run_guards(self.f, [], opts)))
        a = R.render(self.f, R.make_plan(self.f, "abc"))
        C.plan_children(self.f, "abc", ON)
        self.assertEqual(a, R.render(kid_facts(), R.make_plan(kid_facts(), "abc")))
        files = R.render(self.f, R.make_plan(self.f, "abc"))
        self.assertIs(C.files_with_edits(self.f, files, []), files)

    def test_off_guard_catches_edits(self):
        edits, _ = C.plan_children(self.f, "k1", ON)
        self.assertTrue(edits)
        self.assertFalse(C.run_guards(self.f, edits, {})["off_means_no_edits"]["ok"])

    def test_guards_hold_over_50_seeds(self):
        for opts in OPTION_SETS:
            for seed in SEEDS:
                edits, lines = C.plan_children(self.f, seed, opts)
                gd = C.run_guards(self.f, edits, opts)
                for k, v in gd.items():
                    self.assertTrue(v["ok"], (opts, seed, k, v["detail"][:3]))
                self.assertTrue(lines[0].startswith("Children track"))

    def test_job_low_follows_final_promotions(self):
        """Round W1 (WIRE_56 2a): with the promotions track's final promotions passed in (job_promotions), every
        child's job_low is one of its class's new promotions, and the guard reads the same list."""
        f = self.f
        jp = {}
        for jid, j in f.jobs.items():
            ups = [j.get("promotion.1"), j.get("promotion.2")]
            jp[jid] = list(reversed(ups)) if all(u in f.jobs for u in ups) else ups
        # swap a two-promotion base class's targets for another class's, so the old job_low no longer fits
        bases = [jid for jid, j in f.jobs.items() if not f.promoted(j) and len(C.promo_ups(f, jid)) >= 1]
        promoted = [jid for jid, j in f.jobs.items() if f.promoted(j) and not f.excluded_job(jid)]
        for b in bases:
            fem = f.female(f.jobs[b])
            other = [x for x in promoted if f.female(f.jobs[x]) == fem and x not in C.promo_ups(f, b)]
            if other:
                jp[b] = [other[0], jp[b][1] if len(jp[b]) > 1 else None]
        for seed in SEEDS[:20]:
            o = dict(ON, job_promotions=jp)
            edits, _ = C.plan_children(f, seed, o)
            row, _d = new_rows(f, edits)
            for pid in KIDS:
                n = row(pid)
                if not f.promoted(f.jobs[n["job"]]) and C.promo_ups(f, n["job"], jp):
                    self.assertIn(n["job_low"], C.promo_ups(f, n["job"], jp), (seed, pid))
            gd = C.run_guards(f, edits, o)
            self.assertTrue(gd["promotion_line_legal"]["ok"], (seed, gd["promotion_line_legal"]["detail"][:3]))

    def test_legal_classes_explicitly(self):
        moved = set()
        for opts in (ON, dict(ON, trees="any")):
            sw = dict(R.DEFAULT_SWITCHES, trees=opts.get("trees", "own"))
            for seed in SEEDS:
                edits, _ = C.plan_children(self.f, seed, opts)
                row, _ = new_rows(self.f, edits)
                for pid in KIDS:
                    p, n = self.f.by_pid[pid], row(pid)
                    oj, nj = self.f.jobs[p["job"]], self.f.jobs[n["job"]]
                    self.assertEqual(self.f.female(nj), self.f.female(p), (seed, pid))
                    self.assertEqual(self.f.promoted(nj), self.f.promoted(oj), (seed, pid))
                    self.assertEqual("JCID_ラグズ" in nj["category"], "SPID_ラグズ" in p["flags"], (seed, pid))
                    if n["job"] != p["job"]:
                        moved.add(pid)
                        self.assertIsNone(self.f.excluded_job(n["job"]), (seed, pid))
                        self.assertIn(n["job"], R.Facts.legal_classes(self.f, p, sw))
                        if sw["trees"] == "own":
                            self.assertEqual(nj["origin"], oj["origin"])
                self.assertEqual(row("PID_KID_DRAGON")["job"], "JID_ダークプリンセス女")   # the dragon keeps it
        self.assertTrue({"PID_KID", "PID_KID_AXE", "PID_KID_SING", "PID_KID_THIEF"} <= moved, moved)

    def test_healer_stays_healer_and_fighters_keep_a_weapon(self):
        staff = RULES["staff_kind"]
        for seed in SEEDS:
            edits, _ = C.plan_children(self.f, seed, dict(ON, trees="any"))
            row, dispos = new_rows(self.f, edits)
            self.assertGreater(self.f.wexp_max(self.f.jobs[row("PID_KID_HEAL")["job"]])[staff], 0)
            for pid in ("PID_KID", "PID_KID_AXE", "PID_KID_SING", "PID_KID_THIEF"):
                n = row(pid)
                wexp = [R.ival(n[f"weapon_exp.{k}"]) for k in R.KINDS]
                for d in self.f.placements(pid):
                    nd = dispos.get((d["file"], R.ival(d["index"])), d)
                    ok = [nd[f"item_{s}"] for s in range(1, 6)
                          if self.f.item_kind(nd[f"item_{s}"]) not in (None, staff)
                          and self.f.class_can_hold(n["job"], self.f.by_pid[pid], nd[f"item_{s}"], wexp) is None]
                    self.assertTrue(ok, (seed, pid, d["file"], [nd[f"item_{s}"] for s in range(1, 6)]))

    def test_only_children_rows_and_their_placements(self):
        for seed in SEEDS[:20]:
            edits, _ = C.plan_children(self.f, seed, dict(ON, personal_skills="shuffle", skill_slots="class"))
            for e in edits:
                if e["table"] == "Person":
                    self.assertIn(e["label"], KIDS)
                    self.assertIn(e["cell"], C.PERSON_CELLS)
                else:
                    self.assertEqual(e["table"], "DisposUnit")
                    self.assertTrue(e["column"].startswith("item_"))
                    d = [x for x in self.f.dispos if x["file"] == e["file"] and R.ival(x["index"]) == e["index"]][0]
                    self.assertIn(d["pid"], KIDS)
                self.assertNotEqual(e["old"], e["new"])

    def test_same_seed_same_edits_and_own_subseed(self):
        a = C.plan_children(self.f, "same", dict(ON, growth_mode="full", personal_skills="random"))
        b = C.plan_children(kid_facts(), "same", dict(ON, growth_mode="full", personal_skills="random"))
        self.assertEqual(a, b)
        self.assertNotEqual(C.plan_children(self.f, "same", ON)[0], C.plan_children(self.f, "other", ON)[0])
        self.assertNotEqual(C.sub_seed("same"), "same")
        R.check_seed(C.sub_seed("same"))

    def test_lock_skill_kept(self):
        for seed in SEEDS:
            edits, _ = C.plan_children(self.f, seed, dict(ON, trees="any", skill_slots="class",
                                                          personal_skills="random"))
            row, _ = new_rows(self.f, edits)
            self.assertEqual(row("PID_KID_THIEF")["skill.1"], "SEID_鍵開け", seed)

    def test_personal_skills(self):
        fam = {s["label"] for s in SKILLS if int(s["flags_2"]) & 8}
        orig = sorted(self.f.by_pid[p]["personal_skill.normal"] for p in KIDS)
        changed = 0
        for seed in SEEDS:
            for mode in ("shuffle", "random"):
                edits, _ = C.plan_children(self.f, seed, dict(ON, personal_skills=mode))
                row, _ = new_rows(self.f, edits)
                got = [row(p)["personal_skill.normal"] for p in KIDS]
                self.assertTrue(set(got) <= fam)
                for p in KIDS:
                    self.assertEqual(len({row(p)[c] for c in C.PERSONAL_CELLS}), 1)
                if mode == "shuffle":
                    self.assertEqual(sorted(got), orig)
                else:
                    self.assertEqual(len(set(got)), len(got))
                changed += got != [self.f.by_pid[p]["personal_skill.normal"] for p in KIDS]
        self.assertGreater(changed, 50)

    def test_random_personal_avoids_taken(self):
        for seed in SEEDS[:10]:
            edits, _ = C.plan_children(self.f, seed, dict(ON, personal_skills="random",
                                                          taken_personal=["SEID_P1", "SEID_P2"]))
            row, _ = new_rows(self.f, edits)
            for p in KIDS:
                if any(e["label"] == p and e["cell"] == "personal_skill.normal" for e in edits):
                    self.assertNotIn(row(p)["personal_skill.normal"], ("SEID_P1", "SEID_P2"))

    def test_random_personal_short_pool_no_duplicates(self):
        """Round W1 (found by the wiring sweep): when the adults hold most personal skills (taken_personal), the
        children that get no free skill keep their own, and no other child draws it."""
        fam = sorted({s["label"] for s in SKILLS if int(s["flags_2"]) & 8})
        own = {self.f.by_pid[p]["personal_skill.normal"] for p in KIDS}
        for keep_free in (0, 1, 2, 3):
            free = [x for x in fam if x not in own][:keep_free]
            taken = [x for x in fam if x not in free]
            for seed in SEEDS[:15]:
                o = dict(ON, personal_skills="random", taken_personal=taken)
                edits, _ = C.plan_children(self.f, seed, o)
                gd = C.run_guards(self.f, edits, o)
                self.assertTrue(gd["personal_skills_unique"]["ok"], (keep_free, seed, gd["personal_skills_unique"]))

    def test_bad_options_refused(self):
        for bad in ({"trees": "x"}, {"growth_mode": "wild"}, {"skill_slots": "random"}, {"growth_variance": 101},
                    {"base_variance": 0}):
            with self.assertRaises(R.RandoError):
                C.check_opts(dict(ON, **bad))

    def test_inherited_class_rule(self):
        f = self.f
        kid = f.by_pid["PID_KID"]                  # male Cavalier
        par = dict(f.by_pid["PID_C"])              # Fighter (axe): passes on Fighter
        self.assertEqual(C.inherited_class(f, par, kid, "JID_ソシアルナイト男"), "JID_アクスファイター男")
        par = dict(f.by_pid["PID_H"])              # promoted Paladin -> its base class: the child's own: rejected
        self.assertIsNone(C.inherited_class(f, par, kid, "JID_ソシアルナイト男"))
        self.assertEqual(C.inherited_class(f, par, kid, "JID_アクスファイター男"), "JID_ソシアルナイト男")
        par = dict(f.by_pid["PID_B"])              # female Troubadour -> the male twin
        self.assertEqual(C.inherited_class(f, par, kid, "JID_ソシアルナイト男"), "JID_ロッドナイト男")
        par = dict(f.by_pid["PID_B"], job="JID_ロッドナイト女")
        kid2 = dict(kid, job="JID_ロッドナイト男")   # same class as the child: the parallel class instead
        self.assertEqual(C.inherited_class(f, par, kid2, "JID_ロッドナイト男"), "JID_侍男")
        singer = f.by_pid["PID_アクア"]              # banned class -> her reclass.1 (Cavalier; male twin for a son)
        self.assertEqual(C.inherited_class(f, singer, kid, "JID_アクスファイター男"), "JID_ソシアルナイト男")
        # the parent's class as slice 1 changed it is what counts (the game reads the Person row)
        self.assertEqual(C.inherited_class(f, f.by_pid["PID_C"], kid, "JID_ソシアルナイト男",
                                           parent_job="JID_シーフ男", parent_low="JID_パラディン男"), "JID_シーフ男")

    def test_files_with_edits(self):
        base = R.make_plan(self.f, "files")
        edits, lines = C.plan_children(self.f, "files", dict(ON, personal_skills="shuffle", base_plan=base))
        files = C.files_with_edits(self.f, R.render(self.f, base), edits)
        person = files["tables/Person.csv"].decode("utf-8-sig")
        head = person.split("\n")[0].split(",")
        self.assertEqual(head[:2 + len(R.PERSON_COLS)], ["index", "label"] + R.PERSON_COLS)
        self.assertIn("personal_skill.normal", head)
        for pid in {e["label"] for e in edits if e["table"] == "Person"}:
            self.assertIn("," + pid + ",", person)
        if any(e["table"] == "DisposUnit" for e in edits):
            self.assertIn("X00", files["tables/DisposUnit.csv"].decode("utf-8-sig"))
        self.assertTrue(any("inherits from" in x for x in lines))


def _real():
    try:
        import gamedata as GD
        return None if GD.available() else GD
    except Exception:  # noqa: BLE001
        return None


GD = _real()


@unittest.skipIf(GD is None, "no extracted RomFS / table layouts here")
class RealDataChildrenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = GD.load_facts(names=False)
        import skills as S
        cls.f.skills = S.load_skill_rows()

    def test_real_children_listed(self):
        kids = C.children(self.f)
        self.assertEqual(len(kids), 22)                     # 20 paralogue children and the two Kana rows
        for p in kids:
            self.assertTrue(any(c.startswith(("X", "Z")) for c in C.join_chapters(self.f, p["label"])), p["label"])

    def test_real_guards_hold_over_50_seeds(self):
        for opts, n in ((ON, 50), (dict(ON, trees="any", personal_skills="random"), 20),
                        (dict(ON, growth_mode="redistribute", bases_mode="delta", personal_skills="shuffle",
                              skill_slots="class"), 20)):
            for i in range(n):
                edits, _ = C.plan_children(self.f, f"real{i}", opts)
                self.assertTrue(edits)
                for k, v in C.run_guards(self.f, edits, opts).items():
                    self.assertTrue(v["ok"], (opts, i, k, v["detail"][:3]))

    def test_real_off_is_empty(self):
        self.assertEqual(C.plan_children(self.f, "real", {}), ([], []))


if __name__ == "__main__":
    unittest.main()
