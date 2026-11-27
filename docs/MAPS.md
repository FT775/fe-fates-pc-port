# Maps: unit placement and terrain

**In plain words.** Every battle map of Fates is two small files: one says *who stands
where* (the "Dispos" file: the characters, their class, level, items, skills and how the
computer plays them, for every group of units such as the player's starting places, the
enemies and each wave of reinforcements), the other says *what the ground is* (the
"Terrain" file: a grid of tile numbers and the list of tile types with their defence,
avoid and healing). The map tool turns both into spreadsheets plus a coloured picture,
checks your edits against what the game's own code accepts, and turns them back into
game files. An unedited map comes back byte for byte identical (all 185 placement files
and all 109 terrain files are checked).

Status (2026-11-10): the tool works and its 16 tests pass. **No map edit has been seen in
the game yet**; the rules below come from reading the game's code. Putting the rebuilt
files into a mod is the mods tool's job (not wired yet).

Confidence tags as in the plan: **[high]** read in the code and checked by a script or
test, **[med]** good evidence, **[low]** a guess. Addresses are from
`config/functions.csv` (the game's own symbol map).

## Quick start: move an enemy

```
python tools/maps/maps.py list                 every map and its files
python tools/maps/maps.py export A007          writes build/maps/A007/
#   open build/maps/A007/preview.png to see the map with its units and coordinates
#   open build/maps/A007/units.csv in a spreadsheet, change x and y of one enemy,
#   save as "CSV UTF-8 (Comma delimited)"
python tools/maps/maps.py check A007           says what is wrong, if anything
python tools/maps/maps.py build A007           writes build/maps/rebuilt/GameData/...
```

The rebuilt files keep their RomFS paths under `build/maps/rebuilt/`, so they can be used
as file overrides like the table tool's output. Everything under `build/` is your own
game data and is never put in git.

## What a map package holds

`python tools/maps/maps.py export NAME` writes `build/maps/NAME/` (`--all` for every map,
about 30 seconds; it refuses to overwrite a package you already edited unless you add
`--force`):

| File | What it is | Editable |
|---|---|---|
| `units.csv` | one row per placed unit, every group, every difficulty | yes |
| `terrain.csv` | the tile grid: one row per y, one column per x, each cell a tile number | yes (only in the package that owns the terrain) |
| `tiles.csv` | the tile types of this map (defence, avoid, heal, movement-cost column ...) | yes, no new rows |
| `map.csv` | size, playable area, map model | no (read only) |
| `preview.png` | our own drawing: a square per tile, coloured by tile type (dark = nobody can walk there), the playable area outlined in white, unit markers (blue player, red enemy, green ally; hollow = reinforcements), coordinates along the top and left | - |
| `about.txt` | a short version of this page | - |

Map names are the file names: `A007` is `GameData/Dispos/A/A007.bin.lz` plus
`GameData/Terrain/A007.bin.lz`. A, B, C are Birthright, Conquest, Revelation
(docs/ROUTES.md); maps used by every route sit in `GameData/Dispos/` without a route
folder. Names ending in **E** are the *encounter* version of a map (the random battles on
a cleared map: groups `Player`, `Mob00`, `Mob01`, loaded by `Scripts/Encount.cmb` through
`ev::ChapterGetEncountName`) and names ending in **V** are *versus* maps (groups
`PlayerFirst`, `PlayerSecond`, `PlayerRandom`). They stand on their chapter's terrain, so
their package has units only; edit the ground in the chapter's own package. A few
placement files (`AY01`..`CY03`, `Z001`) have no terrain file of their name: their
positions are not checked. The six castle terrain files (`CASTLE0`..`CASTLE5`) have no
placement file of their own name: their package has terrain only (`CASTLE0V`, a versus
map, stands on `CASTLE0`).

### units.csv columns

| Column | Meaning |
|---|---|
| `group`, `slot` | which unit this row is: the group name and the place in that group (0, 1, 2 ...). Do not change them for existing rows. |
| `pid` | the character (`PID_...`). `name` next to it is the English name, for reading only. |
| `jid` | the class (`JID_...`); empty = the character's own class. `class_name` is for reading only. |
| `side` | `player`, `enemy` or `ally` (the game's army number 0, 1, 2) |
| `level` | 0 = the character's own level |
| `x`, `y` | where the unit stands (0,0 = top left; see the picture) |
| `start_x`, `start_y` | must be on the map; usually the same as x, y (where it differs the unit seems to appear there first [low]) |
| `normal`, `hard`, `lunatic` | 1 = the unit is on the map in that difficulty, 0 = not |
| `other_flags` | the rest of the unit's flag word, as a hex number (see "Flags") |
| `item_1` .. `item_5` | items (`IID_...`), with `item_N_flags` and `item_N_forge.normal/hard/lunatic` (forge level per difficulty; negative = the item is not given on that difficulty) |
| `skill_1` .. `skill_5`, `skill_flags` | skills (`SEID_...`) |
| `ai_*`, `ai_params.0-9`, `ai_flags` | how the computer plays the unit (`AI_AC_`, `AI_MI_`, `AI_AT_`, `AI_MV_` with parameters) |
| `sortie_flag` | keep 0 (the game writes into it while the map runs) |

The meaning, confidence and evidence of every field are in docs/TABLES.md (DisposUnit,
TerrainTile, TerrainGrid).

## What you can change (and how sure we are)

| Edit | Allowed | Why [confidence] |
|---|---|---|
| Move a unit | yes, checked | `map::Dispos::Data::IsEnable` 005278DC reads the position each time the group is placed; the file is used in place, no copy elsewhere [high] |
| Change class, level, items, skills, AI, side | yes, IDs checked | `Unit::CreateFromDispos` 003D60D8, `Unit::SetDisposItem` 003D8C38 and `Unit::SetDispos` 003D92FC read them from the record when the unit is made [high]; what each AI value does is not traced [low] |
| Take a unit off the map | set `normal`, `hard`, `lunatic` to 0 | rows are never deleted (project rule); a unit with no difficulty bit is never placed (IsEnable) [high] |
| Change a tile | yes, checked | `map::Image::Update` 0038F96C copies the file's grid into the running map every time it is built [high] |
| Change a tile type (defence, avoid, heal, movement column) | yes, checked | read through `Terrain::Get(int)` 004E0AFC from the file in place [high] |
| **Add a unit to an existing group** | **yes, with limits** (next section) | no fixed-size array anywhere on the path; the limits are the game's own army caps [high] |
| Add a new group | refused | the chapter script (`Scripts/*.cmb`) calls groups by name (`ev::Dispos "Reinforce01"`), so a new group is never placed without a script change [high] |
| Add a tile type | refused | the tile count and the `change_to` links are per map and nobody has reviewed what else counts tiles [med] |
| Change the map size or playable area | refused | the 3D map model and camera are fixed per map; the grid is a fixed 32 x 32 (below) [high for the grid, med for the model] |

### Adding units: the decision and its evidence

Add a unit by copying a row of the group to the end of `units.csv` and writing `new` in
its `slot` cell (or the next number). The tool inserts the record at the end of that
group, moves every later group by one record and raises the group's count.

Why it is safe [high]:

1. `map::Dispos::Load` 0039ED9C loads the whole file into a heap buffer of its own size
   and keeps a pointer to its data; nothing is copied into a fixed table.
2. `map::Dispos::CreateProcess` 0039DB78 finds a group by comparing names along the
   12-byte group list until a null name: any number of groups works.
3. `map::Dispos::Calculate` 0039EF34 walks `unit_count` records from `first_unit`
   (record = first + i x 0x8C) and allocates its shuffle list on the heap
   (`count x 4` bytes). No loop has a constant bound.
4. Units come from a pool: `UnitPool::Initialize` 004F5ABC makes 250 units, and
   `Dispos::Data::GetUnit` 0039E43C takes a free one (army 9 holds the free units) and
   returns "no unit" when none is left. It also creates **no unit once that army
   already holds 50** (`Force::GetCount() >= 50`). Deployment slots are capped by
   `map::SortiePosition::AddData` 00361690 (`count < max`). So too many units are left
   out quietly, never written past an array.
5. A suspended game stores only the Dispos file *name* (`map::Dispos::Serialize`
   0044BC64 / `Deserialize` 0039DB10 reload the file by name): no save holds a unit
   index.

The tool therefore allows adding units, and refuses:

- a group that would place more than **50 units of one side on one difficulty**
  (the game would drop the extra ones; untouched game groups that already exceed it,
  such as a 60-slot player group, are left alone);
- a **Mob** group (encounter maps): those units are rewritten at random by
  `spot::Mob::CreateDisposUnit` 00417B3C / `CreateDisposUnitMonster` 00417B80, which
  nobody has read yet [med];
- **versus** maps (V): both players' placements are matched by the versus code
  (`ChapterSequence ... VersusDisposNormalOne` 001DB4D8), not reviewed [med];
- a group whose last unit has the paired flag (0x10000): the new unit would become its
  partner (`Calculate` pairs unit i with unit i+1 through `Unit::DoubleOn`) [high].

Over all groups, a map may place more than 50 units of one side (reinforcements come in
waves and the dead free their place); the tool warns about it.

## Difficulty versions

There are no separate files per difficulty. Every unit row carries three bits in its
flag word: `map::Dispos::Data::IsEnable` 005278DC reads the difficulty
(`GameUserData+0x2D`: 0 Normal, 1 Hard, 2 Lunatic, the byte the script command
`DifficultyGet` returns) and uses the unit only if flag bit 0x100 (Normal), 0x200 (Hard)
or 0x400 (Lunatic) is set [high]. Harder modes are made of extra rows that only have the
Hard or Lunatic bit, and of items whose forge level is negative on easier modes
(`Unit::SetDisposItem` reads `item_N_forge[difficulty]`) [high]. `units.csv` shows the
three bits as the `normal`, `hard`, `lunatic` columns.

## Reinforcements and turns

A Dispos file has **no turn field** [high: no field of the 0x8C-byte record is read as a
turn by the placement code]. Reinforcements are separate groups (`Reinforce01`,
`Reinforce02_1` ...), and *when* a group appears is decided by the chapter's script
(`Scripts/<route>/<chapter>.cmb`, which calls `ev::Dispos` with the group name at its
turn conditions). So you can change who arrives and where, but not on which turn; that
needs a script edit, which this tool does not do. `start_x`, `start_y` must be on the map
(IsEnable) and differ from `x`, `y` in about one unit in nine; that they mark where an
arriving unit walks in from is likely but not traced [low].

## Map size limits

- The grid in the file and in memory is a fixed **32 x 32**: `map::Image::Update`
  0038F96C copies the file's 1,024 tile bytes to the running map and every reader
  computes the tile as `x | y << 5` (`map::Dispos::Calculate`, IsEnable). The six sizes
  are copied into single bytes. So no map is larger than 32 x 32 [high]; the game's maps
  range from 15 to 32 in each direction.
- Units must stand in the **playable area**: from `play_x_min`, `play_y_min` (1 in every
  map) up to but not including `play_x_end`, `play_y_end` (the size minus 1 in every
  map), unless their flag word has 0x8000, which allows the whole map (IsEnable, the
  deployment slots in `SortiePosition::AddData` use the same box) [high]. Outside it,
  the game silently leaves the unit out.
- These sizes were named `border_width` / `inner_width` in the first table layouts; the
  code shows they are the edges of the playable area, so TerrainGrid now calls them
  `play_x_min`, `play_y_min`, `play_x_end`, `play_y_end` (docs/TABLES.md).

## Flags (the unit's flag word)

| Bit | Meaning | Where | Conf. |
|---|---|---|---|
| 0x100, 0x200, 0x400 | on Normal / Hard / Lunatic | IsEnable 005278DC | high |
| 0x8000 | may stand outside the playable area (anywhere on the map) | IsEnable | high |
| 0x1 | left out when its tile is already taken | IsEnable | high |
| 0x10000 | the next unit of the group is its pair partner | Calculate 0039EF34 -> `Unit::DoubleOn` | high |
| 0x40 | never created by `Dispos::Data::GetUnit` | GetUnit 0039E43C | med |
| 0x4..0x40 (0x7C) without 0x44, on a player unit | a deployment slot | Calculate -> `SortiePosition::AddData` | high |
| others | not traced | - | - |

## Checks the tool makes

On `check` and `build`, for every new or changed row (errors stop the build; nothing is
written):

- `x`, `y` inside the playable area (or the map, with flag 0x8000), `start_x`, `start_y`
  on the map; `255,255` (= -1 to the game) is accepted as "off the map", as the game's
  own support partners use it;
- the unit's tile is walkable for its class: the TerrainCost row of the class's
  `move_cost_class` at the tile's `move_cost_column` must not be negative
  (`TerrainCost::GetCostFromUnit` 001A6708). `--lenient` turns this into a warning, for
  doors and walls that a map event opens. For a deployment slot the rule is the game's
  own: column not 0 and tile attribute 0x8 not set. Mob units are not checked (their
  class is picked at random);
- the character exists: in the resident people or the per-chapter Person file the game
  loads with this map (route folder first, then the shared one); found only in another
  chapter's file = a warning (the game itself has such units);
- every `JID_`, `IID_`, `SEID_` exists in the game's tables, or in the rows a mod adds or
  changes: `--tables DIR` reads `Item.csv`, `Job.csv`, `Skill.csv` from that folder (a
  mod's `tables/` folder), so a new item from a mod can be given to an enemy;
- numbers fit their bytes; the side is 0-2; `sortie_flag` stays 0; no row deleted; no new
  group; group and slot cells name an existing unit.

For tiles: every grid cell names a tile of the same map, the grid keeps its size, tile
numbers and IDs stay, the movement-cost column is one the cost table has (0-15),
`change_to` names a tile of the same map, and `map.csv` is unchanged.

Rows nobody changed are not second-guessed: the game's own maps have units on doors and
walls that open later, characters taken from another chapter's file, and support
partners at 255,255. Those are counted as *notes* (`-v` lists them), never errors.

## How it works inside

- Decoding and encoding use the table layouts and tools (tools/tables/tablelib.py,
  tools/tables/build.py), unchanged. `units.csv` is the DisposUnit spreadsheet with
  readable column names, the flag word split into the three difficulty columns, and
  the groups shown per row instead of `first_unit` / `unit_count`.
- An unedited package rebuilds through the same path as the table tool, so the file is
  byte-identical (string pool, relocation order and LZ13 compression all kept).
- Adding units opens a gap of 0x8C bytes per unit at the end of the group; every
  pointer and relocation behind it moves, strings are pooled again with the game's
  rule, and the result is compressed like the original. Dispos files have no labels and
  no empty groups (checked when a file is read), which keeps this simple.
- Rebuilt files are written atomically (a temporary file, then a rename).

## Tests

`python tools/maps/test_maps.py` (16 tests, about 6 seconds): all 185 + 109 files round
trip in memory and one map through real files; one enemy moved -> only its two position
bytes change; one unit added -> the group grows by one, everything else decodes the
same; adding to a Mob group or a versus map is refused; a position outside the map, a
start position off the map, a moved unit on an unwalkable tile (and `--lenient`), a
deleted row, a new group and an unknown item are refused, and an item a mod adds is
accepted; one terrain tile changed -> only that grid byte changes; a bad tile number and
a size change are refused; the preview is a valid PNG of the right size.
`python tools/maps/maps.py roundtrip` repeats the whole-game round trip on its own.

## Not done yet

- Nothing seen in the game. The first owner check, once the mods tool can install map
  files: move one enemy in Chapter 7 of Birthright (`A007`) two tiles and look.
- The mods tool does not package map edits yet (the integrate stage wires
  `build/maps/rebuilt/` into mods).
- Turn timing of reinforcements (scripts), what each AI value does, the Mob and versus
  code, and the remaining flag bits are not traced.

## Where the facts came from

The owner's own dump: code.bin (read with the Arm GNU objdump at the addresses above)
and the RomFS files. The field names Paragon's FE14 definitions use are cited in the
table layouts as facts only; no community code was used or copied.
