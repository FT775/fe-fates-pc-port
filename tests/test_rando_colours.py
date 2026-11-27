"""Self-tests for the randomizer's colour track (tools/randomizer/colours.py; docs/rando/COLOURS.md).

    python -m unittest tests.test_rando_colours          (from the repo root)

Made-up tables first (a tiny model table, three people, their faces and map heads); the last class runs on the
user's own extracted RomFS (and Seal of Flames when installed) and is skipped otherwise.
"""
from __future__ import annotations

import os
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
import colours as C  # noqa: E402

RULES = {"player_army": "BID_P", "routes": {"A": "a", "B": "b", "C": "c"}, "keep_class_person_flags": ["SPID_AV"]}


def _rows(spec):
    """[(conds, {Hn: value})] -> (data bytes, relocs, strings) of a made-up model table."""
    data = bytearray(struct.pack("<I", 0x0FA01111))
    strs, rel = {}, set()
    for conds, hi_fields in spec:
        lo = 1 if hi_fields else 0
        for i in range(1, len(conds)):
            lo |= 1 << i
        hi = 0
        for k in hi_fields:
            hi |= 1 << int(k[1:])
        data += struct.pack("<I", lo)
        if lo & 1:
            data += struct.pack("<I", hi)
        for c in conds:
            rel.add(len(data))
            strs[len(data)] = c
            data += b"\0\0\0\0"
        for k in sorted(hi_fields, key=lambda k: int(k[1:])):
            data += struct.pack("<I", hi_fields[k])
    data += b"\0\0\0\0"
    return bytes(data), rel, strs


def fake_tables():
    data, rel, strs = _rows([(["JID_X"], {"H2": 0x111111}),
                             (["AID_A"], {"H1": 0, "H2": 0xAA0000, "H3": 0xF0D0C0}),
                             (["AID_A", "JID_Y"], {}),
                             (["AID_B"], {"H2": 0x00BB00}),
                             (["AID_C"], {"H2": 0x0000CC})])
    hdr, rows = C.parse_asset(data, rel, lambda o: strs[o])
    assets = {"asset/ROM3.lz": {"header": hdr, "rows": rows}}
    persons = [{"pid": f"PID_{n}", "aid": f"AID_{n}", "fid": f"FID_{n}", "flags": "", "index": str(i + 1),
                "belong": "BID_P", "job": "JID_X", "job_low": "JID_X", "family_index": "0"}
               for i, n in enumerate("ABC")]
    faces = []
    for i, n in enumerate("ABC"):
        for k, kind in enumerate(("ST", "BU")):
            j = 2 * i + k
            faces.append({"index": j, "fsid": f"FSID_{kind}_{n}", "package": f"{n}_{kind.lower()}", "hair": "",
                          "color": 0xFF000000 | (0x10 * (i + 1)), "off": 4 + j * C.FACE_REC})
    heads = {n: [f"unit/Head/{n}/青0.bch.lz", f"unit/Head/{n}/赤0.bch.lz"] for n in "ABC"}
    copies = [{"file": "GameData/Person/B010.bin.lz", "chapter": "B010", "pid": "PID_C_boss", "aid": "AID_C",
               "belong": "BID_E", "replace_index": "0"}]
    return C.ColourTables("fates", persons, copies, assets, faces, heads, RULES, arcs={"A_ct"},
                          route_of={"PID_A": {"A"}, "PID_B": {"A"}, "PID_C": {"A"}},
                          in_scope=lambda p: True)


class AssetFormat(unittest.TestCase):
    def test_rows_and_fields(self):
        t = fake_tables()
        rows = t.assets["asset/ROM3.lz"]["rows"]
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[1]["fields"][0][2], "AID_A")
        self.assertEqual(C.row_get(rows[1], "H2")[1], 0xAA0000)
        self.assertEqual(C.row_get(rows[1], "H3")[1], 0xF0D0C0)
        self.assertEqual(C.row_conds(rows[2]), ["AID_A", "JID_Y"])

    def test_person_facts(self):
        t = fake_tables()
        self.assertEqual(t.hair_of("AID_A"), 0xAA0000)
        self.assertEqual(t.skin_of("AID_A"), 0xF0D0C0)
        self.assertEqual(t.own_outfit_classes("AID_A"), {"JID_Y"})
        self.assertIsNone(t.hair_of("AID_Z"))

    def test_face_colour_bytes(self):
        self.assertEqual(C.face_to_rgb(0xFFC3D2D2), 0xD2D2C3)          # FaceData Jakob == his model hair
        self.assertEqual(C.rgb_to_face(0xD2D2C3, 0xFF000000), 0xFFC3D2D2)


class Plan(unittest.TestCase):
    def setUp(self):
        self.t = fake_tables()
        self.plan = {"look": "keep", "swaps": [["PID_A", "PID_B"], ["PID_B", "PID_A"], ["PID_C", "PID_A"]],
                     "classes": {"PID_A": ["JID_X", "JID_Y", "JID_Z"], "PID_B": ["JID_X"]}}

    def test_swap_recolours_from_originals(self):
        e, lines = C.plan_colours(self.t, self.plan, {"boss_copies": "follow"})
        hair = {x["spot"]: x["new"] for x in e if x["table"] == "AssetTable"}
        self.assertEqual(hair, {"PID_A": 0x00BB00, "PID_B": 0xAA0000, "PID_C": 0xAA0000})   # no chains
        kinds = {(x["table"], x.get("what")) for x in e if x["spot"] == "PID_A"}
        self.assertEqual(kinds, {("AssetTable", None), ("FaceData", None), ("Picture", "portrait"),
                                 ("Picture", "map_head")})
        self.assertIn("face/face/A_ct.arc", [x["file"] for x in e if x["table"] == "Picture"])
        g = C.run_guards(self.t, e, self.plan, {"boss_copies": "follow"})
        self.assertTrue(all(v["ok"] for v in g.values()), g)
        self.assertTrue(any("hair #AA0000 -> #00BB00" in ln for ln in lines))

    def test_boss_copy_rule(self):
        e, lines = C.plan_colours(self.t, self.plan)                     # default: skip (Grok's rule 3)
        self.assertFalse([x for x in e if x["spot"] == "PID_C"])
        self.assertTrue(any("boss in B010" in ln for ln in lines))
        g = C.run_guards(self.t, e, self.plan)
        self.assertTrue(all(v["ok"] for v in g.values()), g)

    def test_off_and_full_look_change_nothing(self):
        self.assertEqual(C.plan_colours(self.t, self.plan, {"recolour": "off", "own_colours": "off"}), ([], []))
        e, lines = C.plan_colours(self.t, dict(self.plan, look="full"), {"own_colours": "off"})
        self.assertEqual(e, [])
        self.assertIn("full identity", lines[0])
        self.assertEqual(C.plan_colours(self.t, {"look": "keep", "swaps": [], "classes": {}}), ([], []))

    def test_own_colours_lines_only(self):
        e, lines = C.plan_colours(self.t, dict(self.plan, swaps=[]))
        self.assertEqual(e, [])
        self.assertTrue(any(ln.strip().startswith("A: Z") for ln in lines), lines)   # Y is A's own outfit

    def test_guards_catch_bad_cells(self):
        e, _ = C.plan_colours(self.t, self.plan, {"boss_copies": "follow"})
        bad = [dict(x) for x in e]
        for x in bad:
            if x["table"] == "AssetTable":
                x["old"] ^= 1
                break
        g = C.run_guards(self.t, bad, self.plan, {"boss_copies": "follow"})
        self.assertFalse(g["colour: originals"]["ok"])
        g = C.run_guards(self.t, e, dict(self.plan, swaps=[]), {"boss_copies": "follow"})
        self.assertFalse(g["colour: only swapped spots"]["ok"])

    def test_patch_lines(self):
        e, _ = C.plan_colours(self.t, self.plan, {"boss_copies": "follow"})
        lines = C.patch_lines(e)
        self.assertEqual(lines[0], "file asset asset/ROM3.lz 0FA01111")
        self.assertTrue(lines[1].startswith("v "))
        v = lines[1].split()
        self.assertEqual(len(bytes.fromhex(v[2])), 4)
        self.assertIn("file face face/FaceData.bin.lz 6", lines)
        self.assertTrue(any(ln.startswith("tint AA0000 00BB00 unit/Head/A/") for ln in lines))

    def test_determinism(self):
        self.assertEqual(C.plan_colours(self.t, self.plan), C.plan_colours(self.t, self.plan))


class Recolour(unittest.TestCase):
    def test_vectors(self):
        red, light = 0xAF5454, 0xDCD9D3
        self.assertEqual(C.recolour_rgb((0xAF, 0x54, 0x54), red, light), (0xDC, 0xD9, 0xD3))   # the hair colour
        dark = C.recolour_rgb((0x58, 0x2A, 0x2A), red, light)                                   # shaded hair
        self.assertTrue(abs(dark[0] - dark[2]) < 12, dark)                                      # now greyish
        self.assertEqual(C.recolour_rgb((0xF0, 0xC8, 0xA8), red, light), (0xF0, 0xC8, 0xA8))   # skin kept
        self.assertEqual(C.recolour_rgb((0x30, 0x40, 0xC0), red, light), (0x30, 0x40, 0xC0))   # blue kept
        silver, green = 0xAAB4B4, 0x7D9682
        self.assertNotEqual(C.recolour_rgb((0xAA, 0xB4, 0xB4), silver, green), (0xAA, 0xB4, 0xB4))
        self.assertEqual(C.recolour_rgb((0xE8, 0xB8, 0x98), silver, green), (0xE8, 0xB8, 0x98))  # skin kept

    def test_rgba_keeps_alpha_and_transparent(self):
        buf = bytes([0xAF, 0x54, 0x54, 0x80, 0xAF, 0x54, 0x54, 0x00])
        out = C.recolour_rgba(buf, 0xAF5454, 0x00BB00)
        self.assertEqual(out[3], 0x80)
        self.assertEqual(out[4:], buf[4:])


@unittest.skipUnless(os.path.isfile(os.path.join(ROOT, "extracted", "romfs", "asset", "ROM3.lz")),
                     "no extracted RomFS")
class RealTables(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = C.load_tables("fates")

    def test_tables(self):
        r = C.facts_report(self.t)
        self.assertEqual(r["asset_files"]["asset/ROM3.lz"]["header"], "0FA01111")
        self.assertEqual(r["facedata_records"], 452)
        # every portrait colour of a person with a model-table hair row is that hair colour (one fact, two files)
        same = diff = 0
        for p in self.t.persons:
            h = self.t.hair_of(p["aid"]) if p.get("aid") else None
            f = self.t.face_by_fsid.get("FSID_ST_" + self.t.short(p.get("fid", "")))
            if h is not None and f is not None:
                same += C.face_to_rgb(f["color"]) == h
                diff += C.face_to_rgb(f["color"]) != h
        self.assertGreater(same, 40)
        self.assertGreater(same, 2 * diff)        # most agree; the rest differ (portrait vs model lighting)

    def test_seeds(self):
        for i in range(5):
            plan = C._recruit_plan(self.t, f"ut{i}", "route", "fates")
            e, _ = C.plan_colours(self.t, plan)
            g = C.run_guards(self.t, e, plan)
            self.assertTrue(all(v["ok"] for v in g.values()), (i, g))
            self.assertTrue(e)


if __name__ == "__main__":
    unittest.main()
