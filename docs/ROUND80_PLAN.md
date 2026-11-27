# Round 80: the counted header (faster enemy phase + True hit)

Written in round 80's desk part (2026-11-25, 18:04 to 18:25 EST, read only) from the three desk traces:
build/r80/enemy/ENEMY_TRACE.md, build/r80/hit/HIT_TRACE.md (with make_true_hit_table.py and
true_hit_table.json), build/r80/home/HOME_DESIGN.md, and the roadmap row (build/roadmap/NEXT_STRETCH_2026-11-24.md
item 4, docs/NEXT_STRETCH.md). Nothing in this file has been built. Round 80 runs on the owner's standing OK
(F-059 (3); the owner's pick F-057), because its count stays inside the roadmap's 14 h 30-17 h (see Totals).

Every time below is **counted** (measured in a real round, the source is named) or **estimate** (never measured,
written on the slow side), as F-027 asks. GB = the Windows count (1 GB = 1,024 MB), as in
build/r78/disk/DISK_BEFORE_R80.md.

## In plain words

**What the desk part found:**

- **The game already has a faster enemy phase.** Its own Options screen (the system menu on the map, line 6) has
  Off / Move / All. Move: enemies jump straight to their tile and the camera does not glide to each one. All: the
  whole enemy turn runs behind a dark screen. And **pressing Start during an enemy turn already skips the rest of
  it**, in every save, today. The game stops a skip by itself for story fights, scenes and messages.
- **What the game does not have** is a plain 2x / 4x where everything simply runs faster. That is what round 80
  adds.
- **The real hit chance was found in the game's own code.** When the forecast says 50 or less, that is the real
  chance. Above 50 the game quietly helps you: a shown 70 really hits about 79 times in 100, a shown 80 about 90,
  a shown 99 about 99.8. All 101 values were worked out from the game's own roll (not from fan wikis).

**What you will see after round 80** (each shown to you as a looked-at picture where one can be taken; nothing
counts until you say ok, F-037):

1. **Press Esc while playing Fates.** Right under the Randomizer button there is a small **Helpers** heading with
   two rows:
   - **Enemy phase: Normal / 2x / 4x.** At 2x or 4x the enemy turn plays two or four times as fast. The moment
     anyone talks (a boss line, a story scene, a message, a tutorial) it drops back to normal speed by itself, and
     goes fast again afterwards. A small "enemy 2x" tag shows in a corner while it runs fast.
   - **True hit: Off / On.** With On, the battle forecast shows the real chance next to the game's number, for
     example "70 (real 79)". It never shows "real 100" unless the hit is really certain (a shown 98 or 99 shows
   "real 99").
2. **The help line** under the rows also says: the game's own Options line 6 (Off / Move / All) and the Start key
   still work as they always did.

**Defaults:** Normal and Off. With the defaults the game is exactly today's game (the robot proves it with a
memory compare).

**What never changes:**

- **No roll ever changes.** True hit only paints a number on the PC's copy of the picture; it writes nothing into
  the game. 2x / 4x plays the very same game frames faster, so the same enemies do the same things with the same
  dice (the robot checks it).
- **Story lines are never rushed.** Talks, boss lines, story scenes, messages and tutorials always play at normal
  speed (the robot checks it).
- **Held Tab stays as today** (Zakuro's unlimited fast-forward, no sound). It wins over 2x / 4x while held.
- **The Start key stays the game's own.** The port does not touch it.
- **Your randomizer seed and share code never change.** Helpers are not randomizer rows.
- **Your own turn is never sped up**, and Entrust (your own auto turn) stays at normal speed unless you say
  otherwise (call 5).
- One choice for both Fates and Seal of Flames (same battle code), kept for every save and every New Game.

**How long:** about **14 h 30** (estimate: a sum of parts, mostly estimates; builds, checks and install counted from rounds 71 and 74) for the engine part in two sittings (7 h 25 code and unit tests, then 7 h 05
builds, proofs, checks and the report), plus the desk part already done (about 20 min, counted from the clock).
**14 h 50 in all, inside the roadmap's 14 h 30-17 h (estimate), so the plan is not over its count.** Rounds 71
and 74 really took about a quarter of their plans (counted, below), but the count stays the time box.

**Disk:** wave 2 of the cleanup is already done. You typed "Yes, all of wave 2" in chat; Claude's main session (not
the read-only desk run) deleted exactly the plan's six rows at 18:06 today and ran the core tests after it (929, 0 failed;
build/r80/cleanup/WAVE2_DELETED.txt, core_after.log). D: has **81.2 GB free** (counted, df 18:19: 83,121 MB). Round 80 needs
about 8.6 GB, at worst 17.7 GB (estimate from counted rounds 71 and 74), so D: stays at 63.5 GB or more, far over
the 30 GB stop. The engine part starts only if that still holds when it starts (step B0).

**What needs your OK:** nothing new. The engine builds below are covered by your standing OK (F-059 (3)). Your
calls (the end of this page) all have safe defaults; silence means the default. Still held for you: every push.

## Times the engine steps really took (counted)

| Step | Round 71 (REPORT_2027-01-16) | Round 74 (REPORT_2027-01-20, build/r74/build) |
|---|---|---|
| Plan for the whole round | 14 h 40, re-counted 8 h 45 after cuts | 13 h 10 (sittings), 8 h 30 wall-clock plan |
| Whole round, real | about 2 h 30 | about 2 h 07 (04:55-07:02) |
| Code (side by side) and gate | 44 min (plan 3 h 15) | code tracks 27 / 30 / 37 min side by side, gate 10 min |
| Builds (exe + boot-server, staged) | 10 min in all (exe 86.7 s, boot-server 76.7 s) | 6 min (stage log: 133.8 s; exe 88 s, boot-server 70 s) |
| Repair build | not needed | used: repair and re-proof 14 min (06:31-06:45) |
| Cargo tests | 7 rows | 57 s (core + fs 10.4 s, zakuro 46.6 s) in a new target folder |
| Proofs | 1 h 15 (plan 1 h 45) | P1 38, P2 17, P3 about 25, P4 about 2 min |
| Checks and install | 10 min | about 12 min (06:46-06:58) |
| CORE tests | 158 s | 125 s (today after wave 2: 136.4 s, build/r80/cleanup/core_after.log) |
| check_all --core --jobs 4 | 82 s | 47 s |
| smoke --bin | 110 s | 107 s |
| FULL tests | 233 s | 224 s |

The fixed engine steps planned at 3 h 15 (ROUND71_PLAN sitting 2) really took **about 30-45 min** of wall clock in
both rounds (counted: builds 6-10 min, checks and install 10-12 min, repair 0-14 min, report). This plan keeps
the planned figures as caps and lists the real ones beside them.

## The parts, counted

Each part has a cap of its count plus half, rounded up to 5 min. At a cap the part stops and the report says
what is left.

### Desk part (this run): done, about 20 min (counted)

| # | Part | Time | Kind | Result |
|---|---|---|---|---|
| D-E | Enemy-phase trace | 12 min (18:04-18:16) | counted (date) | build/r80/enemy/ENEMY_TRACE.md: AISkip +0xD is Off / Move / All; Start skip is native; the four story signals; Zakuro pacing recommended; robot questions R1-R12 |
| D-H | True hit trace | 8 min (18:04-18:12) | counted (date) | build/r80/hit/HIT_TRACE.md: `RandomCalculateHit` 0x003A3588, all 101 values, three hook points |
| D-M | Home of the rows | 8 min (18:04-18:12) | counted (date) | build/r80/home/HOME_DESIGN.md: `[fates_helpers]` in Zakuro's settings, Helpers heading in the Paused window, U1-U11, H1-H7 |
| D-P | This plan | about 8 min (18:17-18:25) | counted (date) | docs/ROUND80_PLAN.md |

The three traces ran side by side, so the desk part's wall clock is about 20 min (18:04-18:25, the plan written after the traces).

### Sitting 1: code and unit tests (no game run; cargo unit tests compile into the reused targets): 7 h 25

| # | Part | Time | Cap | Kind | Patch / files |
|---|---|---|---|---|---|
| A0 | Before any code or cargo run: build/STOP_ROUND absent; D: measured with df and the disk rule below applied (at least 47.7 GB free); nothing is compiled before A0 passes | 0 (inside A1) | - | counted (one df) | none |
| A1 | **The Helpers home** (HOME_DESIGN 2): `[fates_helpers]` table in Zakuro's settings.toml (`enemy_phase` normal / 2x / 4x, `true_hit` off / on, nothing written at the defaults), new core file `fates_helpers.rs`, `System::set_helpers`, the Helpers heading and two rows under the Randomizer button (Fates title only), the Paused window gets a scroll area and a max height, the help line, the page robot's `{"esc": "paused"}` and `{"expect_settings": ...}` and a `helpers` scenario in pagebot.py; unit tests U1-U9. One Grok consult on the row words and calls 2-4 (5 min, inside) | 1 h 30 | 2 h 15 | estimate (HOME_DESIGN 5) | new `0037-page-...-helpers-heading.patch` (zakuro: menus.rs, settings.rs, lib.rs, pagebot.rs; zakuro-core: fates_helpers.rs) |
| A2 | **2x / 4x pacing** (ENEMY_TRACE 2, hook 1): a core reader `enemy_phase_speed()` returning 1, 2 or 4: fast only when the helper asks, an AI sequence runs (Situation +4 bit 30), the army is not the player's, GameSkip(*0x006D8808) +4 has bits 0 and 1 clear (the game's own mask, (flags & 3) == 0, as GameSkip::Tick 0x004EB4EC tests; bit 1 is set by GameSkipControl::Disable 0x001E0B9C, bit 0 also by GameSkipSequenceHelper::DisableSkip 0x0021DCF8) and the talk manager *0x006DCDAC is 0; the frontend loop emulates 2 or 4 frames per screen frame, held Tab wins, sound as held Tab (call 4), the corner tag; a per-frame speed log for the robot; unit test U10 | 3 h 00 | 4 h 30 | estimate (ENEMY_TRACE 5: about 3 h code and tests) | new `0038-core-frontend-...-enemy-phase-speed.patch` (zakuro-core: new reader; zakuro: lib.rs run loop) |
| A3 | **True hit** (HIT_TRACE 5): the 101 thresholds as our own computed table (true_hit_table.json, made from the game's rule; no game bytes), the forecast window found each frame (a PC watch on `DrawSimpleHit` 0x00365DEC and `DrawDetailDataOne` 0x003676B8, or the proc walk for "SequenceTargetSelect", picked in the first 30 min), "real NN" painted beside the number on the host's copy of the screen with the growth view's 5x7 glyph painter; the display rule (call 6): the shown real number is built from the threshold out of 10000, never from the table's real_whole field: 100 only when the threshold is 10000, else at most 99, and at least 1 when the threshold is above 0; unit tests on the table and the painter (shown 0, 1, 50, 70, 98 and 99; dash when a side has no attack) | 2 h 30 | 3 h 45 | estimate (roadmap 4-6 h 30 with proofs; the painter is reused from patch 0028's growth view) | new `0039-core-...-true-hit.patch` (zakuro-core: new file, `read_screen_scaled` hook) |
| A4 | Python and checks: U11 (`rando.py schema` has no helper keys, the share layout is round 74's), help words, the robot's sandbox settings writer for `[fates_helpers]` | 20 min | 30 min | estimate | Python only |
| G | Gate: `run_tests.py --core` + seed fingerprints (every seed unchanged; no helper is a seed input) | 5 min | 10 min | counted (round 74: 125 s + 24 s; today 136.4 s) | none |

Sitting 1: 90 + 180 + 150 + 20 + 5 = **445 min = 7 h 25**. If a fingerprint changes, sitting 1 stops there and
says which seed.

### Sitting 2: backups, builds, proofs, pictures, checks, install, report: 7 h 05

| # | Part | Time | Cap | Kind | Builds |
|---|---|---|---|---|---|
| B0 | build/STOP_ROUND absent; D: measured with df (the disk rule below); backups of play\game exe, build-record, game-path.txt, boot-server, server_build.json and the capture library to `build/backup/*.<date>-pre-r80` with `pre-r80.json` | 5 min | 10 min | counted (rounds 71, 74) | none |
| B1 | `install.stage_build("r80", build/r80/stage/exe)` = `engine.py port --stage-only` with 0037-0039 + `build.py --server --stage-to`; the capture library only if `build.py` says STALE (expected FRESH: no menu or capture file changes) | 30 min | 45 min | counted (round 74: 133.8 s; round 71: 10 min) | **game exe (staged)**, **boot-server (staged)** |
| B2 | At most one repair build, only if B1 or a proof fails on our code (a change in the run loop is a hot path) | 45 min | 1 h 10 | counted allowance (round 74 used one: 14 min with re-proof) | game exe again, at most once |
| B3 | Cargo tests (zakuro-core, zakuro-fs, zakuro `--lib`) in the reused targets (disk section) | 15 min | 25 min | counted (round 74: 57 s) | none |
| E1 | **The game's own skip, looked at** (R1-R4): from the robot save `opt-ch8-set` (chapter 8, holds All), copies only: Off, Move and All, and Start pressed 120 frames into an Off enemy phase; frames from end of turn to the next player phase for each; shots of one enemy act. **Pass:** Move shows no camera glide and fewer frames than Off; All shows the dark screen; Start ends the enemy phase early; units and the random state at the next player phase are the same for Off, Move, All and Start (R4). If R4 differs, the help line says so plainly | 1 h 00 | 1 h 30 | estimate (ENEMY_TRACE 5) | none |
| E2 | **2x / 4x is pacing only** (H2, R5, R6, R11): one recorded route with an enemy phase (bt-ch8-pair's turns, ROBOT.md 3d) at Normal, 2x and 4x with paced headless runs. **Pass:** GameUserData, GameConfigData, all units, `G_BattleRandom` 0x00752B8C and the general generator 0x00752B7C equal at the same emulated checkpoint frames; the speed log shows 2 / 4 only while bit 30 is set and the army is not the player's (R11 settles the army reading); wall time of the enemy phase at most 0.55x (2x) and 0.33x (4x) of Normal, counted in the run (else 4x is left out, call 2) | 30 min | 45 min | estimate | none |
| E3 | **Story lines are not rushed** (H3, R7-R9): an enemy turn with a boss quote and an item message (a talking-boss chapter from a robot save). **Pass:** the speed log is 1 on every frame a talk, message, tutorial or boss quote is on screen (traced by GameSkip +4 bits 0-1 and the talk manager each frame), and one robot save with an event scene inside an enemy turn (reinforcements with a talk, or a turn-start event) shows the speed log at 1 for the whole scene; if no such save fits inside the cap, "event scenes during an enemy phase" is written as NOT REACHED and they stay covered only by the signals; the boss quote at 4x shows in full (shots at 1x and 4x side by side). If a quote is not covered by those signals, the reader also reads the battle-quote flag (SequenceBattle +600 bit 0) inside A2's cap and E3 runs once more | 40 min | 1 h 00 | estimate | none |
| E4 | Side questions: Entrust with Move / All / 2x and X still cancels (R10); held A walks faster on game speed 2 in the enemy phase (R12). **Pass:** the facts are recorded; nothing ships on them | 15 min | 25 min | estimate | none |
| T1 | **True hit numbers are the game's** (HIT_TRACE 6.1-6.3): a forecast showing a hit above 50 reads Side +0x30 = the shown number; a break at `RandomCalculateHit` 0x003A3588 shows r0 = the shown number and the threshold r5 = the table's (7887 for 70); then the twin `GetHitProbabilityEffectiveDenominator10000` 0x003A361C called on the guest for 0..100 in a headless helper. **Pass:** all 101 thresholds equal the JSON; one value at or below 50 takes the plain branch; no die moved | 30 min | 45 min | estimate | none |
| T2 | **True hit is display only** (H5, HIT_TRACE 6.4-6.5). **Pass:** memory equal with True hit On and Off at the same frames; the forecast picture with Off is pixel-equal to today's program; with On the second number sits beside the game's number in the simple window (and the detail page if kept), both sides, and the dash case leaves the game's pixels alone | 20 min | 30 min | estimate | none |
| N1 | **Nuzlocke** (H6): a Nuzlocke run with 4x and True hit On against the same run at Normal and Off. **Pass:** graveyard file and army identical | 15 min | 25 min | estimate | none |
| D1 | **Defaults are today** (H1): `smoke.py run --bin` memory compare with no `[fates_helpers]` table and again with an explicit normal / off table. **Pass:** both equal to the round-74 baseline | 10 min | 15 min | counted (smoke 107 s, round 74) | none |
| S1 | **The rows save** (H7): page robot scenario `helpers` clicks 4x and True hit On in its sandbox. **Pass:** the sandbox settings.toml holds `enemy_phase = "4x"` and `true_hit = true`; the real `%APPDATA%\zakuro\settings.toml` hash is the same before and after; no window | 10 min | 15 min | estimate (HOME_DESIGN 5) | none |
| V | **Pictures a person looks at** (one SEEN pair per new feature, F-051 (2)): (1) the forecast with True hit Off and On, zoomed, a shown 70; (2) the enemy phase at 2x: the corner tag frame and a strip of the speed log with the boss-quote frames at 1; (3) the game's own Move and All from E1, for the help line. All on `build/r80/review/sheet.png`. The Esc Helpers rows cannot be drawn headless: on your ok list as "press Esc once and look" | 30 min | 45 min | estimate (round 71 P2: 40 min for five) | none |
| C1 | CORE: `run_tests.py --core`, `check_all.py --core --jobs 4`, `smoke.py run --bin build/r80/stage/exe` (8/8, memory equal), seed fingerprints (no seed changed), hygiene (no game bytes tracked) | 15 min | 25 min | counted (round 74: 125 + 47 + 107 s; fingerprints 24 s, round 70) | none |
| C2 | **FULL:** `run_tests.py --full` on the staged exe (an engine patch makes FULL due, F-052). The F-051 full matrix is round 82, not here | 15 min | 25 min | counted (round 74: 224 s; release r77: 4.1 min) | none |
| C3 | Install after C1 and C2 pass: `tools/release/install.py` (copies next to the target first, automatic rollback), `install.py verify`, memory compare of a copy of the installed exe (`smoke --only mem-off`) | 10 min | 15 min | counted (round 74: about 12 min with checks) | none |
| R | Report with the pictures, the speed log, the 101-value check and the undo steps; docs that change after the proofs: MENUS.md line 52 and OPTIONS_WIRING.md row `enemy_phase` (the effect is now read), SKILLS.md line ~121 (the curve is now reproduced), PLAY.md (the Helpers rows), DECISIONS.md (a new F entry, CRLF kept), docs/NEXT_STRETCH.md calls 1a/1b (wave 2 done) | 30 min | 45 min | estimate (roadmap figure; rounds 71 and 74 reports took about as long) | none |

Sitting 2: 5 + 30 + 45 + 15 + 60 + 30 + 40 + 15 + 30 + 20 + 15 + 10 + 10 + 30 + 15 + 15 + 10 + 30 =
**425 min = 7 h 05**.

### Totals

| | Time |
|---|---|
| Desk part (done) | about 20 min, counted |
| Sitting 1 (A1 90, A2 180, A3 150, A4 20, G 5) | 7 h 25 |
| Sitting 2 (builds 95, proofs 230, pictures 30, checks and install 40, report 30) | 7 h 05 |
| **Total of the engine part** (estimate: a sum of parts; B2 included, as the slow side) | **14 h 30** |
| **With the desk part** | **14 h 50** |
| Without the repair build | 13 h 45 (14 h 05 with the desk part) |
| Roadmap row (build/roadmap/NEXT_STRETCH_2026-11-24.md item 4) | 14 h 30-17 h (estimate) |
| By rounds 71 / 74's real speed (code 23% of plan, builds 9%, proofs 71%, checks 25%; ratios from ROUND74_PLAN) | about 5 h 15 (445 x 0.23 + 95 x 0.09 + 260 x 0.71 + 70 x 0.25 = 314 min), **not** assumed |

**Not over:** 14 h 50 sits at the low end of the roadmap's 14 h 30-17 h, so the standing OK covers it (F-059 (3):
only a plan clearly over its count is held). The enemy part shrank (the roadmap's 10 h 30 assumed a speed-up from
scratch; the game already has the skip), True hit is at the low end of its 4-6 h 30, and the home is the planned
1 h 30.

**Hard stop:** 1.5 times each sitting: **11 h 10** for sitting 1 and **10 h 40** for sitting 2. A failed gate
(fingerprint change, CORE or FULL failure, a second repair needed) stops the round and reports; it does not push
on (F-059 (3)).

### Cut order (if a sitting runs past its count)

1. **E4, the side questions** (Entrust and held A): saves 15 min. Entrust stays at normal speed anyway (call 5).
2. **True hit on the detail page and in the fight scene** (simple forecast only): saves about 30 min (A3 20 +
   T2 10).
3. **2x / 4x pacing** (A2 3 h + E2 30 + E3 40 = 4 h 10): patch 0038 is not made. The Enemy phase row becomes a help
   line pointing at the game's own Options line 6 (Off / Move / All) and the Start key, which E1 has proven. True
   hit and the Helpers heading still ship.

With all three cut: **9 h 35** (14 h 30 minus 4 h 55).

## Disk budget

**Free now:** **81.2 GB** (counted: df 83,121 MB at 18:06:45 after the wave 2 delete, the same at 18:19). Before
the delete: 43.2 GB (counted, df 17:31, DISK_BEFORE_R80.md). The stop line is 30 GB free.

### What round 80 adds, per part

| Part | Typical | Worst | Source |
|---|---|---|---|
| Staging (exe + boot-server; a repair build's first stage is kept under its own name, build/r80/stage/exe-b1, not moved) | 0.3 GB | 0.3 GB | counted: build/r74/stage 301 MB with exe-b1 kept |
| Backups (pre-r80) | 0.26 GB | 0.26 GB | counted: pre-r71 and pre-r74 backups 265 MB each |
| Game exe objects (build/port/fef/target, reused) and the boot-server stage target (engine/target/zakuro-server-stage, reused) | 0.7 GB | 1.3 GB | counted: engine/ grew 1,377 MB over rounds 71 + 74 (0.7 GB each is an estimate split; worst = both) |
| Cargo tests | 1.0 GB | 7.3 GB | estimate for reuse; worst = a fresh target, counted build/r74/cargo-target 7,466 MB |
| Robot proofs E1-E4, T1-T2, N1, D1, S1 and pictures | 6.0 GB | 8.0 GB (cap) | counted: build/r74 p1-p4 6,019 MB for its four proofs |
| Checks (smoke --bin, check folders) | 0.2 GB | 0.3 GB | counted: build/r74/check 193 MB, build/r71/check 180 MB |
| Gate, Python, review sheet | 0.1 GB | 0.2 GB | estimate (round 74's small folders) |
| FULL tests remake build/rom | 0 | 0 | counted: rewritten in place, same 2,049 MB (remade 17:12 today) |
| No library-mode sandbox this round | 0 | 0 | round 71's libmode 6,317 MB is not repeated |
| **Round 80 total** | **about 8.6 GB** | **about 17.7 GB** | estimate from counted sizes; a round like 74 was 14.3 GB (counted folder 13.7 GB + 0.7 GB engine split) |

### The cargo build: reuse, do not make a new 7.5 GB folder

- **Use the targets that already exist:** `engine/target/zakuro-core-test` (5,139 MB, counted) for zakuro-core and
  zakuro-fs, and `engine/target/zakuro-frontend-test` (3,194 MB, counted) for zakuro. They are check_all's own
  cargo caches (tools/check_all.py names them), rebuildable, and no report cites them as evidence. Cargo only
  adds the objects of the changed crates (estimate under 1 GB). The game exe already builds in its fixed folder
  build/port/fef/target and the boot-server in engine/target/zakuro-server-stage, so neither makes a new folder.
- **Never** point cargo at `build/r74/cargo-target` (7,466 MB): it is round 74's evidence ("cargo tests in
  build/r74/cargo-target PASS", F-058 (2)), and cargo would rewrite its files. It is not deleted either; it stays
  a row for a later cleanup wave, the owner's yes first (DISK_BEFORE_R80.md section 7).
- **Fallback only:** a fresh `build/r80/cargo-target`, used only if the reused targets fail for a reason that is
  not our code, and only if B0's projection still stays at or above 30 GB with its 7.3 GB added (it does today:
  81.2 - 17.7 = 63.5 GB, and the worst case already counts it).
- Nothing is deleted or moved in round 80.

### Free space after round 80

| Start | Typical (8.6) | Like round 74 (14.3) | Worst (17.7) |
|---|---|---|---|
| **With wave 2 (now): 81.2 GB** | 72.6 GB | 66.9 GB | **63.5 GB** |
| Without wave 2 (as at 17:31): 43.2 GB | 34.6 GB | **28.9 GB UNDER** | **25.5 GB UNDER** |

Looking further (estimates): after round 81 (like 74: 14.3 GB) and round 82's full check (up to 14.5 GB, counted
round 76) the worst path ends near 34.7 GB, still over the line; round 86 needs more room (docs/NEXT_STRETCH.md).

### The plain rule

**The engine part starts only if D: free at B0, minus the worst case (17.7 GB), stays at or above 30 GB, that is
at least 47.7 GB free at B0.** Today that holds (81.2 GB). It is measured again before every proof batch (E1 to
S1): a batch that would take D: under 30 GB does not start, and the report says what is left. Robot shots are
kept only for the frames each proof names (every 60 frames inside its window at most); the proofs folder stops
at 8 GB.

## Risks, and what is NOT REACHED until a robot run

Read at the desk with good confidence: AISkip's three values and its four readers, Start skip being native, the
game's own skip-stop rules, the hit roll and its 101 values, the hook points, the settings home. **Not reached
until the robot runs them (sitting 2):**

| Not reached yet | Why it matters | Settled by | If it fails |
|---|---|---|---|
| Every boss line and story scene in an enemy turn sets GameSkip +4 bit 0 or the talk manager | 2x / 4x must drop to 1 for every line | E3 (R7-R9) | add the battle-quote flag (SequenceBattle +600 bit 0); if still not covered, ship 2x only during plain unit moves, or cut 3 |
| Situation +8 / the "player's army" reading (inferred, no writer traced) | the reader must never speed up your turn | E2 (R11) | read the army from the turn's phase field found in R11; repair build B2 |
| Pacing gives the very same game | the "no roll changes" promise | E2 (R5) | a pacing bug is ours: repair build B2; never ship a 2x that differs |
| The PC keeps up at 4x (the AI thinks on a worker thread; battle scenes) | 4x that runs at 2.5x is a broken promise | E2 (R6) | 4x is left out (call 2), 2x stays |
| How a boss quote looks at 4x, under Move and under All | the owner's "never rush a boss line" | E3 (R9) | keep the whole forced fight at 1x |
| Do Move / All / Start change units or dice (frames change, inputs do not) | the help line must be honest; Nuzlocke | E1 (R4) | the help line says it plainly; the port still does not touch them |
| The forecast's screen and pixel place (top screen is an estimate from y = 181), and the way to find the window each frame | True hit must sit next to the right number | A3's first 30 min + T2 | use the proc walk instead of the PC watch |
| The four override masks (0x006D68B0 / 0x006D68A8 force 100, 0x006D6898 / 0x006D68C0 force 0), filled at run time, meaning not traced | when one fires the real chance is 100 or 0 whatever the forecast says | T1 records any frame where they are non-zero | first version shows the curve number; the report names the gap (rare) |
| Staff forecasts and the reflected strike use the same curve; whether their windows show Side +0x30 | True hit on staff forecasts could be wrong | T2 (one staff forecast) | True hit paints only on attack forecasts |
| The Paused window's new scroll area changes a Zakuro window every game shows | a visible change outside Fates | unit test U9 + the owner's one look | the patch message says so |
| No headless picture of the Esc window (round 71's open item) | the Helpers rows are not SEEN by a robot | S1 checks values only | the owner looks once (ok list) |
| Seal of Flames: same battle and AI code (its one code patch is the chapter read, SEAL_OF_FLAMES_PATH.md) | one shared choice | not run unless a Seal recording with an enemy phase fits inside E2's cap | stays "same code, not robot-proven" in the report |
| The known 0xC0000005 burst at a job's first step (round 72) | robot retries cost time | each job may retry once | never more than one relaunch per job |

Notes for the robot: auto.py answers talk with START, and inside an enemy turn START also starts the game's skip.
Because round 80 never changes the Start key, old recordings replay as before; new E1 routes press START on
purpose.

## Your calls (all have a safe default; silence means the default)

| # | Call | Default |
|---|---|---|
| 1 | Do you still want 2x / 4x now that the game's own Move / All and Start exist? | **Yes, built** (your pick, F-057). It is cut 3 if time runs over |
| 2 | 4x on or not | **Offered only if the PC really reaches it:** E2 must show the enemy phase at 4x in at most a third of Normal's time; otherwise the row is Normal / 2x |
| 3 | Nuzlocke: grey the rows out? | **Not greyed.** True hit only shows a number; 2x / 4x plays the same turn faster, like held Tab, which Nuzlocke never greyed. Proof N1 must pass; if it fails, both rows grey out in Nuzlocke |
| 4 | Sound at 2x / 4x | **Quiet while it runs fast, like held Tab**; sound is back for every talk and boss line, because those drop to normal speed. Grok consult at A1 on the fan convention |
| 5 | Should your own Entrust turns speed up? | **No:** your army's turns, Entrust included, stay at normal speed; the game's own Move / All still apply to Entrust |
| 6 | Show True hit as "70 (real 79)"? (yes / no) | **Yes:** whole numbers rounded, "real 100" only when the hit is certain (a shown 98 or 99 shows "real 99"), never "real 0" unless it is 0. At 50 or less the two numbers are the same. (The roadmap's "70 (real 82)" was a guess; the game's rule gives 78.87) |
| 7 | The Start key | **The game's own, untouched**, at every speed (it already skips the rest of the enemy turn). The home part's idea of Start working only at 2x / 4x is dropped: it would change today's game at Normal |
| 8 | One Helpers choice for Fates and Seal of Flames, or one each | **One for both** (same battle code). One each costs about 15 min more (estimate) |
| 9 | Let boss fights play fast but keep their lines at normal speed? (yes / no) | **Yes**, unless E3 shows a quote is cut: then the whole forced fight plays at 1x |

Grok: no consult in the desk part (no network in this run). One consult at the start of sitting 1 (5 min, inside
A1) on calls 4, 6 and 9 and the row words.

## Not in round 80 (on purpose)

- **Writing the game's own AISkip byte** (a row that sets +0xD): it would need the options writer (OPTIONS_WIRING
  W1/W2, F-034) and its robot list. Not needed: you can set it on the game's own Options screen today; the help line
  points there.
- **Changing the game's clock step** for speed: the 60 fps story switch showed a clock change can move the random
  generator (docs/EXTRAS.md section 2), and walking does not use the step.
- **Gold and EXP helpers** (Grok: keep them out of this build).
- **Round 81's "settings for every New Game"**: it reuses this Helpers heading, table and wiring (HOME_DESIGN 4),
  and its new writer group needs your second yes at that round (F-057).
- The F-051 full matrix (round 82), any push, a release tag, any delete or move, any download. Cheat pokes only in the robot's own copies where a proof needs a state (listed in docs/CHEATS.md), never in your saves.

## Hard rules in round 80 (as in every round)

build/STOP_ROUND is checked before every build, game or robot start; every start is headless and self-exiting with
its own data folder and APPDATA / LOCALAPPDATA under build/r80/; at most 6 robot jobs at once; never relaunch a
run more than once; a visible window = a failed run; never start play\game\Fire Emblem Fates.exe; never write
%APPDATA% / %LOCALAPPDATA%, play/config.json, play/state.json, saves or Zakuro settings; no Nintendo or Seal of
Flames bytes in git (the True hit table holds our own computed numbers; the game's sine table is read at run time,
never stored); backups first, staged, installed only after C1 and C2; every process started is listed and
killed before the round returns.
