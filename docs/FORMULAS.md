# Battle formulas: damage, hit, avoid, critical, read from the code

**In plain words.** When you look at a unit's status window you see Atk, Hit, Avo and Crit, and
when you line up an attack the forecast shows damage, hit %, crit % and whether someone strikes
twice. This note says how Fates computes every one of those numbers, from the game's own code,
and which parts now have a readable C version (the third batch of the readable rewrite, plan step
9, after the stances, the weapon triangle and the dragon veins).

Status 2026-11-11: 21 readable overrides and 2 helpers written (`src/readable/battle/formula_*.c`),
all **UNVERIFIED** in the project's sense. Every one gives the same answers as the game's own ARM
code on made-up cases (section 7), and 31 bugs planted on purpose were all caught. Nothing changes
in the game. The formulas below reproduce the owner's prologue Ryoma screen exactly (section 6).
Real play (2026-11-12, after the formula fix): the robot's live shadow compare on four Birthright
routes gives **0 mismatches of any kind** for every formula override it met (the 0-mismatch goal of
docs/DECISIONS.md F-018 is met; section 7).

Confidence tags: **[high]** read in the code and tested against it, **[med]** read in the code but
its meaning is an inference, **[low]** a guess. No table values are copied here (they are game data);
the table layouts are in docs/TABLES.md. Skill and item flag names are the game's own ID labels
(`SEID_`, `SPID_`, `ISID_`), given in English where their meaning is clear.

---

## 1. Names and call graph (Grok could not name the formula functions; here they are)

All names come from the game's symbol map (config/functions.csv). "Divide" always means the game's
arithmetic shift: rounded down (toward minus infinity), except where "halved toward zero" is said.

**The unit's own numbers** (what the status window shows; the fight starts from them):

| Number | Function | Address | Calls |
|---|---|---|---|
| Strength / Magic / Skill / Speed / Luck | `Unit::GetStrImpl` / `GetPowImpl` / `GetTechImpl` / `GetQuickImpl` / `GetLuckImpl` | 0x0052A80C / 0x0052A500 / 0x0052C30C / 0x0052D860 / 0x0052BC5C | `Unit::GetLimit`, `unit::Edit::GetCapability`, `Unit::GetDoubleCapability` (Guard Stance), `Unit::IsEquipSkill`, `GetEnhanceHave` (carried items), `Unit::GetItemIndexEquipped` |
| Attack | `Unit::GetAttack(const unit::Item*,bool)` | 0x00534188 | `unit::Item::GetPower`, `Item::IsMagic`, Str or Mag, the weapon-rank bonus (docs/TRIANGLE.md) |
| Hit | `Unit::GetHit(const unit::Item*,bool)` | 0x00532DC4 | `unit::Item::GetHit`, Skl, Lck, the weapon-rank bonus |
| Avoid | `Unit::GetAvoid(const unit::Item*)` | 0x00533524 | Spd, Lck |
| Critical | `Unit::GetCritical(const unit::Item*)` | 0x0052B9BC | `unit::Item::GetCritical`, Skl |
| Critical avoid ("dodge") | `Unit::GetSecure(const unit::Item*)` | 0x005345E0 | Lck |
| Attack speed / defense speed | `Unit::GetContinuous` / `Unit::GetUnderContinuous` | 0x0052E134 / 0x00530834 | Spd |
| (by slot) | `GetHit(int,bool)`, `GetAvoid(int)`, `GetCritical(int)`, `GetAttack(int,bool)`, `GetAttackForTerrain(int)` / `(const unit::Item*)` | 0x00532D90, 0x005334F0, 0x0052B988, 0x005342B8, 0x005309A0 / 0x00534180 | slot -1 = the equipped weapon (`GetItemIndexEquipped` 0x005310C0) |

There is no `Unit::GetCriticalAvoid` or `GetDodge`: critical avoid is `GetSecure`.

**The fight and the forecast** (`map::BattleInfo`; the same code for the real fight, the map
forecast, the AI's simulator and the arena, docs/TRIANGLE.md 4):

```
map::BattleInfo::Calculate 0x0034A074
  ComplementConditions 0x00347FA0 -> Side::ComplementConditions 0x003493B0   side flags: magic weapon 0x20, staff 0x40,
                                                                             hindering staff 0x80, siege weapon 0x100,
                                                                             brave 0x800 (when attacking), half drain 0x1000;
                                                                             the terrain under the side (Side +0x20)
  ComplementDual 0x0034746C                                                  who joins as Attack Stance follower
  CalculateDetail 0x003475BC   per side: triangle cell (docs/TRIANGLE.md), then
    Side::CalculateEfficacy 0x0034899C                                       effective? (flag 0x400), killer skill (0x200)
    Side::CalculateDetail 0x00348754
      Side::CalculateDetailAttack 0x00349880  -> Unit::GetAttack
      Side::CalculateDetailDefense 0x00349CF0 -> Unit::GetDefImpl, GetMdefImpl
      Side::CalculateDetailHit 0x00348FF0     -> Unit::GetHit
      Side::CalculateDetailAvoid 0x003491F8   -> Unit::GetAvoid
      (itself)                                -> Unit::GetCritical, GetSecure, GetContinuous, GetUnderContinuous
  CalculateSimple 0x00347C3C   per side: what the forecast shows
    Side::GetSimplePower 0x005253A8  damage of one strike
    Side::GetSimpleHit 0x00525090    shown hit
    (itself)                         shown critical, critical factor
    Side::GetSimpleTimes 0x005259D4  strikes (doubling)
  CalculateDual 0x00347350     Attack Stance follow-up and Guard Stance gauge (docs/STANCES.md)
```

Each side keeps two rows of numbers (`BattleSide.detail`, struct `BattleDetail`, 0x24 bytes):
row 0 against a lead, row 1 against an Attack Stance follower. Against a follower the side gets
no critical and no speed (they stay 0), and the triangle does not count (docs/TRIANGLE.md 4).

**Skill hooks.** Skills enter in four ways [high for the reads, med for which calculator fills
what]:
- inside the stat getters (section 2): `Unit::IsEquipSkill(number)` for +2/+3/+4 skills, the
  "stat absorb" skills, tonics;
- as personal flag bits (`PersonFlag`, `SPID_`) read in GetHit / GetAvoid / GetSimpleHit;
- as bonus words in the side, filled before `CalculateDetail` by the calculators
  `map::EquipSkillCalculator::Calculate` (it writes `BattleSide +0xAC..+0xB2`, the "skill" words
  below), `map::DualSupportCalculator`, `map::TrickEnhanceCalculator`,
  `map::AccessoryEnhanceCalculator` (which of these fills the other bonus words was not traced);
- as the side's active-skill bit set (`BattleSide +0xE6`) read by GetSimplePower, GetSimpleTimes
  and CalculateEfficacy, and as the activated skill number passed to GetSimplePower.

**Terrain bonus.** The side's terrain record (`BattleSide +0x20`) gives avoid (its byte +0x12) and
defense/resistance (byte +0x11), unless the side's flag 0x10 is set (flyers, [med]); three terrain
flag bits restrict it to some units (one EquipSkill cancels a negative terrain bonus; two bits limit
it to the player's or the enemy's allies). Terrain flags 0x200000 / 0x400000 halve / quarter the
damage taken (GetSimplePower). [high for the reads]

**Support bonus.** Fates has no separate support-bonus function in this path: support and stance
bonuses arrive as the side's bonus words (`map::DualSupportCalculator`, docs/STANCES.md) and the
Guard Stance stat bonus inside the stat getters (`GetDoubleCapability`). [med]

## 2. The five stats (Str, Mag, Skl, Spd, Lck) [high]

This confirms docs/TABLES.md "How a unit's stats are computed" and adds the battle extras.
`s` is the stat (1 Str, 2 Mag, 3 Skl, 4 Spd, 5 Lck).

```
base  = Person.base[s] + (avatar: boon/bane, unit::Edit::GetCapability) + Job.base[s] + Unit.gains[s]
        (- Unit.stat_loss[s] while unit state bit 30 is set)
base  = 0 if negative, else at most Unit::GetLimit(s)
        GetLimit = Job.max[s] + Person.limit_mod[s] (+ child / avatar limits) + Unit.limit_bonus[s], 0..99
```

Then, when the getter is asked for extras (its second bool; every battle number asks; the status
window too):

```
Str / Mag only: halved toward zero for one condition bit (Unit +0x28 bit 6 / bit 7), when the third bool is set
+ Guard Stance bonus of the partner behind (Unit::GetDoubleCapability; when the pair bit is set)
+ equipped skills: Str+2/Mag+2/Skl+2/Spd+2 (+2), Lck+4 (+4), a "gouken" skill (+3 Str, -1 Spd),
  a "juuken" skill (+3 Spd), and the "stat absorb" skill of that stat (+ Unit.absorbed[s])
+ rallies and tonics: +1 .. +8 each, by a condition bit or by the rally kind passed in;
  the stat tonic gives 1 more (Lck: 2 more) with the better-tonics skill
+ a mood bit: +2, another: -1
+ the weapon's stat bonus (Item.stat_bonus[s]; the given weapon, or the equipped one)
+ carried-item bonuses (Item.extra_data[s] of every carried item that counts)
- Unit.debuff[s] when the third bool is set
shown = clamped to 0 .. 99
```

## 3. The unit's battle numbers (status window) [high]

```
Attack       = weapon might (+ forge) + (magic weapon ? Mag : Str) + weapon-rank attack bonus      (>= 0)
Hit          = weapon hit (+ forge) + class hit + (3 x Skl + Lck) / 2 + weapon-rank hit bonus
               + 10 / + 20 / + 30 for three personal flag bits                                   (>= 0)
Avoid        = class avoid + (3 x Spd + Lck) / 2 + weapon avoid
               - 20 / - 10 / + 10 / + 20 for four personal flag bits, - 20 for one condition bit  (>= 0)
Critical     = weapon crit (+ forge) + class crit + max(Skl - 4, 0) / 2                           (>= 0)
               (an enemy-army unit gets only half its class crit, unless its state bit 5 is set;
                0 for a weapon with the "no critical, no skill" flag)
Crit avoid   = class dodge + Lck / 2 + weapon dodge                                                (may be negative)
Attack speed = Spd + the weapon's attack speed modifier (Item +0x2A)                              (>= 0)
Defense speed= Spd + the weapon's defense speed modifier (Item +0x2B)                             (>= 0)
```

"Class" numbers are the class sheet's hit/crit/avoid/dodge (Job +0x4C..+0x52); "weapon" numbers
the item sheet (Item +0x1F might, +0x20 hit, +0x22 crit, +0x24 avoid, +0x26 dodge); forge bonuses
come from `ItemRefine`. Without a weapon, Attack, Hit and Critical are 0. The weapon-rank bonus is
added when the bool is set: always in the windows, and in a fight unless the side is at a triangle
disadvantage (docs/TRIANGLE.md 3).

Note: a character's "no critical" / "no avoid" personal flags (the prologue Ryoma has both) are
not read by these functions; the status window shows the full numbers (section 6). Where those flags
act was not traced. [high that they are not read here]

## 4. In a fight (BattleInfo::Side::CalculateDetail*) [high]

For one side against the other (row 0 or 1 as above):

```
attack   = Unit::GetAttack(weapon, not at a triangle disadvantage) + triangle damage (docs/TRIANGLE.md)
           - 4 might for a weapon with the "weaker when not effective" flag, when not effective
           + might again: "double might when attacking" and this side started the fight;
                          "double might when countering" and it did not;
                          "double might when Skl is higher" and its Skl beats the other's
           + 2 x might when effective (so effective = might x 3), else + might for an active killer skill
           + three bonus words                                                              (>= 0)
defense  = Def (Unit::GetDefImpl), resistance = Res (GetMdefImpl)                            (>= 0)
           and separately a defense bonus and a resistance bonus = bonus words + terrain defense
hit      = Unit::GetHit(weapon, not at a disadvantage) + triangle hit
           - 10 for a weapon with the "hit down when not effective" flag, when not effective
           + three bonus words, - 10 for side flag 0x4000                                   (>= 0)
avoid    = Unit::GetAvoid(weapon) + terrain avoid + three bonus words                       (>= 0)
critical = Unit::GetCritical(weapon) + three bonus words, 16-bit                             (>= 0)
           (0 against a follower or for a staff)
crit avoid = Unit::GetSecure(weapon) + three bonus words, 16-bit                             (>= 0)
attack speed  = Unit::GetContinuous + a bonus word      (0 against a follower)
defense speed = Unit::GetUnderContinuous + a bonus word (0 against a follower)
```

**Effective damage** (`Side::CalculateEfficacy`): the side is effective when the weapon's
effectiveness bits (Item +0x34, class categories `JCID_`) meet the target's
`Unit::GetCategory`, minus the categories the target's shield skills cancel (wing shield: flyers,
armor shield: armor, beast shield: beasts); or when a "sword/lance/axe/magic killer" weapon flag
meets a target wielding that weapon kind. Effective = weapon might counted three times. [high]

## 5. The forecast (BattleInfo::CalculateSimple) [high]

```
shown hit      = clamp(own hit - other's avoid, 0, 100)                  (Side::GetSimpleHit)
                 staff (not hindering): 100; hindering staff: 0 against staff immunity, halved against
                 staff resistance, 0 / halved by the status immunity / resistance skills, halved by one
                 game rule bit
shown critical = clamp(own critical - other's crit avoid, 0, 100)
                 0 for a weapon with the "no critical" flag or side flag 0x4000
critical damage factor = 300 % (400 % with the "crit factor up" weapon flag), halved when the
                 other side has the dragonskin skill bit
damage         = own attack - other's (magic weapon ? resistance : defense) - other's matching bonus
                 (Side::GetSimplePower, before any proc skill):
                 halved by the other's dragonskin bit (x 3/4 instead with the "pierces dragonskin"
                 weapon flag), halved by the other's aegis-type skill bit, halved / quartered by the
                 other's terrain bits, halved for an Attack Stance follower                    (>= 0)
strikes        = 0 if the side cannot strike (no weapon, out of range, a siege weapon countering,
                 a magic weapon while silenced, ...); 1; 2 when
                 attack speed >= other's defense speed + 5,                     (Side::GetSimpleTimes)
                 unless the weapon never follows up, either side has the "defensive formation" bit,
                 or the side is a follower
```

**Proc skills in the damage** (GetSimplePower's skill argument; 0 in the forecast) [high for the
code, med for the English names]: Luna ignores half the defense (a quarter against dragonskin;
the bonus part is never ignored); Dragon Fang adds half the attack; Ignis adds half of Mag to a
physical weapon or half of Str to a magic one; Rend Heaven adds half of the other's Str (Mag for a
magic weapon); Vengeance adds the value passed in; Astra halves the damage (35 % with dragonskin).
Against dragonskin each of these additions is a quarter instead of a half.

**Brave weapons** [high for the flag, med for its use]: `Side::ComplementConditions` sets side flag
0x800 when the side started the fight and its weapon has the "attack twice when attacking" flag; the
consecutive strike itself is made by `map::BattleCalculator` (not traced here). The **doubling
threshold is 5**: attack speed at least the other's defense speed + 5 (Item +0x2A / +0x2B let a
weapon change speed differently on attack and defense).

## 6. Cross-check: the owner's prologue Ryoma screen [high]

The owner's screenshot (unmodded, prologue, Raijinto equipped) shows **Atk 29, Crit 20, Hit 110,
Avo 53**. With the decoded data (build/tables, the chapter Person record of prologue Ryoma, his
class, the Raijinto item, WeaponBonus, WeaponLevel; values not copied here), the formulas of
sections 2 and 3 give:

| Shown | Formula | Result |
|---|---|---|
| Atk 29 | might + Str (Person.base + Job.base + the Raijinto's carried-item bonus) + the sword rank bonus at his rank | **29** |
| Hit 110 | weapon hit + class hit + (3 Skl + Lck) / 2 + the sword rank hit bonus at his rank | **110** |
| Crit 20 | weapon crit + class crit + (Skl - 4) / 2 | **20** |
| Avo 53 | class avoid + (3 Spd + Lck) / 2 + weapon avoid (Spd includes the Raijinto's speed bonus) | **53** |

All four agree exactly. Two things this confirms beyond docs/TABLES.md: the item stat bonus (Spd)
is counted inside Avoid, and the character's "no critical" / "no avoid" flags do not change the
window. [high for the arithmetic, med that the window calls exactly these functions: the window's
drawing code was not read]

## 7. What is rewritten, what waits

Readable C in `src/readable/battle/` (`formulas.h`, `formula_stats.c`, `formula_unit.c`,
`formula_forecast.c`; registry config/readable/functions.csv). All overrides are readers; the two
helpers are the pure part of writers and return what the game would store (F-017).

| Address | Game function | Readable | Kind |
|---|---|---|---|
| 0x005310C0 | Unit::GetItemIndexEquipped | unit_equipped_index | override |
| 0x0052A80C | Unit::GetStrImpl | unit_strength | override (4 caches) |
| 0x0052A500 | Unit::GetPowImpl | unit_magic | override (3 caches) |
| 0x0052C30C | Unit::GetTechImpl | unit_skill | override (3 caches) |
| 0x0052D860 | Unit::GetQuickImpl | unit_speed | override (5 caches) |
| 0x0052BC5C | Unit::GetLuckImpl | unit_luck | override (3 caches) |
| 0x00532DC4 / 0x00532D90 | Unit::GetHit (weapon / slot) | unit_hit / unit_hit_of_slot | override (3 caches) |
| 0x00533524 / 0x005334F0 | Unit::GetAvoid | unit_avoid / unit_avoid_of_slot | override (4 caches) |
| 0x0052B9BC / 0x0052B988 | Unit::GetCritical | unit_crit / unit_crit_of_slot | override (1 cache) |
| 0x005345E0 | Unit::GetSecure | unit_crit_avoid | override |
| 0x00534188 / 0x005342B8 | Unit::GetAttack | unit_attack / unit_attack_of_slot | override |
| 0x00534180 / 0x005309A0 | Unit::GetAttackForTerrain | unit_attack_for_terrain / ..._of_slot | override |
| 0x0052E134 / 0x00530834 | Unit::GetContinuous / GetUnderContinuous | unit_attack_speed / unit_defense_speed | override |
| 0x00525090 | Side::GetSimpleHit | forecast_hit | override (5 caches) |
| 0x005259D4 | Side::GetSimpleTimes | forecast_strikes | override (2 caches) |
| 0x00348754 | Side::CalculateDetail | forecast_detail | helper (crit, crit avoid, speeds) |
| 0x00347C3C | BattleInfo::CalculateSimple | forecast_crit | helper (shown critical) |

The stat getters take a fifth argument on the guest stack (the rally kind); the overrides read it
from `sp`. Every override that reads a one-time cache gives up while it is cold (the game then
runs its own code). Because a give-up replays the whole original and tier 2 counts every byte read
from unmapped memory, each function first asks whether every cache it may need is filled (its
own, the stat getters', the weapon-exp limit's) and gives up before reading anything else; this is
sometimes earlier than the game would reach that cache ("early give-up", always safe). `unit_attack` / `unit_hit` compute the weapon-rank bonus from the triangle
batch's readable pieces in the game's order, with its three lookups of the weapon kind, because
tier 2 also counts the bytes read from unmapped memory. Each lookup calls `unit::Item::ToData` and
`ItemSubKind::Get` (0x0019B97C) through the guest, as the game does: the live compare counts the
callee calls (F-018), and doing the table step in C gave 214 `mismatch_calls` records in the join. The triangle batch's helper rows at these
two addresses (`unit_weapon_rank_attack`, `unit_weapon_rank_hit`, still in triangle_tables.c) were
merged into the new override rows (one row per address).

**Host differential test** (`python src/readable/battle/tests/formula_diff.py`): the stance and
triangle tests' method and ARM interpreter. The game's code runs from extracted/text.bin, the
readable C on the same made-up memory: random units, classes, items, tables, sides and caches,
on purpose often outside the game's ranges (negative and huge stats, slots past 4, bools that are
not 0/1, random rally kinds, distances and flags). Only the leaf guest functions are answered by a
table on both sides; the stat getters, the weapon-rank code and GetCritical / GetSecure / speeds
inside CalculateDetail run as real ARM code. For the overrides the test also compares the number
of bytes read from unmapped memory (tier 2's criterion) and the number of `ItemSubKind::Get`
calls, with some units deliberately unmapped
(as in tier 2's made-up state, where the unit pointer is 2). Results: 6,900 cases (seed 20261111) and 23,000 cases
(seed 7), **0 mismatches**; 30 of 30 planted bugs caught. After the formula fix (2026-11-12):
6,900 cases and 34,500 cases (`-n 1500 --seed 7`), 0 mismatches, 31 of 31 planted bugs caught.
**Real play** (2026-11-12, formula fix; docs/PORT_PLAN.md "Status update 2026-11-12 (formula fix)"):
live shadow compare on bt-ch2, bt-ch7, bt-ch8-pair, bt-castle-shop, 2,966 records over 47
overrides, **0 mismatch records of any kind** (`unit_hit` 55 records, `unit_attack` 55; the other
13 met formula overrides all clean). Goal met. **Tier 2** (2026-11-12, all 56
overrides, before and again after the fix): **0 mismatches**; of the 21 formula overrides 1 ABI-ONLY (`unit_equipped_index`), 19
GAVE-UP (verify's caches are cold: only the fallback ran), 1 UNSAMPLED (`unit_avoid`: its code sits
inside GetAvoid(int), which falls into it). So tier 2 here proves the give-ups are clean, not the
formulas; the host test is the evidence for those. Details: docs/READABLE.md section 12.

**Waiting:**
- The writers: `Side::CalculateDetailAttack / Defense / Hit / Avoid`, `CalculateEfficacy`,
  `CalculateSimple` and `CalculateDetail` stores (F-017). `Side::GetSimplePower` is a const
  reader: done in round 21 (2026-11-17) as the override strike_power (docs/STRIKE.md).
- `Unit::GetDefImpl`, `GetMdefImpl`, `GetMHPImpl` (same shape as section 2), `GetLimit`,
  `GetEnhanceHave`, the item forge getters.
- The roll itself (`map::BattleCalculator`: hit roll, critical roll, brave, skill activation).

## 8. For docs/tracks/rules/RULES.md (Grok's file; proposed lines, from code)

The "Hit, avoid, critical, damage" section is a [gap] there. Proposed replacement, all [high, code
2026-11-11]:

- Hit = weapon hit + class hit + (3 x Skl + Lck) / 2 + weapon-rank hit bonus (+ personal +10/20/30).
- Avoid = class avoid + (3 x Spd + Lck) / 2 + weapon avoid (+ personal and terrain).
- Crit = weapon crit + class crit + max(Skl - 4, 0) / 2; an enemy-army unit gets half its class
  crit, unless its unit state bit 5 is set (then the full class crit; section 3).
- Crit avoid = class dodge + Lck / 2 + weapon dodge.
- Displayed hit = hit - target avoid, 0..100; displayed crit = crit - target crit avoid, 0..100.
- Damage = attack - Def (Res for magic weapons) - the matching bonus, at least 0; attack = might +
  Str (Mag) + weapon-rank attack bonus, plus the fight's might changes (section 4). The forecast's
  damage then has the modifiers of section 5: halved by the target's dragonskin bit (x 3/4 with
  the "pierces dragonskin" flag), halved by an aegis-type skill bit, halved / quartered by the
  target's terrain bits, halved for an Attack Stance follower. This line is a summary: for the
  rules page copy sections 2 to 5, not this list alone.
- Effective damage: weapon might counts three times.
- Double attack: attack speed >= target's defense speed + 5 (speed = Spd + weapon modifier).
- Critical damage factor 300 % (400 % with one weapon flag).
