# Several robot runs at once: tools/harness/parallel.py

**In plain words.** The test robot (docs/ROBOT.md) runs the game with no window, one run at a time.
`parallel.py` starts several of those runs side by side, each in its own scratch folder, and gathers
the results into one summary. It changes nothing in headless.py or harness.py: each run calls
`headless.run()`, the same function as `harness.py headless`, so the run itself is the same.
Tags: **[high]** measured or checked by a script, **[med]** strong indirect evidence.

## 1. How to use it

```bash
python tools/harness/parallel.py limits                                   # what the budget allows right now
python tools/harness/parallel.py runs --route title --route new-game      # two routes at once
python tools/harness/parallel.py runs --route new-game --copies 4 --markers   # 4 copies, checkpoint hits too
python tools/harness/parallel.py determinism --route title --copies 3     # h4a's "same twice" check, 3 at once
python tools/harness/parallel.py determinism --route title --copies 3 --serial-too   # and timed against one by one
python tools/harness/parallel.py search --route new-game --target title__ProcMyUnitEdit \
    --variant a=+4300:A --variant b=+4300:B --shots 4400,4600,4800 --frames 5000
python tools/harness/parallel.py build -- --boot     # tools/harness/build.py, one build at a time, low priority
python tools/harness/parallel.py clean               # delete build/parallel/
python tools/harness/parallel.py runs --route bt-ch8 --markers --keep --session S   # keep the job folder, then:
python tools/harness/parallel.py pack S S-1 bt-ch8-clear   # its in-game save -> build/harness/saves/bt-ch8-clear.zip
python tools/harness/parallel.py runs --route bt-ch2 --mode capture --only all --store-keep --session S
                                                     # keep every sampled record in build/parallel/S/records/ (H5/H6)
python tools/harness/test_parallel.py [--smoke]      # tests (fake children; --smoke adds the real title x3)
```

- **Start save.** Without `--save`, each run starts from its route's own `"save"` (the bt-* routes)
  or the empty save. Fixed in round 3: before, the default `new-game-empty` replaced the route's save,
  so a bt-* run started from an empty save (bt-ch2 then ended at memory `893128f2...`, not `059736d3...`).
- **runs**: a list of routes (`--route`, repeatable) and/or K copies of each (`--copies`). Every run
  starts from `--save` if given, else the route's own save, else `new-game-empty` (copied, never
  written). `--mode capture` works as in `harness.py headless`. `--markers` reads the screen markers
  and checks the route's checkpoints (config/harness/markers.json).
- **determinism**: K copies of one route side by side, then each compared with the first using
  h4a's own comparison, imported from headless.py: `compare_digests` on the savestate (guest memory
  byte for byte, metadata through `compare_meta`, run folder names removed) and equal instruction
  counts. Verdict DETERMINISTIC or DIVERGED, as in h4a step 1. `--serial-too` runs the same K again
  one after another and prints the time saved.
- **search**: tries several input scripts for one step at once and ranks them by the earliest shot
  frame where the target screen shows up in the memory markers. `--variant NAME=INPUT`; an INPUT
  that starts with `+` is added to the end of the route's own input. `--target` is a process class
  name as in markers.json (`--current-only`: it must be the current screen, not just alive).
  `--shots` and `--frames` change where the markers are read and how long the run is. Each marker
  dump is about 56 MiB of scratch per shot per run, so shots are capped at 12 (`--max-shots`).
- **pack** (round 4): `pack SESSION RUN NAME` packs the in-game save a finished `--keep` run left in
  `build/parallel/SESSION/jobs/RUN/` into `build/harness/saves/NAME.zip` through headless.pack_save (the same
  checks as `headless.py --pack`: a Completed run, save files no newer than its run.json, the 1 MiB cap). The
  only command that writes into build/harness/saves/; it makes a new zip there and never opens the others.
- **build**: runs tools/harness/build.py as a low-priority child; a lock file makes builds wait
  for each other (round 6: `OsLock`, a byte-range lock held by the OS, freed when the holder dies; before, an
  O_CREAT|O_EXCL file was empty for a moment and a waiter could remove it as stale). Building the engine still
  needs the owner's OK first; this does not change that.

**Capture runs (round 6).** With `--mode capture` a run passes only if boot.exe passed **and** its summary.tsv
files (one per stage for a cheat route) hold no `mismatch_r0`, `mismatch_regs`, `mismatch_mem`, `mismatch_calls`,
`b_escaped`, `unfaithful`, `escaped` or `damaged` record, and at least one summary.tsv was written
(`mismatch_regs` and `damaged` are offline verdicts that capture.c never writes; `hostmem` and `truncated` are not
bad). A real-play route never starts from a cheat save, named or not (docs/CHEATS.md rule 3): the job is refused
before it starts, and `pack` names and marks a cheat run's save `cheat-*`. A failing run
prints `CAPTURE FAIL <run> (<route>): N bad capture record(s): ...` and the session exits 1. After the run list,
one table per session adds the records up per run and in total (functions met, records, match, gave up,
incomplete and every bad kind), real-play runs and cheat runs in two tables (`summary.json` `capture_totals`:
`honest`, `cheat`); the summary.tsv files are copied to `results/<run>.summary.tsv` (`<run>.stage<k>.summary.tsv`
for a cheat route's earlier stages). Before round 6 the pass rule looked at boot.exe only: a reviewer's planted
bug (52 `mismatch_r0` records) printed PASS twice. Do not grep boot.log for MISMATCH as a check: its
`[fe-capture]` lines are capped and that planted run had none.

**Writer totals (round 8).** capture.c writes the writer gate's run totals into each summary.tsv as one comment
line, `# writers: log N; stores N; restored N; sessions N; refusals N; mode_refusals N; stray N; dropped N`
(src/readable/core/fe_writer.h `FE_WT_*`). `parallel.py` reads it into each run's capture totals (`writers`, added
over a cheat route's stages), prints `writers: <verdict> (...)` under each capture table, and writes
`summary.json` `writers` with the verdict read straight from the runs: **"no writer stored anything"**, or
**"WRITER STORED"** (any store, log entry or session in a capture run: the run FAILs with `CAPTURE FAIL ... the
writer gate stored in a capture run`, since the gate refuses every writer in capture mode). A summary.tsv without
the line (a library built before round 8) gives "NOT REPORTED", never a clean verdict. Tests:
`test_parallel.py CaptureVerdictTests.test_writer_totals_are_read` (planted stores, log entries and sessions;
missing and damaged lines; stages adding up) and the end-to-end session test.

**No options file in any child (round 8).** The worker's environment drops `FE_OPTIONS` and `FEF_OPTIONS` (any
case), and headless.py's `child_env` drops them again for boot.exe (docs/OPTIONS_WIRING.md section 6).
`test_parallel.py OptionsEnvTests`, each case also with the drop planted out.

**Kept game records (round 7).** `runs --mode capture --only all --store-keep` (or `--only name,0xADDR,...`) sets
FE_CAPTURE_ONLY to those overrides (every readable override of config/readable/functions.csv for `all`) and
FE_CAPTURE_STORE=keep, so capture.c keeps every sampled record (calls 1-16, then 32, 64, 128 ...; at most 48 per
function), not only bad ones. When the run ends its records (records.fecap, pages/, summary.tsv, callbacks.tsv,
run.json, boot.log) are copied to `build/parallel/<session>/records/<run>/` and outlive the job folder; they are the
input of `tools/harness/h56.py` (H5 coverage, H6 planted bugs; docs/HARNESS.md 4). `--store-keep` without
`--mode capture --only ...`, and `--only` without `--mode capture`, are refused (exit 3). The live compare and its
FAIL rule are unchanged: a store-keep run is still a capture run. Size: about 11 MB for the 6,900-frame
`bt-ch8-options`; game memory, build/ only. Tests: `test_parallel.py StoreKeepTests`.

**Cheat routes** (docs/CHEATS.md) run like any route; their rows carry `[CHEAT]`, are listed under "CHEAT runs"
and counted in their own table; `summary.json` names them in `cheat_runs`. `pack` names a cheat run's save
`cheat-*` and refuses any other name for it (and `cheat-*` for a real-play run). `pack SESSION RUN NAME extdata`
also packs the game's extra data (`user/extdata/<16 hex>/`), where a map's battle save is written (round 6).

Exit codes: 0 all runs passed (and the verdict is good), 1 a run failed or the runs diverged, 3 a
setup problem (missing boot.exe, library, ROM, bad route), 130 stopped by Ctrl-C. A search exits 0
when some variant reached the target, even if other variants missed or failed.

Output: `build/parallel/<session>/summary.json` (every run's row, pool numbers, verdict, the
%APPDATA% check), `results/<run>.json` (the full run.json), `shots/<run>.png` (contact sheets),
`logs/` (boot and worker logs of failed runs only). The per-run work folders are deleted when the
session ends (`--keep` keeps them).

## 2. Measured (2026-11-11, this PC, while the other robot was also working) [high]

`test_parallel.py --smoke` = `parallel.py determinism --route title --copies 3 --jobs 3 --serial-too`:

| | Wall time | Each run (boot.exe / whole run) | Result |
|---|---|---|---|
| 3 side by side | **27.1 s** | 7.9-8.0 s / 26.3-26.9 s | DETERMINISTIC (both pairs: guest memory identical, metadata only reordered, 13,443,408,000 instructions each) |
| 3 one after another | 63.8 s | 4.8-5.8 s / 18.0-22.8 s | DETERMINISTIC |
| | **x2.35 faster** | | the same memory hash `c3cbbe48...` in all 6 runs, the same as the robot's own title runs |

- Peak memory per title run: **330 MB**, 392 MB with `--markers` (the whole process tree, measured
  by the job object; a marker run of title also met all its checkpoints). The
  budget of 8 GB would fit about 20, so for now the 6-run cap is the limit, not memory.
- One run alone: 11 s whole, 4.8 s of it in boot.exe. A determinism run takes longer (18-23 s):
  most of the time outside boot.exe is Python work in headless.py after the game stops (decoding
  and hashing the savestate, and with `keep_meta` decoding it a second time, then the contact sheet)
  [med: from the timings, not profiled]. That work runs in parallel too, which is where most of the gain comes from.
  Round 3 (profiled, [high]): 49 million `min()` calls in the LZ4 decoder's overlapping-match loop
  (a zero run was copied one byte per step); fixed in headless.py, the after-game work is now about 1.5 s.
- `%APPDATA%\zakuro` and `%APPDATA%\3dsrecomp`: 37 entries, modification times and sizes the same
  before and after every session [high].
- A small real search (title with START vs without, shots 2500 and 2990, target `ProcEffect` as
  the current screen): the START variant reached it at 2500, the other never; 20.9 s for both.

## 3. Turning it down (or off)

The limits come from config/harness/resources.json (the owner's budget: 6 runs, below-normal
priority, 8 GB). The owner can turn them down for a shell without editing anything:

```bash
export FEF_ROBOT_JOBS=2            # at most 2 runs at once (1 = one after another)
export FEF_ROBOT_PRIORITY=idle     # idle | below_normal | normal (runs and builds)
export FEF_ROBOT_MEM_GB=3          # all runs together stay under 3 GB
```

(PowerShell: `$env:FEF_ROBOT_JOBS = "2"`.) A bad value is ignored and named in the output, so a
typo never raises the budget. `--jobs N` on the command line can only go lower than the budget.
`python tools/harness/parallel.py limits` prints what is in force and the free memory now.

## 4. How it keeps to the budget and stays safe

- **Priority.** Each run is started with BELOW_NORMAL_PRIORITY_CLASS (or the chosen class) and no
  window, and put in its own Windows job object that forces the same class on boot.exe and anything
  else it starts. Tested: the child and its own child both report the class [high].
- **How many at once.** A new run starts only if fewer than the cap are running, if the runs going
  (each counted at its peak, or at the estimate if that is higher) plus one more fit in the memory
  budget, and if free physical memory stays above 2 GB (`--reserve-gb`). One run always may go.
- **Memory measured and adapted.** The estimate starts at 1.5 GB (`--mem-per-run-gb`) and becomes the
  largest measured peak + 15% after the first run finishes (title: 330 MB peak, estimate 379 MB).
  One run is stopped if it alone goes over the whole budget, and its job object has a hard ceiling
  of 1.5 times that. If all runs together go over the budget, the newest is stopped and queued again
  (twice at most).
- **Ctrl-C** (or Ctrl-Break) stops every run and everything they started, and removes the work
  folders. The job objects are set to kill their process tree when parallel.py itself dies, even
  without a chance to clean up. Tested on the real command line with children and grandchildren [high].
- **Folders.** Everything is written below `build/parallel/<session>/`. Each run gets its own copy of
  the start save, of the shader-pipeline cache (from build/harness/localappdata, 24 MB) and its own
  APPDATA folder; boot.exe and the capture library are copied once per session, so a rebuild by the
  other robot never finds them locked. build/harness/ is only read. The owner's saves
  (%APPDATA%\zakuro) are never opened: each child's APPDATA points into its work folder and the
  summary checks the real folders before and after.
- **No new installs.** Standard library only; Windows calls via ctypes. psutil is used if it is
  installed (it is not here), and only on systems without job objects.

## 4a. The look-ahead helpers (tools/harness/robot/) are not parallel.py jobs (round 5)

Review 4 noted that `robot/bd.sh` started probe.py directly, outside this budget. All the look-ahead helpers
do (look.sh, lk.sh, lb.sh, st.sh, wk.sh, walk.sh, et.sh, endturn.sh, bd.sh, act.py, et2.py): their game runs
are `robot/probe.py` or `robot/auto.py`. They stay outside the pool on purpose: each step loads the savestate
the step before it kept (ZAKURO_LOAD), so a chain is one run at a time by nature, and a parallel.py run starts
from a save zip and has no savestate input. (Round 85: endturn.sh, lb.sh, lk.sh and st.sh are owner-PC scripts
that start with the owner's folder path. They are not in the public download, so et.sh and wk.sh, which call
st.sh, do not run there.) Since round 5 both go through `robot/budget.py` first:

- the priority class of resources.json (FEF_ROBOT_PRIORITY honoured, read with `parallel.load_limits`), set on
  the Python process; boot.exe inherits a below-normal or idle class;
- `build/harness/robot/probe.lock`, held only around one game run, so two look-aheads never overlap. Round 6
  (review round 5): it was an O_CREAT|O_EXCL file with the pid written after; a waiter that read it empty took it
  for a dead holder's, removed it and ran beside the holder. Now it is `parallel.OsLock` (the OS frees it when the
  holder dies; the pid inside is only for messages). Tests: `test_parallel.py LockTests`. (A first version held it for the whole process: act.py's auto.py
  child then waited on its own parent, a deadlock seen once in round 5 and fixed the same hour);
- boot.exe's APPDATA = `build/harness/robot/appdata` (headless.py already puts LOCALAPPDATA below build/).

Checked: `parallel.priority_of` on the helper's own process reads 0x4000 (below normal) after `budget.enter()`;
a probe of `title` through the new path ends at memory `c3cbbe48...` as always; the lock is gone after the run.
Honest note: until the end of round 5 the priority call silently failed (the pseudo-handle of GetCurrentProcess
passed as a C int is refused on 64-bit Windows; fixed with restype/argtypes), so round 5's look-aheads ran at
normal priority, one at a time. The parallel.py marker runs of round 5 were below normal.
A look-ahead is one more run beside a parallel.py session, which does not count it: keep such a session one
job under the cap while looking ahead. The shell helpers now call the tracked scripts in tools/harness/robot/
(some called the old scratch copies in build/harness/robot/).

## 5. Not done / limits

- Only `runs`, `determinism` and a small `search` were run for real; capture-mode runs side by side
  (`--mode capture`) work the same way but were not timed.
- The headless.py savestate work was most of each run's time; round 3 made it about 7x faster
  (docs/ROBOT.md 5: 6.0 s -> 0.8 s per 141 MB state, decoded once instead of twice with keep_meta).
- Several GPU runs at once (the hardware rasterizer) worked for 3; 6 at once was not measured.

## 6. Round 9 speed: measured memory estimate, longest first, capture jobs, --lib [high]

docs/collab/SPEED_AGREED.md items 3 and 6 (no owner OK needed) and the `--lib` the offline proof needed (item C,
docs/harness/H56.md 8). Every change is a new flag or a better first guess; with none of the flags a session runs the
routes in the given order, at the normal cap, from build/harness/lib, as before.

```bash
python tools/harness/parallel.py determinism --route bt-ch10 --copies 2        # first estimate = measured peak + 15%
python tools/harness/parallel.py runs --route a --route b --mode capture --longest-first --capture-jobs 10
python tools/harness/parallel.py runs --route bt-ch8 --mode capture --lib build/speed/replay/trees/T/build/harness/lib/<title id>.dll
python tools/harness/test_offline.py                                            # tests of these (and offline.py)
```

- **Memory estimate (item 3).** `--mem-per-run-gb` now defaults to the largest peak of an earlier passed run of the
  same routes in the same mode (summary.json files below build/parallel/ and build/evidence/) + 15%, the margin the
  pool already adds after a run finishes. A route never measured keeps the old 1.5 GB. The line `memory measured peak
  608 MB of bt-castle-forge (original) -> first estimate 0.683 GB` and summary.json `memory_estimate` say which.
  Round 8's bt-ch10 copies (r8bt-ch10a: peaks 722 MB, budget 2.7 GB) waited 1,714 ticks for the budget and ran one
  after the other (689 s); with 0.83 GB they fit side by side. Measured here (bt-castle-forge x2, determinism,
  FEF_ROBOT_JOBS=2, FEF_ROBOT_MEM_GB=2, the PC shared with the round-8 robots, so seconds swing a lot): old guess
  `--mem-per-run-gb 1.5`: at most 1 at once, 154 / 300 / 229 s; new default: 2 at once, 186 / 203 / 61 s (683 s
  against 450 s over three pairs, -34%); DETERMINISTIC every time (memory d6f814c6...). The pool's checks are
  unchanged: the budget with each run counted at its peak, the free-memory reserve, the per-run cap, requeue.
- **Longest first (item 6).** `runs --longest-first` orders the runs by the newest passed wall time of their route
  and mode, longest first; a route never run is placed by its frames at 200 frames a second. Off by default. On
  i8-cap's real wall times (19 capture runs) a list schedule gives 938 s in the given order and **689 s** longest
  first at 6 jobs (654 s, the bt-ch9-ore floor, at 10 or 12); the real i8-cap took 999 s.
- **Capture jobs (item 6).** `runs --mode capture --capture-jobs N` raises the cap to N (held to resources.json
  `night.max_parallel_runs`, 12; the owner's day budget is 6, so this is for night rounds or when asked) only while
  slots are free: the cap is max(normal cap, N - other boot.exe processes on the machine), counted every tick from
  the process list, this session's own runs excluded. Another 12-run session or a look-ahead holds the slots; it
  never goes below the normal cap and never past the memory budget. A process list that cannot be read means the
  normal cap. Refused (exit 3) without `--mode capture`.
- **--lib PATH** (runs, determinism): that capture library is copied into the session instead of build/harness/lib
  (and its harness_build.json beside it). Used for the planted-library live capture of H56.md 8.

Tests: `tools/harness/test_offline.py` (16, about 20 s: the measured estimate puts two 0.72 GB copies side by side in
2.7 GB and the 1.5 GB guess does not; longest-first order and its fallback; capture jobs with 0, 2 and 12 other runs
and a failing count; the night maximum; --lib copied; offline.py --selftest). `test_parallel.py`: 41 tests OK after
the change.

## Round 9 fixes (2026-11-14)

- **Run timeout scaled by route length.** `--timeout` now defaults to `run_timeout()`: 120 s + frames x 0.012 s
  (capture) or 0.006 s (original), times runs-at-once / 6 when more than 6 runs share the PC, never below 900 s or
  above 4 h. Round 8's six long routes hit the old flat 900 s at 12 capture runs; now bt-ch8 (78,900 frames) gets
  2,014 s at 12 runs, bt-ch11 (141,000) 3,504 s, rv-ch8 (182,200) 4,493 s; short routes keep 900 s. A given
  `--timeout` still wins. `test_run_timeout_scales_with_route_and_load` covers floor, cap, load and the override.
- **Ctrl-Break test under load.** `test_ctrl_break_on_the_command_line` waits up to 180 s for the 6 processes,
  sends the break again if the first is lost, waits 60 s for the children to die, and prints the output on failure.
  `test_parallel.py`: all tests OK (42).
- **Capture library swap** (`build.py --swap`, also `parallel.py build -- --swap`): builds into build/harness/next,
  then puts the DLL and manifest into build/harness/lib (or `--out`'s lib/): manifest removed first, the old DLL
  renamed aside (Windows lets a loaded DLL be renamed, not overwritten), the new DLL copied in by .tmp + rename, the
  manifest last; asides no longer held are deleted. A look-ahead's boot.exe holding the old DLL no longer stops the
  link (round 8 lost 357 s and swapped by hand). Self-test: the swap with the old DLL really loaded (a copy of
  python3.dll through LoadLibrary): the new DLL in place, FRESH, the held one kept aside; planted bug "no rename
  aside" -> PermissionError, caught.
- **build.py --selftest** stages only git-tracked src/readable files: another area's untracked work in progress
  (with or without registry rows) is left out of the self-test's staging and its addresses out of the marker gate
  (named in one line). New checks: a `writer` row is never compared with the staged markers (planted bug: writer rows
  compared -> caught), a skipped source is not staged and its markers leave the gate (planted -> caught). 22 checks.

## Round 10 fixes (2026-11-14)

- **First-run memory estimate from a similar route.** If a route has no measured peak in this mode,
  `measured_peak_mb` now uses the largest passed peak of its family (`route_family`: `bt`, `cq`, `rv`, or the
  route's first word), plus 15%. Round 9's first bt-ch12 copies ran one after the other on the 1.5 GB guess, though
  bt routes peak at 366-722 MB. Now a new bt route gets about 0.81 GB and two copies fit side by side in 2.7 GB. If
  no route of the family was measured, the 1.5 GB guess stays, and the pool still adapts after the first run. The
  summary's `memory_estimate` names the route it borrowed from ("like bt-ch10"). Test:
  `test_new_route_uses_its_family`. Planted bug (no family) caught.
- **run_timeout doc/code mismatch fixed.** `Session.job` had its own flat 900 s default. Callers that did not pass
  a timeout did not get the documented scaled limit. Now the default is `run_timeout(route, mode, 1)`. Also now
  documented in the code and `--timeout` help: the timeout is boot.exe's limit inside the worker, and the pool
  kills the worker 120 s later (the worker's start, copying results, clean-up). So a run's wall limit is timeout
  + 120 s. Test: `test_session_job_default_timeout_is_run_timeout`. test_offline 18 OK, test_parallel 42 OK.

## Round 12 (2026-11-16): H5 lanes and the offline plan's two lines

- **H5's first pass now uses the job budget** (`h56.py h5 --jobs N`, default and cap FEF_ROBOT_JOBS /
  max_parallel_runs). N record folders replay side by side. Each lane writes its coverage counters to its own folder
  (GCOV_PREFIX), and `gcov-tool merge` joins them once at the end. They never share one counter folder, which would
  mix the counts. On round 11's 88 folders: 179 s at 12 lanes against 363 s serial. The replay part went from 276 s
  to 73 s, and the result is identical (docs/harness/H56.md section 10). One tasklist sample during the run showed
  about 10 MB working set per replay.exe. That is one reading, not a measured peak. The check_all `h56-h5` row gets the lanes with no change to the row (it passes no
  `--jobs`).
- **offline.py plan** prints PLAN LINE 1 (routes), PLAN LINE 2 (overrides, and on which routes they must play live),
  and a LIVE TOTAL. `--extra-sessions r12-cap-*` counts the batch's own capture as records, so the old routes stay
  offline once the new readers are captured once (H56.md section 10).

## Round 13 (2026-11-16): 0-record runs kept, capture stamp, keep-empty

- **A store-keep run that kept 0 records leaves records/<run>/** (`keep_records`). capture.c writes no records.fecap
  when nothing it watched was called. The folder now still gets run.json (the watched `only` list, the library
  hash) and summary.tsv, so offline.py plan counts those overrides as "watched, never called" (decided, 0 records)
  instead of NEW. A cheat route's stage folder is kept the same way when it has a summary.tsv.
- **Capture stamp in every records/<run>/run.json**: `capture_targets_sha256` and `capture_manifest_library_sha256`
  (the library's harness_build.json, read at `stage()`), `capture_git_head`, `capture_records_fecap`. run.json keeps
  the run's own modification time, which offline.py compares with later route and save changes. offline.py plan
  takes each session's targets.csv from this stamp (H56.md section 11).
- **`parallel.py keep-empty SESSION`** backfills an older session's 0-record folders from results/<run>.json and
  results/<run>[.stageK].summary.tsv. No game runs. It writes only below build/parallel/SESSION/records/, never
  touches an existing folder, and refuses a run whose summary.tsv counts records but has no folder. run.json gets
  the targets.csv hash from a kept build manifest of its library (`find_manifest`) when there is one, and the time
  of its summary.tsv. Done for r12-cap-weapon_rank: 57 folders (54 runs plus 3 cheat stage0).
- Tests: test_offline.py `ZeroRecordTests` (keep_records, keep-empty, the plan's refusal), test_parallel.py 42 OK.
