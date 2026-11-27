"""Self-tests for the randomizer, slice 1 (tools/randomizer; docs/RANDOMIZER.md).

    python -m unittest tests.test_randomizer          (from the repo root)

Most tests use small made-up tables (no game data). The last class runs on the user's own extracted RomFS
when it is there (skipped otherwise): many seeds through every guard, and the mods tool accepts the output.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
import randolib as R  # noqa: E402

S, K = R.STATS, R.KINDS
RULES = R.load_rules()


def job(ix, label, *, female=False, promoted=False, origin=2, kinds=(), cat="", flags="", promo=("JID_無し男", "JID_無し男"),
        base=2, mx=30, skills=()):
    f = [x for x in (flags, "SPID_女性" if female else "", "SPID_上級職" if promoted else "") if x]
    j = {"index": str(ix), "label": label, "flags": "|".join(f), "category": cat, "origin": str(origin),
         "mjid_name": "MJID_" + label, "promotion.1": promo[0], "promotion.2": promo[1]}
    for s in S:
        j[f"base.{s}"] = str(base)
        j[f"max.{s}"] = str(mx + (20 if s == "hp" else 0))
    for k in K:
        j[f"max_weapon_exp.{k}"] = str((161 if promoted else 96) if k in kinds else 0)
    for i in range(1, 5):
        j[f"skill.{i}"] = skills[i - 1] if i <= len(skills) else "SEID_無し"
    return j


def person(ix, label, jid, low, *, female=False, flags="", wexp=None, child=False, belong="BID_マイユニット軍",
           skills=()):
    f = [x for x in (flags, "SPID_女性" if female else "") if x]
    p = {"index": str(ix), "label": label, "flags": "|".join(f), "belong": belong, "job": jid, "job_low": low,
         "child_id": "3" if child else "65535", "mpid_name": "MPID_" + label, "personal_skill.normal": "SEID_無し"}
    for n, s in enumerate(S):
        p[f"base.{s}"] = str(2 + n % 3)
        p[f"growth.{s}"] = str(30 + 5 * (n % 4))
        p[f"limit_mod.{s}"] = "0"
    for k in K:
        p[f"weapon_exp.{k}"] = str((wexp or {}).get(k, 0))
    for i in range(1, 6):
        p[f"skill.{i}"] = skills[i - 1] if i <= len(skills) else "SEID_無し"
    return p


def item(ix, label, sub, rank, price=1000, flags=""):
    return {"index": str(ix), "label": label, "flags": flags, "weapon_kind": str(sub), "weapon_rank": str(rank),
            "buy_price": str(price), "legal_player_weapon": "1", "miid_name": "MIID_" + label}


def disp(f, ix, pid, team, *items):
    d = {"file": f"GameData/Dispos/{f}.bin.lz", "index": str(ix), "label": "", "pid": pid, "team": str(team)}
    for s in range(1, 6):
        d[f"item_{s}"] = items[s - 1] if s <= len(items) else ""
    return d


def fake_facts(royal_staff_only=False):
    N = "JID_無し男"
    jobs = [job(0, N),
            job(1, "JID_ダークプリンス男", kinds=("sword", "stone"), cat="JCID_竜|JCID_マムクート"),
            job(2, "JID_歌姫女", female=True, kinds=("lance",), flags="SPID_再行動コマンド"),
            job(3, "JID_ソシアルナイト男", kinds=("sword", "lance"), promo=("JID_パラディン男", N)),
            job(4, "JID_ソシアルナイト女", female=True, kinds=("sword", "lance"), promo=("JID_パラディン女", N)),
            job(5, "JID_パラディン男", promoted=True, kinds=("sword", "lance")),
            job(6, "JID_パラディン女", female=True, promoted=True, kinds=("sword", "lance")),
            job(7, "JID_ロッドナイト男", kinds=("staff",), promo=("JID_ストラテジスト男", N)),
            job(8, "JID_ロッドナイト女", female=True, kinds=("staff",), promo=("JID_ストラテジスト女", N)),
            job(9, "JID_ストラテジスト男", promoted=True, kinds=("staff", "tome")),
            job(10, "JID_ストラテジスト女", female=True, promoted=True, kinds=("staff", "tome")),
            job(11, "JID_アクスファイター男", kinds=("axe",), promo=("JID_パラディン男", N)),
            job(12, "JID_アクスファイター女", female=True, kinds=("axe",), promo=("JID_パラディン女", N)),
            job(13, "JID_シーフ男", kinds=("bow",), skills=("SEID_鍵開け",), promo=("JID_パラディン男", N)),
            job(14, "JID_侍男", origin=1, kinds=("sword",), promo=("JID_剣聖男", N)),
            job(15, "JID_剣聖男", origin=1, promoted=True, kinds=("sword",)),
            job(16, "JID_巫女女", origin=1, female=True, kinds=("staff",), promo=("JID_戦巫女女", N)),
            job(17, "JID_ガルー男", kinds=("stone",), cat="JCID_獣|JCID_ラグズ"),
            job(18, "JID_ノスフェラトゥ男", kinds=("stone",), flags="SPID_敵専用"),
            job(19, "JID_魔戦士男", kinds=("sword", "axe")),
            job(20, "JID_ダークマージ男", kinds=("tome",), cat="JCID_ダークマージ", promo=("JID_ストラテジスト男", N))]
    persons = [person(0, "PID_無し", N, N),
               person(1, "PID_プレイヤー男", "JID_ダークプリンス男", N, flags="SPID_主人公|SPID_マムクート|SPID_竜脈",
                      wexp={"sword": 1, "stone": 1}),
               person(2, "PID_アクア", "JID_歌姫女", N, female=True, flags="SPID_竜脈", wexp={"lance": 1}),
               person(3, "PID_マークス", "JID_パラディン男", "JID_ソシアルナイト男", flags="SPID_マークス|SPID_竜脈",
                      wexp={"sword": 161, "lance": 96}),
               person(4, "PID_A", "JID_ソシアルナイト男", "JID_パラディン男", wexp={"sword": 21, "lance": 1}),
               person(5, "PID_B", "JID_ロッドナイト女", "JID_ストラテジスト女", female=True, wexp={"staff": 21}),
               person(6, "PID_C", "JID_アクスファイター男", "JID_パラディン男", wexp={"axe": 51}),
               person(7, "PID_D", "JID_シーフ男", "JID_パラディン男", wexp={"bow": 21}, skills=("SEID_鍵開け",)),
               person(8, "PID_E", "JID_侍男", "JID_剣聖男", wexp={"sword": 21}),
               person(9, "PID_F", "JID_ガルー男", N, flags="SPID_ラグズ", wexp={"stone": 1}),
               person(10, "PID_G", "JID_ソシアルナイト女", "JID_パラディン女", female=True, wexp={"lance": 21}),
               person(11, "PID_KID", "JID_ソシアルナイト男", "JID_パラディン男", child=True, wexp={"sword": 1}),
               person(12, "PID_捕獲_X", "JID_アクスファイター男", N, flags="SPID_捕獲", belong="BID_無し"),
               person(13, "PID_H", "JID_パラディン男", "JID_ソシアルナイト男", wexp={"sword": 96, "lance": 51})]
    subs = [{"index": str(i), "kind": str(k), "origin": str(o)} for i, (k, o) in enumerate(
        [(0, 2), (0, 1), (1, 2), (1, 1), (2, 2), (2, 1), (3, 2), (3, 1), (4, 2), (4, 1), (5, 2), (5, 1), (6, 2), (6, 1),
         (7, 0), (7, 0), (7, 0), (7, 0), (7, 2), (7, 1), (8, 0)])]
    items = [item(0, "IID_無し", 20, 0, 0), item(1, "IID_青銅の剣", 0, 1, 500), item(2, "IID_鉄の剣", 0, 21),
             item(3, "IID_鋼の剣", 0, 51, 2000), item(4, "IID_鉄の槍", 2, 21), item(5, "IID_青銅の槍", 2, 1, 500),
             item(6, "IID_鋼の槍", 2, 51, 2000), item(7, "IID_鉄の斧", 4, 21), item(8, "IID_鋼の斧", 4, 51, 2000),
             item(9, "IID_青銅の斧", 4, 1, 500), item(10, "IID_ライブ", 12, 1, 500), item(11, "IID_リライブ", 12, 21),
             item(12, "IID_鉄の弓", 8, 21), item(13, "IID_ファイアー", 10, 1, 500), item(14, "IID_サンダー", 10, 21),
             item(15, "IID_鉄の刀", 1, 21), item(16, "IID_獣石", 15, 1, 2000, "ISID_貴重品"),
             item(17, "IID_傷薬", 20, 0, 300, "ISID_使用可能"), item(18, "IID_ジークフリート", 0, 1, 0, "ISID_マークス専用"),
             item(19, "IID_春祭", 13, 1, 500), item(20, "IID_鉄の和弓", 9, 21), item(21, "IID_銀の剣", 0, 96, 4000),
             item(22, "IID_リザイア", 10, 21, 4000, "ISID_ダークマージ系専用")]
    dispos = [disp("A001", 0, "PID_プレイヤー男", 0, "IID_青銅の剣"),
              disp("A002", 0, "PID_A", 0, "IID_鉄の剣", "IID_青銅の槍", "IID_傷薬"),
              disp("A002", 1, "PID_B", 0, "IID_ライブ", "IID_リライブ"),
              disp("A002", 2, "PID_C", 0, "IID_鋼の斧"),
              disp("A003", 0, "PID_D", 0, "IID_鉄の弓"),
              disp("A003", 1, "PID_アクア", 0, "IID_青銅の槍"),
              disp("A/A007", 0, "PID_E", 0, "IID_鉄の刀"),
              disp("A/A007", 1, "PID_マークス", 2, "IID_ジークフリート"),
              disp("B/B007", 0, "PID_F", 0, "IID_獣石"),
              disp("B/B007", 1, "PID_G", 0, "IID_鉄の槍"),
              disp("B/B008", 0, "PID_H", 0, "IID_銀の剣", "IID_鋼の槍"),
              disp("B/B008", 1, "PID_マークス", 0, "IID_ジークフリート"),
              disp("C/C007", 0, "PID_D", 0, "IID_鉄の弓"),
              disp("C/C007", 1, "PID_B", 0, "IID_ライブ"),
              disp("X001", 0, "PID_KID", 0, "IID_青銅の剣")]
    if royal_staff_only:  # route B's only staff user is person B: put B in route B only, as the single healer
        dispos = [d for d in dispos if not (d["pid"] == "PID_B" and d["file"].endswith(("A002.bin.lz", "C007.bin.lz")))]
        dispos.append(disp("B/B009", 0, "PID_B", 0, "IID_ライブ"))
    return R.Facts(persons, jobs, items, subs, dispos, RULES, {})


SEEDS = [f"s{i}" for i in range(60)]


class SyntheticTests(unittest.TestCase):
    def setUp(self):
        self.f = fake_facts()

    def test_same_seed_byte_identical(self):
        a = R.render(self.f, R.make_plan(self.f, "abc"))
        b = R.render(fake_facts(), R.make_plan(fake_facts(), "abc"))
        self.assertEqual(a, b)

    def test_different_seed_differs(self):
        a = R.render(self.f, R.make_plan(self.f, "abc"))
        b = R.render(self.f, R.make_plan(self.f, "abd"))
        self.assertNotEqual(a["tables/Person.csv"], b["tables/Person.csv"])

    def test_switches_change_output_and_off_is_original(self):
        off = R.make_plan(self.f, "abc", {"classes": False, "growths": False, "join_stats": False})
        files = R.render(self.f, off)
        self.assertEqual(files["tables/Person.csv"].decode("utf-8-sig").strip().count("\n"), 0)  # header only
        self.assertNotIn("tables/DisposUnit.csv", files)

    def test_bad_seed_and_children_refused(self):
        for bad in ("", "a b", "x" * 41, "-a", "a/b"):
            with self.assertRaises(R.RandoError):
                R.make_plan(self.f, bad)
        with self.assertRaises(R.RandoError):
            R.make_plan(self.f, "abc", {"children": True})

    def test_no_illegal_class(self):
        for seed in SEEDS:
            for sw in ({}, {"trees": "any"}, {"keep_royals": False}):
                plan = R.make_plan(self.f, seed, sw)
                for e in plan["persons"]:
                    p, j = self.f.by_pid[e["pid"]], self.f.jobs[e["job"]]
                    self.assertEqual(self.f.female(j), self.f.female(p), (seed, e))
                    self.assertEqual(self.f.promoted(j), self.f.promoted(self.f.jobs[e["old_job"]]), (seed, e))
                    if e["job"] != e["old_job"]:
                        self.assertIsNone(self.f.excluded_job(e["job"]), (seed, e))
                        self.assertIn(e["job"], self.f.legal_classes(p, plan["switches"]))
                        beast_c = "JCID_ラグズ" in j["category"]
                        self.assertEqual(beast_c, "SPID_ラグズ" in p["flags"])
                    if plan["switches"]["trees"] == "own":
                        self.assertEqual(j["origin"], self.f.jobs[e["old_job"]]["origin"])
                self.assertTrue(plan["guards"]["legal_class"]["ok"])

    def test_story_people_keep_class(self):
        for seed in SEEDS:
            plan = R.make_plan(self.f, seed)
            by = {e["pid"]: e for e in plan["persons"]}
            for pid in ("PID_プレイヤー男", "PID_アクア", "PID_マークス"):
                self.assertEqual(by[pid]["job"], by[pid]["old_job"], (seed, pid))
        moved = {R.make_plan(self.f, s, {"keep_royals": False, "trees": "any"})["persons"][2]["job"] for s in SEEDS}
        self.assertGreater(len(moved), 1)   # with keep-royals off the royal does get other classes

    def test_children_and_outsiders_never_edited(self):
        for seed in SEEDS[:20]:
            plan = R.make_plan(self.f, seed)
            pids = {e["pid"] for e in plan["persons"]}
            self.assertNotIn("PID_KID", pids)
            self.assertNotIn("PID_捕獲_X", pids)
            self.assertNotIn("PID_無し", pids)
            for k in plan["dispos"]:
                self.assertNotIn("X001", k)

    def test_no_new_people_and_only_allowed_cells(self):
        labels = {(p["index"], p["label"]) for p in self.f.persons}
        for seed in SEEDS[:20]:
            files = R.render(self.f, R.make_plan(self.f, seed))
            tables = sorted(k for k in files if k.startswith("tables/"))
            self.assertTrue(set(tables) <= {"tables/Person.csv", "tables/DisposUnit.csv"})
            rows = files["tables/Person.csv"].decode("utf-8-sig").strip().split("\n")
            self.assertEqual(rows[0].split(","), ["index", "label"] + R.PERSON_COLS)
            for r in rows[1:]:
                ix, lab = r.split(",")[:2]
                self.assertIn((ix, lab), labels)
            if "tables/DisposUnit.csv" in files:
                head = files["tables/DisposUnit.csv"].decode("utf-8-sig").split("\n")[0].split(",")
                self.assertEqual(head, ["file", "index", "label"] + [f"item_{s}" for s in range(1, 6)])

    def test_weapons_still_usable_and_swaps_said(self):
        swaps = 0
        for seed in SEEDS:
            plan = R.make_plan(self.f, seed, {"trees": "any"})
            self.assertTrue(plan["guards"]["weapons_usable"]["ok"], plan["guards"]["weapons_usable"])
            for e in plan["persons"]:
                for sw in e.get("swaps", []):
                    swaps += 1
                    if sw["same_rank"]:
                        self.assertEqual(self.f.item_rank(sw["new"]), self.f.item_rank(sw["old"]))
                    self.assertIn(f"{self.f.iname(sw['old'])} -> {self.f.iname(sw['new'])}",
                                  R.spoiler(self.f, plan))
            # every placement item of a changed person is usable by the new class
            for e in plan["persons"]:
                p = self.f.by_pid[e["pid"]]
                for d in self.f.placements(e["pid"]):
                    for s in range(1, 6):
                        iid = plan["dispos"].get(f"{d['file']}#{d['index']}", {}).get(f"item_{s}", d[f"item_{s}"])
                        if self.f.item_kind(iid) is not None and e["job"] != e["old_job"]:
                            self.assertGreater(self.f.wexp_max(self.f.jobs[e["job"]])[self.f.item_kind(iid)], 0)
        self.assertGreater(swaps, 0)

    def test_class_only_item_is_swapped(self):
        p = self.f.by_pid["PID_C"]
        self.assertIsNotNone(self.f.class_can_hold("JID_ロッドナイト男", p, "IID_リザイア", [0] * 6 + [96, 0]))
        self.assertIsNotNone(self.f.class_can_hold("JID_ストラテジスト男", p, "IID_リザイア", [0] * 5 + [96, 96, 0]))
        self.assertIsNone(self.f.class_can_hold("JID_ダークマージ男", p, "IID_リザイア", [0] * 5 + [96, 0, 0]))

    def test_route_roles_kept(self):
        """The route rules (a healer, a door opener and a dragon-vein user somewhere on each route) stay true and stay
        guarded. Round 75b's seed guarantees (tests/test_rando_guarantees.py) are stricter: they also say BY WHEN each
        role joins; these made-up tables carry none of guarantees.json's people, so only the route pass acts here."""
        f = fake_facts(royal_staff_only=True)
        forced = 0
        for seed in SEEDS:
            plan = R.make_plan(f, seed)
            for g in ("staff_user_per_route", "door_opener_per_route", "vein_user_per_route"):
                self.assertTrue(plan["guards"][g]["ok"], (seed, g, plan["guards"][g]))
            forced += len(plan["forced"])
        self.assertGreater(forced, 0)   # the guard had to act at least once

    def test_stats_within_caps_and_totals(self):
        for seed in SEEDS:
            plan = R.make_plan(self.f, seed)
            self.assertTrue(plan["guards"]["stats_within_caps"]["ok"], plan["guards"]["stats_within_caps"])
            for e in plan["persons"]:
                self.assertEqual(sum(e["growth"]), sum(e["old_growth"]))
                self.assertTrue(all(g % 5 == 0 for g in e["growth"][1:]))
                self.assertLessEqual(sum(e["base"]), max(sum(e["old_base"]), 0))

    def test_rng_untouched(self):
        """Only Person class / growth / base / weapon-exp cells and placement item cells are written: no table
        or column of the game's random generator (none is in the output at all)."""
        files = R.render(self.f, R.make_plan(self.f, "abc"))
        text = b"".join(v for k, v in files.items() if k.startswith("tables/")).decode("utf-8-sig", "replace")
        for word in ("rand", "seed", "Random"):
            self.assertNotIn(word, text)

    def test_route_variant_joins_get_the_new_class(self):
        """Round W2 (owner OK, F-046): a placement naming a route-variant (HANDOVER) row gets the person's new class
        in its jid and weapons that class can use with the route row's own weapon exp; nothing else moves, and with
        Classes off nothing is written."""
        base = fake_facts()
        hv = dict(base.by_pid["PID_A"], label="PID_C_A", replace_index="4", file="GameData/Person/C_HANDOVER.bin.lz",
                  index="1")
        dispos = list(base.dispos) + [disp("C/C008", 3, "PID_C_A", 0, "IID_鉄の槍", "IID_傷薬")]
        f = R.Facts(base.persons, list(base.jobs.values()), list(base.items.values()),
                    [{"index": str(k), "kind": str(v), "origin": str(base.sub_origin[k])} for k, v in base.sub_kind.items()],
                    dispos, RULES, {}, handover=[hv])
        self.assertEqual(f.variant_of, {"PID_C_A": "PID_A"})
        plain = R.Facts(base.persons, list(base.jobs.values()), list(base.items.values()),
                        [{"index": str(k), "kind": str(v), "origin": str(base.sub_origin[k])}
                         for k, v in base.sub_kind.items()], dispos, RULES, {})
        hit = 0
        for seed in SEEDS[:30]:
            plan = R.make_plan(f, seed)
            self.assertTrue(all(v["ok"] for v in plan["guards"].values()),
                            {k: v["detail"][:3] for k, v in plan["guards"].items() if not v["ok"]})
            e = next(x for x in plan["persons"] if x["pid"] == "PID_A")
            ed = plan["dispos"].get("GameData/Dispos/C/C008.bin.lz#3", {})
            if e["job"] != e["old_job"]:
                hit += 1
                self.assertEqual(ed.get("jid"), e["job"], seed)
                self.assertEqual(e["route_joins"][0]["jid"], e["job"])
                self.assertIn("route-variant join", R.spoiler(f, plan))
                self.assertIn("jid", R.render(f, plan)["tables/DisposUnit.csv"].decode("utf-8").splitlines()[0])
            else:
                self.assertNotIn("jid", ed)
            # the main rows and every other placement: exactly as without the route-variant row
            other = R.make_plan(plain, seed)
            self.assertEqual(R.render(f, plan)["tables/Person.csv"], R.render(plain, other)["tables/Person.csv"])
            self.assertEqual({k: v for k, v in plan["dispos"].items() if "C008" not in k}, other["dispos"])
        self.assertGreater(hit, 5)
        plan = R.make_plan(f, "s1", {"classes": False})
        self.assertFalse(plan["dispos"])

    def test_write_mod_refuses_foreign_folder(self):
        with tempfile.TemporaryDirectory() as t:
            d = os.path.join(t, "Rando-x")
            os.makedirs(d)
            with open(os.path.join(d, "mod.json"), "w", encoding="utf-8") as fh:
                fh.write('{"name": "Owner"}')
            with self.assertRaises(R.RandoError):
                R.write_mod({"mod.json": b"{}"}, d)


def _real():
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
        import gamedata as GD
        if GD.available():
            return None
        return GD
    except Exception:  # noqa: BLE001
        return None


GD = _real()


@unittest.skipIf(GD is None, "no extracted RomFS / table layouts here")
class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = GD.load_facts()

    def test_many_seeds_all_guards(self):
        for i in range(25):
            for sw in ({}, {"trees": "any"}, {"keep_royals": False, "trees": "any"}):
                plan = R.make_plan(self.f, f"real{i}", sw)
                bad = {k: v["detail"][:3] for k, v in plan["guards"].items() if not v["ok"]}
                self.assertFalse(bad, (i, sw, bad))

    def test_byte_identical_and_differs(self):
        a = R.render(self.f, R.make_plan(self.f, "same"))
        b = R.render(GD.load_facts(), R.make_plan(GD.load_facts(), "same"))
        self.assertEqual(a, b)
        c = R.render(self.f, R.make_plan(self.f, "other"))
        self.assertNotEqual(a["tables/Person.csv"], c["tables/Person.csv"])

    def test_mods_tool_accepts_the_folder(self):
        import mods as M
        with tempfile.TemporaryDirectory() as t:
            plan = R.make_plan(self.f, "modscheck")
            d = R.write_mod(R.render(self.f, plan), os.path.join(t, R.mod_name("modscheck")))
            changes, errors, warnings = M.diff_mod(M.Mod(d))
            self.assertEqual(errors, [])
            self.assertTrue(changes)
            tables = {k[0] for k in changes}
            self.assertTrue(tables <= {"Person", "DisposUnit"}, tables)


if __name__ == "__main__":
    unittest.main()
