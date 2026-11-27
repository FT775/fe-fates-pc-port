# Your review page: rounds 59 to 68

**Read this in about 20 minutes; mark only what is wrong; silence means ok (F-037 / F-051(4)).**

To mark something, write "wrong:" and a few words in chat, with the round number (for example "r62 call B wrong: I want
fast forward on Tab"). Anything you do not mark counts as ok, and each small call keeps its written default pick.

Made in round 69 from the round reports and the pictures that already exist. No new game runs were made for this page.
Every claim here comes from a report; the report is named in each section.

## The program this page is about
- Installed game: `play/game/Fire Emblem Fates.exe` sha **b4a887b2** (the round-62b build, with engine patches 0001-0030).
  Robot server: boot-server **1b8b2593**. Capture library: **405f2bac** (rebuilt with your OK on 2026-11-24).
- Rounds 63 to 68 built no engine parts. They changed the randomizer tools, the robot and the release tools only.

## How to see the randomizer yourself
1. Start `PLAY.bat` (or `PLAY RANDOMIZED.bat`; for Seal of Flames, `PLAY SEAL OF FLAMES.bat`).
2. New Game, pick the difficulty, then Casual or Classic. The **Randomizer** page opens over the game.
3. Set the rows (or press **Randomize everything**), then press **Start game**.
4. Later in the run, Esc shows the run's settings.

## The pictures (3 contact sheets, made from existing pictures only)
Each tile is OFF on the left and ON on the right, unless it says otherwise. Green label = a person looked (SEEN);
orange = not looked at, or a drawn page.
- **Sheet 1**, rounds 59-61 (9 tiles): [build/r69/review/sheet1_r59_r61.png](../build/r69/review/sheet1_r59_r61.png)
- **Sheet 2**, rounds 62 and 62b (12 tiles): [build/r69/review/sheet2_r62_r62b.png](../build/r69/review/sheet2_r62_r62b.png)
- **Sheet 3**, rounds 63-66 (11 tiles): [build/r69/review/sheet3_r63_r66.png](../build/r69/review/sheet3_r63_r66.png)
- Tile list with source paths: build/r69/review/tiles.json. Remake the sheets with
  `python build/r69/review/make_sheets.py`.
- The full per-round sheets still open: build/r59/sheet/index.html, build/r62/sheet/index.html,
  build/r65/sheet/index.html. **The round-60 and round-61 sheets lost their pictures** in cleanup wave 1
  (2026-11-23, build/CLEANUP_PLAN_2026-11-22.md). Round 61 has no pictures left at all.

Pictures are kept under build/ only. They are never committed or shared.

---

## Round 59: the character shuffle, music, recolour, fast start (REPORT_2027-01-02)
- **What changed for you:**
  - The character shuffle, "keep the face" look: a join spot keeps its face and name, but plays as someone else
    (that person's class, stats, growths and skills). On all 4 paths, Seal of Flames included.
  - Random music, Enemy levels up and Tougher bosses rows became live on the page.
  - Recolour: a swapped unit's battle-model hair takes the new person's colour. It is always on with the shuffle.
  - The page makes your game in the background, so Start game is usually quick.
  - Seal of Flames battle saves now reload the right chapter (38 of 41 Seal chapters then; round 60 fixed the rest).
- **How to see it:** Birthright chapter 4, Rinkah's join. Turn on the shuffle.
- **Evidence:** sheet 1, tiles 1-3 (Rinkah, Felicia, Silas). Break check: Fates all pass; Seal 38/41 then.
- **Open for you:** nothing new. The recolour is faint (see the call list, item G).

## Round 60: Seal reload fixed, Nuzlocke built, every setting looked at again (REPORT_2027-01-03)
- **What changed for you:**
  - Seal of Flames: R021, R023 and Y004 now reload the right people. R013 and R023 now get the randomizer too.
    Every Seal chapter passes (41/41).
  - Starting items now reach the route-variant joins (for example Revelation's Elise).
  - The Nuzlocke row is live (Birthright still failed this round; round 61 fixed it).
- **How to see it:** Revelation chapter 14, Elise's items (sheet 1, tile 9).
- **Evidence:** sheet 1, tiles 4-9. Table: 56 SEEN, 41 robot, 10 mem, 9 FAIL (build/r60/integrate/table_reviewed.json).
- **Open for you:** your 4 calls from this round were answered in F-049.

## Round 61: Nuzlocke on Birthright, the real page drives itself, music by sound (REPORT_2027-01-04)
- **What changed for you:**
  - Nuzlocke works on every path: a fallen unit stays fallen after a save, a state load and a restart. Casual becomes
    Classic. The graveyard shows the name and turn ("Kaze: A007, turn 14").
  - A new Nuzlocke game can be started from the New Game mode pick.
  - Skill changes now reach the route-variant joins. Turning on boss classes no longer changes every other enemy.
- **How to see it:** turn on Nuzlocke on the page, lose a unit, then save and load.
- **Evidence:** text only. The pictures were removed in cleanup wave 1. The table is in
  build/r61/integrate/table_reviewed.json (66 SEEN, 43 robot, 6 mem, 1 FAIL); the build shas are in
  build/r61/FINAL_SHA.txt. Music was proven by recorded sound (similarity 0.43-0.50, under 0.8 counts as different).
  Nobody listened.
- **Open for you:** the faint Seal recolour (item G). Its zoomed picture is gone.

## Round F48: the game file and Seal of Flames moved into roms/ (REPORT_2027-01-05)
- **What changed for you:** your game file is now in `roms/`, and Seal of Flames in `roms/seal/`. They were renamed in
  place, not copied, and every hash was checked (build/f48/move.json). The old root places still work for one release.
- **How to see it:** `PLAY.bat --check` says where it found the game.
- **Evidence:** text only (no pictures). The undo is `python build/f48/move_files.py back`.
- **Open for you:** nothing. If you like, clear the "rom" line in play/config.json to stop its one-line note.

## Round 62: growth floor, growth view, weapon ladder, boss classes and boss boost, camera fix (REPORT_2027-01-06)
- **What changed for you:**
  - Every randomized total growth is 20-100%, also stats that were 0.
  - **Growth view:** on the map's unit panel, Select, Tab, pad Back or the Growths button switches stats to growth %
    and back. It also works with the randomizer off.
  - Stronger enemy weapons go one step up by Difficulty (Easy +1 forge, Normal the next tier, Hard the next tier +1).
  - Bosses, story bosses included, can change into a class of the same tier.
  - Tougher bosses: HP up by Difficulty. The weapon part was too weak (round 63 fixed it).
  - The in-game randomizer no longer reads the camera-angle option to tell a new game from a loaded one.
- **How to see it:** Birthright, Kaze's unit panel with its Growths box (sheet 2, tile 1). Any map: press Select on
  the unit panel (tile 2).
- **Evidence:** sheet 2, tiles 1-7. Break check 536/536. Table: 23 SEEN, 112 robot, 6 mem, 11 FAIL.
- **Open for you:** calls A-E in the list below.

## Round 62b: the randomizer page cleanup (REPORT_2027-01-07)
- **What changed for you:**
  - The page has section headers (Basics, Characters, Classes, Growths and stats, Items and shops, Enemies and
    bosses, Extras), short labels, plain choices and one help sentence per row in a help line.
  - The Seal page has no Children row at all.
  - New: a Spoiler log switch and a **Randomize everything** button. The button never turns on Nuzlocke, Children or
    the full swap, and it keeps your seed.
  - Old seeds give the same game.
- **How to see it:** open the page (New Game, then Casual or Classic). Point at Difficulty to see its help line.
- **Evidence:** sheet 2, tiles 8-12. These are the real page code drawn without a window, not game screenshots.
  The page robot passed on Fates and Seal (build/r62b/pagebot/).
- **Open for you:** nothing new. The long help text after Randomize everything fits in round 71 (engine round).

## Round 63: boss weapon might fixed, 24 story bosses run (REPORT_2027-01-08)
- **What changed for you:** Tougher bosses now shows +1 / +2 / +3 weapon might on Easy / Normal / Hard. Before,
  the screen showed only +1 / +1 / +2.
- **How to see it:** Birthright chapter 14, Daniela's Ragnarok (sheet 3, tiles 1-3).
- **Evidence:** sheet 3, tiles 1-4. 13 of the 24 bosses were killed in their new class, and the scenes after played.
  The other 11 could not be reached, the same with the randomizer off. Smoke 8/8.
- **Open for you:** nothing new.

## Round 64: the last story bosses, the Seal boss list, Conquest recolour, the drop flag (REPORT_2027-01-09)
- **What changed for you:**
  - Seal of Flames has its own boss list: a Seal story boss changes class only after a Seal battle proved it
    (5 bosses then).
  - The "drops" rule is proven, so a dropped weapon is never forged.
- **How to see it:** Conquest chapter 10, Effie's hair in battle (sheet 3, tile 7).
- **Evidence:** sheet 3, tiles 5-8. 10 of the 11 bosses were killed in their new class with a placement cheat in the
  robot's own test game. Seal R006 boss might +3 shows on the full unit page.
- **Open for you:** nothing new.

## Round 65: the full check (REPORT_2027-01-10)
- **What changed for you:** nothing in the game. This was the big check of every chapter with everything on.
- **Evidence:**
  - Break check 536/536 on 4 paths, HANDOVER 12/12, Nuzlocke on every path, the page robot, music by sound.
  - Arthur (Conquest 23) killed as a Paladin: sheet 3, tile 9. These are robot pictures; the report calls it a robot
    result.
  - Seal story bosses: sheet 3, tile 10.
  - Table: 72 SEEN, 70 robot, 6 mem, 3 gap, 0 FAIL, 1 n/a (docs/tests/CHECK_R65.md).
- **Open for you:** nothing new. The Start-game wait after a late row change was 5.1 s on Fates and 6.3 s on Seal.
  You decided in F-049 that it stays, with the "Making your game..." text.

## Round 66: Revelation boss might, 9 more Seal bosses (REPORT_2027-01-11)
- **What changed for you:**
  - Revelation's tougher-boss might shows: C007 Vallite's Steel Axe +1 / +2 / +3.
  - 9 more Seal story bosses may change class (14 in all).
- **How to see it:** Revelation chapter 7, Vallite (sheet 3, tile 11).
- **Evidence:** sheet 3, tile 11. The judge's "at the cap" check is now real, and all old passes still hold.
  The table is now 75 SEEN, 70 robot, 6 mem, 0 gap, 0 FAIL, 1 n/a (CHECK_R65.md addendum).
- **Open for you:** call H.

## Round 67: faster tests, the CORE test, smoke (REPORT_2027-01-12)
- **What changed for you:** nothing in the game. The tests are split into CORE (under 5 minutes, smoke included) and
  FULL (everything). No test was deleted. Seed checksums catch any change a round did not announce.
- **Evidence:** text only. Smoke 8/8, the same hashes as round 66 (build/r67/smoke/run2).
- **Open for you:** call I.

## Round 68: the one-command release (REPORT_2027-01-13)
- **What changed for you:**
  - Double-click `RELEASE.bat` to make a release. It checks, tests, packs and tags. It never pushes; only you do.
  - Since then (with your OK): the capture library was rebuilt, LICENSE was added, release r68 was made, and it was
    uploaded to the private dev repo and a public snapshot.
  - **PLAY now stops if the game exe does not match its build record.** `PLAY.bat --anyway` gets past it.
- **How to see it:** `PLAY.bat --check`.
- **Evidence:** text only. The rehearsal record is in build/release/.
- **Open for you:** call F. The full check that was due at round 68 is planned for round 72 (docs/ROADMAP.md).

---

## Small calls with their default pick (silence means the default)
| # | Round | Call | Default pick (what is built now) | Look at |
|---|---|---|---|---|
| A | 62 | On **Hard**, a weapon with no next tier gets **+2 forges** | Keep: +2 forges | weapons.py ladder rule; no sheet tile: the SEEN pair is Conquest Hard, Throwing Club +2 (build/r62/integrate/seen_reviewer.json, 'cq hard') |
| B | 62 | On **Normal**, a weapon with no next tier (or forge-only) gets **+1 forge** | Keep: +1 forge | sheet 2, tile 3 (Throwing Club +1) |
| C | 62 | **Birthright's Nohrian bosses** who join you in Conquest: give them the tougher-bosses boost on Birthright? | No: as you wrote in F-049, only Conquest's chapter-only bosses get it (rules.json `army_boss_boost_routes` = Conquest) | none |
| D | 62 | An avatar growth can show **under 20%** because of the bane (the game adds boon and bane after the floor) | Keep: allowed, the bane is your choice | no sheet tile: REPORT_2027-01-06 (Corrin's Lck shows 30 where the table says 50) |
| E | 62 | **Tab** switches the growth view instead of fast forward while the unit panel is up; the digits are small (5x7) | Keep both | sheet 2, tile 2 |
| F | 68 | **PLAY stops** when the exe does not match its build record (`--anyway` gets past) | Keep the check | `PLAY.bat --check` |
| G | 61 | The Seal (and Fates) **recolour is faint** | Round 71 makes the hair colour easier to see (hair only) and gives Recolour its own row; the stronger colour is shown next to the old one on that round's review page (docs/ROADMAP.md, call 5) | sheet 1, tiles 3-5 |
| H | 66 | 3 Seal bosses passed under a **looser rule** (Arthur and Effie A023, Selena A013: small differences after the kill) | Keep them on the Seal list | docs/rando/SEAL_BOSSES.md |
| I | 67 | The **smoke baseline** (marked NEW) becomes the yardstick | Accept it | config/harness/smoke_baseline.json |

**Already settled, not asked again (F-051(4)):** the Start-game wait after a late row change (F-049: it stays, with
"Making your game..."); story bosses keep changing (F-049 "Keep them changing"); Seal Children removed (F-049);
spoiler files (F-050 addendum); the licence and the first push (done 2026-11-24 with your OK).

**Your general ok:** rounds 59-68 as a whole (F-037). Silence means ok.

---

## Index: SEEN vs robot-only pictures
SEEN = a person opened the pair and saw the change. robot-only = the robot's strict pair passed, but nobody looked.
- **SEEN (25 tiles):** sheet 1 tiles 1-9; sheet 2 tiles 1-7; sheet 3 tiles 1-3, 5-8, 10-11.
- **Not SEEN (2 tiles):** sheet 3 tile 4 (Seal might, the page shows no Atk; tile 5 is the SEEN replacement);
  sheet 3 tile 9 (Arthur, robot pictures).
- **Drawn page, not a game screen (5 tiles):** sheet 2 tiles 8-12.
- **Settings now (152 cells, after round 66):** 75 SEEN, 70 robot-only, 6 memory-only, 0 FAIL, 1 n/a.
  - Memory-only: castle rewards on all 4 paths, and shops on Revelation and Seal (no recorded route reaches them;
    round 72 plans robot cheat pokes for them).
  - Music is proven by recorded sound only. Nobody has listened.
