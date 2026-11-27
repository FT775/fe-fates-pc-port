# Port plan: Fire Emblem Fates on PC, built on Zakuro + 3dsrecomp

Status 2026-11-24, after round 68 (the dated sections at the end say what changed; the newest is the round-68
section, written in round 69); first written
2026-11-10, after the first integration (six areas ported in parallel, each reviewed,
then joined into one green repo).

**In plain words.** The game already plays on this PC: Zakuro recompiled it once
(2026-11-09) and `PLAY.bat` starts it straight into the game. So this is not a runtime
project. It is a list of layers on top of a working emulator: make the game easy to start,
make its data editable (text, stats, pictures, maps), build a test robot that can replay
play sessions, and then rewrite the game's own rules as readable C, one small function at a
time, with options on top. The steps below carry a weight (their share of the whole job)
and a status after today. Everything comes from the Awakening port's experience; what is
different for Fates is said where it matters.

Confidence tags: **[high]** checked by a script or read in source, **[med]** good evidence,
**[low]** an estimate or guess.

## 1. The two finish lines

Two lines, never merged into one (F-006):

- **Moddable** (the near goal). A renamed name installs and uninstalls. One cell edit in
  each of the four stat tables (people, classes, items, skills) shows in the game. One
  portrait swap shows, or we write down that the picture tool failed and the date moves.
  Not all eighteen extra table types, not a byte-identical rebuild of every picture, not
  three routes, not screen extras.
- **Readable rewrite** (the long tail). The game's own code readable, function by
  function, each one proven against the original first; libraries may stay translated.

Off **both** lines, in writing (F-008): the petting scenes (Live2D runtime) and the 3D
castle renderer, with visiting, StreetPass, amiibo, movies and voices. Castle data that is
just tables may still become spreadsheets. The randomizer comes after both lines.

## 2. The steps

| # | Step | Weight | Status after 2026-11-10 | Done |
|---|---|---:|---|---:|
| 1 | Front door (PLAY.bat, saves, backups, standalone exe) | 5% | **Done.** `Fire Emblem Fates.exe` built 2026-11-10 (owner OK); PLAY.bat and the Desktop shortcut start it; the owner played it (unmodded Ryoma screen). Launcher checks fail closed (review 2026-11-11 #3) | 100% |
| 2 | Symbols (function names) | 5% | **Done.** 27,074 functions from the game's own symbol map, ARM/Thumb marked, spot-checked; the code rebuilds byte-identical with it (Thumb included) | 100% |
| 3 | Text mods | 5% | Works: all 1,328 message files round-trip; mods tool builds, installs, uninstalls; 26/26 tests. Missing: the owner's 5-minute look at a renamed name in game | ~90% |
| 4 | Stat tables | 15% | (2026-11-11) 43 layouts, 406 fields from this game's code, every GameData table typed; all table files rebuild byte-identical; edits verified in rebuilt files; the stat formula reproduces an unmodded in-game screenshot. Castle data (evening): 18 My Castle sheets in 13 files as spreadsheets (dining, accessory shop, class showcases ...), all byte-identical, new dishes and titles allowed where the code shows it is safe (F-016), a mod kind with the `ExampleCastle` demo. Missing: an in-game check of one edit per stat table and of one castle edit; many fields are low or medium confidence; the plain castle files (buildings, food, gemstones) | ~68% |
| 5 | Pictures (portraits, UI) | 10% | (2026-11-11) 13,957/13,957 BCH files and 887/887 portrait files rebuild byte-identical; textures can change size (11,688/11,688 resized and restored); better ETC1 encoder; portrait folders are a mod kind (build, install, uninstall tested; `ExampleFace` demo). Missing: one portrait swap seen in game; other pictures (menus, sprites) only as finished files | ~65% |
| 6 | Maps + new rows | 10% | (2026-11-11) Placement and terrain of every chapter as spreadsheets with a preview picture; 185 + 109 files rebuild byte-identical; moves, class/item edits, units added to existing groups, tile edits, all checked against rules read from the code; map folders are a mod kind (`ExampleMap` demo). New Item and Job rows work in mods. Missing: anything seen in game; new characters (refused: 256-person limit), new groups and reinforcement turns (chapter scripts) | ~55% |
| 7 | Screen extras (top screen) | 5% | (2026-11-13, row was stale) Landed 2026-11-12 in commit 9e16174 (docs/EXTRAS.md): three switches found in this game's code, 60 fps battles, faster battles (150%), a 16:9 picture for the 3D scenes, plus a test switch for 60 fps story scenes that changes the game's random values (leave it off); all off by default; checked headless by the robot on two Birthright chapters (game results and saves unchanged); `usa_extras.py verify` rerun 2026-11-13: 51 words in 4 extras, all check out. Since the overnight round 5 (2026-11-13) a standing `check_all` row, `extras-verify`, reruns that check every time. Missing: the owner's 5-minute look in a window | ~50% [low] |
| 8 | Test robot | 10% | (2026-11-13) Runs on Fates for real (owner OK 2026-11-11): boot.exe and the capture library built, 14 routes from the title through one Birthright campaign: Chapter 8 cleared (`bt-ch8`, 16 turns, both dragon veins) and the My Castle Smithy built and entered (`bt-castle-forge`) (docs/ROBOT.md). Grok's ROBOT_PLAN: 12 of 13 rows reached; row 7 (forge a weapon to +1) reaches the forge menu with two Iron Katanas, but the save has 0 ore and the forge needs 1 Pearl, so it is **not done** (getting ore needs a battle or Chapter 9: owner's call). Markers now read levels, exp and stat gains per unit, forge levels and castle ore; a level-up is a checkpoint (Rinkah Lv 5 -> 6 in `bt-ch8`); level-ups listed for 6 routes (`levelups.py`). Every route replays to the same memory, and the live shadow compare (capture runs A+B) ran on **all 12 Birthright routes** with 0 mismatch records (2026-11-13) at the owner's budget (parallel.py: 6 runs, below-normal, 8 GB). **Overnight round 5 (2026-11-13):** 16 routes; Chapter 9 cleared (`bt-ch9`, 19 turns, Azura sings five times, the holy-tree vein used) and **a weapon forged to +1** (`bt-ch9-ore`: the chapter-9 Dragon Vein point built a Lottery Shop, its free draw gave 1 Coral, a second Iron Naginata bought, Smithy: Iron Naginata +1 for Subaki, read from memory and kept in the save `bt-castle-ore`), so ROBOT_PLAN row 7 is reached, though not with the katanas and Pearl it first named (no ore building after chapter 9); both routes replay to the same memory twice. The live shadow compare ran on **all 14 Birthright routes** with all 94 overrides: 84 met, 15,442 records, 0 mismatch records of any kind (12 runs at once, the owner's night budget). **Overnight round 6 (2026-11-14):** a **cheat track** (owner OK 2026-11-12 night, F-019, docs/CHEATS.md): the robot may poke declared values into its own test game between headless stages; 4 `cheat-*` routes (a Pearl poked so Hana's Iron Katana is forged to +1, Lethality made to fire, a made-up family record so the child-unit readers run, the katana save reloaded), each deterministic; a cheat save can never start a real-play route (name, mark or same save files; refused in headless.run, parallel.py and pack_save). Live compare on **all 14 Birthright routes and all 4 cheat routes** with all 110 overrides, scored apart: real play 92 met, 16,952 records; cheat track 62 met, 3,597 records; 0 mismatch records of any kind on either. **Daytime round 7 (2026-11-13):** an options-screen route (`bt-ch8-options`: every options line looked at, left without a change, the 19 saved option bytes identical at 11 checkpoints; the Units list's Battle page) and **H5/H6 on kept game records**: real play 100 of 110 met, branches 60.1% of the overrides' own code (47.3% with callees), offline = live on all 17,818 records; H6 865/1,822 planted bugs caught (**47.5%, gate 90% not met**), cheat track apart 41.6%. Live compare on **all 15 Birthright routes and all 4 cheat routes**: real play 100 met, 17,818 records; cheat 62 met, 3,597; 0 mismatch records of any kind. Missing: H6 at its gate, a writer H6 (HOOK_LIST, a `writer` target kind), the writer-callee list, B-c and B-e of ROBOT_NEXT2, a route that changes options in the game's screen, 6 overrides never met on either track. **Night round 8 (2026-11-14): all three routes (owner, F-022).** Conquest and Revelation branch from the Birthright chapter-5 save (made before the route choice) and both cleared chapter 6 (`cq-ch6`, `rv-ch6`); Birthright cleared chapters 10 and 11 (`bt-ch10`, `bt-ch11`); the options changed on the game's own screen and reloaded from a save (`opt-ch8-set`, `opt-ch8-reload`). Live compare on **all 21 real-play routes and all 4 cheat routes** with all 129 overrides: real play 117 met, 31,334 records; cheat 77 met, 4,807; 0 mismatch records of any kind; the writer counters read 0 stores in every run. H6 49.6% caught (gate 90%: not met). Missing: chapter 7 on Conquest and Revelation, Birthright 12-14, a child unit, a chapter-id marker, H6 at its gate. **Round 9 (2026-11-14):** Birthright 12, Conquest 8, Revelation 9 on the speed tools; 26 routes live, 0 bad (~79%). **Round 10 (2026-11-15, fresh helper per chapter):** Birthright 13-17, Revelation 10-14, Conquest 9 (proof and checkpoints by integrate); 38 verified real-play routes; live compare on all 38 with all 203 overrides after one fix: 179 met, 106,426 records, 0 bad of any kind; cheat track 8,395 records, 0 bad; Birthright chapters take about 54 minutes each (round 9: 74). **Round 11 (2026-11-15/16, F-025):** Birthright 18-23, Conquest 10-12, Revelation 15-17, all proven with two original copies (the proof its own step from F-025); Conquest and Revelation then paused (cq-ch13, rv-ch18 left unverified); 50 verified real-play routes; compare: 38 older routes offline (106,426 records), 12 new routes live with every override and the 38 older live with the 31 new overrides: 166,411 records, 0 bad of any kind; cheat 8,938 records, 0 bad; fastlook serve rollback fixed. **Round 12 (2026-11-16/17, F-025):** Birthright 24 only, proven with two original copies as its own step; 51 verified real-play routes; compare: 50 older routes offline from their records (168,591 records, the class-change readers by their batch's own capture), bt-ch24 live with every override (3,908 records): 172,499 records, 0 bad of any kind; cheat 9,039 records, 0 bad. **Round 13 (2026-11-16):** Birthright 25; 52 routes, 176,698 records, 0 bad. **Round 14 (2026-11-16):** Birthright 26 only (30 min play, 8 min proof); 53 verified real-play routes; compare: 52 older routes offline (177,726 records, the four new readers by their batches' own captures), bt-ch26 live with every override (3,303 records): 181,029 records, 0 bad of any kind; cheat 9,212 records, 0 bad. **Round 15 (2026-11-16):** Birthright 27 (King Garon) only (58 min play, 28 min proof); the game makes no save after it (straight to the Endgame Preparations), so no clear save is packed; 54 verified real-play routes; compare: 53 older routes offline (181,444 records), bt-ch27 live with every override (3,872 records): 185,316 records, 0 bad of any kind; cheat 9,512 records, 0 bad. **Round 16 (2026-11-16):** Birthright Endgame started from the bt-ch27 chain state (F-029) and was **not won** in 63 minutes (stopped at turn 5, 16 of 16 alive, chain kept); no new route; compare: all 54 routes offline (185,561 records), 0 bad of any kind; cheat 9,561 records, 0 bad. **Round 19 (2026-11-17, F-030):** Birthright Endgame finished **on the cheat track** (`cheat-bt-endgame`: one declared poke at turn 8, Garon's HP 78 -> 1; Ryoma's first hit won; the game ran through the ending and credits to the title screen, no hang, no save prompt); two-copy proof passed; its capture with every override 6,328 records, 0 bad; verified. Per the owner this counts as Birthright played to the end; the real-play key bt-endgame stays unwritten. **Round 20 (2026-11-17, F-031):** Conquest and Revelation resumed, real play: cq-ch13, cq-ch14, cq-ch15, rv-ch18, rv-ch19, rv-ch20 proven with two equal copies and packed (60 verified real-play routes); compare: 54 older routes offline (185,812 records, 0 bad), the six new routes live with every override (23,484 records, 2 strike_power call-list records on cq-ch13, open); cheat 16,231 records, 0 bad. Missing: Conquest 16 on, Revelation 21 on and both Endgames, a child unit, H6 at its gate | ~92% [low] |
| 9 | Readable rewrite | 20% | (2026-11-13) 79 overrides: the pilot's 12 (AI, flags, forces), 9 Attack/Guard Stance readers, 7 weapon triangle and rank readers, 7 dragon vein readers, 21 battle-formula readers (the five stat getters, attack, hit, avoid, critical, critical avoid, the follow-up speeds, the forecast's shown hit and number of strikes) and 23 growth/experience readers (growth rates, stat caps, the experience tables, levels and amounts, level limits; docs/GROWTH.md, which also settles that `Unit::LevelUp` rolls the stats), plus 16 helpers (1 forces, 4 stance, 3 triangle, 1 vein, 2 formula, 5 growth: the level-up's generator, its dice plan and what it would store) that return what the game would store; every batch matches the game's own ARM code on made-up cases (two seeds each, `check_all` rows `stance-diff`, `triangle-diff`, `vein-diff` and their `-long` rows; the formula test also compares unmapped reads; 18/18 triangle, 35/35 vein, 30/30 formula and 36/36 growth planted bugs caught; the growth test compares the whole list of guest calls in order). The formulas are written up from the code (docs/FORMULAS.md) and reproduce the owner's prologue Ryoma screen exactly. Tier-2 verify: see the 2026-11-12 status lines. In real play (the robot's live shadow compare on 10 Birthright routes, 2026-11-12) 49 of the 56 overrides were met: the 34 met older ones with 0 mismatches, 13 of the 15 met formula ones with 0 mismatches, and `unit_hit` / `unit_attack` with 214 MISMATCH records (same results and memory, a different list of calls). Fixed the same day (section "Status update 2026-11-12 (formula fix)"): rerun on bt-ch2, bt-ch7, bt-ch8-pair and bt-castle-shop, 47 overrides met, 2,966 records, **0 MISMATCH of any kind** (F-018 goal met). **2026-11-13: live compare on all 12 Birthright routes from a fresh library with all 79 overrides: 67 met, 10,334 records, 0 MISMATCH of any kind; 18 of the 23 growth overrides met (`unit_grow` 74 records, `unit_exp_damage` 66, `unit_stat_limit` 345), the 5 not met are the dance experience pair and the three child/family readers.** Statuses stay `unverified`; no writers (F-017). **2026-11-13 night (skills batch, docs/SKILLS.md): +15 skill readers ("does this unit have skill X", class skills, the skill pool, Nohrian Trust's shared skills, the Lethality immunity, effect names) and 2 helpers (the activation chance; which attack skill fires and how many dice it takes): 94 overrides, 18 helpers; host diff 0 mismatches, 32/32 planted bugs; tier 2 0 MISMATCH over all 94; not yet in a live compare** **2026-11-13 overnight round 5: live compare on all 14 Birthright routes from a fresh library with all 94 overrides: 84 met, 15,442 records, 0 MISMATCH of any kind; 11 of the 15 skill readers met (`unit_has_skill` 418 records on every route, `skill_record` 334, `unit_personal_skill` 322, `battle_side_has_skill` 225), and 6 of the 12 never met before (the dance-experience pair, the four slot forms) met on the Chapter 9 routes. Not met: 4 skill readers, the 2 terrain forms, the 3 family readers, one Revelation-only script command** **2026-11-13 (menus batch, docs/MENUS.md): +16 readers of the options screen's stored settings and the decisions that read them (danger-zone, HP-bar, battle-animation, game-speed, enemy-phase, camera and music lines; the battle-picture rule IsDetailBattle, the support-picture rule, fast movement, the danger panel's IsHide) and 6 helpers (what the options record in a save holds, the battle-picture decision, the map HP-bar decision, the danger zone's unit choice, its OR and its tile test): 110 overrides, 24 helpers; host diff 0 mismatches, 41/41 planted bugs; tier 2 0 MISMATCH over all 110** **2026-11-14 overnight round 6: live compare on all 14 Birthright routes from a fresh library with all 110 overrides: 92 met, 16,952 records, 0 MISMATCH of any kind; 8 of the 16 menu readers met (`danger_panel_is_hide` 282 records, `config_info_capability` 251 on every route, the battle-picture rule 133); `unit_equipped_skill_count`, `family_grow`, `family_limit` and `unit_lethality_immune` met only on cheat routes (F-019; the last one gave up). Never met: the 8 option-item readers (no route opens the options screen), 2 skill, 2 terrain, 1 family, 1 Revelation-only** **2026-11-13 daytime round 7: the 8 option-item readers met in real play (`bt-ch8-options`, all match): 100 of 110 clean in real play, 17,818 records, 0 MISMATCH of any kind. The writer gate and undo log (F-021) and the first writer (`config_write_options`, the options block) are written and compiled into the library **OFF**; host diff 0 mismatches in 600 and 3,000 cases, 25/25 planted bugs; gate test 244/244, 17/17. Never met: 2 skill, 2 terrain, 1 family, 1 Revelation-only** **2026-11-14 night round 8: +19 status-sheet readers (defence, resistance, maximum HP and the HP window, move, class categories, equipped and held item, item count, shown and low level, shortest range, may-not-attack, unique, special battle, invisible, capturable; docs/SHEET.md): 129 overrides; host diff 0 mismatches, 40/40 planted bugs; live compare on all 21 real-play routes: 117 of 129 met, 31,334 records, 0 MISMATCH of any kind; 17 of the 19 new readers met. Never met: 2 skill, 2 terrain, 1 family, 1 Revelation-only, `unit_can_be_captured`, `unit_equipped_item_mutable`** **2026-11-15 round 10: +74 readers in three batches, items (25, docs/ITEM.md), movement and terrain (24, docs/MOVE.md), supports and family (25, docs/SUPPORT.md): 203 overrides; host diff 0 mismatches, 46/46, 47/47, 50/50 planted bugs; live compare on all 38 real-play routes: first try 866 call-list records in `cursor_terrain` (an inlined tail branch; fixed, docs/MOVE.md 9), then 179 of 203 met, 106,426 records, 0 MISMATCH of any kind; 58 of the 74 new readers met** **2026-11-16 round 11: +31 readers in two batches, AI permission (18, docs/AI.md) and battle numbers 3 (13, docs/BATTLE2.md), the `unit_item_stat_bonus` tier-2 note explained (shadow_count.py); the AI attack-score batch parked (F-025): 234 overrides; host diff 0 mismatches, 44/44 and 39/39 planted bugs; compare on all 50 real-play routes: 205 of 234 met, 166,411 records, 0 MISMATCH of any kind; 26 of the 31 new readers met; H6 survivors on the 4 weakest files: 13 more caught by host tests, 80 equivalent candidates for a person** **2026-11-17 round 12: +6 readers in two batches, class change and seals (4, docs/CLASS_CHANGE.md) and weapon rank (2, docs/WEAPON_RANK.md): 240 overrides; host diff 0 mismatches, 28/28 and 23/23 planted bugs; each batch captured once with the final library; compare on all 51 real-play routes: 208 of 240 met, 172,499 records, 0 MISMATCH of any kind; 3 of the 6 new readers met (class_change_type and both weapon-rank readers never called); sampled H6 53.4%** **2026-11-18 round 13: +1 reader (shop_buy_price) and 2 host-only helpers: 241 overrides, 209 met** **2026-11-19 round 14: +4 readers in two batches, the equip check (1, docs/EQUIP_USE.md) and the staff readers (3, docs/STAFF_RANGE.md): 245 overrides; host diff 0 mismatches, 39/39 and 36/36 planted bugs; each batch captured once, capped; compare on all 53 real-play routes: 213 of 245 met, 181,029 records, 0 MISMATCH of any kind; all 4 new readers met; the writer gate is now F-026's three numbers (owner 2026-11-16)** **2026-11-20 round 15: +3 capability readers (docs/CAPABILITY.md) and guest_call6 (two stack words): 248 overrides; host diff 0 mismatches, 35/35 planted bugs; the first capture found 7 call-list records (a tail branch), fixed and recaptured clean; compare on all 54 real-play routes: 215 of 248 met, 185,316 records, 0 MISMATCH of any kind; 2 of the 3 new readers met** **2026-11-21 round 16: +3 shop buy-list readers (docs/SHOP_GREY.md): 251 overrides; host diff 0 mismatches, 37/37 planted bugs; captured once on 6 shop routes, 0 bad; compare on all 54 real-play routes offline: 217 of 251 met, 185,561 records, 0 MISMATCH of any kind; 2 of the 3 new readers met (shop_buy_max never called)** | ~26% [low] |
| 10 | Options | 10% | Grok's options page (`tools/zakuro-options/`): built and 6/6 tests pass 2026-11-10; stores values only, no game hooks, not in the shipped exe yet; OPTIONS_V1 (19 switches) and stance/revive notes are design only. (2026-11-13, menus batch) `danger_zone`, `hp_bars`, `animation_skip`, `anim_speed` are switches of the game's own options screen (one block, GameConfigData, written into every game save); their readers and decision points are readable and named (docs/MENUS.md); nothing hooked. (2026-11-14) 8 of the 16 menu readers clean in real play (the battle-picture rule, fast movement, the danger panel); the option items themselves are never met (no route opens the options screen). (2026-11-13 daytime round 7) all 16 menu readers clean where met: the 8 option items met on the new options-screen route (one value each: this save's); the first options writer exists, gated and OFF (F-021); docs/OPTIONS_WIRING.md reads every caller of the options block's Reset/Deserialize/Serialize and designs the load hook W1 and the save guard W2 (suspend saves included) plus Zakuro patch 0002; design and patch files only, nothing built or hooked (owner OKs A-C listed in REPORT_2026-11-14 round 7). (2026-11-14 night round 8) the robot changes the options on the game's own screen and reloads them from a save in real play (`opt-ch8-set`, `opt-ch8-reload`): each option reader sees 2-4 values; a `writer` kind in the registry and the harness (never stubbed, never probed); every capture run counts the writer gate (0 stores in all 25 runs); still nothing built or hooked (owner OKs A and B open) | ~16% [low] |
| 11 | Polish | 5% | Not started | 0% |

**Rough total: about 55.6% of the whole job** (2026-11-25 round 20: 55.6% by the weights above, the robot ~90% -> ~92% (Conquest 13-15 and Revelation 18-20 proven, real play, F-031) [low]; the readable rewrite stays ~26%; steps 3, 4, 5 and 7 stay until the owner looks; 2026-11-24 round 19: 55.4% by the weights above, the robot ~88% -> ~90% (Birthright Endgame finished on the cheat track, F-030; counts as Birthright played to the end) [low]; the readable rewrite stays ~26%; steps 3, 4, 5 and 7 stay until the owner looks; 2026-11-21 round 16: 55.2%, unchanged: Endgame was not won, so the robot stays ~88% [low]; the readable rewrite stays ~26% (3 shop readers, 217 of 251 clean in real play); steps 3, 4 and 5 stay until the owner looks; 2026-11-20 round 15: 55.2% by the weights above, the robot ~87% -> ~88% (Birthright 27, 54 routes clean) [low]; the readable rewrite stays ~26% (3 readers); step 4 stays ~68% until the owner's look; 2026-11-19 round 14: 55.1% by the weights above, the robot ~86% -> ~87% (Birthright 26, 53 routes clean) and the readable rewrite ~25% -> ~26% (4 readers, 213 of 245 clean in real play); both raises [low]; 2026-11-18 round 13: 54.8%; 2026-11-17 round 12: 54.6% by the weights above, the robot ~84% -> ~85% (Birthright 24, 51 routes clean) and the readable rewrite ~24% -> ~25% (6 readers, 208 of 240 clean in real play); both raises [low]; 2026-11-16 round 11: 54.3% by the weights above, the robot ~82% -> ~84% (twelve chapters, 50 routes clean, the proof its own step) and the readable rewrite ~22% -> ~24% (31 readers, 205 of 234 clean in real play); both raises [low]; 2026-11-15 round 10: 53.7% 53.7% by the weights above, the robot ~79% -> ~82% (ten chapters, Conquest 9 finished, 38 routes clean) and the readable rewrite ~18% -> ~22% (74 readers, 179 of 203 clean in real play); both raises [low]; 2026-11-14 round 9: 52.6%, the robot ~77% -> ~79% (this line was not updated then); 2026-11-14 night round 8: 52.1% by the weights above, the robot ~74% -> ~77% (all three routes, chapters 10-11 and both chapter 6s, the options-changing route), the readable rewrite ~17% -> ~18% (19 status-sheet readers, 117 of 129 clean in real play) and options ~15% -> ~16% (options changed and reloaded in real play, the writer kind and counters); all three raises [low]; 2026-11-13 daytime round 7: 51.5%: 51.5% by the weights above, the robot ~72% -> ~74% (the options route, H5/H6 run), the readable rewrite ~16% -> ~17% (100 of 110 clean in real play, the writer gate) and options ~13% -> ~15% (option items clean, first writer OFF, wiring design); all three raises [low]; 2026-11-14 overnight round 6: 50.9% by the weights above, the robot ~70% -> ~72% (the cheat track, 18 routes in the live compare) and the readable rewrite ~15% -> ~16% (the menu readers clean in real play); both raises [low]; 2026-11-13 menus batch: 50.5%, the readable rewrite ~14% -> ~15% and options ~12% -> ~13%; 2026-11-13 overnight round 5: 50.2% by the weights above, the robot ~65% -> ~70% (Chapter 9 cleared, a weapon forged to +1, the live compare on all 14 Birthright routes) and the readable rewrite ~13% -> ~14% (the skill readers clean in real play); both raises [low]; 2026-11-13 night, skills batch: 49.5%, the readable rewrite ~12% -> ~13%; 2026-11-13: 49.3% by the weights above: the robot ~60% -> ~65%, the readable rewrite ~10% -> ~12%, and the screen extras row corrected from 0% to ~50% because it had not been updated when the extras landed; without that correction 46.8%. **Seen in game by the owner: about 5%** of the job, the front door only: the owner played the unmodded game through PLAY.bat; no mod, robot result, readable function or extra has been seen by the owner in a window yet. 2026-11-12: 45.9%, the test robot row going from ~15% to ~60%; 2026-11-11 night: 41.0%; late: 40.8%; evening: 40.4%; 39.6% in the
morning; 30% on 2026-11-10) [low: the weights are estimates, and "done" counts only what a script checks].

## 3. Dates (the working plan with Grok)

| What | When | Condition |
|---|---|---|
| Text mods + the four stat tables (moddable finish line, data part) | late November 2026 | layouts come from this game's code (they do) [med] |
| Portrait swap | early December 2026 | if the picture tool cooperates; if it cannot reuse the original picture blocks, we say so in its first week and faces move to mid-December |
| Thin robot (boot, refuse an update, one short capture, original vs original clean) | the week the graphics card is free | not a chapter clear |
| Feature list on one campaign | early to mid December 2026 | only with one campaign, not three |
| Rewrite, options, polish | February to March 2027 | only with the petting scenes and the castle renderer excluded |

## 4. Agreements with Grok (docs/collab/GROK_INBOX.md)

- **Two tracks**: moddable work (no graphics card) goes ahead now; Fates headless runs
  wait while the Awakening port holds the card (F-011).
- **One campaign for play checks**: Birthright, Normal, Casual. Conquest is one chapter
  later, the third route a boot and a chapter-1 open. Static round-trip and edit tests
  still cover the data files of all three routes (F-007).
- **Route letters to be confirmed in code**: A/B/C = Birthright/Conquest/Revelation is from
  file names; no option key or test names a route before code confirms it (F-009).
- **Petting scenes and the castle renderer are off both finish lines** (F-008).
- **Options page**: Grok's patch in `tools/zakuro-options/` waits for a build OK; PLAY
  does not set `FE_OPTIONS` yet, so the page writes nothing (F-010).
- **Writers wait**: no rewritten rule that changes the game until a replay can catch it;
  shadow mode never runs a writer; a green report enables nothing. First in the rewrite,
  after the thin robot can replay one battle: the Attack and Guard Stance appliers, then
  the weapon-triangle check, then one dragon-vein writer.
- **Owner minutes**: zero today. The next ask is one 5-minute look at a renamed name, after
  text mods work; not a playthrough.

## 5. What needs the owner

| Ask | Unblocks | Size |
|---|---|---|
| OK to build (`engine.py build` / `port`, cargo) | standalone exe (step 1), 3dsrecomp verify (step 9), test robot (step 8), options page (step 10) | 30-60 min of the PC, no owner time [low] |
| A 5-minute look at a renamed name in game | step 3 done | 5 min |
| A look at one stat edit per table, one portrait swap | moddable finish line | 10-15 min, later |

## Status update 2026-11-10 (evening)

- Owner OK'd both builds. `python tools/engine/engine.py port` built `play/game/Fire Emblem Fates.exe`
  (143.6 MB; recompile 148 s, cargo 104 s, 4 min 19 s total; 4.6 GiB in build/port/fef). PLAY.bat now
  picks it (dry run checked). Not yet started in game by the owner.
- Grok's options page (tools/zakuro-options/patches/0001) compiles; `cargo test -p zakuro fe_options`:
  6/6 pass. It only stores values; no game hooks yet, and it is not in the shipped exe's patch series.

## Status update 2026-11-11 (maps and pictures joined to the mods tool)

- **Step 6, maps (~55%).** `tools/maps/` turns every chapter's unit placement and terrain into
  spreadsheets and a preview picture, and back; all 185 placement and 109 terrain files come back
  byte-identical. The rules for safe edits come from the game's code (docs/MAPS.md). A mod can now
  hold `maps/<MAP>/` folders: `python tools/mods/mods.py example-map` moves one enemy of Birthright
  Chapter 7 two tiles; it builds, installs into a scratch Zakuro folder and uninstalls back exactly
  (tests). Nothing has been seen in the game.
- **Step 5, pictures (~65%).** `tools/assets/bchwrite.py` lets a texture change size; the portrait tool
  accepts other sizes only with a switch, because the 3DS draws faces at their pixel size. A mod can
  now hold `faces/<character>/` PNG folders: `example-face` tints Ryoma's normal standing portrait blue
  by code; built, read back, installed and uninstalled in tests. No portrait swap seen in game yet.
- **Step 4, tables (~65%).** Unchanged today apart from the map layout fix (TerrainGrid's playable-area
  columns renamed from the code). Still waiting for the owner's look at one edit per stat table.
- **Checks.** New `check_all` rows: `maps-test`, `maps-roundtrip`, `assets-bchwrite`, and the slow
  `assets-bchwrite-all`; `text-mods` now also covers map and portrait mods.
- **Owner minutes asked next** (each about 5 minutes, docs/MODDING.md sections 2, 6, 6a, 6b): the
  renamed name, the new item, the moved enemy (needs a save at the start of Birthright Chapter 7), the
  blue Ryoma.

## Status update 2026-11-11 (evening: castle data and stances joined)

- **Step 4, tables (~65% -> ~68%).** `tools/castle/` turns My Castle data into spreadsheets: 13
  files, 18 sheets (dining titles and dishes, accessory shop, class showcases, castle people,
  private-quarters unlocks, fortune pairs, butler, positions ...). Every file rebuilds
  byte-identical; an edit changes exactly the bytes of its cell; the 274 sheet-shaped files of
  the whole game round-trip except one the game itself ships malformed. New rows only for dishes
  and cooking titles (F-016). A mod can now hold `castle/<File>/` folders:
  `python tools/mods/mods.py example-castle` makes one dish give 3 more Strength; it builds,
  installs into a scratch Zakuro folder and uninstalls back exactly (tests). Nothing has been seen
  in the game. The rise is small on purpose: the moddable finish line asks for the four stat
  tables seen in game, and castle data is extra.
- **Step 9, readable rewrite (~3% -> ~5%).** The Attack and Guard Stance rules are written as 9
  readable read-only overrides and 5 helpers (docs/STANCES.md). A small ARM interpreter runs the
  game's own code beside the readable C: 0 mismatches in 5,600 and 21,000 cases, and 13 planted
  bugs were all caught. Still unverified in the engine; writers stay off (F-017).
- **Checks.** New `check_all` rows: `castle-test`, `stance-armmini`, `stance-diff`, and the slow
  `castle-all` and `stance-diff-long`; `text-mods` now also covers castle mods.
- **Owner minutes asked next:** the four 5-minute looks of the morning, plus the better dish
  (docs/MODDING.md section 6c; needs a save in My Castle with a cooking turn unused).

## Status update 2026-11-11 (afternoon): tier-2 verify on Fates

- Owner OK'd `engine.py build 3dsrecomp-verify` (8 s). `tools/readable/verify.py` on all 21
  overrides (stances + the 12-function pilot), whole-game library build 305 s, total 5 min 39 s:
  **0 mismatches**. 2 CLEAN, 15 ABI-ONLY (same return value; only scratch registers/flags the
  calling convention lets a function clobber differ), 2 GAVE-UP (the one-time cache was cold, so
  only the fallback ran: `unit_can_pair_with`, `unit_guard_stance_bonus`), 2 UNSAMPLED (the
  original runs past verify's instruction limit in its made-up state: the two stance-bonus totals).
- A smoke test, not a proof: one made-up state per function. The four not-compared functions stay
  covered by the host ARM comparison (stance-diff, 26,600 cases). The `readable-verify` row of
  `check_all --slow` now runs instead of skipping.

## Status update 2026-11-11 (late): weapon triangle batch

- **Step 9, readable rewrite (~5% -> ~7%).** Grok's batch 1 (docs/tracks/REWRITE_ORDER.md): the weapon
  triangle and weapon ranks, docs/TRIANGLE.md. 7 read-only overrides (`ItemSubKind::Get`,
  `WeaponBonus::Get`, `WeaponLevel::Get`, `WeaponInteract::Get`, `WeaponLevel::GetLevel`,
  `Unit::GetWeaponExpLimit`, `Unit::GetWeaponExp`) and 6 helpers (the rank bonus of
  `Unit::GetAttack/GetHit`, the cell and reversal of `BattleInfo::CalculateDetail`, the triangle part of
  `Side::CalculateDetailHit/Attack`). Host ARM comparison: 5,200 and 19,500 cases, 0 mismatches;
  18 of 18 planted bugs caught. Writers stay off (F-017).
- **Tier 2** (`verify.py --rom ...`, library build 317 s): all 28 overrides, **0 mismatches**: 4 CLEAN,
  18 ABI-ONLY, 4 GAVE-UP, 2 UNSAMPLED. Triangle: CLEAN `weapon_level_record`, `weapon_interact_record`;
  ABI-ONLY `item_subkind_record`, `weapon_bonus_record`, `weapon_rank_of_exp`; GAVE-UP (cold caches)
  `unit_weapon_exp_limit`, `unit_weapon_exp`; none UNSAMPLED. Statuses not updated.
- **Rules check** (docs/tracks/rules/RULES.md): the pairs and the rank numbers are confirmed; "the bonus
  follows the attacker's rank" is refuted as worded (it follows the rank of the unit with the advantage,
  also for the other side's penalty); the reversing weapon is confirmed and also doubles the effect; new
  rule from the code: a unit at a triangle disadvantage loses its own weapon-rank bonus in that fight.
- **Checks.** New `check_all` rows: `triangle-diff` (with the planted bugs) and the slow `triangle-diff-long`.

## Status update 2026-11-11 (night): dragon vein batch

- **Step 9, readable rewrite (~7% -> ~8%).** Grok's batch 2 (docs/tracks/REWRITE_ORDER.md), the agreed
  scope: one vein effect plus the read-only parts the `vein_highlight` option needs (docs/VEINS.md).
  7 read-only overrides (`map::trick::Data::IsAccess`, `AIThink::GetTrickFromAccess`, the script's
  `TrickTst` and `UnitCanDragonVein`, `Person::IsDownload`, `Unit::CanDragonVein`,
  `TransformTerrain::BuildAttribute`) and 1 helper (the ground-change effect: the tiles
  `trick::Data::SetDeploy` marks). Host ARM comparison: 3,200 and 12,000 cases, 0 mismatches, out-of-range
  inputs included; 35 of 35 planted bugs caught. Writers stay off (F-017).
- **Tier 2** (`verify.py --rom ...`, library build 344 s): all 35 overrides, **0 mismatches**: 4 CLEAN,
  22 ABI-ONLY, 7 GAVE-UP, 2 UNSAMPLED. Veins: ABI-ONLY `trick_is_access`, `trick_at_access`,
  `script_trick_test`, `script_unit_can_dragon_vein`; GAVE-UP (cold caches) `unit_can_dragon_vein`,
  `person_is_download`, `vein_command_attribute`. A first run had 2 MISMATCH (the readable code read more
  unmapped memory than the game); fixed and rerun. Statuses not updated.
- **Rules check** (docs/tracks/rules/RULES.md): one command, same for all routes, the effect is the chapter's
  own (script event on the vein tile), who may use it is data (a personal flag bit) - confirmed; "works once"
  is done by the script marking the vein done, not by the command; the skirmish line is consistent with a
  game-mode bit that creates every vein already done (mode not traced); no per-turn use flag exists (refuted);
  new rule: a unit with state bit 28 must also be a download person.
- **Checks.** New `check_all` rows: `vein-diff` (with the planted bugs) and the slow `vein-diff-long`.

## Status update 2026-11-12: battle formula batch

- **Step 9, readable rewrite (~8% -> ~10%).** Grok's batch 3 (docs/tracks/REWRITE_ORDER.md: damage,
  hit, crit). The formula functions are now named (Grok's search could not): `Unit::GetAttack`,
  `GetHit`, `GetAvoid`, `GetCritical`, `GetSecure` (critical avoid), `GetContinuous` /
  `GetUnderContinuous` (follow-up speeds), the stat getters `GetStrImpl` .. `GetLuckImpl`, and the
  fight's `map::BattleInfo::Side::CalculateDetail*`, `CalculateEfficacy`, `GetSimpleHit`,
  `GetSimplePower`, `GetSimpleTimes`; call graph and every formula in plain words in docs/FORMULAS.md.
  21 read-only overrides (the five stat getters, `GetItemIndexEquipped`, the battle numbers with their
  slot forms, `GetSimpleHit`, `GetSimpleTimes`) and 2 helpers (the critical / critical avoid / speed
  part of `Side::CalculateDetail`, the shown critical of `CalculateSimple`). Writers stay off (F-017).
- **Cross-check.** The formulas reproduce the owner's prologue Ryoma screen exactly (Atk 29, Crit 20,
  Hit 110, Avo 53, Raijinto) from the decoded tables. Proposed lines for the [gap] in
  docs/tracks/rules/RULES.md: docs/FORMULAS.md section 8 (Grok's file not edited). Doubling: attack
  speed >= the other's defense speed + 5; effective = might x 3; critical factor 300 %.
- **Host ARM comparison:** 6,900 and 23,000 cases, 0 mismatches, out-of-range inputs and unmapped
  units included; it now also compares unmapped reads and requires a give-up before any such read
  (tier 2's criterion); 30 of 30 planted bugs caught.
- **Tier 2** (`verify.py --rom ...`, library build 360 s): all 56 overrides, **0 mismatches**: 4 CLEAN,
  23 ABI-ONLY, 26 GAVE-UP, 3 UNSAMPLED. Formula overrides: ABI-ONLY `unit_equipped_index`; GAVE-UP 19
  (verify's caches are cold: only the clean give-up is proven); UNSAMPLED `unit_avoid` (its code is held
  inside GetAvoid(int)). Two earlier runs had 7 MISMATCH (unmapped reads before a give-up, and three read
  patterns that differed from the game's); fixed, and the host test now catches that class. The
  3dsrecomp folders under %APPDATA% / %LOCALAPPDATA% were snapshotted before and after: unchanged
  (840 files). Statuses not updated.
- **Checks.** Proposed `check_all` rows (the integrate stage owns check_all): `formula-diff` (with
  `--plant`) and the slow `formula-diff-long` (`-n 1000 --seed 7`).

## Status update 2026-11-12 (join): robot round 3 and the formula batch, checked together

**In plain words.** Two pieces ran side by side and were then joined. The test robot now plays one
Birthright campaign on its own from the title to Chapter 8 (shop, Chapter 7 cleared, a support
conversation), and the battle formulas are readable code that matches the game on made-up cases. The
join replayed every Birthright piece with all 56 readable functions watched: the game is unchanged and
deterministic, and 47 of the 49 functions met agree with the game every time. The two that do not
(hit and attack) give the same numbers but call their helpers in another order, so the "0 mismatches"
goal is **not met yet**; it goes back to the formula track (met later the same day: section
"Status update 2026-11-12 (formula fix)" below). The plan total moves from about 41% to
about 46%, almost all of it from the robot row.

- **Step 8, test robot (~15% -> ~60%)** [low for the percentage, high for the facts]. Round 3
  (docs/ROBOT.md): `bt-castle-shop` (row 5 shop: Rod Shop built, a Vulnerary bought, gold 5000 -> 4700),
  `bt-ch7` (Chapter 7 cleared, 24 turns), `bt-ch8-support` (row 9: Corrin and Felicia's C support),
  `bt-ch8-pair` (Corrin made the support of a pair). Row 7 (forge) is "not here" up to the chapter-7
  castle. 12 of the 13 ROBOT_PLAN rows are reached. headless.py decodes a savestate in 0.77 s instead of
  6.0 s; parallel.py no longer overrides a route's own start save; build.py runs no longer share a
  scratch folder. The percentage counts the plan rows, determinism and the live compare as done, and
  H5/H6 on game records, the writer-callee list (needs a Fates HOOK_LIST.md), the forge and one never-met
  override as not done.
- **Step 9, readable rewrite (~10%, unchanged by the join).** The formula batch (status line above).
  Not raised further: two of its functions differ in real play, and every status is still `unverified`.
- **Capture library rebuilt once** for the join: `parallel.py build` (below-normal, one build),
  284 s, 56 overrides, `build.py --check-fresh` FRESH (2026-11-12 02:04). replay.exe rebuilt with the
  56 overrides (`harness.py build`).
- **Determinism, all 10 Birthright routes** (`parallel.py runs --mode original --copies 2`, 20 runs,
  wall 748 s, at most 6 at once, below-normal, peak 363 MB per run): every pair has the same memory hash
  and instruction count, equal to the robot's committed runs (e.g. `bt-prologue` a3e4ec17 /
  213,346,885,008, `bt-ch2` 059736d3 / 89,801,965,440, `bt-ch7` 4376a256 / 425,707,920,000).
- **Live shadow compare, all 10 Birthright routes** (`parallel.py runs --mode capture`, live A+B,
  10 runs, wall 405 s): every capture run ends with the same memory hash and instruction count as the
  original runs (capture does not disturb the game). 7,332 records over 49 functions: 6,911 match,
  124 gave up (the original ran), 83 incomplete, **214 MISMATCH, all `mismatch_calls`, all in two
  formula overrides**: `unit_hit` 0x00532DC4 (100 of 143 records) and `unit_attack` 0x00534188 (114 of
  143), on every route with a battle (not `bt-castle-shop`, `bt-ch8-support`). r0 and memory agree in
  every one of them. Offline replay of the 8 kept records of `bt-ch2`: original vs original clean,
  readable match 8/8, but it cannot see the calls into other overrides (10 unobservable notes per
  record), so it does not clear them (F-018). This is the same finding the robot reported on `bt-ch7`
  and `bt-ch8-pair` with the 01:02 library; the formula sources did not change since (00:20).
  **Cause found (second pass).** The live detail text is in each job's `boot.log`
  (`run A vs run B: probe calls: 5 vs 2 (5 done inline by B)` for attack, `4 vs 1` for hit, `6 vs 3`
  on some routes: always 3 more in the game). The notes of all 64 kept records (records.fecap)
  show the game calling `ItemSubKind::Get` 0x0019B97C (the triangle batch's override
  `item_subkind_record`) 4 times in GetHit and 5 times in GetAttack, and every kept record has the
  rank-bonus argument set. The readable code calls 0x0019B97C through the guest only where an
  original it calls does (Item::GetHit / GetPower / IsMagic), and makes the three weapon-kind lookups
  of the rank bonus (`weapon_rank_term` -> `item_weapon_kind` -> `item_subkind_record`) in C. The
  checker's rule 4 lets B do a callee's work inline only when B never calls that callee itself, so
  those three count as missing. Proposed fix for the formula track (not made here, not tested):
  reach `ItemSubKind::Get` through the guest for those three lookups in `weapon_rank_term`
  (src/readable/battle/formula_unit.c), then rerun the live compare. [high for the cause: 64 of 64
  kept records fit; the fix is unproven]
- **Formula overrides met in real play: 15 of 21.** 0 mismatches: the five stat getters,
  `unit_equipped_index`, `unit_avoid` (tier 2 could not sample it; met here 148 times), `unit_crit`,
  `unit_crit_avoid`, `unit_attack_speed`, `unit_defense_speed`, `forecast_hit`, `forecast_strikes`.
  MISMATCH: `unit_hit`, `unit_attack`. Not met: the slot forms `unit_hit_of_slot`, `unit_avoid_of_slot`,
  `unit_crit_of_slot`, `unit_attack_of_slot`, and `unit_attack_for_terrain` (+ its slot form).
- **Committed overrides met: 34 of 35, all with 0 mismatches.** New: `ai_value_is_signal` (bt-ch4,
  17 records, 17 match; bt-ch4 had never been captured before). Still never met:
  `script_unit_can_dragon_vein`.
- **%APPDATA% / %LOCALAPPDATA%** (zakuro and 3dsrecomp folders, every file's size and time): listed
  before the library build and after all runs and both check_all runs: 21,654 entries, no difference (the only files written under %LOCALAPPDATA% were the session's own scratch files in Temp). parallel.py's own check said
  "unchanged" for both sessions.
- **Checks.** New `check_all` rows: `markers-selftest`, `headless-selftest`, `parallel-tests` (fast),
  `formula-diff` (medium, with the 30 planted bugs) and the slow `formula-diff-long` and
  `parallel-smoke` (a real title x3 determinism run; new need `robot`: boot.exe, the capture library and
  the empty start save). `tests/test_check_all.py`: samples for every new row and a test of the `robot`
  need, 46 tests. Results: `python tools/check_all.py` **PASS** (38 pass, 12 skip: the 11 slow rows and `gen-headers`, not made for Fates; about 13 minutes); `python tools/check_all.py --slow` (started at below-normal priority) **PASS** (49 pass, 1 skip: `gen-headers`; about 47 minutes): `parallel-smoke` title x3 DETERMINISTIC, side by side 8.7 s against 16.9 s one after another; `formula-diff` 6,900 cases and 30/30 planted bugs, `formula-diff-long` 23,000 cases, 0 mismatches; `readable-verify` OK over all 56 (23 ABI-ONLY, 4 CLEAN, 26 GAVE-UP, 3 UNSAMPLED, 0 MISMATCH).
  Second pass: `formula-diff` / `formula-diff-long` now also fail when one function has 30% or more
  early give-ups (90 of 300, 300 of 1000; today at most 15 of 300), so an override that always gives
  up early can no longer pass; samples in `tests/test_check_all.py`. Rerun results:
  `python tools/check_all.py --slow` (13:50-14:38, below-normal) **PASS** (49 pass, 1 skip: `gen-headers`): `formula-diff` 6,900 cases, 30/30 planted bugs, `formula-diff-long` 23,000 cases, both 0 mismatches and under the early give-up limit; `parallel-smoke` DETERMINISTIC c3cbbe48 (10.3 s side by side, 18.9 s one after another); `parallel-tests` 24 tests OK; `readable-verify` 0 MISMATCH over 56 (23 ABI-ONLY, 4 CLEAN, 26 GAVE-UP, 3 UNSAMPLED). `python tools/check_all.py` (14:38, below-normal) **PASS** (38 pass, 12 skip). `tests/test_check_all.py` 46 tests OK. %APPDATA%/%LOCALAPPDATA% zakuro and 3dsrecomp: 21,654 entries before and after, 0 differ.
- **Open.** `unit_hit` / `unit_attack`: the three weapon-kind lookups (cause above, formula track);
  docs/TRIANGLE.md
  section 6 still lists the two helper rows the formula overrides replaced; the parallel.py regression
  test for the start save picks `bt-prologue`, whose save is the default, so it would not catch the old
  bug; verify.py does not lower its own priority (the join ran it only inside `check_all --slow`, itself
  started at below-normal). The plain-language owner report is docs/REPORT_2026-11-12.md (written in the second pass).

## Status update 2026-11-12 (formula fix): `unit_hit` / `unit_attack` clean in real play

**In plain words.** The two formula functions that gave the right numbers but asked the game's
"what kind of weapon is this?" helper 3 times fewer than the game now ask it exactly as often and
in the same order. The live comparison on four Birthright pieces shows **0 differences of any kind**
over every readable function met, so the F-018 goal is met. No status or percentage changes
(statuses stay `unverified`, F-017; step 9 stays ~10%).

- **Fix** (src/readable/battle/formula_unit.c): the rank bonus's three weapon-kind lookups
  (`weapon_rank_term`) now go through `rank_weapon_kind`: `unit::Item::ToData`, then
  `ItemSubKind::Get` 0x0019B97C through `guest_call1` (`GUEST_ItemSubKindGet` in
  src/readable/battle/formulas.h; a reader, so safe to replay, rule 4), then the record's byte +1;
  a give-up check after each guest call. The game's order is kept: kind, kind, `WeaponBonus::Get`,
  kind, weapon exp (0x00532F2C..0x00532FD4 in GetHit, 0x005341FC..0x005342A0 in GetAttack, read
  2026-11-12). `ItemSubKind::Get` already had a targets.csv row (it is the override
  `item_subkind_record`); `gen_stubs.py --check` OK (56 overrides, 15 guard users, 0 probes).
  triangle_battle.c's `item_weapon_kind` uses are unchanged: the game calls `ItemSubKind::Get` there
  too (0x00347A84, 0x00347A9C, 0x003490CC, 0x003490F8, 0x00349A04, 0x00349A30), but those are helpers
  with no override, so they never run in the game and are not shadow-compared; they need the same
  change when their `CalculateDetail*` functions become overrides.
- **Host test** (src/readable/battle/tests/formula_diff.py): now also counts the calls to
  `ItemSubKind::Get` on both sides (ARM: every BL to it; C: a guest call reaches its readable override,
  as in the capture library) and a 31st planted bug puts the C lookup back (caught: 400 mismatches).
  `formula_diff.py` 6,900 cases (seed 20261111) and `-n 1500 --seed 7 --plant` 34,500 cases, both
  **0 mismatches**, 31/31 planted bugs caught. `triangle_diff.py --plant` 5,200 cases, 0 mismatches,
  18/18. `tools/readable/check.py` OK.
- **Tier 2** (`verify.py --rom ...`, below-normal, library build 277 s): `readable-verify: OK
  (23 ABI-ONLY, 4 CLEAN, 26 GAVE-UP, 3 UNSAMPLED)`, **0 MISMATCH** (same split as before; `unit_hit`,
  `unit_attack` GAVE-UP on cold caches, `item_subkind_record` ABI-ONLY).
- **Capture library rebuilt once**: `parallel.py build -- --rom ...` (below-normal, one build),
  292.7 s, peak 75.6 MB, `build.py --check-fresh` FRESH (17 staged files, 2026-11-12 15:12).
- **Live shadow compare** (`parallel.py runs --mode capture --keep`, routes bt-ch2, bt-ch7,
  bt-ch8-pair, bt-castle-shop; owner budget: at most 6 at once, below-normal, 8 GB; wall 203.9 s,
  peak 362 MB per run; run twice, the same result): memory hashes bt-ch2 059736d3, bt-ch7 4376a256
  (both equal to the committed runs), bt-ch8-pair 047fe571, bt-castle-shop fd292276 (capture does not
  disturb the game). **2,966 records over 47 overrides: 2,889 match, 51 gave up (the original ran),
  26 incomplete, 0 `mismatch_r0`, 0 `mismatch_mem`, 0 `mismatch_calls`, 0 `b_escaped`.**
  `unit_hit` 55 records (45 match, 3 gave up, 7 incomplete), `unit_attack` 55 (55 match),
  `item_subkind_record` 111 (111 match). No "probe calls" line in any boot.log.
  Not met on these four routes: `ai_value_is_signal` (bt-ch4) and `script_trick_test` (met in the
  join on other routes, 0 mismatches there), and the 7 never met anywhere (the six formula slot /
  terrain forms and `script_unit_can_dragon_vein`). Three of the four routes (bt-ch2, bt-ch7,
  bt-ch8-pair) are among the 8 where the join saw the 214 records; the other five battle routes were
  not rerun.
- **Checks.** `python tools/check_all.py` (below-normal) **PASS** (38 pass, 12 skip: the slow rows
  and `gen-headers`); `formula-diff` 6,900 cases, 31/31 planted bugs (its row text now says the
  `ItemSubKind::Get` calls are compared and 31 bugs); `castle-test` 18 tests. `--slow` not rerun.
- **%APPDATA% / %LOCALAPPDATA%** zakuro and 3dsrecomp: 21,654 entries before the library build and
  after all runs, verify and check_all, 0 differ; parallel.py's own check "unchanged" for both sessions.
- **Review round 3** (docs/collab/reviews/REVIEW_2026-11-12.md), both low findings fixed:
  docs/FORMULAS.md section 8 keeps the enemy half-crit exception (state bit 5) and the damage
  modifiers, and says to copy sections 2 to 5; tools/castle/sheetlib.py `insert_rows` refuses a sheet
  whose header is not wholly before its rows (tests in tools/castle/test_castle.py, `InsertLayout`).

## Status update 2026-11-12 (growth batch): growth, level-up and experience readers

**In plain words.** The game's level-up and experience rules are now read and written up
(docs/GROWTH.md): every unit keeps its own dice seed, a level-up makes a fresh roller from it, so
the same unit always gets the same level-up; growth is personal + class (+ boon/bane, children
average with a parent), caps are class + personal (+ family, boon/bane), experience comes from
per-difficulty tables by level gap. 23 more readable functions and 5 helpers, all matching the
game's own code on made-up cases, tier 2 clean. No status or percentage changes (statuses stay
`unverified`, F-017; step 9 stays ~10%); the level-up itself (a writer) stays off.

- **Code** (src/readable/unit/growth.h, growth_rates.c, growth_exp.c, growth_roll.c): 23 overrides
  (readers) and 5 helpers; registry rows in config/readable/functions.csv, harness rows in
  config/harness/targets.csv (`gen_stubs.py --check`: 79 overrides, 19 guard users, 0 probes); new
  layouts (Unit +0xC0/+0xF1/+0xF2/+0x12F/+0x130/+0x132, GameUserData +0x2D, Situation +0x17,
  FamilyParent, G_ExpTable), headers regenerated with `gen_structs.py gen`. `Unit::GetLimit`, a guest
  call of the formula batch until now, is one of the 23: the stat getters' call of it is in the
  game's place (after `ToData`, before `Edit::GetCapability`, read in GetStrImpl and GetMHPImpl).
- **Settled:** `Unit::LevelUp` 0x003D8154 rolls and applies the stats (on a copy made by
  `GrowSequence::LevelUpCalculate`; `LevelUpReflect` copies it back); `GrowSequence::LevelUp` is a
  level comparison; `GainExp` only starts `ExpSequence::Create`, which adds the experience.
  Dice per level-up: 20 (seeding) + 1 (new seed) + one per stat with a rate above 0 per pass, at
  most 4 passes; the caps never change which numbers are drawn.
- **Host test** (src/readable/unit/tests/growth_diff.py, arm_mini on extracted/text.bin): r0,
  unmapped reads and the whole ordered list of guest calls with their argument registers; seed
  20261112 7,800 cases and `-n 1500 --seed 7` 39,000 cases, **0 mismatches**; `--plant` **36/36**
  planted bugs caught. `formula_diff`, `triangle_diff`, `stance_diff`, `vein_diff` (`-n 40`) still
  OK with the new sources linked in; `tools/readable/check.py` OK (95 registry rows; host 146/146,
  capture 565/565, undo 554/554).
- **Tier 2** (`verify.py --rom ... --out build/readable/verify_growth`, below-normal, library build
  336 s): `readable-verify: OK (35 ABI-ONLY, 4 CLEAN, 36 GAVE-UP, 4 UNSAMPLED)`, **0 MISMATCH** over
  all 79 overrides. This batch: ABI-ONLY the six ExpTable getters, `situation_can_gain_exp`,
  `unit_stat_limit`, `edit_grow`, `edit_limit`, `family_grow`, `family_limit`; GAVE-UP (cold caches in
  verify's made-up memory: only the fallback ran) `unit_grow`, `unit_exp_level`, `unit_exp_damage`,
  `unit_dual_exp_damage`, `unit_exp_destroy`, `unit_exp_dance`, `unit_exp_rod`, `unit_exp_normalize`,
  `unit_level_limit`, `job_level_limit`; UNSAMPLED `family_parent_grow` (3dsrecomp keeps it inside
  `f_0053B6CC`, Family::GetGrow, which branches into it). The first run the same evening had **1
  MISMATCH**, `unit_dual_exp_damage`: a shadow-pass fault surplus (79 against 500) beyond check.py's
  bound for nested readable overrides, because its guest call of GetExpDamage gave up inside on the
  cold level cache while the outer function did not; fixed the way the formula batch fixed its
  give-ups (ask for the needed cache first), host test rerun, second run clean. Registry statuses
  not changed (no `--update-status`).
- **Not done:** no robot route records a level-up (BATCH_GROWTH); no live shadow compare of the new
  overrides (needs a capture-library rebuild and runs, not done in this batch); no `check_all.py`
  row for growth_diff (the integrate stage adds it); the writers (`Unit::LevelUp`, `ExpSequence`)
  stay off (F-017).
- **%APPDATA% / %LOCALAPPDATA%** zakuro and 3dsrecomp: 21,658 entries before the first verify and
  after both, 0 differ.

## Status update 2026-11-13 (integrate): robot round 4 and the growth batch, checked together

**In plain words.** The robot cleared Chapter 8 and reached the castle Smithy, but could not forge a
weapon to +1 (the save has no ore; getting ore needs a battle the plan has not allowed yet). The
growth batch made level-ups and experience readable. The join rebuilt the capture library once with
all 79 overrides and replayed **all 12 Birthright routes** with every override watched: 67 met, 10,334
records, **0 mismatch records of any kind**, and the game ended in the same state as the original
runs on every route. The plan total moves from about 46% to about 49% (robot ~60% -> ~65%, readable
~10% -> ~12%, and step 7 corrected from a stale 0% to ~50%). Plain-language owner report:
docs/REPORT_2026-11-13.md. (Run the evening of 2026-11-12.)

- **Step 7, screen extras (stale 0% -> ~50%)** [low for the percentage]. The extras landed in commit
  9e16174 (docs/EXTRAS.md; 3f899fb says so) but this row still said "not started". Checked here only by
  `python tools/extras/usa_extras.py verify`: "51 words in 4 extras: all check out". Their robot
  evidence (two Birthright chapters, game results and saves unchanged with the three safe switches)
  is the extras workflow's, not rerun here. Missing: the owner's look in a window; no `check_all` row.
- **Step 8, test robot (~60% -> ~65%)** [low for the percentage, high for the facts]. Round 4
  (docs/ROBOT.md): `bt-ch8` (Chapter 8 cleared, 16 turns, both veins, memory bee8415f twice, save
  bt-ch8-clear), `bt-castle-forge` (Smithy built and entered, a second Iron Katana bought, the forge menu
  with two katanas; A refused: 0 of all 12 ores, 1 Pearl needed; memory d6f814c6). ROBOT_PLAN row 7
  (forge to +1) stays **not done**: every way to ore needs a battle or Chapter 9, which ROBOT_NEXT rules
  out; owner's call. New marker reads `levels` (Unit +0xF1 level, +0xF2 exp, +0xC8 gains; force 0 and,
  in My Castle, force 3), `forged`/`forge_max`/`forge_pairs` (bits 8-13 of weapons only, read so far
  only at +0), `ore`/`food`; dotted checkpoint keys (`levels.6.lv`); `levelups.py` lists level-ups per
  session (bt-prologue, bt-ch3, bt-ch4, bt-ch5, bt-ch7, bt-ch8); `parallel.py pack`. Not counted done:
  the forge, H5/H6, the writer-callee list, 12 never-met overrides.
- **Step 9, readable rewrite (~10% -> ~12%)** [low]. The growth batch (status line above) plus the first
  live compare of all 79 overrides with 0 MISMATCH. Raised a little because every met override is now
  clean in real play on every Birthright route (F-018), the batches total 79 readers and 16 helpers, and
  the level-up rules are settled from the code. Kept small: statuses stay `unverified`, no writer runs
  (F-017), and 12 overrides are never met.
- **Capture library rebuilt once**: `parallel.py build` (below-normal, one build), 311.8 s, peak 75.4 MB,
  `build.py --check-fresh` **FRESH** (20 staged files, built 2026-11-12T20:26:54). Before it the check
  said STALE (targets.csv changed by the growth batch).
- **Live shadow compare, all 12 Birthright routes** (`parallel.py runs --mode capture --keep --session
  i5-cap`, 12 runs, at most 6 at once, below-normal, wall 594 s, peak 360.6 MB per run). Every run PASS
  and its memory hash equals the original-mode runs: bt-prologue a3e4ec17, bt-ch2 059736d3, bt-ch3
  98dc9c69, bt-ch4 18ca52e0, bt-ch5 cb875c8b, bt-ch6-castle e0758406, bt-castle-shop fd292276, bt-ch7
  4376a256, bt-ch8-support ce8e57f0, bt-ch8-pair 047fe571, bt-ch8 bee8415f, bt-castle-forge d6f814c6
  (capture does not disturb the game). Totals from every run's `summary.tsv`: **67 of 79 overrides met,
  10,334 records: 10,048 match, 180 gave up (the original ran), 106 incomplete, 0 `mismatch_r0`, 0
  `mismatch_mem`, 0 `mismatch_calls`, 0 `b_escaped`, 0 unfaithful, 0 escaped**; no "probe calls" or
  MISMATCH line in any boot.log. [2026-11-14: the boot.log grep is not evidence, its `[fe-capture]` lines are capped (ROBOT.md 4, HARNESS.md); the verdict is the summary.tsv totals before it.] Records per route: bt-prologue 937, bt-ch2 946, bt-ch3 1,101, bt-ch4
  1,087, bt-ch5 1,039, bt-ch6-castle 761, bt-castle-shop 371, bt-ch7 1,287, bt-ch8-support 349,
  bt-ch8-pair 924, bt-ch8 1,181, bt-castle-forge 351. The five battle routes not rerun after the
  formula fix (bt-prologue, bt-ch3, bt-ch4, bt-ch5, bt-ch6-castle) are clean: `unit_hit` 163 records
  over 9 routes (140 match, 7 gave up, 16 incomplete), `unit_attack` 163 (160 match, 3 incomplete).
- **Growth overrides in real play: 18 of 23 met, all 0 mismatch.** Records (match / gave up /
  incomplete): `unit_stat_limit` 345 (345), `edit_limit` 317 (316/0/1), `job_level_limit` 188
  (177/10/1), `unit_level_limit` 142 (142), `unit_exp_level` 113 (106/7), `situation_can_gain_exp` 110
  (110), `unit_exp_normalize` 105 (105), `exp_table_battle` 86 (86), `exp_table_battle_threshold` 86
  (86), `unit_grow` 74 (68/6), `edit_grow` 72 (72), `unit_exp_damage` 66 (59/7), `unit_exp_destroy` 41
  (34/7), `unit_dual_exp_damage` 8 (8), `unit_exp_rod` 8 (8), `exp_table_rod_decline` 8 (8),
  `exp_table_support_decline` 8 (8), `exp_table_rod_high_decline` 3 (3). `unit_grow` and `edit_grow`
  are met exactly on the six routes with level-ups. Not met: `exp_table_dance`, `unit_exp_dance` (no
  dancer yet), `family_grow`, `family_limit`, `family_parent_grow` (no child unit yet; the last is
  also UNSAMPLED in tier 2). Tier 2 GAVE-UP ones now have live evidence: `unit_grow`, `unit_exp_level`,
  `unit_exp_damage`, `unit_dual_exp_damage`, `unit_exp_destroy`, `unit_exp_rod`, `unit_exp_normalize`,
  `unit_level_limit`, `job_level_limit` are all met with 0 mismatch. `Unit::GetLimit` (`unit_stat_limit`),
  reached by guest call from the formula stat getters, is clean in 345 records on every route.
- **Overrides never met (12):** the 5 growth ones above, the six formula slot/terrain forms
  (`unit_hit_of_slot`, `unit_avoid_of_slot`, `unit_crit_of_slot`, `unit_attack_of_slot`,
  `unit_attack_for_terrain`, `unit_attack_for_terrain_of_slot`) and `script_unit_can_dragon_vein`.
- **Checks.** New `check_all` rows: `growth-diff` (medium: `growth_diff.py --plant`, 36 planted bugs, and
  as in `formula-diff` it fails at 90 or more early give-ups of a function's 300 cases; today at most 1),
  `growth-diff-long` (slow: `-n 1500 --seed 7`, fails at 450 of 1500), `harness-levelups`
  (`levelups.py --selftest`); `markers-selftest` text now names levels, forge levels and ore (24/24).
  `tests/test_check_all.py`: samples for the three new rows, markers 24/24 and parallel-tests 25; 46
  tests OK. `python tools/check_all.py --slow` (20:43-21:34, below-normal) **PASS (52 pass, 1 skip:
  `gen-headers`)**: `growth-diff` 7,800 cases, 0 mismatches, 36/36; `growth-diff-long` 39,000, 0;
  `formula-diff` 6,900, 31/31; `formula-diff-long` 23,000; `readable-verify` OK over 79 (35 ABI-ONLY,
  4 CLEAN, 36 GAVE-UP, 4 UNSAMPLED, 0 MISMATCH); `parallel-smoke` DETERMINISTIC c3cbbe48 (11.9 s side by
  side, 20.9 s one after another); `parallel-tests` 25 tests; `harness-selftest` 76/76. `python tools/check_all.py` (21:34-21:54, below-normal) **PASS (40 pass, 13 skip: the 12 slow rows and `gen-headers`)**.
- **%APPDATA% / %LOCALAPPDATA%**: %APPDATA% (zakuro, 3dsrecomp, Citra, azahar, lime3ds) and %LOCALAPPDATA% (zakuro, 3dsrecomp, Citra), every entry's size and modification time, listed before the library build and after the runs and both check_all runs: 32,548 and 21,620 entries, identical. parallel.py's own check said "unchanged" for i5-cap.
- **Open.** The forge to +1 (needs ore: owner's call on a battle or Chapter 9); the forge-level read
  has only seen +0 live; the growth host test cannot catch the "ask for the cache first" regression in
  `unit_dual_exp_damage` that tier 2 caught (the growth reviewer's finding: worth a planted bug or a
  nesting check); markers' self-test does not cover `Item::IsWeapon`'s second non-weapon kind (8);
  `levels` raw stats leave out the avatar's boon/bane; `tools/harness/robot/bd.sh` starts probe.py
  directly, outside parallel.py's budget (one run at a time); Grok's docs/tracks/BATCH_GROWTH.md
  ("no committed route is a level-up exit") and OPTIONS_V2.md ("GainExp applies experience") are out of
  date (Grok's files, not edited); the robot's scratch states and kept sessions in build/ can be removed
  with `parallel.py clean`. Memory hashes of bt-ch8-support, bt-ch5, bt-ch4 and bt-ch6-castle appear
  in no tracked file before this section; they match the robot's and the join's runs.

## Status update 2026-11-13 (skills batch): skill readers, read only

**In plain words.** The game's "does this unit have skill X" checks, the activation chance of a skill
and the way a fight decides which attack skill fires are now written up from the code
(docs/SKILLS.md) and rewritten as readable code that only reads. The key fact for later options: for
each attack skill a unit has, the game throws one 100-sided die *before* it works out the chance, and
the first skill that fires ends the list, so carrying a skill moves every later die of that fight.
Nothing that changes the game was written (F-017). The readable rewrite moves from ~12% to ~13%
[low]; the plan total from 49.3% to 49.5%.

- **Step 9, readable rewrite (~12% -> ~13%)** [low for the percentage, high for the facts].
  `src/readable/skill/` (`skills.h`, `skill_has.c`, `skill_battle.c`, all UNVERIFIED): **15 overrides**
  (`unit_has_skill` = Unit::IsEquipSkill, `unit_personal_skill`, `unit_equipped_skill_count`,
  `skill_record`, `skill_total`, `skill_common_total`, `job_class_skill`, `skill_pool_test`,
  `skill_is_unknown`, `script_unit_has_skill`, `unit_has_rally_move_skill`, `unit_has_rally_skill`,
  `battle_side_has_skill` = HasBattleSkill, `unit_lethality_immune` = IsInvalidKill,
  `skill_effect_name` = SkillIndexProvider::GetSkillEffectName) and **2 helpers** (`unit_skill_chance` =
  the whole of GetEquipSkillProbability with the stat from a callback; `battle_attack_skill_pick` = the
  skill choice of BattleCalculator::CalculateAttack). Registry 112 rows; `gen_stubs.py --check`: 94
  overrides, 24 guard users; `tools/readable/check.py`: OK (lint 112 rows, 22 sources, staged files,
  host 146/146, capture 565/565, undo 554/554). New layouts: Unit +0xFE equip_skills, EquipSkillTable,
  SkillIndexProvider, GameRandom; globals G_EquipSkill, G_SkillIndexProvider, G_BattleRandom, G_IdentHash.
- **Host differential test** `python src/readable/skill/tests/skill_diff.py` (17 functions; r0, unmapped
  reads and the ordered guest-call list; out-of-range inputs, unmapped and "torn" units; a nested
  give-up is a mismatch): seed 20261113 **5,100 cases, 0 mismatches**; `-n 1500 --seed 7` **25,500 cases,
  0 mismatches**; `--plant` (200 cases per function per bug) **32/32 planted bugs caught**, among them
  five that change only the calls, the unmapped reads or a nested give-up, not the numbers. Early
  give-ups at most 19 of 300 (`battle_attack_skill_pick`, which asks 16 caches first). [Corrected 2026-11-13, menus batch: the reviewer's
  rerun at the default seed showed 30 of 300 for `battle_attack_skill_pick`; with the menus batch's generator it is 26 of 300; see that status update.] The other diff
  tests still pass with the new sources linked in (stance, triangle, vein, formula: `-n 30`, 0 mismatches).
- **Review 4 fix (growth_diff.py):** the driver now counts give-ups by nesting depth and a nested one
  is a mismatch; the two-unit experience getters get a cold level cache more often; new planted bug
  "review 4" removes the ask-first lines of `unit_dual_exp_damage` (growth_exp.c). Proof: the old test
  (HEAD) with only that regression planted, 2,000 cases of `unit_dual_exp_damage`: **NOT CAUGHT**; the
  new test, same regression and cases: **caught, 152 mismatches**. Full runs: `--plant` 7,800 cases, 0
  mismatches, **37/37** planted bugs (the regression: 12 mismatches); `-n 1500 --seed 7` 39,000 cases, 0
  mismatches; early give-ups at most 1 of 300.
- **Tier 2** (`verify.py --rom ... --out build/readable/verify_skill`, below-normal, library build 320 s):
  `readable-verify: OK (43 ABI-ONLY, 6 CLEAN, 41 GAVE-UP, 4 UNSAMPLED)`, **0 MISMATCH over all 94
  overrides**. This batch: CLEAN `skill_total`, `skill_common_total`; ABI-ONLY `unit_has_skill`,
  `unit_personal_skill`, `unit_equipped_skill_count`, `skill_record`, `skill_pool_test`,
  `skill_is_unknown`, `script_unit_has_skill`, `skill_effect_name`; GAVE-UP (cold caches in verify's
  made-up memory: only the fallback ran) `job_class_skill`, `unit_has_rally_move_skill`,
  `unit_has_rally_skill`, `battle_side_has_skill`, `unit_lethality_immune`. Registry statuses not changed.
- **Not done:** no live shadow compare of the 15 new overrides (needs a capture-library rebuild and
  robot runs; not run in this batch); no robot route is known to replay a skill activation
  (`skill_banners` waits for one); the writers (`CalculateAttack`, `CalculateAttackSingle`,
  `EquipSkillCalculator::Calculate`, `GainSkill`) stay off (F-017); no `check_all.py` row for
  skill_diff (the integrate stage adds it).
- **%APPDATA% / %LOCALAPPDATA%** (zakuro, 3dsrecomp, Citra, azahar, lime3ds / zakuro, 3dsrecomp,
  Citra), every entry's path, size and modification time: 54,168 entries before the verify run and
  after it and all test runs, 0 differ.

## Status update 2026-11-13 (integrate, overnight round 5): robot round 5 and the skills batch, checked together

**In plain words.** The robot cleared Chapter 9 and forged a weapon to +1 (an Iron Naginata, with
Coral from the lottery; Hana's katanas still need a Pearl). The skills batch made the skill checks
readable. The join rebuilt the capture library once with all 94 overrides and replayed **all 14
Birthright routes** with every override watched: 84 met, 15,442 records, **0 mismatch records of any
kind**, and every route ended in the same memory as its original runs. The plan total moves from
49.5% to 50.2% (robot ~65% -> ~70%, readable ~13% -> ~14%, both [low]). Owner report:
docs/REPORT_2026-11-13.md, section "Overnight round 5". Run from 01:58 at the owner's night budget
(FEF_ROBOT_JOBS=12, below-normal, 8 GB).

- **Step 8, test robot (~65% -> ~70%)** [low for the percentage, high for the facts]. Round 5
  (docs/ROBOT.md 3, 3a, 3b): `bt-ch9` (Chapter 9, 19 turns, five Sings, the holy-tree vein; save
  bt-ch9-clear, sha256 17a65b97...) and `bt-ch9-ore` (Lottery Shop, 1 Coral, a second Iron Naginata,
  Smithy: Iron Naginata +1; marker `forged` = [{where 11, item 71, rank 1}], `forge_max` 1, also after
  loading the packed save bt-castle-ore, sha256 022f5e1b...). Both replayed from frame 0 twice by the
  robot (r5-a, r5-b: memory eb41cae1 / 25a4d7e8, checkpoints all met) and a third time here in capture
  mode (same hashes). ROBOT_PLAN row 7 counts as reached with the naginata; the katana/Pearl goal it
  first named is not met (no ore building after Chapter 9). New `tools/harness/robot/budget.py` (priority
  from resources.json, one look-ahead run at a time under a lock, boot.exe's APPDATA below build/):
  **untracked, but the tracked probe.py and auto.py import it, so it must be committed with them.**
- **Step 9, readable rewrite (~13% -> ~14%)** [low]. The skills batch (section above) plus its first
  live compare: 11 of the 15 skill overrides met, all 0 mismatch; 6 of the 12 overrides never met before
  are now met and clean.
- **Capture library rebuilt once**: `parallel.py build` (below-normal, one build), 301.8 s, peak 75.6 MB;
  `build.py --check-fresh` **FRESH** (22 staged files, built 2026-11-13T01:58:07). Before it: STALE
  (targets.csv changed by the skills batch).
- **Live shadow compare, all 14 Birthright routes** (`parallel.py runs --mode capture --keep --session
  i6-cap`, 14 runs, at most 12 at once, below-normal, wall 1,015 s, peak 367.7 MB per run). Every run PASS
  and its memory hash equals the original-mode runs: bt-prologue a3e4ec17, bt-ch2 059736d3, bt-ch3
  98dc9c69, bt-ch4 18ca52e0, bt-ch5 cb875c8b, bt-ch6-castle e0758406, bt-castle-shop fd292276, bt-ch7
  4376a256, bt-ch8-support ce8e57f0, bt-ch8-pair 047fe571, bt-ch8 bee8415f, bt-castle-forge d6f814c6,
  **bt-ch9 eb41cae1, bt-ch9-ore 25a4d7e8**. Totals from every run's `summary.tsv`: **84 of 94 overrides
  met, 15,442 records: 15,078 match, 242 gave up (the original ran), 122 incomplete, 0 `mismatch_r0`,
  0 `mismatch_mem`, 0 `mismatch_calls`, 0 `b_escaped`, 0 unfaithful, 0 escaped**; no "probe calls" or
  MISMATCH line in any of the 14 boot.logs. [2026-11-14: the boot.log grep is not evidence, its `[fe-capture]` lines are capped (ROBOT.md 4, HARNESS.md); the verdict is the summary.tsv totals before it.] Records per route: bt-prologue 1,099, bt-ch2 1,087, bt-ch3
  1,264, bt-ch4 1,251, bt-ch5 1,208, bt-ch6-castle 890, bt-castle-shop 457, bt-ch7 1,475, bt-ch8-support
  441, bt-ch8-pair 1,073, bt-ch8 1,381, bt-castle-forge 395, bt-ch9 1,710, bt-ch9-ore 1,711.
- **Skill overrides in real play: 11 of 15 met, all 0 mismatch.** Records (match / gave up):
  `unit_has_skill` 418 (418, all 14 routes), `skill_record` 334 (334), `unit_personal_skill` 322 (322),
  `skill_common_total` 270 (270), `battle_side_has_skill` 225 (214/11), `unit_has_rally_skill` 202
  (191/11), `unit_has_rally_move_skill` 179 (179), `job_class_skill` 90 (90), `skill_pool_test` 46 (46),
  `skill_effect_name` 15 (15; bt-prologue, bt-ch8, bt-ch9, bt-ch9-ore), `skill_is_unknown` 1 (1, bt-ch8).
  Four of the five that were GAVE-UP in tier 2 now have live evidence (`job_class_skill`, both rally
  checks, `battle_side_has_skill`). Not met: `unit_equipped_skill_count`, `skill_total`,
  `script_unit_has_skill`, `unit_lethality_immune`. The helpers `unit_skill_chance` and
  `battle_attack_skill_pick` are not overrides and are not in the capture compare; no route is known to
  replay a skill activation (skill_banners still waits).
- **Never met before, now met (6), all 0 mismatch, only on bt-ch9 / bt-ch9-ore:** `exp_table_dance` 12
  (6 + 6), `unit_exp_dance` 12 (10 match, 2 gave up), `unit_hit_of_slot` 54 (48 / 2 gave up / 4
  incomplete), `unit_avoid_of_slot` 56 (52/2/2), `unit_crit_of_slot` 54 (52/2/0), `unit_attack_of_slot`
  54 (52/0/2) (the detail view switched on by the touch at 6965). The robot's report listed
  `ai_value_is_signal` as not met; it is met (17 records, bt-ch4, 0 mismatch), as it was in i5-cap.
- **Overrides never met (10):** the 4 skill ones above, `unit_attack_for_terrain`,
  `unit_attack_for_terrain_of_slot` (attacks on breakable terrain; no such map yet), `family_grow`,
  `family_limit`, `family_parent_grow` (a child unit), `script_unit_can_dragon_vein` (Revelation
  scripts and X015 only, ROBOT.md 3b).
- **Checks.** New `check_all` rows: `skill-diff` (medium: `skill_diff.py --plant`, 32 planted bugs; fails
  at 90 or more early give-ups of a function's 300 cases), `skill-diff-long` (slow: `-n 1500 --seed 7`,
  fails at 450 of 1500), `extras-verify` (`usa_extras.py verify`: every screen-extras site against
  code.bin; gives row 7 a standing check). `growth-diff` text now says 37 planted bugs; the markers
  sample is 25/25. No other robot self-test row: `budget.py` has none (its lock and priority were
  checked by hand by the robot stage). `tests/test_check_all.py`: samples for the three new rows,
  markers 25/25, growth 37/37; 46 tests OK. `python tools/check_all.py` (02:21-02:45, below-normal)
  **PASS (42 pass, 14 skip: the 13 slow rows and `gen-headers`)**: `skill-diff` 5,100 cases, 0
  mismatches, 32/32 (3 min 35 s); `growth-diff` 7,800, 37/37; `formula-diff` 6,900, 31/31;
  `extras-verify` "51 words in 4 extras: all check out"; `markers-selftest` 25/25. `python tools/check_all.py --slow` (02:46-03:44, below-normal, FEF_ROBOT_JOBS=12) **PASS (55 pass, 1 skip: `gen-headers`)**: `skill-diff` 5,100 / 32/32; `skill-diff-long` 25,500 cases, 0 mismatches; `growth-diff-long` 39,000, 0; `formula-diff-long` 23,000; `readable-verify` OK over 94 (43 ABI-ONLY, 6 CLEAN, 41 GAVE-UP, 4 UNSAMPLED, 0 MISMATCH); `parallel-smoke` DETERMINISTIC c3cbbe48 (8.7 s side by side, 17.9 s one after another); `assets-full` 21,880/21,880; `harness-selftest` 76/76.
- **%APPDATA% / %LOCALAPPDATA%**: %APPDATA% (zakuro, 3dsrecomp, Citra, azahar, lime3ds) and
  %LOCALAPPDATA% (zakuro, 3dsrecomp, Citra), every entry's path, size and modification time, listed
  before the library build and after the runs and both check_all runs: 54,168 entries, identical (build/integrate5/appdata_before.txt, appdata_after.txt). parallel.py's own
  check said "unchanged" for i6-cap.
- **Review findings carried, not fixed here** (other areas' files): `budget.py` lock race (an empty
  lock file read as a dead holder, so two look-aheads could overlap in a tiny window); the markers
  self-test covers forge rank 1 only (a 5-bit or 3-bit rank mask still passes 25/25); skill_diff's
  default `--plant` run rarely makes out-of-short skill numbers (a planted `(int16_t)` cast in
  `unit_has_skill` was caught only at 3,000 cases), an unsigned read of the chosen skill number is not
  caught, and planted bug 30 and a Quixotic-bits plant are each caught by a single mismatch; the
  documented early give-ups "at most 19 of 300" read 30 of 300 in the reviewer's rerun on the default seed (still under the
  row's 90). docs/ROBOT.md 3b quotes two short Japanese game identifiers (a sound cue name and a
  building id): facts, not dumps, but game strings in a tracked file. Grok's ROBOT_NEXT2.md says a
  Birthright castle starts with one ore spot already placed; round 5 found no ore building in the build
  list after Chapter 9 (castle_building.bin's springs come later): one of the two is wrong, not settled.
- **Closed 2026-11-13 (owner):** the forge goal counts as done on the cheat-track proof
  (`cheat-forge-katana`, `cheat-katana-reload`); no Pearl is chased in normal play.
- **Open.** The 10 never-met overrides; H5/H6; the writer-callee list;
  the writers stay off (F-017); the Units list (the slot forms' other caller) is opened in no route.

## Status update 2026-11-13 (menus batch): the readers the options need, read only

**In plain words.** Four of Grok's options turn out to be switches the game already has on its own
options screen: the danger zone, the map HP bars, the battle animations and the game speed. They
all live in one block of settings (`GameConfigData`), and that block is written into **every game
save**, so loading a save also loads its options (what `keep_game_options` has to live with). The
code that reads those settings, decides "battle picture or map", "show this HP bar", "which tiles
are in the danger zone", is now written up (docs/MENUS.md) and rewritten as readable code that only
reads. Nothing that changes an option, the zone, a fight or a save was written (F-017). The
readable rewrite moves from ~14% to ~15%, options from ~12% to ~13% (both [low]); the plan total
from 50.2% to 50.5% by the weights (the rough-total line above is left to the integrate stage).
Run from 04:37 at the owner's night budget (below-normal; no robot runs, no capture-library build).

- **Step 9, readable rewrite (~14% -> ~15%)** [low for the percentage, high for the facts].
  `src/readable/menu/` (`menus.h`, `menu_config.c`, `menu_show.c`, `menu_danger.c`, all UNVERIFIED):
  **16 overrides** (`config_danger_value`, `config_hp_gauge_value`, `config_battle_value`,
  `config_game_speed_value`, `config_ai_skip_value`, `config_distance_value`,
  `config_encounter_bgm_value`, `config_item_value` = the option items' GetValue;
  `config_is_speed_fast`, `config_is_skip_input`, `config_info_capability`, `config_is_detail_battle`
  = GameConfigData::IsDetailBattle, `config_is_detail_support`; `unit_is_detail_battle_must`,
  `unit_is_detail_battle_not_allow`; `danger_panel_is_hide` = map::Panel::Danger::IsHide) and **6
  helpers** (`config_saved_record` = what GameConfigData::Serialize writes; `battle_picture_choice` =
  the decision in the map battle sequence's constructor; `actor_hp_bar_shown` = map::Actor::Tick's bar
  bit; `danger_update_targets`, `danger_add_preview`, `danger_tile_kind` = the unit choice of
  map::Image::Danger::Update, the OR of Danger::Add without UnitMove and the cannon marks, the tile
  test of map::Panel::Danger::SetVertex). Registry 134 rows; `gen_stubs.py --check`: 110 overrides,
  27 guard users; `tools/readable/check.py`: OK (lint 134 rows, 25 sources, staged files, host
  146/146, capture 565/565, undo 554/554). New layouts: GameConfigData, Pad, DangerImage,
  MapActor, BattleSequence; MapImage +0x408 / +0x1008, MapDeploy +0x80C..+0x814, Situation +0x4 bit
  0, +0x8, +0x9; globals G_GameConfig 0x006DA0F8, G_Pad 0x006BD96C; `gen_structs.py check` up to date.
- **Host differential test** `python src/readable/menu/tests/menu_diff.py` (22 functions; for the
  overrides r0, unmapped reads and the ordered guest-call list, a nested give-up is a mismatch; the
  helpers against the whole of Serialize and Danger::Update and against regions of the battle
  sequence's constructor, Actor::Tick, Danger::Add and SetVertex): seed 20261114 **6,600 cases, 0
  mismatches**; `-n 1500 --seed 7` **33,000 cases, 0 mismatches**; `--plant` (200 cases per function
  per bug) **41/41 planted bugs caught, each by 5 or more mismatches**, among them a reordered call
  list, a missing guest call, two nested give-ups and an extra unmapped read. Early give-ups at most
  38 of 300 (`battle_picture_choice`, which asks four caches first; 183 of 1500 at seed 7); no
  other function gives up early. The other diff tests still pass with the new sources linked in
  (stance, triangle, vein, formula, growth: `-n 30`, 0 mismatches).
- **Skill test, review-5 gaps fixed (skill_diff.py, plant fixes only).** The generator now makes
  skill numbers that do not fit a short but whose low half is a skill the unit has (30% of the
  skills taken from the unit, plus 0x10000-type numbers among the rare ones), gives the skill numbers -1 .. -8
  records below the table and uses them as attack skills 16% of the time (so a negative number can
  activate), puts Quixotic on one side more often, an unmapped calculator 15% of the time, and in a
  quarter of the attack cases sets every chance to the first die's value (chance == roll). Two new
  planted bugs: **33** `(int16_t)` cast of the skill number in `unit_has_skill` (**caught, 35
  mismatches**) and **34** the activated skill number read unsigned in `battle_attack_skill_pick`
  (**caught, 5 mismatches**). Bugs 30 (BattleInfo read once) and 28 (Quixotic bits of one side) now
  give 18 and 22 mismatches (each 1 before), 25 (`chance >= roll`) 9 (1 before). Full runs: default
  seed **5,100 cases, 0 mismatches, 34/34**; `-n 1500 --seed 7` **25,500 cases, 0 mismatches**.
  **Early give-ups, corrected:** the reviewer's rerun of the old generator at the default seed saw
  30 of 300 for `battle_attack_skill_pick` (not the documented 19); with this generator it is 26 of
  300 (125 of 1500 at seed 7; `unit_has_rally_skill` 8 / 39), still under the check row's 90 / 450.
  The `check_all` row text (32 planted bugs) and a `menu-diff` row are the integrate stage's.
- **Tier 2** (`verify.py --rom ... --out build/readable/verify_menu`, below-normal, library build 303
  s): `readable-verify: OK (48 ABI-ONLY, 12 CLEAN, 45 GAVE-UP, 5 UNSAMPLED)`, **0 MISMATCH over all
  110 overrides**. This batch: CLEAN `config_danger_value`, `config_hp_gauge_value`,
  `config_battle_value`, `config_game_speed_value`, `config_ai_skip_value`, `config_distance_value`;
  ABI-ONLY `config_encounter_bgm_value`, `config_is_speed_fast`, `config_is_skip_input`,
  `config_info_capability`, `danger_panel_is_hide`; GAVE-UP (cold caches in verify's made-up memory)
  `config_is_detail_battle`, `config_is_detail_support`, `unit_is_detail_battle_must`,
  `unit_is_detail_battle_not_allow`; UNSAMPLED `config_item_value` (in verify's made-up state the
  original's virtual call runs past the interpreter's limit in both passes: nothing compared; the
  host test covers it). Registry statuses not changed.
- **Not done:** no live shadow compare of the 16 new overrides (needs a capture-library rebuild and
  robot runs); no robot route opens the options screen, presses X on the map or fights with the
  battle animations switched (docs/MENUS.md section 5 lists what each option needs replayed first);
  the writers (the option items' SetValue, Reset, Deserialize, Danger::Update / Add, UnitMove, the
  battle sequence's store) stay off (F-017); the cannon marks of Danger::Add are not reproduced.
- **%APPDATA% / %LOCALAPPDATA%** (zakuro, 3dsrecomp, Citra, azahar, lime3ds / zakuro, 3dsrecomp,
  Citra), every entry's path, size and modification time: 54,168 entries before the verify run and
  after it and all test runs, identical (build/menus/appdata_before.txt, appdata_after.txt).

## Status update 2026-11-14 (integrate, overnight round 6): robot round 6, the cheat track and the menus batch, checked together

**In plain words.** The robot got a second way to reach game situations: in its **own** test game
only, it may change a few numbers (the owner's OK, 2026-11-12 night, in chat). Those "cheat routes"
are labelled, scored in their own table and can never be the start of a real-play route (F-019).
The menus batch made the readers of the game's own options screen readable. The join rebuilt the
capture library once with all 110 overrides and replayed **all 14 Birthright routes and all 4 cheat
routes** with every override watched: real play 92 of 110 met, 16,952 records; cheat track 62 met,
3,597 records; **0 mismatch records of any kind on either track**, and every route ended in the same
memory as before. The plan total moves from 50.5% to 50.9% (robot ~70% -> ~72%, readable ~15% ->
~16%, both [low]). Owner report: docs/REPORT_2026-11-14.md. Run from 06:06 local on 2026-11-13 (the report and section carry the 2026-11-14 name this round was given) at the owner's night
budget (FEF_ROBOT_JOBS=12, FEF_ROBOT_MEM_GB=8, below-normal), every robot run and the build through
`parallel.py`.

- **Step 8, test robot (~70% -> ~72%)** [low for the percentage, high for the facts]. Robot round 6
  (docs/CHEATS.md, ROBOT.md): `tools/harness/cheats.py` pokes declared values into the savestate's
  FCRAM between boot.exe stages (no engine change); 4 cheat routes: `cheat-forge-katana` (1 Pearl
  poked; Hana's Iron Katana forged to +1, the ROBOT_PLAN goal as first named, met only on the cheat
  track), `cheat-skill-proc` (Lethality equipped and its chance set to 100: cut-in and kill),
  `cheat-family` (Rinkah given a made-up two-parent family record, so the child-unit readers run at her level-up), `cheat-katana-reload` (no pokes; loads the
  marked cheat save: forge_max 1). Review fix: a cheat save (its name, the cheat mark
  `harness-cheat.json`, or the same save files) is refused as the start of any real-play route by
  `headless.run`, `parallel.py` and `pack_save`; the reviewer's repro (`--route title --save
  cheat-castle-katana`) and a renamed copy are refused (LaunderTests 4/4, robot's evidence).
  `harness.py h4a` now fails on any bad live record and refuses cheat routes (self-test 79/79).
  Markers: forge ranks 2..63 with flag bits, repeated person ids kept apart ("6", "6#2"), self-test
  28/28; levelups 3/3; parallel tests 34 (all rerun here). Not reached: B-c (skill readers:
  `skill_total`, `script_unit_has_skill` not met; `unit_lethality_immune` met once but gave up), B-e
  (breakable terrain, not tried); B-d (family) only **partly**: `family_grow` and `family_limit` met,
  `family_parent_grow` cannot be recorded (reached only by a tail branch, so there is no call to hook).
- **Step 9, readable rewrite (~15% -> ~16%)** [low]. The menus batch (section above) plus its first
  live compare: 8 of its 16 overrides met in real play, all 0 mismatch; 92 of the 110 overrides are now
  met in real play, every one clean (F-018).
- **Capture library rebuilt once**: `parallel.py build` (below-normal, one build), 280.7 s, peak 75.5 MB;
  `build.py --check-fresh` **FRESH** (25 staged files, built 2026-11-13T06:06:34). Before it: STALE
  (targets.csv changed by the menus batch).
- **Live shadow compare** (`parallel.py runs --mode capture --session i7-cap`, 18 runs, at most 12 at
  once, below-normal, 06:11-06:26, peak 369.7 MB per real-play run, 779.8 MB per staged cheat run).
  Every run PASS; `parallel.py`, which FAILs a capture run on any bad record (robot A1), printed PASS
  for both tables. Memory hashes equal to earlier runs: bt-prologue a3e4ec17, bt-ch2 059736d3, bt-ch3
  98dc9c69, bt-ch4 18ca52e0, bt-ch5 cb875c8b, bt-ch6-castle e0758406, bt-castle-shop fd292276, bt-ch7
  4376a256, bt-ch8-support ce8e57f0, bt-ch8-pair 047fe571, bt-ch8 bee8415f, bt-castle-forge d6f814c6,
  bt-ch9 eb41cae1, bt-ch9-ore 25a4d7e8; cheat-forge-katana 3188fff1, cheat-skill-proc 371db3a3,
  cheat-family bb5ef48f, cheat-katana-reload 47d34f0d (robot round 6's hashes).
  - **Real play (bt-*, 14 runs): 92 of 110 overrides met, 16,952 records: 16,547 match, 282 gave up
    (the original ran), 123 incomplete, 0 `mismatch_r0`, 0 `mismatch_regs`, 0 `mismatch_mem`, 0
    `mismatch_calls`, 0 `b_escaped`, 0 unfaithful, 0 escaped, 0 damaged.** Records per route:
    bt-prologue 1,221, bt-ch2 1,208, bt-ch3 1,390, bt-ch4 1,393, bt-ch5 1,345, bt-ch6-castle 985,
    bt-castle-shop 469, bt-ch7 1,622, bt-ch8-support 479, bt-ch8-pair 1,166, bt-ch8 1,530,
    bt-castle-forge 397, bt-ch9 1,873, bt-ch9-ore 1,874.
  - **Cheat track (cheat-*, 4 runs, scored apart, F-019): 62 overrides met, 3,597 records: 3,484 match,
    57 gave up, 56 incomplete, 0 bad of any kind.** Records: cheat-skill-proc 1,185, cheat-family
    1,390, cheat-forge-katana 768, cheat-katana-reload 254. Stage summaries included; the totals
    agree with a separate count over every `results/<run>.*summary.tsv` (build/integrate6/agg.txt).
- **Menu overrides in real play: 8 of 16 met, all 0 mismatch.** Records (match / gave up / incomplete):
  `danger_panel_is_hide` 282 (282, 12 routes), `config_info_capability` 251 (251, all 14),
  `config_is_speed_fast` 239 (239), `config_is_skip_input` 222 (222), `unit_is_detail_battle_must`
  168 (157/11), `unit_is_detail_battle_not_allow` 168 (157/11), `config_is_detail_battle` 133
  (121/11/1), `config_is_detail_support` 47 (40/7). The four tier-2 GAVE-UP ones
  (`config_is_detail_battle`, `config_is_detail_support`, both Unit detail-battle checks) now have
  live evidence. Not met: the eight option items' GetValue readers (`config_danger_value`,
  `config_hp_gauge_value`, `config_battle_value`, `config_game_speed_value`, `config_ai_skip_value`,
  `config_distance_value`, `config_encounter_bgm_value`, `config_item_value`): no route opens the
  options screen.
- **Never met before, now met only on the cheat track (4), all 0 mismatch:** `unit_equipped_skill_count`
  12 (12 match, cheat-skill-proc), `family_grow` 8 (8, cheat-family), `family_limit` 25 (25,
  cheat-family), `unit_lethality_immune` 1 (**gave up: met, but no verdict**, cheat-skill-proc). These
  count as "met on a cheat route", not as met in play (F-019).
- **Overrides never met on either track (14):** the 8 option GetValue readers, `skill_total`,
  `script_unit_has_skill`, `family_parent_grow` (cannot be recorded), `unit_attack_for_terrain`,
  `unit_attack_for_terrain_of_slot` (breakable terrain), `script_unit_can_dragon_vein` (Revelation
  scripts and X015 only). Of the 10 never met after round 5, 6 are still never met and 4 are met on
  the cheat track only.
- **Checks.** New `check_all` rows: `menu-diff` (medium: `menu_diff.py --plant`, 41 planted bugs; fails
  at 90 or more early give-ups of a function's 300), `menu-diff-long` (slow: `-n 1500 --seed 7`,
  fails at 450 of 1500), `cheats-selftest` (`cheats.py --selftest`), `cheat-routes` (`cheats.py
  --check`: the cheat routes' rules and every packed real-play start save). `skill-diff` text now
  says 34 planted bugs; the `parallel-tests` text names the capture-fail verdict and the cheat-save
  refusals (CaptureVerdictTests and LaunderTests live in that file, so no separate row);
  `markers-selftest` text names the forge ranks and repeated ids. Samples: harness-selftest 79/79,
  markers 28/28, levelups 3/3, parallel-tests 34, skill-diff 34/34, and the four new rows;
  `tests/test_check_all.py` 46 tests OK. `python tools/check_all.py` (06:27-06:57, below-normal) **PASS (45 pass, 15 skip: the 14 slow rows and `gen-headers`)**: `menu-diff` 6,600 cases, 0 mismatches, 41/41; `skill-diff` 5,100, 34/34; `growth-diff` 7,800, 37/37; `formula-diff` 6,900, 31/31; `cheats-selftest` 23/23; `cheat-routes` 14 real-play start saves checked, 4 cheat routes; `parallel-tests` 34 tests; `harness-selftest` 79/79; `markers-selftest` 28/28; `harness-levelups` 3/3. `python tools/check_all.py --slow` (06:57-08:00, below-normal, FEF_ROBOT_JOBS=12) **PASS (59 pass, 1 skip: `gen-headers`)**: `menu-diff-long` 33,000 cases, 0 mismatches; `skill-diff-long` 25,500, 0; `readable-verify` OK over 110 (48 ABI-ONLY, 12 CLEAN, 45 GAVE-UP, 5 UNSAMPLED, 0 MISMATCH); `parallel-smoke` DETERMINISTIC c3cbbe48 (7.9 s side by side, 17.5 s one after another); `assets-full` 21,880/21,880.
- **Reworded here:** the two 2026-11-13 integrate sections above no longer present the boot.log grep as
  evidence (its `[fe-capture]` lines are capped; the verdict is the summary.tsv). The same wording in
  docs/REPORT_2026-11-13.md is not this stage's file and is left as written.
- **%APPDATA% / %LOCALAPPDATA%** (zakuro, 3dsrecomp, Citra, azahar, lime3ds / zakuro, 3dsrecomp,
  Citra), every entry's path, size and modification time: 54,168 entries listed before the library build (06:06) and after the capture runs and both check_all runs (08:01), identical (build/integrate6/appdata_before.txt, appdata_after.txt). parallel.py's own check said "unchanged" for i7-cap.
- **Open.** `harness.py headless --mode capture` on a cheat route followed by `harness.py report` would
  merge cheat records into build/harness/report.json (no cheat filter; nothing mixed in today: the
  nine cheat runs in build/harness/runs are original mode without a summary.tsv; F-019 "Known gap");
  a capture run of a route that meets no override (title) FAILs by design (ROBOT.md 4), so a
  capture-mode smoke test on title would always fail; the menus test's two weak spots (a `!= 0` for
  `== 1` in `option_says_picture` case 2 caught only at 1,000 cases; an `(int16_t)` cut of the
  EncountBGM count never caught); no route opens the options screen, presses X for the danger zone or
  fights with battle animations switched; B-c, B-e; H5/H6; the writer-callee list; the writers stay
  off (F-017). `config_item_value` is UNSAMPLED in tier 2 and not met live: only the host test covers
  it.

## Status update 2026-11-13 (integrate, daytime round 7): the options route, H5/H6, the writer gate and the options wiring design, checked together

**In plain words.** Three stages joined. The robot (round 7) got a route that opens the game's own
options screen, looks at every line and leaves without changing anything, and it ran the deeper
checks H5 (how much of the readable code real play runs) and H6 (would the records notice a planted
bug). The writers stage built the safety net for code that *changes* the game (a gate and an undo
log) and the first writer, for the options block, kept **off** (F-021). The wiring stage fixed the
design of how the PC options page would reach the game (docs/OPTIONS_WIRING.md, design only). The
join rebuilt the capture library once, with the writer files compiled in and off, and replayed **all
15 Birthright routes and all 4 cheat routes** with every override watched: real play **100 of 110
met, 17,818 records**; cheat track 62 met, 3,597 records; **0 mismatch records of any kind on either
track**; every route ended in the same memory as before. H6 is **not** at its gate (47.5% caught,
gate 90%), so the writers stay off. Plan total 50.9% -> 51.5% (robot ~72% -> ~74%, readable ~16% ->
~17%, options ~13% -> ~15%; all three [low]). Owner report: docs/REPORT_2026-11-14.md, section
"Round 7 (daytime 2026-11-13)". Daytime budget: FEF_ROBOT_JOBS=6, FEF_ROBOT_MEM_GB=8, below-normal,
every robot run and the build through `parallel.py`; host tests and check_all through a below-normal
wrapper (build/integrate7/low.py).

- **Step 8, test robot (~72% -> ~74%)** [low for the percentage, high for the facts]. Robot round 7
  (docs/ROBOT.md, docs/harness/H56.md): route `bt-ch8-options` (6,900 frames from bt-ch8-support:
  system menu > Options, all 25 lines walked with DOWN only, left with B; then the Units list's
  Battle page and back to page 1); new marker `state.game_config` (the 19 saved option bytes of
  GameConfigData) identical at all 11 checkpoints; two marker runs end at memory `7e5ff849...`. A
  control run of the same length without the visit: same instruction count; GameUserData,
  GameConfigData and all 24 units byte-equal; the whole-memory hash differs because any system-menu
  visit advances the general random at 0x00752B7C (fight random 0x00752B8C unchanged), and after the
  next enemy phase two enemy units stood elsewhere [med: the probe savestates were deleted]. H5/H6
  on kept records (`parallel.py runs --mode capture --only all --store-keep`, `tools/harness/h56.py`):
  real play 100 of 110 met, own-body branches 330/549 (60.1%), with callees 1,214/2,564 (47.3%),
  offline verdict = live on all 17,818 records, original vs original clean on 15/15; H6 865/1,822
  caught (47.5%; 20 mutants did not compile; survivors 578 value gaps, 352 test gaps, 27 harmless),
  cheat track apart 522/1,254 (41.6%). **H6 gate (90%) not met.** Markers self-test 31/31, h56
  self-test 15/15, parallel tests 36.
- **Step 9, readable rewrite (~16% -> ~17%)** [low]. The 8 option-item GetValue readers are met in
  real play for the first time (all match), so 100 of 110 overrides are now clean in real play
  (F-018). The writer gate and undo log (`src/readable/core/fe_writer.h`, `writer.c`) and the first
  writer `config_write_options` (`src/readable/menu/menu_config_writer.c`), both OFF (F-021):
  `writer_gate_test.py` 244/244, 17/17 planted bugs; `writer_diff.py` 0 mismatches in 600 and 3,000
  cases, 25/25 planted bugs.
- **Step 10, options (~13% -> ~15%)** [low]. All 16 menu readers are now clean where met (the 8
  option items only with this save's single value each). The first options writer exists and is off.
  docs/OPTIONS_WIRING.md (wiring stage) reads every caller of GameConfigData's Reset, Deserialize and
  Serialize from the code and designs hooks W1 (apply on load, only on the global block, never inside
  a Serialize) and W2 (save guard: the save keeps the game's own value), plus Zakuro patch 0002
  (option lines on the PC page). Design and patch files only: nothing built, nothing hooked.
- **Capture library rebuilt once**: before, `build.py --check-fresh` STALE (core__writer.c,
  menu__menu_config_writer.c changed since the 08:10 build). `parallel.py build` (below-normal, one
  build) 291.2 s, peak 75.0 MB; then **FRESH** (27 staged files, built 2026-11-13T16:12:08).
- **No writer can have stored anything in these runs** [high for the facts listed]. Nothing in the
  staged sources calls a writer (`fe_writer_*` and `config_write_options` appear only in
  core__writer.c and menu__menu_config_writer.c); the DLL holds the writer symbols but not the string
  `FE_WRITERS` (`FE_READABLE` is there 3 times): with every `armed` a const 0, the compiler removed the
  switch's environment read, so no setting can turn a writer on in this library. The undo-log and
  refusal counters are not printed by the capture runtime, so "log empty, counters 0" is shown by the
  missing call path, not read from the live process; every memory hash below equals the runs made
  before writer.c existed.
- **Live shadow compare** (`parallel.py runs --mode capture --session i8-cap`, 19 runs, at most 6 at
  once, below-normal, 16:17-16:34, 998.6 s wall, peak 369.4 MB per real-play run, 780.1 MB per
  staged cheat run). Every run PASS (the capture FAIL rule of round 6 included). Memory hashes equal to
  earlier runs: bt-prologue a3e4ec17, bt-ch2 059736d3, bt-ch3 98dc9c69, bt-ch4 18ca52e0, bt-ch5
  cb875c8b, bt-ch6-castle e0758406, bt-castle-shop fd292276, bt-ch7 4376a256, bt-ch8-support ce8e57f0,
  bt-ch8-pair 047fe571, **bt-ch8-options 7e5ff849** (robot round 7's), bt-ch8 bee8415f, bt-castle-forge
  d6f814c6, bt-ch9 eb41cae1, bt-ch9-ore 25a4d7e8; cheat-forge-katana 3188fff1, cheat-skill-proc
  371db3a3, cheat-family bb5ef48f, cheat-katana-reload 47d34f0d.
  - **Real play (bt-*, 15 runs): 100 of 110 overrides met, 17,818 records: 17,394 match, 293 gave up,
    131 incomplete, 0 `mismatch_r0`, 0 `mismatch_regs`, 0 `mismatch_mem`, 0 `mismatch_calls`, 0
    `b_escaped`, 0 unfaithful, 0 escaped, 0 damaged.** bt-ch8-options: 40 overrides, 866 records (847
    match, 11 gave up, 8 incomplete). The other 14 routes give exactly round 6's record counts.
  - **Cheat track (cheat-*, 4 runs, scored apart, F-019): 62 met, 3,597 records: 3,484 match, 57 gave
    up, 56 incomplete, 0 bad of any kind.** Totals agree with a separate count over every
    `results/<run>.*summary.tsv` (build/integrate7/agg.txt).
- **Never met before, now met in real play (8), all match:** `config_item_value` 24, `config_battle_value`
  21, `config_game_speed_value` 21, `config_hp_gauge_value` 20, `config_distance_value` 20,
  `config_danger_value` 19, `config_ai_skip_value` 19, `config_encounter_bgm_value` 18 (all on
  bt-ch8-options only). The four Units-list slot forms (`unit_attack_of_slot` 77, `unit_hit_of_slot` 77,
  `unit_crit_of_slot` 77, `unit_avoid_of_slot` 79) are now met on 3 routes (bt-ch8-options added to
  the two Chapter 9 routes), 0 bad.
- **Still met only on the cheat track (4):** `unit_equipped_skill_count` 12, `family_grow` 8,
  `family_limit` 25, `unit_lethality_immune` 1 (gave up: no verdict).
- **Never met on either track (6, was 14):** `skill_total`, `script_unit_has_skill`,
  `family_parent_grow` (cannot be recorded), `unit_attack_for_terrain`,
  `unit_attack_for_terrain_of_slot` (breakable terrain), `script_unit_can_dragon_vein` (Revelation
  scripts and X015 only).
- **Checks.** New `check_all` rows: `writer-gate` (medium: `writer_gate_test.py --plant`, 17 planted
  bugs), `writer-diff` (medium: `writer_diff.py --plant`, 25 planted bugs; at least one case that
  stored and one that rebuilt the danger zone required), `writer-diff-long` (slow: `-n 3000 --seed 7`),
  `h56-selftest` (fast: `h56.py --selftest`), `h56-h5` (slow: H5 offline on the kept r7-h5 records,
  original vs original clean, offline = live, 0 bad; skips when the records are gone; it rewrites
  build/harness/h56/play/h5.json). H6 is not a row: 45 minutes, and its rate is a measurement against
  the F-017/F-021 gate, not a pass/fail. Texts updated: `markers-selftest` (option bytes),
  `parallel-tests` (`--store-keep`). `tests/test_check_all.py` samples for the five new rows; 46 tests OK.
  `python tools/check_all.py` (16:34-17:11, below-normal) **PASS (48 pass, 17 skip: the 16 slow rows and `gen-headers`)**: `writer-gate` 17/17 planted bugs, source checks clean; `writer-diff` 600 cases, 0 mismatches, 25/25; `h56-selftest` 15/15; `markers-selftest` 31/31; `parallel-tests` 36 tests; `cheat-routes` 15 real-play start saves checked, 4 cheat routes; `menu-diff` 6,600 cases, 41/41; `selftest` 46 tests. `python tools/check_all.py --slow` (17:11-18:32, below-normal, FEF_ROBOT_JOBS=6) **PASS (64 pass, 1 skip: `gen-headers`)**: `writer-diff-long` 3,000 cases, 0 mismatches; `h56-h5` 100 of 110 met, 17,818 records, offline = live, 0 bad (6 min 40 s); `menu-diff-long` 33,000 cases, 0; `readable-verify` OK over 110 (48 ABI-ONLY, 12 CLEAN, 45 GAVE-UP, 5 UNSAMPLED, 0 MISMATCH); `parallel-smoke` DETERMINISTIC c3cbbe48 (9.9 s side by side, 18.9 s one after another); `assets-full` 21,880/21,880.
- **%APPDATA% / %LOCALAPPDATA%** (zakuro, 3dsrecomp, Citra, azahar, lime3ds / zakuro, 3dsrecomp, Citra), every entry's path, size and modification time: 54,168 entries listed before the library build (16:11) and after the capture runs and both check_all runs (18:32), identical (build/integrate7/appdata_before.txt, appdata_after.txt). parallel.py's own check said "unchanged" for i8-cap. No save was written outside build/.
- **Open.** H6 below its gate (47.5% / 41.6%); no survivor hand-reviewed as equivalent. No writer H6:
  needs a Fates docs/tracks/HOOK_LIST.md and a `writer` kind in `config/harness/targets.csv` /
  `tools/harness/gen_stubs.py` (only `override` and `probe` exist; a probe row would be built and
  run, so it is not OFF); the four setter rows in config/readable/functions.csv are kind `helper` with
  "WRITER, OFF" in the evidence, because `tools/readable/check.py` knows no `writer` kind, so the rule
  "a writer never has an override marker" is documented, not checked. The options route is look-only,
  so each option item has one value (`config_ai_skip_value` and `config_distance_value` caught 0 of
  their planted bugs). Any system-menu visit moves the general random 0x00752B7C; which code draws from
  it is not traced. `h56.py` takes only `--label play|cheat`, so a rerun replaces the last h5/h6 files;
  its replay builds compile every .c under src/readable (another stage's untracked files included).
  The writer gate's `FE_READABLE=readable` is one mode for every override: a play build with a writer
  on would also switch the 110 readers to their readable answers (OPTIONS_WIRING open issue). The
  harness's headless.py and recapture.py do not yet drop `FE_OPTIONS`/`FEF_OPTIONS` (PLAY's capture
  path does); no effect while nothing reads them. OPTIONS_WIRING section 5 promises a help line about
  save states that patch 0002 does not contain (wiring review). Still open from before: B-c, B-e, the
  writer-callee list.

## Status update 2026-11-14 (integrate, night round 8): all three routes, the options-changing route, the writer counters and the status-sheet readers, checked together

**In plain words.** Four stages joined. The owner said on 2026-11-13 evening to play all three
routes (F-022), so the robot now plays Birthright, Conquest and Revelation side by side: Conquest and
Revelation branch from the Birthright chapter-5 save (made before the route choice) and both cleared
chapter 6; Birthright cleared chapters 10 and 11. The writer-prep stage made the robot change the
game's own options on its screen and reload them from a save, taught the tools a `writer` kind, and
made every capture run count what the writer gate did. The readers stage added 19 status-sheet
readers (defence, resistance, maximum HP, move, equipped item, ...). The join rebuilt the capture
library once and replayed **all 21 real-play routes and all 4 cheat routes** with all 129 overrides
watched: real play **117 of 129 met, 31,334 records, 0 mismatch records of any kind**; cheat track
77 met, 4,807 records, 0 bad; **no writer stored anything** (read from the new counters in every run);
every route ended in the same memory as before. H6 is still **below its gate** (49.6% of planted bugs caught, gate 90%), so
the writers stay off. Plan total 51.5% -> 52.1% (robot ~74% -> ~77%, readable ~17% -> ~18%, options
~15% -> ~16%; all three [low]). Owner report: docs/REPORT_2026-11-14.md, section "Round 8
(evening/night 2026-11-13)". Night budget: FEF_ROBOT_JOBS=12, FEF_ROBOT_MEM_GB=8, below-normal.

- **Step 8, test robot (~74% -> ~77%)** [low for the percentage, high for the facts]. New real-play
  routes, each replayed twice to the same memory by its stage and once more here: `cq-ch6` (Conquest
  chapter 6, 37,790 frames from bt-ch5-clear, memory 73534534; "at most 1 enemy left", Ryoma left
  alone, stage complete units [3,1,0]); `rv-ch6` (Revelation chapter 6, 27,740 frames from
  bt-ch5-clear, memory 6f54e4cd; the chapter ends through its own event after the turn-2 enemy phase);
  `bt-ch10` (Ninja Village, rout, 17 turns, 129,000 frames, memory 8008b04b); `bt-ch11` (To the Sea,
  ship map, rout, 17 turns, 141,000 frames, memory d886b7b1; Reina recruited by Corrin's talk; five
  units retreated, Casual); `opt-ch8-set` (options changed on the game's own screen, then a battle save;
  memory 9164c56a) and `opt-ch8-reload` (that save reloaded: the options block equals the set block;
  memory 3c3489bb). New packed saves cq-ch6-clear, rv-ch6-clear, bt-ch10-clear, bt-ch11-clear,
  opt-ch8-set. Proof of the branch: route byte 1 / 2 in the marker reads (cq-ch6 frame 13055 units
  [6,5,0]; rv-ch6 frame 12959 units [3,14,0]) and B006 / C006 person ids in look-ahead board dumps; no
  marker reads the chapter id yet. Chapter 7 is started on both new routes (not cleared); chapter 12
  started on Birthright (not cleared). docs/ROUTES_SPLIT.md, docs/ROBOT.md section 3e,
  docs/harness/OPT_ROUTES.md.
- **Step 9, readable rewrite (~17% -> ~18%)** [low]. 19 status-sheet readers (src/readable/sheet/,
  docs/SHEET.md): 129 overrides. Host diff 5,700 and 28,500 cases, 0 mismatches, 40/40 planted bugs
  (rerun here: 5,700 / 0 / 40/40). 17 of the 19 met in real play on this first run, all match (e.g.
  `unit_max_hp` 608 records, `unit_is_unique` 536, `unit_is_invisible` 512, `unit_defense` and
  `unit_resistance` 496 each); not met: `unit_can_be_captured` (Conquest capture, later chapters) and
  `unit_equipped_item_mutable`. Fixed here, before the live compare: `forecast_strikes`
  (src/readable/battle/formula_forecast.c) now asks GetRangeI's one-time cache 0x006D9898 before its
  guest call, since that call now reaches the readable `unit_range_min` (readers' finding); formula
  diff 6,900 cases, 0 mismatches, 31/31 planted bugs. The tier-2 classifier (tools/readable/check.py)
  learned the two shadow-pass fault-count shapes the sheet batch found (a nested override's reads
  counted twice: bound 4A instead of 3A; a callee's one-time cache filled by the original first:
  A < B < 2A), each with selftest cases (58 verdict combinations); on the readers' own tier-2 output
  `unit_equipped_item`, `unit_equipped_item_mutable` and `unit_is_special_battle` now read ABI-ONLY.
- **Step 10, options (~15% -> ~16%)** [low]. The options are now changed through the game's own screen
  in real play (opt-ch8-set) and survive a save and reload (opt-ch8-reload); H5 on those records saw
  2-4 distinct values for each option reader (round 7: one each). A `writer` kind in the registry,
  targets.csv, gen_stubs.py and check.py (a writer never has an override marker; never stubbed, never
  probed); robot children never get FE_OPTIONS / FEF_OPTIONS. Nothing is built into the engine or
  hooked.
- **Capture library rebuilt once**: before, `build.py --check-fresh` STALE (targets.csv changed).
  The first `parallel.py build` compiled but could not link: another agent's look-ahead boot.exe held
  build/harness/lib's DLL open (357 s lost). Built again into build/harness/lib8 (`parallel.py build --
  --out build/harness/lib8`, below-normal, 362 s, peak 76 MB), the old DLL renamed aside and the new DLL
  and manifest copied in: **FRESH** (29 staged files, built 2026-11-14T00:47:58, sha256 944018045cc3dc7b).
  The DLL holds the `fe_writer_*` symbols and not the string `FE_WRITERS`; every writer's `armed` is 0.
- **Writers stored nothing, read from the live runs** [high]. Every capture summary now carries the
  writer gate's totals (prep). All 25 runs report them: log 0, stores 0, restored 0, sessions 0,
  refusals 0, mode refusals 0, stray 0, dropped 0 (parallel.py verdict "no writer stored anything" on
  r8-cap, r8-capL and r8-capc).
- **Live shadow compare** (`parallel.py runs --mode capture --only all --store-keep --markers
  --longest-first --capture-jobs 12`, below-normal). Session r8-cap (21 real-play routes, at most 12 at
  once, 1,029 s wall): 15 PASS; the six longest (bt-ch7, bt-ch8, bt-ch9, bt-ch9-ore, bt-ch10, bt-ch11)
  hit the default 900 s run timeout with 12 runs and other agents' look-aheads sharing the PC (0 bad
  records in what they had captured; their partial record folders were deleted). Rerun as r8-capL with
  `--timeout 3600` (6 at once, 1,309 s wall): 6 PASS. Session r8-capc (4 cheat routes, 51 s): 4 PASS.
  Every PASS run met all its checkpoints. Memory hashes equal to earlier runs: bt-prologue a3e4ec17,
  bt-ch2 059736d3, bt-ch3 98dc9c69, bt-ch4 18ca52e0, bt-ch5 cb875c8b, bt-ch6-castle e0758406,
  bt-castle-shop fd292276, bt-ch7 4376a256, bt-ch8-support ce8e57f0, bt-ch8-pair 047fe571,
  bt-ch8-options 7e5ff849, bt-ch8 bee8415f, bt-castle-forge d6f814c6, bt-ch9 eb41cae1, bt-ch9-ore
  25a4d7e8, bt-ch10 8008b04b, bt-ch11 d886b7b1, cq-ch6 73534534, rv-ch6 6f54e4cd, opt-ch8-set 9164c56a,
  opt-ch8-reload 3c3489bb; cheat-forge-katana 3188fff1, cheat-skill-proc 371db3a3, cheat-family
  bb5ef48f, cheat-katana-reload 47d34f0d.
  - **Real play (21 runs): 117 of 129 overrides met, 31,334 records: 30,503 match, 518 gave up, 313
    incomplete, 0 `mismatch_r0`, 0 `mismatch_mem`, 0 `mismatch_calls`, 0 `b_escaped`, 0 unfaithful, 0
    escaped.** By family: Birthright (17 runs) 117 met, 26,859 records; Conquest (cq-ch6) 87 met, 1,628
    records; Revelation (rv-ch6) 89 met, 1,618 records; options routes (2) 38 met, 1,229 records; 0 bad
    in each.
  - **Cheat track (4 runs, scored apart, F-019): 77 met, 4,807 records: 4,670 match, 77 gave up, 60
    incomplete, 0 bad of any kind.** Totals re-counted from every `results/<run>*.summary.tsv`
    (stage files included) by build/integrate8/agg.py; per-override table build/integrate8/per_override.tsv.
- **Never met before, now met:** 17 of the 19 new sheet readers (above), all match. Of the 110 older
  overrides the picture is unchanged: 100 met in real play, 4 only on the cheat track
  (`unit_equipped_skill_count`, `family_grow`, `family_limit`, `unit_lethality_immune`), and **never met
  on either track (8, was 6):** `skill_total`, `script_unit_has_skill`, `family_parent_grow`,
  `unit_attack_for_terrain`, `unit_attack_for_terrain_of_slot`, `script_unit_can_dragon_vein`, and the
  new `unit_can_be_captured`, `unit_equipped_item_mutable`. Neither Conquest 6 nor Revelation 6 met a
  reader that Birthright never met.
- **H5/H6 on the kept records** (`tools/harness/h56.py`, prep's faster H6 with source files side by
  side). Real play (r8-cap + r8-capL, label `play`): H5 117 of 129 met, 31,334 records, original vs
  original clean on 21/21, offline = live on every record, own-body branches 413/687 (60.1%), with
  callees 1,409/2,842 (49.6%) (1,104 s). H6: 1,106/2,228 planted bugs caught (**49.6%**; round 7 47.5% on fewer records and overrides) over 115 overrides in 20 source files, 24 stillborn, no harness problem (11,487 s at 8 jobs, beside check_all; prep's side-by-side H6). Lowest: stance_gauge.c 3/12, skill_battle.c 24/81, menu_config.c 85/220, growth_exp.c 126/318; highest: forces.c 42/46, flags.c 9/10, menu_danger.c 4/4. The new sheet files: sheet_unit.c 87/149 (58.4%), sheet_stats.c 119/256 (46.5%). Cheat track apart (r8-capc, label `cheat-r8`):
  H5 77 met, 4,807 records, 0 bad, branches 312/609 (51.2%); H6 692/1,648 caught (42.0%; 21 stillborn;
  1,111 s at 6 jobs). **The 90% gate is not met; writers stay off.**
- **Checks.** New `check_all` rows: `sheet-diff` (medium, 40 planted bugs) and `sheet-diff-long` (slow);
  `gen-stubs-selftest` and `gen-stubs-check` (fast: the writer kind, guard tags; the 19 new rows needed
  7 guard tags, found by `--check`); `robot-routes` (fast, in-process: every verified bt-/cq-/rv-/opt-
  route has checkpoints, Conquest reads route byte 1 and Revelation 2, both branches start from
  bt-ch5-clear, start saves and round 8's packs exist); `mutate-writer-fake` (medium: the writer-callee
  plumbing on fakelib, 26/26); `evidence-selftest` (fast). Changed: `writer-gate` text (19 planted bugs,
  the run totals); `h56-h5` now replays round 8's records (sessions r8-cap,r8-capL) under label `check`,
  so the integrate's `play` results are not overwritten. `tests/test_check_all.py`: samples for the six
  new command rows, a `RobotRoutes` class (6 planted problems), 66 tests OK. `python tools/check_all.py --slow --jobs 4` (01:46-03:10, below-normal, beside H6): 69 pass, 2 fail, 1 skip (`gen-headers`). The two failures, fixed and rerun alone: `writer-diff` (planted bug 24's text was stale: prep added `fe_writer_publish()` to the stray-store path of writer.c; the plant in src/readable/menu/tests/writer_diff.py now carries that line; rerun **PASS**, 600 cases, 0 mismatches, 25/25) and `h56-h5` (timed out at 60 min while H6 ran beside it; timeout raised to 2 h; rerun **PASS**, 117 of 129 met, 31,334 records, 30 min 26 s). So every row of the slow set has passed on today's tree: `readable-verify` OK over all 129 (58 ABI-ONLY, 13 CLEAN, 53 GAVE-UP, 5 UNSAMPLED, 0 MISMATCH), `sheet-diff` 5,700 cases 40/40, `sheet-diff-long` 28,500 cases, `writer-gate` 19/19, `mutate-writer-fake` 26/26, `robot-routes` 0 problems, `parallel-smoke` DETERMINISTIC, `headless-selftest` 64/64, `h56-selftest` 30/30, `parallel-tests` 41 tests, `selftest` 66 tests. `python tools/check_all.py --jobs 4` (03:42-04:32): **PASS (54 pass, 18 skip: the 17 slow rows and `gen-headers`)**.
- **%APPDATA% / %LOCALAPPDATA%** (zakuro, 3dsrecomp, Citra, azahar, lime3ds): every entry's path, size and modification time listed at 00:47 (before the library build) and at 05:01 (after the capture runs, H5/H6 and every check_all run): 52,086 entries, identical (build/integrate8/appdata_before.txt, appdata_after.txt). parallel.py's own check said "unchanged" for r8-cap, r8-capL and r8-capc. No save was written outside build/.
- **Evidence and clean-up.** `tools/evidence/evidence.py pack` (every session; r8-cap 115 files, r8-capL 37, r8-capc 37; docs/evidence/INDEX.md), then `clean --yes --keep-sessions 10 --keep r8-cap --keep r8-capL --keep r8-capc` (the newest 10 kept so other agents' sessions of tonight stay; r7-h5 and r7-h5c went, since `h56-h5` now reads round 8's records): 1.05 GB freed (48 items), plus this integrate's own duplicate build folder build/harness/lib8 and the old DLL (0.65 GB): about 1.7 GB in all. No boot.exe was running.
- **Open.** H6 below its gate. Chapter 7 not cleared on Conquest or Revelation; chapters 12-14 not
  done on Birthright; no child unit yet (Kaze-Hana and Felicia-Saizo at B). No marker reads the chapter
  id. In bt-ch10 the markers read veins_used 2 with no player vein use (not traced). The six longest
  routes need a run timeout above 900 s when 12 runs share the PC. A rebuild cannot link while another
  agent's look-ahead holds build/harness/lib's DLL open, so it was built elsewhere and swapped by hand
  (a build.py option to do this would be safer). Not done here: a chapter-id marker read; per-area lock
  pools in budget.py (split's request); MENUS.md section 5's animation_skip row (its owner).

## Status update 2026-11-14 (integrate, round 9): the speed tools, Birthright 12, Conquest 8, Revelation 9, the fixes batch, checked together

**In plain words.** First round on the speed tools (F-023). Birthright cleared chapter 12 (`bt-ch12`),
Revelation chapter 9 (`rv-ch9`); the Conquest robot played chapter 8 but left before its proof, which
integrate did (two original copies equal, save packed; the route stays `verified: false` until the cq
area adds its checkpoints). The fixes area did the eight round-8 review fixes. Integrate rebuilt the
capture library once with the new `build.py --swap` and replayed **all 26 verified real-play routes live**
(every one, including cq-ch7, rv-ch7, rv-ch8 that round 8 missed; none offline): **118 of 129 met, 41,710
records, 0 bad of any kind**; cq-ch8 2,187 records 0 bad; cheat track 4,807 records 0 bad (apart, F-019);
no writer stored anything. H6 50.6% (gate 90%): writers stay off. Plan total 52.1% -> 52.6% (robot
~77% -> ~79% [low]; readable and options unchanged). Owner report: docs/REPORT_2026-11-14.md, "Round 9".

- **Library**: `build.py --check-fresh` was FRESH (no readable source changed this round); rebuilt anyway
  once with `build.py --swap` (built in build/harness/next, swapped in; 339 s build, 341 s wall, first real
  use of --swap against the real 3dsrecomp): FRESH, built 2026-11-14T09:31:58, 129 overrides, 5 writers
  never stubbed.
- **Live compare** (`parallel.py runs <26 routes> --mode capture --only all --store-keep --markers
  --longest-first --capture-jobs 10 --session r9-cap`, the new length-scaled default timeout, 2,552 s wall,
  no timeouts): 26 PASS, all checkpoints met, every memory hash as before / as the stage claimed.
  Per family: Birthright 18 runs 117 met 29,176 records; Conquest 2 runs (cq-ch6, cq-ch7) 93 met 3,524;
  Revelation 4 runs (rv-ch6..9) 101 met 7,781; options 2 runs 38 met 1,229; 0 bad in each.
  cq-ch8 (r9-capq, 1 run, 380 s): 99 met, 2,187 records, 0 bad, memory 6897aa6a = the two originals.
  Cheat (r9-capc, 4 runs, 45 s): 77 met, 4,807 records, 0 bad. Newly met in real play:
  `unit_equipped_skill_count` (cq/rv only). Never met in real play (11): family_grow, family_limit,
  family_parent_grow, script_unit_can_dragon_vein, script_unit_has_skill, skill_total,
  unit_attack_for_terrain, unit_attack_for_terrain_of_slot, unit_can_be_captured,
  unit_equipped_item_mutable, unit_lethality_immune (family_grow, family_limit, unit_lethality_immune met
  on the cheat track).
- **cq-ch8 proof** (session i9-cq8, 2 original copies, run one after the other by the pool): both exit 0,
  140,000 frames, memory 6897aa6ad14873c2; packed cq-ch8-clear.zip sha256 5151dbe5.
- **H5** (r9-cap, label play, 1,144 s): 118 of 129 met, 41,710 records, 0 bad, offline = live, own-body
  branches 421/691 (60.9%), with callees 1,421/2,846 (49.9%).
- **H6** (r9-cap, label play, 6 at once): `--no-cache` clean run 1,133/2,237 caught (**50.6%**; round 8 49.6%) over 116 overrides in 20 files, 24 stillborn, no problem, 7,975 s; then `--cache`: 20 hits, 0 misses, same 1,133/2,237, 8 s. Gate 90% not met.
- **check_all**: applied the fixes area's lane patch; new rows build-/fastlook-/splitcfg-/offline-/h6cache-/testcache-selftest; robot-routes requires rounds 8-9 packs; h56-h5 reads r9-cap; tests/test_check_all.py 67 tests OK. `check_all --slow --jobs auto` (2,254 s): 75 pass, 2 fail, 1 skip (gen-headers). Failures: `assets-portrait` (collided with assets-full's portrait stage in build/assets/portrait_test; fixed by giving assets-full the build:assets lock) and `h56-h5` (collided with the integrate's own H5 on r9-cap: both replay into the record folders). Rerun alone (1,207 s): both PASS (h56-h5 118 of 129 met, 41,710 records). **It never passed in one run**; every row has passed on today's tree.
- **Evidence**: `evidence.py pack` (28.0 MB total), `clean --yes --keep-sessions 10 --keep r9-cap --keep r9-capc --keep r9-capq --keep i9-cq8`: 1.15 GB freed (r8-cap, r8-capc and older sessions). %APPDATA% unchanged per parallel.py in every session.
- **Open**: H6 below gate; cq-ch8 checkpoints (cq area); bt-ch13-14, cq-ch9, rv-ch10 not started; fastlook
  verify times out on long chains (bt area); fastlook rollback replays the whole chain (rv area); the board
  cursor read is stale at a player phase start (bt area); OK A and OK B still open.

## Status update 2026-11-15 (integrate, round 10): fresh helper per chapter, Birthright 13-17, Revelation 10-14, Conquest 9, the items / movement / supports readers, checked together

**In plain words.** First round with a fresh helper per chapter (owner OK 2026-11-14) on the speed tools (F-023).
Birthright cleared chapters 13-17 and Revelation 10-14, each proven by its helper with two original copies and
packed. The Conquest helpers played chapter 9 to the end but never finished a proof; integrate did it (two original
copies equal, checkpoints written, save packed, `verified: true`). Three reader batches added 74 readers (items,
movement, supports): 203 overrides. The first live compare found one fault in a new reader (`cursor_terrain`, 866
call-list records); fixed, rebuilt, and **all 38 verified real-play routes replayed live again: 0 bad of any kind**.
Plan total 52.6% -> 53.7% (robot ~79% -> ~82%, readable ~18% -> ~22%, both [low]). Owner report:
docs/REPORT_2026-11-15.md.

- **Library**: `build.py --check-fresh` STALE (targets.csv: the three batches); `build.py --swap` 287 s, FRESH,
  203 overrides (50 guard users), 5 writers never stubbed. After the `cursor_terrain` fix, `--swap` again (451 s
  beside the robot runs), FRESH.
- **Live compare, first try** (`parallel.py runs <37 routes> --mode capture --only all --store-keep --markers
  --longest-first --capture-jobs 12 --timeout 5400 --session r10-cap`, 4,628 s, at most 11 at once): every run exit 0,
  every memory hash equal to round 9's or to its helper's claim, every checkpoint met, no writer stored anything;
  **866 bad records, all `mismatch_calls` in `cursor_terrain` (0x0039B7E4)**, 20-29 per route. Cause: an inlined
  tail branch into the `terrain_record` override (docs/MOVE.md 9). Fix in src/readable/move/move_terrain.c and
  move_diff.py (tail branch to an override unlisted; the planted bug moved to the new line): move_diff 7,200 cases
  0 mismatches 47/47, long 36,000 0 mismatches; readable-verify 0 MISMATCH.
- **Live compare after the fix** (same command, 38 routes with cq-ch9, `--session r10-capb`, 5,172 s, at most 11 at
  once, all live, none offline): **38 PASS, 179 of 203 met, 106,426 records (104,043 match, 1,498 gave up, 885
  incomplete), 0 bad of any kind**, every memory hash unchanged, every checkpoint met, %APPDATA% unchanged, no writer
  stored anything. Per family: Birthright 23 runs 172 met 63,500 records; Conquest 4 runs (cq-ch6..9) 155 met
  12,288; Revelation 9 runs (rv-ch6..14) 163 met 28,732; options 2 runs 60 met 1,906; 0 bad in each.
  Cheat track apart (`--session r10-capc`, 4 runs, 55 s): 128 met, 8,395 records, 0 bad.
  New readers met in real play: items 17 of 25, movement 21 of 24, supports 20 of 25. Newly met older readers:
  `script_unit_can_dragon_vein` (rv-ch12), `unit_attack_for_terrain`, `unit_attack_for_terrain_of_slot`.
  Never met in real play (24): family_grow, family_parent_grow, family_limit, skill_total, script_unit_has_skill,
  unit_lethality_immune, unit_equipped_item_mutable, unit_can_be_captured; script_terrain_out_of_play_area,
  script_terrain_has_flag, job_is_rider; item_try_record, item_kind_record, item_is_download, item_same_kind,
  item_is_consumable, item_sell_price, unit_can_cannon_item, unit_has_cannon_item; family_parent_record,
  family_parent_level, family_sibling_level, family_grandfather, family_grandmother (family_grow, family_limit,
  unit_lethality_immune, family_parent_record, family_parent_level met on the cheat track).
- **cq-ch9** (integrate): proof i10-cq9 (2 original copies, 123,500 frames, memory bf1c69255758cc0b in both, saves
  byte-identical), packed cq-ch9-clear.zip (sha256 6e6c5d99), 8 checkpoints from that proof (splitcfg.py), capture
  i10-cq9cap met them all (its 27 bad records were the `cursor_terrain` fault, before the fix), r10-capb met them
  again; `verified: true`. rv-ch10..14 `verified: true` (the rv helpers proved them but left the flag out).
- **H5** (r10-capb, label play, 4,240 s): 179 of 203 met, 106,426 records, 0 bad, offline = live, own-body branches
  659/1,091 (60.4%), with callees 1,893/3,742 (50.6%).
- **H6**: not measured this round. `h56.py h6 --sessions r10-capbh --label play --cache` started 05:08; the cache missed on every file (key changed: library and records), and with 2.5 times round 9's records each file took 5.4-6.6 h (6 of 28 files done after 7 h 38 min, projected ~12 h more). Stopped at the owner's request (2026-11-15 ~12:50, "yes, stop it and save", F-024); partial results not used. Last measured: 50.6% (round 9). Round 11: H6 on a sampled record set per function, weekly or near the gate.
- **check_all**: new rows item-/move-/support-diff and their -long rows (locks, cache specs, samples); robot-routes
  requires the round-10 packs and cq-ch9-clear; h56-h5 reads r10-capb; first KNOWN entry (`readable-verify`:
  item_sell_price NOT-RUN, strict regex). tests/test_check_all.py 70 tests OK. `check_all --slow --jobs auto --cache
  --skip h56-h5` (5,803 s, beside the live compare, mostly 1 lane): 80 pass, 2 fail, 2 skip (gen-headers; h56-h5
  skipped on purpose: its records did not exist yet). Failures: `move-diff` (the planted-bug line it edits changed
  under it while I fixed `cursor_terrain`) and `readable-verify` (the item batch's known NOT-RUN). Rerun of the
  changed rows: move-diff, move-diff-long, readable PASS; readable-verify KNOWN (0 MISMATCH over all 203);
  selftest PASS; robot-routes PASS (38 verified routes), cheat-routes PASS. h56-h5 (r10-capb): timed out twice (120 and 240 min) while H6 ran beside it on the same records; the direct `h56.py h5` run above (4,240 s) completed, 0 bad.
  **It never passed in one run**; every row has passed or is KNOWN on today's tree.
- **Evidence** (by Claude after the stop): `evidence.py pack` (57.6 MB total), `clean --yes --keep-sessions 10 --keep r10-capb --keep r10-capc --keep i10-cq9 --keep i10-cq9cap`: 2.79 GB freed; the stopped H6 scratch deleted. %APPDATA% unchanged per parallel.py in every session.
- **Open**: H6 below gate; item_sell_price never sampled by verify and never met live; Kaze left the Birthright army
  after chapter 15 (not a battle loss; story step not traced; docs/ROBOT.md round 10 integrate); fastlook serve
  rollback bug (bt-ch16 notes); Conquest 10 and later; OK A and OK B still open.

## Status update 2026-11-16 (integrate, round 11): Grok's strategy applied (F-025), Birthright 18-23, Conquest 10-12, Revelation 15-17, the AI permission and battle-number readers, checked together

**In plain words.** Round 11 played Birthright 18-23, Conquest 10-12 and Revelation 15-17; at 21:10 the owner said
"Apply now" to Grok's strategy (F-025, docs/collab/STRATEGY_R11_GROK.md): Conquest and Revelation paused (cq-ch13
and rv-ch18 left as unverified look-ahead chains), the two-copy proof its own step (bt-ch23, cq-ch11, cq-ch12 proven
that way), two green reader batches (AI permission 18, battle numbers 13), the AI attack-score batch parked, H6
survivor test sharpening, and unchanged routes replayed offline. Integrate rebuilt the library once and compared
**all 50 verified real-play routes: 166,411 records, 0 bad of any kind** (offline where the recordings still hold,
live for the new routes and the new readers). Plan total 53.7% -> 54.3% (robot ~82% -> ~84%, readable ~22% -> ~24%,
both [low]). Owner report: docs/REPORT_2026-11-16.md.

- **Library**: `build.py --check-fresh` STALE (targets.csv: the two batches, ai_score rows removed); `build.py --swap`
  303 s, FRESH (built 2026-11-15T23:34:34), 234 overrides (57 guard users), 43 staged readable files (none from
  ai_score), 5 writers never stubbed.
- **Which way each route went (offline.py plan --sessions r10-capb --label play --baseline-rev 0e8ddd7).** The 38
  routes with round-10 records: input, frames, saves, save_at, boot.exe and clock unchanged, so the records decide
  the 203 older overrides **offline**; the 31 new overrides (18 ai_*, 13 battle2) have no records, so they play
  **live** on those 38 routes. The 12 routes new this round have no records with this library: **live**, every
  override. (Without `--baseline-rev` the plan took the hooks from 9aa4ea6 and sent 105 overrides live; round 10's
  commit 0e8ddd7 is the targets.csv the r10-capb records ran with.)
  - Offline `offline.py replay --sessions r10-capb --label play --baseline-rev 0e8ddd7 --name r11-off --jobs 6`:
    source gate passed, 38 folders, **106,426 records (104,043 match, 1,498 gave up, 885 incomplete), 0 bad, offline
    verdict != captured verdict: 0**, 162 s. Cheat `r11-offc` (r10-capc, label cheat): 8,395 records, 0 bad, 59 s.
  - Live new routes `parallel.py runs <bt-ch18..23 cq-ch10..12 rv-ch15..17> --mode capture --only all --store-keep
    --markers --longest-first --capture-jobs 12 --timeout 5400 --session r11-capn` (FEF_ROBOT_JOBS=12): 12 PASS,
    2,705 s, 12 at once; **45,594 records (44,504 match, 675 gave up, 415 incomplete), 0 bad**; every memory hash
    equal to its proof's (bt-ch18 e8e88cf2, bt-ch19 316756a1, bt-ch20 9db6921f, bt-ch21 4d5972e4, bt-ch22 bc342d7d,
    bt-ch23 c3b90758, cq-ch10 875e0080, cq-ch11 52154ebf, cq-ch12 0dbf6a28, rv-ch15 8d54ceb7, rv-ch16 bfc9db06,
    rv-ch17 8b67f81a); every checkpoint met; writers stored nothing.
  - Live older routes, new overrides only (`--only <the 31> ... --session r11-capo`, FEF_ROBOT_JOBS=9 beside the tail
    of r11-capn): 38 PASS, 4,923 s, at most 9 at once; **14,391 records, 0 bad**; all 38 memory hashes equal to
    r10-capb's; every checkpoint met; writers stored nothing; %APPDATA% unchanged.
  - Cheat apart (`r11-capc`, the 31 new overrides on the 4 cheat routes): 543 records, 0 bad; memory = r10-capc.
  - **Per family, real play (offline + live):** Birthright 29 routes 197 met 95,034 records; Conquest 7 (cq-ch6..12)
    183 met 25,587; Revelation 12 (rv-ch6..17) 188 met 43,778; options 2 routes 65 met 2,012; **0 bad in each**.
    All: 50 routes, 166,411 records (162,469 match, 2,590 gave up, 1,352 incomplete), 205 of 234 met. Cheat track
    apart: 138 met, 8,938 records, 0 bad.
  - New readers met (26 of 31): every ai_* reader but ai_heal_condition_for_entrust, ai_heal_rod_permission,
    ai_move_power_slow; every battle2 reader but battle_dead_unit and enhance_has_rally_bonus. Biggest give-up
    share: ai_has_heal_rod 320 of 798 (its cold one-time cache; never a mismatch). Never met in real play (29):
    those 5 and family_grandfather, family_grandmother, family_grow, family_limit, family_parent_grow,
    family_parent_level, family_parent_record, family_sibling_level, item_is_consumable, item_is_download,
    item_kind_record, item_same_kind, item_sell_price, item_try_record, job_is_rider, script_terrain_has_flag,
    script_terrain_out_of_play_area, script_unit_has_skill, skill_total, unit_can_be_captured, unit_can_cannon_item,
    unit_equipped_item_mutable, unit_has_cannon_item, unit_lethality_immune (family_grow, family_limit,
    family_parent_level, family_parent_record, unit_lethality_immune met on the cheat track).
- **H5** (`h56.py h5 --sessions r10-capb,r11-capn,r11-capo --label play --run-id r11-h5b --no-exact`, 163 s): 88
  folders, original vs original clean on every one, **205 of 234 met, 166,411 records (162,469 match, 2,590 gave up,
  0 bad; offline != live: 0)**; aggregate lines 1,238/1,441, branches 855/1,346 (63.5%). The first try (run r11-h5,
  with the per-override exact cover) was stopped in the exact-cover pass on Grok's integrate review
  (docs/collab/INTEGRATE_SLOW_R11_GROK.md): **exact_cover deferred to weekly**; so the run is PARTIAL by the tool's
  rule and build/harness/h56/play/h5.json was not replaced.
- **H6: H6 sample deferred (F-024 weekly).** The sampled cache key holds the library's bytes (h6cache.py); the
  library was rebuilt tonight, so every file would miss (a cold run, about 42 min or more). Last measured: 51.1%
  sampled (N=64, r10-capb; h6-sharpen in this round, docs/harness/H6_SURVIVORS.md). Gate 90% not met: writers off.
- **check_all**: robot-routes requires the round 11 packs (bt-ch18..23, cq-ch10..12, rv-ch15..17; cq-ch13 and rv-ch18
  named as paused and left out); new rows ai-perm-diff(-long), battle2-diff(-long), battle2-shadow-count,
  ai-score-parked; row texts move-diff 48, item-diff 52, support-diff 56 planted bugs; h56-h5 reads
  r10-capb,r11-capn,r11-capo with --no-exact (exact cover weekly). tests/test_check_all.py 74 tests OK.
  `check_all --slow --jobs auto --cache --skip h56-h5` (8,301 s beside the live compare, 1 lane: the 12 robot runs
  held the budget): **88 pass, 1 known (readable-verify: item_sell_price NOT-RUN; 0 MISMATCH over all 234: 127
  ABI-ONLY, 15 CLEAN, 82 GAVE-UP, 9 UNSAMPLED), 2 skip (gen-headers; h56-h5 on purpose)**. Then `check_all --only
  h56-h5` alone: PASS (161 s, 205 of 234 met, 166,411 records). Every row has passed or is KNOWN on tonight's tree.
- **Measured.** Minutes per chapter, play / proof: bt-ch18 38 / 9 (+15 lost to a 900 s timeout), bt-ch19 71 / 10,
  bt-ch20 ~66 in all, bt-ch21 39 / 3, bt-ch22 62 / 9, bt-ch23 115 / 20 (proof its own step); cq-ch10 64 / 21,
  cq-ch11 88 / 18, cq-ch12 105 / 15; rv-ch15 85 / 13, rv-ch16 ~112 / 10, rv-ch17 ~110 in all [helpers' timings].
  Integrate 23:33 to about 03:15: build 5 min, offline 4 min, live 122 min (r11-capn 45 min; r11-capo 82 min,
  started at 00:20 beside r11-capn's last three runs), check_all 138 min beside it, H5 3 min (plus 30 min lost in the
  stopped exact-cover try). **Idle compute in the live window: 33% of 12 slots x 122 min** (the run script queued
  r11-capo behind r11-capn); check_all had 1 lane throughout.
- **Evidence**: `evidence.py pack` (90.0 MB total) and `clean --yes --keep-sessions 10` (7.12 GB freed, 49 items) keeping r10-capb, r10-capc, r11-capn,
  r11-capo, r11-capc, r11bt-23, r11bt-23cap, p11cq11, p11cq11cap, cq12p, cq12pcap (numbers in docs/evidence/INDEX.md).
- **Open**: H6 below gate (sample and exact cover weekly); 80 equivalent-mutant candidates for a person; 5 new readers
  never met; item_sell_price never sampled; Conquest/Revelation paused (cq-ch13, rv-ch18 unverified); next round
  should start the new-route and old-route live runs together; OK A and OK B still open.

## Status update 2026-11-17 (integrate, round 12): Birthright 24, the class-change and weapon-rank readers, Grok's integrate fixes, checked together

**In plain words.** Round 12 (owner "Start round 12"; F-023, F-024, F-025 in force) played Birthright 24 only (Conquest
and Revelation stay paused: cq-ch13 and rv-ch18 unverified, not played), proved it with two original copies as its own
step, added two green reader batches (class change and seals, 4 readers; weapon rank, 2 readers), each captured once
with the final library (Grok's round 12 fix), fanned H5 out into lanes and made the offline plan print both lines.
Integrate did not rebuild the library (FRESH) and compared **all 51 verified real-play routes: 172,499 records, 0 bad
of any kind**: 50 routes offline from their records, only bt-ch24 live. Plan total 54.3% -> 54.6% (robot ~84% ->
~85%, readable ~24% -> ~25%, both [low]). Owner report: docs/REPORT_2026-11-17.md.

- **Library**: `build.py --check-fresh` FRESH (built 2026-11-16T03:48:31 by the class-change capture step; 240
  overrides, 45 staged files, class_change and weapon_rank inside); not rebuilt. Every r12 capture (r12-cap-class_change,
  r12-capc-class_change, r12-cap-weapon_rank, r12-bt24-cap) and r12-capn ran on library sha256 475f58e96fd4...
- **Plan** (`offline.py plan --sessions r10-capb,r11-capn,r11-capo --extra-sessions "r12-cap-*" --label play
  --baseline-rev de846a6`; build/r12int/plan-play.txt):
  - PLAN LINE 1, routes: 50 replay offline from their records, 0 must play live (route changed).
  - PLAN LINE 2, overrides: 238 decided by the records (4 of them by the batch's own capture r12-cap-class_change on
    47 routes), 2 must play live (script_unit_weapon_rank, unit_weapon_exp_for_job_intro: "NEW: never captured").
    LIVE TOTAL as printed: 50 route runs for those 2.
  - Those 2 were not played on the 50 routes: r12-cap-weapon_rank (54 runs, this library) watched both (run.json
    `only`) and no summary.tsv names either, so no route calls them. offline.py cannot see a 0-record run (no
    records/ folder is kept), which is why it still prints them; tool gap open for the tools owner. "Live only on the
    routes that can reach it" is therefore none, plus bt-ch24 (every override), where they were not called either.
  - `--baseline-rev de846a6`: r11-capn/capo ran with de846a6's targets.csv; 0e8ddd7 -> de846a6 only added rows, so
    r10-capb's hooks are unchanged. Without it the plan used 9aa4ea6 and sent 107 overrides live.
  - Cheat (`--sessions r10-capc,r11-capc --extra-sessions "r12-capc-*" --label cheat`): 4 routes offline, the same 2
    left, also never called on the 4 cheat routes.
- **Offline**: `offline.py replay ... --name r12-off --jobs 4`: source gate passed, 135 folders, **168,591 records
  (164,642 match, 2,590 gave up, 1,359 incomplete), 0 bad, offline verdict != captured verdict: 0**, 219 s. Cheat
  `r12-offc`: 20 folders, 9,039 records (8,846 match), 0 bad, 46 s.
- **Live**: `parallel.py runs --route bt-ch24 --mode capture --only all --store-keep --markers --timeout 5400 --session
  r12-capn` (FEF_ROBOT_JOBS=12): PASS, 867 s; 176 met, **3,908 records (3,786 match, 49 gave up, 73 incomplete), 0
  bad**; memory 86af3d4985d54014 = the proof's; checkpoints all met; writers stored nothing; %APPDATA% unchanged.
  Only one live run existed, so "start all live runs together" was trivially met.
- **Per family, real play (offline + live):** Birthright 30 routes 201 met 100,122 records; Conquest 7 186 met
  25,975; Revelation 12 191 met 44,390; options 2 65 met 2,012; **0 bad in each**. All: 51 routes, 172,499 records
  (168,428 match, 2,639 gave up, 1,432 incomplete), 208 of 240 met. Cheat apart: 9,039 records, 0 bad.
- **New readers in real play:** battle_seal_effect 899 records (896 match, 3 incomplete), person_base_job_index 598
  (594 match), unit_reliance_blocks_class_change 735 (735 match; docs/CLASS_CHANGE.md expected it unmet: that note
  is wrong, left to the batch owner). Never called: class_change_type (no route spends a seal), script_unit_weapon_rank,
  unit_weapon_exp_for_job_intro. Never met in all: 32 of 240 (round 11's 29 plus those 3; bt-ch24's cannons did not
  reach unit_can_cannon_item or unit_has_cannon_item).
- **H5** (`h56.py h5 --sessions r10-capb,r11-capn,r11-capo,r12-cap-class_change,r12-capn --label play --run-id r12-h5
  --no-exact --jobs 8`): 136 folders in 8 lanes (tools-r12, verified ok), replay 84 s, gcov-tool merge 0.6 s, wall
  140 s; **208 of 240 met, 172,499 records, 0 bad, offline != live 0**; lines 1,269/1,475, branches 882/1,380 (63.9%).
  Exact cover stays weekly (PARTIAL by the tool's rule; play/h5.json not replaced).
- **H6 sampled** (`h56.py h6 --sample --sample-n 64 --budget-min 60 --cache`, same sessions, --h5 r12-h5, 6 jobs):
  COMPLETE, 41 min 50 s cold (0 cache hits: library, records and tools changed), **2,208/4,137 caught (53.4%)** over
  204 overrides, 11,641 of 172,499 records; published play/h6_sample.json (52.9% this morning, 51.1% in round 11).
  class_change.c 69/92 (75.0%). Gate 90% not met: writers off.
- **check_all**: robot-routes requires bt-ch24-clear (cq-ch13 and rv-ch18 still named paused, left out); new rows
  class-change-diff(-long), weapon-rank-diff(-long) (locks readable:class_change / readable:weapon_rank, cache specs);
  h56-h5 reads r10-capb,r11-capn,r11-capo,r12-cap-class_change,r12-capn. tests/test_check_all.py 75 tests OK.
  `check_all --slow --jobs auto --cache --skip h56-h5` (beside the live run and H6): 4,604 s, **92 pass, 1 known
  (readable-verify: item_sell_price NOT-RUN; 0 MISMATCH over 240: 132 ABI-ONLY, 15 CLEAN, 83 GAVE-UP, 9 UNSAMPLED),
  2 skip (gen-headers; h56-h5 on purpose)**. Then `check_all --only h56-h5` alone: PASS (79 s, 208 of 240 met,
  172,499 records).
- **Measured.** Minutes per chapter: bt-ch24 play 129, proof 12 (two copies 333 s + capture 217 s + pack). Batches:
  class_change 80 min + capture 115 min (library rebuild 5 min inside); weapon_rank 60 min + capture 110 min (both
  captures ran every route because the hit map cannot name routes for functions not yet in the library; about 95-100
  min of robot time each). Integrate 07:27 to about 09:00, **about 1 h 35 min** against a 1.5 h target: plan and
  check_all edits 7 min, offline 4.5 min, live 14.5 min, H5 2.3 min, H6 42 min beside check_all 77 min (the long
  pole: no row could reuse the cache, since new readable folders change every readable row's key, and the 12
  `--plant` rows take 21-36 min each), h56-h5 row 1.3 min, docs, evidence and clean about 8 min. Idle compute [med]:
  check_all was held to its day budget of 6 lanes (config/harness/resources.json max_parallel_runs; FEF_CHECK_ALL_SLOTS
  was not set), so in the 77-minute window about a fifth of the 12 slots stood idle, mostly after H6 ended at 08:34.
- **Evidence**: `evidence.py pack` (97.0 MB total) and `clean --yes --keep-sessions 10` (0.20 GB freed, 6 items)
  keeping r10-capb, r10-capc, r11-capn, r11-capo, r11-capc, r12-capn, r12-cap-class_change, r12-capc-class_change,
  r12-cap-weapon_rank, r12-bt24-proof, r12-bt24-cap (numbers in docs/evidence/INDEX.md).
- **Open**: H6 below gate (53.4%; exact cover weekly); 114 + 80 equivalent-mutant candidates for a person
  (docs/harness/H6_SURVIVORS.md); offline.py does not read 0-record batch captures (weapon_rank); the plan's line-2
  command does not yet use the caller map; 32 readers never met; item_sell_price never sampled by verify;
  CLASS_CHANGE.md coverage note wrong for unit_reliance_blocks_class_change; Conquest/Revelation paused; OK A and OK B
  still open. Next integrate: set FEF_CHECK_ALL_SLOTS=12 when no long live runs are planned.

## Status update 2026-11-18 (integrate, round 13): Birthright 25, the shop-price and castle-join batches, the round 13 tool fixes, checked together

**In plain words.** Round 13 (owner "Start round 12", rounds back to back; F-023, F-024, F-025 in force) played
Birthright 25 only (Conquest and Revelation stay paused: cq-ch13 and rv-ch18 unverified, not played), proved it as its
own step, added one green reader (shop_buy_price, captured once by its batch on the 5 shop routes and the cheat forge
route) and two host-only helpers (castle_join_offer and convoy_stack_value, no override, so nothing to capture). The tools step made
`offline.py plan` work out each session's own baseline and read 0-record batch captures, so this plan needed no
`--baseline-rev` and nothing was settled by hand. Integrate did not rebuild the library (FRESH) and compared **all 52
verified real-play routes: 176,698 records, 0 bad of any kind**: 51 routes offline from their records, only bt-ch25
live. Plan total 54.6% -> 54.8% (robot ~85% -> ~86%, readable ~25% -> ~25%, both [low]). Owner report:
docs/REPORT_2026-11-18.md.

- **Library**: `build.py --check-fresh` FRESH (rebuilt 2026-11-16T09:37:21 by the shop-price capture step with
  `--swap`; 241 overrides, 47 staged files, DLL sha256 97201c67f0b2...). No reader source changed after that build
  (shop_price and castle_join sources last written 09:10-09:16), so no reader needed a second capture. Not rebuilt.
- **Plan** (`offline.py plan --sessions r10-capb,r11-capn,r11-capo,r12-capn --extra-sessions "r12-cap-*,r13-cap-*"
  --label play`, no --baseline-rev; build/r13int/plan-play.txt). Baselines from each session's run.json: 0e8ddd7
  (r10-capb), de846a6 (r11-capn, r11-capo), d930f28 (r12-capn); 50 folders kept 0 records (watched, never called).
  - PLAN LINE 1, routes: 51 replay offline from their records, 0 must play live (route changed).
  - PLAN LINE 2, overrides: 241 decided by the records (1 of them, shop_buy_price, by the batch's own capture
    r13-cap-shop_price: 115 records on bt-castle-forge, bt-castle-shop, bt-ch6-castle, bt-ch9-ore, cq-ch10), 0 must
    play live. LIVE TOTAL: nothing plays live. Every override is decided, so "live only on routes that can reach
    it" is none; the only live run is the new route.
  - Cheat (`--sessions r10-capc,r11-capc --extra-sessions "r12-capc-*,r12-cap-weapon_rank,r13-capc-*" --label
    cheat`): 4 routes offline, 0 live; 241 decided (7 by batch captures, 3 of those watched and never called).
- **Offline**: `offline.py replay ... --name r13-off --jobs 4`: source gate passed, 141 folders, **172,614 records
  (168,543 match, 2,639 gave up, 1,432 incomplete), 0 bad, offline verdict != captured verdict: 0**, 87 s. Cheat
  `r13-offc`: 21 folders, 9,062 records (8,869 match, 100 gave up, 93 incomplete), 0 bad, 30 s.
- **Live**: `parallel.py runs --route bt-ch25 --mode capture --only all --store-keep --markers --timeout 5400 --session
  r13-capn` (FEF_ROBOT_JOBS=12): PASS, 425 s, 132,940 frames; 179 met, **4,084 records (3,988 match, 50 gave up, 46
  incomplete), 0 bad**; memory 10c23ede8159972a = the proof's; checkpoints all met; writers stored nothing; %APPDATA%
  unchanged. Started at once with the offline replays and check_all; only one live run existed.
- **Per family, real play (offline + live):** Birthright 31 routes 202 met 104,296 records; Conquest 7 187 met
  26,000; Revelation 12 191 met 44,390; options 2 65 met 2,012; **0 bad in each**. All: 52 routes, 176,698 records
  (172,531 match, 2,689 gave up, 1,478 incomplete), 209 of 241 met. Cheat apart: 9,062 records, 0 bad.
- **New reader in real play:** shop_buy_price 115 records, 115 match (4 Birthright shop routes 90, cq-ch10 25); cheat
  forge 23, all match. bt-ch25 has no shop visit, so it did not call it. castle_join_offer is a helper (never entered in
  the game): host-tested only (0 mismatches over 300 + 300 + 1,500 cases, 20/20 planted bugs), stays UNVERIFIED.
  Never met: the same 32 as round 12 (bt-ch25's cannons are fired by enemies, so unit_can_cannon_item and
  unit_has_cannon_item stay unmet).
- **H5** (`h56.py h5 --sessions r10-capb,r11-capn,r11-capo,r12-cap-class_change,r12-capn,r13-cap-shop_price,r13-capn
  --label play --run-id r13-h5 --no-exact --jobs 12 --jobs-over-budget`): 142 folders in 12 lanes, replay 80 s,
  gcov-tool merge 2.5 s, wall 3 min 51 s (beside check_all's 12 lanes); **209 of 241 met, 176,698 records, 0 bad,
  offline != live 0**; lines 1,273/1,479, branches 882/1,380 (63.9%). Exact cover stays weekly (PARTIAL by the
  tool's rule; play/h5.json not replaced).
- **H6 sampled** (`h56.py h6 --sample --sample-n 64 --budget-min 60 --cache`, same 7 sessions, --h5 r13-h5, --jobs 8;
  the tool ran 6 files side by side): COMPLETE, 51 min 28 s cold (0 cache hits: library, records and h56.py
  changed), **2,214/4,140 caught (53.5%)** over 205 overrides, 11,675 of 176,698 records; published
  play/h6_sample.json (53.4% in round 12). shop_price.c 3/3. Gate 90% not met: writers off.
- **check_all**: robot-routes requires bt-ch25-clear (cq-ch13 and rv-ch18 still named paused, left out); new rows
  shop-price-diff(-long), castle-join-diff(-long) (locks readable:shop_price / readable:castle_join, cache specs);
  h56-h5 reads r10-capb,r11-capn,r11-capo,r12-cap-class_change,r12-capn,r13-cap-shop_price,r13-capn.
  tests/test_check_all.py 77 tests OK. `FEF_CHECK_ALL_SLOTS=12 check_all --slow --jobs auto --cache --skip h56-h5`
  (beside the live run, H5 and H6): 53.5 min, 85 pass, 1 known, 2 skip, **11 fail, every one a timeout**
  (INCOMPLETE: the 11 older `--plant` rows vein, triangle, sheet, growth, move, formula, ai-perm, menu, support,
  skill, item; no mismatch line in any). With 12 check_all lanes plus H6's 6 files plus the live run on 24
  hardware threads, those rows ran slower than their 20-40 min limits. Rerun of those 11 after H6 ended
  (`--only ... --jobs auto --cache --timeout-scale 2`, 12 lanes): **11 pass** in 31.6 min (16-31 min each, all
  inside their normal limits; 0 mismatches, every planted bug caught). So: **96 pass, 1 known (readable-verify:
  item_sell_price NOT-RUN; 0 MISMATCH over 241: 132 ABI-ONLY, 15 CLEAN, 83 GAVE-UP, 10 UNSAMPLED), 2 skip
  (gen-headers; h56-h5 on purpose)**. Then `check_all --only h56-h5` alone: PASS (71 s, 209 of 241 met, 176,698
  records).
- **Measured.** Minutes per chapter: bt-ch25 play 70, proof 16 (two copies 547 s, pack, then a capture). Batches
  [med, from file times]: shop_price about 25 min + capture 17 min (library rebuild 5 min inside; only the 5 shop
  routes plus the cheat route, not every route: the caller filter worked); castle_join about 20 min, capture not
  applicable (helper only; two attempts confirmed it, no runs). Integrate 10:39 to 12:19, **about 1 h 40 min**
  against a 1.5 h target: plans and check_all edits 4 min; offline 1.5 min + cheat 0.5 min; live 7 min; H5 4 min;
  H6 51.5 min beside check_all 53.5 min; the 11-row rerun 31.6 min (the overrun); h56-h5 row 1.2 min; docs, evidence
  and clean about 3 min (drafted while runs went). Idle compute [med, from start and end times]: none in the first 53 minutes (oversubscribed:
  check_all 12 lanes, H6 6 files, the live run); in the rerun window the 11 rows finished between 16 and 31 min, so
  about a third of the 12 slots stood idle in its last 15 minutes. Without the timeouts integrate would have ended
  near 1 h 10 min. Next integrate: give check_all 8 slots while H6 runs (or start the `--plant` rows first), not 12.
- **Evidence**: `evidence.py pack` (100.3 MB total) and `clean --yes --keep-sessions 10` (0.07 GB freed, 2 items:
  r12-bt24-proof, r12-bt24-cap, both packed) keeping r10-capb, r10-capc, r11-capn, r11-capo, r11-capc, r12-capn,
  r12-cap-class_change, r12-cap-weapon_rank, r12-capc-class_change, r13-capn, r13-cap-shop_price,
  r13-capc-shop_price, r13-bt25-proof, r13-bt25-cap (numbers in docs/evidence/INDEX.md).
- **Open**: H6 below gate (53.5%; exact cover weekly); 43 (round 13) + 114 + 80 equivalent-mutant candidates for a
  person (docs/harness/H6_SURVIVORS.md); the give-up counter is proposed only (owner's call); convoy_stack_value
  (64-bit return) and castle_join_offer (helper) have host tests only; shop_buy_price UNSAMPLED in tier 2 (live
  capture covers it); 32 readers never met; item_sell_price never sampled by verify; the plan's line-2 command does
  not yet use the caller map; Conquest/Revelation paused; OK A and OK B still open.

## Status update 2026-11-19 (integrate, round 14): Birthright 26, the equip-check and staff batches, the new gate and the weekly slow suite, checked together

**In plain words.** Round 14 (owner "Start round 12", rounds back to back; F-023 to F-028 in force) played
Birthright 26 only (Conquest and Revelation stay paused: cq-ch13 and rv-ch18 unverified, not played), proved it as its
own step, and added two green reader batches from REWRITE_ORDER3: the equip check (`unit_can_equip_item`,
Unit::CanItemEquip) and three staff readers (`unit_rod_heal_power`, `unit_status_staff_hit`,
`unit_status_staff_avoid`). Each batch was captured once before integrate. The owner adopted Grok's three-number
writer gate (F-026), Grok's delay rules (F-027) and a weekly slow suite (F-028), so this integrate ran no `--slow`
pass and no sampled H6. It did not rebuild the library (FRESH) and compared **all 53 verified real-play routes:
181,029 records, 0 bad of any kind**: 52 routes offline from their records, only bt-ch26 live; the cheat routes apart
(9,212 records, 0 bad), where the four new readers played live once. Integrate took about 30 minutes. Plan total
54.8% -> 55.1% (robot ~86% -> ~87%, readable ~25% -> ~26%, both [low]). Owner report: docs/REPORT_2026-11-19.md.

- **Library**: `build.py --check-fresh` FRESH (rebuilt 2026-11-16T15:30:21 by the equip capture step with `--swap`;
  245 overrides, 49 staged files). The reader sources were last written before their captures (equip_use.c 12:40,
  staff_range.c 12:39); the batches' later edits were tests, docs and comments only. Not rebuilt; no second capture.
- **Plan** (`offline.py plan --sessions r10-capb,r11-capn,r11-capo,r12-capn,r13-capn --extra-sessions
  "r12-cap-*,r13-cap-*,r14-cap-*" --label play`; build/r14int/plan-play.txt). Baselines from each session's run.json:
  0e8ddd7, de846a6, d930f28, ef15c64; 51 folders kept 0 records (watched, never called).
  - PLAN LINE 1, routes: 52 replay offline from their records, 0 must play live (route changed).
  - PLAN LINE 2, overrides: 245 decided by the records (4 of them by the batches' own captures: unit_can_equip_item
    by r14-cap-equip_use, 215 records on 8 Birthright routes; the three staff readers by r14-cap-staff_range, 731 +
    41 + 41 records), 0 must play live. LIVE TOTAL: nothing plays live; the only real-play live run is the new route.
  - Cheat (`--sessions r10-capc,r11-capc --extra-sessions "r12-capc-*,r12-cap-weapon_rank,r13-capc-*" --label
    cheat`): 4 routes offline; 241 decided, 4 must play live on the 4 cheat routes (the four new readers; neither
    batch capture included a cheat route).
- **Offline**: `offline.py replay ... --name r14-off --jobs 4`: source gate passed, 186 folders, **177,726 records
  (173,344 match, 2,887 gave up, 1,495 incomplete), 0 bad, offline verdict != captured verdict: 0**, 159 s. Cheat
  `r14-offc`: 21 folders, 9,062 records, 0 bad, 29 s.
- **Live** (all started at once with the offline replays): `parallel.py runs --route bt-ch26 --mode capture --only
  all --store-keep --markers --timeout 5400 --session r14-capn` (FEF_ROBOT_JOBS=12): PASS, 127 s, 31,460 frames; 167
  met, **3,303 records (3,185 match, 66 gave up, 52 incomplete), 0 bad**; memory 9da9f7c1fdcaf666 = the proof's;
  checkpoints all met; writers stored nothing; %APPDATA% unchanged. Cheat: `r14-capc-readers` (the 4 cheat routes,
  `--only` the 4 new readers): 4/4 PASS, 59 s, 150 records (48 match, 101 gave up, 1 incomplete), 0 bad; memory
  hashes equal to every earlier cheat session.
- **Per family, real play (offline + live):** Birthright 32 routes 108,185 records; Conquest 7, 26,209; Revelation
  12, 44,623; options 2, 2,012; **0 bad and 0 other differences in each**. All: 53 routes, 181,029 records (176,529
  match, 2,953 gave up), 213 of 245 met. Cheat apart: 9,212 records, 0 bad.
- **New readers in real play:** unit_can_equip_item 242 records (54 match, the rest gave up: safe; most likely early
  calls with one of its 30 caches still cold, not proven); unit_rod_heal_power 731 (692 match) on 36 routes;
  unit_status_staff_hit 41 (37 match) and unit_status_staff_avoid 41 (38 match), only on cq-ch7, cq-ch8, cq-ch11 and
  cq-ch12 (Conquest records already on disk; no Conquest was played). 0 mismatches of any kind. Never met: the same 32.
- **H5** (`h56.py h5 --sessions r10-capb,r11-capn,r11-capo,r12-cap-class_change,r12-capn,r13-cap-shop_price,r13-capn,
  r14-cap-equip_use,r14-cap-staff_range,r14-capn --label play --run-id r14-h5 --no-exact --jobs 12
  --jobs-over-budget`): 1 min 56 s; **213 of 245 met, 181,029 records, 0 bad, offline != live 0**; lines 1,328/1,540,
  branches 928/1,460 (63.6%). Exact cover stays weekly. `check_all --only h56-h5` alone: PASS, 91 s.
- **The new gate (F-026), three numbers kept apart** (`h6three.py` on r14-h5, r14-off, r14-offc, r14-capn,
  r14-capc-readers; build/h6three/three-r14.json): (1) recordings on reached lines 2,214 / 3,700 (59.8%; 62.9% also
  leaving out helper lines H5 has no data for), from round 13's sample, since the sampled H6 is weekly now; (2) host
  test alone 2,864 / 3,139 (91.2%), records or host 2,997 / 3,270 (91.7%), 13 files (870 planted bugs) with no host
  test; (3) live compare 53 routes, 181,029 records, 0 bad, cheat apart 9,212, 0 bad. No writer is near the gate:
  no writer has passed all three for itself, and number 1 is under 90% on every file except ai_think, forces and
  the three smallest.
- **check_all** (F-028, no `--slow`): robot-routes requires bt-ch26-clear; new rows equip-use-diff,
  equip-use-diff-s7, staff-range-diff, staff-range-diff-long (locks readable:equip_use / readable:staff_range) and
  h6three-tests; h56-h5 reads the 10 sessions above; tests/test_check_all.py 78 tests OK.
  `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`: 37 pass in 50 s. `--only` the touched
  slow and medium rows (equip-use-diff, equip-use-diff-s7, staff-range-diff, staff-range-diff-long, readable,
  selftest, item-diff, ai-perm-diff, robot-routes, h6three-tests): **10 pass** in 14.2 min. h56-h5: pass. 58 slow
  and medium rows left for the weekly run (docs/CHECK_ALL.md, round 14).
- **Measured.** Minutes per chapter: bt-ch26 play 30 (29.6), proof 8 (two copies 187 s, pack, then a capture).
  Batches: equip_use review fix 35 min + capture 17 min (8 routes, library rebuild 5 min inside); staff_range
  capture stopped by the cap with 37 of 47 jobs finished (13:41 to about 15:12, kept without new games). Integrate
  15:49 to about 16:20, **about 30 min** against a 45-60 min target: plans 1 min; offline, cheat offline and both live
  runs side by side 3 min; check_all edits 4 min beside them; fast pass 1 min; touched rows 14 min with H5 (2 min)
  beside them; h56-h5 row 1.5 min; h6three 1 min; evidence and clean 0.5 min; docs about 9 min. Idle compute [med]:
  from about 16:00 to 16:10 only item-diff and ai-perm-diff ran, so about 10 of 12 lanes stood idle.
- **Evidence**: `evidence.py pack` (108.9 MB total) and `clean --yes --keep-sessions 10` (0.07 GB freed, 2 items:
  r13-bt25-proof, r13-cap-shop_price-logs, both packed) keeping r10-capb, r10-capc, r11-capn, r11-capo, r11-capc,
  r12-capn, r12-cap-class_change, r12-cap-weapon_rank, r12-capc-class_change, r13-capn, r13-cap-shop_price,
  r13-capc-shop_price, r14-cap-equip_use, r14-cap-staff_range, r14-capn, r14-capc-readers, r14bt26proof, r14bt26cap
  (the H5 run r14-h5 is under build/harness/h56, which clean does not touch).
- **Open**: 237 equivalent-mutant candidates in 13 rule classes for a person (F-026), plus 36 new unsorted ones from
  the measure step; 13 files with no host test; h6host.py's 300 s driver limit is skipped when a diff script passes
  driver arguments (item_record-007/-008 hung 54 min); unit_can_equip_item gives up on most kept calls (which guard
  stays cold is not traced); Unit::CanItemUse still skipped (needs a guest stack object); review notes: the equip
  test barely covers the draw-staff use number above 0xFF, the staff test has no case at the hit clamp's -1;
  staff_range tier 2 is GAVE-UP only (cold caches); 32 readers never met; item_sell_price never sampled by verify;
  Conquest/Revelation paused; OK A and OK B open.

## Status update 2026-11-20 (integrate, round 15): Birthright 27, the capability batch, the step-4 look prepared, checked together

**In plain words.** Round 15 (F-023 to F-028 in force; the first round under Grok's caps and counted time box)
played Birthright 27 "King Garon" only (Conquest and Revelation stay paused: cq-ch13 and rv-ch18 unverified, not
played), proved it as its own step, added one capped reader batch (the capability readers: `unit_capability`,
`unit_capability_rating`, `unit_capability_rating_no_weakness`; docs/CAPABILITY.md) and put one helper on PORT_PLAN
step 4: the stat-table look is ready for the owner (docs/LOOK_STEP4.md). The batch's first capture found 7 call-list
differences in `unit_capability` (a tail branch the capture does not count as a call); the batch fixed the reader,
sharpened its host test so it sees this, and a retry capture on the same 8 routes was clean. The game makes no save
after chapter 27, so there is no bt-ch27-clear save; how Endgame starts is for a person to decide. Integrate did not
rebuild the library (FRESH) and compared **all 54 verified real-play routes: 185,316 records, 0 bad of any kind**:
53 routes offline from their records, only bt-ch27 live; the cheat routes apart (9,512 records, 0 bad), where the
new readers played live once. Integrate took about 38 minutes. Plan total 55.1% -> 55.2% (robot ~87% -> ~88% [low];
readable stays ~26%; step 4 stays ~68% until the owner looks). Owner report: docs/REPORT_2026-11-20.md.

- **Library**: `build.py --check-fresh` FRESH (rebuilt 2026-11-16T17:59:30 by the capability retry capture; 248
  overrides, 50 staged files). Not rebuilt; no reader edited after its last capture; no extra capture.
- **Plan** (build/speed/r15int/): as asked, `offline.py plan --sessions r10-capb,r11-capn,r11-capo,r12-capn,
  r13-capn,r14-capn --extra-sessions "r12-cap-*,r13-cap-*,r14-cap-*,r15-cap-*" --label play`:
  - PLAN LINE 1, routes: 53 replay offline from their records, 0 must play live (route changed).
  - PLAN LINE 2, overrides: 248 decided by the records (3 by the batch's own captures), 0 must play live. LIVE
    TOTAL: nothing plays live; the only real-play live run is the new route bt-ch27.
  - The glob includes `r15-cap-capability`, recorded before the fix with 7 live mismatch_calls; the replay left it
    out and used `r15-cap-capabilityb` (same two lines: 53 offline, 248 decided, 0 live).
  - Cheat (`--sessions r10-capc,r11-capc --extra-sessions "r12-capc-*,r12-cap-weapon_rank,r13-capc-*,r14-capc-*"`):
    4 routes offline; 245 decided, 3 must play live on the 4 cheat routes (the capability readers).
- **Offline**: `r15-off`: source gate passed, 195 runs, **181,444 records (176,802 match, 3,013 gave up, 1,629
  incomplete), 0 bad, offline verdict != captured verdict: 0**, 118 s. Cheat `r15-offc`: 28 runs, 9,212 records,
  0 bad, 29 s.
- **Live** (all started at once with the offline replays, 18:19:33): bt-ch27 with every override (`r15-capn`,
  FEF_ROBOT_JOBS=12): PASS, 370 s, 112,772 frames, 171 met, **3,872 records (3,739 match, 74 gave up, 59
  incomplete), 0 bad**; memory 435c8519ffc0530b = the proof's; checkpoints all met; writers stored nothing;
  %APPDATA% unchanged. Cheat `r15-capc-capability` (4 cheat routes, `--only` the 3 new readers): 4/4 PASS, 49 s,
  300 records, 0 bad; memory hashes equal to r14-capc-readers.
- **Per family, real play (offline + live):** Birthright 33 routes 112,472 records; Conquest 7, 26,209; Revelation
  12, 44,623; options 2, 2,012; **0 bad and 0 other differences in each**. All: 54 routes, 185,316 records, 215 of
  248 met. Cheat apart: 9,512 records, 0 bad.
- **New readers in real play:** unit_capability 259 records (193 match, the rest gave up or incomplete: safe) on the
  8 capture routes and bt-ch27; unit_capability_rating 204 (113 match; SHALLOW: one path signature);
  unit_capability_rating_no_weakness never met (only the help text calls it; host test only). 0 mismatches of any
  kind. Never met: the same 32 plus the no-weakness total.
- **H5** (`r15-h5`, 12 sessions, `--no-exact --jobs 12 --jobs-over-budget`): about 2 min; **215 of 248 met, 185,316
  records, 0 bad, offline != live 0**; lines 1,342/1,556, branches 937/1,470 (63.7%). `check_all --only h56-h5`
  alone: PASS, 74 s.
- **The gate (F-026), three numbers kept apart** (`h6three.py`, build/h6three/three-r15.json): (1) recordings on
  reached lines 2,214 / 3,696 (59.9%; 62.9% also leaving out helper lines), still round 13's sample (weekly);
  (2) host test alone 2,864 / 3,139 (91.2%), records or host 91.7%; (3) live compare 54 routes, 185,316 records,
  0 bad; cheat 9,512, 0 bad. No writer is near the gate.
- **check_all** (F-028, no `--slow`): robot-routes knows bt-ch27 has no clear save (`NO_CLEAR_SAVE`; fails on a
  bt-ch27-clear.zip equal to bt-ch26-clear); new rows capability-diff, capability-diff-long, guest-call6-test,
  look-step4; h56-h5 reads 12 sessions; tests/test_check_all.py 79 OK. Fast pass 38 pass in 41 s; touched rows
  (capability-diff, capability-diff-long, look-step4, readable, selftest, sheet-diff) 6 pass in 9.7 min; h56-h5
  pass. 62 slow/medium rows left for the weekly run (docs/CHECK_ALL.md, round 15). fe_guest.h changed (one function
  added): every reader includes it; tonight only the `readable` row (all 50 sources) and guest_call5/6 tests cover it.
- **Step 4 (stat tables):** the look is prepared, not seen. One mod, `LookStep4` (tools/mods/look_step4.py): Corrin's
  personal HP, Mov +2 for the six Corrin classes, Bronze Sword might, Supportive's icon, and a Luck bonus on every
  dining dish. Built from the owner's own files, read back cell by cell, installed into and uninstalled from a
  scratch folder byte-identical; the robot saw the four table edits in memory, not the dining edit. Step 4 stays
  ~68% until the owner looks (10-15 minutes).
- **Measured (F-027 count).** Chapter 58 min (cap 100); proof 28 min; batch 80 min (cap 120) + live fix 45 min;
  captures 27 min + 25 min retry (cap 45 each); stats 15 min (cap 90); integrate about 38 min (cap 60). No cap was
  hit. The batch's fix and retry (70 min) were not in the count; the round still ended inside its box (about 2 h
  35 min of wall time from the chapter's start at 16:22 to about 18:55, box about 3 h 15 min) because steps ran side
  by side. Idle compute [med]: about 11 minutes of mostly idle PC in integrate (one bt-ch27 copy alone for 4 min;
  sheet-diff alone for 7 min).
- **Evidence**: `evidence.py pack` (112.1 MB) and `clean --yes --keep-sessions 10` (3 small packed items freed),
  keeping every r10-r15 capture session and r15-h5.
- **Open**: no save after bt-ch27 (how Endgame starts needs a person); 33 readers never met; the no-weakness total
  has host-test evidence only; capability tier 2 GAVE-UP only (cold caches); other routes may have checkpoints not
  in their shot list (found on bt-ch27); 237 equivalent candidates in 13 rule classes plus 36 unsorted for a person
  (F-026); 13 files with no host test; the step-4 look; Conquest/Revelation paused; OK A and OK B open.

## Status update 2026-11-21 (integrate, round 16): Birthright Endgame tried, the shop buy-list batch, two looks staged, checked together

**In plain words.** Round 16 (F-023 to F-029 in force; Grok's count docs/collab/NEXT_R16_GROK.md: 239 minutes, hard
stop 315) tried Birthright's last chapter from the bt-ch27 chain state (F-029). It was **not won**: the helper
stopped at 63 minutes of play (cap 100) on turn 5, with 16 of 16 units alive and the chain kept, because Garon (Blight
Dragon) could not be beaten in the time left. No `bt-endgame` route key, no proof, nothing new played live. One
capped reader batch (the shop buy list: `shop_stock`, `shop_price_disabled`, `shop_buy_max`; docs/SHOP_GREY.md) was
green before its capture, and its capture on 6 shop routes was clean the first time (no fix, no retry). Two more
looks were staged for the owner: a renamed name (docs/LOOK_TEXT.md, step 3) and one portrait swap
(docs/LOOK_PORTRAIT.md, step 5), plus the 30-minute sitting order (docs/LOOK_SITTING.md). Integrate did not rebuild
the library (FRESH) and compared **all 54 verified real-play routes offline: 185,561 records, 0 bad of any kind**;
the cheat routes apart: 9,561 records, 0 bad. Integrate took about 20 minutes. Plan total stays 55.2% (robot ~88%:
Birthright not finished; readable ~26%; steps 3, 4, 5 unchanged until the owner looks). Owner report:
docs/REPORT_2026-11-21.md.

- **Library**: `build.py --check-fresh` FRESH (rebuilt 2026-11-16T21:09:58 by the shop_grey capture; 251 overrides,
  51 staged files). Not rebuilt; no extra capture.
- **Plan** (build/speed/r16int/): real play, main sessions r10-capb, r11-capn, r11-capo, r12-capn, r13-capn,
  r14-capn, r15-capn, extra "r12-cap-*,r13-cap-*,r14-cap-*,r15-cap-capabilityb,r16-cap-*":
  - PLAN LINE 1, routes: 54 replay offline from their records, 0 must play live (route changed).
  - PLAN LINE 2, overrides: 251 decided by the records (3 by the batches' own captures, 1 watched and never
    called), 0 must play live. LIVE TOTAL: nothing plays live.
  - Cheat: 4 routes offline; 251 decided, 0 live.
  - The batch capture's one cheat run (cheat-forge-katana) was moved to its own session, r16-capc-shop_grey, because
    the tools refuse a session that mixes real play and cheat records (F-019).
- **Offline**: `r16-off`: 201 runs, **185,561 records (180,786 match, 3,087 gave up, 1,688 incomplete), 0 bad,
  offline verdict != captured verdict: 0**, 104 s. Cheat `r16-offc`: 36 runs, 9,561 records, 0 bad, 33 s.
- **Per family, real play:** Birthright 33 routes 112,664 records; Conquest 7, 26,262; Revelation 12, 44,623;
  options 2, 2,012; **0 bad and 0 other differences in each**. Cheat apart: 9,561 records, 0 bad.
- **New readers in real play:** shop_stock 115 records and shop_price_disabled 130, all match (the second one was
  UNSAMPLED in tier-2 verify; this is its first real check); shop_buy_max never called (host test only). Never met:
  34 of 251.
- **H5** (`r16-h5`, 13 sessions, `--no-exact`): 217 of 251 met, 185,561 records, 0 bad, offline != live 0; branches
  942/1,476 (63.8%). `check_all --only h56-h5` alone: PASS, 74 s.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r16.json): (1) recordings on reached lines
  2,214 / 3,696 (59.9%), still round 13's weekly sample; (2) host test alone 2,864 / 3,139 (91.2%), records or host
  91.7%; (3) live compare 54 routes, 185,561 records, 0 bad; cheat 9,561, 0 bad. No writer is near the gate.
- **check_all** (F-028, no `--slow`): new rows shop-grey-diff, shop-grey-diff-long, look-text, look-portrait; h56-h5
  reads 13 sessions; tests/test_check_all.py 79 OK. Fast 39 pass; touched rows 8 pass (look-portrait after a fix to
  its note, which held Japanese file names and crashed the console print); h56-h5 pass. 63 slow/medium rows left
  for the weekly run. bt-endgame was not added to the "no clear save" list: there is no such route yet.
- **Steps 3 and 5:** the looks are staged, not seen. Step 3: `LookText` renames Jakob to "Jacques" (one English name
  label, found at run time); built, read back, scratch install/uninstall byte-identical; the robot saw "Jacques" in
  the game's memory. Step 5: `LookPortrait` gives Jakob Felicia's face (7 expressions, existing faces/ mod kind);
  built, decoded again, scratch install/uninstall byte-identical; no robot route shows Jakob. Both stay at their
  percent until the owner looks (docs/LOOK_SITTING.md, about 30 minutes in all).
- **Measured (F-027 count, 239 min counted).** Endgame play 63 min (cap 100, stopped); proof and retry 0 (nothing
  to prove); batch 55 min (cap 120); capture 24 min (cap 45); fix and second capture 0 (not needed); looks 23 min
  (cap 60); integrate about 20 min (cap 60). No cap was hit. Wall time from the round's start at about 20:36 to the
  end of integrate at about 22:13: about 1 h 37 min [med: start time read from file times]. Idle compute [med]:
  no game ran in integrate; about 7 minutes of mostly idle PC while check_all rows were written and fixed.
- **Evidence**: `evidence.py pack` (112.4 MB) and `clean --yes --keep-sessions 10` (0 freed), keeping every r10-r16
  capture session and r15-h5 / r16-h5.
- **Open**: Endgame not won (chain kept at build/speed/btend/ce, frame 158338; plan in docs/ROBOT.md 3v); where the
  game lands after Endgame and whether it saves, unknown; shop_buy_max never met (host test only); 34 readers never
  met; 237 equivalent candidates plus 36 unsorted for a person (F-026); 13 files with no host test; the three looks;
  Conquest/Revelation paused; OK A and OK B open.

## Status update 2026-11-22 (integrate, round 17): danger tools fixed, a second Endgame try, host tests for the 13 files with none, checked together

**In plain words.** Round 17 (F-023 to F-029 in force; owner's "choice 2": fix the danger tool first, then a fresh
100-minute Endgame try from the turn-5 chain, beside host tests for the 13 files with none; counted 268 minutes,
hard stop 325) rebuilt the robot's Endgame threat tools on one shared file (about 5 minutes) and played Endgame on
from turn 5 for 57 minutes. It was **not won**: the chain is kept at the start of turn 9 with 16 of 16 alive, Garon
78/78 in his throne alcove. No `bt-endgame` route key, no proof, nothing new played live. The host-test step gave
every one of the 13 files a host verdict (3 new diff scripts for 4 files that had none, adapters for the other 9):
870 planted bugs, 831 caught, 35 of the 39 survivors judged unable to change an answer, 4 open. No reader code
changed. Integrate did not rebuild the library (FRESH) and compared **all 54 verified real-play routes offline:
185,561 records, 0 bad of any kind**; the cheat routes apart: 9,561 records, 0 bad. Integrate took about 24 minutes.
Plan total stays 55.2% (robot ~88%: Birthright Endgame not won; readable ~26%: tests only, no new reader [low];
steps 3, 4, 5, 7 unchanged until the owner looks). Owner report: docs/REPORT_2026-11-22.md.

- **Library**: FRESH (2026-11-16T21:09:58; 251 overrides, 51 staged files). Not rebuilt.
- **Plan** (build/speed/r17int/): real play, the same main and extra sessions as round 16 (r15-cap-capability left
  out): PLAN LINE 1, routes: 54 offline, 0 live. PLAN LINE 2, overrides: 251 decided by the records, 0 live. Cheat:
  4 routes offline; 251 decided, 0 live.
- **Offline**: `r17-off`: 201 runs, **185,561 records (180,786 match, 3,087 gave up, 1,688 incomplete), 0 bad,
  offline verdict != captured verdict: 0**, 97 s. Cheat `r17-offc`: 36 runs, 9,561 records, 0 bad, 27 s.
- **Per family, real play:** Birthright 33 routes 112,664 records; Conquest 7, 26,262; Revelation 12, 44,623;
  options 2, 2,012; **0 bad and 0 other differences in each**.
- **H5** (`r17-h5`, `--no-exact`): 217 of 251 met, 185,561 records, 0 bad, offline != live 0; branches 942/1,476
  (63.8%). `check_all --only h56-h5`: PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r17.json): (1) recordings on reached lines
  2,214 / 3,696 (59.9%), still round 13's weekly sample; (2) host test alone 3,696 / 4,009 (92.2%, was 91.2%),
  records or host 92.6% (was 91.7%), 36 files with a host test and 0 without (was 13 without); (3) live compare 54
  routes, 185,561 records, 0 bad; cheat 9,561, 0 bad. No writer is near the gate.
- **check_all** (F-028, no `--slow`): six new rows (ai-value-diff, flags-diff, forces-diff and their -long rows);
  tests/test_check_all.py 79 OK. Fast 39 pass; touched rows 9 pass; readable pass; h56-h5 pass. 69 slow/medium
  rows left for the weekly run. bt-endgame still has no route key, so robot-routes is unchanged.
- **Step 8 (robot):** stays ~88%. Endgame tried twice, not won; the kept chain replays clean.
- **Step 9 (readable):** stays ~26% [low]. The host tests raise how well the existing 251 readers are checked
  (number 2 above), but no reader was added.
- **Measured (F-027 count, 268 min counted).** Danger tools about 5 min (cap 30); Endgame play 57 min (cap 100) plus
  11 min replay check; proof and retry 0 (nothing to prove); host tests 59 min (cap 120, beside the play); integrate
  about 24 min (cap 60). No cap was hit. Wall time from about 23:57 to about 01:38: about 1 h 41 min [med: start
  read from file times].
- **Evidence**: `evidence.py pack` (112.4 MB, nothing new) and `clean --yes --keep-sessions 10` (0 freed), keeping
  every r10-r16 capture session and r15-h5 / r16-h5 / r17-h5.
- **Open**: Endgame not won (chain build/speed/btend/cf, frame 206992, turn 9; plan in docs/ROBOT.md 3w-2, not
  tested); several units low from blight; the danger tools do not know blight tiles; the ai_has_heal_rod cache-guard
  mutants (4) for a person; h6host has no time limit for drivers imported by a diff script (two runaways stopped by
  hand); flags_diff's case maker can give a false mismatch on other seeds; 34 readers never met; 237 equivalent
  candidates plus 71 unsorted for a person (F-026); the three looks; Conquest/Revelation paused; OK A and OK B open.

## Status update 2026-11-23 (integrate, round 18): a third Endgame try, the weapon-rank line reader, the test-tool fixes, checked together

**In plain words.** Round 18 (F-023 to F-029 in force; owner's "Yes, start it": Endgame from the turn-9 chain with a
100-minute cap, beside one capped reader batch and the round-17 test-tool fixes; counted 254 minutes from the
04:05 restart, hard stop 330) played Endgame a third time, following Grok's plan from the turn-5 chain on a fresh
copy (chain ch). It was **not won**: after 47 minutes the robot stopped at the start of turn 8 with 16 of 16
alive and Garon at 78/78, because a dual-strike partner does only half damage, so the planned strikes cannot reach
78 HP in time. No `bt-endgame` route key, so no proof and nothing new played live for Endgame. The batch added one
reader, `weapon_level_view_kind` (the weapon-rank line on the unit screen; 22/22 planted bugs caught, 0
mismatches), and its capture recorded it 93 times on 4 Birthright routes (92 match, 1 incomplete), 0 bad. The test-tool step fixed all three
round-17 test faults (no reader code changed). Integrate did not rebuild (FRESH after the capture step), compared
**all 54 verified real-play routes offline: 185,654 records, 0 bad of any kind**, and played the new reader live
on the 4 cheat routes (23 records, 0 bad; cheat apart 9,584 records, 0 bad). Integrate took about 28 minutes.
Plan total stays 55.2% (robot ~88%: Endgame not won; readable ~26% with 252 readers, one more [low]; steps 3, 4,
5, 7 unchanged until the owner looks). Owner report: docs/REPORT_2026-11-23.md.

- **Library**: FRESH (2026-11-17T04:26:23, rebuilt once by the capture step; 252 overrides, 52 staged files). Not
  rebuilt by integrate; no reader changed after its capture.
- **Plan** (build/speed/r18int/): real play, round 17's main and extra sessions plus r18-cap-weapon_level_view
  (r15-cap-capability left out): PLAN LINE 1, routes: 54 offline, 0 live. PLAN LINE 2, overrides: 252 decided by
  the records, 0 live. Cheat: PLAN LINE 1, 4 routes offline, 0 live; PLAN LINE 2, 251 decided, 1 live on 4 routes
  (weapon_level_view_kind; session r18-capc-weapon_level_view).
- **Offline**: `r18-off`: 205 runs, **185,654 records (180,878 match, 3,087 gave up, 1,689 incomplete), 0 bad,
  offline verdict != captured verdict: 0**, 130 s. Cheat `r18-offc`: 36 runs, 9,561 records, 0 bad, 31 s.
- **Live (cheat only)**: 4 runs, 44 s; 23 records on cheat-forge-katana (22 match, 1 incomplete), 0 bad; no writer
  stored; %APPDATA% unchanged.
- **Per family, real play:** Birthright 33 routes 112,757 records; Conquest 7, 26,262; Revelation 12, 44,623;
  options 2, 2,012; **0 bad and 0 other differences in each**.
- **H5** (`r18-h5`, `--no-exact`): 218 of 252 met, 185,654 records, 0 bad, offline != live 0; branches 955/1,492
  (64.0%). `check_all --only h56-h5`: PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r18.json): (1) recordings on reached lines
  2,214 / 3,696 (59.9%), still round 13's weekly sample; (2) host test alone 3,700 / 4,009 (92.3%, was 92.2%),
  records or host 92.6%, 36 files with a host test and 0 without; (3) live compare 54 routes, 185,654 records,
  0 bad; cheat 9,584, 0 bad. No writer is near the gate.
- **check_all** (F-028, no `--slow`): four new rows (weapon-level-view-diff and -long, h6host-test,
  flags-diff-s424242), ai-perm-diff now 48 planted bugs; tests/test_check_all.py 79 OK. Fast 40 pass; touched rows 8
  pass; h56-h5 pass. 72 slow/medium rows left for the weekly run. robot-routes unchanged (no bt-endgame).
- **Step 8 (robot):** stays ~88%. Endgame tried three times, not won; the new chain ch replays clean from frame 0.
- **Step 9 (readable):** stays ~26% [low]: 252 readers (one more), all checked by the host test and live compare.
- **Measured (F-027 count, 254 min counted).** Endgame play 47 min (cap 100); proof and retry 0 (nothing to prove);
  batch 35 min (cap 80 counted; its own cap 2 h) plus capture 17 min (cap 27 counted, 45 own); no fix and no second
  capture needed; test tools 49 min (cap 60, beside); integrate about 28 min (cap 60). No cap was hit. Wall time
  from the 04:05 restart to about 05:31: about 1 h 26 min [med: step times are the helpers' own figures].
- **Evidence**: `evidence.py pack` (112.8 MB) and `clean --yes --keep-sessions 10` (0 freed), keeping every r10-r18
  capture session, r14bt26cap / r14bt26proof, and r15-h5 to r18-h5.
- **Open**: Endgame not won (chain build/speed/btend/ch, frame 193094, turn 8; dual strikes do half damage, so a
  new plan built on Ryoma's attacks needs about 4-5 turns, more than one 100-minute cap); Rinkah, Sakura and Scarlet
  at 1 HP, the throne General still alive; the help pop-up caller of the new reader (HelpItemWeaponLv) is not on any
  route; weapon_level_view.c not yet in the weekly H6 sample; CanItemUse and GetTrickFromAccess caches still not
  modelled in ai_perm_diff; 34 readers never met; 237 equivalent candidates plus 70 unsorted for a person (F-026);
  the looks; Conquest/Revelation paused; OK A and OK B open.

## Status update 2026-11-24 (integrate, round 19): Birthright Endgame finished on the cheat track (F-030), checked together

**In plain words.** Round 19 (F-030, owner 2026-11-17 15:00: "just cheat and count it, the purpose of the tests is
to make sure it RUNS"; counted 165 minutes from 15:10, hard stop 240) finished Birthright Endgame **on the cheat
track**. From the kept turn-8 chain (16 of 16 alive), one declared poke set Garon's current HP from 78 to 1; Ryoma's
first hit killed him, and the game then ran through the whole ending (ending scenes, chapter records, epilogue and
staff credits, "The End", the logbook card entry) to the title screen, with no hang, no crash and no save prompt.
The route is `cheat-bt-endgame` (`"cheat": true`). The two-copy proof passed; the proof step's capture was stopped
at its cap, so integrate ran it again in full with every override: **6,328 records, 0 bad**, and the route is now
`verified: true`. Integrate also compared **all 54 verified real-play routes offline: 185,654 records, 0 bad of any
kind** (cheat routes apart: 5 routes, 15,912 records, 0 bad). Per F-030 this counts as Birthright played to the end:
plan total 55.2% -> 55.4% (robot ~88% -> ~90% [low]; readable ~26% unchanged; steps 3, 4, 5, 7 unchanged until the
owner looks). Owner report: docs/REPORT_2026-11-24.md.

- **Library**: check-fresh STALE only because of another area's batch in progress (two new targets.csv rows and
  staged files: strike_power, who_holds_can_equip_subkind; uncommitted, no capture yet). No reader of the 252
  changed; integrate did not rebuild, so as not to bake another area's unfinished code into the capture library.
  The live run used the 04:31 library, the same one the proof used.
- **Plan** (build/speed/r19int/): real play PLAN LINE 1: 54 offline, 0 live; PLAN LINE 2: 252 decided, 2 live on
  54 routes (the other area's two new rows, not in the library; left to that batch's own capture). Cheat: PLAN LINE
  1: 4 offline, 0 live; PLAN LINE 2: 252 decided, 2 live on 4 routes (same two rows). cheat-bt-endgame played live
  with every override (no records before).
- **Live**: cheat-bt-endgame, r19-capc-endgameb: exit 0, 291,636 frames, all checkpoints met, memory
  95f8384c0bf16d25 (same as the proof), 1,395 s; 182 functions, 6,328 records (6,170 match, 76 gave up, 82
  incomplete), **0 bad**; no writer stored; %APPDATA% unchanged.
- **Offline**: `r19-off`: 205 runs, 185,654 records, 0 bad, 0 verdict differences, 110 s. Cheat `r19-offcb`: 37
  runs, 9,584 records, 0 bad, 37 s. Both with `--no-source-gate` (the gate stopped only on the two new staged files,
  which have no records).
- **Per family, real play:** Birthright 33 routes 112,757 records; Conquest 7, 26,262; Revelation 12, 44,623;
  options 2, 2,012; **0 bad and 0 other differences in each**. Cheat apart: 5 routes, 15,912, 0 bad.
- **H5** (`r19-h5`, `--no-exact`): 218 of 254 met (the two new rows never met), 185,654 records, 0 bad;
  `check_all --only h56-h5` PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r19.json): (1) 2,214 / 3,696 (59.9%), round
  13's weekly sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host 92.6%; (3) 54 routes, 185,654
  records, 0 bad; cheat 15,912, 0 bad. No writer is near the gate.
- **check_all** (F-028, no `--slow`): new row `cheat-endgame` (cheat-bt-endgame is a declared cheat route from
  bt-ch26-clear and has no clear save, like bt-ch27); tests/test_check_all.py 83 OK. Fast 41 pass; touched 4 pass;
  h56-h5 pass. 79 slow/medium rows left for the weekly run.
- **Step 8 (robot): ~88% -> ~90% [low].** Birthright now runs from the start of the game to the title screen after
  the ending. Said plainly: the last chapter's boss fight was finished with a cheat (one poke, Garon's HP to 1), on
  the owner's word that this counts. Every earlier Birthright chapter, and Endgame turns 1 to 7, were real play. The
  real-play key bt-endgame stays unwritten. Conquest and Revelation resume beside this (F-031, other steps).
- **Step 9 (readable):** stays ~26% [low]: 252 readers, all checked by the host test and live compare.
- **Measured (F-027 count, 165 min counted, hard stop 240).** Cheat Endgame play 27 min (cap 60); proof 46 min (cap
  30 + one retry 45; its capture hit its 45-minute cap at 93% and was stopped); integrate about 31 min (cap 60, 75
  with the review). About 104 minutes of step time in all; no hard stop near.
- **Disk:** D: was full during integrate (71 MB free at 16:26). Integrate freed about 790 MB by removing the bulk of
  the stopped proof capture r19-capc-endgame (no summary, no records) and reran the one replay that had failed on
  it. D: still has only about 1-1.5 GB free: the owner should free space before the next long round. [high]
- **Evidence**: `evidence.py pack` (117.4 MB); clean dry run would free 0 items (not run with --yes).
- **Open**: D: almost full; the two new rows of the in-progress batch need their own capture; the [medium]
  instruction-count note at frame 193094 (stage 0 vs the look-ahead chain, which had extra breaks; the two proof
  copies agree with each other); no separate stage-complete screen in Endgame (the "Garon beaten" checkpoint stands
  in); 34 readers never met (36 with the two new rows); 237 equivalent candidates plus 70 unsorted for a person; the
  looks; OK A and OK B open.

## Status update 2026-11-25 (integrate, round 20): Conquest 13-15 and Revelation 18-20, real play, checked together

**In plain words.** Round 20 (F-031, owner 2026-11-17 ~15:20: "yes, start both now, cheats for the finale only";
counted 465 minutes from 15:35, hard stop 600; beside rounds 19, 21 and 22) resumed Conquest and Revelation side by
side, real play, one fresh helper per chapter. **Six chapters were proven with two equal copies and packed:
Conquest 13, 14 and 15, Revelation 18, 19 and 20** (cq-ch13 and rv-ch18 were the chains paused in round 11, already
played to My Castle). Nobody was lost, no poke, no cheat save. Integrate compared **all 54 older real-play routes
offline (185,812 records, 0 bad)** and played the six new routes live with every override: **23,484 records, 2
bad**: two strike_power records on cq-ch13 with a different list of guest calls (same results, same memory; they
match when replayed offline). Not fixed inside integrate's cap. The cheat Endgame route played live again: 6,511
records, 0 bad. Plan total 55.4% -> 55.6% (robot ~90% -> ~92% [low]: six more chapters proven; step 9 unchanged
at ~26%; steps 3, 4, 5, 7 unchanged until the owner looks). Owner report: docs/REPORT_2026-11-25.md.

- **Chapters** (minutes of play / proof, against caps 100 / 45): cq-ch13 17 / 35, cq-ch14 37 / 15, cq-ch15 23 /
  12; rv-ch18 18 / 37, rv-ch19 43 / 8, rv-ch20 40 / 15. No retry needed. Each chapter's own section is in
  docs/ROBOT.md (3z-cq13 to 3z-cq15, and the Round 20 rv-ch18 to rv-ch20 sections).
- **Library**: FRESH (2026-11-17T18:22:15, rebuilt by round 22's capture step; 257 overrides, 3 of them round 22's
  unverified rows). Not rebuilt by integrate.
- **Plan** (build/speed/r20int/): real play PLAN LINE 1, 54 offline, 0 live; PLAN LINE 2, 254 decided, 3 live on
  54 routes (round 22's rows, left to round 22). Cheat PLAN LINE 1, 4 offline, 0 live; PLAN LINE 2, 254 decided, 3
  live on 4 routes (the same). The six new routes had no records (their proof captures kept none) and played live;
  cheat-bt-endgame's records no longer counted (route entry changed after them) and it played live.
- **Per family, real play:** Birthright 33 routes 112,915 records, 0 bad; Conquest 10, 38,150, **2 bad**;
  Revelation 15, 56,219, 0 bad; options 2, 2,012, 0 bad. Cheat apart: 16,231 records, 0 bad.
- **H5** (`r20-h5`): 223 of 257 met, 209,296 records, 0 bad, offline != live 2 (the same two); branches 63.3%.
  `check_all --only h56-h5`: PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r20.json): (1) 2,214 / 3,696 (59.9%), round
  13's weekly sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host 92.6%; (3) 60 routes, 209,296
  records, 2 bad; cheat 0 bad. No writer is near the gate.
- **check_all** (no `--slow`): robot-routes requires the six new clear saves; tests 84 OK. Fast 41 pass; touched 3
  pass; h56-h5 pass.
- **Step 8 (robot): ~90% -> ~92% [low].** Conquest now runs through chapter 15 and Revelation through chapter 20,
  every chapter real play and proven. Missing: the rest of Conquest and Revelation and their Endgames (cheat track
  allowed only there, F-031), a child unit, H6 at its gate.
- **Step 9 (readable):** stays ~26% [low]. strike_power (round 21) now has its first real-play meets beyond bt-ch2,
  on all six new routes, and its first live call-list difference (cq-ch13, 2 records): it needs a fix step.
- **Measured (F-027 count, 465 min counted, hard stop 600).** Conquest chain 139 min of step time, Revelation 161,
  side by side (counted 390); integrate about 46 min (cap 60, counted 75 with the review). Wall time about 15:20 to
  19:20, about 4 h. No cap was hit.
- **Open**: the two strike_power records on cq-ch13 (trace, fix, recapture cq-ch13, then add r20-cap-new to
  the h56-h5 row); round 22's three rows not yet decided on the older routes (round 22's step); the proof captures
  should keep records (`--store-keep --only <all>`) so integrate can replay them offline; docs/ROUTES_SPLIT.md has
  no rv-ch18 section; rv-ch20's veins_used counter stayed 0 with four bridge veins used [med]; the bridge-aware
  danger.py is only in the rv20 scratch copy; 34 readers never met; 237 equivalent candidates plus 70 unsorted for
  a person; the looks; OK A and OK B open.

- **Fix step (19:18 to about 20:20).** The two strike_power records were a capture artifact of Unit::GetAttack's
  entry: its bool was passed as `FE_ARG(2) != 0`, so capture compared r3, which is not an argument (the game leaves
  0x1E there, the readable call 0). The four bool entries in formula_unit.c now pass `FE_ARG(2)` plainly (same
  result; host test 0 mismatches). Library rebuilt; the six new routes captured live again (r20-cap-newb):
  **23,484 records, 0 bad**. H5 r20-h5b: 223 of 257 met, 209,460 records, 0 bad, offline != live 0. Three numbers:
  (1) 59.9%, (2) 92.3% / 92.6%, (3) **60 routes, 209,460 records, 0 bad**; cheat 16,231, 0 bad. Round 20 is done
  with 0 bad. Plan % unchanged by the fix (55.6%).

## Status update 2026-11-26 (integrate, round 21): two reader batches from Grok's REWRITE_ORDER4, checked together

**In plain words.** Round 21 (owner 2026-11-17 ~15:45: "yes, ask Grok and start it"; counted 240 minutes from
15:40, hard stop 360; beside rounds 19 and 20) ran two reader batches from Grok's docs/tracks/REWRITE_ORDER4.md side
by side. Row 1, `strike_power`, is the damage of one strike in a fight or forecast (map::BattleInfo::Side::
GetSimplePower), with every damage skill step (Luna, Dragon Fang, Ignis, Rend Heaven, Vengeance, Astra, Dragonskin,
terrain, the follower half): 35/35 planted bugs caught, 0 mismatches. Row 2, `who_holds_can_equip_subkind`, answers
"may this class hold this kind of weapon or stone" (Job::CanEquipFromSubKind): 24/24, 0 mismatches. Both only read.
Their captures in real play were clean (18 and 140 records, 0 bad), and integrate played both live on the 4 cheat
routes (136 records, 0 bad). Integrate did not rebuild (FRESH), compared **all 54 real-play routes offline:
185,812 records, 0 bad of any kind**, and took about 21 minutes. The whole round used about 1 hour 52 minutes of wall
time against the 240 counted. Plan total stays 55.4% (readable ~26% with 254 readers, two more [low]; step 8 is
rounds 19/20's; steps 3, 4, 5, 7 unchanged until the owner looks). Owner report: docs/REPORT_2026-11-26.md.

- **Library**: FRESH (2026-11-17T16:48:32, rebuilt once by the who_holds capture step; 254 overrides, 54 staged
  files). Not rebuilt by integrate; no reader changed after its capture.
- **Registry**: row 0x005253A8 is now the override strike_power (was the stance helper stance_follow_up_damage,
  which strike_power still calls), as docs/BATTLE2.md section 3 planned. Accepted on review; flagged for the owner.
- **Plan** (build/speed/r21int/): real play, round 18's sessions plus r21-cap-strike and r21-cap-who_holds:
  PLAN LINE 1, 54 offline, 0 live; PLAN LINE 2, 254 decided by the records, 0 live. Cheat: PLAN LINE 1, 4 offline,
  0 live; PLAN LINE 2, 252 decided, 2 live on 4 routes (session r21-capc-readers).
- **Offline**: `r21-off`: 212 runs, **185,812 records (181,029 match, 3,094 gave up, 1,689 incomplete), 0 bad,
  offline verdict != captured verdict: 0**, 165 s. Cheat `r21-offc`: 37 runs, 9,584 records, 0 bad, 34 s.
- **Live (cheat only)**: 4 runs, 58 s; 136 records (130 match, 6 gave up), 0 bad; memory equal to round 18's
  cheat runs; no writer stored; %APPDATA% unchanged.
- **Per family, real play:** Birthright 33 routes 112,915 records; Conquest 7, 26,262; Revelation 12, 44,623;
  options 2, 2,012; **0 bad and 0 other differences in each**. Cheat apart: 4 routes, 9,720 records, 0 bad.
- **H5** (`r21-h5`, `--no-exact`): 220 of 254 met, 185,812 records, 0 bad, offline != live 0; branches 988/1,587
  (62.3%). `check_all --only h56-h5`: PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r21.json): (1) 2,214 / 3,696 (59.9%), round
  13's weekly sample (the two new files are not in it yet); (2) host test alone 3,700 / 4,009 (92.3%), records or
  host 92.6%, 36 files (the two new host tests, 35/35 and 24/24, run in check_all); (3) 54 routes, 185,812 records,
  0 bad; cheat 9,720, 0 bad. No writer is near the gate.
- **check_all** (F-028, no `--slow`): four new rows (strike-diff and -long, who-holds-diff and -long); h56-h5 reads
  16 sessions; tests/test_check_all.py 83 OK. Fast 41 pass; touched rows 6 pass; h56-h5 pass. 78 slow/medium rows
  left for the weekly run.
- **Step 9 (readable):** stays ~26% [low]: 254 readers (two more), all checked by the host test and live compare.
  The one-strike damage line, long listed as "waits", is now readable.
- **Step 8:** rounds 19 and 20's (not changed here). **Steps 3, 4, 5, 7:** unchanged until the owner looks.
- **Measured (F-027 count, 240 min counted, hard stop 360).** strike batch 37 min (cap 80 counted), its review
  about 15-20 min [med] (cap 50), capture 3 min (cap 30); who_holds batch 35 min, review about 10-15 min [med],
  capture 41 min (26 of them waiting for other rounds' robots; over its 30 counted, inside its own 45-minute
  cap); no live fix needed (cap 45 each); integrate about 21 min (cap 60; 35 counted with the review). No cap
  was hit. Wall time 15:35 to about 17:27: about 1 h 52 min.
- **Evidence**: `evidence.py pack` (119.3 MB); `clean --yes --keep-sessions 10` with every r10-r21 session kept
  (0 freed).
- **Open**: strike_power met live on one plain fight route (bt-ch2) and two cheat routes; its skill steps are
  met live only on cheat-skill-proc and fully only in the host test; who_holds' stone sub-kinds (14 to 19) were
  probably not met live; three source comments still say "not rewritten" (fix at the next rebuild);
  forecast_damage stays a test copy; strike.c and who_holds.c not yet in the weekly H6 sample nor in h6host; 34
  readers never met; 237 equivalent candidates plus 70 unsorted for a person; the looks; OK A and OK B open.

## Status update 2026-11-27 (integrate, round 22): two more reader batches from Grok's REWRITE_ORDER4, checked together

**In plain words.** Round 22 (owner 2026-11-17 ~17:30, round 21 continued as round 22; counted 240 minutes from
17:35, hard stop 360; beside round 20) ran Grok's rows 3 and 4 side by side. Row 3, `female`, is "is this unit /
this person female" (Unit::IsFemale and Person::IsFemale): 19/19 planted bugs caught, 0 mismatches. Row 4,
`rod_can_use_target`, is "may this staff be used on this unit" (Rod::CanUseTarget: heal, rescue, warp-type, freeze,
silence, weakness, curse): 42/42 after integrate fixed a gap the second review found in its host test. All three
only read. The female capture was clean (45 records, 0 bad); integrate played the staff reader live on 8 real-play
routes (119 records, 0 bad) and all three on the 4 cheat routes (168 records, 0 bad). Integrate did not rebuild
(FRESH) and compared **all 54 real-play routes: 185,976 records, 0 bad of any kind**. Plan total stays 55.6%
(readable ~26% with 257 readers, three more [low]; step 8 is rounds 19/20's; steps 3, 4, 5, 7 unchanged until the
owner looks). Owner report: docs/REPORT_2026-11-27.md.

- **Library**: FRESH (2026-11-17T18:22:15, rebuilt once by the female capture step; 257 overrides, 65 guard
  users, 56 staged files). Not rebuilt by integrate; no staged file changed after it.
- **rod_target fix (integrate)**: the review's missed plant (resistance halving without the sign) is now caught;
  a negative-amount resistance case and the 42nd plant were added to the host test; 14 seeds 42/42, 0 mismatches.
  The C is unchanged.
- **Plan** (build/speed/r22int/): real play: PLAN LINE 1, 54 offline, 0 live; PLAN LINE 2, 256 decided by the
  records, 1 live (rod_can_use_target), capped at 8 staff routes (F-027). Cheat: PLAN LINE 1, 4 offline, 0 live;
  PLAN LINE 2, 254 decided, 3 live on 4 routes.
- **Offline**: `r22-off`: 213 runs, **185,857 records, 0 bad, offline verdict != captured verdict: 0**, 130 s.
  Cheat `r22-offc`: 44 runs, 9,720 records, 0 bad, 35 s.
- **Live**: `r22-cap-rod_target` 8 routes, 833 s, 119 records (112 match, 7 cold give-ups), 0 bad, met on 7;
  `r22-capc-readers` 4 cheat routes, 161 s, 168 records, 0 bad. Every memory hash equal to earlier runs; no writer
  stored; %APPDATA% unchanged.
- **Per family, real play:** Birthright 33 routes 113,028 records; Conquest 7, 26,297; Revelation 12, 44,639;
  options 2, 2,012; **0 bad and 0 other differences in each**. Cheat apart: 4 routes, 9,888 records, 0 bad.
- **H5** (`r22-h5`, `--no-exact`): 223 of 257 met, 185,976 records, 0 bad, offline != live 0; branches
  1,007/1,617 (62.3%). `check_all --only h56-h5` (19 sessions, r20-cap-newb added by round 20): PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r22.json): (1) 2,214 / 3,696 (59.9%), round
  13's weekly sample (the new files are not in it yet); (2) host test alone 3,700 / 4,009 (92.3%), records or host
  92.6%, 36 files; (3) 54 routes, 185,976 records, 0 bad; cheat 9,888, 0 bad. No writer is near the gate.
- **check_all** (F-028, no `--slow`): four new rows (female-diff and -long, rod-target-diff and -long), the KNOWN
  entry rod-target-not-run for tier 2, h56-h5 two more sessions; tests 84 OK. Fast 41 pass; touched rows 8 pass;
  h56-h5 pass.
- **Step 9 (readable):** stays ~26% [low]: 257 readers (three more), each checked by its host test and a live
  compare. All three stay UNVERIFIED until the owner says otherwise.
- **Step 8:** rounds 19 and 20's (not changed here). **Steps 3, 4, 5, 7:** unchanged until the owner looks.
- **Measured (F-027 count, 240 min counted, hard stop 360).** female batch about 20 min (cap 80 counted), its
  capture 31 min (cap 30 counted, inside its 45-minute cap; about 10 min of it waiting for round 20's robots and
  row 4's registry row); rod_target batch and its first review [time not reported to integrate], its fix pass 37
  min (cap 50); no live fix needed for either (cap 45); integrate about 45 min (19:16 to about 20:01, cap 60),
  which included rod_target's capture (8 routes, 14 min) and the second review's fix. No cap was hit.
- **Evidence**: `evidence.py pack` (127.4 MB); `clean --yes --keep-sessions 10` with every r10-r22 session kept
  (0 freed).
- **Open**: rod_can_use_target is fully NOT-RUN in tier 2 (KNOWN entry); some of its rules (curse, silence,
  freeze on enemies) are met only in the host test; Person::IsFemale is not reached through family_grow on any
  route; equip_use.h and two older comments still say "not rewritten" (fix at the next rebuild); female.c and
  rod_target.c not yet in the weekly H6 sample nor in h6host; strike_power's cq-ch13 call-list finding is round 20's
  (formula_unit.c edited and the library rebuilt at 19:23 by that work, after round 22's runs started); 34 readers never met; 237 equivalent candidates plus 70 unsorted; the looks; OK A and
  OK B open.

## Status update 2026-11-28 (integrate, round 23): the last two reader batches from Grok's REWRITE_ORDER4, checked together

**In plain words.** Round 23 (owner 2026-11-17 20:10, continued as round 23; counted 240 minutes from 20:10, hard
stop 360; beside round 20) ran Grok's rows 5 and 6, the last of his list, side by side. Row 5, `item_enhance`, is
"does this item give its bonus while this unit carries it" (Unit::IsItemEnhanceHave): 29/29 planted bugs caught, 0
mismatches. Row 6, `volume`, is the four "what is this volume" questions of the options screen (Volume*::GetValue
for music, effects, system sounds and voices): 19/19, 0 mismatches. All five only read. Both captures were clean
(30 and 80 records, 0 bad); integrate played all five on the 4 cheat routes (175 records, 0 bad). Integrate did
not rebuild (FRESH) and compared **all 54 real-play routes offline: 186,086 records, 0 bad of any kind**. Plan
total stays 55.6% (readable ~26% with 262 readers, five more [low]; step 8 is rounds 19/20's; steps 3, 4, 5, 7
unchanged until the owner looks). Owner report: docs/REPORT_2026-11-28.md.

- **Library**: FRESH (2026-11-17T20:36:49, rebuilt once by the volume capture step; 262 overrides, 66 guard
  users, 58 staged files). Not rebuilt by integrate; no staged file changed after it.
- **Plan** (build/speed/r23int/): real play: PLAN LINE 1, 54 offline, 0 live; PLAN LINE 2, 262 decided by the
  records, 0 live. Cheat: PLAN LINE 1, 4 offline, 0 live; PLAN LINE 2, 257 decided, 5 live on 4 routes.
- **Offline**: `r23-off`: 222 runs, **186,086 records, 0 bad, offline verdict != captured verdict: 0**, 104 s.
  Cheat `r23-offc`: 51 runs, 9,888 records, 0 bad, 32 s.
- **Live**: `r23-capc-readers` 4 cheat routes, 52 s, 175 records (56 match, 117 gave up, 2 incomplete), 0 bad;
  only unit_item_enhance_have met (the volume readers are not called without the options screen). Every memory
  hash equal to earlier runs; no writer stored; %APPDATA% unchanged.
- **Per family, real play:** Birthright 33 routes 113,058 records; Conquest 7, 26,297; Revelation 12, 44,639;
  options 2, 2,092; **0 bad and 0 other differences in each**. Cheat apart: 4 routes, 10,063 records, 0 bad.
- **H5** (`r23-h5`, `--no-exact`): 228 of 262 met (all five new readers met), 209,570 records, 0 bad, offline !=
  live 0; branches 1,034/1,635 (63.2%). `check_all --only h56-h5` (21 sessions): PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r23.json): (1) 2,214 / 3,696 (59.9%), round
  13's weekly sample (the new files are not in it yet); (2) host test alone 3,700 / 4,009 (92.3%), records or host
  92.6%, 36 files; (3) 54 routes, 186,086 records, 0 bad; cheat 10,063, 0 bad. No writer is near the gate.
- **check_all** (F-028, no `--slow`): four new rows (item-enhance-diff and -long, volume-diff and -long); no new
  KNOWN entry; h56-h5 two more sessions; tests 84 OK. Fast 42 pass; touched rows 7 pass; h56-h5 pass.
- **Step 9 (readable):** stays ~26% [low]: 262 readers (five more), each checked by its host test and a live
  compare. All five stay UNVERIFIED until the owner says otherwise. Grok's REWRITE_ORDER4 list is now done.
- **Step 8:** rounds 19 and 20's (not changed here). **Steps 3, 4, 5, 7:** unchanged until the owner looks.
- **Measured (F-027 count, 240 min counted, hard stop 360).** item_enhance batch about 35 min with its review
  (cap 80 + 50 counted), capture 6 min (cap 30); volume batch about 22 min with its review, capture 9 min
  including the one library rebuild (5 min 21 s); no live fix needed for either (cap 45 each); integrate about 20
  min (20:47 to about 21:07, cap 60; 35 counted with the review). No cap was hit. Wall time about 20:05 to 21:07:
  about 1 h 2 min.
- **Evidence**: `evidence.py pack` (128.3 MB); `clean --yes --keep-sessions 10` with every r10-r23 session kept
  (0 freed).
- **Open**: live records for each new reader cover one path only (item_enhance SHALLOW on bt-ch4: 5 matches; the
  volume readers only the 0xFF "maximum" path), the rest only in the host tests; tier 2 gives GAVE-UP / UNSAMPLED
  for them (made-up state), so it compared nothing; item_enhance.c and volume.c not yet in the weekly H6 sample nor
  in h6host; three source comments still say "not rewritten" (fix at the next rebuild); 34 readers never met; 237
  equivalent candidates plus 70 unsorted; the looks; OK A and OK B open.

## Status update 2026-11-29 (integrate, round 24): Conquest 16 and Revelation 21-24, real play, checked together

**In plain words.** Round 24 (F-031, owner 2026-11-17 ~15:20 "yes, start both now, cheats for the finale only",
continued as round 24 at 20:15; counted 375 minutes from 20:20, hard stop 540; beside rounds 23, 25, 26, 27 and
28) went on with Conquest from chapter 16 and Revelation from chapter 21, real play, one fresh helper per chapter.
**Five chapters were proven with two equal copies and packed: Conquest 16, Revelation 21, 22, 23 and 24.**
Conquest 17 is not cleared (the chain stands at turn 19 against the boss Kotaro). Nobody was lost, no poke, no
cheat save. Integrate compared **all 60 older real-play routes offline (209,652 records, 0 bad)** and played the
five new routes live with every reader: **20,010 records, 0 bad**, every final memory equal to its proof. Plan
total 55.6% -> 55.7% (robot ~92% -> ~93% [low]: five more chapters proven; step 9 unchanged at ~26%; steps 3, 4, 5,
7 unchanged until the owner looks). Owner report: docs/REPORT_2026-11-29.md.

- **Chapters** (minutes of play / proof, against caps 100 / 45): cq-ch16 82 / 25; cq-ch17 not cleared (a first
  try plus a 20-minute retry, chain kept at turn 19); rv-ch21 41 / 17, rv-ch22 35 / 9, rv-ch23 78 / 25, rv-ch24
  57 / 18. Each chapter's own section is in docs/ROBOT.md (3z-cq16, 3z-cq17b, and the Round 24 rv-ch21 to rv-ch24
  sections).
- **Library**: FRESH (2026-11-18T00:03:44, round 27's build; 266 overrides). Not rebuilt by integrate.
- **Plan** (build/speed/r24int/): real play PLAN LINE 1, 54 offline, 0 live; PLAN LINE 2, 266 decided, 0 live.
  Cheat PLAN LINE 1, 4 offline, 0 live; PLAN LINE 2, 266 decided, 0 live. The five new routes had no usable
  records on this library (four proof captures kept none; rv-ch22's ran before rounds 26-27's readers) and played
  live with every reader.
- **Per family, real play:** Birthright 33 routes 113,140 records; Conquest 11, 42,388; Revelation 19, 72,042;
  options 2, 2,092; **0 bad in each**. Cheat apart: 4 routes, 10,452 records, 0 bad.
- **H5** (`r24-h5`): 232 of 266 met, 229,662 records, 0 bad, offline != live 0; branches 64.6%. `check_all --only
  h56-h5` (26 sessions): PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r24.json): (1) 2,214 / 3,696 (59.9%), round
  13's weekly sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host 92.6%; (3) 65 routes, 229,662
  records, 0 bad; cheat 10,452, 0 bad. No writer is near the gate.
- **check_all** (no `--slow`): robot-routes requires the five new clear saves; h56-h5 one more session; tests 85
  OK. Fast 47 pass; touched 3 pass; h56-h5 pass.
- **Step 8 (robot): ~92% -> ~93% [low].** Conquest now runs through chapter 16 and Revelation through chapter 24,
  every chapter real play and proven. Missing: Conquest 17 to 27 and Revelation 25 to 27, their Endgames (cheat
  track allowed only there, F-031; F-033 allows a declared, counted movement cheat in Conquest from chapter 17), a
  child unit, H6 at its gate.
- **Step 9 (readable):** stays ~26% [low]; no reader changed this round.
- **Measured (F-027 count, 375 min counted, hard stop 540).** Conquest: 107 min of proven step time plus the
  unfinished chapter 17; Revelation: 280 min of step time; side by side. Integrate about 36 min (01:39 to about
  02:15, cap 60; 75 counted with the review). Wall time 20:20 to about 02:15, about 5 h 55 min: under the count. No
  play or proof cap was hit; cq-ch17's retry stopped inside its cap without a clear.
- **Open**: cq-ch17; the proof steps should keep records (`--store-keep --only all`); evidence clean refused while
  another helper's boot.exe ran (nothing removed); whether Shura joined in cq-ch16 is not checked; Revelation has
  only Mend (Elise) as a working staff; the danger-tool patches for C023 and C024 are scratch copies; 34 readers
  never met; 237 equivalent candidates plus 70 unsorted; the looks; OK B open.

## Status update 2026-11-30 (integrate, round 25): two reader batches from Grok's REWRITE_ORDER5, checked together

**In plain words.** Round 25 (owner 2026-11-17 21:15, continued as round 25; counted 240 minutes from 21:15, hard
stop 360; beside round 24) ran Grok's new list, rows 1 and 2, side by side. Row 1, `job_female`, is "is this class
the female one" (Job::IsFemale): 13/13 planted bugs caught, 0 mismatches, now an override that only reads. Row 2,
`job_record`, is "the class record for a class number" (Job::Get): 18/18, 0 mismatches, but it is kept as a helper,
not an override, because the deep check cannot pick its address (another function runs straight into it, the
UnitPool::Get shape). So the game still runs its own Job::Get, and AIValue::GetJob stays blocked. The job_female
capture was clean (20 records, 0 bad); integrate played it on the 4 cheat routes (131 records, 0 bad). Integrate did
not rebuild (FRESH) and compared **all 60 real-play routes offline: 209,590 records, 0 bad of any kind**. Plan total
stays 55.6% (readable ~26% with 263 readers, one more [low]; step 8 is rounds 19/20's; steps 3, 4, 5, 7 unchanged
until the owner looks). Owner report: docs/REPORT_2026-11-30.md.

- **Library**: FRESH (2026-11-17T21:36:37, rebuilt once by the job_female capture step; 263 overrides, 67 guard
  users, 60 staged files). Not rebuilt by integrate.
- **Plan** (build/speed/r25int/): real play: PLAN LINE 1, 54 offline, 0 live; PLAN LINE 2, 263 decided by the
  records, 0 live. Cheat: PLAN LINE 1, 4 offline, 0 live; PLAN LINE 2, 262 decided, 1 live on 4 routes.
- **Offline**: `r25-off`: 229 runs, **209,590 records, 0 bad, offline verdict != captured verdict: 0**, 147 s.
  Cheat `r25-offc`: 58 runs, 10,063 records, 0 bad, 62 s.
- **Live**: `r25-capc-readers` 4 cheat routes, 84 s, 131 records (127 match, 4 gave up), 0 bad. Every memory hash
  equal to earlier runs; no writer stored; %APPDATA% unchanged.
- **Per family, real play:** Birthright 33 routes 113,078 records; Conquest 10, 38,185; Revelation 15, 56,235;
  options 2, 2,092; **0 bad and 0 other differences in each**. Cheat apart: 4 routes, 10,194 records, 0 bad.
- **H5** (`r25-h5`, `--no-exact`): 229 of 263 met (job_female met), 209,590 records, 0 bad, offline != live 0;
  branches 1,036/1,637 (63.3%). `check_all --only h56-h5` (22 sessions): PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r25.json): (1) 2,214 / 3,696 (59.9%), round
  13's weekly sample (the new files are not in it yet); (2) host test alone 3,700 / 4,009 (92.3%), records or host
  92.6%, 36 files; (3) 60 routes, 209,590 records, 0 bad; cheat 10,194, 0 bad. No writer is near the gate.
- **check_all** (F-028, no `--slow`): four new rows (job-female-diff and -long, job-record-diff and -long); no new
  KNOWN entry; h56-h5 one more session; tests 84 OK. Fast 44 pass; touched rows 7 pass; h56-h5 pass.
- **Step 9 (readable):** stays ~26% [low]: 263 readers (one more) plus one more checked helper. job_female stays
  UNVERIFIED until the owner says otherwise. REWRITE_ORDER5 rows 3-5 wait (row 3 may start now that row 1 is green).
- **Step 8:** rounds 19/20's (round 24 continues it; not changed here). **Steps 3, 4, 5, 7:** unchanged until the
  owner looks.
- **Measured (F-027 count, 240 min counted, hard stop 360).** job_female batch 15 min (21:15-21:30) with its review
  inside the count, capture 12 min including the one library rebuild (6 min 21 s); job_record batch about 30 min,
  no capture possible (helper); no live fix needed (cap 45 each); integrate about 20 min (21:48 to about 22:08,
  cap 60; 35 counted with the review). No cap was hit. Wall time about 21:15 to 22:08: about 53 min.
- **Evidence**: `evidence.py pack` (131.1 MB); `clean` refused while round 24's boot.exe runs (not forced).
- **Open**: job_record is a helper, not an override (tier 2 cannot check a fall-through target: a classifier or
  pipeline change for the owner); job_female live records cover the bt-ch4 battle-name path and the 4 cheat routes,
  not the class-change, swimwear or hot-spring callers; tier 2 reached only job_female's give-up path; the new files
  are not in the weekly H6 sample nor h6host; evidence clean waits; three older source comments still say "not
  rewritten" (fix at the next rebuild); 34 readers never met; 237 equivalent candidates plus 70 unsorted; the looks;
  OK A and OK B open.

## Status update 2026-12-01 (integrate, round 26): two more reader batches from Grok's REWRITE_ORDER5, checked together

**In plain words.** Round 26 (owner 2026-11-17 22:15, continued as round 26; counted 240 minutes from 22:15, hard
stop 360; beside round 24) ran Grok's list, rows 5 and 3, side by side. Row 5, `key_door`, is "can this unit open a
door" (Unit::CanKeyDoor): 18/18 planted bugs caught, 0 mismatches, now an override that only reads. Row 3,
`skill_record`, is "the skill record for a skill label" (EquipSkill::Get(const char*), 514 call sites): 20/20, 0
mismatches, now an override that only reads; it does the whole ID hash lookup in C and never gives up. Both batch
captures on Birthright chapter 4 were clean (key_door 20 records, 19 match, 1 cold give-up; skill_record 22 of 22
match). Integrate played both on the 4 cheat routes (127 records, 0 bad), did not rebuild (FRESH) and compared
**all 60 real-play routes offline: 209,632 records, 0 bad of any kind**. Plan total stays 55.6% (readable ~26% with
265 readers, two more [low]; step 8 is rounds 19/20's; steps 3, 4, 5, 7 unchanged until the owner looks). Owner
report: docs/REPORT_2026-12-01.md.

- **Library**: FRESH (2026-11-17T22:37:58, rebuilt once by the key_door capture step; 265 overrides, 68 guard
  users, 62 staged files). Not rebuilt by integrate.
- **Plan** (build/speed/r26int/): real play: PLAN LINE 1, 54 offline, 0 live; PLAN LINE 2, 265 decided by the
  records, 0 live. Cheat: PLAN LINE 1, 4 offline, 0 live; PLAN LINE 2, 263 decided, 2 live on 4 routes.
- **Offline**: `r26-off`: 231 runs, **209,632 records, 0 bad, offline verdict != captured verdict: 0**, 165 s.
  Cheat `r26-offc`: 65 runs, 10,194 records, 0 bad, 53 s.
- **Live**: `r26-capc-readers` 4 cheat routes, 53 s, 127 records (124 match, 2 gave up, 1 incomplete), 0 bad.
  Every memory hash equal to earlier runs; no writer stored; %APPDATA% unchanged.
- **Per family, real play:** Birthright 33 routes 113,120 records; Conquest 10, 38,185; Revelation 15, 56,235;
  options 2, 2,092; **0 bad and 0 other differences in each**. Cheat apart: 4 routes, 10,321 records, 0 bad.
- **H5** (`r26-h5`, `--no-exact`): 231 of 265 met (both new readers met), 209,632 records, 0 bad, offline != live
  0; branches 1,040/1,641 (63.4%). `check_all --only h56-h5` (24 sessions): PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r26.json): (1) 2,214 / 3,696 (59.9%), round
  13's weekly sample (the new files are not in it yet); (2) host test alone 3,700 / 4,009 (92.3%), records or host
  92.6%, 36 files; (3) 60 routes, 209,632 records, 0 bad; cheat 10,321, 0 bad. No writer is near the gate.
- **check_all** (F-028, no `--slow`): four new rows (key-door-diff and -long, skill-record-diff and -long); no new
  KNOWN entry; h56-h5 two more sessions; tests 84 OK. Fast 46 pass; touched rows 7 pass; h56-h5 pass.
- **Step 9 (readable):** stays ~26% [low]: 265 readers (two more) plus one checked helper. Both new readers stay
  UNVERIFIED until the owner says otherwise. REWRITE_ORDER5: rows 1, 2, 3, 5 done; row 4 (Person::Get) is left,
  and it can reuse skill_record.c's static IdentHash::GetSurely step.
- **Step 8:** rounds 19/20's (round 24 continues it; not changed here). **Steps 3, 4, 5, 7:** unchanged until the
  owner looks.
- **Measured (F-027 count, 240 min counted, hard stop 360).** key_door batch about 15 min with its review inside
  the count, capture 14 min including the one library rebuild (7 min 15 s); skill_record batch about 35 min
  (22:13-22:48) with one verify fix inside, capture 5 min (no rebuild); no live fix needed (cap 45 each);
  integrate about 22 min (22:58 to about 23:20, cap 60; 35 counted with the review). No cap was hit. Wall time
  about 22:13 to 23:20: about 1 h 7 min.
- **Evidence**: `evidence.py pack` (133.2 MB); `clean --yes --keep-sessions 10` with every r10-r26 session kept
  (0 freed).
- **Open**: key_door was met live only through the AI deploy-move caller on bt-ch4 and 2 cheat routes (the door
  map and the other two AI callers are not known to be on any route); skill_record's null-label and 0-bucket paths
  are checked only by the host test and tier 2; tier 2 for key_door reached only the give-up path; the new files
  are not in the weekly H6 sample nor h6host; five source comments (skills.h, class_change.h and the three older
  ones) still say "not rewritten" (fix at the next rebuild); 34 readers never met; 237 equivalent candidates plus
  70 unsorted; the looks; OK A and OK B open.

## Status update 2026-12-02 (integrate, round 27): the last reader from Grok's REWRITE_ORDER5, checked

**In plain words.** Round 27 (owner 2026-11-17 23:25, continued as round 27; counted 240 minutes from 23:25, hard
stop 360; beside round 24) ran Grok's list, row 4, the last named reader. `person_record` is "the person record for
a person name" (Person::Get(const char*)): 38/38 planted bugs caught, 0 mismatches, now an override that only
reads; it does the whole ID hash lookup in C and never gives up. The number version (Person::Get(unsigned short))
is a tested helper, not an override, because another function runs into it. The batch capture on Birthright
chapter 6 with a My Castle visit was clean (20 of 20 match). Integrate played it on the 4 cheat routes (131
records, 0 bad), did not rebuild (FRESH) and compared **all 60 real-play routes offline: 209,652 records, 0 bad of
any kind**. All five rows of REWRITE_ORDER5 are done. Plan total stays 55.6% (readable ~26% with 266 readers, one
more [low]; step 8 is rounds 19/20's; steps 3, 4, 5, 7 unchanged until the owner looks). Owner report:
docs/REPORT_2026-12-02.md.

- **Library**: FRESH (2026-11-18T00:03:44, rebuilt once by the capture step; 266 overrides, 68 guard users, 63
  staged files). Not rebuilt by integrate.
- **Plan** (build/speed/r27int/): real play: PLAN LINE 1, 54 offline, 0 live; PLAN LINE 2, 266 decided by the
  records, 0 live. Cheat: PLAN LINE 1, 4 offline, 0 live; PLAN LINE 2, 265 decided, 1 live on 4 routes.
- **Offline**: `r27-off`: 232 runs, **209,652 records, 0 bad, offline verdict != captured verdict: 0**, 147 s.
  Cheat `r27-offc`: 72 runs, 10,321 records, 0 bad, 58 s.
- **Live**: `r27-capc-readers` 4 cheat routes, 44 s, 131 records (129 match, 2 incomplete), 0 bad. Every memory
  hash equal to earlier runs; no writer stored; %APPDATA% unchanged.
- **Per family, real play:** Birthright 33 routes 113,140 records; Conquest 10, 38,185; Revelation 15, 56,235;
  options 2, 2,092; **0 bad and 0 other differences in each**. Cheat apart: 4 routes, 10,452 records, 0 bad.
- **H5** (`r27-h5`, `--no-exact`): 232 of 266 met (the new reader met), 209,652 records, 0 bad, offline != live 0;
  branches 1,040/1,641 (63.4%). `check_all --only h56-h5` (25 sessions): PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r27.json): (1) 2,214 / 3,696 (59.9%), round
  13's weekly sample (the new file is not in it yet); (2) host test alone 3,700 / 4,009 (92.3%), records or host
  92.6%, 36 files; (3) 60 routes, 209,652 records, 0 bad; cheat 10,452, 0 bad. No writer is near the gate.
- **check_all** (F-028, no `--slow`): two new rows (person-record-diff and -long); no new KNOWN entry; h56-h5 one
  more session; tests 84 OK. Fast 47 pass; touched rows 5 pass; h56-h5 pass.
- **Step 9 (readable):** stays ~26% [low]: 266 readers (one more) plus two checked helpers (job_record_get,
  person_record_get). The new reader stays UNVERIFIED until the owner says otherwise. REWRITE_ORDER5: all five
  rows done. AIValue::GetPerson / AIValue::GetJob stay off (both number lookups are helpers).
- **Step 8:** rounds 19/20's (round 24 continues it; not changed here). **Steps 3, 4, 5, 7:** unchanged until the
  owner looks.
- **Measured (F-027 count, 240 min counted, hard stop 360).** Batch about 22 min (23:25-23:47) with its review
  inside the count; capture 18 min (23:54-00:12), of which about 9 min waiting for round 24's proof to exit and
  5 min 38 s for the one library rebuild; no live fix needed (cap 45); integrate about 20 min (00:12 to about
  00:32, cap 60; 40 counted with the review). No cap was hit. Wall time about 23:25 to 00:32: about 1 h 7 min.
- **Evidence**: `evidence.py pack` (135.2 MB); `clean --yes --keep-sessions 10` with every r10-r27 session kept
  (0 freed).
- **Open**: person_record_by_name was met live on one real-play route (bt-ch6-castle) and the 4 cheat routes; its
  found and not-found paths are otherwise checked by the host test; tier 2 is a smoke test (only the not-found
  path); the IdentHash::GetSurely step now lives as two identical static copies (skill_record.c, person_record.c);
  skill_record_diff.py lacks the new draw-again guard; the new file is not in the weekly H6 sample nor h6host; five
  source comments still say "not rewritten" (fix at the next rebuild); 34 readers never met; 237 equivalent
  candidates plus 70 unsorted; the looks; OK A and OK B open.

## Status update 2026-12-03 (integrate, round 28): OK A stopped at the host test; W1/W2 are not written

**In plain words.** The owner said "Yes, OK A" (F-032, 2026-11-18 ~01:00): test the options writers in the robot's
own test game only. Round 28 started at 01:10 (counted 300 minutes, hard stop 7 h) and stopped at its first step.
The host test could not run, because the two pieces it tests, W1 (`config_options_hook`) and W2
(`config_serialize_guard`), and the options file reader (`src/readable/core/options.c`) are not written; they are
design only (docs/OPTIONS_WIRING.md section 4, F-021). The one writer that does exist, `config_write_options`,
passed its host test on seeds 1 and 2 (600 cases each, 0 mismatches, 25/25 planted bugs caught). Nothing was armed
or built. Plan total stays 55.6%; step 9 does not move (no measured writer pass). Owner report:
docs/REPORT_2026-12-03.md.

- **Host test for W1/W2:** NOT RUN (no code). **T1-T7:** NOT RUN. **OK A checklist:** not green.
- **The gate (F-026) for W1/W2, three numbers kept apart:** (1) recordings on reached lines: none (W1/W2 have no
  lines; never reached is not a failure); (2) host test with planted bugs: not run (no code); (3) live/armed compare
  T1, T2, T5, T6: not run. For `config_write_options` alone, (2) is 25/25 on both seeds.
- **Safety checked by command:** tracked writer.c table unarmed (`git diff` empty; only `{"config_options", 0}`);
  build/oka does not exist; build/harness/lib not replaced (library dll from 00:09, before this round);
  %APPDATA% Zakuro/Azahar folders unchanged (dates 2026-11-10 and 2026-10-28); no owner file touched; routes.json
  has no OK A `opt-*` route and no real-play route starts from an `opt-*` save.
- **check_all:** two new rows, `oka-host-seed1` and `oka-host-seed2` (lock `readable:writers`); tests 84 OK; fast 47
  pass; touched rows 3 pass.
- **Docs:** OPTIONS_WIRING.md section 11 (status), ROBOT.md (no opt-* run; the rules), CHECK_ALL.md round 28.
- **Open:** W1, W2, options.c and their host test (every section 7 plant and the suspend save order) need the
  owner to decide who writes them and when; the OK A checklist's line "already written and switched off" is wrong
  for W1/W2; the robot has no save mark / real-play refusal for OK A saves yet (needed before the first OK A run).

## Status update 2026-12-04 (integrate, round 29): Conquest 17 on the cheat track (F-033), proven; Conquest 18 not cleared

**In plain words.** Round 29 (F-033, owner 2026-11-18 ~01:15: "just maximize movement options for conquest to make
sure the combat and animations etc work, those are what we're testing anyways"; counted 495 minutes from 01:20,
hard stop 660; beside rounds 24, 28 and 30) took Conquest on from chapter 17 with a declared movement cheat: every
unit's move bonus (Unit+0x12C) raised, nothing else poked, and the routes scored apart as cheat routes. **One
chapter was proven: Conquest 17 (`cheat-cq-ch17`)**, played to the castle in 23 turns with nobody lost, two equal
copies, its clear save packed with the cheat mark. **Conquest 18 is not cleared**: two helpers reached turn 11 of
20 with all 14 units alive and the throne room taken; the generals boss pair is left. Conquest 19 to 22 were not
started. Integrate compared **all 65 real-play routes offline (229,662 records, 0 bad)**, played cheat-cq-ch17 live
once with every reader so its records are kept (**11,340 records, 0 bad**, final memory equal to the proof), and
replayed the **5 cheat routes apart: 21,792 records, 0 bad**. Plan total stays 55.7% (robot ~93% -> ~93.2% [low]:
one Conquest chapter proven, cheat-labelled and counted per F-033; step 9 unchanged at ~26%; steps 3, 4, 5, 7
unchanged until the owner looks). Owner report: docs/REPORT_2026-12-04.md.

- **Chapters** (minutes against caps): cheat-cq-ch17 play 41 of 100 (01:09-01:50; replay checks and route to
  02:20), proof and capture about 40 of 45 (to 02:46); cheat-cq-ch18 play 54 of 100 (02:48-03:42) plus retry 41 of 60
  (03:43-04:24), not cleared, no proof; Conquest 19 to 22 not started. Sections: docs/ROBOT.md 3z-cq17c, 3z-cq18,
  3z-cq18b.
- **Library**: FRESH (2026-11-18T00:03:44, round 27's build; 266 overrides). Not rebuilt.
- **Plan** (build/speed/r29int/): real play PLAN LINE 1, 54 offline, 0 live; PLAN LINE 2, 266 decided, 0 live. Cheat:
  the proof capture kept no records, so cheat-cq-ch17 played live once (`r29-capc-cheat-cq-ch17`, `--store-keep`);
  then cheat PLAN LINE 1, 4 offline plus cheat-cq-ch17 from its new records, 0 live; PLAN LINE 2, 266 decided, 0
  live.
- **Per family, real play:** Birthright 33 routes 113,140 records; Conquest 11, 42,388; Revelation 19, 72,042;
  options 2, 2,092; **0 bad in each**. Cheat apart: 5 routes, 21,792 records, 0 bad.
- **H5** (`r29-h5`): 232 of 266 met, 229,662 records, 0 bad, offline != live 0; branches 64.6%. `check_all --only
  h56-h5`: PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r29.json): (1) 2,214 / 3,696 (59.9%), round
  13's weekly sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host 92.6%; (3) 65 routes, 229,662
  records, 0 bad; cheat 5 routes, 21,792, 0 bad. No writer is near the gate.
- **check_all** (no `--slow`): new fast row `cheat-conquest` (cheat-cq-ch17 and its packed cheat clear save); tests
  89 OK. Fast 48 pass; touched 5 pass; h56-h5 pass.
- **Step 8 (robot): ~93% -> ~93.2% [low].** Conquest runs through chapter 16 in real play and chapter 17 on the cheat
  track (F-033, labelled and counted); Revelation through chapter 24. Missing: Conquest 18 to 27 (cheat track, F-033)
  and its Endgame, Revelation 25 to 27 and its Endgame, a child unit, H6 at its gate.
- **Step 9 (readable):** stays ~26% [low]; no reader changed this round.
- **Measured (F-027 count, 495 min counted, hard stop 660).** Play, proof and retry about 3 h 15 of wall time (01:09
  to 04:24); integrate about 25 min (04:25 to about 04:50, cap 60). Wall time about 3 h 45, under the count because
  chapter 18 was not cleared and chapters 19 to 22 never started.
- **Open**: cheat-cq-ch18 (continue from build/speed/cqx18/h or i, turn 11); Conquest 19 to 22 and its Endgame;
  proof captures should keep records (`--only all --store-keep`); 34 readers never met; 237 equivalent candidates
  plus 70 unsorted; the looks; OK B open.

## Status update 2026-12-05 (integrate, round 30): Revelation 25 tried in real play, not cleared; everything checked

**In plain words.** Round 30 (F-031 and F-030, owner 2026-11-18 02:25: Revelation 25 to 27 in real play, then
Revelation's Endgame on the cheat track; counted 315 minutes from 02:25, hard stop 480; beside rounds 28 and 29)
**proved no chapter.** Revelation 25 "Blades Drawn" is a map of moving floors, three dragon-vein locks and a boss room
that moves only when all three are released. Two fresh helpers played 38 turns in real play (63 + 22 minutes) with
nobody lost in the kept chain and all three veins used, but stopped before the boss: at turn 39 Leo is cornered at
7 HP by a late reinforcement wave, so the next try restarts from the kept turn-33 state. Revelation 26, 27 and the
cheat Endgame were not started. Integrate compared **all 65 real-play routes offline (229,662 records, 0 bad)** and
the 4 cheat routes apart (10,452 records, 0 bad); nothing had to play live. Plan total stays 55.7% (robot stays ~93%
[low]: no chapter proven, no cheat ending; step 9 unchanged at ~26%; steps 3, 4, 5, 7 unchanged until the owner
looks). Owner report: docs/REPORT_2026-12-05.md.

- **Chapters** (minutes against caps): rv-ch25 play 63 of 100, retry 22 of 60, not cleared, no proof; rv-ch26,
  rv-ch27 (100 + 30 each) and the finale (90) not started. Section: docs/ROBOT.md "Round 30: Revelation chapter 25".
- **Library**: FRESH (2026-11-18T00:03:44, round 27's build; 266 overrides). Not rebuilt.
- **Plan** (build/speed/r30int/): real play PLAN LINE 1, 54 offline, 0 live; PLAN LINE 2, 266 decided, 0 live (the
  five round 24 routes now replay from r24-capn's kept records). Cheat PLAN LINE 1, 4 offline, 0 live; PLAN LINE 2,
  266 decided, 0 live.
- **Per family, real play:** Birthright 33 routes 113,140 records; Conquest 11, 42,388; Revelation 19, 72,042;
  options 2, 2,092; **0 bad in each**. Cheat apart: 4 routes, 10,452 records, 0 bad.
- **H5** (`r30-h5`): 232 of 266 met, 229,662 records, 0 bad, offline != live 0; branches 64.6%. `check_all --only
  h56-h5`: PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r30.json): (1) 2,214 / 3,696 (59.9%), round
  13's weekly sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host 92.6%; (3) 65 routes, 229,662
  records, 0 bad; cheat 10,452, 0 bad. No writer is near the gate.
- **check_all** (no `--slow`): no row changed; tests 85 OK. Fast 47 pass; touched 3 pass; h56-h5 pass.
- **Step 8 (robot): stays ~93% [low].** Revelation runs through chapter 24 in real play, Conquest through chapter 16
  (chapter 17 on the cheat track is round 29's). Missing: Revelation 25 to 27 and its Endgame (cheat track allowed
  there, F-030/F-031), the rest of Conquest and its Endgame, a child unit, H6 at its gate.
- **Step 9 (readable):** stays ~26% [low]; no reader changed this round.
- **Measured (F-027 count, 315 min counted, hard stop 480).** Play and retry 85 min of step time (02:19 to 03:46);
  integrate about 20 min (03:42 to about 04:02, cap 60; 45 counted with the review). Wall time about 1 h 45 min,
  far under the count because the first chapter was not cleared and the later steps never started.
- **Open**: rv-ch25 (restart from build/speed/rv25/c25_t33_backup; get Leo out of the dead-end vein tile before the
  third vein); rv-ch26, rv-ch27, cheat-rv-endgame; h6three's default `--live` adds round 13's file when no live run
  is given (pass an empty `--live`); 34 readers never met; 237 equivalent candidates plus 70 unsorted; the looks;
  OK B open.

## Status update 2026-12-06 (integrate, round 31): Revelation 25 and 26 proven in real play; 27 not cleared

**In plain words.** Round 31 (F-031 and F-030, owner 2026-11-18 02:25: Revelation 25 to 27 in real play, then
Revelation's Endgame on the cheat track; counted 315 minutes from 04:10, hard stop 480; beside round 29) **proved two
chapters in real play: Revelation 25 "Blades Drawn" and Revelation 26 "The Vallite King"**, each with nobody lost,
two equal proof copies, a packed clear save and a capture with every override (0 bad). **Revelation 27 is not
cleared**: two helpers reached turn 26 with all six alive, but the board was too dangerous to finish inside the cap;
the turn-26 state is kept. The cheat Endgame was not started (it needs chapter 27 won first). Integrate compared
**all 67 real-play routes offline (238,051 records, 0 bad)** and the 5 cheat routes apart (21,792 records, 0 bad);
nothing had to play live. Plan total stays 55.7% (robot ~93.2% -> ~93.6% [low]: two Revelation chapters proven, no
cheat ending yet; step 9 unchanged at ~26%; steps 3, 4, 5, 7 unchanged until the owner looks). Owner report:
docs/REPORT_2026-12-06.md.

- **Chapters** (minutes against caps): rv-ch25 play 48 of 100 (from round 30's turn-33 backup), proof 35 of 45;
  rv-ch26 play 60 of 100, proof 24 of 45; rv-ch27 play 67 of 100 (stopped at turn 35) and retry 28 of 60 (from the turn-20 backup, stopped at turn 27), not cleared;
  finale 4 of 90 (stopped at step 1: chapter 27 not cleared). Sections: docs/ROBOT.md rv-ch25 CLEARED, rv-ch26,
  rv-ch27.
- **Library**: FRESH (2026-11-18T00:03:44, round 27's build; 266 overrides). Not rebuilt; the proof captures count.
- **Plan** (build/speed/r31int/): real play PLAN LINE 1, 54 offline, 0 live; PLAN LINE 2, 266 decided, 0 live (the
  two new routes replay from their proof captures). Cheat PLAN LINE 1, 4 offline, 0 live; PLAN LINE 2, 266 decided,
  0 live (cheat-cq-ch17 from r29-capc-cheat-cq-ch17).
- **Per family, real play:** Birthright 33 routes 113,140 records; Conquest 11, 42,388; Revelation 21, 80,431;
  options 2, 2,092; **0 bad in each**. Cheat apart: 5 routes, 21,792 records, 0 bad.
- **H5** (`r31-h5`): 233 of 266 met (new: `script_terrain_out_of_play_area`), 238,051 records, 0 bad, offline !=
  live 0; branches 64.6%. `check_all --only h56-h5`: PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r31.json): (1) 2,214 / 3,696 (59.9%), round
  13's weekly sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host 92.6%; (3) 67 routes, 238,051
  records, 0 bad; cheat 21,792, 0 bad. No writer is near the gate.
- **check_all** (no `--slow`): robot-routes requires rv-ch25-clear and rv-ch26-clear; h56-h5 has 28 sessions; tests
  90 OK. Fast 48 pass; touched 4 pass; h56-h5 pass.
- **Step 8 (robot): ~93.2% -> ~93.6% [low].** Revelation runs through chapter 26 in real play, Conquest through
  chapter 16 (17 on the cheat track). Missing: Revelation 27 and its Endgame (cheat track allowed there,
  F-030/F-031), the rest of Conquest and its Endgame, a child unit, H6 at its gate.
- **Step 9 (readable):** stays ~26% [low]; no reader changed this round.
- **Measured (F-027 count, 315 min counted, hard stop 480).** About 5 h 8 min of wall time from 04:08 to about 09:16, inside the 315 counted;
  integrate about 20 minutes (08:56 to about 09:16, cap 60).
- **Open**: rv-ch27 (restart from build/speed/rv27/c27r_t26_backup); cheat-rv-endgame; 33 readers never met; 237
  equivalent candidates plus 70 unsorted; the looks; OK B open.

## Status update 2026-12-07 (integrate, round 32): Conquest 18 and 19 on the cheat track (F-033), proven; 20 not cleared

**In plain words.** Round 32 (F-033 with F-031: Conquest goes on from chapter 18 on the cheat track, counted;
counted 495 minutes from 05:00, hard stop 660; beside round 31) **proved two chapters: Conquest 18 (`cheat-cq-ch18`)
and Conquest 19 (`cheat-cq-ch19`)**, each with nobody lost, two equal proof copies, a clear save packed with the
cheat mark and a capture with every override (0 bad). Neither used a new poke: each started from the chapter before's
cheat clear save, which already holds round 29's movement bonus, so they count as cheat routes. **Conquest 20 is not
cleared**: two helpers got through turns 1 to 8 with all 14 alive and stopped at the start of turn 9 with 17 enemies
and the boss left; the chain is kept. Conquest 21 to 23 were not started. Integrate compared **all 67 real-play routes
offline (238,051 records, 0 bad)**, played the two new chapters live once with every reader so their records are
kept (**4,253 and 4,032 records, 0 bad**, final memory equal to the proofs), and replayed the **7 cheat routes apart:
30,077 records, 0 bad**. Plan total stays 55.7% (robot ~93.6% -> ~94.0% [low]: two Conquest chapters proven,
cheat-labelled and counted per F-033; step 9 unchanged at ~26%; steps 3, 4, 5, 7 unchanged until the owner looks).
Owner report: docs/REPORT_2026-12-07.md.

- **Chapters** (minutes against caps): cheat-cq-ch18 play 39 of 100 (04:53-05:32, 13 of them a rebuild; replay
  checks and route to about 06:00), proof 26 of 45 (05:55-06:21); cheat-cq-ch19 play 46 of 100 (06:20-07:06; checks
  to about 07:30), proof 29 of 45 (to about 07:57); cheat-cq-ch20 play 41 of 100 (07:57-08:38) and retry 28 of 60
  (08:42-09:10), not cleared, no proof; Conquest 21 to 23 not started. Sections: docs/ROBOT.md 3z-cq18c, 3z-cq19,
  3z-cq20.
- **Library**: FRESH (2026-11-18T00:03:44, round 27's build; 266 overrides). Not rebuilt.
- **Plan** (build/speed/r32int/): real play PLAN LINE 1, 54 offline, 0 live; PLAN LINE 2, 266 decided, 0 live. The
  proof captures kept no records, so both new cheat chapters played live once with `--store-keep`
  (r32-capc-cheat-cq-ch18/19); then cheat PLAN LINE 1, 4 offline plus the three cheat-cq routes from their records, 0
  live; PLAN LINE 2, 266 decided, 0 live.
- **Per family, real play:** Birthright 33 routes 113,140 records; Conquest 11, 42,388; Revelation 21, 80,431;
  options 2, 2,092; **0 bad in each**. Cheat apart: 7 routes, 30,077 records, 0 bad.
- **H5** (`r32-h5`): 233 of 266 met, 238,051 records, 0 bad, offline != live 0; branches 64.6%. `check_all --only
  h56-h5`: PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r32.json): (1) 2,214 / 3,696 (59.9%), round
  13's weekly sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host 92.6%; (3) 67 routes, 238,051
  records, 0 bad; cheat 30,077, 0 bad. No writer is near the gate.
- **check_all** (no `--slow`): cheat-conquest lists cheat-cq-ch17, ch18 and ch19 (a chapter from a listed cheat
  clear save may declare no pokes); tests 92 OK. Fast 48 pass; touched 5 pass; h56-h5 pass.
- **Step 8 (robot): ~93.6% -> ~94.0% [low].** Conquest runs through chapter 16 in real play and chapters 17 to 19 on
  the cheat track (F-033, cheat-labelled, counted); Revelation through chapter 26 in real play. Missing: Conquest 20
  to 27 and its Endgame, Revelation 27 and its Endgame, a child unit, H6 at its gate.
- **Step 9 (readable):** stays ~26% [low]; no reader changed this round.
- **Measured (F-027 count, 495 min counted, hard stop 660).** About 4 h 47 min of wall time from 04:53 to about
  09:40, well inside the count, because chapter 20 was not cleared and chapters 21 to 23 never started; integrate
  about 21 minutes (09:19 to about 09:40, cap 60).
- **Open**: cheat-cq-ch20 (continue from build/speed/cqx20/h or i at frame 124358, turn 9); Conquest 21 to 27 and
  its Endgame; proof captures should keep records (`--only all --store-keep`); 33 readers never met; 237 equivalent
  candidates plus 70 unsorted; the looks; OK B open.

## Status update 2026-12-08 (integrate, round 33): Revelation 27 tried again in real play, not cleared; everything checked

**In plain words.** Round 33 (F-031 and F-030, owner 2026-11-18 02:25: Revelation 27 in real play, then Revelation's
Endgame on the cheat track; counted 315 minutes from 09:20, hard stop 480; beside round 34) **proved no chapter**. A
fresh helper played Revelation 27 for real from the turn-34 state, got past the turn-34 trap and played to the start
of turn 41 with all six alive, but the boss was still about 20 tiles away when its time ran out; the turn-41 state is
kept. The cheat Endgame was not started (it needs chapter 27 won first). The checking library was rebuilt because
F-034's new (switched off) writer files had made it stale; the reader list did not change. Integrate compared **all
67 real-play routes offline (238,051 records, 0 bad)** and the 7 cheat routes apart (30,077 records, 0 bad); nothing
had to play live. Plan total stays 55.7% (robot stays ~94.0% [low]: nothing new proven; step 9 unchanged at ~26%;
steps 3, 4, 5, 7 unchanged until the owner looks). Owner report: docs/REPORT_2026-12-08.md.

- **Chapters** (minutes against caps): rv-ch27 play 36 of 100 (10:06-10:42, from round 31's turn-34 backup; turns
  34-40 played, stopped at the start of turn 41), not cleared, no retry, no proof; finale not started (chapter 27 not
  cleared). Section: docs/ROBOT.md "rv-ch27, fourth helper (round 32)" (it ran for round 33).
- **Library**: STALE (F-034's writer.c, fe_writer.h, options.c, menu_options_hook.c; every writer armed 0), rebuilt
  with `--swap` (342 s), then FRESH (2026-11-18T10:44:17; 266 overrides, unchanged).
- **Plan** (build/speed/r33int/): real play PLAN LINE 1, 54 offline, 0 live; PLAN LINE 2, 266 decided, 0 live. Cheat
  PLAN LINE 1, 4 offline (plus cheat-cq-ch17 to ch19 from their records), 0 live; PLAN LINE 2, 266 decided, 0 live.
- **Per family, real play:** Birthright 33 routes 113,140 records; Conquest 11, 42,388; Revelation 21, 80,431;
  options 2, 2,092; **0 bad in each**. Cheat apart: 7 routes, 30,077 records, 0 bad.
- **H5** (`r33-h5`): 233 of 266 met, 238,051 records, 0 bad, offline != live 0; branches 64.6%. `check_all --only
  h56-h5`: PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r33.json): (1) 2,214 / 3,696 (59.9%), round
  13's weekly sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host 92.6%; (3) 67 routes, 238,051
  records, 0 bad; cheat 30,077, 0 bad. No writer is near the gate.
- **check_all** (no `--slow`): no table change; tests 92 OK. Fast 48 pass; touched 6 pass (readable included); h56-h5
  pass.
- **Step 8 (robot): stays ~94.0% [low].** Revelation runs through chapter 26 in real play; Conquest through 16 in
  real play and 17 to 19 on the cheat track. Missing: Revelation 27 and its Endgame (cheat track allowed there,
  F-030/F-031), Conquest 20 to 27 and its Endgame, a child unit, H6 at its gate.
- **Step 9 (readable):** stays ~26% [low]; no reader changed this round.
- **Measured (F-027 count, 315 min counted, hard stop 480).** About 1 h 45 min of wall time from 09:20 to about
  11:05, far under the count, because only one chapter step ran (36 min, from 10:06) and the finale could not start; integrate
  about 23 minutes (10:42 to about 11:05, cap 60), 6 of them the library rebuild.
- **Open**: rv-ch27 (restart from build/speed/rv27i/c27i_t41_backup); cheat-rv-endgame; the build-folder clean
  (refused while round 34's boot.exe ran); 33 readers never met; 237 equivalent candidates plus 70 unsorted; the
  looks; OK B open.

## Status update 2026-12-09 (integrate, round 34): Conquest 20 to 23 on the cheat track (F-033), proven; 24 not cleared

**In plain words.** Round 34 (F-033 with F-031: Conquest goes on from chapter 20 on the cheat track, counted;
counted 495 minutes from 09:45, hard stop 660; beside rounds 33 and 35) **proved four chapters: Conquest 20
(`cheat-cq-ch20`), 21 (`cheat-cq-ch21`), 22 (`cheat-cq-ch22`) and 23 (`cheat-cq-ch23`)**, each with nobody lost, two
equal proof copies, a clear save packed with the cheat mark and a capture with every override (0 bad). None used a
new poke: each started from the chapter before's cheat clear save, which already holds round 29's movement bonus, so
they count as cheat routes. Chapter 21 was won by escaping on turn 1 and chapters 22 and 23 by killing the boss and
seizing on turn 1, so those three add little battle coverage. **Conquest 24 is not cleared**: two helpers found that
the turn-1 kill of the boss Hinoka always costs Gunter and that blockers die in enemy phase 1, so with movement only
they stopped and reported, as F-033 says. Conquest 25 to 27 were not started. Integrate compared **all 67 real-play
routes offline (238,051 records, 0 bad)**, played the four new chapters live once with every reader so their records
are kept (**4,373, 2,384, 2,826 and 2,789 records, 0 bad**, final memory equal to the proofs), and replayed the **11
cheat routes apart: 42,449 records, 0 bad**. Plan total 55.7% -> about 55.8% (robot ~94.0% -> ~94.8% [low]: four
Conquest chapters proven, cheat-labelled and counted per F-033; step 9 unchanged at ~26%; steps 3, 4, 5, 7 unchanged
until the owner looks). Owner report: docs/REPORT_2026-12-09.md.

- **Chapters** (minutes against caps): cheat-cq-ch20 play 33 of 100 (09:43-10:16, from round 32's turn-9 chain;
  checks and route to 10:40), proof 26 of 45 (10:40-11:06); cheat-cq-ch21 play about 6 (11:06-11:12; 13 in all),
  proof 8; cheat-cq-ch22 play about 13 (11:24-11:37; 17 in all), proof 10; cheat-cq-ch23 play about 14
  (11:46-12:00; 20 in all), proof 8; cheat-cq-ch24 play 35 of 100 (12:11-12:46) and retry 10 of 60 (12:47-12:57),
  not cleared, no proof; Conquest 25 not started. Sections: docs/ROBOT.md 3z-cq20b, 3z-cq21, 3z-cq22, 3z-cq23, 3z-cq24.
- **Library**: FRESH (2026-11-18T10:44:17, round 33's rebuild; 266 overrides). Not rebuilt.
- **Plan** (build/speed/r34int/): real play PLAN LINE 1, 54 offline, 0 live; PLAN LINE 2, 266 decided, 0 live. The
  proof captures kept no records, so the four new cheat chapters played live once with `--store-keep`
  (r34-capc-cheat-cq-ch20..23); then cheat PLAN LINE 1, 4 offline plus the seven cheat-cq routes from their records,
  0 live; PLAN LINE 2, 266 decided, 0 live.
- **Per family, real play:** Birthright 33 routes 113,140 records; Conquest 11, 42,388; Revelation 21, 80,431;
  options 2, 2,092; **0 bad in each**. Cheat apart: 11 routes, 42,449 records, 0 bad.
- **H5** (`r34-h5`): 233 of 266 met, 238,051 records, 0 bad, offline != live 0; branches 64.6%. `check_all --only
  h56-h5`: PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r34.json): (1) 2,214 / 3,696 (59.9%), round
  13's weekly sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host 92.6%; (3) 67 routes, 238,051
  records, 0 bad; cheat 42,449, 0 bad. No writer is near the gate.
- **check_all** (no `--slow`): cheat-conquest lists cheat-cq-ch17 to ch23; tests 93 OK. Fast 51 pass; touched 5
  pass; h56-h5 pass.
- **Step 8 (robot): ~94.0% -> ~94.8% [low].** Conquest runs through chapter 16 in real play and chapters 17 to 23 on
  the cheat track (F-033, cheat-labelled, counted); Revelation through chapter 26 in real play. Missing: Conquest 24
  to 27 and its Endgame, Revelation 27 and its Endgame, a child unit, H6 at its gate.
- **Step 9 (readable):** stays ~26% [low]; no reader changed this round.
- **Measured (F-027 count, 495 min counted, hard stop 660).** About 3 h 40 min of wall time from 09:43 to about
  13:22, well inside the count, because chapter 24 was not cleared and chapter 25 never started; integrate about 25
  minutes (12:57 to about 13:22, cap 60).
- **Open**: cheat-cq-ch24 (owner's call: allow more than movement for it, or a long multi-turn fight); Conquest 25 to
  27 and its Endgame; proof captures should keep records (`--only all --store-keep`); 33 readers never met; 237
  equivalent candidates plus 70 unsorted; the looks; OK B open.

## Status update 2026-12-10 (integrate, round 35): OK A ran in the test game; not green; W1/W2 stay off

**In plain words.** Round 35 (F-034, owner 2026-11-18 ~10:10 "ok, yes go ahead"; counted 480 minutes from 10:10,
hard stop 11 h; beside rounds 33 and 34) wrote the two missing options writers W1 (`config_options_hook`) and W2
(`config_serialize_guard`) and the options file reader (`src/readable/core/options.c`), all **switched off in
git**, passed their host tests, then ran OK A in the robot's test game on armed test libraries kept below
build/oka/. **OK A is not green**: T1, T2, T3 and T6 (W2) failed, T4 and T5 did not pass, T7 answered for two fights.
No writer was turned on for the owner's game. Owner report: docs/REPORT_2026-12-10.md; details
docs/OPTIONS_WIRING.md sections 12 and 13.

- **Host test (w12_diff.py)**: seeds 20261118 and 2, 300 scenarios each, 0 mismatches, 26/26 planted bugs, clean
  saves 0, unarmed table 0, options file 2,027 files 0.
- **Armed compare**: T1 FAIL (readable mode alone leaves 451 different FCRAM bytes on bt-ch8-pair; the writers add
  0); T2 FAIL (HP bars from the file leave 14,787 bytes the screen does not); T3 FAIL (`danger_zone = 2` still draws
  the zone: the docs' reading of byte 1 is wrong); T4 and T5 not passed (paths not reached); T6 W1 PASS, W2 FAIL
  (252 bytes of the battle save differ after a give-up; save thrown out).
- **The gate (F-026), for W1/W2, kept apart**: (1) recordings 0 (no capture of W1/W2); (2) host 26/26 on both seeds;
  (3) armed compare failing. W1/W2 are not at the gate.
- **check_all**: 5 new rows (w12-host-seed1/2, w12-options, options-track-selftest, options-track-routes);
  `robot-routes` skips options routes.
- **Step 9 (readable): stays ~26% [low].** No measured writer pass (F-017/F-026), so it does not move.
- **Step 10 (options page)**: still waits on a green OK A, then the owner's second yes (writer on for the owner,
  OK C) and OK B.
- **Open**: W2's give-up save (T6); the HP-bar bytes (T2); what game byte 1 of the danger zone does (T3); T1's pass
  rule (readable vs original mode, owner's call); T4's two early applies; a suspend route for T5; the "block is
  mapped" scenario in w12_diff; the opt-* path in headless.py; options.c path normalising.

## Status update 2026-12-11 (integrate, round 36): Revelation 27 and the Revelation Endgame on the cheat track, proven

**In plain words.** Round 36 (F-035 with F-030/F-031: Revelation 27 may use a declared movement cheat, and each
route's Endgame goes on the cheat track; counted 315 minutes from 13:15, hard stop 480; beside rounds 34 and 35)
**cleared Revelation 27 (`cheat-rv-ch27`, 6 movement pokes) and won the Revelation Endgame (`cheat-rv-endgame`, 10
pokes in all: the ch27 movement ones plus Anankos' hands, head and core set to 1 HP after each appeared)**, nobody
lost in either. The game played the ending and came back to the title screen. Both are proven with two equal copies
(the Endgame's proof ran at integrate with a longer time limit after the finale's try timed out on a busy machine).
Neither has a clear save: the game makes none after chapter 27 or the Endgame. The ch27 clear zip that the proof had
packed held the chapter 26 save files, which made the real-play rv-ch26 save look like a cheat save; integrate moved
it aside. Integrate compared **all 67 real-play routes offline (238,051 records, 0 bad)**, played cheat-rv-ch27 live
once to keep its records (**7,424 records, 0 bad**), and replayed the cheat routes apart (**13 routes, 62,936
records, 0 bad**). Plan total about 55.8% -> about 55.9% (robot ~94.8% -> ~95.6% [low]: Revelation is now played to
its end, chapters to 26 in real play and 27 plus the Endgame cheat-labelled, counted per F-030/F-031/F-035; step 9
unchanged at ~26%; steps 3, 4, 5, 7 unchanged until the owner looks). Owner report: docs/REPORT_2026-12-11.md.

- **Chapters** (minutes against caps): cheat-rv-ch27 play 18 of 100 (13:12-13:30; 71 with route and checks), proof
  41 of 30 counted (cap 45); cheat-rv-endgame play and capture 78 of 90 (15:02 to about 16:20), its proof not done in
  that step; done at integrate (16:23-17:00, both copies 2,260 s). Sections: docs/ROBOT.md "rv-ch27 on the cheat
  track", "Revelation Endgame on the cheat track", "Round 36 integrate".
- **Library**: check-fresh STALE only from another round's uncommitted writer edits in src/readable/menu/; the
  library equals HEAD d0d9b4e (source gate passed with `--rev d0d9b4e`). Not rebuilt.
- **Plan** (build/speed/r36int/): real play PLAN LINE 1, 54 offline, 0 live; PLAN LINE 2, 266 decided, 0 live. Cheat
  PLAN LINE 1, 4 offline plus the cheat-cq and cheat-rv routes from their records, 0 live; PLAN LINE 2, 266 decided,
  0 live (after cheat-rv-ch27 played live once with `--store-keep`).
- **Per family, real play:** Birthright 33 routes 113,140 records; Conquest 11, 42,388; Revelation 21, 80,431;
  options 2, 2,092; **0 bad in each**. Cheat apart: 13 routes, 62,936 records, 0 bad.
- **H5** (`r36-h5`): 233 of 266 met, 238,051 records, 0 bad, offline != live 0; branches 64.6%. `check_all --only
  h56-h5`: PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r36.json): (1) 2,214 / 3,696 (59.9%), round
  13's weekly sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host 92.6%; (3) 67 routes, 238,051
  records, 0 bad; cheat apart 0 bad. No writer is near the gate.
- **check_all** (no `--slow`): cheat-endgame lists cheat-bt-endgame, cheat-rv-ch27 and cheat-rv-endgame (no clear
  save by design); tests 94 OK. Fast 51 pass; touched 5 pass; h56-h5 pass.
- **Step 8 (robot): ~94.8% -> ~95.6% [low].** Birthright to the end (Endgame on the cheat track); Revelation to the
  end (27 and Endgame on the cheat track); Conquest through 16 in real play and 17 to 23 on the cheat track. Missing:
  Conquest 24 to 27 and its Endgame, a child unit, H6 at its gate.
- **Step 9 (readable):** stays ~26% [low]; no reader changed this round.
- **Measured (F-027 count, 315 min counted, hard stop 480).** From 13:12 to about 17:10, about 4 h of wall time,
  inside the count. Integrate about 50 minutes (16:19 to about 17:10, cap 60), most of it waiting on the Endgame proof
  (37 min) and the cheat-rv-ch27 live capture (34 min), which ran side by side.
- **Open**: Conquest 24 to 27 and its Endgame; the Endgame objective-card wait (20,000 frames, harmless); the ch27
  banner's turn count; offline.py's mtime rule for uncommitted cheat routes; 33 readers never met; 237 equivalent
  candidates plus 70 unsorted; the looks; OK A not green, OK B open.

## Status update 2026-12-12 (integrate, round 37): Conquest 24 to 27 and the Conquest Endgame on the cheat track, proven

**In plain words.** Round 37 (F-033 and F-036 with F-030/F-031: Conquest goes on from chapter 24 on the cheat track,
with the declared HP/Def/Res boost of F-036, counted; counted 495 minutes from 13:30, hard stop 11 h; beside rounds
35/38 and 36/39) **proved Conquest 24 (`cheat-cq-ch24`, 106 boost pokes), 25 (`cheat-cq-ch25`, 8 pokes for the new
unit Leo), 26 (`cheat-cq-ch26`, no pokes of its own), 27 (`cheat-cq-ch27`, no pokes of its own) and the Conquest
Endgame (`cheat-cq-endgame`, one poke: the boss Takumi's HP 60 -> 1)**, nobody lost in any of them, two equal proof
copies each. The game played the Conquest ending and came back to the title screen. Chapters 24 to 26 have clear
saves packed with the cheat mark; chapter 27 and the Endgame have none by design (the game saves nothing after
chapter 27). **All three campaigns now run to their endings** (parts on the cheat track, counted per
F-030/F-033/F-035/F-036). The capture library was rebuilt (check-fresh said STALE from round 38's committed writer
edits); integrate then compared **all 67 real-play routes offline (238,051 records, 0 bad)**, played the five new
cheat routes live once with every reader and `--store-keep` (**4,778 + 5,101 + 4,121 + 3,822 + 5,972 records, 0
bad**, final memory equal to each proof), and replayed the cheat routes apart (**18 routes, 86,730 records, 0
bad**). Plan total about 55.9% -> about 56.0% (robot ~95.6% -> ~96.6% [low]: Conquest 24 to 27 and its Endgame
proven, cheat-labelled and counted per F-033/F-036; step 9 unchanged at ~26%; steps 3, 4, 5, 7 unchanged until the
owner looks). Owner report: docs/REPORT_2026-12-12.md.

- **Chapters** (minutes against caps): cheat-cq-ch24 play 9 of 100 (13:22-13:31; 20 in all), proof 13 of 45;
  cheat-cq-ch25 play 25 (13:50-14:14; 35 in all), proof 12; cheat-cq-ch26 play 33 (14:37-15:10; 56 in all), proof 45
  of 45 (two 20-minute copies); cheat-cq-ch27 play 30 (16:17-16:47; 49 in all), proof 25; Endgame play 16
  (17:22-17:38), proof and capture 15 (40 of 90 in all). No retry. Sections: docs/ROBOT.md 3z-cq24b, 3z-cq25,
  3z-cq26, 3z-cq27, 3z-cqend, "Round 37 integrate".
- **Library**: STALE (round 38's committed menu writer edits), rebuilt with `build.py --swap` (18:04-18:11, 385 s,
  266 overrides, 65 staged files); FRESH after. Another round edited two menu writer files again at 18:27, so the
  cheat replays ran with `--rev 7b146ba` (source gate passed: the library is that commit).
- **Plan** (build/speed/r37int/): real play PLAN LINE 1, 54 offline, 0 live; PLAN LINE 2, 266 decided, 0 live. The
  proof captures of ch24 to ch27 kept no records and the library changed, so all five new routes played live once
  with `--store-keep` (r37-capc-cheat-cq-ch24..27, r37-capc2-endgame); then cheat PLAN LINE 1, 4 offline plus the
  cheat routes from their records, 0 live; PLAN LINE 2, 266 decided, 0 live. cheat-rv-ch27 and cheat-rv-endgame were
  flagged "routes.json entry changed after the records" (the mtime rule; both entries are equal to commit e9d2950)
  and were replayed with `--ignore-plan` (r37-offrv: 20,487 records, 0 bad).
- **Per family, real play:** Birthright 33 routes 113,140 records; Conquest 11, 42,388; Revelation 21, 80,431;
  options 2, 2,092; **0 bad in each**. Cheat apart: 18 routes, 86,730 records, 0 bad.
- **H5** (`r37-h5`): 233 of 266 met, 238,051 records, 0 bad, offline != live 0; branches 64.6%. `check_all --only
  h56-h5`: PASS.
- **The gate (F-026), three numbers kept apart** (build/h6three/three-r37.json): (1) 2,214 / 3,696 (59.9%), round
  13's weekly sample; (2) host test alone 3,700 / 4,009 (92.3%), records or host 92.6%; (3) 67 routes, 238,051
  records, 0 bad; cheat apart 0 bad. No writer is near the gate.
- **check_all** (no `--slow`): cheat-conquest lists cheat-cq-ch17 to ch26; cheat-endgame adds cheat-cq-ch27 and
  cheat-cq-endgame (no clear save by design, no pokes needed when the start save is a Conquest cheat clear save);
  tests 95 OK. Fast 51 pass; touched 5 pass; h56-h5 pass.
- **Step 8 (robot): ~95.6% -> ~96.6% [low].** Birthright, Conquest and Revelation each run to the ending (Birthright
  Endgame, Conquest 17 to Endgame, Revelation 27 and Endgame on the cheat track). Missing: a child unit, H6 at its
  gate, real-play wins of the cheat-track chapters.
- **Step 9 (readable):** stays ~26% [low]; no reader changed this round.
- **Measured (F-027 count, 495 min counted, hard stop 660).** From 13:22 to about 18:42, about 5 h 20 of wall time,
  inside the count. Integrate about 43 minutes (17:59 to about 18:42, cap 60): rebuild 7, live captures 19 (the
  Endgame the longest), offline 4.5, H5 3, check_all 8, cheat replays 2.
- **Open**: real-play Conquest 17+ (none won without a poke); Gunter's HP drop in ch24 enemy phase 1 not traced; the
  Conquest ending movie skipped with START, not watched; offline.py's mtime rule for uncommitted cheat routes; 33
  readers never met; 237 equivalent candidates plus 70 unsorted; the looks; OK A not green, OK B open.

## Status update 2026-12-13 (integrate, round 38): OK A fixes made, OK A rerun; not green; W1/W2 stay off

**In plain words.** Round 38 (F-034 continued, from 13:35 on 2026-11-18; counted 480 minutes, hard stop 11 h; beside
rounds 36 and 37) explained all six round-35 findings: W2's give-up save (T6) was a real bug, fixed with a new
`config_restore_options`; the danger-zone mapping (T3) was a wrong design, fixed (page value 2 stores nothing); T1,
T2 (HP bars), T4 and T5 were wrong tests, corrected in docs/OPTIONS_WIRING.md section 7 / 13a. Then OK A ran again on
a fresh armed tree below build/oka/. **OK A is still not green**: T1 FAIL (readable mode itself, not the writers,
changes Chapter0 on two routes and leaves non-stack bytes on eight), T2 FAIL (danger zone 2 to 0 from the file
leaves 4,795 bytes). T3 PASS under the changed rule, T4, T5, T6 PASS, T7 answered for two fights. No writer turned
on for the owner. Owner report: docs/REPORT_2026-12-13.md; details docs/OPTIONS_WIRING.md section 14.

- **Host tests**: w12_diff seeds 20261118 and 2, 300 scenarios each, 0 mismatches, 32/32 plants; writer_diff 600
  cases, 0 mismatches, 25/25.
- **The gate (F-026), for W1/W2, kept apart**: (1) recordings 0; (2) host 32/32 and 25/25 on both seeds; (3) armed
  compare T1 FAIL, T2 FAIL, T5 PASS, T6 PASS. Not at the gate.
- **check_all**: `w12-host-seed1/2` now also require at least 32 plants (all caught).
- **Step 9 (readable): stays ~26% [low].** No measured writer pass. New finding for step 9 itself: on full routes,
  readable mode changes play (Chapter0 differs from original mode on bt-castle-shop and bt-ch8-support). Earlier
  captures compared reader answers, not whole-route saves, so this is new and needs finding [med].
- **Step 10 (options page)**: still waits on a green OK A, then the owner's second yes (writer on for the owner,
  OK C) and OK B.
- **Open**: the reader override(s) behind T1; the T2 danger-line bytes; the owner's look at T3's changed rule; the
  Versus-file path (host test only); 5 T1 routes not run; the opt-* path in headless.py.

## Status update 2026-12-14 (integrate, round 40): OK A's two FAILs explained, W1 fixed, T1/T2 rerun; not green

**In plain words.** Round 40 (F-034 continued, from 17:40 on 2026-11-18; counted 300 minutes, hard stop 8 h)
explained round 38's T1 and T2 FAILs. T1: no reader is wrong; readable mode spends no guest cycles, so a clock read
lands 1 ms earlier and one saved time byte changes. T2 danger: W1 rebuilt the zone mid-load (fixed with
`config_apply_options`); the rest is the options screen drawing. Rerun on build/oka/t41: every check that ran passes
**under corrected rules the owner has not seen**; T1 short 2 routes; HP bars by judgement. **OK A is not green.** No
writer on for the owner. Report: docs/REPORT_2026-12-14.md; details docs/OPTIONS_WIRING.md sections 13b, 15, 16.

- **Host tests**: w12_diff both seeds 0 mismatches, 34/34 plants; options reader 0 mismatches; writer_diff 25/25.
- **Gate (F-026), W1/W2, kept apart**: (1) recordings 0; (2) host 34/34 both seeds; (3) armed compare T1 PASS on
  12/14 routes (corrected rule), T2 PASS (corrected rule, HP bars by judgement), T5/T6 PASS (rounds 38/40). Not at
  the gate.
- **check_all**: `w12-host-seed1/2` now require at least 34 plants, all caught.
- **Step 9 (readable): stays ~26% [low].** No measured writer pass. New for step 9: readable mode shifts the guest
  clock (overrides spend no guest budget); harmless on 12 routes, but an RNG-seed clock read could move [med].
- **Step 10 (options page)**: still waits on a green OK A, then the owner's second yes (writer on for the owner,
  OK C) and OK B.
- **Open**: owner's look at the T1/T2/T3 rule changes; T1 on bt-ch9 / bt-ch9-ore; HP-bar bytes; the clock design
  question (charge guest cycles in readable mode?); tree7 incident (do not use its 17:47:57 build).

## Status update 2026-12-15 (integrate, round 41): the look sitting done by the robot, and equivalence classes 1-3 as a proposal (F-037)

**In plain words.** Under F-037 ("Robot checks, you review", 2026-11-18 ~19:05) the robot did the look sitting's
checks in its own test game, and a script checked equivalence classes 1-3 against the written rules. Both are
**proposals for the owner**: nothing counts as done until the owner says ok. Owner report: docs/REPORT_2026-12-15.md;
details docs/LOOK_ROBOT.md and docs/EQUIV_PROPOSAL.md.

- **Look sitting (docs/LOOK_ROBOT.md)**: 17 checks, 14 PASS (one of them info only; Stats line 1 capped by Nohr
  Prince's HP cap 40, 39 -> 40), 3 NOT RUN (Bronze Sword Mt on screen, dining hall Luck, Jakob in the small talk
  window). Off = original: same memory hash with and without the extras file (5d55fe7b086961db) and with all looks
  removed (4cee94f30f588c87). Only robot folders under build/ were used; %APPDATA%, the owner's saves, mods/, play/
  and build/oka untouched. A reviewer reran E2 and E5 and got the same numbers, but only with the dense sample window;
  the exact command and the exact off-check folder trail were added to the doc at integrate.
- **Equivalence (docs/EQUIV_PROPOSAL.md)**: 40 checked, 0 fail. Class 1: 15 (7 clean, 8 with a note); class 2: 18;
  class 3: 7 (2 clean, 5 held for a person: null-pointer reads). The 70 unsorted are sorted only. Nothing is marked:
  tools/harness/mutants_equivalent.csv and the H6 headline are unchanged. Applying an approved class needs a separate
  script after the owner's ok.
- **Steps 3-7 (the look sitting): unchanged.** They move ONLY after the owner says ok to the review list; even then
  the 3 NOT RUN lines stay open until seen.
- **Step 9 (readable): stays ~26% [low].** H6 headline unchanged; any approved classes are counted apart, never in
  the headline (EQUIV_RULES).
- **check_all**: no new row (no test was added; tools/harness/equiv_propose.py is a proposal script, not a gate).
- **Open**: the 3 NOT RUN looks; whole-route replay with faster battles goes a different way (press list out of
  step, most likely [med]); Zakuro's 16:9 window shape not testable by the robot; class 1/3 reading notes not yet read
  by an independent reviewer in full; owner's ok per item. Nothing committed.

## Status update 2026-12-16 (round 42): the owner's review of round 41 applied (F-026, F-037)

**In plain words.** On 2026-11-19 at about 18:00 the owner answered round 41's review list (docs/REPORT_2026-12-15.md)
with "Yes, Grok's picks". That means exactly docs/collab/ROADMAP_NOW_GROK.md, "What to answer now". The record, line by
line, is docs/OWNER_REVIEW_2026-11-19.md, and the owner's verdict per check is in docs/LOOK_ROBOT.md. Host only: no
game run and no build. Nothing committed.

- **Looks ok'd:** the name (army list, status, talk); Mov +2; the Supportive icon; the face in the talk and on the
  status screen; all looks off = original; the battle extras as the robot measured them (smoother, faster, a wider
  view, same save; NOT Zakuro's 16:9 window shape); HP as "the cap held" (not the full +5).
- **Held, still open:** the Bronze Sword line, the dining-hall line, the small talk window. Also held: the OK A
  test-rule changes (T1/T2/T3), until bt-ch9 and bt-ch9-ore run under T1 and the clock note is in a committed
  report.
- **Step 3 (text mods): ~90% -> ~95% [low].** The renamed name was seen in all three places and ok'd. Only a look in
  the owner's own window is left.
- **Step 4 (stat tables): ~68% -> ~71% [low].** Three of the five stat lines are ok'd (Mov, the skill icon, the HP
  cap held). The item table (Bronze Sword) and the castle dining line are still open.
- **Step 5 (pictures): ~65% -> ~70% [low].** The portrait swap is ok'd in the talk and on the status screen. The
  small talk window is still open.
- **Step 7 (screen extras): ~50% -> ~55% [low].** The robot's results are ok'd. The 16:9 window shape and a look in
  the owner's window are still open.
- **Equivalence (F-026):** 27 cases are marked in tools/harness/mutants_equivalent.csv (10 -> 37 entries): class 2
  all 18, class 1 the 7 clean, class 3 the 2 clean. Each row is pinned to its case by "[id X line N]", which
  tools/harness/mutate.py and tools/harness/h6three.py now honour. The other 13 stay held (class 1: 8; class 3: 5).
  h6three's judgement pile goes from 237 to 211 (and 70 to 69 new). **Number 1 is unchanged**: 2,214 / 3,696 (59.9%)
  on reached lines.
- **Step 9 (readable): stays ~26% [low].** No writer pass. Cleared cases leave the pile and never join the headline.
- **Plan total: about 56.0% -> about 57.4% [low].** By the weights: step 3 +0.25, step 4 +0.45, step 5 +0.5,
  step 7 +0.25 points. Every other step is unchanged.
- **check_all**: no new row. The mutate self-test (inside `harness.py --selftest`) gained a pinned-entry case, and
  test_h6three gained a cleared-count case.
- **Open**: the 3 held looks; the class 1 (8) and class 3 (5) cases held; OK A not green (the two T1 routes and the
  clock report); the next sampled H6 run cannot reuse the h6 cache, because the cache key includes
  mutants_equivalent.csv.

## Status update 2026-12-18 (integrate, round 44): the Bronze Sword line run by the robot, and the Seal of Flames study

**In plain words.** On 2026-11-19 the owner said "bronze sword should've been done already, but go ahead" and asked
what it would take to bring in Laz14's Seal of Flames mod (GameBanana 656034) with credit. Both were done as
**proposals for the owner** (F-037): nothing counts as done until the owner says ok. Owner report:
docs/REPORT_2026-12-18.md; details docs/LOOK_ROBOT.md (Round 44) and docs/tracks/SEAL_OF_FLAMES_STUDY.md.

- **Stats line 3, the Bronze Sword (docs/LOOK_ROBOT.md row S3): robot PASS, owner's ok still needed.** Robot's own
  test game, real presses only, no poke: bt-prologue's recorded presses up to frame 38810 on the Chapter 1 map, then
  one tap on the Bronze Sword line of Corrin's panel. The item window reads Mt 4 without the mod and Mt 14 with
  LookStep4; everything else on the window is the same. In memory only the might byte of the Bronze Sword record
  differs (4 vs 14). Off check on an installed-then-uninstalled folder: the same full memory hash as two no-mod runs
  (663e192f...449c), which also covers the uninstall step that round 41 had not proven. Seen in passing: HP 22 ->
  27 (the full +5 of line 1, not only the cap) and the crown icon (line 4). The owner-verdict table still says HOLD.
- **Step 4 (stat tables): stays ~71% [low].** It moves only after the owner says ok to S3; then the item table is
  closed and only the dining-hall line (S5) is left.
- **Moddable finish line, checklist as it stands:**
  - name: ok'd (round 42).
  - people / classes: ok'd (HP "the cap held", Mov +2); the full HP +5 now also seen by the robot (info).
  - skills: ok'd (the Supportive icon).
  - items: **robot PASS in round 44, waiting for the owner's ok** (S3).
  - portrait: ok'd in the talk and on the status screen; the small talk window (F2) still not run.
  - Still open besides: S5 (dining hall Luck) and F2.
- **Seal of Flames (host-only study, nothing downloaded, no code changed):** our Zakuro build should load it with no
  code change (romfs folder per game, names matched exactly or ignoring case), but one unknown decides that: the mod
  page lists `.bin` names and our dump uses `.bin.lz` (to check once the owner has downloaded it). It cannot be mixed
  with our own mods (same files, one folder per game; combining them would be modifying the mod, which needs Laz14's
  permission under CC BY-NC-ND 4.0). Plan: 10 steps, robot about 3 h 15 to 4 h 15 (195-255 min, counted from the
  study's table; the first draft's 3 h 30 to 4 h 25 was added up wrong and is fixed), owner about 22-27 min. Needs the
  owner's OK: the download itself (owner does it), the small report script (step 3) and new real play of the mod's
  Chapter 6 as route sof-ch6 (step 6). Credit line ready, goes into CREDITS.md once we test with the mod: "Seal of
  Flames by Laz14, https://gamebanana.com/mods/656034, CC BY-NC-ND 4.0".
- **Other steps and the plan total: unchanged** (about 57.4% [low]). Step 9 (readable) stays ~26% [low]; no writer
  armed.
- **check_all**: no new row (build/look_robot/bronze.py is a robot driver under build/, not a gate).
- **Open**: the owner's ok on S3; S5 and F2 not run; the mod's file names (`.bin` vs `.bin.lz`); whether a pre-mod
  save loads with the mod in; the mid-battle save problem's cause is a reasoned guess [med], untested. Nothing
  committed.

## Status update 2026-12-21 (integrate, round 47): 60 fps / 3x / 16:9 as defaults, randomizer slice 1, randomizer page (F-041)

**In plain words.** Round 47 did F-041's three tracks side by side (owner OK "Yes, all five", 2026-11-19; engine
build for the defaults OK'd with "do it", F-041 addendum). All three are **proposals for the owner** (F-037): nothing
counts as done until the owner says ok. Owner report: docs/REPORT_2026-12-21.md; details docs/DEFAULTS_60FPS_3X.md,
docs/RANDOMIZER.md, docs/RANDOMIZER_PAGE.md.

- **Defaults (F-041 #1-3): built, robot-checked, owner's ok still needed.** One new engine patch
  (patches/zakuro/0006-...first-run...): the four Fates extras are built into the program, and a FIRST run (no
  settings.toml yet) starts with 60 fps battles, the 16:9 top screen and 3x (the slider still stops at 8x). An existing
  settings file is never replaced, so the owner's own (4x, console shape) stays as it is; the owner ticks the two
  extras by hand (2-minute note in docs/DEFAULTS_60FPS_3X.md). play/game exe rebuilt (backup in build/backup/).
  Robot: bt-ch2 battle at one game frame per refresh, saves/units/game random values the same. Not run: the patch's
  own cargo unit tests (outside the OK).
- **Randomizer slice 1 (F-041 #4-5): built, robot PASS, owner's ok still needed.** tools/randomizer (rando.py
  make/check), rules in config/randomizer/rules.json: seeded classes, growths (same total) and join stats (same total,
  in caps) for 49 playable people; weapons the new class cannot use are swapped at each map placement; story people,
  royals with legendary weapons and Mozu keep their class; staff user, door opener and vein user kept on each route.
  Robot read all 49 people in memory = the plan, 0 mismatches; off (uninstalled) = the original, same memory hash.
- **Randomizer page (F-041 #4): built.** PLAY RANDOMIZED.bat (tools/play/rando.py): new / continue / list; each seed
  is its own profile in play/randomizer/<seed>/ with its own saves and mods; the owner's normal saves and mods are
  never used. Integrate check: the page calls the REAL randomizer CLI (`make --seed .. --zakuro-dir <profile>\data
  --out <profile>\mod`, no stub); one end-to-end new game (seed INT47, --no-start) in the build copy
  build/rando_page/play made the profile, installed the mod into the profile's data folder, and `rando.py check`
  passed all 9 guards with a byte-identical remake. play/randomizer/ (under /play/) and build/rando* (under build/)
  are gitignored; the real play/ has no randomizer folder.
- **check_all**: two new rows, rando-page-tests (9 tests) and randomizer-tests (17 tests; the 4 real-data ones skip
  without the extracted tables), with samples in tests/test_check_all.py. `--fast --jobs auto --cache --skip h56-h5`:
  51 pass, 1 fail, 104 skip; the one FAIL was hygiene-paths (a NUL byte in docs/RANDOMIZER_PAGE.md, where "\000" in a
  path had been turned into a NUL); fixed, hygiene-paths now PASS. The two new rows are medium (skipped by --fast);
  run with --only: both PASS, play-tests PASS (53). selftest still fails on one missing sample, for round 46's
  watchdog-tests row (not this round's file to edit).
- **Plan total: unchanged** (about 57.4% [low]); F-041 is outside the old steps. No writer armed.
- **Next (each needs the owner's yes):** slice 2 items and shops, then skills, enemy gear, joins; the owner's ok on
  the three proposals. **Open**: patch 0006's cargo tests not run; the page's windowed starts closed by themselves in
  the build copy (cause not proven, another game was running); a randomized unit has been seen on a map only by the
  robot (Gunter, Felicia), not in a real start from the page. Nothing committed.

## Status update for round 68 (report 2027-01-13; written 2026-11-24 in round 69): rounds 48-68 in short

**In plain words.** Since round 47 the work moved from the old steps to F-041 and later rulings: a randomizer
inside the game, Seal of Flames as a second game, Nuzlocke, a test robot that checks every chapter of every path,
and a one-command release. Nothing counts as done until the owner says ok (F-037); the owner's review list for
rounds 59-68 is docs/REVIEW_R59_R68.md. The plan for rounds 69-78 is docs/ROADMAP.md (adopted 2026-11-24).

- **The program (step 1).** The installed standalone program is round 62b's: `play/game/Fire Emblem Fates.exe`
  sha256 `b4a887b2...`, built from Zakuro plus our 30 patches (0001-0030; `play/game/build-record.json` lists the
  same 30). boot-server `1b8b2593...`, capture library `405f2bac...` (rebuilt 2026-11-24 with the owner's OK,
  commit 16105ad). No engine build in rounds 63-68. Since round 68 PLAY stops when the exe does not match its
  build record (`--anyway` gets past it; waiting for the owner's ok). F-048 (report 2027-01-05) moved the game file
  to `roms/` and Seal of Flames to `roms/seal/`.
- **Randomizer (F-043..F-047, F-049, F-050).** Built into the program (patches 0007-0030): the page after the New
  Game Casual / Classic pick (round 51), for Seal of Flames too (round 58), the character shuffle "keep the face",
  music, enemy levels, tougher bosses and recolour (round 59), growth floor, weapon ladder by difficulty, story boss
  classes and the growth view (round 62), the page cleanup with sections and help lines (round 62b, F-050). Rounds
  63-66 fixed boss weapon might (+1 / +2 / +3 shown), proved all 25 Fates story bosses that change class past their
  scenes, gave Seal of Flames its own boss list (14 bosses by round 66), saw the Conquest recolour and proved the drop
  flag (reports 2027-01-08 .. 2027-01-11).
- **The full check (round 65, report 2027-01-10).** Every chapter of Birthright (41), Conquest (30), Revelation (22)
  and Seal of Flames (41) started, played through an enemy turn, battle-saved and reloaded, randomizer off and three
  everything-on seeds: 536 of 536. HANDOVER 12 of 12, Nuzlocke on every path, music different by sound on all four
  paths. 152 setting cells: 72 seen, 70 robot, 6 memory only, 3 gap, 0 FAIL, 1 n/a; the 3 gaps (Revelation boss
  might) were seen in round 66. The next full check is due before the owner plays (round 72 in the roadmap).
- **Nuzlocke (rounds 60-61, reports 2027-01-03 and 2027-01-04).** A fallen unit stays fallen (graveyard, battle
  saves, state loads), Classic locked; passes on all four paths.
- **Tests and release (rounds 67-68, F-052, F-053).** CORE (under 5 minutes with smoke: 290 s and 274.5 s) and
  FULL in 4 lanes (`tools/release/run_tests.py`); `tools/harness/smoke.py` (8 runs + memory compare, 8/8); seed
  fingerprints; `RELEASE.bat` makes a release and never pushes. 790 unit tests (commit a0c96f7). Release r68 was
  made by RELEASE.bat from commit 5bb9c38 (build/release/r68/release.json, core only, nothing installed) and put
  on GitHub with the owner's OK on 2026-11-24 (a private repository with the history, a public one with one clean snapshot
  made from the release zip). LICENSE: scoped MIT for the project's own work (commit 5bb9c38).
- **Old steps.** Steps 2-11 and the plan total are unchanged since round 47 (about 57.4% [low]): the randomizer,
  Seal of Flames, Nuzlocke and the release sit outside the old weights. Readable code: 266 overrides, 31 helpers and
  5 writers in config/readable/functions.csv; no writer armed.
- **Open**: the owner's ok on rounds 59-68 (docs/REVIEW_R59_R68.md); Start game takes 4.5-6.3 s after a late row
  change (2 s goal missed, engine item); the help line overflow (engine); the growth view in Preparations; the full
  check before play; boot-server's old build record.
