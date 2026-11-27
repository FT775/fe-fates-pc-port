# RomFS assets: survey, converters and round trips (Fates)

Status: 2026-11-10. Tools live in `tools/assets/` (Python 3.13, standard library only).
Everything they produce from the owner's ROM goes to `extracted/` (RomFS files, reports,
PNG exports) or `build/assets/` (scratch); both are gitignored. This file holds counts,
types, layouts and file *paths* only: no file contents, no game text.

The tools are the Awakening port's (its docs/ASSETS.md explains LZ13, IS .bin, message
archives, CTPK and CGFX in depth; those sections apply unchanged). New for Fates:
`arc.py` handles the Fates `.arc` layout, `bch.py` reads and edits BCH (H3D) files,
`bchwrite.py` rebuilds a BCH around a texture of a new size (section 3.3.1),
`portrait.py` exports a character's portrait layers, and the "stored" wrapper is
understood everywhere. Game constants (product code, ROM path) come from
`config/game.json` through `tools/gamecfg.py`.

Goal (FE8 parity): every asset is either converted to an editable form that rebuilds
byte-identically, or carried as an original blob. Every converter is at **100%** on the
whole RomFS; blob-only formats are listed in section 5.

## 1. Quick start

```bash
python tools/assets/romfs.py                  # unpack the RomFS from the .cci in config/game.json (~12 s) + manifest
python tools/assets/survey.py                 # counts/types report -> extracted/assets/survey.txt
python tools/assets/roundtrip_all.py          # every converter + whole-RomFS chain (~15 min, 12 workers)
python tools/assets/bch.py info  unit/<file>.bch.lz            # sections, resources, textures
python tools/assets/bch.py export IN.bch.lz OUT_DIR             # textures -> PNG + bch.json
python tools/assets/bch.py pack OUT_DIR IN.bch.lz OUT.bch.lz    # edited PNGs back in place
python tools/assets/bch.py pack OUT_DIR IN.bch.lz OUT.bch.lz --allow-resize  # PNGs of a new size
python tools/assets/bchwrite.py selftest                         # resize writer checks (~5 s)
python tools/assets/bchwrite.py test                             # resize writer on every BCH (~1.5 min)
python tools/assets/portrait.py list カミラ                      # FaceData records matching a name
python tools/assets/portrait.py export カミラ build/assets/camilla
python tools/assets/portrait.py import build/assets/camilla mods/MyMod/romfs
python tools/assets/portrait.py import build/assets/camilla mods/MyMod/romfs --allow-resize
python tools/assets/portrait.py etcbench 6                       # ETC encoder quality numbers
python tools/assets/arc.py unpack face/face/<name>_st.arc OUT_DIR  # any .arc <-> member files
```

Paths for `bch.py`/`arc.py` are real file paths (e.g. under `extracted/romfs/`). Set
`PYTHONIOENCODING=utf-8` to see Japanese names on a Windows console (otherwise they print
as `\uXXXX` escapes; files and folders always use the real names).

## 2. Survey (`survey.py`)

**21,880 files, 645 directories, 1,804,271,145 bytes** (2,489,655,567 after
decompression). 5,731 paths have Japanese names. Depth: 2 files at the root, 8,126 one
level down, 9,696 two, 4,056 three.

Compression: **LZ13 13,455**, none 8,395, **stored 30** (see 3.1). No LZ10/LZ11 files
(Awakening's message archives were LZ11; Fates' are LZ13).

| Top-level dir | Files | Bytes | Main contents |
|---|---:|---:|---|
| `sound` | 1,211 | 796,780,070 | `.bcstm` / `.dspadpcm.bcstm` streams, `.aac` voices, `IRON15_sound.bcsar` |
| `movie` | 150 | 516,050,565 | `.moflex` video |
| `field` | 1,095 | 191,173,674 | 3D maps: BCH models (`*.bch.lz`) + textures (`*_t.bch.lz`), `.bin.lz` data |
| `bu` | 1,898 | 78,286,764 | battle units: BCH models + textures |
| `live2d` | 5,637 | 69,759,520 | Live2D: `.moc`, `.mtn`, `.exp.json`, `.json`, CTPK textures |
| `face` | 890 | 39,276,363 | portraits (section 4) |
| `ba` | 3,130 | 31,929,162 | battle animations: BCH skeletal animations |
| `effect` | 300 | 24,816,414 | `.arc.lz`: `model.bch` members + `effect.ptcl` particles |
| `unit` | 3,423 | 15,837,290 | map sprites: BCH textures (one per file) |
| `bx` | 1,112 | 11,997,418 | BCH models / textures / animations |
| `sky` | 20 | 11,275,513 | BCH sky domes |
| `m` | 1,328 | 5,927,869 | message archives (`m/@E`, `m/A`, `m/B`, `m/C`, ...) |
| `GameData` | 567 | 1,251,776 | game tables (IS .bin), per-route folders |
| `Scripts` | 624 | 1,141,872 | `.cmb` event scripts |
| others | 445 | ~12.5 M | `ui`, `tut`, `bp`, `castle`, `font`, `icon`, `scene`, `map`, `debug` (symbol map), ... |

| Extension | Files | Stored bytes | Decompressed | Content |
|---|---:|---:|---:|---|
| `.bch.lz` | 10,743 | 340,393,675 | 801,992,248 | BCH (10,713 LZ13, 30 stored) |
| `.mtn` / `.exp.json` / `.json` / `.moc` | 2,925 / 2,313 / 72 / 71 | ~46 M | | Live2D |
| `.bin.lz` | 2,231 | 13,587,539 | 40,612,838 | 1,328 message archives + 902 IS .bin data + 1 non-IS (`GameData/TextEditor.bin.lz`, not LZ) |
| `.aac` | 1,026 | 43,915,386 | | voice clips |
| `.cmb` | 624 | 1,141,872 | | event scripts |
| `.arc` / `.arc.lz` | 516 / 304 | 37 M / 25 M | 62.6 M (`.arc.lz`) | IS .bin archives (section 3.2) |
| `.bin` | 506 | 1,448,319 | | IS .bin data |
| `.ctpk.lz` | 170 | 20,932,441 | 178,301,440 | CTPK (Live2D textures), all ETC1A4 |
| `.dspadpcm.bcstm` / `.bcstm` | 144 / 38 | 594 M | | CSTM audio |
| `.lsbin` | 85 | 2,135,888 | | IS .bin data |
| `.moflex` | 55 | 516,036,154 | | Mobiclip video |
| `.lz` | 30 | 368,304 | 724,517 | 22 CGFX (one ETC1A4 texture each) + 8 IS .bin |
| `.bch` | 9 | 694,520 | | plain BCH |
| small | | | | `.bfnt.lz` 8 fonts, `.shbin` 3 DVLB shaders, `.stacktrace` 2 (symbol map), `.bcsar`, `.cdc`, `.ptcl`, `.txt` |

`.arc` members (3,412): 3,036 LZ13 BCH, 169 plain BCH, 195 `effect.ptcl` (magic `SPBD`,
NW4C particle data, blob), 8 `40x40.ctpk` in `icon/link*.arc.lz` (despite the name,
headerless pixel data, no CTPK magic; blob), 4 SMDH icons.

## 3. Converters and round-trip results

Measured with `python tools/assets/roundtrip_all.py --jobs 12` over the whole RomFS
(times are wall clock for that run). "Identical" always means byte-for-byte.

| Stage | Tool | Result |
|---|---|---|
| RomFS manifest | `romfs.py --check` | 21,880 / 21,880 files match |
| LZ13 recompress | `lz.py` | **13,455 / 13,455 (100%)** (greedy-far, as Awakening) |
| IS .bin -> listing -> rebuild | `isbin.py` | **3,650 / 3,650 (100%)**, all pass the shift test |
| Message archives -> UTF-8 text | `msg.py` | **1,328 / 1,328 (100%)** |
| `.arc` -> member files -> rebuild | `arc.py` | **820 / 820 (100%)**; 3,036 / 3,036 LZ members recompress identically |
| CTPK -> PNG + JSON | `ctpk.py` | **170 / 170 (100%)** (all ETC1A4, original blocks kept) |
| CGFX textures re-injected | `cgfx.py` | **22 / 22 (100%)** |
| BCH parse | `bch.py` | **13,957 / 13,957 (100%)** (10,752 RomFS files + 3,205 `.arc` members) |
| BCH textures via PNG, re-injected | `bch.py` | **13,957 / 13,957 files, 11,743 textures (100%)** |
| BCH rewrapped (LZ13 / stored / plain) | `bch.py test --lz` | **13,957 / 13,957 (100%)** |
| BCH edit selftest | `bch.py selftest` | 6 / 6 (non-ETC with mips, ETC1A4, stored file; a portrait doubled and halved through `--allow-resize`; a non-power-of-two PNG refused) |
| BCH unedited rebuild through the relocating writer | `bchwrite.py test` | **13,957 / 13,957 (100%)** |
| BCH relocation coverage scan | `bchwrite.py test` | **13,957 / 13,957** clean |
| Every texture resized (x2, or /2 at 1024), checked, restored | `bchwrite.py test` | **11,688 / 11,688** (+55 cube-map textures refused by rule) |
| Relocation-table mutation fuzz | `bchwrite.py test` | **5,663 / 5,663** removals noticed |
| Portrait files via PNG folders | `portrait.py` | **887 / 887 (100%)**, 3,407 PNGs, + edit test + resize test (doubled, halved) |
| Whole RomFS through editable forms | `roundtrip_all.py` chain | **21,880 / 21,880 (100%)** (3.6) |

### 3.1 The "stored" wrapper (the 30 `.bch.lz` files that start with `0x00`)

All 30 are texture-only field files (`field/*_t.bch.lz`: `Btl_*`, `Cas_Obj*`,
`Gmp_World`, `Lds_Fort`, `Obj_Obstacle`, `Z000`). They are not LZ: the header is
`00 ss ss ss` (type 0, 24-bit size = file size - 4) followed by the plain BCH.

- Code: `Compress::Uncompress` (0x126A08, name from the symbol map) skips an LZ13 outer
  header (type bit 1), then calls `nn::cx::UncompressLZ` if bit 4 of the type byte is set
  and otherwise **copies** the payload (`memcpy(dst, src + 4, size)`). Type `0x00` is
  therefore "stored, not compressed".
- Why: for all 30, LZ13 compression would *grow* the data (measured: compressed / raw is
  1.0009 to 1.014; the textures are mostly ETC1, which does not compress). The 328 other
  `field/*_t` files compress, so the packer evidently stored a file whenever LZ did not
  help.
- `bch.py` (`unwrap`/`rewrap`), `survey.py` and the `roundtrip_all.py` chain all handle
  it; an edited stored file is written stored again.

### 3.2 `.arc` archives (`arc.py`)

Same IS .bin container as Awakening (labels `Data`, `Count`, `Info` + one per member;
`Info` = count x {name pointer, index, size, offset}). Fates differs in layout only:

| | Awakening | Fates (all 820) |
|---|---|---|
| `Data` label | data offset 0 | data offset `0x60` (file `0x80`); the bytes before it are zero |
| member offsets (`Info`) | from `Data` | from `Data` |
| member alignment | 1 (5 archives: 0x20) | **0x80 in file coordinates** |
| `Count` alignment | 4 (or 0x20) | 0x80 in file coordinates |

`arc.py` now measures alignment in file coordinates (`0x20 + data offset`), records
`align` and `data_off` in `arc.json`, and rebuilds either layout. Checked: 820 / 820
Fates archives and 863 / 863 Awakening archives (read-only run on the Awakening port's
RomFS) rebuild identically. Contents: `face/face` 516 (portrait expressions),
`effect` 300 (`model.bch` + `effect.ptcl`), `icon` 4.

### 3.3 BCH / H3D (`bch.py`)

10,752 RomFS files plus 3,205 `.arc` members; backward versions 0x22 (10,666 RomFS files; forward 0x23 or 0x22) and 0x21
(86). Resources over all of them: textures 11,743, materials 6,044, skeletal animations
4,560, models 3,637, material animations 611, lights 553, light animations 472,
visibility animations 288, shaders 129, fogs 55, scenes 49, LUTs 39, fog animations 27.

| Dir | BCH files | Textures | Models | Skeletal anims | What |
|---|---:|---:|---:|---:|---|
| `unit` | 3,273 | 3,273 | 0 | 0 | map sprites (one texture each) |
| `ba` | 3,130 | 0 | 0 | 3,897 | battle animations |
| `bu` | 1,898 | 2,162 | 734 | 0 | battle unit models + textures |
| `bx` | 1,090 | 864 | 629 | 220 | battle extras |
| `field` | 726 | 1,314 | 1,920 | 218 | 3D maps |
| `face` | 371 | 371 | 0 | 0 | hair / accessory layers (plus 3,036 in `face/face/*.arc`) |
| others | 264 | 238 | 108 | 7 | `castle`, `scene`, `tut`, `ui`, `bp`, `sky`, `common`, `map`, `icon`, ... |

Texture formats: ETC1A4 6,904, RGBA4444 3,289, ETC1 1,358, RGB565 96, RGBA8888 23, RGB888
18, L8 14, A8 10, HILO8 8, LA44 8, RGBA5551 5, A4 5, LA88 3, L4 2.

Format (facts from the game's loader `nw::h3d::res::ResourceBinary::TryInit` at 0x3233F4
and the community SPICA / Ohana3DS notes, read for facts only):

```
0x00 "BCH\0", u8 backward ver, u8 forward ver, u16 converter ver
0x08 u32 offsets: contents, strings, gpu commands, data, data-extended (backward > 0x20), relocations
     u32 lengths of the same, then uninitialized data / description lengths,
     u16 flags, u16 address count
contents: 15 x {u32 pointer table, u32 count, u32 name dictionary}: models, materials,
     shaders, textures, LUTs, lights, cameras, fogs, skeletal / material / visibility /
     light / camera / fog animations, scenes (contents-relative)
texture entry: 3 x {u32 GPU command offset, u32 word count} (texture units 0-2),
     u32 ?, u32 name (strings)
PICA commands (unit 0): 0x82 dim (height | width << 16), 0x84 LOD (max level, bits 16-19),
     0x85 address, 0x8E format (same numbering as tex3ds)
relocation u32: bits 0-24 offset (words; bytes for kind 1), bits 25-28 kind,
     bits 29-31 target section (0 contents, 1 strings, 2 gpu, 3 data, 4 data-extended)
     kind -> base added: 0 contents, 1 strings, 2-3 gpu, 4-8 data, 9-13 data-extended;
     kinds 5/10 store (physical address >> 3) (PICA addresses), 6-8 / 11-13 store
     physical-address-relative forms (7/12 with bit 31 set).
```

The file on disk is unrelocated: each pointer is an offset into its own section. A
texture's pixels are at `section(kind of the 0x85 word's relocation) + value` (always
kind 5 or 10 here). Pixel rows: the first stored tile row is the **top** of the image
(as in Awakening); checked visually on portraits (with a vertical flip they come out
upside down).

**Editing.** `export` writes one PNG per texture (level 0) and `bch.json`; `pack` takes
the PNGs back. Re-injection is **in place**: same width, height and format, the file
length and every offset stay the same, and the writer refuses any texture range that
overlaps a relocated word. An unchanged PNG keeps the original bytes (so ETC blocks and
hand-made mip levels survive); an edited one is re-encoded with tex3ds (exact for the 12
raw formats, tex3ds' ETC1 encoder for ETC1/ETC1A4, see 3.3.2) and its mip levels are
rebuilt with a 2x2 box filter. A PNG of another size, or a `format` / `mips` value edited
in `bch.json`, is refused unless `--allow-resize` is given; then it goes through the
relocating writer (3.3.1). Editing models or animations is still not possible.

`bch.py test` decodes every texture, goes through PNG bytes, re-encodes every level of
every non-ETC texture (no shortcut), re-injects and compares; `--lz` also re-wraps and
compares with the file on disk (~6.5 min; without `--lz` ~1.5 min). `bch.py selftest`
edits a 16x16 block in a non-ETC texture with mips (HILO8 512x512), an ETC1A4 texture and
a stored file, and checks pixels, length, wrapper and that every other byte is untouched.
It then doubles and halves a portrait PNG. The pack must refuse it without
`--allow-resize` and accept it with the flag, and the result must pass `bchwrite`'s
checks. Last, a 96x64 PNG must be refused (~40 s in all).

### 3.3.1 Resizing a texture: the relocating writer (`bchwrite.py`)

**In short:** a picture inside a BCH file can now be replaced by one of a different size
(for example 256x256 -> 512x512 or 128x128), with a different number of mip levels, or
in a related pixel format. The tool rebuilds the file around it and fixes every internal
pointer. Everything else in the file stays bit-for-bit the same. Unsafe edits are refused
with a plain message.

What it does:

1. The texture's pixels (plus the zero padding up to the next thing anything points at)
   are swapped for the new pixels. Everything after them moves by a multiple of 0x80
   bytes, so every later block keeps the alignment the game needs.
2. Every pointer that the file's relocation table lists and whose target moved is
   rewritten. The relocation table itself is re-encoded, and the header's section offsets
   and lengths are updated. Later sections (data-extended, relocation table) slide along.
3. The texture's own description is updated in all three texture-unit command lists
   (size register 0x82/0x92/0x9A, mip levels 0x84/0x94/0x9C bits 16-19, format
   0x8E/0x96/0x9E), plus the format and mip-count bytes of its contents entry (+0x18,
   +0x19).

**What the game does with these fields.** Read from code; addresses come from
`config/functions.csv`.

| Code | Finding |
|---|---|
| `ResourceBinary::TryInit` 0x3233F4 | Wants the GPU-command section in memory 16-aligned, and the data and data-extended sections 0x80-aligned. That is why moves are multiples of 0x80. |
| `ResourceBinary::Relocate` 0x3235A8 | Each entry: offset bits 0-24 (x4 except kind 1), kind bits 25-28, section holding the word bits 29-31. Base by kind: 0 contents, 1 strings, 2-3 GPU commands, 4-8 data, 9-13 data-extended. Kinds 5/10 (textures) are stored as physical address >> 3. Kinds 6/11 (vertices), 7/12 (16-bit indices, bit 31 set) and 8/13 (8-bit indices) are stored as physical address minus a global base. **Kind 14** ignores the word and stores that global base >> 3: this is the vertex attribute base register 0x200 (not in the community notes). For kinds 5-13 the loader saves the original address in the "uninitialized data" area (4 bytes each). The count must equal the header's address count (+0x42), so header +0x38 = 4 x that count. A resize keeps every relocation, so neither number changes. |
| `TexCommand::GetWidth/GetHeight/GetAddress` 0x19080C / 0x19092C / 0x1906F0, `ITexture::Setup` 0x4EBC10, `ITexture::SetMatrix` 0x11D1B4 | The game reads width and height from the texture's command list, and format and mip count from entry +0x18 / +0x19. It then scales texture coordinates by 1/width, 1/height. **The size comes from the file, not from a constant.** |
| `TextureSamplerData::MakeUnit0Command` 0x51D118 | Builds the sampler words at run time. Each material's own texture commands are placeholders: size, LOD and address are zero in all 1,055 measured. The material is bound to the texture by name. |
| `FaceInstance::CalcDrawFaceRect` 0x1AF8B0 | Draws a portrait at the texture's width and height in **screen pixels**. In one mode it uses FaceData layout numbers +0x34 / +0x36 instead, centred with a fixed 256. So on the 3DS a bigger face is drawn bigger (or cropped), not sharper. Sweat and blush overlays keep their own sizes and positions. |

**Limits (refused, with the reason):**

- a side that is not a power of two, or not 8-1024 (3DS GPU limits);
- more mip levels than the size allows, or data of the wrong length;
- a format change across families. The families are colour+alpha (RGBA8888, RGBA5551,
  RGBA4444, ETC1A4), colour (RGB888, RGB565, ETC1), L (L8, L4), LA (LA88, LA44), A (A8, A4)
  and HILO8. A colour texture may gain alpha and L may become LA; nothing may lose alpha;
- a texture whose three unit command lists disagree, or that is not the standard 2D
  layout. This means the 55 cube-map textures (the six-face environment textures in
  effects);
- pixels shared with another texture, a pointer into the middle of the pixels, non-zero
  bytes after the pixels, or overlapping sections (only `sample/telop.bch`, which has no
  texture);
- an offset that would not fit the relocation fields.

Note that one material word is still not explained. A material's placeholder format word
(0x8E) is non-zero (all 1,055). The run-time binding seems to replace it with the
texture's own command list, as `TexCommand` and `MakeTextureCommand` (0x322968) suggest,
but this is not proven. Until a resized or re-formatted texture is seen in game, treat a
**format** change as less certain than a size change.

**How it is proven** (`bchwrite.py test`, every BCH: 10,752 RomFS files plus 3,205 `.arc`
members, ~1.5 min, 12 workers):

- **Unedited rebuild through the writer: 13,957 / 13,957 identical.** The header,
  sections and relocation table are re-encoded from the parsed values.
- **Coverage scan: 13,957 / 13,957 clean.** Every non-zero write to a GPU address
  register in every command list has a relocation entry. These registers are texture
  addresses 0x85-0x8A / 0x95 / 0x9D, vertex buffer offsets 0x203+3n and the index buffer
  0x227. Every relocation into data / data-extended that sits in the command section is on
  such a register. A word holding 0 without an entry is harmless, because offset 0 never
  moves. (Only the developer sample files in `sample/` also point into data from
  contents, kind 4; those are listed, so they move too.)
- **Every texture resized: 11,688 / 11,688** (all except the 55 cube maps). Each is
  doubled, or halved when it is 1,024 wide, with synthetic pixels, then checked:
  - the file re-parses;
  - the edited texture reads back exactly;
  - every other texture has the same pixels;
  - contents, strings and command sections are identical except at words the relocation
    table lists and at the edited texture's own size / format / mip words;
  - every moved pointer still points at the same bytes;
  - data sections are still 0x80-aligned;
  - the coverage scan is clean.

  Then the original texture is written back, and the file must be **byte-identical** to
  the original. It always is.
- **Mutation fuzz: 5,663 / 5,663.** Up to two relocation entries per file that point at
  moving data are removed, one at a time. The coverage scan must report every removal, so
  a missing entry cannot go unnoticed.

`bchwrite.py selftest` (~5 s) runs the same checks on a small made-up BCH (no game data):
growing, shrinking, a format change with mips, two textures at once, and every refusal.
It then repeats them on four sample ROM files (a portrait, a hair layer, a model file with
its textures, a stored-wrapper field file).

**Checked against `docs/tracks/formats/BCH.md`.** These points in the community-sourced
notes agree with the code:

- the header field order;
- the relocation bit layout and kinds 0-13;
- the 0x80 / 16 alignment hints;
- textures bound by name;
- cube faces mark a non-2D texture.

These points needed correcting:

- the flags at +0x40 are read as a byte, and +0x42 is the address count the loader checks;
- kind 14 exists (the attribute base register);
- "a different size is a reject" is now the relocating writer's job, under the limits
  above.

### 3.3.2 ETC1 / ETC1A4 encoder quality (`tex3ds.py`)

Nearly every portrait is ETC1A4. Unedited pictures keep their original blocks, so only an
**edited** picture is re-encoded. The old encoder took the average colour of each half
block. The new default (`ETC_QUALITY = "high"`) works as follows:

- it starts from the old answer;
- for each of the 8 modifier tables, it refits the base colour (pixel average minus the
  average chosen modifier) and tries the rounding neighbours in both the 4-bit and the
  5-bit differential modes;
- when a differential pair is out of range, it re-searches one half clamped to the other;
- it scores every candidate exactly, with the hardware's clamping.

It is never worse than the old encoder (checked in `tex3ds.py selftest`) and is
deterministic. Alpha is now rounded to the nearest 4-bit step instead of truncated.
Facts come from the public ETC1 specification; no code was taken.

Measured with `portrait.py etcbench 6` on six standing portraits (256x256 ETC1A4). PSNR
is over the RGB channels of non-transparent pixels; higher is better.

| Picture | Old encoder | New encoder | Time per 256x256 |
|---|---:|---:|---|
| decoded original (already ETC-shaped) | 34.50 dB | **43.18 dB** (+8.7) | 0.9 s -> 3.3 s |
| re-filtered copy (stand-in for new art) | 34.43 dB | **35.84 dB** (+1.4) | 0.9 s -> 5.2 s |

For new art, the second row is the realistic number: about +1.4 dB, which is visibly
cleaner edges and fewer colour blocks. A full portrait set (all `_st`, `_bu` and `_ct`
expressions of one character, about 15-20 pictures) re-encodes in roughly a minute. In
practice only the changed PNGs are re-encoded. `tex3ds.ETC_QUALITY = "fast"` brings back
the old encoder.

### 3.4 Live2D, CTPK and CGFX

The 170 `live2d/**/*.ctpk.lz` packages and the 22 CGFX `.lz` files go through the
Awakening converters unchanged (all ETC1A4, original blocks kept). Live2D models
(`.moc`, `.mtn`, `.json`) are blobs.

### 3.5 Everything else

LZ13, IS .bin and message archives behave exactly as in Awakening (1,480 LZ13 files have
an outer size different from the data size; it is kept, as in Awakening). The Fates
GameData header layout and table meanings are the tables area's work, not covered here.

### 3.6 Whole-RomFS chain (`roundtrip_all.py`)

Every RomFS file through its editable form end to end (LZ or stored wrapper, text /
listing / PNG / member files, rebuild, re-wrap; `.arc` members recursively, BCH via
PNG) and compared with the original. Reference run (2026-11-10, 12 workers):
**21,880 / 21,880 files identical**: BCH 10,722 (+30 stored), `.arc` 820, message
archives 1,328, IS .bin data 1,502, CTPK 170, CGFX 22, blobs 7,286.

`roundtrip_all.py` printed "ALL STAGES 100%" in 15 min 20 s (LZ stage 302 s, chain
435 s, BCH 91 s + selftest 23 s, portraits 30 s). Report:
`extracted/assets/roundtrip_report.txt`; failures, if any, `extracted/assets/*_fail.txt`.

## 4. Portraits (`portrait.py`)

A Fates portrait is assembled from several files (paths from `FaceData` getters in the
code, roots from a string table at 0x6BDBA0: `face/face`, `face/body`, `face/hair`,
`face/accessory1`, `face/accessory2`):

| Piece | Path | Count | Notes |
|---|---|---:|---|
| expressions | `face/face/<package>.arc` | 516 archives, 3,036 LZ13 BCH members | `<name>_st` standing (204), `_bu` bust / talk window (204), `_ct` cut-in (108). Members are named after the expression (normal, smile, angry, pained, ...) plus `汗` sweat and `照` blush overlays; one ETC1A4 texture each (256x256 for faces) |
| hair | `face/hair/<dir>/髪<n>.bch.lz` | 75 dirs | recolourable layers (avatar, children); tint from the record |
| accessories | `face/accessory1|2/<dir>/<name>.bch.lz` | | avatar accessories; names from `FaceData_Acc1/2.bin.lz` (13 / 6 ACID records) |
| record | `face/FaceData.bin.lz` | 452 | IS .bin: u32 count + 0x48-byte records (below) |

FaceData record (offsets checked against `FaceData::GetPackegeFilePath` 0x545CB0,
`GetBodyFilePath` 0x545C28, `GetHairFilePath` 0x545C74, `GetAccessory1/2FilePath`
0x545D00 / 0x545D4C, `GetStandCenterOffset` 0x545CEC, `GetMessName` 0x545BD8):

| Offset | Type | Meaning |
|---|---|---|
| 0x00 | ptr | FSID (`FSID_ST_<name>` / `FSID_BU_<name>`; also the label) |
| 0x04 | ptr | MPID of the name (`MPID_username` = the avatar's own name) |
| 0x08 | ptr or 0 | ASCII key (e.g. a character's English name, `PLAYER_M1`); use not checked in code |
| 0x0C | ptr | package: `face/face/<package>.arc` |
| 0x10 | ptr or 0 | body dir: `face/body/<dir>/体<n>.bch.lz` (unused on this cart) |
| 0x14 | ptr or 0 | hair dir: `face/hair/<dir>/髪<n>.bch.lz` |
| 0x18 | ptr or 0 | accessory dir: `face/accessory1|2/<dir>/<accessory>.bch.lz` |
| 0x1C | u32 | colour (hair tint) |
| 0x20, 0x24 | ptr | two default expression names |
| 0x28-0x47 | 16 x u16 | layout numbers; `GetStandCenterOffset` = [0x30] + [0x34] / 2 - 128 |

`portrait.py export QUERY OUT` matches FSID, MPID, key or package. It writes every layer
of the matching records (plus the character's `_ct` cut-in arc) as PNG folders, with a
manifest, `portrait.json` (format 2). The manifest lists the FaceData records (names,
package, hair, accessory, colour, default expressions, layout numbers), the source files,
and **every picture layer**: the PNG path, the source file and member, its role
(`expression`, `overlay-sweat`, `overlay-blush`, `hair`, `accessory1/2`), and its size,
format and mip count.

Picture sizes on this cart:

| Package | Expressions | Overlays |
|---|---|---|
| `_st` (standing) | 256x256 | 16x16 to 256x256 |
| `_bu` (bust / talk window) | 128x128 | 16x16 to 256x256 |
| `_ct` (cut-in) | 512x512 | none |

All are ETC1A4, one mip level.

`import OUT DEST` first checks every PNG, then rebuilds the files whose PNGs changed. Only
when everything succeeded does it write them at their RomFS paths under DEST, each
through a temporary file. The arc is rebuilt with `arc.py`, and the edited member is
re-compressed LZ13. An error writes nothing and names the PNG and the reason.

**Size changes.** The game draws a portrait at its pixel size (3.3.1). A bigger PNG
therefore shows bigger on the 3DS screen, and the sweat and blush overlays stay where
they were. So `import` refuses a PNG whose size differs from the original, and says why.
With `--allow-resize` it accepts the new size when:

- both sides are powers of two from 8 to 1024;
- **every expression of one package has the same size** (the game swaps them in place).

Overlays and hair / accessory layers are checked one by one. The resized files go
through the relocating writer. This is meant for experiments, and for a PC renderer that
draws at a fixed size. A 3DS swap should keep the original size.

`test` exports and re-imports all 887 portrait files (every arc, hair and accessory BCH;
770 are referenced by FaceData records, the other 117 are not named by any record). It
also:

- edits a 16x16 block of one expression and reads it back;
- runs a **resize test**: the expressions of one standing portrait are doubled, then
  halved. The import must refuse without the flag and refuse mixed sizes, and must write
  nothing when it refuses. With the flag, every expression must re-parse at the new size
  and the overlays must keep their bytes.

Measured 2026-11-10: **887 / 887** rebuilt identically (3,407 PNGs), edit test PASS,
resize test 2 / 2 PASS.

## 5. Not converted (carried as blobs)

| Format | Files | Notes / next step |
|---|---:|---|
| BCH structure (models, materials, animations, shaders) | 13,957 | textures are editable in place or resized (`bchwrite.py`); models, materials and animations are still blobs inside the file |
| Live2D `.moc` / `.mtn` / `.json` | ~5,400 | Cubism 2 formats; a renderer is engine work (licence check) |
| audio `.bcstm` / `.dspadpcm.bcstm` / `.aac` / `.bcsar` | 182 / 1,026 / 1 | CSTM documented; `.aac` are plain AAC |
| `.moflex` video | 55 | Mobiclip |
| `.cmb` event scripts | 624 | same magic and header as Awakening; no decompiler yet |
| `.ptcl` particles (`SPBD`) | 196 | NW4C effect data |
| `.bfnt.lz` fonts | 8 | header differs from Awakening's |
| `GameData/TextEditor.bin.lz` | 1 | neither LZ nor IS .bin (not investigated) |
| IS .bin data semantics | 3,650 | containers round-trip; field names are the tables work |

## 6. Files

- `tools/assets/romfs.py` - RomFS unpack (product code from config/game.json) + manifest + IVFC verify
- `tools/assets/survey.py` - counts/types report (knows BCH and the stored wrapper)
- `tools/assets/lz.py` - LZ10/11/13 codec
- `tools/assets/isbin.py` - IS .bin <-> listing
- `tools/assets/msg.py` - message archives <-> text
- `tools/assets/arc.py` - `.arc` <-> member files (Awakening and Fates layouts)
- `tools/assets/tex3ds.py` - PICA texture codecs + PNG reader/writer
- `tools/assets/ctpk.py`, `cgfx.py` - CTPK / CGFX textures
- `tools/assets/bch.py` - BCH parser, texture export / in-place import, tests
- `tools/assets/bchwrite.py` - relocating BCH writer (texture resize / mips / format), coverage scan, tests
- `tools/assets/portrait.py` - FaceData reader, portrait layer export / import, tests
- `tools/assets/roundtrip_all.py` - runs everything, prints pass rates
- ROM container tools: `tools/rom/`, `tools/extract_rom.py` (see docs/ROM_REBUILD.md)
