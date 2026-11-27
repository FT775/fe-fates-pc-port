# Rewrite order after stances — superseded for the tail

ELI5 / ETA: The next batches are in `docs/tracks/REWRITE_ORDER2.md`. Rows 4, 5, and 6 below are out of date. Do not start skills at the picture, do not treat `GainExp` as the applier, and do not rewrite every `AIThink` name.

ELI5 / ETA: This is the order to rewrite the rules in readable code, after the two stances. Counts are how many times a name showed up in `config/functions.csv` on 2026-11-11, not a census of every function. Nothing is rewritten here.

Status 2026-11-11. Names only. Unverified. Stances are already the batch in progress (`src/readable/battle`). This list starts after that batch replays clean.

A batch stops when a new function adds no behavior the tests can see. Do not raise the depth. Three failed rebuilds of one function, or four hours on one function, means skip it and keep the last good one.

| batch | systems | name hits | unlocks | risk |
|---|---|---|---|---|
| 1. Weapon triangle | the battle rule that reads the triangle table. `WeaponLevel::*` is weapon rank, not the triangle. No function whose name says triangle was in the search (2 hits for `WeaponData` or `Triangle`, neither a battle rule) | not counted. The table layout is already typed | a forecast that shows advantage. Not a new option | a wrong bonus changes every hit. Do not guess the cells |
| 2. Dragon veins | `Unit::CanDragonVein` is the map check. The other hits are the castle sequence (`castle::DragonVeinSequence`, `ProcDragonVein`) | 15 hits on `DragonVein` | `vein_highlight`, after a vein has been seen | a highlight that fires the vein is a bug. The castle sequence is not this batch |
| 3. Damage, hit, crit | `map::BattleInfo` and `map::BattleCalculator` together | 59 hits. That is the whole calculator, not the three formulas. The formula functions were not named in this search | stance forecast numbers, and `animation_skip` only if the result still happens | the formulas are still a gap in `docs/tracks/rules/RULES.md`. Do not rewrite them from a guide |
| 4. Growth and level-up | `GrowSequence` (25 name hits on `GrowSequence::`). `LevelUpSequence` is the window. `Unit::GetGrow` is the rate reader, already named | 25 on `GrowSequence::`, plus the level-up sequence | `growth_display` can read `Unit::GetGrow` once a draw path exists. `growth_mode` still waits on the roll. Experience can ride here: `GrowSequence::GainExp` applies it, and `Unit::GetExpDamage` and the other GetExp names are the amounts | the roll must still advance. `LevelUpShow` is the window, not the roll. Do not hook only one GetExp and call it all experience |
| 5. Skills | start with `map::anonymous_namespace::ProcSkillEffect` (4 name hits) and `SkillIndexProvider::GetSkillEffectName`. A search for Skill was 186 hits and is not this batch | 4 on the picture sequence | `skill_banners`, after one activation has been replayed | a banner that calls the picture sequence is a bug. Do not start on the 186-hit pile |
| 6. AI targeting | `AIThink` | 117 name hits on `AIThink::`. That is the class, not the targeting slice. The named move and heal checks are `HasHealRod`, `IsMoveNear`, `IsMoveOver` | nothing in options v1. Smarter enemies was cut | changing who is attacked changes the chapter. After both finish lines, if it is asked for. Do not start by rewriting all 117 |
| 7. Menus the options need | `map::Panel::Danger` | 4 name hits on `map::Panel::Danger::`, including `Draw` | `danger_zone`, then `hp_bars`, `animation_skip`, `anim_speed`, `keep_game_options` when those draws are named | a draw that writes the game's zone byte, or that skips the hit, is a bug. The HP-bar draw, the battle-picture skip, and the options screen are still unnamed |

## What this order does not do

- Petting scenes, the castle renderer, and `ProcLive2D::AddReliance`. Already out.
- The general gold writer. Still unnamed (`docs/tracks/OPTION_HOOKS.md`). It does not get a batch until a name exists. Experience does: it rides with batch 4.
- A second stance pass. The stance batch is the one already open.

## When it can start

After the stance batch replays one follow-up and one pair, and the card is free. Batch 1 is the triangle, not a chapter clear. Batches 3 and 5 do not start on a guessed formula or on the 186-hit pile.
