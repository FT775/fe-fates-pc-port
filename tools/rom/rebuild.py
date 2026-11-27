#!/usr/bin/env python3
"""Rebuild the whole .cci (the game in config/game.json) from code.bin + extracted parts, and compare it.

Usage:
    python tools/rom/rebuild.py [build] [--code PATH] [--parts DIR] [--out FILE]
                                [--romfs-order manifest|rule] [--no-compare]
    python tools/rom/rebuild.py compare [IMAGE] [--parts DIR] [--rom ORIGINAL.cci]
    python tools/rom/rebuild.py verify  [IMAGE]

build (default):
    --code   decompressed code.bin; default build/code.bin if present, else
             extracted/code.bin. It is BLZ-compressed into ExeFS .code by tools/rom/blz.py
             (byte-identical to retail when code.bin is the retail one).
    --parts  output of tools/rom/extract.py (default extracted/rom)
    --out    default build/rom/rebuilt.cci (2 GiB; card padding is written as 0xFF)
    --romfs-order  'manifest' (default) uses p<N>/romfs_order.json; 'rule' derives the
             order from the directory tree (sorted, see tools/rom/romfs.py), which is
             what you want after adding or renaming RomFS files.
    Then runs `compare` on the result unless --no-compare.

compare:
    Splits IMAGE (default build/rom/rebuilt.cci) into named regions (headers, ExeFS files,
    RomFS levels, paddings) and checks each region's SHA-256 and the whole-file SHA-256 /
    SHA-1 against extracted/rom/manifest.json (taken from the original by extract.py).
    --rom additionally streams the original and IMAGE side by side and prints the first
    differing offsets. Report: build/rom/compare.txt. Exit 0 iff the whole file matches.

verify:
    Internal consistency of any .cci (works on modified builds, needs no manifest):
    ExHeader, ExeFS superblock and per-file SHA-256, .code BLZ decodes, RomFS superblock
    SHA-256 and every IVFC level's block hashes. Exit 0 iff all pass.

What is regenerated vs copied: see docs/ROM_REBUILD.md. Signatures (NCSD, NCCH, access
descriptor) cannot be regenerated without Nintendo's keys and are copied from the
templates in extracted/rom/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blz  # noqa: E402
import romfs  # noqa: E402
from ctr import (CHUNK, MU, NCCH_EXEFS, NCCH_EXEFS_HASH, NCCH_EXH_HASH, NCCH_EXH_SIZE,  # noqa: E402
                 NCCH_LOGO, NCCH_PLAIN, NCCH_ROMFS, NCCH_ROMFS_HASH, NCCH_SIZE, NCSD_PART_TABLE,
                 CARD_FILLED_SIZE, CARD_NCCH_COPY, align, build_exefs_header, hash_regions,
                 image_regions, sha256, u32)

ROOT = Path(__file__).resolve().parent.parent.parent
PAGE = 0x1000


def log(msg: str) -> None:
    print(msg, flush=True)


def pad_to(out, target: int, fill: int = 0) -> None:
    n = target - out.tell()
    if n < 0:
        raise ValueError(f"layout overflow: at 0x{out.tell():X}, wanted 0x{target:X}")
    block = bytes([fill]) * min(n, CHUNK)
    while n:
        k = min(n, CHUNK)
        out.write(block[:k])
        n -= k


class FieldLog:
    """Records regenerated header fields and whether they equal the original template."""

    def __init__(self):
        self.rows: list[tuple[str, bool]] = []

    def put(self, buf: bytearray, tmpl: bytes, off: int, data: bytes, name: str) -> None:
        buf[off:off + len(data)] = data
        self.rows.append((name, tmpl[off:off + len(data)] == data))

    def summary(self) -> str:
        bad = [n for n, ok in self.rows if not ok]
        s = f"{len(self.rows)} header fields regenerated, {len(self.rows) - len(bad)} equal the original"
        return s + (f"; differ: {', '.join(bad)}" if bad else "")


def check_exheader(exh: bytes, code_len: int) -> list[str]:
    warn = []
    pages = [u32(exh, o + 4) for o in (0x10, 0x20, 0x30)]
    if sum(pages) * PAGE != code_len:
        warn.append(f"code.bin is 0x{code_len:X} bytes but the ExHeader code set covers "
                    f"0x{sum(pages) * PAGE:X} (text/rodata/data pages {pages}); the ExHeader is "
                    f"copied, not regenerated, so this image will not load correctly")
    return warn


def build_ncch(out, pidx: int, pm: dict, pdir: Path, code_blob: bytes | None, order_mode: str,
               fields: FieldLog) -> tuple[int, bytes]:
    base = out.tell()
    tmpl = (pdir / "ncch_header.bin").read_bytes()
    hdr = bytearray(tmpl)
    out.write(bytes(0x200))
    cur = 0x200
    tag = f"p{pidx}"
    spans = {"plain": (0, 0), "logo": (0, 0), "exefs": (0, 0), "romfs": (0, 0)}
    hashes = {}
    hash_sizes = {"exefs": 0, "romfs": 0}
    if "exheader" in pm["parts"]:
        exh = (pdir / "exheader.bin").read_bytes()
        out.write(exh)
        exh_size = u32(tmpl, NCCH_EXH_SIZE)
        fields.put(hdr, tmpl, NCCH_EXH_HASH, sha256(exh[:exh_size]), f"{tag}.exheader_sha256")
        cur = 0x200 + len(exh)
        if code_blob is not None:
            for w in check_exheader(exh, pm["_code_len"]):
                log("WARNING: " + w)
    for key in pm["parts"]:
        if key == "exheader":
            continue
        off = align(cur, pm["aligns"][key])
        pad_to(out, base + off)
        if key in ("plain", "logo"):
            data = (pdir / f"{key}.bin").read_bytes()
            out.write(data)
            size = len(data)
            if key == "logo":
                fields.put(hdr, tmpl, 0x130, sha256(data), f"{tag}.logo_sha256")
        elif key == "exefs":
            entries = []
            for name in pm["exefs_order"]:
                if name == ".code" and code_blob is not None:
                    entries.append((name, code_blob))
                else:
                    entries.append((name, (pdir / "exefs" / (name.lstrip(".") + ".bin")).read_bytes()))
            eh, offs = build_exefs_header(entries)
            out.write(eh)
            for (name, data), fo in zip(entries, offs):
                pad_to(out, base + off + 0x200 + fo)
                out.write(data)
            last = offs[-1] + len(entries[-1][1]) if entries else 0
            size = 0x200 + align(last, MU)
            pad_to(out, base + off + size)
            hash_sizes["exefs"] = 0x200
            hashes["exefs"] = sha256(eh)
        elif key == "romfs":
            rroot = pdir / "romfs"
            if order_mode == "rule":
                dirs, files = romfs.order_by_rule(*romfs.scan_tree(rroot))
            else:
                o = json.loads((pdir / "romfs_order.json").read_text(encoding="utf-8"))
                dirs, files = o["dirs"], o["files"]
            t = time.time()
            size, superblock, info = romfs.write_romfs(out, dirs, files, rroot)
            hs = align(len(superblock), MU)
            hash_sizes["romfs"] = hs
            hashes["romfs"] = sha256(superblock + bytes(hs - len(superblock)))
            log(f"  {tag} RomFS: {info['dirs']} dirs, {info['files']} files, "
                f"0x{size:X} bytes ({time.time() - t:.0f}s)")
        else:
            raise ValueError(f"unknown NCCH part {key}")
        spans[key] = (off, size)
        cur = off + size
    total = align(cur, MU)
    pad_to(out, base + total)

    fields.put(hdr, tmpl, NCCH_SIZE, struct.pack("<I", total // MU), f"{tag}.content_size")
    for key, fo in (("plain", NCCH_PLAIN), ("logo", NCCH_LOGO), ("exefs", NCCH_EXEFS), ("romfs", NCCH_ROMFS)):
        off, size = spans[key]
        fields.put(hdr, tmpl, fo, struct.pack("<II", off // MU, size // MU), f"{tag}.{key}_span")
        if key in hash_sizes:
            fields.put(hdr, tmpl, fo + 8, struct.pack("<I", hash_sizes[key] // MU), f"{tag}.{key}_hash_size")
    fields.put(hdr, tmpl, NCCH_EXEFS_HASH, hashes.get("exefs", bytes(32)), f"{tag}.exefs_superblock_sha256")
    fields.put(hdr, tmpl, NCCH_ROMFS_HASH, hashes.get("romfs", bytes(32)), f"{tag}.romfs_superblock_sha256")
    end = out.tell()
    out.seek(base)
    out.write(hdr)
    out.seek(end)
    return total, bytes(hdr)


def cmd_build(a) -> int:
    t0 = time.time()
    parts = Path(a.parts)
    man = json.loads((parts / "manifest.json").read_text(encoding="utf-8"))
    if man.get("problems"):
        log("WARNING: extract.py reported problems: " + "; ".join(man["problems"]))
    code_path = Path(a.code) if a.code else (
        ROOT / "build" / "code.bin" if (ROOT / "build" / "code.bin").is_file() else ROOT / "extracted" / "code.bin")
    code = code_path.read_bytes()
    code_sha1 = hashlib.sha1(code).hexdigest()
    retail = code_sha1 == man.get("code_bin_sha1")
    log(f"code.bin: {code_path} sha1 {code_sha1} ({'retail' if retail else 'MODIFIED'})")
    t = time.time()
    code_blob = blz.compress(code)
    margin = blz.inplace_margin(code_blob)
    same = hashlib.sha256(code_blob).hexdigest() == man["partitions"]["0"].get("code_compressed_sha256")
    log(f"  BLZ .code: 0x{len(code_blob):X} bytes ({time.time() - t:.1f}s), "
        f"{'identical to retail .code' if same else 'differs from retail .code'}, "
        f"in-place margin {margin}{'' if margin >= 0 else ' (UNSAFE for in-place decompression)'}")
    man["partitions"]["0"]["_code_len"] = len(code)

    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ncsd_t = (parts / "ncsd_header.bin").read_bytes()
    card_t = (parts / "card_info.bin").read_bytes()
    ncsd = bytearray(ncsd_t)
    card = bytearray(card_t)
    fields = FieldLog()
    built = []
    p0_hdr = None
    with open(out_path, "wb") as out:
        out.write(ncsd_t)
        out.write(card_t)
        prev_end = None
        for pe in man["ncsd"]["partitions"]:
            idx = pe["index"]
            off = man["ncsd"]["first_partition"] if prev_end is None else align(prev_end, pe["align"])
            pad_to(out, off)
            log(f"partition {idx} at 0x{off:X}")
            size, hdr = build_ncch(out, idx, man["partitions"][str(idx)], parts / f"p{idx}",
                                   code_blob if idx == 0 else None, a.romfs_order, fields)
            if idx == 0:
                p0_hdr = hdr
            built.append((idx, off, size))
            prev_end = off + size
        filled = prev_end
        log(f"card padding 0x{filled:X} .. 0x{man['ncsd']['image_size']:X}")
        pad_to(out, man["ncsd"]["image_size"], 0xFF)
        for idx, off, size in built:
            fields.put(ncsd, ncsd_t, NCSD_PART_TABLE + 8 * idx, struct.pack("<II", off // MU, size // MU),
                       f"ncsd.partition{idx}")
        fields.put(card, card_t, CARD_FILLED_SIZE - 0x200, struct.pack("<I", filled), "card.filled_size")
        if p0_hdr is not None:
            # Copy of the partition-0 NCCH header, except its flags: the card keeps the
            # original (encrypted) flags, the decrypted dump's NCCH header has NoCrypto set.
            o = CARD_NCCH_COPY - 0x200
            copy = bytearray(p0_hdr[0x100:0x200])
            copy[0x88:0x90] = card_t[o + 0x88:o + 0x90]
            fields.put(card, card_t, o, bytes(copy), "card.ncch_header_copy")
        out.seek(0)
        out.write(ncsd)
        out.write(card)
    log(fields.summary())
    log(f"wrote {out_path} ({time.time() - t0:.0f}s)")
    if a.no_compare:
        return 0
    return compare(out_path, parts, None)


def compare(image: Path, parts: Path, rom: Path | None) -> int:
    t0 = time.time()
    man = json.loads((parts / "manifest.json").read_text(encoding="utf-8"))
    ref = man["regions"]
    size = image.stat().st_size
    lines = []
    with open(image, "rb") as fh:
        regions = image_regions(fh, size)
        table, w256, w1 = hash_regions(fh, regions, size)
    ok = bad = 0
    for name in list(ref) + [n for n in table if n not in ref]:
        r, m = ref.get(name), table.get(name)
        if r is None or m is None:
            lines.append(f"MISSING  {name:34s} {'only in original' if m is None else 'only in rebuilt'}")
            bad += 1
            continue
        same = (r["offset"], r["size"], r["sha256"]) == (m["offset"], m["size"], m["sha256"])
        ok += same
        bad += not same
        lines.append(f"{'match   ' if same else 'DIFFER  '} {name:34s} 0x{m['offset']:09X} 0x{m['size']:09X}"
                     + ("" if same else f"  (original 0x{r['offset']:X} 0x{r['size']:X})"))
    whole = w256 == man["rom"]["sha256"]
    lines.append("")
    lines.append(f"regions: {ok} match, {bad} differ or missing (of {len(ref)} in the original)")
    lines.append(f"size     {size} vs original {man['rom']['size']}")
    lines.append(f"sha256   {w256} {'== original' if whole else '!= original ' + man['rom']['sha256']}")
    lines.append(f"sha1     {w1} {'== original' if w1 == man['rom']['sha1'] else '!= original'}")
    if rom is not None:
        lines.append("")
        lines.append("direct byte comparison with " + str(rom) + ":")
        lines += _direct_diff(image, rom)
    lines.append(f"VERDICT: {'BYTE-IDENTICAL' if whole else 'DIFFERENT'} ({time.time() - t0:.0f}s)")
    report = "\n".join(lines)
    print(report)
    rp = ROOT / "build" / "rom" / "compare.txt"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(report + "\n", encoding="utf-8")
    return 0 if whole else 1


def verify(image: Path) -> int:
    """Internal consistency of any .cci: every hash the console/emulators can check."""
    from ctr import parse_exefs_header, parse_ivfc, parse_ncch, parse_ncsd, read_at
    t0 = time.time()
    errs, checks = [], 0
    with open(image, "rb") as fh:
        nc = parse_ncsd(read_at(fh, 0, 0x200))
        for p in nc["partitions"]:
            base, tag = p["offset"], f"p{p['index']}"
            h = read_at(fh, base, 0x200)
            n = parse_ncch(h)
            def chk(cond, what):
                nonlocal checks
                checks += 1
                if not cond:
                    errs.append(f"{tag}: {what}")
            if n["exh_size"]:
                chk(sha256(read_at(fh, base + 0x200, n["exh_size"])) == h[NCCH_EXH_HASH:NCCH_EXH_HASH + 32],
                    "ExHeader SHA-256")
            if n["exefs"][1]:
                eo = base + n["exefs"][0]
                eh = read_at(fh, eo, 0x200)
                chk(sha256(read_at(fh, eo, n["exefs_hash_size"])) == h[NCCH_EXEFS_HASH:NCCH_EXEFS_HASH + 32],
                    "ExeFS superblock SHA-256")
                for f in parse_exefs_header(eh):
                    data = read_at(fh, eo + 0x200 + f["offset"], f["size"])
                    chk(sha256(data) == f["sha256"], f"ExeFS {f['name']} SHA-256")
                    if f["name"] == ".code":
                        try:
                            blz.decompress(data)
                            chk(True, "")
                        except blz.BLZError as e:
                            chk(False, f".code BLZ: {e}")
            if n["romfs"][1]:
                ro = base + n["romfs"][0]
                iv = parse_ivfc(read_at(fh, ro, 0x60))
                chk(sha256(read_at(fh, ro, n["romfs_hash_size"])) == h[NCCH_ROMFS_HASH:NCCH_ROMFS_HASH + 32],
                    "RomFS superblock SHA-256")
                lv = iv["levels"]
                master = read_at(fh, ro + 0x60, iv["master_size"])
                # (child data offset, size, stored hashes): L1 <- master, L2 <- L1, L3 <- L2
                for name, coff, csize, hashes in (
                        ("L1", iv["l1_off"], lv[0]["size"], master),
                        ("L2", iv["l2_off"], lv[1]["size"], read_at(fh, ro + iv["l1_off"], lv[0]["size"])),
                        ("L3", iv["l3_off"], lv[2]["size"], read_at(fh, ro + iv["l2_off"], lv[1]["size"]))):
                    w = romfs.BlockHashWriter(romfs._Null(), 1 << 12)
                    fh.seek(ro + coff)
                    left = csize
                    while left:
                        b = fh.read(min(CHUNK, left))
                        w.write(b)
                        left -= len(b)
                    chk(w.finish() == hashes, f"RomFS {name} block hashes")
    for e in errs:
        print("FAIL", e)
    print(f"verify {image}: {checks} hash checks, {len(errs)} failures ({time.time() - t0:.0f}s)")
    return 1 if errs else 0


def _direct_diff(a: Path, b: Path, limit: int = 20) -> list[str]:
    out = []
    pos = 0
    with open(a, "rb") as fa, open(b, "rb") as fb:
        while len(out) < limit:
            x, y = fa.read(CHUNK), fb.read(CHUNK)
            if not x and not y:
                break
            if x != y:
                n = min(len(x), len(y))
                i = next((k for k in range(n) if x[k] != y[k]), n)
                while i < n and len(out) < limit:
                    j = i
                    while j < n and x[j] != y[j]:
                        j += 1
                    out.append(f"  differ 0x{pos + i:X} .. 0x{pos + j:X}")
                    i = next((k for k in range(j, n) if x[k] != y[k]), n)
                if len(x) != len(y):
                    out.append(f"  length differs at 0x{pos + n:X}")
                    break
            pos += len(x)
    return out or ["  no differences"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", default="build", choices=["build", "compare", "verify"])
    ap.add_argument("image", nargs="?", help="compare: image to check (default build/rom/rebuilt.cci)")
    ap.add_argument("--code")
    ap.add_argument("--parts", default=str(ROOT / "extracted" / "rom"))
    ap.add_argument("--out", default=str(ROOT / "build" / "rom" / "rebuilt.cci"))
    ap.add_argument("--romfs-order", default="manifest", choices=["manifest", "rule"])
    ap.add_argument("--no-compare", action="store_true")
    ap.add_argument("--rom", help="compare: original .cci for a direct byte diff")
    a = ap.parse_args()
    if a.cmd == "verify":
        return verify(Path(a.image or a.out))
    if a.cmd == "compare":
        return compare(Path(a.image or a.out), Path(a.parts), Path(a.rom) if a.rom else None)
    return cmd_build(a)


if __name__ == "__main__":
    sys.exit(main())
