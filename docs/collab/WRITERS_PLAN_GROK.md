# How writers get tested, once the owner says yes

**For the owner.** Nothing that changes the game turns on in this round. When you say yes to the test copy, the first one to test is the options writer that is already written and switched off. The proof is a replay of the options screens we already recorded, on a test copy, never on your game. Most of what is still named, after the short reader list, is this kind of change. That split is a guess.

Status 2026-11-17. Read: `docs/DECISIONS.md` F-021 and F-026, `docs/OPTIONS_WIRING.md` tests T1–T6, `docs/tracks/REWRITE_ORDER4.md`. No game file opened. You decide the OK. This note does not ask for it.

## Which one first

The options writer. It is already in the tree, gated, and off. It is the only writer that already has a screen the robot can open, and a host test. The others (a class change, a shop taking gold, an enemy choosing a target, a level-up roll) write into the army or the save. They stay off.

OK A is a test-only library with that writer allowed to store. It is not the copy you play, and it is not a rebuild of the emulator. The playthroughs running now do not use it.

## What proves it

Three numbers, for this writer only, never added together (F-026).

1. Recordings, on lines a recording reached. The existing options routes are enough. No new chapter. Lines no recording reached are listed, not counted as failures.
2. The host test catches every planted bug that can change a stored byte. That test already exists. If it misses one, the writer is not ready, and OK A waits.
3. A live compare of those same options routes, on the test library, with zero differences except the bytes the game's own screen already writes. The wiring note's checks T1 through T6 are that compare: the game ends as it does today when the file is absent, a value set on the game's screen matches the test file, and a save made after a store matches a save made without one. A suspend save has to be in that set, or the save check does not pass.

A person still has to judge the "this cannot change an answer" cases on that writer's files, by a written rule, one class at a time. A script does not mark them. Until those three hold, the writer is not offered to you as something to turn on.

## What stays off

- Your game, your saves, and the three playthroughs running now.
- The gold change, class change, the parked attack scores, the level-up roll, and anything that writes a unit.
- A cheat-track run as the proof. A labelled cheat is not real play.
- The second owner ask, the emulator rebuild. It is not on this path.

## How much is left [low]

The readable step is about 26%, and that figure is readers already done (252 of them). The named readers still worth a batch are the six rows in `docs/tracks/REWRITE_ORDER4.md`, a handful of functions, two of them long. The named work that stores — scores, seals, gold, the options setters, the fight's own stores, the level-up — is the larger pile. Of what the notes still list by name, about one part is readers and about three parts is writers. That is a guess from those lists, not a count of the symbol list, and it is not a percent of the whole job.
