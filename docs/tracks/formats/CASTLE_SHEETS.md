# Castle sheet files — public facts only

ELI5 / ETA: Some castle files are ordinary data files with three named lists inside them. That is not a new file type, and it is not a codec. The row layouts stay in the tool that already reads them. We do not copy that tool.

Status 2026-11-11. No game file opened. No code copied.

## Two different things

The castle folder has ordinary pointer-based `.bin` files. RainThunder's wiki describes that layout and names `castle_person.bin`, `castle_join.bin`, `castle_building.bin`, `castle_food.bin`, and `castle_gemstone.bin`. [high, https://github.com/RainThunder/fefates-tools/wiki/BIN-(File-Format), read 2026-11-11]

Little-endian. A 32-byte header: file size, data size, two pointer counts, then padding. Then the data, a pointer list, pairs of (data offset, label offset), then labels. Labels are Shift-JIS and end in a zero. An unsorted first pointer list still works, on that page. It does not say that about the second list. [high, same page]

That is the file our table tools already read. The sheet shape below sits inside it. It is not a second container.

## The three lists

Paragon's FE14 type files, on the `poetry` branch, describe some of these files as three lists in a row. The type files are GPL-3.0. This note paraphrases them. Do not copy the files. [high, read 2026-11-11. https://github.com/thane98/paragon/blob/poetry/Data/FE14/Types/Sheet.yml and the type files named below]

1. A mod list. A label, a count, then entries. Each entry is a name, a type name, and 12 bytes the type file does not decode. One dining file's type definition appends a label that starts with `MOD_` and then a short name. That is a label string, not a four-byte magic at a fixed offset. [high, Sheet.yml and the dining type file]
2. A data table. A short header: a label, a name, a count, two bytes the type file leaves unknown, then the rows. No file read for this note uses a label that starts with `DAT_`. [gap]
3. A sheet list. A label, a count, then names. The type files append the label `SHEET_LIST`. Each name is a string, not a row of stats. [high, Sheet.yml]

Field kinds those type files use, not the columns: a label, a string, an integer of a stated width, a fixed run of bytes, a message id, a reference to another table, a list whose count lives beside it, a record stored inline or by pointer, and a union. The per-file column lists are in the type files. Do not copy them. Read a row from the file, or write our own layout from that reading. [high, kinds only]

## Which files

Paragon's store list names these paths. A path is not a claim that the three lists are inside it. The three lists are claimed only where a type file was opened. [high, https://github.com/thane98/paragon/blob/poetry/Data/FE14/Stores/Singles.yml]

| path | three lists? |
|---|---|
| `GameData/JobIntro.bin.lz` | yes, one mod list, one table, then `SHEET_LIST` |
| `GameData/AcceShop.bin.lz` | yes, same shape |
| `GameData/Castle/DiningData.bin.lz` | yes, two mod lists and two tables, then `SHEET_LIST` |
| `castle/CastlePerson.bin` | yes, same shape as JobIntro |
| `castle/castle_building.bin.lz` | no. The type file opened for it is a plain row list |
| `GameData/Castle/Butler.bin.lz` | not opened |
| `castle/CastleButlerVoice.bin` | not opened |
| `castle/CastlePosition.bin` | not opened |
| `castle/castle_join.bin.lz` | not opened |
| `castle/castle_init_buildings.bin.lz` | not opened |

`MyRoom` and `Fortune` are not in that store list. They stay unnamed until a page or a file list says they exist. [gap]

RainThunder's page also names `castle_food.bin` and `castle_gemstone.bin`. Paragon's store list, as read, does not. [high, both pages]

## Tools, and their licences

| tool | what it claims | licence | use |
|---|---|---|---|
| Paragon (thane98), `poetry` branch | edits these files as the ordinary `.bin`, using the type files above | GPL-3.0. https://github.com/thane98/paragon | facts only. Do not copy the type files or the Rust |
| Mila (thane98) | reads and writes the ordinary `.bin` for FE13–FE15, plus LZ. Its readme does not mention the three lists | GPL-3.0. https://github.com/thane98/mila | facts only. Do not copy |
| Nightmare, and RainThunder's modules | fixed-size edits of `.bin` files. Cannot add rows by itself | the module text format is on FEUniverse. The program's own licence was not on the page read here | facts only |
| `castle_join.py` in fefates-tools | turns `castle_join.bin` into a text table and back | no licence file on the pages read here. Treat it as all-rights-reserved until one is read | do not copy |
| FEAT (SciresM) | text archives, not these lists | not opened this session | not this tool |

A community tutorial says the castle-join table is where a character is set to join after a chapter is cleared. That is a use, not a field layout. The field names were not copied. [med]

## What Claude should do

Open one file from the yes rows. If it is the ordinary `.bin`, use the table tools. Then look for the three lists by their labels, not by assuming a four-byte magic. If a label starts with `DAT_`, write that down from the file. This note does not have it. Do not copy Paragon's column lists into our layouts. No game bytes in git.
