# OK A, one page

**For the owner.** This is a yes to a test copy. It is not a yes to changing the game you play. A green test still does not switch the writer on. That needs a second yes, after the three numbers pass.

Status 2026-11-17. Read: `docs/OPTIONS_WIRING.md` (T1–T6), `docs/collab/WRITERS_PLAN_GROK.md`, `docs/tracks/WRITER_ORDER1.md`, `docs/DECISIONS.md` F-021 and F-026. This note does not ask for the yes. You decide.

## What a yes switches on

One writer, on a test library only: the options writer that is already written and switched off. Both of its pieces must be on together. The piece that writes your choice may not run without the piece that keeps the save clean.

The test library is not the copy you play. It is not a rebuild of the emulator. Your saves, and the three plays running now, do not use it. The writer stores only when three things hold at once: it is armed in that test build, its name is on the test list, and the test is in readable mode. The play build cannot arm it.

## Pass or fail, in order

The host test comes first, and it does not need this yes. If it misses one planted bug that can change a stored byte, stop. The yes waits.

| # | Pass | Fail | What it proves |
|---|---|---|---|
| T1 | Armed, no options file. Every Birthright route ends with the same memory as today. Every save those routes make is byte for byte the same | Any different memory, or any different save byte | Off is the original game |
| T2 | A value set on the game's own screen, and the same value from the test file, leave the same memory after the load and after one fight, one move, or one map frame. Cursor and sound bytes the screen itself writes may differ | Any other byte differs | The test file does what the game's own screen already does |
| T3 | The danger zone is drawn when the test says on, and not drawn when it says off. A suspend save loaded onto a map rebuilds the zone | It draws the wrong way, or the loaded map keeps the old zone | The zone follows the choice. No route presses that button today, so T3 cannot pass until a test route does. That route is not a real-play chain |
| T4 | The choice is applied once per load or reset, and never at boot | It applies at boot, or more than once | A new game does not get a surprise setting |
| T5 | After a load, an apply, and a save, the save matches the same route with no options file. This must include a suspend save and then a chapter save in the same session. Both files match. The block is unchanged across the suspend save | Any save byte differs, or there is no suspend-then-save route | A save does not keep the test choice. Without the suspend route, T5 does not pass |
| T6 | A planted failure after one store puts the block back as the game left it. The save is clean | The save keeps the test choice, or the block is left half-written | A failure closes. It does not leak into the save |

Then the three numbers, kept apart, never added. Recordings on lines a recording reached. Lines never reached are listed, not failed. The host test, already run. A live compare of these routes with zero differences. A person still judges the "cannot change an answer" cases by a written rule. A script does not mark those.

Any fail stops the test. Do not arm a second writer to "finish the set."

## What stays off

- The game you play, your saves, and every real-play chain.
- Turning this writer on for you. That is a second yes, after the table above is green.
- Battle pictures, map speed, and the danger-zone writer as their own tests. They wait until this one passes. The check that asks whether a picture change also changes the fight's dice is not this yes.
- A class change, a level-up roll, a shop, an item use, and how an enemy picks a target.
- A cheat-track run as the proof.
- The emulator rebuild. That is a different ask.

## How to undo it

Stop using the test library. The play build never had the writer on, so your game does not need a patch to go back.

On a failed check, the test puts its own session back, newest store first. If that undo fails, throw out that test save. Do not load it. Do not pack it as a clear.

A second undo of the last apply works only while those bytes still hold what was stored. If they do not, it changes nothing. That is a stop, not a repair.

To disarm the test copy: set the writer back to off and rebuild that library, or delete the test library. No file in your saves folder is part of this test.

## The question

May the robot run the options writer on a test copy only, never on your game, and throw that test save out if the undo fails?
