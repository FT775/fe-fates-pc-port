# Round 82 plan: the full every-path check before you play (2026-11-26, desk part by Claude, 01:25 to 01:40 EST)

**In one line:** run the whole robot check once more, this time on the program you will play (round 81b), with
round 80, 81 and 81b's new parts checked on every path too. **No engine build, and no fix:** a FAIL is reported,
and fixing it waits for your yes.

## Why now
- F-051 / F-053 run the full check before you play, or every third round.
- The last one was round 76, on the round-74 program. Since then, four rounds changed the program:
  - round 77: Seal full-swap refusal (the randomizer, not the engine);
  - round 80: True hit and the Esc > Helpers heading;
  - round 81: New Game defaults;
  - round 81b: the Classic fix.
- Each of those checked only its own change plus the 8-job smoke (F-051's lean rule).
- The owner said "ok start 82" after the plain answer on why it is needed.

## What is checked (the program frozen: installed exe c2791862, build-record 9c171545, boot-server 90e5638a, server_build 2dee1628, capture library 405f2bac; any other sha is refused)
**Track check** (4 robot lanes). Round 76's matrix again, as docs/tests/CHECK_R76.md describes it, written up in
docs/tests/CHECK_R82.md:
- the runs remade with HEAD's randomizer: every run id and patch cell must equal round 76's, or the difference is
  explained (round 77 changed only Seal full-swap answers);
- the break check: 536 of 536 (each chapter x 4 paths x off / all1 / all2 / all3), plus chests 4/4 and HANDOVER;
- Nuzlocke on every path, the page robot (quick, agency, p4 on Fates and Seal), the seed guarantees in memory;
- the 42-row x 4-path table. Cells whose runs are byte-identical to round 76's may carry its mark, marked
  "carried". Every cell that touches a part changed since round 76 is re-judged on this program.

**Track new** (2 robot lanes): the new parts on each path. Each item is SEEN or robot, with its picture or log line:
- N1 True hit on the forecast: one fight per path (Birthright, Conquest, Revelation, Seal). The shown hit equals the
  game's own two-roll number. SEEN once on Fates and once on Seal.
- N2 the Esc > Helpers page: page robot targets on Fates and Seal (heading, True hit row, New Game defaults line
  and rows).
- N3 the play chain, the way you will start, once on Fates:
  - New Game on Normal + Classic, with all four New Game defaults rows set;
  - Randomizer on, everything on, full swap, Nuzlocke on;
  - expected: one pick, the run laid, the Nuzlocke game started, one defaults write;
  - then play on to the Prologue's first player phase: the game's Options hold the chosen values (bytes), and the
    randomized units are on the map (SEEN).
- N4 the same chain on Seal of Flames: keep the face, which is the only choice there, with the Randomizer on and
  rows set. Expected: one write, one pick, the run laid. SEEN up to the first map if a route reaches it.
- N5 old saves: a chapter save and a battle save from round 76's runs load on this program with no write, no pick
  and no warning.

**Track full** (1 lane):
- run_tests.py --full;
- check_all.py --slow (round 77 counted 77.1 min; the one known readable-verify row as before);
- smoke 8/8;
- fingerprints;
- hygiene.

**Integrate** (after the tracks): the review sheet, the table's FAIL list, the reviewers' corrections, docs (CHECK_R82.md,
F-068, ROADMAP row 82, NEXT_STRETCH line), the report.

## Counts (F-027; estimates unless marked)
| Part | Count | Cap | Source |
|---|---|---|---|
| Desk (this) | 15 min | done | - |
| Check track | 2 h 45 | 3 h 30 | round 76's check track took 2 h 42 (counted, REPORT_2027-01-23); same matrix size |
| New track | 1 h 30 | 2 h 15 | about 14 routes x 2.7 min + the play chain (2 long routes, about 30 min) + set-up 30 min |
| Full track | 1 h 35 | 2 h 15 | check_all --slow 77.1 min + FULL 5 min + smoke 3 min + fingerprints 1 min (counted, r77 / r81b) |
| Tracks side by side | 2 h 45 | 3 h 30 | the longest track |
| Integrate + reviews | 45 min | 1 h 15 | round 76: 27 min (counted), plus the new track's items |
| Report + Claude's commit | 30 min | - | - |
| **Total** | **4 h 15** | **hard stop 7 h real time** (roadmap row 82: about 7 h) | |

Round 76 planned 7 h and took about 3 h 10 (counted). This count is built from this round's parts.

## Disk
D: 75,012 MB free (df at 01:30). Round 76 used 14.5 GB (counted), so this round should leave about 60 GB. Stop rule:
nothing starts below 35 GB free. The round's folder stops at 18 GB.

## Hard stops
- STOP_ROUND, a visible window, or a program sha other than the frozen ones.
- 7 h real time.
- D: under 35 GB.
- A FAIL is never fixed here. It is listed, with its evidence, for your yes.

## Cut order (if past the count)
1. N5.
2. N4's play past the pick.
3. Carried table cells whose runs are byte-identical (keep round 76's mark, labelled "carried").
4. The page robot's Seal p4.

Never cut: the break check, N3, the full track.
