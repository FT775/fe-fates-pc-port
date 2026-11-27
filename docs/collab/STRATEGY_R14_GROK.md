# Should the plan change? Grok's answer, round 14

**For the owner.** The bug-catcher is stuck at about 53%, and more of the same work will not get it to 90%. That is not a reason to turn on anything that changes the game. It is a reason to change what the 90% is counting. The rewrite list is used up for things that can be read. The next work is a short list of leftover readers a class or skill change would need, not more late chapters, and not Conquest or Revelation.

Status 2026-11-16. Read: the round 11, 12, and 13 reports, `docs/DECISIONS.md` F-017, F-021, F-024, F-025, `docs/harness/H6_SURVIVORS.md`, `docs/tracks/REWRITE_ORDER2.md`, and the "not in this batch" sections of the rewrite notes. The percents in those notes are accepted. No game file opened. No new timing was taken. The owner decides gates. This note only proposes.

## 1. Can 90% be reached on this path?

No.

The sampled bug-catcher went from 50.6% to 53.5% across these rounds. That is about three points. Three rounds of sharper tests found that the host tests already catch most of the bugs the recordings miss. The bug-catcher counts game recordings only, so those sharper tests cannot raise it. The note says so in those words. A give-up counter, if switched on, would make it 54.3%. That is not a path to 90%.

On the six files measured in round 13, the recordings caught 374 of 669 planted bugs (55.9%). 129 of the 295 that slipped through were never reached by any recording. Taking those out of the count leaves 374 of 540, about 69%, and only on those six files. Not 90%, and not the whole project. The same six files, if a recording or a host test counts, are already at 93.6%. If a person judges the 43 leftover candidates on those files as changes that cannot alter an answer, the note says those six would be at 100% on that combined count. The project still has 237 such candidates (80, then 114, then 43). None has been judged. Judging them is a person's job. A script must not mark them.

Some lines will never be reached if the current rules hold. The note names them: child units, a download unit, a cannon type no recording hit, a tile score no terrain in the game has, a script asking the map size when no map is loaded. F-025 says do not play a chapter to light those up. So they stay as misses forever, on a meter that counts them as failures.

The 90% idea is still right. It means: do not turn on a change to the game until a planted mistake would be noticed. The current meter is the wrong meter. It counts unreachable lines, and changes that cannot alter an answer, as failures. Keeping that meter and waiting will not open the writer gate. Lowering 90% to 53% and turning writers on would ship changes the catcher cannot see. Do not do that.

### What to measure instead

Three numbers, kept apart. Do not add them into one percent.

1. **Recordings, on lines a recording reached.** Same planted-bug replay as now. Lines no recording reached are listed, not counted as failures. On the six files, that is the 69% figure, not a project-wide promise.
2. **Host test, on the same bugs.** This is the number that is already near the bar on the worst files (93.6% before any equivalent is judged). A writer does not turn on unless its own host test catches every planted bug that can change a returned value or a stored byte.
3. **Live compare.** Already the rule (F-018): zero differences on the routes that reach that writer. This stays. 176,698 clean comparisons do not replace it for a writer that has never run.

A writer may be asked of the owner only when all three hold for that writer and the functions it calls, and a person has applied a written rule to each class of "cannot change an answer" on that file. One rule can cover a class (a compare at a boundary that divides to the same whole number; an argument swap in a call that only adds the arguments; a pointer value of 1 that never occurs). It does not cover all 237 at once, and it does not cover a bug that changes a result. The 90% bar then applies to number 1 for that writer, after never-reached lines and judged equivalents are out. If that writer's reached-line rate is still around 69%, it stays off.

The give-up counter stays off unless the owner wants the 0.8 point. It does not change this decision.

## 2. What rounds 14 and after should do

`REWRITE_ORDER2.md` is used up for readers that can be written. Batches 1, 3, 4, 5, and 6 are done. Batch 2 is parked because those bodies store. Batch 7 was a writer and is a host-only helper. Batches 8, 9, and 10 have no name in the symbol list, and no route. They do not start. Batch 11's two script names have no caller in the notes. They do not start. Batch 12's leftovers are the short list in `docs/tracks/REWRITE_ORDER3.md`.

A full randomizer is still after the port. Paragon is the public editor that changes this game's tables. It is GPL. Do not copy it. The next readers are the ones that editor's table changes would have to pass through at runtime, and only where a note already names the function. [https://github.com/thane98/paragon]

Two green leftover batches a round, not three, while each batch is this small. A batch of one reader that integrates is a round. Do not pad it.

## 3. Birthright, Conquest, Revelation

Keep one Birthright chapter in a round only when the last one stayed near an hour. Chapter 25 was 70 minutes, so one more is allowed. Chapter 24 was 129 minutes, which is why that route had already been stopped once. If the next one goes past about 100 minutes, stop again and keep the save. Do not clear two in one round to fill time the rewrite is not using.

Do not resume Conquest or Revelation. The pause is doing what it was for. Their saves stay. The 32 readers real play never meets are the same 32 as last round, and Birthright 25's cannons, fired by the enemy, still did not meet the cannon readers. Another late chapter will not fix that. F-025 already said not to play for coverage.

## 4. What to cut

- Another round whose only H6 work is sharper host tests. Three rounds proved those tests already catch the survivors, and the recording percent barely moved.
- Marking the 237 candidates equivalent by script.
- The give-up counter, as a plan. It is an owner option, not a path to the gate.
- `check_all` on 12 lanes while the bug-catcher is also running. Round 13 lost about 30 minutes to timeouts from that. Eight lanes beside it, or the planted-bug rows first.
- Batches 8, 9, and 10, and the two script readers with no caller.
- A new Conquest or Revelation chapter.
- Asking again for the two open owner items (the test-only options writer, and the Zakuro options patch) until the gate proposal above is accepted. They do not unblock a writer while the meter is the old one.

Nothing here turns a writer on, pokes a real-play chain, or treats a host test as a live compare.
