#!/usr/bin/env python3
"""Unit tests for tools/harness/watchdog.py (no game): each watchdog on made-up samples, the press index in every
verdict, the allow-list rules, the corrupted-savestate round trip, the plant route variant."""
from __future__ import annotations

import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import watchdog as wd  # noqa: E402


def guest(tick: int, state: int = 0) -> bytes:
    b = bytearray(4096)
    b[0:4] = struct.pack("<I", tick)
    b[1000] = state % 256
    return bytes(b)


PRESSES = ",".join(f"{f}:A" for f in range(300, 3000, 300))


class WatchTests(unittest.TestCase):
    def feed(self, w, pic, state, upto=3000):
        for f in range(30, upto, 30):
            if w.feed(f, pic(f), guest(f, state(f))):
                break
        return w

    def test_selftest_passes(self):
        fails, line = wd.selftest()
        self.assertEqual(fails, [], line)

    def test_clean(self):
        p = wd.Presses(PRESSES)
        w = self.feed(wd.Watch("t", p), lambda f: f"p{p.index_at(f)}", p.index_at)
        v = w.finish(0, "Completed", 3000, 3000, "")
        self.assertEqual(v["kind"], "clean")
        self.assertTrue(v["line"].startswith("CLEAN: "))

    def test_crash_has_press_index(self):
        p = wd.Presses(PRESSES)
        w = self.feed(wd.Watch("t", p), lambda f: f"p{f}", lambda f: f, upto=1000)
        v = w.finish(1, None, None, 3000, "")
        self.assertEqual(v["kind"], "crash")
        self.assertEqual(v["press"], 3)  # last sample 990: presses at 300, 600, 900
        self.assertIn("press 3 of 9 (frame 900 A)", v["line"])
        self.assertEqual(len(v["line"].splitlines()), 1)

    def test_crash_on_panic_line(self):
        v = wd.Watch("t", wd.Presses(PRESSES)).finish(0, "Completed", 3000, 3000, "thread 'main' panicked at x")
        self.assertEqual(v["kind"], "crash")

    def test_hang_wall(self):
        w = wd.Watch("t", wd.Presses(PRESSES), hang_s=30)
        w.feed(630, "a", guest(1), wall=0.0)
        self.assertIsNone(w.wall_check(29.0))
        v = w.wall_check(31.0)
        self.assertEqual((v["kind"], v["press"]), ("hang", 2))

    def test_hang_guest(self):
        w = self.feed(wd.Watch("t", wd.Presses(PRESSES), guest_frames=300), lambda f: f"p{f}", lambda f: 0)
        w2 = wd.Watch("t", wd.Presses(PRESSES), guest_frames=300)
        for f in range(30, 900, 30):
            w2.feed(f, f"p{f}", bytes(4096))
        self.assertEqual(w2.verdict["kind"], "hang")
        self.assertNotEqual((w.verdict or {}).get("kind"), "hang")  # the ticker moves: the guest is alive

    def test_stuck_and_allow(self):
        p = wd.Presses(PRESSES)
        w = self.feed(wd.Watch("t", p, soft_presses=99), lambda f: "still", p.index_at)
        self.assertEqual((w.verdict["kind"], w.verdict["press"]), ("stuck", 1))
        allow = {"static_ok": [{"route": "t", "from": 0, "to": 9999, "why": "a static menu"}]}
        w = self.feed(wd.Watch("t", p, allow=allow, soft_presses=99), lambda f: "still", p.index_at)
        self.assertIsNone(w.verdict)
        self.assertEqual(w.allowed_static[0][2], "a static menu")
        other = {"static_ok": [{"route": "other", "from": 0, "to": 9999, "why": "x"}]}
        w = self.feed(wd.Watch("t", p, allow=other, soft_presses=99), lambda f: "still", p.index_at)
        self.assertEqual(w.verdict["kind"], "stuck")

    def test_softlock(self):
        p = wd.Presses(PRESSES)
        w = self.feed(wd.Watch("t", p, stuck_frames=10 ** 6, soft_presses=4), lambda f: f"a{f % 90}", lambda f: 0)
        self.assertEqual(w.verdict["kind"], "softlock")
        w = self.feed(wd.Watch("t", p, stuck_frames=10 ** 6, soft_presses=4), lambda f: f"a{f % 90}", p.index_at)
        self.assertIsNone(w.verdict)

    def test_no_presses_no_stuck(self):
        w = self.feed(wd.Watch("t", wd.Presses("")), lambda f: "still", lambda f: 0)
        self.assertIsNone(w.verdict)


class StateTests(unittest.TestCase):
    def test_corrupt_roundtrip_caught(self):
        hl = wd.headless()
        with tempfile.TemporaryDirectory() as td:
            a, b = os.path.join(td, "a.bin"), os.path.join(td, "b.bin")
            with open(a, "wb") as fh:
                fh.write(hl.fake_state(b"meta", [bytes(0x200000), bytes(32), bytes(32), bytes(32)]))
            note = wd.corrupt_state(a, b)
            self.assertIn("fcram", note)
            da, ma = wd.digest_file(a, [])
            db, mb = wd.digest_file(b, [])
            ok, why = hl.compare_digests(da, db, ma, mb)
            self.assertFalse(ok)
            self.assertIn("DIFFERS (fcram)", why)

    def test_static_variant(self):
        r = {"input": "100:A,400:B,700:A", "frames": 1000, "save_at": 990, "shots": [500, 900]}
        v = wd.static_variant(r, 450, "SELECT", 100, 3)
        self.assertEqual(v["input"], "100:A,400:B,550:SELECT,650:SELECT,750:SELECT")
        self.assertLess(v["save_at"], v["frames"])
        self.assertEqual(r["input"], "100:A,400:B,700:A")  # the route itself is not changed

    def test_refuses_cheat_and_options_routes(self):
        lane = wd.Lane.__new__(wd.Lane)
        lane.routes = {"c": {"cheat": True}, "o": {"options": {}}, "p": {"input": "1:A"}}
        with self.assertRaises(wd.Stop):
            lane.route("c")
        with self.assertRaises(wd.Stop):
            lane.route("o")
        self.assertEqual(lane.route("p"), {"input": "1:A"})


if __name__ == "__main__":
    unittest.main()
