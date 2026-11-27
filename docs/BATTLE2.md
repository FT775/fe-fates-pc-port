# Battle numbers, second batch (Fates): one strike's damage, avoid and defense, strike lists, stat bonuses and fight rules, read from the code

**In plain words.** The first battle batch (docs/FORMULAS.md) rewrote a unit's own attack, hit,
avoid and critical and the forecast's hit and strike count. This batch takes the battle numbers
that were still left (docs/tracks/REWRITE_ORDER2.md row 3): the damage of one strike, the avoid and
defense a fight side ends up with once terrain and bonuses are in, who died and how many strikes in
a row one side makes in the fight's strike list, what carried items and the avatar's boon and bane
add to a stat, whether a unit has a stat rally skill, whether a class is promoted or giant, and the
map rules a fight's outcome depends on (casual, phoenix, which deaths and kills are recorded).

Everything here is a **reader** or the pure part of a writer: nothing stores into the game (F-017,
F-021: no writer, nothing armed). A function that stores is named and left out (section 7).

Status 2026-11-15 (round 11 batch `battle_num`), all **UNVERIFIED** in the project's sense:

- **13 readable overrides** (`src/readable/battle2/`, registry and target rows added).
- **2 helpers** (F-017): `battle_detail_avoid` and `battle_detail_defense`, the pure part of
  `map::BattleInfo::Side::CalculateDetailAvoid` and `CalculateDetailDefense`, which store into the
  fight side. They return what the game would store.
- **1 written, tested and waiting for a registry decision**: `forecast_damage`, the whole of
  `map::BattleInfo::Side::GetSimplePower` (section 3). It has no override marker and no row.
  **Update, round 21 (2026-11-17):** the address now has its override, `strike_power` (src/readable/strike/,
  docs/STRIKE.md), with the Ignis and Rend Heaven steps too. Row 0x005253A8 in functions.csv is now
  that override; `stance_follow_up_damage` stays a C function named in its evidence. `forecast_damage`
  here is kept only as a test copy (battle2_diff), with no marker.

Every one gives the same answers as the game's own ARM code on made-up cases (two seeds), with the
same guest calls in the same order and the same unmapped reads; the planted bugs and the tier-2
result are in section 9. Not yet in a live compare: the integrate step rebuilds the capture library
and compares them in real play. Nothing changes in the game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-15) [high unless marked]. No table values or game text are copied here; skill and flag
names are the game's ID labels (`SEID_` = equip skill, `ISID_` = item flag, `SPID_` = PersonFlag
bit) given in English [med for the English].

---

## 1. Where the fight's numbers live

- A fight is a `map::BattleInfo`: four **sides** of 0x200 bytes (lead 0, lead 1, follower 0,
  follower 1; `BattleSide` in config/readable/structs). A side holds its unit (+0x4), its item
  (+0x10), the weapon-triangle result (+0x14), the terrain it stands on (+0x20, a pointer to a
  TerrainTile record or 0), flag bits (+0x28) and two **detail rows** (+0x48, 0x24 bytes each:
  attack, defense, defense bonus, resistance, resistance bonus, hit, critical, avoid, critical
  avoid, the two follow-up speeds). Row 0 is "against the other side's lead", row 1 "against its
  follower"; a side reads row 1 when the side it faces is a follower (type 2 or 3).
- Each side also keeps **skill bits** per row (+0xE6, then +0x17A for row 1): one bit per skill
  number, set when the fight starts. The damage reads the *other* side's bits (Dragonskin and a
  "halve damage" skill).
- The running fight is a `map::BattleCalculator` (+0 the BattleInfo). Its **scene records** are a
  linked list: +0 the next record, +4 the side (0 .. 3), +5 the kind. Kind 1 is a strike and kind 7
  a death [med]; 4, 8 and 9 end a search [low for what they are].

## 2. The strike list (overrides)

- **`map::BattleCalculator::GetDeadUnit`** (0x00525FE0, `battle_dead_unit`): the unit that dies in
  a list of scene records. Walking from the first record: kind 1, 4, 8 or 9 means "no one", kind 7
  gives the unit of that record's side (`info->sides[side].unit`). Asked by the map fight's hit
  effect (`map::SequenceBattle` HitEffect).
- **`map::BattleCalculator::GetAttackContinuousCount`** (0x0052603C, `battle_strike_run`): how
  many strikes in a row a strike record starts: 0 when it is not a strike; else 1 plus every later
  strike of the same side, until a record of another side or of kind 8. The game reads both side
  bytes again for each record, so the readable code does too. Asked when a strike ends
  (`SequenceBattle` AttackEnd).

## 3. One strike's damage (`forecast_damage`, waiting for a registry decision)

**`map::BattleInfo::Side::GetSimplePower`** (0x005253A8). The forecast calls it with skill 0
(`BattleInfo::CalculateSimple`), a strike with the activated skill's number
(`BattleCalculator::CalculateAttackSingle`), the AI's fight preview seven times
(`AIBattleSimulator::CalculateIndication`). It stores nothing.

```
damage = own attack (detail row 0) - the other's defense (resistance when the side's flag 0x20 is set)
         - the other's matching bonus
  Luna:        + half the defense back (a quarter when the other has Dragonskin)
  Dragon Fang: + half of Unit::GetAttack (a quarter against Dragonskin); GetAttack's bool is 1
               unless the side's triangle word is negative
  Ignis:       + half of Str for a magic weapon, of Mag otherwise (a quarter against Dragonskin)
  Rend Heaven: + half of the other's Str (Mag for a magic weapon) (a quarter against Dragonskin)
  Vengeance:   + the value passed in (half against Dragonskin)
  Astra:       halved; x 35 / 100 (toward zero) against Dragonskin
then: Dragonskin on the other side halves it (x 3/4 with an ISID "pierces dragonskin" weapon);
      the other's "halve damage" skill bit halves it;
      the other's terrain attribute bit 21 halves it and bit 22 quarters it;
      an Attack Stance follower (own flag bit 1) deals half;
      below 0 -> 0.
0 at once when the side has no item or its flag 0x40 is set.
```

All halvings are the game's arithmetic shift (they round down, also for negative values). The
nine skill numbers and the item flag are one-time caches; the readable code gives up while one is
cold. This matches docs/FORMULAS.md section 5, now with the exact order of the steps.

**What is not done.** Ignis and Rend Heaven read Str and Mag through `Unit::GetStrImpl` /
`GetPowImpl`, which take a fifth argument on the guest stack; `guest_call` passes only four. For
those two skill numbers the readable code gives up at once (the original runs). A `guest_call5`
is being added to include/readable/fe_guest.h by another round-11 batch (uncommitted in the working
tree today); once it is in, those two steps can be written.

**Why it has no row.** config/readable/functions.csv lists each address once, and 0x005253A8 is
already the address of the stance batch's helper row `stance_follow_up_damage` (the last step,
"a follower deals half, then below 0 is 0"). `forecast_damage` calls that helper for its last step.
To make it an override, the integrate step would turn that row into the override row
`forecast_damage` (source src/readable/battle2/battle2_calc.c), keep `stance_follow_up_damage` as a
C function (and as a named part in the evidence text), add the target row, and add the marker:

```
RECOMP_OVERRIDE(0x005253A8) {
    FE_ENTRY(0x005253A8, forecast_damage, FE_ARG(0), FE_ARG(1), FE_ARG_S(2), FE_ARG_S(3));
}
```

This batch did not do it: the row is the stance batch's, and only own rows may be changed.

**Done in round 21 (2026-11-17)** as planned here, but with a new source: the override is `strike_power`
(src/readable/strike/strike.c, docs/STRIKE.md), not `forecast_damage`.

## 4. Avoid and defense of a fight side (helpers)

Both are the pure part of a writer: the game stores the result into the side's detail row; the
helper returns it and writes nothing (F-017).

**`CalculateDetailAvoid`** (0x003491F8, `battle_detail_avoid`): the avoid a side gets against the
other side's lead or follower:

```
avoid = Unit::GetAvoid(unit, item)
        + the terrain's avoid, when it counts (below)
        + three halfword terms of the side (+0x13C of the row, +0xB0, +0x1F0) [low for their names]
a negative result (as a signed 16-bit number) -> 0; 0 when either side has no unit
```

The game keeps the running value in the 16-bit field, so the unit's avoid and the terrain step are
cut to 16 bits as the game reads them back; the last three additions are added in full and cut
once.

**`CalculateDetailDefense`** (0x00349CF0, `battle_detail_defense`): four numbers:

```
defense    = Unit::GetDefImpl(unit, item, true, true, 0), never below 0
resistance = Unit::GetMdefImpl(unit, item, true, true, 0), never below 0
defense bonus    = side words +0x12C and +0x130 of the row, + side +0x1E8 and +0x1FC
resistance bonus = side words +0x12C and +0x134 of the row, + side +0x1E8 and +0x1FC
both bonuses     + the terrain's defense, when it counts
all four 0 when either side has no unit
```

The two stat getters take a stack argument, so the helper takes their values from its caller.

**When the terrain counts** (both): never without terrain or with the side's flag 0x10; not when
the terrain number is negative on a tile with attribute bit 8 and the unit has a certain skill
(two different skill caches, one for avoid, one for defense) [low for what that skill is]; not on
an attribute-bit-19 tile for a unit allied with force 0; not on a bit-20 tile for a unit allied
with force 1 (`Force::IsAllied`). The game reads the side's terrain pointer again before each test.

## 5. Stat bonuses and the rally skills (overrides)

- **`anonymous_namespace::GetEnhanceHave`** (0x0033A790, `unit_item_stat_bonus`): what carried
  items add to one stat: for each of the five slots whose bonus applies to the unit
  (`Unit::IsItemEnhanceHave(unit, item, false)`), the record's signed byte +0x40 + stat. Every stat
  getter of the formula and sheet batches calls it: the round-10 capture runs logged **35,763**
  guest calls to it from older overrides (build/parallel/r10-cap*/records/*/callbacks.tsv).
- **`unit::Edit::GetCapability`** (0x0053ABEC, `edit_stat_bonus`): what the avatar's boon and bane
  add to one base stat: the boon's Personality record +0xC + stat plus the bane's +0x24 + stat.
  11,565 guest calls from the stat getters in the round-10 runs.
- **`Unit::HasCheerSkillCapability`** (0x00532124, `unit_has_rally_stat_skill`): whether the unit
  has one of nine stat rally skills, asked in a fixed order (`Unit::IsEquipSkill`). The skills
  batch's `unit_has_rally_skill` (`Unit::HasCheerSkill`) calls it: 1,781 guest calls.
- **`unit::Enhance::TstCheerFromCapabilityIndex`** (0x0041B38C, `enhance_has_rally_bonus`): whether
  a unit's rally record holds the rally of stat 1 .. 10 (bit stat + 22) at a strength of at most 2.
  A second branch (stat 31, strength up to 4) can never be taken: 31 + 22 is not a rally bit.
  `Unit::CanItemUse` asks it for the units 1 .. 4 tiles away of the same force [med]. **Reach not
  shown**: no named route is known to make that check [low].

## 6. Fight rules (overrides)

- **`Job::IsHigh`** (0x00524804, `job_is_promoted`) and **`Job::IsGiant`** (0x005249F8,
  `job_is_giant`): the class has the PersonFlag bit "promoted class" / "giant" (one-time cached
  masks). 3,633 and 1,906 guest calls from older overrides in the round-10 runs (the growth batch's
  experience readers and the sheet batch's `unit_is_special_battle`).
- **`map::Situation::IsCasual`** (0x005281F8, `situation_is_casual`): casual mode in the save
  (GameUserData +0x28 bit 2), or else (when the bool is false) the map's rule bit 9.
- **`map::Situation::IsPhoenix`** (0x0052824C, `situation_is_phoenix`): phoenix mode in the save
  (bit 3), unless the map's rule bit 19 turns it off. Asked by the death events (`event::Die`).
- **`map::Situation::IsRecordDead` / `IsRecordKill`** (0x00527E80 / 0x00527EA4,
  `situation_records_death` / `_kill`): force 0 .. 2, the map's per-force byte is 1 and rule bit
  24 (deaths) or 23 (kills) is clear. Asked after a death and before the level-up step of a fight.
- **`map::sound::IsIndividualBattle`** (0x00397FB4, `sound_is_individual_battle`): the kind byte
  (+0x18C) of the fight record the map music keeps (the pointer at 0x006D7F40) is 4 [low for what
  kind 4 means]. Asked by the pinch-music test of every map fight.

GameUserData::Get only returns the word at 0x006DA248; the readable code reads that word directly,
as the stance batch's `situation_can_dual` does.

## 7. Not here, and why

- **Stores into the fight side** (writers): `Side::CalculateDetail`, `CalculateDetailHit`,
  `CalculateDetailAttack` (their pure parts are the formula / triangle helpers already),
  `CalculateEfficacy`, `ComplementConditions`, `BattleInfo::CalculateSimple`, `CalculateDetail`,
  `ComplementDual`, `Clear`, `Calculate`. `CalculateDetailAvoid` / `Defense` only as the helpers above.
- **Random numbers** (writers: the generator's state changes): `map::battle::detail::RandomCalculateHit`,
  `map::sound::util::sGetDeathProbability` (and so `IsPinchBattle`).
- **VFP** (floating point; readable C does not touch VFP registers, so tier 2 would show "vfp state"
  as a difference): `GetHitProbabilityEffectiveDenominator10000` (the shown-hit curve),
  `AIBattleSimulator::IsPower0Attack`, `CalculateKillProbabilityWithoutInterference2/3`,
  `map::ItemHelper::Battle::GetItemIndex`.
- **A stack argument to a callee** (`guest_call` passes four words): `Unit::GetCapabilityRating`,
  `GetNoWeaknessCapabilityRating`, `GetInterferenceRodAvoid`, `unit::Family::GetDualSupport` /
  `GetDoubleCapability`, the script's `UnitGetCapability`; `Unit::GetCapabilityImpl` itself (it
  calls through a table with a stack word). Candidates once `guest_call5` is in.
- **Another batch has it**: `Unit::GetRodHealPower` (0x0052F008) was written here first, then found
  already overridden by the round-11 AI-score batch (`unit_rod_heal_power`, src/readable/ai_score/);
  this batch's copy was removed. `Unit::GetDualExpDestroy` is a 4-byte NOP that falls into
  `GetExpDamage` (growth batch).
- **Reach not shown**: the script readers `UnitGetWeakness` and `UnitTstEnhance` (no BL caller; only
  a chapter script could call them). Left for REWRITE_ORDER2 row 11.
- **Too big for this batch**: `Unit::IsItemEnhanceHave` (2,500 bytes, 12 caches), `Unit::CanItemEquip`
  (3,352 bytes; since rewritten by the equip_use batch, docs/EQUIP_USE.md). Picture and sound ticks (`BattlePhase`, `BattleUnit`, `BattleUtil`): last, per
  REWRITE_ORDER2.

## 8. Checks

**Host differential test:** `python src/readable/battle2/tests/battle2_diff.py` (move_diff.py's
method and ARM interpreter: r0, unmapped reads and the whole ordered list of guest calls with their
argument registers, nested give-ups flagged, a cold one-time cache must make the original reach the
guard and the readable code give up first). The two helpers and `forecast_damage` run through
test-only entries of the generated driver (never a marker in src/readable/); for the helpers the
ARM function runs whole and the value it **stores** is the expected result (the avoid halfword; the
four defense words folded into one number). A tail branch (B) into another override would be run on
as ARM code, unlisted (as move_diff.py now does); none of this batch's functions has one, and none of
its targets is reached by a tail branch (all callers use BL).

Three things in the test were tightened after the first review (round 11, second pass):

- **Early give-ups are checked.** The readable code may give up before reading anything while the
  original runs to the end (always safe: the original runs). The test now accepts that only where
  it must happen (`early_ok`): a cache the function asks first is cold, or, in `forecast_damage`,
  the skill is Ignis or Rend Heaven, or it is Dragon Fang and GetAttack's caches are cold. Any other
  early give-up is a mismatch, so a bug that makes a function give up more often is caught (a
  planted bug of that kind is in the list).
- **Every damage step meets Dragonskin.** Half the `forecast_damage` cases are now focused: all
  caches warm, eight different skill numbers, a weapon, positive damage most of the time, and the
  other side's Dragonskin and halve-damage bits set often in the row the striking side reads (with
  and without the piercing flag). The test prints how often each step met Dragonskin, e.g. seed
  20261115: Astra 21 cases without and 24 with Dragonskin (19 of them with damage above 0), Luna
  20 / 37, Dragon Fang 35 / 27, Vengeance 24 / 18, no skill 43 / 27.
- **Planted bug 5 replaced.** It read the strike's own side byte once instead of once per record.
  That change cannot be seen by any test: the loop makes no guest call and stores nothing, so the
  byte cannot change between reads, and an unreadable side byte (+4) means the kind byte (+5) on the
  same 4 KiB page is unreadable too, so the function returns 0 before the loop. It is replaced by
  "a record of the other side is passed over instead of ending the run", which the strike lists do
  meet. A 39th plant makes `forecast_damage` give up for Astra as well (caught by the early-give-up
  check above).

The planted-bug run is also much faster now: each source is compiled on its own in parallel, and
the other areas' objects are compiled once per run and reused for every plant (a plant rebuilds
only battle2 and the driver: about 3 s instead of about 75 s).

**Tier 2's shadow count of `unit_item_stat_bonus`, explained.** The shadow pass showed 310 unmapped
reads against 440, which none of the existing rules accepted (not exactly twice; a nested override
is logged, but the nested rule wants more than twice). `python src/readable/battle2/tests/shadow_count.py`
rebuilds verify's made-up state exactly as engine/3dsrecomp/src/verify.rs does (the fixed random
heap, the per-function registers; read, not copied) and runs the game's own GetEnhanceHave twice on
the same memory, counting each call's unmapped reads:

```
first run  (caches cold): IsItemEnhanceHave 254 (6 of them in its ToData call), then 4 x 14  = 310 = A
second run (caches warm): 5 x 14 (6 each in ToData)                                          =  70
shadow pass: the original 310 + item_to_data's readable code in its 5 ToData calls 5 x 6
             + the readable GetEnhanceHave after the original (caches warm) 70 + 5 x 6        = 440 = B
```

So both effects are there at once: the readable code of the nested override `item_to_data` adds
reads (the nested rule), and IsItemEnhanceHave's one-time caches, filled by the original first, make
the readable code read less (the round-8 cache rule). Each rule alone rejects 440; the two together
give it exactly. The prediction matches tier 2's numbers exactly (the script exits 0 only then).
tools/readable/check.py now has a rule for exactly this case ("Both at once", next to the other
two): accepted only with the readable pass passing without a give-up, the fault count the only
non-AAPCS difference, this override's and another override's shadow match logged, no MISMATCH line,
A < B < 2A, and a function the override calls that is not a logged override and calls the one-time
guard routine (read from extracted/text.bin; here IsItemEnhanceHave calls __cxa_guard_acquire). It
fails closed without text.bin, a function row or the guard address. 13 self-test cases cover it
(the real 310 / 440 case passes; without the guard call, with the cache only in a logged override,
with the cache function itself logged, without a call graph, without a surplus, with an r0 or
memory difference, with a callee's MISMATCH, after a give-up, or with a readable pass that differs,
it stays a MISMATCH or GAVE-UP).

Results: see section 9.

**Callers that now reach these overrides.** The stat getters (formula, sheet batches) reach
`unit_item_stat_bonus` and `edit_stat_bonus` (no caches: no give-up possible); the growth batch's
experience reader reaches `job_is_promoted`, the sheet batch's `unit_is_special_battle` reaches
`job_is_giant`, and the skills batch's `unit_has_rally_skill` reaches `unit_has_rally_stat_skill`.
Those three read one-time caches; while one is cold (only before the game's first call of that
function) they give up inside the caller, and the caller's original then runs (safe, F-017). The
callers' owners may add the guard check first, as move.h does for `Unit::GetCategory`; not done
here (their files).

## 9. Results (2026-11-15, second pass after the review)

- Host test, seed 20261115, 300 cases per function, with `--plant`: **4,800 cases, 0 mismatches,
  39/39 planted bugs caught** (the plants run on 300 cases per function of seed 20261116; 5 min 50 s).
- Host test, seed 7, 300 cases per function, with `--plant`: **4,800 cases, 0 mismatches, 39/39
  planted bugs caught** (plants on seed 8; 4 min 38 s).
- The first review's run (seed 7, plants on 150 cases) caught only 36 of 38: plant 5 (cannot be seen
  by any test, replaced, section 8) and plant 12 (Astra against Dragonskin, almost never met; the
  focused cases fix that). A first rerun after the fixes still missed the "last rally guard not
  asked" plant on seed 7, so the rally, class-guard and rally-bit cases were made to meet their edge
  cases more often and the plants now run on as many cases as the main run. In both final runs every
  plant gives at least 4 mismatches.
- forecast_damage gives up early in 26 (seed 20261115) and 30 (seed 7) of 300 cases, every one of
  them allowed by `early_ok`.
- Tier 2 (`tools/readable/verify.py --skip-build`, the 13 override addresses, build/readable/verify_battle2,
  the library built from the same battle2 sources): **10 ABI-ONLY, 3 GAVE-UP, 0 MISMATCH**
  (`readable-verify: OK`). GAVE-UP: job_is_promoted, job_is_giant, unit_has_rally_stat_skill (their
  caches are cold in verify's made-up memory: proves nothing either way). `unit_item_stat_bonus` is
  ABI-ONLY through the new "Both at once" rule, its 310 / 440 explained exactly in section 8
  (`shadow_count.py`: OK).
- `python tools/readable/check.py --selftest`: readable OK (lint 271 rows 0 problems, 46 sources,
  host 146/146, capture 568/568, undo 554/554, self-test 27/27 broken inputs and 81 verdict
  combinations, verify pipeline 28/28). `python tools/harness/gen_stubs.py --check`: OK.

**Re-checked (round 11 continuation, same day).** The round-11 stop left a note that
`unit_item_stat_bonus` still showed a tier-2 MISMATCH (shadow pass, 310 against 440, memory at
0x0FFFEFD4). That note was older than the "Both at once" rule above; the memory difference is dead
stack (below sp 0x0FFFF000), which the classifier already allows. Rerun with no source change:
`verify.py --skip-build --out build/readable/verify_battle2 --only <the 13 addresses>`:
10 ABI-ONLY, 3 GAVE-UP, 0 MISMATCH (`readable-verify: OK`); `shadow_count.py`: OK (predicted
310 / 440 = logged 310 / 440); host test seeds 20261115 and 7 with `--plant`: 4,800 cases,
0 mismatches, 39/39 planted bugs caught each (early give-ups 26 and 30, as above);
`check.py --selftest`: readable OK; `gen_stubs.py --check`: OK. The two seeds must not run at the
same time: both write build/readable/battle2/plant/ (a parallel run fails to link, it is not a
test result).
