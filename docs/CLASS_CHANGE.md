# Class change and seals (Fates): what a seal item asks for, base classes, and stat seals, read from the code

**In plain words.** This is batch 4 of docs/tracks/REWRITE_ORDER2.md, "Class change and seals". It
rewrites, as readable C, the small questions the game asks around a class change: what kind of
class change a seal item is, whether a unit's supports count for the support-based seals, and what
a character's base class is. "Seal" also means a second thing in Fates: skills that lower a stat
of the foe after a hit (Seal Strength and friends). The batch rewrites the question "which stat
seal does this unit apply", and, as a helper, how a new stat seal is merged with an old one.

Nothing here changes a class, a stat or anything else in the game: every function only reads
(F-017, F-021). The functions that do change something are named in section 5 and left out.

Status 2026-11-16 (round 12 batch `class_change`), all **UNVERIFIED** in the project's sense:

- **4 readable overrides** (`src/readable/class_change/class_change.c`, registry and target rows
  added): `class_change_type`, `unit_reliance_blocks_class_change`, `person_base_job_index`,
  `battle_seal_effect`.
- **1 helper** (F-017): `seal_merged_value`, the pure part of `MergeSeal`, which stores. It returns
  what the game would store and writes nothing.

Each gives the same answers as the game's own ARM code on made-up cases (two seeds), with the same
guest calls in the same order and the same unmapped reads; planted bugs and tier 2 are in section 6.
Not yet in a live compare: a separate capture step rebuilds the capture library and runs the routes.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-16) [high unless marked]. No table values or game text are copied here; skill names are the
game's ID labels (`SEID_` = equip skill) given in English [med for the English, low where marked].

---

## 1. How a class change runs (the sequence), and the level-up lesson

A class change is a step of the same `GrowSequence` object as a level-up (docs/GROWTH.md). Its
target class is the word +0x64 of the sequence and the seal item +0x68. The steps, read in order:

| Step | What the code does |
|---|---|
| `GrowSequence::ClassChange` 0x001B3DD8 | **only a branch**: if a target class is set, jump to the class-change part of the sequence (`ProcInst::Jump(4)`). It changes nothing |
| `GrowSequence::ClassChangeCalculate` 0x001B46E4 | makes a **copy** of the unit (a new 0x140-byte Unit, `Unit::operator=`, the force word copied), asks `ClassChange::GetType(item)` and runs `Unit::ClassChange(target, type)` **on the copy**; with a flag set it also fills the copy's HP from `Unit::GetMHPImpl` |
| `GrowSequence::ClassChangeShow` 0x001B42D0 | the window (picture of old and new class) |
| `GrowSequence::ClassChangeReflect` 0x001B4610 | copies the changed copy back into the unit (`Unit::CopyForLevelUp`), frees the copy, clears a flag of the equipped item, re-equips (`Unit::ItemEquip(-1)`) and updates the map figure and a pair partner's |
| `GrowSequence::BranchSkill` / `GainSkill` | after the change; they ask `ClassChange::GetType` again (BranchSkill acts only on type 3: it steps a counter up to the unit's level and jumps back, a loop over levels [med for what the loop learns]) |

So the lesson of level-up holds: `ClassChangeCalculate` is not the change itself but the step that
makes a copy and calls the real one, `Unit::ClassChange(const Job*, int)` (0x003D40C8, 736 bytes),
which stores. `GrowSequence::ClassChange` applies nothing. `ClassChangeReflect` is where the result
reaches the real unit. A class-change mod's hook is `Unit::ClassChange` (writer, off).

## 2. What a seal item asks for (`class_change_type`)

**`ClassChange::GetType`** (0x001951B0): the item's signed kind byte +0x40 (for other items the same
byte is the first carried-stat bonus, docs/BATTLE2.md 5):

```
kind 0 -> 0      kind 4 -> 2      kind 6 -> 3      any other value (also negative) -> 1
```

The class-change list (`ClassChangeEnumerator::Enumerate`, a writer: it fills the list) reads the
same byte. First a condition per kind: kind 0 needs level 10 or more; kind 4 needs the unit at its
level cap (and an unpromoted unit above level 20); kind 6 needs a family number on the Person, the
unit at its class's level cap, `IsRelianceInvalidForClassChange` (below) false and a unit flag
(+0xC bit 4). Then a switch on the byte (0 .. 6; 7 and up add nothing): 0 and 6 add the class's two
promotions (Job +0x64), unless a personal-skill bit on the unit, Person or class forbids it, 1 the "parallel" classes
(`EnumerateParallel`), 2 the spouse's (`EnumerateMarrige`), 3 the best friend's (`EnumerateBuddy`),
4 the unit's own class, 5 one class named by the item (+0x41, if it exists). Which seal is which
kind is table data and is not copied here; the likely reading is 0 = Master Seal, 1 = Heart Seal,
2 = Partner Seal, 3 = Friendship Seal, 4 = Eternal Seal [low for the item names; med for what each
kind lists]. `GetType`'s result goes to `Unit::ClassChange` as its second argument (0 for a
promotion, 2 for kind 4, 3 for kind 6, 1 for the others), and `BranchSkill` acts only on 3.

## 3. Who may use the support seals, and base classes (overrides)

- **`Unit::IsRelianceInvalidForClassChange`** (0x00532D60, `unit_reliance_blocks_class_change`):
  1 only for a unit whose state bit 28 is set (the same "download-only" bit the dragon-vein check
  reads, docs/VEINS.md) and whose Person is **not** a download person (`Person::IsDownload`, a guest
  call; the veins batch's `person_is_download`). Asked by the Partner and Friendship lists and by
  kind 6. Its support twin `Unit::IsRelianceInvalid` (0x0053055C) also checks state bit 18; it is
  support work and not done here (REWRITE_ORDER2: no second pass over supports).
- **`Person::GetLowJobIndex`** (0x0053E198, `person_base_job_index`): the Person record's class
  number (+0x2C), or its unpromoted class (+0x2E) when the class is a promoted one
  (`Job::IsHigh(Job::Get(number))`, two guest calls; IsHigh is the battle2 batch's
  `job_is_promoted`). The class number is read a second time for the answer, as the game does.
  Asked by the Heart Seal list (`EnumerateParallel`), the child class inheritance
  (`IsInheritJobIndex`, `GetInheritJobIndex`, `GetInheritJobIndexFromPlayer`) and
  `Unit::ToPacket`.

## 4. Stat seals (override and helper)

**`map::SequenceBattle::(anonymous)::ProcSequence::GetSealEffect(map::BattleSide::Type)`**
(0x00357120, `battle_seal_effect`): the skill record of the first stat seal the unit of fight side
0 or 1 applies with this strike, or 0. It stores nothing; it looks each skill up by its ID label
(`EquipSkill::Get`, a hash lookup; since round 26 a readable override, `skill_record_by_name`,
docs/SKILL_RECORD.md, reached through the guest call) and asks `Unit::IsEquipSkill` (the skills batch's
`unit_has_skill`).

```
no seal (0) when: the sequence's skip word (+0x25C) is set; its mode word (+0x280) has bit 2 or 13;
                  its seal-step word (+0x274) is 0; either side's word of the strike record
                  (+0x250 -> +0x24 / +0x28) has bit 10
then, for the unit of the side (+0x270 + 4 x side), the first skill it has of:
    dragon curse [low], Seal Strength, Seal Magic, Seal Speed, Seal Defense, Seal Resistance
    side 0 only: "dirty fight" [low] unless the fight record's word (+0x24C -> +0x23C) is above 0
    side 0 only: "clumsy" [low], only with bit 7 of side 0's strike word
  (a skill the unit has is looked up a second time and returned; a lookup that gives 0 is passed over)
last, from the side's own strike word: bit 15 -> the ninja technique's record [low for the name],
      bit 16 -> "ice blood"'s [low], whether the unit has that skill or not (two tail calls)
```

Asked by `SetSeal` (side 0, then side 1) and by the weakness steps of the map fight
(`WeaknessEffect`, `WeaknessCalculateEffect`). It is a decision, not a picture tick, so it is a
reader here although it sits in `map::SequenceBattle` (REWRITE_ORDER2 row 3 keeps the picture last).

**`MergeSeal(Capability*, const Unit*, int stat, int amount)`** (0x00354D2C, helper
`seal_merged_value`): `SetSeal` builds an eight-byte seal block on its own stack (one byte per stat)
and merges each stat seal into it with MergeSeal, which **stores** the merged byte:

```
the unit has the "chain of seals" skill [low for the English]:  old byte (unsigned) + amount, cut to 8 bits
otherwise:                                                    the larger of the old byte (signed) and the amount
```

So MergeSeal is a writer (it stores into its caller's block), not a reader: the helper returns the
byte and writes nothing. The block is only on `SetSeal`'s stack; where SetSeal puts the result is
not traced here.

## 5. Not here, and why

- **Writers** (they store): `Unit::ClassChange` (the change itself), `GrowSequence::ClassChangeCalculate`
  (allocates and changes a copy), `GrowSequence::ClassChangeReflect` (copies it back, re-equips),
  `ClassChangeEnumerator::Enumerate`, `EnumerateParallel` / `Marrige` / `Buddy` / `...Low`, `Add`,
  `AddSlideLow`, `GetLearnEquipSkill` (they fill the enumerator), `MergeSeal` (helper only),
  `SetSeal`, the script command `UnitSetInvalidUseClassChange`.
- **Branch and window**: `GrowSequence::ClassChange` (a jump), `ClassChangeShow`, `ClassChangeMenu`,
  `ClassChangeSequence::CreateMenu` / `CreateAction`, `CutSceneController::ClassChange`, the
  `ProcSequence::ClassChange*` ticks, `GrowClassChangePlate` / `MenuPlate`.
- **Needs a guest buffer**: `Unit::GetCollectiveLevelUpClassChangeJob` only reads, but it hands a
  0x410-byte enumerator on its own stack to `Enumerate`, which fills it; the readable code would have
  to give the callee guest memory to write. Not done.
- **Takes a fifth argument on the stack**: `IsInheritJobIndex`, `GetInheritJobIndex` (5 words),
  `GetInheritJobIndexFromPlayer` (6). An override receives only r0 .. r3.
- **No seal item has a function of its own.** A search found no Heart Seal, Partner Seal or Master
  Seal name; none is invented here.

## 6. Checks and results

**Host differential test:** `python src/readable/class_change/tests/class_change_diff.py` (the
method of battle2_diff.py: arm_mini.py runs the ARM code from extracted/text.bin, the readable C runs
on the same memory; compared are r0, unmapped reads and the ordered list of guest calls with their
argument registers, tail calls included). The callees `Job::Get`, `Job::IsHigh`,
`Person::IsDownload`, `EquipSkill::Get` and `Unit::IsEquipSkill` are answered by one table on both
sides. The ARM side also checks that the original stores nothing outside the stack (one byte for
MergeSeal). `seal_merged_value` runs through a test-only entry; the expected result is the byte the
ARM function stores. Half of the seal cases are focused on side 0's two extra steps. 28 planted
bugs; one first plant (the strike pointer not read again before the last step) cannot be seen by any
test (nothing stores, so the pointer cannot change, and the word it comes from was already read) and
was replaced by "the last step reads the fight record instead of the strike record".

Results (2026-11-16):

- Seed 20261116, 300 cases per function, `--plant`: **1,500 cases, 0 mismatches, 28/28 planted
  bugs caught** (fewest mismatches for one plant: 6). Seal answers met: none 147, dragon curse 35,
  Str 28, Mag 14, Spd 16, Def 13, Res 8, dirty fight 6, clumsy 6, ninja 13, ice 14.
- Seed 7, 300 cases per function, `--plant`: **1,500 cases, 0 mismatches, 28/28 caught** (fewest: 8).
- Tier 2 (`tools/readable/verify.py --out build/readable/verify_class_change --only
  0x001951B0,0x00532D60,0x0053E198,0x00357120`; the verify library built from all 45 staged sources
  in 413 s): **4 ABI-ONLY, 0 MISMATCH, 0 GAVE-UP** (`readable-verify: OK`). The differences are only
  in scratch registers, flags and the dead stack. For `battle_seal_effect` the shadow pass logged no
  comparison (verify's note: the original stopped in a short slice); its readable pass is ABI-ONLY.
  No classifier rule was changed.
- `python tools/readable/check.py --selftest`: readable OK (lint 273 rows, 0 problems; 45 sources).
  `python tools/harness/gen_stubs.py --check`: OK (240 overrides).

**Live coverage.** Class-change items: **not here.** No recorded route spends a seal (docs/ROBOT.md:
the Master Seals picked up are carried, "not used"), and REWRITE_ORDER2 says not to spend one on a
recorded chain. `class_change_type` stays unmet (no route spends a seal). Round 12's capture
(r12-cap-class_change, 47 routes) met the other three, all matching: `unit_reliance_blocks_class_change`
735 records (it is asked outside the class-change list too, so the earlier "expected unmet" note was
wrong), `battle_seal_effect` 899, `person_base_job_index` 598.
