"""Self-tests for the randomizer track "weapons" (tools/randomizer/weapons.py; docs/rando/WEAPONS.md).

    python -m unittest tests.test_rando_weapons          (from the repo root)

Made-up tables first (no game data): the enemies track's fixture (tests/test_rando_enemies.py) with weapon stats,
a Yato, a legendary, a personal weapon, an S-rank route weapon, a stone and a drop. The last class runs on the
user's own extracted RomFS when it is there (skipped otherwise): many seeds through every guard, and the mods tool
reads the made folder without an error.
"""
from __future__ import annotations

import os
import shutil
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
sys.path.insert(0, os.path.join(ROOT, "tools", "mods"))
sys.path.insert(0, ROOT)
import randolib as R  # noqa: E402
import weapons as W  # noqa: E402
import enemies as E  # noqa: E402
from tests import test_rando_enemies as TE  # noqa: E402

try:
    import gamedata as GD  # noqa: E402
    if GD.available():
        GD = None
except Exception:  # noqa: BLE001
    GD = None

SEEDS = [f"w{n}" for n in range(30)]
TMP = os.path.join(ROOT, "build", "test_rando_weapons")
ALL = {"stats": True, "traits": 60, "wild_traits": True, "enemy_upgrade": 100, "upgrade_rank": "next"}

# (label, might, hit, crit, avoid, uses, range) for the fixture's items; the rest get sane defaults
STATS = {"IID_青銅の剣": (4, 100, 0, 0, 0, (1, 1)), "IID_鉄の剣": (6, 90, 0, 0, 0, (1, 1)),
         "IID_鋼の剣": (9, 85, 0, -5, 0, (1, 1)), "IID_鉄の槍": (7, 80, 0, 0, 0, (1, 1)),
         "IID_鋼の槍": (10, 75, 0, -5, 0, (1, 1)), "IID_鉄の斧": (8, 70, 0, 0, 0, (1, 1)),
         "IID_鋼の斧": (12, 65, 0, -5, 0, (1, 1)), "IID_手斧": (7, 65, 0, 0, 0, (1, 2)),
         "IID_ライブ": (10, 0, 0, 0, 20, (1, 1)), "IID_リライブ": (20, 0, 0, 0, 15, (1, 1)),
         "IID_サンダー": (5, 80, 0, 0, 0, (1, 2)), "IID_鋼の刀": (9, 85, 0, -5, 0, (1, 1)),
         "IID_敵の剣": (6, 90, 0, 0, 0, (1, 1)), "IID_鉄の弓": (8, 80, 0, 0, 0, (2, 2)),
         "IID_銀の斧": (16, 70, 0, 0, 0, (1, 1)), "IID_ファイアー": (3, 90, 0, 0, 0, (1, 2)),
         "IID_爪": (10, 80, 0, 0, 0, (1, 1))}


def fill(it, might=5, hit=80, crit=0, avoid=0, uses=0, rng=(1, 1)):
    it.update({"might": str(might), "hit": str(hit), "crit": str(crit), "avoid": str(avoid), "uses": str(uses),
               "range_min": str(rng[0]), "range_max": str(rng[1])})
    it.setdefault("effective", "")
    for s in R.STATS:
        it.setdefault(f"stat_bonus.{s}", "0")
    return it


def fake(more_dispos=()):
    t = TE.fake(more_dispos)
    f = t.f
    for i, it in f.items.items():
        fill(it, *STATS.get(i, (0, 0, 0, 0, 0, (1, 1))))
    f.items["IID_青銅の剣"]["flags"] = "ISID_必殺奥義禁止"
    f.items["IID_ライブ"]["flags"] = "ISID_回復杖"
    extra = [  # index, label, subkind, rank, price, flags, stats
        (20, "IID_夜刀神", 0, 1, 0, "ISID_貴重品|ISID_神武器|ISID_プレイヤー専用", (8, 85, 0, 0, 0, (1, 1))),
        (21, "IID_雷神刀", 1, 1, 0, "ISID_貴重品|ISID_神武器|ISID_リョウマ専用", (11, 80, 5, 10, 0, (1, 2))),
        (22, "IID_ミステルトィン", 10, 1, 0, "ISID_オフェリア専用", (9, 70, 10, 0, 0, (1, 2))),
        (23, "IID_葉隠", 1, 251, 0, "ISID_戦闘後能力半減", (18, 95, 0, 20, 0, (1, 1))),
        (24, "IID_キルソード", 0, 51, 3000, "ISID_必殺倍率＋", (6, 85, 25, -10, 0, (1, 1))),
        (25, "IID_銀の剣", 0, 96, 4000, "ISID_戦闘後能力減少", (12, 90, 0, 0, 0, (1, 1))),
        (26, "IID_アーマーキラー", 0, 21, 2500, "ISID_非特効時威力－|ISID_非特効時命中－", (9, 95, 0, 0, 0, (1, 1))),
        (27, "IID_竜石", 14, 1, 2000, "ISID_魔法武器|ISID_貴重品", (14, 85, 0, -10, 0, (1, 1))),
        (28, "IID_銀の槍", 2, 96, 4000, "ISID_戦闘後能力減少", (14, 80, 0, 0, 0, (1, 1))),
        (29, "IID_大祭", 12, 161, 5000, "ISID_回復杖|ISID_無限回数", (2, 0, 0, 0, 2, (1, 10))),
        (30, "IID_鋼の弓", 8, 51, 2000, "", (11, 75, 0, -5, 0, (2, 2)))]
    for ix, lab, sub, rank, price, fl, st in extra:
        it = fill(TE.item(ix, lab, sub, rank, price, fl), *st)
        f.items[lab] = it
        f.item_list.append(it)
    f.items["IID_葉隠"]["legal_player_weapon"] = "0"
    f.items["IID_竜石"]["legal_player_weapon"] = "0"
    f.items["IID_敵の剣"]["legal_player_weapon"] = "0"
    f.items["IID_鉄の弓"]["effective"] = "JCID_飛行"
    f.items["IID_鋼の弓"]["effective"] = "JCID_飛行"
    f.items["IID_アーマーキラー"]["effective"] = "JCID_アーマー"
    f.items["IID_ドラゴンキラー"] = fill(TE.item(31, "IID_ドラゴンキラー", 0, 21, 2500, "ISID_非特効時威力－"),
                                     9, 95, 0, 0, 0, (1, 1))
    f.items["IID_ドラゴンキラー"]["effective"] = "JCID_竜|JCID_獣"
    f.item_list.append(f.items["IID_ドラゴンキラー"])
    f.item_list.sort(key=lambda i: R.ival(i["index"]))
    # a drop: unit A010 #2's steel sword marked as the unit item (bit 0)
    for d in t.dispos:
        for s in W.ITEM_SLOTS:
            d.setdefault(f"item_{s}_flags", "0")
    return t


def run(t, seed, o=None, enemies_edits=None):
    o = dict(ALL if o is None else o)
    full = dict(o, enemies_edits=enemies_edits or [])
    e, l = W.plan_weapons(t, W.sub_rng(seed, o), full)
    return e, l, W.check_weapons(t, e, full)


def bad_of(g):
    return {k: v["detail"][:3] for k, v in g.items() if not v["ok"]}


class FakeTableTests(unittest.TestCase):
    def setUp(self):
        self.t = fake()

    def test_off_means_no_edits(self):
        for o in ({}, {"stats": False, "traits": 0, "enemy_upgrade": 0}, {"variance": {"might": 5}},
                  {"wild_traits": True, "upgrade_rank": "next"}):
            for s in SEEDS[:5]:
                e, lines, g = run(self.t, s, o)
                self.assertEqual(e, [], (o, s))
                self.assertFalse(bad_of(g))
                self.assertEqual(len(lines), 1)

    def test_same_seed_same_output_and_seeds_differ(self):
        a = run(self.t, "same")
        b = run(fake(), "same")
        self.assertEqual(a[0], b[0])
        self.assertEqual(a[1], b[1])
        self.assertGreater(len({repr(run(self.t, s)[0]) for s in SEEDS[:10]}), 1)

    def test_guards_pass_many_seeds_and_options(self):
        for s in SEEDS:
            for o in (ALL, {"stats": True}, {"traits": 100}, {"traits": 100, "wild_traits": True},
                      {"enemy_upgrade": 100}, {"enemy_upgrade": 50, "upgrade_rank": "next", "stats": True},
                      {"stats": True, "variance": {"might": 10, "hit": 40, "crit": 30, "avoid": 30, "uses": 10}}):
                _e, _l, g = run(self.t, s, o)
                self.assertFalse(bad_of(g), (s, o, bad_of(g)))

    def test_bounds_and_variance(self):
        var = {"might": 3, "hit": 15, "crit": 7, "avoid": 6, "uses": 4}
        for s in SEEDS:
            e, _l, _g = run(self.t, s, {"stats": True, "variance": var})
            for x in e:
                it = self.t.f.items[x["label"]]
                for c, v in x["cells"].items():
                    old, new = R.ival(it[c]), R.ival(v)
                    lo, hi = W.bound(c, old)
                    self.assertLessEqual(abs(new - old), var[c], (x["label"], c))
                    self.assertTrue(lo <= new <= hi, (x["label"], c, new))
        with self.assertRaises(W.WeaponsError):
            W.norm_opts({"variance": {"might": 99}})
        with self.assertRaises(W.WeaponsError):
            W.norm_opts({"variance": {"weight": 3}})
        with self.assertRaises(W.WeaponsError):
            W.norm_opts({"traits": 101})
        with self.assertRaises(W.WeaponsError):
            W.norm_opts({"upgrade_rank": "two"})

    def test_kept_items_never_touched(self):
        kept = {"IID_夜刀神", "IID_雷神刀", "IID_ミステルトィン", "IID_葉隠", "IID_竜石", "IID_爪"}
        for s in SEEDS:
            e, _l, _g = run(self.t, s, {"stats": True, "traits": 100, "wild_traits": True})
            labels = {x["label"] for x in e}
            self.assertFalse(labels & kept, s)
            for x in e:
                if self.t.f.item_kind(x["label"]) == 6:          # staves: only uses
                    self.assertEqual(set(x["cells"]), {"uses"})
                    self.assertNotEqual(x["label"], "IID_大祭")    # infinite staff
        why = W.WeaponView(self.t.f).kept
        self.assertIn("legendary", why("IID_夜刀神"))
        self.assertIn("personal", why("IID_ミステルトィン"))
        self.assertIn("never the player's", why("IID_葉隠"))
        self.assertIsNone(why("IID_敵の剣"))                       # enemy-only weapons vary with the rest

    def test_traits_only_on_weapons_with_a_power(self):
        wv = W.WeaponView(self.t.f)
        self.assertTrue(wv.plain("IID_鉄の剣"))
        self.assertTrue(wv.plain("IID_青銅の剣"))
        self.assertTrue(wv.plain("IID_鉄の弓"))                   # bows' own flier effectiveness does not count
        self.assertFalse(wv.plain("IID_キルソード"))
        seen = set()
        for s in SEEDS:
            e, lines, g = run(self.t, s, {"traits": 100})
            self.assertFalse(bad_of(g))
            for x in e:
                self.assertTrue(wv.trait_ok(x["label"]), x["label"])
                self.assertNotIn(x["label"], ("IID_鉄の剣", "IID_青銅の剣", "IID_鋼の剣", "IID_敵の剣", "IID_鉄の弓"))
                c = x["cells"]
                if "flags" in c:
                    seen.add(c["flags"].split("|")[-1])
                    self.assertNotIn(W.F_BRAVE, c["flags"])        # brave only with wild traits
                seen |= {k for k in c if k != "flags"}
        self.assertIn(W.F_REVERSE, seen)
        self.assertIn("crit", seen)
        self.assertIn("effective", seen)
        self.assertTrue(any(k.startswith("stat_bonus.") for k in seen))

    def test_guard_catches_bad_edits(self):
        f = self.t.f
        o = {"stats": True, "traits": 50}
        bads = [
            [{"table": "Item", "index": 20, "label": "IID_夜刀神", "cells": {"might": "9"}}],
            [{"table": "Item", "index": 3, "label": "IID_鋼の剣", "cells": {"might": "30"}}],
            [{"table": "Item", "index": 3, "label": "IID_鋼の剣", "cells": {"buy_price": "1"}}],
            [{"table": "Item", "index": 9, "label": "IID_ライブ", "cells": {"might": "11"}}],
            [{"table": "Item", "index": 24, "label": "IID_キルソード", "cells": {"flags": ""}}],
            [{"table": "Item", "index": 24, "label": "IID_キルソード",
              "cells": {"flags": "ISID_必殺倍率＋|ISID_攻撃時2回攻撃"}}],                    # brave without wild
            [{"table": "Item", "index": 24, "label": "IID_キルソード",
              "cells": {"effective": "JCID_飛行", "stat_bonus.str": "2"}}],                 # two traits
            [{"table": "Item", "index": 2, "label": "IID_鉄の剣", "cells": {"effective": "JCID_竜"}}],  # plain
            [{"table": "DisposUnit", "file": "GameData/Dispos/A010.bin.lz", "index": 1, "label": "",
              "column": "item_1", "old": "IID_鉄の斧", "new": "IID_鋼の斧"}],               # upgrade off
        ]
        for edits in bads:
            g = W.check_weapons(self.t, edits, o)
            self.assertTrue(bad_of(g), edits)
        up = {"enemy_upgrade": 50}
        bads = [
            [{"table": "DisposUnit", "file": "GameData/Dispos/A010.bin.lz", "index": 1, "label": "",
              "column": "item_1", "old": "IID_鉄の斧", "new": "IID_銀の斧"}],               # two ranks up
            [{"table": "DisposUnit", "file": "GameData/Dispos/A010.bin.lz", "index": 1, "label": "",
              "column": "item_1", "old": "IID_鉄の斧", "new": "IID_鉄の槍"}],               # another kind
            [{"table": "DisposUnit", "file": "GameData/Dispos/A010.bin.lz", "index": 10, "label": "",
              "column": "item_1", "old": "IID_鉄の斧", "new": "IID_鋼の斧"}],               # scripted unit
            [{"table": "DisposUnit", "file": "GameData/Dispos/A010.bin.lz", "index": 1, "label": "",
              "column": "item_2", "old": "IID_傷薬", "new": "IID_鋼の斧"}],                 # not a weapon
            [{"table": "DisposUnit", "file": "GameData/Dispos/B009.bin.lz", "index": 0, "label": "",
              "column": "item_1", "old": "IID_鉄の斧", "new": "IID_鋼の斧"}],               # guarded chapter
        ]
        for edits in bads:
            g = W.check_weapons(self.t, edits, up)
            self.assertTrue(bad_of(g), edits)
        _ = f

    def test_enemy_upgrades_legal(self):
        """Round 62 (F-049): an upgrade is one step on the same ladder (next rung) or a forge, by the difficulty;
        upgrade_rank is still taken and changes nothing."""
        f = self.t.f
        wv = W.WeaponView(f)
        lines = W.ladder_lines(wv)
        tiers = {"easy": 0, "normal": 0, "hard": 0}
        for s in SEEDS:
            for diff in ("easy", "normal", "hard"):
                for mode in ("same", "next"):
                    e, _l, g = run(self.t, s, {"enemy_upgrade": 100, "upgrade_rank": mode, "difficulty": diff})
                    self.assertFalse(bad_of(g), (s, diff, mode))
                    for x in e:
                        self.assertEqual(x["table"], "DisposUnit")
                        d = [d for d in self.t.dispos if d["file"] == x["file"] and R.ival(d["index"]) == x["index"]][0]
                        self.assertIsNone(self.t.out_of_scope(d) or self.t.scripted(d))
                        if "_forge." in x["column"]:
                            self.assertTrue(0 <= R.ival(x["new"]) <= W.FORGE_TOP)
                            self.assertGreater(R.ival(x["new"]), R.ival(x["old"]))
                            continue
                        self.assertNotEqual(diff, "easy")
                        self.assertEqual(W.next_rung(lines, x["old"]), x["new"])
                        self.assertEqual(f.item_rank(x["new"]), W.next_rank(f.item_rank(x["old"])))
                        tiers[diff] += 1
        self.assertEqual(tiers["easy"], 0)
        self.assertEqual(tiers["normal"], tiers["hard"])

    def test_upgrade_never_loses_an_effective_bonus(self):
        """Round W1 (Grok's pick (a), WIRE_56 2c): a weapon that is effective against a class group is upgraded only
        into one that keeps that bonus; the guard catches a hand-made upgrade that loses it."""
        import copy
        t = copy.deepcopy(self.t)
        f = t.f
        wv = W.WeaponView(f)
        jid = next(j for j in f.jobs if f.wexp_max(f.jobs[j])[0] > 0 and t.can_hold(j, False, "IID_鋼の剣"))
        rank = f.item_rank("IID_鉄の剣")
        before = W.upgrade_pool(t, wv, {}, jid, False, "IID_鉄の剣", 0, rank, False, "next")
        self.assertIn("IID_鋼の剣", before)
        f.items["IID_鉄の剣"]["effective"] = "JCID_竜"                 # an iron sword that slays dragons
        wv = W.WeaponView(f)
        after = W.upgrade_pool(t, wv, {}, jid, False, "IID_鉄の剣", 0, rank, False, "next")
        self.assertNotIn("IID_鋼の剣", after)
        for c in after:
            self.assertIn("JCID_竜", R.flags(f.items[c].get("effective", "")))
        for seed in SEEDS:
            e, _l, g = run(t, seed, {"enemy_upgrade": 100, "upgrade_rank": "next"})
            self.assertFalse(bad_of(g), seed)
            self.assertFalse([x for x in e if x["old"] == "IID_鉄の剣"], seed)
        d = next((d for d in t.dispos if t.out_of_scope(d) is None and t.scripted(d) is None
                  and any(d.get(f"item_{s}") == "IID_鉄の剣" for s in W.ITEM_SLOTS)), None)
        if d is not None:
            s_ = next(s for s in W.ITEM_SLOTS if d.get(f"item_{s}") == "IID_鉄の剣")
            bad = [{"table": "DisposUnit", "file": d["file"], "index": R.ival(d["index"]), "label": d.get("label", ""),
                    "column": f"item_{s_}", "old": "IID_鉄の剣", "new": "IID_鋼の剣"}]
            g = W.check_weapons(t, bad, {"enemy_upgrade": 100, "upgrade_rank": "same", "enemies_edits": []})
            self.assertIn("effective", " ".join(g["enemy_upgrades_legal"]["detail"]))

    def test_drops_and_unusable_weapons_kept(self):
        d = [d for d in self.t.dispos if d["file"].endswith("A010.bin.lz") and R.ival(d["index"]) == 1][0]
        d["item_1_flags"] = "1"                   # the iron axe becomes a drop
        for s in SEEDS:
            e, _l, g = run(self.t, s, {"enemy_upgrade": 100, "upgrade_rank": "next"})
            self.assertFalse(bad_of(g))
            self.assertFalse([x for x in e if x["file"] == d["file"] and x["index"] == 1 and x["column"] == "item_1"])

    def test_on_top_of_the_enemies_track(self):
        for s in SEEDS[:15]:
            eo = TE.ALL_ON
            ee, _ = E.plan_enemies(self.t, E.track_rng(s, eo), eo)
            e, _l, g = run(self.t, s, {"enemy_upgrade": 100, "upgrade_rank": "next"}, ee)
            self.assertFalse(bad_of(g), s)
            after = W._apply_chain(self.t, ee)
            for x in e:
                row = after.get((x["file"], x["index"]))
                if row is not None:
                    self.assertEqual(str(row.get(x["column"], "0")), str(x["old"]))
            # the same edits checked against the wrong chain fail
            if any((x["file"], x["index"]) in after and after[(x["file"], x["index"])] != {}
                   for x in e if x["table"] == "DisposUnit"):
                g2 = W.check_weapons(self.t, e, {"enemy_upgrade": 100, "upgrade_rank": "next", "enemies_edits": []})
                changed = [x for x in e if (x["file"], x["index"]) in after
                           and str(next(d for d in self.t.dispos if d["file"] == x["file"]
                                        and R.ival(d["index"]) == x["index"]).get(x["column"])) != x["old"]]
                if changed:
                    self.assertTrue(bad_of(g2))

    def test_track_streams_independent(self):
        """Weapon stats do not depend on the trait or upgrade switches, and one item's draw on another's."""
        a = run(self.t, "ind", {"stats": True})[0]
        b = [x for x in run(self.t, "ind", {"stats": True, "enemy_upgrade": 100})[0] if x["table"] == "Item"]
        self.assertEqual(a, b)

    def test_facts_alone_are_enough_without_upgrades(self):
        e, _l, g = run(self.t.f, "facts", {"stats": True, "traits": 50})
        self.assertFalse(bad_of(g))
        with self.assertRaises(W.WeaponsError):
            run(self.t.f, "facts", {"enemy_upgrade": 10})


@unittest.skipIf(GD is None, "no extracted RomFS / table layouts here")
class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = E.load_tables(names=False)

    def test_many_seeds_all_guards(self):
        for n in range(6):
            for o in (ALL, {"stats": True, "traits": 25, "enemy_upgrade": 25},
                      {"stats": True, "variance": {"might": 10, "hit": 40, "crit": 30, "avoid": 30, "uses": 10}}):
                e, _l, g = run(self.t, f"real{n}", o)
                self.assertFalse(bad_of(g), (n, o, bad_of(g)))
                self.assertTrue(e)

    def test_off_no_edits_real(self):
        e, _l, g = run(self.t, "realoff", {})
        self.assertEqual(e, [])

    def test_yato_and_legendaries_kept_real(self):
        f = self.t.f
        e, _l, _g = run(self.t, "realkeep", {"stats": True, "traits": 100, "wild_traits": True})
        for x in e:
            fl = R.flags(f.items[x["label"]]["flags"])
            self.assertFalse(fl & W.KEEP_FLAGS, x["label"])
            self.assertIn(R.ival(f.items[x["label"]]["legal_player_weapon"]) in (1, 2) or W.ENEMY_ONLY in fl,
                          (True,))

    def test_on_top_of_the_enemies_track_real(self):
        eo = dict(E.DEFAULT_OPTS, enemy_classes=True)
        ee, _ = E.plan_enemies(self.t, E.track_rng("realchain", eo), eo)
        e, _l, g = run(self.t, "realchain", {"enemy_upgrade": 50, "upgrade_rank": "next"}, ee)
        self.assertFalse(bad_of(g))

    def test_mods_tool_accepts_the_folder(self):
        import mods as M
        o = {"stats": True, "traits": 50, "enemy_upgrade": 50}
        e, _l, g = run(self.t, "modscheck", o)
        files = W.edits_to_files(self.t.f, e, self.t.dispos)
        files["mod.json"] = b'{"name": "wcheck", "description": "test", "enabled": true, "order": 100, ' \
                            b'"override": false, "randomizer": {"weapons": {}}}\n'
        os.makedirs(TMP, exist_ok=True)
        d = os.path.join(TMP, "Rando-wcheck")
        try:
            R.write_mod(files, d)
            changes, errors, _w = M.diff_mod(M.Mod(d))
            self.assertEqual(errors, [])
            tables = {k[0] for k in changes}
            self.assertEqual(tables, {"Item", "DisposUnit"})
        finally:
            shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
