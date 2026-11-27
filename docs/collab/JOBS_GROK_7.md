# Jobs for Grok, batch 7 (2026-11-13 evening) — round 8: all three routes

Same rules: no game data, facts from public sources only (cite), never copy GPL code. Write ONLY in
docs/tracks/ and docs/collab/ (the round 8 workflow edits tools/, src/, config/ and the main docs).
ELI5 + ETA at start and end of each job; one dated GROK_INBOX.md line per job. Work in order.

**Owner decision 2026-11-13 evening: "yes, run all three routes in round 8".** This overrides item 3
of docs/collab/EFFICIENCY_AGREED.md ("no Conquest/Revelation yet") and your ROBOT_ROUTES_BC.md
"do not start". From round 8 the robot plays Birthright, Conquest (`cq-*`) and Revelation (`rv-*`)
side by side, sharing the 12 runs. The split starts from the last shared save before the choice
(chapter 5 clear / the chapter 6 choice) if the save allows it, else a new game replaying the shared
chapters. It is recorded as F-022 in DECISIONS by round 8's integrate.

State: commit 278099a (round 7). New: `bt-ch8-options` route (options screen looked at, nothing
changed), H5/H6 on kept game records (H6 47.5% caught, gate 90% not met, writers stay off), writer gate
+ undo log with the first options writer kept OFF (docs/WRITERS.md), docs/OPTIONS_WIRING.md, F-021.

## Job 27 — Review round 7 (docs/collab/reviews/REVIEW_2026-11-15.md)
Read-only review of src/readable/core/writer.c + fe_writer.h, src/readable/menu/menu_config_writer.c,
docs/WRITERS.md, docs/OPTIONS_WIRING.md, tools/harness/h56.py. Look for: a path where an OFF writer
could store, an undo that is not exact, a save that could carry a PC-applied value the doc says it
won't, H6 numbers the tables don't support. Same finding format as before.

## Job 28 — Conquest and Revelation checkpoint lists (docs/tracks/ROUTES_CQ_RV.md)
From public guides, cited, chapters 6 to 12 of Conquest AND of Revelation (refresh ROBOT_ROUTES_BC):
per chapter the win condition, map size/turn limits if stated, units that join, the enemies that
make it hard, the boss, a low-risk plan for an AI that plays by button plans (who to deploy, chokes,
where to wait), any vein, any recruit-by-talk, and what the castle/My Castle offers between chapters
on that route. Mark what the robot can use first. Where Conquest is hard (no free EXP), say which
early chapter is the first real wall and the cheapest safe tactic.

## Job 29 — Birthright 10 to 14 (docs/tracks/ROUTES_BT_10_14.md)
Same format for Birthright chapters 10 to 14 (the robot cleared 9). Include the paralogues that open
there and which ones give a child unit (family readers) or a skill scroll.

## Job 30 — Readers that the new routes will meet
From docs/ROBOT.md (never-met list: unit_attack_for_terrain*, script_unit_can_dragon_vein,
script_unit_has_skill, skill_total, unit_lethality_immune, unit_equipped_skill_count, family_*),
say for each which Conquest/Revelation chapter (6-12) is the cheapest public-fact way to meet it.
Append as a section of ROUTES_CQ_RV.md.
