# Readable code for Fates: what is ready, what waits for the engine

**In plain words.** The engine (Zakuro + 3dsrecomp) runs Fates by translating its ARM code into
C automatically. That C works but nobody can read it. 3dsrecomp lets us replace any single game
function with one we write by hand: a short, named C function such as `unit_next()` or
`force_is_allied()`. This layer is where those live. Each one first runs in **shadow mode** (the
game keeps its own answer, ours runs next to it and every disagreement is logged), and only a
function that has agreed for a long time is switched on for real.

The design, the rules and the reasons are the Awakening port's (its docs/READABLE.md, D-013). This
file says what carried over to Fates, what is new, and what is still blocked. Confidence tags:
**[high]** checked by a script or read in the code, **[med]** strong indirect evidence, **[low]** a
guess.

Status 2026-11-10: tooling ported and tested; a **pilot of 12 overrides + 1 helper**, all
**UNVERIFIED** (they compile, and a host test of 146 checks passes on invented records). Nothing
has run against the real game: that needs the engine built (owner's OK).

```bash
python tools/readable/check.py --selftest     # lint + compile + host/capture/undo tests + broken inputs
python tools/readable/gen_structs.py gen      # guest structs and per-game constants from config/
python tools/readable/stage.py                # self-contained override files in build/readable/overrides/
python tools/readable/symmap.py find "^Unit::Get"      # the game's own function names
python tools/readable/xmap.py                 # Awakening readable functions found in Fates (byte match)
python tools/readable/candidates.py --summary # the worklist, grouped by system
python tools/readable/gameaddr.py --check     # per-game addresses agree with the symbol map
python tools/readable/verify.py --selftest    # tier-2 pipeline against a fake 3dsrecomp
```

---

## 1. The big difference from Awakening: real names

Fates ships a debug symbol map in its RomFS (`debug/name.StackTrace` + `debug/addr.StackTrace`):
26,122 demangled C++ names such as `Unit::GetNext(unsigned int) const` [high].
`tools/readable/symmap.py` reads it (format: a blob of NUL-terminated names, and (u32 address,
u32 name offset) pairs). Two facts that matter:

- Thumb functions are **not** marked by bit 0. A 2-aligned address is surely Thumb, but a
  4-aligned one can be Thumb too (`__cxa_guard_acquire` at 0x00302C6C is) [high]. Ask the code
  analysis (`build/cache/analysis.json`, or the `mode` column of config/functions.csv) for the
  instruction set.
- Names are labels: tracked files may hold them (addresses + names), never code or data.

So in Fates a readable function starts with a known name and signature; the work is reading the
body, not guessing what it is for.

## 2. Files

| What | Where | Tracked |
|---|---|---|
| Readable sources, one file per topic | `src/readable/<system>/*.c` | yes (our code) |
| Runtime, capture mode, undo log (game-agnostic) | `src/readable/core/{runtime,capture,undo}.c` | yes (from the Awakening port) |
| Headers | `include/readable/fe*.h` | yes |
| Generated headers | `include/readable/generated/fe_{structs,globals,game}.h` | yes (layouts and addresses only) |
| Registry of written functions | `config/readable/functions.csv` | yes |
| Runtime struct layouts (Unit, Force, ...) | `config/readable/structs.csv`, `structs/<Name>.csv` | yes |
| Hand-found globals | `config/readable/globals.csv` | yes |
| Per-game named addresses (guard, operator new, ...) | `config/readable/addresses.json` | yes |
| Awakening -> Fates byte matches | `config/readable/xmap_reference.csv` | yes |
| Worklist | `config/readable/candidates.csv` | yes |
| Extras address maps (per game) | `config/readable/extras.json` | yes |
| Staged files, test executables | `build/readable/` | no |

`fe_game.h` is new for Fates: per-game constants of the C side (title id, the one-time guard
routine and its override literal), generated from config/game.json and addresses.json.

## 3. The pilot (12 overrides, 1 helper) [high for the reads, UNVERIFIED as code]

Chosen because each is small, pure (no guest writes, no guest calls, no one-time cache, so none
can give up) and either byte-identical to an Awakening function the Awakening port already
rewrote, or the same code shape with moved offsets. Every read below was re-read in the Fates code
on 2026-11-10 (objdump of extracted/text.bin, read only).

| Address | Fates name (symbol map) | Readable | Source | Awakening analog (xmap) |
|---|---|---|---|---|
| 0x00543DF4 | AIValue::IsArgument | ai_value_is_argument | ai/ai_value.c | ai_arg_is_variable (exact) |
| 0x00543E0C | AIValue::GetArgument | ai_value_argument_address | ai/ai_value.c | ai_variable_address (imm; Unit+0x6A) |
| 0x00543E28 | AIValue::IsMax | ai_value_is_max | ai/ai_value.c | ai_arg_is_minus_2 (exact) |
| 0x00543E44 | AIValue::IsSkip | ai_value_is_skip | ai/ai_value.c | ai_arg_is_unset (exact) |
| 0x00543E58 | AIValue::IsSignal | ai_value_is_signal | ai/ai_value.c | ai_arg_is_negative (exact) |
| 0x00543E6C | AIValue::IsDefault | ai_value_is_default | ai/ai_value.c | ai_arg_is_any (exact) |
| 0x004C8584 | AIThink::IsMoveOver() | ai_think_is_move_over | ai/ai_think.c | ai_has_forced_unit (imm) |
| 0x004C8544 | AIThink::IsMoveOver(Unit*,int,int) | ai_think_is_move_over_at | ai/ai_think.c | ai_forced_unit_stands_at (imm) |
| 0x00508584 | FlagManager::Get(int) | flag_manager_get | event/flags.c | flagset_test (exact) |
| 0x0053C3E0 | Force::IsAllied | force_is_allied | unit/forces.c | sides_are_allied (exact) |
| 0x004F62CC | UnitPool::GetFirst | unit_pool_first | unit/forces.c | forces_first_unit (imm) |
| 0x00533208 | Unit::GetNext | unit_next | unit/forces.c | forces_next_unit (imm) |
| 0x004F6310 | UnitPool::GetForce (helper) | unit_pool_force | unit/forces.c | - |

The symbol map also names what Awakening could only guess: the special AI argument values are
Default (-1), Max (-2), Skip (-3) and Argument (-4..-7) [high names, from the map].

Struct fields found on the way (config/readable/structs/): Unit.next +0x14, Unit.ai_arguments
+0x6A (s16[16]), Unit.force +0xA4, Unit.map_x/map_y +0xF4/+0xF5 (s8); Force (12 bytes)
.first_unit +0x0, .type +0x8; FlagManager.bits +0xC; UnitPool.forces +0x4 [all high]. Globals:
G_UnitPool 0x006D9F40 [high], G_AIThinkHolder 0x006D0EBC [med: what object it holds is not
named]. The Unit record size is not known yet.

## 4. Awakening -> Fates byte matches (tools/readable/xmap.py)

The scout's method (scout/code-mapping.txt), now a tool with a selftest. Each function of the
Awakening port's registry (its config/readable/functions.csv, read only) is compared word by word
with every Fates ARM function: **exact** = equal after wildcarding branch offsets and literal-pool
words; **imm** = also wildcarding load/store offsets and ALU immediates. Unique hits get a
confidence: high (exact, at least 5 words), medium (imm, at least 8 words), low (anything else, or
two Awakening rows on one Fates function).

Result 2026-11-10, 296 Awakening rows: 16 high, 10 medium, 6 low, 264 none or ambiguous [high
for the counts]. The scout counted 27 "byte-level confident"; the tool's 26 high+medium are the
same set less one that now collides. Lows are mostly wrong (e.g. two Awakening option getters
landing on one `GameUserGlobalData::IsUsedJapaneseVoice`, a 5-word getter landing in Pia
networking): always read the Fates name before trusting a low row. All the big stat getters and
battle formulas have no counterpart: they were rewritten in Fates.

## 5. The worklist (tools/readable/candidates.py -> config/readable/candidates.csv)

Every game function in the symbol map whose name puts it in a game system, grouped into batches in
the order the Awakening port worked (data getters, unit, battle, map, AI, events, save), then the
Fates-only systems. Library code (nn::, nw::, std::, NEX/Pia, live2d::, the RVCT runtime) is left
out. Each row: address, a suggested C name, the demangled name, batch, system, kind (getter /
query / mutator / ctor / dtor / serialize / other), size in words, the Awakening analog if any, and
a priority (1 = small const getters of core records and byte-matched analogs).

Counts 2026-11-10: 16,312 rows; priority 1: 241. By batch: B1 data/item/skill 162, B2 unit 331,
B3 battle 114 (map::BattleCalculator, map::BattleInfo, Unit::GetHit/GetAvoid/GetCritical/...),
B4 map 1,717, B5 ai 186, B6 event 748, B7 save 91; Fates-only: F1 castle 3,005, F2 dual/pair-up
147, F3 dragon veins 19, F4 Live2D game side 185, F5 amiibo 23; X (ui and other) 9,584.
The classification is by name only [med]: check a row's code before trusting its system or kind.

Suggested next batches, in order: B1 getters of Person/Job/Item/EquipSkill (the record layouts
come from config/tables/, the tables area's work), then the B3 Unit::Get* battle numbers
(Unit::GetHit(int,bool), GetAvoid, GetCritical, GetAttack: 13-15 words each, they call the
heavier *Impl functions), then map::BattleCalculator.

## 6. Checks (tools/readable/check.py) [high]

Unchanged from the Awakening port except where noted:

- Lint: registry rows (address = a function start of config/functions.csv; **new**: when that
  file is missing, the analysis cache and the symbol map stand in), markers, FE_ENTRY, no markers
  in headers, no pasted disassembly, UNVERIFIED notes, FE_TRACKED large enough, generated headers
  up to date.
- Compile: every source with `-std=c11 -Wall -Wextra -Wpedantic -Werror` against the stand-in
  header, every staged file alone, then three test programs:
  - `tools/readable/tests/host_test.c` (**rewritten for Fates**: the struct offsets, the six
    AIValue tests over the special values, AIThink with the unit not read without a target,
    FlagManager with a negative index, forces and unit lists, and the override glue in readable,
    shadow-match, shadow-mismatch and original modes): 146/146.
  - `capture_test.c` (565/565) and `undo_test.c` (554/554): game-agnostic, unchanged.
- `--selftest`: 22 broken inputs (now edits of the Fates pilot, plus a Thumb registry address),
  15 verify-log samples, 52 verdict combinations, 7 entry-table cases, and verify.py's pipeline
  against a fake 3dsrecomp (28/28). All pass.

## 7. What needs the engine built first (owner's OK)

None of this has run, and none of it can until 3dsrecomp is built (`python tools/engine/engine.py
build 3dsrecomp-verify`, not run by this session):

1. **Tier 2** (`tools/readable/verify.py --rom <cci>`): build the library with the overrides and
   run `3dsrecomp verify` once per override. Expected: the pilot's pure functions come back
   CLEAN or ABI-ONLY; `--update-status` writes the result into the registry.
2. **Shadow / tier 4**: the capture library and the harness (docs/HARNESS.md).
3. The library name is `<title id>.dll` = `0004000000179800.dll` (config/game.json).

`python tools/readable/stage.py --commands "<path to the .cci>"` prints the exact commands.

## 8. Known gaps [high that they are gaps]

- The Unit record size and most fields are unknown; struct layouts grow only with code evidence.
- Fates keeps a few RVCT runtime functions in Thumb; readable overrides are ARM-only (lint refuses
  odd addresses). No game function in the worklist is Thumb.
- Fates' one-time guard is Thumb: guard caches (`fe_static_ready`) work the same, but a probe on
  the guard must use the odd literal 0x00302C6D (docs/HARNESS.md 3).
- `include/readable/generated/fe_structs.h` also carries the table layouts of config/tables/ (the
  tables area's work). When those change, `gen_structs.py gen` must be rerun or check.py says
  "out of date".

## 9. Stances: the first rewrite target (battle area, 2026-11-11)

The Attack/Guard stance system, agreed with Grok as the first rewrite target. How the system
works, the cross-check against docs/tracks/rules/RULES.md (the follow-up's half damage is now
confirmed from code) and the full table of what waits: docs/STANCES.md.

**Written** (`src/readable/battle/`, all **UNVERIFIED**, registry rows in
config/readable/functions.csv):

- 9 overrides, all readers: the stance bonus lookups (`PersonEnhanceDual/Double::GetTotal`,
  `::GetEdit`, `Unit::GetDualSupport`, `Unit::GetDoubleCapability`,
  `Unit::GetDoubleMovePower`), who may pair (`Unit::CanDoubleOn`) and whether stances are on
  for an army (`map::Situation::CanDual`). Two of them read a one-time cache and give up while
  it is cold; their targets.csv rows carry the guard tag.
- 5 helpers: the pure part of functions that also write (`BattleInfo::CalculateDual`, the
  gauge and block code of `BattleCalculator::CalculateAttackSingle`, the turn-start gauge
  step, the last step of `Side::GetSimplePower`). They return what the game would store and
  write nothing; they become writers only after H6/H8 are green on Fates.
- `stances.h` sits next to the sources (the battle area owns only that folder); the
  integrate step may move its declarations into `fe_functions.h` / `fe_callees.h`.
- New layouts: Unit (+0x0 private_flags, +0x8 state_flags, +0x9C person, +0xA0 job, +0xA8
  pair_partner, +0xB0 edit, +0xB4 family, +0x135 guard_gauge), UnitEdit, UnitFamily,
  Situation, GameUserData, BattleSide, BattleInfo, BattleCalculator; globals G_GameUserData,
  G_PersonalityTable, G_Situation.

**New test kind: original ARM against readable C on the host.**
`python src/readable/battle/tests/stance_diff.py` runs the game's own code from
extracted/text.bin in a small ARM interpreter (`src/readable/battle/tests/arm_mini.py`,
written for this: the project had none and Unicorn is not installed) and the readable
function on the same made-up memory, and compares. Guest calls the readable code still makes
answer from one random table on both sides. Result: 14 functions, 5,600 cases (and 21,000
with another seed), 0 mismatches; 13 of 13 planted bugs caught. This is stronger than the
host_test.c smoke tests (it compares with the original) and weaker than tier 2 (made-up
states, an interpreter we wrote). It does not change any registry status. It runs in `check_all.py`
as `stance-diff` (and `stance-diff-long` with `--slow`).

## 10. Weapon triangle and weapon ranks: the second rewrite target (battle area, 2026-11-11)

Grok's next agreed target (docs/tracks/REWRITE_ORDER.md, batch 1). How the triangle and the
ranks work, the cross-check against docs/tracks/rules/RULES.md (one line refuted as worded: the
rank that scales the bonus is the advantaged unit's, in both directions) and what waits:
docs/TRIANGLE.md.

**Written** (`src/readable/battle/triangle.h`, `triangle_tables.c`, `triangle_battle.c`, all
**UNVERIFIED**, registry rows in config/readable/functions.csv):

- 7 overrides, all readers: the table getters `ItemSubKind::Get`, `WeaponBonus::Get`,
  `WeaponLevel::Get`, `WeaponInteract::Get`, the rank `WeaponLevel::GetLevel`, and the weapon
  exp `Unit::GetWeaponExpLimit` (three one-time caches: gives up while any is cold; its
  targets.csv row carries the guard tag) and `Unit::GetWeaponExp` (gives up with it).
- 6 helpers: the weapon-rank part of `Unit::GetAttack` / `Unit::GetHit`, the triangle cell and
  the reversal of `map::BattleInfo::CalculateDetail` (one cache), and the triangle part of
  `Side::CalculateDetailHit` / `CalculateDetailAttack` (with the bool they pass to
  GetHit/GetAttack: 0 at a disadvantage). They return what the game would store and write
  nothing (F-017).
- The one guest call left is `unit::Item::ToData` (a reader).
- New layouts: Unit +0xE8 weapon_exp, BattleSide +0x10 item and +0x14 triangle; globals
  G_ItemSubKindTable, G_WeaponLevel, G_WeaponBonus, G_WeaponInteract.

**Host differential test:** `python src/readable/battle/tests/triangle_diff.py` (the stance
test's method and ARM interpreter; for the two Side regions `Unit::GetHit/GetAttack` are stubs
and their bool argument is compared). 13 functions, 5,200 cases (and 19,500 with seed 7), 0
mismatches; `--plant` plants 18 bugs one at a time, 18 of 18 caught. `check_all.py` rows
`triangle-diff` (with `--plant`) and `triangle-diff-long` (`--slow`).

**Tier 2** (2026-11-11, all 28 overrides): 0 mismatches. Triangle: CLEAN `weapon_level_record`,
`weapon_interact_record`; ABI-ONLY `item_subkind_record`, `weapon_bonus_record`,
`weapon_rank_of_exp`; GAVE-UP `unit_weapon_exp_limit`, `unit_weapon_exp` (verify's caches are
cold); none UNSAMPLED. Details: docs/TRIANGLE.md section 7.

## 11. Dragon veins: the third rewrite target (map area, 2026-11-11)

Grok's batch 2 (docs/tracks/REWRITE_ORDER.md): one vein effect plus the read-only parts the
`vein_highlight` display option needs. How veins work (a vein and its effect are one event of
the chapter's script; who may use one is a personal flag bit; there is no per-turn flag), the
cross-check against docs/tracks/rules/RULES.md and what waits: docs/VEINS.md.

**Written** (`src/readable/map/veins.h`, `vein_tricks.c`, `vein_units.c`, `vein_effect.c`, all
**UNVERIFIED**, registry rows in config/readable/functions.csv):

- 7 overrides, all readers: "is this tile a vein" (`AIThink::GetTrickFromAccess` with type 11,
  `map::trick::Data::IsAccess`), "may this unit use a vein" (`Unit::CanDragonVein`,
  `Person::IsDownload`, the script's `UnitCanDragonVein`, the command's
  `TransformTerrain::BuildAttribute`) and "has this vein been used" (the script's `TrickTst`).
  Two one-time caches: their functions give up while cold (guard tag in targets.csv).
- 1 helper: the ground-change effect, i.e. the tiles `map::trick::Data::SetDeploy` marks for a vein
  (the region list `PositionEnumerator`, the type-12 regions, the terrain attribute bits). It
  returns the marks and writes nothing (F-017).
- No guest call at all. New layouts: TrickData, Trick, MapImage, MapDeploy, MapMind,
  PersonBlockNode, PersonBlock, UnitPool.units, the Unit size 0x140; globals G_Trick, G_MapImage,
  G_Deploy, G_MapMind, G_TerrainHeader, G_PersonBlocks.

**Host differential test:** `python src/readable/map/tests/vein_diff.py` (the stance test's method
and ARM interpreter; for the helper the whole of SetDeploy runs as ARM code and a 3 KiB window
around its bitmap is compared). Inputs reach outside the usual ranges on purpose. 8 functions,
3,200 cases (and 12,000 with seed 7), 0 mismatches; `--plant` plants 35 bugs one at a time, 35 of
35 caught. `check_all.py` rows `vein-diff` (with `--plant`) and `vein-diff-long` (`--slow`).

**Tier 2** (2026-11-11, all 35 overrides): 0 mismatches. Veins: ABI-ONLY `trick_is_access`,
`trick_at_access`, `script_trick_test`, `script_unit_can_dragon_vein`; GAVE-UP (cold caches)
`unit_can_dragon_vein`, `person_is_download`, `vein_command_attribute`. The first run caught two
readable functions reading more unmapped memory than the game (fixed; docs/VEINS.md section 8).

## 12. Battle formulas: the fourth rewrite target (battle area, 2026-11-11)

Grok's batch 3 (docs/tracks/REWRITE_ORDER.md: damage, hit, crit), which Grok could not start
because the formula functions were not named. They are named now, with the call graph and every
formula in plain words, cross-checked against the owner's prologue Ryoma screen (Atk 29, Crit 20,
Hit 110, Avo 53: all four reproduced exactly): docs/FORMULAS.md. Its section 8 has proposed lines
for the [gap] in docs/tracks/rules/RULES.md (Grok's file, not edited here).

**Written** (`src/readable/battle/formulas.h`, `formula_stats.c`, `formula_unit.c`,
`formula_forecast.c`, all **UNVERIFIED**, registry rows in config/readable/functions.csv):

- 21 overrides, all readers: the five stat getters the formulas use (`Unit::GetStrImpl`,
  `GetPowImpl`, `GetTechImpl`, `GetQuickImpl`, `GetLuckImpl`: one shared body driven by a
  per-stat table; the fifth argument, the rally kind, is read from the guest stack) and
  `Unit::GetItemIndexEquipped`; the unit's battle numbers `Unit::GetAttack`, `GetHit`,
  `GetAvoid`, `GetCritical`, `GetSecure` (critical avoid), `GetContinuous` / `GetUnderContinuous`
  (the follow-up speeds) with their slot forms and `GetAttackForTerrain`; the forecast's
  `Side::GetSimpleHit` and `Side::GetSimpleTimes` (strikes: 2 at attack speed >= defense speed + 5).
  Twelve of them read one-time caches and give up while one is cold (guard tags in targets.csv).
- 2 helpers (F-017: the game functions store): the critical / critical avoid / speed part of
  `Side::CalculateDetail` and the shown critical of `BattleInfo::CalculateSimple`.
- `unit_attack` / `unit_hit` compute the weapon-rank bonus from the triangle batch's readable
  pieces with the game's three weapon-kind lookups (tier 2 counts unmapped reads); since
  2026-11-12 (formula fix) each lookup calls `ItemSubKind::Get` through the guest as the game does
  (the live compare counts callee calls, F-018). The triangle helper rows at the same two addresses
  were merged into the new override rows.
- Guest calls left (readers, or one-time cache fills, which are idempotent): `Unit::GetLimit`,
  `unit::Edit::GetCapability`, `Unit::GetDoubleCapability` (its readable override is reached
  through guest_call when built), `Unit::IsEquipSkill`, `GetEnhanceHave`, `unit::Item::ToData` /
  `GetHit` / `GetCritical` / `GetPower`, `Item::IsMagic`, `Unit::GetRangeI` / `GetRangeO`,
  `ItemSubKind::Get` (its readable override `item_subkind_record` is reached when built).
- New layouts: BattleDetail (0x24 bytes, two per side: against a lead, against a follower),
  BattleSide +0x2C..+0x38 (power, hit, crit, crit factor), +0x48 detail, skill and bonus words,
  +0xE6 active-skill bits; Unit +0x28 conditions, +0x2F absorbed, +0x37 debuff, +0xC8 gains,
  +0xD0 limit bonus, +0xE0 stat loss, +0x108 items.

**Host differential test:** `python src/readable/battle/tests/formula_diff.py` (the stance
test's method and ARM interpreter). Only leaf guest functions are answered by a table; the stat
getters, the weapon-rank code and GetCritical / GetSecure / speeds inside CalculateDetail run as
the game's ARM code. Inputs reach outside the game's ranges on purpose. New in this test: for the
overrides it also compares the number of bytes read from unmapped memory (tier 2's criterion),
about 1 case in 8 uses an unmapped unit pointer (as tier 2's made-up state does), and a give-up
must come before any unmapped read. 23 functions: 6,900 cases (seed 20261111) and 23,000 cases
(seed 7, `-n 1000`), 0 mismatches; `--plant` plants 30 bugs one at a time, 30 of 30 caught.
Since the formula fix it also counts `ItemSubKind::Get` calls on both sides: 6,900 and 34,500
cases (`-n 1500 --seed 7`), 0 mismatches, 31 of 31 planted bugs caught.

**Tier 2** (2026-11-12, all 56 overrides, library build 360 s): **0 mismatches**,
`readable-verify: OK (23 ABI-ONLY, 4 CLEAN, 26 GAVE-UP, 3 UNSAMPLED)`. The 21 formula overrides:
ABI-ONLY `unit_equipped_index`; GAVE-UP the other 19 except one (verify's made-up memory has the
one-time caches cold, so only the fallback ran: the give-up is invisible, the formula itself was not
compared by tier 2; the host test covers it); UNSAMPLED `unit_avoid` (3dsrecomp keeps its code inside
`f_005334F0`, GetAvoid(int), which falls into it, so verify cannot pick its address). Two earlier runs
the same night had 7 MISMATCH, all fault counts: the readable code read unmapped memory before
giving up on a cold cache (and, in the stat getters, read the pair partner unconditionally and the
weapon kind once instead of the game's three times). Fixed by reading what the game reads and by
asking for every needed cache first; the host test now checks both, so it reproduces that tier-2
criterion. Registry statuses were not changed (no `--update-status`).

## 13. Growth, level-up and experience: the fifth rewrite target (growth area, 2026-11-12)

Grok's batch 4 (docs/tracks/BATCH_GROWTH.md). How growth rates, caps, experience and the level-up
roll work, read from the code, the number and order of the dice per level-up, and Grok's leads
checked one by one: docs/GROWTH.md. It settles the open question: **`Unit::LevelUp` rolls and
applies the stats**; `GrowSequence::LevelUp` is only a level comparison, `LevelUpCalculate` runs
`Unit::LevelUp` on a copy, `LevelUpReflect` copies it back, and `GainExp` only starts the
experience bar (`ExpSequence::Create` adds the experience).

**Written** (`src/readable/unit/growth.h`, `growth_rates.c`, `growth_exp.c`, `growth_roll.c`, all
**UNVERIFIED**, registry rows in config/readable/functions.csv, harness rows in
config/harness/targets.csv; `gen_stubs.py --check`: 79 overrides, 19 guard users):

- 23 overrides, all readers: growth rates (`Unit::GetGrow`, `unit::Edit::GetGrow`,
  `unit::Family::GetGrow`, `unit::Family::ParentSingle::GetGrow`), caps (`Unit::GetLimit`,
  `unit::Edit::GetLimit`, `unit::Family::GetLimit`), the six ExpTable getters, the experience
  level and amounts (`GetLevelForCalculateExp`, `GetExpDamage`, `GetDualExpDamage`,
  `GetExpDestroy`, `GetExpDance`, `GetExpRod`, `ExpNormalize`), the level limits
  (`Unit::GetLimitLevel`, `Job::GetLimitLevel`) and the map gate `map::Situation::CanGainExp`.
  Four read one-time caches of their own (they call the guard routine: guard tag in targets.csv);
  six more ask for a cached callee's cache first, so a give-up comes before any read.
  `Unit::GetLimit` was a guest call of the formula batch; its stat getters now reach this override
  through `guest_call`, in the game's order (checked against GetStrImpl / GetMHPImpl's calls).
- 5 helpers (F-017): the generator `growth_random_seed` / `_next` / `_below` (Random::Initialize,
  GetValue(void), GetValue(int), on a host-side copy), `growth_level_up_plan` (the dice of one
  level-up without the caps; pure) and `unit_level_up_preview` (everything `Unit::LevelUp` would
  store). The cap check's stat comes from a callback because `Unit::GetCapabilityImpl` takes two
  stack words, which `guest_call` cannot pass.
- Callee calls: wherever the game calls a function with a readable override, the readable code
  calls it through the guest, in the same order with the same arguments (F-018); words the game
  reads twice are read twice (tier 2 counts unmapped reads).
- New layouts: Unit +0xC0 growth_seed, +0xF1 level, +0xF2 exp, +0x12F, +0x130, +0x132;
  GameUserData +0x2D difficulty; Situation +0x17 no_exp; FamilyParent; global G_ExpTable.

**Host differential test:** `python src/readable/unit/tests/growth_diff.py` (the formula test's
method and ARM interpreter, now with the **whole list of guest calls and their argument registers
compared in order**, not only one callee's count): 26 functions (23 overrides, the generator, the
plan, the preview against the whole of `Unit::LevelUp`), out-of-range inputs and unmapped units on
purpose. Seed 20261112: 7,800 cases, 0 mismatches; `-n 1500 --seed 7`: 39,000 cases, 0
mismatches; `--plant`: 36 planted bugs, 36 caught (among them three that change only the calls or
the unmapped reads, not the numbers). Not yet a `check_all.py` row (the integrate stage adds it).

**Tier 2:** see docs/PORT_PLAN.md, status update 2026-11-12 (growth batch).

## 14. Skill readers: the sixth rewrite target (skills area, 2026-11-13)

Grok's batch 5 (docs/tracks/REWRITE_ORDER.md row 5; Grok's BATCH_SKILLS.md did not exist yet). How
"does this unit have skill X" works (personal skill per difficulty + five equipped slots; classes
only teach skills), how an activation chance is computed and how an attack skill is rolled (one
GetValue(100) per attack skill the side has, thrown **before** the chance, first that fires wins),
which battle-formula readers already reach the skill check, and Grok's lead checked:
docs/SKILLS.md. `ProcSkillEffect` (the lead's first name) is the activation picture and was not
rewritten.

**Written** (`src/readable/skill/skills.h`, `skill_has.c`, `skill_battle.c`, all **UNVERIFIED**,
registry rows in config/readable/functions.csv, harness rows in config/harness/targets.csv;
`gen_stubs.py --check`: 94 overrides, 24 guard users):

- 15 overrides, all readers: `Unit::IsEquipSkill` (`unit_has_skill`), `GetIndividualSkill`,
  `GetHasEquipSkillNum`, `EquipSkill::Get(short)` / `GetNum` / `GetCommonNum` / `IsUnknown`,
  `Job::GetEquipSkill`, `unit::EquipSkillPool::Tst`, the script's `UnitIsEquipSkill`,
  `Unit::HasCheerSkill` / `HasCheerSkillMove`, `map::battle::detail::HasBattleSkill` and
  `IsInvalidKill`, `SkillIndexProvider::GetSkillEffectName`. Five read one-time caches and ask all
  of them first. The formula, stance and growth readers' guest calls of `IsEquipSkill` now reach
  `unit_has_skill`.
- 2 helpers (F-017): `unit_skill_chance` (`GetEquipSkillProbability`; its `GetCapabilityImpl` call
  takes two stack words, so the stat comes from a callback) and `battle_attack_skill_pick` (the
  skill choice of `BattleCalculator::CalculateAttack`: which skill fires, the dice on a host copy of
  the battle roller, the scene it would store, the strikes).
- New layouts: Unit +0xFE equip_skills; EquipSkillTable (G_EquipSkill), SkillIndexProvider,
  GameRandom (G_BattleRandom 0x00752B8C); G_IdentHash.

**Host differential test:** `python src/readable/skill/tests/skill_diff.py` (growth_diff's method:
r0, unmapped reads and the whole ordered list of guest calls; new here: "torn" units whose record
stops at an offset the readers read, and a **nested give-up check**: a guest call of another
readable override that gives up inside while the outer function goes on is a mismatch). The
helpers are compared with the whole of `GetEquipSkillProbability` and of `CalculateAttack`
(scene, number of dice, the roller's four words afterwards, strike calls). Results: docs/PORT_PLAN.md,
status update 2026-11-13 (skills batch). The same nesting check was added to growth_diff.py (review 4:
it now catches removing "ask for the cache first" in `unit_dual_exp_damage`).

**Tier 2:** see docs/PORT_PLAN.md, status update 2026-11-13 (skills batch).

## 15. Menus and panels the options need: the seventh rewrite target (menus area, 2026-11-13)

Grok's batch 7 (docs/tracks/REWRITE_ORDER.md row 7; OPTIONS_V2, OPTION_HOOKS). Four of the
options are already switches of the game's own options screen: the danger zone, the map HP bars,
the battle animations and the game speed all read one block, `GameConfigData` (G_GameConfig
0x006DA0F8), and that block is written into every game save (`GameUserData::Serialize`). How each
option is decided, which functions only read, what a port option may hook and what the robot must
replay first: docs/MENUS.md. `map::Panel::Danger` (the lead's name) only draws; the zone itself is
`map::Image::Danger::Update` / `Add`, and both write.

**Written** (`src/readable/menu/menus.h`, `menu_config.c`, `menu_show.c`, `menu_danger.c`, all
**UNVERIFIED**, registry rows in config/readable/functions.csv, harness rows in
config/harness/targets.csv; `gen_stubs.py --check`: 110 overrides, 27 guard users):

- 16 overrides, all readers: the option items' `GetValue` (DangerPanel, HPGauge, Battle,
  GameSpeed, AISkip, Distance, EncountBGM, the on/off `ConfigItem`), `GameConfigData::IsSpeedFast`,
  `IsSkipInput`, `GetInfoCapability`, `IsDetailBattle` (the battle-picture rule), `IsDetailSupport`,
  `Unit::IsDetailBattleMust` / `IsDetailBattleNotAllow` and `map::Panel::Danger::IsHide`. Three
  read one-time caches (guard tag in targets.csv); `IsDetailBattle` asks its two callees' three
  caches first.
- 6 helpers (F-017): `config_saved_record` (what `Serialize` writes), `battle_picture_choice`
  (the decision in the battle sequence's constructor), `actor_hp_bar_shown` (the bit
  `map::Actor::Tick` stores), `danger_update_targets` (the units `Danger::Update` passes to `Add`),
  `danger_add_preview` (`Add`'s search flags and OR, without `UnitMove` and the cannon marks) and
  `danger_tile_kind` (`SetVertex`'s tile test: the reader a `danger_zone` option needs).
- Guest calls left (readers): `VertexBuffer::GetSize`, `Force::Get`, `Terrain::Get`, the option
  item's virtual `GetMask`; `Force::IsAllied` and this batch's overrides are called through the
  guest where the game calls them (F-018).
- New layouts: GameConfigData, Pad, DangerImage (MapImage +0x1008), MapActor, BattleSequence;
  MapImage +0x408 draw_terrain, MapDeploy +0x80C..+0x814, Situation +0x4 bit 0, +0x8, +0x9;
  globals G_GameConfig, G_Pad.

**Host differential test:** `python src/readable/menu/tests/menu_diff.py` (skill_diff's method:
r0, unmapped reads and the ordered guest-call list for the overrides, nested give-ups; the
helpers against the whole of `Serialize` and `Danger::Update` and against regions of the
battle-sequence constructor, `map::Actor::Tick`, `Danger::Add` and `SetVertex`). Results:
docs/PORT_PLAN.md, status update 2026-11-13 (menus batch).

**Tier 2:** the same status update.

## 16. Writers: the gate, the undo log and the first writer, all OFF (writers area, 2026-11-14)

F-006 "writers wait" and F-017 made into code, without switching anything on. Plain-language
rules, what must pass before a writer may be switched on (the host comparison, robot H6, a replay,
the owner's OK) and the save consequence: **docs/WRITERS.md**.

**Written** (all **UNVERIFIED**, all OFF):

- `src/readable/core/fe_writer.h`, `writer.c`: the writer gate and the writer undo log. A writer
  runs only when it is armed in `writer.c` (every writer ships `0`, and the table is `const` in a
  library build), listed in `FE_WRITERS` and the mode is `readable`; shadow, capture and original
  mode refuse it (counted). Every store (`fe_writer_store`, and every store of a game function the
  writer calls with `fe_writer_call`) is logged as address, size, old, new, writer, frame, session
  before the byte changes; `fe_writer_end(keep = 0)` and `fe_writer_undo_last` put the bytes back
  exactly (undo refuses with `FE_WRITER_CONFLICT` and changes nothing when a byte was changed
  since). A store that could not be undone is refused and the session rolls back. 8,192 entries,
  static; full: the oldest finished sessions are dropped whole, an open one fails instead. Game
  -agnostic. No marker: the core build compiles it as dead code (nothing calls it).
- `src/readable/menu/menu_writer.h`, `menu_config_writer.c`: `config_write_options`, the first
  writer: sets the battle-animation, game-speed, danger-zone and HP-bar lines of `GameConfigData`
  the way the options screen does (`ConfigItem::KeyCall`: `GetValue`, then `SetValue(int)` only
  when the value differs), with `DangerPanel::SetValue`'s `Map::Get` / `Danger::Update` calls in
  the game's order, through the gate. Values past a line's range are refused before anything is
  read. Registry rows (kind `helper`, evidence "WRITER, OFF"): `config_set_battle` 0x003BC36C,
  `config_set_game_speed` 0x003BC968, `config_set_danger` 0x003BAF00, `config_set_hp_gauge`
  0x003BC51C. No targets.csv row (it accepts only `override` and `probe`; WRITERS.md section 5).

**The lint.** `check.py` refuses `guest_set_*` / `mem_write*` / `WRITE_FIELD` in readable sources
(the verify classifier assumes overrides never store). The gate stores through the page pointers of
`write_pages` itself, so the writers pass the lint; that is sound because no writer is an override
(no marker: `verify` and `FE_ENTRY` never run one). A writer must store only through
`fe_writer_store` / `fe_writer_call`.

**Checks** (host compiler only, no engine build):

| Check | Result |
|---|---|
| `python src/readable/core/tests/writer_gate_test.py` | 244/244 checks; source checks clean (every writer unarmed; the gate reads only FE_WRITERS and the mode) |
| `python src/readable/core/tests/writer_gate_test.py --plant` | 17/17 planted bugs caught (one, the log-room check removed, shows as a hang: the 60 s limit catches it) |
| `python src/readable/menu/tests/writer_diff.py` | 600 cases, 0 mismatches: result, one ordered list of stores and guest calls, bytes read, the block after, the undo log (old values, writer id, frame), undo back to the start |
| `python src/readable/menu/tests/writer_diff.py --plant` | 25/25 planted bugs caught (15 in the writer: wrong byte, wrong size, the compare left out or turned round, `Map::Get` skipped or its answer ignored, a wrong `Update` argument, the zone rebuilt before the store, lines out of order, range off by one both ways, the wrong byte compared, an extra read; 10 in the gate: old value, frame, writer id, the mode / armed / listed keys, a callee store not logged, a store dropped quietly, a stray store made, an undo that keeps the bytes). The weakest, `danger >= 3` made `> 3`, is caught by 1 case of 400 |
| `python tools/readable/check.py` | lint 138 rows, 0 problems; 27 sources and 27 staged files compile; host 146/146, capture 565/565, undo 554/554 |

What is not done: nothing calls a writer; no robot H6 on writers; no engine build; nothing armed.

## 17. A fifth argument on the guest stack: `guest_call5` (tools-fixes, round 11, 2026-11-15)

`include/readable/fe_guest.h` gained `guest_call5(ctx, f, a0, a1, a2, a3, a4)` for callees that take a
fifth word on the stack (AAPCS: the word at sp when the callee starts), as the game passes the rally kind
to the stat getters (`Unit::GetPowImpl` and its siblings). It stores a4 at the first 8-byte aligned
address at least 8 bytes below the readable function's sp, lowers sp to it for the call and puts sp back.

The rule that readable code stores nothing before a point where it may give up has one stated exception
now: that one store, because it is in the **dead stack** (below sp: no live guest data is there, the
game's own call stores its frame and this very word in the same place, the capture compares leave
`FE_CAP_STACK_WINDOW` below sp out, and the host tests count such stores apart and never as a guest write).
No other store is allowed. Six words: `guest_call6`, section 18. More than six words: still not supported.

First user: `unit_range_max` (the 0xFE range, docs/ITEM.md 4). Callees still waiting on this, now
unblocked for a later batch: `Unit::GetRodHealPower` / `GetInterferenceRodHit` / `Avoid` (one stack word,
docs/ITEM.md 7) and the support review's `GetFamily` helpers. `Unit::GetCapabilityImpl` takes two
stack words: callable since round 15 with `guest_call6` (section 18).

**How guest_call5 is tested (round 11 review).** The review planted two bugs in fe_guest.h that
`item_diff --only unit_range_max` did not catch: sp not put back after the call, and the fifth word
stored 4 bytes too high. The second slipped through because the fifth word is always 0 there and the
test's stack was all zeros. The first cannot be seen by item_diff or ai_score_diff at all: they enter
readable functions through FE_ENTRY, and FE_ENTRY puts every register back (`fe_load`) when the readable
function returns or gives up. So at the override's edge the game never sees a lowered sp. Inside the
readable function it does matter: later code and later guest calls (and their give-up replays) would
run on the wrong sp. Two changes:
- `tools/readable/tests/guest_call5_test.c` (run by `python tools/readable/tests/guest_call5_test.py
  [--plant]`, host gcc only) calls guest_call5 directly on a dead stack full of non-zero junk, for four
  sp alignments and four fifth words (0, 1, 0x12345678, 0xFFFFFFFF). It checks that the callee sees
  r0..r3 and the fifth word at [sp], that its sp is 8-byte aligned and 8..15 bytes below, that sp is put
  back after a normal return, after the callee gave up and when there is no host code, that only the
  word's four bytes change, and that nothing is stored or called while a give-up is pending.
  192 checks. Seven planted bugs in a copy of the header, all caught: sp not put back (48 failed
  checks), word 4 bytes too high (64), no 8-byte alignment (8), only 4 bytes below sp (24), sp not
  lowered (88), word stored after the call (48), store while a give-up is pending (16).
- item_diff fills the dead stack below sp with random bytes, so a word in the wrong slot shows in the
  call list. Its `--plant` list gained the "4 bytes too high" bug in fe_guest.h (fe.h and fe_guest.h
  are copied into the plant folder so the item sources pick up the copy).
ai_score_diff (another helper's untracked test) still zeroes the stack; guest_call5_test covers the
helper itself for every caller.

## 18. A sixth argument on the guest stack: `guest_call6` (capability batch, round 15, 2026-11-16)

`guest_call6(ctx, f, a0, a1, a2, a3, a4, a5)` is `guest_call5` with a sixth word: the fifth word goes to
the same 8-byte aligned slot at least 8 bytes below the readable function's sp, the sixth to the slot + 4
(still below sp), sp is lowered to the slot for the call and put back. The same dead-stack exception as
section 17 covers both stores; nothing else changes. Written for `Unit::GetCapabilityImpl` (two stack
words: the loss bool and the rally kind), whose two totals call it (docs/CAPABILITY.md). guest_call5's
text is untouched, so its planted-bug list still applies.

Its own test, `python tools/readable/tests/guest_call6_test.py [--plant]` (guest_call5_test with a sixth
word; host gcc only): the callee sees r0..r3, the fifth word at [sp] and the sixth at [sp + 4], its sp is
8-byte aligned and 8..15 bytes below, the sixth word is below the caller's sp, sp is put back after a
return, a give-up and a missing callee, only the eight bytes of the two words change, nothing is stored or
called while a give-up is pending. 224 checks; 10 planted bugs in a copy of the header, all caught (sp
not put back, fifth word too high, sixth word in the fifth's place, sixth word not stored, words swapped,
no alignment, only 4 bytes below sp, sp not lowered, words stored after the call, store while a give-up
is pending).

The callers that took the stat by callback because of the two words (`unit_skill_chance`,
`unit_level_up_preview`; both helpers, not overrides) were not changed.
