# Round 82 full check, track check (the round-76 matrix again on the program you will play: round 81b)

**In plain words.** Nothing was built and nothing was fixed. The installed round-81b program was checked through frozen
copies, the same way as round 76's check, with the randomizer frozen at HEAD ecf766b. All 110 test runs were
made again: **every run id and every file is byte for byte round 76's** (the only randomizer change since then, round 77's
Seal full-swap refusal, never fires with "How they look" at "Keep the face"). Every chapter on all 4 paths was started,
played to an enemy phase, saved and reloaded with Everything on (three ways) and with the randomizer off:
**536 of 536 passed**; chests 4/4; HANDOVER 12/12; Nuzlocke on every path; the page robot (Fates and Seal).
The table has 168 cells: **104 SEEN, 54 robot, 8 mem, 1 n/a, 1 mem (part)**; 32 re-judged on this program (22 SEEN, 1 robot,
8 mem, 1 mem (part)), 136 carried with round 76's final mark (82 SEEN, 53 robot, 1 n/a; marked "carried"). So 82 of the
104 SEEN marks were not looked at again on this program. **Table FAIL: 0.**
**One FAIL outside the table** (page robot quick-s, Seal of Flames): with Everything on, the page's random seed 6ipff2kc made the randomizer refuse its own result (guard 'cross: no_stuck_final'), so pressing Start game started no game. It is NOT new: round 76's randomizer refuses the same seed the same way (desk reproduction). Not fixed here; it waits for the owner's yes. Everything else matches round 76: 541 of 541 break, chest and staff jobs have the same verdict, the same laid-cell counts, the same units and the same memory readback, and all 472 pair and cell pictures (422 pair, 50 cell) are byte for byte round 76's (build/r82/review/pixcmp82_bytes.json; integrate's recount, see the corrections at the end).
Nothing counts as done until the owner says ok (F-037).

## Frozen program (any other sha is refused)
| File | sha256 | Where it comes from |
|---|---|---|
| play/game/Fire Emblem Fates.exe (page robot) | c2791862f05ee1d876fd1bc91b10e3954f1753cefcb08e2e67b2f849b48acf04 | installed by round 81b |
| play/game/build-record.json | 9c171545a98d42697707e35413e51284c366d886dfb7ac56f1ca1a31da45ca41 | installed by round 81b |
| play/game/game-path.txt | 9b5eb6e3a1ce7118aa9291adea33f748bc0844e7589bc3ab7a8e90d2b0588a4b | unchanged since round 74 |
| boot-server.exe (robot) | 90e5638a8f8718d9e0945d841a3c9afe83024570a9c77199a15b0d3f7d9a5154 | engine/target/zakuro-server/release, installed by round 81b |
| server_build.json | 2dee162809f5cfcdca25c9a097e616d75827c2a21f120d3ce377c8749d03878a | engine/target/zakuro-server, installed by round 81b |
| capture library 0004000000179800.dll | 405f2bac2f383fed116a39e64c460345c711f1519b6c154016015e62645d50fb | build/harness/lib (not rebuilt since round 74) |
| harness_build.json | 877196b9e527b198f1c4c35b799b96aa3901036201b785d9ee9524086c69c7a9 | build/harness/lib |
| tools/harness/rcheck.py, frozen copy | 03bac124704e1d19a67a1269dd75370a3202263f4094c741ffc00c2deade104f | HEAD ecf766b |
| tools/harness/pagebot.py, frozen copy | d29710d4725fce8482b8aea4e43c37ebf8b7f2c38aa0ecd52f54fae939b54933 | HEAD ecf766b |

- Copies: build/r82/check/bin (SHA256.txt), hashed against the installed files before the copy (all equal). tools/harness
  (and config/randomizer) frozen with git archive of HEAD ecf766b (tools/harness tree 80c2a7a6;
  bin/HARNESS_SHA256.txt); every check process loads rcheck, server, headless, chapsel, pagebot from that copy through
  bin/pyfrozen/sitecustomize.py (sha checked at import).
- tools/randomizer tree 34cc3f63 and config/randomizer tree ad44ae94 (HEAD), frozen for the round (checked at the end: tools/randomizer 34cc3f63, config/randomizer ad44ae94, tools/harness 80c2a7a6 at 04:15, no change in the work tree).
- Round 76's drivers were copied from build/r76/check into build/r82/check (paths r76 -> r82, the frozen shas -> round
  81b's). No run id needed remapping (all equal).

## Runs remade with HEAD's randomizer (and what changed since round 76)
- All 110 runs remade (make82.jsonl, 0 failed). **110 of 110 have round 76's run id; 0 differ in any
  file** (patch.txt, options.json, plan.json, spoiler.txt, chests.txt, nuzlocke.json compared byte for byte:
  run_changes82.json). Round 77's Seal full-swap refusal is the only randomizer change since round 76 that could move a
  run, and none of these runs asks for the full swap (look = keep), so nothing moved: no finding.
- Hand-made runs used by the queue (Hayato, Sakura, the Seal recolour nocol twin) copied from round 76: their source runs
  are byte-identical.
- **What changed in the program since round 76** (round 74's program -> round 81b's): round 80 True hit (Off unless turned
  on; display only) and the Esc > Helpers heading; round 81 the New Game defaults rows and their writer; round 81b the
  Classic fix (the New Game step listener). None of these changes a randomized run.
- **Which cells are re-judged.** The same 32 cells round 76 re-judged, now on round 81b's program (their pair, cell and break jobs re-run: Shuffle (route) x4, Shuffle (any) x4, Classes x4, Skill slots x4, Children x3, Everything on x4, Shops / Seal, Castle rewards x4, Seed guarantees x4); Claude opened all 22 of their picture pairs (review/*.png, every one SEEN). The other 136 cells are carried with round 76's final mark: their runs are byte-identical and the program parts that changed since round 76 do not reach them. Checked, not assumed: (a) **the forecast** (True hit): no table cell rests on a forecast picture (every pair job's screens are enemies, unitgrid, mapunits, levelup, battles, child, mseal, hseal, bosskill, growthview_map; 'forecast' appears in no round-72 or round-76 cell record), and True hit is Off in every robot game (no Helpers table in the robots' own settings); (b) **the page, New Game, Nuzlocke start and Classic** are not table cells: they are re-judged here by the page robot (all six runs plus the rando_version row, on the new exe c2791862) and by the Nuzlocke chapter jobs and the five gate proofs (the new-game proof picks Casual and is switched to Classic), all re-run on this program, never carried; (c) a whole-program sign: the 36 re-run pair and cell jobs' 472 pictures (422 under pjobs, 50 under cjobs) are byte-identical to round 76's (round 74's program; build/r82/review/pixcmp82_bytes.json, integrate's recount), and the 541 break jobs' memory readback is identical (cmpbreak82.json). Not re-run: round 72's other pair lanes (the 136 carried cells), as the plan allows (cut 3 not needed beyond the plan's own carry).

## Break check: every chapter, 4 paths, all1 / all2 / all3 / off (536 of 536), plus the chests row
| Path | off | all1 | all2 | all3 | chests on |
|---|---|---|---|---|---|
| Birthright | 41/41 | 41/41 | 41/41 | 41/41 | 1/1 |
| Conquest | 30/30 | 30/30 | 30/30 | 30/30 | 1/1 |
| Revelation | 22/22 | 22/22 | 22/22 | 22/22 | 1/1 |
| Seal of Flames | 41/41 | 41/41 | 41/41 | 41/41 | 1/1 |

A pass means (classify.py as rounds 62, 65, 72 and 76): chapter select, onto the map, an enemy phase, a battle save and a
reload with the same units; no log fault; every patched cell right in memory on the map and after the reload; the laid-cell
count equals the patch; no player unit missing; the frozen shas in the result.

**HANDOVER: 12 of 12 pass** (Revelation 9 and 13, Conquest 9; off and all1-3): cq-B009-all1 PASS, cq-B009-all2 PASS, cq-B009-all3 PASS, cq-B009-off PASS, rv-C009-all1 PASS, rv-C009-all2 PASS, rv-C009-all3 PASS, rv-C009-off PASS, rv-C013-all1 PASS, rv-C013-all2 PASS, rv-C013-all3 PASS, rv-C013-off PASS.

## Nuzlocke on every path
- 4 chapter jobs: nz-bt-A010-nuz PASS, nz-cq-B010-nuz PASS, nz-rv-C012-nuz PASS, nz-seal-S002-nuz PASS (graveyard loaded, the
  fallen in no army and not on the map, Casual switched to Classic, no log fault, frozen shas).
- 5 gate proofs on the frozen program: path PASS, death PASS, battle PASS, newgame PASS, profile PASS (castle
  load on all 4 paths, a real death, the battle save, a new Nuzlocke game, the profile).
- On this program the new-game proof logged "New Game mode picked at frame 4019" once and the graveyard event "Casual was picked; switched back to Classic" (nuz/proof/newgame.json, run nuz61ng-2220e7fb): the round-81b listener and the Nuzlocke start work together. All 9 Nuzlocke results carry the frozen boot-server 90e5638a.

## Page robot (the real in-game page; frozen exe c2791862)
| Run | Verdict | Start game -> run laid | -> the avatar | round 76 (laid) |
|---|---|---|---|---|
| quick-f | PASS | 0.044 s | 0.725 s | 0.033 s |
| quick-s | FAIL | - | - | 0.142 s |
| agency-f | PASS | 10.637 s | 11.281 s | 5.982 s |
| agency-s | PASS | 10.386 s | 10.895 s | 7.785 s |
| p4-f | PASS | - | - | - |
| p4-s | PASS | - | - | - |

- **The hidden rando_version row**: Fates pbv-f PASS (seed hoshido73 -> run id hoshido73-439f92bf, the tests' v2 id);
  Seal pbv-s2 PASS (seed r82vseal -> r82vseal-430f6fab). **The raw page robot verdict is FAIL** for both (pagebot/pbv-f and
  pbv-s2 result.json); the PASS is pbv76.py's re-judge (result76v.json), which drops the scenario's 'stale' and
  'expects_ok' checks because this hidden-row scenario makes no late row change. Round 76 did the same
  (build/r76/check/pagebot/pbv-*/result.json FAIL, result76v.json PASS).
- quick-f, agency-f, agency-s, p4-f, p4-s PASS (the laid game byte for byte a fresh make; the stale guess thrown away; Light, Wild, the share code). The owner's real settings.toml hash ed6d9057 before and after each page run.
- **quick-s FAIL** (the one FAIL of this check, outside the table): the page drew seed 6ipff2kc, Randomize everything, Start game; the background make and the make at Start both ended 'FAIL cross: no_stuck_final' -> 'guards failed: the mod folder is written for inspection but NOT installed' (exit 2); nothing was laid; the robot's page script stopped at its own 36,001-frame limit (667 s) and the program closed itself. Evidence: build/r82/check/pagebot/quick-s/stdout.txt (lines 34-271), pagebot.jsonl (prebuild_done ok false, no laid event). The guard's detail (desk reproduction, build/r82/check/repro/head-quick-s/plan.json): one enemy, GameData/Dispos/X013.bin.lz #17, Brave Hero -> Bow Knight, reaches 144 tiles in 3 turns instead of 197 (73 %, the line is 75 %). **Not new:** round 76's randomizer (git archive of 1f266a4) refuses the same answer the same way (repro/r76tool-quick-s/make.log). **How often:** 24 more seeds with the same page answer (12 Seal, 12 Fates, repro/sample.jsonl): 0 refused. Round 76's quick-s drew another seed and passed. Rule b: no retry was made.
- **The 2 s target after a late row change still fails** (agency: 10.6 s Fates, 10.4 s Seal; round 76: 6.0 / 7.8 s): the known engine item, measured on a busy machine (4 check lanes plus the new and full tracks' robots).

## Seed guarantees in memory (F-061)
Every all1-3 run (Fates and Seal; Nuzlocke runs listed for their plans only), judged as round 76 (guar82.py): the plan's
needs met; for every repair that is the final cover of a need: the Person row's class cell is the repair's class and every
patched GameData cell read back right in every break job of that run; the unit itself on the map with that class where its
join chapter's readback frame shows it; a healer's staff on the map, or in its join placement with that chapter's
placement cells read back right.
  - fates/all1 (r59fall1-2b606176): needs met 11/11; Felicia JID_グレートナイト女 -> JID_ドラゴンマスター女 (repaired during the passes; not the final cover of a need)
  - fates/all2 (r59fall2-fc2e0b1f): needs met 11/11; Felicia JID_ダークナイト女 -> JID_アドベンチャラー女 (staff): Person-row class = the repair True, GameData read back right in 93 of 93 break jobs; on the map with that class in bt-A002-all2; staff in hand True (A002: IID_フリーズ, IID_ライブ, read back right); PROVEN True; Jakob JID_グレートナイト男 -> JID_ストラテジスト男 (staff): Person-row class = the repair True, GameData read back right in 93 of 93 break jobs; not on the map at its join chapter's readback frame; staff in hand True (A002: IID_リライブ, IID_ライブ, read back right); PROVEN True; Kaze JID_侍男 -> JID_忍男 (door): Person-row class = the repair True, GameData read back right in 93 of 93 break jobs; on the map with that class in bt-A004-all2; PROVEN True
  - fates/all3 (r59fall3-d0af3b42): needs met 11/11; Gunter JID_ボウナイト男 -> JID_ストラテジスト男 (staff): Person-row class = the repair True, GameData read back right in 93 of 93 break jobs; on the map with that class in bt-A002-all3; staff in hand True (A002: IID_フリーズ, read back right); PROVEN True; Rinkah JID_鬼人女 -> JID_天馬武者女 (flier): Person-row class = the repair True, GameData read back right in 93 of 93 break jobs; on the map with that class in bt-A004-all3; PROVEN True; Kaze JID_ドラゴンナイト男 -> JID_シーフ男 (door): Person-row class = the repair True, GameData read back right in 93 of 93 break jobs; on the map with that class in bt-A004-all3; PROVEN True; Silas JID_天馬武者男 -> JID_修験者男 (staff): Person-row class = the repair True, GameData read back right in 93 of 93 break jobs; not on the map at its join chapter's readback frame; staff in hand True (A008: IID_神風招来, IID_夏祭, read back right; B007: IID_夏祭, IID_春祭, read back right); PROVEN True
  - fates/nuz_all1 (r60fnuz-5595726d): needs met 11/11; no repair on this seed
  - seal/all1 (r59sall1-0b999cea): needs met 2/2; no repair on this seed
  - seal/all2 (r59sall2-dda7692b): needs met 2/2; Elise JID_マーシナリー女 -> JID_シーフ女 (door): Person-row class = the repair True, GameData read back right in 41 of 41 break jobs; not on the map at its join chapter's readback frame; PROVEN True
  - seal/all3 (r59sall3-0fc33ee3): needs met 2/2; Felicia JID_上忍女 -> JID_陰陽師女 (staff): Person-row class = the repair True, GameData read back right in 41 of 41 break jobs; not on the map at its join chapter's readback frame; staff in hand True (S001: IID_爆炎手裏剣, IID_鉄の暗器, IID_ライブ, IID_フリーズ, read back right); PROVEN True; Jakob JID_山伏男 -> JID_山伏男 (staff): Person-row class = the repair True, GameData read back right in 41 of 41 break jobs; not on the map at its join chapter's readback frame; staff in hand False (A002: IID_夏祭, IID_青銅の薙刀, read back not reached); PROVEN False
  - seal/nuz_all1 (r60snuz-ffb6e758): needs met 2/2; Jakob JID_弓聖男 -> JID_陰陽師男 (repaired during the passes; not the final cover of a need)
- **The staff-in-hand insert in a game**: bt-A002-recany (r59f1recruitany-894f55f7): Felicia joins at A002 holding IID_春祭 in slot 3; in memory the unit holds it: True (slot True), class ['JID_聖天馬武者女'], placement cells {'name': 'A002', 'base': '32815f20', 'cells': {'cells': 5, 'changed': 5, 'wrong': 0, 'first': []}}.
- Every line above equals round 76's (the same runs, the same jobs, the same readback). Still NOT REACHED: Seal all3 Jakob's staff in hand (his join placement is in A002, a chapter no Seal break job loads), hence Seal stays 'mem (part)'.
- The route-variant memory proofs (c_r82r1-4): Sakura (C008) skills [255, 3, 36, 0, 0] against off [255, 36, 0, 0, 0]; Hayato (C009) [255, 112, 0, 0, 0] against off [255, 3, 0, 0, 0]: both MEM, as round 76.


## Every page row on every path
SEEN = Claude opened the OFF/ON pair made on THIS program in this check and saw the change (review/seen82.json, the
side-by-side pictures under build/r82/check/review). robot = a strict robot pair valid on this program, nobody looked.
mem = memory only. +poke = rests on a content poke. n/a = the row is not on that path's page. (r) = re-judged on this
program. **(carried)** = the cell keeps round 76's FINAL mark (docs/tests/CHECK_R76.md's table after its integrate
corrections) because its runs are byte-identical to round 76's; not re-seen on the round-81b program. NOT REACHED is
never a pass.

| Setting | Birthright | Conquest | Revelation | Seal of Flames |
|---|---|---|---|---|
| Shuffle (route) | SEEN (r) | SEEN (r) | SEEN (r) | SEEN (r) |
| Shuffle (any) | SEEN (r) | SEEN (r) | SEEN (r) | SEEN (r) |
| Recolour | SEEN (carried) | SEEN+poke (carried) | SEEN (carried) | robot (carried) |
| Classes | SEEN (r) | SEEN (r) | SEEN (r) | SEEN (r) |
| Join stats | SEEN (carried) | SEEN (carried) | SEEN (carried) | SEEN (carried) |
| Growths | robot (carried) | robot+poke (carried) | robot+poke (carried) | robot+poke (carried) |
| Personal skills | SEEN (carried) | SEEN (carried) | SEEN (carried) | SEEN (carried) |
| Skill slots | SEEN (r) | SEEN (r) | robot (r) | SEEN (r) |
| Promotions (Master Seal) | robot+poke (carried) | robot+poke (carried) | robot+poke (carried) | robot+poke (carried) |
| Heart Seal classes | robot+poke (carried) | robot+poke (carried) | robot+poke (carried) | robot+poke (carried) |
| Children | SEEN (r) | SEEN (r) | SEEN (r) | n/a (carried) |
| Class growths | robot+poke (carried) | robot+poke (carried) | robot+poke (carried) | robot+poke (carried) |
| Class bases | robot (carried) | robot (carried) | robot (carried) | robot (carried) |
| Class movement | robot (carried) | robot (carried) | robot (carried) | robot (carried) |
| Starting items | SEEN (carried) | SEEN (carried) | SEEN (carried) | SEEN (carried) |
| Shops | SEEN (carried) | SEEN (carried) | SEEN (carried) | mem (r) |
| Castle rewards | mem (r) | mem (r) | mem (r) | mem (r) |
| Weapon stats | robot (carried) | robot (carried) | robot (carried) | robot (carried) |
| Weapon special powers | robot (carried) | robot (carried) | robot+poke (carried) | robot+poke (carried) |
| Enemy classes | SEEN (carried) | SEEN (carried) | SEEN (carried) | SEEN (carried) |
| Boss classes | SEEN (carried) | SEEN (carried) | SEEN (carried) | SEEN (carried) |
| Enemy weapons | SEEN (carried) | SEEN (carried) | SEEN (carried) | SEEN (carried) |
| Stronger enemy weapons (Normal ladder pair) | SEEN (carried) | SEEN (carried) | SEEN (carried) | SEEN (carried) |
| Enemies grow faster | robot (carried) | robot (carried) | robot (carried) | robot (carried) |
| Enemy levels up | robot (carried) | robot (carried) | robot (carried) | robot (carried) |
| Tougher bosses (stat buff) | robot (carried) | robot (carried) | robot (carried) | robot (carried) |
| Enemy drops | SEEN (carried) | SEEN (carried) | SEEN (carried) | SEEN (carried) |
| Music | robot (carried) | robot (carried) | robot (carried) | robot (carried) |
| Everything on | SEEN (r) | SEEN (r) | SEEN (r) | SEEN (r) |
| Growth view | SEEN (carried) | SEEN (carried) | SEEN (carried) | SEEN (carried) |
| Growth floor 20-100 | SEEN (carried) | SEEN (carried) | SEEN (carried) | SEEN (carried) |
| Ladder: Easy | SEEN (carried) | SEEN (carried) | SEEN (carried) | SEEN (carried) |
| Ladder: Normal | SEEN (carried) | SEEN (carried) | SEEN (carried) | SEEN (carried) |
| Ladder: Hard | SEEN (carried) | SEEN (carried) | SEEN (carried) | SEEN (carried) |
| Story boss classes (class change) | SEEN+poke (carried) | SEEN+poke (carried) | SEEN+poke (carried) | SEEN (carried) |
| Boss might/HP: Easy | SEEN (carried) | SEEN (carried) | SEEN (carried) | SEEN (carried) |
| Boss might/HP: Normal | SEEN (carried) | SEEN (carried) | SEEN (carried) | SEEN (carried) |
| Boss might/HP: Hard | SEEN (carried) | SEEN (carried) | SEEN (carried) | SEEN (carried) |
| Chest and village items (row on) | SEEN (carried) | SEEN+poke (carried) | robot (carried) | SEEN+poke (carried) |
| Recolour: Easier to see | SEEN (carried) | robot+poke (carried) | robot (carried) | robot (carried) |
| Growths in Preparations (Y) | SEEN (carried) | SEEN (carried) | SEEN (carried) | SEEN (carried) |
| Seed guarantees (repaired class and healer's staff in memory) | mem (r) | mem (r) | mem (r) | mem (part) (r) |

42 rows x 4 paths = 168 cells: 104 SEEN, 54 robot, 8 mem, 1 n/a, 1 mem (part) (sum 168); 24 of them +poke (6 SEEN+poke, 18 robot+poke); 32 re-judged on this program (marked (r): 22 SEEN, 1 robot, 8 mem, 1 mem (part)), 136 carried with round 76's final mark
(82 SEEN or SEEN+poke, 53 robot or robot+poke, 0 mem, 1 n/a).
Per path: bt: 27 SEEN, 1 SEEN+poke, 2 mem, 9 robot, 3 robot+poke; cq: 24 SEEN, 3 SEEN+poke, 2 mem, 8 robot, 5 robot+poke; rv: 24 SEEN, 1 SEEN+poke, 2 mem, 10 robot, 5 robot+poke; seal: 23 SEEN, 1 SEEN+poke, 2 mem, 1 mem (part), 1 n/a, 9 robot, 5 robot+poke.

### What changed against round 76's final table (re-judged cells only)
- Seed guarantees (repaired class and healer's staff in memory) / Birthright: None -> **mem**: 6 of 6 repairs that are a final cover on this path proven in memory (the Person row's class cell, every GameData cell read back right in every all1-3 break job; a healer's staff on the map or in its join placement read back right); every plan's needs met (none missed). all2 Felicia staff -> JID_アドベンチャラー女: Person-row class laid, GameData read back right in 93 of 93 break jobs; on the map with it in
- Seed guarantees (repaired class and healer's staff in memory) / Conquest: None -> **mem**: 3 of 3 repairs that are a final cover on this path proven in memory (the Person row's class cell, every GameData cell read back right in every all1-3 break job; a healer's staff on the map or in its join placement read back right); every plan's needs met (none missed). all2 Felicia staff -> JID_アドベンチャラー女: Person-row class laid, GameData read back right in 93 of 93 break jobs; on the map with it in
- Seed guarantees (repaired class and healer's staff in memory) / Revelation: None -> **mem**: 6 of 6 repairs that are a final cover on this path proven in memory (the Person row's class cell, every GameData cell read back right in every all1-3 break job; a healer's staff on the map or in its join placement read back right); every plan's needs met (none missed). all2 Felicia staff -> JID_アドベンチャラー女: Person-row class laid, GameData read back right in 93 of 93 break jobs; on the map with it in
- Seed guarantees (repaired class and healer's staff in memory) / Seal of Flames: None -> **mem (part)**: 2 of 3 repairs that are a final cover on this path proven in memory (the Person row's class cell, every GameData cell read back right in every all1-3 break job; a healer's staff on the map or in its join placement read back right); every plan's needs met (none missed). all2 Elise door -> JID_シーフ女: Person-row class laid, GameData read back right in 41 of 41 break jobs; not on the map at the readbac
- Re-judged with the same mark: Shuffle (route) / Birthright (SEEN), Shuffle (route) / Conquest (SEEN), Shuffle (route) / Revelation (SEEN), Shuffle (route) / Seal of Flames (SEEN), Shuffle (any) / Birthright (SEEN), Shuffle (any) / Conquest (SEEN), Shuffle (any) / Revelation (SEEN), Shuffle (any) / Seal of Flames (SEEN), Classes / Birthright (SEEN), Classes / Conquest (SEEN), Classes / Revelation (SEEN), Classes / Seal of Flames (SEEN), Skill slots / Birthright (SEEN), Skill slots / Conquest (SEEN), Skill slots / Revelation (robot), Skill slots / Seal of Flames (SEEN), Children / Birthright (SEEN), Children / Conquest (SEEN), Children / Revelation (SEEN), Shops / Seal of Flames (mem), Castle rewards / Birthright (mem), Castle rewards / Conquest (mem), Castle rewards / Revelation (mem), Castle rewards / Seal of Flames (mem), Everything on / Birthright (SEEN), Everything on / Conquest (SEEN), Everything on / Revelation (SEEN), Everything on / Seal of Flames (SEEN)

## FAILs
None of the 168 cells failed.

**FAIL outside the table (listed for the owner's yes, not fixed):** the page robot's quick-s run, Seal of Flames + Everything on, seed 6ipff2kc: the randomizer refuses its own result (guard no_stuck_final, one X013 enemy reaches 73 % of its old tiles), so Start game starts no game. Pre-existing (round 76's randomizer does the same), rare (0 of 24 other seeds). What the player sees on screen was NOT REACHED (the robot is headless; no picture).
Known misses (not cells): the 2 s Start-game target after a late row change (engine item, above).


## Pokes
Every check job made the chapter-select pokes (chapsel.py rule 2: the world-map spot record and the current chapter
pointer; the Seal jobs' route_mask write, chapter-table record +0x14, 00 -> 04) in its own copy, as round 76 (docs/CHEATS.md
section 6, carried). Not content pokes, not marked. No job of this check made a content poke (final82.py scans every re-judged pair's job.pokes and pokes_extra: none). Nothing new for docs/CHEATS.md.

## Robot notes (honest)
- At most 4 check robot jobs at once (run4.py: the page robot pb.py as one lane plus 3 workers; the 4th worker started
  only after the page robot's last run; claim files; claim deadline 04:40 EST (moved from 04:10 at 02:01: the break check is never cut)). No job ran twice at once.
- shascan.json: 600 result files carry the frozen boot-server 90e5638a + capture library
  405f2bac (page robot: exe c2791862); 0 carry another sha.
- Lanes: 51 of 51 queued lanes ended; not claimed by the deadline: none.
- Times (counted with date): setup 01:18-01:31, runs remade 01:24-01:30, page robot 01:32-01:52, check lanes 01:32-04:15 (ALL DONE 04:15:12), judging and this page 04:15 on. The claim deadline was moved from 04:10 to 04:40 at 02:01 so the break check (never cut) could not lose a lane; every lane was claimed by 03:59.
- 545 break-type jobs (536 break, 4 chests, 1 staff insert, 4 Nuzlocke) + 36 pair jobs + 6 cell jobs + 8 page robot runs + 5 Nuzlocke proofs; 0 retries (rule b), 0 crashes.
- No visible window (watch.py at 19 looks: VISIBLE: [] every time). STOP_ROUND never existed. No engine build, no install, no edit in tools/randomizer or config/randomizer, no write to %APPDATA% / %LOCALAPPDATA% (every job's data, APPDATA, LOCALAPPDATA and TMP below build/r82/check). The program's own make folder build/rando-make (below build/, as in every page robot round) received the page robot's makes. The owner's files (21: Zakuro saves, settings.toml, cheats, mods, rando, play/config.json, play/state.json) hashed before and after: equal (ownerhash.jsonl).
- Desk extras (no game): repro/ (the quick-s answer made offline with HEAD's and with round 76's randomizer; a 24-seed sample). The old-tool copy used a link to extracted/ that was removed after use (the link only).
- Processes: none of this track's robot or python processes remained at the end (checked 04:16).
- D: free 75,012 MB at 01:30 (plan) -> 62,945 MB at 04:16 (all tracks).

## Where things are
- Data: build/r82/check/final82.json, table82.md, break.json, handover.json, nz-verdicts.json, guarantees82.json,
  pairs-verdicts.json, cells-verdicts.json, run_changes82.json, shascan.json, ownerhash.jsonl, review/seen82.json,
  pagebot/*/result.json and result76v.json, plane/*.out (lane logs), watch.log.
- Drivers: build/r82/check/*.py (copies of round 76's; new: runchg82.py, final82.py, guar82.py, mkcheck82.py,
  ownerhash.py, pair82img.py).

## Integrate's corrections (round 82, from the reviewers; 2026-11-26 04:22 EST)
- **Carried counts stated.** The track's own claim text said the 136 carried cells were "102 SEEN, 32 robot, 1 mem, 1 n/a"
  and that "80" SEEN marks were carried. A recount of the table above gives **82 SEEN (+poke), 53 robot (+poke), 0 mem,
  1 n/a carried**, and **22 SEEN, 1 robot, 8 mem, 1 mem (part) re-judged** (82 + 53 + 1 = 136; 22 + 1 + 8 + 1 = 32). No
  table mark moved; the plain-words line and the count line now say these numbers, and the Seal Children cell is now
  marked "n/a (carried)" (it had no mark).
- **Pictures: 456 -> 472, pixel -> byte.** No result file backed "456 pair pictures pixel-identical". Integrate compared
  every PNG under build/r82/check/pjobs (422) and cjobs (50) with the same path under build/r76/check: **472 byte-identical,
  0 differ, 0 missing** (build/r82/review/pixcmp82_bytes.json). The check reviewer's own recount gave the same 472.
- **rando_version row:** the raw page robot verdict FAIL and its re-judge by pbv76.py are now said (page robot section).
- **Files written during the round by another round.** patches/zakuro/0042-*.patch (03:19), patches/zakuro/README.md
  (03:21), docs/ROUND82B_PLAN.md (03:06), docs/SEAL_EDITION_PLAN.md (03:37) and docs/collab/SEAL_EDITION_SPLIT_GROK.md
  (02:16) belong to round 82b and the Seal edition planning (the owner's "Yes, that order", about 02:25, recorded in
  docs/ROUND82B_PLAN.md), not to this check. Round 82b's build is staged under build/r82b and not installed: at
  integrate (04:22) the installed files still hash c2791862 / 9c171545 / 9b5eb6e3 / 90e5638a / 2dee1628 / 405f2bac /
  877196b9, the frozen program of this round.
