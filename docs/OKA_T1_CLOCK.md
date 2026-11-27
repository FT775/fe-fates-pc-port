# OK A T1: the clock byte, bt-ch9 and bt-ch9-ore (round 48, 2026-11-20)

Chapter oka-t1, owner "Yes, all three" (F-042). This finishes the two T1 routes round 40 left out (cap) and
round 46 started but was stopped (its runs killed; build/oka/t46 is treated as dirty and only read). **Nothing here
changes the test definitions.** The T1/T2/T3 rule changes of rounds 38/40 still wait for the owner (F-037).

## In plain words

- Both routes ran under T1 on a fresh armed test tree (build/oka/t48): original, armed readable, readable
  without writers, and shadow mode. 8 runs, all completed, 0 timeouts, 0 retries.
- **bt-ch9-ore: PASS.** Every save file is byte-identical to the original game's. Shadow mode: memory, saves,
  clock and random numbers all identical to the original.
- **bt-ch9: one save byte differs, and it is the clock.** The byte is the low byte of the game's saved
  "real time" clock (GameRealElapse +0x10), 0x64 in the original and 0x63 in readable mode: 1 millisecond. Shadow
  mode is identical to the original. **But the T1 rule as written is not met**: the rule allows clock bytes only if
  every clock read differs by at most 1 ms, and one later read (call 46, from `unit::Identifier::SetIdentifier`)
  differs by 2 ms. So bt-ch9 is **FAIL by the letter of the rule**, though the only differing save byte is the
  proven clock field. The owner decides (review item below).
- **Random numbers (the round-40 risk):** no random seed reads the moved clock on these routes. All 52 / 57
  generator seeds are identical in every mode, and the seed-time clock reads are identical. Readable mode does
  draw from the game's one global generator in a slightly different order from roll 4,968 on (sound-effect
  variation and per-frame tasks); that changed no save byte beyond the clock and did not change how either route
  played (same frames, same end).

## What ran

| Item | Value |
|---|---|
| Tree | build/oka/t48: fresh `git archive` of HEAD e0b09bb + the OK A tree-only edits used on t41/t46 (writer.c: `config_options`, `config_options_hook`, `config_save_guard` armed; 3 override rows; menu_options_overrides.c as t41) + a log-only probe (`oka_time_probe.c`: GetNow, Random::Initialize, Random::GetValue(void) every roll up to 20,000 then a hash every 4,096). Sources compared with t46/t46d: equal except comment text. TREE.json written. |
| Library | t48 sha256 bfec3778...; built with build.py in its own folder, below normal, 297 s; never swapped in |
| Shared library | build/harness/lib 610f791d... before and after every step |
| Diagnosis tree | build/oka/t48d = t48 + one log-only override of Random::GetMaxMin (caller log); sha 82174891...; 2 runs |
| Runs | opt-t1r48-{o,a,r,h}: o = t48 original mode, a = armed readable with the three writers listed, r = readable without writers, h = shadow mode. 2 lanes, below normal, headless, data and APPDATA/LOCALAPPDATA under build/parallel/... Wall 2,270 s. Diagnosis opt-t1r48-{o,a}diag on bt-ch9-ore, 623 s |
| Safety | %APPDATA% / %LOCALAPPDATA% zakuro: 0 files changed (snapshot and timestamp check); no options file; no visible window (boot.exe had no main window, below normal); no retry; no commit; t46/t46d untouched |
| Tools and results | build/oka/r48/: build_t48.py, build_t48d.py, run_t48.py and analyse48.py (copies of round 46's), rngcmp.py, rows.json, rowsdiag.json, t1_result.json, analyse48.out, rngcmp.txt |

## Results

| Route | frames | O memory | A memory | R memory | H memory | T1(a) A = R | T1(b) saves A vs O | T1(c) shadow | T1 |
|---|---|---|---|---|---|---|---|---|---|
| bt-ch9-ore | 162,800 | 25a4d7e8... (= the known original hash) | 20b3063a... | 20b3063a... | 25a4d7e8... | PASS | PASS: 6 of 6 files byte-identical | PASS: memory 0 bytes apart, saves equal, 0 mismatch lines, clock and RNG logs identical | **PASS** |
| bt-ch9 | 147,400 | eb41cae1... (= the known original hash) | 3f6c0c40... | 3f6c0c40... | eb41cae1... | PASS | Chapter0 differs in 1 decoded byte, the clock field (below); the "every call at most 1 ms" condition fails at call 46 (2 ms) | PASS: memory 0 bytes apart, saves equal, 0 mismatch lines, clock and RNG logs identical | **FAIL under the written rule** (save byte = clock, proven) |

The writers add nothing: armed = readable without writers, byte for byte, on both routes.

## Byte evidence (bt-ch9, Chapter0)

- Raw files: 5,500 bytes each, 31 raw bytes differ (Huffman stream). Header (0xC0 bytes) equal. Decoded body
  19,536 bytes each (build/oka/r40/savedec.py).
- **Exactly one decoded byte differs: body offset 0x1D82, original 0x64, readable 0x63.**
- The u64 at 0x1D82 is 0xAD4D504464 (original) and 0xAD4D504463 (readable): milliseconds since 2000-01-01, the
  same format round 40 found (bt-castle-shop 0x143B, bt-ch8-support 0x1B98).
- It is the clock field: this run's own GetNow log shows call 30, from lr 0x001D16E8 (`GameRealElapse::Update`),
  returning 0xAD4D504464 in O and 0xAD4D504463 in A, exactly the two saved values. In both end states the
  `GameRealElapse` objects (vtable 0x0068F62C) are present in FCRAM, and their +0x10 fields hold the same kind of
  GetNow values (for example FCRAM 0x26706F0 +0x10 = 0xAD4D751434 in both). Round 40's fixed address 0x2670678 holds
  no GameRealElapse at the end of these routes (the object moved; the analyser's fixed-address check therefore reads
  "vtable not found" and the object was located by vtable search instead).
- GetNow log, O vs A: 102 calls each, same callers in the same order. 28 values differ: 1 x `Update`
  (0x001D16E8, -1 ms, the saved one), 18 x `GameRealElapse::GetNow` (0x0050B01C, -1 ms each), 9 x
  `unit::Identifier::SetIdentifier` (0x00418B4C, -1 ms, **and call 46: -2 ms**). R gives the same 28. H: 0.
- bt-ch9-ore has the same 28 differing reads (the routes share their start), but its later save stores an
  `Update` value that is equal in both modes (0xAD4D751434), so every file matches.

## RNG check

- **Code**: the clock reaches the generators only through `Random::InitializeAll` (lr 0x0044AC4C, called from
  `MainSequence::InitializeA` and `GameReset`). `unit::Identifier::SetIdentifier` reads the clock for unit IDs, not
  for a generator. `Random::Initialize` has 50 call sites (map sequence, AI, level-up, lottery, castle...); their
  seeds come from the game, not from GetNow (round 46's static list, build/oka/r46/rng_seed_callers.txt).
- **Logs, both routes, O vs A, R and H**:
  - InitializeAll's three GetNow reads (calls 1, 16, 20) are identical in every mode (0xAD4D4F88FF,
    0xAD4D4FD905, 0xAD4D4FED75).
  - Every `Random::Initialize` call (52 on bt-ch9, 57 on bt-ch9-ore) has the same caller and the **same seed**,
    in the same order.
  - The **first random roll and the first 64 are identical**; in fact the first 4,967 rolls are identical.
  - From roll 4,968, readable mode (A and R alike) differs on the **global generator** (0x00752B7C): one extra
    roll from `Random::GetMaxMin`, then the same stream shifted. The `rolls_before` counts at later seeds drift
    (5,931 vs 5,932 ... 101,638 vs 101,648). Its consumers are `ProcInst::RecursivePersistentTask` (per-frame),
    `ParameterSound::Play` / `ParameterSound::EffectParameter` (sound-effect variation, `GetMaxMin(0,0)`) and
    `kaneko::frnd`. The diagnosis runs (t48d) show the sound calls already change order at roll ~4,802 (same
    values, other consumer) before the count changes. The separately seeded generators (0x00752B8C/9C/AC/BC,
    0x0FFFFF10, the AI objects) made 550 of the first 20,000 logged rolls; all 550 have the same caller and value
    as O, in A and in R, on both routes. After roll 20,000 only a running hash over all generators is logged, so
    later rolls of the seeded generators were not compared one by one (their seeds were, and the saves were).
  - Shadow mode (H): every roll, seed and clock read identical to O on both routes.
- **Meaning**: readable mode's saved cycles move per-frame timing (as round 40 found), which reorders draws on the
  global generator. No seed moved and nothing reached a save except the one clock byte. The risk round 40 noted
  stays open for routes this check did not cover, and in principle for any gameplay draw from the global generator.

## Review item for the owner (not applied, F-037)

1. **T1(b)'s clock exception on bt-ch9**: the only differing save byte is the proven `GameRealElapse` clock field
   (1 ms), but one later clock read differs by 2 ms (call 46, SetIdentifier, after that save). Choose: (a) keep "at
   most 1 ms per call" (bt-ch9 stays FAIL), (b) apply the 1 ms bound only to the reads whose values reach a saved
   byte (bt-ch9 PASS), or (c) another bound.
2. The round-40 T1 correction, round-38 T3 rule and round-40 T2 danger rule are still unseen and unapplied.
3. Note for the RNG risk: readable mode reorders the global generator (sound variation, per-frame tasks) from
   roll 4,968 on both routes; seeds and seeded generators are unchanged; a "charge the guest budget" fix (round 40)
   would be an engine/runtime decision.

With these two routes, T1 has now run on all 14 Birthright routes (12 on t41 in round 40, 2 here). OK A is
**not green**: it waits on the owner's answer to the items above.
