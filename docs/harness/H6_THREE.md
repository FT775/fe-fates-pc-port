# H6 as three numbers (round 14 measure)

**In plain words.** H6 plants one small bug at a time in the readable code and replays the game's recordings. Today
it is one percent: 2,214 of 4,140 planted bugs caught (53.5%). Grok's strategy note (docs/collab/STRATEGY_R14_GROK.md)
says that one percent counts two kinds of bugs as failures that recordings cannot catch: bugs on lines no recording
ever ran, and bugs that cannot change any answer. It proposed three numbers kept apart (adopted as F-026). This page gives those three
numbers from data that already existed (no new game run), plus the list of never-reached bugs by reason and the 237
"equivalent candidates" sorted into rule classes.

**Nothing here changes a gate.** The 90% H6 gate is unchanged; writers stay off; no planted bug is marked equivalent
(tools/harness/mutants_equivalent.csv untouched). The owner adopted this gate on 2026-11-16 (docs/DECISIONS.md F-026).

Command (read-only; it writes a file only with `--json`):

    python tools/harness/h6three.py                 # the three numbers, per file and per family
    python tools/harness/h6three.py --never         # + every never-reached planted bug, by reason
    python tools/harness/h6three.py --candidates    # + every equivalent candidate, by rule class
    python tools/harness/test_h6three.py            # its tests (made-up inputs, a few seconds)

Inputs: the sampled H6 `build/harness/h56/play/h6_sample.json` (round 13's run r13-h6s) and its mutants.csv files;
the H5 run it used (`runs/r13-h5/h5.json`, all 176,698 records); every host verdict under `build/harness/h6host/`;
round 13's integrate (`build/speed/replay/r13-off`, `r13-offc`, `build/parallel/r13-capn`); the reasons table
`tools/harness/h6three_reasons.csv` (written by hand from the source and the notes).

## The three numbers (round 13 data)

| # | What | Number | Notes |
|---|---|---|---|
| - | H6 as today (one percent) | **2,214 / 4,140 (53.5%)** | unchanged |
| 1 | Recordings, on lines a recording reached | **2,214 / 3,696 (59.9%)** | 444 planted bugs left out: H5 says no recording ran their line. Leaving out also the 178 on helper lines H5 has no line data for: 2,214 / 3,518 (62.9%) |
| 2 | Host test, on the same planted bugs | **2,864 / 3,139 (91.2%)** caught by the host test alone | 23 files have a host test; 13 files (870 planted bugs) have none and are listed, not guessed. "Records or host test" on those 23 files: 2,997 / 3,270 (91.7%) |
| 3 | Live compare, round 13 | **176,698 comparisons, 0 bad, 0 other differences** | per family below; cheat routes apart: 9,062, 0 bad |

### What surprised us (read this before quoting a number)

1. **"The sample did not reach it" is not "no recording reached it".** The sampled H6 keeps 64 records per function.
   Of its 852 "not reached" survivors, H5 (all records) counts **230 as on a line that ran in some recording**
   (per line; see Limits). Those stay in the count (number 1): the full records might catch them. Only 444 are confirmed never run; 178 more sit in small
   helper functions where H5 keeps only counts, not lines (they stay in the count too; the second figure leaves
   them out). So Grok's "about 69% on the six files" (which used the sample's own "not reached") is **62.1%**
   (374 / 602) when only confirmed never-run lines are left out, **66.3%** if the helper lines are left out too.
2. **The host tests catch almost everything the recordings catch.** Of 1,525 planted bugs the recordings catch and
   that have a host verdict, the host test misses only **2** (both in sheet_stats.c). So on files with a host test,
   "records or host test" is barely above "host test alone".
3. **All 237 candidates are still survivors**, both in today's sampled H6 and in today's host run (r14-three re-ran
   every one of them: all 237 still not caught). 36 more appeared in files that had never been host-tested before
   (below). They are not part of the 237 and nobody has sorted them.

### Number 1 per file (recordings, reached lines only)

"never" = left out (H5: no recording ran the line); "gap" = the sample did not reach it but a recording did (kept
in); "no data" = helper line, H5 has no line data (kept in). Worst first.

| File | H6 today | Reached lines only | never | gap | no data |
|---|---|---|---|---|---|
| stance_gauge.c | 2 / 12 (16.7%) | 2 / 8 (25.0%) | 4 | 1 | 0 |
| menu_config.c | 84 / 220 (38.2%) | 84 / 218 (38.5%) | 2 | 10 | 36 |
| item_value.c | 56 / 126 (44.4%) | 56 / 126 (44.4%) | 0 | 5 | 39 |
| growth_exp.c | 137 / 318 (43.1%) | 137 / 303 (45.2%) | 15 | 14 | 20 |
| formula_forecast.c | 63 / 150 (42.0%) | 63 / 129 (48.8%) | 21 | 9 | 7 |
| sheet_stats.c | 126 / 256 (49.2%) | 126 / 249 (50.6%) | 7 | 8 | 22 |
| skill_battle.c | 34 / 81 (42.0%) | 34 / 67 (50.7%) | 14 | 31 | 0 |
| formula_unit.c | 155 / 304 (51.0%) | 155 / 304 (51.0%) | 0 | 29 | 0 |
| stance_bonus.c | 129 / 247 (52.2%) | 129 / 239 (54.0%) | 8 | 2 | 33 |
| support_unit.c | 137 / 412 (33.3%) | 137 / 250 (54.8%) | 162 | 58 | 8 |
| move_terrain.c | 48 / 92 (52.2%) | 48 / 80 (60.0%) | 12 | 2 | 0 |
| battle2_rules.c | 38 / 71 (53.5%) | 38 / 62 (61.3%) | 9 | 6 | 0 |
| battle2_bonus.c | 25 / 40 (62.5%) | 25 / 40 (62.5%) | 0 | 1 | 0 |
| ai_area.c | 80 / 135 (59.3%) | 80 / 125 (64.0%) | 10 | 1 | 0 |
| ai_items.c | 76 / 146 (52.1%) | 76 / 118 (64.4%) | 28 | 4 | 0 |
| vein_tricks.c | 49 / 84 (58.3%) | 49 / 76 (64.5%) | 8 | 5 | 4 |
| vein_units.c | 53 / 85 (62.4%) | 53 / 81 (65.4%) | 4 | 8 | 0 |
| item_unit.c | 19 / 44 (43.2%) | 19 / 29 (65.5%) | 15 | 3 | 0 |
| skill_has.c | 67 / 114 (58.8%) | 67 / 101 (66.3%) | 13 | 3 | 0 |
| ai_value.c | 15 / 22 (68.2%) | 15 / 22 (68.2%) | 0 | 0 | 0 |
| support_records.c | 96 / 146 (65.8%) | 96 / 139 (69.1%) | 7 | 4 | 0 |
| sheet_unit.c | 96 / 149 (64.4%) | 96 / 131 (73.3%) | 18 | 6 | 0 |
| ai_permission.c | 139 / 223 (62.3%) | 139 / 189 (73.5%) | 34 | 3 | 6 |
| growth_rates.c | 50 / 80 (62.5%) | 50 / 68 (73.5%) | 12 | 4 | 1 |
| item_record.c | 59 / 84 (70.2%) | 59 / 80 (73.8%) | 4 | 1 | 2 |
| formula_stats.c | 16 / 21 (76.2%) | 16 / 21 (76.2%) | 0 | 0 | 0 |
| battle2_calc.c | 20 / 26 (76.9%) | 20 / 26 (76.9%) | 0 | 2 | 0 |
| move_occupy.c | 45 / 81 (55.6%) | 45 / 58 (77.6%) | 23 | 3 | 0 |
| triangle_tables.c | 32 / 42 (76.2%) | 32 / 41 (78.0%) | 1 | 1 | 0 |
| class_change.c | 69 / 92 (75.0%) | 69 / 87 (79.3%) | 5 | 2 | 0 |
| move_cost.c | 131 / 160 (81.9%) | 131 / 156 (84.0%) | 4 | 3 | 0 |
| ai_think.c | 9 / 14 (64.3%) | 9 / 10 (90.0%) | 4 | 1 | 0 |
| forces.c | 42 / 46 (91.3%) | 42 / 46 (91.3%) | 0 | 0 | 0 |
| flags.c, menu_danger.c, shop_price.c | 17 / 17 (100%) | 17 / 17 (100%) | 0 | 0 | 0 |
| **All** | **2,214 / 4,140 (53.5%)** | **2,214 / 3,696 (59.9%)** | **444** | **230** | **178** |

On reached lines, no file is at 90% except ai_think.c (9 / 10) and the small fully caught ones. **Leaving out the
never-reached lines does not get the recordings near 90%.**

### Number 2 per file (host test on the same planted bugs)

"host alone" = the host test's own catch rate on every planted bug it judged; "records or host" = caught by either
(kept apart, never added into H6); "rec only" = caught by the recordings, missed by the host test.

| File | Host alone | H6 survivors it catches | Records or host | rec only |
|---|---|---|---|---|
| formula_forecast.c | 146 / 150 (97.3%) | 83 / 87 | 146 / 150 (97.3%) | 0 |
| formula_stats.c | 20 / 21 (95.2%) | 4 / 5 | 20 / 21 (95.2%) | 0 |
| formula_unit.c | 229 / 304 (75.3%) | 74 / 149 | 229 / 304 (75.3%) | 0 |
| stance_bonus.c | survivors only: 110 / 118 | 110 / 118 | 239 / 247 (96.8%) | - |
| stance_gauge.c | survivors only: 10 / 10 | 10 / 10 | 12 / 12 (100%) | - |
| item_record.c | 78 / 84 (92.9%) | 19 / 25 | 78 / 84 (92.9%) | 0 |
| item_unit.c | 40 / 44 (90.9%) | 21 / 25 | 40 / 44 (90.9%) | 0 |
| item_value.c | 123 / 126 (97.6%) | 67 / 70 | 123 / 126 (97.6%) | 0 |
| vein_tricks.c | 82 / 84 (97.6%) | 33 / 35 | 82 / 84 (97.6%) | 0 |
| vein_units.c | 81 / 85 (95.3%) | 28 / 32 | 81 / 85 (95.3%) | 0 |
| menu_config.c | 220 / 220 (100%) | 136 / 136 | 220 / 220 (100%) | 0 |
| menu_danger.c | 4 / 4 (100%) | - | 4 / 4 (100%) | 0 |
| move_cost.c | 155 / 160 (96.9%) | 24 / 29 | 155 / 160 (96.9%) | 0 |
| move_occupy.c | 77 / 81 (95.1%) | 32 / 36 | 77 / 81 (95.1%) | 0 |
| move_terrain.c | 72 / 92 (78.3%) | 24 / 44 | 72 / 92 (78.3%) | 0 |
| sheet_stats.c | 226 / 256 (88.3%) | 102 / 130 | 228 / 256 (89.1%) | 2 |
| sheet_unit.c | 148 / 149 (99.3%) | 52 / 53 | 148 / 149 (99.3%) | 0 |
| skill_battle.c | 80 / 81 (98.8%) | 46 / 47 | 80 / 81 (98.8%) | 0 |
| skill_has.c | 110 / 114 (96.5%) | 43 / 47 | 110 / 114 (96.5%) | 0 |
| support_records.c | 127 / 146 (87.0%) | 31 / 50 | 127 / 146 (87.0%) | 0 |
| support_unit.c | 377 / 412 (91.5%) | 240 / 275 | 377 / 412 (91.5%) | 0 |
| growth_exp.c | 274 / 318 (86.2%) | 137 / 181 | 274 / 318 (86.2%) | 0 |
| growth_rates.c | 75 / 80 (93.8%) | 25 / 30 | 75 / 80 (93.8%) | 0 |
| **23 files** | **2,864 / 3,139 (91.2%)** | **1,341 / 1,614** | **2,997 / 3,270 (91.7%)** | **2** |

Below 90% on "records or host": formula_unit.c (75.3%), move_terrain.c (78.3%), growth_exp.c (86.2%),
support_records.c (87.0%), sheet_stats.c (89.1%). Most of what is left there is in the candidate classes below.

**Files with no host test (870 planted bugs; listed, not guessed):**

| File(s) | Planted bugs | Why no host number |
|---|---|---|
| ai_area.c, ai_items.c, ai_permission.c, ai_think.c, ai_value.c | 540 | h6host.py refuses the ai batch (another workflow owns it) |
| battle2_bonus.c, battle2_calc.c, battle2_rules.c | 137 | h6host.py refuses battle2 (another workflow owns it) |
| class_change.c | 92 | no h6host adapter for class_change (class_change_diff.py exists; no make_cases / compare split wired) |
| forces.c | 46 | growth_diff.py never names its functions: no host test |
| triangle_tables.c | 42 | the battle adapter's diff script (formula_diff.py) does not test this file |
| flags.c | 10 | no h6host adapter for the event batch |
| shop_price.c | 3 | no h6host adapter for shop_price |

### Number 3 per family (live compare, round 13 integrate)

| Family | Routes | Records | Match | Gave up | Incomplete | Bad | Other differences |
|---|---|---|---|---|---|---|---|
| Birthright (bt) | 31 | 104,296 | 101,820 | 1,461 | 1,015 | 0 | 0 |
| Conquest (cq) | 7 | 26,000 | 25,345 | 486 | 169 | 0 | 0 |
| Revelation (rv) | 12 | 44,390 | 43,381 | 726 | 283 | 0 | 0 |
| Options (opt) | 2 | 2,012 | 1,985 | 16 | 11 | 0 | 0 |
| **All, no cheat** | **52** | **176,698** | **172,531** | **2,689** | **1,478** | **0** | **0** |
| Cheat routes (apart) | 4 | 9,062 | 8,869 | 100 | 93 | 0 | 0 |

"Other differences" adds every mismatch kind the capture counts (r0, registers, memory, calls, escaped, unfaithful,
damaged). Sources: offline replay of 51 routes (141 runs, PASS), bt-ch25 live (1 run), cheat offline (21 runs, PASS).

## Never reached, by reason

The 444 never-run survivors plus the 178 on helper lines H5 cannot place (622 in all). Reasons come from
`tools/harness/h6three_reasons.csv`. F-025: do not play a chapter to light these up. "host" = what the host test
says about them (it catches most).

| Reason | Bugs | Files | Host catches |
|---|---|---|---|
| child unit (family record) | 193 | support_unit 153, stance_bonus 28, growth_rates 12 | 171 of 193 |
| AI order, band or item use no recorded chapter has | 82 | ai_permission 40, ai_items 28, ai_area 10, ai_think 4 | no host test (ai) |
| staff, tome or forged weapon no recorded fight used | 77 | item_value 39, formula_forecast 28, item_unit 9, triangle_tables 1 | 71 of 76 |
| game mode, difficulty or option the recordings do not use | 58 | menu_config 38, battle2_rules 9, growth_exp 7, stance_gauge 4 | 45 of 49 |
| skill no recorded unit had equipped | 49 | skill_battle 14, move_terrain 12, sheet_stats 9, item_unit 6, move_cost 4, skill_has 3, sheet_unit 1 | 41 of 49 |
| exp corner cases (unarmed foe, level cap, half-exp modes) | 28 | growth_exp 28 | 19 of 28 |
| move-range fill modes no recording used | 23 | move_occupy 23 | 23 of 23 |
| download (DLC) unit | 22 | support_unit 8, class_change 5, sheet_unit 5, vein_units 4 | 17 of 17 |
| condition or state no recorded unit had (stat loss, mood, halved HP, flyer move) | 20 | sheet_stats 20 | 20 of 20 |
| data lookup misses (no record, unknown skill record) | 16 | skill_has 10, item_record 6 | 14 of 16 |
| support corner cases (partner keeps points, S rank, record lists) | 16 | support_unit 9, support_records 7 | 14 of 16 |
| avatar boon/bane and support-rank corner cases | 13 | stance_bonus 13 | 13 of 13 |
| unit setting no recorded chapter uses (may-not-attack forces) | 12 | sheet_unit 12 | 12 of 12 |
| map gimmick type no recording has (standable gimmick) | 12 | vein_tricks 12 | 12 of 12 |
| not sorted yet | 1 | growth_rates 1 (the half_toward_zero helper) | 1 of 1 |

Two reasons named in round 13's note are missing here, and why: the "map not loaded" lines (move_terrain 81 and 88,
`return 0;` when a script asks the map size with no map) count as run in H5, so they are sample gaps and stay in
number 1; the type 24 / cannon tests of trick_is_access share line 91 with other `case` labels that did run, so H5
counts the line as run (see Limits: coverage is per line, a planted bug is per column). `--never` lists every id
with its line and source text.

## The 237 equivalent candidates, by rule class: FOR A PERSON TO JUDGE (F-026)

These are the survivors of rounds 11-13 that the host tests still miss after the sharper cases (80 + 114 + 43). A
class says what kind of change it is and what a person would have to check; it never says the change is harmless.
A rule the owner accepts could cover one class on one file; none is applied. `--candidates` lists every id.

| Class | Count | Files | What a person would check | Examples |
|---|---|---|---|---|
| boundary_compare | 80 | growth_exp 36, formula_unit 14, move_terrain 11, sheet_stats 10, formula_forecast 3, growth_rates 3, item_unit 3 | a compare moved by one at its boundary (`<` vs `<=`, `x < 0` vs `x < 1`): do both give the same value exactly there (a floor, a clamp, a value divided afterwards)? | forecast_hit-054 (`v < 0 ? 0` made `v <= 0 ? 0`), ai_terrain_score-013 |
| zero_offset | 29 | support_unit 28, move_terrain 1 | `+` made `-` on a field at offset 0 (`family + FAMILY_PARENT_A + FAMILY_PARENT_PERSON`, both 0): the same address. Is the offset 0 in every build? | unit_family_child-003, script_terrain_width-007 |
| call_argument_constant | 26 | formula_unit 23, sheet_stats 3 | a constant argument made one bigger (`unit_stat_value(..., 1u, 1u, 0)` made `2u`): does the callee treat both the same (a yes/no flag)? | unit_attack-023, hp_window_max_hp-003 |
| swapped_arguments | 17 | sheet_stats 11, stance_bonus 4, growth_rates 2 | two arguments swapped: does the callee only add them? | unit_grow-035, unit_attack_stance_bonus-012 |
| return_after_give_up | 17 | formula_unit 15, vein_units 2 | `if (fe_gave_up(ctx)) return 0;` made `return 1;`: the original answers instead, so the value is thrown away | unit_attack-007, unit_can_dragon_vein-009 |
| give_up_only | 15 | formula_unit 14, sheet_stats 1 | the readable code only gives up more (or later); never a wrong answer. The give-up counter (H6_SURVIVORS C.6) is the owner's option | unit_attack-022, unit_move-002 |
| no_arg_call_words | 12 | move_terrain 8, move_occupy 4 | an argument word of a call to `Map::Get(void)` made 1: does it really ignore its argument registers? | script_unit_at-000, script_terrain_height-000 |
| named_constant | 12 | formula_unit 8, formula_forecast 1, item_unit 1, skill_battle 1, vein_tricks 1 | a named constant made one bigger (a stat number in a cache check, a search mode tested only one way) | unit_avoid-035, trick_at_access-000 |
| clamp_limit | 8 | growth_exp 8 | a clamp's limit made one bigger (`clamp(x, 0, 9)` made `10`): can the value ever pass the old limit? | unit_exp_damage-007, unit_exp_damage-044 |
| impossible_value | 7 | stance_bonus 4, support_unit 2, vein_tricks 1 | compared against a value that never occurs (a pointer of 1, `0x100000000` against a 32-bit type) | stance_attack_bonus_edit-004, script_trick_test-003 |
| start_value | 7 | item_value 3, sheet_stats 3, formula_unit 1 | a starting or flag value made one bigger (`forged = 1` made `2`, `state = 0` made `1`): overwritten, or only tested as yes/no? | item_hit-006, unit_max_hp-001 |
| early_return_value | 6 | support_unit 4, vein_units 2 | the value of an early exit that is not a give-up: can that path run with its result used? | unit_support_level-006, script_unit_can_dragon_vein-013 |
| other | 1 | support_unit 1 | read by a person: `+ FAMILY_PARENT_B` (0x14) made `-`, a child-unit line no record or host case reaches | unit_is_uncle_aunt-039 |

Today: all 237 are still survivors in the sampled H6 and still missed by the newest host run. The classes are made
by a small rule list in h6three.py (`classify`); a person may move an item to another class.

**36 new candidates, not part of the 237 and not sorted by anyone:** this round's host run covered six files that
had never been host-tested (support_records 19, item_record 6, move_cost 5, skill_has 4, formula_stats 1,
sheet_unit 1). By the same rules: zero_offset 12, boundary_compare 5, swapped_arguments 5, early_return_value 4,
no_arg_call_words 4, other 4, named_constant 1, call_argument_constant 1. Some of them clearly can change an answer
(for example reliance_level-008 swaps a support and a rank level in `points_needed`); they are listed for a person,
not judged.

## How number 2 was made this round [high]

Before this round, host verdicts existed only for the H6 survivors of 16 files. To give number 2 on the same planted
bugs, `tools/harness/h6host.py --all --label r14-three` ran on every judged planted bug of r13-h6s for the 21 files
with an adapter (forces.c excluded: its functions are not in growth_diff.py), below-normal priority, about 1.5 hours,
4 then 6 files side by side, 3-4 jobs each. Every baseline was clean (0 mismatches), 0 id mismatches, 0 host
stillborn. The stance files keep their round 12/13 survivor verdicts (h6host_stance.py has no `--all`). Results:
build/harness/h6host/r14-three/ (csv + json per file); logs build/h6three/.

One by-hand step: on item_record.c two planted bugs (item_record-007 and -008, the item list's `node != 0` made
`node == 0` / `node != 1`) made the host driver loop. h6host.py's 300 s limit does not apply here, because
item_diff.py starts its driver with arguments and the limit is only added to argument-less calls. After 54 minutes
both drivers were stopped by hand; h6host recorded them as caught ("driver failed"), which is what its time limit
would have said ("runaway"). This is a gap in h6host.py for whoever owns it; it was not changed here.
**Round 18 (test tools):** the real cause was that item_diff.py runs its driver through sheet_diff.compare (and
ai_perm_diff through move_diff.compare, round 17's two 15-minute runaways): the borrowed module kept the real
subprocess.run. h6host.py now gives the time-limited run to every module under src/readable that the diff script
has imported (`patch_helpers`, at load and again before each verdict); tools/harness/test_h6host.py checks it
(a made-up runaway in a borrowed module is stopped; move_diff, leaf_diff and sheet_diff get the limit).

## Limits [high]

- Number 1's "never" comes from H5's aggregate gcov over each override's line span. Lines of small static helpers
  have no line data in H5; they are settled only when none or all of an override's helper lines ran, otherwise kept
  in the count and shown apart.
- The sample gaps (230) are survivors the 64-record sample did not reach. A full (exact) H6 run would show whether
  the full records catch them; the weekly exact cover is the place for that, not this page.
- Coverage is per line; a planted bug is per column. A line holding several `case` labels or a `? :` counts as run
  when any part of it ran, and a compiler may share one return block between `return` lines. So some "sample gaps"
  may really be never-reached parts of a line (for example trick_is_access line 91, move_terrain lines 81 / 88).
  This only makes number 1 lower than it could be (they stay in the count), never higher.
- A host verdict is matched to today's planted bug by id, operator, old and new text, and source line and column (or
  line number where the run kept no mutants.csv). Other agents changed src/readable/item/item.h during the run; each
  host run builds its own copy and its baseline was clean, so the item verdicts are for the item folder as built.
- The host test is not the game. Number 2 is never added into H6, and never stands in for a live compare.
- The reasons table and the classes are ours (a reading of the source); a person should check them before relying
  on them. The classes are a grouping, not a judgement.

Files: tools/harness/h6three.py, tools/harness/h6three_reasons.csv, tools/harness/test_h6three.py; results
build/harness/h6host/r14-three/, build/h6three/three.json (from `--json`), build/h6three/report*.txt.
