#!/usr/bin/env python3
"""CTPK texture packages <-> PNG + JSON, with byte-identical rebuild. Stdlib only.

CTPK layout (little-endian):
    0x00 "CTPK", u16 version, u16 count, u32 texture-data offset, u32 texture-data size,
         u32 hash-table offset, u32 conversion-info offset, 8 bytes zero
    0x20 count x 0x20 entries: u32 name offset, u32 data size, u32 data offset (relative
         to texture data), u32 format, u16 width, u16 height, u8 mip levels, u8 type,
         u16 cube face, u32 mip-size table index (in u32 units), u32 timestamp
    mip-size tables (u32 per level, per entry), names (NUL-terminated, 4-aligned block),
    hash table (u32 crc32(name), u32 index; sorted by hash), conversion info
    (4 bytes per entry), zero padding to the texture data (0x80 aligned); each texture's
    data starts on a 0x80 boundary and the data section is padded to 0x80.

`unpack` writes OUT_DIR/<texture>.png (+ .mipN.png for extra levels) and ctpk.json
(every non-pixel field). `pack` rebuilds the CTPK from them. Non-ETC formats are
regenerated from the PNG bit-exactly. ETC1/ETC1A4 are lossy to re-encode, so unpack also
keeps the original blocks in <texture>.orig.bin plus the SHA-1 of the decoded pixels:
pack reuses the original blocks when the PNG still decodes to the same pixels and only
runs the (simple) ETC1 encoder for edited images.

Usage:
    python tools/assets/ctpk.py unpack IN.ctpk[.lz] OUT_DIR
    python tools/assets/ctpk.py pack OUT_DIR OUT.ctpk [--like ORIGINAL.ctpk.lz]
        --like: compress the result the way ORIGINAL is compressed (if it is LZ)
    python tools/assets/ctpk.py test [--jobs N] [--png]
        every CTPK in extracted/romfs (.ctpk/.ctpk.lz/.tp.lz and members of IS .arc
        archives): parse -> rebuild from fields + re-encoded pixels -> compare.
        --png also routes every texture through PNG encode/decode (slower).
    python tools/assets/ctpk.py exportall [--jobs N]
        PNGs for every CTPK -> extracted/assets/textures/<path>/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import arc  # noqa: E402
import isbin  # noqa: E402
import lz  # noqa: E402
import tex3ds  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
ROMFS = os.path.join(ROOT, "extracted", "romfs")
OUT_TEX = os.path.join(ROOT, "extracted", "assets", "textures")


class CtpkError(ValueError):
    pass


def _align(v: int, a: int) -> int:
    return (v + a - 1) & ~(a - 1)


def parse(d: bytes) -> dict:
    if d[:4] != b"CTPK":
        raise CtpkError("not a CTPK")
    ver, cnt, toff, tsize, hoff, ioff = struct.unpack_from("<HHIIII", d, 4)
    if d[0x18:0x20] != bytes(8):
        raise CtpkError("non-zero header padding")
    texs = []
    for i in range(cnt):
        e = 0x20 + 0x20 * i
        no, size, doff, fmt, w, h, mips, typ, cube, bmi, ts = struct.unpack_from("<IIIIHHBBHII", d, e)
        end = d.index(b"\0", no)
        nmips = struct.unpack_from(f"<{mips}I", d, bmi * 4)
        texs.append({"name": isbin.quote(d[no:end]), "format": fmt, "width": w, "height": h,
                     "mips": mips, "type": typ, "cube": cube, "timestamp": ts,
                     "mip_sizes": list(nmips), "size": size,
                     "conv": d[ioff + 4 * i:ioff + 4 * i + 4].hex(),
                     "_name_off": no, "_doff": doff, "_bmi": bmi})
    hashes = [list(struct.unpack_from("<II", d, hoff + 8 * i)) for i in range(cnt)]
    hdr = {"version": ver, "textures": texs, "hashes": hashes,
           "_toff": toff, "_tsize": tsize, "_hoff": hoff, "_ioff": ioff}
    for t in texs:
        t["_data"] = d[toff + t["_doff"]:toff + t["_doff"] + t["size"]]
    return hdr


def build(hdr: dict, datas: list[bytes]) -> bytes:
    """Lay the CTPK out the way the game's packager does (verified by `test`)."""
    texs = hdr["textures"]
    cnt = len(texs)
    out = bytearray(0x20 + 0x20 * cnt)
    # mip-size tables
    bmi = []
    for t, data in zip(texs, datas):
        bmi.append(len(out) // 4)
        sizes = t["mip_sizes"]
        out += struct.pack(f"<{len(sizes)}I", *sizes)
    # names
    name_offs = []
    names = [isbin.unquote(t["name"]) for t in texs]
    for n in names:
        name_offs.append(len(out))
        out += n + b"\0"
    while len(out) % 4:
        out.append(0)
    hoff = len(out)
    hashes = hdr.get("hashes")
    if hashes is None or len(hashes) != cnt:
        hashes = sorted([zlib.crc32(n) & 0xFFFFFFFF, i] for i, n in enumerate(names))
    for hv, idx in hashes:
        out += struct.pack("<II", hv, idx)
    ioff = len(out)
    for t in texs:
        out += bytes.fromhex(t["conv"])
    toff = _align(len(out), 0x80)
    out += bytes(toff - len(out))
    doffs = []
    for data in datas:
        out += bytes(_align(len(out), 0x80) - len(out))
        doffs.append(len(out) - toff)
        out += data
    out += bytes(_align(len(out), 0x80) - len(out))
    tsize = len(out) - toff
    struct.pack_into("<4sHHIIII", out, 0, b"CTPK", hdr["version"], cnt, toff, tsize, hoff, ioff)
    for i, (t, data) in enumerate(zip(texs, datas)):
        struct.pack_into("<IIIIHHBBHII", out, 0x20 + 0x20 * i, name_offs[i], len(data), doffs[i],
                         t["format"], t["width"], t["height"], t["mips"], t["type"], t["cube"],
                         bmi[i], t["timestamp"])
    return bytes(out)


def mip_dims(t: dict):
    w, h = t["width"], t["height"]
    for _ in range(t["mips"]):
        yield w, h
        w, h = max(8, w // 2), max(8, h // 2)


def split_mips(t: dict, data: bytes) -> list[bytes]:
    out = []
    p = 0
    for w, h in mip_dims(t):
        n = tex3ds.data_size(t["format"], w, h)
        out.append(data[p:p + n])
        p += n
    if p != len(data):
        raise CtpkError(f"texture size {len(data)} != sum of mip levels {p}")
    return out


def _safe(name: str) -> str:
    s = name.strip('"')
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in s) or "tex"


# ----------------------------------------------------------------- unpack / pack
def unpack(d: bytes, out_dir: str, source: str = "") -> int:
    hdr = parse(d)
    os.makedirs(out_dir, exist_ok=True)
    used = set()
    for i, t in enumerate(hdr["textures"]):
        base = _safe(t["name"])
        while base in used:
            base += f"_{i}"
        used.add(base)
        t["file"] = base
        levels = split_mips(t, t.pop("_data"))
        t["pixels_sha1"] = []
        for lvl, ((w, h), raw) in enumerate(zip(mip_dims(t), levels)):
            img = tex3ds.decode(t["format"], w, h, raw)
            t["pixels_sha1"].append(hashlib.sha1(img).hexdigest())
            fn = base + (f".mip{lvl}" if lvl else "") + ".png"
            tex3ds.write_png(os.path.join(out_dir, fn), w, h, img)
        if t["format"] in (12, 13):
            with open(os.path.join(out_dir, base + ".orig.bin"), "wb") as fh:
                fh.write(b"".join(levels))
        for k in [k for k in t if k.startswith("_")]:
            del t[k]
    for k in [k for k in hdr if k.startswith("_")]:
        del hdr[k]
    hdr["source"] = source
    with open(os.path.join(out_dir, "ctpk.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(hdr, fh, indent=1, ensure_ascii=False)
    return len(hdr["textures"])


def pack(in_dir: str) -> bytes:
    with open(os.path.join(in_dir, "ctpk.json"), encoding="utf-8") as fh:
        hdr = json.load(fh)
    datas = []
    for t in hdr["textures"]:
        base = t["file"]
        levels = []
        orig = None
        if t["format"] in (12, 13) and os.path.exists(os.path.join(in_dir, base + ".orig.bin")):
            with open(os.path.join(in_dir, base + ".orig.bin"), "rb") as fh:
                orig = split_mips(t, fh.read())
        for lvl, (w, h) in enumerate(mip_dims(t)):
            fn = os.path.join(in_dir, base + (f".mip{lvl}" if lvl else "") + ".png")
            pw, ph, img = tex3ds.read_png(fn)
            if (pw, ph) != (w, h):
                if lvl:
                    raise CtpkError(f"{fn}: mip size {pw}x{ph}, expected {w}x{h}")
                t["width"], t["height"] = w, h = pw, ph
            if orig is not None and hashlib.sha1(img).hexdigest() == t["pixels_sha1"][lvl]:
                levels.append(orig[lvl])
            else:
                levels.append(tex3ds.encode(t["format"], w, h, img))
        t["mip_sizes"] = [len(x) for x in levels]
        datas.append(b"".join(levels))
    return build(hdr, datas)


# ----------------------------------------------------------------- discovery / test
def iter_ctpks(path: str):
    """Yield (label, ctpk bytes) for a RomFS file: plain/LZ CTPK, or CTPK members of an
    IS .arc archive (members are LZ13-compressed)."""
    try:
        d, _ = isbin.load_maybe_lz(path)
    except lz.LZError:
        return
    if d[:4] == b"CTPK":
        yield "", d
    elif path.lower().endswith((".arc", ".arc.lz")) and arc.is_arc(d):
        for name, member in arc_members(d):
            if member[:4] == b"CTPK":
                yield name, member


def arc_members(d: bytes):
    """(name, decompressed data) for each member of an IS .arc archive."""
    for m in arc.parse(d):
        blob = m["data"]
        if lz.lz_type(blob) is not None:
            try:
                blob = lz.decompress(blob)
            except lz.LZError:
                pass
        yield m["name"].decode("cp932", "replace"), blob


def _test_one(args):
    path, via_png = args
    res = []
    for label, d in iter_ctpks(path):
        try:
            hdr = parse(d)
            datas = []
            etc = raw = 0
            for t in hdr["textures"]:
                levels = split_mips(t, t["_data"])
                new = []
                for (w, h), lv in zip(mip_dims(t), levels):
                    if t["format"] in (12, 13):
                        new.append(lv)  # original blocks kept (lossy format)
                        etc += 1
                        continue
                    img = tex3ds.decode(t["format"], w, h, lv)
                    if via_png:
                        _, _, img = tex3ds.parse_png(tex3ds.png_bytes(w, h, img, 1))
                    new.append(tex3ds.encode(t["format"], w, h, img))
                    raw += 1
                datas.append(b"".join(new))
            ok = build(hdr, datas) == d
            fmts = [t["format"] for t in hdr["textures"]]
            res.append((label, ok, fmts, etc, raw, ""))
        except (CtpkError, ValueError, struct.error) as e:
            res.append((label, False, [], 0, 0, str(e)))
    return path, res


def test(jobs: int, via_png: bool) -> tuple[int, int]:
    from concurrent.futures import ProcessPoolExecutor
    files = []
    for dp, _dn, fn in os.walk(ROMFS):
        for f in fn:
            fl = f.lower()
            if ".ctpk" in fl or fl.endswith((".tp.lz", ".arc", ".arc.lz")):
                files.append(os.path.join(dp, f))
    files.sort()
    n = ok = 0
    fmt_count: dict[int, int] = {}
    etc = raw = 0
    fails = []
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for path, res in ex.map(_test_one, [(f, via_png) for f in files], chunksize=4):
            for label, good, fmts, e, r, err in res:
                n += 1
                ok += good
                etc += e
                raw += r
                for f in fmts:
                    fmt_count[f] = fmt_count.get(f, 0) + 1
                if not good:
                    fails.append(f"{os.path.relpath(path, ROMFS)}:{label}\t{err}")
    fc = ", ".join(f"{tex3ds.FORMAT_NAMES.get(k, k)}={v}" for k, v in sorted(fmt_count.items()))
    print(f"CTPK packages: {ok}/{n} rebuild byte-identically ({100.0 * ok / max(n, 1):.2f}%)"
          f"{' via PNG' if via_png else ''}")
    print(f"   textures: {raw} regenerated from pixels (exact), {etc} ETC1/ETC1A4 kept as "
          f"original blocks; formats: {fc}")
    os.makedirs(os.path.join(ROOT, "extracted", "assets"), exist_ok=True)
    with open(os.path.join(ROOT, "extracted", "assets", "ctpk_fail.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(fails) + "\n")
    return ok, n


def _export_one(path: str) -> int:
    rel = os.path.relpath(path, ROMFS)
    k = 0
    for label, d in iter_ctpks(path):
        out = os.path.join(OUT_TEX, rel + (("/" + _safe(label)) if label else ""))
        try:
            k += unpack(d, out, rel + (":" + label if label else ""))
        except (CtpkError, ValueError):
            pass
    return k


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("unpack", "pack", "test", "exportall"))
    ap.add_argument("inp", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--like", help="pack: compress like this original file")
    ap.add_argument("--png", action="store_true")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    if a.cmd == "test":
        ok, n = test(a.jobs, a.png)
        return 0 if ok == n else 1
    if a.cmd == "exportall":
        from concurrent.futures import ProcessPoolExecutor
        files = []
        for dp, _dn, fn in os.walk(ROMFS):
            for f in fn:
                fl = f.lower()
                if ".ctpk" in fl or fl.endswith((".tp.lz", ".arc", ".arc.lz")):
                    files.append(os.path.join(dp, f))
        with ProcessPoolExecutor(max_workers=a.jobs) as ex:
            total = sum(ex.map(_export_one, sorted(files), chunksize=4))
        print(f"exported {total} textures to {OUT_TEX}")
        return 0
    if not (a.inp and a.out):
        ap.error("need IN and OUT")
    if a.cmd == "unpack":
        d, _ = isbin.load_maybe_lz(a.inp)
        print(f"{unpack(d, a.out, os.path.basename(a.inp))} textures")
    else:
        out = pack(a.inp)
        if a.like:
            with open(a.like, "rb") as fh:
                out = lz.compress_like(out, fh.read())
        with open(a.out, "wb") as fh:
            fh.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
