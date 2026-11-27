# H6 survivors: sharper host tests on the worst files (F-025 "sharper tests, not more battles")

Round 13 (section C, first below) did six more files and measured a give-up counter; round 12 (section A) did the
next six worst files; round 11 (section B) did the four worst. Sections A and B are unchanged.

# C. Round 13 (h6-sharpen-3): six more files, and a give-up counter

**In plain words.** Same method as rounds 11 and 12: plant one small bug at a time in the readable code, replay the
game records, and look at the bugs no record notices (*survivors*). This round took the six next-worst files that
nobody else owns tonight, sorted their 295 survivors into "never reached" and "reached, not noticed", and ran every
one against the batch's host test. **The host tests already caught 249 of the 295; three new host cases catch 3
more; the other 43 look like bugs that cannot change any answer** (listed in C.5 for a person; none marked
equivalent here). It also measured a **give-up counter** (C.6): a check that flags a planted bug that only makes
the readable code give up more often. It is not armed; the numbers say what it would catch.

**H6 itself did not move** (it counts game records only; host cases add none). Today's sampled H6, on the current
records (round 12's, 172,499): **2,208 / 4,137 (53.4%)**; on these six files **374 / 669 (55.9%)**, before and
after. "Caught by records or by the host test" (kept apart, never added into H6) on these six files: **623 / 669
(93.1%) before, 626 / 669 (93.6%) after**.

## C.1 How it was run [high]

| Step | What |
|---|---|
| Sampled H6, before | `h56.py h6 --sample --sample-n 64 --budget-min 60 --cache --sessions r10-capb,r11-capn,r11-capo,r12-cap-class_change,r12-capn --h5 build/harness/h56/play/runs/r12-h5/h5.json --label play --jobs 6 --run-id r13-sharpen-before`: the same sessions and H5 as round 12's integrate H6 (r12-h6s), so the current records. **Warm: 35 cache hits, 0 misses, 4,170 verdicts reused, 93 s**; COMPLETE, **2,208 / 4,137 (53.4%)**, the same as r12-h6s (being complete it was published as h6_sample; same number) |
| Files chosen | the worst catch rates not done in rounds 11-12 and not owned by another agent: stance_bonus.c 52.2%, move_terrain.c 52.2%, move_occupy.c 55.6%, vein_tricks.c 58.3%, vein_units.c 62.4%, growth_rates.c 62.5%. Skipped: ai_items.c 52.1% and battle2_rules.c 53.5% (h6host.py refuses the ai and battle2 batches: other workflows own them), shop_price and castle_join (other agents tonight; not in this H6 yet) |
| Host H6 | `h6host.py --mutants <run>/mutants.csv --label r13-before --jobs 2` per file (new adapter: **map**, vein_diff.py, for the two vein files); stance_bonus.c through **h6host_stance.py**, which now takes stance_bonus.c as well as stance_gauge.c and runs in shards (`--shard K/3`, three side by side). Every baseline gave 0 mismatches first. Below-normal |
| Sharper cases | a `SHARP` list in move_diff.py (1 generator) and in vein_diff.py (1), each from its own random stream (seed xor 0x5EED13), so every old case is byte-for-byte the same; each adds n/3 cases (C.4) |
| Host H6, after | the same tools, `--label r13-after`, on the 46 survivors the host tests missed before |
| Sampled H6, after | the same command with `--functions` (the 31 overrides of the six files), `--run-id r13-sharpen-after`: cold (another agent changed h56.py and rebuilt the library meanwhile), 246 s, **374 / 669, every mutant's verdict the same as before** (checked id by id). PARTIAL by design, not published |
| Host tests after the change | move_diff 7,300 cases (7,200 before), **0 mismatches, 48 / 48 planted bugs caught**; vein_diff 3,333 cases (3,200), **0 mismatches, 35 / 35 planted bugs caught** |
| Give-up counter | h6host.py now writes, per mutant, `host_extra_giveups` (early give-ups of the planted copy minus the baseline's; report only, never changes the verdict). Run as `--label r13-giveup` on every survivor the records flag "gives up more" plus round 12's give-up-only list (C.6) |

## C.2 Survivors per file, today's records (sampled H6, N=64) [high]

| File | Caught / judged | Survivors | Never reached | Reached, not noticed |
|---|---|---|---|---|
| battle/stance_bonus.c | 129 / 247 (52.2%) | 118 | 43 | 75 |
| move/move_terrain.c | 48 / 92 (52.2%) | 44 | 14 | 30 |
| move/move_occupy.c | 45 / 81 (55.6%) | 36 | 26 | 10 |
| map/vein_tricks.c | 49 / 84 (58.3%) | 35 | 17 | 18 |
| map/vein_units.c | 53 / 85 (62.4%) | 32 | 12 | 20 |
| unit/growth_rates.c | 50 / 80 (62.5%) | 30 | 17 | 13 |
| **Six files** | **374 / 669 (55.9%)** | **295** | **129** | **166** |

Every file today, worst first (survivors: never reached / reached): stance_gauge 2/12 (16.7%; 5/5), support_unit
137/412 (33.3%; 228/47), menu_config 84/220 (38.2%; 48/88), skill_battle 34/81 (42.0%; 45/2), formula_forecast
63/150 (42.0%; 37/50), growth_exp 136/318 (42.8%; 49/133), item_unit 19/44 (43.2%; 18/7), item_value 56/126 (44.4%;
44/26), sheet_stats 125/256 (48.8%; 38/93), formula_unit 155/304 (51.0%; 29/120), ai_items 76/146 (52.1%; 32/38),
stance_bonus 129/247 (52.2%; 43/75), move_terrain 48/92 (52.2%; 14/30), battle2_rules 38/71 (53.5%; 15/18),
move_occupy 45/81 (55.6%; 26/10), vein_tricks 49/84 (58.3%; 17/18), skill_has 67/114 (58.8%; 16/31), ai_area
80/135 (59.3%; 11/44), ai_permission 139/223 (62.3%; 43/41), vein_units 53/85 (62.4%; 12/20), battle2_bonus 25/40
(62.5%; 1/14), growth_rates 50/80 (62.5%; 17/13), sheet_unit 95/149 (63.8%; 24/30), ai_think 9/14 (64.3%; 5/0),
support_records 96/146 (65.8%; 11/39), ai_value 15/22 (68.2%; 0/7), item_record 59/84 (70.2%; 7/18), class_change
69/92 (75.0%; 7/16), formula_stats 16/21 (76.2%; 0/5), triangle_tables 32/42 (76.2%; 2/8), battle2_calc 20/26
(76.9%; 2/4), move_cost 131/160 (81.9%; 7/22), forces 42/46 (91.3%; 0/4), flags 10/10, menu_danger 4/4.

## C.3 Before and after, on these six files [high]

| File | H6 (records), before = after | Host catches, before | after | Either, before | Either, after | Left: candidates |
|---|---|---|---|---|---|---|
| stance_bonus.c | 129 / 247 (52.2%) | 110 of 118 (39 of the 43 never reached) | 110 | 239 / 247 (96.8%) | 239 / 247 (96.8%) | 8 |
| move_terrain.c | 48 / 92 (52.2%) | 23 of 44 (6 of 14) | **24** | 71 / 92 (77.2%) | **72 / 92 (78.3%)** | 20 |
| move_occupy.c | 45 / 81 (55.6%) | 32 of 36 (26 of 26) | 32 | 77 / 81 (95.1%) | 77 / 81 (95.1%) | 4 |
| vein_tricks.c | 49 / 84 (58.3%) | 31 of 35 (16 of 17) | **33** | 80 / 84 (95.2%) | **82 / 84 (97.6%)** | 2 |
| vein_units.c | 53 / 85 (62.4%) | 28 of 32 (8 of 12) | 28 | 81 / 85 (95.3%) | 81 / 85 (95.3%) | 4 |
| growth_rates.c | 50 / 80 (62.5%) | 25 of 30 (17 of 17) | 25 | 75 / 80 (93.8%) | 75 / 80 (93.8%) | 5 |
| **Six files** | **374 / 669 (55.9%)** | 249 of 295 | **252** | 623 / 669 (93.1%) | **626 / 669 (93.6%)** | **43** |

As before, most "never reached" survivors were already caught by the host tests: 112 of the 129 before, 113 after.
The 16 left are all candidates in C.5. Of the 46 survivors the host tests missed, 3 could be caught and are caught
now. If a person judges the 43 candidates equivalent, these six files would be at 100% "either".

## C.4 The sharper cases [high]

| Test | New cases | Catches | Real-play path that would reach it |
|---|---|---|---|
| move_diff.py `gen_score_cap` | ai_terrain_score for a unit that is not a flyer, on a tile whose score adds up to exactly 61 .. 66 (mostly 63 and 64), the "lockpick" attribute bit on or off | ai_terrain_score-032 (the clamp's test `score > 63` made `score > 64`; only a score of exactly 64 tells them apart) | a tile with about 59 avoid or more: no terrain of the game has it; host only |
| vein_diff.py `gen_is_access_types` | trick_is_access on gimmick types 24, 23, 13, 14, 1, 5, 8 asked about a tile inside the area, and types 28, 29, 25 .. 27 asked about the tile a cannon of that size and side is used from | trick_is_access-019 (`case 24` made `case 25`: a type 24 gimmick then answers "none"); trick_is_access-003 (the cannon test `type - 25u <= 2u` made `<= 3u`: type 28 then answers by the cannon rule) | -019: a chapter whose map has a type 24 gimmick, with a unit asking about a tile inside it (no record reached that line; which chapter has one is not known yet). -003: a type 28 gimmick (SetDeploy "first listed position") asked IsAccess at its cannon tile, which needs a search of any type over it; host only as far as we know |

"Never reached" lines and what in real play would reach them (the host tests catch these already):
stance_bonus 144-145, 156-159, 189-193: **child units** (the family record paths; paralogue children); 78, 80, 87,
89, 115: the avatar's boon / bane change when both name the same battle number or none, the 5/3 and 3/5 scaling
when one names number 1, and the Guard Stance +1 at support rank 4 or more (an avatar paired at S / A+ rank).
move_occupy deploy_is_fill 88-101: a move-range fill through a tile holding a unit when the deploy's mode has the
"pass test" (bit 4) or the "ally test" (bit 14); the records reached those tests only twice and never past them.
move_terrain 166-169: an AI unit with the "lockpick" pairing skill scoring a tile with attribute bit 8; 81 / 88: a
script asking the map size with no map loaded. vein_tricks: maps with cannons (types 25-27), ring gimmicks (9, 10)
or "standable" gimmicks (29). vein_units: **download persons** (DLC units) and the "vein: download only" state bit.
growth_rates: child units' family growth and limit. None needs a cheat save; F-025 says do not play for coverage.

## C.5 Candidates for a person to judge (not marked equivalent) [med: the reasoning is ours]

None is in tools/harness/mutants_equivalent.csv; a person decides. Ids from
build/harness/mutate/game-h6play-r13-sharpen-before-<file>/mutants.csv.

**move_terrain.c (20)**
- 8: the four argument words of the `Map::Get(void)` guest call (`guest_call(ctx, MOVE_MapGet, 0u, 0u, 0u, 0u)`)
  made 1u: the function takes no arguments: script_terrain_height-000, -001, -002, -003; script_terrain_width-000,
  -001, -002, -003.
- 1: script_terrain_width-007: `G_MapImage + MAPIMAGE_WIDTH` made `-`; MAPIMAGE_WIDTH is 0.
- 8: ai_terrain_score's floors `x < 0 ? 0 : x` on avoid / defence / heal at their boundary (`<=`, `< 1`):
  -013, -014, -016, -017, -019, -020; and `defense < 0 ? 1` / `heal < 0 ? 1` (-018, -021): the value is then
  divided by 5 or 10, and 1 / 5 = 0 / 5, 1 / 10 = 0 / 10.
- 3: the final clamp at its boundary (`score <= 0`, `score < 1`, `score >= 63`): -028, -029, -031.

**stance_bonus.c (8)**
- 4: the block and the column swapped in a call that only adds them (`block + column + stride * i`):
  unit_attack_stance_bonus-012, -013; unit_guard_stance_bonus-024, -025.
- 2: `type == 0xFFFFFFFFu` made `0x100000000u` (never equal to a 32-bit type): with type 0xFFFFFFFF the next tests
  still answer 0 (a battle number of -1 returns 0; no other number reads as 0xFFFFFFFF): stance_attack_bonus_edit-004,
  unit_attack_stance_bonus-032.
- 2: family_ready's `family != 0` made `!= 1` (unit_attack_stance_bonus-020, unit_guard_stance_bonus-034): a family
  pointer of 1 never occurs, and in the host test both sides then read unmapped memory as 0.

**growth_rates.c (5)**: unit_grow-035 and unit_stat_limit-018 (the Person and the stat swapped in a call that only
adds them); unit_stat_limit-006, -007, -009 (`cap < 0` made `<= 0` / `< 1`, `cap > 99` made `>= 99`: the same
value at the boundary).

**move_occupy.c (4)**: script_unit_at-000, -001, -002, -003 (the Map::Get(void) argument words, as above).

**vein_units.c (4)**
- 2: `return 0;` right after `if (fe_gave_up(ctx))` made `return 1;` (the value is thrown away):
  unit_can_dragon_vein-009, vein_command_attribute-000.
- 2: unit_pool_get's `return 0` for pool number 0 made `return 1`: script_unit_can_dragon_vein-013 (the script
  function returns before for numbers <= 0) and vein_command_attribute-015 (MapMind.unit_index 0: the game never
  builds the vein command without a unit; the host reads the unmapped unit 0 or 1 as zeros both ways).

**vein_tricks.c (2)**: script_trick_test-003 (`d == 0` made `d == 1`: d is a gimmick address or 0, never 1);
trick_at_access-000 (TRICK_SEARCH_ACCESS 2 made 3: trick_find only asks `search == TRICK_SEARCH_AT` (0), so 2 and 3
act the same).

## C.6 Give-up counter: proposed, not armed [high for the counts; the rule is a proposal]

A "give-up only" bug never gives a wrong answer: the readable code gives up, the original runs, the game stays
right; the readable code just does less of the work. Neither H6 nor the host test counts that today. Two checks
would; both are proposals for the owner (nothing in H6 or check_all changed):

1. **On the records (H6):** mutate.py's `judge` already says "gives up more (N fewer matches)" when a planted copy
   matches fewer records than the baseline. The proposal: count such a survivor as caught, in its own column
   (`by` = "gives up more"), reported beside H6. Today **37 survivors** in 11 files carry it (formula_unit 14,
   growth_exp 6, battle2_bonus 4, sheet_stats 4, menu_config 2, skill_has 2, and one each in ai_area,
   ai_permission, item_value, move_cost, vein_units). Sampled H6 would read **2,245 / 4,137 (54.3%)** instead of
   53.4%. Of the 37, 20 already give a wrong answer on some host case (caught by the host test), 6 are in batches
   h6host.py does not run (ai, battle2), and **11 are give-up only** (below).
2. **On the host test:** compare the planted copy's count of early give-ups (the readable code gave up although
   the original answered; the 4th count most diff scripts already keep) with the baseline's. h6host.py now writes
   that difference as `host_extra_giveups` (report only). On the 15 give-up-only survivors of rounds 12 and 13
   (A.5's 14 formula_unit ones and sheet_stats unit_move-002), checked as `--label r13-giveup`:
   - **"more early give-ups than the baseline" catches 11 of the 15**: unit_attack-022 (+903 cases),
     unit_attack_of_slot-006 (+548), -011 (+903), unit_avoid_of_slot-002 (+270), unit_crit-031 (+573),
     unit_crit_avoid-010 (+536), unit_crit_of_slot-002 (+280), unit_hit-037 (+362), unit_hit_of_slot-002 (+267),
     -010 (+362), unit_move-002 (+185). These are the same 11 the records flag (check 1).
   - The other 4 (unit_attack-018, -020; unit_attack_of_slot-007, -009) give up **later**, not more: the early
     count goes down (-12, -2) because the give-up moves into the callee. Only a check that flags **any** change of
     the give-up count would catch them (15 of 15), at the price of also flagging harmless changes.

   The diff scripts without that count (stance_diff, triangle_diff, vein_diff, class_change_diff) would need it
   added first. Arming either check is the owner's call (it changes what "caught" means); until then the 15 stay
   in A.5 as candidates.

## C.7 Limits [high]

- As in B.6: the host test is not the game, and "either" is never H6.
- The after run of H6 was cold (another agent changed h56.py and rebuilt the library during this round); every
  mutant's verdict was the same as before.
- vein_diff and stance_diff do not count unmapped reads, so a planted bug that only reads other unmapped memory
  (a pointer of 0 or 1) is not caught there (two candidates above).
- h6host_stance.py copies src/readable/ as it is at run time (another agent's unfinished file would break its
  baseline; it did not tonight).

Files: tools/harness/h6host.py (map adapter; `host_extra_giveups` column; vein_diff's two-value make_cases),
tools/harness/h6host_stance.py (stance_bonus.c, `--shard`, `--ids`); SHARP lists in
src/readable/move/tests/move_diff.py and src/readable/map/tests/vein_diff.py. Results:
build/harness/h6host/r13-before/, r13-after/, r13-giveup/ (csv per mutant, json per file; stance_bonus.shard*.csv);
build/harness/h56/play/runs/r13-sharpen-before/, r13-sharpen-after/; logs build/h6r13/.


# A. Round 12 (h6-sharpen-2): six more files

**In plain words.** H6 plants one small bug at a time in the readable code and replays the game records; a bug no
record notices is a *survivor*. This round ran the sampled H6 on today's records, took the six worst-caught files
that round 11 had not done, sorted each survivor into "the records never ran that line" and "ran it and did not
notice", and checked every survivor against the batch's host test (the game's own ARM code against the readable C on
made-up states). **Result: of the 472 survivors on these six files, the host tests already caught 355; three new
host cases catch 3 more; the other 114 look like bugs that cannot change any answer** (or only make the readable code
give up more often, which is safe). They are listed in A.5 for a person to judge; none was marked equivalent here.

**The H6 number did not move, and cannot move this way** (H6 counts game records only; new host cases add no game
records). Today's sampled H6: **2,138 / 4,045 (52.9%)**; on these six files **420 / 892 (47.1%)**, before and after.
What moved is the separate number "caught by records or by the host test" (never added into H6): on these six files
**775 / 892 (86.9%) before, 778 / 892 (87.2%) after**.

## A.1 How it was run [high]

| Step | What |
|---|---|
| Sampled H6, before | `h56.py h6 --sample --sample-n 64 --budget-min 60 --cache --sessions r10-capb,r11-capn,r11-capo --h5 build/harness/h56/play/runs/r11-h5b/h5.json --label play --jobs 6 --run-id r12-sharpen-before`, in the live tree (no frozen snapshot needed this time). These are the newest records with an H5: round 10's 38 routes, round 11's 12 new routes and its 38-route capture of the 31 new readers: **166,411 records; the sample kept 11,422** over 205 overrides in 34 files. The `--h5` is round 11's `r11-h5b` (aggregate coverage, `--no-exact`); H6 reads only its list of overrides with a MATCH record. Every file was a cache miss (tools, library, records changed), so it ran cold: **39 min, COMPLETE, 2,138 / 4,045 (52.9%)** over 201 overrides (33 stillborn, no problems). Being complete, it was published as build/harness/h56/play/h6_sample.json (latest.json `h6_sample` = r12-sharpen-before). Round 10's figure, on round 10's records, was 1,737 / 3,396 (51.1%) |
| Files chosen | the worst catch rates not done in round 11: stance_gauge.c 16.7%, formula_forecast.c 42.0%, item_unit.c 43.2%, item_value.c 44.4%, sheet_stats.c 48.8%, formula_unit.c 51.0%. Skipped: support_unit, menu_config, skill_battle, growth_exp (round 11 did them); class_change and weapon_rank (other agents' work tonight; no records yet, so not in this H6); ai_items.c 52.1% (the ai batch belongs to another workflow). move_terrain.c and stance_bonus.c (52.2%) come next |
| Host H6 | `python tools/harness/h6host.py --mutants <run>/mutants.csv --label r12-before` per file, as in round 11 (B.1). h6host.py now also takes the batches battle (formula_diff.py, for the formula_*.c files only), item, sheet and move. stance_diff.py has no make_cases / compare split, so stance_gauge.c has its own small tool, **tools/harness/h6host_stance.py**: each survivor planted into a copy of src/readable/ under build/readable/h6host/, then stance_diff.py's normal run (every function, -n 400, its own seed) on that copy. Every baseline (nothing planted) gave 0 mismatches first. Below-normal, 3 at once per file |
| Sharper cases | a `SHARP` list in formula_diff.py (2 generators) and sheet_diff.py (1), drawn from their own random stream (seed xor 0x5EED12), so every old case is byte-for-byte the same; each generator adds n/3 cases (A.4) |
| Host H6, after | the same tool, `--label r12-after --ids <the survivors the host test missed before>` |
| Sampled H6, after | the same command with `--functions` (the 32 overrides of the six files), `--run-id r12-sharpen-after`: cold again (another workflow rebuilt the library at 03:53 and changed h56.py / harness.py meanwhile), 8 min, **420 / 892, every mutant's verdict the same as before** (checked id by id). PARTIAL by design (`--functions`), so not published |
| Host tests after the change | formula_diff 7,100 cases, sheet_diff 5,800 cases: **0 mismatches of any kind** (item_diff and stance_diff unchanged) |

## A.2 Survivors per file, today's records (sampled H6, N=64) [high]

"Never reached" is mutate.py's gcov tag (the changed line ran in no sampled record).

| File | Caught / judged | Survivors | Never reached | Reached, not noticed |
|---|---|---|---|---|
| battle/stance_gauge.c | 2 / 12 (16.7%) | 10 | 5 | 5 |
| battle/formula_forecast.c | 63 / 150 (42.0%) | 87 | 37 | 50 |
| item/item_unit.c | 19 / 44 (43.2%) | 25 | 18 | 7 |
| item/item_value.c | 56 / 126 (44.4%) | 70 | 44 | 26 |
| sheet/sheet_stats.c | 125 / 256 (48.8%) | 131 | 38 | 93 |
| battle/formula_unit.c | 155 / 304 (51.0%) | 149 | 29 | 120 |
| **Six files** | **420 / 892 (47.1%)** | **472** | **171** | **301** |

Every file today, worst first: stance_gauge 2/12 (16.7%; 10 left: 5 never reached, 5 reached), support_unit 137/412 (33.3%; 275 left: 228 never reached, 47 reached), menu_config 84/220 (38.2%; 136 left: 48 never reached, 88 reached), skill_battle 34/81 (42.0%; 47 left: 45 never reached, 2 reached), formula_forecast 63/150 (42.0%; 87 left: 37 never reached, 50 reached), growth_exp 137/318 (43.1%; 181 left: 49 never reached, 132 reached), item_unit 19/44 (43.2%; 25 left: 18 never reached, 7 reached), item_value 56/126 (44.4%; 70 left: 44 never reached, 26 reached), sheet_stats 125/256 (48.8%; 131 left: 38 never reached, 93 reached), formula_unit 155/304 (51.0%; 149 left: 29 never reached, 120 reached), ai_items 76/146 (52.1%; 70 left: 32 never reached, 38 reached), move_terrain 48/92 (52.2%; 44 left: 14 never reached, 30 reached), stance_bonus 129/247 (52.2%; 118 left: 43 never reached, 75 reached), battle2_rules 38/71 (53.5%; 33 left: 15 never reached, 18 reached), move_occupy 45/81 (55.6%; 36 left: 26 never reached, 10 reached), skill_has 64/114 (56.1%; 50 left: 18 never reached, 32 reached), vein_tricks 49/84 (58.3%; 35 left: 17 never reached, 18 reached), ai_area 81/135 (60.0%; 54 left: 11 never reached, 43 reached), ai_permission 139/223 (62.3%; 84 left: 43 never reached, 41 reached), vein_units 53/85 (62.4%; 32 left: 12 never reached, 20 reached), battle2_bonus 25/40 (62.5%; 15 left: 1 never reached, 14 reached), growth_rates 50/80 (62.5%; 30 left: 17 never reached, 13 reached), sheet_unit 95/149 (63.8%; 54 left: 24 never reached, 30 reached), ai_think 9/14 (64.3%; 5 left: 5 never reached, 0 reached), support_records 96/146 (65.8%; 50 left: 11 never reached, 39 reached), ai_value 15/22 (68.2%; 7 left: 0 never reached, 7 reached), item_record 59/84 (70.2%; 25 left: 7 never reached, 18 reached), formula_stats 16/21 (76.2%; 5 left: 0 never reached, 5 reached), triangle_tables 32/42 (76.2%; 10 left: 2 never reached, 8 reached), battle2_calc 20/26 (76.9%; 6 left: 2 never reached, 4 reached), move_cost 131/160 (81.9%; 29 left: 7 never reached, 22 reached), forces 42/46 (91.3%; 4 left: 0 never reached, 4 reached), flags 10/10 (100.0%; 0 left: 0 never reached, 0 reached), menu_danger 4/4 (100.0%; 0 left: 0 never reached, 0 reached).

## A.3 Before and after, on these six files [high]

"Host" = the batch's host test catches the planted bug. "Either" = caught by a record or by the host test (kept apart
from H6).

| File | H6 (records), before = after | Host catches, before | after | Either, before | Either, after | Left: candidates |
|---|---|---|---|---|---|---|
| stance_gauge.c | 2 / 12 (16.7%) | 10 of 10 | 10 | 12 / 12 (100%) | 12 / 12 (100%) | 0 |
| formula_forecast.c | 63 / 150 (42.0%) | 82 of 87 (all 37 never reached) | **83** | 145 / 150 (96.7%) | **146 / 150 (97.3%)** | 4 |
| item_unit.c | 19 / 44 (43.2%) | 21 of 25 (14 of the 18 never reached) | 21 | 40 / 44 (90.9%) | 40 / 44 (90.9%) | 4 |
| item_value.c | 56 / 126 (44.4%) | 67 of 70 (41 of 44) | 67 | 123 / 126 (97.6%) | 123 / 126 (97.6%) | 3 |
| sheet_stats.c | 125 / 256 (48.8%) | 102 of 131 (all 38) | **103** | 227 / 256 (88.7%) | **228 / 256 (89.1%)** | 28 |
| formula_unit.c | 155 / 304 (51.0%) | 73 of 149 (13 of 29) | **74** | 228 / 304 (75.0%) | **229 / 304 (75.3%)** | 75 |
| **Six files** | **420 / 892 (47.1%)** | 355 of 472 | **358** | 775 / 892 (86.9%) | **778 / 892 (87.2%)** | **114** |

As in round 11, most "never reached" survivors were already caught by the host tests: 148 of the 171 (stance_gauge's
5 included). The 23 left are all in A.5 (mostly a `return 0` after a give-up, whose value is thrown away). Of the
117 survivors the host tests missed, only 3 could be caught at all, and they are caught now. If a person judges the
114 candidates equivalent, these six files would be at 100% "either".

## A.4 The sharper cases [high]

| Test | New cases | Catches | Real-play path that would reach it |
|---|---|---|---|
| formula_diff.py `gen_fhit_clamp` | forecast_hit with a plain weapon and hit - avoid exactly 101 (also 100, 102, 99, 1, 0, -1) | forecast_hit-058 (the clamp's test `v > 100` made `v > 101`; only 101 tells them apart) | a fight forecast whose raw hit is exactly 101 (a high-hit unit against a low-avoid enemy); no sampled record had one |
| formula_diff.py `gen_hit_none_cold` | unit_hit with no weapon while exactly one of its three caches is cold | unit_hit-001 (the guard test `!G10 \|\| !G20 \|\| !G30` made `!G10 \|\| (!G20 && !G30)`: the readable code then answered 0 where the game first fills its cache) | hardly any: the caches fill the first time any hit is shown; host only |
| sheet_diff.py `gen_max_hp_cap` | unit_max_hp of a unit whose HP adds up to 98 .. 102 under a limit of 100 or more, no boon/bane, no loss, no condition, no HP skill | unit_max_hp-062 (the cap test `value > 99` made `value > 100`) | a unit at 100 maximum HP before the cap: not in a normal game (class HP limits are lower); host only |

The "never reached" lines and what in real play would reach them (the host tests already catch these):
forecast_hit lines 51-53 and 75-93: a staff, hindering or not, in a fight forecast (a unit with a status staff
targeting someone); forecast_strikes 119-148: a magic weapon while the unit's condition bit 3 is set, distance 0, a
siege ("long range") weapon on the side that did not start the fight, the no-strike info bit, a staff or siege side
that is a stance follower, the no-double skill bit. item_hit / item_might / item_crit lines 49-61 and item_can_forge
145-163: a **forged weapon** in a fight, or the forge menu with an item that cannot be forged (the My Castle smithy).
unit_item_heal_amount 61-62: a unit with the better-medicine skill using a healing item with the "standing
medicine" bit. unit_range_max 38-45: the 0xFE range (no item of the game has it: host only) and a staff user with
the endless-staff skill. sheet_stats (unit_defense / unit_resistance 158-174, unit_max_hp 205-217, unit_move
247-294): rallies and tonics on that stat, the absorb skills, a mood bit, the HP-halving condition, the HP+5 skill,
the move rally, a paired unit's move, the flyer half-move conditions. formula_unit (unit_hit 154-158, unit_avoid
184-192, unit_crit 210): the hit / avoid flag words (person or class flags) and the avoid-down condition bit. None
needs a cheat save; F-025 says do not play for coverage.

## A.5 Candidates for a person to judge (not marked equivalent) [med: the reasoning is ours]

None is in tools/harness/mutants_equivalent.csv; a person decides. Ids from
build/harness/mutate/game-h6play-r12-sharpen-before-<file>/mutants.csv.

**formula_unit.c (75)**
- 15: `return 0;` right after `if (fe_gave_up(ctx))` made `return 1;` (a give-up replays the original, so the
  value is thrown away): unit_attack-007, -009, -031, -032, -033; unit_attack_speed-001; unit_avoid-002;
  unit_crit-015; unit_crit_avoid-002; unit_defense_speed-001; unit_hit-007, -011, -046, -047, -048.
- 14: a floor at 0 whose two sides agree at the boundary (`x < 0 ? 0 : x` made `x <= 0` or `x < 1`; `if (skl < 0)`
  the same): unit_attack-010, -011; unit_attack_speed-004, -005; unit_avoid-014, -015; unit_crit-016, -017, -020,
  -021; unit_defense_speed-004, -005; unit_hit-015, -016.
- 1: unit_crit-018: `skl = 0` made `skl = 1`; the next line halves skl, and 1 / 2 = 0 / 2 = 0.
- 21: stat_of's constant arguments `unit_stat_value(..., 1u, 1u, 0)`: the two bools made 2 (only read as true or
  false) and the rally kind 0 made 1 (no rally rule has kind 1; they are 9 .. 33): unit_attack-023, -024, -025;
  unit_attack_speed-010, -011, -012; unit_avoid-036, -037, -038; unit_crit-035, -036, -037; unit_crit_avoid-012,
  -013, -014; unit_defense_speed-010, -011, -012; unit_hit-038, -039, -040.
- 8: `STAT_LCK` made `STAT_LCK + 1`: stat_rule's `default:` is the luck rule, so 6 picks luck too: unit_avoid-001,
  -035; unit_avoid_of_slot-009; unit_hit-006, -035; unit_hit_of_slot-008; unit_crit_avoid-000, -001.
- 2: the rank-bonus argument 1 made 2 (read as true or false): unit_attack_for_terrain-000,
  unit_attack_for_terrain_of_slot-000.
- 14, **gives up more or later, never a different answer** (a cache test asks another stat's caches; an inverted
  "ready" test whose callee then gives up itself; `(!rank_bonus || ready)` made `&&`): unit_attack-018, -020, -022;
  unit_attack_of_slot-006, -007, -009, -011; unit_avoid_of_slot-002; unit_crit-031; unit_crit_of_slot-002;
  unit_crit_avoid-010; unit_hit-037; unit_hit_of_slot-002, -010. Note: unit_attack-022, unit_attack_of_slot-011,
  unit_hit-037 and unit_hit_of_slot-010 make the readable code give up on **every** call with the rank bonus on.
  That is still never a wrong answer (the original runs), so neither the records nor the host test can tell; a
  check that counts give-ups would.

**sheet_stats.c (28)**
- 11: `condition(ctx, unit, X)` swapped to `condition(ctx, X, unit)`: condition() reads unit + offset + byte, and
  the sum is the same either way round: unit_defense-042, -044; unit_resistance-042, -044; unit_max_hp-025, -027,
  -029; unit_move-056, -060, -062, -064.
- 10: boundary tests whose two sides agree at the boundary (`limit < value`, `value < 0` / `< 1` before
  `return 0`, `value > 99` made `>= 99`, `loss < 0 ? 0 : loss`, `value < 0 ? 0 : value`): unit_max_hp-042, -058,
  -059, -061; unit_move-015, -016, -018, -019, -048, -049.
- 3: `uint32_t state = 0;` made `= 1`: base_stat always overwrites it before it is read: unit_defense-014,
  unit_max_hp-001, unit_resistance-014.
- 3: hp_window_max_hp's call `unit_max_hp(ctx, unit, 1u, 0u, 0)`: 1u made 2u (read as true or false), the unused
  argument 0u made 1u, the rally kind 0 made 1 (only 8 counts): hp_window_max_hp-003, -004, -005.
- 1, gives up more, never a different answer: unit_move-002 (`with_extras && (cold ...)` made `||`: it then also
  gives up without the extras when one of those caches is cold).

**formula_forecast.c (4)**
- 3: the clamp `v < 0 ? 0 : v > 100 ? 100 : v` at its edges (`<` made `<=`, `v < 0` made `v < 1`, `>` made
  `>=`): forecast_hit-054, -055, -057.
- 1: forecast_strikes-023: `flags & SIDE_NO_STRIKE` made `flags & (SIDE_NO_STRIKE + 1)`: the extra bit is
  SIDE_INITIATOR (0x1), and that line sits inside `if (!(flags & SIDE_INITIATOR))`, so the bit is always 0 there.

**item_unit.c (4)**: unit_range_max-007, -008 (`half < 1 ? 1 : half`: `<=` and `< 2` agree at half = 1), -016,
-017 (`range < 10` made `<= 10` or `< 11`: the range is then set to 10, which it already is).

**item_value.c (3)**: item_crit-006, item_hit-006, item_might-006: `forged = 1` made `forged = 2`; `forged` is only
tested as true or false.

**stance_gauge.c**: none left (stance_diff catches all 10).

## A.6 Limits [high]

- As in B.6: the host test is not the game, and "either" is never H6.
- The before run used the library on disk at 03:00; another workflow rebuilt it at 03:53, so the after run used
  that one. Every mutant's verdict was the same in both.
- "Never reached" comes from the sample's own gcov baseline (the sample keeps every block the full record set
  reached, H56.md section 9).
- The `--h5` input was round 11's `--no-exact` H5 (aggregate coverage only); H6 reads only its MATCH list.
- h6host_stance.py copies src/readable/ as it is at run time; another agent's unfinished file there would break its
  baseline (it did not tonight).

Files: tools/harness/h6host.py (battle / item / sheet / move adapters), tools/harness/h6host_stance.py (new); SHARP
lists in src/readable/battle/tests/formula_diff.py and src/readable/sheet/tests/sheet_diff.py. Results:
build/harness/h6host/r12-before/, r12-after/ (csv per mutant, json per file; stance_gauge.csv);
build/harness/h56/play/runs/r12-sharpen-before/, r12-sharpen-after/; logs build/h6r12/.

# B. Round 11: the four worst files

**In plain words.** H6 plants one small bug at a time in the readable code and replays the game records; a bug no
record notices is a *survivor*. F-025 says: on the worst files, sort the survivors into "the records never ran that
line" and "the records ran it and still did not notice", and fix the first kind with sharper host test cases, not
with more battles. This round did that for the four files with the lowest catch rate. Result: **every survivor on
those four files is now caught by the records or by the batch's host test, except 80 that look like equivalent
mutants** (bugs that cannot change any answer). Those 80 are listed below for a person to judge. None was marked
equivalent here.

**The H6 number itself did not move, and cannot move this way.** H6 counts game records only. New host cases do not
add game records, so the sampled H6 is still **1,737 / 3,396 (51.1%)** overall and **385 / 1,031 (37.3%)** on these
four files. What changed is the second number below, "caught by records or by the host test", which is kept apart
and never added into H6.

## 1. How it was run [high]

| Step | What |
|---|---|
| Sampled H6, before | `h56.py h6 --sample --sample-n 64 --budget-min 60 --cache --sessions r10-capb --label play --jobs 6 --run-id r11-sharpen-before`, run in build/h6snap/r10 (the frozen round-10 tree, library and h5.json of H56.md section 9; its src/readable files equal today's for these four files, support_unit.c differs only in a comment). The cache did **not** apply: every file missed (`changed: tools(...), library, records`: the stored entries were keyed with other tool files), so it ran cold: 42.6 min, COMPLETE, 1,737 / 3,396 (51.1%). It gave exactly the round-10 N=64 result: the same caught/judged for every override and the same mutant rows for the four files |
| Records: current? | r10-capb (38 routes, 106,426 records) is the newest full capture with an H5. Round 11's chapter captures (bt-ch18..22, cq-ch10..12, rv-ch15..17) have no merged session or H5 yet, so they are not in this H6 |
| Host H6 (new tool) | `python tools/harness/h6host.py --mutants <run>/mutants.csv --label r11-before` per file: each survivor planted again exactly as mutate.py made it (same id; operator, old, new, column and source line checked), then the batch's host differential test (`src/readable/<batch>/tests/*_diff.py`: the game's ARM code in arm_mini.py against the readable C on made-up states, its normal run: `-n 300` and its own default seed) on the planted copy. Caught = any case mismatches, or the C driver crashes or runs away. The unplanted baseline must give 0 mismatches first (it did, all four). Readable sources outside the batch are compiled once and linked; warnings are not errors (as in mutate.py). Below-normal, 3-4 at once. Results: build/harness/h6host/r11-before/, r11-after/ |
| Sharper cases | added to growth_diff.py, menu_diff.py, support_diff.py as a `SHARP` list (section 4). They draw from their own random stream, so every old case is byte-for-byte the same; each SHARP generator adds n/3 cases |
| Host H6, after | the same tool, `--label r11-after`, on the survivors the host test missed before |
| Sampled H6, after | the same command with `--functions` (the 45 overrides of the four files), `--run-id r11-sharpen-after`: warm, **4 cache hits, 0 misses, 1,037 verdicts reused, 30 s**, 385 / 1,031: unchanged, as expected (no record and no readable code changed) |
| Host tests after the change | growth_diff 7,900 cases, menu_diff 7,100, support_diff 7,700, skill_diff 5,100 (unchanged): **0 mismatches of any kind** |

The four files: support_unit.c 33.3%, skill_battle.c 37.0%, menu_config.c 37.7%, growth_exp.c 42.5% (the lowest
rates among files with at least 20 mutants). stance_gauge.c is lower (2 / 12, 16.7%) but has 12 mutants and its
test (stance_diff.py) has another layout; not done this round. The batches ai_perm, battle2 and ai_score were not
touched (other workflows own them).

## 2. Survivors per file, sampled H6 (N=64), round-10 records [high]

| File | Caught / judged | Survivors | Never reached by a record | Reached, not noticed |
|---|---|---|---|---|
| support/support_unit.c | 137 / 412 (33.3%) | 275 | 228 | 47 |
| skill/skill_battle.c | 30 / 81 (37.0%) | 51 | 49 | 2 |
| menu/menu_config.c | 83 / 220 (37.7%) | 137 | 48 | 89 |
| unit/growth_exp.c | 135 / 318 (42.5%) | 183 | 49 | 134 |
| (all 28 files) | 1,737 / 3,396 (51.1%) | 1,659 | | |

Every file, survivors (judged - caught): support_unit 275, growth_exp 183, formula_unit 149, menu_config 137,
sheet_stats 131, stance_bonus 119, formula_forecast 84, item_value 70, support_records 59, sheet_unit 54,
skill_battle 51, skill_has 50, move_terrain 44, move_occupy 41, vein_tricks 37, vein_units 32, growth_rates 30,
move_cost 29, item_record 25, item_unit 18, triangle_tables 10, stance_gauge 10, ai_value 7, ai_think 5,
formula_stats 5, forces 4, menu_danger 0, flags 0. Per override: build/harness/h56/play/runs/r10-sample2-n64/h6_sample.tsv
(the same numbers as r11-sharpen-before).

"Never reached" is mutate.py's gcov tag (the changed line ran in no sampled record). One caveat found: the 34
"never reached" survivors of `skill_effect_name` sit on the lines of a constant table (the skill-word / name pairs).
gcov never counts a table line as run, so those are not truly unreached: the records called the function (15
records) but only with a few skills.

## 3. Before and after, on these four files [high]

"Host" = the batch's host differential test catches the planted bug. "Either" = caught by a record or by the host
test (kept apart from H6).

| File | H6 (records) | Survivors the host test catches, before | after the sharper cases | Either, before | Either, after | Left: candidates for a person |
|---|---|---|---|---|---|---|
| support_unit.c | 137 / 412 (33.3%) | 235 of 275 (190 of the 228 never reached) | 240 | 372 / 412 (90.3%) | **377 / 412 (91.5%)** | 35 |
| skill_battle.c | 30 / 81 (37.0%) | 50 of 51 | 50 (no change needed) | 80 / 81 (98.8%) | 80 / 81 (98.8%) | 1 |
| menu_config.c | 83 / 220 (37.7%) | 130 of 137 | **137** | 213 / 220 (96.8%) | **220 / 220 (100%)** | 0 |
| growth_exp.c | 135 / 318 (42.5%) | 138 of 183 | 139 | 273 / 318 (85.8%) | **274 / 318 (86.2%)** | 44 |
| **Four files** | **385 / 1,031 (37.3%)**, before and after | 553 of 646 | 566 | 938 / 1,031 (91.0%) | **951 / 1,031 (92.2%)** | 80 |

So most of the "never reached" survivors were already caught by the host tests (they were written with odd inputs
on purpose); the records simply do not hold those inputs. The 13 the host tests missed and that could be caught are
caught now. If the 80 candidates are judged equivalent by a person, these four files would be at 100% "either".

## 4. The sharper cases (what each catches) [high]

| Test | New cases | Catches (mutant ids of the round-10 N=64 run) | Real-play path that would reach it |
|---|---|---|---|
| menu_diff.py `gen_detail_plain` (battle and support picture) | battle_mode 2 or 3, the map's byte 1, all four "always / never picture" masks 0 | config_is_detail_battle-057, -063; config_is_detail_support-043, -049 (the option's answer 1 made 2) | an options save with the battle-animation option on its 3rd or 4th setting (an opt-* route, OPT_ROUTES.md) and a fight |
| menu_diff.py `gen_bgm_sharp` | battle-music item with no list (count 0 or below), config pointer unmapped | config_encounter_bgm_value-002 (`count <= 0` made `< 0`: reads on with no list) | none (the game's list is never empty); host only |
| menu_diff.py `gen_detail_tiny` | unit arguments 0 and 1 only, caches often cold | config_is_detail_battle-001, -004 (the "no unit" test made "not 1") | none (a unit pointer of 1); host only |
| growth_diff.py `gen_dance_sharp` | dancing in modes 2 / 3 with table bytes 9 .. 12 | unit_exp_dance-011 (the dance cap 10 made 11) | a dance or song in a fight with a dance-table value of 11 at that level; the records' table values never were |
| support_diff.py `gen_tiny` (siblings, uncle / aunt both ways) | the shared Person pointer is the value 1 | unit_is_sibling-018, -034; unit_is_uncle_aunt-027, -042, -088 (a "not 0" test made "not 1") | none for the value 1; these lines need child units at all, which no route has (F-025: do not marry for coverage) |

Other "never reached" lines and the fight that would reach them in real play (the host tests already catch these):
unit_family_child / unit_is_sibling / unit_is_uncle_aunt (167 of support_unit's 228): child units (paralogue
children); unit_exp_damage lines 123-126: a fight on difficulty 2 or above (Hard / Lunatic; no record ran it); battle_side_has_skill lines 63-67: a paired unit that has the skill Nohrian Trust in a fight;
config_is_detail_battle / support option paths: an options save with each battle-animation setting.

## 5. Candidates for a person to judge (not marked equivalent) [med: the reasoning is ours]

None of these is in tools/harness/mutants_equivalent.csv; a person decides. Ids from
build/h6snap/r10/build/harness/mutate/game-h6play-r10-sample2-n64-<file>/mutants.csv.

**support_unit.c (35)**
- 29: adding or taking away a constant that is 0 (`FAMILY_PARENT_A`, `FAMILY_PARENT_PERSON`, `RELIANCE_PARTNER`,
  `FAMILY_SIBLING_POINTS` are all 0, so `x - 0` = `x + 0`): unit_family_child-003, -005, -011, -016, -018, -024;
  unit_is_sibling-007, -009, -013, -015, -024, -031; unit_is_uncle_aunt-010, -012, -019, -031, -033, -039, -054,
  -056, -063, -076, -078, -085, -103, -105, -112; unit_support_level-013; unit_support_points-005.
- 4: `if (parent == 0) return 0;` in unit_support_level and unit_support_max_level made `== 1` or `return 1`
  (-005, -006 of each): the child test and the parent lookup read the same family record, so a found child always
  has a parent record; the guard looks unreachable.
- 2: is_unique's `return 1` made `return 2` (unit_spouse_pid-018, unit_support_points-026): is_unique is only
  used as true / false.

**growth_exp.c (44)**
- 27: a boundary test where both sides give the same value at the boundary (clamp's `<` / `>` made `<=` / `>=`,
  the min of two levels, the floor, the caps of 10 / 30 / 1 / 20 / 100, `room < amount`): unit_exp_damage-008,
  -027, -030, -042, -046, -047; unit_exp_dance-010, -020, -031, -035, -036; unit_exp_destroy-014, -017, -024,
  -036, -062, -066, -067; unit_exp_level-014, -015; unit_exp_normalize-000, -011; unit_exp_rod-006, -030, -038,
  -039, -047.
- 7: a constant + 1 that gives the same value at the one input where it differs (`decline < 1 ? 0 : decline` at 0,
  `v < 1` at 0, `v < 2 ? 1 : v` at 1, the boss / flag sums at base or v = 20): unit_exp_damage-028, -031;
  unit_exp_dance-021; unit_exp_rod-031; unit_exp_destroy-018, -025, -037.
- 8: an index clamp past what the level can be (unit_exp_level, the game's own function, clamps the level to
  1 .. 40, so `level - 31` never passes 9, the lower level - 2 never passes 38, `level - 1` never passes 39):
  unit_exp_damage-007, -044; unit_exp_dance-003, -033; unit_exp_destroy-013, -064; unit_exp_rod-012, -049.
- 2: `limit > 20` made `> 21` (unit_exp_normalize-019, unit_level_limit-003): job_level_limit returns only 20, 40
  or 101, never 21.

**skill_battle.c (1)**: skill_effect_name-000: the table is declared one entry longer; the loop still stops at
the old count, so the extra (zero) entry is never read.

**menu_config.c**: none left.

## 6. Limits [high]

- The host test is not the game: it runs the game's ARM code on made-up memory, with stubbed callees (F-018 says
  how). A planted bug it catches is a real difference of the readable code from the original on some input, but
  maybe an input the game never builds (a unit pointer of 1). That is why the "either" number is reported apart
  and never as H6.
- Only survivors were re-judged; a mutant H6 caught was not run through the host test.
- The record H6 here is the sampled one (N=64), a lower bound of the full-record rate (H56.md section 9).
- Sampled H6 runs from the frozen round-10 tree; the four files' code there equals today's.
- The diff scripts' `--plant` lists were not rerun (their cases only grew, so a planted bug caught before is still
  caught).

Files: tools/harness/h6host.py (new); SHARP lists in src/readable/unit/tests/growth_diff.py,
src/readable/menu/tests/menu_diff.py, src/readable/support/tests/support_diff.py (focus_pair takes `kinds` /
`tiny`; its default draws exactly as before). Results: build/harness/h6host/r11-before/, r11-after/ (csv per
mutant, json per file); build/h6snap/r10/build/harness/h56/play/runs/r11-sharpen-before/, r11-sharpen-after/;
logs build/h6snap/r11-sharpen-*.log, build/harness/h6host-r11-*.log.
