# Should the plan change? Grok's answer, round 11

**For the owner.** The game-playing is ahead of the rewriting, and that is the wrong way around for the number you watch. Playing the rest of all three stories will not move that number much. Finishing rewrite batches that pass the real check will. Keep the rule that nothing which changes the game turns on until the bug-catcher is at 90%. Do not lower that bar to go faster. Stop spending two hours on a late chapter that does not teach the rewrite anything new.

Status 2026-11-15. This answers the round-11 questions. Read: `docs/DECISIONS.md` F-017 through F-024, `docs/REPORT_2026-11-15.md`, `docs/collab/SPEED_AGREED.md`, `docs/collab/EFFICIENCY_AGREED.md`, `docs/tracks/REWRITE_ORDER2.md`. The percents and the minute tables in those notes are accepted. They are estimates, marked low in the plan. No game file opened. No new timing was taken.

The plan's own weights: the robot is 10% of the job, the readable rewrite is 20%. Round 10 moved the robot from about 79% to about 82% and the rewrite from about 18% to about 22%, and the whole job from 52.6% to 53.7%. The rewrite's smaller step was the larger piece of the headline, because it is the heavier row. [docs/PORT_PLAN.md, the weight table and the 2026-11-15 total]

## 1. Is the balance right?

No. The robot row is about 82%. The rewrite row is about 22%. The owner already said the playthroughs must not outweigh the rewrite, and that a round carries two or three rewrite batches. Round 10 did both, and the rewrite moved the headline more. Round 11, seven hours in, has cleared a lot of late chapters and has one rewrite batch that is not green.

What moves the overall percent fastest is a rewrite batch that integrates clean, not another chapter. Finishing the robot from 82% to 100% is about two points of the whole job. The rewrite row is twice as heavy, and most of it is still ahead. A batch that misses planted bugs, or that is still red in the second check, does not count. Two green batches beat three started ones.

Do not add a fourth story track, a randomizer, or a writer to chase the percent. The randomizer is after the port. Paragon is the public table editor for this game, and it is GPL. Do not copy it. It does not change this round. [https://github.com/thane98/paragon]

## 2. Play every route to the end?

No. Stop a route when the next chapter does not meet a readable function the routes already recorded do not meet. That is the stop rule already in `docs/tracks/ROBOT_PLAN.md`: a new piece stops when it adds no functions. Do not raise it for a longer map.

Round 10 is the evidence. 179 of 203 readers were met. The 24 never used are mostly cannon, family, and capture. Three older readers were seen for the first time, and they were named: the Revelation dragon-vein script command on chapter 12, and the two "attack on this terrain" readers. Those are met now. Another rout, or another "defeat the boss," does not meet a cannon, a child, or a capture.

What is still worth a chapter:

- Birthright, one chapter at a time, only while it stays near an hour and a fight on it meets a reader the new batches need. Late Birthright was 49 to 88 minutes. That is the cheap chain.
- Do not keep Conquest and Revelation marching in parallel once a chapter costs about two hours and its only new thing is another fight of a kind already recorded. Conquest 10 to 12 and Revelation 15 to 17 were 106 to 123 minutes. That is the waste.
- A child unit is not on any of these maps. Do not marry to unlock one. A capture is not a reason to capture. Both can wait, and a poke for them is a cheat route, counted apart, and only if a proof actually needs it (F-019, F-024).
- The AI permission readers are met by an enemy phase that is already on disk. They do not need chapter 21.

Keep the three saves. Replay a recorded chapter when a new reader needs that fight. Do not clear toward the ending for coverage. The ending is not a finish line of the moddable port (F-022).

## 3. How does the bug-catcher get from about 51% to 90%?

The gate stays. It is the test that asks whether a planted mistake would be noticed. At about 51%, a mistake is as likely to slip as to be caught. Writers change the game and land in the save (F-021). Turning one on at 51% is how a bad change ships. The Awakening bar of 90% is still the right bar. Do not lower it.

The sampled run is a thermometer, not a cure. It scored 50.7% where the full-record run scored 50.6%, in 42 minutes instead of about 19 hours, and a warm rerun was 92 seconds. F-024 already took the 19-hour run out of every round. Leave it out. Running it again will not raise the percent. It will spend the night.

What raises the percent is catching mutants the current tests cannot see. More copies of the same battles will not do that. More chapters of the same shape will not do that. A cheat record raises it only when the missed bug sits on a path real play never takes, and only for a writer that would use that path. That is rare. Do not build a cheat pile to inflate the number. Cheat records stay in their own table (F-019).

The fast path: once a week, on the sample, list the survivors as "the test never reached that line" or "the test reached it and still did not notice." Fix the first kind with a sharper host case, on the files with the worst catch rate, not on all of them. Leave the second kind until someone has looked at it. Equivalent mutants do not count against the gate, but only after a person says they are equivalent. Do not mark them equivalent to make 90%.

The attack-score batch does not belong in this push. Most of those bodies store through out-pointers, which is what `REWRITE_ORDER2.md` said to stop on. A batch that misses 3 to 5 planted bugs out of about 47 is not a reader batch yet. Stop it. Do not spend the round making a writer look like a reader so the percent moves.

## 4. The proof that dies when the helper is sent home

Move the two-copy proof to its own stage. A prompt will not fix this.

It has happened three times: Conquest 9 in round 10, then Conquest 11 and 12. The helper is told to go home while the check is still running, so the check dies, and the review says "not confirmed." Integrate then replays the route anyway. That is the same proof, paid twice, and the first payment is thrown away.

The chapter helper's job ends when the save is packed and the press list is written. A short proof job runs next, in the foreground, with the slots. The next chapter on that route does not start until those two copies match. F-024 already says waiting proofs come before extra reader batches. This is that rule, applied to the thing that keeps dying.

Do not also replay that route live at integrate if the two copies matched and the capture library did not change. Replaying stored records offline is already approved (F-023 item C), and it was measured at 999 seconds down to 34 seconds. A route or a hook that changed still plays live. Round 10's second full live compare was right, because a real mistake had been found. It is not the shape of every round.

## 5. What to cut

- Late Conquest and Revelation chapters whose only job is more map. Keep the saves. Stop the march.
- The attack-score rewrite, until a body is shown not to store. The permission readers can finish review. The score functions wait on the writer gate.
- A third rewrite batch in a round where one of the first two is still red. Two that integrate beat three that do not.
- A full H6 every integrate. Already cut. Do not bring it back.
- A live compare of all 38 routes when item C says the offline replay is enough.
- A helper that both plays the chapter and owns the two-copy proof. That is why the proof dies.
- A seal, a capture, a marriage, or a poke, just to light a reader. Cheats only when a proof needs one (F-024).
- Lowering the 90% bar, or calling a sampled 51% "close enough."

One battle-number function is still a mismatch in the second check. Fix that, or write down why it is not a mistake, before any more battle readers. A batch that is "green after fixes" with one mismatch left is not green.

Nothing here turns a writer on, pokes a real-play chain, or skips the rule that a clean compare means zero differences of any kind (F-018).
