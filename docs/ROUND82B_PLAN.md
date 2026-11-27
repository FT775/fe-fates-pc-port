# Round 82b plan: Seal of Flames + Classic (2026-11-26, desk part by Claude, 02:30 to 02:40 EST)

**In one line:** let Seal of Flames hear the same "New Game started" step that round 81b gave Fates, so a Normal +
Classic New Game on Seal starts the randomizer and Nuzlocke, and give Seal the warning line too. One engine build.

## Why
- Round 82's new-parts track (N4) found the gap: Seal + Normal + Classic with the randomizer on gives the plain game,
  with no warning (build/r82/new/chain/n4-cla, n4-srv; the same answer on Casual is randomized).
- The cause is round 81b's plan D1. It assumed the randomizer's hooks are off on Seal, but they are on (F-047). The
  81b gate then kept Seal out of the step (`step_game`: Fates only).
- **Owner:** "Yes, that order" (2026-11-26 about 02:25) to Grok's order (docs/collab/SEAL_EDITION_SPLIT_GROK.md):
  round 82, then this fix as its own small round, then the split planning, then the split. That is the OK for this
  round's one build, at most one repair build, and the install after the checks.

## Timing against round 82
- Round 82 checks the installed round-81b program (through copies) and is still running.
- This round codes, builds, stages and proves on copies alongside it (at most 2 robot lanes, low priority).
- **The install and the final checks wait until round 82 has finished and been committed.** The workflow stops at
  "staged and proved". Claude runs the install part afterwards.
- DECISIONS / ROADMAP rows are written by Claude at the commit (F-069, row 82b), never by the workflow, so they do
  not collide with round 82's F-068.

## The design
- **S1.** `step_game` (fates_rando_session) is true for Fates **and** Seal. Both have the randomizer, and both have the
  same `StartFromBeginning` step (round 81 P6 trapped it on Seal).
- With the randomizer's hooks on, Seal now lays the trap at the defaults, exactly as Fates has done since 81b.
- **S2.** The two warning lines also apply on Seal, with the same words and once each.
- **S3.** Seal's randomizer output is unchanged: the seal/* fingerprints stay the same. The rest is unchanged too:
  round 81's rows, the Fates behaviour from 81b, loads, and the page.
- **Patch:** a new commit on e23bcf5, `core: Seal of Flames randomizer: hear the New Game step`, as patch 0042.

## Counts (estimates)
| Part | Count | Cap |
|---|---|---|
| Code + tests (S1-S3; the 81b tests that pinned "Seal does not listen" change on purpose, say so) | 30 min | 1 h |
| Review | 10 min | 15 min |
| Gate (0001-0042 apply, cargo, run_tests --core, fingerprints) | 10 min | 15 min |
| Build to build/r82b/stage/exe | 10 min | 25 min |
| Proofs (9 routes x 2.7 min + 20 min set-up, 2 lanes) | 45 min | 1 h 15 |
| Repair (only if needed, one build) | 45 min | 45 min |
| After round 82: install, core / full / smoke / fingerprints, docs | 45 min | 1 h |
| Report + commit | 30 min | - |
| **Total** | **3 h 25** | **hard stop 6 h real time** |

## Proofs (staged program, copies only, headless, own folders under build/r82b/)
- **Q1, Seal Normal + Classic:** with a queued randomizer answer (the same answer as round 82's N4), exactly one pick,
  the run laid, and run id + files equal to the same answer on Seal Casual. SEEN: the randomized unit on the map
  where N4 saw the plain Fighter.
- **Q2, Seal Casual and Phoenix:** one pick each, not two; run files equal to the installed program's (reference
  copies).
- **Q3, Seal Nuzlocke on Classic:** the Nuzlocke game starts once.
- **Q4, Seal loads:** a Seal save (robot-made, or a copy from round 76/82's Seal runs) loads with no pick and no
  warning.
- **Q5, Fates unchanged:** smoke 8/8 with memory equal; Fates Normal + Classic and Casual still pick once, with run
  files equal to the installed program's.
- **Q6:** the warnings on Seal are covered by unit tests only.

## Cut order
(1) Q4 if no Seal save loads headless, (2) Q2's Phoenix. Never cut: Q1, Q5.
