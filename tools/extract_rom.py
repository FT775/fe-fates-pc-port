#!/usr/bin/env python3
"""Extract the executable (and optionally RomFS) from a decrypted 3DS .cci image.

Pure standard library. Only handles decrypted (NoCrypto) NCCH partitions. Partition 0
must carry the product code in config/game.json (pass --any-game to skip that check).

Usage:
    python tools/extract_rom.py ["<path to .cci>"] [--out extracted] [--romfs] [--any-game]
        the .cci defaults to the one in roms/ (tools/paths.py; one release: the old repo-root place)

Outputs (in --out):
    ncch_header.bin, exheader.bin
    exefs/<name>.bin           raw ExeFS files (.code is still compressed here)
    code.bin                   decompressed .code (text | rodata | data, page aligned)
    text.bin, rodata.bin, data.bin
    layout.json                load addresses, sizes, hashes, dependencies
    romfs/...                  (with --romfs) every file in the RomFS, streamed from
                               the image (Fates: 21,880 files, 1.8 GB)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gamecfg import GAME  # noqa: E402

MEDIA_UNIT = 0x200
PAGE = 0x1000


def u32(b: bytes, o: int) -> int:
    return struct.unpack_from("<I", b, o)[0]


def u64(b: bytes, o: int) -> int:
    return struct.unpack_from("<Q", b, o)[0]


def sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def fail(msg: str) -> None:
    sys.exit(f"error: {msg}")


# --------------------------------------------------------------------------- BLZ
def blz_decompress(comp: bytes) -> bytes:
    """Decompress 3DS ExeFS '.code' (backwards LZ77, a.k.a. BLZ)."""
    if len(comp) < 8:
        fail("compressed .code too small")
    top_bottom = u32(comp, len(comp) - 8)
    extra = u32(comp, len(comp) - 4)
    header_len = top_bottom >> 24
    enc_len = top_bottom & 0xFFFFFF
    out = bytearray(comp) + bytearray(extra)
    src = len(comp) - header_len  # read pointer, moves down
    end = len(comp) - enc_len     # stop when src reaches this
    dst = len(out)                # write pointer, moves down
    if end < 0 or src > len(comp):
        fail("bad BLZ footer")
    while src > end:
        src -= 1
        flags = out[src]
        for _ in range(8):
            if flags & 0x80:
                src -= 2
                info = out[src] | (out[src + 1] << 8)
                length = (info >> 12) + 3
                disp = (info & 0xFFF) + 3
                for _ in range(length):
                    dst -= 1
                    out[dst] = out[dst + disp]
            else:
                src -= 1
                dst -= 1
                out[dst] = out[src]
            flags = (flags << 1) & 0xFF
            if src <= end:
                break
    if dst != end:
        # Decoder must meet the untouched prefix exactly; anything else means corruption.
        fail(f"BLZ decode misaligned (dst=0x{dst:X}, expected 0x{end:X})")
    return bytes(out)


# -------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cci", nargs="?", default=None)
    ap.add_argument("--out", default="extracted")
    ap.add_argument("--romfs", action="store_true", help="also extract every RomFS file")
    ap.add_argument("--any-game", action="store_true", help="skip the product-code check")
    a = ap.parse_args()
    if a.cci is None:
        import paths  # noqa: E402  (tools/paths.py: roms/ first, then the old root place for one release)
        try:
            a.cci = str(paths.find_rom(repo=Path(HERE).parent, check="header"))
        except paths.PathError as e:
            fail(str(e))
    if not os.path.isfile(a.cci):
        fail(f"no ROM at {a.cci}")

    os.makedirs(os.path.join(a.out, "exefs"), exist_ok=True)
    with open(a.cci, "rb") as fh:
        ncsd = fh.read(0x200)
        if ncsd[0x100:0x104] != b"NCSD":
            fail("not an NCSD (.cci) image")
        p0_off = u32(ncsd, 0x120) * MEDIA_UNIT
        p0_len = u32(ncsd, 0x124) * MEDIA_UNIT
        fh.seek(p0_off)
        ncch = fh.read(0x200)
        if ncch[0x100:0x104] != b"NCCH":
            fail("partition 0 is not NCCH")
        if not (ncch[0x18F] & 0x04):
            fail("NCCH is encrypted; decrypt it first (e.g. with GodMode9)")
        pc = ncch[0x150:0x160].rstrip(b"\0").decode("ascii", "replace")
        if pc != GAME.product_code and not a.any_game:
            fail(f"product code {pc} is not {GAME.product_code} ({GAME.game}); "
                 f"wrong ROM, or pass --any-game")

        exh_size = u32(ncch, 0x180)
        exefs_off = u32(ncch, 0x1A0) * MEDIA_UNIT
        exefs_len = u32(ncch, 0x1A4) * MEDIA_UNIT
        exefs_hash_len = u32(ncch, 0x1A8) * MEDIA_UNIT
        romfs_off = u32(ncch, 0x1B0) * MEDIA_UNIT
        romfs_len = u32(ncch, 0x1B4) * MEDIA_UNIT

        fh.seek(p0_off + 0x200)
        exheader = fh.read(0x800)
        fh.seek(p0_off + exefs_off)
        exefs = fh.read(exefs_len)

    # Integrity checks against the hashes stored in the NCCH header.
    if sha256(exheader[:exh_size]) != ncch[0x160:0x180]:
        fail("ExHeader SHA-256 mismatch")
    if sha256(exefs[:exefs_hash_len]) != ncch[0x1C0:0x1E0]:
        fail("ExeFS superblock SHA-256 mismatch")

    with open(os.path.join(a.out, "ncch_header.bin"), "wb") as fh:
        fh.write(ncch)
    with open(os.path.join(a.out, "exheader.bin"), "wb") as fh:
        fh.write(exheader)

    files = {}
    for i in range(10):
        name = exefs[i * 16: i * 16 + 8].rstrip(b"\0").decode("ascii")
        if not name:
            continue
        off, size = struct.unpack_from("<II", exefs, i * 16 + 8)
        data = exefs[0x200 + off: 0x200 + off + size]
        want = exefs[0x200 - 0x20 * (i + 1): 0x200 - 0x20 * i]
        if sha256(data) != want:
            fail(f"ExeFS file {name} SHA-256 mismatch")
        files[name] = data
        with open(os.path.join(a.out, "exefs", name.lstrip(".") + ".bin"), "wb") as fh:
            fh.write(data)

    # ExHeader code set info.
    flags = exheader[0x0D]
    def cs(o):
        addr, pages, size = struct.unpack_from("<III", exheader, o)
        return {"addr": addr, "pages": pages, "size": size}
    text, ro, data = cs(0x10), cs(0x20), cs(0x30)
    bss = u32(exheader, 0x3C)
    stack = u32(exheader, 0x1C)
    deps = [f"{u64(exheader, 0x40 + 8 * i):016X}" for i in range(48) if u64(exheader, 0x40 + 8 * i)]

    code = files[".code"]
    if flags & 1:
        code = blz_decompress(code)

    text_b = code[0: text["size"]]
    ro_start = text["pages"] * PAGE
    ro_b = code[ro_start: ro_start + ro["size"]]
    data_start = ro_start + ro["pages"] * PAGE
    data_b = code[data_start: data_start + data["size"]]
    expected_len = data_start + data["size"]
    if len(code) < expected_len:
        fail(f"code.bin is 0x{len(code):X} bytes, ExHeader says at least 0x{expected_len:X}")

    for name, blob in (("code.bin", code), ("text.bin", text_b), ("rodata.bin", ro_b), ("data.bin", data_b)):
        with open(os.path.join(a.out, name), "wb") as fh:
            fh.write(blob)

    layout = {
        "product_code": ncch[0x150:0x160].rstrip(b"\0").decode("ascii"),
        "program_id": f"{u64(ncch, 0x118):016X}",
        "app_title": exheader[0:8].rstrip(b"\0").decode("ascii", "replace"),
        "code_compressed": bool(flags & 1),
        "text": {**text, "file_offset": 0, "sha1": sha1(text_b)},
        "rodata": {**ro, "file_offset": ro_start, "sha1": sha1(ro_b)},
        "data": {**data, "file_offset": data_start, "sha1": sha1(data_b)},
        "bss_size": bss,
        "stack_size": stack,
        "code_bin": {"size": len(code), "sha1": sha1(code)},
        "code_compressed_sha1": sha1(files[".code"]),
        "dependencies": deps,
        "exefs_files": {k: {"size": len(v), "sha1": sha1(v)} for k, v in files.items()},
    }
    with open(os.path.join(a.out, "layout.json"), "w") as fh:
        json.dump(layout, fh, indent=2)

    print(json.dumps({k: layout[k] for k in ("product_code", "app_title", "text", "rodata", "data", "bss_size", "code_bin")}, indent=2))

    if a.romfs and romfs_len:
        # Streamed (tools/rom/romfs.py): never holds the RomFS in memory.
        sys.path.insert(0, os.path.join(HERE, "rom"))
        import romfs as romfs_mod  # tools/rom/romfs.py
        with open(a.cci, "rb") as fh:
            info = romfs_mod.extract_romfs(fh, p0_off + romfs_off, Path(a.out) / "romfs")
        print(f"RomFS: extracted {len(info['files'])} files")


if __name__ == "__main__":
    main()
