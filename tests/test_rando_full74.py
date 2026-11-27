"""Round 74, track py: the full swap's Python half (docs/rando/FULL_BLOCK.md, docs/ROUND74_PLAN.md A1, A2, A3, A5, A7).

    python -m unittest tests.test_rando_full74          (from the repo root)

Made-up tables, made-up IS .bin files, made-up message archives and made-up face packages only (no game bytes or
text): the robot's test-only switch and the owner's page row (A7), label-pointer cells in person files (A3 Python
half), FaceData cells (A1), chapter copies (A1), R9 (a)(b)(c) (A2), the full block (A5). One real-data class (skipped
without the user's RomFS) makes one full-look seed under the switch and lays its patch on memory images.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
sys.path.insert(0, os.path.join(ROOT, "tools", "mods"))
sys.path.insert(0, os.path.join(ROOT, "tools", "assets"))
import ingame as IG  # noqa: E402
import recruit as RC  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _edition as E  # noqa: E402  (round 84: Seal legs run only in the Seal edition)

CLI = os.path.join(ROOT, "tools", "randomizer", "rando.py")
GD_BASE, FILE_BASE = 0x30000000, 0x38000000


def have_tables() -> bool:
    try:
        import gamedata as G
        return G.available() is None
    except Exception:  # noqa: BLE001
        return False


@contextlib.contextmanager
def env(value):
    old = os.environ.get(IG.TEST_ENV)
    try:
        if value is None:
            os.environ.pop(IG.TEST_ENV, None)
        else:
            os.environ[IG.TEST_ENV] = value
        yield
    finally:
        if old is None:
            os.environ.pop(IG.TEST_ENV, None)
        else:
            os.environ[IG.TEST_ENV] = old


def build_tmp():
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    return tempfile.TemporaryDirectory(dir=os.path.join(ROOT, "build"))


def write_switch(folder: str, text: str):
    os.makedirs(os.path.join(folder, "rando"), exist_ok=True)
    with open(os.path.join(folder, "rando", "test-switches.json"), "w", encoding="utf-8") as fh:
        fh.write(text)


# ------------------------------------------------------------------ made-up IS .bin files
def isbin(data: bytes, ptrs: dict[int, bytes | None], extra_pool=()) -> bytes:
    """An IS .bin with `data`, a relocated pointer at each slot of ptrs (to its label in the pool; None = null, no
    relocation), extra unreferenced pool strings, no exported labels. Padded so it never looks like an LZ stream."""
    import isbin as IB
    names = []
    for lab in [v for v in ptrs.values() if v is not None] + list(extra_pool):
        if lab not in names:
            names.append(lab)
    relocs = sorted(s for s, v in ptrs.items() if v is not None)
    for pad in range(8):
        pool = bytearray()
        at = {}
        for n in names:
            at[n] = len(pool)
            pool += n + b"\0"
        pool += bytes(pad)
        se = len(data) + 4 * len(relocs)
        d = bytearray(data)
        for s, v in ptrs.items():
            struct.pack_into("<I", d, s, 0 if v is None else se + at[v])
        b = IB.IsBin()
        b.data, b.relocs, b.labels, b.strtab = bytes(d), relocs, [], bytes(pool)
        raw = b.build()
        if raw[0] not in (0x10, 0x11, 0x13):
            return raw
    raise AssertionError("could not pad the made-up file")


def container(rel: str, raw: bytes):
    return IG._T().Container(rel, raw)


# ------------------------------------------------------------------ A7: the robot's test-only switch
class TestSwitch(unittest.TestCase):
    def test_switch_only_inside_build_and_well_formed(self):
        with build_tmp() as d:
            with env(None):
                self.assertEqual(IG.test_switches(), {})
            with env(d):                                   # no file
                self.assertEqual(IG.test_switches(), {})
            write_switch(d, "{not json")
            err = io.StringIO()
            with env(d), contextlib.redirect_stderr(err):
                self.assertEqual(IG.test_switches(), {})
            self.assertIn("ignored", err.getvalue())
            write_switch(d, json.dumps({"format": 2, "recruit_look": "full"}))
            with env(d), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(IG.test_switches(), {})
            write_switch(d, json.dumps({"format": 1, "recruit_look": "full"}))
            with env(d):
                self.assertEqual(IG.test_switches().get("recruit_look"), "full")
                self.assertTrue(IG.full_look_allowed())
            with env(os.path.join(d, "..", os.path.basename(d))):   # the same folder through '..': resolved
                self.assertEqual(IG.test_switches().get("recruit_look"), "full")
        with tempfile.TemporaryDirectory() as outside:          # the system temp folder: never under build/
            write_switch(outside, json.dumps({"format": 1, "recruit_look": "full"}))
            with env(outside):
                self.assertEqual(IG.test_switches(), {})
        with env(None):                                         # round 76 (F-062): the owner's page offers full
            self.assertTrue(IG.full_look_allowed())
        with env(os.path.join(ROOT, "build")):                  # build/ itself does not count: a folder inside it
            self.assertEqual(IG.test_switches(), {})

    def test_owner_page_offers_the_look_row(self):
        """Round 76 (F-062): without a qualifying switch the schema is byte-identical, and "How they look" is offered
        (keep / full, default and "all" keep; grey on Seal) and make_args passes full; with the switch the robot sees
        the round-74 labels, the Seal grey lifted, and the same answer gives the same run id and make flags."""
        with env(None):
            base = json.dumps(IG.schema(), ensure_ascii=False, sort_keys=True)
        row = next(r for r in json.loads(base)["rows"] if r["key"] == "recruit_look")
        self.assertNotIn("fixed", row)
        self.assertEqual((row["default"], row["all"], row["choices"]), ("keep", "keep", ["keep", "full"]))
        with self.subTest(game="seal"):
            E.need_seal(self)
            self.assertIn("seal", row["grey_for"])
        with tempfile.TemporaryDirectory() as outside, build_tmp() as d:
            write_switch(outside, json.dumps({"format": 1, "recruit_look": "full"}))
            write_switch(d, json.dumps({"format": 1, "recruit_look": "keep"}))
            for v in (outside, d, os.path.join(d, "missing")):
                with env(v):
                    self.assertEqual(json.dumps(IG.schema(), ensure_ascii=False, sort_keys=True), base, v)
                    self.assertIn("--recruit-look", IG.make_args({"seed": "s", "recruit": "route",
                                                                   "recruit_look": "full"}))
                    a = IG.make_args({"seed": "s", "recruit": "route", "recruit_look": "full"})
                    self.assertEqual(a[a.index("--recruit-look") + 1], "full", "the offered row passes its value")
            write_switch(d, json.dumps({"format": 1, "recruit_look": "full"}))
            with env(d):
                rows = IG.schema()["rows"]
                row = next(r for r in rows if r["key"] == "recruit_look")
                self.assertNotIn("fixed", row)
                self.assertNotIn("grey_for", row)
                self.assertEqual(row["choices"], ["keep", "full"])
                self.assertEqual(row["choice_labels"], {"keep": "Keep the face", "full": "Full swap (robot test)"})
                self.assertEqual((row["default"], row["all"]), ("keep", "keep"))
                vals, _turned = IG.page_everything(rows, {"seed": "x"})
                self.assertEqual(vals["recruit_look"], "keep", "Randomize everything never picks the full swap")
                a = IG.make_args({"seed": "s", "recruit": "route", "recruit_look": "full"})
                self.assertEqual(a[a.index("--recruit-look") + 1], "full")
                ans = IG.page_answers(rows, dict(IG.page_restore(rows, {}), randomizer=True, seed="s",
                                                 recruit="route", recruit_look="full"))
                self.assertEqual(ans["recruit_look"], "full")
                keep = dict(ans, recruit_look="keep")
                self.assertNotEqual(IG.run_id(ans), IG.run_id(keep), "a full run never shares a keep run's id")
                a7_args = IG.make_args(ans)
            with env(None):                 # round 76: the owner's page gives the same answer, run id and flags
                rows0 = IG.schema()["rows"]
                ans0 = IG.page_answers(rows0, dict(IG.page_restore(rows0, {}), randomizer=True, seed="s",
                                                   recruit="route", recruit_look="full"))
                self.assertEqual(IG.answer_text(ans0), IG.answer_text(ans))
                self.assertEqual(IG.run_id(ans0), IG.run_id(ans))
                self.assertEqual(IG.make_args(ans0), a7_args)


# ------------------------------------------------------------------ A3 Python half: person files
PERSON = "GameData/Person/X001.bin"


class PersonPointers(unittest.TestCase):
    def files(self):
        data = bytes(0x40)
        o = isbin(data, {0x10: b"AID_AA", 0x14: b"MPID_AA", 0x18: b"MPID_H_AA"}, extra_pool=[b"MPID_CC"])
        nd = bytearray(data)
        nd[0x20] = 5
        n = isbin(bytes(nd), {0x10: b"AID_BB", 0x14: b"MPID_CC", 0x18: b"MPID_H_Z"})
        return o, n

    def test_off_is_todays_path(self):
        o, n = self.files()
        ents = IG.file_entries(PERSON, n, {b"AID_BB": 0x1234}, orig=container(PERSON, o))
        self.assertEqual([e[0] for e in ents].count("p"), 0, "keep runs: renames in place only")
        self.assertEqual(ents, IG.file_entries(PERSON, n, {b"AID_BB": 0x1234}, person_ptrs=False,
                                               orig=container(PERSON, o)))

    def test_full_lays_pointers_g_then_s(self):
        o, n = self.files()
        oc = container(PERSON, o)
        ents = IG.file_entries(PERSON, n, {b"AID_BB": 0x1234}, person_ptrs=True, orig=oc)
        ps = {e[1]: e for e in ents if e[0] == "p"}
        self.assertEqual(sorted(ps), [0x10, 0x14])
        self.assertEqual(ps[0x10][2:6], (b"AID_AA", b"AID_BB", "g", 0x1234))
        self.assertEqual(ps[0x14][2:5], (b"MPID_AA", b"MPID_CC", "s"))
        self.assertEqual(ps[0x14][5], IG._pool_index(oc)[b"MPID_CC"])
        self.assertEqual(ps[0x10][6], oc.u32(0x10), "the old pointer's file value")
        vs = [e for e in ents if e[0] == "v"]
        self.assertIn(("v", 0x20, b"\0", b"\x05"), vs)
        self.assertTrue(any(e[1] >= oc.se and e[3].startswith(b"MPID_H_Z\0") for e in vs),
                        "a label in neither pool keeps the rename in place")
        # laid on a memory image (gd label at GD_BASE + 0x1234) and reverted
        gd = bytearray(0x2000)
        gd[0x1234:0x123B] = b"AID_BB\0"
        img = IG.memory_image(oc, FILE_BASE)
        before = bytes(img)
        f = IG.parse_patch("fates-rando-patch 1\nseed s\nfile person " + PERSON + "\n"
                           + "\n".join(IG._entry_line(e) for e in ents) + f"\nend {len(ents)}\n")["files"][0]
        images = {GD_BASE: gd, FILE_BASE: img}
        self.assertEqual(IG.apply_image(f, img, FILE_BASE, images, GD_BASE), [])
        rd = (lambda s: IG.read_cstr(images, struct.unpack_from("<I", img, s)[0]))
        self.assertEqual((rd(0x10), rd(0x14), rd(0x18)), (b"AID_BB", b"MPID_CC", b"MPID_H_Z"))
        self.assertEqual(IG.apply_image(f, img, FILE_BASE, images, GD_BASE, revert=True), [])
        self.assertEqual(bytes(img), before)

    def test_map_settings_still_refuse_pointers(self):
        rel = "map/config/X001.bin"
        o = isbin(bytes(0x20), {0x10: b"STRM_AAAA"})
        n = isbin(bytes(0x20), {0x10: b"STRM_BB"})
        ents = IG.file_entries(rel, n, {b"STRM_BB": 0x40}, person_ptrs=True, orig=container(rel, o))
        self.assertEqual([e[0] for e in ents], ["v"], "a rename in place, never a pointer")
        n2 = isbin(bytes(0x20), {0x10: b"STRM_LONGER_NAME"})
        with self.assertRaises(IG.PatchError):
            IG.file_entries(rel, n2, {b"STRM_LONGER_NAME": 0x40}, person_ptrs=True, orig=container(rel, o))


# ------------------------------------------------------------------ A1: FaceData cells
def facedata(bad_pointer: bool = False) -> bytes:
    recs = [("ST", "AA", "aa_st", b"hairA", 0x11223344, (b"smile", b"pain"), 1),
            ("BU", "AA", "aa_bu", b"hairA", 0x11223344, (b"smile", b"pain"), 2),
            ("ST", "BB", "bb_st", None, 0x55667788, (b"smile", b"angry"), 3),
            ("BU", "BB", "bb_bu", None, 0x55667788, (b"smile", b"angry"), 4)]
    data = bytearray(4 + len(recs) * IG.FACE_REC)
    struct.pack_into("<I", data, 0, len(recs))
    ptrs = {}
    for i, (kind, who, pkg, hair, col, ex, lay) in enumerate(recs):
        o = 4 + i * IG.FACE_REC
        ptrs.update({o: f"FSID_{kind}_{who}".encode(), o + 4: f"MPID_{who}".encode(), o + 8: f"{who}KEY".encode(),
                     o + 0x0C: pkg.encode(), o + 0x10: None, o + 0x14: hair, o + 0x18: None,
                     o + 0x20: ex[0], o + 0x24: ex[1]})
        struct.pack_into("<I", data, o + 0x1C, col)
        struct.pack_into("<16H", data, o + 0x28, *([100] * 16))
        struct.pack_into("<H", data, o + 0x30, 100 + lay)      # two layout numbers differ between people
        struct.pack_into("<H", data, o + 0x3A, 50 * lay)
    raw = bytearray(isbin(bytes(data), ptrs))
    if bad_pointer:      # BB's ST package pointer points into the data region, not the pool
        struct.pack_into("<I", raw, 0x20 + 4 + 2 * IG.FACE_REC + 0x0C, 0x30)
    return bytes(raw)


class FaceCells(unittest.TestCase):
    def test_cells_only_differing_fields_never_fsid_or_voice(self):
        c = container(IG.FACE_REL, facedata())
        recs = IG.face_records(c)
        pairs = IG.face_pairs(recs, {"FID_AA": "FID_BB", "FID_BB": "FID_AA", "FID_ZZ": "FID_AA"})
        self.assertEqual(pairs, [(0, 2), (1, 3), (2, 0), (3, 1)], "kinds matched; no record for ZZ")
        ents = IG.face_entries(c, pairs)
        a0 = [e for e in ents if 4 <= e[1] < 4 + IG.FACE_REC]
        self.assertEqual(sorted((e[0], e[1] - 4) for e in a0),
                         [("p", 0x04), ("p", 0x0C), ("p", 0x14), ("p", 0x24), ("v", 0x1C), ("v", 0x30)])
        for e in ents:
            self.assertNotIn((e[1] - 4) % IG.FACE_REC, (0x00, 0x08), "FSID and voice key never written")
            if e[0] == "p":
                self.assertIn(e[4], ("s", "-"))
        hair = next(e for e in a0 if e[1] - 4 == 0x14)
        self.assertEqual(hair[3:6], (None, "-", None), "B has no hair dir: null")
        lay = next(e for e in a0 if e[1] - 4 == 0x30)
        self.assertEqual(len(lay[2]), 0x3A - 0x30 + 1, "one run from the first to the last differing byte")

    def test_laid_on_memory_a_shows_b_and_reverts(self):
        c = container(IG.FACE_REL, facedata())
        recs = IG.face_records(c)
        ents = IG.face_entries(c, IG.face_pairs(recs, {"FID_AA": "FID_BB", "FID_BB": "FID_AA"}))
        text = (f"fates-rando-patch 1\nseed s\nfile face {IG.FACE_REL} {len(recs)}\n"
                + "\n".join(IG._entry_line(e) for e in ents) + f"\nend {len(ents)}\n")
        f = IG.parse_patch(text)["files"][0]
        img = IG.memory_image(c, FILE_BASE)
        before = bytes(img)
        images = {FILE_BASE: img}
        self.assertEqual(IG.apply_image(f, img, FILE_BASE, images, 0), [])
        rd = (lambda off: (lambda v: None if v == 0 else IG.read_cstr(images, v))(struct.unpack_from("<I", img, off)[0]))
        for a, b in ((0, 2), (1, 3), (2, 0), (3, 1)):
            oa, ob = 4 + a * IG.FACE_REC, 4 + b * IG.FACE_REC
            self.assertEqual(rd(oa), recs[a]["fsid"], "the FSID stays")
            self.assertEqual(rd(oa + 8), recs[a]["key"], "the voice key stays")
            for fo in IG.FACE_PTRS:
                self.assertEqual(rd(oa + fo), recs[b]["ptr"][fo][0], (a, fo))
            self.assertEqual(img[oa + 0x1C:oa + 0x20], c.data[ob + 0x1C:ob + 0x20])
            self.assertEqual(img[oa + 0x28:oa + 0x48], c.data[ob + 0x28:ob + 0x48])
        self.assertEqual(IG.apply_image(f, img, FILE_BASE, images, 0, revert=True), [])
        self.assertEqual(bytes(img), before)

    def test_a_label_outside_the_pool_is_refused(self):
        c = container(IG.FACE_REL, facedata(bad_pointer=True))
        with self.assertRaises(IG.PatchError):
            IG.face_entries(c, IG.face_pairs(IG.face_records(c), {"FID_AA": "FID_BB"}))
        with self.assertRaises(IG.PatchError):
            IG.face_entries(c, [(0, 2), (0, 3)])


# ------------------------------------------------------------------ A1 copies, A2 R9, A5 full block (made-up tables)
def stub_tables(faces=True, packages=None, copies=(), scenes=None, names=None):
    persons = [{"index": str(i), "label": f"PID_{w}", "fid": f"FID_{w}", "aid": f"AID_{w}", "mpid_name": f"MPID_{w}",
                "mpid_help": f"MPID_H_{w}"} for i, w in enumerate(("AA", "BB", "CC"), 1)]
    facts = types.SimpleNamespace(rules={}, persons=persons, by_pid={p["label"]: p for p in persons})
    recs = []
    if faces:
        for w in ("AA", "BB", "CC"):
            for k in ("ST", "BU"):
                recs.append({"fsid": f"FSID_{k}_{w}", "key": f"{w}KEY", "package": f"{w.lower()}_{k.lower()}"})
    pk = packages if packages is not None else {
        "aa_st": {"通常", "smile", "shock"}, "aa_bu": {"通常", "smile", "shock"},
        "bb_st": {"通常", "smile"}, "bb_bu": {"通常", "smile"}, "cc_st": {"通常"}, "cc_bu": {"通常"}}
    return RC.RecruitTables(facts, [], None, copies=list(copies), faces=recs if faces else None,
                            packages=lambda p: pk.get(p), scenes=scenes, names=names)


class FullPython(unittest.TestCase):
    def test_chapter_copies_and_their_cells(self):
        copies = [{"file": "GameData/Person/A/A003.bin.lz", "index": "2", "label": "PID_A003_AA", "fid": "FID_AA",
                   "aid": "AID_AA", "mpid_name": "MPID_AA", "mpid_help": "MPID_H_OWN"},
                  {"file": "GameData/Person/A_HANDOVER.bin.lz", "index": "0", "label": "PID_A_AA", "fid": "FID_AA",
                   "aid": "AID_AA", "mpid_name": "MPID_AA", "mpid_help": "MPID_H_AA"},
                  {"file": "GameData/Person/A/A004.bin.lz", "index": "0", "label": "PID_AA", "fid": "FID_AA"},
                  {"file": "GameData/Person/A/A004.bin.lz", "index": "1", "label": "PID_X", "fid": "FID_XX"}]
        t = stub_tables(copies=copies)
        got = t.chapter_copies("PID_AA")
        self.assertEqual([r["label"] for r in got], ["PID_A003_AA"], "HANDOVER, the main label and others left out")
        e = RC.copy_edits(got, t.facts.by_pid["PID_AA"], t.facts.by_pid["PID_BB"], RC.COPY_CELLS,
                          "PID_AA", "PID_BB")
        self.assertEqual([(x["cell"], x["old"], x["new"]) for x in e],
                         [("aid", "AID_AA", "AID_BB"), ("mpid_name", "MPID_AA", "MPID_BB")],
                         "a help text of the copy's own stays")
        self.assertTrue(all(x["copy"] and x["laid_by"] == "person_hook" and x["look"] == "full" for x in e))
        self.assertEqual(stub_tables().chapter_copies("PID_AA"), [])

    def test_r9_normal_face_and_records(self):
        mp = {"PID_AA": "PID_BB", "PID_BB": "PID_AA", "PID_CC": "PID_CC"}
        bad, info = RC.r9_faces(stub_tables(), mp)
        self.assertEqual(bad, [])
        no_normal = {"aa_st": {"smile"}, "aa_bu": {"通常"}, "bb_st": {"通常"}, "bb_bu": {"通常"}}
        bad, _ = RC.r9_faces(stub_tables(packages=no_normal), mp)
        self.assertEqual(len(bad), 1)
        self.assertIn("no normal face", bad[0])
        self.assertIn("PID_AA", bad[0])
        bad, _ = RC.r9_faces(stub_tables(packages={}), mp)
        self.assertEqual(len(bad), 4, "four packages not found")
        t = stub_tables()
        t.given("faces")[:] = [r for r in t.given("faces") if r["fsid"] != "FSID_BU_BB"]
        t._cache.pop("faces_by", None)
        bad, _ = RC.r9_faces(t, mp)
        self.assertEqual(bad, ["PID_BB: no FSID_BU face record (filling PID_AA)"])
        t = stub_tables()                  # a generic face (no record of AA's own): nothing to fill, only counted
        t.given("faces")[:] = [r for r in t.given("faces") if not r["fsid"].endswith("_AA")]
        t._cache.pop("faces_by", None)
        bad, info = RC.r9_faces(t, {"PID_AA": "PID_BB"})
        self.assertEqual(bad, [])
        self.assertIn("no face record of their own", info[0])
        bad, info = RC.r9_faces(stub_tables(faces=False), mp)
        self.assertEqual(bad, [])
        self.assertIn("not checked", info[0])
        t = stub_tables()
        t.facts.by_pid["PID_BB"]["fid"] = ""
        self.assertEqual(RC.r9_faces(t, mp)[0], ["PID_BB has no face id"])

    def test_r9c_missing_scene_faces(self):
        scenes = {"AA": {"shock": "X001 MID_1", "smile": "X001 MID_0", "wink": "X002 MID_3"},
                  "BB": {"smile": "X003 MID_1"}}
        t = stub_tables(scenes=scenes)
        got = RC.missing_faces(t, {"PID_AA": "PID_BB", "PID_BB": "PID_AA"})
        self.assertEqual(got, [("PID_AA", "PID_BB", [("shock", "X001 MID_1")]), ("PID_BB", "PID_AA", [])],
                         "only faces A has and B lacks (wink: A lacks it too)")

    def test_scene_faces_reads_speaker_and_expression(self):
        import msg
        arc = msg.build_bytes(b"MESS_ARCHIVE_X001", [(b"MID_1", "$Wmaa|$w0|$Wsaa|$Wa$SvpVOICE_AA_EVT_1|$Eshock,|Hi.$k$Wsbb|$E"
                                                "smile,|Yo.$k$Wsaa|$Eshock,|Again.", False),
                                        (b"MID_2", "$Wsbb|$Eangry,|Hm.", False)])
        got = RC.scene_faces([("A/X001", arc), ("bad", b"nope")])
        self.assertEqual(got, {"aa": {"shock": "A/X001 MID_1"}, "bb": {"smile": "A/X001 MID_1",
                                                                        "angry": "A/X001 MID_2"}})

    def test_full_text_format_order_and_dedupe(self):
        names = {"E": {"MPID_AA": "Al", "MPID_BB": "Bertha", "MPID_CC": "Cy", "MPID_DD": "Cy"}}
        pairs = [("MPID_AA", "MPID_BB"), ("MPID_BB", "MPID_AA"), ("MPID_CC", "MPID_DD"), ("MPID_ZZ", "MPID_AA")]
        text = RC.full_text("demo-7", "fates", pairs, names, ["BBKEY", "AAKEY", "AAKEY", ""], ["C013", "C008"])
        ln = text.splitlines()
        self.assertEqual(ln[:3], ["fates-rando-full 1", "seed demo-7", "game fates"])
        u = (lambda s: s.encode("utf-16-le").hex())
        self.assertEqual(ln[3:5], [f"n E {u('Bertha')} {u('Al')}", f"n E {u('Al')} {u('Bertha')}"],
                         "longest old name first; old == new (Cy) and unknown labels never written")
        self.assertEqual(ln[5:7], [f"s {b'AAKEY'.hex()}", f"s {b'BBKEY'.hex()}"])
        self.assertEqual(ln[7:], ["off C008", "off C013", "end 6"])
        p = RC.parse_full(text)
        self.assertEqual(p["names"], [("E", "Bertha", "Al"), ("E", "Al", "Bertha")])
        self.assertEqual((p["silence"], p["off"], p["count"]), (["AAKEY", "BBKEY"], ["C008", "C013"], 6))
        clash = RC.full_text("s", "seal", [("MPID_AA", "MPID_BB"), ("MPID_EE", "MPID_CC")],
                             {"E": {"MPID_AA": "Al", "MPID_EE": "Al", "MPID_BB": "Bo", "MPID_CC": "Cy"}}, [], [])
        self.assertEqual(clash.splitlines()[3:], ["end 0"], "an old name with two new ones is left out")
        for bad in ("", "fates-rando-full 2\nend 0\n", text.replace("end 6", "end 5"), text.replace("end 6\n", ""),
                    text.replace("seed demo-7", "x y")):
            with self.assertRaises(ValueError):
                RC.parse_full(bad)

    def test_full_block_from_tables(self):
        names = {"E": {"MPID_AA": "Al", "MPID_BB": "Bo", "MPID_CC": "Cy"}}
        t = stub_tables(names=names)
        t.rules["full_off_chapters"] = ["B009"]
        text = RC.full_block(t, {"PID_AA": "PID_BB", "PID_BB": "PID_AA", "PID_CC": "PID_CC"}, "s1", "fates")
        p = RC.parse_full(text)
        self.assertEqual(sorted(p["names"]), [("E", "Al", "Bo"), ("E", "Bo", "Al")])
        self.assertEqual(p["silence"], ["AAKEY", "BBKEY"], "the spot's voice key; CC stays and keeps its voice")
        self.assertEqual(p["off"], ["B009"])
        self.assertEqual(text, RC.full_block(t, {"PID_BB": "PID_AA", "PID_AA": "PID_BB"}, "s1", "fates"))
        self.assertEqual(RC.parse_full(RC.full_block(stub_tables(), {}, "s1"))["count"], 0)


# ------------------------------------------------------------------ one real full-look make under the switch
# round 75 (b): spoiler wording that said the full swap's portraits and dialogue names were still to come
STALE_SPOILER = ("E3/E4", "need engine rounds", "for the later engine rounds", "until then the spot's portrait shows")


class StaleSpoilerSource(unittest.TestCase):
    """round 75 (b), host only: the spoiler and page wording no longer say the full swap waits for engine rounds."""

    def test_no_stale_full_swap_wording(self):
        with open(os.path.join(ROOT, "tools", "randomizer", "tracks.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("need engine rounds E3/E4", src)
        self.assertNotIn("until then the spot's portrait shows", src)
        self.assertIn('"(laid by the full swap below)"', src)
        self.assertNotIn("for the later engine rounds (plan.json only)", src)     # round 75b
        with open(os.path.join(ROOT, "tools", "randomizer", "rando.py"), encoding="utf-8") as fh:
            self.assertNotIn("E3/E4", fh.read())
        with env(None):
            row = next(r for r in IG.schema()["rows"] if r["key"] == "recruit_look")
        self.assertNotIn("fixed", row)                      # round 76 (F-062): offered; rule 5 holds no chapter now
        self.assertNotIn("engine round", row["label"])
        for chapter in ("Revelation 13", "Conquest 9"):
            self.assertNotIn(chapter, row["label"] + row["help"])
        self.assertNotIn("recruit_look", [k for k in IG.NOT_IN_EVERYTHING if k != "recruit_look"])
        self.assertIn("recruit_look", IG.NOT_IN_EVERYTHING)


@unittest.skipUnless(have_tables(), "the user's extracted RomFS is not available")
class RealFullMake(unittest.TestCase):
    """rando.py make --recruit route --recruit-look full --patch-out under the robot's switch: the patch's person files
    carry label pointers, laid on memory images they equal the mods tool's rebuilt files (labels as text), revert =
    original; the face section makes every swapped spot's records show the filler's; full.txt parses with this seed
    and game; a keep make into the same folder removes the stale full.txt; without the switch the make is refused
    (tests.test_rando_ingame covers that)."""

    def test_full_make_under_the_switch(self):
        T = IG._T()
        with build_tmp() as d:
            data = os.path.join(d, "robot-data")
            write_switch(data, json.dumps({"format": 1, "recruit_look": "full"}))
            e = dict(os.environ, **{IG.TEST_ENV: data, "PYTHONIOENCODING": "utf-8"})
            patch = os.path.join(d, "out", "patch.txt")
            run = (lambda look: subprocess.run(
                [sys.executable, CLI, "make", "--seed", "r74full", "--recruit", "route", "--recruit-look", look,
                 "--out", os.path.join(d, "mods-" + look), "--patch-out", patch],
                capture_output=True, text=True, timeout=900, cwd=ROOT, env=e, encoding="utf-8", errors="replace"))
            r = run("full")
            self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
            with open(patch, encoding="ascii") as fh:
                text = fh.read()
            with open(os.path.join(os.path.dirname(patch), "full.txt"), encoding="ascii") as fh:
                full = RC.parse_full(fh.read())
            self.assertEqual((full["seed"], full["game"]), ("r74full", "fates"))
            self.assertTrue(full["names"] and full["silence"])
            self.assertEqual({lang for lang, _o, _n in full["names"]}, {"E"})
            mods = os.path.join(d, "mods-full")
            with open(os.path.join(mods, "Rando-r74full", "spoiler.txt"), encoding="utf-8") as fh:
                spoiler = fh.read()
            self.assertIn(RC.NAMES_GAP, spoiler)
            for stale in STALE_SPOILER:                 # round 75 (b): no spoiler line says the full swap is later
                self.assertNotIn(stale, spoiler)
            self.assertIn("portrait / name records (laid by the full swap below).", spoiler)
            files = IG.rebuilt_files(mods, os.path.join(d, "w2"))
            p = IG.parse_patch(text)
            person_p = [f for f in p["files"] if f["kind"] == "person" and f["p"]]
            self.assertTrue(person_p, "chapter copies and route rows carry label pointers")
            self.assertTrue(any(not f["rel"].endswith("_HANDOVER.bin.lz") for f in person_p), "chapter copies")
            gd = T.container(IG.GAMEDATA_REL)
            gd_img = IG.memory_image(gd, GD_BASE)
            for f in person_p:
                o = T.container(f["rel"])
                n = T.Container(f["rel"], files[f["rel"]])
                img = IG.memory_image(o, FILE_BASE)
                before = bytes(img)
                images = {GD_BASE: gd_img, FILE_BASE: img}
                self.assertEqual(IG.apply_image(f, img, FILE_BASE, images, GD_BASE), [], f["rel"])
                want = {0x7000_0000: IG.memory_image(n, 0x7000_0000)}
                for s in n.b.relocs:
                    if n.u32(s) >= n.se:
                        got = struct.unpack_from("<I", img, s)[0]
                        self.assertEqual(IG.read_cstr(images, got), IG.read_cstr(want, 0x7000_0000 + n.u32(s)),
                                         f"{f['rel']} {s:#x}")
                self.assertEqual(IG.apply_image(f, img, FILE_BASE, images, GD_BASE, revert=True), [])
                self.assertEqual(bytes(img), before)
            face = [f for f in p["files"] if f["kind"] == "face"]
            self.assertEqual(len(face), 1)
            fc = T.container(IG.FACE_REL)
            self.assertIn(f"file face {IG.FACE_REL} {fc.u32(0)}\n", text)
            recs = IG.face_records(fc)
            img = IG.memory_image(fc, FILE_BASE)
            images = {FILE_BASE: img}
            self.assertEqual(IG.apply_image(face[0], img, FILE_BASE, images, GD_BASE), [])
            with open(os.path.join(mods, "Rando-r74full", "plan.json"), encoding="utf-8") as fh:
                plan = json.load(fh)
            fids = {x["fid"]: x["show"] for x in plan["recruit_engine"] if x["table"] == "FaceData"}
            pairs = IG.face_pairs(recs, fids)
            self.assertEqual(len(pairs), 2 * len(fids))
            for a, b in pairs:
                oa = 4 + a * IG.FACE_REC
                for fo in IG.FACE_PTRS:
                    v = struct.unpack_from("<I", img, oa + fo)[0]
                    self.assertEqual(None if v == 0 else IG.read_cstr(images, v), recs[b]["ptr"][fo][0])
                self.assertEqual(IG.read_cstr(images, struct.unpack_from("<I", img, oa + 8)[0]), recs[a]["key"])
            r = run("keep")
            self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
            self.assertFalse(os.path.exists(os.path.join(os.path.dirname(patch), "full.txt")), "stale full.txt removed")
            with open(patch, encoding="ascii") as fh:
                keep = fh.read()
            kp = IG.parse_patch(keep)
            self.assertFalse([f["rel"] for f in kp["files"] if f["kind"] == "person" and f["p"]],
                             "keep runs: no pointer cell in a person file")
            with open(os.path.join(d, "mods-keep", "Rando-r74full", "spoiler.txt"), encoding="utf-8") as fh:
                kspoil = fh.read()
            self.assertNotIn("E3/E4", kspoil)
            self.assertNotIn("Full swap (round 74", kspoil)
            # round 75b: the keep-the-face phrase no longer points at "later engine rounds" (round 75 kept it so the
            # fingerprints stayed; round 75b re-records every fingerprint anyway)
            self.assertIn("portrait / name records (plan.json only; the 'keep the face' look does not lay them).", kspoil)
            self.assertNotIn("for the later engine rounds", kspoil)


if __name__ == "__main__":
    unittest.main()
