# The built-in launcher: a "get ready" step before the game (desk plan for round 77)

Written 2026-11-25 as a desk plan, while round 74 ran in the main folder. Nothing was built, nothing was started
and no tool or test was changed. It is your own idea: "a launcher that's built in to launch before it plays so
you can route/find the roms". It is proposed for **round 77**, the release round ([ROADMAP.md](ROADMAP.md) row 77).
Sources read: `PLAY.bat`, `tools/play/play.py`, `tools/play/sof.py`, `tools/paths.py`, `tools/assets/romfs.py`,
`config/game.json`, [PLAY.md](PLAY.md), [DOWNLOAD_PLAN.md](DOWNLOAD_PLAN.md), [RELEASE.md](RELEASE.md),
`tools/release/package.py`, [GAME_PICKER.md](GAME_PICKER.md), [ROUND74_PLAN.md](ROUND74_PLAN.md) (the shape of
the time box) and DECISIONS F-048 (the download folder layout).

## In plain words

**What it is.** When someone downloads the port and double-clicks `PLAY.bat`, the launcher makes sure their own
game file is found and is the right one before the game starts. If the file is missing or wrong, the launcher
helps them find it or point to it. It does the same for the Seal of Flames zip, if they have one. Once
everything checks out, it starts the game as PLAY does today.

**What a stranger sees, step by step** (the first time, in a freshly unzipped folder):

1. They double-click **`PLAY.bat`**. A window opens with the title **Getting ready**, and a short list:
   ```
   Getting ready (Fire Emblem Fates PC port)
     [ ] Your game file (Fire Emblem Fates Special Edition, USA, .cci)   not found yet
     [-] Seal of Flames by Laz14 (optional)                               not found (that is fine)
     [ ] The game program                                                 not checked yet
   ```
2. Under the list it offers three ways to find the game file:
   - **1 Look for it.** It looks in `roms\`, Downloads, Desktop and Documents, down to 3 folders deep, for at
     most 30 seconds. It reads only file names and sizes. It opens a file only when the file has the exact
     size of the real game (2,147,483,648 bytes), and then only its first header bytes.
   - **2 Choose the file.** The normal Windows "Open" window appears, so they can click their way to the file.
   - **3 Type or drag the path.** They can drag the file from Explorer onto the window and press Enter.
3. The file is checked: right game, right edition, not encrypted, not an update, and then its **fingerprint**
   (SHA-256). That takes about 10 seconds once, and the result is remembered until the file changes.
   - If the check passes, the list shows `[x]`.
   - If it fails, one plain sentence says why and what to do. For example: "This is an update file, not the
     game" or "This is the right game, but not the clean dump: its fingerprint differs." Nothing is saved.
4. **Seal of Flames (optional):** "Seal of Flames by Laz14 is a fan mod, not part of this port. It is optional.
   Press S to skip, or P to point to the zip you downloaded." It prints the address where they can get the mod
   themselves (gamebanana.com/mods/656034) and never downloads anything. A zip they point to is checked by
   fingerprint, size, file count and the fingerprint of its code file. Then the existing installer
   (`sof.py`) installs it into their own `play\seal-of-flames\` profile.
5. **The game program:**
   - If `play\game\Fire Emblem Fates.exe` is there, its fingerprint is checked against its build record (as today).
   - If it is not there, the launcher says in plain words what is missing and the one step that makes it
     (section 5). It never builds by itself.
6. **The Randomizer, once:** the Randomizer page needs a readable copy of the game's files on their PC
   (`extracted\romfs`, about 1.8 GB). The launcher offers: "Press R to prepare the Randomizer once (it reads
   your game file and writes about 1.8 GB into the extracted folder here)." It runs the existing
   `tools/assets/romfs.py`.
7. When every row is `[x]` (or Seal of Flames is skipped), it shows **Ready. Press Enter to play.** Then PLAY does
   what it does today: it backs up the save, starts the program, and the window opens on **Choose your game**.

**The second time** nothing has changed, so the launcher shows nothing and PLAY goes straight into the game, as it
does for you today. `PLAY.bat --setup` opens the Getting ready window again at any time, for example to point to
a moved file.

**On your PC** nothing changes: your folder already has `play\config.json`, your game file passes, and your
program is built, so the launcher stays silent. Your save places stay where they are.

**Does it need an engine build?** **No.** It is Python inside `tools/play/` plus PLAY.bat, which it already uses.
The game program is not changed, so no engine OK is needed for it.

**How long:** counted **3 h 45** (all estimates, written on the slow side), with a hard stop at 5 h 40. It is
added to round 77's 6 h 15, so round 77 becomes **10 h 00**. If that runs long, things are cut in the order of
section 9. With all three cuts it is **2 h 40** (round 77: 8 h 55).

## 1. What is checked (fingerprints only)

| File | Checks | Where the expected values live |
|---|---|---|
| Your game file (.cci) | header: title id `0004000000179800`, product code `CTR-P-BFZE`, decrypted; size 2,147,483,648; SHA-256 `a89be7a4...f449`; no update `.cia` beside it | `config/game.json` (`title_id`, `product_code`, `rom_size`, `rom_sha256`), read by `tools/gamecfg.py`. Already used by `play.py` and `paths.py` |
| Seal of Flames zip (optional) | size 162,497,619; SHA-256 `56b4afab...`; 979 files; every entry is `romfs/**` or the one `code.ips`; SHA-256 of `code.ips` `82e4a0e9...` | `tools/play/sof.py` `EXPECTED` (facts only, version v6). Already used by `sof.py check_zip` |
| The built program | SHA-256 of `play\game\Fire Emblem Fates.exe` equals its `build-record.json` | `play\game\build-record.json`, made on your PC. Already checked by `play.py` (round 68) |

**What the port never does, launcher included:**

- It never ships, uploads, prints or copies a byte of the game or of Seal of Flames. The launcher **reads** a file
  to fingerprint it. It **remembers the path**; it does not copy or move the file. No new fingerprint is added
  anywhere: it uses the ones above.
- Two steps that already exist work on the player's own copy, on the player's own PC, as they do for you today:
  - the Seal of Flames install (`sof.py`) unpacks the player's zip into their `play\seal-of-flames\`, unchanged;
  - the Randomizer preparation (`romfs.py`) writes `extracted\romfs`.

  Both places are git-ignored (`/play/`, `extracted/`) and the release gates keep them out of every package.
  The launcher only starts these steps, and only when the player presses the key.

## 2. Where its settings are kept

- **Inside the folder.** Everything the launcher learns goes into **`play\launcher.json`**: the game file's path,
  the Seal zip's path if it is not in `roms\seal\`, "Seal skipped", and "Randomizer prepared". The fingerprint
  result stays in `play\state.json` (as today). `play\` is git-ignored, so a path with the player's user name
  never reaches git or a package.
- **`play\config.json` is not rewritten** (F-048 says it holds no machine-specific path by default, and `play.py`
  never writes a found path into it). `play.py` reads `launcher.json` as one more place: first the `"rom"` you
  set in `config.json` by hand, then `launcher.json`, then `roms\`.
- **Never the real APPDATA.** The launcher itself writes only inside `play\`. For a **freshly unzipped folder**
  (no `play\config.json` before the first PLAY), PLAY starts the program with `APPDATA`, `LOCALAPPDATA` and
  `TEMP` pointed at `play\appdata`, `play\localappdata` and `play\temp`. That is the portable folder from
  DOWNLOAD_PLAN 3.3 (your call (c) there, default yes). So the stranger's Zakuro settings, saves and caches stay
  in the download folder, and deleting the folder removes everything. It is the same method Seal of Flames used
  in round 52 (`sof.py profile_env`) and the robot's sandbox uses.
- **A folder that already has `play\config.json` keeps today's places** (yours does: your save stays in
  `%APPDATA%\zakuro`). The launcher never moves a save. If the portable folder is empty but a save exists in the
  normal place, PLAY prints one note naming `PLAY.bat --migrate-saves` and copies nothing. That command already
  exists.

## 3. What already exists, and what is new

| Already there (reused, not rewritten) | New for the launcher |
|---|---|
| `paths.find_rom`: the `.cci` in `roms\`, one file only; title check; update files refused with one sentence | `tools/play/launcher.py`: the Getting ready window, its three ways to find the file, and the Seal and Randomizer rows |
| `play.py check_rom`: header, SHA-256, the cache in `play\state.json`, the trimmed-size note | **Look for it**: the folder search with its 3-level and 30-second caps; names and sizes only, header only for files of the right size |
| `play.py classify_cias`: update vs DLC `.cia` beside the file | **Choose the file**: the Windows Open window, opened through PowerShell (built into Windows 10 and 11). Python's own window kit (Tk) is not used, because the bundled Python of the download plan has none |
| `paths.find_seal_zip` (any depth in `roms\seal\`), `sof.check_zip`, `sof.install`, the Choose your game page and `play\game-choice.txt` (patches 0011 and 0012) | Dragged paths: quotes and spaces removed |
| The exe check against `build-record.json` (round 68) | `play\launcher.json`, read by `play.py effective_rom` and `sof.py default_zip` (a few lines each) |
| `romfs.py`: writes `extracted\romfs` from the `.cci` | `PLAY.bat --setup`; the launcher stays silent when nothing is missing |
| The profile environment redirect (`sof.py profile_env`, round 52) | The portable folder for fresh folders only (section 2) |
| PLAY.bat's "Python 3 was not found" message | A first-start section in `Read Me First.txt` and [PLAY.md](PLAY.md) section 6e |
| The release package gates: no game bytes, no `.exe` / `.dll`, privacy scan, credits | `tests/test_launcher.py` (section 6) |

`PLAY.bat` itself barely changes. `play.py` calls the launcher when something is missing, so a double-click on the
same file does it all. No new `.bat` file is added.

## 4. The engine question: no build

Everything above is Python (standard library only) and the PowerShell file window. Neither the game program nor
the boot-server nor the capture library changes, so round 77's engine build stays exactly what RELEASE WITH ENGINE
BUILD would build anyway. Considered and **not proposed**:

- A Getting ready page inside the game window, like Choose your game, would need a patch and an engine build. It
  would also be useless in the case that matters most: when the program is not built yet.
- **Port mode** (DOWNLOAD_PLAN 3.1) is an engine patch, but it belongs to the ready-made download. That download
  waits for the 3dsrecomp author's OK. The launcher works with or without it.

## 5. The game program: what the launcher says when it is missing

Until 3dsrecomp's author says yes, the release has **no program in it** (ROADMAP call 3: source-only). So on a
stranger's PC the program row can be missing, and the launcher explains what to do, in this order:

1. **Zakuro is installed and has recompiled the game:** the launcher asks for the folder that holds `zakuro.exe`
   (the same three ways as for the game file). The path goes into `launcher.json`, and PLAY starts Zakuro as today.
2. **The player wants the one-game program:** the launcher prints the one command that makes it,
   `python tools\engine\engine.py port`. That takes about 30-60 minutes the first time (a rough guess in Read Me
   First, never measured on a fresh PC). It asks once: "Check what it needs now? (Y/N)". A yes runs
   `engine.py port --dry-run`, which only checks and builds nothing. The launcher **never starts a build**.
3. **Later, with the author's OK and port mode:** the download holds a program with no game code in it. The
   launcher shows "The first start turns your game into PC code once (about 8 minutes, estimate). Zakuro asks
   before it downloads its compiler (Zig, 100 MB)." Zakuro's own Recompile does the work (DOWNLOAD_PLAN 3.1).

## 6. Tests

All of them run in temporary folders: synthetic cartridge headers (identifiers only), synthetic Seal zips through
the existing `FEF_SOF_EXPECT` test hook, and a fake `APPDATA` / `LOCALAPPDATA`. They never use the real game file,
never open a window (the file window is replaced by a stand-in), never start a game, and never use the network.
`tests/test_launcher.py` joins the CORE set. `test_play` takes 8.68 s today (measured, `test_times.json`), and the
new file should be about as fast.

| # | Test | Passes when |
|---|---|---|
| T1 | File already in `roms\` | no questions; the start command is printed (`--dry-run`); `launcher.json` not written |
| T2 | No file, typed path | the path is accepted, `launcher.json` holds it, and the next `play.py --dry-run` uses it |
| T3 | Dragged path with quotes, spaces and non-English letters | the same file is found |
| T4 | Wrong files: update `.cia`, other title, encrypted, trimmed size, changed fingerprint, a folder, a missing file | the right one-sentence answer for each; nothing written |
| T5 | Look for it, in a fake Downloads with decoys | finds only the right file; never opens a file of the wrong size; stops at 3 levels and at the time cap (fake clock) |
| T6 | Seal zip: right, wrong fingerprint, outside `roms\seal\`, skipped | right is installed through `sof.install`; wrong is refused and not remembered; outside is remembered; skipped is never asked again until `--setup` |
| T7 | Writes only inside `play\` | every file of the fake `APPDATA` / `LOCALAPPDATA` keeps its name, size, time and fingerprint; nothing new outside `play\` (and `build\` caches) |
| T8 | A folder like yours (`play\config.json` exists, everything passes) | no window, no portable redirect, `config.json` byte for byte unchanged (F-048) |
| T9 | Fresh folder | the program's environment points `APPDATA`, `LOCALAPPDATA` and `TEMP` inside `play\`; the note about a save in the normal place appears, and nothing is copied |
| T10 | The Windows file window | the PowerShell command is built right; without PowerShell, it falls back to typing |
| T11 | Missing program | the Zakuro-folder question; `engine.py port --dry-run` only on Y (a fake runner is called, nothing is built) |
| T12 | `PLAY.bat` exit codes (Windows only, `PLAY_NO_PAUSE`) | 0 when ready, 1 when the player quits the Getting ready window |
| T13 | Release package | the package zip holds no `play\` file and no `launcher.json` (the existing archive gate, plus one assertion) |

`test_play` (59 tests) and `test_sof_path` (20 tests) must still pass unchanged. That shows PLAY behaves the same
for a folder that needs no launcher.

**Your look (once, after the round):** delete nothing. Rename your `roms\` game file for a minute, double-click
`PLAY.bat`, try "Choose the file", then rename the file back. It is a console window plus the normal Windows Open
window, so the robot cannot take a picture of it for you (its hidden-desktop picture failed in round 72), as with the page in rounds 71-72.

## 7. The parts, counted (round 77, before the release build)

"Counted" = a time measured before (the round is named). "Estimate" = never measured, written on the slow side.
Every part has a cap of its count plus half, rounded up to 5 min. For a sense of scale (not used in the count):
round 73b's similar `play.py` change (`--backup-seal` with 4 tests) fit into a 22-minute fixes part, and round 71
wrote code at about 23% of its count.

| # | Part | Time | Cap | Kind | Files |
|---|---|---|---|---|---|
| L1 | **The Getting ready window:** the game file, Seal and program rows; the Randomizer offer; the Ready screen; silent when nothing is missing | 1 h 00 | 1 h 30 | estimate | new `tools/play/launcher.py` |
| L2 | **Finding the file:** Look for it (caps), the Windows Open window through PowerShell, dragged paths | 30 min | 45 min | estimate | `launcher.py` |
| L3 | **Hooks:** `launcher.json` in `play.py effective_rom` and `sof.py default_zip`; `--setup`; the portable folder for fresh folders and its one note | 30 min | 45 min | estimate | `play.py`, `sof.py` |
| L4 | **Tests** T1-T13; `test_play` and `test_sof_path` unchanged | 45 min | 1 h 10 | estimate | new `tests/test_launcher.py` |
| L5 | **Words:** Read Me First's first-start section, PLAY.md 6e, one line on round 77's "how to start" page | 20 min | 30 min | estimate | docs |
| L6 | **Grok:** the wording of the window's lines (joins the round's existing Grok consult on the "how to start" page) | 10 min | 15 min | estimate | docs/collab |
| G | **Gate:** `run_tests.py --core` and seed fingerprints (no seed changes: the launcher does not touch the randomizer) | 5 min | 10 min | counted (round 71: 158 s + 24 s) | none |
| L7 | **A dry try on the real package:** unzip the round's release zip into `build\r77\launcher-try\`, then run `PLAY.bat --setup --dry-run` there with typed answers and a fake APPDATA. No game start | 15 min | 25 min | estimate | none |
| L8 | **Report lines** and the undo step (`git revert` of one commit; nothing installed) | 10 min | 15 min | estimate | report |

60 + 30 + 30 + 45 + 20 + 10 + 5 + 15 + 10 = **225 min = 3 h 45**.

### Totals

| | Time |
|---|---|
| **Launcher, counted** | **3 h 45** |
| Hard stop (1.5 times the count) | 5 h 40 |
| Round 77 as on the roadmap (release with engine build, download package if allowed, how-to-start page) | 6 h 15 |
| **Round 77 with the launcher** | **10 h 00** |
| With all three cuts of section 9 | 2 h 40 (round 77: 8 h 55) |

Round 77 then goes over 8 h. As with round 74, you are asked once at the round ("Yes, start round 77", or start
with the cuts).

**Where it sits in round 77:** the launcher is done and passes its gate **before** RELEASE WITH ENGINE BUILD runs.
The release's own core step then tests it again, and the package holds it. If the launcher is not done when its
hard stop comes, it is left out of the release commit, and the release goes ahead without it. PLAY's existing
messages ("put your .cci in the roms folder") stay.

**Disk:** about 30 MB for the dry try (estimate: r68's package zip is 6.4 MB, measured; it holds the tracked files only). The Randomizer preparation is
the player's own 1.8 GB, on their PC, only when they press R. No D: stop is needed for this part.

## 8. Your calls (silence = the default)

| # | Call | Default |
|---|---|---|
| 1 | Where the chosen paths are kept | **`play\launcher.json`**, so `play\config.json` stays as F-048 says. (Other answer: write them into `config.json`'s `"rom"`.) |
| 2 | "Look for it" outside the port folder | **Yes, only when the player presses 1**: `roms\`, Downloads, Desktop, Documents; 3 levels; 30 s; names and sizes, headers only of files with the right size. (Other answer: no search; only the file window and typing.) |
| 3 | When the window shows | **Only when something is missing or wrong**, plus `PLAY.bat --setup`. Your PLAY stays silent. (Other answer: a short status screen with Enter every time.) |
| 4 | The portable folder for a freshly unzipped folder | **Yes** (DOWNLOAD_PLAN call (c)); folders that already have `play\config.json` keep today's places. |
| 5 | The Seal of Flames address | **Printed only.** The launcher never opens a browser or downloads. (Other answer: open the page in the browser when the player presses L.) |
| 6 | The kind of window | **The console window PLAY already opens**, plus the Windows Open window. Not a Tk window (the bundled Python has no Tk) and not a page inside the game (that needs an engine build). |
| 7 | The Randomizer preparation | **Offered on a key press**, with the size said first. (Other answer: done by itself on the first start.) |
| 8 | Missing program | **Explain and offer only `engine.py port --dry-run`**. Never start a build. |

## 9. Cut order (if round 77 runs past its count)

1. **Look for it** (the search: 15 min of L2 and 5 min of L4). The file window and typing stay.
2. **Seal zip outside `roms\seal\`** (10 min of L1, 5 of L3, 5 of L4). The Seal row still finds the zip in
   `roms\seal\` and offers the skip.
3. **The portable folder for fresh folders** (15 min of L3, 5 of L4, 5 of L5). It moves to the ready-made
   download (port mode), where it matters most.

The three cuts save 65 min (20 + 20 + 25), which leaves **2 h 40**. The last resort is to leave the launcher out of the release
(section 7).

## 10. Not in this plan (on purpose)

- No download of anything (the game, the mod, Python, Zig). The launcher never contacts the internet.
- No build started by the launcher; no change to the game program, the boot-server or the capture library.
- No change to your saves, your Zakuro settings, `%APPDATA%` or `%LOCALAPPDATA%`.
- No Citra / Azahar save import (roadmap call 4: not built).
- The ready-made download (a program in the zip) stays blocked by the licence stops below. The launcher does
  not depend on it.

## 11. Round 77 release checklist (the public repository)

Ticked in the round's report. Only you push (`python tools/release/release.py push rNN` for the private
repository; the public snapshot is made the same way as r68).

- [ ] **Public repo = one clean snapshot only.** `fe-fates-pc-port` gets one new commit, made from
      `build/release/rNN/package/FE-Fates-port-rNN.zip`, in its own fresh `git init` under `build/publish/rNN`.
      It never gets the private history (`fe-fates-pc-port-dev` keeps that, as `origin`). The git bundle never
      goes up.
- [ ] **No `.exe` or `.dll`, ever.** The package's gates say "no program file". Before the upload, `git ls-files`
      in the snapshot shows no `.exe`, `.dll`, `.cci`, `.3ds`, `.cia` or `.zip`. The GitHub release assets
      are only the zip, `SHA256SUMS.txt` and `RELEASE_NOTES.md`. That holds even if the ready-made download
      is ever allowed: then it needs its own call and its own gates (DOWNLOAD_PLAN 6), not this checklist.
- [ ] **Author = FT775's GitHub noreply address** (`…+FT775@users.noreply.github.com`, as for r68). Never the local
      repository's own author e-mail. The privacy scan (`privacy-head`, `privacy-history`) passes, and
      `play\launcher.json` (which holds a path with a user name) is not in the zip.
- [ ] **The licence stops hold:**
  - **3dsrecomp has no licence file:** no program that contains it is shipped; the release stays source-only
    until its author says OK (ROADMAP call 3).
  - **Symphonia is MPL-2.0:** a stop until you say "MPL is fine" (DOWNLOAD_PLAN call (b)). It matters only for
    a shipped program.
  - **The 19 crates.io packages without a licence file inside:** your call D4, still open.
  - **The portable-folder default** (section 2, DOWNLOAD_PLAN call (c)) is what the stranger gets.
  - **Python embeddable:** downloaded only after your OK in this round, and shipped with its own `LICENSE.txt`.
  - **Zig:** not bundled.
- [ ] **Seal of Flames is never shipped and always credited:** Laz14, gamebanana.com/mods/656034, CC BY-NC-ND 4.0,
      in `CREDITS.md`, the release notes and the launcher's Seal row. The `seal-ids` and `credits` gates pass.
- [ ] **No Nintendo bytes:** the `leak` and `same-file` gates pass. The launcher adds only identifiers that are
      already tracked (title id, sizes, SHA-256).
- [ ] **No push by Claude.** No push by any round or workflow (`release.py push` refuses inside an agent session).

## Round 77 result (2026-11-25)

**Built, nothing cut.** Parts L1-L6 were done in round 77's desk part (about 14:40 to 15:20 by the clock, against
a count of 3 h 05 for L1-L6 and G; no engine, Zakuro, boot-server, capture-library or cargo build; no game start).
All three section-9 items stayed: Look for it, the Seal zip outside `roms\seal\`, and the portable folder. L7 (the
dry try on the real release zip) and L8 (report lines) belong to the release run after the commit.

- **The window** is the new `tools/play/launcher.py`. Its rows are the game file, Seal of Flames by Laz14
  (optional), the game program and the Randomizer (optional), followed by the Ready screen (Enter goes on, Q starts
  nothing). It shows only when PLAY.bat started PLAY (PLAY.bat now sets `FEF_LAUNCHER=1`) and something is missing
  or wrong, or with `PLAY.bat --setup`. A plain `python tools/play/play.py` never shows it, so every older caller
  behaves as before.
- **Finding the file.** Key 1 looks in `roms\`, Downloads, Desktop and Documents, at most 3 folders deep and
  30 s. It reads names and sizes only, skips links and junctions, and reads 512 header bytes only of files of
  exactly `rom_size`. Key 2 opens the Windows file window through PowerShell, and falls back to typing when there
  is no PowerShell. Key 3 takes a typed or dragged path: quotes, `& '...'` and `file:///` are removed, and after
  the review a `file:///` address's `%20`-style escapes are decoded. Every wrong file gets one plain sentence, and
  nothing is written for it.
- **Kept where.** `play\launcher.json` holds `rom`, `seal_zip`, `seal_skipped`, `randomizer_prepared` and
  `zakuro_dir`. It is git-ignored and never packaged. `play\config.json` is never written (call 1). The reading
  order is config.json first, then launcher.json, then `roms\`.
- **Seal and the program.** The Seal row goes through `sof.check_zip` / `sof.install`, and the address is printed
  only. The program row never builds: Z points to Zakuro, and Y runs `engine.py port --dry-run` once.
- **The portable folder.** On the first start of a freshly unzipped folder (none of PLAY's own files in `play\`),
  PLAY makes `play\appdata`. That folder is the marker. From then on the standalone program gets APPDATA,
  LOCALAPPDATA, TEMP and TMP inside `play\`. Zakuro keeps its own places, because its recompiled DLL lives in the
  real `%APPDATA%\3dsrecomp`. When a Zakuro save exists in the normal place, PLAY prints one note naming
  `--migrate-saves to-portable`, and nothing is copied.
- **Words.** Every window line is in launcher.py's `WORDS`, reworded with Grok
  ([collab/LAUNCHER_WORDS_GROK.md](collab/LAUNCHER_WORDS_GROK.md)). The window's own names for two things changed
  from this plan's: key 1 is shown as "Look in the usual folders" (this plan says "Look for it"), and the Open
  window is shown as "the Windows file window". Read Me First has a new "First start: the Getting ready window"
  section, and [PLAY.md](PLAY.md) has a new section 6e.
- **Tests.** `tests/test_launcher.py` holds T1-T13 plus T6b and T9b, 15 tests in all. The run_tests `--core` set
  runs every non-heavy module, and T8 is also a quick guard in `tests/core.txt`. `test_play` and `test_sof_path`
  are unchanged and pass. No test opens a window: T10 builds the PowerShell command and hands it to a fake runner.
  No test starts the game or a build, uses the network, or writes into the real `play\` or AppData.
- **Integrate's review fixes.** The `%20` decoding above. Look for it now checks the time cap while it reads a
  folder too, not only between entries; one slow header read can still go a little past 30 s.
- **The review's six findings (fixed, 8 tests in `ReviewFixTests`).** A right game that is not usable as is
  (changed fingerprint, trimmed, update .cia beside it) no longer opens the window: PLAY.bat prints the old STOP
  with its way out (clean dump, `"check_rom": "header"`, or `--anyway`), and the window prints the same way out
  when it shows anyway. `engine.py port` reads `launcher.json` "rom" after config.json, PLAY RANDOMIZED gets the
  portable places, Look for it skips every reparse point and cloud placeholder, and the Seal row's dry run
  unpacks nothing.
- **Known, not fixed.** When `py -3` cannot start Python, PLAY.bat still exits 0. This was already so before round
  77; T12 keeps the real LOCALAPPDATA for that reason. **Your own look** (section 6): rename the `roms\` file for a
  minute, double-click PLAY.bat, try key 2 (the Windows file window), then rename the file back. The robot cannot
  picture that window or how the rows line up on a real screen.
