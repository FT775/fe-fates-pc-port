# Seal of Flames edition plan: two editions in one repo (planning desk, 2026-11-26)

**In one line:** Fates with the randomizer stays the main project ("Vanilla+"); Seal of Flames becomes an optional
edition in its own folders; the program stays one program, and it stops showing Seal to players who did not add it.

**The owner's words (2026-11-26):** "have Seal of Flames an optional version of this project, not built in. So, you can
have a pc port of the project with Seal of Flames or without, but both would include the randomizer built in. So, we can
have a vanilla+ vs a Seal of Flames side project in the git. This allows for the projects to not get too tangled up.
Discuss with grok before acting on any of this to be sure." Then, to Grok's order: "Yes, that order", and "continue
until the reset, try to utilize all of the usage before that time".

**Where this plan sits in that order:** (1) round 82, the full check; (2) round 82b, the Seal + Classic fix (engine
patch 0042, now on disk); (3) **this planning round**; (4) split round A; (5) split round B. Rounds 82 and 82b must be
committed before round A starts. Round numbers for A and B are not fixed yet (likely 83 and 84).

**How this plan was made:** a read-only desk, 2026-11-26 03:08 to 03:30 EST (counted with `date`), then a fix pass
after two reviews, 03:33 to 03:38 EST (counted with `date`). Four
inventories (build/split/INVENTORY_engine.md, INVENTORY_randomizer.md, INVENTORY_harness.md, INVENTORY_docs_tests.md)
and five Grok consults (docs/collab/SEAL_EDITION_SPLIT_GROK.md; build/split/grok_engine.txt, grok_harness.txt,
grok_docs_credits.txt, grok_plan.txt). Nothing was moved, built, run or committed. Facts, paths and ids only: no
Nintendo or Seal of Flames bytes or text. Seal of Flames is Laz14's fan mod (gamebanana.com/mods/656034,
CC BY-NC-ND 4.0). We never ship it. We always credit it.

Every time figure is marked **counted** (measured before, with its source) or **estimate** (F-027).

---

## 0. In plain words (for the owner)

- **One repo, two editions.** "Vanilla+" (Fates + the randomizer + the helpers) is the main one. The Seal of Flames
  edition is the same thing plus Seal. Both have the randomizer. Neither ships Laz14's files.
- **One program.** Both editions run the same game program. Seal's code stays inside it. Players who did not add
  Seal never see it.
- **One small engine change is needed.** Today the "Choose your game" page opens at every start, even with no Seal.
  It shows Seal greyed out with an Install button. Grok's rule was "an engine build only if the page cannot already
  hide Seal". It cannot, so this is that build. It is small: about 25 lines of code and 35 lines of tests (estimate).
- **Seal files move into Seal folders:** `config/seal`, `tools/seal`, `tests/seal`, `docs/seal`. Old reports stay where
  they are.
- **The check gets smaller for Vanilla+:** 3 story paths instead of 4. Seal gets its own small check. It runs when the
  engine or the shared randomizer changes, and before a Seal release.
- **Two rounds do the work.** Round A: the engine change, a test for the release safety check (the check that stops
  any game or mod bytes from going into a zip), Seal data and Seal-only tests. Round B: everything else, then a first
  Vanilla+ zip made as a practice run (not uploaded).
- **How long:** round A about 5 h 30, round B about 5 h 25 (estimates, counted step by step in section 7). Each round
  stops at 7 h, whatever is left.
- **Nothing changes for the player except one thing:** no Seal page when Seal is not installed. Every other move is
  proved "same game" three ways: the seed fingerprints (a test that the same seed still makes the exact same game),
  the smoke check (a quick run of a few chapters by the robot, with no window) and the Randomizer page robot (a robot
  that clicks through the Randomizer page and checks the share codes).
- **Five calls for you** are in section 9. Each has a default, so the rounds can start on "yes".

---

## 1. The owner's request, restated as rules

1. Two editions in one git repo: Vanilla+ and the Seal of Flames edition. Not a second repo, not a long-lived branch
   (Grok: those drift, and Seal becomes the thing we forget).
2. Both editions include the randomizer, built in.
3. Seal is optional: never built into what a Vanilla+ player sees.
4. Not tangled: Seal-only code and data live in Seal folders. Shared code stays shared. A Seal-only fix lives in Seal
   folders. A shared step never gets a Seal-only gate again without its Seal test in the same change (the round 81b
   lesson).

---

## 2. The shape

Grok's shape (docs/collab/SEAL_EDITION_SPLIT_GROK.md, build/split/grok_engine.txt):

- **One repo, two editions.** Vanilla+ is the default. Seal is optional.
- **One program.** The "Choose your game" page appears only when Seal is installed. No build-time switch (that would
  be two programs again).
- **One shared randomizer.** Seal's rules file and Seal-only fixes live in Seal folders. The New Game hook is shared.
- **Seal folders** for config, tools, tests and docs. Seal gets its own small check and its own release notes.

### The exact folder layout after round B

```
(repo root)
  PLAY.bat                          shared
  PLAY SEAL OF FLAMES.bat           Seal edition. Stays at the root (players double-click it). Left out of the Vanilla+ zip.
  CREDITS.md, README.md             shared; the Seal line is worded per edition (section 6)
  Read Me First.txt                 shared; its 55-line Seal block moves to docs/seal/PLAY_SEAL.md, one pointer line stays
  roms/README.txt                   shared
  roms/seal/README.txt              Seal edition (the player's drop folder for the zip). Left out of the Vanilla+ zip.

  config/randomizer/                shared: rules.json, guarantees.json, ... (no Seal file left here)
  config/harness/                   shared: smoke_set.json (6 Fates jobs), smoke_baseline.json, check_paths.json (bt, cq, rv), routes.json ...
  config/release/                   shared: seed_fingerprints.json (all keys, Seal keys included: hashes only), editions.json (NEW: the Vanilla+ leave-out list)
  config/seal/                      Seal edition
    seal_rules.json                 moved from config/randomizer, SAME NAME (the release gate matches "seal*" file names)
    seal_bosses.json                moved from config/randomizer, same name
                                    (the 3 harness files below must NEVER be named seal*: they hold numbers, and the
                                    gate's ids-only rule would fail them; section 8, risk 1)
    smoke_set.json                  the 2 Seal jobs (seal-R011-off, seal-R011-all1), the sealmod input, run seal-all1
    smoke_baseline.json             their 3 baseline entries
    check_paths.json                the Seal path for the small check

  tools/randomizer/                 shared. STAYS at depth 2 (the program finds it there). sources.py keeps
                                    activate(game, mod), the mod layer, merge_rules, load_rules, seal_romfs.
  tools/play/                       shared: play.py, launcher.py, rando.py
    sof.py                          a 5-line stub that runs tools/seal/sof.py (Seal zip only; removed in a later round)
  tools/harness/, tools/release/    shared (check_all and package.py learn --edition; smoke.py's --set already exists)
  tools/paths.py                    shared (find_seal_zip stays: one finder for roms/ and roms/seal)
  tools/seal/                       Seal edition
    sof.py                          the Seal installer and starter, moved from tools/play
    seal_rules.py                   the Seal rules builder, moved out of sources.py (about 350 lines)
    launcher_seal.py                the launcher's Seal row and zip install (from launcher.py)
    play_seal.py                    seal_extras() and backup_seal() (from play.py)

  tests/                            shared; tests with a Seal leg skip with a plain reason when config/seal is missing
  tests/seal/                       Seal edition
    __init__.py, _fixtures.py       _fixtures: FILES, make_zip, facts (moved out of test_sof_path.py FIRST)
    core.txt, heavy.txt             the 2 quick Seal ids and the 1 heavy id
    test_sof_path.py, test_rando_seal.py, test_rando_seal_bosses.py, test_rando_sealfix77.py, test_sources_layer.py   (moved whole)
    test_paths_seal.py, test_launcher_seal.py, test_play_seal.py, test_rando_seal_rules.py                          (carved out of mixed tests)

  docs/                             shared. GAME_PICKER.md stays shared (one program, one page). History docs that
                                    mention Seal (88 files) stay frozen where they are.
  docs/seal/                        Seal edition
    README.md                       front page: credit first, "not included, download it yourself", the history list
    SEAL_OF_FLAMES_PATH.md, RANDOMIZER_SEAL.md, SEAL_BOSSES.md, SEAL_SAVE.md   moved; one-line stub left at each old path
    PLAY_SEAL.md, CHECK.md, RELEASE_NOTES.md                                   new

  engine/zakuro + patches/zakuro/   shared: one program. No patch moves. patches/zakuro/README.md gets an Edition column.
```

Removed (call 4): `tools/sof_rando_off/` (2 files, 55 lines). The player program has not used it since round 58, but
one helper still does: `tools/harness/chapsel.py` (run_one, line 782) points FEF_RANDO_TOOL at it for every
`--game seal` chapter-select job. Round A switches that job to `tools/randomizer` with `FEF_RANDO_GAME=seal`, the way
`smoke.py` (lines 984-987) and `rcheck.py` (line 1634) already do, and proves it with one Seal chapter-select job.
It cannot move under `tools/seal/`: the program finds a randomizer folder exactly two folders below the repo.

Not touched by either round: the player's own files (`play/seal-of-flames/`, `play/launcher.json`,
`play/game-choice.txt`). `play.py` keeps protecting Seal saves in both editions (SEAL_DATA_DIR, NOT_FRESH).
`.gitignore` keeps its Seal lines in both editions (they keep the mod out of git).

---

## 3. The seam in the engine

**We prefer no engine change. The code says one is needed.**

### What the page does today when there is no Seal (read from the code at engine commit c2fa3b7, patch 0042)

1. **The page opens on every windowed start of the Fates program.** `picker_applies()` (crates/zakuro/src/lib.rs
   lines 1103-1112) checks three things only: the program is linked, it is not a test pattern, and the game is Fates
   Special Edition USA. It never asks whether Seal is installed.
2. **The Seal row is always drawn.** With no Seal profile, `seal_status()` (crates/zakuro/src/game_pick.rs line 180)
   says `Missing`. The row is greyed, with our own line telling the player to put the zip in roms\seal and press
   Install (line 170), and an Install button (line 465).
3. **Esc > Switch game is always there.** `apply_choice()` always sets `menus.switch_game` (lib.rs line 1154). With
   no Seal it shows greyed, with a reason.
4. **No flag skips the page.** `--game fates` only pre-selects Fates on the page.
5. **The engine never looks in roms\seal.** It knows only the Seal profile folder. The launcher passes
   `--seal-broken` when an install is damaged, and nothing when there is no profile.
6. **The program has `tools\play\sof.py` written into it.** It finds the port folder by that file (game_pick.rs
   line 297) and runs it for Install (line 304).
7. **Headless runs never open the page.** Every robot, smoke job and check runs headless, so changing the page
   changes no robot path.

### The change: one patch, 0043 (one build; call 1)

A runtime check, keyed on `SealStatus`. No cargo feature. No engine files move.

- **H1. The page only when Seal is there.** Open the page when `picker_applies()` and Seal is `Installed` or
  `Broken`. When Seal is `Missing`, start Fates at once. The rule lives in a small pure function in game_pick.rs
  (for example `page_wanted(applies, &status)`), tested with no window.
- **H2. Switch game only when Seal is there.** `apply_choice()` leaves `switch_game` empty when Seal is `Missing`.
- **H3. A remembered Seal choice with Seal gone.** A saved `seal` choice, or `--game seal` with a window, while Seal
  is `Missing`: start Fates, with one log line. Headless `--game seal` keeps its error exit, as today.
- **H4. The new sof.py home.** The port-folder finder and Install look for `tools\seal\sof.py` first, then
  `tools\play\sof.py`. After H1, Install shows only in the `Broken` (repair) state, which needs a Seal profile, so
  only the Seal edition ever reaches it.
- **H5. A headless proof line.** The headless report (FEF_HEADLESS_REPORT) gains one line: "page: would open" or
  "page: skipped (Seal not installed)". The proof then needs no window (the owner wants no visible windows). If the
  reviewer prefers, H5 can be dropped and the proof is the `page_wanted` unit tests only.
- **Grok on the zip:** leave the zip to the launcher. The engine does not go looking in roms\seal. A zip in roms\seal
  that is not installed yet means no page; the Seal edition's launcher asks and installs.
- **Size (estimate):** about 25 code lines in game_pick.rs and lib.rs, about 35 test lines. The test
  `the_page_preselects_and_greys_seal_of_flames_when_it_cannot_be_chosen` changes on purpose. The check_all row
  `game-picker-page` already says "Seal of Flames shown only when installed"; that text becomes true.
- **Why not a cargo feature:** two programs to build, stage and check. A Vanilla+ program with no Seal strings at all
  is a later release choice (Grok), not daily work.
- **Why no engine code moves:** 14 of the 42 patches touch Seal code (13 of 0001-0041, plus 0042), woven in with later shared patches (0036, 0037,
  0039, 0041, 0042 build on them). Splitting the chain means rewriting old patches: high risk, nothing the player
  sees. Instead `patches/zakuro/README.md` gets an Edition column: Seal-only (0012, 0027), Mixed (0011, 0013, 0018,
  0020, 0021, 0022, 0029, 0041, 0042), Shared-found-on-Seal (0017, 0019, 0023), and 0043 (Mixed).
- **Rule for later engine rounds:** Seal-only engine code goes in game_pick.rs (or a Seal-named module next to it),
  behind `Game::Seal`. The core randomizer takes only the game name (`Config::fates_rando_game`) and never gates a
  shared step on it. A new `Some("seal")` gate in Fates logic needs its Seal test in the same patch.

---

## 4. The randomizer seam

**The randomizer stays one piece.** It already reads "which game" from one switch (`tools/randomizer/sources.py`).

### What moves

| What | From | To | Round |
|---|---|---|---|
| seal_rules.json (844 lines), seal_bosses.json (42 lines) | config/randomizer/ | config/seal/, **same names** | A |
| The Seal rules builder (reachable_chapters, the Seal route and boss consts, chapter_door_events, seal_rolls, seal_guarantees, seal_boss_classes, build_seal_rules, write_seal_rules; about 350 lines) | tools/randomizer/sources.py | tools/seal/seal_rules.py; `sources.py rules` forwards to it, and thin names stay in sources.py for one round | B |
| 4 Seal-only tests (test_rando_seal, test_rando_seal_bosses, test_rando_sealfix77, test_sources_layer) | tests/ | tests/seal/ | A |
| Seal cases inside mixed randomizer tests (guarantees x2, page62b x3, sharecode x2: 76 lines) | tests/ | tests/seal/test_rando_seal_rules.py | B |

### What stays

- `sources.activate(game, mod)`, the mod layer, `merge_rules`, `load_rules`, `seal_romfs`, `check_game`. The program's
  make script runs `import sources; sources.activate(game, mod)` from `tools/randomizer`. Renaming or moving that
  would need an engine build. The page robot also sets `sources.LAYER_TOP` directly.
- `sharecode.py`, untouched. Its game letter (F / S) is part of the code format, mirrored in the program.
- The 24 small Seal branches in 12 other randomizer modules (rando.py, ingame.py, cache.py, chests.py, colours.py,
  recruit.py, guarantees.py ...). They read the rules file or pick the mod's folder first. That is the shared
  randomizer working with a game name, which is what Grok asked for.
- `tools/randomizer` stays at depth 2 below the repo (the program finds the repo two folders above it).

### Fingerprints and share codes: unchanged

- **Seed fingerprints** (`seal/default/1`, `seal/everything-on/1`, and every Fates key) hash the make's output: the
  patch, plan, spoiler and mod folder. They depend on the rules **content**, not on file paths or credit lines. A pure
  move keeps every key. Proof: run `tools/release/fingerprints.py` with the mod installed after each round; every key
  must match. On a machine without Seal the two Seal keys skip with a plain reason.
- **The rules file's `about` line** names the builder's path. Round B keeps that line **word for word**, so the file
  does not change and needs no rebuild. (test_rando_seal checks the file equals `build_seal_rules()` byte for byte.)
- **Share codes** hash row keys, kinds and choices only. Moving Seal files or page rules changes no code. Old Seal
  codes still read.
- **Leave alone:** the fingerprint key R62_IDS mixes both games' round-62 answer sets. Do not split it in these
  rounds (that would change a Fates-side key).
- **Side effect, expected:** any edit to sources.py empties the table cache once (cache.py hashes sources.py). The
  first make after the edit is slower (about 35 s, from the randomizer inventory), then normal.

### Tests

- The test runner (`tools/release/run_tests.py` line 71) only finds `tests/test_*.py`. Round A teaches it
  `tests/seal/test_*.py` (module ids `tests.seal.test_x`). Plain `unittest discover` needs `tests/seal/__init__.py`.
- The 5 tests moved whole set their repo root as "two folders up" (`os.path.dirname(os.path.dirname(...))` in
  test_rando_seal.py line 16, test_rando_seal_bosses.py line 14, test_rando_sealfix77.py line 21,
  test_sources_layer.py line 13; `Path(__file__).resolve().parent.parent` in test_sof_path.py line 30). Under
  `tests/seal/` that points at `tests/`. Round A changes each to three folders up in the same step as the move.
- The shared `tests/test_launcher.py` (line 38) imports the Seal zip fixtures. After round A it imports them from
  `tests/seal/_fixtures.py` inside a guard: when `tests/seal` is absent, its Seal cases skip with a plain reason
  instead of an ImportError.
- The runner becomes edition-aware in round B: when `tests/seal/` is absent, `run_tests` and `--check-lists` skip
  the `tests.seal.*` ids named in `tests/core.txt`, `tests/heavy.txt` and `config/release/test_times.json`, and
  print how many it skipped. Without this the Vanilla+ folder refuses its own lists.
- Names to update with the move: `tests/core.txt` (ids `seal`, `seal-bosses`), `tests/heavy.txt` (Seal five seeds),
  `tools/check_all.py` (3 module ids), `tests/test_check_all.py` fixtures, `config/release/test_times.json` keys.
- About 10 shared randomizer tests loop over `(None, "seal")` or check `grey_for` / `hide_for` "seal". Round B makes
  their Seal legs **skip with a plain reason** when `config/seal/seal_rules.json` is missing, so the Vanilla+ zip
  passes its own tests.
- Vanilla+ asking for Seal (`activate("seal")` with no config/seal) already refuses (sources.py line 400). Round B
  makes the line plain: "The Seal of Flames edition is not installed."

---

## 5. The harness and check split

### The Vanilla+ full check: 3 paths (Birthright, Conquest, Revelation)

Counted from docs/tests/CHECK_R76.md and CHECK_R82_NEW.md:

| Part | Today (4 paths) | Vanilla+ (3 paths) |
|---|---|---|
| Break check jobs | 536 | 372 (bt 164, cq 120, rv 88) |
| Runs remade | 110 | 55 |
| Table cells | 168 | 126 |
| Page robot runs | 8 | 4 |
| Nuzlocke chapter jobs | 4 | 3 |
| check_all rows | 182 | 177 |

Time: round 76's check track took 2 h 42 (counted, REPORT_2027-01-23) for 536 jobs. By the job ratio the Vanilla+
check track is about 1 h 55 (estimate).

The full-check path list becomes tracked config, so a copied driver cannot bring Seal back by habit:
`config/harness/check_paths.json` (bt, cq, rv) and `config/seal/check_paths.json` (seal).

### The small Seal check

Grok's list, confirmed tonight (build/split/grok_plan.txt):

1. **The picker:** the cargo row `game-picker-page` (with 0043's tests) and the page robot's `quick-s` run.
2. **One chapter:** the 2 Seal smoke jobs (`seal-R011-off`, `seal-R011-all1`).
3. **A Classic New Game that starts the seed:** round 82's N4 pair on Seal: Normal + Classic and Normal + Casual,
   same answer, one pick each, run laid, the randomized unit seen on the first map.
4. The 5 Seal check_all rows (`sof-path-tests`, `rando-r64-seal-bosses`, `rando-seal-tests`,
   `engine-seal-person-name`, `engine-seal-person-order`) and the 2 Seal fingerprints.

Size: 5 routes x 2.7 min = 14 min, + 15 min set-up, + about 2 min of unit rows = **about 30 min (estimate)**.

**When it runs** (Grok, build/split/grok_plan.txt; call 5): when the engine changes; when the shared randomizer or
the New Game hook changes; before a Seal-edition release. Not every round. A Fates-only page change does not need it.
Before a Seal-edition release that offers Nuzlocke, also one Seal Nuzlocke chapter. Nuzlocke is not in the small
check itself.

### Smoke, per edition

- **Until 0043 is installed: 8 jobs every round, as today** (Grok: that is how the Classic miss happened).
- **After round A installs 0043, from round B on:** Vanilla+ smoke = 6 jobs (bt, cq, rv x off / all1) + the memory
  compare. Seal smoke = 2 jobs, run as part of the small Seal check.
- `tools/harness/smoke.py` already takes `--set` (line 1351). The real work is a complete second set file:
  `config/seal/smoke_set.json` with its own `fixtures_dir`, `rom`, `inputs` (sealmod), `robot`, `runs` (seal-all1),
  `jobs`, `timeouts` and `lanes`, and the 2 jobs taken out of `config/harness/smoke_set.json`. check_all's smoke-set
  row then requires `PASS: jobs 6/6`, and a new `seal-smoke` row (edition seal) requires 2/2.
  `tests/test_check_all.py` changes with it.
- The memory compare (`mem-off`, randomizer off, the installed program's memory at fixed frames) stays in the
  Vanilla+ set only, by default: it boots Fates, not Seal, so running it twice proves nothing new. Round B writes
  this in docs/seal/CHECK.md; the reviewer may move it.

### check_all, per edition

- Each row gets an `edition` tag: `shared` (default) or `seal` (the 5 rows above, and `seal-smoke` from round B).
- `check_all --edition vanilla` skips Seal rows. `--edition seal` runs only them. The default on the dev machine is
  `all`, so nothing is lost while both editions live here.
- The 2 engine Seal cargo rows guard shared engine code, so the install gate keeps running them in both editions.

### What does not change

- The robot's routes and scripts: 0 Seal routes, 0 Seal lines in `tools/harness/robot/`.
- `chapsel.py`, `rcheck.py`, `pagebot.py`, `smoke.py`: their per-job "game" handling stays (shared). Only paths they
  name follow the moves.

---

## 6. Releases

### Two zips from one commit (call 3)

| | Vanilla+ zip | Seal of Flames edition zip |
|---|---|---|
| Name (Grok: fine) | `FE-Fates-port-<tag>.zip` | `FE-Fates-port-<tag>-seal-edition.zip` |
| Made by | `package.py --edition vanilla`: `git archive` of the commit, leaving out the paths in `config/release/editions.json` | `package.py --edition seal`: today's zip. **No flag = `seal`**, so today's callers and tests keep working |
| Output folder | `<out>/vanilla/`: its own zip, RELEASE_NOTES.md, SHA256SUMS.txt, package.json | `<out>/seal/`: the same four files plus the history bundle |
| Leaves out | `PLAY SEAL OF FLAMES.bat`, `roms/seal/`, `config/seal/`, `tools/seal/`, `tests/seal/`, `docs/seal/`, the `tools/play/sof.py` stub | nothing |
| Gates | archive (leave-out aware: the tracked files missing from the zip must be exactly the leave-out list), zip-reopen, leak, same-file, seal-ids (finds 0 files), credits (wants CREDITS.md's one Seal line; it must stop requiring `roms/seal/README.txt`, which today's `CREDIT_FILES` at package.py line 67 names and the Vanilla+ zip leaves out), privacy-head, sums, plus a new **edition** gate (no left-out path and no `config/**/seal*` file in the zip). bundle-verify, history-paths and privacy-history report "not applicable: no bundle; the Seal-edition run from the same commit checks the history" | today's 11 gates |
| Where it goes | the public snapshot (Grok: the public repo is Vanilla+ only) | private repo only, by default (call 3) |
| History bundle | none (the public repo never gets the bundle anyway) | as today (private) |
| Allowed when | **only after 0043 is installed** (Grok: no zip is called Vanilla+ while the page still shows Seal) | any time |

**What the release tools must learn (round B, step B6).** Today's `package.build()` writes ZIP, BUNDLE, NOTES_NAME,
SUMS_NAME and package.json into one output folder and deletes those files when it starts (package.py lines 684-688;
package.json written at line 899). A second run in the same folder would wipe the first run's notes and sums, and the
public publish needs both. So:
1. **Per-edition output folders** (`<out>/vanilla/`, `<out>/seal/`), so neither run deletes the other's files.
2. **Per-edition gate sets** (the row above). Today's archive gate fails on any tracked file missing from the zip
   (lines 705-707); the Vanilla+ run passes it the leave-out list instead.
3. **A default edition:** no flag = `seal` (today's full zip). `test_package` keeps its current cases and gains
   Vanilla+ ones.
4. **`tools/release/release.py`** (RELEASE.bat FULL, rehearse and push) calls package once today (`s_package`, line
   807). Once 0043 is installed it calls it twice, seal first, then vanilla. Its record, notes check and push step
   read both results; the public-snapshot step takes its files from `<out>/vanilla/` only. `tests/test_release.py`
   gains the two-run cases.

Both zips carry the 88 frozen history docs that mention Seal (facts only, no mod bytes). Grok and the docs inventory
accept that. Every upload still needs the owner's yes for that release.

The other choice, **one zip with an optional Seal folder** (today's zip, page hidden until Seal is installed), is
simpler: one package run instead of two. It goes against Grok's "the public snapshot is Vanilla+ only".

### Credits text per edition

Both editions, every time: the name **Seal of Flames**, the author **Laz14**, the link
**https://gamebanana.com/mods/656034**, the licence **CC BY-NC-ND 4.0**, and **not included**.

- **Vanilla+ (one line only, no install steps; Grok):** in CREDITS.md and the release notes: "Seal of Flames by Laz14
  (https://gamebanana.com/mods/656034, CC BY-NC-ND 4.0) is a separate fan mod. A Seal of Flames edition of this port
  is in the works and is not public yet. The mod is never included." This line follows call 3: if the owner later
  says yes to a public Seal-edition release, "is in the works and is not public yet" becomes where to get it, in that
  release's round. README opens: "Fire Emblem Fates with the port's extras (the randomizer, helpers, options).
  It is not a new story."
- **Seal of Flames edition (leads with the credit):** "Seal of Flames by Laz14 (https://gamebanana.com/mods/656034),
  CC BY-NC-ND 4.0. Not included: download it yourself from GameBanana and put the zip, still zipped, in roms/seal/."
  Then: "This port is not affiliated with or endorsed by Laz14." and "Bugs in the port go to us, not to Laz14." Then
  the licence in plain words: "We never share the mod. Get it from Laz14's page. Do not share a changed copy, and do
  not sell it." (Correction to Grok's wording: CC BY-NC-ND 4.0 does allow sharing an unchanged copy for free with
  credit. It forbids changed copies and selling. We still never share it.) CREDITS.md keeps today's full row.
  roms/seal/README.txt stays as it is.
- **Player-facing names (Grok, build/split/grok_plan.txt):** call the default "Fire Emblem Fates" / "the FE Fates PC
  port", and the other "the FE Fates PC port, Seal of Flames edition". Grok calls "Vanilla+" a lab word. The repo,
  tools and docs keep "Vanilla+" (the owner's word). This is call 2.

### Never shipping Seal

Nothing changes here. The mod is never in git (`.gitignore` keeps `roms/seal/*` and `play/seal-of-flames/`), never in
a zip, and the seal-ids gate keeps checking that Seal data files hold ids only. Its rule (`SEAL_DATA`, package.py
line 70) stays as it is: it already matches `config/seal/seal_rules.json` and `config/seal/seal_bosses.json`. Round A
adds a test proving that **before** any file moves (section 8, risk 1).

---

## 7. The two split rounds

Counting rule (F-027, with F-028's integrate of 60 min): routes x 2.7 min + set-up + desk work + 60 min integrate. Desk
work is an estimate from the inventories (no move round has been done before). Check times marked counted come from
round 74 (run_tests --core 125 s, check_all --core 47 s, smoke 107 s), round 77 / 81b (run_tests --full 5 min,
fingerprints 1 min), round 81b (engine build 191.7 s) and the package runs (29.7 s in build/release/r77, 235.5 s in
build/release/rehearse-20261123-220744; the leak gate is the slow part, 16.4 s to 221.3 s).

Workflows run lanes side by side. Each shared file has one owner lane: `tools/check_all.py`, `tests/core.txt`,
`tests/heavy.txt` and `config/release/test_times.json` belong to the harness lane; in round B, `tools/release/package.py`,
`tools/release/release.py` and `config/release/editions.json` belong to the release lane. Other lanes hand their
lines over at the merge. All proofs run on copies, headless, in the round's own build folder.

### Split round A (likely round 83): the hide, the release gate, Seal data and Seal-only tests

Starts only after rounds 82 and 82b are committed. Engine lane (A1) beside the Python lane (A2-A6).

| Step | Work | Count | Cap |
|---|---|---|---|
| A0 | Start: clock, disk, STOP_ROUND check; re-count with the inventory scripts; re-read engine rows 9-10 after 0042 | 10 min | 15 min |
| A1 | Engine patch 0043 (H1-H5): code + tests 30, review 10, gate (0001-0043 apply, cargo, run_tests --core, fingerprints) 10, build 10 (191.7 s counted, r81b) | 60 min | 1 h 55 |
| A2 | Release gate first: **no change to `SEAL_DATA`** (package.py line 70 already matches `config/seal/seal_*.json`). A test_package case proving `config/seal/seal_rules.json` and `seal_bosses.json` still match, and that `config/seal/smoke_set.json`, `smoke_baseline.json` and `check_paths.json` do not | 10 min | 20 min |
| A3 | check_all: `edition` tag on the 5 Seal rows, `--edition vanilla/seal/all` (default all), test_check_all cases | 30 min | 45 min |
| A4 | seal_rules.json and seal_bosses.json to config/seal (same names); sources.py paths; the test `jl()` helper; check_all text | 20 min | 30 min |
| A5 | tests/seal: `__init__.py`, `_fixtures.py` FIRST; test_launcher's fixture import from `tests.seal._fixtures` inside a guard (Seal cases skip when tests/seal is absent); the 5 Seal-only tests moved, each repo root changed from two folders up to three (section 4); run_tests.py finds tests/seal; ids in core.txt / heavy.txt / check_all / test_times | 70 min | 1 h 40 |
| A6 | Retire tools/sof_rando_off (call 4) with its part of test_sof_path; chapsel.py line 782 switched to `tools/randomizer` + `FEF_RANDO_GAME=seal` (as smoke.py and rcheck.py do); sof.py lines 95 and 525 | 20 min | 30 min |
| A7 | Proofs on the staged program: 15 routes x 2.7 = 41 min + 15 set-up + 10 unit (run_tests --full, check_all --core, fingerprints) | 66 min | 1 h 30 |
| A8 | Install (Claude's step, owner OK via call 1), then core / full / smoke / fingerprints on the installed program | 15 min | 25 min |
| A9 | Integrate: review sheet, docs (docs/seal/CHECK.md first draft, patches README Edition column, GAME_PICKER.md hide rule) | 60 min | 1 h 15 |
| A10 | Report + Claude's commit | 30 min | - |
| | **Counted sum** | **6 h 31** | |
| | **Real time with the 2 lanes side by side** (10 + 150 Python lane + 66 + 15 + 60 + 30) | **5 h 31** | **hard stop 7 h** |

A7's 15 routes: smoke 8 (still 8 in round A); page robot `quick-f`, `quick-s` (2); headless picker boots with no Seal
profile, with Seal installed, with Seal broken (3); Seal Normal + Classic starts the seed, again, because the engine
changed (1); one `--game seal` chapter-select job on the new `tools/randomizer` path (1, from A6; dropped if cut 1 is
taken).

**Proofs ("nothing changed for the player", plus the one intended change):**
- Fingerprints: every key the same, with the mod installed.
- Smoke 8/8, memory compare equal to the baseline.
- The Randomizer page: `quick-f` and `quick-s` pass with the same share codes and runs.
- The picker: no Seal profile = "page: skipped" and no Switch game (the intended change). Seal installed = "page:
  would open" and Switch game set, as today. Seal broken = page opens with the repair line.
- run_tests --full and check_all --core green; the moved tests found and passing under their new ids.
- The Seal chapter-select job passes on `tools/randomizer` (the one path A6 changes).

**Cut order (if past the count):** (1) A6, leave tools/sof_rando_off in place; (2) A3's `--edition` flag, keep the
tags only; (3) H5, prove the hide by unit tests only. **Never cut:** A2 before A4, A1's tests, fingerprints, smoke,
the 3 picker boots.

**Round 83 result (2026-11-26, split round A done; counted with `date`, 04:56 to about 06:10 EST, about 1 h 14 against
the 5 h 31 count):** A0-A10 done, no cuts. Patch 0043 (H1-H5) built once (no repair build) and installed after the
checks: play/game exe 3a471269 (was 7ddae842), boot-server ee5ec22e (same bytes), server_build c782ac79, capture
library 405f2bac unchanged; undo `install.undo('r83')`. Moved with `git mv`: config/seal/seal_rules.json,
seal_bosses.json and 5 tests to tests/seal; tools/sof_rando_off retired; check_all `--edition`. Fingerprints: all 6
keys the same, Seal keys included, before and after every move and after the install. Smoke 8/8 with memory equal
(twice on the staged bytes; memory-only on the installed copy), picker boots skipped / would open / would open, quick-f and quick-s PASS (exact), Seal Classic
one pick, the Seal chapter-select job on tools/randomizer ok, run_tests --full 975 tests (49 under tests.seal) PASS.
Two corrections to this plan's text: "same share codes as round 82" cannot hold (the quick scenario draws a new seed
every run; "exact", laid patch = a fresh make, replaces it), and A7's 3-robot cap was broken once (smoke's default 5
lanes beside the prover's lane; no wrong result; later runs pass `--lanes 2`). Report: docs/REPORT_2027-01-31.md.

### Split round B (likely round 84): the rest of the moves, smoke 6 + 2, editions in the tools, a practice Vanilla+ zip

Starts only after round A's commit, with 0043 installed. Four lanes: randomizer (B1-B2), play + harness (B3, B5),
docs (B4), release (B6). The release lane is its own lane because B6 grew once the two-edition release work was
listed (section 6). CREDITS.md belongs to the docs lane; the release lane's credits gate tests against the exact
lines in section 6.

| Step | Work | Count | Cap |
|---|---|---|---|
| B0 | Start: clock, disk, STOP_ROUND; re-count | 10 min | 15 min |
| B1 | Rules builder to tools/seal/seal_rules.py; thin names left in sources.py; `sources.py rules` forwards; the `about` line kept word for word | 60 min | 1 h 30 |
| B2 | Shared tests' Seal legs skip when config/seal is missing (about 10 files); run_tests and `--check-lists` skip `tests.seal.*` ids when tests/seal is absent, with a printed count (section 4); carve the randomizer Seal cases (guarantees 35, page62b 30, sharecode 11 lines) into tests/seal/test_rando_seal_rules.py | 75 min | 1 h 45 |
| B3 | sof.py to tools/seal (stub left); PLAY SEAL OF FLAMES.bat path; sources.py line 197's player message names tools/seal/sof.py; launcher's Seal block to tools/seal/launcher_seal.py (row shown only when tools/seal exists; this covers the unguarded `import sof` at launcher.py line 445); play.py's seal_extras / backup_seal to tools/seal/play_seal.py (lazy import, covering play.py's `import sof` at line 775 and `sof.backup_profile` at line 1450); their Seal tests carved into tests/seal (test_paths 115, test_launcher 95, test_play 73 lines) | 90 min | 2 h |
| B4 | Docs: 4 Seal-only docs to docs/seal + 4 stubs (SEAL_SAVE.md's stub is required: patches 0018, 0022, 0023 cite it); new README, PLAY_SEAL, CHECK, RELEASE_NOTES; README / Read Me First / CREDITS per edition; trim the 27 in-use mixed docs to pointer lines | 90 min | 2 h |
| B5 | Smoke 6 + 2: a complete config/seal/smoke_set.json (fixtures_dir, rom, inputs, robot, runs, jobs, timeouts, lanes) + its baseline, the 2 jobs out of config/harness/smoke_set.json (smoke.py's `--set` already exists); check_all smoke-set `6/6` + `seal-smoke` row; check_paths.json x 2; test_check_all | 60 min | 1 h 30 |
| B6 | package.py `--edition` with the four items in section 6 (per-edition output folders, per-edition gate sets with the leave-out-aware archive gate, default `seal`, release.py calling package twice); config/release/editions.json; the edition gate; the credits gate per edition; test_package and test_release cases; two practice zips into the round's build folder (no upload, no public snapshot) | 120 min | 2 h 45 |
| B7 | Proofs: 12 routes x 2.7 = 32 min + 15 set-up; unit 14 (run_tests --full on the repo; run_tests --core in a folder unpacked from the Vanilla+ zip; check_all --core --edition vanilla and seal; fingerprints with the mod and in the Vanilla+ folder); 5 for the Vanilla+ folder's `extracted` junction (made, checked, removed); 2 package runs x 4 = 8 (counted: 29.7 s to 235.5 s per run) | 74 min | 1 h 40 |
| B8 | Integrate (4 lanes to merge) | 60 min | 1 h 15 |
| B9 | Report + Claude's commit | 30 min | - |
| | **Counted sum** | **11 h 09** | |
| | **Real time with 4 lanes** (10 + 150 longest lane, play + harness + 74 + 60 + 30) | **5 h 24** | **hard stop 7 h** |

Lane lengths: randomizer 135, play + harness 150, docs 90, release 120 (minutes, estimate).

**The Vanilla+ folder needs the game's extracted data.** `sources.BASE_ROMFS` is `ROOT/extracted/romfs` (sources.py
line 46), and a folder unpacked from the zip has no `extracted/`. Without it every real-data test and every Fates
fingerprint key just skips, which proves nothing. So B7 links the main repo's `extracted/` into the unpacked folder
with a **junction** (`mklink /J`), never a copy, and never links the Seal mod (so the 2 Seal keys skip, as they should).
The junction is removed with `cmd /c rmdir <folder>\extracted` only: a recursive delete through a junction would
delete the real extracted data (section 8, risk 13).

B7's 12 routes: Vanilla+ smoke 6; Seal smoke 2; page robot `quick-f`, `quick-s` (2); Seal Normal + Classic and Normal +
Casual starting the seed (2). Round B changes no engine code, so no install step: the tools run from the repo.

**Proofs:**
- Fingerprints: every key the same with the mod; in the Vanilla+ folder (with the `extracted` junction) the 2 Seal
  keys skip with a plain reason and the Fates keys match.
- Smoke 6/6 + Seal 2/2, memory compare equal.
- The page: `quick-f` and `quick-s` pass, exact (laid patch = fresh make; quick draws a new seed each run).
- The Vanilla+ practice zip: its gate set passes (section 6), the edition gate included; unpacked (with the
  `extracted` junction), its own `run_tests --core` and `--check-lists` pass with Seal tests and Seal ids skipped, not
  failed, and the launcher and play.py import with no `sof`.
- The Seal practice zip: today's 11 gates pass, credits included.
- Both runs' files sit side by side in `<out>/vanilla/` and `<out>/seal/`: each folder has its own notes and
  SHA256SUMS after both runs.
- No file in the Vanilla+ zip holds a strong Seal marker outside the frozen history docs and CREDITS.md / README.md's
  one line (markers: `Seal of Flames`, `Laz14`, `656034`, `seal_rules`, `seal_bosses`, `roms/seal`, `--game seal`,
  `sof.py`; never the bare word "seal").

**Cut order (if past the count):** (1) the trim of the 27 mixed docs (keep the 4 moves, stubs and new docs/seal files;
the trim goes to a later desk); (2) B3's launcher move (keep the block in launcher.py behind an "is the Seal edition
here" check; that check must also cover the `import sof` at launcher.py line 445); (3) the check_paths.json files;
(4) B2's carving (keep the skip rule and the edition-aware runner only). Cut (1) saves desk work but not real time
(the docs lane is not the longest). Cut (2) saves about 30 min of the play + harness lane (estimate), bringing real
time to about 5 h 10 (10 + 135 + 74 + 60 + 30; the randomizer lane, 135 min, becomes the longest). **Never cut:** the Vanilla+ folder test run
(with its junction), the edition-aware runner, fingerprints, smoke, the edition gate, the per-edition output
folders, the credits gate per edition, sof.py moving only with 0043's new path already installed.

**Round 84 result (2026-11-26, split round B done; counted with `date`, 06:14 to about 07:46 EST, about 1 h 32
against the 5 h 24 count, plus a finish part 07:48 to about 08:01, about 13 min):** B0-B9 done, no cuts (the 27-doc
trim, the launcher move, both check_paths.json files and the carving all landed). Four lanes side by side
06:14-06:40 (randomizer 24 min, play + harness 26, docs 13, release 19, against 135 / 150 / 90 / 120 estimated),
gate 06:46-07:09, B7 proofs 07:09-07:21, a repair 07:24-07:36 (the Vanilla+ edition gate named the new helper
tests/_edition.py, which `package.py markers` had not scanned because the file was untracked; both fixed),
integrate 07:37-07:46. Finish part (07:48 onward): the release's smoke step and preflight taught the Seal set, and
these notes corrected. No engine change, build or install. Moved: the rules builder to tools/seal/seal_rules.py
(old names forward for one round; seal_rules.json rebuilt byte for byte), sof.py to tools/seal (stub left), the
launcher's Seal row to tools/seal/launcher_seal.py, play.py's Seal save and extras to tools/seal/play_seal.py, 4 docs
to docs/seal (4 stubs), Seal test cases to tests/seal (now 10 modules). Smoke split 6 + 2
(config/seal/smoke_set.json, `--lanes 2` default). Proofs: fingerprints all 6 keys the same with the mod (5 runs in the repo: gate, proofs, repair, integrate, the last prep); smoke 6/6 memory equal + Seal 2/2, twice; quick-f and quick-s PASS,
exact; Seal Classic + Casual one pick each, run r82n4-5e09d108 as in round 82b; run_tests --full 1023 tests 0 failed
1 skipped; check_all --core --edition vanilla PASS (51); Seal edition rows (check_all --edition seal, not --core): 3
of 3 PASS; hygiene PASS (960 tracked + 17 new files). D: free space was lowest at about 57,000 MB (57,002 at 07:49).
The practice zips (never uploaded) are made from the round's final committed tree; their results are in
docs/REPORT_2027-02-01.md. Known for the owner, not fixed: 4 core tests cannot pass in any unpacked zip folder (they
need engine/ source, build/r62 or a non-linked extracted/). Finish change: tools/release/release.py now runs the
2-job Seal smoke set after the 6-job Vanilla+ set whenever the Seal edition will be packaged, and stops before
packaging, naming the edition, if it fails; its preflight (step 1) also runs `smoke.py --set
config/seal/smoke_set.json check`, so missing or wrong Seal inputs stop the release at step 1, naming the edition
(tests/test_release.py 69/69).
Corrections to this plan's text: (1) `check_all --core --edition seal` can never pass (every Seal row is a unit
duplicate or slow; the check is `--edition seal`); (2) "no strong marker outside the frozen history and the one
credit line" is narrower in the tools: shared-by-design files are named one by one in editions.json with a reason,
and LICENSE's credit line is allowed; (3) CREDITS.md is one shared file, so it carries the one Vanilla+ line and the
full Seal row moved to docs/seal/README.md. Report: docs/REPORT_2027-02-01.md.

### Hard stops (both rounds)

- STOP_ROUND, or any visible window.
- Any fingerprint key changes: stop, put the move back, report. A pure move never changes a key.
- Smoke fails or its memory compare differs.
- D: under 35 GB free (66 GB free at 03:20 today, counted with `df`).
- 7 h real time.
- Any Nintendo or Seal of Flames bytes in a tracked file (the hygiene gate).
- A Vanilla+ zip that holds any left-out path.
- No push, no public snapshot, no release upload: each needs the owner's yes for that release.
- A FAIL found in a part the round did not change is listed for the owner, never fixed in the round.

### After round B

- The first real Vanilla+ release is its own step: a FULL release (round 77's took 83 min, counted) and the owner's
  yes for the upload.
- Later, small, optional: one `sources.roots()` helper for the 4 "mod folder first" copies; the Children-off rule and
  the two page entries as Seal data, so rando.py and ingame.py lose their Seal words; removing the tools/play/sof.py
  stub and the thin names in sources.py. Each changes nothing in the output; fingerprints prove it.

---

## 8. Risks: what could go wrong

1. **The release safety check goes blind, or trips on the wrong files.** `package.py`'s `SEAL_DATA` rule (line 70)
   matches any file under `config/`, at any folder depth, whose name starts with "seal". So `config/seal/seal_rules.json`
   and `config/seal/seal_bosses.json` still match after the move. Two ways to break it: a rename (for example
   `config/seal/rules.json`) would quietly stop the ids-only check; widening the rule to all of `config/seal/**` would
   catch the harness files, and today's smoke set already fails the ids-only rule (a reviewer ran
   `package._seal_problems` on `config/harness/smoke_set.json`: run overlays and memory frames hold plain numbers).
   Fix: keep the `seal_*` names, keep `SEAL_DATA` as it is, never name a harness file `seal*`, and add a test_package
   case (A2) before any move, proving the two rules files match and the three harness files do not.
2. **The program's fixed paths.** The program imports `sources` from `tools/randomizer` and finds the repo two folders
   above it. It also finds the port folder by `tools\play\sof.py`. Fix: sources.py keeps its name, place and
   `activate()`; tools/randomizer stays at depth 2; 0043 (round A) reads `tools\seal\sof.py` first; sof.py moves only
   in round B, with a stub.
3. **Moved files break imports.** `tests/test_launcher.py` line 38 imports from `tests.test_sof_path`; the test runner
   cannot see `tests/seal/`; `unittest discover` needs `__init__.py`; check_all, core.txt, heavy.txt, test_times.json
   and test_check_all name modules by path; the 5 moved tests find the repo "two folders up", which under `tests/seal/`
   is `tests/`. In the Vanilla+ folder the `tests.seal.*` ids and the fixture import are missing. Fix: `_fixtures.py`
   first, the fixture import guarded, the repo root changed to three folders up in the same step as each move, runner
   change in the same step, the edition-aware runner (B2), the full test run and the Vanilla+ folder run as proofs.
4. **Robots' paths.** The routes have no Seal, but the copied full-check drivers in `build/rNN/check` do (24 of round
   76's 40 scripts). A copied driver can bring Seal back into the Vanilla+ check. Fix: the tracked check_paths.json
   files. chapsel.py and rcheck.py name Seal folders that follow the moves; pagebot.py sets `sources.LAYER_TOP` (one
   reason the layer stays in sources.py).
5. **A blind search-and-replace.** "seal" is also Fates' own word: Master Seal, Heart Seal, `battle_seal_effect`,
   `offspring_seal_level`, a "sealed" throne room, the chapter "Black Flames", and a compiler word in the engine's
   jit.rs. 12 docs/tests files, 27 harness lines and 17 randomizer files use it that way. Fix: every check and every
   move uses the strong markers (section 7), never the bare word.
6. **The public snapshot.** A Vanilla+ zip made before 0043 would show a greyed Seal row whose Install button cannot
   find sof.py. Fix: no Vanilla+ zip before 0043 is installed (Grok); the edition gate; the public repo gets Vanilla+
   only, and never the bundle.
7. **Shared tests fail without Seal.** About 10 shared test files run a Seal leg. Fix: skip with a plain reason when
   config/seal is missing (B2), proved by running the tests in a folder unpacked from the Vanilla+ zip.
8. **Seal breaks unseen.** Once Seal leaves the every-round smoke, a shared change could break it (the 81b miss).
   Fix: the small Seal check runs on any engine, shared randomizer or New Game hook change (Grok), and the code rule
   in section 3.
9. **The player's own files.** `play/seal-of-flames/`, `play/launcher.json` and `play/game-choice.txt` are never touched.
   A remembered Seal choice with Seal gone boots Fates (H3), not an error.
10. **Running alongside rounds 82 / 82b.** They are still writing (docs/ROUND82B_PLAN.md, docs/tests/CHECK_R82_NEW.md,
    patch 0042). The counts in the inventories are a 03:1x snapshot. Fix: re-count at A0 and B0 (a few minutes).
11. **Small cache cost.** Each sources.py edit empties the table cache once (the first make about 35 s slower).
12. **Credit wording.** Grok's "do not redistribute" is not what CC BY-NC-ND 4.0 says. Fix: the wording in section 6.
13. **The junction in the Vanilla+ folder.** B7 links `extracted/` into the unpacked folder. A recursive delete of
    that folder would follow the junction and delete the real extracted game data. Fix: remove the junction first
    with `cmd /c rmdir`, check it is gone, then remove the folder.
14. **Two package runs in one folder.** Each run deletes the zip, bundle, notes and sums it finds at start, so a
    second run in the same folder wipes the first. Fix: per-edition output folders (section 6, item 1), proved in B7.

---

## 9. Calls for the owner (each has a default)

| # | Call | Default (what happens on "yes") | Other choice |
|---|---|---|---|
| 1 | **The engine build for the hide (patch 0043, round A).** Without it, every player sees a greyed Seal button at every start. One build, one install, about 25 lines of code (estimate) | **Yes**, in round A | Ride with a later engine round; the Vanilla+ zip waits until then |
| 2 | **Edition names.** Why the default: players may not know what "Vanilla+" means. | Repo, tools and docs say **"Vanilla+"** (your word) and **"Seal of Flames edition"**. Players read "the FE Fates PC port" and "the FE Fates PC port, Seal of Flames edition" (Grok: "Vanilla+" is a lab word) | Players read "Vanilla+" too |
| 3 | **One zip or two.** | **Two zips from the same commit.** `FE-Fates-port-<tag>.zip` (Vanilla+) is the public one. `...-seal-edition.zip` stays private. "Private" is only the default: a public Seal-edition release is its own later yes, and then the Vanilla+ credit line says where to get it | One zip with an optional Seal folder (simpler, but the public project shows Seal) |
| 4 | **Retire the old Seal randomizer stand-in** (`tools/sof_rando_off`, 55 lines; the player program has not used it since round 58, and the one helper still using it, chapsel.py's Seal chapter jobs, moves to the normal randomizer with one proof job; git history keeps it) | **Retire it** in round A | Leave it where it is |
| 5 | **When the small Seal check runs** | Grok's rule: when the engine changes, when the shared randomizer or New Game hook changes, and before a Seal release (plus one Seal Nuzlocke chapter then) | Every round (about 30 min more each round, estimate) |

Decided by default (no answer needed; the written or fan pick, per F-051):
- The launcher's Seal row shows only in the Seal edition. The Vanilla+ launcher says nothing about Seal.
- The 88 history docs stay frozen where they are. `docs/seal/README.md` lists them.
- `docs/GAME_PICKER.md` stays shared. The seed fingerprints file stays in config/release.
- sharecode.py and R62_IDS are not touched. The mod layer stays in sources.py.
- A Vanilla+ player who pastes a Seal share code sees today's "This code is for ..." line.
- A public Seal-edition snapshot is not planned now (Grok: later, its own call; your words "with Seal of Flames or
  without" may mean you want both public someday, and that stays open).
- Every upload, push or public release still waits for your yes.
