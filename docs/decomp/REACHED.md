# Robot-reached game functions (F-038 choice 3, round 43)

The first decomp job (F-038) is to count the game functions the robot's existing recordings already run. Two
helpers counted them in two independent ways; this page compares the two and gives the number to use.
No new play, no engine/Zakuro/cargo build. All lists are under `build/decomp/` (gitignored): names and addresses
from our own symbol files only, no game bytes, no disassembly.

## The number

**8,342 game functions** are reached by the robot's recordings (51% of the 16,312 on the game list,
`config/readable/candidates.csv`).

| | count |
|---|---|
| Method A (dynamic trace) | 8,491 |
| Method B (live records + static rules) | 1,897 |
| Found by both (agreed) | 1,824 |
| Found by A only | 6,667 |
| Found by B only | 73, of which 33 confirmed |
| A + confirmed B, before the library filter | 8,524 |
| minus functions `config/functions.csv` tags as library (ctr_sdk 112, molive 35, rvct_clib 10, cxx_runtime 6, zlib 1) | -164 |
| minus functions tagged `unknown` (set aside, not counted) | -18 |
| **Final (game-tagged only)** | **8,342** = 1,791 both + 6,518 A only + 33 B only |

F-038 covers game code only, so the 164 library-tagged rows that `candidates.csv` carries (both helpers' review
flagged them) are left out. 240 of the 266 readable overrides are in the final list; 8,102 are not readable yet.

The list: `build/decomp/compare/final_reached_game_functions.csv` (columns: function, address, group, module,
arm_or_thumb, reader_or_writer_guess, already_readable, found_by, routes_hit_count_A). The one-sided B rows with
the reason for each: `build/decomp/compare/one_sided.csv`. Totals: `build/decomp/compare/compare.json`.
Script: `build/decomp/compare/compare.py` (reads the two method folders, writes only `build/decomp/compare/`).

## The two methods

**A, dynamic trace** (`build/decomp/method-a/`). A trace copy of the 2026-11-18 capture library (same generated C,
same gcc flags, plus a forced-include header) marks one byte the first time each generated block runs. 49 routes
were rerun in original mode with `parallel.py --lib`; final game memory matched the proven runs on all 47 routes
that had an earlier hash (0 differ). A function counts when the block at its start address ran.

**B, live-anchored static closure** (`build/decomp/method-b/`). No runs. Reads every existing capture record
(371,285 records, 87 routes): the override itself, its caller (entry LR), return addresses found on the stored
stack pages, lookups and notes. Then two static rules add callees that are always called in a straight line from a
function's entry, and the single caller of a function whose address is never taken.

## Why they differ

**A only (6,667).** B can only see call stacks that lead into one of the 266 readable overrides, because capture
records exist only around those calls. Whole areas that never call an override are invisible to it: most UI,
drawing, sound, scripts, events, menus, the castle. Only 2,061 of the 6,667 are even inside B's upper bound
(everything reachable by direct calls from B's set); the rest are reached through indirect (virtual) calls or
from code B never anchors on. A sees every function whose start ran, so A is the main count. 518 of the A-only
functions ran on just one route.

**B only (73).** Sorted by reason:

| reason | count | counted? |
|---|---|---|
| Direct record evidence (entry LR, the record itself, summary rows) on routes A did not trace | 20 | yes |
| A ran blocks inside the function but never marked its start block (an A blind spot; see below) | 13 | yes |
| Stack-scan only, on routes A did not trace | 17 | no (plausible, not confirmed) |
| Stack-scan only, A traced the same route and never saw it (likely a stale return address or a data word) | 9 | no |
| Static rule only, A never saw it (8 of the 14 are online/Wi-Fi `link::` code, which the robot never uses) | 14 | no |

The 20 confirmed by direct evidence are mostly AI actions (`AIThink::ActionMind*`/`ActionMove*` for villages,
breakable walls and traps), terrain script calls and `Unit::GetAttackForTerrain`, all from chapters A did not
trace (cq-ch8 to 13, rv-ch10 to 26, bt-ch13, cheat-cq-ch17). So the uncovered chapters do add a little.

**A blind spot.** Method A's own totals list 58 game functions where inner blocks ran but the start block was never
marked (the function is entered in a way that does not start a new generated block). 13 of them are confirmed by B
and counted. The other 45 probably ran too but are not counted, because no second source confirms them.

## Split of the 8,342

By group (the batch file the notes use; "other" is everything outside the eight game batches):

| group | reached | writers (guess) |
|---|---|---|
| data (B1 data 73, item 18, skill 17) | 108 | 65 |
| unit (B2) | 253 | 204 |
| battle (B3) | 108 | 85 |
| map (B4) | 1,322 | 921 |
| AI (B5) | 130 | 101 |
| events (B6) | 448 | 273 |
| save (B7) | 58 | 45 |
| castle (F1) | 798 | 532 |
| other (X/other 3,335, X/ui 1,607, F2 dual 113, F4 live2d_game 51, F3 vein 11) | 5,117 | 3,498 |

**ARM vs Thumb.** All 8,342 are ARM; 0 are Thumb. All 225 Thumb functions in the registry are library code. So the
reached list needs no engine change for Thumb overrides.

**Reader vs writer guess** (static, from method A's store scan; method B's own guess used for the 33 B-only rows):
writer 4,460, writer-via-callee 1,264, reader 2,395, reader-unsure-indirect 223. On the 1,824 agreed functions the
two methods' guesses agree on 1,738 (1,088 writer/writer, 300 via-callee/via-callee, 315 reader/reader,
35 reader-unsure/reader). Treat "writer" as an upper bound: 119 of the 266 proven-reader overrides come out as
writers under method A's rule (cached fields, out-parameters, local structs). "reader" is the more trustworthy
label, apart from indirect calls.

**Already readable.** 240 of the 266 overrides are reached; 26 are not reached by these recordings.

## Counted time (F-027)

8,102 reached functions are not readable yet. Calendar days, working every day, no new chapters:

| proven per day | all 8,102 | readers first (2,487) | writers (5,615) |
|---|---|---|---|
| 2 | 4,051 days (about 11.1 years) | 1,244 days | 2,808 days |
| 5 | 1,620 days (about 4.4 years) | 497 days | 1,123 days |
| 10 | 810 days (about 2.2 years) | 249 days | 562 days |

The rates are the plan's (2 to 5 seen in recent rounds, 10 with helpers), not measured on this list.

## Writer groups (F-038 choice 4), largest first

Groups follow the batch files. Each needs one owner yes/no on a pass/fail summary; every writer in it still passes
the full gate alone.

| # | group | writers (guess) | largest classes inside |
|---|---|---|---|
| 1 | other | 3,498 (X/other 2,256, ui 1,119, dual 78, live2d 39, vein 6) | ProcSequence (75), BattleUnit (71), FaceInstance (39), BasicMenu (39) |
| 2 | map | 921 | map ProcSequence (76), SequenceBattle ProcSequence (72), map::Actor (29), FieldWorld (18), map::Target (18) |
| 3 | castle | 532 | castle::cut (42), CastleSeq (25), BuildingDispos::Data (15), CastleLowerDrawer (13) |
| 4 | events | 273 | event script calls (103), ChapterSequence (20), event (17), MainSequence (13), VariableManager (9) |
| 5 | unit | 204 | Unit (114), unit::Item (13), unit::Edit (11), UnitPool (11), unit::Enhance (9) |
| 6 | AI | 101 | AIThink (66), AIOrder (24), AICannon (5) |
| 7 | battle | 85 | Unit battle stats (31), BattleUtil (19), BattleInfo::Side (11), BattleCalculator (7) |
| 8 | data | 65 | Person (15), Job (14), Chapter (7), Item (5) |
| 9 | save | 45 | Backup (10), Backup ProcError (10), GameBackup (5) |

"other" and "map" are too big for one owner yes; they will need splitting by class (for example "all menu
writers", "all map sequence writers") before any writer in them is asked about.

## Coverage gaps

- Routes: A traced 49 routes, B read 87. Together 88 of the 119 in routes.json. Not covered by either: the 31
  opt-t* options-track routes (they need options_track.py's setup, which parallel.py removes, and have no capture
  records). 39 chapter routes were read only by B (bt-ch10 to 16, 18 to 20, 22 to 24; cq-ch8 to 13;
  rv-ch8 to 18, 23, 25, 26; cheat-cq-ch17 to 20, 26; cheat-rv-ch27). Method A's saturation curve (its last 24
  routes added 26 functions) and B's 20 confirmed extras from those chapters both say they add little, but a trace
  run of them (about 2 h robot time at 6 jobs, `--timeout 4000`) is the only measurement.
- The 45 A body-only functions and 17 B stack-only functions on untraced routes are probably real but not counted.
- Interpreted code is not traced; the whole game list is compiled ARM, so the effect should be small.
- Reader/writer is a static guess. Sorting writers properly needs a store trace or the harness memory compare.

No check_all row: no test was added.
