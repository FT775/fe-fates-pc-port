# Why the delays keep happening

**For the owner.** The clock keeps slipping because a rule that was meant to save time has no number on it, and the time we tell you is copied from last round instead of counted. This afternoon, "record the new rules on the fight chapters we already have" was read as all 47 of them. That is about two hours before the next job can start. The chapter itself was fast.

Status 2026-11-16. Read: the round 11–13 reports, `docs/collab/INTEGRATE_SLOW_R11_GROK.md`, `docs/collab/STRATEGY_R14_GROK.md`, `docs/PORT_PLAN.md` section 2, `docs/DECISIONS.md` F-026. The times in the question are accepted. No game file opened. No new timing was taken. F-026 stands: three numbers, never added, writers still off.

## The same miss, three times

The estimate counts the sentence, not the work under it.

- Round 11. "Old chapters recheck in seconds" was true for routes and false for new readers. A second command played all 38 old chapters live. The estimate did not add that line. Integrate ran past three and a half hours.
- Round 13. "Use the computer fully" became 12 check lanes beside the bug-catcher. The machine timed out for about 30 minutes. Twelve lanes is not free when another heavy job is already on.
- Round 14. "Capture a new reader once, on a narrowed set" was applied as every fight route already on disk: 47 routes, started 13:41, 34 done at 15:12, six or seven copies of the player at about 1 GB each. The equip capture waits behind that on a lock. Integrate, about 1 hour 40 minutes, waits behind both. The chapter was 30 minutes plus an 8-minute proof. The slip is the capture, not the play.

The sentence that was read as 47 routes is in `docs/tracks/REWRITE_ORDER3.md`: "fight routes already on disk." That was a place to look, and a warning not to add a chapter. It had no count. A rule without a count is read as all of them. That is the root cause. Not a slow chapter, and not one bad afternoon.

A host test that misses planted bugs makes the next slip too. The staff test missed 2 of 5. A capture of a reader that will be edited is thrown away, and the next integrate treats it as new again. Do not capture until that test catches every planted bug that can change an answer (F-026, number 2).

## 1. The rule that stops it

Keep the capture before integrate. Moving it back into integrate is how round 11 hid two hours. Do not capture during integrate.

Cap it.

- At most 8 routes per new reader, and at most 12 routes or 45 minutes for the whole capture, whichever comes first. Stop. Write "not here" for a reader the cap did not meet. Do not add routes, and do not add a chapter.
- Pick those routes from the last coverage hit map of a caller, or of a sibling the note says is called from the same place. A staff reader needs a route that used a staff, not every fight. An equip check needs one preparations screen and one fight, not every route that opens a menu.
- One recording that contains the new name is enough for the old routes to stay on the seconds path. The live compare is the routes in that capture, not all 47. F-018 does not ask for a clean recording of every old chapter once the name has been recorded once.
- Six player copies at once, not twelve. Nothing else heavy beside them: no bug-catcher, no slow check. Round 13 already paid for sharing the machine. Six or seven copies at about 1 GB each is the pace this afternoon actually held.
- Two captures may run together only if they write different folders and different names, and the two of them still fit in those six copies. If a lock forces them to wait, the estimate adds the second. It does not hide it.
- No capture while the host test still misses a planted bug.

This afternoon's pace was 34 routes in 91 minutes, about 2.7 minutes of wall time per route at six or seven copies. Forty-seven routes is about 2 hours 6 minutes. Two such captures, one after the other, plus integrate, is about 5 hours 50 minutes before the chapter is even counted. Eight routes is about 21 minutes. That is the difference the missing number made.

Tonight: do not start the remaining staff routes. Thirty-four is already past both caps. The equip capture, when the lock frees, is 8 routes, not "almost everywhere." If the staff test is fixed after this, recapture the capped set once. Do not recapture 47.

## 2. How to name a time

Do not name a clock time until this is written down. Do not copy last round's total.

```
minutes = last chapter of this kind
        + its proof
        + capture routes x 2.7
        + the second capture, added in full if a lock makes it wait
        + 100 for integrate
```

The 2.7 is this afternoon's pace (91 minutes for 34 routes). Replace it when a later capture measures a different pace. The 100 is rounds 12 and 13 (1 hour 35, then 1 hour 40), and it holds only when the new names are already in a kept recording. If they are not, add the capture. Do not add a bug-catcher or a slow check to this line. They are not in the round.

A round has a box. The box is the time told to the owner, and it is told only after the formula. If the formula is over the box, cut a capture or a chapter before starting. Do not start and slip. This afternoon's box was 4–5. The formula, had it been written, was already past that at 47 routes. The cut was the capture list, and it should have happened at 13:41, not at 7.

## 3. Round 15, and the steps that make the game moddable

Steps 3 through 7 have not moved since 11–13 November. Together they are 45% of the plan. What is left in them is about 16 points of the whole job (text 0.5, stat tables 4.8, pictures 3.5, maps 4.5, screen extras 2.5). The robot has about 1.5 points left. The readable rewrite has about 15 left, and a round now buys one to four readers plus a capture that can eat the afternoon.

Yes, the robot and the rewrite are too large a share for what they buy now. One capped reader batch a round, and only after its host test is green. No new chapter unless the formula has room. Conquest and Revelation stay paused.

Put one helper on step 4 first. It is the heaviest unfinished data step, and the plan's own finish line names the four stat tables. The files already rebuild. What is missing is one edit of each stat table, and one castle edit, seen in the game. The helper prepares that one sitting: the edits, the install, and a short note of what should look different. It does not add a table type, and it does not open eighteen castle sheets. The percent does not move until someone looks. That look is already the ask in the plan (10–15 minutes). Do not spend the helper on more spreadsheets while waiting for it.

Step 3 and step 7 are the same kind of leftover: a 5-minute look, not a build. A helper can stage the window. It cannot finish them. Step 5 (one portrait swap, seen in game) is next after the stat-table sitting is ready. Step 6 after that. Not all four in round 15.

## 4. What to cut

- A capture list with no count. Eight routes, 45 minutes, then stop.
- A second capture the estimate does not add.
- A clock time copied from last round.
- A capture of a batch whose test missed a planted bug. The staff test is the work, not another 13 routes.
- Twelve lanes beside a capture or the bug-catcher.
- A chapter to fill a round whose formula is already full.
- Another round that only sharpens the bug-catcher. F-026 already changed what that number is for.

Nothing here turns a writer on, pokes a real-play chain, or treats an offline replay as the check for a reader that has never been recorded.
