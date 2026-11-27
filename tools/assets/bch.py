#!/usr/bin/env python3
"""BCH (NintendoWare "H3D" resource, Fates' model/texture container) <-> PNG textures.

Standard library only (PNG and PICA codecs from tex3ds.py, LZ from lz.py).

Fates stores portraits, UI art, unit, battle and field models as BCH: 10,752 *.bch(.lz)
files in the RomFS plus the 3,205 BCH members of .arc files (3,036 portrait
expressions in face/face/*.arc, 169 effect models). This tool reads the
container, lists its sections and resources, exports every texture to PNG, and re-injects
edited PNGs of the same size and format IN PLACE: no offset, size or relocation changes, so
the file keeps its length and every pointer stays valid. An unedited rebuild is
byte-identical (also after LZ recompression). A PNG of another size (or a format / mip
count edited in bch.json) goes through the relocating writer in bchwrite.py when asked
(--allow-resize); it rebuilds the file around the new size and refuses unsafe edits.

Wrappers seen on disk (unwrap()/rewrap()):
    LZ13 (13 ss ss ss + LZ11 stream)      10,713 files
    "stored": 00 ss ss ss + raw bytes         30 files (field/*_t.bch.lz). The game's
              Compress::Uncompress (0x126A08) copies the payload when bit 4 of the type
              byte is clear, so type 0x00 means "not compressed".
    none (plain "BCH\\0")                       9 files

Container facts (versions 0x21/0x22, all Fates files; checked against the game's own
loader nw::h3d::res::ResourceBinary::TryInit at 0x3233F4, and against the community
format notes (SPICA / Ohana3DS docs, read for facts only, no code taken)):
    0x00 "BCH\\0", u8 backward version, u8 forward version, u16 converter version
    0x08 u32 offsets: contents, strings, gpu commands, data, data-extended (if backward
         > 0x20), relocation table
         u32 lengths of the same six sections, then uninitialized data length and
         uninitialized description length; then (backward > 7) u16 flags,
         u16 address count. The file is stored UNRELOCATED: pointers are offsets into
         their own section and the loader adds the section base.
    contents: 15 x { u32 pointer-table offset, u32 entry count, u32 name dictionary }
         for models, materials, shaders, textures, LUTs, lights, cameras, fogs, skeletal,
         material, visibility, light, camera, fog animations, scenes (all offsets
         relative to contents). The pointer table holds contents-relative entry offsets.
    texture entry (contents): 3 x { u32 GPU command offset, u32 word count } for texture
         units 0..2 (the same texture set up for each unit), u32 ?, u32 name (strings).
         Unit 0's PICA commands give 0x82 TEXUNIT0_DIM (height | width << 16), 0x84 LOD
         (max mip level in bits 16-19), 0x85 address, 0x8E format (tex3ds numbering).
    relocation entry u32: bits 0-24 offset (words, bytes for kind 1), bits 25-28 kind,
         bits 29-31 target section (0 contents, 1 strings, 2 gpu, 3 data, 4 data-ext).
         The patched word gets the base of: kind 0 contents, 1 strings, 2-3 gpu,
         4-8 data, 9-13 data-extended; kinds 5/10 store the GPU address >> 3 (texture
         and vertex addresses), 6-8/11-13 physical-address-relative forms.
         Texture addresses are relocated with kind 5 (data) or 10 (data-extended).

Pixel rows: as in Awakening's CTPK/CGFX art, the first tile row in memory is the TOP of
the picture (checked visually: portraits come out upright with no flip, upside down with
one). FLIP_Y below exists only for experiments.

Usage:
    python tools/assets/bch.py info IN.bch[.lz]
        sections, resource counts, textures (name, size, format, mips, offset)
    python tools/assets/bch.py export IN.bch[.lz] OUT_DIR
        OUT_DIR/<index>_<name>.png per texture + bch.json (what pack needs)
    python tools/assets/bch.py pack OUT_DIR ORIGINAL.bch[.lz] OUT.bch[.lz] [--allow-resize]
        re-inject every PNG in OUT_DIR; OUT is wrapped like ORIGINAL (LZ13 / stored /
        plain). Unchanged PNGs keep the original bytes exactly. Without --allow-resize a
        PNG must keep its width/height (and bch.json its format and mips); with it, sizes
        that are powers of two from 8 to 1024, other mip counts and formats of the same
        family are accepted (bchwrite.py).
    python tools/assets/bch.py selftest
        edit round trip: changes a 16x16 block in a non-ETC texture with mips, an ETC1A4
        texture and a "stored" file, packs, reads back (pixels, length, other bytes);
        then a portrait PNG doubled and halved through --allow-resize, and the refusals
        (resize without the flag, a non-power-of-two PNG)
    python tools/assets/bch.py test [--jobs N] [--lz] [--limit N]
        every *.bch(.lz) in extracted/romfs and every BCH member of an .arc: parse,
        decode every texture, PNG round trip,
        re-encode, re-inject, compare. --lz also recompresses (slow). Report:
        extracted/assets/bch_report.txt, failures extracted/assets/bch_fail.txt
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lz  # noqa: E402
import tex3ds  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
ROMFS = os.path.join(ROOT, "extracted", "romfs")
REPORT_DIR = os.path.join(ROOT, "extracted", "assets")

SECTIONS = ("contents", "strings", "gpu", "data", "data_ext", "reloc")
CONTENT_KINDS = ("models", "materials", "shaders", "textures", "luts", "lights", "cameras",
                 "fogs", "skeletal_anims", "material_anims", "visibility_anims",
                 "light_anims", "camera_anims", "fog_anims", "scenes")
RELOC_TARGET = {0: "contents", 1: "strings", 2: "gpu", 3: "data", 4: "data_ext"}


def kind_base(kind: int) -> str | None:
    if kind == 0:
        return "contents"
    if kind == 1:
        return "strings"
    if kind in (2, 3):
        return "gpu"
    if 4 <= kind <= 8:
        return "data"
    if 9 <= kind <= 13:
        return "data_ext"
    return None


class BchError(ValueError):
    pass


# ------------------------------------------------------------------ wrappers
def unwrap(raw: bytes) -> tuple[bytes, str]:
    """(BCH bytes, wrapper) where wrapper is 'lz', 'stored' or 'none'."""
    if raw[:4] == b"BCH\0":
        return raw, "none"
    if len(raw) >= 8 and raw[0] == 0 and raw[4:8] == b"BCH\0":
        n = raw[1] | raw[2] << 8 | raw[3] << 16
        if n != len(raw) - 4:
            raise BchError(f"stored wrapper size {n} != payload {len(raw) - 4}")
        return raw[4:], "stored"
    if lz.lz_type(raw) is not None:
        d = lz.decompress(raw)
        if d[:4] != b"BCH\0":
            raise BchError("LZ payload is not BCH")
        return d, "lz"
    raise BchError(f"not a BCH (starts {raw[:8].hex()})")


def rewrap(d: bytes, wrapper: str, orig: bytes | None = None) -> bytes:
    if wrapper == "none":
        return d
    if wrapper == "stored":
        return bytes((0, len(d) & 255, len(d) >> 8 & 255, len(d) >> 16 & 255)) + d
    if wrapper == "lz":
        if orig is not None:
            return lz.compress_like(d, orig)
        return lz.compress(d, 0x13)
    raise BchError(f"unknown wrapper {wrapper}")


# ------------------------------------------------------------------ PICA commands
def pica_commands(words: list[int]) -> list[tuple[int, int, int]]:
    """[(register, value, word index of the value)] from a PICA200 command list.
    Each command: param0, header (id 0-15, byte mask 16-19, extra count 20-27,
    consecutive bit 31), extra params, padded to an even word count."""
    out = []
    i = 0
    n = len(words)
    while i + 1 < n:
        p0, hdr = words[i], words[i + 1]
        reg, extra, consec = hdr & 0xFFFF, (hdr >> 20) & 0xFF, hdr >> 31
        out.append((reg, p0, i))
        j = i + 2
        for k in range(extra):
            if j >= n:
                break
            out.append((reg + (k + 1 if consec else 0), words[j], j))
            j += 1
        i = j + ((2 + extra) & 1)
    return out


# ------------------------------------------------------------------ parse
class Bch:
    def __init__(self, d: bytes):
        self.d = d
        if d[:4] != b"BCH\0":
            raise BchError("missing BCH magic")
        self.back, self.fwd, self.conv = struct.unpack_from("<BBH", d, 4)
        names = ["contents", "strings", "gpu", "data"] + (["data_ext"] if self.back > 0x20 else []) + ["reloc"]
        k = len(names)
        offs = struct.unpack_from(f"<{k}I", d, 8)
        lens = struct.unpack_from(f"<{k}I", d, 8 + 4 * k)
        self.sec = {n: (o, ln) for n, o, ln in zip(names, offs, lens)}
        self.sec.setdefault("data_ext", (0, 0))
        p = 8 + 8 * k
        self.uninit_data, self.uninit_desc = struct.unpack_from("<2I", d, p)
        p += 8
        self.flags = self.addr_count = 0
        if self.back > 7:
            self.flags, self.addr_count = struct.unpack_from("<2H", d, p)
        for n, (o, ln) in self.sec.items():
            if ln and o + ln > len(d):
                raise BchError(f"section {n} 0x{o:X}+0x{ln:X} past end 0x{len(d):X}")
        ro, rl = self.sec["reloc"]
        self.relocs = []  # (target section, kind, absolute file offset of the patched word)
        for i in range(rl // 4):
            v = struct.unpack_from("<I", d, ro + 4 * i)[0]
            off, kind, tgt = v & 0x1FFFFFF, (v >> 25) & 0xF, v >> 29
            tname = RELOC_TARGET.get(tgt)
            if tname is None:
                raise BchError(f"relocation target {tgt} unknown")
            pos = self.sec[tname][0] + (off if kind == 1 else off * 4)
            self.relocs.append((tname, kind, pos))
        self.reloc_at = {pos: (t, k) for t, k, pos in self.relocs}
        co = self.sec["contents"][0]
        self.content = {}
        for i, name in enumerate(CONTENT_KINDS):
            ptab, cnt, dic = struct.unpack_from("<3I", d, co + 12 * i)
            self.content[name] = (ptab, cnt, dic)
        self._tex = None

    def u32(self, o: int) -> int:
        return struct.unpack_from("<I", self.d, o)[0]

    def string(self, off: int) -> bytes:
        so = self.sec["strings"][0] + off
        e = self.d.index(b"\0", so)
        return self.d[so:e]

    def entries(self, kind: str) -> list[int]:
        """Absolute file offsets of the entries of one content kind."""
        co = self.sec["contents"][0]
        ptab, cnt, _ = self.content[kind]
        return [co + self.u32(co + ptab + 4 * i) for i in range(cnt)]

    def textures(self) -> list[dict]:
        if self._tex is not None:
            return self._tex
        out = []
        go = self.sec["gpu"][0]
        for idx, e in enumerate(self.entries("textures")):
            cmd_off, nwords = struct.unpack_from("<2I", self.d, e)
            name = self.string(self.u32(e + 0x1C))
            base = go + cmd_off
            words = list(struct.unpack_from(f"<{nwords}I", self.d, base))
            regs, where = {}, {}
            for reg, val, wi in pica_commands(words):
                regs.setdefault(reg, val)
                where.setdefault(reg, base + 4 * wi)
            if 0x82 not in regs or 0x85 not in regs or 0x8E not in regs:
                raise BchError(f"texture {name!r}: unit 0 commands lack dim/address/format")
            h, w = regs[0x82] & 0x7FF, (regs[0x82] >> 16) & 0x7FF
            fmt = regs[0x8E] & 0xF
            mips = ((regs.get(0x84, 0) >> 16) & 0xF) + 1
            rel = self.reloc_at.get(where[0x85])
            if rel is None:
                raise BchError(f"texture {name!r}: address word has no relocation")
            sec = kind_base(rel[1])
            if sec not in ("data", "data_ext"):
                raise BchError(f"texture {name!r}: address relocated to {sec}")
            off = self.sec[sec][0] + regs[0x85]
            dims = [(max(w >> i, 8), max(h >> i, 8)) for i in range(mips)]
            size = sum(tex3ds.data_size(fmt, a, b) for a, b in dims)
            if off + size > len(self.d):
                raise BchError(f"texture {name!r} data past end of file")
            out.append({"index": idx, "name": name, "width": w, "height": h, "format": fmt,
                        "mips": mips, "dims": dims, "offset": off, "size": size,
                        "section": sec, "reloc_kind": rel[1]})
        self._tex = out
        return out

    def levels(self, t: dict) -> list[bytes]:
        out = []
        pos = t["offset"]
        for a, b in t["dims"]:
            n = tex3ds.data_size(t["format"], a, b)
            out.append(self.d[pos:pos + n])
            pos += n
        return out

    def summary(self) -> dict:
        return {"version": f"0x{self.back:02X}/0x{self.fwd:02X}/{self.conv}",
                "sections": {k: [v[0], v[1]] for k, v in self.sec.items()},
                "counts": {k: v[1] for k, v in self.content.items() if v[1]},
                "relocations": len(self.relocs)}


# ------------------------------------------------------------------ pixels
FLIP_Y = False  # True would treat the first stored tile row as the bottom (see module doc)


def flip_rows(rgba: bytes, w: int, h: int) -> bytes:
    if not FLIP_Y:
        return rgba
    s = w * 4
    return b"".join(rgba[y * s:(y + 1) * s] for y in range(h - 1, -1, -1))


def decode_level(fmt: int, w: int, h: int, data: bytes) -> bytes:
    """Upright RGBA8 for one stored level."""
    return flip_rows(tex3ds.decode(fmt, w, h, data), w, h)


def encode_level(fmt: int, w: int, h: int, rgba: bytes) -> bytes:
    return tex3ds.encode(fmt, w, h, flip_rows(rgba, w, h))


def downscale(rgba: bytes, w: int, h: int) -> bytes:
    """2x2 box filter (alpha-weighted colour), used to rebuild mips of an edited image."""
    nw, nh = max(w // 2, 1), max(h // 2, 1)
    out = bytearray(nw * nh * 4)
    for y in range(nh):
        for x in range(nw):
            acc = [0, 0, 0, 0]
            for dy in (0, 1):
                for dx in (0, 1):
                    p = ((2 * y + dy) * w + 2 * x + dx) * 4
                    a = rgba[p + 3]
                    acc[0] += rgba[p] * a
                    acc[1] += rgba[p + 1] * a
                    acc[2] += rgba[p + 2] * a
                    acc[3] += a
            q = (y * nw + x) * 4
            if acc[3]:
                out[q:q + 3] = bytes(min(255, (c + acc[3] // 2) // acc[3]) for c in acc[:3])
            out[q + 3] = (acc[3] + 2) // 4
    return bytes(out)


def encode_texture(t: dict, rgba: bytes, orig_levels: list[bytes] | None) -> bytes:
    """Bytes for all mip levels of texture `t` from an upright RGBA8 level 0. If the image
    equals the original's decoded level 0, the original bytes are kept (ETC is lossy and
    hand-made mips are preserved)."""
    fmt, (w, h) = t["format"], t["dims"][0]
    if orig_levels is not None and decode_level(fmt, w, h, orig_levels[0]) == rgba:
        return b"".join(orig_levels)
    out = []
    img, cw, ch = rgba, w, h
    for i, (a, b) in enumerate(t["dims"]):
        if i:
            while cw > a or ch > b:
                img = downscale(img, cw, ch)
                cw, ch = max(cw // 2, 1), max(ch // 2, 1)
        out.append(encode_level(fmt, a, b, img))
    return b"".join(out)


def inject(d: bytes, replacements: dict[int, bytes]) -> bytes:
    """Write texture data (index -> bytes of all levels) in place. Refuses any write that
    would change length or overlap a relocated word."""
    b = Bch(d)
    texs = b.textures()
    out = bytearray(d)
    rpos = sorted(b.reloc_at)
    import bisect
    for idx, data in replacements.items():
        t = texs[idx]
        if len(data) != t["size"]:
            raise BchError(f"texture {t['name']!r}: new data 0x{len(data):X} bytes, need 0x{t['size']:X}")
        i = bisect.bisect_left(rpos, t["offset"] - 3)
        if i < len(rpos) and rpos[i] < t["offset"] + t["size"]:
            raise BchError(f"texture {t['name']!r} overlaps a relocated word")
        out[t["offset"]:t["offset"] + t["size"]] = data
    return bytes(out)


# ------------------------------------------------------------------ files
def _safe(name: bytes) -> str:
    s = name.decode("cp932", "replace")
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in s) or "tex"


def export(raw: bytes, out_dir: str) -> list[str]:
    d, wrapper = unwrap(raw)
    b = Bch(d)
    os.makedirs(out_dir, exist_ok=True)
    meta = {"wrapper": wrapper, "bch_sha1": hashlib.sha1(d).hexdigest(), "textures": []}
    files = []
    for t in b.textures():
        w, h = t["dims"][0]
        rgba = decode_level(t["format"], w, h, b.levels(t)[0])
        fn = f"{t['index']:02d}_{_safe(t['name'])}.png"
        tex3ds.write_png(os.path.join(out_dir, fn), w, h, rgba)
        files.append(fn)
        meta["textures"].append({"index": t["index"], "name": t["name"].decode("cp932", "replace"),
                                 "file": fn, "width": w, "height": h,
                                 "format": tex3ds.FORMAT_NAMES.get(t["format"], t["format"]),
                                 "mips": t["mips"],
                                 "png_sha1": hashlib.sha1(rgba).hexdigest()})
    with open(os.path.join(out_dir, "bch.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(meta, fh, indent=1, ensure_ascii=False)
    return files


FORMAT_IDS = {v: k for k, v in tex3ds.FORMAT_NAMES.items()}


def _meta_format(m: dict, t: dict, where: str) -> int:
    f = m.get("format", t["format"])
    if isinstance(f, int):
        return f
    if f in FORMAT_IDS:
        return FORMAT_IDS[f]
    raise BchError(f"{where}: unknown format {f!r} in bch.json (use one of "
                   + ", ".join(tex3ds.FORMAT_NAMES.values()) + ")")


def pack(in_dir: str, orig_raw: bytes, allow_resize: bool = False) -> tuple[bytes, list[str]]:
    """Re-inject PNGs from an export folder into the original BCH. Returns (new file bytes
    wrapped like the original, names of textures that changed).

    Same width / height / format / mips as the original: written in place (file length
    unchanged). A PNG of another size, or a "format" / "mips" value edited in bch.json,
    needs allow_resize=True and goes through the relocating writer (bchwrite.py), which
    refuses unsafe edits with a plain message."""
    meta_path = os.path.join(in_dir, "bch.json")
    if not os.path.exists(meta_path):
        raise BchError(f"{in_dir}: no bch.json (make the folder with `bch.py export`)")
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    d, wrapper = unwrap(orig_raw)
    b = Bch(d)
    texs = b.textures()
    rep, changed, moves = {}, [], {}
    for m in meta["textures"]:
        if not 0 <= m["index"] < len(texs):
            raise BchError(f"{m['file']}: bch.json names texture {m['index']}, the file has {len(texs)}")
        t = texs[m["index"]]
        p = os.path.join(in_dir, m["file"])
        if not os.path.exists(p):
            continue
        try:
            w, h, rgba = tex3ds.read_png(p)
        except (ValueError, KeyError, OSError) as e:
            raise BchError(f"{m['file']}: cannot read this PNG ({e}); save it as an 8-bit RGB/RGBA PNG")
        fmt = _meta_format(m, t, m["file"])
        mips = int(m.get("mips", t["mips"]))
        if (w, h) == t["dims"][0] and fmt == t["format"] and mips == t["mips"]:
            new = encode_texture(t, rgba, b.levels(t))
            if new != d[t["offset"]:t["offset"] + t["size"]]:
                rep[t["index"]] = new
                changed.append(m["file"])
            continue
        if not allow_resize:
            what = []
            if (w, h) != t["dims"][0]:
                what.append(f"the PNG is {w}x{h}, the texture is {t['width']}x{t['height']}")
            if fmt != t["format"]:
                what.append(f"bch.json asks for {tex3ds.FORMAT_NAMES.get(fmt, fmt)}, the texture is "
                            f"{tex3ds.FORMAT_NAMES[t['format']]}")
            if mips != t["mips"]:
                what.append(f"bch.json asks for {mips} mip levels, the texture has {t['mips']}")
            raise BchError(f"{m['file']}: " + "; ".join(what) + ". Keep the original size, or allow "
                           "a resize (--allow-resize) to rebuild the file around the new size")
        import bchwrite
        if not (bchwrite._pow2(w) and bchwrite._pow2(h)) or not (8 <= w <= 1024 and 8 <= h <= 1024):
            raise BchError(f"{m['file']}: {w}x{h} - both sides must be powers of two between 8 and "
                           "1024 (8, 16, 32, 64, 128, 256, 512, 1024); the 3DS GPU cannot use other sizes")
        if fmt not in tex3ds.FORMAT_NAMES:
            raise BchError(f"{m['file']}: unknown format {fmt}")
        if mips == t["mips"]:  # not edited: keep the original count where the size allows it
            mips = min(mips, bchwrite.max_mips(w, h))
        if not 1 <= mips <= bchwrite.max_mips(w, h):
            raise BchError(f"{m['file']}: {mips} mip levels; {w}x{h} allows 1..{bchwrite.max_mips(w, h)}")
        data = bchwrite.encode_levels(fmt, w, h, mips, rgba)
        moves[t["index"]] = bchwrite.TexEdit(w, h, fmt, mips, data)
        changed.append(m["file"])
    nd = inject(d, rep) if rep else d
    if moves:
        import bchwrite
        nd = bchwrite.write(nd, moves)
    if nd == d:
        return orig_raw, changed
    return rewrap(nd, wrapper, None), changed


# ------------------------------------------------------------------ test
def bch_files(root: str = ROMFS) -> list[str]:
    """Every *.bch(.lz) file plus every .arc(.lz) (whose BCH members are tested too)."""
    out = []
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            fl = f.lower()
            if ".bch" in fl or fl.endswith((".arc", ".arc.lz")):
                out.append(os.path.join(dp, f))
    return sorted(out)


def roundtrip_bytes(d: bytes) -> tuple[bytes, int, dict]:
    """Rebuild BCH bytes through PNG: decode every texture, PNG encode/parse, re-encode,
    re-inject. Returns (rebuilt bytes, textures, format counts)."""
    b = Bch(d)
    rep = {}
    fmts: dict = {}
    for t in b.textures():
        lv = b.levels(t)
        w, h = t["dims"][0]
        img = decode_level(t["format"], w, h, lv[0])
        _, _, img2 = tex3ds.parse_png(tex3ds.png_bytes(w, h, img, 1))
        if t["format"] in (12, 13):
            new = encode_texture(t, img2, lv)  # keeps the original blocks (unchanged)
        else:
            # Non-ETC: force a real re-encode of every level (no shortcut), so the test
            # proves the codec is exact on this data.
            new = b"".join(encode_level(t["format"], a, c, decode_level(t["format"], a, c, x))
                           for (a, c), x in zip(t["dims"], lv))
            if encode_level(t["format"], w, h, img2) != lv[0]:
                new = b""
        rep[t["index"]] = new
        k = tex3ds.FORMAT_NAMES.get(t["format"], str(t["format"]))
        fmts[k] = fmts.get(k, 0) + 1
    bad = [i for i, v in rep.items() if len(v) != b.textures()[i]["size"]]
    if bad:
        raise BchError(f"texture {bad[0]} did not re-encode exactly")
    return inject(d, rep), len(rep), fmts


def _test_blob(rel: str, raw: bytes, do_lz: bool) -> dict:
    r = {"rel": rel, "parse": False, "tex": 0, "ok": False, "lz": None, "wrapper": "",
         "fmts": {}, "err": "", "counts": {}}
    try:
        d, r["wrapper"] = unwrap(raw)
        b = Bch(d)
        b.textures()
        r["parse"] = True
        r["counts"] = {k: v[1] for k, v in b.content.items() if v[1]}
        new, r["tex"], r["fmts"] = roundtrip_bytes(d)
        r["ok"] = new == d
        if do_lz:
            r["lz"] = rewrap(new, r["wrapper"], raw) == raw
    except Exception as e:  # report, never hide
        r["err"] = f"{type(e).__name__}: {e}"
    return r


def _test_one(args) -> list[dict]:
    path, do_lz = args
    rel = os.path.relpath(path, ROMFS).replace(os.sep, "/")
    with open(path, "rb") as fh:
        raw = fh.read()
    if ".bch" in rel.lower():
        r = _test_blob(rel, raw, do_lz)
        r["member"] = False
        return [r]
    import arc
    import isbin
    out = []
    d, _ = isbin.load_maybe_lz(path)
    for m in arc.parse(d):
        if b".bch" in m["name"].lower():
            r = _test_blob(f"{rel}:{m['name'].decode('cp932', 'replace')}", m["data"], do_lz)
            r["member"] = True
            out.append(r)
    return out


def test(jobs: int, do_lz: bool = False, limit: int = 0, files: list[str] | None = None):
    from concurrent.futures import ProcessPoolExecutor
    files = files if files is not None else bch_files()
    if limit:
        files = files[:limit]
    files.sort(key=lambda p: -os.path.getsize(p))
    n = nmem = parsed = ok = tex = lzok = lzn = 0
    wr: dict = {}
    fmts: dict = {}
    counts: dict = {}
    fails = []
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for r in (x for rs in ex.map(_test_one, [(f, do_lz) for f in files], chunksize=4) for x in rs):
            n += 1
            nmem += r["member"]
            parsed += r["parse"]
            ok += r["ok"]
            tex += r["tex"] if r["ok"] else 0
            wr[r["wrapper"]] = wr.get(r["wrapper"], 0) + 1
            for k, v in r["fmts"].items():
                fmts[k] = fmts.get(k, 0) + v
            for k, v in r["counts"].items():
                counts[k] = counts.get(k, 0) + v
            if r["lz"] is not None:
                lzn += 1
                lzok += r["lz"]
            if not r["ok"] or r["lz"] is False:
                fails.append(f"{r['rel']}\t{r['err'] or 'mismatch'}")
    lines = [f"BCH files: {n} ({n - nmem} RomFS files + {nmem} .arc members); wrappers " + ", ".join(f"{k or '?'}={v}" for k, v in sorted(wr.items())),
             f"  parse (header, relocations, textures): {parsed}/{n}",
             f"  textures exported and re-injected byte-identically: {tex} in {ok}/{n} files",
             "  texture formats: " + ", ".join(f"{k}={v}" for k, v in sorted(fmts.items(), key=lambda x: -x[1])),
             "  resources: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x: -x[1]))]
    if do_lz:
        lines.append(f"  rewrapped (LZ13 recompress / stored / plain) identical to the file: {lzok}/{lzn}")
    text = "\n".join(lines)
    print(text)
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(os.path.join(REPORT_DIR, "bch_report.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + "\n")
    with open(os.path.join(REPORT_DIR, "bch_fail.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(fails) + "\n")
    return ok, n, parsed, tex, (lzok, lzn)


def edit_selftest() -> int:
    """Edit textures through the export/pack folder and read them back:
    a non-ETC texture with mips (exact pixels, mips rebuilt), an ETC1A4 texture (lossy,
    colour must survive), and a "stored"-wrapper file (wrapper kept). Every edited file
    must keep its length, parse, and leave the other textures untouched."""
    import shutil
    tmp = os.path.join(ROOT, "build", "assets", "bch_selftest")
    want = {"nonetc_mips": None, "etc": None, "stored": None}
    for path in bch_files():
        if ".bch" not in path.lower() or all(want.values()):
            continue
        with open(path, "rb") as fh:
            raw = fh.read()
        d, wr = unwrap(raw)
        texs = Bch(d).textures()
        if wr == "stored" and texs and not want["stored"]:
            want["stored"] = (path, 0)
        for t in texs:
            if t["format"] not in (12, 13) and t["mips"] > 1 and not want["nonetc_mips"] and wr == "lz":
                want["nonetc_mips"] = (path, t["index"])
            if t["format"] == 13 and not want["etc"] and wr == "lz" and t["width"] >= 64:
                want["etc"] = (path, t["index"])
    bad = 0
    for label, item in want.items():
        if item is None:
            print(f"  SKIP {label}: no such texture")
            continue
        path, idx = item
        shutil.rmtree(tmp, ignore_errors=True)
        with open(path, "rb") as fh:
            raw = fh.read()
        export(raw, tmp)
        meta = json.load(open(os.path.join(tmp, "bch.json"), encoding="utf-8"))
        m = meta["textures"][idx]
        png = os.path.join(tmp, m["file"])
        w, h, rgba = tex3ds.read_png(png)
        img = bytearray(rgba)
        for y in range(min(h, 16)):
            for x in range(min(w, 16)):
                img[(y * w + x) * 4:(y * w + x) * 4 + 4] = b"\xff\x00\xff\xff"
        tex3ds.write_png(png, w, h, bytes(img))
        new, changed = pack(tmp, raw)
        d0, wr0 = unwrap(raw)
        d1, wr1 = unwrap(new)
        b0, b1 = Bch(d0), Bch(d1)
        t1 = b1.textures()[idx]
        back = decode_level(t1["format"], w, h, b1.levels(t1)[0])
        px = back[(4 * w + 4) * 4:(4 * w + 4) * 4 + 4]
        ok = len(d1) == len(d0) and wr1 == wr0 and changed == [m["file"]]
        if t1["format"] in (12, 13):
            ok &= px[0] > 200 and px[1] < 60 and px[2] > 200
        else:
            ok &= back == decode_level(t1["format"], w, h, encode_level(t1["format"], w, h, bytes(img)))
        others = [t for t in b0.textures() if t["index"] != idx]
        ok &= all(b0.levels(t) == b1.levels(t) for t in others)
        # bytes outside the edited texture are untouched
        ok &= d0[:t1["offset"]] == d1[:t1["offset"]] and \
            d0[t1["offset"] + t1["size"]:] == d1[t1["offset"] + t1["size"]:]
        print(f"  {'PASS' if ok else 'FAIL'} {label}: {os.path.relpath(path, ROMFS)} texture {idx} "
              f"({tex3ds.FORMAT_NAMES.get(t1['format'])}, {w}x{h}, mips {t1['mips']}, wrapper {wr1})")
        bad += not ok
    bad += resize_selftest(tmp)
    shutil.rmtree(tmp, ignore_errors=True)
    return bad


def _upscale2(rgba: bytes, w: int, h: int) -> bytes:
    """Nearest-neighbour 2x (test helper)."""
    out = bytearray()
    s = w * 4
    for y in range(h):
        row = b"".join(rgba[y * s + x * 4:y * s + x * 4 + 4] * 2 for x in range(w))
        out += row + row
    return bytes(out)


def resize_selftest(tmp: str) -> int:
    """Through the export folder: a portrait expression PNG doubled and halved with
    allow_resize (re-parse, size, pixels close to the source, other bytes untouched),
    and the refusals: a resize without the flag, a non-power-of-two PNG."""
    import shutil
    import arc
    import isbin
    face = os.path.join(ROMFS, "face", "face")
    arcs = sorted(f for f in os.listdir(face) if f.endswith("_st.arc")) if os.path.isdir(face) else []
    if not arcs:
        print("  SKIP resize: no face/face/*_st.arc")
        return 0
    dd, _ = isbin.load_maybe_lz(os.path.join(face, arcs[0]))
    raw = next(m["data"] for m in arc.parse(dd) if b".bch" in m["name"].lower())
    bad = 0
    for label, scale in (("doubled", 2), ("halved", 0)):
        shutil.rmtree(tmp, ignore_errors=True)
        export(raw, tmp)
        meta = json.load(open(os.path.join(tmp, "bch.json"), encoding="utf-8"))
        png = os.path.join(tmp, meta["textures"][0]["file"])
        w, h, rgba = tex3ds.read_png(png)
        if scale == 2:
            nw, nh, img = w * 2, h * 2, _upscale2(rgba, w, h)
        else:
            nw, nh, img = w // 2, h // 2, downscale(rgba, w, h)
        tex3ds.write_png(png, nw, nh, img)
        try:
            pack(tmp, raw)
            refused = False
        except BchError:
            refused = True
        new, changed = pack(tmp, raw, allow_resize=True)
        d1, wr1 = unwrap(new)
        b1 = Bch(d1)
        t1 = b1.textures()[0]
        back = decode_level(t1["format"], nw, nh, b1.levels(t1)[0])
        err = sum((a - c) ** 2 for a, c in zip(back, img)) / max(1, len(img))
        import bchwrite
        d0, _ = unwrap(raw)
        ed = bchwrite.TexEdit(nw, nh, t1["format"], t1["mips"], b"".join(b1.levels(t1)))
        problems = bchwrite.verify_move(d0, d1, {0: ed})
        same_rest = not problems
        ok = (refused and (t1["width"], t1["height"]) == (nw, nh) and wr1 == "lz" and changed
              and err < 60 and same_rest)
        print(f"  {'PASS' if ok else 'FAIL'} resize {label}: {arcs[0]} {w}x{h} -> {nw}x{nh} "
              f"(refused without --allow-resize: {refused}; mean squared error {err:.1f})"
              + (f"; {problems[0]}" if problems else ""))
        bad += not ok
    shutil.rmtree(tmp, ignore_errors=True)
    export(raw, tmp)
    meta = json.load(open(os.path.join(tmp, "bch.json"), encoding="utf-8"))
    png = os.path.join(tmp, meta["textures"][0]["file"])
    tex3ds.write_png(png, 96, 64, bytes(96 * 64 * 4))
    try:
        pack(tmp, raw, allow_resize=True)
        ok, msg = False, "accepted"
    except BchError as e:
        ok, msg = "power" in str(e), str(e)
    print(f"  {'PASS' if ok else 'FAIL'} refuse non-power-of-two PNG: {msg[:90]}")
    bad += not ok
    return bad


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):  # Japanese names on a cp1252 console
        sys.stdout.reconfigure(errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("info", "export", "pack", "test", "selftest"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--lz", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--allow-resize", action="store_true",
                    help="pack: allow PNGs of another size / edited format or mips (relocating writer)")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return 1 if edit_selftest() else 0
    if a.cmd == "test":
        ok, n, parsed, _tex, (lzok, lzn) = test(a.jobs, a.lz, a.limit)
        return 0 if ok == n and lzok == lzn else 1
    if a.cmd == "info":
        with open(a.args[0], "rb") as fh:
            d, wrapper = unwrap(fh.read())
        b = Bch(d)
        print(json.dumps({"wrapper": wrapper, **b.summary()}, indent=1))
        for t in b.textures():
            print(f"  {t['index']:3d} {t['name'].decode('cp932', 'replace'):<32} {t['width']}x{t['height']} "
                  f"{tex3ds.FORMAT_NAMES.get(t['format'], t['format'])} mips={t['mips']} "
                  f"{t['section']}+0x{t['offset']:X} 0x{t['size']:X}")
        return 0
    if a.cmd == "export":
        with open(a.args[0], "rb") as fh:
            files = export(fh.read(), a.args[1])
        print(f"{len(files)} textures -> {a.args[1]}")
        return 0
    with open(a.args[1], "rb") as fh:
        orig = fh.read()
    try:
        new, changed = pack(a.args[0], orig, a.allow_resize)
    except BchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    tmp = a.args[2] + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(new)
    os.replace(tmp, a.args[2])
    print(f"{len(changed)} textures changed" + (": " + ", ".join(changed) if changed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
