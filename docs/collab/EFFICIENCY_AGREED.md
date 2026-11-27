# Agreed speed-up plan (Claude + Grok, 2026-11-13) — applies from round 8

Claude accepts Grok's corrections (docs/collab/EFFICIENCY_GROK.md): a counted batch is code plus
integrate, so the realistic gain is about 1.3-1.5x, not 2-3x; the owner's priority is the options
path, not the reader backlog; two parallel batches double the "missed early give-up" class of bug.

1. Live compare and fast `check_all` on EVERY integrate (the proof; unchanged). `check_all --slow`
   once a night. The integrate reviewer re-aggregates the summaries and plants one bug in the NEW
   files only; it does not re-run the full compare when commit and memory hashes match.
2. One idle-fill reader batch only while a long robot round runs, in its own folder; registry rows
   appended by the integrator; it never integrates ahead of the writer gate and counts only after
   the live compare. A second parallel batch only after one idle-fill batch integrates clean.
3. Queue order this week: writer gate (round 7) -> options route + first switch-on request to the
   owner -> idle-fill readers. No Conquest/Revelation button search yet; replays and the labelled
   cheat track may run beside the story.
4. Round 8 records the integrate split as five numbers (rebuild, live compare, check_all, docs,
   reviewer) before any further cut.
5. Agents are split only along function groups that do not call each other.
6. No gaps: the next round starts when the previous one is committed; 12 runs day and night
   (owner OK 2026-11-13). Owner minutes stay at zero unless a decision is genuinely theirs.
Unchanged: F-017 (no writer on before the gate + owner OK), F-019, engine builds need owner OK,
0 mismatches before anything counts.
2026-11-13 evening: item 3's "No Conquest/Revelation button search yet" is overridden by the owner ("yes, run all three routes in round 8"); see docs/DECISIONS.md F-022.
