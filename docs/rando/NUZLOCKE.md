# Randomizer track: Nuzlocke (round 55, F-046; engine round E2 in round 60; gate fix in round 61)

**Round 61 (track nuz), in plain words.** The round-60 check found that Nuzlocke did nothing on Birthright. The
cause, read in the game's code: the core waited for a byte that it took for "a game is going on", but that byte is
the **map camera angle option** (0, 1 or 2; the game's default is 1, and every Birthright save of the robot has the
default). Now the core waits for the right thing: **the army exists** (the game empties every army list before each
title screen, so a loaded or new game is exactly "the army lists hold someone"). With that: Birthright passes like the
other three paths; a **battle save** loaded with two fallen people on the map comes back without them (they are moved
the moment the save's units are read, before the map draws them); a **brand-new Nuzlocke game** from the New Game
mode pick starts its own graveyard and the Casual pick is switched to Classic as soon as Corrin exists; a death is
written with its **turn and the person's name** ("Kaze: A007, turn 14"); Revelation's "Felicia drawn on the map now"
is explained and gone (section 8.3); and **PLAY RANDOMIZED accepts Nuzlocke** (in such a profile leave Randomizer off
at the New Game page: the profile's own Nuzlocke starts by itself). All proven headless on the track's test
boot-server (section 8). It is an exact patch for the assemble step (0025), not yet in the program you play. Nothing
counts as done until you say ok (F-037).


**Round 60 (engine round E2, track e2), in plain words.** Nuzlocke is now a live row on the in-game Randomizer page:
"Nuzlocke: a death stays dead after a reset (Classic is locked; a lost chapter can be restarted)". With it on, the game
core writes a fallen unit to a graveyard file beside the save in the very frame the unit falls, and every time a save
or a save state is loaded it puts anyone in that graveyard back among the fallen. Casual or Phoenix is switched back
to Classic (at the New Game and in My Castle), and the log says so. Corrin's death is never written (it ends the game,
so the chapter is replayed as usual). "Only one new ally per chapter" is shown grey at "all": Grok's pick
(docs/collab/NUZLOCKE_E2_GROK.md), because the game cannot tell a story join from a recruit. **Proven headless (robot,
own test boot-server, recorded route bt-ch7, no pokes):** Kaze falls in chapter 7 (the recording was made in Casual;
the core had switched the game to Classic), the graveyard names him at once; after a reset to a state from before
the chapter, and after a fresh program start that loads the save from the title, he is among the fallen, not in the
army, and chapter 7 starts without him. **Not yet:** the New Game start of a Nuzlocke game was not run in the robot
(it is in the unit tests only); a battle save loaded in the middle of a map with a fallen unit drawn on it waits
until that unit is off the map (not tested); a chapter whose lose rule names a unit other than Corrin would still
write that death; the Esc "This run" page does not show the graveyard yet; PLAY RANDOMIZED still refuses Nuzlocke.
The core change is not in the program you play: it is an exact plan for the assemble step (section 6). Nothing counts
as done until you say ok (F-037).

**For the owner.** Fates' Classic mode already makes a fallen unit stay gone. A Nuzlocke adds three things on top,
the way the Sacred Stones port does it. (1) **Classic only:** with Nuzlocke on, the New Game page will not start a
Casual or Phoenix game, and My Castle will not let the run switch to them. (2) **A death is final, whatever you
do:** it is written down beside the save the moment it happens. Resetting, loading the chapter save, a battle save,
an older save or a Zakuro save state never brings that person back. A death that ends the game (Corrin, or a unit
the chapter says must survive) is not written down: you go back as usual. (3) **Optional, "first recruit per
chapter":** only the first person who joins in each chapter may be fielded. The others still join, but they sit on
the bench for the whole run. A prisoner you scout in My Castle counts as the recruit of the chapter where you
captured them. Corrin, Azura and Kana are never benched. You also get a plain death and recruit log you can read.
**What is built now:** the rules, the log file and every decision the game must make, as a tested module
(`tools/randomizer/nuzlocke.py`, 21 tests pass). **What is not built:** none of this works in the game yet. Every
rule needs small hooks in the game core, which means an engine build, so it waits for a later engine round and your
OK then. "No Dragon Veins" was considered and left out: some maps cannot be cleared without a vein. Nothing counts
as done until you say ok (F-037).

Status 2026-11-20, round 55, host only: no game, robot or engine run; no other file changed. Facts are from the game's
code (`extracted/code.bin` disassembled with the user's binutils; names from `config/functions.csv`, the game's own
symbol map), docs/RANDOMIZER_INGAME.md (the in-game randomizer's save-side files), docs/TABLES.md, and the FE8 port's
PLAYING.md ("Randomizer", "The side file next to your save") and `port/reforged/reforged_rando_nuzlocke.c` (our sister
project: its rules were followed, its code was not needed). No public Fates tool has a Nuzlocke
(docs/collab/FATES_RANDO_RESEARCH_GROK.md). Tags: **[high]** read in the code, **[med]** good evidence, **[low]** a
guess the engine round must test.

## 1. The FE8 port's Nuzlocke, and what fits Fates

| FE8 port rule | Fates | Our decision |
|---|---|---|
| Deaths are final; Casual's retreat is off for the run | Classic already does this; Casual and Phoenix bring units back | Nuzlocke needs Classic: refused at the page, locked in My Castle (core) |
| A death is written at once in the side file next to the save | Fates saves can be reloaded (chapter saves, battle saves), Zakuro has save states | Same: graveyard file beside the save's run files (core writes, `Ledger` is the format) |
| Loading any save of the run kills the graveyard's units again | same need | Same (core, on every save read and state load) |
| A unit that joins again (older save) dies as it joins | same need | Same (core, at the join) |
| A game-ending death is not written | Corrin's death and a chapter's lose condition end the game | Same |
| Rewind and save states refused in a Nuzlocke | Fates has no rewind in Classic; Zakuro states exist | States allowed, but a loaded state is treated like a loaded save (the graveyard is re-applied), so a state cannot undo a death |
| (no recruit rule in the FE8 port) | most Fates joins are story joins, several per chapter | Optional "first recruit per chapter" (benched, not removed: the story still uses them) |
| (none) | Dragon Veins | **Not offered.** Some maps need a vein, a flier or a door path (research list; the randomizer already keeps a vein user per route). A no-vein rule could make a map unwinnable. An honour rule needs no code |
| Run told apart by seed + playthrough id | Fates' save has no id we know of | A random game id made when a Nuzlocke game starts (from the OS, never the game's dice), kept in the run state and the slot files |

## 2. Facts (from the game's code)

| Fact | Where | Tag |
|---|---|---|
| Every move of a unit between armies goes through `Unit::Transfer(unit, force, last)` 0x003D8C00, which calls `Unit::TransferImpl` 0x003D5308. 73 call sites | BL scan of code.bin | high |
| Force 4 is the dead: `TransferImpl` calls `unit::Enhance::Dead` 0x0041B3D8 only for force 4, and clears unit state bits first | disassembly 0x003D5424.. | high |
| A battle death is `Unit::Transfer(unit, 4, 1)` from `map::SequenceBattle::ProcSequence::DeadActionEnd` (calls at 0x00356B30 and 0x00356F2C) | disassembly | high |
| The unit's current army: `Unit +0xA4` (Force*), its index byte at `Force +0x8`. The unit's Person: `Unit +0x9C` (tools/harness markers) | disassembly; markers.py | high |
| Forces 0 (player), 1 (enemy), 2 (other) are the map; the player's "same force" masks are 0x19 (forces 0, 3, 4) and "with lost" 0x59 (0, 3, 4, 6): 3 = the player's units off the map, 4 = dead | `Force::GetMaskSameForce*` 0x0041C6C4.. | med (3, 6) |
| `TransferImpl` sends a unit with `Unit +0x8` bit 0x40000 to force 9 instead of 3+ (not to 4): such units are never recorded | disassembly 0x003D53C8 | high (meaning of the bit: low) |
| Lose check on a death: `map::Situation::GameEndCheckUnitDead` 0x003A65A4, called from `DeadSkipEscape` 0x00357F2C | BL scan | high (that it decides game over: med) |
| The game mode: `GameUserData::GetMode` 0x005096D0 reads `GameUserData +0x28`: bit 0x8 Phoenix -> 0, bit 0x4 Casual -> 1, else Classic 2. The script tests `DifficultyIsCasual` / `DifficultyIsPhoenix` read the same bits | disassembly | high |
| The mode is set by `GameUserData::SetMode` 0x001B3BB8 from `title::ProcTitle::JumpMyUnitEdit` (0x00441784, the New Game) and from My Castle's `castle::ChangeDifficultyMenu ... ConfirmYes::ACall` (0x0045F9EC) | BL scan | high |
| Joins (calls of `Unit::Transfer` into the player's army): script command `UnitTransferByIndex` 0x003AD280 (calls `Unit::SetPlayerBelong`), `event::JoinUniqueGuest::Create` 0x00423F8C, castle `JoinSeq::Join` 0x0046B034, `AfterBattleSequence ... JoinProccess` 0x0045E3CC, `MI_Join ... DI_Yes::ACall` 0x00489478, prison scout `ProcJail::JoinTargetPrisoner` 0x004EF108 | BL scan | high (that each is a join: med, by name) |
| Benching: the script command `UnitSetNeverSortie` 0x003AC6DC sets `Unit +0x8` bit 0x800, only for a unit in force 3 (it refuses force 9). The game's own "may not be deployed" bit | disassembly | high (that deployment honours it: med) |
| A save is read back by `UnitPool::Deserialize` 0x004F5BE8 (units re-joined to their forces with `Force::JoinLast`) | BL scan | high |
| Placements on the player's side (DisposUnit team 0) name the people a chapter puts on the map; whether a named one is a forced deploy is not traced | docs/TABLES.md DisposUnit | low |

## 3. What is built (table-only part and the reference for the core)

`tools/randomizer/nuzlocke.py`, the track's only module (track rules of round 55: no shared file edited).

```
plan_nuzlocke(tables, rng, opts) -> (edits, spoiler_lines)
    opts  {"nuzlocke": False|True, "recruits": "all"|"first"}  (DEFAULT_OPTS: off, all)
    edits always []  (no table cell serves any rule); off -> ([], []): old seeds stay byte-identical
    rng   not used: Nuzlocke draws nothing, so it never moves another track, and the rules do not depend on the seed
check_mode(mode, opts) -> None | reason       the New Game page: Classic only with Nuzlocke on
always_allowed(facts) -> [{pid, name, why}]   never benched: Corrin (both rows), Azura (the singer), Kana (both rows)
make_rules(facts, opts) -> dict | None        the run's rules file for the core (None when off)
ledger_path(data, game_id)                    <data>/rando/0004000000179800/nuzlocke/<game id>.json
Ledger.new_game / load / save                 the graveyard and recruit log (JSON, temp file + rename after every change)
Ledger.on_death(pid, chapter, turn, ends_game=, player_unit=, cause=)  -> written?
Ledger.on_join(pid, chapter, how, forced=)    -> "dead" | "bench" | "field"
Ledger.on_load(alive_pids)                    -> {"kill": [...], "bench": [...]}
Ledger.on_mode_change(mode)                   -> voided?
Ledger.text()                                 the readable death and recruit log
python tools/randomizer/nuzlocke.py rules [--recruits first] [--out FILE]
python tools/randomizer/nuzlocke.py log FILE
```

Decisions the core must follow (each has a test in `tests/test_rando_nuzlocke.py`):
- A death is written once, at once, for a player unit only; never for Corrin (`game_over_not_recorded`) or a death
  the lose check turns into a game over; nothing more is written in a voided run.
- First recruit per chapter: the first join in a chapter (a capture counts for the chapter it was made in) is
  fielded and takes the chapter's place; later joins in that chapter are benched for the run. Never benched:
  `always_allowed`. A person the chapter itself places on the map (`forced`) is fielded for that chapter and does not
  take the chapter's place; a benched person stays benched afterwards. The first decision for a person stands.
- A person in the graveyard who joins (an older save) is sent to force 4 at once. A benched person who dies is dead,
  not benched.
- Two games (two game ids) never share a graveyard; a new game with an id starts empty.
- A mode switch away from Classic voids the run (it should not be possible: the core greys the choices).

Tests: `python -m unittest tests.test_rando_nuzlocke` -> **21 tests, OK** (20 on made-up tables and temp files; 1 on
the user's own RomFS, read only: the five never-benched rows above, no edits). Nothing here starts the game.

## 4. What needs the game core later (an engine round, owner OK then)

None of the rules work in the game until these hooks exist. They follow the in-game randomizer's layout
(docs/RANDOMIZER_INGAME.md section 4: `fates_rando` in zakuro-core, its run folder and `slots/<save>.json`).

| # | Hook | Where in the game | What the core does |
|---|---|---|---|
| C1 | The page | New Game page (after the mode pick, ProcTitle+116) | A "Nuzlocke" row (off / on) and "Recruits" (all / first). With Nuzlocke on and a mode other than Classic, Start is refused with `check_mode`'s text. Start: make a game id, write `runs/<run>/nuzlocke.json` (`make_rules`) and a new graveyard (`Ledger.new_game`); the id goes into the active run and every `slots/<save>.json` |
| C2 | A death | entry of `Unit::Transfer` 0x003D8C00 with force argument 4, when the unit's current force (`[Unit+0xA4]+8`) is 0 or 3 | Person label from `Unit +0x9C`; chapter from `GameUserData::GetChapterPrefix` 0x005095D8; turn from the map state. `ends_game` = the lose check (`GameEndCheckUnitDead` result in `DeadSkipEscape`, or simpler: the death is written only after the death sequence has ended without a game over, before the game can write any save). Write the graveyard at once |
| C3 | A join | entry of `Unit::Transfer` with force 0 or 3 when the current force is not 0/3/4, from the join callers in section 2 (`how`: story for the script command and guest event, castle, capture for `ProcJail::JoinTargetPrisoner`) | `on_join`: "dead" -> transfer to 4 instead; "bench" -> after the transfer, set `Unit +0x8` bit 0x800 as `UnitSetNeverSortie` does (force 3 only; a unit put straight into force 0 is benched when it next goes to force 3) |
| C4 | A load | after `UnitPool::Deserialize` 0x004F5BE8 (the save read the in-game randomizer already hooks, `save_opened_for_read`), and after a Zakuro state load | `on_load` with the people in forces 0 and 3: each "kill" -> `Unit::Transfer(unit, 4, 1)` (carrying/paired links undone first, as the game's death does); each "bench" -> bit 0x800 again |
| C5 | Mode lock | My Castle `castle::ChangeDifficultyMenu` (`ModeItem::BuildAttribute` 0x004601B0 greys a choice; `ConfirmYes::ACall` 0x0045F9C4 calls `SetMode`) | Grey Casual / Phoenix while a Nuzlocke run is active; if `SetMode` is reached with another mode anyway, `on_mode_change` (voided) |
| C6 | Esc "This run" | the existing Randomizer page's "This run" | Show Nuzlocke, recruits, the graveyard and the benched list (`Ledger.text`) |

Tests the engine round needs (robot, headless, recorded routes only, own test game): a battle death on a recorded
route is written once; Restart / battle save / older save / state load bring the unit back dead; Corrin's death is not
written; a second join in a chapter is benched and cannot be deployed; with Nuzlocke off the program is byte-identical
in memory and saves (as T4 of round 51). Open [low] points it must settle: whether deployment honours bit 0x800 for
every chapter (including the forced story deploys), whether killing a person again at load breaks a later scene that
expects them (Fates' story handles dead units, since Classic allows it), and the meaning of forces 3, 6 and 9.

## 5. Cost

Module and tests: done this round. Core hooks C1-C6: about 1 engine round (Rust in zakuro-core `fates_rando` + the
page rows) plus 1 robot round for the tests above [low]. Nothing in the game changes until then.

## 6. Engine round E2 (round 60): what was built, and the plan for the assemble step

Track e2 built the core part in its own engine copy (`build/r60/e2/zakuro`, from `engine/zakuro` fe14 HEAD 7deeb7c =
patches 0001-0021) and proved it on a boot-server built from that copy. Nothing in `engine/zakuro`, `patches/zakuro` or
`play/game` was touched.

**Core change** (`build/r60/e2/E2_core.diff`, 4 files, +979 -4; becomes the next free patch,
"core: Fire Emblem Fates randomizer: Nuzlocke (graveyard, fallen kept fallen, Classic locked)"):
- new `crates/zakuro-core/src/fates_nuzlocke.rs`: the graveyard (`<data>/rando/<title>/nuzlocke/<game id>.json`, the
  Python `Ledger` format: `nuzlocke.py log FILE` prints it), the per-frame work (deaths in force 4 written at once;
  graveyard people in force 0/3 moved to force 4 the way `Unit::TransferImpl(unit, 4, 1)` does it, only when the unit
  has no map actor, Unit +0xB8 == 0; GameUserData +0x28 bits 0x4/0x8 cleared), people keyed by their labels' cp932
  bytes (`label_key`, Python `pid_key`), 6 unit tests;
- `fates_rando.rs`: `slot_written_nuz` / `slot_nuz` (the slot side file also names the game id; without one the file
  is byte-identical to before);
- `fates_rando_session.rs`: `Session.nuz`; a new game whose run folder holds `nuzlocke.json` starts a Nuzlocke game
  (new id from the OS); a save read or a state names its game; a state of the same run keeps the game; the state
  sidecar names the id; `after_frame` runs the Nuzlocke frame only while a Nuzlocke game is active and a game is going
  on (GameConfigData +0xB != 1); the run keeps `nuzlocke.json` from the make's work folder;
- `lib.rs`: `pub mod fates_nuzlocke`.
With Nuzlocke off nothing new reads or writes memory or files (no `nuzlocke.json` -> `Session.nuz` stays None).

**Python change** (already in the tree): `ingame.py` (the Nuzlocke row live with `--nuzlocke`, Grok's label;
"recruits" grey at "all", no flag), `rando.py` (`--patch-out` takes Nuzlocke and writes `nuzlocke.json` beside the
patch, removes a stale one when off; refuses only `--recruits first`), `nuzlocke.py` (`pid_key`, `key_label`, the
`*_keys` lists in the rules). Tests: `tests/test_rando_ingame.py` (updated, 2 new), `tests/test_rando_nuzlocke.py`
(+1).

**Assembled (round 60 assemble step, 2026-11-21):** the diff was merged on top of 0022/0023 (3-way merge, no conflicts; the changed lines are exactly E2_core.diff's) and is patch `0024-core-Fire-Emblem-Fates-randomizer-Nuzlocke-graveyard-f.patch`; `engine.py apply` put 0001-0024 on fe14; `cargo test -p zakuro-core -p zakuro-fs --lib` 194 + 23 passed; play/game and the boot-server rebuilt (build/r60/FINAL_SHA.txt). `nuzproof.py` re-run on the final boot-server (build/r60/assemble/nuz/nuzproof.json): the same six steps as track e2's proof (Classic kept, Kaze written at A007, still fallen after the state load, the fresh start and at chapter 7), only the times and folders differ. Randomizer off: memory-identical to the pre-r60 exe at boot and frames 3000/4600/5200 (build/r60/assemble/smoke).

**Assemble steps:** (1) back up `play/game` exe, build-record and boot-server to `build/backup/*.2026-11-21-pre-r60`;
(2) `git apply build/r60/e2/E2_core.diff` in `engine/zakuro` on top of the round-60 sealfix commits, commit, and write
it out as the next free `patches/zakuro/NNNN-*.patch`; (3) `cargo test -p zakuro-core --lib fates_` (41 + sealfix's
tests); (4) `engine.py port` and `build.py --server`; (5) re-run `build/r60/e2/nuzproof.py` with the new boot-server
(set EXE) and the randomizer-off memory-identity check; (6) check_all rows.

**Proof** (`build/r60/e2/proof/nuzproof.json`, boot-server sha256 7cc6fdf4..., 130 s, 2 sequential sessions, exit 0,
no process left): castle loaded, Casual switched to Classic, Kaze in force 3; the graveyard names Kaze
(`PID_スズカゼ`, A007) by frame 49800 and he is in force 4; the state "castle" loaded again: Kaze back in force 4
(force 3 has 5, not 6); a new program start loading the save from the title: Kaze in force 4; chapter 7 starts
(frame 17200) with Kaze still in force 4. The test program `build/r60/e2/target-port/release/fe-fates.exe`
(sha256 7e0b5a43...) was built from the same copy but not run.

## 7. Round 60 check on the final build (2026-11-21)

One all-on seed per path with Nuzlocke, two army people put in the graveyard (build/r60/check/nuz/).
- Castle save loaded from the title (nuzpath.json): Conquest, Revelation and Seal pass (both people go to force 4 at
  load, Casual is switched to Classic). **Birthright fails** (save bt-ch9-clear): the core never acts, because the
  game byte it waits on (GameConfigData +0xB) stays 1 up to frame 8000 while the game is loaded in Casual with 15 army
  units (nuzprobe.json). The fallen stay in force 3 and Casual is kept. This breaks "a lost unit is never kept".
- Chapter start from chapter select (jobs nz-*): Conquest and Seal move the fallen off the map. Revelation keeps them
  off the map, but the log says twice that Felicia is "drawn on the map now" (not explained). **Birthright A010: both
  fallen stay on the map** for preparations, the map, the enemy phase and turn 2 (the core logs "drawn on the map
  now; moved as soon as it can be" and it never resolves). All four jobs stop at "Save item not found", which is
  expected: Classic has no battle save.
- Graveyard entries carry `turn: 0` and `name: ""` (the core writes only the person key), so `nuzlocke.py log` and the
  later Esc page show no turn and no display name.
- Fix needed (engine, next round, owner OK for an engine build): the 0024 gate must not rely on +0xB alone, and a
  fallen unit already drawn on the map must be removed before preparations; then rebuild and re-run every Nuzlocke job
  and the randomizer-off memory-identity check.

## 8. Round 61 (track nuz): the gate, the battle save, the new game, turn and name, PLAY RANDOMIZED

Engine copy `build/r61/nuz/zakuro` (a clone of `engine/zakuro` fe14 2a89146 = patches 0001-0024; nothing in
`engine/zakuro`, `patches/zakuro` or `play/game` touched). Patch for the assemble step:
`build/r61/nuz/patch/0025-core-Fire-Emblem-Fates-randomizer-Nuzlocke-gate-is-t.patch` (2 files, +326 -22,
`git apply --check` clean on engine/zakuro fe14). Test boot-server `build/r61/nuz/bin/boot-server.exe` (sha256
49ed0351...; built from the same tree, crate = tools/harness/patches/zakuro-server as tracked, own target folder).
`cargo test -p zakuro-core --lib`: 197 passed (fates_: 45).

### 8.1 Facts (from the game's code) [high]
| Fact | Where |
|---|---|
| GameConfigData +0xB is the map camera angle option (0/1/2): `CameraBase::GetGameConfigAngle` 0x003E06E0 and `SetGameConfigAngle` 0x003E07CC are its only readers; `GameConfigData::Reset` 0x001D06DC sets it to 1 | scan of every `ldrb/strb [x, #11]` after a load of `*0x006DA0F8` |
| `MainSequence ProcSequence::GameReset` 0x001B6CBC calls `UnitPool::Reset` 0x004F6198: forces 0-9 made empty, all 250 units joined to force 9 (the free list) | disassembly |
| `map::Situation` is `*0x006D7ED0`: +0x8 the phase, +0xC the turn (u16; `TurnEnd` 0x003A6850 counts it, up to 999) | disassembly |
| `map::Dispos::Data::CreateSortie` (0x0039E0xx) looks a placement's person up in force 3 and then in **force 4**, and takes them from there | disassembly |
| `Unit::TransferImpl` from a map force deletes the unit's map actor (+0xB8, its virtual destructor) itself | disassembly 0x003D537C |

### 8.2 The change (patch 0025)
- `fates_nuzlocke::in_game`: the unit pool holds a player army (force 0, 3 or 4 has a unit), not the camera byte.
- `Nuz::sweep` at every system call (`before_svc`): a graveyard person in force 0 or 3 with no map actor goes to force
  4. For 1200 frames after a save, state, new game or chapter start every army unit is checked; at other times only
  the units of fallen people seen at the last frame (one force byte read each).
- A death is written only for a person seen alive in the army in this game, with the turn and the name (the rules'
  new `names` pairs, `nuzlocke.py make_rules`); the readable log shows "Kaze: A007, turn 14 (battle)".
- A New Game mode pick closes the Nuzlocke game of the game before.
- PLAY RANDOMIZED: `tools/play/rando.py new --nuzlocke on` writes the run `profile-nuzlocke` (a patch of no cells +
  the rules) into the profile's own data folder; the core lays it when the New Game page answers Randomizer off and
  starts a Nuzlocke game. "First recruit per chapter" stays refused (Grok's pick, round 60).
- Not changed (open, reported): the in-game randomizer's save-read gate (`at_title`) and mode-pick watch
  (`NewGameWatch`) also read the camera byte. With the default angle, a save menu inside a game could re-lay another
  slot's run, and a change of the +4 option word inside a game could look like a mode pick. Both need a robot test
  that returns to the title, which this round could not do without new play.

### 8.3 Revelation's "Felicia drawn on the map now" (round 60), explained
At a chapter start `CreateSortie` takes a person the chapter's player-side placement names out of force 4 when they
are not in force 3, so a fallen Felicia was put back in the army and drawn; the round-60 core waited for her map
actor to go (the preparations screen re-made it a frame later) and then moved her. Now the move happens at the next
system call, before she is drawn: the re-run has no such line (cq B010 and rv C012 log the move twice at the chapter
start; Birthright A010 and Seal S002 none).

### 8.4 Proofs (headless, test boot-server 49ed0351, capture library 610f791d, recorded routes and saves only)
| Job | Result | File |
|---|---|---|
| Castle save from the title, two army people in the graveyard: bt-ch9-clear (camera byte 1), cq-ch9-clear, rv-ch11-clear, Seal rv-ch11-clear | **pass x4**: both in force 4 at frames 4300 to 8000, Casual -> Classic (moved at a system call during the load) | build/r61/nuz/proof/path.json |
| Battle save of opt-ch8-set (Birthright A008 map, route opt-ch8-reload's presses). Control with an empty graveyard: Rinkah and Kaze drawn on the map. With those two in the graveyard | **pass**: never in force 0/3 at frames 1900-3280, in force 4; the map holds 9 player units instead of 11 | proof/battle.json |
| New game: new-game-empty + bt-prologue presses, the mode pick answered with a Nuzlocke run | **pass**: Nuzlocke game started at the pick (graveyard file), Casual -> Classic once Corrin is in the army (between frames 6000 and 9000), the Prologue map at 14000 in Classic | proof/newgame.json |
| PLAY RANDOMIZED profile (rando.py's profile run in the data folder), mode pick answered off | **pass**: "Nuzlocke game ... started for this PLAY RANDOMIZED profile", Classic | proof/profile.json |
| bt-ch7 recorded route (Kaze falls) | **pass**: graveyard entry Kaze, A007, turn 14; still fallen after a state load, a new program start and at chapter 7 | proof/death.json, proof/death-graveyard |
| Chapter start from chapter select (the round-60 jobs; copy `build/r61/nuz/nzr61.py`): bt A010, cq B010, rv C012, Seal S002 | the fallen are on no preparation list and no map on any path; every job stops at "Save item not found" as in round 60 (Classic has no battle save). Real enemy-phase deaths are now written (rv C012: Azura, turn 1; Seal S002: Azura, Subaki, a Fighter, turn 1; the robot's units stand still; 12 -> 11 and 12 -> 9 units, the same counts as round 60, whose camera-byte gate missed them) | build/r61/nuz/jobs/*/result.json |
| Randomizer off: the test boot-server vs the round-60 final boot-server, bt-ch7 to frames 4300/9000/17200/30000 | **guest memory identical** at all four (state metadata differs only by the run folder's name) | proof/offsame.json |

Tests: `python -m unittest tests.test_rando_nuzlocke` (+1: the rules name the army), `tests.test_rando_integrate -k
nuzlocke` (PLAY RANDOMIZED accepts Nuzlocke and writes the profile run). Assemble steps: back up as the round says;
apply 0025 on fe14 in engine/zakuro and copy it to `patches/zakuro/`; cargo tests; `engine.py port` and `build.py
--server`; re-run `build/r61/nuz/nuz61.py` (set `NUZ_EXE`) and `nzr61.py` (the final exe in its bin/ with SHA.json)
and the randomizer-off identity (`offsame.py`, its exe pair edited).

### 8.5 Round 61 assemble, check and review (final build ff85e43d / 4d0b60c9 / 610f791d)
- Patch 0025 is in patches/zakuro and in play/game since the round-61 assemble.
- Final boot-server, re-run of the track's proof script (build/r61/check/nuz): the castle loads on all 4 paths
  (bt-ch9-clear with camera byte 1 included), Kaze's death (A007, turn 14), the battle save, the new game from the mode
  pick and the PLAY RANDOMIZED profile all pass. Chapter-select jobs bt A010, cq B010, rv C012, Seal S002 PASS
  (graveyard loaded, fallen in no army list and not on the map, Classic, no log faults); the reviewer opened bt A010
  (Felicia and Saizo absent from the prep list, in force 4). Verdicts: build/r61/check/nz-verdicts.json.
- Correction (review): proof/offsame.json records `"same": false`. Only its metadata section differs (run folder
  name); fcram, vram, dsp_ram, axi_wram and the memory digest are identical at all four frames. The assemble step's
  smoke (randomizer off, new exe vs pre-r61 exe, frames 0/3000/4600/5200/end: memory hashes identical) replaces it.
- Correction (review): "never drawn" in proof/battle.json is read from force membership only (no map-actor check
  or screenshot in that proof); the A010 chapter-select job's map readback and unit-list picture back it.
- Open (latent bug, not Nuzlocke only): `fates_rando_session::at_title` (the save-read gate) and `NewGameWatch` still
  read GameConfigData +0xB, the camera angle option. With the default angle, a save menu inside a game could lay another
  slot's run, and a change on the in-game Options screen could be taken for a New Game pick. Needs its own fix and a
  robot test that returns to the title.
- Open: the graveyard turn (map::Situation +0xC) is not yet compared with the game's own turn display (medium
  confidence). A fallen unit already drawn in a Zakuro save state (not a game save) waits until its map actor goes.
  Seal graveyard names stay empty until the Seal run is made again (new makes carry names).
- Warning for later checks: real enemy-phase deaths are written now (rv C012 Azura, Seal S002 three units, turn 1),
  so a Nuzlocke re-check that plays past the first enemy phase loses units for real.
