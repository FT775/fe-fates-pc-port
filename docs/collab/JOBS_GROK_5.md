# Jobs for Grok, batch 5 (2026-11-12 night) — owner: "hyper drive is good to go" (work overnight)

Same rules: no game data, facts from public sources only (cite), never copy GPL code. Write ONLY in
docs/tracks/ and docs/collab/ (an overnight workflow is editing tools/, src/, config/ and the main
docs). ELI5 + ETA at start and end of each job; one dated GROK_INBOX.md line per job. Work in order.

State: commit 6db796c. Robot cleared Birthright chapter 8 (`bt-ch8`), built + entered the Smithy
(`bt-castle-forge`), but forging is blocked: the save has 0 ore (Iron Katana needs 1 Pearl).
Readable batch 4 (23 growth/level-up/EXP readers, docs/GROWTH.md) landed; live shadow compare of all
12 Birthright routes: 10,334 records, 0 mismatches. Report: docs/REPORT_2026-11-13.md.

## Job 19 — Review round 4 (docs/collab/reviews/REVIEW_2026-11-13.md)
Read-only review of src/readable/unit/growth_*.c + growth.h against docs/GROWTH.md, and of the new
marker reads in tools/harness/markers.py (levels, forged/forge_max/forge_pairs, ore/food) and
tools/harness/levelups.py. Look for: rules GROWTH.md states that the code does not implement, cases
growth_diff.py cannot catch (known one: the "ask for the cache first" order in unit_dual_exp_damage),
any writer that is not disabled (F-017). Same finding format as before.

## Job 20 — Refresh your own out-of-date tracks
- docs/tracks/BATCH_GROWTH.md: "no committed route is a level-up exit" is out of date (docs/ROBOT.md 3a:
  level-ups in bt-prologue, bt-ch3, bt-ch4, bt-ch5, bt-ch7, bt-ch8). Unit::LevelUp 0x003D8154 is the
  roll; GrowSequence::LevelUpCalculate only copies the unit with level - 1 and falls into it.
- docs/tracks/OPTIONS_V2.md: "GrowSequence::GainExp applies experience" is refuted — GainExp only starts
  ExpSequence::Create. The exp_rate hook belongs at GrowSequence::Calculate / ExpNormalize or
  ExpSequence::Create (docs/GROWTH.md section 9). Update the fixed-growth / exp-rate options to match.

## Job 21 — Robot next 2 (docs/tracks/ROBOT_NEXT2.md)
From public guides, cited: on Birthright after chapter 8, the fastest way to get ONE ore (Pearl for
katanas, or any ore whose weapon the army holds two of): chapter 9 drops/rewards, Mine building
(cost, when buildable, yield after one battle), Ore Swap, castle gifts. Also: when Azura can first
Sing (for the dance-EXP readers), the first child paralogue on Birthright and what unlocks it (for
the family growth readers), and any early event that makes a unit stand on a fort/throne/special
terrain in battle (for the formula terrain forms). Turn it into a checkpoint list.

## Job 22 — Skills batch plan (docs/tracks/BATCH_SKILLS.md)
For readable batch 5 (skills, read-only readers). From config/functions.csv (names only) and
docs/tracks/REWRITE_ORDER.md row 5: which skill READERS to do first — "does unit have skill X",
activation-chance getters (Skl%, Lck%-style triggers), passive stat skills. Avoid the picture/banner
sequence and the 186-hit pile. Order, expected callers, which robot routes likely activate a skill
(public facts on early Birthright units' skills: Ryoma, Hinoka, Hana, Rinkah, Kaze, Corrin, Sakura).
Mark everything unverified.
