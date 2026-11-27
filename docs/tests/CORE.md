# Core and full tests (round 67, release part A; F-052)

Round 67 split the tests into a CORE (about 10 minutes, run every round and by the later release command) and
FULL (everything that ran before round 67, and more). **Nothing lost coverage:** no test was deleted or weakened.
Heavy tests only moved to FULL, and each one that could have a cheap fixed stand-in got one in the core.

## The commands

| What | Command | Runs |
|---|---|---|
| Unit core | `python tools/release/run_tests.py --core` | every unit test except the ids in `tests/heavy.txt` (649 tests, round 67 part 2), 4 lanes |
| Unit full | `python tools/release/run_tests.py --full` | every unit test (671, round 67 part 2), 4 lanes; the same set as plain discover |
| Plain | `python -m unittest discover -s tests -t .` | unchanged: every unit test, heavy ones included, one after another |
| Lists | `python tools/release/run_tests.py --core --list` / `--full --list` / `--check-lists` | prints ids; checks heavy.txt and core.txt name real tests |
| check_all core | `python tools/check_all.py --core` | the fast rows (after the round-67 retag) plus engine-selftest (and, round 68, release-selftest: medium, about 50 s), without the 17 rows that only re-run unit modules (52 rows from round 68; round 67 had 51: 50 PASS + gen-headers SKIP; 38-48 s wall with `--jobs 4` in round 67 part 2; includes `smoke-selftest`, the smoke tool's synthetic selftest) |
| check_all full | `python tools/check_all.py --slow --jobs auto` (add `--skip-unit-dupes` when the unit suite runs in the same pass) | every row |
| Seeds | `python tools/release/fingerprints.py check` | the seed fingerprints (also run by the core test `tests/test_seed_fingerprints.py`) |
| Smoke | `python tools/harness/smoke.py run` | the round smoke: 6 headless robot jobs since round 84 (Birthright A011, Conquest B016, Revelation C012; randomizer off and everything-on all1, re-made with today's code) plus the randomizer-off memory compare, against `config/harness/smoke_baseline.json` (the Seal edition's 2 jobs: `--set config/seal/smoke_set.json`, docs/seal/CHECK.md); 2 lanes by default since round 84 (round 67: 8 jobs, 5 lanes, 103.9 s); exit 0 only if 6/6 PASS, the compare is equal and the baseline matches (docs/harness/SMOKE.md) |

The core is all three: unit core, check_all core and smoke. Smoke runs on its own (not inside check_all's
`--core`; the check_all row `smoke-set` is slow and runs the same command for the FULL pass).

Lanes are whole test modules, longest first by measured times (`config/release/test_times.json`, then the last run's
`build/release/test_times.json`). Each lane is a hidden below-normal process; the exit code is 0 only if every lane
finished, at least one test ran and nothing failed. Logs: `build/release/tests/<time>-<profile>/`.

## What the core runs

- Every synthetic test (check_all, play, sof_path, profile, paths, nuzlocke, run_tests, fingerprint verdicts, ...).
- The seed-identity layer: `test_rando_page62b`, `test_randomizer`, integrate default byte-identical, ingame
  `test_defaults`, the Seal boss list (tests/seal, the Seal edition only), boss_might, and the seed fingerprints (below).
- One QUICK GUARD per randomizer track, named in `tests/core.txt` (25 tracks: `<track> <test id>`; `--check-lists`
  fails if a quick guard is in heavy.txt).
- Fixed samples of the heavy tests (fixed lists, never random):
  - `test_text_mods.UserFilesTests.test_fixed_sample_archives_round_trip`: 40 fixed archives (the 20 largest, the
    largest and 2 smallest of each of the 5 places, the smallest Japanese-named and the smallest overall), same byte
    comparison as the 1,328-archive test;
  - `test_rando_recruit.RealTables.test_guards_over_2_seeds_every_option_set`: seeds r0 and r1 x 16 option sets;
  - `test_rando_cache.RealMake.test_one_seed_hit_is_byte_identical_and_change_misses`: one seed, cold vs warm
    byte-identical, warm makes 0 misses, a code change misses (so the core never trusts the cache blindly);
  - one "mods tool accepts" check: integrate `test_mods_tool_accepts_and_check_remakes`.
- `test_rando_ingame` makes one fresh `rando.py make` per (seed, flags) in setUpClass, side by side, with the rando
  cache OFF; every test asserts exactly what it did before (module 153.7 s before, 86.4 s full / 25.4 s core after).

## What is FULL only

The 22 ids in `tests/heavy.txt` (each with its measured time and its core stand-in in the comments): the
1,328-archive text round trip, recruit 50 seeds x 16, the six-make cache test, growth real modes, ingame
w1_table_options / e1 / recolour / everything_on, items and randomizer many-seeds, Seal five-seed everything-on,
integrate everything-on and do-not-disturb (6), and 4 of the 5 repeated "mods tool accepts" checks (music, skills,
promotions, stats). Plus the medium and slow check_all rows (the default set and `--slow`), and the F-051 matrix.

## When FULL is due

- an edit under `src/readable`, `include/readable` or `tools/readable` (then also run the 8 retagged check_all rows by
  name: `python tools/check_all.py --only volume-diff,job-female-diff,job-record-diff,key-door-diff,skill-record-diff,person-record-diff,parallel-tests,w12-options`);
- an engine patch edit (`patches/zakuro`, `tools/harness/patches`) or an engine build round;
- a seed fingerprint changed (announced; an unannounced change already fails the core);
- the owner says so, before the owner plays, every third round (F-051), and the weekly slow check_all (F-028).

## Seed fingerprints

`config/release/seed_fingerprints.json` holds sha256 only (no game values) of what each seed produces:
`fates/default/1`, `fates/everything-on/1`, `seal/default/1`, `seal/everything-on/1` (the page's defaults and
"Randomize everything", seed 1), `fates/boss-classes/r63fboss1` (the guarded round-63 patch 372b5d5c... and plan
c5825cce...) and `ids/r62-page` (run ids and make flags of the 119 round-62/62b page answer sets). Makes are fresh,
cache off, about 30-46 s wall with 5 at once.

`fingerprints.py check`:
- same hash: pass; a changed / new / vanished key listed in `config/release/seed_changes.json`: pass with a note;
- a change NOT listed: **FAIL** "seeds changed without notice: <keys>" (never a silent jump to FULL);
- a make error: FAIL; the Seal keys skip with a plain reason only when the Seal mod is not installed (and the
  ids key only when the game data itself is missing; with the data present but `build/r62/check/runs` missing it FAILS);
- the guarded r63fboss1 patch/plan shas cannot be announced away: a change there FAILS check and update until a person
  changes `GUARDED` in `tools/release/fingerprints.py`.

### Updating the fingerprints inside a round commit

1. When the round's code changes what a seed makes, write the change into `config/release/seed_changes.json`:
   `{"round": N, "changes": [{"key": "fates/everything-on/1", "reason": "round N: <what changed, plain words>"}]}`
   and announce it in the round report.
2. `python tools/release/fingerprints.py check` must pass (the listed keys show "changed-announced").
3. `python tools/release/fingerprints.py update --round N` rewrites only the listed keys. It refuses and writes
   nothing if an unlisted key changed, if seed_changes.json is for another round, if a guarded sha changed, or if any
   key was skipped or failed (so run it on the machine with the Seal mod).
4. Commit `seed_fingerprints.json` and `seed_changes.json` in the round commit, never on their own. The next round
   empties `changes` and sets its own round number.

## Timing gate and the cut list

The core is timed twice on a quiet machine (round 67 calibrate). Gate: the slower core total (unit core + check_all core + smoke, run back to back) must be <= 540 s.
If it is over, cut from this list in order (each cut moves a test or row to FULL, never deletes it; add it to
`tests/heavy.txt` with its time and re-time once):

1. `test_text_mods.FaceModTests` face demo (10.9 s) and resize (6.5 s);
2. `test_text_mods` InstallJournal crash tests (6.9 s, 5.2 s);
3. `test_rando_integrate` `test_w1_defaults_change_nothing` (13 s) and `test_w2_defaults_change_nothing` (11.5 s)
   (the integrate default byte-identical quick guard stays);
4. `test_check_all.RowCache.test_real_cache_specs_are_complete` (14.5 s);
5. the ingame core makes beyond `test_defaults` (the fingerprints keep everything-on covered).

Never cut: a quick guard in `tests/core.txt`, the fixed samples, the seed fingerprints, the smoke set, or any synthetic test.

### Measured (round 67 part 2 calibrate, 2026-11-23, quiet machine, smoke included, wall seconds)

The two passes ran back to back, each as `run_tests.py --core`, then `check_all.py --core --jobs 4`, then
`smoke.py run` (5 lanes). Logs are in build/r67/calibrate2/core1 and core2 (script: build/r67/calibrate2/core_once.sh).

| Part | Pass 1 | Pass 2 |
|---|---|---|
| Unit core (`run_tests.py --core`, 4 lanes, 649 tests, 0 failed, 1 known skip) | 120.6 | 99.3 |
| `check_all.py --core --jobs 4` (51 rows: 50 PASS, gen-headers SKIP, no classes.csv) | 47.8 | 38.2 |
| Smoke (`smoke.py run`: 2 makes + 8 jobs 8/8 PASS, memory compare equal, baseline equal) | 121.6 | 137.0 |
| **Core total** | **290.0** | **274.5** |

- Gate: the slower total, 290.0 s, is under 540 s, so nothing was cut. The cut list was not used.
- Smoke matched `config/harness/smoke_baseline.json` in both passes: the same patches (Fates 18cf5416..., Seal
  00066ed7...) and the same job and memory hashes as round 67's proof run (103.9 s). It ran slower here (121.6 s and
  137.0 s): the slowest job, cq-B016-all1, took 77-86 s against 65 s in the proof run.
- Full suite, same day: `run_tests.py --full` ran 671 tests in 189.4 s wall on 4 lanes (lane walls 187.7 / 188.7 /
  172.4 / 170.2 s; 0 failed, 1 skip). Plain `python -m unittest discover -s tests -t .` ran 671 tests in 985.3 s: OK
  (skipped=1). It ran last, after every code change. The id set of `run_tests.py --full --list` equals plain
  discover's id set, 671 = 671, checked with build/r67/calibrate2/count_discover.py.
- The one skip in every run is `test_check_all.RowCache.test_real_cache_specs_are_complete` (leaf_diff imports
  from outside its declared inputs; older than round 67).

### Measured earlier (round 67 part 1 calibrate, before smoke and before the part-2 tests; kept for comparison)

| Part | Run 1 | Run 2 |
|---|---|---|
| Unit core (630 tests) | 138.9 | 102.9 |
| `check_all.py --core --jobs 4` (50 rows) | 33.6 | 32.9 |
| Core total without smoke | 172.5 | 135.8 |

Part 1 full suite: plain discover ran 652 tests in 828.6 s, and before round 67 it ran 616 tests in 740.8 s.
`run_tests.py --full` ran 652 tests in 227.1 s.

## Files

`tools/release/run_tests.py`, `tools/release/fingerprints.py`, `tools/release/makes.py`, `tests/heavy.txt`,
`tests/core.txt`, `tests/_rando_makes.py`, `tests/test_run_tests.py`, `tests/test_seed_fingerprints.py`,
`config/release/seed_fingerprints.json`, `config/release/seed_changes.json`, `config/release/test_times.json`;
smoke: `tools/harness/smoke.py`, `config/harness/smoke_set.json`, `config/harness/smoke_baseline.json`,
`tests/test_smoke.py`, docs/harness/SMOKE.md (inputs copied once into the git-ignored `build/fixtures/smoke`).
