# The test setup

**For the owner.** The three stories already run. Playing them again will not find the missing half. The last 24 routes added 26 functions. What is left is screens the robot never opens: shops, supports, the castle, a bookmark, a mid-battle save, a game over. The fast setup visits those screens on purpose, then keeps the old playthroughs as the check that nothing we already proved has broken.

Status 2026-11-19. Read: `docs/REPORT_2026-12-17.md`, `docs/decomp/REACHED.md`, `docs/harness/PARALLEL.md`. No game file opened.

Where the proposal is wrong. Random bursts are the second tool, not the first. A burst that reaches new code is not yet a route. Minimising every lucky burst will grow a suite we cannot replay. A nightly run of every existing route is not nightly: the day budget is 6 jobs, and a chapter is half an hour to an hour. That full pass is weekly. A cheat that sets Lunatic is not the same as pressing Lunatic on the title screen. The unreached code is the screen. Press the screen once. Lockstep compare on every burst is the slow path. Use it on routes we keep, not on bursts we throw away. Skipping a battle picture to go faster can skip the code we are trying to reach. Speed up the wait. Do not skip the screen.

## Layers

| Layer | What it catches | Speed | Cost |
|---|---|---|---|
| 1. The routes we have | A chapter that used to finish and now crashes, or a save that no longer matches | The plain build. No trace | Weekly, not nightly. Hours, on 6 lanes [low] |
| 2. One visit per missing screen | A menu, a shop, a support, a bookmark, a game over, that crashes or never returns | Short. Minutes each | A few rounds to write. Then cheap |
| 3. Short bursts from a hub | An odd press the script did not try. A hang, a soft-lock, a garbled frame | Many at once, 6 by day, 12 at night. Throw most away | One night finds candidates. Keeping them is the cost |
| 4. Trace, on discovery only | Which new functions that visit or burst actually ran | 1.5 to 2.4 times slower. Memory stayed the same | Not on the weekly pass |
| 5. Save, then load | A save that will not load, or loads as a different game | One extra boot per kept route | Minutes, on the routes we keep |

A stuck frame is a hang. A crash is a crash. A save that loads to a different memory is a break. A screenshot is not required. The headless picture hash is enough.

## Build it in this order

1. **Group the unreached list by screen.** Castle, shop, support, bookmark, mid-battle save, game over, difficulty, online. No play. A few hours [low].
2. **One scripted visit per playable screen,** from a hub we already have. Open it, press each item once, leave, save and load. Labelled. Not a real-play route. Two or three rounds [low].
3. **Watchdogs on those short runs.** Crash, hang, stuck frame, save/load. One round [low].
4. **Bursts only on screens the script could not finish.** Keep a burst only if it opens a named screen the script missed. Cap kept routes at 8 a week. One night to try, then stop [low].
5. **Weekly replay of the routes we have,** plain build, no trace. The three stories stay the backbone. Do not add a fourth full playthrough to raise the percent.

## What "flawless" can mean

Not 100% of 16,312. Online, StreetPass, and DLC the port does not run are listed as out, not failed.

Done, for the playable game: every screen in the grouped list has one labelled visit that returns; save then load matches on those visits; the existing routes stay 0 bad; a stated fuzz budget (one night, 6 or 12 lanes) ends with 0 crashes and 0 hangs. The coverage number is reported. It is not the finish line.

## Do not

- Replay chapters to push 51% toward 100%.
- Run all routes every night.
- Compare every burst against the original.
- Poke a difficulty instead of pressing it once.
- Trace the weekly pass.
- Let a burst write your saves, or start a real-play route from a cheat save.
- Treat StreetPass as a bug because the PC has no StreetPass.

## What you decide

1. Playable screens are the finish line, not every named function?
2. Online, StreetPass, and DLC stay listed as out?
3. New visits stay labelled, and never start a real-play route?
4. Full replay weekly, and only the new short visits nightly?
5. At most 8 new kept routes a week?
