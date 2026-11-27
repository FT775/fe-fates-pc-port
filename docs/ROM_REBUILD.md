# Whole-ROM (.cci) rebuild

Status (2026-11-10): **done for the retail image.** `tools/rom/rebuild.py` rebuilds the
whole 2 GiB Fates `.cci` from `code.bin` plus the parts written by `tools/rom/extract.py`,
and the result is byte-identical to the owner's dump (all 60 regions and the whole file
match). This is the Fates counterpart of FE8's `make compare`. The tools are the
Awakening port's, made game-neutral through `config/game.json` (product code, default ROM
path) and fixed for two Fates differences found on the way (see "What changed for Fates").

Retail image (Special Edition USA, `CTR-P-BFZE`, title `0004000000179800`, decrypted dump,
2,147,483,648 bytes):

| Hash | Value |
|---|---|
| SHA-256 | `a89be7a4cb6a471bcfeac4feca55eeec68937d90d7fed18b1cf967399363f449` (= `rom_sha256` in config/game.json) |
| SHA-1 | `2e4ad3327efd23ba0ed015858afd036f66669da0` |
| ExeFS `.code` (compressed) SHA-1 | `8bde042d70098078f1a86fbe1d5d582d6ffa6b63` |
| `code.bin` (decompressed) SHA-1 | `038db5d79786914f645fbef08242a138703f8d70` |

## Usage

```bash
python tools/rom/extract.py              # once, ~17 s: writes extracted/rom/ (ROM path from config/game.json)
python tools/rom/rebuild.py              # build/rom/rebuilt.cci from build/code.bin (else extracted/code.bin), then compare
python tools/rom/rebuild.py compare --rom "roms/Fire Emblem Fates - Special Edition (USA).cci"   # also a direct byte diff
python tools/rom/rebuild.py verify [IMAGE]   # every hash inside an image; works on modified builds
python tools/rom/blz.py selftest         # BLZ recompression research harness (every cut rule)
python tools/rom/tests.py                # BLZ, code-mutation and RomFS mutation/shift tests (~65 s)
python tools/extract_rom.py [--romfs]    # code.bin / text / rodata / data / layout.json (+ RomFS, streamed)
```

The ROM path defaults to `rom_path` in `tools/config.local.json`, else the `.cci` in `roms/`
(`tools/paths.py`, F-048; for one release also `default_rom` from `config/game.json` in the repo root). Every tool checks that partition 0 carries
`product_code` from `config/game.json` (`extract_rom.py --any-game` skips that).

**Disk use.** Fates' RomFS is 1.8 GB. `extract.py` hard-links partition-0 RomFS files
from `extracted/romfs/` (the tree `extract_rom.py --romfs` / `tools/assets/romfs.py`
wrote) when their bytes equal the ROM's, so `extracted/rom/` costs almost nothing extra
(`--no-link` copies instead). A linked file is the *same* file in both places: never
edit `extracted/romfs/` in place (mods go to `mods/<Name>/`; `tools/assets/romfs.py
--check` detects edits). `tests.py` copies the parts dir with hard links too and breaks
the link before writing a test file.

Timings on the dev machine (warm file cache): extract 17-21 s, build 13 s (BLZ 8 s of
it), compare 3 s, verify 2 s, `tests.py` 65 s. Images are streamed in 16 MiB chunks;
`build/rom/rebuilt.cci` is 2 GiB, delete it when done.

All output lives under `extracted/rom/` or `build/rom/` (gitignored: Nintendo data).

## Image layout

| Region | Offset | Size | Notes |
|---|---|---|---|
| NCSD header | `0x0` | `0x200` | RSA signature + partition table |
| Card info | `0x200` | `0xE00` | filled size at `0x300` |
| Card dev info | `0x1000` | `0x200` | NCCH header copy at `0x1100` |
| padding | `0x1200` | `0x2E00` | `0xFF` |
| Partition 0 (CXI, game) | `0x4000` | `0x6CB94000` | see below |
| Partition 1 (CFA, manual) | `0x6CB98000` | `0x6B000` | header, zero pad, RomFS at `+0x1000` (1 file) |
| Partition 6 (CFA, New 3DS update data) | `0x6CC03000` | `0x5DE000` | RomFS at `+0x1000` (11 files) |
| Partition 7 (CFA, update data) | `0x6D1E1000` | `0x22CF000` | RomFS at `+0x1000` (69 files) |
| Card padding | `0x6F4B0000` | `0x10B50000` | `0xFF` up to the 2 GiB card size |

Partition 0: NCCH header `0x200`, ExHeader `0x400` + access descriptor `0x400`, then a
**separate logo region** `0x2000` at `0xA00`, the plain region `0x400` at `0x2A00`, the
ExeFS at `0x2E00` (`.code`, `banner`, `icon`; no `logo` file, unlike Awakening), zero
pad, RomFS at `0x389000` (`0x6C80F000` bytes; 645 directories, 21,880 files).

RomFS physical order (all four partitions): IVFC header + master hash, level 3, level 1,
level 2, each 4 KiB aligned. The level-3 rules documented for Awakening hold unchanged on
all four Fates RomFS images (`extracted/rom/manifest.json` -> `partitions.N.romfs.rules`,
all true): hash and bucket rules, sibling links, metadata order derivable from the
directory tree, 16-byte file data alignment. So `--romfs-order rule` works here too.

## What changed for Fates

1. **Part order.** `extract.py` used to walk the NCCH parts in a fixed order (plain, logo,
   ExeFS, RomFS) and failed on Fates ("no power-of-two alignment maps 0xA00 to 0x2A00"),
   because Fates' logo region comes *before* the plain region. It now records the parts
   in physical (offset) order in `manifest.json` (`['exheader', 'logo', 'plain', 'exefs',
   'romfs']`), and `rebuild.py` already wrote them in recorded order.
2. **BLZ raw-prefix rule.** The Awakening rule (`cut=le`, keep the *last* point where
   compressed-so-far + raw-remaining is minimal) is 72 bytes off on Fates. Measured with
   `blz.py selftest` on both retail files:

   | Cut rule | Awakening `.code` | Fates `.code` |
   |---|---|---|
   | `end` (new default) | byte-identical | byte-identical |
   | `le` (old default) | byte-identical | 72 bytes differ (raw prefix 78 instead of 161) |
   | `lt` (CUE as published) | 1 byte differs (footer) | byte-identical |
   | `none` | byte-identical | differs (and not in-place safe) |

   On Fates the minimum is reached at 17 cut points and retail keeps the first (a
   161-byte raw prefix, in-place margin exactly 0); on Awakening it is reached at raw 1
   and raw 0 and retail keeps raw 0. `cut="end"` = strict `<` while parsing, but the
   final state (everything compressed) wins a tie. It is the only rule tried that
   reproduces both games. A "smallest safe raw prefix" rule was also tested and does not
   match (it gives 78 on Fates).
3. **Partition set.** Fates has a partition 6 (New 3DS update data) besides 0/1/7; nothing
   in the tools assumed a fixed set, the manifest lists what is there.
4. `tests.py` picks its code-mutation bytes from `config/game.json`'s `.data` segment
   (they were hard-coded Awakening offsets that fall inside Fates' `.text`).
5. `extract_rom.py` streams the RomFS through `tools/rom/romfs.py` instead of reading the
   whole RomFS into memory (1.8 GB on Fates).

## What is regenerated and what is copied

Same as Awakening (see the Awakening port's docs/ROM_REBUILD.md for the full list).
Regenerated: ExeFS `.code` (BLZ from `code.bin`), ExeFS header, every RomFS (level 3
metadata, hash levels, IVFC header), NCCH header sizes/offsets/hashes, NCSD partition
table, card filled size, the card's NCCH header copy (except its 8 flag bytes), all
padding. The build prints "44 header fields regenerated, 44 equal the original".
Copied: signatures (need Nintendo's keys; emulators do not check them), other header
fields, the ExHeader (code set info is not regenerated; `rebuild.py` warns if
`code.bin`'s size disagrees), logo, plain region, `banner`, `icon`, every RomFS file as a
blob (asset converters live in `tools/assets/`, see docs/ASSETS.md).

## Verification done (2026-11-10)

- `extract.py`: 60 regions recorded, 0 problems, BLZ recompression of `.code`
  byte-identical, all RomFS rules true on partitions 0, 1, 6, 7.
- `rebuild.py`: 60/60 regions match; whole-file SHA-256 and SHA-1 equal the original
  ("VERDICT: BYTE-IDENTICAL").
- `rebuild.py verify` on the rebuilt image: 22 hash checks, 0 failures.
- `tests.py`: 14/14 checks pass (BLZ, code mutation: only `p0.ncch_header`,
  `card_info_dev`, `p0.exefs.header`, `p0.exefs..code` differ; RomFS mutation + shift: a
  p7 file changed, another grown by `0x1234`, a new p0 file, image verifies, files read
  back, later partitions move, NCSD table and filled size follow).
- The Awakening `.code` still recompresses byte-identically with the new default
  (`blz.py selftest` pointed at the Awakening port's extracted files, read-only).

## Known gaps

As for Awakening: decrypted dumps only; signatures copied; ExHeader code set info not
regenerated; RomFS files are blobs at this layer. Which BLZ rule Nintendo's tool really
uses is inferred from two samples; `cut="end"` fits both.
