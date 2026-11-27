# Chapter select on the cheat track (tools/harness/chapsel.py), round 58

**In plain words.** The robot can now start a chapter of any path straight from a packed test save. It does not
have to play there first. It then walks the chapter through battle preparations, the unit list and a unit's page,
the inventory, the map with its enemies, the first enemy phase, and a battle save that it loads again. Owner asked
for this in F-047 ("enable a chapter select cheat"). It is a robot test on the cheat track (docs/CHEATS.md), never
real play. Every file it makes is below `build/r58/chapsel/`. Runs are headless boot-server only (no window, below
normal priority, data/APPDATA/LOCALAPPDATA in each run's own folder), and each run checks `build/STOP_ROUND` before
it starts anything. It never touches the owner's saves, settings, cheat file or mods; the Seal edition's mod is
**copied** from the installed profile into `build/r58/chapsel/_sealmod/`. Nothing counts as done until the owner
says ok (F-037).

## How it works [high: read in memory, proven by the runs below]

1. **Base save.** It loads the nearest packed real-play clear save of the chapter's path that comes before the
   chapter (`bt/cq/rv-chN-clear`, never a `cheat-*` save). So the army is that path's own units at about that
   chapter's level. Paralogues use a mid-path save (X001-X006 from chapter 12 or earlier, X007-X022 from
   chapter 16 or earlier). `--base` overrides this choice. Title > Continue opens the castle's Preparations
   (frame 3590).
2. **Poke** (cheats.py's savestate helpers). The state is saved to a file and its FCRAM is changed. Each changed
   page is first checked equal to live memory. The state is then loaded back at the same frame:
   - the target's **world-map spot record**. These are 68-byte records in a row: +0 is the Chapter record pointer,
     +4 is a u16 state (0 locked / 1 open / 2 cleared). The robot sets the state to 1.
   - GameUserData (`*0x006DA248`) +0xC (the current chapter, = table + index x 28) and +0x2E (the route byte).
   A save only has spots for its own path. Birthright, for example, has A001-A028, X001-X014, AY01-03, E000 and
   M001-004. The Seal edition's own chapters (R/S/Y) have no spot in a Fates save. For those, chapsel's Seal game option **lends**
   the last locked spot of the row: its +0 pointer is set to the Seal chapter's record.
3. **Next Battle.** B, START (butler), DOWN x4, A. The target is now listed on the world map, but other open
   chapters stay listed too: setting their spot to 0 did not hide them. So the robot keeps a memory slot at the
   list and tries list positions (DOWN p times, A, Yes). A position counts only when GameUserData +0xC after Yes
   reads the target; any other position is undone by loading the slot. Then the chapter's own events run up to
   battle preparations (talk and movies skipped as robot/auto.py does).
4. **Driver.** It takes screenshots and memory reads at:
   - the spot list;
   - preparations;
   - Select Units (the unit list), with the selected unit's page on the bottom screen;
   - R (the Units table: class, level, HP);
   - Inventory and a unit's item menu (Items / Trade / Optimize / Store All);
   - Fight! (START) and the map. Memory: every unit's person id, class id, level, HP and place, by force;
   - the system menu > End, the enemy phase, and the next player phase once it has settled;
   - the system menu > Save > slot 1 > Yes. This writes a battle save (`extdata/.../Map0.bak`, which the base
     zips do not hold);
   - a **second fresh server** with the saved user folder. Continue loads the battle save. The robot checks the
     chapter id and that every unit (force, person, class, level, HP, x, y) equals what was there before the save.

Facts learned: the map's system menu opens on Units (Units, Guide, Options, Save, Auto, End). A press that lands
before an earlier one finishes is lost or lands in the wrong screen, so `press_wait` waits for the last press.
The castle's world-map list is not driven by the spot state alone: the current main chapter and the open
paralogues/invasions stay listed.

## Proof (2026-11-20, 8 runs, one lane at a time; results in build/r58/chapsel/summary.json, pictures in build/r58/chapsel/chapsel-contact.png)

| Chapter | Base | Started | Map: player / enemy / other | Enemy phase | Save + reload | Result |
|---|---|---|---|---|---|---|
| A015 Birthright 15 | bt-ch14-clear | prep, A015 | 12 / 15 / 0 (levels 3-20) | ran, enemies moved, back to turn 2 | Map0.bak, reload A015, units equal | **PASS** |
| B010 Conquest 10 | cq-ch9-clear | prep, B010 | 10 / 19 / 0 | ran, enemies moved | equal | **PASS** |
| B020 Conquest 20 (beyond the real Conquest saves) | cq-ch16-clear | prep, B020 (list position 1) | 14 / 30 / 0 | ran (no enemy moved on turn 1) | equal | **PASS** |
| C012 Revelation 12 | rv-ch11-clear | prep, C012 | 12 / 27 / 0 | ran, enemies moved | equal | **PASS** |
| C027 Revelation 27 | rv-ch26-clear | prep, C027 | 16 / 29 / 0 | ran (long, many fights) | equal | **PASS** |
| X007 child paralogue (Paralogue 7) | bt-ch16-clear | prep, X007 (list position 4) | 12 / 33 / 1 | ran, enemies moved | equal | **PASS** |
| Seal R003 (shows "Chapter 9") | rv-ch11-clear, route 2, mod copy | prep, R003 (lent spot M004) | 8 / 29 / 0 | ran, enemies moved | battle save written; **reload: both screens black, stuck on GameElapse for 7,200 frames** | **PART** |
| Seal S002 (shows "Chapter 13x") | rv-ch11-clear, route 2, mod copy | prep, S002 (lent spot M004) | 12 / 20 / 0 | ran, enemies moved | battle save written; **reload: the robot's answers loop at Continue > Battle Save** | **PART** |

No server log line with panic, guest fault or abort in any run. Each run took 20-80 s. The Seal runs show the mod's
maps, chapter names and objectives (contact sheet). Their army is the Fates Revelation army of the base save
(Corrin and others), not Seal's own cast. That is enough to load and play a map, but it is not a sane Seal roster.

## Not done / open

- **Seal reload** is not proven (table above). R003's black screens may be a real problem (loading a battle save
  of a Seal chapter made from a Fates save) or a robot-timing problem. It needs one look at the reload sequence
  before anyone calls it either. S002's loop is the robot's title answers (a fix to the title driver).
- **Seal roster.** A sane Seal army needs a save from Seal's own route (the mod's new game is the only one, at the
  prologue: round 52 `sof-ng`). Not built.
- **Prologue to chapter 6** are not selected by this tool. The prologue is the new game itself (routes `new-game` /
  `bt-prologue`). Chapters 1-5 run back to back without a castle, so the existing `bt-chN-clear` saves already start
  chapter N+1. `pick_base` points chapters 1-5 at bt-ch6-clear, but that save's first castle visit opens the butler
  (a forced first build), not the Preparations, so the run stops there (seen with A003).
- **Shop/armory**: no battle preparations reached had a shop entry. The item menu is shot instead. The castle's own
  shops (route `bt-castle-shop`) are outside the chapter.
- The units lost in the enemy phase are a test copy on Casual (A015 12 -> 11, C027 16 -> 9). Nothing is kept: it is
  not real play.

## Use

```bash
python tools/harness/chapsel.py --selftest                       # 26/26, invented memory (spots, lending, patch checks, base pick)
python tools/harness/chapsel.py plan A015 X007 B020              # which base save
python tools/harness/chapsel.py run A015                         # full drive; build/r58/chapsel/fates-A015/result.json + PNGs
# the Seal edition's chapter-select command: docs/seal/CHECK.md
python tools/harness/chapsel.py run B020 --steps prep            # stop after the preparations (for setting checks)
```

Hooks for the everything-on check: `Run.select()` leaves the server at the chapter's preparations, and `--steps
prep|start` stop early. FEF_RANDO_ANSWER / `rando-answer` must be given before the base save starts a new game.
Chapter select loads an existing save, so a randomizer check has to lay a randomized save (or apply the tables to
the loaded game). That is for the check track to decide.

## Round 58 check use (553 jobs, docs/RANDOMIZER.md section 12)

Chapter select drove every chapter of the four paths for the everything-on check, with the randomized run laid
into a copy of the clear save. Not reached (known gaps, not counted as passes):
- base save opens the butler or castle, not the Preparations: A007, A016, B007, B016, C007, C016, C017 (and A003
  above; `pick_base` should refuse these cleanly or fall back to the bt-chN-clear starts);
- map system menu not opened, even after one retry: A017, X009, X010, X012, X014, B019 (off run), Y002, Y003;
- direct start from a chapter-clear save stuck (ProcEffect): A002-A006 (covered at map start by recorded routes);
- not on the spot list: R011, R012, S007, S009.
Seal reload failed in every run, randomizer off too (units differ 16, black GameElapse 13, title loop 5).
Small fix still owed: `summary.json` leaves `enemy_phase` null on some passing runs where `enemy_moved` is set.

## Round 59: the unreached chapters reached (build/r59/robot/unreached-summary.json)

Fixes in chapsel.py (self-test 29/29). Each was proven by a full run on a frozen copy of the round-58 exe, with the
randomizer off. The strict-pair check driver and the new screens are in docs/tests/RCHECK.md.
- **Base save opens the butler or a castle event** (A007, A016, B007, B016, C007, C017): `pick_base` now starts them
  from their OWN clear save (the spot is cleared, so its state goes 2 -> 1; the list still decides it). C016:
  rv-ch15-clear stops at a castle event and rv-ch16-clear goes straight onto chapter 17's map, so C016 starts from
  rv-ch14-clear. A first-visit butler menu is also handled now (the poke happens at the menu, then Next Battle). But
  bt-ch6-clear refuses Next Battle there (the forced first build), so the own-save start is the one in use.
- **Map system menu not opened** (A017, A027, X009, X010, X012, X014, B019, Y002, Y003): the old free-tile walk moved
  relative to a cursor that had already moved, and it gave up in a tight group of units at the map's edge. The new
  walk tries the nearest free tiles in turn, reads the cursor back after each move and learns where the map edge is.
- **Not on the spot list** (R011, R012, S007, S009): these Seal chapters have route_mask (+0x14) = 0, so the list
  decided R001 instead, whatever spot was lent. The test copy's record gets the route's bit (0 -> 0x4, a cheat poke
  that is recorded). After that they are decided at list position 3. `lend` can also name a spot or pick an open one.
- **Direct starts A002-A006**: round 58 cut the title presses after 700:A, so the title's demo (ProcMovie, ProcEffect,
  ProcJobIntro) ran for 30,000 frames. The robot now sends the full title presses and START/A during the demo. Two
  more answers were added: a tutorial window in the enemy phase needs START (A002, A005), and chapter 6's route choice
  (EventDialog) is answered with A, the first item (Birthright, the same answer bt-ch6-castle gives).

| Chapters | Base | Result |
|---|---|---|
| A002, A003, A004, A005, A006 | bt-ch(N-1)-clear, direct start | PASS: map, enemy phase, battle save, reload equal |
| A007, B007, C007, A016, B016, C017 | the chapter's own clear save | PASS: preparations, map, enemy phase, save, reload equal |
| C016 | rv-ch14-clear | PASS |
| A017, A027, X009, X010, X012, X014, B019 | as before | PASS: the system menu opens; save and reload equal |
| R011, R012, S007, S009, Y002, Y003 (Seal) | rv-ch11-clear, route 2 | preparations, map and enemy phase reached. **Reload fails**, as it does in every Seal chapter with the randomizer off (the sealsave track's problem, not chapter select) |

No server log in these runs has a line with panic, guest fault or abort. All of these runs had the randomizer off.
The everything-on check still has to run them with the randomizer on, on the final exe.
