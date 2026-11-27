# Seal of Flames: could our port load it? (study, round 44)

**In plain words.** Probably yes, with no code change. The port runs on Zakuro. Zakuro already reads a
mod folder laid out the way Citra's is: `mods\0004000000179800\romfs\...` in its data folder. Seal of
Flames ships exactly that kind of folder and no code patch. Our robot has already loaded our own mods
this way in its own test game (the look sitting, docs/LOOK_ROBOT.md). So the likely way to use it is:
you download it yourself and drop its `0004000000179800` folder into Zakuro's `mods` folder. Nothing of
the mod would ever go into our repository or into anything we share. Before you do that, the robot can
try it in its own test copy and tell you what it found. That means booting it, making the Chapter 5
choice, playing Chapter 6, and running a 0-bad compare with our readable code on. Three things are not
proven yet. (1) The mod's file names must match our copy's: our game files end in `.bin.lz`, and the
mod page lists `.bin`. (2) Our own mods must stay off while it is in, because both replace the same
files. (3) Its "mid-battle saves don't load" problem most likely comes from the game's own code running
on the mod's data, not from the emulator. If so, our port would have the same problem. This is a
reasoned guess, not tested. The robot can test it once the mod is in its test copy. Nothing was
downloaded, installed or changed for this study.

Credit: **Seal of Flames by Laz14, https://gamebanana.com/mods/656034, CC BY-NC-ND 4.0**

Status: study only (2026-11-19, about 25 of the 45 counted minutes). Sources: our own code and docs,
plus the facts from the mod's page that the round brief gave (read 2026-11-19). I did not open the
mod's files and have not seen them. Nothing counts as done until the owner says ok (F-037).

## What the mod page says (from the round brief)

- Needs Fire Emblem Fates Special Edition (USA), title `0004000000179800`. Our copy is exactly that edition
  (config/game.json: `edition` "Special Edition (USA)", `title_id` "0004000000179800", product code
  CTR-P-BFZE).
- Made for Citra. It is installed as a LayeredFS folder, `0004000000179800/romfs/...`, and replaces
  `GameData/GameData.bin`, `GameData/Dispos/*`, `GameData/Person/*`, `GameData/Terrain/*`, the
  `m/@E/*.bin` message files, `map/config/*.bin`, `castle/castle_building.bin`, `face/FaceData.bin` and
  `talk/RelianceTalkBGM.bin`. No exefs or code patch is listed.
- Known issues: mid-battle saves (bookmarks) don't load, so use save states instead. A Private Quarters
  invite may crash the game. The accessory shop list is broken.
- It starts at Chapter 6, after you pick "Refuse to choose a side" in Chapter 5.
- Licence CC BY-NC-ND 4.0. The page allows download and install. It says to ask before you
  redistribute it, modify it or use parts of it. Commercial use is not allowed.

## 1. How our build reads game files, and where a user would put the folder

- **Zakuro reads mod folders the Citra and Luma3DS way.** `engine/zakuro/crates/zakuro-core/src/mods.rs`
  says "mods, kept in the data directory's mods folder under the title's id, laid out the way Luma3DS
  and Citra take them". `dir()` picks `<data>\mods\<title id as 16 hex digits>`, in upper case. Lower case
  is used only when the lower-case folder alone exists. Our title id is all digits, so case does not
  matter. `lay()` lays that folder over the game's RomFS (and over an update's, if one is present). It
  logs one line: "mods from ...: N files replaced, N added, N patched, N removed".
- **How the layering works** (`engine/zakuro/crates/zakuro-fs/src/layered.rs`): files in `romfs/` replace
  the game file at the same path. Names are matched exactly first, then ignoring case. A file with no
  match is added as a new file. Files in `romfs_ext/` are `.ips`/`.bps` patches or `.stub` removals.
  The bytes go to the game as they are, with no decompressing or converting. A `code.bin`, `code.ips` or
  `code.bps` (in the folder or in `exefs/`) would change the code and then need a new recompile. The
  mod page lists none, so none is expected. Step 2 below checks this.
- **Where the owner's game reads it.** PLAY.bat starts Zakuro, because the standalone exe is not built
  (docs/PLAY.md). `play/config.json` has portable saves off, so the folder is
  `%APPDATA%\zakuro\mods\0004000000179800\` ("Read Me First.txt", "Where mods go"). With portable saves
  on, it would be `play\data\mods\0004000000179800\`. The standalone exe, once built, is Zakuro with the
  code linked in and uses the same folders (docs/PLAY.md). Today that folder holds two empty
  subfolders, `romfs\` and `textures\`, both dated 2026-11-09. I only listed it and wrote nothing there.
  So no mod of ours is installed now.
- **What a user would do.** Take the mod's top folder `0004000000179800` and put it into
  `%APPDATA%\zakuro\mods\`. Its `romfs\...` then lands in `%APPDATA%\zakuro\mods\0004000000179800\romfs\`.
  This is the same step as Citra's `load\mods\`, with only the parent folder different. Doing this in
  the owner's folder is **the owner's decision** (F-037: anything that changes the owner's own setup).
  We never write to `%APPDATA%`.
- **The robot's own copy.** Every robot run boots with `ZAKURO_DATA` pointing at its own folder under
  `build/` (`tools/harness/headless.py` `boot_env`). `build/look_robot/drive.py` copies a mod folder into
  `<run data>/mods/` before boot. Round 41 showed this works: with a look mod in, the memory hash
  changed, and with the folder emptied it went back to the unmodded hash (docs/LOOK_ROBOT.md O1). The
  same was seen for tables in memory (docs/LOOK_STEP4.md "The test robot"). So the robot test needs no
  new mechanism. The mod goes into `build/sof/data/mods/0004000000179800/romfs/` (or a run's own data
  folder), never anywhere else.
- **Our tools' install target** (`tools/mods/mods.py install`) is that same Zakuro folder. It takes
  `--zakuro-dir`, and the robot always points it below `build/`. Section 3 explains why it must not
  run while Seal of Flames is in.

**Open point A: file names.** Our dump's files are LZ-compressed with `.lz` names:
`GameData/GameData.bin.lz`, `GameData/Person|Dispos|Terrain/*.bin.lz`, all 1,239 files in `m/@E/` are
`.bin.lz`, `castle/castle_building.bin.lz` and `face/FaceData.bin.lz`. Only `map/config/*.bin` (118
files) and `talk/RelianceTalkBGM.bin` are plain `.bin`. If the mod really ships `GameData.bin`
without `.lz`, Zakuro would add it as a new file and not replace anything. Whether the game then reads
it, I don't know (not read in the code). Maybe the page just shortened the names. The first robot step
(step 2) settles it by listing the names. After the install, Zakuro's log line ("N replaced, N added")
shows it again.

## 2. Can our tools read each replaced file kind (for a read-only report)?

Every file kind the mod replaces is one our tools already read, and on our unedited dump they write it
back byte for byte. So the robot could compare the mod's files with our dump and write a plain report:
which characters, classes, items, maps and texts changed. It would ship nothing and keep the mod's
words and numbers out of git (the report would live under `build/`).

| Replaced file | Our reader / builder | Byte-identical round trip on our dump | Source |
|---|---|---|---|
| `GameData/GameData.bin(.lz)` (Person, Job, Item, Skill ... tables) | `tools/tables` (`dump.py`, `build.py`, layouts in `config/tables/`) | yes: all 412 table files | docs/TABLES.md lines 24, 327, 360 |
| `GameData/Person/{,A,B,C}/*.bin.lz` (per-chapter characters) | `tools/tables` (PersonChapter layout, 1,622 records in 117 files) | yes (part of the 412) | docs/TABLES.md lines 419, 566 |
| `GameData/Dispos/*.bin.lz` (unit placement) | `tools/maps` (`maps.py`, `maplib.py`) | yes: all 185 placement files | docs/MAPS.md lines 10-11, 238 |
| `GameData/Terrain/*.bin.lz` (tile grid and tile types) | `tools/maps` | yes: all 109 terrain files | docs/MAPS.md lines 10-11, 238 |
| `m/@E/*.bin(.lz)` (English messages) | `tools/mods/textmod.py` | yes: all 1,328 archives (every place) | docs/MODDING.md section 4 |
| `map/config/*.bin` (per-map settings) | `tools/castle/castle.py` (generic IS .bin sheet reader) | round trip OK, but no layout is registered, so it shows raw fields with no names | docs/CASTLE.md line 146 |
| `castle/castle_building.bin.lz` | `tools/castle` (registered, `KID_` building rows) | yes | docs/CASTLE.md lines 150, 165, 179 |
| `face/FaceData.bin.lz` (portrait records) | `tools/assets/portrait.py` (452 records of 0x48 bytes) | read and written by the portrait tool (docs/LOOK_PORTRAIT.md) | docs/ASSETS.md lines 388-409 |
| `talk/RelianceTalkBGM.bin` | `tools/castle/castle.py` (generic) | round trip OK, not registered (raw fields) | docs/CASTLE.md line 147 |

Limits, said plainly:
- Our layouts were made from **our** files. If the mod adds rows (new characters, chapters, items),
  the readers should still read them: table files are counted blocks, and `mods.py` itself adds rows
  at the end. But a new kind of block we never saw would stop the reader with an error instead of a
  silent wrong answer. The report would list any file our readers refuse.
- Two kinds (`map/config`, `RelianceTalkBGM`) can only be shown as numbers with no names.
- Making a report means writing a small script. This round allowed no code changes, so it is a
  step in the plan below.

## 3. Clashes with our own mods, and how to keep ours off

- **The same files.** Our demo and look mods replace `GameData/GameData.bin.lz` (tables),
  `m/@E/GameData.bin.lz` (names), `GameData/Dispos/A001.bin.lz`/`A007` (maps), `face/...` (portraits)
  and castle files. Seal of Flames replaces all of those kinds. Zakuro takes **one** mod folder per
  game, so whichever file is there last wins, whole.
- **Why ours must not go on top.** `mods.py` always builds from the **base** game (`extracted/romfs/`),
  not from what is already installed. If someone ran `mods.py install` while Seal of Flames is in, the
  tool would move the mod's files at those paths aside (into `fe14pcport-backup\`, and back on
  `uninstall`; docs/MODDING.md section 7). It would then put our files, built from the base game, in
  their place. The result is a broken mix: our base-game `GameData.bin` next to the mod's chapters
  and people. Nothing would be lost, but the game would not be right.
- **How to keep ours off.** (a) Don't run `mods.py install` (or `look_*.py install`) without
  `--zakuro-dir` while Seal of Flames is in. `mods.py status` shows "installed: nothing by this tool"
  when ours are out. (b) For the robot, only one of the two goes into a test copy at a time.
  (c) The screen extras (60 fps, faster battles, wide picture) are cheat-file code patches, not RomFS
  files. The mod has no code patch, so the code addresses they patch are the same, and they could in
  principle run beside it (not tested). The same goes for our readable code layer: it swaps game
  functions by code address, not by data.
- **Combining them (for example our names on top of the mod's text)** would mean building changed
  versions of the mod's files. The page says to **ask the author** before modifying it or using parts
  of it (ND). So we don't do that unless Laz14 says yes, and then only privately, never shipped.

## 4. The "mid-battle saves don't load" problem: could our save path explain or avoid it?

From code reading only. Nothing here was tested.
- Our port runs the game's **own** save code: the recompiled `GameBackup::Serialize` and friends. A
  battle save is backup type 4, `Map0.bak`, and a chapter save is type 3, `Chapter0`
  (docs/OPTIONS_WIRING.md, rounds 35-40). The file layer under it is Zakuro's `HostArchive`
  (`engine/zakuro/crates/zakuro-core/src/services/host_archive.rs`). It keeps each save archive as a
  plain folder (`<data>\user\savedata\0004000000179800\`) and stores the bytes the game writes, without
  reading or changing them. Citra does the same job in its own high-level way. So the save files'
  contents come from the game's code and the mod's data in both emulators.
- On the unmodded game, the robot has written and reloaded battle saves and chapter saves many times
  (for example `opt-t5-chain2-*`: a battle save then a chapter save, every save file byte-identical
  across runs). So our save path itself is not known to break battle saves.
- **So my best guess [medium, reasoning only]:** the problem is in what the game does when it reloads a
  battle save with the mod's data (for example, a battle save that points at chapter or unit data the
  mod laid out differently). It is not in the emulator. If that is right, our port would show the
  **same** problem, and the fix would be in the mod's data or in game code, not in Zakuro. I found
  nothing that would make our port avoid it.
- **What we can offer instead.** Zakuro has save states (`%APPDATA%\zakuro\states\0004000000179800\`,
  "Read Me First.txt"), which is the workaround the mod page itself suggests. The robot can also
  **test** the problem: make a battle save in the mod's Chapter 6, reload it, and record exactly where
  it fails (step 8). That gives evidence instead of a guess. It could later help the author, but only
  if the owner wants to pass it on. We contact no one.

## 5. Step list, with counted sizes

Each size is counted from a past job of the same kind. The rule is no new play without the owner's
OK, and step 6 is new play.

| # | Step | Who | Size | Counted from |
|---|---|---|---|---|
| 1 | Download Seal of Flames yourself from its GameBanana page and unpack it into a folder **outside** the repository (for example `D:\Downloads\SealOfFlames\`). Tell Claude the folder. | owner | 5-10 min | one download and unzip |
| 2 | Read-only check of the download: list every file with its size and hash, check the names against our dump (`.bin` vs `.bin.lz`, open point A), confirm there is no `code.*`/`exheader.bin`/`exefs`, read its licence file. Nothing is copied into the repo. | robot | 10 min | listing 1,700-ish files |
| 3 | Compatibility report (read-only, under `build/sof/`): run each file through our readers (section 2) and list what differs from our dump, and any file a reader refuses. Needs one small new script (owner's OK as usual for code). | robot | 45-60 min (script 30, run and report 15-30) | LOOK_STEP4's `check`, maps/text round-trip tools |
| 4 | Install into the **robot's own** test data copy: copy the mod's `0004000000179800` folder to `build/sof/data/mods/` (as `drive.py` does). Never the owner's `%APPDATA%`. | robot | 5 min | drive.py |
| 5 | Boot and the Chapter 5 choice: boot-server on a copy of `bt-ch5-clear` (the save before the route choice), replay `rv-ch6`'s presses up to the choice ("neither kingdom" + Yes, frames 11725-12039). Check Zakuro's "N replaced" log line, the mod's tables in memory (LOOK_STEP4 method), and screenshots. One unknown: whether a save made before the mod was installed loads cleanly with the mod in. The page implies yes, since it starts after the Chapter 5 choice. | robot | 20 min | LOOK_ROBOT runs, rv-ch6 is 27,740 frames |
| 6 | Chapter 6 played: the mod changes Chapter 6's map and people, so `rv-ch6`'s battle presses won't fit after the choice. This needs **new real play** (a new route, say `sof-ch6`, recorded by the robot, no pokes, never from a cheat save). **Needs the owner's OK.** | robot | 60-90 min | ROBOT.md chapter wall times 50-74 min |
| 7 | Compare with readable overrides on: replay `sof-ch6` twice (determinism), then in capture/shadow mode with every readable override on. Pass = **0 mismatches of any kind**, the save at the end identical between modes. It is also a new kind of input for our readable code. | robot | 30-40 min | round 40 shadow runs |
| 8 | The known issue, tested: in `sof-ch6`, a battle save (map Save, `Map0.bak`), quit, reload. Record pass/fail and where it stops. Also try a save state. | robot | 15-20 min | opt-t5-chain2 |
| 9 | Credit and summary: the credit line (below) in CREDITS.md and in any doc that mentions it; a short pass/fail summary for the owner (F-037). | robot | 10 min | |
| 10 | Owner review of the summary; then **your decision** whether to put the mod into your own Zakuro folder (one folder copy, section 1), with our mods kept out (section 3). | owner | 15 min, plus 2 min to copy | OWNER_REVIEW sittings |

Totals (counted from the table): robot about **3 h 15 to 4 h 15** (steps 2-9: 195-255 min). Owner about **22-27 min** (steps 1 and 10). Steps 2-5
and 9 need no new play. Step 3 needs one new script, and step 6 needs your OK for new real play.

**Credit line (for CREDITS.md, a new row under "Facts and documentation" or a new "Mods we tested with"
table):** Seal of Flames by Laz14, https://gamebanana.com/mods/656034, CC BY-NC-ND 4.0. Tested with the
port in the robot's own copy; not shipped, not changed, download it from its page. (Not added to
CREDITS.md this round. It belongs there once we actually test with it, per the owner's rule in CREDITS.md.)

## What we will never do

Download the mod for the owner, put any of its files (or any game file) in git or in anything we share,
change it or merge it with ours without the author's yes, contact anyone, write to `%APPDATA%`, or use it
commercially.
