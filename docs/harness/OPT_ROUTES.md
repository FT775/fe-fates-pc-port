# opt-* routes: the game's own options screen, changed, saved and reloaded (round 8, prep)

**In plain words.** Round 7's options route only looked at the game's options screen, so every option reader saw
one value (the save's own). These two real-play routes *change* the options on the game's own screen, the way a
player would, save the game, load it again, and check that the game's options block follows the screen at every
step. They are real play: no cheat save, no memory poke, no options file, no writer (every writer stays OFF).
The robot plays in its own game below build/; the owner's saves are never touched.

Status 2026-11-15. Found with savestate look-aheads (tools/harness/robot/probe.py, states in
build/harness/robot/states/prep/), then replayed from frame 0. Tags: [high] seen in a run's memory markers.

## The two routes (config/harness/routes.json, checkpoints in config/harness/markers.json)

| Route | From | Frames | What it does | Save |
|---|---|---|---|---|
| `opt-ch8-set` | bt-ch8-support | 7,000 | bt-ch8-options' input to the options screen (cursor on line 1 at 4870), then sets lines: line 1 RIGHT x4, line 2 once, line 3 x2, line 4 x2, line 5 once, line 6 x2, line 7 x2, line 8 once, line 17 x3, line 25 x2 (40 frames between presses so the screen redraws); B (no dialog); system menu (the cursor is back on the first item) DOWN x3, A: the save slots; A on slot 1; the dialog starts on No: LEFT, A. A **battle save** in the robot's own game (extra data, Map0.bak); the map again at 6860 | packs `opt-ch8-set` (`parallel.py pack ... extdata`) |
| `opt-ch8-reload` | opt-ch8-set | 4,500 | title, Continue, the save-type menu's default (battle save), slot 1: the chapter 8 map at 3100; system menu, options screen, DOWN x25 (look only), B, B | none |

## Which line stores which byte [high]

Found by RIGHT once on each of the 25 lines from a savestate on the screen (look-ahead `prep-lines`), reading
`state.game_config` (GameConfigData +0x4 .. +0x16, docs/MENUS.md section 1) after each press. RIGHT steps a line's
value up and wraps. No game text is copied here: lines are named by the byte they store.

| Line | Byte | Seen | Reader (readable override) |
|---|---|---|---|
| 1 | +0x8 battle animations | 1, 2, 3, 4, 0 (wraps after 4) | `config_battle_value` |
| 2 | +0x4 bit 1 (support / dance pictures allowed; `IsDetailSupport`) | on, off | `config_item_value` |
| 3 | +0xC game speed | 2, 0, 1 (wraps after 2) | `config_game_speed_value` |
| 4 | +0xA camera distance line | 0, 1, 2 | `config_distance_value` |
| 5 | +0x5 a bit (bit 9 of the word) | on, off | `config_item_value` |
| 6 | +0xD enemy-phase skip | 0, 1, 2 | `config_ai_skip_value` |
| 7 | +0xE danger zone | 0, 1, 2 | `config_danger_value` |
| 8 .. 16 | bits of the word +0x4 .. +0x7, one per line except line 10, which changed bit 7 and bit 30 together (bits 29/30 are the unit-info level `config_info_capability` reads) | on, off | `config_item_value` |
| 17 | +0x16 HP bars | 1, 0 | `config_hp_gauge_value` |
| 18 .. 21 | +0x10 .. +0x13 the four volumes | 0xFF, 0x00 | the four `Volume*::GetValue` readers (round 23, docs/VOLUME.md); the routes do not change the bytes, but opt-ch8-reload passes these lines and calls all four (r23-cap-volume: 80 records, 80 match; only the 0xFF path live) |
| 22 .. 24 | bits of the word | on, off | `config_item_value` |
| 25 | nothing changed by RIGHT (two presses) | | (`config_encounter_bgm_value` is the candidate; not settled) |

Leaving the screen also stores +0xB (2 after line 4 was set to 2): the camera angle byte follows the distance line
on exit [high: seen; which function stores it was not traced].

## What the runs showed [high]

| Check | Result |
|---|---|
| Block at each shot of `opt-ch8-set` | follows the screen line by line: start `de5e0140 01 00 00 00 02 00 00 80 ffffffff 24 00 01`, end `d85c0140 00 00 02 02 01 02 02 80 ffffffff 24 00 00` (battle 0, speed 1, distance 2, angle 2, enemy skip 2, danger 2, HP bars 0, four bits changed) |
| Title of `opt-ch8-reload` | the block holds the game's Reset values (`5e1e0100 01 00 00 01 02 00 00 80 ffffffff 00 00 01`, docs/MENUS.md section 1's reset column) |
| After loading the battle save | **the block is exactly the set block** from 3100 on, through the options screen (which shows the set values) to the end: a battle save carries the options block and loading it restores it |
| Markers, 2 runs of each route side by side (`parallel.py runs --markers --copies 2`, session prep-r8-optmk) | checkpoints all met in all four; memory `9164c56a...` (set) and `3c3489bb...` (reload), equal per route |
| Capture (`parallel.py runs --mode capture --only all --store-keep`, session prep-r8-optcap) | 1,003 records (669 + 334), 988 match, 10 gave up, 5 incomplete, **0 bad of any kind**; memory hashes equal to the original runs; the library predates this round's writer totals, so summary.json says "writers: NOT REPORTED" (the integrate rebuild adds the line) |
| H5 on those records (`h56.py h5 --sessions prep-r8-optcap --label r8-opt`) | 31 overrides met, 1,003 records, 0 bad, offline = live on every record. Distinct results per reader (round 7: 1 each): `config_battle_value` 4, `config_ai_skip_value` 3, `config_distance_value` 2, `config_danger_value` 2, `config_game_speed_value` 2, `config_hp_gauge_value` 2, `config_item_value` 2; `config_encounter_bgm_value` and `config_info_capability` still 1 |

Sampling note: capture keeps calls 1-16, then 32, 64, ... of each function per run, so a value set late in a run is
recorded only at those calls. The reload route opens the screen again from call 1 with the new values, which is
why it is a separate run.

## Rules kept

- Real play only (F-019): both start from real-play saves; `opt-ch8-set`'s battle save is not a cheat save.
- No options file, no writer: these routes change options through the game's own screen. The PC options page and
  W1/W2 (docs/OPTIONS_WIRING.md) are not involved; robot child processes never see `FE_OPTIONS` / `FEF_OPTIONS`.
- A save made by `opt-ch8-set` carries changed options (game speed 1, battle animations 0, ...): **no bt-* route
  may start from it** (frame-timed inputs would move). Only `opt-ch8-reload` does.
- Any map-menu visit moves the general random at 0x00752B7C (docs/ROBOT.md 3d), so these routes are not followed by
  further play.

## The options track (2026-11-18, F-034): rules ready, no route yet

`tools/harness/options_track.py` holds the rules of OPTIONS_WIRING section 7 for runs that **apply** an options file
with the writers armed (OK A, F-032). Such a route is named opt-* and has `"options": {...}` (the page's own lines,
e.g. `{"danger_zone": 1}`; `{}` = armed with no line set, test T1). The two routes above have no `"options"` and stay
real play. Rules, with a self-test (`options_track.py --selftest`, 23 checks; `--check` reads routes.json):
a route with `"options"` is named opt-*, is never a cheat route, and uses the page's keys and ranges; a save packed
from an options run carries the mark `harness-options.json` (never laid out for the game) and is named `opts-*`, and
only such a save is (`headless.pack_save`); an options save, found by name, mark or the same save files, never starts
a route without `"options"` (`headless.check_start_save`, `parallel.py`, `load_routes`); options runs are left out of
`harness.py report`, get their own table in `parallel.py`, and `recapture.py` refuses them. Until the OK A test library
exists (its own tree below build/oka/, never build/harness/lib), `headless.run` refuses every options route.

## OK A T2, T4, T5, T6, T7 (round 35, chapter oka-t2t5, 2026-11-18)

**In plain words.** The options writers were switched on in a test copy only (below build/oka/, never the shared
library, never the owner's game), and the robot played short routes with and without an options file. Saves made
with the file matched the saves made without it. One test failed: when the save guard (W2) is made to give up on
purpose, the save it then lets the game write is not the same as the normal save. Hiding the HP bars from the file
also leaves different memory than hiding them on the game's own screen. So OK A is not green.

How it ran: `build/oka/oka_run.py` (gitignored; runs one opt-* route on `build/oka/tree2`'s library, readable mode,
`FE_WRITERS` = the three OK A writers, options file below build/oka/opts/), 4 jobs, below normal. tree2 = the OK A
tree plus two switches read only there: `FE_OKA_TRACE=1` (one `[oka]` line per W1/W2 call) and `FE_OKA_PLANT=w1|w2`
(give up after the first store). Details and numbers: build/oka/results/oka-t2t5.json. Routes `opt-t2-*`,
`opt-t4-newgame`, `opt-t5-*`, `opt-t7-*` (all from real-play saves, real presses, no pokes); checkpoints in
markers.json for every one but `opt-t5-chain-*`. No save of these runs was packed.

| Test | Result | What was seen |
|---|---|---|
| T2 | **FAIL** (HP bars line) | Per line, X = set on the game's screen, Y = the same value from the file, same presses otherwise. Battle animations, game speed (both values), danger zone: every differing byte is one the file run shares with the untouched-screen baseline, so the screen's own presses wrote it (91-94 KB each, plus sound bytes). HP bars: 14,787 bytes differ that the screen did not write (FCRAM 0x4F80, 2,688 bytes; 0x273B35 on). All four lines at the save's own values: memory identical to the baseline. Only map frames and cursor moves after the change, no fight |
| T4 | NOT PASSED (partly run) | The boot `Reset` is never applied (the pointer is 0 then). A new game applies twice before the title; each save load adds exactly one apply. Which game calls the two startup applies follow is not known (the trace has no caller) |
| T5 | NOT PASSED | Battle save (Map0.bak) and chapter save (Chapter0) byte-identical with and without the file. The suspend-then-chapter-save route was tried four times: the battle save was made (identical, block unchanged across it), the chapter save was not reached. No route ever ran the versus-copy path: the Casual map Save is one `Serialize` on the global block |
| T6 | **FAIL** (W2) | W1 give-up: memory and every save identical to the no-file run. W2 give-up: the block went back to the game's values, but Map0.bak differs from the no-file save in 252 bytes (4 header bytes at 204-207 and 248 in the last 252 bytes of 6,892); that save was deleted, never loaded or packed |
| T7 | answered | Corrin's and Rinkah's first chapter 8 fights, picture vs map: same experience, same level-up (Skl +1), same enemy count, every unit's level, exp and stats equal at every shot. No difference in these two fights |

## Round 38 (2026-11-18, chapter oka-write): T5's battle-save-then-chapter-save route, recorded

**In plain words.** T5 needs one session that makes a battle save and then a chapter save. Round 35's try made the
battle save but lost the end of the chapter, because opening the map menu moves the game's dice. The last action was
found again by savestate look-ahead, and the route now reaches the chapter save.

| Route | From | Frames | What it does |
|---|---|---|---|
| `opt-t5-chain2-base` | bt-ch8-support | 79,900 | opt-t5-chain-base's input to 74,700 (bt-ch8 to turn 16, then the map system menu > Save > slot 1 > Yes: the battle save, Map0.bak, at 74,190); the unit at (8,6) attacks the last enemy at (8,7) in place (74,736-75,134), START skips the picture, 75,830 A; stage complete; 78,740 A, 78,915 / 79,004 START, 79,099 A, 79,259 LEFT, 79,289 A: "Save your progress?" Yes, the chapter save (Chapter0); My Castle from 79,500. No options file |
| `opt-t5-chain2-file` | bt-ch8-support | 79,900 | the same presses, options `hp_bars 2, danger_zone 1` (lines that move no frame) |

Replayed from frame 0 on build/oka/tree3 (readable mode, the three OK A writers listed; `build/oka/r38/diag_run.py`):
both runs reach the chapter save (markers: MapFileMenu 74,000, GameDialogYesNo 79,150, GameMessage 79,320,
castle 79,500). Map0.bak (5,696 bytes, `1e3a5acf...`), Chapter0 (5,128 bytes, `de4a9c29...`) and every other save file
are byte-identical between the two; in the file run W2 wrote both saves itself and `own[]` and the block were the same
before and after the battle save. No checkpoints in markers.json yet; no save of these runs was packed. The old
`opt-t5-chain-*` routes stay as round 35 left them (not finished).
