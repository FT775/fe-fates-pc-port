#!/usr/bin/env python3
"""Split a decrypted .cci (the game in config/game.json) into the parts tools/rom/rebuild.py
needs. Stdlib only.

Usage:
    python tools/rom/extract.py ["<path to .cci>"] [--out extracted/rom] [--no-romfs]
                                [--link-romfs DIR | --no-link]

The ROM path defaults to "rom_path" in tools/config.local.json if that key exists, else the shared
order of tools/paths.py (FE_ROM, play/config.json "rom" if that file exists, then the .cci in roms/;
for one release also the old repo-root place); otherwise pass it.
The ROM is only read. Partition 0 must carry config/game.json's product code.

--link-romfs (default extracted/romfs, the tree tools/extract_rom.py / tools/assets/romfs.py
wrote): partition 0 RomFS files whose bytes equal that tree are hard-linked instead of
copied (Fates' RomFS is 1.8 GB). Never edit extracted/romfs in place afterwards: a linked
file is the same file in both places. --no-link always copies.

Writes (everything under extracted/, which is gitignored: it holds Nintendo data):
    extracted/rom/ncsd_header.bin      NCSD header (0x200; RSA signature is copied, not made)
    extracted/rom/card_info.bin        card info area 0x200 .. first partition
    extracted/rom/p<N>/ncch_header.bin NCCH header template (signature copied)
    extracted/rom/p<N>/exheader.bin    ExHeader + access descriptor (0x800), if present
    extracted/rom/p<N>/plain.bin       plain region, logo.bin logo region, if present
    extracted/rom/p<N>/exefs/<name>.bin  ExeFS files (code.bin = compressed .code)
    extracted/rom/p<N>/romfs/...       every RomFS file
    extracted/rom/p<N>/romfs_order.json  RomFS dir/file metadata order (file names)
    extracted/rom/manifest.json        layout facts, rule checks, and SHA-256 of every
                                       region of the original image (for compare)

Deterministic: rerunning overwrites the same files with the same bytes. Exit code 1 if
any structural check fails (hash mismatch, non-zero padding, unknown layout).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gamecfg import GAME  # noqa: E402
import blz  # noqa: E402
import romfs  # noqa: E402
from ctr import (CHUNK, MU, align, hash_regions, image_regions, parse_exefs_header,  # noqa: E402
                 parse_ncch, parse_ncsd, read_at, sha256, u32)

ROOT = Path(__file__).resolve().parent.parent.parent
ALIGNS = [1 << k for k in range(9, 21)]  # 0x200 .. 0x100000


def find_align(prev_end: int, off: int) -> int:
    for a in ALIGNS:
        if align(prev_end, a) == off:
            return a
    raise ValueError(f"no power-of-two alignment maps 0x{prev_end:X} to 0x{off:X}")


def default_rom() -> str | None:
    cfg = ROOT / "tools" / "config.local.json"
    if cfg.is_file():
        p = json.loads(cfg.read_text()).get("rom_path")
        if p:
            return p
    import paths  # noqa: E402  (tools/paths.py: roms/ first, then the old root place for one release)
    found = paths.try_resolve_rom(repo=ROOT, notes=None)  # shared order: FE_ROM, play/config.json, roms/, old root
    return str(found) if found else None


def progress(pos: int, total: int, _last=[0.0]) -> None:
    now = time.time()
    if now - _last[0] > 2 or pos == total:
        _last[0] = now
        print(f"\r  hashing {pos * 100 // total:3d}%", end="" if pos != total else "\n", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cci", nargs="?", default=default_rom())
    ap.add_argument("--out", default=str(ROOT / "extracted" / "rom"))
    ap.add_argument("--no-romfs", action="store_true", help="skip writing RomFS files")
    ap.add_argument("--link-romfs", default=str(ROOT / "extracted" / "romfs"),
                    help="hard-link identical partition-0 RomFS files from this tree")
    ap.add_argument("--no-link", action="store_true", help="copy every RomFS file")
    a = ap.parse_args()
    if not a.cci:
        sys.exit("give the .cci path (or set rom_path in tools/config.local.json)")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    t0 = time.time()
    rom = Path(a.cci)
    size = rom.stat().st_size
    with open(rom, "rb") as fh:
        hdr = read_at(fh, 0, 0x200)
        nc = parse_ncsd(hdr)
        parts = nc["partitions"]
        (out / "ncsd_header.bin").write_bytes(hdr)
        card = read_at(fh, 0x200, parts[0]["offset"] - 0x200)
        (out / "card_info.bin").write_bytes(card)
        filled = parts[-1]["offset"] + parts[-1]["size"]
        man: dict = {
            "format": 1,
            "rom": {"size": size},
            "ncsd": {"image_size": nc["image_size"], "first_partition": parts[0]["offset"],
                     "filled_size": filled, "partitions": []},
            "partitions": {},
        }
        if u32(card, 0x300 - 0x200) != filled:
            problems.append("card info filled-size field != end of last partition")
        prev_end = None
        for p in parts:
            if prev_end is not None:
                man["ncsd"]["partitions"].append(
                    {"index": p["index"], "align": find_align(prev_end, p["offset"])})
            else:
                man["ncsd"]["partitions"].append({"index": p["index"], "align": None})
            prev_end = p["offset"] + p["size"]
            base = p["offset"]
            pdir = out / f"p{p['index']}"
            pdir.mkdir(exist_ok=True)
            nh = read_at(fh, base, 0x200)
            n = parse_ncch(nh)
            if not n["nocrypto"]:
                problems.append(f"p{p['index']}: NCCH is encrypted; decrypt the dump first")
                continue
            (pdir / "ncch_header.bin").write_bytes(nh)
            pm: dict = {"product_code": n["product_code"], "aligns": {}, "parts": []}
            if p["index"] == 0 and n["product_code"] != GAME.product_code:
                problems.append(f"p0 product code {n['product_code']!r} is not {GAME.product_code} "
                                f"({GAME.game}, config/game.json)")
            cur = 0x200
            if n["exh_region"][1]:
                exh = read_at(fh, base + 0x200, 0x800)
                (pdir / "exheader.bin").write_bytes(exh)
                if sha256(exh[:n["exh_size"]]) != nh[0x160:0x180]:
                    problems.append(f"p{p['index']}: ExHeader SHA-256 mismatch")
                pm["parts"].append("exheader")
                cur = 0xA00
            # Physical order: Awakening is plain, ExeFS, RomFS (logo inside the ExeFS);
            # Fates has a separate logo region first: logo (0xA00), plain, ExeFS, RomFS.
            # pm["parts"] records it and rebuild.py writes the parts in that order.
            for key in sorted((k for k in ("plain", "logo", "exefs", "romfs") if n[k][1]),
                              key=lambda k: n[k][0]):
                off, sz = n[key]
                pm["aligns"][key] = find_align(cur, off)
                pm["parts"].append(key)
                gap = read_at(fh, base + cur, off - cur)
                if gap.strip(b"\0"):
                    problems.append(f"p{p['index']}: non-zero padding before {key}")
                cur = off + sz
                if key in ("plain", "logo"):
                    (pdir / f"{key}.bin").write_bytes(read_at(fh, base + off, sz))
                elif key == "exefs":
                    eh = read_at(fh, base + off, 0x200)
                    if sha256(eh[:n["exefs_hash_size"]]) != nh[0x1C0:0x1E0]:
                        problems.append(f"p{p['index']}: ExeFS superblock hash mismatch")
                    (pdir / "exefs").mkdir(exist_ok=True)
                    order = []
                    ecur = 0
                    for f in parse_exefs_header(eh):
                        data = read_at(fh, base + off + 0x200 + f["offset"], f["size"])
                        if sha256(data) != f["sha256"]:
                            problems.append(f"p{p['index']}: ExeFS {f['name']} hash mismatch")
                        if f["offset"] != align(ecur, MU) or f["slot"] != len(order):
                            problems.append(f"p{p['index']}: unexpected ExeFS file placement")
                        pad = read_at(fh, base + off + 0x200 + f["offset"] + f["size"],
                                      align(f["size"], MU) - f["size"])
                        if pad.strip(b"\0"):
                            problems.append(f"p{p['index']}: non-zero ExeFS padding after {f['name']}")
                        ecur = f["offset"] + f["size"]
                        order.append(f["name"])
                        (pdir / "exefs" / (f["name"].lstrip(".") + ".bin")).write_bytes(data)
                        if f["name"] == ".code":
                            pm["code_compressed_sha256"] = hashlib.sha256(data).hexdigest()
                    pm["exefs_order"] = order
                    if 0x200 + align(ecur, MU) != sz:
                        problems.append(f"p{p['index']}: ExeFS size is not header + aligned files")
                elif key == "romfs":
                    print(f"p{p['index']}: RomFS at 0x{base + off:X}, size 0x{sz:X}")
                    rdir = pdir / "romfs"
                    if a.no_romfs:
                        from ctr import parse_ivfc
                        iv = parse_ivfc(read_at(fh, base + off, 0x60))
                        l3 = base + off + iv["l3_off"]
                        info = romfs.parse_level3(read_at(fh, l3, u32(read_at(fh, l3, 0x28), 0x24)))
                        info["ivfc"] = iv
                    else:
                        lf = Path(a.link_romfs) if p["index"] == 0 and not a.no_link else None
                        if lf is not None and not lf.is_dir():
                            lf = None
                        info = romfs.extract_romfs(fh, base + off, rdir, lf)
                        if info.get("linked"):
                            print(f"  hard-linked {info['linked']}/{len(info['files'])} files from {lf}")
                    iv = info["ivfc"]
                    bls = {lv["block_log2"] for lv in iv["levels"]}
                    if bls != {12}:
                        problems.append(f"p{p['index']}: IVFC block sizes {bls} (expected 4 KiB)")
                    if iv["end"] != sz:
                        problems.append(f"p{p['index']}: RomFS size 0x{sz:X} != IVFC layout end 0x{iv['end']:X}")
                    rules = romfs.check_rules(info)
                    for k, v in rules.items():
                        if not v and k != "dir_order_matches_rule" and k != "file_order_matches_rule":
                            problems.append(f"p{p['index']}: RomFS rule failed: {k}")
                    pm["romfs"] = {"dirs": len(info["dirs"]), "files": len(info["files"]),
                                   "l3_size": iv["levels"][2]["size"],
                                   "data_bytes": sum(f["size"] for f in info["files"]),
                                   "rules": rules}
                    (pdir / "romfs_order.json").write_text(json.dumps(
                        {"dirs": [d["path"] for d in info["dirs"]],
                         "files": [f["path"] for f in info["files"]]},
                        ensure_ascii=False, indent=0), encoding="utf-8")
            if align(cur, MU) != n["size"]:
                problems.append(f"p{p['index']}: NCCH size 0x{n['size']:X} != content end 0x{cur:X}")
            man["partitions"][str(p["index"])] = pm

        print("hashing every region of the original image ...")
        regions = image_regions(fh, size)
        table, whole256, whole1 = hash_regions(fh, regions, size, progress)
        # Padding expectations: card padding is 0xFF, every other '+pad' is zero.
        for name, off, sz in regions:
            if name.endswith("+pad") or name == "card_padding":
                fill = 0xFF if name == "card_padding" else 0
                if fill == 0 and name == "card_info_dev+pad":
                    fill = 0xFF  # 0x1200 .. first partition is 0xFF on this card
                want = _fill_hash(fill, sz)
                table[name]["fill"] = fill
                if table[name]["sha256"] != want:
                    problems.append(f"region {name} is not all 0x{fill:02X}")
        man["rom"].update({"sha256": whole256, "sha1": whole1})
        man["regions"] = table

    # Does the code BLZ round trip? Recorded so rebuild knows whether reuse is ever needed.
    codep = out / "p0" / "exefs" / "code.bin"
    if codep.is_file():
        comp = codep.read_bytes()
        rawc = blz.decompress(comp)
        man["code_bin_sha1"] = hashlib.sha1(rawc).hexdigest()
        man["blz_reproduces_retail"] = blz.compress(rawc) == comp
        print(f"BLZ recompression of .code byte-identical: {man['blz_reproduces_retail']}")

    man["problems"] = problems
    (out / "manifest.json").write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"whole image: sha256 {man['rom']['sha256']}  sha1 {man['rom']['sha1']}")
    print(f"{len(man['regions'])} regions recorded; {len(problems)} problems; {time.time() - t0:.0f}s")
    for pr in problems:
        print("  PROBLEM:", pr)
    return 1 if problems else 0


def _fill_hash(fill: int, size: int) -> str:
    h = hashlib.sha256()
    block = bytes([fill]) * CHUNK
    while size:
        k = min(size, CHUNK)
        h.update(block[:k])
        size -= k
    return h.hexdigest()


if __name__ == "__main__":
    sys.exit(main())
