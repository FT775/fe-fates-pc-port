# Weapon rank, the part not already done (Fates): the script's rank question, the class showcase's weapon exp, and the weapon exp a unit starts with

**In plain words.** The triangle batch (docs/TRIANGLE.md) already rewrote how a unit's weapon exp
turns into a rank (`WeaponLevel::Get`, `WeaponLevel::GetLevel`) and how much exp a unit holds and may
hold (`Unit::GetWeaponExp`, `Unit::GetWeaponExpLimit`). This batch (docs/tracks/REWRITE_ORDER2.md
batch 5) takes what was left that only reads: the rank an event script asks for, the weapon exp the
castle's class showcase shows, and the weapon exp a new unit starts with. Nothing that adds exp is
here: the three adders store, so they wait for the writer gate.

Status 2026-11-16 (round 12 batch `weapon_rank`), all **UNVERIFIED** in the project's sense:

- **2 readable overrides** (`src/readable/weapon_rank/weapon_rank.c`, registry and target rows added):
  `script_unit_weapon_rank`, `unit_weapon_exp_for_job_intro`.
- **1 helper** (F-017): `unit_first_weapon_exp`, the pure part of `Unit::CaclulateFirstWeaponExp`,
  which stores. It returns what the game would store and writes nothing.

Each gives the same answers as the game's own ARM code on made-up cases (two seeds), with the same
guest calls in the same order and the same unmapped reads; the planted bugs and the tier-2 result
are in section 6. Not yet in a live compare: a separate capture step rebuilds the capture library
and compares the overrides in real play. Nothing changes in the game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-16) [high unless marked]. No table values or game text are copied here.

---

## 1. The script's "weapon rank of unit N" (override)

**`anonymous_namespace::UnitGetWeaponLevel`** (0x003AC430, `script_unit_weapon_rank`), an event
script command. Arguments: the script context (not read), a unit's pool number, a weapon kind, a
bool.

```
pool number not 1 .. 250                    -> 0
unit = UnitPool::Get(number); its force's type is 9 -> 0   [low for what force 9 is; the other
                                                            script readers refuse it the same way]
unit = UnitPool::Get(number)                (the game asks twice)
exp  = the stored byte Unit.weapon_exp[kind]            when the bool is 0 (not capped)
       Unit::GetWeaponExp(unit, kind's low byte, sign-extended)  otherwise (capped at the class limit)
rank = WeaponLevel::GetLevel(WeaponLevel::Get(), exp)   0 = S .. 5 = E, 6 = none
```

The kind is not range-checked, as in the game. The last step is a tail branch (`B`) in the game,
not a call. The tier-1 library does not copy GetLevel's code into this function; its generated code
calls `override_0x005090A4` there (checked in build/harness/lib, code130.c, per docs/MOVE.md 9). So
the override is entered, and the readable code makes it a guest call; the host test lists it.

With the bool set, GetWeaponExp's override reads GetWeaponExpLimit's three one-time caches and gives
up while one is cold. A give-up inside a guest call (nested) counts as a mismatch, so this function
asks those three caches first, right after the pool-number test and before reading anything, and
gives up itself (the original then runs: always safe). That can be earlier than the game would
reach them (for a force-9 unit the game returns 0 without asking); the host test allows exactly
that early give-up and no other.

**Reach.** No BL calls it; only a chapter script can. A plain-text search of extracted/romfs/Scripts
for the command name found nothing (the scripts may name it in a form a text search cannot see)
[med]. So no named route is known to meet it; the capture step will say.

## 2. The class showcase's weapon exp (override)

**`Unit::GetWeaponExpForJobIntro`** (0x00532060, `unit_weapon_exp_for_job_intro`). Its only caller is
`ProcJobIntro::Persistent`, the castle's class showcase (the castle file JobIntro, docs/CASTLE.md),
which asks it for each kind next to the limit and draws both ranks.

```
kind 7 (stones) and the unit, its Person or its class carries the flag bit -> 0
otherwise the stored byte Unit.weapon_exp[kind]   (NOT capped by the class limit)
```

The flag bit is a one-time cache (guard 0x006D97BC, mask 0x006D9AA0). The game looks it up by name,
and the name is the same one GetWeaponExpLimit uses for its stone rule (the two strings are equal
byte for byte; not copied here) [high for "same name", low for what the flag means]. The readable
code gives up while the cache is cold, before reading anything. The kind is compared as a full word
and not range-checked.

**Reach.** Only the class showcase. No named route opens it [med]; the capture step will say.

## 3. The weapon exp a unit starts with (helper)

**`Unit::CaclulateFirstWeaponExp`** (0x00531C5C, the game's spelling) stores eight bytes through its
pointer. `Unit::CreateImpl` passes the new unit's own `Unit.weapon_exp`; `Unit::Handover` passes a
buffer on its stack and then raises the new unit's exp by the difference. Because it stores into
the unit, it is a **writer** and gets no override. The helper `unit_first_weapon_exp` runs the whole
function and puts the eight bytes into host memory instead:

```
difficulty = GameUserData.difficulty                      (read once)
for each kind 0 .. 7:
  limit = Unit::GetWeaponExpLimit(unit, kind), at least 1
  floor = 1
  if the Person's unit_kind is not 1 or 3, and GetWeaponExpLimit(unit, kind) (asked again) > 0:
      hard (1):    floor = WeaponLevel threshold[3]  (the rank C threshold)
      lunatic (2): floor = WeaponLevel threshold[0]  (the rank S threshold)
      floor at most limit
  own = the Person's weapon_exp[kind]
  start = floor when floor > own, else own at most limit
```

In plain words: a unit starts with its Person's weapon exp, cut down to what its class allows. On
hard and lunatic, units whose Person's unit_kind is not 1 or 3 [low for which units those are] get
at least rank C (hard) or the class's highest allowed exp up to rank S (lunatic) in every kind the
class can use. All comparisons are signed, as in the game. GetWeaponExpLimit and WeaponLevel::Get
are called through the guest in the game's order (once or twice, and once per floor, per kind); the
helper asks GetWeaponExpLimit's three caches first and gives up while one is cold.

A mod that changes starting ranks can now be checked against this helper. It cannot change them:
that is the store, which waits for the writer gate.

## 4. Not here, and why

- **They store** (writers): `Unit::AddWeaponExp` (0x003D52AC), `GrowSequence::GainWeaponExp`
  (0x001B40C8), `GrowSequence::DualGainWeaponExp` (0x001B4474), `GrowSequence::WeaponLevelUp`, and the
  event version `event::Informal::...::ProcWeaponExp::GainWeaponExp`. `CaclulateFirstWeaponExp` only
  as the helper above.
- **The window**: `ProcWeaponExp::ShowWeaponLevelUp`, `WeaponLevelDrawer::Draw`, the level-up sound.
- **Already done** (triangle batch): `WeaponLevel::Get`, `GetLevel`, `Unit::GetWeaponExp`,
  `GetWeaponExpLimit`.
- **Not looked at further**: `GameInfoViewer::GetWeaponLevelKind` (a display helper; not in the plan
  row).

## 5. Checks

**Host differential test:** `python src/readable/weapon_rank/tests/weapon_rank_diff.py` (battle2_diff.py's
method: the ARM interpreter src/readable/battle/tests/arm_mini.py on extracted/text.bin against the
readable C built with the host gcc; r0, unmapped reads and the whole ordered list of guest calls
with their argument registers; nested give-ups and guest writes flagged). Every callee is answered
by one table on both sides and listed: UnitPool::Get, GameUserData::Get, WeaponLevel::Get,
WeaponLevel::GetLevel, Unit::GetWeaponExp, Unit::GetWeaponExpLimit. On the ARM side the last two
raise "cold guard" while one of GetWeaponExpLimit's caches is cold (the game's code would reach the
guard routine inside the call), so the readable code must give up first. The tail branch into
GetLevel is listed as a call (section 1). The helper runs through a test-only entry of the generated
driver (never a marker in src/readable/); the ARM function runs whole and the eight bytes it stores
are the expected result, folded into one number (FNV-1a) on both sides. The made-up states are
random test values, never game data, and often outside what the game uses (unmapped units and
Persons, a unit whose exp bytes run onto an unmapped page, pool numbers 0, 251 and negative, kinds
past 7 and negative, bools that are not 0/1, limits 0, negative and huge, difficulties 3 and up,
thresholds out of order). The test prints which paths the cases met.

**Planted bugs** (`--plant`, 23): every boundary and branch of the three functions, the "ask the
limit caches first" step and an over-eager version of it, each guest call dropped or replaced by a
direct read, the kind's sign extension, a signed instead of unsigned byte, the hard/lunatic
thresholds swapped, each cap removed.

**Tier 2** (`tools/readable/verify.py`): section 6.

## 6. Results (2026-11-16)

- Host test, seed 20261116, 300 cases per function, with `--plant`: **900 cases, 0 mismatches,
  23/23 planted bugs caught** (plants on 300 cases per function of seed 20261117; about 75 s).
  Paths met: the script reader 110 stored-byte ranks, 96 capped ranks, 39 refused pool numbers,
  32 force-9 units, 23 cold give-ups and 1 allowed early give-up; the showcase 85 stone cases
  (60 of them 0), 205 other kinds, 10 cold; the helper every difficulty 0 .. 3 and others, with
  and without unit_kind 1/3, 42 cold.
- Host test, seed 7, with `--plant`: **900 cases, 0 mismatches, 23/23 planted bugs caught**.
- Host test, seed 7, 1500 cases per function: **4,500 cases, 0 mismatches** (23 allowed early
  give-ups).
- Tier 2 (`python tools/readable/verify.py --out build/readable/verify_weapon_rank --only
  0x003AC430,0x00532060`; the verify library built from the tree of that moment, 404 s):
  **1 ABI-ONLY, 1 GAVE-UP, 0 MISMATCH** (`readable-verify: OK`). ABI-ONLY: `script_unit_weapon_rank`
  (flags and dead stack only). GAVE-UP: `unit_weapon_exp_for_job_intro` (its cache is cold in verify's
  made-up memory: proves nothing either way). No classifier change.
- `python tools/readable/check.py --selftest`: readable OK (lint 273 rows 0 problems, 45 sources,
  host 146/146, capture 568/568, undo 554/554, self-test 27/27 broken inputs, verify pipeline 28/28).
  `python tools/harness/gen_stubs.py --check`: OK (236 overrides at the time of the run).
