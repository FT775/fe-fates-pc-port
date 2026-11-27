# The smoke set: `tools/harness/smoke.py`

Round 67 (release part A, goal 5). One tracked command now does the robot smoke. Before this, each round copied a set of hand-made scripts forward.

**Round 84 (Seal edition split B, F-070): two sets.** The Vanilla+ set `config/harness/smoke_set.json` has 6 Fates jobs
(Birthright, Conquest, Revelation, each randomizer off and everything on) plus the memory compare. The Seal edition's
2 jobs moved to their own complete set, `config/seal/smoke_set.json` (`smoke.py --set config/seal/smoke_set.json run --lanes 2`;
check_all row `seal-smoke`); when and how it runs: docs/seal/CHECK.md. The default is now 2 lanes (`--lanes 2`), the
harness lane's share of the round's 3-robot cap. The text below is round 67's, with the Seal parts cut to pointers.

## What it replaces

| Hand-made (copied every round) | Now |
|---|---|
| `build/r6x/smoke/mkruns.py`: re-makes the everything-on runs | `smoke.py` `_make` worker (same recipe, cache OFF) |
| `build/r6x/smoke/brk.py` + `build/r59/e1/smoke.py` + `build/r58/check/rcheck.py`: one robot job (untracked drivers) | `smoke.py` `_job` worker (the same logic, now tracked) |
| `build/r6x/smoke/classify.py` → break.json | `judge_job` / `judge_all` (the same round-59 rules) |
| `build/r6x/smoke/extra.py`: off runs compared with the round before | the baseline compare (readback hashes per job) |
| `build/r62b/build/smoke/smoke.py` + `compare.py`: memory compare of the game exe, randomizer off | the `mem-off` task + the baseline compare |
| the hand-written lane files and the 8-job list | `config/harness/smoke_set.json` |

## The set (`config/harness/smoke_set.json`)
- **1 run, re-made each time with today's code** (rando cache OFF): Fates, every row on (round 59's `all1` recipe). Run id `r59fall1-37ec8c6e`. If the id changes, the answer changed, and that is a FAIL. (The Seal edition's run `seal-all1` is in its own set.)
- **6 robot jobs**: Birthright A011, Conquest B016 and Revelation C012, each with the randomizer off and with the run laid as the save's side file (until round 84 also Seal R011, now in the Seal edition's set). Each job:
  - selects the chapter from a base save;
  - goes through the preparations;
  - reads memory on the map: every patch cell must hold its NEW value, or its OLD value when the randomizer is off;
  - looks at one enemy and plays the first enemy phase;
  - makes a battle save and reloads it in a fresh server, where the units must be equal.
- **1 memory compare (`mem-off`)**: the installed game exe (a frozen copy), randomizer off, the new-game replay for 5200 frames. RAM is hashed at boot, at frames 3000, 4600 and 5200, and at the end.

## Inputs
- Every input is a **copy** in `build/fixtures/smoke/`. That folder is git-ignored, so no game data goes into git. Each input is listed in the set with its sha256:
  - the frozen boot-server and capture library;
  - the game exe;
  - 3 base saves;
  - the replay;
  - round 59's answer file;
  - (the Seal edition's set lists its own inputs, the Seal mod copy among them.)
- To make the copies, once: `python tools/harness/smoke.py fixtures`. It copies and never moves. It refuses a source whose sha differs from the set.
- A missing input, or one with the wrong sha, is a **FAIL** with a plain message, never a skip. Check without running: `smoke.py check`.
- The ROM is found and checked by `tools/paths.find_rom`.

## Running
```
python tools/harness/smoke.py [--set FILE] run [--out DIR] [--lanes N] [--write-baseline] [--baseline FILE] [--only a,b]
python tools/harness/smoke.py --list
python tools/harness/smoke.py selftest
python tools/harness/smoke.py record --jobs DIR --runs DIR --memory REPORT --out FILE
```
- **Output**: the default is `build/smoke/<timestamp>/`. One run per folder; a folder that is not empty is refused. The tool writes `results.json`, `table.md` and a printed table. The evidence for each job is `jobs/<name>/result.json` plus its PNGs. The runs are in `runs/<game>/<id>/`, and the memory hashes in `mem-off/report.json`.
- **Lanes**: `--lanes` sets the number of tasks at once (default 2 since round 84, at most 6; the round passes `--lanes 2` itself). The memory compare and the two makes start first. The jobs start once their make is done.
- **Safety**:
  - Every task runs headless and muted and exits by itself. It gets CREATE_NO_WINDOW and below-normal priority through subprocess flags, never `start /belownormal`.
  - Every task has its own Windows job object, which kills the whole tree; anything left dies when smoke.py ends, Ctrl+C included.
  - APPDATA, LOCALAPPDATA, TMP and the data folder are under the task's own folder.
  - `build/STOP_ROUND` is checked before every start and every half second. If it appears, everything is killed and the exit code is 3.
  - A visible window from any task kills everything and fails the run.
  - Every task has a timeout: make 600 s, job 480 s, memory 300 s.
  - Nothing is retried.
  - Only the frozen copies run, never `play/game` itself.
- **Exit codes**:
  - 0 = PASS: every job of the set PASS (6/6 for the Vanilla+ set, 2/2 for the Seal set), the memory compare PASS, and everything equal to the baseline;
  - 1 = FAIL;
  - 2 = usage error;
  - 3 = STOP_ROUND;
  - 4 = PARTIAL: an `--only` run whose part passed. It is never 0, because 0 means the whole set passed. A partial run never writes a baseline.

## Baseline (`config/harness/smoke_baseline.json`)
- Each set names its own baseline file (its `"baseline"` key: `config/harness/smoke_baseline.json` for the Vanilla+ set, `config/seal/smoke_baseline.json` for the Seal set); `--write-baseline` writes that file. A set may say `"memory": null` (the Seal set): it has no memory compare, and its PASS line reads `PASS: jobs N/N, baseline equal (no memory compare in this set)`.
- It holds hashes and verdicts only, no game values:
  - each run's id and patch sha256;
  - each job's verdict, its map frame, and the sha256 of its readback (map units, map cells, reload units, reload cells);
  - the memory hashes at every point.
- A difference is a FAIL that names the job (or `mem-off`) and the frame.
- `--write-baseline` writes the file, marked `NEW`, but only from a run that passed in full. When a baseline file is given and exists, the run must also agree with it first.
- With no baseline file present, `--write-baseline` writes one from any run that passed, without comparing it to anything. So a re-take must name a reference with `--baseline FILE`: the old baseline, or a `record` of an earlier round's smoke. Round 67 used `--baseline build/r67/smoke/r66_record.json`.
- A round that changes seeds on purpose (listed in `config/release/seed_changes.json`) re-takes the baseline with `--write-baseline` inside its round commit.
- `record` judges a finished hand-made smoke (for example `build/r66/smoke`) by the same rules, in the baseline format. That is how round 67 checked that the tool agrees with round 66 before writing the first baseline.

## Selftest
`python -m unittest tests.test_smoke` (or `python tools/harness/smoke.py selftest`, the check_all row `smoke-selftest`) runs without the game, using tiny child processes and a fake window watcher. It covers:
- pass, fail and timeout;
- a missing input and a wrong-sha input;
- a window, and STOP_ROUND (before a start and while running);
- the lanes cap, and a failed dependency;
- the round-59 job rules, the memory judge, and a baseline hash mismatch that names the job and the frame;
- the exit codes (a partial `--only` run is never 0), and the shape of the tracked set.

## In check_all (round 67 integrate)
- `smoke-selftest` (fast, in `--core`): `smoke.py selftest`, about 5 s, no game.
- `smoke-set` (slow; not in `--core` or `--fast`; runs alone at the end): `smoke.py run`, the live set, about 105 s on 5 lanes (round 67; round 84: 6 jobs, 2 lanes by default; check_all wants `PASS: jobs 6/6`; the Seal set is the row `seal-smoke`, edition seal). The release core runs smoke as its own step (docs/tests/CORE.md).
