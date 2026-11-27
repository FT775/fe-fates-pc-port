#!/usr/bin/env python3
"""Unpack the RomFS of the user's .cci (the game in config/game.json) straight from the ROM.

Standard library only. Reads the decrypted (NoCrypto) NCCH partition 0, checks the
RomFS superblock hash stored in the NCCH header, optionally checks every IVFC hash level,
and writes every RomFS file to extracted/romfs/ plus a manifest
extracted/assets/romfs_manifest.tsv (path, size, sha1). It never touches
extracted/code.bin or anything else outside extracted/romfs/ and extracted/assets/.

Usage:
    python tools/assets/romfs.py "<path to .cci>" [--verify] [--force]
        --verify   also check all IVFC levels (master -> L1 -> L2 -> L3 data)
        --force    rewrite files even if the manifest says they are already present
    python tools/assets/romfs.py --check
        re-hash extracted/romfs/ against the manifest (detects edited/missing files)

The ROM path defaults to the "rom" key of tools/config.local.json if present, else the shared
order of tools/paths.py (FE_ROM, play/config.json "rom" if that file exists, then the .cci in roms/;
for one release also the old repo-root place). Running
twice is a no-op unless --force is given (files whose size+sha1 already match are kept).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from gamecfg import GAME  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
OUT_ROMFS = os.path.join(ROOT, "extracted", "romfs")
OUT_ASSETS = os.path.join(ROOT, "extracted", "assets")
MANIFEST = os.path.join(OUT_ASSETS, "romfs_manifest.tsv")
MEDIA_UNIT = 0x200
NONE = 0xFFFFFFFF


def fail(msg: str) -> None:
    sys.exit(f"error: {msg}")


def u32(b: bytes, o: int) -> int:
    return struct.unpack_from("<I", b, o)[0]


def u64(b: bytes, o: int) -> int:
    return struct.unpack_from("<Q", b, o)[0]


class RomFS:
    """Random-access view of the RomFS inside a .cci (no full read into memory)."""

    def __init__(self, cci_path: str):
        self.fh = open(cci_path, "rb")
        fh = self.fh
        ncsd = fh.read(0x200)
        if ncsd[0x100:0x104] != b"NCSD":
            fail("not an NCSD (.cci) image")
        p0 = u32(ncsd, 0x120) * MEDIA_UNIT
        fh.seek(p0)
        ncch = fh.read(0x200)
        if ncch[0x100:0x104] != b"NCCH":
            fail("partition 0 is not NCCH")
        if not (ncch[0x18F] & 0x04):
            fail("NCCH is encrypted; decrypt it first")
        pc = ncch[0x150:0x160].rstrip(bytes(1)).decode("ascii", "replace")
        if pc != GAME.product_code:
            fail(f"product code {pc} is not {GAME.product_code} ({GAME.game}, config/game.json)")
        self.base = p0 + u32(ncch, 0x1B0) * MEDIA_UNIT
        self.size = u32(ncch, 0x1B4) * MEDIA_UNIT
        sb_len = u32(ncch, 0x1B8) * MEDIA_UNIT
        fh.seek(self.base)
        sb = fh.read(sb_len)
        if hashlib.sha256(sb).digest() != ncch[0x1E0:0x200]:
            fail("RomFS superblock SHA-256 mismatch")
        if sb[:4] != b"IVFC" or u32(sb, 4) != 0x10000:
            fail("RomFS has no IVFC header")
        self.master_size = u32(sb, 0x08)
        self.levels = []  # (logical off, size, block log2)
        for i in range(3):
            lo, sz, bl, _ = struct.unpack_from("<QQII", sb, 0x0C + i * 0x18)
            self.levels.append((lo, sz, bl))
        self.master = sb[0x60:0x60 + self.master_size]
        b3 = 1 << self.levels[2][2]
        self.l3 = (0x60 + self.master_size + b3 - 1) & ~(b3 - 1)
        h = self.read(self.l3, 0x28)
        (hdr_len, _dho, _dhl, dmo, dml, _fho, _fhl, fmo, fml, data_off) = struct.unpack("<10I", h)
        if hdr_len != 0x28:
            fail(f"unexpected RomFS level-3 header length 0x{hdr_len:X}")
        self.dir_meta = self.read(self.l3 + dmo, dml)
        self.file_meta = self.read(self.l3 + fmo, fml)
        self.data_base = self.l3 + data_off

    def read(self, off: int, n: int) -> bytes:
        self.fh.seek(self.base + off)
        return self.fh.read(n)

    def _name(self, meta: bytes, off: int, name_off: int) -> str:
        n = u32(meta, off + name_off - 4)
        return meta[off + name_off: off + name_off + n].decode("utf-16-le")

    def files(self):
        """Yield (relative posix path, data offset in RomFS, size) in RomFS order."""
        out = []

        def walk(off: int, path: str) -> None:
            _, _, child, fil, _, _ = struct.unpack_from("<6I", self.dir_meta, off)
            f = fil
            while f != NONE:
                sib = u32(self.file_meta, f + 4)
                doff = u64(self.file_meta, f + 8)
                dsize = u64(self.file_meta, f + 16)
                name = self._name(self.file_meta, f, 0x20)
                out.append((path + name, self.data_base + doff, dsize))
                f = sib
            c = child
            while c != NONE:
                sib = u32(self.dir_meta, c + 4)
                walk(c, path + self._name(self.dir_meta, c, 0x18) + "/")
                c = sib

        walk(0, "")
        return out

    def verify_ivfc(self) -> None:
        """Check master -> L1 -> L2 -> L3 hashes (streams the whole RomFS)."""
        (_, s1, b1), (_, s2, b2), (_, s3, b3) = self.levels
        bs3 = 1 << b3
        off3 = self.l3
        off1 = (off3 + s3 + (1 << b1) - 1) & ~((1 << b1) - 1)
        off2 = (off1 + s1 + (1 << b2) - 1) & ~((1 << b2) - 1)

        def check(data_off, data_size, block_log2, hashes, label):
            bs = 1 << block_log2
            nblocks = (data_size + bs - 1) // bs
            bad = 0
            chunk = 1024
            for i0 in range(0, nblocks, chunk):
                buf = self.read(data_off + i0 * bs, min(chunk, nblocks - i0) * bs)
                for j in range(min(chunk, nblocks - i0)):
                    blk = buf[j * bs:(j + 1) * bs].ljust(bs, b"\0")
                    if hashlib.sha256(blk).digest() != hashes[(i0 + j) * 32:(i0 + j + 1) * 32]:
                        bad += 1
            if bad:
                fail(f"IVFC {label}: {bad}/{nblocks} blocks mismatch")
            print(f"IVFC {label}: {nblocks} blocks OK")

        l1 = self.read(off1, s1)
        check(off1, s1, b1, self.master, "level 1")
        l2 = self.read(off2, s2)
        check(off2, s2, b2, l1, "level 2")
        check(off3, s3, b3, l2, "level 3")
        _ = bs3


def load_manifest() -> dict[str, tuple[int, str]]:
    m = {}
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("#") or not line.strip():
                    continue
                p, s, h = line.rstrip("\n").split("\t")
                m[p] = (int(s), h)
    return m


def default_rom() -> str | None:
    cfg = os.path.join(ROOT, "tools", "config.local.json")
    if os.path.exists(cfg):
        with open(cfg, encoding="utf-8") as fh:
            r = json.load(fh).get("rom")
            if r:
                return r
    import paths  # noqa: E402  (tools/paths.py: roms/ first, then the old root place for one release)
    found = paths.try_resolve_rom(repo=ROOT, notes=None)  # shared order: FE_ROM, play/config.json, roms/, old root
    return str(found) if found else None


def check() -> tuple[int, int]:
    m = load_manifest()
    if not m:
        fail("no manifest; run the extractor first")
    bad = 0
    for p, (s, h) in m.items():
        fp = os.path.join(OUT_ROMFS, *p.split("/"))
        if not os.path.exists(fp):
            print("missing", p)
            bad += 1
            continue
        with open(fp, "rb") as fh:
            d = fh.read()
        if len(d) != s or hashlib.sha1(d).hexdigest() != h:
            print("changed", p)
            bad += 1
    print(f"{len(m) - bad}/{len(m)} files match the manifest")
    return len(m) - bad, len(m)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cci", nargs="?")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        good, total = check()
        return 0 if good == total else 1
    cci = a.cci or default_rom()
    if not cci:
        fail("give the .cci path (or set \"rom\" in tools/config.local.json)")
    rf = RomFS(cci)
    if a.verify:
        rf.verify_ivfc()
    old = {} if a.force else load_manifest()
    files = rf.files()
    os.makedirs(OUT_ASSETS, exist_ok=True)
    rows = []
    written = kept = 0
    total = 0
    for path, off, size in files:
        fp = os.path.join(OUT_ROMFS, *path.split("/"))
        data = rf.read(off, size)
        h = hashlib.sha1(data).hexdigest()
        total += size
        rows.append((path, size, h))
        if path in old and old[path] == (size, h) and os.path.exists(fp) and os.path.getsize(fp) == size:
            kept += 1
            continue
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "wb") as fh:
            fh.write(data)
        written += 1
    tmp = MANIFEST + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# path\tsize\tsha1   (generated by tools/assets/romfs.py; RomFS order)\n")
        for p, s, h in rows:
            fh.write(f"{p}\t{s}\t{h}\n")
    os.replace(tmp, MANIFEST)
    print(f"RomFS: {len(rows)} files, {total:,} bytes; wrote {written}, kept {kept}")
    print(f"manifest: {MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
