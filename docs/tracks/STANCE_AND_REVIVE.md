# Stance forecast and revive-next-turn

ELI5 / ETA: This is the design for two switches that do not exist yet. One shows whether a nearby ally would strike or block, before you confirm. The other brings a defeated unit back next turn. Neither is built. Nothing in the game changes. You do not need to do anything for this note. Building them is part of the February–March rewrite, and only after the test robot can replay one battle.

Status 2026-11-10. Design only. No code, no hooks filled, no option file created. Hook ids stay blank on purpose. A blank is not a license to pick the nearest function.

Agreed with Claude the same day: one campaign for play and the robot; all three routes still get static data tests; no option key names a route until code confirms the letter map. Petting scenes and the castle renderer are off both finish lines. Castle *tables* may still become spreadsheets later. That is data, not this note.

## Shape, copied from the Awakening options design

The rules carry. The keys do not. No addresses are copied.

- One `key = value` file. `#` comments. Unknown keys and bad values stay at the default. The file is not created until a value changes. Writes are atomic.
- PLAY points `FE_OPTIONS` at `fe14-options.txt`. If PLAY did not start the game, the fallback is that file next to the active data dir. Not in the repo. Not in the emulator's settings file. Not in the 3DS save.
- Display options never mark a save. Off means the hooks do nothing, and the result is the original game.
- Run options are a mark per save block (each slot, plus suspend), with a fingerprint of that block. A mark that does not match is dropped. The mark is written before the save. A failed mark must not cancel the save. PLAY's backup includes the mark once it exists.
- Options have their own dispatch. They must not depend on the readable-rewrite switch. In a capture, force them off. A replay that sees a different option than the recording is not a test.
- The menu is a page on the existing Esc menu, not a rewrite of the game's option screen. Changing a value does not rebuild.
- Default is 0 on every key here. 0 means "leave the game alone."

## The keys

| key | values | default | class | hooks |
|---|---|---|---|---|
| `stance_forecast` | 0 off, 1 show the ally strike and the ally block before confirm | 0 | display | draw path, blank. Readers, blank. Must not call either applier |
| `dual_strike` | 0 the game's roll, 1 always, 2 never | 0 | run, marker | strike applier, blank. Not enabled in this note |
| `dual_guard` | 0 the game's roll, 1 always, 2 never | 0 | run, marker | guard applier, blank. Not enabled in this note |
| `death_rule` | 0 leave the save alone, 1 back next chapter, 2 back next player phase | 0 | run, marker, including an already-started save | the game's own death-rule flag, blank. Not enabled in this note |

No route key. No castle key. No petting-scene key.

A percent slider is not a value. The game's scale is unread. Always and never can be tested without that scale. A slider is a later row, after the roll function is read, and not before.

## 1. Stance forecast

Display only. Before the player confirms a strike, show two facts the game already knows: whether a nearby ally would add a strike, and whether a paired ally would block. [med] those are the two retail stances. Not confirmed from this repo's code. The labels in the menu wait on that reading. Do not invent the sentences from a dump.

Must not add a point to a gauge, change hit or damage, move a unit onto or off a paired tile, or call either applier. A forecast that changes the fight is a bug. Same rule as a support preview that adds a point.

It can ship when the draw path exists and the two readers are named. It does not wait on the run options. It must not call them.

What this note will not pretend to know: the rate, the gauge size, which skills change it, and which function draws the battle forecast. Those stay blank until a reading names them.

## 2. Stance rates

`dual_strike` and `dual_guard` are separate so one can wait while the other is clean. 0 leaves the game's roll alone.

Design choice, copied from the other port, not a fact about this game: the game's roll still runs, so the random sequence advances as in the original. The result is discarded. If a reading shows the roll is not a separate step, this sentence changes. Do not enable either key on this choice.

Do not enable until that applier and every readable callee are replay-clean together on a named scene (a strike that happens and one that does not; a block that happens and one that does not), the planted-bug test has caught the bug, and the undo log is on. A green reader report enables nothing. These keys stay off in a capture.

Guard-stance stat bonuses are not these keys. If they are table data, they are a spreadsheet, not an option. If they are a formula, that is a later writer, unnamed here.

## 3. Revive next turn

One key, not two booleans. "Back next chapter" and "back next player phase" are mutually exclusive. Two switches would fight over the same flag.

[med] The retail game has three death rules: gone for good, back next chapter, back next player phase. The third is what "revive next turn" means in this note. The timing is not confirmed from this repo. The menu string waits on a code reading. Do not write the English difficulty name into the key.

Preferred mechanism: set the game's own flag, once code names it. Off leaves the save's flag as it already is. On sets the flag for "back next player phase." Value 1 sets the flag for "back next chapter," and is reserved so the two cannot stack. It is not enabled by this note either.

Rejected until the flag is shown not to exist: an overlay that revives a unit the game has already removed, without touching the flag. That is a second death system. It fights the game's own rule. Do not build it on a guess.

Do not enable `death_rule` until the flag writer is replay-clean on a save of each rule, the planted-bug test has caught a planted change, and the undo log is on. May apply to an already-started save, same shape as the other port's death-rule switch. That shape is a proposal here, not an owner ruling. Off does not rewrite the save.

A run option on a clean hook can still poison a save. Stamp those sessions. PLAY's backup is the restore path.

## Save safety

| class | in the options file | in the mark | in the 3DS save | in the emulator settings |
|---|---|---|---|---|
| display (`stance_forecast`) | yes | no | no | no |
| run (the other three) | yes, as the menu's current value | yes, per save block, before the save | only if we are setting the game's own flag, and only after that writer is enabled | no |

## Out of this note

- Route choice. The game's own select. No key until code confirms which letter is which, and this note does not add one even then.
- Petting scenes and the castle renderer. Off both finish lines.
- Forge rows and dining rows. Spreadsheets, if cheap. Not writers, and not switches.
- Weapon triangle, growths, danger zone, animation skip, vein highlight. Later rows in the same file shape. Not designed here.
- Child paralogues, amiibo, visiting.

## Owner minutes

None. The first in-game look is `stance_forecast` only, after the draw path exists, about 5 minutes, and not in the capture session. The three run keys are not in that look. They are not in the December feature list either. They wait on the rewrite.
