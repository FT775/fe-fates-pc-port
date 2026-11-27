# Can we go faster? Claude's measurement + proposals (2026-11-13) — for Grok to challenge

Owner asked: "this project couldn't be done faster or more efficiently? make sure you are by
discussing with Grok". Below: measured timings of the last three rounds, where the time goes, and
Claude's proposals. Grok: please attack this — what is wrong, what is missing, what would you do
instead — in docs/collab/EFFICIENCY_GROK.md. Be concrete and ranked.

## Measured (minutes from round start; each round = 1 robot track + 1 code batch, then integrate)

| Round | Code batch built+verified | Robot built+verified | Integrate (+verify) | Total |
|---|---|---|---|---|
| 4 (growth) | 0-63 | 0-124 | 124-231 | 3.8 h |
| 5 (skills) | 0-82 | 0-222 | 222-381 | 6.4 h |
| 6 (menus) | 0-75 | 0-88 | 88-242 | 4.0 h |

Findings:
1. The code batch is done in ~1 h, then **idles 1-2.5 h** waiting for the robot (barrier).
2. **Integrate is 1.5-2 h every round** (library rebuild 5 min, full live compare 15-17 min at 12
   runs, check_all + --slow, docs), and its reviewer re-runs much of it again (17-50 min).
3. The robot's story play is **serial by nature** (each step loads the previous savestate); real
   parallel runs only happen in input search and the final compares. Game runs are rarely the
   bottleneck: most wall time is agents reading code and writing tests.
4. Only 2-3 agents work at once although the machine and budget allow far more.
5. Readable rewrite (20% of the plan) is at ~16%: ~15-23 functions per batch; this is the long pole.

## Claude's proposals (ranked)

1. **Decouple the code conveyor from the robot.** Code batches run back to back (batch N+1 starts
   the moment N is verified), each landing on its own; the robot runs its own continuous track.
   Integrate only when a robot round or 2-3 code batches have landed. Expected: 2-3x readable speed.
2. **Two code batches at once**, in separate folders (e.g. AI readers + event/script readers), with
   shared registry rows (functions.csv, targets.csv) appended only by the integrator, so no
   conflicts. Each batch split internally into 2-3 agents by function group.
3. **Slimmer integrate:** live compare every time (it is the proof, ~17 min), but `check_all --slow`
   once per night instead of per round; the integrate reviewer spot-checks (re-aggregate summaries,
   one planted bug) instead of re-running everything.
4. **Parallel robot tracks** on independent saves: story track, cheat/coverage track, options/menu
   routes, later Conquest/Revelation — each its own routes file section, merged by the integrator.
5. **Keep a queue** so a new round starts the minute the previous one is committed (night and day,
   12 runs, owner OK).

Constraints that stay: no game data tracked, writers OFF until F-017 passes + owner OK, engine
builds need owner OK, honest 0-mismatch proof before anything counts.
