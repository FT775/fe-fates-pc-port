#!/usr/bin/env python3
"""Tests for the .cci rebuild (tools/rom/), for the game in config/game.json. Stdlib only. Needs tools/rom/extract.py output.

Usage:
    python tools/rom/tests.py [all|blz|code|romfs] [--keep]

    blz    BLZ: retail .code decompresses to extracted/code.bin and recompresses
           byte-identically; a mutated code.bin round-trips and is in-place safe.
    code   mutation: flip one byte in .data of code.bin, rebuild; the image must pass
           `rebuild.py verify` (all hashes regenerated), .code must decode to the mutated
           code.bin, and only the expected regions may differ from the original.
    romfs  mutation + shift: in a scratch parts dir (hard links, originals untouched)
           change one byte of a p7 file, grow another p7 file by 0x1234 bytes, and add a
           new file to p0's RomFS root, rebuild with --romfs-order rule; the image must
           pass verify, the new file must read back, and partitions after the change must
           move (NCSD table + card filled size regenerated).
Scratch output: build/rom/test/ (deleted afterwards unless --keep). Each rebuilt image is
2 GiB. Exit 0 iff every test passes.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from gamecfg import GAME  # noqa: E402
import blz  # noqa: E402
import romfs  # noqa: E402
from ctr import parse_ivfc, parse_ncch, parse_ncsd, read_at, u32  # noqa: E402

ROOT = HERE.parent.parent
PARTS = ROOT / "extracted" / "rom"
TEST = ROOT / "build" / "rom" / "test"
REBUILD = [sys.executable, str(HERE / "rebuild.py")]
results: list[tuple[str, bool]] = []


def check(name: str, cond: bool) -> None:
    results.append((name, bool(cond)))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def run(args: list[str]) -> tuple[int, str]:
    p = subprocess.run(REBUILD + args, capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout + p.stderr


def differing_regions(report: str) -> list[str]:
    return [ln.split()[1] for ln in report.splitlines() if ln.startswith(("DIFFER", "MISSING"))]


def test_blz() -> None:
    print("blz:")
    raw = (ROOT / "extracted" / "code.bin").read_bytes()
    comp = (PARTS / "p0" / "exefs" / "code.bin").read_bytes()
    check("retail .code decompresses to extracted/code.bin", blz.decompress(comp) == raw)
    check("retail code.bin recompresses byte-identically", blz.compress(raw) == comp)
    mut = bytearray(raw)
    mut[0x3D0000] ^= 0x5A
    mut[0x10] ^= 0xFF
    c2 = blz.compress(bytes(mut))
    check("mutated code.bin round-trips", blz.decompress(c2) == bytes(mut))
    check("mutated .code is safe for in-place decompression", blz.inplace_margin(c2) >= 0)


def test_code() -> None:
    print("code mutation:")
    TEST.mkdir(parents=True, exist_ok=True)
    raw = bytearray((ROOT / "extracted" / "code.bin").read_bytes())
    # Two bytes inside .data (code.bin offset = vaddr - .text vaddr; config/game.json).
    d0 = GAME.seg("data").vaddr - GAME.seg("text").vaddr
    raw[d0 + 0x100] ^= 0x5A
    raw[d0 + GAME.seg("data").size // 2] ^= 0x5A
    mp = TEST / "code_mut.bin"
    mp.write_bytes(raw)
    img = TEST / "mut_code.cci"
    rc, out = run(["build", "--code", str(mp), "--out", str(img), "--no-compare"])
    check("rebuild with mutated code.bin succeeds", rc == 0)
    rc, out = run(["verify", str(img)])
    check("mutated image passes verify (all hashes regenerated)", rc == 0)
    with open(img, "rb") as fh:
        p0 = parse_ncsd(read_at(fh, 0, 0x200))["partitions"][0]
        n = parse_ncch(read_at(fh, p0["offset"], 0x200))
        eo = p0["offset"] + n["exefs"][0]
        eh = read_at(fh, eo, 0x200)
        off, size = u32(eh, 8), u32(eh, 12)
        code = blz.decompress(read_at(fh, eo + 0x200 + off, size))
    check(".code in the image decodes to the mutated code.bin", code == bytes(raw))
    rc, out = run(["compare", str(img)])
    diff = differing_regions(out)
    allowed = {"p0.ncch_header", "card_info_dev", "p0.exefs.header", "p0.exefs..code",
               "p0.exefs..code+pad"}
    # If .code changed size, everything after it in partition 0's ExeFS moves too.
    shifted = {r for r in diff if r.startswith("p0.exefs.")}
    check(f"only header/ExeFS regions differ ({', '.join(diff)})",
          rc == 1 and set(diff) <= allowed | shifted and "p0.exefs..code" in diff)
    img.unlink(missing_ok=True)


def read_romfs_file(fh, romfs_off: int, path: str) -> bytes | None:
    iv = parse_ivfc(read_at(fh, romfs_off, 0x60))
    l3 = romfs_off + iv["l3_off"]
    data_off = u32(read_at(fh, l3, 0x28), 0x24)
    info = romfs.parse_level3(read_at(fh, l3, data_off))
    for f in info["files"]:
        if f["path"] == path:
            return read_at(fh, l3 + data_off + f["data_off"], f["size"])
    return None


def test_romfs() -> None:
    print("romfs mutation + shift:")
    parts = TEST / "parts"
    if parts.exists():
        shutil.rmtree(parts)
    shutil.copytree(PARTS, parts, copy_function=os.link)  # hard links: no 1 GB copy
    order = json.loads((PARTS / "p7" / "romfs_order.json").read_text(encoding="utf-8"))
    f_mut, f_grow = order["files"][0], order["files"][1]
    for rel, how in ((f_mut, "flip"), (f_grow, "grow")):
        p = parts / "p7" / "romfs" / rel
        data = bytearray(p.read_bytes())
        p.unlink()  # break the hard link before writing
        if how == "flip":
            data[len(data) // 2] ^= 0xFF
        else:
            data += bytes(range(256)) * 0x12 + bytes(0x34)
        p.write_bytes(data)
    new_name = "zz_rom_rebuild_test.bin"
    payload = b"rom rebuild test payload\n" * 100
    (parts / "p0" / "romfs" / new_name).write_bytes(payload)
    img = TEST / "mut_romfs.cci"
    rc, out = run(["build", "--parts", str(parts), "--out", str(img), "--romfs-order", "rule",
                   "--no-compare"])
    check("rebuild with modified RomFS succeeds", rc == 0)
    rc, out = run(["verify", str(img)])
    check("modified image passes verify (IVFC trees + superblock hashes)", rc == 0)
    with open(img, "rb") as fh:
        nc = parse_ncsd(read_at(fh, 0, 0x200))
        p0 = nc["partitions"][0]
        n0 = parse_ncch(read_at(fh, p0["offset"], 0x200))
        got = read_romfs_file(fh, p0["offset"] + n0["romfs"][0], new_name)
        check("new p0 RomFS file reads back", got == payload)
        p7 = nc["partitions"][-1]
        n7 = parse_ncch(read_at(fh, p7["offset"], 0x200))
        got = read_romfs_file(fh, p7["offset"] + n7["romfs"][0], f_grow)
        check("grown p7 file reads back", got == (parts / "p7" / "romfs" / f_grow).read_bytes())
        filled = u32(read_at(fh, 0x300, 4), 0)
        check("card filled size follows the last partition", filled == p7["offset"] + p7["size"])
    man = json.loads((PARTS / "manifest.json").read_text(encoding="utf-8"))
    check("partition 1/7 offsets moved (p0 grew)", p7["offset"] != man["regions"]["p7.ncch_header"]["offset"])
    img.unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    what = next((a for a in argv if not a.startswith("--")), "all")
    keep = "--keep" in argv
    if not (PARTS / "manifest.json").is_file():
        sys.exit("run tools/rom/extract.py first")
    if what in ("all", "blz"):
        test_blz()
    if what in ("all", "code"):
        test_code()
    if what in ("all", "romfs"):
        test_romfs()
    if not keep and TEST.exists():
        shutil.rmtree(TEST)
    bad = [n for n, ok in results if not ok]
    print(f"{len(results) - len(bad)}/{len(results)} checks passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
