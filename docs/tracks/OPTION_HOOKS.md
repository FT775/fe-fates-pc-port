# Option hook map

ELI5 / ETA: This is which named game functions each switch might call, and which of those only read. Nothing is hooked. Every row is unverified: names only, from `config/functions.csv` on 2026-11-11. A name is not a reading of the body.

Status 2026-11-11. No game file opened. Addresses are in that csv; they are not copied here, so a later rename does not leave a stale number in this note.

A reader may be called to draw a forecast. A writer changes the battle, the save, or a gauge. A forecast that calls a writer is a bug. Off still means the original game.

| key | candidate (name only) | read or write | unblocked by | gap |
|---|---|---|---|---|
| `growth_display` | `Unit::GetGrow`. Also `unit::Family::GetGrow` and `unit::Edit::GetGrow` | readers. A const get, not the level-up | the options page and a draw path | `GrowSequence::LevelUpShow` is the level-up window. Do not call it to draw the status page |
| `danger_zone` | `map::Panel::Danger::Draw`, `map::Image::Danger::Add`, `map::Image::Danger::Update` | Draw is the picture. Add and Update may write the game's own zone. Do not call those two for a preview | the same draw path. Must not leave the game's zone byte set | which of Add and Update writes is unverified |
| `animation_skip` | none. `BattleUnitResName::ClearBattleAnims` clears a list. It is not a skip | display | the picture path | a second search (`AnimSpeed`, `SkipBattle`, `BattleView`) still named no skip |
| `anim_speed` | none | display | the same picture path | same gap |
| `hp_bars` | `anonymous_namespace::ChapterSetHideHpGauge` | a script command. Not the draw | the draw path | the bar draw is not named |
| `stance_forecast` | `Unit::GetDualSupport`, `Unit::GetDoubleCapability` | readers | one battle the robot has replayed | do not call `map::BattleInfo::CalculateDual` for this. The readable note already calls that one a writer |
| `vein_highlight` | `Unit::CanDragonVein` | reader | a vein has been seen, plus a draw path | the highlight draw is not named. `castle::DragonVeinSequence::*` is the castle sequence, not the map mark |
| `support_preview` | `Unit::GetRelianceLevel` | reader | a support has been opened | do not call `GameProfile::UpdateReliance` for a preview |
| `growth_mode` | `GrowSequence::LevelUp`, `GrowSequence::DualLevelUpCalculate` | appliers. The roll itself is not named | those hooks, a planted-bug test, and the undo log | do not enable on a guessed formula. `Unit::GetGrow` is the rate, not the roll |
| `casual_mode` | `anonymous_namespace::DifficultyIsCasual` | a script reader, not the save writer | the flag writer, both save kinds, the two gates | `GameUserData::SetMode` is a candidate writer. Not confirmed as the death rule |
| `death_rule` | `anonymous_namespace::DifficultyIsPhoenix`, `map::SequencePhoenix::Create` | the first is a script reader. The second creates the revive sequence | the same flag writer, plus a reading that names the revive value | 1 and `casual_mode` must not both be on. An overlay is still rejected |
| `dual_strike` | `map::BattleCalculator::CalculateAttackSingle` | applier. The strike roll is not separately named | one follow-up the robot has replayed, plus the two gates | `Unit::GetDualSupport` is the bonus reader, not the roll |
| `dual_guard` | `Unit::GetDoubleCapability` for the bonus. The block is not separately named; the readable note points at a region inside `CalculateAttackSingle` | reader, and an applier that is not named on its own | one pair the robot has replayed, plus the two gates | do not treat the whole of `CalculateAttackSingle` as the guard hook |
| `exp_rate` | `Unit::GetExpDamage`, `Unit::GetExpDestroy`, `Unit::GetExpDance`, `Unit::GetExpRod` for the amount. `GrowSequence::GainExp` to apply it. `map::Situation::CanGainExp` is a gate | the GetExp names are readers. GainExp is the writer | that writer, plus the two gates | not per route. A staff, a dance, and a kill are different getters. Do not hook only one and call it all experience |
| `gold_rate` | `event::Informal::anonymous_namespace::ProcMoney::GainMoney` | an event gain, not the shop or the battle payout | the gold writer, plus the two gates | a second search (`GetGold`, `AddGold`) still named no general writer. Not infinite gold |
| `enemy_phase` | none | display | the enemy-turn picture path | no speed function in the names searched. A line that waits for a button still waits |
| `skill_banners` | `SkillIndexProvider::GetSkillEffectName` for the name. `map::anonymous_namespace::ProcSkillEffect::Tick` for the picture. `map::battle::detail::HasBattleSkill` is a reader | name and HasBattleSkill are readers. Tick is the picture sequence. Do not treat Tick as the roll | one skill activation the robot has replayed | a banner that calls the applier is a bug. The applier is not named here |
| `support_rate` | `GameProfile::UpdateReliance` | writer | that hook, plus the two gates | `ProcLive2D::AddReliance` is the petting scene. Do not hook it. The conversation still needs the two units together |
| `keep_game_options` | none | side file only. Never the 3DS save | the options page can read the game's own rows without writing the save | no options-screen name in the names searched |

## What Claude should do

Hook nothing from this list until the body is read and the row above says reader, or the two gates have passed for a writer. If a searched name is the wrong function, say so under this note. Do not fill a gap from memory.
