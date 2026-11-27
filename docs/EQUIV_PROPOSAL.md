# Equivalence classes 1-3: a proposal for the owner (F-026, F-037)

**In plain words.** H6 plants small bugs in the readable code. 237 planted bugs survive every test and were put into
rule classes (docs/harness/H6_THREE.md). Grok's rule note (docs/collab/EQUIV_RULES_GROK.md) says three classes are
safe enough for a script to mark once you approve them. A script checked every case in those three classes against
the class's written test. **Nothing is marked.** tools/harness/mutants_equivalent.csv is untouched and the headline
H6 percent does not change. You say ok or no per class; only then may a separate script apply that one class.

Date 2026-11-18 (round 41, chapter "equiv-proposal"). Host only: no game run, no build, no source changed.

## Short summary (pass / fail)

| Class | Checked | Pass, clean | Pass, with a note | Held for a person | Fail |
|---|---|---|---|---|---|
| 1 Gives up, and nothing else | 15 (all of the 237) | 7 | 8 | 0 | 0 |
| 2 A give-up returning a number nobody uses | 18 (17 of the 237 + 1 of the 70) | 18 | 0 | 0 | 0 |
| 3 Compared with a value that cannot occur | 7 (all of the 237) | 2 | 0 | 5 | 0 |
| **All three** | **40** | **27** | **8** | **5** | **0** |

What you can say ok to (pick one per class):
- **Class 1:** ok to all 15, or ok to the 7 clean only. The 8 "with a note" give no wrong answer by my reading of the code (a reading, not a test result), but on a cold
  cache they can return an answer (the no-weapon or no-crit answer, read from warm data only) where the original
  readable code gave up.
- **Class 2:** ok to all 18. Every one is `return 0;` made `return 1;` straight after `if (fe_gave_up(ctx))`.
- **Class 3:** ok to the 2 clean only (my advice). The other 5 pass the written test (the planted value can never
  occur) but the written test is not enough there: when the *original* value occurs (a null pointer), the planted copy
  reads through that null pointer instead of returning. That can be harmless, but it is a person's call.

If all of it were approved the judgement pile would lose 27 to 40 cases. That count is kept apart; it is never
added into the H6 headline (EQUIV_RULES: "It must not add the cleared count into the headline percent").

The rule note's estimate was "about 39" (15 + 17 + 7). The checked count is 40 because one of the 70 unsorted
(unit_weapon_exp-000) sorts into class 2.

## How it was checked [high for the facts the script reads; the reading notes are mine]

    python tools/harness/equiv_propose.py        # writes build/equiv/equiv_proposal.json, prints the summary

Input: build/h6three/three-r37.json (h6three.py `--json`, round 37; 237 classed + 70 new_not_sorted; checked: 237
and 70). For every case the script:

1. **Finds the planted bug in today's source**: it re-makes the mutants with tools/harness/mutate.py and needs the
   same id, operator, old text, new text, column and source line (the way h6host.py matches). All 40 matched
   (two support_unit lines moved down by one; same change).
2. **Reads the newest host verdict** from build/harness/h6host/<label>/<file>.csv (r14-three, r13-after for the
   stance ones, r17-host for triangle_tables). All 40: `survived` (no host case shows a wrong answer).
3. **Applies the class's written test**:
   - Class 1: the change sits in a give-up decision (an `if (...)` whose body is `return fe_use_original(ctx)`, or a
     `*_ready` helper such an `if` asks); the host give-up count moved (`host_extra_giveups` not 0); the case is not
     one the notes say can change an answer; and my reading of the code says "more" or "later" (see notes).
   - Class 2: the planted line is `return <constant>;`; the line before it is exactly `if (fe_gave_up(ctx))`; the
     give-up flag is never cleared inside readable code (the only clears are FE_ENTRY's restore,
     include/readable/fe_guest.h:304, and the capture replay entry, src/readable/core/capture.c:1064), so the value
     is thrown away and the original runs; no guest store (WRITE_FIELD / guest_set_*) in the file or in any file that
     calls the function (all 0).
   - Class 3: the compared variable's declared type makes the planted value impossible (`uint32_t` against
     0x100000000, or a guest pointer `gaddr` against 1); not named as can-change. Extra (not in the written test):
     what happens when the original value occurs.

Reading notes, class 1: "more" = gives up wherever the original readable code gave up, and in more cases. "later" =
on a cold cache it passes the first guard and gives up in the callee's own guard (unit_stat_value, unit_avoid,
unit_hit, unit_crit, unit_attack all check their caches first) before any cached value is read. "answer" = on a
cold cache it can also answer on a path that reads no cached value (no weapon: slot -1 with nothing equipped or a
negative slot; or a weapon that can never crit); that answer is what the readable code returns warm on the same path.

## Every case

#### Class 1 (give_up_only): 15 checked

| Case | From | File:line now | Change | Verdict | Why it fits (or not) |
|---|---|---|---|---|---|
| unit_attack-018 | 237 | formula_unit.c:125 | `STAT_STR` -> `(STAT_STR + 1)` | fits, with a note | later + answer: attack_ready asks STAT_MAG twice instead of STR+MAG: with a cold STR cache it goes on; a physical weapon gives up in stat_of(STR) (unit_stat_value's own guard); a magic weapon answers from the warm MAG cache; edited in attack_ready, line 125 |
| unit_attack-020 | 237 | formula_unit.c:125 | `STAT_MAG` -> `(STAT_MAG + 1)` | fits, with a note | later + answer: attack_ready asks STAT_SKL instead of STAT_MAG: more give-ups when SKL is cold; with a cold MAG cache a magic weapon gives up in stat_of(MAG); a physical weapon answers from the warm STR cache; edited in attack_ready, line 125 |
| unit_attack-022 | 237 | formula_unit.c:126 | `\|\|` -> `&&` | fits | more: `!rank_bonus \|\| exp_ready` made `&&`: with rank_bonus it always gives up, without it gives up also when the exp caches are cold; never goes on where the original gave up; edited in attack_ready, line 126 |
| unit_attack_of_slot-006 | 237 | formula_unit.c:276 | `if (!attack_ready(ctx, rank_bonus))` -> `!(!attack_ready(ctx, rank_bonus))` | fits, with a note | later + answer: guard turned round: gives up when warm (more); when cold it goes on: slot -1 with nothing equipped answers 0 before unit_attack's own attack_ready guard; otherwise that guard gives up; edited in unit_attack_of_slot, line 276 |
| unit_attack_of_slot-007 | 237 | formula_unit.c:125 | `STAT_STR` -> `(STAT_STR + 1)` | fits, with a note | later + answer: same edit as unit_attack-018 (shared helper attack_ready); edited in attack_ready, line 125 |
| unit_attack_of_slot-009 | 237 | formula_unit.c:125 | `STAT_MAG` -> `(STAT_MAG + 1)` | fits, with a note | later + answer: same edit as unit_attack-020 (shared helper attack_ready); edited in attack_ready, line 125 |
| unit_attack_of_slot-011 | 237 | formula_unit.c:126 | `\|\|` -> `&&` | fits | more: same edit as unit_attack-022 (shared helper attack_ready); edited in attack_ready, line 126 |
| unit_avoid_of_slot-002 | 237 | formula_unit.c:198 | `if (!avoid_ready(ctx))` -> `!(!avoid_ready(ctx))` | fits | later: guard turned round: gives up when warm; when cold unit_avoid's first line is the same avoid_ready guard, so it gives up there (slot_or_none reads no cache); edited in unit_avoid_of_slot, line 198 |
| unit_crit-031 | 237 | formula_unit.c:211 | `if (!crit_ready(ctx))` -> `!(!crit_ready(ctx))` | fits, with a note | later + answer: inner crit_ready guard turned round: when warm it gives up; when cold (NoCritGuard already checked warm, so the SKL cache is cold) a weapon with the no-crit flag answers 0, otherwise stat_of(SKL) gives up; edited in unit_crit, line 211 |
| unit_crit_avoid-010 | 237 | formula_unit.c:241 | `if (!unit_stat_caches_ready(ctx, STAT_LCK))` -> `!(!unit_stat_caches_ready(ctx, STAT_LCK))` | fits | later: guard turned round: when the LCK cache is cold the next line stat_of(LCK) gives up at once (unit_stat_value's own guard); when warm it gives up; edited in unit_crit_avoid, line 241 |
| unit_crit_of_slot-002 | 237 | formula_unit.c:232 | `if (!crit_ready(ctx))` -> `!(!crit_ready(ctx))` | fits, with a note | later + answer: guard turned round: when cold and there is no weapon (slot -1 with nothing equipped, or a negative slot: item 0), unit_crit answers 0 before its crit_ready guard; otherwise unit_crit's guards give up; edited in unit_crit_of_slot, line 232 |
| unit_hit-037 | 237 | formula_unit.c:111 | `\|\|` -> `&&` | fits | more: hit_ready: `!rank_bonus \|\| exp_ready` made `&&`; as unit_attack-022; edited in hit_ready, line 111 |
| unit_hit_of_slot-002 | 237 | formula_unit.c:164 | `if (!hit_ready(ctx, rank_bonus))` -> `!(!hit_ready(ctx, rank_bonus))` | fits, with a note | later + answer: guard turned round: when cold and there is no weapon (slot -1 with nothing equipped, or a negative slot: item 0), unit_hit answers 0 before its hit_ready guard; otherwise unit_hit's guards give up; edited in unit_hit_of_slot, line 164 |
| unit_hit_of_slot-010 | 237 | formula_unit.c:111 | `\|\|` -> `&&` | fits | more: same edit as unit_hit-037 (shared helper hit_ready); edited in hit_ready, line 111 |
| unit_move-002 | 237 | sheet_stats.c:262 | `&&` -> `\|\|` | fits | more: `with_extras && (cold ...)` made `with_extras \|\| (cold ...)`: with with_extras set it always gives up; without it, it gives up whenever one of those six caches is cold (the original went on); the original gave up only when both held, and then this does too; edited in unit_move, line 262 |

#### Class 2 (return_after_give_up): 18 checked

| Case | From | File:line now | Change | Verdict | Why it fits (or not) |
|---|---|---|---|---|---|
| unit_attack-007 | 237 | formula_unit.c:263 | `0` -> `1` | fits | line 263 `return 0;` right after `if (fe_gave_up(ctx))` in unit_attack; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |
| unit_attack-009 | 237 | formula_unit.c:267 | `0` -> `1` | fits | line 267 `return 0;` right after `if (fe_gave_up(ctx))` in unit_attack; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |
| unit_attack-031 | 237 | formula_unit.c:83 | `0` -> `1` | fits | line 83 `return 0;` right after `if (fe_gave_up(ctx))` in weapon_rank_term; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |
| unit_attack-032 | 237 | formula_unit.c:87 | `0` -> `1` | fits | line 87 `return 0;` right after `if (fe_gave_up(ctx))` in weapon_rank_term; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |
| unit_attack-033 | 237 | formula_unit.c:90 | `0` -> `1` | fits | line 90 `return 0;` right after `if (fe_gave_up(ctx))` in weapon_rank_term; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |
| unit_attack_speed-001 | 237 | formula_unit.c:302 | `0` -> `1` | fits | line 302 `return 0;` right after `if (fe_gave_up(ctx))` in unit_attack_speed; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |
| unit_avoid-002 | 237 | formula_unit.c:177 | `0` -> `1` | fits | line 177 `return 0;` right after `if (fe_gave_up(ctx))` in unit_avoid; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |
| unit_crit-015 | 237 | formula_unit.c:223 | `0` -> `1` | fits | line 223 `return 0;` right after `if (fe_gave_up(ctx))` in unit_crit; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |
| unit_crit_avoid-002 | 237 | formula_unit.c:245 | `0` -> `1` | fits | line 245 `return 0;` right after `if (fe_gave_up(ctx))` in unit_crit_avoid; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |
| unit_defense_speed-001 | 237 | formula_unit.c:313 | `0` -> `1` | fits | line 313 `return 0;` right after `if (fe_gave_up(ctx))` in unit_defense_speed; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |
| unit_hit-007 | 237 | formula_unit.c:145 | `0` -> `1` | fits | line 145 `return 0;` right after `if (fe_gave_up(ctx))` in unit_hit; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |
| unit_hit-011 | 237 | formula_unit.c:150 | `0` -> `1` | fits | line 150 `return 0;` right after `if (fe_gave_up(ctx))` in unit_hit; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |
| unit_hit-046 | 237 | formula_unit.c:83 | `0` -> `1` | fits | line 83 `return 0;` right after `if (fe_gave_up(ctx))` in weapon_rank_term; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |
| unit_hit-047 | 237 | formula_unit.c:87 | `0` -> `1` | fits | line 87 `return 0;` right after `if (fe_gave_up(ctx))` in weapon_rank_term; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |
| unit_hit-048 | 237 | formula_unit.c:90 | `0` -> `1` | fits | line 90 `return 0;` right after `if (fe_gave_up(ctx))` in weapon_rank_term; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |
| unit_can_dragon_vein-009 | 237 | vein_units.c:83 | `0` -> `1` | fits | line 83 `return 0;` right after `if (fe_gave_up(ctx))` in unit_can_dragon_vein; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |
| vein_command_attribute-000 | 237 | vein_units.c:112 | `0` -> `1` | fits | line 112 `return 0;` right after `if (fe_gave_up(ctx))` in vein_command_attribute; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |
| unit_weapon_exp-000 | 70 | triangle_tables.c:99 | `0` -> `1` | fits | line 99 `return 0;` right after `if (fe_gave_up(ctx))` in unit_weapon_exp; the flag stays set until FE_ENTRY replays the original, so the value is thrown away; stores in this file and its callers' files: 0 |

#### Class 3 (impossible_value): 7 checked

| Case | From | File:line now | Change | Verdict | Why it fits (or not) |
|---|---|---|---|---|---|
| stance_attack_bonus_edit-004 | 237 | stance_bonus.c:77 | `0xFFFFFFFFu` -> `0x100000000u` | fits | `type` is uint32_t; 0x100000000u is more than 32 bits; type 0xFFFFFFFF no longer returns at line 77, but line 79 returned 0 for a group of -1, so both groups are not -1, and line 81 then returns 0 because type (-1) equals neither group: the same 0, no extra read; line 77 |
| unit_attack_stance_bonus-020 | 237 | stance_bonus.c:144 | `0` -> `1` | fits the written test; held for a person | `family` is a guest pointer (gaddr); a pointer of 1 is never a real object; family_ready: `family != 0` made `!= 1` (always true): when the unit's family pointer is 0 the planted copy reads link_00 at guest address 0; the answer is the same only if that read gives 0, and it is an extra read of unmapped memory; line 144 |
| unit_attack_stance_bonus-032 | 237 | stance_bonus.c:77 | `0xFFFFFFFFu` -> `0x100000000u` | fits | `type` is uint32_t; 0x100000000u is more than 32 bits; same line as stance_attack_bonus_edit-004 (shared helper); line 77 |
| unit_guard_stance_bonus-034 | 237 | stance_bonus.c:144 | `0` -> `1` | fits the written test; held for a person | `family` is a guest pointer (gaddr); a pointer of 1 is never a real object; same line as unit_attack_stance_bonus-020 (shared helper); line 144 |
| unit_support_level-005 | 237 | support_unit.c:82 | `0` -> `1` | fits the written test; held for a person | `parent` is a guest pointer (gaddr); a pointer of 1 is never a real object; `parent == 0` made `== 1` (never true): when SUP_FamilyGetParent returns 0 the planted copy reads the points at parent + FAMILY_PARENT_POINTS (near address 0) and calls family_parent_level on a null parent; line 82 |
| unit_support_max_level-005 | 237 | support_unit.c:107 | `0` -> `1` | fits the written test; held for a person | `parent` is a guest pointer (gaddr); a pointer of 1 is never a real object; `parent == 0` made `== 1`: when the parent is 0 the planted copy makes the guest call SUP_ParentGetMaxLevel(0) instead of returning 0; line 107 |
| script_trick_test-003 | 237 | vein_tricks.c:163 | `0` -> `1` | fits the written test; held for a person | `d` is a guest pointer (gaddr); a pointer of 1 is never a real object; `d == 0` made `d == 1`: when no gimmick is found (d == 0, the common case) the planted copy reads TrickData.state at guest address 0+offset; the answer is the same only if that read gives 0 (H6_SURVIVORS C.7: vein_diff does not count such reads); line 163 |

#### The 70, by class

| Class | Count | Case ids |
|---|---|---|
| zero_offset | 25 | ai_is_escape_position-006, ai_is_escape_position-017, ai_is_escape_position-030, ai_is_escape_position-043, ai_item_index_doping-017, ai_item_index_heal-029, ai_attack_permission_self-000, ai_has_active_command-002, ai_has_active_command-009, ai_has_crossfire_command-003, ai_has_crossfire_command-010, battle_strike_run-009, battle_strike_run-022, item_record-001, item_record-011, item_record-020, reliance_count-006, reliance_count-020, reliance_entry-005, reliance_entry-024, reliance_find-005, reliance_find-015, reliance_find-021, reliance_find-038, reliance_person-000 |
| boundary_compare | 19 | ai_is_dual_support_unit-022, ai_is_dual_support_unit-023, ai_is_dual_support_unit-026, ai_is_dual_support_unit-029, ai_sigh_of_death_score-018, ai_sigh_of_death_score-019, ai_sigh_of_death_score-020, ai_sigh_of_death_score-026, ai_sigh_of_death_score-027, ai_sigh_of_death_score-030, ai_sigh_of_death_score-033, route_cost-014, route_cost-015, unit_shown_level-000, reliance_find-020, reliance_max_level-001, unit_weapon_exp-002, unit_weapon_exp_limit-016, weapon_rank_of_exp-001 |
| early_return_value | 5 | unit_has_rally_stat_skill-017, item_record-030, reliance_count-014, reliance_entry-016, reliance_find-030 |
| swapped_arguments | 5 | reliance_is_romance-005, reliance_level-008 (can change an answer), reliance_level-009, reliance_max_level-010, reliance_max_level-011 |
| other | 4 | battle_seal_effect-035 (by hand), route_cost-031 (by hand), route_cross-017 (by hand), route_goal_x-008 (by hand) |
| no_arg_call_words | 4 | skill_pool_test-000, skill_pool_test-001, skill_pool_test-002, skill_pool_test-003 |
| call_argument_constant | 3 | ai_is_dual_support_unit-003, ai_sigh_of_death_score-000, item_record-000 |
| start_value | 2 | ai_item_index_doping-043, item_record-031 (by hand) |
| named_constant | 2 | unit_luck-000, weapon_rank_of_exp-002 |
| return_after_give_up (class 1-3) | 1 | unit_weapon_exp-000 |

Sorting the 70 (sorting only, nothing marked): the class comes from h6three.py's rule list (`classify`, the same
rules that sorted the 237); five it called "other" were read by hand: item_record-031 (`*found = 1` made `2`) is a
start_value; battle_seal_effect-035 (the `0` in `sizeof first[0]`, which looks the same by C rules) and the three
`step & 2u` mask lines (route_cost-031, route_cross-017, route_goal_x-008) stay "other" for a person. Only one of
the 70 is in classes 1-3 (unit_weapon_exp-000, class 2, checked above). reliance_level-008 (swaps a support and a
rank) is in swapped_arguments and the notes say it can change an answer: never for a script.

## Limits

- The class 1 and class 3 reading notes are mine, written into tools/harness/equiv_propose.py (C1_READ, C3_READ)
  so a reviewer can check them line by line. A person may disagree with a note; the script only reports.
- The host test is not the game. "survived" means no host case showed a different answer.
- Class 2's "nobody uses it" rests on the give-up flag being sticky and on no guest store after the give-up; both are
  read from today's source. A future writer that stores after a give-up would break it (none of these files stores).
- Nothing here changes a gate, a writer, mutants_equivalent.csv or the H6 headline.

Files: tools/harness/equiv_propose.py (the check), build/equiv/equiv_proposal.json (machine file: every test's
true/false per case, the host label and verdict, the line today).
