"""Which edition this folder is (round 84, F-070 split round B; docs/SEAL_EDITION_PLAN.md section 4).

One repo, two editions: Vanilla+ (Fire Emblem Fates with the randomizer and the helpers) and the Seal edition (the
same plus the Seal folders: config/seal, tools/seal, tests/seal, docs/seal; credits in CREDITS.md). The fan mod itself
is never shipped and no byte of it is in these files.

A shared test with a Seal leg (a loop over (None, "seal"), a check of a page row's "seal" entry) runs that leg only in
the Seal edition. In the Vanilla+ folder (no Seal rules file in config/seal) the leg is skipped with one plain reason, as
a skipped subtest, so the run counts it and never fails on it. The Fates legs run in both editions.

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _edition as E
    for game in E.legs(self, (None, "seal")): ...          # the Seal leg skipped (and counted) without the edition
    with self.subTest(game="seal"):                          # one Seal-only check inside a shared test
        E.need_seal(self); self.assertIn("seal", ...)
    @E.needs_seal                                            # a whole Seal-only test (prefer tests/seal for new ones)
"""
from __future__ import annotations

import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEAL_RULES = os.path.join(ROOT, "config", "seal", "seal_rules.json")
SEAL_WORDS = ("seal", "sof", "seal-of-flames")
SKIP_REASON = "Seal edition leg: the Seal edition is not in this folder (no config/seal rules file)"


def seal_edition() -> bool:
    """True in the Seal edition (the repo on the dev machine is both editions)."""
    return os.path.isfile(SEAL_RULES)


def is_seal(game) -> bool:
    return isinstance(game, str) and game.lower() in SEAL_WORDS


def legs(tc: unittest.TestCase, games) -> tuple:
    """The games a looping test runs: all of them in the Seal edition; without it the Seal ones are left out and each
    is recorded as one skipped subtest (game=...) with SKIP_REASON."""
    games = tuple(games)
    if seal_edition():
        return games
    for g in games:
        if is_seal(g):
            with tc.subTest(game=g):
                tc.skipTest(SKIP_REASON)
    return tuple(g for g in games if not is_seal(g))


def need_seal(tc: unittest.TestCase) -> None:
    """Skip the current test (or the subtest it runs in) with SKIP_REASON when the Seal edition is not here."""
    if not seal_edition():
        tc.skipTest(SKIP_REASON)


needs_seal = unittest.skipUnless(seal_edition(), SKIP_REASON)
