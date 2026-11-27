# The enemy's choices (Fates): who the AI may attack, heal or leave idle, read from the code

**In plain words.** On every enemy (and allied, and other army) phase the game's AI goes through
its units one by one and asks many small questions before it moves anyone: may this unit attack
that one, may it heal that one with a staff, does one of its orders apply right now, is this tile
an edge it can run away from, how many enemies stand close to this tile, is there a partner next to
it, which healing item or stat booster would it use, does it carry a heal staff it can wield. This
batch rewrites **18 of those questions** as readable C (REWRITE_ORDER2 batch 1, "who the AI is
allowed to hit, heal or idle").

All 18 are **readers**: they store nothing (F-017, F-018, F-021: no writer, nothing armed). The
functions that act (`AIThink::MoveTo`, `AttackTo`, `RodHealTo`) and the ones that fill the move
range are named in section 7 and left out. Nothing in this batch changes how the enemy plays; it
makes the reasons readable, so that a later mod (or a later batch) can see why a unit acted.

Status 2026-11-15: 18 readable overrides (`src/readable/ai/ai_permission.c`, `ai_area.c`,
`ai_items.c`, header `ai_perm.h`), all **UNVERIFIED** in the project's sense. Every one gives the
same answers as the game's own ARM code on made-up cases, with the same guest calls in the same
order and the same unmapped reads (section 8); every bug planted on purpose was caught. Not yet in
a live compare: the round-11 integrate rebuilds the capture library with these rows. Nothing
changes in the game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-15) [high unless marked]. No table values or game text are copied here. Field names that
config/readable/structs does not have yet are given with their offsets in `ai_perm.h`, with a
confidence each; where only the effect is known the meaning is marked [low].

---

## 1. Where the AI's data lives

- **AIThink** (the object every question with a `this` gets): its first word is the unit it is
  thinking for. Several questions ask about *that* unit and not about the unit passed in (section 5).
- **The AI sequence state**: the holder at 0x006D0EBC points to a root whose +0x10 is the state
  (config/readable/structs AIThinkState; the older `ai_think_is_move_over` readers use its +0x14C).
  This batch reads its signed byte +0x150 (section 6).
- **The map situation** (global 0x006D7ED0, `Situation`): its byte +8 is read as a force type: the
  army whose turn it is [med: used as the "own side" in the danger count below, and compared with 1
  in `IsClever`].
- **Unit fields the AI uses**: the state word (+0x8; bit 2 = never attacked or healed by the AI
  [low for what the bit means]), the AI word (+0x54: bits 7, 13, 15, 16, 20, 21 are tested here), the
  AI group byte (+0x5B), the healing threshold (+0x5D), the sequence index bytes (+0x65, one per
  order type), the sixteen AI arguments (+0x6A, the older `ai_value_*` readers), HP (+0xF3, signed).
- **AI sequences**: a table at 0x0070560C holds one array per order type (0, 1, 2); a unit's sequence
  for type *t* is `array[t][unit byte 0x65 + t]`. A sequence's commands start at +8, 12 bytes each:
  kind (byte), code (byte), condition (signed byte), and two AI values (signed halfwords at +4 and
  +8). A command of kind 0 ends the list.

## 2. May the AI attack or heal this unit?

- **`AIThink::IsAttackPermission(Unit*,Unit*,bool)`** (0x004CF624, `ai_attack_permission`):
  never a target with state bit 2; always yes when there is no attacker; otherwise yes unless
  `Unit::IsDontAttack` (the sheet batch's `unit_may_not_attack`: the "may not attack" state bit of
  either unit, a Person this unit may never attack, the forces it may never attack) says no. The
  bool is passed on as the caller gave it.
- **`AIThink::IsAttackPermission(Unit*,bool)`** (0x004CF658, `ai_attack_permission_self`): the same
  for the unit the AI is thinking for. The game reads that unit before it looks at the target's bit,
  and the readable code does too.
- **`AIThink::IsHealRodPermission(Unit*)`** (0x004D0ADC, `ai_heal_rod_permission`): never a unit
  with state bit 2; otherwise yes when either AI bit 20 or 21 is set [low for what the two bits mean].

## 3. Does an order apply now?

- **`AIThink::IsActiveCommand(Unit*,AICommand*)`** (0x004CB280, `ai_command_is_active`), by the
  command's condition byte:

  | Condition | Active when |
  |---|---|
  | -1 | always |
  | -2 | the unit's AI group byte is 0 |
  | 0 | the group byte is not 0 |
  | anything else | it equals the group byte |

- **`AIThink::HasActiveCommand(Order::Type,Unit*)`** (0x004CC870, `ai_has_active_command`): does
  the unit's sequence for that order type hold an active attack command (kind 3)? Code 0x51 never
  counts; codes 40 and 41 count only with AI bit 21; a command whose first or second value is
  "skip" (-3) does not count. A value from -4 to -7 is first replaced by the unit's AI argument it
  names, always with order type 2, whatever the sequence's own type [high for the code; why type 2
  is not traced].
- **`AIThink::HasActiveAttackCommandForCrossfire(Unit*,Unit*)`** (0x004D48BC,
  `ai_has_crossfire_command`): for joint attacks: the unit's sequence for order type 2 holds an
  active attack command with a code below 12 whose values are usable and that allows the target
  (next item).
- **`AIThink::IsAttackPermissionOnlyCommand(int,AIValue*,AIValue*,Unit*)`** (0x004D4770,
  `ai_attack_permission_for_command`): does an attack command with this code allow this target?
  Only the first value is used.

  | Code | The target is allowed when |
  |---|---|
  | 3 | the target, its Person or its class has one cached PersonFlag bit (looked up once, by name, from a private skill) [low for which flag] |
  | 4 | the value names the target's Person (`AIValue::GetPerson`) |
  | 5 | the value does not name it |
  | 6 | the target's byte +0x5A is not the value [low for the meaning] |
  | 7, 8 | the value names the target's class (`AIValue::GetJob`) |
  | 9 | the value is the target's force type |
  | any other | always |

## 4. Around a tile

- **`AIThink::IsEscapePosition(int,int)`** (0x004CC978, `ai_is_escape_position`): can the AI's unit
  leave the map from here? For each edge of the playable area the tile lies on (left, top, right,
  bottom, in that order) the tile one step outside is looked up in the map's cost-column grid, and
  if the unit's cost there (`TerrainCost::GetCostFromUnit`) is 0 or more the answer is yes.
  Otherwise yes when a map gimmick of type 6 is reachable from the tile
  (`AIThink::GetTrickFromAccess`, the vein batch's `trick_at_access`). Coordinates are not checked.
- **`AIThink::GetSighOfDeathScore(int,int)`** (0x004D0820, `ai_sigh_of_death_score`): how
  dangerous a tile is: the number of units one or two steps away (|dx| + |dy|), inside the playable
  area, whose army is not allied with the army whose turn it is and that have more than 1 HP; at
  most 63 (never reached: only 12 tiles are that close). The box the game walks is cut to the playable area and its corners are kept to 16 bits
  (signed), as the game stores them.
- **`AIThink::IsDualSupportUnit(Unit*,int,int)`** (0x004CDF40, `ai_is_dual_support_unit`): could the
  unit pair up from here? Yes when it already has a partner; otherwise yes when a unit of the same
  force type stands on one of the four tiles next to the tile, inside the playable area.

## 5. Which item the AI would use

- **`AIThink::GetItemIndexHeal(Unit*,bool,bool)`** (0x004CC684, `ai_item_index_heal`): the slot of a
  healing item, or -1. An item counts when its use kind is one of two cached kinds (looked up once
  by name) and `Unit::CanItemUse` allows it **for the AI's own unit** (AIThink +0), not for the unit
  passed in. The unit's five slots first; then, when the second bool is set and the unit has a
  partner, the partner's slots, numbered 5 to 9. With the first bool, and always in the partner's
  slots, the item's weapon kind must also be 8 (a healing item).
- **`AIThink::GetItemIndexDoping(Unit*)`** (0x004CF360, `ai_item_index_doping`): the slot of a stat
  booster, or -1: an item not marked with bit 15 of its second halfword (the AI never uses it [low]),
  whose use kind is one of four cached kinds, that `Unit::CanItemUse` allows (again for the AI's own
  unit). The fourth kind is taken as it is; the first three only when the item raises a stat
  (record bytes +0x40..+0x47) whose bit in the unit's byte +0x29 is still clear [low for what that
  byte records].
- **`AIThink::HasHealRod(Unit*,bool)`** (0x004C829C, `ai_has_heal_rod`): does the unit carry a heal
  staff it can wield? An item with one cached item flag bit, that `Unit::CanItemEquip` allows; when
  the unit's byte +0x28 has bit 3, a magic item (`Item::IsMagic`) does not count; with the bool, an
  item whose longest range (`Unit::GetRangeO`) is 255 does not count. With AI bit 7 the partner's
  items are looked at too, the same way.

## 6. Smaller questions

- **`AIThink::IsClever(void)`** (0x004D61E4, `ai_is_clever`): the map situation's force byte is not
  1. The attack score, the interference score, the cannon score and the battle simulator ask it
  [low for what "clever" changes; that is batch 2's attack score].
- **`AIThink::IsAllowIdleMutation(void)`** (0x004D0AC0, `ai_allow_idle_mutation`): the AI sequence
  state's signed byte +0x150, returned as it is (a negative byte stays negative). Only the idle
  move action asks it [low for the meaning].
- **`AIThink::GetDeployFreeMoveFlag(const Unit*)`** (0x004D24D4, `ai_deploy_free_move_flag`): the
  move-range flags an AI unit may ignore: 0x200 when AI bit 13 is set and `Unit::CanKeyDoor` says
  the unit can open doors, 0x400 with AI bit 15, 0x1000000 with AI bit 16. Every move action of the
  AI asks it before it builds the move range.
- **`AIThink::GetMovePowerSlow(void)`** (0x004CC818, `ai_move_power_slow`): the move the AI plans a
  slow approach with: the unit's move (with its extras) minus 1 on difficulty 1, unchanged on
  difficulty 2, minus 2 on any other difficulty byte [high for the code; which byte value is which
  difficulty name is not checked here]. On difficulty 2 the game ends with a plain branch into
  `Unit::GetMovePower`; 3dsrecomp keeps that code inside this function (docs/MOVE.md 9), so the
  readable code runs `unit_move` directly there and makes no guest call.
- **`AIThink::IsHealConditionForEntrust(Unit*)`** (0x004D4054, `ai_heal_condition_for_entrust`): an
  entrusted unit wants healing when its HP is below its maximum HP (with the extras) and
  HP x 100 / max HP is below 75 for a unit of army 0 (the player), or below the unit's own byte
  +0x5D for any other army. The division is the game's RVCT routine: toward zero, and 0 when the
  maximum is 0 (its division-by-zero handler returns 0; checked by running it).

## 7. Not in this batch, and why

- **`AIThink::IsMoveNear(int,int)`** 0x004C83F4 and **`AIThink::IsEnemyInsideAttackArea`**
  0x004D359C: both call `map::Deploy::UnitAIMoveXY`, which fills the deploy's move image (a
  store into game memory): writers in this project's sense. Named and left out.
- **`AIThink::GetDualScore(Unit*,int,int)`** 0x004C8E10: builds a `map::BattleDualUnitEnumerator`
  on its own stack (the constructor stores into that frame) and reads it back. `guest_call` cannot
  hand a guest stack buffer to a constructor, and doing the constructor's work inline is a separate
  piece of work; left for batch 2 with the other scores.
- **`AIThink::GetAttackScore`, `GetDestroyScore`, `GetInterferenceScore`, `GetEntrustAttackScore`,
  `GetEntrustHealRodScore`** and the `Get*Range` / `Get*Position` functions: they take out-pointers
  (REWRITE_ORDER2 batch 2 reads each body first).
- **`AIThink::MoveTo`, `AttackTo`, `RodHealTo`, `ToBreak`, `ToDestroy`** and the `Action*` /
  `Entrust*` / `Processing*` functions: they act.
- `AIThink::GetTerrainScore` is the movement batch's `ai_terrain_score` (src/readable/move/); its
  test now has the odd negative defence and heal cases (section 8).
- `AIThink::HasActiveCommand` asks `IsActiveCommand` and the AIValue readers through the guest;
  `AIThink::IsMoveOver` (both) are the older `ai_think.c` readers. Not duplicated.

## 8. Checks

**Host differential test** `python src/readable/ai/tests/ai_perm_diff.py` (the movement test's
method and ARM interpreter, the same tail-branch rule: a plain branch into an override is run on as
ARM code, unlisted, and the readable code runs that override's C directly; a branch into a guest
function is listed). Two kinds of made-up state: the status-sheet test's units (Person, class,
force, partner, carried items, item and sub-kind records), so that `Unit::IsDontAttack`,
`GetMHPImpl`, `GetMovePower` and `GetCategory` run as ARM code on one side and as their readable
overrides on the other; and the movement test's map (unit grid, cost columns, cost tables, unit
pool), so that `map::Image::Unit::GetUnit` and `TerrainCost::GetCostFromUnit` run that way.
`IsActiveCommand`, `IsAttackPermissionOnlyCommand` and the AIValue readers run that way too.
Values are on purpose often outside the game's ranges: coordinates far off the map, unmapped units,
AIThink objects, map images and sequences, condition bytes and AI values that name nothing, command
codes past the switch, bools that are not 0/1, negative HP, a maximum HP of 0. For each override it
compares r0, the unmapped reads and the list of guest calls with their argument registers in order;
a nested give-up is a mismatch.

The test links only the sources git tracks (plus this batch's): other rewrite batches write new
files into src/readable/ at the same time, and an unfinished one must not break this test.

Guest functions answered by one table on both sides: those of the two older tests, and
`GameUserData::Get`, `Unit::CanKeyDoor`, `AIThink::GetTrickFromAccess`, `AIValue::GetPerson`,
`AIValue::GetJob`, `Unit::CanItemUse`, `Item::IsMagic`, `Unit::GetRangeO`. The last three and
`GetTrickFromAccess` are overrides of older batches with their own tests; the readable code here
asks their one-time caches first, so they never give up inside it. (Until round 17, with a table
answering them, the test could not see such a nested give-up itself; a cold cache showed as an early
give-up of the readable code, which is always safe.) **Round 18 (test tools):** two rules close that
gap for `HasHealRod`. (1) A call to `Item::IsMagic` or `Unit::GetRangeO` while its own cache is cold
(guards 0x006D38D4 / 0x006D989C) is answered with a give-up counted as nested, as their overrides would
do in the game (`COLD_STUBS`). (2) A give-up of `ai_has_heal_rod` while all three caches it asks
(rod mask, IsMagic, GetRangeO) are warm is printed as gave_up 2, a mismatch (`GIVEUP_GUARDS`); it was
a give-up-only bug before, never a wrong answer. Those two caches are now cold in 10 % of its cases
(4 % before). The four guard-check bugs h6host round 17 left open (ai_has_heal_rod-001 to -004,
`ai_items.c` lines 110-111) are caught: the plain test (planted bugs 45-48, now 48/48) and
`h6host.py --ids ... --label r18-tt` (all 4 "caught"). Reader code unchanged. One case is left open on purpose: `unit_range_max` of round 10 gives
up on a record range of 0xFE ("half the unit's magic"), which no item of the game has; on such an
item it would give up inside `HasHealRod`. A first version gave up in `HasHealRod` before the call
instead, but that give-up came after reads and calls, and the test (rightly) counted it as a
mismatch when one of those reads was unmapped; it was taken out. The round-11 working tree changes
`unit_range_max` so that it no longer gives up there.

Two details of the game's code cannot change any answer, so no test can see them, and no planted
bug is aimed at them: the scans' 16-bit corners (a corner that the cut changes is always so far
from the tile that no tile of the box is one or two steps away), and the danger count's cap of 63
(at most 12 tiles are one or two steps away).

Results 2026-11-15:

| Run | Cases | Mismatches | Planted bugs |
|---|---|---|---|
| default (`--plant`, seed 20261115, 300 per function) | 5,400 | 0 | 44/44 caught |
| second seed (`--seed 7`, 300 per function) | 5,400 | 0 | - |
| long (`-n 1500 --seed 7`) | 27,000 | 0 | - |

**Re-check 2026-11-15 evening** (the batch's first review had not finished; every gate was run again
to the end on the round-11 working tree, logs in build/readable/ai_perm/r11b/): default `--plant`
5,400 cases, 0 mismatches, **44/44** planted bugs caught; `--seed 7` 5,400 cases, 0 mismatches;
`move_diff.py --plant` 7,200 cases, 0 mismatches, **48/48** caught (now built in the repository
itself: the other batches' files no longer break it); tier 2 again `readable-verify: OK` (section 9,
same verdicts); `gen_stubs.py --check` OK (240 overrides); `tools/readable/check.py` and `--selftest`
OK. No function dropped; no code changed (one comment in ai_items.c brought up to date about
`unit_range_max`).

What the test found while it was written: (1) the late give-up in `HasHealRod` described above
(taken out). (2) Four planted bugs were first not caught: the 75 % line needed cases with HP at
exactly three quarters of the maximum (added); a signed/unsigned swap in code 6 could not change an
answer (replaced by a signed read of the unit's byte, caught with keys of 128 and more, added); the
16-bit corners and the cap of 63 cannot change an answer (above; replaced by an off-by-one in the
box and a wrong force byte, both caught). Logs: build/readable/ai_perm/ (default_plant.txt,
seed7.txt, long.txt, verify2.txt, move_default_plant.txt, move_long.txt). The default run with
planted bugs and the movement runs were made in a copy of the committed tree plus this batch's
files, because other batches' unfinished files in src/readable/ broke the movement test's build
(it compiles every .c file there) while they were being written.

**`ai_terrain_score`'s test** (src/readable/move/tests/move_diff.py, `gen_score`): half of its cases
now put odd negative defence and heal values on the tile itself (-1, -3, -7, -11, -127, ...), where
the game's division toward zero and a floor or a shift give different scores, with and without the
"lockpick" pairing that lifts them to 0. A new planted bug (a floor division of a negative defence)
is caught by them. Results: default `--plant` 7,200 cases, 0 mismatches, **48/48** planted bugs caught (47 before); long (`-n 1500 --seed 7`) 36,000 cases, 0 mismatches. The check_all row `move-diff` still says 47 planted bugs in its text (integrate owns that file).

## 9. Tier 2

**Tier 2** (2026-11-15, `python tools/readable/verify.py --only <the 18 addresses> --out
build/readable/verify_ai_perm`, library built from the working tree): **`readable-verify: OK`: 1
CLEAN, 9 ABI-ONLY, 8 GAVE-UP, 0 MISMATCH, 0 NOT-RUN.** No classifier change.

- CLEAN / ABI-ONLY (`ai_allow_idle_mutation`; `ai_attack_permission`, `ai_attack_permission_self`,
  `ai_heal_rod_permission`, `ai_is_clever`, `ai_command_is_active`, `ai_deploy_free_move_flag`,
  `ai_has_active_command`, `ai_sigh_of_death_score`, `ai_is_dual_support_unit`): differences only in
  r1-r3, r12, flags and dead stack; the shadow passes' unmapped-read surpluses are the shape the
  classifier already accepts (the original's reads plus the readable code's same reads).
- GAVE-UP (`ai_move_power_slow`, `ai_heal_condition_for_entrust`,
  `ai_attack_permission_for_command`, `ai_has_crossfire_command`, `ai_is_escape_position`, the
  three item readers): verify's made-up memory has every one-time cache cold, so the readable code
  gave up and the original ran, as in every earlier batch. Proves nothing either way; the host test
  and the live compare cover them.

Run again in the evening from the round-11 working tree (`--out build/readable/verify_ai_perm_r11b`,
its own library, not the capture library): the same result, `readable-verify: OK (9 ABI-ONLY,
1 CLEAN, 8 GAVE-UP)`, 0 MISMATCH, 0 NOT-RUN.

The first verify run from a clean copy in the scratch folder could not link (Windows: "the filename
or extension is too long", the folder path was too long); the run above is from the repository.

## 10. Where these will be met in real play

Every one has callers in the AI's own code (a scan of every BL in text.bin, 2026-11-15):
`IsAttackPermission` (both) from the attack, force, person and crossfire actions and the joint
attack code; `IsActiveCommand`, `HasActiveCommand` and the crossfire command test from
`UpdateTargetOne`, `CheerNoMove`, `CheerInsteadOfAttack`, `AICrossfire::Calculate` and `AIDual::Think`;
`GetDeployFreeMoveFlag` from every move action (19 calls); `GetSighOfDeathScore` from
`GetAttackPosition`, beside `GetTerrainScore`; `IsClever` from the attack score; the item readers
from `ProcessingMutation`, `HealMindToVulnerary` and the heal-staff actions; `GetMovePowerSlow` from
`MoveTo`. The older overrides these call are met in real play on every enemy phase: in the round-10
live compare (r10-capb, 38 routes) `ai_terrain_score` was called 66,013 times, `ai_value_is_argument`
242,506, `unit_may_not_attack` 570,979 and `image_unit_at` 8,271,075 times [high for those counts;
med that each reader of this batch is reached: the integrate's live compare will say which]. The
item readers need an enemy that carries a vulnerary, a booster or a staff, and the escape test an
enemy with an escape order; some may be met only on some routes.
