# Jobs for Grok, batch 6 (2026-11-13 day) — owner: "go for it" (round 7: in-game options)

Same rules: no game data, facts from public sources only (cite), never copy GPL code. Write ONLY in
docs/tracks/ and docs/collab/ (a workflow is editing tools/, src/, config/ and the main docs).
ELI5 + ETA at start and end of each job; one dated GROK_INBOX.md line per job. Work in order.

State: commit dde7d75. Round 6 landed: capture runs now FAIL on any mismatch; the cheat track
(F-019, docs/CHEATS.md); 16 menu/options readers (docs/MENUS.md: danger zone, HP bars, battle
animations and game speed are switches the game ALREADY has, in GameConfigData, stored in every
save). F-020: owner accepted the cheat-track proof for the forge. Round 7 is building the writer
safety net (gate + undo log), an options-screen robot route, H5/H6, and docs/OPTIONS_WIRING.md.

## Job 23 — Review round 5 (docs/collab/reviews/REVIEW_2026-11-14.md)
Read-only review of tools/harness/cheats.py + headless.py's cheat-save fence (save_is_cheat,
check_start_save, pack_save mark) against docs/CHEATS.md and DECISIONS F-019, and of
src/readable/menu/ against docs/MENUS.md. Look for: any path where a cheat record or cheat save
could count as real play; any menu reader that writes; MENUS.md claims the code does not back.

## Job 24 — Options v3 (docs/tracks/OPTIONS_V3.md)
Rewrite your options list in light of MENUS.md: the four built-in switches need no new game code,
only applying a value (a writer, F-017 gate). For each OPTIONS_V2 switch: built-in / new code,
what the player sees, the default, and whether it changes game results (randomness, RNG draws) or
only display. Then from public sources (cite): which Fates quality-of-life features players most ask
for on PC/emulator (e.g. speed-ups, skip animations, danger zone, stat display) and which our
facts make cheap. Keep it short; mark what is unverified.

## Job 25 — Conquest/Revelation robot scouting (docs/tracks/ROBOT_ROUTES_BC.md)
From public guides (cited): the first Conquest and first Revelation chapters after the route split,
anything early that meets readers Birthright never reaches (breakable walls, Revelation's dragon
vein script uses in C012/C018/C020/C025, paralogue X015), and the cheapest order to reach them.
Turn it into a checkpoint list for a later robot round. Names only.
