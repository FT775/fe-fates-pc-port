# PLAY: the launcher for Fire Emblem Fates

Status 2026-11-26 (round 85: the second edition's pointers cut to one line, section 1 brought up to date; round 84: that edition's parts moved to its own page; first written 2026-11-10). `PLAY.bat` (in the repo root) runs `tools/play/play.py`, which checks
everything and then starts Fire Emblem Fates (Special Edition, USA) straight into the game:
in the standalone program `play/game/Fire Emblem Fates.exe` when it has been built
([ENGINE.md](ENGINE.md)), else in the installed Zakuro. It is the Fire Emblem Awakening
port's launcher with every per-game value taken from `config/game.json`. The plain-language
guide for the owner is `Read Me First.txt`.

The second edition's own PLAY steps, its save and its tests are in `docs/seal/PLAY_SEAL.md` (in that edition only).

## 1. State

| Part | State |
|---|---|
| `tools/play/play.py` | Fates-ready; constants from `config/game.json` [high] |
| `tests/test_play.py` | 59 tests (`python -m unittest tests.test_play`), all in temporary folders; part of the CORE test set [high] |
| `PLAY.bat --dry-run` on this PC | **passes** (2026-11-25): ROM hash matches, the standalone program found, command printed (section 4) [high] |
| `PLAY.bat --make-shortcut --dry-run` | would create `Desktop\PLAY Fire Emblem Fates.lnk` -> `PLAY.bat`; nothing made [high] |
| Standalone program | **built and installed** on the project's PC: `play/game/Fire Emblem Fates.exe` (first built 2026-11-10; the installed one is round 83's, sha256 `3a471269...`, 43 Zakuro patches, `play/game/build-record.json`); PLAY starts it, with Zakuro as the fallback when it is missing or `"standalone": false`. How to build it on another PC: [BUILD.md](BUILD.md) |
| Exe check (round 68) | PLAY stops when the program's sha256 differs from `build-record.json` (an install cut short or a hand copy); `--anyway` starts it once anyway. It matches today. Waiting for the owner's ok (docs/REVIEW_R59_R68.md) |
| `--capture` | code kept from Awakening. The robot now has a Fates capture library (`build/harness/lib`, rebuilt 2026-11-24, sha256 `405f2bac...`), but PLAY's own `--capture` path has not been re-tested against it [med] |

## 2. What is per game

| play.py name | game.json key | Fates value |
|---|---|---|
| `TITLE_ID` / `TITLE_HEX` | `title_id` | `0004000000179800` |
| `PRODUCT_CODE` | `product_code` | `CTR-P-BFZE` |
| `ROM_SIZE` | `rom_size` | 2,147,483,648 (named in the hash-mismatch message when the size differs) |
| `ROM_SHA256` | `rom_sha256` | `a89be7a4cb6a471bcfeac4feca55eeec68937d90d7fed18b1cf967399363f449` |
| `GAME`, `EDITION` | `game`, `edition` | Fire Emblem Fates, Special Edition (USA) |
| `SHORTCUT_NAME` | `port.shortcut_name` | `PLAY Fire Emblem Fates.lnk` |
| `STANDALONE_NAME` | `port.standalone_name` | `Fire Emblem Fates.exe` |
| default `"rom"` | (none) | empty: the `.cci` in `roms/`, found by `tools/paths.py` (title checked; one release: `default_rom` in the repo root, with a move note). A `"rom"` that is no longer there falls back to `roms/`; `play/config.json` is never rewritten (F-048) |
| `EXTDATA_FALLBACK` | `extdata_id` | `0x1794`, used only when the ROM's exheader cannot be read (the exheader is read first: offset 0x230, also `0x1794` on the owner's dump) |
| env names | `port.env_prefix` | `FEF_PLAY_DIR`, `FEF_HARNESS_DIR`, `FEF_ASSUME_NOT_RUNNING` (tests) |

## 3. Checks before starting

1. **Program**: `play/game/Fire Emblem Fates.exe` if built and `"standalone"` is not false
   (its sha256 must equal `build-record.json`'s, round 68; `--anyway` gets past a mismatch),
   else `zakuro.exe` in `"zakuro_dir"` (default empty since F-048: no machine-specific path; the owner's
   existing `play/config.json` keeps its own folder).
2. **ROM header**: NCSD media id and NCCH program id `0004000000179800`, product code
   `CTR-P-BFZE`, decrypted (NoCrypto). Anything else stops with what to do.
3. **ROM SHA-256** (`"check_rom": "full"`, the default): hashed once, cached in
   `play/state.json` until the file changes. A different hash is a STOP (a patched, trimmed
   or differently dumped copy has other code: the recompiled code, the bundled hints and
   the project's mods are made for the clean dump). `--anyway` starts it once anyway;
   `"check_rom": "header"` skips the hash.
4. **.cia files beside the ROM**: Zakuro loads an update or DLC from the ROM's folder.
   PLAY reads each `.cia`'s title id from its TMD: an **update** (`0004000E00179800`) or
   anything unreadable or for another title is a STOP (an update changes the code); this
   game's **DLC** (`0004008C00179800`) is only a note. New for Fates; the capture session
   already refused every `.cia`.
5. **Recompiled code** (Zakuro only): `%APPDATA%\3dsrecomp\0004000000179800.dll` must exist
   (it does on this PC, built 2026-11-09), unless the game's settings turn it off.
6. **Save place**: if the save is only in the other place (portable vs `%APPDATA%`), STOP.
7. **Already running**: `zakuro.exe` or `Fire Emblem Fates.exe` in the task list: STOP.

Then, unless `--dry-run` / `--check`: zip the save into `play/backups/auto-*.zip` when it
changed (keeps 20), and start the program detached.

## 4. `PLAY.bat --dry-run` on this PC (2026-11-25)

`python tools/play/play.py --dry-run` (what `PLAY.bat --dry-run` runs), round 73b, private folders shortened to
`<repo>`:

```
ROM: SHA-256 matches the known clean Fire Emblem Fates dump.
Program: Fire Emblem Fates.exe (standalone, recompiled code built in, made 2026-11-24 15:39).
[dry run] would back up the save to play\backups (if it changed since the last backup)
[dry run] would run, from the program's folder:
  cd /d "<repo>\play\game"
  "<repo>\play\game\Fire Emblem Fates.exe" "<repo>\roms\Fire Emblem Fates - Special Edition (USA).cci"
```

(Read only: `play/config.json` and `play/state.json` already existed and kept their modification times; by the code,
nothing in `%APPDATA%` is written. The 2026-11-10
sample this replaces was from before the standalone program: it started Zakuro with the `%APPDATA%\3dsrecomp` DLL.)

## 5. Where the save is

Zakuro (and the standalone program, which is Zakuro with the code linked in) keeps Fates'
save in `%APPDATA%\zakuro\user`:

- `savedata\0004000000179800\` and `savedata\0004000000179800.format`
- `extdata\0000000000001794\` and `extdata\0000000000001794.format` (Zakuro names extdata
  folders by the 16-digit id: `host_archive.rs`)

Backups (`--backup`, automatic before each start, `--migrate-saves`) zip exactly these, with
paths relative to `user\`. A backup zip is accepted for a capture session only when every
member is this game's savedata or its own extdata id.

## 6. Tests

`tests/test_play.py` (59 tests; Windows-only ones: the shortcut dry run and `PLAY.bat` exit
codes). Everything runs in temporary folders: a fake `APPDATA`, a fake Zakuro folder with an
empty `zakuro.exe` that is never started, a synthetic cartridge header and synthetic `.cia`
heads (identifiers only). No ROM, no Zakuro, no network, and never the real saves. The
expected values come from `config/game.json` (with literal checks that they are the Fates
ones). Fates-specific tests: constants from game.json, the first-run ROM is the repo-root
dump, the extdata fallback, update vs DLC `.cia`, the CIA title id reader for all six
signature types, the trimmed-size note. The capture and recapture tests (from Awakening)
also pass with the Fates title id; they exercise `tools/harness/recapture.py` with fakes.

## 6c. Choose your game (round 53)

Since round 83 (patch 0043) the **Choose your game** page and Esc > **Switch game** show only in the second edition;
Fire Emblem Fates starts at once.

## 6d. Randomized games

The main way is the **Randomizer page inside the program** (Zakuro patches 0007-0030): New Game, pick the difficulty
and Casual / Classic, and the page opens; Esc > Randomizer shows the run later. Off = the original game. PLAY.bat
needs nothing extra for it (the page calls `tools/randomizer/rando.py` through a hidden Python). `PLAY RANDOMIZED.bat`
(`tools/play/rando.py`) is the older way: one profile per seed in `play/randomizer/<seed>/` with its own saves and
mods ([RANDOMIZER_PAGE.md](RANDOMIZER_PAGE.md)). Details: [RANDOMIZER_INGAME.md](RANDOMIZER_INGAME.md).

**Classic works (round 81b, patch 0041, F-067).** Before round 81b
a New Game on Normal + Classic did not start the randomizer or the Nuzlocke run. Now Classic, Casual and Phoenix all
do (on Hard the game offers Casual
and Classic; both work); the randomizer gives the same game for a seed as before. If the port ever cannot see your New Game, it shows one line on screen: "This New Game
did not use your seed." That game is then the plain game, not randomized. A second line, "Classic New Games cannot
start the randomizer in this setup; pick Casual or Phoenix.", means Classic cannot be seen in this setup. Neither line
was seen in the rounds' robot runs (only in the tests). Details: RANDOMIZER_INGAME.md sections 16.1 and 16.2.

## 6e. First start: the Getting ready window (round 77)

Plan: [LAUNCHER_PLAN.md](LAUNCHER_PLAN.md) (parts L1-L4). Code: `tools/play/launcher.py`, called by `play.py`
`run_launcher`. Python standard library only; no engine build.

**When it shows.** Only when `PLAY.bat` started PLAY (it sets `FEF_LAUNCHER=1`) and something is missing or wrong,
or always with `PLAY.bat --setup`. A plain `python tools/play/play.py` never shows it, and neither do `--anyway`,
`--check`, `--backup` and `--migrate-saves`. When nothing is missing it prints nothing, so a folder that already
works (yours) starts exactly as before (test T8: the `--dry-run` output is byte for byte the same). A fault inside
the launcher prints one note and PLAY goes on as before.

**The rows.** Your copy of the game (the `.cci`), the game program, the Randomizer (optional). Keys are typed, then
Enter:

- Game file: **1** looks in `roms\`, Downloads, Desktop and Documents, at most 3 folders deep and 30 seconds (the
  cap is checked between entries, so one slow header read can go a little past it); it reads names and sizes only (links and junctions skipped) and reads the first 512 header bytes only of files whose
  size is exactly `rom_size`. **2** opens the Windows file window through PowerShell (`-STA`, on top; without
  PowerShell it falls back to typing). **3** takes a typed or dragged path (quotes, `& '...'` and `file:///` are
  removed, and a `file:///` address's percent escapes such as `%20` are decoded). The file then goes through the same checks as
  `check_rom` (title, edition, decrypted, size, SHA-256, no update `.cia` beside it). A wrong file gets one sentence
  and nothing is written; an accepted one is cached in `play\state.json` under `check_rom`'s own key.
- Program: never built here. **Z** points to a Zakuro folder (type, drag, or 2 for the file window). **Y** runs
  `engine.py port --dry-run` once (it builds nothing).
- Randomizer: **R** runs `tools/assets/romfs.py` once (about 1.8 GB into `extracted\`), after a free-space check.
- Ready: Enter goes on; **Q** quits with exit 1 and starts nothing.

**What it keeps.** `play\launcher.json` (git-ignored, never in a package): `rom`, `seal_zip` and `seal_skipped` (second edition
only), `randomizer_prepared`, `zakuro_dir`. Reading order for the game file: `config.json`
`"rom"` first, then `launcher.json`, then `roms\`; for Zakuro, `config.json` `"zakuro_dir"` then `launcher.json`.
`play\config.json` is never written with a path (F-048). Delete
`launcher.json` to be asked again.

**The portable folder.** On the first start of a freshly unzipped folder (`play\` holds none of PLAY's own files:
`config.json`, `state.json`, `launcher.json`, `backups`, `data`, `seal-of-flames`, `randomizer`, `appdata`,
`localappdata`), PLAY makes `play\appdata`. That folder is the marker: from then on the standalone program gets
`APPDATA`, `LOCALAPPDATA`, `TEMP` and `TMP` inside `play\` (`--dry-run` prints them), so its settings and saves stay
in the download folder. Zakuro itself keeps its own places (its recompiled code lives in the real
`%APPDATA%\3dsrecomp`). When the portable save is empty and a save exists in the normal place, PLAY prints one note
naming `PLAY.bat --migrate-saves to-portable`, then `PLAY.bat --portable on`; nothing is copied. A folder PLAY used
before (yours) keeps today's places. Deleting `play\appdata` turns the redirect off.

**Wording.** Every line the window prints is in `WORDS` in `launcher.py`; round 77 worded them with Grok
([collab/LAUNCHER_WORDS_GROK.md](collab/LAUNCHER_WORDS_GROK.md)).

**Tests.** `tests/test_launcher.py` (T1-T13 plus T6b and T9b), all in temporary folders under `build/`: a fake
AppData, LocalAppData and home, synthetic cartridge headers, a stand-in for the Windows file window
(T10 only builds the PowerShell command and never runs it) and a recording stand-in for every program start. No
window opens, no game, Zakuro or build starts, no network, never the real `play\` or game file. T8 is the quick guard in
`tests/core.txt` (track `launcher`).

## 6f. Helpers in the Esc window (rounds 80 and 81)

Esc, on the Fire Emblem Fates game, has a **Helpers** heading (Zakuro patch 0037):

- **True hit: Off / On** (Off by default). On, the battle forecast also shows the real chance to hit, such as
  70 (real 79) (patch 0038): on the simple forecast above each side's Hit box; on the detail page (the game's
  default) beside the right side's number only, since the left side's number has no free room. A label shows only
  for a shown 51-99: at 50 or less the game's number is already the real one. The number comes from the game's own
  curve (build/r80/hit/true_hit_table.json, checked against the game 101/101). It only paints the program's copy of
  the screen and never changes a roll. The fight scene does not show it.
- **Faster enemy turns:** a help line, not a setting. Since round 81 it points at the Enemy turn skip row under New
  Game defaults and, in a game already going, at the game's own Options line 6 (Off, Movement, or All) and the Start
  key during the enemy turn. Units, HP and hits stay the same, but later enemy moves can differ, as when
  you take more or less time on your turn (round 80 E1). The port's own 2x / 4x speed was cut in round 80 (F-065).

A click saves into Zakuro's own settings.toml under `[fates_helpers]` (`true_hit = true`; `enemy_phase` is kept but
nothing reads it). With no table, or True hit Off, the program is memory-identical to round 74's (proof D1) and nothing
is written. The rows cannot be drawn headless: press Esc once and look.

**New Game defaults (round 81, patches 0039 and 0040, F-066).** Under True hit and its help line there is a line
**New Game defaults**, closed at first ("New Game defaults: game's choice", or for example "2 set"). Open, it has four
rows, each starting on **Game's choice**:

- **Battle animations:** Game's choice / Off / On (Off plays fights on the map; supports and dances follow it too).
- **Map speed:** Game's choice / Normal / Fast / Manual (Manual: units go fast while you hold the A Button; the
  game starts at Manual).
- **Enemy turn skip:** Game's choice / Off / Movement / All (the game's own Options line 6).
- **HP bars:** Game's choice / Off / On.

They are used once, when you start a New Game (right after Casual, Classic or Phoenix): the game's own Options
screen then shows your choices at the Prologue. A game already going, Continue, a battle save, a chapter retry and
your old saves are never changed; change those on the game's own Options screen. A row saves into settings.toml under
`[fates_helpers]` (`battle_animations`, `map_speed`, `enemy_skip`, `hp_bars`) only when it is not Game's choice. With
every row at Game's choice the program is memory-identical to round 80's (proof P1) and watches nothing. One choice
for both editions. Options that change timing can make later enemy moves differ; hits, damage
and the battle dice stay the same. The rows cannot be drawn headless: press Esc once and look (your ok list).

## 7. Open points

- PLAY's `--capture` path (from Awakening) has not been re-tested against the Fates capture library.
- The round-68 exe check waits for the owner's ok.
- Older notes kept for the record: the Fates top-screen extras became built-in enhancements in patch 0006 (60 fps
  battles and the 16:9 top screen on a first run, docs/DEFAULTS_60FPS_3X.md); the Awakening-only "Top-screen extras"
  block still does not show for Fates (see [ENGINE.md](ENGINE.md) section 4).
