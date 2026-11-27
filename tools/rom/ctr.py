"""3DS container formats shared by tools/rom/*.py: NCSD (.cci), NCCH, ExeFS, IVFC.

Stdlib only. Everything here works on decrypted (NoCrypto) images. `image_regions()`
splits any .cci (original or rebuilt) into named, contiguous regions that cover the whole
file, so two images can be compared region by region (tools/rom/rebuild.py compare).
"""
from __future__ import annotations

import hashlib
import struct
from typing import BinaryIO

MU = 0x200                 # media unit
NONE32 = 0xFFFFFFFF
IVFC_BLOCK_LOG2 = 12
CHUNK = 16 << 20           # streaming chunk size

# NCSD header fields (offsets into the first 0x200 bytes of the image).
NCSD_MAGIC = 0x100
NCSD_IMAGE_SIZE = 0x104    # u32, media units (card capacity)
NCSD_PART_TABLE = 0x120    # 8 x (u32 offset, u32 size), media units
NCSD_PART_IDS = 0x190      # 8 x u64
CARD_FILLED_SIZE = 0x300   # u32 bytes: end of the last partition (card info header)
CARD_NCCH_COPY = 0x1100    # 0x100 bytes: copy of partition 0 NCCH header 0x100..0x200

# NCCH header fields.
NCCH_SIZE = 0x104
NCCH_EXH_HASH = 0x160
NCCH_EXH_SIZE = 0x180
NCCH_FLAGS = 0x188
NCCH_PLAIN = 0x190
NCCH_LOGO = 0x198
NCCH_EXEFS = 0x1A0         # off, size, hash region size (media units)
NCCH_ROMFS = 0x1B0
NCCH_EXEFS_HASH = 0x1C0
NCCH_ROMFS_HASH = 0x1E0


def u32(b, o: int) -> int:
    return struct.unpack_from("<I", b, o)[0]


def u64(b, o: int) -> int:
    return struct.unpack_from("<Q", b, o)[0]


def align(x: int, a: int) -> int:
    return (x + a - 1) // a * a


def sha256(b) -> bytes:
    return hashlib.sha256(b).digest()


def read_at(fh: BinaryIO, off: int, n: int) -> bytes:
    fh.seek(off)
    b = fh.read(n)
    if len(b) != n:
        raise ValueError(f"short read at 0x{off:X} (wanted 0x{n:X}, got 0x{len(b):X})")
    return b


# ----------------------------------------------------------------------------- NCSD
def parse_ncsd(hdr: bytes) -> dict:
    if hdr[NCSD_MAGIC:NCSD_MAGIC + 4] != b"NCSD":
        raise ValueError("not an NCSD (.cci) image")
    parts = []
    for i in range(8):
        off, size = struct.unpack_from("<II", hdr, NCSD_PART_TABLE + 8 * i)
        if size:
            parts.append({"index": i, "offset": off * MU, "size": size * MU,
                          "id": f"{u64(hdr, NCSD_PART_IDS + 8 * i):016X}"})
    return {"image_size": u32(hdr, NCSD_IMAGE_SIZE) * MU, "partitions": parts}


# ----------------------------------------------------------------------------- NCCH
def parse_ncch(h: bytes) -> dict:
    if h[0x100:0x104] != b"NCCH":
        raise ValueError("not an NCCH header")
    def span(o):
        return u32(h, o) * MU, u32(h, o + 4) * MU
    d = {
        "size": u32(h, NCCH_SIZE) * MU,
        "exh_size": u32(h, NCCH_EXH_SIZE),
        "nocrypto": bool(h[NCCH_FLAGS + 7] & 0x04),
        "plain": span(NCCH_PLAIN),
        "logo": span(NCCH_LOGO),
        "exefs": span(NCCH_EXEFS),
        "exefs_hash_size": u32(h, NCCH_EXEFS + 8) * MU,
        "romfs": span(NCCH_ROMFS),
        "romfs_hash_size": u32(h, NCCH_ROMFS + 8) * MU,
        "product_code": h[0x150:0x160].rstrip(b"\0").decode("ascii", "replace"),
        "program_id": f"{u64(h, 0x118):016X}",
    }
    # The ExHeader (0x400) is always followed by the access descriptor (0x400).
    d["exh_region"] = (0x200, 0x800) if d["exh_size"] else (0x200, 0)
    return d


# ---------------------------------------------------------------------------- ExeFS
def parse_exefs_header(h: bytes) -> list[dict]:
    files = []
    for i in range(10):
        name = h[i * 16:i * 16 + 8].rstrip(b"\0")
        off, size = struct.unpack_from("<II", h, i * 16 + 8)
        if not name:
            continue
        files.append({"slot": i, "name": name.decode("ascii"), "offset": off, "size": size,
                      "sha256": h[0x200 - 0x20 * (i + 1):0x200 - 0x20 * i]})
    return files


def build_exefs_header(entries: list[tuple[str, bytes]]) -> tuple[bytes, list[int]]:
    """ExeFS header for files in slot order; files start 0x200-aligned after the header.
    Returns (header, file offsets relative to the end of the header)."""
    if len(entries) > 10:
        raise ValueError("ExeFS holds at most 10 files")
    h = bytearray(0x200)
    offs = []
    cur = 0
    for i, (name, data) in enumerate(entries):
        nb = name.encode("ascii")
        if len(nb) > 8:
            raise ValueError(f"ExeFS name too long: {name}")
        struct.pack_into("<8sII", h, i * 16, nb, cur, len(data))
        h[0x200 - 0x20 * (i + 1):0x200 - 0x20 * i] = sha256(data)
        offs.append(cur)
        cur = align(cur + len(data), MU)
    return bytes(h), offs


# ----------------------------------------------------------------------------- IVFC
def parse_ivfc(h: bytes) -> dict:
    if h[:4] != b"IVFC" or u32(h, 4) != 0x10000:
        raise ValueError("bad IVFC header")
    levels = []
    for k in range(3):
        lo, size, bl = struct.unpack_from("<QQI", h, 0x0C + 0x18 * k)
        levels.append({"logical": lo, "size": size, "block_log2": bl})
    mh = u32(h, 8)
    bs3 = 1 << levels[2]["block_log2"]
    l3 = align(0x60 + mh, bs3)
    bs1 = 1 << levels[0]["block_log2"]
    l1 = align(l3 + levels[2]["size"], bs1)
    bs2 = 1 << levels[1]["block_log2"]
    l2 = align(l1 + levels[0]["size"], bs2)
    return {"master_size": mh, "levels": levels, "l3_off": l3, "l1_off": l1, "l2_off": l2,
            "end": align(l2 + levels[1]["size"], bs2)}


def ivfc_sizes(l3_size: int, bl: int = IVFC_BLOCK_LOG2) -> tuple[int, int, int]:
    """(master hash size, level 1 size, level 2 size) for a level-3 size."""
    bs = 1 << bl
    l2 = (l3_size + bs - 1) // bs * 0x20
    l1 = (l2 + bs - 1) // bs * 0x20
    mh = (l1 + bs - 1) // bs * 0x20
    return mh, l1, l2


def build_ivfc_header(l3_size: int, bl: int = IVFC_BLOCK_LOG2) -> bytes:
    mh, l1, l2 = ivfc_sizes(l3_size, bl)
    bs = 1 << bl
    h = bytearray(0x60)
    h[0:4] = b"IVFC"
    struct.pack_into("<II", h, 4, 0x10000, mh)
    lo = 0
    for k, size in enumerate((l1, l2, l3_size)):
        struct.pack_into("<QQI", h, 0x0C + 0x18 * k, lo, size, bl)
        lo = align(lo + size, bs)
    struct.pack_into("<I", h, 0x54, 0x5C)
    return bytes(h)


# ------------------------------------------------------------------- region listing
def _ncch_regions(fh: BinaryIO, base: int, prefix: str) -> list[tuple[str, int, int]]:
    """Named sub-regions (absolute offset, size) of one NCCH, in file order, gaps included."""
    h = read_at(fh, base, 0x200)
    n = parse_ncch(h)
    regs = [(f"{prefix}.ncch_header", base, 0x200)]
    if n["exh_region"][1]:
        regs.append((f"{prefix}.exheader", base + 0x200, 0x400))
        regs.append((f"{prefix}.access_desc", base + 0x600, 0x400))
    if n["plain"][1]:
        regs.append((f"{prefix}.plain", base + n["plain"][0], n["plain"][1]))
    if n["logo"][1]:
        regs.append((f"{prefix}.logo", base + n["logo"][0], n["logo"][1]))
    if n["exefs"][1]:
        eo = base + n["exefs"][0]
        regs.append((f"{prefix}.exefs.header", eo, 0x200))
        for f in parse_exefs_header(read_at(fh, eo, 0x200)):
            regs.append((f"{prefix}.exefs.{f['name']}", eo + 0x200 + f["offset"], f["size"]))
        regs.append((f"{prefix}.exefs._end", eo + n["exefs"][1], 0))
    if n["romfs"][1]:
        ro = base + n["romfs"][0]
        iv = parse_ivfc(read_at(fh, ro, 0x60))
        l3 = ro + iv["l3_off"]
        data_off = u32(read_at(fh, l3, 0x28), 0x24)
        regs.append((f"{prefix}.romfs.ivfc_header", ro, 0x60 + iv["master_size"]))
        regs.append((f"{prefix}.romfs.l3_meta", l3, data_off))
        regs.append((f"{prefix}.romfs.l3_data", l3 + data_off, iv["levels"][2]["size"] - data_off))
        regs.append((f"{prefix}.romfs.l1", ro + iv["l1_off"], iv["levels"][0]["size"]))
        regs.append((f"{prefix}.romfs.l2", ro + iv["l2_off"], iv["levels"][1]["size"]))
        regs.append((f"{prefix}.romfs._end", ro + n["romfs"][1], 0))
    regs.append((f"{prefix}._end", base + n["size"], 0))
    return regs


def image_regions(fh: BinaryIO, file_size: int) -> list[tuple[str, int, int]]:
    """Cover [0, file_size) with named regions; holes become '<prev>+pad' regions.
    Zero-size '_end' markers only delimit padding and are dropped."""
    hdr = read_at(fh, 0, 0x200)
    nc = parse_ncsd(hdr)
    marks = [("ncsd_header", 0, 0x200), ("card_info", 0x200, 0x1000 - 0x200),
             ("card_info_dev", 0x1000, 0x200)]
    for p in nc["partitions"]:
        marks += _ncch_regions(fh, p["offset"], f"p{p['index']}")
    out: list[tuple[str, int, int]] = []
    cur = 0
    last = "start"
    for name, off, size in sorted(marks, key=lambda r: (r[1], r[2] != 0)):
        if off < cur:
            raise ValueError(f"overlapping regions at {name} 0x{off:X} < 0x{cur:X}")
        if off > cur:
            out.append((f"{last}+pad", cur, off - cur))
        if size:
            out.append((name, off, size))
        cur = off + size
        last = name[:-5] if name.endswith("._end") else name
    if file_size > cur:
        out.append(("card_padding" if last == f"p{nc['partitions'][-1]['index']}" else f"{last}+pad",
                    cur, file_size - cur))
    return out


def hash_regions(fh: BinaryIO, regions: list[tuple[str, int, int]], file_size: int,
                 progress=None) -> tuple[dict, str, str]:
    """One sequential pass: per-region SHA-256 plus whole-file SHA-256 and SHA-1.
    Regions must be contiguous and sorted (as image_regions returns them)."""
    whole256 = hashlib.sha256()
    whole1 = hashlib.sha1()
    res = {}
    fh.seek(0)
    pos = 0
    for name, off, size in regions:
        if off != pos:
            raise ValueError("regions not contiguous")
        h = hashlib.sha256()
        left = size
        while left:
            b = fh.read(min(CHUNK, left))
            if not b:
                raise ValueError("file shorter than regions")
            h.update(b)
            whole256.update(b)
            whole1.update(b)
            left -= len(b)
            pos += len(b)
            if progress:
                progress(pos, file_size)
        res[name] = {"offset": off, "size": size, "sha256": h.hexdigest()}
    if pos != file_size:
        raise ValueError("regions do not cover the file")
    return res, whole256.hexdigest(), whole1.hexdigest()
