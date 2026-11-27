# The check robot's strict pairs and new screens (tools/harness/rcheck.py), round 59

**In plain words.** Round 58 counted some on/off picture pairs that did not prove anything: the cursor was on another
unit, or nothing had changed, or several settings had the very same ON picture. The new driver only counts a pair
when the robot can show, from memory, that both pictures are of the same screen, at the same frame, about the same
unit, that the setting's own value really differs for that unit, that the pictures differ, and that the ON picture is
not the same file as another setting's. It also reaches new screens: a level-up, the Master Seal and Heart Seal class
lists, a child unit on the map, and the castle shops. All runs are headless boot-server copies on a frozen copy of the
round-58 exe (`build/r59/robot/bin`, sha256 in SHA256.txt), each with its data, APPDATA and LOCALAPPDATA below
`build/r59/robot/jobs/<job>/`, below normal priority, `build/STOP_ROUND` checked before every start and step. Cheat
track only (exp, item and enemy-HP pokes go into the job's own copy). Nothing counts as done until the owner says ok
(F-037): a VALID pair is "robot", not "SEEN".

## The pair rules (judge_pair, self-tested 18/18)
A pair is VALID only if all hold; anything else is REJECTED with its reason and never counted:
1. same screen (markers' current process) and same frame;
2. the same screen history before the shot (the runs did not take different screens earlier: a timing shift makes
   later pictures differ for the wrong reason; this rule rejected 11 level-up shots that rule 1 alone would pass);
3. the same unit (person id read from memory: the unit under the map cursor, or the unit at the menu's index in the
   army list);
4. the setting's OWN field differs for that unit (growths, personal skill, Master Seal targets of its class, Heart
   Seal classes, class, items, ...), or, for settings with no unit (shops), its patch cells hold the OLD values in the
   OFF run and the NEW values in the ON run;
5. the pictures differ in pixels (not just file bytes);
6. the ON picture is not byte-identical to another setting's ON picture at the same chapter and screen.

## New screens (how the robot gets there)
| Screen | How | Proven on |
|---|---|---|
| Level-up | every player unit's exp -> 99; End; if defending gave no exp (a staff user cannot strike back), a unit next to an enemy attacks it with the enemy at 1 HP (A on the unit, A in place, Attack, weapon, target, confirm); shots every 6 frames through the window | A015 Silas |
| Master Seal class list | a Master Seal (IID_マスタープルフ, item 311) poked into the unit's item slot 5; Inventory > the unit > Items > the seal > DOWN x3 (Use) > A | A015 Saizo |
| Heart Seal class list | the same with IID_パラレルプルフ (item 312). One seal per job: the preparations menu keeps its cursor | A015 Saizo |
| Child unit on the map | the child paralogue by chapter select; the cursor onto the 'other' force unit; its panel and R page | X007 Shiro |
| Castle shop | the recorded castle routes, shots at the buy list: Birthright Rod Shop (`bt-castle-shop` 7932), Conquest Staff Store (`cq-ch10` 9750 / 10100) | both |
| Skill page | **not found**: touching the skill icon, X, Y and START on the unit page open no skill description. The unit page's skill icons are the visible place (the personal skill icon changes) | - |
| Castle rewards | **not reached** (no route or screen shows the castle battle/visit rewards) | - |

## Proof: one valid pair per new screen (round-58 exe; the reviewer looked at every picture)
Verdicts: `build/r59/robot/pairs-final.verdicts.json` (18 pairs: 8 VALID, 10 REJECTED); pictures side by side:
`build/r59/robot/pairs-final-valid.png` and `build/r59/robot/pair-levelup-growths-A015.png`.

| Setting | Screen | Chapter, unit | What differs (OFF -> ON) | Verdict |
|---|---|---|---|---|
| Growths | level-up window (frame 8256) | A015, Silas | gains HP/Str/**Spd** -> HP/Str/**Mag** (Mag growth 5 -> 35) | VALID, looked at |
| Promotions | Master Seal list | A015, Saizo | Master Ninja / **Mechanist** -> Master Ninja / **Butler** | VALID, looked at |
| Heart Seal classes | Heart Seal list | A015, Saizo | **Samurai** -> **Fighter** | VALID, looked at |
| Personal skills | Master Seal and Heart Seal pages | A015, Saizo | the personal skill icon (skill 171 -> 177) | VALID x2, looked at |
| Shops | Birthright Rod Shop | castle (bt-ch6-clear) | row 5 Concoction 600G -> Elixir 900G | VALID, looked at |
| Shops | Conquest Staff Store | castle (cq-ch9-clear) | row 5 Concoction -> Elixir | VALID x2, looked at |
| Children | child on the map | X007, Shiro | **nothing**: Shiro's class and Heart Seal classes are equal in both children runs (vs classes alone, and vs off). The child's class is decided when he joins, not while he is an 'other' unit | REJECTED (true: no visible effect on this screen) |

Rejected as they should be: the unit page for promotions / personal skills (Corrin is not the changed unit there:
same field, same pixels, and the settings' ON pictures are one file), growths on the level-up shots before the third
stat shows (equal pixels), and every level-up shot after frame 8256 (the OFF window ends earlier: different screens
or a different history).

## Not done / open
- Children: a visible pair needs the child to JOIN (a recruit talk in X007, then his page). Not built.
- Shops on Revelation and in the Seal edition: no recorded castle route reaches a shop there. Not built.
- Castle rewards and a skill description page: not reached (above).
- The pairs file names the pairs by hand (`pairs-final.json`); the check step should generate them per setting and
  per chapter (one seal screen per job).

## Use
```bash
python tools/harness/rcheck.py --selftest                              # 18/18 pair rules on invented records
python tools/harness/rcheck.py run build/r59/robot/lanes/rrA.json      # a lane of jobs, one after another
python tools/harness/rcheck.py pairs build/r59/robot/pairs-final.json  # -> pairs-final.verdicts.json
```
Job keys: `name, chapter, base?, game, route_byte?, lend?, run (a build/r58/check/runs id or null), mode
select|direct|route, screens [unitpage, mseal or hseal, levelup, child], steps full (End, enemy phase, save, reload),
seal_unit (army index), levelup_skip / levelup_step / levelup_shots, cell_files (shops)`.

## Round 59 check step: the everything-on check (build/r59/check)
Drivers (all headless, own data/APPDATA/LOCALAPPDATA under build/r59/check, below normal, STOP_ROUND checked, at most
6 jobs at once, frozen exe copies with their sha256 checked before every job and written in every result):
- `build/r59/check/brk.py` (exe A, `bin/`) and `brk2.py` (exe B, `bin2/`): every chapter of every path, preparations,
  map, enemy phase, battle save and reload, with the memory readback of every patch cell (GameData, placements,
  chapter person files) on the map and after the reload; `classify.py` -> `break.json` / `break2.json`.
- `build/r59/check/pairs.py`: rcheck.py's strict pairs (judge_pair's rules unchanged) plus four screens: `unitgrid`
  (the Preparations unit grid, the bottom-screen panel of each of the first 12 units), `mapunits` (the cursor on each
  player unit on the map: joiners), `enemies` (the cursor on up to 8 enemies, unique-person enemies first), `battles`
  (enemy-phase battles, then a chosen player unit attacks: battle pictures for the recolour row). `judge.py` ->
  `pairs-verdicts.json`; `sheet.py` -> build/r59/sheet/index.html.
- Judge additions: the shuffle rows are judged per army slot (same slot, the slot's person differs); settings that
  need a baseline (skill slots, children: classes; stronger enemy weapons: enemy weapons) use a run with the
  baseline's seed, and rule 6 does not compare a setting with its own baseline; skill slots also need the class equal;
  recolour needs the defender/attacker's spot in the ON run's recolour list.
- chapsel: `map__anonymous_namespace__ItemMenuSend` answered with A (a full inventory getting an item in the enemy
  phase stopped two Revelation runs).

### Results (round 59 integrate, 2026-11-21)
- **Break check:** Birthright 41/41, Conquest 30/30. Revelation 22/22, except C026 all2 and C012 all3 (the enemy
  phase did not return). Seal 38/41 (R021, R023 and Y004 reload differs, off too).
- **Pairs:** the per-setting table is in docs/REPORT_2027-01-02.md.
- **Not reviewed:** the check step's review of the final-exe pairs was not available. Only these pairs were opened by
  eye: shuffle Birthright A004, shuffle-any Seal R002, recolour Birthright A015 (faint). Every other PASS is robot-only.
- **Never counted:** stronger enemy weapons, because the upgrade draw moves the dice.

## Round 60 screens track (build/r60/screens)
All runs headless on a frozen copy of the current play/game build's boot-server and capture library
(build/r60/screens/bin: boot-server e71515c5..., library 610f791d..., the same as round 59's exe B), sha checked
before every job and written in every result; data, APPDATA, LOCALAPPDATA below build/r60/screens/; below normal;
STOP_ROUND checked; at most 4 jobs at once; cheat track only (pokes into the job's own copy). Driver
`build/r60/screens/p60.py` (round 59's pairs.py with these additions), judges `judge60.py` (judge_pair's six rules
unchanged), `music60.py`, `upgrade60.py`; pictures `build/r60/screens/sheet/index.html`.

New or changed screens (each proven once with a strict valid pair, looked at by eye):
| Screen | How | Proven on |
|---|---|---|
| Unit grid, full page | the saves of Conquest, Revelation and Seal open the bottom panel on its simple page (no Atk/Hit/Crit): the robot touches the page icon once (`grid_page`) | weapon stats, Conquest B010 Felicia: Crit 4 -> 5, Hit 116 -> 113 |
| Weapon poke | the same weapon (one that got a visible trait in the ON run) poked into two units' first item slot in OFF and ON (`pokes`) | weapon traits, Revelation C012 Hana (Axe Splitter, Crit 3 -> 18); Seal S002 Felicia (Quill Pen, Crit 5 -> 20) |
| Level-up over several turns | `levelup_turns` ends up to N turns (Conquest: no enemy attacks on turn 1); the window's unit = the last whose level rose, read after the shots (round 59 read the unit before the level was written, so Revelation and Seal had no unit; with several turns an earlier level-up must not count). Two units can rise in one battle (a pair-up): both are named (`level_up_candidates`) | growths, Conquest B010 Nyx (gains Mag+Lck -> HP+Lck) |
| Enemy-phase battles over several turns | `battle_turns` (records of turn t renamed t<t>battle...) | recolour, Conquest B010 Effie's hair (lavender -> pale blond; small: Effie is in the background) |
| Map song in memory | `mem_scan`: every place in memory naming a STRM_ song at the map shot, OFF vs ON; the differing places are the map's settings sheet, the boss song pointer, and one runtime buffer that holds the label of the song the game started | music, all four paths |
| Joiners after turn 1 | `pre_turns` ends N turns before the map look | no pair: the Revelation reinforcement joiners did not arrive in 3 idle turns |

Notes: `rust_log` and `log_grep` job keys exist (rcheck.py) but the server does not log RomFS file reads (one RomFS
archive is opened once), so the stream file cannot be seen that way. A sound recording needs a boot-server
command (plan: build/r60/screens/plans/SERVER_AUDIO.md).

## Round 60 check step and its review (build/r60/check, final build 09740aa7 / a3f0bc67 / 610f791d)

- 995 robot results, all on boot-server a3f0bc67 + library 610f791d (0 from another build); break check 536/536.
- Per-setting table: 116 cells. After the check reviewer opened the pairs (build/r60/integrate/table_reviewed.json):
  **56 SEEN, 41 robot-only, 10 memory-only, 9 FAIL**. (The check's own line said 31 SEEN / 12 memory; final.json had
  33 SEEN, 64 robot incl. 10 memory, 9 FAIL; the reviewer then opened 23 more robot cells and kept weapon special powers
  on Conquest as robot, because the special power itself is not on the screen.)
- Rejected in review: boss classes on all four paths (every pair shows a generic enemy and the baseline run had another
  seed: that is the enemy class draw, which round 59's judge counted by mistake) and Seal recolour (the recolour run
  also swaps the person, so Hit differs too).
- Caveats the reviewers asked to state:
  - Children on Revelation (X007 Shiro, Spear Fighter -> Diviner): the OFF side is the classes run, not a plain off run.
  - Class growths on Seal (variance 50): the ON run's Fighter class growths are all 0. A real change, but it backs
    Grok's unbuilt "floor at half the original" pick (owner's call).
  - Weapon special powers on Revelation and Seal: the same weapon was cheat-poked into both runs, not a natural draw.
  - Class bases on Revelation: only the Rating changes on that page (89 -> 97).
  - Stronger enemy weapons: proven the only change with the same seed (Fates 637/637, Seal 343/343 cells are listed
    upgrades), but the upgrades seen are sidegrades by the game's own Rating (Barb Shuriken -> Steel Dagger 61 -> 59).
  - HANDOVER (handover.py): on the off runs class_ok and growth_ok are forced true, so only the on runs are proof
    (Revelation 13 Kaden/Keaton, Conquest 9 Nyx). Revelation 9 Hayato's variant row was not on the map on turn 1.
  - Music: memory label of the started song only (OFF old, ON new on all 4 paths), no audio fingerprint.


## Round 61 cells track (build/r61/cells): the FAIL cells again

All runs headless boot-server copies on a frozen copy of the current play/game build (build/r61/cells/bin: boot-server
a3f0bc67, library 610f791d, the round-60 final build), sha checked before every job and written in every result;
data, APPDATA, LOCALAPPDATA below build/r61/cells/jobs/<job>/; below normal; STOP_ROUND checked before every job; at
most 4 jobs at once; no window. Driver `build/r61/cells/p61.py` (round 60's p60.py + `enemy_at`, the battles'
defender by exp or by "next to the attacker", and `route_units`), judge `build/r61/cells/judge61.py` (judge_pair's six
rules unchanged, plus the per-setting extras written at its top) -> `build/r61/cells/verdicts.json`. Runs made with
today's tools by `build/r61/cells/mk/mkruns.py` into build/r61/cells/mk/after/runs.

| Cell | Pair (OFF -> ON, same seed) | What differs | Verdict |
|---|---|---|---|
| Skill slots, Revelation | C014 classes run -> classes + skill slots (class) | Elise Resistance +2 -> HP +5 (HP 24 -> 29), Arthur HP +5 -> Good Fortune (HP 29 -> 24), Effie Defense +2 -> Locktouch; class equal | robot, 3 valid (needed the skills.py fix below) |
| Skill slots, Revelation 9 end (Hayato) | rv-ch9 route replayed OFF and with a one-cell test patch (his C_HANDOVER row's skill) | Hayato joins in the chapter's END event: skills [Magic +2] -> [Locktouch], class equal; every route shot byte-identical | memory |
| Skill slots, Revelation 8 end (Sakura) | rv-ch8 route, one-cell test patch (her C_HANDOVER row skill.1 Miracle -> Odd Shaped) | Sakura joins in the END event: [Miracle] -> [Miracle, Odd Shaped] (her class teaches Miracle itself); route shots equal | memory |
| Boss classes, Birthright / Conquest / Revelation | Paralogue 2 (X002) from each path's save: enemy classes -> enemy classes + boss classes | the boss "Invader": Swordmaster -> Master of Arms; patch level: the ONLY differing DisposUnit cell is that boss's class | robot (one pair per path, the same map) |
| Boss classes, Seal | R006: enemy classes -> + boss classes (`enemy_at` the two changed bosses) | "Chevois": Wyvern Lord -> Malig Knight (x2); the 7 differing cells are all boss rows | robot, 2 valid |
| Class growths, Conquest | B010 level-up: off -> class growths variance 50, seed r61f1cgrowths11 (the seed of 300 that moves the Dark Mage growths most) | Nyx's level-up: Mag+1 Lck+1 -> HP+1 Mag+1 Spd+1 Lck+1 (Dark Mage HP growth 0 -> 45, Spd 10 -> 55) | robot, 16 valid; rule 2 read as "history equal up to the level-up window" (the ON window runs longer because more stats rise) |
| Stronger enemy weapons, Birthright | A010: enemy weapons -> + upgrade 50 (`enemy_at` the upgraded units) | Diviner: Calamity Gate -> Fimbulvetr, a listed upgrade of A010 | robot, 1 valid |
| Recolour, Seal | S002: the recolour run with its colour lines taken out (same seed, same shuffle) -> the recolour run | the Felicia spot's battle hair (#E6C8B4 -> #DCD9D3, faint), battle panel equal (HP 24, Hit 98%) | robot, 4 valid; the enemy missed, so the unit is the only recoloured one of the two next to the attacker (read from memory) |
| Class bases, Seal (reopened) | round 60's S002 pictures | not a copy slip: bases and class bases both raise Corrin's HP 37 -> 39, through different cells (personal HP base 2 -> 4; Dark Prince class HP base 17 -> 19); Ratings differ (89 vs 80) and Hinata differs (26 -> 27 vs 26 -> 29) | stays SEEN |

Explained, not paired:
- **Revelation late joiners.** C008 and C009 place their joiners (Support01: Kaze, Sakura, Hana, Subaki; Hayato) in
  the chapter's COMPLETION event (the scripts' order: MapEventBeginForComplete ... Support01), so they never stand on
  the map during the battle: 8 idle enemy turns showed none of them (jobs c-rv-C008-J8-*, c-rv-C009-J8-*). C010's
  joiners (Oboro, Hinata, Takumi) did not arrive in 8 idle turns either. The two route jobs above prove the end-event
  joins in memory.
- **Boss classes on Fates** reach only 4 paralogue bosses (docs/rando/ENEMIES.md round 61). Grok:
  docs/collab/BOSS_CLASSES_GROK.md.

Tool changes behind these pairs: skills.py edits the route-variant HANDOVER rows too (laid as tables/PersonChapter.csv;
tests in tests/test_rando_skills.py); enemies.py leaves the boss-classes switch out of its random key.

## Round 61 check step and its review (build/r61/check, final build ff85e43d / 4d0b60c9 / 610f791d)
- 1043 robot results, all on the final boot-server and library (the robot results do not record the game exe sha;
  the exe is proven by file hash and by the 4 pagebot results), 0 log faults, no window. Break check 536 jobs:
  all pass except Seal Y006 on all1 and all2 (the robot could not open the map menu at the turn-2 save step: every
  tile it tried opened the unit command; chapter start, preparations, enemy look, readback 2637/2637 and enemy
  phase passed; save and reload are NOT checked there).
- Correction (review): besides Y006 x2 and the 4 Nuzlocke chapter jobs (expected stop), **8 more pair jobs ended
  ok=false**: pjobs/p-rv-X007-c-{classes,children_c} and sjobs/p-rv-X015-C, X016-C, X017-C {classes,children_c}
  (castle or sortie menu not found after 60 steps, last screen SystemMenu). None feeds the table (Revelation Children
  uses p-rv-X007-C2).
- Table after the reviewer (build/r61/integrate/table_reviewed.json, made by build/r61/integrate/review_table.py):
  116 cells, 66 SEEN, 43 robot, 6 mem, 1 FAIL (Seal Children, owner call). Music counts as SEEN by sound: the reviewer
  checked the OFF/ON fingerprints (0.498/0.459/0.491/0.434, rule < 0.8); nobody listened.
- Corrections (review):
  - Seal recolour: in the pair in final.json no pixel differs by more than 12 levels; "pinkish -> paler blue-white"
    overstates it. Faint, zoomed only; the OFF side is a test-only run. Birthright, Conquest and Revelation recolour
    are also zoomed-only (Conquest: no pixel moves 24 levels or more).
  - Stronger enemy weapons: listed upgrades, but some are sidegrades by the game's Rating (cq Barb Shuriken -> Steel
    Dagger 61 -> 59; Seal Steel Club -> Steel Axe 56 = 56). Birthright's Diviner also shows Spd/Def 12/5 vs 11/4:
    Calamity Gate's own stat bonus (bases equal).
  - Seal class growths (delta mode, variance 50): 11 spoiler lines are all zero, e.g. the Fighter class growths
    become 0 0 0 0 0 0 0 0. The game laid what the spoiler says; the clamp at 0 is a design point for the owner.
  - The 3 Fates boss-classes pairs are the same Paralogue 2 boss (Invader, Swordmaster -> Master of Arms).
  - The assemble log lines "FAIL build/harness/saves/rv-ch26-clear.zip is missing" are test_check_all's fake-tree
    samples; the real save exists.

## Round 62 robot track (build/r62/robot): Y006, the 8 stopped paralogue jobs, new screens, the pair plans
All runs headless on a frozen copy of the current play/game build (build/r62/robot/bin: boot-server 4d0b60c9...,
capture library 610f791d..., the round-61 FINAL, sha checked before every job), data/APPDATA/LOCALAPPDATA below
build/r62/robot/, below normal, STOP_ROUND checked before every start, at most 4 jobs at once, no job retried more
than once, no window. Drivers: `brk62.py` / `p62.py` (round 61's brk.py / p61.py loaded read-only, folders moved),
`run4.py` (lanes side by side), `judge62.py` (-> verdicts.json). Cheat track only.

### Fixes (tools/harness/chapsel.py, tools/harness/rcheck.py) and their proof
| What | Cause | Fix | Proof (each run once) |
|---|---|---|---|
| Seal Y006 all1/all2 save step | an A that answered the last turn-start event landed on the map and picked up the unit under the cursor; every "free" tile then moved that unit and opened its UnitCommand | `drop_pick`: B twice before the system-menu search and after every failed tile (B on the bare map does nothing) | Y006 all1 and all2: save, reload, readback 2637/2637 and 2624/2624, dispos 173/173, units equal. No regression on Y006 off, bt A015 off, cq B010 all1, rv C012 off (all pass the full chain) |
| 8 Revelation paralogue pair jobs (X007, X015-X017 classes/children_c) | the base pick took rv-ch16-clear, whose Continue goes straight onto chapter 17's map | `pick_base`: Revelation paralogues X007 and later start from rv-ch18-clear (My Castle after chapter 18; the Nohrian parents join in chapter 17); rv-ch15/16 are never used (RV_NO_CASTLE); selftest 32/32 | all 8 run to the end (preparations, map, child screen) |
| Child not on the 'other' force | Siegbert (X015) starts in the player army | `child_look`: the player unit that the base save's army does not hold; job key `child_turns` (end N turns first) | Conquest X015: Siegbert found, children pair VALID (Cavalier -> Dark Mage). Revelation X015 has the same fallback but was not run again (its one relaunch, with child_turns 3, found no 'other' unit) |

Children pairs judged (rcheck judge_pair, rules unchanged; OFF = classes run, ON = children run, same seed):
- Revelation X007 Shiro: VALID (Spear Fighter -> Diviner; looked at, build/r62/robot/pair-children-rv-X007.png).
- Revelation X017 Ignatius: VALID (Knight -> Dark Mage).
- Conquest X015 Siegbert: VALID (Cavalier -> Dark Mage).
- Revelation X016 Forrest: REJECTED. The children run gives him the same class, so this seed shows no visible effect
  for him. The rejection is correct.

### New screens and judges (for the final check; rcheck selftest 52/52)
- `growthview`: Preparations > Select Units > the army unit given by `growth_unit` or `growth_pid`. The list is a
  3-column grid, so DOWN moves a whole row.
- `growthview_map`: the cursor on a player unit on the map.
- Both take these shots: gv_stats, gv_stats2 (the idle noise), gv_growths (after `growth_keys`, default SELECT) and
  gv_back (the same keys again). With `growth_touch [x, y]` they also take gv_touch and gv_touch_back.
- Every shot names the unit and its `growth_total` (personal + class). The job also keeps every army unit's totals
  (`army_totals`). `growth_page` touches the page icon first.
- **Finding on the current exe.** In the Select Units grid, SELECT already opens the game's own "Start the battle?"
  question. In the gv-neg jobs it showed as GameDialogYesNo with No as the default; B closes it and no battle starts.
  On the map SELECT does nothing: the pictures stay within the idle noise. The core's growth view must not collide
  with that question. The check takes the screen and the keys from the core's notes.
- `judge_growthview` (one run): the press changes the picture by more than the idle noise, and the second press
  brings the stats back. All four shots must be of one unit on one screen.
- `judge_pair` with the settings `growth_view` and `growth_floor` (field growth_total).
- `judge_floor`: the OFF side has a total under 20, and every ON total is 20..100.
- `judge_same`: for a unit that must not change. Its fields and pixels must be equal.
- `judge_ladder`: one enemy's item slots, per difficulty.
  - Easy: +1 forge.
  - Normal: the next rung, or +1 forge.
  - Hard: the next rung + 1 forge, or +2 forges.
  - Killer, Brave and effective weapons are forged only. The never-list stays unchanged. The forge is at most 7.
  - The forge level is item word 2 >> 8 & 0xF.
- `judge_boost`: the HP rise is ceil(10% x step x (personal + class base HP)).
  - It must be exact for an army boss and at least that for the others. A smaller rise is allowed only at a cap.
  - Weapons (round 63, F-051): every forged weapon must show might +1 / +2 / +3 on Easy / Normal / Hard, the
    might the player sees, not a forge count. `might_add(item number, forge off, forge on)` gives the shown rise;
    the default `name_slot_might` is the enemy/boss row (name slot 1: the second forge table, +1 might a level).
    Pass another callable for a playable person's row (+2 a level). A smaller rise is allowed only when the forge
    stops at its maximum 7 (reported in `forge_capped`). The never-list is not forged.
  - Still open from the round-62 review: an HP rise below the plan is accepted as "capped" without checking the
    cap (check it against stats.boss_limits); it needs the never-list from tools/randomizer/weapons.py.
    **Fixed in round 66** (see "Round 66 might track" at the end).
  - Self-checks (57/57): round 62's +2 on Hard and +1 on Normal are rejected; a +2-a-level row and the forge-7 cap
    are covered.
- Job key `item_numbers` keeps {iid: item number} as laid, for the ladder judge.
- On real data (round 61 OFF against the rando track's r62fboosthard run):
  - The Birthright A014 boss is VALID (HP 33 -> 45, forge +2).
  - The Conquest B010 and B012 and Revelation C017 bosses are REJECTED, but only for "no weapon forged". The test
    passed no never-list, and Fujin Yumi, Raijinto and Iago's tome are legendary or can't-remove weapons. The check
    must pass the never-list.
- `bosskill`: the proof that a chapter runs past a boss's scenes with its new class. All pokes are cheat pokes in
  the job's own copy.
  - A player unit gets move bonus 60 (+0x12C, as in the cheat routes). Every enemy on the boss's tile gets HP 1,
    because a pair-up lead takes the hits first. The unit walks to a free tile next to the boss and attacks.
  - While the boss stands, the next unit attacks: up to 4 waves by default.
  - Fliers are tried when no walker can reach. A guard next to the boss is killed first if needed. There are up to
    4 attempts, each from a memory slot. `pre_turns 1-2` lets the guards walk away first.
  - It records the boss (its class before), the waves, the screens after the kill, `talk_after_kill`,
    `stage_complete` and `passed_scenes`.
  - Proven on Conquest B008 (defeat the boss): the battle talk, the death lines, stage complete and the castle
    sequence. passed_scenes is true.
  - Proven on Revelation X002 with Boss classes on (Master of Arms): the boss is killed in wave 2, the death lines
    play and the player phase comes back.
  - **Limits:**
    - The Revelation C013 and Conquest B010 bosses could not be reached on turn 2: no walker had a path, and the
      army had no flier. Such a boss stays "not proven by battle". The rando track's proof (opening scenes, map,
      enemy phase, save) still stands.
    - The HP-1 poke does not always reach the battle. On X002 the forecast showed 24 HP. The waves cover this.

### Pair plans for the final check (goal 10): build/r62/robot/plans
- `make_lanes.py write` made 21 lanes, 90 jobs and 62 strict pairs, with 15 run names per game (runs_r62.json,
  lanes/*.json, pairs_r62.json).
- `make_lanes.py fill MAKE.jsonl OFFJOBS OUT` puts in the made run ids and the floor's unit: the first army unit
  whose OFF totals have one under 20.
- Order: run the gv_* lanes first, then fill, then gf_*.

| Pair | Per path | OFF / ON | Screen, judge |
|---|---|---|---|
| Growth view toggle | bt A015, cq B010, rv C012, Seal Y006: randomizer off, growths on, and the map | one run | gv_*, judge_growthview (works with the randomizer off) |
| Growth view numbers | the same | off / growths | gv_growths, judge_pair growth_view |
| Growth floor | the same, with the unit that fill picks | off / growths | gv_growths, judge_floor; every army total is 20..100 and equals the spoiler's final table |
| Weapon ladder, one per difficulty | bt A008, cq B010, rv C017, Seal R006 | ladder_w_d / ladder_u_d (same seed, upgrade 100%) | enemy0-9, judge_pair + judge_ladder; the reviewer reads the Rating |
| Story boss classes | bt A014, A018; cq B010, B012; rv C017, C023; Seal R006 | enemy_classes / boss_classes_e (same seed) | enemy0-3: the class differs; same tier, gender and side; items equal; boss rows only. Plus bosskill on the ON job |
| Tougher bosses, one per difficulty | bt A014; cq B010, B012 (army bosses: exact HP); rv C017; Seal R006 | boost_off_d / boost_on_d (same seed) | enemy0-1, judge_boost |
| Recruit unchanged | rv X015 (Takumi in the army) | boost_off_hard / boost_on_hard | gv_stats, judge_same |

## Round 64 note: new job keys live in round drivers (not in rcheck.py yet)
tools/harness/rcheck.py did not change in round 64. The round's new robot steps are in copies of the round-63 driver:
- build/r64/bosses/p64.py: `place_next` (the attacker is put on a free square next to the boss: its x/y in the unit
  and the map's unit grid, found per chapter by a state search, pair-ups handled), the armed-attacker swap (a singer
  is replaced by the next armed unit that has not acted), `boss_look` (map cursor on the boss, one picture).
- build/r64/bosses/might/p64m.py: `touch_page` (the bottom screen's page icon touched once, so the unit page shows
  Atk).
- build/r64/checks/robot/p64.py: `attack_unit` (a named unit attacks the nearest reachable enemy with bosskill's
  pokes) and `dropcheck` (kill-and-compare of a target's drop).
- build/r64/seal/p64s.py: an x/y-only `place_next` (the game did not take it) and `attacker_pid` (did not pick the
  right unit).
None of them has a selftest yet. Moving the working ones into rcheck.py with selftests is open (docs/tests/STORY_BOSSES.md).

## Round 65 side track: round 64's job keys moved into rcheck.py (selftest 90/90, was 57/57)
The working round-64 keys now live in tools/harness/rcheck.py (module doc lists them); round drivers no longer need
their own copies. The full check of round 65 runs on its own frozen copy of the old file (build/r65/check/bin,
sha 306ac5d5...), so none of this reached it. Old drivers that still wrap these methods keep working (checked:
build/r64/bosses/p64.py loads; `boss_look` runs once per job even when a driver also calls it).
- `place_next` (CheckRun._place_attack, chosen by `_attack_from`; the walk is `_walk_attack`): the attacker is put on
  a free square next to the target (its x/y and the map's unit grid, `grid_search`: pair-up tiles left out, a few
  reference units, under 3 single units no guess), picked and told to stay, then attack_keys.
  - armed-attacker swap (`pick_attacker`): a unit with no equipped weapon (bit 0x4000), or one that already acted in
    this attempt, gives way to the next armed living unit.
  - NEW talk skip (`command_outcome`, `next_downs`): a talk window before any battle forecast means Talk was the
    highlighted command; the square is tried again from its memory slot with one more DOWN (up to `command_downs`,
    default 3). `command_shots`: pictures of the unit command before and after the DOWNs and of the talk.
  - NEW: when no square starts a battle, the state before the call is loaded back (round 64's flier tries began
    inside Arthur's talk).
- `boss_look` (CheckRun.boss_look): cursor on the boss, shot boss_page. Default off in rcheck (round 64's driver had
  it on by default: set it in the job).
- `touch_page`, `enemy_at`, `enemy_page` (CheckRun.enemy_look; a pairs.py driver sets `P.enemy_look =
  R.CheckRun.enemy_look`), order by `enemy_order`.
- `attack_unit` (CheckRun.unit_attack) and `dropcheck` (CheckRun.drop_check, `drop_writes`, `items_gained`), both
  chosen by `boss_kill` on the bosskill screen.
- `yesno_left` (CheckRun.press, `yesno_buttons`): every A on a Yes/No question is LEFT A.
- NEW `talk_shots N`: after the boss battle, the first N new talk/event screens are shot (bosskill_talk<k>, listed in
  steps.bosskill.talk_pngs).
- Not moved: build/r64/seal/p64s.py's x/y-only `place_next` and `attacker_pid` (they did not work in round 64).

Selftests added (33): the armed test (1) and the swap (4), free tiles (2), grid search on a made-up memory (found with a
pair-up, one odd unit, no grid, too few units), command outcome (3), talk skip steps (3), yesno_left (2), drop pokes
(3), items gained (2), enemy order (1), the bosskill / attack dispatch (6) and press (2) on a stand-in run with no
server.

Proof in the game (frozen boot-server 1b8b2593 + capture library 610f791d, build/r65/side): A023 Arthur, randomizer
off and seed r63fboss1 (Hero -> Paladin): both killed after the talk skip, lines and the next player turn played
(docs/tests/STORY_BOSSES.md, "Round 65 (side track)"; sheet build/r65/side/arthur_sheet.png).

Open after round 65 (integrate review of the full check):
- **judge_boost's `capped` flag cannot fail** (`capped = 0 <= rise < want`, line 276 of the frozen copy): any smaller HP
  rise counts as capped, and it never compares against the real class-max cap. Together with the drop exemption it let
  Revelation's tb-rv-C017 pairs (Iago, Fimbulvetr is a drop, HP 38 -> 45 on all three difficulties) pass without
  showing the row; the round-65 table marks them **gap**. Labels that passed only as capped on Conquest: Hinata Hard 8 vs
  want 10, the B010 boss 5 vs 7 / 11, Saizo 5 vs 6 / 9 (those cells stand on the shown might). Fix in a side track:
  compute the cap from the run's tables (boss_limits / class max + the person's limit mod) and fail a rise below it.
- The new keys change two defaults for later jobs: `boss_look` is off unless the job sets it, and every bosskill result
  carries a `steps.bosskill.talk_pngs` list (empty without `talk_shots`).

## Round 66 might track: judge_boost's "capped" checks the real cap (selftest 102/102, was 90/90)

- **What "capped" checks now.** A short HP rise (0 <= rise < want) passes only when the caller gives `hp_cap`, the
  boss's personal-base HP cap from that run's own tables, and the ON personal HP (person_base[0] in memory) sits
  exactly at max(OFF personal HP, hp_cap) and the shown HP rise equals the personal rise. Otherwise it fails with
  the reason: "(no cap given)" or "(ON personal HP x is not at its cap: max(OFF y, cap z), shown rise r)". A rise
  of 0 passes only the same way (the randomizer's "an HP already at or above the cap stays"). A full rise still
  needs no cap.
- **Where the cap comes from.** New `boss_hp_cap(tables, row, jid=None)`: tools/randomizer/stats.py `boss_limits`
  (class max HP + the row's limit modifier - class base HP) on a passed-in tables object (F-047: a StatsTables of
  the run's game, Fates or Seal), the class taken from the unit in memory when given.
- **Selftests added (12):** a true cap passes; a fake cap above the ON value, no cap, ON above the cap and a shown
  rise that differs from the personal rise are rejected; "already above the cap" passes with rise 0 and rise 0
  below a cap fails; a full rise needs no cap; boss_hp_cap (class max - base, the limit modifier, the run's class
  wins, unknown class gives None) on a stand-in tables object.
- **Round 65's capped pairs re-judged** (host only, from build/r65/check/pjobs/tb-* result files and their runs;
  build/r66/might/rejudge65.py -> rejudge65.json / .out). Every label that passed only as capped sits exactly at
  its real cap, and the spoiler of the same run gives the same final personal HP:

  | Pair (round 65) | Boss | HP shown off -> on | rise / want | personal HP off -> on | cap (tables) | old | new |
  |---|---|---|---|---|---|---|---|
  | cq B010 Hard | Hinata (enemy0) | 30 -> 38 | 8 / 10 | 15 -> 23 | 23 | PASS (capped) | PASS (at cap) |
  | cq B010 Normal | B010 boss Takumi (enemy2) | 33 -> 38 | 5 / 7 | 18 -> 23 | 23 | PASS (capped) | PASS (at cap) |
  | cq B010 Hard | B010 boss Takumi (enemy2) | 33 -> 38 | 5 / 11 | 18 -> 23 | 23 | PASS (capped) | PASS (at cap) |
  | cq B012 Normal | Saizo (enemy0, enemy1) | 29 -> 34 | 5 / 6 | 14 -> 19 | 19 | PASS (capped) | PASS (at cap) |
  | cq B012 Hard | Saizo (enemy0, enemy1) | 29 -> 34 | 5 / 9 | 14 -> 19 | 19 | PASS (capped) | PASS (at cap) |
  | rv C017 Easy | Iago (enemy1) | 38 -> 45 | 7 / 5 | 26 -> 33 | 33 | PASS | PASS (full rise, at cap) |
  | rv C017 Normal | Iago (enemy1) | 38 -> 45 | 7 / 9 | 26 -> 33 | 33 | PASS (capped) | PASS (at cap) |
  | rv C017 Hard | Iago (enemy1) | 38 -> 45 | 7 / 13 | 26 -> 33 | 33 | PASS (capped) | PASS (at cap) |

  The other 22 tougher-boss labels of round 65 keep PASS. The B010 boss, Saizo and Iago still pass only on the
  drop/never exemption for the weapon (no forgeable weapon: no might shown); the fix makes their HP part honest,
  it does not make those pairs show might. Revelation's might is now SEEN on C007 (docs/rando/BOSS_MIGHT.md,
  "Round 66").


### Integrate review (round 66)
- Re-run on the host: selftest 102/102, rejudge65.py 30/30 PASS, judge66.py C007 Easy/Normal/Hard PASS with
  `capped` false. The cap in both scripts comes from `boss_hp_cap(tables, row, jid)` (stats.boss_limits); nothing
  is hard-coded.
- The selftest case "ON personal HP 13 above a cap of 10, rise 0, counts as capped" (flagged by the seal reviewer)
  is intended: the randomizer leaves an HP already at or above its cap alone, so ON = max(OFF, cap) = OFF.
- Older frozen judges (build/r65/check/judge62c.py, judge65n.py) call `judge_boost` without `hp_cap`. With today's
  rcheck.py a short HP rise judged by them would fail with "no cap given". Their results are frozen and were
  re-judged by rejudge65.py; new judges must pass `hp_cap=boss_hp_cap(...)`. No live tools/ or tests/ caller is
  affected.
- check_all row `rcheck-selftest` (same command) now names the round-66 cap check in its text.

## Round 72: the attacker is picked by person id (bosses_chests track; doc line added by integrate)
- `attacker_order(ps, want)` (pure) and the job key `boss_attacker_pid` (one person id or a list). bosskill used an index
  into the player list, and that list (the game's own unit list) comes in a different order from run to run (round 66
  R016: Corrin, Azura, Gunter, Kazahana on; Corrin, Felicia, Sakura, Takumi off, same save). With the key set, the wave
  pick, the guard path's second unit and place_next's armed-unit swap list put the wanted ids first, then everyone else
  by person id; jobs without the key keep the old order. Selftest 107 -> 113 (6 attacker_order checks); rcheck sha e997b76d.
- Known, not fixed in round 72: `judge_chest` adds the unit's gain and the convoy's gain separately, so a full inventory
  that sends one of the unit's own items to the convoy counts as a second gain (Conquest B010 village, Corrin's
  Dragonstone); build/r72/chests/judge72c.py judges the net gain. A missed bosskill attack repeats in every try (the hit
  roll comes from the saved state), so a fixed-attacker proof needs a scout pair or a hit poke.
- The full check's content pokes (seal, exp99, enemy HP 1, move 60 / placement, weapon) are listed in docs/CHEATS.md
  section 4 and marked "+poke" in docs/tests/CHECK_R72.md.

## Round 73b: judge_chest judges the net gain of unit and convoy (fixes track)
- `judge_chest` now takes one multiset difference over the unit's slots and the convoy together (before = bag + convoy
  before the open, after = bag + convoy after). An item that only moves from the bag to the convoy cancels out, so the
  round-72 Conquest B010 village (Killer Axe into a full bag, Corrin's Dragonstone sent to the convoy) is one gain and
  passes; the old code said "more than one item gained". build/r72/chests/judge72c.py is no longer needed for that case.
- Selftest 113 -> 116 (3 checks on that pattern, made-up item numbers): the moved-item case passes with the planned
  item, still fails when the original item comes, and the new item sent straight to the convoy with the bag unchanged
  passes. The round-72 code on the same input says FAIL ("more than one item gained"; checked by hand). rcheck sha 03bac124.
