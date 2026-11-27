# The weapon-rank line on the unit screen (Fates): which weapon icon goes on line N

**In plain words.** The unit screen lists a unit's weapon ranks, one line per weapon kind the unit
has used. For line N the game asks `GameInfoViewer::GetWeaponLevelKind` which weapon icon to draw
there. This batch (docs/tracks/REWRITE_ORDER3.md row 6, round 18) rewrites that one question. It
stores nothing: it only reads. The callers draw (`ViewerUnitStatus::DrawDetail`,
`HelpItemWeaponLv::Draw` and `::IsInside`, `castle::ShopBuyUnitInfoDrawer::Draw`) and stay in the
game. The rank-up window and `Unit::AddWeaponExp` (a writer) are not here.

Status 2026-11-17 (round 18 batch `weapon_level_view`), **UNVERIFIED** in the project's sense:

- **1 readable override** (`src/readable/weapon_level_view/weapon_level_view.c`, registry and target
  rows added): `weapon_level_view_kind`.

It gives the same answers as the game's own ARM code on made-up cases (two seeds), with the same
guest calls in the same order and the same unmapped reads; the planted bugs and the tier-2 result
are in section 4. Not yet in a live compare: a separate capture step rebuilds the capture library
and compares the override in real play. Nothing changes in the game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-17) [high unless marked]. No table values or game text are copied here.

---

## 1. What it decides

**`GameInfoViewer::GetWeaponLevelKind(const Unit*, int)`** (0x001D13A4, 38 words, a static
function: r0 the unit, r1 the line number).

```
seen = 0
for kind 0 .. 7:
  exp = Unit::GetWeaponExp(unit, kind sign-extended from its low byte)   (capped at the class limit)
  if exp <= 0 (signed): next kind (the line count does not move)
  if seen == line (full 32-bit compare, no range check):
    for sub 0 .. 20:
      record = ItemSubKind::Get(sub)
      if record's kind byte (+1, read signed) != kind: next sub
      if kind == 7 (stones) and Job::CanEquipFromSubKind(unit's class (Unit+0xA0), sub) == 0: next sub
      return sub (sign-extended from its low byte)
  seen = seen + 1
return -1
```

In plain words: the lines are the weapon kinds the unit has exp in, in kind order. Line N shows the
first sub-kind (the icon) of the N-th such kind; for dragonstones and beaststones the unit's class
must also be able to use that sub-kind. When the line is past the last one, the answer is -1.

Two details that matter for matching the game exactly:

- When line N's kind has no sub-kind that fits, the game does not stop: it counts the line, asks
  `GetWeaponExp` for every kind after it, never meets line N again, and returns -1. The readable
  code does the same (same calls in the same order).
- `GetWeaponExp` is an override of the triangle batch (docs/TRIANGLE.md) that gives up while
  `Unit::GetWeaponExpLimit`'s three one-time caches are cold; a give-up inside a guest call counts
  as a mismatch. It is the game's first call, before any read, so this function asks those three
  caches at entry and gives up while one is cold (the original then runs). That is exactly where
  the original would meet the cold cache: no early give-up.

## 2. Why it is a reader

The body has no store: the only memory it touches is its own stack (push/pop). The three calls
read too: `Unit::GetWeaponExp` and `ItemSubKind::Get` are readable overrides already (triangle
batch), `Job::CanEquipFromSubKind` is called as in src/readable/equip_use/equip_use.h. Not here,
and why:

- **They store** (writers): `Unit::AddWeaponExp` and the GrowSequence adders (docs/WEAPON_RANK.md 4).
- **The window**: `ProcWeaponExp::ShowWeaponLevelUp` and its drawer.
- **The callers**: they draw (icons, help boxes), so they stay in the game.

**Reach.** Any unit screen. `bt-ch8-options` opens Units (REWRITE_ORDER3 row 6); no chapter is added.

## 3. Checks

**Host differential test:** `python src/readable/weapon_level_view/tests/weapon_level_view_diff.py`
(weapon_rank_diff.py's method: the ARM interpreter src/readable/battle/tests/arm_mini.py on
extracted/text.bin against the readable C built with the host gcc; r0, unmapped reads and the whole
ordered list of guest calls with their argument registers; nested give-ups and guest writes
flagged). Every callee is answered by one table on both sides and listed: `Unit::GetWeaponExp`,
`ItemSubKind::Get`, `Job::CanEquipFromSubKind`. On the ARM side `GetWeaponExp` raises "cold guard"
while one of the limit caches is cold. The made-up states are random test values, never game data,
and often outside what the game uses: unmapped units, records and class pointers, negative and huge
exp, record kinds past 7 and negative, kinds with no record, line numbers negative, huge and past
the last line, class-test answers that are not 0/1.

The test's "torn" unit (its class pointer on an unmapped page) is 4-aligned, as every Unit in the
game. A word that straddles a page edge would be an unaligned load, which arm_mini.py models as the
older rotated read while the C reads the bytes in place; the game cannot meet it (fixed on
2026-11-17; the partial run of this batch had the unit 2 bytes off and showed 3 such false
mismatches).

**Planted bugs** (`--plant`, 22): the "ask the limit caches first" step dropped or with one cache
missing; the exp test removed, made `< 0`, unsigned, or `<= 1`; the line test `>=`; stopping at a
line whose kind has no sub-kind; the line count moved only for exp above 1; 7 kinds or 20
sub-kinds; the sub-kind search from 1; `ItemSubKind::Get` read directly instead of called; the
record's kind read from the wrong byte or compared with the line number; the stone kind 6; the
class test skipped or asked for every kind; the unit passed instead of its class; the class test's
answer read as a byte; the kind returned instead of the sub-kind; 0 instead of -1.

Not planted, because they cannot change an answer: the sign extension of the kind (0 .. 7) and of
the sub-kind (0 .. 20) passed to the callees and returned; reading the record's kind byte unsigned
instead of signed (a byte 0x80 .. 0xFF is unequal to 0 .. 7 either way).

**Tier 2** (`tools/readable/verify.py`): section 4.

## 4. Results (2026-11-17)

- Host test, seed 20261117, 300 cases, with `--plant`: **300 cases, 0 mismatches, 22/22 planted bugs
  caught**. Paths met: 95 "no such line", 126 sub-kinds found, 22 stone sub-kinds (6 after a refusal),
  41 "line reached but no sub-kind fits", 16 cold give-ups at entry; 65 cases with unmapped reads.
- Host test, seed 7, with `--plant`: **300 cases, 0 mismatches, 22/22 planted bugs caught**.
- Host test, seed 7, 1500 cases: **1,500 cases, 0 mismatches** (79 cold give-ups at entry).
- Tier 2 (`python tools/readable/verify.py --out build/readable/verify_weapon_level_view --only
  0x001D13A4`; the verify library built from the tree of that moment, 398 s): **1 GAVE-UP,
  0 MISMATCH** (`readable-verify: OK`). GAVE-UP: GetWeaponExpLimit's caches are cold in verify's
  made-up memory, so the readable code gave up at entry and only the fallback ran: proves nothing
  either way (as `unit_weapon_exp_for_job_intro` in docs/WEAPON_RANK.md). No classifier change.
- `python tools/readable/check.py --selftest`: readable OK (lint 287 rows 0 problems, 52 sources,
  host 146/146, capture 568/568, undo 554/554, self-test 27/27 broken inputs, verify pipeline 28/28).
  `python tools/harness/gen_stubs.py --check`: OK (252 overrides).
- Callers (every BL/BLX to 0x001D13A4 in extracted/text.bin, 4): HelpItemWeaponLv::Draw,
  HelpItemWeaponLv::IsInside, ViewerUnitStatus::DrawDetail, castle::ShopBuyUnitInfoDrawer::Draw.
