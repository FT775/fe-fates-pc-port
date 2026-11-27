# Growth, level-ups and experience (Fates), read from the game's code

**In plain words.** Every unit carries its own dice seed. When it levels up, the game makes a
fresh dice roller from that seed, saves the roller's next number as the new seed, and then goes
through the eight stats (HP, Str, Mag, Skl, Spd, Lck, Def, Res) in that order: a growth rate of
100 or more gives a sure point per full 100, and the rest is one roll of 0..99. If nothing rose at
all, it rolls the eight stats again, at most four times. A point only counts while the stat is
below its cap. Because the seed lives in the unit and is replaced at every level-up, reloading a
save and fighting again gives exactly the same level-up. Experience comes from small per-difficulty
tables indexed by the level gap.

This page is the readable rewrite's batch 4 (growth, level-up, experience). Everything below was
read in the game's ARM code (objdump of extracted/text.bin, read only, 2026-11-12) and is
confirmed by a host comparison of readable C against that code (section 8) [high unless marked].
Grok's lead list (docs/tracks/BATCH_GROWTH.md) is checked in section 9.

Stat order everywhere: 0 hp, 1 str, 2 mag, 3 skl, 4 spd, 5 lck, 6 def, 7 res.

---

## 1. Who does what (settles BATCH_GROWTH's open question)

| Function | What it really does |
|---|---|
| `GrowSequence::Calculate` 0x001B48E8 | before the window: copies the unit (a new 0x140-byte Unit), cuts the experience amount with `Unit::ExpNormalize`, and does the same for the second unit of the sequence (a pair partner) [med for the partner part] |
| `GrowSequence::GainExp` 0x001B4888 | only starts `ExpSequence::Create(proc, unit, amount, other, other_amount, ...)`: the experience bar. It computes nothing |
| `ExpSequence::Create` 0x001961F0 | adds the experience. When animations are skipped it does it at once: exp + amount; at 100 or more, level + 1 and exp = the rest (mod 100). The animated path (its ProcSequence ticks) was not read [med that it is the same] |
| `GrowSequence::LevelUp` 0x001B48C4 | **only a branch**: if the unit's level is now above the copy's, jump to the level-up step. It applies nothing |
| `GrowSequence::LevelUpCalculate` 0x003D80FC | makes a second copy of the unit, lowers the copy's level by 1, and runs straight into `Unit::LevelUp` on the copy (no call: the code falls through) |
| **`Unit::LevelUp` 0x003D8154** | **the roll and the stat rises** (section 5): seed, level + 1, gains, and a second per-stat counter |
| `GrowSequence::LevelUpReflect` 0x003D4FD0 | copies the rolled copy back into the unit (`Unit::CopyForLevelUp`) and frees the copy |
| `GrowSequence::LevelUpShow`, `LevelUpSequence`, `ProcGrowUp`, `GrowWindow` | the picture; they roll nothing |

So the stats are applied by **`Unit::LevelUp`** (on a copy that `LevelUpReflect` then copies back).
`Unit::CreateImpl` also calls the level-up code when a unit is made above its base level
(docs/TABLES.md "How a unit's stats are computed").

## 2. Growth rate (`Unit::GetGrow` 0x005330B4)

```
rate  = Person.growth[s]
      + boon growth[s] + bane growth[s]                 avatar only (unit::Edit::GetGrow: Personality rows of Edit +0x1A / +0x1B)
child: rate = (rate + parent's rate) / 2                (rounded toward zero; unit::Family::GetGrow)
rate += Job.growth[s]        when Person.unit_kind == 1 (playable characters)
        Job.enemy_growth[s]  otherwise
rate += 10                   with one equipped skill (the EquipSkill number cached at 0x006D9660)
```

The parent's rate (`unit::Family::ParentSingle::GetGrow`): that parent's Person.growth[s] + its
boon and bane growth; when both grandparent words of the record are set, averaged (toward zero)
with one grandparent's Person.growth[s]; never below 0. Which parent record: the child's Person
names a fixed parent (Person.family_index, looked up with `Person::Get`); the first record
(family +0x0) is used when that Person is female, the second (+0x14) otherwise. Nothing is used
when either record or the fixed parent is missing. The child average comes **before** the class
growth is added, so the class growth is never halved. The final rate is not clamped: it can be
negative (then no roll at all) or above 100.

## 3. Stat caps (`Unit::GetLimit` 0x005337F0)

```
cap = Job.max[s] + Person.limit_mod[s]
    + child terms (unit::Family::GetLimit): both parents' limit_mod + their boon and bane limit
      + each parent's two grandparents' limit_mod (when both are set), + 1 for every stat but hp
    + avatar: boon limit[s] + bane limit[s] (unit::Edit::GetLimit)
    + Unit.limit_bonus[s] (Unit +0xD0)
clamped to 0 .. 99
```

A level-up point counts while `Unit::GetCapabilityImpl(s)` (the stat as the game computes it,
section 5) is below this cap.

## 4. Experience

Every amount uses both units' **experience level** (`Unit::GetLevelForCalculateExp` 0x00531F24):
level + Unit +0x12F (a signed per-unit offset) + 6 when the unit, its Person or its Job has one
PersonFlag bit (cached at 0x006D9C88), clamped 1 .. 40. Below, *mine* is the acting unit's, *theirs*
the other unit's. Each table has **one row per difficulty** (GameUserData +0x2D: 0, 1, 2; the row
layouts are in docs/TABLES.md ExpTableHeader .. ExpSupport; values: `python tools/tables/dump.py`
writes them from your own ROM to build/tables/, which git ignores).

ExpMode (second argument; the type is named in the symbol map, its values are not): in modes 2
and 3, *theirs* becomes min(mine, theirs) - 2, clamped 1 .. 38, and a target with no equipped
weapon gives 0 (hit and defeat only); mode 3 also halves the amount (arithmetic shift).

| Amount | Formula |
|---|---|
| Hit (damage), `GetExpDamage` 0x0052D418 | max(ExpBattle.damage[clamp(theirs - mine + 10, 0, 33)], ExpBattleFloor.damage_min[clamp(theirs - 31, 0, 9)]); mode rules; then **on difficulty 2 and above**: minus (target's Unit +0x132 - 2, at least 0), never below 0 |
| Pair partner's share, `GetDualExpDamage` 0x0052F274 | GetExpDamage, halved when it is 2 or more. `GetDualExpDestroy` 0x0052D414 is a one-word NOP that falls into GetExpDamage: the partner's defeat share is the plain hit amount |
| Defeat, `GetExpDestroy` 0x0052E184 | base b = max(ExpBattle.defeat[same index], ExpBattleFloor.defeat_min[same index]); boss (the bool): b + b/2 below 20, else b + 10; then by the defeated unit's PersonFlag bits (unit, Person, Job): three masks add b (at most 20), one takes (b + 1) / 2 off when b >= 2, one of the three also makes it at least 20; mode rules. No difficulty decline |
| Dance / sing, `GetExpDance` 0x0052BAD0 | ExpDance[clamp(mine - 1, 0, 39)] (at most 10 in modes 2/3) + ExpSupport[clamp(theirs - mine + 39, 0, 39)]; mode 3 halves; at least 1 |
| Staff, `GetExpRod` 0x005342F4 | Item.staff_exp (at most 30 in modes 2/3) + ExpRod[clamp(mine - 1, 0, 39)] + ExpRodHigh (once) when the class has a weapon rank limit for any kind but staff (Job.max_weapon_exp) + ExpSupport[gap] when there is a target; mode 3 halves; at least 1 |
| Taking it, `ExpNormalize` 0x0052D34C | at most 100; 0 at or above the level limit; on the last level below the limit, at most what fills the bar to 100 |
| Level limit, `Unit::GetLimitLevel` 0x0052E5EC | `Job::GetLimitLevel` (101 for one class found by its JID; 20 for a promoted class or one that can promote, i.e. Job.promotion[0] set; else 40), + Unit +0x130 x the word at 0x006D96E4 when that limit is above 20 or the class is promoted |
| Gate, `map::Situation::CanGainExp` 0x00527D90 | only forces 0 .. 2; never when Situation +0x17 is 1; else the force's byte (Situation +0x0 + force) == 1 |

Who calls the four amount getters and with which mode (the battle's ProcSequence::Grow, the
dance and staff sequences) was not traced in this batch.

## 5. The level-up (`Unit::LevelUp` 0x003D8154)

1. `Random::Initialize(Unit +0xC0)`: four words from the seed with the Mersenne-twister seeding
   rule (multiplier 0x6C078965), then **20 values thrown away**.
2. One value: stored as the **new seed** (Unit +0xC0). 31 bits (the top bit is cleared).
3. Level + 1 (Unit +0xF1, a byte).
4. Pass loop (at most **4 passes**), each pass over stats 0 .. 7 in order:
   - rate = `Unit::GetGrow(s)`; **rate <= 0: skip the stat (no roll drawn)**.
   - while rate >= 100: rate -= 100, a sure point (needs room under the cap).
   - **one roll** `Random::GetValue(100)` (value mod 100); a point when **roll < rate** (the rest).
     The roll is drawn even when the rest is 0 (rate 100, 200 ...), and then never hits.
   - each point: if `GetCapabilityImpl(s) < GetLimit(s)`, gains[s] + 1 (Unit +0xC8, a byte).
   - when Unit +0x130 is above Person.level_cap (Person +0x86), the points of this pass are also
     added to Unit +0xE0[s] (the byte the stat getters subtract while state bit 30 is set; what the
     two fields mean together is not traced) [med].
   - "something rose" is set by any sure point or any roll that hit, **caps ignored**.
5. If nothing rose, the next pass rolls all eight again; after pass 4 it stops anyway.

The generator (`Random::GetValue` 0x0044AE14) is a 128-bit xorshift (shifts 11, 8, 19);
`GetValue(n)` is value mod n through the RVCT signed division 0x002FFA0C.

**Draws per level-up**, for determinism and for a fixed-growth option: 20 (seeding) + 1 (the new
seed) + one per stat whose rate is above 0, per pass. The caps never change which numbers are
drawn: the dice depend only on the seed and the eight rates. A unit with rates 0 everywhere draws
nothing after the seed and runs four empty passes.

**Fixed growth.** `Unit::LevelUp` is the one place: a fixed-growth mode can keep steps 1-3 (the
seed and the level move on exactly as before, so a later switch back stays deterministic) and
replace step 4 only. The pure plan of step 4 is `growth_level_up_plan` (section 7). Experience
amounts are separate (ExpSequence and the getters above), so an `exp_rate` switch belongs at
`GrowSequence::Calculate` / `ExpNormalize`, not in the roll.

## 6. Stat caps in the roll

The cap check uses `Unit::GetCapabilityImpl(s, no item, false, false, 0)`, a dispatcher (member
pointers at 0x006D9CE0) to the stat getter of the stat (`GetMHPImpl` for hp, `GetStrImpl` ...):
the base stat clamped to its cap (docs/FORMULAS.md section 2) without the extras. Each point
re-reads it, so the second sure point of a 200% rate sees the first. `GetLimit` is section 3.

## 7. The readable code (src/readable/unit/, all **UNVERIFIED**)

Files: `growth.h`, `growth_rates.c`, `growth_exp.c`, `growth_roll.c`; registry rows in
config/readable/functions.csv; harness rows in config/harness/targets.csv (four guard users).

- **23 overrides, all readers:** `unit_grow`, `edit_grow`, `family_grow`, `family_parent_grow`,
  `unit_stat_limit` (`Unit::GetLimit`, until now a guest call of the formula batch), `edit_limit`,
  `family_limit`; the six ExpTable getters; `unit_exp_level`, `unit_exp_damage`,
  `unit_dual_exp_damage`, `unit_exp_destroy`, `unit_exp_dance`, `unit_exp_rod`,
  `unit_exp_normalize`, `unit_level_limit`, `job_level_limit`, `situation_can_gain_exp`.
  Four read one-time caches of their own (`unit_grow`, `unit_exp_level`, `unit_exp_destroy`,
  `job_level_limit`) and six more ask for a callee's cache first (the other experience getters ask
  for the level cache, the level-limit pair for both Job caches); all give up while one is cold,
  before any other read.
  Where the game calls a function that has a readable override, the readable code calls it through
  the guest in the same order with the same arguments (F-018); `ParentSingle::GetGrow`, which the
  game reaches by a branch, runs in C. Words the game reads twice are read twice.
- **5 helpers (F-017: the game functions store):** `growth_random_seed` / `_next` / `_below`
  (the generator on a host-side copy), `growth_level_up_plan` (step 4 without caps: next seed,
  points per pass and stat, passes, draws; pure) and `unit_level_up_preview` (everything
  `Unit::LevelUp` would store: seed, level, gains, the +0xE0 bytes; GetGrow and GetLimit through the
  guest in the game's order). `growth_roll_hits(roll, rate)` is the roll decision as a pure function.
  `GetCapabilityImpl` takes two stack words, which `guest_call` cannot pass, so the preview gets the
  stat from a callback that is given the gains byte the game would have stored by then; a future
  writer (after H6/H8) stores the byte first and calls the real getter.
- Guest calls left: `Person::Get(unsigned short)` (round 27: a tested helper `person_record_get`, docs/PERSON_RECORD.md, not an override, so this guest call still runs the game's code), `Person::IsFemale` (female_person_is_female since round 22, docs/FEMALE.md), `Unit::IsEquipSkill`, `Job::IsHigh`,
  `unit::Item::ToData` (readers or idempotent cache fills).
- New layouts: Unit +0xC0 growth_seed, +0xF1 level, +0xF2 exp, +0x12F exp_level_offset, +0x130
  level_limit_raises, +0x132 exp_decline; GameUserData +0x2D difficulty; Situation +0x17 no_exp;
  FamilyParent (0x14: person, boon, bane, two grandparents); global G_ExpTable 0x006D3804.

## 8. Checks

**Host differential test** `python src/readable/unit/tests/growth_diff.py` (formula_diff's method
and ARM interpreter): made-up states with values outside the game's ranges on purpose (negative
growths, levels 0 and 255, difficulties past 2, modes and bools that are not 0/1, about 1 case in 8
with an unmapped unit). For the overrides it compares r0, the bytes read from unmapped memory, **and
the list of guest calls with their argument registers in order** (ARM side: every BL/BLX to a
listed callee, also inside callees that run as ARM code; C side: every guest call, with another
readable override running when reached). The level-up helpers are compared with the whole of
`Unit::LevelUp` (GetGrow / GetLimit answered by a table, GetCapabilityImpl by "a base + the gains
byte now in memory"), the generator with `Random::Initialize` / `GetValue(void)` / `GetValue(int)`
(negative moduli included). Results: see docs/PORT_PLAN.md (status 2026-11-12, growth batch).

**Tier 2** (`tools/readable/verify.py --rom ...`): see the same status lines.

## 9. Grok's leads (docs/tracks/BATCH_GROWTH.md, OPTIONS_V2.md) checked

| Lead | Verdict |
|---|---|
| `GrowSequence::GainExp` applies the amount (writer) | **refuted**: it only starts `ExpSequence::Create`, which adds the experience |
| `GrowSequence::LevelUpCalculate` is the roll | **partly**: it copies the unit and falls into `Unit::LevelUp`, which rolls |
| `GrowSequence::LevelUp` applies that roll | **refuted**: a level comparison and a jump; `LevelUpReflect` copies the rolled copy back |
| `Unit::LevelUp` vs `GrowSequence::LevelUp` (left open) | **settled**: `Unit::LevelUp` rolls and applies (section 1) |
| Four amount getters, do not hook one only | agrees; two more exist: `GetDualExpDamage` (half) and `GetDualExpDestroy` (= GetExpDamage) |
| `map::Situation::CanGainExp` is a gate, not an amount | agrees (section 4) |
| `unit::Family::ParentSingle::GetGrow` is a child rate | agrees (section 2) |
| The window is not the roll | agrees |
| growth_mode: the level must still advance | agrees, and the seed too (section 5) |
| exp_rate stays separate from growth_mode | agrees; its hook is `GrowSequence::Calculate` / `ExpNormalize` or `ExpSequence::Create`, not `GainExp`'s body |
