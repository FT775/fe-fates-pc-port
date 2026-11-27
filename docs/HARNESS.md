# The tier-4 harness for Fates: what is ready, what waits for the engine

**In plain words.** Tier 2 (3dsrecomp `verify`) runs each readable function once, on a made-up
state. The tier-4 harness runs the **real game** with a "capture" library: every so often it copies
the inputs of a call to a readable function, runs the game's own code and ours on that same state
(runs A and B), and compares the answers live. Records that disagree are kept and can be replayed
offline, without the game. It is how the Awakening port got real-state evidence for its readable
code (171 of 281 functions met, 0 mismatches).

The design, the verdict rules and the reasons are the Awakening port's (its docs/HARNESS.md). The
tools (tools/harness/, src/readable/core/capture.c, include/readable/fe_capture.h) are the same
code, made per-game. This file lists the Fates differences, what was tested here, and what cannot
run before the engine is built. Tags: **[high]** checked by a script, **[med]** strong indirect
evidence, **[low]** a guess.

Status 2026-11-11: **first real runs on Fates.** boot.exe and the capture library are built; the
`title` and `new-game` routes run headless from an empty save and are deterministic; h4a on
`new-game` passes; one short capture was kept and replayed offline (original vs original 10/10).
Stage B (same day): one Birthright campaign from the empty save through the Prologue, Chapters 1-6,
the route choice and My Castle (armory, convoy, support list), with forecast, Attack Stance, Pair Up and
dragon veins on the way; six bt-* routes, each from the packed in-game save of the piece before it, all
marker checkpoints met; h4a PASS on four of them with 0 mismatches over 1,903 live records (32 of 35
overrides met). What was reached, with evidence and times: [ROBOT.md](ROBOT.md). Problems met: [harness/SOLVED.md](harness/SOLVED.md).
Round 3 (2026-11-12): headless.py's savestate decode is about 7x faster (same hashes); four more
routes (`bt-castle-shop` shop, `bt-ch7`, `bt-ch8-support` support conversation, `bt-ch8-pair`), all
markers met and h4a PASS; 33 of the 35 committed overrides met over all runs, 0 mismatches among them
(ROBOT.md 4). parallel.py now honours a route's own start save; build.py's freshness check no longer races
when two h4a start together.
Round 4 (2026-11-12): two more routes, `bt-ch8` (chapter 8 cleared, real level-ups) and `bt-castle-forge`
(Smithy built and its refine menu opened; the forge itself refused for want of ore), both checkpoints all met
and their saves packed; marker runs now read levels, experience and stats (`state.levels`), forged weapons
(`forged`, `forge_max`, `forge_pairs`) and the castle's ore and food; `tools/harness/levelups.py` lists the
level-ups of a marker session; `parallel.py pack` packs a kept parallel run's in-game save (ROBOT.md 3, 7).
Round 5 (2026-11-13): two more routes, `bt-ch9` (Birthright chapter 9 cleared: Azura's Sing, the unit panel's
detail view by a touch input, a dragon vein) and `bt-ch9-ore` (Lottery Shop > 1 Coral, a second Iron Naginata, the
Smithy forges **+1**; the forge read sees rank 1 on the real weapon), checkpoints all met twice, same memory, saves
`bt-ch9-clear` and `bt-castle-ore` packed; markers self-test 25/25 (Item::IsWeapon's kind 8); the look-ahead
helpers keep to the budget through `robot/budget.py` (docs/harness/PARALLEL.md 4a); never-met readers: which route
meets which, and what the rest would take (ROBOT.md 3b).
Round 6 (2026-11-13, night): **a capture-mode `parallel.py` run now FAILS on any bad record** in its summary.tsv
(`mismatch_r0/regs/mem/calls`, `b_escaped`, `unfaithful`, `escaped`, `damaged`; `regs` and `damaged` are offline
verdicts capture.c never writes, kept so they would fail too) or when it wrote none, and `harness.py h4a` fails on
the same records in run A+B (it used to pass with MISMATCH records as "findings"), and every
session prints one table of capture records (real-play runs and cheat runs apart). The verdict of a live compare
is the summary.tsv, never a grep of boot.log (whose `[fe-capture]` lines are capped: a planted bug with 52
`mismatch_r0` records left no MISMATCH line there). The look-ahead lock (`robot/budget.py`) and the build lock are
OS-held locks (no race on an empty lock file); `markers.unit_levels` keeps two units with one person id; markers
self-test 28/28. New: the **cheat track** (docs/CHEATS.md, `tools/harness/cheats.py`): `cheat-*` routes poke the
robot's own test game between boot.exe stages (savestate in, patched savestate out; no engine change):
`cheat-forge-katana` (Iron Katana +1), `cheat-skill-proc` (a skill activation), `cheat-family` (the family
readers). Details: ROBOT.md 3c.
Round 7 (2026-11-13, day): **H5 and H6 on game records** ([harness/H56.md](harness/H56.md)). `parallel.py runs --mode
capture --only all --store-keep` keeps every sampled record of a run in build/parallel/<session>/records/;
`tools/harness/h56.py` replays them offline. Real play, all 15 bt-* routes: 17,818 records, 0 bad, original vs
original clean, offline = live on every record; **100 of 110 overrides met**; H5: own-body branches 330/549 (60.1%),
with every readable callee 1,214/2,564 (47.3%), each override from its own records only; H6: **865 of 1,822 planted
bugs caught (47.5%)**, under the 90% gate (Awakening's game records: 51.2%), so F-017's writers stay off. The cheat
track is scored apart (62 met, 522/1,254 caught). New route `bt-ch8-options`: the game's options screen and Units list
looked at, nothing changed (the 19 saved option bytes equal at every checkpoint); it meets the 8 option-item
GetValue readers (ROBOT.md 3d).
(2026-11-10: self-tests on fakes only.)

```bash
python tools/harness/harness.py --selftest          # fakelib: the whole pipeline, invented code + memory (76/76)
python tools/harness/harness.py --mutate --fake     # H6 planted bugs on fakelib (57/58 caught, 98.3%)
python tools/harness/gen_stubs.py --check           # targets.csv vs the readable registry (+ guard tags)
python tools/harness/gen_stubs.py --refresh         # rewrite the override rows from the registry
python tools/harness/build.py --check-setup         # what is missing for a real build (3dsrecomp, ROM, gcc)
python tools/harness/build.py --boot                # Zakuro's windowless boot.exe (engine/target/zakuro-test)
python tools/harness/build.py                       # the capture library (about 5 minutes)
python tools/harness/harness.py h4a --route new-game --save new-game-empty --run h4a-ng
python tools/harness/harness.py headless --run NAME --route title --mode original --save new-game-empty --markers
python tools/harness/markers.py --selftest          # process-tree walk + game-state reads on invented memory (31/31)
python tools/harness/cheats.py --selftest           # the cheat track: paths, FCRAM mapping, savestate patching, rules (23/23)
python tools/harness/cheats.py --check              # the cheat-* routes of routes.json against docs/CHEATS.md's rules
python tools/harness/levelups.py SESSION            # level-ups between the shots of a parallel.py marker session
python tools/harness/harness.py headless --run mk-bt-ch3 --route bt-ch3 --mode original --markers   # a route from its own start save
python tools/harness/headless.py --pack RUN NAME    # a finished run's in-game save -> build/harness/saves/NAME.zip
python tools/harness/parallel.py runs --route bt-ch2 --mode capture --only all --store-keep --session S   # keep game records
python tools/harness/h56.py h5 --sessions S [--label play|cheat]   # H5: coverage of each override from its own game records
python tools/harness/h56.py h6 --sessions S [--label play|cheat]   # H6: planted bugs replayed on those records
python tools/harness/h56.py --selftest              # record-folder rules (F-019), gcov JSON, call closure
```

---

## 1. Per-game settings and where they come from [high]

| Setting | Awakening (was in code) | Fates (now) | Source |
|---|---|---|---|
| Library name | `00040000000A0500.dll` | `0004000000179800.dll` | config/game.json `title_id` |
| Save folder title | `00040000000A0500` | `0004000000179800` | config/game.json |
| One-time guard routine | 0x00314438 (ARM) | 0x00302C6C `__cxa_guard_acquire` (**Thumb**) | config/readable/addresses.json `guard` |
| FE_CAPTURE_GUARD default | 0x00314438 | 0x00302C6D (odd: Thumb entry) | generated include/readable/generated/fe_game.h |
| Guard tag in targets.csv | "guard user (calls 0x00314438)" | "guard user (calls 0x00302C6C)" | gen_stubs.GUARD_TAG |
| Headless routes | tools/harness/routes.json (18 routes) | config/harness/routes.json (`title`, `new-game`, fifteen Birthright `bt-*` routes (round 7: `bt-ch8-options`), four `cheat-*` routes (docs/CHEATS.md); a route may name its start save) | per game |
| Screen markers | Zakuro patch 0001 (pictures) | memory reads, config/harness/markers.json (tools/harness/markers.py) | ROBOT.md 3 |
| Pipeline cache | %LOCALAPPDATA%\zakuro (the owner's) | build/harness/localappdata (LOCALAPPDATA set for boot.exe) | harness/SOLVED.md |
| WSL scratch | ~/fe13-wsl-scratch, fixed repo path | ~/<key>-wsl-scratch, repo = the script's own | tools/wsl/env.sh |

## 2. Guard users: found from code.bin, not asm/ [high]

The harness needs to know which readable functions call the one-time guard routine (such a
function needs a cold record as well as warm ones before it can be called REPLAY-CLEAN). The
Awakening tools grepped `bl func_00314438` out of the local asm/. That cannot work for Fates:

- the guard is Thumb, so ARM code calls it with `BLX imm`, which tools/gen_asm.py writes as a raw
  `.inst` word (no symbol);
- asm/ labels now carry config/functions.csv names (symbol-map names), not only func_XXXXXXXX.

`gen_stubs.guard_callers()` (and `mutate.writer_callees()`) now decode BL and BLX imm straight from
extracted/code.bin (`gen_stubs.call_target`, the H bit included). On Fates: **537 functions call
the guard** [high]; none of the 12 pilot overrides is one of them. The self-test plants BL/BLX calls
inside, between and after invented functions, a plain B, and a call to another routine.

A probe on the guard itself must use the odd literal 0x00302C6D (3dsrecomp marks a Thumb
override with address | 1). gen_stubs accepts an odd probe address only for the Thumb routines
named in config/readable/addresses.json; any other odd address is still refused.

## 3. What was run here, and the results [high]

| Check | Result |
|---|---|
| `harness.py --selftest` (fakelib pipeline, gen_stubs, build fake, headless, mutate operators) | 76/76 |
| `harness.py --mutate --fake` (H6 on fakelib) | 57/58 caught, 98.3% (same as Awakening) |
| `h56.py --selftest` (record folders: real play and cheat never mixed; gcov JSON; call closure) | 15/15 |
| `h56.py h5` on 15 real-play routes (round 7) | 100/110 met, 17,818 records, original vs original clean, offline = live 17,818/17,818; branches own 330/549, with callees 1,214/2,564 |
| `h56.py h6` on the same records | 865/1,822 caught (47.5%), 20 stillborn; cheat track apart 522/1,254 (41.6%) |
| `gen_stubs.py --selftest` / `--check` | 31/31; targets OK (12 overrides, 0 guard users, 0 probes) |
| `readable/check.py --selftest` (capture_test, undo_test) | 565/565, 554/554 |

Fixes made while porting (all in owned files): the two fake 3dsrecomp scripts read staged files
as UTF-8 (the generated table headers carry non-ASCII descriptions); harness.py and headless.py
append tools/ to sys.path instead of prepending it, so tools/build.py no longer shadows
tools/harness/build.py.

### 3.1 Round 8 (prep): writer prep and review fixes [high]

| Change | Where | Checked by |
|---|---|---|
| No robot child sees the PC options file: `FE_OPTIONS` and `FEF_OPTIONS` dropped (any case) from every boot.exe environment, the recapture replays and parallel.py's worker | headless.py `child_env`, recapture.py `replay_env`, parallel.py | headless self-test 64/64; test_parallel `OptionsEnvTests` (4, each with a planted removal) |
| A `writer` kind: registry and targets.csv rows for the four option setters and `config_write_options` (0x003BA714); a writer never has an override marker or probe | tools/readable/check.py, gen_stubs.py, build.py (writer rows are never staged markers), config/readable/functions.csv, config/harness/targets.csv | check.py `--selftest` 27/27 broken inputs (5 new, the override-marker-on-a-writer case checked by its own message); gen_stubs `--selftest` 39/39 (6 new); `build.py --stage-only` on a scratch copy: 110 markers, writers left out |
| The writer gate's run totals in every capture summary (`# writers:` line) and in `summary.json` `writers` | src/readable/core (fe_writer.h, runtime.c, writer.c, capture.c), parallel.py | capture_test 568/568; writer_gate_test 307/307, `--plant` 19/19; test_parallel `test_writer_totals_are_read`. Compiled into the library at the next `parallel.py build` (integrate) |
| Fates hook list and writer H6 plumbing | docs/harness/HOOK_LIST.md; mutate.py (`hook_rows`, `writer_callees`: code.bin calls + the "readable callees" column); harness.py `--mutate --writer-callees [--run NAME / --fake]`; h56.py `h6 --writer-callees` | mutate self-test (hook rows, callees from the column); `harness.py --mutate --fake --writer-callees` (H6 on the fakelib callees of a made-up hook list) |
| `harness.py report` never merges a suspect run as real play: no or unreadable run.json, a `cheat-*` route without the flag (Grok review 5 #1) | harness.py `default_report_runs` | harness self-test case 3c (9 run folders) |
| h56.py: a folder per run (`<label>/runs/<id>/`), only a complete run updates `<label>/h5.json` / `h6.json`; any label (one starting with "cheat" is the cheat track) | h56.py | h56 self-test 29/29 |
| H6 speed: source files side by side, at most `--jobs` processes over all of them, baseline replays side by side | h56.py `--files-at-once`, mutate.py `set_process_limit`, `par_baseline` | same 238 mutant verdicts old vs new (docs/harness/H56.md section 6) |
| opt-* real-play routes: the game's own options screen changed, battle save, reload | config/harness/routes.json, markers.json (opt-* keys) | docs/harness/OPT_ROUTES.md |

## 4. What needed the engine built first (owner's OK, done 2026-11-11 for H3 and H4a; see ROBOT.md)

In order (Awakening milestones H3-H5):

1. **H3, capture library**: `python tools/harness/build.py --rom "<cci>"` needs
   engine/target/3dsrecomp/release/3dsrecomp.exe (`tools/engine/engine.py build 3dsrecomp`). It
   stages the 12 pilot overrides + capture.c in original mode and builds
   build/harness/lib/0004000000179800.dll. Then `harness.py abi` (stand-in header vs the real
   recomp.h) and `harness.py smoke`.
2. **H4a, headless runs**: needs Zakuro's boot.exe (engine/target/zakuro-test/...), a PLAY save
   backup of Fates, and real routes. config/harness/routes.json has only `title`, with timings
   copied from Awakening and marked `"verified": false`. TODO: continue, a prologue (A000) route
   with one battle and forecast, a warm-battle route (enemy phase, Attack/Guard Stance), one per
   route split after chapter 6, and a My Castle route for castle:: functions.
3. **H5/H6 on game records**: real-state coverage and mutation on kept records. **Run 2026-11-13 (round 7,
   [harness/H56.md](harness/H56.md))**: `parallel.py runs --mode capture --only all --store-keep`, then
   `h56.py h5` and `h56.py h6`; real play and cheat track apart (F-019). H5: 100 of 110 overrides met, branches
   with callees 47.3% taken; H6: 47.5% of planted bugs caught on real-play records (gate 90%: **not met**; per
   override in H56.md 5). `harness.py --mutate --writer-callees` reads docs/harness/HOOK_LIST.md (round 8)
   and runs H6 on the writer slots' readable callees; H6 on a writer's own code needs a test build with that
   writer armed (owner OK A, docs/OPTIONS_WIRING.md section 10).

## 5. Known gaps

- The Awakening title timings were wrong for Fates, as feared: the real ones are in
  config/harness/routes.json (four prompts on an empty save, then the movie, START skips it) [high].
- `harness.py smoke` on the real Fates library did not finish (records grew past 107 MB in 18
  minutes; stopped). Game runs do not need it; open.
- Headless runs refuse any `.cia` beside the ROM except this game's DLC (`headless.refuse_cias`).
- `recapture.py` reads the save title from tools/play/play.py `TITLE_HEX` (the play area's file).
- mutants_equivalent.csv holds three fakelib rows from Awakening; they match no Fates mutant
  (the tool says so), harmless.
