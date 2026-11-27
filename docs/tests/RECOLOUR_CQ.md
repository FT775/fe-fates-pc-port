# Recolour on Conquest: one strict pair (round 64, goal 4)

**In plain words.** Round 62's Recolour cell for Conquest was FAIL: its B010 jobs had no battle with a recoloured
unit. Round 64 makes one strict pair on Conquest chapter 10 (B010). Effie's spot gets Selena's hair in this seed,
and Effie attacks on turn 1. Her hair is silver-white with the colour lines taken out, and dark red with Recolour on.
Everything else in the two pictures is the same. The robot judge says VALID (4 of 4 shots), and the reviewer opened
the pictures and saw it: **SEEN** (the owner's ok is still needed, F-037).

## The two runs (made with today's tools, `python build/r64/checks/mkrecol.py`)
- ON: `r64f1recol5-84f5a0aa`. This is round 62's recolour answer with a new seed: the shuffle (route), with the spot's
  class and stats, every other row off. The page's "keep the face" look recolours swapped spots by default.
  Spoiler: `エルフィ <- ルーナ: hair #DCD9D3 -> #AF5454` (Effie's spot, Selena's hair).
- OFF: `r64f1recol5-84f5a0aa-nocol`. The same patch with its colour lines (the `file asset` and `file face`
  sections) taken out, so the seed and the shuffle are the same and only the hair colour differs. This is round 61's
  Seal method. It is test-only: no page option makes it.
- Seed: `build/r64/checks/seedpick.py` tried 40 seeds. r64f1recol5 gives Effie's spot the biggest hair change
  (RGB distance 305), and Niles' spot changes too (#F5F3F0 -> #999191).

## The jobs (headless, frozen round-62b robot side: boot-server 1b8b2593, capture library 610f791d, sha checked)
Driver `build/r64/checks/robot/p64.py`. Runs were one at a time, below normal priority, data/APPDATA/LOCALAPPDATA
under build/r64/checks/robot/pjobs/<job>/, STOP_ROUND checked before every job, no window.

| Try | Jobs | What | Result |
|---|---|---|---|
| 1 | rc-cq-B010-nocol / -recolour (67 s, 77 s) | round 60's way: 3 turns of enemy-phase battles, then pairs.py's player attack (Effie first) | REJECTED, rightly. The battles' defenders were Nyx and Azura, who are not recoloured. Niles (recoloured) stands in the background of two battles and differs a little (at most 39 levels). The player attack started no battle ("no battle started") |
| 2 (the one retry) | rc2-cq-B010-nocol / -recolour (39 s each) | new `unit_attack` (job key `attack_unit PID_エルフィ`): on turn 1 Effie attacks the nearest enemy she can reach, using bosskill's attack (the target's HP -> 1, her move bonus -> 60; cheat pokes in the job's own copy, the same in both jobs). Shots attack0..3 at 100/160/220/280 frames after the battle starts | **VALID 4/4**: Effie vs the B010 Spear Fighter at 5,12 (the Oni at 1,8 was not reachable) |

The judge is round 61/62's recolour judge (build/r62/check/judge61.py `judge`, loaded read-only by
`build/r64/checks/judge64.py`), with tools/harness/rcheck.py judge_pair's six rules unchanged. For every shot:
- the same screen, frame and history;
- the same unit (Effie, read from memory);
- her spot is in the ON run's recolour list;
- class, items, bases, level and HP are equal;
- the pixels differ (attack0 0.48 %; the largest change is 144 levels on one channel).

- Verdicts: build/r64/checks/verdicts.json, "recolour/cq" (alts[1] is the valid pair).
- Pair (attack0, frame 6793): build/r64/checks/robot/pjobs/rc2-cq-B010-nocol/attack0-6793.png and
  build/r64/checks/robot/pjobs/rc2-cq-B010-recolour/attack0-6793.png.
- Side by side, with a 2x crop of her head: build/r64/checks/review/recolour_cq_B010_effie.png. The reviewer
  looked: silver-white hair OFF, dark red hair ON, and nothing else differs. Unlike the earlier faint pairs (Seal
  12 levels, Conquest under 24), this one needs no zoom.

## Status and review (round 64 integrate)
- The Conquest Recolour cell (round 62, docs/REPORT_2027-01-06.md: FAIL) is now **SEEN, waiting for the owner's ok**
  (F-037). Birthright, Revelation and Seal are unchanged.
- The reviewer opened `recolour_cq_B010_effie.png` and the raw attack0-6793.png pair: same unit (Effie), same frame
  6793, same scene; silver-white hair OFF, dark red ON, nothing else changes. verdicts.json shows try 1 FAIL and the
  retry VALID on 4 of 4 shots.
- Both jobs used the same cheat pokes (target HP 1, Effie's move bonus 60). The ON run itself is a normal page-made run.
- `build/r64/checks/stale_allon` holds a first run made by mistake with every row on. It is unused and can be deleted.

## Limits
- The OFF side is the test-only "colour lines out" run, not a page setting. The make step has no separate recolour
  switch (tools/randomizer/tracks.py RECRUIT_DEFAULTS; rando.py `_colours` recolours whenever the shuffle runs in
  the keep look), so this is the closest strict OFF. (Integrate correction: F-047 asks for
  an on/off picture pair, not for a page row. A separate Recolour on/off row is not built and nobody asked for one;
  recolour follows the shuffle's keep-the-face look.)
- Battle hair only (F-047 recolour scope). Portraits and map sprites are not recoloured by design.
