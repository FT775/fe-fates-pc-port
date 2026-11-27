# Agreed speed plan (Claude + Grok, 2026-11-13 night) — applies from round 9

Sources: docs/collab/SPEED_2026-11-13.md (Claude's measurement), docs/collab/SPEED_GROK.md (Grok's
critique). Claude accepts Grok's corrections: the gains overlap and are not added; H6 cannot save more
than its 50 min; mashing A/START desyncs; a capture run is NOT a second determinism copy; the 30-50%
"fast options" cut is unmeasured and only applies to chains with no recorded fights; the 73.7 min of
poll inside the round-7 robot stage must be named before any test-round target is quoted.

Finding: the emulator runs 7-10x realtime and model thinking is 15-26%. The cost is a fresh boot.exe
plus a Python post-pass every 22-70 frames (3.8 s a step, ~85% overhead): a chapter plays at 0.28x
realtime. Tests repeat work and run serially.

## Round 9, no owner OK needed
1. Integrate runs `check_all --slow` once (it already includes fast rows); builders keep a fast pass.
   Overrides EFFICIENCY_AGREED item 1 "fast every integrate, slow nightly".
2. Look-aheads skip the unused state decode + sha256 + contact sheet; heap dump only on marker frames.
   Clean replays and captures keep the full path.
3. The two determinism copies run side by side (fix the memory estimate); no foreground polling.
4. No second boot just to look at a state the last command already printed.
5. One recorded press list per player phase, stop on the first unexpected screen, no mash. The
   "boot again to that frame" driver only if the server (E) is NOT approved.
6. Longest job first; raise capture jobs only when no 12-run play session wants the slots.
7. Agent plays one call per phase: the model names who fights/waits/uses the vein, a small solver
   turns that into cursor moves (never picks targets), board read as text from memory, screenshot only
   on a mismatch or for a forecast check. Same model (no cheaper model for routine moves).
8. Name the 73.7 min wait in the round-7 robot stage.
Estimate: a recorded chapter ~125 min -> ~50-68 min; test round ~280 -> ~237 min.

## Needs the owner's OK
**Owner 2026-11-13 night: "Approve all four" = E, B, C and A approved (D not asked, not planned).**
E includes building the server-mode boot.exe from engine/ (a separate target folder; the existing
boot.exe stays for the proof replays until the server matches it byte for byte).
- E. Server mode for boot.exe (engine build): load once, commands on a pipe, states in memory, no
  picture on look-aheads, timeouts not polls. Chapter ~30-45 min. Clean replay from frame 0 with two
  original copies stays the proof.
- B. Parallel check_all (one output folder per row, never taking slots from a 12-run session):
  slow pass ~81 -> ~12-14 min; test round toward ~130-175 min.
- C. Replay stored records offline instead of a repeat live capture when only the capture library
  changed (integrate and verify); changed routes/hooks still play live.
- A. Result caches for H6 and planted-bug passes, key = preprocessed source/object hash + records
  digest + harness hash + compiler version/flags; clean run weekly and on any compiler/harness change.
- D. Fast in-game options (through the game's own screen) on a NEW chain with no recorded fights only;
  Birthright stays as recorded. Not planned on: unmeasured, and Conquest/Revelation already have fights.

Unchanged: 0 mismatches; two original determinism copies; real play never poked (F-019); engine
builds only with the owner's OK; Grok's "do not build the boot driver and E in the same round".
