# Skills (Fates), read from the game's code

**In plain words.** A unit "has" a skill when it is its personal skill or one of its five equipped
skills; nothing else counts. The personal skill can differ per difficulty (the Person record keeps
one per difficulty). Classes do not give skills by themselves: a class only says which skill a unit
learns at levels 1/10/25/35 (or 5/15 for a promoted class), and a learned skill sits in the unit's
pool until it is equipped. Every skill is a row of the Skill table, and that row holds the
*activation rate* as data (which stat, times a factor, divided by a divisor). What a skill *does* is
always code: each function that implements a skill looks the skill up once by its ID label and
then asks "does this unit have it". In a fight, attack skills (Lethality, Aether, Astra, Dragon
Fang, Sol, Luna, Ignis, Rend Heaven, Vengeance) are tried one after another; for each one the unit
has, the game throws one 100-sided die **before** it computes the chance, and the skill fires when
the chance is above the die. The first skill that fires ends the list. The dice come from the same
battle dice roller as the hit and critical rolls, so a skill the unit has changes every later roll
of the fight even when it does not fire.

This page is the readable rewrite's batch 5 (skill readers, read only). Everything below was read
in the game's ARM code (objdump of extracted/text.bin, read only, 2026-11-13) and the functions
marked *readable* are confirmed by a host comparison of readable C against that code (section 7)
[high unless marked]. Skill names: the game's own ID labels (SEID_ = an equip skill, SPID_ = a
PersonFlag bit, ISID_ = an item flag bit), given here by their usual English names [med for the
English names; the labels themselves are high]. No values of the Skill table are copied here
(`python tools/tables/dump.py` writes them from your own ROM to build/tables/).

Grok's batch-5 lead (docs/tracks/REWRITE_ORDER.md row 5) is checked in section 8. Grok's
docs/tracks/BATCH_SKILLS.md and ROBOT_NEXT2.md did not exist when this was written.

---

## 1. Who has which skill

| Function | What it does | Readable |
|---|---|---|
| `Unit::IsEquipSkill(short)` 0x0052DD04 | 0 for skill 0; else 1 when the skill equals Person.personal_skill[difficulty] (Person +0x74 + 2 x GameUserData +0x2D) or one of the five equipped slots Unit +0xFE, +0x100, +0x102, +0x104, +0x106 (s16 each). It stops at the first match, and it compares the whole register (a caller passing 0x10003 never matches skill 3) | `unit_has_skill` |
| `Unit::GetIndividualSkill` 0x00530814 | the personal skill for the difficulty now | `unit_personal_skill` |
| `Unit::GetHasEquipSkillNum` 0x00530B90 | how many of the five slots are not 0 | `unit_equipped_skill_count` |
| `Job::GetEquipSkill(int level)` 0x00524224 | the skill a class teaches at a level: promoted class (SPID "promoted class" bit in Job.flags): level 5 -> Job +0x54, 15 -> +0x56; any other class: 1 -> +0x54, 10 -> +0x56, 25 -> +0x58, 35 -> +0x5A; else 0 | `job_class_skill` |
| `unit::EquipSkillPool::Tst(int)` 0x0053AA74 | the learned-skill pool: one bit per *common* skill; 0 for a number at or past `EquipSkill::GetCommonNum`, else the pool's byte (number >> 3, sign kept) AND the bit (the masked byte, not 0/1) | `skill_pool_test` |
| `EquipSkill::Get(short)` 0x001758E4, `GetNum`, `GetCommonNum` | the Skill record (table + number x 0x20, no range check) and the two counts kept by `EquipSkill::Initialize` | `skill_record`, `skill_total`, `skill_common_total` |
| `EquipSkill::IsUnknown` 0x00506034 | "???" in the menus: a record of kind 5 whose name label has no message entry (or one whose word +0xC is 0) | `skill_is_unknown` |
| script `UnitIsEquipSkill(index, "SEID_..")` 0x003AB148 | the event script's test: pool index 1 .. 250, not a unit of force 9, then `IsEquipSkill` of the label's number | `script_unit_has_skill` |
| `Unit::HasCheerSkillMove` 0x0052F9F8, `Unit::HasCheerSkill` 0x0052E6E4 | the movement rally skill; any rally skill (a stat rally, asked through `HasCheerSkillCapability`, or the movement rally) | `unit_has_rally_move_skill`, `unit_has_rally_skill` |
| `map::battle::detail::HasBattleSkill(info, side, skill)` 0x003A34B4 | in a fight: the side's unit has the skill, or the unit has **Nohrian Trust** (SEID "Nohr") and the unit of its pair side (lead 0/1 <-> follower 2/3) has it | `battle_side_has_skill` |
| `map::battle::detail::IsInvalidKill(unit)` 0x003A3360 | Lethality cannot kill: a PersonFlag bit (SPID "Lethality immune") on the unit, its Person or its Job, or Dragonskin, or a second shield skill (SEID 神盾; meaning not traced) | `unit_lethality_immune` |
| `SkillIndexProvider::GetSkillEffectName(int)` 0x00211BC4 | the name of a skill's activation effect ("Skl_..." strings in the code), for 23 skills whose numbers `SkillIndexProvider::Initialize` stored by label; Aether's number is stored but never asked (it shows as Sol, then Luna); Aegis and Brynhildr share one effect; 0 for the rest | `skill_effect_name` |

**Data vs code.** The Skill table (229 records, docs/TABLES.md "Skill") is data: name, help, icon,
the activation stat / factor / divisor, a kind byte. Everything a skill *does* is code: 135
functions look a skill up by its label (`EquipSkill::Get(const char*)`, 514 call sites) and 129
functions ask `Unit::IsEquipSkill` (410 call sites). A mod can change an activation rate in the
table; it cannot give a new skill an effect without code.

## 2. Passive skills that feed the battle numbers (and which readable paths reach them)

These are `IsEquipSkill` checks inside the getters (docs/FORMULAS.md sections 1-3, docs/GROWTH.md 2):

| Where | Skills | Already readable (batch) |
|---|---|---|
| the five stat getters `GetStrImpl` .. `GetLuckImpl` | Str/Mag/Skl/Spd +2, Lck +4, "gouken" (+3 Str), "juuken" (+3 Spd, -1 elsewhere), the "stat absorb" skills, better tonics | yes, formula batch: `unit_strength` .. `unit_luck` call `IsEquipSkill` through the guest, which now reaches `unit_has_skill` |
| `Side::GetSimpleHit` (forecast hit) | status immunity / resistance skills | yes, `forecast_hit` (formula batch) |
| `Unit::GetDoubleCapability`, `CalculateDual`, the gauge step | pair-up and stance skills | yes, stance batch |
| `Unit::GetGrow` | +10 to every growth with one skill | yes, `unit_grow` (growth batch) |
| `GetDefImpl`, `GetMdefImpl`, `GetMHPImpl`, `GetMovePower`, range getters, heal power | the other stat / move / range skills | not yet (no readable override) |
| `map::EquipSkillCalculator::Calculate` (14 KB, 85 `IsEquipSkill` calls) | the skill bonus words of a side (hit, crit, avoid, crit avoid at BattleSide +0xAC..+0xB2) and the active-skill bits (+0xE6) | not yet: a writer (it fills the side), and far too large for this batch |
| `Side::GetSimplePower` | Luna, Dragon Fang, Ignis, Rend Heaven, Vengeance, Astra damage (FORMULAS section 5) | done in round 21 (2026-11-17): override strike_power (docs/STRIKE.md) |

So the readable stat, hit, stance and growth readers already reach the skill check; with this batch
that check itself is readable (`unit_has_skill`), and every guest call of it in those readers now
runs readable code in shadow and capture modes.

## 3. The activation chance (`Unit::GetEquipSkillProbability(short skill, bool quixotic)` 0x005324B8)

```
record = EquipSkill::Get(skill)
0 when record.trigger_stat (Skill +0x16) is 0             (not an activation skill; nothing else read)
c = stat * record.trigger_factor / record.trigger_divisor   stat = GetCapabilityImpl(trigger_stat, no item,
                                                            true, true, 0): the stat with every extra;
                                                            signed division toward zero
c += 10    the unit has Hoshidan Unity (SEID "Hoshido")
c += 15    the bool: Quixotic active on either side (CalculateAttack passes it)
c += 20    a luck-based skill (trigger_stat 5) and the unit has the luck charm skill (SEID 幸運のおまじない)
c = clamp(c, 0, 100)
c = 100    PersonFlag "forced skill activation" on the unit, its Person or its Job
c = 0      PersonFlag "skill activation forbidden" (checked last: it wins over "forced")
```

Stat numbers: 1 Str, 2 Mag, 3 Skl, 4 Spd, 5 Lck (docs/FORMULAS.md 2). The function rolls nothing.
Its callers: `map::BattleCalculator::CalculateAttack` (9 calls), `CalculateAttackSingle` (6) and
`AIBattleSimulator::CalculateIndication` (11, the AI's estimate).

## 4. How an attack skill is rolled (`map::BattleCalculator::CalculateAttack(side)` 0x00361F70)

For one attack of one side, before its strikes:

1. **No roll at all** for a follower side (2, 3; any side above 1), for a weapon with the item flag
   ISID "no critical, no skill", or with side flag 0x100 or 0x4000 (BattleSide +0x28; meaning not
   traced). Then the strike is made with skill 0.
2. Quixotic (the chance bonus of step 3) counts when its bit is set in this side's active-skill bits
   (BattleSide +0xE6) or the other lead side's.
3. The nine attack skills, always in this order: **Lethality** (only when the side's power,
   BattleSide +0x2C, is above 0), **Aether, Astra, Dragon Fang, Sol, Luna, Ignis, Rend Heaven,
   Vengeance**. For each:
   - `HasBattleSkill(side, skill)` (own skill, or the pair side's with Nohrian Trust); if not:
     next skill, **no die thrown**;
   - **one die** `Random::GetValue(100)` from the battle dice roller (G_BattleRandom 0x00752B8C),
     thrown **before** the chance is computed;
   - `GetEquipSkillProbability(unit, skill, quixotic)`; the skill **fires when chance > die**
     (chance 100 always fires, chance 0 never);
   - the first skill that fires ends the list: the game makes a new scene (side, kind 4, skill).
4. Strikes (`CalculateAttackSingle`, a writer): Astra strikes up to 5 times; Aether strikes as Sol,
   then (if the first strike did not end the fight) as Luna; any other skill (or none) strikes once.

**Number of dice per attack:** 0 when step 1 applies; else one per attack skill the side has,
counted in the order above, up to and including the one that fires. A side with Sol and Luna whose
Sol fires throws 1 die; whose Sol fails throws 2. Having a skill is enough to move the dice, so
equipping or removing an attack skill changes every later roll of that fight.

**The strike's own dice** (`CalculateAttackSingle` 0x003628BC, read for the order only [med]): the
hit roll `map::battle::detail::RandomCalculateHit(hit)` throws one die of 0 .. 9999 from the same
roller and hits when it is below hit x 100, raised above hit 50 by a sine-shaped amount (so a shown
hit above 50 lands more often than shown; round 80 reproduced the curve: the threshold out of 10000
for every shown 0 .. 100 equals the game's own `GetHitProbabilityEffectiveDenominator10000` 0x003A361C,
called on the guest, 101/101 (for example 70 -> 7887, 90 -> 9705; 50 and below are plain hit x 100;
build/r80/hit/true_hit_table.json, F-065); on a hit, one
more die 0 .. 99 for the critical; then up to six defensive skills (Pavise-type shields, Miracle and
others looked up in that function) each throw a die before their chance, as in step 3. Not
rewritten in this batch: the whole function is a writer.

## 5. What the readable code computes (`src/readable/skill/`, all **UNVERIFIED**)

Files: `skills.h`, `skill_has.c`, `skill_battle.c`; registry rows in config/readable/functions.csv,
harness rows in config/harness/targets.csv (`gen_stubs.py --check`: 94 overrides, 24 guard users).

- **15 overrides, all readers:** the twelve "has" readers of section 1 and `battle_side_has_skill`,
  `unit_lethality_immune`, `skill_effect_name`. Five read one-time caches (`job_class_skill`,
  both rally readers, `battle_side_has_skill`, `unit_lethality_immune`): they ask every cache they
  need first and give up before reading anything else; `unit_has_rally_skill` asks its cache
  before the stat-rally call the game makes first (an early give-up is always safe).
- **2 helpers (F-017):** `unit_skill_chance` (section 3; `GetCapabilityImpl` takes two stack words,
  which `guest_call` cannot pass, so the stat comes from a callback, as in the growth batch's
  level-up preview) and `battle_attack_skill_pick` (section 4: the skill that fires, the dice
  thrown on a host copy of the battle roller, its four words afterwards, what the new scene would
  hold and which skill the strikes get). Neither writes anything.
- Where the game calls a function that has a readable override (`IsEquipSkill`,
  `EquipSkill::Get(short)`, `GetCommonNum`, `HasBattleSkill`), the readable code calls it through
  the guest in the game's order with the game's arguments (F-018). The script reader reaches
  `IsEquipSkill` by a branch in the game, so it runs it in C. The attack choice reads the
  calculator's BattleInfo pointer again for every `HasBattleSkill` call, as the game does.
- Guest calls left (readers): `UnitPool::Get`, `EquipSkill::Get(const char*)` (since round 26 a readable
  override, `skill_record_by_name`, docs/SKILL_RECORD.md, that the guest call now reaches),
  `IdentHash::GetIdent`, `Unit::HasCheerSkillCapability`, `unit::Item::ToData`.
- New layouts: Unit +0xFE `equip_skills` (s16[5]); structs EquipSkillTable (G_EquipSkill
  0x006D3C5C), SkillIndexProvider (G_SkillIndexProvider 0x006BC0AC), GameRandom (G_BattleRandom
  0x00752B8C); global G_IdentHash 0x006DCB44.

**For `skill_banners`** (Grok's option): a banner may read `battle_attack_skill_pick`'s result (or
the scene's skill) and `skill_effect_name`; it must never call the picture sequence
(`ProcSkillEffect`, below) nor throw a die.

## 6. Not this batch

- `map::anonymous_namespace::ProcSkillEffect` (Persistent 0x003730E0, Tick, IsFinished 0x00506678)
  is the activation **picture**: `IsFinished` is a two-word stub that falls into a function asking
  `ObjectManager::Get` and `EffectNode::IsFinished`. It is the picture sequence REWRITE_ORDER warns
  about; not rewritten.
- `map::EquipSkillCalculator::Calculate` / `CalculateAround` (the skill bonus words; writers, 14 KB),
  `CalculateAttackSingle` (the strike, its defensive skills), `GetSimplePower` (proc damage),
  `GrowSequence::GainSkill` (learning), `Unit::AddEquipSkill` / `InheritEquipSkill` (writers).
- The 186-hit "Skill" name pile (REWRITE_ORDER): only the readers above were taken from it.

## 7. Checks

**Host differential test** `python src/readable/skill/tests/skill_diff.py` (the growth test's method
and ARM interpreter): made-up states with values outside the game's ranges on purpose (skill numbers
that do not fit a short, difficulties past 2, levels and pool indexes negative or huge, side numbers
past 3, bools not 0/1, unmapped units, and "torn" units whose record stops at an offset the readers
read, so a read the game skips shows as a fault count). For the overrides it compares r0, the bytes
read from unmapped memory and the list of guest calls with their argument registers in order; a
nested give-up (a guest call of another readable function giving up inside while the outer one goes
on) is a mismatch. `unit_skill_chance` is compared with the whole of `GetEquipSkillProbability`
(the `GetCapabilityImpl` stub also checks the two stack words), `battle_attack_skill_pick` with the
whole of `CalculateAttack` (scene, dice count, the roller's four words, strike calls, unmapped reads,
guest calls). Results: docs/PORT_PLAN.md, status update 2026-11-13 (skills batch).

**Tier 2** (`tools/readable/verify.py --rom ...`): see the same status update.

## 8. Grok's lead (docs/tracks/REWRITE_ORDER.md row 5) checked

| Lead | Verdict |
|---|---|
| start with `map::anonymous_namespace::ProcSkillEffect` | **refuted as a start**: it is the activation picture (section 6), nothing a reader or a banner option should call; not rewritten |
| and `SkillIndexProvider::GetSkillEffectName` | **agrees**: a pure reader of 23 stored skill numbers returning effect names; rewritten (`skill_effect_name`) |
| "4 on the picture sequence" | agrees: Persistent, Tick, the destructor and IsFinished |
| a banner that calls the picture sequence is a bug | agrees; the readable pieces a banner needs are `battle_attack_skill_pick` and `skill_effect_name` (section 5) |
| do not start on the 186-hit pile | kept: 15 small readers and 2 helpers taken from it, no writer |
| `skill_banners` after one activation has been replayed | open: no robot route is known to replay an activation yet; the overrides were not run in a live compare in this batch |
