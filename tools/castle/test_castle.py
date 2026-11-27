#!/usr/bin/env python3
"""Tests for the castle sheet tools (tools/castle/).

Standard library only (unittest). Needs the user's own extracted/romfs/; every test is
skipped when it is missing. Writes only under build/castle/_test/.

    python tools/castle/test_castle.py            all tests
    python tools/castle/test_castle.py -k Append  some tests by name
    FEF_CASTLE_ALL=1 python tools/castle/test_castle.py -k every
                                                  also round-trip all 274 sheet files

What is covered:
  * every registered layout passes `castle.py check` (the file's own declaration, the
    code's row size, list items on relocated pointers, no overlaps, row labels);
  * every registered file rebuilds byte-identical through CSV text (dump -> build), and
    through real files on disk with the command line (dump, build --check);
  * one-cell edits (dining stats, an accessory's damage bonus, a castle person, a My Room
    unlock) change exactly the edited byte(s) of the decompressed file; a string edit in
    a list item (JobIntro) changes only that cell after decoding;
  * rows added to the two dining sheets: the count goes up, the new row decodes to the
    CSV, its label resolves to it, every other row and sheet decodes unchanged, the
    rebuilt file passes the checks and rebuilds itself identically;
  * refusals: adding to AcceShop (fixed 256-entry save array), a row without a label, a
    reused label, wrong numbering, a removed row, a renamed label, a changed list count,
    an added list item, changed columns;
  * broken layouts are caught (wrong width, wrong list item size, wrong type);
  * a sample of other sheet files (effects, talk, field, map config, textures) round-trip
    with their declared types; the one malformed file is reported, not rebuilt;
  * the layouts hold no game text (ASCII only).
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sheetlib as L  # noqa: E402
import castle as C  # noqa: E402

T = L.T
HAVE = os.path.isfile(os.path.join(L.ROMFS, "GameData", "Castle", "DiningData.bin.lz"))
TESTDIR = os.path.join(L.OUTDIR, "_test")
DINING = "GameData/Castle/DiningData.bin.lz"


def quiet(fn, *a):
    buf = io.StringIO()
    with redirect_stdout(buf):
        r = fn(*a)
    return r, buf.getvalue()


def table(reg, key, c=None):
    d = reg[key]
    cod = C.codec(c or L.container(d.file), d)
    return cod, L.columns(cod.fields), cod.rows()


@unittest.skipUnless(HAVE, "needs extracted/romfs (python tools/assets/romfs.py)")
class Castle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = L.registry()

    # -------------------------------------------------------------- layouts
    def test_check_all_layouts(self):
        for k, d in self.reg.items():
            self.assertEqual(C.check_one(d), [], k)

    def test_layouts_are_ascii(self):
        for n in os.listdir(L.CONFIG):
            with open(os.path.join(L.CONFIG, n), "rb") as fh:
                raw = fh.read()
            self.assertTrue(all(b < 0x80 for b in raw), f"{n} holds non-ASCII text")

    def test_broken_layouts_are_caught(self):
        real = L.load_layout

        def broken(sheet: str, layout: str, patch) -> list[str]:
            L.load_layout = lambda k: patch(real(k)) if k == layout else real(k)
            try:
                return C.check_one(self.reg[sheet])
            except L.SheetError as e:
                return [str(e)]
            finally:
                L.load_layout = real

        def widen(f):  # two s8 stats merged into one s16
            return [x for x in f if x.name not in ("str", "mag")][:5] + [L.Field(0x7, 2, "s16", "strmag")] +                 [x for x in f if x.offset > 0x8]

        def retype(f):  # a str field typed as u32
            return [L.Field(0, 4, "u32", "person")] + f[1:]

        def shrink(f):  # list items of 16 bytes instead of 20
            return [x for x in f if x.offset < 0x10]

        def wrong_item(f):  # a string pointer read as a number
            return [L.Field(0, 4, "u32", "job")] + f[1:]
        self.assertTrue(broken("DiningData_Dish", "DiningData_Dish", widen))
        self.assertTrue(broken("CastlePerson", "CastlePerson", retype))
        self.assertTrue(broken("JobIntro_Group", "JobIntro_Unit", shrink))
        self.assertTrue(broken("JobIntro_Group", "JobIntro_Unit", wrong_item))
        self.assertEqual(broken("JobIntro_Group", "JobIntro_Unit", lambda f: f), [])

    # -------------------------------------------------------------- round trips
    def test_roundtrip_registered(self):
        r, out = quiet(C.roundtrip, self.reg)
        self.assertEqual(r, 0, out)
        self.assertEqual(out.count("byte-identical"), len(C.defs_by_file(self.reg)))

    def test_cli_dump_build_check(self):
        if os.path.isdir(TESTDIR):
            shutil.rmtree(TESTDIR)
        env = dict(os.environ)
        code = (f"import sys; sys.path.insert(0, {HERE!r}); import sheetlib as L; "
                f"L.OUTDIR = {TESTDIR!r}; L.REBUILT = {os.path.join(TESTDIR, 'rebuilt')!r}; "
                "import castle; sys.argv = ['castle.py'] + sys.argv[1:]; sys.exit(castle.main())")
        for args in (["dump"], ["build", "--check"]):
            p = subprocess.run([sys.executable, "-c", code] + args, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", env=env)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(os.path.isfile(os.path.join(TESTDIR, "DiningData_Dish.csv")))
        self.assertTrue(os.path.isfile(os.path.join(TESTDIR, "JobIntro_Group__JobIntro_Unit.csv")))
        with open(os.path.join(TESTDIR, "rebuilt", "GameData", "Castle", "DiningData.bin.lz"), "rb") as fh:
            self.assertEqual(fh.read(), L.container(DINING).raw)

    def test_generic_sample(self):
        for rel in ("GameData/GameEffect.bin.lz", "talk/call.bin", "GameData/Field/Btl_Yomi.bin",
                    "map/config/A001.bin", "TextureCoordinate.bin", "GameData/Live2D.bin.lz",
                    "GameData/Museum.bin.lz", "GameData/MyUnitEdit.bin.lz"):
            ok, note = L.generic_roundtrip(rel)
            self.assertTrue(ok, f"{rel}: {note}")

    def test_malformed_file_reported(self):
        with self.assertRaises(L.SheetError):
            L.generic_roundtrip("GameData/Field/Btl__UnexploredSea.bin")

    @unittest.skipUnless(os.environ.get("FEF_CASTLE_ALL"), "slow: set FEF_CASTLE_ALL=1")
    def test_every_sheet_file(self):
        bad = []
        for rel in L.sheet_files():
            try:
                ok, _ = L.generic_roundtrip(rel)
            except L.SheetError:
                ok = rel.endswith("Btl__UnexploredSea.bin")
            if not ok:
                bad.append(rel)
        self.assertEqual(bad, [])

    # -------------------------------------------------------------- edits
    def test_one_cell_edits(self):
        r, out = quiet(C.edit_test, self.reg)
        self.assertEqual(r, 0, out)
        self.assertEqual(out.count("exactly the edited byte"), 5, out)

    def test_negative_stat_edit(self):
        cod, hdr, rows = table(self.reg, "DiningData_Dish")
        rows[2][hdr.index("spd")] = "-3"
        out = C.build_file(self.reg, DINING, {"DiningData_Dish": (hdr, rows)}, {})
        c2 = T.Container(DINING, out)
        o = cod.s.rows + 2 * 0x10 + 0xA
        self.assertEqual(c2.data[o], 0xFD)
        self.assertEqual([i for i in range(len(c2.dec)) if c2.dec[i] != cod.c.dec[i]], [0x20 + o])

    def test_list_item_string_edit(self):
        d = self.reg["JobIntro_Group"]
        c = L.container(d.file)
        cod = C.codec(c, d)
        f = cod.fields[2]
        hdr = L.sub_columns(cod.subs[f.sub])
        items = cod.items(f)
        j = hdr.index("equipped_item")
        items[3][j] = "TEST_ITEM_NAME"
        out = C.build_file(self.reg, d.file, {}, {("JobIntro_Group", f.sub): (hdr, items)})
        c2 = T.Container(d.file, out)
        cod2 = C.codec(c2, d)
        self.assertEqual(cod2.items(cod2.fields[2]), items)
        self.assertEqual(cod2.rows(), cod.rows())

    # -------------------------------------------------------------- appends
    def _append(self, key, cells: dict):
        cod, hdr, rows = table(self.reg, key)
        new = [str(cod.s.count), cells["label"]] + [cells.get(f.name, "0") for f in cod.fields]
        out = C.build_file(self.reg, self.reg[key].file, {key: (hdr, rows + [new])}, {})
        return cod, rows, new, T.Container(self.reg[key].file, out)

    def _check_append(self, key, cells):
        cod, rows, new, c2 = self._append(key, cells)
        d = self.reg[key]
        cod2 = C.codec(c2, d)
        self.assertEqual(cod2.s.count, cod.s.count + 1)
        self.assertEqual(cod2.rows(), rows + [new])
        lab = T.untext(cells["label"])
        self.assertEqual(c2.label_off[lab], cod2.s.rows + cod.s.count * cod.s.size)
        for k, o in self.reg.items():  # every other sheet of the file is unchanged
            if o.file == d.file and k != key:
                self.assertEqual(C.codec(c2, o).rows(), C.codec(cod.c, o).rows(), k)
        reg2 = {k: v for k, v in self.reg.items() if v.file == d.file}
        old = L.container
        L.container = lambda rel: c2 if rel == d.file else old(rel)
        try:
            for k in reg2:
                self.assertEqual(C.check_one(reg2[k]), [], k)
        finally:
            L.container = old
        tables = {k: (L.columns(C.codec(c2, v).fields), C.codec(c2, v).rows()) for k, v in reg2.items()}
        self.assertEqual(C.build_file(reg2, d.file, tables, {}, c2), c2.raw)  # stable

    def test_append_dish(self):
        self._check_append("DiningData_Dish", {"label": "TEST_DISH", "name": "TEST_DISH", "ingredient_1": "3",
                                               "ingredient_2": "255", "str": "2", "def": "-1"})

    def test_append_cook_title_moves_dishes(self):
        self._check_append("DiningData_CookTitle", {"label": "TEST_TITLE", "name": "TEST_TITLE",
                                                    "bonus_target": "1", "spd": "3"})

    def test_append_two_rows(self):
        cod, hdr, rows = table(self.reg, "DiningData_Dish")
        n = cod.s.count
        extra = [[str(n + k), f"TEST_{k}", f"TEST_{k}"] + ["1"] * (len(hdr) - 3) for k in range(2)]
        out = C.build_file(self.reg, DINING, {"DiningData_Dish": (hdr, rows + extra)}, {})
        cod2 = C.codec(T.Container(DINING, out), self.reg["DiningData_Dish"])
        self.assertEqual(cod2.rows(), rows + extra)

    # -------------------------------------------------------------- refusals
    def assertRefused(self, key, rows=None, items=None, hdr=None, why=""):
        d = self.reg[key]
        with self.assertRaises(L.SheetError) as cm:
            C.build_file(self.reg, d.file, {key: (hdr, rows)} if rows is not None else {}, items or {})
        if why:
            self.assertIn(why, str(cm.exception))

    def test_refusals(self):
        cod, hdr, rows = table(self.reg, "AcceShop")
        extra = [str(cod.s.count), "ACCE_TEST"] + rows[1][2:]
        extra[2] = str(cod.s.count)
        self.assertRefused("AcceShop", rows + [extra], hdr=hdr, why="256")
        cod, hdr, rows = table(self.reg, "DiningData_Dish")
        n = cod.s.count
        base = ["X"] + ["0"] * (len(hdr) - 3)
        self.assertRefused("DiningData_Dish", rows + [[str(n), ""] + base], hdr=hdr, why="needs a label")
        self.assertRefused("DiningData_Dish", rows + [[str(n), rows[0][1]] + base], hdr=hdr, why="already used")
        self.assertRefused("DiningData_Dish", rows + [[str(n + 1), "T"] + base], hdr=hdr, why="numbered")
        self.assertRefused("DiningData_Dish", rows[:-1], hdr=hdr, why="cannot be removed")
        bad = [r[:] for r in rows]
        bad[0][1] = "RENAMED"
        self.assertRefused("DiningData_Dish", bad, hdr=hdr, why="renamed")
        self.assertRefused("DiningData_Dish", rows, hdr=hdr[:-1] + ["x"], why="columns")
        cod, hdr, rows = table(self.reg, "JobIntro_Group")
        bad = [r[:] for r in rows]
        bad[0][4] = "n=99"
        self.assertRefused("JobIntro_Group", bad, hdr=hdr, why="item count")
        f = cod.fields[2]
        ih = L.sub_columns(cod.subs[f.sub])
        items = cod.items(f)
        self.assertRefused("JobIntro_Group", items={("JobIntro_Group", f.sub): (ih, items + [items[-1]])},
                           why="cannot be added")
        extra = [str(cod.s.count), "TEST_GROUP"] + rows[0][2:]
        self.assertRefused("JobIntro_Group", rows + [extra], hdr=hdr, why="refused")

    def test_cells(self):
        for b in (b"\x00\x00\x80\x3f", b"\x00\x00\x80\xbf", b"\x00\x00\xc0\x7f", b"\x01\x00\x80\x7f",
                  b"\x00\x00\x00\x80", b"\xcd\xcc\x4c\x3d"):
            self.assertEqual(L.f32_bytes(L.f32_cell(b)), b)


class InsertLayout(unittest.TestCase):
    """insert_rows writes the raised count at the header's offset: it must refuse a sheet whose
    header is not wholly before its rows (review 2026-11-12, finding 2). Made-up layouts, no game file."""

    class Fake:
        rel = "made-up.bin"

    def sheet(self, hdr: int, rows: int) -> L.Sheet:
        return L.Sheet(0, 0, [], hdr=hdr, name=b"TEST", count=2, size=4, rows=rows)

    def test_rows_first_refused(self):
        for hdr, rows in ((0x40, 0x20), (0x20, 0x20), (0x1C, 0x20)):  # rows before, at, inside the header
            with self.assertRaises(L.SheetError) as cm:
                L.insert_rows(self.Fake(), self.sheet(hdr, rows), 1, [b""])
            self.assertIn("not before its rows", str(cm.exception))

    def test_header_first_passes_the_check(self):
        # the header's count ends exactly where the rows start: past the check, the fake container
        # has no file behind it, so the next step fails with something else
        with self.assertRaises(AttributeError):
            L.insert_rows(self.Fake(), self.sheet(0x1A, 0x20), 1, [b""])


if __name__ == "__main__":
    unittest.main(verbosity=1)
