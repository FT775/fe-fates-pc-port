# Round 72 full check (F-051: the everything-on matrix before the owner plays)

**In plain words.** Nothing was built. The installed round-71 program was checked through frozen copies, the same way
as round 65's check, with the randomizer frozen at HEAD c4fb6f5. Every chapter on all 4 paths started, played,
saved and reloaded with Everything on (three ways) and with the randomizer off: **536 of 536 passed**, plus 4 of 4
chapters with the new chest row on. HANDOVER 12/12, Nuzlocke on every path, the page robot (Fates and Seal),
music by sound and by memory on every path all pass. Every page row on every path has a strict pair or a memory proof;
the 3 round-71 rows are new rows of the table. **FAIL: 0. gap: 0.** Nothing counts as done until the
owner says ok (F-037).

**Final table (integrate, after the three reviewers):** 164 cells, **87 SEEN, 71 robot, 5 mem, 0 gap, 0 FAIL, 1 n/a**;
25 of them rest on a content poke in the robot's own copy and say so ("+poke": 7 SEEN+poke, 18 robot+poke; every poke
is in docs/CHEATS.md section 4). The check track's first table said 82 SEEN, 71 robot, 8 mem, 2 poke; the 28 changed
cells and why are listed under the table.

## Frozen program (any other sha is refused)
| File | sha256 | Where it comes from |
|---|---|---|
| play/game/Fire Emblem Fates.exe (page robot) | 853e713ae904b8e4548781fd3db71f32886b2f7ede43d0afc8d8ae67920ceed8 | installed by round 71 (install.py, F-056) |
| play/game/build-record.json | 384c63da2f6e3ac34a862800ab9c0a3fc3c2db3e23541a26cc28647ced5367ac | installed by round 71 |
| boot-server.exe (robot) | fb9af97987642862a0ff535c82aed326c81f6906f79752b9f88ca755fceaaad6 | engine/target/zakuro-server/release, installed by round 71 |
| server_build.json | 551eb1e1792c4df1a46acb1832792d81247d15f1859faee7d18b1e904c8383dd | installed by round 71 |
| capture library 0004000000179800.dll | 405f2bac2f383fed116a39e64c460345c711f1519b6c154016015e62645d50fb | build/harness/lib (FRESH, not rebuilt in round 71) |
| tools/harness/rcheck.py, frozen copy | 814ca233a42c82468c980f2b857ebf5e956c2d42e803966df4ec4fa966ecd6be | HEAD c4fb6f5 |

- Copies: build/r72/check/bin (SHA256.txt). **The whole of tools/harness was frozen** (git archive of HEAD c4fb6f5, tree
  8416ff9e; 68 files, bin/HARNESS_SHA256.txt). Every check process loads rcheck, server, headless, chapsel, pagebot, ...
  from that copy through bin/pyfrozen/sitecustomize.py (sha checked at import). The side tracks changed tools/harness/rcheck.py
  and pagebot.py during the check; none of that reached the check.
- tools/randomizer tree 415461d0 and config/randomizer tree 0e6826d6 (HEAD); unchanged during the check (checked at the end).

## Runs remade with HEAD's randomizer
- Every run of round 65's check was remade (make72*.jsonl): 55 Fates + 55 Seal runs plus the hand-made test runs.
- **105 runs are byte-identical to round 65's** (patch, plan, spoiler, options): every Fates run.
- **6 runs changed since round 65, all Seal of Flames**, all for one reason: **round 66's Seal boss list** (round 66 proved more
  Seal story bosses, so 7 more boss lines now change class within their rank: A013 Selena, A014 Daniela, A016 Iago (two
  lines), A019 Illusion, A023 Arthur and A023 Effie). Only placement (dispos)
  cells and the patch's end count moved (the "face" section shows only because its end count moved):
  - seal/r59s1bossclasse-62ce87d7: patch sections {'dispos': 9}; spoiler adds e.g. A016 unit 14 (boss Iago at 20,4): class Sorcerer -> Dark Knight; A019 unit 14 (boss Illusion at 15,2): class General -> Paladin; A023 unit 18 (story boss Arthur at 16,12): class Hero -> Paladin
  - seal/r59s1enemyclass-3bbda2d8: patch sections {'dispos': 9}; spoiler adds e.g. A016 unit 14 (boss Iago at 20,4): class Sorcerer -> Dark Knight; A019 unit 14 (boss Illusion at 15,2): class General -> Paladin; A023 unit 18 (story boss Arthur at 16,12): class Hero -> Paladin
  - seal/r59sall1-3d54cbff: patch sections {'face': 1, 'dispos': 8}; spoiler adds e.g. A013 unit 15 (story boss Selena at 8,1): class Mercenary -> Cavalier; A014 unit 14 (boss Daniela at 13,1): class Strategist -> Sorcerer; A016 unit 13 (boss Iago at 20,4): class Sorcerer -> Dark Knight
  - seal/r59sall2-9aac3dce: patch sections {'face': 1, 'dispos': 8}; spoiler adds e.g. A013 unit 15 (story boss Selena at 8,1): class Mercenary -> Cavalier; A014 unit 14 (boss Daniela at 13,1): class Strategist -> Dark Knight; A016 unit 13 (boss Iago at 20,4): class Sorcerer -> Dark Knight
  - seal/r59sall3-50f4bf8f: patch sections {'face': 1, 'dispos': 8}; spoiler adds e.g. A013 unit 15 (story boss Selena at 8,1): class Mercenary -> Cavalier; A014 unit 14 (boss Daniela at 13,1): class Strategist -> Dark Knight; A016 unit 13 (boss Iago at 20,4): class Sorcerer -> Dark Knight
  - seal/r60snuz-59821ef6: patch sections {'face': 1, 'dispos': 8}; spoiler adds e.g. A013 unit 15 (story boss Selena at 8,1): class Mercenary -> Cavalier; A014 unit 14 (boss Daniela at 13,1): class Strategist -> Sorcerer; A016 unit 13 (boss Iago at 20,4): class Sorcerer -> Dark Knight
- **The chests row (off by default) and the Recolour row (default "Their own colour") changed no existing run**: both are
  left out of the answer while at their default (omit_default), so every run id and every byte stayed the same.
- New this round (5): fates/r59f1chests-2da84e5f, fates/r59f1recolour-840c7dbc, fates/r64f1recol5-2b6c3a59, seal/r59s1chests-e716af57, seal/r59s1recolour-0aaee64a (the chests row on alone, Recolour "Easier to see" on the recolour
  runs' seeds, and Conquest's r64f1recol5 seed with "Easier to see").
- Hand-made test runs copied unchanged because their source runs did not change: Hayato, Sakura (Fates skill_slots_c) and the
  Seal recolour nocol twin; r64f1recol5 and its nocol twin were remade (byte-identical to round 65's).

## Break check: every chapter, 4 paths, all1 / all2 / all3 / off (536 of 536), plus the chests row
| Path | off | all1 | all2 | all3 | chests on |
|---|---|---|---|---|---|
| Birthright | 41/41 | 41/41 | 41/41 | 41/41 | 1/1 |
| Conquest | 30/30 | 30/30 | 30/30 | 30/30 | 1/1 |
| Revelation | 22/22 | 22/22 | 22/22 | 22/22 | 1/1 |
| Seal of Flames | 41/41 | 41/41 | 41/41 | 41/41 | 1/1 |

A pass means (classify.py as rounds 62 and 65): chapter select, onto the map, an enemy phase, a battle save and a reload with
the same units; no log fault; every patched cell right in memory on the map and after the reload; the laid-cell count equals
the patch; no player unit missing. The chests jobs (Birthright A007, Conquest B010, Revelation C008, Seal R006) also logged
"chest hook on" with the run's gift count.

**HANDOVER: 12 of 12 pass** (Revelation 9 and 13, Conquest 9; off and all1-3).

**A crash burst, retried once (honest):** from 18:51:58 to 18:55:31 every boot-server that started (or reloaded) stopped
at its first step with exit 0xC0000005 (3221225477): 56 jobs in all (jobs: 33, n\checks\pjobs: 3, n\might\pjobs: 4, n\mights\pjobs: 4, pjobs: 12).
Before 18:51:58 and after 18:55:31 no job crashed (0 of every other result). No Windows error event was written and the
server folders were already removed, so the cause is not known (the machine also ran the side tracks' robots and the
integrate track's tests then; memory pressure is the likeliest guess). Each of the 56 jobs was run once more (F-042 rule
b: at most one retry), its first result kept in build/r72/check/crash1/: all 56 ran through; 2 of them (bc-bt-A014) stop
at the boss kill with "no reachable tile", exactly as in round 65 (their class pictures are valid). The counts above are the
retried results.

## Nuzlocke on every path: pass
- 4 chapter jobs (nz-bt-A010, nz-cq-B010, nz-rv-C012, nz-seal-S002): nz-bt-A010-nuz PASS, nz-cq-B010-nuz PASS, nz-rv-C012-nuz PASS, nz-seal-S002-nuz PASS.
  Graveyard loaded, the fallen in no army and not on the map, Casual switched to Classic, no log fault.
- 5 gate proofs on the frozen program: path PASS, death PASS, battle PASS, newgame PASS, profile PASS (castle load on all 4 paths, a real death, the battle save, a new Nuzlocke game, the profile).

## Page robot (the real in-game page; frozen exe 853e713a)
| Run | Verdict | Start game -> run laid | -> the avatar |
|---|---|---|---|
| quick-f | PASS | 0.032 s | 0.567 s |
| quick-s | PASS | 0.144 s | 0.585 s |
| agency-f | PASS | 5.472 s | 5.914 s |
| agency-s | PASS | 6.648 s | 7.089 s |

- The owner's rule holds in all 4 runs (the laid game is byte for byte a fresh make; a stale guess is thrown away).
- **The 2 s target still fails right after a late row change** (5.5 s Fates, 6.6 s Seal; round 65:
  5.1 / 6.3 s, round 71's library mode 5.3 s). The known engine item; not a randomizer regression.
- Not a quiet machine this time: the side tracks' robots were running (build/r72/check/pagebot/load_before.txt), so the
  times may be a little high.

## Music: by sound and by memory on all 4 paths (round 65's memory-scan miss closed)
| Path, chapter | Sound | OFF vs ON | ON vs ON2 | Map song | Memory scan (runtime song label) |
|---|---|---|---|---|---|
| Birthright A015 | PASS | 0.4976 | 1.0 | STRM_MAP_B3 -> STRM_MAP_B4 | PASS (327e3131) |
| Conquest B010 | PASS | 0.4594 | 1.0 | STRM_MAP_B2 -> STRM_MAP_B5 | PASS (327e1d31) |
| Revelation C012 | PASS | 0.4906 | 1.0 | STRM_MAP_B3 -> STRM_MAP_B4 | PASS (327e0db9) |
| Seal of Flames S002 | PASS | 0.4336 | 1.0 | STRM_MAP_B1 -> STRM_MAP_A4 | PASS (329041b9) |

Sound: under 0.8 = a different song, over 0.98 = repeatable. Memory: the runtime buffer holds the old map song OFF and the
spoiler's new one ON at the same frame (music60.py). Round 65 ran the memory scan on Birthright only; it now passes on all 4.

## The 40 alternate lanes round 65's time box cut
- **Run: 40 of 40** (s_laneI, the music memory scans, ran early on purpose).
- Cut again by this round's claim deadline (21:45): 0 (none).
- They hold second and third pairs for cells that already have a valid pair, so no cell depends on them.

## Every page row on every path (final table, integrate)
SEEN = a reviewer opened an OFF/ON pair made on THIS program and saw the change (the check's reviewer: review/seen72.json,
pictures under build/r72/check/review; for Shops, Children on Conquest and the Conquest / Seal chests: the castle_esc and
bosses_chests reviewers, pictures under build/r72/castle/look and build/r72/chests/review). robot = a strict robot pair
is valid on this program, nobody looked. mem = memory only (no recorded route reaches the screen). gap = the robot pair
passed but does not show the change. **+poke** = the pair the mark rests on was reached with a content poke in the
robot's own copy (a seal, exp, HP, move, placement or item poke; build/r72/integrate/pokescan.json reads every valid
pair's `job.pokes` and `pokes_extra`, a poke written after the judged shot not counted; docs/CHEATS.md section 4 says
what and why). The chapter-select pokes every job makes are not content pokes. n/a = the row is not on that path's page.

| Setting | Birthright | Conquest | Revelation | Seal of Flames |
|---|---|---|---|---|
| Shuffle (route) | robot | robot | robot | robot |
| Shuffle (any) | robot | robot | robot | robot |
| Recolour | SEEN | SEEN+poke | SEEN | robot |
| Classes | SEEN | SEEN | SEEN | SEEN |
| Join stats | SEEN | SEEN | SEEN | SEEN |
| Growths | robot | robot+poke | robot+poke | robot+poke |
| Personal skills | SEEN | SEEN | SEEN | SEEN |
| Skill slots | robot | robot | robot | robot |
| Promotions (Master Seal) | robot+poke | robot+poke | robot+poke | robot+poke |
| Heart Seal classes | robot+poke | robot+poke | robot+poke | robot+poke |
| Children | robot | SEEN+poke | robot | n/a |
| Class growths | robot+poke | robot+poke | robot+poke | robot+poke |
| Class bases | robot | robot | robot | robot |
| Class movement | robot | robot | robot | robot |
| Starting items | SEEN | SEEN | SEEN | SEEN |
| Shops | SEEN | SEEN | SEEN | mem |
| Castle rewards | mem | mem | mem | mem |
| Weapon stats | robot | robot | robot | robot |
| Weapon special powers | robot | robot | robot+poke | robot+poke |
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
| Story boss classes (class change) | SEEN+poke | SEEN+poke | SEEN+poke | SEEN |
| Boss might/HP: Easy | SEEN | SEEN | SEEN | SEEN |
| Boss might/HP: Normal | SEEN | SEEN | SEEN | SEEN |
| Boss might/HP: Hard | SEEN | SEEN | SEEN | SEEN |
| Chest and village items (row on) | SEEN | SEEN+poke | robot | SEEN+poke |
| Recolour: Easier to see | SEEN | robot+poke | robot | robot |
| Growths in Preparations (Y) | SEEN | SEEN | SEEN | SEEN |

41 rows x 4 paths = 164 cells: **87 SEEN, 71 robot, 5 mem, 0 gap, 0 FAIL, 1 n/a** (sum 164); **25 of them +poke** (7 SEEN+poke, 18 robot+poke).
Per path: bt: 23 SEEN, 17 robot, 1 mem, 0 n/a, 4 +poke; cq: 23 SEEN, 17 robot, 1 mem, 0 n/a, 9 +poke; rv: 21 SEEN, 19 robot, 1 mem, 0 n/a, 6 +poke; seal: 20 SEEN, 18 robot, 2 mem, 1 n/a, 6 +poke.

### The 28 cells integrate changed (check track's mark -> final)
- Recolour, Conquest: SEEN -> **SEEN+poke**: content poke in every valid pair (pokescan.json: ua00, ua01, ua02, ua10).
- Growths, Conquest: robot -> **robot+poke**: content poke in every valid pair (pokescan.json: exp99).
- Growths, Revelation: robot -> **robot+poke**: content poke in every valid pair (pokescan.json: exp99).
- Growths, Seal of Flames: robot -> **robot+poke**: content poke in every valid pair (pokescan.json: exp99).
- Promotions (Master Seal), Birthright: robot -> **robot+poke**: content poke in every valid pair (pokescan.json: mseal).
- Promotions (Master Seal), Conquest: robot -> **robot+poke**: content poke in every valid pair (pokescan.json: mseal).
- Promotions (Master Seal), Revelation: robot -> **robot+poke**: content poke in every valid pair (pokescan.json: mseal).
- Promotions (Master Seal), Seal of Flames: robot -> **robot+poke**: content poke in every valid pair (pokescan.json: mseal).
- Heart Seal classes, Birthright: robot -> **robot+poke**: content poke in every valid pair (pokescan.json: hseal).
- Heart Seal classes, Conquest: robot -> **robot+poke**: content poke in every valid pair (pokescan.json: hseal).
- Heart Seal classes, Revelation: robot -> **robot+poke**: content poke in every valid pair (pokescan.json: hseal).
- Heart Seal classes, Seal of Flames: robot -> **robot+poke**: content poke in every valid pair (pokescan.json: hseal).
- Children, Conquest: robot -> **SEEN+poke**: castle_esc: live child join, Conquest X015 Siegbert Cavalier -> Dark Mage SEEN (build/r72/castle/look/child_join_cq_X015.png; chapter-select pokes); the check's own robot pair has no content poke.
- Class growths, Birthright: robot -> **robot+poke**: content poke in every valid pair (pokescan.json: enemyhp1, exp99).
- Class growths, Conquest: robot -> **robot+poke**: content poke in every valid pair (pokescan.json: exp99).
- Class growths, Revelation: robot -> **robot+poke**: content poke in every valid pair (pokescan.json: exp99).
- Class growths, Seal of Flames: robot -> **robot+poke**: content poke in every valid pair (pokescan.json: exp99).
- Shops, Birthright: robot -> **SEEN**: castle_esc: Dawn Armory off/on SEEN by its reviewer (build/r72/castle/look/bt_armory.png); Rod Shop too (bt_rod.png); no poke.
- Shops, Conquest: robot -> **SEEN**: castle_esc: Staff Store off/on SEEN (build/r72/castle/look/cq_staff.png); no poke.
- Shops, Revelation: mem -> **SEEN**: castle_esc: Rod Shop off/on SEEN (build/r72/castle/look/rv_rod.png; one extra DOWN menu press, not in routes.json); no poke.
- Weapon special powers, Revelation: poke -> **robot+poke**: the check's 'poke' mark written as robot+poke (round 61's weapon poke in both runs).
- Weapon special powers, Seal of Flames: poke -> **robot+poke**: the check's 'poke' mark written as robot+poke (round 61's weapon poke in both runs).
- Story boss classes (class change), Birthright: SEEN -> **SEEN+poke**: content poke in every valid pair (pokescan.json: b0w00, b0w01, b0w02, b0w03).
- Story boss classes (class change), Conquest: SEEN -> **SEEN+poke**: content poke in every valid pair (pokescan.json: b0fly00, b0fly01, b0fly02, b0fly03, b0w00, b0w01, b0w02, b0w03).
- Story boss classes (class change), Revelation: SEEN -> **SEEN+poke**: content poke in every valid pair (pokescan.json: b0fly00, b0w00, b0w01, b0w02, b0w03, b0w10, b0w11, b0w12, b0w20, b0w21).
- Chest and village items (row on), Conquest: mem -> **SEEN+poke**: bosses_chests: B011 chest opened by the player (Seraph Robe on / Spirit Dust off) and B010 village (Killer Axe on / Dual Club off) SEEN (build/r72/chests/review/B011chest_on_off.png, B010village_on_off.png); Chest Key and placement pokes; village on net gain (rcheck.judge_chest double-counts the convoy move).
- Chest and village items (row on), Seal of Flames: mem -> **SEEN+poke**: bosses_chests: A016 chest opened by the player (Enfeeble on / Silence off) SEEN (build/r72/chests/review/A016chest_on_off.png); chapter-select, Chest Key and placement pokes.
- Recolour: Easier to see, Conquest: SEEN -> **robot+poke**: check reviewer: NOT SEEN (max channel difference 20/255, fainter than Seal's pair the check already demoted).

The check track's first table (82 SEEN, 71 robot, 8 mem, 0 gap, 2 poke, 0 FAIL, 1 n/a) is kept in build/r72/check/table72.md;
the final one is build/r72/integrate/table72_final.json / .md (made by build/r72/integrate/final_table.py).

Round 65's table had 38 rows (152 cells); this table adds the 3 round-71 rows (Chest and village items on, Recolour "Easier
to see", Growths in Preparations on Y): 41 rows x 4 paths = 164 cells.

### Notes on the table
- **Round 65's 3 gap cells (Revelation boss might Easy / Normal / Hard): SEEN.** The round-66 pairs on C007 Vallite (Berserker,
  Steel Axe, forged, HP under its cap), Tougher bosses off vs on, same seed: Steel Axe +1 / +2 / +3, Atk-Str 12 -> 13 / 14 / 15,
  HP 26 -> 31 / 34 / 37 (review/might_rv_C007.png). judge_boost now gets the real HP cap (rcheck.boss_hp_cap, round 66) in
  this check's copies of judge62c.py and judge65n.py: capped is no longer a loophole; Iago C017 and Hinata B010 Hard pass only
  because their HP sits exactly at the cap.
- **Chest and village items:** Birthright A007 and Revelation C008: a recorded enemy open, row on = the plan's item, row off =
  the original (rcheck.judge_chest, both pairs PASS: A007 Armorslayer -> the planned item, C008 Killer Lance -> the planned
  item; the enemy thief / ninja at (11,12) opens it). SEEN on Birthright: "The enemy swiped Armorslayer" -> "The enemy swiped
  Parasol" (review/chest_bt_A007.png). Conquest and Seal of Flames: mem (the hook is on with the run's gift list and the
  chapter passes the break rules; no recorded route opens a chest there). A chest the player opens and a village visit are
  the bosses_chests track's (cheat pokes), not this table. **Final table (integrate):** Conquest and Seal of Flames are SEEN+poke from the bosses_chests
  track: the B011 chest and the A016 chest opened by the player, and the first village proven in a game (Conquest B010,
  Killer Axe on / Dual Club off; ok on the net gain of unit and convoy, rcheck.judge_chest as run said 'more than one item
  gained' because the full inventory sent Corrin's Dragonstone to the convoy).
- **Recolour "Easier to see":** pair = the recolour job of round 65's SEEN pair vs the same seed with recolour=clear. SEEN on
  Birthright (Silas grey-blue -> dark teal) and Conquest (Effie dark red -> brighter red); Revelation and Seal pass the robot
  judge but the change is too faint to see on zoom (review/notseen72.txt). Whether it is "clearer" is the owner's call.
- **Growths in Preparations (Y):** Preparations > Select Units, Corrin: Y shows the growths, Y again hides them; SEEN on all 4
  paths (review/gprep_4paths.png).
- **Weapon special powers on Revelation and Seal (robot+poke; the check's 'poke' cells):** weapon_traits/rv, weapon_traits/seal: the Weapon special powers pairs on Revelation and Seal
  poke the same weapon into both runs (round 61's method, docs/tests/RCHECK.md); no natural draw shows the trait there.
- Children on Seal: n/a (the row is not on the Seal page). Shops on Revelation and Seal, Castle rewards on every path: mem
  (every patched cell right in memory in every all1-3 break job); the castle_esc track looks at them with pictures. **Final table:** Shops
  SEEN on Birthright, Conquest and Revelation (castle_esc, no poke); Seal stays mem (no Seal save or route reaches the castle);
  Castle rewards stay mem on every path (no screen shows them offline).
- **Integrate corrections from the check's reviewer (round 72):** Recolour "Easier to see" on Conquest is NOT SEEN (max
  channel difference 20/255 in attack0, 16 in attack1; fainter than Seal's pair, which the check already called robot): robot.
  The Birthright chest picture review/chest_bt_A007.png had a bottom pair that compared two different thieves (the opener
  with Iron Bow, 1000G, Armorslayer vs another thief with a Bronze Bow); the SEEN rests on the top pair only ("The enemy
  swiped Armorslayer" -> "The enemy swiped Parasol"), and the contact sheet now shows the top pair only
  (build/r72/integrate/review/chest_bt_A007_top.png). Memory agrees: in the ON result the opener holds item 45 where OFF has 9.
- **Boss classes on Birthright, Conquest and Revelation all rest on the same shared paralogue X002** (Invader Swordmaster ->
  Master of Arms; the Conquest and Revelation pictures look the same). That is weak per-path evidence; each path's own
  chapters are covered by the Story boss pairs (A014 Benny, B010 Takumi, C017 Iago), so no verdict changes.
- **Raw judge59.out still shows first-pass FAILs** (weapon_stats cq/seal, weapon_traits rv/seal, rewards x4, music x4,
  recolour cq/seal): "no visible change" or "byte-identical ON picture" on the first pair tried. final.json replaces them
  with later pairs (the G-variant jobs, the audio fingerprint, mem cells, the rc2 recolour pairs), the same way round 65
  did. They are superseded, not hidden FAILs; the final 0 FAIL holds.
- **The 6 chest-route results** (chest/k1-a007, k1-c008, k2-chest, on and off) carry no sha field: they record
  exe = build/r72/check/bin/boot-server.exe and the library copied from bin (p1.py / p2.py set hl.LIB to the bin dll).
  bin re-hashes to 853e713a / fb9af979 / 405f2bac / 384c63da / 551eb1e1, so they ran on the frozen program by
  construction, not by a recorded sha.
- SEEN marks of round 65 were not carried over: every SEEN cell here was opened on this program by this check. Every pair
  picture this reviewer opened that round 65 also had is byte-identical to round 65's (review/sheets.py prints it per cell).
- Not seen by eye: r71_recolour_clear/rv: C016 battle0_1 Setsuna under the red hit effect: the change (0.07% of pixels) is not visible by eye on zoom; stays robot; r71_recolour_clear/seal: S002 battle2_2 Felicia: the change (0.19% of pixels) is too faint to call by eye on zoom (lavender -> slightly pinker?); stays robot; recolour/seal: c-seal-S002-b5 nocol vs recolour battle2_1 Felicia under the hit effect: not visible by eye on zoom (as in round 65); stays robot.

## FAILs
None of the 164 cells failed.
Known misses (not cells): the 2 s Start-game target after a late row change (engine item, above).

## Robot notes (honest)
- At most 4 check robot jobs at once (run4.py: 4 workers, lock files, the claim deadline 21:45). No job ran twice at
  once; no job was retried more than once (the 56 crash-burst jobs once each).
- Harness fixes in this check's own copies only (allowed): judge62c.py / judge65n.py pass the real HP cap to judge_boost;
  final72.py's memory proof counts only all1-3 break jobs (the chests-only jobs have no GameData cells); p61.py got the
  prep_y step (Pick Units, Y, Y); judge72x.py judges the new rows; the growth floor lane first failed before any game start
  (its plane62 job lists had not been copied) and ran after they were.
- build/r72/check/shascan.json: 1,236 result files; 1,230 carry the frozen boot-server fb9af979 + capture library 405f2bac (page robot: exe 853e713a; Nuzlocke proofs: sha.exe/sha.lib), 0 carry another sha. The 6 chest-route jobs (round 71's p1/p2 drivers) record the frozen bin paths instead of a sha field; bin/SHA256.txt and every frozen harness file were re-checked at the end: all OK.
- No visible window (watch.py at every check, VISIBLE: [] each time). STOP_ROUND never existed. No new play, no engine
  build, nothing in tools/randomizer or config/randomizer changed, no write to %APPDATA% / %LOCALAPPDATA%.
- Lanes: 165 of 165 queued lanes ended; the page robot ran 17:51-17:56, the 4 workers 17:56-21:37.

## Where things are
- Contact sheet: build/r72/sheet/index.html (every pair, OFF left, ON right, and the reviewer's pictures).
- Data: build/r72/check/final.json, table72.json/md, break.json, handover.json, nz-verdicts.json, audio/audio-verdicts.json,
  music-verdicts.json, verdicts62.json, verdicts65n.json, verdicts72x.json, n/m66/verdicts72m.json, chest/judge72.json,
  run_changes72.json, crash1/retry_plan.json, review/seen72.json, review/screen72.json.
