# Round 71: the counted header (for your OK before any engine build)

Written in round 70 (2026-11-24, desk work only) from the three round-70 tracks: docs/rando/CHESTS.md,
docs/rando/FULL_SWAP_PLAN.md (section 7), docs/DOWNLOAD_PLAN.md (section 8), and the roadmap
(docs/ROADMAP.md, build/roadmap/ROADMAP_PLAN_2026-11-24.md "Round 71"). Nothing in this file has been built.

## In plain words

**What you will see after round 71** (each one shown to you as a looked-at picture, nothing counts until you
say ok, F-037):

1. **Chests and villages give new items** when the new page row "Chest and village items" is on. Each new
   item is about as strong as the old one (the same-band rule you chose). Story and key items (Yato and its
   forms, Ganglari, Corrin's Dragonstone, Draconic Rage, Missiletainn, keys) never change. With the row off
   (the default) every chest gives exactly what it gives today.
2. **The Esc menu's Randomizer window** gets a "Next New Game" part under "This run": the same rows as the New
   Game page, with Keep / Defaults / Randomize everything. It never changes the game you are playing.
3. **The help text fits:** "Randomize everything" writes one short line, and the help area keeps a fixed
   height of two lines, so the buttons never jump.
4. **Growths in Preparations** on the **Y button** (keyboard: Zakuro's Y key, A by default). Select / Tab
   stays the growth key on the battle map.
5. **Recolour gets its own page row** (on by default whenever the shuffle is on), and the hair colour is made
   easier to see, still battle hair only (F-047 recolour scope).
6. **The no-game-code program** (the base of a future download) is built to a test folder and tried headless
   in a sandbox. Nothing is installed, nothing is downloaded, nothing is released.

**How long:** counted **14 h 40** in two sittings (8 h 10 code and unit tests, then 6 h 30 builds, proofs,
checks and the report). That is 1 h 40 more than the roadmap's "about 13 h", because round 70 counted the parts
bottom-up and kept the slower number each time. Most parts are estimates (never measured); the builds and
checks are counted. If it runs long, the cut order is: growths in Preparations (saves 1 h 55), then the
Recolour row (saves 1 h 05), then the download staging (saves 1 h 35). With all three cut: 10 h 05.

**What needs your OK:**

- **The engine builds in sitting 2** (listed below): the game program (engine.py port), at most one repair
  build, boot-server, the capture library only if it is stale, the cargo tests, and the no-game-code program
  to a staging folder. One line from you ("Yes, start round 71") is the OK for all of them. Your game,
  saves and Zakuro settings are backed up first and never written.
- Nothing else. The round-70 calls in docs/DECISIONS.md F-055 all have defaults; silence means the default.

## The parts, counted

"Counted" = a time we have measured before (with the round it comes from). "Estimate" = never measured; it
is written on the slow side. Every part has a cap of its count plus half, rounded up to 5 min.

### Sitting 1: code and unit tests (no build, no game run): 8 h 10

| # | Part | Time | Kind | Patch files | Source |
|---|---|---|---|---|---|
| A1 | Chest and village hook: new `crates/zakuro-core/src/fates_rando_chests.rs`, an svc entry trap at `anonymous_namespace::ItemGain` 0x003B0768 that swaps the item id from the run's chest list (off = original word back, original game); `tools/randomizer/chests.py` wired into `tracks.py`, the schema row "Chest and village items" (default off, its key left out of the run id when off, so every old seed keeps its id) and the chest list in the run's mod folder; unit tests; rcheck.judge_chest already coded | 2 h 30 | estimate (the track's engine part was 60 min; the roadmap's 2 h 30 kept as the slower count) | new `0031-core-...-chest-and-village-items.patch` (zakuro-core: new file, core hook registration) | CHESTS.md sections 3-5 |
| A2 | Esc "Next New Game": `draw_this_run` gets a data parameter, a "Next New Game" part under push_id("next"), `keep_next()` and a shared `write_last()`, robot targets with a `next:` prefix | 2 h 00 | estimate | new `0032-page-...-next-new-game-and-help-line.patch` (`crates/zakuro/src/rando_page.rs`, `lib.rs`, `pagebot.rs`; `menus.rs` unchanged) | FULL_SWAP_PLAN.md section 6 |
| A3 | The help text fits: one-line "Randomize everything" note, `help_line()` with a fixed two-line LayoutJob (max_rows 2, ellipsis, full text on hover) | 30 min | estimate | same 0032 | FULL_SWAP_PLAN.md section 6 |
| A4 | Growths in Preparations on Y: `prep_shown()` in `fates_growth_view.rs`, `filter_input` takes Y only there; help text line | 1 h 45 | estimate (roadmap 1 h 30) | new `0033-core-frontend-...-growths-in-preparations.patch` (`crates/zakuro-core/src/fates_growth_view.rs`, page help text) | FULL_SWAP_PLAN.md section 5 |
| A5 | The switched-off page test fixed or removed | 20 min | estimate | none (tests) | roadmap |
| A6 | Recolour row + clearer hair colour (Python only, schema and colours.py; battle hair only) | 1 h 00 | estimate | none (Python) | roadmap; F-047 recolour scope |

Sitting 1 ends with `run_tests.py --core` (counted 5 min: round 69 core 120 s) and a fingerprints check:
with every new row off, every seed fingerprint must be unchanged (counted 1 min: 24 s in round 70). If one
changes, sitting 1 stops there and says which.

### Sitting 2: backups, builds, proofs, checks, report: 6 h 30

| # | Part | Time | Kind | Builds |
|---|---|---|---|---|
| B0 | build/STOP_ROUND absent; D: free measured (stop under 30 GB free after the need below); back up `play\game` exe + build-record + game-path.txt + boot-server + capture library to `build/backup/*.<date>-pre-r71` | 5 min | counted (rounds 59-62 backups) | none |
| B1 | `engine.py port` with patches 0031-0033 (the installed exe b4a887b2 is replaced only after C1 and C2 pass, in step C3) | 1 h 00 | counted (round 68 header: 30-60 min) | **game exe** |
| B2 | One repair build, only if B1 or a proof fails on our code | 45 min | counted allowance (roadmap) | game exe again (at most once) |
| B3 | boot-server with zakuro_head (F-053 (6)), the capture library (only if `build.py` says STALE after the patches: expected fresh, since no menu or capture file changes), cargo tests | 15 min | counted (boot-server 5 min, capture library 306 s, cargo tests 6 min) | **boot-server**, capture library if stale |
| B4 | The no-game-code program to `build/r71/libmode/stage` only (cargo build, own target folder) | 30 min (cap 40) | estimate (roadmap 20) | **no-game-code program (staging only)** |
| P1 | Chest and village proof: one chapter per path (Birthright, Conquest, Revelation) plus Seal of Flames, the robot opens a chest or visits a village from an existing recording; `rcheck.judge_chest` compares the item the game gave with plan.json, row on and row off. Chapters picked from build/r70/chests against the recorded routes. A path with no recording that reaches a chest moves to round 72 (cheat pokes are OK'd only for rounds 72 and 75, F-054). Also settles terrain kind 10 = chest, 1 = village | 1 h 00 | estimate | none |
| P2 | One looked-at (SEEN) picture per new feature, on the final program: a chest item on and off; the Esc "Next New Game" part; the help line with the one-line note; growths in Preparations from the bt-ch9 checkpoint (frame 5875) with Y pressed in the robot's test copy (the first picture also settles whether Pick Units draws the stats on the top or the bottom screen); the Recolour row on and off (zoomed battle crop) | 40 min | estimate | none |
| P3 | Library-mode sandbox test (DOWNLOAD_PLAN.md section 4): sandbox folders under build/r71/libmode (APPDATA, LOCALAPPDATA, TEMP, data, ROM copy with sha before and after); Zig 0.17.0 **copied** from your real %LOCALAPPDATA% (read only, never written there); real-folder snapshot before the copy and after the run (realdirs.py); Recompile with `CC='zig cc'`; headless runs a-d (same game memory at frames 0/3000/4600/5200, the page by the page robot, 60 fps and 16:9, recolour); row e (Seal profile) is skipped without port mode. If it fails, the download slips and no extra engine OK is spent | 1 h 05 | estimate (10 + 15 + 25 + 15 min) | none (uses B4) |
| C1 | CORE: `run_tests.py --core`, `check_all.py --core --jobs 4`, smoke with `--bin` on the staged B1 game exe (8/8, randomizer-off memory equal to today's program) | 15 min | counted (round 69: 120 s + 47 s + 101 s) | none |
| C2 | **FULL place:** round 71's last check is `run_tests.py --full` with the staged B1 game exe, because an engine patch makes FULL due (F-052). The F-051 full matrix (every chapter, all settings) is round 72, on exactly this program | 15 min | counted (round 69: 233 s) | none |
| C3 | Install after C1 and C2 pass (release install step with automatic rollback), memory check of the installed exe | 10 min | estimate | none |
| R | Report with the pictures and the undo steps | 30 min | counted (roadmap) | none |

Grok: one consult at the start of sitting 1 on any open page wording (5 min, inside A2).

### Totals

| | Time |
|---|---|
| Sitting 1 (A1 150, A2 120, A3 30, A4 105, A5 20, A6 60, core + fingerprints 5, rounded up) | 8 h 10 |
| Sitting 2 (B0 5, B1 60, B2 45, B3 15, B4 30, P1 60, P2 40, P3 65, C1 15, C2 15, C3 10, R 30) | 6 h 30 |
| **Counted total** (B2 included, as the slow side) | **14 h 40** |
| If no repair build is needed | 13 h 55 |

Hard stop per sitting: 1.5 times its count (sitting 1: 12 h 15; sitting 2: 9 h 45).

### Cut order (if a sitting runs past its count)

1. **Growths in Preparations** (A4 1 h 45 + its picture 10 min = 1 h 55). Patch 0033 is then not made.
2. **The Recolour row** (A6 1 h 00 + its picture 5 min = 1 h 05). Python only, nothing in the engine.
3. **The download staging** (B4 30 min + P3 1 h 05 = 1 h 35). The download waits for 3dsrecomp's author
   anyway (F-054 call 3), so cutting it costs only the early proof.

With all three cut: **10 h 05** (14 h 40 minus 4 h 35).

## Not in round 71 (on purpose)

- **Port mode** (DOWNLOAD_PLAN.md section 3.1, +1 h 20 estimate, a new frontend patch in `lib.rs`): left out.
  Without it the library-mode test runs rows a-d; the Seal row waits. The download cannot ship before
  3dsrecomp's author answers, so port mode waits for that answer (F-055 call D3, default: not in round 71).
- **Presets and the share code** (2 h 10 estimate), **the full swap's names, voices and faces** and the
  expression backstop: round 74 (FULL_SWAP_PLAN.md section 7).
- **Event gifts and gold chests** stay as they are (CHESTS.md section 2).
- No Windows Sandbox, no download of any kind, no push, no release tag, no delete.

## Disk

| Need | Size | Kind |
|---|---|---|
| Engine build output (engine/zakuro/target is 1.7 GB today; a port build adds the game exe and objects) | up to 4 GB | estimate |
| Backups (exe, boot-server, capture library) | about 1 GB | estimate |
| Library-mode sandbox (ROM copy 2 GiB, Zig 0.4 GB, recompiled library, runs) | about 6 GB | estimate (DOWNLOAD_PLAN.md) |
| Robot proofs and pictures | about 2 GB | estimate (round 62's folder is 7.4 GB for a much bigger run) |
| **Total** | **about 13 GB** | estimate |

D: had 105 GB free on 2026-11-24 (measured in round 70). Stop rule: B0 measures again, and the round stops if
D: would fall under 30 GB free.

## Hard rules in round 71 (as in every round)

build/STOP_ROUND checked before every game or robot start; every start headless and self-exiting with its data
folder and APPDATA/LOCALAPPDATA under build/; at most 6 robot jobs at once; never relaunch a run more than
once; a visible window = failed run; never start play\game\Fire Emblem Fates.exe; no Nintendo or Seal of Flames
bytes in git; your saves, Zakuro settings, cheats and mods are never touched; every process started is listed
and killed before the round returns.
