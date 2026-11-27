"""Self-tests for the randomizer track "enemies" (tools/randomizer/enemies.py; docs/rando/ENEMIES.md).

    python -m unittest tests.test_rando_enemies          (from the repo root)

Small made-up tables (no game data). The last class runs on the user's own extracted RomFS when it is there
(skipped otherwise): many seeds through every guard.
"""
from __future__ import annotations

import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
import enemies as E  # noqa: E402
import randolib as R  # noqa: E402

S, K = R.STATS, R.KINDS
N = "JID_無し男"


def job(ix, label, *, kinds=(), female=False, promoted=False, origin=2, cat="", flags="", mov=5, mc=1):
    f = [x for x in (flags, "SPID_女性" if female else "", "SPID_上級職" if promoted else "") if x]
    j = {"index": str(ix), "label": label, "flags": "|".join(f), "category": cat, "origin": str(origin),
         "mjid_name": "", "promotion.1": N, "promotion.2": N, "mov": str(mov), "move_cost_class": str(mc)}
    for s in S:
        j[f"base.{s}"] = "2"
        j[f"max.{s}"] = "30"
    for k in K:
        j[f"max_weapon_exp.{k}"] = str(96 if k in kinds else 0)
    return j


def item(ix, label, sub, rank, price=1000, flags=""):
    return {"index": str(ix), "label": label, "flags": flags, "weapon_kind": str(sub), "weapon_rank": str(rank),
            "buy_price": str(price), "legal_player_weapon": "1", "miid_name": ""}


def pchap(ch, label, jid, *, female=False, unit_kind=0, mpid="MPID_兵", pflags=""):
    f = [x for x in (pflags, "SPID_女性" if female else "") if x]
    return {"file": f"GameData/Person/{ch}.bin.lz", "index": "0", "label": label, "flags": "|".join(f),
            "job": jid, "unit_kind": str(unit_kind), "mpid_name": mpid}


def disp(ch, ix, pid, team, x, y, *items, jid=""):
    d = {"file": f"GameData/Dispos/{ch}.bin.lz", "index": str(ix), "label": "", "pid": pid, "jid": jid,
         "team": str(team), "pos.x": str(x), "pos.y": str(y), "flags": "1792"}
    for s in range(1, 6):
        d[f"item_{s}"] = items[s - 1] if s <= len(items) else ""
    return d


# Terrain: column 4 plains (cost 1 for all), column 9 mountain (foot 3, armor impassable, horse impassable,
# flier 1), column 0 wall (only nobody).
COST = {0: [-1] * 16, 1: [-1, -1, -1, -1, 1, 2, 2, 2, 2, 3] + [-1] * 6,     # foot
        2: [-1, -1, -1, -1, 1, 2, 3, 3, 3, -1] + [-1] * 6,                    # armor
        3: [-1, -1, -1, -1, 1, 3, 3, 3, 3, -1] + [-1] * 6,                    # horse
        4: [-1, -1, -1, -1, 1, 1, 1, 1, 1, 1] + [-1] * 6}                     # flier


def grid(ch, rows):
    """rows: strings of '.', 'M', '#' (plains, mountain, wall); 32x32 grid, play area = the strings."""
    tiles = bytearray(1024)
    code = {".": 1, "M": 2, "#": 3}
    for y, line in enumerate(rows):
        for x, c in enumerate(line):
            tiles[x | (y << 5)] = code[c]
    g = {"file": f"GameData/Terrain/{ch}.bin.lz", "index": "0", "label": "", "play_x_min": "0", "play_y_min": "0",
         "play_x_end": str(len(rows[0])), "play_y_end": str(len(rows)), "tiles": tiles.hex()}
    tt = [{"file": g["file"], "index": str(i), "move_cost_column": str(c)} for i, c in enumerate([0, 4, 9, 0])]
    return g, tt


OPEN = ["." * 32] * 32
MOUNT = ["MMMMMMMMMMMM"] * 12


def fake(more_dispos=(), scripts=None):
    jobs = [job(0, N),
            job(1, "JID_アクスファイター男", kinds=("axe",)),
            job(2, "JID_マーシナリー男", kinds=("sword",)),
            job(3, "JID_アーマーナイト男", kinds=("lance",), mov=4, mc=2, cat="JCID_アーマー"),
            job(4, "JID_ソシアルナイト男", kinds=("sword", "lance"), mov=7, mc=3, cat="JCID_騎乗"),
            job(5, "JID_ダークマージ男", kinds=("tome",)),
            job(6, "JID_ロッドナイト男", kinds=("staff",), mov=7, mc=3),
            job(7, "JID_ドラゴンナイト男", kinds=("axe",), mov=7, mc=4, cat="JCID_飛行|JCID_竜"),
            job(8, "JID_ドラゴンナイト女", kinds=("axe",), female=True, mov=7, mc=4, cat="JCID_飛行|JCID_竜"),
            job(9, "JID_アクスファイター女", kinds=("axe",), female=True),
            job(10, "JID_マーシナリー女", kinds=("sword",), female=True),
            job(11, "JID_ノスフェラトゥ男", kinds=("stone",), flags="SPID_敵専用"),
            job(12, "JID_侍男", kinds=("sword",), origin=1),
            job(13, "JID_ジェネラル男", kinds=("lance", "axe"), promoted=True, mov=5, mc=2),
            job(14, "JID_シーフ男", kinds=("bow",), flags="SPID_村破壊"),
            job(15, "JID_天馬武者男", kinds=("lance",), origin=2, mov=7, mc=4, cat="JCID_飛行"),
            job(16, "JID_ストラテジスト男", kinds=("staff", "tome"), mov=7, mc=3)]
    subs = [{"index": str(i), "kind": str(k), "origin": str(o)} for i, (k, o) in enumerate(
        [(0, 2), (0, 1), (1, 2), (1, 1), (2, 2), (2, 1), (3, 2), (3, 1), (4, 2), (4, 1), (5, 2), (5, 1), (6, 2), (6, 1),
         (7, 0), (7, 0), (7, 0), (7, 0), (7, 2), (7, 1), (8, 0)])]
    items = [item(0, "IID_無し", 20, 0, 0), item(1, "IID_青銅の剣", 0, 1, 500), item(2, "IID_鉄の剣", 0, 21),
             item(3, "IID_鋼の剣", 0, 51), item(4, "IID_鉄の槍", 2, 21), item(5, "IID_鋼の槍", 2, 51),
             item(6, "IID_鉄の斧", 4, 21), item(7, "IID_鋼の斧", 4, 51), item(8, "IID_手斧", 4, 21),
             item(9, "IID_ライブ", 12, 1, 500), item(10, "IID_リライブ", 12, 21), item(11, "IID_サンダー", 10, 21),
             item(12, "IID_傷薬", 20, 0, 300), item(13, "IID_3000G", 20, 0, 0), item(14, "IID_鋼の刀", 1, 51),
             item(15, "IID_敵の剣", 0, 21, 0, "ISID_敵専用"), item(16, "IID_鉄の弓", 8, 21), item(17, "IID_銀の斧", 4, 96),
             item(18, "IID_ファイアー", 10, 1, 500), item(19, "IID_爪", 14, 1, 0)]
    persons = [{"index": "0", "label": "PID_無し", "flags": "", "mpid_name": "", "job": N},
               {"index": "1", "label": "PID_ニュクス", "flags": "SPID_女性", "mpid_name": "MPID_ニュクス", "job": N},
               {"index": "2", "label": "PID_魔物下級0", "flags": "", "mpid_name": "MPID_賊", "job": N}]
    pc = [pchap("A010", "PID_A010_斧", "JID_アクスファイター男"),
          pchap("A010", "PID_A010_剣", "JID_マーシナリー男"),
          pchap("A010", "PID_A010_重", "JID_アーマーナイト男"),
          pchap("A010", "PID_A010_騎", "JID_ソシアルナイト男"),
          pchap("A010", "PID_A010_杖", "JID_ロッドナイト男"),
          pchap("A010", "PID_A010_竜", "JID_ドラゴンナイト男"),
          pchap("A010", "PID_A010_竜女", "JID_ドラゴンナイト女", female=True),
          pchap("A010", "PID_A010_魔物", "JID_ノスフェラトゥ男"),
          pchap("A010", "PID_A010_ボス", "JID_ジェネラル男", unit_kind=2, mpid="MPID_ハンス"),
          pchap("A010", "PID_A010_話", "JID_アクスファイター男"),
          pchap("A010", "PID_A010_ニュクス", "JID_ダークマージ男", mpid="MPID_ニュクス"),
          pchap("A010", "PID_A010_賊", "JID_アクスファイター男", mpid="MPID_賊"),
          pchap("A010", "PID_A010_固定", "JID_マーシナリー男", pflags="SPID_移動禁止"),
          pchap("A011", "PID_A011_斧", "JID_アクスファイター男"),
          pchap("A011", "PID_A011_ボス", "JID_ジェネラル男", unit_kind=2, mpid="MPID_ハンス"),
          pchap("A011", "PID_A011_重", "JID_アーマーナイト男")]
    for g in ("B009", "B016", "C008", "C013"):
        pc.append(pchap(g, f"PID_{g}_斧", "JID_アクスファイター男"))
    dispos = [disp("A010", 0, "PID_プレイヤー男", 0, 0, 0, "IID_鉄の剣"),
              disp("A010", 1, "PID_A010_斧", 1, 5, 5, "IID_鉄の斧", "IID_傷薬"),
              disp("A010", 2, "PID_A010_剣", 1, 6, 5, "IID_鋼の剣", "IID_3000G"),
              disp("A010", 3, "PID_A010_重", 1, 7, 5, "IID_鉄の槍"),
              disp("A010", 4, "PID_A010_騎", 1, 8, 5, "IID_鉄の剣", "IID_鉄の槍"),
              disp("A010", 5, "PID_A010_杖", 1, 9, 5, "IID_ライブ", "IID_リライブ"),
              disp("A010", 6, "PID_A010_竜", 1, 5, 6, "IID_鉄の斧"),
              disp("A010", 7, "PID_A010_竜女", 1, 6, 6, "IID_手斧"),
              disp("A010", 8, "PID_A010_魔物", 1, 7, 6, "IID_爪"),
              disp("A010", 9, "PID_A010_ボス", 1, 8, 6, "IID_鋼の槍", "IID_鋼の斧"),
              disp("A010", 10, "PID_A010_話", 1, 9, 6, "IID_鉄の斧"),
              disp("A010", 11, "PID_ニュクス", 1, 10, 6, "IID_サンダー"),
              disp("A010", 12, "PID_A010_ニュクス", 1, 10, 7, "IID_サンダー"),
              disp("A010", 13, "PID_A010_賊", 1, 5, 7, "IID_鉄の斧"),
              disp("A010", 14, "PID_A010_斧", 1, 6, 7, "IID_鉄の斧"),           # Event group below
              disp("A010", 15, "PID_A010_剣", 1, 255, 255, "IID_敵の剣"),
              disp("A010", 16, "PID_A010_固定", 1, 7, 7, "IID_鉄の剣"),
              disp("A010", 17, "PID_A010_斧", 2, 8, 7, "IID_鉄の斧"),
              disp("A010", 18, "PID_A010_斧", 1, 9, 7, "IID_鉄の斧", jid="JID_マーシナリー男"),
              disp("A011", 0, "PID_A011_斧", 1, 3, 3, "IID_鋼の斧"),
              disp("A011", 1, "PID_A011_ボス", 1, 4, 4, "IID_銀の斧"),
              disp("A011", 2, "PID_A011_重", 1, 5, 5, "IID_鉄の槍")]
    for g in ("B009", "B016", "C008", "C013"):
        dispos.append(disp(g, 0, f"PID_{g}_斧", 1, 3, 3, "IID_鉄の斧"))
    dispos += list(more_dispos)
    fac = [{"file": "GameData/Dispos/A010.bin.lz", "group": "Player", "first_unit": "#0", "unit_count": "1"},
           {"file": "GameData/Dispos/A010.bin.lz", "group": "Enemy", "first_unit": "#1", "unit_count": "13"},
           {"file": "GameData/Dispos/A010.bin.lz", "group": "Event01", "first_unit": "#14", "unit_count": "1"},
           {"file": "GameData/Dispos/A010.bin.lz", "group": "Reinforce01", "first_unit": "#15", "unit_count": "4"},
           {"file": "GameData/Dispos/A011.bin.lz", "group": "Enemy", "first_unit": "#0", "unit_count": "3"}]
    for g in ("B009", "B016", "C008", "C013"):
        fac.append({"file": f"GameData/Dispos/{g}.bin.lz", "group": "Enemy", "first_unit": "#0", "unit_count": "1"})
    grids, tiles = [], []
    for ch, rows in (("A010", OPEN), ("A011", MOUNT), ("B009", OPEN), ("B016", OPEN), ("C008", OPEN), ("C013", OPEN)):
        g, tt = grid(ch, rows)
        grids.append(g)
        tiles += tt
    cost = [{"index": str(i), **{f"cost.{c}": str(v) for c, v in enumerate(COST.get(i, [-1] * 16))}}
            for i in range(16)]
    return E.EnemyTables(persons, pc, jobs, items, subs, dispos, fac, tiles, grids, cost,
                         scripts if scripts is not None else {"A010": {"PID_A010_話", "PID_A010_ボス"}})


ALL_ON = {"gear": True, "enemy_classes": True, "boss_classes": True, "trees": "own"}


def run(t, seed, o=ALL_ON):
    edits, spoil = E.plan_enemies(t, E.track_rng(seed, o), o)
    return edits, spoil, E.run_guards(t, edits, o)


class EnemiesTrack(unittest.TestCase):
    def test_guards_pass_many_seeds(self):
        t = fake()
        for n in range(60):
            for o in (ALL_ON, E.DEFAULT_OPTS, dict(ALL_ON, gear=False), dict(ALL_ON, trees="any")):
                edits, _s, g = run(t, f"s{n}", o)
                bad = {k: v["detail"] for k, v in g.items() if not v["ok"]}
                self.assertFalse(bad, (n, o, bad))

    def test_same_seed_same_edits_and_different_seed_differs(self):
        t = fake()
        a, b = run(t, "abc")[0], run(fake(), "abc")[0]
        self.assertEqual(a, b)
        self.assertTrue(any(run(t, f"x{n}")[0] != a for n in range(5)))

    def test_track_seed_is_its_own(self):
        """A track's stream depends only on the seed, the track and its options (never another track)."""
        self.assertEqual(E.track_rng("abc").random(), E.track_rng("abc").random())
        self.assertNotEqual(E.track_rng("abc").random(), R.rng_for("abc", R.DEFAULT_SWITCHES).random())

    def test_every_changed_enemy_has_legal_class_and_weapon(self):
        t = fake()
        seen_class = seen_weapon = False
        for n in range(40):
            edits, _s, _g = run(t, f"l{n}")
            rows = {}
            for e in edits:
                rows.setdefault((e["file"], e["index"]), {})[e["column"]] = e["new"]
            by = {(d["file"], int(d["index"])): d for d in t.dispos}
            for k, nd in rows.items():
                d = by[k]
                old = t.unit_job(d)
                new = nd.get("jid") or old
                oj, nj = t.f.jobs[old], t.f.jobs[new]
                self.assertEqual(t.f.female(oj), t.f.female(nj))
                self.assertEqual(t.f.promoted(oj), t.f.promoted(nj))
                self.assertEqual("JCID_飛行" in oj["category"], "JCID_飛行" in nj["category"])
                self.assertIsNone(t.kept_job(new))
                seen_class |= new != old
                for s in range(1, 6):
                    iid = nd.get(f"item_{s}", d[f"item_{s}"])
                    if t.f.item_kind(iid) is not None and t.can_hold(old, t.f.female(oj), d[f"item_{s}"]):
                        self.assertTrue(t.can_hold(new, t.f.female(oj), iid), (k, new, iid))
                        if iid != d[f"item_{s}"]:
                            seen_weapon = True
                            self.assertLessEqual(t.f.item_rank(iid), t.f.item_rank(d[f"item_{s}"]))
        self.assertTrue(seen_class and seen_weapon)

    def test_terrain_rule(self):
        t = fake()
        d_axe = [d for d in t.dispos if d["pid"] == "PID_A011_斧"][0]
        # on an all-mountain map: armor and horse cannot stand; foot units keep the same reach
        self.assertIsNotNone(t.terrain_ok(d_axe, "JID_アクスファイター男", "JID_アーマーナイト男"))
        self.assertIsNotNone(t.terrain_ok(d_axe, "JID_アクスファイター男", "JID_ソシアルナイト男"))
        self.assertIsNone(t.terrain_ok(d_axe, "JID_アクスファイター男", "JID_マーシナリー男"))
        # a 4-move armor cannot replace a 7-move horse on plains (less than 3/4 of the reach)
        d_cav = [d for d in t.dispos if d["pid"] == "PID_A010_騎"][0]
        self.assertIn("reaches", t.terrain_ok(d_cav, "JID_ソシアルナイト男", "JID_アーマーナイト男"))
        for n in range(40):
            edits, _s, _g = run(t, f"t{n}")
            for e in edits:
                if e["column"] == "jid" and e["file"].endswith("A011.bin.lz"):
                    self.assertNotIn(e["new"], ("JID_アーマーナイト男", "JID_ソシアルナイト男"))
                if e["column"] == "jid":
                    d = [d for d in t.dispos if d["file"] == e["file"] and int(d["index"]) == e["index"]][0]
                    self.assertIsNone(t.terrain_ok(d, t.unit_job(d), e["new"]))

    def test_guarded_chapters_and_scripted_units_unchanged(self):
        t = fake()
        never = {"PID_A010_話", "PID_ニュクス", "PID_A010_ニュクス", "PID_A010_魔物", "PID_プレイヤー男"}
        for n in range(40):
            edits, _s, _g = run(t, f"g{n}")
            for e in edits:
                ch = E.chapter_of(e["file"])
                self.assertNotIn(ch[:4], E.GUARDED)
                d = [d for d in t.dispos if d["file"] == e["file"] and int(d["index"]) == e["index"]][0]
                self.assertNotIn(d["pid"], never)
                self.assertEqual(d["team"], "1")
                self.assertFalse(e["file"].endswith("A010.bin.lz") and e["index"] == 14, "Event group unit changed")
                self.assertFalse(e["column"] == "jid" and d["pid"] in ("PID_A010_ボス", "PID_A010_固定"))
                self.assertFalse(e["column"] == "jid" and d["pid"] == "PID_A010_竜" and "JCID_飛行" not in
                                 t.f.jobs[e["new"]]["category"])
                self.assertIn(e["column"], ("jid", "item_1", "item_2", "item_3", "item_4", "item_5"))
                old = d.get(e["column"], "")
                self.assertFalse(e["column"] != "jid" and t.f.item_kind(old) is None, "a non-weapon changed")
                self.assertFalse(e["column"] != "jid" and t.special_item(old), "a special weapon changed")
        lst = E.scripted_list(t)
        reasons = {pid: why for _c, _i, pid, why in lst}
        self.assertIn("guarded", reasons["PID_B009_斧"])
        self.assertIn("script", reasons["PID_A010_話"])
        self.assertIn("main cast", reasons["PID_ニュクス"])
        self.assertIn("named person", reasons["PID_A010_ニュクス"])
        self.assertNotIn("PID_A010_賊", reasons)          # a generic name id shared with the main table

    def test_guard_catches_bad_edits(self):
        t = fake()
        bad = [{"table": "DisposUnit", "file": "GameData/Dispos/B009.bin.lz", "index": 0, "label": "",
                "column": "item_1", "old": "IID_鉄の斧", "new": "IID_鋼の斧"},
               {"table": "DisposUnit", "file": "GameData/Dispos/A011.bin.lz", "index": 0, "label": "",
                "column": "jid", "old": "", "new": "JID_アーマーナイト男"},
               {"table": "DisposUnit", "file": "GameData/Dispos/A010.bin.lz", "index": 1, "label": "",
                "column": "item_2", "old": "IID_傷薬", "new": "IID_鉄の斧"},
               {"table": "DisposUnit", "file": "GameData/Dispos/A010.bin.lz", "index": 1, "label": "",
                "column": "pos.x", "old": "5", "new": "6"},
               {"table": "DisposUnit", "file": "GameData/Dispos/A011.bin.lz", "index": 1, "label": "",
                "column": "item_1", "old": "IID_銀の斧", "new": "IID_鉄の剣"}]
        g = E.run_guards(t, bad, ALL_ON)
        for k in ("guarded_chapters_unchanged", "legal_class_weapons_terrain", "only_jid_and_item_cells",
                  "bosses_keep_a_usable_weapon"):
            self.assertFalse(g[k]["ok"], k)

    def test_bosses_keep_kind_and_rank(self):
        t = fake()
        for n in range(40):
            edits, _s, _g = run(t, f"b{n}")
            for e in edits:
                if "ボス" in e.get("old", "") or e["column"] == "jid":
                    continue
                d = [d for d in t.dispos if d["file"] == e["file"] and int(d["index"]) == e["index"]][0]
                if t.is_boss(d):
                    self.assertEqual(t.f.item_kind(e["old"]), t.f.item_kind(e["new"]))
                    self.assertEqual(t.f.item_rank(e["old"]), t.f.item_rank(e["new"]))

    def test_options_off_changes_nothing_and_classes_off_keeps_classes(self):
        t = fake()
        off = {"gear": False, "enemy_classes": False, "boss_classes": False, "trees": "own"}
        self.assertEqual(run(t, "z", off)[0], [])
        for n in range(20):
            self.assertFalse([e for e in run(t, f"d{n}", E.DEFAULT_OPTS)[0] if e["column"] == "jid"])


class RealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import gamedata as GD
            if GD.available():
                raise unittest.SkipTest("no extracted RomFS")
            cls.t = E.load_tables(names=False)
        except R.RandoError as e:
            raise unittest.SkipTest(str(e))

    def test_real_seeds_pass_every_guard(self):
        for n in range(4):
            for o in (ALL_ON, E.DEFAULT_OPTS):
                edits, _s, g = run(self.t, f"real{n}", o)
                bad = {k: v["detail"][:3] for k, v in g.items() if not v["ok"]}
                self.assertFalse(bad, (n, o, bad))
                self.assertTrue(edits)
                self.assertFalse([e for e in edits if E.chapter_of(e["file"])[:4] in E.GUARDED])

    def test_guarded_chapters_found_in_real_data(self):
        chs = {E.chapter_of(d["file"])[:4] for d in self.t.dispos}
        for g in E.GUARDED:
            self.assertIn(g, chs)


if __name__ == "__main__":
    unittest.main()
