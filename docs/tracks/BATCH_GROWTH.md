# Growth and experience batch

ELI5 / ETA: This is the order to rewrite level-ups, using only the names in the symbol list. Nothing is rewritten. Every name is unverified: it was found in `config/functions.csv` on 2026-11-12, and the body was not read.

No game file opened. Addresses from that file are not copied here.

## Correction, 2026-11-13

The lines below that say no route records a level-up are out of date. `docs/ROBOT.md` section 3a recorded level-ups on `bt-prologue`, `bt-ch3`, `bt-ch4`, `bt-ch5`, `bt-ch7`, and `bt-ch8`. `bt-ch2`, `bt-ch6-castle`, and `bt-ch8-pair` showed none between shots. The tight one is `bt-ch8`, one battle, Rinkah only: the growth functions over that span see one level-up. Do not add a new chapter for this.

`Unit::LevelUp` is the roll. `GrowSequence::LevelUpCalculate` is not: it copies the unit, lowers that copy's level by 1, and falls into `Unit::LevelUp`. `GrowSequence::LevelUp` applies nothing. `GrowSequence::GainExp` does not add experience. It only starts `ExpSequence::Create`. Those three are settled in `docs/GROWTH.md` sections 1 and 9. The address of the roll is in that note. It is not repeated here.

Fixed growth still hooks the roll, which is `Unit::LevelUp`, not `LevelUpCalculate`. The seed and the level still advance. `exp_rate` hooks `GrowSequence::Calculate`, `Unit::ExpNormalize`, or `ExpSequence::Create`. Not `GainExp`.

## Names

**Rates (readers).** `Unit::GetGrow`, `unit::Edit::GetGrow`, `unit::Family::GetGrow`, `unit::Family::ParentSingle::GetGrow`. The last one is a child rate. Do not start there. A display of rates may call `Unit::GetGrow`. It must not call the window.

**Experience amount (readers).** Four names, and only these four matched `GetExp` plus a capital letter:

- `Unit::GetExpDamage`
- `Unit::GetExpDestroy`
- `Unit::GetExpDance`
- `Unit::GetExpRod`

A staff, a dance, a hit, and a kill are different getters. Hooking one and calling it all experience is a bug. `map::Situation::CanGainExp` was named in `OPTION_HOOKS.md` as a gate. It did not match this search. Do not drop it; do not treat it as an amount.

**The sequence (25 names whose symbol starts with `GrowSequence::`).** The ones this batch may touch, in order:

1. `GrowSequence::GainExp` — applies the amount. Writer.
2. `GrowSequence::LevelUpCalculate` — the roll. Writer. This is the fixed-growth hook, if a reading shows the roll lives here.
3. `GrowSequence::LevelUp` — applies that roll. Writer.
4. `GrowSequence::LevelUpReflect` — after the apply. Do not rewrite it until 2 and 3 match.

The pair versions wait until the single path matches: `GrowSequence::DualLevelUpCalculate`, `DualLevelUp`, `DualLevelUpReflect`, `DualLevelUpShow`.

The window is not the roll: `GrowSequence::LevelUpShow`, `GrowSequence::DualLevelUpShow`, and `LevelUpSequence::Create`. The same search also returned the `LevelUpSequence` picture ticks (`ProcGrowUp` and `ProcGrowMessage`: open, close, face, scroll, the result line). Those draw. They do not roll. Do not call them to apply a stat.

**Not this batch.** Still in the 25, and left until a level-up matches: `ClassChange`, `ClassChangeShow`, `ClassChangeReflect`, `ClassChangeCalculate`, `GainSkill`, `ForgetSkill`, `DualGainSkill`, `DualForgetSkill`, `BranchSkill`, `GainWeaponExp`, `DualGainWeaponExp`, `WeaponLevelUp`, `Create`, `ResumeGameInfo`, and the destructor. Also not this batch: `Unit::CopyForLevelUp`, `Unit::CollectiveLevelUpCapability`, `Unit::GetCollectiveLevelUpClassChangeJob`, `ProcLilithLevelUpMotion::Tick`. A class change and a weapon rank are not a level-up.

## Order

Readers, then `GainExp`, then `LevelUpCalculate`, then `LevelUp`. One function at a time. The pair path is a second pass. The window is never the test that the roll worked: the test is a stat that rose, or a level number that rose, not the picture.

Stop when a new function adds no testable change, or after three failed rebuilds, or four hours. Keep the last good one. Do not raise the depth. Same rule as `docs/tracks/REWRITE_ORDER.md`.

## What the robot has already played

`docs/ROBOT.md` section 3a (2026-11-13) records the level-ups. The sentence that used to say none were recorded is withdrawn. The tight capture is `bt-ch8`, not `bt-ch7`. Do not add a chapter whose only job is a level-up.

## What fixed growth needs

`growth_mode` in `docs/tracks/OPTIONS_V1.md`: 0 is the game's roll, 1 is fixed. Default 0. It is a run switch. It marks the slot. It stays off until:

- `LevelUpCalculate` is read, and the reading shows where the roll is. This note does not say the roll is there. The name is the candidate.
- The level still advances when the switch is on. A fixed rate that skips the level is a bug.
- Experience amount stays `exp_rate`. Do not fold that into `growth_mode`.
- The switch does not call `LevelUpShow` or `LevelUpSequence::Create`.
- One route already records a level-up with the switch off: `bt-ch8`, one battle. The same route with the switch on is the later test. The off replay must still match.
- The two gates from v1: a planted-bug test, and the undo log.

`growth_display` may use `Unit::GetGrow` before any of that. It is not this batch.

## Recheck — names the first pass skipped

Same day, same file, names only. Still unverified. No body was read.

`Unit::LevelUp` is in the symbol list. The first pass named `GrowSequence::LevelUp` and not this one. Do not decide which of the two applies the stats until a body is read. Rewrite neither until `GainExp` matches. `game::graphics::GrowLevelUpPlate::Draw` is the picture plate. It is not the roll.

The window ticks, so they are listed and not rewritten: `LevelUpSequence::Create`, then `ProcGrowUp::Persistent`, `TickParams`, `WindowOpen`, `WindowClose`, `TickWaitLoad`, `ResultMessage`, `CreateLightEffect`, `Telop`, `LevelTo`, `LevelTo2`, `TickFace`, and `ProcGrowMessage::Persistent`, `TickFadeOut`, `TickScrollIn`, `TickScrollUp`, `TickScrollOut`.

A search for `LevelUp` also hits the castle building menu: `MI_LevelUpBuilding`, `MI_LevelUpBuildingList`, `EditSeq::LevelUpMenu`, `CanLevelUpBuilding`, `CallBuildingLevelUp`, `LilithParam::LevelUp`. That is a building upgrade, the same word as the smithy level in `ROBOT_NEXT.md`. It is not this batch. `ProcWeaponExp::ShowWeaponLevelUp` and `GrowSound::SE::WeaponLevelUp` are a weapon rank, not a level.

Routes in `docs/ROBOT.md` that fight: `bt-prologue`, `bt-ch2`, `bt-ch3`, `bt-ch4`, `bt-ch5`, `bt-ch6-castle`, `bt-ch7`, `bt-ch8`, `bt-ch8-pair`. Section 3a of that note lists which of them recorded a level-up. The line that used to say none did is withdrawn. `bt-castle-shop` and `bt-ch8-support` do not fight.
