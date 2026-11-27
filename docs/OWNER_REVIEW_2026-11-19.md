# The owner's review of round 41, 2026-11-19 (F-026, F-037)

**The owner's words**, in chat on 2026-11-19 at about 18:00, answering round 41's review list
(docs/REPORT_2026-12-15.md):

> "Yes, Grok's picks"

That means exactly the section "What to answer now" of docs/collab/ROADMAP_NOW_GROK.md: ok to what Grok called safe,
and hold to what Grok said to hold. Nothing beyond that page is approved. Under F-037 an OK below counts as done for
that line; a HOLD stays open.

## The looks (docs/LOOK_ROBOT.md)

| # | Review item | Verdict | Reason (from Grok's page) |
|---|---|---|---|
| 3 | Name: "Jacques" in the army list, on the status screen and in the talk (N1-N3) | **OK** | Seen in all three places, and the taken-out check matched. |
| 5 | Stats line 2: Mov +2 (S2) | **OK** | Seen (5 -> 7), and the taken-out check matched. |
| 7 | Stats line 4: the Supportive icon shows Nobility's crown (S4) | **OK** | Seen, and the taken-out check matched. |
| 9 | Face in the talk (F1) | **OK** | Seen, and the taken-out check matched. |
| 10 | Face on the status screen (F3) | **OK** | Seen, and the taken-out check matched. |
| 12 | All looks off = the original game (O1) | **OK** | "Taken out, the game is the original": the memory hash equals two unmodded runs. |
| 1 | Battle extras (E1-E4) | **OK, as the robot measured them** | Smoother, faster, a wider view, same save. **Not** ok'd: "your window is 16:9". The robot cannot see Zakuro's window shape. |
| 2 | Extras off = original (E5) | **OK** | Part of the robot's battle-switch result: the same memory with every switch off as with no file. |
| 4 | Stats line 1: HP +5 (S1) | **OK, as "the cap held"** | It did not show the full +5 (39 -> 40, the class cap is 40). Only "the cap held" is ok'd. |
| 6 | Stats line 3: Bronze Sword Mt 4 -> 14 (S3) | **HOLD** | Not run. Never seen on a screen. |
| 8 | Stats line 5: dining-hall dishes Luck +2 (S5) | **HOLD** | Not run. |
| 11 | Face in the small talk window (F2) | **HOLD** | Not run. |

The three HOLD lines stay open. Do not play a chapter just to find a Bronze Sword or a meal; a later save that
already has one can close them (Grok's page, "From here" item 4).

## Equivalence classes 1-3 (docs/EQUIV_PROPOSAL.md)

| # | Class | Verdict | Reason (from Grok's page) |
|---|---|---|---|
| 14 | Class 2, a give-up returning a number nobody uses: all 18 | **OK** | A give-up returns a number nobody uses, and every one was clean. |
| 13 | Class 1, gives up only: the 7 clean | **OK** | Clean. |
| 13 | Class 1: the 8 "with a note" | **HOLD (with a note)** | They can answer from warm data, and no test shows that. |
| 15 | Class 3, a value that cannot occur: the 2 clean | **OK** | Clean. |
| 15 | Class 3: the 5 held | **HOLD** | They read through an empty pointer. That is a person's call, and the call is no for now. |

The 27 approved cases (18 + 7 + 2), as listed in docs/EQUIV_PROPOSAL.md:

- Class 2 (18): unit_attack-007, unit_attack-009, unit_attack-031, unit_attack-032, unit_attack-033,
  unit_attack_speed-001, unit_avoid-002, unit_crit-015, unit_crit_avoid-002, unit_defense_speed-001, unit_hit-007,
  unit_hit-011, unit_hit-046, unit_hit-047, unit_hit-048, unit_can_dragon_vein-009, vein_command_attribute-000,
  unit_weapon_exp-000.
- Class 1, clean (7): unit_attack-022, unit_attack_of_slot-011, unit_avoid_of_slot-002, unit_crit_avoid-010,
  unit_hit-037, unit_hit_of_slot-010, unit_move-002.
- Class 3, clean (2): stance_attack_bonus_edit-004, unit_attack_stance_bonus-032.

Held, not marked: class 1 unit_attack-018, unit_attack-020, unit_attack_of_slot-006, unit_attack_of_slot-007,
unit_attack_of_slot-009, unit_crit-031, unit_crit_of_slot-002, unit_hit_of_slot-002; class 3
unit_attack_stance_bonus-020, unit_guard_stance_bonus-034, unit_support_level-005, unit_support_max_level-005,
script_trick_test-003.

**How they were marked (round 42).** The 27 rows were added to tools/harness/mutants_equivalent.csv in its format
(function, operator, old, new, col, source_line, why). Each "why" reads "owner ok 2026-11-19 (F-037), class N:
<reason>" and ends in "[id <case> line <n>]". The tag is needed because the key columns alone cannot tell apart two
`return 0;` lines of one function. Without it, five rows would also have matched other `return 0;` lines that give
a real answer (for example unit_attack-002 after `if (item == 0)`). tools/harness/mutate.py and
tools/harness/h6three.py now honour the tag: a pinned row names that one planted bug only, and if the code moves it
matches nothing and is reported stale. It is never a wrong mark.

**Counts.**
- mutants_equivalent.csv: 10 entries before, 37 after.
- h6three: the judgement pile goes from 237 of the 237 (and 70 of the 70 new) to 211 and 69. 26 of the 237 were
  cleared, plus unit_weapon_exp-000 from the 70.
- Number 1 is unchanged: 2,214 / 3,696 (59.9%) on reached lines, and 2,214 / 4,140 (53.5%) as the one-percent figure.
- Re-applying the list to the 332 kept mutants.csv files marks exactly these 27 ids (370 rows, counting repeats
  across runs), and none is flagged WRONG.
- Per F-026, cleared cases leave the judgement pile and are not added to the headline. In a future H6 run they are
  left out of "judged", as F-026 says ("after never-reached lines and judged equivalents are out").

No writer is turned on by this. It does not move the headline.

## The options-test rule changes (OK A, T1/T2/T3)

| Item | Verdict | Reason (from Grok's page) |
|---|---|---|
| The corrected T1/T2/T3 rules of round 40 | **HOLD** | No, until the two missing T1 routes (bt-ch9, bt-ch9-ore) are run and the clock note is in a committed report. |

OK A is still not green. No writer is turned on.

## Later the same day: the Bronze Sword line (round 44)
Owner, after first answering "Not ok" and seeing the picture: "it works, just don't add the mod". Stats line 3
(Bronze Sword Mt 4 -> 14) is **OK** as a check. The test mod (LookStep4: Bronze Sword Mt 14, HP +5, crown icon) stays a
robot-only test: it is never installed in the owner's game, never enabled in the owner's mods/ folder and never shipped.
With this, all five Moddable checks (name, people/class, skills, items, portrait) have the owner's ok.
