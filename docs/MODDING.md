# Modding Fire Emblem Fates

Status: 2026-11-11. Tool: `tools/mods/mods.py` (Python 3.13, standard library only).
Game: Fire Emblem Fates, Special Edition (USA), title `0004000000179800` (all three
routes on one card). Plays in Zakuro (the same build the Awakening port uses).

**In plain words.** A mod is a folder with your changes in it. There are six kinds of
change, and one mod can hold any mix of them:

- **Text** (works today): names, descriptions and conversations. The game keeps its words
  in "message archives"; the tool turns one into a plain text file with a label and one
  line of text per message. Change the words, keep the labels.
- **Whole files** (works today): drop a replacement game file (for example a picture
  rebuilt by `tools/assets`) into the mod's `romfs/` folder at the same path the game uses.
- **Spreadsheets** (works as far as the table layouts go): the game's rules, one row per
  character, class, item or skill. You change cells in Excel or LibreOffice, and you can
  add new items and classes as new rows at the end.
- **Maps** (built and checked; not seen in the game yet): where each unit stands, its
  class, level, items and skills, and the tiles of the map, as spreadsheets plus a picture
  of the map (section 6a).
- **Portraits** (built and checked; not seen in the game yet): every face picture of a
  character as PNG files you can paint over (section 6b).
- **Castle data** (built and checked; not seen in the game yet): dining-hall dishes and
  cooking titles, the accessory shop, class showcases and other My Castle sheets, as
  spreadsheets (section 6c).

Then you run one command. The tool checks everything, builds new game files that hold
only your changes, and copies them into Zakuro's mod folder for Fates. Start the game in
Zakuro and the change is there. One more command takes it all out again.

## 1. Quick start

You need your own game unpacked once (`extracted/romfs/` filled by
`python tools/extract_rom.py` or `python tools/assets/romfs.py`; both read the `.cci` in `roms/`). Then,
from the repository folder:

```bash
python tools/mods/mods.py example-text       # makes mods/ExampleText (Ryoma's name -> "Ryouma")
python tools/mods/mods.py install            # checks, builds, copies into Zakuro
#   start (or restart) Fire Emblem Fates in Zakuro
python tools/mods/mods.py uninstall          # back to the original game
```

`install` always builds first. If something is wrong it stops, says which file and line,
and does not touch Zakuro's folder.

## 2. The demo mods

| Command | What it makes | Works today? |
|---|---|---|
| `example-text` | `mods/ExampleText`: **Ryoma's name shows as "Ryouma"** | yes |
| `example` | `mods/Example`: **Ryoma's Strength +10** | yes, now that `config/tables/Person.csv` exists |
| `example-item` | `mods/ExampleItem`: **a new item, "Example Sword"** (a Bronze Sword copy with 5 more might), in the avatar's starting items in Chapter 1 | builds, installs and uninstalls; not seen in the game yet |
| `example-map` | `mods/ExampleMap`: **one enemy of Birthright Chapter 7 (`A007`) stands two tiles away from its usual place** | builds, installs and uninstalls; not seen in the game yet |
| `example-face` | `mods/ExampleFace`: **Ryoma's normal standing portrait tinted blue** | builds, installs and uninstalls; not seen in the game yet |
| `example-castle` | `mods/ExampleCastle`: **one dining-hall dish gives 3 more Strength** (the dish made from dining ingredient 0 alone; in the file it is the first dish, its Japanese name means "steak") | builds, installs and uninstalls; not seen in the game yet |

The tool finds Ryoma itself each time: the name label (`MPID_...`) in
`m/@E/GameData.bin.lz` whose English text is exactly "Ryoma", and for `example` the one
row of the Person table (in `GameData/GameData.bin.lz`) that uses that name label. No game
text is written into this repository.

- `example-text` changes one message and nothing else [high: tests compare every other
  label]. Look at Ryoma's name when he appears (Birthright and Revelation; he is also in the
  shared opening chapters).
- `example` adds 10 to the Person table's `base.str` column of his main record. The tables
  work reads that column in the code that computes Strength (`Unit::GetStrImpl`,
  config/tables/Person.csv) [high that the column is read there; medium that every chapter
  uses this main record: the per-chapter files in `GameData/Person/` hold their own copies
  of some characters, and those are not changed].
- `example-item` finds the Bronze Sword the same way (the Item row whose `MIID_` name has
  the English text "Bronze Sword"), copies its row to the end of the Item table under the
  new ID `IID_EXAMPLE_SWORD` with might +5, names it with two new messages
  (`MIID_EXAMPLE_SWORD` "Example Sword", `MIID_H_EXAMPLE_SWORD` its help line, both our
  own words), and puts it into the first empty item slot of the avatar's placement in
  Chapter 1 (`GameData/Dispos/A001.bin.lz`, the player unit that carries the Bronze
  Sword). The copied row keeps the Bronze Sword's shop stock and prices, so it may also be
  sold where the Bronze Sword is [medium: the shop columns' meaning is from the code, the
  shop names are not].
- **Not checked in the game yet.** Owner step, about 5 minutes: `example-text` and
  `example`, `install`, look at Ryoma's name and stats, then `uninstall`. For the new item,
  see "Owner check: the new item" in section 6.

## 3. Making a mod

```
mods/MyMod/
  mod.json            {"name", "description", "enabled", "order", "override"}
  text/
    m/@E/GameData.bin.lz.txt       a message archive as text (section 4)
  romfs/
    face/...                       whole replacement files (section 5)
  tables/
    Person.csv                     spreadsheets (section 6)
  maps/
    A007/units.csv ...             a map package (section 6a)
  faces/
    Ryoma/portrait.json, PNGs      a portrait folder (section 6b)
  castle/
    DiningData/DiningData_Dish.csv castle spreadsheets, one folder per castle file (section 6c)
```

Two optional switches in `mod.json`: `"allow_face_resize": true` (section 6b) and
`"lenient_maps": true` (section 6a).

### Commands

| Command | What it does |
|---|---|
| `new NAME [--description T] [--tables A,B] [--text ARCHIVE,...]` | make a mod: a copy of every spreadsheet that has a layout, or only `--tables`; with `--text` and no `--tables`, a text-only mod |
| `text NAME ARCHIVE...` | add the whole text file of message archive(s) to an existing mod |
| `archives` | where the game's text is: how many archives are shared, per route, common |
| `map NAME MAP...` | add a map package (for example `A007`) from your game to a mod: `maps/<MAP>/` (an empty mod NAME is made if there is none) |
| `face NAME QUERY [--folder F] [--extras]` | add a character's portrait folder to a mod: `faces/<F>/` (QUERY as in `python tools/assets/portrait.py list`; `--extras` adds hair and accessory layers; an empty mod NAME is made if there is none) |
| `castle NAME FILE [--sheets K,...]` | add a castle file's spreadsheets to a mod: `castle/<FILE>/` (FILE for example `DiningData`, `AcceShop`, `JobIntro`; `--sheets` picks some sheets of it; an empty mod NAME is made if there is none) |
| `example` / `example-text` / `example-item` / `example-map` / `example-face` / `example-castle` | make the demo mods (section 2) |
| `list` | the mods in build order, on/off, how many cells, text labels and whole files each changes, and how many map, portrait and castle folders it has |
| `enable NAME` / `disable NAME` | switch a mod on or off (run `install` afterwards) |
| `build` | check and merge the mods that are on, write the changed files to `build/mods/romfs/` and a readable list of every change to `build/mods/changes.txt` |
| `install [--no-build]` | build, then copy into Zakuro's folder for Fates |
| `uninstall` | remove exactly what `install` put there; put back anything it moved aside; also undoes an install that was interrupted (section 7a) |
| `uninstall --restore-backups` (or `recover`) | the same, and where you changed an installed file afterwards: move that file to `fe14pcport-changed\` (not deleted) and put your previous file back (section 7a) |
| `status` | what is on, what is built, what is installed, and whether they match |
| `selftest` | the tool's own checks, in a temporary folder |

Options for every command: `--zakuro-dir DIR` (default `%APPDATA%\zakuro`),
`--mods-dir DIR` (default `mods/`) and `--stage-dir DIR` (default `build/mods/`).

### Several mods at once

Mods that are on are applied in `order` (smaller first; ties by folder name). If two mods
change the **same** text label, the same cell, or replace the same whole file
differently, the build stops and names both. To let the later one win, set
`"override": true` in its `mod.json`. Two mods making the same change are fine. A whole
file in `romfs/` and a text or cell change to that same file cannot be combined (the
whole file already decides every byte); the build says so. The same goes for maps and
portraits: two mods editing the same map or the same portrait file stop the build unless
the later one has `"override"` (then its whole file wins), and a map edited both in
`maps/` and as a `DisposUnit.csv` spreadsheet is refused (edit it in one place). Castle
spreadsheets merge cell by cell like tables: two mods setting one castle cell to different
values stop the build unless the later one has `"override"`.

## 4. Text: names, descriptions, dialogue

```bash
python tools/mods/mods.py new MyText --text m/@E/GameData.bin.lz   # a text-only mod
#   ... edit mods/MyText/text/m/@E/GameData.bin.lz.txt, save as UTF-8
python tools/mods/mods.py install
```

**Where the text is** (`python tools/mods/mods.py archives`):

| Folder | What | Files |
|---|---|---|
| `m/@E/` | English text used by every route. `GameData.bin.lz` holds unit, class, item and skill names and descriptions; the chapter-numbered files (`A001`...) hold conversations | 1,239 |
| `m/A/@E/`, `m/B/@E/`, `m/C/@E/` | English text for one route only: A = Birthright, B = Conquest, C = Revelation | 22 each |
| `m/common/` | text with no language folder | 23 |

That is 1,328 archives; there are none anywhere else in the game. The route letters come
from file names, not from the code [medium] (config/game.json `route_folders`). To find a
label, dump all text once (`python tools/assets/msg.py dumpall`, then look in
`extracted/assets/text/`).

**Format** (the one `tools/assets/msg.py` writes):

```
#msgarchive 1                 keep this first line
#name "MESS_ARCHIVE_..."      keep this second line as it was dumped
[MPID_...]                    a label that exists in that archive
New text on ONE line          \n = line break, \\ = backslash, \uXXXX = other codes
[LABEL_B] = LABEL_A           alias: LABEL_B shows LABEL_A's text (keep these lines as dumped)
```

- **Only changed labels count.** Keep the whole dump or delete every label you do not
  change (keep the two header lines). An unedited dump builds nothing.
- **New labels** are allowed only in `m/@E/GameData.bin.lz` and only for a row the same
  mod adds (section 6, "New rows"): the `MIID_` name and `MIID_H_` help of a new item, the
  `MJID_` ones of a new class. They are added as new messages after the game's own; the
  game finds messages by name, so their place does not matter (`Mess::Get` 003D1CEC looks
  the label up in a dictionary).
- Blank lines and `#` comment lines between messages are ignored. Windows line ends and a
  byte-order mark (Notepad) are fine.
- **Refused, with file and line:** a label that is not in that archive (unless a new row
  of the same mod names it, above), a changed `#name`
  line, a changed alias line, text running onto a second line, a bad escape such as
  `\u12`, a label listed twice, a file that is not a message archive.
- **Warned:** a different number of `$` characters (`$` starts the control codes in
  conversations; a broken one may crash a conversation [medium]), a character the archive
  never uses (it may be missing from the font), an empty message.
- How it is built (`tools/mods/textmod.py`): your changed labels are merged into a copy of
  the original archive in the original order, packed and LZ13-compressed the way the
  original was, then read back: every label must show exactly the asked-for text.
- **Checked:** all 1,328 archives go dump -> text file -> build and give back the original
  file byte for byte (`python tools/mods/textmod.py roundtrip`, and in
  `tests/test_text_mods.py`, which compares the bytes itself). Renaming a unit changes
  only that message's bytes [high, test]. A name much longer than the original may not fit
  its box on screen [guess].

## 5. Whole files (`romfs/`)

Put any replacement file in `mods/<Name>/romfs/` at the path the game uses, for example
`mods/MyPics/romfs/face/face/<file>.arc` or a rebuilt `.bch.lz` from `tools/assets`. It is
installed exactly as it is.

- The path must match a game path; upper/lower case does not matter (the tool uses the
  game's spelling). A path the game does not have is added, with a warning (the game only
  reads it if something asks for that name).
- A file whose name ends in `.lz` must be LZ-compressed when the game's own file is (the
  game would fail otherwise): refused with a hint (`python tools/assets/lz.py c IN OUT
  --fmt 13`). A few game files end in `.lz` without being compressed; for those anything
  is accepted. Replacing an LZ file with an uncompressed one under another name is warned.
- A file with the same bytes as the game's is skipped. `Thumbs.db`, `desktop.ini`,
  `.DS_Store` and editor backups (`name~`) are skipped. `exefs/` and `code.bin` are
  refused: code changes are not data mods.
- `build` copies each file into `build/mods/romfs/` and records its SHA-256; `install`
  and `uninstall` treat it like any other file (manifest, backup, never deleting a file
  changed by hand).

## 6. Spreadsheets (tables)

Table mods use the table layouts in `config/tables/` and the tools in `tools/tables/`
(the tables work; section 9). Whatever layouts exist there are editable here; nothing in
the mods tool is tied to a particular table. On 2026-11-10 the layouts cover Person,
PersonChapter (per-chapter characters), Job, Item, Skill, Belong, Chapter and the ID lists;
check `python tools/mods/mods.py status` and `new` for the current list. Confidence per
column (`high`/`medium`/`low`) and the evidence are in each layout file: editing a `low`
column is allowed, but nobody knows yet exactly what it does.

- `new NAME` copies every spreadsheet; `new NAME --tables Person,Job` only those. Only
  cells that differ from the game count. You may delete spreadsheets, rows and columns you
  do not need, but keep `index` and `label` (plus `file` for tables spread over several
  files): they say which row is which.
- **Saving from Excel:** *Save As > CSV UTF-8 (Comma delimited)*. Other character sets are
  refused with that hint (the IDs are Japanese). Semicolons, tabs, no byte-order mark and
  numbers written as `12.0` are accepted.
- **Checked for every changed cell:** whole numbers inside the column's range (0..255 for
  `u8`, -128..127 for `s8` ...); links, flags and kinds must name a record or ID that
  exists; raw bytes (`hex` columns) must have the right number of hex digits; a record's
  own ID (`pid`, `jid` ...) cannot be renamed; raw data offsets (`@0x...`) cannot be
  edited; editing a text ID (`mpid_name`, `fid` ...) gives a warning. Read-only tables or
  columns can be listed in `config/tables/readonly.csv` (`table,column,reason`).
- Every rebuilt file is read back: it must decode to exactly your spreadsheet, every other
  table in the same file must be unchanged, and it must pass `tools/tables/check.py`.
- **Rows are never removed.** Rows can be **added** to Item and Job (below).

### New rows (new items and classes)

Put the new row at the end of the spreadsheet with the next free `index` (the first new
item is 355, the first new class 129; two new rows are 355 and 356). Easiest: copy an
existing row to the end and change it.

- The row needs **every column** of the table (a copied row has them).
- `label` is the new ID: `IID_...` for an item, `JID_...` for a class, not used by the game
  (letters, digits and `_` are safest). The own-ID column (`iid`, `jid`) must be the same
  text or empty; the number column (`item_number`, `job_number`) must be the index or empty
  (the tool fills it in).
- Give it its own name and help IDs (`miid_name`, `miid_help`), and give those labels text
  in the mod's `text/m/@E/GameData.bin.lz.txt` (two header lines, then a label line and a
  text line each). A name ID the game does not have and the mod gives no text for is
  refused. Reusing an existing name ID is allowed (the new item then shows that name).
- To make it obtainable, name the new ID somewhere the game gives items: a unit's starting
  items (`DisposUnit.csv`, `item_1` .. `item_5`, per chapter file) or the shop stock
  columns of the row itself. Any `IID_` or `JID_` text in a changed cell must name an item
  or class that exists or that an enabled mod adds; anything else is refused.
- **Refused, with the reason:** new rows in any other table (Person: the game keeps a
  256-person bit set, `GameProfile::UpdateReliance`, and already has 255 people; tables
  spread over several files; tables nobody has checked; tables with a fixed size in the
  code), gaps in the numbering, a label that already exists, two mods adding rows to the
  same table (their numbers would collide; put them in one mod), and a reference to a new
  row through a numbered link column (`ref`/`ptr`; e.g. an arena weapon): those still need
  an existing record. The table decisions and their code evidence are in
  `config/tables/appends.csv` and docs/TABLES.md, "Adding records".
- **Saves and DLC:** the game stores items by number, so a save that holds a new item
  needs the mod installed to show it right; item or class DLC would use the same numbers
  as new rows, so do not combine such DLC with a mod that adds items or classes [medium,
  from the code; not checked in game].

**Owner check: the new item** (about 5 minutes, after `python tools/mods/mods.py
example-item` and `install`):

1. Start Fire Emblem Fates in Zakuro and begin a **new game** (Birthright is not needed:
   Chapter 1 is shared by every route). Play through the Prologue.
2. In **Chapter 1**, before the first move, open the avatar's items (select the avatar,
   then Items, or look at the unit's status page).
3. Expected: a second item named **Example Sword** next to the Bronze Sword, with the same
   icon. Its help line reads "A Bronze Sword copy with 5 more might, added by the
   ExampleItem mod." Its might is the Bronze Sword's plus 5 (the item detail window), and
   equipping it raises the shown attack by 5 over the Bronze Sword.
4. Write down what you saw (or a screenshot), then `python tools/mods/mods.py uninstall`
   and restart: the Example Sword is gone from a new game.

If the game crashes when Chapter 1 loads, or the item shows without a name, say so: that
tells us whether the game reads new records and new messages as the code suggests.
- If `config/tables/` has no layouts (or `tools/tables` cannot be loaded), table mods are
  switched off with the reason in `status` and `list`; a mod with a `tables/` folder is
  then refused, and text and whole-file mods keep working.
- **Saves:** values the game copies into your save when a unit joins or levels up (level,
  items, stats already gained) keep their old values in that save; values it reads every
  time (personal and class bases, caps, weapon numbers) change at once [medium, from
  Awakening; not checked for Fates]. For a clean test, start a new game.

## 6a. Maps (`maps/`)

A map mod holds one folder per map, named after the map's file: `A007` is Birthright
Chapter 7 (A = Birthright, B = Conquest, C = Revelation; names ending in `E` are the
random-encounter versions, `V` the versus maps; `python tools/maps/maps.py list` shows
them all). The folder is the same "map package" the map tool makes, so everything in
docs/MAPS.md applies.

```bash
python tools/mods/mods.py map MyMap A007             # writes mods/MyMap/maps/A007/ (makes MyMap if needed)
#   open mods/MyMap/maps/A007/preview.png to see the map, units and coordinates
#   edit mods/MyMap/maps/A007/units.csv (and terrain.csv) in a spreadsheet, save as CSV UTF-8
python tools/mods/mods.py install
```

What is in the folder: `units.csv` (one row per placed unit, every group and difficulty),
`terrain.csv` (the tile grid), `tiles.csv` (the tile types), `map.csv` (size; read only),
`preview.png` (our own drawing, for you) and `about.txt`. Only `units.csv`,
`terrain.csv` and `tiles.csv` change anything; you may delete the files you do not edit.

- **You can:** move a unit (`x`, `y`, and `start_x`, `start_y` where it appears first);
  change its class, level, items, skills, AI or side; take it off the map (set `normal`,
  `hard` and `lunatic` to 0: rows are never deleted); add a unit at the end of an
  existing group (copy a row of that group to the end and set its `slot` to `new`);
  change a tile or a tile type's values.
- **Checked when you build** (the same checks as `python tools/maps/maps.py check`):
  positions inside the playable area, tiles the unit's class can walk on, characters,
  classes, items and skills that exist, numbers that fit, no deleted rows, at most 50
  units of one side per difficulty. Items, classes and skills that **any enabled mod adds**
  in its `tables/` count as existing, so a new item of `ExampleItem` can be given to a
  unit here.
- **Refused:** a new group (the chapter's script calls groups by name), new units in the
  random-encounter (`Mob`) groups or on versus maps, a different map size, changing the
  map model. Reinforcement turns are decided by the chapter's script, not by the map file,
  so they cannot be changed here.
- A unit on a door or wall that an event opens later: set `"lenient_maps": true` in
  `mod.json` to make "cannot walk there" a warning instead of an error.
- The game's own rows that the checks would flag (some stand on such tiles already) are
  left as they are and only counted in a note.
- The build rebuilds the map's `GameData/Dispos/...` and/or `GameData/Terrain/...` file
  in the game's own LZ format, reads it back, and stages only the files that changed. An
  unedited package stages nothing (all 185 placement and 109 terrain files come back
  byte for byte, `check_all` row `maps-roundtrip`).

**Owner check: the moved enemy** (about 5 minutes once you have a save at the start of
Birthright Chapter 7, for example the save made right after choosing Birthright; without
one, playing there takes longer):

1. `python tools/mods/mods.py example-map`. It prints which enemy it moved and from where
   to where, for example `moved from (1, 20) to (3, 20)` (x counts columns from the left,
   y rows from the top, starting at 0). `mods/ExampleMap/maps/A007/preview.png` shows the
   map with the unit in its new place (red squares are enemies).
2. `python tools/mods/mods.py install`, start Fire Emblem Fates in Zakuro.
3. Start **Birthright Chapter 7 fresh** (not by resuming a suspended battle: a suspended
   battle may keep its own copy of the map).
4. Expected: on the first turn, that enemy stands two tiles from where the original game
   puts it; everything else is the same. Compare with the preview picture.
5. Write down what you saw, then `python tools/mods/mods.py uninstall`.

If the chapter does not load, or the enemy is missing, say so: it tells us whether the
game reads a rebuilt map file the way the code suggests.

## 6b. Portraits (`faces/`)

A portrait mod holds one folder per character (any folder name). Inside is what
`tools/assets/portrait.py export` makes: `portrait.json` (the list of pictures) and one
folder of PNG files per game file, one PNG per expression and overlay.

```bash
python tools/assets/portrait.py list                  # find the character (FSID, name ID, key)
python tools/mods/mods.py face MyFace CAMILLA --folder Camilla   # writes mods/MyFace/faces/Camilla/
#   paint over the PNGs you want to change (keep the file names)
python tools/mods/mods.py install
```

- Only PNGs that differ from the game's picture count; the others leave their file
  untouched. Each changed file (`face/face/<name>.arc`, hair or accessory `.bch.lz`) is
  rebuilt, every picture in it is read back, and only then staged.
- **Keep the size.** The 3DS draws a portrait at its pixel size, so a bigger picture shows
  bigger on screen (not sharper) and the sweat and blush overlays stay where they were
  (docs/ASSETS.md 3.3.2). A different size is refused unless `mod.json` has
  `"allow_face_resize": true`; even then both sides must be powers of two from 8 to 1024,
  and every expression of one portrait must get the same new size. The build warns for
  each resized picture.
- The pictures are re-encoded in the game's format (mostly ETC1A4, which is lossy):
  expect tiny colour differences where you did not paint; about 3 to 5 seconds per
  256x256 picture.
- `romfs/` (section 5) still takes a finished `.arc` made elsewhere; a `faces/` folder and
  a `romfs/` file for the same game file cannot be combined.

**Owner check: the blue Ryoma** (about 5 minutes):

1. `python tools/mods/mods.py example-face` (it tints Ryoma's normal standing expression
   blue by code; nothing is painted by hand), then `install`, then start the game.
2. Go to any scene where Ryoma talks with his big standing portrait (he appears in the
   shared opening chapters; a save with him in your army works too, for example a support
   conversation in My Castle).
3. Expected: with his normal expression his face and clothes look blue; his other
   expressions (smiling, angry ...) and his small portrait in menus look as usual.
4. Write down what you saw, then `uninstall`.

If he shows a garbled or empty picture, or the game crashes when he talks, say so.

## 6c. Castle data (`castle/`)

A castle mod holds one folder per castle file, named after the file without its folder
and extension (`DiningData` for `GameData/Castle/DiningData.bin.lz`, `AcceShop`,
`JobIntro`, `CastlePerson`, `MyRoom`, `Fortune`, `Butler`, `CastleButlerVoice`,
`CastleObstacle`, `CastlePosition`, `AcceActionData`, `MyRoomMotion`). Inside are the
spreadsheets `tools/castle/castle.py dump` writes, with the same names:
`<SHEET>.csv` for a sheet, `<SHEET>__<LIST>.csv` for the items of a list column. What each
column means, and how sure we are, is in docs/CASTLE.md.

```bash
python tools/mods/mods.py castle MyCastle DiningData     # writes mods/MyCastle/castle/DiningData/
#   change cells (a dish's stat bonus, a cooking title's bonus ...), delete the CSVs you do not change
python tools/mods/mods.py install
```

- Only cells that differ from the game count; numbers compare by value (`0x10` = `16`).
  The `index` and `label` columns (and `item` in list files) must stay as dumped: rows are
  found by number and by label, so they cannot be moved, renamed or removed.
- **New rows** only where the code shows it is safe (docs/CASTLE.md "Which rows may be
  added", F-016): today the dining dishes and cooking titles. Put the row at the end,
  number it, and give it a new label. A new dish also needs its name text, and a new title
  is only used if a character's `cook_title` names it; the tool does not add either for
  you. Rows added to the accessory shop and everywhere else are refused with the reason.
  New rows from several mods are kept in mod order and renumbered.
- List items (JobIntro units, Fortune pairs, butler voices ...) can be changed, not added
  or removed.
- Each changed file is rebuilt by `tools/castle`, then read back: every sheet and list of
  the file must decode to exactly the merged spreadsheet (unedited sheets included), in the
  game's LZ format, before it is staged. A castle file cannot also be replaced as a whole
  file in `romfs/`.

**Owner check: the better dish** (about 5 minutes; needs a save in My Castle with the dining
hall built and a cooking turn not yet used today):

1. `python tools/mods/mods.py example-castle`, then `install`, then start the game and load
   that save. (The command prints which dish row changed and the Strength before and after.)
2. In the dining hall, cook with **one** ingredient only: the first dish in the file is
   made from dining ingredient number 0 alone. We have not matched the ingredient numbers to
   the menu yet; the dish's Japanese name means "steak", so try meat first.
3. Expected: the meal's Strength bonus is 3 more than without the mod (the cooking title
   and the cook can add their own bonus on top; compare with the same meal after
   `uninstall`, from the same save).
4. Write down what you saw, then `uninstall`.

If the meal shows the old bonus, say so, with the ingredient you used and the dish the game
named: either the dish was a different one, or something else decides the bonus.

## 7. Where the files go (Zakuro)

- Zakuro looks in `<its data folder>\mods\<title id>\`: here
  `%APPDATA%\zakuro\mods\0004000000179800\` (upper case; lower case is used only if that
  folder alone exists, and the tool follows the same rule). Files in `romfs\` replace the
  game's file at the same path (exact name first, then ignoring case) or are added, byte
  for byte, so they stay LZ-compressed like the originals. (Read from Zakuro's source,
  `crates/zakuro-core/src/mods.rs` and `crates/zakuro-fs/src/layered.rs`, v0.2.32, for the
  Awakening port; the code is the same for every title.)
- Data mods need **no recompile**: the recompiler only looks at the code. Restart the game
  after installing.
- The tool writes only inside `...\mods\0004000000179800\`: the files under `romfs\`, a
  manifest `fe14pcport-mods-manifest.json` (Zakuro ignores it) and, if a file was already
  there, a copy of it under `fe14pcport-backup\`. The manifest is written **before**
  each change: it says which file is about to be placed and where the earlier file will be
  kept, and it is saved to disk before anything is moved. Each file is copied under a
  temporary name (`.fe14tmp`), saved to disk, and then renamed into place. So a crash at
  any moment leaves a manifest that names everything the install may have touched
  (section 7a). `uninstall` keeps the manifest up to date the same way: before it puts a
  file of yours back it notes that in the manifest, and once the file is back it crosses
  that file off. So an uninstall that is itself interrupted can always be finished, and it
  never mistakes your restored file for a changed mod file.
- `uninstall` deletes only files whose contents are still exactly what it installed. A
  file you changed by hand afterwards is left alone and reported. Folders it made are
  removed when empty. Your own files in that folder are never touched; one at the same
  path as a mod file is moved aside on install and put back on uninstall.
- Mods are built from the base game. If you add a Fates update to Zakuro, a mod file also
  replaces the update's version of that file.

## 7a. If an install is interrupted, or uninstall leaves something

**The install stopped part-way** (the computer crashed, the window was closed, the power
went off): nothing is lost. Run `python tools/mods/mods.py uninstall` and the folder is put
back exactly as it was before that install, including any file of yours that had been
moved into `fe14pcport-backup\`. Or just run `install` again: it first undoes the
unfinished install, then installs. `status` says `THIS INSTALL DID NOT FINISH` while one is
waiting to be undone.

**The uninstall stopped part-way** (or the automatic undo at the start of `install` did):
run `python tools/mods/mods.py uninstall` again. It carries on where it stopped; files of
yours it had already put back stay as they are. `status` says `AN UNINSTALL DID NOT FINISH`
until then.

**The disk filled up during install** (or a file was locked): install undoes what it had
done straight away and says so. Free some space and run `install` again.

**Uninstall said a file "was changed since install"**: you (or another tool) changed a file
after `install` put it there, so `uninstall` did not delete it. If a file of yours was
there before the install, it is still safe in `fe14pcport-backup\` (the message names it);
it was not put back, because that would overwrite the changed file. `install` refuses until
this is settled. To settle it, run:

```bash
python tools/mods/mods.py uninstall --restore-backups     # or: python tools/mods/mods.py recover
```

It moves each changed file to `fe14pcport-changed\` in the same folder (nothing is
deleted; look there if you want it), puts your previous files back, and finishes the
uninstall. Then `install` works again.

**A file is in `fe14pcport-backup\` but no install mentions it** (for example the manifest
was deleted by hand, or an older version of this tool stopped at the wrong moment):
`uninstall` puts it back if nothing is at its place. If something is, it is left alone and
`uninstall --restore-backups` does the same as above.

## 8. Not yet

- Removing rows; adding characters, skills or per-chapter rows (refused, section 6); new
  text labels except for new rows.
- Typed conversation control codes (edited today as the raw characters).
- Castle: new rows anywhere except the two dining sheets, new list items, and the plain
  castle files without the sheet shape (`castle_building`, `castle_join`, `castle_food`
  ...; docs/CASTLE.md "Not done"). Nothing from a castle mod has been seen in the game yet.
- Maps: new groups, reinforcement turns (both live in the chapter scripts), units in the
  random-encounter groups and versus maps, other map sizes (section 6a).
- Pictures other than portraits (menus, map sprites, battle models) as PNG folders: today
  they go in as finished files under `romfs/` (section 5), made with `tools/assets/bch.py`.
- Portrait cube maps and other effect textures cannot be resized (docs/ASSETS.md).
- Code changes (Zakuro's `code.ips`, or per-function C overrides).

## 9. For developers: the table backend contract

`tools/mods/mods.py` calls `tools/tables` and nothing else for tables. It needs, from
`tablelib.py`: `ROMFS`, `CONFIG`, `registry()` (TableDef with `.file`, `.files()`,
`.size`), `layout_path(name)`, `Codec(reg, name)` with `.columns()`, `.decode(c, i, base,
label)`, `.fields` (Field with `.kind`, `.width`, `.signed`, `.n`, `.ref`, `.type`,
`.columns()`), `.reflabels()`, `.ids()`; `container(rel)`, `Container(rel, raw)` (`.raw`,
`.is_lz`, `.label_off`, `.labels_at`), `locate(t, c)`, `record_labels(t, c, start, count)`,
`text()`, `untext()`, `EMPTY_STR`, `LayoutError`, `_CACHE`, and for new rows
`append_refusal(t)` (None or the reason) and `append_policies()` (per table:
`.number_field`, `.prefix`); from `build.py`:
`build_file(reg, rel, tables, override={table: (head, rows)})` returning the stored bytes
(rows past a table's end are appended), `shift_cells(reg, name, rows, moves)` and
`LAST_MOVES[rel]` (raw `@0x` offsets as they read back after an append);
from `check.py`: `check_table(reg, name)` returning `(records, errors)`. A table is
multi-file when its `file` field contains `*` (rows then start with a `file` column).
Column kinds understood by the cell checker: `int`, `enc` (obfuscated, multiples of 5),
`hex`, `ref`, `enum`, `flags`, `str` (and `str:self`), `lptr`; anything else is refused
as uneditable. `selftest` exercises this contract on an invented layout over an invented
container, so a break shows up even before real layouts change.

## 10. Checks

- `python tools/mods/mods.py selftest` (24 checks today; `check_all.py` row
  `mods-selftest`): text archives from every place round-trip; an unedited dump builds
  nothing; `ExampleText` changes one label and stays LZ13; route and common archive edits
  build; broken text files are refused; install over existing files, reinstall and
  uninstall restore a fake Zakuro folder byte for byte; a fresh folder is left without a
  trace; a hand-edited file is never deleted; a missing Zakuro folder is refused; the
  lower-case folder rule; an install stopped by a crash at every step (after the manifest
  record, after the move-aside, half-way through and after the copy, after the rename, in
  each manifest write) is undone byte for byte by `uninstall` or by the next `install`;
  disk full at each of those steps is undone at once; a refused uninstall is finished by
  `uninstall --restore-backups`; a crash at every step of `uninstall`, and of the undo at the
  start of an `install` over an earlier one, is finished byte for byte by the next
  `uninstall`; whole files install as-is, take the game's spelling, and the LZ,
  same-bytes, junk, new-file, code and conflict rules; table mods on an invented layout
  (unedited, one-cell edit read back and installed, invalid cells, conflicts); table mods
  switched off cleanly; with the real layouts, an unedited mod of every spreadsheet builds
  nothing and `Example` changes exactly one Person cell. Scratch folders live under
  `build/mods-selftest/` and are deleted afterwards.
- `python -m unittest tests.test_text_mods` (55 tests): the parser, aliases, errors, new
  labels only for new rows,
  merging, conflicts, disabled mods, the out-of-date check, `list`, `status`, the
  read-back guard and whole-file mods on invented archives; an install stopped by a crash
  or a full disk at every step undone byte for byte (by uninstall or the next install), a
  refused uninstall finished with --restore-backups or recover, status naming an unfinished
  install or uninstall; a crash at every step of uninstall, of `--restore-backups`, of the
  undo inside an install over an install, and of the undo after a full disk, each finished
  byte for byte by the next uninstall (also when your previous file has the same bytes as
  the mod's); and, on your own
  `extracted/romfs/`, all 1,328 archives byte for byte (none outside the message folders),
  the one-unit rename, and the rename demo built, installed into a scratch Zakuro folder
  under `build/` (never `%APPDATA%`) and uninstalled back to the exact earlier state;
  the new-item demo built, its staged files decompressed and parsed in the test (the new
  Item record resolves by its ID, its name and help messages exist, the Chapter 1 unit
  carries it), installed into a scratch folder and uninstalled back exactly; a new Person
  row, a new item without its name text and a placement naming an unknown item refused.
  Maps: the `ExampleMap` demo built, the staged placement file decoded in the test
  (exactly one unit differs, only in its position), installed into a scratch Zakuro
  folder and uninstalled back exactly; a unit outside the playable area and an unknown
  item refused, an item another mod adds accepted, a map edited both as a map and as a
  spreadsheet refused, two mods on one map a conflict unless `override`, a folder that is
  not a map refused, an unedited package staging nothing. Portraits: the `ExampleFace`
  demo built, the staged `.arc` parsed in the test (same members, exactly the tinted one
  changed, its picture measurably bluer, same size), installed and uninstalled back
  exactly; halved pictures refused without `allow_face_resize`, refused with it while one
  expression keeps the old size, built with it (pictures read back at half size, a warning
  given); an unedited portrait folder staging nothing.
- Castle (`CastleModTests` in the same file): the `ExampleCastle` demo built, the staged
  dining file decompressed in the test (exactly one byte differs: the dish's Strength, +3)
  and decoded (only that cell differs), installed into a scratch Zakuro folder and
  uninstalled back exactly; a dish added through a mod decodes back with its label and a
  reused label is refused; rows added to the accessory shop, removed rows, renamed labels,
  changed columns, a value too big for its byte, an unknown file or folder, an added list
  item and a castle file also replaced in `romfs/` refused; two mods on one cell a
  conflict unless `override` (the same number written two ways is not); an unedited copy
  of every castle file staging nothing.
- Other gates the map and portrait mods rely on (`check_all.py` rows): `maps-test` and
  `maps-roundtrip` (the map tool), `assets-bch` and `assets-bchwrite` (picture edits and
  resizing), `assets-portrait` and `assets-bchwrite-all` (every portrait file and every
  BCH in the game; slow rows, `--slow`). Castle mods rely on `castle-test` (the castle
  tool's own tests) and the slow `castle-all` (every sheet-shaped file in the game).
- Nothing from the game is tracked in git: `mods/*` is ignored except `mods/README.md`;
  built files live in `build/mods/`.
