# The test robot on Fates: what a real headless run reached

ELI5: the robot is the game running with no window, pressing buttons from a list. On 2026-11-11 it ran
Fates for the first time (stage A: title, New Game, Normal, Casual). Later the same day (stage B) it
played one Birthright campaign from the empty save through the Prologue and Chapters 1-6, picked
Birthright at the route split, and walked into My Castle: armory, convoy and support list. On the way
it opened a combat forecast, used Attack Stance, paired two units (Guard Stance) and used dragon veins.
Round 3 (2026-11-12) went on from the chapter-6 save: the first castle visit built a Rod Shop instead
of the armory and bought a Vulnerary there (the shop), Chapter 7 was cleared with Corrin and Sakura
paired the whole map, and the chapter-8 preparations then had two support conversations ready: the
robot watched Corrin and Felicia's C support (and Corrin and Sakura's). A short chapter-8 piece made
Corrin the support of a pair, which met one more readable function. No smithy was offered up to then.
Round 4 (2026-11-12, same day) cleared chapter 8 (desert, rout the enemy, 16 turns, both dragon veins) and
recorded real level-ups from memory (Rinkah Lv 5 -> 6, Skl +1; Corrin 9 -> 12; Sakura 1 -> 2). After it the
castle build list has the Smithy: the robot built it, built a Dawn Armory with the second point, bought a second
Iron Katana for Hana and opened the forge's refine menu with the two katanas, but the forge refused: an Iron
Katana needs 1 Pearl (ore) and this save has no ore of any kind (read from memory). No weapon reached +1.
Round 5 (2026-11-13, night) played Birthright chapter 9 (Izumo, rout 17 enemies and the reinforcements, 19 turns,
Azura singing, a dragon vein, the boss on a healing throne), then in the castle built a Lottery Shop with the new
Dragon Vein point: its free daily draw gave 1 Coral (naginata ore), the Dawn Armory sold a second Iron Naginata for
Subaki, and the Smithy forged **Iron Naginata +1**; the forge read now has a real forged weapon (rank 1, Subaki).
Round 6 (2026-11-13, night) first made the harness tell the truth (a capture run with mismatch records now FAILS;
the look-ahead lock has no race), then opened a separate **cheat track** (docs/CHEATS.md, owner's OK): three
`cheat-*` routes poke the robot's own test game in headless runs and meet what real play had not: Hana's
**Iron Katana +1** (one Pearl poked in), a **skill activation** (Corrin's Lethality fires), and the **family**
readers (a two-parent record poked onto Rinkah before her level-up). They are counted apart from real play.
Round 7 (2026-11-13, day) looked at the game's own **options screen** (all 25 lines) and the **Units list** in
chapter 8 without changing anything (the saved option bytes are the same before, inside and after), which met the
last eight option readers, and ran the deeper checks H5/H6 on kept game records (docs/harness/H56.md).
Round 8 (2026-11-13/14, night, Birthright share of the three-route round, F-022) went on from the chapter-9 save:
the castle's Support screen first (five conversations, among them **Kaze-Hana** and **Felicia-Saizo**, two pairs that
can reach S and so open a child paralogue), then **chapter 10** (Ninja Village, rout, 17 turns: an enemy Takumi
falls and joins after the map, Kotaro beaten) and **chapter 11** (To the Sea, a ship, rout, 17 turns: Takumi's bow,
Reina recruited by Corrin's talk; five units retreat, Casual). Both replay from their start save to the same memory
twice, meet every checkpoint, pass a capture run with 0 bad records, and end in packed saves (`bt-ch10-clear`,
`bt-ch11-clear`). Section 3e. Conquest and Revelation (the other agent's share this round): [ROUTES_SPLIT.md](ROUTES_SPLIT.md).
Every piece replays from frame 0 (or from the in-game save the piece before it made) to the same game
memory, byte for byte. It knows where it is by reading the game's own list of running processes and a
few named game bytes, not by looking at pictures.

Plan: [tracks/ROBOT_PLAN.md](tracks/ROBOT_PLAN.md) (13 rows, one campaign: Birthright, Normal, Casual).
Tools: [HARNESS.md](HARNESS.md). Problems met: [harness/SOLVED.md](harness/SOLVED.md).
Tags: **[high]** seen in a run or checked by a script, **[med]** strong indirect evidence, **[low]** a guess.

## 1. Rows reached

| Row | Reach | State | Evidence |
|---|---|---|---|
| 0 | Title, twice, same inputs | **reached** [high] | route `title`, h4a determinism: guest memory identical (FCRAM, VRAM, DSP RAM, AXI WRAM), 13,443,408,000 instructions both runs, savestate memory hash `c3cbbe48...` in every original and capture run of the route |
| 0 | An update beside the ROM is refused | **reached** [high] | a hard link of the ROM in `build/harness/scratchrom/` with a synthetic update `.cia` (identifiers only, title `0004000E00179800`): `headless: SETUP: refused: .cia beside the ROM (update.cia (title 0004000E00179800))`, exit 3, no run folder made; the same link without it booted (same memory hash) |
| 1 | New game, Normal, Casual | **reached** [high] | screens: route `new-game` (markers `title__SelectDifficltyMenu`, `title__SelectModeMenu`, `title__ProcMyUnitEdit`). Bytes named by code and read by marker runs (`markers.game_state`; run `mk-bt-prologue` frame 16992 and every later bt-* checkpoint): GameUserData+0x2D = **0** (difficulty: `DifficultyGet` 0x003A8A70 returns this byte; the title's `NormalItem::ACall` stores 0, `HardItem` 1, `LunaticItem` 2), GameUserData+0x28 = 0x00000004 (death rule: `DifficultyIsCasual` 0x003AC324 tests bit 2 = **set**, `DifficultyIsPhoenix` 0x003AC820 tests bit 3 = clear; `SelectModeCasualItem::ACall` stores mode 1). The copy from the title's settings (0x006FEC18 +115/+116) into GameUserData was not traced: [high] for the bytes, [med] for "0 = Normal" through that copy |
| 2 | Shared prologue, one battle, forecast opened once | **reached** [high] | route `bt-prologue`: 17460 current `map__anonymous_namespace__ProcSequence` under `map__SequenceHuman` (the forecast; the sheet shows Corrin vs the Fighter with hit rates), 17600 `ProcBattleInfo` + `BattleSeq` (battle screen); the route byte stays 0 and no route is chosen before Chapter 6 |
| 3 | Route choice: Birthright | **reached** [high] | route `bt-ch6-castle`: 11714 `anonymous_namespace__EventDialog@00626DB0` (the branch dialog; its first item, the white kingdom, is the default) + A; 11861 `EventDialogYesNo@00626F30` + LEFT, A; 13043 GameUserData+0x2E = **0** (Birthright, docs/ROUTES.md) on the chapter-6 map that follows, whose cast is the Hoshidan side (Ryoma, Hinoka, Takumi as allies, Xander as boss); the castle then offers the Hoshidan (Dawn) armory. Not checked separately: which Scripts/A file was loaded |
| 4 | Early Birthright | **reached** [high] | chapters 6 and 7 cleared (route `bt-ch7`: rout the enemy, 24 turns; 87016 stage complete, enemy count 0); chapter 8 cleared (round 4, route `bt-ch8`: rout the enemy, 16 turns, both dragon veins used; 77839 stage complete with units [9, 0, 1], i.e. no enemy left; save `bt-ch8-clear`); chapter 9 (round 5); chapters 10 and 11 cleared (round 8, routes `bt-ch10` / `bt-ch11`: rout, 17 turns each; 127815 / 139862 stage complete with units [12, 0, 0] / [8, 0, 0]; saves `bt-ch10-clear`, `bt-ch11-clear`); chapter 12 escaped (round 9, route `bt-ch12`: Corrin uses the vein at (17,15), crosses the ice, escapes at (13,1) after 39 turns, nobody lost; save `bt-ch12-clear`, section 3f) |
| 5 | Shop | **reached** [high] | route `bt-castle-shop` (from bt-ch6-clear): the forced first build is the Rod Shop instead of the armory; 7634 `castle__CastleBuildingTopMenu` + `VisitBuildingSeq` inside it, 7932 `anonymous_namespace__ItemBuyMenu@0063CB08` (its goods list), one Vulnerary bought: gold (GameUserData+0x38, read by `anonymous_namespace::GoldGet` 0x003B0660) 5000 at 3861, **4700** at 8330 |
| 6 | Armory | **reached** [high] | 30807 `castle__CastleBuildingTopMenu` + `castle__anonymous_namespace__VisitBuildingSeq` (Dawn Armory, Buy/Sell), 31056 its buy list (`UnitItemViewer@0063C690`); nothing bought |
| 7 | Forge | **reached: a weapon at +1** [high] | round 5, route `bt-ch9-ore` (from bt-castle-forge, through chapter 9): no ore building is offered after chapter 9 (build list: Arena, Prison, Lottery Shop, Mess Hall, Accessory Shop, Dawn Dragon, statues; the ore springs of castle_building.bin come later), so the chapter-9 Dragon Vein point built a **Lottery Shop**; its free daily draw gave **1 Coral** (`state.ore` slot 7 = naginata ore, castle_gemstone.bin's 7th row; 157201). Dawn Armory > Subaki > Iron Naginata (gold 13700 -> 12700, `forge_pairs` 2 at 159270), Smithy > Forge > Subaki: 160463 refine menu (Coral 1), combine, Yes, name kept: **161568 `forged` = [{where 11 (Subaki), item 71, rank 1}], `forge_max` 1**, ore all 0, screen "Iron Naginata +1" (Mt 6 -> 8). Saved: `bt-castle-ore`. Round 4's refusal (no Pearl for Hana's katanas) stays in `bt-castle-forge` |
| 8 | Convoy | **reached** [high] | castle X (Preparations) > Inventory > Corrin > Items: 31833 `sortie__property__PoolMenu` (the convoy pool beside the unit's items, stock 0/50) |
| 9 | One support | **reached (conversation)** [high] | route `bt-ch8-support`: chapter-8 preparations > Support (TALK! on Corrin, Felicia, Sakura) > Corrin > Felicia: 5668 `TalkKeyWait` under `anonymous_namespace__ProcSequence@0063FBD0`, between two `RelianceMenu@0063FD98` frames (5338, 9529). Support read (`state.support_c`: pairs of player units at C or more, from the game's own Reliance tables): **0** at 5338, **1** during the Felicia talk, **2** after (the A presses also ran Corrin-Sakura's C). The points came from chapter 7 (Corrin + Sakura paired, Felicia's heal): 2 of 3 each after it; viewing the talk raises them to 3 = C. Round 8 (`bt-ch10`, castle before chapter 10): five more talks viewed (Corrin-Sakura, Corrin-Kaze, Corrin-Azura, Kaze-Hana C, Felicia-Saizo C), `support_c` **6** at chapter 10's preparations (7980), **7** at chapter 11's (6699, after Silas-Orochi in `bt-ch11`); best pair 10 points. Kaze-Hana and Felicia-Saizo show S as possible (the child pairs) |
| 10 | One dragon vein | **reached** [high] | route `bt-ch3`: Corrin on the vein at (9,13) > first command > confirm: 15595 current `map__trick__anonymous_namespace__ProcMutation`; that vein's TrickData state 1 -> 2 (bit 0 usable cleared): `veins_used` 0 at 5128, 1 at 27474. Chapter 4 used more (`bt-ch4` 12522, 22863; `veins_used` 3 at 29223) |
| 11 | One Attack Stance follow-up | **reached** [med-high] | route `bt-ch2`: Corrin attacks from beside Felicia; the forecast at 10298 carries the stance label; battle frames 10700 (Corrin's attack shown as base + 4) and 10900 (Felicia striking) on the contact sheet; the live capture of that route met `unit_attack_stance_bonus` and `stance_attack_bonus_total` (0 mismatches). No memory read names "the ally struck" yet |
| 12 | One Guard Stance pair | **reached** [high] | route `bt-ch3`: Gunter > Pair Up > Corrin on the gate tile; 27474 `paired_player` = 2 (Unit.state_flags: Corrin bit 1 lead, Gunter bit 2 partner, both at (16,14)); 5128 `paired_player` = 0. Chapter 4 has a second pair (Rinkah + Kaze). A block was not needed |

## 2. Routes (config/harness/routes.json)

All start from `build/harness/saves/new-game-empty.zip` (`--save new-game-empty`, an empty zip: no game
save, so the game makes its save and its SD-card extra data in the scratch folder). Frames are boot.exe frames.

| Route | Inputs | Frames | What the shots show |
|---|---|---|---|
| `title` | 400:A, 800:A, 1200:A, 1600:A, 2100:START | 3000 (save_at 2990) | 300 save-initialization prompt; 700 its done notice; 1100 SD extra-data prompt; 1500 its done notice; the intro movie from about 1800, START skips it; title screen from about 2300 |
| `new-game` | `title`, then 3000:A, 3400:A, 3700:A, 4000:A | 4600 (save_at 4590) | 3300 main menu (New Game / Extras); 3600 difficulty list; 3900 mode list; 4590 avatar creator, body type |

Birthright routes (stage B). Each starts from the packed in-game save of the piece before it (the
route's `save` field; `headless.py --pack RUN NAME` makes the zip from a finished run's scratch save
folder), so a later piece never replays earlier chapters. Loading a save: 300:A, 700:A (SD extra-data
prompts: the zip holds savedata only), 1200:START, 1500:START (movie, title), 2000:A Continue, 2400:A
slot 1, 2800:A, 3200:A.

| Route | Start save | Frames | What it does | Packs |
|---|---|---|---|---|
| `bt-prologue` | new-game-empty | 47,610 | new-game, avatar creator with defaults (START jumps to OK; name kept; Yes needs LEFT), SpotPass question answered No, slot 1, Prologue (Corrin attacks the Fighter, scripted scenes, Takumi finishes the Lancer), Chapter 1 (three attacks on the boss), save | bt-ch1-clear |
| `bt-ch2` | bt-ch1-clear | 20,040 | Chapter 2: wait three turns, Attack Stance kill (Corrin beside Felicia), Gunter and Felicia finish | bt-ch2-clear |
| `bt-ch3` | bt-ch2-clear | 34,240 | Chapter 3 (canyon): dragon vein bridge, archer and samurai, boss, Pair Up on the gate, Felicia seizes | bt-ch3-clear |
| `bt-ch4` | bt-ch3-clear | 36,860 | Chapter 4 (snow): two veins, a pair, the boss; allies clear the rest | bt-ch4-clear |
| `bt-ch5` | bt-ch4-clear | 43,050 | Chapter 5: feral-dragon Corrin, a heal from Sakura, the boss | bt-ch5-clear |
| `bt-ch6-castle` | bt-ch5-clear | 32,640 | Chapter 6 branch dialog (Birthright), Ryoma beats the boss, save, My Castle: forced build tutorial (Dawn Armory), walk in, armory buy list, Preparations > Inventory (convoy), Support list | bt-ch6-clear (the chapter-6 save, made before the castle) |
| `bt-castle-shop` | bt-ch6-clear | 10,260 | Round 3. The first castle visit again (the chapter-6 save comes before it): build tutorial with the **Rod Shop** (second item), placed 10 tiles right of the armory's spot (red/pink placement is refused, blue accepted), walk to its door, Buy > Corrin > Vulnerary > Yes, Preparations > Support (no rank lit), Save | bt-castle-shop |
| `bt-ch7` | bt-castle-shop | 95,000 | Butler > Next Battle, world map Chapter 7 > Yes, Fight! > Yes. Chapter 7 (rout 11 enemies): Sakura pairs with Corrin on turn 1 and the pair fights an axe fighter, both lancers, the knight and the boss; Rinkah and Kaze finish weak enemies, the march south for the last four; stage complete after 24 turns, save | bt-ch7-clear |
| `bt-ch8-support` | bt-ch7-clear | 10,530 | Chapter 8 preparations: Support > Corrin > Felicia, the C conversation, A through it (and Corrin-Sakura's C), Preparations > Save. Chapter 8 not played | bt-ch8-support |
| `bt-ch8-pair` | bt-ch8-support | 9,800 | Fight!; turn 1 Sakura pairs with Corrin; turn 3 Switch makes Corrin the support (for `stance_guard_bonus_edit`); enemy phase. No save | - |
| `bt-ch8-options` | bt-ch8-support | 6,900 | Round 7, look only: chapter 8's first player phase, system menu > Options, every one of the 25 lines (DOWN only), B; system menu > Units, its Battle page, the last unit, back to the first page, B, B. Nothing changed (3d) | - |
| `bt-ch8` | bt-ch8-support | 78,900 | Round 4. Fight!; chapter 8 (desert, 11 enemies, 3 green allies, rout): turn 1 Sakura uses the vein at (11,15) (the "desert/plain" tiles become plain), Corrin hits the samurai, **Rinkah kills it and levels up** (6860 before, 7870 after); turn 4 Corrin uses the vein at (9,12) (the northern plain); oni, archer, diviners pushed back; Corrin with the Dragonstone (Y on the forecast switches the weapon) hits the boss, whose counter-attack on the enemy phase finishes him (the map goes on: rout); Hana kills the last shrine maiden on turn 16; stage complete, save slot 1, castle. Rinkah and Orochi fall (Casual) | bt-ch8-clear |
| `bt-castle-forge` | bt-ch8-clear | 12,600 | Round 4, row 7. Build > Smithy (new), placed 8 down, 9 right, 8 down of the throne; enter, back out; Build > Dawn Armory below it (the last point); walk round to its door; Buy > Hana > Iron Katana, Yes; walk back; Smithy > Forge > Hana > Iron Katana: refused (Pearl 0); back out; START > Save > slot 1 > Yes | bt-castle-forge |
| `bt-ch9` | bt-castle-forge | 147,400 | Round 5. Butler > Next Battle, Chapter 9 > Yes, Fight! > Yes. Chapter 9 (Izumo maze, rout): turn 1 a touch on the bottom screen's arrow (`@305x15`) turns on the unit panel's detail view (Atk/Hit/Crit/Avo), Kaze and Asama wait, **Azura Sings to Asama**; Corrin holds the doorway (13,19); reinforcements from turn 3 (mages, cavaliers); the army marches west and north through the maze; Azura sings three more times (Saizo, Kaze twice, Corrin; her level 2 comes from the Sing to Kaze, 88990 -> 90290); turn 18 **Sakura uses the holy-tree dragon vein at (22,9)** (heal all); the boss Zola on the throne heals each turn (29 -> 35 seen), so he falls only to a one-phase burst: Kaze's shuriken (lowers his defence), Saizo, Silas, Corrin with Saizo's follow-up (35 -> 4), throne heal to 11, Saizo the next turn; stage complete after 19 turns; save slot 1; castle. Tsubaki and Orochi retreat (Casual) | bt-ch9-clear |
| `bt-ch9-ore` | bt-castle-forge | 162,800 | Round 5, row 7. The whole `bt-ch9` input, then: Build > Lottery Shop (placed 7 down, 9 left of the throne, the first blue spot), walk to it, Dawn Lottery > Yes: 1 Coral; walk to the Dawn Armory, Buy > Subaki > Iron Naginata, Yes; walk to the Smithy, Forge > Subaki > Iron Naginata, combine, Yes, name kept (START, Yes): **+1**; START > Save > slot 1 > Yes | bt-castle-ore |
| `bt-ch10` | bt-ch9-clear | 129,000 | Round 8. Castle Preparations > Support: five talks (START skips each). Butler > Next Battle, Chapter 10 'Ninja Village' > Yes, Fight! > Yes. Chapter 10 (forest, rout 17): turn 1 Hana pairs with Kaze, Felicia with Saizo; turn 2 an enemy Takumi (archer) appears beside the army and falls to Corrin, Silas/Orochi and Saizo (he joins after the map anyway); Asama heals, Azura Sings several times (the "wait" of a unit beside an ally that has acted picks Sing, the menu's first item); the west cleared by turn 7, then north-east and down the south corridor; Kaze and Saizo kill the last shrine maiden, Corrin beats Kotaro on turn 17 (his Kodachi to the convoy); save slot 1, castle. No unit lost | bt-ch10-clear |
| `bt-ch11` | bt-ch10-clear | 141,000 | Round 8. Support: Silas-Orochi. Next Battle, Chapter 11 'To the Sea'; Select Units: Subaki out, Takumi in. Chapter 11 (a ship in a storm, rout 17 + reinforcements: wyvern riders and invaders, pegasus and Kinshi knights, a falcon knight, the boss): the pairs again; four turns on the lower deck (Takumi and Corrin kill what flies in), then the march west over the main deck; Corrin talks to the green Kinshi knight Reina, who joins and beats the boss in an enemy phase; the last falcon knight and invader fall on the lower-left deck on turns 16-17. Silas, Orochi, Azura, Sakura, Rinkah retreat (Casual); save slot 1, castle | bt-ch11-clear |

Round 8 (`parallel.py runs --markers --copies 2`, FEF_ROBOT_JOBS=3 for the runs + 1 look-ahead, FEF_ROBOT_MEM_GB=2.7,
below-normal; sessions r8bt-ch10a, r8bt-ch11a): `bt-ch10` both copies memory `8008b04b09daa94c`, `bt-ch11` both
`d886b7b1487ec2bb`; the in-game save files of the two copies are byte-identical (Chapter0, Global, Exchange, Rating;
the zips differ only in file times). Saves packed from copy 1 with `parallel.py pack`: `bt-ch10-clear.zip` sha256
`76ef3506...`, `bt-ch11-clear.zip` `e96abafd...`; both load (bt-ch11 and the chapter-12 look-ahead start from them).
Capture runs (sessions r8bt-ch10cap, r8bt-ch11cap, `--mode capture --markers`): **checkpoints all met**, memory equal
to the original runs, 87 overrides met each, 1,866 / 1,895 records, 1,795 / 1,845 match, 26 / 25 gave up, 45 / 25
incomplete, **0** mismatch_r0 / regs / mem / calls, b_escaped, unfaithful, escaped, damaged: PASS. The library was
used as it was: `build.py --check-fresh` says STALE (config/harness/targets.csv changed by another workflow since the
build); writer totals NOT REPORTED (library built before them).

Cheat routes (round 6, docs/CHEATS.md; named `cheat-*`, `"cheat": true`, scored apart, never a parent of the
routes above): `cheat-forge-katana` (from bt-ch8-clear; packs cheat-castle-katana), `cheat-skill-proc` and
`cheat-family` (from bt-ch8-support; battle saves cheat-ch8-lethality, cheat-ch8-family). Section 3c.

Marker runs of all six (and of the four round-3 routes; `harness.py headless --run mk-<route> --route <route> --mode original --markers`):
**checkpoints: all met** on every route [high]; their savestate memory hashes equal the first from-zero
replays of the stitched inputs (e.g. bt-prologue `a3e4ec17...`, bt-ch2 `059736d3...`, bt-ch3 `98dc9c69...`).

Round 4 (`parallel.py runs --markers`): `bt-ch8` checkpoints all met; two from-save runs ended at the same
savestate memory `bee8415f...` (353,561,630,400 instructions); `bt-castle-forge` checkpoints all met, memory
`d6f814c6...` in all five runs of it. The saves were packed from the kept job folders with `parallel.py pack`
(`bt-ch8-clear.zip` sha256 `0aa4eb5d...`, `bt-castle-forge.zip` `3e69798a...`; packing again gave the same bytes).

Round 5 (`parallel.py runs --markers`, FEF_ROBOT_JOBS=12, below-normal; sessions r5-a and r5-b): `bt-ch9` and
`bt-ch9-ore` each replayed from frame 0 of the bt-castle-forge save, twice: memory `eb41cae1...` (bt-ch9) and
`25a4d7e8...` (bt-ch9-ore) in both sessions, **checkpoints all met** (r5-b, after the checkpoints were written from
r5-a's reads). 553-556 s and 585-591 s per run (2.7 ms per frame with 10-12 dumps), peak 606 / 706 MB.
Saves packed from r5-a with `parallel.py pack`: `bt-ch9-clear.zip` sha256 `17a65b97...`, `bt-castle-ore.zip`
`022f5e1b...`; loading bt-castle-ore (probe `chk-ore`, 4390) shows gold 12700 and the +1 naginata (`forged`
[{11, 71, rank 1}]): the forge survives the save. `bt-ch9-ore` is not chained off bt-ch9-clear: it repeats chapter 9
because the lottery's prize depends on the game's random state, which a fresh load of the save would change (not
tried); bt-ch9 is its first 147,400 frames.

How the inputs were found (build/harness/robot/, tools in tools/harness/robot/): savestate look-ahead
(ZAKURO_LOAD from a scratch state, a few hundred frames per try, about 1-6 s), an autopilot that answers
screens which need no decision by their marker class (talk: START then A; tutorial and movie: START;
chapter-complete: A; never START inside a battle, it pauses it), and a one-action helper that reads the
board (units, HP, cursor at `*0x006D7198`, terrain grid, dragon veins) from a dump, moves the cursor,
selects, tries destination candidates in order, opens the forecast and confirms. The stitched input of
each piece was then replayed from frame 0 (or the piece's start save) with markers; savestates never
enter a route.


The copied Awakening title timings (700:START, 1000:A) were nothing like Fates': Fates first asks
four questions on an empty save (two save-initialization prompts, two SD extra-data prompts), and
the intro movie starts only after them. [high]

## 3. Screen markers: memory reads (config/harness/markers.json, tools/harness/markers.py)

Zakuro's screen markers (patch 0001) only run for Awakening, so Fates uses memory. A marker run
(`harness.py headless ... --markers`) has boot.exe dump at each shot frame (ZAKURO_DUMP_MEM +
ZAKURO_DUMP_MEM_AT) the two process roots and the linear heap (0x30000000, 0x037C5000 bytes: the
mapped part on this boot; the game's objects live there, the 0x08000000 heap is only 1.5 MiB). The walk:

- roots: three list heads at 0x00752B48 (Proc::KillByName 0x0010FD20); tree links +16 parent, +20
  first child, +28 next sibling, +40 bit 0 dying (ProcInst::FindNext 0x0011D318); +44 name hash.
- current screen: MainSequence::GetCurrent 0x001B5F70 from `*0x006D88D4`, the last child with +41 set.
- class: a process's vtable is read from `extracted/code.bin` (static, not dumped); its destructors'
  names in config/functions.csv give the class. A file-local class (`anonymous_namespace__X`) gets
  `@vtable` added: several files have their own anonymous ProcSequence.
- only class names reach run.json; the dumps are deleted with the run's tmp folder.

Checkpoints seen (runs `title-markers`, `ng-markers`; all met on reruns) [high]:

| Route, frame | Screen | current | also live |
|---|---|---|---|
| title 300 | save initialization prompt | `GameMessage` | `Backup__anonymous_namespace__ProcError` |
| title 1100 | SD extra-data prompt | `GameMessage` | `link__anonymous_namespace__ProcInit` |
| title 2990 | title, press any button | `ProcEffect` | `anonymous_namespace__ProcSequence@00640B64` (the opening sequence; its destructor 0x0033AD4C sits beside ProcSequence::PlayMovie), `ProcScene` |
| new-game 3300 | main menu | `title__TopMenu` | `title__ProcTitle` |
| new-game 3600 | difficulty | `title__SelectDifficltyMenu` (sic, the symbol's spelling) | `title__ProcTitle` |
| new-game 3900 | game mode | `title__SelectModeMenu` | `title__ProcTitle` |
| new-game 4590 | avatar creator | `title__ProcMyUnitEdit` | `CutSceneMain` |

Dumping memory does not change the game: the marker runs' savestate memory hashes equal the plain
runs' (`c3cbbe48...` title, `d328d671...` new-game) [high]. Marker runs are still kept out of h4a (a
read of an unmapped page is noted in Zakuro's fault list, which is in the state's metadata).

Game-state facts (stage B, `markers.game_state`, config/harness/markers.json `state`): at every marker frame
the walk also reads, through the game's own globals, GameUserData's difficulty (+0x2D), death-rule flags
(+0x28 bit 2 Casual, bit 3 Phoenix) and route (+0x2E); the unit counts per force and every paired unit
(Unit.state_flags bit 1 lead, bit 2 partner; `paired_player` counts force 0 only, since chapter 3 starts
with an enemy pair); and the dragon veins (TrickData type 11) with how many are used (state bit 0
cleared). Only these numbers reach run.json. A checkpoint can require them (exact value, or `min:N`).
The board reader used while playing (tools/harness/robot/units.py) adds positions, HP, the map cursor
(`*0x006D7198` points at two int32: x, y) and the terrain grid (G_MapImage +0x808) with this chapter's
terrain names (the TerrainTile records, found in the heap by their TID_ labels).

Round 3 adds two reads to `state` [high: each read through the function named, checked against the screen]:
`gold` (GameUserData+0x38, `anonymous_namespace::GoldGet` 0x003B0660; 5000 -> 4700 after a 300 G buy) and
the support counts `support_pairs`, `support_c`, `support_points_max` (markers.support_pairs): Unit+0x9C
Person; Person+0x30 int16 support row, +0x24 id; `*0x006D3BD0` (Reliance::GetFromPerson 0x004F0FDC) is a
table of bucket chains by row & 127 (node +0 record, +4 next); a record holds +0 row, +2 count, then
12-byte entries (+0 partner id, +2 slot, +4..+7 the C/B/A/S thresholds, Reliance::GetLevel 0x00546878);
the points are byte [slot] of Unit+0x11C (Unit::GetReliance 0x0052C260). A ready conversation sits one
point below C; viewing it adds the point (the read goes 0 -> 1 -> 2 across the two talks).
New screens: build list `castle__anonymous_namespace__M_Building`, Build/Move menu `M_Top`, world map
`castle__anonymous_namespace__M_SpotSelectTop`, shop goods `anonymous_namespace__ItemBuyMenu@0063CB08`
(with `UnitItemViewer@0063C690` current), yes/no `GameDialogYesNo`, support talk `TalkKeyWait` under
`anonymous_namespace__ProcSequence@0063FBD0`, unit command after Switch `map__anonymous_namespace__UnitCommand`.

Round 4 adds three reads to `state` [high: each read through the functions named, checked against the screen]:

- `levels` (markers.unit_levels): per person id (Person+0x24) of every unit in force 0 (the army on a map) and
  force 3 (the army in My Castle: in a castle dump force 0 is empty and the 13 units are listed under force 3):
  `lv` = Unit+0xF1 (Unit::GetShowLevel 0x0052DC44; Unit::LevelUp 0x003D8154 adds 1 to it), `exp` = Unit+0xF2
  (Unit::ExpNormalize 0x0052D34C caps it at 100), `gain` = Unit+0xC8 s8[8] (Unit::LevelUp adds each stat's
  rise there), `stats` = Person.base (+0x38) + Job.base (+0x1C) + gain, the raw stat of docs/TABLES.md before the
  class cap and before the avatar's boon/bane edit (so Corrin's numbers are a little off the stat screen; the
  other units' match it, e.g. Rinkah's Skl +1 at the level-up; the stat numbers stay out of tracked files,
  checkpoints name the level, the experience and the gains). A checkpoint can name one value with a dotted
  key: `"levels.6.lv": 6`.
- `forged`, `forge_max`, `forge_pairs` (markers.weapon_items): every weapon held by forces 0/3 (five
  unit::Item at Unit+0x108, Unit::GetHasItemNum 0x0052E594) or in the convoy (*0x006D95E8, 500 entries of 8
  bytes, +4 count, Transporter::Get 0x001A744C), with its refine rank = bits 8..13 of the item's second u16
  (unit::Item::GetRefineRank 0x0053B278 / SetRefineRank 0x0041978C). Only for weapons (Item::IsWeapon
  0x00529164 through Item::Get 0x003D0EAC and ItemSubKind::Get 0x0019B97C): for staves and items the same bits
  are the uses (Sakura's Bloom Festal reads 18 there). Checked on a real dump: Yato, Dragonstone, club,
  shuriken, katana, sword, lance, naginata, tome = weapon; HP Tonic, Vulnerary, both festals = not.
  `forge_pairs` counts like weapons (same holder, item, rank; a convoy entry's count) that the smithy could fuse.
- `ore`, `food` (markers.castle_stock): the castle's stock, *0x006D1998 (Castle::Get 0x0044544C) +8 -> ->
  CastleUserData; +0xD4 -> one byte per ore (castle::CastleUserData::GetGemstoneNum 0x00540AD4), +0xD8 -> food
  (GetFoodNum 0x00540A3C); kinds = castle::Gemstone::GetNum / castle::Food::GetNum (12 and 10 here, the same as
  the castle screen's two panels). Kaze's castle gift (a berry) shows as food [.., 1, 0]; ore stays all 0.

New screens: forge `anonymous_namespace__ItemRefineMenu@0063B444`, forge unit list
`anonymous_namespace__UnitItemViewer@0063B084`, Ore Swap `anonymous_namespace__GemstoneMenu@0063B888`, the
castle's placement mode `castle__anonymous_namespace__Sequence`, staff target `map__anonymous_namespace__ProcSequence`
(same class as the forecast), item list `map__anonymous_namespace__ItemMenu` / `ItemMenuPanel`.

Stage B screens (all in markers.json checkpoints):

| Screen | current | also live |
|---|---|---|
| map, player phase | `map__SequenceHuman__anonymous_namespace__ProcSequence` | |
| unit command menu | `map__anonymous_namespace__UnitCommand` | |
| combat forecast / target choice | `map__anonymous_namespace__ProcSequence` | `map__SequenceHuman__...` (the chapter objective screen has the same current, with `ProcScene`) |
| battle | `ProcBattleInfo` | `BattleSeq` |
| talk / tutorial / movie | `TalkKeyWait`, `ProcTutorialViewer`, `ProcMovie` | in a battle, `ProcTutorialViewer` can stay current under `BattleSeq` |
| dragon vein effect | `map__trick__anonymous_namespace__ProcMutation` | |
| map yes/no (seize) | `map__DialogYesNo` | |
| system menu (End turn is its last item) | `map__anonymous_namespace__SystemMenu` | |
| stage complete | `map__SequenceCompleteEffect__anonymous_namespace__ProcSequence` | |
| save slots | `ChapterFileMenu` | |
| route branch / confirm | `anonymous_namespace__EventDialog@00626DB0` / `EventDialogYesNo@00626F30` | |
| castle: free walk / butler / building menu | `castle__Sequence` / `castle__anonymous_namespace__M_Butler` / `castle__CastleBuildingTopMenu` | `castle__anonymous_namespace__VisitBuildingSeq` inside a building |
| Preparations / unit list / convoy / support | `sortie__anonymous_namespace__TopMenu` / `sortie__anonymous_namespace__UnitSelectMenu` / `sortie__property__PoolMenu` / `anonymous_namespace__RelianceMenu@0063FD98` | |

## 3a. Level-ups on the routes (for the growth batch's live compare) [high]

Round 4 marker runs of every bt-* route (`parallel.py runs --markers`, session r4-levels, 6 at once, 498 s; every
checkpoint met, every memory hash equal to the committed runs') read `state.levels` at each shot;
`tools/harness/levelups.py SESSION` lists each unit whose level rose between two shots. Person ids: 1 Corrin,
4 Felicia, 6 Rinkah, 7 Kaze, 8 Sakura, 9 Azura, 10 Hana, 11 Subaki, 12 Silas, 13 Saizo, 16 Asama.

| Route | Level-ups between shots (person: level, frames) |
|---|---|
| `bt-prologue` | 1: 1 -> 2 (43794 -> 47124, chapter 1) |
| `bt-ch2` | none seen between shots |
| `bt-ch3` | 1: 2 -> 3 (15595 -> 27474) |
| `bt-ch4` | 1: 3 -> 4 (22863 -> 29223) |
| `bt-ch5` | 1: 4 -> 5 (5306 -> 26624), 5 -> 6 (26624 -> 40030) |
| `bt-ch6-castle` | none seen (Ryoma, a guest, does the fighting) |
| `bt-castle-shop`, `bt-ch8-support`, `bt-castle-forge` | no battle |
| `bt-ch7` | 1: 6 -> 8 and 8 -> 9; 4: 1 -> 2; 6: 4 -> 5 (19783 -> 55489 -> 87016) |
| `bt-ch8-pair` | none (three turns) |
| **`bt-ch8`** | **6: 5 -> 6 between 6860 and 7870, one battle (the checkpoint, Skl +1)**; 1: 9 -> 12; 8: 1 -> 2 (16320 -> 77839) |
| `bt-ch9` (round 5, session r5-b) | **9 (Azura): 1 -> 2 between 88990 and 90290, a Sing (dance experience), no battle**; 1: 12 -> 13, 4: 2 -> 3, 7: 3 -> 5, 10: 4 -> 5, 13: 7 -> 9 (8273 -> 88990); 7: 5 -> 6, 12: 6 -> 7 (90290 -> 110154); 16: 7 -> 8 (110154 -> 136237, a heal) |
| `bt-ch9-ore` | the same chapter (fewer shots: 8273 -> 136237); no level-up in the castle part |

`bt-ch8` 6860 -> 7870 is the tight one: Rinkah's only action between the two shots is one attack (forecast at
6860, kill, level-up screen, back to the map at 7870), so a capture of the growth functions over that span sees
exactly one level-up. The others span many fights.

What the code shows (bodies read in asm/text, facts for docs/tracks/BATCH_GROWTH.md, which guessed from names):
`Unit::LevelUp` 0x003D8154 is the roll: it seeds a Random from Unit+0xC0, stores the next value back there,
adds 1 to Unit+0xF1, then for each of the 8 stats takes Unit::GetGrow (each full 100 is a sure point, the rest a
Random 0..99 below the rate), adds the point to Unit+0xC8[s] only while Unit::GetCapabilityImpl is under
Unit::GetLimit, and runs the whole pass again (at most 4 passes) when no stat's roll succeeded. `GrowSequence::LevelUpCalculate`
0x003D80FC is not a roll: it makes a new Unit, copies the levelling unit into it and lowers the copy's level by 1
(a "before" picture); `GrowSequence::LevelUpReflect` 0x003D4FD0 calls Unit::CopyForLevelUp and deletes that copy.
Experience is Unit+0xF2 (Unit::ExpNormalize 0x0052D34C: at most 100 per gain, none at the level cap).

## 3b. Round 5: never-met readers, which route meets which [high: callers decoded from code.bin, BL/BLX]

Callers were found by decoding every ARM BL/BLX in extracted/code.bin (gen_stubs.call_target) and naming the
caller from config/functions.csv. The live compare itself is the integrate stage's (no capture library was built
this round).

| Reader(s) | Who calls them in the game | Route that meets them |
|---|---|---|
| `exp_table_dance` (ExpTable::GetDance 0x004E634C), `unit_exp_dance` (Unit::GetExpDance 0x0052BAD0) | GetDance only from GetExpDance; GetExpDance only from `map::SequenceDance::ProcDance::Grow` (the Sing/Dance experience step) | `bt-ch9`: five Sings (Asama at 7.4k, Saizo, Kaze twice, Corrin); Azura 0 -> 17 at the first (8273), and her level 1 -> 2 comes from the Sing to Kaze between 88990 and 90290 (a level-up with no battle in the span). Also `bt-ch9-ore` (same input) |
| `unit_hit_of_slot`, `unit_avoid_of_slot`, `unit_crit_of_slot`, `unit_attack_of_slot` (GetHit(int,bool) 0x00532D90, GetAvoid(int) 0x005334F0, GetCritical(int) 0x0052B988, GetAttack(int,bool) 0x005342B8) | only `ViewerUnitStatus::DrawBattleAbilities` (the unit panel's detail view: Atk/Hit/Crit/Avo) and `UnitListMenu::UnitListBaseMenuItem` (OnDraw and constructor: system menu > Units, its "Battle" page); GetAvoid(int) also `map::CannonCalculator::Calculate` | `bt-ch9` / `bt-ch9-ore`: input `6965:@305x15` is a touch on the panel's arrow (Zakuro's `@XxY` touch token): the detail view stays on for the whole chapter, so every unit under the cursor draws its battle abilities. The Units list was opened only in a look-ahead (7441 `UnitListMenu__UnitListMapMenu`, Battle page with Atk/Hit/Crit/Avo), not in a route |
| `unit_attack_for_terrain` (GetAttackForTerrain(const Item*) 0x00534180), `unit_attack_for_terrain_of_slot` (GetAttackForTerrain(int) 0x005309A0) | not fort or throne fights: (Item*) only from `map::anonymous_namespace::ProcSequence::Persistent` 0x00389258; (int) from `map::SequenceBattle::ProcSequence::Destroy` / `DestroyRuin` and `AIThink::GetDestroyScore`, i.e. attacking a breakable terrain object | **not met**: chapter 9's terrain kinds (none, plain, wall, floor, stairs, throne, door, chest, sacred tree) have no breakable object; the boss fought on the throne all game, which does not call them. Needs a map with a breakable wall or ruin (which Birthright chapter has one was not checked) |
| `script_unit_can_dragon_vein` (event script command `UnitCanDragonVein` 0x003ABD8C) | the command name appears only in Scripts/C/C012, C018, C020, C025 (folder C = route 2, Revelation) and Scripts/X015 (a Conquest/Revelation paralogue, docs/ROUTES.md) | **not reachable on Birthright**: no A/ (Birthright) chapter script and no shared script uses it. The map's own vein command is `unit_can_dragon_vein` (met since stage B; `bt-ch9` uses the vein at (22,9) through it) |
| `family_grow`, `family_parent_grow`, `family_limit` (unit::Family::GetGrow 0x0053B6CC, ParentSingle::GetGrow 0x0053B740, Family::GetLimit 0x0053BDC4) | only from Unit::GetGrow (call at 0x00533164) and Unit::GetLimit (0x00533828), for a unit with family data (a child) | **not met; what it would take**: a child unit. Children come from child paralogues (Birthright and Revelation: CID_X007-X014, docs/ROUTES.md), each opened by an S support of the parent; this save has two C supports (Corrin-Felicia, Corrin-Sakura). It would take B, A and S for one pair (more chapters or castle talks) and then that paralogue's map |

Chapter 9 also showed: the green allies Oboro and Hinata (force 2 at first; Oboro is listed in force 0 later with
state bit 0x100); dragon veins here are the four holy trees (TrickData type 11 at (23,23), (22,9), (3,23), (4,9));
the chapter's terrain script (A009_Terrain.cmb) heals every unit of the user's side and plays a stat-up sound cue (its Japanese name is left out: no game text in tracked files)
(no stat change was seen in the next forecast); the chests hold a speed item and 5000 G (strings in that script,
not opened). The win rule is `ChapterSetWinRuleEnemyNumberLessThanOrEqualTo` (rout: the boss must fall too).

Ore sources (callers of castle::CastleUserData::AddGemstoneNum 0x00457178): the lottery (`ProcSequence::PlayLottery`),
castle gifts (`event::Informal::ProcGemstone::GainGemstone`, `GetRandomGemstone`), the arena (win and lose events),
map material pickups (`map::SequenceHelper::MaterialGain`, `ProcGainMaterialFromTrick`), StreetPass exchange,
Ore Swap, prisoner scouting costs and the forge itself. The ore springs and rock mounts of castle_building.bin
(the Pearl Spring, its building id a Japanese label not quoted here; ore slot 6, the katana ore) were not in the build list after chapter 9.

## 3c. Round 6: harness truth fixes and the cheat track [high]

**Truth fixes (review round 5 and Grok review 4).**

- `parallel.py` capture runs: a reviewer planted a wrong `unit_has_skill` (returning 2): 52 `mismatch_r0`
  records in summary.tsv, both runs still printed PASS and the boot.log had no MISMATCH line (its
  `[fe-capture]` lines are capped). Now every summary.tsv of a capture run is read (a cheat run has one per
  stage); any `mismatch_r0`, `mismatch_regs`, `mismatch_mem`, `mismatch_calls`, `b_escaped`, `unfaithful`,
  `escaped` or `damaged` record, or no summary.tsv at all, makes the run FAIL, prints a `CAPTURE FAIL` line,
  and the session exits 1. (`mismatch_regs` and `damaged` are verdicts of the offline replay and report;
  capture.c never writes them into a summary.tsv, and they stay in the set only so that a summary carrying
  them would fail. `hostmem` and `truncated` are not counted as bad.) `harness.py h4a` now fails the same way
  on run A+B's summary.tsv files, and refuses cheat routes. One table per session adds the records up (real-play runs and cheat runs apart);
  the summary.tsv files are kept in `results/` (`<run>.summary.tsv`, `<run>.stage<k>.summary.tsv`). **A grep
  of the boot.log for MISMATCH is not a check**: the verdict is the summary.tsv. Test:
  `test_parallel.py CaptureVerdictTests` plants a summary.tsv with 52 `mismatch_r0` records.
- `robot/budget.py` lock (and `parallel.py`'s build lock): the lock file was created with O_CREAT|O_EXCL and the
  pid written after; a waiter that read it in between saw it empty, took it for a dead holder's, removed it and
  ran too. Both now use `parallel.OsLock`, a byte-range lock the OS holds for the process (freed when the holder
  closes it or dies, so nothing stale to take over). Tests `LockTests`: an emptied lock file while the holder
  lives is still held (and `budget.run_slot` in another process waits), four look-aheads never overlap, a
  killed holder frees it. The old budget.py fails these tests.
- `markers.unit_levels`: two units with one person id both survive (the first keeps `"6"`, the next is
  `"6#2"`); `levelups.py` sorts and compares such keys. Self-tests: markers 28/28 (new: the duplicate id; forge
  ranks 2, 5, 7, 31, 32, 63 with bits 14-15 set, which a 5-bit or 3-bit mask or a shift of 9 fails; a rank-3
  forge_max), levelups 3/3.
- Section 3b no longer quotes the two Japanese identifiers (a sound cue, a building id).

**The cheat track** (rules and mechanism: docs/CHEATS.md; tools/harness/cheats.py, self-test 23/23). A poke is
applied between two boot.exe stages: the run saves its state at the poke frame, the poke's path is followed in a
memory dump of the same moment, the byte(s) are checked and written into the savestate's FCRAM, and the next
stage loads the patched state. No engine change, no Zakuro build.

| Route | Pokes (frame) | Result | Runs |
|---|---|---|---|
| `cheat-forge-katana` (from bt-ch8-clear, 14,000 frames) | 3500: castle ore index 6 (the katana ore; castle_gemstone.bin lists the 12 ores by weapon kind) 0 -> 1 | 3640 ore [0,0,0,0,0,0,1,...]; 3760 Equip Skills > Corrin (`sortie__skill__PoolMenu`); the bt-castle-forge walk 400 frames later; 11634 Hana's refine menu with the Pearl; **12500 `forged` = [{where 10 (Hana), item 22, rank 1}]**, ore back to 0; saved 13300; the screen shows "Iron Katana +1" | checkpoints all met twice; DETERMINISTIC (62,735,904,000 instructions both); memory 3188fff1...; save **cheat-castle-katana** (first pack sha256 624cfdb2...; round 6b repack with the cheat mark d025ab23..., the same save files; loaded again by the cheat route `cheat-katana-reload`: forge_max 1 at the preparations, memory 47d34f0d... twice) |
| `cheat-skill-proc` (from bt-ch8-support, 6,420 frames) | 5100: Corrin's Unit.equip_skills[4] 0 -> 25; skill 25's trigger factor (Skill +0x17) 1 -> 100 | 25 is Lethality (the first of CalculateAttack's nine; its cached number read at 0x006D6724 after a fight). The activation cut-in at 5950-6050; **6400 enemies 11 -> 10 and Corrin exp 28 -> 55**: one attack killed the 22-HP samurai, which the same attack in bt-ch8 only weakens | then system menu > Save > slot 1 > Yes (a battle save); checkpoints all met twice; DETERMINISTIC (33,608,520,000); memory 371db3a3...; save **cheat-ch8-lethality** (first pack sha256 0566e52e..., round 6b marked repack 4bfb726d..., same save files, with extdata; loaded again: the map with enemies 10, Corrin exp 55) |
| `cheat-family` (from bt-ch8-support, 7,900 frames) | 6400: a family record at 0x337C4F00 (unused, all-zero top of the mapped linear heap; still intact at the end): +0 Corrin's Person, +0x14 Felicia's (`value_from`); Rinkah's Unit.family -> it; her Person.family_index (+0x2A) 0 -> 4 | Unit::GetGrow and GetLimit take the family path at her level-up (7450, Lv 5 -> 6, Skl +1 as in bt-ch8) | then a battle save as above; checkpoints all met twice; DETERMINISTIC (40,106,167,200); memory bb5ef48f...; save **cheat-ch8-family** (first pack sha256 7765d04b..., round 6b marked repack 33405b79..., same save files) |

A first try of the skill route used Rinkah's attack: her Brass Club cannot activate skills (the item flag
CalculateAttack tests), so nothing fired; Corrin's Yato can. A first family try with family_index 1 (a male
Person) took Family::GetGrow's fall-through path; 4 (female) takes the tail branch; neither is a BL, so
`family_parent_grow` (ParentSingle::GetGrow 0x0053B740, no BL caller anywhere in code.bin) showed no capture
record either way.

Capture look (the library as it stood: built 04:26, STALE because targets.csv changed after; the live compare
of record is the integrate stage's), session r6-cap-final2 (the routes as committed), cheat table:
`cheat-forge-katana` 760 records (749 match, 8 gave up, 3 incomplete), `cheat-skill-proc` 1094 (1043 / 18 / 33),
`cheat-family` 1292 (1255 / 18 / 19), **0 bad records of any kind**; an earlier session (r6-cap-final, before the
battle saves) printed the real-play table beside it: `bt-castle-forge` 395 (388 / 7), 0 bad.
Never-met overrides seen there: `unit_equipped_skill_count` 12 records, 12 match (cheat-forge-katana's Equip
Skills screen: this reader needs no poke, any preparations' Equip Skills > a unit meets it);
`unit_lethality_immune` 1 record, gave up (a cold one-time cache); `family_grow` 8 / 8 match; `family_limit` 25 / 25 match (REPLAY-CLEAN). Memory hashes in capture mode equal the original-mode runs.

Not met by a poke (what each would take, from code.bin's BL/BLX callers and the scripts):

| Reader | Why not |
|---|---|
| `skill_total` (EquipSkill::GetNum 0x001758F8) | one BL caller, `castle::anonymous_namespace::Seq::MainMenu` 0x00487DC0 (a castle menu beside the food/ore event code); which screen it is was not found |
| `script_unit_has_skill` (script `UnitIsEquipSkill` 0x003AB148) | the command appears only in Scripts/B/B028 (Conquest) and Scripts/X022 (a paralogue); no Birthright main chapter |
| `skill_effect_name` (0x00211BC4) | only `hfx::CreateSkillHit` calls it; it did not run for Lethality's activation |
| `family_parent_grow` | no BL caller (tail branch / fall-through only, above) |
| `unit_attack_for_terrain` and `..._of_slot` | need an attack on a breakable wall or ruin; no Birthright map with one was reached (not tried) |
| `skill_banners` (an option) | its replay now exists: `cheat-skill-proc` |

## 3d. Round 7: the options screen and the Units list, looked at, nothing changed [high]

Route `bt-ch8-options` (from bt-ch8-support, 6,900 frames; config/harness/routes.json): bt-ch8-pair's input to chapter
8's first player phase (4470), the cursor 5 tiles left onto empty desert, A opens the map's system menu (Units,
Guide, Options, Save, Auto, End). DOWN DOWN A opens the options screen (`anonymous_namespace__ConfigMenu@00636D34`):
25 lines, DOWN 25 times walks every one and wraps to the first; no LEFT/RIGHT/A/X (X is the screen's Reset). B leaves
with no dialog. Then A opens Units (`UnitListMenu__UnitListMapMenu`), RIGHT RIGHT to its Battle page (Atk, Hit, Crit,
Avo), DOWN 10 to the last unit, LEFT LEFT back to the first page, B, B: the player phase again. No save.

| Check | Result |
|---|---|
| Markers, 2 runs side by side (`parallel.py runs --markers`, session r7-opt2) | checkpoints all met in both; memory `7e5ff849...` both |
| Options block before / inside / after | new read `state.game_config` (markers.game_config: G_GameConfig 0x006DA0F8 -> GameConfigData +0x4 .. +0x16, the 19 bytes GameConfigData::Serialize saves): **the same 19 bytes at all 11 checkpoint frames**, from the player phase before the visit (4470) through every options line to the player phase after (6650, 6890) |
| Capture (`parallel.py runs --mode capture`, session r7-optcap; library built 08:10, STALE only for two new writer files of another workflow, core/writer.c and menu/menu_config_writer.c) | 40 overrides met, 866 records, 847 match, 11 gave up, 8 incomplete, **0 bad of any kind**; memory hash equal to the original runs |
| The 8 option-item GetValue readers (never met before) | **all met**, every record a match: `config_item_value` 24 records (4,895 calls), `config_battle_value` 21, `config_hp_gauge_value` 20, `config_distance_value` 20, `config_game_speed_value` 21, `config_ai_skip_value` 19, `config_danger_value` 19, `config_encounter_bgm_value` 18 |
| The Units list's slot forms | `unit_hit_of_slot` 23 records (22 match, 1 incomplete), `unit_avoid_of_slot` 23 (22 / 1 gave up), `unit_crit_of_slot` 23 (22 / 1 gave up), `unit_attack_of_slot` 23 (22 / 1 incomplete): met in a route from the Units list now, not only from the unit panel of bt-ch9 |

**The same route without the visit** (probes o7vis / o7ctl from the same save, the same cursor moves, the same
frame count; tools/harness/robot/probe.py, savestates compared offline):

- same instruction count (30,919,838,400); **GameUserData (0x400 bytes from G_GameUserData), GameConfigData and all
  24 units (0x140 bytes each, forces 0-2) byte for byte equal**;
- the whole memory hash differs (`7e5ff849...` vs `dbb995db...`, 653 FCRAM pages): freed menu objects, the
  sound and the screen. Not the game's data;
- found on the way: the Units list remembers its page in **GameUserData +0x44** (left on the Battle page it holds 2,
  0 otherwise; checked by leaving on page 3 and on page 1). The route goes back to the first page before leaving,
  so even that byte is unchanged. GameUserData is part of the game save, so leaving on another page would be saved;
- **a general random number generator at 0x00752B7C (16 bytes) moves with any system-menu visit**: opening the
  menu and closing it (A, B) already gives another value than not opening it; options-only and units-only visits gave
  the same value as each other. The fight random `G_BattleRandom` 0x00752B8C next to it is unchanged. With
  bt-ch8-pair's next turns replayed after the visit (frames shifted by 2,606, both runs 12,420 frames), GameUserData,
  GameConfigData and every player unit stay equal, but after one enemy phase **two enemy units stand on other tiles**
  (unit f1#5 x, unit f1#10 x and y) [med: that the generator at 0x00752B7C is what the enemy AI draws from was not
  traced]. So "the same memory at a following checkpoint" is not possible with a menu visit in this game: a robot
  route that opens any map menu changes the later enemy moves. Looking stores nothing in the options, units or save
  data.

## 3e. Round 8: Birthright chapters 10 and 11 [high unless tagged]

Same method as rounds 3-5 (savestate look-ahead from the packed save, then the stitched input replayed from frame 0
of that save, twice, with markers; then one capture run). The look-ahead tools were copied unchanged in method to an
own scratch folder (build/harness/robot/bt/tools: run names `btlook`/`btlk`, states in
build/harness/robot/states/bt/, the one-at-a-time lock of robot/budget.py kept, APPDATA below build/), so the three
agents of this round never shared a run folder. Two scratch helpers were added there: `path.py` (cheapest path on
the map's own terrain grid, per-map costs, the farthest free tile within a unit's move) and `march.sh` (every
unacted lead/solo unit steps toward a tile), which made the long marches of chapter 11 cheap.

| | Chapter 10 'Ninja Village' (`bt-ch10`) | Chapter 11 'To the Sea' (`bt-ch11`) |
|---|---|---|
| Win rule (Scripts/A/A010, A011) | `ChapterSetWinRuleEnemyNumberLessThanOrEqualTo` (rout), reinforcement labels Reinforce02-03 | the same rule, Reinforce01-10, 90, 91 |
| Map | 25 x 13 forest; terrain kinds none, plain, plain/bamboo spikes, spikes, woods, deep forest, door/plain, chest; three dragon veins (TrickData type 11) at (7,6), (11,7), (15,7), each tied to a type-12 area | 30 x 22 ship; storm, sea, wall, low wall, floor, floor/storm, stairs; three veins (7,11), (16,10), (24,11) tied to the storm areas |
| Start | 12 units, 17 enemies (7980) | 12 units (Takumi in, Subaki out), 17 enemies (6699) |
| Turns, end | 17; 127815 stage complete, units [12, 0, 0] | 17; 139862 stage complete, units [8, 0, 0] |
| Lost (Casual retreat) | none | Silas, Orochi, Azura, Sakura, Rinkah |
| Joined | Takumi, Kagero (in the chapter-11 list) | Reina (green -> force 0 after Corrin's talk; she beat the boss in an enemy phase) |
| Levels (markers `levels`, person id: start -> stage complete) | Corrin 13 -> 15, Saizo 9 -> 12, Kaze 6 -> 7, Silas 7 -> 8, Asama 8 -> 9, Azura exp 2 -> 70 (Sings) | Corrin 15 -> 16, Takumi 11 -> 14, Saizo 12 -> 13, Asama 9 -> 11, Kaze 7 -> 9, Rinkah 6 -> 7, Sakura 2 -> 4 |
| `veins_used` | **2** at 110240 and later, but no player unit used a vein [med: the enemy side or the map script cleared two veins' usable bit; not traced] | 0 |

What it met: no override that real play had not met before. Both capture runs met the same 87 overrides; compared
with the 8 earlier real-play capture sessions still in build/parallel/ (100 met), 10 overrides of
config/readable/functions.csv are still never met in real play: `family_grow`, `family_parent_grow`, `family_limit`,
`script_unit_can_dragon_vein`, `script_unit_has_skill`, `skill_total`, `unit_attack_for_terrain`,
`unit_attack_for_terrain_of_slot`, `unit_equipped_skill_count`, `unit_lethality_immune` (cleaned sessions of earlier
rounds may have met some of the skill ones; this list is from the folders that exist).

Cheap extras tried on the way:
- **Supports toward a child paralogue**: Kaze-Hana and Felicia-Saizo were paired the whole of both chapters (Guard
  Stance, `paired_player` 4 from turn 1). Their C talks are in `bt-ch10`. In the chapter-12 look-ahead (from
  bt-ch11-clear, not a route yet) the Support screen offered **Kaze-Hana B, Felicia-Saizo B** and Corrin-Kaze B, and
  they were viewed. A and S are still to come; then the paralogue of that pair's child (the family readers).
- **A fort or throne fight** for `unit_attack_for_terrain*`: none on these two maps; and round 5 found that those two
  readers are not about forts at all (breakable terrain objects only).
- **A skill check**: nothing aimed; `skill_total`, `unit_equipped_skill_count`, `unit_lethality_immune` stay unmet in
  real play.
- Seen and not taken: a **Paralogue 1** entry on the world map since chapter 9 (not played), a "Buildings NEW" mark in
  the castle, two Master Seals (Takumi, Saizo).

Chapter 12 (done in round 9, section 3f; its start state was build/harness/robot/states/bt/b12t1, frame 7669): 'Dark Reunion', win rule
`ChapterSetWinRuleEscapeHero` (Corrin escapes), 27 enemies, Kaden already in the army (force 0). The map
is boats and bridges (floor, bridge) on "sea / ice hill" tiles; one dragon vein at (17,15) tied to a 27 x 22 area named
"sea" (TrickData type 12); a type-8 trick at (13,1) [med: the escape tile]. On floor and bridges only, Corrin's path to
(13,1) is 84 tiles; across the sea tiles it is 27 [med: the vein turns the sea to ice; Grok's
tracks/ROUTES_BT_10_14.md says the same from a public page, and that a flier could carry Corrin].

Grok's tracks/ROUTES_BT_10_14.md checked against the runs: map sizes 25 x 13, 30 x 22, 25 x 20 match the play areas
read; Takumi does join after chapter 10 although he was attacked (the note says to talk first; not needed); Reina
joins by Corrin's talk (as written); "this save has two C supports" is out of date (see above).

## 3f. Round 9: Birthright chapter 12 on the speed tools [high unless tagged]

Same proof as before (the stitched input replayed from frame 0 of the start save on two ORIGINAL boot.exe copies,
then a marker run and a capture run), but the look-ahead ran on `fastlook.py` (docs/harness/SERVER.md, F-023):
chain `c12` in build/speed/r9-bt/ (`--dir`), started with `new c12 --save bt-ch11-clear` (frame 0, so it can be
verified) and one `abs` step that replayed round 8's b12t1 presses (castle Support talks, Next Battle, Fight!) to
frame 7669. Three scratch helpers in build/speed/r9-bt/tools/ (not tracked, no game data):

- `act2.py CHAIN UX,UY DX,DY wait|attack[:N]|staff[:N]|show` = one unit action as ONE `fastlook phase` (select,
  move, command, then `until` the next free-cursor screen); `act2.py CHAIN end X,Y` ends the turn from an empty tile;
  `raw PRESSES` for menus (trade, switch, the save). Before each call it copies the chain (chain.json, inputs.txt,
  state.bin, last.json) to `hist/`; a stopped phase is undone whole, and `undo N` rolls back N calls (no re-boot).
- `rb.py CHAINDIR [-m] [-t] [-T]` = the board read live with `peek` (unit names from the person / class ids,
  level, HP, pair flags; the terrain grid, tricks, the map's terrain names): no dump, no picture.
- `pp.py` = cheapest path on the read grid with chosen terrain costs.

Things learned on the way (all [high], seen in the chain):
- **The cursor read at the start of a player phase is stale** (`*0x006D7198` keeps the old tile until the cursor
  moves). Two wrong selections came from it; `act2 end` now presses RIGHT LEFT after the phase starts, and the read
  is right after that.
- Pair Up is a command from a tile NEXT TO the ally (A on the ally's own tile does nothing); Switch is free (the
  menu comes back); Trade too (Asama, a Monk with no items, took Corrin's Sun Festal and healed in the same turn).
- On this map the sea/ice tiles (terrain kind 3, "sea / ice hill") cost 2 for Corrin after the vein; the grid's
  kind numbers do not change when the sea freezes.
- Enemy great knights and knights carry javelins: a healer two tiles from the front tile is hit. Sakura was lost
  twice in look-aheads that way (Casual retreat); both were undone (a lost unit is never kept).

| | Chapter 12 'Dark Reunion' (`bt-ch12`) |
|---|---|
| Win rule | Corrin escapes (the "Escape" command on (13,1), then "Leave the battlefield?" Yes) |
| Map | 25 x 20; terrain names read: none, ice hill, bridge, sea / ice hill, low wall, floor, chest; one vein (17,15) tied to the whole map's "sea" area; Garon (level 30) and three knights at (12-14,19-20) never moved; Xander, Laslow, Peri (top left) never moved |
| Start | 12 units, 27 enemies (7669) |
| Turns, end | 39; stage complete at 148831, saved 153349 |
| Lost (Casual retreat) | none |
| Supports | Kaze-Hana B, Felicia-Saizo B, Corrin-Kaze B viewed in the castle (part of the route); Kaze+Hana and Felicia+Saizo paired from turn 1 (`paired_player` 4 at 9101) |
| Vein | used by Corrin at 114947 (`map__trick` mutation, "Freeze the water to make it passable") |

Proof (`parallel.py runs --route bt-ch12 --markers --copies 2 --keep`, session r9bt-12, below normal, FEF_ROBOT_JOBS=2,
FEF_ROBOT_MEM_GB=2.6): both ORIGINAL copies exit 0 after 154,000 frames, 690,094,944,104 instructions, memory
**`c6f70ba7...`** in both, **checkpoints all met** (markers.json `bt-ch12`: 7669 turn 1 with units [12, 27, 0] and no pair;
9101 `paired_player` 4; 114947 `veins_used` 1; 148831 stage complete; 153349 the castle after the save). 736 s and
602 s, peak 364 / 366 MB; the pool ran them one after the other (the first-run memory estimate, 1.5 GB, did not fit
twice in 2.6 GB). Save packed from copy 1 with `parallel.py pack`: `bt-ch12-clear.zip` sha256 `41e75990...`.
`fastlook.py verify c12` did NOT give a verdict: its clean-line server pass stopped at frame 106,429 on the server's
600 s step timeout (a 153k-frame chain is longer than that pass allows); the two original copies above are the proof.

Capture (`parallel.py runs --route bt-ch12 --mode capture --markers --timeout 3600`, session r9bt-12cap, the current
library): exit 0, memory `c6f70ba7...` (equal to the original copies), checkpoints all met, **100 overrides met, 2317
records, 2242 match, 34 gave up, 41 incomplete, 0 bad of any kind** (no mismatch of r0, registers, memory or calls; 0
unfaithful, escaped, damaged); no writer stored anything. 632 s. The 10 overrides that real play had never met (3e)
are still not met here (checked by address against the run's summary.tsv): family_grow, family_parent_grow,
family_limit, script_unit_can_dragon_vein, script_unit_has_skill, skill_total, unit_attack_for_terrain,
unit_attack_for_terrain_of_slot, unit_equipped_skill_count, unit_lethality_immune. (`script_unit_can_dragon_vein`
stays unmet although Corrin used a vein: the vein command does not go through that script call.)

Wall time, chapter 12 (start of the look-ahead to the packed save): **74 min** (1794651966 -> 1794656380 epoch s):
about 50 min look-ahead (including writing the three helpers and about 15 min lost on the stale cursor and the two
undone Sakura losses), 22 min for the two proof copies (serial, see above), 1 min to pack. The look-ahead itself was
~120 fastlook calls of 1-12 s each (one boot per call, no server kept: `act2.py` copies state.bin between calls).

Continue from: `bt-ch12-clear` (slot 1 saved after chapter 12, the castle). Next: chapter 13 'Another Hope' (rout;
Grok's note: do not use the thunder vein on your own side). Supports: Kaze-Hana and Felicia-Saizo are at B with
points still rising (paired all of chapter 12); A needs more paired turns, S then the child paralogue.

## 3g. Round 10: Birthright chapter 13 (`bt-ch13`) [high unless tagged]

Fresh helper, one chapter. Chain `c13` in build/speed/bt13/ (`new c13 --save bt-ch12-clear`, frame 0), the round-9
scratch helpers copied there (act2.py, rb.py; act2 now presses RIGHT LEFT itself when the kept cursor read is stale).

| | Chapter 13 'Another Hope' (`bt-ch13`) |
|---|---|
| Win rule | rout (24 enemies on Normal, as Grok's note says) |
| Map | 21 x 19 town; terrain read: plain, forest, cliff, river (rows 5-6), buildings (impassable), villages; the north (Camilla, Belka, Selena, six knights) is behind cliffs and the river, crossed only by bridges at column 4 and column 18; four lightning-vein tiles (type 11) at (11,2), (11,11), (21,18), (5,16) and four 3 x 3 vein areas (type 12) |
| Start | 13 units, 24 enemies (7613) |
| Turns, end | 23; stage complete (castle Seq) at 123227, saved slot 1, castle at 127865 |
| Lost (Casual retreat) | none kept. Orochi was lost twice and Corrin once in look-aheads (north group woken at the bridge); all three undone |
| Vein | Takumi on (21,18) at 73267: "Call lightning to drop units in area to 1 HP"; the area is (19-21,8-10), only Hans was in it (44 -> 1 HP). Grok's warning checked: it hits whoever is in the area, so it was used only with no unit of ours there |
| Supports | Kaze-Hana and Felicia-Saizo paired from turn 1 (`paired_player` 4 at 9157); points before the battle: Kaze-Hana 9, Felicia-Saizo 11, next level (A) at 14. The Support screen offered Corrin/Saizo/Kaden talks in the castle; not viewed |

Learned [high, seen in the chain]: the north group does not move until a unit comes near the bridge top; Camilla
(Malig Knight, Silver Axe + Ragnarok, range 1-2) then flies over the river. What worked: lure fliers to the south
bank where knights cannot follow (Corrin at (14,8) killed Belka on the counter), then Corrin + Takumi dual strike
on Camilla. Corrin's Dragonstone damage is computed against Res (25 on a Def 13 / Res 2 wyvern), so knights take ~23.
Hans (Berserker, 44 HP, Atk 33) never moved until someone came within reach. Felicia's Iron Dagger does 0 to Def 10.
Switch after a B on the command menu is undone; switch after moving works (then Wait).

Proof (`parallel.py runs --route bt-ch13 --markers --copies 2 --keep`, session r10bt-13, FEF_ROBOT_JOBS=4,
FEF_ROBOT_MEM_GB=2.64): both ORIGINAL copies exit 0 after 128,500 frames, memory **`230805919f8aa338`** in both,
**checkpoints all met** (7613 units [13, 24, 0] no pair; 9157 `paired_player` 4; 73267 `veins_used` 1; 123227
stage complete; 127865 castle after the save); 667 s and 659 s, run side by side, peak 366 MB each. Packed from
copy 1: `bt-ch13-clear.zip` sha256 `984edf67...`.

Capture (`parallel.py runs --route bt-ch13 --mode capture --markers --timeout 3600`, session r10bt-13cap): exit 0,
memory `230805919f8aa338` (equal to the original copies), checkpoints all met, **103 functions met, 2322 records,
2260 match, 32 gave up, 30 incomplete, 0 bad of any kind** (no r0, register, memory or call mismatch; 0 unfaithful,
escaped, damaged); no writer stored anything. 568 s.

Wall time, chapter 13 (start of the look-ahead to the packed save): **53 min** (1794685324 -> 1794688484 epoch s).

Continue from: `bt-ch13-clear` (slot 1 saved after chapter 13, the castle). Next: chapter 14. Kaze-Hana and
Felicia-Saizo still near A (keep them paired); a Support talk mark is up in the castle.

## 3h. Round 10: Birthright chapter 14 (`bt-ch14`) [high unless tagged]

Two fresh helpers, one chapter. The first played the chain `c14` in build/speed/bt14/ (`new c14 --save
bt-ch13-clear`, frame 0, act2.py/rb.py helpers copied from bt13) to the castle and wrote the route key; its proof
was cut off when it returned. The second ran the proof, packed the save and ran the capture.

| | Chapter 14 'Light Scatters' (`bt-ch14`) |
|---|---|
| Win rule | defeat the boss (a Strategist in the fort; the game data gives only the generic id `PID_A014_ボス`, so Grok's name "Daniela" is not seen) |
| Map | 25 x 30; a fort in the north; dragon-vein tiles at (13,14), (15,11), (11,11) set off a landslide |
| Start | 14 units, 16 enemies (6740); 17 more appear inside the fort on turn 3 (as Grok's note says) |
| Turns, end | 14; stage complete (castle Seq) at 110692, saved slot 1, castle at 116820 |
| Lost (Casual retreat) | none; nobody captured |
| Veins | Ryoma (13,14) at 63820, Ryoma (15,11), Corrin (11,11) by 78496: each takes 10 HP from every enemy inside the fort, never below 1 (the boss 33 -> 3); none of our units were hit |
| Supports | Kaze-Hana and Felicia-Saizo paired from turn 1 (`paired_player` 4 at 8174). The in-battle read stayed Kaze-Hana 10, Felicia-Saizo 11 (A at 14) the whole battle [medium: not read after the chapter; the castle look gives no supports] |

Played [high, seen in the chain]: Ryoma, Takumi, Corrin and Kaden killed the field enemies (thieves, knights, two
paladins, cavaliers); Corrin + Ryoma + Kaden + Saizo beat the enemy pair Benoit + Charlotte standing on the vein
tile (13,14); Azura's Sing once; after the three landslides Ryoma killed the boss from (14,2) at range 2.

Proof (`parallel.py runs --route bt-ch14 --markers --copies 2 --keep`, session r10bt-14b, FEF_ROBOT_JOBS=4,
FEF_ROBOT_MEM_GB=2.64): both ORIGINAL copies exit 0 after 117,500 frames, memory **`79d41237d39c24ac`** in both,
**checkpoints all met** (6740 units [14, 16, 0] no pair; 8174 `paired_player` 4; 63820 `veins_used` 1; 78496
`veins_used` 3; 110692 stage complete; 116820 castle after the save); 551 s and 561 s side by side, peak 381 MB each;
%APPDATA% unchanged. Packed from copy 1: `bt-ch14-clear.zip` sha256 `c3834b8f...` (Chapter0 and Global differ from
bt-ch13-clear, so slot 1 was overwritten).

Capture (`parallel.py runs --route bt-ch14 --mode capture --markers --timeout 3600`, session r10bt-14cap): exit 0,
memory `79d41237d39c24ac` (equal to the original copies), checkpoints all met, **102 functions met, 2227 records,
2155 match, 30 gave up, 42 incomplete, 0 bad of any kind** (no r0, register, memory or call mismatch; 0 unfaithful,
escaped, damaged); no writer stored anything. 488 s.

Wall time, chapter 14 (first helper's start, epoch 1794692163, to the packed save, 1794695169): **50 min**
(39 min first helper incl. the cut-off proof, 11 min this helper).

Continue from: `bt-ch14-clear` (slot 1 saved after chapter 14, the castle). Next: chapter 15, Butler > Next Battle.
Kaze-Hana 10 and Felicia-Saizo 11 (A at 14): keep them paired.

## 3i. Round 10: Birthright chapter 15 (`bt-ch15`) [high unless tagged]

Fresh helper, one chapter. Chain `c15` in build/speed/bt15/ (`new c15 --save bt-ch14-clear`, frame 0; act2.py,
rb.py, cfg.py copied from bt14). Two new scratch helpers there (not tracked, no game data): `sk.py` (each unit's
equipped skill numbers and items, read live) and `reach.py` (which enemies can reach a tile, from rb.json, with wolf
costs plain/woods 1, mountain/fort 2, Wolfskin move 5, Wolfssegner 6). `chk.py` replays the exported input from
frame 0 on boot-server and prints the markers at chosen frames (used to pick the checkpoints before the proof).

| | Chapter 15 'Wolfskin Peak' (`bt-ch15`) |
|---|---|
| Win rule | rout (the Preparations screen: "Rout the enemy") |
| Map | 20 x 20 mountains (terrain read: plain, woods, mountain, high mountain, fort, castle gate, buildings; every name carries the vein mark); one vein area over the whole map and three vein tiles (19,2), (4,16), (13,14) |
| Start | 12 units, 15 enemies (7494): the boss (a level-6 Wolfssegner in the gate at (9,3)), 8 Wolfssegner and 6 Wolfskin; 7 more Wolfskin came on turns 6-8 at the west edge and the north-east |
| Turns, end | 32; stage complete at 128480, saved slot 1, castle at 135908 |
| Lost (Casual retreat) | none kept. Sakura (turn-1 test), Orochi and Silas (turn 4) were lost in look-aheads and undone |
| Vein | Corrin on (13,14) at 66522 (turn 15): "Call rains to drop enemy stats (temp.)" |
| Supports | Kaze-Hana and Felicia-Saizo paired from turn 1 (`paired_player` 4 at 12816). Points did not move all chapter: Kaze-Hana 10, Felicia-Saizo 13 (A at 14) at the start and at stage complete. They never fought together; pairing alone does not add points |

Learned [high, seen in the chain]:
- Each Wolfssegner carries one skill (Skill table numbers read live, names from the local table dump): Counter (37),
  Pavise (33), Aegis (34), Countermagic (38), Poison Strike (101), Pass (111), Life or Death (55) and 50; the boss
  Beastbane (40) and 54; the Wolfskin none. **Counter** cost Corrin 24 HP on one melee hit (his 20 came back); from two
  tiles (Orochi, Saizo's shuriken) there is no counter at all, and a killing blow is not reflected.
- Kaden (Kitsune) has Beastbane too: 25 x2 effective against a Wolfskin, so each Wolfskin that attacked him died on
  the counter. Corrin's Dragonstone (magic) hits the low Res for ~20 but Aegis halved it (7 on a fort).
- The northern wolves do not move until a unit is inside their reach; the boss does leave its gate (Asama at (12,7)
  drew it to (12,6), 27 HP, then Orochi from (12,8) and Corrin from (12,7) killed it).
- Mountains cost 4 for Corrin and Kaden (move 5): the centre band (rows 11-13) took two turns to cross. Asama's staff
  and Sakura's rod ran out of uses during the chapter.
- The boss came out with 27 of 38 HP after attacking Asama, who carries no weapon (in a look-ahead that was undone it was 29) [not traced].

Proof (`parallel.py runs --route bt-ch15 --markers --copies 2 --keep`, session r10bt-15, FEF_ROBOT_JOBS=4,
FEF_ROBOT_MEM_GB=2.64): both ORIGINAL copies exit 0 after 136,600 frames, memory **`31afa8bc8fe5fddf`** in both,
**checkpoints all met** (7494 units [12, 15, 0] no pair; 12816 `paired_player` 4; 66522 `veins_used` 1; 128480
stage complete, units [12, 0, 0]; 135908 castle after the save); 555 s and 551 s side by side, peak 372 / 368 MB;
%APPDATA% unchanged. Before the proof, `chk.py` replayed the exported input from frame 0 on boot-server and read the
same values at those frames. Packed from copy 1: `bt-ch15-clear.zip` sha256 `06c0f510...`.

Capture (`parallel.py runs --route bt-ch15 --mode capture --markers --timeout 3600`, session r10bt-15cap): exit 0,
memory `31afa8bc8fe5fddf` (equal to the original copies), checkpoints all met, **99 functions met, 2240 records,
2156 match, 31 gave up, 53 incomplete, 0 bad of any kind** (no r0, register, memory or call mismatch; 0 unfaithful,
escaped, damaged); no writer stored anything. 413 s.

Wall time, chapter 15 (start, epoch 1794695839, to the packed save, 1794700258): **74 min** (about 57 min look-ahead,
including ~15 min lost on the turn-1 selection left open by the banner A press, two lost units undone and mountain
paths that did not reach; 10 min proof; the rest checkpoints and notes).

Continue from: `bt-ch15-clear` (slot 1 saved after chapter 15, the castle). Next: chapter 16. The bt-ch14 opening presses (up to frame 5860) worked unchanged from this kind of castle save
[med: the castle menu steps were not looked at one by one; check with a look]. Kaze-Hana 10 and Felicia-Saizo 13 (A at 14): they need fights while paired, not
just turns. The look at turn start (frame 7494) showed a unit already selected: the A that closed the "Rout the
enemy" banner had picked up Corrin; one B cleared it.

## 3j. Round 10: Birthright chapter 16 (`bt-ch16`) [high unless tagged]

Fresh helper, one chapter. Chain `c16` in build/speed/bt16/ (`new c16 --save bt-ch15-clear`, frame 0; act2.py, rb.py,
sk.py, chk.py, cfg.py copied from bt15). New scratch helpers there (not tracked, no game data): `mp.py` (wall map from
rb.json: `#` wall, `.` floor, `s` stairs, `o` pillar, `D` door, `$` chest, `C` turret), `go.py` (best reachable end
tile toward a goal for a given move), `thr.py` (which of our units / which tiles an enemy can hit with a given move
and range), `bd.sh` (one-line live board from state.bin).

| | Chapter 16 'Pleasure Palace' (`bt-ch16`) |
|---|---|
| Win rule | rout ("Rout the enemy") |
| Map | 20 x 25 palace: walls (terrain 1), floor (2), stairs, pillars, three doors (6,16), (10,16), (17,19), four chests, two magic turrets (20,2), (20,8). We start in a 2-wide corridor (x 1-2); the only ways out are the gap (3,14)-(3,15) (two Armor Knights in it) and the room to the south (two more Knights) |
| Start | 13 units, 20 enemies (9162): Sorcerer boss (20,4), 6 Armor Knights, 4 Dark Mages (one of them the key carrier at (20,7)), 1 Sorcerer, 2 Heroes (brave swords), 3 Fighters, 1 Strategist, 2 Thieves. Later: 3 Thieves and 1 Dark Mage at the north and the stairs |
| Turns, end | 14; stage complete at 124904, saved slot 1 (130018-130272), castle at 130712 |
| Lost (Casual retreat) | none kept. Rinkah was lost in a look-ahead on turn 7 (the Strategist rode 8 tiles to (7,5) and killed her at (6,6)) and undone |
| Supports | Felicia paired onto Saizo on turn 1 (`paired_player` 2 at 13020); Saizo fought paired 3 times (knight, two thieves). Felicia-Saizo still read 13 (A at 14) on the map after those fights; the value after the chapter was not read. Kaze was not in the 13 deployed, so Kaze-Hana did not move |

Learned [high, seen in the chain]:
- **Castle menu changed**: from this castle save the old opening (START, 4 DOWN, A, A) landed on Preparations >
  Support (support talks waiting) instead of the chapter. B, B back to the castle walk, then START (Butler menu:
  Buildings, Castle Settings, Unit Logbook, Save, Next Battle), 4 DOWN, A (map: Chapter 16 first), A, LEFT A (Yes).
- **Ryoma (Swordmaster lv 5, Raijinto 1-2) carried the chapter**: one round killed a full Armor Knight (31), each Hero
  (39, from two tiles so the brave sword could not answer), three Dark Mages, the Strategist, a Knight and the boss
  (40) with no damage taken in most fights. Raijinto from two tiles is the safe way at Knights and Heroes.
- Armor Knights hit Kaden for 24 per round (13 per hit); Corrin's Dragonstone took a Knight from 31 to 1. Orochi's
  scroll from two tiles took 16 with no counter.
- Each enemy phase from turn 10 on, two of our units 6-9 tiles from the boss's corner lost 6-9 HP each with no enemy
  next to them (Scarlet at (15,8), Rinkah (15,5), Sakura (15,6)). Most likely the boss's long-range tome or the
  turrets [med: not looked at in a battle picture]. It stopped once the weak units were 10+ tiles away.
- Enemy drops filled Ryoma's 5 slots four times; each time `ItemMenuSend` came up and the new 6th item went to the
  convoy (Tiger Spirit, Door Key and two later drops). Corrin sent a thief's Silence staff.
- Hana's Bloom Festal (20 uses) traded to Sakura gave a heal of about 9 each turn; Asama had nothing to use all chapter.
- One Thief left the map from the bottom-right chest room on turn 12; the rout still completed.
- Fates ends the player phase by itself when the last unit acts (seen on turns 9 and 11).

Tool finding [high]: `fastlook serve` plus act2's file undo went wrong. A step that stopped and rolled back inside
`serve` kept the cursor moves of its first (passed) step in the server but did not write them to inputs.txt, and
act2's `undo` restores the files but not the server. The clean replay then diverged (Rinkah paired onto Hana instead
of Felicia onto Saizo; at 14828 the Units list was open). I truncated inputs.txt to 12444, rebuilt with `clean` and
played the rest without `serve` (one boot per call from state.bin, about 2-3 s each).

Proof (`parallel.py runs --route bt-ch16 --markers --copies 2 --keep`, session r10bt-16, FEF_ROBOT_JOBS=4,
FEF_ROBOT_MEM_GB=2.64): both ORIGINAL copies exit 0 after 131,400 frames, memory **`47f022d038f51de2`** in both,
**checkpoints all met** (9162 units [13, 20, 0] no pair; 13020 units [13, 19, 0] `paired_player` 2; 124904 stage
complete, units [13, 0, 0]; 130712 castle after the save); 429 s and 431 s side by side, peak 370 MB; %APPDATA%
unchanged. Before the proof, `chk.py` replayed the exported input from frame 0 on boot-server and read the same
values at those frames (and 14262 [13, 18, 0], 22968 [13, 17, 0]). Packed from copy 1: `bt-ch16-clear.zip` sha256
`290affa7...`.

Capture (`parallel.py runs --route bt-ch16 --mode capture --markers --timeout 3600`, session r10bt-16cap): exit 0,
memory `47f022d038f51de2` (equal to the original copies), checkpoints all met, **104 functions met, 2272 records,
2202 match, 33 gave up, 37 incomplete, 0 bad of any kind** (no r0, register, memory or call mismatch; 0 unfaithful,
escaped, damaged); no writer stored anything. 359 s.

Wall time, chapter 16 (start 19:11:45, to the packed save 20:09:04, epoch 1794704944): **57 min** (about 35 min
look-ahead including ~6 min on the serve divergence and ~3 min on the undone Rinkah loss; ~7 min the from-frame-0
check; 7 min proof; the rest marks and notes).

Continue from: `bt-ch16-clear` (slot 1 saved after chapter 16, the castle). Next: chapter 17. From this castle
save do not reuse the old castle presses blindly: check whether Preparations > Support opens first (support talks
waiting); the Butler menu has Next Battle 5th (4 DOWN). Sakura carries the Bloom Festal now; Ryoma's Sun Festal is
unused (Asama could take it). Felicia stays paired on Saizo.

## 3k. Round 10: Birthright chapter 17 (`bt-ch17`) [high unless tagged]

Fresh helper, one chapter. Chain `c17` in build/speed/bt17/ (`new c17 --save bt-ch16-clear`, frame 0; act2.py, rb.py,
sk.py, chk.py, cfg.py, go.py, thr.py, mp.py copied from bt16; go/thr/mp changed to this map's terrain ids). New scratch
helper `mv.sh` (try several end tiles for one unit, keep the first one the game accepts). No `serve` used.

| | Chapter 17 'Lost in the Ice' (`bt-ch17`) |
|---|---|
| Win rule | rout ("Rout the enemy") |
| Map | 25 x 17 snow village. Terrain: plain, woods, buildings and walls (no walk), five villages, and a big lake (x 8-18, y 4-18, terrain 4 "lake only") that nobody on foot can enter. Dragon vein at (17,14) (TrickData type 11; type 12 over the lake): "Freeze the lake and make it passable" |
| Start | 13 units at the bottom right, only **1 enemy** in the unit table (8516): the boss, a Maid lv 9 at (3,5). In the enemy phase of turn 4 nine more came (2 Mercenaries lv 17, 2 Sorcerers, 2 Fighters lv 17, 2 Maids, 1 Thief) |
| Turns, end | 14; stage complete at 96250 (heroes Felicia & Saizo), saved slot 1 (99892-100458), castle at 100998 |
| Lost (Casual retreat) | none kept. In a look-ahead on turn 4, Silas (10,17) and Rinkah (14,16) walked onto the new ice and both were lost when the turn-4 enemies came in; undone |
| Supports | Felicia paired onto Saizo on turn 1 (`paired_player` 2 at 9680). Saizo countered a Sorcerer once while paired (turn 5). Felicia-Saizo still read 13 (A at 14) at stage complete. Kaze is not in the army list at all (Select Units shows 21 names, no Kaze), so Kaze-Hana cannot move |

Learned [high, seen in the chain]:
- **Castle opening from bt-ch16-clear**: the load lands on Preparations (4400, support talks waiting). B (castle), START
  (Butler: Buildings, Castle Settings, Unit Logbook, Save, Next Battle), 4 DOWN, A, A (Chapter 17), LEFT A (Yes),
  START x4 skips the events and the 4th START is Fight! in Preparations; LEFT A, then A on the "Victory: Rout the enemy"
  banner (it waits for a key).
- **Snow slows everyone**: on foot about 2-4 tiles a turn on the plain here; the lake cannot be entered until the vein.
  Ryoma (royal) can use the vein; it froze the whole lake at once and stayed frozen.
- The western enemies stayed put until a unit came within reach. Ryoma alone as bait at (8,8) on turn 10 took both a
  Mercenary and a Sorcerer on counters (37 -> 15 HP). He used his Elixir (got from the Maid on turn 11; Silver Shuriken
  sent to the convoy) and killed the boss from two tiles with no damage on turn 13.
- Kaden killed the last Mercenary on turn 14 but took 15 (24 -> 9).

Proof (`parallel.py runs --route bt-ch17 --markers --copies 2 --keep`, session r10bt-17, FEF_ROBOT_JOBS=4,
FEF_ROBOT_MEM_GB=2.64): both ORIGINAL copies exit 0 after 101,700 frames, memory **`e44b77b516d2e982`** in both,
**checkpoints all met** (8516 units [13, 1, 0] no pair; 9680 [13, 1, 0] `paired_player` 2; 96250 stage complete
[13, 0, 0]; 100998 castle after the save); 377 s and 378 s side by side, peak 366 MB; %APPDATA% unchanged. Packed from
copy 1: `bt-ch17-clear.zip` sha256 `ce36752d...`. routes.json bt-ch17 `verified` set true after this run.

Capture (`parallel.py runs --route bt-ch17 --mode capture --markers --timeout 3600`, session r10bt-17cap): exit 0,
memory `e44b77b516d2e982` (equal to the original copies), checkpoints all met, **98 functions met, 2102 records,
1993 match, 31 gave up, 78 incomplete, 0 bad of any kind** (no r0, register, memory or call mismatch; 0 unfaithful,
escaped, damaged); no writer stored anything. 303 s.

Wall time, chapter 17 (start 20:29:08, epoch 1794706148, to the packed save, epoch 1794708280): **36 min** (about 27 min
look-ahead including the undone turn-4 losses; 6 min proof; the rest config and pack). No from-frame-0 `chk.py` pass
was run first; the two-copy proof was the first clean replay and it matched.

Continue from: `bt-ch17-clear` (slot 1 saved after chapter 17, the castle). Next: chapter 18. Check the castle
opening step by step again (Preparations may open first; Next Battle is 5th in the Butler menu). Felicia stays paired
on Saizo (13, A at 14); he needs to fight while paired. Kaden ended at 9 HP (heals between chapters).

## 3l. Round 11: Birthright chapter 18 (`bt-ch18`) [high unless tagged]

Fresh helper, one chapter. Chain `c18` in build/speed/bt18/ (`new c18 --save bt-ch17-clear`, frame 0; act2.py, rb.py,
sk.py, chk.py, cfg.py, go.py, thr.py, mp.py, mv.sh, bd.sh copied from bt17). act2's end-turn wait is now `EMAX`
(default 30000 frames): with battle scenes on, one enemy phase here took about 10,000 frames and the old 9000 cap
stopped it. No `serve` used (so the round-10 rollback bug could not apply); `chk.py` replayed the export from frame 0
before the proof and read the same checkpoint values.

| | Chapter 18 'Leo' (`bt-ch18`) |
|---|---|
| Win rule | defeat the boss ("Defeat the boss") |
| Map | 20 x 20 dark forest. Terrain: plain, "plain / poison swamp", "poison swamp" (units standing there lost 3 HP a turn), woods, deep forest (the walls), graves. Dragon veins at (5,7), (10,5), (15,6) (TrickData type 11) |
| Start | 14 units in a pocket at the bottom (rows 18-20), 18 enemies (7674): Leo (Dark Knight lv 12, 34 HP, Brynhildr, Energy Drop) at (10,6), Odin (Sorcerer) (7,4), Niles (Adventurer) (13,4), 15 Faceless lv 18 (30 HP, Atk 17, Def 13, Res 12, Spd 13, move 5, range 1), three of them right next to the pocket |
| Turns, end | 6; stage complete at 79582 (heroes Felicia & Saizo), saved slot 1 (85314-86020), castle at 86630 |
| Lost (Casual retreat) | none, also none in the look-ahead |
| Supports | Felicia paired onto Saizo on turn 1 (`paired_player` 2 at 14146); Saizo killed two Faceless while paired (turns 2 and 4). Felicia-Saizo read 13 (B, next 14) at the start; the value after the chapter was not read (the castle look prints no supports). Ryoma paired onto Scarlet on turn 5 (`paired_player` 4 at 64126). Kaze is not in the army |

Learned [high, seen in the chain]:
- **Castle opening from bt-ch17-clear**: same as chapter 17: the load lands on Preparations (4400), B, START, 4 DOWN,
  A, A (Chapter 18 first), LEFT A, START x4 (the 4th is Fight!), LEFT A, then A on the win banner.
- **Faceless keep coming**: the 6 corner Faceless came back at their start tiles after turn 2 and again after turn 4;
  Leo moves onto a dragon vein in the enemy phase ((5,7) on turn 3, (10,5) on turn 4; `veins_used` 2) and 3 more
  Faceless appeared around the vein he used. The map does not run out; kill Leo early.
- Faceless do no damage to Scarlet (Def 22-23) and Ryoma takes 1; both kill one in a round (Ryoma 27 x2, Scarlet
  doubles). Corrin left one at 7, Saizo's shuriken does 10 x2. Silas (Def about 8) took 9 a hit and fell to 6 HP with
  two next to him: keep him inside.
- **Pocket hold**: units on (8,18), (9,17), (10,16) or (10,17), (11,17), (12,17), (13,18) close the start pocket;
  the 10 tiles behind them are out of reach. Most Faceless died on counters in the enemy phases.
- **The win**: turn 5 Ryoma (move 6) paired onto Scarlet from (10,16); Scarlet flew to (10,10) (menu: Attack, Lunge,
  Items, Trade, Switch, Separate, Wait), Switch (4 DOWN A; the menu comes back with Ryoma as lead) and Ryoma killed a
  Faceless. Nothing hurt him in the enemy phase and Leo stayed on (10,5). Turn 6 the pair moved to (10,7); the attack
  target list starts on the Faceless at (10,8), one RIGHT gives Leo: Raijinto 26 x2 at 91% against 34 HP, Leo's
  counter 12 at 5%. Leo died in one round.
- Pair Up target choice cycles with UP through every adjacent ally (Azura, Scarlet, Orochi, Saizo from (12,18));
  look at the panel before A.
- act2 `attack` with Ryoma (several weapons) went into the battle on the second A; on a tile with more than one
  target, use `show`, one A, a forecast picture, then RIGHT to choose.

Proof (`parallel.py runs --route bt-ch18 --markers --copies 2 --keep --timeout 3600`, session r11bt-18b,
FEF_ROBOT_JOBS=4, FEF_ROBOT_MEM_GB=2.64): both ORIGINAL copies exit 0 after 87,300 frames, memory
**`e8e88cf23c0bcd40`** in both, **checkpoints all met** (7674 units [14, 18, 0] no pair; 14146 [14, 15, 0]
`paired_player` 2; 64126 [14, 15, 0] `paired_player` 4, `veins_used` 2; 79582 stage complete [14, 10, 0]; 86630 castle
after the save); 527 s and 528 s side by side, peak 364 MB; %APPDATA% unchanged. A first try (session r11bt-18,
deleted) used the default 900 s timeout and both copies were stopped at 900 s before frame 64126 with the machine
shared: not a mismatch, only the timeout. Packed from copy 1: `bt-ch18-clear.zip` sha256 `57a5fe00...`. routes.json
bt-ch18 `verified` set true after this run.

Capture (`parallel.py runs --route bt-ch18 --mode capture --markers --timeout 3600`, session r11bt-18cap): exit 0,
memory `e8e88cf23c0bcd40` (equal to the original copies), checkpoints all met, **146 functions met, 3305 records,
3206 match, 42 gave up, 57 incomplete, 0 bad of any kind** (no r0, register, memory or call mismatch; 0 unfaithful,
escaped, damaged); no writer stored anything. 400 s.

Wall time, chapter 18 (start 13:09:42, epoch 1794766182, to the packed save, epoch 1794770189): **66 min** (about
32 min look-ahead, 6 turns; ~6 min the from-frame-0 check; 15 min lost on the proof that hit the 900 s timeout; 9 min
the proof; the rest config and pack).

Continue from: `bt-ch18-clear` (slot 1 saved after chapter 18, the castle). Next: chapter 19. Check the castle opening
step by step again. Felicia stays paired on Saizo (13, A at 14). Ryoma and Scarlet are the strongest pair; Saizo
carries a Master Seal (not used).

## 3m. Round 11: Birthright chapter 19 (`bt-ch19`) [high unless tagged]

Fresh helper, one chapter. Chain `c19` in build/speed/bt19/ (`new c19 --save bt-ch18-clear`, frame 0; act2.py, rb.py,
sk.py, chk.py, cfg.py, go.py, thr.py, mp.py, mv.sh, bd.sh copied from bt18, names changed to bt19/c19). No `serve`
used (so the round-10 rollback bug could not apply); every undo was act2's own file undo on a one-shot chain, and
`chk.py` replayed the export from frame 0 before the proof.

| | Chapter 19 'Rainbow Sage' (`bt-ch19`) |
|---|---|
| Win rule | rout ("Rout the enemy") |
| Map | 30 x 30, seven floating floors with "impassable" between them (terrain read: none, impassable, floor, stairs, gate, chest). Two chests (TrickData type 10) at (2,9) and (28,10), not opened. 14 stairs tiles (TrickData type 28) |
| Stairs | Moving onto a stairs tile gives a **Stairs** command (first in the menu); it puts the unit on the paired tile and the unit **keeps the rest of its move** (it can move again, attack, or Wait). Pairs seen: (15,29)->(25,28), (6,29)->(3,25), (19,23)->(28,19), (9,20)->(2,16), (7,10)->(11,18), (23,10)->(19,18), (15,13)->(15,9) (top floor). A unit that arrives with 0 move left must be selected again and Wait (menu Stairs, Items, [Trade, Transfer, Switch,] Wait), and it blocks the arrival tile for the rest of the turn |
| Start | 14 units at the bottom (rows 29-30), 22 enemies (7978): boss a General lv 13 (48 HP, lance + javelin) at (15,2) with a Spear Master and a Swordmaster; a General and a Basara on the start floor (on both stairs); pairs Merchant+Onmyoji (19,23) and Maid+Mechanist (9,20); Snipers, Adventurers, Tacticians (Master of Arms type, very hard to hit), a Hero, a Master Ninja, two Yamabushi, a Berserker |
| Enemy moves | Nobody came to us. An enemy moved only once one of ours was in its reach; enemies never used the stairs. The top three never moved until the Swordmaster stepped out on turn 11 |
| Turns, end | stage complete at 152738 (heroes Felicia & Saizo; the screen says 14 turns, by my count it was turn 13), saved slot 1 (157320-157864), castle at 158786 |
| Lost (Casual retreat) | none kept. In the look-ahead: Scarlet (flier) on the west floor was killed by the Maid+Mechanist pair (the Mechanist bow led); Silas next to the Onmyoji died in its enemy phase; Saizo (13 HP) died to the Merchant's counter. All undone and played another way |
| Supports | Felicia paired onto Saizo on turn 1 (`paired_player` 2 at 13730); Saizo fought four times while paired. Felicia-Saizo read 13 (B, next 14) at stage complete (152778 look): it did not move in chapters 17-19 although he fought paired each time [med: why not known] |

Learned [high, seen in the chain]:
- **Castle opening from bt-ch18-clear**: the load lands on Preparations (4666), B, START, 4 DOWN, A, A (Chapter 19
  first), LEFT A, START x3 (the 3rd is Fight! here, not the 4th), LEFT A, then A on the win banner.
- **Ryoma's Raijinto at range 2 is magic and takes no counter from melee enemies**: he one-rounded the start
  General (42 HP), a Yamabushi, the Spear Master (46 HP), took the Swordmaster to 7 and the boss from 48 to 9, never
  hurt. On enemy phases alone on the west chain he killed a Maid, a Sniper, the Master Ninja and a Yamabushi on counters.
- Fliers (Scarlet, Reina) must stay out of bow reach (Snipers, Merchant, Mechanist, Adventurers). Scarlet (Def 23)
  is a good bait for melee: she took the Hero on a counter.
- Azura's Sing (first in her menu, A A) refreshed Saizo for a second attack; she levelled up (a talk screen, so the
  wait step needs `"answer": true`).
- Item drops when the inventory is full open ItemMenuSend; DOWN x5 A, LEFT A sends the new item to the convoy. On an
  enemy phase it stops act2's `end`; pe.json sends it and waits on.
- On the stage-complete banner the game waits for A (one A, then the talk runs with `answer` to ChapterFileMenu);
  slot 1 A, LEFT A, castle about 900 frames later.

Look-ahead check: `chk.py` replayed the export (3107 presses) from frame 0 on boot-server and read the same values
at all seven checkpoints (7978 [14, 22, 0]; 13730 [14, 20, 0] `paired_player` 2; 34070 [14, 17, 0]; 82292 [14, 8, 0];
109958 [14, 4, 0]; 152738 stage complete [14, 0, 0]; 158786 castle). 8 min.

Proof (`parallel.py runs --route bt-ch19 --markers --copies 2 --keep --timeout 3600`, session r11bt-19,
FEF_ROBOT_JOBS=4, FEF_ROBOT_MEM_GB=2.64): both ORIGINAL copies exit 0 after 159,460 frames, memory
**`316756a1aca11662`** in both, **checkpoints all met**; 578 s and 585 s side by side, peak 438 MB; %APPDATA%
unchanged. Packed from copy 1: `bt-ch19-clear.zip` sha256 `7863278c...`. routes.json bt-ch19 `verified` set true
after this run.

Capture (`parallel.py runs --route bt-ch19 --mode capture --markers --timeout 5400`, session r11bt-19cap): exit 0,
memory `316756a1aca11662` (equal to the original copies), checkpoints all met, **148 functions met, 3436 records,
3357 match, 43 gave up, 36 incomplete, 0 bad of any kind** (no r0, register, memory or call mismatch; 0 unfaithful,
escaped, damaged); no writer stored anything. 520 s.

Wall time, chapter 19 (start 14:44:07, epoch 1794771847, to the packed save, epoch 1794777116): **88 min** (about
63 min look-ahead, 13 turns on a big map, three undone losses; 8 min the from-frame-0 check; 10 min the proof; the
rest config and pack).

Continue from: `bt-ch19-clear` (slot 1 saved after chapter 19, the castle). Next: chapter 20. Check the castle
opening step by step again (here the 3rd START was Fight!, in 17 and 18 the 4th). Felicia stays paired on Saizo
(13, B, next 14; not moving). Ryoma with Raijinto at range 2 is the army; Reina ended at 19 HP, Scarlet 18, Corrin 31
(heal between chapters). Saizo still carries a Master Seal (not used).

## 3n. Round 11: Birthright chapter 20 (`bt-ch20`) [high unless tagged]

Two fresh helpers. The first played chain `c20` in build/speed/bt20/ (`new c20 --save bt-ch19-clear`, tools copied
from bt19; act2 file undo only, no `serve`) to the castle (83312 frames, 630 presses) but had to return before any
check. The second ran the from-frame-0 check, the proof, the pack and the capture.

| | Chapter 20 'Fort Dragonfall' (`bt-ch20`) |
|---|---|
| Win rule | defeat the boss |
| Map | a walled maze with acid-bog floors (about 3 HP a turn); ten dragon veins, each "Neutralize acid-bog spaces" in its area (using one ends the unit's action) |
| Start | 14 units, 19 Faceless (10314); more Faceless appear every turn in the east. Boss: Faceless lv 25, 48 HP, Def 15, Res 15, Gauntlet; Ryoma hits it 59% |
| Play | turn 1 Ryoma and Kaden kill the two start Faceless, Corrin uses the vein at (7,8), Felicia pairs onto Saizo; turns 2-4 Corrin holds the north door (8,6), Saizo+Felicia the south door (8,11); turns 5-8 Ryoma and Scarlet go round the maze (15,11) -> (18,10) -> (17,7) -> (13,7); Ryoma takes the boss to 10 HP from range 2 and it dies to his counter at (12,7) in the turn-8 enemy phase |
| End | the 79564 checkpoint reads `castle__anonymous_namespace__Seq` (the chapter-end sequence) with [14, 16, 0]; saved slot 1, castle at 82622 |
| Lost | none, in the route or in the look-ahead |
| Drops | Master Seal x2 and Spy's Shuriken, sent to the convoy |
| Supports | **Why Felicia-Saizo was stuck at 13 in ch17-19**: the B->A talk was waiting to be viewed. Viewed in Preparations > Support > Felicia > Saizo (START skips it); now 14 (A, next 20) |

Learned [high, seen in the chain]:
- **Castle opening from bt-ch19-clear**: the load lands on Preparations, B, START, 4 DOWN, A, A (Chapter 20 first),
  LEFT A; one START skips the events and the **2nd** START is Fight! (3rd in ch19, 4th in ch17/18: check every time).
- A support value that stops moving usually means a support talk is waiting; view it in Preparations > Support.

Look-ahead check: `chk.py` replayed the export from frame 0 and read 10314 [14, 19, 0] paired 0 veins 0; 15776
[14, 17, 0] paired 2 veins 1; 37746 [14, 21, 0]; 62714 [14, 19, 0]; 79564 [14, 16, 0] chapter end; 82622 castle.
[med] The first helper called 79564 "stage complete"; the replay reads the chapter-end sequence there, not
`map__SequenceCompleteEffect`, so the checkpoint uses what was read.

Proof (`parallel.py runs --route bt-ch20 --markers --copies 2 --keep --timeout 3600`, session r11bt-20,
FEF_ROBOT_JOBS=4, FEF_ROBOT_MEM_GB=2.64): both ORIGINAL copies exit 0 after 83,312 frames, memory
**`9db6921f56b77be0`** in both, **checkpoints all met**; 441 s and 442 s side by side, peak 381 MB; %APPDATA%
unchanged. Packed from copy 1: `bt-ch20-clear.zip` sha256 `607c7102...`. routes.json bt-ch20 `verified` set true.

Capture (`parallel.py runs --route bt-ch20 --mode capture --markers --timeout 3600`, session r11bt-20cap): exit 0,
memory `9db6921f56b77be0` (equal to the original copies), checkpoints all met, **147 functions met, 3378 records,
3290 match, 40 gave up, 48 incomplete, 0 bad of any kind**; no writer stored anything. 380 s.

Wall time: first helper about 50 min (look-ahead); second helper 16 min (17:23 to the packed save at 17:39:32).

Continue from: `bt-ch20-clear` (slot 1 saved after chapter 20, the castle). Next: chapter 21 via Butler > Next
Battle; check the castle opening one step at a time. Felicia-Saizo is A (14, next 20): watch for an A->S talk.

## 3o. Round 11: Birthright chapter 21 (`bt-ch21`) [high unless tagged]

Fresh helper, one chapter. Chain `c21` in build/speed/bt21/ (`new c21 --save bt-ch20-clear`, frame 0; tools copied
from bt20, names changed). No `serve`; every undo was act2's own file undo on a one-shot chain, and `chk.py`
replayed the export from frame 0 before the proof. act2.py got three new actions: `pair` (move onto an ally, A on
the pair preview), `swatk[:N]` (after the move: Switch, then attack target N) and `swwait` (Switch, then Wait).

| | Chapter 21 'Burning Falls' (`bt-ch21`) |
|---|---|
| Win rule | defeat the boss |
| Map | 20 x 30, four rock floors one above the other (rows 27-30, 20-23, 9-16, 1-5) with lava cliffs between them. Terrain read: plain, plain/lava floor, lava floor, cliff, cliff/bridge, bridge, hole, wall. Vein tiles (TrickData type 11) at (11,28), (12,28), (14,20), (15,20), (5,11), (6,11); the cliff/bridge tiles (8-9,24-27), (5-6,17-19), (16-17,6-8) are cliffs until something (not tried) turns them into bridges. No vein was used |
| Start | 14 units bottom left, 27 enemies (8190): boss a Stoneborn (ゴーレム) lv 26, 45 HP, at (6,3); seven more Stoneborn lv 21; four Spear Masters on the top floor; three Masters of Arms (兵法者), a Master Ninja on the bottom floor; four Heroes, a Swordmaster on the 2nd; two Snipers, two Adventurers, a Mechanist, an Onmyoji on the 3rd |
| Stoneborn Rock | the Stoneborn throw "Rock" from far away (it hit Orochi in the back corner; Atk 21 on her, 83%). Against Def 20+ it does about 5-7. Any unpaired unit with low Def (Orochi, Azura, Sakura, Silas, Rinkah) can die to Rock plus one more hit in an enemy phase |
| Enemy moves | the bottom floor (Masters of Arms, Master Ninja, a Stoneborn) came to us from turn 1; the upper floors moved only when one of ours was in reach |
| Play | turn 1 Ryoma pairs onto Scarlet (Wyvern Lord, mov 8, flies over the cliffs) and the pair goes to (1,22); turn 3 it lands at (2,15), **Switch** (Ryoma leads; the command menu stays open) and Ryoma kills the Stoneborn there from range 2; enemy phase: he kills the Sniper, an Adventurer and the Onmyoji on counters (the west of the 3rd floor is empty). Turn 4 Ryoma walks to (4,11) and Switches (Scarlet leads). Turn 5 Scarlet flies to (4,3), Switch, Ryoma kills the boss (target 1; target 0 was the Stoneborn at (5,2)). The rest held the bottom-left corner: Kaden, Corrin, Saizo and Yugiri killed three Masters of Arms and the Master Ninja; every weak unit was paired |
| Turns, end | boss dead at 48224 (drop sent to the convoy), stage complete (screen says 5 turns), saved slot 1, castle at 53358 |
| Lost (Casual retreat) | none kept. In the look-ahead: Saizo (19 HP) to a Master of Arms; Silas to a Master of Arms counter; Scarlet to the 3rd-floor bows when the pair flew over at (1,11); Azura, Orochi, Silas, Rinkah on different tries to Rock plus the Master Ninja. All undone and played another way |
| Supports | Felicia-Saizo read 17 (A, next 20) in Preparations and still 17 at the boss kill (Saizo fought paired twice) |

Learned [high, seen in the chain]:
- **Castle opening from bt-ch20-clear**: the load lands on Preparations (4666), B, START, 4 DOWN, A, A (Chapter 21
  first), LEFT A; one START skips the events to Preparations (6758), the **2nd** START is Fight! (6990), LEFT A,
  then A on the win banner (same as ch20).
- **Switch after moving does not end the action**: the menu comes back with the new lead, who can attack. So a flier
  can carry Ryoma over cliffs and he attacks on the same turn. A Switch before moving, then B, is taken back (the
  old lead moves). Switch is the 3rd menu item when the lead has no target (Items, Trade, Switch, Separate, Wait).
- Fliers can stop on cliff tiles; no melee unit can reach a cliff tile whose four neighbours are cliffs.
- Raijinto at range 2 one-rounds Stoneborn (lv 21, 37 HP, and the lv 26 boss, 45 HP) with no counter.
- [med] Moving Azura onto an Asama who had already moved gave Sing, not Pair Up (the cursor path); pair Azura onto an unmoved unit.
- On the stage-complete banner the game waits for A; the screen read there is `castle__anonymous_namespace__Seq`
  with `map__SequenceCompleteEffect...` among the classes (so a wait on the screen name never stops).

Look-ahead check: `chk.py` replayed the export (634 presses) from frame 0 on boot-server and read the same values
at every checkpoint: 8190 [14, 27, 0] paired 0; 13178 [14, 27, 0] paired 4; 25000 [14, 25, 0]; 38844 [14, 20, 0]
paired 12; 45298 [14, 19, 0] paired 14; 48224 boss dead (ItemMenuSend); 50050 chapter end [14, 18, 0]; 53358 castle.
(`paired_player` counts units, so one pair is 2.)

Proof (`parallel.py runs --route bt-ch21 --markers --copies 2 --keep --timeout 3600`, session r11bt-21,
FEF_ROBOT_JOBS=4, FEF_ROBOT_MEM_GB=2.64): both ORIGINAL copies exit 0 after 54,048 frames, memory
**`4d5972e43c8b1218`** in both, **checkpoints all met**; 177 s and 179 s side by side, peak 438 MB; %APPDATA%
unchanged. Packed from copy 1: `bt-ch21-clear.zip` sha256 `34940eed...`. routes.json bt-ch21 `verified` set true.

Capture (`parallel.py runs --route bt-ch21 --mode capture --markers --timeout 3600`, session r11bt-21cap): exit 0,
memory `4d5972e43c8b1218` (equal to the original copies), checkpoints all met, **147 functions met, 3218 records,
3159 match, 42 gave up, 17 incomplete, 0 bad of any kind** (no r0, register, memory or call mismatch; 0 unfaithful,
escaped, damaged); no writer stored anything. 175 s.

Wall time, chapter 21 (start 17:46:41 to the packed save at 18:36:02): **49 min** (about 35 min look-ahead with
six tries undone for losses, 4 min the from-frame-0 check, 3 min the proof, the rest config and pack).

Continue from: `bt-ch21-clear` (slot 1 saved after chapter 21, the castle). Next: chapter 22 via Butler > Next
Battle; check the castle opening one step at a time. Felicia-Saizo is A (17, next 20). Asama ended at 2 HP and
Scarlet at 25 (heal between chapters). Ryoma carried by a flier with Switch-then-attack is the fast pattern.

## 3p. Round 11: Birthright chapter 22 (`bt-ch22`) [high unless tagged]

Fresh helper, one chapter. Chain `c22` in build/speed/bt22/ (`new c22 --save bt-ch21-clear`, frame 0; tools copied
from bt21, names changed; new scratch tools `thr2.py`, `safe.py`, `cov.py`, `lure.py` (which enemies can reach which
tile next enemy phase) and `fc.sh` (forecast screenshot)). `serve` was used only for the castle opening, then
stopped (state.bin needed by rb.py); the battle was one-shot calls with act2's file undo; `chk.py` replayed the
export from frame 0 before the proof.

| | Chapter 22 'Hidden Capital' (`bt-ch22`) |
|---|---|
| Win rule | rout the enemy |
| Map | 25 x 23 town square; house blocks (impassable) on both sides leave a wide centre and edge lanes (x 1-2, x 24-25, rows 1 and 12-13); the centre (8-18, 8-17) is "plain + dragon vein" with vein tiles (TrickData type 11) at (10,10), (16,10), (10,15), (16,15) (not used). Four launchers: dagger (9,22), magic "Fire Orb" (17,22), bow (9,5), bow (17,5). They are used from the tile **south** of them ((9,23), (17,23)): the command menu there starts with Launcher / Fire Orb; at (9,21) there is none |
| Start | 15 units in the centre-south, 23 enemies (8966): boss an Adventurer lv 8 (35 HP, bow) at (13,1); six Berserkers lv 6 (48 HP, Atk 38-40, Steel or Silver Axe, range 1); four Maids (36 HP, Steel Dagger 1-2, staff); four Dark Mages lv 20 (27 HP, Fimbulvetr, Atk 24); two Fighters lv 20 (34 HP); three Adventurers (bows); two Sorcerers; a Thief |
| Enemy moves | turn 1 the south Maid and Dark Mage stood beside the south launchers and hit the whole group from far away (Hana 21 -> 6, others 2-15). The two Berserkers at (5,13)/(21,13), the Sorcerers and the edge Dark Mages charge; everything else waits until one of ours is in its reach. Reinforcements: a Maid pair (turn 2) and Dark Mage pairs (turns 3, 5) at (8,23) and (18,23) at the end of the enemy phase (they act the next one); on turn 7 the north group stepped down two rows and four more appeared (a Maid, a Berserker, a Fighter, a Dark Mage) |
| Play | turn 1 Ryoma kills the south Dark Mage, Felicia pairs onto Saizo; turns 2-6 the army sits in the south-east corner out of reach, Kaden is the only unit a charging Berserker can reach (it dies on his counter), and Ryoma (with Azura's Sing), Kaden, Saizo, Scarlet, Reina, Orochi kill the reinforcements, Sorcerers and Dark Mages as they come. Turns 7-15 Corrin is paired on Ryoma and Ryoma stands each enemy phase on a tile only one to three enemies can reach (`lure.py`); Berserkers, Fighters, Maids and Dark Mages die on his counters (Raijinto, range 1-2, doubles everything). Turn 11 Ryoma takes the boss to 1 HP and Rinkah finishes it; turn 15 Ryoma and Saizo kill the last north Adventurer and the Thief; turn 16 Scarlet (adjacent, no bow counter) and Reina (range 2) kill the last Adventurer at (2,12) |
| Turns, end | rout at 134656 (stage complete effect, turn 16), saved slot 1, castle at 139394, route ends 140084 |
| Lost (Casual retreat) | none kept. In the look-ahead: Orochi died to a Maid's counter at range 2 (turn 5); undone, Saizo and Scarlet killed that Maid instead |
| Healing | Sakura and Azama had no items; next to Corrin, Convoy > (6 RIGHTs to the staff tab) gave Bloom Festal (Sakura, +9, range 1-2) and Sun Festal (Azama, +18) |
| Supports | Felicia-Saizo 18 (A, next 20) at the start and still 18 at the end, although they fought paired several times. The Preparations Support screen showed TALK! on many units (not viewed) |

Learned [high, seen in the chain]:
- **Castle opening from bt-ch21-clear**: the load lands on Preparations (4666), B, START, 4 DOWN, A, A (Chapter 22
  first), LEFT A; one START skips the events to Preparations (6738); a look at Support (RIGHT A, then B); the next
  START is Fight! (7256), LEFT A, then A on the 'Rout the enemy' banner (about 1300 frames later).
- A unit standing beside a launcher has the launcher as its first command, so `attack` there is `menu:1 "A"`.
- `lure.py` (enemy reach from rb.json, units block, guessed moves: Berserker 6/1, Fighter 5/1, Maid 6/1-2, Dark
  Mage 5/1-2, Adventurer 6/1-2) predicted every enemy-phase attack in this chapter. A Ryoma paired with Corrin took
  at most 2 damage in a phase while killing up to two attackers.
- When the last player unit acts the turn ends by itself; act2's wait runs through the enemy phase (fine), but an
  item drop in the enemy phase stops on ItemMenuSend (DOWN x5, A, LEFT A).
- Bows (the boss, Adventurers) took Scarlet from 26 to 8 and Azura from 17 to 3 at range 2: keep fliers and Azura out
  of Adventurer reach.

Look-ahead check: `chk.py` replayed the export (1767 presses) from frame 0 on boot-server and read: 8966 [15, 23, 0]
paired 0; 25398 [15, 21, 0] paired 2; 51774 [15, 16, 0]; 89576 [15, 13, 0] paired 4; 115650 [15, 6, 0]; 131410
[15, 1, 0]; 134656 `map__SequenceCompleteEffect...` [15, 0, 0]; 137848 ChapterFileMenu; 139394 castle; 140084 castle.

Proof (`parallel.py runs --route bt-ch22 --markers --copies 2 --keep --timeout 3600`, session r11bt-22,
FEF_ROBOT_JOBS=4, FEF_ROBOT_MEM_GB=2.64): both ORIGINAL copies exit 0 after 140,084 frames, memory
**`bc342d7d1a251288`** in both, **checkpoints all met**; 530 s and 533 s side by side, peak 495 MB; %APPDATA%
unchanged. Packed from copy 1: `bt-ch22-clear.zip` sha256 `1a7de294...`. routes.json bt-ch22 `verified` set true.

Capture (`parallel.py runs --route bt-ch22 --mode capture --markers --timeout 3600`, session r11bt-22cap): exit 0,
memory `bc342d7d1a251288` (equal to the original copies), checkpoints all met, **154 functions met, 3549 records,
3469 match, 40 gave up, 40 incomplete, 0 bad of any kind**; no writer stored anything. 450 s.

Wall time, chapter 22 (start 18:45:56 to the packed save at 20:00:47): **75 min** (about 58 min look-ahead, 16 turns,
4 min the from-frame-0 check, 9 min the proof, the rest config and pack).

Continue from: `bt-ch22-clear` (slot 1 saved after chapter 22, the castle). Next: chapter 23 via Butler > Next
Battle; check the castle opening one step at a time. Felicia-Saizo is A (18, next 20) and did not move this chapter.
Sakura has Bloom Festal and Azama Sun Festal now.

## 3q. Round 11: Birthright chapter 23 (`bt-ch23`) [high unless tagged]

Fresh helper, one chapter. Chain `c23` in build/speed/bt23/ (started by a stopped helper from frame 0 of bt-ch22-clear;
its clean replay matched, instructions 158112402624 at 35284, but it had lost Silas on turn 3, so it was cut back to
turn 2 (13648) and played again from there). One-shot calls with act2's file undo (act2.py now takes `WMAX` for long
enemy phases); scratch `opt.py` (a unit's reachable tiles and who can hit each), `chk2.py` (clean replay with
instruction counts). Look-ahead only; the two-copy proof is a separate step (routes.json bt-ch23 `verified` false).

| | Chapter 23 'Camilla' (`bt-ch23`) |
|---|---|
| Win rule | rout the enemy (25 at the start, no reinforcements came in 27 turns) |
| Map | 30 x 25 dungeon: N-S lanes (x3-4, x7, x11-13, x18-19, x24, x27-28) between building blocks and two rivers (x5-6, x14-17, x25-26) with bridges; crossings at rows 7/8, 14/15, 19/20, 24. Tile 4 'building/floor' (e.g. x24 rows 21-23, x18-19 rows 8-9 and 13-14, x27-28 rows 12-13) is walkable by enemies (Paladin, Dark Knight, General, Sorcerer seen on it) but refused for our units, fliers included |
| Vein damage | on even turns every player **lead** on a vein floor (TerrainTile 1 bridge, 2 river, 7 floor) loses 10 HP at the end of the enemy phase (supports untouched); plain floor (tile 6: row 24 x20-23, row 19 x20-23, row 15 x20-23, (29-30,22), (8-10,14), (8-10,8)) is safe. Orochi and Scarlet died to it plus attacks in the look-ahead (undone) |
| Play | turns 2-4 Ryoma (Kaden), Scarlet (Silas paired via the Pair Up command) and Reina kill the Paladin, Bow Knight, Great Knight and Wyvern Lord coming down the east lanes (Reina's yumi 23x2 kills a Wyvern Lord); from turn 5 Ryoma stands on odd turns on a tile one enemy can reach (`opt.py`) and kills on his counters; on even turns the low units stand on tile 6. Turn 24-25 Beruka, Selena and the boss die to Ryoma; turn 27 Scarlet (20x2) and Reina finish Effie |
| End | stage complete 148796 (turn 27), A, talk with `answer` to ChapterFileMenu 151340, slot 1 A, LEFT A, castle 151756, route ends 152466 |
| Lost | none kept (15 of 15). Undone in the look-ahead: Silas (old chain), Scarlet twice, Orochi, Reina once |

Learned [high, seen in the chain]:
- Moving a unit onto an ally only pairs sometimes (Hana onto Corrin worked, Silas onto Rinkah did not); the command
  menu's **Pair Up** (then pick the partner, DOWN cycles) always worked.
- A Maid's Heal can break: Felicia's menu then has no Staff. Trade (Scarlet's Bloom Festal into her empty slot: RIGHT
  DOWN DOWN A, A, B) does not end the action; Staff came back in the same menu. Live to Serve heals Felicia too.
- After Switch the new lead acts at once (Felicia healed Rinkah in the same move).
- The stage-complete banner here is `castle__anonymous_namespace__Seq` and needs a second A before the talk.
- Staff target order is not position order; try `staff:0`, look, undo, `staff:1`.

Look-ahead check: `chk2.py` replayed the export (2214 presses) from frame 0 on boot-server: 8632 [15, 25, 0];
21298 [15, 23, 0] paired 6; 54700 [15, 16, 0] paired 10; 90822 [15, 10, 0]; 130744 [15, 4, 0]; 143678 [15, 1, 0];
148796 stage complete [15, 0, 0]; 151340 ChapterFileMenu; 151756 castle; 152466 castle, instructions 683220881376
equal to the chain's own state.

Wall time, chapter 23 (21:10 start to the exported press list at 23:05): **115 min** (look-ahead, 27 turns).

Continue from (after the proof packs it): `bt-ch23-clear` (slot 1 saved after chapter 23, the castle). Next: chapter 24.
Felicia carries Bloom Festal, Saizo still has a Master Seal, Dragonstone+ is in the convoy.

## 3r. Round 12: Birthright chapter 24 (`bt-ch24`) [high unless tagged]

Fresh helper, one chapter. Chain `c24` in build/speed/bt24/ (`new c24 --save bt-ch23-clear`, frame 0; tools copied from
bt23, names changed; new scratch tools `far.py` (tiles far from the cannons), `acc.py` (which of our tiles one enemy can
hit, with blockers) and `safe2.py` (every tile a unit can reach, with the enemies and cannons that can hit it)). One-shot
calls with act2's file undo; no `serve`. Look-ahead only; the two-copy proof is a separate step (routes.json bt-ch24
`verified` false).

| | Chapter 24 'Tears of a Dragon' (`bt-ch24`) |
|---|---|
| Win rule | defeat the boss (Hans, Berserker lv 13, 69 HP, Def 11, Brave Axe / Silver Star Axe, at (13,1)) |
| Map | A024, 25 x 30: a round hall (rows 7-23) with a wall block in the middle (11-15, 13-17) and four 3-wide arms (north x12-14 rows 1-6, south x12-14 rows 24-30, west rows 14-16, east rows 14-16) over open sky (tile 1, fliers only). Veins at (10,15), (16,15), (7,21), (19,21): Ryoma can use them; (10,15) "creates a storm that slows fliers" in the north-west quarter (not used) |
| Cannons | three magic cannons (TrickData type 27) at (13,27), (9,9), (17,9), fired by a Sorcerer standing on the tile beside them ((13,28), (9,8), (17,8)). Plus-shaped, **reach 10 tiles** from the cannon (every hit seen was at 10 or less; nothing at 11 or 12 was hit), damage about 25 minus Res (Felicia 10, Azura 12-13, Corrin 14, Ryoma 7, Kaden 9). Two cannons can hit the same pair. They were the main cost of this chapter |
| Enemies | 21 at the start (a pair-up of Generals, Berserkers, Sorcerers 37 atk, Brave Heroes, a Great Knight). The west group (2 Heroes, a Berserker, a Sorcerer) and the east Berserker and Sorcerer come at once; the rest wait until someone is in reach. **Reinforcements every enemy phase from turn 3**: a Hero at (1,16), two Wyvern Lords (41 HP, Def 24, Atk 36) at (1,28)/(1,29), from turn 4 a Sorcerer at (25,16); turn 7 two more fliers at (25,29)/(24,30). Hans stayed on his tile the whole time (AI 'attack in range' did not pull him out at (12,8)) |
| Play | turn 1 seven pairs, out of the south General's reach; turn 2 Ryoma (Hana) kills a Hero at range 2 and the west group dies on his counters; turn 3 Ryoma kills the Great Knight (30 x2, no counter), Saizo + Scarlet kill the east Berserker, Kaden + Reina the east Sorcerer; turns 4-7 the army kills the next Heroes, Sorcerers and the Wyvern Lords (Reina's yumi 23 x2 one-rounds them; Azura's Sing gave her a second kill), two Vulneraries taken from the convoy, and the weak pairs stand only where `safe2.py` shows no enemy and no cannon; turn 6 Ryoma kills the (9,8) cannon Sorcerer and the west General dies on his counter; turn 7 he waits at (12,8) (a Berserker dies on his counter); turn 8 he kills Hans from (13,3): 40 x2 at 100%, Hans cannot counter |
| End | boss dead 83174 (`castle__anonymous_namespace__Seq` with the complete effect, 11 enemies still on the map), talk with `answer` to ChapterFileMenu 86976, slot 1, castle 87392, route ends 88102 |
| Lost | none kept (15 of 15). Undone in the look-ahead: Scarlet (twice), Silas (twice), Orochi, Asama, Felicia, Azura (to the south General at (13,22)) |

Learned [high, seen in the chain]:
- Ryoma has Avo 92: enemy hit on him is about 10% (Sorcerer) to 30% (Great Knight); he is the only safe lure. Swords
  beat axes: Berserkers, Wyvern Lords and Hans die on his counters or to one round.
- A Sorcerer (Atk 37, Fimbulvetr 1-2) kills any of our soft units; plan every enemy phase with the Sorcerers' reach
  (`acc.py`), not only melee reach. Units block enemy paths: a pair on (15,18) kept the east Sorcerer off Kaden.
- Convoy: a unit next to Corrin's pair has Convoy; 9 RIGHTs reach the item tab; Take, then Items > Use (the Vulnerary
  ends the action, the Take does not).
- `bd.sh`'s HP read is wrong for some paired units (Felicia showed 10 while her panel said 20); trust the panel.
- Kaden (Kitsune) cannot use the Wakizashi; Azama has no weapon or staff (Trade, Rally, Switch only).

Look-ahead check: `chk2.py` replayed the export (1172 presses) from frame 0 on boot-server: 8660 [15, 21, 0] paired 0;
25920 [15, 16, 0] paired 14; 48124 [15, 15, 0]; 71734 [15, 12, 0]; 80854 [15, 12, 0]; 83174 boss dead [15, 11, 0];
86976 ChapterFileMenu; 87392 castle; 88102 castle, instructions 394797043872 equal to the chain's own state.

Wall time, chapter 24 (02:59:42 start to the exported press list at 05:08:40): **129 min** (look-ahead, 8 turns, many
undone enemy phases).

Continue from (after the proof packs it): `bt-ch24-clear` (slot 1 saved after chapter 24, the castle). Next: chapter 25.
Azura and Asama ended at 1 HP, Kaden 13 (heal between chapters). Azura carries a Vulnerary (2).

## 3s. Round 12: Birthright chapter 25 (`bt-ch25`) [high unless tagged]

Fresh helper, one chapter. Chain `c25` in build/speed/bt25/ (`new c25 --save bt-ch24-clear`, frame 0; tools copied from
bt24, names changed; `lib25.py` (A025 move costs); new scratch `dz.py` (danger map: how many enemies can hit each tile,
fixed units by weapon range only, and who); act2.py now refreshes a stale cursor before `end` too; fc.sh stops when act2
refuses). One-shot calls with act2's file undo; no `serve`. Look-ahead only; the two-copy proof is a separate step
(routes.json bt-ch25 `verified` false).

Azura, Asama and Kaden ended chapter 24 low; the game heals between chapters (turn 1: Azura 17, Asama 30, Kaden 34, all full).

| | Chapter 25 'Traitor Revealed' (`bt-ch25`) |
|---|---|
| Win rule | defeat the boss (Iago, Sorcerer lv 15, 50 HP, Ginnungagap 1-2, at (13,3)) |
| Map | A025, 25 x 30, walls (tile 1) stop fliers too. South corridor rows 28-30; a 3-wide lane x12-14 rows 24-27 with three **fixed** Generals (12-14,26) (they only hit adjacent tiles) and an Entrap Strategist (13,25); hall rows 20-23; lanes x8-10 and x16-18 rows 17-19; dragon-vein room rows 12-16 with a magic cannon (8,13) and a shuriken cannon (18,13); north corridor x10-16 rows 6-11; boss room rows 1-5 |
| Cannons | fired by an enemy standing beside them (Sorcerer at (8,12), Maid at (18,12)); a hit landed at Manhattan distance 9-10 from the cannon (Azura 17 -> 1 twice). Dangerous to soft units anywhere within 10 |
| Enemies | 28 at the start (Normal set: DisposUnit flag bit 0x100; bit 0x4000 = fixed). Movers attack whatever is in move + range. Reinforcements (DisposUnit `Reinforce01-05`): Great Knight + Bow Knight at (2,28)/(1,29) on enemy phases 1 and 3; Great Knight + Dark Knight at (24,28)/(25,29) on phase 2; Sorcerer + Hero in the NW room (3,8)/(6,8) on phase 5; two Maids in the NE room on phase 6; Berserker + General in the boss room on phase 7. None after that up to turn 16 |
| Play | turn 1 Ryoma (Hana paired) kills the Entrap Strategist from (13,27) (35 x2); turn 2 he kills the south General, Azura sings, he kills the east Great Knight (24 x2 at range 2); turns 2-5 Ryoma, Scarlet (Killer Axe crit) and Reina finish the west knights while two blockers hold column x10 (Corrin, Asama+Felicia) so only sturdy units are in reach; turns 6-9 the army goes up the lane (only (13,27), (13,25), (13,24) are safe from the fixed Generals) into the hall; Ryoma lures the NW Sorcerer and Hero, kills the magic-cannon Sorcerer from (9,13) and two Berserkers on his counters; turns 10-11 Scarlet (Maids do 0 to her) and Reina kill the two Maids while every soft unit stands where no Maid can reach (`dz.py`); turns 12-15 Ryoma waits on tiles only one or two enemies reach: north General, Strategist, a reinforcement General, a boss-room General and a Hero die on his counters; turn 16 he kills Iago from (11,3): 32 x2 at 97%, Iago 8% |
| End | boss dead 127712 (`castle__anonymous_namespace__Seq` STAGE COMPLETE, turn 16, 14 enemies still on the map), A, talk with `answer` to ChapterFileMenu 131814, slot 1 A, LEFT A, castle 132230, route ends 132940 |
| Lost | none kept (15 of 15). Undone in the look-ahead: Reina (first turn and again to the Maid + cannon), Saizo and Subaki (to the west Great Knight, Bow Knight and Hero), Azura (to the Dark Knight), Rinkah (to a Great Knight), Silas (to a Maid) |

Learned [high, seen in the chain]:
- Most units are weak against Great Knights (Saizo 0, Reina 3, Corrin 13 a hit); only Ryoma (20-24 x2 at range 2, no counter)
  and Scarlet (12 x2, crits) hurt them. Ryoma's Raijinto counters at range 2 (a Bow Knight died attacking him).
- Maids (silver dagger) kill soft units (Silas 24 HP in one round) but do 0 to Scarlet.
- A drop on a full inventory: ItemMenuSend (DOWN x5, A, LEFT A sends the new item). act2 `raw` runs on any screen: fc.sh
  must stop when the `show` step is refused, or `undo 2` takes back a real move (happened once; fixed and re-done).
- Corrin's command menu: Items, Trade, Convoy, Switch, Separate, Wait; Switch made Azura the lead and she could still act
  (Items > Vulnerary). Pair Up from a unit's menu: Items, Trade, Pair Up (DOWN DOWN A, then A on the partner).
- Fates ends the player phase by itself after the last unit acts (turn 7).

Look-ahead check: `chk2.py` replayed the export (1812 presses) from frame 0 on boot-server: 9328 [15, 28, 0] paired 0;
15044 [15, 29, 0]; 28670 [15, 27, 0]; 43634 [15, 25, 0]; 61174 [15, 27, 0]; 76850 [15, 25, 0]; 97380 [15, 24, 0];
112368 [15, 19, 0]; 121742 [15, 16, 0]; 125190 [15, 15, 0]; 127712 stage complete [15, 14, 0]; 131814 ChapterFileMenu;
132230 castle; 132940 castle, instructions 595722219840 equal to the chain's own state.

Wall time, chapter 25 (09:04:47 start to the exported press list at 10:14:23): **70 min** (look-ahead, 16 turns).

Continue from (after the proof packs it): `bt-ch25-clear` (slot 1 saved after chapter 25, the castle). Next: chapter 26.
Azura ends at 1 HP (support of Corrin); the game heals between chapters.

## 3t. Round 14: Birthright chapter 26 (`bt-ch26`) [high unless tagged]

Fresh helper, one chapter. Chain `c26` in build/speed/bt26/ (`new c26 --save bt-ch25-clear`, frame 0; tools copied from
bt25, names changed; `lib26.py` (A026 move costs); new scratch `trig.py` (for every enemy, which of our units it can hit
next enemy phase, with planned moves `=X,Y>X2,Y2`) and `cmp.py` (tiles forecast shots into one picture); dz.py's fixed
units now come from the FIXED env). One-shot calls with act2's file undo; no `serve`. Look-ahead only; the two-copy
proof is a separate step (routes.json bt-ch26 `verified` false).

| | Chapter 26 'Xander' (`bt-ch26`) |
|---|---|
| Win rule | defeat the boss (Xander, Paladin lv 18, 60 HP, Siegfried 1-2, Atk 31, Spd 15, Def 22, Res 12, at (18,11)) |
| Map | A026, 29 x 20. A walled throne room (rows 9-12, x 11-19) with **closed doors** (terrain 5) at (15,8) and (15,13); Corrin starts alone inside it at (12,11). The army (16 units: Shura, the Adventurer, is new) starts south of the room; the only way to the south door is a 1-wide corridor (15,14)-(15,16) held by a **fixed** General (bit 0x4000) at (15,15). West and east corridors x3-4 / x26-27 rows 8-13 are held by Generals too |
| Enemies | 27 at the start (Normal set, DisposUnit bit 0x100). AI (DisposUnit ai_action): Xander `AI_AC_Turn 8` (he did not act on turns 1-2 with Corrin in reach); Laslow + Heroes NW wake on turn 3, Peri + Great Knights NE on turn 4, the east Great Knights on turn 2, Heroes, Maids, Berserkers, Generals on turn 7 (or when someone is in reach); Bow Knights and a Revenant Knight (Fimbulvetr) move every turn. No reinforcements in the table |
| Doors | no Door Key in the convoy; **Locktouch** (skill 112) opens a door from the next tile (command `Door`, first in the menu): Saizo and Shura have it. Shura opened (15,13) from (15,14) once the General was dead |
| Play | turn 1 Ryoma hits the door General from range 2 ((16,16), then (14,16) after Azura's Sing from (16,17)): forecast 7 x2 each time, 56 -> 10 (more than forecast; a crit is likely, the fight was not looked at); Reina moves out of a Hero's reach; a Brave Hero comes for Ryoma and dies on his counter. Turn 2 Ryoma kills the General from (14,16), Shura opens the door, Azura sings from (15,16), Ryoma walks in to (16,12); Corrin, Convoy, stones tab, Dragonstone+ > Trade with his Dragonstone (Atk 27 -> 38; the Take/Trade does not end his action, then Wait); Reina kills the Revenant Knight from (11,16) (30 x2, 100%). Turn 3 Ryoma attacks Xander from (17,11) (forecast 27 x2 at 100%, Xander 7%) and he dies in that one fight (54 forecast against 60 HP: a crit or a follow-up, not looked at) |
| End | boss dead, `map__SequenceCompleteEffect` 27332, STAGE COMPLETE (`castle__anonymous_namespace__Seq`) 27642, turn 3, 23 enemies still on the map; A, talk with `answer` to ChapterFileMenu 30334, slot 1 A, LEFT A, castle 30750, route ends 31460 |
| Lost | none (16 of 16). Nothing was undone for a loss; the only undos were menu looks (convoy tabs, Corrin's menu) |

Learned [high, seen in the chain]:
- Xander has low Res (12): Corrin's Dragonstone (magical) did 13 a hit, Dragonstone+ 24; Ryoma's Raijinto 27 x2.
- The fixed door General took 0 from Orochi (Rat Spirit), Kaden, Silas, Reina and Saizo; only Ryoma (7 x2 at range 2,
  no counter; 9 x2 in melee with a 29 counter) and Scarlet (4 x2, 31% crit) hurt him.
- Corrin's command menu with nobody beside him: Items, Convoy, Wait (Convoy = DOWN A); with an ally beside him: Items,
  Trade, Convoy, Pair Up, Wait. The convoy opens on the items tab; LEFT goes to the stones tab; RIGHT on the last tab
  moves the cursor to the unit's list. A convoy item on a full inventory offers Take / Trade.
- Sing only offers units that have already acted, so the target choice is a single A.

Look-ahead check: `chk2.py` replayed the export (304 presses) from frame 0 on boot-server: 10132 [16, 27, 0];
16970 [16, 26, 0]; 25168 [16, 24, 0]; 27642 stage complete [16, 23, 0]; 30334 ChapterFileMenu; 30750 castle;
31460 castle, instructions 140976538560 equal to the chain's own state.

Wall time, chapter 26 (12:32:13 start to the exported press list at 13:01:50): **30 min** (look-ahead, 3 turns).

Continue from (after the proof packs it): `bt-ch26-clear` (slot 1 saved after chapter 26, the castle). Next: chapter 27.
Corrin now carries Dragonstone+ (his Dragonstone is in the convoy). Ryoma ends at 28 HP, Reina 27 (heal between chapters).

## 3u. Round 15: Birthright chapter 27 (`bt-ch27`) [high unless tagged]

Fresh helper, one chapter. Chain `c27` in build/speed/bt27/ (`new c27 --save bt-ch26-clear`, frame 0; tools copied from
bt26, names changed; `lib27.py` (A027 move costs)). One-shot calls with act2's file undo; no `serve`. Look-ahead only;
the two-copy proof is a separate step (routes.json bt-ch27 `verified` false).

| | Chapter 27 'King Garon' (`bt-ch27`) |
|---|---|
| Win rule | defeat the boss (Garon, Nohrian King lv 40, 68 HP, Bolverk 1-3, Atk 51, Spd 20, Def 23, Res 23, on the throne at (13,7): +3 Def, +30 Avo, heals 20% each turn). Skills 10 and 114: **Dragonskin** (halves the damage he takes, no crits on him) |
| Map | A027, 25 x 30 hall. Throne room x12-14 rows 7-11 with three Generals across row 11; open hall below; side rooms NW/NE (rows 7-11) and W/E wings |
| Enemies | 26 at the start (Normal set, DisposUnit bit 0x100). Fixed (bit 0x4000): Garon (AI attack in range 1-3), Sorcerer (12,7) (Vantage, range 1-2), Maid (14,7) (Pavise, Aegis, Miracle, Recover: heals Garon). Not fixed but MV_Null (they move only to hit someone in move + range): Generals (row 11, (13,23)), Berserker (13,16) (Brave Axe, Swordbreaker, Vengeance, Counter; Atk 43, Spd 27, Def 11), Great Knights, four Wyvern Lords (Def 27, Res 11). NearestEnemy every turn: a Berserker and a Hero (south). Wake by turn: Bow Knights 2, Revenant Knights 3, Strategists 4/6, Dark Knights 5. No reinforcements came |
| Play | turn 1 Ryoma kills the south General (crit); turn 2 he kills the Berserker and, after Sing, the Hero; turn 3 Felicia heals him and he kills the east Bow Knight from (18,24), soft units step east out of the other's reach; turn 4 he kills the west Bow Knight; turns 5-7 the Revenant and Dark Knights die on his counters (they hit him 0-4%), a Great Knight and a Strategist too; turn 8 Shura (dual strike with Ryoma) finishes a Wyvern Lord; turns 9-12 Ryoma lures the Wyvern Lords one or two at a time (tiles from `trig.py`), Reina and Ryoma finish them; turn 13 Ryoma kills the Berserker from range 2 at (13,18) (40 x2, 66%), Sing, then he waits on a tile only one General reaches; turn 14 he kills the lured west General from range 2 and, after Sing, baits the east General, which dies on his counter; turn 15 he kills the last General from range 2 in one fight (18 x2 forecast against 53 HP, likely a crit; it cannot counter there); turn 16 he kills the Maid from (14,9) (25 x2); turns 17-18 he hits Garon from (13,9) (11 x2 at 82%, Garon 28 at 13%; Garon heals 13 a turn), turn 18 Azura sings from (14,9) and his second round kills Garon |
| End | boss dead `map__SequenceCompleteEffect` 94864, STAGE COMPLETE (`castle__anonymous_namespace__Seq`) 94894, turn 18, 1 enemy (the Sorcerer) left; A, A, then 501 answered talk presses lead **straight to the Endgame Preparations** (`sortie__anonymous_namespace__TopMenu`) 111258: **no save prompt and no castle** after chapter 27. Exit ("Return to your castle") is refused there; a B and two A on Exit (no effect) end the list at 112772 |
| Lost | none kept (16 of 16). Undone in the look-ahead: Ryoma once (killing the Berserker on turn 9 left him in reach of the General and three Wyvern Lords; he died on the enemy phase), plus menu looks and moves that did not reach |

Learned [high, seen in the chain]:
- Garon cannot be killed in one player phase here: Dragonskin halves Ryoma to 11-12 a hit, Corrin's Dragonstone+ does 6 at 33%, Reina 3; the
  Maid's Recover undoes chip damage, so the Maid goes first. Ryoma on (13,9) is the only unit in his reach and counters at range 2.
- Generals hold a range-1 lance first: a range-2 Raijinto attack gets no counter (14-18 x2).
- `trig.py` (move + weapon range, FIXED env) predicted every enemy phase correctly; one unit per lure tile works.
- bd.sh's name "Yugiri" is Reina (PID_ユウギリ).
- The castle checkpoint cannot exist for this chapter; the route's last checkpoint is the Endgame Preparations.

Look-ahead check: `chk2.py` replayed the export (1617 presses) from frame 0 on boot-server: 9860 [16, 26, 0]; 12186 [16, 25, 0];
17788 [16, 22, 0]; 23368 [16, 21, 0]; 25788 [16, 20, 0]; 34660 [16, 15, 0]; 40434 [16, 13, 0]; 45448 [16, 11, 0];
52442 [16, 10, 0]; 55606 [16, 10, 0]; 60438 [16, 9, 0]; 65766 [16, 7, 0]; 68572 [16, 7, 0]; 74412 [16, 6, 0]; 79066 [16, 4, 0];
84468 [16, 3, 0]; 88346 [16, 2, 0]; 90726 [16, 2, 0]; 94864 complete effect [16, 1, 0]; 94894 stage complete [16, 1, 0];
111258 Endgame Preparations; 112772 Preparations, instructions 505346668992 equal to the chain's own state.

Wall time, chapter 27 (16:22:34 start to the exported press list at 17:20:17): **58 min** (look-ahead, 18 turns).

Continue from: there is **no in-game save** after chapter 27 (the game goes from the chapter straight to the Endgame
Preparations). Owner chose the chain state (F-029, 2026-11-16); the Preparations menu, its R Options and View Map
were checked on a copy of c27 and offer no Save, so Endgame starts from c27's state (`--import-chain`).

## 3v. Round 16: Birthright Endgame (`bt-endgame`), NOT cleared [high unless tagged]

Fresh helper, one chapter, cap 100 min of play. Chain `ce` in build/speed/btend/ = a **copy** of c27's folder (chain.json,
inputs.txt, state.bin, last.json; c27 untouched, same sha256 when copied). c27 itself started at frame 0 of
bt-ch26-clear, so ce's inputs.txt is already one absolute press list: bt-ch27's exact 1617 presses (checked equal to
routes.json bt-ch27) + the Endgame presses. Tools copied from bt27 (paths changed; lib27.py now reads A028), new
scratch `place.py` (our unit's reachable tiles, who can hit each) and `who.py` (which of our units can attack a target).
One-shot calls with act2's file undo; no `serve`. Look-ahead only. **No route key written** (chapter not won).

| | Endgame 'Dawn Breaks' (A028) |
|---|---|
| Start | Preparations cursor on Exit: menu is 2x3 (Select Units / Inventory, View Map / Equip Skills, Fight! / Exit): `LEFT A` = Fight!, then the "Start the battle?" dialog `LEFT A`; talk answered (A every 30 frames) to 113870; the "Victory: Defeat the boss" banner needs an **A** (sent at 115962); player phase 116186 |
| Boss | Garon, **Blight Dragon** lv 40, 78 HP, Atk 56 (Dark Breath, magic, range 1-2, 100% hit), Spd 27, Def 25, Res 25, **Mov 6**, Dragonskin (halves damage). Starts (13,9); on the turn-4 enemy phase he moved to (12,11). Forecast: Scarlet's Killer Axe 7. Ryoma (Atk 44) would do about 9 a hit x2; one breath does about 36 to Ryoma, 41-49 to Corrin |
| Key item | Corrin's **Blazing Yato** (item 38) carries the flag ISID_竜鱗有効 (works through Dragonskin): Mt 16, Corrin Atk 37 with it (12 a hit on Garon, no double). Equipped on a copy of turn 5 (Items, DOWN, A, Equip): it drops Corrin's Def 23->13 and Res 15->7 (the Dragonstone+ bonus goes) |
| Enemies | 26 at the start. MV_Null near the throne: General (13,11), Brave Hero (15,12), Maids (14,10), (18,10). Brave Hero (6,17), Hero (7,28), Berserker (6,25) wake on turn 4. NearestEnemy from turn 2: Great Knight (11,30), Bow Knight (22,28), **Dark Knight (4,27): Ragnarok, Atk 33, 100% hit, range 1-2, Mov 8, Def 25 Res 20** (killed Silas, 24 HP, on a counter at range 2). **Golems: Boulder range 1-5** (weapon kind 18; the copied trig/dz/place ignored kinds >= 11 until fixed on turn 5, so turn-4/5 Golem threats were missed). A reinforcement Hero appeared at (3,18) on the turn-5 enemy phase; the ground starts to blight (purple tiles, west) by turn 5 |
| Play | turn 1 Ryoma (15,18) lures both Heroes; they die on his counters. turn 2 Reina+Corrin+Saizo kill the Great Knight, Kaden+Scarlet the Bow Knight, Ryoma (15,16) lures the throne Maid (dies on his counter). turn 3 Saizo+Reina kill a Hero; everyone else is moved out of the Dark Knight's reach (pairs: Azura on Shura, Hana on Asama, Silas on Rinkah, Saizo on Corrin). turn 4 Felicia heals Ryoma, Ryoma kills the Revenant (12,17) from (12,18), Shura pair moves to (13,18), Switch (4th item), Azura sings Ryoma, Ryoma kills the Dark Knight from (13,23) at range 2 (no damage taken), Scarlet kills the Dragon Master (15,15) |
| Stop | turn 5 player phase, frame 158338, **16 of 16 alive**, nobody has acted yet, 17 enemies. Chain ce is kept there |
| Lost | none kept. Undone in the look-ahead: Silas (Dark Knight counter), Corrin's attack on the Dark Knight (left at 6 HP), Orochi (Revenant counter after a Switch), Rinkah+Sakura (turn-4 enemy phase, Dark Knight went round to (13,17)), five units on one turn-5 try (threat list read from a stale board), Shura (Brave Hero, 4 hits) + Rinkah (Hero) + Subaki (Golem range 5) on a second turn-5 try |

Why it stopped (at 63 min of play, with 37 left): from turn 5 the army is boxed in. North: Garon (reach 8), the Brave
Hero (12,17) (killed Shura, 34 HP, Def 14, in one enemy phase) and a Maid; south-west: a Hero and a Golem; east: a
Golem with range 5 that reaches Corrin at (18,24); reinforcements start. No safe tile was found for every unit, and the
boss itself needs about 3 attack turns. That does not fit in the cap, so the chain was put back to the clean turn-5
start instead of keeping a half-played turn.

Plan notes for the next try [medium, not tested]:
- Garon is beaten with Corrin's Yato and dual strikes: Corrin unpaired and **adjacent** to the attacker adds a Yato hit
  (about 12, through Dragonskin) without taking the counter. Shura's Spy's Yumi is range 3 only, so Shura + Corrin hit
  Garon with no counter at all (about 1 + 12). Ryoma + Corrin about 18 + 12, but Ryoma takes one breath (about 36).
- Corrin must end every player phase out of Garon's reach (or paired as support), and with the Dragonstone+ equipped
  when he is in anyone's reach (Res 7 with the Yato).
- Use the Golem fix (kind 18 range 1-5) and run `bd.sh` before every `trig.py` (the board file is not refreshed by
  act2).
- Kill the Brave Hero (12,17) before standing in its reach; it is the deadliest unit left. Bloom Festals (heal 12) are
  spread over Felicia, Saizo, Scarlet; Sun Festals over Ryoma, Saizo, Reina; Sakura and Asama carry no staff.
- Corrin carries a Master Seal (Nohr Prince lv 20, not promoted) and Orochi a Dracoshield; not used.

Look-ahead check: `chk2.py` replayed the export (2163 presses = bt-ch27's 1617 + 546) from frame 0 of bt-ch26-clear on
boot-server: 112772 Preparations [16, 26, 0], instructions 505346668992 (equal to c27's proven state); 116186 [16, 26, 0];
124400 [16, 24, 0]; 137634 [16, 21, 0]; 147738 [16, 20, 0]; 158338 [16, 17, 0], instructions 709534111968, equal to
chain ce's own state. Export: build/speed/btend/ce-export.json; log: build/speed/btend/chk.log.

Wall time, Endgame (20:38:13 start to the exported press list at 21:41:33): **63 min** of play, not cleared; the
replay check took another 10 min (to 21:52).

## 3w. Round 17: danger tools fixed [high unless tagged]

Scratch look-ahead tools only (build/speed/btend/tools/, host python + boot-server reads, below normal). The four
threat tools `trig.py`, `dz.py`, `place.py`, `who.py` now sit on one shared file, `danger.py`; the round-16 copies are
kept in `tools/old_r16/` for comparison. What changed:

- **Every weapon kind, its own range.** An item is a weapon when its sub-kind's ItemKind (ItemSubKind.csv `kind`) is
  not 6 (staff) and not 8 (item); the attack distances are the item's own `range_min..range_max` (union over all
  weapons carried). Before: `dz.py` counted sub-kinds < 11 only, so Garon's breath (16), the Nosferatu fists (17) and
  the Golem Boulder (18, range 1-5) fell back to "1-2"; `trig.py`/`place.py` (patched mid-turn-5) left out scrolls (11),
  stones (14, 15) and Mechanist weapons (19) and counted staves (12, 13: range up to 1-255) as attacks; `who.py` counted
  sub-kinds < 9 only (no tomes, scrolls, stones) and skipped pair leaders. A unit with no weapon is now no threat.
- **No stale board possible.** `danger.board(chain)` reads state.bin itself (one boot-server load: units, items per
  unit, move boost, map) and keeps `board.json` stamped with the sha256 of state.bin; every call re-hashes and re-reads
  when it changed. `bd.sh` is no longer needed before a threat read. Items are taken per unit, not matched by tile
  (that mixed up paired units). A read with an empty map or no units stops with an error.
- **Reach** = Job mov + the unit's move boost (Unit+0x12C, max 2) with the A028 terrain costs (as before); our units
  block; tiles held by other enemies count as end tiles (safe side; `STRICT=1` turns that off). `FIXED` now defaults to
  no enemy (the old defaults "15,15" and "13,9", Garon's start, were stale: he moved on turn 4).

Self-test, on a copy of chain ce (build/speed/btend/ce-dt; ce's state.bin, chain.json, inputs.txt sha256 unchanged),
turn 5 player phase, frame 158338:

| Check | Old (round 16 copy) | Fixed |
|---|---|---|
| Corrin (18,24) | dz: nobody | Golem (20,18), range 1-5 |
| Subaki's tile (18,21) | dz: Golem as range 1-2 | Golem (20,18) range 1-5, Maid (17,14) |
| Shura's tile (13,18) | dz: Garon, Brave Hero, Maid | Garon, Brave Hero (12,17), Maid, Golem (20,18) |
| Weapon ranges | | all 21 sub-kinds checked: Boulder 1-5, breath 1-2, dagger 1-2, bow 2, tome/scroll 1-2, every staff none |
| Stale board | trig read rb.json as left | state.bin swapped to the turn-4 one: frame 150206 read at once; put back: 158338 again |

[medium] The exact tiles Subaki and Shura stood on in round 16's second turn-5 try were not kept (that try was undone
and not in ce/hist); the test uses their turn-5 tiles and the killers named in 3v. The other scratch tools in that
folder (thr*, lure*, safe*, reach.py, lib27.py) still carry the old rules; use the four above.

### 3w-2. Round 17: Endgame try from the turn-5 chain, NOT cleared [high unless tagged]

Fresh helper, cap 100 min of play. Chain `cf` = a copy of ce (chain.json, inputs.txt, state.bin, last.json, server,
_tools; new empty hist, so undo can not go below turn 5). ce and c27 untouched (ce state.bin / inputs.txt sha256 the
same after the round). Threat reads with the fixed `danger.py` tools plus new scratch `gz.py` (map of who hits each
tile, with planned moves and kills), `srch.py` / `srch2.py` (try every end-tile mix for the last few units). Look-ahead
only. **No route key written** (Garon not beaten).

| Turn | What happened (kept line) |
|---|---|
| 5 | Ryoma kills the Brave Hero (12,17) (2x35); Reina + Scarlet kill the Golem (20,18); Saizo trades a Bloom Festal to Asama, Asama heals Kaden; Felicia heals Ryoma to 43; Shura pair switches (Shura lead, takes the Berserker hit, 5 HP left). Garon did **not** attack Ryoma, who stood in the tool's Garon reach |
| 6 | Reina (+Corrin dual) and Shura hit the Berserker, Ryoma kills it; Saizo + Felicia (Saizo dual) kill the Brave Hero; Scarlet blocks the Maid's path to Shura; Kaden pairs onto Scarlet. Garon moved (12,11) -> (14,11) |
| 7 | Saizo + Reina kill the Maid; Ryoma (moved to (13,18)) uses the Energy Drop; Corrin uses the **Master Seal: Hoshido Noble** (41 HP, Str 24, Mov 6); the new Brave Hero dies on Ryoma's counter |
| 8 | Shura pair Separated (both units grey after a Separate); Reina + Saizo kill a Malig Knight; staging around (13-16, 15-18). Garon moved (14,11) -> **(14,9)** |
| Stop | **turn 9 player phase, frame 206992, 16 of 16 alive, nobody acted**, Garon 78/78 at (14,9). Chain cf is kept there |
| Lost | none kept. Undone in the look-ahead: Ryoma on the first turn-7 try (stood on a blight tile at (10,17) after killing a Brave Hero; blight 10 + Berserker + Maid). A turn-9 start (General left at 4 HP, Corrin open to a Berserker double and a Golem/Malig on Felicia) was rolled back to the turn-9 start file copy |

What was learned [high]:
- **Garon does not move to attack.** DisposUnit: `AI_AC_Everytime`, `AI_AT_Null`, `AI_MV_Null`. Ryoma (12,18) and
  Shura (13,18) sat 7-8 tiles away with nothing in between and were not attacked. He shifts by script every 2nd enemy
  phase (turns 4, 6, 8) between the 1x1 trick tiles (12,9), (12,11), (14,9), (14,11) inside the throne alcove (walls at
  x=11 and x=15, opening on row 12). So the threat tools must be run with `FIXED="<Garon tile>"`; without it they put
  his reach out to 8-10 tiles. Next shift expected on the turn-10 enemy phase.
- **Blight**: units standing on blight tiles lose 10 HP at the enemy phase but never go below 1. The tools do not know
  blight tiles. Several units sit at 1-6 HP now (Rinkah 1, Sakura 1, Saizo 6, Subaki 6, Shura 8).
- Other enemies with `AI_MV_Null` (Berserker (8,14), Golem (18,7), General (21,11), Maid (5,15)/(11,6)) do move and
  attack anything in their own reach; Malig Knights (fliers, Fimbulvetr 1-2, Atk 30 magic) and Brave Heroes keep
  coming as reinforcements (west (3,18), east (24,12)/(24,20), south (18,21)).
- Dual strike: only an **unpaired** attacker gets one, from an **unpaired** neighbour; the neighbour does not need to
  have its action left. Corrin's dual with the Dragonstone+: 24 on the General, 14 on a Berserker. Shura's Spy's
  Yumi hits once (no double). Pair Up: the unit that moves becomes the support. Separate greys both units.
- Felicia's Bloom Festal is used up; Asama now carries Saizo's Bloom Festal (heals 11).

Plan for the next try from cf (turn 9, Garon (14,9)) [medium, not tested]: the throne General (13,11) blocks the
middle; Ryoma (range 2, 18x2) + Corrin dual (24) kill it in one attack (tested, but then Corrin stood open). Strike
shape for Garon at (14,9): Corrin (13,10) waits; Shura (unpaired, Spy's Yumi range 3) from (12,10) or (13,11): 1 +
Corrin 15; Ryoma (14,10): 10 + 15 + 10, takes one breath (36; needs 37+ HP); Azura sings Shura for a second shot
(16); finisher on the other d1 tile (13,9) with Corrin's dual (Felicia 0 + 15). Sum about 82 of 78; any miss fails.
Before that, the turn-9 enemy phase must be survived with the Berserker (8,14), the Golem (18,7) range 5 and a Malig
Knight (18,12) all reaching the staging tiles.

Look-ahead check: `chk2.py` replayed the export (2882 presses = ce's 2163, checked equal as a prefix, + 719) from frame 0
of bt-ch26-clear on boot-server: 158338 [16, 17, 0] instructions 709534111968 (equal to ce); 172262 [16, 16, 0];
184762 [16, 16, 0]; 196820 [16, 17, 0]; 206992 [16, 19, 0], instructions 927559302912, equal to chain cf's own state
(after the turn-9 rollback, so the rollback replays clean). Export: build/speed/btend/cf-export.json; log:
build/speed/btend/chkf.log.

Wall time, Endgame (00:04:51 start to the exported press list at 01:01:34): **57 min** of play, not cleared; the replay
check took another 11 min (to 01:12:56).

### 3x. Round 18: Endgame third try (Grok's plan) from the turn-5 chain, NOT cleared [high unless tagged]

Fresh helper, cap 100 min of play. Chain `ch` = a copy of ce (chain.json, inputs.txt, state.bin, last.json, server,
_tools; new empty hist). ce, cf, cg and c27 not changed (ce state.bin / inputs.txt / chain.json sha256 the same after
the round). Grok's plan (docs/collab/ENDGAME_GROK.md) followed: walk north, kill only what blocks or covers the path,
no Separate on a strike turn, threat reads with the fixed danger tools and `FIXED="<Garon tile>"`. Turn-start copies:
build/speed/btend/ch-t6start, ch-t7start, ch-t8start. Look-ahead only. **No route key written** (Garon not beaten).

| Turn | What happened (kept line) |
|---|---|
| 5 | Ryoma kills the Brave Hero (12,17) (35x2, 100%); Reina + Scarlet kill the Golem (20,18) (its range 1-5 covered every tile of the walk north; Scarlet left at 3 HP by the counter); Azura/Shura Switch (Shura lead); Felicia pairs onto Ryoma (move next to him, **Pair Up** is the 4th command; moving onto his tile does not pair); Corrin moves to (18,19) and uses the **Master Seal: Hoshido Noble** in the same action (no move lost; Mov 6, Yato Atk 40, Hit 119). Undone: Felicia alone at (14,18) (killed by the Maid) |
| 6 | Ryoma kills the Berserker (13,20) (38x2, Berserker 0% hit on him); Reina + Scarlet (Reina dual) kill the Maid; Shura/Azura Separate on a quiet turn (Azura to (16,16): the Separate tile is picked with LEFT/DOWN, default was (15,15) in the General's reach). Garon shifted (12,11) -> (14,11) on the turn-6 enemy phase, as in cf |
| 7 | Ryoma (with Felicia) as bait at (12,17): the Berserker (8,14) and the Brave Hero (9,18) attack him and **both die on his counters**; Reina + Scarlet (dual, crit) kill the Hero (13,22); everyone else on tiles the tools call safe. Blight took the low ones to 1 (Rinkah, Sakura, Scarlet) |
| Stop | **turn 8 player phase, frame 193094, 16 of 16 alive, nobody acted**, Garon 78/78 at (14,11), the throne General (13,11) still in the door. Chain ch is kept there |
| Lost | none kept. Undone in the look-ahead: Felicia (turn 5, Maid), Scarlet (turn 7, Hero counter after a 5-damage hit), **Corrin** (turn 7, the Berserker doubles him: Spd 24 vs 19, 20 a hit on Dragonstone Def 25, 28 HP) after a turn-7 General kill (Reina, then Ryoma unpaired by **Transfer** + Corrin's dual) |

What was learned [high]:
- **Dual strikes do half damage.** Every forecast shows the partner's number halved: Corrin's Dragonstone+ on the
  General +12 (39 vs Res 15 = 24), Corrin's Yato on the General +5 (40 vs Def 28 = 12), Scarlet's Killer Axe +7 on the
  General and +10 on the Hero (41 vs Def 20 = 21). So **Corrin's Yato dual on Garon is about 7, not 15**, and it hits
  about 58% (Corrin Hit 119 with the Yato, Garon Avo 61). Shura's Spy's Yumi does 1 at 61%. A Shura + Corrin shot is
  about 5 expected; two a turn (song) about 10. Garon's 78 does not fit in the turns Garon stays on a near tile. The
  "about 82 of 78" sum in 3w-2 used the full 15 and is wrong. [medium] That the game halves the partner hit was read
  from forecasts only, not from code.
- Ryoma is the only real damage: Raijinto Hit 141 (80% on Garon), 9-10 a hit through Dragonskin, doubles (Spd 34-37
  vs 27), but takes one breath (about 36) per attack, so at most one attack per heal, and he must be sung away before
  the enemy phase. Corrin's own Yato attack (15, no double) takes a breath of about 48 (Res 8 with the Yato).
- **Transfer** (lead's command) hands the support to an adjacent unit and **does not end the lead's action**: Ryoma
  transferred Felicia, then attacked unpaired with Corrin's dual. Switch also does not end the action (the new lead
  keeps the menu, but the move is already spent).
- Equip from Items (Items, pick, Equip, B) keeps the command menu open; Corrin can move, equip the Yato and Wait.
  With the Yato: Def 15, Res 8, Spd 24.
- Ryoma (paired with Felicia) is a safe bait for Berserkers and Brave Heroes (0% / 15% hit on him; 35-38 x2 back).
- The convoy is reachable next to Corrin (Convoy command): 28 items; L/R did not change its tabs (not read further).
- Turn starts in the kept line: 171904 (turn 6), 182294 (turn 7), 193094 (turn 8).

Plan notes for the next try [medium, not tested]: the boss needs Ryoma's attacks, not dual strikes. From ch (turn 8,
Garon (14,11) until the turn-8 enemy phase, then (14,9)): kill the General first (Reina from (13,13) with a dual,
Ryoma from (12,12) at range 2: both tiles are 3 from Garon); then each turn heal Ryoma to 37+, Ryoma attacks Garon from
range 2 with an unpaired neighbour, Azura sings him out of breath range. That is about 15-20 a turn: 4-5 turns, which
does not fit one 100-minute cap at about 10 minutes a turn. Keep Corrin out of every Berserker's reach (it doubles him).

Look-ahead check: `chk2.py` replayed the export (27315 input entries; ce's 21456 checked equal as a prefix) from frame 0
of bt-ch26-clear on boot-server: 158338 [16, 17, 0] instructions 709534111968 (equal to ce); 171904 [16, 16, 0];
182294 [16, 16, 0]; 193094 [16, 16, 0], instructions 865280474784, equal to chain ch's own state. Export:
build/speed/btend/ch-export.json; log: build/speed/btend/chkh.log.

Wall time, Endgame (04:05:29 start to the exported press list at 04:51:58): **47 min** of play, not cleared (stopped
early: the halved dual strike makes the strike plan not fit the cap); the replay check took another 10 min (to 05:01:57).

### 3y. Round 19: Birthright Endgame finished on the cheat track (`cheat-bt-endgame`, F-030) [high unless tagged]

The owner, 2026-11-17: "just cheat and count it, the purpose of the tests is to make sure it RUNS". Fresh helper, cap
60 min. Chain `cx` = a copy of ch (chain.json, inputs.txt, state.bin, last.json, _tools; new empty hist); ce, cf, cg, ch,
ch-t*start and c27 not changed (ch state.bin sha256 fc78f061... before and after the copy). The route is a cheat route
(`"cheat": true`) and is listed in the cheat tables (F-019 rule 2), but for the plan it counts as Birthright played to
the end (F-030). The real-play key `bt-endgame` stays unwritten.

**The poke (one, nothing else was needed).** At frame 193094 (turn 8, player phase, 16 of 16 alive): Garon's current
HP, path `unit:31232 +0xF3`, size 1, 78 -> 1, expect 78. Garon is person 31232, the only unit with that id (enemy
force, lv 40, (14,11)); Unit.csv has no current-HP field, so the path adds +0xF3 (the byte the forecasts and danger.py
read). In the look-ahead the poke was made by scratch `build/speed/btend/tools/poke.py`: boot-server loads the chain's
state.bin, the markers.json dump ranges are read by peek into a markers.Memory, and `cheats.apply` patches the state
(the same path rules, expect check and page check as a route stage: "linear heap (page checked)", 0x3262AE03, FCRAM
+0x0262AE03). The route run did the same at its stage boundary; its run.json has the same address and old/new values.

**How it ran.** Ryoma (paired with Felicia) from (12,17) to (13,12), Attack, RIGHT to the second target (the first is
the General at (13,11)); forecast Garon 1/78, Ryoma 13 x2 at 80%, Garon 35 at 36%. Ryoma's first hit kills Garon. No
unit was lost and nothing was undone. Then only A presses on talk (fastlook's answer table, START on two movie
screens at 208152/208182), one A on 'The End' and the logbook card entry. Screens met (markers, read every 120 frames
on boot-server, then checked as checkpoints on the original boot.exe):

| Frame | Screen |
|---|---|
| 193094 | turn 8 player phase, units [16, 16, 0] (the poke frame; read before the poke) |
| 193814 | the fight (ProcBattleInfo, BattleSeq) |
| 195014 | Garon beaten: units [16, 15, 0], ProcResDelayBind. Endgame shows **no separate stage-complete banner**: the map hands straight over to the ending events |
| 195134 | the ending events (event ProcEvent, CutSceneMain): Ryoma's coronation and the closing talk, answered with A |
| 208214 | chapter records (turns and heroes per chapter; ProcSequence@00626B48) |
| 230054 | epilogue cards with the staff credits (ProcEpilogue@0062695C), then ProcSequence@00626A70 at 264014 |
| 270614 | **'The End'** (ProcEffect, ProcSequence@006269E8). It waits for a key: it sat there 19,000 frames until A (289818). Not a hang: the screen is a wait for input |
| 289934 | the logbook card entry: pick up to 5 units ("You can select 5 more"); A on OK |
| 290534 | "Would you like to proceed?" (cursor starts on No): LEFT, A |
| 291326 on | **the title screen, "PRESS ANY BUTTON"** (ProcEffect, ProcSequence@00640B64), the first stable screen; unchanged to 291636 |

**Where the game lands:** the title screen. No save prompt was shown, and no file was written: after a server replay
from the poke frame to 291636, the savedata files are byte for byte those of bt-ch26-clear and there is no extdata
folder. **No hang or crash**: every screen advanced (the only long still screen is 'The End', which waits for a key).

**The route.** `cheat-bt-endgame` in config/harness/routes.json: save bt-ch26-clear, frames 291636, save_at 291630,
3140 presses (ch's presses checked equal as a prefix + the turn-8 attack and the ending's presses), the one poke, 10
shots = the 10 checkpoints in markers.json, verified false; the run timeout is parallel.py's frame-scaled default.
Written by a checked read-modify-write of only this key (scratch `tools/wroute.py`: every other key equal, re-read
just before writing, the files' own style; splitcfg.py does not write cheat-* keys). `cheats.py --check`: 5 cheat
routes, rules OK; `cheats.py --selftest` 23/23.

**Replay check:** `parallel.py runs --route cheat-bt-endgame --markers` (FEF_ROBOT_JOBS=4, 2.64 GB, below normal)
from frame 0: PASS, exit 0, Completed after 291636 frames, **checkpoints all met**, memory 95f8384c0bf16d25..., boot
938 s (stage 0 to the poke frame 728 s, stage 1 209 s), peak 781 MB; %APPDATA% unchanged. Run
build/parallel/runs-20261117-151424. [medium] Stage 0's instruction count at 193094 (865284955920) is not chain ch's
865280474784: ch's state carries look-ahead breaks (saves and shots); the checkpoint at 193094 is met with the same
units. The two-copy proof is a separate step.

Wall time (15:03:27 start to the replay-checked route at 15:30:05): **27 min**, of a 60-minute cap.

### 3z-cq13. Round 20: Conquest chapter 13 (`cq-ch13`) taken from the paused chain [high unless tagged]

F-031 (Conquest resumes, real play). The paused round-11/12 look-ahead chain `c13` (build/speed/cq13, left untouched)
had already played chapter 13 'Uprising' (rout) from frame 0 of `cq-ch12-clear` to My Castle (frame 272868, 8644
presses, `cheat: false`; its breaks are only state.bin loads and screenshots, no pokes); routes.json `cq-ch13` held its
press list but markers.json had no checkpoints. This helper worked on a copy (build/speed/cq13b) and played nothing new.

- **Replay check:** `build/speed/cq13b/tools/chk3.py` (chk2.py plus the full marker state) replayed the export from frame 0
  on boot-server (clean line): the instruction count at 272868 is **1222758618048, equal to chain.json's own**; the export
  is equal to routes.json `cq-ch13` input.
- **Nobody lost** (casual save, so a fallen unit would leave the map): player units 10 from turn 1, 12 from turn 3 (Benny,
  Charlotte join), 12 at every sample every 10,000 frames and at stage complete; enemies 22 -> 0 (6 reinforcements came).
- **Checkpoints** (markers.json `cq-ch13`, splitcfg.py `marks`): 14142 preparations, gold 3500 [10, 22, 0]; 15504 turn 1
  [10, 22, 0]; 101706 [12, 11, 0]; 151754 [12, 9, 0]; 223630 [12, 3, 0]; **269348 stage complete**
  (`map__SequenceCompleteEffect`) [12, 0, 0]; 271132 the save slot menu (chapter now B014); **272800 `castle__Sequence`**.
  Route frames 272900, save_at 272890, slot 1. Not the Endgame (castle after it).
- routes.json `cq-ch13` stays `verified: false` (about text extended); the two-copy proof is a separate step.

Wall time (15:21 start to the replay-checked export and written checkpoints, ~15:39): **~18 min** of a 100-minute cap
(no play needed).

### 3z-cq14. Round 20: Conquest chapter 14 (`cq-ch14`), real play [high unless tagged]

F-031, fresh helper, cap 100 min of play. Chain `c14` (`--dir build/speed/cq14`, `new c14 --save cq-ch13-clear`,
frame 0, `cheat: false`, no pokes, no cheat save; the breaks are only state.bin loads and screenshots). Tools: the
rv19 set copied to build/speed/cq14/tools (act2.py, danger.py with `MAPFILE` B014.bin.lz, gz.py, dz.py, near.py,
bl.py, st.py) plus `tmap.py` (terrain letters) and `dist.py` (walking distance map). A fresh board before every threat
read (danger.py re-reads state.bin by its sha256); every enemy weapon kind with its own range (3w).

| | Chapter 14 'Voice of Paradise' (`cq-ch14`) |
|---|---|
| Win rule | defeat the boss (Oni Chieftain Kumagera, 36 HP, steel mace 1-2, stays on his platform at (23,6) between two archers) |
| Map | 26 x 21, rooms joined by bridges over the void; low walls (TID_低壁) only fliers cross |
| Start | 12 deployed (as the save had them), 25 enemies, Keaton green at (13,20); a sky-knight + Kinshi-knight pair comes in at (1,10) later |
| Turns, end | about 13; stage complete at 111502, saved slot 1, castle at 117050 |
| Lost | none (12 of 12 at stage complete); Keaton alive |

Played [high, seen in the chain]: Camilla (steel axe) and Leo (Brynhildr) kill the samurai and sky knights that come
from the centre; Benny and Harold finish a sky-knight pair; the two archers that chase Keaton die to Leo and Camilla;
the army walks the south rooms east; Leo baits the oni at (17,18) and his counters kill the three oni and both east
archers; a shrine maiden's Freeze holds Camilla one turn and Harold one turn (move range only around the unit: read
as "frozen", not a tool fault). Nyx paired under Silas and Odin under Niles so the Kinshi knight (Spd 17) can not
double them. Last turn: Leo from (23,8) (boss 36 -> 13) and Camilla from (24,6) (one axe hit) beat the boss.

- **Auto end turn is on in this save** [high]: when the last unit acts the enemy phase starts by itself. An `act2 end`
  after that ends the next player phase with nobody moved (it happened twice here: harmless, two idle turns, but count
  the units before calling `end`). Camilla's equipped weapon was Thunder: Y on the forecast switches to the axe.
- **Export and replay check:** `fastlook export` -> build/speed/cq14/c14-export.json, 2,042 presses, frames in order,
  no duplicates, last press 116888. `tools/chk3.py` (cq13b's, plus budget.enter for below normal) replayed it from
  frame 0 of `cq-ch13-clear` on boot-server: every checkpoint gave the recorded screen, and at 117050 the instruction
  count is **524516968800, equal to c14/chain.json's**.
- **Route key** routes.json `cq-ch14` (splitcfg checked merge): frames 117100, save_at 117090, `verified: false`, input
  equal to the export. **Checkpoints** markers.json `cq-ch14`: 7666 preparations, gold 3500 [12, 25, 1]; 9308 turn 1
  [12, 25, 1]; 26320 [12, 22, 1]; 52276 [12, 17, 1]; 82894 [12, 13, 1]; 100978 [12, 10, 1] paired 2; 108438 [12, 10, 1];
  **111502 stage complete** [12, 9, 1]; 116624 the save slot menu (chapter now B015); **117050 `castle__Sequence`**.
  Not the Endgame (castle after it). The two-copy proof, pack and capture are a separate step.

Wall time: start (epoch 1794952180) to the exported press list (1794954393) **37 min**; replay check read at 41 min.
No cap hit.

### 3z-cq15. Round 20: Conquest chapter 15 (`cq-ch15`), real play [high unless tagged]

F-031, fresh helper, cap 100 min of play. Chain `c15` (`--dir build/speed/cq15`, `new c15 --save cq-ch14-clear`,
frame 0, `cheat: false`, no pokes, no cheat save; breaks are only screenshots, serve slots and state.bin loads). Tools:
cq14's set copied to build/speed/cq15/tools (`MAPFILE` B015.bin.lz), plus `fm.py` (whole map with units), `opt.py`
(every tile one unit can reach, with who can hit it there) and `trk.py` (TrickData nodes: type, x, y, w, h). A fresh
board before every threat read; every enemy weapon kind with its own range (3w). The battle ran one call per action
(no `serve`: the danger tools read state.bin).

| | Chapter 15 'The Black Pillar' (`cq-ch15`) |
|---|---|
| Win rule | defeat the boss or all units escape, 20 turns |
| Map | 30 x 30 ruins over the void; the boss (Brave Hero, (3,22)) and 14 enemies are in the south part, which the north part does not reach on foot. **Escape tiles** (TrickData type 5): x 30, y 5, 6, 7, 11, 12, 13, 14. One dragon vein (type 11) at (8,7), not used |
| Start | only Corrin (lv 17), Azura (lv 1, 16 HP) and Gunter (lv 10) (preparations: "You can select 0 more"); 25 enemies: villagers (naginata), ninjas (shuriken 1-2), axe fighters, lancers |
| Turns, end | 12; stage complete at 69750, saved slot 1, Lilith's talk, castle at 78366 |
| Lost | none: all three escaped; at the castle the roster is 20 -> 21 people, Corrin 19, Gunter 11 |

Played [high, seen in the chain]: Gunter (Def high, steel lance) and Corrin (dragonstone) bait the north enemies a
pair at a time and kill them on counters and the next turn (turns 1-8, 7 kills); Azura sings twice for Corrin from
tiles the threat read showed safe. Turn 8 Azura pairs up with Gunter, so nothing can attack her and she moves with
his 7. Corrin baits the axe fighter from (25,8) at (24,4) and kills it on turn 10. Turn 11 Gunter (Azura paired)
escapes on (30,5): **the pair leaves together** ("Escape" > "Leave the battlefield?" Yes; force 0 count 3 -> 1).
Turn 12 Corrin walks past the second axe fighter (8 HP, at (29,5)) to (30,6) and escapes; stage complete.

- **Tool findings** [high]: danger.py and opt.py do not check that **our** destination tile is walkable (they score
  any tile): a move to (18,4) (lake) did not open the command menu, the phase stopped and act2 undid it (no harm).
  Check the terrain (fm.py) before choosing a bait tile. The ending event runs under `castle__anonymous_namespace__Seq`
  for about 20,000 frames before `map__SequenceCompleteEffect`; an `until` for the complete effect needs a longer max.
  The castle opens with Lilith's talk (TalkKeyWait): `psave`'s `until castle__Sequence` needs `answer: true` here.
- **Export and replay check:** `fastlook export` -> build/speed/cq15/c15-export.json, 814 presses, frames in order,
  no duplicates, last press 78310. `tools/chk3.py` replayed it from frame 0 of `cq-ch14-clear` on boot-server (below
  normal): every checkpoint gave the recorded screen, and at 78366 the instruction count is **351168703776, equal to
  c15/chain.json's**.
- **Route key** routes.json `cq-ch15` (splitcfg checked merge): frames 78420, save_at 78410, `verified: false`, input
  equal to the export. **Checkpoints** markers.json `cq-ch15`: 10426 preparations, gold 3500 [3, 25, 0]; 11040 turn 1
  [3, 25, 0]; 20560 [3, 23, 0]; 31686 [3, 20, 0]; 40398 [3, 18, 0]; 47394 [1, 17, 0] (Gunter + Azura escaped);
  48988 [1, 17, 0]; **69750 stage complete** [0, 17, 0]; 77400 the save slot menu (chapter now B016); **78366
  `castle__Sequence`**. Not the Endgame (castle after it). The two-copy proof, pack and capture are a separate step.

Wall time: start (epoch 1794955633) to the exported press list (1794956986) **23 min**; replay check read at 27 min.
No cap hit.

### 3z-cq16. Round 24: Conquest chapter 16 (`cq-ch16`), real play [high unless tagged]

F-031, fresh helper, cap 100 min of play. Chain `c16` (`--dir build/speed/cq16`, `new c16 --save cq-ch15-clear`,
frame 0, `cheat: false`, no pokes, no cheat save; breaks are only screenshots and state.bin loads). Tools: cq15's set
copied to build/speed/cq16/tools (`MAPFILE` B016.bin.lz) plus `g.sh` (confirm a forecast and settle). A fresh board
before every threat read; every enemy weapon kind with its own range (3w).

| | Chapter 16 'Invasion' (`cq-ch16`) |
|---|---|
| Win rule | defeat the boss. The boss is hidden: "Speak with the green lancers and try to unmask the enemy commander" (gold is stolen each turn until then; not a loss rule). The **fourth** suspect talked to becomes Shura (script B016.cmb: three innocent talks, then `UnitRecreate` of PID_B016_ボス) |
| Map | ship deck (Btl_ShipDeck_TypeA), 30 x 19; low walls (TID_低壁) are "Partition, Impassable" even for Camilla; the centre (x 14-20) joins the west by the top and bottom corridors and the east by rows 10-12; the east edge strip x 27-29 is reached only from the south (rows 15-16) |
| Start | 12 deployed + Xander (guest, Paladin, Siegfried 1-2); 25 enemies; 4 green suspects at (3,7), (7,17), (23,5), (29,10) |
| Turns, end | 21; stage complete at 162242, saved slot 1, castle at 168550 |
| Lost | none (13 of 13 at stage complete) |

Played [high, seen in the chain]: the movers (two mages, two axe fighters, two mercenaries) are killed as they come
(turns 1-4; Xander with Effie paired under him takes the two mercenaries alone at (17,11)); the west is cleared
(turns 5-8) and suspects 2 (Corrin, turn 6) and 1 (Xander, turn 9) are talked to; a thief pair that reached the
centre dies on turn 10 (Camilla, Harold, Niles twice: Azura sang for him); the east is cleared turns 13-18 (suspect 3
by Xander on turn 14, who then kills the mercenary at range 2); on turn 21 Xander talks to suspect 4 at (29,10):
Shura (Adventurer, 38 HP, mini bow + killer bow) appears; Siegfried takes him to 6 (his counter did 0), Gunter's
javelin misses, Harold's hand axe from (29,12) finishes him.

- **One try undone** [high]: turn 13 Gunter alone at (18,13) (threat read: mercenary, two thieves, adventurer) was
  killed in the enemy phase; the look-ahead went back two snapshots (before his move) and the turn was played again
  without that bait. The kept chain never lost a unit.
- **Tool findings** [high]: `danger.py`/`opt.py` reach is wrong here both ways: storm floor (TID_床／嵐) slows mounted
  units in the game (Xander, Silas, Harold reached far fewer tiles than opt listed: check the move with `show` first),
  and the thief pair at (24,10) reached (19,9) and shot Harold although trig had not listed it. Freeze (adventurer's
  staff) held Xander one turn (no blue tiles). After some enemy phases the end plan left Corrin **selected** (his
  move range up, screen still SequenceHuman): the next `act2` moved his path arrow instead of the cursor; a `B` after
  each `end` fixed it. Talk does not use the action: the menu comes back (Attack if an enemy is in range, then Items
  ... Wait). Swords beat axes and lances beat swords in Fates (Harold's axes are poor against mercenaries).
- **Export and replay check:** `fastlook export` -> build/speed/cq16/c16-export.json, 3,108 presses, frames in order,
  no duplicates, last press 168388. `tools/chk3.py` replayed it from frame 0 of `cq-ch15-clear` on boot-server (below
  normal): every checkpoint gave the recorded screen, and at 168550 the instruction count is **755295472800, equal to
  c16/chain.json's**.
- **Route key** routes.json `cq-ch16` (splitcfg checked merge): frames 168600, save_at 168590, `verified: false`,
  input equal to the export. **Checkpoints** markers.json `cq-ch16` [players, enemies, others]: 13140 preparations,
  gold 3500 [13, 25, 4]; 14232 turn 1 [13, 25, 4]; 29898 [13, 21, 4]; 53622 [13, 16, 4]; 87434 [13, 10, 4]; 110654
  [13, 7, 4]; 134472 [13, 2, 4]; 157652 [13, 0, 4]; **162242 stage complete** [13, 0, 3]; 168124 the save slot menu
  (chapter now B017); **168550 `castle__Sequence`**. Not the Endgame (castle after it). The two-copy proof, pack and
  capture are a separate step. [medium] Whether Shura joined (the post-battle choice was answered by the plan's talk
  answering, default choice) was not checked.

Wall time: start (epoch 1794964390) to the exported press list (1794969352) **82 min**; replay check read at ~93 min.
No cap hit (100 min).

### 3z-cq17. Round 24: Conquest chapter 17 (`cq-ch17`), real play, NOT cleared [high unless tagged]

F-031, fresh helper, cap 100 min of play. Chain `c17` (`--dir build/speed/cq17`, `new c17 --save cq-ch16-clear`,
frame 0, `cheat: false`, no pokes, no cheat save). Tools: cq16's set copied to build/speed/cq17/tools (`MAPFILE`
B017.bin.lz). Shura joined in chapter 16 (he is on the chapter 17 roster).

| | Chapter 17 'Den of Betrayal' (`cq-ch17`) |
|---|---|
| Win rule | defeat the boss (Kotaro, Master Ninja, Flame Shuriken 1-2 magic, on the throne at (21,3)) |
| Map | cave maze 25 x 22, mostly walls (TID_壁), caltrops (TID_撒菱／床, cost 2 on foot, 3 for horses, 1 for fliers); the start room (1-8, 16-22) leaves only north by the corridor (3,15)-(3,17) and (4,14); the caltrop room east of the start (8-12, 19-21) is a dead end |
| Start | 14 deployed, Saizo green (gone by turn 8), 32 enemies (ninjas, master ninjas, mechanists, automatons, samurai, swordmasters, a shrine maiden); the cq-ch16-clear save boots straight into the castle preparations menu (B, then START > Next Battle > Chapter 17 > LEFT A) |
| Reinforcements | turn 10 (NW corner and south), turn 12 (NW and south), turn 15/16 (north and east) |
| Reached | turn 19 player phase, frame **144711**, nobody lost; Kotaro 16/38; Camilla (1 HP) leads a pair with Xander (38) at (21,4) next to the throne |

Played [high, seen in the chain]: Gunter, Xander and Camilla hold the (4,14) choke while the first waves die
(turns 2-7); the samurai group and the maiden die on turns 8-10; Xander and Camilla go east and north (turns 11-15),
Corrin corks the start corridor at (3,17) against the NW reinforcements (Felicia heals him twice, Azura sings once);
turn 18 Camilla (Xander paired under her) hits Kotaro 38 -> 9 from (21,4), but on the enemy phase he heals on the
throne to 16 and takes Camilla to 1 HP.

- **Why it stopped** [high]: on turn 19 every try to finish Kotaro failed in the look-ahead and was undone (7 tries):
  Camilla attacking at 1 HP dies first every time (3 tries; Kotaro strikes first, [medium] probably Vantage below half
  HP); Xander as lead (Switch is free and is undone by B until an action is taken) shows 53% hit and missed 4 times
  from (21,4), (21,5) and (20,4), also after other battles were fought first to move the random numbers. Each miss
  leaves Xander at 8 HP next to Kotaro and two master ninjas, so no try was kept. [medium] The forecast shows an
  enemy "Attack!" supporter beside Kotaro; whether that changes the result was not found.
- **Tool findings** [high]: `danger.py`/`opt.py` reach is too generous on caltrops and for pairs (Xander pair "could
  reach" (21,4), the game refused). After a B-B cancel out of an attack forecast the unit stays **selected**
  (move range up) while the screen still reads SequenceHuman: the next `act2` moves the path arrow instead of the
  cursor; one more B fixes it. `act2 ... X,Y X,Y show` (act in place) needs `MW=160`. A unit with an enemy in range
  has Attack first in its menu: `A W30 A` meant for Staff starts an attack (one such attack was undone).
- **Export** [high]: `fastlook export` -> build/speed/cq17/c17-t19-export.json, 1,804 presses, last press 144659,
  chain frame 144711 (instructions 648469671696). Not replay-checked; **no route key and no checkpoints written**
  (the chapter is not played to the castle). Next: a later helper continues chain c17 from frame 144711 (or replays
  the export from frame 0 of cq-ch16-clear). Ideas: pull the pair back out of Kotaro's reach and heal Camilla (Elise
  is at (11,13) with 5 HP, Felicia at (4,19)), bring Shura (killer bow) or Corrin north, then attack Kotaro while he
  is above half HP.

Wall time: start (epoch 1794971481) to the exported press list (1794976154) **78 min**; cap (100 min of play)
not reached, stopped on the failed boss tries.


#### 3z-cq17b. Round 24 continuation helper (session `c17b`), turn 19 boss tries, NOT cleared [high unless tagged]

Cap 60 min. Copy of chain c17 at build/speed/cq17/c17b (frame 144711, inputs.txt byte-equal to c17's); every try
below was undone with `act2.py undo`, so c17b ends equal to c17 again. g.sh now takes `CH` (`phase ${CH:-c17}`).

- **Xander as lead never damages Kotaro on turn 19** [high, 3 more tries, 7 in all]: forecast Xander Atk 20, Hit
  53%, Crit 2% (Kotaro 16 HP, skull = lethal); Kotaro Atk 15 x2, Hit 100%. Every battle ends the same: Xander 38 -> 8,
  Kotaro 16/38, the same frame count (about 1,050 frames). With a different start (Gunter first kills the mechanist
  (13,14) with the javelin in place; or Gunter, then Harold attacks the automaton (14,13) from (13,13)), Xander's
  result does not change. Battle pictures (frames 148163-148403): Kotaro hits 15, a "NO DAMAGE!!" pop, Kotaro hits 15.
  [medium] So the outcome on this turn looks fixed, not a 53% roll; why is not known.
- **Camilla with the Steel Axe** [high]: forecast (Y on the forecast toggles Thunder / Steel Axe) Camilla Hit 57%
  (Thunder 47%), Kotaro Hit 81% (Thunder 96%); one axe try: Camilla missed and died (undone).
- **Kotaro has no Vantage** [high, build/tables/PersonChapter.csv row PID_B017_ボス]: skills SEID_鍵開け (Locktouch),
  SEID_四牙 (Skill.csv 103, effect Skl_戦闘後ダメージ, damage after battle), SEID_見下す者 (63), SEID_清流の一撃 (57);
  not SEID_待ち伏せ (39, Vantage). Items in DisposUnit B017 #14: Silver Shuriken + Flame Shuriken. The game state is
  difficulty 0 (Normal), casual. [medium] "Kotaro strikes first" in 3z-cq17 was probably Camilla missing first.
- **Next try** [medium]: do not repeat turn-19 attacks on Kotaro; they look fixed. Either pass turn 19 safely (Gunter's
  in-place javelin kill of the mechanist is safe: no damage, Lv 15; Elise to (11,15) can heal Gunter) and try on turn
  20, or bring a second attacker so one battle does not have to kill. On turn 18 Camilla did hit him (38 -> 9).
- **Replay check of c17-t19-export.json: PASS** [high]: `tools/chk3.py c17-t19-export.json chk19 60000 144711`
  (boot-server, below normal, from frame 0 of cq-ch16-clear): at 144711 the screen is SequenceHuman and the
  instruction count is **648469671696, equal to c17/chain.json's**. A later helper can start from this export.

Wall time: start (epoch 1794976239) to the stop and replay check (~1794977400) about **20 min** of the 60-min cap;
stopped early because the turn-19 boss battles look fixed and a safe multi-turn plan (heal Camilla, bring a second
attacker north) does not fit the cap. No new export (the chain did not move).

#### 3z-cq17c. Round 29: Conquest chapter 17 finished on the cheat track (`cheat-cq-ch17`, F-033) [high unless tagged]

Owner, 2026-11-18 ~01:15: "just maximize movement options for conquest to make sure the combat and animations etc
work". Fresh helper, cap 100 min of play. Chain `build/speed/cqx17/c` = a copy of c17 (chain.json, inputs.txt,
state.bin, last.json; state.bin sha256 d5e900b0... equal to c17's, inputs.txt byte-equal); c17 and c17b not changed.
Tools: cq17's set copied to cqx17/tools; danger.py there reads the move bonus as the s8 at Unit+0x12C **uncapped**.

- **The field** [high, asm/text/text_0051F350.s]: Unit::GetMovePower 0x0052D5E4 = Job mov (Job+0x5D, through
  Unit+0xA0) + the s8 at Unit+0x12C (0x0052D6B8, skipped while state bit 30 is set) - max(0, s8 at Unit+0x12D) + the
  skill/pair terms. No cap of 2 there (the old danger.py `min(.., 2)` was a guess). The script command
  UnitSetMovePower 0x003AB6D8 writes the same byte.
- **The pokes** (movement only; tools/poke.py = btend's, via cheats.apply): frame 144711 (turn 19 player phase, c17's
  end) all 14 units `unit:N +0x12C` 0 -> 20 (expect 0); frame 164473 (turn 22 player phase) 20 -> 60 (expect 20),
  because samurai kept plugging the maze and Gunter/Elise needed 27-31 move. Checked in the look-ahead: the pair moved
  (23,10) -> (21,4) (paladin cost 12 > base 8), Elise moved 31, Shura (3,17) -> (20,4) in one move.
- **How it was won** (turns 19-23, nobody lost): Xander never hits Kotaro (10 tries on turns 19, 20 and 22, every one
  undone; his hit shows 51-61%, the battle pictures show a real MISS each time). Kotaro heals 7 a turn on the throne
  and two units must hit in one phase. Turn 19: the pair switched to Xander lead and left for (23,10); Gunter's javelin
  killed the mechanist (13,14). Turn 20: the pair went into a closed pocket at (16,6) and **Separated** (Camilla to
  (17,6); Separate ends both units' turn); Gunter (Harold dual) killed an automaton; Elise healed Gunter, Felicia
  Corrin. Turn 21: Xander (Camilla dual) killed the swordmaster (15,8) that closed the pocket; Harold the 2nd automaton.
  Turn 22 (after the 2nd poke): Gunter + Harold killed the samurai (15,14); Elise (move 31) healed Camilla; Corrin +
  Shura killed the start-room mechanist. Turn 23: Gunter (Harold dual) killed the samurai that came back to (15,14),
  Elise healed Camilla to 32, Xander waited at (22,4), Camilla (21,4, Steel Axe, Xander's dual) hit Kotaro 38 -> 21,
  Shura (20,4, killer bow, Camilla's dual, 76%) killed him. Stage complete 183159, the STAGE COMPLETE banner waits for
  A (186169), save slot 1 (A, LEFT, A), castle 188537. The next chapter is B018 (not the Endgame).
- **Tool findings** [high]: a long move (20+ tiles) needs act2 `MW=240..400` (else the stop sees ProcMoveRoute);
  at a tile with no enemy in range the command menu has no Attack (Separate is 3 DOWNs, not 4); act2 keeps only 4
  undo snapshots (KEEP), so undo past them is not possible.
- **The route** `cheat-cq-ch17` (routes.json, markers.json; one checked read-modify-write of only this key,
  build/speed/cqx17/tools/wroute.py): save cq-ch16-clear, frames 188600, save_at 188590, 2,440 presses (c17's 1,804 a
  prefix), the 28 pokes, 11 checkpoints (two read before the pokes), verified false. `cheats.py --check` 6 cheat
  routes, rules OK; `--selftest` 23/23. The clear save `cheat-cq-ch17-clear` is not packed yet.
- **Replay checks** [high]: boot-server from frame 0 with the pokes applied between steps (tools/chk4.py): the same
  screens; then `parallel.py runs --route cheat-cq-ch17 --markers` (FEF_ROBOT_JOBS=4, 2.64 GB, below normal): PASS,
  exit 0, Completed after 188600 frames, **checkpoints all met**, memory e02b945e..., instructions 845142249600 (equal to
  the boot-server replay's at 188600), boot 643 s, peak 780 MB, %APPDATA% unchanged; build/parallel/runs-20261118-020807.
  The two-copy proof was not run (a separate step).
- **Proof** [high, round 29 proof step]: `parallel.py runs --route cheat-cq-ch17 --copies 2 --markers --keep`
  (session r29-proof-cheat-cq-ch17): both copies exit 0, memory e02b945e..., instructions 845142249600 both,
  checkpoints all met (all 11 checkpoint frames were already in the shot list). `cheat-cq-ch17-clear.zip` packed from
  copy 1 (carries harness-cheat.json). Capture r29-cap-cheat-cq-ch17 (current library, not rebuilt): 197 functions,
  11,340 records, 11,167 match, 121 gave up, 52 incomplete, **0 bad**, no writer stored. Route set verified true;
  `cheats.py --check` 6 cheat routes, rules OK.

Wall time: 01:09 start to the exported press list 01:50: **41 min of play** (cap 100); replay checks and the route
to 02:20.

#### 3z-cq18. Round 29: Conquest chapter 18 on the cheat track (`cheat-cq-ch18`), NOT cleared [high unless tagged]

Fresh helper, F-033, cap 100 min of play. Chains in build/speed/cqx18 (`new c --save cheat-cq-ch17-clear --cheat`;
tools = cqx17's set, `MAPFILE` B018.bin.lz, cheat=True in the server tools, `tools/rewind.py SRC DST F` = copy a chain
cut at frame F and rebuild it on the clean line). No route key, no checkpoints, no clear save written.

| | Chapter 18 'Black & White' (B018) |
|---|---|
| Win rule | defeat all bosses within 20 turns: Zola (Sorcerer, 37 HP, Nosferatu/Fimbulvetr, throne (13,1)) and a paired General boss at (13,20) (43 + 43 HP, steel javelin / throwing axe) |
| Map | Izumo palace (Btl_CastleIzumo_Indoor); the throne room (11-15, 1-3) opens only by (13,4); doors (6,2), (20,2) shut; our start in two walled yards (1-6, 5-10) and (20-26, 5-10); 4 green Hoshidan royals in the centre room |
| Start | 14 deployed, 27 enemies; the opening presses are the first 23 of the export (castle > Next Battle > yes > Fight > yes; the 'Victory' rule card waits for A) |

- **No new poke** [high]: the move bonus `Unit+0x12C` = 60 on all 14 units came **in the save** (cheat-cq-ch17-clear,
  F-033 poke of round 29); Corrin moved (2,7) -> (12,1) in one move. So this chapter is a cheat route by its start save
  only.
- **Enemies sleep** [high]: with nobody in reach the enemy phase moves nobody (chain d, turn 1 ended untouched). They
  wake when one of ours is in their move + range; `danger.py`/`dz.py` count through walls and over-count here.
- **Reached** [high]: chain f (= d/e cut at **37060**, turn 2 player phase), all 14 alive: Zola, both throne pairs
  (sorcerers, heroes) killed on turn 1 (Xander (11,1), Corrin Yato (12,1) with Xander's dual, Gunter javelin (12,2) with
  Corrin's dual kills Zola; Camilla (14,1) axe and Shura (15,1) bow kill the sorcerer pair; Azura sings Camilla, Camilla
  (13,3), Harold (11,2), Odin (13,2) kill the hero lead; Effie pairs onto Harold; Elise heals Corrin from the throne).
  The hero support (11,3) 30 HP and a hero (13,4) 10 HP woke and came in; 5 sorcerers, 3 heroes and a maid are awake
  outside, the generals boss untouched.
- **Why it stopped** [high]: on turn 2 the only way out of the throne room is (13,4)/(13,5), held by the awake
  sorcerers. A blocker at (13,3) gets two attackers ((13,4) and (13,5)); every try lost units and was undone: Camilla
  (31 HP) at (13,3) died and the room flooded (Camilla, Azura, Odin lost); Corrin with the Dragonstone (40 HP, Def+4
  Res+3) at (13,3) died too. The generals boss takes 3-5 from Odin, Nyx and Camilla's Thunder (forecasts, 100% javelin
  counters), so it needs a plan of its own. At about 10 min a turn the 20-turn map does not fit the cap.
- **Tool findings** [high]: Shelter (take an adjacent ally into one's pair) shows for Gunter, not for Effie or Azura;
  menu Pair Up joins the **acted** unit as support; moving onto an acted ally is refused. A bow cannot dual-strike an
  adjacent target. Forecast Y toggles the weapon only if both reach.
- **Export and replay check** [high]: `fastlook export f` -> build/speed/cqx18/f-t2-export.json, 479 presses, last
  37008, chain frame 37060; chain f was rebuilt from frame 0 of cheat-cq-ch17-clear on the clean line (fastlook clean,
  98 s) and gives the same board (14 of 14, same enemies and HP) as the look-ahead (instructions 166070900160).
  `cheats.py --selftest` 23/23, `--check` 6 cheat routes, rules OK. Next: a later helper continues from chain f (turn 2):
  kill (13,4)/(13,5) first from inside, or leave the room only once the sorcerer pack is thinned; then the generals.

Wall time: 02:48 start (epoch 1794988095) to the export (54 min); the cap (100) was not reached, stopped because the
rest of the map does not fit it at this pace.

#### 3z-cq18b. Round 29 continuation helper (chains g, h, i), turn 2 to turn 11, NOT cleared [high unless tagged]

Cap 60 min. g = a copy of f (frame 37060); h = g cut at 44876 (turn 3 start) and rebuilt (`rewind.py g h 44876`);
f, c, d, e not changed. No new poke (the move bonus 60 is still the one from the start save). No route key written.

- **How the throne room was held** [high]: the exit (13,4) is the only way in, so whoever stands on (13,3) can be hit
  from (13,4) and, at range 2, from (13,5) only. Turn 2: Odin (13,2) Thunder kills the hero (13,4) without moving;
  Gunter javelin + Xander Siegfried (range 2, from where they stand) kill the hero (11,3); Camilla (13 HP) uses menu
  **Pair Up** onto Odin (she is support, safe); Corrin to (13,3) and Elise menu Pair Up onto him (support). Each turn
  after: Gunter or Xander hits (13,4) from (12,3) at range 2, Corrin (Dragonstone, forecast Y) finishes it, **Azura
  sings the attacker** who then goes back to (12,1)/(11,1) (left on (12,3) Gunter died to the (13,4) sorcerer), Shura
  (Mend) heals Corrin from (13,2). Corrin must use the Dragonstone: with the Grim Yato he died (try g, turn 3 enemy
  phase: Corrin, Elise, Azura, Harold lost; chain g still ends there, do not use it; h was rebuilt before it). Moving onto an unmoved ally (Corrin) did nothing;
  menu Pair Up works.
- **Hall cleared** [high]: turn 7 Corrin to (13,4) + Xander (13,3) kill the last sorcerer at (13,5); Xander (15,3)
  hits the sorcerer (17,3) through the wall (range 2) and Niles from the east yard (17,5) kills it. Turn 8 Corrin kills
  a hero, Xander (14,10) + Shura (10,10) kill the hero (12,10) (Nyx there died to the paladin: undone); the maid (10,8)
  died attacking Shura. Turn 9 Xander kills the general (14,11), Shura (9,10) + Corrin (12,10) + Niles (10,9) + Silas
  (10,10) kill the paladin. Turn 10 Nyx (11,10) + Shura (13,10) kill the general (12,11); Felicia (Live) heals.
- **Reached** [high]: chain h at **108680 = turn 11 player phase, all 14 alive**. Left: the boss pair (13,20) 43+43,
  generals (4,18), (8,15), (8,16), paladins (17,20), (18,19), (18,24), (25,21), (25,22), bow knight (18,20),
  strategist (21,20). 10 turns left of the 20.
- **Boss forecast** (probe, undone) [high]: Xander from (12,20): Siegfried 9 damage, hit 94% (sword vs lance, "Poor
  weapon compatibility"); boss javelin 9 back, hit 89%, the support shown. Axes (Gunter steel axe, Camilla steel axe,
  Harold) have the triangle edge; the passage south is (12-14, 11-12), then x9 (rows 15-20) past the generals at x8.
- **Tool findings** [high]: `attack:N` picks the N-th target (Nyx at (10,10) hit the maid with plain `attack`); Sing
  and Pair Up ask for a target (screenshot, DOWN/RIGHT moves it); `KEEP=8` keeps more undo snapshots.
- **Export and replay check** [high]: `fastlook export h` -> build/speed/cqx18/h-t11-export.json, 1,107 presses, last
  108628, frame 108680; `rewind.py h i 108680` rebuilt it from frame 0 of cheat-cq-ch17-clear on the clean line
  (392 s): instructions **487009860480, equal to h's**, the same board (14 of 14, same enemies and HP).
  `cheats.py --selftest` 23/23, `--check` 6 cheat routes, rules OK. Next helper: continue from chain h or i (turn 11).

Wall time: 03:43 start to the replay check 04:24 (about 41 min of the 60-min cap); stopped with time left for the
export and the replay check, the boss needs a few more turns.

#### 3z-cq18c. Round 31 helper: Conquest chapter 18 finished on the cheat track (`cheat-cq-ch18`, F-033) [high unless tagged]

Fresh helper, cap 100 min of play. j = a copy of h (chain.json, inputs.txt, state.bin, last.json, board.json; state.bin
sha256 e8468ea9... equal to h's); h, i, g not changed. k = j cut at 149400 and rebuilt on the clean line
(`rewind.py j k 149400`, 787 s under load), then played to the castle. **No new poke**: the move bonus 60 came in
the start save, so the route is a cheat route by its start save only (`"pokes": []`).

- **Turn 11** (all from out of the boss's reach): Gunter (javelin, Nyx dual) + Shura's killer bow killed the paladin
  (18,19); Xander (18,19) killed the bow knight (100%, no counter); Corrin (17,19) + Harold (18,20) + Niles (18,21)
  killed the paladin (17,20). The boss pair never moves: it only hits units within 2 of (13,20).
- **Turn 12**: Corrin's menu has **Separate** (5 DOWNs) only when a tile next to him is free; Elise put on (17,20)
  (both units end). Shura Mend Corrin 23 -> 40, Felicia Live Gunter 21 -> 36, Azura sang Elise, Elise healed Xander to
  39 (Gunter moved off first to free a tile). Xander (12,21) hit the pair 43 -> 34; the boss countered him in the
  enemy phase (lead 27).
- **Turn 13**: Shura (11,21) Mend Xander; Xander (Shura partner) 27 -> 20. Corrin's first try was eaten by the
  **dual guard** (full gauge, the hit did nothing, Corrin took 21): undone; Gunter (12,20) attacked first (0 damage,
  takes 8) to use up the gauge, then Corrin (13,21) 20 -> 6; Azura (12,22) sang Xander, Xander killed the lead. The
  partner's dual strike added little or nothing against this general (half damage, or blocked).
  First end of turn lost **Elise** (healing Corrin from (14,21), in the boss's range) and **Nyx** (left at (17,17):
  reinforcements came in that enemy phase, a paladin at (17,16) and generals at (9,14), (9,15)): the undo snapshots
  did not reach back (KEEP=4), so chain k was rebuilt at 149400 (use KEEP=12). Second try: Elise healed Corrin from
  (13,22), then **Silas Shelter**ed her from (14,22) (out of reach), Nyx to the throne room, Niles (12,23) and
  Felicia (13,23) closed the alcove for Azura. All 14 alive (Felicia 3 HP, Gunter 14).
- **Turn 14**: Xander (sword vs the axe general) hit 34 -> 11 (forecast 23 damage, he took 7); Corrin (Dragonstone)
  killed him. Stage complete 163230, banner (Chapter 18, 14 turns, heroes Corrin & Elise) at 166260 waits for A, save
  menu 170422 (A, LEFT A), castle 170778. The next chapter is B019 (not the Endgame).
- **Tool findings** [high]: Harold could not move on turn 13 (the strategist has Freeze; [medium] a Freeze from the
  turn-12 enemy phase); Felicia's `staff` in reach of an enemy picks Attack first (the menu starts with Attack);
  `fq.sh` shots are named by frame, so two forecasts from one state overwrite each other.
- **The route** `cheat-cq-ch18` (routes.json, markers.json; one checked read-modify-write of only this key,
  build/speed/cqx18/tools/wroute18.py): save cheat-cq-ch17-clear, frames 170920, save_at 170910, 1,992 presses
  (h's 1,107 a prefix), no pokes, 11 checkpoints, verified false. `cheats.py --check` 7 cheat routes, rules OK;
  `--selftest` 23/23.
- **Replay checks** [high]: boot-server from frame 0 (tools/chk4.py, no pokes): instructions at 37060 and 108680
  equal f's and h's; 14 of 14 at every checkpoint, enemies 27 -> 10. Then `parallel.py runs --route cheat-cq-ch18
  --markers` (session r31-cqx18-markers, FEF_ROBOT_JOBS=4, 2.64 GB, below normal): PASS, exit 0, Completed after
  170920 frames, **checkpoints all met**, memory defb76ac..., instructions 765915765120, boot 553 s, peak 667 MB,
  %APPDATA% unchanged. The two-copy proof and the clear save `cheat-cq-ch18-clear` are a separate step.
- **Proof and capture (round 32)** [high]: `parallel.py runs --route cheat-cq-ch18 --copies 2 --markers --keep`
  (session r32-proof-cheat-cq-ch18, 05:55-06:21): both copies exit 0, Completed 170920 frames, memory defb76ac...,
  instructions 765915765120 both, checkpoints all met. `cheat-cq-ch18-clear.zip` packed from copy 1 (carries
  harness-cheat.json); verified true. Capture r32-cap-cheat-cq-ch18: 185 functions, 4,253 records, 0 bad (it kept
  no records, so integrate played it live once more with `--only all --store-keep`: r32-capc-cheat-cq-ch18, same
  memory, 4,253 records, 0 bad; it now replays offline from those records).

Wall time: 04:53 start to the castle 05:32 (**39 min of play**, 13 of them the rebuild; cap 100); export, replay
checks, route and docs to about 06:00.

#### 3z-cq19. Round 31 helper: Conquest chapter 19 on the cheat track (`cheat-cq-ch19`, F-033) [high unless tagged]

Fresh helper, cap 100 min of play. Chain `build/speed/cqx19/c` (`new c --save cheat-cq-ch18-clear --cheat`; tools = cqx18's
set with `MAPFILE` B019.bin.lz). **No new poke**: the move bonus 60 came in the start save, so the route is a cheat
route by its start save only (`"pokes": []`).

| | Chapter 19 'Kitsune Lair' (B019) |
|---|---|
| Win rule | rout the enemy: 26 foxes (kitsune 30 HP, nine-tails 34 HP, "guard" variants with 守獣石), the boss a nine-tails (38 HP, 超獣石) at (3,2) with two guards in the north-west corner |
| Start | 13 deployed (east, 20-24 x 15-19); opening: castle > Next Battle > LEFT A > LEFT A > preparations START > LEFT A > the 'Victory' rule card waits for A |

- **Beaststones do 0 to Camilla and Xander** [high, forecasts]: Camilla (Def 25) vs kitsune: 27 dealt, 0 taken; Xander
  vs nine-tails 28 dealt, 0 taken (x2). Guards and the boss do 7-11 to them. So Camilla and Xander went into each pack
  first; the weaker units only finished wounded foxes and otherwise stayed on tiles no fox could reach (`trig.py`).
- **State bit 0x400000 (Unit+8)** [high]: a fox with it set cannot be targeted that phase (no Attack in the menu next
  to it); the bit flips between turns (a "hidden" fox shows up the next turn and attacks). Plan kills only on 0x100
  units. The boss and its guards **do move** once a neighbour dies (the boss stepped to (2,3) and hit Camilla).
- **How it was won** (12 turns, nobody lost): turns 1-3 the north pack, turn 4 the centre trio (Azura sang Xander),
  turns 5-9 the west and centre-west packs, turn 10 Camilla (1,3) and Xander (2,4) killed the guard (2,3) after Elise
  healed Xander, turn 11 the boss came out and Camilla killed him (Xander missed), turn 12 Xander killed the last guard.
  Stage complete 167696, banner (Chapter 19, 12 turns) at 170706 waits for A, save menu 172318 (A, LEFT A), castle
  172674. The next chapter is B020 (not the Endgame).
- **Undone tries** (each lost a unit): Gunter at (20,8) on turn 1 (three foxes reached him), Gunter at (17,14) on
  turn 6, Camilla at 15 HP left at (12,9) on turn 7 (back to the turn-7 start, 10 undos, KEEP=14), Harold at (16,14)
  on turn 8. All were moved to tiles with 0 threat and replayed.
- **Tool findings** [high]: `attack:1` picks the second target (Gunter's javelin hit the wrong fox with plain
  `attack`); a staff move to a tile the unit cannot enter stops (Elise, mountain); Silas/Elise/Gunter could not cross
  to the west half (river), use `who.py` first; after an `attack` that ends the chapter the free-cursor screen shows
  for a moment before map__SequenceCompleteEffect; `end` needs a fresh cursor (`rp.sh "RIGHT LEFT"` first) after an
  attack, else the cursor lands on a unit.
- **The route** `cheat-cq-ch19` (routes.json, markers.json; one checked read-modify-write of only this key through
  `splitcfg.merge`, build/speed/cqx19/tools/wroute19.py): save cheat-cq-ch18-clear, frames 172690, save_at 172680,
  2,321 presses, no pokes, 11 checkpoints, verified false. `cheats.py --check` 8 cheat routes, rules OK; `--selftest`
  23/23.
- **Replay checks** [high]: boot-server from frame 0 (tools/chk4.py, no pokes): instructions at 172674 =
  773775677664, equal to the chain's; 13 of 13 at every checkpoint, enemies 26 -> 22 -> 17 -> 14 -> 8 -> 3 -> 1 -> 0.
  Then `parallel.py runs --route cheat-cq-ch19 --markers` (session r31-cqx19-markers, FEF_ROBOT_JOBS=4, 2.64 GB, below
  normal): PASS, exit 0, Completed after 172690 frames, **checkpoints all met**, memory faf6fbe0..., instructions
  773847375840, boot 632 s, peak 668 MB, %APPDATA% unchanged. The two-copy proof and the clear save
  `cheat-cq-ch19-clear` are a separate step.
- **Proof and capture (round 32)** [high]: `parallel.py runs --route cheat-cq-ch19 --copies 2 --markers --keep`
  (session r32-proof-cheat-cq-ch19, to 07:45): both copies exit 0, Completed 172690 frames, memory faf6fbe0...,
  instructions 773847375840 both, checkpoints all met. `cheat-cq-ch19-clear.zip` packed from copy 1 (carries
  harness-cheat.json); verified true. Capture r32-cap-cheat-cq-ch19: 179 functions, 4,032 records, 0 bad (no
  records kept, so integrate played it live once more with `--only all --store-keep`: r32-capc-cheat-cq-ch19, same
  memory, 4,032 records, 0 bad; it now replays offline from those records).

Wall time: 06:20 start to the castle 07:06 (**46 min of play**, cap 100); export, replay checks, route and docs to
about 07:32.

#### 3z-cq20. Conquest chapter 20 on the cheat track (`cheat-cq-ch20`), NOT cleared [high unless tagged]

Fresh helper, cap 100 min of play. Chain `build/speed/cqx20/c` (`new c --save cheat-cq-ch19-clear --cheat`; tools =
cqx19's set with `MAPFILE` B020.bin.lz; act2.py `end` now waits up to `ENDMAX` frames, default 20000, because one
enemy phase here ran past 9000). **No new poke** (the move bonus 60 came in the start save). No route key, no
checkpoints, no clear save written; cheats.py `--check` 8 cheat routes, rules OK; `--selftest` 23/23.

| | Chapter 20 'Winds of Change' (B020) |
|---|---|
| Win rule | Seize: the boss Fuga (Master of Arms, 45 HP, nageyari / katti / mace, throne (21,3)) must die, then Corrin stands on the throne |
| Map | sky walkways; the boss room (18-24, 2-8) is reached on foot **only** along row 5 from the west room (corridor (6-17,5)), held by a spear-master pair (12,5), a yamabushi (14,4), a spear master (13,6) and a shrine maiden (17,5) |
| Start | 14 deployed in a walled room (13-16, 22-25) whose only doors are (12,23) west and (15,26) south; 30 enemies; opening: castle > Next Battle (UP A) > LEFT A > LEFT A > START > LEFT A > the 'Seize' rule card waits for A |

- **Hard numbers** (forecasts) [high]: Fuga takes 11 from Camilla's steel axe (79%) and hits back for 7. Onmyoji
  scrolls (Tiger/Horse Spirit) take Corrin 40 -> 11-24, Harold or Nyx to 0 in one round, with the next onmyoji's dual
  strike. Spear masters take Camilla 19, Xander's Siegfried 23. The enemy pair's dual guard fills fast: burn it with a
  weak first hit (Nyx Fimbulvetr) before the killing blow.
- **Wind** [high]: at the end of each enemy phase units on wind tiles are pushed: (11,5) -> (11,11); the start room
  pushes north to (15,15)-(16,18). Pegasi also landed inside the room.
- **What failed (undone)** [high]: the row-5 push on turns 1-2 (Corrin at (10,5): lost; Nyx (10,5) + Camilla (12,4):
  both lost; Gunter shelter of Nyx at (9,5) + Xander (11,5): Gunter, Nyx and Xander lost). The west room's pegasi,
  kite archer, spear and onmyoji plus the corridor pack all reach (9-12, 4-6). At home on turn 4 every layout tried
  lost one or two (Gunter + Odin, Nyx, Silas, Odin, Felicia, Effie + Nyx): the onmyoji trio comes in by (12,23), three
  spear masters by (15,26), and a pegasus + spear pair lands on any empty tile in the room.
- **Reached** [high]: chain c at **49400 = turn 4 player phase, mid-turn, all 14 alive**. Turn 1 Elise menu Pair Up
  onto Xander, Xander (11,5) cut the pair lead to 12 (pushed home by the wind); turn 2 Camilla (4,23) + Niles (7,23)
  killed the reinforcement onmyoji, Xander back to (15,18); turn 3 everyone into the start room (Felicia healed Xander),
  all alive; turn 4 Camilla (16,22) killed one yamabushi that came into the room, Corrin (15,24) + Xander (15,22) the
  other, Shura (11,22) + Niles (11,20) one pegasus, Gunter (12,19) + Harold (11,21) the other; the pegasus +
  spear pair (18,20) is still there. Not yet moved on turn 4: Azura (13,19), Felicia, Silas, Effie, Odin, Nyx (16,27). Corrin 27.
- **Export and replay check** [high]: `fastlook export c` -> build/speed/cqx20/c-export.json, 666 presses, last 49348,
  frame 49400; `rewind.py c d 49400` rebuilt it from frame 0 of cheat-cq-ch19-clear on the clean line (132 s):
  cycles **221368118400, equal to c's**, the same presses, the same board (14 of 14, 30 enemies, same HP). The
  turn-4 start (37368, all alive, two yamabushi in the room) is a prefix of it (`rewind.py c e 37368`).
- **Next helper**: a turn-4 layout that loses nobody (fill the room so the pegasus pair cannot land next to a weak
  lead, or kill it first with Shura/Niles bows), then clear the onmyoji trio and the south spears from the doors
  before going north; the row-5 corridor needs the west room cleared first. At this pace the chapter is many turns.

Wall time: 07:57 start to the cut 08:38 (**41 min of play**, cap 100); stopped because no turn-4 layout tried kept
everyone alive and the rest of the map does not fit the cap at this pace; export, replay check and docs to about 08:45.

**Continuation (second helper, cap 60 min, 08:42 to 09:10 play), still NOT cleared** [high unless tagged]. Chain
`build/speed/cqx20/h` (a copy of c at 49400; trial copies f, g dropped). **No new poke.** Reached **turn 9 player
phase, frame 124358, 14 of 14 alive, 17 enemies left** (30 at the start; 13 killed in turns 4-8).

- **Turn 4 that works**: Azura Sings to Xander from (15,23) (not to Shura from (11,23): that left her where an
  onmyoji reaches her); Xander + Elise hit the pegasus pair from (17,19) at range 2 (34 -> 4); Odin from (19,19)
  takes the dual guard; Effie from (18,19) kills the pegasus. The pair's spear master is put down at (16,19); it can
  reach only Gunter or Xander (both lived). Nyx goes to (14,24): from (16,27) or (16,25) the south spears reach her.
  [high] The other order (Effie killing with Xander at (17,19) and (19,19) free) put the spear master at (19,19)
  next to Effie, and Effie died in the enemy phase (undone).
- **Turns 5-8**: the corridor spear master (13,19) (Xander range 2 + Camilla); the two onmyoji left at the west door
  (Shura, then Xander after a Sing); the two spear masters that walked into the start room (Xander, Shura, Gunter,
  Xander again); the slender-spear master (Harold + Corrin, it hits at range 2 only, so melee gets no counter);
  turn 7 the two north onmyoji (15,11) and (16,10) (Xander, Shura); turn 8 the (10,14)/(9,15)/(10,15) group (Xander
  twice with a Sing, Shura, Gunter, Harold, Camilla, Nyx).
- **Learned** [high]: magic barely hurts here (Odin's Thunder did 0 four times on the pegasus and a spear master;
  Nyx's Fire 7); Harold misses onmyoji; Xander's Siegfried at range 2 kills an onmyoji in one fight and is the main
  killer, with Azura's Sing every turn. Corrin's `attack` uses his first item, the dragonstone (15 to a spear master,
  he took 21 back from the corridor pair). Tsukuyomi (9,9), the west shrine maiden (3,15) and the yamabushi beside it
  did **not move** in turns 7-8 although `trig.py` showed them reaching us (they look like stay-in-place AI) [med].
  The wind moves units several tiles at the end of each enemy phase (turn 6: Odin to (16,11), Niles to (11,14));
  plan the next turn from where they land. A move of ten or more tiles needs `MW=300`-`600` in act2.py, else the
  phase stops on ProcMoveRoute and undoes. Pair Up onto a unit that has already moved is not offered.
- **Tried and undone** [high]: the corridor pair (12,5) on turn 8: Xander from (10,5) was dual-guarded, Corrin from
  (11,5) fell to 10 HP (the pair lead 28 -> 14). Tsukuyomi: Gunter (31 -> 10) and Camilla (26 -> 14) on counters.
- **Export and replay check** [high]: `fastlook export h` -> build/speed/cqx20/h-export.json (1644 presses, last
  124306, frame 124358); `rewind.py h i 124358` rebuilt it from frame 0 of cheat-cq-ch19-clear on the clean line
  (346 s): the same 1644 presses, cycles **557265110688 equal**, the same board (14 of 14, 17 enemies, same HP).
  cheats.py `--check` 8 cheat routes, rules OK; `--selftest` 23/23. No route key, checkpoints or clear save.
- **Next helper**: continue from chain h (or i) at 124358. Left: the corridor (pair (12,5) 28+36, spear (13,6),
  yamabushi (14,4), shrine maiden (17,5)), then the boss room (Fuga 45 HP, shrine maiden (21,6)); the west room
  (3,5)/(1,5)/(2,3) and the east spears (23,15)/(24,16) + kite archer (24,13) reach the corridor ends. Burn the
  pair's dual guard with a cheap hit first, then Xander; keep Corrin off (11,5) until the pair is dead.

Wall time (second helper): 08:42 start, play cut at 09:10 (**28 min of play**, cap 60), export and frame-0 rebuild
to 09:17, docs to about 09:20. Stopped with the cap's remaining time too short for the corridor and the boss.

#### 3z-cq20b. Round 33 helper: Conquest chapter 20 CLEARED on the cheat track (`cheat-cq-ch20`) [high unless tagged]

Fresh helper, cap 100 min of play. Chain `build/speed/cqx20/j` = a copy of i (frame-0 rebuild of h) at 124358; c, h
and i untouched. KEEP=12 undo snapshots, `MW=300`-`600` for the long moves. **No new poke** (the move bonus 60 came in
the start save `cheat-cq-ch19-clear`, so the route is a cheat route by its start save only, `"pokes": []`).

- **Turn 9**: Gunter as bait at (6,9) died (the west spear master + kite archer came out; undone). With Xander's
  pair there instead nobody attacked, but the **kite archer flew out to (6,7)**.
- **Turn 10**: Xander killed the kite archer from (5,7) at range 1 (a bow cannot counter, 100%), Azura Sang, Xander
  killed the west onmyoji (1,5) from (1,7) at range 2. Camilla, Gunter and Effie blocked round Azura (4,7): **the
  spear masters do 0-2 to Camilla and 0 to Gunter** (forecasts), Harold takes 24. A first end of turn lost Shura and
  Nyx because their moves had stopped (ProcMoveRoute, MW too short) and were undone without my noticing; undone, the
  moves redone with MW=600 [high]. The south-west yamabushi came out for Shura/Nyx and went home the next turn.
- **Turn 11**: west spear master (3,6): Xander range 2 (31 -> 13, no counter), Camilla melee 12 (killed). Felicia
  Heal and Shura Mend: the staff target list starts with the nearest ally (RIGHT to change).
- **Turn 12 (the corridor pair)**: Gunter's javelin **from (10,5) at range 2** (7, no counter), Azura Sang Gunter,
  javelin again (21 -> 13), Xander melee from (11,5) killed the lead (no dual guard). The first try (Gunter melee from
  (11,5), took 16, then Camilla paired onto him) lost Gunter in the enemy phase: undone 6 steps (KEEP=12 was enough).
- **Turns 13-14**: Xander (11,5) killed the yamabushi (13,5) at range 2 (95%); Gunter javelin + Sing + javelin took
  the pair's support to 6; turn 14 Xander (10,5) killed it, Shura (12,5) 12 + Gunter (13,5) 7 + Xander from the
  pillar (14,5) killed the last spear master.
- **Turn 15**: Xander killed the corridor shrine maiden (15,5) at 6 HP; the boss-room shrine maiden (21,6): Camilla
  melee from (22,6) 26 (a bow cannot counter at range 1), Effie (21,7) finished it. Xander + Sing hit Fuga 45 -> 30.
  **Fuga hit Xander 34 -> 6 in the enemy phase and healed to 39 on the throne** [high].
- **Turn 16 (Fuga)**: forecasts: Silver Katti doubles most units (Atk 26, 100% hit); Harold and Silas 0 damage, Effie,
  Nyx, Odin, Silas would die on the counter. Felicia (22,2) Heal Xander 6 -> 22, Shura (20,2) Mend -> 42 (careful: in
  reach of the boss the menu starts with **Attack**, staff is DOWN A); Xander's first try missed (71%), undone;
  Camilla (22,3) first (39 -> 30, she took 13), then Xander (21,2) 23 (30 -> 7), then Corrin (20,3) dragonstone
  killed him. The Secret Book drop: Corrin's bag full, DOWN x5 A, LEFT A (Yes) sends it to the convoy.
- **Turn 17**: the wind had pushed **Effie onto the throne**: Effie off to (21,5), Corrin to (21,3): **Seize** is the
  first command, then "Seize and finish the battle?" LEFT A. Stage complete 218370 (17 turns, heroes Elise & Xander),
  banner 221380 waits for A, a talk (answered), save menu 223014 (A, LEFT A), castle 223370. Next chapter B021 (not
  the Endgame).
- **Wind** [high]: pushes are per column and per turn (turn 9: x 10-13 north up to 6 tiles to the farthest floor,
  x 8 and 14-15 south); units cross sky tiles in a push (Nyx (11,11) -> (11,5)). It also moved the enemies' kite archer.
- **The route** `cheat-cq-ch20` (routes.json, markers.json; one checked read-modify-write of only this key through
  `splitcfg.merge`, build/speed/cqx20/tools/wroute20.py): save cheat-cq-ch19-clear, frames 223386, save_at 223376,
  2,855 presses (h's 1,644 a prefix), no pokes, 12 checkpoints, verified false. `cheats.py --check` 9 cheat routes,
  rules OK; `--selftest` 23/23.
- **Replay checks** [high]: boot-server from frame 0 (tools/chk4.py, no pokes, chk20.out): cycles at 124358 =
  557265110688 (h/i's) and at 223370 = 1000951348320 (j's); 14 of 14 at every map checkpoint, enemies 30 -> 34 -> 17 ->
  15 -> 13 -> 10 -> 8 -> 7 (reinforcements on turn 4). Then `parallel.py runs --route cheat-cq-ch20 --markers` (session
  r33-cqx20-markers, FEF_ROBOT_JOBS=4, 2.64 GB, below normal): PASS, exit 0, Completed after 223386 frames,
  **checkpoints all met**, memory 2737fb0d..., instructions 1001023046496, boot 633 s, peak 703 MB, %APPDATA%
  unchanged. The two-copy proof and the clear save `cheat-cq-ch20-clear` are a separate step.
- **Proof (round 34, 10:40-11:06):** `parallel.py runs --route cheat-cq-ch20 --copies 2 --markers --keep` (session
  r34-proof-cheat-cq-ch20, FEF_ROBOT_JOBS=4, below normal): both copies exit 0, Completed after 223386 frames, memory
  2737fb0dea13f91a... and instructions 1001023046496 in both, checkpoints all met. `cheat-cq-ch20-clear.zip` packed from copy 1
  (carries harness-cheat.json: cheat true, 0 pokes); routes.json verified true. Capture r34-cap-cheat-cq-ch20:
  187 functions, 4,373 records (4,241 match, 97 gave up, 35 incomplete), 0 bad of any kind, no writer stores (no records kept, so round 34 integrate played it
  live once more with `--only all --store-keep`: r34-capc-cheat-cq-ch20, same memory, same counts, 0 bad).

Wall time: 09:43 start to the castle 10:16 (**33 min of play**, cap 100); export, frame-0 replay, route, marker run
and docs to about 10:40 (about 57 min in all).

#### 3z-cq21. Round 34 helper: Conquest chapter 21 CLEARED on the cheat track (`cheat-cq-ch21`) [high unless tagged]

Fresh helper, cap 100 min of play. Chain `build/speed/cqx21/c` (`new c --save cheat-cq-ch20-clear --cheat`; tools =
cqx20's set with `MAPFILE` B021.bin.lz; tmap.py now prints the map's own play area). **No new poke** (the move bonus 60
came in the start save, so the route is a cheat route by its start save only, `"pokes": []`).

| | Chapter 21 'Eternal Stairway' (B021) |
|---|---|
| Win rule | escape with all units: a unit on the escape tile has **Escape** as its first command, then "Leave the battlefield?" (LEFT A = Yes) |
| Map | 18 x 31 stairway, low walls (fliers only) and rubble force a zigzag up the side stairs; escape tile used (9,1), next to the boss pair (10,2) |
| Enemies | 27: the boss (Nosferatu, 45 HP) paired at (10,2), 6 golems (Boulder 1-5), 19 Nosferatu (fists 1); none moved (we never ended a turn) |
| Start | 14 deployed at the south end (6-13, 25-26); opening as in chapter 20 (castle > Next Battle > LEFT A > LEFT A > START > LEFT A > the 'Victory' card waits for A) |

- **How it was won** [high]: with move 60 every unit reaches (9,1) from the start in one move (danger.reach and the
  game agree: about 26 presses of path each, `MW=600`). On turn 1 the 14 units moved there one after another and
  escaped (the tile is free again after each escape), Corrin last: `act2.py c X,Y 9,1 menu:0 "LEFT A"`. Corrin's
  escape ends the chapter at once: stage complete 40598 (the screen reads `castle__anonymous_namespace__Seq`), banner
  (Chapter 21, 1 turn, 14 units) waits for A (43608), a talk (answered), save slot menu 51380 (A, LEFT A), castle
  51736. **No battle was fought** in this chapter (nothing to test for combat here; the escape, banner, talk and save
  ran). The next chapter is B022 (not the Endgame). Nothing undone.
- **The route** `cheat-cq-ch21` (routes.json, markers.json; one checked read-modify-write of only this key through
  `splitcfg.merge`, build/speed/cqx21/tools/wroute21.py): save cheat-cq-ch20-clear, frames 51752, save_at 51742,
  1,177 presses, no pokes, 8 checkpoints, verified false. `cheats.py --check` 10 cheat routes, rules OK; `--selftest`
  23/23.
- **Replay checks** [high]: boot-server from frame 0 (tools/chk4.py, no pokes, chk21.out): cycles at 51736 =
  231836052096, equal to the chain's; units on the map 14 -> 13 -> 10 -> 1 -> 0, enemies 27 throughout. Then
  `parallel.py runs --route cheat-cq-ch21 --markers` (session r34-cqx21-markers, FEF_ROBOT_JOBS=4, 2.64 GB, below
  normal): PASS, exit 0, Completed after 51752 frames, **checkpoints all met**, memory b0b3c09e..., instructions
  231907750272, boot 85 s, peak 498 MB, %APPDATA% unchanged. The two-copy proof and the clear save
  `cheat-cq-ch21-clear` are a separate step.
- **Proof (round 34, 11:18-11:26):** `parallel.py runs --route cheat-cq-ch21 --copies 2 --markers --keep` (session
  r34-proof-cheat-cq-ch21, FEF_ROBOT_JOBS=4, below normal): both copies exit 0, Completed after 51752 frames, memory
  b0b3c09ee71138cd... and instructions 231907750272 in both, checkpoints all met. `cheat-cq-ch21-clear.zip` packed from copy 1
  (carries harness-cheat.json: cheat true, 0 pokes); routes.json verified true. Capture r34-cap-cheat-cq-ch21:
  103 functions, 2,384 records (2,286 match, 69 gave up, 29 incomplete), 0 bad of any kind, no writer stores (no records kept, so round 34 integrate played it
  live once more with `--only all --store-keep`: r34-capc-cheat-cq-ch21, same memory, same counts, 0 bad).

Wall time: 11:06 start to the castle about 11:12 (**about 6 min of play**, cap 100); export, frame-0 replay, route,
marker run and docs to about 11:20 (about 15 min in all).


#### 3z-cq22. Round 34 helper: Conquest chapter 22 CLEARED on the cheat track (`cheat-cq-ch22`) [high unless tagged]

Fresh helper, cap 100 min of play. Chain `build/speed/cqx22/c` (`new c --save cheat-cq-ch21-clear --cheat`; tools =
cqx21's set with `MAPFILE` B022.bin.lz, plus tools/veins.py (the TrickData list from state.bin: type 11 veins with the
type-12 areas they change) and tools/vsim.py (reach with chosen levees flattened)). **No new poke** (the move bonus 60
came in the start save, so the route is a cheat route by its start save only, `"pokes": []`). Benoit (new) has bonus 0.

| | Chapter 22 'Sakura' (B022) |
|---|---|
| Win rule | Seize the gate (13,1) (TrickData type 3); the boss Yukimura (Mechanist, 45 HP, Silver Shuriken 1-2) stands on it |
| Map | 26 x 21, two walled lanes; levees (terrain 7-9, impassable even for fliers) open by 7 dragon veins: (20,7) -> (8-10,5), (10,4) -> (17-19,3-6), (15,4) -> (11,6-8)+(14,6-8), (6,6) -> (17-20,9), (22,13) -> (5-9,7-9), (3,13) -> (14-19,13-14), (19,16) -> (4,14-16); Sakura's own vein (13,5) is already used (state 2) |
| Enemies | 23 (boss, Sakura, Kazahana, Subaki, 2 mechanists, 4 oni chieftains, 4 blacksmiths, 3 automatons, 4 onmyoji); none moved (we never ended a turn) |
| Start | 15 deployed: west lane (5-9, 18-19), east lane (16-19, 18-19); opening castle > B > START > UP A > LEFT A > LEFT A > (talk) > preparations START > LEFT A > the 'Seize' card waits for A |

- **How it was won** [high]: with move 60 the east lane already reaches the gate by the east edge (about 42 steps);
  after the vein (20,7) the west lane does too (Corrin 26-27). Turn 1: Elise (Troubadour, a royal) to (20,7), Dragon
  Vein is her first command, then A on 'Flatten a levee.' Camilla (14,1) steel axe 45 -> 36 (forecast said 29; took 11),
  Xander (14,2) Siegfried at range 2 with Camilla's dual strike 36 -> 28 (took 12), Azura (15,2) Sing to Xander (R on the
  forecast switches the dual-strike partner from Azura to Camilla: 28 -> 2 forecast), Xander again 28 -> 2 (Xander 14
  HP), Gunter (13,2) javelin 73% killed him (Gold Bar). Corrin (7,19) -> (13,1): **Seize** first command, Yes (LEFT A).
  Stage complete 25242 (screen `castle__anonymous_namespace__Seq`), banner (Chapter 22: Sakura, 1 turn, 15 units,
  heroes Camilla & Xander) waits for A (28312), a talk (answered), save slot menu 32344 (A, LEFT A), castle 32700.
  The next chapter is B023 (not the Endgame). Nothing was lost; no try was undone for a loss.
- **Forecasts on the boss on the gate** [high]: Nyx Fire, Odin Thunder, Niles Iron Bow, Corrin Dragonstone, Harold
  Hand Axe do 0-2 and would die on the counter; Shura Killer Bow 2; Gunter javelin 6 (16 back). Only Camilla and Xander
  hurt him. Camilla's **Lunge** is not offered next to him (it was offered at (20,7) with no target near) [med: boss or
  gate tile excludes Lunge; not traced].
- **Tool finding** [high]: danger.py's grid (`mi+0x808`) still shows the flattened levee after the vein; the game's
  move used the open path (Corrin reached (12,2)). Trust a `show` move, not the grid, after a vein.
- **The route** `cheat-cq-ch22` (routes.json, markers.json; one checked read-modify-write of only this key through
  `splitcfg.merge`, build/speed/cqx22/tools/wroute22.py): save cheat-cq-ch21-clear, frames 32716, save_at 32706,
  515 presses, no pokes, 11 checkpoints, verified false. `cheats.py --check` 11 cheat routes, rules OK; `--selftest`
  23/23.
- **Replay checks** [high]: boot-server from frame 0 (tools/chk4.py, no pokes, chk22.out): cycles at 32700 =
  146533147200, equal to the chain's; units 15 at every map checkpoint, enemies 23 -> 22 (the boss), veins_used 1 -> 2.
  Then `parallel.py runs --route cheat-cq-ch22 --markers` (session r34-cqx22-markers, FEF_ROBOT_JOBS=4, 2.64 GB, below
  normal): PASS, exit 0, Completed after 32716 frames, **checkpoints all met**, memory a3d1ce80..., instructions
  146604845376, boot 79 s, peak 668 MB, %APPDATA% unchanged. The two-copy proof and the clear save
  `cheat-cq-ch22-clear` are a separate step.
- **Proof (round 34, about 11:41-11:51):** `parallel.py runs --route cheat-cq-ch22 --copies 2 --markers --keep` (session
  r34-proof-cheat-cq-ch22, FEF_ROBOT_JOBS=4, below normal): both copies exit 0, Completed after 32716 frames, memory
  a3d1ce80f2fa2a74... and instructions 146604845376 in both, checkpoints all met. `cheat-cq-ch22-clear.zip` packed from copy 1
  (carries harness-cheat.json: cheat true, 0 pokes); routes.json verified true. Capture r34-cap-cheat-cq-ch22:
  150 functions, 2,826 records (2,699 match, 90 gave up, 37 incomplete), 0 bad of any kind, no writer stores (no records kept, so round 34 integrate played it
  live once more with `--only all --store-keep`: r34-capc-cheat-cq-ch22, same memory, same counts, 0 bad).

Wall time: 11:24 start to the castle 11:37 (**about 13 min of play**, cap 100); export, frame-0 replay, route, marker
run and docs to about 11:45 (about 21 min in all).

#### 3z-cq23. Round 34 helper: Conquest chapter 23 CLEARED on the cheat track (`cheat-cq-ch23`) [high unless tagged]

Fresh helper, cap 100 min of play. Chain `build/speed/cqx23/c` (`new c --save cheat-cq-ch22-clear --cheat`; tools =
cqx22's set with `MAPFILE` B023.bin.lz, plus tools/via.sh (one unit through both stairs to a tile, stops at the command
menu) and tools/wc.py (move cost through the stairs pairs; it over-counted Gunter's leftover move, see below)). **No new
poke** (the move bonus 60 came in the start save, so the route is a cheat route by its start save only, `"pokes": []`).

| | Chapter 23 'Possessed' (B023) |
|---|---|
| Win rule | Seize the throne (5,3) (TrickData type 3); the boss Takumi (Sniper, 45 HP, Fujin Yumi 2-2, Goddess Icon) sits on it |
| Map | 30 x 24; the throne room (x 2-8, y 3-5) and the castle (x 10-29, y 1-7) are walled; the only ways in are 8 stairs tiles in 4 pairs (TrickData type 28): (14,8)-(16,6), (17,9)-(19,7), (25,9)-(23,7), (28,8)-(26,6) into the castle, and (10,1)-(8,1) from the castle into the throne room. South to north only by the bridge (4-6, 11-13). Bow turrets (5,4), (21,7), (17,12) (fliers may not stand on (5,4) either) |
| Enemies | 30 (Takumi, Hinata (5,9), Oboro pair (12,2), snipers, spear masters, basara, great masters); none moved (we never ended a turn) |
| Start | 15 deployed (20-24, 19-22); opening as in chapter 22 (castle > B > START > UP A > LEFT A > LEFT A > (talk) > preparations START > LEFT A > the 'Seize' card waits for A, sometimes twice) |

- **Stairs** [high]: a unit that ends a move on a stairs tile gets **Stairs** as its first command; A warps it to the paired
  tile and the unit **can move again** with the move it has left (a `show` from the exit tile reached the command menu).
  danger.py's reach does not know the warps. Xander, Camilla, Azura and Corrin reached the throne room in one turn from
  the start; Gunter (Great Knight) had only about 3 tiles left at (8,1) (game's blue range), less than wc.py said [med:
  not traced why].
- **Forecasts on Takumi** [high]: Fujin Yumi is 2-2 but **he counters at range 1** (Xander alone: 71% hit, 26 damage,
  took 8). Camilla at (4,3) would die (Fujin Yumi is effective on fliers: 100% hit, she has 0 HP after). With Camilla
  waiting adjacent at (6,4) (attack stance), Xander (6,3) got 81% and her dual strike: Takumi 45 -> 8, but his counter
  took Xander 43 -> 1. The first try (Xander alone) missed and was undone.
- **How it was won** [high]: turn 1: Camilla via the stairs (14,8) and (10,1) to (6,4), Wait (her menu starts with Attack:
  DOWN DOWN A); Xander via the stairs to (6,3), attack (Takumi -> 8); Azura via the stairs to (7,3), Sing (first command)
  to Xander; Xander again with Camilla's dual strike (85%) killed Takumi; Corrin via the stairs onto the throne (5,3):
  **Seize** first command, then 'Seize and finish the battle?' LEFT A. Seize question 28774, stage complete 28898 (the
  screen reads `castle__anonymous_namespace__Seq`), banner (Chapter 23: Possessed, 1 turn, heroes Camilla & Xander)
  31968 waits for A, a talk (answered), save slot menu 36150 (A, LEFT A), castle 36506. The next chapter is B024 (not the
  Endgame). Nothing was lost; Xander ended on 1 HP (no enemy phase came).
- **The route** `cheat-cq-ch23` (routes.json, markers.json; one checked read-modify-write of only this key through
  `splitcfg.merge`, build/speed/cqx23/tools/wroute23.py; both files compared before and after: only this key changed):
  save cheat-cq-ch22-clear, frames 36522, save_at 36512, 555 presses, no pokes, 10 checkpoints, verified false.
  `cheats.py --check` 12 cheat routes, rules OK; `--selftest` 23/23.
- **Replay checks** [high]: boot-server from frame 0 (tools/chk4.py, no pokes, chk23.out): cycles at 36506 =
  163588350816, equal to the chain's; units 15 at every map checkpoint, enemies 30 -> 29 (Takumi). Then `parallel.py runs
  --route cheat-cq-ch23 --markers` (session r34-cqx23-markers, FEF_ROBOT_JOBS=4, 2.64 GB, below normal): PASS, exit 0,
  Completed after 36522 frames, **checkpoints all met**, memory bd79d0e5..., instructions 163660048992, boot 116 s, peak
  612 MB, %APPDATA% unchanged. The two-copy proof and the clear save `cheat-cq-ch23-clear` are a separate step.
- **Proof (round 34, about 12:06-12:14):** `parallel.py runs --route cheat-cq-ch23 --copies 2 --markers --keep` (session
  r34-proof-cheat-cq-ch23, FEF_ROBOT_JOBS=4, below normal): both copies exit 0, Completed after 36522 frames, memory
  bd79d0e50a8ded72... and instructions 163660048992 in both, checkpoints all met. `cheat-cq-ch23-clear.zip` packed from copy 1
  (carries harness-cheat.json: cheat true, 0 pokes); routes.json verified true. Capture r34-cap-cheat-cq-ch23:
  148 functions, 2,789 records (2,653 match, 84 gave up, 52 incomplete), 0 bad of any kind, no writer stores (no records kept, so round 34 integrate played it
  live once more with `--only all --store-keep`: r34-capc-cheat-cq-ch23, same memory, same counts, 0 bad).

Wall time: 11:46 start to the castle 12:00 (**about 14 min of play**, cap 100); export, frame-0 replay, route, marker
run and docs to about 12:06 (about 20 min in all).

#### 3z-cq24. Conquest chapter 24 on the cheat track (`cheat-cq-ch24`), NOT cleared, stopped [high unless tagged]

Fresh helper, cap 100 min of play. Chain `build/speed/cqx24/c` (`new c --save cheat-cq-ch23-clear --cheat`; tools =
cqx23's set with `MAPFILE` B024.bin.lz). **No poke** was made. **No route key was written** (the chapter was not won).

| | Chapter 24 (B024) |
|---|---|
| Win rule | Seize the gate (12,1) (TrickData type 3, also a dragon vein); the boss Hinoka (Falcon Knight lv 16, 41 HP, Silver Nageyari 1-2, Speedwing) stands on it **paired with an Oni Chieftain** (41 HP, Silver Throwing Club 1-2, Rabbit scroll) |
| Enemies | 25 at the start (falcon knights, kinshi, Asama (Great Master, 45 HP, steel naginata + a staff), onmyoji in pairs next to oni chieftains); **reinforcements already at the end of enemy phase 1**: oni (17,1) (18,1), kinshi (23,6) (23,7) and (9,29) (9,30) |
| Start | 15 deployed (19-22, 25-28); opening: p0 (abs to 4400, already the preparations), START LEFT A (st.json), A on the 'Seize' card (ok.json) |

- **Forecasts** [high]: only Xander (Siegfried, about 15-17 a hit, 47-65%) and Camilla (steel axe, 8-12, 57%) hurt Hinoka.
  Gunter's javelin does 2-4; Niles, Nyx, Odin, Harold, Silas, Felicia, Shura (killer bow: **no bow bonus on her**, as
  Grok said), Corrin (dragonstone and Grim Yato, X in the forecast switches weapon) do 0. She hits back for 15-30 and
  kills everyone but Xander, Camilla and Gunter. Against the Oni Chieftain alone (after Hinoka died) every other unit did
  0-2 and would die on his counter (silver mace). The onmyoji next to an oni get the oni's dual strike: Effie and
  Harold died on them (undone).
- **Reading the forecast** [high]: a white, empty HP bar with no number means 0 HP (that side dies); the skull marks
  a kill too. A red bar with a number is the HP left.
- **Hinoka's defences** [high]: she has **Sol** (healed 12 from a hit on Shura, 7 from one on Gunter), and the pair's
  **dual guard gauge** fills after two combats: the third attack is blocked whole (Xander did 0 that time). So every
  third combat must be a 'burner': only Gunter survives that (from (12,2), 37 -> 23), and from (12,2) he gets Xander's
  dual strike.
- **A turn-1 kill line exists** [high]: chain c at frame 27822 (inputs.txt there): Shura (19,1) and Niles (18,2) killed
  the kinshi (17,1) (no damage taken); Camilla (11,1) axe; Xander (11,2) with Camilla's dual strike (Hinoka 16); Gunter
  (12,2) burner with Xander's dual; Azura (11,3) sang to Xander ((10,2) is a tree, she cannot stand there); Xander again
  (65%, the forecast showed the kill) killed Hinoka. The **Oni Chieftain then stays on (12,1)** (state 0x800100), so no
  seize that turn.
- **Why it stopped** [high]: ending turn 1 there lost Gunter (the oni on the gate), Azura (the oni (14,7) came to (12,3))
  and Niles (onmyoji / falcon), all undone. Every unit that the turn-1 kill needs next to the gate (burner, singer)
  dies in enemy phase 1, and only Xander and Camilla can hurt the oni on turn 2. A pair-up does not protect: the unit
  that **moves onto** an ally becomes the **support**, the one already standing stays the lead (Corrin onto Azura made
  Azura the lead; undone). danger.py's grid shows most of rows 4-6 as walls here, but the screen shows open plains
  and the oni walked (14,7) -> (12,3): do not trust dz.py on this map. A clear needs more than a movement poke
  (F-033 allows movement only), or a long careful multi-turn fight with reinforcements every turn; per F-033 this is
  stopped and reported.
- Wall time: 12:11 start, play stopped 12:46 (**about 35 min of play**, cap 100), docs to about 12:52.
- **Second helper (cap 60 min, 12:47-12:58)** [high]: went on from a copy of chain c (`cqx24/e`, frame 27904,
  Hinoka dead, turn 1). No poke. Checks: Nyx's Fire does 2 to the Oni Chieftain and dies on the counter (magic does
  not help); the dragon vein at (10,4) only "slows fliers, speeds others" (no damage); Azura's max HP is 17.
  Try: Felicia healed Gunter to 37/37 from (12,3), then six fresh units ringed Azura and Felicia (Effie (13,3),
  Corrin (12,4), Harold (11,5), Silas (11,4), Nyx (10,4); (10,3) cannot be entered). Enemy phase 1 (look-ahead,
  `cqx24/e_after_ep1_lost`, frame 48144) lost **Gunter at full HP** (the gate Oni), **Corrin**, Harold and Effie
  (onis from (14,7) and the reinforcement side); Xander, Camilla, Azura lived. Undone (`cqx24/e` = the state
  before end turn, also `e_pre_end1`). So the turn-1 kill always costs the burner Gunter, and blockers die too:
  not winnable with movement only. Stopped and reported again; no route key.

#### 3z-cq24b. Round 35: Conquest chapter 24 CLEARED on the cheat track with the F-036 boost (`cheat-cq-ch24`) [high unless tagged]

Fresh helper, cap 100 min of play. New chain `build/speed/cqx24/f` (`new f --save cheat-cq-ch23-clear --cheat`, the
opening presses of chain c to 7654; the old chains c, d, e were not changed; copies `f_prepoke`, `f_t1kill`).
**Pokes used (F-036, plus one F-033 movement poke)**: 106 at frame 7654 (turn 1 player phase, before any move), each with
`expect`, made by tools/r35rd.py and applied with tools/poke.py: for all 15 units the HP gain `Unit.gains[0]` (+0xC8) +60
and the HP cap bonus `Unit.limit_bonus[0]` (+0xD0, added by Unit::GetLimit, so the raised stat is not cut to the class
cap) +60, Def and Res gains (+0xCE, +0xCF) and cap bonuses (+0xD6, +0xD7) +40, current HP (u8 Unit+0xF3) to the new
maximum (99 at most); unit 39 (the only one without the save's move bonus) `+0x12C` 0 -> 60. No hit, item or enemy poke.
- **The boost took** [high]: the status screen shows Corrin 99/99; the forecasts show 0 damage taken (Gunter vs the Oni
  Chieftain 64%, Xander 100%).
- **How it was won** [high]: turn 1 = round 34's kill line pressed again (chain c's presses 7694-27812): Shura and Niles
  killed the kinshi (17,1), Camilla (11,1), Xander (11,2) with Camilla's dual, Gunter (12,2) took the dual guard (no damage
  now), Azura (11,3) sang, Xander killed Hinoka; the Oni Chieftain stayed on the gate. End turn: enemy phase 1 lost
  **nobody**; no enemy moved, Gunter alone went 97 -> 49 (not traced what did it); 4 reinforcements came. Turn 2: Xander
  (11,2) Siegfried on the oni 41 -> 18, Camilla (11,1) with Gunter's dual strike killed it (the forecast showed the kill,
  65%), Corrin (20,26) moved onto the gate (12,1) (act2 `MW=1200`: a long move route outlasts the default wait), Seize,
  LEFT A. Stage complete 35428 (2 turns, heroes Camilla & Xander), banner A 38548, talk, save slot menu 42740 (A,
  LEFT A), castle 43096 (chapter B025, not the Endgame). 15 of 15, nobody lost, no rollback of a played turn.
- **The route** `cheat-cq-ch24` (routes.json, markers.json; one checked read-modify-write of only this key through
  `splitcfg.merge`, tools/wroute24.py; both files compared before and after: only this key added): save
  cheat-cq-ch23-clear, frames 43112, save_at 43102, 706 presses, 106 pokes, 16 checkpoints, verified false.
  `cheats.py --check` 13 cheat routes, rules OK; `--selftest` 23/23.
- **Replay checks** [high]: boot-server from frame 0 with the pokes (tools/chk4.py, chk24.out): cycles at 43096 =
  193119037056, equal to the chain's; units 15 at every map checkpoint, enemies 25 -> 23 (turn 1), 27 (turn 2) -> 26.
  `parallel.py runs --route cheat-cq-ch24 --markers` (session r35-cqx24-markers, FEF_ROBOT_JOBS=4, 2.64 GB, below normal):
  PASS, exit 0, Completed after 43112 frames, **checkpoints all met**, memory 372863cc..., instructions 193190735232, boot
  202 s, peak 798 MB, %APPDATA% unchanged. The two-copy proof and the clear save `cheat-cq-ch24-clear` are a separate step.
- **Proof (round 37, r37-proof-cheat-cq-ch24, 13:40-13:53):** both copies exit 0, 43112 frames, memory
  372863cca6511895, 193,190,735,232 instructions, checkpoints all met; `cheat-cq-ch24-clear.zip` packed from copy 1
  (cheat mark, 106 pokes); capture r37-cap-cheat-cq-ch24 4,778 records, 0 bad (kept no records); verified true.
  Integrate played it live again with every override and `--store-keep` (r37-capc-cheat-cq-ch24) after the library
  rebuild; see "Round 37 integrate".

Wall time: 13:22 start, castle 13:31 (**about 9 min of play**, cap 100); export, frame-0 replay, route, marker run and docs
to about 13:42 (about 20 min in all).

#### 3z-cq25. Conquest chapter 25 CLEARED on the cheat track (`cheat-cq-ch25`) [high unless tagged]

Fresh helper, cap 100 min of play. Chain `build/speed/cqx25/c` (`new c --save cheat-cq-ch24-clear --cheat`; tools = cqx24's
set, `MAPFILE` B025.bin.lz). Opening: p0 (abs to 4400: Preparations > Inventory menu), B, START (castle butler), UP A
(Next Battle), A (Chapter 25), LEFT A (Yes), talk until the sortie menu (11904, answer on), st.json, ok.json (12772).
**Pokes (F-036 + F-033)**: 8 at 12856, Leo only (unit 41, new this chapter, 34 HP, no boost): HP gain/cap +60, Def/Res
gains/caps +40, current HP 34 -> 94, move bonus 0 -> 60, each with `expect` (r35rd.py `--make`, poke.py). The other 15
carry the boost in the save. No hit, item or enemy poke.

| | Chapter 25 (B025) |
|---|---|
| Win rule | Defeat the boss Ryoma (Swordmaster lv 18, 48 HP, Raijinto, Dracoshield) at (13,11) in the throne room (12-17, 10-18, terrain "Chamber", heal tiles) |
| Start | **Corrin alone inside the throne room** (16,17); 15 others in the south rooms; 28 enemies, all in rooms that are closed or blocked; doors (TrickData type 0) (14,19), (14,9), (11,5), (18,5) state 0x1; vein (type 11) (14,6) tied to the room (type 12) |

- **The room heals** [high]: Corrin (dragonstone 2 a hit, 63%; Grim Yato 1) took Ryoma 48 -> 46 and he was 48 again
  next turn. Ryoma did nothing in enemy phases 1-3 and no enemy moved at all.
- **The way in** [high]: the guide's rule holds: killing a retainer opens all four doors at once (state 0x2), the same
  action. Saizo's room (NW) is blocked by the swordmasters (3,7)/(3,8); Kagero's (NE) only by the Master of Arms (25,7)
  (row 7). Danger tools: enemies block tiles, so `near.py` showed both rooms unreachable until (25,7) died.
  Locktouch (Shura) and Niles show no Door command at these doors.
- **How it was won** [high]: turns 1-3 Corrin's hit and two empty end turns (end on an empty tile: `act2 end 14,14`).
  Turn 4: Xander (25,8) on (25,7) 47 -> 21, Azura (25,9) sang, Xander killed it; Kagero (37 HP, Master Ninja) by Camilla
  (27,2) -> 30, Odin (28,2) Thunder with Camilla's dual -> 20, Shura (24,2) -> 15, Niles (27,3) -> 11, Harold (25,2) iron
  axe -> 5, Gunter (26,3) javelin killed her (axes and bows beat shuriken; Nyx's Fire/Fimbulvetr 0-8% on her, undone).
  Elise (14,6) used the vein ("turn healing tiles to Avo.-penalty tiles"). Corrin then 48 -> 38, Nyx (14,12) Fimbulvetr
  with Corrin's dual -> 23, Leo (12,12) Brynhildr (forecast kill, 83%) killed Ryoma. No unit took damage all chapter.
  Stage complete 53566 (4 turns), banner + talk (ban25.json, until ChapterFileMenu, 64028), save slot 1 (sv.json),
  castle 64514 (chapter B026, not the Endgame). 16 of 16, nobody lost.
- **Long moves** need `MW=600-900` in act2 (the default 80-frame wait stops on map__ProcMoveRoute; the stop is undone).
- **The route** `cheat-cq-ch25` (tools/wroute25.py, splitcfg.merge, only this key; routes/markers compared before and
  after): save cheat-cq-ch24-clear, frames 64530, save_at 64520, 1,159 presses, 8 pokes, 20 checkpoints, verified false.
  `cheats.py --check` 15 cheat routes, rules OK; `--selftest` 23/23.
- **Replay checks** [high]: boot-server from frame 0 with the pokes (tools/chk4.py, chk25.out): cycles at 64514 =
  289096007904, equal to the chain's; units 16 at every map checkpoint. `parallel.py runs --route cheat-cq-ch25
  --markers` (session r37-cqx25-markers, FEF_ROBOT_JOBS=4, 2.64 GB, below normal): PASS, exit 0, Completed after 64530
  frames, **checkpoints all met**, memory d639641062f7591e, instructions 289167706080, boot 240 s, peak 787 MB,
  %APPDATA% unchanged. The two-copy proof and the clear save `cheat-cq-ch25-clear` are a separate step.
- **Proof (round 37, r37-proof-cheat-cq-ch25, 14:25-14:31):** both copies exit 0, 64530 frames, memory
  d639641062f7591e, 289,167,706,080 instructions, checkpoints all met; `cheat-cq-ch25-clear.zip` packed (cheat mark,
  8 pokes); capture r37-cap-cheat-cq-ch25 5,101 records, 0 bad (kept no records); verified true.

Wall time: 13:50 start, castle 14:14 (**about 25 min of play**, cap 100); export, frame-0 replay, route, marker run and
docs to about 14:27 (about 37 min in all).

#### 3z-cq26. Conquest chapter 26 CLEARED on the cheat track (`cheat-cq-ch26`), no new poke [high unless tagged]

Fresh helper, cap 100 min of play. Chain `build/speed/cqx26/c` (`new c --save cheat-cq-ch25-clear --cheat`; tools = cqx25's
set, `MAPFILE` B026.bin.lz). Opening: p0 (abs to 4400, Preparations), plans/open26.json (B, START, UP A, A, LEFT A, talk
until the sortie menu 10884, answer on), st.json, ok.json (11362). **No poke**: r35rd.py at 11362 showed all 16 (Benny,
unit 39, included) already carry the move bonus 60 and the HP/Def/Res boost from the cheat start save. It is a cheat route
only because it starts from a cheat save.

| | Chapter 26 'Treason' (B026) |
|---|---|
| Win rule | Seize the throne (13,19) (TrickData type 3) where the boss Iago (Sorcerer lv 20, 45 HP, Excalibur, Freeze/Enfeeble/Silence staves) stands; his room (9-18, 18-20) opens only by the door (13,21) from the south room |
| Start | 16 in the north room (9-18, 1-9); 35 enemies: 6 Heroes in the middle room, Faceless + 2 Golems west, sorcerers + maids east, Hans + Berserkers + Generals in the south room; 10 doors (type 9), 5 chests (type 10) |

- **Doors** [high]: only Shura (Adventurer) and Niles (Outlaw) get the Door command; one door per action. Other units get
  'Break' (Xander: 7 of the door's 50 HP, undone). Route used (east): (13,10) -> (19,12) -> (22,19) -> (23,23) -> the
  south room's (20,25) -> the boss door (13,21). danger.py / near.py do not know opened doors (near.py showed everyone
  shut in); trust the screen.
- **Enemies block** [high]: braziers (type 'c') split the middle room, so one enemy on (15,12) cuts the east side off
  (Shura's move stopped twice; Odin and Camilla could not leave on turn 5 until that Faceless moved). Generals step into
  the open door (20,25) every enemy phase. The boost holds: Heroes, Generals, Sorcerers did 0; the Faceless did 34 to
  Niles on turn 1, Azura took 20 + 6 (77 -> 51), nobody fell.
- **Against Iago** [high]: axes 17-42% hit (Harold's hand/iron axe undone); Gunter's Steel Lance (Y twice in the
  forecast) 92%; Camilla's 35% axe missed (9 from the dual strike). Five units hit him from (12,19), (13,20), (13,18),
  (12,20), (14,20); Leo's Brynhildr (81%, forecast kill) finished him.
- **Turns** [high]: T1 Shura (13,10), Niles (8,12), Heroes; T2 Hero (15,12) killed, Shura (19,12), Niles (22,19); T3
  Shura (23,23), Niles (20,25), Elise and Felicia healed Niles; T4 General in the door, Hans (Xander from range 2 at
  (16,22), Azura sang; Aurgelmir went to the convoy: DOWN x5 A, LEFT A); T5 General in the door, Faceless to 2,
  Berserker (19,25) killed; T6 Shura opened (13,21), Iago killed, Corrin seized (13,19). Stage complete 123940 (6 turns,
  heroes Felicia & Leo; the screen's class is `castle__anonymous_namespace__Seq` at once, so seize.json's `until` timed
  out and was rolled back: wait 1500 instead, `map__SequenceCompleteEffect` is then in the classes), banner A + talk
  (plans/ban26.json, ChapterFileMenu 128022), save slot 1 (sv.json), castle 128378 (chapter B027, not the Endgame).
  16 of 16, nobody lost; no enemy phase rolled back. Rollbacks: single actions undone before their confirm, and one
  undo to the turn 2 start (22120) after a stray A on an empty tile (it also dropped Xander's first turn 2 attack); the
  exported press list then replayed from frame 0 to the same cycles (below).
- **The route** `cheat-cq-ch26` (tools/wroute26.py, splitcfg.merge, only this key; routes/markers compared before and
  after: only this key added): save cheat-cq-ch25-clear, frames 128394, save_at 128384, 1,420 presses, 0 pokes, 21
  checkpoints, verified false. `cheats.py --check` 16 cheat routes, rules OK; `--selftest` 23/23.
- **Replay checks** [high]: boot-server from frame 0 (tools/chk4.py, chk26.out): cycles at 128378 = 575279277408, equal to
  the chain's; units 16 at every map checkpoint, enemies 35 -> 27. `parallel.py runs --route cheat-cq-ch26 --markers`
  (session r37-cqx26-markers, FEF_ROBOT_JOBS=4, 2.64 GB, below normal): PASS, exit 0, Completed after 128394 frames,
  **checkpoints all met**, memory 67190ee9f1126f00, instructions 575350975584, boot 669 s, peak 648 MB, %APPDATA%
  unchanged. The two-copy proof and the clear save `cheat-cq-ch26-clear` are a separate step.
- **Proof (round 37, r37-proof-cheat-cq-ch26, 15:32-16:17):** both copies exit 0, 128394 frames, memory
  67190ee9f1126f00, 575,350,975,584 instructions, checkpoints all met; `cheat-cq-ch26-clear.zip` packed (cheat mark,
  0 pokes); capture r37-cap-cheat-cq-ch26 4,121 records, 0 bad (kept no records); verified true.

Wall time: 14:37 start, castle 15:10 (**about 33 min of play**, cap 100); export, frame-0 replay, route, marker run and
docs to about 15:33 (about 56 min in all).

#### 3z-cq27. Conquest chapter 27 CLEARED on the cheat track (`cheat-cq-ch27`), no new poke [high unless tagged]

Fresh helper, cap 100 min of play. Chain `build/speed/cqx27/c` (`new c --save cheat-cq-ch26-clear --cheat`; tools = cqx26's
set, `MAPFILE` B027.bin.lz). Opening: p0 (abs to 4400), plans/open27.json (= open26: B, START, UP A, A, LEFT A, talk until
the sortie menu 14574), st.json, ok.json (15052). **No poke**: r35rd.py at 15052 showed all 16 already carry the move bonus
60 and the HP/Def/Res boost from the cheat start save. A cheat route only because it starts from a cheat save.

| | Chapter 27 'The Empty King' (B027) |
|---|---|
| Win rule | Defeat the boss Garon (Empty Vessel lv 40, 65 HP, Bolverk range 1-3, AI_MV_Null) on the throne (15,1) (throne: heal 20, def 3, avoid 30) |
| Start | Corrin's 10 at the south end (13-17, 29-30); Camilla, Elise, Xander, Shura, Benny, Leo one each in the six side rooms; 17 enemies: 3 Lancers (lv 40) and a Merchant plug the corridor (14-16, 8-9); one champion + one shrine maiden in each side room; stairs (type 28) side room <-> hall (13/17, 8-10), side-room doors (type 9) |

- **The way in** [high]: the side rooms join the hall through the pillar tiles, so with the move bonus everyone reaches the
  plug on turn 1; only row 7 (14-16) leads to the boss room, so one corridor enemy must die. Leo (13,9) Brynhildr took the
  Lancer (14,8) 47 -> 30 (the Lancers hurt the attacker back even at range 2: Leo 96 -> 79), Camilla (13,8) steel axe
  (81%) killed it. No stairs were needed.
- **Garon** [high]: damage to him is about halved: Xander's Siegfried 9-10 a hit (77%), Leo 8, Corrin 1 (6 with Leo's dual
  strike), Gunter 1, Nyx 2, Odin, Shura, Niles, Harold, Benny 0. He heals 13 a turn on the throne and never moved; his hits
  on our boosted units were 0-12. Way that worked: Xander on (15,2) (Siegfried reaches 2), Azura on (15,3) sings him every
  turn (two Xander attacks), and range-2 units on (14,2)/(16,2) next to Xander, so each of their attacks brings Xander's dual
  strike (about 4). Garon 65 -> 42 (turn 1) -> 54 healed, -> 14 (turn 2) -> 27 healed, turn 3 Xander, Leo (dual), Azura's
  song, Xander's forecast kill (97%): stage complete 69526, 3 turns, 16 of 16, nobody lost, no rollback of any turn.
- **After the boss** [high]: banner (A), talk (540 answered presses), then straight to the **Endgame preparations**
  (sortie TopMenu, chapter B028, "Defeat the boss", 16 of ours / 22 enemies) at 89278. No save question and no castle, as
  docs/collab/FINALES_GROK.md says; the route ends there (89424). Chain end for the finale: build/speed/cqx27/c at 89408
  (copies c_t3_prekill, c_complete).
- **The route** `cheat-cq-ch27` (tools/wroute27.py, splitcfg.merge, only this key; routes/markers compared before and
  after: only this key added): save cheat-cq-ch26-clear, frames 89424, save_at 89414, 1,515 presses, 0 pokes, 11
  checkpoints, verified false. `cheats.py --check` 18 cheat routes, rules OK; `--selftest` 23/23.
- **Replay checks** [high]: boot-server from frame 0 (tools/chk4.py, chk27.out): cycles at 89408 = 400649407488, equal to
  the chain's; units 16 at every map checkpoint, enemies 17 -> 15. `parallel.py runs --route cheat-cq-ch27 --markers`
  (session r37-cqx27-markers, FEF_ROBOT_JOBS=4, 2.64 GB, below normal): PASS, exit 0, Completed after 89424 frames,
  **checkpoints all met**, memory 4fcd68e281abd835, instructions 400721105664, boot 383 s, peak 591 MB, %APPDATA%
  unchanged. The two-copy proof is a separate step; no clear save exists after chapter 27 (the Endgame route starts from
  cheat-cq-ch26-clear frame 0 with these presses as its prefix, like cheat-bt-endgame).
- **Proof (round 37, r37-proof-cheat-cq-ch27):** both copies exit 0, 89424 frames, memory 4fcd68e281abd835, 400,721,105,664
  instructions, checkpoints all met; capture r37-cap-cheat-cq-ch27 3,822 records, 0 bad; verified true. The zip the
  proof packed was byte-identical to cheat-cq-ch26-clear (no save after chapter 27) and was set aside as
  build/parallel/r37-proof-cheat-cq-ch27/cheat-cq-ch27-clear.NOT-A-CLEAR-SAVE.zip; check_all `cheat-endgame` now lists
  cheat-cq-ch27 and cheat-cq-endgame and fails if a clear zip comes back.

Wall time: 16:17 start, Endgame preparations 16:47 (**about 30 min of play**, cap 100); export, frame-0 replay, route,
marker run and docs to about 17:06 (about 49 min in all).

#### 3z-cqend. Conquest Endgame on the cheat track (`cheat-cq-endgame`, F-030/F-033/F-036), ENDING REACHED [high unless tagged]

- **Counts as Conquest played to the end** (F-030/F-031), cheat table (F-019 rule 2). Own folder build/speed/cqend:
  chain **ce** = a copy of cqx27/c (frame 89408, Endgame preparations; state.bin sha256 b520af60... equal); cqx27 and its
  chain not changed. Tools = cqx27's copies with paths moved to cqend (`MAPFILE` B028.bin.lz). FEF_ROBOT_JOBS=4 (2.64 GB),
  below normal. Played 17:22 to 17:38 (**about 16 min**).
- **Save check first (F-029):** the preparations menu (Select Units, Inventory, View Map, Equip Skills, Fight!, Exit) has
  no Save. So the route starts from cheat-cq-ch26-clear frame 0 with cheat-cq-ch27's 1,515 presses as its prefix
  (checked equal; ch27 has no pokes), like cheat-bt-endgame and cheat-rv-endgame.
- **Fight!:** START opens 'Start the battle?' with the cursor on **No** (one A on No went back to the menu, harmless and
  recorded); START, LEFT, A; the opening talk (A); the objective card 'Victory: Defeat the boss' waits for a key (A).
- **Map (B028, 'Night Breaks Through'), turn 1 (91472):** 16 of ours in the north (13-17, 3-6), all still carrying the
  move bonus 60 and the HP/Def/Res boost from the cheat start save; 22 enemies. The boss **Takumi** (person 31232, Sniper
  lv 20, 60 HP, Skadi) is at (15,29) in the south, paired with a second unit of the same person (the "copy"). who.py: with
  the move bonus every unit can reach a tile next to him on turn 1.
- **The poke (one, nothing else):** frame 91472 (turn 1 player phase, read before the poke): `unit:31232 +0xF3` (current
  HP, as cheat-bt-endgame), size 1, 60 -> 1, expect 60; `unit:31232` = the first unit of that id = 0x3262A090, the
  **front** unit (the forecast showed Takumi 1/60); the paired copy 0x3262BAD0 stayed 60 and was **not poked**. Made in
  the look-ahead by tools/poke.py (cheats.apply: "linear heap (page checked)", address 0x3262A183). Tried first on a
  scratch copy (cet), then on ce.
- **The kill:** Xander (Siegfried) moved (13,6) -> (15,28) (a 22-tile move; act2 needs MW=400 for the move to finish),
  Attack: forecast Takumi 1/60, Xander 94% hit, kill mark, Takumi 100% with "Support!" from the copy. Xander's first hit
  killed him. No enemy phase, **16 of 16 alive** (all 16 back in the pool with HP unchanged, Xander lv 16 -> 17),
  **nothing undone**. Like Birthright, **no stage-complete banner**: the map hands straight to the ending (ProcResDelayBind
  at 94290).
- **After the boss** (screens read by tools/chkE.py on boot-server from the ch27 chain state with the poke applied the
  route way, chkE.out; cycles at 89408 = 400649407488 = the chain's):

  | Frame | Screen |
  |---|---|
  | 94290 | Takumi beaten, ProcResDelayBind, units [0, 0, 0] (map closed) |
  | 94890 | the ending events (TalkUtil, answered with A; long talk to about 107200) |
  | 107220 | an ending movie (ProcMovie): START (as Birthright's movie screens) |
  | 107282 | the chapter records (ProcSequence@00626B48) |
  | 140000, 160000 | the epilogue cards and staff credits (ProcEpilogue@0062695C) |
  | 180000 to 197282 | **'The End'** (ProcEffect, ProcSequence@006269E8). It waits for a key (A at 197292). Not a hang |
  | 197434 | the logbook card entry: "You can select 5 more"; A on OK |
  | 197586 | "Would you like to proceed?" (cursor on No): LEFT, A |
  | 198090 on | **the title screen "PRESS ANY BUTTON"** (ProcSequence@00640B64, chapter NONE), the first stable screen; unchanged to 198700 |

  **Where the game lands:** the title screen. No save prompt, **no hang, no crash**. The same shape as Birthright and
  Revelation.
- **The route** `cheat-cq-endgame` (routes.json, markers.json; checked read-modify-write of only this key with
  splitcfg.merge, build/speed/cqend/tools/wrouteE.py; before/after compare: only this key added): `"cheat": true`, save
  cheat-cq-ch26-clear, frames 198700, save_at 198690 (schema only; no clear save exists or is packed), **1,994 presses**,
  **1 poke**, **14 checkpoints** (ch27's 89278 and the 13 frames above plus 90390, 91472, 92880). `cheats.py --check` 19
  cheat routes, rules OK; `--selftest` 23/23.
- **Two-copy proof** (`parallel.py runs --route cheat-cq-endgame --copies 2 --markers --session r37-proof-cheat-cq-endgame
  --timeout 6000`, FEF_ROBOT_JOBS=4, below normal, 17:43 to 17:58): **PASS**, both copies exit 0, Completed after 198700
  frames, **memory cd5d0d3dca2b7e5b, instructions 890,401,723,200 in both**, checkpoints all met, peak 814 MB; the poke
  went to 0x3262A183 (60 -> 1) in both; %APPDATA% unchanged. The instruction count equals the boot-server read at 198690
  (890356911840) plus 10 idle frames.
- **Capture from frame 0** (`parallel.py runs --route cheat-cq-endgame --mode capture --only all --store-keep --markers
  --session r37-capc-endgame --timeout 6000`, same time, below normal): **PASS**, exit 0, Completed after 198700 frames,
  checkpoints all met, memory cd5d0d3dca2b7e5b (= the proof), **179 functions, 5,972 records (5,814 match, 93 gave up,
  65 incomplete), 0 bad of any kind**; no writer stored anything; %APPDATA% unchanged. [medium] `build.py --check-fresh`
  said STALE only because of another round's uncommitted writer edits in src/readable/menu/ (the same reason as round 36);
  the library was not rebuilt, so another area's unfinished code was not put into this capture.
- `verified` set **true** (checked rewrite of only this key). The machine also ran 6 zakuro-test boot.exe of another
  round at the same time; both runs still took about 15 min.
- Wall time: 17:22 start, title screen reached in the chain 17:38, route written 17:42, proof and capture 17:43 to 17:58,
  docs to about 18:00 (**about 40 min of a 90-minute cap**). No commit.

## 4. Capture and replay (one short capture)

- `title`: no readable function is called before the title; capture.c starts on the first call, so
  capture A wrote nothing. h4a now says so and stops after the fidelity step (exit 1, not a pass).
- `new-game` h4a: **PASS**. Determinism (original twice) identical; capture A identical memory and
  instruction count, 3 functions met, 10 records faithful, 0 unfaithful; capture A+B identical;
  report PARTIAL 1 (`unit_weapon_exp_limit`, 1 gave up of 8), SHALLOW 2 (`weapon_level_record`,
  `unit_pool_first`, one call each). No record mismatched, so h4a kept none.
- Kept records for the offline replay: run `ng-store` (store keep, only those 3 functions): 10
  records. Offline replay **original vs original: match 10 / 10, nothing else** (clean). Readable:
  match 9, gave_up 1 (the same give-up as live).

Stage B (library fresh, 35 overrides: pilot, stances, weapon triangle, dragon veins, AI):

| h4a route | determinism | capture A | live A+B (shadow compare) | verdict |
|---|---|---|---|---|
| `bt-prologue` | identical, 213,346,885,008 instructions | identical, 27 functions, 457 faithful, 0 unfaithful | 458 records, 454 match, **0 mismatch**, 3 gave up | **PASS** |
| `bt-ch2` (Attack Stance) | identical, 89,801,965,440 | identical, 24 functions, 461 faithful | 461 records, 458 match, **0 mismatch**, 3 gave up | **PASS** |
| `bt-ch3` (vein, pair) | identical, 153,434,096,640 | identical, 30 functions, 592 faithful | 593 records, 587 match, **0 mismatch**, 5 gave up | **PASS** |
| `bt-ch6-castle` | identical, 146,264,279,040 | identical, 23 functions, 391 faithful | 391 records, 387 match, **0 mismatch**, 4 gave up | **PASS** |
| `bt-castle-shop` (round 3) | identical, 45,976,455,360 | identical, 15 functions, 319 faithful | **0 mismatch** (no record kept) | **PASS** |
| `bt-ch7` (round 3) | identical, 425,707,920,000 | identical, 46 functions, 1016 faithful, 0 unfaithful | 2 functions MISMATCH (see below), all others 0 | **PASS** (h4a exit 0) |
| `bt-ch8-support` (round 3) | identical, 47,186,362,080 | identical, 14 functions, 280 faithful | **0 mismatch** (no record kept) | **PASS** |
| `bt-ch8-pair` (round 3) | identical, 43,915,132,800 | identical | 2 functions MISMATCH (the same two), all others 0 | **PASS** (h4a exit 0) |

Round 3 (library rebuilt 2026-11-12 01:02, FRESH for all four; it now stages 56 overrides: the committed 35
plus 21 uncommitted formula rows of another workflow, src/readable/battle/formula_*.c). Every committed
override met in round 3 had **0 mismatches**. The two MISMATCH functions are both new, uncommitted rows:
`unit_hit` 0x00532DC4 (bt-ch7: 5 match, 11 mismatch_calls, 1 gave up; bt-ch8-pair: 6 / 9 / 1) and `unit_attack`
0x00534188 (8 / 12; 6 / 11): r0 and memory always agree, only the list of calls the readable code makes
differs (mismatch_calls). A finding for the formula track, not a route problem; h4a passed then (MISMATCH
records were findings; since round 6 h4a FAILS on any bad live record, as `parallel.py` capture runs do). replay.exe was stale (formula sources newer), so their kept records were not
replayed offline. `stance_guard_bonus_edit` is now **met**: `bt-ch8-pair` 23 records, 23 match, REPLAY-CLEAN.
It runs only when the pair's support has the avatar's edit data (Unit::GetDoubleCapability 0x00530A34 tests
Unit+0xB0 before calling PersonEnhanceDouble::GetEdit at 0x00530B58), so Corrin had to be the support,
never the lead as in every earlier pair. Committed overrides met over all h4a runs: **33 of 35**; still not
met: `ai_value_is_signal` (its only caller is AIThink::ActionMoveForce 0x004CA8A4, behind a skill-mask test)
and `script_unit_can_dragon_vein` (a script command; no chapter so far called it).

Stage B merged report (these four plus `new-game`): 32 of the 35 overrides met (PARTIAL 10, REPLAY-CLEAN 7,
SHALLOW 15); not met: `ai_value_is_signal`, `stance_guard_bonus_edit`, `script_unit_can_dragon_vein`.
Met with 0 mismatches on game state: every stance function except `stance_guard_bonus_edit`
(`stance_attack_bonus_total/edit`, `stance_guard_bonus_total`, `unit_attack/guard_stance_bonus`,
`unit_guard_stance_move`, `unit_can_pair_with`, `situation_can_dual`), the triangle tables
(`weapon_interact_record`, `weapon_bonus_record`) and the vein code (`vein_command_attribute`,
`unit_can_dragon_vein`, `trick_is_access`, `script_trick_test`). `bt-ch4` and `bt-ch5` were not captured.

Kept records replayed offline (store keep, only the 15 stance / triangle / vein functions):

| run | records | original vs original | readable |
|---|---|---|---|
| `st-bt-ch2` | 163 | match 163, nothing else (clean) | match 162, gave_up 1, 0 mismatch |
| `st-bt-ch3` | 252 | match 252, nothing else (clean) | match 249, gave_up 3, 0 mismatch |

## 5. Times (this PC, RTX 3080) [high]

| Step | Time |
|---|---|
| boot.exe (`build.py --boot`, first build of the example) | 105 s |
| capture library (`build.py`, the whole game) | 314 s, again 292 s |
| `title` run, 3000 frames | 4.4-5.3 s (original), 4.7 s (capture) |
| `new-game` run, 4600 frames | 8.2-8.7 s (original), 8.7-10.0 s (capture A / A+B) |
| marker run (5-6 dumps of 56 MiB) | 6.7-11.5 s |
| intro movie not skipped (6000 frames) | 36 s (the movie is the slow part) |
| h4a `new-game` (4 runs, compare, report) | 97 s |
| finding the 9 inputs of `new-game` | 10 probe runs, about 15 minutes with reading the sheets |
| bt-* route, original, from its start save | 46 s (20k frames) to 107 s (47.6k frames), about 2.2 ms per frame |
| bt-* marker run (5-9 dumps) | 46-103 s |
| h4a on a bt-* route | about 4 x the route time (3-7 minutes) |
| savestate look-ahead step (load, 100-400 frames, shot) | 1-6 s; with a 56 MiB marker dump about 5 s |
| one unit action with the helper (select, move, act, settle) | 40-60 s |
| finding Prologue to castle (stage B) | most of one session |
| round 3: bt-ch7 marker run, 95,000 frames | 203 s (2.1 ms per frame); h4a on it about 15 minutes |
| round 3: look-ahead step after the speed fix | about 2.6 s for a 90-frame autopilot segment with markers (4 in 10.3 s); every step decodes one 141 MB state, 0.8 s now instead of 6 s |
| round 3: finding shop + chapter 7 + support | one session; chapter 7 alone about 60 helper actions |
| round 4: chapter 8 look-ahead (16 turns, about 45 helper actions) | most of one session; an end turn with `robot/et2.py` 15-60 s |
| round 4: `bt-ch8` marker run, 78,900 frames | 222-225 s (2.8 ms per frame, 8 dumps of 56 MiB) |
| round 4: `bt-castle-forge` marker run, 12,600 frames | 22-24 s |
| round 4: all ten earlier bt-* marker runs, 6 at once | 498 s wall (the ten one after another: about 2,000 s), peak 606 MB per run |
| round 5: chapter 9 look-ahead (19 turns, about 110 helper actions, many retries at the boss) | most of one night session |
| round 5: castle part (lottery, armory, smithy; walking by bottom-map position) | about 1.5 hours, mostly walking |
| round 5: `bt-ch9` / `bt-ch9-ore` marker runs, 147,400 / 162,800 frames | 553-556 s / 585-591 s, both side by side |
| round 8: chapter 10 look-ahead (17 turns, about 60 helper actions) | about 2.5 hours, mostly waiting on runs |
| round 8: chapter 11 look-ahead (17 turns, about 70 actions with `march.sh`) | about 3 hours |
| round 8: `bt-ch10` / `bt-ch11` marker runs, 129,000 / 141,000 frames | 344 s / 522-550 s (one at a time: the 2.7 GB budget fits one 1.5 GB estimate) |
| round 8: capture runs of the same | 433 s / 577 s |

Round 3 speed fix (headless.py, profiled with cProfile on a real 141 MB title state) [high]: after boot.exe
stopped, `state_sections` took 6.0 s per state (FCRAM alone is 128 MiB) and keep_meta decoded it a second
time. 49 million of the calls were `min()` in the LZ4 overlapping-match loop: a run of zero bytes (offset 1)
was copied one byte per step. Now an overlapping match is written as its period repeated, a run of 255
length bytes is skipped with one regex match, `len(out)` is kept by hand, and run() decodes once for both
the digest and keep_meta. Decoding: **6.0 s -> 0.77 s** (byte-identical sections, compared with the old
decoder on the same state); the whole after-game work of a new-game marker run is about 1.4 s. Same results:
`parallel.py determinism --copies 3` on `title` (memory `c3cbbe48...`, 13,443,408,000 instructions),
`new-game` (`d328d671...`, 20,613,225,600) and `bt-ch2` (`059736d3...`, 89,801,965,440): DETERMINISTIC each,
every hash equal to the committed runs'. headless self-test 60/60 (two new LZ4 cases: a period-3 overlap with
several 255 length bytes, a long zero run).

## 6. What is not done

- Round 8: chapters 12-14 not done (chapter 12's start state and map facts in 3e). The Kaze-Hana and Felicia-Saizo B
  talks were viewed only in the chapter-12 look-ahead, not in a route. In `bt-ch11` five units retreated (Casual);
  they are back in bt-ch11-clear's army list. `veins_used` 2 in chapter 10 without a player vein is not explained.
  The capture library was STALE (targets.csv) and has no writer totals: the integrate stage's rebuild and live compare
  are still to run on the two new routes.

- Round 7: H6 on game records catches 47.5% of planted bugs on real play (docs/harness/H56.md), under the 90% gate:
  F-017's writers stay off. The survivors are 352 test gaps and 578 value gaps (none hand-reviewed for equivalence).
  The options route is look-only: every option has this save's one value, so `config_ai_skip_value` and
  `config_distance_value` catch none of their planted bugs; other values need a route that changes options in the
  game's own screen (real play, then a save) or a cheat route. Any map-menu visit moves the general random at
  0x00752B7C and so the later enemy moves (3d); not traced which code draws from it. The store-keep records (231 MB
  real play, 47 MB cheat) stay in build/parallel/r7-h5*/records/ for a rerun of H5/H6 after code changes
  (`parallel.py clean` removes them).

- Round 6: `cheat-skill-proc` and `cheat-family` stop mid-chapter with a battle save, which lives in the game's
  extra data (`parallel.py pack ... extdata`). `harness.py h4a` and `report` read only the last stage's summary.tsv
  of a cheat run: score cheat routes with `parallel.py runs --mode capture`. The never-met readers of 3c's last
  table stay open. Hana's katana is +1 only on the cheat line; real play still has no Pearl.

- Row 7 (forge) is reached in round 5 with Coral and Subaki's naginatas; Hana's katanas (Pearl) are still +0:
  no Pearl came (the lottery is once a day; no ore spring is in the build list after chapter 9).
- Not met in real play: `unit_attack_for_terrain` and `..._of_slot` (need a breakable wall or ruin),
  `script_unit_can_dragon_vein` (Revelation/Conquest scripts only), the three family readers (a child unit),
  `ai_value_is_signal` (section 3b; met since, bt-ch4, 17 records). The Units list (the other caller of the four
  slot forms) is opened in a route since round 7 (`bt-ch8-options`, 3d).
- Castle walking is by the bottom map's player marker and screenshots (walk.sh); a castle unit's "!" talk was tried
  and not reached (A opened Preparations twice); the gift event stays untested.
- `levels` counts Corrin's raw stats without the avatar's boon/bane edit (unit::Edit); the level, experience and
  gains are exact.
- No capture (h4a) of `bt-ch9` or `bt-ch9-ore` was run in round 5 either (the library was not rebuilt: another
  stage is changing src/readable); the integrate stage does the live compare.
- No capture (h4a) of `bt-ch8` or `bt-castle-forge` was run in round 4: the capture library was not rebuilt
  (another workflow is changing src/readable); the integrate stage does the live compare.

- Two committed overrides never met: `ai_value_is_signal`, `script_unit_can_dragon_vein` (see 4; the second is not on Birthright at all, 3b).
- bt-ch7 and bt-ch8-pair h4a: two MISMATCH functions in the uncommitted formula overrides (see 4).
- Row 9: the support read counts pairs at C (`support_c`); which pair is which is not named in run.json
  (tools/harness/robot/rel.py prints names and points from a look dump).
- Row 11: the ally strike is shown on the contact sheet and the stance code ran (0 mismatches), but no
  memory read names "the follow-up hit" yet (BattleInfo / the battle log).
- Row 3: the route byte is 0 both before and after the choice (0 is also its starting value); the
  choice is shown by the dialog, the Hoshidan cast of the next map and the Dawn Armory. Reading which
  chapter file loaded (Scripts/A) was not done.
- In `bt-castle-shop` the first building is the Rod Shop, so on this save line there is no armory (row 6
  stays reached by `bt-ch6-castle`; a Dawn Armory can still be built with the chapter-7 DVP).
- `bt-ch4` and `bt-ch5` have marker runs but no capture; `harness.py smoke` is still open (stage A).
- The library goes STALE whenever src/readable/ changes (another workflow edits it); h4a refuses a
  stale library, so rebuild (5 minutes) right before an h4a. It was FRESH for every stage B h4a.

## Round 9: bt-ch10 `veins_used 2` traced (2026-11-14)

Question from round 8: in `bt-ch10` the markers read `veins_used 2` but no player unit used a vein. Traced on a
boot-server replay of the verified route's recorded presses (nothing new played; 417 s + a 500-frame scan):
chapter 10 has 3 dragon veins (TrickData type 11) at (11,7), (15,7) and (7,6), all state 1 (usable) at 8390 and
9980. (7,6) turns to state 2 between frames 49980 and 50480, (15,7) between 72480 and 72980; (11,7) stays 1 to the
end. Both changes happen while `map__SequenceHuman` (the player phase) is current, no `map__trick` ProcMutation is
live at the window's end, and **no unit stands on or next to either vein**; the node's word at +4 is cleared at the
same time. So the veins were not used by a unit: something else (most likely the chapter's own turn events)
switched them off. The marker read is right about memory; its name was wrong about the cause. **Meaning from now
on: `veins_used` = veins whose usable bit is cleared (used or switched off), not "veins a unit used".** Proof of a
unit's vein use stays the `map__trick__anonymous_namespace__ProcMutation` class at the frame (as for `bt-ch3`).
Nothing in markers.py's numbers changes, so every recorded checkpoint stays valid. Not traced further: which
script call clears them (needs the chapter's event code; no game text read).

## Round 9 integrate (2026-11-14)

- `cq-ch8` (Conquest chapter 8, 140,000 frames from cq-ch7-clear): the cq area played it but left
  before its proof (its replay logs were empty). Integrate replayed it with two ORIGINAL boot.exe
  copies (session i9-cq8): both exit 0, memory 6897aa6ad14873c2 in both. Packed as
  build/harness/saves/cq-ch8-clear.zip (sha256 5151dbe5...; Chapter0 4,868 bytes vs 4,268 in
  cq-ch7-clear, so the in-game save did happen). Capture run r9-capq: same memory, 99 functions met,
  2,187 records, 0 bad. **Still `verified: false` and no checkpoints**: markers.json `cq-ch8` is the
  cq area's key; it adds the checkpoints and flips verified next round.
- Live capture of all 26 verified real-play routes with today's library (session r9-cap): every run
  PASS, every checkpoint met, every memory hash equal to its stage's claim (bt-ch12 c6f70ba7,
  rv-ch9 7c408510, cq-ch7 / rv-ch7 / rv-ch8 first compared this round).
- Wall time per chapter this round: bt-ch12 74 min, rv-ch9 ~210 min, cq-ch8 ~90 min look-ahead +
  34 min proof (by integrate). Round 8: ~1-2 h per chapter.

## Round 10 integrate (2026-11-15)

- **Chapters this round (fresh helper per chapter, owner OK 2026-11-14):** Birthright 13-17 (3g-3k),
  Revelation 10-14 (docs/ROUTES_SPLIT.md 10, 12-16), all proven by their helpers with two ORIGINAL boot.exe
  copies and packed. Conquest 9 was played to the end by the cq helpers (chain q9g, build/speed/r9-cq9) but
  neither helper's proof finished.
- **cq-ch9 finished by integrate.** Two ORIGINAL copies (session i10-cq9, FEF_ROBOT_JOBS=2): both exit 0,
  123,500 frames, memory **bf1c69255758cc0b** in both (705 s / 712 s). The two copies' in-game saves are
  byte-identical; packed as build/harness/saves/cq-ch9-clear.zip (sha256 6e6c5d99...; Chapter0 and Global
  differ from cq-ch8-clear, so the slot-1 save happened). Checkpoints read from that proof at the route's
  shots and written with splitcfg.py (`marks cq-ch9`, 8 checkpoints): turn 1 [9, 17, 1]; the green unit joined
  [10, 10, 0]; [10, 6, 0] and [10, 9, 0] (reinforcements); turn 28 [10, 5, 0]; STAGE COMPLETE [10, 5, 0]
  (seize, all 10 units); the save question (chapter B010; `GameDialogYesNo`, not `ChapterFileMenu` as the
  helper guessed); My Castle. Checked by two more runs from frame 0: i10-cq9cap and r10-capb (below), both
  with every checkpoint met. Then `verified: true` (splitcfg.py `route`). Nobody lost: 10 units from the join
  to the stage-complete screen.
- **rv-ch10..rv-ch14 `verified: true`.** The rv helpers proved them but never set the flag (the rv-ch10
  reviewer noticed). Set by integrate with splitcfg.py after the live compare below gave every one its
  claimed memory hash with all checkpoints met.
- **Live compare, first try (session r10-cap, 37 routes, library with all 203 overrides):** every run exit 0,
  every memory hash as before or as its helper claimed, every checkpoint met, no writer stored anything; but
  **866 bad records, all `mismatch_calls` in one new reader, `cursor_terrain`** (20-29 per route). Cause and fix:
  docs/MOVE.md 9 (an inlined tail branch; the readable code made a guest call the library's original does not
  make). The cq-ch9 capture (i10-cq9cap) showed the same 27 records.
- **Live compare after the fix (session r10-capb, 38 routes: the 37 and cq-ch9, all live, none offline):**
  38 PASS, 106,426 records, **0 bad of any kind**, every memory hash unchanged, every checkpoint met, writers
  stored nothing, %APPDATA% unchanged. 179 of 203 overrides met in real play. Cheat track apart
  (r10-capc, 4 routes): 8,395 records, 0 bad, 128 met.
- **Minutes per chapter (look-ahead start to packed save):** bt-ch13 53, bt-ch14 50 (39 + 11, two helpers),
  bt-ch15 74, bt-ch16 57, bt-ch17 36 (average 54; round 9 bt-ch12 74); rv-ch10 81, rv-ch11 83, rv-ch12 65,
  rv-ch13 83, rv-ch14 173 (88 + 85, two helpers; 45 turns, 389,600 frames) (median 83; round 9 rv-ch9 ~210);
  cq-ch9 about 2 h 15 min of look-ahead over two helpers, proof by integrate (12 min) [the helpers' own timings].
- **Kaze (person 7), traced from the r10-capb markers:** he is in the army list at every bt-ch15 checkpoint up
  to STAGE COMPLETE (frame 128,480; level 9, exp 1, unchanged all chapter, so he did not fight in it) and gone at
  the castle after the save (135,908), where person 5 appears instead; bt-ch16 and bt-ch17 start without him.
  So he was **not lost in a battle**: he left between the chapter-15 clear and the castle save. Which story step
  does it (and who person 5 is) is not traced [med].
- **Open for the next round:** the fastlook serve rollback bug (bt-ch16 notes: presses of passed
  steps not written to inputs.txt on a serve rollback; act2 undo does not reset the server) is not fixed;
  the 900 s floor that made a bt-ch13 review copy time out is fixed in parallel.py (PARALLEL.md round 10).

## Round 11 tools-fixes: the fastlook serve rollback (2026-11-15) [high]

**What really happened in bt-ch16** (re-read from build/speed/bt16/: serve.log, inputs-served-bad.txt and the
copied act2.py): the call from frame 12444 had step 0 (select and move) pass and step 1 stop at 12770.
fastlook did what it says: step 0's presses were recorded in inputs.txt and stayed in the server, step 1 went
back. Then act2.py saw "STOPPED" and ran its own `undo`, which copied chain.json / inputs.txt / state.bin back
from hist/ (frame 12444, without step 0). The server was not told: it stayed at the end of step 0 with step 0's
presses in its list. The next call started from the server's frame, so its presses begin at 12646 (the gap after
12444 in inputs-served-bad.txt) and inputs.txt lost step 0's cursor moves for good. So the presses were written;
an outside tool took them out of the files and not out of the server.

**Fix in tools/harness/robot/fastlook.py** (edited by temp file + rename; nothing else of the robot changed):
- Under `serve`, every request first compares inputs.txt and chain.json's frame with what the server last
  wrote (`Chain.mark` / `Chain.sync`). A rollback of the server's own presses (inputs.txt a prefix of the
  server's presses, every dropped press at or after chain.json's frame, every kept press before it, that frame
  not past the server's) takes
  the server back to that frame on the files' presses (`back_to`: a slot or the base, no save) and prints
  `note: files rolled back outside the server ...`. Any other outside change is refused, and `stop` then closes
  the server without saving (the files stay as the outside tool left them).
- `phase --whole` (request key "whole"): a stop takes the whole call back inside fastlook (inputs.txt as before
  the call, the server at the call's start; the passed steps are reported as `undone_steps`). A helper like
  act2.py should use it instead of its own file undo.

**Self-test** (`python tools/harness/robot/fastlook.py --selftest`, the fake server): 49 -> 58 checks, all ok.
New: the bt-ch16 sequence (step 0 passes, step 1 stops, the files put back from a hist/ copy, next call) checks
that the server's press list equals inputs.txt, that the new call's first press is at the files' frame + 10,
and the screen/frame; a foreign edit of inputs.txt under serve is refused; `--whole` one-shot and served.
Planted bugs: `sync` returning at once -> 4 checks fail; the `--whole` branch removed -> 4 checks fail.
Not done: no robot run (FEF_ROBOT_JOBS=0); act2.py copies in build/speed/ (scratch, not tracked) not changed.

**Review fix (same day).** The review found a hole: with chain.json's frame put back (to 20, after three
served phases) and inputs.txt left alone, `sync` took it as a rollback. The next call then ran at frame 112 while
the presses at 102 and 194 stayed in inputs.txt after the new frame, so the recorded line no longer matched what
was played. `sync` now also refuses when any press kept in inputs.txt is at or after chain.json's frame. With that,
"any other outside change is refused" is true for every case the review tried (its build/review-tf/guard_test.py
now gives refused for all three cases). The `stop` handling moved into `serve_stop(ch, s)` so the self-test can
reach it. New self-test checks (58 -> 68): each of the three refusals on its own (frame put back with inputs.txt
unchanged; inputs.txt cut with the frame left alone; the frame past the server's), a real rollback to 92 that is
followed and saved by stop, stop after a refused sync (no state.bin, chain.json and inputs.txt byte-for-byte
unchanged), and `--whole` leaving a stale cursor stale after an undone DOWN press (one-shot and served).
Planted bugs, all caught (build/speed/r11-fixes2/plant_fastlook.py): kept-press test removed 2 FAIL; dropped-press
test removed 1; frame-past-server test removed 1; stop saving after a refusal 1; `--whole` not putting the cursor
freshness back 2; `sync` disabled 9; `--whole` branch removed 6; `--whole` not restoring inputs.txt 2; `sync`
without `back_to` 3. The three refusal plants and the stop plant are each caught by exactly one check.

## Round 11 integrate (2026-11-15 night to 2026-11-16) [high unless tagged]

- **Chapters this round, all proven (two ORIGINAL copies) and packed:** Birthright 18-23 (3l-3q), Conquest 10-12
  and Revelation 15-17 (docs/ROUTES_SPLIT.md 18-23). From F-025 (owner "Apply now", Grok's strategy) the two-copy
  proof is its own step after the play: bt-ch23 (r11bt-23, 2 copies, memory c3b9075833eaee34, packed
  bt-ch23-clear.zip sha256 9384d55e...), cq-ch11 (p11cq11, 52154ebff72f0b57) and cq-ch12 (cq12p, 0dbf6a282590f10c)
  were proven that way; each proof step waited in the foreground to the end. Conquest and Revelation are now
  **paused** (F-025): cq-ch13 and rv-ch18 stay look-ahead chains with `verified: false` (build/speed/cq13,
  build/speed/rv18), not packed, never in robot-routes.
- **Compare (library rebuilt once, `build.py --swap`, 303 s, 234 overrides, FRESH).** `offline.py plan --sessions
  r10-capb --baseline-rev 0e8ddd7`: all 38 older routes may stay offline (inputs, saves, boot.exe unchanged); 203
  overrides decided by their records; 31 new (the 18 AI permission and 13 battle-number readers) must play live.
  - Offline (r11-off, 162 s): the 38 routes' 106,426 records through tonight's library: 0 bad, verdict = the
    captured one on every record (source gate passed). Cheat apart (r11-offc, 59 s): 8,395 records, 0 bad.
  - Live, new routes (r11-capn, every override, 12 routes, 2,705 s, 12 at once): 45,594 records, 0 bad of any kind,
    every memory hash equal to its proof, every checkpoint met, writers stored nothing.
  - Live, older routes, only the 31 new overrides (r11-capo, 38 routes, 4,923 s, at most 9 at once): 14,391 records,
    0 bad; every memory hash equal to round 10's r10-capb; every checkpoint met.
  - Cheat apart, 31 new overrides (r11-capc, 48 s): 543 records, 0 bad; memory hashes = r10-capc.
  - Per family (live + offline, real play): Birthright 29 routes 197 met 95,034 records; Conquest 7 (cq-ch6..12) 183
    met 25,587; Revelation 12 (rv-ch6..17) 188 met 43,778; options 2 routes 65 met 2,012; **0 bad in each**. All:
    50 routes, 166,411 records, 205 of 234 overrides met.
- **Measured.** Minutes per chapter, play (look-ahead to export) vs proof (two copies): bt-ch18 32+6 check / 9 (15
  lost on a 900 s timeout); bt-ch19 63+8 / 10; bt-ch20 ~66 in all (two helpers); bt-ch21 35+4 / 3; bt-ch22 58+4 / 9;
  bt-ch23 115 / 20 (first chapter with the proof as its own step); cq-ch10 64 / 21; cq-ch11 88 / 18; cq-ch12 105 /
  15; rv-ch15 85 / 13; rv-ch16 ~112 / 10; rv-ch17 ~110 in all. Birthright stays near an hour (median 66 min with
  proof, bt-ch23 the outlier: 27 turns); Conquest and Revelation 106-123 min, the reason for the pause.
  Idle robot compute in the compare: 33% of 12 slots x 122 min (the old-route run waited for the new-route run
  until I started it beside the tail at 00:20); check_all got 1 lane the whole time (the 12 robot slots took
  the budget), so it ran 138 min.

## Round 12 integrate (2026-11-16 morning) [high unless tagged]

- **Chapter this round:** Birthright 24 only (F-025: Conquest and Revelation stay paused; cq-ch13 and rv-ch18 stay
  `verified: false`, not packed, not played). bt-ch24 (3r): play 129 min in the look-ahead from bt-ch23-clear, 15 of
  15 units kept, Hans killed on turn 8; proof its own step (session r12-bt24-proof, 2 original copies, both 88,102
  frames, memory 86af3d4985d54014, 333 s), packed bt-ch24-clear.zip from copy 1, then one capture run on the
  library (r12-bt24-cap, 0 bad); routes.json bt-ch24 `verified: true`. robot-routes now asks for bt-ch24-clear.
- **Library:** `build.py --check-fresh` FRESH (built 2026-11-16T03:48:31 by the class-change capture step, 240
  overrides, 45 staged files): not rebuilt. Every batch capture and the bt-ch24 proof capture ran on this same
  library (sha256 475f58e96fd4...; checked in each run.json).
- **Plan (Grok's round 12 fixes; `offline.py plan --sessions r10-capb,r11-capn,r11-capo --extra-sessions "r12-cap-*"
  --label play --baseline-rev de846a6`).** PLAN LINE 1: 50 routes offline, 0 live. PLAN LINE 2: 238 overrides
  decided by records (4 class-change readers by the batch's own capture r12-cap-class_change on 47 routes), 2 left
  live (script_unit_weapon_rank, unit_weapon_exp_for_job_intro: "NEW: never captured"). Those 2 were watched in all
  54 runs of r12-cap-weapon_rank on this library and called 0 times (results/<run>.json `only` names both; no
  summary.tsv row names either); offline.py does not see that because a run with 0 records keeps no records/ folder
  (the tool gap the weapon_rank capture reported). So no route can reach them: they played live only inside the
  bt-ch24 run (every override), where they were not called either. `--baseline-rev de846a6`: the r11 records ran
  with de846a6's targets.csv; since 0e8ddd7 targets.csv only gained rows (none changed), so r10-capb's hooks are the
  same. Without it the plan took 9aa4ea6 and wrongly sent 107 overrides live. Cheat plan (r10-capc, r11-capc, extra
  r12-capc-*): 4 routes offline, the same 2 left (also 0 calls on the 4 cheat routes in r12-cap-weapon_rank).
  - Offline, real play (r12-off, 135 folders, 4 at once, 219 s): 168,591 records (164,642 match, 2,590 gave up,
    1,359 incomplete), 0 bad of any kind, offline verdict != captured verdict: 0, source gate passed.
  - Offline, cheat apart (r12-offc, 20 folders, 46 s): 9,039 records, 0 bad, verdict differences 0.
  - Live, bt-ch24, every override (`parallel.py runs --route bt-ch24 --mode capture --only all --store-keep
    --markers --session r12-capn`, FEF_ROBOT_JOBS=12): PASS, 867 s, 176 functions met, 3,908 records (3,786 match,
    49 gave up, 73 incomplete), 0 bad of any kind; memory 86af3d4985d54014 = the proof's; checkpoints all met; no
    writer stored anything; %APPDATA% unchanged. (The proof's capture of the same route took 217 s alone; this one
    ran beside check_all's 5 lanes and the offline replay, all below-normal.)
  - Per family, real play: Birthright 30 routes, 201 met, 100,122 records; Conquest 7, 186 met, 25,975; Revelation
    12, 191 met, 44,390; options 2, 65 met, 2,012; **0 bad in each**. All: 51 routes, 172,499 records (168,428
    match, 2,639 gave up, 1,432 incomplete), 208 of 240 met.
- **H5** (`h56.py h5 --sessions r10-capb,r11-capn,r11-capo,r12-cap-class_change,r12-capn --label play --run-id
  r12-h5 --no-exact --jobs 8`, tools-r12 lanes): 136 folders in 8 lanes, replay 84 s, gcov-tool merge 0.6 s, 140 s
  wall; 208 of 240 met, 172,499 records, 0 bad, offline != live 0; lines 1,269/1,475, branches 882/1,380 (63.9%).
  Exact cover stays weekly. `check_all --only h56-h5` alone afterwards: PASS, 79 s.
- **H6 sampled** (`h56.py h6 --sample --sample-n 64 --budget-min 60 --cache`, same 5 sessions, --h5 r12-h5, 6
  jobs): COMPLETE in 41 min 50 s, all 35 files cold (library, records and h56.py/harness.py changed):
  **2,208 / 4,137 caught (53.4%)** over 204 overrides, 11,641 of 172,499 records sampled; published as
  build/harness/h56/play/h6_sample.json. Gate 90%: writers stay off.
- **check_all** (`--slow --jobs auto --cache --skip h56-h5`, beside the live run and H6): 76.7 min, **92 pass, 1
  known, 2 skip** (known: readable-verify item_sell_price NOT-RUN; 0 MISMATCH over 240: 132 ABI-ONLY, 15 CLEAN, 83
  GAVE-UP, 9 UNSAMPLED; skip: gen-headers, h56-h5 on purpose). New rows class-change-diff(-long),
  weapon-rank-diff(-long) all pass. No row came from the cache: the new readable folders change every readable
  row's key. The 12 `--plant` rows take 21-36 min each and set the wall time.
- **Measured.** bt-ch24: play 129 min, proof 12 min (both helpers' timings). Integrate 07:27 to about 09:00 (about
  1 h 35 min): plan and check_all edits 7 min; offline 4.5 min; live 14.5 min; H5 2.3 min; H6 42 min and check_all
  77 min side by side (check_all the long pole); h56-h5 row 1.3 min; docs, evidence and clean about 8 min.
  Idle compute [med, from start and end times]: the live part was one run, so the 12 slots were mostly held by
  check_all (5-6 lanes, its day budget max_parallel_runs 6) and H6 (6 jobs); from H6's end (08:34) to check_all's
  end (08:51) about half the slots stood idle while the last `--plant` rows and readable-verify finished. About a
  fifth of the slot time in the 77-minute window was idle.

## Round 13 integrate (2026-11-16 late morning) [high unless tagged]

- **Chapter this round:** Birthright 25 only (F-025: Conquest and Revelation stay paused; cq-ch13 and rv-ch18 stay
  `verified: false`, not packed, not played). bt-ch25 (3s): play 70 min in the look-ahead from bt-ch24-clear, 15 of 15
  units kept, Iago killed on turn 16; proof its own step (session r13-bt25-proof, 2 original copies, both 132,940
  frames, memory 10c23ede8159972a, 547 s), packed bt-ch25-clear.zip from copy 1, then one capture run on the library
  (r13-bt25-cap, 0 bad); routes.json bt-ch25 `verified: true`. robot-routes now asks for bt-ch25-clear (52 verified
  real-play routes checked, 0 problems).
- **Library:** `build.py --check-fresh` FRESH (rebuilt 09:37 by the shop-price capture step, 241 overrides, 47 staged
  files, sha256 97201c67f0b2...): not rebuilt. No reader was edited after its batch capture.
- **Plan (round 13 tools: each session's own baseline, 0-record captures read; no --baseline-rev).** `offline.py plan
  --sessions r10-capb,r11-capn,r11-capo,r12-capn --extra-sessions "r12-cap-*,r13-cap-*" --label play`: baselines
  0e8ddd7 (r10-capb), de846a6 (r11-capn, r11-capo), d930f28 (r12-capn). PLAN LINE 1: 51 routes offline, 0 live.
  PLAN LINE 2: 241 overrides decided by records (shop_buy_price by r13-cap-shop_price, 115 records on the 5 shop
  routes), 0 live. Cheat plan (r10-capc, r11-capc, extra r12-capc-*, r12-cap-weapon_rank, r13-capc-*): 4 routes
  offline, 0 live.
  - Offline, real play (r13-off, 141 folders, 4 at once, 87 s): 172,614 records (168,543 match, 2,639 gave up,
    1,432 incomplete), 0 bad of any kind, offline verdict != captured verdict: 0, source gate passed.
  - Offline, cheat apart (r13-offc, 21 folders, 30 s): 9,062 records (8,869 match), 0 bad, verdict differences 0.
  - Live, bt-ch25, every override (`parallel.py runs --route bt-ch25 --mode capture --only all --store-keep
    --markers --timeout 5400 --session r13-capn`, FEF_ROBOT_JOBS=12): PASS, 425 s, 179 functions met, 4,084 records
    (3,988 match, 50 gave up, 46 incomplete), 0 bad of any kind; memory 10c23ede8159972a = the proof's; checkpoints
    all met; no writer stored anything; %APPDATA% unchanged.
  - Per family, real play: Birthright 31 routes, 202 met, 104,296 records; Conquest 7, 187 met, 26,000; Revelation
    12, 191 met, 44,390; options 2, 65 met, 2,012; **0 bad in each**. All: 52 routes, 176,698 records (172,531
    match, 2,689 gave up, 1,478 incomplete), 209 of 241 met (the same 32 never met as round 12).
- **H5** (`h56.py h5 --sessions r10-capb,r11-capn,r11-capo,r12-cap-class_change,r12-capn,r13-cap-shop_price,r13-capn
  --label play --run-id r13-h5 --no-exact --jobs 12 --jobs-over-budget`): 142 folders in 12 lanes, replay 80 s, merge
  2.5 s, 3 min 51 s wall; 209 of 241 met, 176,698 records, 0 bad, offline != live 0; branches 882/1,380 (63.9%).
  Exact cover stays weekly. `check_all --only h56-h5` alone afterwards: PASS, 71 s.
- **H6 sampled** (same 7 sessions, --h5 r13-h5, N=64, 60-min budget, cache on): COMPLETE in 51 min 28 s, all 36 files
  cold: **2,214 / 4,140 caught (53.5%)** over 205 overrides; published build/harness/h56/play/h6_sample.json. Gate
  90%: writers stay off.
- **check_all** (`FEF_CHECK_ALL_SLOTS=12 --slow --jobs auto --cache --skip h56-h5`, beside the live run, H5 and H6):
  53.5 min, 85 pass, 1 known, 2 skip, 11 fail; all 11 fails were timeouts of the older `--plant` rows (CPU
  oversubscribed), no mismatch. Rerun of the 11 after H6 (`--timeout-scale 2`): 11 pass in 31.6 min, each inside its
  normal limit. Net **96 pass, 1 known (item_sell_price NOT-RUN; 0 MISMATCH over 241), 2 skip**. New rows
  shop-price-diff(-long), castle-join-diff(-long) pass.
- **Measured.** bt-ch25: play 70 min, proof 16 min. Integrate 10:39 to 12:19 (about 1 h 40 min, target 1.5 h):
  plans and edits 4 min; offline 2 min; live 7 min; H5 4 min; H6 51.5 min beside check_all 53.5 min; the 11-row
  rerun 31.6 min; h56-h5 row 1.2 min; docs, evidence and clean about 3 min. Idle compute [med]: none in the first
  53 min (oversubscribed), about a third of the slots in the rerun's last 15 min. Lesson: 12 check_all lanes beside
  H6 is too many on this PC; use 8 while H6 runs.

## Round 14 integrate (2026-11-16 afternoon) [high unless tagged]

- **Chapter this round:** Birthright 26 only (F-025: Conquest and Revelation stay paused; cq-ch13 and rv-ch18 stay
  `verified: false`, not packed, not played). bt-ch26 (3t): play 30 min in the look-ahead from bt-ch25-clear, 16 of 16
  units kept, Xander killed by Ryoma on turn 3; proof its own step (session r14bt26proof, 2 original copies, both
  31,460 frames, memory 9da9f7c1fdcaf666, 187 s), packed bt-ch26-clear.zip from copy 1, then one capture run
  (r14bt26cap, 3,276 records, 0 bad); routes.json bt-ch26 `verified: true`. robot-routes now asks for bt-ch26-clear
  (53 verified real-play routes checked, 0 problems).
- **Library:** `build.py --check-fresh` FRESH (rebuilt 15:30:21 by the equip capture step with `--swap`: 245
  overrides, 49 staged files). Not rebuilt. No reader source was edited after its batch capture (equip_use.c 12:40,
  staff_range.c 12:39; the batches' later edits were tests, docs and comments only), so no reader needed a second
  capture.
- **Plan.** `offline.py plan --sessions r10-capb,r11-capn,r11-capo,r12-capn,r13-capn --extra-sessions
  "r12-cap-*,r13-cap-*,r14-cap-*" --label play` (r13-capn, bt-ch25 with every override, is now a main session;
  baselines 0e8ddd7, de846a6, d930f28, ef15c64 from each session's run.json; 51 folders kept 0 records):
  - PLAN LINE 1, routes: 52 replay offline from their records, 0 must play live (route changed).
  - PLAN LINE 2, overrides: 245 decided by the records (4 by the batches' own captures: unit_can_equip_item 215
    records on 8 Birthright routes from r14-cap-equip_use; unit_rod_heal_power 731, unit_status_staff_hit 41,
    unit_status_staff_avoid 41 from r14-cap-staff_range), 0 must play live. LIVE TOTAL: nothing plays live, so the
    only real-play live run is the new route bt-ch26.
  - Cheat plan (`--sessions r10-capc,r11-capc --extra-sessions "r12-capc-*,r12-cap-weapon_rank,r13-capc-*"
    --label cheat`): 4 routes offline; 241 decided, **4 must play live on the 4 cheat routes** (the four new readers:
    neither batch capture included a cheat route). Played live as `r14-capc-readers` (below).
- **Runs, all started at once (15:51):**
  - Offline, real play (`offline.py replay ... --name r14-off --jobs 4`): source gate passed, 186 folders, **177,726
    records (173,344 match, 2,887 gave up, 1,495 incomplete), 0 bad of any kind, offline verdict != captured verdict:
    0**, 159 s.
  - Offline, cheat apart (`r14-offc`): 21 folders, 9,062 records (8,869 match), 0 bad, 0 verdict differences, 29 s.
  - Live, bt-ch26, every override (`parallel.py runs --route bt-ch26 --mode capture --only all --store-keep --markers
    --timeout 5400 --session r14-capn`, FEF_ROBOT_JOBS=12): PASS, 127 s, 167 functions met, **3,303 records (3,185
    match, 66 gave up, 52 incomplete), 0 bad**; memory 9da9f7c1fdcaf666 = the proof's; checkpoints all met; no writer
    stored anything; %APPDATA% unchanged. unit_can_equip_item met (27 records, 8 match, the rest gave up); the three
    staff readers were not called (no staff used in chapter 26).
  - Live, cheat routes, the 4 new readers (`parallel.py runs --route cheat-family --route cheat-forge-katana --route
    cheat-katana-reload --route cheat-skill-proc --mode capture --only unit_can_equip_item,unit_rod_heal_power,
    unit_status_staff_avoid,unit_status_staff_hit --store-keep --session r14-capc-readers`): 4/4 PASS in 59 s, 150
    records of unit_can_equip_item (48 match, 101 gave up, 1 incomplete), 0 bad; the staff readers not called; each
    memory hash equal to r10-capc / r11-capc / r12-capc-class_change; writers stored nothing.
  - Per family, real play (offline + live; h6three number 3): Birthright 32 routes 108,185 records; Conquest 7,
    26,209; Revelation 12, 44,623; options 2, 2,012; **0 bad and 0 other differences in each**. All: 53 routes,
    181,029 records. Cheat apart: 4 routes, 9,212 records (9,062 offline + 150 live), 0 bad.
- **H5** (`h56.py h5 --sessions r10-capb,r11-capn,r11-capo,r12-cap-class_change,r12-capn,r13-cap-shop_price,r13-capn,
  r14-cap-equip_use,r14-cap-staff_range,r14-capn --label play --run-id r14-h5 --no-exact --jobs 12
  --jobs-over-budget`): 1 min 56 s; **213 of 245 met, 181,029 records (176,529 match, 2,953 gave up), 0 bad, offline
  != live 0**; lines 1,328/1,540, branches 928/1,460 (63.6%). All 4 new readers met (equip 242 records, heal 731,
  staff hit 41, staff avoid 41); never met: the same 32 as round 13. Exact cover stays weekly. `check_all --only
  h56-h5` alone afterwards: PASS, 91 s.
- **No sampled H6 this round** (weekly; last run round 13, 53.5%). The three-number report (F-026,
  `h6three.py --h5 r14-h5 --offline r14-off --offline-cheat r14-offc --live r14-capn --live r14-capc-readers`) on
  the fresh data: (1) recordings on reached lines 2,214 / 3,700 (59.8%; 62.9% also leaving out helper lines), still
  from round 13's sample; (2) host test alone 2,864 / 3,139 (91.2%); (3) live compare 53 routes, 181,029 records, 0
  bad.
- **check_all** (F-028: no `--slow` this round): `FEF_CHECK_ALL_SLOTS=8 --fast --jobs auto --cache --skip h56-h5`:
  37 pass, 0 fail, 50 s (gen-headers skipped as always). Touched slow and medium rows (`--only`, 8 slots): equip-use-diff,
  equip-use-diff-s7, staff-range-diff, staff-range-diff-long, readable, selftest, item-diff, ai-perm-diff (item.h and
  ai_perm.h comments edited by the equip batch), robot-routes, h6three-tests: **10 pass**, 14.2 min (item-diff 14 min,
  the long pole). Then h56-h5: pass. 58 slow/medium rows were left for the weekly run (listed in docs/CHECK_ALL.md).
- **Measured.** bt-ch26: play 30 min, proof 8 min. Integrate 15:49 to about 16:20 (**about 30 min**, target 45-60):
  plans 1 min; offline, cheat offline and both live runs side by side 3 min (15:51-15:54); check_all edits and tests
  4 min beside them; fast pass 1 min; touched rows 14 min; H5 2 min beside them; h56-h5 row 1.5 min; h6three 1 min;
  evidence and clean 0.5 min; docs about 9 min. Idle compute [med]: from about 16:00 to 16:10 only item-diff and
  ai-perm-diff ran (2 of 12 lanes), so most of the PC stood idle for those 10 minutes.

## Round 15 integrate (2026-11-16 evening) [high unless tagged]

- **Chapter this round:** Birthright 27 "King Garon" only (F-025: Conquest and Revelation stay paused; cq-ch13 and
  rv-ch18 stay `verified: false`, not packed, not played). bt-ch27 (3u): play 58 min in the look-ahead from
  bt-ch26-clear, 16 of 16 units kept, 18 turns, Garon killed by Ryoma on turn 18 after Azura's song; proof its own
  step (session r15bt-ch27proof2, after checkpoint 45448 was added to the shot list; 2 original copies, both 112,772
  frames, memory 435c8519ffc0530b, 505,346,668,992 instructions, 601 s), then one capture run (r15bt-ch27cap, 3,872
  records, 0 bad); routes.json bt-ch27 `verified: true`. **No bt-ch27-clear.zip**: the game makes no save after
  chapter 27 (it goes straight from the talk scenes to the Endgame Preparations, where Exit is refused), and copy 1's
  save files are byte-for-byte bt-ch26-clear. robot-routes now knows this (`NO_CLEAR_SAVE`, docs/CHECK_ALL.md) and
  checks 54 verified real-play routes, 0 problems. How Endgame starts (from the chain state with --import-chain, or
  a savestate at frame 112762) is a person's decision.
- **Library:** `build.py --check-fresh` FRESH (rebuilt 17:59:30 by the capability retry capture, 248 overrides, 50
  staged files; the staged capability.c holds the stat-0 fix). Not rebuilt; no reader was edited after its last
  capture, so no extra capture.
- **Plan** (build/speed/r15int/plan-play.txt, plan-play2.txt, plan-cheat.txt):
  - As asked (`--sessions r10-capb,r11-capn,r11-capo,r12-capn,r13-capn,r14-capn --extra-sessions
    "r12-cap-*,r13-cap-*,r14-cap-*,r15-cap-*" --label play`): PLAN LINE 1, routes: 53 replay offline from their
    records, 0 must play live (route changed). PLAN LINE 2, overrides: 248 decided by the records (3 by the batch's
    own captures r15-cap-capability and r15-cap-capabilityb, 456 + 374 records, 1 watched and never called), 0 must
    play live. LIVE TOTAL: nothing plays live.
  - The glob also picks up `r15-cap-capability`, the first capture made before the fix (7 live mismatch_calls). It
    was left out of the replay: `--extra-sessions "r12-cap-*,r13-cap-*,r14-cap-*,r15-cap-capabilityb"` gives the same
    two lines (53 offline; 248 decided, unit_capability 228 and unit_capability_rating 187 records from the retry
    capture alone, the no-weakness total watched, never called; 0 live).
  - Cheat (`--sessions r10-capc,r11-capc --extra-sessions "r12-capc-*,r12-cap-weapon_rank,r13-capc-*,r14-capc-*"
    --label cheat`; no r15-capc-* existed before the live run): 4 routes offline; 245 decided, **3 must play live on
    the 4 cheat routes** (the three capability readers: the batch capture had no cheat route).
- **Runs, all started at once (18:19:33):**
  - Offline, real play (`offline.py replay ... --name r15-off --jobs 4`): source gate passed, 195 runs, **181,444
    records (176,802 match, 3,013 gave up, 1,629 incomplete), 0 bad of any kind, offline verdict != captured verdict:
    0**, 117.5 s.
  - Offline, cheat apart (`r15-offc`): 28 runs, 9,212 records (8,917 match), 0 bad, 0 verdict differences, 28.5 s.
  - Live, bt-ch27, every override (`parallel.py runs --route bt-ch27 --mode capture --only all --store-keep --markers
    --timeout 5400 --session r15-capn`, FEF_ROBOT_JOBS=12): PASS, 369.6 s, 112,772 frames, 171 functions met,
    **3,872 records (3,739 match, 74 gave up, 59 incomplete), 0 bad**; memory 435c8519ffc0530b = the proof's;
    checkpoints all met; no writer stored anything; %APPDATA% unchanged. unit_capability and unit_capability_rating
    met.
  - Live, cheat routes, the 3 new readers (`parallel.py runs --route cheat-family --route cheat-forge-katana --route
    cheat-katana-reload --route cheat-skill-proc --mode capture --only unit_capability,unit_capability_rating,
    unit_capability_rating_no_weakness --store-keep --session r15-capc-capability`): 4/4 PASS in 49 s, 300 records
    (236 match, 30 gave up, 34 incomplete), 0 bad; 2 of the 3 readers met (not the no-weakness total); each memory
    hash equal to r14-capc-readers; writers stored nothing.
  - Per family, real play (offline + live; h6three number 3): Birthright 33 routes 112,472 records; Conquest 7,
    26,209; Revelation 12, 44,623; options 2, 2,012; **0 bad and 0 other differences in each**. All: 54 routes,
    185,316 records. Cheat apart: 4 routes, 9,512 records (9,212 offline + 300 live), 0 bad.
- **H5** (`h56.py h5 --sessions r10-capb,r11-capn,r11-capo,r12-cap-class_change,r12-capn,r13-cap-shop_price,r13-capn,
  r14-cap-equip_use,r14-cap-staff_range,r14-capn,r15-cap-capabilityb,r15-capn --label play --run-id r15-h5
  --no-exact --jobs 12 --jobs-over-budget`): about 2 min; **215 of 248 met, 185,316 records (180,541 match, 3,087
  gave up), 0 bad, offline != live 0**; lines 1,342/1,556, branches 937/1,470 (63.7%). New: unit_capability 259
  records (193 match), unit_capability_rating 204 (113 match); never met: the same 32 plus
  unit_capability_rating_no_weakness (33). Exact cover stays weekly. `check_all --only h56-h5` alone: PASS, 74 s.
- **No sampled H6 this round** (weekly; last run round 13). The three-number report (F-026, `h6three.py --offline
  build/speed/replay/r15-off/offline.json --offline-cheat build/speed/replay/r15-offc/offline.json --live
  build/parallel/r15-capn/summary.json --live build/parallel/r15-capc-capability/summary.json --json
  build/h6three/three-r15.json`): (1) recordings on reached lines 2,214 / 3,696 (59.9%; 62.9% also leaving out
  helper lines), still round 13's sample and its H5 reach data; (2) host test alone 2,864 / 3,139 (91.2%), records
  or host 91.7%; (3) live compare 54 routes, 185,316 records, 0 bad; cheat 9,512, 0 bad. A first try with `--h5
  r15-h5` gave "0 left out" because a `--no-exact` H5 run holds no per-line reach data for the sample; the sample's
  own H5 (r13-h5, the default) is the right input, as in round 14. [med: inferred from the output, not traced]
- **check_all** (F-028: no `--slow`): fast 38 pass in 41 s; touched rows capability-diff, capability-diff-long,
  look-step4, readable, selftest, sheet-diff: 6 pass in 9.7 min; h56-h5 pass. 62 slow/medium rows left for the
  weekly run (docs/CHECK_ALL.md, round 15). fe_guest.h changed: only the `readable` row (all 50 sources compiled)
  and the batch's guest_call5/6 tests cover that tonight.
- **Measured.** bt-ch27: play 58 min (cap 100), proof 28 min (a first proof missed a checkpoint frame and was rerun).
  Capability batch 80 min (cap 120) + live fix 45 min; captures 27 min (failed: 7 mismatch_calls) + 25 min retry
  (cap 45 each). Stats step 15 min (cap 90). Integrate 18:17 to about 18:55 (**about 38 min**, cap 60): reading and
  plans 2 min; offline, cheat offline and both live runs side by side 6 min (18:19:33-18:25:46, bt-ch27 live the
  long pole at 6 min 10 s); check_all edits and tests beside them; fast pass 1 min; touched rows 10 min with H5
  (2 min) beside them; h56-h5 row 1.2 min; h6three 1 min (twice); evidence and clean 1 min; docs about 14 min.
  Idle compute [med]: 18:21:30-18:25:46 only the one bt-ch27 copy ran (one route cannot be split), and 18:29-18:36
  only sheet-diff ran (1 of 8 slots), so most of the PC stood idle for about 11 minutes.
- **Evidence**: `evidence.py pack` (112.1 MB total) and `clean --yes --keep-sessions 10` (3 items, about 1 MB:
  smoke-title-ser, smoke-title-par, r13-bt25-cap, all packed) keeping every r10-r15 capture session (r10-capb,
  r10-capc, r11-capn, r11-capo, r11-capc, r12-capn, r12-cap-class_change, r12-cap-weapon_rank, r12-capc-class_change,
  r13-capn, r13-cap-shop_price, r13-capc-shop_price, r14-cap-equip_use, r14-cap-staff_range, r14-capn,
  r14-capc-readers, r14bt26proof, r14bt26cap, r15-cap-capability, r15-cap-capabilityb, r15-capn,
  r15-capc-capability, r15bt-ch27cap, r15bt-ch27proof2) and r15-h5 (under build/harness/h56, which clean does not
  touch).

## Round 16 integrate (2026-11-16 night) [high unless tagged]

- **Chapter this round:** Birthright Endgame only, from the bt-ch27 chain state (F-029), look-ahead (3v). **Not won**:
  the helper stopped at 63 minutes of play (cap 100) at the start of turn 5's player phase (frame 158338, 16 of 16
  alive, 17 enemies left), because the boss (Garon, Blight Dragon) could not be beaten in the time left. No
  `bt-endgame` route key was written, so there was nothing for a two-copy proof and no new route to play live. The
  kept chain replays from frame 0 of bt-ch26-clear to c27's proven state (505,346,668,992 instructions at 112772)
  and to its own state at 158338 (chk2.py, boot-server). Conquest and Revelation stay paused (cq-ch13, rv-ch18
  `verified: false`, not played).
- **Library:** `build.py --check-fresh` FRESH (rebuilt 2026-11-16T21:09:58 by the shop_grey capture; 251 overrides,
  51 staged files). Not rebuilt; no reader was edited after its batch capture, so no extra capture.
- **The cheat run in the batch capture.** r16-cap-shop_grey held 5 real-play runs and one cheat run
  (r16-cap-shop_grey-4, cheat-forge-katana, plus its 4.stage0 folder). offline.py stopped: "label play: these record
  folders are the other track (F-019, never mixed)". Integrate moved runs 4 and 4.stage0 to
  `build/parallel/r16-capc-shop_grey/records/` (with a copy of summary.json and a MOVED.txt in both folders); no
  record was changed. Next capture of a batch: give the cheat route its own `r16-capc-*` session.
- **Plan** (build/speed/r16int/plan-play.txt, plan-cheat.txt):
  - Real play (`--sessions r10-capb,r11-capn,r11-capo,r12-capn,r13-capn,r14-capn,r15-capn --extra-sessions
    "r12-cap-*,r13-cap-*,r14-cap-*,r15-cap-capabilityb,r16-cap-*" --label play`; r15-cap-capability, the pre-fix
    capture, left out): **PLAN LINE 1, routes: 54 replay offline from their records, 0 must play live (route
    changed). PLAN LINE 2, overrides: 251 decided by the records (3 of them by the batches' own captures, 1 of those
    watched and never called), 0 must play live.** LIVE TOTAL: nothing plays live. bt-ch27 is now offline from
    r15-capn.
  - Cheat (`--sessions r10-capc,r11-capc --extra-sessions "r12-capc-*,r12-cap-weapon_rank,r13-capc-*,r14-capc-*,
    r15-capc-*,r16-capc-*" --label cheat`): **PLAN LINE 1: 4 routes offline, 0 live. PLAN LINE 2: 251 decided (17 by
    the batches' own captures, 8 of those watched and never called), 0 live.** No live cheat run was needed.
- **Runs, started at once (21:55:34):**
  - Offline, real play (`offline.py replay ... --name r16-off --jobs 6`, FEF_ROBOT_JOBS=12): source gate passed, 201
    runs, **185,561 records (180,786 match, 3,087 gave up, 1,688 incomplete), 0 bad of any kind, offline verdict !=
    captured verdict: 0**, 104 s.
  - Offline, cheat apart (`r16-offc --jobs 2`): 36 runs, **9,561 records (9,202 match), 0 bad, 0 verdict
    differences**, 33 s.
  - Per family, real play (h6three number 3): Birthright 33 routes 112,664 records; Conquest 7, 26,262; Revelation
    12, 44,623; options 2, 2,012; **0 bad and 0 other differences in each**. All: 54 routes, 185,561 records.
    Cheat apart: 4 routes, 9,561 records, 0 bad.
- **New readers in real play:** shop_stock 115 records, shop_price_disabled 130, all match, on the 5 shop routes
  (bt-castle-forge, bt-castle-shop, bt-ch6-castle, bt-ch9-ore, cq-ch10); on the cheat route 23 and 26, all match.
  shop_buy_max never met (no recorded route calls it; host test only).
- **H5** (`h56.py h5 --sessions <the round 15 twelve>,r16-cap-shop_grey --label play --run-id r16-h5 --no-exact
  --jobs 12 --jobs-over-budget`): 2 min; **217 of 251 met, 185,561 records (180,786 match, 3,087 gave up), 0 bad,
  offline != live 0**; lines 1,353/1,567, branches 942/1,476 (63.8%). Never met: 34 (the 33 of round 15 plus
  shop_buy_max). `check_all --only h56-h5` alone: PASS, 74 s.
- **No sampled H6 this round** (weekly). Three-number report (`h6three.py --offline build/speed/replay/r16-off/
  offline.json --offline-cheat build/speed/replay/r16-offc/offline.json --live "" --json
  build/h6three/three-r16.json`): (1) recordings on reached lines 2,214 / 3,696 (59.9%; 62.9% also leaving out
  helper lines), still round 13's sample; (2) host test alone 2,864 / 3,139 (91.2%), records or host 91.7%, 13 files
  without a host test; (3) live compare 54 routes, 185,561 records, 0 bad; cheat 9,561, 0 bad. Note: without
  `--live`, h6three adds round 13's r13-capn summary by default (bt-ch25 a second time: 189,645 records). With no
  live run this round, `--live ""` is the right call [high: read in h6three.py].
- **check_all** (F-028: no `--slow`): fast 39 pass in 43 s; touched rows shop-grey-diff, shop-grey-diff-long,
  readable, selftest, mods-selftest, text-mods, harness-selftest 7 pass, look-portrait crashed the run on a
  Japanese note (fixed, docs/CHECK_ALL.md round 16) and then passed alone; h56-h5 pass. 63 slow/medium rows left
  for the weekly run.
- **Measured.** Endgame play 63 min (cap 100; stopped, not won) plus about 10 min replay check of the kept chain;
  no proof (nothing to prove). Shop batch 55 min (cap 120); capture 24 min (cap 45; 6 routes, no retry); no fix and
  no second capture needed. Looks 23 min (cap 60). Integrate 21:53 to about 22:13 (**about 20 min**, cap 60): plans
  and the cheat-run move 3 min; both offline replays side by side 1 min 45 s; check_all rows and tests written
  beside them; fast pass 43 s with H5 (2 min) beside it; touched rows 3 min (to the crash); look-portrait fix and
  row 1 min; h56-h5 row 1 min 12 s; h6three and evidence 2 min; docs about 6 min. Idle compute [med]: no game ran
  in integrate at all. The PC stood mostly idle for about 7 minutes while I wrote check_all rows and fixed the note
  (21:57:19 to 22:00:45, 22:04:23 to 22:05:45, and the 2 minutes of plans), and through the docs time.
- **Evidence**: `evidence.py pack` (112.4 MB in all; new: r15bt-ch27proof2, r16-cap-shop_grey, r16-capc-shop_grey)
  and `clean --yes --keep-sessions 10` (0 items freed), keeping every r10-r16 capture session (the round 15 list
  plus r16-cap-shop_grey, r16-capc-shop_grey) and r15-h5 / r16-h5 (under build/harness/h56, which clean does not
  touch).

## Round 17 integrate (2026-11-17 night) [high unless tagged]

- **Round 17 in one line.** The danger tools were rebuilt on one shared file (3w, about 5 min of a 30-minute cap),
  then a fresh Endgame try from the turn-5 chain (3w-2): **not won**, 57 min of play (cap 100), stopped at the start
  of turn 9 (chain cf, frame 206992, 16 of 16 alive, Garon 78/78 at (14,9)); the press list replays clean from
  bt-ch26-clear (chk2.py, 11 min). No `bt-endgame` route key, so no proof, no retry and nothing new played live. Beside
  them the host-test step gave the 13 files with no host verdict one (4 new diff scripts plus h6host adapters; 59 min
  of a 120-minute cap; 870 mutants, 831 caught, 39 survived, 35 judged unable to change an answer, 4 open).
  Conquest and Revelation stay paused (cq-ch13, rv-ch18 `verified: false`, not played).
- **Library:** `harness/build.py --check-fresh` FRESH (built 2026-11-16T21:09:58, 51 staged files, 251 overrides).
  No reader code changed this round (tests only), so not rebuilt.
- **Plan** (build/speed/r17int/plan-play.txt, plan-cheat.txt):
  - Real play (`--sessions r10-capb,r11-capn,r11-capo,r12-capn,r13-capn,r14-capn,r15-capn --extra-sessions
    "r12-cap-*,r13-cap-*,r14-cap-*,r15-cap-capabilityb,r16-cap-*" --label play`; r15-cap-capability, the pre-fix
    capture, left out): **PLAN LINE 1, routes: 54 replay offline from their records, 0 must play live (route
    changed). PLAN LINE 2, overrides: 251 decided by the records (3 by the batches' own captures, 1 of those watched
    and never called), 0 must play live.** LIVE TOTAL: nothing plays live.
  - Cheat (`--sessions r10-capc,r11-capc --extra-sessions "r12-capc-*,r12-cap-weapon_rank,r13-capc-*,r14-capc-*,
    r15-capc-*,r16-capc-*" --label cheat`): **PLAN LINE 1: 4 routes offline, 0 live. PLAN LINE 2: 251 decided (17 by
    the batches' own captures, 8 of those watched and never called), 0 live.** No undecided override, so no live
    cheat run.
- **Runs, started at once (01:16:03, FEF_ROBOT_JOBS=12):**
  - Offline, real play (`offline.py replay ... --name r17-off --jobs 6`): source gate passed, 201 runs, **185,561
    records (180,786 match, 3,087 gave up, 1,688 incomplete), 0 bad of any kind, offline verdict != captured
    verdict: 0**, 97 s.
  - Offline, cheat apart (`r17-offc --jobs 2`): 36 runs, **9,561 records (9,202 match), 0 bad, 0 verdict
    differences**, 27 s.
  - Per family, real play (h6three number 3): Birthright 33 routes 112,664 records; Conquest 7, 26,262; Revelation
    12, 44,623; options 2, 2,012; **0 bad and 0 other differences in each**. Cheat apart: 4 routes, 9,561, 0 bad.
- **H5** (`h56.py h5 --sessions <the round 16 thirteen> --label play --run-id r17-h5 --no-exact --jobs 12
  --jobs-over-budget`): 2 min 32 s; **217 of 251 met, 185,561 records, 0 bad, offline != live 0**; lines
  1,353/1,567, branches 942/1,476 (63.8%). Never met: the same 34. `check_all --only h56-h5` alone: PASS, 73 s.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r17-off/offline.json --offline-cheat build/speed/replay/r17-offc/offline.json --live "" --json
  build/h6three/three-r17.json`): (1) recordings on reached lines 2,214 / 3,696 (59.9%; 62.9% also leaving out
  helper lines), still round 13's sample; (2) **host test alone 3,696 / 4,009 (92.2%)**, H6 survivors the host test
  catches 1,618 / 1,926 (84.0%), records or host 3,832 / 4,140 (92.6%), **36 files with a host test, 0 without**
  (was 23 and 13); caught by the records but not the host test: 5; (3) live compare 54 routes, 185,561 records,
  0 bad; cheat 9,561, 0 bad. Unsorted new equivalent candidates: 71 (was 36; the host-test step's runs), plus the 237.
- **check_all** (docs/CHECK_ALL.md round 17): new rows ai-value-diff, flags-diff, forces-diff and their -long rows;
  fast 39 pass (44 s); touched rows 9 pass; readable pass; h56-h5 pass. 69 slow/medium rows left for the weekly run.
- **Measured.** Integrate 01:14 to about 01:38 (about 24 min, cap 60): reading and plans 2 min; both offline replays
  1 min 38 s; check_all rows and tests written beside them; fast pass 44 s with H5 (2 min 32 s) beside it, then
  touched rows 2 min 13 s; three-number report 1 min; a cache trial for the new rows 2 min (dropped); h56-h5 row
  1 min 14 s; evidence and the tests again 1 min; readable row 1 min 44 s (beside the docs); docs and report about 9 min. Idle compute [med]: no
  game ran in integrate. The PC stood mostly idle 01:14 to 01:16 (reading), 01:17:41 to 01:20:52 (writing rows) and
  through the docs time (about 9 min, the readable row apart).
- **Evidence**: `evidence.py pack` (112.4 MB in all, nothing new to pack: no new capture session this round) and
  `clean --yes --keep-sessions 10` (0 items freed), keeping every r10-r16 capture session and r15-h5 / r16-h5 /
  r17-h5. The Endgame chains (build/speed/btend/ce, cf and the turn-start copies) are not sessions; clean does not
  touch them.

## Round 18 integrate (2026-11-17 early morning) [high unless tagged]

- **Round 18 in one line.** The third Endgame try (3x; fresh helper, Grok's plan from the turn-5 chain, chain ch)
  played turns 5 to 7 in 47 minutes of a 100-minute cap and stopped at the start of turn 8 (frame 193094, 16 of 16
  alive, Garon 78/78 on (14,11)): **not won**, no `bt-endgame` route key, so no proof, no retry and nothing new
  played live for Endgame. It stopped early because the forecasts show a dual-strike partner does half damage, so
  the Shura + Corrin strike plan cannot reach 78 HP in time [med: read from forecasts, not traced in code]. Beside
  it: one reader batch (weapon_level_view_kind, GameInfoViewer::GetWeaponLevelKind, 35 min of a 2-hour cap), its
  capture (17 min, library rebuilt once by that step at 04:26:23), and the round-17 test-tool fixes (49 min of 60).
  Conquest and Revelation stay paused (cq-ch13, rv-ch18 `verified: false`, not played).
- **Library:** `harness/build.py --check-fresh` FRESH (built 2026-11-17T04:26:23 by the capture step, 52 staged
  files, 252 overrides). No reader changed after that capture (the batch's source is from 04:01; the test-tool step
  changed tests only), so integrate did not rebuild and no second capture was due.
- **Plan** (build/speed/r18int/plan-play.txt, plan-cheat.txt):
  - Real play (`--sessions r10-capb,r11-capn,r11-capo,r12-capn,r13-capn,r14-capn,r15-capn --extra-sessions
    r12-cap-class_change,r12-cap-weapon_rank,r13-cap-shop_price,r14-cap-equip_use,r14-cap-staff_range,
    r15-cap-capabilityb,r16-cap-shop_grey,r18-cap-weapon_level_view --label play`; r15-cap-capability, the pre-fix
    capture, left out; the batch capture needed no retry): **PLAN LINE 1, routes: 54 replay offline from their
    records, 0 must play live (route changed). PLAN LINE 2, overrides: 252 decided by the records (4 by the batches'
    own captures, 1 of those watched and never called), 0 must play live.** Nothing plays live.
  - Cheat (`--sessions r10-capc,r11-capc --extra-sessions r12-capc-class_change,r12-cap-weapon_rank,
    r13-capc-shop_price,r14-capc-readers,r15-capc-capability,r16-capc-shop_grey --label cheat`): **PLAN LINE 1: 4
    routes offline, 0 live. PLAN LINE 2: 251 decided (17 by the batches' own captures, 8 of those watched and never
    called), 1 must play live on 4 routes** (weapon_level_view_kind, never captured on a cheat route).
- **Runs, started at once (05:04:29, FEF_ROBOT_JOBS=12):**
  - Offline, real play (`r18-off --jobs 6`): source gate passed, 205 runs, **185,654 records (180,878 match, 3,087
    gave up, 1,689 incomplete), 0 bad of any kind, offline verdict != captured verdict: 0**, 130 s.
  - Offline, cheat apart (`r18-offc --jobs 2`): 36 runs, **9,561 records (9,202 match), 0 bad, 0 verdict
    differences**, 31 s.
  - Live, cheat apart (`parallel.py runs --route cheat-family --route cheat-forge-katana --route cheat-katana-reload
    --route cheat-skill-proc --mode capture --only weapon_level_view_kind --store-keep --session
    r18-capc-weapon_level_view`): 4 of 4 exit 0 Completed, 44 s; **23 records on cheat-forge-katana (22 match, 1
    incomplete), 0 bad**; the other three cheat routes never call it (0 records). No writer stored; %APPDATA%
    (zakuro, 3dsrecomp) unchanged.
  - Per family, real play (h6three number 3): Birthright 33 routes 112,757 records; Conquest 7, 26,262; Revelation
    12, 44,623; options 2, 2,012; **0 bad and 0 other differences in each**. Cheat apart: 4 routes, 9,584 records
    (offline plus live), 0 bad.
- **H5** (`h56.py h5 --sessions <the round 17 thirteen plus r18-cap-weapon_level_view> --label play --run-id r18-h5
  --no-exact --jobs 12 --jobs-over-budget`, beside the replays): 2 min 13 s; **218 of 252 met, 185,654 records, 0
  bad, offline != live 0**; lines 1,368/1,583, branches 955/1,492 (64.0%). weapon_level_view_kind: 93 records, lines
  15/16, branches 13/16. Never met: the same 34. `check_all --only h56-h5` alone: PASS, 70 s.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r18-off/offline.json --offline-cheat build/speed/replay/r18-offc/offline.json --live
  build/parallel/r18-capc-weapon_level_view/summary.json --json build/h6three/three-r18.json`): (1) recordings on
  reached lines 2,214 / 3,696 (59.9%; 62.9% also leaving out helper lines), still round 13's sample; (2) **host test
  alone 3,700 / 4,009 (92.3%)**, H6 survivors the host test catches 1,619 / 1,926 (84.1%), records or host
  3,833 / 4,140 (92.6%), 36 files with a host test, 0 without; caught by the records but not the host test: 2 (was
  5; the new heal-rod test rules); (3) live compare 54 routes, 185,654 records, 0 bad; cheat 9,584, 0 bad. Unsorted
  new equivalent candidates: 70 (was 71), plus the 237. weapon_level_view.c is not in the weekly H6 sample yet, so
  it has no line in numbers 1 and 2; its host test (22/22) runs in check_all.
- **check_all** (docs/CHECK_ALL.md round 18): new rows weapon-level-view-diff(-long), h6host-test,
  flags-diff-s424242; ai-perm-diff text says 48 planted bugs; h56-h5 reads 14 sessions. Fast 40 pass (41 s);
  touched rows 8 pass (14 min 9 s); h56-h5 pass. 72 slow/medium rows left for the weekly run.
- **Measured.** Integrate 05:02:58 to about 05:31 (about 28 min, cap 60): reading and both plans 1 min; the three
  compare runs and H5 side by side 2 min 13 s; check rows and tests written beside them (about 4 min, including a
  control-character fix in the new patterns); fast pass 41 s; touched rows 14 min 9 s (ai-perm-diff alone
  11 min 32 s, the long pole); three-number report under 1 s; evidence beside the touched rows; h56-h5 row
  1 min 10 s; docs and report about 8 min. Idle compute [med]: no game ran after 05:05:14. For about 9 of
  ai-perm-diff's 11.5 minutes it was the only row running (one lane of 8), so most of the PC stood idle then and
  during the docs.
- **Evidence**: `evidence.py pack` (112.8 MB in all; r18-cap-weapon_level_view and r18-capc-weapon_level_view
  packed, 0.2 MB each) and `clean --yes --keep-sessions 10` (0 items freed), keeping every r10-r18 capture session,
  r14bt26cap and r14bt26proof (the dry run offered them; kept), and r15-h5 to r18-h5. The Endgame chains
  (build/speed/btend/ce, cf, ch and the turn-start copies) are not sessions; clean does not touch them.

## Round 20: Revelation chapter 18 (`rv-ch18`), the paused chain picked up (2026-11-17) [high]

- **F-031, real play.** No new play was needed: the paused look-ahead chain build/speed/rv18/c18 (round 11, no
  pokes, no cheat save, from `rv-ch17-clear`) was already played to the end before the F-025 pause: chapter 18
  'Veiled Kingdom', all 8 dragon veins used, Xander (carrying Leo) killed the boss on turn 25, STAGE COMPLETE at
  228628 with 12 of 12 units, save in slot 1, My Castle at 232058, chain frame 232070 (`castle__Sequence`). Round 11
  had played it in about 113 min (start_epoch to played_epoch) and stopped before the proof; the docs only said
  "paused", so the chain looked unplayed.
- **Route key already written** (round 11): routes.json `rv-ch18` holds the full absolute press list from
  `rv-ch17-clear` (4,437 presses, in frame order, no duplicates), frames 232700, save_at 232690, `verified: false`;
  markers.json `rv-ch18` has 10 checkpoints (turns 1, 2, 6, 10, 16, 20, 25, STAGE COMPLETE 228628, the save question
  231874, castle 232058), equal to build/speed/rv18/marks.json. The press list equals build/speed/rv18/export.json.
  Nothing in routes.json or markers.json was changed this round.
- **Replay check (this round, current build).** The chain was copied to build/speed/rv18r (the original is kept as
  it was). `chk2.py` (from bt27) replayed export.json from frame 0 of `rv-ch17-clear` on boot-server, below normal:
  every checkpoint gave the recorded screen and units ([12, 30, 0] ... [12, 4, 0] at 226390, [12, 3, 0] at 228628,
  `GameDialogYesNo` at 231874, `castle__Sequence` at 232058), and at 232070 the instruction count was
  1,039,937,231,520, the same as c18/chain.json's `cycles`. So the export reaches the chain's own state. Run 15.5 min
  (build/speed/rv18r/chk.out).
- **Not done here:** the two-copy proof, pack and capture (a separate step, F-025). Next is chapter 19 from
  `rv-ch18-clear` once that is packed. No ROUTES_SPLIT section exists for rv-ch18 yet (the route's `about` names one).
- **Time:** 15:20 (start) to 15:38 (replay check read), about 18 min; no cap hit.

## Round 20: Revelation chapter 19 (`rv-ch19`), played to My Castle (2026-11-17) [high unless tagged]

- **F-031, real play** (no pokes, no cheat save). One fresh helper, fastlook chain build/speed/rv19/c19 from frame 0 of
  `rv-ch18-clear`, one call per action (no `serve` in battle: the danger tools read state.bin), below normal.
  Chapter 19 'Hidden Strings' (map C019, `Btl_RuinsCityInvisible`): "defeat the boss or escape all in 20 turns".
  Not the Endgame (castle after it; chapter id becomes C020).
- **Map.** 30 x 30. The start (12-16, 4-6) and the east (17-30, 1-16) are one floor; the boss (Dark Knight on (3,22)
  with two Generals) and 30 more enemies are on the south floor, which no ground path joins (terrain 1 "impassable"
  in rows 11-14 and 17-18; nothing changed it in 11 turns). Lake tiles (17-20, 3-7) are not walkable for the ground
  units. **Escape tiles** (shown as red squares; TrickData type 5) at (30,5)-(30,7) and (30,11)-(30,14). On an
  escape tile the command menu starts with **Escape**; A > "Leave the battlefield?" (cursor on No) > LEFT A. The
  unit leaves the map (the marker `units` count drops); the tile is free again at once, so one tile serves many.
  When the last unit leaves: STAGE COMPLETE (`castle__anonymous_namespace__Seq`, no `map__SequenceCompleteEffect`).
- **Units.** Preparations default 8 (Corrin, Azura, Felicia, Gunter, Sakura with no staff, Hana, Takumi, Oboro) were
  changed in Select Units to Corrin, Takumi, Shura, Xander, Leo, Ryoma, Elise, Camilla (presses in the route).
- **Enemy AI** (DisposUnit C019): the start-side Swordmasters, Berserkers, Brave Heroes, Maid and Adventurer are
  "Everytime" with no move (they attack what they can reach); the west Generals/Sorcerers, the Oni Chieftains,
  Snipers and the east Paladin, Great Knight, Bow Knight are "AttackRange" (they wait until a unit is in reach).
- **Played** (danger-tools rules of 3w: `danger.py` + gz/place/who/trig, copied to build/speed/rv19/tools with
  `MAPFILE=C019.bin.lz`; a fresh board per read): turn 1 Ryoma and Xander killed the two Swordmasters; turns 2-6
  Xander alone in reach of 1-2 enemies killed both Berserkers, both Brave Heroes and (with others) the Paladin,
  Bow Knight, Great Knight and Dark Knight on counters; turn 7 Xander killed the Maid, Leo escaped; turn 8 Ryoma,
  Camilla, Elise escaped, Xander waited as the only unit in the Adventurer's reach and the Adventurer was gone on turn 9 [med: not watched]; turns 9-11 Xander, Shura, Takumi, then
  Corrin escaped. **Nobody lost**: every unit at full or partial HP on each board read until it escaped; the
  marker player count goes 8 (turns 1-7) > 7 (turn 8, Leo out) > 2 (turn 11) > 0 only through Escape commands.
  Untouched: the north Oni Chieftains and Snipers, the west Generals/Sorcerers and the whole south.
- **Tool notes.** (1) When the last unit acts, the enemy phase starts by itself (22.2 note): after the 6th move of turn
  7 the board showed the Adventurer "moved" mid-turn; it was turn 8 already. I rolled the chain back by hand to
  55504 (inputs.txt cut at that step, chain.json frame set, `fastlook.py clean`, 3.2 min) and played the same moves
  again; the replay gave the same instruction count at 59294 as the first line. (2) `danger.py` reach is only a
  guide: on turn 5 Camilla lost 9 HP (30 > 21) on a tile the tool called safe and the Paladin stood next to her
  after [med: cause not traced]. (3) Disk D: was full (0 bytes free) at 16:27 for a few minutes (others' runs); act2.py here keeps only the
  4 newest hist snapshots (env KEEP).
- **Route key** (splitcfg.py): routes.json `rv-ch19` = the full absolute press list from `rv-ch18-clear` (1,280
  presses, in frame order, no duplicates, equal to build/speed/rv19/export.json), frames 73700, save_at 73690,
  `verified: false`; markers.json `rv-ch19` 10 checkpoints: 8222 preparations [8, 45, 0]; 10876 turn 1 [8, 45, 0];
  18578 [8, 43, 0]; 26408 [8, 42, 0]; 46220 [8, 38, 0]; 59294 [7, 34, 0]; 69816 [2, 33, 0]; **70938 STAGE COMPLETE**;
  73362 the save question (`GameDialogYesNo`, slot 1); **73546 `castle__Sequence`**. The summary screen says
  "TURNS 13"; I counted 11 player phases [med: not traced].
- **Replay check:** `tools/chk3.py` (from cq13b) replayed export.json from frame 0 on boot-server (clean line, below
  normal): every checkpoint screen and unit count as above, and at 73566 the instruction count is **329,659,250,976,
  equal to c19/chain.json's `cycles`** (build/speed/rv19/chk.out, 5 min). The two-copy proof, pack and capture are
  a separate step.
- **Time:** 16:15 (start) to 16:58 (exported press list): **about 43 min** of the 100-minute cap; replay check and
  config written by 17:05.

## Round 20: Revelation chapter 20 (`rv-ch20`), played to My Castle (2026-11-17) [high unless tagged]

- **F-031, real play** (no pokes, no cheat save). One fresh helper, fastlook chain build/speed/rv20/c20 from frame 0 of
  `rv-ch19-clear`, one call per action, below normal. Chapter 20 'Seeds of Doubt' (map C020, `Btl_StrangelyRocks`,
  play area 1-24 x 1-28): "defeat the boss". Not the Endgame (castle after it; chapter id becomes C021).
- **Map.** Floating isles in sky; ground units cross only on bridges. Each bridge has two places and a Dragon Vein
  moves it ("Relocate bridge and all units on it": units standing on it ride along). Trick list at g+0xFEC: bridges
  are type 0x0C with x, y, w, h and byte +0x16 = 2 when up, 1 when down; veins are type 0x0B. The terrain grid keeps
  tile 5 for both states, so the old `danger.py` called every bridge sky. Pairs seen: (15,26)<->(20,20) (vein
  (21,26)), (10,13)<->(10,21) (veins (11,23), (11,17)), (10,6)<->(12,3) (vein (10,9)), (2,6)<->(6,2) (vein (8,2)).
  A used vein stays usable (its byte did not change) [med: not used twice].
- **Units.** Preparations deploy 12 (last chapter's 8 plus Azura, Felicia, Gunter, Sakura); Select Units took those
  four out (8 units, presses in the route).
- **Enemy AI.** The boss (1,1) (Kinshi Knight, DisposUnit flags 0x6700: bit 0x4000 fixed) never moved, even with
  Xander 9 tiles away for a whole enemy phase: use `FIXED="1,1"`. Falcon Knights (MV_Null, AttackToHeal) did move.
  The AttackRange groups (Generals, Malig Knights, Kinshi Knights, Ninjas, Swordmasters) wait until someone is in reach.
- **Played** (danger-tools rules of 3w, a fresh board per read): turn 2-3 the flying Kinshi Knight came to Xander and
  died; turn 4 Xander used vein (11,23); turns 5-10 Xander (and Ryoma, Leo) took the middle isle's enemies one or two
  at a time on the bridge end (3 Great Masters, 2 Onmyoji, 3 Kinshi Knights, 4 Malig Knights; Takumi and Shura's bows
  for the fliers); turn 11 vein (11,17) carried Corrin, Elise, Ryoma, Leo north on the bridge; turn 12 Corrin used
  vein (10,9), both Falcon Knights attacked him and died on turn 13; turn 14 the Malig Knight by the boss; turn 16
  Xander used vein (8,2) (boss isle joined), the General from (3,1) died on his counter; turn 17 Ryoma and Leo killed
  the two Generals on the bridge and Xander (from (3,1)) killed the boss in one attack. **Nobody lost**: 8 player
  units at every checkpoint. Untouched: the east isles (Ninjas, Swordmasters, Sorcerers, Berserkers) and the west
  Generals.
- **Tool notes.** (1) `danger.py` (rv20 copy) now reads the trick list and counts an up bridge as bridge, a down one
  as sky; env `FLIP="x,y ..."` looks ahead at a vein use (that bridge pair switched). `gz.py -m` marks tiles 0, 4,
  5, 8 as walls on this map. (2) act2 `end` right after a move: the cursor read is stale and the path to the empty
  tile went wrong (cursor ended on an enemy, plan stopped and undone); a `refresh_cursor` step first fixed it.
  (3) Elise carries Physic but got no Staff command [med: likely her staff rank]. (4) The marker `veins_used` stayed 0
  although four bridge veins were used [med: that counter does not count these veins]. (5) Killing the boss gave
  Xander a Silver Naginata with a full bag: the item-send menu (`map__anonymous_namespace__ItemMenuSend`) came up;
  Steel Bow sent to the convoy (DOWN x4, A, LEFT A). One rolled-back try left four DOWN presses in that battle's
  animation; the line kept them and the replay matches.
- **Route key** (splitcfg.py): routes.json `rv-ch20` = the full absolute press list from `rv-ch19-clear` (1,521
  presses, in frame order, no duplicates, equal to build/speed/rv20/export.json), frames 97654, save_at 97644,
  `verified: false`; markers.json `rv-ch20` 10 checkpoints: 7536 preparations [12, 42, 0]; 8854 turn 1 [8, 42, 0];
  20396 [8, 41, 0]; 37122 [8, 38, 0]; 59954 [8, 29, 0]; 77610 [8, 26, 0]; 89564 [8, 24, 0]; **94652 STAGE COMPLETE**
  ([8, 21, 0], "TURNS 17"); 97296 the save question (`GameDialogYesNo`, slot 1); **97500 `castle__Sequence`**.
- **Replay check:** `tools/chk3.py` replayed export.json from frame 0 on boot-server (clean line, below normal): every
  checkpoint screen and unit count as above, and at 97520 the instruction count is **437,000,382,720, equal to
  c20/chain.json's `cycles`** (build/speed/rv20/chk.out, about 6 min). The two-copy proof, pack and capture are a
  separate step.
- **Time:** 17:20 (start) to 18:00 (exported press list): **about 40 min** of the 100-minute cap; replay check and
  config written by about 18:10.

## Round 24: Revelation chapter 21 (`rv-ch21`), played to My Castle (2026-11-17) [high unless tagged]

- **F-031, real play** (no pokes, no cheat save). One fresh helper, fastlook chain build/speed/rv21/c21 from frame 0 of
  `rv-ch20-clear`, one call per action, below normal. Chapter 21 'Going Forward' (map C021, `Btl_RuinsUnderground`,
  play area 1-26 x 1-26, normal difficulty): "defeat the boss". Not the Endgame (castle after it; chapter id becomes C022).
- **Map.** Rooms of dragon-vein floor joined by one- or two-tile doorways; no vein was used. The way from the start
  (x 17-26, y 1-5) to the boss room (x 21-26, y 17-26) runs west through the top rooms, down the x 7-8 doorways, east
  through the sorcerer room (x 11-16, y 11-15), down (12-13, 16-17) and east along rows 19-20. The enemy list is in
  `maps.py export C021` (build/speed/rv21/maps, gitignored): the boss (Faceless, AI_AC_Area (21,17)-(26,26)) waits
  until someone enters its room; most others are AttackRange; the Merchant, two Snipers, Sorcerer and Maids are
  Everytime. **Reinforcements step out of stair tiles** ((13,8) Swordmaster on turn 5, (7,13) Sniper on turn 10,
  (3,1)/(4,1) Masters of Arms on turn 8, Master Ninja thieves at (26,8)/(26,9) on turn 12); each appeared at the end
  of an enemy phase and did not act until the next one.
- **Units.** Preparations deploy 14; Select Units took out Azura, Felicia, Gunter, Sakura, Hana, Oboro (8 units:
  Corrin, Takumi, Shura, Xander, Leo, Ryoma, Elise, Camilla; presses in the route).
- **Played** (danger tools of 3w, `MAPFILE=C021.bin.lz`, a fresh board per read; every attack previewed first): turn 1
  Leo alone in reach of the Onmyoji/Basara room at the start doorway; turns 2-5 the north rooms and the x 8 corridor
  (Basara, Onmyoji, Swordmaster, Sorcerer, Samurai, Sniper); turn 5-6 Xander alone in reach of the Merchant and two
  Masters of Arms (they took 0-5 a hit); turn 7 Shura (Res 24) alone in reach of the three Sorcerers; turn 9 Xander
  alone in reach of the two Master Ninjas and two Mechanists (they could not hurt him: 36 HP before and after);
  turns 10-12 the stair Sniper and the reinforcement Masters of Arms; turn 13 the boss room's Generals, Sniper and
  Merchant came out to Xander at (16,19) and died over turns 13-14; turn 14 Xander entered the boss area at (23,20),
  the boss came and lost 28 HP on the counter; turn 15 Xander killed it (100%). **Nobody lost**: 8 player units at
  every checkpoint. Untouched: the west room (Swordmaster, Adventurer), the Berserkers, a Master of Arms and the
  thieves. The summary says "TURNS 15".
- **Tool notes.** (1) act2's `wait` waited only 3,000 frames for the next free cursor; when the last unit's move starts
  the enemy phase (22.2 note) that is too short (one stop, undone by act2); raised to 12,000. (2) `tools/prev.sh U D N`
  moves, picks Attack and target N, takes a shot of the forecast and puts the chain files back (nothing kept); the
  forecast showed what the danger tools do not (Ragnarok would have taken Xander from 36 to 11 on a counter, so Ryoma
  was sent instead). (3) Elise (Troubadour, Physic) again got no Staff command with Leo hurt in range [med: staff rank
  not read]. (4) The first STAGE COMPLETE A came too early (the `until` waited 30,000 frames on that screen and stopped);
  a second A then reached the save menu. (5) A Chest Key dropped on Ryoma with a full bag: sent to the convoy (DOWN x5,
  A, LEFT A).
- **Route key** (splitcfg.py): routes.json `rv-ch21` = the full absolute press list from `rv-ch20-clear` (1,758
  presses, in frame order, no duplicates, equal to build/speed/rv21/export.json), frames 118284, save_at 118274,
  `verified: false`; markers.json `rv-ch21` 10 checkpoints: 9892 preparations [14, 29, 0]; 11428 turn 1 [8, 29, 0];
  25296 [8, 25, 0]; 45120 [8, 21, 0]; 67508 [8, 15, 0]; 91776 [8, 11, 0]; 109158 [8, 10, 0]; **116740 STAGE COMPLETE**
  ([8, 7, 0]); 117946 the save question (`GameDialogYesNo`, slot 1, chapter C022); **118130 `castle__Sequence`**.
- **Replay check:** `tools/chk3.py` (cq14's, budget.enter for below normal) replayed export.json from frame 0 on
  boot-server: every checkpoint screen and unit count as above, and at 118150 the instruction count is
  **529,446,218,400, equal to c21/chain.json's `cycles`** (build/speed/rv21/chk.out, 6 min). The two-copy proof, pack
  and capture are a separate step.
- **Time:** 20:13 (start) to 20:54 (exported press list): **about 41 min** of the 100-minute cap; replay check and
  config written by about 21:05.

## Round 24: Revelation chapter 22 (`rv-ch22`), played to My Castle (2026-11-17) [high unless tagged]

- **F-031, real play** (no pokes, no cheat save). One fresh helper, fastlook chain build/speed/rv22/c22 from frame 0 of
  `rv-ch21-clear`, one call per action, below normal. Chapter 22 'Memories' (map C022, `Btl_WoodsLost`, play area
  1-24 x 1-20, normal difficulty): **Seize** (24,13), the boss's fort; the game asks "Seize and finish the battle?"
  (Yes = LEFT A). Not the Endgame (castle after it; chapter id becomes C023).
- **Map.** Plain paths through thick wood (tile 4 `TID_深い森／林`, tile 3 at the edges): every ground class has cost -1
  there, fliers (cost class 15) cost 1, so Falcon Knights, Kinshi Knights and our Camilla fly straight over it. The way
  to the seize tile: north along row 2 (x 2-23), then down the east column (x 23-24, rows 3-12). Enemies are all
  AI_AC_Everytime; most are MV_Null (wait until someone is in reach), a few MV_NearestEnemy (one Swordmaster, the south
  Sniper, Falcon Knight (14,12)) walk at once. The boss (Strategist Arete, flags 0x6000, bit 0x4000) never moved:
  `FIXED="24,13"`. She carries **Silence**: Leo (red arrow on the map) had only Items/Wait for the rest of the map,
  no Attack, even next to an enemy [med: the silence turn not seen; it showed on turn 11]. Reinforcements: Master
  Ninjas from the forts (19,10), (16,15), (6,14), two Basara from the west edge (1,5)/(1,6) seen on turn 10 (they walked
  after us along row 2 and never reached us).
- **Units.** Preparations deploy 14; Select Units took out Azura, Felicia, Gunter, Sakura, Hana, Oboro (same grid
  and presses as rv-ch21): 8 units.
- **Played** (danger tools of 3w, `MAPFILE=C022.bin.lz`, a fresh board per read, forecasts by `prev.sh`): turn 1
  Xander alone in reach at (3,2) of two Swordmasters and the Sniper; turn 2 Leo (range 2) and Ryoma (melee, no bow
  counter) killed the Swordmaster and Sniper, the other Swordmaster died on Ryoma's counter; turns 3-4 Takumi's Fujin
  Yumi killed two Falcon Knights (97%, lethal), Xander + Camilla the south Sniper, Corrin and Shura stood next to
  Takumi so no flier could reach him; turns 4-7 Leo baited the Onmyoji, Xander and Leo the Faceless, the Spear Master
  died on counters; turns 8-9 Xander baited the two north-east Falcon Knights at (21,2) (Ryoma and Leo finished them);
  turns 10-12 Ryoma (range 2) the (24,11) Swordmaster and an Oni Chieftain, Xander bait at (24,8); turn 13 Ryoma
  killed the boss from (24,11) (76%, two hits), two Oni Chieftains died on his counters; turn 14 Corrin seized from
  (24,10). **Nobody lost**: 8 player units at every checkpoint. The summary says "TURNS 15".
- **Tool notes.** (1) `dz.py`/`gz.py` marked tiles 0, 1 (A028's walls) and 0, 4, 5, 8 (rv20) as walls: on C022 that
  showed plain as wall and thick wood as floor (display only; the threat numbers were right). Now a wall is a tile whose
  cost for class 1 is -1. (2) **When the last unit acts, its `wait` already runs the enemy phase** (22.2 note): a
  following `end` then ended the NEXT player phase with nobody moved (one turn passed, nobody hurt, nothing undone:
  it is in the route). Leave a unit unmoved before `end`, or skip `end` after the last unit. (3) The danger tools do
  not know staves: Silence is not a threat in them. (4) After the seize, `until` waited 30,000 frames on the STAGE
  COMPLETE screen (class `castle__anonymous_namespace__Seq`, not `map__SequenceCompleteEffect...`) and stopped; plan
  end1.json (its list has that class, A answers) then reached the save menu. (5) Silver Katana (Ryoma) and Chest Key
  (Takumi) dropped with full bags: sent to the convoy (DOWN x5, A, LEFT A).
- **Route key** (splitcfg.py): routes.json `rv-ch22` = the full absolute press list from `rv-ch21-clear` (1,452
  presses, in frame order, no duplicates, equal to build/speed/rv22/export.json), frames 91194, save_at 91184,
  `verified: false`; markers.json `rv-ch22` 11 checkpoints: 6742 preparations [14, 29, 0]; 8142 turn 1 [8, 29, 0];
  21198 [8, 26, 0]; 34126 [8, 23, 0]; 50292 [8, 21, 0]; 64110 [8, 20, 0]; 77918 [8, 20, 0]; 88986 [8, 17, 0];
  **89480 STAGE COMPLETE** ([8, 17, 0]); 90856 the save question (`GameDialogYesNo`, slot 1, chapter C023);
  **91040 `castle__Sequence`**.
- **Replay check:** `tools/chk3.py` replayed export.json from frame 0 on boot-server (below normal): every checkpoint
  screen and unit count as above, and at 91060 the instruction count is **408,052,244,160, equal to c22/chain.json's
  `cycles`** (build/speed/rv22/chk.out, about 5 min). The two-copy proof, pack and capture are a separate step.
- **Time:** 21:19 (start) to 21:54 (exported press list): **about 35 min** of the 100-minute cap; replay check and
  config written by about 22:05.

## Round 24: Revelation chapter 23 (`rv-ch23`), played to My Castle (2026-11-17) [high unless tagged]

- **F-031, real play** (no pokes, no cheat save). One fresh helper, fastlook chain build/speed/rv23/c23 from frame 0 of
  `rv-ch22-clear`, one call per action, below normal. Chapter 23 (map C023, `Btl_CastleInvisible_Front`, play area
  x 1-20, y 1-28: `play` [1,1,21,29] is end-exclusive, a move to x 21 is refused), normal difficulty: **Seize** (1,1),
  the boss's fort. Not the Endgame (castle after it; chapter id becomes C024).
- **Map: floating islands and five moving 2x2 blocks.** Emptiness (tile 4) is fliers only. Scripts/C/C023.cmb (the
  turn event from turn 2, every player phase start) swaps each block between two places and carries the units standing
  on it (`UnitRescueAll`): odd turns (14,23) (10,5) (5,13) (4,24) (18,4), even turns (14,20) (10,1) (5,19) (10,24)
  (18,11) (top-left corner of each 2x2). The live grid at map+0x808 does **not** show the move, so tools/danger.py
  (scratch) takes env `PAR=even|odd` and sets the blocks itself. Route used: start island > block (14,23)/(14,20) >
  central island (its north part, rows 7-10, is cut off from the south part) > north-east island > block
  (18,11)/(18,4) > north strip; block (10,1) fills the row 1-2 gap at x 10-11 only on even turns. **A unit still on a
  block at the end of the turn is carried back**: step off on arrival (cost us one round trip on turn 16).
- **Units.** 12 deploy; Select Units took out Azura, Felicia, Gunter, Sakura (Hana, Oboro were not deployed): 8 units.
  Elise stayed on the start island all chapter (no Staff command again; Shura's Heal staff broke on turn 15).
- **Played** (danger tools of 3w with the block patch, a fresh board per read, forecasts by `prev.sh`): turn 3
  Ryoma's counter killed the Kinshi Knight, Camilla killed Scarlet; Camilla paired with Xander (whole chapter); two
  Spear Masters rode the block onto our island and died; turns 6-12 Xander baited the central and north-east groups
  (Oni Chieftains, Basara, Spear Master, Master Ninja, Mechanist); turn 14 Xander, Leo, Shura boarded block (18,11);
  turns 15-21 the north strip's east end (Masters of Arms, Onmyoji, Mechanist, the turn-16 Master Ninja, two
  Swordmasters and a Sniper that crossed the gap); turns 22-27 Basara, Onmyoji, Falcon Knights, two Masters of Arms;
  turn 27-28 Ryoma (Raijinto, range 2) brought the boss Arete to 1 then killed her (9 after her fort heal); turn 29
  Corrin seized. **Nobody lost**: 8 player units at every checkpoint. Untouched: the west and south-west islands
  (Swordmasters, Onmyoji, Sniper, Great Master, Spear Masters, reinforcements), the Merchant and Master Ninja of turn 19.
- **Undone tries** (lost unit = failed try): turn 21, a 10-HP Swordmaster walked round to Takumi (trig had listed his
  tile) and killed him: undone 4 actions to before Ryoma's attack and replayed with Xander and Ryoma blocking
  (15,2)/(14,1). Turn 24, Ryoma at (7,2) would have been in reach of two Masters of Arms and the Onmyoji (49 damage
  possible): undone 3 actions and he attacked the Basara from (8,2) instead. Also undone by act2 (no turn passed): a
  staff try with Elise (no Staff command), Shura staff tries after her staff broke, moves too long for Corrin.
- **Tool notes.** (1) The STAGE COMPLETE screen is `castle__anonymous_namespace__Seq` again (rv22 note 4): seize2's
  `until` stopped there, end1.json then reached the save menu. (2) Item drops with full bags (Swordcatcher on Xander,
  Silver Yumi on Ryoma, Snake Spirit on Xander) sent to the convoy (DOWN x5, A, LEFT A). (3) The opening victory banner
  needs one A after the opening event (the `until` waited 15,000 frames on it; kept with `--keep-failed`, no presses).
  (4) Leo's forecasts were right but his Brynhildr hit rates are low (44-83%): two misses on turn 17.
- **Route key** (splitcfg.py): routes.json `rv-ch23` = the full absolute press list from `rv-ch22-clear` (2,743
  presses, in frame order, no duplicates, equal to build/speed/rv23/export.json), frames 200166, save_at 200156,
  `verified: false`; markers.json `rv-ch23` 12 checkpoints: 6592 preparations [12, 38, 0]; 22706 turn 1 [8, 38, 0];
  41394 [8, 36, 0]; 66176 [8, 31, 0]; 96366 [8, 28, 0]; 121006 [8, 30, 0]; 156494 [8, 23, 0]; 178086 [8, 21, 0];
  197160 [8, 17, 0]; **197632 STAGE COMPLETE** ([8, 17, 0]); 199818 the save question (`GameDialogYesNo`, chapter
  C024); **200012 `castle__Sequence`**.
- **Replay check:** `tools/chk3.py` replayed export.json from frame 0 on boot-server (below normal): every checkpoint
  screen and unit count as above, and at 200032 the instruction count is **896,370,596,352, equal to c23/chain.json's
  `cycles`** (build/speed/rv23/chk.out, about 12 min). The two-copy proof, pack and capture are a separate step.
- **Time:** 22:19 (start) to 23:37 (exported press list): **about 78 min** of the 100-minute cap; replay check and
  config written by about 23:51.

## Round 24: Revelation chapter 24 (`rv-ch24`), played to My Castle (2026-11-18) [high unless tagged]

- **F-031, real play** (no pokes, no cheat save). One fresh helper, fastlook chain build/speed/rv24/c24 from frame 0 of
  `rv-ch23-clear`, one call per action, below normal. Chapter 24 'Days Lost' (map C024, `Btl_CastleInvisible_Dungeon`,
  play area x 1-23, y 1-28), normal difficulty: "locate and defeat the boss". Not the Endgame (castle after it; chapter
  id becomes C025).
- **Map: a dark dungeon.** Only the south corridor (rows 22-28) is lit at the start. Darkness regions are trick type
  0x0C (state 1 dark, 2 lit); a dark tile (7-11) is a wall until its region is lit, then it is its `change_to` tile.
  The live grid at map+0x808 does **not** change when a region lights, so tools/danger.py (scratch, rv24) now turns
  the tiles of lit regions into floor/wall/chest and an opened door (trick 0x09 state 2) into floor. Opening a door
  with a Door Key lights the next part and starts a talk. Patrols (Samurai, Spear Fighters, Ninjas, AI_MV_B009, each
  with a Door Key) raise **alarm waves** when they find us (Reinforce04_1, 05_1, 06_1, 07: Swordmasters, Great
  Masters, Kinshi Knights, Master Ninjas, Mechanists, Basara, Masters of Arms, Merchants), NearestEnemy, each appearing
  at the end of an enemy phase. **Two door pairs, one right and one wrong:** (3,12)/(6,12) and (16,2)/(13,2); the
  right one is the **blue** door (left (3,12), right (16,2)), the red one hurt every unit by about 20 HP (tried at
  (6,12): Elise left at 1 HP; undone, no turn passed). Opening (16,2) brings the boss group (Mikoto's phantom,
  Priestess, Silver Bow, 44 HP; two Master Ninjas, Oni Chieftain, Great Master), then wave 07.
- **Units.** 12 deploy; Select Units took out Azura, Felicia, Gunter, Sakura (same presses as rv-ch23): 8 units.
- **Played** (danger tools of 3w with the lit-region patch, a fresh board per read, forecasts by `prev.sh`): turn 1
  Xander baited the patrol Samurai (died on his counter; its Door Key kept, Mend sent to the convoy); turns 2-4 the
  first wave (Leo, Shura, Ryoma on the west pair, Xander on the Kinshi Knights, Ryoma and Xander on the Master Ninja and
  Merchant); turn 5 Xander opened (18,21); turns 6-9 **Xander held the doorway (18,22)** (only (18,21) and (18,20) reach
  him) against the second wave; turns 10-12 north and west; turn 12 Xander opened the right door (3,12); turns 13-18
  **Xander held the room door (3,13)** against two Masters of Arms, a Great Master, two Merchants and a Mechanist
  (Leo sniped from (4,13)); turns 19-22 east along row 11 and up x 14 to the top doors; turn 22 Elise took **Mend from
  the convoy** (Convoy next to Corrin: RIGHT, six RIGHTs to the staff tab, DOWN A A) and on turn 23 healed Xander
  (14 to 40), who opened (16,2) and held (16,3) (40 to 16 HP); turn 24 Leo killed the Oni Chieftain from (15,3)
  (100%) and Ryoma, from the door tile (16,2), killed the boss (100%, no counter: bow range 2). **Nobody lost**:
  8 player units at every checkpoint. The summary says "TURNS 24".
- **Undone tries** (lost unit = failed try): turn 17, Leo sniped a Merchant from (4,13) and Shura another from (5,13):
  Leo died in the enemy phase (two ranged attackers): undone 3 actions, Xander alone held. Turn 22, Leo (19 HP) opened
  (16,2) with Shura blocking (16,1): both died: undone 3 actions, the turn spent on Mend instead.
- **Tool notes.** (1) A level-up or a skill/weapon-rank message after a fight made act2's answer-until press A once too
  often (System Menu opened, the step rolled back); act2's attack now waits without answering and also stops on
  `ProcEffect`, `TalkKeyWait`, `GameMessage` (handled by hand: wait 450, A; or A on GameMessage). (2) `end` with the
  cursor on a unit selects it: give an empty tile (`end X,Y`). (3) Elise again had no Staff command with Physic (rank
  C needed); Mend (rank D) works. (4) Drops with full bags (a Door Key on Xander, Silver Club on Leo, Pursuer on Ryoma)
  sent to the convoy (DOWN x5, A, LEFT A); Mend sent from Xander on turn 1 (DOWN x2).
- **Route key** (splitcfg.py): routes.json `rv-ch24` = the full absolute press list from `rv-ch23-clear` (2,669
  presses, in frame order, no duplicates, equal to build/speed/rv24/export.json), frames 149388, save_at 149378,
  `verified: false`; markers.json `rv-ch24` 11 checkpoints: 9022 preparations [12, 1, 0]; 10498 turn 1 [8, 1, 0];
  26160 [8, 3, 0]; 41602 [8, 0, 0]; 66732 [8, 0, 0]; 85964 [8, 8, 0]; 105702 [8, 3, 0]; 131912 [8, 0, 0];
  **146124 STAGE COMPLETE** ([8, 5, 0]); 149030 the save question (`GameDialogYesNo`, slot 1, chapter C025);
  **149234 `castle__Sequence`**.
- **Replay check:** `tools/chk3.py` replayed export.json from frame 0 on boot-server (below normal): every checkpoint
  screen and unit count as above, and at 149234 the instruction count is **668,737,849,824, equal to c24/chain.json's
  `cycles`** (build/speed/rv24/chk.out, about 7 min). The two-copy proof, pack and capture are a separate step.
- **Time:** 00:15 (start) to 01:12 (exported press list): **about 57 min** of the 100-minute cap; replay check and
  config written by about 01:22.

## Round 30: Revelation chapter 25 (`rv-ch25`), NOT cleared (2026-11-18) [high unless tagged]

- **F-031, real play** (no pokes, no cheat save). One fresh helper, fastlook chain build/speed/rv25/c25 from frame 0 of
  `rv-ch24-clear`, one call per action, below normal. Chapter 25 'Blades Drawn' (map C025, play area x 1-30, y 1-26),
  normal difficulty: defeat the boss (Swordmaster, PID_C025_ボス, (28,13), never moves). Not the Endgame (castle after it).
  **Stopped at turn 33 player phase, frame 166789, 6 of 6 units alive, 2 of the 3 dragon veins used; no route key,
  no markers, no export** (the rest could not fit the 100-minute cap: see "What is left").
- **Map mechanics (Scripts/C/C025.cmb, read by a scratch disassembler).** The start rooms are cut off; three 5x4
  **moving floors** (field objects floor5x4_1 north, floor5x4_2 south, bossroom_1) move at every player phase start
  from turn 2, carrying the units on them (`UnitRescueAll`), unless a unit (ours or theirs) stands on the link tiles
  of the side they would leave. South floor: W (walk x 6-9, y 19-20, link (5,19-20)) > M (x 12-14, y 19-20, link
  (13,17-18) to the central hall) > E (x 18-20, y 19-20, link (19,21-22) to the south corridor) > M > W ..., one step
  per turn. North floor: W (north start room) > M (x 13-15, y 7-8, link (14,5-6) to the north corridor) > E (x 17-19,
  y 7-8, link (18,9-10) to the hall at (18,11)) > M > W. The live grid at map+0x808 never shows any of it:
  tools/danger.py (scratch, rv25) reads the current floors from build/speed/rv25/open.txt ("OPEN rects # CLOSE rects").
  **Dragon veins** (trick 0x0B) at (6,1), (7,13), (6,25), each reachable from one tile only ((7,1), (8,13)/(7,12)...,
  (7,25)); a royal's "Dragon Vein" command asks to release one of three chain locks (any choice, A). Only when all
  three are released does the boss room (bossroom_1) move north (0,-3) and open (26-28,6-7) to the north-east area;
  then it shuttles north/south each turn (south link (26-28,19-20) to the south-east area). The three 3x1 chain
  bridges (21-23, 11/13/15) do **not** open (checked: a released lock leaves the bridge impassable). Area events:
  ending in x 7-12, y 1-2 brings Reinforce03 (2 Onmyoji, Merchant at (13-15,1)); x 7-12, y 24-25 brings Reinforce04
  (2 Master Ninjas, Oni Chieftain at (17-19,25)); both act in the same enemy phase. AI_AC_Null enemies wake as a group
  when one of their group engages (the north Spear Master and two Master Ninjas, the south Onmyoji and two Oni).
- **Units.** 14 deploy (two start rooms); Select Units kept only Corrin, Takumi, Shura, Xander, Leo, Ryoma (the six
  south slots; deselecting compacts the slots, so a 7th unit would start alone in the north room). **Shura (Adventurer)
  can use staves:** Heal taken from the convoy next to Corrin (Convoy, seven RIGHTs to the staff tab, A, A) on turn 12.
- **Played** (danger tools of 3w with the floor patch, FIXED for sleeping Null enemies, forecasts by `prev.sh`):
  turns 1-2 rode the south floor to M; turns 3-11 held the 1-wide link (13,18) (Xander, Ryoma) and cleared the central
  hall; turn 8 **Ryoma used vein (7,13)** (middle lock); turns 15-16 Leo, Takumi, Shura rode the south floor to E and
  Xander, Ryoma the north floor to M; turns 16-24 south group cleared the south corridor, turn 25 **Leo used vein
  (6,25)**; turns 25-31 Corrin, then Takumi and Shura rode the north floor up and joined Xander and Ryoma in the
  pocket (13-15, 3-4) below the north corridor. HP at the stop: Corrin 38/38, Xander 43/43, Ryoma 26/43, Takumi 32/32,
  Shura 13 (lv 13), Leo 39/39 (alone at the vein (6,25), no enemy in reach).
- **Undone tries** (lost unit = failed try): turn 5, a Master Ninja crit took Corrin to 10 (undone 2 actions, no bait
  that turn). Turn 20, Ryoma at (14,2) and Xander at (11,2): Xander's tile set off Reinforce03 and the Spear Master
  (19,1) walked in: **Ryoma died**; the history was too short, so the chain was cut back to turn 20 start (inputs.txt
  to frame 109370, `fastlook clean`, 274 s; the lost line is kept in build/speed/rv25/lost_t20) and turn 20 replayed
  from (13,3)/(13,4). Turn 22, **Takumi died** at (17,23) to the Oni and Onmyoji (threat read was printed but the end
  ran in the same call): undone 1 action, Takumi went back onto the floor. Turn 27, Xander baited (13,2): the whole
  north group woke and a Master Ninja **killed Corrin** at (14,4): undone 3 actions, turn 27 replayed as a regroup.
- **What is left** (next helper, same chain or a new one): the north vein (6,1): kill the Spear Master (7,1) and the
  Master Ninjas (9,1), (10,2) (they wake together; ninjas do 0 to Xander, about 20 to Leo, 28 crit to Corrin), then
  Reinforce03; a royal on (6,1). Then the boss room via the north-east area (Falcon Knight, two Oni Chieftains, Spear
  Master (21,1), Reinforce01) or the south-east (Merchants, Kinshi Knights, Reinforce02), and the room itself (two
  Great Masters, two Snipers, two Masters of Arms, boss). Keep Corrin out of ninja reach (2 tiles of row 2).
- **Tool notes.** (1) After an attack, `plans/pe0.json` (wait until map/GameMessage/TalkKeyWait/ItemMenuSend, no
  press) is safer than lv.json: lv.json's A after a short effect opened the System Menu once (closed with B).
  (2) act2 `staff:0` picks the first adjacent ally in the game's order (Xander before Ryoma), not the one you mean.
  (3) The vein lock choice needs one A after the "Release one of the locks" banner (`plans/vein.json` twice).
  (4) Drops with full bags (Venge Katana, Venge Naginata on Ryoma) sent to the convoy (B, DOWN x5, A, LEFT A).
- **Time:** 02:19 (start) to 03:22 (stop at turn 33): **about 63 min** of the 100-minute cap; no exported press list
  (2,626 presses in c25/inputs.txt). Stopped early because the north vein fight plus the boss room (about 15 more
  turns, plus replay check and config) could not fit the cap.
- **Continuation (second fresh helper, 03:24 to about 03:45, cap 60 min), still NOT cleared.** Same chain c25 (the turn-33
  state is kept untouched in build/speed/rv25/c25_t33_backup). Turns 33-38 played, nothing lost, nothing undone except
  a stray A (pe/ga plan pressed A on the map and opened the System Menu; undone, Ryoma's attack replayed to the same
  result). What worked: (1) **Bait at (13,2)** with Xander alone (everyone else at (13,4), (15,4), (14,5), (14,6)): the
  Spear Master and both Master Ninjas came, ninjas did 0, Xander 43 -> 21, counters left them at 23/9/9; turn 34 Takumi
  (13,3), Ryoma (14,2), Xander killed all three without anyone ending in x 7-12, y 1-2. (2) **The vein needs the unit ON
  (6,1)** (from (7,1) the menu is only Items/Wait). Turn 35 Xander released the third lock (vein2.json: A, wait 400, A,
  until map). (3) **Standing on the Reinforce03 tiles (13,1) Shura, (14,1) Ryoma, (15,1) Corrin blocked it: it never
  came.** (4) The north floor left M on turn 35 (nobody on (14,5-6)): the pocket is now rows 3-4 only. (5) Corridor
  hold: the east row 1 is one tile wide at x 18-22, so Xander on (19,1) can be hit by at most two enemies ((20,1) and
  (21,1)); turns 37-38 his counters plus Takumi from (18,1) (bow vs the Falcon Knight), Ryoma (Raijinto range 2) and
  Xander killed the Falcon Knight, both Oni Chieftains, both Mechanists and a Basara (Reinforce01 from (29,1-3)) and the
  east Spear Master. **The north and north-east are now empty**; the boss room shuttles (north at odd turns, boss
  (28,10); south at even, boss (28,16)) with its six guards and the boss untouched.
- **Why stopped: Leo is cornered.** Reinforce02 (2 Basaras, a Mechanist from (29,23-25)) appeared at the turn-36 start
  (after the third vein) and walked the south corridor to Leo, who sits on the dead-end vein tile (6,25) (only exit
  (7,25)). Leo killed the Mechanist, but at the turn-39 player phase (frame 216,699, 641 lines in inputs.txt) he has
  7 HP against Basaras at (7,25) 8 HP (Steel Naginata, about 12 a round to Leo) and (8,25) 4 HP (Rat Spirit); the
  forecast says "very dangerous" both ways and the enemy hit is 89-90% (2RN): whichever he kills, the other one almost
  surely kills him next enemy phase. Nobody else can reach him. **Next helper: go back to c25_t33_backup (frame 166,789,
  state.bin included, no rebuild needed) and get Leo out of the dead end, or ready for them, before the third vein**,
  then replay the north plan above (it is robust: bait, kill, block the Reinforce03 tiles, hold the corridor).
  No route key, markers or export written.

## Revelation chapter 25 (`rv-ch25`) CLEARED: third fresh helper, from the turn-33 backup (2026-11-18) [high unless tagged]

- **F-031, real play** (no pokes, no cheat save). Chain build/speed/rv25b/c25 = a COPY of round 30's
  build/speed/rv25/c25_t33_backup (frame 166,789; c25, c25_t33_backup and lost_t20 untouched). Tools: copies of
  rv25/tools with the paths moved to rv25b (act2, danger, dz, prev, peek, hp). **Boss killed on turn 50, 6 of 6 units
  alive (Corrin, Takumi, Shura, Xander, Leo, Ryoma), save slot 1, castle (chapter id now C026: not the Endgame).**
- **Played.** Turns 33-34 = the same north plan as the continuation (same presses, same results: Xander bait (13,2),
  Takumi/Ryoma/Xander kill the Spear Master and both Master Ninjas). **Leo left the dead end first**: turn 33 to
  (14,25), turn 34 to (16,23) (moving the last unit ends the turn by itself: auto end turn). Turns 35-37 the vein was
  held back (Reinforce02 did not come at turn 36 on its own, so it is tied to the third vein); Shura healed. **The south
  floor was at M on odd turns and W/E on even ones (W on 36, E on 38)**: checked by a peek shot each time. Turn 38 Leo
  rode onto the floor at E (18,19) and Xander used the third vein on (6,1) the same turn; turn 39 the floor carried Leo
  to M and he walked into the hall; turn 41 **Leo stood on the hall link (13,18), so the floor stays at M and
  Reinforce02 (two Basaras and a Mechanist at (29,23-25), AI Everytime) never reached anyone** (they never moved).
  Reinforce01 came at turn 39-40. Turns 40-43 the row-1 corridor hold ((19,1), Xander, then Ryoma): Reinforce01, both
  Oni Chieftains and the Falcon Knight (Takumi's bow, 97%) died (the Spear Master on turn 38). Turns 44-47 the boss room guards
  (AI AttackRange, all wake together when one engages) were drawn out with Ryoma on (25,3) and held at the corridor
  mouth with Xander on (22,1): both Snipers, both Masters of Arms, both Great Masters died.
- **The boss moves.** units.csv says AI_MV_Null for PID_C025_ボス, but after the guards died it walked out of the north
  room (28,10) to (26,6) and **killed Ryoma** at (26,5) on turn 47 (my open.txt had the room south: a wrong board).
  Undone: inputs.txt cut to frame 241,519 and `fastlook clean` (765 s); the lost line is kept in rv25b/lost_t47. Then:
  turn 48 Shura healed Xander to 44, turn 49 (room north) **Xander alone baited at (27,4)**: the boss came out to (28,4),
  hit him to 35 and was left at 15 by his counters; turn 50 **Ryoma (Raijinto, range 2, no counter, 77%) killed it**.
- **Room shuttle.** The boss room moves every player phase start unless a unit stands on the link of the side it would
  leave: a Great Master on (27,7) kept it north one extra turn (45), so the parity changed (north on even turns 40-44, odd
  turns from 47). Read the boss's tile at each turn start before trusting open.txt.
- **Route key** (splitcfg.py via rv25b/tools/cfg.py): routes.json `rv-ch25` = the full absolute press list from
  `rv-ch24-clear` (3,760 presses, frame order, no duplicates, equal to rv25b/export.json), frames 255171, save_at
  255161, `verified: false`; markers.json `rv-ch25` 11 checkpoints: 9682 preparations [14, 39, 0]; 26018 turn 1
  [6, 39, 0]; 166789 turn 33 [6, 17, 0]; 180507 [6, 14, 0]; 197687 [6, 19, 0] (3 veins); 222173 [6, 13, 0]; 240487
  [6, 8, 0]; 249775 [6, 7, 0]; **252023 STAGE COMPLETE** (`castle__anonymous_namespace__Seq`, [6, 6, 0]); 254667 the
  save question (`GameDialogYesNo`, chapter C026); **254861 `castle__Sequence`**.
- **Replay check:** rv25b/tools/chk3.py replayed export.json from frame 0 on boot-server (below normal): every
  checkpoint screen and unit count as above, and at 255171 the instruction count is **1,143,455,954,256, equal to
  c25/chain.json's `cycles`** (rv25b/chk.out, about 12 min). The two-copy proof, pack and capture are a separate step.
- **Proof** [high, round 31 proof step, 05:10-05:44]: all 11 checkpoint frames were already in the shot list.
  `parallel.py runs --route rv-ch25 --copies 2 --markers --keep --timeout 3600` (FEF_ROBOT_JOBS=4, session
  r31-proof-rv-ch25): both copies exit 0, Completed after 255171 frames, **memory 725c1eedaa7b2e9a both, instructions
  1,143,455,954,256 both** (equal to the chain), checkpoints all met, 1,061 s, %APPDATA% unchanged. `rv-ch25-clear.zip`
  packed from copy 1. Capture r31-cap-rv-ch25 (`--mode capture --markers --only all --store-keep`, current library,
  not rebuilt, FRESH 2026-11-18T00:03:44): PASS, same memory, 182 functions, **4,209 records (4,082 match, 112 gave
  up, 15 incomplete), 0 bad of any kind**, no writer stored, records kept. Route set `verified: true`.
- **Time:** 04:08 (start) to 04:56 (exported press list): **about 48 min** of the 100-minute cap (13 min of it the
  `clean` after the lost Ryoma); replay check and config written by about 05:10.

## Revelation chapter 26 (`rv-ch26`), played to My Castle (2026-11-18) [high unless tagged]

- **F-031, real play** (no pokes, no cheat save). One fresh helper, fastlook chain build/speed/rv26/c26 from frame 0 of
  `rv-ch25-clear`, one call per action, below normal (tools: copies of rv25b/tools with the paths moved to rv26).
  Chapter 26 'The Vallite King' (map C026, play area x 1-25, y 1-28: row 29 is outside, the cursor stops at 28),
  normal difficulty, "defeat the boss". **Not the Endgame**: castle after it, chapter id now C027.
- **Map.** One big hall. Five 2x2 **pools** (trick 0x0C) send waves (normal: 1-2 units each): south (13-14,26-27)
  Malig Knights, south-west (1-2,20-21) Sorcerers, south-east (24-25,23-24) Heroes, north-west (2-3,4-5) Great
  Knights, north-east (24-25,4-5) Berserkers; first waves seen from turn 7 (Great Knights). Each pool has a **vein** (trick
  0x0B) on one of its tiles ((13,26), (2,21), (24,24), (3,5), (24,5)); a royal standing on it gets "Dragon Vein" (top
  of the menu; A, then A on the yellow area: plans/vf.json) and the pool freezes into an Ice Patch (state 2). The live
  grid keeps the water tile 8: **tools/danger.py (scratch, rv26) now turns a frozen pool into ice (tile 7, floor)**,
  without it a Bow Knight's path through the ice was missed and Takumi was lost in a look-ahead. A freeze lasted from
  turn 1 to turn 8 (a Malig Knight came out on turn 9); Corrin froze it again on turn 9. The C024 darkness patch is now
  only for C024. Corrin's guard tile **Ward** (avoid 40, heal 20%) follows Corrin. The boss **Gunter** (Great Knight,
  45 HP, Brave Lance, Tomahawk, Bifrost) **never left the throne (13,4)** although Xander stood in his reach: use
  `FIXED="13,4"`. Thirteen NearestEnemy movers (Paladins, Generals, Bow Knights, Wyvern Lords, Sorcerer, Hero, Dark
  Knight) rush the start; the rest are AI_MV_Null but walk up to hit anything in their reach.
- **Units.** 16 deploy; Select Units kept Corrin, Takumi, Shura, Xander, Leo, Ryoma (A on Select Units, DOWN DOWN A
  RIGHT A RIGHT A DOWN A LEFT A LEFT A DOWN A RIGHT A RIGHT A DOWN, then LEFT LEFT A for Laslow; B, START, LEFT A).
- **Played** (danger tools of 3w, a fresh board per read, forecasts by `prev.sh`; Y on the forecast switches Corrin's
  weapon): turn 1 Xander froze the south pool; turns 2-4 killed the first movers in the south pocket; from turn 4
  **three pairs** (Pair Up is the 4th or 3rd command; the mover becomes the support): Corrin+Takumi, Xander+Leo,
  Ryoma+Shura, so only three units can be hit; turns 5-13 the Paladins, Generals, Wyvern Lords, Great Knights, Heroes
  and Sorcerers died on Xander's and Ryoma's counters and attacks; turns 14-23 **Xander alone baited one group at a
  time** (place.py tiles with one threat: the Dark Knights, the Wyvern Lord and General, the Berserkers) while the
  rest stayed out of reach; **Switch** keeps the command menu open, so a pair can switch and then use the new lead's
  Staff/Attack (Shura healed Leo twice that way, Takumi's bow killed a Malig Knight); Separate places the support on a
  chosen side. Turn 24: Xander from (13,5) (boss 45 to 15), Ryoma (lead, Raijinto from (13,6), 69%) to 3, Leo from
  (12,5) with **Xander's dual strike** killed him (unpaired attacker, unpaired neighbour). **Nobody lost**: 6 of 6.
  The summary says "TURNS 25" (my own count of player phases was 24; not checked further).
- **Undone tries** (lost unit = failed try, turn-start copies in build/speed/rv26/bk): turn 2, Corrin (res 7) left on
  (13,24) died to the Sorcerer (Ginnungagap) and a General: undone, Corrin moved away. Turn 3, Takumi died to a Bow
  Knight that reached (13,28) over the frozen pool (the tool bug above): undone, Takumi to (17,27). Turn 4, Takumi and
  Corrin both died to three Paladins and a Wyvern Lord in the open: undone to the turn-4 start and played with pairs.
  Lost lines kept in rv26/lost_t2, lost_t3, lost_t4.
- **Tool notes.** (1) A move to an unreachable tile (row 29, or past the unit's move) stops act2 and is undone, but
  a.sh still exits 0: check its last line before chaining the next step. (2) Battle scenes: `plans/pe6.json` (wait up
  to 6000 frames, no press) instead of pe0 (600). (3) Boss talk before the fight: `plans/ans.json` (answer on). (4)
  The Stage Complete banner needs one A (plans/fin3.json), then talk to ChapterFileMenu, slot 1 (sv.json), LEFT A
  (svy.json) to the castle. (5) place.py prints only TOP=25 tiles unless `TOP=300` is set.
- **Route key** (splitcfg.py via rv26/tools/cfg.py): routes.json `rv-ch26` = the full absolute press list from
  `rv-ch25-clear` (1,644 presses, frame order, no duplicates, equal to rv26/export.json), frames 136970, save_at
  136960, `verified: false`; markers.json `rv-ch26` 9 checkpoints: 11050 preparations [16, 34, 0]; 13294 turn 1
  [6, 34, 0]; 35304 [6, 29, 0] (vein 1); 66300 [6, 23, 0] (3 pairs); 97162 [6, 23, 0]; 125668 [6, 19, 0];
  **130902 STAGE COMPLETE** (`castle__anonymous_namespace__Seq`, [6, 18, 0]); 136466 the save question
  (`GameDialogYesNo`, chapter C027); **136660 `castle__Sequence`**.
- **Replay check:** rv26/tools/chk3.py replayed export.json from frame 0 on boot-server (below normal): every
  checkpoint screen and unit count as above, and at 136970 the instruction count is **613,781,197,920, equal to
  c26/chain.json's `cycles`** (rv26/chk.out, about 8 min). The two-copy proof, pack and capture are a separate step.
- **Time:** 05:44 (start) to 06:44 (exported press list): **about 60 min** of the 100-minute cap; replay check and
  config written by about 06:55.
- **Proof** [high, round 31 proof step, 06:54-07:18; written here by the integrate step]: all 9 checkpoint frames
  were already in the shot list. `parallel.py runs --route rv-ch26 --copies 2 --markers --keep --timeout 3600`
  (FEF_ROBOT_JOBS=4, session r31-proof-rv-ch26): both copies exit 0, Completed after 136970 frames, **memory
  38a9a2ef1212db20 both, instructions 613,781,197,920 both** (equal to the chain), checkpoints all met, 697 s,
  %APPDATA% unchanged. `rv-ch26-clear.zip` packed from copy 1 (8,104 bytes). Capture r31-cap-rv-ch26 (`--mode
  capture --markers --only all --store-keep`, current library, not rebuilt): PASS, same memory, 185 functions,
  **4,180 records (4,028 match, 110 gave up, 42 incomplete), 0 bad of any kind**, no writer stored, records kept.
  Route set `verified: true`.

## Revelation chapter 27 (`rv-ch27`), NOT cleared (2026-11-18) [high unless tagged]

- **F-031, real play** (no pokes, no cheat save). One fresh helper, fastlook chain build/speed/rv27/c27 from frame 0 of
  `rv-ch26-clear`, one call per action, below normal (tools: copies of rv26/tools with the paths moved to rv27,
  `MAPFILE=C027.bin.lz`; the C026 pool and floor patches in danger.py stay off for C027). Chapter 27 'Hear My Cry' (map
  C027, play area x 1-26, y 1-29), normal difficulty, "defeat the boss". Not the Endgame, but no castle after it (the
  next stop is Endgame preparations). Same six units as chapter 26 (same Select Units presses: plans/sel.json); the goal
  screen after Fight needs one A (plans/f2.json).
- **Stopped, not cleared**: turn 35, frame 182,168, 1,110 presses, **6 of 6 alive**, at about 67 minutes (07:18 to
  08:25) because the boss could not be reached inside the cap. No routes.json / markers.json key, no export.
- **Map** (units.csv from `tools/maps/maps.py export C027 --out build/speed/rv27/maps`, scratch, not tracked). Boss
  Silent Dragon (13,1), 80 HP, Def 22, Res 15, breath range 1-3, AI_MV_Null, in a 3-tile niche (12-14, 0-1); three
  Generals (Def 34) and three Sorcerers next to it are AI_MV_Null and **never moved in 35 turns**. Sixteen
  NearestEnemy movers rush the start. Rubble (tile 2) and pillars (5) block everyone. **Spawn pools never stop**: the
  2x2 corner pools send four-unit groups (SW turns 9, 18, 27; SE 12 and 28; NW 17 and 33; NE 21) and the thirteen
  single pools (tile 6 with a vein, trick 0x0B, e.g. (20,18), (20,11), (19,14)) each send one strong unit, all on turn
  15-16 and again on turn 31. Sealing them with veins (a royal on the tile) was not tried.
- **The corridor cork.** From the start room a corridor runs south: (13-15,15-17), (13-15,18), (12-14,19), (13-14,20),
  then one tile wide (13,21)-(13,22) into the south room (heal tiles (13-14,26-27), 20%). A pair on **(13,22)** can be
  hit only from (13,21) (melee) and (13,20) (range 2), so at most two attacks per enemy phase. Xander as lead (Def 32)
  held it best; Ryoma (Raijinto, range 1-2, counters both) also did; Corrin (Def 16, Res 7) went from 38 to 3 there in
  one phase. The south room has two more one-tile entrances, (7,19)-(7,20) west and (20,19)-(20,20) east; enemies
  that cannot pass the cork walk round through them in 2-3 turns. Most of both big waves died on cork counters.
- **Undone tries** (lost unit = failed try): turn 17, Corrin as lead on (14,19) died to a Basara, a Mechanist and a
  Falcon Knight: undone to the turn-17 start (lost line kept in rv27/lost_t17). Turn 18, Corrin as the cork came out at
  3 HP: not a loss, but abandoned and redone with Ryoma as the cork (rv27/lost_t18). Turn-1 lesson: a danger read
  must include the planned moves (gz.py `=A,B>C,D`); at the start our own units blocked the corridor, dz showed it
  safe, and two Bow Knights hit Takumi and Leo once we moved.
- **Healing.** Shura's Heal staff (2 uses) ran out on turn 12. Ryoma carries **Sun Festal (夏祭, 15 uses, range about
  2)**: Switch the pair so Shura leads, Trade (UP picks the own partner), move Sun Festal across, then Staff: a heal
  from two tiles away (+19 to +21). The lead of a pair is the only one a staff can target.
- **Menus.** The Switch row moves with the menu (Attack, Staff, Items, Trade, Convoy, Transfer show up depending on
  the tile): take a peek shot before each Switch. Moving onto a partner shows a pair preview and needs one more A
  (plans/pt.json). The HP number on a forecast is the HP after the worst exchange, not the current HP.
- **Kept states**: build/speed/rv27/c27 = c27_t35_backup (turn 35; Corrin 23/38 lead at (11,23) next to a Master of
  Arms and a Basara, Xander 40/44 lead (Leo 4/41) on the cork, Ryoma 23/44 lead (Shura 21/36)); **c27_t20_backup** (turn
  20, frame 108,780: the first wave dead, nobody in reach, Ryoma 15, Xander 34 lead, Corrin 38). Next: from the
  turn-20 backup, march north at once (Xander or Leo lead in front), seal the single pools with veins on the way, and
  kill the boss from (12,1)/(14,1)/(13,2) range with Ryoma, Leo and Xander in one player phase.

### rv-ch27, second helper: from the turn-20 backup, still NOT cleared (2026-11-18) [high unless tagged]

- **F-031 real play**, no pokes, no cheat save. Copy chain build/speed/rv27/c27r from c27_t20_backup (the old c27,
  c27_t20_backup and c27_t35_backup were not touched); tools: rv27/tr/*.sh = the rv27/tools shell tools pointed at
  c27r. Cap 60 min; played 08:27 to about 08:55 (about 28 min), then stopped to write up. **Not cleared**, no route
  key, markers or export.
- **Kept state: build/speed/rv27/c27r_t26_backup** (= c27r): turn 26 start, frame 141,736, **6 of 6 alive**: Corrin
  20/38 lead (Takumi 13) at (13,23), Xander 28/44 lead (Leo 27) at (13,22), Ryoma 10/44 lead (Shura 36) at (13,21).
  Killed on turns 20-25 (mostly on counters at the (13,22) cork): the Oni Chieftain, the Kinshi Knight, the west group
  (Berserker, Brave Hero, Maid), a Basara, and the whole north-east wave of turn 21 (Revenant Knight, Dark Knight, Bow
  Knight, Great Knight). Still coming: a Paladin, a Sorcerer (Fire), an Onmyoji, an Adventurer and a General from the
  north-west single pools, a Great Master (山伏, Str 28, silver naginata) behind us in the south room, a Merchant, and
  the south-east group (Basara, Master of Arms, Master Ninja, Swordmaster), which appears at the start of turn 27.
- **What worked.** Turn 20 all north (the "AI_MV_Null" look of the west group was wrong: they rush once we get near).
  Xander at the (13,22) cork with a Sun Festal heal first (Switch so Shura leads, Trade: UP picks the partner, RIGHT,
  DOWN x4, A, A, B; then Staff, A A A): 39 HP Xander killed the Revenant Knight and Dark Knight on counters in one
  enemy phase. Ryoma's Raijinto from range 2 kills a Brave Hero, Berserker or Paladin with no counter (26-29 x2, 100%).
  Shura (Adventurer) has no Attack next to an enemy: his axe, lance and shuriken are greyed out, only the bow (range 2).
  Takumi cannot use Sun Festal (no Staff command).
- **Lost tries, all undone** (copies: rv27/lost_r_t22, lost_r_t22b, lost_r_t27): turn 22 twice, Takumi as lead (13 HP)
  in the (12,19) pocket died (first to the Maid and Basara, then to the Kinshi Knight from (13,20)); fix: no Switch to
  Takumi on turn 21, Corrin's pair goes back behind the cork. Turn 27, Corrin (20 HP) at (13,18) with only "1 threat"
  (the Great Master) and Xander at (13,12) both died in one enemy phase. **Lesson: a weak lead (Corrin Def 16 Res 7,
  Takumi Res 5) must stand on a 0-threat tile; one threat is enough to kill it.**
- **Why stopped.** At turn 27 every tile Corrin's pair can reach is threatened (Paladin north, Great Master south), Ryoma
  is at 10 HP and both casters reach him, and Leo's 89% shot on the Paladin missed in the test line. With 2-3 more
  turns of fighting plus 3-4 turns of marching before the boss, the chapter could not fit the cap. Next: from
  c27r_t26_backup, spend turn 26 healing (Shura leads Ryoma's pair and uses Sun Festal every turn), keep Corrin's pair
  south of a cork with no threat, and let the north-west group come to Xander/Ryoma counters before marching.

### rv-ch27, third helper (round 32): from c27r_t26_backup, still NOT cleared (2026-11-18) [high unless tagged]

- **F-031 real play**, no pokes, no cheat save. Own folder build/speed/rv27h: chain **c27h** = a copy of
  rv27/c27r_t26_backup (the rv27 folder, c27, c27r and every backup there untouched); tools = copies of rv27/tools and
  rv27/tr with the paths moved to rv27h (act2.py TOP, *.sh), plus gzf.sh (gz.py with FIXED = boss, 3 Generals,
  3 Sorcerers, 2 Adventurers). Cap 100 min; played 09:18 to 10:05 (about 47 min), then stopped: every line from the
  turn-34 start lost a unit. **Not cleared**: no route key, markers, export or replay check.
- **Kept state: build/speed/rv27h/c27h_t34_backup** (= c27h now): turn 34 start, frame 191,054, 496 press lines,
  **6 of 6 alive**, cheat false. Xander 25/44 lead (Leo 27) at (12,19) (the dead-end pocket west of (13,19)); south
  room: Corrin 37/38 lead (Takumi 10/32) at (12,28), Shura 36/36 lead (Ryoma 10/44) at (14,28). Enemies next to the
  south pairs: Swordmaster (silver katana, 48) (13,26), Master of Arms (54) (13,27); in the 1-wide corridor Merchant
  (silver naginata + steel yumi, 53) (13,22) and Swordmaster (iron, 48) (13,21); Oni Chieftain (49) (7,18). North of
  Xander: Falcon Knight 16, Mechanist 15, Master Ninja 11, Basara 25; the turn-33 north-west group (Maid, Berserker,
  Hero, Wyvern Lord) at x 2-11, y 9-13.
- **Killed turns 26-33** (in the kept line, around (13,19)-(13,22)): Great Master (Takumi range 2, Xander range 2,
  Shura's bow finished it), Paladin (Ryoma range 2), General (Xander), Merchant (iron) (Xander, doubles, 100%),
  Adventurer (Xander), Sniper, silver Master of Arms and silver Master Ninja (Xander counters); the Fire Sorcerer and
  the Onmyoji were gone by turn 28 (not checked how) [medium].
- **Learned** [high]: (1) the game has **auto end turn**: after the last unit acts the enemy phase runs at once (use
  a long `until` after the last action; 3000 frames is too short). (2) **Siegfried and Raijinto hit at range 2**: Xander
  and Ryoma attack at range 2 with no counter from melee units; Ryoma's two hits killed a 39-HP Paladin (98%). (3)
  **Omega Yato**: equip it (Items, A, Equip): +4 Str/Spd/Def/Res, doubles a Merchant for 16 x2; Corrin's Silver Sword
  does 8. In the forecast, **Y cycles the weapon** (R does nothing). (4) **Transfer** (pair next to a pair) swaps the
  two supports (Takumi <-> Ryoma) and does not end the action; with Switch after it, Ryoma can lead the other pair and
  be healed by Shura the same turn (Ryoma 10 -> 29). (5) Sun Festal range 2, heals the target pair's lead to full or
  +19. (6) **The danger tools undercount here**: they do not add enemy dual strikes (enemies in attack stance next to
  the attacker) and the movers reshuffle; Corrin at 37 HP died on a tile gz showed with 2 threats, Shura at 36 on
  tiles with 2.
- **Lost tries, all undone** (copies: rv27h/lost_t31 = Corrin dead turn 32 at (13,21); lost_t34, lost_t34b = Shura
  dead turn 34): turn 31 Corrin (37) as the second unit at (13,20) behind Xander; turn 32 Corrin (37) at (13,21) after
  killing the Adventurer; turn 34 Shura (36) healing Ryoma from (14,28), from (12,28), and Shura simply waiting at
  (14,28): the Merchant and the Master of Arms (with dual strikes) kill a 36-HP Shura every time.
- **Why stopped.** At turn 34 the party is split (Xander north of the corridor, four units in the south room) and
  the south room has no tile out of reach of the Merchant and Master of Arms; the two possible leads besides Corrin
  are Shura (no melee counter, low Def) and Ryoma/Takumi at 10 HP. Every tried line loses one; the boss (13,1) is
  still about 20 tiles away and pools keep sending units. Next: do not split the party. From c27h_t34_backup the
  likely way is to give up the Swordmaster kill and use Transfer + Switch so Corrin (Omega Yato) and a healed Ryoma
  lead; or restart from c27r_t26_backup and keep all three pairs together north of the corridor at (13,19)-(14,20)
  (Xander and Corrin's pair at the front, Shura healing every turn), never sending pairs back into the south room.

### rv-ch27, fourth helper (round 32): from c27h_t34_backup, still NOT cleared (2026-11-18) [high unless tagged]

- **F-031 real play**, no pokes, no cheat save. Own folder build/speed/rv27i: chain **c27i** = a copy of
  rv27h/c27h_t34_backup (rv27, rv27h and every backup there untouched; checked rv27h/c27h_t34_backup = rv27h/c27h
  afterwards); tools = copies of the rv27h tools with the paths moved to rv27i/c27i. Cap 60 min; played 10:06 to
  10:42 (about 36 min), then stopped to write up. **Not cleared**: no route key, markers, export or replay check.
- **The turn-34 fix (worked, nobody lost):** the south room's only Merchant-proof tile is the corner **(16,28)**
  (the Merchant moves 6 and every tile within 2 of (16,28) is 7+ steps from (13,22) through the 1-wide corridor;
  row 29 is NOT walkable although gz/danger draw it). Turn 34: Corrin's pair moves to (15,28), **Transfer** with
  Shura's pair (now Corrin+Ryoma and Shura+Takumi), **Switch** (Ryoma leads), Wait; then Shura's pair moves to
  (16,28) and heals Ryoma (Staff is the first menu row there) to 29; Xander waits. Enemy phase: Ryoma killed the
  Master of Arms on counters, the Merchant went north and died on Xander's counter later, Shura 36 -> 11 (one
  attacker only), all alive. Turn 35: Ryoma kills the silver Swordmaster at range 2 from (15,28) (89%, Shura dual
  strike), Shura heals Ryoma again. After that Ryoma (Raijinto range 2, 100% forecasts, skull = kill) cleaned the
  room: Oni Chieftain from (13,26), Wyvern Lord, Hero from (13,24), Malig Knight from (17,23); Leo (Switch to lead in
  Xander's pocket (12,19)) killed the Kinshi Knight, the Master Ninja and the Basara; Xander killed the Mechanist.
- **Learned** [high]: (1) the three earlier ways lose Shura every time (heal from (12,28) or (14,28), or Shura as
  Corrin's lead after Transfer): with the Merchant and a Master of Arms both reaching him, a 36-HP Shura dies.
  (2) **Separate ends the lead's action and the dropped unit is done too** (selecting it opens the system menu), so
  it cannot be used to hide a healer. (3) Moving a staff user with the cursor ending on a hurt ally opens the heal
  preview straight away (and the unit heals from where it stands). (4) The convoy has only Vulneraries (3+1, +10 HP),
  a Master Seal and a Heart Seal as items. (5) Leo's attack opens a weapon screen first: `A` (Attack) then `A`
  starts the battle on the first target; RIGHT before the second `A` picks the next target. (6) The pools sent more
  units on turns 39-41 (a Paladin at (1,20), a Great Master, an Onmyoji, a Merchant at (20,18), and a south-east four
  (Basara, Master of Arms, Master Ninja, Swordmaster) at (24-25,23-24) on turn 41).
- **Lost tries, all undone** (copies kept: rv27i/lost_t34s, lost_t34s2, lost_t34s3, lost_t41, lost_t41b): turn 34
  three times (Shura dead, see above); turn 41 twice: Shura 11 HP dies to the Great Knight (left at 1 HP by Ryoma and
  then healed to 26 by the Maid's Mend) or to the Maid (silver dagger, moves 6, range 1-2) when he kills the Great
  Knight from (14,26).
- **Kept states** (all 6 of 6 alive, cheat false): c27i_t35_backup .. c27i_t40_backup, and **c27i_t41_backup** (= c27i
  now): turn 41 start, frame 238,284, 591 press lines. Corrin 37 (support) + Ryoma 44 lead at (18,21); Shura 11 lead +
  Takumi 10 at (16,28); Leo 42 lead + Xander 14 at (12,19). Near: Maid 44 (13,19), Great Master 51 (13,17), Great
  Knight 53 (14,24), Paladin 51 (8,11). Next: on turn 41 keep Shura out of reach of both the Great Knight and the Maid
  (or kill the Great Knight outright: Ryoma leaves it at 1 HP alone, so add a dual strike or a second attacker), then
  heal Shura on the (13-14,26-27) tiles and march north through the cleared corridor; the boss (13,1) is still about
  20 tiles away, so the next helper needs a full cap.

### rv-ch27 on the cheat track (`cheat-rv-ch27`, F-035), CLEARED (2026-11-18, round 34) [high unless tagged]

- **F-035** (owner ~11:10: "Yes, boost it"): counted like F-030/F-033, records in the cheat table. Own folder
  build/speed/rv27x: chain **c27x** = a copy of rv27i/c27i_t41_backup (state.bin sha256 f1e3ce0e... equal; rv27, rv27h,
  rv27i and every backup there untouched); tools = copies of the rv27i tools with the paths moved to rv27x/c27x, KEEP=12
  undo snapshots, FEF_ROBOT_JOBS=4 (2.64 GB), below normal; danger.py reads the move bonus as the s8 at Unit+0x12C
  **uncapped** (as cqx17); poke.py = cqx17's (cheats.apply); new try.sh / mv.py / plan2.py (run a plan, shot, restore the
  chain files). Cap 100 min; played 13:12 to 13:30 (**18 min**).
- **The poke** (movement only, frame 238284 = turn 41 player phase, read before the poke): the 6 units' `unit:N +0x12C`
  0 -> 30 (expect 0): Corrin 1, Ryoma 25, Leo 41, Xander 43, Shura 27, Takumi 21. Nothing else poked.
- **How it was won** (turns 41-42, nobody lost): turn 41 Ryoma's pair (Corrin support) went round through the south room
  and killed the Maid that closed Leo's pocket at (13,19) from (13,21) (Raijinto range 2, 100%, skull); Leo's pair moved
  to (24,4) and Shura's to (25,8) (the north-east room, 0 threats); in the enemy phase the Great Master and the Great
  Knight died on Ryoma's counters. Turn 42 Shura healed Ryoma from (13,23) (Sun Festal, 34 -> 44), Ryoma hit the boss
  (Silent Dragon (13,1)) from (13,3): 80 -> 29; Leo waited at (24,4); in the enemy phase the boss attacked Ryoma and died
  on his counter: stage complete 253108, 6 of 6 alive.
- **After the boss** (what the game shows): the STAGE COMPLETE banner (Chapter 27 'Hear My Cry', **43 turns**, heroes Leo
  & Xander) waits for A (253718); the closing scenes are talk screens (TalkKeyWait, answered with A); then straight to
  the **Endgame preparations** (sortie TopMenu, chapter C028, "Defeat the boss", Endgame, 13 units / 2 enemies in the
  markers) at 260860. No save question and no castle, as docs/collab/FINALES_GROK.md says. The route ends there (261200).
- **Learned** [high]: (1) the boss's guard (3 Generals, 3 Sorcerers, "AI_MV_Null") is not fixed: once a unit stands near
  the boss they move and kill weak units (Shura 11 + Takumi 10 died at (15,3); a Sorcerer from (9,6) went to (13,5) and
  killed Ryoma at 12 HP at (13,3)). (2) The boss (Atk 32 on Ryoma, 24% hit; on Leo 30, 100%; on Corrin 36, 86%) does not
  heal between turns and counters are its weak spot: with Ryoma at full HP alone in its range at (13,3), it attacked him
  and his counter took it from 29 to 0. Leo's Brynhildr does only 15-17 to it; an adjacent pair's lead gave no dual strike on Leo's attack. (3) After
  a Switch in place the pair cannot move any more (B undoes the Switch). (4) poke.py deletes last.json, so the first
  try after a poke needs a fresh `fastlook look` (else prev.sh fails and leaves a look of the try behind).
- **Lost tries, all undone** (copies: rv27x/lost_t41_shura, rv27x/lost_t41_ryoma): turn 41, Ryoma hit the boss
  (80 -> 48) and Shura healed him from (15,3): the guard killed Shura's pair (Leo 2 HP); the same with Shura's pair away
  at (25,8): the Sorcerer killed Ryoma's pair (12 HP). Both were undone to the turn-41 start (with the poke).
- **The route** `cheat-rv-ch27` (routes.json, markers.json; one checked read-modify-write of only this key,
  build/speed/rv27x/tools/wroute.py, since splitcfg refuses cheat keys): `"cheat": true`, save rv-ch26-clear, frames
  261200, save_at 261190, **2,388 presses** from frame 0 (the 2,015 real-play presses of c27i_t41_backup are a prefix),
  the 6 pokes with expect, 11 checkpoints (turn 1, turns 20, 26, 34, turn 41 read before the poke, turn 42, the boss at
  29, stage complete, the banner, the Endgame preparations, the last screen), verified false. `cheats.py --check` 14
  cheat routes, rules OK; `--selftest` 23/23.
- **Replay checks** [high]: boot-server from frame 0 with the poke applied at 238284 (tools/chk4.py, build/speed/rv27x/
  chk.out): the same screens at every checkpoint, cycles at 238284 equal to the chain's (1067783010624); then
  `parallel.py runs --route cheat-rv-ch27 --markers` (FEF_ROBOT_JOBS=4, 2.64 GB, below normal): **PASS**, exit 0,
  Completed after 261200 frames, **checkpoints all met**, memory b4025f15b3475c00..., instructions 1170472723200 (equal to
  the boot-server replay's count at 261190 plus 10 frames), boot 1405 s, peak 786 MB, %APPDATA% unchanged;
  build/parallel/runs-20261118-135605. The two-copy proof was not run (not this step).
- **Chain end for the finale (F-029):** build/speed/rv27x/c27x at frame 261210 (Endgame preparations, cheat true),
  copies c27x_t42_backup (turn 42 start), c27x_t42_mid (after Ryoma's hit), c27x_complete_backup (stage complete
  253108). No clear save is packed (no save after chapter 27); the Endgame route will start from rv-ch26-clear frame 0
  with these presses as its prefix, like cheat-bt-endgame.

### Revelation Endgame on the cheat track (`cheat-rv-endgame`, F-030/F-031/F-035), ENDING REACHED (2026-11-18, round 36) [high unless tagged]

- **Counts as Revelation played to the end** (F-030/F-031), cheat table (F-019 rule 2). Own folder build/speed/rvend:
  chain **ce** = a copy of rv27x/c27x (frame 261210, Endgame preparations; state.bin sha256 e0e665e7... equal);
  rv27x, its chain and backups not changed. Tools = rv27x's copies with paths moved to rvend; danger.py and the other
  server readers open the chain with `cheat=True` because `rv-ch26-clear.zip` now has the same save files as
  `cheat-rv-ch27-clear.zip` (packed in round 36's ch27 proof), so the fingerprint rule calls it a cheat save. Played
  15:02 to 15:13 (**11 min**); FEF_ROBOT_JOBS=4 (2.64 GB), below normal.
- **Save check first (F-029):** the preparations menu has no Save; R Options lists settings only. So the route starts
  from rv-ch26-clear frame 0 with cheat-rv-ch27's 2,388 presses and 6 pokes as its prefix (checked equal), like
  cheat-bt-endgame.
- **Map (C028, 'Anankos'):** turn 1 shows 13 player units and 10 enemies: the two hands (persons 31234 at (5,6) and
  31235 at (15,6), 61 HP, breath range 1-3) and 8 others. The ch27 movement bonus (+30, Unit+0x12C) is still on the
  6 units; it was used only to reach the parts, nobody stood on a corner.
- **Three declared poke frames, each part only after it appeared (FINALES_GROK / RV_ENDGAME_PLAN_GROK), all on turn 1:**
  | Frame | Poke (current HP `unit:P +0xF3`, expect) | Kill |
  |---|---|---|
  | 281490 (turn 1 player phase, read before) | both hands 61 -> 1 | Xander (Siegfried) from (6,7) killed the west hand (82%); Leo (Brynhildr) from (14,7) the east hand (76%) |
  | 284738 (the head 31233 appeared at (10,11), 80 HP) | head 80 -> 1 | Ryoma (Raijinto, range 2) from (10,13), 100%; talk |
  | 287822 (the core 31232 appeared at (10,11), 80 HP) | core 80 -> 1 | Corrin (Omega Yato) from (10,12), 61%, hit |
  No enemy phase was played, **13 of 13 alive, nothing undone**, no part healed back, no script blocked.
- **After the core** (what the game shows): closing talk (289060), ending events (289300), chapter records
  (ProcSequence@00626B48, 296772), epilogue cards and credits (ProcEpilogue@0062695C, 330000), **'The End'** (ProcEffect,
  ProcSequence@006269E8, from 375912; waits for a key, A at 376532), the logbook card entry (376674, A on OK), "Would you
  like to proceed?" (cursor on No: LEFT, A), **the title screen "PRESS ANY BUTTON"** (ProcSequence@00640B64) from 377020.
  The route ends there (377700). No save prompt, no hang. Left alone ~3,000 more frames, the title starts its attract
  demo (class intros, ProcJobIntro, seen at 380640): the game is still running, not a hang. One long still screen in
  the route: the objective card before turn 1 sat 20,000 frames (261436 to 281400) until A; it waits for a key.
- **The route** `cheat-rv-endgame` (routes.json, markers.json; checked read-modify-write of only this key,
  build/speed/rvend/tools/wroute2.py, since splitcfg refuses cheat keys; diff: only added lines): `"cheat": true`, save
  rv-ch26-clear, frames 377700, save_at 377690 (schema only; no clear save exists or is packed), **2,805 presses**,
  **10 pokes** (the 6 ch27 movement pokes + 4 HP pokes), **16 checkpoints** (ch27's 238284 and 253108, preparations
  261210, turn 1 before the hand pokes, west hand dead, head appeared, core appeared, after the core, ending events,
  records, epilogue, 'The End', logbook, proceed?, title, last screen). `cheats.py --check` 17 cheat routes, rules OK;
  `--selftest` 23/23.
- **Checkpoint read** (tools/chk5.py, boot-server from the chain's preparations state with the 4 pokes applied the route
  way, chk5.out): the same screens as play; instructions at 377690 = 1692480255840.
- **Capture from frame 0** (`parallel.py runs --route cheat-rv-endgame --mode capture --only all --store-keep --markers
  --session r36-capc-endgame`, below normal): **PASS**, exit 0, Completed after 377700 frames, **checkpoints all met**,
  memory f03306be7ca8af55..., instructions 1,692,525,067,200 (= the boot-server read at 377690 plus 10 idle frames),
  boot 3455 s, peak 788 MB; **183 functions, 13,063 records (12,904 match, 110 gave up, 49 incomplete), 0 bad of any
  kind**; no writer stored; %APPDATA% unchanged.
- **Two-copy proof: done at round 36 integrate, PASS** (r36-proof2-cheat-rv-endgame, `--timeout 6000`, 16:23 to 17:00: both copies exit 0, memory f03306be7ca8af55, 1,692,525,067,200 instructions, checkpoints all met; verified true). In the finale step it was **NOT done:** `parallel.py runs --route cheat-rv-endgame --copies 2 --markers --keep --session
  r36-proof-cheat-rv-endgame` failed on time, not on the game: both copies hit parallel.py's frame-scaled default
  timeout (2,386 s / 2,506 s) while the machine ran 12 boot.exe at once (other rounds' opt-t1r38, r37, zakuro-test);
  copy 1 had passed the ch27 poke frame. To do: the same command with `--timeout 6000` on a quieter machine. Until then
  `verified` stays **false**.
- Wall time: 15:02 to about 16:25, inside the 90-minute cap; the proof rerun (about 60 min) did not fit.
- **Second two-copy proof, PASS** (2026-11-18, own proof step after commit e9d2950: r36-proof3-cheat-rv-endgame,
  `parallel.py runs --route cheat-rv-endgame --copies 2 --markers --keep --timeout 6000`, FEF_ROBOT_JOBS=4, below
  normal, 17:15 to 17:42, 1,588 s wall): all 16 checkpoint frames checked in the shot list first (none missing, inputs
  and pokes unchanged, so no route edit); both copies exit 0, Completed after 377,700 frames, memory
  f03306be7ca8af55d588e85f79fdbb905d890bcdcf729d8c5153ad27900fb044, 1,692,525,067,200 instructions, checkpoints all
  met: the same as r36-proof2 and as the capture r36-capc-endgame. `verified` stays true; check_all `--only
  cheat-endgame,cheat-routes` PASS, `unittest tests.test_check_all` OK (94 tests, 1 skipped).

## Round 19 integrate (2026-11-17 afternoon) [high unless tagged]

- **Round 19 in one line.** F-030 ("just cheat and count it, the purpose of the tests is to make sure it RUNS"):
  Birthright Endgame was finished on the cheat track (3y; route `cheat-bt-endgame`, one poke at the turn-8 player
  phase, frame 193094: Garon's current HP 78 -> 1; Ryoma's first hit killed him at 195014, 16 of 16 alive, nothing
  undone). The game ran through the ending (ending scenes, chapter records, epilogue and staff credits, "The End",
  the logbook card entry) to the title screen at about 291326 and stayed there to 291636: no hang, no crash, no save
  prompt. The two-copy proof passed (r19-det2-endgame: memory 95f8384c0bf16d25 and 1,306,860,578,496 instructions
  in both copies). The proof step's capture was stopped at its 45-minute cap at frame 270614; integrate ran the
  capture again in full with every override, **0 bad**, and set `verified: true`.
- **Library:** `harness/build.py --check-fresh` said **STALE**, but only because config/harness/targets.csv has two
  new rows and two new staged files from another area's batch in progress this afternoon (strike_power
  `src/readable/strike/`, who_holds_can_equip_subkind `src/readable/who_holds/`; uncommitted, no capture of their
  own yet, docs/tracks/REWRITE_ORDER4.md). No reader of the 252 changed. Integrate did **not** rebuild: a rebuild
  would have put another area's unfinished code into the capture library during its own batch. The live run used
  the library from 04:31 (the one the proof used). [med: a judgement call, said plainly]
- **Plan** (build/speed/r19int/plan-play.txt, plan-cheat.txt; same sessions as round 18, cheat side plus
  r18-capc-weapon_level_view; r15-cap-capability left out):
  - Real play: **PLAN LINE 1, routes: 54 replay offline from their records, 0 must play live (route changed).
    PLAN LINE 2, overrides: 252 decided by the records (4 by the batches' own captures, 1 of those watched and never
    called), 2 must play live on 54 routes** (strike_power, who_holds_can_equip_subkind: the other area's two new
    rows, not in the library, so they cannot be captured yet; left to that batch's own capture).
  - Cheat: **PLAN LINE 1: 4 routes offline, 0 live. PLAN LINE 2: 252 decided (18 by the batches' own captures, 8 of
    those watched and never called), 2 must play live on 4 routes** (the same two rows; left to that batch).
    cheat-bt-endgame has no records yet, so it is not in the plan: it played live with every override.
- **Runs, started at once (from 16:18:42, FEF_ROBOT_JOBS=12):**
  - Live, cheat (`parallel.py runs --route cheat-bt-endgame --mode capture --only all --store-keep --markers
    --session r19-capc-endgameb`): exit 0, Completed after 291636 frames, all checkpoints met, memory
    95f8384c0bf16d25 (same as the proof), 1395 s, peak 781 MB; **182 functions, 6,328 records (6,170 match, 76 gave
    up, 82 incomplete), 0 bad of any kind**; no writer stored; %APPDATA% (zakuro, 3dsrecomp) unchanged.
  - Offline, real play (`r19-off --jobs 6 --no-source-gate`): 205 runs, **185,654 records (180,878 match, 3,087 gave
    up, 1,689 incomplete), 0 bad, offline verdict != captured verdict: 0**, 110 s. `--no-source-gate` because the
    gate stopped on the two staged files above (they have no records, so no verdict depends on them).
  - Offline, cheat apart (`r19-offcb --jobs 2 --no-source-gate`): 37 runs, **9,584 records (9,224 match), 0 bad, 0
    verdict differences**, 37 s.
  - **Disk:** D: ran full (71 MB free) at 16:26 and the first real-play offline replay stopped on "not enough space"
    while copying its library. Integrate removed jobs/ and lib/ (about 790 MB) of the stopped, superseded proof
    capture build/parallel/r19-capc-endgame (no summary, no records; REMOVED.txt says so) and reran the replay. D:
    had about 1.1-1.5 GB free for the rest of the step. [high]
  - Per family, real play (h6three number 3): Birthright 33 routes 112,757 records; Conquest 7, 26,262; Revelation
    12, 44,623; options 2, 2,012; **0 bad and 0 other differences in each**. Cheat apart: 5 routes, 15,912 records
    (9,584 offline plus 6,328 live), 0 bad.
- **H5** (`h56.py h5 --sessions <round 18's fourteen> --label play --run-id r19-h5 --no-exact --jobs 12
  --jobs-over-budget`): 2 min 46 s; **218 of 254 met** (the two new rows count as never met), 185,654 records, 0 bad,
  offline != live 0; lines 1,368/1,583, branches 955/1,492 (64.0%). `check_all --only h56-h5` alone: PASS, 95 s.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r19-off/offline.json --offline-cheat build/speed/replay/r19-offcb/offline.json --live
  build/parallel/r19-capc-endgameb/summary.json --json build/h6three/three-r19.json`): (1) 2,214 / 3,696 (59.9%;
  62.9% also leaving out helper lines), still round 13's sample; (2) host test alone 3,700 / 4,009 (92.3%), records
  or host 92.6%, 36 files with a host test, 0 without; (3) 54 routes, 185,654 records, 0 bad; cheat 5 routes, 15,912
  records, 0 bad. Equivalent candidates: 237 plus 70 unsorted, unchanged.
- **routes.json**: `cheat-bt-endgame` `verified` false -> true, by a checked read-modify-write (re-read just before
  writing; every other key and the file's format equal; no final newline, as before). Nothing else changed.
  `cheats.py --check`: 5 cheat routes, rules OK; 56 real-play start saves, none carries cheat state.
- **check_all** (docs/CHECK_ALL.md round 19): new row `cheat-endgame`. Fast 41 pass; touched rows (selftest,
  cheat-endgame, cheat-routes, robot-routes) 4 pass; h56-h5 pass. 79 slow/medium rows left for the weekly run.
- **Other areas this afternoon (not this step's work):** robot-routes now counts 55 verified real-play routes because
  round 20 (F-031) set rv-ch18 verified; cq-ch13 is still unverified. Integrate did not play or change them.
- **Evidence**: `evidence.py pack` (117.4 MB in all; new: r19-capc-endgameb 0.5 MB, r19-det2-endgame 0.9 MB, the
  stopped r19-capc-endgame 0.0 MB). `clean --keep-sessions 10 --keep <every r10-r19 session> --keep r15-h5 ...
  r19-h5`: the dry run (with --force, because other areas' boot.exe were running) would free 0 items, so `--yes` was
  not run.
- **Measured.** Integrate 16:17 to about 16:48 (about 31 min, cap 60): reading, freshness and both plans 4 min; the
  live Endgame capture 23 min 15 s (16:18:42 to 16:42), with everything else beside it: H5 2 min 46 s, the first
  offline pair stopped by the source gate (16:21-16:22), the cheat replay 37 s, the real-play replay failed on the
  full disk and ran again in 110 s (16:29:37 to 16:31:28); new row and tests written beside (about 5 min); fast pass
  46 s; touched rows 58 s; h56-h5 row 1 min 35 s; three-number report under 1 s; evidence pack under 1 min; docs
  and report about 6 min. Idle compute [med]: from 16:35 to 16:42 the one Endgame capture was the only game running
  (1 of 12 slots); a single long route cannot be split.

## Round 21 integrate (2026-11-17 evening) [high unless tagged]

- **Round 21 in one line.** Two reader batches from Grok's docs/tracks/REWRITE_ORDER4.md, side by side, beside
  rounds 19 and 20 (owner 2026-11-17 ~15:45, "yes, ask Grok and start it"): row 1 `strike_power`
  (map::BattleInfo::Side::GetSimplePower, 0x005253A8, docs/STRIKE.md; 35/35 planted bugs, 0 mismatches) and row 2
  `who_holds_can_equip_subkind` (Job::CanEquipFromSubKind, 0x00524420, docs/WHO_HOLDS.md; 24/24, 0 mismatches).
  Both read only. Registry: row 0x005253A8 changed from the stance helper `stance_follow_up_damage` to the override
  `strike_power` (the change docs/BATTLE2.md section 3 planned; the helper stays a C function that strike_power
  calls; accepted on review, still for the owner to see). No game play of rounds 19/20's routes here.
- **Library:** `harness/build.py --check-fresh` **FRESH** (built 2026-11-17T16:48:32 by the who_holds capture step,
  254 overrides, 62 guard users, 54 staged files; both new readers in it). Integrate did not rebuild, so no reader
  needed a second capture. (Integrate briefly edited three source comments, saw the risk to the library hash, and put
  them back with `git checkout` before anything read them; check-fresh still FRESH.)
- **Batch captures** (already done by the batches' capture steps, no retry needed): `r21-cap-strike` (bt-ch2, 18
  records, 17 match, 1 gave up, 0 bad, memory 059736d328d99c29 = earlier bt-ch2 runs) and `r21-cap-who_holds` (6
  Birthright routes, 140 records, 134 match, 6 gave up, 0 bad, every memory hash = the route's earlier hash).
- **Plan** (build/speed/r21int/plan-play.txt, plan-cheat.txt):
  - Real play (`--sessions r10-capb,r11-capn,r11-capo,r12-capn,r13-capn,r14-capn,r15-capn --extra-sessions
    r12-cap-class_change,r12-cap-weapon_rank,r13-cap-shop_price,r14-cap-equip_use,r14-cap-staff_range,
    r15-cap-capabilityb,r16-cap-shop_grey,r18-cap-weapon_level_view,r21-cap-strike,r21-cap-who_holds --label play`;
    r15-cap-capability left out): **PLAN LINE 1, routes: 54 replay offline from their records, 0 must play live
    (route changed). PLAN LINE 2, overrides: 254 decided by the records (6 by the batches' own captures on 51 routes,
    1 of those watched and never called), 0 must play live.**
  - Cheat (`--sessions r10-capc,r11-capc --extra-sessions r12-capc-class_change,r12-cap-weapon_rank,
    r13-capc-shop_price,r14-capc-readers,r15-capc-capability,r16-capc-shop_grey,r18-capc-weapon_level_view --label
    cheat`): **PLAN LINE 1: 4 routes offline, 0 live. PLAN LINE 2: 252 decided (18 by the batches' own captures, 8
    of those watched and never called), 2 must play live on 4 routes** (strike_power, who_holds_can_equip_subkind:
    never captured on a cheat route). cheat-bt-endgame (round 19's) is not in this plan; it is round 19's to replay.
- **Runs, started at once (17:12:47, FEF_ROBOT_JOBS=12, below normal):**
  - Offline, real play (`r21-off --jobs 6`, source gate on and passed): 212 runs, **185,812 records (181,029 match,
    3,094 gave up, 1,689 incomplete), 0 bad of any kind, offline verdict != captured verdict: 0**, 165 s.
  - Offline, cheat apart (`r21-offc --jobs 2`): 37 runs, **9,584 records (9,224 match), 0 bad, 0 verdict
    differences**, 34 s.
  - Live, cheat apart (`parallel.py runs --route cheat-family --route cheat-forge-katana --route
    cheat-katana-reload --route cheat-skill-proc --mode capture --only strike_power,who_holds_can_equip_subkind
    --store-keep --longest-first --session r21-capc-readers`): 4 of 4 exit 0 Completed, 58 s; **136 records (130
    match, 6 gave up), 0 bad**. who_holds met on all 4; strike_power met on cheat-family and cheat-skill-proc (the
    skill-proc route reaches the skill steps live for the first time). Memory hashes equal r18-capc's on all 4. No
    writer stored; %APPDATA% (zakuro, 3dsrecomp) unchanged.
  - Per family, real play (h6three number 3): Birthright 33 routes 112,915 records; Conquest 7, 26,262; Revelation
    12, 44,623; options 2, 2,012; **0 bad and 0 other differences in each**. Cheat apart: 4 routes, 9,720 records
    (9,584 offline plus 136 live), 0 bad.
- **H5** (`h56.py h5 --sessions <round 18's fourteen plus r21-cap-strike,r21-cap-who_holds> --label play --run-id
  r21-h5 --no-exact --jobs 12 --jobs-over-budget`, beside the replays): 2 min 4 s; **220 of 254 met, 185,812
  records, 0 bad, offline != live 0**; lines 1,413/1,660, branches 988/1,587 (62.3%). strike_power: 18 records,
  lines 30/55, branches 19/64 (one plain fight route only). who_holds_can_equip_subkind: 140 records, lines 15/22,
  branches 14/31. Never met: the same 34. `check_all --only h56-h5` alone: PASS, 1 min 19 s.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r21-off/offline.json --offline-cheat build/speed/replay/r21-offc/offline.json --live
  build/parallel/r21-capc-readers/summary.json --json build/h6three/three-r21.json`): (1) 2,214 / 3,696 (59.9%;
  62.9% also leaving out helper lines), still round 13's sample; strike.c and who_holds.c are not in it yet; (2) host
  test alone 3,700 / 4,009 (92.3%), records or host 92.6%, 36 files with a host test, 0 without (the two new files
  are not yet in h6host; their host tests, 35/35 and 24/24, run in check_all); (3) 54 routes, 185,812 records, 0
  bad; cheat 9,720, 0 bad. Equivalent candidates 237 plus 70 unsorted, unchanged.
- **check_all** (docs/CHECK_ALL.md round 21): new rows strike-diff(-long), who-holds-diff(-long); h56-h5 reads 16
  sessions. Fast 41 pass (41 s); touched rows 6 pass (2 min 26 s); h56-h5 pass. 78 slow/medium rows left for the
  weekly run.
- **Docs brought up to date** (the batches' notes): docs/BATTLE2.md (section 3 and the status line), STANCES.md,
  SKILLS.md, FORMULAS.md section 7, tracks/OPTIONS_V2.md, EQUIP_USE.md. Not changed, on purpose: the comments in
  src/readable/battle2/battle2_calc.c, equip_use.h and weapon_level_view.h still say "not rewritten" / "no row",
  because editing staged sources would make the capture library STALE; change them with the next rebuild.
  forecast_damage (battle2_calc.c) is kept as a test copy (no marker; battle2_diff still runs it).
- **Evidence**: `evidence.py pack` (119.3 MB in all; new: r21-cap-strike 0.0 MB, r21-cap-who_holds 0.3 MB,
  r21-capc-readers 0.2 MB) and `clean --yes --keep-sessions 10 --keep <every r10-r21 session, r19-*/r20-* included,
  runs-20261117-151424, r14-h5 ... r21-h5>`: 0 items freed. D: had about 107 GB free at 17:06.
- **Measured.** Integrate 17:06 to about 17:27 (about 21 min, cap 60): reading, freshness and both plans 6 min;
  check rows and tests written (about 5 min, including the same control-character fix as round 18, caught by
  reading back); the three compare runs and H5 side by side 2 min 46 s; fast pass 41 s; touched rows 2 min 26 s;
  three-number report under 1 s; evidence beside; h56-h5 row 1 min 19 s; docs and report about 6 min. Idle compute
  [med]: no game ran for this round after 17:13:46; during the readable row (2 min 26 s, the long pole) one lane of
  8 was busy; most of the PC stood idle while the docs were written.

## Round 20 integrate (2026-11-17 evening) [high unless tagged]

- **Round 20 in one line.** F-031 (owner 2026-11-17 ~15:20, "yes, start both now, cheats for the finale only"):
  Conquest and Revelation resumed side by side, real play, one fresh helper per chapter, each chapter proven by
  the two-copy proof. Proven and packed this round: **cq-ch13, cq-ch14, cq-ch15, rv-ch18, rv-ch19, rv-ch20**
  (all `verified: true`, clear saves in build/harness/saves). cq-ch13 and rv-ch18 came from the chains paused in
  round 11 (already played to My Castle, replay-checked again this round); the other four were played fresh. No
  pokes, no cheat save; nobody lost. Next: cq-ch16 from cq-ch15-clear, rv-ch21 from rv-ch20-clear.
- **Proof sessions** (the proof steps): r20cq13p (cq-ch13, memory 055aec24a7828f79), r20-proof-cq-ch14
  (57bfc491a8357f50), r20-cq-ch15 (daadb106c759f957), r20-proof-rv-ch18 (8df07735ea742f7d), r20-proof-rv-ch19
  (eced60b0e15f36c5), r20-proof-rv-ch20 (dcddd56af3ee408e): both copies equal and every checkpoint met in each.
  Their captures (r20-cap-<route>) were clean but kept **no records** (run without `--store-keep`), so they cannot
  be replayed offline, and the capture library changed after them (rebuilt 18:22:15 by round 22's `female`
  capture step: 257 overrides, 56 staged files). So integrate played all six **live with every override**.
- **Library:** `harness/build.py --check-fresh` FRESH (built 2026-11-17T18:22:15 by round 22, which runs beside;
  its three new rows female_unit_is_female, female_person_is_female and rod_can_use_target are in the library and
  in targets.csv, uncommitted, UNVERIFIED). Integrate did not rebuild. Each live session ran on its own copy of the
  library (build/parallel/<session>/lib, sha256 ab7763f1..., equal to build/harness/lib at 19:00).
- **Plan** (build/speed/r20int/plan-play.txt, plan-cheat.txt):
  - Real play (round 21's sessions: `--sessions r10-capb,r11-capn,r11-capo,r12-capn,r13-capn,r14-capn,r15-capn
    --extra-sessions r12-cap-class_change,r12-cap-weapon_rank,r13-cap-shop_price,r14-cap-equip_use,
    r14-cap-staff_range,r15-cap-capabilityb,r16-cap-shop_grey,r18-cap-weapon_level_view,r21-cap-strike,
    r21-cap-who_holds --label play`; r15-cap-capability left out; adding the r20-cap-* sessions was refused: "no
    records/<run>/records.fecap"): **PLAN LINE 1, routes: 54 replay offline from their records, 0 must play live
    (route changed). PLAN LINE 2, overrides: 254 decided by the records, 3 must play live on 54 routes** (round
    22's three new rows, never captured). The six new routes are not in the plan (no records): played live.
  - Cheat (`--sessions r10-capc,r11-capc --extra-sessions r12-capc-class_change,r12-cap-weapon_rank,
    r13-capc-shop_price,r14-capc-readers,r15-capc-capability,r16-capc-shop_grey,r18-capc-weapon_level_view,
    r21-capc-readers,r19-capc-endgameb --label cheat`): **PLAN LINE 1: 4 routes offline, 0 live. PLAN LINE 2: 254
    decided, 3 live on 4 routes** (round 22's rows). r19-capc-endgameb's runs on cheat-bt-endgame "no longer count:
    route changed" (its routes.json entry changed after the record was made), so cheat-bt-endgame played live with
    every override.
  - Round 22's three undecided rows were **not** played live on the 54 + 4 older routes: they belong to round 22's
    batch, still in progress; its own capture and integrate decide them. They were met on the six new routes.
- **Runs, started at once (18:38, FEF_ROBOT_JOBS=12, below normal).** The first launch at 18:37 was refused by
  parallel.py ("--store-keep needs --mode capture and --only") and restarted with `--only` = all 257 override names.
  - Offline, real play (`r20-off --jobs 6`, source gate passed): 212 runs, **185,812 records (181,029 match,
    3,094 gave up, 1,689 incomplete), 0 bad of any kind, offline verdict != captured verdict: 0**, 148 s.
  - Offline, cheat apart (`r20-offc --jobs 2`): 44 runs, **9,720 records (9,354 match), 0 bad, 0 verdict
    differences**, 38 s.
  - Live, the six new routes (`parallel.py runs --route cq-ch13 --route rv-ch18 --route cq-ch14 --route rv-ch20
    --route cq-ch15 --route rv-ch19 --mode capture --markers --only <all 257> --store-keep --longest-first
    --timeout 3600 --session r20-cap-new`): 6 of 6 exit 0 Completed, every checkpoint met, **every memory hash
    equal to its proof's**, 1,418 s; **23,484 records (22,692 match, 587 gave up, 203 incomplete): 2 bad**, both
    `mismatch_calls` in strike_power (0x005253A8) on cq-ch13 (23 strike records there: 20 match, 2 call-list, 1
    gave up). The other five routes: 0 bad. No writer stored; %APPDATA% unchanged.
  - Live, cheat (`--route cheat-bt-endgame ... --session r20-capc-endgame`): exit 0, 291,636 frames, memory
    95f8384c0bf16d25 (= round 19), all checkpoints met, 1,599 s; 187 functions, **6,511 records (6,349 match),
    0 bad**.
  - **The cq-ch13 finding** [high for the facts, low for the cause]: the two records are a different list of guest
    calls with the same results and the same memory. Replayed offline from the same records with today's code
    (`offline.py replay --sessions r20-cap-new --routes cq-ch13 --ignore-plan --name r20-new-off`) they **match**
    ("offline verdict != captured: 2"), so the difference shows only in the live game. A guess, not traced: a getter
    cache that is warm on one live side and cold on the other (the strike_power batch already allows early give-ups
    before cold getter caches). Not fixed inside integrate's 60-minute cap. A strike_power fix step must trace it,
    fix it, and capture cq-ch13 again (about 24 min live).
  - strike_power is now met on all six new routes (144 records in H5), its first real-play meets outside bt-ch2.
    Round 22's three rows were met on the new routes too (female_person_is_female 171 records,
    female_unit_is_female 149, rod_can_use_target 89), with 0 bad; round 22's own step judges them.
  - Per family, real play (h6three number 3): Birthright 33 routes 112,915 records, 0 bad; **Conquest 10 routes
    38,150 records, 2 bad (the two above)**; Revelation 15 routes 56,219, 0 bad; options 2 routes 2,012, 0 bad.
    All real play: 60 routes, 209,296 records, 2 bad. Cheat apart: 9,720 offline plus 6,511 live
    (cheat-bt-endgame) = 16,231 records, 0 bad.
- **H5** (`h56.py h5 --sessions <round 21's sixteen>,r20-cap-new --label play --run-id r20-h5 --no-exact --jobs
  12 --jobs-over-budget`): 2 min; **223 of 257 met, 209,296 records (203,723 match, 3,681 gave up), 0 bad,
  offline != live: 2** (the same two strike records); lines 1,456/1,696, branches 1,024/1,617 (63.3%).
  strike_power: 144 records, lines 36/55, branches 28/64. Never met: the same 34. `check_all --only h56-h5` (the
  row's sixteen sessions; r20-cap-new is not added to the row while it holds the two records): PASS, 1 min 27 s.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r20-off/offline.json --offline-cheat build/speed/replay/r20-offc/offline.json --live
  build/parallel/r20-cap-new/summary.json --json build/h6three/three-r20.json`): (1) 2,214 / 3,696 (59.9%; 62.9%
  also leaving out helper lines), round 13's sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host
  92.6%, 36 files; (3) 60 routes, 209,296 records, **2 bad (strike_power, cq-ch13)**; cheat 9,720 offline, 0 bad.
- **check_all** (docs/CHECK_ALL.md round 20): robot-routes requires the six new clear saves and names any
  unverified cq-/rv- key instead of the old F-025 paused list; tests/test_check_all.py 84 OK. Fast 41 pass; touched
  rows (robot-routes, cheat-endgame, selftest) 3 pass; h56-h5 pass.
- **Evidence**: `evidence.py pack` (125.1 MB in all; r20-cap-new 2.2 MB, r20-capc-endgame 0.5 MB; the first try
  stopped on a file that vanished while it read, the second went through) and `clean --yes --keep-sessions 10
  --keep <every r1x-/r2x- session folder, runs-20261117-151424, r14-h5 ... r21-h5>`: freed 0.28 GB, six proof
  folders whose names have no hyphen after the round number, so the keep list missed them (r20cq13p,
  r15bt-ch27cap, r15bt-ch27proof, r15bt-ch27proof2, r14bt26cap, r14bt26proof). Their evidence stays in
  build/evidence, and cq-ch13-clear.zip stays. D: 106 GB free.
- **Measured.** Integrate 18:34 to about 19:20 (about 46 min, cap 60): reading, freshness and both plans 3 min;
  the refused first launch 1 min; the two live sessions 23.6 and 26.7 min, with everything else beside them:
  offline 148 s and 38 s, the check row and its tests (about 5 min), fast pass 2 min 15 s (one lane of 8 free;
  the robots held the rest); then the cq-ch13 look 2 min; H5 2 min; touched rows 1 min 16 s; h56-h5 row 1 min
  27 s; three-number report under 1 s; evidence 1 min; docs and report about 8 min. Idle compute [med]: from
  about 18:52 to 19:05 only three games ran (cq-ch13, rv-ch18, cheat-bt-endgame: 3 of 12 slots); long routes
  cannot be split.

## Round 22 integrate (2026-11-17 evening) [high unless tagged]

- **Round 22 in one line.** Grok's docs/tracks/REWRITE_ORDER4.md rows 3 and 4, side by side, beside round 20
  (owner 2026-11-17 ~17:30, continued as round 22): `female_unit_is_female` (Unit::IsFemale, 0x00533938) and
  `female_person_is_female` (Person::IsFemale, 0x0053ED90), docs/FEMALE.md, 19/19 planted bugs; and
  `rod_can_use_target` (Rod::CanUseTarget, 0x0034AC30), docs/ROD_TARGET.md, now 42/42. All three read only and stay
  UNVERIFIED (owner's call). No game play of rounds 19/20's routes here.
- **Library:** `harness/build.py --check-fresh` **FRESH** (built 2026-11-17T18:22:15 by the female capture step:
  257 overrides, 65 guard users, 56 staged files; all three new readers in it). Integrate did not rebuild, so no
  reader needed a second capture. Integrate changed only a test file (rod_target_diff.py) and docs: nothing staged.
- **rod_target review fix (inside integrate)** [high]: the second review's major point (ok: false) was a planted
  bug the host test missed on the default seed: resistance halving without the sign (`(uint8_t)amount >> 1`). The
  resistance set-up used only amounts 2 and 3. Integrate added a negative-amount resistance case (0x80..0xFF
  against a debuff 0, in half of the resistance cases that did not take the 2-or-3 case) and the plant as the
  42nd. 14 seeds (20261117, 7, 11, 13, 99, 5, 12, 14, 15, 16, 1, 2, 3, 4242): **all 0 mismatches, 42/42**. A first
  try that mixed the negative amounts into the 2-or-3 choice missed the halve-twice plant on seed 1 and was
  replaced. rod_target.c/.h unchanged. docs/ROD_TARGET.md: the CanUseDisvalueRange wording fixed (3dsrecomp did
  copy the body into that caller, but no call reaches the copy), the new set-up, plant and results.
- **Batch captures:** `r22-cap-female` (bt-ch4, 45 records, 43 match, 2 cold give-ups, 0 bad, memory
  18ca52e007f5179e = earlier bt-ch4 runs). rod_target had no capture step of its own: integrate played it live.
- **Plan** (build/speed/r22int/plan-play.txt, plan-cheat.txt):
  - Real play (round 21's sessions plus r22-cap-female; r15-cap-capability left out): **PLAN LINE 1, routes: 54
    replay offline from their records, 0 must play live (route changed). PLAN LINE 2, overrides: 256 decided by the
    records (8 by the batches' own captures on 51 routes, 1 of those watched and never called), 1 must play live on
    54 routes** (rod_can_use_target, never captured). Capped by F-027 at 8 routes that met a staff in round 14's
    staff capture, shortest first and all three families: bt-ch4, bt-ch5, cq-ch6, bt-ch7, bt-ch8, cq-ch7, rv-ch7,
    bt-ch17.
  - Cheat (round 21's cheat sessions plus r21-capc-readers): **PLAN LINE 1: 4 routes offline, 0 live. PLAN LINE 2:
    254 decided, 3 must play live on 4 routes** (the three new readers).
- **Runs, started at once (19:20:45, FEF_ROBOT_JOBS=12, below normal; all exited 0 by 19:34:39):**
  - Offline, real play (`r22-off --jobs 6`, source gate passed): 213 runs, **185,857 records (181,072 match,
    3,096 gave up, 1,689 incomplete), 0 bad of any kind, offline verdict != captured verdict: 0**, 130 s.
  - Offline, cheat apart (`r22-offc --jobs 2`): 44 runs, **9,720 records (9,354 match), 0 bad, 0 verdict
    differences**, 35 s.
  - Live, real play (`parallel.py runs --route bt-ch4 ... --route bt-ch17 --mode capture --only rod_can_use_target
    --store-keep --longest-first --session r22-cap-rod_target`): 8 of 8 exit 0 Completed, 833 s; **119 records (112
    match, 7 gave up: each route's cold first call), 0 bad**. Met on 7 of 8 (not bt-ch4: no staff used there).
    Every final memory hash equal to the route's earlier runs. No writer stored; %APPDATA% unchanged.
  - Live, cheat (`--route cheat-family --route cheat-forge-katana --route cheat-katana-reload --route
    cheat-skill-proc --mode capture --only female_person_is_female,female_unit_is_female,rod_can_use_target
    --store-keep --longest-first --session r22-capc-readers`): 4 of 4 exit 0, 161 s; **168 records (160 match, 8
    gave up), 0 bad**. female_person_is_female met on all 4, female_unit_is_female on 3, rod_can_use_target only
    as one cold first call on cheat-family and cheat-skill-proc (2 records, both gave up). Memory hashes equal to
    every earlier cheat run.
  - Per family, real play (h6three number 3): Birthright 33 routes 113,028 records; Conquest 7, 26,297; Revelation
    12, 44,639; options 2, 2,012; **0 bad and 0 other differences in each**; all 54 routes 185,976 records. Cheat
    apart: 4 routes, 9,888 records, 0 bad.
- **H5** (`h56.py h5 --sessions <round 21's sixteen>,r22-cap-female,r22-cap-rod_target --label play --run-id r22-h5
  --no-exact --jobs 12 --jobs-over-budget`): 103 s; **223 of 257 met, 185,976 records (181,184 match, 3,103 gave
  up), 0 bad, offline != live 0**; lines 1,443/1,696, branches 1,007/1,617 (62.3%). female_unit_is_female 21
  records, lines 8/8, branches 2/2; female_person_is_female 24, lines 5/5, branches 2/2; rod_can_use_target 119,
  lines 17/23, branches 15/26. Never met: the same 34.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r22-off/offline.json --offline-cheat build/speed/replay/r22-offc/offline.json --live
  build/parallel/r22-cap-rod_target/summary.json --live build/parallel/r22-capc-readers/summary.json --json
  build/h6three/three-r22.json`): (1) 2,214 / 3,696 (59.9%; 62.9% also leaving out helper lines), round 13's
  sample; female.c and rod_target.c are not in it yet; (2) host test alone 3,700 / 4,009 (92.3%), records or host
  92.6%, 36 files (the two new files are not in h6host yet; their host tests run in check_all); (3) 54 routes,
  185,976 records, 0 bad; cheat 9,888, 0 bad. Equivalent candidates 237 plus 70 unsorted, unchanged.
- **check_all** (docs/CHECK_ALL.md round 22): new rows female-diff(-long), rod-target-diff(-long); readable-verify
  KNOWN `rod-target-not-run` (exactly two named NOT-RUN, no MISMATCH); h56-h5 also reads r22-cap-female and
  r22-cap-rod_target (round 20's integrate added r20-cap-newb beside: 19 sessions); tests 84 OK. `--only h56-h5`
  alone: PASS, 1 min 23 s, 223 of 257 met, 209,460 records (with r20-cap-newb), 0 bad.
  Fast 41 pass (46 s); touched rows (the four new, readable, gen-stubs-check, equip-use-diff, growth-diff) 8 pass
  (10 min 47 s; growth-diff the long pole at 10 min 39 s beside round 20's robots).
- **Not changed, on purpose:** src/readable/equip_use/equip_use.h still says Unit::IsFemale is "(not rewritten)",
  and the two older comments from round 21 stay: editing staged sources would make the library STALE. Fix at the
  next rebuild. docs/GROWTH.md lists Person::IsFemale under guest calls (true: the call now reaches the override).
- **Open:** round 20's integrate found 2 strike_power call-list records on cq-ch13 (live only); that fix is round
  20's, not round 22's. While round 22 ran, another step edited src/readable/battle/formula_unit.c (bool arguments
  passed as the plain register) and rebuilt the library at 19:23:10 (sha256 6304666849ad...). Round 22's live runs
  had started at 19:20:45 on their own copies of the 18:22:15 library (sha256 ab7763f1b240..., in every run.json),
  and the three new readers' sources did not change, so no recapture is needed for them. Job::IsFemale (0x00524AF4) is a possible later reader.
- **Evidence**: `evidence.py pack` (127.4 MB in all; new: r22-cap-female 0.0 MB, r22-cap-rod_target 0.4 MB,
  r22-capc-readers 0.2 MB). `clean` was **refused** ("boot.exe is running": round 20's robots were playing) and
  was not forced. Retried at about 20:00 once the robots had stopped (`clean --yes --keep-sessions 10 --keep <every
  r10-r22 session folder in build/parallel, r19-*/r20-* included, runs-20261117-151424, r14-h5 ... r22-h5>`):
  freed 0.00 GB (0 items). D: 105 GB free.

### Round 20 fix step (2026-11-17, 19:18 to about 20:20) [high unless tagged]

- **The two strike_power records on cq-ch13, traced.** The capture log says: "probe call 0: 00534188(r3=0000001E)
  vs (r3=00000000)". So the game's strike code and the readable one both call Unit::GetAttack (0x00534188, the
  Dragon Fang step) with the same r0-r2 and get the same answer; only r3 differs, and r3 is **not** an argument of
  GetAttack(this, item, bool): the game leaves 0x1E there, the readable call leaves 0. The capture compares only a
  callee's argument registers, which FE_ENTRY finds from plain `FE_ARG(n)` expressions. unit_attack's entry passed
  its bool as `FE_ARG(2) != 0`, which is not plain, so capture compared all four registers. Offline replay does not
  see that callee note (unobservable_notes 32), so there the records matched.
- **Fix** (src/readable/battle/formula_unit.c, entry lines only): the four entries with a bool (unit_hit,
  unit_hit_of_slot, unit_attack, unit_attack_of_slot) now pass `FE_ARG(2)` plainly. Their `rank_bonus` is only
  tested for non-zero, so the readable result is the same; capture now compares r0-r2 only. Host test
  formula_diff.py: 7,100 cases, 0 mismatches, 31/31 planted bugs caught. Library rebuilt with `build.py --swap`
  (553 s, built 19:23:10, FRESH). [med] Round 22's runs that started before 19:32 used the library before this
  swap; their readers are not touched by the change.
- **Recapture** (`parallel.py runs --route cq-ch13 --route rv-ch18 --route cq-ch14 --route rv-ch20 --route cq-ch15
  --route rv-ch19 --mode capture --markers --only <all 257> --store-keep --timeout 3600 --session r20-cap-newb`,
  FEF_ROBOT_JOBS=12, below normal): 6 of 6 exit 0 Completed, every checkpoint met, every memory hash equal to its
  proof's, 1,066 s; **23,484 records (22,694 match, 587 gave up, 203 incomplete), 0 bad of any kind**. strike_power
  on cq-ch13: 23 records, 22 match, 1 gave up. No writer stored; %APPDATA% unchanged. r20-cap-newb is the clean
  retry; r20-cap-new is no longer used.
- **Offline with the new library:** real play r20-offb 185,812 records 0 bad; with round 22's own captures added
  (r20-offd) 185,976 records, 0 bad, 0 verdict differences; cheat r20-offcb (r20-capc-endgame included) 16,231
  records, 0 bad.
- **Plan lines** (build/speed/r20fix/plan-play.txt, plan-cheat.txt; r20-cap-newb and round 22's captures as extra
  sessions): real play PLAN LINE 1, 54 offline / 0 live; PLAN LINE 2, 257 decided by the records, 0 live. Cheat
  PLAN LINE 1, 4 offline / 0 live (plus cheat-bt-endgame from r20-capc-endgame); PLAN LINE 2, 257 decided, 0 live.
- **H5** (`r20-h5b`, 19 sessions = the h56-h5 row's 18 plus r20-cap-newb): **223 of 257 met, 209,460 records
  (203,878 match, 3,690 gave up), 0 bad, offline != live: 0**; branches 1,030/1,617 (63.7%).
- **Three numbers** (build/h6three/three-r20b.json): (1) 2,214 / 3,696 (59.9%), round 13's sample; (2) host 3,700 /
  4,009 (92.3%), records or host 92.6%; (3) **60 routes, 209,460 records, 0 bad** (Birthright 33 / 113,028,
  Conquest 10 / 38,185, Revelation 15 / 56,235, options 2 / 2,012; all 0 bad). Cheat apart: 5 routes, 16,231, 0 bad.
- **check_all:** h56-h5 row now has r20-cap-newb (19 sessions); see docs/CHECK_ALL.md "Round 20 fix step".

## Round 23 integrate (2026-11-17 night) [high unless tagged]

- **Round 23 in one line.** Grok's docs/tracks/REWRITE_ORDER4.md rows 5 and 6 (the last two), side by side, beside
  round 20 (owner 2026-11-17 20:10): `unit_item_enhance_have` (Unit::IsItemEnhanceHave, 0x0052FB98),
  docs/ITEM_ENHANCE.md, 29/29 planted bugs; and the four volume readers `volume_bgm_value`, `volume_se_value`,
  `volume_sys_se_value`, `volume_voice_value` (Volume*::GetValue at 0x003BCA4C, 0x003BC7C4, 0x003BB078, 0x003BB168),
  docs/VOLUME.md, 19/19. All five read only and stay UNVERIFIED (owner's call). No game play of rounds 19/20's
  routes here.
- **Library:** `harness/build.py --check-fresh` **FRESH** (built 2026-11-17T20:36:49 by the volume capture step:
  262 overrides, 66 guard users, 58 staged files; both batches' readers in it). Integrate did not rebuild, so no
  reader needed a second capture. Integrate changed only check_all, its tests and docs: nothing staged.
- **Batch captures:** `r23-cap-item_enhance` (bt-ch4, 30 records: 5 match, 23 gave up, 2 incomplete, 0 bad; memory
  18ca52e007f5179e = earlier bt-ch4 runs; verdict SHALLOW, one path); `r23-cap-volume` (opt-ch8-reload, 80
  records, 80 match, 0 bad; memory 3c3489bb53f19c54 = earlier runs; each reader one path, the 0xFF "maximum" one).
- **Plan** (build/speed/r23int/plan-play.txt, plan-cheat.txt):
  - Real play (round 22's sessions plus r22-cap-rod_target, r23-cap-item_enhance, r23-cap-volume; r15-cap-capability
    left out): **PLAN LINE 1, routes: 54 replay offline from their records, 0 must play live (route changed). PLAN
    LINE 2, overrides: 262 decided by the records (14 of them by the batches' own captures on 51 routes, 1 of those
    watched and never called), 0 must play live.**
  - Cheat (round 22's cheat sessions plus r22-capc-readers): **PLAN LINE 1: 4 routes offline, 0 live. PLAN LINE 2:
    257 decided, 5 must play live on 4 routes** (the five new readers).
- **Runs, started at once (20:49:22, FEF_ROBOT_JOBS=12, below normal; all exited 0 by 20:51:07):**
  - Offline, real play (`offline.py replay ... --name r23-off --jobs 6`, source gate passed): 222 runs, **186,086
    records (181,269 match, 3,126 gave up, 1,691 incomplete), 0 bad of any kind, offline verdict != captured
    verdict: 0**, 104 s.
  - Offline, cheat apart (`r23-offc --jobs 2`): 51 runs, **9,888 records (9,514 match), 0 bad, 0 verdict
    differences**, 32 s.
  - Live, cheat (`parallel.py runs --route cheat-family --route cheat-forge-katana --route cheat-katana-reload
    --route cheat-skill-proc --mode capture --only unit_item_enhance_have,volume_bgm_value,volume_se_value,
    volume_sys_se_value,volume_voice_value --store-keep --longest-first --session r23-capc-readers`): 4 of 4 exit 0,
    52 s; **175 records (56 match, 117 gave up, 2 incomplete), 0 bad**. Only unit_item_enhance_have was met (all 4
    routes; on cheat-forge-katana and cheat-katana-reload every record gave up on a cold cache). The four volume
    readers were watched and never called: no cheat route opens the options screen. Memory hashes equal to every
    earlier cheat run (bb5ef48f8587ec3e, 3188fff1deb224f4, 47d34f0df6f9ea1e, 371db3a3ca695a1b). No writer stored;
    %APPDATA% unchanged.
  - Per family, real play (h6three number 3): Birthright 33 routes 113,058 records; Conquest 7, 26,297; Revelation
    12, 44,639; options 2, 2,092; **0 bad and 0 other differences in each**; all 54 routes 186,086 records. Cheat
    apart: 4 routes, 10,063 records, 0 bad.
- **H5** (`h56.py h5 --sessions <the h56-h5 row's 19>,r23-cap-item_enhance,r23-cap-volume --label play --run-id r23-h5
  --no-exact --jobs 12 --jobs-over-budget`): 101 s; **228 of 262 met, 209,570 records (203,963 match, 3,713 gave
  up), 0 bad, offline != live 0**; lines 1,476/1,721, branches 1,034/1,635 (63.2%). unit_item_enhance_have 30
  records, lines 8/17, branches 4/18; each volume reader 20 records, lines 2/2 (no branch). Never met: the same 34.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r23-off/offline.json --offline-cheat build/speed/replay/r23-offc/offline.json --live
  build/parallel/r23-capc-readers/summary.json --json build/h6three/three-r23.json`): (1) 2,214 / 3,696 (59.9%;
  62.9% also leaving out helper lines), round 13's sample; item_enhance.c and volume.c are not in it yet; (2) host
  test alone 3,700 / 4,009 (92.3%), records or host 92.6%, 36 files (the two new files are not in h6host yet; their
  host tests run in check_all); (3) 54 routes, 186,086 records, 0 bad; cheat 10,063, 0 bad. Equivalent candidates
  237 plus 70 unsorted, unchanged.
- **check_all** (docs/CHECK_ALL.md round 23): new rows item-enhance-diff(-long) (early give-ups allowed on purpose),
  volume-diff(-long) (no give-up allowed); no new KNOWN entry (GAVE-UP / UNSAMPLED are not verify problems); h56-h5
  reads 21 sessions; tests 84 OK. Fast 42 pass (48 s); touched rows 7 pass (2 min 36 s); `--only h56-h5` alone
  PASS (1 min 45 s).
- **Docs fixed by integrate:** docs/MENUS.md (the +0x10..+0x13 row now names the four volume readers),
  docs/harness/OPT_ROUTES.md (lines 18-21), docs/ITEM_ENHANCE.md (plain summary: "kind 8 exactly", not "not a
  weapon kind"; the review's wording point).
- **Not changed, on purpose:** the three older source comments that say "not rewritten" (equip_use.h and two from
  round 21) stay: editing staged sources would make the library STALE. Fix at the next rebuild.
- **Evidence**: `evidence.py pack` (128.3 MB in all; new: r23-cap-item_enhance 0.0 MB, r23-cap-volume 0.0 MB,
  r23-capc-readers 0.2 MB); `clean --yes --keep-sessions 10 --keep <every r10-r23 session folder in
  build/parallel, r19-*/r20-* included, runs-20261117-151424, r14-h5 ... r23-h5>`: freed 0.00 GB (0 items). D:
  104 GB free.

## Round 25 integrate (2026-11-17 night) [high unless tagged]

- **Round 25 in one line.** Grok's new docs/tracks/REWRITE_ORDER5.md rows 1 and 2, side by side, beside round 24
  (owner 2026-11-17 21:15): `job_female_is_female` (Job::IsFemale, 0x00524AF4), docs/JOB_FEMALE.md, 13/13 planted
  bugs, now an override (reads only, UNVERIFIED, owner's call); and `job_record_get` (Job::Get, 0x00341AA4),
  docs/JOB_RECORD.md, 18/18 planted bugs, kept as a registered **helper, not an override**: tier 2 says NOT-RUN
  because castle::CastleButler::GetJob (0x00341A50) runs on into it (the UnitPool::Get shape), so the batch's stop
  rule applied. The game still runs its own Job::Get; AIValue::GetJob stays blocked (REWRITE_ORDER5). No game play
  of round 24's routes here.
- **Library:** `harness/build.py --check-fresh` **FRESH** (built 2026-11-17T21:36:37 by the job_female capture
  step: 263 overrides, 67 guard users, 60 staged files; job_female.c and the helper job_record.c in it). Integrate
  did not rebuild, so no reader needed a second capture. Integrate changed only check_all, its tests and docs.
- **Batch capture:** `r25-cap-job_female` (bt-ch4, 20 records: 19 match, 1 gave up on the first, cold call, 0
  incomplete, 0 bad; memory 18ca52e007f5179e = earlier bt-ch4 runs). The review's worry (the game skips the guard
  release, so the cache might never look filled) did not happen live: 19 calls answered from the readable code.
  job_record has no capture (a helper has no override entry).
- **Plan** (build/speed/r25int/plan-play.txt, plan-cheat.txt):
  - Real play (round 23's sessions plus r20-cap-newb and r25-cap-job_female; r15-cap-capability left out): **PLAN
    LINE 1, routes: 54 replay offline from their records, 0 must play live (route changed). PLAN LINE 2,
    overrides: 263 decided by the records (15 of them by the batches' own captures on 57 routes, 1 of those
    watched and never called), 0 must play live.**
  - Cheat (round 23's cheat sessions plus r23-capc-readers): **PLAN LINE 1: 4 routes offline, 0 live. PLAN LINE 2:
    262 decided, 1 must play live on 4 routes** (job_female_is_female).
- **Runs, started at once (21:50:12, FEF_ROBOT_JOBS=12, below normal; all exited 0 by 21:52:40):**
  - Offline, real play (`offline.py replay ... --name r25-off --jobs 6`): 229 runs, **209,590 records (203,982
    match, 3,714 gave up, 1,894 incomplete), 0 bad of any kind, offline verdict != captured verdict: 0**, 147 s.
    (60 routes: round 20's six new routes come in through r20-cap-newb's records, offline only.)
  - Offline, cheat apart (`r25-offc --jobs 2`): 58 runs, **10,063 records (9,570 match), 0 bad, 0 verdict
    differences**, 62 s.
  - Live, cheat (`parallel.py runs --route cheat-family --route cheat-forge-katana --route cheat-katana-reload
    --route cheat-skill-proc --mode capture --only job_female_is_female --store-keep --longest-first --session
    r25-capc-readers`): 4 of 4 exit 0, 84 s; **131 records (127 match, 4 gave up, one cold first call per route),
    0 bad**. Memory hashes equal to every earlier cheat run (bb5ef48f8587ec3e, 3188fff1deb224f4, 47d34f0df6f9ea1e,
    371db3a3ca695a1b). No writer stored; %APPDATA% unchanged.
  - Per family, real play (h6three number 3): Birthright 33 routes 113,078 records; Conquest 10, 38,185;
    Revelation 15, 56,235; options 2, 2,092; **0 bad and 0 other differences in each**; all 60 routes 209,590
    records. Cheat apart: 4 routes, 10,194 records, 0 bad.
- **H5** (`h56.py h5 --sessions <the h56-h5 row's 22> --label play --run-id r25-h5 --no-exact --jobs 12
  --jobs-over-budget`): 114 s; **229 of 263 met, 209,590 records (203,982 match, 3,714 gave up), 0 bad, offline !=
  live 0**; lines 1,481/1,726, branches 1,036/1,637 (63.3%). job_female_is_female 20 records, lines 5/5, branches
  2/2. Never met: the same 34.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r25-off/offline.json --offline-cheat build/speed/replay/r25-offc/offline.json --live
  build/parallel/r25-capc-readers/summary.json --json build/h6three/three-r25.json`): (1) 2,214 / 3,696 (59.9%;
  62.9% also leaving out helper lines), round 13's sample; job_female.c and job_record.c are not in it yet; (2)
  host test alone 3,700 / 4,009 (92.3%), records or host 92.6%, 36 files (the new files are not in h6host yet;
  their host tests run in check_all); (3) 60 routes, 209,590 records, 0 bad; cheat 10,194, 0 bad. Equivalent
  candidates 237 plus 70 unsorted, unchanged.
- **check_all** (docs/CHECK_ALL.md round 25): new rows job-female-diff(-long) (cold give-ups allowed on purpose),
  job-record-diff(-long) (no give-up allowed); no new KNOWN entry; h56-h5 reads 22 sessions; tests 84 OK. Fast 44
  pass (1 min 9 s); touched rows 7 pass (2 min 48 s); `--only h56-h5` alone PASS (1 min 51 s).
- **Docs fixed by integrate:** docs/JOB_RECORD.md now says the holder's shadow log counts "1 mismatched" only for
  "4 faults against 8" (the benign A-against-2A shadow shape), as the review asked.
- **Evidence**: `evidence.py pack` (131.1 MB in all; new: r25-cap-job_female 0.0 MB, r25-capc-readers 0.2 MB).
  `clean --keep-sessions 10 --keep <every r10-r25 session folder, r19-*/r20-*/r24-* included,
  runs-20261117-151424, r14-h5 ... r25-h5>` **refused: boot.exe is running** (round 24's play). Not forced, so
  round 24's files stay safe; the clean waits for the next integrate. D: 103 GB free.

## Round 26 integrate (2026-11-17 night) [high unless tagged]

- **Round 26 in one line.** Grok's docs/tracks/REWRITE_ORDER5.md rows 5 and 3, side by side, beside round 24
  (owner 2026-11-17 22:15): `key_door_unit_can_open` (Unit::CanKeyDoor, 0x00529E20), docs/KEY_DOOR.md, 18/18
  planted bugs, an override that only reads (one s16 skill-number cache; gives up while it is cold); and
  `skill_record_by_name` (EquipSkill::Get(const char*), 0x001758C4), docs/SKILL_RECORD.md, 20/20 planted bugs, an
  override that only reads (the whole ID hash lookup in C, no cache, no guest call, never gives up). Both
  UNVERIFIED (owner's call). IdentHash::GetSurely is not an override (UniqueArchiveObject::GetSurely runs into
  it); its body is a static step in skill_record.c. No game play of round 24's routes here.
- **Library:** `harness/build.py --check-fresh` **FRESH** (built 2026-11-17T22:37:58 by the key_door capture step:
  265 overrides, 68 guard users, 62 staged files; both new readers in it; skill_record.c last changed 22:34:57,
  before that build). Integrate did not rebuild, so no reader needed a second capture.
- **Batch captures:** `r26-cap-key_door` (bt-ch4, 20 records: 19 match, 1 gave up, 0 bad) and
  `r26-cap-skill_record` (bt-ch4, 22 records, 22 match, 0 bad; 1,913 calls). Memory 18ca52e007f5179e = every
  earlier bt-ch4 run. In H5 key_door shows 2 results, lines 5/5 and branches 4/4, so the item fallback path was
  met live too.
- **Plan** (build/speed/r26int/plan-play.txt, plan-cheat.txt):
  - Real play (round 25's sessions plus r26-cap-key_door and r26-cap-skill_record; r15-cap-capability left out):
    **PLAN LINE 1, routes: 54 replay offline from their records, 0 must play live (route changed). PLAN LINE 2,
    overrides: 265 decided by the records (17 of them by the batches' own captures on 57 routes, 1 of those watched
    and never called), 0 must play live.**
  - Cheat (round 25's cheat sessions plus r25-capc-readers): **PLAN LINE 1: 4 routes offline, 0 live. PLAN LINE 2:
    263 decided, 2 must play live on 4 routes** (key_door_unit_can_open, skill_record_by_name: never captured).
- **Runs, started at once (23:00:22, FEF_ROBOT_JOBS=12, below normal; all exited 0 by 23:03:08):**
  - Offline, real play (`offline.py replay ... --name r26-off --jobs 6`): 231 runs, **209,632 records (204,023
    match, 3,715 gave up, 1,894 incomplete), 0 bad of any kind, offline verdict != captured verdict: 0**, 165 s.
  - Offline, cheat apart (`r26-offc --jobs 2`): 65 runs, **10,194 records (9,697 match), 0 bad, 0 verdict
    differences**, 53 s.
  - Live, cheat (`parallel.py runs --route cheat-family --route cheat-forge-katana --route cheat-katana-reload
    --route cheat-skill-proc --mode capture --only key_door_unit_can_open,skill_record_by_name --store-keep
    --longest-first --session r26-capc-readers`): 4 of 4 exit 0, 53 s; **127 records (124 match, 2 gave up, 1
    incomplete), 0 bad**. Per function (summary.tsv, stage0 and main runs): key_door 4 records on cheat-family and
    cheat-skill-proc (2 match, 2 cold give-ups); skill_record 122 records on all 4 routes (121 match, 1
    incomplete). The per-function rows add to 126 and the run table to 127; both have 0 bad. Memory hashes equal
    to every earlier cheat run (bb5ef48f8587ec3e, 3188fff1deb224f4, 47d34f0df6f9ea1e, 371db3a3ca695a1b). No writer
    stored; %APPDATA% unchanged.
  - Per family, real play (h6three number 3): Birthright 33 routes 113,120 records; Conquest 10, 38,185;
    Revelation 15, 56,235; options 2, 2,092; **0 bad and 0 other differences in each**; all 60 routes 209,632
    records. Cheat apart: 4 routes, 10,321 records, 0 bad.
- **H5** (`h56.py h5 --sessions <the h56-h5 row's 24> --label play --run-id r26-h5 --no-exact --jobs 12
  --jobs-over-budget`): 112 s; **231 of 265 met, 209,632 records (204,023 match, 3,715 gave up), 0 bad, offline !=
  live 0**; lines 1,488/1,733, branches 1,040/1,641 (63.4%). key_door 20 records, lines 5/5, branches 4/4;
  skill_record 22 records, 21 results, lines 2/2. Never met: the same 34.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r26-off/offline.json --offline-cheat build/speed/replay/r26-offc/offline.json --live
  build/parallel/r26-capc-readers/summary.json --json build/h6three/three-r26.json`): (1) 2,214 / 3,696 (59.9%;
  62.9% also leaving out helper lines), round 13's sample; key_door.c and skill_record.c are not in it yet; (2)
  host test alone 3,700 / 4,009 (92.3%), records or host 92.6%, 36 files (the new files are not in h6host yet;
  their host tests run in check_all); (3) 60 routes, 209,632 records, 0 bad; cheat 10,321, 0 bad. Equivalent
  candidates 237 plus 70 unsorted, unchanged.
- **check_all** (docs/CHECK_ALL.md round 26): new rows key-door-diff(-long) (cold give-ups allowed on purpose),
  skill-record-diff(-long) (no give-up allowed); no new KNOWN entry; h56-h5 reads 24 sessions; tests 84 OK. Fast 46
  pass (1 min 42 s); touched rows 7 pass (3 min 2 s); `--only h56-h5` alone PASS (2 min 8 s).
- **Docs fixed by integrate:** docs/SKILL_RECORD.md (19/19 -> 20/20 in the status line; seed 20261117 "entry
  found" recounted as 205), docs/SKILLS.md "Guest calls left" and docs/CLASS_CHANGE.md (EquipSkill::Get(const
  char*) is now an override the guest call reaches), docs/tracks/REWRITE_ORDER5.md (a progress line: rows 1, 2, 3,
  5 done; row 4 left). The comments in src/readable/skill/skills.h and src/readable/class_change/class_change.h
  still say "not rewritten": not edited, because a source edit makes the library stale; fix at the next rebuild.
- **Evidence**: `evidence.py pack` (133.2 MB in all; new: r26-cap-key_door 0.0 MB, r26-cap-skill_record 0.0 MB,
  r26-capc-readers 0.2 MB). `clean --yes --keep-sessions 10 --keep <every r10-r26 session folder in
  build/parallel, r19-*/r20-*/r24-* included, runs-20261117-151424, r14-h5 ... r26-h5>` (no boot.exe running at
  23:16): freed 0.00 GB (0 items). D: 102 GB free.

## Round 27 integrate (2026-11-18 night) [high unless tagged]

- **Round 27 in one line.** Grok's docs/tracks/REWRITE_ORDER5.md row 4, the last named reader, one batch, beside
  round 24 (owner 2026-11-17 23:25): `person_record_by_name` (Person::Get(const char*), 0x0044A6DC), an override
  that only reads (G_IdentHash, then the IdentHash::GetSurely lookup copied as a static step; no cache, no guest
  call, never gives up), and `person_record_get` (Person::Get(unsigned short), 0x0044A6F8), a tested helper, not
  an override (AIValue::GetPerson 0x0044A6F0 runs into it: the Job::Get / UnitPool::Get stop rule).
  docs/PERSON_RECORD.md, 38/38 planted bugs. UNVERIFIED (owner's call). All five REWRITE_ORDER5 rows are done. No
  game play of round 24's routes here.
- **Library:** `harness/build.py --check-fresh` **FRESH** (built 2026-11-18T00:03:44 by the person_record capture
  step after round 24's proof had exited: 266 overrides, 68 guard users, 63 staged files). Integrate did not
  rebuild, so no reader needed a second capture. Still FRESH at 00:25.
- **Batch capture:** `r27-cap-person_record` (bt-ch6-castle, 20 records, 20 match, 0 bad; memory
  e0758406b8bf7452 = all 6 earlier bt-ch6-castle runs). In H5: 20 records, 14 results, lines 2/2.
- **Plan** (build/speed/r27int/plan-play.txt, plan-cheat.txt):
  - Real play (round 26's sessions plus r27-cap-person_record; r15-cap-capability left out): **PLAN LINE 1,
    routes: 54 replay offline from their records, 0 must play live (route changed). PLAN LINE 2, overrides: 266
    decided by the records (18 of them by the batches' own captures on 57 routes, 1 of those watched and never
    called), 0 must play live.**
  - Cheat (round 26's cheat sessions plus r26-capc-readers): **PLAN LINE 1: 4 routes offline, 0 live. PLAN LINE
    2: 265 decided, 1 must play live on 4 routes** (person_record_by_name: never captured on a cheat route).
- **Runs, started at once (00:14:14, FEF_ROBOT_JOBS=12, below normal; all exited 0 by 00:16:42):**
  - Offline, real play (`offline.py replay ... --name r27-off --jobs 6`): 232 runs, **209,652 records (204,043
    match, 3,715 gave up, 1,894 incomplete), 0 bad of any kind, offline verdict != captured verdict: 0**, 147 s.
  - Offline, cheat apart (`r27-offc --jobs 2`): 72 runs, **10,321 records (9,821 match), 0 bad, 0 verdict
    differences**, 58 s.
  - Live, cheat (`parallel.py runs --route cheat-family --route cheat-forge-katana --route cheat-katana-reload
    --route cheat-skill-proc --mode capture --only person_record_by_name --store-keep --longest-first --session
    r27-capc-readers`): 4 of 4 exit 0, 44 s; **131 records (129 match, 0 gave up, 2 incomplete), 0 bad**, all of
    them person_record_by_name (met on all 4 routes: 37, 39, 18, 37). Memory hashes equal to every earlier cheat
    run (bb5ef48f8587ec3e, 3188fff1deb224f4, 47d34f0df6f9ea1e, 371db3a3ca695a1b). No writer stored; %APPDATA%
    unchanged.
  - Per family, real play (h6three number 3): Birthright 33 routes 113,140 records; Conquest 10, 38,185;
    Revelation 15, 56,235; options 2, 2,092; **0 bad and 0 other differences in each**; all 60 routes 209,652
    records. Cheat apart: 4 routes, 10,452 records, 0 bad.
- **H5** (`h56.py h5 --sessions <the h56-h5 row's 25> --label play --run-id r27-h5 --no-exact --jobs 12
  --jobs-over-budget`): 101 s; **232 of 266 met, 209,652 records (204,043 match, 3,715 gave up), 0 bad, offline !=
  live 0**; lines 1,490/1,735, branches 1,040/1,641 (63.4%). Never met: the same 34.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r27-off/offline.json --offline-cheat build/speed/replay/r27-offc/offline.json --live
  build/parallel/r27-capc-readers/summary.json --json build/h6three/three-r27.json`): (1) 2,214 / 3,696 (59.9%;
  62.9% also leaving out helper lines), round 13's sample; person_record.c is not in it yet; (2) host test alone
  3,700 / 4,009 (92.3%), records or host 92.6%, 36 files (person_record is not in h6host yet; its host test runs in
  check_all); (3) 60 routes, 209,652 records, 0 bad; cheat 10,452, 0 bad. Equivalent candidates 237 plus 70
  unsorted, unchanged.
- **check_all** (docs/CHECK_ALL.md round 27): new rows person-record-diff (fast) and person-record-diff-long (slow;
  3000 cases, two functions); no give-up allowed; "drawn again" lines allowed; no new KNOWN entry; h56-h5 reads 25
  sessions; tests 84 OK. Fast 47 pass (1 min 55 s); touched rows 5 pass (2 min 17 s); `--only h56-h5` alone PASS
  (1 min 42 s).
- **Docs fixed by integrate:** docs/GROWTH.md "Guest calls left" (Person::Get(unsigned short) is a tested helper,
  not an override, so that guest call still runs the game's code), docs/CASTLE_JOIN.md (Person::Get(const char*)
  is now an override the guest call reaches), docs/tracks/REWRITE_ORDER5.md (progress line: all five rows done).
  Source comments not edited (a source edit makes the library stale).
- **Evidence**: `evidence.py pack` (135.2 MB in all; new: r27-cap-person_record 0.0 MB, r27-capc-readers 0.2 MB).
  `clean --yes --keep-sessions 10 --keep <every r10-r27 session folder in build/parallel, r19-*/r20-*/r24-*
  included, runs-20261117-151424, r14-h5 ... r27-h5>` (no boot.exe running at 00:26): freed 0.00 GB (0 items). D:
  101 GB free.

## Round 28 integrate (2026-11-18 night): OK A, no opt-* run [high unless tagged]

- **No new `opt-*` route.** OK A (F-032) stopped at the host test: W1/W2 are not written (docs/OPTIONS_WIRING.md
  section 11). routes.json still has only the two real-play options routes (opt-ch8-set, opt-ch8-reload; they
  change options on the game's own screen, no writer). None has an `"options"` key.
- **Rules for OK A's `opt-*` routes when they come** (unchanged from F-032): named `opt-*`, `"options": {...}` in
  routes.json, scored apart like the cheat track, never in check_all's `robot-routes` real-play list, any save
  they make carries a mark and never starts a real-play route, options files only below build/, runs only on the
  armed library in its own tree (never build/harness/lib).
- **Checked tonight:** no real-play route starts from an `opt-*` save (0 found). The save mark and its refusal
  are not written yet in the robot (there is no OK A save to mark); they must exist before the first OK A run.

## Round 24 integrate (2026-11-18 night) [high unless tagged]

- **Round 24 in one line.** F-031 (owner 2026-11-17 ~15:20, continued as round 24 at 20:15): Conquest from
  chapter 16 and Revelation from chapter 21, real play per chapter, one fresh helper per chapter, counted 375 min
  from 20:20 (hard stop 540). **Five chapters proven and packed: cq-ch16, rv-ch21, rv-ch22, rv-ch23, rv-ch24.**
  cq-ch17 is NOT cleared (chain c17/c17b at frame 144711, turn 19; no route key, no checkpoints). Nobody lost in
  any kept chain; no poke, no cheat save. Each chapter's own section: 3z-cq16, 3z-cq17b and the Round 24 rv-ch21 to
  rv-ch24 sections above.
- **Proofs** (two copies, same memory, every checkpoint): cq-ch16 r24-cq-ch16 (944e6ad3cb505d60, 168,600 frames);
  rv-ch21 r24-rv-ch21 (4982b7be624bfff5, 118,284); rv-ch22 r24-proof-rv-ch22 (88035f6e3c200c70, 91,194); rv-ch23
  r24-proof-rv-ch23 (d9a2fff8178d8c4e, 200,166); rv-ch24 r24-proof-rv-ch24 (40ce706031026a9e, 149,388). Clear saves
  packed in build/harness/saves: cq-ch16-clear, rv-ch21-clear, rv-ch22-clear, rv-ch23-clear, rv-ch24-clear. The
  proof steps' captures (r24-cap-*) were all PASS, 0 bad, but only r24-cap-rv-ch22 kept records, and three of them
  (cq-ch16, rv-ch21, rv-ch22) ran on an older library (rounds 25-27 added overrides during round 24).
- **Library:** `build.py --check-fresh` **FRESH** (2026-11-18T00:03:44, round 27's build, 266 overrides). Not
  rebuilt (no reader code changed this round).
- **Plan** (build/speed/r24int/plan-play.txt, plan-cheat.txt): real play (round 27's sessions plus
  r24-cap-rv-ch22): **PLAN LINE 1, routes: 54 replay offline from their records, 0 must play live (route changed).
  PLAN LINE 2, overrides: 266 decided by the records (18 by the batches' own captures on 58 routes, 1 watched and
  never called), 0 must play live.** Cheat (round 27's cheat sessions plus r27-capc-readers): **PLAN LINE 1: 4
  routes offline, 0 live. PLAN LINE 2: 266 decided (32 by the batches' own captures), 0 live.** The plan does not
  see the five new routes (no usable records on this library), so they played LIVE with every override
  (`--only all`); r24-cap-rv-ch22 was then left out of the offline replay so no record counts twice.
- **Runs, started at once (01:42:36, FEF_ROBOT_JOBS=12, below normal):**
  - Offline, real play (`offline.py replay ... --name r24-off --jobs 4`): 232 runs, **209,652 records (204,043
    match, 3,715 gave up, 1,894 incomplete), 0 bad, offline verdict != captured verdict 0**, 185 s.
  - Offline, cheat apart (`r24-offc --jobs 2`): 79 runs, **10,452 records (9,950 match), 0 bad, 0 verdict
    differences**, 47 s.
  - Live, the five new routes (`parallel.py runs --route rv-ch23 --route cq-ch16 --route rv-ch24 --route rv-ch21
    --route rv-ch22 --mode capture --markers --only all --store-keep --longest-first --timeout 3600 --session
    r24-capn`): 5 of 5 exit 0, wall 1,192 s; **20,010 records (19,357 match, 533 gave up, 120 incomplete), 0 bad
    of any kind**. Every memory hash equals its proof (above). No writer stored; %APPDATA% unchanged.
  - Per family, real play (h6three number 3): Birthright 33 routes 113,140 records; Conquest 11, 42,388;
    Revelation 19, 72,042; options 2, 2,092; **0 bad and 0 other differences in each**; all 65 routes 229,662
    records. Cheat apart: 4 routes, 10,452 records, 0 bad.
- **H5** (`h56.py h5 --sessions <the h56-h5 row's 26> --label play --run-id r24-h5 --no-exact --jobs 12
  --jobs-over-budget`): 125 s; **232 of 266 met, 229,662 records (223,400 match, 4,248 gave up), 0 bad, offline !=
  live 0**; lines 1,500/1,735, branches 1,060/1,641 (64.6%). Never met: the same 34.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r24-off/offline.json --offline-cheat build/speed/replay/r24-offc/offline.json --live
  build/parallel/r24-capn/summary.json --json build/h6three/three-r24.json`): (1) 2,214 / 3,696 (59.9%; 62.9%
  also leaving out helper lines), round 13's sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host
  92.6%, 36 files; (3) 65 routes, 229,662 records, 0 bad; cheat 10,452, 0 bad.
- **check_all** (docs/CHECK_ALL.md round 24): robot-routes requires the five new clear saves (65 verified
  real-play routes); h56-h5 reads 26 sessions (r24-capn added); tests 85 OK. Fast 47 pass (2 min 56 s); touched
  rows selftest, robot-routes, cheat-endgame 3 pass (1 min 27 s); `--only h56-h5` alone PASS (2 min 12 s).
- **Evidence**: `evidence.py pack` (138.9 MB in all; new: r24-capn 2.2 MB, the five proofs and five proof
  captures). `clean --yes --keep-sessions 10 --keep <every r10-r28 session, runs-*, every r*-h5>` **refused**:
  another helper's boot.exe (build/parallel/runs-20261118-020807, started at frame 144712: the cq-ch17 chain) was
  running. Not forced; nothing removed. D: 99 GB free.
- **Open**: cq-ch17 (Kotaro at 16/38 on turn 19; turn-19 battles look fixed; next plan in 3z-cq17b; F-033 now
  allows a declared, counted movement cheat from chapter 17); proof steps should keep records (`--store-keep
  --only all`) so integrate can replay them offline instead of 20 min live; whether Shura joined in cq-ch16 is not
  checked; Elise's Physic needs staff rank C (she carries Mend now); the scratch danger.py patches (C023 blocks,
  C024 lit regions) live only in build/speed; 34 readers never met; the looks; OK B open.

## Round 37 integrate (2026-11-18 evening) [high unless tagged]

- **Round 37 in one line.** F-033 and F-036 with F-030/F-031: Conquest on the cheat track from chapter 24 with the
  declared HP/Def/Res boost, counted 495 min from 13:30 (hard stop 11 h), beside rounds 35/38 and 36/39. **Five routes
  proven: cheat-cq-ch24 (106 boost pokes), cheat-cq-ch25 (8 pokes, Leo), cheat-cq-ch26 (none of its own),
  cheat-cq-ch27 (none of its own) and cheat-cq-endgame (one poke, Takumi's HP 60 -> 1)**; nobody lost; two equal copies
  each; ch24-26 clear saves packed with the cheat mark; ch27 and the Endgame have no clear save by design (the ch27
  proof's packed zip was cheat-cq-ch26-clear byte for byte and was set aside as NOT-A-CLEAR-SAVE). The Conquest
  ending ran to the title screen. Sections 3z-cq24b, 3z-cq25, 3z-cq26, 3z-cq27 (proof lines added at integrate),
  3z-cqend.
- **Library:** `build.py --check-fresh` **STALE** (round 38's committed menu writer edits: menu_config.c,
  menu_config_writer.c, menu_danger.c, menu_options_hook.c). **Rebuilt** (`build.py --swap`, 18:04-18:11, 385 s, 266
  overrides, 65 staged, 5 writers never stubbed); FRESH after. At 18:27 another round edited menu_config_writer.c and
  menu_options_hook.c again (uncommitted), so the cheat replays ran with `--rev 7b146ba` (source gate passed). The
  real-play replay ran at 18:13-18:17, before that edit, on the tree.
- **Plan** (build/speed/r37int/plan-play.txt, plan-cheat0.txt, plan-cheat.txt; vars.sh = round 36's sets plus
  r37-capc-cheat-cq-ch24..27 and r37-capc2-endgame). Real play: **PLAN LINE 1, routes: 54 replay offline from their
  records, 0 must play live. PLAN LINE 2, overrides: 266 decided by the records (18 by the batches' own captures on
  64 routes, 1 watched and never called), 0 must play live.** The proof captures r37-cap-cheat-cq-ch24..27 kept no
  records, and the library changed after r37-capc-endgame was made, so all five new routes played **live once with
  every override and `--store-keep`** (18:11:22, all at once, FEF_ROBOT_JOBS=4 each, below normal). Cheat plan with
  those added: **PLAN LINE 1: 4 offline (plus the cheat routes from their extra records), 0 live. PLAN LINE 2: 266
  decided (32 by the batches' own captures, 9 watched and never called), 0 live.** cheat-rv-ch27 and cheat-rv-endgame
  showed as "routes.json entry changed after the records" (offline.py's mtime rule: their entries equal commit
  e9d2950, which was written from the same text round 36 recorded with); they were replayed with `--ignore-plan`
  (r37-offrv). r15-cap-capability (pre-fix) not used.
- **Runs** (all below normal):
  - Live cheat-cq-ch24 (r37-capc-cheat-cq-ch24): exit 0, 43112 frames, memory 372863cca6511895 (equal to the proof),
    checkpoints all met, 481 s; **180 functions, 4,778 records (4,604 match, 111 gave up, 63 incomplete), 0 bad**.
  - Live cheat-cq-ch25 (r37-capc-cheat-cq-ch25): 64530 frames, memory d639641062f7591e (equal), 639 s; **172
    functions, 5,101 records (4,976 / 90 / 35), 0 bad**.
  - Live cheat-cq-ch26 (r37-capc-cheat-cq-ch26): 128394 frames, memory 67190ee9f1126f00 (equal), 972 s; **184
    functions, 4,121 records (3,988 / 90 / 43), 0 bad**.
  - Live cheat-cq-ch27 (r37-capc-cheat-cq-ch27): 89424 frames, memory 4fcd68e281abd835 (equal), 891 s; **177
    functions, 3,822 records (3,683 / 92 / 47), 0 bad**.
  - Live cheat-cq-endgame (r37-capc2-endgame): 198700 frames, memory cd5d0d3dca2b7e5b (equal), 1,068 s, peak 816 MB;
    **179 functions, 5,972 records (5,814 / 93 / 65), 0 bad**. No writer stored anything; %APPDATA% unchanged in all.
  - Real play (`offline.py replay ... --name r37-off --jobs 6`, FEF_ROBOT_JOBS=12): 239 runs, **67 routes, 238,051
    records (231,510 match, 4,470 gave up, 2,071 incomplete), 0 bad, offline != captured verdict 0**, 269 s.
  - Cheat apart (`r37-offc2`, `--rev 7b146ba`, after the live runs): 96 runs, **16 routes, 66,243 records (64,091
    match, 1,485 gave up, 667 incomplete), 0 bad, 0 verdict differences**, 79 s. `r37-offrv` (`--ignore-plan`):
    cheat-rv-ch27 and cheat-rv-endgame, 7 runs, 20,487 records, 0 bad. Cheat in all: **18 routes, 86,730 records, 0
    bad**. (The first try, `r37-offc`, stopped at the source gate on the 18:27 edits.)
  - Per family, real play (h6three number 3): Birthright 33 routes 113,140 records; Conquest 11, 42,388; Revelation
    21, 80,431; options 2, 2,092; **0 bad and 0 other differences in each**.
- **H5** (`h56.py h5 --sessions <the h56-h5 row's 28> --label play --run-id r37-h5 --no-exact --jobs 12
  --jobs-over-budget`, 18:13-18:17): **233 of 266 met, 238,051 records (231,510 match, 4,470 gave up), 0 bad,
  offline != live 0**; lines 1,503/1,738, branches 1,061/1,643 (64.6%). Never met: the same 33.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r37-off/offline.json --offline-cheat build/speed/replay/r37-offc2/offline.json --live ""
  --json build/h6three/three-r37.json`): (1) 2,214 / 3,696 (59.9%; 62.9% also leaving out helper lines), round 13's
  sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host 92.6%, 36 files; (3) 67 routes, 238,051
  records, 0 bad; cheat apart 0 bad.
- **check_all** (docs/CHECK_ALL.md round 37): tests 95 OK (1 skipped); fast 51 pass; touched rows 5 pass;
  `--only h56-h5` alone PASS.
- **Evidence**: `tools/evidence/evidence.py pack` (176.9 MB in all); `clean --yes --keep-sessions 10 --keep <every
  session folder in build/parallel, every rNN-h5>` (build/speed/r37int/keep.txt): freed 0 items.
- **Open:** real-play Conquest 17+ (none won without a poke); Gunter's 97 -> 49 HP in ch24 enemy phase 1 not traced
  [medium]; the Conquest ending movie skipped with START; danger.py/near.py do not know opened doors; seize.json's
  until-wait on door maps; offline.py's mtime rule for uncommitted cheat routes; 33 readers never met.

## Round 36 integrate (2026-11-18 afternoon) [high unless tagged]

- **Round 36 in one line.** F-035 with F-030/F-031: Revelation 27 on the cheat track (`cheat-rv-ch27`, movement
  only, 6 pokes) and then the Revelation Endgame on the cheat track (`cheat-rv-endgame`, 10 pokes in all); counted
  315 min from 13:15 (hard stop 480), beside rounds 34 and 35. **Both are proven now**: cheat-rv-ch27 by its proof
  step (r36-proof-cheat-rv-ch27), cheat-rv-endgame by integrate (r36-proof2-cheat-rv-endgame, `--timeout 6000`, both
  copies memory f03306be7ca8af55 and 1,692,525,067,200 instructions, equal to the capture r36-capc-endgame; verified
  true by a checked read-modify-write of that one key, build/speed/r36int/verify_endgame.py, a 2-line diff).
  Revelation is now played to the end: chapters to 26 in real play, 27 and the Endgame on the cheat track.
- **cheat-rv-ch27-clear.zip moved aside (F-029).** It held rv-ch26-clear's save files byte for byte (no save after
  chapter 27), so the fingerprint rule (headless.save_is_cheat) made **rv-ch26-clear read as a cheat save**. Moved to
  build/harness/saves-aside/ (not deleted); rv-ch26-clear is real play again (`save_is_cheat` -> None; cheats.py
  --check: 98 real-play start saves, none cheat). check_all `cheat-endgame` now lists cheat-rv-ch27 and
  cheat-rv-endgame beside cheat-bt-endgame and fails if a clear zip comes back.
- **Library:** `build.py --check-fresh` said **STALE**, only because of another round's uncommitted writer edits in
  src/readable/menu/ (an unarmed W2 restore function and comments). The library equals **HEAD d0d9b4e** exactly
  (offline.py's source gate passed with `--rev d0d9b4e`; it failed on the working tree and on 7e1b4dc). Not rebuilt,
  so this round's proof captures count.
- **Plan** (build/speed/r36int/plan-play.txt, plan-cheat0.txt, plan-cheat.txt; vars.sh = round 34's sets plus
  r36-capc-cheat-rv-ch27 and r36-capc-endgame). Real play: **PLAN LINE 1, routes: 54 replay offline from their
  records, 0 must play live. PLAN LINE 2, overrides: 266 decided by the records (18 by the batches' own captures on
  64 routes, 1 watched and never called), 0 must play live.** The ch27 proof capture r36-cap-cheat-rv-ch27 kept no
  records, so cheat-rv-ch27 played **live once with every override and `--store-keep`** (r36-capc-cheat-rv-ch27,
  16:24-16:58). Cheat plan: **PLAN LINE 1: 4 offline (plus the cheat-cq, cheat-rv-ch27 and cheat-rv-endgame routes
  from their extra records), 0 live. PLAN LINE 2: 266 decided (32 by the batches' own captures on 12 routes, 9
  watched and never called), 0 live.** In the second cheat plan (after 16:58) cheat-rv-endgame's records showed as
  "routes.json entry changed after the records": another round wrote routes.json at 16:56:40 and an uncommitted
  route's change time is the file's mtime. Its input, frames, start save and all 10 pokes equal the records' run.json,
  so the first cheat replay (r36-offcheat, 16:34, plan offline) is the one counted for it.
- **Runs** (all below normal):
  - Real play (`offline.py replay ... --rev d0d9b4e --name r36-offc --jobs 6`, FEF_ROBOT_JOBS=12): 239 runs, **67
    routes, 238,051 records (231,510 match, 4,470 gave up, 2,071 incomplete), 0 bad, offline != captured verdict 0**,
    145 s.
  - Cheat (`r36-offcheat`, --rev d0d9b4e): 93 runs, **12 routes, 55,512 records (53,930 match, 1,119 gave up), 0
    bad, 0 verdict differences** (includes cheat-rv-endgame, 13,063 records). `r36-offcheat2` (after the live run):
    cheat-rv-ch27's records 7,424 (7,298 match, 110 gave up, 16 incomplete), 0 bad.
  - Live cheat-rv-ch27 (r36-capc-cheat-rv-ch27): exit 0, Completed 261200 frames, memory b4025f15b3475c00 (equal to
    the proof), checkpoints all met, peak 786 MB, 2,015 s; **183 functions, 7,424 records, 0 bad of any kind**, no
    writer stored anything, %APPDATA% unchanged.
  - Proof cheat-rv-endgame (r36-proof2-cheat-rv-endgame): 2/2 PASS, 2,260 s each.
  - Per family, real play: Birthright 33 routes 113,140 records; Conquest 11, 42,388; Revelation 21, 80,431; options
    2, 2,092; **0 bad in each**. Cheat apart: 13 routes, 62,936 records, 0 bad.
- **H5** (`h56.py h5 ... --label play --run-id r36-h5 --no-exact --jobs 12 --jobs-over-budget`, 16:25-16:28): **233
  of 266 met, 238,051 records (231,510 match, 4,470 gave up), 0 bad, offline != live 0**; branches 1,061/1,643
  (64.6%). Never met: the same 33.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (build/h6three/three-r36.json):
  (1) 2,214 / 3,696 (59.9%; 62.9% also leaving out helper lines), round 13's sample; (2) host test alone 3,700 /
  4,009 (92.3%), records or host 92.6%, 36 files; (3) 67 routes, 238,051 records, 0 bad; cheat apart 0 bad.
- **check_all** (docs/CHECK_ALL.md round 36): tests 94 OK (1 skipped); fast 51 pass; touched rows 5 pass (twice:
  before and after cheat-rv-endgame joined the table); `--only h56-h5` alone PASS.
- **Evidence**: `evidence.py pack` (169.4 MB in all); `clean --yes --keep-sessions 10 --keep <every session folder
  in build/parallel, every rNN-h5>` (build/speed/r36int/keep.txt): freed 0.11 GB (5 old robot scratch states).
- **Open:** Conquest 24 to 27 and its Endgame (round 34's track); the Endgame objective card wait of 20,000 frames
  in cheat-rv-endgame (harmless, about 100 s per replay); the ch27 banner's 43-turn count not traced [medium];
  offline.py's mtime rule for uncommitted cheat routes (any routes.json write by another round sends them live);
  33 readers never met.

## Round 34 integrate (2026-11-18 midday) [high unless tagged]

- **Round 34 in one line.** F-033 (and F-031): Conquest on the cheat track from chapter 20, counted 495 min from
  09:45 (hard stop 660), beside rounds 33 and 35. **Four chapters proven: cheat-cq-ch20, cheat-cq-ch21,
  cheat-cq-ch22, cheat-cq-ch23** (no pokes of their own: each starts from the one before's cheat clear save, which
  already holds the move bonus 60; nobody lost; two equal copies each; clear saves packed with the cheat mark;
  verified). **cheat-cq-ch24 is NOT cleared** (two helpers, 35 + 10 min of play; chains build/speed/cqx24/c and e; no
  route key): the turn-1 Hinoka kill always costs Gunter, and blockers die in enemy phase 1, so with movement only it
  was stopped and reported (F-033). Conquest 25 to 27 and its Endgame not started. The real-play key cq-ch17 and later
  stay unwritten (none won without a poke). Sections 3z-cq20b, 3z-cq21, 3z-cq22, 3z-cq23, 3z-cq24.
- **Library:** `build.py --check-fresh` **FRESH** (built 2026-11-18T10:44:17 by round 33, 65 staged files, 266
  overrides). Not rebuilt (no reader code changed).
- **Plan** (build/speed/r34int/plan-play.txt, plan-cheat.txt; vars.sh = round 33's sets plus the four new cheat
  sessions). Real play, unchanged set: **PLAN LINE 1, routes: 54 replay offline from their records, 0 must play
  live. PLAN LINE 2, overrides: 266 decided by the records (18 by the batches' own captures on 64 routes, 1 watched
  and never called), 0 must play live.** The proof captures r34-cap-cheat-cq-ch20..23 kept no records (run without
  `--store-keep`), so all four played **live once with every override and `--store-keep`** (r34-capc-cheat-cq-ch20,
  -ch21, -ch22, -ch23; 12:58:25, all at once, FEF_ROBOT_JOBS=4 each, below normal). Cheat plan with those added
  (r10-capc, r11-capc; extra r12-capc-* to r27-capc-*, r29-capc-cheat-cq-ch17, r32-capc-cheat-cq-ch18/19,
  r34-capc-cheat-cq-ch20..23): **PLAN LINE 1: 4 offline (plus the seven cheat-cq routes from their extra records), 0
  live. PLAN LINE 2: 266 decided (32 by the batches' own captures on 11 routes, 9 watched and never called), 0
  live.** r15-cap-capability (pre-fix) not used.
- **Runs**, all started at once (12:58-13:12, below normal):
  - Live cheat-cq-ch20 (r34-capc-cheat-cq-ch20): exit 0, Completed 223386 frames, memory 2737fb0dea13f91a (equal to
    the proof), checkpoints all met, peak 706 MB, 738 s, %APPDATA% unchanged; **187 functions, 4,373 records (4,241
    match, 97 gave up, 35 incomplete), 0 bad of any kind**, no writer stored anything.
  - Live cheat-cq-ch21 (r34-capc-cheat-cq-ch21): exit 0, Completed 51752 frames, memory b0b3c09ee71138cd (equal),
    checkpoints all met, peak 498 MB, 158 s; **103 functions, 2,384 records (2,286 / 69 / 29), 0 bad**.
  - Live cheat-cq-ch22 (r34-capc-cheat-cq-ch22): exit 0, Completed 32716 frames, memory a3d1ce80f2fa2a74 (equal),
    checkpoints all met, peak 669 MB, 152 s; **150 functions, 2,826 records (2,699 / 90 / 37), 0 bad**.
  - Live cheat-cq-ch23 (r34-capc-cheat-cq-ch23): exit 0, Completed 36522 frames, memory bd79d0e50a8ded72 (equal),
    checkpoints all met, peak 612 MB, 141 s; **148 functions, 2,789 records (2,653 / 84 / 52), 0 bad**.
  - Real play (`offline.py replay ... --name r34-off --jobs 6`, FEF_ROBOT_JOBS=12): 239 runs, **67 routes, 238,051
    records (231,510 match, 4,470 gave up, 2,071 incomplete), 0 bad, offline != captured verdict 0**, 197.9 s.
  - Cheat apart (`r34-offc --jobs 4`, after the live runs): 88 runs, **11 routes, 42,449 records (41,026 match,
    1,009 gave up, 414 incomplete), 0 bad, 0 verdict differences**, 55.2 s.
  - Per family, real play (h6three number 3): Birthright 33 routes 113,140 records; Conquest 11, 42,388; Revelation
    21, 80,431; options 2, 2,092; **0 bad and 0 other differences in each**. Cheat apart: 11 routes, 42,449 records,
    0 bad.
- **H5** (`h56.py h5 --sessions <the h56-h5 row's 28> --label play --run-id r34-h5 --no-exact --jobs 12
  --jobs-over-budget`, 13:03:26-13:05:48): **233 of 266 met, 238,051 records (231,510 match, 4,470 gave up), 0 bad,
  offline != live 0**; lines 1,503/1,738, branches 1,061/1,643 (64.6%). Never met: the same 33.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r34-off/offline.json --offline-cheat build/speed/replay/r34-offc/offline.json --live ""
  --json build/h6three/three-r34.json`): (1) 2,214 / 3,696 (59.9%; 62.9% also leaving out helper lines), round 13's
  sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host 92.6%, 36 files; (3) 67 routes, 238,051
  records, 0 bad; cheat 11 routes, 42,449 records, 0 bad.
- **check_all** (docs/CHECK_ALL.md round 34): `cheat-conquest`'s CHEAT_CQ_PACKS now lists cheat-cq-ch20 to ch23,
  each from the one before's cheat clear save. Tests 93 OK (1 skipped). Fast 51 pass; `--only selftest,
  robot-routes,cheat-routes,cheat-endgame,cheat-conquest` 5 pass (12 cheat routes, 7 proven Conquest cheat routes);
  `--only h56-h5` alone PASS (233 of 266, 238,051 records).
- **Evidence**: `tools/evidence/evidence.py pack` (154.5 MB in all; new: r34-proof-cheat-cq-ch20..23 0.6-1.2 MB each,
  r34-capc-cheat-cq-ch20..23, r34-cap-cheat-cq-*, r34-cqx2x-markers). `clean --yes --keep-sessions 10 --keep <every
  session folder in build/parallel, every rNN-h5>` (build/speed/r34int/keep.txt): freed 0.00 GB (0 items). D: 80 GB
  free.
- **Open:** cheat-cq-ch24 (owner's call: F-033 allows movement only, and two helpers found no way to win with it;
  chains build/speed/cqx24/c at 27822 and e at 40474); Conquest 25 to 27 and its Endgame wait for it; proof captures
  should keep records (`--only all --store-keep`) so integrate need not play them again; 33 readers never met.

## Round 33 integrate (2026-11-18 late morning) [high unless tagged]

- **Round 33 in one line.** F-031 (and F-030 for the Endgame only): Revelation 27 in real play, then its Endgame on
  the cheat track; counted 315 min from 09:20 (hard stop 480), beside round 34 (cheat-cq-ch20, still proving at
  integrate time). **No chapter was proven.** One play helper (the section "rv-ch27, fourth helper (round 32)"
  above; it ran for this round, 10:06-10:42) solved the turn-34 trap and played turns 34-40 with nobody lost, but
  rv-ch27 is NOT cleared: restart point build/speed/rv27i/c27i_t41_backup (turn 41, frame 238,284, 6 of 6 alive).
  No route key, markers, export, proof or capture (no r33-cap-rv-* session). **cheat-rv-endgame not started** (it
  needs the chain state after chapter 27, F-029; no r33-capc-endgame session).
- **Library:** `build.py --check-fresh` said **STALE**: 6 staged files changed since round 27's build (core__capture.c,
  core__options.c, core__runtime.c, core__writer.c, ...). The cause is not a reader: it is F-034's writer work in the
  tree (writer.c table rows 2 and 3, fe_writer.h, the new core/options.c and menu_options_hook.c; every writer row
  armed 0). As the brief says, rebuilt with `build.py --swap` (10:44:16, below normal, 342 s): "targets: OK (266
  override(s), 68 of them guard users, 0 probe(s), 5 writer(s))", 120,500,331 bytes, swapped; `--check-fresh` then
  **FRESH** (built 2026-11-18T10:44:17, 65 staged files). The override list and targets.csv did not change, so every
  kept record still decides its override (plan below), and the offline source gate passed on the new library
  (14c198394f1c). Nothing new was captured on it this round.
- **Plan** (build/speed/r33int/plan-play.txt, plan-cheat.txt; vars.sh = round 32's sets unchanged: no new real-play
  or cheat session this round). Real play: **PLAN LINE 1, routes: 54 replay offline from their records, 0 must play
  live. PLAN LINE 2, overrides: 266 decided by the records (18 by the batches' own captures on 64 routes, 1 watched
  and never called), 0 must play live.** Cheat (r10-capc, r11-capc; extra r12-capc-* to r27-capc-*,
  r29-capc-cheat-cq-ch17, r32-capc-cheat-cq-ch18/19): **PLAN LINE 1: 4 offline, 0 live. PLAN LINE 2: 266 decided (32
  by the batches' own captures on 7 routes, 9 watched and never called), 0 live.** LIVE TOTAL: nothing plays live.
  r15-cap-capability (pre-fix) not used. cheat-cq-ch20 (round 34's, proof running) is not in any session and is left
  to round 34's integrate.
- **Runs (10:51:36, FEF_ROBOT_JOBS=12, below normal), offline only, all at once with H5:**
  - Real play (`offline.py replay ... --name r33-off --jobs 6`): 239 runs, **67 routes, 238,051 records (231,510
    match, 4,470 gave up, 2,071 incomplete), 0 bad, offline != captured verdict 0**, 212.7 s.
  - Cheat apart (`r33-offc --jobs 4`): 84 runs, **7 routes, 30,077 records (29,147 match, 669 gave up, 261
    incomplete), 0 bad, 0 verdict differences**, 43.3 s.
  - Per family, real play (h6three number 3): Birthright 33 routes 113,140 records; Conquest 11, 42,388; Revelation
    21, 80,431; options 2, 2,092; **0 bad and 0 other differences in each**. Cheat apart: 7 routes, 30,077, 0 bad.
- **H5** (`h56.py h5 --sessions <the h56-h5 row's 28> --label play --run-id r33-h5 --no-exact --jobs 12
  --jobs-over-budget`, 10:51:36-10:54:00): **233 of 266 met, 238,051 records (231,510 match, 4,470 gave up), 0 bad,
  offline != live 0**; lines 1,503/1,738, branches 1,061/1,643 (64.6%). Never met: the same 33.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r33-off/offline.json --offline-cheat build/speed/replay/r33-offc/offline.json --live ""
  --json build/h6three/three-r33.json`): (1) 2,214 / 3,696 (59.9%; 62.9% also leaving out helper lines), round 13's
  sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host 92.6%, 36 files; (3) 67 routes, 238,051
  records, 0 bad; cheat 7 routes, 30,077, 0 bad.
- **check_all** (docs/CHECK_ALL.md round 33): no table change (nothing proven); tests 92 OK (1 skipped). Fast 48
  pass; `--only selftest,robot-routes,cheat-routes,cheat-endgame,cheat-conquest,readable` **6 pass** (readable
  because the library was rebuilt over F-034's files: host test 146/146; cheat-routes now sees 9 cheat routes,
  round 34's cheat-cq-ch20 included); `--only h56-h5` alone PASS.
- **Evidence**: `tools/evidence/evidence.py pack` (149.7 MB in all; it also packed round 34's sessions, one of them
  still running, so round 34 should pack again after its proof). `clean --yes --keep-sessions 10 --keep <every
  session folder in build/parallel, every rNN-h5>` (build/speed/r33int/keep.txt) **refused: "boot.exe is running"**
  (round 34's proof); not forced, nothing deleted. D: 86 GB free.
- **Open:** rv-ch27 (restart from build/speed/rv27i/c27i_t41_backup; turn 41: keep Shura away from the Great Knight
  and the Maid or kill the Great Knight outright; boss about 20 tiles away, so a full cap); cheat-rv-endgame after
  it; the clean step after round 34's boot.exe exits; 33 readers never met.

## Round 32 integrate (2026-11-18 morning) [high unless tagged]

- **Round 32 in one line.** F-033 (and F-031): Conquest on the cheat track from chapter 18, counted 495 min from
  05:00 (hard stop 660), beside round 31. **Two chapters proven: cheat-cq-ch18 and cheat-cq-ch19** (no pokes of
  their own: each starts from the one before's cheat clear save, which already holds the move bonus 60; nobody lost;
  two equal copies each; clear saves packed with the cheat mark; verified). **cheat-cq-ch20 is NOT cleared** (two
  helpers, 41 + 28 min; chain build/speed/cqx20/h or its frame-0 rebuild i at frame 124358, turn 9 player phase, 14
  of 14 alive, 17 enemies left; no route key). Conquest 21 to 23 not started. The real-play key cq-ch17 and later
  stay unwritten (none won without a poke). Sections 3z-cq18c, 3z-cq19, 3z-cq20.
- **Library:** `build.py --check-fresh` **FRESH** (2026-11-18T00:03:44, round 27's build, 266 overrides). Not
  rebuilt (no reader code changed).
- **Plan** (build/speed/r32int/plan-play.txt, plan-cheat.txt; vars.sh). Real play, the round 31 set unchanged (no
  new real-play route): **PLAN LINE 1, routes: 54 replay offline from their records, 0 must play live. PLAN LINE 2,
  overrides: 266 decided by the records (18 by the batches' own captures on 64 routes, 1 watched and never called),
  0 must play live.** The proof captures r32-cap-cheat-cq-ch18/19 kept no records (run without `--store-keep`), so,
  as in round 29, both played **live once with every override and `--store-keep`** (r32-capc-cheat-cq-ch18,
  r32-capc-cheat-cq-ch19; 09:19:43, both at once, FEF_ROBOT_JOBS=4 each, below normal). Cheat plan with those added
  (r10-capc, r11-capc; extra r12-capc-* to r27-capc-*, r29-capc-cheat-cq-ch17, r32-capc-cheat-cq-ch18/19): **PLAN LINE
  1: 4 offline (plus the three cheat-cq routes from their extra records), 0 live. PLAN LINE 2: 266 decided (32 by the
  batches' own captures on 7 routes, 9 watched and never called), 0 live.** r15-cap-capability (pre-fix) not used.
- **Runs**, all started at once (09:19-09:34, FEF_ROBOT_JOBS=12 for the offline lanes, below normal):
  - Live cheat-cq-ch18 (r32-capc-cheat-cq-ch18): exit 0, Completed 170920 frames, memory defb76ac07db4286 (equal to
    the proof), checkpoints all met, peak 667 MB, 728 s, %APPDATA% unchanged; **185 functions, 4,253 records (4,127
    match, 88 gave up, 38 incomplete), 0 bad of any kind**, no writer stored anything.
  - Live cheat-cq-ch19 (r32-capc-cheat-cq-ch19): exit 0, Completed 172690 frames, memory faf6fbe0ae8619bf (equal to
    the proof), checkpoints all met, peak 668 MB, 794 s, %APPDATA% unchanged; **179 functions, 4,032 records (3,903
    match, 92 gave up, 37 incomplete), 0 bad of any kind**, no writer stored anything.
  - Real play (`offline.py replay ... --name r32-off --jobs 6`): 239 runs, **67 routes, 238,051 records (231,510
    match, 4,470 gave up, 2,071 incomplete), 0 bad, offline != captured verdict 0**, 187.6 s.
  - Cheat apart (`r32-offc --jobs 4`, after the two live runs): 84 runs, **7 routes, 30,077 records (29,147 match,
    669 gave up, 261 incomplete), 0 bad, 0 verdict differences**, 37.6 s.
  - Per family, real play (h6three number 3): Birthright 33 routes 113,140 records; Conquest 11, 42,388; Revelation
    21, 80,431; options 2, 2,092; **0 bad and 0 other differences in each**. Cheat apart: 7 routes, 30,077 records,
    0 bad.
- **H5** (`h56.py h5 --sessions <the h56-h5 row's 28> --label play --run-id r32-h5 --no-exact --jobs 12
  --jobs-over-budget`, 09:25:32-09:27:40): **233 of 266 met, 238,051 records (231,510 match, 4,470 gave up), 0 bad,
  offline != live 0**; lines 1,503/1,738, branches 1,061/1,643 (64.6%). Never met: the same 33.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r32-off/offline.json --offline-cheat build/speed/replay/r32-offc/offline.json --live ""
  --json build/h6three/three-r32.json`): (1) 2,214 / 3,696 (59.9%; 62.9% also leaving out helper lines), round 13's
  sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host 92.6%, 36 files; (3) 67 routes, 238,051
  records, 0 bad; cheat 7 routes, 30,077 records, 0 bad.
- **check_all** (docs/CHECK_ALL.md round 32): `cheat-conquest`'s CHEAT_CQ_PACKS now lists cheat-cq-ch18 (from
  cheat-cq-ch17-clear) and cheat-cq-ch19 (from cheat-cq-ch18-clear); a listed route that starts from another listed
  route's cheat clear save may declare no pokes. Tests 92 OK (1 skipped). Fast 48 pass; `--only selftest,
  robot-routes,cheat-routes,cheat-endgame,cheat-conquest` 5 pass (8 cheat routes, 3 proven Conquest cheat routes);
  `--only h56-h5` alone PASS (233 of 266, 238,051 records).
- **Evidence**: `tools/evidence/evidence.py pack` (148.2 MB in all; new: r32-cap-cheat-cq-ch18/19 0.2 MB each,
  r32-capc-cheat-cq-ch18/19 0.4 MB each, r32-proof-cheat-cq-ch18/19 1.0 MB each). `clean --yes --keep-sessions 10
  --keep <every session folder in build/parallel, every rNN-h5>` (build/speed/r32int/keep.txt): freed 0.00 GB (0
  items). D: 89 GB free.
- **Open:** cheat-cq-ch20 (continue from cqx20/h or i at 124358: the corridor pair (12,5), then the boss Fuga);
  Conquest 21 to 27 and its Endgame; proof captures should keep records (`--only all --store-keep`) so integrate
  need not play them again; 33 readers never met.

## Round 31 integrate (2026-11-18 morning) [high unless tagged]

- **Round 31 in one line.** F-031 (and F-030 for the Endgame only), owner 2026-11-18 02:25: Revelation 25-27 in
  real play, then its Endgame on the cheat track; counted 315 min from 04:10 (hard stop 480). **Two chapters
  proven: rv-ch25 and rv-ch26** (real play, no pokes; two equal copies each; clear saves packed; proof captures
  r31-cap-rv-ch25 and r31-cap-rv-ch26, every override, records kept, 0 bad). **rv-ch27 is NOT cleared** (two
  helpers; the kept restart point is build/speed/rv27/c27r_t26_backup, turn 26, frame 141,736, 6 of 6 alive; no
  route key). **cheat-rv-endgame not started** (it needs the chain state after chapter 27, F-029). Sections: rv-ch25
  CLEARED, rv-ch26, rv-ch27 above.
- **Library:** `build.py --check-fresh` **FRESH** (2026-11-18T00:03:44, round 27's build, 266 overrides). Not
  rebuilt (no reader code changed). Both proof captures ran on this same library, so they count.
- **Plan** (build/speed/r31int/plan-play.txt, plan-cheat.txt; vars.sh). Real play: main r10-capb, r11-capn,
  r11-capo, r12-capn, r13-capn, r14-capn, r15-capn; extra the round 30 list plus **r31-cap-rv-ch25, r31-cap-rv-ch26**.
  **PLAN LINE 1, routes: 54 replay offline from their records, 0 must play live (route changed). PLAN LINE 2,
  overrides: 266 decided by the records (18 by the batches' own captures on 64 routes, 1 watched and never called),
  0 must play live.** Cheat (r10-capc, r11-capc; extra r12-capc-* to r27-capc-*, r29-capc-cheat-cq-ch17): **PLAN
  LINE 1: 4 offline, 0 live. PLAN LINE 2: 266 decided (32 by the batches' own captures on 5 routes, 9 watched and
  never called), 0 live.** LIVE TOTAL: nothing plays live. r15-cap-capability (pre-fix) not used; r29-cap-cheat-cq-ch17
  (kept no records) replaced by its clean live rerun r29-capc-cheat-cq-ch17.
- **Runs (09:01:48, FEF_ROBOT_JOBS=12, below normal), offline only, all at once with H5:**
  - Real play (`offline.py replay ... --name r31-off --jobs 6`): 239 runs, **67 routes, 238,051 records (231,510
    match, 4,470 gave up, 2,071 incomplete), 0 bad, offline != captured verdict 0**, 170.5 s.
  - Cheat apart (`r31-offc --jobs 2`): 82 runs, **5 routes, 21,792 records (21,117 match), 0 bad, 0 verdict
    differences**, 40.4 s (cheat-cq-ch17 included through r29-capc-cheat-cq-ch17).
  - Per family, real play (h6three number 3): Birthright 33 routes 113,140 records; Conquest 11, 42,388;
    Revelation 21, 80,431; options 2, 2,092; **0 bad and 0 other differences in each**. Cheat apart: 5 routes,
    21,792 records, 0 bad.
- **H5** (`h56.py h5 --sessions <the h56-h5 row's 28> --label play --run-id r31-h5 --no-exact --jobs 12
  --jobs-over-budget`): 2 min 1 s; **233 of 266 met, 238,051 records (231,510 match, 4,470 gave up), 0 bad, offline
  != live 0**; lines 1,503/1,738, branches 1,061/1,643 (64.6%). **New met: `script_terrain_out_of_play_area`** (19
  records, all match, on Revelation 25/26). Never met: 33 (the round 30 34 less that one).
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r31-off/offline.json --offline-cheat build/speed/replay/r31-offc/offline.json --live ""
  --json build/h6three/three-r31.json`): (1) 2,214 / 3,696 (59.9%; 62.9% also leaving out helper lines), round 13's
  sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host 92.6%, 36 files; (3) 67 routes, 238,051
  records, 0 bad; cheat 5 routes, 21,792, 0 bad.
- **check_all** (docs/CHECK_ALL.md round 31): `robot-routes` now requires rv-ch25-clear and rv-ch26-clear; the
  `h56-h5` row has 28 sessions (r31-cap-rv-ch25, r31-cap-rv-ch26 added). Tests 90 OK (1 skipped). Fast 48 pass;
  `--only selftest,robot-routes,cheat-endgame,cheat-conquest` 4 pass (67 verified real-play routes); `--only
  h56-h5` alone PASS (233 of 266, 238,051 records).
- **Evidence**: `tools/evidence/evidence.py pack` (147.5 MB in all; new: r31-cap-rv-ch25 0.5 MB, r31-cap-rv-ch26
  0.4 MB, r31-proof-rv-ch25 1.4 MB, r31-proof-rv-ch26 1.0 MB). `clean --yes --keep-sessions 10 --keep <every
  session folder in build/parallel (other rounds' r31-cqx*, r32-* included), every rNN-h5>` (build/speed/r31int/
  keep.txt): freed 0.00 GB (0 items). D: 89 GB free.
- **Open:** rv-ch27 (restart from c27r_t26_backup: heal first, Corrin's and Takumi's pairs only on zero-threat
  tiles); cheat-rv-endgame after it; 33 readers never met.

## Round 30 integrate (2026-11-18 night) [high unless tagged]

- **Round 30 in one line.** F-031 (and F-030 for the Endgame only), owner 2026-11-18 02:25: Revelation 25-27 in
  real play, then Revelation's Endgame on the cheat track; counted 315 min from 02:25 (hard stop 480). **No chapter
  was proven.** rv-ch25 is NOT cleared (first helper 02:19-03:22, stopped at turn 33; continuation 03:24-03:46, turns
  33-38, stopped at turn 39 with Leo at 7 HP cornered by two Basaras on the dead-end vein tile (6,25)). rv-ch26,
  rv-ch27 and cheat-rv-endgame were not started. No route key, markers, export, proof, pack or capture for any of
  them (no r30-cap-rv-* or r30-capc-endgame session exists). Nobody lost in the kept chain; the turn-33 state is
  kept untouched in build/speed/rv25/c25_t33_backup (frame 166789, state.bin included). Details: the rv-ch25
  section above.
- **Library:** `build.py --check-fresh` **FRESH** (2026-11-18T00:03:44, round 27's build, 266 overrides). Not
  rebuilt (no reader code changed this round).
- **Plan** (build/speed/r30int/plan-play.txt, plan-cheat.txt). Real play: main r10-capb, r11-capn, r11-capo,
  r12-capn, r13-capn, r14-capn, r15-capn; extra the round 24 list with **r24-capn** (round 24 integrate's live
  capture of the five new routes, kept records, library 266) in place of r24-cap-rv-ch22 (so rv-ch22 counts once).
  **PLAN LINE 1, routes: 54 replay offline from their records, 0 must play live (route changed). PLAN LINE 2,
  overrides: 266 decided by the records (18 by the batches' own captures on 62 routes, 1 watched and never called),
  0 must play live.** Cheat (r10-capc, r11-capc; extra r12-capc-* to r27-capc-*): **PLAN LINE 1: 4 offline, 0 live.
  PLAN LINE 2: 266 decided (32 by the batches' own captures, 12 watched and never called), 0 live.** LIVE TOTAL:
  nothing plays live. r15-cap-capability (pre-fix) not used. cheat-cq-ch17 (round 29, F-033) is round 29's to
  integrate (its capture r29-cap-cheat-cq-ch17 kept no records); it was not run here.
- **Runs (03:45:43, FEF_ROBOT_JOBS=12, below normal), offline only:**
  - Real play (`offline.py replay ... --name r30-off --jobs 6`): 237 runs, **65 routes, 229,662 records (223,400
    match, 4,248 gave up, 2,014 incomplete), 0 bad, offline verdict != captured verdict 0**, 122.7 s. All five round
    24 routes now replay offline from r24-capn (no 20-minute live rerun).
  - Cheat apart (`r30-offc --jobs 2`): 79 runs, **4 routes, 10,452 records (9,950 match), 0 bad, 0 verdict
    differences**, 33 s.
  - Per family, real play (h6three number 3): Birthright 33 routes 113,140 records; Conquest 11, 42,388;
    Revelation 19, 72,042; options 2, 2,092; **0 bad and 0 other differences in each**. Cheat apart: 4 routes,
    10,452 records, 0 bad.
- **H5** (`h56.py h5 --sessions <the h56-h5 row's 26> --label play --run-id r30-h5 --no-exact --jobs 12
  --jobs-over-budget`): 112 s; **232 of 266 met, 229,662 records (223,400 match, 4,248 gave up), 0 bad, offline !=
  live 0**; lines 1,500/1,735, branches 1,060/1,641 (64.6%). Never met: the same 34.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r30-off/offline.json --offline-cheat build/speed/replay/r30-offc/offline.json --live ""
  --json build/h6three/three-r30.json`). The empty `--live` is needed because there was no live run: without it
  h6three adds its round 13 default live file and counts 4,084 Birthright records twice. (1) 2,214 / 3,696 (59.9%;
  62.9% also leaving out helper lines), round 13's sample; (2) host test alone 3,700 / 4,009 (92.3%), records or
  host 92.6%, 36 files; (3) 65 routes, 229,662 records, 0 bad; cheat 10,452, 0 bad. Equivalent candidates 237 plus
  70 unsorted, unchanged.
- **check_all** (docs/CHECK_ALL.md round 30): no row changed (nothing new proven). Fast 47 pass (2 min 1 s);
  `--only selftest,robot-routes,cheat-endgame` 3 pass (58 s; 85 tests OK; 65 verified real-play routes;
  cheat-bt-endgame the only cheat Endgame); `--only h56-h5` alone PASS (1 min 50 s).
- **Evidence**: `tools/evidence/evidence.py pack` (140.6 MB in all; new: r29-cap-cheat-cq-ch17 0.3 MB,
  r29-proof-cheat-cq-ch17 1.2 MB). `clean --yes --keep-sessions 10 --keep <every r10-r30 session folder in
  build/parallel, runs-*, r11-h5 ... r30-h5>` (build/speed/r30int/keep.txt): freed 0.00 GB (0 items). D: 97 GB free.
- **Open:** rv-ch25 (restart from c25_t33_backup with Leo out of the dead end before the third vein; plan in the
  rv-ch25 section); rv-ch26, rv-ch27, cheat-rv-endgame not started; h6three's default `--live` silently adds round
  13's file when no live run is given (pass an empty `--live`).

## Round 29 integrate (2026-11-18 night) [high unless tagged]

- **Round 29 in one line.** F-033 (owner 2026-11-18: "just maximize movement options for conquest to make sure the
  combat and animations etc work, those are what we're testing anyways"): Conquest from chapter 17 on the cheat
  track with a declared movement cheat, counted apart; counted 495 min from 01:20 (hard stop 660). **One chapter
  proven: cheat-cq-ch17** (play 01:09-01:50, 41 of 100 min, 28 movement-only pokes, nobody lost; replay checks and
  the route by 02:20; two-copy proof and capture about 40 min to 02:46, clear save
  build/harness/saves/cheat-cq-ch17-clear.zip packed with harness-cheat.json; sections 3z-cq17c). **cheat-cq-ch18 is
  NOT cleared** (first helper 02:48-03:42, 54 min, stopped at turn 2; second helper 03:43-04:24, 41 of 60 min, chain
  build/speed/cqx18/h or i at frame 108680, turn 11 player phase, 14 of 14 alive; no route key; sections 3z-cq18,
  3z-cq18b). Conquest 19 to 22 were not started (they need cheat-cq-ch18-clear). The real-play key cq-ch17 stays
  unwritten.
- **Library:** `build.py --check-fresh` **FRESH** (2026-11-18T00:03:44, round 27's build, 266 overrides). Not
  rebuilt (no reader code changed). The proof capture r29-cap-cheat-cq-ch17 ran on this same library.
- **Plan** (build/speed/r29int/plan-play.txt, plan-cheat.txt, plan-cheat2.txt). Real play (main r10-capb, r11-capn,
  r11-capo, r12-capn, r13-capn, r14-capn, r15-capn; extra as round 30 with r24-capn): **PLAN LINE 1, routes: 54
  replay offline from their records, 0 must play live (route changed). PLAN LINE 2, overrides: 266 decided by the
  records (18 by the batches' own captures on 62 routes, 1 watched and never called), 0 must play live.** Cheat with
  r29-cap-cheat-cq-ch17 added: offline.py **stopped** ("no records/<run>/records.fecap": the proof capture kept no
  records). So cheat-cq-ch17 played **live once with every override and `--store-keep`** (session
  r29-capc-cheat-cq-ch17, 04:31-04:45, 805 s, FEF_ROBOT_JOBS=4, below normal), beside the offline replays. Cheat plan
  again with r29-capc-cheat-cq-ch17: **PLAN LINE 1: 4 offline (plus cheat-cq-ch17 from its extra records), 0 live.
  PLAN LINE 2: 266 decided (32 by the batches' own captures, 12 watched and never called), 0 live.** r15-cap-capability
  (pre-fix) not used.
- **Runs (04:31:47, FEF_ROBOT_JOBS=12, below normal), all started at once:**
  - Real play (`offline.py replay ... --name r29-off --jobs 6`): 237 runs, **65 routes, 229,662 records (223,400
    match, 4,248 gave up, 2,014 incomplete), 0 bad, offline != captured verdict 0**, 143 s.
  - Cheat (`r29-offc --jobs 2`, old 4 routes): 79 runs, 10,452 records, 0 bad, 36 s.
  - Live cheat-cq-ch17 (`parallel.py runs --route cheat-cq-ch17 --mode capture --markers --only all --store-keep
    --session r29-capc-cheat-cq-ch17`): exit 0, Completed 188600 frames, memory e02b945ea095247e (equal to the
    proof), checkpoints all met, peak 780 MB, %APPDATA% unchanged; **197 functions, 11,340 records (11,167 match,
    121 gave up, 52 incomplete), 0 bad of any kind**, no writer stored anything. Same totals as the proof capture.
  - Cheat with the kept records (`r29-offc2 --jobs 4`): 82 runs, **5 cheat routes, 21,792 records (21,117 match),
    0 bad, 0 verdict differences**, 34 s. From now on cheat-cq-ch17 replays offline from r29-capc-cheat-cq-ch17.
  - Per family, real play (h6three number 3): Birthright 33 routes 113,140 records; Conquest 11, 42,388;
    Revelation 19, 72,042; options 2, 2,092; **0 bad and 0 other differences in each**. Cheat apart: 5 routes,
    21,792 records, 0 bad.
- **H5** (`h56.py h5 --sessions <the h56-h5 row's 26> --label play --run-id r29-h5 --no-exact --jobs 12
  --jobs-over-budget`, 04:36:44-04:38:47): **232 of 266 met, 229,662 records (223,400 match, 4,248 gave up), 0 bad,
  offline != live 0**; lines 1,500/1,735, branches 1,060/1,641 (64.6%). Never met: the same 34.
- **No sampled H6, no exact cover, no `--slow`** (weekly, F-028). Three-number report (`h6three.py --offline
  build/speed/replay/r29-off/offline.json --offline-cheat build/speed/replay/r29-offc2/offline.json --live ""
  --json build/h6three/three-r29.json`): (1) 2,214 / 3,696 (59.9%; 62.9% also leaving out helper lines), round 13's
  sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host 92.6%, 36 files; (3) 65 routes, 229,662
  records, 0 bad; cheat 5 routes, 21,792 records, 0 bad.
- **check_all** (docs/CHECK_ALL.md round 29): new fast row `cheat-conquest` (CHEAT_CQ_PACKS = cheat-cq-ch17 from
  cq-ch16-clear, its packed cheat clear save required with the cheat mark); 89 tests OK. Fast 48 pass (2 min 12 s);
  `--only selftest,robot-routes,cheat-routes,cheat-endgame,cheat-conquest` 5 pass (1 min 1 s); `--only h56-h5`
  alone PASS (2 min 1 s).
- **Evidence**: `tools/evidence/evidence.py pack` (141.4 MB in all; new r29-capc-cheat-cq-ch17 0.8 MB). `clean --yes
  --keep-sessions 10 --keep <every r* session folder and runs-* in build/parallel, every r*-h5>`
  (build/speed/r29int/keep.txt): freed 0.00 GB (0 items). D: 96 GB free.
- **Open:** cheat-cq-ch18 (continue from build/speed/cqx18/h or i, turn 11, ten turns left; the generals boss pair at
  (13,20) needs several hits); Conquest 19 to 22 and the Conquest Endgame; proof captures should keep records
  (`--only all --store-keep`) so integrate need not play them live; Xander's 10 misses on Kotaro not explained.

## Round 35 integrate (2026-11-18 midday): OK A opt-* routes [high unless tagged]

- **The options track exists now** (tools/harness/options_track.py, F-034). routes.json holds **24 options
  routes** (`opt-t2-*`, `opt-t3-dz0..2`, `opt-t4-newgame`, `opt-t5-*`, `opt-t7-*`), each with `"options": {...}`,
  none `verified`. The two older real-play options routes (opt-ch8-set, opt-ch8-reload) have no `"options"` key and
  stay real play.
- **Scored apart:** check_all's `robot-routes` now skips any route with `"options"` (it was already only counting
  verified ones); `options-track-routes` and `options-track-selftest` check the rules. `harness.py report` leaves
  options runs out, `parallel.py` gives them their own table, `recapture` refuses them.
- **Saves:** an options run's save is named `opts-*` and carries `harness-options.json`; `headless` refuses it as
  the start of any route without `"options"`. Tonight no options save was packed (build/harness/saves has none; the
  T6 W2 save was thrown out). The oka-* run folders under build/harness/data have no mark: pack only through
  `headless.pack_save`, never by hand.
- **Runs:** `headless.run` still refuses options routes; T1-T7 ran through wrappers below build/oka/ (t1/, t3/,
  oka_run.py) on the armed libraries build/oka/tree and build/oka/tree2, never build/harness/lib (sha 14c19839...
  unchanged). A real opt-* path in headless.py (lib below build/oka/, FE_READABLE=readable, FE_WRITERS, FE_OPTIONS
  below build/, save mark) is still to be written.

## Round 38 integrate (2026-11-18 evening): OK A rerun, opt-* routes [high unless tagged]

- **New opt-* routes this round** (all through splitcfg, own keys only, options track: named opt-*, `"options"` key,
  scored apart, never real play): `opt-t5-chain2-base` / `opt-t5-chain2-file` (bt-ch8-support: battle save at
  74190, then a chapter save at 79289 in one session; integrate removed 6 stray newline characters from their input
  strings and corrected "suspend" to "battle save" in their notes), `opt-t2-spd0-set` / `-file` (game speed 0),
  `opt-t2-dz0-base` / `-set` / `-file` (danger zone 2 to 0, from the opt-ch8-set save). options_track --check: 31
  options routes, rules OK.
- **Checkpoints** (markers.json, splitcfg): new for the 5 routes above, `opt-t5-chain2-*` and `opt-t3-dz0/1/2`;
  re-recorded for `opt-t2-dz-file`, `opt-t5-bsave-file`, `opt-t5-csave-file`, `opt-t4-newgame` (their round-35
  checkpoints expected the old danger mapping). Run.json files of round-38 runs made before that re-record show
  checkpoint mismatches and are not 0-mismatch evidence.
- **Left as they are:** `opt-t2-a-set` / `-a-file` and `opt-t2-dz-set` no longer pair under the new mapping.
  `opt-ch8-set` / `opt-ch8-reload` are round-8 real-play routes that change options on the game's own screen (no
  `"options"` key); `opt-ch8-set.zip` carries no options mark and is a real-play save.
- **How they ran:** headless.run still refuses options routes (rule 5); OK A used the wrappers in build/oka/r38c/
  (oka_run.py) with the armed libraries build/oka/tree5 / tree6, never build/harness/lib. No opts-* save was packed.
- **Timeouts under load:** with rounds 36/37 running, full Birthright routes timed out at normal timeouts; T1 used
  x4 timeouts.

## Round 40 integrate (2026-11-18 evening): OK A opt-* runs on t41 [high unless tagged]

- **No new opt-* route in routes.json.** T1 used session names `opt-t1r40-{o,a,r,h}` (build/parallel) and T2 the
  existing opt-t2-* / opt-t3-* routes, run as `oka-r41g-*` / `oka-r41h-dz0-*` with the armed library
  build/oka/t41 (never build/harness/lib). No opts-* save was packed; options saves keep their mark and are refused
  as real-play starts (`options-track-selftest`, `options-track-routes`).
- Shared library during the round: 14c19839 -> 610f791d at 18:11 (another round's rebuild from the main tree).

