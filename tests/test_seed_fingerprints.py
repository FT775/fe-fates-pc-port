"""Seeds unchanged (round 67, release part A, goal 3; tools/release/fingerprints.py).

config/release/seed_fingerprints.json holds sha256 hashes only of what each guarded seed makes (Fates and Seal of
Flames, the page's default and "Randomize everything", seed 1; round 63's boss seed r63fboss1 with its guarded patch
and plan shas; the round-62/62b page run ids). config/release/seed_changes.json lists the changes the current round
announces. A change that is listed passes with a note; one that is not FAILS with "seeds changed without notice".

The first classes use made-up hashes (no game data). RealCheck makes every key fresh (rando cache OFF, makes side by
side, about 45 s wall) and skips without the extracted RomFS; Seal keys skip with a plain reason without the mod.
R62Runs (round 85): without build/r62/check/runs, ids/r62-page is an ERROR in the work folder and a plain skip in a
release copy (no .git: the zip is a `git archive`).

    python -m unittest tests.test_seed_fingerprints
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "release"))
import fingerprints as FP  # noqa: E402

H1, H2, H3 = "a" * 64, "b" * 64, "c" * 64


def val(h, part=None):
    parts = {"patch": part or h, "plan": H3}
    return {"sha256": h, "parts": parts}


def store(**keys):
    return {"format": FP.FORMAT, "round": 66, "keys": {k.replace("__", "/"): v for k, v in keys.items()}}


class Verdicts(unittest.TestCase):
    def test_same_passes(self):
        ev = FP.evaluate({"f/d/1": val(H1)}, {}, {}, store(f__d__1=val(H1)), {"round": 67, "changes": []})
        self.assertTrue(ev["ok"])
        self.assertEqual(ev["rows"], [("f/d/1", "same", "")])

    def test_unannounced_change_fails_with_the_keys(self):
        ev = FP.evaluate({"f/d/1": val(H2, H2), "f/e/1": val(H1)}, {}, {},
                         store(f__d__1=val(H1), f__e__1=val(H1)), {"round": 67, "changes": []})
        self.assertFalse(ev["ok"])
        self.assertEqual(ev["unannounced"], ["f/d/1"])
        self.assertEqual(ev["message"], "seeds changed without notice: f/d/1")
        self.assertIn("patch changed", dict((k, n) for k, _s, n in ev["rows"])["f/d/1"])

    def test_announced_change_passes_with_a_note(self):
        ch = {"round": 67, "changes": [{"key": "f/d/1", "reason": "boss classes on Seal"}]}
        ev = FP.evaluate({"f/d/1": val(H2)}, {}, {}, store(f__d__1=val(H1)), ch)
        self.assertTrue(ev["ok"])
        self.assertEqual(ev["rows"][0][1], "changed-announced")
        self.assertIn("boss classes on Seal", ev["rows"][0][2])

    def test_new_and_gone_keys_are_changes(self):
        ev = FP.evaluate({"n/1": val(H1)}, {}, {}, store(o__1=val(H1)), {"round": 67, "changes": []})
        self.assertFalse(ev["ok"])
        self.assertEqual(sorted(ev["unannounced"]), ["n/1", "o/1"])
        ch = {"round": 67, "changes": [{"key": "n/1", "reason": "new"}, {"key": "o/1", "reason": "dropped"}]}
        ev = FP.evaluate({"n/1": val(H1)}, {}, {}, store(o__1=val(H1)), ch)
        self.assertTrue(ev["ok"])
        self.assertEqual({s for _k, s, _n in ev["rows"]}, {"new-announced", "gone-announced"})

    def test_skipped_passes_with_its_reason_and_errors_fail(self):
        ev = FP.evaluate({}, {"s/d/1": "Seal of Flames is not installed (play/seal-of-flames)"}, {},
                         store(s__d__1=val(H1)), {"round": 67, "changes": []})
        self.assertTrue(ev["ok"])
        self.assertEqual(ev["rows"][0][1:], ("skipped", "Seal of Flames is not installed (play/seal-of-flames)"))
        ev = FP.evaluate({}, {}, {"f/d/1": "make failed"}, store(f__d__1=val(H1)), {"round": 67, "changes": []})
        self.assertFalse(ev["ok"])
        self.assertIn("could not be made: f/d/1", ev["message"])


    def test_guarded_key_cannot_be_announced_away(self):
        # round 67 integrate: r63fboss1's patch/plan shas are guarded since round 63
        good = {"sha256": H1, "parts": dict(FP.GUARDED[FP.R63FBOSS1])}
        bad = {"sha256": H2, "parts": dict(FP.GUARDED[FP.R63FBOSS1], patch=H2)}
        st = {"format": FP.FORMAT, "round": 67, "keys": {FP.R63FBOSS1: good}}
        ch = {"round": 67, "changes": [{"key": FP.R63FBOSS1, "reason": "announced"}]}
        ev = FP.evaluate({FP.R63FBOSS1: bad}, {}, {}, st, ch)
        self.assertFalse(ev["ok"])
        self.assertIn("guarded shas changed", ev["message"])
        with self.assertRaisesRegex(FP.FingerprintError, "guarded shas changed"):
            FP.apply_update({FP.R63FBOSS1: bad}, {}, {}, st, ch, 67)
        # a listed change outside the guarded parts (e.g. the spoiler) still passes with a note
        other = {"sha256": H2, "parts": dict(FP.GUARDED[FP.R63FBOSS1], spoiler=H2)}
        self.assertTrue(FP.evaluate({FP.R63FBOSS1: other}, {}, {}, st, ch)["ok"])


class Update(unittest.TestCase):
    def test_rewrites_only_listed_keys(self):
        ch = {"round": 67, "changes": [{"key": "f/d/1", "reason": "announced"}]}
        new = FP.apply_update({"f/d/1": val(H2), "f/e/1": val(H1)}, {}, {}, store(f__d__1=val(H1), f__e__1=val(H1)),
                              ch, 67)
        self.assertEqual(new["keys"]["f/d/1"], val(H2))
        self.assertEqual(new["keys"]["f/e/1"], val(H1))
        self.assertEqual(new["round"], 67)
        self.assertEqual(FP.check_store(new), [])

    def test_refuses_unlisted_change_wrong_round_skips_and_errors(self):
        st = store(f__d__1=val(H1), f__e__1=val(H1))
        ch = {"round": 67, "changes": [{"key": "f/d/1", "reason": "announced"}]}
        with self.assertRaisesRegex(FP.FingerprintError, "seeds changed without notice: f/e/1"):
            FP.apply_update({"f/d/1": val(H2), "f/e/1": val(H2)}, {}, {}, st, ch, 67)
        with self.assertRaisesRegex(FP.FingerprintError, "for round 67, not round 68"):
            FP.apply_update({"f/d/1": val(H2), "f/e/1": val(H1)}, {}, {}, st, ch, 68)
        with self.assertRaisesRegex(FP.FingerprintError, "skipped here"):
            FP.apply_update({"f/d/1": val(H2)}, {"f/e/1": "no mod"}, {}, st, ch, 67)
        with self.assertRaisesRegex(FP.FingerprintError, "could not be made"):
            FP.apply_update({"f/d/1": val(H2)}, {}, {"f/e/1": "rc 1"}, st, ch, 67)

    def test_file_shapes(self):
        self.assertEqual(FP.check_changes_file({"round": 67, "changes": []}), [])
        self.assertTrue(FP.check_changes_file({"round": 67, "changes": [{"key": "x"}]}))
        self.assertTrue(FP.check_changes_file({"round": 67, "changes": [{"key": "x", "reason": " "}]}))
        self.assertTrue(FP.check_changes_file({"changes": []}))
        self.assertTrue(FP.check_store(store(f__d__1={"sha256": H1, "parts": {"plan": "HP 20"}})))
        self.assertTrue(FP.check_store(store(f__d__1=dict(val(H1), name="Corrin"))))


class Files(unittest.TestCase):
    """The tracked files: hashes only, the right keys, the existing guards carried on."""

    @classmethod
    def setUpClass(cls):
        cls.store = FP.load_json(FP.STORE)
        cls.changes = FP.load_json(FP.CHANGES)

    def test_shapes(self):
        self.assertIsNotNone(self.store, "config/release/seed_fingerprints.json is missing")
        self.assertIsNotNone(self.changes, "config/release/seed_changes.json is missing")
        self.assertEqual(FP.check_store(self.store), [])
        self.assertEqual(FP.check_changes_file(self.changes), [])

    def test_every_key_recorded(self):
        listed = {c["key"] for c in self.changes["changes"]}
        self.assertEqual((set(self.store["keys"]) ^ set(FP.all_keys())) - listed, set())
        for game in ("fates", "seal"):
            for flags in ("default", "everything-on"):
                self.assertIn(f"{game}/{flags}/1", self.store["keys"])

    def test_r63fboss1_guard_carried_on(self):
        if FP.R63FBOSS1 in {c["key"] for c in self.changes["changes"]}:
            self.skipTest("r63fboss1 change announced this round")
        got = self.store["keys"][FP.R63FBOSS1]["parts"]
        for part, want in FP.GUARDED[FP.R63FBOSS1].items():
            self.assertEqual(got[part], want, part)


class R62Runs(unittest.TestCase):
    """ids/r62-page without build/r62/check/runs: an ERROR in the work folder (round 67 rule), a skip with a plain
    reason in a release copy (round 85, plan section 4 item 4: the zip is a `git archive`, so it has no .git)."""

    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.root = self.t.name
        self.runs = os.path.join(self.root, "build", "r62", "check", "runs")

    def tearDown(self):
        self.t.cleanup()

    def test_release_copy_skips_with_a_plain_reason(self):
        self.assertTrue(FP.is_release_copy(self.root))
        what, why = FP.r62_status(None, self.runs, self.root)
        self.assertEqual((what, why), ("skip", FP.R62_RELEASE_SKIP))
        self.assertIn("release copy", why)
        self.assertIn("build/r62/check/runs", why)

    def test_work_folder_stays_an_error(self):
        os.mkdir(os.path.join(self.root, ".git"))
        self.assertFalse(FP.is_release_copy(self.root))
        what, why = FP.r62_status(None, self.runs, self.root)
        self.assertEqual(what, "error")
        self.assertIn("is missing", why)
        # a git worktree has a .git FILE: still the work folder
        os.rmdir(os.path.join(self.root, ".git"))
        with open(os.path.join(self.root, ".git"), "w") as fh:
            fh.write("gitdir: elsewhere\n")
        self.assertEqual(FP.r62_status(None, self.runs, self.root)[0], "error")

    def test_runs_present_or_no_game_data(self):
        os.makedirs(self.runs)
        self.assertEqual(FP.r62_status(None, self.runs, self.root), ("make", None))
        self.assertEqual(FP.r62_status("no RomFS", self.runs, self.root), ("skip", "no RomFS"))

    def test_this_folder(self):
        self.assertEqual(FP.is_release_copy(), not os.path.exists(os.path.join(ROOT, ".git")))

    def test_a_skipped_key_passes_check_but_blocks_update(self):
        st = store(f__d__1=val(H1))
        st["keys"][FP.R62_IDS] = val(H2)
        ch = {"round": 85, "changes": []}
        ev = FP.evaluate({"f/d/1": val(H1)}, {FP.R62_IDS: FP.R62_RELEASE_SKIP}, {}, st, ch)
        self.assertTrue(ev["ok"])
        self.assertIn((FP.R62_IDS, "skipped", FP.R62_RELEASE_SKIP), ev["rows"])
        with self.assertRaisesRegex(FP.FingerprintError, "skipped here"):
            FP.apply_update({"f/d/1": val(H1)}, {FP.R62_IDS: FP.R62_RELEASE_SKIP}, {}, st, ch, 85)


@unittest.skipIf(FP.fates_ready() is not None, f"no real data: {FP.fates_ready()}")
class RealCheck(unittest.TestCase):
    """Every key made fresh now (cache off) and compared with the recorded hashes."""

    @classmethod
    def setUpClass(cls):
        cls.values, cls.skipped, cls.errors, cls.secs = FP.compute()
        cls.ev = FP.evaluate(cls.values, cls.skipped, cls.errors, FP.load_json(FP.STORE), FP.load_json(FP.CHANGES))

    def test_no_seed_changed_without_notice(self):
        self.assertTrue(self.ev["ok"], FP.table(self.ev))
        for k, s, n in self.ev["rows"]:
            if s == "changed-announced":
                print(f"\nnote: {k} changed, announced: {n}")

    def test_seal_keys_made(self):
        why = FP.seal_ready()
        if why:
            self.skipTest(f"Seal keys skipped: {why}")
        for flags in ("default", "everything-on"):
            self.assertIn(f"seal/{flags}/1", self.values)

    def test_fates_and_ids_keys_made(self):
        self.assertEqual(self.errors, {})
        for k in FP.all_keys():
            if not k.startswith("seal/") and k != FP.R62_IDS:
                self.assertIn(k, self.values)
        if os.path.isdir(FP.R62_RUNS):
            self.assertIn(FP.R62_IDS, self.values)
        elif FP.is_release_copy():
            # round 85: a release copy has no build/; the key is skipped with its plain reason (never an error)
            self.assertEqual(self.skipped.get(FP.R62_IDS), FP.R62_RELEASE_SKIP)
            print(f"\nnote: {FP.R62_IDS} skipped: {FP.R62_RELEASE_SKIP}")


if __name__ == "__main__":
    unittest.main()
