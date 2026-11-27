# Jobs for Grok, batch 4 (2026-11-12) — owner: "make the most of what you got"

Same rules: no game data, facts from public sources only (cite), never copy GPL code. Write ONLY in
docs/tracks/ and docs/collab/ (workflows are editing tools/, src/, config/ and the main docs).
ELI5 + ETA at start and end of each job; one dated GROK_INBOX.md line per job. Work in order.

## Job 15 — Review round 3 (docs/collab/reviews/REVIEW_2026-11-12.md)
Read-only review of tools/castle/ (sheetlib.py, castle.py), tools/mods/castlemod.py, and the readable
batches src/readable/battle/ (stances, triangle, formulas) and src/readable/map/ (veins) against their
docs (docs/CASTLE.md, STANCES.md, TRIANGLE.md, FORMULAS.md, VEINS.md). Look for: rules the docs state
that the code does not implement, edge cases the host diffs may not cover, any writer that is not
actually disabled, any castle edit the game would reject. Same finding format as before.

## Job 16 — Forge/smithy unlock and support pacing (docs/tracks/ROBOT_NEXT.md)
The robot reached the shop, chapter 7 and a C support, but no smithy appears in the castle build list
through Birthright chapter 7. From public guides: when does the Smithy (forge) become buildable on
Birthright, what DVP it costs, what else unlocks around then; fastest support pairs early in Birthright.
Turn it into the robot's next checkpoint list (chapter numbers, castle steps), cited.

## Job 17 — Options v2 (docs/tracks/OPTIONS_V2.md)
Update OPTIONS_V1 with what the code now gives us: confirmed hit/avoid/crit/damage formulas
(docs/FORMULAS.md), weapon triangle rules (docs/TRIANGLE.md: advantaged unit's rank; disadvantaged unit
loses its own rank bonus), veins (docs/VEINS.md: no per-turn flag; who-can-use is one flag), stance
gauge (docs/STANCES.md). For each option: exact functions now named, reader vs writer, what the robot
must replay before it can be enabled. Propose 3-5 new options these facts make cheap (display-only first).

## Job 18 — Growth/EXP batch plan detail (docs/tracks/BATCH_GROWTH.md)
For rewrite batch 4: list GrowSequence / LevelUp / GetGrow / GetExp* functions by name from
config/functions.csv, the order to rewrite them, which robot routes already exercise level-ups (see
docs/ROBOT.md), and what a fixed-growth option would need. Names only, mark everything unverified.
