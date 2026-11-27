# Picture and media formats

ELI5 / ETA: This is the map of the picture file, written so a face swap can be checked against it. It is notes, not a tool. No game file was opened. A face swap that keeps the same size and the same picture type can be tried in the December window. A swap that needs a new size is a rebuild, and that is the thing that slips the date.

Status 2026-11-10. Facts from public pages, rewritten. No code copied. No game bytes, names, or table values.

Each fact is tagged. [high] means the cited page says it. [med] means two public pages agree, or one page says it and a second reader behaves as if it were true. [guess] means not checked.

## What the December swap is allowed to do

Replace the pixels of one picture. Keep the name, the width, the height, the format code, the mip count, and the byte length. Leave the material, the model, and the relocation table alone.

If any of those change, reject the file. Do not rebuild the container to make it fit. A rebuild is a different tool, and it is not the early-December exit.

## Outer compression

The picture container itself starts at the three characters BCH. Files on disk are often compressed before that. [med, scout/SCOUT.md: the other containers use the same compression and round-trip; this note did not open a picture file.]

Unwrap first. If the first bytes are not BCH, it is not a picture file yet. When writing back, use the same compression the file already used. Do not pick a new one. Same rule as text mods.

## Header

Little-endian. The first eight bytes are the magic and the version. The next 32-bit word, at offset 8, is the file offset where the contents start. Trust that offset. Do not hard-code a header size. [high, SPICA field order; Ohana3DS reads a 32-bit value at offset 8 and treats 0x44 as the later header.]

| offset | what | tag |
|---|---|---|
| 0x00 | four bytes: the characters BCH and a zero | [med] SPICA stores a 3-character magic and then a byte, a byte, and a 16-bit converter version. That only lines up if the magic occupies 4 bytes. Ohana's read at offset 8 agrees. |
| 0x04 | backward-compatibility byte. This is the version the reader must branch on. | [high, SPICA] |
| 0x05 | forward-compatibility byte | [high, SPICA] |
| 0x06 | converter version, 16-bit | [high, SPICA] |
| 0x08 | contents offset | [high] |
| 0x0C | strings offset | [high] |
| 0x10 | commands offset | [high] |
| 0x14 | raw-data offset | [high] |
| next | extra-raw offset, only if backward compatibility is 0x21 or higher | [high, SPICA] |
| next | relocation-table offset | [high] |
| then | the matching lengths, in the same order, including the extra-raw length only on that same version | [high] |
| then | length of the uninitialized-data area, then length of the uninitialized-commands area | [high] |
| then | if backward compatibility is 8 or higher: a flags byte and a 16-bit count of raw blobs | [high, SPICA] |

Flags, when present [high, SPICA]:

| bit | meaning |
|---|---|
| 0 | written by the newer converter |
| 1 | marked initialized |
| 2 | uninitialized-data area disabled |

A 2015 game is likely to use compatibility 0x21 or higher. That is a guess until a file is read. The tool reads the byte. It does not assume it.

## Sections

Six regions, in file order [high, SPICA]:

1. Contents. Models, materials, textures, and the other named objects. Pointers here are not file offsets until the relocation table has been applied.
2. Strings. Names, including texture names. Aligned to 16 bytes when SPICA writes a file.
3. Commands. GPU command streams. Aligned to 128 bytes when SPICA writes a file.
4. Raw data. Pixels, vertices, and indices. Textures are placed before vertex and index bytes. SPICA reports that putting pixels last, or in a random order, breaks games, most likely on alignment. A swap must not reorder this region.
5. Extra raw. Present only on compatibility 0x21 or higher. Same kinds of bytes as raw data.
6. Relocation table. One 32-bit word per pointer.

A command stream must stay a multiple of 16 bytes. A shorter tail is a known way to hang the GPU. [high, 3dbrew GPU internal registers.]

## Relocation table

Each entry is one 32-bit word. [high, SPICA relocator, rewritten.]

| bits | meaning |
|---|---|
| 0–24 | where the pointer sits inside the source section. For every section except strings, this value is stored divided by 4. |
| 25–28 | which section the pointer points into |
| 29–31 | which section the pointer lives in |

To apply one entry: add the target section's file offset to the 32-bit word at (source section's file offset + the pointer offset).

Section numbers are not stable across versions. [high, SPICA.]

- Compatibility 8 through 0x20: numbers at or above the vertex-data number are stored one lower than the modern list.
- Compatibility below 7: numbers at or above the commands-source number are stored one higher.
- Compatibility 0x21 or higher: modern numbering.

Modern numbers, for a reader that has already applied that shift [high, SPICA]:

| number | section |
|---|---|
| 0 | contents |
| 1 | strings |
| 2 | commands |
| 3 | commands, as a source (same base as 2) |
| 4 | raw data |
| 5 | raw data, a texture |
| 6 | raw data, vertices |
| 7 | raw data, 16-bit indices. The base address has its top bit set. |
| 8 | raw data, 8-bit indices |
| 9 | extra raw |
| 10–13 | extra raw, split the same way as 5–8 |

A pointer value does not fit in 25 bits past 32 MB, or 128 MB for the sections whose offset is stored divided by 4. A normal picture file is nowhere near that. If one is, reject it.

Do not apply the table to the buffer you will save. Applying it turns relative pointers into file offsets. Saving that buffer writes a corrupt file. [high, SPICA's own warning.] A swap that does not move any pointer should not touch this table at all.

## Texture descriptor

A texture is not a flat record. It is a name, three GPU command streams, and a pixel blob. [high, SPICA texture reader.]

The name lives in the string section. A material points at the texture by that name. It does not embed the pixels. [high, SPICA dictionaries are by name.] Keeping the name means the material and the model do not need an edit.

The three command streams are texture units 0, 1, and 2. They must agree on width, height, format, and where the pixels are. If they disagree, reject the file. Do not pick one and hope. [high, SPICA writes the same values into all three; an independent checker requires them to agree.]

Read those values from unit 0's commands. The command format is public. [high, 3dbrew GPU internal registers.]

A command is at least 8 bytes. The first word is the value. The second word is the header: bits 0–15 are the register id, bits 16–19 are a byte mask, bits 20–27 count extra values, bit 31 means the next values go to the next registers.

| register | id | what a swap reads |
|---|---|---|
| size | 0x82 | height in bits 0–10, width in bits 16–26 |
| format | 0x8E | bits 0–3, table below |
| lod | 0x84 | do not reinterpret. See the disagreement below. |
| pixel address | 0x85 through 0x8A | one address per face |

Width and height are 11-bit fields, so the field can hold up to 2047. SPICA's writer refuses anything above 1024. [high, both pages.] A swap does not change the size, so the disagreement does not matter. Do not resize to make a picture fit.

The lod register is a real disagreement. 3dbrew says bits 0–12 are a bias, bits 16–19 a maximum level, and bits 24–27 a minimum level. SPICA stores a mip count and writes that count into the same register. [high that the two pages disagree.] A swap copies the register unchanged. It does not decode a mip count out of it. If the file has more than one mip level, either every level is regenerated at the same sizes or the swap is rejected. Leaving a stale smaller level is a bug.

Addresses, after relocation, are file offsets in SPICA's reader. In a live GPU command the same field is a physical address shifted down by 3. [high, 3dbrew; high, SPICA treats the relocated value as a file offset.] A tool must not shift a file offset. Before using an address, check that it falls inside the raw section. If it does not, the table has not been applied, or the file is not one this note covers. Reject it.

A flat picture uses the first address. The other five are zero. A cube uses all six, in the order +X, −X, +Y, −Y, +Z, −Z, lowest address first. [high, 3dbrew.] The December swap rejects a cube. Six faces are not a portrait swap.

Mip levels sit immediately after the base image. [high, 3dbrew.] Pixels are not in rows. They are in a Z-order curve, and compressed formats are in 8×8 tiles. [high, 3dbrew.] The byte packing for those tiles is already in our texture codec. This note does not restate it. A new codec would be a second implementation of the same hardware. Check the picture tool against that codec, not against a guessed layout.

### Format codes

[high, 3dbrew GPU internal registers, texture-unit type.]

| code | name | size, before tiling |
|---|---|---|
| 0x0 | RGBA8 | 4 bytes a pixel |
| 0x1 | RGB8 | 3 bytes a pixel |
| 0x2 | RGBA5551 | 2 bytes a pixel |
| 0x3 | RGB565 | 2 bytes a pixel |
| 0x4 | RGBA4 | 2 bytes a pixel |
| 0x5 | IA8 | 2 bytes a pixel |
| 0x6 | HILO8 | 2 bytes a pixel |
| 0x7 | I8 | 1 byte a pixel |
| 0x8 | A8 | 1 byte a pixel |
| 0x9 | IA4 | half a byte a pixel |
| 0xA | I4 | half a byte a pixel |
| 0xB | A4 | half a byte a pixel |
| 0xC | ETC1 | one 4×4 block, 8 bytes, no alpha |
| 0xD | ETC1A4 | ETC1 plus 4 bits of alpha per pixel |

ETC1 and ETC1A4 are the formats a portrait is likely to use, because they are the compressed ones. That likelihood is a [guess] until a file is read. The tool reads the code. It does not assume 0xC.

The block order inside ETC1A4 is not copied here. 3dbrew names the format and does not, on the page read for this note, give the nibble order. Use the codec we already have. If that codec and a file disagree, the file wins and the codec is the bug. Do not invent an order to make a test pass.

Power-of-two sides are what the hardware accepts. [high, SPICA refuses a non-power-of-two write.] A swap whose new picture is not the same width and height is a reject, not a resize.

## What a swap must check

1. Unwrap. Magic is BCH. Put the same compression back.
2. Read the compatibility byte. Do not assume 0x21.
3. Do not relocate the buffer that will be saved.
4. The three command streams agree on width, height, format, and length.
5. The new pixels encode to the same length, in the same format, at the same size, with the same mip register left untouched.
6. The name is unchanged.
7. A non-zero second face address is a cube. Reject.
8. Tests use a synthetic file. No game pixels, names, or encoded blocks in git.

If step 5 fails, say so. That is the week-one slip signal from the plan. It is not a reason to rebuild the container inside the swap tool.

## Out of this note

Skeletons, shaders, animations, cameras, lights, and a full model rebuild. A material is mentioned only because a swap that keeps the texture name does not edit it. Vertex data is mentioned only so a swap does not move it.

## Other media

These are not the December tool. They are here so nobody starts one by accident.

### `.dspadpcm.bcstm`

A CTR stream. Magic is the four characters CSTM. [high, 3dbrew BCSTM.]

The 16-bit value at offset 4 is the byte order: 0xFEFF means little-endian, 0xFFFE means big-endian. Do not assume the order from the magic. [high, 3dbrew.]

The rest of the header is a version, a file size, and three references (info, seek, data). Encoding value 2 is DSP-ADPCM: 16 predictor coefficients per channel, plus a scale and two previous samples. Value 0 is 8-bit PCM, 1 is 16-bit PCM, 3 is IMA-ADPCM. Samples are in blocks, not one interleaved stream. Info, seek, and data are aligned to 32 bytes.

Playback tools that already exist: vgmstream, Every File Explorer, Citric Composer. [high, 3dbrew's tool list.] Check each tool's licence before copying a decoder. A voice swap is not on the moddable line. If one is ever done, it keeps the same block sizes.

### `.aac`

MPEG-4 AAC audio. The extension does not say whether a file has a frame header. [guess, until one file is framed.] Confirm that before any tool assumes a header. ffmpeg can decode it once the framing is known. Do not vendor a decoder. Not on either finish line.

### `.moflex`

A Mobiclip movie container, used on 3DS. The container marker cited for this suffix is 0x4C32. A 3dbrew page for Nintendo Video gives the first 32-bit word as 0xABAA324C, whose first two bytes are that same marker. [high, both pages; med that every movie in this game uses that header, because no movie was opened.]

The picture codec is Mobiclip, not H.264. It was Actimagine's, later Nintendo's. [high, public codec note.] It looks a little like H.264 and is not. A tool that searches the payload for H.264 start codes will cut frames. Community decoders exist. There is no libre official one. Do not copy a decoder into this repo. Movies stay as the game already plays them. Not on either finish line.

### Live2D `.moc` and `.mtn`

The extensions match Cubism 2, the generation current when this game shipped. Cubism 3 and later use different extensions (`.moc3`, and a motion file that is not `.mtn`). [med, public naming. Not confirmed by opening a file.]

`.moc` is the model. `.mtn` is a motion. The current public editor and SDK are Cubism 4/5. They do not promise to load a Cubism 2 file. [med.]

Licence, from Live2D's own pages: the SDK is proprietary. Downloading it requires their licence. Publishing a product that contains the SDK needs a separate publication agreement. Individuals and small businesses are exempt from that fee, with an extra rule for applications that let an end user supply their own model. The console SDK is not public. [high, live2d.com SDK licence page and the matching help page, read 2026-11-10.]

Do not add Cubism code to this repo. The game's own runtime stays as it is. A PC rewrite of these scenes is a licence question for the owner, asked before any code is written. Not on either finish line. This matches the agreed plan.

## Sources

Read 2026-11-10. Facts rewritten. No code copied.

- SPICA, gdkchan, CTR H3D reader and relocator. Community tool. Facts only. The licence file was not at the usual path this session; do not copy a line until that file is read. https://github.com/gdkchan/SPICA
- Ohana3DS, same author, older reader. Used only as a cross-check that offset 8 holds a header size. Do not copy.
- 3dbrew, GPU internal registers (command header, texture registers, format table): https://www.3dbrew.org/wiki/GPU/Internal_Registers
- 3dbrew, BCSTM: https://www.3dbrew.org/wiki/BCSTM
- 3dbrew, Nintendo Video (moflex word): https://www.3dbrew.org/wiki/Nintendo_Video
- Mobiclip container note: https://gist.github.com/quatric/3e2f0caa5c22a9a8b24d9cf1ffdfe860
- Live2D SDK licence: https://www.live2d.com/en/sdk/license/ and https://help.live2d.com/en/sdk/sdk_001/

## For the picture tool under review

Check `tools/assets/bch.py` against this note after it lands. The failures that matter: a hard-coded header size, a hard-coded compatibility, relocating the buffer that gets saved, trusting one command stream when the other two disagree, shifting a file offset by 3, resizing, and rebuilding the container because a PNG was the wrong size. Those are rejects, not fixes.
