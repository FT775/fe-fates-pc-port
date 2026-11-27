# Conquest and Revelation on the robot (round 8, area "split")

**In plain words.** The robot had only played Birthright. This round it went back to the last save before the
route choice (the chapter-5 save of the Birthright chain, which is still neutral), picked Conquest once and
Revelation once, and cleared **chapter 6 on both**. Each clear is a route that replays from that save to the same
game memory, byte for byte, ends in the game's own save, and is packed as the next start save
(`cq-ch6-clear`, `rv-ch6-clear`). Chapter 7 was started on both routes but **not cleared** (section 4).
Tags: **[high]** seen in a run or checked by a script, **[med]** strong indirect evidence, **[low]** a guess.
Owner decision F-022 (2026-11-13, "run all three routes in round 8") is what allowed this.

## 1. The split [high]

- `bt-ch5-clear.zip` is before the choice: route `bt-ch6-castle` starts from it and meets the branch dialog at
  frame 11714. Its route byte (GameUserData+0x2E) is 0 there, but no route has been chosen yet (docs/ROUTES.md:
  the chapter-6 script calls RouteSet after the dialog). So both chains start from it, with the same "continue"
  prefix as the bt routes and the same three START presses (4596, 4685, 4774).
- The branch dialog lists three items; Birthright is the first. Conquest = DOWN, A; Revelation = DOWN, DOWN, A;
  then LEFT, A on the confirmation (the same as Birthright).
- Proof that the branch took (marker reads of the replays, run.json `state`):

| Route | First player phase | Route byte | Units (player, enemy, other) | Cast loaded |
|---|---|---|---|---|
| `cq-ch6` | 13055 | **1** (Conquest) | 6, 5, 0 | units with `PID_B006_*` person ids (the B006 dispos file) |
| `rv-ch6` | 12959 | **2** (Revelation) | 3, 14, 0 | units with `PID_C006_*` person ids (the C006 dispos file) |

  The person ids were read from the board dump of the look-ahead (tools/harness/robot/units.py), not tracked.
  No chapter-id read exists in markers.py; the route byte plus the B006 / C006 cast is the evidence that
  chapter B006 / C006 is the one loaded. (A chapter-id read would need a markers.py change: open issue.)

## 2. Routes cleared

| Route | Start save | Frames | What happens | Packs |
|---|---|---|---|---|
| `rv-ch6` | bt-ch5-clear | 27,740 | Revelation chapter 6. Turn 1: Corrin hits a wyvern rider, Felicia hits it, Azura Sings to Corrin, Corrin finishes it. Enemy phase: Azura retreats (Casual). Turn 2: Corrin beats the dragon-knight boss; Felicia waits. The chapter ends by its own event after that enemy phase (the scene where the ground gives way); save slot 1; My Castle | `rv-ch6-clear` |
| `cq-ch6` | bt-ch5-clear | 37,790 | Conquest chapter 6. Win rule read from the script: at most 1 enemy left (`EnemyNumberLessThanOrEqualTo`, argument 1: the byte pushed before the call in Scripts/B006.cmb). Turn 1 Leo hits the Hinoka/Takumi pair. Enemy phase: the pair beats Felicia. Turn 2 Corrin and Leo beat Takumi, Camilla beats Hinoka. Xander stays in the north with Ryoma (Ryoma is never fought on purpose; Xander falls on turn 4). Turns 3-4 the army crosses the south bridge, Leo draws Yukimura. Turn 5 Camilla beats Sakura, Elise heals Leo, Leo hits Yukimura. Turn 6 Corrin beats Yukimura: stage complete with Ryoma alone left; save slot 1; My Castle | `cq-ch6-clear` |

Checks (sessions in build/parallel/, all `parallel.py`, FEF_ROBOT_JOBS within this area's share of 6):

| Check | rv-ch6 | cq-ch6 |
|---|---|---|
| Two replays side by side (`runs --copies 2 --markers --keep`) | sp-rv6a: both **memory `6f54e4cd...`** | sp-cq6b: both **memory `73534534...`** |
| Marker run with the new checkpoints | sp-rv6mk: **checkpoints all met**, memory `6f54e4cd...` | sp-cq6mk: **checkpoints all met**, memory `73534534...` |
| Capture run (`--mode capture`, the capture library as it stood) | sp-rv6cap: 75 functions met, 1320 records, 1266 match, 23 gave up, 31 incomplete, **0 bad of any kind**, PASS, memory `6f54e4cd...` | sp-cq6cap: 73 functions, 1312 records, 1269 match, 25 gave up, 18 incomplete, **0 bad of any kind**, PASS, memory `73534534...` |
| Clear marker | 27362 `ChapterFileMenu` (route 2), 27600 the castle | 37000 `map__SequenceCompleteEffect...` with units [3, 1, 0], 37397 `ChapterFileMenu`, 37650 the castle |
| Packed save | `parallel.py pack sp-rv6a sp-rv6a-1 rv-ch6-clear` | `parallel.py pack sp-cq6b sp-cq6b-1 cq-ch6-clear` |

Every run printed "%APPDATA% (zakuro, 3dsrecomp) unchanged". The capture-mode memory hash equals the original
runs' in both routes. The capture library was not rebuilt here (integrate rebuilds it); the writer totals line
said "NOT REPORTED (library built before the writer totals)".

**Never-met readers: none met.** `script_unit_can_dragon_vein`, `script_unit_has_skill`,
`unit_attack_for_terrain`, `unit_attack_for_terrain_of_slot`, `family_grow`, `family_limit`, `family_parent_grow`,
`unit_equipped_skill_count`, `skill_total`, `ai_value_is_signal`: 0 rows in either summary.tsv. Every function
met by the two captures was already met by an earlier summary on disk (80 summaries, 104 functions). Expected:
the dragon-vein script command is in Revelation chapters 12, 18, 20, 25 (docs/ROBOT.md 3b), the skill script
command in Conquest 28.

## 3. What the chapters taught (for the next look-ahead)

- **Ryoma (Conquest 6) is a wall**: hit 88-100 %, the royals' hit on him 19-55 %; Xander, Camilla and Leo each
  lost to him in look-aheads. Leave him; win on the other four (Grok's notes say the same). Felicia has a Heal
  staff, Elise has Heal and Freeze.
- **The Hinoka/Takumi pair blocks the first attack after it has fought** (Guard Stance gauge): a 97 % hit was
  blocked. Spend a weak attack first, or let them come to the group.
- **Corrin at risk**: the pair took Corrin from 27 to 1 in one enemy phase. Keep Corrin out of a flier's 8 tiles.
- Revelation 6 ends by its own event after the second enemy phase; killing one boss was enough to get there in
  this line (the script has DestroyBoss and LimitTurn).
- A battle's random numbers depend on what fought before it; a re-tried attack in the same position gives the
  same result, so change the order, not the button.

## 4. Chapter 7 (started, not cleared)

| Chain (build/harness/robot/states/split/) | Where it stands | What it needs |
|---|---|---|
| `cq7b` (from `cq-ch6-clear`, frame 17268) | Conquest chapter 7, turn 1 player phase. Castle: the forced build tutorial placed the first building 8 tiles below its default spot (the first blue spot); Next Battle; preparations > Fight! (2 units: Corrin, Felicia) | Rout 14 Faceless (one boss) with Corrin and Felicia; four helpers join on turns 3-4 (Grok). Long |
| `rv7n` (from `rv-ch6-clear`, frame 22305) | Revelation chapter 7, turn 3 player phase. Castle: build tutorial placed 13 tiles below the default spot; Next Battle; Fight! (3 units) | Seize at (17,3) on a dark map: each room opens when a unit reaches its exit, a dead end warps the unit back (seen at (16,18)); (14,21) opened the next room (3 enemies). A thief is left at 5 HP |

The `.inputs` file of each chain is the stitched input; `split.py input CHAIN` prints it. The chain states start
from the packed save with the continue prefix, so the replay of a finished chapter is that input, cut at the save.

## 5. Tools (tools/harness/robot/, new files only)

- `split.py`: the look-ahead commands of this area (`base`, `fork`, `press`, `auto`, `look`, `act`, `endturn`,
  `input`). It reuses auto.py and act.py unchanged, with its own state folder (`states/split/`), run names equal to
  the chain names, and a pool of `SPLIT_SLOTS` (default 2) OS-held locks instead of the one shared
  `probe.lock`, so it does not queue behind the Birthright agent's look-aheads; its slots count inside this
  area's FEF_ROBOT_JOBS. A failed `act` puts the chain back as it was before the action.
- `splitmk.py SESSION [RUN]`: prints the marker reads of a parallel.py session (screen, route byte, units).
- `splitcfg.py route|marks NAME FILE`: read-modify-write of one `bt-*` / `cq-*` / `rv-*` / `opt-*` key in
  routes.json or markers.json (round 13: bt- and opt- too, so no helper hand-edits routes.json); it refuses other
  names (title, new-game, cheat-*, anything but letters, digits, - _ .) and checks that every other key is unchanged.

## 6. Time

About 2.8 minutes per replay of a chapter-6 route (boot.exe 125-207 s), 1-2 minutes per look-ahead action
(select, move, forecast, confirm, settle). Conquest 6 took four restarts of its look-ahead before the line above.

## 7. Revelation, round 8 area "rv": chapters 7 and 8 cleared

**In plain words.** The robot went on with Revelation from the chapter-6 save. It cleared **chapter 7** (the dark
maze, seize the throne, 25 turns) and **chapter 8** (the castle with Yukimura, defeat the boss, 20 turns) without
losing a unit. Both are routes that replay to the same game memory twice, end in the game's own save, and are packed
(`rv-ch7-clear`, `rv-ch8-clear`). Chapter 9 is reached (turn 1 player phase, all 9 units) but not played.
Tags as above.

### 7.1 Routes [high]

| Route | Start save | Frames | What happens | Packs |
|---|---|---|---|---|
| `rv-ch7` | rv-ch6-clear | 104,300 | The split agent's chain `rv7n` (castle build tutorial, Fight with Corrin, Azura, Felicia, up to turn 3), then: each dark room opens when a unit reaches its exit tile, and its enemies appear at that moment. Rooms are fought one at a time at their one-tile entrance: the corridor west of the first room, then the west column, then the north-west room; Gunter joins at (7,1) when the top corridor opens and beats the oni that comes out of the boss room; Corrin (with Azura's song) beats the samurai, the archer and the Berserker boss; Corrin seizes (17,3) on turn 25 (the Stage Complete screen waits for A); save slot 1; My Castle | `rv-ch7-clear` |
| `rv-ch8` | rv-ch6-clear (see 7.3) | 182,200 | The whole `rv-ch7` input, then chapter 8: castle > Next Battle > Chapter 8; preparations Equip Skills > Corrin > back; Fight (Corrin, Azura, Felicia, Gunter). Turns 1-3 the Oni Savage, two Spear Fighters and two Sky Knights that charge are beaten at the start funnel; turns 4-13 up the west side (ninjas, samurai, archers); turns 14-15 Saizo is drawn out of the boss room onto row 7 and beaten; turn 16 Corrin beats Orochi; turns 19-20 Corrin's Dragonstone and Felicia's dagger beat Yukimura (the win: 5 other enemies are still on the map); save slot 1; My Castle | `rv-ch8-clear` |

Checks (sessions in build/parallel/, `parallel.py`, FEF_ROBOT_JOBS=3, FEF_ROBOT_MEM_GB=2, below-normal):

| Check | rv-ch7 | rv-ch8 |
|---|---|---|
| Two replays (`runs --copies 2 --markers --keep`) | rv-ch7a: both **memory `9495b353...`** | rv-ch8b: both **memory `410aa12a...`** |
| Capture run with the new checkpoints (`--mode capture --markers`; the capture library as it stood, not rebuilt) | rv-ch7cap: **checkpoints all met**, 78 functions met, 1538 records, 1503 match, 25 gave up, 10 incomplete, **0 bad of any kind**, PASS, memory `9495b353...` (equal to the original runs) | rv-ch8cap2: **checkpoints all met**, 99 functions met, 2140 records, 2094 match, 32 gave up, 14 incomplete, **0 bad of any kind**, PASS, memory `410aa12a...` (equal); the capture library had been rebuilt by then (the writer totals line: "no writer stored anything", stores 0). A first try (rv-ch8cap) stopped at parallel.py's default 900 s timeout (FAIL with 0 bad records, 6 checkpoints not reached): this route needs `--timeout 2700` in capture mode |
| Clear markers | 94099 the seize dialog with 0 enemies, 103090 `map__SequenceCompleteEffect...`, 103512 `ChapterFileMenu`, 104250 the castle | 180600 Stage Complete with units [4, 5, 0], 181278 `ChapterFileMenu`, 182150 the castle |
| Packed save | `parallel.py pack rv-ch7a rv-ch7a-1 rv-ch7-clear` | `parallel.py pack rv-ch8b rv-ch8b-1 rv-ch8-clear` |

Every run printed "%APPDATA% (zakuro, 3dsrecomp) unchanged". The writer totals line said "NOT REPORTED (library built
before the writer totals)". Checkpoints: config/harness/markers.json `rv-ch7` (8 frames) and `rv-ch8` (9 frames),
written with splitcfg.py; both routes are `verified: true`.

**Never-met readers.** `unit_equipped_skill_count` is **met in real play** for the first time (rv-ch8cap2: 12 records, 12 match; chapter 8's preparations Equip Skills > Corrin; before, only the cheat route met it). Still 0 rows in both summaries: `script_unit_can_dragon_vein`, `script_unit_has_skill`, `unit_attack_for_terrain` and `..._of_slot`, `family_grow`, `family_limit`, `family_parent_grow`, `skill_total`, `ai_value_is_signal`, `unit_lethality_immune`. Every other function the two captures met was already in an earlier summary on disk (151 summaries).

### 7.2 What the chapters taught [high unless tagged]

- **Chapter 7 terrain**: the darkness tile types (one per terrain under them) have move cost column 0 (no unit can enter)
  and change into the plain / fort / chest under them when their room opens. units.py `-m` prints the original grid
  (map info + 0x808); **the grid the game moves on is at map info + 0x408** (opened rooms show as plain there).
  The rooms' enemies are the Dispos groups `Reinforce03`..`09` of C007 (3-5 each); Gunter is `Support02` at (7,1).
- Dead ends: corridor tips such as (16,18) by the start, (6,18) and (5,15) [med: only (16,18) was seen to warp, by the
  split agent]; the route never steps on one. Only the west side was opened; the middle rooms (Reinforce04-06) stayed shut.
- An enemy that drops a Chest Key into a full inventory stops the game on "You cannot carry any more"
  (`ItemMenuSend`): DOWN x5, A sends the new key to the convoy, then LEFT A for Yes. Twice in chapter 7.
- The chapter-7 Berserker and Yukimura do not move. **Yukimura's Steel Dagger beats Corrin's Yato** (poor weapon
  compatibility: 77 % hit, two misses in two tries); X in the forecast switches to the Dragonstone (83 %, 10 damage,
  takes 7). Archers and mages hit over the one-tile walls of the chapter-8 castle (range 2): keep weak units 3 tiles
  from a wall pocket with an archer in it (Azura went to 3 HP that way in a look-ahead; that turn was redone).
- Azura's Sing takes the first adjacent unit. Felicia's command menu starts with Attack when an enemy is in dagger
  range (1-2), so "move next to Corrin, A, A, A" attacks instead of healing (it happened once in rv-ch8: she hit
  Yukimura and lived at 6 HP). The heal target list starts with one adjacent unit; RIGHT moves to the next.
- Azura was knocked out once in a look-ahead (Casual: she retreats) after singing inside Yukimura's bow range; that
  line was thrown away and replayed without the song. No unit is lost in either route.

### 7.3 Why `rv-ch8` starts at rv-ch6-clear [high for the facts, med for the cause]

Chapter 8 was played on from the chapter-7 chain (continuous play). Replaying only chapter 8 from `rv-ch7-clear`
(title, continue, castle, the same battle inputs shifted by -102,171 frames) gave a turn-1 board equal to the chain's
(units, positions, HP), but the run had **diverged by turn 13** (session rv-ch8a: two units paired up that never were
in the chain; the two copies agreed with each other, memory `a56adf53...`). Likely cause [med]: castle and map menu
visits move the general random at 0x00752B7C (docs/ROBOT.md 3d), and the reload took another menu path (the loaded
save opens the castle's preparations menu, which was backed out of with B). So `rv-ch8` is the chain's own input from
rv-ch6-clear (both chapters, about 13.5 minutes per replay), which is deterministic. A chapter-9 route can start from
`rv-ch8-clear` only with a look-ahead made from that save.

### 7.4 Chapter 9 (reached, not played)

Chain `rv9s` in build/harness/robot/states/split-rv/ (from `rv8done` = the end of `rv-ch8`; the chain's start save
is rv-ch6-clear): castle > Next Battle > Chapter 9 > Yes; preparations (all 8 units preselected; Rinkah forced) >
Fight; frame 183,731, turn 1 player phase. 9 player units (Corrin lv 14 with the Dragonstone equipped, Azura, Felicia,
Gunter, Sakura, Hana, Subaki, Kaze, Rinkah), 26 enemies, the boss (35 HP) at (21,3). It needs a long
look-ahead (winds; reinforcements from turn 5 per Grok's notes). For a route that starts at `rv-ch8-clear`, start a
new chain with `splitrv.py base CHAIN rv-ch8-clear ...` (7.3).

### 7.5 Tools and files

- `tools/harness/robot/splitrv.py` (new): split.py with this area's own state folder
  `build/harness/robot/states/split-rv/` (savestates, chain inputs, slot locks); split.py itself unchanged.
- Scratch helpers (not tracked): a map renderer that reads map info + 0x408, and button macros: heal (move, A Staff,
  A Heal, A target), sing (move, A Sing, target, A), atkx (forecast, X for the second weapon, A).
- In build/harness/robot/states/split-rv/: `rv-ch7.route.json`, `rv-ch8.route.json`, `*.marks.json`, `par_*.txt`
  (session outputs), chains `rv7done` (end of chapter 7), `rv8done` (end of chapter 8), `rv9s` (chapter 9 turn 1),
  per-turn forks `rv8t*`.

### 7.6 Time

Chapter 7 from turn 3: about 90 look-ahead actions; chapter 8: about 110 (two redone turns: Azura shot by an archer in
a wall pocket at turn 8, and the Yukimura fight). A replay of rv-ch7 takes 4.5-10 minutes (boot.exe 270-610 s; runs
went one at a time under the 2 GB budget); rv-ch8 about 13.5 minutes (two side by side, 800 s each).

## 8. Conquest, round 8 area "cq": chapter 7 cleared, chapter 8 started

**In plain words.** The Conquest chain went on from `cq-ch6-clear`. **Chapter 7 is cleared** with no unit lost: it
replays from that save to the same game memory twice, meets every checkpoint, ends in the game's own save, and is
packed as `cq-ch7-clear`; a capture run of it found no bad record. **Chapter 8 was started and not cleared**: the
robot reached turn 21 with the whole army alive, but the boss is still across the map (section 8.3).

### 8.1 Route cleared [high]

| Route | Start save | Frames | What happens | Packs |
|---|---|---|---|---|
| `cq-ch7` | cq-ch6-clear | 81,100 | Castle build tutorial and Next Battle (the `cq7b` prefix of section 4), Fight! with Corrin and Felicia. Win rule: rout (14 Faceless, the boss a level-8 Faceless). Turn 1 Corrin holds the east end of the bridge; two Faceless cross and hit Felicia (19 -> 3). Turn 2 Corrin and Silas kill them, Elise heals Felicia (Silas and Elise join on turn 2, Arthur and Effie on turn 3, at the east edge). Turns 3-7 the army holds the three ways onto the eastern island: the 2-wide bridge (x 11), the one-tile north way (14,8)-(14,9) and the one-tile south way (15,16); Effie, Arthur, Silas and Corrin kill the Faceless as they come, Elise and Felicia heal. Turns 8-11 Elise uses **Freeze** on the boss three times (it cannot move for that enemy phase) while Arthur's **Hand Axe** hits it from two tiles with Effie's Attack Stance (no counter: the boss has range 1). Turn 12 Corrin with the **Dragonstone** and Arthur's stance finishes it: stage complete (turn count on the screen 13); save slot 1; My Castle. No unit lost | `cq-ch7-clear` (sha256 starts `b8a42e39`) |

Checks (sessions in build/parallel/, `parallel.py`, this area's share: FEF_ROBOT_JOBS 3, 2 GB, below normal):

| Check | Result |
|---|---|
| Two replays (`runs --copies 2 --markers --keep`, session cq7r1) | both **memory `7ef78267...`**, 81,100 frames, 334 / 394 s, peak 609 MB |
| Marker run with the checkpoints (session cq7mk) | **checkpoints all met**, memory `7ef78267...` |
| Capture run (`--mode capture`, the capture library as it stands; session cq7cap) | 78 functions met, 1559 records, 1527 match, 24 gave up, 8 incomplete, **0 bad of any kind**, PASS, memory `7ef78267...` (the same as the original runs); writer totals "NOT REPORTED" (library built before the writer totals line) |
| Marker reads (unit counts player, enemy, other) | 17294 turn 1 [2, 13, 0] (route byte 1); 26011 [6, 11, 0]; 47933 [6, 6, 0]; 60723 [6, 3, 0]; 72990 [6, 1, 0]; 80058 stage complete [6, 0, 0]; 80428 `ChapterFileMenu`; 81023 `castle__Sequence` |
| Packed save | `parallel.py pack cq7r1 cq7r1-1 cq-ch7-clear` |

Every run printed "%APPDATA% (zakuro, 3dsrecomp) unchanged". The capture library was not rebuilt. The summary.tsv
lists functions by address only; which never-met readers it holds was not checked by name here.

### 8.2 What chapter 7 taught

- **The boss Faceless kills in one round**: Effie (17 HP) was a sure kill on its counter (99 % hit), Corrin with the
  Yato would drop to 6. It must be hit from two tiles (Hand Axe, Felicia's dagger) or finished in one attack.
- **Freeze** (Elise, 4 uses, range 1-7, hit about 80 %) stops the boss for one enemy phase; status byte Unit+0x28 = 2
  while frozen (read from the board dump). The staff menu remembers the last staff used: after a Freeze, `A A`
  picks Freeze again and `A DOWN A` picks Heal.
- Felicia's command menu puts **Attack** first when an enemy is in her dagger's range (1-2) and Staff first otherwise.
- The forecast's Y switches between the Yato and the Dragonstone; the Dragonstone often avoids the counter that the
  Yato's double attack takes in between.
- A Faceless moves about 7 tiles; two of them went around Corrin on the 2-wide bridge on turn 1.
- After the stage-complete banner the current screen is `castle__anonymous_namespace__Seq` and needs one A (the
  autopilot does not answer it); then the save slots: `A`, `LEFT`, `A`.

### 8.3 Chapter 8 (started, not cleared)

Chain `q8zd` in build/harness/robot/states/split-cq/ (from `cq-ch7-clear`; `cqsplit.py input q8zd` prints its input):
loading the save opens the castle's Preparations; the chain opens **Equip Skills > Corrin** and backs out (for
`unit_equipped_skill_count`; not captured yet), START (castle menu) > Next Battle (UP A) > Chapter 8 > LEFT A,
Fight! (START) > LEFT A. Win rule: defeat the boss (a Sorcerer at (3,5), 27 HP). 6 units deployed; Odin and Niles
join on turn 2. Turn 6 Corrin used the **lake dragon vein** at (17,14) (TrickData state 1 -> 2; "melt the ice to make
a lake for 1 turn"). `q8zd` is turn 21's player phase with all 8 units alive (Corrin 9 HP after killing an axe
fighter on the counter); 6 enemies plus the boss are left, all west of the lake.

What it needs: the axe fighters hit Corrin for about 10 each and every guard group joins once a unit comes near it;
Corrin alone at the front died twice (24 HP at (11,8) and at (12,7)), the Silas/Effie pair once. Reinforcements of a
fighter and three dark mages appear at the starting corner and at the south-west every few turns; dark mages beat
Effie and Silas (low resistance) and killed Effie and Arthur in look-aheads. Pair Up (move next to the ally,
command `Pair Up` is the third item of Effie's menu) keeps the weak unit off the board. Next step: from `q8zd`,
heal Corrin to full, step one tile at a time from (14,8) so that only one guard group joins per enemy phase.

### 8.4 Tools

- `tools/harness/robot/cqsplit.py`: split.py unchanged with this area's own folder `states/split-cq/` (states, inputs,
  its own `SPLIT_SLOTS` lock pool), chain names starting with `q`, and full-size contact sheets (`CQ_SCALE`, default
  1; `SPLIT_SCALE=1` for `press`), so the forecast numbers can be read.
- Config keys written with `splitcfg.py` only: `routes.json` `cq-ch7`, `markers.json` `cq-ch7`.

### 8.5 Time

About 15 s per look-ahead action, 1-2 minutes per end turn; a chapter-7 replay 5.5-9 minutes (81,100 frames,
slower beside the other area's runs). Chapter 7 took about 70 look-ahead actions and one restart of a turn (the
boss's line). Chapter 8 used most of the remaining time: 21 turns, four restarts of a turn after a lost unit.

## Round 9 fixes (2026-11-14)

- **Chapter id marker** (`markers.game_state`: `chapter`, `chapter_routes`). Read as the game's own script call
  ChapterGetName (0x003A92E8) reads it: GameUserData (*0x006DA248) +0xC = the current chapter's row (0 = none, kept
  as "NONE"), row +0 = a pointer to its id "CID_xxxx", kept without the prefix. `chapter_routes` from docs/ROUTES.md:
  A = bt, B = cq, C = rv from chapter 6, X007-X014 bt+rv, X015-X022 cq+rv, A000-A005 shared. The offset is a default
  in markers.py (`GUD_CHAPTER`), since markers.json is shared; integrate may move it to `state.gud_chapter`.
  Live check (boot-server replays of the verified routes' recorded presses, nothing new played; 802 s for 7 reads):
  cq-ch7 at 17294 `B007` (route byte 1) and at 80428 (save menu after the clear) `B008`; rv-ch7 at 22318 `C007`
  (route byte 2); bt-ch10 at 4399/8390/9980/110240 `A010` (route byte 0). So the branch is now proven directly, not
  only by the route byte and the cast. No checkpoint was added (routes.json / markers.json untouched); a route's
  owner can add `"state": {"chapter": "B007"}`. Self-test 40 checks (planted: a non-text id, each letter).
- **splitcfg.py**: the bare `assert` (skipped under `python -O`) is now `check_only_name_changed`: every top-level
  key other than the section and every other key in the section must be unchanged and NAME must hold the new
  object, else nothing is written (exit 1); written by temp + rename. `splitcfg.py --selftest` 10 checks; planted
  bugs (top-level keys skipped, other keys skipped, the new key not checked): all caught. On today's routes.json a
  no-change merge of `cq-ch7` gives byte-identical text.

## 9. Revelation, round 9 area "rv": chapter 9 cleared from `rv-ch8-clear` (route `rv-ch9`)

**In plain words.** Chapter 9 ("Wanderer", seize the throne) was played with the speed tools (fastlook on one kept
server) from frame 0 of the chapter-8 clear save and **cleared on turn 34 with nobody lost** (Corrin seizes after the
boss falls). Route `rv-ch9` (routes.json), checkpoints `rv-ch9` (markers.json), packed save `rv-ch9-clear`. Two
original boot.exe copies from frame 0 give the same memory with all checkpoints met (9.3). Chapter 10 was not started.

### 9.1 Which start [high]

A new look-ahead was made **from frame 0 of `rv-ch8-clear`** (title > Continue > the save opens the castle's
Preparations menu > B > START menu > Next Battle > Chapter 9 > Yes > events > Fight). The round-8 drift (7.3) came
from replaying presses recorded on a *different* line (the chain from rv-ch6-clear) after a reload; a look-ahead
recorded on this save's own line has no such problem, and its replay proof is the usual two original boot.exe copies
from frame 0 (9.3). So **rv-ch9 starts from rv-ch8-clear; there is no need to chain from rv-ch6-clear** (the rv9s chain
of round 8 was not used). The turn-1 board equals rv9s's (9 units, 26 enemies, boss 35 HP at (21,3)).

### 9.2 What chapter 9 taught [high for what was seen]

- **Winds fire every third turn**, at the end of the enemy phase of turns 1, 4, 7, 10, 13 (next: 16, 19), seen on
  turns 4, 7, 10 and 13 (turn 1: nobody stood on a wind tile). A unit on a wind tile is carried 3-7 tiles, **over
  walls**, so winds are the way between the walled-off areas. Seen: the start room's bridge (x13-16, y22-25) carries
  units north to y17-19; (16,16)/(16,17) carry north to (16,10)/(16,11) (the long corridor, y10-11); (11,15) carries
  south to (11,22); (11,19) to (11,23); (17,19) to (17,16); **(20,10)/(20,11) carry north into the boss room
  ((20,4)/(20,5), next to the boss and 6 guards)**: Gunter and Felicia landed there alone in one look-ahead, with the
  only way out blocked by a samurai at (18,5); that line was thrown away. Not winds (stayed put on a wind turn): (16,10), (16,11), (13,19), (14,19),
  (15,19), (16,19), (13,22). The wind tiles are not in the terrain grid (G_MapImage +0x808); the screen shows them as
  red arrows.
- The boss room has no walking way from the corridor at y10-11 (row 9 is wall); by foot it is reached only through the
  west room and the corridor at y5 (a samurai stands in its door at (18,5)).
- The enemy groups come in waves at the west side: the narrow corridor at y14 (x11-16) and the column x10 (y13-18).
  Corrin (Dragonstone, lv 15) holding (10,17) / (11,15) beat most of them; the archers must not reach the fliers
  (Tsubaki) or a lone unit at the corridor end: a try with Hana at (12,14) lost her (thrown away).
- A kill can drop an item into a full inventory: the "send to convoy" list (ItemMenuSend; UP = the new item, A) and a
  Yes/No (LEFT A).
- The end-turn menu is `map__anonymous_namespace__SystemMenu` (A on an empty tile, UP A); once (turn 11, tile
  (16,15)) A did not open it, and the plan's screen check stopped and rolled back.
- **Correction (later turns): the winds are not one fixed map.** On turn 16 the column x12-16 tiles carried units
  north (e.g. (16,16) to (16,11), (15,17) to (15,10), (15,19) to (15,14), (12,19) to (12,14), the bridge (14,23) to
  (14,19)). On turn 19 (16,16) and (16,17) did **not** move anyone, while (11,9), (11,10), (10,8) and (11,5) carried
  units **south** to (11,15), (11,16), (10,13), (11,11), and (17,16) carried Rinkah north to (17,10). On turn 25 the
  same (17,10) carried her to (17,5) (the boss-room door), on turns 22 and 28 nobody on rows 5-14 moved, and on turn 31
  (19,6)/(20,7)/(20,6)/(19,5)/(18,5) carried five units north to (19,3), (20,3), (20,2), (19,2), (18,3), next to
  the boss, while (17,5), (16,5), (15,5) stayed. The map also has three "Call wind" tiles (`*` in the terrain read: (1,3), (25,10), (2,16);
  the game's help text calls them a wind that moves enemies, once per turn); nobody used them. Treat every wind as a
  surprise: never leave a weak unit where a wind could drop it alone (a line where it did was thrown away).
- **Rinkah is a player unit** (force 0) and can be moved; she only looked idle because nobody moved her before turn
  26. A turn does not end by itself while she has not acted.
- The boss (Master of Arms, 35 HP, katana/naginata/club, all range 1) never moves; he heals on the throne (4 to 11
  HP between turns) and hits back hard (15 to Hana, 10 to Gunter). Gunter's lance did most of the damage (19); a
  Gunter with 11 HP next to him was killed in the enemy phase (that line was thrown away and cut back to turn 32).
  The win: Felicia's dagger from 2 tiles (no counter), then Corrin, on turn 33; Corrin seizes on turn 34.

### 9.3 The route and its proof [high]

- Chain **`rv9j`** in `build/speed/r9-rv/` (fastlook `--dir build/speed/r9-rv`), start save `rv-ch8-clear` from frame
  0, 183,000 frames, 2,512 presses, no breaks. Exported to routes.json `rv-ch9` (save_at 182,990; slot 1; ends in My
  Castle). Earlier chains rv9 .. rv9i are thrown-away or cut-back lines (rv9e = the round-9 first stop at turn 14; rv9f
  lost Tsubaki to an archer on turn 21; rv9g/rv9h got stray menu presses; rv9i lost Gunter to the boss on turn 32).
- `fastlook verify rv9j` (session sp-fastlook-rv9j-083117): two original boot.exe copies from frame 0 and the clean
  server line all give memory `18946c3f...`, equal cycles, verdict **SAME**, no breaks, problems [] (output:
  build/speed/r9-rv/verify-rv9j.txt).
- `parallel.py runs --route rv-ch9 --copies 2 --markers --keep --session rv-ch9a`: both **PASS**, Completed after
  183000 frames, **memory `7c408510...`** in both, **checkpoints all met** (6 checkpoints, markers.json `rv-ch9`),
  boot 524 s and 543 s (output: build/speed/r9-rv/runs-rv-ch9a.txt). (The verify memory hash and the runs memory hash
  differ because the two tools stop at different frames: verify at 183,010, runs at 183,000.)
- Packed: `parallel.py pack rv-ch9a rv-ch9a-1 rv-ch9-clear` -> build/harness/saves/rv-ch9-clear.zip.
- Capture run: see 9.5.

### 9.4 Time and method

Wall time, start of the look-ahead to the packed save: about **210 minutes** for 34 turns in two sittings (round 9
first try: 71 min for turns 1-13; this try: 06:43 to 09:02, about 139 min for turns 14-34 and the end screens). Of
that, about 18 minutes were one rollback on a server that had been started at frame 0 (a phase stop re-steps the whole
chain from the server's start state: 87,000 frames with another area's runs on the machine), and about 4 x 6 minutes
were cut-backs (a new chain replayed from frame 0). Lesson: after a long stretch, `stop` and `serve` again, so the
server's start state (state.bin) is recent and a stop costs seconds. Verify took 17 min (clean 9 min + 2 copies),
`runs --copies 2` 18 min (it ran the two copies one after the other). One `phase` call per unit action; board read
from live memory (rvserve.py `rb`); screenshots only on a stop, for the seize/save menus and one forecast-free check.

Helpers (untracked, build/speed/r9-rv/): `rvserve.py` (serve + `rb` rich board), `rb.py`, `act.sh` (cursor from its
live position to a unit, move, act; on a stop it cancels the selection with B), `run.sh` (several act.sh, stops at
the first failure), `go.sh`, `et.sh` (end turn), `mk.py`, `rewind.py` (cut back = new chain + one abs phase).

### 9.5 Capture run

`parallel.py runs --route rv-ch9 --copies 1 --mode capture --markers --timeout 3600 --session rv-ch9cap` with the
capture library as it stood (not rebuilt): **PASS**, Completed after 183000 frames, memory `7c408510...` (equal to the
original runs), **checkpoints all met**, **96 functions met, 2099 records, 2047 match, 32 gave up, 20 incomplete,
0 bad of any kind** (mm 0, escaped 0, unfaithful 0, damaged 0); writers: no writer stored anything (stores 0). Boot
530 s (no --timeout problem; 3600 was given). Output: build/speed/r9-rv/cap-rv-ch9.txt, summary
build/parallel/rv-ch9cap/summary.json. I did not compare the met-function list against earlier summaries this round
(open item for whoever looks at never-met readers next).

### 9.6 State to continue from

Chapter 10 is not started. Start it from the packed save `rv-ch9-clear` (My Castle after chapter 9), with a new
fastlook chain (`fastlook.py new rv10 --save rv-ch9-clear --dir build/speed/r9-rv`).

## 10. Revelation, round 9 area "rv": chapter 10 cleared from `rv-ch9-clear` (route `rv-ch10`)

**In plain words.** Chapter 10 ("Voice of a God", seize; boss Zola) was played by a fresh helper with fastlook
from frame 0 of `rv-ch9-clear` (it replays; no drift seen) and **cleared with nobody lost** (the stage-complete
screen counts 21 turns). Route `rv-ch10` (routes.json), checkpoints `rv-ch10` (markers.json), packed save
`rv-ch10-clear`. Proof and capture: 10.3.

### 10.1 What chapter 10 taught [high for what was seen]

- Sortie: the 6 default units (Corrin, Azura, Felicia, Gunter, Sakura, Hana). A talk and a "Victory: Seize" banner
  come after the first map frame; the banner waits for A (fastlook's answer table does not press it).
- The white field is **ice blocks** (terrain panel "Ice, HP 1"; attack them, one hit breaks one). Only 4 enemies
  are on the board at the start; the rest are hidden and appear when ice near them breaks (an axe fighter at
  (17,15), a mercenary at (17,11), an axe fighter at (19,9), a mercenary at (16,5), a fighter with a hand axe at
  (10,5), a dark mage at (6,4), and at (6,4)/(6,3) a cavalier (5,4) plus a **Mjolnir** dark mage (5,5)). The
  terrain grid read (G_MapImage +0x808) does not show the blocks (`%` = snow floor and ice alike); a block is seen
  only on the screen or by the move range.
- The way that worked: north up the x17-18 corridor from the start ledge, west along row 5 to (6,4), then the boss
  room (x1-4, y1-3; entry (4,4)/(5,3)).
- Opening (6,4) also lets the boss room's two Thunder mages and mercenary out. All five hit whoever stands at (6,4)
  in one enemy phase (Corrin 35 -> 10 alone; 35 -> 13 with Gunter paired as support). Lines thrown away: rv10b
  (Azura broke the ice at (19,15)-ish, a cavalier came out and killed her), rv10c (Hana at (18,13) killed by the
  axe fighter), rv10d (Gunter at (6,4) beside the Mjolnir mage), rv10e (Corrin left at 10 HP next to three mages).
- Kept line rv10f: Gunter pairs up with Corrin (moving onto him: one A shows the pair preview, a second A
  confirms); Corrin wakes the group, next turn pulls back to (10,5) and drinks a Vulnerary, Sakura heals him,
  Felicia's dagger (range 2, no counter, Hana beside her) kills the cavalier; the mages walk into the corridor and
  die to Corrin + Felicia (Azura's Sing gives Corrin a second attack). **Zola** (30 HP, Nosferatu): the Dragonstone
  forecast only did 10, the **Yato** (X on the forecast) kills him in one attack. Corrin seizes on the next turn.
- When every unit has acted the turn ends by itself (et.sh is then not needed and must not be sent).
- Drops into a full inventory (Vulnerary, Bloom Festal, Iron Bow, Master Seal) went to the convoy.

### 10.2 Helpers (untracked, build/speed/r9-rv/)

`ib.sh` (cursor to a unit, move, Attack/Staff, stop at the target screen with a shot), `cf.sh` (confirm + board),
`send.json` (new item to the convoy), `path.py` (fewest-ice path on the grid; not useful here, the grid does not
show the blocks), `mk.py` gained kind `ice`.

### 10.3 Proof, save, capture

- Chain **`rv10f`** (fastlook `--dir build/speed/r9-rv`), start save `rv-ch9-clear` from frame 0, 91,605 frames,
  1,327 presses; exported to routes.json `rv-ch10` (frames 91,600, save_at 91,590, slot 1, ends in My Castle).
- `parallel.py runs --route rv-ch10 --copies 2 --markers --keep --session rv-ch10a`: both PASS, memory
  **`7fb58f061e2710a4`** in both, but **1 checkpoint missed** in both: at frame 6453 the opening talk is already up
  (TalkKeyWait), my checkpoint wanted the bare map. The checkpoint was wrong, not the play; it was changed to
  TalkKeyWait (splitcfg) and the proof run again: `--session rv-ch10b`, 2 original copies: both **PASS**, same memory
  `7fb58f061e2710a4`, **checkpoints all met** (5), boot 722 s / 761 s (runs-rv-ch10b.txt). The in-game save files
  of the two rv-ch10a copies are byte-identical (Chapter0, Global).
- Packed: `parallel.py pack rv-ch10a rv-ch10a-1 rv-ch10-clear` -> build/harness/saves/rv-ch10-clear.zip, sha256
  `2009df59...`. Not yet loaded by a later route (chapter 11 not started).
- Capture `--session rv-ch10cap --mode capture --markers --timeout 3600` (library as it stood, not rebuilt): **PASS**,
  memory equal to the original runs, checkpoints all met, 97 functions met, 2006 records, 1955 match, 31 gave up,
  20 incomplete, **0** mismatch_r0 / regs / mem / calls, b_escaped, unfaithful, escaped, damaged; no writer stored
  anything (cap-rv-ch10.txt).
- Time: start of the look-ahead to the packed save about **81 minutes** (four cut-backs, each a 12-15 s replay
  from frame 0; most time went on screenshots to find the ice blocks). Proof re-run and capture after that: ~13 min.

### 10.4 State to continue from

Chapter 11 is not started. Start it from `rv-ch10-clear` (My Castle after chapter 10) with a new fastlook chain.

## 11. Conquest, round 9 area "cq": chapter 8 finished (route `cq-ch8`)

**In plain words.** Chapter 8 ("Cold Reception", defeat the boss) was cleared earlier this round by fastlook from
`cq-ch7-clear` and packed as `cq-ch8-clear` (sha256 starts `5151dbe5`); integrate replayed it to memory
`6897aa6ad14873c2`. A helper then gave it checkpoints and set it verified. No unit lost, 33 turns.

### 11.1 Route and checkpoints [high]

- Route `cq-ch8` (routes.json, written with splitcfg.py): 140,000 frames, save_at 139,990, slot 1, ends in My
  Castle. Play: turns 1-20 as round 8's chain q8zd (section 8.3; lake dragon vein at (17,14) on turn 6); turn 21
  Corrin falls back to (15,9) and is healed; he then steps west one tile a turn along row 8 with Felicia healing
  behind him; attacks the boss (Sorcerer, Nosferatu, at (3,5)) from (4,5) with the Yato; the boss dies to his
  counter in the enemy phase.
- Marker run (`runs --route cq-ch8 --copies 1 --markers`, session cq8mk): PASS, memory `6897aa6ad14873c2` (the
  integrate hash). Checkpoints (markers.json `cq-ch8`, splitcfg.py) from it: 107960 turn 21 [8, 11, 0], chapter
  `B008`; 124000 [8, 7, 0]; 137602 stage complete (`castle__anonymous_namespace__Seq` with
  `map__SequenceCompleteEffect`) [8, 6, 0]; 139400 the save message (`GameMessage`, chapter now `B009`); 139800
  `castle__Sequence`.
- Proof with the checkpoints (`runs --route cq-ch8 --copies 2 --markers`, session cq8v): **both PASS**, memory
  `6897aa6ad14873c2` in both, checkpoints all met, boot 602 s / 605 s, peak 367 MB. `verified` set true.

### 11.2 What chapter 8 taught (beyond 8.3)

- Stepping one tile a turn along row 8 woke one guard group at a time; Felicia kept Corrin topped up behind him.
- Around turn 29 an enemy staff froze Corrin for a turn (he could not move); nothing else changed.
- The boss Sorcerer does not leave (3,5); with Corrin next to him at (4,5) the boss attacks in the enemy phase and
  dies to the counter.

## 12. Revelation, round 10 area "rv": chapter 11 cleared from `rv-ch10-clear` (route `rv-ch11`)

**In plain words.** Chapter 11 ("Mutual Enemies", rout, boss Kotaro) was played by a fresh helper with fastlook
from frame 0 of `rv-ch10-clear` (it replays; no drift seen; this is the first route that loads that save) and
**cleared in 15 turns with nobody lost**. Saizo, Orochi and Reina joined by Corrin's talk with Saizo. Route `rv-ch11`
(routes.json), checkpoints `rv-ch11` (markers.json), packed save `rv-ch11-clear`.

### 12.1 What chapter 11 taught [high for what was seen]

- Start: 12 default units, 26 enemies, 3 green (Saizo, Orochi, Reina at (16-18,13)). Map 25 x 13, the Birthright
  chapter 10 forest; terrain names read: none, plain, plain/bamboo spikes, bamboo spikes, woods, deep forest,
  door/plain, chest; four vein tiles (type 11) at (6,7), (12,6), (14,8), (17,7) tied to four areas. No vein used.
- **Tiles "plain / bamboo spikes" take 1-3 HP a turn from whoever ends the turn on them** (ours and the enemy's)
  [med: seen as steady HP loss on exactly those tiles; not traced in code]. End turns on plain or woods when possible.
- The west ninjas, archer and samurai charge on turn 1; a unit at the pocket edge alone dies (Kaze at (7,7) in a
  first try; Felicia healing at (7,6) in a second; both undone). Holding the start pocket (8-13, 3-8) with Corrin at
  (7,7), Takumi behind, and the healers inside worked. The east and boss groups do not move until someone comes near.
- Green Saizo (11 HP) was killed by a 1-HP oni next to him in one try (undone). Killing that oni first (Hinata from
  (14,8), Felicia's dagger from (12,9)), then Azura's Sing on Corrin, let Corrin reach (13,10) and Talk on turn 4.
  The talk makes all three player units at once; Reina was then deep in the east and must be pulled back that turn.
- Reina (Kinshi Knight, Iron Naginata, Atk 25) doubles master ninjas and spear fighters; she fell to 1 HP once after
  killing two units in one enemy phase (kept: nobody lost). Kotaro (36 HP): Reina 15, then Takumi's Fujin Yumi 22.
  Two attacks missed in tries (Corrin on a 7-HP master ninja, Takumi on Kotaro); changing the order of the attacks
  (which changes the random rolls) fixed both.
- The north-west master ninja and diviner wait in the corner; Gunter at (5,7) drew the master ninja out, Rinkah's
  club (axes beat shuriken) with Gunter beside her and then Gunter's lance killed it; Hana and Rinkah beat the diviner.
- A drop into a full inventory again needed the convoy screen (Heal staff sent). The STAGE COMPLETE screen waits for A.
- Grok's tracks/ROUTES_CQ_RV.md checked: rout, 25 x 13, the Saizo talk brings Orochi and Reina, boss Kotaro: all as
  written. "Kagero joins at the end" was not seen in the board read (not looked for). The vein was not needed.

### 12.2 Helpers (untracked, build/speed/rv11/tools/)

The round-9 bt helpers copied and pointed at build/speed/rv11: `act2.py` (one unit action = one fastlook phase, with
`hist/` snapshots and `undo N`), `rb.py` (board read by name, terrain grid, tricks, `-T` terrain names; Revelation
names added), `pp.py`, and `et.sh` (end turn + board). One-shot calls only (no server kept).

### 12.3 Proof, save, capture

- Chain **`r11`** (`--dir build/speed/rv11`), from frame 0 of `rv-ch10-clear`, 168,284 frames, 2,449 presses;
  route `rv-ch11`: frames 168,200, save_at 168,190, slot 1, ends in My Castle. Checkpoints: 12498 turn 1 [12, 26, 3];
  64472 after the talk [15, 13, 0]; 165290 stage-complete effect [15, 0, 0]; 165350 STAGE COMPLETE
  (`castle__anonymous_namespace__Seq`); 168100 `castle__Sequence` after the save.
- `parallel.py runs --route rv-ch11 --copies 2 --markers --keep --session rv-ch11a` (FEF_ROBOT_JOBS=3,
  FEF_ROBOT_MEM_GB=1.98): both **PASS**, 168,200 frames, memory **`be1bfea953e7fa50`** in both, **checkpoints all
  met**, 714 s each side by side, peak 367 MB (runs-rv-ch11a.txt).
- Packed: `parallel.py pack rv-ch11a rv-ch11a-1 rv-ch11-clear` -> build/harness/saves/rv-ch11-clear.zip, sha256
  `c4a6b57b...`.
- Capture `--copies 1 --mode capture --markers --timeout 3600 --session rv-ch11cap` (library as it stood):
  **PASS**, memory `be1bfea953e7fa50` (equal to the original copies), checkpoints all met, 91 functions met, 1999
  records, 1957 match, 31 gave up, 11 incomplete, **0** mismatch of r0 / regs / mem / calls, 0 b_escaped,
  unfaithful, escaped, damaged; no writer stored anything; 591 s (cap-rv-ch11.txt).
- Time: start of the look-ahead to the packed save about **83 minutes** (16:33 to 17:56): ~57 min look-ahead
  (15 turns, each enemy phase 1-2 min of frames; three undone losses and two re-rolled misses), 12 min the two
  proof copies, under 1 min to pack. Capture 10 min after that.

### 12.4 State to continue from

Chapter 12 is not started. Start it from `rv-ch11-clear` (My Castle after chapter 11) with a new fastlook chain.
Grok's note: Revelation chapter 12 is the script reader Birthright can never meet.

## 13. Revelation, round 10 area "rv": chapter 12 cleared from `rv-ch11-clear` (route `rv-ch12`)

**In plain words.** Chapter 12 ("Frozen Sea", defeat the boss; boss Flora) was played by a fresh helper with fastlook
from frame 0 of `rv-ch11-clear` (it replays; no drift seen; the first route that loads that save) and **cleared in
19 turns with nobody lost** (12 units at the end). Route `rv-ch12` (routes.json), checkpoints `rv-ch12`
(markers.json), packed save `rv-ch12-clear`.

### 13.1 What chapter 12 taught [high for what was seen]

- Start: 12 default units (Corrin, Azura, Felicia, Gunter, Sakura, Hana, Takumi, Oboro, Hinata, Subaki, Kaze,
  Rinkah; Saizo, Orochi, Reina not sortied), 27 enemies, 0 green. Map 28 x 28: four of our boats (left top, left
  middle, right middle, right bottom) and the enemy's boss boat (rows 1-6, x14-28) on an "Icy Sea". Terrain names
  read: none, sea, wall, floor, stairs, icy sea, icy sea / sea road, sea road.
- **Our units cannot walk the icy sea** (Corrin's move range stops at the boat edge; three planned moves onto it were
  refused), **but the enemy's fighters, mages, thieves and berserkers walk it** at will. Only a royal on a dragon
  vein makes a crossing: "Call floating blocks of ice to form a path". Veins (trick type 11) and their areas
  (type 12): (4,10)/(6,14)/(21,11) -> the centre strip rows 10-13 x4-23; (25,11)/(24,2) -> the bridge (25-26,7-10)
  to the boss boat; (7,19) -> (7-8,20-22); (24,16)/(24,19) -> (24-26,17-18). The path costs 1 (class of floor).
- Corrin on (6,14) on turn 1 had no Dragon Vein command (cause not found); on (7,19) on turn 6 he had it. Sakura
  (royal, support of Gunter) got the command after the pair moved and then **Switch** made her the lead.
- The boss boat is closed: walls on x13 and sea on row 7, so its units leave only by the bridge (or fly).
  **Camilla** (Malig Knight, Hand Axe + Steel Axe, 30 HP) flies: she woke when Hana stood 10 tiles from her
  (16,1) and hit Hana 21 -> 2 from range 2; Gunter's forecast against her was "a very dangerous confrontation"
  (Gunter killed). That turn was undone; the left groups then walked east keeping more than 10 tiles from (16,1),
  and she never moved again [med: the 10-tile rule fits what was seen, move 8 + range 2; not traced].
- The bridge-end sorcerers (Fire / Thunder, 27 HP) and a berserker came down only when a unit stood 7 tiles from
  them; Felicia (high Res) as bait at (25,9) / (26,8) pulled one or two at a time. Takumi's Fujin Yumi kills a
  sorcerer or a 33-HP berserker in one attack from range 2; Corrin's Yato kills a sorcerer.
- Flora (Maid lv 3, 28 HP, Steel Dagger + Heal) never moved: Takumi from (24,4) 28 -> 8, Corrin's Yato from (25,2)
  finished her (Dragonstone did 0 against her Res). Win at once on her defeat; STAGE COMPLETE counts 19 turns.
- Outlaws carry bows (effective on Subaki): Subaki was lost once (turn 6, undone). Sakura starts with no staff;
  Hana's Sun Festal traded to her (Trade, then Staff in the same turn) heals. Reinforcements: axe fighters from the
  boss boat down the bridge (turns 5-6), a thief and a dark mage on the boss boat (turn 7), axe fighters in the
  bottom left (turn 6).
- A drop into a full inventory (Thunder, then Flora's Steel Dagger) needs the convoy screen (UP, A, Yes).
- Grok's tracks/ROUTES_CQ_RV.md checked: "win is defeat Flora": as written. "The vein makes ice bridges between the
  boats. Use it once": the vein makes the paths, but one was not enough here (two used: the strip and the bridge).
  "Camilla, Selena, and Beruka join": not checked (the post-battle talks were passed with A; no unit list read after).

### 13.2 Helpers (untracked, build/speed/rv12/tools/)

The rv11 helpers copied and pointed at build/speed/rv12 (`act2.py`, `rb.py`, `pp.py`, `cfg.py`, `et.sh`), plus
`ms.py` (markers state of chain snapshots, read only, used to pick the checkpoint values). One-shot calls only.
Lesson: act2 undoes a stopped call by itself, so an extra `undo` after a stop removes the action before it (happened
once; the removed attack was replayed with the same presses and gave the same result).

### 13.3 Proof, save, capture

- Chain **`c12`** (`--dir build/speed/rv12`), from frame 0 of `rv-ch11-clear`, 135,920 frames, 1,963 presses;
  route `rv-ch12`: frames 136,000, save_at 135,990, slot 1, ends in My Castle. Checkpoints: 15492 turn 1
  [12, 27, 0], no pair; 63102 after Sakura's vein [12, 19, 0], veins_used 4; 103142 after Takumi's vein [12, 14, 0],
  veins_used 5; 129894 STAGE COMPLETE (`castle__anonymous_namespace__Seq`); 135920 `castle__Sequence` after the save.
  (`veins_used` here counts vein tiles whose state bit 0 is clear; on this map it reads 8 on turn 1 and changes with
  the turn, so it is a literal reading, not a count of uses [high for the readings, med for the meaning].)
- `parallel.py runs --route rv-ch12 --copies 2 --markers --keep --session rv-ch12a` (FEF_ROBOT_JOBS=3,
  FEF_ROBOT_MEM_GB=1.98): both **PASS**, 136,000 frames, memory **`11a11690e20a163c`** in both, **checkpoints all
  met**, 521 s / 524 s side by side, peak 365 MB; %APPDATA% unchanged (runs-rv-ch12a.txt).
- Packed: `parallel.py pack rv-ch12a rv-ch12a-1 rv-ch12-clear` -> build/harness/saves/rv-ch12-clear.zip, sha256
  `686cc9ba...`; its Chapter0 and Global differ from rv-ch11-clear's (the slot-1 save was written).
- Capture `--copies 1 --mode capture --markers --timeout 3600 --session rv-ch12cap` (library as it stood):
  **PASS**, memory `11a11690e20a163c` (equal to the original copies), checkpoints all met, 96 functions met, 2029
  records, 1975 match, 30 gave up, 24 incomplete, **0** mismatch of r0 / regs / mem / calls, 0 b_escaped,
  unfaithful, escaped, damaged; no writer stored anything; 385 s (cap-rv-ch12.txt).
  **`script_unit_can_dragon_vein` (0x003ABD8C) is met here for the first time in real play: 13 records, 13 match**
  (summary.tsv), as Grok's note expected (the chapter's script, not the vein press).
- Time: start of the look-ahead to the packed save **65 minutes** (18:20:01 to 19:24:40): ~52 min look-ahead
  (19 turns; one undone loss (Subaki), one undone turn (Camilla woken), a few refused moves onto the icy sea),
  9 min the two proof copies, under 1 min to pack. Capture 7 min after that.

### 13.4 State to continue from

Chapter 13 is not started. Start it from `rv-ch12-clear` (My Castle after chapter 12, slot 1) with a new fastlook
chain. The track's window ends at 12 (tracks/ROUTES_CQ_RV.md: "Do not continue to chapter 13").

## 14. Revelation, round 10 area "rv": chapter 13 cleared from `rv-ch12-clear` (route `rv-ch13`)

**In plain words.** Chapter 13 ("A Lost Peace", Cyrkensia; defeat the boss) was played by a fresh helper with fastlook
from frame 0 of `rv-ch12-clear` (it replays; no drift seen; the first route that loads that save) and **cleared with
nobody lost** (14 units at the end; the stage-complete screen counts 32 turns). Route `rv-ch13` (routes.json),
checkpoints `rv-ch13` (markers.json), packed save `rv-ch13-clear`.

### 14.1 What chapter 13 taught [high for what was seen]

- Start: 14 units (the 12 of chapter 12 plus Kaden and Keaton, who join at the start), 38 enemies, 0 green. Map
  20 x 25 town with canals. Terrain names read: none, plain, sea, sea / plain, wall, obstacle (on floor), floor (under
  obstacle). Win: defeat the boss, a Vallite Berserker (lv 4, 44 HP, Silver Axe + Hand Axe) at (11,2).
- **Our start pocket (6-12, 22-25) is shut by rubble**: grid kind 5 is "Obstacle, impassable". The chapter's own
  tutorial text: a unit next to an obstacle can **Grab** it and later **Set** it next to itself. Sakura grabbed the
  one at (9,21) on turn 2 (command menu item 1), which opened the pocket; she carried it to the end (it shows as an
  item "Obstacle"). Other obstacles: (4,16), (4,20), (11,16), (19,11), (19,15), (18,22), (15,23), (2,23), (4,9).
- Nohr army on the left (Xander, Paladin lv 3, 37 HP, Siegfried, at (4,4); Peri + Laslow as a pair; paladins,
  cavaliers, knights, thieves, mercenaries), Hoshido on the right (Ryoma at (16,4), Scarlet at (17,4), samurai,
  ninjas, archers, a diviner, a great master, an onmyoji), Vallite soldiers in the moated centre (General at (11,7)
  is the only door of the boss room; axe fighter, two dragon knights). **Xander and Ryoma each stand next to the only
  land entrance of the centre** and never moved all game. Forecast Corrin vs Xander: Yato 2 damage to him, 23 to
  Corrin; Dragonstone 12 to him, 18 to Corrin. He was left alone.
- Enemies wake by distance (most stood still until a unit came within their move + range); Kaden was lost once (turn
  7, three attackers at (4,15)) and Keaton once (turn 10, a paladin woke from (2,5)); both turns undone.
- Two vein tiles (trick type 11) at (4,1) and (17,1), area (type 12) x5-16, y0-13. Corrin on (4,1) on turn 17: "Lower
  the tide to make river passable": every "sea / plain" tile (the moats around the centre and rows 12-13) becomes
  land and **both** vein tiles read used (`veins_used` 0 -> 2). After it the Hoshido units and the centre's units
  started moving toward us and reinforcements came (turn 17: a paladin and a master ninja on each side; turn 12, before
  the vein, a cavalier, a thief and a mercenary on each side). The chapter script (C013_Terrain.cmb) names
  `AI_MV_NearestEnemy` and the reinforcement flag next to the vein; which units get the new AI was not traced [med].
- After the vein the left column (x1-3, rows 7-15) was held: Keaton on (3,8) as the plug (only (4,8) touches it),
  fragile units only on tiles no enemy can reach or shoot (Azura was lost twice to bows/javelins from (5,9) and
  (5,12), Hinata and Subaki once each; all undone). The onmyoji's counter killed Subaki (22 HP) in one round.
- The General left the boss room to hit Corrin and fell to Keaton; Keaton then killed the axe fighter and both
  dragon knights at the door (11,7)-(11,8). The boss never moved: Takumi from (11,4) (no counter) 44 -> 20, Corrin
  with the Yato from (11,3) and Takumi's attack stance finished it. A full inventory asked to send one item (Hand
  Axe, UP A, Yes).
- Grok's tracks: nothing on chapter 13 (the track window ends at 12), so nothing to check.

### 14.2 Helpers (untracked, build/speed/rv13/tools/)

The rv12 helpers copied and pointed at build/speed/rv13 (`act2.py`, `rb.py`, `pp.py`, `cfg.py`, `et.sh`, `ms.py`),
plus `ux.py` (raw unit bytes at given tiles, read only; did not find the stats). One-shot calls only.
Lessons: Pair Up, Sing, Grab, Staff, Items > Vulnerary are menu items picked with raw presses after `act2 ... show`;
`pp.py` needs kind 5 left out (obstacle) and kind 3 added only after the vein.

### 14.3 Proof, save, capture

- Chain **`c13`** (`--dir build/speed/rv13`), from frame 0 of `rv-ch12-clear`, 231,888 frames; route `rv-ch13`:
  frames 232,000, save_at 231,990, slot 1, ends in My Castle. Checkpoints: 13472 turn 1 [14, 38, 0], no pair,
  veins_used 0; 123278 after Corrin's vein [14, 22, 0], veins_used 2; 226374 STAGE COMPLETE
  (`castle__anonymous_namespace__Seq`); 231888 `castle__Sequence` after the save. The chain has many write-back
  breaks (one-shot calls, screenshots), so its state.bin is not the clean line; the proof is the two original copies.
- `parallel.py runs --route rv-ch13 --copies 2 --markers --keep --session rv-ch13a` (FEF_ROBOT_JOBS=3,
  FEF_ROBOT_MEM_GB=1.98): both **PASS**, 232,000 frames, memory **`6b293319033d2f69`** in both, **checkpoints all
  met**, 886 s / 887 s side by side, peak 364 MB; %APPDATA% unchanged (runs-rv-ch13a.txt).
- Packed: `parallel.py pack rv-ch13a rv-ch13a-1 rv-ch13-clear` -> build/harness/saves/rv-ch13-clear.zip, sha256
  `1642d3ef...`.
- Capture `--copies 1 --mode capture --markers --timeout 3600 --session rv-ch13cap` (library as it stood): **PASS**,
  memory `6b293319033d2f69` (equal to the original copies), checkpoints all met, 96 functions met, 2140 records, 2094
  match, 32 gave up, 14 incomplete, **0** mismatch of r0 / regs / mem / calls, 0 b_escaped, unfaithful, escaped,
  damaged; no writer stored anything; 707 s (cap-rv-ch13.txt).
- Time: start of the look-ahead to the packed save **83 minutes** (epoch 1794703610 -> 1794708596): ~65 min
  look-ahead (32 turns; five undone losses: Kaden, Keaton, Azura twice, Hinata, Subaki), ~15 min the two proof copies,
  under 1 min to pack. Capture 12 min after that.

### 14.4 State to continue from

`rv-ch13-clear` (My Castle after chapter 13, slot 1). Chapter 14 is not started; start it with a new fastlook chain.
Not checked: who joins after chapter 13 (the post-battle talks were passed with the answer presses).

## 15. Revelation, round 10 area "rv": chapter 14 started from `rv-ch13-clear`, NOT cleared (no route key yet)

**In plain words.** A fresh helper played chapter 14 with fastlook from frame 0 of `rv-ch13-clear` (it replays; no
drift seen; the first route that loads that save). The chapter is **not cleared**: after 33 turns 25 of 35+ enemies are
dead and nobody is lost, but the last part (two late paladins plus the bottom-left group) could not be finished with
the army split as it is. No route key, no checkpoints, no packed save, no capture run. The best chain is kept.

### 15.1 What chapter 14 taught [high for what was seen]

- Start: title > Continue > castle > Next Battle > Chapter 14 > Yes > events (answer presses) > Preparations (START,
  LEFT A) > "Rout the enemy" banner (wait about 200 frames, then A). 15 units: the 12 of chapter 13 minus Kaden and
  Keaton, plus **Elise, Arthur, Effie** (they join at the start). 35 enemies on turn 1.
- Map 26 x 22 Nohr town. Grid kinds here: 1 plain, 3 bridge, 4 sea/plain (water, impassable), 5 village, 8 building,
  9 low wall, 10 low-wall gap, 11 floor, 12 bow ballista, 13 magic ballista. Villages (2,2), (15,2), (8,10), (21,10):
  visits gave Wane Festal (Corrin), Levin Sword (Gunter); a thief razed (21,10). Ballistas are worked from the next
  tile ("Ballista" first in the command menu); the one at (12,10) had nothing in range.
- Win: rout. **Reinforcements** at the map edges on turns 6-9 (thieves, cavaliers, mercenaries), turn 20 (two
  paladins top right, two mercenaries left) and turn 31 (two cavaliers right, two paladins top right). The thieves and
  most cavaliers/paladins move at once; armors, generals, mercenaries and fighters mostly wait until a unit comes into
  reach, and groups wake together (both right paladins came when one was baited: Effie lost once, Gunter lost once,
  both undone).
- Boss = **Silas** (Cavalier lv 18, Silver Sword + Javelin) at (16,22) in a walled yard whose only door is the bridge
  (19,19)-(19,20); two Generals at (18,19),(18,20) never moved until hit. No Talk command with Silas or Benny (Corrin
  adjacent). Takumi's Fujin Yumi from range 2 killed a General in one attack and took Silas 33 -> 12 (no counter);
  Corrin finished him with the Dragonstone. Benny (Knight) and Charlotte (Fighter, (7,22)) are plain enemies.
- Corrin: Yato for cavaliers/paladins, Dragonstone for armors/generals (it hits the lower of Def/Res); X swaps the
  weapon on the forecast. Most of our other units do 0-5 damage to paladins, generals and armors.
- Left column x1-3 is a pocket: north door the low-wall gap (2,5), south choke (1,10) (only (1,11) touches it). With
  Effie at (2,4) the gap tile (2,5) cannot be reached, so units in rows 6-9 are safe from the north.

### 15.2 Where it stands, and why it stopped

- Chain **`c14`** (`--dir build/speed/rv14`), from frame 0 of `rv-ch13-clear`, kept at **frame 274,859** (turn 33,
  player phase, mid-turn): 15 units alive; 10 enemies left: Charlotte (7,22), thieves (1,21),(3,21), mercenaries
  (3,19),(1,12),(6,21),(8,21), fighter (1,13), and the turn-31 paladins at (18,2),(18,3). Already acted this turn:
  Hinata, Felicia, Rinkah, Sakura + Azura (paired at (7,3)); not yet: Corrin (17,22), Takumi (16,20), Subaki (19,20),
  Oboro, Gunter, Arthur, Elise, Kaze, Hana, Effie. The chain has many write-back breaks (one-shot calls,
  screenshots, 579 listed): run `fastlook clean c14` before using its state.bin; prove with parallel.py, not verify.
- The problem: the strong units (Corrin, Takumi) are at the boss yard in the south-east, the weak "west team" (Effie,
  Rinkah, Hana, Kaze, Elise, Sakura + Azura) is in the left column with mercenaries/fighter at its south choke, and the
  two paladins (33 HP, javelin) walk the top row into the pocket and over the bridge (4-6,3) to them. Played on from
  here three ways: each lost a unit (Hana, Kaze, or Hana + Rinkah + Kaze); one way kept all 15 for two more turns but
  left Effie at 1 HP between both paladins. The west team cannot hurt the paladins (Hana's forecast: 0 damage).
- Next helper: start from this chain (or from frame 0 with these presses) and bring Takumi and Corrin back north
  first (corridor x20-22 up to rows 12-13, bridges west, into the pocket by (15,9)); keep the west team out of
  paladin reach (8 move + javelin 2) and plug the column gap with Effie at full HP only when Takumi is one turn away.
  The rest is the bottom-left group (lances for the mercenaries, Corrin's Yato for the fighters, Takumi for thieves).

### 15.3 Helpers (untracked, build/speed/rv14/tools/)

The rv13 helpers pointed at rv14, plus: `rb.py` now prints each unit's items (Unit +0x108, item record name), `th.py`
(enemy reach from the board, weapon ranges from items, "x,y>x2,y2" to try moves; it assumes every enemy wakes, so it
over-warns, and it missed the group wake once), `bd.py`/`b.sh` (short board + reach), `rp.sh` (one raw press step,
optional screenshot). One-shot calls only (the serve mode cannot give state.bin to rb.py without a stop).

### 15.4 Time

Start of the look-ahead 21:40, stopped 23:08 (88 minutes), no proof run, nothing packed.

## 16. Revelation, round 10 area "rv": chapter 14 cleared (second fresh helper; route `rv-ch14`)

**In plain words.** A second fresh helper continued section 15's chain and **cleared chapter 14 with nobody lost**
(15 units; the stage-complete screen counts 45 turns). It did not start from 15's mid-turn frame 274,859: it went back
to the **start of turn 33** (frame 266,868, a snapshot of chain `c14`) and replayed turn 33 differently. Frames 0 to
266,868 are the first helper's presses. Route `rv-ch14` (routes.json), checkpoints `rv-ch14` (markers.json), packed
save `rv-ch14-clear`.

### 16.1 What worked [high for what was seen]

- Turn 33: every west unit into the left pocket. Sakura + Azura paired (Azura moves onto Sakura, then Sakura moves).
  Effie at (2,4), then on turn 34 **on the west bridge (4,3)**. The two turn-31 paladins walked west and stood on the
  bridge (5,3), (6,3) hitting her. **Their javelin does 1-3 to Effie, the sword about 9**; her Iron Lance does 8 to them.
  Nobody else was within their reach: the pocket's only other tile in range is (3,3).
- Elise cannot use Physic (it needs staff rank C). She traded Mend to Sakura, and Sakura healed Effie from (3,3). The
  javelin does 8 to Sakura there.
- South choke (1,10)-(1,11): the mercenary and the fighter came up. Kaze from (1,9) (range 2, no counter) plus Hana
  (Rinkah paired as her support) killed them.
- **Pair-up taxi:** a unit that moves onto Subaki rides along on his 7-tile flight. A *separated* unit counts as having
  acted. **Switch after the flight makes the passenger the lead, and it can still attack from that tile.** Corrin rode to
  (8,5) and then (7,20) that way.
- Turn 38: Corrin with the Silver Sword (forecast 33 -> 1; the Yato did 24, the Dragonstone only 9) killed the paladin
  at (6,3). Turn 39: Corrin killed the one at (5,3) after Effie missed.
- Bottom-left group: enemies wake by reach. Baits at (3,13) (Oboro + Arthur) and (1,13) (Gunter + Hinata) drew a
  mercenary and both thieves. Oboro counter-killed mercenaries; Hana, Gunter and Kaze (Oboro's attack stance) killed
  the thieves. Turn 44: Corrin as lead at (7,20) was the only unit in reach of the last mercenary and Charlotte, and his
  counters killed both in the enemy phase. STAGE COMPLETE, A, answer presses, save slot 1 (A, LEFT A), castle.
- The magic ballista at (7,5) ("Fire Orb" at the top of the menu from (8,5)) did nothing for Subaki or Corrin [low; not
  traced].

### 16.2 Proof, save, capture

- Route `rv-ch14`: 389,600 frames, save_at 389,590, slot 1, ends in My Castle. Checkpoints:
  - 15372: turn 1 [15, 35, 0], no pair.
  - 345740: turn 39 [15, 7, 0], paired_player 6.
  - 386524: STAGE COMPLETE (`castle__anonymous_namespace__Seq`).
  - 389492: `castle__Sequence` after the save.
- `parallel.py runs --route rv-ch14 --copies 2 --markers --keep --session rv-ch14a` (FEF_ROBOT_JOBS=3,
  FEF_ROBOT_MEM_GB=1.98): both **PASS**, memory **`d774896c4be00a7b`** in both, **checkpoints all met**, about 1299 s
  each, peak 367 MB, %APPDATA% unchanged (build/speed/rv14/runs-rv-ch14a.txt).
- Packed: `parallel.py pack rv-ch14a rv-ch14a-1 rv-ch14-clear` -> build/harness/saves/rv-ch14-clear.zip, sha256
  `ee197ab3...`.
- Capture `--copies 1 --mode capture --markers --timeout 3600 --session rv-ch14cap`: **PASS**, memory
  `d774896c4be00a7b` (the same as the original copies), checkpoints all met, 104 functions, 2383 records, 2330 match,
  31 gave up, 22 incomplete, **0** mismatches of any kind, 0 b_escaped, unfaithful, escaped or damaged; no writer stored
  anything; 874 s (build/speed/rv14/cap-rv-ch14.txt).
- Time: from the start of this helper's look-ahead to the packed save, **85 minutes** (epoch 1794715716 ->
  1794720810). That was about 60 minutes of look-ahead (turns 33-45, no unit lost and no undo for a loss) and 22 minutes
  for the two proof copies. The capture took 15 minutes after that.
- Continue from `rv-ch14-clear` (My Castle after chapter 14, slot 1). Start chapter 15 with a new fastlook chain.

### 16.3 Not checked

- Who joins after chapter 14 (the talks were passed with answer presses). Charlotte was killed; whether she, Benny or
  Silas could be recruited in this chapter was not checked [med].
- Helpers: build/speed/rv14/tools (act2.py gained `pair`; bb.sh = the board for `c14b`). Chain **`c14b`**
  (`--dir build/speed/rv14`) has 903 recorded write-back breaks (one-shot calls, screenshots), so its state.bin is not
  the clean line. The proof is the two original copies. Chain `c14` (section 15) is kept unchanged.

## 17. Conquest, round 10: chapter 9 finished by integrate (route `cq-ch9`)

**In plain words.** Conquest chapter 9 ("Another Trial", seize the throne; boss Haitaka, a Spear Fighter with a Steel
Nageyari, range 1-2, on the throne at (17,8)) was played to the end by two fresh cq helpers in fastlook chain `q9g`
(build/speed/r9-cq9, from frame 0 of `cq-ch8-clear`): seize on turn 28, nobody lost, saved in slot 1, My Castle. Both
helpers had to return while their two-copy proof was still running, so neither proof finished (sessions cq9a and cq9b
are empty). Integrate ran the proof, wrote the checkpoints, packed the save and set `verified: true`.

### 17.1 What chapter 9 taught [high for what was seen, from the helpers]

- (15,12) is a breakable wall (15 HP); breaking it opens the south corridor into the room below the throne room.
- Corrin talks to Nyx (green, (12,13)) on turn 3 and she joins: 9 player units at the start, 10 after the join.
- Reinforcements (two spear fighters, two archers) appear when a unit ends its turn at about (20,9) or further north.
- The throne boss heals about 6 a turn; it fell only to Corrin's Dragonstone twice in one turn (Effie's attack stance,
  then Azura's Sing).
- Pressing any button on the final battle forecast starts the fight; the target-select view is the safe one (B goes
  back). A separated backup cannot act until the next turn.
- Healing left for chapter 10 is thin: Elise's Heal staff broke and Felicia's staff has 1 use left.

### 17.2 Proof, checkpoints, save, capture (integrate)

- `parallel.py runs --route cq-ch9 --copies 2 --markers --keep --timeout 3600 --session i10-cq9` (FEF_ROBOT_JOBS=2):
  both **PASS**, 123,500 frames, memory **`bf1c69255758cc0b`** in both, 705 s / 712 s, peak 495 MB, %APPDATA%
  unchanged. The two copies' Chapter0 and Global are byte-identical.
- Checkpoints (markers.json `cq-ch9`, written with splitcfg.py `marks`, read from that proof at the route's shots):
  12942 turn 1 [9, 17, 1]; 61430 Nyx joined [10, 10, 0]; 87244 [10, 6, 0] with a pair; 92376 reinforcements
  [10, 9, 0]; 119312 turn 28 [10, 5, 0]; 120220 STAGE COMPLETE [10, 5, 0]; 122550 the save question
  (`GameDialogYesNo`, chapter now B010); 123300 `castle__Sequence`. All route byte 1.
- Packed: `parallel.py pack i10-cq9 i10-cq9-1 cq-ch9-clear` -> build/harness/saves/cq-ch9-clear.zip, sha256
  `6e6c5d99...`; Chapter0 and Global differ from cq-ch8-clear (the slot-1 save happened).
- Capture `--mode capture --only all --store-keep --markers --session i10-cq9cap`: same memory, every checkpoint met,
  152 functions, 3,318 records, 27 `mismatch_calls`, all in `cursor_terrain` (the movement batch's fault, docs/MOVE.md
  9, fixed the same night). After the fix, r10-capb's cq-ch9 run: PASS, same memory, checkpoints met, 0 bad.
- `verified: true` (splitcfg.py `route`).

### 17.3 State to continue from

`cq-ch9-clear` (My Castle after chapter 9, slot 1). Chapter 10 is not started; start it with a new fastlook chain.

## 18. Revelation, round 11 area "rv": chapter 15 cleared from `rv-ch14-clear` (route `rv-ch15`)

**In plain words.** One fresh helper played Revelation chapter 15 ("Rainbow Sage" on the save screen) with fastlook
one-shot calls from frame 0 of `rv-ch14-clear` (it replays; no drift seen). Seize on turn 19, **nobody lost** (9 units
plus Shura, who joined on turn 7). Route `rv-ch15` (routes.json), checkpoints `rv-ch15` (markers.json), packed save
`rv-ch15-clear`.

### 18.1 What chapter 15 taught [high for what was seen]

- Start: title > Continue > castle > Next Battle (START opens the castle menu, DOWN x4 A) > Chapter 15 > Yes > events
  (answer presses) > Preparations (START, LEFT A; the default 9 units: Corrin, Azura, Felicia, Gunter, Sakura, Hana,
  Takumi, Oboro, Hinata) > START skips the opening talk > LEFT A > "Seize" banner. 30 enemies, all "Illusion".
- Map 30 x 30 of rooftops: 7 islands, terrain kinds 1 impassable, 2 floor, 3 stairs, 4 gate, 5 chest. The stairs
  (trick type 28; the destination is a "x,y" string at trick+0x18) are one-way pairs: (15,29)<->(25,28),
  (19,23)<->(28,19), (19,18)<->(23,10), (15,13)<->(15,9), (11,18)<->(7,10), and by the type-14 records' list
  (2,16)<->(9,20), (3,25)<->(6,29). The east way taken: start > B (18-26,23-28) > C (23-28,10-19) > D (11-19,13-18) >
  throne island G (11-19,1-9).
- "Stairs" is a command on the stair tile; the unit appears on the other end and **keeps its unused movement** (select
  it again on the arrival tile). The arrival tile must be empty, so each arrival has to step off before the next.
  The command menu order changes: a staff user next to a hurt ally gets Staff first, Stairs second (menu:1).
- Enemies do not move until a unit is in their reach (they never came through the stairs). Then they hit hard:
  Hinata was lost twice and Gunter once in look-aheads (all undone); the B island general, diviner and thief together
  kill a 28 HP unit. The working way: only Corrin and Takumi on an island first, others at tiles out of reach.
- A Spear Fighter illusion made Corrin lose 18 HP on a 6-damage forecast (a counter-type skill [med: not traced]);
  Takumi's Fujin Yumi from range 2 kills them with no counter.
- **Shura** (Adventurer, PID_アシュラ, (27,14), steel bow, Heal staff, 34 HP) doubled Takumi for 30. Corrin next to him
  has **Talk**; he joins at once (A, A, answer presses; Corrin can still Wait after). He then kills almost anything from
  range 2 (generals 13 x 2, the boss 16 + Takumi 18).
- Nyx (Dark Mage, green, appears at (16,30) on turn 2) was left alone (not talked to).
- The two throne-side generals came down on turn 16; one was killed, the other (6 HP) went back to (14,2) and was at
  27 HP the next turn. The boss (Onmyoji, Tiger Spirit) never left the throne. Seize: Corrin on (15,1), Seize, then
  "Seize and finish the battle?" LEFT A (Yes).
- A Chest Key drop filled Corrin's items (ItemMenuSend): UP A sends the key, LEFT A.

### 18.2 Tool findings

- The fastlook rollback bug shows in one-shot mode too: one `act2 end` whose plan rolled back left its passed steps'
  presses in inputs.txt (frames 84838-85746) while state.bin and chain.json stayed at 84828; the next call recorded
  its own presses from 84838 again, so the exported list went back in time. Those two lines were removed
  (inputs.before-fix.txt kept); the two-copy proof below replays the fixed list to the same checkpoints.
- act2's `end` can return on the same free-cursor screen before the turn really ends (seen with 8 units left);
  `c15/end.json` waits 60 frames after "UP A" before looking. act2 gained `plan FILE` (any recorded plan with undo).
- `tools/st.py` (stats = Person.base + Job.base + gain) gives enemy numbers far below what they hit for; not used.

### 18.3 Proof, save, capture

- Route `rv-ch15`: 150,400 frames, save_at 150,390, slot 1, ends in My Castle. Checkpoints (read from the chain's
  own snapshots with `markers`, then met by both proof copies):
  - 10128: turn 1 [9, 30, 0], no pair.
  - 53340: Shura joined (`UnitCommand` after the talk) [10, 25, 1] (the 1 is Nyx, green).
  - 118444: turn 15, islands B, C, D cleared [10, 15, 1].
  - 145020: STAGE COMPLETE (`castle__anonymous_namespace__Seq`).
  - 150268: `castle__Sequence` after the save.
- `parallel.py runs --route rv-ch15 --copies 2 --markers --keep --timeout 3600 --session rv-ch15a`
  (FEF_ROBOT_JOBS=4, FEF_ROBOT_MEM_GB=2.64): both **PASS**, memory **`8d54ceb7be7de6fc`** in both, **checkpoints all
  met**, 772 s / 793 s side by side, peak 367 MB, %APPDATA% unchanged (build/speed/rv15/runs-rv-ch15a.txt).
- Packed: `parallel.py pack rv-ch15a rv-ch15a-1 rv-ch15-clear` -> build/harness/saves/rv-ch15-clear.zip, sha256
  `f616e85c...`.
- Capture `--copies 1 --mode capture --markers --timeout 3600 --session rv-ch15cap` (run beside the proof, the
  library as it stood): **PASS**, memory `8d54ceb7be7de6fc` (the same as the original copies), checkpoints all met,
  138 functions, 3104 records, 3034 match, 42 gave up, 28 incomplete, **0** mismatches of any kind, 0 b_escaped,
  unfaithful, escaped or damaged; no writer stored anything; 723 s (build/speed/rv15/cap-rv-ch15.txt).
- `verified: true` (splitcfg merge through build/speed/rv15/tools/cfg.py).
- Time: from the start of the look-ahead to the packed save, **109 minutes** (epoch 1794766139 -> 1794772649): about
  85 minutes of look-ahead (19 turns; three undone losses: Hinata twice, Gunter once), ~2 minutes for the route and
  checkpoints, 13 minutes for the two proof copies, under 1 minute to pack. The capture ran beside the proof.

### 18.4 State to continue from

`rv-ch15-clear` (My Castle after chapter 15, slot 1; the army of chapter 14 plus Shura; 9 of them plus Shura fought here).
Chapter 16 is not started; start it with a new fastlook chain. Not checked: whether Nyx could have been recruited
here, and who else joins after chapter 15 (the talks were passed with answer presses). Chain `c15`
(`--dir build/speed/rv15`) has 333 recorded write-back breaks; the proof is the two original copies.

## 19. Conquest, round 11 area "cq": chapter 10 cleared from `cq-ch9-clear` (route `cq-ch10`)

**In plain words.** Conquest chapter 10 ("Unhappy Reunion", defend the green zone for 11 turns) was played by a fresh
helper with fastlook from frame 0 of `cq-ch9-clear` (it replays; the first route that loads that save) and **cleared
after turn 11 with nobody lost**. Before the battle the helper built a Staff Store and bought five Heal staves.
Route `cq-ch10` (routes.json, verified), checkpoints `cq-ch10` (markers.json), packed save `cq-ch10-clear`.

### 19.1 What chapter 10 taught [high for what was seen]

- Castle: Castle Menu > Buildings > Build lists Staff Store LV1 for 1 dragon vein point (we had 3). The build
  question defaults to No (A, LEFT A = Yes). Placement starts red over the throne; 6 DOWN, 6 RIGHT was free (blue).
  Touching a building on the bottom map only shows its name; walking is needed: DOWN held 60 frames reached the
  armory, RIGHT 30 frames gave the "A Staff Store" prompt. The store sells Heal 500 G, Mend 1000 G, Freeze 1800 G.
  6000 G -> 3500 G after 3 Heal for Elise (her bag was empty) and 2 Heal for Felicia (she held only an Iron Dagger).
- The map (26 x 22): our pocket is rows 1-13, cols 7-15; the green zone is row 1, cols 10-13 (trick type 4), and row 1
  is building everywhere else, so a wall of four units on (10-13, 2) seals the zone. Enemies come from the west and
  east bridges (rows 12-13), the west bridge on row 3, the open north strip from the east, and sky knights fly in.
  Terrain 4 is sea that the map vein turns into plain: the vein was never used (it would open every approach).
- Every enemy charges, and reinforcements keep coming (37 enemies on the map at turn 8). Camilla, Selena and Beruka
  join at (11-13, 4) at the start of turn 3.
- The win screen after Fight needs one A; the turn-1 ballista tutorial is answered.
- Pairing: moving onto an unacted ally shows a preview and A pairs (the ally stays lead); onto an ally that already
  acted it does nothing. The Pair Up command (adjacent) pairs too and the TARGET stays lead. Switch keeps the command
  menu open, so the new lead can still attack (Odin killed a spear fighter after Silas fell to 10 HP).
- The game ends the player phase by itself when the last unit acts; a tool must wait through the enemy phase then.
- Row-1 healers are hit only from range 2 (the row-3 tile below them, and (9,2)/(14,2) for the corners). Elise at
  11 HP and Azura at 16 HP each died once in a look-ahead (both undone, not kept); after that Azura rode as Elise's
  partner and the healer stood where the row-3 tile below was held by a melee enemy.
- Camilla's Thunder (range 1-2) one-shot 26-HP oni Savages; Arthur's Hand Axe and Odin's Thunder finish at range 2.
  Corrin fell to 11 HP in one enemy phase on turn 9 (healed); Arthur ended at 3 HP in the last enemy phase.
- Grok's tracks/ROUTES_CQ_RV.md checked: 11 turns, Camilla/Selena/Beruka join, do not use the vein: as written.
  "Takumi is the boss": the boss is an archer (PID_B010_ボス) at (2,21) who never moved; never fought.

### 19.2 Tool notes (untracked, build/speed/cq10/tools/, copied from bt17)

- act2.py now homes the cursor to the play corner (1,1) before every action (LEFT/UP past the edge) instead of
  trusting the last cursor read: twice a stale read made the wrong unit move. Added a `pair` action; enemy-phase waits
  raised to 12000 frames (auto end turn). One-shot fastlook calls only (no `serve`, so no rollback press loss).

### 19.3 Proof, save, capture

- Chain **`c10`** (`--dir build/speed/cq10`), 159,880 frames, 1,855 presses; route `cq-ch10`: frames 160,000,
  save_at 159,990, slot 1, ends in My Castle.
- `parallel.py runs --route cq-ch10 --copies 2 --markers --keep --timeout 3600 --session cq10a` (FEF_ROBOT_JOBS=4,
  FEF_ROBOT_MEM_GB=2.64, below normal): both **PASS**, 160,000 frames, memory **`875e00805db01da9`** in both, the two
  copies' marker reads equal, 1,234 s / 1,238 s side by side, peak 495 MB, %APPDATA% unchanged.
- Checkpoints (markers.json `cq-ch10`, splitcfg.py `marks`, read from that proof): 12524 shop screen, gold 3500;
  19074 turn 1 [10, 19, 0]; 29664 turn 3 [13, 21, 0], 6 paired; 91622 turn 8 [13, 37, 0]; 127452 turn 10 [13, 26, 0];
  157132 stage complete (`map__SequenceCompleteEffect`) [13, 19, 0]; 159426 the save question (`GameDialogYesNo`,
  chapter now B011); 159800 `castle__Sequence`. All route byte 1.
- Packed: `parallel.py pack cq10a cq10a-1 cq-ch10-clear` -> build/harness/saves/cq-ch10-clear.zip, sha256
  `03a961f8...`; Chapter0 and Global differ from cq-ch9-clear (the slot-1 save happened).
- Capture `--copies 1 --mode capture --markers --timeout 3600 --session cq10cap`: **PASS**, memory `875e00805db01da9`
  (equal to the original copies), checkpoints all met, 150 functions, 3,413 records, 3,337 match, 47 gave up,
  29 incomplete, **0** mismatch of r0 / regs / mem / calls, 0 b_escaped, unfaithful, escaped, damaged; no writer
  stored anything; 701 s (cap-cq10.txt). `verified: true` (splitcfg.py `route`).
- Time: start of the look-ahead (with the castle shop) to the packed save **106 minutes** (13:09 to 14:55): about
  64 min look-ahead (11 turns; two undone losses; cursor and menu surprises), 21 min the two proof copies, under
  1 min to pack. Capture 12 min after that.

### 19.4 State to continue from

`cq-ch10-clear` (My Castle after chapter 10, slot 1, 3500 G; Elise and Felicia carry Heal staves). Chapter 11 is
not started; start it with a new fastlook chain.

## 20. Revelation, round 11 area "rv": chapter 16 cleared from `rv-ch15-clear` (route `rv-ch16`)

**In plain words.** Two fresh helpers. The first played Revelation chapter 16 with a fastlook chain (`c16`,
`--dir build/speed/rv16`) from frame 0 of `rv-ch15-clear` (it replays; no drift seen): Ryoma defeated the boss Hans
(Berserker at (26,1)) on turn 10, **nobody lost** (15 units). Its proof runs were cut off when it returned. The second
helper re-ran the proof, packed, captured and set `verified: true`. Route `rv-ch16` (routes.json), checkpoints
`rv-ch16` (markers.json), packed save `rv-ch16-clear`, which is a **chapter 17 turn-1 battle save**, not a castle save.

### 20.1 What chapter 16 taught [high for what was seen]

- Start: title > Continue > "Jakob joined" message (one A) > castle > START > Next Battle > Chapter 16 > events (answer
  presses) > Preparations (default 10 plus Ryoma, Hinoka, Asama, Setsuna, Scarlet already placed) > Fight.
- The walls are flame walls / canyons (trick type 12) that change state by themselves from turn to turn. The 20
  type-11 tiles are dragon veins; none were used. Most enemies stay put until provoked.
- Ryoma's Raijinto at range 2 one-rounds generals and berserkers with no counter; the boss forecast was 100% hit,
  0% back, lethal. Scarlet's counters killed both armor knights on turn 1.
- Two undone tries (Gunter, Scarlet) went badly and were rolled back; no kept line lost anyone.
- **No My Castle and no chapter save between chapters 16 and 17**: the game goes straight to chapter 17
  Preparations, whose menu has no Save item. The route Fights into chapter 17 (the default 10 units) and makes a
  battle save on turn 1: system menu > Save > slot 1 > Yes. It is written as extra data (`extdata/.../Map0.bak`);
  `Chapter0` stays the chapter-15 castle save.
- In the look-ahead server (boot-server.exe) that battle save fails with an "SD Card" message (its data folder has no
  extdata); the original boot.exe copies write it. Battle saves cannot be checked in fastlook.

### 20.2 Tool findings

- act2 `end` once returned on a stale cursor without ending the turn; the rv16 act2 now requires the system menu to
  open before it continues. Scratch tools in build/speed/rv16/tools: th2.py (map and threats using the live wall
  states), mp.py, ls.py. The press list (2,281 presses) was checked to be in frame order before proving.

### 20.3 Proof, save, capture

- Route `rv-ch16`: 124,600 frames, save_at 124,590. Checkpoints: 17468 turn 1 [15, 31, 0]; 55258 turn 5 [15, 20, 0];
  94415 turn 8 [15, 13, 0]; 117489 turn 10 [15, 9, 0]; 119677 STAGE COMPLETE; 122279 chapter 17 Preparations
  (`sortie TopMenu`); 123201 chapter 17 turn 1 [10, 23, 0]; 123625 the battle save's Yes/No question.
- First try (session rv-ch16a, rv-ch16cap) was started by the first helper and died with it: no result.
- `parallel.py runs --route rv-ch16 --copies 2 --markers --keep --timeout 3600 --session rv-ch16b`
  (FEF_ROBOT_JOBS=4, FEF_ROBOT_MEM_GB=2.64): both **PASS**, memory **`bfc9db068b3e90d6`** in both, **checkpoints all
  met**, 562 s / 564 s side by side, peak 541 MB, %APPDATA% unchanged (build/speed/rv16/runs-rv-ch16b.txt). Map0.bak
  was written in the job folder at the end of the run.
- Packed: `parallel.py pack rv-ch16b rv-ch16b-1 rv-ch16-clear extdata` -> build/harness/saves/rv-ch16-clear.zip,
  sha256 `da17b636...`, members: savedata (Chapter0, Exchange, Global, Rating, .format) and extdata
  (`0000000000001794.format`, `Map0.bak`, `Map0.bak^`).
- Capture `--copies 1 --mode capture --markers --timeout 3600 --session rv-ch16cap2` (beside the proof): **PASS**,
  memory `bfc9db068b3e90d6` (same as the original copies), checkpoints all met, 139 functions, 3044 records, 2977
  match, 41 gave up, 26 incomplete, **0** mismatches of any kind, 0 b_escaped, unfaithful, escaped or damaged; no
  writer stored anything; 571 s (build/speed/rv16/cap-rv-ch16b.txt).
- `verified: true` (splitcfg merge through build/speed/rv16/tools/cfg.py).
- Time: the first helper reported 112 minutes from the start of the look-ahead to its proof launch; the second
  helper took 10 minutes to re-run the proof and pack (capture beside it). About 122 minutes in all.

### 20.4 State to continue from

`rv-ch16-clear`: a battle save on chapter 17 turn 1 (slot 1; default 10 units deployed, 23 enemies). **Not checked:**
how this save is resumed (title > Continue should offer the battle save; the first chapter 17 helper must confirm
it reaches the chapter 17 map at turn 1 and not the chapter-15 castle in `Chapter0`). Owner question: is a battle
save acceptable as a chapter-clear save here, since chapter 16 offers no chapter save?

## 21. Conquest, round 11 area "cq": chapter 11 cleared from `cq-ch10-clear` (route `cq-ch11`)

**In plain words.** Conquest chapter 11 ("Rainbow Sage", defeat the boss Hinoka) was played by a fresh helper with
fastlook one-shot calls from frame 0 of `cq-ch10-clear` and **cleared on turn 18 with nobody lost** (11 units
deployed, all 11 kept). Route `cq-ch11` (routes.json, verified), checkpoints `cq-ch11` (markers.json), packed save
`cq-ch11-clear`. No castle shopping: Elise and Felicia still carried five Heal staves (11-20 uses each).

### 21.1 What chapter 11 taught [high for what was seen]

- It is the same 30 x 30 rooftop map as Revelation chapter 15 (section 18.1): islands joined by one-tile stairs.
  Conquest's win rule is "Defeat the boss" (the rule screen needs one A). Enemies: Hinoka (sky knight, Steel
  Nageyari 1-2) with two Bolt Naginata sky knights, one Iron Naginata sky knight and a shrine maiden on the top
  island; three paired samurai on the middle island; Azama (Monk, Hexing Rod) and three diviners east; Rinkah and
  three oni south-east; Setsuna and three archers south-west; Kaze and three ninja west. The east way was taken.
- Stairs: "Stairs" is the first command; the unit lands on the far tile with its unused movement but may then only
  move, trade, pair or wait (no attack, no staff). The landing tile must be empty. Stairs work both ways.
- Nobody flies over the gaps (Camilla could not; the sky knights never left their island).
- Rinkah and the top island never moved; the oni, diviners and samurai came once a unit was in reach.
- Azama's Hexing Rod (range across most of the island) halves a unit's **maximum** HP for the rest of the map:
  Corrin stayed at 18, Camilla at 15, Arthur at 19, and Heal is not even offered on them (only on real damage).
- Camilla's Thunder (14 x 2) one-shot oni and diviners from range 2 and took little back; on Hinoka it did 1.
  The samurai island was held from the arrival corner (19,18) (only two tiles touch it): Camilla + Nyx (dual guard)
  killed the pairs on counters and player phases over turns 9-15. One 80% Thunder missed twice; retrying the same
  action gives the same miss (the random numbers do not depend on frame timing), Switch to Nyx changed it.
- Top island: Niles (Iron Bow, from Arthur's pair by Switch) killed a Bolt Naginata knight from range 2 (97%);
  Effie (with Arthur's Attack support) took Hinoka 32 -> 15, Corrin's Dragonstone 15 -> 2, Silas finished (71%).
  The stage ends at once when Hinoka falls.

### 21.2 Tool notes (untracked, build/speed/cq11/tools/, copied from cq10)

- act2.py as in cq10 (cursor homed to (1,1) before every action). Homing costs ~2,000 frames per action on this
  30 x 30 map, hence the long route. Several plans stopped (a move out of range, a wrong menu index) and were undone
  with act2's own snapshots; the exported press list was checked: all 15,331 presses in rising frame order, and the
  two original copies replayed it to the same memory.

### 21.3 Proof, save, capture

- Chain **`c11`** (`--dir build/speed/cq11`), 357,047 frames, 15,331 presses; route `cq-ch11`: frames 357,000,
  save_at 356,990, slot 1, ends in My Castle.
- `parallel.py runs --route cq-ch11 --copies 2 --markers --keep --timeout 5400 --session cq11a` (FEF_ROBOT_JOBS=4,
  FEF_ROBOT_MEM_GB=2.64, below normal): both **PASS**, 357,000 frames, memory **`52154ebff72f0b57`** in both, the two
  copies' marker reads equal, 1,076 s / 1,080 s side by side, peak 491 MB, %APPDATA% unchanged.
- Checkpoints (markers.json `cq-ch11`, splitcfg.py `marks`, read from that proof): 9564 preparations, gold 3500,
  [11, 27, 0]; 10966 turn 1 [11, 27, 0]; 105688 oni island cleared [11, 23, 0], 4 paired; 221534 turn 9, diviner
  island cleared [11, 19, 0]; 299927 turn 16, samurai island cleared [11, 13, 0]; 350209 stage complete
  (`map__SequenceCompleteEffect`) [11, 11, 0]; 356483 the save question (`GameDialogYesNo`, chapter now B012);
  356900 `castle__Sequence`. All route byte 1.
- Packed: `parallel.py pack cq11a cq11a-1 cq-ch11-clear` -> build/harness/saves/cq-ch11-clear.zip, sha256
  `e1155d25...`; Chapter0 and Global differ from cq-ch10-clear (the slot-1 save happened).
- Capture `--copies 1 --mode capture --markers --timeout 5400 --session cq11cap` (run beside the proof, before the
  checkpoints were written): **PASS**, memory `52154ebff72f0b57` (equal to the original copies), its marker reads at
  all eight shots equal the checkpoints above (compared by script), 144 functions, 3,274 records, 3,195 match,
  48 gave up, 31 incomplete, **0** mismatch of r0 / regs / mem / calls, 0 b_escaped, unfaithful, escaped, damaged;
  no writer stored anything; 1,095 s (cap-cq11.txt). `verified: true` (splitcfg.py `route`).
- Time: start of the look-ahead to the packed save **108 minutes** (epoch 1794774629 -> 1794781125): about 88 min
  look-ahead (18 turns; no unit ever lost, several forecast checks undone), 18 min the two proof copies (capture
  beside them), under 1 min to pack.

### 21.4 State to continue from

`cq-ch11-clear` (My Castle after chapter 11, slot 1, 3500 G; the same 14 units; Elise and Felicia carry Heal staves).
Chapter 12 is not started; start it with a new fastlook chain.

## 22. Revelation, round 11 area "rv": chapter 17 cleared from `rv-ch16-clear` (route `rv-ch17`)

**In plain words.** One fresh helper played Revelation chapter 17 ("Black Flames", seize; boss Iago, a Sorcerer with
Fimbulvetr on the throne at (8,24)) with a fastlook chain (`c17`, `--dir build/speed/rv17`) from frame 0 of the battle
save `rv-ch16-clear`. Xander and Leo killed Iago on turn 16; on turn 18 Peri, carrying Corrin, seized. **Nobody lost**
(16 units). Route `rv-ch17` (routes.json, verified), checkpoints `rv-ch17` (markers.json), packed save `rv-ch17-clear`
(My Castle after chapter 17, slot 1).

### 22.1 What chapter 17 taught [high for what was seen]

- **The battle save resumes:** title > Continue (A) > "Battle Save" is already selected (A) > slot 1 "Chapter 17: Black
  Flames, Turn 1, Casual" (A) > the chapter 17 map at turn 1, free cursor at frame 1856 (10 units, 23 enemies). It does
  not load the chapter-15 castle save in `Chapter0`. This answers the open question in 20.4.
- Map 18 x 24. Terrain ids: 1 plain, 2 forest, 3 high mountain and 4 cliff (no walking), 5 bridge, 6 fort (costs 2; the
  throne is also id 6), 7 bow ballista (14,24) and (1,24), 8 magic turret (8,18).
- Turn 2 Xander (Paladin, Siegfried) and Leo (Dark Knight, Brynhildr) join at (11,1)/(13,1); turn 3 Odin, Laslow, Peri,
  Niles join at (10,1)-(13,2). Big cavalry reinforcement waves come from the east; armor knights and generals on the west.
- Holding the 3-wide gap (9,1)-(9,3) (mountains at (8,4),(9,4)) let only one enemy hit each wall unit. Xander (Def 23)
  takes 0-2 from cavaliers and paladins and kills most of them on counters.
- Most enemies near the boss stood still until our units came close; then the generals at (6,24)/(10,24)/(3,21) did move
  (one stepped onto the throne after Iago died and had to be killed).
- The turrets fire on the enemy phase with no unit on them: once a 3 x 3 magic blast hit three units at (13,19), (14,18)
  and (15,18) for 11-14 each; the ballista hit single units at distance 6-7 for about 9. Not every enemy phase.
- Corrin's first weapon was the Dragonstone (it hits Res); Y on the forecast cycles weapons (Dragonstone > Alpha Yato >
  Silver Sword). Sakura's Mend broke on turn 3; Shura (Heal) was the only healer after that.
- A unit carrying Corrin can Seize: Peri (lead) with Corrin as support moved onto the throne and the menu showed Seize.
  "Switch" is a post-move command and B undoes it.
- After STAGE COMPLETE the summary screen needs one A; then about 210 answer presses of story, the save slot screen
  (`ChapterFileMenu`), slot 1 > "Save your progress?" Yes (LEFT A) > My Castle.

### 22.2 Tool findings

- **Auto end turn:** when the last unit acts, the enemy phase starts by itself. act2's `until` then returns on the next
  player phase; calling `end` after that ends the next turn with no moves. This happened once (turn 11 -> 12): Gunter
  and Azura were then killed in the empty turn 12; the lost line was rolled back to the turn 12 start (nobody lost on the
  kept line). Keep one unit unacted and end with `end`, or do not call `end` after the last unit.
- act2.py `undo` took `sorted(listdir(hist))[-1]`, which is `hist/_tools` (fastlook's scratch) once that exists: it then
  restored nothing. The rv17 copy now uses only numbered folders (also for new snapshot numbers).
- Scratch tools in build/speed/rv17/tools: th17.py (threat map with this map's move costs), r17.py (reach of a player
  unit), b.sh, plus the rv16 set adapted. The press list (3,181 presses) was checked to be in frame order, no duplicates.

### 22.3 Proof, save, capture

- Route `rv-ch17`: 174,500 frames, save_at 174,490. Checkpoints: 1856 turn 1 [10, 23, 0]; 4216 turn 2 [12, 36, 0];
  40314 turn 5 [16, 28, 0] pairs 2; 81646 turn 9 [16, 21, 0]; 109446 turn 11 [16, 17, 0]; 153850 turn 16 [16, 12, 0]
  pairs 4; 168148 turn 18 [16, 9, 0]; 170232 STAGE COMPLETE; 173636 the save question (`GameDialogYesNo`); 173820
  `castle__Sequence`.
- `parallel.py runs --route rv-ch17 --copies 2 --markers --keep --timeout 3600 --session rv-ch17a` (FEF_ROBOT_JOBS=4,
  FEF_ROBOT_MEM_GB=2.64): both **PASS**, memory **`8b67f81a0a24d605`** in both, checkpoints all met, 810 s / 814 s,
  peak 590 MB, %APPDATA% unchanged (build/speed/rv17/runs-rv-ch17a.txt).
- Packed: `parallel.py pack rv-ch17a rv-ch17a-1 rv-ch17-clear` -> build/harness/saves/rv-ch17-clear.zip, sha256
  `f0a3c7e8...`; savedata only; Chapter0 and Global differ from rv-ch16-clear (the slot-1 save happened).
- Capture `--copies 1 --mode capture --markers --timeout 3600 --session rv-ch17cap` (beside the proof): **PASS**, memory
  `8b67f81a0a24d605`, checkpoints all met, 144 functions, 3335 records, 3275 match, 43 gave up, 17 incomplete, **0**
  mismatches of any kind, 0 b_escaped, unfaithful, escaped or damaged; no writer stored anything; 825 s
  (build/speed/rv17/cap-rv-ch17.txt).
- `verified: true` (splitcfg merge through build/speed/rv17/tools/cfg.py).
- Time: 16:36 (start of the look-ahead) to 18:26 (packed save): **110 minutes**.

### 22.4 State to continue from

`rv-ch17-clear` (My Castle after chapter 17, slot 1; 16 units; Shura carries the only Heal staff, Sakura has none).
Chapter 18 is not started; start it with a new fastlook chain.

## 23. Conquest, round 12 area "cq": chapter 12 cleared from `cq-ch11-clear` (route `cq-ch12`)

**In plain words.** Conquest chapter 12 ("Bitter Intrigue": defeat Ryoma, or Corrin escapes, within 16 turns) was
played by a fresh helper with fastlook one-shot calls from frame 0 of `cq-ch11-clear`, and **Corrin escaped on turn
16 with nobody lost** (13 units deployed, all 13 kept). Route `cq-ch12` (routes.json, verified), checkpoints
`cq-ch12` (markers.json), packed save `cq-ch12-clear`. No castle shopping (Felicia still had two Heal staves).
Game difficulty on the save screen: Casual.

### 23.1 What chapter 12 taught [high for what was seen]

- Map 19 x 28 (castle). Terrain read: plain, woods, lake, wall, floor, stairs, pillar, door, chest, and four pot
  kinds (medicine / poison, each on plain or floor). Pots block movement. Every exit of every room is shut by a
  pot: the start room's ways are (4,24) behind a poison pot, (9,24) behind the medicine pot (9,25), and (16,24).
  The escape tiles are (9,1), (10,1), (11,1) (trick type 8) beside Ryoma at (10,2), shut by pots too.
- "Break" is a command on a unit next to a pot (or within range 2 with Thunder). Breaking a medicine pot heals units
  within 2 tiles (both sides). A pot broken by an attack has trick state 4; by the vein, state 2.
- Dragon vein tiles (type 11) at (10,14) and (10,11). Camilla used (10,14) on turn 7: every pot on the map broke.
  Enemies near poison pots lost HP and had their **maximum HP halved** (a spear fighter showed 13/13).
- Enemies wait until a unit is within their reach. Saizo and Kagero (paired ninjas) hit very hard (25 to full Corrin
  at range 2; they killed an 18 HP Effie in a look-ahead). The four apothecaries carry **Steel / Iron Yumi** (bows,
  range 2 only, effective on Camilla): they killed Camilla and Peri in one look-ahead. Bows cannot answer at range 1,
  so they were killed only by melee attacks (Camilla axe, Arthur, Silas).
- Reinforcements: six units appear at the bottom corners (1-2,27-28) and (18-19,27-28) on turn 14; never met.
- Ryoma never moved, even with Camilla three tiles away. The two samurai at (9,3) and (11,3) guard the way; the
  last one was killed on turn 16 (Peri from (10,3), Arthur's Hand Axe from (11,5)); then Corrin walked
  (11,6) > (11,5) > (11,4) > (11,3) > (11,2) > (11,1) and chose Escape > Yes: stage complete at once.
- Retrying the same attack gives the same miss; doing another battle first (Peri on the shrine maiden) changed it.

### 23.2 Tool notes (untracked, build/speed/cq12/tools/, copied from cq11)

- act2.py as in cq11. New scratch tools: thr2.py (threat per tile with this map's costs; reads broken pots from the
  tricks), tmap.py (threat-count map; `--only` a job), ppot.py (units near pots), tn.py (markers of state.bin).
- **Pitfall found:** bd.sh copied from cq11 still ran cq11's rb.py (no tricks) and overwrote rb.json, so some
  threat reads treated broken pots as walls. Fixed mid-chapter; check the rb.py path when copying bd.sh.
- No `serve`, so no rollback press loss; the exported press list (8,956 presses, rising frames) replayed on both
  original copies to the same memory.

### 23.3 Proof, save, capture

- Chain **`c12`** (`--dir build/speed/cq12`), 260,937 frames, 8,956 presses; route `cq-ch12`: frames 261,000,
  save_at 260,990, slot 1, ends in My Castle.
- `parallel.py runs --route cq-ch12 --copies 2 --markers --keep --timeout 3600 --session cq12a` (FEF_ROBOT_JOBS=4,
  FEF_ROBOT_MEM_GB=2.64, below normal): both **PASS**, 261,000 frames, memory **`0dbf6a282590f10c`** in both, the two
  copies' marker reads equal, 896 s / 908 s side by side, peak 495 MB, %APPDATA% unchanged.
- Checkpoints (markers.json `cq-ch12`, splitcfg.py `marks`, read from that proof): 13666 preparations, gold 3500,
  [13, 31, 0]; 14858 turn 1 [13, 31, 0]; 131758 turn 7 after the vein [13, 24, 0]; 166904 turn 11 [13, 22, 0];
  229298 turn 15 [13, 19, 0]; 256947 stage complete [12, 16, 0] (Corrin has left the map); 259590 the save slot
  menu (chapter now B013); 260900 `castle__Sequence`. All route byte 1.
- Packed: `parallel.py pack cq12a cq12a-1 cq-ch12-clear` -> build/harness/saves/cq-ch12-clear.zip, sha256
  `d9977efd...`.
- Capture `--copies 1 --mode capture --markers --timeout 3600 --session cq12cap` (beside the proof): **PASS**, memory
  `0dbf6a282590f10c`, 146 functions, 3,362 records, 3,287 match, 49 gave up, 26 incomplete, **0** mismatch of r0 /
  regs / mem / calls, 0 b_escaped, unfaithful, escaped, damaged; no writer stored anything; 918 s (cap-cq12.txt).
- Second capture with the checkpoints written (`--session cq12cap2`, --keep): **PASS, checkpoints all met**, same
  memory, the same 146 functions / 3,362 records, **0 bad of any kind**, no writer stored anything; 678 s
  (cap2-cq12.txt). `verified: true` (splitcfg.py `route`).
- Time: start of the look-ahead to the packed save **123 minutes** (epoch 1794781448 -> 1794788822): about 105 min
  look-ahead (16 turns; three look-ahead losses undone: Effie on turn 5, Camilla and Peri on turn 10), 15 min the
  two proof copies (capture beside them), under 1 min to pack.

### 23.4 State to continue from

`cq-ch12-clear` (My Castle after chapter 12, slot 1, 3500 G; the same units, Felicia carries two Heal staves,
Elise was not deployed). Chapter 13 is not started; start it with a new fastlook chain.

## 24. Conquest, round 20 area "cq": chapter 14 played from `cq-ch13-clear` (route `cq-ch14`)

F-031, real play (no pokes, no cheat save). Chain `c14` (`--dir build/speed/cq14`), 117,050 frames, 2,042 presses:
chapter 14 'Voice of Paradise', boss Kumagera beaten by Leo and Camilla, **12 of 12 units, nobody lost**, Keaton
(green) alive, save slot 1, castle. Route `cq-ch14` (routes.json, `verified: false`) and checkpoints `cq-ch14`
(markers.json, 10 frames from preparations 7666 to the castle 117050) written; the export replays from frame 0 to the
chain's own instruction count (524516968800). Details: docs/ROBOT.md 3z-cq14. Not done here: the two-copy proof, the
pack of `cq-ch14-clear` and the capture (a separate step). Next: chapter 15 from `cq-ch14-clear` once packed.

## 25. Revelation, round 20 area "rv": chapter 20 played from `rv-ch19-clear` (route `rv-ch20`)

F-031, real play (no pokes, no cheat save). Chain `c20` (`--dir build/speed/rv20`), 97,520 frames, 1,521 presses:
chapter 20 'Seeds of Doubt' (floating isles; Dragon Veins move the bridges and the units on them), boss (fixed at
(1,1)) beaten by Xander on turn 17, **8 of 8 units, nobody lost**, save slot 1, castle. Route `rv-ch20` (routes.json,
`verified: false`) and checkpoints `rv-ch20` (markers.json, 10 frames from preparations 7536 to the castle 97500)
written; the export replays from frame 0 to the chain's own instruction count (437000382720). Details: docs/ROBOT.md
(rv-ch20). Not done here: the two-copy proof, the pack of `rv-ch20-clear` and the capture (a separate step). Next:
chapter 21 from `rv-ch20-clear` once packed (not the Endgame: C021 leads on to C022).

## 26. Conquest, round 20 area "cq": chapter 15 played from `cq-ch14-clear` (route `cq-ch15`)

F-031, real play (no pokes, no cheat save). Chain `c15` (`--dir build/speed/cq15`), 78,366 frames, 814 presses:
chapter 15 'The Black Pillar' (defeat the boss or all escape; only Corrin, Azura and Gunter), the north enemies baited
and killed, Azura paired with Gunter, Gunter + Azura escape on (30,5) on turn 11 and Corrin on (30,6) on turn 12,
**3 of 3 escaped, nobody lost**, save slot 1, Lilith's talk, castle. Route `cq-ch15` (routes.json, `verified: false`)
and checkpoints `cq-ch15` (markers.json, 10 frames from preparations 10426 to the castle 78366) written; the export
replays from frame 0 to the chain's own instruction count (351168703776). Details: docs/ROBOT.md 3z-cq15. Not done
here: the two-copy proof, the pack of `cq-ch15-clear` and the capture (a separate step). Next: chapter 16 from
`cq-ch15-clear` once packed (not the Endgame: the castle follows chapter 15).

## 27. Revelation, round 24 area "rv": chapter 21 played from `rv-ch20-clear` (route `rv-ch21`)

F-031, real play (no pokes, no cheat save). Chain `c21` (`--dir build/speed/rv21`), 118,150 frames, 1,758 presses:
chapter 21 'Going Forward' (map C021, underground rooms joined by doorways; reinforcements step out of stair tiles),
boss (Faceless 'Anthony', area AI) beaten by Xander on turn 15, **8 of 8 units, nobody lost**, save slot 1, castle.
Route `rv-ch21` (routes.json, `verified: false`) and checkpoints `rv-ch21` (markers.json, 10 frames from
preparations 9892 to the castle 118130) written; the export replays from frame 0 to the chain's own instruction count
(529446218400). Details: docs/ROBOT.md (rv-ch21). Not done here: the two-copy proof, the pack of `rv-ch21-clear` and
the capture (a separate step). Next: chapter 22 from `rv-ch21-clear` once packed (not the Endgame: C021 leads on to
C022).

## 28. Conquest, round 24 area "cq": chapter 16 played from `cq-ch15-clear` (route `cq-ch16`)

F-031, real play (no pokes, no cheat save). Chain `c16` (`--dir build/speed/cq16`), 168,550 frames, 3,108 presses:
chapter 16 'Invasion' (ship deck, B016; the boss is hidden among four green suspects: the fourth one talked to becomes
Shura), the enemies cleared west then east, suspects talked to on turns 6, 9, 14 and 21, Shura beaten by Xander and
Harold on turn 21, **13 of 13, nobody lost** (one turn-13 bait that lost Gunter was undone in the look-ahead), save
slot 1, castle. Route `cq-ch16` (routes.json, `verified: false`) and checkpoints `cq-ch16` (markers.json, 11 frames
from preparations 13140 to the castle 168550) written; the export replays from frame 0 to the chain's own
instruction count (755295472800). Details: docs/ROBOT.md 3z-cq16. Not done here: the two-copy proof, the pack of
`cq-ch16-clear` and the capture (a separate step). Next: chapter 17 from `cq-ch16-clear` once packed (not the
Endgame: the castle follows chapter 16).

## 29. Revelation, round 24 area "rv": chapter 22 played from `rv-ch21-clear` (route `rv-ch22`)

F-031, real play (no pokes, no cheat save). Chain `c22` (`--dir build/speed/rv22`), 91,060 frames, 1,452 presses:
chapter 22 'Memories' (map C022, Seize; plain paths through thick wood that only fliers cross), the boss (Strategist
'Arete', never moves, carries Silence) killed by Ryoma, Corrin seized (24,13) on the game's turn 15, **8 of 8 units,
nobody lost**, save slot 1, castle. Route `rv-ch22` (routes.json, `verified: false`) and checkpoints `rv-ch22`
(markers.json, 11 frames from preparations 6742 to the castle 91040) written; the export replays from frame 0 to the
chain's own instruction count (408052244160). Details: docs/ROBOT.md (rv-ch22). Not done here: the two-copy proof,
the pack of `rv-ch22-clear` and the capture (a separate step). Next: chapter 23 from `rv-ch22-clear` once packed (not
the Endgame: C022 leads on to C023).

## 30. Conquest, round 24 area "cq": chapter 17 from `cq-ch16-clear`, NOT cleared (no route key)

F-031, real play (no pokes, no cheat save). Chain `c17` (`--dir build/speed/cq17`) reached turn 19 player phase,
frame 144,711 (1,804 presses, export build/speed/cq17/c17-t19-export.json, not replay-checked), **nobody lost**:
chapter 17 'Den of Betrayal' (B017, defeat the boss Kotaro). Kotaro is at 16/38 on his throne; every turn-19 try to
finish him lost Camilla (1 HP) or missed with Xander and was undone. No route `cq-ch17` and no checkpoints were
written. Details: docs/ROBOT.md 3z-cq17. Next: continue chain c17 (heal Camilla out of his reach first).
Continuation (session c17b, 20 min): the export **replays to the chain's state** (instruction count 648469671696 at
144711); three more Xander tries and one Camilla axe try on turn 19 failed the same way and were undone; the turn-19
battle results look fixed whatever is done first; Kotaro has no Vantage (PersonChapter B017). Still NOT cleared, no
route key. Details: docs/ROBOT.md 3z-cq17b.

## 31. Revelation, round 24 area "rv": chapter 23 played from `rv-ch22-clear` (route `rv-ch23`)

F-031, real play (no pokes, no cheat save). Chain `c23` (`--dir build/speed/rv23`), 200,032 frames, 2,743 presses:
chapter 23 (map C023, `Btl_CastleInvisible_Front`, Seize at (1,1)): floating islands joined by five moving 2x2 blocks
that swap position at every player phase start from turn 2 and carry whoever stands on them. Ryoma killed the boss
(Arete) on turn 28, Corrin seized (1,1) on turn 29, **8 of 8 units, nobody lost** (one turn-21 try lost Takumi and was
undone), save slot 1, castle. Route `rv-ch23` (routes.json, `verified: false`) and checkpoints `rv-ch23`
(markers.json, preparations 6592 to the castle 200012) written; the export was replayed from frame 0 (see
docs/ROBOT.md rv-ch23 for the result). Not done here: the two-copy proof, the pack of `rv-ch23-clear` and the capture
(a separate step). Next: chapter 24 from `rv-ch23-clear` once packed (not the Endgame: C023 leads on to the castle).

## 32. Revelation, round 24 area "rv": chapter 24 played from `rv-ch23-clear` (route `rv-ch24`)

F-031, real play (no pokes, no cheat save). Chain `c24` (`--dir build/speed/rv24`), 149,234 frames, 2,669 presses:
chapter 24 'Days Lost' (map C024, `Btl_CastleInvisible_Dungeon`, defeat the boss): a dark dungeon lit door by door,
patrols that raise alarm waves, and two door pairs where the blue door is right and the red one hurts every unit
(tried once, undone). Xander held two doorways, Elise healed him with Mend from the convoy, Xander opened the boss
door (16,2), Leo killed the Oni Chieftain and Ryoma killed the boss (Mikoto's phantom) on turn 24, **8 of 8 units,
nobody lost** (two tries that lost Leo, and Shura, were undone), save slot 1, castle. Route `rv-ch24` (routes.json,
`verified: false`) and checkpoints `rv-ch24` (markers.json, preparations 9022 to the castle 149234) written; the
export was replayed from frame 0 and reached the chain's instruction count (see docs/ROBOT.md rv-ch24). Not done
here: the two-copy proof, the pack of `rv-ch24-clear` and the capture (a separate step). Next: chapter 25 from
`rv-ch24-clear` once packed (not the Endgame: C024 leads on to the castle, chapter id C025).

## 33. Round 24 integrate: proofs of sections 27, 28, 29, 31 and 32

All five routes passed the two-copy proof (same memory in both copies, every checkpoint met), their clear saves are
packed and `verified` is true: `rv-ch21` (4982b7be624bfff5), `cq-ch16` (944e6ad3cb505d60), `rv-ch22`
(88035f6e3c200c70), `rv-ch23` (d9a2fff8178d8c4e), `rv-ch24` (40ce706031026a9e). Integrate played all five live with
every override (session r24-capn): 20,010 records, 0 bad, every memory equal to its proof. The "not done here" lines
in those sections are now done. Section 30 (`cq-ch17`) stays without a route key. Details: docs/ROBOT.md "Round 24
integrate".

## 34. Revelation, round 30 area "rv": chapter 25 from `rv-ch24-clear`, NOT cleared (no route key)

F-031, real play (no pokes, no cheat save). Chain `c25` (`--dir build/speed/rv25`), stopped at turn 33, frame 166,789,
2,626 presses, **6 of 6 units alive** (Corrin, Takumi, Shura, Xander, Leo, Ryoma; tries that lost Ryoma, Takumi and
Corrin were undone). Chapter 25 'Blades Drawn' (map C025, defeat the boss): moving floors carry units between rooms
each turn, and the boss room only moves into reach after all three dragon veins are used. Two veins used ((7,13)
Ryoma, (6,25) Leo); left: the north vein (6,1) behind a Spear Master, two Master Ninjas and Reinforce03, then the boss
room. Stopped at about 63 minutes because that could not fit the 100-minute cap. No routes.json / markers.json key
written. Details and map mechanics: docs/ROBOT.md "Round 30: Revelation chapter 25".

Continuation (second helper, about 21 minutes): turns 33-38 played on the same chain, nothing lost. The third vein (6,1) is
used and the whole north and north-east are cleared. The chain is at turn 39, frame 216,699, still with no route key. The
line is a dead end for Leo, though: he is alone on the vein tile (6,25) with 7 HP, and two Basaras (Reinforce02) stand
at the only exit. The turn-33 state is kept in build/speed/rv25/c25_t33_backup. Next: from that backup, make Leo safe
before the third vein, then repeat the north plan.

## 35. Revelation, area "rv": chapter 25 cleared from the turn-33 backup (route `rv-ch25`)

F-031, real play (no pokes, no cheat save). A third fresh helper worked on a copy of section 34's turn-33 state (chain
`c25`, `--dir build/speed/rv25b`; round 30's chains were not changed). Leo left the dead end before the third vein,
rode the south floor into the hall and stood on its link so Reinforce02 never reached anyone; Xander used the third vein
(6,1) on turn 38; the north-east, Reinforce01 and the boss room guards were killed from the row-1 corridor; Xander
baited the boss out of its room and Ryoma killed it on turn 50. **6 of 6 units, nobody lost** (a try where the boss
walked out and killed Ryoma was undone), save slot 1, castle, chapter id now C026 (not the Endgame). Route `rv-ch25`
(routes.json, 3,760 presses, frames 255171, `verified: false`) and checkpoints `rv-ch25` (markers.json, preparations
9682 to stage complete 252023 and the castle 254861) written; the export was replayed from frame 0 and reached the
chain's instruction count (see docs/ROBOT.md "Revelation chapter 25 (`rv-ch25`) CLEARED"). Not done here: the
two-copy proof, the pack of `rv-ch25-clear` and the capture (a separate step). Next: chapter 26 from `rv-ch25-clear`.

## 36. Revelation, area "rv": chapter 26 played from `rv-ch25-clear` (route `rv-ch26`)

F-031, real play (no pokes, no cheat save). One fresh helper, chain `c26` (`--dir build/speed/rv26`). Chapter 26 'The
Vallite King' (map C026, defeat the boss): Xander froze the south pool's vein on turn 1 (Corrin again on turn 9), the
army held the south pocket in three pairs, Xander then baited the centre and the north one group at a time, and on
turn 24 Xander, Ryoma and Leo (with Xander's dual strike) killed the boss Gunter on his throne. **6 of 6 units, nobody
lost** (tries that lost Corrin, Takumi, and Takumi with Corrin on turns 2-4 were undone), save slot 1, castle, chapter
id now C027 (not the Endgame). Route `rv-ch26` (routes.json, 1,644 presses, frames 136970, `verified: false`) and
checkpoints `rv-ch26` (markers.json, preparations 11050 to stage complete 130902 and the castle 136660) written; the
export was replayed from frame 0 and reached the chain's instruction count (see docs/ROBOT.md "Revelation chapter 26").
Not done here: the two-copy proof, the pack of `rv-ch26-clear` and the capture (a separate step). Next: chapter 27
from `rv-ch26-clear` (the last map with a castle; the Endgame follows it).

## 37. Revelation, area "rv": chapter 27 from `rv-ch26-clear`, NOT cleared (no route key)

F-031, real play (no pokes, no cheat save). One fresh helper, chain `c27` (`--dir build/speed/rv27`). Chapter 27
'Hear My Cry' (map C027, defeat the boss). It is not the Endgame, but there is no castle after it: the next stop is
Endgame preparations. Stopped at turn 35, frame 182,168, 1,110 presses, at about 67 minutes of the 100-minute cap.
**6 of 6 units alive** (one try that lost Corrin on turn 17 was undone). The boss (Silent Dragon, 80 HP, throne
(13,1)) was never reached. The spawn pools kept sending waves (the second wave of the single pools came on turn 31),
and the clock could not fit a march north plus the boss fight. No routes.json / markers.json key written. Kept states:
build/speed/rv27/c27_t35_backup (the chain's turn 35: everyone alive, but Corrin has 23 HP next to a Master of Arms and
a Basara) and build/speed/rv27/c27_t20_backup (turn 20, frame 108,780: the first wave dead, a quiet board). Details:
docs/ROBOT.md "Revelation chapter 27 (`rv-ch27`), NOT cleared". Next: from the turn-20 backup, go north at once, and
use the veins to seal the single pools on the way.
Second helper (2026-11-18, 08:27-08:55, cap 60 min): played on a copy (build/speed/rv27/c27r) from the turn-20
backup, real play, still **not cleared**. Turns 20-25 killed the west group, the Oni Chieftain, the Kinshi Knight and
the whole north-east wave with nobody lost (three lost tries undone). New restart point:
**build/speed/rv27/c27r_t26_backup** (turn 26, frame 141,736, 6 of 6 alive, but Ryoma 10 HP, Corrin 20, Takumi 13).
No route key, markers or export. Details: docs/ROBOT.md "rv-ch27, second helper".
Third helper (round 32, 2026-11-18, 09:18-10:05, cap 100 min): a copy of c27r_t26_backup in its own folder
(build/speed/rv27h/c27h), real play, still **not cleared**. Turns 26-33 killed the Great Master, a Paladin, a General,
a Merchant, an Adventurer, a Sniper and two of the south-east group with nobody lost, but the party ended split
(Xander north of the corridor, Corrin's and Shura's pairs in the south room) and every line from turn 34 lost Shura or
Corrin (five lost tries, all undone). New restart point: **build/speed/rv27h/c27h_t34_backup** (turn 34, frame
191,054, 6 of 6 alive; Xander 25, Ryoma 10, Takumi 10). No route key, markers or export. Details: docs/ROBOT.md
"rv-ch27, third helper (round 32)".
Fourth helper (round 32, 2026-11-18, 10:06-10:42, cap 60 min): a copy of c27h_t34_backup in its own folder
(build/speed/rv27i/c27i), real play, still **not cleared**, but the turn-34 trap is solved: turns 34-40 went with
nobody lost (both silver Swordmasters, both Masters of Arms, the Merchant, the Oni Chieftain, the Wyvern Lord, the
Hero, the Malig Knight, the Kinshi Knight, the Mechanist, the Master Ninja, the Basara and others killed). Every turn-41
line lost Shura (three tries, undone). New restart point: **build/speed/rv27i/c27i_t41_backup** (turn 41, frame
238,284, 591 press lines, 6 of 6 alive; Shura 11, Takumi 10, Xander 14 as support). No route key, markers or
export. Details: docs/ROBOT.md "rv-ch27, fourth helper (round 32)".
