# check_all: parallel rows and the row-result cache

`tools/check_all.py` runs every gate of the port (README.md, "Checks"). This page covers the two speed
items the owner approved on 2026-11-13 (docs/collab/SPEED_AGREED.md: **B** parallel check_all, the
planted-bug half of **A** result caches) and round 9's item 1 (one slow pass on integrate).

Both are **off by default**. Without `--jobs`, `--cache` or `--no-cache`, check_all is the serial run it
always was (same table, same JSON, same exit status). Round 9 switches them on in the integrate brief.

## Which pass, when (item 1)

| Who | Command | Why |
|---|---|---|
| Builder, after a change | `python tools/check_all.py --fast` (or the default set) | a fail shows up early |
| Integrate | `python tools/check_all.py --slow` **once** | `--slow` already holds every fast and medium row |
| Never | a fast pass and then a slow pass | repeats every fast row (2,208 s of 4,856 s in round 7) |

Slow stays on integrate (it is the proof); it does not move to nightly.

## Parallel rows: `--jobs N|auto` (item B)

```
python tools/check_all.py --slow --jobs auto      # round 9 integrate
python tools/check_all.py --slow --jobs 3         # at most 3 lanes
```

* **Lanes.** `auto` = the owner's budget (`config/harness/resources.json` `max_parallel_runs`, 6; or
  `FEF_CHECK_ALL_SLOTS`) minus the robot runs going now (running `boot.exe` processes). It is counted
  again every few seconds while check_all runs and never goes below 1, so a 12-run robot session leaves
  check_all one lane and a session that starts mid-run takes its slots back. `--jobs N` is capped the
  same way. If the robot runs cannot be counted, 1 lane.
* **FEF_CHECK_ALL_SLOTS (round 13).** A whole number > 0 replaces `max_parallel_runs` for that shell, up
  or down: `FEF_CHECK_ALL_SLOTS=12 python tools/check_all.py --slow --jobs auto` on an integrate night with
  no long live runs (round 12 ran on the day budget of 6 because it was not set). The `[check-all] lanes:`
  line names the source (`budget 12 (FEF_CHECK_ALL_SLOTS) - 0 robot run(s) = 12 free`); a value that is
  not a whole number > 0 is ignored and named on that line, never dropped silently. The Parallel tests
  clear the variable first, so an integrate shell that exports it does not change their numbers.
* **Order.** Longest first, by the last wall time of each row (`build/check_all_times.json`, merged
  after every run, cache hits and skips excluded; else `build/check_all.json`; else a guess by cost).
* **Priority.** check_all and every row run at below-normal priority (`--priority` to change).
* **Output folders.** Every row already logs to its own `build/check_all/<row>.log`. The tools
  themselves write fixed folders, so rows that share one hold a **lock** and never overlap
  (`PARALLEL_LOCKS` in check_all.py). Found by reading each row's tool:

  | Lock | Rows | Shared |
  |---|---|---|
  | build:code | code-hash, lint, m1-tests, diff-func, gen-headers, extras-verify, readable, rom-rebuild | build/obj, code.bin, fe1.elf, cache/analysis.json |
  | build:rom | rom-rebuild, rom-tests | build/rom/ |
  | build:symbols | symbols, symbols-spotcheck | build/symbols* |
  | build:tables | tables-test, tables-gen, tables-check, tables-rebuild | build/tables/ |
  | build:maps | maps-test, maps-roundtrip | build/maps*/ |
  | build:castle | castle-test, castle-all | build/castle/_test/ (removed by each) |
  | build:assets | assets-bch, assets-portrait | build/assets/ |
  | build:harness | harness-selftest, headless-selftest, h56-selftest, h56-h5, markers/cheats/levelups selftests, cheat-routes | harness.py --selftest removes build/harness/selftest/ |
  | build:parallel | parallel-tests, parallel-smoke | build/parallel/test-*/ |
  | readable:&lt;area&gt; | each X-diff with its X-diff-long; writer-gate + writer-diff + writer-diff-long | build/readable/&lt;area&gt;/ program and plant folder |

* **Alone.** The in-process checks (hygiene-paths, hygiene-leak, py-compile, progress: they share
  check_all's stdout and scan the work tree the other rows write into) and the real robot smoke run
  (parallel-smoke: it times boot.exe side by side) run alone after the others, in row order. A row
  that waits (`after:`) on one of them runs alone too.
* **Weight.** Rows that start their own pool of `cpu_count - 1` workers (assets-arc, assets-bch,
  assets-bchwrite, assets-bchwrite-all) and rom-tests (three 2 GiB images) take two lanes.
* **Report.** The table and `check_all.json` are in row order with the same statuses and notes as a
  serial run; the JSON's `options` gains `"jobs"`. Ctrl-C kills every running row's process tree;
  those rows and the ones not started are `FAIL (INCOMPLETE: interrupted)`.

## Row-result cache: `--cache`, `--no-cache` (item A, planted-bug passes)

```
python tools/check_all.py --slow --no-cache   # the weekly clean run: everything runs, PASSes stored
python tools/check_all.py --slow --cache      # unchanged host tests: CACHED key=<sha256>
python tools/testcache.py status              # entries and the last clean run per row
python tools/testcache.py clear               # drop every entry and the clean record
```

Cached rows (`CACHE_SPECS`): the readable comparisons and their planted-bug passes, stance, triangle,
vein, formula, growth, skill, menu and writer diffs (and each `-long`), and writer-gate. Store:
`build/testcache/` (`--cache-dir`). Every write is a temp file + rename.

**Key** = sha256 over: the row definition (command, env, required/rejected lines, note patterns,
needs); every declared file by sha256 (all of `src/readable/`, `include/readable/`, `tools/readable/`,
`extracted/text.bin` + `code.bin`; the diff scripts walk the whole of `src/readable/`, so it is declared
whole); the host compiler (path, resolved path, `--version`, `-dumpmachine`, sha256 of the binary);
the Python version; the `FE_*` environment; and the harness (sha256 of `tools/check_all.py` and
`tools/testcache.py`).

**Complete or never cached.** Before a row may hit, `tools/testcache.py` proves its declared list
complete; any gap makes the row "uncacheable" (it always runs, the reason is in the JSON):
1. the import closure of the row's script: every non-stdlib module resolves to a declared file
   (following `sys.path.insert` folders, and for library modules only the functions the importer
   uses, e.g. `check.find_cc`);
2. every repository path those reachable lines spell (`os.path.join(ROOT, "src", "readable")`,
   `ROOT / "extracted" / "text.bin"`) lies inside the declared files; a folder must be declared whole;
3. `cc -MM -MG` over every `.c` under the declared source folders names only declared headers (a
   header outside the list, or one it cannot find, fails).

**When a hit is refused:** an entry older than 7 days; no clean run of the row (`--no-cache`) in the
last 7 days; a compiler or harness change since that clean run (all hits refused until the next
`--no-cache`); any key change. Only PASS is stored: FAIL, KNOWN and SKIP always run again. A hit
writes the stored log to `build/check_all/<row>.log` under a `CACHED key=...` line.

**Planted-bug check of the cache itself:** `tests/test_check_all.py RowCache` changes a header the row's
C file includes and proves the next run misses and runs; it also covers a script edit, a row-definition
edit, an `FE_*` variable, a week-old clean run, a harness change, a FAIL never stored, an undeclared
path or header never cached, and that every real `CACHE_SPECS` entry is complete in this repository.

## Measured (2026-11-13, round 8 running)

Measured while round 8's robot agents ran (1 to 5 boot.exe runs going), so `--jobs 3` (a modest N)
and `FEF_ROBOT_JOBS=2`; parallel-smoke (real boot.exe runs) and h56-h5 (loads the live capture library
in place) were skipped in all four runs. Outputs: `build/speed/checks/`.

| Pass | Serial | `--jobs 3` | Verdicts |
|---|---|---|---|
| `--fast` (65 rows, 22 run) | 135 s | 76 s | identical: 0 status differences, notes differ only in timing |
| `--slow` (65 rows, 61 run) | 5,061 s (84 min) | 2,127 s (35 min) | identical: 0 status differences; 2 notes differ because the live tree changed between runs (round 8 packed 3 more saves; files grew 24 KB) |

The `--jobs 3` run dropped itself to 2 lanes and then 1 while 4 and 5 robot runs were going. Both slow
runs had the same 4 FAILs, none from check_all: readable and harness-selftest (round 8's untracked
`src/readable/sheet/` has no registry rows yet), writer-diff (a planted-bug text gone from writer.c
in round 8's edit), parallel-tests (`test_ctrl_break_on_the_command_line` expects 3 children;
`FEF_ROBOT_JOBS=2` allows 2 — it passes without that variable).

**Model for the full N** (serial slow sum 5,060 s, longest row assets-full 831 s, rows run alone 8 s):
at 6 to 8 free lanes the slow pass is about max(831, 5,052 / N) + 8 = **about 14 min** (floor: assets-full),
before contention. It only gets those lanes when no robot session holds them.

**Cache** (real triangle-diff row, planted-bug pass, in a scratch copy of its inputs):

| Run | Wall | Result |
|---|---|---|
| `--no-cache` (clean run, stored) | 230 s | PASS, 18/18 planted bugs caught |
| `--cache` | 2 s | PASS, CACHED key=aecf4733...458f |
| `--cache` after one line added to `src/readable/battle/triangle.h` | 219 s | miss ("no entry for this key"), ran, PASS, stored new key |
| `--cache` again | 2 s | PASS, CACHED key=50c45318...f08fe |

The 17 cached rows took 3,468 s of the 5,060 s serial slow pass. A round that touches nothing under
`src/readable/`, `include/readable/` or `tools/readable/` (and no compiler or harness change) gets them
in about 2 s each; any edit there misses all 17 (the diff scripts walk all of `src/readable/`).

## Round 9 fixes (2026-11-14)

- `python tools/testcache.py selftest` (8 checks): hit at exactly 7 days, refusal one second later for the clean
  run ("weekly clean run due") and for the entry ("entry older than 7 days"), a compiler change, FAIL never stored.
  Planted bugs caught: either age test removed, `>` changed to `>=`, MAX_AGE_S changed. Note: testcache.py is in the
  harness digest, so this edit refuses every cached hit until the next `check_all --no-cache` clean run.
- `run_parallel` lane count outside the shared lock: **not applied** (tools/check_all.py and tests/test_check_all.py
  belong to integrate). The patch is docs/collab/patches/r9-fixes-check_all-lanes.patch (`git apply` checked):
  `lanes()` releases the condition while `lanes_now` runs tasklist (up to 30 s) and takes it back after, plus
  `Parallel.test_lane_count_runs_outside_the_lock` (a counter that sleeps 2 s while a row finishes). Measured on a
  scratch copy: the new test FAILS on today's check_all.py and PASSES with the patch (8 s).
- Rows integrate may add: `build.py --selftest` (22), `fastlook.py --selftest` (32), `testcache.py selftest` (8),
  `h6cache.py --selftest` (15), `offline.py --selftest`, `markers.py --selftest` (40), `splitcfg.py --selftest` (10).

## Round 9 integrate (2026-11-14)

- Applied docs/collab/patches/r9-fixes-check_all-lanes.patch (lane count outside the lock + its test).
- New fast rows: `build-selftest`, `fastlook-selftest`, `splitcfg-selftest`, `offline-selftest`,
  `h6cache-selftest`, `testcache-selftest` (with pass/fail samples in tests/test_check_all.py).
- `robot-routes` also requires the packed saves cq-ch7/rv-ch7/rv-ch8 (round 8, late) and
  bt-ch12/rv-ch9 (round 9).
- `h56-h5` now replays round 9's records (session r9-cap, all 26 real-play routes in one session).
- Lock fix: `assets-full` takes `build:assets` like `assets-portrait` (its portrait stage uses the same
  build/assets/portrait_test folder; the two collided in the first `--slow --jobs auto` run).
- Known collision, not a check_all bug: two `h56.py h5` runs on the same session at the same time
  overwrite each other's replay_*.jsonl in the record folders. Run the integrate's own H5/H6 only
  when check_all's `h56-h5` is not running on that session.

## Round 10 integrate (2026-11-15)

- New rows for the round-10 reader batches (read only): `item-diff` / `item-diff-long`
  (src/readable/item/tests/item_diff.py, 25 functions, 46 planted bugs), `move-diff` / `move-diff-long`
  (move_diff.py, 24 functions, 47 planted bugs), `support-diff` / `support-diff-long` (support_diff.py,
  25 functions, 50 planted bugs). Same rules as `sheet-diff`: 0 mismatches, every planted bug caught, no
  "could not run", fewer than 30 % early give-ups per function. Each has its own lock
  (`readable:item`, `readable:move`, `readable:support`: separate build/readable/<batch>/ folders) and a
  cache spec like the other readable diff rows. Pass/fail samples in tests/test_check_all.py.
- `robot-routes` also requires the packed saves of round 10 (bt-ch13..bt-ch17, rv-ch10..rv-ch14),
  integrate's cq-ch8-clear of round 9 and integrate's cq-ch9-clear of round 10; new test `test_round10_packs_are_required` (each one removed in
  turn must fail the row).
- `h56-h5` now replays round 10's records (session r10-capb: every verified real-play route, 38 in one session, after the cursor_terrain fix).
- First KNOWN entry: `readable-verify` / `item-sell-price-not-run`. Verify tests 0 functions at
  `unit::Item::GetSellPrice` (0x0053AE8C), which `ItemSellMenuItem::GetPrice` falls straight into
  (docs/ITEM.md 6; Grok's review 2026-11-16 #2). The row shows KNOWN, never PASS, and only while the log
  has exactly one problem, this NOT-RUN, and no MISMATCH (tests `KnownFailures`). Remove the entry when
  the classifier explains the fall-through or a route meets the function live.
- `move-diff` failed in the slow pass because `src/readable/move/move_terrain.c` was fixed while the pass
  ran (the live compare's `cursor_terrain` call-list fault, docs/MOVE.md 9; the planted bug for that line
  was moved to the new line). Rerun with the changed rows afterwards.
- `h56-h5` timeout raised from 2 h to 4 h: round 10's records are 2.5 times round 9's (106,426); H5 alone took
  71 min, and the row timed out at 120 min while H6 ran beside it on a copy of the same records.

## Round 11 tools-h6 (2026-11-15)

- New fast row `h6sample-selftest` (tools/harness/h6sample.py --selftest: the H6 sampled mode's block cover, one
  record per input signature, content order, sample folder bytes; pass/fail samples in tests/test_check_all.py).
  `h56-selftest` now also checks the time budget (unjudged mutants not counted, a late file not started) and that an
  h6 run with nothing to mutate is refused; `h6cache-selftest` the sampled-record key (hit and miss).

## Round 11 integrate (2026-11-15 night)

- `robot-routes` also requires round 11's packed saves: bt-ch18..23, cq-ch10..12, rv-ch15..17 (now 50 verified
  real-play routes). cq-ch13 and rv-ch18 are look-ahead chains left `verified: false` when Conquest and Revelation
  were paused (F-025): never checked, never required; the note names them ("paused unverified left out").
- New rows from the round 11 reader batches (both read only, both under one lock each because each test has one
  build folder): `ai-perm-diff` (src/readable/ai/tests/ai_perm_diff.py --plant: 18 functions x 300 cases, 44
  planted bugs), `ai-perm-diff-long` (-n 1500 --seed 7), `battle2-diff` (src/readable/battle2/tests/battle2_diff.py
  --plant: 39 planted bugs), `battle2-diff-long` (-n 1500 --seed 7) and `battle2-shadow-count` (shadow_count.py:
  the predicted tier-2 unmapped-read counts of unit_item_stat_bonus equal the logged ones; skipped when verify's
  battle2 output is not there). The four diff rows are cached like the round 10 reader rows.
- New row `ai-score-parked` (F-025): fails if any `*.c` file is under src/readable/ai_score/ or a row of
  functions.csv / targets.csv names that folder. No ai_score_diff row while the batch is parked.
- Row texts brought up to date: `move-diff` 48 planted bugs (the AI batch added one for ai_terrain_score with
  negative defence), `item-diff` 52 and `support-diff` 56 (round 11 tools-fixes and h6-sharpen added plants).
- tests/test_check_all.py: samples for the five new command rows, round 11 packs and the paused keys, and the
  parked-batch check (74 tests).
- `h56-h5` reads this round's compare records (r10-capb, r11-capn, r11-capo: 166,411 records) with `--no-exact`:
  the per-override exact cover (hours on this many records) is deferred to the weekly run (Grok, integrate review).
  Passed alone 2026-11-16 in 161 s: 205 of 234 met, 0 bad.

## Round 14 integrate (2026-11-16 afternoon; F-028: the slow suite is weekly)

- `robot-routes` also requires bt-ch26-clear (53 verified real-play routes; cq-ch13 and rv-ch18 still named paused,
  left out). New test `test_round14_pack_is_required`.
- New rows from the round 14 reader batches (read only): `equip-use-diff` (src/readable/equip_use/tests/
  equip_use_diff.py --plant: 300 cases, each of the 30 cache guards cold in turn, 39 planted bugs; also fails on "a
  guard was never cold"), `equip-use-diff-s7` (`--seed 7 --plant`, slow), `staff-range-diff` (staff_range_diff.py
  --plant: 3 functions x 300 cases, 36 planted bugs) and `staff-range-diff-long` (-n 1500 --seed 7, slow). Same
  rules as the other reader rows (0 mismatches, every planted bug caught, no "could not run", fewer than 30 % early
  give-ups per function). Locks `readable:equip_use` (the equip test always builds into build/readable/equip_use/,
  whatever the seed, so its two rows must never run together) and `readable:staff_range`; cache specs like the
  other reader rows.
- New fast row `h6three-tests` (tools/harness/test_h6three.py, 15 tests: the three-number report of F-026).
- `h56-h5` reads round 14's compare records: r10-capb, r11-capn, r11-capo, r12-cap-class_change, r12-capn,
  r13-cap-shop_price, r13-capn, r14-cap-equip_use, r14-cap-staff_range, r14-capn (181,029 records). Passed alone in
  91 s: 213 of 245 met, 0 bad.
- tests/test_check_all.py: samples for the five new command rows and the round 14 pack (78 tests OK).
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  37 pass in 50 s; `--only equip-use-diff,equip-use-diff-s7,staff-range-diff,staff-range-diff-long,readable,
  selftest,item-diff,ai-perm-diff,robot-routes,h6three-tests` 10 pass in 14.2 min; `--only h56-h5` pass.
- Left for the weekly slow run (58 rows, last full run round 13): m1-tests, gen-headers (skipped: no
  classes.csv), symbols, tables-test, assets-quick, assets-bch, assets-bchwrite, assets-bchwrite-all, assets-arc,
  assets-portrait, assets-full, maps-test, castle-all, mods-selftest, text-mods, play-tests, engine-selftest,
  harness-selftest, parallel-smoke, stance-diff(-long), triangle-diff(-long), vein-diff(-long), formula-diff(-long),
  growth-diff(-long), skill-diff(-long), menu-diff(-long), sheet-diff(-long), item-diff-long, move-diff(-long),
  support-diff(-long), ai-perm-diff-long, battle2-diff(-long), class-change-diff(-long), weapon-rank-diff(-long),
  shop-price-diff(-long), castle-join-diff(-long), writer-gate, writer-diff(-long), mutate-writer-fake,
  readable-verify, rom-rebuild, rom-tests.

## Round 15 integrate (2026-11-16 evening; F-028: the slow suite is weekly)

- `robot-routes` checks 54 verified real-play routes. bt-ch27 (King Garon) is verified but has **no packed clear
  save on purpose**: the game makes no save after chapter 27 (it goes straight to the Endgame Preparations), and
  the proof's copy 1 save is byte-for-byte bt-ch26-clear. New `NO_CLEAR_SAVE = {"bt-ch27": "bt-ch26-clear"}`: the
  row never asks for bt-ch27-clear, and fails if a `bt-ch27-clear.zip` appears that is byte-identical to
  bt-ch26-clear.zip (a mislabelled copy). No new pack this round. cq-ch13 and rv-ch18 still named paused, left out.
  New test `test_round15_no_clear_save_after_bt_ch27`.
- New rows from the round 15 capability batch (read only, docs/CAPABILITY.md): `capability-diff` (medium;
  capability_diff.py --plant: 3 functions x 300 cases, 35 planted bugs) and `capability-diff-long` (slow; -n 1500
  --seed 7). Same rules as the other reader rows (0 mismatches, every planted bug caught, no "could not run",
  fewer than 30 % early give-ups per function; now 46 of 300). Lock `readable:capability`; cache specs like the
  other reader rows. The batch's own proposal of a looser give-up limit (about 150 per 300) was not needed.
- New fast row `guest-call6-test` (tools/readable/tests/guest_call6_test.py --plant: the two-stack-word guest call
  added to include/readable/fe_guest.h, 10 planted bugs).
- New medium row `look-step4` from the stats step (tools/mods/look_step4.py check: builds mods/LookStep4 from the
  owner's own files into build/look_step4/check/, reads back exactly the planned table and dish cells, installs into
  a scratch Zakuro-style folder there and uninstalls back byte-identical; never %APPDATA%; lock `look_step4`).
- `h56-h5` reads round 15's compare records: the round 14 ten plus r15-cap-capabilityb (the capability batch's
  retry capture) and r15-capn (bt-ch27, every override); r15-cap-capability (before the fix) is left out. Passed
  alone in 74 s: 215 of 248 met, 185,316 records, 0 bad.
- tests/test_check_all.py: samples for the four new command rows and the no-save rule (79 tests OK).
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **38 pass** in 41 s (guest-call6-test and robot-routes among them); `--only capability-diff,capability-diff-long,
  look-step4,readable,selftest,sheet-diff` **6 pass** in 9.7 min (sheet-diff 9 min 42 s, the long pole: the
  capability reader now runs sheet's `unit_max_hp` directly); `--only h56-h5` pass.
- **Note [high]:** include/readable/fe_guest.h changed (guest_call6 added, no existing line changed). Every reader
  includes it. The `readable` row compiled all 50 sources and passed its host checks with it, and guest_call5_test
  passed in the batch step; the other reader diff rows were not rerun tonight and wait for the weekly run.
- Left for the weekly slow run (62 rows): m1-tests, symbols, tables-test, assets-quick, assets-bch,
  assets-bchwrite, assets-bchwrite-all, assets-arc, assets-portrait, assets-full, maps-test, castle-all,
  mods-selftest, text-mods, play-tests, engine-selftest, harness-selftest, parallel-smoke, stance-diff(-long),
  triangle-diff(-long), vein-diff(-long), formula-diff(-long), growth-diff(-long), skill-diff(-long),
  menu-diff(-long), sheet-diff-long, item-diff(-long), move-diff(-long), support-diff(-long), ai-perm-diff(-long),
  battle2-diff(-long), class-change-diff(-long), weapon-rank-diff(-long), shop-price-diff(-long),
  castle-join-diff(-long), equip-use-diff, equip-use-diff-s7, staff-range-diff(-long), writer-gate,
  writer-diff(-long), mutate-writer-fake, readable-verify, rom-rebuild, rom-tests. (gen-headers is skipped as
  always: no classes.csv.)

## Round 16 integrate (2026-11-16 night; F-028: the slow suite is weekly)

- `robot-routes` still checks 54 verified real-play routes (paused cq-ch13 and rv-ch18 left out; bt-ch27 no clear
  save by design). **bt-endgame was not added to `NO_CLEAR_SAVE`**: the round's Endgame play did not beat the boss,
  so no `bt-endgame` route key exists, and whether the game offers a save after Endgame is still unknown. Add it
  (with the save its chain starts from, bt-ch26-clear) in the round that writes and proves the route, and only if
  that round finds no save.
- New rows from the round 16 shop buy-list batch (read only, docs/SHOP_GREY.md): `shop-grey-diff` (medium;
  shop_grey_diff.py --plant: 3 functions x 300 cases, 37 planted bugs) and `shop-grey-diff-long` (slow; -n 1500
  --seed 7, 4,500 cases). Same rules as the other reader rows (0 mismatches, every planted bug caught, no "could not
  run", fewer than 30 % early give-ups per function). Lock `readable:shop_grey`; cache specs like the other reader
  rows.
- New rows from the looks step: `look-text` (fast, about 1 s; tools/mods/look_text.py check: builds mods/LookText,
  one English name label Jakob -> Jacques, reads it back, scratch install/uninstall byte-identical; lock
  `look_text`) and `look-portrait` (medium, about 35 s; tools/mods/look_portrait.py check: Jakob's 7 expressions get
  Felicia's pictures, decoded again, scratch install/uninstall byte-identical; lock `look_portrait`). Both require
  `CHECK PASS` and `uninstall back byte-identical: OK`; never %APPDATA%.
- **Fix [high]:** look-portrait's first note quoted the built file names, which are Japanese; check_all printing that
  note to a cp1252 console (stdout redirected to a file) raised UnicodeEncodeError and stopped the touched-rows run
  after 7 rows had passed. The row's note is now ASCII (file count plus the uninstall line). The general weakness
  (check_all prints notes in the console's code page) is not changed; other rows keep ASCII notes.
- `h56-h5` reads round 16's compare records: the round 15 twelve plus r16-cap-shop_grey (the batch's own capture,
  5 real-play shop routes). The capture session held one cheat run (cheat-forge-katana); offline.py and h56.py refuse
  a session that mixes the two tracks (F-019), so integrate moved that run and its stage0 folder to
  `build/parallel/r16-capc-shop_grey/` (a MOVED.txt in each folder says so). Passed alone in 74 s: 217 of 251 met,
  185,561 records, 0 bad.
- tests/test_check_all.py: samples for the four new command rows (79 tests OK, twice: before and after the note fix).
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **39 pass** in 43 s (look-text, robot-routes, gen-stubs-check with 251 overrides among them); `--only
  shop-grey-diff,shop-grey-diff-long,look-portrait,readable,selftest,mods-selftest,text-mods,harness-selftest`
  **7 pass**, then the crash above; `--only look-portrait` after the fix **pass** (32 s); `--only h56-h5` **pass**.
  readable was the long pole (2 min 54 s).
- Left for the weekly slow run (63 rows): m1-tests, symbols, tables-test, assets-quick, assets-bch, assets-bchwrite,
  assets-bchwrite-all, assets-arc, assets-portrait, assets-full, maps-test, castle-all, play-tests, engine-selftest,
  parallel-smoke, stance-diff(-long), triangle-diff(-long), vein-diff(-long), formula-diff(-long),
  growth-diff(-long), skill-diff(-long), menu-diff(-long), sheet-diff(-long), item-diff(-long), move-diff(-long),
  support-diff(-long), ai-perm-diff(-long), battle2-diff(-long), class-change-diff(-long),
  weapon-rank-diff(-long), shop-price-diff(-long), castle-join-diff(-long), equip-use-diff, equip-use-diff-s7,
  staff-range-diff(-long), capability-diff(-long), look-step4, writer-gate, writer-diff(-long),
  mutate-writer-fake, readable-verify, rom-rebuild, rom-tests. (gen-headers is skipped as always: no classes.csv.)

## Round 17 integrate (2026-11-17 night; F-028: the slow suite is weekly)

- `robot-routes` is unchanged: 54 verified real-play routes (paused cq-ch13 and rv-ch18 left out; bt-ch27 no clear
  save by design). **bt-endgame was not added**: round 17's Endgame try (chain cf, docs/ROBOT.md 3w-2) did not beat
  the boss, so there is still no `bt-endgame` route key and nothing proven. `NO_CLEAR_SAVE` stays
  `{"bt-ch27": "bt-ch26-clear"}`.
- New rows from round 17's host-test step (tests only; no reader code changed), in the shop-price-diff style, needs
  `rom:code` and `host-cc`:
  - `ai-value-diff` (medium; src/readable/ai/tests/ai_value_diff.py --plant: ai_value.c and ai_think.c, 8 functions
    x 300 cases, 18 planted bugs) and `ai-value-diff-long` (slow; -n 1500 --seed 7, 12,000 cases). Lock
    `readable:ai_value`.
  - `flags-diff` (medium; src/readable/event/tests/flags_diff.py --plant: 300 cases, 7 planted bugs) and
    `flags-diff-long` (slow; 1,500 cases). Lock `readable:flags`.
  - `forces-diff` (medium; src/readable/unit/tests/forces_diff.py --plant: 3 functions x 300 cases, 14 planted bugs)
    and `forces-diff-long` (slow; 4,500 cases). Lock `readable:forces`.
  - Same rules as the other reader rows: 0 mismatches, every planted bug caught, no "could not run", no
    Traceback, no FAILED/SKIPPED line. The early-give-up limits of the other rows are kept too (these scripts already
    count give-ups as failures, so the limit never decides alone).
  - **Not cached [high]:** the three scripts share src/readable/battle/tests/leaf_diff.py, which puts sheet/tests and
    tools/readable on sys.path in a loop, and tools/readable/check.py in turn reads config/ and extracted/romfs. The
    cache's import scan cannot see all of that, so it marks the six rows "uncacheable" and simply runs them (about
    25 to 60 s each). Declaring those inputs was tried and dropped: the closure reaches extracted/romfs. A verdict is
    never changed by this.
  - Known weak spot, not a row failure: flags_diff.py can report a false mismatch on other seeds (seed 424242, -n 400:
    one case where the case maker sends an "unmapped" pointer into text.bin, which arm_mini maps and the C driver
    does not). The rows use the default seed and seed 7, which do not hit it. Fix belongs in the test's case maker.
- tests/test_check_all.py: the three new pairs added to the generated reader-row samples (79 tests OK, run three
  times: after the rows, and twice after the cache trial was undone).
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **39 pass** in 44 s; `--only ai-value-diff,ai-value-diff-long,flags-diff,flags-diff-long,forces-diff,
  forces-diff-long,selftest,h6three-tests,castle-join-diff` **9 pass** in 2 min 13 s (18/18, 7/7 and 14/14 planted
  bugs caught; 12,000, 1,500 and 4,500 long cases with 0 mismatches; castle-join-diff came along by mistake for a
  test_h6three row and passed, 20/20); `--only readable` (src/readable gained three test scripts) **pass** in 1 min 44 s (host test 146/146);
  `--only h56-h5` **pass** in 1 min 13 s (217 of 251 met, 185,561 records, 0 bad).
- Left for the weekly slow run (69 rows): m1-tests, symbols, tables-test, assets-quick, assets-bch, assets-bchwrite,
  assets-bchwrite-all, assets-arc, assets-portrait, assets-full, maps-test, castle-all, mods-selftest, text-mods,
  play-tests, engine-selftest, harness-selftest, parallel-smoke, stance-diff(-long), triangle-diff(-long),
  vein-diff(-long), formula-diff(-long), growth-diff(-long), skill-diff(-long), menu-diff(-long), sheet-diff(-long),
  item-diff(-long), move-diff(-long), support-diff(-long), ai-perm-diff(-long), battle2-diff(-long),
  class-change-diff(-long), weapon-rank-diff(-long), shop-price-diff(-long), castle-join-diff-long, equip-use-diff,
  equip-use-diff-s7, staff-range-diff(-long), capability-diff(-long), shop-grey-diff(-long), look-step4,
  look-portrait, writer-gate, writer-diff(-long), mutate-writer-fake, readable-verify, rom-rebuild, rom-tests.
  (gen-headers is skipped as always: no classes.csv.)

## Round 18 integrate (2026-11-17 early morning; F-028: the slow suite is weekly)

- `robot-routes` is unchanged: 54 verified real-play routes (paused cq-ch13 and rv-ch18 left out; bt-ch27 no clear
  save by design). **bt-endgame was not added**: round 18's third Endgame try (chain ch, docs/ROBOT.md 3x) did not
  beat Garon, so there is still no `bt-endgame` route key and nothing proven. `NO_CLEAR_SAVE` stays
  `{"bt-ch27": "bt-ch26-clear"}`.
- New rows from the round 18 weapon-rank line batch (read only, docs/WEAPON_LEVEL_VIEW.md; REWRITE_ORDER3 row 6):
  `weapon-level-view-diff` (medium; weapon_level_view_diff.py --plant: 300 cases, 22 planted bugs, about 30 s) and
  `weapon-level-view-diff-long` (slow; -n 1500 --seed 7, about 20 s). Same rules as the other reader rows (0
  mismatches, every planted bug caught, no "could not run", no Traceback, no FAILED/SKIPPED line; the script allows
  no early give-up at all, the usual 30 % give-up reject is kept for uniformity). Lock `readable:weapon_level_view`.
  The script borrows leaf_diff (like round 17's three), so the cache marks the rows uncacheable and runs them.
- New rows from the round 18 test-tools step (tests only, no reader code changed):
  - `h6host-test` (fast, about 4 s; tools/harness/test_h6host.py, 4 tests: the time limit reaches borrowed test
    modules). Requires `Ran N tests` and a bare `OK` line, so a skipped test (`OK (skipped=1)`) fails the row.
  - `flags-diff-s424242` (medium, about 13 s; flags_diff.py -n 400 --seed 424242): round 17's false-mismatch seed,
    kept as a regression row now that the case maker is fixed. Lock `readable:flags`.
  - `ai-perm-diff`: text now says 48 planted bugs (was 44) and names the two new test rules (a cold IsMagic /
    GetRangeO guard is a nested give-up; heal-rod give-ups with warm caches count). The require pattern did not
    change (it reads N/N).
- `h56-h5` now also reads r18-cap-weapon_level_view (the batch's own capture on 6 Birthright routes): 14 sessions.
- **Fix [high], found while writing the rows:** an edit made with a non-raw Python string turned `\1` and `\b` in
  the new patterns into control characters (0x01, 0x08). Caught by reading the row back before any run; replaced
  with the real backslashes, and `grep -c` for both bytes is 0 in tools/check_all.py. tests/test_check_all.py
  would not have caught the 0x08 in a reject pattern on its own, so check new rows by eye.
- tests/test_check_all.py: weapon_level_view added to the generated reader-row pairs; samples for h6host-test and
  flags-diff-s424242; ai_perm sample says 48. 79 tests OK (1 skipped, as before).
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **40 pass** in 41 s (h6host-test 4 s, robot-routes 54 routes, gen-stubs-check 252 overrides among them);
  `--only ai-perm-diff,ai-perm-diff-long,weapon-level-view-diff,weapon-level-view-diff-long,flags-diff,
  flags-diff-long,flags-diff-s424242,readable` **8 pass** in 14 min 9 s (ai-perm-diff 11 min 32 s: 5,400 cases, 0
  mismatches, 48/48; ai-perm-diff-long 2 min 30 s: 27,000 cases; weapon-level-view 22/22 and 1,500 long cases;
  flags 7/7, 1,500 long, and seed 424242 400 cases, all 0 mismatches; readable host test 146/146, 2 min 19 s);
  `--only h56-h5` **pass** in 1 min 10 s (218 of 252 met, 185,654 records, 0 bad).
- Left for the weekly slow run (72 rows): m1-tests, symbols, tables-test, assets-quick, assets-bch, assets-bchwrite,
  assets-bchwrite-all, assets-arc, assets-portrait, assets-full, maps-test, castle-all, mods-selftest, text-mods,
  play-tests, engine-selftest, harness-selftest, parallel-smoke, selftest, stance-diff(-long), triangle-diff(-long),
  vein-diff(-long), formula-diff(-long), growth-diff(-long), skill-diff(-long), menu-diff(-long),
  sheet-diff(-long), item-diff(-long), move-diff(-long), support-diff(-long), battle2-diff(-long),
  class-change-diff(-long), weapon-rank-diff(-long), shop-price-diff(-long), castle-join-diff(-long),
  equip-use-diff, equip-use-diff-s7, staff-range-diff(-long), capability-diff(-long), shop-grey-diff(-long),
  ai-value-diff(-long), forces-diff(-long), look-step4, look-portrait, writer-gate, writer-diff(-long),
  mutate-writer-fake, readable-verify, rom-rebuild, rom-tests. (gen-headers is skipped as always: no classes.csv.)

## Round 19 (2026-11-17 afternoon): Birthright Endgame on the cheat track joins the cheat-route checks

- New fast row **`cheat-endgame`** (F-030): `check_cheat_endgame` reads config/harness/routes.json and markers.json.
  For each route of the new table `CHEAT_NO_CLEAR_SAVE = {"cheat-bt-endgame": "bt-ch26-clear"}` it FAILs unless
  the route exists, says `"cheat": true`, declares at least one poke, starts from bt-ch26-clear and has checkpoints;
  and it FAILs if build/harness/saves/cheat-bt-endgame-clear.zip exists, because the game makes no save after
  Endgame (it runs through the ending to the title screen; the proof's savedata stayed byte-for-byte bt-ch26-clear).
  This is bt-ch27's `NO_CLEAR_SAVE` idea on the cheat side. The note says whether the route is verified, and names
  the real-play key bt-endgame as unwritten while it is (F-030). cq-ch13 and rv-ch18 are not in the table.
- `cheat-routes` (cheats.py --check) now covers 5 cheat routes, cheat-bt-endgame among them; `robot-routes` is
  unchanged in code (it counts 55 verified real-play routes now, because round 20 set rv-ch18 verified; cq-ch13 is
  still named paused).
- tests/test_check_all.py: new class `CheatEndgame` (4 tests: the table and row, unverified and verified both pass,
  a clear save is refused, five planted problems fail). 83 tests OK (1 skipped, as before).
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **41 pass** in 46 s; `--only selftest,cheat-endgame,cheat-routes,robot-routes` **4 pass** in 58 s (selftest 57 s);
  `--only h56-h5` **pass** in 1 min 35 s (218 of 254 met: the two new rows of another area's batch in progress,
  strike_power and who_holds_can_equip_subkind, count as never met; 185,654 records, 0 bad). After
  cheat-bt-endgame was set verified: cheat-endgame PASS ("verified: cheat-bt-endgame").
- Left for the weekly slow run (79 rows; round 18's eight touched rows are back in the list): m1-tests, symbols,
  tables-test, assets-quick, assets-bch, assets-bchwrite, assets-bchwrite-all, assets-arc, assets-portrait,
  assets-full, maps-test, castle-all, mods-selftest, text-mods, play-tests, engine-selftest, readable,
  harness-selftest, parallel-smoke, stance-diff(-long), triangle-diff(-long), vein-diff(-long), formula-diff(-long),
  growth-diff(-long), skill-diff(-long), menu-diff(-long), sheet-diff(-long), item-diff(-long), move-diff(-long),
  support-diff(-long), ai-perm-diff(-long), battle2-diff(-long), class-change-diff(-long), weapon-rank-diff(-long),
  shop-price-diff(-long), castle-join-diff(-long), equip-use-diff, equip-use-diff-s7, staff-range-diff(-long),
  capability-diff(-long), shop-grey-diff(-long), ai-value-diff(-long), flags-diff(-long), flags-diff-s424242,
  forces-diff(-long), weapon-level-view-diff(-long), look-step4, look-portrait, writer-gate, writer-diff(-long),
  mutate-writer-fake, readable-verify, rom-rebuild, rom-tests. (gen-headers is skipped as always: no classes.csv.)

## Round 21 integrate (2026-11-17 evening; F-028: the slow suite is weekly)

- New rows from the round 21 reader batches (read only; docs/tracks/REWRITE_ORDER4.md rows 1 and 2):
  - `strike-diff` (medium; strike_diff.py --plant: 300 cases, 35 planted bugs, about 45 s) and `strike-diff-long`
    (slow; -n 1500 --seed 7, about 23 s). Lock `readable:strike`. The script allows an early give-up only just before
    a getter whose own caches are cold (68 to 78 per 1,500 cases so far), so the long row rejects 200 or more early
    give-ups (not the usual 450), and the short row the usual 90 or more.
  - `who-holds-diff` (medium; who_holds_diff.py --plant: 300 cases, 24 planted bugs, about 39 s) and
    `who-holds-diff-long` (slow; -n 1500 --seed 7, about 14 s). Lock `readable:who_holds`. The script allows no early
    give-up at all, so both rows reject any "N early give-ups" line.
  - Same other rules as the reader rows: 0 mismatches, every planted bug caught, no "could not run", no Traceback,
    no FAILED/SKIPPED line. Both scripts are cached on their own source, like the other readable rows.
- `h56-h5` now also reads r21-cap-strike (bt-ch2) and r21-cap-who_holds (6 Birthright routes): 16 sessions.
- The same control-character slip as round 18 (`\1`, `\b` turned into 0x01, 0x08 by an escaping step) happened
  again while writing the rows; it was caught by reading the rows back before any run and fixed; both bytes now
  count 0 in tools/check_all.py. Write new patterns from a file, never through an escaping heredoc.
- tests/test_check_all.py: strike added to the generated reader-row pairs; who-holds-diff(-long) have their own
  samples (the generated sample's "3 early give-ups" is a FAIL for who_holds). 83 tests OK (1 skipped, as before).
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **41 pass** in 41 s (robot-routes 56 routes: round 20's rv-ch19 is verified now; gen-stubs-check 254 overrides);
  `--only strike-diff,strike-diff-long,who-holds-diff,who-holds-diff-long,stance-diff,readable` **6 pass** in 2 min
  26 s (strike 35/35 and 1,500 long, who_holds 24/24 and 1,500 long, stance 5,600 cases: the stance row is in
  because its registry row 0x005253A8 became strike_power; readable 146/146); `--only h56-h5` **pass** in 1 min 19 s
  (220 of 254 met, 185,812 records, 0 bad).
- Left for the weekly slow run (78 rows): m1-tests, symbols, tables-test, assets-quick, assets-bch, assets-bchwrite,
  assets-bchwrite-all, assets-arc, assets-portrait, assets-full, maps-test, castle-all, mods-selftest, text-mods,
  play-tests, engine-selftest, harness-selftest, parallel-smoke, selftest, stance-diff-long, triangle-diff(-long),
  vein-diff(-long), formula-diff(-long), growth-diff(-long), skill-diff(-long), menu-diff(-long), sheet-diff(-long),
  item-diff(-long), move-diff(-long), support-diff(-long), ai-perm-diff(-long), battle2-diff(-long),
  class-change-diff(-long), weapon-rank-diff(-long), shop-price-diff(-long), castle-join-diff(-long),
  equip-use-diff, equip-use-diff-s7, staff-range-diff(-long), capability-diff(-long), shop-grey-diff(-long),
  ai-value-diff(-long), flags-diff(-long), flags-diff-s424242, forces-diff(-long), weapon-level-view-diff(-long),
  look-step4, look-portrait, writer-gate, writer-diff(-long), mutate-writer-fake, readable-verify, rom-rebuild,
  rom-tests. (gen-headers is skipped as always: no classes.csv.)

## Round 20 integrate (2026-11-17 evening; F-028: the slow suite is weekly)

- `robot-routes` (F-031: Conquest and Revelation resumed): ROUND8_PACKS now also requires cq-ch13-clear,
  cq-ch14-clear, cq-ch15-clear, rv-ch18-clear, rv-ch19-clear and rv-ch20-clear (all six proven this round with two
  equal copies and packed). The old `PAUSED_F025` list is gone: the note now names every unverified cq-/rv- key
  ("unverified cq-/rv- key(s) left out: ..."), so the next unproven chain stays out and is shown. Today: 60
  verified real-play routes, none left out.
- tests/test_check_all.py: the five old asserts "cq-ch13-clear / rv-ch18-clear are not packs" removed (they are
  now); the round 11 test reads the new note; a new test requires each of the six round 20 packs and checks that
  an unverified rv-ch21 is left out and named. 84 tests OK (1 skipped, as before). Written from a file, no
  escaping step: 0x01 and 0x08 count 0 in both files.
- `h56-h5` unchanged (16 sessions). r20-cap-new (the six new routes, every override) is not added yet: it holds
  two strike_power call-list records on cq-ch13 that differ only live (offline they match), so the row would fail
  on "offline != live". Add it after the strike_power fix and a clean recapture.
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **41 pass** in 2 min 15 s (one lane: seven robot runs held the rest; gen-stubs-check 257 overrides, 3 of them
  round 22's); `--only selftest,robot-routes,cheat-endgame` **3 pass** in 1 min 16 s; `--only h56-h5` **pass** in
  1 min 27 s (220 of 257 met, 185,812 records, 0 bad).
- Left for the weekly slow run (round 21's list; selftest ran here): m1-tests, symbols, tables-test, assets-quick,
  assets-bch, assets-bchwrite, assets-bchwrite-all, assets-arc, assets-portrait, assets-full, maps-test,
  castle-all, mods-selftest, text-mods, play-tests, engine-selftest, harness-selftest, parallel-smoke,
  stance-diff(-long), triangle-diff(-long), vein-diff(-long), formula-diff(-long), growth-diff(-long),
  skill-diff(-long), menu-diff(-long), sheet-diff(-long), item-diff(-long), move-diff(-long), support-diff(-long),
  ai-perm-diff(-long), battle2-diff(-long), class-change-diff(-long), weapon-rank-diff(-long),
  shop-price-diff(-long), castle-join-diff(-long), equip-use-diff, equip-use-diff-s7, staff-range-diff(-long),
  capability-diff(-long), shop-grey-diff(-long), ai-value-diff(-long), flags-diff(-long), flags-diff-s424242,
  forces-diff(-long), weapon-level-view-diff(-long), strike-diff(-long), who-holds-diff(-long), look-step4,
  look-portrait, writer-gate, writer-diff(-long), mutate-writer-fake, readable-verify, rom-rebuild, rom-tests.

### Round 20 fix step (2026-11-17, 19:18 to about 20:20)

- `h56-h5` now also holds **r20-cap-newb** (19 sessions): round 20's six new Conquest/Revelation routes, every
  override, captured again after the GetAttack argument fix (src/readable/battle/formula_unit.c: the bool entries
  pass `FE_ARG(2)` plainly, so capture compares r0-r2 only; docs/ROBOT.md "Round 20 fix step"). r20-cap-new, with
  its two strike_power call-list records on cq-ch13, is left out. `--only h56-h5`: **PASS** in 1 min 42 s (223 of
  257 met, 209,460 records, 0 bad, offline != live 0).
- Touched rows: `--only selftest,robot-routes,formula-diff,cheat-endgame` **4 pass** (formula-diff 8 min 18 s:
  7,100 cases, 0 mismatches, 31/31 planted bugs caught; selftest 84 tests OK). `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`: **41 pass**
  (90 skipped as slow/medium) in about 1 min 40 s.
- formula-diff-long joins the weekly list as before (formula_unit.c changed this round).

## Round 22 integrate (2026-11-17 evening; F-028: the slow suite is weekly)

- New rows from the round 22 reader batches (read only; docs/tracks/REWRITE_ORDER4.md rows 3 and 4):
  - `female-diff` (medium; female_diff.py --plant: 600 cases, 19 planted bugs, about 40 s) and `female-diff-long`
    (slow; -n 1500 --seed 7: 3,000 cases, about 30 s). Lock `readable:female`.
  - `rod-target-diff` (medium; rod_target_diff.py --plant: 300 cases, 42 planted bugs, about 60 s) and
    `rod-target-diff-long` (slow; -n 1500 --seed 7, about 25 s). Lock `readable:rod_target`.
  - Neither script allows an early give-up (a cold one-time cache gives up at entry on both sides and is counted
    apart as "cold"), so all four rows reject any "N early give-ups" line. Same other rules as the reader rows:
    0 mismatches, every planted bug caught, no "could not run", no Traceback, no FAILED/SKIPPED line. Cached on
    their own source.
- `readable-verify` KNOWN: a second entry `rod-target-not-run` (verify's sampler cannot name Rod::CanUseTarget,
  0x0034AC30: 0 functions in both passes). Both entries now require exactly 2 problems, 2 NOT-RUN (item_sell_price
  and rod_can_use_target, each named) and no MISMATCH anywhere; the old one-NOT-RUN log is no longer the known shape.
  Remove the rod entry once tier 2 can sample that address.
- `h56-h5` now also reads r22-cap-female (bt-ch4) and r22-cap-rod_target (8 real-play routes). Round 20's
  integrate, running beside, added r20-cap-newb to the same row at about the same time: 19 sessions in all.
- tests/test_check_all.py: generated samples for the four new rows (no early give-up allowed), and the KnownFailures
  test on a two-NOT-RUN log (a third NOT-RUN, any MISMATCH, another address, or the old one-NOT-RUN log are not
  known). 84 tests OK (1 skipped, as before). Written with literal edits: 0x01 and 0x08 count 0 in both files.
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **41 pass** in 46 s; `--only female-diff,female-diff-long,rod-target-diff,rod-target-diff-long,readable,
  gen-stubs-check,equip-use-diff,growth-diff` (the new rows, the readable layer, the target rows, and the two caller
  tests whose docs changed) **8 pass** in 10 min 47 s (growth-diff the long pole, 10 min 39 s beside round 20's
  robots; rod 42/42 and 1,500 long, female 19/19 and 3,000 long, readable 146/146, gen-stubs 257 overrides);
  `--only h56-h5` alone **pass** in 1 min 23 s (19 sessions: 223 of 257 met, 209,460 records, 0 bad).
- Left for the weekly slow run: m1-tests, symbols, tables-test, assets-quick, assets-bch, assets-bchwrite,
  assets-bchwrite-all, assets-arc, assets-portrait, assets-full, maps-test, castle-all, mods-selftest, text-mods,
  play-tests, engine-selftest, harness-selftest, parallel-smoke, selftest, stance-diff(-long), triangle-diff(-long),
  vein-diff(-long), formula-diff(-long), growth-diff-long, skill-diff(-long), menu-diff(-long), sheet-diff(-long),
  item-diff(-long), move-diff(-long), support-diff(-long), ai-perm-diff(-long), battle2-diff(-long),
  class-change-diff(-long), weapon-rank-diff(-long), shop-price-diff(-long), castle-join-diff(-long),
  equip-use-diff-s7, staff-range-diff(-long), capability-diff(-long), shop-grey-diff(-long), ai-value-diff(-long),
  flags-diff(-long), flags-diff-s424242, forces-diff(-long), weapon-level-view-diff(-long), strike-diff(-long),
  who-holds-diff(-long), look-step4, look-portrait, writer-gate, writer-diff(-long), mutate-writer-fake,
  readable-verify, rom-rebuild, rom-tests.

## Round 23 integrate (2026-11-17 night; F-028: the slow suite is weekly)

- New rows from the round 23 reader batches (read only; docs/tracks/REWRITE_ORDER4.md rows 5 and 6, the last two):
  - `item-enhance-diff` (medium; item_enhance_diff.py --plant: 300 cases, 29 planted bugs, about 41 s) and
    `item-enhance-diff-long` (slow; -n 1500 --seed 7, about 24 s). Lock `readable:item_enhance`: both rows share
    one build folder, and two runs of this test at once crash with WinError 32 (the batch's review saw it), so they
    never overlap. **Early give-ups are allowed here on purpose** (about 35 per 300 cases: a CanItemEquip cache cold
    before the tail branch, where the original answers first; safe), so these two rows do not copy the female/rod
    "N early give-ups" reject. A mismatch, a missed plant, "could not run", a Traceback or a FAILED/SKIPPED line
    still fails. The cache key holds both item_enhance_diff.py and equip_use_diff.py (it imports that file's base
    states, answers and guard lists).
  - `volume-diff` (fast; volume_diff.py --plant: 1,200 cases over four readers, 19 planted bugs, about 30 s) and
    `volume-diff-long` (slow; -n 1500 --seed 7: 6,000 cases, about 30 s). Lock `readable:volume`. The volume readers
    have no cache, so these rows reject any give-up at all ("N cold:" or "N early give-ups").
- `readable-verify`: no new KNOWN entry. unit_item_enhance_have (0x0052FB98) gives GAVE-UP in tier 2 (verify's
  made-up state has its guard words cold) and the four volume readers give UNSAMPLED (no real class table, so the
  virtual GetMax runs into junk). Neither is a verify problem; a NOT-RUN or MISMATCH for them would still fail the
  row. A comment beside the KNOWN list says so.
- `h56-h5` now also reads r23-cap-item_enhance (bt-ch4) and r23-cap-volume (opt-ch8-reload): 21 sessions.
- tests/test_check_all.py: samples for the four new rows (item_enhance passes with early give-ups; volume fails on
  any give-up). 84 tests OK (1 skipped, as before).
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **42 pass** in 48 s (volume-diff is a fast row); `--only selftest,readable,gen-stubs-check,item-enhance-diff,
  item-enhance-diff-long,volume-diff,volume-diff-long` **7 pass** in 2 min 36 s (item 29/29 and 1,500 long, volume
  19/19 and 6,000 long, readable 146/146, gen-stubs 262 overrides, tests 84 OK); `--only h56-h5` alone **pass** in
  1 min 45 s (21 sessions: 228 of 262 met, 209,570 records, 0 bad).
- Left for the weekly slow run: m1-tests, symbols, tables-test, assets-quick, assets-bch, assets-bchwrite,
  assets-bchwrite-all, assets-arc, assets-portrait, assets-full, maps-test, castle-all, mods-selftest, text-mods,
  play-tests, engine-selftest, harness-selftest, parallel-smoke, stance-diff(-long), triangle-diff(-long),
  vein-diff(-long), formula-diff(-long), growth-diff(-long), skill-diff(-long), menu-diff(-long), sheet-diff(-long),
  item-diff(-long), move-diff(-long), support-diff(-long), ai-perm-diff(-long), battle2-diff(-long),
  class-change-diff(-long), weapon-rank-diff(-long), shop-price-diff(-long), castle-join-diff(-long),
  equip-use-diff, equip-use-diff-s7, staff-range-diff(-long), capability-diff(-long), shop-grey-diff(-long),
  ai-value-diff(-long), flags-diff(-long), flags-diff-s424242, forces-diff(-long), weapon-level-view-diff(-long),
  strike-diff(-long), who-holds-diff(-long), female-diff(-long), rod-target-diff(-long), look-step4, look-portrait,
  writer-gate, writer-diff(-long), mutate-writer-fake, readable-verify, rom-rebuild, rom-tests.

## Round 25 integrate (2026-11-17 night; F-028: the slow suite is weekly)

- New rows from the round 25 batches (read only; docs/tracks/REWRITE_ORDER5.md rows 1 and 2):
  - `job-female-diff` (fast; job_female_diff.py --plant: 300 cases, 13 planted bugs, about 30-40 s) and
    `job-female-diff-long` (slow; -n 1500 --seed 7, about 23 s). Lock `readable:job_female` (one build folder).
    **Give-ups at entry while the one-time cache is cold are allowed on purpose** (about 24 per 300 cases; the
    game's own code then fills the cache), so these rows do not reject "N cold:". A mismatch, a missed plant,
    "could not run", a Traceback or a FAILED/SKIPPED line still fails.
  - `job-record-diff` (fast; job_record_diff.py --plant: 300 cases, 18 planted bugs, about 35 s) and
    `job-record-diff-long` (slow; -n 1500 --seed 7, about 21 s). Lock `readable:job_record`. Job::Get is a
    registered **helper**, not an override (tier 2 cannot pick a fall-through target, the UnitPool::Get lesson);
    the rows still guard its C. No cache, so any give-up ("N cold:" or "N early give-ups") fails.
- `readable-verify`: no new KNOWN entry. job_female_is_female (0x00524AF4) gives GAVE-UP (cold cache in verify's
  made-up memory; its shadow r0 matched); job_record_get is a helper, which verify does not sample. A comment beside
  the KNOWN list says so.
- `h56-h5` now also reads r25-cap-job_female (bt-ch4): 22 sessions.
- tests/test_check_all.py: samples for the four new rows (job_female passes with cold give-ups; job_record fails on
  any give-up). 84 tests OK (1 skipped, as before).
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **44 pass** in 1 min 9 s (the two new short rows are fast rows); `--only selftest,readable,gen-stubs-check,
  job-female-diff,job-female-diff-long,job-record-diff,job-record-diff-long` **7 pass** in 2 min 48 s (job_female
  13/13 and 1,500 long, job_record 18/18 and 1,500 long, readable 146/146, gen-stubs 263 overrides / 67 guard users,
  tests 84 OK); `--only h56-h5` alone **pass** in 1 min 51 s (22 sessions: 229 of 263 met, 209,590 records, 0 bad).
- Left for the weekly slow run: m1-tests, symbols, tables-test, assets-quick, assets-bch, assets-bchwrite,
  assets-bchwrite-all, assets-arc, assets-portrait, assets-full, maps-test, castle-all, mods-selftest, text-mods,
  play-tests, engine-selftest, harness-selftest, parallel-smoke, stance-diff(-long), triangle-diff(-long),
  vein-diff(-long), formula-diff(-long), growth-diff(-long), skill-diff(-long), menu-diff(-long), sheet-diff(-long),
  item-diff(-long), move-diff(-long), support-diff(-long), ai-perm-diff(-long), battle2-diff(-long),
  class-change-diff(-long), weapon-rank-diff(-long), shop-price-diff(-long), castle-join-diff(-long),
  equip-use-diff, equip-use-diff-s7, staff-range-diff(-long), capability-diff(-long), shop-grey-diff(-long),
  ai-value-diff(-long), flags-diff(-long), flags-diff-s424242, forces-diff(-long), weapon-level-view-diff(-long),
  strike-diff(-long), who-holds-diff(-long), female-diff(-long), rod-target-diff(-long), item-enhance-diff(-long),
  volume-diff-long, look-step4, look-portrait, writer-gate, writer-diff(-long), mutate-writer-fake,
  readable-verify, rom-rebuild, rom-tests.

## Round 26 integrate (2026-11-17 night; F-028: the slow suite is weekly)

- New rows from the round 26 batches (read only; docs/tracks/REWRITE_ORDER5.md rows 5 and 3):
  - `key-door-diff` (fast; key_door_diff.py --plant: 300 cases, 18 planted bugs, 45 s alone, 1 min 16 s in the
    fast run) and `key-door-diff-long` (slow; -n 1500 --seed 7, about 20 s). Lock `readable:key_door` (one build
    folder). **Give-ups at entry while the one-time skill-number cache is cold are allowed on purpose** (about 34
    per 300 cases; the game's own code then fills the cache), so these rows do not reject "N cold:". A mismatch, a
    missed plant, "could not run", a Traceback or a FAILED/SKIPPED line still fails.
  - `skill-record-diff` (fast; skill_record_diff.py --plant: 300 cases, 20 planted bugs, 44 s alone, 1 min 10 s in
    the fast run) and `skill-record-diff-long` (slow; -n 1500 --seed 7, about 22 s). Lock `readable:skill_record`.
    No cache and no guest call, so any give-up ("N cold:" or "N early give-ups") fails.
- `readable-verify`: no new KNOWN entry. key_door_unit_can_open (0x00529E20) gives GAVE-UP (cold cache in verify's
  made-up memory) and skill_record_by_name (0x001758C4) gives ABI-ONLY (0 MISMATCH). A comment beside the KNOWN
  list says so.
- `h56-h5` now also reads r26-cap-key_door and r26-cap-skill_record (both bt-ch4): 24 sessions.
- tests/test_check_all.py: samples for the four new rows (key_door passes with cold give-ups; skill_record fails on
  any give-up). 84 tests OK (1 skipped, as before).
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **46 pass** in 1 min 42 s (the two new short rows are fast rows); `--only selftest,readable,gen-stubs-check,
  key-door-diff,key-door-diff-long,skill-record-diff,skill-record-diff-long` **7 pass** in 3 min 2 s (key_door
  18/18 and 1,500 long, skill_record 20/20 and 1,500 long, readable 146/146, gen-stubs 265 overrides / 68 guard
  users, tests 84 OK); `--only h56-h5` alone **pass** in 2 min 8 s (24 sessions: 231 of 265 met, 209,632 records,
  0 bad).
- Left for the weekly slow run: the round 25 list (m1-tests, symbols, tables-test, assets-quick, assets-bch,
  assets-bchwrite, assets-bchwrite-all, assets-arc, assets-portrait, assets-full, maps-test, castle-all,
  mods-selftest, text-mods, play-tests, engine-selftest, harness-selftest, parallel-smoke, every older *-diff and
  *-diff-long row, look-step4, look-portrait, writer-gate, writer-diff(-long), mutate-writer-fake, readable-verify,
  rom-rebuild, rom-tests) plus job-female-diff-long and job-record-diff-long. The round 26 long rows ran this round.
  The callers' tests (class_change_diff, skill_diff, ai_perm_diff) were rerun by the batches by hand with 0
  mismatches; their check_all rows stay weekly.

## Round 27 integrate (2026-11-18 night; F-028: the slow suite is weekly)

- New rows from the round 27 batch (read only; docs/tracks/REWRITE_ORDER5.md row 4):
  - `person-record-diff` (fast; person_record_diff.py --plant: 300 cases per function, two functions, 38 planted
    bugs, 43 s alone, 55 s in the fast run) and `person-record-diff-long` (slow; -n 1500 --seed 7 prints 3000
    cases, about 15 s). Lock `readable:person_record` (one build folder: two runs at once fail with WinError 32).
    No cache and no guest call, so any give-up ("N cold:" or "N early give-ups") fails. A made-up state whose data
    read lands in the game's code is drawn again on the ARM side before the C runs and printed ("drawn again");
    those lines are allowed, since they cannot hide a mismatch.
- `readable-verify`: no new KNOWN entry. person_record_by_name (0x0044A6DC) gives ABI-ONLY (0 MISMATCH);
  person_record_get (0x0044A6F8) is a helper, so verify does not sample it. A comment beside the KNOWN list says so.
- `h56-h5` now also reads r27-cap-person_record (bt-ch6-castle): 25 sessions.
- tests/test_check_all.py: samples for the two new rows (any give-up fails; a "drawn again" line passes). 84 tests
  OK (1 skipped, as before).
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **47 pass** in 1 min 55 s; `--only selftest,readable,gen-stubs-check,person-record-diff,person-record-diff-long`
  **5 pass** in 2 min 17 s (person_record 38/38 and 3,000 long, readable 146/146, gen-stubs 266 overrides / 68
  guard users, tests 84 OK); `--only h56-h5` alone **pass** in 1 min 42 s (25 sessions: 232 of 266 met, 209,652
  records, 0 bad).
- Left for the weekly slow run: the round 26 list (m1-tests, symbols, tables-test, assets-quick, assets-bch,
  assets-bchwrite, assets-bchwrite-all, assets-arc, assets-portrait, assets-full, maps-test, castle-all,
  mods-selftest, text-mods, play-tests, engine-selftest, harness-selftest, parallel-smoke, every older *-diff and
  *-diff-long row, look-step4, look-portrait, writer-gate, writer-diff(-long), mutate-writer-fake, readable-verify,
  rom-rebuild, rom-tests, job-female-diff-long, job-record-diff-long) plus key-door-diff-long and
  skill-record-diff-long. The round 27 long row ran this round. The caller's test (castle_join_diff -n 1500 --seed
  7, 0 mismatches) was rerun by the batch by hand; its check_all row stays weekly.

## Round 28 integrate (2026-11-18 night; OK A, F-032; F-028: the slow suite is weekly)

- New rows `oka-host-seed1` and `oka-host-seed2` (medium): OK A's host test with planted bugs on both seeds
  (`src/readable/menu/tests/writer_diff.py --plant --seed 1` / `--seed 2`). Each must print its own seed, 0
  mismatches and every planted bug caught; any NOT CAUGHT, MISMATCH, FAILED, SKIPPED or traceback fails. They
  cover `config_write_options` only: W1 (`config_options_hook`) and W2 (`config_serialize_guard`) are not written
  (docs/OPTIONS_WIRING.md section 11), so there is no W1/W2 row yet. Both use the unarmed table and the
  ordinary host build; check_all never uses an armed library.
- Lock: both new rows take `readable:writers` with writer-gate / writer-diff(-long), because they share
  writer_diff's build folder. The first run tonight, before the lock, had writer-diff and oka-host-seed1 collide in
  that folder (a traceback, exit 1); with the lock both pass. That was a check_all fault, not a writer fault.
- No `opt-*` rule row: no step proposed one, and no OK A `opt-*` route exists. `robot-routes` is unchanged (it still
  checks the two real-play options routes; an OK A route must never be added to it).
- tests/test_check_all.py: samples for the two rows (a wrong seed, a mismatch, a missed plant, a run without plants
  and a skip all fail). 84 tests OK (1 skipped, as before).
- Run this round: `check_all --fast --jobs auto --cache --skip h56-h5` **47 pass** in 2 min 38 s;
  `--only oka-host-seed1,oka-host-seed2,writer-diff` (after the lock) **3 pass**: seed 1 and seed 2 each 600 cases,
  0 mismatches, 25/25 caught (about 8 min each, below normal, one lane at a time beside round 24).

## Round 24 integrate (2026-11-18 night; F-028: the slow suite is weekly)

- `robot-routes` (F-031): ROUND8_PACKS now also requires cq-ch16-clear, rv-ch21-clear, rv-ch22-clear,
  rv-ch23-clear and rv-ch24-clear (all five proven this round with two equal copies and packed). cq-ch17 was not
  cleared: no key, no pack, not required. Today: 65 verified real-play routes, none left out.
- `h56-h5`: r24-capn added (round 24's five new routes, every override, live on the round 27 library): 26
  sessions, 232 of 266 met, 229,662 records, 0 bad.
- tests/test_check_all.py: the round 20 test now uses an unverified rv-ch25 as the key left out; a new test
  requires each of the five round 24 packs and checks that cq-ch17-clear is not required. 85 tests OK (1 skipped,
  as before). Written from a file, no escaping step: 0x01 and 0x08 count 0 in both files. Round 28's oka rows in
  the same files were left as they were.
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **47 pass** in 2 min 56 s; `--only selftest,robot-routes,cheat-endgame` **3 pass** in 1 min 27 s; `--only
  h56-h5` alone **pass** in 2 min 12 s.
- Left for the weekly slow run: the round 27 list unchanged (m1-tests, symbols, tables-test, assets-quick,
  assets-bch, assets-bchwrite, assets-bchwrite-all, assets-arc, assets-portrait, assets-full, maps-test,
  castle-all, mods-selftest, text-mods, play-tests, engine-selftest, harness-selftest, parallel-smoke, every older
  *-diff and *-diff-long row, look-step4, look-portrait, writer-gate, writer-diff(-long), mutate-writer-fake,
  readable-verify, rom-rebuild, rom-tests, job-female-diff-long, job-record-diff-long, key-door-diff-long,
  skill-record-diff-long, person-record-diff-long). No reader file changed this round, so no medium or slow row
  was touched beyond selftest.

## Round 30 integrate (2026-11-18 night; F-028: the slow suite is weekly)

- **No row changed.** Round 30 proved no chapter: rv-ch25 is not cleared, and rv-ch26, rv-ch27 and
  cheat-rv-endgame were not started. So `robot-routes` requires no new pack (rv-ch25-clear does not exist and is
  not required) and `cheat-endgame` gets no cheat-rv-endgame row. tests/test_check_all.py unchanged: 85 tests OK
  (1 skipped, as before). Round 29's cheat-cq-ch17 is round 29's to add.
- `h56-h5` unchanged (26 sessions): run alone, PASS; 232 of 266 met, 229,662 records, 0 bad.
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **47 pass** in 2 min 1 s; `--only selftest,robot-routes,cheat-endgame` **3 pass** in 58 s; `--only h56-h5` alone
  **pass** in 1 min 50 s.
- Left for the weekly slow run: the round 24 list unchanged, plus round 28's oka-host-seed1 and oka-host-seed2
  (m1-tests, symbols, tables-test, assets-quick, assets-bch, assets-bchwrite, assets-bchwrite-all, assets-arc,
  assets-portrait, assets-full, maps-test, castle-all, mods-selftest, text-mods, play-tests, engine-selftest,
  harness-selftest, parallel-smoke, every older *-diff and *-diff-long row, look-step4, look-portrait, writer-gate,
  writer-diff(-long), mutate-writer-fake, readable-verify, rom-rebuild, rom-tests, job-female-diff-long,
  job-record-diff-long, key-door-diff-long, skill-record-diff-long, person-record-diff-long, oka-host-seed1,
  oka-host-seed2). No reader file changed this round, so no medium or slow row was touched beyond selftest.

## Round 29 integrate (2026-11-18 night; F-033; F-028: the slow suite is weekly)

- **New row `cheat-conquest`** (fast, `check_cheat_conquest`). F-033 (owner 2026-11-18: "just maximize movement
  options for conquest to make sure the combat and animations etc work") put Conquest from chapter 17 on the cheat
  track with a declared movement cheat (move bonus s8 Unit+0x12C). The table `CHEAT_CQ_PACKS` names every Conquest
  cheat chapter proven by a two-copy proof, with the save it starts from: this round **cheat-cq-ch17 from
  cq-ch16-clear**. Each must be in routes.json with `"cheat": true`, at least one poke, that start save, `"verified":
  true` and checkpoints in markers.json; when build/harness/saves exists its packed `<route>-clear.zip` must be
  there and carry the cheat mark `harness-cheat.json` (so it can never start real play). Any other cheat-cq-* key is
  named as not proven (none written this round: cheat-cq-ch18 was not cleared). No real-play cq-ch17+ key was won
  without a poke, so `ROUND8_PACKS` and `robot-routes` are unchanged. The existing `cheat-routes` row
  (cheats.py --check) already checks the cheat-cq-ch17 route's rules: 6 cheat routes, rules OK.
- tests/test_check_all.py: new class `CheatConquest` (4 tests: the table and row; good with and without
  build/harness/saves; an unmarked or missing clear save fails; six planted route problems fail). **89 tests OK** (1
  skipped, as before).
- `h56-h5` unchanged (26 real-play sessions; the cheat track never mixes in): run alone, PASS.
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **48 pass** in 2 min 12 s (47 + cheat-conquest); `--only selftest,robot-routes,cheat-routes,cheat-endgame,
  cheat-conquest` **5 pass** in 1 min 1 s; `--only h56-h5` alone **pass** in 2 min 1 s.
- Left for the weekly slow run: the round 30 list unchanged (m1-tests, symbols, tables-test, assets-quick,
  assets-bch, assets-bchwrite, assets-bchwrite-all, assets-arc, assets-portrait, assets-full, maps-test,
  castle-all, mods-selftest, text-mods, play-tests, engine-selftest, harness-selftest, parallel-smoke, every older
  *-diff and *-diff-long row, look-step4, look-portrait, writer-gate, writer-diff(-long), mutate-writer-fake,
  readable-verify, rom-rebuild, rom-tests, job-female-diff-long, job-record-diff-long, key-door-diff-long,
  skill-record-diff-long, person-record-diff-long, oka-host-seed1, oka-host-seed2). No reader file changed this
  round, so no medium or slow row was touched beyond selftest.

## Round 31 integrate (2026-11-18 morning; F-028: the slow suite is weekly)

- **`robot-routes`**: ROUND8_PACKS now requires **rv-ch25-clear and rv-ch26-clear** (round 31, F-031, real play,
  each proven with two equal copies and packed). rv-ch27 is not cleared (no key, no pack) and is not required; the
  round 20 test's "unverified key left out" example moved from rv-ch25 to rv-ch27. New test
  `test_round31_packs_are_required` (each of the two packs missing fails the row). tests/test_check_all.py: 90
  tests OK (1 skipped).
- **`cheat-endgame`**: unchanged. cheat-rv-endgame was not started (chapter 27 not cleared), so it gets no row.
- **`h56-h5`**: 28 sessions (r31-cap-rv-ch25 and r31-cap-rv-ch26 added, the proof captures on the unchanged round
  27 library). Run alone: PASS, **233 of 266 met** (`script_terrain_out_of_play_area` met for the first time),
  238,051 records, 0 bad.
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **48 pass** in 2 min 7 s; `--only selftest,robot-routes,cheat-endgame,cheat-conquest` **4 pass** in 1 min 48 s;
  `--only h56-h5` alone **pass** in 2 min 21 s.
- Left for the weekly slow run: the round 30 list unchanged (m1-tests, symbols, tables-test, assets-quick,
  assets-bch, assets-bchwrite, assets-bchwrite-all, assets-arc, assets-portrait, assets-full, maps-test, castle-all,
  mods-selftest, text-mods, play-tests, engine-selftest, harness-selftest, parallel-smoke, every older *-diff and
  *-diff-long row, look-step4, look-portrait, writer-gate, writer-diff(-long), mutate-writer-fake, readable-verify,
  rom-rebuild, rom-tests, job-female-diff-long, job-record-diff-long, key-door-diff-long, skill-record-diff-long,
  person-record-diff-long, oka-host-seed1, oka-host-seed2). No reader file changed this round, so no medium or slow
  row was touched beyond selftest and h56-h5.

## Round 32 integrate (2026-11-18 morning; F-033; F-028: the slow suite is weekly)

- **`cheat-conquest`**: `CHEAT_CQ_PACKS` now lists **cheat-cq-ch18 (from cheat-cq-ch17-clear) and cheat-cq-ch19
  (from cheat-cq-ch18-clear)**, both proven this round with two equal copies and packed with the cheat mark. They
  declare no pokes of their own: the move bonus is already in their cheat start save. So the row now accepts an
  empty poke list only when the route starts from another listed route's `-clear` save; a listed route from any
  other save still needs at least one poke. cheat-cq-ch20 is not cleared (no key) and is not listed. No real-play
  cq-ch17+ key was won without a poke, so `ROUND8_PACKS` and `robot-routes` are unchanged. `cheat-routes`
  (cheats.py --check): 8 cheat routes, rules OK.
- tests/test_check_all.py, class `CheatConquest`: setUp trims the table to cheat-cq-ch17 so the four round 29 tests
  keep their meaning (tearDown restores it); `test_table_and_row` checks the real three-entry table; new
  `test_round32_chain_without_pokes_passes` (ch18 and ch19 with no pokes from the chain's saves pass; an unproven
  cheat-cq-ch20 is named) and `test_round32_chain_problems_fail` (ch19 from a real-play save, ch18 not verified, ch19
  not marked cheat, ch18 without checkpoints, ch19's clear save missing: each fails). **92 tests OK** (1 skipped).
- `h56-h5` unchanged (28 real-play sessions; the cheat track never mixes in): run alone, PASS (233 of 266, 238,051
  records).
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **48 pass** in 2 min 18 s; `--only selftest,robot-routes,cheat-routes,cheat-endgame,cheat-conquest` **5 pass** in
  1 min 12 s; `--only h56-h5` alone **pass** in 3 min 23 s (it ran beside the live captures).
- Left for the weekly slow run: the round 31 list unchanged (m1-tests, symbols, tables-test, assets-quick,
  assets-bch, assets-bchwrite, assets-bchwrite-all, assets-arc, assets-portrait, assets-full, maps-test, castle-all,
  mods-selftest, text-mods, play-tests, engine-selftest, harness-selftest, parallel-smoke, every older *-diff and
  *-diff-long row, look-step4, look-portrait, writer-gate, writer-diff(-long), mutate-writer-fake, readable-verify,
  rom-rebuild, rom-tests, job-female-diff-long, job-record-diff-long, key-door-diff-long, skill-record-diff-long,
  person-record-diff-long, oka-host-seed1, oka-host-seed2). No reader file changed this round, so no medium or slow
  row was touched beyond selftest and h56-h5.

## Round 33 integrate (2026-11-18 late morning; F-031; F-028: the slow suite is weekly)

- **No table change.** Nothing was proven this round: rv-ch27 is not cleared (no key, no pack) and cheat-rv-endgame
  was not started, so `robot-routes` (ROUND8_PACKS), `cheat-endgame` and `cheat-conquest` keep round 32's lists.
  tests/test_check_all.py unchanged: **92 tests OK** (1 skipped).
- The capture library was rebuilt (`build.py --swap`; check-fresh had said STALE because of F-034's unarmed writer
  files, not a reader), so `readable` ran with the touched rows: host test 146/146, PASS.
- `h56-h5` unchanged (28 real-play sessions): run alone, PASS (233 of 266, 238,051 records).
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **48 pass** in 2 min 15 s; `--only selftest,robot-routes,cheat-routes,cheat-endgame,cheat-conquest,readable`
  **6 pass** in 3 min 7 s (cheat-routes: 9 cheat routes, round 34's cheat-cq-ch20 included); `--only h56-h5` alone
  **pass** in 2 min 17 s.
- Left for the weekly slow run: the round 32 list unchanged (m1-tests, symbols, tables-test, assets-quick,
  assets-bch, assets-bchwrite, assets-bchwrite-all, assets-arc, assets-portrait, assets-full, maps-test, castle-all,
  mods-selftest, text-mods, play-tests, engine-selftest, harness-selftest, parallel-smoke, every older *-diff and
  *-diff-long row, look-step4, look-portrait, writer-gate, writer-diff(-long), mutate-writer-fake, readable-verify,
  rom-rebuild, rom-tests, job-female-diff-long, job-record-diff-long, key-door-diff-long, skill-record-diff-long,
  person-record-diff-long, oka-host-seed1, oka-host-seed2). F-034's new writer code is covered there by writer-gate,
  writer-diff(-long) and mutate-writer-fake, which this round did not run.

## Round 34 integrate (2026-11-18 midday; F-033; F-028: the slow suite is weekly)

- **`cheat-conquest`**: `CHEAT_CQ_PACKS` now lists **cheat-cq-ch20 (from cheat-cq-ch19-clear), cheat-cq-ch21 (from
  cheat-cq-ch20-clear), cheat-cq-ch22 (from cheat-cq-ch21-clear) and cheat-cq-ch23 (from cheat-cq-ch22-clear)**, all
  proven this round with two equal copies and packed with the cheat mark. None declares pokes of its own (each
  starts from the listed chapter before's cheat clear save), which round 32's rule already allows. cheat-cq-ch24 is
  not cleared (no key) and is not listed. No real-play cq-ch17+ key was won without a poke, so `ROUND8_PACKS` and
  `robot-routes` are unchanged. `cheat-routes` (cheats.py --check): 12 cheat routes, rules OK.
- tests/test_check_all.py, class `CheatConquest`: `test_table_and_row` checks the real seven-entry table (setUp
  still trims it to cheat-cq-ch17 for the other tests). **93 tests OK** (1 skipped).
- `h56-h5` unchanged (28 real-play sessions; the cheat track never mixes in): run alone, PASS (233 of 266, 238,051
  records).
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5`
  **51 pass** in 2 min 23 s; `--only selftest,robot-routes,cheat-routes,cheat-endgame,cheat-conquest` **5 pass** in
  1 min 32 s; `--only h56-h5` alone **pass** in 3 min 7 s (all beside the four live captures).
- Left for the weekly slow run: the round 33 list unchanged (m1-tests, symbols, tables-test, assets-quick,
  assets-bch, assets-bchwrite, assets-bchwrite-all, assets-arc, assets-portrait, assets-full, maps-test, castle-all,
  mods-selftest, text-mods, play-tests, engine-selftest, harness-selftest, parallel-smoke, every older *-diff and
  *-diff-long row, look-step4, look-portrait, writer-gate, writer-diff(-long), mutate-writer-fake, readable-verify,
  rom-rebuild, rom-tests, job-female-diff-long, job-record-diff-long, key-door-diff-long, skill-record-diff-long,
  person-record-diff-long, oka-host-seed1, oka-host-seed2). No reader file changed this round, so no medium or slow
  row was touched beyond selftest and h56-h5 (round 35 ran its own w12 rows).

## Round 35 integrate (2026-11-18 midday; OK A, F-034; F-028: the slow suite is weekly)

- **5 new rows.** `w12-host-seed1` (w12_diff.py --plant, seed 20261118) and `w12-host-seed2` (--plant --seed 2),
  medium: the game's Reset / Deserialize / Serialize / SetValue against W1/W2 through the gate; each must show its
  own seed, W1 stores, W2 saves and W2 restores all exercised, the unarmed table with 0 mismatches, clean saves 0,
  and every planted bug caught; any MISMATCH (scenario, options file or clean save), NOT CAUGHT or a stale plant
  list fails. `w12-options` (fast): the options file reader alone, 0 mismatches. `options-track-selftest` and
  `options-track-routes` (fast): the opt-* rules. The three w12 rows share build/readable/writers/w12 and take
  turns with the other writer rows (lock `readable:writers`).
- **`robot-routes` skips routes with `"options"`** (the options track is never real play); new test
  `test_options_routes_are_not_real_play`. check_all never uses the armed library.
- `oka-host-seed1/2` keep covering config_write_options only.
- Run this round (no `--slow`, F-028): `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5
  --priority below_normal` **51 pass** in about 2 min (12:41:48 to 12:43:54); `--only robot-routes,cheat-routes,
  options-track-selftest,options-track-routes,w12-options,w12-host-seed1,w12-host-seed2` **7 pass** in about 14 min
  (w12-host-seed1 7 min 02 s, w12-host-seed2 7 min 06 s, both 300 scenarios, 0 mismatches, 26/26 caught).
  tests/test_check_all.py: **93 tests OK** (1 skipped).
- Added to the weekly slow list: none (the two w12 seed rows are medium and ran this round).

## Round 36 integrate (2026-11-18 afternoon; F-035; F-028: the slow suite is weekly)

- **`cheat-endgame`**: `CHEAT_NO_CLEAR_SAVE` now lists **cheat-rv-ch27 and cheat-rv-endgame (both from
  rv-ch26-clear)** beside
  cheat-bt-endgame. Revelation 27 on the cheat track (proven this round, two equal copies) ends on the Endgame
  preparations screen; the game makes no save after chapter 27, so the proof's save files stayed byte for byte
  rv-ch26-clear, as with bt-ch27. The packed cheat-rv-ch27-clear.zip was therefore an rv-ch26 save under a ch27 name
  (F-029), and by the fingerprint rule (headless.save_is_cheat) it made **rv-ch26-clear itself read as a cheat
  save**. Integrate moved it to build/harness/saves-aside/ (not deleted); rv-ch26-clear is real play again and the
  row now fails if a cheat-rv-ch27-clear.zip comes back. **cheat-rv-endgame joined the table too**, after integrate's
  two-copy proof passed (r36-proof2-cheat-rv-endgame; verified true): it ends on the title screen with no save,
  like cheat-bt-endgame. The FAIL text now says "the game makes no save there" (chapter 27 or Endgame).
- No real-play route was proven this round, so `ROUND8_PACKS` and `robot-routes` are unchanged (67 verified
  real-play routes). `cheat-routes`: 17 cheat routes, 98 packed real-play start saves checked, none carries cheat
  state.
- tests/test_check_all.py, class `CheatEndgame`: setUp trims the table to cheat-bt-endgame and tearDown restores it;
  `test_table_and_row` checks the real three-entry table; new
  `test_rv_ch27_clear_zip_is_refused`. **94 tests OK** (1 skipped).
- `h56-h5` unchanged (28 real-play sessions; the cheat track never mixes in).
- Run this round (no `--slow`, F-028), all below normal beside two live runs and rounds 34/35's games:
  `FEF_CHECK_ALL_SLOTS=8 check_all --fast --jobs auto --cache --skip h56-h5` **51 pass** (16:35:51 to 16:38:12);
  `--only selftest,robot-routes,cheat-routes,cheat-endgame,cheat-conquest` **5 pass** (to 16:39:15); `--only
  h56-h5` alone **pass** (to 16:41:30); the touched rows again after cheat-rv-endgame joined (17:01:36 to 17:02:37):
  **5 pass** (18 cheat routes; cheat-endgame: 3 verified, 0 problems).
- Note: `build.py --check-fresh` said STALE, but only because of another round's uncommitted writer edits in
  src/readable/menu/ (menu_config_writer.c, menu_options_hook.c, menus.h, menu_writer.h: an unarmed W2 restore
  function and comments). The library equals HEAD d0d9b4e exactly (offline.py's source gate passed with
  `--rev d0d9b4e`), so it was not rebuilt.
- Left for the weekly slow run: the round 34 list unchanged. No reader file changed this round, so no medium or slow
  row was touched beyond selftest and h56-h5.

## Round 38 integrate (2026-11-18 evening): OK A rerun [high unless tagged]

- **No new row.** The writer host-test rows (`w12-host-seed1`, `w12-host-seed2`, `w12-options`, `oka-host-seed1/2`,
  `writer-diff`) and the opt-* rule rows (`options-track-selftest`, `options-track-routes`) already exist (round 35).
- **`w12-host-seed1` / `w12-host-seed2` tightened**: the OK line must now show at least 32 planted bugs, all caught
  (`W12_PLANT_FLOOR`; round 38 added six plants: danger page value 2 stored, the restore rebuilding the zone from
  the hook and from the writer, the restore refusing the save's own byte, the block-mapped check removed, the gate
  asked for nothing). A run that catches all of a shrunken plant list (for example round 35's 26) fails. Test
  samples moved to 32/32 and a 26/26 fail sample was added for both seeds.
- **Not added (by the rules):** no opt-* route in `robot-routes`; check_all never uses an armed library.
- **Runs:** see docs/REPORT_2026-12-13.md (touched rows and the fast set, at below normal priority).

## Round 37 integrate (2026-11-18 evening; F-033/F-036; F-028: the slow suite is weekly)

- **`cheat-conquest`**: `CHEAT_CQ_PACKS` now lists **cheat-cq-ch24 (from cheat-cq-ch23-clear, 106 F-036 boost
  pokes), cheat-cq-ch25 (from cheat-cq-ch24-clear, 8 pokes) and cheat-cq-ch26 (from cheat-cq-ch25-clear, no pokes of
  its own)**, each proven this round with two equal copies and a packed cheat clear save (cheat mark checked).
- **`cheat-endgame`**: `CHEAT_NO_CLEAR_SAVE` adds **cheat-cq-ch27 and cheat-cq-endgame, both from
  cheat-cq-ch26-clear**. The game saves nothing after chapter 27 (the ch27 proof's packed zip was cheat-cq-ch26-clear
  byte for byte and was set aside as NOT-A-CLEAR-SAVE), and the Endgame ends on the title screen. New rule: a route
  of this table that starts from a listed Conquest cheat clear save may declare no pokes of its own (cheat-cq-ch27
  has none), as in `CHEAT_CQ_PACKS`; from a real-play save it still needs a poke. `cheat-conquest` no longer names
  these two as "not listed (not proven)".
- No real-play route was proven (no cq-ch17+ won without a poke), so `ROUND8_PACKS` and `robot-routes` are unchanged
  (67 verified real-play routes). `cheat-routes`: 19 cheat routes, 98 packed real-play start saves, none cheat.
- tests/test_check_all.py: both table tests check the real tables; new
  `CheatEndgame.test_cq_ch27_from_cheat_save_without_pokes` (passes from the cheat save with no pokes, refuses a
  cheat-cq-ch27-clear.zip, fails "declares no pokes" once the start save is not a listed cheat save). **95 tests OK**
  (1 skipped).
- `h56-h5` unchanged (28 real-play sessions; the cheat track never mixes in).
- Run this round (no `--slow`, F-028), all below normal beside five live captures: `FEF_CHECK_ALL_SLOTS=8 check_all
  --fast --jobs auto --cache --skip h56-h5` **51 pass** (18:19:45 to 18:23:06); `--only
  selftest,robot-routes,cheat-routes,cheat-endgame,cheat-conquest` **5 pass** (to 18:24:12); `--only h56-h5` alone
  **pass** (to 18:27:16).
- Library: check-fresh said STALE (round 38's committed menu writer edits), so it was rebuilt (`build.py --swap`).
- Left for the weekly slow run: the round 34 list unchanged. No reader file changed this round, so no medium or slow
  row was touched beyond selftest and h56-h5.

## Round 40 integrate (2026-11-18 evening): W1/W2 plant floor 34 [high unless tagged]

- **`W12_PLANT_FLOOR` raised from 32 to 34.** Round 40 added two w12_diff plants ("apply rebuilds the zone", from
  the hook and from the writer) with the new `config_apply_options`. `w12-host-seed1/2` fail if all of fewer than
  34 plants are caught. tests/test_check_all.py: the w12 fixtures now print 34/34; new bad case per seed: round 38's
  32/32 list no longer passes. **95 tests OK** (1 skipped).
- No new row: `w12-host-seed1/2`, `w12-options`, `options-track-selftest`, `options-track-routes` already cover
  W1/W2, options.c, the planted bugs on both seeds and the opt-* rules. No opt-* route added to `robot-routes`;
  check_all never uses an armed library. The three w12 rows keep their `readable:writers` lock (they share
  build/readable/writers/w12; two w12_diff runs started by hand at the same time collide there).
- Run this round (below normal, 20:43 to 21:16): w12_diff --plant seed 20261118 and seed 2 by hand (pass, 34/34, scored against the new row patterns); `check_all --fast --jobs auto --cache --skip h56-h5,w12-host-seed1,w12-host-seed2` **51 pass** (102 skip, medium/slow rows not run with --fast); `--only selftest,w12-options,options-track-selftest,options-track-routes,robot-routes` **5 pass**; `--only w12-host-seed1` **pass** (9m25s, 34/34). `w12-host-seed2` ran by hand only (same command, pass).
- Recheck 2026-11-19 (17:51 to 18:14, below normal, no source change since): `--only selftest,w12-options,
  options-track-selftest,options-track-routes,robot-routes` **5 pass**; `--fast --jobs auto --cache --skip
  h56-h5,w12-host-seed1,w12-host-seed2,w12-options` **50 pass** (103 skip); `--only w12-host-seed1,w12-host-seed2`
  **2 pass** (34/34 each, 8m24s / 12m01s); `python -m unittest tests.test_check_all` **95 OK** (1 skipped).

## Round 67 integrate (2026-11-23; release part A, F-052): retag, `--core`, `--skip-unit-dupes`

- **Retag.** 8 rows moved from fast to medium (they held 613 of the old 746 recorded s of `--fast`): volume-diff,
  job-female-diff, job-record-diff, key-door-diff, skill-record-diff, person-record-diff, parallel-tests, w12-options.
  The default set (126 rows) and `--slow` (181 rows) still run them; only the tags changed. **After an edit under
  `src/readable`, `include/readable` or `tools/readable`, run them by name:**
  `python tools/check_all.py --only volume-diff,job-female-diff,job-record-diff,key-door-diff,skill-record-diff,person-record-diff,parallel-tests,w12-options`.
- **Profiles (2026-11-23 recorded times, with the two smoke rows):** default 126 rows about 18,500 s; `--fast` 50 rows
  about 138 s; `--core` 52 rows about 159 s + about 50 s (the fast rows plus `CORE_EXTRA` = engine-selftest and, round 68, release-selftest, minus `UNIT_DUPES`);
  `--slow` 181 rows about 25,500 s. `--core`, `--fast` and `--slow` cannot be combined any more (usage error, exit 2; before, `--fast
  --slow` meant `--fast`). No caller in tools/ passed two of them.
- **`--skip-unit-dupes`** (on with `--core`) drops the 17 `UNIT_DUPES` rows, which are pure `python -m unittest`
  re-runs of 26 unit modules (text-mods, play-tests, rando-page-tests, sof-path-tests, randomizer-tests,
  rando-tracks-tests, rando-ingame-tests, rando-more-tracks-tests, rando-r56-tracks-tests, rando-r62-tracks-tests,
  rando-r63-boss-might, rando-r64-seal-bosses, rando-recruit-tests, rando-seal-tests, rando-colours-tests,
  rando-cache-tests, selftest). Each shows SKIP "unit-suite duplicate ...". Use it only in a pass that also runs the
  unit suite (`tools/release/run_tests.py`, docs/tests/CORE.md); it never drops a test from the repository.
- **`--list`** follows every profile: a Run yes/no column, recorded seconds, the reason a row is not run, and a sum.
- **Times file:** the stale rando-r66-rcheck-selftest entry is gone; `save_times()` now drops rows that no longer
  exist on every run. `tests/test_check_all.py` gained a Profiles class (9 tests; 104 OK, 1 skipped).
- **Smoke rows (round 67 part 2).** `smoke-selftest` (fast, so in `--fast` and `--core`): `python tools/harness/smoke.py
  selftest`, which runs tests/test_smoke.py in-process (fake runner, no game, about 5 s) and prints `smoke selftest: N/N
  ok`. It is a tool selftest row, not a `-m unittest` row, so it is not in `UNIT_DUPES`; the unit suite also runs
  tests/test_smoke.py, so a core pass runs those 19 synthetic tests twice (about 5 s). `smoke-set` (slow; not in
  `--core`, `--fast` or the default set; runs alone at the end, `PARALLEL_EXCLUSIVE`): `python tools/harness/smoke.py run`,
  the live round smoke (6 Fates jobs since round 84; 8 before) plus the memory compare against
  config/harness/smoke_baseline.json, about 105 s on 5 lanes in round 67 (2 lanes by default since round 84); PASS needs
  `PASS: jobs 6/6, memory compare equal, baseline equal`, and the Seal edition's row `seal-smoke` (edition seal, its
  own set `config/seal/smoke_set.json`) needs `PASS: jobs 2/2`, and any `FAIL`, `MISMATCH:`, `PARTIAL` or
  `STOPPED` line fails it. The release core runs smoke as its own step (docs/tests/CORE.md). Both rows have
  ROW_SAMPLES in tests/test_check_all.py. Details: docs/harness/SMOKE.md.
