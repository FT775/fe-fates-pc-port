# The look sitting, done by the robot (F-037, round 41)

2026-11-18, about 19:45-20:35. The checks of docs/LOOK_SITTING.md and docs/collab/LOOK_SITTING_SHORT_GROK.md were
done by the test robot in **its own test game**, not the owner's. Nothing here counts as done until the owner says ok
(F-037).

**Where the mods went.** Each look was built and installed with its own tool into robot folders only:
`python tools/mods/look_<text|step4|portrait>.py install --mods-dir build/look_robot/mods_<x> --stage-dir
build/look_robot/stage_<x> --zakuro-dir build/look_robot/zak_<x>`. For each run that folder's `mods/` was copied into
the robot server's own data folder (`build/look_robot/server/<run>/data/mods/`), one look per run. The screen extras
used a cheat file inside the robot's own run folders only (`build/extras/robot/<session>/jobs/<run>/data/cheats/`).
Not touched: %APPDATA%\zakuro (no file there newer than 19:40 after the runs), the owner's saves, Zakuro settings,
cheat file, `mods/`, play/, build/oka, the shared capture library (only read), routes.json / markers.json (no edits:
the screens were reached with in-memory press lists, not new recorded routes). Real button presses only, no pokes.

**Tools.** `build/look_robot/drive.py` (boots boot-server on a copy of a recorded save, one look mod in its own data
folder, presses buttons, takes screenshots, prints the memory hash), `tools/extras/extras_robot.py compare` (the
screen extras). Screenshots and side-by-side pictures are under `build/look_robot/` and `build/extras/robot/`
(not tracked: they are game pictures).

**Saves used.** bt-ch25-clear (My Castle: X > Inventory, the army list and the unit status panel, Corrin and Jakob),
new-game-empty with bt-prologue's presses to Chapter 1, then A through the Chapter 1 opening talk (Jakob speaks at
frames 38880, 39000, 40080), bt-ch1-clear with bt-ch2's presses (a battle at frames 10392-11072), bt-ch5-clear with
bt-ch6-castle's presses (the castle armory's buy list).

## One line per check

| # | Check | Result | Evidence | In plain words |
|---|---|---|---|---|
| E1 | Smoother battles (60 fps) | **PASS** | build/extras/robot/lookrobot-extras-b/report.json, shots/fps60-from10300.png; side by side build/look_robot/cmp_extras.png | In the bt-ch2 battle the game moved 1.0 game frame per screen refresh instead of 0.5 (60 pictures a second instead of 30); the battle took 664 refreshes instead of 680; units, the game's random numbers and the save files were the same as without it. |
| E2 | Faster battles (150%) | **PASS** | same report, shots/battle_speed-from10300.png | The same battle took 608 refreshes instead of 680 (all three switches on: 572); units, random numbers and save files the same as without it. |
| E3 | Wider picture (16:9) | **PASS (picture shape only partly)** | same report, shots/wide-from10300.png; build/look_robot/cmp_extras.png | The battle is drawn with a wider view (more of the hall on both sides; people look narrower because the robot's picture stays 400 pixels wide, Zakuro's 16:9 window shape would widen it); battle length, units and random numbers unchanged. The 16:9 window setting itself is not part of the robot. |
| E4 | All three on together | **PASS** | same report, shots/all.png | Smoother and faster together, the battle 572 refreshes; the same game results. |
| E5 | Extras off = the original game | **PASS** | build/look_robot/shots/lr-x-nocheat/result.json and lr-x-cheatoff/result.json | bt-ch2 to frame 11120 with the extras file present but every switch off ("4 cheats, 0 of them on") gives the same memory hash as with no cheat file at all: 5d55fe7b086961db both. |
| E6 | Note: whole recorded route with an extra on from frame 0 | info | build/extras/robot/lookrobot-extras/report.json | Smoother and wider over the whole of bt-ch2: units, random numbers, save files the same as off. Faster battles over the whole route: the recorded presses are fixed to frame numbers, so once a fight ends sooner the later presses land at other moments and the replay goes a different way (random numbers first differ at frame 4800). This is the robot's press list falling out of step, most likely not a game change [med]; the one-battle check E2 is the fair one. Fast-forward (hold A) and pause were not pressed this time. |
| N1 | Name: army list shows Jacques | **PASS** | build/look_robot/cmp_castle_jakob.png (runs lr-castle-none / lr-castle-text, frame 5600) | My Castle, X > Inventory: the tile reads "Jacques" with the mod and "Jakob" without. |
| N2 | Name: status screen shows Jacques | **PASS** | same picture, frames 5600 and 5800 | The unit status panel under the list reads "Jacques" on both of its pages; class still Butler, stats the same. |
| N3 | Name: conversation shows Jacques | **PASS** | build/look_robot/cmp_ch1_jakob.png (lr-ch1open-none / -text, frames 38880, 40080) | Chapter 1 opening talk: the name above his lines reads "Jacques"; the lines and his face are unchanged. Memory at the castle frame: "Jacques" once, "Jakob" one time fewer than without the mod. |
| S1 | Stats line 1: Corrin HP +5 | **PASS (stopped by the class cap)** | build/look_robot/cmp_castle_corrin.png (lr-castle-none / -step4, frame 5300) | Corrin's HP went 39/39 -> 40/40, not 44: Nohr Prince's HP cap is 40 (the game's Job table: max HP 40; Corrin's cap bonus 0), so the +5 shows as +1. A save with Corrin further below the cap would show the full +5. |
| S2 | Stats line 2: Corrin Mov +2 | **PASS** | same picture | Mov 5 -> 7 (Nohr Prince). |
| S3 | Stats line 3: Bronze Sword Mt 4 -> 14 | **PASS** (round 44, 2026-11-19; owner ok 2026-11-19) | build/look_robot/cmp_bronze.png (runs b44-s3-none / b44-s3-step4, frames 38900 and 39000); result.json of each run under build/look_robot/shots/b44-s3-*/ | Chapter 1 map (new-game-empty with bt-prologue's presses up to frame 38810, then one tap on the Bronze Sword line of Corrin's bottom-screen panel at frame 38900; real presses, no poke). The item window reads "Mt 4" without the mod and "Mt 14" with it; Hit 100, Crit 0, Avo 0, Rng 1, Ddg 10 and the help line are the same. Memory: the Bronze Sword record (item 1, at 0x325ED8D0 in both runs) has might 4 (byte +0x1F = 0x04) without the mod and 14 (0x0E) with it; the other 39 bytes read are the same. |
| S4 | Stats line 4: Supportive shows Nobility's icon | **PASS** | build/look_robot/cmp_castle_corrin.png | Corrin's first skill icon changes from Supportive's picture to the red crown, the same picture as the skill next to it (Nobility). |
| S5 | Stats line 5: dishes give Luck +2 | **NOT RUN** | - | The robot did not cook in the dining hall (no recorded route reaches it). |
| F1 | Face: conversation shows Felicia's face | **PASS** | build/look_robot/cmp_ch1_jakob.png (lr-ch1open-portrait, frames 38880, 40080) | In the Chapter 1 opening talk the large picture next to "Jakob" is Felicia's face and clothes; name and lines unchanged; nothing garbled. |
| F2 | Face: talk window | **NOT RUN (partly seen)** | build/look_robot/cmp_castle_jakob.png, frame 5600 | No scene with Jakob in the small talk-window layout was reached. The small head-and-shoulders picture on his castle status panel does show Felicia, clean. |
| F3 | Face: status screen | **PASS** | same picture, frames 5600 and 5800 | Jakob's castle status panel shows Felicia's picture on both pages; nothing garbled, no odd colours or cut-off parts. |
| O1 | All looks off = the original game | **PASS** | build/look_robot/shots/lr-castle-off/result.json, lr-castle-none, lr-castle-none2; build/look_robot/uninstall_*.log, offlist.log | Each look was uninstalled from the robot's folders with `mods.py uninstall` (0 files left each, status "installed: nothing by this tool") and switched off with `mods.py disable` (list shows "no"). The same castle run with the emptied folders gives memory hash 4cee94f30f588c87, equal to two unmodded runs (4cee94f30f588c87 twice). With a look in, the hash differs (text 4ae11a7d..., stats ba68dce0..., face 9a74a67b...), so the check can tell. |

## The four owner-style lines

- **Extras:** smoother yes (60 pictures a second in battle, game results the same), faster yes (608 instead of 680,
  same results), wider yes (a wider view; Zakuro's 16:9 window shape not part of the robot), off = original yes
  (same memory). Odd: a recorded route replayed with faster battles from the start goes a different way, because
  its presses are fixed to frame numbers.
- **Name:** army list Jacques yes, status yes, conversation yes.
- **Stats:** 1 yes but capped (39 -> 40, Nohr Prince's cap is 40), 2 yes (5 -> 7), 3 yes (round 44: Mt 4 -> 14 in the
  Chapter 1 item window), 4 yes, 5 not tried.
- **Face:** conversation Felicia's face yes, talk window not reached (castle panel head picture yes), status screen
  yes, nothing garbled.

## Added at integrate (round 41 review)

- **The exact extras command (E1-E4).** The dense sample window is needed; without it the run samples only 42
  frames, the last battle is cut off and the check fails ("400 vs 400"). A reviewer reran it both ways
  (sessions lookrobot-review and lookrobot-review2) and got 680 -> 608 back only with the window:

      python tools/extras/extras_robot.py compare --route bt-ch2 --until 11110 --variant off         --variant fps60@10300 --variant battle_speed@10300 --variant wide@10300         --variant all=fps60,battle_speed,wide@10300 --window 10300:11110:4 --session <name> --check

- **The off check's folders (O1), written down exactly.** The install folders `build/look_robot/zak_<x>` are gone
  now; four empty folders remain, `build/look_robot/zak_off/mods` and `build/look_robot/zak_off_<text|step4|portrait>/mods`
  (all made 20:06). The uninstall logs say "uninstall OK" with the files removed, but not which folder they ran in.
  The off run lr-castle-off used an empty mods folder (mods_in_data []), so O1 compares "an empty mods folder" with
  "no mods folder". That is still a fair off check, but it does not by itself prove the uninstall step on an
  installed folder.

## Left for later (not done tonight)

- Stats line 3: done in round 44 (see below). Line 5 still needs a route that cooks in the dining hall.
- Face: a scene that shows Jakob in the small talk window.
- Extras: fast-forward and pause during a fast battle were not pressed this time (the 2026-11-12 robot check did).

## The owner's verdict (2026-11-19, ~18:00: "Yes, Grok's picks")

The owner answered the review list with Grok's picks (docs/collab/ROADMAP_NOW_GROK.md, "What to answer now"). The full
record is docs/OWNER_REVIEW_2026-11-19.md. Under F-037, OK means done for that line, and HOLD means still open.

| # | Check | Owner's verdict |
|---|---|---|
| E1 | Smoother battles (60 fps) | **OK**, as the robot measured it |
| E2 | Faster battles (150%) | **OK**, as the robot measured it |
| E3 | Wider picture (16:9) | **OK for the wider view only**. "Your window is 16:9" (Zakuro's window shape) is not ok'd, because the robot cannot see it |
| E4 | All three on together | **OK**, as the robot measured it |
| E5 | Extras off = the original game | **OK** |
| E6 | Note: whole recorded route with an extra on | info only, no verdict needed |
| N1 | Name: army list shows Jacques | **OK** |
| N2 | Name: status screen shows Jacques | **OK** |
| N3 | Name: conversation shows Jacques | **OK** |
| S1 | Stats line 1: Corrin HP +5 | **OK as "the cap held"**. The full +5 was not shown |
| S2 | Stats line 2: Corrin Mov +2 | **OK** |
| S3 | Stats line 3: Bronze Sword Mt 4 -> 14 | **OK** (owner, 2026-11-19: "it works, just don't add the mod"). The check counts; the test mod (LookStep4) is never installed in the owner's game or shipped |
| S4 | Stats line 4: Supportive shows Nobility's icon | **OK** |
| S5 | Stats line 5: dishes give Luck +2 | **HOLD**. Not run, so it stays open |
| F1 | Face: conversation shows Felicia's face | **OK** |
| F2 | Face: talk window | **HOLD**. Not run, so it stays open. The castle panel's head picture alone does not close it |
| F3 | Face: status screen | **OK** |
| O1 | All looks off = the original game | **OK** |

## Round 44 (2026-11-19, ~22:50-23:20): Stats line 3, the Bronze Sword

The owner said this should have been done already; it was done now, in the robot's own test game, under the same rules
as round 41. **PASS**, waiting for the owner's ok (F-037: nothing counts as done until then).

**Where the screen was.** No new save or poke was needed: Corrin carries a Bronze Sword in Chapter 1 (the Xander
training fight), and the recorded route bt-prologue (from new-game-empty) reaches that map. The run takes
bt-prologue's presses up to frame 38810 (the map, cursor on Corrin, Corrin's panel on the bottom screen), then adds one
tap on the Bronze Sword line of that panel at frame 38900 (bottom-screen point 180,120). The item window opens over
the panel and stays open. Real presses only; routes.json and markers.json were not edited (an in-memory press list,
as in round 41). Driver: `build/look_robot/bronze.py` (drive.py plus memory reads).

**Where the mod went.** `mods.py --mods-dir build/look_robot/mods_step4 --zakuro-dir build/look_robot/zak_step4
enable LookStep4`, then `python tools/mods/look_step4.py install --mods-dir build/look_robot/mods_step4 --stage-dir
build/look_robot/stage_step4 --zakuro-dir build/look_robot/zak_step4` (log build/look_robot/install_step4_r44.log:
10 cells, 2 files). The run copied that folder's `mods/` into its own server data folder
(build/look_robot/server/b44-s3-step4/data/mods/). Not touched: %APPDATA%\zakuro (nothing there newer than the
install), the owner's saves, Zakuro settings, cheat file, `mods/` (unchanged since 2026-11-10), play/.

| Run | Mod | Item window (frame 39000) | Bronze Sword record in memory (item 1, 0x325ED8D0, byte +0x1F) | Memory hash at frame 39000 |
|---|---|---|---|---|
| b44-s3-none | none | **Mt 4**, Hit 100, Crit 0, Avo 0, Rng 1, Ddg 10 | 4 | 663e192fd37fc59d... |
| b44-s3-none2 | none (repeat) | same | 4 | 663e192fd37fc59d... (same) |
| b44-s3-step4 | LookStep4 | **Mt 14**, the rest the same | 14 | 6e528ac9bdce7905... (differs, so the check can tell) |
| b44-s3-off | LookStep4 uninstalled and disabled | Mt 4 | 4 | 663e192fd37fc59d... (same as no mod) |

- **Pictures** (not tracked, game pictures): `build/look_robot/cmp_bronze.png` puts both runs side by side. Top row,
  frame 38900: Corrin's panel before the tap. Bottom row, frame 39000: the open item window, "Mt 4" on the left (no
  mod), "Mt 14" on the right (mod). Single shots: `build/look_robot/shots/b44-s3-none/f039000.png` and
  `build/look_robot/shots/b44-s3-step4/f039000.png`.
- **Off check, this time on an installed folder.** After the step4 run, `mods.py uninstall` and `mods.py disable`
  were run on the same robot folders (log build/look_robot/uninstall_step4_r44.log: both files removed, 0 files
  left). The off run copied the emptied folder and gave the same full memory hash as two runs with no mod
  (663e192fd37fc59dd8ee5074453f3b68a16fdc425e5ca9d4a38c7e748312449c, three times). This closes the gap noted for O1
  above (the uninstall step itself is now covered).
- **Seen in passing, same screen (info, not new checks):** with the mod, Corrin's HP on the panel reads 27/27
  instead of 22/22, the full +5 of stats line 1 (Corrin is far below the Nohr Prince HP cap at level 1, unlike the
  Chapter 25 save of S1), and the first skill icon is the red crown (stats line 4).
- **One small difference, said plainly:** in the mod run the "2. Moving Units" tutorial label at the top-screen
  corner was already gone at frame 38900 and the map cursor read one tile to the left (6,11 instead of 7,11) while the
  cursor box drawn on Corrin is in the same place in both pictures. The same presses reached the same screen; this
  looks like a loading-time difference from the larger modded data file [med], and it does not touch the off check
  (the off run matches the unmodded runs byte for byte).
- **Reading note on b44-s3-off's result.json:** it is labelled mod "step4" (the folder it copied) but its
  mods_in_data list is empty, because that folder had just been emptied by the uninstall. Its item list is also
  empty (no cursor reads were saved for this run). The memory hash and the frame-39000 picture (Mt 4) are what the
  off check rests on.
- **Not done:** a read of Corrin's own item slots. The robot's board read finds no units on this map (it returned
  an empty list on the prologue and Chapter 1 maps), so the slot read was skipped; the item window and the record
  read above show the same item. Stats line 5 (the dining hall) is still not run.

