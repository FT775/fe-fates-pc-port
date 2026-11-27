# Can the robot and the tests go faster? Grok's answer

**For the owner.** The game is not the slow part. A fresh start of the player, every few seconds of play, is. The fixes that do not need you are real and should land in round 9. The one that needs you, a player that stays running, is the only change that makes a chapter feel like a chapter again. Do not add the gains in the table. They overlap.

Status 2026-11-15. This answers `docs/collab/SPEED_2026-11-13.md`. The minute table in that note is accepted. No game file opened. No new timing was taken. Estimates below are arithmetic on that note's figures, marked as estimates.

## 1. What is wrong with the top 8

**The gains are not additive, and the combined paragraph is the one that knows it.** Items 2, 4, and 5 all cut the same 104 minutes of look-ahead. Item 2's 25 to 35 minutes is the digest and the contact sheet inside those steps. Item 5's "2 to 3 times shorter" already removes most of those steps. Adding them to item 3's 6 minutes and calling the chapter 50 to 65 minutes counts the same minute twice. Tools 2 through 5, taken together, leave the 19 minutes of thinking and the 2 minutes of reads. That is about 60 to 75 minutes for chapter 10, not 50 to 65, unless the agent also stops calling once per move.

**Item 7's 60 minutes is larger than the stage it cites.** H6 play was 50 minutes. You cannot save 60 from 50. Those 50 minutes also sit inside a 107-minute build stage that already contains 73.7 minutes of sleep or poll. Adding the sub-rows (73.7 + 17 + 50 + 10) gives 151 minutes, against a stage of 107. They overlap. A cache hit does not come off the 280-minute critical path one for one.

**Item 3 and "capture as the second copy" are the same 689 seconds.** Side-by-side copies save about 345 seconds (6 minutes). After that, calling the capture run the other copy saves about 6 minutes more, not another 690 seconds. See question 3. It should not.

**The biggest measured wait is not a row.** 73.7 of the 107 minutes in `build:robot7` is sleep or poll. Item 3 stops the chapter's 660-second poll. It does not say what the 73.7 minutes is waiting on. If it is waiting on H6, shortening the poll does not shorten H6. Round 9 should name that wait before anyone treats 100 to 120 minutes as the test-round target.

**Item 1 is right, and it changes an agreement.** `check_all --slow` already runs the fast and medium rows. The code skips a slow row only when `--slow` is absent. A fast pass and then a slow pass repeats about 37 minutes (2,208 seconds of 4,856). Drop the first pass on integrate. Builders keep a fast pass so a fail is not a surprise at the end of the day. `docs/collab/EFFICIENCY_AGREED.md` item 1 said fast on every integrate and slow once a night. The measurement overrides that. Do not also move slow to nightly. Slow on integrate is the proof. Fast on integrate, on top of slow, is the duplicate.

**Item 5's mash is a desync, not a shortcut.** "Mash START/A for talk" adds presses the step-by-step run did not make. Our own chapter-8 note already showed that opening a menu moves the general random and the later enemy positions. Extra A presses can do the same. The second run then will not match, and the fallback boots again. Conquest chapter 6 already lost 25 to 30 minutes to failed lineages. A guess that looks like a stop screen and gets written into the route file is how that happens. Record the presses you actually sent. Do not mash.

**Item 6 is small, and the floor is the number.** Capture at 999 seconds, floor 654 seconds until two long routes are split. That is about 6 minutes, not 999 down to 689. Do it. Do not rank it above the look-ahead skip. Raising the job count during a 12-run session is the contention the note already measured (replays down to 163 to 184 fps). The "only when no play session needs the slots" line has to apply to parallel `check_all` too. The worth-doing list does not say that.

**The 30 to 50 percent frame cut was not measured, and it does not speed up a recorded chapter.** Battle animations off, game speed fast, and enemy-phase skip, set through the game's own screen, is real play. It is also a new movie. Every recorded Birthright route was timed with the save's current options. Those frame numbers will not replay. The cut, if it is real, applies only to a chain that has no fight recording yet. Enemy-phase skip must not skip a choice that is waiting. That limit is already in our options notes.

**The server estimate assumes the digest is already gone.** A step is 3.84 seconds. About 1.44 seconds of that is a decode and a hash a look-ahead never uses, plus the contact sheet. About 0.7 seconds is Python starting. A player that stays up, and still does that decode, is not a 0.2 to 0.6 second step. The 15 to 25 minute look-ahead is believable only after item 2. With thinking left at 19 minutes, the chapter is about 36 to 46 minutes, not 30 to 40.

**H5 ran three times, and the proposal cuts one.** 1,044 seconds in the build, 289 in verify, 999 in integrate. That is 39 minutes of live capture. "Replay stored records when only the library changed" should cover the verify re-run too, not only the integrate one. A route or a hook that changed still plays live. That rule is already in the note. Keep it.

## 2. What other projects actually do

Facts from public pages, read 2026-11-15. None of this is a Fates address, a table, or a poke.

**Fire Emblem, tool-assisted.** A GBA Fire Emblem TAS burns random numbers with legal cursor moves: a long diagonal path, then a wobble, because the path picker draws a number. An enemy-phase script saves a state at the start of the phase, plays the phase, reloads, and burns one number, so the author can pick a phase while away from the machine. The movie that is kept is the input list, replayed from the start. [TASVideos submission 3266, https://tasvideos.org/3266S; Serenes Forest, "How to Manipulate the RNG", https://forums.serenesforest.net/topic/28299-how-to-manipulate-the-rng/] Radiant Dawn does not burn numbers that way. The useful lever there is the order of actions, and a house visit. People still test orders with savestates in real time. [TASVideos forum topic 8666, https://tasvideos.org/Forum/Topics/8666] The Serenes guide calls writing the random directly "basically cheating." That matches our rule: a poke stays on the cheat track.

What that means here. Savestate branching is the right shape for a retry, once a branch is cheaper than a restart. It is not a reason to wobble the cursor on a real-play chain. A wobble lengthens the movie and hunts a crit. That is the wrong goal. A branch that reloads and tries the next legal input, and records the list that won, is a test technique. It waits on the server. At 3.8 seconds a step it costs more than it saves.

**One process, not a boot per look.** The projects that stay fast do not start the emulator for each click. `node-mgba` keeps the core in-process: about 1,110 frames a second through a worker, about 3,420 direct, a state restore in about 0.44 milliseconds, and a batch of 50 memory reads in one round-trip. [https://github.com/ARISE-Foundation/node-mgba] A Pokemon agent bridge is one headless process and a line-delimited command socket: step, press, read a range, save, load. Its core free-runs at about 4,800 frames a second. A Python client that polls for frames cannot keep up, so the screenshot is taken inside the emulator, on the frame the script asked for. `advance_frames` hangs on that headless build. The note says not to rely on it. [https://github.com/RiFa-Innovation/pkmn-azoth-translation/blob/main/EMULATOR.md] A second project runs one subprocess per game and prefers an in-process controller over an HTTP call. [https://github.com/apiad/retrokix]

What that means here. Our player already runs at 450 to 580 frames a second with no frame cap. Render-skip is not the first win. The fresh process is. A server is: load once, commands on a pipe, states in memory, no picture during a look-ahead, a timeout on a step that does not return. Do not poll. The software rasterizer stays off. Our own note says it crashes after a save loads. That is not a public recipe to retry.

**A planner reads the board. The model picks the fight.** The same Pokemon bridge's agent reads memory, lists the legal moves with the facts already computed, asks the model to choose, and checks the cursor bytes after the press. If the model is down, a small heuristic plays. It stops on an anomaly instead of inventing the next press. [same EMULATOR.md, the Jev agent section] That is the split to copy. It is not "a cheaper model per move," and it is not a solver that picks who dies.

Menu macros, in that world, are a recorded press list with a frame wait, not a mash. The bridge's earlier client sent the wrong field names and the presses were silently ignored. A macro that does not check the cursor will look like progress and be a desync. Our stop rule is the same: if the screen is not the one the list expected, stop and boot the step-by-step path. Do not send START/A "to be sure."

## 3. The five questions

**1. Build the one-boot settle if the server is approved?** Build the input list and the stop-on-unexpected-screen rule either way. Do not build the "boot, then boot again to that frame" driver if the server is approved before that driver is written. They solve the same wait. The list is a few hours and survives the server. The second boot layer is thrown away. If the server is not approved this round, build the one-boot driver, without a mash, and keep the step-by-step fallback.

**2. What must a cache key cover, and how often is a clean run?** The key is the preprocessed source or the object hash, the records digest, the harness file hash, and the compiler version and flags. A hash of the `.c` file alone misses a header. A nightly full clean run spends the 50 minutes you saved. Clean once a week, and on any compiler or harness change. A round that edits the file under test gets no hit. Do not cache a pass whose only green result is a hit, on a week when the key did not include the headers.

**3. Does the capture run count as the second copy?** No. Two matching copies means two runs of the same player, same inputs, same guest memory, same instruction count. That is what `parallel.py determinism` compares. A capture run is a different program in the middle. A matching hash shows the library did not change that route. It does not show the player is deterministic. Both can share a bug the library does not touch. Run the capture beside the two copies when the slots are free. Do not replace a copy. The 0-mismatch rule stays.

**4. Which chain keeps animations on?** The Birthright chain. That is the one with recorded fights, and it is where the battle-picture readers were met. Do not change its options. Conquest and Revelation may take the fast options only at a chain start, only after you say so, and only on a chain that has no fight recording yet. If Conquest chapter 6 already has a recording, that chain stays as it was recorded. One animations-on chain is enough. Not three, and not zero.

**5. Planner and turn batching, without more restarts.** One call per player phase. The model names who fights, who waits, and who uses the vein. A small solver turns that list into cursor moves. It does not pick a target, and it does not "improve" the list. The board is a memory read. A screenshot only when that read and the expected screen disagree, or when a forecast picture is the thing being checked. The phase is one press list. The first unexpected screen aborts to the step-by-step path. No extra A or START. A bad solver move costs a restart, and a restart is already 25 to 30 minutes. That is more than the 19 minutes of thinking. Do not move routine steps to a cheaper model.

## 4. Round 9, in order

Times are estimates from the note's chapter-10 figure (125 minutes) and the round-7 critical path (280 minutes). They are not a new measurement.

### No owner OK

| Step | What | Chapter after | Test round after |
|---|---|---|---|
| 0 | As measured | 125 min | 280 min |
| 1 | Integrate runs `--slow` once. Builders keep a fast pass. Do not move slow to nightly | 125 min | about 243 min |
| 2 | Look-ahead skips the unused decode, the hash, and the contact sheet. Heap dump only on a frame that needs markers | about 90 to 95 min | 243 min |
| 3 | Two determinism copies side by side. Stop polling in the foreground. Do not subtract the 73.7 minutes until that wait is named | about 84 to 89 min wall; the agent also stops sitting for about 11 min | 243 min, unless that poll is this same wait |
| 4 | Do not boot again to look at a state the last command already printed | about 75 to 84 min | 243 min |
| 5 | One press list per phase, stop on the first unexpected screen, no mash. Build the second-boot driver only if the server is not approved | about 60 to 75 min if the driver lands; otherwise the step-4 number | 243 min |
| 6 | Longest job first. Raise the capture job count only when no 12-run session wants the slots | 60 to 75 min | about 237 min |
| 7 | Agent: one call per phase, solver executes the named list only, text board | about 50 to 68 min | 237 min. The retry tax is the risk, not the gain |

### Needs the owner's OK

| Step | What | Chapter after | Test round after | Why it needs you |
|---|---|---|---|---|
| A | Cache, with the key in question 2, clean once a week | no change to a recorded chapter | 0 to 40 min off 237, and only on files that did not change. Not 60 | A stale cache can hide a weakened test |
| B | `check_all` in parallel, one folder per row, only when it will not take slots from a 12-run session | no change | slow pass about 81 min toward 12 to 14, so the round toward about 130 to 175 depending on A | Shared folders, and the machine is already contended |
| C | Capture beside the two copies, never instead of one | the 6 minutes of a second copy, only if it was still serial | about 17 min if the integrate live capture is a repeat of stored records, and the verify re-run too when the library did not change | It changes what "two copies" means if used as a replacement. Do not use it that way |
| D | Fast options on a new chain with no fight recording. Birthright stays as it is | a future chapter only, and the 30 to 50 percent was not measured. Do not plan on it | no change to the test round | It changes the game state, and a menu visit moves the random |
| E | Server mode: one process, pipe, states in memory, no picture on a look-ahead, timeout instead of a poll | about 30 to 45 min if step 2 and step 7 are in; about 36 to 46 if thinking stays at 19 | the poll inside the build stage should shrink; do not quote a number until that 73.7 minutes is named | Engine build. The clean replay from frame 0, two original copies, stays |

Do not start step 5's boot driver and step E in the same round. Do not sum A through E with 1 through 7.

The test round does not become 100 to 120 minutes on these figures. About 130 to 175 is the honest band if parallel `check_all` is allowed and the slots are free. Under 120 needs the unnamed 73.7-minute poll to have been waiting on work this plan already cut. Measure that before calling it done.

Nothing here turns a writer on, pokes a real-play chain, skips the live compare, or treats a capture hash as a second copy.
