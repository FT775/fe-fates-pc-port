# Menus and panels the options need (Fates), read from the game's code

**In plain words.** Four of the options Grok listed already exist in the game itself. The game's
own options screen keeps a small block of settings (one object, `GameConfigData`), and the code
that draws the map or starts a fight asks that block what to do:

- **Danger zone** (`danger_zone`): the game keeps the enemy's reach as four tile maps (32 x 32
  tiles, one bit per tile) and draws a tile when it is in one of them. The game's option byte
  says whether it is drawn at all. Building those tile maps is a *writer* (it runs the game's
  move search and stores the result); reading them is what an option may do.
- **HP bars on the map** (`hp_bars`): the game already has this option (one byte). A unit's
  bar shows when the option is on, the chapter has not hidden all bars, and the unit is not the
  partner being carried in a pair.
- **Battle animations** (`animation_skip`): the game already has this option (one byte, 0 .. 4).
  When a fight starts, the game decides once, from that byte, the two units and the L button,
  whether to show the battle picture or play the fight on the map, and stores the answer in the
  fight's own flags.
- **Game speed** (`anim_speed`): the game already has this option (one byte): 1 = map movements
  always fast, 2 = fast while A is held, 0 = never.
- **Keeping options** (`keep_game_options`): the options block is written into **every game
  save** (as part of the save's own data) and read back when a save is loaded, so loading a
  save also loads the options it was saved with. A side file would have to put the player's
  options back after a load, and that is a *writer*.

Everything rewritten for this batch only **reads** (F-017). Nothing here changes an option,
the danger tile maps, a fight or a save.

This page is the readable rewrite's batch 6 (REWRITE_ORDER row 7, OPTIONS_V2, OPTION_HOOKS).
Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-13) and the functions marked *readable* are confirmed by a host comparison of readable C
against that code (section 6) [high unless marked]. No game text is copied here: the option
names are Grok's keys and plain descriptions, not the game's menu strings.

---

## 1. The options block (`GameConfigData`, G_GameConfig 0x006DA0F8)

One object; `G_GameConfig` holds a pointer to it. Each line of the options screen is a small
item class (`anonymous_namespace::DangerPanel`, `HPGauge`, `Battle`, `GameSpeed`, `AISkip`, ...,
built by `ProcGameConfigMenu::CreateConfigMenu` 0x003BB810). Its `GetValue` reads one byte of the
block, its `SetValue` stores it. On/off lines share one word (`option_bits`), one bit per line:
the line's `GetMask` says which bit (`ConfigItem::GetValue` / `SetValue`).

| Byte | What it is | Read by (readable) | Written by (not rewritten) | Reset value |
|---|---|---|---|---|
| +0x4 (word) | on/off lines, one bit each; bit 1 = support pictures allowed; bits 29/30 = unit info level; bit 16 = movie subtitles | `ConfigItem::GetValue` (`config_item_value`), `GetInfoCapability` (`config_info_capability`), `IsDetailSupport` | `ConfigItem::SetValue`, `Reset`, `Deserialize` | 0x00011E5E |
| +0x8 | battle animations (0 .. 4) | `Battle::GetValue` (`config_battle_value`), `IsDetailBattle`, `IsDetailSupport` | `Battle::SetValue`, `Reset`, `Deserialize` | 1 |
| +0x9 | camera distance [med] | camera code | `Reset`, `Deserialize` | 0 |
| +0xA | camera-distance line | `Distance::GetValue` (`config_distance_value`) | `Distance::SetValue` | 0 |
| +0xB | camera angle [med] | camera code | | 1 |
| +0xC | game speed (0, 1, 2) | `GameSpeed::GetValue` (`config_game_speed_value`), `IsSpeedFast` (`config_is_speed_fast`) | `GameSpeed::SetValue` | 2 |
| +0xD | enemy-phase skip (Options line 6: 0 Off, 1 Move, 2 All; round 80 read and seen, F-065) | `AISkip::GetValue` (`config_ai_skip_value`); the map sequence's Think (2 starts the game's dark skip, `GameSkip::Trigger`) and UnitMove / FocusWait / UnitFocus (1, while an AI sequence runs: no camera glide or wait, units placed at once). Seen in round 80 E1 (chapter 8 turn 1, End turn to the next player phase): Off 728 frames, Move 543, All 418 (dark 'Skipping...' screen); Start also skips the moving army's turn outside a map fight. Units, HP and the fight dice (`G_BattleRandom`) stayed equal; the general random 0x00752B7C moves once per frame, so later enemy turns can differ | `AISkip::SetValue` | 0 |
| +0xE | danger zone (0, 1, 2) | `DangerPanel::GetValue` (`config_danger_value`), `Danger::Add`, `Panel::Danger::SetVertex` | `DangerPanel::SetValue` (then rebuilds the zone) | 0 |
| +0xF | not traced [low] | | | 0x80 |
| +0x10 .. +0x13 | volumes: music, effects, system sounds, voices | the four `Volume*::GetValue`: rewritten in round 23 as readers `volume_bgm_value`, `volume_se_value`, `volume_sys_se_value`, `volume_voice_value` (src/readable/volume/, docs/VOLUME.md; 0xFF gives the maximum 32, any other byte gives byte / 8) | `SetValue`, `Deserialize` (also sets the sound volumes) | 0xFF |
| +0x14 | battle music | `EncountBGM::GetValue` (`config_encounter_bgm_value`: its position in the line's own list) | `EncountBGM::SetValue` | 0 |
| +0x15 | not traced [low] | one camera function | | 0 |
| +0x16 | HP bars on the map | `HPGauge::GetValue` (`config_hp_gauge_value`), `map::Actor::Tick` | `HPGauge::SetValue` | 1 |

**Where it is saved.** `GameUserData::Serialize` (the game save) calls `GameConfigData::Serialize`
with this block (0x005098B4), and `GameUserData::Deserialize` calls `Deserialize` (0x001B3A1C).
`Serialize` writes 20 bytes in this order: a version byte (1), the word +0x4, then the 15 bytes
+0x8 .. +0x16 (`config_saved_record` returns exactly that list). `Deserialize` reads them back
the same way, except that a record of version 0 has one more byte after +0xC, which is read and
dropped; it also pushes the four volumes to the sound system and the subtitle bit to the movie
player. The versus mode keeps its own copy (`versus::Data`). The game's `Reset` (new game, game
reset) stores the values in the last column.

**New Game, and who reads the block then (round 81, build/r81/options/OPTIONS_TRACE.md, F-066).** `GameReset`
calls `Reset` before every title screen, so every New Game starts from the last column, and loading a save brings
back that save's own 20 bytes (`Deserialize`). The one step that begins a New Game is
`GameConfigData::StartFromBeginning` 0x001D0618, called only from 0x00441794 right after Casual, Classic or Phoenix
is picked (not by Continue, a battle save, a chapter retry, the branch of fate, versus or online). It sets the
Tutorial bit and clears 0x80, 0x4000 and bits 29/30 of word +0x4 (for Normal + Classic the word does not change:
robot-seen in round 81, 0x00011E5E before and after). Between that step and the Prologue's first map no `Reset`
runs, and the readers of +0x8, +0xC, +0xD and +0x16 listed above act on the bytes only later (fights, map moves,
the enemy phase, `map::Actor::Tick`). Round 81's core writer (patch 0040, docs/OPTIONS_WIRING.md section 17)
stores the owner's chosen bytes at the end of that frame, once per New Game, and the game's own Options screen then
shows them (round 81 V: Combat Animations, Game Speed, Skip Actions, HP Gauges). The game's screen names the values
of +0xC 0 Normal, 1 Fast, 2 Manual (hold A to speed up) and of +0xD 0 Off, 1 Movement, 2 All.

## 2. The decisions that read the block

**Battle picture or map (`GameConfigData::IsDetailBattle(a, b, flip)`, readable
`config_is_detail_battle`).** For each unit of the fight that exists (and only when a map
Situation exists), the option says "picture" when it is 1; when it is 2 and the unit's army is
one of the map's `force_dual` armies (the Situation byte at the army's type is 1); when it is 3
and the Situation byte at index (Situation byte +0x8) is 1; when it is 4 and the unit's state
bit 31 is set. Any other value (0, or 5 and up) says "map". Either unit saying "picture" is
enough. Then the bool flips the answer (the battle passes "L is held"). Then, for a, b, a, b in
that order, the unit's PersonFlag word (its own, its Person's, its Job's) is checked: one of two
"always" bits forces the picture (`Unit::IsDetailBattleMust`, readable
`unit_is_detail_battle_must`), the "never" bit forces the map (`Unit::IsDetailBattleNotAllow`,
readable `unit_is_detail_battle_not_allow`); "never" is checked last and wins. The four checks
are always made, whatever the answer so far. Those bits are found by label the first time (three
one-time caches).

**Support picture (`IsDetailSupport`, readable `config_is_detail_support`).** The same per-unit
rule, but a unit counts only when option bit 1 is also on; the flip; then a unit with the "no
support picture" PersonFlag bit turns it off (one one-time cache). Used by the battle sequence
for a support or dance and by `map::SequenceDance::Create`.

**Fast movement (`IsSpeedFast`, readable `config_is_speed_fast`).** 1 when game speed is 1; when
it is 2 and A is held; else 0. Asked by unit walking (`map::ProcMoveRoute::Tick`), the cursor,
effects, event object moves and the script's `TimeGetConfigSpeed`.

**Skip input (`IsSkipInput`, readable `config_is_skip_input`).** 1 when B or Start was pressed
this frame. Asked by effects and the battle sequence to cut them short.

## 3. Where the options take effect

**The battle-picture decision** (helper `battle_picture_choice`). In the constructor of the map
battle sequence (`map::SequenceBattle::ProcSequence`, 0x0035D8A0 .. 0x0035D96C), flags bit 0
("no battle picture, play it on the map") is set when the sequence's word +0x25C is not 0, when
flags bit 1 is already set, or when the check answers 0. The check is `IsDetailSupport` when
flags bit 2 is set (a support or dance), else `IsDetailBattle`, with the two units at +0x270 and
+0x274 and "L held" (Pad.held bit 9) as the flip. The decision is made once per fight and
stored; nothing later in the fight asks the option again (not searched beyond the constructor
[med]).

**The map HP bar** (helper `actor_hp_bar_shown`). In `map::Actor::Tick` (0x0038D408 ..
0x0038D44C): shown when the HP-bar byte is not 0, the Situation's flags bit 0 is clear (the
chapter script's `ChapterSetHideHpGauge` sets or clears that bit: it is the script switch, not
the draw), and the actor's unit is not the carried pair partner (state bit 2). The result is
stored as bit 4 of the actor's draw word every tick. The battle picture's own HP gauge
(`ProcBattleInfo::DrawHPGauge`, `HPGaugeDrawer`) is a draw and was not read further.

## 4. The danger zone

| Function | What it does | Read or write |
|---|---|---|
| `map::Image::Danger::Update` 0x0038F834 | clears the four tile maps, then for armies 0, 1, 2 (via `Force::Get`) calls `Add` for every unit that is not skipped (state bits 0x24004), not allied with the viewing army (Situation +0x9, `Force::IsAllied`), and is marked (state bit 16) or the whole zone is on (flags bit 0); sets the redraw bit | **writer** (helper `danger_update_targets`: the units, in order, and the flag word) |
| `map::Image::Danger::Add` 0x0038F304 | runs `map::Deploy::UnitMove` for the unit (the move search; it fills Deploy's two tile maps) with search flags from the option (0 -> 0x50000, 2 -> 0x30000, else 0x10000), adds the tiles cannons can hit to Deploy's first map, then ORs Deploy's first map into `marked_a` (marked units only) and `all_a`, the second into `marked_b` (marked only) and `all_b`; sets the redraw bit | **writer** (helper `danger_add_preview`: the search flags and the OR, taking Deploy's two maps as they are; the cannon marks and `UnitMove` are not reproduced) |
| `map::Panel::Danger::Tick` 0x00390F14 | when the redraw bit is set: `SetVertex`, then clears the bit | writer |
| `map::Panel::Danger::SetVertex` 0x00390F54 | only when the option is 0 or 2: for every tile of the playable area whose terrain is drawn (`Terrain::Get` of the tile in MapImage +0x408: byte +0x10 not 0, word +0x18 bit 3 clear), a tile in `marked_b` gets the first colour, else a tile in `all_b` the second, with an edge shape from its eight neighbours | writes a vertex buffer (helper `danger_tile_kind`: 0 / 1 / 2 per tile, the colour test only) |
| `map::Panel::Danger::Draw` 0x00390E8C | draws the vertex buffer | draw |
| `map::Panel::Danger::IsHide` 0x005264C4 | the vertex buffer is empty | **reader** (`danger_panel_is_hide`) |
| `map::SequenceHelper::DangerTick` 0x0035E2CC | X pressed on the map, and some non-allied army has units: toggles the whole-zone bit, `Update`, plays the on/off sound | writer |
| script `UnitShowDanger`, `UnitShowWholeDanger` | mark one unit / switch the whole zone, then `Update` | writers |

So the tile maps the panel draws are the `_b` pair (from Deploy's second map); the `_a` pair is
filled the same way but not drawn by this panel [what the `_a` pair is for is not traced]. A
tile is in the zone only after the game has run `Update` (the player turned the zone on, or
marked a unit). **A display option may read the four maps (`danger_tile_kind` does), never call
`Update`, `Add` or `UnitMove`**: those store the zone and Deploy's move preview.

## 5. Option by option

| Grok's key | The game's own switch | What a port option would hook | Reader or writer | What the robot must replay first |
|---|---|---|---|---|
| `danger_zone` | option byte +0xE (0, 2 draw; 1 does not) and the X button (whole zone) | read the four tile maps (`danger_tile_kind`) after the game built them; the game's own option line already turns the drawing on and off | reader. `Update` / `Add` / `UnitMove` / `Tick` are writers | a map turn where X turns the whole zone on (and one with a marked unit), with a marker reading DangerImage.flags and the `_b` maps; none of the 14 routes presses X on the map |
| `hp_bars` | option byte +0x16; the chapter's hide switch (Situation.flags bit 0) | nothing new: the game's own line does it. A port option would read `config_hp_gauge_value` / `actor_hp_bar_shown` | reader; `HPGauge::SetValue` is a writer | one map frame with bars on, read through the actor's draw bit 4; the same frame with the option off. Not replayed |
| `animation_skip` | option byte +0x8 (0 .. 4), L held, the two PersonFlag bits | the decision is `IsDetailBattle` at the start of a fight, stored in the fight's flags bit 0. A port switch that changes it must store the option (or the flags): a writer | readers: `config_is_detail_battle`, `battle_picture_choice`. Writers: `Battle::SetValue`, the constructor's store | one fight replayed with the picture on and the same fight with it off, ending in the same memory (do the dice of a fight depend on the picture? not traced); the existing routes fight with the save's own setting |
| `anim_speed` | option byte +0xC (0, 1, 2) and A held | `IsSpeedFast` (`config_is_speed_fast`) | reader; `GameSpeed::SetValue` writer | the robot replays inputs by frame: a different speed moves every later input, so a route must be recorded with the speed fixed, or a speed change needs routes that wait for screens instead of frames |
| `keep_game_options` | none: each save carries its options | read the block (`config_saved_record` and the `GetValue` readers) into a side file; putting it back after a load is a writer (the game's `SetValue` lines or `Deserialize`) | the record is a reader; restoring is a writer (F-017: off) | open the options screen, change one line, save, load another save, with a marker reading the block before and after |
| `enemy_phase` (found on the way) | option byte +0xD | read by the map sequence's AI steps (round 80: Move / All read and seen, line 52) | reader `config_ai_skip_value` | round 80: the port shows a help line pointing at the game's own line 6 and the Start key; the port's own 2x / 4x was cut (F-065) |

Readers only, and default off, as OPTIONS_V1/V2 require. A display switch that calls one of the
writers above is a bug.

## 6. Checks

**Host differential test** `python src/readable/menu/tests/menu_diff.py` (skill_diff's method and
ARM interpreter): made-up states with values outside the game's ranges on purpose (option bytes
past their last value, army types past 3, bools that are not 0/1, tile coordinates past 31 or
negative, unmapped and "torn" units, no map Situation). For the 16 overrides it compares r0, the
bytes read from unmapped memory and the ordered list of guest calls with their argument
registers; a nested give-up is a mismatch. The six helpers are compared with the game's own code:
the whole of `Serialize` (the values written, in order), the battle sequence's decision region
(the flags word it leaves), `map::Actor::Tick`'s HP-bar region, the whole of `Danger::Update`
(the units passed to `Add`, the flag word), `Danger::Add`'s option test and OR (the tile maps
touched), and `SetVertex`'s option test and tile test. Results: docs/PORT_PLAN.md, status update
2026-11-13 (menus batch).

**Tier 2** (`tools/readable/verify.py --rom ...`): the same status update.

## 7. Grok's leads checked (REWRITE_ORDER row 7, OPTION_HOOKS, OPTIONS_V2)

| Lead | Verdict |
|---|---|
| start with `map::Panel::Danger` | agrees, with a correction: the panel only draws. The zone itself is `map::Image::Danger` (`Update`, `Add`), and those write. The readable pieces are `IsHide` and the helpers |
| "4 name hits on `map::Panel::Danger::`, including `Draw`" | agrees: `Draw`, `Tick`, `SetVertex`, `IsHide` |
| "which of Add and Update writes is unverified" (OPTION_HOOKS) | settled: **both** write (Update clears the maps and sets the redraw bit; Add runs the move search, marks cannon tiles in Deploy, ORs into the maps). `Draw` writes nothing; `Tick` clears the redraw bit |
| "a draw that writes the game's zone byte is a bug" | agrees; the option byte is GameConfigData +0xE and only `DangerPanel::SetValue` stores it |
| `animation_skip`: "none named"; `ClearBattleAnims` is not a skip | refuted as "none": the decision is `GameConfigData::IsDetailBattle`, made once in the battle sequence's constructor. Agrees that `ClearBattleAnims` is not it |
| `anim_speed`: "none" | refuted: `GameConfigData::IsSpeedFast` and option byte +0xC |
| `hp_bars`: `ChapterSetHideHpGauge` is a script command, not the draw | agrees: it sets Situation.flags bit 0, which `map::Actor::Tick` reads. The bar decision is in `Actor::Tick` |
| `keep_game_options`: "no options-screen name in the names searched"; "never the 3DS save" | the options screen is `ProcGameConfigMenu` and its items; the block is part of every game save (`GameUserData::Serialize`), so the game itself already ties options to saves. A side file stays the only allowed place for the port's copy |
| `enemy_phase`: "none" | refuted: the game has an enemy-phase skip byte (+0xD, `AISkip`); round 80 read its effect on the map sequence and saw it in a robot run (line 52, F-065) |
