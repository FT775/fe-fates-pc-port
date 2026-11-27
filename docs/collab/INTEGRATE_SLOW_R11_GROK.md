# Why round 11's integrate is slow

**For the owner.** The estimate said old chapters would be rechecked in seconds. They were not. A new rule was added, so the tool played all 38 old chapters again for real, for about two hours. The next check then plays those recordings one at a time, and a second pass inside it can replay them once per rule. That is the rest of the night. Round 12 should record a new rule once, when the batch is finished, and reuse that recording. Do not play every old chapter again.

Status 2026-11-16. Read: `docs/DECISIONS.md` F-023 and F-025, `docs/harness/H56.md` section 8, `tools/harness/offline.py` (`decide`, `plan_lines`), `tools/harness/h56.py` (`cmd_h5`, `exact_cover`). The times in the question are accepted. No game file opened. No new timing was taken.

## What the estimate missed

F-025 says unchanged routes replay offline, and a changed route or hook plays live. The tool agrees, and then adds a second line the estimate did not count.

`offline.py` marks a route offline when its buttons, frames, and save did not change. Round 11's plan said 38 old routes offline and 0 routes must play live. That sentence is true.

It also marks an override live when its address was never in a kept recording (`NEW: never captured`). Round 11 added 31 overrides. `plan_lines` then prints a second command: play every offline route live, capturing only those new names. That command is `r11-capo`. It ran until about 01:47. Offline replay of the old calls saved almost nothing, because the new names had no recordings yet.

The "seconds" figure in `docs/harness/H56.md` (34 seconds, 15 routes) is for a library whose overrides already have recordings. A round that adds readers does not get that figure. The plan's first summary line hides the second command. Round 12's estimate has to print both lines, or it will lie the same way.

The new chapters (`r11-capn`) and the cheat capture (`r11-capc`) are a different cost. A chapter that has never been captured has to play live once. That part is not the waste. Playing the 38 old ones again is.

## 1. Do new readers force every old route live?

Yes, with the tool as it is. That is the main loss this round.

**(a) Record them once, during the batch. This is the fix.** After the batch is green on its own test, and before integrate, one capture of the new names, with the recordings kept. The library in that capture must be the one integrate will check, so it includes every new reader of the round, not an earlier draft. Then those addresses are in the recordings, `decide` does not call them NEW, and the 38 old routes stay on the seconds path. One capture. Integrate reuses it. If a reader is edited after that capture, it is NEW again and must be captured once more. Do not capture at the start of the batch, before the fixes.

**(b) The old hit map cannot name a route for a function that was not in the library.** It can name routes that already ran a caller of the new function. An AI permission reader is reached by an enemy phase. A route whose last coverage never met an AI or a fight reader will not meet it. Do not play the title, a menu-only visit, or a shop-only route to capture an AI reader. Use the caller map as that filter inside (a). Do not use it as a reason to skip a fight route, and do not use it as a reason to play all 38.

**(c) Do not defer the live check to next round.** A reader counts as clean in real play only after the live compare (F-018). Deferring makes this integrate short and the batch not done. Park a batch that is not ready, as the attack-score batch already is. Do not park a green batch to save an hour.

## 2. Should the coverage step run 12 recordings at once?

The verdict pass, yes. The counter files, no, not into one folder.

`h56.py` `cmd_h5` asks for a job count and then does not use it. It plays each of the 88 folders one after another, and the coverage build writes its counters into one object folder. At the pace already seen (72 folders in about 45 minutes), 88 folders is about an hour before the second pass starts.

Twelve processes writing one counter file will mix the counts. The public tool for this is separate counter directories, then `gcov-tool merge`. GCC documents that merge, and a prefix so each run writes its own tree. [https://gcc.gnu.org/onlinedocs/gcc/Gcov-tool.html] Fan out only with one directory per lane, then one merge, then read the counters. A shared folder is a wrong coverage number, not a faster one.

The second pass is the larger risk, and it has not started. For each override, `exact_cover` deletes the counters and replays every folder that contains that override, still one at a time. The check row asks for 234 overrides. If each of those replays even one folder, that is another few hours at the same pace. The mismatch check does not need that pass. The first pass already says whether the replay matched the live verdict. The second pass is so a shared helper's line is not credited to every override. Limit it to the 31 new names, or run the full second pass weekly with the bug-catcher. Do not put 234 serial replays on the integrate path.

## 3. What fits in about an hour and a half

| Piece | This round | Round 12 |
|---|---|---|
| 38 old routes, new readers, live | about 2 h, already spent | gone, if (a) kept the recordings. Offline is about a minute, not 34 seconds times 38 as a new measurement; the measured offline pass was 34 seconds for 15 routes |
| 12 new routes, live, once | has to happen once | do not repeat if `r11-capn` recordings exist and the hooks did not move |
| Cheat capture | small in earlier rounds | keep it apart. Do not repeat it unless that library changed |
| Coverage, first pass | about an hour, serial, in progress | about 5 to 10 minutes if 12 lanes each have their own counter directory and the merge is one step. Estimate from the 45-minute pace, not a new timing |
| Coverage, second pass | not started; can be hours | new names only, or weekly. Not all 234 on this path |
| Sampled bug-catcher | 42 minutes cold, 92 seconds warm, 90-minute budget | not on this path. F-024 already took the long run out of every integrate. A cold 42 minutes does not fit beside a live capture |
| Slow check, report, pack | the slow check has mostly run | do not run it again |

Tonight, the two-hour live replay of the old routes is spent. Do not start it again. If the coverage step enters the per-override replay, stop that pass and keep the first pass's match line. Leave the sampled bug-catcher for the weekly run. That is how this integrate ends. It will not become an hour and a half tonight.

## 4. What else

- The attack-score batch is parked (F-025). It must not appear in the 31, and it must not grow this capture. A body that stores is not a reader.
- Conquest and Revelation are paused (F-025). Their new chapters already played need the one live capture. They do not need a second, and they do not need chapter 13 or 18 cleared to finish this integrate.
- A cache of the bug-catcher misses when the recordings change. Another reason it stays off this path: this round's new recordings would miss it, and the cold run is 42 minutes.
- Print the second plan line in the estimate. "0 routes must play live" is not "nothing plays live" while new overrides exist.

Nothing here turns a writer on, pokes a real-play chain, or treats an offline replay as the check for a reader that has never been recorded.
