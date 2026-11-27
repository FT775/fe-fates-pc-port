# The robot's cheat track: pokes into its own test game

**In plain words.** Some readable functions only run in situations real play has not reached yet: a
forge that needs an ore the castle never gave, a skill that fires on a lucky roll, a child unit that
needs a long support chain. Instead of waiting for those, the test robot may change a few numbers in
its **own** test game's memory while a headless run plays (the owner's OK, 2026-11-12 night, in chat).
Those runs are kept apart: they are called **cheat routes**, they are counted in their own table, and
nothing real-play depends on them. Tags: **[high]** checked by a script or a run, **[med]** strong
indirect evidence.

## 1. Rules

1. **Only the robot's own test game.** A poke changes the memory of a headless boot.exe run below
   `build/` (its savestate between two stages, section 2). Never the owner's saves, never the owner's
   Zakuro cheat file (`%APPDATA%\zakuro\...\cheats`), never the mods folder, never `play/`. boot.exe's
   data folder is the run's own (`ZAKURO_DATA` below `build/`), so even Zakuro's own cheat-file loader
   only looks there (there is no file there) [high: `parallel.py` checks `%APPDATA%\zakuro` and
   `%APPDATA%\3dsrecomp` before and after every session].
2. **Named and labelled.** A cheat route is named `cheat-*` and says `"cheat": true` in
   config/harness/routes.json (both or neither: `headless.load_routes` refuses anything else). Only a
   cheat route may have `"pokes"`.
3. **Never a parent of real play.** A cheat run is a run of a cheat route, or any run whose start save
   is a cheat save. A save is a cheat save when it is named `cheat-*`, **or** it holds the cheat mark
   (`harness-cheat.json`, written by `headless.pack_save` into every save of a cheat run; it records the
   run, route, start save and poke count, and is never laid out for the game), **or** its save files are
   byte for byte those of a cheat save in build/harness/saves/ (a copy under a new name, or a repack
   without the mark) (`headless.save_is_cheat`). Enforced at four places:
   - `headless.load_routes` (through `cheats.check_routes`): a real-play route may not name a `cheat-*`
     save; `cheats.py --check` also opens every packed start save of a real-play route.
   - `headless.run` (`check_start_save`, before the save is laid out) and `parallel.py` (when a job is
     made): a real-play route refuses a cheat start save, however it was named (the route's `"save"` or
     `--save`). run.json records `start_save_cheat` (why, or null).
   - `headless.pack_save` (also `parallel.py pack`): a save from a cheat run (route or start save) is
     named `cheat-*` and carries the mark; a real-play run's save may not be named `cheat-*`. A run.json
     without `start_save_cheat` is checked against its start save zip, and refused if that is gone.
   - `recapture.py synth` refuses a cheat run (its pokes happen between stages, which a session cannot
     replay).
   Review round 6 found the first version open: `runs --route title --save cheat-castle-katana` ran as
   real play and its save packed under a plain name. That is now refused (test_parallel `LaunderTests`).
   The limit: someone editing a zip by hand (changing a byte of the save) is not something the harness
   can tell from real play; tracked routes name their saves, and the rule is about the robot's own
   pipeline. A cheat route may start from a real save or a cheat save.
4. **Scored apart.** `parallel.py` prints real-play runs and cheat runs in two lists and, in capture
   mode, two record tables with their own totals (`summary.json` `capture_totals.honest` /
   `.cheat`, `cheat_runs`). A reader met only on a cheat route is "met on a cheat route", never "met in
   play".
5. **Recorded.** Every run's run.json has `"cheat": true`, the stages, and every poke: frame, path,
   address, FCRAM offset and how it was found, old and new value. Only those numbers.
6. **Checked before writing.** A poke may name the value it expects to find (`expect`); a different
   value stops the run before anything is written (wrong place or wrong moment). The dumped page must
   equal the savestate's page where the poke lands.
7. **Same rules as every robot run otherwise**: below-normal priority, the owner's budget
   (`FEF_ROBOT_JOBS`), through `parallel.py` (or `robot/budget.py` for one-at-a-time look-aheads), no
   game data in tracked files (no dumps, saves or screenshots; numbers and code addresses only).

## 2. How a poke is applied (tools/harness/cheats.py) [high]

No engine change and no Zakuro build: boot.exe already saves and loads states (`ZAKURO_SAVE_AT`,
`ZAKURO_LOAD`) and dumps memory (`ZAKURO_DUMP_MEM`). A cheat run is cut into stages at the poke frames:

1. Stage k runs boot.exe up to the poke frame F (from the start save, or from the patched state of
   stage k-1), keeps the savestate of frame F and a memory dump of the same moment (boot.exe dumps
   after frame F-1 and saves before frame F).
2. Each poke's path is followed in the dump, the old bytes are checked, and the address is found in the
   savestate's FCRAM section: the linear heap (0x30000000 + x is FCRAM + x on this boot, checked page by
   page against the dump), or, for any other address, the one page-aligned place in FCRAM holding the
   dumped page (it must occur exactly once).
3. The bytes are written, FCRAM is stored again as a literal-only LZ4 block (the other sections are
   copied byte for byte), and stage k+1 starts from that state (`ZAKURO_LOAD`; boot.log says "loaded
   the state at frame F", which the run checks).

Replays repeat byte for byte: every stage is a normal deterministic run and the patch is a pure function
of its state. In capture mode each stage writes its own `summary.tsv` (`runs/<run>/stage<k>/` and
`runs/<run>/`); `parallel.py` reads them all. `harness.py report` reads only the last one, and
`harness.py h4a` refuses a cheat route (exit 2), so score cheat routes with `parallel.py runs --mode
capture`.

A poke in config/harness/routes.json:

```json
{"frame": 5100, "at": "unit:1 Unit.equip_skills[4]", "size": 2, "value": 25, "expect": 0,
 "why": "Corrin's fifth equip-skill slot (Unit::IsEquipSkill 0x0052DD04 reads it): skill 25"}
```

Path tokens, left to right: a hex address, a name of config/readable/globals.csv (`G_EquipSkill`), or
`unit:ID` (the unit of person id ID in forces 0..3); `*` follows the pointer stored there; `+0x8` / `-4`
adds; `Struct.field[i]` adds a field of config/readable/structs/ (offset + index x element size; the
poke's size must equal the element's). `value_from` (instead of `value`) writes the address another
path names, e.g. `"unit:1 Unit.person *"` (Corrin's Person record).

```bash
python tools/harness/cheats.py --selftest   # invented memory and savestates: paths, mapping, patching, rules (23/23)
python tools/harness/cheats.py --check      # the cheat routes of routes.json against the rules
python tools/harness/parallel.py runs --route cheat-forge-katana --markers      # like any route
python tools/harness/parallel.py runs --route cheat-skill-proc --mode capture   # scored in the CHEAT table
```

## 3. The cheat routes (round 6, 2026-11-13 night) [high]

| Route | From | Pokes | What it meets | Save |
|---|---|---|---|---|
| `cheat-forge-katana` | bt-ch8-clear | frame 3500: 1 Pearl (ore index 6, the katana's) in the castle stock | Hana's Iron Katana **+1** (marker `forged` = [{where 10, item 22, rank 1}]); Equip Skills > Corrin on the way: `unit_equipped_skill_count` (12 records) | `cheat-castle-katana` (loads: forge_max 1 at the castle) |
| `cheat-skill-proc` | bt-ch8-support | frame 5100: Corrin's 5th skill slot = 25 (Lethality); skill 25's trigger factor 1 -> 100 | a skill **activation** replayed: the cut-in at 5950-6050, Corrin's one attack kills the 22-HP samurai (enemies 11 -> 10, exp 28 -> 55); `unit_lethality_immune` (IsInvalidKill) met | `cheat-ch8-lethality`, a battle save (loads onto the map: enemies 10, Corrin exp 55) |
| `cheat-family` | bt-ch8-support | frame 6400: a two-parent family record in unused heap; Rinkah's Unit.family -> it; her Person.family_index = 4 | `family_grow` (8 records), `family_limit` (25) at her level-up | `cheat-ch8-family`, a battle save |
| `cheat-katana-reload` (round 6b) | cheat-castle-katana | none (it starts from a cheat save, so it is a cheat route) | the katana save loaded again: 3500 preparations, forge_max 1, `forged` [{where 10, item 22, rank 1}], ore all 0; checkpoints met twice, DETERMINISTIC x2, memory 47d34f0d... | none |
| `cheat-bt-endgame` (round 19, F-030: counts as Birthright played to the end) | bt-ch26-clear (frame 0: bt-ch27 + Endgame turns 1-7 of chain btend/ch) | frame 193094 (Endgame turn 8, player phase): Garon's current HP `unit:31232 +0xF3` 78 -> 1 (Unit.csv has no current-HP field; +0xF3 is the byte the forecasts and danger.py read) | Ryoma kills Garon (195014, enemies 16 -> 15, 16 of 16 alive); the ending, records, epilogue and credits, 'The End', the logbook card entry, then the title screen (291626). No hang, no save written. 10 checkpoints met in one marker run from frame 0 (memory 95f8384c...); the two-copy proof is a separate step. docs/ROBOT.md 3y. Proven later (two copies, memory 95f8384c..., same instruction count) and captured (r19-capc-endgameb, 6,328 records, 0 bad), verified. The route keeps a `save_at` (291630) only because headless.py's schema needs one; no clear save exists or is packed (check_all row cheat-endgame guards it) | none |
| `cheat-cq-ch17` (round 29, F-033: counts as Conquest played) | cq-ch16-clear (frame 0: chain cq17/c17's real-play turns 1-18, then its copy cqx17/c) | movement only, 28 pokes: frame 144711 (turn 19 player phase) every one of the 14 units' move bonus `unit:N +0x12C` (s8; Unit::GetMovePower 0x0052D6B8 adds it uncapped unless state bit 30) 0 -> 20, expect 0; frame 164473 (turn 22 player phase) 20 -> 60, expect 20 | Kotaro killed on turn 23 (Camilla with Xander's dual strike 38 -> 21, then Shura's killer bow with Camilla's dual), 14 of 14 alive, stage complete (183159), banner, save slot 1, the castle (188537). 11 checkpoints met in one marker run from frame 0 (memory e02b945e..., instructions 845142249600, equal to the boot-server replay with the pokes); the two-copy proof is a separate step. docs/ROBOT.md 3z-cq17c. Proven later (two copies, memory e02b945e..., same instruction count) and captured (r29-cap-cheat-cq-ch17, 11,340 records, 0 bad), verified | `cheat-cq-ch17-clear` (packed from r29-proof-cheat-cq-ch17-1, cheat mark) |
| `cheat-cq-ch18` (round 32, F-033: counts as Conquest played) | cheat-cq-ch17-clear (frame 0: chains cqx18 f, h, then its copy j/k) | none of its own (the move bonus 60 is in the cheat start save, so it is a cheat route) | Zola killed on turn 1, the generals boss pair on turns 13-14 (Corrin and Xander, Azura's song; Gunter took the dual guard; Silas sheltered Elise), 14 turns, 14 of 14 alive, stage complete (163230), banner, save slot 1, the castle (170778). 11 checkpoints met in one marker run from frame 0 (r31-cqx18-markers, memory defb76ac..., instructions 765915765120); two-copy proof r32-proof-cheat-cq-ch18 PASS (both exit 0, memory defb76ac..., instructions 765915765120 both, checkpoints all met), capture r32-cap-cheat-cq-ch18 4,253 records 0 bad, verified; round 32 integrate played it live once more with kept records (r32-capc-cheat-cq-ch18, same memory, 4,253 records, 0 bad). docs/ROBOT.md 3z-cq18c | `cheat-cq-ch18-clear` (packed from r32-proof-cheat-cq-ch18-1, carries harness-cheat.json) |
| `cheat-cq-ch19` (round 32, F-033: counts as Conquest played) | cheat-cq-ch18-clear (frame 0: chain cqx19/c) | none of its own (the move bonus 60 is in the cheat start save, so it is a cheat route) | Rout the enemy (26 foxes): Camilla and Xander broke each pack (beaststones do 0 to them), the boss killed on turn 11 (Camilla), the last guard on turn 12 (Xander), 12 turns, 13 of 13 alive, stage complete (167696), banner, save slot 1, the castle (172674). 11 checkpoints met in one marker run from frame 0 (r31-cqx19-markers, memory faf6fbe0..., instructions 773847375840); two-copy proof r32-proof-cheat-cq-ch19 PASS (both exit 0, same memory and instructions, checkpoints all met), capture r32-cap-cheat-cq-ch19 4,032 records 0 bad, verified; round 32 integrate played it live once more with kept records (r32-capc-cheat-cq-ch19, same memory, 4,032 records, 0 bad). docs/ROBOT.md 3z-cq19 | `cheat-cq-ch19-clear` (packed from proof copy 1, carries harness-cheat.json) |
| `cheat-cq-ch20` (round 33, F-033: counts as Conquest played) | cheat-cq-ch19-clear (frame 0: chains cqx20 c, h/i, then its copy j) | none of its own (the move bonus 60 is in the cheat start save, so it is a cheat route) | Seize: the west room, the row-5 corridor and both shrine maidens cleared (turns 9-15), Fuga killed on turn 16 (Camilla, Xander, Corrin's dragonstone), Corrin seized on turn 17; 17 turns, 14 of 14 alive, stage complete (218370), banner, talk, save slot 1, the castle (223370). 12 checkpoints met in one marker run from frame 0 (r33-cqx20-markers, memory 2737fb0d..., instructions 1001023046496). Two-copy proof passed (round 34, r34-proof-cheat-cq-ch20: both copies equal, checkpoints all met); capture with every override 4,373 records, 0 bad (r34-cap-cheat-cq-ch20; with records kept r34-capc-cheat-cq-ch20, round 34 integrate). docs/ROBOT.md 3z-cq20b | `cheat-cq-ch20-clear` (packed with the cheat mark) |
| `cheat-cq-ch21` (round 34, F-033: counts as Conquest played) | cheat-cq-ch20-clear (frame 0: chain cqx21/c) | none of its own (the move bonus 60 is in the cheat start save, so it is a cheat route) | Escape with all units: on turn 1 all 14 moved from the south end to the escape tile (9,1) one after another and escaped (Escape, Leave the battlefield? Yes), Corrin last; no battle fought, 1 turn, 14 of 14, stage complete (40598), banner (43608), talk, save slot 1, the castle (51736). 8 checkpoints met in one marker run from frame 0 (r34-cqx21-markers, memory b0b3c09e..., instructions 231907750272). Two-copy proof passed (round 34, r34-proof-cheat-cq-ch21: both copies equal, checkpoints all met); capture with every override 2,384 records, 0 bad (r34-cap-cheat-cq-ch21; with records kept r34-capc-cheat-cq-ch21, round 34 integrate). docs/ROBOT.md 3z-cq21 | `cheat-cq-ch21-clear` (packed with the cheat mark) |
| `cheat-cq-ch22` (round 34, F-033: counts as Conquest played) | cheat-cq-ch21-clear (frame 0: chain cqx22/c) | none of its own (the move bonus 60 is in the cheat start save, so it is a cheat route) | Seize: on turn 1 Elise used the dragon vein (20,7) (the levee (8-10,5) opens), Camilla, Xander (twice, Azura sang, Camilla's dual strikes) and Gunter killed the boss Yukimura on the gate (13,1), Corrin seized; 1 turn, no enemy phase, 15 of 15, stage complete (25242), banner (28312), talk, save slot 1, the castle (32700). 11 checkpoints met in one marker run from frame 0 (r34-cqx22-markers, memory a3d1ce80..., instructions 146604845376). Two-copy proof passed (round 34, r34-proof-cheat-cq-ch22: both copies equal, checkpoints all met); capture with every override 2,826 records, 0 bad (r34-cap-cheat-cq-ch22; with records kept r34-capc-cheat-cq-ch22, round 34 integrate). docs/ROBOT.md 3z-cq22 | `cheat-cq-ch22-clear` (packed with the cheat mark) |
| `cheat-cq-ch23` (round 34, F-033: counts as Conquest played) | cheat-cq-ch22-clear (frame 0: chain cqx23/c) | none of its own (the move bonus 60 is in the cheat start save, so it is a cheat route) | Seize: the throne room is reached only by stairs (Stairs command, the move goes on after the warp); on turn 1 Camilla waited at (6,4), Xander (6,3) twice (Camilla's dual strikes, Azura sang) killed the boss Takumi on the throne (5,3), Corrin seized; 1 turn, no enemy phase, 15 of 15, seize question (28774), stage complete (28898), banner (31968), talk, save slot 1, the castle (36506). 10 checkpoints met in one marker run from frame 0 (r34-cqx23-markers, memory bd79d0e5..., instructions 163660048992). Two-copy proof passed (round 34, r34-proof-cheat-cq-ch23: both copies equal, checkpoints all met); capture with every override 2,789 records, 0 bad (r34-cap-cheat-cq-ch23; with records kept r34-capc-cheat-cq-ch23, round 34 integrate). docs/ROBOT.md 3z-cq23 | `cheat-cq-ch23-clear` (packed with the cheat mark) |
| `cheat-cq-ch24` (round 35, F-033 + F-036: counts as Conquest played) | cheat-cq-ch23-clear (frame 0: chain cqx24/f, its turn 1 = round 34's chain c presses) | 106 at frame 7654 (turn 1 player phase), each with expect: all 15 units' HP gain `Unit.gains[0]` (+0xC8) and HP cap bonus `Unit.limit_bonus[0]` (+0xD0, Unit::GetLimit 0x0053384C) +60, Def/Res gains (+0xCE/+0xCF) and cap bonuses (+0xD6/+0xD7) +40, current HP `+0xF3` to the new maximum (99 at most); unit 39's move bonus `+0x12C` 0 -> 60. No hit, item or enemy poke | Seize: turn 1 Hinoka killed (Camilla, Xander twice, Gunter, Azura's song), enemy phase 1 nobody lost; turn 2 Xander and Camilla (Gunter's dual) killed the Oni Chieftain on the gate (12,1), Corrin seized; 2 turns, 15 of 15, stage complete (35428), banner (38538), talk, save slot 1, the castle (43096, chapter B025). 16 checkpoints met in one marker run from frame 0 (r35-cqx24-markers, memory 372863cc..., instructions 193190735232); the two-copy proof: two copies equal (r37-proof-cheat-cq-ch24, memory 372863cc..., 193,190,735,232 instructions), clear save packed with the cheat mark, verified (round 37). docs/ROBOT.md 3z-cq24b | `cheat-cq-ch24-clear` (to be packed by the proof step) |
| `cheat-cq-ch25` (round 37, F-033 + F-036: counts as Conquest played) | cheat-cq-ch24-clear (frame 0: chain cqx25/c; the save already carries the move bonus 60 and the HP/Def/Res boost on 15 units) | 8 at frame 12856 (turn 1 player phase, before any move), each with expect, for Leo only (unit 41, new this chapter, unboosted): HP gain `Unit.gains[0]` (+0xC8) and HP cap bonus `Unit.limit_bonus[0]` (+0xD0) +60, Def/Res gains (+0xCE/+0xCF) and cap bonuses (+0xD6/+0xD7) +40, current HP `+0xF3` 34 -> 94, move bonus `+0x12C` 0 -> 60. No hit, item or enemy poke | Defeat the boss: Corrin starts sealed in the throne room with Ryoma (heal tiles undo Corrin's 2 damage); turn 4 Xander killed the Master of Arms (25,7) that blocks the east way, six units killed Kagero (26,2), the four doors opened, Elise used the vein (14,6) (heal tiles -> avoid-penalty tiles), Corrin, Nyx and Leo killed Ryoma; 4 turns, 16 of 16, stage complete (53566), banner, talk, save slot 1, the castle (64514, chapter B026). 20 checkpoints met in one marker run from frame 0 (r37-cqx25-markers, memory d6396410..., instructions 289167706080); the two-copy proof: two copies equal (r37-proof-cheat-cq-ch25, memory d6396410..., 289,167,706,080 instructions), clear save packed with the cheat mark, verified (round 37). docs/ROBOT.md 3z-cq25 | `cheat-cq-ch25-clear` (to be packed by the proof step) |
| `cheat-cq-ch26` (round 37, F-033 + F-036: counts as Conquest played) | cheat-cq-ch25-clear (frame 0: chain cqx26/c; the save already carries the move bonus 60 and the HP/Def/Res boost on all 16) | none of its own (a cheat route only because of the cheat start save) | Seize: the doors open only by Shura and Niles (Door command, one per action); east way (13,10), (19,12), (22,19), (23,23), (20,25), then the boss door (13,21) on turn 6; Generals in the door (20,25) and Hans killed on turns 4-5; Camilla, Gunter, Benny, Niles and Leo killed the boss Iago, Corrin seized the throne (13,19); 6 turns, 16 of 16, nobody lost, stage complete (123940), banner, talk, save slot 1, the castle (128378, chapter B027). 21 checkpoints met in one marker run from frame 0 (r37-cqx26-markers, memory 67190ee9..., instructions 575350975584); the two-copy proof: two copies equal (r37-proof-cheat-cq-ch26, memory 67190ee9..., 575,350,975,584 instructions), clear save packed with the cheat mark, verified (round 37). docs/ROBOT.md 3z-cq26 | `cheat-cq-ch26-clear` (to be packed by the proof step) |
| `cheat-cq-ch27` (round 37, F-033 + F-036: counts as Conquest played) | cheat-cq-ch26-clear (frame 0: chain cqx27/c; the save already carries the move bonus 60 and the HP/Def/Res boost on all 16) | none of its own (a cheat route only because of the cheat start save) | Defeat the boss: turn 1 Leo and Camilla killed the Lancer (14,8) that plugged the corridor; Garon (65 HP, damage about halved, throne heals 13 a turn) hit by Xander from (15,2) twice a turn (Azura's song) with range-2 units next to him for his dual strikes; turn 3 Xander killed him; 3 turns, 16 of 16, nobody lost, stage complete (69526), banner, talk, then straight to the Endgame preparations (89278, chapter B028; no save question, no castle). 11 checkpoints met in one marker run from frame 0 (r37-cqx27-markers, memory 4fcd68e2..., instructions 400721105664); the two-copy proof: two copies equal (r37-proof-cheat-cq-ch27, memory 4fcd68e2..., 400,721,105,664 instructions), verified; no clear save by design (round 37). docs/ROBOT.md 3z-cq27 | none (the game writes no save after chapter 27; the Endgame starts from cheat-cq-ch26-clear frame 0 with this route as its prefix) |
| `cheat-cq-endgame` (round 37, F-030/F-033/F-036: counts as Conquest played to the end) | cheat-cq-ch26-clear (frame 0: cheat-cq-ch27's 1,515 presses as the prefix, to the Endgame preparations 89278; no Save there, F-029; then chain build/speed/cqend/ce, a copy of cqx27/c) | one poke at frame 91472 (Endgame turn 1 player phase): the boss Takumi's current HP `unit:31232 +0xF3` 60 -> 1, expect 60 (the first unit of that id = the front unit; the paired copy not poked) | Turn 1: Xander (Siegfried) moved (13,6) -> (15,28), forecast 1/60, 94%, his first hit killed Takumi (94290, no stage-complete banner); no enemy phase, 16 of 16 alive, nothing undone; ending events, one movie (START), chapter records (107282), epilogue and credits, 'The End' (waits for A), the logbook card entry, 'proceed?' (LEFT, A), the title screen (198090) to 198700. No save prompt, no hang. 14 checkpoints. Two-copy proof r37-proof-cheat-cq-endgame: PASS, both copies memory cd5d0d3d..., 890,401,723,200 instructions, checkpoints all met; capture from frame 0 r37-capc-endgame: PASS, 179 functions, 5,972 records, 0 bad; verified true. docs/ROBOT.md 3z-cqend | none (the game makes no save after Endgame) |
| `cheat-rv-ch27` (round 34, F-035: counts as Revelation played) | rv-ch26-clear (frame 0: real-play chains rv27/c27, rv27/c27r, rv27h/c27h, rv27i/c27i up to the turn-41 player phase 238284, 2,015 presses; then its copy rv27x/c27x) | movement only, 6 pokes at frame 238284 (turn 41 player phase), each with expect 0: the 6 units' move bonus `unit:N +0x12C` (s8; Unit::GetMovePower 0x0052D6B8 adds it uncapped) 0 -> 30 (Corrin 1, Ryoma 25, Leo 41, Xander 43, Shura 27, Takumi 21) | Turn 41: Ryoma killed the Maid closing Leo's pocket; turn 42: Shura healed Ryoma, Ryoma (Raijinto, range 2) hit the boss 80 -> 29, the boss died on Ryoma's counter in the enemy phase; 6 of 6 alive, stage complete (253108), banner (253718, 43 turns), closing scenes, **Endgame preparations** (260860, chapter C028; no save, no castle) to 261200. 11 checkpoints met in one marker run from frame 0 (runs-20261118-135605: memory b4025f15..., instructions 1170472723200, equal to the boot-server replay with the poke); two-copy proof not run in the play step; round 36 proof PASS (two equal copies, memory b4025f15b3475c00), verified true. No clear save by design: the packed cheat-rv-ch27-clear.zip held rv-ch26-clear's save files (no save after chapter 27) and was moved to build/harness/saves-aside/ at integrate (check_all cheat-endgame). docs/ROBOT.md "rv-ch27 on the cheat track" | none (no save after chapter 27; the Endgame starts from chain build/speed/rv27x/c27x, F-029) |
| `cheat-rv-endgame` (round 36, F-030/F-031: counts as Revelation played to the end) | rv-ch26-clear (frame 0: cheat-rv-ch27's 2,388 presses and 6 pokes as the prefix, to the Endgame preparations 261210; no Save there, F-029; then chain build/speed/rvend/ce, a copy of rv27x/c27x) | the 6 ch27 movement pokes, then current HP `unit:P +0xF3`, each part only after it appeared, each with expect: frame 281490 (turn 1 player phase) both hands 31234, 31235 61 -> 1; 284738 the head 31233 80 -> 1; 287822 the core 31232 80 -> 1 | All on turn 1, no enemy phase, 13 of 13 alive, nothing undone: Xander and Leo kill the hands, Ryoma the head, Corrin the core; ending events, chapter records (296772), epilogue and credits, 'The End' (375912, waits for A), the logbook card entry, 'proceed?' (LEFT, A), the title screen (377020) to 377700. No save prompt, no hang (the idle title later runs its attract demo). 16 checkpoints. Capture from frame 0 r36-capc-endgame: PASS, all checkpoints met, memory f03306be..., instructions 1692525067200, 183 functions, 13,063 records, 0 bad. **Two-copy proof not done in the finale step** (r36-proof-cheat-rv-endgame: both copies hit the default timeout on a loaded machine); **round 36 integrate re-ran it with --timeout 6000 (r36-proof2-cheat-rv-endgame): PASS, both copies memory f03306be7ca8af55, 1,692,525,067,200 instructions, checkpoints all met; verified true**; a second two-copy proof after commit e9d2950 (r36-proof3-cheat-rv-endgame, --timeout 6000, 1,588 s): PASS, same memory, instructions and checkpoints; no clear save by design (check_all cheat-endgame). docs/ROBOT.md "Revelation Endgame on the cheat track" | none (the game makes no save after Endgame) |

Each: checkpoints all met in two marker runs; `parallel.py determinism --copies 2` DETERMINISTIC (guest
memory identical, same instruction count); the same memory hash in plain, marker and capture runs
(`cheat-forge-katana` 3188fff1..., `cheat-skill-proc` 371db3a3..., `cheat-family` bb5ef48f...). The three cheat
saves were packed again in round 6b from fresh runs of their routes so they carry the cheat mark; their save files
are byte for byte the first packs' (`headless.save_fingerprint` equal). A battle save
(system menu > Save on a map) is written to the game's extra data (`user/extdata/0000000000001794/Map0.bak`), not
to savedata: pack it with `parallel.py pack SESSION RUN NAME extdata`; the title then asks chapter save or battle
save, and the default (A) loads the battle save. The
live compare of record (library fresh) is the integrate stage's; a look with the library as it stood
(STALE: targets.csv had changed) gave 0 bad records on all three.

Not done with a poke: `skill_total` (EquipSkill::GetNum: its one BL caller is a castle menu,
`castle::anonymous_namespace::Seq::MainMenu` 0x00487DC0, which screen was not found), `script_unit_has_skill`
(the script command is used only by a Conquest chapter script and one paralogue script, B028 and X022),
`skill_effect_name` (its caller `hfx::CreateSkillHit` did not run for Lethality), `family_parent_grow`
(reached only by Family::GetGrow's tail branch or by falling through, never by a BL: the capture hook
saw no call), the breakable-terrain forms (no Birthright map with a breakable wall or ruin reached).
Details and evidence: docs/ROBOT.md section 3c.

## 4. Round 72 pokes in the robot's own test copies (F-054 call 1; labelled "poke" in every round-72 table)

Not cheat routes: one-off robot jobs on copies of the installed program (boot-server fb9af979, capture library
405f2bac), headless, below `build/r72/`, never the owner's saves, never a parent of real play.

- **Track castle_esc, the child join (build/r72/castle/jobs/k-cq-X015-off, -on, -ond):** chapter select only
  (tools/harness/chapsel.py, rule 2 there), 2 pokes per job at frame 3590 in the job's own savestate, each
  checked against live memory first: the world-map spot record of X015 (0x3282727C, +4 state) 0 -> 1 (open)
  [0x32827280: 0000 -> 0100], and GameUserData +0xC, the current chapter pointer, -> X015's Chapter record
  [0x31CB210C: 9c945d32 -> f8995d32]; base save cq-ch16-clear (route B). Why: Conquest X015 is where a child
  (Siegbert) joins the army at the map's start; no recording reaches a child paralogue. No unit, item, stat or
  enemy poke. The castle shop jobs (build/r72/castle/jobs/c-*) have no poke: recorded routes only, plus one
  extra DOWN menu press in Revelation's build list (route variant r72-rv-castle-rod, never written to
  config/harness/routes.json).

- **Track bosses_chests, the Seal bosses (build/r72/bosses/jobs/b72*, driver build/r72/bosses/p72b.py):** chapter
  select pokes as above (chapsel.py rule 2: base rv-ch11-clear, Seal route byte 0 / 1 / 2), then rcheck's F-030 test
  cheats, the same in the randomizer-on and the randomizer-off job: the boss's current HP `+0xF3` -> 1 before each
  attack; the attacker PUT next to the boss (`+0xF4` / `+0xF5` and the map's unit-grid byte, rcheck `place_next`).
  New this round, only in the R016 pair b72k-R016-gunter / b72koff-R016-gunter: Gunter's Skl gain `Unit.gains[3]`
  (+0xCB) and Skl cap bonus `Unit.limit_bonus[3]` (+0xD3) +60 each (job key `attacker_boost`; hit 26% -> 100%).
  Why: Takumi sits on a fort with high avoid and a 28 x2 counter, so every attacker missed and died, on and off
  alike, and a miss repeats in every try (the hit roll comes from the saved state). No item or enemy-stat poke.
- **Track bosses_chests, the chests and the village (build/r72/chests/jobs/c72*, driver build/r72/chests/p72c.py):**
  chapter select pokes as above for the Seal job, then, the same in the on and the off job: the opener PUT next to
  the chest (a chest tile is impassable) or on the village tile (`+0xF4` / `+0xF5` and the unit-grid byte); for a
  chest, a Chest Key (IID_宝の鍵, item number 298 read from the game's own item table) written into the opener's
  first empty item slot (`+0x108 + 4k`: number 298, word 2 0x0100, as a fresh one-use item). Why: no recording
  opens a Conquest or Seal chest or visits a village, and round 71's two opens were by enemies. No stat or enemy
  poke; the gift itself is never poked (the game's own chest script gives it).
- **Track check, the full check's robot jobs (build/r72/check: pjobs, sjobs, cjobs, n/*/pjobs, jobs; frozen harness
  copy build/r72/check/bin/h, the same pokes in the randomizer-off and the randomizer-on job of a pair; added by
  integrate, round 72):** listed by kind, with the cells they touch (build/r72/integrate/pokescan.json scans every
  valid pair's result.json `job.pokes` and `pokes_extra`; a poke written after the judged shot is not counted).
  - Chapter select in every job (chapsel.py rule 2: the world-map spot record and the current chapter pointer). Why:
    a recording reaches only some chapters. Not a content poke; not marked in the table.
  - `mseal` / `hseal` (rcheck `seal_menu`): a Master Seal (IID_マスタープルフ) or Heart Seal (IID_パラレルプルフ) written
    into the first army unit's item slot 4 (`+0x108 + 16`). Why: the class change list is shown only when a unit holds
    a seal, and no recording gives one early. Cells: Promotions and Heart Seal classes on all 4 paths (robot+poke).
  - `exp99` (rcheck `levelup`): every player unit's exp `+0xF2` -> 99 before End. Why: a level-up window shows the
    growths only when someone levels in the enemy phase. Cells: Growths (Conquest, Revelation, Seal) and Class growths
    (all 4 paths) (robot+poke).
  - `enemyhp1` (rcheck `unit_attack`): the target enemy's HP `+0xF3` -> 1, so the attack kills it and a level-up can
    follow. Cell: Class growths on Birthright (robot+poke).
  - `b<n>w<k>` / `b<n>fly<k>` (rcheck `bosskill`) and `ua<n>` (rcheck `attack_unit`): every enemy on the target tile
    HP `+0xF3` -> 1 and the attacker's move bonus `+0x12C` -> 60 (bosskill's F-030 test cheats). Why: the battle
    picture of the unit itself (recolour) and the scenes after a boss kill. Cells: Story boss classes on Birthright,
    Conquest, Revelation (SEEN+poke); Recolour and Recolour "Easier to see" on Conquest (SEEN+poke / robot+poke).
  - `trait_weapon` plus the job's item pokes (round 61's method, build/r72/check/p61.py): the same weapon written
    into a unit's item slot in both runs. Why: no natural draw shows a weapon special power on those paths. Cells:
    Weapon special powers on Revelation and Seal (robot+poke).
  - The drop check (`dropcheck`, round 64): the target at 1 HP, its drop compared after the kill; only its own drop
    shots. No table cell rests on it alone.
  No poke wrote a gift, a randomizer table or anything the judged change comes from: the pokes reach the screen, the
  judged values are the game's own. Every such cell is labelled "+poke" in docs/tests/CHECK_R72.md.

## 5. Round 75 pokes in the robot's own test copies (F-059 (3) standing OK; cheat pokes OK'd for rounds 72 and 75; F-060)

Not cheat routes: one-off robot jobs on copies of the installed round-74 program (boot-server b3ebe748, capture
library 405f2bac), headless, below `build/r75/`, never the owner's saves, never a parent of real play. In every
pair the full job and the keep job carry exactly the same pokes (`pokes_extra` equal). No unit stat, item, gift or
randomizer-table poke was used: the judged names, faces and lines are the game's own.

- **Track c008, Revelation 8 (build/r75/c008/jobs/c008b-full, c008b-keep; driver build/r75/c008/tools/c008.py):**
  - Chapter select (chapsel.py rule 2, base save rv-ch7-clear, frame about 3590). Both writes wrote the value
    already there, because C008 is already open and current in that save: the world-map spot record of C008, +4
    state [0x327E22CC: 0100 -> 0100]; GameUserData +0xC, the current chapter pointer [0x31CB210C: 24965d32 ->
    24965d32]. Why: reach the chapter.
  - rcheck `bosskill` with `place_next` (F-030 test cheats; unit grid at 0x328E8BE8, byte y*32+x). Why: reach the
    boss battle quotes and the chapter's ending scenes without new play.
    - frame 8484, Orochi's spot (PID_C008_オロチ at (14,4)): HP +0xF3 [0x32627983: 0x14 -> 0x01]; Corrin put on
      (14,5) [0x32626E44 (+0xF4): 0x0d -> 0x0e, 0x32626E45 (+0xF5): 0x13 -> 0x05]; grid [0x328E8E55: 01 -> 00,
      0x328E8C96: 00 -> 01].
    - frame 10026, Saizo's spot (PID_C008_サイゾウ at (12,4)): HP [0x32627843: 0x17 -> 0x01]; Gunter put on (12,5)
      [0x32627204: 0x0e -> 0x0c, 0x32627205: 0x14 -> 0x05]; grid [0x328E8E76: 04 -> 00, 0x328E8C94: 00 -> 04].
    - frame 11658, the boss Yukimura (PID_C008_ボス at (13,3)): HP [0x32627703: 0x24 -> 0x01]; Felicia put on (13,4)
      [0x326270C4: 0x0d -> 0x0d, 0x326270C5: 0x14 -> 0x04]; grid [0x328E8E75: 03 -> 00, 0x328E8C75: 00 -> 03].
- **Track c013, Revelation 13, the chapter-end leg only (build/r75/c013/bk/jobs bk-*, bk2-*, bk3-* full and keep;
  driver build/r75/c013/tools/bk.py):** the recording jobs (c013-full, -keep, -fullnh, -off) and the talk jobs used
  no poke.
  - Chapter select (rcheck/chapsel `select`, base save rv-ch12-clear, frame 3590), both writes unchanged values:
    C013's chapter-spot state [0x32826BC0: 0100 -> 0100]; the current chapter pointer [0x31CB210C: b0965d32 ->
    b0965d32].
  - frame 5240, label b0w0p0 (rcheck `bosskill` `place_next`, F-030 test cheat): the boss PID_C013_ボス (unit
    0x32629550) current HP +0xF3 [0x32629643: 2c -> 01]; Keaton's spot (unit 0x32629410) moved from (10,23) to
    (11,3), next to the boss behind the moat [0x32629504 (+0xF4): 0a -> 0b, 0x32629505 (+0xF5): 17 -> 03]; the
    map's unit-grid byte (grid 0x327DDDA8) [0x327DE092: 20 -> 00, 0x327DDE13: 00 -> 20]. Why: the chapter's
    closing scenes without new play (the recording leaves step under full at about frame 43500).
- **Track b009, Conquest 9:** no poke (the existing cq-ch9 recording only).
- **Track b016, Conquest 16:** no poke (the existing cq-ch16 recording only, with recruit_class and recruit_stats at
  "slot" so the recorded presses stay in step).
- **Track drift (build/r75/drift):** no poke. Its test-only patch variants (tools/mkvariant.py noaid / noface /
  nosex: the full patch minus some cells) are robot data in build/r75/drift/runs only, not pokes and never a run
  the page can make.

## 6. Round 76 pokes in the robot's own test copies (F-059 (3) standing OK; F-060's round-76 matrix)

Not cheat routes: one-off robot jobs on copies of the installed round-74 program (boot-server b3ebe748, capture
library 405f2bac), headless, below `build/r76/`, never the owner's saves, never a parent of real play. Each track
appends only its own lines here.

- **Track seal, the Seal edition's full swap and guarantees (build/r76/seal/jobs: s002-full, s002-keep, s002t-keep,
  s001t-keep, s004t-keep, s004t-full; driver build/r76/seal/tools/seal.py, a copy of round 75's c008.py):** COPIES of
  the installed boot-server b3ebe748 and capture library 405f2bac in build/r76/seal/bin; headless, self-exiting;
  runs r76s4-b659873f (look = full, A7 switch in the job's own data folder) and r76s4-9b8b8acb (look = keep), Seal
  page defaults with the shuffle 'route'. The full and the keep job of a pair carry exactly the same pokes.
  - Chapter select in every job (chapsel.py rule 2, base save rv-ch11-clear, frame 3590, Seal route byte 2, the spot
    record of M004 borrowed as in round 72's Seal jobs): the spot record's Chapter pointer [0x32840D58: a4575e32 ->
    f8575e32 (R002) / dc575e32 (R001) / 30585e32 (R004)] and its +4 state [0x32840D5C: 0000 -> 0100]; GameUserData
    +0xC, the current chapter pointer [0x31CBE06C: 14515e32 -> the same three values]; the route byte +0x2E
    [0x31CBE08E: 02 -> 02, unchanged]. Why: no Seal recording exists. Not a content poke.
  - s002-full and s002-keep only, frame 8490, label b0w0p0 (rcheck `bosskill` with `place_next`, F-030 test cheat):
    the boss PID_X020_ボス (Senno, at (28,12)) current HP +0xF3 [0x3263C783: 1f -> 01]; the Felicia spot's unit put
    from (8,16) to (27,12) next to the boss [0x3263B4C4 (+0xF4): 08 -> 1b, 0x3263B4C5 (+0xF5): 10 -> 0c]; the map's
    unit-grid byte (grid 0x328414E8) [0x328416F0: 03 -> 00, 0x32841683: 00 -> 03]. Why: a battle close-up of the
    swapped person and the chapter's closing scenes without new play. Content poke: the battle shots and the
    closing scenes of s002-* are '+poke'; the opening scenes, the unit list, unit page and map panel are not.
  - s002t-keep, s001t-keep, s004t-keep, s004t-full: no poke but chapter select (turns ended with End only).
- **Track full, the full swap on long replays and AID pieces (build/r76/full/jobs; driver build/r76/full/tools/r76run.py,
  a copy of round 75's c013 r75run.py with a per-frame random-generator trace):** **no poke, no chapter select.** Every
  job replays an existing recording (rv-ch13, cq-ch9, bt-ch14) from its own packed start save on COPIES of the
  installed boot-server b3ebe748 and capture library 405f2bac in build/r76/full/bin; headless, self-exiting. No memory
  write of any kind. The talk jobs b9op4-* and p3-* stop the recorded presses before the recording's Start skip
  (cq-ch9 frame 11348, rv-ch13 frame 6566) and press A every 40 / 60 frames instead, the same presses in the full and
  the keep job (robot presses, as round 75's talk jobs; not a poke). The "full minus AID" runs (`*-noaid`) are
  test-only patch variants made by build/r75/drift/tools/mkvariant.py noaid in build/r76/full/runs (robot data only,
  never a run the page can make), not pokes. Nothing here is '+poke'.
- **Track check, round 76's full check (build/r76/check: jobs, pjobs, cjobs; drivers copied from round 72's
  build/r72/check; frozen harness copy build/r76/check/bin/h; COPIES of the installed boot-server b3ebe748 and capture
  library 405f2bac in build/r76/check/bin; look = keep, no full block in any run):** chapter select only, in 557 of the
  587 robot results (the others start on their recorded chapter): chapsel.py rule 2 at frame 3590 in each job's own
  savestate, each write checked against live memory first: the target chapter's world-map spot record (its Chapter
  pointer and its +4 state 0000 -> 0100; Seal chapters borrow the spot record of M004 at 0x32840D58 / 0x32840D5C, as in
  round 72's Seal jobs), GameUserData +0xC, the current chapter pointer (Fates 0x31CB210C, Seal 0x31CBE06C), and for
  Seal the route byte +0x2E (0x31CBE08E, 02 -> 02, unchanged). The same pokes in the randomizer-off and the
  randomizer-on job of every pair. Every address and old / new value is in the job's result.json `pokes`. Why: a
  recording reaches only some chapters. **No content poke**: no unit, item, stat, HP, move, seal, exp or enemy write
  (build/r76/check/final76.py scans every re-judged pair's `job.pokes` and `pokes_extra`: none; the Nuzlocke gate
  proofs and the page robot write no memory). Nothing this track judged is '+poke'; the '+poke' cells of
  docs/tests/CHECK_R76.md are carried from round 72 (section 4 above).
  - Added by integrate on the check reviewer's finding: in 16 Seal jobs (R011, R012, S007, S009, each x off / all1 /
    all2 / all3, for example jobs/seal-R011-all1 and jobs/seal-S009-off) chapsel.py's `route_mask` write also sets the
    chapter-table record's +0x14 byte [0x325E5940, 0x325E595C, 0x325E5A58, 0x325E5B00: 00 -> 04], so the chapter is open
    on the Seal route. It is in each result.json `pokes`; a chapter-select write (round 59's borrow rule), not a content
    poke, so nothing changes in any table. Round 72's section 4 has the same gap (the same write in its Seal jobs).
