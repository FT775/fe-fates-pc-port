# Harness on Fates: solved problems

One short entry per problem found and fixed, so the knowledge stays after the scratch files
(runs, dumps, sheets) are deleted. Newest at the end. Awakening's list: its docs/harness/SOLVED.md.

## 2026-11-11 (first headless runs, ROBOT_PLAN rows 0-1)

- **No boot.exe in this repo.** headless.py runs engine/target/zakuro-test/release/examples/boot.exe,
  which only the Awakening repo had. Fix: `tools/harness/build.py --boot` builds the example from
  this repo's Zakuro (pin + the same 5 patches; `engine.py status` must pass first), pinned toolchain,
  `--locked`. 105 s.
- **The hardware rasterizer writes the owner's pipeline cache.** zakuro-gpu keeps one file per title in
  `%LOCALAPPDATA%\zakuro\pipelines\` (raster/hardware.rs pipeline_cache), and the Awakening harness
  wrote there. Fix: boot.exe gets `LOCALAPPDATA=build/harness/localappdata`. Checked: the real
  `pipelines\0004000000179800.bin` kept its size and mtime over all runs; the harness's own grew to 4.6 MB.
- **An update .cia beside the ROM was not checked by headless runs.** boot.exe loads an update only via
  ZAKURO_UPDATE (headless drops every inherited ZAKURO_ variable), but the plan wants it refused.
  Fix: `headless.refuse_cias` uses PLAY's TMD reader (tools/play/play.py classify_cias): an update or
  unreadable .cia stops the run, this game's DLC is a note. Proved on a hard link of the ROM with a
  synthetic update .cia; self-test covers update, DLC, unreadable.
- **The copied Awakening title timings did not fit.** From an empty save Fates asks four questions
  (save initialization x2, SD extra data x2) before the intro movie; START skips the movie. Found
  with shots every 150-300 frames, one input added per try.
- **No screen markers for Fates in Zakuro.** Patch 0001's markers run only for Awakening. Fix: memory
  reads (tools/harness/markers.py): the process tree from 0x00752B48, MainSequence::GetCurrent from
  0x006D88D4, classes from the vtables' destructor names. The first try dumped only the heap and got
  `vtable_XXXXXXXX` for every class: vtables are in read-only data, now read from extracted/code.bin.
- **Objects are not in the 0x08000000 heap.** It is only 1.5 MiB mapped; thread stacks and objects
  point at 0x31xxxxxx. The marker dump is the linear heap 0x30000000 + 0x037C5000 (mapped part).
- **h4a crashed on a route with no readable call.** capture.c starts on the first override call, so the
  `title` route left no summary.tsv. Fix: h4a says "no readable function was called" and stops (exit 1).
- **The library went STALE minutes after the build.** Another workflow edits src/readable/. Fix: build
  and run h4a back to back.

## 2026-11-11 (stage B: one Birthright campaign, Prologue to My Castle)

- **Finding a 47,000-frame route from frame 0 was too slow.** Fix: savestate look-ahead (ZAKURO_LOAD from a
  scratch state under build/harness/robot/states/, a few hundred frames per try), then the stitched input
  replayed from frame 0. Unlike Awakening (its route ch1-hubba), the Fates replays reached every screen at
  the same frames as the chained look-ahead (all marker checkpoints met on the first from-zero run of each
  piece). Savestates never enter a route.
- **Every later piece replayed the whole campaign.** Fix: each chapter ends at the save menu; the route
  saves to slot 1 and `headless.py --pack` turns the run's scratch save folder into bt-chN-clear.zip; the
  next route names it (`"save"` in routes.json, new) and starts with Title > Continue. The zip holds
  savedata only, so the two SD extra-data prompts come back on every load (300:A, 700:A).
- **Screens that need no decision cost one probe each.** Fix: an autopilot (tools/harness/robot/auto.py)
  answers by the current marker class: talk START, then A if START did not move it on (START skips a
  whole scene; inside a battle it pauses the battle instead, so there only A); tutorials and movies START;
  stage complete A; the chapter objective screen (map ProcSequence with ProcScene) A. It stops on the
  player phase, menus and yes/no dialogs.
- **A battle hung for 40 segments.** Cause: a START sent during a battle talk paused the battle (the
  bottom screen shows the pause button). Fix: never START under `BattleSeq`; after 8 segments of
  `ProcBattleInfo` the autopilot sends one START to resume.
- **Moves to unreachable tiles broke the rest of the input.** The game's move ranges are not computed
  here (terrain costs per class were not read). Fix: the action helper (act.py) tries destination
  candidates in order: after each A it checks that the command menu opened, else it moves on to the next.
- **Defaults that are traps.** Every yes/no dialog defaults to No (avatar name, save slot, route
  confirmation, seize): LEFT then A. The SpotPass question defaults to No and is answered No. The avatar
  menus jump to OK with START. "First command" is Items, not Dragon Vein, when the unit is not on a vein.
  A on an acted unit opens the system menu, whose last item ends the turn (UP, A): no need to make every
  unit wait.
- **Pair Up is not offered in chapter 2** (moving onto an ally does nothing there, acted or not). It is
  a command from chapter 3 on (Pair Up beside an ally on the unit menu).
- **The '5' tiles of chapter 3 were not walls.** The terrain names (TID_ labels of the chapter's
  TerrainTile records, found in the heap) showed void, void/bridge (changes to bridge) and bridge: the
  path to the boss is the dragon vein's bridge.
- **"Paired units" counted the enemy.** Chapter 3 starts with an enemy pair; the checkpoint counts
  `paired_player` (force 0) only.
- **The first castle visit locks the butler menu** until a building is placed (forced tutorial: Build >
  Dawn Armory > a 2x2 spot that shows blue, Yes). The castle has no facility warp: walk with the D-pad
  (held as consecutive 6-frame presses); fences block, the prompt "A <building>" appears at the door.
  Preparations (X in the castle) has Inventory (convoy) and Support.

## 2026-11-12 (round 3: speed, shop, chapter 7, a support conversation)

- **6-18 s of Python after every run.** cProfile: `lz4_block` spent most of 6 s per 141 MB state in 49
  million `min()` calls: an overlapping match (offset 1: a run of zero bytes) was copied one byte per loop.
  Fix (headless.py): repeat the period, skip 255 length bytes with one regex match, keep len(out) by hand,
  decode once for the digest and keep_meta. 6.0 s -> 0.77 s, byte-identical sections; title, new-game and
  bt-ch2 keep their memory hashes.
- **parallel.py ran bt-* routes from the empty save.** Its `--save` default (new-game-empty) replaced the
  route's own `"save"`, so `determinism --route bt-ch2` ended at `893128f2...` instead of `059736d3...`
  (all three copies agreed, so the verdict looked fine). Fix: no default; a route's save, else the empty one.
  Test `test_route_save_is_used_without_save_arg`.
- **Two h4a started together: one crashed in the freshness check.** build.freshness staged into one shared
  build/harness/fresh_check; the other process deleted files under it (FileNotFoundError). Fix: a folder
  per process, removed after.
- **Castle placement colours.** Red or pink footprint: refused (A does nothing). Blue: accepted (yes/no).
  The armory's spot from bt-ch6-castle overlaps a building for the Rod Shop; 10 tiles right is blue.
- **Support points are not live.** Battles side by side add nothing to Unit+0x11C during the map; the
  chapter end adds them (Corrin-Sakura 1 -> 2 after chapter 7). A ready conversation sits one point below
  C and the TALK! menu shows it; watching it adds the point.
- **The end-turn helper selected a unit.** A on an unacted unit opens its move range, not the system
  menu: et.sh moves the cursor to an empty tile first (read the cursor from a look; it stays where the last
  action ended).
- **Terrain codes are per chapter.** Chapter 8's code 3 costs 2 (forest-like); chapter 7's code 3 was floor.
  act.py's candidate list (try the next tile when the menu does not open) covers it; read costs if needed.
- **stance_guard_bonus_edit never ran with Corrin leading.** Unit::GetDoubleCapability calls
  PersonEnhanceDouble::GetEdit only when the support unit has avatar edit data (Unit+0xB0): Corrin must be
  the support. Pair, then Switch (fifth item of a paired unit's menu after Talk) made it run (23 records).
- **h4a MISMATCH in other work.** A library rebuilt while another workflow had 21 uncommitted formula
  overrides in targets.csv includes them; two of them mismatch on calls (ROBOT.md 4). Note which rows are
  committed before reading a report.

Round 5 (2026-11-13):

- **The look-ahead lock deadlocked once.** robot/budget.py first held probe.lock for the whole process; act.py
  runs a segment itself and then starts auto.py as a child, which waited on its own parent's lock. Now the lock is
  held only around one headless.run (`with budget.run_slot()`). Found after 10 idle minutes; the two processes were
  stopped through the shell that started them.
- **walk.sh logs only its own presses.** It runs `auto.py DST SRC`, which appends to DST.inputs without copying
  SRC's history (br.sh copies it). A chain built by walks must be stitched from each step's .inputs, and a failed
  walk retried into the same DST leaves its inputs there (drop the earlier line). bt-ch9-ore was stitched this way
  and replayed from frame 0 to the same screens.
- **act.py pairs up on an occupied candidate.** A candidate tile holding an ally gives the Pair Up preview (or a
  pair's System menu), not a move; list only empty tiles, and remember tiles taken earlier in the same turn.
- **A staff user's first command opens the item panel.** Sakura/Asama/Felicia: `attack` lands on
  ItemMenuPanel; then A (the staff), A (the target).
- **The boss on a throne heals about 20% each turn** (Zola 29 -> 35): chip damage is undone; it needs one player
  phase. Shuriken lower the target's defence for later hits (game rule, not measured here: Saizo's shuriken took 10 after Kaze's hit, Corrin's Dragonstone 6 without one, 10 after).
- **Detail view by touch.** The unit panel's Atk/Hit/Crit/Avo page (ViewerUnitStatus::DrawBattleAbilities) has no
  button; Zakuro's input accepts `FRAME:@XxY` (a touch on the bottom screen): `@305x15` is the panel's arrow,
  `@22x222` the book (stat strip), `@58x30` the magnifier (class intro).
- **Castle A opened Preparations.** Pressing A beside the castle's "!" units twice opened sortie TopMenu instead
  of a talk; facing was not controlled. Unsolved; the lottery was used instead.
- **Rolls depend on the order of actions.** The same burst in another order dealt 22 instead of 31 (a miss); the
  runs are still deterministic, so trying orders from a kept state is cheap.
- **SetPriorityClass on the pseudo-handle failed silently.** ctypes passed GetCurrentProcess()'s -1 as a 32-bit
  int; Windows refused it and the process stayed at normal priority. Fixed in robot/budget.py (restype c_void_p,
  argtypes, a message when it fails); `parallel.priority_of` now reads 0x4000.
- **act.py wrote screenshots into tools/harness/robot/** (cmd.png, fore.png: game pictures in a tracked folder,
  never added to git). They now go to build/harness/robot/; the two stray files were deleted.
