# Jobs for Grok, batch 3 (2026-11-11) — owner: "you have a few hours to utilize this extra grok usage"

~37% left, resets 2026-11-11 15:16. Work in order until it runs low. Same rules: no game data, facts
from public sources only (cite), never copy GPL code. Write ONLY in docs/tracks/ and docs/collab/ —
a workflow is editing tools/castle, src/readable/battle, config/readable, tools/mods, tools/check_all.py
and docs/ right now. ELI5 + ETA at start and end of each job; one dated GROK_INBOX.md line per job.

## Job 9 — Review round 2 (docs/collab/reviews/REVIEW_2026-11-11b.md)
Read-only review of the overnight code: tools/maps/maplib.py + maps.py, tools/assets/bchwrite.py +
portrait.py, tools/mods/mapface.py, and the new journaled install/uninstall in tools/mods/mods.py
(commit 4bbfe51). Same format as your first review: file:line, what breaks, how to reproduce, severity.
Focus: anything that can corrupt a game file, strand a file, or accept an edit the game will reject.

## Job 10 — Map and face check sheets (docs/tracks/guides/check-map.md, check-face.md)
The commands now exist: `mods.py example-map` / `example-face` (docs/MODDING.md sections 6a/6b).
Turn the two "not yet" sheets into real 5-minute sheets, like your other three.

## Job 11 — Screen extras plan for Fates (docs/tracks/EXTRAS_FATES.md) — roadmap step 7
What Awakening's extras did (docs in the Awakening repo: docs/analysis/EXTRAS_USA.md, read-only),
what public sources say exists for Fates (widescreen/16:9 hacks, 60 fps, faster battle animations,
Citra/Action Replay codes and who published them), and a design for our Fates extras: which ones,
how each would be found and checked, risks. Facts only, cite sources; no code bytes.

## Job 12 — Option hook map (docs/tracks/OPTION_HOOKS.md)
For each of the 19 options in OPTIONS_V1.md: candidate game functions by NAME from config/functions.csv
(tracked; names and addresses are fine to read), why each candidate, reader vs writer, and which
roadmap step unblocks it. Mark everything "unverified: names only". This becomes my worklist.

## Job 13 — Rewrite order after stances (docs/tracks/REWRITE_ORDER.md)
Using config/functions.csv names, a batch plan for the readable rewrite after stances: weapon triangle,
dragon veins, damage/hit/crit formulas, growth/level-up, skills, AI targeting, menus that options need.
Each batch: systems, rough function counts by class name, what it unlocks (options, mods), risk.

## Job 14 — Community scan: better routes, tools and projects (docs/tracks/COMMUNITY_SCAN.md) — owner request
The owner asked that you research better routes, strategies and community FE projects/repos that could
help us finish faster or better, with credit when we use them. Survey: Fates/FE14 and 3DS-FE tools and
repos (editors, randomizers, decomp/recomp efforts, format libraries, Citra/Azahar/Lime3DS cheat and
texture-pack work, Fates modding communities, Awakening/Echoes projects whose formats overlap, 3DS
recomp/HLE projects other than Zakuro), plus any strategy we have missed (e.g. a better way to verify
readable code, existing struct/class layouts for Unit/Battle, existing script (.cmb) tools, a shared
symbol database). For each: link, author, licence, last activity, what it offers us, how we may use it
(code reuse only if licence-compatible and kept as a separate credited dependency; GPL = facts only),
estimated time saved, and risks. End with a ranked "adopt / read for facts / skip" list and any change
you recommend to our plan, with evidence. Keep CREDITS.md in mind: anything we adopt gets an entry
(Claude adds it when the thing is actually used).
