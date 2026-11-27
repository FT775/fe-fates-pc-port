# Jobs for Grok, batch 2 (2026-11-10 night) — owner: "make use of Grok's last usage before the reset"

Your weekly quota resets 2026-11-11 15:16; ~46% is left. Work through these in order until it runs low.
Same rules as batch 1: no game data (no extracted files, table values, game text, images); facts from
public sources only, cite them; never copy GPL code. Write ONLY in docs/tracks/ and docs/collab/
(a workflow is editing tools/assets, tools/maps, tools/mods, tools/check_all.py right now).
ELI5 + ETA at the start and end of each job in the chat; one dated GROK_INBOX.md line per finished job.

## Job 4 — Review our committed code (docs/collab/reviews/REVIEW_2026-11-11.md)
Independent second read of our own tools (no game files needed; read the code and docs):
tools/tables/ (tablelib.py, build.py, appends logic, check.py), tools/fates/routes.py, tools/mods/mods.py
(install/uninstall atomicity, manifest, backups), tools/play/play.py (save backup, ROM check).
Look for: data-loss risks (install/uninstall/backups), wrong assumptions, unchecked edge cases, crash
paths a non-technical owner could hit, unclear errors. Each finding: file:line, what breaks, how to
reproduce, severity. Do not edit tools/; I verify and fix.

## Job 5 — Test robot plan for Fates (docs/tracks/ROBOT_PLAN.md)
Design only. Using the agreed scope (one campaign: Birthright, Normal, Casual): an ordered list of
what the headless robot must reach (title, new game, prologue chapters, route choice, early Birthright
chapters, My Castle entry points that matter: shop, armory, forge, convoy; one support; one dragon
vein; one stance attack/guard), each with an exit check that a screen-marker or memory read could
confirm, and the "stop when a new route adds nothing" rule. Mark which need the GPU (all headless runs)
and which can be done by replaying recorded inputs. Use docs/HARNESS.md for the robot's real abilities.

## Job 6 — Full options list v1 (docs/tracks/OPTIONS_V1.md)
FE8-port parity for Fates (see docs/tracks/STANCE_AND_REVIVE.md and docs/collab/GROK_INBOX.md for the
shape). Every option: name, values, default (off), display vs run, which game system/hook it needs,
which roadmap step unblocks it, and risk. Include Casual on/off for existing saves, growth display,
danger zone, battle animation/speed helpers, fixed growths, stance rates, revive switch, weapon
durability where relevant, EXP/gold multipliers per route, and whatever the FE8 port's Helpers/Game
fixes pages have that makes sense in Fates. Mark what is cut and why.

## Job 7 — Owner check sheets (docs/tracks/guides/)
Plain-language 5-minute check sheets for a non-technical owner, one per pipeline: text (renamed
name), stats (Ryoma +10 Str), new item (ExampleItem), map (ExampleMap: a moved enemy), face
(ExampleFace: tinted portrait). Each: exact clicks/commands, what they should see, how to undo, what
to report back. Read docs/MODDING.md for the real commands (it is being extended tonight; leave
placeholders where a command does not exist yet).

## Job 8 — Castle data format, public facts (docs/tracks/formats/CASTLE_SHEETS.md)
Fates castle/MyRoom/Fortune/JobIntro/AcceShop files use a self-describing MOD_/DAT_/SHEET_ format.
From public sources only: what is known about it (headers, sheet tables, field types, which files),
tools that read it and their licences. Facts only; I will build the codec against the real files.
