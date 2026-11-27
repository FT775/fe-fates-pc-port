# Round 82 full check, track new (N1-N5 of docs/ROUND82_PLAN.md): rounds 80, 81 and 81b's new parts on every path

**In plain words.** Nothing was built and nothing was fixed. The installed program (round 81b) was checked through
copies, the way you will start a game. **True hit** shows the right numbers in one fight on Conquest, Revelation and Seal of Flames, and in Chapter 2 (a
chapter every path plays before the split; no fight on Birthright's own chapters was measured). **Esc > Helpers**
works on Fire Emblem Fates and on Seal of Flames: the heading, True hit and the New Game defaults line (line closed),
then all 14 row buttons (line open), were each on screen when the robot read them (not proven all at once), and the robot's own settings file saved every click and went back to the defaults.
**The Fates play chain works:** New Game on Normal + Classic with all four New Game defaults rows set and the
randomizer on (everything, full swap, Nuzlocke) gave exactly one pick, one randomized game, one Nuzlocke game and one
settings write; at the Prologue's first player turn the game's Options hold your four choices and the randomized
enemy is on the map (seen). **Old saves from round 76 load** with no write, no pick and no warning.

**One FAIL (not fixed, it needs your yes):** on **Seal of Flames**, a New Game on **Normal + Classic** with the
randomizer on does **not** randomize. No pick, no randomized game, no warning line, and the Randomizer page never
opens. You get the plain Seal game without being told. On Seal, Normal + Casual works (one write, one pick, the
randomized game, seen on the first map). Until it is fixed: on Seal of Flames pick Casual or Phoenix for a
randomized game.

Nothing counts as done until you say ok (F-037).

## Frozen program (any other sha is refused; every result carries these)
| File | sha256 (first 8) |
|---|---|
| play/game/Fire Emblem Fates.exe | c2791862 |
| play/game/build-record.json | 9c171545 |
| play/game/game-path.txt | 9b5eb6e3 |
| boot-server.exe (engine/target/zakuro-server/release) | 90e5638a |
| server_build.json | 2dee1628 |
| capture library 0004000000179800.dll | 405f2bac |
| harness_build.json | 877196b9 |

Copies in build/r82/new/bin (SHA256.txt); common.check_bin() refuses any other sha before every job, and every
result / meta file records the seven shas ("frozen"). play/game's own exe was never run.

## The results
| Item | Verdict | Evidence |
|---|---|---|
| N1 True hit, Chapter 2 (shared by all paths, before the split; listed as Birthright by the track) | **SEEN** (shown number) + robot (real number) | build/r82/new/n1/jobs/fc-bt-ch2-route/forecast-14970.png |
| N1 True hit, Birthright's own chapters (after the split) | **NOT REACHED** (A004 found no battle; Chapter 2 measured instead) | n1/jobs/fc-bt-A004, fc-bt-A004-2 |
| N1 True hit, Conquest | **SEEN** + robot | n1/jobs/fc-cq-B010/forecast-6619.png |
| N1 True hit, Revelation | **SEEN** + robot | n1/jobs/fc-rv-C017/forecast-5660.png |
| N1 True hit, Seal of Flames | **SEEN** + robot | n1/jobs/fc-seal-R006/forecast-6678.png |
| N1 the program's own "real NN" label on screen | **NOT REACHED** (as round 80) | painted copies n1/painted_{bt,cq,rv,seal}.png |
| N2 Esc > Helpers, Fates | **robot PASS** (17/17 checks) | n2/h2-fates/pagebot.jsonl, n2/verdict-h2.json |
| N2 Esc > Helpers, Seal of Flames | **robot PASS** (17/17 checks) | n2/h2-seal/pagebot.jsonl, n2/verdict-h2.json |
| N2 the help line | **NOT REACHED** (no robot target) | - |
| N3 play chain, Fates, Normal + Classic | **PASS** (robot + SEEN) | chain/n3-game, chain/n3-srv2, chain/n3-verdict.json |
| N3 swapped faces on the Prologue map | **NOT REACHED** (the Prologue has no swapped person) | spoiler / full.txt of r82n3-27c3f519 |
| N4 Seal, Normal + **Classic** | **FAIL** | chain/n4-cla, chain/n4-srv, n4page/quick-seal-classic |
| N4 Seal, Normal + Casual | **PASS** (robot + SEEN to the first map) | chain/n4-cas, chain/n4-srv-cas |
| N5 round-76 chapter save | **robot PASS** | n5/n5-ch, n5/verdict.json |
| N5 round-76 battle save | **robot PASS** | n5/n5-bt, n5/verdict.json |

(All paths below are under build/r82/new/.)

### N1 True hit on the forecast (round 80's T rules)
The robot opened one forecast per path on the boot-server copy and read the game's own forecast number (BattleInfo
Side +0x30, round 80 T1: the number the game shows and rolls). The real chance is the game's two-roll number out of
10000 for that shown number; round 80 T1 proved our 101-row table equals the game's own
`GetHitProbabilityEffectiveDenominator10000` for every shown 0..100, and the table read from build/r80/hit is
byte-for-byte patch 0038's THRESHOLDS (101 of 101). True hit's label is "real" + round(threshold / 100), only for a
shown 51..99.

| Path | Fight (how reached) | Shown hit, left / right (picture = memory) | True hit label, left / right |
|---|---|---|---|
| Chapter 2 (shared; not a Birthright-only chapter) | bt-ch2 recorded route, frame 14970 (round 80's own forecast frame; no poke): Corrin with Ganglari against Kaze | 71 / 100 | real 80 / none (100 is already certain) |
| Conquest | chapter select B010, Effie attacks (rcheck attack_unit, as round 64's rc2-cq-B010) | 83 / 88 | real 93 / real 96 |
| Revelation | chapter select C017, Corrin attacks the boss after one turn (rcheck boss kill, as round 62/65) | 76 / 96 | real 86 / real 99 |
| Seal of Flames | chapter select R006 from rv-ch11-clear, route byte 2, Hinoka attacks the boss Scarlet | 97 / 68 | real 99 / real 76 |

- SEEN (opened): all four forecast pictures show exactly the numbers memory gave (71% / 100%, 83% / 88%,
  76% / 96%, 97% / 68%), once on Fates (three times) and once on Seal of Flames. Read twice on the same frame
  (Conquest, Revelation, Seal): equal.
- The program's own label: **NOT REACHED**, as in round 80: only the game exe reads the Helpers row, and its headless
  mode draws no picture; the boot-server has no Helpers setting. The painted copies (round 80's
  build/r80/repair/t2/replica_paint_b2.py on these real frames, labelled as copies, not the program) put "real 80",
  "real 93 / real 96", "real 86 / real 99" and "real 99 / real 76" above the Hit boxes; opened: SEEN on
  painted_bt.png and painted_seal.png, clear of the numbers.
- Pokes (carried, docs/CHEATS.md): chapter select (chapsel rule 2, the Seal route byte), rcheck's attack pokes
  (ua<n>, b<n>w<k>: the target's HP to 1, the move bonus); the HP of 1 shows on the Conquest, Revelation and Seal
  pictures. The hit number does not depend on HP. Birthright used no poke.

### N2 Esc > Helpers (page robot, our scenario r82h, hook steps from rounds 80/81 only)
Start game (original game), Esc > Paused; the targets read; the defaults read back from the job's OWN settings.toml;
True hit On (saved); the New Game defaults line opened; Battle animations Off, Map speed Fast, Enemy turn skip All,
HP bars Off (saved, all four); the 14 row targets read; every row and True hit put back (saved: the defaults again,
the round trip); Esc closed. Same on Fates and Seal of Flames.

- Checks (17, all true on both): the hook ran all 38 steps, no unknown step, ended by itself, the game laid first,
  Esc opened and closed, the heading target, both True hit targets, the New Game line target, all 14 row targets,
  4 of 4 settings reads right, every read from the job's own file, the round trip, 12 clicks landed, 10 saves (the
  line's opening saves nothing), the owner's settings.toml the same (ed6d9057 before and after), no window.
- All 18 targets are drawn wholly on the robot's 800 x 480 screen (heading x237-282 y191-206; HP bars On, the lowest,
  y370-388), on both games, **each when it was read, not all at once**: the heading (y191-206), True hit (y209-227) and
  the New Game line (y303-321) were read with the line closed; the 14 row buttons were read after it opened, at
  y211-388, the same space True hit and the line had used, so the page moves when the line opens and the first three
  were not read again in that state. No read or picture shows all of them on screen together (integrate correction).
- The help line has no robot target (pagebot.rs lists the heading, the rows and the New Game line); **NOT REACHED**
  here, its words are covered by the program's unit tests only.
- Honest note: the first run (n2/h-fates, n2/h-seal) read the 14 row targets in the frames while the line was still
  opening and found only HP bars' three; the other 11 rows were then clicked and saved fine. The one re-run (h2-*)
  reads the targets after the four row clicks: 14 of 14.

### N3 the play chain on Fates, the way you will start
Answer made the way the page makes it (ingame.page_everything + page_answers): Randomize everything, then "How
they look" = full swap, Nuzlocke on, seed r82n3 (run r82n3-27c3f519). All four New Game defaults rows set in the
job's own settings.toml (Battle animations Off, Map speed Fast, Enemy turn skip All, HP bars Off). Route
bt-prologue-classic (Normal + Classic) up to the Prologue's first player turn.

- The game exe copy (chain/n3-game, headless, 14770 frames, 110 s): exactly **one** "New Game step was heard at the
  trap ... (Classic)", **one** "New Game mode picked at frame 4019", **one** "randomized game r82n3-27c3f519 laid",
  **one** "Nuzlocke game c930b80e2c1b4028 started" (its graveyard file made), **one** settings write
  `fates_options: New Game: battle 1->0, speed 2->1, enemy skip 0->2, hp bars 1->0 (frame 4019, block 31CC8438)`;
  no warning line.
- The game's Options block, read byte by byte: before the pick (4018) 1 / 2 / 0 / 1 (the game's own); from 4019 on,
  and at the first player turn (14640, 14760): **0 / 1 / 2 / 0** = your four choices.
- The boot-server twin (chain/n3-srv2, the same answer and route, no rows: it reads no settings file) laid the same
  run with byte-equal run files (6 of 6). Its marker walk: the Classic pick screen at 3990, the map at 13860, the
  first player turn at 14640. Every one of the 30 units on the map (player, enemy, ally) has byte-identical memory
  (0x140 bytes each) in the game exe and the twin at 14640 and 14760, so the twin's pictures show the game exe's map.
- SEEN (opened): chain/n3-srv2/shot_003990.png (Classic chosen); shot_human_014640.png (the Prologue map, Corrin's
  turn); hover_0x32626E10_014838.png: the first enemy at (19, 11) is a **Mercenary with a Bronze Sword**. The plan's
  spoiler says exactly that: "A000 unit 1 (Nohrian at 19,11): class Fighter -> Mercenary; Bronze Axe -> Bronze
  Sword". (In the plain game it is a Fighter with a Bronze Axe; see N4's Classic picture.)
- **NOT REACHED:** swapped faces on the Prologue map. The full swap changes people who join later; the run's swap
  list (full.txt) has no Prologue person, and the spoiler's A000 lines are enemy classes only. The face swap itself was
  checked by round 76's seal/full tracks, not on this program.

### N4 the same chain on Seal of Flames (keep the face, rows set, Randomizer on): FAIL on Classic
Answer: Randomize everything on Seal (keep the face, Seal's only look), seed r82n4 (run r82n4-5e09d108). Rows set as
in N3.

- **Normal + Classic (chain/n4-cla, route bt-newgame-classic): FAIL.** One settings write (same line, block 31CD43B8;
  bytes 0 / 1 / 2 / 0 from frame 4019), the run was made in the background, but **no "New Game mode picked", no run
  laid, no warning line** (the run ended at frame 4600 after 23 s, against 39 s with the pick on Casual).
  - The boot-server twin on Seal (chain/n4-srv, route bt-prologue-classic): Classic chosen (SEEN shot_003990.png), no
    pick, nothing laid; at the first player turn (15020) the first enemy at (19, 11) is a **Fighter with a Bronze Axe**
    (SEEN hover_0x3263B290_015218.png), while this answer's spoiler says Mercenary with a Bronze Sword. So the game is
    the plain one.
  - The real Randomizer page on Seal with Classic (n4page/quick-seal-classic, page robot scenario quick): the page
    **never opened** in 4600 frames (pagebot.jsonl holds only the hook's first line); its verdict FAIL.
  - Why (from the round-81b notes, not traced again): round 81b's fix listens for the New Game step in Fire Emblem
    Fates only ("Seal of Flames does not listen", RANDOMIZER_INGAME.md 16.1), and on Normal + Classic the old watch
    sees no change. The "did not use your seed" warning is Fates-only too, so nothing tells you.
- **Normal + Casual (chain/n4-cas, route new-game): PASS.** One write, one "New Game mode picked at frame 4019", one
  "randomized game r82n4-5e09d108 laid", no warning.
  - SEEN to the first map: the boot-server twin chain/n4-srv-cas (route bt-prologue, Casual) laid the same run with the
    same 4 run files, and the first enemy at (19, 11) is a **Mercenary with a Bronze Sword** (hover_0x3263B290_015218.png),
    as the spoiler says.

### N5 old saves (round 76) on this program
Both with all four rows set and a queued randomizer answer (seed r82n5), so the writer and the randomizer listen.
- Chapter save (n5/n5-ch): a copy of build/r76/check/nuz/robot/newgame/data, the Chapter0 that round 76's Nuzlocke New
  Game wrote on the round-74 program, loaded with bt-ch2's title presses. No settings write, no pick, no lay, no
  warning; the saves byte-for-byte unchanged.
- Battle save (n5/n5-bt): a copy of build/r76/check/nuz/robot/battle-ctrl/data (Map0.bak is the robot-made
  opt-ch8-set battle save, bound by round 76 to its run r60fnuz-5595726d; the save itself is older than round 76),
  route opt-ch8-reload. No write, no pick, no lay, no warning; the saves unchanged. Its Nuzlocke game loaded
  ("0 in the graveyard") and added its usual "classic kept" line to the graveyard file, as in round 76.
- Both: the queued answer was made in the background and never laid, which is what a load must do. Its run folder
  r82n5-f18203de, like N3's r82n3-27c3f519 and N4's r82n4-5e09d108, was written by the program to its own make folder
  build/rando-make (git-ignored, outside build/r82/new; the program picks that path itself, as in every page-robot round).

## FAILs (for your yes; nothing was fixed)
1. **Seal of Flames, Normal + Classic, randomizer on: the randomizer and its page do not start, and nothing says so.**
   Evidence: build/r82/new/chain/n4-cla/stdout.txt (no pick line), chain/n4-srv/shot_003990.png and
   hover_0x3263B290_015218.png (Classic chosen; plain Fighter where the plan has a Mercenary), chain/n4-srv-cas/
   hover_0x3263B290_015218.png (the same answer on Casual: the Mercenary), n4page/quick-seal-classic/pagebot.jsonl
   (page never opened). Likely fix (not built): let Seal of Flames listen to the same New Game step as Fates (round
   81b's patch 0041), and show the warning line on Seal too. Workaround until then: Casual or Phoenix on Seal.

## Robot notes (honest)
- Every game start was headless (game exe: `--headless N --mute`; boot-server: CREATE_NO_WINDOW), below normal, ended
  by itself, with --data, APPDATA, LOCALAPPDATA and TMP under build/r82/new/. smoke.run_tasks and pagebot's watchdog
  saw no window; STOP_ROUND never existed (checked before every job). At most 2 robot jobs of this track at once.
- The owner's files, read only (realhash.py): 17 files (real saves, settings.toml, play/config.json,
  play/state.json), aggregate 24adf7b7 before (01:27) and after (01:48); settings.toml ed6d9057 both times.
- Re-runs (each once, never twice): n3-srv -> n3-srv2 (the game run ended, but my driver's result write failed on a
  Japanese person id in the default file encoding; all files are now written as UTF-8); N2 h-* -> h2-* (target
  timing, above); N1 Birthright: fc-bt-A004 was stopped by me (the same encoding bug would have spoiled its result),
  its one re-run fc-bt-A004-2 found no battle (A004's map start opens a talk and a tutorial), so Birthright was
  measured on the recorded route bt-ch2 instead (a different job, round 80's own forecast frames, no poke). Both
  A004 folders are kept.
- No content poke; only the carried pokes listed under N1 (all in docs/CHEATS.md). No Nintendo or Seal of Flames text
  or pictures in git: the pictures stay under build/.
- Cuts: none (N5 and N4's play past the pick both ran).
- Disk: D: 75,012 MB free at the round's start (plan), 68,814 MB at 01:48 (all tracks); build/r82/new is 1.7 GB.
- Time (counted with date): track new 01:18 to about 01:51, about 33 min, against the plan's 1 h 30 (estimate, cap
  2 h 15).
- Grok: not asked (no judgment question in this track: the Seal Classic result is a fact against the plan's
  expectation).

## Where things are
build/r82/new: common.py (the frozen copies), n1.py + n1/verdict.json, n2.py + n2/verdict-h2.json (and verdict-h.json),
chain.py + n3judge.py + chain/n3-verdict.json, chain/n4-*/judge.json, n4page.py, n5.py + n5/verdict.json,
owner_before.json / owner_after.json.

## Integrate's corrections (round 82, from the reviewers; 2026-11-26 04:24 EST)
- **N1 "Birthright" moved to "Chapter 2, shared".** Route bt-ch2 is Chapter 2 (forecast-14970.png, opened by the reviewer:
  Corrin with Ganglari against Kaze), which every path plays before the split. The cell now says so, and a new row says
  **Birthright's own chapters: NOT REACHED**. True hit's rule is the same on every path (Conquest, Revelation and Seal were
  measured on their own chapters), so N1's verdict stands.
- **N2 "all on screen" narrowed.** Each target was on screen when read; the heading, True hit and the line were read with
  the line closed and the rows with it open, in overlapping space. Not proven all on one screen together (N2 section).
- **N2 first-run wording.** The track's claim text said the first run "read 11 of the row targets"; it found 3 (HP bars)
  and missed 11 (verdict-h.json row_targets_14 false). This page already said so; unchanged.
- **Make folders outside the track's folder** (r82n3, r82n4, r82n5 in build/rando-make) are now listed (N5 section).
- **The Seal + Classic FAIL is being fixed in round 82b** (patch 0042, docs/ROUND82B_PLAN.md, the owner's "Yes, that
  order"); it is staged, not installed: the program checked here is still the frozen round-81b one, so the FAIL stands for
  this program.
