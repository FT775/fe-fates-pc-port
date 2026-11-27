# Attack Stance and Guard Stance: how they work, read from the code

**In plain words.** Fates lets two allies help each other in a fight in one of two ways.
Standing *next to* an ally (Attack Stance), the ally adds an extra strike after yours.
Standing *on the same tile* as an ally (Guard Stance, "pair up"), the ally behind gives you
stat bonuses and fills a shared shield gauge; when the gauge is full, the next enemy strike
is blocked. This note says how that works, from the game's own code, and which parts now
have a readable C version (the first step of the readable rewrite, plan step 9).

Status 2026-11-11: 9 readable overrides and 5 helpers written, all **UNVERIFIED** in the
project's sense (no 3dsrecomp verify run and no shadow run yet: that needs the engine
built, owner's OK). Every one of them gives the same answers as the game's own ARM code on
generated inputs (host differential test, section 5). Nothing changes in the game.

Confidence tags: **[high]** read in the code and tested against it, **[med]** read in the
code but its meaning is an inference, **[low]** a guess.

---

## 1. Words

| In this note | In the game's code (symbol map) | What it is |
|---|---|---|
| lead | side 0 or 1 of `map::BattleInfo` | the unit that fights |
| ally behind / follow-up side | side 2 or 3 (lead + 2) | the ally that adds the extra strike, or the partner of a pair |
| Attack Stance | "Dual" (`PersonEnhanceDual`, `CalculateDual`, `ActionDualAttackRequest`) | ally next to the lead, follow-up strike |
| Guard Stance, pair | "Double" (`Unit::DoubleOn`, `PersonEnhanceDouble`, `DoubleInfoWindow`) | two units on one tile |
| shield gauge | `DualGuardGauge`, `Unit +0x135` | the pair's block meter |

So in the code "Dual" means the Attack Stance help and "Double" the pair, with one
exception: the shield gauge is drawn by `DualGuardGauge`. [high for which code is which; the
English menu names are the retail ones, not read from the code]

## 2. Guard Stance (the pair)

**Who may pair** (`Unit::CanDoubleOn` 0x0052B60C) [high]: both units are unpaired, they are in
the same army (force type), and neither the unit, its character record nor its class carries
one particular flag bit that forbids pairing (the bit is looked up once by name and cached).
Pairing stores each unit in the other's `Unit +0xA8` and marks the lead (`+0x8` bit 1) and the
one carried (bit 2) (`Unit::DoubleOn` 0x003D82C0).

**Stat bonus** (`Unit::GetDoubleCapability` 0x00530A34) [high]. The unit behind gives the
lead, per stat:

- its class's pair-up byte for that stat (`Job +0x3C`, the "pair_up" columns of the class
  sheet),
- plus its own Guard Stance rows at the pair's support rank: the character record points to a
  block of 8 signed bytes per support rank (`Person +0x20`, "guard_stance_bonus"); the bonus
  at rank *r* is the sum of rows 0 .. *r*,
- plus the avatar's change (below), or for a child unit the family's numbers instead,
- plus 1 when the lead has one particular skill (looked up once by name and cached).

The pair's move bonus is the class's pair-up byte 0 (`Unit::GetDoubleMovePower` 0x00530680)
[high]: that first column is used for movement, not HP.

**The avatar's change** (`PersonEnhanceDouble::GetEdit` 0x0050D844) [high for the arithmetic,
med for the meaning]. The boon and the bane (`unit::Edit +0x1A`, `+0x1B`, two personality
records) each list three stats. For each of the three pairs where both name a stat and the
two differ, the bane stat's column (rows 1 .. rank) is moved: subtracted from the bane stat,
added to the boon stat. The boon's first stat also gets +1 from rank 4 up.

**The shield gauge** [high unless marked]:

- **Size: 10.** The gauge drawer draws 10 cells and shows the "full" look at 10 or more
  (`game::graphics::DualGuardGauge::Draw` 0x003E7898); the block test is "10 or more".
- **Where it lives.** Each unit keeps its own part (`Unit +0x135`); the pair's gauge is the
  sum of the two parts. A fight copies the parts into four counters, one per side
  (`map::BattleCalculator +0x14`), and writes them back afterwards.
- **Filling, per strike, hit or miss** (`map::BattleCalculator::CalculateAttackSingle`, the
  code at 0x00364530; a miss runs the same code with 0 damage):
  - the *defending* pair gets +1 on each part (2 points), unless the strike was blocked;
  - the *attacking* pair gets +1 on each part while the gauge is below 9; at 9 only the
    smaller part gets +1 (so it stops at exactly 10); at 10 or more nothing;
  - one particular skill on the unit behind adds 1 more point, while the pair is below 10;
  - only when the stance system is on for that army (section 4).
  - Quirk: the defending pair is not capped. A pair at 9 that is struck goes to 11.
- **Blocking** (0x0036378C): when the defending lead is paired and the gauge is 10 or more,
  the strike is blocked (no damage), and the gauge goes back to 0. The hit and critical
  random numbers are still drawn first, so the random sequence advances as if the strike had
  been rolled. Blocking itself is **not** a random roll: it depends only on the gauge.
- **Emptying over time** (`ProcSequence::TurnBegin` 0x003A54D8, the step at 0x003A557C): at
  the start of an army's turn, each of its units that fought as part of a pair since its last
  turn keeps its points (the fight marks both units, `Unit +0x8` bit 23, in
  `BattleCalculator::Calculate` 0x00365488); every other unit loses 1 of its own points. [med
  for how much a whole pair loses: 1 per unit, so 2 for the pair if the carried unit is on the
  army's unit list while it is carried; not traced]

## 3. Attack Stance (the follow-up strike)

**Who joins** [high for the code path, the choice of the ally is not rewritten]: when a lead
is not paired, `map::BattleInfo::ComplementDual` 0x0034746C asks
`map::BattleDualUnitEnumerator` for the adjacent allies and takes one. A paired lead's
partner is the side's "dual unit" instead.

**Whether it strikes** (`map::BattleInfo::CalculateDual` 0x00347350) [high]:

- an adjacent ally (not the partner) strikes, unless the side carries the "no follow-up" flag
  (`BattleSide +0x28` bit 8);
- a pair partner does **not** strike, except when the lead has one particular skill;
- the follow-up side's strike count is cleared when the lead has no strike of its own, or no
  follow-up is allowed.

**Damage: half, confirmed.** `map::BattleInfo::Side::GetSimplePower` 0x005253A8 ends with:
if this side is a follow-up side (`BattleSide +0x28` bit 1, which
`map::BattleInfo::ComplementConditions` sets on sides 2 and 3 only), the damage is halved,
rounded down, and then anything below 0 becomes 0 [high]. Every other damage step (weapon
triangle, skills) comes before the halving; a critical multiplies the halved number
afterwards (`CalculateAttackSingle` 0x003638B4) [med]. This settles the single-source claim
in docs/tracks/rules/RULES.md: **the follow-up deals half of what that ally would deal**.

**The units behind cannot be hurt** [high for the code, med for the wording]: a side's attack
against a follow-up side is stored as 0 (`Side::CalculateDetailAttack` 0x00349880). This
matches the preview's "only the two leads take damage".

**Attack Stance bonus** (`Unit::GetDualSupport` 0x0052E974) [high]: the ally gives the lead,
per battle number (hit, avoid, critical, ...: `BattleCapability::Type`), its own Attack
Stance rows at their support rank: the character record points to a block of 4 signed bytes
per rank (`Person +0x1C`, "attack_stance_bonus"); rank *r* = rows 0 .. *r*. The avatar's
boon and bane name one battle number each (`Personality +0x3C`); when they differ, the
bane's column (rows 1 .. rank) is subtracted from the bane's number and added to the boon's,
scaled by 5/3 or 3/5 when one of them names number 1 (`PersonEnhanceDual::GetEdit`
0x0050CADC) [high for the arithmetic]. A child takes its family's numbers. Applying these
bonuses to the fight (`map::DualSupportCalculator::Calculate`) is not rewritten yet.

## 4. When stances are on at all

`map::Situation::CanDual` 0x005281B8 [high for the test, med for the meaning]: always on,
unless a game-mode bit is set (`GameUserData +0x28` bit 3); then each army is on only if the
map's rules mark it (one byte per army). A map-wide flag turns it on for everyone. The gauge
only fills for armies where this is on.

## 5. Cross-check against docs/tracks/rules/RULES.md

| RULES.md line | Code says | Verdict |
|---|---|---|
| A unit is in one stance or the other | a lead's helper is either its pair partner or an adjacent ally (one "dual unit" per side) | agrees |
| Follow-up always attempts, own hit roll | the follow-up side runs the normal strike code with its own hit roll | agrees [med] |
| Follow-up follows only the first strike | not read (the strike order in `BattleCalculator::Calculate` is not rewritten) | open |
| A Guard Stance pair blocks the follow-up | a strike from a follow-up side is blocked whatever the gauge when the defending side's byte `+0x40` is set; what sets that byte is not traced | possibly; open |
| Follow-up damage is half | halved, rounded down, after all other steps, then floored at 0 | **confirmed** |
| Lead's stats go up by class and support rank | class pair-up byte + the partner's rank rows (+ avatar change, + a skill point) | agrees, more detail |
| Gauge starts empty, holds 10 | 10 cells, block at 10 or more | agrees |
| Full gauge negates the next hit | blocked at 10+, then the gauge empties | agrees |
| A full gauge also blocks the hit's debuff | not read | open |
| +2 per hit dealt or taken, even a miss | +1 per unit of the pair per strike, hit or miss; the attacking pair is capped at 10, the defending pair is not | agrees, with the cap quirk |
| A multi-hit skill adds 2 per hit | each strike runs the gauge code once [med] | likely agrees |
| Falls by 1 at the turn's end if the pair did not fight | at the start of the army's own turn, each unit that did not fight as a pair loses 1 of its points | differs in timing and possibly amount (2 for a whole pair) [med] |
| Both sides paired: only the leads take damage | attack against a follow-up side is 0 | agrees |

For docs/tracks/STANCE_AND_REVIVE.md: the `dual_guard` option assumed "the game's roll".
There is no roll for the block: it is the gauge alone. "Always" and "never" would have to
change the gauge test, not a roll.

## 6. What is rewritten, what waits

Readable C in `src/readable/battle/` (registry: config/readable/functions.csv). Overrides
replace the game function in shadow/readable mode; helpers are the pure part of a bigger
function that also writes memory, and return what the game would write.

| Address | Game function | Readable | Kind | Host diff |
|---|---|---|---|---|
| 0x0050CBE8 | PersonEnhanceDual::GetTotal | stance_attack_bonus_total | override | 0 mismatches |
| 0x0050D968 | PersonEnhanceDouble::GetTotal | stance_guard_bonus_total | override | 0 mismatches |
| 0x0050CADC | PersonEnhanceDual::GetEdit | stance_attack_bonus_edit | override | 0 mismatches |
| 0x0050D844 | PersonEnhanceDouble::GetEdit | stance_guard_bonus_edit | override | 0 mismatches |
| 0x0052E974 | Unit::GetDualSupport | unit_attack_stance_bonus | override | 0 mismatches |
| 0x00530A34 | Unit::GetDoubleCapability | unit_guard_stance_bonus | override (cache: gives up while cold) | 0 mismatches |
| 0x00530680 | Unit::GetDoubleMovePower | unit_guard_stance_move | override | 0 mismatches |
| 0x0052B60C | Unit::CanDoubleOn | unit_can_pair_with | override (cache: gives up while cold) | 0 mismatches |
| 0x005281B8 | map::Situation::CanDual | situation_can_dual | override | 0 mismatches |
| 0x00347350 | map::BattleInfo::CalculateDual | battle_dual_plan | helper (the function writes) | 0 mismatches (whole function) |
| 0x003628BC | BattleCalculator::CalculateAttackSingle | stance_gauge_after_strike, stance_dual_guard_blocks | helpers (gauge and block code regions) | 0 mismatches |
| 0x003A54D8 | ProcSequence::TurnBegin | stance_gauge_at_turn_begin | helper (the per-unit step) | 0 mismatches |
| 0x005253A8 | BattleInfo::Side::GetSimplePower | stance_follow_up_damage | helper (its last step); since round 21 (2026-11-17) the row is the override strike_power (docs/STRIKE.md), which calls this helper | 0 mismatches |

**Waiting** (not written, or written only as helpers):

- The writers: storing the gauge counters, the turn-start decay, `CalculateDual`'s stores,
  `Unit::DoubleOn/DoubleOff`, `map::HpWindow::ShowDualGuardGauge`. Project rule: no readable
  writer until the harness steps H6/H8 are green on Fates. The helpers above already compute
  what they would store.
- Too big for this step: `CalculateAttackSingle` as a whole (10 KB),
  `GetSimplePower` as a whole, `map::DualSupportCalculator::Calculate` (applies the Attack
  Stance bonus), `map::BattleDualUnitEnumerator` (which adjacent ally joins), `ComplementDual`.
- The child/family versions (`unit::Family::GetDualSupport`, `GetDoubleCapability`): still
  called as game code.
- AI (`AIDual::Think`, `AIThink::GetDualScore`, `AIThink::IsDualSupportUnit`), drawing
  (`DualGuardGauge`, `DualSupDrawer`, `BattleInfoWindow::DrawSimpleDual`), animations
  (`ActionDual*`), level-ups of the unit behind (`GrowSequence::Dual*`).

## 7. The test

```bash
python src/readable/battle/tests/stance_diff.py            # 14 functions x 400 cases
python src/readable/battle/tests/stance_diff.py -n 2000 --seed 7
python src/readable/battle/tests/arm_mini.py               # the interpreter's own self-test
```

The project had no way to run original ARM code on the host (no interpreter in
tools/readable or tools/harness, Unicorn not installed), so this test brings a small ARM
interpreter (`src/readable/battle/tests/arm_mini.py`, standard library only). For each
function it makes random guest states (made-up units, character and class records, bonus
blocks, personality records, battle sides and counters), runs the game's ARM code from your
own `extracted/text.bin`, runs the readable C on the same memory (built with the host gcc
against tools/readable/stub/), and compares. Game functions the readable code still calls
(`Person::Get`, `Unit::IsEquipSkill`, `Unit::GetRelianceLevel`, the family versions) answer
from the same random table on both sides; everything else runs as game code. A cache the game
has not filled must make the original reach its one-time guard and the readable code give up.

Results 2026-11-11: 5,600 cases (seed 20261111) and 21,000 cases (seed 7), 0 mismatches.
Planted-bug check: 13 deliberate one-line bugs in the readable code, 13 caught.

What it does not prove: the meanings in this note, or that the generated states are like
the real game's. The tier-2 verify and shadow runs (docs/READABLE.md section 7) still decide
when an override may be switched on.
