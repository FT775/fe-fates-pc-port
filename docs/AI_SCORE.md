# AI attack scores (Fates): PARKED

**In plain words.** This batch is **parked** (docs/DECISIONS.md F-025, 2026-11-15 night; the plan is
docs/collab/STRATEGY_R11_GROK.md). Nothing of it is in the game, in the capture library, in the readable
registry or in the harness target list. The source files are kept, renamed so that no build sees them.

## Status 2026-11-15

- **Parked, not finished.** The batch was meant to rewrite the five functions that score the AI's
  attacks. All five store their answers through out-pointers (section 1), so by the readers-only rule
  (F-017, F-021) none of them could be written. What the batch wrote instead were six small readers the
  score functions ask. The owner's "Apply now" (F-025) parked the whole batch: it does not deliver what
  its plan row asked for, and no new battle readers are added until the battle-number mismatch is fixed
  or explained.
- **Not green when parked.** The planted-bug gate failed (46 of 49 caught) and the long run (seed 7) did
  not pass by the test's own rule (section 8). Three of the six never ran their readable body in tier 2.
- **Never live.** The capture library in build/harness/lib was built at 02:27 on 2026-11-15, before this
  batch existed; no capture library was built with it and no live compare ran on it.
- **Removed:** its six rows in config/readable/functions.csv and its six rows in
  config/harness/targets.csv (addresses 0x0050C10C, 0x00526B10, 0x004C5344, 0x00528238, 0x0034A8CC,
  0x0052F008). **Kept:** `src/readable/ai_score/ai_score.h`, the three bodies as `*.c.parked`, and the
  host test `src/readable/ai_score/tests/ai_score_diff.py` (section 9).

What remains below is the reading of the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-15) [high unless marked], kept so a later batch does not have to read it again. No table values or
game text are copied here; skill and item-use names are the game's ID labels (`SEID_`, `ISID_`, `IUID_`)
given in English [med for the English, low where marked].

---

## 1. The five score functions store: named and left out

Each was read in full before deciding. "Out-pointer" means a pointer the caller passes so the function
can write its answers into the caller's memory (here: the AI's stack); by this batch's rule that is a
store, so the function is a writer and waits (F-017, F-021).

| Function | Address | What it stores |
|---|---|---|
| `AIThink::GetAttackScore(Unit*,unsigned,bool,unsigned*,int*,int*,int*,float*)` | 0x004CA140 | Clears all five out-pointers on entry, writes the best score, tile and item slot into them; calls `Random::GetValue` (advances the random generator) to break ties; builds an `AIBattleSimulator` (2 KB on its stack) whose `Calculate` stores into it |
| `AIThink::GetDestroyScore(int,int,unsigned,bool,unsigned*,int*,int*,int*)` | 0x004CAB2C | The four out-pointers; when it tries the pair partner, sets and then clears bit 21 of the word at Unit +0x8 of both the AI unit and its partner around `Unit::GetAttackForTerrain` (stores into live units, even if put back); `Random::GetValue` |
| `AIThink::GetInterferenceScore(Unit*,unsigned,bool,unsigned*,int*,int*,int*)` | 0x004D1908 | The four out-pointers; a byte table on its stack; `AIInterferenceSimulator::Calculate`; `Random::GetValue` |
| `AIThink::GetEntrustAttackScore(Unit*,int,unsigned*,int*,int*)` | 0x004D2518 | The three out-pointers (cleared on entry, the score on success); `AIBattleSimulator::Calculate` |
| `AIThink::GetEntrustHealRodScore(Unit*,unsigned*,int*,int*,int*)` | 0x004D26CC | The four out-pointers; `Random::GetValue` |

Their score helpers store too: `AIBattleSimulator::Calculate`, `CalculateScore`, `CalculateIndication`,
`CalculateKillProbabilityWithoutInterference2/3` and `AIInterferenceSimulator::Calculate/CalculateScore`
all write into the simulator object. The order's advice ("return the number from a helper, do not store
it") would need the random generator's next value without advancing it, and the whole simulator; that is
writer work, not this batch.

Also left out: `map::battle::detail::GetHitProbabilityEffectiveDenominator10000` and
`anonymous_namespace::ExpectationScoreNormalize` (pure, but VFP float code: readable C does not run
VFP and tier 2 would show a "vfp state" MISMATCH, as `map::Actor::GetTerrain` did in docs/MOVE.md);
`AIThink::IsClever` and the other permission readers (batch 1,
`src/readable/ai/`).

## 2. Would this attack do nothing? (`AIBattleSimulator::IsPower0Attack`, 0x0050C10C)

`ai_sim_is_power0_attack`. `GetAttackScore` asks it for every target and tile (unless the AI unit has
bit 6 of Unit +0x54 and is not "clever"); an answer of 1 makes the AI skip that try. `AIThink::AttackTo`
and `AIThink::ProcessingMutation` ask it too.

It reads the simulator the score function filled: +0 the attacker, +4 the target, then four 0x200-byte
battle sides from +8 (side 0 the attacker's, side 1 the target's, side 2 a third one, the pair-up
attacker's [med]).

1. Eight skill numbers are looked up by name once and cached (guards 0x006D0F40 down to 0x006D0F24).
   While any guard is cold the readable code gives up before reading anything. It also asks the guard
   of `Item::IsHiddenEffect`'s own cache (0x006D38D8, item batch) first, so that override never gives
   up inside it (no nested give-up).
2. +0x814 above 0: the game compares a float (+0x820) with 0.0 and answers 0 when it is above. That is
   VFP code; **the readable code gives up here and the original runs** [low for what the two fields mean].
3. Side 1's +0x3C above 0: answer 1 [low for the meaning: `Calculate` works out a kill chance for a side
   only when this field is above 0].
4. The attacker has "snake venom", "four fangs" or "breath of death" [low for all three English
   names]: answer 0.
5. Otherwise it works out how much Defence (D) and Resistance (R) the attack would lower:
   - both start at 0;
   - side 0's weapon, and side 2's when side 2's +0x3C is above 0: when `Item::IsHiddenEffect` says it is
     a concealed weapon (daggers, shuriken), D and R become at least the record's bytes +0x46 / +0x47;
     the item is passed only when its item number is not 0, else a null item;
   - "seal Defence" / "seal Resistance": D / R at least 6;
   - side 1 has "status immunity" (a skill bit in side 1 +0xE6): D = R = 0; else "status resistance":
     both halved.
6. No target unit: answer 1.
7. The attacker has "chain of the negative" [low]: answer 0 when D > 1 or R > 1, else 1.
8. Otherwise answer 0 when the target's Defence already lowered (Unit +0x3D, signed) is below D - 1,
   or its Resistance already lowered (+0x3E) is below R - 1; else 1.

In plain words: a clever enemy will not make an attack that deals nothing and lowers nothing the target
has not already lost.

## 3. Castle-offense targets (`map::trick::Data::IsDestroyTargetCastleOffense`, 0x00526B10)

`trick_is_destroy_target_castle_offense`: 1 when the breakable object's trick type (byte +0xC) is 15 to 22.
`GetDestroyScore` asks it only when its search flags include 0x10 [low for what the types are in play;
no named route has proved a breakable wall, docs/tracks/REWRITE_ORDER2.md].

## 4. Versus battles (`versus::Config::Get` 0x004C5344, `map::Situation::IsVersus` 0x00528238)

- `versus_config_get`: the versus configuration pointer (global 0x006DA318), 0 outside versus play.
  156 call sites in the game (chapter sequence, save data, the map's end checks).
- `situation_is_versus`: 1 when `versus::Config::Get` gives a configuration. The situation object itself is
  not read. 66 call sites. In a normal (non-link) game both answer "no" every time.

## 5. How much does a staff heal? (`Unit::GetRodHealPower`, 0x0052F008)

`unit_rod_heal_power(unit, item, target)`. `GetEntrustHealRodScore` asks it for every heal it weighs;
the staff use on the map asks it too.

```
heal = the staff's base heal (record +0x1F, unsigned)
     + magic / 3 (toward zero)       only for a staff with the ISID flag "effect + magic / 3"
     + staff rank bonus              WeaponBonus row of the staff kind, signed byte at 2 x rank;
                                     rank = WeaponLevel::GetLevel(min(staff exp, staff exp limit))
then, when the healed unit (may be 0) has the cached skill "absent-minded" [low]: heal += heal / 2 (down)
```

The magic is `Unit::GetPowImpl(unit, no item, extras on, loss on, rally kind 0)`. Its fifth argument is
on the stack; the readable code passes it with `guest_call5` (round 11, docs/READABLE.md 17), whose one
store is that word in the dead stack below sp, where the game's own call puts the same word. The readable
code asks the caches of `Unit::GetWeaponExpLimit` (three guards) and of `Unit::GetPowImpl`
(`unit_stat_caches_ready`, battle batch) with its own two before anything else, so neither override gives
up inside it.

Who owns it now: nobody. The battle-numbers batch (`src/readable/battle2/`) wrote the same function
the same round and took its copy out when it found this one (docs/BATTLE2.md, "Another batch has it").
With this batch parked, 0x0052F008 has no override and the game's own code runs. A batch that wants it
can take the reading above; the parked copy here is not built (section 9).

## 6. Can this staff be used from here? (`map::ItemHelper::Rod::CanUseDisvalueRange`, 0x0034A8CC)

`rod_can_use_from(unit, slot, x, y)`. Asked by `GetInterferenceScore` for the AI's staves, and by the
player's side through `map::Target::PreCheckItemMaskRod` and `map::ItemHelper::Battle::CanUse` (whether
the staff in a slot can be used at all from a tile).

| Case | Answer |
|---|---|
| the item in the slot (Unit +0x108 + 4 x slot) is not a staff (its sub-kind's kind is not 6) | 0 |
| the unit's condition byte (Unit +0x28) has bit 3 [low: probably a "no staves" state] | 0 |
| `Unit::CanItemEquip(unit, item, 1, 1)` says no | 0 |
| a "heal all" staff (the record's +0x1B equals the cached ItemUse number of `IUID_` "heal all") | 1 when some unit at a distance from `GetRangeI` to `GetRangeO` of (x, y), inside the playable area, or that unit's pair partner, passes `Rod::CanUseTarget`; else 0 |
| a "revival" staff (`IUID_` "revival") | 0 in a versus battle or when the unit is not of the player's army (force type 0); else 1 when the fallen (force 4) has a first unit whose state word bit 7 is set [low for the bit] |
| any other staff | `Rod::CanUseTarget` on the unit standing on (x, y) |

The scan of the "heal all" case goes row by row from the top, each row from the left, and stops at the
first unit that passes. Its bounds are the range square cut to the playable area (map image bytes 2..5)
and kept to 16 bits as the game keeps them (`SXTH`); a playable area that ends before it starts gives no
scan.

Calls kept as guest calls, in the game's order: `unit::Item::ToData` (three times, as the game asks it),
`ItemSubKind::Get`, `Unit::CanItemEquip` (since rewritten: `unit_can_equip_item`, docs/EQUIP_USE.md), `Unit::GetRangeI` / `GetRangeO` (sheet and
item batches), `map::Image::Unit::GetUnit` (move batch), `map::Situation::IsVersus` (this batch, now parked: the game's own code),
`Force::Get` (not rewritten), and `Rod::CanUseTarget` (2,184 bytes, not rewritten: it stores only into its
own one-time caches, read 2026-11-15). The game ends the last case with a plain branch (B) into
`Rod::CanUseTarget`. That target is a guest function, not an override, so the readable code makes it a
guest call, as `image_unit_at`'s branch into `UnitPool::Get` is (it matched live, 891 records,
docs/MOVE.md 9). The round-10 lesson (a tail branch to an *override* is inlined by 3dsrecomp, so a guest
call there would add a call the original does not make) does not apply: no function here branches into
an override. Whether this holds in the capture library was never checked: the batch was parked before
any live compare.

The two range overrides each fill a one-time cache; the readable code asks those two guards (0x006D9898,
0x006D989C) in its opening test, with its own two (0x006D74C8, 0x006D74C4), so no override gives up
inside it (no nested give-up).

## 7. Not written, and why

- The five score functions and their simulator helpers: they store (section 1).
- `Rod::CanUseTarget` 0x0034AC30: a reader (stores only into its caches) but 2,184 bytes with a branch
  per staff kind. It was a guest call from `rod_can_use_from`.
- `AIBattleSimulator::IsPower0Attack`'s float test: the readable code gave up there (section 2).

## 8. What was proven, and what was not

All numbers are from the logs named; nothing here goes beyond them.

**Host differential test** (`src/readable/ai_score/tests/ai_score_diff.py`: the original ARM code in the
interpreter arm_mini.py against the readable C built with the host gcc, on made-up guest states, r0,
unmapped reads and the ordered list of guest calls with their argument registers compared; a nested
give-up counts as a mismatch). Runs of 2026-11-15 night, on the bodies as they were parked:

| Run | Log (build/readable/ai_score/) | Result |
|---|---|---|
| default seed 20261115, 300 cases per function | park_default.txt | 1,800 cases, 0 mismatches, exit 0 |
| the same, rerun from the parked copy after the rename | park_after.txt | 1,800 cases, 0 mismatches, exit 0 |
| seed 7, 1,500 cases per function | park_seed7.txt | 8,999 cases compared, 0 mismatches; 1 `rod_can_use_from` case the interpreter stopped at its step limit, which the test counts as a failure: **FAILED** |
| `--plant`, 49 planted bugs | park_plant.txt | **46 of 49 caught, FAILED** |

The three planted bugs not caught: 1 (the cached-skill loop one short, `ai_score_sim`), 9 (the seal amount
6 changed to 5, `ai_score_sim`) and 47 (the army check of the revival case, `ai_score_rod`). Nobody has
judged whether any of them is an equivalent change; until then the gate counts them as missed.

Parts of the original the cases reached (park_default.txt): `IsPower0Attack` 223 of 335 words,
`Rod::CanUseDisvalueRange` 189 of 217, `GetRodHealPower` 71 of 105, `versus::Config::Get` 3 of 4,
the other two all of theirs.

**Tier 2** (tools/readable/verify.py, build/readable/verify_ai_score_review/summary.json, run
2026-11-15 14:34; the three bodies were last changed at 13:43, so it ran on the parked code): **0
MISMATCH**.

| Function | Verdict | What that means |
|---|---|---|
| `versus_config_get` | CLEAN | shadow: same r0 |
| `trick_is_destroy_target_castle_offense` | ABI-ONLY | same r0 in shadow; flag and dead-stack differences only |
| `situation_is_versus` | ABI-ONLY | same r0 in shadow; r14, flag and dead-stack differences only |
| `ai_sim_is_power0_attack` | GAVE-UP | the readable code gave up; only the fallback was tested |
| `rod_can_use_from` | GAVE-UP | the same |
| `unit_rod_heal_power` | GAVE-UP | the same |

**Not proven:** anything in the running game. No capture library had these overrides, no live compare
ran, and no robot game met them. The three GAVE-UP functions were never checked against the game
outside the host test.

## 9. The parked files, and how to take the batch up again

- `src/readable/ai_score/ai_score_sim.c.parked`, `ai_score_rod.c.parked`, `ai_score_heal.c.parked`:
  the bodies, renamed from `.c`. Every walker of src/readable/ (tools/readable/stage.py, which
  tools/harness/build.py uses for the capture library; tools/readable/check.py; the other batches' host
  drivers) takes only `*.c`, so none of them sees these. Checked after parking: `stage.py` stages 43
  files and none is from ai_score; `check.py --selftest` and `gen_stubs.py --check` are green.
- `src/readable/ai_score/ai_score.h`: still scanned by check.py's no-disassembly rule; includes only
  `fe.h`; nothing outside this folder includes it.
- `ai_score_diff.py` copies the folder to build/readable/ai_score/parked_src/ with the `.parked` names
  taken off and builds only that copy, so the proof above can be rerun.

To take it up again: name the three files `.c` again, put back the six override rows in
config/readable/functions.csv and config/harness/targets.csv (`kind` override, status unverified; the
targets rows of `ai_sim_is_power0_attack`, `rod_can_use_from` and `unit_rod_heal_power` are guard users),
check that no other batch has meanwhile overridden one of the six addresses (two overrides of one address
do not link), and pass the gates that failed (section 8) before anything else.
