"""Round 63 (F-049, F-051): tougher bosses give +1 / +2 / +3 weapon MIGHT as the player sees it (Easy / Normal /
Hard), not forge levels (tools/randomizer/weapons.py boss_refine_row / boss_might_plan; docs/rando/BOSS_MIGHT.md).

    python -m unittest tests.test_rando_boss_might          (from the repo root)

The game's own rule (asm): Unit::SetDisposItem 003D8C38 gives every weapon of a unit whose Person.unit_kind is not
1 name slot 1; unit::Item::GetPower 0053B4B4 then adds the might byte of ItemRefine row Item+0x49 (`unknown_49`)
at the weapon's forge rank, instead of row Item+0x48 (`refine_index`). Round 62 forged by the +0x48 row (+2 might
a level) while the screen showed +1 a level: that row is the wrong one for enemies.

Made-up forge rows first (no game data). The last class reads the game's tables and the runs made by
build/r63/might/mkruns.py (skipped when either is missing) and recomputes the SHOWN might of every boss weapon the
spoiler lists, independently of weapons.py.
"""
from __future__ import annotations

import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
import randolib as R  # noqa: E402
import weapons as W  # noqa: E402

STEP = {"easy": 1, "normal": 2, "hard": 3}


def _row(mights):
    r = {"index": "0"}
    for lvl in range(10):
        r[f"plus_{lvl}.might"] = str(([0] + list(mights) + [0] * 10)[lvl])
    return r


# the shapes of the game's rows: 0/1 = +2 a level up to +4 then +1; 2 = +1 a level (the second forge table)
REFINE = {0: _row([2, 4, 6, 8, 9, 10, 11]), 1: _row([2, 4, 6, 8, 9, 10, 11]), 2: _row([1, 2, 3, 4, 5, 6, 7, 8, 9])}


class _WV:
    def __init__(self, items):
        self.items = items

    def v(self, iid, col):
        return R.ival(self.items[iid].get(col, 0))


class _T:
    def __init__(self, pc):
        self.pc = pc


class MightPlan(unittest.TestCase):
    def test_second_table_gives_step(self):
        for d, st in STEP.items():
            n, add, cap = W.boss_might_plan(REFINE, 2, 0, st)
            self.assertEqual((n, add, cap), (st, st, False), d)

    def test_second_table_on_a_forged_weapon(self):
        self.assertEqual(W.boss_might_plan(REFINE, 2, 2, 3), (3, 3, False))

    def test_forge_maximum_stops_and_says_so(self):
        self.assertEqual(W.boss_might_plan(REFINE, 2, 5, 3), (2, 2, True))
        self.assertEqual(W.boss_might_plan(REFINE, 2, 7, 1), (0, 0, True))

    def test_first_table_even_steps(self):
        # a playable person's weapon (unit_kind 1) uses refine_index: +2 a level, so Easy/Normal +2, Hard +4
        self.assertEqual(W.boss_might_plan(REFINE, 0, 0, 1), (1, 2, False))
        self.assertEqual(W.boss_might_plan(REFINE, 0, 0, 2), (1, 2, False))
        self.assertEqual(W.boss_might_plan(REFINE, 0, 0, 3), (2, 4, False))
        self.assertEqual(W.boss_might_plan(REFINE, 0, 4, 3), (3, 3, False))   # past +4: +1 a level

    def test_step_zero(self):
        self.assertEqual(W.boss_might_plan(REFINE, 2, 0, 0), (0, 0, False))

    def test_round62_rule_was_short(self):
        # the round-62 bug: levels picked on row 0, shown on row 2 -> Normal +1, Hard +2 (the screen's numbers)
        for d, shown in (("easy", 1), ("normal", 1), ("hard", 2)):
            n = W.boss_might_plan(REFINE, 0, 0, STEP[d])[0]
            self.assertEqual(W.refine_might(REFINE, 2, n), shown, d)

    def test_row_by_unit_kind(self):
        wv = _WV({"IID_X": {"refine_index": "1", "unknown_49": "2"}})
        for kind, want in (("0", 2), ("2", 2), ("3", 2), ("1", 1)):
            t = _T({"PID_B": {"unit_kind": kind}})
            self.assertEqual(W.boss_refine_row(t, wv, {"pid": "PID_B"}, "IID_X"), want, kind)
        self.assertEqual(W.boss_refine_row(_T({}), wv, {"pid": "PID_NONE"}, "IID_X"), 2)

    def test_no_table_one_per_level(self):
        self.assertEqual(W.boss_might_plan(None, 0, 0, 3), (3, 3, False))


# ------------------------------------------------------------------ the game's tables and the made runs
RUNS = os.path.join(ROOT, "build", "r63", "might", "runs")
LINE = re.compile(r"^  (\w{4}) unit (\d+) \(boss\) slot (\d): forge \+(\d+) \(tougher boss \+(\d+): might \+(\d+) shown"
                  r"(, stopped by the forge maximum 7)?")


def shown_check(run_dir: str, tables: dict) -> tuple[int, list[str]]:
    """Every tougher-boss line of a run's spoiler, recomputed from the game's own tables: the forge row by the
    unit's Person.unit_kind in that chapter's Person file, the might byte of that row at the old and new rank.
    Returns (lines checked, problems)."""
    import json
    with open(os.path.join(run_dir, "options.json"), encoding="utf-8") as fh:
        opts = json.load(fh)
    with open(os.path.join(run_dir, "spoiler.txt"), encoding="utf-8") as fh:
        spoiler = fh.read().splitlines()
    step = STEP[opts.get("difficulty", "normal")]
    bad, n = [], 0
    for ln in spoiler:
        m = LINE.match(ln.rstrip("\n"))
        if not m:
            continue
        ch, ix, s, fx, bn, shown, cap = m.groups()
        n += 1
        d = tables["dispos"].get((ch, int(ix)))
        if d is None:
            bad.append(f"{ch} unit {ix}: no dispos row")
            continue
        p = tables["pc"].get((ch, d["pid"])) or tables["pc_any"].get(d["pid"]) or {}
        it = tables["items"][d[f"item_{s}"]]
        row = R.ival(it["refine_index"]) if R.ival(p.get("unit_kind", 0)) == 1 else R.ival(it["unknown_49"])
        cur = max([0] + [R.ival(d.get(f"item_{s}_forge.{c}", 0) or 0) for c in W.FORGE_COLS])
        rr = tables["refine"][row]
        top = min(7, cur + int(fx))              # forge +fx = ladder levels (fx - bn) + tougher-boss levels (bn)
        add = R.ival(rr[f"plus_{top}.might"]) - R.ival(rr[f"plus_{top - int(bn)}.might"])
        if add != int(shown):
            bad.append(f"{ch} unit {ix} slot {s}: spoiler says might +{shown}, the game's rule gives +{add}")
        if add != step and not cap and row == 2:
            bad.append(f"{ch} unit {ix} slot {s}: shown might +{add}, the difficulty wants +{step}")
        if add < step and not cap:
            bad.append(f"{ch} unit {ix} slot {s}: shown might +{add} is short of +{step}")
    return n, bad


def _tables():
    import gamedata as GD
    if GD.available():
        return None
    dispos = {}
    for d in GD._load("DisposUnit"):
        dispos.setdefault((W._chapter(d["file"]), R.ival(d["index"])), d)
    pc, pc_any = {}, {}
    for r in GD._load("PersonChapter"):
        pc.setdefault((os.path.basename(r["file"])[:4], r["label"]), r)
        pc_any.setdefault(r["label"], r)
    return {"dispos": dispos, "pc": pc, "pc_any": pc_any,
            "items": {r["label"]: r for r in GD._load("Item", only_first=True)},
            "refine": {R.ival(r["index"]): r for r in GD._load("ItemRefine")}}


@unittest.skipUnless(os.path.isdir(os.path.join(RUNS, "fates")), "no runs made by build/r63/might/mkruns.py")
class GameTables(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.t = _tables()
        except Exception:  # noqa: BLE001
            cls.t = None
        if cls.t is None:
            raise unittest.SkipTest("the game's tables are not available")

    def test_second_forge_table_is_one_per_level(self):
        rr = self.t["refine"][2]
        self.assertEqual([R.ival(rr[f"plus_{lvl}.might"]) for lvl in range(8)], list(range(8)))

    def test_fates_runs_shown_might(self):
        total = 0
        for rid in sorted(os.listdir(os.path.join(RUNS, "fates"))):
            n, bad = shown_check(os.path.join(RUNS, "fates", rid), self.t)
            self.assertEqual(bad, [], rid)
            total += n
        self.assertGreater(total, 0)


if __name__ == "__main__":
    unittest.main()
