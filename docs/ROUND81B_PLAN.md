# Round 81b plan: the Classic fix (2026-11-25, desk part by Claude, 23:40 to 00:00 EST)

**In one line:** the randomizer and Nuzlocke now also notice a New Game started on Classic. They listen to the same
"start from the beginning" step that round 81's New Game defaults use. One engine build.

## Why
Round 81's side look R1 (docs/RANDOMIZER_INGAME.md section 16) found the problem. `NewGameWatch` (fates_rando.rs)
only fires when `GameConfigData` word +0x4 changes at the pick. On Normal + Classic that word is already at its
reset value 0x00011E5E, so it does not change. The result: no pick, no randomized run, no Nuzlocke, and no message.
Round 81's writer (patch 0040) traps `StartFromBeginning` itself, and that trap fired on Normal + Classic in round 81's
P2 runs.

## The owner's words and the choice
- The owner said "fix the classic bug first", then "or just add a randomizer setting".
- Grok was asked (docs/collab/ROUND81B_CLASSIC_GROK.md): **do the real fix**. A second "Classic" switch on the
  randomizer page would mean two switches for one choice, and the player would not know which one won. Fates and
  Nuzlocke players expect to pick Classic on the game's own screen. Add one warning line instead of a new mode.
- Taken: the real fix, plus the warning. No new page row. Both cost one engine build. The owner's "fix it" is the
  OK for this round's one build (B1), at most one repair build, and the install after the checks.

## The design
- **D1. When the trap is laid.** The round-81 trap word (svc 0xEFFEC003 over 0x001D0618) is laid when any New Game
  row is set **or** the randomizer's hooks are on (`fates_rando_session::hooks_on`: Fates title and
  `Config::fates_rando`, which is off for Seal of Flames). Seal with no rows set: no trap, as in round 81. The rest
  is unchanged: a stranger word is left alone, `checks_itself()` false means off, and a state restore puts the word
  right.
- **D2. At the svc.** The same checks as round 81: lr 0x00441794, r0 == *0x006DA0F8, block readable, no player army,
  no map. When they hold, record "New Game step seen in this frame". That is used by the randomizer whatever the
  rows. The rows' pending store happens only while a row is set, exactly as in round 81.
- **D3. In the randomizer.** `Session::frame` treats a pick as **NewGameWatch fired OR the svc saw the New Game step
  this frame**. That is at most one pick per frame. A watch firing within 2 frames after an svc pick is the same
  pick (dedupe). The save-read load window rule stays. Casual, Phoenix and Hard + Casual still pick in the same frame,
  4019, exactly once. The seen flag is cleared at the frame end, so it never carries over to another frame or a state.
- **D4. The warning (Grok).** With the randomizer's hooks on, two cases get one plain line on screen (the existing
  `notice`) and in the log, once each:
  - The trap was hit but the checks refused, and no pick was taken in that frame.
  - The trap cannot be laid (a stranger word, or recompiled code that cannot check itself). New Games on Classic
    then cannot be seen.

  The words: "This New Game did not use your seed." For the second case: "Classic New Games cannot start the
  randomizer in this setup; pick Casual or Phoenix."
- **Unchanged:** the randomizer's output (every seed fingerprint), the page, round 81's rows and bytes, and loads (a
  load never reaches `StartFromBeginning`; lr check).
- **Patch:** 0041 `core: Fire Emblem Fates randomizer: hear the New Game step` (engine/zakuro fe14, on 0040 af3a9b8).

## Steps and counts (F-027; every figure an estimate unless marked measured)
| Part | What | Count | Cap |
|---|---|---|---|
| Desk | this plan, Grok, backups (made 23:54 measured: build/backup/*.2026-11-25-pre-r81b, pre-r81b.json) | 20 min | done |
| A1 | core fix D1-D4 + unit tests (planted: Classic pick fires once; Casual fires once, not twice; watch+svc in one frame = one; load = no pick; Seal no trap at defaults; refusal = warning once; stranger word = warning once; flag cleared at frame end and after a jump) | 1 h 00 | 1 h 30 |
| A2 | route bt-newgame-hard-classic (copy of bt-newgame-hard plus the Classic press, verified:false until seen); docs list | 20 min | 30 min |
| Review | one skeptic per track | 15 min | 20 min |
| G | apply 0001-0041 on a clean clone, cargo tests, run_tests --core, fingerprints | 10 min | 15 min |
| B1 | install.stage_build('r81b', 'build/r81b/stage/exe') + server; capture library only if STALE | 15 min | 25 min |
| P | 12 new routes x 2.7 min + 5 reference runs on the installed program x 2.7 min + 20 min set-up (4 lanes) | 1 h 10 | 1 h 40 |
| Repair | only if a proof fails on our code: the one repair build | 45 min | 45 min |
| C | core, check_all --core, smoke, fingerprints, hygiene, full; install; docs | 45 min | 1 h 00 |
| Report | REPORT_2027-01-28.md | 15 min | 30 min |
| Claude | read, fix, commit | 30 min | - |
| **Total** | | **5 h 20** | **hard stop 8 h real time** |

Round 81 ran in about 22% of its count (measured: 2 h 10 against 10 h 00). This count is made from this round's
parts, not copied.

## Proofs (staged program; every run headless, self-exiting, own folders under build/r81b/)
- **P1, nothing else moved:** smoke 8/8 with memory equal to the baseline (the trap word is outside smoke's ranges).
  Seed fingerprints are all the same.
- **P2, the fix:** a queued randomizer answer on bt-newgame-classic (Normal + Classic) and bt-newgame-hard-classic
  (Hard + Classic; SEEN mode and difficulty, and bytes GameUserData +0x28 = 01, +0x2D = 01). Pass:
  - exactly one "New Game mode picked" line;
  - the run is laid;
  - the run id and run files equal the same answer's on Normal + Casual.
- **P3, no double picks:** Normal + Casual, Normal + Phoenix and Hard + Casual with the same answer. Exactly one pick
  line each, and the run id and files equal the installed round-81 program's (reference runs).
- **P4, Nuzlocke on Classic:** a Nuzlocke answer on Normal + Classic. The Nuzlocke game starts once.
- **P5, loads are not picks:** bt-ch2 (chapter save) and opt-ch8-reload (battle save) with the randomizer on. No pick
  line, no warning, and memory equal to the installed program's except the trap word.
- **P6, rows and randomizer together:** Normal + Classic with all four rows set plus a randomizer answer. One writer
  line, one pick and the run laid.
- **P7, Seal (cut 2):** a Seal New Game at the defaults lays no trap (memory equal to the installed program). With a
  row set, it gets one write, as in round 81.
- **P8, the window's page (cut 1):** if a page-robot scenario drives the randomizer page at the mode pick, run it
  once on Normal + Classic: the page opens. Otherwise NOT REACHED, and it goes on the owner's look list.
- **The warning:** unit tests only; a headless refusal cannot be made without a poke. NOT REACHED in a game is said
  as such.

## Hard stops
- A failed gate, a fingerprint change, a visible window, or D: under 47.7 GB free.
- 8 h real time.
- Below the smallest useful set (P1, P2 Normal + Classic, P3 Normal + Casual, P5): stop and report, no install.

## Cut order
(1) P8, (2) P7, (3) the Hard + Classic route if it cannot be made, (4) the warning's second case (keep the first).

## Undo
`install.undo('r81b')`, then revert the round's one commit. The engine series before the fix is 0001-0040 at af3a9b8.
