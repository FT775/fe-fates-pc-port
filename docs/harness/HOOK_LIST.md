# Fates hook list: the writer slots and the game functions they touch

**In plain words.** A *writer* is our code that changes the game's memory (an option byte, a save byte).
This page lists every writer of the Fates port, built or designed, with the game function it stands for,
what it stores, and which of our readable *readers* (overrides) it relies on. The test robot uses this
list to plant bugs in exactly the code a writer depends on (H6 on writers, `harness.py --mutate
--writer-callees`, `h56.py h6 --writer-callees`) before any writer may be switched on. **Every writer
here is OFF** (docs/WRITERS.md: armed 0 in `src/readable/core/writer.c`, not listed in `FE_WRITERS`, and
never in capture, shadow or original mode). Nothing on this page switches anything on.

Status 2026-11-15 (round 8, prep). Same layout as the Awakening port's docs/tracks/HOOK_LIST.md
(Grok's track), so `tools/harness/mutate.py` reads both. Facts come from docs/WRITERS.md,
docs/OPTIONS_WIRING.md and docs/MENUS.md (the game's ARM code, read only); addresses are function starts
of config/functions.csv. Tags: [high] read in the game's code or checked by a script, [med] good evidence,
[design] a piece designed in OPTIONS_WIRING.md and not written yet.

How the tools read it: a table row whose first cell is an id (letters then digits, `O1`, `W2`) is a writer
slot. The **address** cell's `entry 0x...` (else its first backticked `0x...`) is the game function the
slot stands for; `blank` means not found yet. Calls made directly by that function (ARM `bl` / `blx`,
decoded from extracted/code.bin) to a readable override count as the slot's callees, and so do the
overrides named in backticks in the **readable callees** cell (our own writer calls them, e.g. the
`GetValue` compare). Parked rows and the "Not hooks" list have no id, so they never count.

Enable rule (WRITERS.md section 2, unchanged): a slot is not enableable until its writer passes the
host comparison with planted bugs, the gate test, H6 on the writer and its callees on game records,
a replay that shows the effect, and the owner's OK for that one writer. A green report enables nothing.

## 1. The game's own options block (`GameConfigData`, G_GameConfig 0x006DA0F8)

Built, OFF: `src/readable/menu/menu_config_writer.c`, gate writer `config_options` (registry kind
`writer`, config/harness/targets.csv kind `writer`).

| id | slot | address | writes | proves | readable callees | option or mod | risk |
|---|---|---|---|---|---|---|---|
| O1 | battle animations line | entry `0x003BC36C` (`Battle::SetValue`; ours `config_set_battle`) | GameConfigData +0x8 (0 .. 4) [high] | opt-* route: the game's own screen sets +0x8 through several values, saved and reloaded (docs/ROBOT.md, round 8) | `config_battle_value` | `animation_skip` (fights **and** supports/dances: `IsDetailBattle`, `IsDetailSupport`) | [high] one byte. Read once per fight in the battle sequence's constructor |
| O2 | game speed line | entry `0x003BC968` (`GameSpeed::SetValue`; ours `config_set_game_speed`) | GameConfigData +0xC (0 .. 2) [high] | the same opt-* route | `config_game_speed_value` | `anim_speed` (map movement speed) | [high] a different speed moves every later robot input (routes are by frame) |
| O3 | danger zone line | entry `0x003BAF00` (`DangerPanel::SetValue`; ours `config_set_danger`) | GameConfigData +0xE (0 .. 2), then `Map::Get` and, when a map exists, `map::Image::Danger::Update` on MapImage +0x1008 (the zone's four tile maps and flags, through `fe_writer_call`: logged and undone with the line) [high] | the same opt-* route; a map frame with X (whole zone) for the rebuild (not replayed yet) | `config_danger_value` | `danger_zone` | [high] the only setter that calls another game writer (D1) |
| O4 | HP bars line | entry `0x003BC51C` (`HPGauge::SetValue`; ours `config_set_hp_gauge`) | GameConfigData +0x16 (0 .. 1) [high] | the same opt-* route | `config_hp_gauge_value` | `hp_bars` | [high] one byte; `map::Actor::Tick` reads it every tick |
| O5 | the screen's store path | entry `0x003BA714` (`ConfigItem::KeyCall`; ours `config_write_options`, gate `config_options`) | per line: compares with the line's `GetValue`, calls the line's `SetValue` only when the value differs (O1 .. O4). The key decoding, redraw and cursor sound are not reproduced [high] | the same opt-* route (every line through several values) | `config_battle_value`, `config_game_speed_value`, `config_danger_value`, `config_hp_gauge_value` | the four built-in PC switches (OPTIONS_WIRING section 8) | [med] that slot +0x78 is `GetNum` is read from the class layout |
| D1 | danger zone rebuild (callee) | entry `0x0038F834` (`map::Image::Danger::Update`, game code, not rewritten) | the four tile maps of DangerImage, its flag word (redraw bit) [high] | a map frame with X; a suspend save loaded onto a map with the line set (OPTIONS_WIRING T3) | `danger_update_targets` is a helper, not a callee override | none by itself | [high] run inside O3's gate session only; never called by a reader |

## 2. The options wiring (designed, not written: OPTIONS_WIRING.md sections 3 .. 5)

| id | slot | address | writes | proves | readable callees | option or mod | risk |
|---|---|---|---|---|---|---|---|
| W1 | apply hook after a save load | entry `0x001D0374` (`GameConfigData::Deserialize`, an override that runs the game's function first, then calls O5) | through O5 only: the lines set on the PC page [design] | OPTIONS_WIRING T1 .. T7 (owner OK A) | `config_battle_value`, `config_game_speed_value`, `config_danger_value`, `config_hp_gauge_value` | the four PC switches | [design] only `this == *G_GameConfig`, never inside a `Serialize` |
| W3 | apply hook after a game reset | entry `0x001D06DC` (`GameConfigData::Reset`) | the same as W1 [design] | T4 (when `ProcSequence::GameReset` runs) | the same as W1 | the same | [design] the boot `Reset` runs before the pointer is stored: applies nothing |
| W2 | save guard | entry `0x0050AEA0` (`GameConfigData::Serialize`, rewritten for the global block) | the save stream's 20 option bytes: the game's own value for every line W1 set [design] | T5 (a suspend save then a chapter save, byte-identical to no options) | `config_battle_value`, `config_game_speed_value`, `config_danger_value`, `config_hp_gauge_value` | keeps saves the game's | [design] known limit: a value picked in-game that equals the PC value is saved as the save's earlier value (OPTIONS_WIRING section 5) |

## Parked (no id: never a slot until read)

| parked | address | why |
|---|---|---|
| `keep_game_options` side file | blank | needs W1/W2 first and the T4 new-game route |
| growth roll for `growth_mode` (`Unit::LevelUp`) | blank | a run switch: the level-up roll, two gates (OPTIONS_WIRING section 8) |
| difficulty flag writer for `casual_mode` / `death_rule` | blank | candidate `GameUserData::SetMode`, not confirmed |
| `dual_strike` / `dual_guard` | blank | inside `CalculateAttackSingle`, not isolated |
| `exp_rate`, `support_rate`, `gold_rate` | blank | writers named in OPTIONS_WIRING section 8 but not read to an address here |

## Not hooks

The readers (`config_*_value`, `config_is_detail_battle`, `config_is_detail_support`, `config_is_speed_fast`,
`actor_hp_bar_shown`, `danger_tile_kind`, ...) never store. The display switches (forecasts, growth numbers,
vein marks) are new drawing code (build D), not writers. `map::Image::Danger::Add`, `map::Deploy::UnitMove`
and `map::Panel::Danger::Tick` are game writers no slot calls directly (D1 calls `Add`).
