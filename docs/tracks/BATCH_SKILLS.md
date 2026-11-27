# Skills batch — readers first

ELI5 / ETA: This is which skill functions to rewrite first, and which early units already carry one. Nothing is rewritten. Every name is unverified: found in `config/functions.csv` on 2026-11-13, body not read.

No game file opened. Addresses are not copied. A search for `Skill` is still 186 hits in that file. That pile is not this batch.

`docs/tracks/REWRITE_ORDER.md` row 5 said to start at the picture sequence. That row is out of date for this batch. The picture is last.

## Order

1. `Unit::IsEquipSkill` — does this unit have this skill. Reader. The stance code already calls it as a guest. That is the first body to read.
2. `map::battle::detail::HasBattleSkill` — the same question for one side of a fight. Reader. A banner may read this. It must not call the picture.
3. `EquipSkill::Get(short)` and `EquipSkill::Get(const char*)` — the skill row by number or by name. Readers. Not a battle.
4. Stop. The activation chance (a Skill% or Luck% roll) has no function whose name says so. This search looked for `BattleSkill::`, `SkillTrigger`, `InvokeSkill`, `GetSkillInvoke`, and `SkillPercent`, and found none. Do not invent the percent. If it lives inside `map::EquipSkillCalculator::Calculate`, that function is about 14 KB and the formula note says it writes the side's skill words. It is not a first reader.
5. Not this batch: `ProcSkillEffect::Tick`, `Persistent`, and `IsFinished` (the banner picture). `ProcSkillDamage` and `ProcSkillCannon` (the effect pictures). `ActionSkill::Tick`. `SkillIndexProvider::GetSkillEffectName` is a name for a banner, not a rule. A banner that calls any of these is a bug, same as `OPTIONS_V2.md`.

`anonymous_namespace::UnitIsEquipSkill` is a script command. It is not the unit reader. Do not start there.

## Who would call them

A forecast or a fight that already calls `Unit::IsEquipSkill` (the stance bonus does). `HasBattleSkill` is the fight-side check a banner would read. `EquipSkillCalculator::Calculate` is the later writer, after the two readers match. `skill_banners` stays off until one activation is replayed, and even then it only reads.

## What the robot can already meet

Personal skills, from Serenes Forest's Hoshido page, read 2026-11-13. Each is on the unit from the start. [https://serenesforest.net/fire-emblem-fates/hoshidan-characters/personal-skills/]

| Unit | Skill | What the page says | On a route yet? |
|---|---|---|---|
| Sakura | Quiet Strength | allies within 2 tiles take 2 less damage | She joined in chapter 5 and was paired with Corrin for all of chapter 7. A passive, if the distance rule is the body's. Not recorded as a skill hit |
| Rinkah | Fiery Blood | +4 damage when her HP is not full | She has the one recorded level-up, on `bt-ch8`. The log does not say her HP. Do not claim the skill fired |
| Corrin | Supportive | as the support unit, if the lead has a C support: hit +10, damage +2, damage taken -2 | A C support exists. `bt-ch8-pair` made Corrin the support for three turns. Not recorded as a skill hit |
| Kaze | Miraculous Save | as the support unit, Luck% chance to survive a fatal hit at 1 HP | Joined in chapter 4. A Luck% roll. No fatal save is recorded. This is the chance the name search did not find |
| Hana | Fearsome Blow | on her kill, adjacent enemies lose 20% HP | Joined in chapter 7. Not the first reader |
| Hinoka | Rallying Cry | allies within 2 tiles deal 2 more damage | Joined in chapter 8, so she can be on the save. Not required for the first reader |
| Ryoma | Bushido | as the lead, if his level is higher than his partner's: crit +10, damage +2, damage taken -2 | Joins in chapter 13. Do not march there for a skill |

Join chapters are the public chapter list, read the same day. [https://fireemblemwiki.org/wiki/List_of_chapters_in_Fire_Emblem_Fates]

The first live check is not a new chapter. Replay a fight the routes already have: Sakura within 2 tiles of an ally, or Rinkah below full HP. If `IsEquipSkill` is not in that capture, write "not seen" and stop. Do not wait for Ryoma. Do not turn `skill_banners` on.
