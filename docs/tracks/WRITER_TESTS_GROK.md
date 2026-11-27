# Tests for the next three writers

**For the owner.** These three do not start until the options test is green. Each one is its own test copy. A green test does not turn it on in the game you play. That is a second yes, for that one writer.

Status 2026-11-18. Read: `docs/tracks/WRITER_ORDER1.md`, `docs/OPTIONS_WIRING.md` (T1–T7 and the gate), `docs/DECISIONS.md` F-021, F-026, F-034, `docs/MENUS.md`, `docs/GROWTH.md`. Names only from those notes. No address copied. F-034 is the options pieces, kept off. It is not a yes for these three.

The three after the options writer are pictures and speed, the danger zone, then the level-up. The first two share the options block. The level-up writes a unit, so it is not in that test. A cheat run is not the proof. Rows 5 through 8 stay off.

Every host test below uses the same planted kinds the wiring note already names: a store when the value is the game's choice, a store into the wrong byte, a store outside a gate session, and a give-up after one store. A kind the notes do not name is not added here.

## Pictures and speed

Names: `Battle::SetValue`, `GameSpeed::SetValue`. Not until the options writer's three numbers pass.

**Planted bugs.** A store when the value is the game's choice. A picture value written into the speed byte, or the reverse. A store outside a gate session. A give-up after one store.

**Replays.** The options routes already recorded (`opt-ch8-set`, `opt-ch8-reload`) only prove the screen. They do not prove a changed picture or a changed speed. The old Birthright routes cannot be replayed at a different speed, because the robot feeds inputs by frame. New `opt-*` routes, recorded with the picture and the speed fixed: one fight each way, and one support or dance each way (T2). T7 is a separate pair: the same fight with the picture, and on the map. Two chapter 8 fights already answered T7 for those fights only. That is not a proof for every fight.

**Off equals the original.** Armed, no options file. Every route ends with the same memory as today. Every save is byte for byte the same (T1).

**Undo.** A planted give-up after one store puts the block back as the game left it. The save is clean (T6). If the undo fails, that test save is thrown out. Do not load it. Do not pack it.

**Stays off.** The play build. Your saves. Replaying an old route at a new speed. Calling it display-only if T7 says the dice, the damage, or the experience changed. If they change, the page must say so. The volume setters. They wait behind this row.

## The danger zone

Name: `DangerPanel::SetValue`. It stores, then rebuilds the zone. `Danger::Update` is not a writer of its own. The helper already returns who it would mark.

**Planted bugs.** The same four kinds. Plus a rebuild when no map is loaded. The menu note says 0 and 2 draw, and 1 does not. The wiring sentence says drawn with 1, not with 2. Those are not the same test. The host test uses the menu note until a later note settles the sentence. Do not pass both.

**Replays.** T3, on a new `opt-*` route that presses the map button. No route presses it today. Not a real-play chain. A suspend save loaded onto a map must rebuild the zone. Without that route, this row does not pass.

**Off equals the original.** Armed, no options file. The zone matches today. No extra marks.

**Undo.** Same as above. A failed undo throws out that test save only.

**Stays off.** `Danger::Update`, `Add`, and `UnitMove` as writers. A chapter added so the button gets pressed. The play build.

## The level-up

Name: `Unit::LevelUp`. This is the roll. `GainExp` only starts the bar. `LevelUpCalculate` only copies. Do not start until the two rows above are green, and not in their test. It writes a unit.

**Planted bugs.** A gain stored on the wrong stat. A gain stored when the roll said none. The seed or the level moved differently from the game, so the next level-up would diverge. A store outside a gate session. The growth note says a fixed mode keeps the seed and the level moving as before, and replaces only the roll step. A planted bug that moves the seed is a fail.

**Replays.** `bt-ch8`, the route that already levelled. No new chapter. One `opt-*` copy of that level-up, with the fixed roll on, scored apart. A save it makes never starts a real-play route.

**Off equals the original.** Armed, fixed roll not applied. The same level-up stores the same gains, the same seed, and the same level as today.

**Undo.** A planted give-up after one store puts the unit back. The save is clean. If the undo fails, throw out that test save. Do not load it.

**Stays off.** The window ticks. A fixed-growth switch in the game you play. `exp_rate` in the roll. It belongs on the experience step, not here. A class change, a shop, and how an enemy picks. Each of those is a later yes.
