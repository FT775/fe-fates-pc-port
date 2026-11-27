# Data tables (Fire Emblem Fates)

The game's characters, classes, items, skills, chapters, terrain, map placements and the
rule tables (weapon triangle, weapon ranks, forging, experience, movement costs, boons and
banes, arena, achievement rewards, tutorials) live in
IS ".bin" containers in the RomFS (`GameData/...`, LZ13-compressed). This page explains how
the port finds them, what every field means, how sure we are, and how to edit them.

Everything here is about **layouts** (offsets, sizes, types, names). The values themselves
are Nintendo's data: they only ever appear in your own `extracted/` and `build/` folders,
which git ignores.

## Quick start: change a character's strength

```
python tools/tables/dump.py Person            # writes build/tables/Person.csv
#   open it in a spreadsheet, change base.str of one row, save as CSV (UTF-8)
python tools/tables/check.py Person           # the layout still matches the game
python tools/tables/build.py                  # writes build/tables/rebuilt/GameData/GameData.bin.lz
```

`build.py` writes every rebuilt file under `build/tables/rebuilt/` with its RomFS path, ready
to be used as a LayeredFS-style override (the mods tool, `tools/mods/`, packages these).
An unedited dump always rebuilds to the identical original file, byte for byte; that is
checked for all 412 table files by `python tools/tables/build.py --check --no-write`.

## The tools

| Command | What it does |
|---|---|
| `python tools/tables/dump.py [TABLE ...]` | Writes `build/tables/<TABLE>.csv` (UTF-8 with BOM, so Excel shows the Japanese IDs) for every table, or the ones named. |
| `python tools/tables/build.py [--check] [--no-write] [--edit-test] [--out DIR]` | Rebuilds every file that holds a table from the CSVs. `--check`: compare with the originals (exit 1 on a difference). `--edit-test`: edit a few cells in memory and prove the rebuilt file decodes to exactly that edit. |
| `python tools/tables/check.py [TABLE ...] [--selftest] [--stats TABLE]` | Validates every layout against every record (see below). `--selftest` also breaks each layout on purpose and requires the check to notice. `--stats` prints per-field value ranges to the console. |
| `python tools/tables/evidence.py REGEX` / `--fields TABLE` | Code evidence: which offsets the game's named functions load (see "How the layouts were derived"). |
| `python tools/tables/evidence.py --bitsets [LO:HI]` | The fixed-array scan: every `cmp Rn, #N` followed by a byte access `[base, Rn, asr #3]` (a bit set or byte array of N entries indexed by a bounded number). Decides whether a table may grow (see "Adding records"). |
| `python tools/tables/gen.py doc` / `structs` / `check` | Regenerates the field tables at the bottom of this page and `config/tables/structs.h.txt` (C structs with offset asserts), or checks they are current. |
| `python tools/tables/test_tables.py` | The test suite (19 tests, see "Tests"). |

## Cells in the CSV

The first columns are `file` (only for tables spread over many files: PersonChapter,
Terrain*, Dispos*), `index` (record number in its file) and `label` (the record's ID, e.g.
`PID_プレイヤー男`; empty for Dispos units, which have no labels). Then one column per field;
arrays get one column per element (`base.hp`, `base.str`, ...).

| Field type | How the cell looks | Editing |
|---|---|---|
| integers | decimal, signed where the layout says so | any number that fits the width |
| `str` | the text (`MPID_...`, `IID_...`); empty = no pointer; `""` = empty string | any text; the string pool is rebuilt with the game's own rules |
| `str:self` | the record's own ID (equals `label`) | renaming an ID also renames nothing else: change references too |
| `refN:TABLE` | the target's label (`JID_パラディン男`), or a number (tables without labels, such as ItemRefine or TerrainCost, always show numbers), `none` = all-ones | a label of that table or a number |
| `flagsN:IDLIST` | set bits as names joined by `\|` (`SPID_女性\|SPID_プレイヤー`), unknown bits as `bitN` | add/remove names |
| `ptr:TABLE` | target label, or `#N` = record N of TABLE in the same file | a label or `#N` |
| `ptr` | `@0xOFFSET` inside the container | leave alone unless you know the data |
| `hex[n]` | the bytes as hex (the 32x32 terrain grid) | same length |

Records are never removed (the build refuses fewer rows than the file has). Records may
be **added at the end** of Item and Job (rows numbered past the last one; see "Adding
records" below); every other table refuses a new row with the reason. For the tables with
no stored count (registry count `fixed:N` or `one`: ItemKind, ItemSubKind, ItemRefine,
WeaponLevel, WeaponBonus, WeaponInteract, the Exp* tables, TerrainCost, GameDataUnknown50)
the refusal is permanent: the game indexes them with sizes fixed in code (WeaponBonus::Get
is only called for kinds below 8, the Exp* rows are one per difficulty, TerrainCost rows
are `Job.move_cost_class`), and the refusal message says so.

## How the tables are found

Fates' `GameData.bin` has no `PersonData`-style table labels (Awakening has them). Instead
its data region starts with a 0x64-byte header of pointers and counts. The game's own loader
shows what each word is: `GameData::Initialize` (004E6954) reads the header and hands each
word to the table's initializer:

Every header slot and its status:

| Header | Goes to | Table(s) | Status |
|---|---|---|---|
| +0x00, +0x04 | `Chapter::Initialize(const void*, int)` | Chapter | typed |
| +0x08 | `Person::Initialize(const void*)` | Person block (16-byte header, then records) | records typed; the block header and the support (Reliance) data its +0x8 points at are not |
| +0x0C | `Job::Initialize(const void*)` | Job block (8-byte header, then records) | records typed (the JobCategory and PersonFlag ID lists follow them) |
| +0x10, +0x14, +0x18 | `EquipSkill::Initialize(const void*, int, int)` | Skill, common count, total count | typed |
| +0x1C, +0x20 | `Personality::Initialize(const void*, int)` | Personality (boons/banes) | typed |
| +0x24, +0x28 | `Belong::Initialize(const void*, int)` | Belong | typed |
| +0x2C | `Item::Initialize(const void*)` | Item block (8-byte header, then records) | records typed (the ItemFlag and ItemUse ID lists follow ItemSubKind) |
| +0x30 | `ItemKind::Initialize(const void*)` | ItemKind | typed |
| +0x34 | `ItemSubKind::Initialize(const void*)` | ItemSubKind | typed |
| +0x38 | `ItemRefine::Initialize(const void*)` | ItemRefine (forging) | typed |
| +0x3C | `WeaponLevel::Initialize(const void*)` | WeaponLevel | typed |
| +0x40 | `WeaponBonus::Initialize(const void*)` | WeaponBonus | typed |
| +0x44 | `WeaponInteract::Initialize(const void*)` | WeaponInteract (weapon triangle) | typed |
| +0x48 | `ExpTable::Initialize(const void*)` | ExpTableHeader -> ExpBattle, ExpBattleFloor, ExpRod, ExpRodHigh, ExpDance, ExpSupport | typed |
| +0x4C | `TerrainCost::Initialize(const void*)` | TerrainCostHeader, TerrainCost | typed |
| +0x50 | nothing (GameData::Initialize skips it; no other reader found) | GameDataUnknown50 | typed as raw 4-byte entries, low confidence |
| +0x54, +0x58 | `Tutorial::Initialize(const void*, int)` | Tutorial | typed |
| +0x5C | `AchieveBonus::Initialize(const void*)` | AchieveBonusHeader -> AchieveBonusRoute, AchieveBonusBattle, AchieveBonusVisit, AchieveBonusList4 | typed |
| +0x60 | `Arena::Initialize(const void*)` | ArenaHeader -> ArenaLow, ArenaHigh | typed |

Every byte of the GameData data region now belongs to a typed table except the Person,
Job and Item block headers, the stance bonus blocks and support lists after the Person
records, 16 bytes right after the Item records (not read by any layout yet), and zero
bytes that align blocks to 8 (after Chapter and after ExpSupport).

The tables the header points at directly have no labels and, for half of them, no stored
count: their record counts are `fixed:N` in the registry, taken from the code's own
indexing (ItemRefine::Get(row, level) = table + (row*10 + level)*4, WeaponBonus::Get(kind)
= table + kind*0xC, ...) and proven against the file by check.py (see "Checks"). The
ExpTable, AchieveBonus and Arena headers point at sub-tables; those are separate registry
tables whose start is a nested address (`[[0x48]+0x4]` = the second pointer of the
ExpTable header).

The "block" tables (Person, Job, Item) are archives the game can also load from other files:
a small header (archive name such as `resident`, record count, a resident flag) followed by
the records. `Person::Get(unsigned short)` computes `block + 0x10 + index * 0x98`, which is
where the `[0x8]+0x10` start in `config/tables/tables.csv` comes from. Every per-chapter
`GameData/Person/{,A/,B/,C/}*.bin.lz` file is one such Person block at data offset 0.

The registry (`config/tables/tables.csv`) says, per table, which file(s), where record 0
is and how many records there are, as small address expressions: `[0x8]+0x10` = "the
pointer stored at 0x8, plus 0x10", `u16@[0x8]+0x4` = "the 16-bit count at that block's
+4". `tools/tables/tablelib.py` documents the full syntax. The IS .bin pointer model
(relocation table + string pool, `tools/assets/isbin.py`) is used unchanged, so pointers
and strings stay consistent when strings change length.

Other files:

- **Terrain** (`GameData/Terrain/*.bin.lz`, one per chapter): a 16-byte header (tile table,
  tile count, map model name, grid pointer), the TID_ tile records (0x28 each), and a 0x418
  grid (six sizes, then 32x32 tile numbers) that ends every file.
- **Dispos** (`GameData/Dispos/{,A/,B/,C/}*.bin.lz`, one per chapter or variant): a list of
  unit groups `{name, first unit, count}` ended by an all-zero entry, then all units (0x8C
  each). Groups are contiguous in all 185 files, so DisposUnit is simply "every unit after
  the list". To move a unit between groups, change the groups' `first_unit` / `unit_count`.

## Route letters

File names use A, B and C. In `config/game.json` (and here) A = Birthright, B = Conquest,
C = Revelation, with A000-A005 plus the route choice `CID_P006` the shared prologue
(chapter 6 is per route: `CID_A006`, `CID_B006`, `CID_C006`). The mapping is confirmed in
code (docs/ROUTES.md, `python tools/fates/routes.py`): the route byte GameUserData+0x2E
is 0/1/2 = A/B/C. Chapter.route_mask uses the same bit order (1 = A, 2 = B, 4 = C,
7 = all; Spot::Rebuild tests `route_mask & (1 << route)`), and Chapter.next_chapter /
required_chapter are indexed by the route byte (ChapterComplete, Spot::Rebuild).

## How the layouts were derived, and what "confidence" means

1. **The game's symbol map.** The RomFS ships `debug/name.StackTrace` and
   `debug/addr.StackTrace`: 26,122 real function names (`Person::GetHelp(void) const`,
   `Unit::GetGrow(int) const` ...). `tools/tables/evidence.py` decodes the ARM code of each
   named function and lists the offsets it loads from its arguments, following pointer
   fields (`arg0+0x9C->+0x40[i]:s8` = "the unit's Person record, byte array at +0x40") and
   the results of lookup functions (`Item::Get(unsigned short)` returns an Item record).
   `config/tables/slots.csv` names the object slots this needs (Unit+0x9C = Person,
   Unit+0xA0 = Job, the Dispos::Data argument = a Dispos unit, the Person and Job
   arguments of `Unit::CreateImpl`). A unit's carried item (`unit::Item::ToData`) is
   followed to its Item record. The walk is linear; it also follows a conditional word
   load into an empty register and an `addeq`/`addne` pair (Unit::GetGrow picks
   Job+0x24 or Job+0x2C that way), but reads behind a branch it walked past are missed,
   so the evidence column cites the disassembly where the tool cannot see a read.
2. **Data patterns** over every record (`check.py --stats`): which bytes are always zero,
   which are relocated pointers, value ranges, IDs equal to the record index.
3. **Community field maps, as facts only.** Paragon's FE14 type definitions (GPL-3.0) were
   read to cross-check names and offsets; no code or text was copied. Where a field's name
   comes from there, its evidence says "Paragon ... (fact)".

| Confidence | Meaning |
|---|---|
| high | A named game function reads exactly this offset with this width for this purpose (e.g. `Unit::GetStrImpl` reads Person+0x39), or the data proves it (an ID string equal to the record label, a pointer relocated in every record). |
| medium | The game reads the offset, but the meaning comes from data patterns or the community map; or the meaning is clear from data but no read was found. |
| low | Name from the community map or a guess from values; nothing in the code confirms it yet. Editing works the same; the effect in game is unverified. |

Findings worth knowing:

- **Growth rates are not obfuscated in Fates** (Awakening scrambled them with a cipher).
  Person+0x40 and Job+0x24 are plain multiples of 5; the player character's row reads as
  the known in-game growths.
- **Character base stats are personal bases added to the class bases**: Person.base is
  added to the class's Job.base (`Unit::GetStrImpl` adds both), so small numbers in
  Person.base are expected. The full formula is in "How a unit's stats are computed"
  below; it reproduces an in-game stat screen exactly.
- **Difficulty-dependent fields** use the difficulty byte GameUserData+0x2D (0 = Normal,
  1 = Hard, 2 = Lunatic; the byte the `DifficultyGet` script command returns):
  Person.normal_mod / lunatic_mod and normal_extra_levels / lunatic_extra_levels (no Hard
  column: Hard uses the record as is), Person.personal_skill[difficulty],
  Person.skill_mask bit (3 x skill + difficulty), DisposUnit.item_N_forge[difficulty]
  (negative = item not given on that difficulty), and one Exp* row per difficulty.
- **Flag words are ID lists.** Person.flags and Job.flags are 64-bit sets whose bit numbers
  are the `SPID_` list (`SPID_女性` = bit 0 ...). Item.flags uses `ISID_`, Job.category uses
  `JCID_`. The game looks a bit up by name (`PrivateSkill::Get("SPID_女性")`) and tests
  `1 << number`; the CSV shows the names.

## How a unit's stats are computed

Followed end to end in the code (addresses from `config/functions.csv`). `s` is one of
the eight stats (hp str mag skl spd lck def res, the element order of every stat array).

**When a unit is created** (`Unit::CreateImpl` 003D3954 calls
`Unit::CaclulateAutoGrowCapability` 00532880), the unit stores a per-stat gain `G[s]`
(Unit+0xC8, signed byte):

```
L    = (Person.unit_kind == 0 ? level - 1 (+19 if the class is promoted) : 0)
       + (Normal: Person.normal_extra_levels | Lunatic: Person.lunatic_extra_levels | Hard: 0)
L    = max(L, 0)
g    = max(0, Person.growth[s] + (Person.unit_kind == 1 ? Job.growth[s] : Job.enemy_growth[s]))
G[s] = round_half_up(g * L / 100)
       + (Normal: Person.normal_mod[s] | Lunatic: Person.lunatic_mod[s] | Hard: 0)
G[s] is lowered so that the capped stat (below) does not pass its limit.
```

So only generic units (unit_kind 0) get level-based automatic stats; named characters
(unit_kind 1, 2, 3) start from their Person.base as written, plus the difficulty columns.
Afterwards `Unit::CreateImpl` may add real level-ups (`CollectiveLevelUpCapability`)
when the scenario rank is above Person.autolevel_rank; every level-up
(`Unit::LevelUp` 003D8154) adds to `G[s]` with the chance `Unit::GetGrow` 005330B4 =
Person.growth (averaged with the parent's for children) + Job.growth (unit_kind 1) or
Job.enemy_growth (others), +10 with one skill.

**When a stat is shown or used** (`Unit::GetStrImpl` 0052A80C; GetMHPImpl, GetPowImpl,
GetTechImpl, GetQuickImpl, GetLuckImpl, GetDefImpl, GetMdefImpl have the same shape):

```
raw    = Person.base[s] + Job.base[s] + G[s]   (+ the avatar's boon/bane edit, unit::Edit)
limit  = Job.max[s] + Person.limit_mod[s]      (+ child and avatar terms; Unit::GetLimit 005337F0, 0..99)
stat   = clamp(raw, 0, limit)
shown  = stat + Item.stat_bonus[s] of the equipped item
              + Item.extra_data[s] of every carried item with a carried-item bonus
                (anonymous_namespace::GetEnhanceHave 0033A790; ISID_所持強化 items)
              + pair-up, skills, rallies and tonics, minus debuffs
shown  = clamp(shown, 0, 99)
```

Checked against an in-game fact: the owner's screenshot of an unmodded unit in the
prologue (Lv 1, unit_kind 3, so `G[s]` = 0 on every difficulty) matches Person.base +
Job.base for HP, Mag, Skl and Lck exactly; Spd, Def and Res differ by exactly the
equipped weapon's Item.stat_bonus, and Str by exactly that weapon's Item.extra_data
carried-item bonus. All eight stats agree (the numbers stay out of this file; they are
game data).

What this means for mods: a Person.base edit moves the stat one for one, but the class
cap is applied before item bonuses, so `Person.base[s] + Job.base[s] + G[s]` above
`Job.max[s] + Person.limit_mod[s]` is cut to the cap (raise limit_mod too for a bigger
change). For generic enemies Person.base also stacks with the automatic gains.

## Layout changes in this revision (re-run dump.py)

These were wrong or too coarse and are fixed; old dumps no longer match and must be
re-dumped (`python tools/tables/dump.py`):

- Person +0x35 `unknown_35` (u8[3]) is now three fields: `autolevel_rank` (u8),
  `normal_extra_levels` (s8), `lunatic_extra_levels` (s8). Person +0x50 / +0x58
  `stat_mod_50` / `stat_mod_58` are renamed `normal_mod` / `lunatic_mod`.
- Item +0x34 `effective_1` / +0x35 `effective_2` (two u8) are one field `effective`
  (flags16:JobCategory): the battle code reads one u16 and tests it against JCID_ bits.
- Item +0x40 `extra_data` is s8[8] with stat element names (was u8[8], numbered).
- Item +0x58 `shop_misc` is renamed `pool_rank`; its element names were wrong (the
  lottery ranks are the last two bytes, not the third and fourth). Item +0x36
  `mov_bonus` is s8. The four stock fields name their elements lv1 / lv2 / lv3.
- Chapter +0x12 / +0x13 are s8 (255 shows as -1).
- DisposUnit `item_N_flags` (u8[4]) is now `item_N_flags` (u8) + `item_N_forge` (s8[3],
  normal / hard / lunatic).

## Checks

`check.py` verifies, for every record of every file:

- the fields tile the record exactly (no gap or overlap);
- pointer fields hold a relocated word or 0, and no other field ever holds a relocation;
- strings decode as clean Shift-JIS; `str:self` IDs equal the record's label;
- `ptr:T` fields point at a record start of T in the same file;
- flags only use bits that exist in their ID list; refs are below the target's count;
- pad bytes are zero;
- cross-table rules: the GameData header counts match the tables and their label counts;
  Dispos groups are contiguous and cover every unit; terrain grids only use tile numbers
  that exist in the same file; the ExpTable, AchieveBonus and Arena sub-tables follow each
  other with nothing in between; TerrainCost rows are as wide as TerrainCostHeader says and
  every terrain file's `move_cost_column` fits; ID numbers (Personality, ItemKind,
  ItemSubKind, Tutorial) equal the record index;
- tables without a stored count (`fixed:N`) are proven against the file: nothing points
  inside them after their first record, and only zero bytes lie between their end and the
  next pointer target or label. A count one too small leaves a non-zero row behind; one
  too large swallows the start of the next table.

`--selftest` mutates every layout (drop a field, read a pointer as an integer, declare a
used field as padding, swap the ID string with its neighbour), gives every `fixed:N` table
the counts N-1 and N+1, and requires every mutation to be rejected (135/135).

## Adding records (new rows)

The first new row is an item; classes work the same way; characters are refused. Which
table may grow is decided in `config/tables/appends.csv` (one row per table: `allow` or
`refuse`, the number field, the label prefix, files whose presence refuses, and the code
evidence). A table that is not listed there is refused, and so is every table spread over
several files (PersonChapter, Dispos, Terrain) and every table without a stored count.

How the game finds the records, read in the code (addresses from `config/functions.csv`):

| Table | How records are counted and numbered | Fixed arrays | Decision |
|---|---|---|---|
| Item | `Item::Get(unsigned short)` 003D0EAC (and TryGet, IsExist) walks the loaded Item archives; one archive holds numbers *first* .. *first*+*count*-1, with *first* = record 0's `item_number` (+0x14, block+0x1C) and *count* = the u16 at block+0x6; the record is block+0x8+(n-*first*)*0x68. `Item::IsDownload` 00528E68 is "number >= the resident archive's count". `Item::Get(const char*)` looks the `IID_` up in the global label dictionary, which `ArchiveConstruct(void*,IdentHash*)` 00165EEC fills from every exported label of the file after applying all its relocations (it loops over the stored counts, so new labels and relocations are taken). Only `ItemEnumerator::Enumerate` also reads the archive list, and it loops to the stored count | none found: saves keep item numbers as u16 (`unit::Item::Serialize` 0044BBB4); the four shop lists (`shop::Data::Serialize` 0053A4F0) are {u16 item, u8, u8} lists with a u8 length each; `evidence.py --bitsets` finds no set sized by the item count | **allow** |
| Job | `Job::Get(unsigned short)` 00341AA4: *first* = record 0's `job_number` (+0x18, block+0x20), *count* = u16 at block+0x6, record = block+0x8+(n-*first*)*0x80; `Job::IsDownload` uses the resident count; only `JobEnumerator::Enumerate` also reads the list | none found | **allow** (not checked in game; a new class has no class-change list entry, model or animation of its own, and its `move_cost_class` must name an existing TerrainCost row) |
| Person | `Person::Get(unsigned short)` 0044A6F8: the same scheme (*first* = +0x24, *count* = u16 at block+0x4); the resident archive already holds 255 people (0..254) | `GameProfile::UpdateReliance` 0019B274 keeps a **256-bit set** on the stack indexed by person number (`cmp number, #256`; `ldrb [sp, number asr #3]`) | **refuse** |
| PersonChapter | every per-chapter archive numbers its people from 0x7A00 and is loaded alone | not reviewed | refuse |
| Skill | two counts in the GameData header (+0x14 common, +0x18 total); skills are also bits of Person.skill_mask | not reviewed | refuse |

Caveat for Item and Job: download archives (`GameData/Item/%s.bin.lz`, `GameData/Job/%s.bin.lz`,
loaded by `Item::Load` / `Job::Load`) number their records from the resident count too, so
a new resident record takes a number such an archive would use. The cartridge has no such
files (the build refuses appends while one exists in the RomFS, `refuse_if_files`); item
or class DLC must not be used together with a mod that adds items or classes.

What the build does (`tools/tables/tablelib.py` `append_records`, called by
`build.py build_file` when a table has more rows than the file):

1. checks the policy, then each new row: numbered *count*, *count*+1, ... in order; a new
   label with the table's prefix (`IID_`, `JID_`) that the file does not have; the own-ID
   cell (`iid`, `jid`) equal to the label; the number field (`item_number`, `job_number`)
   equal to the first record's number + the index;
2. opens a gap of n x record size zero bytes after the last record (`insert_bytes`): every
   relocated pointer to that place or beyond, every relocation position and every label
   offset at or beyond it moves; the strings are re-pooled with the game's rule; the
   relocation order is kept, new pointers go last; the new labels go into the label table
   in offset order (the tables keep their labels sorted by offset). Raw offsets shown as
   `@0x...` cells move with it (`build.py shift_cells`). Insertions must keep the 8-byte
   alignment of what follows (0x68 and 0x80 do);
3. raises the stored count (the u16 at block+0x6), then writes every row, the new ones
   included, through the layout as usual.

Files without new rows are rebuilt exactly as before (all 412 still byte-identical). The
tests decompress the result and check that the count is one higher, the new record
resolves by its label and decodes to exactly the row, every other table in the file
decodes unchanged (raw offsets moved) and check.py passes on the grown file.

New rows need text: their name and help IDs (`MIID_...`, `MIID_H_...`) are message labels.
The mods tool lets a mod give text for labels the game does not have, in the name archive
`m/@E/GameData.bin.lz`, only when a row the same mod adds names them (docs/MODDING.md
section 6). The ID lists (ISID_, IUID_ ...) do not need new entries for this: a new item
uses the existing flag and effect names.

## Tests

`python tools/tables/test_tables.py` (needs your `extracted/`):

- one Person stat cell (`base.str` of record 1) edited, `GameData.bin.lz` rebuilt and
  decompressed: exactly one byte differs, at the expected offset, holding the new value;
  the same for a growth, a per-chapter Person file and a Dispos unit position;
- the same one-byte proof for the rule tables: a weapon-triangle cell, a boon growth, a
  battle-experience cell, a movement cost and a weapon-rank bonus;
- multi-cell edits (a string, a class reference, a promotion, an item string, an arena
  entry's class and weapon, a tutorial message ID) decode back to exactly the edit, and
  every other table in the file is unchanged;
- a row added to a table without a stored count is refused with the reason; every
  `fixed:N` count passes and N-1 / N+1 are rejected;
- an Item and a Job appended to GameData.bin: count +1, the new record resolves by its
  label and decodes to exactly the row, every other table unchanged, check.py passes;
  Person (the 256-person bit set), an unlisted table, a planted policy that names a fixed
  array, a matching `refuse_if_files`, a wrong record number, a reused label, a gap in
  the numbering and a deleted row are all refused; the fixed-array scan finds
  `GameProfile::UpdateReliance`'s 256-entry set;
- the GameData header points at every new table, and arena / achievement references
  decode as `JID_` / `IID_` labels;
- all 412 table files rebuild byte-identical from an unedited dump;
- every layout passes, and the self-test rejects all mutations;
- CSV write/read keeps every cell; `#N` references and IDs survive;
- the evidence decoder's self-test, and that it still finds the reads the layouts cite,
  including reads through the sub-table getters (`ExpTable::GetBattle`, `ItemRefine::Get`).

## Cross-check with docs/tracks/rules/RULES.md

RULES.md is Grok's sheet of public rules (wikis, guides). Where it and a layout touch:

- **Weapon triangle: agrees.** WeaponInteract's 8x8 matrix encodes exactly the three
  pairs RULES.md lists (sword and tome beat axe and bow; axe and bow beat lance and
  dagger; lance and dagger beat sword and tome; partners neutral; staff and special
  neutral to everything), and the rank-scaled bonus (damage and hit by the attacker's
  rank, D and E equal) has the same shape and the same numbers as its rank table. The
  code multiplies the bonus by +1 / -1 (BattleInfo::Side::CalculateDetailHit / Attack),
  so advantage and disadvantage are symmetric, as the sheet says. The "dual weapon
  reverses" line is not in these tables (it would be an item flag or a skill); not checked.
- **Boon and bane: agrees.** Personality has separate boon and bane rows for base,
  growth and maximum, and unit::Edit::GetGrow adds the boon and the bane growth to the
  unit's growth, as RULES.md says ("the modifiers are added together").
- **Experience: no oracle.** RULES.md has no experience formula for this game ([gap]).
  The code's shape is now laid out: battle experience is a table lookup by level
  difference (-10..+23) with a floor for high-level enemies, one row per difficulty;
  staff experience is the staff's own Item.staff_exp plus a level row, a penalty row for
  classes that also use other weapons, and a level-gap row. Nothing to agree or disagree
  with yet.
- **Routes:** RULES.md says Birthright can train and Conquest cannot; the arena tables
  are route-independent (two opponent lists chosen by a level threshold), so they say
  nothing about which route offers the arena.

## Not done yet

- In GameData.bin: the Person/Job/Item block headers, the stance bonus blocks
  Person.attack_stance_bonus / guard_stance_bonus point to, and the support (Reliance)
  lists the Person block header's +0x8 points to (variable-length; next step).
- What GameDataUnknown50 is (nothing reads header +0x50); what AchieveBonusList4 is for
  (no named getter); the meaning of ItemRefine's level byte and Personality.dual_stats.
- The other GameData files (AIData, Castle/, Field/, MyRoom, Fortune, JobIntro, AcceShop,
  ...). The castle files (Castle/Butler, Castle/DiningData) and MyRoom, Fortune, JobIntro,
  AcceShop are not plain record tables: they share a self-describing "sheet" layout
  (`MOD_<name>` header naming the columns, `DAT_<name>` rows, `SHEET_<name>` footer). They
  need one generic sheet codec rather than a layout per file, so they were left for a
  separate step. No GameData header slot points at castle shop or forge price lists.
- Adding characters (refused: the 256-person bit set), skills and per-chapter records;
  new items and classes work in the files but have not been seen in a running game.
- The low-confidence fields' in-game effects have not been tested in a running game.

## Field reference

Generated from `config/tables/` by `python tools/tables/gen.py doc`; do not edit by hand.

<!-- tables:begin (generated by tools/tables/gen.py doc) -->

| Table | File(s) | Record | Records | Fields (high / medium / low) |
|---|---|---:|---:|---|
| [GameDataHeader](#gamedataheader) | `GameData/GameData.bin.lz` | 0x64 | 1 | 25 (23 / 1 / 1) |
| [Chapter](#chapter) | `GameData/GameData.bin.lz` | 0x1C | 122 | 15 (7 / 4 / 4) |
| [Person](#person) | `GameData/GameData.bin.lz` | 0x98 | 255 | 43 (27 / 6 / 10) |
| [PersonChapter](#personchapter) | `GameData/Person/*.bin.lz` `GameData/Person/A/*.bin.lz` `GameData/Person/B/*.bin.lz` `GameData/Person/C/*.bin.lz` | 0x98 | 1622 in 117 files | 43 (27 / 6 / 10) |
| [Job](#job) | `GameData/GameData.bin.lz` | 0x80 | 129 | 36 (21 / 6 / 9) |
| [JobCategory](#jobcategory) | `GameData/GameData.bin.lz` | 0x4 | 12 | 1 (1 / 0 / 0) |
| [PersonFlag](#personflag) | `GameData/GameData.bin.lz` | 0x4 | 63 | 1 (1 / 0 / 0) |
| [Skill](#skill) | `GameData/GameData.bin.lz` | 0x20 | 229 | 14 (10 / 3 / 1) |
| [Belong](#belong) | `GameData/GameData.bin.lz` | 0x10 | 22 | 6 (4 / 2 / 0) |
| [Item](#item) | `GameData/GameData.bin.lz` | 0x68 | 355 | 41 (26 / 5 / 10) |
| [ItemFlag](#itemflag) | `GameData/GameData.bin.lz` | 0x4 | 64 | 1 (1 / 0 / 0) |
| [ItemUse](#itemuse) | `GameData/GameData.bin.lz` | 0x4 | 20 | 1 (1 / 0 / 0) |
| [TerrainHeader](#terrainheader) | `GameData/Terrain/*.bin.lz` | 0x10 | 109 in 109 files | 4 (3 / 1 / 0) |
| [TerrainTile](#terraintile) | `GameData/Terrain/*.bin.lz` | 0x28 | 1066 in 109 files | 15 (9 / 4 / 2) |
| [TerrainGrid](#terraingrid) | `GameData/Terrain/*.bin.lz` | 0x418 | 109 in 109 files | 7 (7 / 0 / 0) |
| [DisposFaction](#disposfaction) | `GameData/Dispos/*.bin.lz` `GameData/Dispos/A/*.bin.lz` `GameData/Dispos/B/*.bin.lz` `GameData/Dispos/C/*.bin.lz` | 0xC | 1330 in 185 files | 3 (3 / 0 / 0) |
| [DisposUnit](#disposunit) | `GameData/Dispos/*.bin.lz` `GameData/Dispos/A/*.bin.lz` `GameData/Dispos/B/*.bin.lz` `GameData/Dispos/C/*.bin.lz` | 0x8C | 9601 in 185 files | 43 (34 / 9 / 0) |
| [Personality](#personality) | `GameData/GameData.bin.lz` | 0x40 | 9 | 11 (6 / 4 / 1) |
| [ItemKind](#itemkind) | `GameData/GameData.bin.lz` | 0xC | 9 | 3 (2 / 1 / 0) |
| [ItemSubKind](#itemsubkind) | `GameData/GameData.bin.lz` | 0x10 | 21 | 7 (2 / 5 / 0) |
| [ItemRefine](#itemrefine) | `GameData/GameData.bin.lz` | 0x28 | 3 | 10 (9 / 1 / 0) |
| [WeaponLevel](#weaponlevel) | `GameData/GameData.bin.lz` | 0x8 | 1 | 2 (2 / 0 / 0) |
| [WeaponBonus](#weaponbonus) | `GameData/GameData.bin.lz` | 0xC | 8 | 6 (6 / 0 / 0) |
| [WeaponInteract](#weaponinteract) | `GameData/GameData.bin.lz` | 0x4C | 1 | 14 (14 / 0 / 0) |
| [ExpTableHeader](#exptableheader) | `GameData/GameData.bin.lz` | 0x18 | 1 | 6 (6 / 0 / 0) |
| [ExpBattle](#expbattle) | `GameData/GameData.bin.lz` | 0x48 | 3 | 4 (4 / 0 / 0) |
| [ExpBattleFloor](#expbattlefloor) | `GameData/GameData.bin.lz` | 0x18 | 3 | 4 (4 / 0 / 0) |
| [ExpRod](#exprod) | `GameData/GameData.bin.lz` | 0x28 | 3 | 1 (1 / 0 / 0) |
| [ExpRodHigh](#exprodhigh) | `GameData/GameData.bin.lz` | 0x4 | 3 | 2 (2 / 0 / 0) |
| [ExpDance](#expdance) | `GameData/GameData.bin.lz` | 0x28 | 3 | 1 (1 / 0 / 0) |
| [ExpSupport](#expsupport) | `GameData/GameData.bin.lz` | 0x28 | 3 | 1 (1 / 0 / 0) |
| [TerrainCostHeader](#terraincostheader) | `GameData/GameData.bin.lz` | 0x4 | 1 | 1 (1 / 0 / 0) |
| [TerrainCost](#terraincost) | `GameData/GameData.bin.lz` | 0x10 | 16 | 1 (1 / 0 / 0) |
| [GameDataUnknown50](#gamedataunknown50) | `GameData/GameData.bin.lz` | 0x4 | 16 | 1 (0 / 0 / 1) |
| [Tutorial](#tutorial) | `GameData/GameData.bin.lz` | 0x14 | 34 | 6 (5 / 1 / 0) |
| [AchieveBonusHeader](#achievebonusheader) | `GameData/GameData.bin.lz` | 0x20 | 1 | 8 (7 / 1 / 0) |
| [AchieveBonusRoute](#achievebonusroute) | `GameData/GameData.bin.lz` | 0x8 | 8 | 4 (1 / 2 / 1) |
| [AchieveBonusBattle](#achievebonusbattle) | `GameData/GameData.bin.lz` | 0x8 | 80 | 4 (1 / 2 / 1) |
| [AchieveBonusVisit](#achievebonusvisit) | `GameData/GameData.bin.lz` | 0x8 | 80 | 4 (1 / 2 / 1) |
| [AchieveBonusList4](#achievebonuslist4) | `GameData/GameData.bin.lz` | 0x8 | 24 | 4 (1 / 2 / 1) |
| [ArenaHeader](#arenaheader) | `GameData/GameData.bin.lz` | 0x10 | 1 | 4 (4 / 0 / 0) |
| [ArenaLow](#arenalow) | `GameData/GameData.bin.lz` | 0x8 | 17 | 3 (2 / 1 / 0) |
| [ArenaHigh](#arenahigh) | `GameData/GameData.bin.lz` | 0x8 | 28 | 3 (2 / 1 / 0) |

### GameDataHeader

Top of GameData.bin: pointers to every sub-table and their counts, in the order GameData::Initialize (004E6954) hands them to Chapter/Person/Job/.../Arena::Initialize. File `GameData/GameData.bin.lz`; start `0`; count `one`; record size 0x64; 1 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `ptr:Chapter` | chapter_table | high | GameData::Initialize 004E6954: ldrd [hdr+0x0] -> Chapter::Initialize(const void*;int) |
| +0x004 | 4 | `u32` | chapter_count | high | GameData::Initialize: second word of the ldrd at +0x0 = Chapter::Initialize count argument |
| +0x008 | 4 | `ptr` | person_block | high | GameData::Initialize: ldr [hdr+0x8] -> Person::Initialize(const void*); block = 16-byte header + records |
| +0x00C | 4 | `ptr` | job_block | high | GameData::Initialize: ldr [hdr+0xC] -> Job::Initialize(const void*); block = 8-byte header + records |
| +0x010 | 4 | `ptr:Skill` | skill_table | high | GameData::Initialize: ldm [hdr+0x10] (3 words) -> EquipSkill::Initialize(const void*;int;int) |
| +0x014 | 4 | `u32` | skill_common_count | medium | EquipSkill::Initialize 2nd argument; EquipSkill::GetCommonNum returns it (skills a unit can learn normally) |
| +0x018 | 4 | `u32` | skill_count | high | EquipSkill::Initialize 3rd argument; equals the number of SEID_ labels |
| +0x01C | 4 | `ptr:Personality` | personality_table | high | GameData::Initialize: ldrd [hdr+0x1C] -> Personality::Initialize(const void*;int) |
| +0x020 | 4 | `u32` | personality_count | high | Personality::Initialize count argument |
| +0x024 | 4 | `ptr:Belong` | belong_table | high | GameData::Initialize: ldrd [hdr+0x24] -> Belong::Initialize(const void*;int) |
| +0x028 | 4 | `u32` | belong_count | high | Belong::Initialize count argument; equals the number of BID_ labels |
| +0x02C | 4 | `ptr` | item_block | high | GameData::Initialize: ldr [hdr+0x2C] -> Item::Initialize(const void*); block = 8-byte header + records |
| +0x030 | 4 | `ptr:ItemKind` | item_kind_table | high | GameData::Initialize: ldr [hdr+0x30] -> ItemKind::Initialize(const void*) |
| +0x034 | 4 | `ptr:ItemSubKind` | item_subkind_table | high | GameData::Initialize: ldr [hdr+0x34] -> ItemSubKind::Initialize(const void*) |
| +0x038 | 4 | `ptr:ItemRefine` | item_refine_table | high | GameData::Initialize: ldr [hdr+0x38] -> ItemRefine::Initialize(const void*) (forging) |
| +0x03C | 4 | `ptr:WeaponLevel` | weapon_level_table | high | GameData::Initialize: ldr [hdr+0x3C] -> WeaponLevel::Initialize(const void*) |
| +0x040 | 4 | `ptr:WeaponBonus` | weapon_bonus_table | high | GameData::Initialize: ldr [hdr+0x40] -> WeaponBonus::Initialize(const void*) |
| +0x044 | 4 | `ptr:WeaponInteract` | weapon_interact_table | high | GameData::Initialize: ldr [hdr+0x44] -> WeaponInteract::Initialize(const void*) (weapon triangle) |
| +0x048 | 4 | `ptr:ExpTableHeader` | exp_table | high | GameData::Initialize: ldr [hdr+0x48] -> ExpTable::Initialize(const void*) |
| +0x04C | 4 | `ptr:TerrainCostHeader` | terrain_cost_table | high | GameData::Initialize: ldr [hdr+0x4C] -> TerrainCost::Initialize(const void*) (movement cost classes) |
| +0x050 | 4 | `ptr:GameDataUnknown50` | unknown_table_0x50 | low | not passed to any initializer by GameData::Initialize; Paragon FE14 GameData.yml also leaves it unnamed (fact cross-check) |
| +0x054 | 4 | `ptr:Tutorial` | tutorial_table | high | GameData::Initialize: ldrd [hdr+0x54] -> Tutorial::Initialize(const void*;int) |
| +0x058 | 4 | `u32` | tutorial_count | high | Tutorial::Initialize count argument; equals the number of TUTID_ labels |
| +0x05C | 4 | `ptr:AchieveBonusHeader` | achieve_bonus_table | high | GameData::Initialize: ldr [hdr+0x5C] -> AchieveBonus::Initialize(const void*) |
| +0x060 | 4 | `ptr:ArenaHeader` | arena_table | high | GameData::Initialize: ldr [hdr+0x60] -> Arena::Initialize(const void*) |

### Chapter

Chapters (CID_): map model, route links, prep screen (Chapter::Initialize(const void*,int) gets header +0x0/+0x4). File `GameData/GameData.bin.lz`; start `[0x0]`; count `u32@0x4`; record size 0x1C; 122 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `str:self` | cid | high | Chapter::GetTitleName/GetTerrainName/GetTitlePrefix read +0x0 (CID_ string; equals the record label) |
| +0x004 | 4 | `str` | battle_map | medium | data: Btl_* battle-background names (3 records none); Paragon FE14 Chapter.yml 'battlefield' (fact) |
| +0x008 | 1 | `u8` | chapter_number | high | Chapter::SerializePointer stores +0x8 (u8); equals the record index in every record (Chapter::Get(unsigned char)) |
| +0x009 | 1 | `u8` | chapter_type | medium | read by MemberMenu::Draw / ProcEpilogue::SettingWord / Spot::Rebuild (+0x9 u8; Spot::Rebuild walks back over chapters whose type is not 0, so 0 = main story); values 0-7; Paragon 'type' (fact) |
| +0x00A | 3 | `ref8:Chapter[3]` | next_chapter (A, B, C) | high | ChapterComplete 001B64D8 takes the next chapter as +0xA[route byte] (GameUserData+0x2E; docs/ROUTES.md); Spot::Rebuild 003D314C walks forward through +0xA[route]; index 0/1/2 = Birthright/Conquest/Revelation (Route::Type) |
| +0x00D | 3 | `ref8:Chapter[3]` | required_chapter (A, B, C) | high | Spot::Rebuild 003D314C walks the chapter chain backwards through +0xD[route byte] (u8; GameUserData+0x2E) to mark the chapters before the current one; data: the previous chapter on that route (0 = none); Paragon 'route requirement' (fact) |
| +0x010 | 2 | `u16` | married_character | low | data 0..0x2B (101 zero); Paragon 'married_character' (fact) |
| +0x012 | 1 | `s8` | offspring_seal_level | medium | event::Informal GetRank 00431A38 uses the current chapter's +0x12 (s8; +0x13 when GameUserData+0x28 bit 1 is set) as the rank instead of the scenario rank when it is >= 0; data 0..0x28 or -1; Paragon 'offspring_seal_level' (fact); WAS u8 (255 now shows as -1) |
| +0x013 | 1 | `s8` | offspring_seal_level_2 | medium | event::Informal GetRank 00431A38 reads +0x13 (s8) instead of +0x12 when GameUserData+0x28 bit 1 is set; Paragon (fact); WAS u8 |
| +0x014 | 1 | `u8` | route_mask | high | Spot::UpdateSpot / Spot::Rebuild list a chapter when +0x14 & (1 << route byte); values 1/2/4/7 = route bits Birthright/Conquest/Revelation (docs/ROUTES.md) |
| +0x015 | 1 | `u8` | unknown_15 | low | read by GameUserData::Deserialize (+0x15 u8); values 0-3 |
| +0x016 | 2 | `pad` | pad_16 | high | zero in every record; no code read seen |
| +0x018 | 1 | `u8` | prep_screen | low | data 0x7F/0x80/0; Paragon 'battle_prep_screen' (fact) |
| +0x019 | 1 | `u8` | unknown_19 | low | data 0-2 |
| +0x01A | 2 | `pad` | pad_1a | high | zero in every record; no code read seen |

### Person

Characters always loaded (archive 'resident', PID_): stats, growths, classes, skills (Person::Initialize gets header +0x8; Person::Get(unsigned short) = block+0x10+i*0x98). File `GameData/GameData.bin.lz`; start `[0x8]+0x10`; count `u16@[0x8]+0x4`; record size 0x98; 255 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 8 | `flags64:PersonFlag` | flags | high | Person::IsFemale/IsPlayer/IsBond/IsCapture/IsDownload (0053ED90.. 0053DFEC) test the u64 at +0x0 against 1<<n for n = PrivateSkill::Get("SPID_..") (SPID_女性/プレイヤー/絆/捕獲/ダウンロード) |
| +0x008 | 4 | `str:self` | pid | high | record label = this string in every record; Person::Get(const char*) looks persons up by PID_ |
| +0x00C | 4 | `str` | fid | high | Person::GetCaptureChange 0053E1BC reads +0xC and skips 4 chars (FID_ prefix); data: FID_ face IDs |
| +0x010 | 4 | `str` | aid | medium | data: AID_ asset (model) IDs; Paragon FE14 Person.yml 'aid' (fact) |
| +0x014 | 4 | `str` | mpid_name | high | Person::GetNameWithCaptureNameIndex 0053E2D0 reads +0x14 (MPID_ message ID of the name) |
| +0x018 | 4 | `str` | mpid_help | high | Person::GetHelp 0053ECD0 reads +0x18 (MPID_H_ description message) |
| +0x01C | 4 | `ptr` | attack_stance_bonus | high | Unit::GetDualSupport 0052E974 reads Person+0x1C (Attack Stance support bonus block; Paragon: 5 support ranks x 4 bytes) |
| +0x020 | 4 | `ptr` | guard_stance_bonus | high | Unit::GetDoubleCapability 00530A34 reads Person+0x20 (Guard Stance support bonus block; Paragon: 5 ranks x 8 bytes) |
| +0x024 | 2 | `u16` | pid_number | high | Person::Get(unsigned short) 0044A6F8: index = number - (first record +0x24); GameData persons are 0..254; chapter files start at 0x7A00 |
| +0x026 | 1 | `u8` | support_route | low | Unit::AddChapterReliance reads +0x26 (u8); Paragon 'support_route' (fact) |
| +0x027 | 1 | `ref8:Belong` | belong | high | Unit::CreateImpl 003D3954 reads Person+0x27 (u8) for the unit's army; values < Belong count |
| +0x028 | 2 | `u16` | replace_index | low | read by map::Dispos::Data::CalculateImpl/Unit::Handover/Unit::CreateImpl2 (u16); data 0..0x26; Paragon 'replacing' (fact) |
| +0x02A | 2 | `u16` | family_index | medium | unit::Family::GetGrow / ParentSingle::GetGrow / Person::GetRelianceRecollection* compare +0x2A (u16) to find parents and siblings; Unit::GetGrow 005330B4 averages the unit's growth with the parent's (unit::Family::GetGrow) when +0x2A != 0 and the parent exists; Paragon 'parent' (fact) |
| +0x02C | 2 | `ref16:Job` | job | high | Person::GetLowJobIndex 0053E198 returns +0x2C (or +0x2E when Job::IsHigh); Unit::CreateImpl reads +0x2C |
| +0x02E | 2 | `ref16:Job` | job_low | high | Person::GetLowJobIndex returns +0x2E when the class at +0x2C is promoted (base class for reclassing) |
| +0x030 | 2 | `s16` | support_id | low | data -1 in 1806 records; Paragon 'support_id' (fact) |
| +0x032 | 1 | `u8` | level | high | Unit::CreateImpl reads Person+0x32 (u8) as the starting level |
| +0x033 | 1 | `s8` | internal_level | high | Unit::CreateImpl 003D3954 stores +0x33 (s8) in Unit+0x12F (levels gained before promotion); -1 means 0 for an unpromoted class and 20 for a promoted one; Paragon 'internal_level' (fact) |
| +0x034 | 1 | `u8` | unit_kind | high | growth source: Unit::GetGrow 005330B4 and Unit::CaclulateAutoGrowCapability 00532880 add Job.growth (+0x24) when +0x34 == 1 and Job.enemy_growth (+0x2C) otherwise; Unit::CaclulateAutoGrowCapability 00532880 gives automatic level-based stats only when +0x34 == 0 (generic units); Person::GetCaptureChange tests == 1; values 0-3; Paragon 'enemy_flag' (fact) |
| +0x035 | 1 | `u8` | autolevel_rank | high | Unit::CreateImpl 003D3954: when the scenario rank (GameUserData+0x30; the ScenarioRankGet script command and spot::Data::GetRank read it) is above this value and this is non-zero, the new unit gets (rank - this) extra level-ups (Unit::CollectiveLevelUpCapability); 0 = never; WAS part of unknown_35 (u8[3]) |
| +0x036 | 1 | `s8` | normal_extra_levels | high | Unit::CaclulateAutoGrowCapability 00532880 adds +0x36 (s8) to the automatic level count on difficulty 0 (GameUserData+0x2D; Normal); data -5..0; WAS part of unknown_35 |
| +0x037 | 1 | `s8` | lunatic_extra_levels | high | Unit::CaclulateAutoGrowCapability 00532880 adds +0x37 (s8) to the automatic level count on difficulty 2 (Lunatic); data 0..10; WAS part of unknown_35 |
| +0x038 | 8 | `s8[8]` | base (hp, str, mag, skl, spd, lck, def, res) | high | Unit::GetMHPImpl/GetStrImpl/GetPowImpl/GetTechImpl/GetQuickImpl/GetLuckImpl/GetDefImpl/GetMdefImpl read Person+0x38..+0x3F (s8) in that order |
| +0x040 | 8 | `s8[8]` | growth (hp, str, mag, skl, spd, lck, def, res) | high | Unit::GetGrow(int) 005330B4 (Person.growth + Job.growth or Job.enemy_growth; +10 with one equipped skill) and Unit::CaclulateAutoGrowCapability 00532880 read Person+0x40[i] (s8); plain values (multiples of 5) - Fates does not obfuscate them |
| +0x048 | 8 | `s8[8]` | limit_mod (hp, str, mag, skl, spd, lck, def, res) | high | Unit::GetLimit(int) 005337F0 adds Person+0x48[i] to Job+0x34[i] (maximum-stat modifier) |
| +0x050 | 8 | `s8[8]` | normal_mod (hp, str, mag, skl, spd, lck, def, res) | high | Unit::CaclulateAutoGrowCapability 00532880 adds Person+0x50[i] (s8) to the unit's created stats on difficulty 0 (GameUserData+0x2D; Normal); data almost all <= 0; Paragon calls it 'penalties' (fact); WAS named stat_mod_50 |
| +0x058 | 8 | `s8[8]` | lunatic_mod (hp, str, mag, skl, spd, lck, def, res) | high | Unit::CaclulateAutoGrowCapability 00532880 adds Person+0x58[i] (s8) to the unit's created stats on difficulty 2 (Lunatic) (from the disassembly: the evidence walk misses this branch); data almost all >= 0; Paragon calls it 'bonuses' (fact); WAS named stat_mod_58 |
| +0x060 | 8 | `u8[8]` | weapon_exp (sword, lance, axe, dagger, bow, tome, staff, stone) | medium | Unit::CaclulateFirstWeaponExp and CollectiveLevelUpCapability read Person+0x60[i] (u8); order from Paragon (fact) |
| +0x068 | 10 | `ref16:Skill[5]` | skill (1, 2, 3, 4, 5) | high | Unit::CreateImpl 003D3954 reads +0x68+2i (s16) for i = 0..4 and adds EquipSkill::Get(short) as an equipped skill when skill_mask allows it; Paragon skill_1..5 (fact) |
| +0x072 | 2 | `u16` | skill_mask | high | Unit::CreateImpl 003D3954: skill i (+0x68) is given only when bit (3*i + difficulty) of +0x72 (u16) is set (difficulty = GameUserData+0x2D); 0x7FFF = every skill on every difficulty; Paragon 'skill_flags' (fact) |
| +0x074 | 6 | `ref16:Skill[3]` | personal_skill (normal, hard, lunatic) | high | Unit::IsEquipSkill 0052DD04 reads +0x74 + 2*difficulty (GameUserData+0x2D) as the unit's personal skill; Paragon normal/hard/lunatic (fact) |
| +0x07A | 2 | `u8[2]` | birthday (month, day) | low | data month/day pairs; Paragon 'birthday' (fact) |
| +0x07C | 4 | `ref16:Job[2]` | reclass (1, 2) | medium | data: Job indexes (0 = none); Paragon reclass_1/2 (fact) |
| +0x080 | 2 | `u16` | parent_id | low | data 0xFFFF in most records; Paragon 'parent_id' (fact) |
| +0x082 | 2 | `u16` | child_id | low | data 0xFFFF in most records; Paragon 'child_id' (fact) |
| +0x084 | 2 | `u16` | support_index | low | data 0xFFFF or 0x8E9..; Paragon 'support_index' (fact) |
| +0x086 | 1 | `s8` | level_cap | high | Unit::CreateImpl stores +0x86 in Unit+0x130; Unit::GetLimitLevel 0052E5EC = Job::GetLimitLevel + Unit+0x130 * step for promoted or special classes (pre-applied level-limit extensions; not a level cap by itself); Unit::LevelUp reads it; Paragon 'level_cap' (fact) |
| +0x087 | 1 | `u8` | body_type | low | data 0xFF in most records; Paragon 'body_type' (fact) |
| +0x088 | 4 | `str` | combat_music | medium | data: BGM cue names; Paragon (fact) |
| +0x08C | 4 | `str` | voice | medium | data: voice set names; Paragon (fact) |
| +0x090 | 2 | `ref16:Item` | recruit_weapon | low | data: Item indexes in 4 records; Paragon 'recruit_equip_weapon' (fact) |
| +0x092 | 2 | `ref16:Item` | shop_item | low | data: Item indexes in 4 records; Paragon 'special_shop_item' (fact) |
| +0x094 | 4 | `pad` | pad_94 | high | zero in every record of every Person file |

### PersonChapter

Per-chapter characters (enemies, NPCs, bosses), one Person block per chapter file (Person::Load/LoadArchive); same record layout as Person. File `GameData/Person/*.bin.lz` `GameData/Person/A/*.bin.lz` `GameData/Person/B/*.bin.lz` `GameData/Person/C/*.bin.lz`; start `0x10`; count `u16@0x4`; record size 0x98; 1622 in 117 files records.

Same record layout as [Person](#person) (config/tables/Person.csv).

### Job

Classes (JID_) (Job::Initialize gets header +0xC; Job::Get(unsigned short) = block+0x8+i*0x80). File `GameData/GameData.bin.lz`; start `[0xC]+0x8`; count `u16@[0xC]+0x6`; record size 0x80; 129 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 8 | `flags64:PersonFlag` | flags | high | Job::IsHigh/IsFemale/IsGiant/IsEnemyOnly (00524804 00524AF4 005249F8 00524140) test the u64 at +0x0 with SPID_上級職/女性/巨大/敵専用 bits (PrivateSkill::Get) |
| +0x008 | 4 | `str:self` | jid | high | record label = this string; Job::GetIntroName 005241C4 reads +0x8 |
| +0x00C | 4 | `str` | fid | medium | data: FID_ (generic face) IDs; castle::CastleButler::GetFid reads Job+0xC |
| +0x010 | 4 | `str` | mjid_name | high | Job::GetName 00524910 reads +0x10 (MJID_ message) |
| +0x014 | 4 | `str` | mjid_help | high | Job::GetHelp 00524888 reads +0x14 (MJID_H_ message) |
| +0x018 | 2 | `u16` | job_number | high | Job::IsDownload/GetName read +0x18; equals the record index (Job::Get(unsigned short)); Job::SerializePointer stores it |
| +0x01A | 2 | `flags16:JobCategory` | category | high | Job::IsFlyer 00524980 / Job::IsRider 00524A7C test +0x1A with JCID_飛行 / JCID_騎乗 bits |
| +0x01C | 8 | `s8[8]` | base (hp, str, mag, skl, spd, lck, def, res) | high | Unit::GetMHPImpl..GetMdefImpl read Job+0x1C..+0x23 (s8) in stat order |
| +0x024 | 8 | `s8[8]` | growth (hp, str, mag, skl, spd, lck, def, res) | high | Unit::GetGrow 005330B4 and Unit::CaclulateAutoGrowCapability add Job+0x24[i] (s8) to Person.growth when Person.unit_kind == 1; Unit::Inherit2 reads it; Paragon 'player_growths' (fact) |
| +0x02C | 8 | `s8[8]` | enemy_growth (hp, str, mag, skl, spd, lck, def, res) | high | Unit::GetGrow 005330B4 and Unit::CaclulateAutoGrowCapability 00532880 add Job+0x2C[i] (s8) instead of +0x24 when Person.unit_kind != 1 (enemies, NPCs; also the auto-level stats of generic units); Paragon 'enemy_growths' (fact) |
| +0x034 | 8 | `s8[8]` | max (hp, str, mag, skl, spd, lck, def, res) | high | Unit::GetLimit(int) 005337F0 reads Job+0x34[i] (maximum stats; plus Person.limit_mod) |
| +0x03C | 8 | `s8[8]` | pair_up (hp, str, mag, skl, spd, lck, def, res) | high | Unit::GetDoubleCapability 00530A34 reads Job+0x3C[i] (pair-up bonus); GetDoubleMovePower reads +0x3C |
| +0x044 | 8 | `u8[8]` | max_weapon_exp (sword, lance, axe, dagger, bow, tome, staff, stone) | high | Unit::GetWeaponExpLimit 0052F824 / Job::CanEquipFromSubKind read Job+0x44[i] (u8); weapon order from Paragon (fact) |
| +0x04C | 2 | `s16` | hit | high | Unit::GetHit 00532DC4 and GetInterferenceRodHit read Job+0x4C (s16) |
| +0x04E | 2 | `s16` | crit | high | Unit::GetCritical(const unit::Item*) 0052B9BC reads Job+0x4E (s16) |
| +0x050 | 2 | `s16` | avoid | high | Unit::GetAvoid 00533524 reads Job+0x50 (s16) |
| +0x052 | 2 | `s16` | dodge | high | Unit::GetSecure 005345E0 reads Job+0x52 (s16) (critical avoid) |
| +0x054 | 8 | `ref16:Skill[4]` | skill (1, 2, 3, 4) | medium | data: Skill indexes; Job::GetEquipSkill(int) 00524224 reads +0x58/+0x5A; Paragon skill_1..4 (fact) |
| +0x05C | 1 | `ref8:TerrainCost` | move_cost_class | high | TerrainCost::GetCostFromUnit 001A6708 uses Job+0x5C as the TerrainCost row; map::Dispos::Data::UnitMove and Terrain::IsCastleUnitDispos read it too |
| +0x05D | 1 | `u8` | mov | high | Unit::GetMovePower 0052D5E4 reads Job+0x5D |
| +0x05E | 1 | `u8` | unknown_5e | low | data 0x0F/0x14/0x12; Paragon 'smoke_clouds_size' (fact) |
| +0x05F | 1 | `u8` | unknown_5f | low | spot::Mob::CreateDisposUnitMonster reads +0x5F; Paragon 'extra_flags' (fact) |
| +0x060 | 4 | `str` | move_sound | medium | data: footstep sound names; Paragon 'movement_sound' (fact) |
| +0x064 | 4 | `ref16:Job[2]` | promotion (1, 2) | high | Unit::ClassChange 003D40C8 and ClassChangeEnumerator::AddSlideLow read Job+0x64 (u16 Job index) |
| +0x068 | 4 | `ref16:Job[2]` | base_class (1, 2) | low | data: Job indexes; Paragon base_class_1/2 (fact); no reader found (evidence --fields Job and a scan of the class-change and inherit code for +0x68/+0x6A loads) |
| +0x06C | 4 | `pad` | pad_6c | high | zero in every record |
| +0x070 | 2 | `ref16:Job` | gender_pair | medium | anonymous_namespace::IsInheritJobIndex reads +0x70; data: Job indexes; Paragon 'gender_equivalent_class' (fact) |
| +0x072 | 2 | `ref16:Job` | parallel_class | medium | ClassChangeEnumerator::EnumerateParallel and GetInheritJobIndex read +0x72 (u16 Job index) |
| +0x074 | 1 | `u8` | origin | medium | map::EquipSkillCalculator::Calculate / ProcTerrainHeal / ProcTerrainDamage / Job::GetBasicItemCanEquipForEvent read +0x74; values 1-3; GameUserData::IsRouteOrigin / Origin::IsRoute: origin 1 = Hoshido side, 2 = Nohr side (docs/ROUTES.md); Paragon 'origin' (fact) |
| +0x075 | 1 | `u8` | swimwear_index | low | Swimwear::Get reads Job+0x75 |
| +0x076 | 1 | `u8` | unknown_76 | low | castle::AngelSequence::..::Angel_Create reads Job+0x76 |
| +0x077 | 1 | `s8` | swimwear_variant | low | Swimwear::Get reads Job+0x77 (s8) |
| +0x078 | 2 | `u16` | sort_order | low | data: 129 distinct values (a per-class number); no code read found |
| +0x07A | 1 | `u8` | special_battle | low | Unit::IsSpecialBattle reads Job+0x7A |
| +0x07B | 1 | `s8` | unknown_7b | low | Unit::ClassChange reads Job+0x7B (s8); -1 in most records; Paragon 'dlc_skill_index' (fact) |
| +0x07C | 4 | `pad` | pad_7c | high | zero in every record |

### JobCategory

ID list JCID_: class category bits used by Job.category_flags (Job::IsFlyer tests JCID_ flying). File `GameData/GameData.bin.lz`; start `family:JCID_`; count `family:JCID_`; record size 0x4; 12 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `u32` | number | high | ID list: the record's label is the ID name; the number is the bit (flags) or value it stands for (PrivateSkill::Get returns this record; 1<<number is the mask) |

### PersonFlag

ID list SPID_: bit numbers of the Person/Job 64-bit flag words (looked up by PrivateSkill::Get(const char*) 001B7758). File `GameData/GameData.bin.lz`; start `family:SPID_`; count `family:SPID_`; record size 0x4; 63 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `u32` | number | high | ID list: the record's label is the ID name; the number is the bit (flags) or value it stands for (PrivateSkill::Get returns this record; 1<<number is the mask) |

### Skill

Skills (SEID_) (EquipSkill::Initialize(const void*,int,int) gets header +0x10, +0x14 common count, +0x18 total count). File `GameData/GameData.bin.lz`; start `[0x10]`; count `u32@0x18`; record size 0x20; 229 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `str:self` | seid | high | record label = this string; EquipSkill::Get(const char*) |
| +0x004 | 4 | `str` | mseid_name | high | EquipSkill::GetName 00505FD0 reads +0x4 (MSEID_ message) |
| +0x008 | 4 | `str` | mseid_help | high | EquipSkill::GetHelp 00505F08 reads +0x8 (MSEID_H_ message) |
| +0x00C | 4 | `str` | effect | medium | map::SequenceHelper::..::CheerImpl reads +0xC; data: effect names on 71 skills; Paragon 'effect' (fact) |
| +0x010 | 2 | `u16` | skill_number | high | read by 79 functions (AIBattleSimulator SkillIndexProvider...); equals the record index (EquipSkill::Get(short)) |
| +0x012 | 2 | `s16` | sort_order | low | data: -1 on 69 skills else unique; Paragon 'sort_order' (fact) |
| +0x014 | 2 | `u16` | icon | high | EquipSkill::GetIcon 00505F80 reads +0x14 |
| +0x016 | 1 | `u8` | trigger_stat | high | Unit::GetEquipSkillProbability 005324B8 reads +0x16 (stat the activation rate uses; 3 = skl; 5 = lck) |
| +0x017 | 1 | `u8` | trigger_factor | high | Unit::GetEquipSkillProbability reads +0x17 (multiplier) |
| +0x018 | 1 | `u8` | trigger_divisor | high | Unit::GetEquipSkillProbability reads +0x18 (divisor) |
| +0x019 | 1 | `u8` | kind | medium | EquipSkill::IsUnknown 00506034 compares +0x19 with 5 (then looks up the MSEID_ name); GetName/GetHelp/GetIcon and Unit::InheritEquipSkill also branch on it; values 0/1/3/4 |
| +0x01A | 2 | `u16` | price | high | Unit::GetLearnFromDictionaryPrice 005329E0 and IsLearnFromDictionary read +0x1A |
| +0x01C | 1 | `u8` | flags_2 | medium | Unit::CreateImpl 003D3954 skips a Person skill whose +0x1C has bit 1 (2) when Person.unit_kind == 0 and bit 0 (1) when unit_kind == 1; DeleteEquipSkillUnknownAndEnemyOnlyWithPool / SetDispos read it too |
| +0x01D | 3 | `pad` | pad_1d | high | zero in every record |

### Belong

Armies / factions (BID_) (Belong::Initialize(const void*,int) gets header +0x24/+0x28). File `GameData/GameData.bin.lz`; start `[0x24]`; count `u32@0x28`; record size 0x10; 22 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `u32` | belong_number | high | equals the record index; Belong::Get(int); UnitSetBID reads +0x0 |
| +0x004 | 4 | `str` | mbid_name | high | Belong::GetName 0053D44C reads +0x4 (MBID_ message) |
| +0x008 | 4 | `str` | mbid_help | high | Belong::GetHelp 0053D438 reads +0x8 (MBID_H_ message) |
| +0x00C | 1 | `u8` | kind | medium | Unit::CanCaptured 0052AE20 and Unit::IsInvisible read +0xC; values 0-2 |
| +0x00D | 1 | `u8` | icon | medium | ViewerSituation::DrawSituationBelong reads +0xD; Paragon 'icon' (fact) |
| +0x00E | 2 | `pad` | pad_0e | high | zero in every record |

### Item

Items and weapons (IID_) (Item::Initialize gets header +0x2C; Item::Get(unsigned short) = block+0x8+i*0x68). File `GameData/GameData.bin.lz`; start `[0x2C]+0x8`; count `u16@[0x2C]+0x6`; record size 0x68; 355 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 8 | `flags64:ItemFlag` | flags | high | Item::IsMagic 005290B8 / IsHiddenEffect 00528E90 / CanUse 00528F3C test the u64 at +0x0 with ISID_魔法武器 / ISID_暗器 / ISID_使用可能 bits |
| +0x008 | 4 | `str:self` | iid | high | record label = this string; Item::Get(const char*) |
| +0x00C | 4 | `str` | miid_name | high | Item::GetName 00529050 reads +0xC (MIID_ message) |
| +0x010 | 4 | `str` | miid_help | high | Item::GetHelp 00528FD0 reads +0x10 (MIID_H_ message) |
| +0x014 | 2 | `u16` | item_number | high | Item::GetName/IsDownload read +0x14; equals the record index; unit::Item::New(const Item*) stores it |
| +0x016 | 2 | `u16` | list_position | low | data: near-unique per item; Paragon 'item_list_position' (fact) |
| +0x018 | 2 | `u16` | icon | low | data 0..0x1F; Paragon 'icon' (fact) |
| +0x01A | 1 | `s8` | weapon_kind | high | Item::IsWeapon 00529164 / IsMagic read +0x1A (s8); ItemGetKind; Unit::GetHit/GetAttack pass it to ItemSubKind::Get(int): an ItemSubKind index (check.py: < ItemSubKind count) |
| +0x01B | 1 | `u8` | item_subkind | low | data 0..0x12; Paragon 'non_weapon_category' (fact) |
| +0x01C | 1 | `u8` | weapon_rank | high | Unit::CanItemEquip 0052C634 / Unit::WeaponBuildup / handicap::..::CalculateUnitItem read +0x1C; data are weapon-exp thresholds (0x01 0x15 0x33 0x60 0xA1 0xFB = WeaponLevel ranks); Paragon 'required_weapon_exp' (fact) |
| +0x01D | 1 | `u8` | staff_exp | high | Unit::GetExpRod 005342F4 reads Item+0x1D (u8) as the base experience of a staff use (then adds ExpRod/ExpRodHigh/ExpSupport); Paragon 'base_staff_exp' (fact) |
| +0x01E | 1 | `u8` | uses | high | unit::Item::New(const Item*) 00419820 reads +0x1E as the starting durability (UnitItemSetEndurance) |
| +0x01F | 1 | `u8` | might | high | unit::Item::GetPower 0053B4B4 reads +0x1F |
| +0x020 | 2 | `s16` | hit | high | unit::Item::GetHit 0053B2A4 reads +0x20 (s16) |
| +0x022 | 2 | `s16` | crit | high | unit::Item::GetCritical 0053AD54 reads +0x22 (s16) |
| +0x024 | 2 | `s16` | avoid | high | Unit::GetAvoid 00533524 adds the equipped item's +0x24 (s16; through unit::Item::ToData); Paragon 'avoid' (fact) |
| +0x026 | 2 | `s16` | dodge | high | Unit::GetSecure 005345E0 adds the equipped item's +0x26 (s16) (critical avoid); Paragon 'dodge' (fact) |
| +0x028 | 1 | `u8` | range_min | high | Unit::GetRangeI / IsItemRangeCanEquip / ArenaData::CalculateEnemy read +0x28; data 0-3; Paragon (fact) |
| +0x029 | 1 | `u8` | range_max | high | Unit::GetItemMaxRangeCanEquip / IsItemRangeCanEquip / ArenaData::CalculateEnemy read +0x29; data 0-5 or 0xFF; Paragon (fact) |
| +0x02A | 1 | `s8` | speed_mod_player | high | Unit::GetContinuous 0052E134 = Spd + the item's +0x2A (s8): speed used for follow-up attacks when this unit attacks; Paragon 'effective_speed_player_phase' (fact) |
| +0x02B | 1 | `s8` | speed_mod_enemy | high | Unit::GetUnderContinuous 00530834 reads +0x2B (s8): follow-up speed modifier when this unit is attacked; Paragon (fact) |
| +0x02C | 4 | `s32` | buy_price | high | ItemBuyMenuItem::GetPrice 00528454 / ProcSequence::CreateItemBuyMenu / Transporter GetPrice read +0x2C (u32); Paragon 'buy_price' (fact) |
| +0x030 | 4 | `s32` | sell_price | high | unit::Item::GetSellPrice 0053AE8C returns +0x30 (doubled per forge level for weapons; times uses left / Item.uses for other items); ItemGain reads it; Paragon 'sell_price' (fact) |
| +0x034 | 2 | `flags16:JobCategory` | effective | high | map::BattleInfo::Side::CalculateEfficacy 0034899C tests the u16 at +0x34 against the target's Unit::GetCategory() (JCID_ bits, as Job.category); WAS two u8 fields effective_1/effective_2 (Paragon effective_damage_1/2), merged because the code reads one u16 |
| +0x036 | 1 | `s8` | mov_bonus | high | Unit::ItemUse 003D7B7C adds +0x36 (s8) to the unit's movement boost (Unit+0x12C; capped at 2); Paragon 'mov' (fact) |
| +0x037 | 1 | `u8` | legal_player_weapon | low | data 0-2; Paragon (fact) |
| +0x038 | 8 | `s8[8]` | stat_bonus (hp, str, mag, skl, spd, lck, def, res) | high | Unit::GetStrImpl 0052A80C adds the equipped item's +0x39 (s8) (the other stat getters their element) after the cap; GameHelp CreateCapabilityString reads +0x38[i]; Paragon 'bonuses' (fact) |
| +0x040 | 8 | `s8[8]` | extra_data (hp, str, mag, skl, spd, lck, def, res) | high | per-item effect values by stat: anonymous_namespace::GetEnhanceHave 0033A790 adds +0x40[stat] (s8) of every carried item that Unit::IsItemEnhanceHave accepts (ISID_所持強化 items: a bonus while carried); Unit::GetItemHealPower reads +0x40 (heal amount); Unit::ItemUse / SetSeal / EnhanceAfterBattleOne read +0x40[i] (stat boosters; after-battle effects); WAS u8[8] with numbered elements (a 255 now shows as -1) |
| +0x048 | 1 | `ref8:ItemRefine` | refine_index | high | unit::Item::GetPower 0053B4B4 / GetHit / GetCritical pass +0x48 to ItemRefine::Get(row;level) as the row; Paragon 'forge_table_index' (fact) |
| +0x049 | 1 | `ref8:ItemRefine` | unknown_49 | medium | unit::Item::GetPower/GetHit/GetCritical pass +0x49 to ItemRefine::Get as the row instead of +0x48 when the unit item's mode bits (unit::Item+0x2 & 0x7F) are 1 |
| +0x04A | 1 | `u8` | skirmish_drop | low | data 0-3; Paragon (fact) |
| +0x04B | 1 | `u8` | unknown_4b | low | 1 in every vanilla record |
| +0x04C | 3 | `u8[3]` | dawn_stock (lv1, lv2, lv3) | medium | shop::Data::UpdateStock 00416E54 / ItemEnumeratorInfinityGoods::IsExclusion read Item+0x4C[kind*3 + level - 1]: the item's stock in shop kind 0 at shop level 1-3 (255 = unlimited, 0 = not sold); which shop kind is which comes from Paragon 'dawn_stock' (fact) |
| +0x04F | 3 | `u8[3]` | dusk_stock (lv1, lv2, lv3) | medium | shop kind 1 of Item+0x4C[kind*3 + level - 1] (shop::Data::UpdateStock); Paragon 'dusk_stock' (fact) |
| +0x052 | 3 | `u8[3]` | rod_stock (lv1, lv2, lv3) | medium | shop kind 2 of Item+0x4C[kind*3 + level - 1] (shop::Data::UpdateStock); Paragon 'rod_stock' (fact) |
| +0x055 | 3 | `u8[3]` | staff_stock (lv1, lv2, lv3) | medium | shop kind 3 of Item+0x4C[kind*3 + level - 1] (shop::Data::UpdateStock); Paragon 'staff_stock' (fact) |
| +0x058 | 8 | `s8[8]` | pool_rank (gain0_hoshido, gain0_nohr, gain1_hoshido, gain1_nohr, gain2_hoshido, gain2_nohr, lottery_hoshido, lottery_nohr) | high | event::Informal GainItemEnumerator::IsExclusion 004319D8: for item table type 0 the item is in the random-gain pool when +0x58[side] >= 0 and <= the scenario rank; for types 1/2 +0x5A[side] / +0x5C[side] (GetRandomItem 00430E44: side 0 on Birthright; 1 on Conquest; random on Revelation); ItemEnumeratorLottery::IsExclusion 0033AF60: lottery rank (1-5) is +0x5E[origin - 1] (Lottery::CalculateItem); -1 = never; WAS named shop_misc with Paragon's element names (hoshido/nohr event; dawn/dusk lottery; hoshido_1/2; nohr_1/2) which do not match the code: the lottery bytes are the last two |
| +0x060 | 4 | `str` | com | low | data: 56 records name a script/effect string; Paragon 'com' (fact) |
| +0x064 | 2 | `u16` | unknown_64 | low | handicap::..::CalculateUnitItem reads +0x64 (u16) |
| +0x066 | 1 | `u8` | unknown_66 | low | data 0-7 |
| +0x067 | 1 | `u8` | weapon_rank_2 | low | handicap::..::CalculateUnitItem reads +0x67; same value set as +0x1C |

### ItemFlag

ID list ISID_: bit numbers of Item.flags (Item::IsMagic tests ISID_ magic weapon). File `GameData/GameData.bin.lz`; start `family:ISID_`; count `family:ISID_`; record size 0x4; 64 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `u32` | number | high | ID list: the record's label is the ID name; the number is the bit (flags) or value it stands for (PrivateSkill::Get returns this record; 1<<number is the mask) |

### ItemUse

ID list IUID_: item use effects (IUID_回復 heal, IUID_クラスチェンジ class change...); no Item field mapped to it yet. File `GameData/GameData.bin.lz`; start `family:IUID_`; count `family:IUID_`; record size 0x4; 20 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `u32` | number | high | ID list: the record's label is the ID name; the number is the bit (flags) or value it stands for (PrivateSkill::Get returns this record; 1<<number is the mask) |

### TerrainHeader

Per-chapter terrain file header: tile table, tile count, map model, grid (Terrain::Initialize(const char*)). File `GameData/Terrain/*.bin.lz`; start `0`; count `one`; record size 0x10; 109 in 109 files records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `ptr:TerrainTile` | tile_table | high | points at the first TID_ record in every terrain file (Terrain::Initialize(const char*) 004E0A2C loads the file) |
| +0x004 | 4 | `u32` | tile_count | high | equals the number of TID_ labels in every file |
| +0x008 | 4 | `str` | map_model | medium | data: Btl_* / map model names; Paragon FE14 Terrain.yml 'map_model' (fact) |
| +0x00C | 4 | `ptr:TerrainGrid` | grid | high | points at the 0x418-byte grid that ends every file |

### TerrainTile

Per-chapter terrain types (TID_): movement cost class, defence/avoid/heal bonuses. File `GameData/Terrain/*.bin.lz`; start `[0x0]`; count `u32@0x4`; record size 0x28; 1066 in 109 files records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `str:self` | tid | high | record label = this string |
| +0x004 | 4 | `str` | mtid_name | high | Terrain::GetName 005453D0 reads +0x4 (MTID_ message) |
| +0x008 | 4 | `pad` | pad_08 | high | zero in every record of every file |
| +0x00C | 1 | `u8` | tile_number | high | read by 16 functions (ObstacleAcquisition/trick::Data::Mutation...); equals the record index in its file |
| +0x00D | 3 | `u8[3]` | change_to (1, 2, 3) | medium | map::Trick::Deserialize / trick::Data::Mutation / TerrainAttributeSetTID read +0xD..+0xF (tile it turns into: index in the same file); Paragon change_id_1..3 (fact) |
| +0x010 | 1 | `u8` | move_cost_column | high | map::Image::Update / Terrain::IsCastleUnitDispos / Dispos::Data::Calculate read +0x10 (25 functions) (column in the movement-cost table) |
| +0x011 | 1 | `s8` | defense | high | AIThink::GetTerrainScore / map::Route::TickMindSeek read +0x11 (s8) |
| +0x012 | 1 | `s8` | avoid | high | AIThink::GetTerrainScore / map::Route::TickMindSeek read +0x12 (s8) |
| +0x013 | 1 | `s8` | heal | high | ProcTerrainHeal::Calculate / ProcTerrainDamage::Calculate read +0x13 (s8; negative = damage) |
| +0x014 | 1 | `u8` | minimap_color | medium | map::MiniMap::Update reads +0x14 |
| +0x015 | 3 | `pad` | pad_15 | high | zero in every record |
| +0x018 | 4 | `u32` | attributes | medium | read by 43 functions (BattleUtil::IsChangeBattle FieldTrick::Update ItemHelper::Battle::CanUse...) as a bit set |
| +0x01C | 4 | `str` | unknown_str_1c | low | FieldTrick::Update reads +0x1C; set in 2 records |
| +0x020 | 4 | `str` | unknown_str_20 | low | SequenceBattle::..::Destroy reads +0x20; set in 3 records |
| +0x024 | 4 | `str` | effect | medium | castle::Actor::MovePlayer reads +0x24; data FLAT1-style ground-effect names; Paragon 'effect' (fact) |

### TerrainGrid

Per-chapter map grid: sizes and a 32x32 tile-index grid (indexes into that file's TerrainTile records). File `GameData/Terrain/*.bin.lz`; start `[0xC]`; count `one`; record size 0x418; 109 in 109 files records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `u32` | map_width | high | map::Image::Update 0038F96C copies +0x0 into image byte 0 and loops x below it when it builds the movement-cost grid; data 15..32; Paragon FE14 Terrain.yml Grid (fact) |
| +0x004 | 4 | `u32` | map_height | high | map::Image::Update copies +0x4 into image byte 1 and loops y below it; data 15..32; Paragon (fact) |
| +0x008 | 4 | `u32` | play_x_min | high | map::Image::Update copies +0x8 into image byte 2; map::Dispos::Data::IsEnable 005278DC and SortiePosition::AddData 00361690 refuse x below it (left edge of the playable area); 1 in every file; Paragon 'border_width' (fact) |
| +0x00C | 4 | `u32` | play_y_min | high | map::Image::Update copies +0xC into image byte 3; IsEnable and SortiePosition::AddData refuse y below it (top edge of the playable area); 1 in every file; Paragon 'border_height' (fact) |
| +0x010 | 4 | `u32` | play_x_end | high | map::Image::Update copies +0x10 into image byte 4; IsEnable and SortiePosition::AddData require x below it (playable area ends before this column); map_width - 1 in every file; Paragon 'effective_width' (fact) |
| +0x014 | 4 | `u32` | play_y_end | high | map::Image::Update copies +0x14 into image byte 5; IsEnable and SortiePosition::AddData require y below it; map_height - 1 in every file; Paragon 'effective_height' (fact) |
| +0x018 | 1024 | `hex[1024]` | tiles | high | 32x32 bytes; map::Image::Update copies these 0x400 bytes to image+0x408 and map::Dispos::Calculate 0039EF34 reads image+0x408+(x \| y << 5) then Terrain::Get(tile): row-major with 32 bytes per row; each byte is a TerrainTile index of the same file (all values < tile_count) |

### DisposFaction

Per-chapter unit groups (Player, Enemy, ReinforceNN...): name, first unit, unit count (map::Dispos::Header, map::Dispos::Calculate reads +0x4/+0x8). File `GameData/Dispos/*.bin.lz` `GameData/Dispos/A/*.bin.lz` `GameData/Dispos/B/*.bin.lz` `GameData/Dispos/C/*.bin.lz`; start `0`; count `zterm`; record size 0xC; 1330 in 185 files records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `str` | group | high | data: Player / Enemy / ReinforceNN / EventNN ... group names; the list ends with an all-zero entry |
| +0x004 | 4 | `ptr:DisposUnit` | first_unit | high | map::Dispos::Calculate(map::Dispos::Header*;unsigned int) 0039EF34 reads +0x4; every group's units follow the previous group's (185/185 files) |
| +0x008 | 4 | `u32` | unit_count | high | map::Dispos::Calculate reads +0x8; first_unit + count x 0x8C reaches the next group / end of data in every file |

### DisposUnit

Per-chapter unit placements: character, class, level, position, items, skills, AI (map::Dispos::Data, Unit::SetDispos). File `GameData/Dispos/*.bin.lz` `GameData/Dispos/A/*.bin.lz` `GameData/Dispos/B/*.bin.lz` `GameData/Dispos/C/*.bin.lz`; start `[0x4]`; count `span`; record size 0x8C; 9601 in 185 files records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `str` | pid | high | Unit::CreateFromDispos 003D60D8 and Dispos::Data::GetUnit read +0x0; data PID_ strings |
| +0x004 | 4 | `str` | jid | high | Unit::CreateFromDispos and Dispos::Data::UnitMove read +0x4; data JID_ (empty = the person's own class) |
| +0x008 | 1 | `u8` | team | high | map::Dispos::Data::IsEnable 005278DC and Dispos::Data::GetUnit 0039E43C pass +0x8 to Force::Get(Force::Type) (the unit's army; GetUnit makes no unit once that army holds 50); values 0-2 (0 = player: the only team map::Dispos::Calculate turns into deployment slots); Paragon 'team' (fact) |
| +0x009 | 1 | `u8` | level | high | Unit::CreateFromDispos reads +0x9 (0 = the person's own level) |
| +0x00A | 2 | `u8[2]` | pos_start (x, y) | medium | map::Dispos::Data::IsEnable 005278DC requires +0xA/+0xB (s8) to be >= 0 and below the map size (image bytes 0/1); Dispos::Data::Calculate copies them next to +0xC/+0xD; differs from pos in 1042 of 9601 units (where the unit appears before it moves to pos: not traced); Paragon 'coord_1' (fact) |
| +0x00C | 2 | `u8[2]` | pos (x, y) | high | Unit::SetDispos 003D92FC and Dispos::Data::Calculate read +0xC/+0xD (map position); map::Dispos::Data::IsEnable 005278DC leaves the unit out unless play_x_min <= x < play_x_end and play_y_min <= y < play_y_end (TerrainGrid; flags bit 0x8000: anywhere on the map) |
| +0x00E | 2 | `pad` | pad_0e | high | zero in every unit of every file |
| +0x010 | 4 | `u32` | flags | high | map::Dispos::Data::IsEnable 005278DC: bit 8/9/10 (0x100/0x200/0x400) = the unit is used on Normal/Hard/Lunatic (GameUserData+0x2D); 0x8000 = position may be outside the playable area; bit 0 = left out when its tile is taken; map::Dispos::Calculate 0039EF34: 0x10000 = the next unit of the group is paired with this one (Unit::DoubleOn); Dispos::Data::GetUnit: 0x40 = never created by GetUnit; Unit::CreateFromDispos also reads it; other bits not traced; Paragon spawn_flags (fact) |
| +0x014 | 4 | `str` | item_1 | high | data IID_ strings; Unit::SetDisposItem 003D8C38 fills the unit's item slots |
| +0x018 | 1 | `u8` | item_1_flags | high | Unit::SetDisposItem 003D8C38: bit 0 marks the unit item (unit::Item+0x2 bit 15; kept only for some ISID flags); bits 1-4 give the item only at some levels (bit 1: unpromoted level <= 20; bit 2: level >= 21 or promoted; bit 3: level <= 30 and promoted level <= 10; bit 4: level >= 31 or promoted level >= 11); Paragon item_flags (fact); WAS the first byte of item_N_flags (u8[4]) |
| +0x019 | 3 | `s8[3]` | item_1_forge (normal, hard, lunatic) | high | Unit::SetDisposItem 003D8C38 reads entry+0x5+difficulty (s8; GameUserData+0x2D): forge rank on Normal/Hard/Lunatic; negative = the item is not given on that difficulty; WAS the last three bytes of item_N_flags (u8[4]) |
| +0x01C | 4 | `str` | item_2 | high | data IID_ strings |
| +0x020 | 1 | `u8` | item_2_flags | high | as item_1_flags (Unit::SetDisposItem; item slot 2) |
| +0x021 | 3 | `s8[3]` | item_2_forge (normal, hard, lunatic) | high | as item_1_forge (item slot 2) |
| +0x024 | 4 | `str` | item_3 | high | data IID_ strings |
| +0x028 | 1 | `u8` | item_3_flags | high | as item_1_flags (Unit::SetDisposItem; item slot 3) |
| +0x029 | 3 | `s8[3]` | item_3_forge (normal, hard, lunatic) | high | as item_1_forge (item slot 3) |
| +0x02C | 4 | `str` | item_4 | high | data IID_ strings |
| +0x030 | 1 | `u8` | item_4_flags | high | as item_1_flags (Unit::SetDisposItem; item slot 4) |
| +0x031 | 3 | `s8[3]` | item_4_forge (normal, hard, lunatic) | high | as item_1_forge (item slot 4) |
| +0x034 | 4 | `str` | item_5 | high | data IID_ strings |
| +0x038 | 1 | `u8` | item_5_flags | high | as item_1_flags (Unit::SetDisposItem; item slot 5) |
| +0x039 | 3 | `s8[3]` | item_5_forge (normal, hard, lunatic) | high | as item_1_forge (item slot 5) |
| +0x03C | 4 | `str` | skill_1 | high | data SEID_ strings |
| +0x040 | 4 | `str` | skill_2 | high | data SEID_ strings |
| +0x044 | 4 | `str` | skill_3 | high | data SEID_ strings |
| +0x048 | 4 | `str` | skill_4 | high | data SEID_ strings |
| +0x04C | 4 | `str` | skill_5 | high | data SEID_ strings |
| +0x050 | 4 | `u32` | skill_flags | medium | Unit::SetDispos reads +0x50 (u32); Paragon 'skill_flags' (fact) |
| +0x054 | 4 | `str` | ai_action | high | data AI_AC_ strings; Paragon (fact) |
| +0x058 | 4 | `str` | ai_action_param | medium | data; Paragon (fact) |
| +0x05C | 4 | `str` | ai_mission | high | data AI_MI_ strings; Paragon (fact) |
| +0x060 | 4 | `str` | ai_mission_param | medium | data; Paragon (fact) |
| +0x064 | 4 | `str` | ai_attack | high | data AI_AT_ strings; Paragon (fact) |
| +0x068 | 4 | `str` | ai_attack_param | medium | data; Paragon (fact) |
| +0x06C | 4 | `str` | ai_move | high | data AI_MV_ strings; Paragon (fact) |
| +0x070 | 4 | `str` | ai_move_param | medium | data; Paragon (fact) |
| +0x074 | 10 | `u8[10]` | ai_params (0, 1, 2, 3, 4, 5, 6, 7, 8, 9) | medium | Unit::SetDispos reads each byte +0x74..+0x7D into the unit's AI state; Paragon ai_unknown_1/2 (fact) |
| +0x07E | 2 | `pad` | pad_7e | high | zero in every unit |
| +0x080 | 4 | `u32` | ai_flags | medium | Unit::SetDispos reads +0x80 (u32) |
| +0x084 | 1 | `u8` | sortie_flag | medium | run-time state: map::Dispos::CreateProcess 0039DB78 zeroes +0x84..+0x89 of every unit of a group and Calculate / GetUnit write 2/3/4 into +0x84 while the map runs (the file is used in place); zero in every vanilla unit: keep 0 |
| +0x085 | 3 | `pad` | pad_85 | high | zero in every unit; run-time scratch (map::Dispos::CreateProcess zeroes +0x85..+0x89; Calculate reads +0x85 as a UnitPool index) |
| +0x088 | 4 | `pad` | pad_88 | high | zero in every unit |

### Personality

Avatar boons and banes (Personality::Initialize(const void*,int) gets header +0x1C/+0x20; Personality::Get(int) = table+i*0x40): base, growth and maximum-stat modifiers. File `GameData/GameData.bin.lz`; start `[0x1C]`; count `u32@0x20`; record size 0x40; 9 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `u32` | personality_number | medium | equals the record index in every record (Personality::Get(int) = table+i*0x40); no read seen |
| +0x004 | 4 | `str` | mid_name | medium | data: MID_ name message of the boon/bane in every record; no read seen yet |
| +0x008 | 4 | `str` | mid_help | medium | data: MID_H_ description message in every record; no read seen yet |
| +0x00C | 8 | `s8[8]` | boon_base (hp, str, mag, skl, spd, lck, def, res) | high | unit::Edit::GetCapability 0053ABEC reads +0xC[i] (s8); Personality::GetEnhanceCastle 005088C0 picks the stat (1..7) with the largest +0xD..+0x13 |
| +0x014 | 8 | `s8[8]` | boon_growth (hp, str, mag, skl, spd, lck, def, res) | high | unit::Edit::GetGrow 0053AC20 and unit::Family::ParentSingle::GetGrow 0053B740 read +0x14[i] (s8) |
| +0x01C | 8 | `s8[8]` | boon_limit (hp, str, mag, skl, spd, lck, def, res) | high | unit::Edit::GetLimit 0053AC54 and unit::Family::GetLimit 0053BDC4 read +0x1C[i] (s8) (maximum-stat modifier) |
| +0x024 | 8 | `s8[8]` | bane_base (hp, str, mag, skl, spd, lck, def, res) | high | unit::Edit::GetCapability reads +0x24[i] (s8) next to +0xC[i]; data: no positive values |
| +0x02C | 8 | `s8[8]` | bane_growth (hp, str, mag, skl, spd, lck, def, res) | high | unit::Edit::GetGrow and unit::Family::ParentSingle::GetGrow read +0x2C[i] (s8) |
| +0x034 | 8 | `s8[8]` | bane_limit (hp, str, mag, skl, spd, lck, def, res) | high | unit::Edit::GetLimit and unit::Family::GetLimit read +0x34[i] (s8) |
| +0x03C | 1 | `s8` | dual_group | medium | PersonEnhanceDual::GetEdit 0050CADC compares +0x3C (s8) of the boon and the bane personality (-1 = none) before adding pair-up bonuses |
| +0x03D | 3 | `u8[3]` | dual_stats | low | data: stat numbers 1..7 (str..res) in every record but the first; no read found yet |

### ItemKind

Weapon kinds (sword, lance, axe, dagger, bow, tome, staff, special, item) (ItemKind::Initialize gets header +0x30; ItemKind::Get(int) = table+i*0xC); no stored count. File `GameData/GameData.bin.lz`; start `[0x30]`; count `fixed:9`; record size 0xC; 9 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `u32` | kind_number | high | equals the record index (ItemKind::Get(int) = table+i*0xC); castle::cut::CanBattle reads +0x0 |
| +0x004 | 4 | `str` | mikid_name | medium | data: MIKID_ name message in every record; no read seen yet |
| +0x008 | 4 | `str` | mikid_help | high | ItemKind::GetHelp 005460A4 reads +0x8 (MIKID_H_ message) |

### ItemSubKind

Weapon sub-kinds, the value of Item.weapon_kind (ItemSubKind::Initialize gets header +0x34; ItemSubKind::Get(int) = table+i*0x10): kind, Hoshido/Nohr origin, refine group. File `GameData/GameData.bin.lz`; start `[0x34]`; count `fixed:21`; record size 0x10; 21 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 1 | `u8` | subkind_number | medium | equals the record index in every record (ItemSubKind::Get(int) = table+i*0x10) |
| +0x001 | 1 | `ref8:ItemKind` | kind | high | Unit::GetHit 00532DC4 / Unit::GetAttack pass ItemSubKind::Get(Item+0x1A)+0x1 to WeaponBonus::Get(ItemKind::Type); map::BattleInfo::CalculateDetail uses it to index the weapon triangle (80 functions read +0x1) |
| +0x002 | 1 | `u8` | origin | medium | anonymous_namespace::ItemGetOrigin 003A8AE4 and spot::WeaponEnumerator::IsExclusion read +0x2; values 0-2 (data: the Hoshido-style kinds and the Nohr-style kinds differ) |
| +0x003 | 1 | `s8` | refine_group | medium | ProcSequence::CreateGemstoneMenu / ItemRefineMenu::DrawWindow / ItemRefineMenuItem::ACall / IsDecideDisable read +0x3 (s8); -1 on staves, stones and items |
| +0x004 | 4 | `str` | mikid_name | medium | data: MIKID_ name message in every record; no read seen yet |
| +0x008 | 4 | `str` | mikid_help | high | ItemSubKind::GetHelp 00508710 reads +0x8 (MIKID_H_ message) |
| +0x00C | 4 | `u32` | skill_flags | medium | map::BattleCalculator::CalculateAttackSingle 003628BC tests bit 0 and bit 1 of +0xC before rolling (different) skill activations; AIBattleSimulator::CalculateIndication reads it too; values 0-2 |

### ItemRefine

Forge bonus rows (ItemRefine::Initialize gets header +0x38; ItemRefine::Get(row,level) = table+(row*10+level)*4): might/hit/crit per forge level; Item.refine_index picks the row. File `GameData/GameData.bin.lz`; start `[0x38]`; count `fixed:3`; record size 0x28; 3 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `u8[4]` | plus_0 (level, might, hit, crit) | medium | forge level 0 (unforged): same reads as plus_1..; zero in every row |
| +0x004 | 4 | `u8[4]` | plus_1 (level, might, hit, crit) | high | unit::Item::GetPower 0053B4B4 / GetHit 0053B2A4 / GetCritical 0053AD54 read ItemRefine::Get(row; forge level)+0x1 / +0x2 / +0x3 (u8): might / hit / crit added at this forge level; +0x0: data equals the forge level except unused tail entries, no read found |
| +0x008 | 4 | `u8[4]` | plus_2 (level, might, hit, crit) | high | unit::Item::GetPower 0053B4B4 / GetHit 0053B2A4 / GetCritical 0053AD54 read ItemRefine::Get(row; forge level)+0x1 / +0x2 / +0x3 (u8): might / hit / crit added at this forge level; +0x0: data equals the forge level except unused tail entries, no read found |
| +0x00C | 4 | `u8[4]` | plus_3 (level, might, hit, crit) | high | unit::Item::GetPower 0053B4B4 / GetHit 0053B2A4 / GetCritical 0053AD54 read ItemRefine::Get(row; forge level)+0x1 / +0x2 / +0x3 (u8): might / hit / crit added at this forge level; +0x0: data equals the forge level except unused tail entries, no read found |
| +0x010 | 4 | `u8[4]` | plus_4 (level, might, hit, crit) | high | unit::Item::GetPower 0053B4B4 / GetHit 0053B2A4 / GetCritical 0053AD54 read ItemRefine::Get(row; forge level)+0x1 / +0x2 / +0x3 (u8): might / hit / crit added at this forge level; +0x0: data equals the forge level except unused tail entries, no read found |
| +0x014 | 4 | `u8[4]` | plus_5 (level, might, hit, crit) | high | unit::Item::GetPower 0053B4B4 / GetHit 0053B2A4 / GetCritical 0053AD54 read ItemRefine::Get(row; forge level)+0x1 / +0x2 / +0x3 (u8): might / hit / crit added at this forge level; +0x0: data equals the forge level except unused tail entries, no read found |
| +0x018 | 4 | `u8[4]` | plus_6 (level, might, hit, crit) | high | unit::Item::GetPower 0053B4B4 / GetHit 0053B2A4 / GetCritical 0053AD54 read ItemRefine::Get(row; forge level)+0x1 / +0x2 / +0x3 (u8): might / hit / crit added at this forge level; +0x0: data equals the forge level except unused tail entries, no read found |
| +0x01C | 4 | `u8[4]` | plus_7 (level, might, hit, crit) | high | unit::Item::GetPower 0053B4B4 / GetHit 0053B2A4 / GetCritical 0053AD54 read ItemRefine::Get(row; forge level)+0x1 / +0x2 / +0x3 (u8): might / hit / crit added at this forge level; +0x0: data equals the forge level except unused tail entries, no read found |
| +0x020 | 4 | `u8[4]` | plus_8 (level, might, hit, crit) | high | unit::Item::GetPower 0053B4B4 / GetHit 0053B2A4 / GetCritical 0053AD54 read ItemRefine::Get(row; forge level)+0x1 / +0x2 / +0x3 (u8): might / hit / crit added at this forge level; +0x0: data equals the forge level except unused tail entries, no read found |
| +0x024 | 4 | `u8[4]` | plus_9 (level, might, hit, crit) | high | unit::Item::GetPower 0053B4B4 / GetHit 0053B2A4 / GetCritical 0053AD54 read ItemRefine::Get(row; forge level)+0x1 / +0x2 / +0x3 (u8): might / hit / crit added at this forge level; +0x0: data equals the forge level except unused tail entries, no read found |

### WeaponLevel

Weapon rank thresholds S..E (WeaponLevel::Initialize gets header +0x3C; WeaponLevel::GetLevel(int) compares weapon exp with them). File `GameData/GameData.bin.lz`; start `[0x3C]`; count `one`; record size 0x8; 1 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 6 | `u8[6]` | threshold (s, a, b, c, d, e) | high | WeaponLevel::GetLevel(int) 005090A4 compares weapon exp with +0x0[i] for i = 0..5 and returns the first rank reached (0 = S .. 5 = E; 6 = none); spot::SetDisposUnitItem reads +0x0..+0x5 one by one; ArenaData::CalculateEnemy / Unit::CaclulateFirstWeaponExp read single ranks |
| +0x006 | 2 | `pad` | pad_06 | high | zero; GetLevel never reads past +0x5 |

### WeaponBonus

Weapon rank bonuses per weapon kind (WeaponBonus::Initialize gets header +0x40; WeaponBonus::Get(ItemKind::Type) = table+kind*0xC; Unit::GetHit/GetAttack only call it for kinds < 8). File `GameData/GameData.bin.lz`; start `[0x40]`; count `fixed:8`; record size 0xC; 8 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 2 | `s8[2]` | rank_s (attack, hit) | high | Unit::GetAttack 005342B8 reads WeaponBonus::Get(kind)+rank*2 (s8; rank from WeaponLevel::GetLevel) and Unit::GetHit 00532DC4 reads +rank*2+1; Unit::GetRodHealPower reads the staff row (kind 6) +rank*2 |
| +0x002 | 2 | `s8[2]` | rank_a (attack, hit) | high | Unit::GetAttack 005342B8 reads WeaponBonus::Get(kind)+rank*2 (s8; rank from WeaponLevel::GetLevel) and Unit::GetHit 00532DC4 reads +rank*2+1; Unit::GetRodHealPower reads the staff row (kind 6) +rank*2 |
| +0x004 | 2 | `s8[2]` | rank_b (attack, hit) | high | Unit::GetAttack 005342B8 reads WeaponBonus::Get(kind)+rank*2 (s8; rank from WeaponLevel::GetLevel) and Unit::GetHit 00532DC4 reads +rank*2+1; Unit::GetRodHealPower reads the staff row (kind 6) +rank*2 |
| +0x006 | 2 | `s8[2]` | rank_c (attack, hit) | high | Unit::GetAttack 005342B8 reads WeaponBonus::Get(kind)+rank*2 (s8; rank from WeaponLevel::GetLevel) and Unit::GetHit 00532DC4 reads +rank*2+1; Unit::GetRodHealPower reads the staff row (kind 6) +rank*2 |
| +0x008 | 2 | `s8[2]` | rank_d (attack, hit) | high | Unit::GetAttack 005342B8 reads WeaponBonus::Get(kind)+rank*2 (s8; rank from WeaponLevel::GetLevel) and Unit::GetHit 00532DC4 reads +rank*2+1; Unit::GetRodHealPower reads the staff row (kind 6) +rank*2 |
| +0x00A | 2 | `s8[2]` | rank_e (attack, hit) | high | Unit::GetAttack 005342B8 reads WeaponBonus::Get(kind)+rank*2 (s8; rank from WeaponLevel::GetLevel) and Unit::GetHit 00532DC4 reads +rank*2+1; Unit::GetRodHealPower reads the staff row (kind 6) +rank*2 |

### WeaponInteract

Weapon triangle (WeaponInteract::Initialize gets header +0x44): rank-scaled bonus plus the 8x8 advantage matrix of weapon kinds. File `GameData/GameData.bin.lz`; start `[0x44]`; count `one`; record size 0x4C; 1 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 2 | `s8[2]` | rank_s (attack, hit) | high | map::BattleInfo::Side::CalculateDetailAttack 00349A60 reads WeaponInteract::Get()+rank*2 (s8) and CalculateDetailHit 00349128 reads +rank*2+1, each times the advantage (+1 / -1) |
| +0x002 | 2 | `s8[2]` | rank_a (attack, hit) | high | map::BattleInfo::Side::CalculateDetailAttack 00349A60 reads WeaponInteract::Get()+rank*2 (s8) and CalculateDetailHit 00349128 reads +rank*2+1, each times the advantage (+1 / -1) |
| +0x004 | 2 | `s8[2]` | rank_b (attack, hit) | high | map::BattleInfo::Side::CalculateDetailAttack 00349A60 reads WeaponInteract::Get()+rank*2 (s8) and CalculateDetailHit 00349128 reads +rank*2+1, each times the advantage (+1 / -1) |
| +0x006 | 2 | `s8[2]` | rank_c (attack, hit) | high | map::BattleInfo::Side::CalculateDetailAttack 00349A60 reads WeaponInteract::Get()+rank*2 (s8) and CalculateDetailHit 00349128 reads +rank*2+1, each times the advantage (+1 / -1) |
| +0x008 | 2 | `s8[2]` | rank_d (attack, hit) | high | map::BattleInfo::Side::CalculateDetailAttack 00349A60 reads WeaponInteract::Get()+rank*2 (s8) and CalculateDetailHit 00349128 reads +rank*2+1, each times the advantage (+1 / -1) |
| +0x00A | 2 | `s8[2]` | rank_e (attack, hit) | high | map::BattleInfo::Side::CalculateDetailAttack 00349A60 reads WeaponInteract::Get()+rank*2 (s8) and CalculateDetailHit 00349128 reads +rank*2+1, each times the advantage (+1 / -1). WeaponLevel::GetLevel 005090A4 can also return 6 (below the E threshold); rank 6 would read +0xC, the first attacker_sword entry, so no separate rank-none row exists (not seen with a weapon equipped) |
| +0x00C | 8 | `s8[8]` | attacker_sword (sword, lance, axe, dagger, bow, tome, staff, special) | high | map::BattleInfo::CalculateDetail 00347A6C and map::CannonCalculator::Calculate read WeaponInteract::Get()+0xC+attacker_kind*8+defender_kind (s8; kinds from ItemSubKind.kind): +1 advantage, -1 disadvantage |
| +0x014 | 8 | `s8[8]` | attacker_lance (sword, lance, axe, dagger, bow, tome, staff, special) | high | map::BattleInfo::CalculateDetail 00347A6C and map::CannonCalculator::Calculate read WeaponInteract::Get()+0xC+attacker_kind*8+defender_kind (s8; kinds from ItemSubKind.kind): +1 advantage, -1 disadvantage |
| +0x01C | 8 | `s8[8]` | attacker_axe (sword, lance, axe, dagger, bow, tome, staff, special) | high | map::BattleInfo::CalculateDetail 00347A6C and map::CannonCalculator::Calculate read WeaponInteract::Get()+0xC+attacker_kind*8+defender_kind (s8; kinds from ItemSubKind.kind): +1 advantage, -1 disadvantage |
| +0x024 | 8 | `s8[8]` | attacker_dagger (sword, lance, axe, dagger, bow, tome, staff, special) | high | map::BattleInfo::CalculateDetail 00347A6C and map::CannonCalculator::Calculate read WeaponInteract::Get()+0xC+attacker_kind*8+defender_kind (s8; kinds from ItemSubKind.kind): +1 advantage, -1 disadvantage |
| +0x02C | 8 | `s8[8]` | attacker_bow (sword, lance, axe, dagger, bow, tome, staff, special) | high | map::BattleInfo::CalculateDetail 00347A6C and map::CannonCalculator::Calculate read WeaponInteract::Get()+0xC+attacker_kind*8+defender_kind (s8; kinds from ItemSubKind.kind): +1 advantage, -1 disadvantage |
| +0x034 | 8 | `s8[8]` | attacker_tome (sword, lance, axe, dagger, bow, tome, staff, special) | high | map::BattleInfo::CalculateDetail 00347A6C and map::CannonCalculator::Calculate read WeaponInteract::Get()+0xC+attacker_kind*8+defender_kind (s8; kinds from ItemSubKind.kind): +1 advantage, -1 disadvantage |
| +0x03C | 8 | `s8[8]` | attacker_staff (sword, lance, axe, dagger, bow, tome, staff, special) | high | map::BattleInfo::CalculateDetail 00347A6C and map::CannonCalculator::Calculate read WeaponInteract::Get()+0xC+attacker_kind*8+defender_kind (s8; kinds from ItemSubKind.kind): +1 advantage, -1 disadvantage |
| +0x044 | 8 | `s8[8]` | attacker_special (sword, lance, axe, dagger, bow, tome, staff, special) | high | map::BattleInfo::CalculateDetail 00347A6C and map::CannonCalculator::Calculate read WeaponInteract::Get()+0xC+attacker_kind*8+defender_kind (s8; kinds from ItemSubKind.kind): +1 advantage, -1 disadvantage |

### ExpTableHeader

Experience tables header (ExpTable::Initialize gets header +0x48): six pointers, one per sub-table; every sub-table has one row per difficulty (GameUserData+0x2D). File `GameData/GameData.bin.lz`; start `[0x48]`; count `one`; record size 0x18; 1 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `ptr:ExpBattle` | battle | high | ExpTable::GetBattle(int) 004E6368 reads [ExpTable+0x0] (row stride 0x48) |
| +0x004 | 4 | `ptr:ExpBattleFloor` | battle_threshold | high | ExpTable::GetBattleThreshold(int) 004E6314 reads [ExpTable+0x4] (row stride 0x18) |
| +0x008 | 4 | `ptr:ExpRod` | rod_decline | high | ExpTable::GetRodDecline(int) 004E62C4 reads [ExpTable+0x8] (row stride 0x28) |
| +0x00C | 4 | `ptr:ExpRodHigh` | rod_high_decline | high | ExpTable::GetRodHighDecline(int) 004E62E0 reads [ExpTable+0xC] (row stride 4) |
| +0x010 | 4 | `ptr:ExpDance` | dance | high | ExpTable::GetDance(int) 004E634C reads [ExpTable+0x10] (row stride 0x28) |
| +0x014 | 4 | `ptr:ExpSupport` | support_decline | high | ExpTable::GetSupportDecline(int) 004E62F8 reads [ExpTable+0x14] (row stride 0x28) |

### ExpBattle

Experience for damaging and for defeating an enemy, by level difference (ExpTable::GetBattle(int) = [ExpTable+0x0]+row*0x48). File `GameData/GameData.bin.lz`; start `[[0x48]]`; count `fixed:3`; record size 0x48; 3 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 34 | `s8[34]` | damage | high | Unit::GetExpDamage 0052D418 reads GetBattle(difficulty)[i] (s8) with i = enemy level - own level + 10 clamped to 0..33 |
| +0x022 | 2 | `pad` | pad_22 | high | zero in every row; index clamped to 33 |
| +0x024 | 34 | `s8[34]` | defeat | high | Unit::GetExpDestroy 0052E184 reads GetBattle(difficulty)+0x24[i] (s8), same index rule |
| +0x046 | 2 | `pad` | pad_46 | high | zero in every row; index clamped to 33 |

### ExpBattleFloor

Minimum battle experience against high-level enemies (ExpTable::GetBattleThreshold(int) = [ExpTable+0x4]+row*0x18). File `GameData/GameData.bin.lz`; start `[[0x48]+0x4]`; count `fixed:3`; record size 0x18; 3 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 10 | `s8[10]` | damage_min | high | Unit::GetExpDamage reads GetBattleThreshold(difficulty)[i] (s8), i = enemy level - 31 clamped to 0..9, and uses it when it is larger than the ExpBattle value |
| +0x00A | 2 | `pad` | pad_0a | high | zero in every row; index clamped to 9 |
| +0x00C | 10 | `s8[10]` | defeat_min | high | Unit::GetExpDestroy 0052E184 reads GetBattleThreshold(difficulty)+0xC[i] (s8), same rule |
| +0x016 | 2 | `pad` | pad_16 | high | zero in every row; index clamped to 9 |

### ExpRod

Staff experience change by the healer's level (ExpTable::GetRodDecline(int) = [ExpTable+0x8]+row*0x28). File `GameData/GameData.bin.lz`; start `[[0x48]+0x8]`; count `fixed:3`; record size 0x28; 3 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 40 | `s8[40]` | by_level | high | Unit::GetExpRod 005342F4 adds GetRodDecline(difficulty)[level-1] (s8, index clamped 0..39) to the staff's Item.staff_exp |

### ExpRodHigh

Staff experience change for healers whose class also uses a non-staff weapon (ExpTable::GetRodHighDecline(int) = [ExpTable+0xC]+row*4). File `GameData/GameData.bin.lz`; start `[[0x48]+0xC]`; count `fixed:3`; record size 0x4; 3 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 1 | `s8` | non_staff_class | high | Unit::GetExpRod adds GetRodHighDecline(difficulty)+0 (s8) when the class has a non-zero Job.max_weapon_exp for any weapon other than staff |
| +0x001 | 3 | `pad` | pad_01 | high | zero in every row; only +0x0 is read |

### ExpDance

Dance/sing experience by level (ExpTable::GetDance(int) = [ExpTable+0x10]+row*0x28). File `GameData/GameData.bin.lz`; start `[[0x48]+0x10]`; count `fixed:3`; record size 0x28; 3 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 40 | `s8[40]` | by_level | high | Unit::GetExpDance 0052BAD0 reads GetDance(difficulty)[level-1] (s8, index clamped 0..39) |

### ExpSupport

Experience change by the level gap to the unit helped (staff, dance) (ExpTable::GetSupportDecline(int) = [ExpTable+0x14]+row*0x28). File `GameData/GameData.bin.lz`; start `[[0x48]+0x14]`; count `fixed:3`; record size 0x28; 3 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 40 | `s8[40]` | by_level_gap | high | Unit::GetExpDance and Unit::GetExpRod add GetSupportDecline(difficulty)[i] (s8), i = target level - own level + 39 clamped to 0..39 |

### TerrainCostHeader

Movement-cost table header (TerrainCost::Initialize gets header +0x4C): number of terrain columns per row. File `GameData/GameData.bin.lz`; start `[0x4C]`; count `one`; record size 0x4; 1 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `u32` | columns | high | TerrainCost::Get(int) 001A67EC / GetCostFromUnit 001A6708: row stride = this value rounded up to 4; check.py requires it to equal the TerrainCost record size (16) |

### TerrainCost

Movement cost per class move type (row = Job.move_cost_class) and terrain column (TerrainTile.move_cost_column) (TerrainCost::Get(int) / GetCostFromUnit). File `GameData/GameData.bin.lz`; start `[0x4C]+0x4`; count `fixed:16`; record size 0x10; 16 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 16 | `s8[16]` | cost | high | TerrainCost::GetCostFromUnit 001A6708 reads row Job+0x5C, column = its terrain argument (TerrainTile.move_cost_column) (s8); when the cost is negative and the unit has a SPID_ private-terrain-cost skill bit the game re-reads row 0 (how callers treat negatives is not traced) |

### GameDataUnknown50

Unnamed block at GameData header +0x50 (GameData::Initialize does not pass it on): 16 four-byte entries. File `GameData/GameData.bin.lz`; start `[0x50]`; count `fixed:16`; record size 0x4; 16 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `u8[4]` | entry (r, g, b, a) | low | data: the 4th byte is 0xFF in every entry (looks like RGBA colours); GameData::Initialize 004E6954 does not read header +0x50 and no other reader was found |

### Tutorial

Tutorials (TUTID_) (Tutorial::Initialize(const void*,int) gets header +0x54/+0x58; Tutorial::Get(int) = table+i*0x14). File `GameData/GameData.bin.lz`; start `[0x54]`; count `u32@0x58`; record size 0x14; 34 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `str:self` | tutid | high | record label = this string (TUTID_); Tutorial::Get(const char*) 004F33FC |
| +0x004 | 2 | `s16` | tutorial_number | high | anonymous_namespace::TutorialSetFlag / TutorialShow / sortie::CreateTopMenu read +0x4 (s16; the tutorial-seen flag number); equals the record index |
| +0x006 | 2 | `s16` | variant | medium | Tutorial::GetFileName 00546B00 and GetMessage 0054699C read +0x6 (s16): 1..3 pick a file-name suffix from game settings; values 0-3 |
| +0x008 | 4 | `str` | mtutid_name | high | Tutorial::GetName 00546C88 reads +0x8 (MTUTID_ message) |
| +0x00C | 4 | `str` | mtutid_help | high | Tutorial::GetHelp 00546C60 / GetMessage / GetPageNum read +0xC (MTUTID_H_ message; pages) |
| +0x010 | 4 | `str` | file_name | high | Tutorial::GetFileName reads +0x10 (picture file base name) |

### AchieveBonusHeader

Achievement reward lists header (AchieveBonus::Initialize gets header +0x5C): four {list, count} pairs (GetRoute/GetBattle/GetVisit return the first three). File `GameData/GameData.bin.lz`; start `[0x5C]`; count `one`; record size 0x20; 1 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `ptr:AchieveBonusRoute` | route_list | high | AchieveBonus::Initialize 001A8114 stores header+0x0; AchieveBonus::GetRoute 001A8134 returns it; castle::AchieveBonusMenuItem::Draw reads +0x0 (list) |
| +0x004 | 4 | `u32` | route_count | high | castle::CastleAchieveBonus::CastleAchieveBonus 0045BE70 reads +0x4 of AchieveBonus::GetRoute (entry count); AchieveBonusMenuItem::Draw bounds the index with it |
| +0x008 | 4 | `ptr:AchieveBonusBattle` | battle_list | high | AchieveBonus::Initialize 001A8114 stores header+0x8; AchieveBonus::GetBattle 001A8154 returns it; castle::AchieveBonusMenuItem::Draw reads +0x0 (list) |
| +0x00C | 4 | `u32` | battle_count | high | castle::CastleAchieveBonus::CastleAchieveBonus 0045BE70 reads +0x4 of AchieveBonus::GetBattle (entry count); AchieveBonusMenuItem::Draw bounds the index with it |
| +0x010 | 4 | `ptr:AchieveBonusVisit` | visit_list | high | AchieveBonus::Initialize 001A8114 stores header+0x10; AchieveBonus::GetVisit 001A8144 returns it; castle::AchieveBonusMenuItem::Draw reads +0x0 (list) |
| +0x014 | 4 | `u32` | visit_count | high | castle::CastleAchieveBonus::CastleAchieveBonus 0045BE70 reads +0x4 of AchieveBonus::GetVisit (entry count); AchieveBonusMenuItem::Draw bounds the index with it |
| +0x018 | 4 | `ptr:AchieveBonusList4` | list4_list | high | AchieveBonus::Initialize stores header+0x18 (no named getter reads it) |
| +0x01C | 4 | `u32` | list4_count | medium | data: entry count of list 4 (the list ends where the next block starts) |

### AchieveBonusRoute

Achievement rewards, list 1 (AchieveBonus::GetRoute). File `GameData/GameData.bin.lz`; start `[[0x5C]]`; count `u32@[0x5C]+0x4`; record size 0x8; 8 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 2 | `u16` | requirement | medium | castle::anonymous_namespace::AchieveBonusMenuItem::Draw 0048B2A4 reads entry +0x0 (u16); data: rising thresholds in lists 2-4 |
| +0x002 | 2 | `u16` | requirement_2 | low | data: zero except in list 4; no read found yet |
| +0x004 | 2 | `ref16:Item` | item | medium | data: every value is an Item index (the reward); no read found yet |
| +0x006 | 2 | `pad` | pad_06 | high | zero in every entry (high half of a 32-bit item word) |

### AchieveBonusBattle

Achievement rewards, list 2 (AchieveBonus::GetBattle). File `GameData/GameData.bin.lz`; start `[[0x5C]+0x8]`; count `u32@[0x5C]+0xC`; record size 0x8; 80 records.

Same record layout as [AchieveBonusRoute](#achievebonusroute) (config/tables/AchieveBonusRoute.csv).

### AchieveBonusVisit

Achievement rewards, list 3 (AchieveBonus::GetVisit). File `GameData/GameData.bin.lz`; start `[[0x5C]+0x10]`; count `u32@[0x5C]+0x14`; record size 0x8; 80 records.

Same record layout as [AchieveBonusRoute](#achievebonusroute) (config/tables/AchieveBonusRoute.csv).

### AchieveBonusList4

Achievement rewards, list 4 (no named getter; AchieveBonus::Initialize stores its address). File `GameData/GameData.bin.lz`; start `[[0x5C]+0x18]`; count `u32@[0x5C]+0x1C`; record size 0x8; 24 records.

Same record layout as [AchieveBonusRoute](#achievebonusroute) (config/tables/AchieveBonusRoute.csv).

### ArenaHeader

Arena opponent lists header (Arena::Initialize gets header +0x60): {low list, count}, {high list, count}. File `GameData/GameData.bin.lz`; start `[0x60]`; count `one`; record size 0x10; 1 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `ptr:ArenaLow` | low_list | high | Arena::Initialize 0041C67C stores header+0x0; Arena::GetLow returns it; ArenaData::CalculateEnemy 003B9538 reads +0x0 (list) |
| +0x004 | 4 | `u32` | low_count | high | ArenaData::CalculateEnemy loops while index < +0x4 |
| +0x008 | 4 | `ptr:ArenaHigh` | high_list | high | Arena::Initialize stores header+0x8; Arena::GetHigh 0041C6A0 returns it; CalculateEnemy uses it when its level argument is 21 or more |
| +0x00C | 4 | `u32` | high_count | high | ArenaData::CalculateEnemy loop bound (+0x4 of the GetHigh pair) |

### ArenaLow

Arena opponents, low list (Arena::GetLow; ArenaData::CalculateEnemy uses it below a threshold of 21). File `GameData/GameData.bin.lz`; start `[[0x60]]`; count `u32@[0x60]+0x4`; record size 0x8; 17 records.

| Offset | Size | Type | Name | Conf. | Evidence |
|---|---:|---|---|---|---|
| +0x000 | 4 | `u32` | weight | medium | ArenaData::CalculateEnemy reads entry +0x0 (u32) and subtracts it from a running random number (weighted pick) |
| +0x004 | 2 | `ref16:Job` | job | high | ArenaData::CalculateEnemy passes entry +0x4 (u16) to Job::Get(unsigned short) 00341AA4 |
| +0x006 | 2 | `ref16:Item` | weapon | high | ArenaData::CalculateEnemy passes entry +0x6 (u16) to Item::Get(unsigned short) 003D0EAC and checks the item range (Item+0x28/+0x29) |

### ArenaHigh

Arena opponents, high list (Arena::GetHigh). File `GameData/GameData.bin.lz`; start `[[0x60]+0x8]`; count `u32@[0x60]+0xC`; record size 0x8; 28 records.

Same record layout as [ArenaLow](#arenalow) (config/tables/ArenaLow.csv).

<!-- tables:end -->
