#!/usr/bin/env python3
"""Tests for the Fates function registry.

    python tools/fates/test_symbols.py        (or: python -m unittest tools/fates/test_symbols.py)

The synthetic tests always run. The registry tests need extracted/ (the owner's ROM,
python tools/extract_rom.py) and are skipped without it.
"""
from __future__ import annotations

import csv
import io
import re
import struct
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "analysis"))
import symbols as S  # noqa: E402
from gamecfg import GAME  # noqa: E402

HAVE_ROM = (ROOT / "extracted" / "code.bin").is_file() and \
    (ROOT / "extracted" / "romfs" / GAME.romfs.symbol_map.names).is_file()


class Synthetic(unittest.TestCase):
    def test_selftest(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = S.selftest()
        self.assertEqual(rc, 0, buf.getvalue())

    def test_unterminated_map(self):
        ents, st = S.parse_map(b"f(void)\0", struct.pack("<2I", 0x100000, 0))
        self.assertFalse(st["terminator"])
        self.assertEqual(ents[0].names, ["f(void)"])

    def test_descending_rejected(self):
        with self.assertRaises(ValueError):
            S.parse_map(b"a\0b\0", struct.pack("<4I", 0x100010, 0, 0x100000, 2))


@unittest.skipUnless(HAVE_ROM, "needs extracted/ (python tools/extract_rom.py)")
class Registry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "config" / "functions.csv").open(newline="", encoding="utf-8") as f:
            cls.rows = list(csv.DictReader(f))
        cls.entries, cls.stats = S.read_map()

    def test_columns(self):
        self.assertEqual(list(self.rows[0].keys()), S.COLUMNS)

    def test_up_to_date(self):
        r = subprocess.run([sys.executable, str(HERE / "symbols.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_contiguous_and_sized(self):
        t = GAME.seg("text")
        prev_end = None
        for r in self.rows:
            a, e, size = int(r["addr"], 16), int(r["end"], 16), int(r["size"])
            self.assertTrue(t.vaddr <= a < e <= t.end, r["addr"])
            self.assertEqual(e - a, size)
            self.assertEqual(a & 1, 0, "Thumb bit must not be in addr")
            if prev_end is not None:
                self.assertEqual(prev_end, a, "rows must tile .text")
            prev_end = e
        self.assertEqual(prev_end, t.end)

    def test_names_unique_and_safe(self):
        names = [r["name"] for r in self.rows]
        self.assertEqual(len(names), len(set(names)))
        for n in names:
            self.assertRegex(n, r"^[A-Za-z_][A-Za-z0-9_]*$")

    def test_every_map_name_present(self):
        by = {int(r["addr"], 16): r for r in self.rows}
        for e in self.entries:
            r = by.get(e.addr)
            self.assertIsNotNone(r, hex(e.addr))
            got = {r["signature"]} | set(filter(None, r["aliases"].split(" | ")))
            self.assertEqual(got, set(e.names), hex(e.addr))
        self.assertEqual(self.stats["names"], 26122)
        self.assertIn("27274", self.stats["timestamp"])

    def test_library_tags(self):
        libs = {r["library"] for r in self.rows}
        self.assertLessEqual(libs, set(S.LIBRARIES))
        by_sig = {r["signature"]: r["library"] for r in self.rows if r["signature"]}
        self.assertEqual(by_sig.get(".nn.svc.SleepThread"), "ctr_sdk")
        unknown = sum(1 for r in self.rows if r["library"] == "unknown")
        self.assertLess(unknown, 200)
        for r in self.rows:
            sig = r["signature"]
            if sig.startswith("nn::nex::"):
                self.assertEqual(r["library"], "nex", sig)
            elif sig.startswith("nn::pia::"):
                self.assertEqual(r["library"], "pia", sig)
            elif sig.startswith("nw::"):
                self.assertEqual(r["library"], "nw4c", sig)

    def test_modes(self):
        for r in self.rows:
            if int(r["addr"], 16) & 2:
                self.assertEqual(r["mode"], "THUMB", r["addr"])

    def test_arm_alignment(self):
        """ARM rows start on a word; one may end on a halfword only when a Thumb row follows
        (ARM->Thumb stubs and Thumb helpers packed after an ARM literal pool)."""
        for i, r in enumerate(self.rows):
            if r["mode"] != "ARM":
                continue
            a, e = int(r["addr"], 16), int(r["end"], 16)
            self.assertEqual(a % 4, 0, r["addr"])
            if e % 4:
                self.assertEqual(self.rows[i + 1]["mode"], "THUMB", r["addr"])

    def test_named_bodies_intact(self):
        """No unnamed start may sit inside the code a named function reaches (flow.reach from
        its map start, up to the next map start), unless code calls it with BL/BLX (armcc
        lets a caller run into a tail callee). This is the check that catches 'ldr r0,=x ;
        push {..lr}' openings being split into a 4-byte function plus a fake func_X."""
        import flow as F
        code = (ROOT / "extracted" / "code.bin").read_bytes()
        t = GAME.seg("text")
        named = [r for r in self.rows if r["signature"]]
        starts = [int(r["addr"], 16) for r in named]
        reaches = {}
        calls = set()
        for i, r in enumerate(self.rows):
            a = int(r["addr"], 16)
            calls.update(c for c, _ in F.reach(code, t.vaddr, a, int(r["end"], 16), r["mode"] == "THUMB").calls)
        for i, a in enumerate(starts):                 # named code reached past nearer unnamed starts
            lim = starts[i + 1] if i + 1 < len(starts) else t.end
            reaches[a] = F.reach(code, t.vaddr, a, lim, named[i]["mode"] == "THUMB")
            calls.update(c for c, _ in reaches[a].calls)
        known = sorted(int(r["addr"], 16) for r in self.rows)
        bad = []
        for r in self.rows:
            if r["signature"] or r["source"] == "hand":
                continue
            x = int(r["addr"], 16)
            i = __import__("bisect").bisect_right(starts, x) - 1
            if i < 0:
                continue
            s = named[i]
            lim = starts[i + 1] if i + 1 < len(starts) else t.end
            key = starts[i]
            if key not in reaches:
                reaches[key] = F.reach(code, t.vaddr, key, lim, s["mode"] == "THUMB")
            if reaches[key].covers(x, known) and x not in calls:
                bad.append(f"{r['addr']} inside {s['name']}")
        self.assertEqual(bad, [], f"{len(bad)} unnamed starts split named functions")

    def test_direct_calls_are_starts(self):
        import flow as F
        code = (ROOT / "extracted" / "code.bin").read_bytes()
        t = GAME.seg("text")
        starts = {int(r["addr"], 16) for r in self.rows}
        missing = set()
        n = 0
        for r in self.rows:
            for c, _ in F.reach(code, t.vaddr, int(r["addr"], 16), int(r["end"], 16), r["mode"] == "THUMB").calls:
                if t.vaddr <= c < t.end:
                    n += 1
                    if c not in starts:
                        missing.add(c)
        self.assertGreater(n, 80000)
        self.assertEqual(sorted(hex(m) for m in missing), [])

    def test_reviewed_boundaries(self):
        """Cases checked by hand with objdump (docs/SYMBOLS.md, 'Function boundaries')."""
        by = {int(r["addr"], 16): r for r in self.rows}
        for a, size in [(0x1D42BC, 48), (0x1E9ABC, 28), (0x1951D8, 56), (0x1648DC, 40), (0x375B58, 92),
                        (0x100048, 6),
                        # Thumb C-library code packed after ARM functions (stdio init at
                        # 0x103060 calls 0x30119C / 0x301A10 / 0x301A1C with Thumb BL)
                        (0x102FE2, 126), (0x301148, 84), (0x3019A8, 104), (0x301A10, 12)]:
            self.assertEqual(int(by[a]["size"]), size, f"{a:#x} {by[a]['name']}")
        for a in (0x1D42C0, 0x1E9AC0, 0x1951DC, 0x1648E0, 0x375BA6, 0x376B42, 0x376080, 0x4F002E):
            self.assertNotIn(a, by, f"false start {a:#x}")
        for a in (0x10004E, 0x2FDBEC, 0x2FDBF6, 0x103D0C,      # real Thumb code
                  0x103060, 0x30119C, 0x301A10, 0x301A1C):
            self.assertEqual(by[a]["mode"], "THUMB", f"{a:#x}")
        self.assertEqual([r["addr"] for r in self.rows if r["library"] == "game" and r["mode"] == "THUMB"], [])

    def test_export(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "export_symbols.py")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = (ROOT / "build" / "symbols.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), len(self.rows))
        for ln in lines:
            self.assertRegex(ln, r"^\S+ 0x[0-9A-F]{8} f$")

    def test_spotcheck(self):
        r = subprocess.run([sys.executable, str(HERE / "spotcheck.py")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("24 match", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
