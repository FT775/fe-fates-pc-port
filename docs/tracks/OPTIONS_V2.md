# Options list v2

ELI5 / ETA: The first options list did not know the battle math. This page names the functions the readable code now has, says which ones only read, and adds a few switches that can draw a number without changing the fight. Nothing is hooked. Every switch still defaults to off.

Status 2026-11-12. Design only. v1 (`docs/tracks/OPTIONS_V1.md`) still holds the file rules and the keys already agreed. This page does not replace those rules. Off is still the original game. A display switch never marks a save. A run switch still waits on the two gates in v1 (replay-clean, and the undo log).

Names below are the ones the readable notes already use. Addresses are not copied. A name is not a second reading of the body. The review the same day (`docs/collab/reviews/REVIEW_2026-11-12.md`) found no writer that stores. Do not treat a helper as a licence to store.

Do not copy `docs/FORMULAS.md` section 8 into a switch. It drops the enemy-crit exception (state bit 5) and the fight modifiers. Use section 2 and section 5 of that note.

## What the code now names

| fact | function | read or write | robot before a display switch may use it |
|---|---|---|---|
| Hit, avoid, crit, crit avoid, attack | `Unit::GetHit`, `Unit::GetAvoid`, `Unit::GetCritical`, `Unit::GetSecure`, `Unit::GetAttack` | readers. Overrides. The fight passes a bool: add the weapon-rank bonus only when not at a triangle disadvantage | one forecast the robot has replayed (`ROBOT_PLAN.md` row 2) |
| Shown hit, shown crit, strikes | `Side::GetSimpleHit`, the crit helper of `BattleInfo::CalculateSimple`, `Side::GetSimpleTimes` | readers. The doubling line is attack speed at least the other side's defense speed + 5 | the same forecast |
| One-strike damage | `Side::GetSimplePower` | reader, override strike_power since round 21 (2026-11-17) (docs/STRIKE.md). The follower-half step is a helper and does not store | not yet. Do not invent the damage line from section 8 |
| Triangle cell and rank bonus | the helpers in the triangle batch. The bonus uses the advantaged unit's rank. A disadvantage also drops that unit's own rank bonus (`triangle >= 0` is the bool) | helpers. The stores in `CalculateDetail` still wait | one forecast, and the switch must not store the cell |
| Who may use a vein | `Unit::CanDragonVein` | reader. Override. One flag, plus the download rule when state bit 28 is set. No per-turn "used" flag | one vein the robot has seen (`ROBOT_PLAN.md` row 10). The highlight must not call `Done` or the vein event |
| Vein marks | the `SetDeploy` helper | returns the marks. Writes nothing. `SetDeploy` itself still waits | the same vein. A mark is not a use |
| Stance gauge | the turn-begin and after-strike helpers | return what the game would store. They do not store. `map::BattleInfo::CalculateDual` is still a writer | one pair the robot has replayed (`ROBOT_PLAN.md` row 12). A forecast that calls `CalculateDual` is still a bug |
| Pair allowed | `map::Situation::CanDual` | reader. Override | the same pair |

`Unit::GetAttack` and `Unit::GetHit` as whole overrides exist. They still give up while a cache is cold, and the fight's own store of the triangle cell is not rewritten. A display switch calls the reader. It does not replace the fight.

## v1 keys, with the names filled in

Only the rows the new code changes. The other v1 rows stay as in `OPTIONS_V1.md` and `OPTION_HOOKS.md`.

| key | now | still blocked |
|---|---|---|
| `stance_forecast` | may read `Unit::GetDualSupport` and `Unit::GetDoubleCapability`, and the gauge helper's returned points. Must not call `CalculateDual` | one replayed battle, then one replayed pair before the gauge number is shown |
| `vein_highlight` | may read `Unit::CanDragonVein` and the mark helper. Must not call `SetDeploy`, `Done`, or the vein event | one vein seen |
| `growth_display` | `Unit::GetGrow` is still the rate reader. The formula batch did not rewrite the roll | unchanged. Not this page's new switches |
| `growth_mode`, `exp_rate` | still writers. `GainExp` does not apply the amount. See the recheck | not unblocked by the formula readers |
| `dual_strike`, `dual_guard` | still appliers. The readers above are not the roll | one follow-up, one pair, plus the two gates |

True hit stays cut. The shown hit is a reader. The hit roll is `map::BattleCalculator`, and that note says it is not traced. No reading shows the forecast and the roll disagree.

## New switches these facts make cheap

Display only. Default 0. No save mark. Off during capture. Each one is a draw on top of a reader. If the draw calls a writer, it is a bug, same as v1.

| key | values | draws | must not | robot |
|---|---|---|---|---|
| `forecast_hit` | 0 off, 1 show the shown hit and shown crit beside the forecast | `Side::GetSimpleHit` and the crit helper | call `GetSimplePower`, or store a detail row | one replayed forecast |
| `forecast_strikes` | 0 off, 1 show 1 or 2 strikes | `Side::GetSimpleTimes` | change the strike count the fight uses | the same forecast |
| `triangle_hint` | 0 off, 1 show advantage, disadvantage, or none, and whether the rank bonus is kept | the triangle helper's cell and `triangle >= 0` | store the cell, or change `GetAttack`'s bool | the same forecast |
| `vein_who` | 0 off, 1 show if the selected unit may use a vein | `Unit::CanDragonVein` | mark a tile, or fire the vein. That is `vein_highlight`, and it stays a separate key | one vein seen |
| `gauge_display` | 0 off, 1 show the gauge points the helper would leave | the gauge helper's returned number | store the gauge, or call `CalculateDual` | one replayed pair |

Five is the list. No sixth. Damage, experience, gold, and the stance rolls are not cheap: their writers are not done, or the damage function is not rewritten.

## Recheck — every v1 key

Same day. The formulas, the triangle, the vein rule, and the gauge are the confirmed facts. `docs/ROBOT.md` already replayed a forecast, a vein, a follow-up, a pair, and a C support. That replay is not a licence to turn a switch on. A display switch still needs the options page and a draw path, and it stays off during capture. A run switch still needs the two gates.

Confirmed, from the notes, not from a new reading of the bodies:

- Hit, avoid, crit, attack, and the shown forecast numbers are the readers in `docs/FORMULAS.md` sections 2 and 5. An enemy gets half its class crit unless state bit 5 is set. Do not use section 8.
- One-strike damage is written in section 5. `Side::GetSimplePower` is the readable override strike_power since round 21 (2026-11-17). No damage switch.
- The triangle penalty uses the advantaged unit's rank. The disadvantaged unit also loses its own weapon-rank bonus, because the fight passes `triangle >= 0` into `Unit::GetAttack` and `Unit::GetHit`. The stores of that cell still wait.
- Who may use a vein is one flag (`Unit::CanDragonVein`). There is no per-turn "used" flag. The vein's own state byte is the record. A highlight must not call `Done`.
- The gauge helpers return the points. They do not store them. `CalculateDual` is still a writer.

| key | function now named | read or write | robot before it may be enabled |
|---|---|---|---|
| `growth_display` | `Unit::GetGrow` | reader | options page and a draw path. No level-up required. Not replayed as a status screen |
| `danger_zone` | `map::Panel::Danger::Draw` | reader. Do not call `Danger::Add` or `Update` | the draw path. This batch did not name a new one |
| `animation_skip` | none | display | the picture path. Still unnamed |
| `anim_speed` | none | display | the same picture path. Still unnamed |
| `hp_bars` | `ChapterSetHideHpGauge` is a script command, not the draw | display | the bar draw. Still unnamed |
| `stance_forecast` | `Unit::GetDualSupport`, `Unit::GetDoubleCapability`. Gauge number from the helper only | readers. Must not call `CalculateDual` | forecast and a pair are already replayed. Still needs the draw path |
| `vein_highlight` | `Unit::CanDragonVein`. Marks from the `SetDeploy` helper | reader. The helper returns marks and writes nothing | a vein is already replayed. Must not call `Done` or the vein event |
| `support_preview` | `Unit::GetRelianceLevel` | reader. Must not call `GameProfile::UpdateReliance` | a C support is already replayed. Still needs the draw path |
| `growth_mode` | `Unit::LevelUp` is the roll. `LevelUpCalculate` only copies the unit, lowers the copy's level by 1, and falls into it | writer. The seed and the level must still advance | a level-up is already on `bt-ch8` (one battle). Stay off until the body is the hook and the two gates pass. See `BATCH_GROWTH.md` |
| `casual_mode` | `DifficultyIsCasual` is a reader. The save writer is not named | writer | the flag writer, both save kinds, the two gates. This batch did not name it |
| `death_rule` | `DifficultyIsPhoenix`, `SequencePhoenix::Create` | the first reads. The second creates a sequence | the same flag writer. 1 and `casual_mode` must not both be on |
| `dual_strike` | `CalculateAttackSingle` | applier. The readers are not the roll | a follow-up is already replayed. The two gates are not |
| `dual_guard` | `Unit::GetDoubleCapability` for the bonus. The block is inside `CalculateAttackSingle` | reader, plus an applier that is not its own name | a pair is already replayed. The two gates are not |
| `exp_rate` | the four `GetExp*` readers, plus `GetDualExpDamage`. The writer is `GrowSequence::Calculate`, `Unit::ExpNormalize`, or `ExpSequence::Create`. `GainExp` only starts that sequence | readers, and a writer that is not `GainExp` | do not hook only one getter. Do not hook `GainExp` |
| `gold_rate` | `ProcMoney::GainMoney` is an event gain, not the general writer | writer, and the general one is still unnamed | stay off. Not infinite gold |
| `enemy_phase` | none | display | the enemy-turn picture path. A waiting choice still waits |
| `skill_banners` | `SkillIndexProvider::GetSkillEffectName`. Do not call `ProcSkillEffect::Tick` | the name is a reader. Tick is the picture | one skill activation. This batch did not record one |
| `support_rate` | `GameProfile::UpdateReliance` | writer | the hook and the two gates. A viewed C support is not that |
| `keep_game_options` | none | side file only. Never the 3DS save | the options page can read the game's rows without writing the save |

The five new keys above are the cheap ones. None of the run keys in this table are unblocked.

## Owner minutes

None. The forecast and the pair are already replayed. These five still wait on a draw path, and the look is still not during a capture.
