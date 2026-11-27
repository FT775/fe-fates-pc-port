# Round 65 full check (F-051: the everything-on matrix, every third round)

**In plain words.** Nothing was built this round. The installed round-62b build was checked the same way as round 62's
check, with the randomizer frozen at HEAD aaa4034. Every chapter on all 4 paths started, played, saved and reloaded
with Everything on (three ways) and with the randomizer off: 536 of 536 passed. Every page row on every path has a
strict OFF/ON pair on this build. After the integrate review, 72 cells were opened and looked at (SEEN). There is no
FAIL. Three cells are a **gap**: Revelation's boss might pairs (Easy, Normal, Hard) passed the robot judge only on a
loophole and do not show the change. Nothing counts as done until the owner says ok (F-037).

## Frozen build (any other sha is refused)
| File | sha256 | Where it comes from |
|---|---|---|
| play/game/Fire Emblem Fates.exe (page robot) | b4a887b262d14a0847733b137550bca84b82a784df291c49bf4ec3e19daaddbd | build/r62b/FINAL_SHA.txt |
| boot-server.exe (robot) | 1b8b2593690160ba26c8ed64d3928cfaf0beeea2fab121f113a2a4ca8e574ad1 | build/r62b/FINAL_SHA.txt |
| capture library 0004000000179800.dll | 610f791d43ba6184b1c75be844cfd6a5c529cd7e168eb241e9c987e11387debd | build/r62/FINAL_SHA.txt (not rebuilt in r62b) |
| tools/harness/rcheck.py, frozen copy | 306ac5d54a79dda2dafc3d197547d28500ad70cd8346b32e26f1a9c83b2d3454 | HEAD aaa4034 |

- Copies are in build/r65/check/bin (SHA256.txt, FROZEN_TREES.txt). The git tree ids at HEAD aaa4034 are
  tools/randomizer 1064b661 and config/randomizer cca62d39. Neither changed during the check.
- `import rcheck` loaded only the frozen copy, through build/r65/check/bin/pyfrozen/sitecustomize.py on every check
  process's PYTHONPATH (sha checked). The side track changed tools/harness/rcheck.py during the check (33e1b5c6 at the
  end). None of that reached the check.
- build/r65/check/shascan.json lists 949 result files: every robot, Nuzlocke-proof and page-robot result. All 949
  carry the frozen shas, and 0 were refused.

## Runs remade with HEAD's randomizer
- All 106 runs of round 62's check were remade with HEAD's randomizer (build/r65/check/runs, make65*.jsonl).
- **Every run id equals round 62's.** The id is the seed plus a hash of the page answer, and no answer changed.
- Three hand-made test runs were copied unchanged, because their source runs did not change: Hayato, Sakura and
  Seal nocol.
- The Conquest recolour pair's runs (r64f1recol5) were remade, and they are byte-identical to round 64's.
- **16 runs changed contents since round 62** (build/r65/check/run_changes.json):
  - Fates all1, all2, all3, nuz_all1, boss_stats, boost_on_normal and boost_on_hard: only placement (dispos) cells
    changed. These are the boss weapon forge levels, so that the shown might is +2 on Normal and +3 on Hard (round 63).
    Easy and Tougher bosses off are unchanged.
  - Seal all1, all2, all3, nuz_all1, boss_stats, boost_on_normal and boost_on_hard: the same might change.
  - Seal all1, all2, all3, nuz_all1, boss_classes and boss_classes_e: the Seal boss list also changed (round 64).
    14 boss lines keep their class again. They are 12 bosses: A013 Selena, A014 Daniela, A016 Iago, A018 Leo,
    A019 Illusion, A023 Beruka, Arthur and Effie, A025 Iago, A026 Peri, B010 Takumi and B011 Setsuna. B006 Ryoma now
    changes (Swordmaster to Master of Arms).
  - No other table changed in any run, and no face or colour cell changed. Only the patch's end count moved.
- A make problem, fixed before any game started: the first parallel make of the Seal runs rebuilt the shared Seal
  view build/sources/seal/romfs at the same time in 6 processes. They collided and left it without GameData. It was
  rebuilt once with `sources.build_layer(<r58 _sealmod>, force=True)`, and all 53 Seal runs were then remade cleanly.

## Break check: every chapter, 4 paths, all1 / all2 / all3 / off (536 of 536)
| Path | off | all1 | all2 | all3 |
|---|---|---|---|---|
| Birthright | 41/41 | 41/41 | 41/41 | 41/41 |
| Conquest | 30/30 | 30/30 | 30/30 | 30/30 |
| Revelation | 22/22 | 22/22 | 22/22 | 22/22 |
| Seal of Flames | 41/41 | 41/41 | 41/41 | 41/41 |

A pass means all of these held (build/r65/check/break.json, classify.py as round 62):
- the chapter was started by chapter select, played onto the map and through an enemy phase, battle-saved and
  reloaded with the same units;
- no fault in any log;
- every patched cell was right in memory, on the map and after the reload;
- the laid-cell count matched;
- no player unit was missing.

**HANDOVER: 12 of 12 pass** (Revelation 9 and 13, Conquest 9; off and all1-3; handover.json).

## Nuzlocke on every path: pass
- The 4 chapter jobs (nz-bt-A010, nz-cq-B010, nz-rv-C012, nz-seal-S002) all passed every check. The graveyard loaded,
  the fallen were in no army and not on the map, Casual switched to Classic, and there was no log fault.
- The 5 gate proofs passed on the frozen build (nz-verdicts.json):
  - castle load on all 4 paths;
  - a real death ("Kaze, A007, turn 14");
  - the battle save;
  - a new Nuzlocke game from New Game;
  - the profile.

## Page robot (the real in-game page; frozen exe b4a887b2; alone on a quiet machine)
| Run | Verdict | Start game -> run laid |
|---|---|---|
| quick, Fates | PASS | 0.035 s laid, 0.47 s to the avatar |
| quick, Seal | PASS | 0.12 s laid, 0.57 s to the avatar |
| agency, Fates (Difficulty and Royals changed just before Start) | PASS | 5.1 s laid, 5.5 s to the avatar |
| agency, Seal (the same) | PASS | 6.3 s laid, 6.7 s to the avatar |

- The owner's rule holds in all 4 runs. The laid game is byte for byte a fresh make, and the stale guess is thrown away.
- **The 2 s target fails right after a late row change (5.1 s Fates, 6.3 s Seal).** This is the known engine item from
  round 62 (4.5 / 5.4 s then). It is not a regression of the randomizer, and it waits for an engine round.

## Music by sound: pass on all 4 paths
OFF vs ON similarity (under 0.8 means different music):

| Path | OFF vs ON | ON vs ON2 | Map song |
|---|---|---|---|
| Birthright A015 | 0.498 | 1.0 | B3 -> B4 |
| Conquest B010 | 0.459 | 1.0 | B2 -> B5 |
| Revelation C012 | 0.491 | 1.0 | B3 -> B4 |
| Seal S002 | 0.434 | 1.0 | B1 -> A4 |

audio/audio-verdicts.json. The separate memory-scan note (music60.py) ran for Birthright only. The other three
memory scans sit in alternate lanes that the time box cut. The audio verdict, which includes a memory label check,
is the one that counts.

## Every page row on every path
SEEN = a reviewer (this check's, or the integrate review) opened the OFF/ON pair on this build and saw the change.
robot = a strict robot pair (rcheck judge_pair or the round-62 judges, frozen copy) is valid on this build, but nobody
looked. mem = memory only (no recorded route reaches the screen). gap = the robot pair passed, but the reviewer found it
does not show the row's change (a judge loophole); not a FAIL of the randomizer, needs a better pair. n/a = the row is
not on that path's page.

| Setting | Birthright | Conquest | Revelation | Seal of Flames |
|---|---|---|---|---|
| Shuffle (route) | robot | robot | robot | robot |
| Shuffle (any) | robot | robot | robot | robot |
| Recolour | SEEN | SEEN | SEEN | robot |
| Classes | SEEN | SEEN | SEEN | SEEN |
| Join stats | SEEN | SEEN | SEEN | SEEN |
| Growths | robot | robot | robot | robot |
| Personal skills | SEEN | SEEN | SEEN | SEEN |
| Skill slots | robot | robot | robot | robot |
| Promotions (Master Seal) | robot | robot | robot | robot |
| Heart Seal classes | robot | robot | robot | robot |
| Children | robot | robot | robot | n/a |
| Class growths | robot | robot | robot | robot |
| Class bases | robot | robot | robot | robot |
| Class movement | robot | robot | robot | robot |
| Starting items | SEEN | SEEN | SEEN | SEEN |
| Shops | robot | robot | mem | mem |
| Castle rewards | mem | mem | mem | mem |
| Weapon stats | robot | robot | robot | robot |
| Weapon special powers | robot | robot | robot | robot |
| Enemy classes | SEEN | SEEN | SEEN | SEEN |
| Boss classes | SEEN | SEEN | SEEN | SEEN |
| Enemy weapons | SEEN | SEEN | SEEN | SEEN |
| Stronger enemy weapons (Normal ladder pair) | SEEN | SEEN | SEEN | SEEN |
| Enemies grow faster | robot | robot | robot | robot |
| Enemy levels up | robot | robot | robot | robot |
| Tougher bosses (stat buff) | robot | robot | robot | robot |
| Enemy drops | SEEN | SEEN | SEEN | SEEN |
| Music | robot | robot | robot | robot |
| Everything on | robot | robot | robot | robot |
| Growth view | SEEN | SEEN | SEEN | SEEN |
| Growth floor 20-100 | SEEN | SEEN | SEEN | SEEN |
| Ladder: Easy | SEEN | SEEN | SEEN | SEEN |
| Ladder: Normal | SEEN | SEEN | SEEN | SEEN |
| Ladder: Hard | SEEN | SEEN | SEEN | SEEN |
| Story boss classes (class change) | SEEN | SEEN | SEEN | SEEN |
| Boss might/HP: Easy | SEEN | SEEN | gap | SEEN |
| Boss might/HP: Normal | SEEN | SEEN | gap | SEEN |
| Boss might/HP: Hard | SEEN | SEEN | gap | SEEN |


38 rows x 4 paths = 152 cells: **72 SEEN, 70 robot, 6 mem, 3 gap, 0 FAIL, 1 n/a** (sum 152).
Per path: bt: 19 SEEN, 18 robot, 1 mem, 0 gap, 0 FAIL, 0 n/a; cq: 19 SEEN, 18 robot, 1 mem, 0 gap, 0 FAIL, 0 n/a; rv: 16 SEEN, 17 robot, 2 mem, 3 gap, 0 FAIL, 0 n/a; seal: 18 SEEN, 17 robot, 2 mem, 0 gap, 0 FAIL, 1 n/a
(Before the integrate review: 34 SEEN, 111 robot, 6 mem, 0 FAIL, 1 n/a; build/r65/check/pre_integrate.)

Notes on the table:
- **"Stronger enemy weapons" reuses the Ladder: Normal pairs.** Normal is the page's default difficulty.
- **Boss might is judged on the SHOWN number.** rcheck judge_boost (frozen) reads HP and the might the game shows from
  the boss's unit::Item.
  - It passes every Easy, Normal and Hard pair on all 4 paths (tb-* jobs; verdicts62.json); round 62 failed Normal
    and Hard. **But on Revelation the pass is hollow (integrate review): gap.** The only pair is tb-rv-C017 Iago
    (Sorcerer, Fimbulvetr). Fimbulvetr is a drop, and drops are never forged by design, so no might change shows. HP goes
    38 -> 45 on Easy, Normal and Hard alike, because it stops at the cap (the spoiler's C017 line reaches the same capped
    HP on all three). judge_boost let it through on the drop exemption and its "capped" flag (`0 <= rise < want`,
    frozen rcheck.py line 276), which can never fail. Not a randomizer FAIL; it needs a Revelation boss whose weapon can
    be forged (next full check), and judge_boost should check the rise against the real cap (side track, next round).
  - Conquest (integrate review, SEEN): Hinata's Iron Katana shows +1 / +2 / +3. Some other Conquest labels passed only
    as "capped" (Hinata Hard HP 8 vs want 10, the B010 boss 5 vs 7 / 11, Saizo 5 vs 6 / 9); the cell stands on the
    shown might.
  - Seal Easy (integrate review, SEEN): tb-seal-R006 enemy1 Steel Lance +1, HP 32 -> 38.
  - The reviewer read the unit page for Birthright A014 Daniela (Ragnarok). Atk minus Mag goes from 12 to 13, 14 and 15,
    so +1 / +2 / +3, and HP goes from 33 to 40, 43 and 45 (review/might_bt.png).
  - The reviewer also read both Seal R006 Chevois (Steel Lance and Javelin). Atk minus Str rises +2 on Normal and +3 on
    Hard (review/might_seal.png; screen65.json).
- **Story boss classes, Seal (FAIL in round 62): SEEN.** These bosses are on the Seal list:
  - B006 Ryoma, Swordmaster to Master of Arms;
  - A014 Benny, Knight to Cavalier;
  - R006 Chevois (a generic boss), Wyvern Lord to Malig Knight (review/seal_story_boss.png, seal_R006_boss.png).
  - Round 62's bc-seal-R006 pair, rerun here, still shows no change. After one turn it picked the chapter's story boss
    (not on the Seal list, so it rightly keeps its class) and generic units.
  - Memory at map start shows both Chevois at (6,13) and (19,13) in the new class. A new two-job pair with the cursor
    on (6,13), sbc-seal-R006, shows it on screen.
- **Recolour, Conquest (FAIL in round 62): SEEN.** Round 64's strict pair was rerun: Effie attacks in B010. Her hair is
  silver-white with the colour lines out and dark red with them in, and nothing else changes (review/recolour_cq_zoom.png).
- **Drop flag (Enemy drops row note): pass.** With the flag the kill gives "You got Iron Club". With it cleared, the same
  kill gives nothing, and the two plain-enemy kills agree (review/drop_flag.png; n/checks/verdicts.json).
- **Children, Seal: n/a.** The row is not on the Seal page (owner, F-049 Seal Children addendum; ingame.HIDE_FOR), and
  make forces it off. Round 62 counted this cell as FAIL (greyed row then).
- **Shops on Revelation and Seal, and Castle rewards on every path: mem, as in round 62.** No recorded route reaches
  those screens. Every patched cell was right in memory in all of the path's all1-3 break jobs.
- **Recolour (integrate review):** Birthright (A015-b2, hair light purple -> dark navy) and Revelation (C016-b2, dark
  brown -> orange-brown) are SEEN. Seal (c-seal-S002-b5, Felicia) is very faint on close zoom (pink -> slightly
  lavender): NOT SEEN by eye, it stays robot.
- **Boss classes on bt, cq and rv rest on one chapter, paralogue X002** (Invader, Swordmaster -> Master of Arms). It is a
  valid pair per path, but not a route chapter; the route chapters are covered by Story boss classes.
- **Integrate review, other SEEN cells:** Classes, Join stats, Personal skills, Enemy classes, Enemy weapons, Enemy drops
  and Starting items on all 4 paths (the pair each note names is in review/seen65.json). The Birthright growth floor
  note no longer quotes "HP 50" (the panel has no HP row); the floor itself is SEEN.
- **ok=false robot jobs (integrate review rescan of 949 results):** the 4 Nuzlocke chapter jobs stop at "Save item was
  not found in the system menu", which is expected under Classic (no battle save) and checked on purpose by nzjudge; 6 bc
  jobs (bt A014, cq B010, cq B012; boss_classes_e and enemy_classes) report "no reachable tile" for the kill only; their
  class screens are valid pairs. No other ok=false; all 536 break jobs are ok with no log fault.
- **Story bosses killed in the new class:** only Revelation C017 Iago again (bc-rv-C017). The other bc kills found no
  tile, as in round 62. Rounds 63-64 proved 24 of 25 by their own placement cheat; that is not part of this check.

## FAILs
None of the 152 cells failed. **Gaps (3 cells): Revelation boss might Easy / Normal / Hard**, see the notes above.
Known misses, which are not cells:
- **Start game 5.1 s (Fates) and 6.3 s (Seal) after a late row change**, against the 2 s target. This is the engine
  item above.
- **The time box cut 40 alternate lanes of round 62's queue** (second and third pairs for cells that already have a
  valid pair; listed in plane/queue.txt without a .claim file). They hold 0 cells that would otherwise be empty.
  - Round 62 ran every lane. This check first ran, for every cell, the lane that proved it in round 62 (214 jobs,
    minimal.json), plus all the F-049 lanes (growth view, growth floor, ladder, boss classes, boss boost), plus as much
    of the rest as fitted.

## Robot notes (honest)
- Robot fixes in this check, each run once:
  - Lock files, so a job named in two lanes runs once.
  - An `s_fix` lane: three jobs a judge reads from sjobs had first run only into pjobs.
  - The new sbc-seal-R006 pair (the cursor on the changed boss).
- One edit to p61.py was broken for about a minute (a split string). No lane started in that minute; it was fixed
  before the next claim.
- No game was relaunched or retried. No job ran twice at once. At most 5 check robot jobs ran at once. While one job
  closed and the next opened in the same lane, a sixth boot-server was briefly seen.
- No visible window appeared (watch.py, every minute). STOP_ROUND never existed.
- Counts and times:
  - **Results:** 540 break and Nuzlocke chapter jobs, 325 pjobs (the 6 sbc pair jobs included), 16 sjobs, 36 cjobs,
    12 audio, 11 newer-lane jobs, 5 Nuzlocke proofs and 4 page-robot runs.
  - **Times:** the page robot ran 18:53-19:00, and the robot lanes 19:00-21:35.

## Where things are
- Contact sheet: build/r65/sheet/index.html.
- Data: build/r65/check/final.json (table), table65.json, break.json, handover.json, nz-verdicts.json,
  audio/audio-verdicts.json, verdicts62.json, verdicts65n.json, n/checks/verdicts.json, run_changes.json, shascan.json.
- The reviewer's notes are in review/seen65.json, and the screen reads in review/screen65.json.
- Integrate (round 65): build/r65/integrate_review.py added the reviewer's SEEN cells to review/seen65.json and wrote
  build/r65/check/review.json (the 3 gaps and notes); final65.py and mkdoc65.py now know the "gap" mark. The pre-review
  outputs are kept in build/r65/check/pre_integrate.

## Round 66 addendum (lean round, integrate)
- **Revelation boss might Easy / Normal / Hard: gap -> SEEN.** New strict pairs on C007 Vallite (Berserker, Steel Axe,
  forged, HP below its cap): shown might +1 / +2 / +3 and HP 26 -> 31 / 34 / 37, Tougher bosses off vs on, same seed,
  full unit page (docs/rando/BOSS_MIGHT.md, "Round 66"; build/r66/might/verdicts66.json; sheet
  build/r66/might/review/rv_C007_might_sheet.png). The integrate reviewer opened the pictures and SAW the change.
  The table now reads **75 SEEN, 70 robot, 6 mem, 0 gap, 0 FAIL, 1 n/a** (152); Revelation: 19 SEEN, 17 robot, 2 mem,
  0 gap.
- **judge_boost's "capped" now checks the real cap** (docs/tests/RCHECK.md, "Round 66 might track"). Round 65's 8
  short-rise or capped labels (cq B010 Hinata Hard, B010 boss Normal/Hard, B012 Saizo Normal/Hard, rv C017 Iago
  Easy/Normal/Hard) were re-judged from their own result files: all sit exactly at their tables' cap, all stay PASS.
  No cell changes because of this.
- Not re-run: the rest of this matrix. The next full check is due at round 68, or before the owner plays.
