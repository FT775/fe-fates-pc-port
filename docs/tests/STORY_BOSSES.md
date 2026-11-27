# Story bosses in their new class: does the chapter get past the boss's scenes? (round 63, bosses track)

**Round 75b note (seed guarantees).** The guarded seed **r63fboss1** now gives patch **372b5d5c...** (unchanged) and
plan **d1f81611...** (was c5825cce...), run id **`r63fboss1-d8084ab3`** (the round-63 run below is
`r63fboss1-1692cf97`). Only plan.json changed: it gains the `guarantees` block (no repair for this seed), the
`guarantees: timing` guard and `rando_version` 2; its persons, placements and tracks are equal. The cell diff of the
round-63 patch and the round-75b patch (`build/r75b/f1/r63fboss1_celldiff.txt`) shows all 30 cells equal (19 boss
cells, 11 enemy cells, 0 player cells) and the two files byte-identical, so every boss below keeps the class it was
tested in and the results on this page still hold. Re-recorded under the owner's standing OK (F-059 (3)).

**Round 66 note.** The Fates list (config/randomizer/rules.json) is unchanged and Fates seeds are byte-identical
(r63fboss1 patch 372b5d5c..., plan c5825cce...). The Seal edition's story bosses have their own list (14 proven by
round 66): the boss page in docs/seal/.

## Round 72 (bosses_chests track): the Seal bosses again
Moved to the boss page in docs/seal/ in round 84 (the Seal edition only).

## Round 64 (bosses track): the 11 bosses round 63 could not fight

**Result: 10 of the 11 passed, 0 broke, 1 still not fought (A023 Arthur).** (Round 65: Arthur passed, see below.) No boss goes back to its own class,
so config/randomizer/rules.json is unchanged. All 11 stay changing (owner rule). Every passed boss has one picture
that shows its new class on screen (the map cursor on the boss: the bottom screen names the class).

How: the same seed **r63fboss1** (run `r63fboss1-1692cf97`, a copy in build/r64/bosses/runs), the same frozen
boot-server 1b8b2593 + capture library 610f791d (build/r64/bosses/bin, sha checked before every job and written in
every result: all 22 counted results have these two). Driver `build/r64/bosses/p64.py` (round 63's driver plus
three job keys, F-030 test cheats in the run's own copy only, never a real save):
- `place_next`: the attacker is **put on a free square next to the boss** (its x/y in the unit, and the map's unit
  grid: 32 bytes a row, one byte per square holding the unit's pool number; found by searching the state for the
  one place where every unit's number sits at its square, its address differs per chapter). Then the unit is
  picked on that square and told to stay, the unit command opens, and it attacks. The boss is at 1 HP as before.
- an attacker with no weapon equipped (a singer) is swapped for the next armed unit that has not acted yet
  (B025: Ryoma survived Corrin's first attack, the swap let Gunter make the kill in the same player phase).
- `boss_look`: before the kill the map cursor is put on the boss and a picture is taken (`boss_page-*.png`).
Each boss ran with the randomizer off too (same steps), the yardstick. Up to 3 jobs at once, headless, below
normal priority, data/APPDATA/LOCALAPPDATA under build/r64/bosses/jobs/<job>/, build/STOP_ROUND checked before
every start, 8-minute cap per job (none reached it; the longest 284 s). One retry each (`r64-` / `r64off-`) for the
bosses whose first run (`p64-` / `p64off-`) did not fight: the first version of the grid search did not count
pair-ups (two units on one square, only the lead is on the grid), fixed before the retries.
Judge: `build/r64/bosses/judge64.py` -> `build/r64/bosses/verdicts.json`. "passed" = the boss stood in its new class
(memory and picture), died, no fault in the log, and the game went on (chapter end and castle, or the player's
turn back) with the same kinds of screens after the kill (talk, stage complete, castle, map) as the randomizer-off run.

| Chapter | Boss | Old class | New class | Result | After the kill (on = off) | SEEN picture (new class) | Jobs (on / off) |
|---|---|---|---|---|---|---|---|
| A013 | Selena | Mercenary | Cavalier | passed | talk, player's turn back | `build/r64/bosses/jobs/p64-A013-selena/boss_page-5892.png` | p64-A013-selena / p64off-A013-selena |
| A014 | Daniela | Strategist | Sorcerer | passed (retry) | talk, Stage Complete, castle | `build/r64/bosses/jobs/r64-A014-boss/boss_page-5676.png` | r64-A014-boss / r64off-A014-boss |
| A016 | Iago | Sorcerer | Dark Knight | passed | talk, player's turn back | `build/r64/bosses/jobs/p64-A016-boss/boss_page-5686.png` | p64-A016-boss / p64off-A016-boss |
| A019 | Illusion | General | Great Knight | passed (retry) | talk, player's turn back | `build/r64/bosses/jobs/r64-A019-boss/boss_page-5760.png` | r64-A019-boss / r64off-A019-boss |
| A023 | Arthur | Hero | Paladin | not fought in round 64; **passed in round 65** (side track, below) | round 65: talk (his lines and his death line), player's turn back, the same on and off | `build/r65/side/jobs/s65-A023-arthur/boss_page-5606.png` (round 64: `build/r64/bosses/jobs/r64-A023-arthur/boss_page-5606.png`) | s65-A023-arthur / s65off-A023-arthur (round 64: r64-A023-arthur / r64off-A023-arthur) |
| A026 | Peri | Great Knight | Paladin | passed | talk, player's turn back | `build/r64/bosses/jobs/p64-A026-peri/boss_page-6076.png` | p64-A026-peri / p64off-A026-peri |
| B010 | Takumi | Archer | Apothecary | passed | talk, player's turn back (the robot then opened the map menu itself, on and off alike) | `build/r64/bosses/jobs/p64-B010-boss/boss_page-5980.png` | p64-B010-boss / p64off-B010-boss |
| B011 | Setsuna | Archer | Apothecary | passed (retry) | talk, player's turn back | `build/r64/bosses/jobs/r64-B011-setsuna/boss_page-5424.png` | r64-B011-setsuna / r64off-B011-setsuna |
| B012 | Ryoma | Swordmaster | Blacksmith | passed (retry) | talk, Stage Complete, castle | `build/r64/bosses/jobs/r64-B012-boss/boss_page-5800.png` | r64-B012-boss / p64off-B012-boss |
| B015 | Invader | Hero | Great Knight | passed | talk, Stage Complete, castle | `build/r64/bosses/jobs/p64-B015-boss/boss_page-5896.png` | p64-B015-boss / p64off-B015-boss |
| B025 | Ryoma | Swordmaster | Blacksmith | passed (retry) | talk, player's turn (he survived Corrin), second attacker kills, talk, Stage Complete, castle | `build/r64/bosses/jobs/r64-B025-boss/boss_page-5756.png` | r64-B025-boss / r64off-B025-boss |

All 11 pictures in one sheet: `build/r64/bosses/review/boss_pages_on.png`. Each job folder also has the battle
(`bosskill_battle-*.png`) and where it ended (`bosskill_end-*.png`). The randomizer-off runs had every boss in its
original class (memory, 11/11).

Together with round 63 (13 passed) and round 62 (C017 Iago), **24 of the 25 changing story/generic bosses are now
proven past their scenes**; A023 Arthur is the one left.

Review (round 64, 10 minutes; the robot pools were not re-run, 36 jobs are more than the review allows):
- `python build/r64/bosses/judge64.py` re-run: the same 10 passed, 0 broke, 1 still not fought. Every result has the
  frozen boot-server 1b8b2593 and capture library 610f791d.
- SEEN by the reviewer: all 11 pages in the sheet show the new class name. Six bosses were opened in detail (A014,
  A023, A026, B010, B012, B025): each off page shows the old class at the same unit and spot; the kill-battle
  forecasts show the boss in the fight; the end screens match between off and on.
- A023 is honest as "not fought": at its end screen Arthur is a Paladin at 1/37 HP (on) and a Hero at 1/38 (off),
  the Elise talk scene is the same in both, and no fight happened.
- B012's yardstick: the randomizer-on retry (`r64-B012-boss`) is judged against the FIRST off run
  (`p64off-B012-boss`), which used the driver from before the pair-up fix (there is no `r64off-B012` run), so the
  steps are not strictly the same code. Both reached the same "Chapter 12: Bitter Intrigue" Stage Complete (turn 1),
  so the pass holds.

### The Seal edition's boss might, seen on screen (goal 2)
Moved to the boss page in docs/seal/ in round 84.

### Open after round 64
- (Done in round 65: passed, see "Round 65 (side track)".) A023 Arthur: not fought. Next try: an `attack_keys` list that moves down past Talk to Attack (or the attacker
  Corrin swapped for a unit who cannot talk to him). Not run: its one retry is used.
- (Done in round 65: moved into tools/harness/rcheck.py with selftests, docs/tests/RCHECK.md.) The new job keys (`place_next` with the unit-grid search, the armed-attacker swap, `boss_look`, and `touch_page`
  in build/r64/bosses/might/p64m.py) live in the round drivers, not yet in tools/harness/rcheck.py, and have no
  selftest (docs/tests/RCHECK.md, round 64 note). Moving them into rcheck.py with a selftest is the next step; the
  Seal track's robot needs `place_next` too (the boss page in docs/seal/).

## Round 65 (side track): A023 Arthur fought and passed

**Result: passed.** With the randomizer on (seed r63fboss1, run `r63fboss1-1692cf97`, a copy of round 64's run)
Arthur stood on the map as a **Paladin** (memory `JID_パラディン男`, 37 HP; the bottom screen says Paladin), Corrin
killed him in that class, his two lines ("In the name of justice ..." before the fight and "I've failed you, Lady
Elise..." when he falls) played, and the player's turn came back with no fault in the log. The randomizer-off
yardstick did the same steps with Arthur as a **Hero** (`JID_ブレイブヒーロー男`, 38 HP): the same screens after the
kill (two talk windows, then the map), the same lines. So his scene does not break; he stays changing (owner rule),
config/randomizer/rules.json untouched.

How the robot got past Talk: tools/harness/rcheck.py's `place_next` (moved there this round) now has a talk skip.
Next to Arthur, Corrin's unit command reads Talk, Attack, Items, Convoy, Wait; the first A opened the Elise talk
(as in round 64). The robot saw a talk window before any battle forecast, loaded the square's memory slot back and
tried again with one DOWN before the attack keys: Attack, the forecast, the battle. Both jobs: 1 try with Talk, 1 with
Attack, first wave, first square (16,13).

- Program: frozen boot-server 1b8b2593 + capture library 610f791d (build/r65/side/bin, = build/r62b FINAL; sha
  checked before each job and written in each result). Driver `build/r65/side/p65s.py` (rcheck.run_job).
- Pictures: on/off sheet `build/r65/side/arthur_sheet.png` (boss page, unit command, the talk, Attack picked, battle,
  his two lines, the map after). Per job: `boss_page-5606.png`, `b0w00_cmd1_moved-5867.png` (Attack highlighted),
  `bosskill_talk0-6145.png`, `bosskill_talk2-6795.png` (his death line), `bosskill_end-7165.png` in
  `build/r65/side/jobs/s65-A023-arthur/` and `build/r65/side/jobs/s65off-A023-arthur/`.
- Robot only until the owner says ok (F-037). With round 63 (13), round 64 (10) and round 62 (C017 Iago),
  **all 25 changing story/generic bosses have now been run past their scenes** (robot).
- Integrate review (round 65): SEEN on the sheet and in both result.json files (Hero 38 HP off, Paladin 37 HP on, the
  bottom screen reads Paladin, Talk then Attack highlighted, his two lines, the horse in his death scene, the end screen
  byte-identical on and off). Arthur shows 1 HP in the talk frames of both runs: that is the F-030 test cheat (the boss
  at 1 HP in the run's own copy), the same on and off, not a fault.

## Round 63 setup
- Program: a frozen copy of the installed build's boot-server (1b8b2593, build/r62b/FINAL_SHA.txt) and capture
  library (610f791d, build/r62/FINAL_SHA.txt, not rebuilt since) in build/r63/bosses/bin; the sha256 is checked
  before every job and written in every result (all 61 results: these two shas).
- Seed: **r63fboss1**, run id `r63fboss1-1692cf97` (Boss classes on, everything else off), made at HEAD 3494924 with
  `build/r63/bosses/mkrun.py`. Every one of the 24 bosses changes class in it (`build/r63/bosses/bossmap_before.json`).
- Driver: `build/r63/bosses/p63.py` (round 62's p61.py -> pairs.py -> tools/harness/rcheck.py `bosskill`, read
  only, loaded as modules). Each job runs in its own process; up to 5 at once and never more than 6 boot-server.exe on
  the machine; headless (no window), below normal priority; data, APPDATA, LOCALAPPDATA under
  build/r63/bosses/jobs/<job>/; build/STOP_ROUND checked before every start; each job killed at its 8-minute cap
  (none reached it: the longest took 200 s).
- Runs: 24 first runs, 13 retries (one each, for the bosses that did not pass), 24 randomizer-off runs. No run
  was started twice.
- Retry changes: one turn ended first (the guards walk away from the boss, as round 62 did), three tries instead of
  two, and the Yes/No dialog answered with Yes (`yesno_left`). That last part fixed A018 Leo and A025 Iago. Their
  first runs killed the boss, but Corrin's inventory was full, so the dropped item's "send one item to the convoy"
  dialog looped (picture: build/r63/bosses/jobs/bk-A018-boss/bosskill_end-15019.png). The option is now also in
  tools/harness/rcheck.py's bosskill (opt-in job key `yesno_left`; selftest 52/52).
- Judge: `build/r63/bosses/judge63.py` -> `build/r63/bosses/verdicts.json`.
  - **passed scenes**: the boss was in its new class, it died, and the game went on with no fault in the log. "Went
    on" means either the chapter ended (Stage Complete, castle) or the player's turn came back after the boss's
    lines.
  - **broke**: the server died, a fault, or the game got stuck in a scene.
  - **ran, no kill** (judge63.py writes "not run"): the run happened inside its cap and the boss stood in its new
    class, but the robot itself could not get the boss killed, so the scenes after the kill are not proven.
- The randomizer-off run is the yardstick. Every boss's result and end (chapter end, or player's turn back) is the
  same with the randomizer off.

## Per boss
| Chapter | Boss | Old class | New class | Seed | Result | After the kill / why not | Randomizer off | Evidence |
|---|---|---|---|---|---|---|---|---|
| A008 | Fuga (story boss) | Master of Arms | Blacksmith | r63fboss1 | passed scenes | player phase back | passed scenes, same | `build/r63/bosses/jobs/bk-A008-boss` |
| A013 | Selena (story boss) | Mercenary | Cavalier | r63fboss1 | ran, no kill (stays changing) | no battle: the robot found no reachable tile next to the boss | ran, no kill, same | `build/r63/bosses/jobs/bk2-A013-selena` |
| A014 | Benny (story boss) | Knight | Cavalier | r63fboss1 | passed scenes | player phase back | passed scenes, same | `build/r63/bosses/jobs/bk-A014-benny` |
| A014 | Daniela (boss) | Strategist | Sorcerer | r63fboss1 | ran, no kill (stays changing) | no battle: the robot found no reachable tile next to the boss | ran, no kill, same | `build/r63/bosses/jobs/bk2-A014-boss` |
| A016 | Iago (boss) | Sorcerer | Dark Knight | r63fboss1 | ran, no kill (stays changing) | no battle: the robot found no reachable tile next to the boss | ran, no kill, same | `build/r63/bosses/jobs/bk2-A016-boss` |
| A018 | Leo (story boss) | Dark Knight | Strategist | r63fboss1 | passed scenes (retry: full inventory answered) | Stage Complete, castle | passed scenes, same | `build/r63/bosses/jobs/bk2-A018-boss` |
| A019 | Illusion (boss) | General | Great Knight | r63fboss1 | ran, no kill (stays changing) | no battle: the robot found no reachable tile next to the boss | ran, no kill, same | `build/r63/bosses/jobs/bk2-A019-boss` |
| A023 | Effie (story boss) | General | Paladin | r63fboss1 | passed scenes | player phase back | passed scenes, same | `build/r63/bosses/jobs/bk-A023-effie` |
| A023 | Arthur (story boss) | Hero | Paladin | r63fboss1 | ran, no kill (stays changing) | no battle: the robot found no reachable tile next to the boss | ran, no kill, same | `build/r63/bosses/jobs/bk2-A023-arthur` |
| A023 | Beruka (story boss) | Wyvern Lord | Malig Knight | r63fboss1 | passed scenes | player phase back | passed scenes, same | `build/r63/bosses/jobs/bk-A023-beruka` |
| A025 | Iago (boss) | Sorcerer | Dark Knight | r63fboss1 | passed scenes (retry: full inventory answered) | Stage Complete, castle | passed scenes, same | `build/r63/bosses/jobs/bk2-A025-boss` |
| A026 | Peri (story boss) | Great Knight | Paladin | r63fboss1 | ran, no kill (stays changing) | no battle: the robot found no reachable tile next to the boss | ran, no kill, same | `build/r63/bosses/jobs/bk2-A026-peri` |
| A026 | Xander (story boss) | Paladin | Hero | r63fboss1 | passed scenes | Stage Complete, castle | passed scenes, same | `build/r63/bosses/jobs/bk-A026-boss` |
| B010 | Takumi (story boss) | Archer | Apothecary | r63fboss1 | ran, no kill (stays changing) | no battle: the robot found no reachable tile next to the boss | ran, no kill, same | `build/r63/bosses/jobs/bk2-B010-boss` |
| B011 | Setsuna (story boss) | Archer | Apothecary | r63fboss1 | ran, no kill (stays changing) | no battle: the robot found no reachable tile next to the boss | ran, no kill, same | `build/r63/bosses/jobs/bk2-B011-setsuna` |
| B012 | Ryoma (story boss) | Swordmaster | Blacksmith | r63fboss1 | ran, no kill (stays changing) | no battle: the robot found no reachable tile next to the boss | ran, no kill, same | `build/r63/bosses/jobs/bk2-B012-boss` |
| B013 | Orochi (story boss) | Onmyoji | Basara | r63fboss1 | passed scenes | player phase back | passed scenes, same | `build/r63/bosses/jobs/bk-B013-orochi` |
| B013 | Takumi (story boss) | Sniper | Mechanist | r63fboss1 | passed scenes | player phase back | passed scenes, same | `build/r63/bosses/jobs/bk-B013-takumi` |
| B015 | Invader (boss) | Hero | Great Knight | r63fboss1 | ran, no kill (stays changing) | no battle: the robot found no reachable tile next to the boss | ran, no kill, same | `build/r63/bosses/jobs/bk2-B015-boss` |
| B018 | Nohrian (boss) | General | Paladin | r63fboss1 | passed scenes | player phase back | passed scenes, same | `build/r63/bosses/jobs/bk-B018-boss2` |
| B025 | Ryoma (story boss) | Swordmaster | Blacksmith | r63fboss1 | ran, no kill (stays changing) | battles, but the boss survived every try | ran, no kill, same | `build/r63/bosses/jobs/bk2-B025-boss` |
| C023 | Scarlet (story boss) | Wyvern Lord | Malig Knight | r63fboss1 | passed scenes | player phase back | passed scenes, same | `build/r63/bosses/jobs/bk-C023-scarlet` |
| X012 | Invader (boss) | General | Paladin | r63fboss1 | passed scenes | player phase back | passed scenes, same | `build/r63/bosses/jobs/bk-X012-boss` |
| X021 | Zhara (boss) | Mercenary | Cavalier | r63fboss1 | passed scenes | player phase back | passed scenes, same | `build/r63/bosses/jobs/bk-X021-boss` |

Shots in each job folder: `map-*.png` (the map at the start), `bosskill_battle-*.png` (the battle with the boss),
`bosskill_end-*.png` (where it ended; for A018, A025 and A026 the Stage Complete screen). The first try of a retried
boss is the `bk-` folder; the randomizer-off runs are `bkoff-`.

"Player phase back" means: in that chapter, killing this boss does not end the chapter. Examples are a retainer who
retreats, or a boss who is not the last one. The randomizer-off run behaves the same way.

## The might fix does not change which class a boss gets (host check)
`build/r63/bosses/hostcheck.py` makes seed r63fboss1 twice: once with the randomizer at HEAD 3494924 (a copy laid at
build/r63bosshead with `git archive`), once with the working tree's tools/randomizer (the might track's fix in
weapons.py, rando.py, stats.py, tracks.py as of 10:40). It does this with Boss classes alone, and with Tougher
bosses on at Easy, Normal and Hard. The class of every boss line (30 lines) is the same in all 4 variants, while the
Hard spoiler's forge lines do differ (so the new code really ran). The robot's laid run equals the HEAD make. Result:
`build/r63/bosses/hostcheck.json`. The integrate step should run it once more on the final code (exit 0 = same).

## Integrate notes (round 63)
- Labels: the review pointed out that "not run" was not quite right for the 11; those runs did happen inside the cap,
  only the kill was missing. This page now says "ran, no kill".
- Cheats: the F-030 cheats used were the boss at 1 HP and a long move for the attacker. Placing a unit next to the
  boss was not used, so a boss with no reachable square stays out of reach. That is the obvious next try.
- The new class is proven from memory only (class_on_map 24/24 on, original class 24/24 off). No screenshot shows the
  boss's class (the map shots of bk2-A018 and bkoff-A018 are byte-identical; indirect signs only, e.g. A018 Leo's Atk
  17 on vs 16 off).
- hostcheck.py was rerun by the integrate step on the final code (might fix included): exit 0, the 30 boss lines are
  the same for classes alone, Easy, Normal and Hard; the laid run equals the HEAD make
  (build/r63/integ_hostcheck.out).

## Not done / open
- The 11 bosses without a kill still have no battle proof. They need a better way for the robot to reach them, such as
  more turns or a flier. They stay changing (owner rule).
- Not on the list, but seen: Paralogue X002's generic boss (the Invader) also changes class in every seed made
  this round, although it is not in `proven_bosses`. The spoiler marks it as a "boss" row, so it is probably
  governed by the generic-boss rule, not the story list. It was not run here.
