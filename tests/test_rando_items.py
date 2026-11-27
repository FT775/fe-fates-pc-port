"""Self-tests for the randomizer's items track (tools/randomizer/items.py; docs/rando/ITEMS.md).

    python -m unittest tests.test_rando_items          (from the repo root)

Made-up tables first (no game data): the slice-1 fixture of tests/test_randomizer.py plus shop stock, healing
staves, a door key, a seal and a downloadable item. The last class runs on the user's own extracted RomFS when it
is there (skipped otherwise).
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
sys.path.insert(0, ROOT)
import randolib as R  # noqa: E402
import items as I  # noqa: E402
from tests import test_randomizer as T  # noqa: E402

SEEDS = [f"i{n}" for n in range(40)]


def _stock(it, shop, pat):
    for lv, v in zip(I.LEVELS, pat):
        it[f"{shop}.{lv}"] = str(v)


def fake_facts(**kw):
    f = T.fake_facts(**kw)
    for it in f.item_list:
        it.setdefault("item_subkind", "0")
        for sh in I.SHOPS:
            _stock(it, sh, (0, 0, 0))
    heal = "ISID_回復杖"
    for lab in ("IID_ライブ", "IID_リライブ", "IID_春祭"):
        f.items[lab]["flags"] = heal
        f.items[lab]["item_subkind"] = "1"
    f.items["IID_傷薬"]["item_subkind"] = "1"
    extra = [T.item(23, "IID_調合薬", 20, 0, 600, "ISID_使用可能"), T.item(24, "IID_扉の鍵", 20, 0, 0, "ISID_扉鍵|ISID_貴重品|ISID_章限定"),
             T.item(25, "IID_マスタープルフ", 20, 0, 2000, "ISID_使用可能"), T.item(26, "IID_魔戦士の巻物", 20, 0, 0, "ISID_使用可能"),
             T.item(27, "IID_キルソード", 0, 21, 3000), T.item(28, "IID_アーマーキラー", 0, 21, 2500),
             T.item(29, "IID_ハンマー", 4, 21, 2500), T.item(30, "IID_手槍", 2, 21, 1800),
             T.item(31, "IID_フリーズ", 12, 21, 1800)]
    subs = {"IID_調合薬": 1, "IID_扉の鍵": 0, "IID_マスタープルフ": 11, "IID_魔戦士の巻物": 11}
    for it in extra:
        it["item_subkind"] = str(subs.get(it["label"], 0))
        for sh in I.SHOPS:
            _stock(it, sh, (0, 0, 0))
    extra[3]["legal_player_weapon"] = "0"        # downloadable class scroll
    for it in extra:
        f.items[it["label"]] = it
        f.item_list.append(it)
    # shops: Nohr armory (dusk) and Nohr item shop (staff)
    for lab, pat in (("IID_鉄の剣", (255, 255, 255)), ("IID_キルソード", (0, 1, 2)), ("IID_アーマーキラー", (0, 1, 2)),
                     ("IID_鋼の剣", (1, 255, 255)), ("IID_鉄の槍", (255, 255, 255)), ("IID_手槍", (2, 5, 10)),
                     ("IID_鉄の斧", (255, 255, 255)), ("IID_ハンマー", (0, 1, 2))):
        _stock(f.items[lab], "dusk_stock", pat)
    for lab, pat in (("IID_鉄の刀", (255, 255, 255)),):
        _stock(f.items[lab], "dawn_stock", pat)
    for lab, pat in (("IID_傷薬", (255, 255, 255)), ("IID_調合薬", (3, 255, 255)), ("IID_ライブ", (255, 255, 255)),
                     ("IID_リライブ", (0, 255, 255)), ("IID_フリーズ", (0, 1, 2)), ("IID_マスタープルフ", (0, 2, 7))):
        _stock(f.items[lab], "staff_stock", pat)
    for lab, pat in (("IID_傷薬", (255, 255, 255)), ("IID_春祭", (255, 255, 255)), ("IID_マスタープルフ", (0, 2, 7))):
        _stock(f.items[lab], "rod_stock", pat)
    # a door key and a seal in someone's starting items; a healing item
    d = [x for x in f.dispos if x["pid"] == "PID_C"][0]
    d["item_2"], d["item_3"] = "IID_扉の鍵", "IID_マスタープルフ"
    return f


ACHIEVE = {"AchieveBonusBattle": [{"index": "0", "label": "", "requirement": "1", "item": "IID_調合薬"},
                                  {"index": "1", "label": "", "requirement": "5", "item": "IID_キルソード"},
                                  {"index": "2", "label": "", "requirement": "9", "item": "IID_魔戦士の巻物"}],
           "AchieveBonusVisit": [{"index": "0", "label": "", "requirement": "1", "item": "IID_リライブ"}]}


def run(f, seed, opts=None, slice1=True):
    o = dict(opts or {})
    full = dict(o, achieve=ACHIEVE, slice1_plan=R.make_plan(f, seed) if slice1 else None)
    edits, lines = I.plan_items(f, I.sub_rng(seed, "items", o), full)
    return edits, lines, I.check_items(f, edits, full), full


class FakeTableTests(unittest.TestCase):
    def setUp(self):
        self.f = fake_facts()

    def test_same_seed_same_output_and_seeds_differ(self):
        a = run(self.f, "same")
        b = run(fake_facts(), "same")
        self.assertEqual(a[0], b[0])
        self.assertEqual(a[1], b[1])
        fa = I.edits_to_files(self.f, a[0], R.render(self.f, a[3]["slice1_plan"]))
        fb = I.edits_to_files(self.f, b[0], R.render(self.f, b[3]["slice1_plan"]))
        self.assertEqual(fa, fb)
        outs = {repr(run(self.f, s)[0]) for s in SEEDS[:12]}
        self.assertGreater(len(outs), 1)

    def test_all_guards_many_seeds(self):
        for s in SEEDS:
            for o in ({}, {"shop_sides": "mixed"}, {"shops": False}, {"inventories": False, "rewards": False}):
                for kw in ({}, {"royal_staff_only": True}):
                    _e, _l, g, _o = run(fake_facts(**kw), s, o)
                    bad = {k: v["detail"][:3] for k, v in g.items() if not v["ok"]}
                    self.assertFalse(bad, (s, o, kw, bad))

    def test_no_unusable_starting_weapon(self):
        for s in SEEDS:
            edits, _l, _g, full = run(self.f, s)
            final = {e["pid"]: (e["job"], e["wexp"]) for e in full["slice1_plan"]["persons"]}
            for e in edits:
                if e["table"] != "DisposUnit":
                    continue
                d = [x for x in self.f.dispos if x["file"] == e["file"] and R.ival(x["index"]) == e["index"]][0]
                p = self.f.by_pid[d["pid"]]
                job, wexp = final[d["pid"]]
                for sl in range(1, 6):
                    i = e["cells"][f"item_{sl}"]
                    if self.f.item_kind(i) is not None:
                        self.assertIsNone(self.f.class_can_hold(job, p, i, wexp, True), (s, d["pid"], i))

    def test_healing_and_door_opening_kept_per_route(self):
        for s in SEEDS:
            edits, _l, g, _o = run(self.f, s)
            self.assertTrue(g["healing_and_doors_per_route"]["ok"], g["healing_and_doors_per_route"])
            for e in edits:
                if e["table"] == "DisposUnit" and e["index"] == 2 and e["file"].endswith("A002.bin.lz"):
                    self.assertEqual(e["cells"]["item_2"], "IID_扉の鍵")       # the key never moves
                    self.assertEqual(e["cells"]["item_3"], "IID_マスタープルフ")  # nor the seal
        # the only healer of route B keeps a healing staff whatever the seed
        f = fake_facts(royal_staff_only=True)
        iv = I.ItemView(f)
        kept = 0
        for s in SEEDS:
            edits, _l, _g, full = run(f, s)
            for e in edits:
                if e["table"] == "DisposUnit" and e["file"].endswith("B009.bin.lz"):
                    d = [x for x in f.dispos if x["file"] == e["file"]][0]
                    before = I.base_items(d, full["slice1_plan"]["dispos"])[0]    # after slice 1's swap
                    if iv.heal_staff(before):
                        kept += 1
                        self.assertTrue(iv.heal_staff(e["cells"]["item_1"]), (s, e))
        self.assertGreater(kept, 0)

    def test_shops_sane(self):
        iv = I.ItemView(self.f)
        for s in SEEDS:
            for o in ({}, {"shop_sides": "mixed"}):
                edits, _l, g, _o = run(self.f, s, o)
                self.assertTrue(g["shops_sane"]["ok"], g["shops_sane"])
                for e in edits:
                    if e["table"] != "Item":
                        continue
                    self.assertNotIn(e["label"], I.PINNED)
                    self.assertNotIn(e["label"], ("IID_マスタープルフ",))
                    self.assertGreater(iv.price(e["label"]), 0)
                    self.assertEqual(iv.lpw(e["label"]) in (1, 2), True)
        # own sides never sells a Hoshido-shop item in the Nohr armory
        for s in SEEDS:
            edits, _l, _g, _o = run(self.f, s)
            for e in edits:
                if e["table"] == "Item" and any(e["cells"].get(f"dusk_stock.{lv}", "0") != "0" for lv in I.LEVELS):
                    self.assertNotEqual(e["label"], "IID_鉄の刀")

    def test_no_dlc_or_story_items_placed(self):
        iv = I.ItemView(self.f)
        for s in SEEDS:
            edits, _l, _g, _o = run(self.f, s)
            for e in edits:
                vals = [v for k, v in e["cells"].items() if k.startswith("item")]
                for v in vals:
                    if e["table"] == "DisposUnit" and v in ("IID_扉の鍵", "IID_マスタープルフ", "IID_ジークフリート", ""):
                        continue
                    self.assertTrue(iv.placeable(v), (s, e))
                    self.assertNotEqual(v, "IID_魔戦士の巻物")

    def test_rewards_same_band(self):
        iv = I.ItemView(self.f)
        for s in SEEDS:
            edits, _l, g, _o = run(self.f, s)
            self.assertTrue(g["rewards_same_band"]["ok"], g["rewards_same_band"])
            for e in edits:
                if e["table"] in I.REWARD_TABLES:
                    self.assertNotEqual((e["table"], e["index"]), ("AchieveBonusBattle", 2))   # downloadable: kept
                    old = {R.ival(r["index"]): r["item"] for r in ACHIEVE[e["table"]]}[e["index"]]
                    self.assertEqual(iv.band(old), iv.band(e["cells"]["item"]))

    def test_track_independent_of_slice1_switches(self):
        """Shops and rewards come only from the seed and this track's own switches."""
        def shops(sw):
            f = fake_facts()
            full = {"achieve": ACHIEVE, "slice1_plan": R.make_plan(f, "ind", sw)}
            e, _l = I.plan_items(f, I.sub_rng("ind"), full)
            return [x for x in e if x["table"] != "DisposUnit"]
        self.assertEqual(shops({}), shops({"trees": "any", "growths": False}))
        self.assertNotEqual(I.sub_rng("x", "items").random(), I.sub_rng("x", "skills").random())

    def test_off_means_nothing(self):
        e, _l, _g, _o = run(self.f, "off", {"inventories": False, "shops": False, "rewards": False})
        self.assertEqual(e, [])

    def test_guard_catches_bad_edit(self):
        edits, _l, _g, full = run(self.f, "bad")
        d = [x for x in self.f.dispos if x["pid"] == "PID_C"][0]
        edits = [x for x in edits if not (x["table"] == "DisposUnit" and x["file"] == d["file"] and x["index"] == 2)]
        edits.append({"table": "DisposUnit", "file": d["file"], "index": 2, "label": "",
                      "cells": {"item_1": "IID_鋼の剣", "item_2": "", "item_3": "IID_マスタープルフ", "item_4": "", "item_5": ""}})
        g = I.check_items(self.f, edits, full)
        self.assertFalse(g["healing_and_doors_per_route"]["ok"])
        self.assertFalse(g["starting_items_usable_and_story_kept"]["ok"])


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
        cls.ach = I.load_achieve()

    def _run(self, seed, o=None, sw=None):
        o = dict(o or {})
        full = dict(o, achieve=self.ach, slice1_plan=R.make_plan(self.f, seed, sw or {}))
        e, l = I.plan_items(self.f, I.sub_rng(seed, "items", o), full)
        return e, l, I.check_items(self.f, e, full), full

    def test_many_seeds_all_guards(self):
        for n in range(12):
            for o, sw in (({}, {}), ({"shop_sides": "mixed"}, {"trees": "any"}), ({"rewards": False}, {"classes": False})):
                _e, _l, g, _f = self._run(f"real{n}", o, sw)
                bad = {k: v["detail"][:3] for k, v in g.items() if not v["ok"]}
                self.assertFalse(bad, (n, o, sw, bad))

    def test_route_variant_joins_get_starting_items(self):
        """round 60: Revelation's PID_C_ joins (and the other HANDOVER rows) were left out of starting items; they
        are in scope now, usable for the class they join in, and the main rows' picks did not move"""
        hv = getattr(self.f, "variant_row", {})
        if not hv:
            self.skipTest("no route-variant rows in these tables")
        for seed in ("hv1", "hv2", "hv3"):
            e, _l, g, full = self._run(seed, {"shops": False, "rewards": False})
            self.assertTrue(all(v["ok"] for v in g.values()), {k: v["detail"][:3] for k, v in g.items() if not v["ok"]})
            vkeys = {f"{d['file']}#{R.ival(d['index'])}" for d in self.f.dispos if d.get("pid") in hv}
            got = [x for x in e if x["table"] == "DisposUnit" and f"{x['file']}#{x['index']}" in vkeys]
            self.assertTrue(got, seed)
            # the main rows' edits equal a plan made without the variant rows known
            import copy
            f0 = copy.copy(self.f)
            f0.variant_of, f0.variant_row = {}, {}
            e0, _l0 = I.plan_items(f0, I.sub_rng(seed, "items", {"shops": False, "rewards": False}), full)
            main = [x for x in e if x["table"] == "DisposUnit" and f"{x['file']}#{x['index']}" not in vkeys]
            self.assertEqual(main, [x for x in e0 if x["table"] == "DisposUnit"])

    def test_same_seed_same_bytes(self):
        a = self._run("same")
        b = self._run("same")
        fa = I.edits_to_files(self.f, a[0], R.render(self.f, a[3]["slice1_plan"]))
        fb = I.edits_to_files(self.f, b[0], R.render(self.f, b[3]["slice1_plan"]))
        self.assertEqual(fa, fb)
        self.assertNotEqual(a[0], self._run("other")[0])

    def test_mods_tool_accepts_the_folder(self):
        import mods as M
        e, _l, _g, full = self._run("modscheck")
        files = I.edits_to_files(self.f, e, R.render(self.f, full["slice1_plan"]))
        with tempfile.TemporaryDirectory() as t:
            d = R.write_mod(files, os.path.join(t, R.mod_name("modscheck")))
            changes, errors, _w = M.diff_mod(M.Mod(d))
            self.assertEqual(errors, [])
            tables = {k[0] for k in changes}
            self.assertTrue(tables <= {"Person", "DisposUnit", "Item", "AchieveBonusBattle", "AchieveBonusVisit"}, tables)
            self.assertIn("Item", tables)


if __name__ == "__main__":
    unittest.main()
