"""Self-tests for the randomizer's music track (tools/randomizer/music.py; docs/rando/MUSIC.md).

    python -m unittest tests.test_rando_music          (from the repo root)

Made-up tables and a made-up map-settings file first (no game data); the last class runs on the user's own
extracted RomFS when it is there (skipped otherwise): many seeds and both modes through every guard, a rebuilt
map file read back, and the mods tool accepts the folder.
"""
from __future__ import annotations

import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
sys.path.insert(0, os.path.join(ROOT, "tools", "assets"))
import randolib as R  # noqa: E402
import music as MU  # noqa: E402

MAPS5 = ["STRM_MAP_A1", "STRM_MAP_A2", "STRM_MAP_B1", "STRM_MAP_B2", "STRM_MAP_C1"]
BOSS3 = ["STRM_BOSS_A1", "STRM_BOSS_B1", "STRM_BOSS_C1", "STRM_BOSS_E1"]
OTHER = {"STRM_MAPEX_A1": 3, "STRM_SYS_BASE_A1": 2, "STRM_EVT_SAD_E1": 2, "STRM_VO_AQUA_WS": 1,
         "STRM_FF_LVUP1": 2, "STRM_SYS_GAMEOVER_E1": 2, "STRM_MAP_Z9": 3}


def cfg(stem, main=None, second=None, prep="STRM_SYS_BASE_A1", schema=None):
    return {"file": f"map/config/{stem}.bin", "cid": f"CID_{stem}", "player_bgm": main, "player_bgm_2": second,
            "advance_bgm": prep, "schema": schema}


def unit(ix, label, music="", f="GameData/Person/A002.bin.lz", table="PersonChapter"):
    return {"table": table, "file": f, "index": str(ix), "label": label, "combat_music": music}


def tables(**kw):
    maps = kw.get("maps", [cfg("A001", "STRM_MAP_A1"), cfg("A002", "STRM_MAP_A1"), cfg("A003", "STRM_MAP_B1"),
                           cfg("A004", None, prep=None), cfg("C017", "STRM_MAP_A2", "STRM_MAP_B2"),
                           cfg("A028", "STRM_MAPEX_A1"), cfg("B001", "STRM_MAP_Z9"),
                           cfg("X001", "STRM_MAP_C1"), cfg("BAD", "STRM_MAP_A1", schema="odd file")])
    persons = kw.get("persons", [unit(0, "PID_A", "STRM_BOSS_A1"), unit(1, "PID_B", "STRM_BOSS_A1"),
                                 unit(2, "PID_C", ""), unit(3, "PID_D", "STRM_BOSS_B1"),
                                 unit(0, "PID_E", "STRM_BOSS_A1", f="GameData/Person/A\\A007.bin.lz"),
                                 unit(1, "PID_F", "STRM_BOSS_C1", f="GameData/Person/A\\A007.bin.lz"),
                                 unit(0, "PID_G", "STRM_BOSS_E1", f="GameData/Person/X001.bin.lz"),
                                 unit(5, "PID_H", "", f="", table="Person")])
    layouts = dict({m: 5 for m in MAPS5}, **{b: 3 for b in BOSS3}, **OTHER)
    labels = set(layouts) | {"STRM_MAP_GHOST"}
    return MU.MusicTables(maps, persons, labels, layouts, {"STRM_MAP_A1": "Song A1"})


def ok(g):
    return all(v["ok"] for v in g.values())


class OptionTests(unittest.TestCase):
    def test_modes(self):
        self.assertEqual(MU.check_opts(None), {"music": "off"})
        self.assertEqual(MU.check_opts({"music": "Maps+Battles"})["music"], "maps+battles")
        self.assertEqual(MU.check_opts({"music": True})["music"], "maps+battles")
        self.assertEqual(MU.check_opts({"music": False})["music"], "off")
        with self.assertRaises(R.RandoError):
            MU.check_opts({"music": "everything"})

    def test_off_makes_no_edits(self):
        t = tables()
        for o in (None, {}, {"music": "off"}):
            e, lines = MU.plan_music(t, "seed1", o)
            self.assertEqual((e, lines), ([], []))
            self.assertTrue(ok(MU.run_guards(t, e, o)))
        self.assertEqual(MU.edits_to_files(t, [], read_raw=lambda rel: b""), {})

    def test_guard_catches_edits_with_off(self):
        t = tables()
        e, _ = MU.plan_music(t, "s", {"music": "maps"})
        self.assertFalse(MU.run_guards(t, e, {"music": "off"})["off makes no edits"]["ok"])


class PlanTests(unittest.TestCase):
    def test_pools_only_music_of_the_right_role_and_layout(self):
        mp, bp, ex = MU.pools(tables())
        self.assertEqual(mp, ["STRM_MAP_A1", "STRM_MAP_A2", "STRM_MAP_B1", "STRM_MAP_B2", "STRM_MAP_C1"])
        self.assertEqual(bp, BOSS3)
        self.assertIn("STRM_MAPEX_A1", ex)                      # finale theme: other layout, other name
        self.assertIn("another stream layout", ex["STRM_MAP_Z9"])
        for lab in ("STRM_SYS_BASE_A1", "STRM_EVT_SAD_E1", "STRM_VO_AQUA_WS", "STRM_FF_LVUP1"):
            self.assertNotIn(lab, mp + bp)
            self.assertFalse(MU.is_music(lab, "map") or MU.is_music(lab, "battle"))

    def test_label_unknown_to_the_sound_archive_is_not_used(self):
        t = tables(maps=[cfg("A001", "STRM_MAP_A1"), cfg("A002", "STRM_MAP_GHOST")])
        t.layouts["STRM_MAP_GHOST"] = 5
        t.sound_labels.discard("STRM_MAP_GHOST")
        mp, _bp, ex = MU.pools(t)
        self.assertNotIn("STRM_MAP_GHOST", mp)
        self.assertIn("sound archive", ex["STRM_MAP_GHOST"])

    def test_maps_mode(self):
        t = tables()
        for n in range(40):
            e, lines = MU.plan_music(t, f"s{n}", {"music": "maps"})
            g = MU.run_guards(t, e, {"music": "maps"})
            self.assertTrue(ok(g), {k: v for k, v in g.items() if not v["ok"]})
            self.assertTrue(all(x["table"] == "MapConfig" for x in e))
            files = {x["file"] for x in e}
            # every chapter with a pooled theme changes; empty, finale, odd-layout and unreadable ones never
            self.assertEqual({f for f in files}, {"map/config/A001.bin", "map/config/A002.bin", "map/config/A003.bin",
                                                  "map/config/C017.bin", "map/config/X001.bin"})
            for x in e:
                self.assertNotEqual(x["old"], x["new"])
                self.assertIn(x["new"], MAPS5)
                self.assertIn(x["cell"], MU.MAP_CELLS)
            c17 = {x["cell"]: x["new"] for x in e if x["file"].endswith("C017.bin")}
            self.assertEqual(set(c17), {"player_bgm", "player_bgm_2"})
            self.assertNotEqual(c17["player_bgm"], c17["player_bgm_2"])
            self.assertTrue(any("Kept as they are" in s for s in lines))

    def test_battles_mode(self):
        t = tables()
        seen_new = set()
        for n in range(40):
            e, _ = MU.plan_music(t, f"s{n}", {"music": "maps+battles"})
            g = MU.run_guards(t, e, {"music": "maps+battles"})
            self.assertTrue(ok(g), {k: v for k, v in g.items() if not v["ok"]})
            b = [x for x in e if x["cell"] == "combat_music"]
            self.assertEqual({(x["file"], x["index"]) for x in b},
                             {("GameData/Person/A002.bin.lz", 0), ("GameData/Person/A002.bin.lz", 1),
                              ("GameData/Person/A002.bin.lz", 3), ("GameData/Person/A\\A007.bin.lz", 0),
                              ("GameData/Person/A\\A007.bin.lz", 1), ("GameData/Person/X001.bin.lz", 0)})
            a, bb = [x["new"] for x in b if x["label"] in ("PID_A", "PID_B")]
            self.assertEqual(a, bb)                               # same old theme in one chapter -> same new
            for x in b:
                self.assertIn(x["new"], BOSS3)
                self.assertNotEqual(x["new"], x["old"])
                seen_new.add(x["new"])
        self.assertEqual(seen_new, set(BOSS3))

    def test_every_chapter_still_has_a_track(self):
        t = tables()
        e, _ = MU.plan_music(t, "x", {"music": "maps+battles"})
        after = {m["file"]: dict(m) for m in t.maps}
        for x in e:
            if x["table"] == "MapConfig":
                after[x["file"]][x["cell"]] = x["new"]
        for m in t.maps:
            self.assertEqual(bool(m["player_bgm"]), bool(after[m["file"]]["player_bgm"]))
            self.assertEqual(m["advance_bgm"], after[m["file"]]["advance_bgm"])

    def test_same_seed_same_edits_and_seeds_differ(self):
        t = tables()
        a = MU.plan_music(t, "abc", {"music": "maps+battles"})
        self.assertEqual(a, MU.plan_music(t, "abc", {"music": "maps+battles"}))
        self.assertNotEqual(a[0], MU.plan_music(t, "abd", {"music": "maps+battles"})[0])
        # the maps part does not depend on whether battles are on
        m = [x for x in a[0] if x["table"] == "MapConfig"]
        self.assertEqual(m, MU.plan_music(t, "abc", {"music": "maps"})[0])

    def test_random_object_as_rng(self):
        import random
        e1, _ = MU.plan_music(tables(), random.Random(5), {"music": "maps"})
        e2, _ = MU.plan_music(tables(), random.Random(5), {"music": "maps"})
        self.assertEqual(e1, e2)

    def test_guards_catch_bad_edits(self):
        t = tables()
        base = {"table": "MapConfig", "file": "map/config/A001.bin", "cid": "CID_A001", "cell": "player_bgm",
                "old": "STRM_MAP_A1"}
        o = {"music": "maps+battles"}
        cases = {
            "only music labels of the right role, named by the sound archive":
                [dict(base, new="STRM_SYS_BASE_A1")],
            "same stream layout as the track replaced": [dict(base, new="STRM_MAPEX_A1")],
            "only the map-theme cells and combat_music are written": [dict(base, cell="advance_bgm", new="STRM_MAP_A2")],
            "old values match the game's tables": [dict(base, old="STRM_MAP_B1", new="STRM_MAP_A2")],
            "every chapter that had a map theme still has one (and none gains one)":
                [{"table": "MapConfig", "file": "map/config/A004.bin", "cid": "CID_A004", "cell": "player_bgm",
                  "old": None, "new": "STRM_MAP_A2"}],
            "one chapter: the same old battle theme -> the same new one":
                [{"table": "PersonChapter", "file": "GameData/Person/A002.bin.lz", "index": 0, "label": "PID_A",
                  "cell": "combat_music", "old": "STRM_BOSS_A1", "new": "STRM_BOSS_B1"},
                 {"table": "PersonChapter", "file": "GameData/Person/A002.bin.lz", "index": 1, "label": "PID_B",
                  "cell": "combat_music", "old": "STRM_BOSS_A1", "new": "STRM_BOSS_C1"}],
        }
        for name, edits in cases.items():
            g = MU.run_guards(t, edits, o)
            self.assertFalse(g[name]["ok"], name)
        # a unit with no theme never gets one
        g = MU.run_guards(t, [{"table": "PersonChapter", "file": "GameData/Person/A002.bin.lz", "index": 2,
                               "label": "PID_C", "cell": "combat_music", "old": "", "new": "STRM_BOSS_B1"}], o)
        self.assertFalse(g["old values match the game's tables"]["ok"])
        # battle themes with maps only
        g = MU.run_guards(t, [{"table": "PersonChapter", "file": "GameData/Person/A002.bin.lz", "index": 0,
                               "label": "PID_A", "cell": "combat_music", "old": "STRM_BOSS_A1",
                               "new": "STRM_BOSS_B1"}], {"music": "maps"})
        self.assertFalse(g["only the map-theme cells and combat_music are written"]["ok"])

    def test_spoiler_uses_song_names(self):
        e, lines = MU.plan_music(tables(), "names", {"music": "maps"})
        self.assertTrue(any("Song A1 [STRM_MAP_A1] ->" in s for s in lines), lines)


# ------------------------------------------------------------------ a made-up map-settings file (no game data)
def fake_config(main, second=None, prep="STRM_SYS_BASE_A1") -> bytes:
    import isbin
    sheet = MU.SHEET
    data = bytearray(160)
    str_at: dict[int, bytes] = {}
    data_ptr: dict[int, int] = {}
    struct.pack_into("<I", data, 0, len(MU.SCHEMA))
    for i, (name, kind, _c) in enumerate(MU.SCHEMA):
        str_at[4 + 20 * i] = name.encode("cp932")
        str_at[8 + 20 * i] = kind.encode("ascii")
    str_at[0x7C] = sheet
    struct.pack_into("<HH", data, 0x80, 1, 0x10)
    data_ptr[0x84] = 0x88
    for o, v in ((0x88, main), (0x8C, second), (0x90, prep)):
        if v:
            str_at[o] = v.encode("ascii")
    struct.pack_into("<I", data, 0x98, 1)
    str_at[0x9C] = sheet
    labels = [(0, b"MOD_" + sheet), (0x7C, sheet), (0x88, b"DAT_" + sheet), (0x98, b"SHEET_LIST")]
    relocs = sorted(set(str_at) | set(data_ptr))
    tab, noffs, soffs = isbin.build_pool([n for _o, n in labels], [str_at[r] for r in relocs if r in str_at])
    se = len(data) + 4 * len(relocs) + 8 * len(labels)
    for r, so in zip([r for r in relocs if r in str_at], soffs):
        struct.pack_into("<I", data, r, se + so)
    for r, v in data_ptr.items():
        struct.pack_into("<I", data, r, v)
    b = isbin.IsBin()
    b.data, b.relocs, b.strtab = bytes(data), relocs, tab
    b.labels = [(o, n, no) for (o, n), no in zip(labels, noffs)]
    return b.build()


class FileTests(unittest.TestCase):
    def test_parse_and_rebuild_made_up_file(self):
        raw = fake_config("STRM_MAP_A1", "STRM_MAP_B2")
        row = MU.parse_config("map/config/C017.bin", raw)
        self.assertIsNone(row["schema"])
        self.assertEqual((row["player_bgm"], row["player_bgm_2"], row["advance_bgm"]),
                         ("STRM_MAP_A1", "STRM_MAP_B2", "STRM_SYS_BASE_A1"))
        self.assertEqual(MU.rebuild_config("map/config/C017.bin", raw, {}), raw)   # no change: same bytes
        out = MU.rebuild_config("map/config/C017.bin", raw, {"player_bgm": "STRM_MAP_C1"})
        row2 = MU.parse_config("map/config/C017.bin", out)
        self.assertEqual((row2["player_bgm"], row2["player_bgm_2"], row2["advance_bgm"]),
                         ("STRM_MAP_C1", "STRM_MAP_B2", "STRM_SYS_BASE_A1"))
        with self.assertRaises(R.RandoError):
            MU.rebuild_config("map/config/C017.bin", raw, {"advance_bgm": "STRM_MAP_C1"})

    def test_empty_theme_is_never_added(self):
        raw = fake_config("STRM_MAP_A1")
        self.assertIsNone(MU.parse_config("map/config/A001.bin", raw)["player_bgm_2"])
        with self.assertRaises(R.RandoError):
            MU.rebuild_config("map/config/A001.bin", raw, {"player_bgm_2": "STRM_MAP_C1"})

    def test_unknown_schema_is_kept(self):
        raw = bytearray(fake_config("STRM_MAP_A1"))
        # rename the first field's type string "str" -> "s16" in the string pool: the file no longer matches
        i = raw.rfind(b"str\0")
        raw[i:i + 3] = b"s16"
        row = MU.parse_config("map/config/A001.bin", bytes(raw))
        self.assertIsNotNone(row["schema"])
        self.assertIsNotNone(MU.parse_config("map/config/A001.bin", b"not a table file")["schema"])

    def test_edits_to_files(self):
        raws = {"map/config/A001.bin": fake_config("STRM_MAP_A1"),
                "map/config/C017.bin": fake_config("STRM_MAP_A2", "STRM_MAP_B2")}
        t = MU.MusicTables([MU.parse_config(k, v) for k, v in raws.items()],
                           [unit(0, "PID_A", "STRM_BOSS_A1"), unit(1, "PID_B", "")],
                           None, dict({m: 5 for m in MAPS5}, **{b: 3 for b in BOSS3}))
        e, spoil = MU.plan_music(t, "files", {"music": "maps+battles"})
        self.assertTrue(ok(MU.run_guards(t, e, {"music": "maps+battles"})))
        files = MU.edits_to_files(t, e, read_raw=raws.__getitem__)
        self.assertEqual(set(files), {"romfs/map/config/A001.bin", "romfs/map/config/C017.bin",
                                      "tables/PersonChapter.csv"})
        for rel in raws:
            row = MU.parse_config(rel, files["romfs/" + rel])
            for x in e:
                if x["table"] == "MapConfig" and x["file"] == rel:
                    self.assertEqual(row[x["cell"]], x["new"])
        csv = files["tables/PersonChapter.csv"].decode("utf-8").lstrip("﻿").splitlines()
        self.assertEqual(csv[0], "file,index,label,combat_music")
        self.assertEqual(len(csv), 2)
        self.assertTrue(csv[1].startswith("GameData/Person/A002.bin.lz,0,PID_A,STRM_BOSS_"))
        rendered = MU.render(t, "files", {"music": "maps+battles"}, e, spoil,
                             MU.run_guards(t, e, {"music": "maps+battles"}), read_raw=raws.__getitem__)
        self.assertIn("mod.json", rendered)
        self.assertIn("PASS", rendered["spoiler-music.txt"].decode("utf-8"))

    def test_refuses_owner_folders(self):
        self.assertIsNotNone(MU._forbidden(os.path.join(ROOT, "mods", "x")))
        self.assertIsNone(MU._forbidden(os.path.join(ROOT, "build", "rando55", "music")))


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
        cls.t = MU.load_tables()

    def test_facts(self):
        mp, bp, ex = MU.pools(self.t)
        self.assertGreaterEqual(len(mp), 10)
        self.assertGreaterEqual(len(bp), 10)
        self.assertFalse([m for m in self.t.maps if m["schema"]])
        self.assertTrue(all(x.startswith("STRM_MAP_") for x in mp))
        self.assertTrue(all(x.startswith("STRM_BOSS_") for x in bp))
        self.assertTrue(all(k.startswith("STRM_MAPEX_") for k in ex), ex)

    def test_many_seeds_both_modes(self):
        for n in range(15):
            for mode in ("maps", "maps+battles"):
                e, _ = MU.plan_music(self.t, f"real{n}", {"music": mode})
                g = MU.run_guards(self.t, e, {"music": mode})
                self.assertTrue(ok(g), (n, mode, {k: v for k, v in g.items() if not v["ok"]}))
                self.assertEqual(e, MU.plan_music(self.t, f"real{n}", {"music": mode})[0])
        self.assertEqual(MU.plan_music(self.t, "real0", {"music": "off"})[0], [])

    def test_fits_rule_never_a_longer_name(self):
        """Round 59 (Grok's pick A, docs/collab/E1_MUSIC_GROK.md): a new name is never longer than the old one, so
        the in-game core can write it in place; the guard catches a longer one."""
        for n in range(40):
            e, _ = MU.plan_music(self.t, f"fits{n}", {"music": "maps+battles"})
            self.assertTrue(all(len(x["new"]) <= len(x["old"]) for x in e), n)
        e, _ = MU.plan_music(self.t, "fits0", {"music": "maps+battles"})
        bad = [dict(e[0], new=e[0]["old"] + "X")]
        g = MU.run_guards(self.t, bad, {"music": "maps+battles"})
        self.assertFalse(g["a new name is never longer than the old one (the in-game core writes it in place)"]["ok"])

    def test_rebuilt_files_read_back(self):
        e, _ = MU.plan_music(self.t, "readback", {"music": "maps+battles"})
        files = MU.edits_to_files(self.t, e)
        for x in e:
            if x["table"] == "MapConfig":
                row = MU.parse_config(x["file"], files["romfs/" + x["file"]])
                self.assertEqual(row[x["cell"]], x["new"])
                orig = next(m for m in self.t.maps if m["file"] == x["file"])
                self.assertEqual(row["advance_bgm"], orig["advance_bgm"])

    def test_mods_tool_accepts_the_folder(self):
        sys.path.insert(0, os.path.join(ROOT, "tools", "mods"))
        import mods as M
        with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, "build")) as d:
            seed = "r55music"
            o = {"music": "maps+battles"}
            e, spoil = MU.plan_music(self.t, seed, o)
            g = MU.run_guards(self.t, e, o)
            self.assertTrue(ok(g))
            R.write_mod(MU.render(self.t, seed, o, e, spoil, g), os.path.join(d, "mods", R.mod_name(seed) + "-music"))
            ctx = M.Ctx(mods_dir=os.path.join(d, "mods"), stage_dir=os.path.join(d, "stage"),
                        zakuro_dir=os.path.join(d, "zak"), quiet=True)
            r = M.compute(ctx)
            self.assertFalse(r.errors, r.errors[:5])


if __name__ == "__main__":
    unittest.main()
