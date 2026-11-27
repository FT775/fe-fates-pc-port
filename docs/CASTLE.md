# Castle data as spreadsheets

**In plain words.** Much of My Castle is ordinary data: what each dish in the dining hall
gives (+2 Strength for the day), what each cooking title adds, which accessories the
shop sells and what they do, which characters star in each class showcase, who likes
which accessory. Fates keeps this in small files that describe themselves: each one
carries its own list of column names and types, then the rows. The castle tool turns
those rows into spreadsheets and back into game files. An unedited spreadsheet comes back
byte for byte identical (checked for every file below), an edit changes exactly the bytes
of the edited cell, and new rows can be added to the two dining sheets, where the code
shows that is safe. Everywhere else, new rows are refused with the reason.

Status (2026-11-11): the tool works and its 16 tests pass. **No castle edit has been seen
in the game yet.** Castle spreadsheets are a mod kind (`mods/<Name>/castle/`, docs/MODDING.md
section 6c) and `check_all` runs `castle-test` (and `castle-all` with `--slow`). The castle renderer itself stays off both finish
lines (F-008); this page is only about data.

Confidence tags as in the plan: **[high]** read in the code, **[med]** good evidence
(usually the file's own column declaration), **[low]** a guess from the values. Addresses
come from `config/functions.csv` (the game's own symbol map).

## Quick start: make a dish better

```
python tools/castle/castle.py dump DiningData_Dish   writes build/castle/DiningData_Dish.csv
#   open it in a spreadsheet, change "str" of one dish from 1 to 3, save as CSV UTF-8
python tools/castle/castle.py check                  every layout still matches its file
python tools/castle/castle.py build DiningData_Dish  writes build/castle/rebuilt/GameData/Castle/DiningData.bin.lz
```

`python tools/castle/castle.py dump` writes every sheet below; `build --check --no-write`
on an unedited dump proves every file comes back identical. Everything under `build/` is
your own game data and never goes into git. The rebuilt files keep their RomFS paths, so
they work as file overrides like the table and map tools' output.

## The commands

| Command | What it does |
|---|---|
| `castle.py dump [KEY ...]` | `build/castle/<KEY>.csv` per sheet (UTF-8 with BOM), and `build/castle/<KEY>__<LIST>.csv` for the items of a list column |
| `castle.py build [--check] [--no-write] [KEY ...]` | rebuild every file that holds a sheet from the CSVs (a missing CSV = unchanged) into `build/castle/rebuilt/`; `--check` fails unless identical to the original |
| `castle.py check [KEY ...]` | each layout against the file's own column list, the row size the code expects, list items, row labels, overlaps |
| `castle.py survey [--all]` | every file in the RomFS with this shape and its status; `--all` also round-trips each one with its declared types (about 1 minute) |
| `castle.py roundtrip` | dump -> CSV text -> build in memory for every registered file |
| `castle.py edit-test` | five one-cell edits, each proven to change exactly the edited bytes |
| `test_castle.py` | the tests (below); `FEF_CASTLE_ALL=1` adds the all-files round trip |

## Cells

The first columns are `index` (row number) and `label` (the row's key, empty for rows
without one). Then one column per field. Numbers are decimal. `str` cells are the text;
empty = no string, `""` = an empty string. `list` cells read `n=COUNT`: the items live in
their own spreadsheet `<KEY>__<LIST>.csv` (columns `row`, `row_label`, `item`, then the
fields) and can be edited in place, not added or removed. `ptr` cells (`@0x...`) are kept
as they are. Floats (other files only) are written so they come back to the same bits.

Rows can never be removed, moved or renamed (the game finds rows by number or by label).

## What a sheet file is

An ordinary IS `.bin` (header, data, relocation list, labels, string pool; see
`tools/assets/isbin.py`). Inside the data region each *sheet* has three parts, all found
through labels:

1. `MOD_<name>`: a field count, then 20 bytes per field: the field's name, its type name
   (`u8 s8 u16 s16 u32 f32 str ptr`) and 12 bytes (three floats that look like editor
   ranges; the loader does not read them). [high, every file]
2. The header, labelled with the sheet's own name, right after the field list: the sheet
   name, a 16-bit row count, a 16-bit row size, a pointer to the rows. [high]
3. `DAT_<name>`: the rows, fields packed in declared order without padding. Rows may carry
   their own labels (their keys). [high]

Once per file, `SHEET_LIST`: a count and the sheet names. [high]

How the game reads them [high, read in the code]:

- `StructList::Load(path, sheet, base id, row size)` (0018DF70) finds the header by name
  and **refuses the file unless the row size in the file equals the size compiled into
  the caller**. So a sheet's row size can never change: the layouts keep it and
  `check` compares it with the size in `config/tables/castle/sheets.csv`, which was read
  from each caller.
- `StructList::Update` (0018E140) builds a table of row pointers sized by the **row count
  in the file**. Rows are then reached by number (`StructList::TryGet(int)`, bounds-checked
  against that count) or by label (`StructList::TryGet(const char*)`, through a hash of
  the file's labels, so label order does not matter).
- `DiningData` is read without StructList: `ProcDining::ProcDining` (00180B90) takes each
  sheet's count and rows pointer with `StructFile::GetHeader`; the row size is fixed in
  the readers.

## Which rows may be added

A row may be added only where the code reads the count from the file **and** nothing
keeps a fixed-size array indexed by the row number. Decided per sheet:

| Sheet | Adding rows | Why |
|---|---|---|
| DiningData_CookTitle | **allowed** (label needed) | Count from the file (ProcDining ctor). `ExecuteCookingInternal` (0017F384) picks the cook's own title by label (the text in CastlePerson.cook_title) or a random one below the count. No fixed array. |
| DiningData_Dish | **allowed** (label needed) | Count from the file. `ExecuteCookingInternal` scans rows 0..count-1 for the chosen ingredient pair and falls back to row 0. No fixed array. |
| AcceShop | refused | `castle::Accessory` keeps a fixed 256-byte owned-count array (saved) indexed by the row number (`AddAccessory` 00499AE8, its loader 00499A4C), and units store worn accessories as row numbers in bytes (unit+0x90..+0x93). A new row would use a save slot nothing has checked. |
| JobIntro_Group | refused | Count from the file and a random pick below it (`JobIntroSequence::CreateBind` 001ED8A8), but `ProcJobGroup::BeginGroup` reads the group's unit list with no null check and this tool cannot create a new list yet. |
| CastlePerson, CastleButlerVoice, AcceActionData | refused | One row per character, found by the character's ID; new characters are refused by the Person tables (docs/TABLES.md). |
| all others | refused | Reader not checked for fixed counts. |

New rows go after the last row; the tool opens the gap, moves every pointer, relocation
and label after it, raises the header's count and exports the new row's label.

## The sheets (and how sure we are)

Field-by-field evidence is in `config/tables/castle/<KEY>.csv`. Every field type matches
the file's own declaration (checked); "medium" usually means the file names the field
but no reader was traced.

| File | Sheet key | Rows | Row size (code) | Fields: high / med / low | Notes |
|---|---|---|---|---|---|
| `GameData/Castle/DiningData.bin.lz` | DiningData_CookTitle | 33 | 0x14 | 11 / 6 / 0 | cooking titles: who gets the bonus (+0x5), two extra effects (+0x6, +0x7), stat bonuses (+0xA..+0x10 read in `CalculateCookTitleEffect` 0017F590) |
| | DiningData_Dish | 55 | 0x10 | 11 / 1 / 0 | dishes: two ingredients (255 = none), eight stat bonuses (`ReflectDishEffect` 0017F008 adds +0x6+i) |
| `GameData/AcceShop.bin.lz` | AcceShop | 61 | 0x18 | 3 / 9 / 0 | accessories: damage dealt (+0x2) and damage taken (+0x3) (`map::AccessoryEnhanceCalculator::Calculate` 003728D0, which runs only when GameUserData+0x28 bit 0x20 is set; what sets it was not traced), flags +0x14 (bit 0x20000 read), name, help, shop level, slot, material and count |
| `GameData/JobIntro.bin.lz` | JobIntro_Group | 9 | 0xC | 2 / 1 / 0 | class showcase groups, music, unit list |
| | (list) JobIntro_Unit | 79 items | 20 | 2 / 3 / 1 | class, person (`JobIntroData::Data::GetPerson`), item (`GetItem`), two numbers, battle field |
| `castle/CastlePerson.bin` | CastlePerson | 73 | 0x10 | 2 / 5 / 0 | per character: cooking title (looked up as a CookTitle label), liked and disliked accessory slots, hot spring, accessory reaction, voice label |
| `GameData/MyRoom.bin.lz` | MyRoom_Release | 4 | 0x8 | 0 / 4 / 0 | private quarters unlocks by heart count |
| `GameData/Fortune.bin.lz` | Fortune_List (+ Fortune_Pair) | 1 (30 pairs) | 0x4 | 0 / 1 / 2 | fortune teller character pairs |
| `GameData/Castle/Butler.bin.lz` | Butler (+ Butler_Job) | 1 (46 items) | 0x4 | 0 / 1 / 2 | butler class list |
| `castle/CastleButlerVoice.bin` | CastleButlerVoice (+ _Voice) | 4 (26 items) | 0x4 | 3 / 0 / 2 | weighted random butler voices (`castle::ButlerVoice::GetVoiceID` 0044E98C) |
| `castle/CastleObstacle.bin` | CastleObstacle (+ _Item) | 2 (7 items) | 0x4 | 1 / 5 / 1 | obstacles per castle map (`castle::Obstacle::Setup` 00497F64 reads five bytes per item) |
| `castle/CastlePosition.bin` | CastlePosition_Crowd, _CrowdMuse, _Siege, _Area, _View | 7, 7, 10, 11, 10 | 0x4 each | 0 / 20 / 0 | castle placements and areas (x, y, size) |
| `GameData/AcceActionData.bin.lz` | AcceActionData (+ _Pose) | 71 | 0x4 | 0 / 1 / 2 | accessory pose per character |
| `GameData/MyRoomMotion.bin.lz` | MyRoomMotion_Scene, MyRoomMotion_Motion | 11, 12 | 0x4, 0x28 | 0 / 11 / 1 | private quarters motions (scene data kept as pointers) |

Forge and stat priorities: forging is not in these files (it is `ItemRefine` in
`GameData.bin`, already a spreadsheet: docs/TABLES.md). The stat-relevant castle data is
the dining sheets (high confidence on every stat column) and AcceShop's damage columns.

## Every file with this shape (survey)

`python tools/castle/castle.py survey --all` (2026-11-11): **274 files** in the RomFS have
`MOD_` blocks; **273 round-trip byte-identical** with their declared types; one is
malformed.

| Files | Status |
|---|---|
| the 13 files in the table above | editable here, with layouts and evidence |
| `GameData/CameraData`, `GameEffect`, `GeoAttr`, `Live2D`, `MovieData`, `MovieLogo`, `Museum`, `MyUnitEdit` (`.bin.lz`) | same shape, round trip OK, not castle: no layouts yet |
| `GameData/Field/*` (133 files, one sheet each) | same shape, round trip OK, not registered (field settings: camera, light and so on, mostly floats) |
| `GameData/Field/Btl__UnexploredSea.bin` | **malformed**: its header says 2 rows of 0xBC bytes, the file holds one (and the other Field files use 0xC4 rows). Looks like an unused leftover; refused, not rebuilt |
| `map/config/*` (118 files) | same shape, round trip OK, not registered (per-map settings) |
| `talk/call.bin`, `talk/RelianceTalkBGM.bin`, `TextureCoordinate.bin` | same shape, round trip OK, not registered |

Castle files that are **not** this shape (plain IS `.bin` without `MOD_` blocks):
`castle/castle_building.bin.lz` (labelled `KID_` building records), `castle_food`,
`castle_gemstone`, `castle_init_buildings`, `castle_join`, `castle_lilith` (`.bin.lz`, no
labels), and `GameData/Castle/Seq_DiningCooking.bin`, `Seq_JailPrevail.bin`. They belong
with the ordinary table tools (docs/TABLES.md) and are not done yet.

## Checking Grok's notes (docs/tracks/formats/CASTLE_SHEETS.md)

| Note | Found in the files and code |
|---|---|
| Ordinary IS `.bin`, not a new container | **right** |
| Three lists: mod list, data table, `SHEET_LIST` | **right**; there is one mod list + table per sheet, and `SHEET_LIST` once per file |
| 12 undecoded bytes per field | **right**; they are three floats the loader does not read |
| "No file uses a label that starts with `DAT_`" [gap] | **closed**: every sheet labels its rows `DAT_<name>` |
| The table header: label, name, count, two unknown bytes | **refined**: name, u16 count, **u16 row size** (checked by the loader against the code), rows pointer |
| JobIntro, AcceShop, CastlePerson one sheet; DiningData two | **right** |
| `castle_building.bin.lz` is a plain row list | **right** (no `MOD_` blocks) |
| `MyRoom` and `Fortune` unnamed [gap] | **closed**: `GameData/MyRoom.bin.lz` and `GameData/Fortune.bin.lz` exist and have this shape |
| Butler, CastleButlerVoice, CastlePosition "not opened" | all three have this shape and are editable here |

No Paragon type file or code was used: the layouts come from each file's own declaration,
the data and the game's code.

## Tests

`python tools/castle/test_castle.py` (16 tests, about 1 second; skipped without
`extracted/romfs`):

- every layout passes `check`; broken layouts (two fields merged, a string typed as a
  number, list items of the wrong size) are caught; the layouts hold no game text;
- every registered file rebuilds byte-identical through CSV text, and through real files
  with the command line (`dump`, `build --check`);
- one-cell edits in five sheets and a negative stat change exactly the edited bytes of
  the decompressed file; a string edit in a JobIntro list item changes only that cell;
- one and two dishes and one cooking title added: the count rises, the new row decodes to
  the spreadsheet and resolves by its label, every other row and sheet is unchanged (the
  dish sheet moves behind a new title), the result passes `check` and rebuilds itself;
- refused: a new accessory (fixed 256-entry save array), a new row without a label or with
  a used label, wrong numbering, a removed row, a renamed label, a changed list count, an
  added list item, changed columns, a new JobIntro group;
- a sample of other sheet files round-trips; the malformed Field file is refused.

## Not done

- Nothing seen in the game yet (dining: eat a dish you changed and look at the stat).
- List items can be edited, not added; JobIntro groups therefore cannot be added.
- The other same-shape files (effects, fields, map config, Live2D, talk) have no layouts.
- The plain castle files (buildings, joins, food, gemstones) are still to do.
