# What a staff does, and how far a weapon reaches (staff_range batch)

**In plain words.** Three new readers, all read-only: how many HP a healing staff restores, how likely a
status staff (one that hinders a foe, "interference rod" in the game's names) is to hit, and how well a
unit resists one. The fourth name of the plan row, the weapon's longest range, already had a reader
from the item batch, so nothing new was written for it. Nothing here stores into the game.

Plan row: docs/tracks/REWRITE_ORDER3.md batch 2. Code: `src/readable/staff_range/`. Host test:
`src/readable/staff_range/tests/staff_range_diff.py`. Status of all three: **unverified** (below
shadow-clean). They have not run in the game yet; a separate capture step records that.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only, 2026-11-16)
[high unless marked]. No table values or game text are copied here. Skill and flag names are given in
English only as a guess [low/med as marked].

## 1. Before starting: the five-argument call

The plan said: read round 11's five-argument guest call first, and stop if it still cannot pass the
extra stack word. It can. `guest_call5` (include/readable/fe_guest.h, docs/READABLE.md 17) stores the
fifth word at the first 8-byte aligned address at least 8 bytes below sp, lowers sp for the call and puts
it back. Its own test was run again before any code was written:
`python tools/readable/tests/guest_call5_test.py --plant`: **192/192 checks, 7/7 planted bugs caught**.
All three readers here pass their stat getters' fifth word (the rally kind, 0) with it.

## 2. The functions

| Readable name | Game function | What it decides |
|---|---|---|
| `unit_rod_heal_power` | `Unit::GetRodHealPower` 0x0052F008 | HP a staff heals (below) |
| `unit_status_staff_hit` | `Unit::GetInterferenceRodHit` 0x0053135C | the hit of a status staff (below) |
| `unit_status_staff_avoid` | `Unit::GetInterferenceRodAvoid` 0x00531D30 | how well a unit resists a status staff (below) |
| (none new) | `Unit::GetRangeO` 0x00534510 | already `unit_range_max` (item batch, src/readable/item/item_unit.c, docs/ITEM.md 4). It already passes its stack word with `guest_call5` (since round 11). Two overrides of one address cannot both be built, so it is not repeated here |

"The staff rank bonus" below: the unit's staff exp (Unit +0xEE, the staff byte of `weapon_exp`), capped
at `Unit::GetWeaponExpLimit(unit, staff)`, turned into a rank by `WeaponLevel::GetLevel`. The staff
kind's `WeaponBonus` row holds two signed bytes per rank, the might first and the hit second
(config/tables/WeaponBonus.csv).

**How much a staff heals** (`unit_rod_heal_power(unit, staff, healed unit)`):

```
heal = the staff's might (item record +0x1F, unsigned byte)
     + magic / 3, rounded toward zero      only when the staff has the cached item flag
                                           "effect + magic / 3" [med for the English]
     + the staff rank bonus (might byte)
then, when the healed unit is given (not 0) and has the cached skill: heal += heal / 2 (rounded down)
```

Magic is `Unit::GetPowImpl(unit, no item, with extras, with loss, rally kind 0)`. Which skill the
"half again" cache names was not looked up [low]. The parked AI-score batch read the same function
(docs/AI_SCORE.md 5); this batch read it again and it agrees.

**Hit of a status staff** (`unit_status_staff_hit(unit, staff)`):

```
no staff (0)   -> 0, before anything is asked
otherwise        the item's hit (unit::Item::GetHit) + the class's hit (Job +0x4C, signed 16-bit)
               + magic + skill (both with no item, extras and loss on, rally kind 0)
               + the staff rank bonus (hit byte)
               at least 0
```

**Resisting a status staff** (`unit_status_staff_avoid(unit, staff)`):

```
(3 x resistance + luck) / 2, rounded down, at least 0
```

Both stats are asked with the staff given, extras and loss on, rally kind 0. Note: the game never sets
r1 here, so the staff the caller passed goes straight on to `GetMdefImpl` and `GetLuckImpl`.

All sums wrap at 32 bits as the game's adds do (`fe_add32`). The tests feed huge stats on purpose.

## 3. Why these are readers

None of the three stores into the game. They read the unit, its class, the item record, two cached
values and the WeaponBonus row, and ask other readers. `GetRodHealPower` fills two one-time caches the
first time it runs (the skill number and the item flag, looked up by name). The readable code does not
fill them: it gives up while one is cold, before reading anything, and then the game's own code runs.
The only store the readable code makes is `guest_call5`'s fifth word in the dead stack below sp, the
same word the game's own call puts in the same place (docs/READABLE.md 17).

## 4. Guest calls and caches

Every callee is an older batch's readable override, called through the guest in the game's order with
the game's arguments (docs/DECISIONS.md F-018): `unit::Item::ToData` (item_to_data),
`unit::Item::GetHit` (item_hit), `Unit::IsEquipSkill` (unit_has_skill), `WeaponBonus::Get`,
`WeaponLevel::Get`, `WeaponLevel::GetLevel`, `Unit::GetWeaponExpLimit` (triangle batch), and the four
stat getters with `guest_call5`: `GetPowImpl` (magic), `GetTechImpl` (skill), `GetMdefImpl`
(resistance), `GetLuckImpl` (luck).

Caches asked first, so that no callee gives up inside a guest call (a nested give-up):
- heal: its own two (0x006D9918, 0x006D9914), the exp limit's three (triangle.h `S_ExpLimitGuardA..C`)
  and magic's (`unit_stat_caches_ready(STAT_MAG)`, battle batch). Magic is asked even for a staff
  without the flag. That is safe: it can only give up early, while a cache is cold.
- hit: magic, skill and the exp limit.
- avoid: resistance's three (sheet.h `S_ResGuard0..2`) and luck.

The addresses of the exp-limit and resistance guards are copied into staff_range.h with a note to keep
them in step with their owners' headers.

## 5. Checks

**Host differential test** (`python src/readable/staff_range/tests/staff_range_diff.py`, the method of
shop_price_diff.py with the stack-word and cache-guard additions of the parked AI-score test). The ARM
interpreter (src/readable/battle/tests/arm_mini.py) runs the original on extracted/text.bin. The
readable C is built with the host gcc. Both sides compare r0, the unmapped reads, and the ordered list
of guest calls with their argument registers, the stat getters with their fifth word (the word at sp).
Every callee is answered by one table on both sides. The exp limit and the four stat getters are
"guarded": reaching one while one of its guards is cold gives up on the ARM side and counts as a nested
give-up on the C side, so a missing cache check is caught. Guest writes and nested give-ups are flagged.
The made-up states are random test values, never game data, and often outside what the game uses:
unmapped units, items, records and rows, item 0, negative and huge stats, exp limits and ranks, class hits
of both signs, might bytes past 127, and skill numbers of both signs.

**Planted bugs** (`--plant`, 36): the rally kind, the loss flag, min/max of the exp cap, the rank
column, the rank step, a signed vs unsigned bonus byte, the call order of the rank pieces, the uncapped
exp, the exp byte's offset; for heal each cache check left out, the might read as signed or from the
wrong byte, magic / 4, magic asked with the staff, magic / 3 rounded down, only 32 bits of the item
flag, the "healed unit is 0" test left out, the skill read unsigned, a quarter instead of half, half
rounded toward zero; for hit the "no staff" answer left out, each cache check left out, the class hit
read unsigned, skill asked with the staff or not asked, the might byte instead of the hit byte, no
clamp; for avoid each cache check left out, resistance asked without the staff, the call order, 5 x
instead of 3 x, no halving, no clamp.

## 6. Results (2026-11-16)

| Run | Result |
|---|---|
| `guest_call5_test.py --plant` | 192/192 checks, 7/7 planted bugs caught |
| host test, seed 20261116, 300 per function | **900 cases, 0 mismatches** (69 where both gave up at a cold cache, 0 early give-ups) |
| the same with `--plant` (plants on seed 20261117) | 900 cases, 0 mismatches, **36/36 planted bugs caught** |
| host test, seed 7, `--plant` (plants on seed 8) | 900 cases, 0 mismatches, **36/36 planted bugs caught** |
| host test, seed 7, 1,500 per function | **4,500 cases, 0 mismatches** (381 both gave up at a cache, 7 early give-ups in heal) |

Parts of the original the cases ran: hit 51 of 51 words, avoid 20 of 20, heal 71 of 93. The 22 heal
words not run are the two cache-fill blocks after the guard routine (0x0052F034-0x0052F050 and
0x0052F07C-0x0052F0B0). The readable code never runs them: it gives up there and the game's code runs.
Paths met on seed 7 (1,500 each): heal with and without the magic third, with and without "half again",
unmapped records and reads; hit "no staff" 122, clamped to 0 248, above 0 973; avoid clamped to 0 180,
above 0 1,223.

The existing range reader was checked too: `python src/readable/item/tests/item_diff.py --only
unit_range_max`: 300 cases, 0 mismatches.

Tier 2, check.py and gen_stubs: see section 8.

## 7. Where the game reaches them

- `GetRodHealPower`: when a staff heals on the map, and the AI's "entrust heal" score (docs/AI_SCORE.md 5).
- `GetInterferenceRodHit` / `Avoid`: when a status staff is used, and the forecast for one.

Per the plan, no map is added to find them. Which recordings already on disk reach them was not checked
here (this batch runs no robot games). The capture step says it; a reader no recording reaches is
"not here" (never met in real play).

## 8. Gates

- `python tools/harness/gen_stubs.py --check`: OK (245 overrides, 60 guard users, on the real tree with the other batch's row in). The heal row carries the
  guard tag ("guard user (calls 0x00302C6C)"); hit and avoid call no guard routine themselves.
- Another batch was being written in the same tree at the same time (src/readable/equip_use/, its
  override not yet in the registry). While it is unregistered the whole-tree lint and staging refuse
  the tree, so check.py and tier 2 were run on a copy of tools/, include/, src/ and config/ under
  build/ without that one folder (everything else identical, this batch's registry rows included).
- `python tools/readable/check.py --selftest` (on that copy): **readable: OK**. Lint 279 rows, 0
  problems; 48 sources and 48 staged files compile; host 146/146, capture 568/568, undo 554/554;
  self-test 27/27 broken inputs; verify pipeline 28/28. (A first try from a copy under the user's temp
  folder failed 26 capture-test checks; the same capture test run alone in the real tree passed
  568/568, so that was the location, not the code.) Later, once the other batch had registered its
  row, `check.py --selftest` on the real tree: **readable: OK** (lint 280 rows, 0 problems; 49 sources
  and 49 staged files; host 146/146, capture 568/568, undo 554/554; 27/27; 28/28).
- Tier 2 (`python tools/readable/verify.py --out build/readable/v --only 0x0052F008,0x0053135C,0x00531D30`
  on that copy; library build 334 s): **0 MISMATCH, 3 GAVE-UP** (`readable-verify: OK (3 GAVE-UP)`).
  GAVE-UP means verify's pristine memory has the one-time caches cold, so the readable code gave up and
  only the fallback ran: that proves nothing either way (as for the other cache users). In the shadow
  pass (the original runs first and fills the caches) hit and avoid ran their readable body and gave
  the game's r0; heal logged no comparison. The classifier was not changed.

## 9. Not in this batch

- `Unit::GetSimplePower` and any damage switch (the plan says so).
- `Unit::GetRangeO`: already a reader (section 2).
- The parked AI-score batch's copy of `GetRodHealPower` (src/readable/ai_score/ai_score_heal.c.parked).
  If that batch is ever unparked, its heal body must be dropped, or the two overrides of 0x0052F008 will
  not link. Its test (ai_score_diff.py, not in check_all) builds every source of src/readable/ plus its
  parked copy, so it no longer links while both exist. That test is parked with its batch.
