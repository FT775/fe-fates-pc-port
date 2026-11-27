# Engine: Zakuro + 3dsrecomp from source, for Fire Emblem Fates

Status 2026-11-26 (round 85: sections 1, 4, 5 and 9 brought up to date; first written 2026-11-10). If you only want
to build the program on your own PC, read [BUILD.md](BUILD.md) first: it lists every tool and the commands in order.
How the engine sources are fetched, patched and built, and how the
standalone program `play/game/Fire Emblem Fates.exe` is made. The chain is the Fire Emblem
Awakening port's (its `docs/ENGINE.md` has the long story of each step); this page says what
is the same, what changed for Fates, and what was checked. Tags: **[high]** checked by a
script or read in source, **[med]** good evidence, **[low]** a guess.

## 1. State

| Part | State |
|---|---|
| `tools/engine/engine.py` (fetch, apply, build, port, status, selftest) | **Fates-ready**: every per-game value comes from `config/game.json`; `selftest` **24/24** [high] |
| Pins in `config/upstream.json` | the Awakening port's pins: Zakuro `c856685` (v0.2.32), 3dsrecomp `df82e6e`, fe-awakening-recomp `832fe86` (reference only); Zakuro's local branch is now `fe14` |
| `engine.py fetch` | **done**: all three cloned at the pins, clean [high] |
| `engine.py apply` | **done**: 43 patches (0001-0043, `ls patches/zakuro/*.patch`); a rerun says "unchanged"; `status` exit 0 [high] |
| 3dsrecomp's bundled hints for this dump | **present**: `engine/3dsrecomp/hints.txt` has the section `= 0004000000179800 9677F5445E8DCD01` with 94 addresses [high] |
| Code hash of the owner's dump | FNV-1a of `.text` (`extracted/text.bin`, 0x51011C bytes) = `9677F5445E8DCD01`, the hash 3dsrecomp keys the section by (`src/build.rs code_hash`) [high, computed here] |
| `engine.py port --dry-run` | **passes** (section 5) [high] |
| `cargo build` of Zakuro / 3dsrecomp, `engine.py port` (real) | **built**: first 2026-11-10, rebuilt in many rounds since, each with the owner's OK (F-004). The program installed on the owner's PC was built 2026-11-26 (round 83) from the pin + 43 patches: sha256 `3a471269...`, 145 MB, work folder `build/port/fef` 4.98 GB (counted, `play/game/build-record.json`) [high] |

## 2. What is per game, and where it comes from

`tools/engine/engine.py` imports `GAME` from `tools/gamecfg.py` (which reads
`config/game.json`). Nothing in it names a game any more:

| engine.py name | game.json key | Fates value |
|---|---|---|
| `TITLE_ID`, `TITLE_HEX` | `title_id` | `0004000000179800` |
| `GAME_NAME`, `EDITION` | `game`, `edition` | Fire Emblem Fates, Special Edition (USA) |
| `PROGRAM_NAME` | `port.program_name` | `Fire Emblem Fates` (exe name = window title, patch 0005) |
| `PACKAGE` | `port.package` | `fe-fates` (Cargo's name; no spaces allowed) |
| `PORT_DIR` | `port.port_dir` | `build/port/fef` |
| env names | `port.env_prefix` | `FEF_ENGINE_DIR`, `FEF_PORT_DIR`, `FEF_GAME_DIR` (override the folders; tests only) |
| `rom_path()` | `default_rom` | `--rom`, else `play/config.json`'s `"rom"` when that file is there, else the `.cci` in `roms/` (`tools/paths.py`; one release: the repo root) |
| ROM checks | `product_code`, `rom_sha256` | `CTR-P-BFZE`, `a89be7a4...f449` |
| `HINTS_SECTION` | `title_id`, `code_fnv1a` | `= 0004000000179800 9677F5445E8DCD01` |
| git identity for `git am` | `key` | `fe14 engine.py <engine@localhost>` |
| `hints_file()` | `title_id` | `%APPDATA%\3dsrecomp\0004000000179800.hints` (read, stat only) |

The branch name lives in `config/upstream.json` (`repos.zakuro.branch` = `fe14`); the
selftest uses the same name.

## 3. Commands

```
python tools/engine/engine.py fetch       # clone missing repos at the pins, check the rest
python tools/engine/engine.py apply       # branch fe14 = Zakuro pin + patches/zakuro (idempotent)
python tools/engine/engine.py status      # exit 1 when a repo is off its pin or unpatched
python tools/engine/engine.py selftest    # apply logic on a throwaway repo + port helpers
python tools/engine/engine.py port --dry-run   # every check and the plan; builds nothing
# need the owner's OK (they compile code):
python tools/engine/engine.py build [zakuro|3dsrecomp|3dsrecomp-verify]
python tools/engine/engine.py port        # -> play/game/Fire Emblem Fates.exe
```

The safety behaviour is unchanged from Awakening: `fetch` checks each `origin` URL and
moves a clean off-pin checkout back; 3dsrecomp must stay exactly at its pin with a clean
tree (it has no licence: built unmodified, never copied into tracked files, never shared);
`apply` compares by `git patch-id --verbatim`, refuses to drop uncommitted edits without
`--force`, and leaves the branch at the pin when a patch fails; `build` refuses unless every
source is at its pin and Zakuro carries exactly the series; `RUSTUP_TOOLCHAIN` and
`cargo --locked` pin the toolchain and crates; nothing writes to `%APPDATA%` or
`%LOCALAPPDATA%`.

## 4. The patch series for Fates

Today the series has **43 patches** (0001-0043). 0001-0005 are the Awakening port's (below, as checked on
2026-11-10). 0006-0043 are ours, for Fates: the first-run 60 fps / 16:9 defaults (0006), the randomizer laid in
memory and its in-game page, saves, Nuzlocke, recolours, the full character swap, presets and the share code
(0007-0036, with 0041 for Classic New Games), the growth view (0028, 0033), the Helpers heading with True hit and New
Game defaults (0037-0040), and the shared code for the second edition (0012, 0013, 0027, 0042, 0043). One line per
patch, with its edition: [patches/zakuro/README.md](../patches/zakuro/README.md).

On 2026-11-10 all five patches were kept, **byte-identical** to the Awakening port's files. The reasoning
(read from the patch text and the patched source) is in
[patches/zakuro/README.md](../patches/zakuro/README.md); in short:

- **0001, 0002, 0005 are game-agnostic.** 0001 only watches for markers a game's table
  names; 0002 adds two layouts only the extras pick; 0005 names the standalone program's
  window after its exe and starts the ROM in `game-path.txt`. [high]
- **0003 and 0004 are Awakening's top-screen extras, and inert for Fates.** Everything goes
  through `game_ui::is_awakening(id)` / `game_ui::for_game(id)`, which match only
  `000400000009F100` and `00040000000A0500`. For Fates `system.game_ui` is `None`, so
  `follows_cursor()` and with it the frontend's `extras_active()` are false; the settings
  block is not drawn; the sound lookup finds no entry. The only visible change is two extra
  bindings in the general Controls list. [high, read in source]
- Kept rather than dropped: one patched Zakuro for both ports, and Fates' own extras later
  slot into the same `for_game` list. Dropping them was tried and works (0001 + 0002 + 0005
  apply cleanly on the pin, scratch clone).

Fates' own top-screen extras (its UI marker tables, bottom-screen sounds from
`sound/IRON15_sound.bcsar`) are new research and are **not** in the series.

## 5. `port --dry-run` output (2026-11-10, kept for the record)

This is the first sample, from when the series had 5 patches. Today the Zakuro line says `+43 commits`; the other
lines have the same shape. The C compiler and archiver lines show what this PC used: on yours they name your own Zig
or clang and `llvm-ar` or MSYS2 `ar` ([BUILD.md](BUILD.md)).

```
zakuro: on the pin c856685 (+5 commits)
3dsrecomp: at the pin df82e6e, clean
game:       Fire Emblem Fates Special Edition (USA), title 0004000000179800, CTR-P-BFZE
ROM:        <repo>\Fire Emblem Fates - Special Edition (USA).cci
ROM SHA-256 a89be7a4cb6a471bcfeac4feca55eeec68937d90d7fed18b1cf967399363f449 (hashed now): the known clean dump
hints:      3dsrecomp's own: section '= 0004000000179800 9677F5445E8DCD01' in hints.txt (94 entries)
            Zakuro's: %APPDATA%\3dsrecomp\0004000000179800.hints (present)
C compiler: CC=%LOCALAPPDATA%\zakuro\tools\zig-0.17.0\zig.exe cc -target x86_64-windows-msvc
archiver:   AR=C:\msys64\ucrt64\bin\ar.exe
3dsrecomp:  engine\target\3dsrecomp\release\3dsrecomp.exe (will be built first)
Zakuro:     engine\zakuro\crates\zakuro (pin c856685 + 5 patches)
readable:   left out (default for this game; --readable stages them)
project:    <repo>\build\port\fef
program:    <repo>\play\game\Fire Emblem Fates.exe
[dry run] nothing built
```

## 6. What `port` does differently for Fates

1. **ROM checks**: the NCSD media id, and now also the game partition's NCCH program id and
   product code (`CTR-P-BFZE`), then the **SHA-256** of the whole file against
   `config/game.json`. PLAY's cached hash (`play/state.json`, read only) is used when it is
   for the very same file (path, size, mtime); otherwise the file is hashed (2 GiB, a few
   seconds). A different hash stops `port`: an update or a patched dump has other code, so
   3dsrecomp's bundled hints (keyed by the code hash) and the project's addresses would not
   fit. `--any-dump` overrides it on purpose. Tested with a synthetic header (refused, then
   accepted with `--any-dump`).
2. **Hints**: `port` reports whether 3dsrecomp's own `hints.txt` has this dump's section
   (it does: 94 addresses) and whether Zakuro's per-title hints file exists. Neither is
   required: 3dsrecomp reads both by itself (`src/build.rs bundled` and `hints`).
3. **Readable overrides are opt-in** (`--readable`; `--no-readable` is still accepted and is
   the default). Since the 2026-11-10 integration `tools/readable/stage.py` stages only
   `src/readable/` and refuses any override that is not a Fates function start with a
   row in `config/readable/functions.csv`. Those few overrides are still unverified
   (no 3dsrecomp verify run yet), so they stay out of the played build by default.
4. The generated project must call `zakuro::run(Some(...))` and name `0x0004000000179800`:
   3dsrecomp writes `0x{program_id:016X}` into `src/main.rs` (`src/port.rs` line 112), which
   is what `project_problems` looks for [high].

Everything else (C compiler choice, `Cargo.toml` fix, Zakuro's release profile and
`Cargo.lock`, `--help` check, `build-record.json`) is unchanged.

## 7. Selftest (24 checks)

10 apply checks on a throwaway repo (fresh apply, no-op rerun, shorter series, whitespace-
only edit, dirty tree refused, `--force`, broken patch leaves the pin, empty series), 9 port
helpers (manifest fix with spaces and parentheses, profile copy, lock drift, `--help` text,
project checks with the Fates title id), and 5 new ones: the ROM check takes
`0004000000179800` / `CTR-P-BFZE` and refuses another media id, program id, product code or a
cut-short file; the ROM hash uses PLAY's cache only for the same file (a temporary
state.json, never the real one); the hash without a cache is the file's SHA-256; the bundled
hints section is found and counted; a hints file without this game's section gives none.

## 8. Rules

- Zakuro (MIT): our changes only as `patches/zakuro/` files, credit to fe-awakening-recomp
  (MIT) where adapted ([NOTICE.md](../patches/zakuro/NOTICE.md)).
- 3dsrecomp (no licence): unmodified, at its pin, personal builds only, never tracked.
- Nothing game-derived in tracked files: `engine/`, `build/port/fef/` and `play/game/` are
  gitignored. The program holds the game's code: never share it.
- `engine.py` never writes `%APPDATA%` / `%LOCALAPPDATA%`; it only stats Zakuro's hints file.

## 9. Open points

- **Built** (see section 1). A first build on a new PC has never been timed: 30-60 minutes is an **estimate**
  (1.5x Awakening's times, since Fates' `.text` is 1.5x larger); on the owner's PC with warm caches the whole build
  step took about 10 minutes (counted, round 71). Disk: `build/port/fef` 4.98 GB (counted, section 1).
- **Never tried on a clean PC.** [BUILD.md](BUILD.md) lists every tool the build needs; the list comes from the code
  and this PC, not from a trial on a fresh Windows.
- Fates uses services Awakening never touched (act, nfc for amiibo, qtm on New 3DS). Zakuro
  lists Fates SE USA as Playable + Recompiled, so they are at least stubbed [med].
- `tools/readable/stage.py` stages only Fates overrides now (2026-11-10 integration);
  `--readable` is useful once those overrides pass a 3dsrecomp verify run.
- `.gitattributes` now marks `*.patch -text` and `*.bat eol=crlf` (2026-11-10), so the
  patches stay byte-exact and the batch files CRLF.
