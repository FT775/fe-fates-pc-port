# Round 76 full check, track check (F-051/F-053 everything-on matrix again; look = keep, the page default)

**In plain words.** Nothing was built. The installed round-74 program was checked through frozen copies, as round 72's
check, with the randomizer frozen at HEAD 1f266a4 (round 75b's seed guarantees in; the full swap off because
"How they look" stays at "Keep the face"). Every chapter on all 4 paths was started, played to an enemy phase, saved
and reloaded with Everything on (three ways) and with the randomizer off: **536 of 536 passed**. HANDOVER
12/12, Nuzlocke on every path, the page robot (Fates and Seal, the hidden rando_version row, Light / Wild / share
code). The table has 168 cells (round 72's 41 rows plus the new guarantees row): **32 re-judged on this
program, 136 carried with round 72's mark** because their runs did not change. **FAIL: 0.**
After the review (integrate, round 76): the check reviewer opened 44 OFF/ON pairs made on this program, so 15 re-judged
cells move from robot to SEEN (Shuffle route x4, Shuffle any x4, Skill slots on Birthright, Conquest and Seal,
Everything on x4); the final count is **104 SEEN, 54 robot, 8 mem, 1 mem (part), 1 n/a** (section "Integrate's
corrections" below).
Nothing counts as done until the owner says ok (F-037).

## Frozen program (any other sha is refused)
| File | sha256 | Where it comes from |
|---|---|---|
| play/game/Fire Emblem Fates.exe (page robot) | c49a0ab1332a6cda10b33a807890131966f33b2eb0f72fc11ceafab1c065660f | installed by round 74 |
| play/game/build-record.json | b2beaf6275b9dcf3bdfff8638d76c7057b85fc4a41fccb2667189014d9f47431 | installed by round 74 |
| play/game/game-path.txt | 9b5eb6e3a1ce7118aa9291adea33f748bc0844e7589bc3ab7a8e90d2b0588a4b | installed by round 74 |
| boot-server.exe (robot) | b3ebe748ea313953b2ddecc33755098abac02e2166c0a0c2a5bcea23aa5b7795 | engine/target/zakuro-server/release, installed by round 74 |
| server_build.json | 15fa58e01a81b20270c2a53ab2cf1cbb0f35c20616f27ae8f55bc07f34be3d50 | engine/target/zakuro-server, installed by round 74 |
| capture library 0004000000179800.dll | 405f2bac2f383fed116a39e64c460345c711f1519b6c154016015e62645d50fb | build/harness/lib (not rebuilt) |
| harness_build.json | 877196b9e527b198f1c4c35b799b96aa3901036201b785d9ee9524086c69c7a9 | build/harness/lib |
| tools/harness/rcheck.py, frozen copy | 03bac124704e1d19a67a1269dd75370a3202263f4094c741ffc00c2deade104f | HEAD 1f266a4 |
| tools/harness/pagebot.py, frozen copy | 74cc61938754cc6d5c3e37a6a1d935ce963b135bf0351cc8d3421684e65210c9 | HEAD 1f266a4 |

- Copies: build/r76/check/bin (SHA256.txt). The whole of tools/harness (and config/randomizer) was frozen with git archive
  of HEAD 1f266a4 (tools/harness tree 7fbc350a; bin/HARNESS_SHA256.txt); every check process loads rcheck, server,
  headless, chapsel, pagebot from that copy through bin/pyfrozen/sitecustomize.py (sha checked at import).
- tools/randomizer tree c1dae4bf and config/randomizer tree ad44ae94 (HEAD), frozen for the round (checked at the end).
- Round 72's drivers were copied into build/r76/check (paths r72 -> r76, the frozen shas -> round 74's, run ids remapped by
  remap76.py: 1426 ids in 184 files).

## Runs remade with HEAD's randomizer (and what changed since round 72)
- All 110 runs of round 72's check were remade (make76.jsonl, 0 failed). Each answer now carries the hidden
  one-choice row `"rando_version": "2"` (F-061 (5); the page always answers it, make_args gives it no flag), so **every
  run id changed** (e.g. fates/all1 r59fall1-37ec8c6e -> r59fall1-2b606176).
- **90 runs have exactly round 72's patch cells**: only options.json (rando_version) and plan.json / spoiler.txt
  (the new guarantees block, the 'guarantees: timing' guard and rando_version) differ.
- **20 runs changed their patch cells, all for one reason: round 75b's seed guarantees** (a repair gives one
  person a role class, with the weapon exp and the weapons that class can hold; a repaired healer may get a staff in hand;
  the even spread may give slice 1's class back, F-061 (4d)). Only placement (dispos), person and GameData cells and the
  end count moved (the "face" section shows only because its end count moved):
  - fates/all1 (r59fall1-37ec8c6e -> r59fall1-2b606176): patch lines {'dispos': 536, 'person': 6, 'face': 2, 'gamedata': 36}; repaired: Felicia Great Knight -> Wyvern Lord
  - fates/all2 (r59fall2-ecca617a -> r59fall2-fc2e0b1f): patch lines {'dispos': 888, 'person': 10, 'face': 2, 'gamedata': 72}; repaired: Felicia Dark Knight -> Adventurer; repaired: Jakob Great Knight -> Strategist; repaired: Kaze Samurai -> Ninja
  - fates/all3 (r59fall3-1f1e51e5 -> r59fall3-d0af3b42): patch lines {'dispos': 926, 'person': 28, 'face': 2, 'gamedata': 112}; repaired: Gunter Bow Knight -> Strategist (last resort: nobody else in that army could take the role); repaired: Rinkah Oni Savage -> Sky Knight; repaired: Kaze Wyvern Rider -> Outlaw; repaired: Silas Sky Knight -> Monk
  - fates/children_c (r59f1classes-299cc74f -> r59f1classes-871d381f): patch lines {'dispos': 916, 'gamedata': 52}; repaired: Felicia Sorcerer -> Strategist; repaired: Rinkah Samurai -> Sky Knight
  - fates/classes (r59f1classes-94131206 -> r59f1classes-346ca531): patch lines {'dispos': 916, 'gamedata': 46}; repaired: Felicia Sorcerer -> Strategist; repaired: Rinkah Samurai -> Sky Knight
  - fates/recruit (r59f1recruit-31c67934 -> r59f1recruit-5a6d351c): patch lines {'dispos': 86, 'face': 2, 'gamedata': 4}; repaired: Silas Cavalier -> Outlaw
  - fates/recruit_any (r59f1recruitany-d465ce13 -> r59f1recruitany-894f55f7): patch lines {'dispos': 336, 'face': 2, 'gamedata': 23}; repaired: Felicia Spear Master -> Falcon Knight; repaired: Jakob Master Ninja -> Great Master; repaired: Rinkah Oni Savage -> Ninja; repaired: Kaze Mercenary -> Outlaw; staff in hand: Felicia joins (A002) holding Bloom Festal
  - fates/skill_slots (r59f1skillslots-d6ebcad8 -> r59f1skillslots-cace8ad0): patch lines {'dispos': 883, 'person': 14, 'gamedata': 56}; repaired: Felicia Hero -> Strategist; repaired: Jakob Great Knight -> Butler; repaired: Rinkah Diviner -> Sky Knight
  - fates/skill_slots_c (r59f1classes-b2eec9e4 -> r59f1classes-14350778): patch lines {'dispos': 916, 'person': 11, 'gamedata': 60}; repaired: Felicia Sorcerer -> Strategist; repaired: Rinkah Samurai -> Sky Knight
  - seal/all1 (r59sall1-3d54cbff -> r59sall1-0b999cea): patch lines {'dispos': 42, 'face': 2, 'gamedata': 9}; no repair line: the class draw moved (the even spread, F-061 (4d))
  - seal/all2 (r59sall2-9aac3dce -> r59sall2-dda7692b): patch lines {'dispos': 792, 'face': 2, 'person': 2, 'gamedata': 31}; repaired: Elise Mercenary -> Outlaw
  - seal/all3 (r59sall3-50f4bf8f -> r59sall3-0fc33ee3): patch lines {'dispos': 676, 'face': 2, 'gamedata': 52}; repaired: Felicia Master Ninja -> Onmyoji; repaired: Jakob keeps Great Master (drawn again with the retainer slot)
  - seal/children (r59s1children-04cdf656 -> r59s1children-868e90e7): patch lines {'dispos': 889, 'gamedata': 46}; repaired: Felicia Great Knight -> Strategist; repaired: Jakob Strategist -> Butler
  - seal/children_c (r59s1classes-4551b656 -> r59s1classes-22d1c9bf): patch lines {'dispos': 585, 'gamedata': 30}; repaired: Felicia General -> Maid; repaired: Jakob Paladin -> Butler
  - seal/classes (r59s1classes-ddfa9171 -> r59s1classes-90e86310): patch lines {'dispos': 585, 'gamedata': 30}; repaired: Felicia General -> Maid; repaired: Jakob Paladin -> Butler
  - seal/nuz_all1 (r60snuz-59821ef6 -> r60snuz-ffb6e758): patch lines {'dispos': 876, 'face': 2, 'person': 1, 'gamedata': 128}; repaired: Jakob Sniper -> Onmyoji
  - seal/recruit (r59s1recruit-7e945b4d -> r59s1recruit-7feaf752): patch lines {'dispos': 956, 'face': 2, 'gamedata': 19}; repaired: Felicia Oni Chieftain -> Priestess; repaired: Jakob Hero -> Butler; repaired: Elise Troubadour -> Outlaw; staff in hand: Jakob joins (A002) holding Heal
  - seal/recruit_any (r59s1recruitany-48fe9cb2 -> r59s1recruitany-14827b00): patch lines {'dispos': 769, 'gamedata': 15}; repaired: Felicia Swordmaster -> Falcon Knight; repaired: Jakob Master Ninja -> Falcon Knight; staff in hand: Jakob joins (A002) holding Bloom Festal
  - seal/skill_slots (r59s1skillslots-e78e053f -> r59s1skillslots-29334ec4): patch lines {'dispos': 564, 'person': 2, 'gamedata': 53}; repaired: Felicia Paladin -> Strategist; repaired: Jakob Hero -> Butler
  - seal/skill_slots_c (r59s1classes-f087c6b7 -> r59s1classes-13cc7de2): patch lines {'dispos': 585, 'person': 2, 'gamedata': 40}; repaired: Felicia General -> Maid; repaired: Jakob Paladin -> Butler
- So the rows whose pairs use these runs were re-judged: Shuffle (route), Shuffle (any), Classes, Skill slots, Children,
  Everything on; plus the memory-only cells (they rest on the all1-3 break jobs) and the new guarantees row. Every other
  row's runs have round 72's patch cells, so those cells carry round 72's mark and say so.
- Hand-made test runs: Hayato (one cell, unchanged in the new skill_slots_c run) copied under the new id; Sakura's one cell
  changed (0x36 -> 0x03: her class changed) and was remade from the new run; the Seal recolour nocol twin copied (its source
  patch is unchanged); r64f1recol5 and its twins remade (patch byte-identical to round 72's).
- The look = full block (round 74) is absent from every run here: look = keep (the default; the row is fixed on the page).

## Break check: every chapter, 4 paths, all1 / all2 / all3 / off (536 of 536), plus the chests row
| Path | off | all1 | all2 | all3 | chests on |
|---|---|---|---|---|---|
| Birthright | 41/41 | 41/41 | 41/41 | 41/41 | 1/1 |
| Conquest | 30/30 | 30/30 | 30/30 | 30/30 | 1/1 |
| Revelation | 22/22 | 22/22 | 22/22 | 22/22 | 1/1 |
| Seal of Flames | 41/41 | 41/41 | 41/41 | 41/41 | 1/1 |

A pass means (classify.py as rounds 62, 65 and 72): chapter select, onto the map, an enemy phase, a battle save and a
reload with the same units; no log fault; every patched cell right in memory on the map and after the reload; the laid-cell
count equals the patch; no player unit missing; the frozen shas in the result.

**HANDOVER: 12 of 12 pass** (Revelation 9 and 13, Conquest 9; off and all1-3): cq-B009-all1 PASS, cq-B009-all2 PASS, cq-B009-all3 PASS, cq-B009-off PASS, rv-C009-all1 PASS, rv-C009-all2 PASS, rv-C009-all3 PASS, rv-C009-off PASS, rv-C013-all1 PASS, rv-C013-all2 PASS, rv-C013-all3 PASS, rv-C013-off PASS.

## Nuzlocke on every path
- 4 chapter jobs: nz-bt-A010-nuz PASS, nz-cq-B010-nuz PASS, nz-rv-C012-nuz PASS, nz-seal-S002-nuz PASS (graveyard loaded, the
  fallen in no army and not on the map, Casual switched to Classic, no log fault, frozen shas).
- 5 gate proofs on the frozen program: path PASS, death PASS, battle PASS, newgame PASS, profile PASS (castle
  load on all 4 paths, a real death, the battle save, a new Nuzlocke game, the profile).

## Page robot (the real in-game page; frozen exe c49a0ab1)
| Run | Verdict | Start game -> run laid | -> the avatar |
|---|---|---|---|
| quick-f | PASS | 0.033 s | 0.471 s |
| quick-s | PASS | 0.142 s | 0.582 s |
| agency-f | PASS | 5.982 s | 6.421 s |
| agency-s | PASS | 7.785 s | 8.225 s |
| p4-f | PASS | - | - |
| p4-s | PASS | - | - |

- quick and agency (Fates, Seal): the owner's rule holds (the laid game is byte for byte a fresh make; a stale guess is
  thrown away). **The 2 s target still fails right after a late row change** (6.0 s
  Fates, 7.8 s Seal; round 72: 5.5 / 6.6 s): the known engine item. Not a quiet
  machine: the full and seal tracks' robots ran beside it.
- p4 (round 74's presets and share code, Fates and Seal): Light, Wild, Light pressed and checked, Copy, paste back, a code
  made by sharecode.py pasted: p4-f PASS, p4-s PASS (every check true).
- **The hidden rando_version row** (round 75b's P1 scenario, build/r76/check/pbv76.py): Fates pbv-f PASS
  (seed hoshido73 -> run id hoshido73-439f92bf, the tests' v2 id; the row and its option draw nothing before and
  after Randomize everything, a shown row does; the answer carries "rando_version": "2"; the laid plan = a fresh make);
  Seal pbv-s2 PASS (seed r76vseal -> r76vseal-19659a6c, the same checks without the
  round-73 answer ones). The first Seal try (pbv-s) laid its seed file in the Fates data folder (a driver mistake: the
  Seal page reads <seal-profile>/data/rando/last.json); its page checks (no version row drawn, answer with rando_version
  2, laid = fresh make) passed and only the seed expectation failed; fixed and run once more (F-042 rule b: one retry).

## Seed guarantees in memory (F-061)
Every all1-3 run (Fates and Seal; Nuzlocke runs listed for their plans only): the plan's needs met; for every repair that
is the final cover of a need: the Person row's class cell is the repair's class and every patched GameData cell read back
right in every break job of that run (so the class is in memory wherever the person is created); the unit itself on the
map with that class where its join chapter's readback frame shows it; a healer's staff on the map, or in its join
placement with that chapter's placement cells read back right. A unit carried in from a chapter's base save keeps the
class the save was made with (no randomizer then): never counted either way.
  - fates/all1 (r59fall1-2b606176): needs met 11/11; Felicia JID_グレートナイト女 -> JID_ドラゴンマスター女 (repaired during the passes; not the final cover of a need)
  - fates/all2 (r59fall2-fc2e0b1f): needs met 11/11; Felicia JID_ダークナイト女 -> JID_アドベンチャラー女 (staff): Person-row class = the repair True, GameData read back right in 93 of 93 break jobs; on the map with that class in bt-A002-all2; staff in hand True (A002: IID_フリーズ, IID_ライブ, read back right); PROVEN True; Jakob JID_グレートナイト男 -> JID_ストラテジスト男 (staff): Person-row class = the repair True, GameData read back right in 93 of 93 break jobs; not on the map at its join chapter's readback frame; staff in hand True (A002: IID_リライブ, IID_ライブ, read back right); PROVEN True; Kaze JID_侍男 -> JID_忍男 (door): Person-row class = the repair True, GameData read back right in 93 of 93 break jobs; on the map with that class in bt-A004-all2; PROVEN True
  - fates/all3 (r59fall3-d0af3b42): needs met 11/11; Gunter JID_ボウナイト男 -> JID_ストラテジスト男 (staff): Person-row class = the repair True, GameData read back right in 93 of 93 break jobs; on the map with that class in bt-A002-all3; staff in hand True (A002: IID_フリーズ, read back right); PROVEN True; Rinkah JID_鬼人女 -> JID_天馬武者女 (flier): Person-row class = the repair True, GameData read back right in 93 of 93 break jobs; on the map with that class in bt-A004-all3; PROVEN True; Kaze JID_ドラゴンナイト男 -> JID_シーフ男 (door): Person-row class = the repair True, GameData read back right in 93 of 93 break jobs; on the map with that class in bt-A004-all3; PROVEN True; Silas JID_天馬武者男 -> JID_修験者男 (staff): Person-row class = the repair True, GameData read back right in 93 of 93 break jobs; not on the map at its join chapter's readback frame; staff in hand True (A008: IID_神風招来, IID_夏祭, read back right; B007: IID_夏祭, IID_春祭, read back right); PROVEN True
  - fates/nuz_all1 (r60fnuz-5595726d): needs met 11/11; no repair on this seed
  - seal/all1 (r59sall1-0b999cea): needs met 2/2; no repair on this seed
  - seal/all2 (r59sall2-dda7692b): needs met 2/2; Elise JID_マーシナリー女 -> JID_シーフ女 (door): Person-row class = the repair True, GameData read back right in 41 of 41 break jobs; not on the map at its join chapter's readback frame; PROVEN True
  - seal/all3 (r59sall3-0fc33ee3): needs met 2/2; Felicia JID_上忍女 -> JID_陰陽師女 (staff): Person-row class = the repair True, GameData read back right in 41 of 41 break jobs; not on the map at its join chapter's readback frame; staff in hand True (S001: IID_爆炎手裏剣, IID_鉄の暗器, IID_ライブ, IID_フリーズ, read back right); PROVEN True; Jakob JID_山伏男 -> JID_山伏男 (staff): Person-row class = the repair True, GameData read back right in 41 of 41 break jobs; not on the map at its join chapter's readback frame; staff in hand False (A002: IID_夏祭, IID_青銅の薙刀, read back not reached); PROVEN False
  - seal/nuz_all1 (r60snuz-ffb6e758): needs met 2/2; Jakob JID_弓聖男 -> JID_陰陽師男 (repaired during the passes; not the final cover of a need)
- **The staff-in-hand insert in a game** (round 75b did not prove it): bt-A002-recany (r59f1recruitany-894f55f7, page shuffle across stories): Felicia joins at A002 holding IID_春祭 in slot 3 (the plan's insert); in memory the unit holds it: True (slot True), class ['JID_聖天馬武者女'], placement cells {'name': 'A002', 'base': '32815f20', 'cells': {'cells': 5, 'changed': 5, 'wrong': 0, 'first': []}}.
- **Not reached:** Seal all3 Jakob's staff in hand: his join placement in the Seal tables is in A002, a prologue chapter no Seal break job loads (the Seal break jobs play the 41 R/S/Y chapters from the Revelation save rv-ch11-clear); his class (the Person row) is proven like every other repair. The Seal track checks the healer by R002 in its own Seal game. Hence the Seal cell 'mem (part)', never a pass.
- The Seal break jobs never show a Seal join from a placement for the retainers: Felicia, Jakob and the others are in the base save's army (made by the Revelation recording without the randomizer) and keep that save's class; only the GameData and placement readbacks prove their repairs. On Fates, Felicia, Gunter, Kaze and Rinkah were also seen on the map with the repaired class in their join chapter (bt-A002, bt-A004).


## Every page row on every path
SEEN = this check's reviewer opened the OFF/ON pair made on THIS program and saw the change (review/seen76.json,
pictures under build/r76/check/review; integrate added the 15 cells the second reviewer opened, listed below). robot = a strict robot pair valid on this program, nobody looked. mem = memory
only. +poke = rests on a content poke (all carried from round 72; no re-judged pair has a content poke). n/a = the row is
not on that path's page. (r) = re-judged on this program; a cell without (r) carries round 72's final mark
(docs/tests/CHECK_R72.md, build/r72/integrate/table72_final.json) because the row's runs have the same patch cells.

| Setting | Birthright | Conquest | Revelation | Seal of Flames |
|---|---|---|---|---|
| Shuffle (route) | SEEN (r) | SEEN (r) | SEEN (r) | SEEN (r) |
| Shuffle (any) | SEEN (r) | SEEN (r) | SEEN (r) | SEEN (r) |
| Recolour | SEEN | SEEN+poke | SEEN | robot |
| Classes | SEEN (r) | SEEN (r) | SEEN (r) | SEEN (r) |
| Join stats | SEEN | SEEN | SEEN | SEEN |
| Growths | robot | robot+poke | robot+poke | robot+poke |
| Personal skills | SEEN | SEEN | SEEN | SEEN |
| Skill slots | SEEN (r) | SEEN (r) | robot (r) | SEEN (r) |
| Promotions (Master Seal) | robot+poke | robot+poke | robot+poke | robot+poke |
| Heart Seal classes | robot+poke | robot+poke | robot+poke | robot+poke |
| Children | SEEN (r) | SEEN (r) | SEEN (r) | n/a |
| Class growths | robot+poke | robot+poke | robot+poke | robot+poke |
| Class bases | robot | robot | robot | robot |
| Class movement | robot | robot | robot | robot |
| Starting items | SEEN | SEEN | SEEN | SEEN |
| Shops | SEEN | SEEN | SEEN | mem (r) |
| Castle rewards | mem (r) | mem (r) | mem (r) | mem (r) |
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
| Everything on | SEEN (r) | SEEN (r) | SEEN (r) | SEEN (r) |
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
| Seed guarantees (repaired class and healer's staff in memory) | mem (r) | mem (r) | mem (r) | mem (part) (r) |

42 rows x 4 paths = 168 cells (final, after integrate's corrections): **104 SEEN, 54 robot, 8 mem, 1 mem (part), 1 n/a, 0 FAIL** (sum 168); 24 of them +poke (6 SEEN+poke, 18 robot+poke, all carried from round 72); 32 re-judged on this program (marked (r)), 136 carried with round 72's mark.
Per path: bt: 27 SEEN, 1 SEEN+poke, 2 mem, 9 robot, 3 robot+poke; cq: 24 SEEN, 3 SEEN+poke, 2 mem, 8 robot, 5 robot+poke; rv: 24 SEEN, 1 SEEN+poke, 2 mem, 10 robot, 5 robot+poke; seal: 23 SEEN, 1 SEEN+poke, 2 mem, 1 mem (part), 1 n/a, 9 robot, 5 robot+poke.
(The track's own count before the review was 89 SEEN, 69 robot, 8 mem, 1 mem (part), 1 n/a; build/r76/check/final76.json keeps that count.)

### Integrate's corrections (round 76, from the check reviewer)
- **Robot -> SEEN (15 cells).** The reviewer opened these OFF|ON pairs (all valid in pairs-verdicts.json, all made in
  round 76) and saw the change: Shuffle (route): Birthright p-bt-A004-j Rinkah Brass Club -> Brass Naginata; Conquest
  p-cq-B012-j Arthur, Odin, Niles; Revelation p-rv-C016-j Hana, Oboro, Hinata (same class, HP / skill / rating
  differ); Seal p-seal-R002-j Felicia. Shuffle (any): Birthright p-bt-A004-j Kaze (Iron Shuriken -> Iron Bow);
  Conquest p-cq-B007-j Felicia; Revelation p-rv-C007-j Felicia; Seal p-seal-R002-j Felicia. Skill slots: Birthright
  p-bt-A004-j (classes vs skill_slots_c, Rinkah); Conquest p-cq-B012-j Laslow, Peri; Seal p-seal-R006-j Rowland,
  Iris. Everything on: Birthright p-bt-A015-g-all1 (Corrin, Rinkah, Kaze); Conquest p-cq-B010-g-all1 (Corrin,
  Felicia, Elise); Revelation p-rv-C012-g-all1 (three units); Seal p-seal-S002-g-all1 (Corrin, Hinata 26 -> 31 HP,
  Azura 16 -> 22 HP).
- **Skill slots / Revelation stays robot**: it rests on the C014 pair plus the Sakura and Hayato memory proofs; no
  reviewer opened a Revelation skill-slots pair.
- **Classes x4 and Children (Birthright, Conquest, Revelation) confirmed SEEN** by the second reviewer's own look
  (Rinkah, Kaze, Laslow, Peri, Hinoka, Azama, Scarlet, Rowland, Iris; Shiro and Siegbert).
- **Seed guarantees stay mem / mem (part), never raised.** No picture pair exists. The Seal cell rests on tables
  and readback only: Seal all3 Felicia is carried in every Seal job from the base save as her old class, so her
  repaired class is never on a map; her "proven" is the Person row, the GameData readback and the S001 placement
  readback with a staff in the laid items; Seal all2 Elise is proven the same way. On Fates, all2 Jakob and all3
  Silas are proven by placement readback, not by a unit on the map. The staff-in-hand insert (bt-A002-recany,
  Felicia holds Bloom Festal in slot 3) is a memory proof, not SEEN.
- **The seal track's own Seal guarantee check was NOT REACHED** (build/r76/seal/verdict.json): chapter select into
  R002 never places the R002 healer cover (the Odin spot on seed r76s4) and R004 never places the opener cover (the
  Arthur spot). The plan's only Odin join placements found are Dispos/C/C017 #55 and #61 (a Revelation file), while
  config/randomizer/seal_rules.json lists Odin in R002's army ([medium]). If Odin is not placed in Seal R002, the
  Seal healer need is met on paper only.
  **Host check after integrate (commit step, Seal tables, read only):** guarantees.join_placements on the Seal facts
  gives Odin's join placement as Dispos/C/R002 #1 (team 0, flags 0x720, not scene-only), and r76s4's plan.json and
  patch.txt change that placement's item 1 from Thunder to Recover (the general weapon swap for the repaired
  Troubadour already puts a staff in hand, so staff_in_hand adds nothing). The C017 #55 / #61 rows are only the
  route_joins of the Revelation variant PID_C_オーディン, which no Seal chapter loads. So the plan side has no gap.
  Still NOT REACHED: that R002 #1 creates Odin in a real Seal story game (chapter select from a Fates save places
  the save's army; no Seal story save exists), so the Seal guarantees stay mem (part) / [medium].
- **Carried cells.** Starting items and the other 136 carried cells have no round-76 pair job ("a pair job is
  missing" in pairs-verdicts.json); they carry round 72's marks because run_changes76.json shows identical patch
  cells for their runs, NOT re-seen on the round-74 program.
- **Pokes.** The chapter-select `route_mask` write in 16 Seal jobs (chapter-table record +0x14, 00 -> 04) was missing
  from docs/CHEATS.md; integrate added it under 'Track check, round 76'. Not a content poke: no table mark changes.

### What changed against round 72's table
- Children / Birthright: robot -> **SEEN**: r76 check reviewer: p-bt-X007-c Shiro Spear Fighter -> Diviner (childhover, childpage; classes run vs children on the same seed) (review/children_bt.png)
- Children / Conquest: SEEN+poke -> **SEEN**: r76 check reviewer: p-cq-X015-c Siegbert Cavalier -> Dark Mage (childhover, childpage) (review/children_cq.png)
- Children / Revelation: robot -> **SEEN**: r76 check reviewer: p-rv-X007-c Shiro Spear Fighter -> Diviner (childhover, childpage) (review/children_rv.png)
- Seed guarantees (repaired class and healer's staff in memory) / Birthright: None -> **mem**: 6 of 6 repairs that are a final cover on this path proven in memory (the Person row's class cell, every GameData cell read back right in every all1-3 break job; a healer's staff on the map or in its join placement read back right); every plan's needs met (none missed). all2 Felicia staff -> JID_アドベンチャラー女: Person-row class laid, GameData read back right in 93 of 93 break jobs; on the map with it in bt-A002-all2; staff in hand True (A002 staff in the placement, read back right) | all2 Jakob staff 
- Seed guarantees (repaired class and healer's staff in memory) / Conquest: None -> **mem**: 3 of 3 repairs that are a final cover on this path proven in memory (the Person row's class cell, every GameData cell read back right in every all1-3 break job; a healer's staff on the map or in its join placement read back right); every plan's needs met (none missed). all2 Felicia staff -> JID_アドベンチャラー女: Person-row class laid, GameData read back right in 93 of 93 break jobs; on the map with it in bt-A002-all2; staff in hand True (A002 staff in the placement, read back right) | all2 Jakob staff 
- Seed guarantees (repaired class and healer's staff in memory) / Revelation: None -> **mem**: 6 of 6 repairs that are a final cover on this path proven in memory (the Person row's class cell, every GameData cell read back right in every all1-3 break job; a healer's staff on the map or in its join placement read back right); every plan's needs met (none missed). all2 Felicia staff -> JID_アドベンチャラー女: Person-row class laid, GameData read back right in 93 of 93 break jobs; on the map with it in bt-A002-all2; staff in hand True (A002 staff in the placement, read back right) | all2 Jakob staff 
- Seed guarantees (repaired class and healer's staff in memory) / Seal of Flames: None -> **mem (part)**: 2 of 3 repairs that are a final cover on this path proven in memory (the Person row's class cell, every GameData cell read back right in every all1-3 break job; a healer's staff on the map or in its join placement read back right); every plan's needs met (none missed). all2 Elise door -> JID_シーフ女: Person-row class laid, GameData read back right in 41 of 41 break jobs; not on the map at the readback frame of its join chapter | all3 Felicia staff -> JID_陰陽師女: Person-row class laid, GameData read b
- Re-judged with the same mark: Shuffle (route) / Birthright (robot), Shuffle (route) / Conquest (robot), Shuffle (route) / Revelation (robot), Shuffle (route) / Seal of Flames (robot), Shuffle (any) / Birthright (robot), Shuffle (any) / Conquest (robot), Shuffle (any) / Revelation (robot), Shuffle (any) / Seal of Flames (robot), Classes / Birthright (SEEN), Classes / Conquest (SEEN), Classes / Revelation (SEEN), Classes / Seal of Flames (SEEN), Skill slots / Birthright (robot), Skill slots / Conquest (robot), Skill slots / Revelation (robot), Skill slots / Seal of Flames (robot), Shops / Seal of Flames (mem), Castle rewards / Birthright (mem), Castle rewards / Conquest (mem), Castle rewards / Revelation (mem), Castle rewards / Seal of Flames (mem), Everything on / Birthright (robot), Everything on / Conquest (robot), Everything on / Revelation (robot), Everything on / Seal of Flames (robot)

## FAILs
None of the 168 cells failed.
Known misses (not cells): the 2 s Start-game target after a late row change (engine item, above).


## Pokes
Every check job made the chapter-select pokes (chapsel.py rule 2: the world-map spot record and the current chapter
pointer) in its own copy; not content pokes, not marked. No job of this check made a content poke (final76.py scans every
re-judged pair's job.pokes and pokes_extra: none). docs/CHEATS.md section 6 'Round 76 pokes' lists them.

## Robot notes (honest)
- At most 4 check robot jobs at once (run4.py: 4 workers, claim files, the claim deadline 14:15); the page robot's six runs
  ran before the workers (pb.py), beside the full and seal tracks (1 job each). No job ran twice at once.
- shascan.json: 602 result files carry the frozen boot-server b3ebe748 + capture library
  405f2bac (page robot: exe c49a0ab1); 0 carry another sha.
- Lanes: 52 of 52 queued lanes ended; not claimed by the deadline: none.
- No crash burst this time (round 72's 0xC0000005 burst did not repeat): 0 retries of break jobs. One mid-run classify read a result file while brk.py was rewriting it (seal-R005-off had no sha for a moment); the final classify reads it with the frozen shas: PASS.
- The route-variant memory proofs of round 72 were re-run (cjobs c-rv-C008-R-off/-sakura, c-rv-C009-R-off/-hayato, one lane each, 13:26-13:42): Sakura's remade one-cell run shows skills [255, 3, 36, 0, 0] (the new 0x03), Hayato's [255, 112, 0, 0, 0] (unchanged): both MEM; the Revelation skill-slots cell rests on the C014 pair (PASS, 3 valid pairs).
- Page robot: one retry (pbv-s -> pbv-s2, the driver's seed file in the wrong folder).
- The full check ran 11:29-13:42 (workers), page robot 11:20-11:29; D: free 59 GB at the start, 44 GB at the end (all tracks).

- No visible window (watch.py at every look: VISIBLE: [] each time). STOP_ROUND never existed. No new play, no engine
  build, nothing in tools/randomizer or config/randomizer changed, no write to %APPDATA% / %LOCALAPPDATA% (every job's
  data, APPDATA and LOCALAPPDATA below build/r76/check).

## Where things are
- Contact sheet: build/r76/sheet/index.html (the table, every re-judged pair OFF left / ON right, the reviewer's pictures,
  the guarantees in memory, the break counts, the page robot).
- Data: build/r76/check/final76.json, table76.md, break.json, handover.json, nz-verdicts.json, guarantees76.json,
  pairs-verdicts.json, cells-verdicts.json, run_changes76.json, remap76.json, shascan.json, review/seen76.json,
  pagebot/*/result.json and result76v.json.
