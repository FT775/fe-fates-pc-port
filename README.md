# Fire Emblem Fates (Special Edition, USA): PC port and modding tools

**Fire Emblem Fates on a Windows PC, with an in-game randomizer, Nuzlocke and a few helpers. It is not a new story.**

## What this is

This is the **source** of a PC port of Fire Emblem Fates: tools, our patches to fearkov's Zakuro (a 3DS runtime),
tests and guides. **There is no program and no game in it**: no .exe or .dll, no Nintendo files, no game text. You
bring your own copy of the game, and the game program is made on your own PC from it.

**What you need**
- Windows 11, Python 3.13 (standard library only, no `pip install`) and Git for Windows.
- Your own **decrypted** `.cci` of Fire Emblem Fates **Special Edition (USA)** (product `CTR-P-BFZE`). Its SHA-256 is
  checked against `config/game.json`. Birthright or Conquest alone, other regions, encrypted dumps and update files
  are refused. It goes in `roms\` and is never shared.

**Two roads.** Neither has been tried on a clean PC yet.

| | Road A: stock Zakuro, no build | Road B: build our patched Zakuro |
|---|---|---|
| What you do | Install Zakuro (github.com/fearkov/zakuro), press Recompile on the game once, run `PLAY.bat` and point it at Zakuro (key Z) | Install Rust, the Visual Studio C++ Build Tools, a C compiler and an archiver, then run three commands: [docs/BUILD.md](docs/BUILD.md) |
| What you get | The plain game through `PLAY.bat`: the game-file check and save backups | Everything: the in-game Randomizer page, Nuzlocke, the growth view, True hit, New Game defaults, built-in 60 fps battles and 16:9 top screen |
| What you do not get | The Randomizer page, Nuzlocke, the growth view, True hit, New Game defaults, the built-in 60 fps / 16:9 (they live in our 43 Zakuro patches) | - |
| Time | Zakuro's own Recompile (not timed here) | Installing the tools 30-60 min, first build 30-60 min (both **estimate**) |
| Disk | Zakuro's own files (not measured here) | The build folder 4.98 GB (**counted** on the project's PC), the Randomizer's game files about 1.8 GB; plan for about 15 GB free (**estimate**) |
| Notes | The project uses Zakuro v0.2.32; a newer one was never tried | The program you build holds the game's code: **never share it** |

**3dsrecomp** (fearkov's recompiler) has **no licence file**. It is not in this download: the build fetches it
unmodified at a fixed version (a pin) for your own build only. Never share the program you build.

**Honest state.** The project's robots play every chapter of all three stories with the randomizer off and on; nobody
has yet played a randomized game to the end by hand. Known limits (a rare refused seed, Start taking a few seconds
after a late page change, and more) are listed in the release notes, `config/release/notes/`.

**Start here:** [Read Me First.txt](Read%20Me%20First.txt) (playing, saves, controls, the randomizer). To build:
[docs/BUILD.md](docs/BUILD.md). Who made what: [CREDITS.md](CREDITS.md).

## Get started

1. Read **[Read Me First.txt](Read%20Me%20First.txt)**: put your own `.cci` in `roms\`, then double-click
   `PLAY.bat`. It checks your copy, backs up your save and starts the game. If something is missing, a "Getting
   ready" window asks for it.
2. For the full port (Road B): **[docs/BUILD.md](docs/BUILD.md)**.
3. What comes next: **[docs/ROADMAP.md](docs/ROADMAP.md)**.
4. For the project owner only: making a release, **[docs/RELEASE.md](docs/RELEASE.md)** (`RELEASE.bat`). You do not
   need it to play.

## Where things stand

State at round 85 (written 2026-11-26, before release r86). Nothing counts as done until the owner says ok
(F-037); "robot" means checked by the test robot in its own test game, "seen" means a person looked at the
pictures. Program hashes and times are from the project's own PC.

| Area | State | Guide |
|---|---|---|
| Playing | **works**: the standalone program `play/game/Fire Emblem Fates.exe`, built from Zakuro v0.2.32 plus our 43 patches (first built 2026-11-10; the installed one is round 83's, sha256 `3a471269...`). `PLAY.bat` checks the game file, backs up the save and starts it, and stops if the program does not match its build record (`--anyway` gets past it). In a new folder the **Getting ready** window (round 77) finds the game file, points PLAY at Zakuro or the built program and prepares the Randomizer; a freshly unzipped folder keeps its saves inside it. First run: 60 fps battles, 16:9 top screen, 3x | [PLAY.md](docs/PLAY.md), [BUILD.md](docs/BUILD.md), [ENGINE.md](docs/ENGINE.md) |
| Randomizer | **built, in the game**: after New Game and the Casual / Classic / Phoenix pick (Classic since round 81b), a Randomizer page opens (Esc > Randomizer shows the run later). Rows under seven headings, each with a help line: classes, growths, skills, items, shops, chests and villages, enemies and bosses, the character shuffle with "keep the face" or the **full swap** (faces and names in scenes too, round 76), music, children, promotions and more. **Presets** Light and Wild and a **share code** (round 74). **Seed guarantees** (round 75b): a door opener, a healer and, where a map needs one, a flier join in time. A seed gives the same game every time; with Randomizer off the game is the original. Round 82's full check: 536 of 536 robot jobs, 0 FAIL. A rare seed is refused by the randomizer's own safety check (press Back, pick another). `PLAY RANDOMIZED.bat` is the older way (one profile per seed) | [RANDOMIZER.md](docs/RANDOMIZER.md), [RANDOMIZER_INGAME.md](docs/RANDOMIZER_INGAME.md), [tests/CHECK_R82.md](docs/tests/CHECK_R82.md) |
| Nuzlocke | **built** (rounds 60-61): a fallen unit stays fallen (graveyard file, battle saves too); passes on all three stories; on Classic too since round 81b | [rando/NUZLOCKE.md](docs/rando/NUZLOCKE.md) |
| Growth view | **built**: on the map's unit panel, Select / Back / Tab or the Growths button shows growth percents (round 62); in Preparations on Y (round 71); randomizer on or off | [REPORT_2027-01-06.md](docs/REPORT_2027-01-06.md) |
| Helpers | **built** (rounds 80-81): Esc > Helpers. **True hit** (Off at first) shows the real chance to hit beside the forecast's number; **New Game defaults** set battle animations, map speed, enemy turn skip and HP bars once for each New Game. Not yet looked at on screen by a person: the True hit label and the Helpers help line | [PLAY.md](docs/PLAY.md) section 6f |
| Test robot | **runs on Fates**: headless, closes by itself; real-play routes through all three campaigns plus a labelled cheat track for its own test game; the smoke set (6 short runs, about 2 minutes) passed 6/6 in round 84 | [ROBOT.md](docs/ROBOT.md), [HARNESS.md](docs/HARNESS.md), [harness/SMOKE.md](docs/harness/SMOKE.md) |
| Tests | round 84: FULL 1,023 unit tests, 0 failed, 1 known skip; CORE 1,000, 0 failed (`tools/release/run_tests.py`) | [REPORT_2027-02-01.md](docs/REPORT_2027-02-01.md) |
| Release | **one command**, for the project owner: `RELEASE.bat` checks, tests, packs a source-only zip and tags it locally; it never pushes. r68 (2026-11-24) is the public one so far; r86 is being prepared (round 85). Release numbers follow the work rounds | [RELEASE.md](docs/RELEASE.md) |
| Modding | text (all 1,328 message files), all 412 stat-table files, pictures, maps and My Castle data rebuild byte-identical; the mods tool builds, installs and uninstalls; the owner ok'd the renamed name, Mov +2, the skill icon and the portrait in game (round 42) | [MODDING.md](docs/MODDING.md), [TABLES.md](docs/TABLES.md), [ASSETS.md](docs/ASSETS.md), [MAPS.md](docs/MAPS.md), [CASTLE.md](docs/CASTLE.md) |
| Function names, code and ROM rebuild | **done**: 27,074 functions found, 26,118 named from the game's own symbol map; the code and the whole ROM rebuild byte-identical | [SYMBOLS.md](docs/SYMBOLS.md), [CODE.md](docs/CODE.md), [ROM_REBUILD.md](docs/ROM_REBUILD.md) |
| Readable code | 266 overrides and 31 helpers written as readable C (`config/readable/functions.csv`), compared with the game's own code in shadow mode; the 5 writers stay off (no writer is armed) | [READABLE.md](docs/READABLE.md) |

The full story, round by round: the reports `docs/REPORT_*.md` and the dated sections of
**[PORT_PLAN.md](docs/PORT_PLAN.md)** (the first plan; its rough total, about 57.4% [low], is from round 68). Rulings:
**[DECISIONS.md](docs/DECISIONS.md)**.

## For developers

The rest of this page is for people working on the project: setup, every tool, the checks and the guides. The project is
built from the Fire Emblem Awakening port's tooling (F-001); game: title `0004000000179800`, all three routes on one
card.

### Setup

Windows 11, Python 3.13 (standard library only; no `pip install`), Git for Windows.

1. Put your own clean dump in `roms/` (any name ending `.cci`; its title and SHA-256 are checked:
   `config/game.json` `rom_sha256`; an update `.cia` or another edition is refused). Every tool finds it through
   `tools/paths.py` (for one release the old repo-root places are still found, with a note).
2. Play: `PLAY.bat`. It starts the standalone program `play/game/Fire Emblem Fates.exe` when it
   is there (Road B: `engine.py fetch`, `apply`, `port`, docs/BUILD.md), else an installed
   Zakuro with the game recompiled once (Road A); PLAY says what is missing. Nothing else below is needed to play.
3. For the tools, extract once (everything goes to the gitignored `extracted/`):

   ```bat
   python tools\extract_rom.py
   python tools\rom\extract.py
   python tools\assets\romfs.py
   python tools\toolchain.py
   ```

   In order: code.bin and layout.json (code tools); every part of the .cci (ROM rebuild); the RomFS files
   (assets, tables, mods); the Arm GNU toolchain finder (code rebuild).

4. Check everything. Day to day: `python tools\release\run_tests.py --core`, `python tools\check_all.py --core
   --jobs 4` and `python tools\harness\smoke.py run` (together under 5 minutes on the project's PC, round 67,
   counted). `python tools\release\run_tests.py --full` runs every unit test in 4 lanes (about 4 minutes, round
   68, counted); `python tools\check_all.py --slow` adds the long asset, ROM, comparison and robot rows (weekly,
   F-028). In a folder unpacked from a release zip, the unit tests are meant to end with 0 failed (the release
   checks this on its own zip): the few that need something a download does not carry skip with a plain reason
   (the engine source before `engine.py fetch`, an old round's check files). `smoke.py` needs the robot's own
   programs and recordings, which a download does not carry (docs/HARNESS.md).

Never commit anything under `extracted/`, `build/`, `asm/`, `play/`, `engine/` or a mod
folder; `check_all` checks it. In the project's own rounds, builds of the engine (cargo, `engine.py build`/`port`)
need the owner's OK (F-004).

### The tools

| Tool | What it does |
|---|---|
| `PLAY.bat` -> `tools/play/play.py` | checks the ROM, updates and the recompiled code, backs up the save, starts the game (standalone exe or Zakuro); `--dry-run`, `--where`, `--backup`, `--help` |
| `PLAY RANDOMIZED.bat` -> `tools/play/rando.py` | the older randomizer launcher: one profile per seed in `play/randomizer/<seed>/` with its own saves and mods ([RANDOMIZER_PAGE.md](docs/RANDOMIZER_PAGE.md)); the in-game page is the main way now |
| `tools/randomizer/rando.py` (+ the modules beside it) | the randomizer: `make` (a seed -> a mod folder or an in-game patch, with a spoiler log), `check` (remake and every guard), `schema` (the page's rows) ([RANDOMIZER.md](docs/RANDOMIZER.md)) |
| `tools/play/Make Desktop Shortcut.bat` | a Desktop shortcut to PLAY |
| `RELEASE.bat` / `RELEASE WITH ENGINE BUILD.bat` -> `tools/release/release.py` | for the project owner: the one-command release (round 68): preflight, core tests, smoke, package (zip, bundle, sums, notes, gates incl. privacy), record, local tag; never pushes (`push` is owner only); `--dry-run`, `--rehearse`, `status`, `undo rNN` ([RELEASE.md](docs/RELEASE.md)) |
| `tools/engine/engine.py` | fetches Zakuro + 3dsrecomp at the pins (`config/upstream.json`), applies `patches/zakuro/`, builds, makes the standalone exe (`port`); `selftest`, `port --dry-run` build nothing ([BUILD.md](docs/BUILD.md)) |
| `tools/gamecfg.py` | reads `config/game.json` (every per-game constant) for all tools |
| `tools/extract_rom.py` | decrypted .cci -> `extracted/code.bin` + segment layout |
| `tools/rom/extract.py`, `rebuild.py`, `tests.py` | every part of the .cci out; the whole 2 GiB image back, byte-identical; mutation/shift tests |
| `tools/rom/blz.py`, `romfs.py`, `ctr.py` | ExeFS code compression, RomFS images, NCCH/NCSD containers |
| `tools/fates/symbols.py` | the game's symbol map -> `config/functions.csv` (names, boundaries, ARM/Thumb) |
| `tools/fates/spotcheck.py`, `flow.py`, `test_symbols.py` | checks the names against the code; the boundary walker; the registry tests |
| `tools/fates/ghidra_import.py`, `tools/export_symbols.py` | symbols for Ghidra and crash lookups (`build/symbols*`) |
| `tools/analysis/funcmap.py` | function starts found by reading the code |
| `tools/build.py`, `gen_asm.py`, `compile.py`, `m1_tests.py`, `diff_func.py` | the code rebuild: asm from code.bin (ARM and Thumb), assemble, link, compare; tests; C++ per function later |
| `tools/progress.py` | function counts per library (the block below) |
| `tools/assets/romfs.py`, `survey.py`, `roundtrip_all.py` | RomFS unpack + manifest, counts, every converter over the whole RomFS |
| `tools/assets/lz.py`, `isbin.py`, `msg.py`, `arc.py`, `ctpk.py`, `bch.py`, `tex3ds.py`, `cgfx.py` | LZ13, IS .bin, message archives, .arc, CTPK, BCH textures, 3DS texture codecs |
| `tools/assets/portrait.py` | a character's portrait layers -> PNG folder and back (`--allow-resize` for other sizes) |
| `tools/assets/bchwrite.py` | the relocating BCH writer: a texture of another size, mip count or format, with the file re-laid out around it; `selftest`, `test` |
| `tools/maps/maps.py` (+ `maplib.py`, `test_maps.py`) | maps: unit placement and terrain of every chapter -> spreadsheets and a preview picture, checked, and back |
| `tools/tables/dump.py`, `build.py`, `check.py`, `gen.py`, `evidence.py`, `test_tables.py` | data tables <-> spreadsheets (CSV), byte-identical rebuild, layout checks, generated docs/structs, code evidence for layouts |
| `tools/castle/castle.py` (+ `sheetlib.py`, `test_castle.py`) | My Castle data (and every other self-describing "sheet" file) <-> spreadsheets, byte-identical rebuild, layout checks, safe row additions |
| `tools/mods/mods.py` (+ `textmod.py`, `mapface.py`, `castlemod.py`, `selftest.py`) | mods: text, whole files, spreadsheets, maps, portraits and castle data; check, build, install into Zakuro, uninstall |
| `tools/readable/check.py`, `stage.py`, `verify.py`, `gen_structs.py`, `xmap.py`, `candidates.py`, `symmap.py`, `gameaddr.py` | the readable layer: lint/compile/host tests, staging for 3dsrecomp (Fates overrides only), tier-2 verify, structs from config, Awakening->Fates function map, candidates |
| `src/readable/battle/tests/stance_diff.py` (+ `arm_mini.py`) | runs the game's own Attack/Guard Stance ARM code (a small ARM interpreter over `extracted/text.bin`) and the readable C on the same made-up inputs and compares |
| `src/readable/battle/tests/triangle_diff.py` | the same comparison for the weapon triangle and weapon ranks; `--plant` also checks that 18 planted bugs are caught |
| `tools/harness/harness.py`, `build.py`, `headless.py`, `recapture.py`, `gen_stubs.py`, `mutate.py` | the test robot: capture library, headless runs, replays, planted bugs |
| `tools/harness/smoke.py` | the smoke set: 6 short headless runs (each route, randomizer off and everything on) and the memory compare ([harness/SMOKE.md](docs/harness/SMOKE.md)) |
| `tools/release/run_tests.py` | the unit tests in 4 lanes: `--core` (the quick set) or `--full` (every test) |
| `tools/extras/usa_extras.py` | screen extras: Fates' own map (config/extras/fe14.json: 60 fps battles, faster battles, 16:9; `verify`, `build`), and Awakening's EUR->USA extras for `--game fe13` |
| `tools/zakuro-options/` | Grok's options page design and patch (not built) |
| `tools/wsl/` | timing trial scripts for a WSL build (scratch only) |
| `tools/m2/`, `tools/make_config.py`, `tools/analysis/splits.py`, `tools/gen_headers.py` | Awakening's RTTI naming passes and class headers: kept for the shared code, they refuse to run or SKIP for Fates |
| `tools/check_all.py` | every check of this repo in one command (below); `--core` is the quick profile |

### Checks

`python tools/check_all.py` runs every gate and prints one table (PASS, FAIL, SKIP with
the reason, KNOWN). `--core` for the release's quick profile (round 67), `--fast` for the quick rows, `--slow` to add the portrait test, the
whole-game BCH resize test, every sheet-shaped file through the castle tool, the long stance,
triangle, vein and formula comparisons, one real three-copy robot run (`parallel-smoke`, needs boot.exe, the capture library and the ROM), the whole-RomFS asset round trip and the three-image ROM tests, `--list` for what each row
needs. Logs go to `build/check_all/`. Rows: the code rebuild (`code-hash`, `lint`,
`m1-tests`, `diff-func`, `gen-headers`), symbols (`symbols`, `symbols-spotcheck`,
`symbols-flow`), tables (`tables-test`, `tables-gen`, `tables-check`, `tables-rebuild`),
assets (`assets-quick`, `assets-bch`, `assets-bchwrite`, `assets-bchwrite-all`, `assets-arc`,
`assets-portrait`, `assets-full`), maps (`maps-test`, `maps-roundtrip`), castle (`castle-test`, `castle-all`), mods and PLAY (`mods-selftest`, `text-mods`, `play-tests`), the engine (`engine-selftest`),
readable code and the robot (`readable`, `harness-selftest`, `markers-selftest`, `harness-levelups`, `cheats-selftest`, `cheat-routes`, `headless-selftest`, `parallel-tests`, `parallel-smoke`, `stance-armmini`, `stance-diff`, `stance-diff-long`, `triangle-diff`, `triangle-diff-long`, `vein-diff`, `vein-diff-long`, `formula-diff`, `formula-diff-long`, `growth-diff`, `growth-diff-long`, `skill-diff`, `skill-diff-long`, `menu-diff`, `menu-diff-long`, `readable-verify`), screen extras (`extras-verify`), the ROM
(`rom-rebuild`, `rom-tests`), and hygiene (`hygiene-paths`, `hygiene-leak`, `py-compile`,
`selftest`, `progress`).

### Docs

| Page | About |
|---|---|
| [Read Me First.txt](Read%20Me%20First.txt) | the player's guide: the two roads, playing, saves, controls, the randomizer, mods |
| [docs/BUILD.md](docs/BUILD.md) | building the game program on your own PC (Road B): every tool, the commands, time and disk |
| [docs/ROADMAP.md](docs/ROADMAP.md) | the plain roadmap from round 69 (2026-11-24) and the owner's calls with their defaults |
| [docs/REVIEW_R59_R68.md](docs/REVIEW_R59_R68.md) | the owner's review page for rounds 59-68 (kept as written) |
| [docs/PORT_PLAN.md](docs/PORT_PLAN.md) | the first plan: steps, weights, finish lines, and a dated status section per round |
| `docs/REPORT_*.md` | one plain-language report per round; the newest is [docs/REPORT_2027-02-01.md](docs/REPORT_2027-02-01.md) (round 84). The file dates are the reports' own numbering, not calendar dates |
| [docs/RANDOMIZER.md](docs/RANDOMIZER.md), [docs/RANDOMIZER_INGAME.md](docs/RANDOMIZER_INGAME.md), `docs/rando/` | the randomizer: rows, rules, the in-game page, per-part designs and checks |
| [docs/DECISIONS.md](docs/DECISIONS.md) | rulings F-001 ... |
| [docs/PLAY.md](docs/PLAY.md) | the PLAY launcher |
| [docs/RELEASE.md](docs/RELEASE.md) | for the project owner: making a release, the screens, undo, pushing |
| [docs/ENGINE.md](docs/ENGINE.md) | Zakuro + 3dsrecomp from source, the patch series, the standalone exe (how it works and what was checked) |
| [docs/SYMBOLS.md](docs/SYMBOLS.md) | the symbol map and the function registry |
| [docs/CODE.md](docs/CODE.md) | the byte-identical code rebuild, Thumb |
| [docs/ROM_REBUILD.md](docs/ROM_REBUILD.md) | the whole-ROM rebuild |
| [docs/ASSETS.md](docs/ASSETS.md) | RomFS formats and converters, BCH, portraits |
| [docs/TABLES.md](docs/TABLES.md) | data tables: layouts, fields, confidence, editing |
| [docs/MAPS.md](docs/MAPS.md) | maps: unit placement, terrain, what can be changed and why |
| [docs/CASTLE.md](docs/CASTLE.md) | My Castle data as spreadsheets: sheets, fields, confidence, which rows may be added |
| [docs/MODDING.md](docs/MODDING.md) | making and installing mods |
| [docs/READABLE.md](docs/READABLE.md) | the readable code layer |
| [docs/STANCES.md](docs/STANCES.md) | Attack and Guard Stance: the rules as the code has them, what is rewritten, what waits |
| [docs/TRIANGLE.md](docs/TRIANGLE.md) | weapon triangle and weapon ranks: the rules as the code has them, the RULES.md check, what is rewritten |
| [docs/VEINS.md](docs/VEINS.md) | dragon veins: the rules as the code has them, what is rewritten |
| [docs/FORMULAS.md](docs/FORMULAS.md) | battle formulas (hit, avoid, critical, attack, follow-up, forecast) from the code, the Ryoma cross-check |
| [docs/HARNESS.md](docs/HARNESS.md) | the test robot's tools |
| [docs/ROBOT.md](docs/ROBOT.md) | what the robot reached on Fates: routes, screens, memory reads, shadow compare |
| [docs/harness/PARALLEL.md](docs/harness/PARALLEL.md) | side-by-side robot runs within the owner's budget |
| [docs/CHEATS.md](docs/CHEATS.md) | the robot's cheat track: pokes into its own test game, labelled and scored apart |
| [docs/MENUS.md](docs/MENUS.md) | the game's own options screen (danger zone, HP bars, battle animations, game speed) from the code |
| `docs/collab/`, `docs/tracks/` | Grok's notes and design tracks (Grok writes these) |
| `scout/SCOUT.md` | the first survey of Fates against the Awakening tools (kept as written) |
| `patches/zakuro/README.md` | why each engine patch is kept |
| `mods/README.md` | the mods folder |

### Progress

Function counts, not a measure of the port (the port is measured in
[PORT_PLAN.md](docs/PORT_PLAN.md) steps). "Matched" means compiled C++ that rebuilds a
function byte for byte; this port does not need it to play or mod.

<!-- progress -->
**Matching progress (game + untagged code): 0 / 17,140 functions, 0 / 3,319,112 bytes (0.00%).** Named functions: 26,118 / 27,078.

| Library | Functions | Bytes | % of .text | Named | Matched (armcc) | Matched (GCC stand-in) |
|---|---:|---:|---:|---:|---:|---:|
| game | 17,094 | 3,310,884 | 62.4% | 17,083 | 0 | 0 |
| nex | 2,170 | 522,224 | 9.8% | 2,168 | 0 | 0 |
| ctr_sdk | 2,541 | 392,170 | 7.4% | 2,479 | 0 | 0 |
| pia | 1,925 | 337,188 | 6.4% | 1,918 | 0 | 0 |
| nw4c | 1,250 | 274,208 | 5.2% | 1,250 | 0 | 0 |
| cxx_runtime | 377 | 172,704 | 3.3% | 377 | 0 | 0 |
| molive | 911 | 153,356 | 2.9% | 156 | 0 | 0 |
| live2d | 383 | 75,460 | 1.4% | 383 | 0 | 0 |
| rvct_clib | 226 | 25,258 | 0.5% | 104 | 0 | 0 |
| zlib | 25 | 22,776 | 0.4% | 25 | 0 | 0 |
| pead | 129 | 14,208 | 0.3% | 129 | 0 | 0 |
| unknown | 46 | 8,228 | 0.2% | 46 | 0 | 0 |
| crt0 | 1 | 36 | 0.0% | 0 | 0 | 0 |
| **total** | 27,078 | 5,308,700 | 100% | 26,118 | 0 | 0 |

_Generated by `python tools/progress.py --readme`._
<!-- /progress -->

## Credits and licence

Zakuro is by fearkov (MIT) and is built from source with our patches (patches/zakuro). 3dsrecomp,
also by fearkov, has no licence file: it is not included, and the build fetches it unmodified at a pin for your own
build (CREDITS.md). The game is by Nintendo and Intelligent
Systems; no game file is included or shared.

Seal of Flames by Laz14 (https://gamebanana.com/mods/656034, CC BY-NC-ND 4.0) is a separate fan mod. The mod is never included.

Licence: the project's own work is under a scoped MIT licence (see `LICENSE`); it claims no
rights over the game, the fan mod above or other third-party work.
