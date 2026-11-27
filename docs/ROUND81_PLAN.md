# Round 81: the counted header (your game settings for every New Game)

**In one line:** your "ok keep going" started this round and its new writer group; it is not a push OK. The plain-words part is below the next paragraph.

Written in round 81's desk part (2026-11-25, 21:04 to 21:27 EST, read only) from the three desk traces:
build/r81/options/OPTIONS_TRACE.md, build/r81/hook/HOOK_TRACE.md, build/r81/home/HOME_DESIGN.md, the one Grok
consult (docs/collab/ROUND81_OPTIONS_GROK.md) and the roadmap row (build/roadmap/NEXT_STRETCH_2026-11-24.md item 5,
docs/NEXT_STRETCH.md, docs/ROADMAP.md row 81). Nothing in this file has been built. Round 81 runs on the owner's
standing OK (F-059 (3); the owner's pick F-057 #5). Its **new writer group** (F-038, F-057's second yes asked at
this round) was answered by the owner's "ok keep going" to the question "Start round 81 with its new writer group?"
after round 80's report. That line is not an ok of round 80's ok list (F-037) and not a push OK.

Every time below is **counted** (measured in a real round, the source is named) or **estimate** (never measured,
written on the slow side), as F-027 asks. GB = the Windows count (1 GB = 1,024 MB), as in round 80's plan.

## In plain words

**What the desk part found:**

- **The game puts its own Options back to its defaults before every title screen.** So every New Game starts from
  the game's defaults, and that is why your choices are lost each time. Each save keeps its own copy of the
  Options, and loading a save brings that copy back.
- **There is exactly one moment where a New Game begins:** right after you pick Casual, Classic or Phoenix. Nothing
  else runs that step: not Continue, not a battle save, not the branch-of-fate start, not a chapter retry, not the
  versus or online parts.
- **So the port can set your choices once, at that moment,** as if you had changed them on the game's Options
  screen before the Prologue. No "save guard" is needed (the old design needed one because it wrote at every load).

**What you will see after round 81** (nothing counts until you say ok, F-037):

1. **Press Esc while playing Fates.** Under round 80's Helpers heading (True hit and its help line) there is a new
   line, **New Game defaults** (Grok's name), closed at first. Closed, it says "game's choice" or, for example,
   "2 set". Open, it has four rows, each starting on **Game's choice**:
   - **Battle animations:** Game's choice / Off / On. Help: "Off plays fights on the map. Supports and dances
     follow this too."
   - **Map speed:** Game's choice / Normal / Fast / Fast while A is held.
   - **Enemy turn skip:** Game's choice / Off / Move / All (the game's own line 6, which round 80 measured).
   - **HP bars:** Game's choice / Off / On.
   - A note: "Used when you start a New Game. A game already going keeps its own settings; change those on the
     game's Options screen." And: anything that changes how long things take can make later enemy moves differ;
     hits, damage and the battle dice stay the same.
2. **Start a New Game.** The game's own Options screen already shows your choices at the Prologue.

**Defaults:** Game's choice on every row. Then the port does nothing at all: it does not even watch, and the game
is exactly round 80's game (the robot proves it with a memory compare).

**What never changes:**

- **No roll is changed by the port.** It writes four Options bytes once and calls no game code. (The game's own
  options that change timing can make later enemy moves differ, as round 80 measured; that is the game's behaviour
  with that option, and the note says so.)
- **Written once per New Game only.** Never at Continue, a battle save, a chapter retry, a reset, or later in that
  game. Changing a row in Esc mid-game does nothing until your next New Game.
- **The game's own Options screen still works afterwards.** It shows the written values, you can change any line,
  and your saves keep what you pick there.
- **Saves you already have are never changed.**
- **The versus copy of the settings is never written**, and nor is any other part of the game's data.
- **Danger zone is left out** (nobody has seen what its three values change; Grok agrees). Your randomizer seed and
  share code never change: these rows are not randomizer rows. Nuzlocke: allowed, not greyed.
- One choice for Fire Emblem Fates and Seal of Flames (same game underneath).

**How long:** about **10 h 00** for the engine part (estimate: a sum of parts; builds, checks and install counted
from rounds 74 and 80), plus the desk part already done (about 23 min, counted with date). **10 h 23 in all, under the
roadmap's 11-13 h (estimate), so the plan is not over its count** and your standing OK covers it.

**Disk:** D: has **78.2 GB free** (counted: df 80,108 MB at 21:22). Round 81 needs about 5.8 GB, at worst 17.7 GB
(estimate from counted rounds 74 and 80). The engine part starts only if D: still has at least 47.7 GB free then.

**What needs your OK:** nothing new. Your calls (end of this page) all have safe defaults; silence means the
default. Still held for you: every push and the public snapshot.

## Times the engine steps really took (counted)

| Step | Round 74 (REPORT_2027-01-20, ROUND80_PLAN's counted table and build/r74/build/stage_b1_b3.log) | Round 80 (REPORT_2027-01-26, F-065) |
|---|---|---|
| Plan for the whole engine part | 13 h 10 | 14 h 30 |
| Whole engine part, real | about 2 h 07 (04:55-07:02) | about 2 h 28 (18:32-21:00) |
| Code and gate | tracks 27 / 30 / 37 min side by side, gate 10 min | sitting 1: about 48 min (plan 7 h 25) |
| Builds (exe + boot-server, staged) | 133.8 s stage log (exe 88 s, boot-server 70 s) | B1 151 s, B2 159 s |
| Repair build | used: repair and re-proof 14 min | used: B2 (one) |
| Cargo tests | 57 s | 242 + 23 + 130 tests in the reused targets |
| Proofs, builds, checks, install | P1 38, P2 17, P3 about 25, P4 about 2 min | sitting 2: about 1 h 32 (plan 7 h 05) |
| CORE tests | 125 s | 156.9 s |
| check_all --core --jobs 4 | 47 s | 51.4 s |
| smoke --bin | 107 s | 108.6 s |
| Seed fingerprints | 24 s (round 70) | 26.6 s |
| FULL tests | 224 s | 253.9 s |
| Checks and install | about 12 min | installed 20:51, checks inside sitting 2 |

Both rounds really took about 15-17% of their plans (counted; against round 74's 8 h 30 wall-clock plan it was about 25%). This plan keeps its figures as caps and the real
ones beside them; it does not assume the real speed.

## The parts, counted

Each part has a cap of its count plus half, rounded up to 5 min. At a cap the part stops and the report says what
is left.

### Desk part (this run): done, about 23 min (counted with date, 21:04 to 21:27)

| # | Part | Time | Kind | Result |
|---|---|---|---|---|
| D-O | Options trace | 14 min (21:04-21:18) | counted (date) | build/r81/options/OPTIONS_TRACE.md: all 25 Options lines with bytes, values, reset values and readers; New Game starts from the defaults; saves keep all 20 bytes; the versus copy and its writers; safe and do-not-offer lines |
| D-H | Hook trace | 13 min (21:04-21:17) | counted (date) | build/r81/hook/HOOK_TRACE.md: the one New Game step, the trap, the deferred write, fail-closed rules, robot checks R1-R14 |
| D-M | Home of the rows | 9 min (21:04-21:13) | counted (date) | build/r81/home/HOME_DESIGN.md: the rows under Helpers, settings keys, `lenient`, tests N1-N4, U1-U9, `newgame` page robot scenario |
| D-G | One Grok consult | 1 min (21:20-21:21) | counted (date) | docs/collab/ROUND81_OPTIONS_GROK.md: four rows, "New Game defaults", danger zone out |
| D-P | This plan, with the consult | 9 min (21:18-21:27) | counted (date) | docs/ROUND81_PLAN.md |

The three traces ran side by side, so the desk part's wall clock is about 23 min (21:04 to 21:27, the plan written after the traces).

### The design the build follows (from the traces; one design, the conflicts settled)

- **Where the core writes:** the hook trace's choice. A reserved svc (word 0xEFFEC003; 0xEFFEC001 is the chests,
  0xEFFEC002 the names) over the first word of `GameConfigData::StartFromBeginning` 0x001D0618 (original word
  0xE92D4070), laid only while the title is Fates (`is_fates_title()`, so Seal too) and at least one row is not
  Game's choice; the 0031 / 0035 machinery (word follows the rows, put back after a state, a stranger word left
  alone, `checks_itself()` false = off). At the svc: lr == 0x00441794 (the one call site), r0 == `*G_GameConfig`
  (0x006DA0F8) and not 0, block readable, no player army, no map; then only "pending" is recorded and the replaced
  push is done. **At the end of that frame** (after `fates_rando_session::after_frame`, outside its Fates-rando
  gate): the same checks again, then each set row's byte is stored only if it differs: +0x8 battle animations (0/1),
  +0xC map speed (0/1/2), +0xD enemy turn skip (0/1/2), +0x16 HP bars (0/1). Nothing else: no word +0x4, no camera
  byte, no volume, no +0xE danger zone, no game function call, never the versus copy (versus::Data +0x12AC). One log
  line with the bytes before and after.
- **Why not the other two places the traces named:** after `Reset` in `GameReset` (the options trace's option A)
  runs before every title, Continue too, so it is not "once per New Game"; the randomizer's existing `NewGameWatch`
  (the home design's trigger) most likely misses a Normal + Classic New Game and is off for Seal. The frame-end
  write keeps `NewGameWatch` firing in the pick frame (it needs +0x8..+0x17 unchanged in that frame; its internal rest_moved flag is then set for the next frame, which is harmless; A2 adds a unit test for it). A2 also traces, before the build, which proc label `MainSequence::Jump(4)` lands on after the pick, so a `GameConfigData::Reset` after the pick is caught at the desk, and P2 reads the bytes at the character creator first.
- **Where the rows live:** the home design, with Grok's name "New Game defaults": four enum fields in zakuro-core
  `Helpers` (`battle_animations`, `map_speed`, `enemy_skip`, `hp_bars`; never the unread `enemy_phase`), each with
  `skip_serializing_if` at Game's choice (an untouched file and a round-80 file round-trip byte for byte) and a
  per-key `lenient` reader (a bad value resets only that key; also given to `enemy_phase` and `true_hit`, which
  changes round 80's U3 on purpose, said in the patch message). Round 80's help line is reworded to name the new
  Enemy turn skip row as well as line 6 and the Start key.
- **Patches:** `0039-page-...-new-game-defaults.patch` (zakuro: menus.rs, settings.rs, pagebot.rs; zakuro-core:
  fates_helpers.rs fields) and `0040-core-...-new-game-defaults-writer.patch` (zakuro-core: new
  `fates_options.rs`, lib.rs `run_frame` call, kernel/svc.rs dispatch).

### Sitting 1: code and unit tests (no game run; cargo unit tests in the reused targets): 4 h 00

| # | Part | Time | Cap | Kind | Patch / files |
|---|---|---|---|---|---|
| A0 | Before any code or cargo run: build/STOP_ROUND absent; D: measured with df and the disk rule below applied (at least 47.7 GB free); nothing is compiled before A0 passes | 0 (inside A1) | - | counted (one df) | none |
| A1 | **The rows** (HOME_DESIGN 2, Grok's words): four enums with `byte()`, `lenient`, the collapsing "New Game defaults" line under True hit, its rows, help and note, the reworded help line, pagebot's "game = absent key" rule; tests N1-N4, U1-U9 changes, the words test | 1 h 25 | 2 h 10 | estimate (HOME_DESIGN 7) | new `0039-page-...` |
| A2 | **The writer** (HOOK_TRACE 1.3, 2, 3.1): the svc trap at 0x001D0618 on the 0031 pattern, the svc checks, the frame-end store after the randomizer's watch, the fail-closed branches, the log line; unit tests with planted bugs for every refusal (wrong lr, wrong r0, null pointer, player army present, stranger word, row at Game's choice = no trap word and no guest access, value past the line's count refused, compare-then-store, never +0x4 or +0xE, a state with the word restored) | 2 h 00 | 3 h 00 | estimate (HOOK_TRACE 7) | new `0040-core-...` |
| A3 | Python and routes: `helpers_settings.py` flags for the four rows (sandbox only, planted refusals), tests/test_rando_helpers81.py (no new key or word in `rando.py schema`, share layout and row count as round 74, fingerprints row green), pagebot.py scenario `newgame` with `judge_newgame`; new robot New Game routes copied from `new-game` / `bt-prologue` with one menu press changed (Normal + Classic: DOWN on the mode list; Normal + Phoenix: UP; Hard + Casual: DOWN on the difficulty list) | 30 min | 45 min | estimate (HOME_DESIGN 6; the route edits are timing copies) | Python, config/harness/routes.json |
| G | Gate: `run_tests.py --core` + seed fingerprints (every seed unchanged; no row is a seed input); the series 0001-0040 applies in order on a clean clone of fe14's pin | 5 min | 10 min | counted (round 80: 156.9 s + 26.6 s) | none |

Sitting 1: 85 + 120 + 30 + 5 = **240 min = 4 h 00**. If a fingerprint changes, sitting 1 stops there and says which
seed.

### Sitting 2: backups, builds, proofs, pictures, checks, install, report: 6 h 00

Every proof runs headless and self-exiting, with its own data folder and APPDATA / LOCALAPPDATA under build/r81/,
on recordings copied into build/r81/ and sandbox settings files only. Every save used in a proof (P2, P3 and the rest) is a robot-made save or a copy under build/r81/<part>/ inside the job's own --data folder; the owner's real saves and the real Zakuro settings.toml are hashed before and after each proof set, the way round 80's S1 hashed settings.toml, and any change stops the round. "A/B" means run A without any round-81 row and
run B with rows set, same route, same `ZAKURO_CLOCK`. When a row is set, memory compares leave out exactly the
4-byte trap word at 0x001D0618 and nothing else.

| # | Part | Time | Cap | Kind | Builds |
|---|---|---|---|---|---|
| B0 | build/STOP_ROUND absent; D: measured (the disk rule); backups of play\game exe, build-record, game-path.txt, boot-server, server_build.json, harness_build.json and the capture library to `build/backup/*.2026-11-25-pre-r81` with `pre-r81.json` | 5 min | 10 min | counted (rounds 74, 80; 266 MB) | none |
| B1 | `install.stage_build("r81", build/r81/stage/exe)` with 0001-0040 + `build.py --server --stage-to`; the capture library only if `build.py` says STALE (expected FRESH) | 15 min | 25 min | counted (round 80: 151 s; round 74: 133.8 s) | **game exe (staged)**, **boot-server (staged)** |
| B2 | At most one repair build, only if B1 or a proof fails on our code; the first stage is kept as build/r81/stage/exe-b1 | 30 min | 45 min | counted allowance (round 74: 14 min with re-proof; round 80: 159 s build) | game exe again, at most once |
| B3 | Cargo tests (zakuro-core, zakuro-fs, zakuro `--lib`) in the reused targets | 10 min | 15 min | counted (round 74: 57 s) | none |
| P1 | **Game's choice is today's game** (R14, H1 style): `smoke.py run --bin` with no round-81 keys and again with an explicit all-"game" table. **Pass:** memory equal to round 80's baseline at every point and the trap word never written | 10 min | 15 min | counted (smoke 108.6 s, round 80) | none |
| P2 | **Exactly the chosen bytes, once per New Game** (R2, R3, R4): A/B/C on the New Game routes: Normal + Casual (bt-prologue / opt-t4-newgame), Normal + Classic, Normal + Phoenix, Hard + Casual. Rows set to non-default values on all four lines in B. Run C sets the same four values on the game's own Options screen before the pick (opt-t2-*-set style), with no round-81 row. **Pass, check one (the trap itself moves nothing, R4; a hard gate):** exactly one `New Game` log line per route in B and none in A or C; before the pick memory equal; at the pick frame's end and through the character creator, the whole memory (FCRAM, VRAM, DSP, AXI) A vs B equal except the trap word and the chosen bytes of `*G_GameConfig`; GameUserData equal; **both random generators** (0x00752B7C, 0x00752B8C), the GetNow log and GameRealElapse equal; the versus copy (versus::Data +0x12AC, when allocated) equal. **Pass, check two (the game then acts on the bytes as if you set them yourself; R3):** at the Prologue's first map frame and at the first save, B vs C (not B vs A): the options block, GameUserData, the versus copy and the save file equal. Differences B vs A after the character creator are EXPECTED (the game draws without HP bars, timing options move the general dice) and do not count as failures; they are listed in the report, not judged. Any B vs C difference beyond the trap word is a failure. If check one fails (the trap moves the clock or the dice), the write moves to plan B (HOOK_TRACE 1.2 F) with the repair build, else the round stops | 1 h 15 | 1 h 55 | estimate (HOOK_TRACE 7: most of the 3-4 h proofs) | none |
| P3 | **Loads never write; the game's screen still works** (R2 loads, R5, R6): with rows set, bt-ch2 (chapter save), opt-ch8-reload (battle save) and a game-over retry if one is recorded: zero log lines and memory equal to the no-row run (less the trap word); the block after the New Game write equals the block of the matching `opt-t2-*-set` route that set the same lines on the game's screen; on the new game, a line changed on the game's screen, a save, a load: the block holds the screen's choice and the count stays 1; an old save loaded and saved again with rows set equals the no-row run's file byte for byte | 45 min | 1 h 10 | estimate | none |
| P4 | **Randomizer and Nuzlocke New Game paths** (R7, R8, R1): rows set on bt-prologue (Casual) with a queued randomizer answer: the pick fires, run id and fingerprint equal the no-row run; a Nuzlocke answer with rows set: graveyard file and army equal at the first map frame; R1, the side look: the Normal + Classic route with a randomizer answer, log word +0x4 and whether "New Game mode picked" appears (report only, nothing fixed) | 30 min | 45 min | estimate | none |
| P5 | **Battle animations and HP bars reach the game** (R12): the Prologue's first fight with battle animations Off plays on the map; the fight results equal the On run (round 38 T7's rule); HP bars Off: no bars on the first map; a support or dance following the byte is written as NOT REACHED unless a recorded save reaches one inside the cap | 20 min | 30 min | estimate | none |
| P6 | **Seal of Flames and save states** (R9, R10): one Seal New Game with rows set, only if a Seal New Game recording exists or fits inside the cap: one write, the P2 compare holds; a state taken before the pick with rows set, loaded with rows off: the original word back within one frame, no write. Else "same code, not robot-proven" (unit tests cover the word rule) | 20 min | 30 min | estimate | none |
| S1 | **The rows save** (page robot scenario `newgame`): opens Esc, opens New Game defaults, clicks two rows and back. **Pass:** every expect ok; the sandbox settings.toml holds exactly the set key; the real `%APPDATA%\zakuro\settings.toml` hash the same before and after; no window | 10 min | 15 min | estimate (round 80 S1) | none |
| V | **Pictures a person looks at** (F-051 (2)), headless frame captures as round 80's E1 sheets: (1) the game's own Options screen right after a New Game with rows set, each line on the chosen value (R13: the row words must match the game's screen; if a word differs, the row's word is changed to the game's); (2) the Prologue's first fight on the map with battle animations Off; (3) the Prologue map with HP bars Off and On side by side. Each SEEN or NOT REACHED. The Esc rows cannot be drawn headless: on your ok list | 25 min | 40 min | estimate (round 71 P2: 40 min for five) | none |
| C1 | CORE: `run_tests.py --core`, `check_all.py --core --jobs 4`, `smoke.py run --bin build/r81/stage/exe` (8/8, memory equal), seed fingerprints (no seed changed), hygiene (no game bytes tracked) | 15 min | 25 min | counted (round 80: 156.9 + 51.4 + 108.6 + 26.6 + 10.3 s, build/r80/check logs and F-065) | none |
| C2 | **FULL:** `run_tests.py --full` on the staged exe (an engine patch makes FULL due, F-052). The F-051 full matrix is round 82, not here | 10 min | 15 min | counted (round 80: 253.9 s) | none |
| C3 | Install after C1 and C2 pass: `tools/release/install.py` (copies next to the target first, automatic rollback), `install.py verify`, memory compare of a copy of the installed exe (`smoke --only mem-off`) | 10 min | 15 min | counted (round 74: about 12 min with checks) | none |
| R | Report with the pictures, the A/B tables and the undo steps; docs that change after the proofs: OPTIONS_WIRING.md (a section: the core writer replaces W1/W2 for these four lines), MENUS.md (the block's readers and New Game), PLAY.md 6f (the new rows), RANDOMIZER_INGAME.md (R1's result), DECISIONS.md (a new F entry, CRLF kept), patches/zakuro/README.md rows 0039 / 0040 | 30 min | 45 min | estimate (rounds 74 and 80 reports) | none |

Sitting 2: 5 + 15 + 30 + 10 + 10 + 75 + 45 + 30 + 20 + 20 + 10 + 25 + 15 + 10 + 10 + 30 = **360 min = 6 h 00**.

### Totals

| | Time |
|---|---|
| Desk part (done) | about 23 min, counted with date (21:04 to 21:27) |
| Sitting 1 (A1 85, A2 120, A3 30, G 5) | 4 h 00 |
| Sitting 2 (builds 60, proofs 210, pictures 25, checks and install 35, report 30) | 6 h 00 |
| **Total of the engine part** (estimate: a sum of parts; B2 included, as the slow side) | **10 h 00** |
| **With the desk part** | **10 h 23** |
| Without the repair build | 9 h 30 (9 h 53 with the desk part) |
| Roadmap row (NEXT_STRETCH_2026-11-24 item 5, ROADMAP row 81) | 11-13 h (estimate) |
| By rounds 74 / 80's real speed (about 15-17% of plan) | about 1 h 40, **not** assumed |

**Not over:** 10 h 23 is under the low end of the roadmap's 11-13 h, so the standing OK covers it (F-059 (3): only
a plan clearly over its count is held). It came in under because the desk part found one exact New Game moment, so
the old design's save guard (W2), the readable library and "OK C" are all gone; the roadmap's 8-10 h assumed
rebuilding W1 and W2 in the core.

**Hard stop:** 1.5 times each sitting: **6 h 00** for sitting 1 and **9 h 00** for sitting 2. A failed gate
(fingerprint change, CORE or FULL failure, P1 not equal, P2 check one showing any byte beyond the chosen ones, a second repair
needed) stops the round and reports; it does not push on (F-059 (3)). Nothing is installed unless C1 and C2 pass.
Whatever the sitting caps allow, if the engine part's real time reaches the roadmap's 13 h before the work is done, the round stops and reports (F-059 (3)).

### Cut order (if a sitting runs past its count)

1. **P4's side look R1** (the randomizer's Normal + Classic gap): saves about 10 min. It stays an open item.
2. **P6** (Seal New Game and the save-state run): saves 20 min. Seal stays "same code, not robot-proven"; the word
   rule stays covered by unit tests.
3. **P2's extra routes** (keep Normal + Casual and Normal + Classic; drop Phoenix and Hard + Casual): saves about
   25 min. The report names the two routes not run.
4. **The Enemy turn skip row** (A1 about 10 min, P2/P5 about 10 min): saves about 20 min. Round 80's help line stays
   as it is.

With all four cut: **8 h 45** (10 h 00 minus 1 h 15). **The smallest useful set** that still ships: three rows
(Battle animations, Map speed, HP bars), the writer, P1, P2 on two routes, P3, P4's randomizer and Nuzlocke runs,
P5, S1, the pictures, the checks and install. Below that set the round stops and reports rather than ships.

## Disk budget

**Free now:** **78.2 GB** (counted: df 80,108 MB at 21:22 today). Round 80 plus this desk part used **2.9 GB** in all (counted: df
83,121 MB at 18:19 before it, 80,108 MB after). The stop line is 30 GB free.

### Counted sizes behind the estimate (du, 21:23)

| Folder | Size | Note |
|---|---|---|
| build/r80 (whole round 80) | 2,642 MB | t 1,058, repair 311, stage 301, e2 257, e1 187, n1 173, install 155, s1 141, check 38 |
| build/r74 (whole round 74) | 13,980 MB | of it cargo-target 7,466 (a fresh cargo folder, not repeated), p1 4,143 (A/B memory compares), p3 1,197, p2 524, stage 301, check 193 |
| build/r71 (whole round 71) | 11,238 MB | of it libmode 6,317 (not repeated) |
| build/backup pre-r80 | 266 MB | one round's backups |
| engine/target/zakuro-core-test | 5,201 MB | 5,139 before round 80: grew 62 MB |
| engine/target/zakuro-frontend-test | 3,236 MB | 3,194 before round 80: grew 42 MB |
| build/port/fef/target, engine/target/zakuro-server-stage | 2,658 MB, 861 MB | reused in place by the builds |

### What round 81 adds, per part

| Part | Typical | Worst | Source |
|---|---|---|---|
| Staging (exe + boot-server; exe-b1 kept if a repair build runs) | 0.3 GB | 0.3 GB | counted: build/r80/stage and build/r74/stage 301 MB each |
| Backups (pre-r81) | 0.26 GB | 0.26 GB | counted: pre-r80 266 MB |
| Game exe objects and boot-server stage target (reused) | 0.7 GB | 1.3 GB | estimate split of counted growth (round 80 plan) |
| Cargo tests in the reused targets | 0.2 GB | 7.3 GB | counted: round 80 grew them 0.1 GB; worst = a fresh target (counted build/r74/cargo-target 7,466 MB) |
| Robot proofs P1-P6, S1 and pictures (A/B whole-memory compares like round 74's p1) | 4.0 GB | 8.0 GB (cap) | counted: round 74 p1 4,143 MB; round 80's proofs about 2.1 GB |
| Checks (smoke --bin, check folders, install copies) | 0.2 GB | 0.3 GB | counted: build/r80 check + install 193 MB, build/r74/check 193 MB |
| Gate, Python, review sheet | 0.1 GB | 0.2 GB | estimate (round 80's gate 12 MB, review 2 MB) |
| FULL tests remake build/rom in place | 0 | 0 | counted (rounds 74, 80) |
| **Round 81 total** | **about 5.8 GB** | **about 17.7 GB** | estimate from counted sizes; round 80 really used 2.9 GB, round 74 about 14.3 GB |

### The cargo build: reuse, do not make a new 7.5 GB folder

- Use `engine/target/zakuro-core-test` (zakuro-core, zakuro-fs) and `engine/target/zakuro-frontend-test` (zakuro),
  as round 80 did. The game exe builds in build/port/fef/target, the boot-server in
  engine/target/zakuro-server-stage.
- **Never** point cargo at `build/r74/cargo-target` (round 74's evidence, F-058 (2)).
- Fallback only: a fresh `build/r81/cargo-target`, only if the reused targets fail for a reason that is not our
  code and B0's projection still stays at or above 30 GB with it (the worst case already counts it).
- Nothing is deleted or moved in round 81.

### Free space after round 81

| Start | Typical (5.8) | Like round 74 (14.3) | Worst (17.7) |
|---|---|---|---|
| **Now: 78.2 GB** | 72.4 GB | 63.9 GB | **60.5 GB** |

Looking further (estimates): round 82's full check (up to 14.5 GB, counted round 76) after the worst round 81 leaves
about 46 GB, still over the line.

### The plain rule

**The engine part starts only if D: free at A0 / B0, minus the worst case (17.7 GB), stays at or above 30 GB, that
is at least 47.7 GB free.** Today that holds (78.2 GB). It is measured again before every proof batch (P1 to S1): a
batch that would take D: under 30 GB does not start, and the report says what is left. Robot shots are kept only
for the frames each proof names; the proofs folder stops at 8 GB.

## Risks, and what is NOT REACHED until a robot run

Read at the desk with good confidence: the 25 Options lines and their bytes, `GameReset` before every title, the one
caller of `StartFromBeginning`, loads never reaching it, saves keeping all 20 bytes, the versus copy's writers, each
line's store being one byte, the randomizer watch's rule. **Not reached until the robot runs them (sitting 2):**

| Not reached yet | Why it matters | Settled by | If it fails |
|---|---|---|---|
| The trap's interpreter run leaves the clock and both random generators alone | the "no roll changes" promise | P2 (R4) | plan B: a read-only watch on MainSequence's program pointer (HOOK_TRACE 1.2 F, needs its code table traced) in the repair build; else the round stops |
| Nothing reads the four bytes with an effect between `StartFromBeginning` and the frame's end | "as if set before the Prologue" | P2 (R3) | write inside the svc but after the watch (the watch then ignores +0x8..+0x16), repair build |
| No `GameConfigData::Reset` between the pick and the first map (round 38 T4 saw none, [medium]) | the bytes must survive to the Prologue and the first save | P2, P3 | the write moves later on the same route (character creator end), repair build |
| Every route the robot has to a load (chapter save, battle save, game-over retry) writes nothing | "existing saves untouched" | P3 | a bug in the svc checks: repair build; never ship a write on a load |
| A Normal + Classic / Phoenix / Hard New Game goes through the same step | one write for every mode | P2's new routes | the routes are new: a wrong menu press is fixed in the route, not the code |
| The game's screen words for each value match the rows | the page must not lie | V (1) (R13) | the row's words change to the game's (page text only, inside A1's patch if before the build, else the repair build) |
| Battle animations 2-4 and the danger zone's values | not offered, so no risk to the rows | - | stay out |
| Supports and dances follow the battle byte (read in code, OPTIONS_WIRING 1) | the help line says so | P5 if a save reaches one | stays "read in the game's code, not seen" |
| The randomizer page and Nuzlocke start with rows set | the deferred write must not block them | P4 (R7, R8) | write a frame later; repair build |
| The randomizer's Normal + Classic gap (it may never open its page there) | not this round's change; a present gap | P4 (R1) | reported to you; fixed only as its own later change, your yes first |
| Seal of Flames New Game | one shared choice | P6 (R9) if a recording exists | "same code, not robot-proven" |
| No headless picture of the Esc window | the rows are not SEEN by a robot | S1 checks values only | you look once (ok list) |
| The known 0xC0000005 burst at a job's first step (round 72) | robot retries cost time | each job may retry once | never more than one relaunch per job |

## Your calls (all have a safe default; silence means the default; each answerable with a word)

| # | Call | Default |
|---|---|---|
| 1 | Which rows: Battle animations, Map speed, Enemy turn skip, HP bars? | **All four** (Grok agrees; Enemy turn skip is the game's own line 6, and round 80's own speed-up was cut) |
| 2 | Danger zone as a row? (yes / no) | **No** for now: every value draws the zone and nobody has seen what the three change. A later look at the old danger pictures could add it |
| 3 | New Game only, or also change saves you already have at every load? | **New Game only.** Changing old saves at every load needs the old save-guard design again (OPTIONS_WIRING W1 + W2) and is not in this round |
| 4 | The line's name | **New Game defaults** (Grok's; "For every New Game" sounded like it changes the game you are playing) |
| 5 | Battle animations: only Off / On? | **Yes.** The game's per-army and per-unit choices are not traced |
| 6 | Look at the randomizer's Normal + Classic gap this round, report only? (yes / no) | **One robot look in this round (P4), report only.** Any fix is its own later change, with your yes |
| 7 | One bad value in the settings file resets only that row (and no longer True hit too)? | **Yes** (changes round 80's U3 test on purpose) |
| 8 | Nuzlocke: grey the rows out? | **Not greyed**: they are the game's own comfort lines |
| 9 | One choice for Fates and Seal of Flames, or one each? | **One for both** (same game underneath) |

Grok: one consult in this desk part (docs/collab/ROUND81_OPTIONS_GROK.md). No second consult is planned.

## Not in round 81 (on purpose)

- Writing the Options of a game already going, or of old saves (call 3).
- The danger zone, battle animations 2-4, volumes, battle music, camera lines, subtitles, voices, Tutorial and the
  easy-play lines (OPTIONS_TRACE section 5: either the game sets them from difficulty and mode, or a plain store does
  not reach the sound system, or no reader was found).
- Fixing the randomizer's Normal + Classic gap (call 6).
- The F-051 full matrix (round 82), any push, a release tag, any delete or move, any download.

## Hard rules in round 81 (as in every round)

build/STOP_ROUND is checked before every build, game or robot start; every start is headless and self-exiting with
its own data folder and APPDATA / LOCALAPPDATA under build/r81/; at most 6 robot jobs at once; never relaunch a run
more than once; a visible window = a failed run; never start play\game\Fire Emblem Fates.exe; never write
%APPDATA% / %LOCALAPPDATA%, play/config.json, play/state.json, saves, Zakuro settings, cheats or mods; never touch
the versus copy; no Nintendo or Seal of Flames bytes in git (addresses, offsets and short identifiers only);
backups first, staged, installed only after C1 and C2; every process started is listed and killed before the round
returns.
