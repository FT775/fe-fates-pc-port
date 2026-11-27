"""Self-tests for the randomizer track "misc": enemy drops, assign evenly, class movement
(tools/randomizer/misc.py; docs/rando/MISC.md).

    python -m unittest tests.test_rando_misc          (from the repo root)

Small made-up tables (no game data), borrowed from the slice-1 and enemies tests. The last class runs on the
user's own extracted RomFS when it is there (skipped otherwise): several seeds through every guard.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
sys.path.insert(0, ROOT)
import misc as M  # noqa: E402
import randolib as R  # noqa: E402
from tests import test_rando_enemies as TE  # noqa: E402
from tests import test_randomizer as TR  # noqa: E402

N = "JID_無し男"
ON = {"enemy_drops": 100, "class_move": "wide", "assign_evenly": True}


def bad_of(g: dict) -> dict:
    return {k: v["detail"] for k, v in g.items() if not v["ok"]}


def drop_tables():
    """The enemies test tables, plus a unit that already drops, one with a precious item and one with a forge."""
    more = [TE.disp("A011", 3, "PID_A011_斧", 1, 6, 6, "IID_鉄の斧", "IID_傷薬"),
            TE.disp("A011", 4, "PID_A011_斧", 1, 7, 7, "IID_鉄の斧", "IID_獣石"),
            TE.disp("A011", 5, "PID_A011_斧", 1, 8, 8, "IID_鋼の斧")]
    more[0]["item_2_flags"] = "1"                                  # already drops its vulnerary
    more[2]["item_1_forge.normal"] = "2"                           # a forged axe: never marked
    t = TE.fake(more_dispos=more)
    t.f.items["IID_獣石"] = TE.item(20, "IID_獣石", 15, 1, 2000, "ISID_貴重品")
    t.group[("GameData/Dispos/A011.bin.lz", 3)] = "Enemy"
    t.group[("GameData/Dispos/A011.bin.lz", 4)] = "Enemy"
    t.group[("GameData/Dispos/A011.bin.lz", 5)] = "Enemy"
    return t


def move_tables():
    """Enemies test tables with promotion links and gender pairs, so the Move rules have something to hold."""
    t = TE.fake()
    jobs = t.f.job_list
    extra = [TE.job(17, "JID_ソシアルナイト女", kinds=("sword", "lance"), female=True, mov=7, mc=3, cat="JCID_騎乗"),
             TE.job(18, "JID_パラディン男", kinds=("sword", "lance"), promoted=True, mov=8, mc=3, cat="JCID_騎乗"),
             TE.job(19, "JID_パラディン女", kinds=("sword", "lance"), promoted=True, female=True, mov=8, mc=3,
                    cat="JCID_騎乗"),
             TE.job(20, "JID_バーサーカー男", kinds=("axe",), promoted=True, mov=6, mc=1)]
    for j in jobs + extra:
        t.f.jobs[j["label"]] = j
    t.f.jobs["JID_ソシアルナイト男"]["promotion.1"] = "JID_パラディン男"
    t.f.jobs["JID_ソシアルナイト女"]["promotion.1"] = "JID_パラディン女"
    t.f.jobs["JID_アクスファイター男"]["promotion.1"] = "JID_バーサーカー男"
    t.f.jobs["JID_マーシナリー男"]["promotion.1"] = "JID_バーサーカー男"
    t.f.job_list = sorted(t.f.jobs.values(), key=lambda j: int(j["index"]))
    return t


class Options(unittest.TestCase):
    def test_off_is_default_and_inactive(self):
        self.assertFalse(M.active(None))
        self.assertFalse(M.active(M.DEFAULT_OPTS))
        self.assertTrue(M.active({"enemy_drops": 5}))
        self.assertTrue(M.active({"class_move": "small"}))
        self.assertTrue(M.active({"assign_evenly": True}))

    def test_bad_options_refused(self):
        for o in ({"enemy_drops": 7}, {"enemy_drops": 105}, {"class_move": "huge"}):
            with self.assertRaises(R.RandoError):
                M.check_opts(o)
        self.assertEqual(M.check_opts({"enemy_drops": "25%"})["enemy_drops"], 25)
        self.assertEqual(M.check_opts({"enemy_drops": "off"})["enemy_drops"], 0)

    def test_sub_seed_is_the_tracks_own(self):
        self.assertEqual(M.track_key("abc"), M.track_key("abc"))
        self.assertNotEqual(M.track_key("abc"), M.track_key("abd"))
        with self.assertRaises(R.RandoError):
            M.track_key("bad seed!")

    def test_off_makes_no_edits_anywhere(self):
        t = drop_tables()
        self.assertEqual(M.plan_drops(t, "s1", None), ([], []))
        self.assertEqual(M.plan_movement(move_tables(), "s1", None), ([], []))
        f = TR.fake_facts()
        plan = R.make_plan(f, "s1")
        self.assertEqual(M.assign_evenly(f, plan, "s1", None), ({}, []))
        p2, lines = M.make_plan_even(f, "s1", None, None)
        self.assertEqual(json.dumps(p2, sort_keys=True, ensure_ascii=False),
                         json.dumps(plan, sort_keys=True, ensure_ascii=False))
        self.assertEqual(lines, [])
        files = {"tables/Job.csv": b"x", "tables/DisposUnit.csv": b"y"}
        self.assertIs(M.job_csv_with_edits(f, files, []), files)
        self.assertIs(M.dispos_csv_with_edits([], files, []), files)


class Drops(unittest.TestCase):
    def test_guards_pass_many_seeds_and_chances(self):
        t = drop_tables()
        for n in range(40):
            for ch in (5, 50, 100):
                o = {"enemy_drops": ch}
                e, _l = M.plan_drops(t, f"s{n}", o)
                self.assertFalse(bad_of(M.run_drop_guards(t, e, o)), (n, ch))

    def test_same_seed_same_edits(self):
        a = M.plan_drops(drop_tables(), "abc", {"enemy_drops": 50})[0]
        self.assertEqual(a, M.plan_drops(drop_tables(), "abc", {"enemy_drops": 50})[0])
        self.assertTrue(any(M.plan_drops(drop_tables(), f"x{n}", {"enemy_drops": 50})[0] != a for n in range(6)))

    def test_what_gets_marked(self):
        t = drop_tables()
        e, lines = M.plan_drops(t, "s1", {"enemy_drops": 100})
        by = {(x["file"], x["index"]): x for x in e}
        a10 = "GameData/Dispos/A010.bin.lz"
        a11 = "GameData/Dispos/A011.bin.lz"
        self.assertEqual(by[(a10, 1)]["column"], "item_2_flags")    # the vulnerary, not the axe
        self.assertEqual((by[(a10, 1)]["old"], by[(a10, 1)]["new"]), ("0", "1"))
        self.assertEqual(by[(a10, 2)]["column"], "item_2_flags")    # the gold, not the sword
        self.assertNotIn((a11, 3), by)                               # already drops: left alone
        self.assertEqual(by[(a11, 4)]["column"], "item_1_flags")    # the precious stone never, the axe yes
        self.assertNotIn((a11, 5), by)                               # forged: never
        self.assertNotIn((a10, 15), by)                              # an enemy-only sword never drops
        for k in [(a10, 0), (a10, 10), (a10, 14), (a10, 17)] + [(f"GameData/Dispos/{g}.bin.lz", 0)
                                                                          for g in ("B009", "B016", "C008", "C013")]:
            self.assertNotIn(k, by)                                  # player, scripted, event, other army, guarded
        self.assertIn("100%", lines[0])

    def test_guard_catches_bad_edits(self):
        t = drop_tables()
        e, _ = M.plan_drops(t, "s1", {"enemy_drops": 100})
        o = {"enemy_drops": 100}
        x = dict(e[0], new="3")
        self.assertFalse(M.run_drop_guards(t, [x] + e[1:], o)["drops_only_on_ordinary_items_of_unscripted_enemies"]["ok"])
        x = {"table": "DisposUnit", "file": "GameData/Dispos/A010.bin.lz", "index": 15, "label": "",
             "column": "item_1_flags", "old": "0", "new": "1"}
        self.assertFalse(M.run_drop_guards(t, e + [x], o)["drops_only_on_ordinary_items_of_unscripted_enemies"]["ok"])
        y = dict(e[0], column="item_1_flags" if e[0]["column"] != "item_1_flags" else "item_2_flags")
        self.assertFalse(M.run_drop_guards(t, e + [y], o)["at_most_one_new_drop_per_enemy"]["ok"])
        self.assertFalse(M.run_drop_guards(t, e, None)["drops_off_no_edits"]["ok"])

    def test_dispos_csv_merge_keeps_other_tracks_cells(self):
        t = drop_tables()
        e, _ = M.plan_drops(t, "s1", {"enemy_drops": 100})
        k = e[0]
        other = R._csv([["file", "index", "label", "item_1"], [k["file"], str(k["index"]), "", "IID_鋼の斧"]])
        out = M.dispos_csv_with_edits(t.dispos, {"tables/DisposUnit.csv": other}, e)
        rows = M._read_csv(out["tables/DisposUnit.csv"])
        head = rows[0]
        self.assertEqual(head[:4], ["file", "index", "label", "item_1"])
        row = [r for r in rows[1:] if r[0] == k["file"] and r[1] == str(k["index"])][0]
        self.assertEqual(row[3], "IID_鋼の斧")
        self.assertEqual(row[head.index(k["column"])], "1")
        self.assertEqual(len(rows) - 1, len({(x["file"], x["index"]) for x in e}))


class Movement(unittest.TestCase):
    def test_guards_pass_many_seeds(self):
        t = move_tables()
        for n in range(40):
            for mode in ("small", "wide"):
                o = {"class_move": mode}
                e, _l = M.plan_movement(t, f"s{n}", o)
                self.assertFalse(bad_of(M.run_move_guards(t, e, o)), (n, mode))

    def test_rules_hold(self):
        t = move_tables()
        seen_change = False
        for n in range(40):
            e, _l = M.plan_movement(t, f"s{n}", {"class_move": "wide"})
            new = {x["label"]: int(x["new"]) for x in e}
            seen_change |= bool(new)
            mv = lambda j: new.get(j, int(t.f.jobs[j]["mov"]))  # noqa: E731
            for kept in ("JID_ノスフェラトゥ男",):                     # enemy-only: never
                self.assertNotIn(kept, new)
            self.assertEqual(mv("JID_ソシアルナイト男"), mv("JID_ソシアルナイト女"))
            self.assertGreaterEqual(mv("JID_パラディン男"), mv("JID_ソシアルナイト男"))
            self.assertGreaterEqual(mv("JID_バーサーカー男"), max(mv("JID_アクスファイター男"), mv("JID_マーシナリー男")))
            self.assertLessEqual(mv("JID_アーマーナイト男"), 5)
            self.assertGreaterEqual(mv("JID_ドラゴンナイト男"), 5)
            for j, v in new.items():
                self.assertLessEqual(abs(v - int(t.f.jobs[j]["mov"])), 2 if not t.f.promoted(t.f.jobs[j]) else 8)
        self.assertTrue(seen_change)

    def test_no_stuck_rule(self):
        """A 5-Move fighter in a corridor where 4 Move reaches far fewer tiles: the loss is refused."""
        t = move_tables()
        units = M._units_by_family(t)
        fam = units[M.family("JID_アクスファイター男")]
        self.assertTrue(fam)
        stuck = M.stuck_units(t, fam, {"JID_アクスファイター男": 2}, {})
        self.assertTrue(stuck)
        e = [{"table": "Job", "index": 1, "label": "JID_アクスファイター男", "column": "mov", "old": "5", "new": "2"}]
        g = M.run_move_guards(t, e, {"class_move": "wide"})
        self.assertFalse(g["no_stuck_enemies"]["ok"])
        self.assertFalse(g["move_within_bounds"]["ok"])
        for n in range(30):
            e, _ = M.plan_movement(t, f"s{n}", {"class_move": "wide"})
            self.assertFalse(M.stuck_units(t, fam, {x["label"]: int(x["new"]) for x in e}, {}))

    def test_guard_catches_bad_edits(self):
        t = move_tables()
        o = {"class_move": "small"}
        e = [{"table": "Job", "index": 11, "label": "JID_ノスフェラトゥ男", "column": "mov", "old": "5", "new": "6"}]
        self.assertFalse(M.run_move_guards(t, e, o)["only_mov_of_normal_classes"]["ok"])
        e = [{"table": "Job", "index": 4, "label": "JID_ソシアルナイト男", "column": "mov", "old": "7", "new": "8"}]
        g = M.run_move_guards(t, e, o)
        self.assertFalse(g["male_and_female_rows_move_together"]["ok"])
        e = [{"table": "Job", "index": 18, "label": "JID_パラディン男", "column": "mov", "old": "8", "new": "6"},
             {"table": "Job", "index": 19, "label": "JID_パラディン女", "column": "mov", "old": "8", "new": "6"}]
        self.assertFalse(M.run_move_guards(t, e, {"class_move": "wide"})["promoted_never_slower_than_its_base"]["ok"])
        self.assertFalse(M.run_move_guards(t, e, None)["movement_off_no_edits"]["ok"])

    def test_job_csv_merge_keeps_promotion_cells(self):
        t = move_tables()
        e = [{"table": "Job", "index": 1, "label": "JID_アクスファイター男", "column": "mov", "old": "5", "new": "6"}]
        promo = R._csv([["index", "label", "promotion.1", "promotion.2"], ["4", "JID_ソシアルナイト男", "JID_X", N]])
        out = M.job_csv_with_edits(t.f, {"tables/Job.csv": promo}, e)
        rows = M._read_csv(out["tables/Job.csv"])
        self.assertEqual(rows[0], ["index", "label", "promotion.1", "promotion.2", "mov"])
        self.assertEqual(rows[1][1], "JID_アクスファイター男")
        self.assertEqual(rows[1][4], "6")
        self.assertEqual(rows[2], ["4", "JID_ソシアルナイト男", "JID_X", N, "7"])
        fresh = M.job_csv_with_edits(t.f, {}, e)
        self.assertEqual(M._read_csv(fresh["tables/Job.csv"]), [["index", "label", "mov"], ["1", "JID_アクスファイター男", "6"]])


def pair_tables(explicit: bool):
    """move_tables plus the three Fates pairs whose labels differ by more than the gender ending."""
    import copy
    t = move_tables()
    extra = [TE.job(30, "JID_修験者男", kinds=("staff",), origin=1, mov=5),
             TE.job(31, "JID_巫女女", kinds=("staff",), origin=1, female=True, mov=5),
             TE.job(32, "JID_山伏男", kinds=("staff",), origin=1, promoted=True, mov=6),
             TE.job(33, "JID_戦巫女女", kinds=("staff",), origin=1, promoted=True, female=True, mov=6),
             TE.job(34, "JID_バトラー男", kinds=("dagger", "staff"), promoted=True, mov=6),
             TE.job(35, "JID_メイド女", kinds=("dagger", "staff"), promoted=True, female=True, mov=6)]
    for a, b in ((0, 1), (2, 3), (4, 5)):
        extra[a]["gender_pair"], extra[b]["gender_pair"] = extra[b]["label"], extra[a]["label"]
    extra[0]["promotion.1"], extra[1]["promotion.1"] = "JID_山伏男", "JID_戦巫女女"
    for j in extra:
        t.f.jobs[j["label"]] = j
    t.f.job_list = sorted(t.f.jobs.values(), key=lambda j: int(j["index"]))
    t.rules = copy.deepcopy(t.rules)
    if explicit:
        t.rules["scope"] = {"job_pairs": {"JID_修験者男": "JID_巫女女", "JID_山伏男": "JID_戦巫女女",
                                          "JID_バトラー男": "JID_メイド女"}}
    else:
        t.rules.pop("scope", None)
    return t


class Pairs(unittest.TestCase):
    """Round W1 (WIRE_56 2c): Monk / Shrine Maiden, Great Master / Priestess and Butler / Maid are one class each,
    from the tables object (rules' scope.job_pairs, else the Job rows' own gender_pair cells)."""

    def test_three_pairs_are_one_family(self):
        for explicit in (True, False):
            t = pair_tables(explicit)
            for m, w in (("JID_修験者男", "JID_巫女女"), ("JID_山伏男", "JID_戦巫女女"), ("JID_バトラー男", "JID_メイド女")):
                self.assertEqual(M.family(m, t), M.family(w, t), (explicit, m))
                self.assertNotEqual(M.family(m), M.family(w))           # the bare label rule alone does not see it
            self.assertEqual(M.family("JID_パラディン女", t), "JID_パラディン")   # ordinary pairs as before

    def test_rules_file_lists_the_three_pairs(self):
        rules = R.load_rules()
        self.assertEqual(rules["scope"]["job_pairs"], {"JID_修験者男": "JID_巫女女", "JID_山伏男": "JID_戦巫女女",
                                                       "JID_バトラー男": "JID_メイド女"})

    def test_pairs_move_together_in_plan_and_guard(self):
        t = pair_tables(True)
        for n in range(30):
            e, _l = M.plan_movement(t, f"p{n}", {"class_move": "wide"})
            mv = {x["label"]: x["new"] for x in e}
            for m, w in (("JID_修験者男", "JID_巫女女"), ("JID_山伏男", "JID_戦巫女女"), ("JID_バトラー男", "JID_メイド女")):
                self.assertEqual(mv.get(m, t.f.jobs[m]["mov"]), mv.get(w, t.f.jobs[w]["mov"]), (n, m))
            self.assertFalse(bad_of(M.run_move_guards(t, e, {"class_move": "wide"})), n)
        e = [{"table": "Job", "index": 30, "label": "JID_修験者男", "column": "mov", "old": "5", "new": "6"}]
        self.assertFalse(M.run_move_guards(t, e, {"class_move": "small"})["male_and_female_rows_move_together"]["ok"])

    def test_promoted_move_upper_bound(self):
        t = pair_tables(True)
        e = [{"table": "Job", "index": 18, "label": "JID_パラディン男", "column": "mov", "old": "8", "new": "8"},
             {"table": "Job", "index": 20, "label": "JID_バーサーカー男", "column": "mov", "old": "6", "new": "9"}]
        g = M.run_move_guards(t, e, {"class_move": "wide"})
        self.assertFalse(g["move_within_bounds"]["ok"])
        self.assertIn("above", " ".join(g["move_within_bounds"]["detail"]))

    def test_plan_classes_argument_equals_the_old_bridge(self):
        """randolib.make_plan(classes=...) gives the person exactly that class and follows it (job_low, weapon exp,
        weapons); misc.make_plan_even now uses it (the _EvenFacts bridge is gone)."""
        self.assertFalse(hasattr(M, "_EvenFacts"))
        f = crowd_facts()
        base = R.make_plan(f, "cl1")
        e0 = [e for e in base["persons"] if not e["kept"]][0]
        pid = e0["pid"]
        legal = f.legal_classes(f.by_pid[pid], base["switches"])
        want = [j for j in legal if j != e0["job"]][0]
        plan = R.make_plan(f, "cl1", None, classes={pid: want})
        self.assertEqual({e["pid"]: e["job"] for e in plan["persons"]}[pid], want)
        self.assertEqual(R.make_plan(f, "cl1", None, classes={}), base)


def crowd_facts():
    """Nine Nohr men who all start as Cavaliers in the shared opening chapters, plus a healer and a thief."""
    base = TR.fake_facts()
    persons = list(base.persons)
    dispos = list(base.dispos)
    for i in range(9):
        pid = f"PID_M{i}"
        persons.append(TR.person(20 + i, pid, "JID_ソシアルナイト男", "JID_パラディン男", wexp={"sword": 21, "lance": 1}))
        dispos.append(TR.disp("A004", i, pid, 0, "IID_鉄の剣"))
    jobs = list(base.job_list)
    items = list(base.item_list)
    subs = [{"index": str(k), "kind": str(v), "origin": str(base.sub_origin[k])} for k, v in base.sub_kind.items()]
    return R.Facts(persons, jobs, items, subs, dispos, TR.RULES, {})


class AssignEvenly(unittest.TestCase):
    def test_guards_pass_many_seeds(self):
        for f in (TR.fake_facts(), TR.fake_facts(royal_staff_only=True), crowd_facts()):
            for n in range(30):
                for sw in (None, {"trees": "any"}):
                    plan, _l = M.make_plan_even(f, f"s{n}", sw, {"assign_evenly": True})
                    self.assertFalse(bad_of(plan["guards"]), (n, sw))

    def test_spread_is_even_when_everyone_has_the_same_choices(self):
        f = crowd_facts()
        for n in range(20):
            before = R.make_plan(f, f"s{n}")
            classes, _l = M.assign_evenly(f, before, f"s{n}", {"assign_evenly": True})
            jobs = {e["pid"]: e["job"] for e in before["persons"]}
            jobs.update(classes)
            crowd = [M.family(jobs[f"PID_M{i}"]) for i in range(9)]
            counts = {c: crowd.count(c) for c in set(crowd)}
            routes = before["routes"]
            ca = M.route_counts(f, jobs, routes)
            cb = M.route_counts(f, {e["pid"]: e["job"] for e in before["persons"]}, routes)
            for k in routes:
                self.assertLessEqual(max(ca[k].values()), max(cb[k].values()))
            legal = {M.family(j) for j in f.legal_classes(f.by_pid["PID_M0"], before["switches"])}
            self.assertLessEqual(max(counts.values()) - min(counts.get(c, 0) for c in legal), 1, (n, counts))

    def test_plan_follows_the_even_class(self):
        f = crowd_facts()
        plan, lines = M.make_plan_even(f, "s3", None, {"assign_evenly": True})
        s1 = R.make_plan(f, "s3")
        self.assertTrue(lines[0].startswith("Assign evenly"))
        moved = [e for e, b in zip(plan["persons"], s1["persons"]) if e["job"] != b["job"]]
        self.assertTrue(moved)
        for e in moved:                                  # job_low, weapon exp and stats follow the new class
            nj = f.jobs[e["job"]]
            self.assertTrue(all(v <= m for v, m in zip(e["wexp"], f.wexp_max(nj))))
        self.assertTrue(all(v["ok"] for v in plan["guards"].values()))
        self.assertIn("misc: route_roles_kept", plan["guards"])

    def test_story_people_stay_and_roles_stay(self):
        f = TR.fake_facts(royal_staff_only=True)
        for n in range(30):
            before = R.make_plan(f, f"s{n}")
            plan, _l = M.make_plan_even(f, f"s{n}", None, {"assign_evenly": True})
            g = M.run_even_guards(f, before, plan)
            self.assertFalse(bad_of(g), n)

    def test_classes_off_means_nothing_to_spread(self):
        f = TR.fake_facts()
        plan = R.make_plan(f, "s1", {"classes": False})
        self.assertEqual(M.assign_evenly(f, plan, "s1", {"assign_evenly": True}), ({}, []))


@unittest.skipUnless(os.path.isdir(os.path.join(ROOT, "extracted")), "the user's own RomFS is not extracted")
class RealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import gamedata as GD
        if GD.available():
            raise unittest.SkipTest(GD.available())
        import enemies as E
        cls.t = E.load_tables(names=False)
        cls.f = GD.load_facts(names=False)

    def test_real_seeds_pass_every_guard(self):
        for seed in ("r56a", "r56b", "r56c"):
            o = {"enemy_drops": 25, "class_move": "wide", "assign_evenly": True}
            de, _ = M.plan_drops(self.t, seed, o)
            me, _ = M.plan_movement(self.t, seed, o)
            self.assertTrue(de and me)
            self.assertFalse(bad_of(M.run_drop_guards(self.t, de, o)), seed)
            self.assertFalse(bad_of(M.run_move_guards(self.t, me, o)), seed)
            plan, _ = M.make_plan_even(self.f, seed, None, o)
            self.assertFalse(bad_of(plan["guards"]), seed)

    def test_real_off_is_slice1(self):
        p, _ = M.make_plan_even(self.f, "r56a", None, None)
        self.assertEqual(json.dumps(p, sort_keys=True, ensure_ascii=False),
                         json.dumps(R.make_plan(self.f, "r56a"), sort_keys=True, ensure_ascii=False))
        self.assertEqual(M.plan_drops(self.t, "r56a", None), ([], []))
        self.assertEqual(M.plan_movement(self.t, "r56a", None), ([], []))


if __name__ == "__main__":
    unittest.main()
