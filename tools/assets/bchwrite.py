#!/usr/bin/env python3
"""Relocating BCH writer: replace a texture with one of a different size, mip count or
pixel format, and rebuild the file around it. Standard library only.

bch.py edits textures IN PLACE (same size, same format). This module is the next step:
it takes a parsed BCH, swaps the pixel data of one or more textures for data of any
legal size, and re-lays the file out:

  * the texture's chunk of the data section (its pixels plus the zero bytes up to the next
    thing anything points at) is replaced; everything after it in that section moves by a
    multiple of 0x80 bytes, so every later block keeps its alignment;
  * every pointer listed in the file's relocation table whose target moved is rewritten
    (contents and GPU-command words), the relocation table itself is re-encoded (its
    entries hold positions, which can move too), and the header's section offsets and
    lengths are updated; later sections (data-extended, relocation table) slide along;
  * the texture's own description is updated: width/height (PICA register 0x82/0x92/0x9A),
    mip levels (0x84/0x94/0x9C bits 16-19), format (0x8E/0x96/0x9E) in all three texture
    unit command lists, and the format / mip-count bytes of its contents entry (+0x18,
    +0x19);
  * nothing else changes: strings, names, materials, models, animations and every other
    texture keep their bytes (they may sit at a new file offset).

With no edits, write() still goes through the whole encoder (header, sections, relocation
table re-encoded from the parsed values) and gives back the original bytes.

What the game does with these fields (from code; addresses from config/functions.csv):
  nw::h3d::res::ResourceBinary::TryInit (0x3233F4) requires the memory addresses it is
      given for the GPU-command section to be 16-aligned and for the data and
      data-extended sections to be 0x80-aligned, then calls
  ResourceBinary::Relocate (0x3235A8): entry = offset (bits 0-24, x4 except kind 1),
      kind (bits 25-28), section holding the word (bits 29-31). The word gets the base of
      kind 0 contents, 1 strings, 2-3 GPU commands, 4-8 data, 9-13 data-extended; kinds
      5/10 (textures) become physical address >> 3; 6/11 (vertices), 7/12 (16-bit
      indices, bit 31 set), 8/13 (8-bit indices) become physical address minus a global
      base; kind 14 ignores the word and stores that global base >> 3 (attribute buffer
      base register 0x200). For kinds 5-13 the original address is saved in the
      "uninitialized data" area (4 bytes each) and the count must equal the header's
      address count (+0x42), so header +0x38 = 4 x address count. A texture resize keeps
      the number of relocations, so neither changes.
  TexCommand::GetWidth / GetHeight / GetAddress (0x19080C / 0x19092C / 0x1906F0) search a
      texture's unit command list for the dim / address registers, and ITexture::Setup
      (0x4EBC10) stores width, height, format (+0x18) and mip count (+0x19) from the
      resource and calls ITexture::SetMatrix (0x11D1B4), which scales texture coordinates
      by 1/width, 1/height. So the game takes the size from the file, not from a constant.
  nw::h3d::res::TextureSamplerData::MakeUnit0Command (0x51D118) builds the sampler words
      (0x83 / 0x84) at run time; a material's own copy of 0x82 / 0x84 / 0x85 is a zero
      placeholder (all 1,055 measured), filled from the texture when it is bound by name.
  FaceInstance::CalcDrawFaceRect (0x1AF8B0) draws a portrait at the texture's width and
      height in screen pixels (or, in one mode, at the FaceData layout numbers +0x34 /
      +0x36, centred with a fixed 256). A resized face is therefore drawn bigger or
      smaller (or cropped), not sharper: see portrait.py, which refuses face resizes
      unless asked.

Refused (BchError with a plain message): a side that is not a power of two or is outside
8..1024 (PICA limits), more mip levels than the size allows, a format change across
families (colour+alpha / colour / luminance(+alpha) / alpha / HILO8; a colour texture may
gain alpha, never lose it), a texture whose three unit command lists disagree or are not
the standard 2D layout (cube maps), data shared with another texture or pointed into, a
non-zero byte in the slack after the texture, an irregular section layout (overlapping
sections; one sample file), and anything that would not fit the relocation fields.

Usage (library):
    write(d, {index: TexEdit(width, height, fmt, mips, data)}) -> new BCH bytes
    coverage_problems(Bch) -> list of address-register words with no relocation
CLI:
    python tools/assets/bchwrite.py selftest     synthetic checks + resize/round trips on
                                                 sample ROM files (if extracted)
    python tools/assets/bchwrite.py test [--jobs N] [--limit N] [--fuzz N]
        every BCH (RomFS + .arc members): unedited rebuild identical; coverage scan; every
        texture grown (x2) or shrunk and checked (re-parse, other textures and sections
        bit-identical, only listed words changed), then restored = original bytes;
        a mutation fuzz (relocations removed -> the coverage scan must notice).
        Report extracted/assets/bchwrite_report.txt, failures bchwrite_fail.txt.
"""
from __future__ import annotations

import argparse
import os
import random
import struct
import sys
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bch  # noqa: E402
import tex3ds  # noqa: E402
from bch import Bch, BchError  # noqa: E402

ORDER = ("contents", "strings", "gpu", "data", "data_ext", "reloc")
TGT_INDEX = {"contents": 0, "strings": 1, "gpu": 2, "data": 3, "data_ext": 4}
ALIGN = 0x80          # data / data-extended alignment the loader requires
MAX_SIDE = 1024       # PICA texture size limits
MIN_SIDE = 8
REG_DIM, REG_LOD, REG_ADDR, REG_FMT = 0x82, 0x84, 0x85, 0x8E
# the same four registers for texture units 0, 1, 2 (PICA register map, 3dbrew)
UNIT_REGS = ({0x82: REG_DIM, 0x84: REG_LOD, 0x85: REG_ADDR, 0x8E: REG_FMT},
             {0x92: REG_DIM, 0x94: REG_LOD, 0x95: REG_ADDR, 0x96: REG_FMT},
             {0x9A: REG_DIM, 0x9C: REG_LOD, 0x9D: REG_ADDR, 0x9E: REG_FMT})
UNIT_REG = tuple({v: k for k, v in m.items()} for m in UNIT_REGS)  # unit -> {role: register}
# PICA registers that hold memory addresses (texture units 0-2 incl. cube faces, vertex
# attribute buffer offsets 0x203 + 3n, index buffer 0x227). 0x200 (attribute base) is
# relocation kind 14, whose stored value the loader ignores.
ADDR_REGS = frozenset({0x85, 0x86, 0x87, 0x88, 0x89, 0x8A, 0x95, 0x9D, 0x227} |
                      {0x203 + 3 * i for i in range(12)})
FAMILY = {0: "rgba", 2: "rgba", 4: "rgba", 13: "rgba", 1: "rgb", 3: "rgb", 12: "rgb",
          7: "l", 10: "l", 5: "la", 9: "la", 8: "a", 11: "a", 6: "hilo"}
WIDER = {"rgb": "rgba", "l": "la"}  # a family may move to its alpha-carrying version


@dataclass
class TexEdit:
    width: int
    height: int
    fmt: int
    mips: int
    data: bytes   # all mip levels, level 0 first (tex3ds layout)


def mip_dims(w: int, h: int, mips: int) -> list[tuple[int, int]]:
    return [(max(w >> i, 8), max(h >> i, 8)) for i in range(mips)]


def data_size(w: int, h: int, fmt: int, mips: int) -> int:
    return sum(tex3ds.data_size(fmt, a, b) for a, b in mip_dims(w, h, mips))


def max_mips(w: int, h: int) -> int:
    n = 1
    while min(w, h) >> n >= 8:
        n += 1
    return n


def _pow2(v: int) -> bool:
    return v > 0 and v & (v - 1) == 0


def format_change_ok(old: int, new: int) -> bool:
    fo, fn = FAMILY.get(old), FAMILY.get(new)
    return fo is not None and fn is not None and (fo == fn or WIDER.get(fo) == fn)


# ------------------------------------------------------------------ texture slots
def texture_slot(b: Bch, idx: int) -> dict:
    """Where texture `idx` keeps its size / LOD / address / format words (absolute file
    offsets, one per unit) and its contents entry. Raises if the units disagree or the
    command lists are not the standard 2D layout."""
    t = b.textures()[idx]
    e = b.entries("textures")[idx]
    go = b.sec["gpu"][0]
    units = []
    vals = None
    for u in range(3):
        off, n = struct.unpack_from("<2I", b.d, e + 8 * u)
        if n == 0:
            raise BchError(f"texture {t['name']!r}: unit {u} has no command list (cube map "
                           "or non-standard texture); resize refused")
        words = list(struct.unpack_from(f"<{n}I", b.d, go + off))
        pos = {}
        for reg, val, wi in bch.pica_commands(words):
            r0 = UNIT_REGS[u].get(reg)
            if r0 is not None and r0 not in pos:
                pos[r0] = (go + off + 4 * wi, val)
            elif 0x86 <= reg <= 0x8A:
                raise BchError(f"texture {t['name']!r}: cube-map faces; resize refused")
        for r0 in (REG_DIM, REG_ADDR, REG_FMT):
            if r0 not in pos:
                raise BchError(f"texture {t['name']!r}: unit {u} lacks register 0x{UNIT_REG[u][r0]:X}")
        v = tuple(pos[r][1] if r in pos else None for r in (REG_DIM, REG_LOD, REG_ADDR, REG_FMT))
        if vals is None:
            vals = v
        elif v != vals:
            raise BchError(f"texture {t['name']!r}: unit {u} command list disagrees with unit 0")
        units.append({r: p for r, (p, _v) in pos.items()})
    for u in units:
        if u[REG_ADDR] not in b.reloc_at:
            raise BchError(f"texture {t['name']!r}: an address word has no relocation")
    return {"entry": e, "units": units, "texture": t}


def check_edit(b: Bch, idx: int, ed: TexEdit, allow_format_family: bool = False) -> None:
    """Raise BchError (plain words) if this edit is unsafe."""
    texs = b.textures()
    if not 0 <= idx < len(texs):
        raise BchError(f"no texture {idx} (the file has {len(texs)})")
    t = texs[idx]
    nm = t["name"].decode("cp932", "replace")
    w, h = ed.width, ed.height
    if not (_pow2(w) and _pow2(h)):
        raise BchError(f"texture {nm!r}: {w}x{h} - both sides must be powers of two "
                       "(8, 16, 32, ... 1024); the 3DS GPU cannot use other sizes")
    if not (MIN_SIDE <= w <= MAX_SIDE and MIN_SIDE <= h <= MAX_SIDE):
        raise BchError(f"texture {nm!r}: {w}x{h} - sides must be between 8 and 1024")
    if ed.fmt not in tex3ds.FORMAT_NAMES:
        raise BchError(f"texture {nm!r}: unknown format {ed.fmt}")
    if ed.fmt != t["format"] and not allow_format_family and not format_change_ok(t["format"], ed.fmt):
        raise BchError(f"texture {nm!r}: format {tex3ds.FORMAT_NAMES[t['format']]} -> "
                       f"{tex3ds.FORMAT_NAMES[ed.fmt]} changes what the channels mean (or drops "
                       "alpha); allowed: same family, or colour -> colour+alpha, L -> LA")
    if not 1 <= ed.mips <= max_mips(w, h):
        raise BchError(f"texture {nm!r}: {ed.mips} mip levels; {w}x{h} allows 1..{max_mips(w, h)}")
    need = data_size(w, h, ed.fmt, ed.mips)
    if len(ed.data) != need:
        raise BchError(f"texture {nm!r}: data is 0x{len(ed.data):X} bytes, {w}x{h} "
                       f"{tex3ds.FORMAT_NAMES[ed.fmt]} with {ed.mips} levels needs 0x{need:X}")
    slot = texture_slot(b, idx)
    if ed.mips > 1 and any(REG_LOD not in u for u in slot["units"]):
        raise BchError(f"texture {nm!r}: has no LOD register, so it cannot gain mip levels")


# ------------------------------------------------------------------ layout
def regular(b: Bch) -> bool:
    """Sections in canonical order, not overlapping, after the header."""
    cur = header_size(b)
    for s in ORDER:
        o, ln = b.sec[s]
        if ln == 0:
            continue
        if o < cur:
            return False
        cur = o + ln
    return cur <= len(b.d)


def header_size(b: Bch) -> int:
    k = 6 if b.back > 0x20 else 5
    return 8 + 8 * k + 8 + (4 if b.back > 7 else 0)


def encode_header(b: Bch, offs: dict, lens: dict) -> bytes:
    names = ["contents", "strings", "gpu", "data"] + (["data_ext"] if b.back > 0x20 else []) + ["reloc"]
    out = struct.pack("<4sBBH", b"BCH\0", b.back, b.fwd, b.conv)
    out += struct.pack(f"<{len(names)}I", *(offs[n] for n in names))
    out += struct.pack(f"<{len(names)}I", *(lens[n] for n in names))
    out += struct.pack("<2I", b.uninit_data, b.uninit_desc)
    if b.back > 7:
        out += struct.pack("<2H", b.flags, b.addr_count)
    return out


def encode_reloc(tgt: str, kind: int, off: int) -> int:
    if kind == 1:
        field = off
    else:
        if off & 3:
            raise BchError(f"relocated word at {tgt}+0x{off:X} is not word aligned")
        field = off >> 2
    if field >> 25:
        raise BchError(f"relocation offset {tgt}+0x{off:X} does not fit 25 bits")
    return field | kind << 25 | TGT_INDEX[tgt] << 29


def section_targets(b: Bch, sec: str) -> list[int]:
    """Sorted section-relative offsets that relocated words point at in `sec`."""
    out = set()
    for _t, k, pos in b.relocs:
        if bch.kind_base(k) == sec:
            out.add(b.u32(pos) & 0x7FFFFFFF)
    return sorted(out)


class _Map:
    """Old -> new offsets inside one section after splices [(start, end, new_len)]."""

    def __init__(self, splices):
        self.sp = sorted(splices)

    def __call__(self, off: int) -> int:
        delta = 0
        for s, e, n in self.sp:
            if off <= s:
                break
            if off < e:
                raise BchError(f"a pointer targets 0x{off:X}, inside a replaced texture (0x{s:X}..0x{e:X})")
            delta += n - (e - s)
        return off + delta


# ------------------------------------------------------------------ writer
def write(d: bytes, edits: dict[int, TexEdit] | None = None, allow_format_family: bool = False,
          verify: bool = True) -> bytes:
    """New BCH bytes with the given textures replaced (see module doc). No edits: the
    file is re-encoded and comes back identical."""
    edits = edits or {}
    b = Bch(d)
    texs = b.textures()
    hs = header_size(b)
    old_off = {s: b.sec[s][0] for s in ORDER}
    old_len = {s: b.sec[s][1] for s in ORDER}
    if not regular(b):
        if edits:
            raise BchError("irregular section layout (sections overlap); resize refused")
        out = bytearray(encode_header(b, old_off, old_len) + d[hs:])
        ro = old_off["reloc"]  # re-encode the relocation table in place
        for i, (tgt, kind, pos) in enumerate(b.relocs):
            struct.pack_into("<I", out, ro + 4 * i, encode_reloc(tgt, kind, pos - old_off[tgt]))
        return bytes(out)

    # 1. splices per section
    splices: dict[str, list] = {}
    new_chunks: dict[str, list] = {}
    for idx in sorted(edits):
        ed = edits[idx]
        check_edit(b, idx, ed, allow_format_family)
        t = texs[idx]
        sec = t["section"]
        so, sl = b.sec[sec]
        start = t["offset"] - so
        tg = section_targets(b, sec)
        inside = [v for v in tg if start < v < start + t["size"]]
        if inside:
            raise BchError(f"texture {t['name']!r}: something points inside its pixels")
        if any(x["offset"] == t["offset"] for x in texs if x is not t):
            raise BchError(f"texture {t['name']!r}: pixels shared with another texture")
        nxt = [v for v in tg if v >= start + t["size"]]
        end = min(nxt[0], sl) if nxt else sl
        slack = d[so + start + t["size"]:so + end]
        if slack.count(0) != len(slack):
            raise BchError(f"texture {t['name']!r}: non-zero bytes after the pixels; resize refused")
        old_chunk = end - start
        pad = (old_chunk - len(ed.data)) % ALIGN
        chunk = ed.data + bytes(pad)
        splices.setdefault(sec, []).append((start, end, len(chunk)))
        new_chunks.setdefault(sec, []).append((start, end, chunk))
    for sec, sp in splices.items():
        sp.sort()
        for (s1, e1, _), (s2, _e2, _) in zip(sp, sp[1:]):
            if s2 < e1:
                raise BchError("two edited textures overlap")
    maps = {s: _Map(splices.get(s, [])) for s in ORDER}

    # 2. new section bytes
    secbytes = {}
    for s in ORDER:
        o, ln = old_off[s], old_len[s]
        raw = d[o:o + ln]
        if s in new_chunks:
            parts, cur = [], 0
            for st, en, chunk in sorted(new_chunks[s], key=lambda x: x[0]):
                parts += [raw[cur:st], chunk]
                cur = en
            parts.append(raw[cur:])
            raw = b"".join(parts)
        secbytes[s] = bytearray(raw)
    new_len = {s: len(secbytes[s]) for s in ORDER}
    delta = {s: new_len[s] - old_len[s] for s in ORDER}

    # 3. new section offsets: a section moves by the growth of every non-empty section
    #    that comes before it in the canonical order and ends at or before its start
    new_off = {}
    for i, s in enumerate(ORDER):
        shift = sum(delta[p] for p in ORDER[:i]
                    if old_len[p] and old_off[p] + old_len[p] <= old_off[s])
        new_off[s] = old_off[s] + shift if (old_len[s] or old_off[s]) else 0

    # 4. pointer words and the relocation table
    rel_sec = secbytes["reloc"]
    for i, (tgt, kind, pos) in enumerate(b.relocs):
        rel = pos - old_off[tgt]
        nrel = maps[tgt](rel)
        base = bch.kind_base(kind)
        if base in splices and kind != 14:
            w = b.u32(pos)
            mask = 0x7FFFFFFF if kind in (7, 12) else 0xFFFFFFFF
            struct.pack_into("<I", secbytes[tgt], nrel, maps[base](w & mask) | (w & ~mask & 0xFFFFFFFF))
        struct.pack_into("<I", rel_sec, 4 * i, encode_reloc(tgt, kind, nrel))

    # 5. texture descriptions
    for idx, ed in edits.items():
        slot = texture_slot(b, idx)
        co = old_off["contents"]
        eo = slot["entry"] + 0x18 - co
        secbytes["contents"][eo] = ed.fmt
        secbytes["contents"][eo + 1] = ed.mips
        go = old_off["gpu"]
        for u in slot["units"]:
            p = u[REG_DIM] - go
            v = struct.unpack_from("<I", secbytes["gpu"], p)[0]
            struct.pack_into("<I", secbytes["gpu"], p, (v & 0xF800F800) | ed.height | ed.width << 16)
            p = u[REG_FMT] - go
            v = struct.unpack_from("<I", secbytes["gpu"], p)[0]
            struct.pack_into("<I", secbytes["gpu"], p, (v & ~0xF & 0xFFFFFFFF) | ed.fmt)
            if REG_LOD in u:
                p = u[REG_LOD] - go
                v = struct.unpack_from("<I", secbytes["gpu"], p)[0]
                struct.pack_into("<I", secbytes["gpu"], p, (v & ~0xF0000 & 0xFFFFFFFF) | (ed.mips - 1) << 16)

    # 6. assemble: header, then each non-empty section after its original gap
    out = bytearray(encode_header(b, new_off, new_len))
    cur = hs
    for s in sorted((s for s in ORDER if old_len[s]), key=lambda s: old_off[s]):
        out += d[cur:old_off[s]]
        if len(out) != new_off[s]:
            raise BchError(f"internal: section {s} lands at 0x{len(out):X}, header says 0x{new_off[s]:X}")
        out += secbytes[s]
        cur = old_off[s] + old_len[s]
    out += d[cur:]
    out = bytes(out)
    if verify and edits:
        nb = Bch(out)
        nt = nb.textures()
        for idx, ed in edits.items():
            x = nt[idx]
            if (x["width"], x["height"], x["format"], x["mips"]) != (ed.width, ed.height, ed.fmt, ed.mips) \
                    or b"".join(nb.levels(x)) != ed.data:
                raise BchError(f"internal: texture {idx} did not read back as written")
        for s in ("data", "data_ext"):
            if nb.sec[s][1] and nb.sec[s][0] % ALIGN:
                raise BchError(f"internal: section {s} lost its 0x80 alignment")
    return out


def replace_texture_rgba(d: bytes, idx: int, w: int, h: int, rgba: bytes, fmt: int | None = None,
                         mips: int | None = None, allow_format_family: bool = False) -> bytes:
    """Encode an upright RGBA8 image (all mip levels, 2x2 box filter) and write() it as
    texture `idx`. fmt / mips default to the texture's own (mips clamped to the size)."""
    t = Bch(d).textures()[idx]
    fmt = t["format"] if fmt is None else fmt
    if mips is None:
        mips = min(t["mips"], max_mips(w, h)) if _pow2(w) and _pow2(h) else 1
    data = encode_levels(fmt, w, h, mips, rgba)
    return write(d, {idx: TexEdit(w, h, fmt, mips, data)}, allow_format_family)


def encode_levels(fmt: int, w: int, h: int, mips: int, rgba: bytes) -> bytes:
    out = []
    img, cw, ch = rgba, w, h
    for i, (a, c) in enumerate(mip_dims(w, h, mips)):
        if i:
            while cw > a or ch > c:
                img = bch.downscale(img, cw, ch)
                cw, ch = max(cw // 2, 1), max(ch // 2, 1)
        out.append(bch.encode_level(fmt, a, c, img))
    return b"".join(out)


# ------------------------------------------------------------------ coverage
def gpu_writes(b: Bch) -> list[tuple[int, int, int]]:
    """[(register, value, absolute file offset)] for the whole GPU-command section, read
    as one command stream (Fates' command lists are packed back to back)."""
    go, gl = b.sec["gpu"]
    if not gl:
        return []
    words = list(struct.unpack_from(f"<{gl // 4}I", b.d, go))
    return [(reg, val, go + 4 * wi) for reg, val, wi in bch.pica_commands(words)]


def coverage_problems(b: Bch) -> list[str]:
    """Words the writer could need to move but the relocation table does not list.
    Checked: every non-zero write to a PICA address register (textures, vertex buffers,
    index buffers) in the GPU-command section has a relocation, and every relocation
    into the data / data-extended sections that sits in the GPU-command section is on
    such a register (pointers in contents are listed, so they move with their target).
    An unlisted word holding 0 is harmless for the writer: offset 0 of a section never
    moves."""
    out = []
    regs = gpu_writes(b)
    at = {}
    for reg, val, pos in regs:
        at[pos] = reg
        if reg in ADDR_REGS and val and pos not in b.reloc_at:
            out.append(f"register 0x{reg:X} at 0x{pos:X} = 0x{val:X} has no relocation")
    go, gl = b.sec["gpu"]
    co, cl = b.sec["contents"]
    for tgt, kind, pos in b.relocs:
        base = bch.kind_base(kind)
        if base not in ("data", "data_ext"):
            continue
        if go <= pos < go + gl:
            if at.get(pos) not in ADDR_REGS:
                out.append(f"relocation kind {kind} at 0x{pos:X} is not on an address register")
        elif not co <= pos < co + cl:
            out.append(f"relocation kind {kind} at 0x{pos:X} ({tgt}) points into {base} from an unexpected section")
    return out


# ------------------------------------------------------------------ verification
def verify_move(d0: bytes, d1: bytes, edits: dict[int, TexEdit]) -> list[str]:
    """Independent checks after write(): returns problems (empty = fine).
    - both parse; same relocation count, header counters, resource counts
    - every texture not edited has the same pixels; edited ones read back as written
    - contents / strings / GPU sections are identical except at words the relocation
      table lists (the moved pointers) and the edited textures' own description words
    - every relocated pointer into data / data-extended that does not target an edited
      texture points at the same bytes (same length up to the next target) as before
    - the coverage scan finds nothing in the new file"""
    p = []
    b0, b1 = Bch(d0), Bch(d1)
    if len(b0.relocs) != len(b1.relocs) or (b0.uninit_data, b0.uninit_desc, b0.flags, b0.addr_count) != \
            (b1.uninit_data, b1.uninit_desc, b1.flags, b1.addr_count) or b0.content != b1.content:
        p.append("header counters / relocation count / contents table changed")
        return p
    t0, t1 = b0.textures(), b1.textures()
    for a, c in zip(t0, t1):
        if a["index"] in edits:
            ed = edits[a["index"]]
            if (c["width"], c["height"], c["format"], c["mips"]) != (ed.width, ed.height, ed.fmt, ed.mips) or \
                    b"".join(b1.levels(c)) != ed.data:
                p.append(f"edited texture {a['index']} reads back wrong")
        elif b0.levels(a) != b1.levels(c) or (a["width"], a["height"], a["format"], a["mips"]) != \
                (c["width"], c["height"], c["format"], c["mips"]):
            p.append(f"texture {a['index']} changed")
    allowed = set()
    for tgt, kind, pos in b0.relocs:
        allowed.add((tgt, pos - b0.sec[tgt][0]))
    for idx in edits:
        sl = texture_slot(b0, idx)
        allowed.add(("contents", sl["entry"] + 0x18 - b0.sec["contents"][0]))
        for u in sl["units"]:
            for r, pos in u.items():
                if r != REG_ADDR:
                    allowed.add(("gpu", pos - b0.sec["gpu"][0]))
    changed_unlisted = 0
    for s in ("contents", "strings", "gpu"):
        o0, l0 = b0.sec[s]
        o1, l1 = b1.sec[s]
        if l0 != l1:
            p.append(f"section {s} changed length")
            continue
        x, y = d0[o0:o0 + l0], d1[o1:o1 + l1]
        if x == y:
            continue
        for i in range(0, l0 - 3, 4):
            if x[i:i + 4] != y[i:i + 4] and (s, i) not in allowed:
                changed_unlisted += 1
        if l0 % 4 and x[l0 & ~3:] != y[l0 & ~3:]:
            changed_unlisted += 1
    if changed_unlisted:
        p.append(f"{changed_unlisted} words changed that the relocation table does not list")
    edited_starts = {(t0[i]["section"], t0[i]["offset"] - b0.sec[t0[i]["section"]][0]) for i in edits}
    for (tgt, kind, pos), (tgt1, kind1, pos1) in zip(b0.relocs, b1.relocs):
        base = bch.kind_base(kind)
        if base not in ("data", "data_ext") or kind == 14:
            continue
        v0 = b0.u32(pos) & 0x7FFFFFFF
        v1 = b1.u32(pos1) & 0x7FFFFFFF
        if (base, v0) in edited_starts:
            continue
        tg0 = section_targets(b0, base)
        nxt = [v for v in tg0 if v > v0]
        n = (nxt[0] if nxt else b0.sec[base][1]) - v0
        a = d0[b0.sec[base][0] + v0:b0.sec[base][0] + v0 + n]
        c = d1[b1.sec[base][0] + v1:b1.sec[base][0] + v1 + n]
        if a != c:
            p.append(f"pointer at 0x{pos:X} no longer points at the same bytes")
            break
    for s in ("data", "data_ext"):
        if b1.sec[s][1] and b1.sec[s][0] % ALIGN:
            p.append(f"section {s} not 0x80-aligned")
    p += coverage_problems(b1)
    return p


# ------------------------------------------------------------------ tests
def _synthetic_levels(fmt: int, w: int, h: int, mips: int, seed: int) -> bytes:
    rnd = random.Random(seed)
    return bytes(rnd.randrange(256) for _ in range(data_size(w, h, fmt, mips)))


def grow_shrink_target(t: dict) -> tuple[int, int]:
    w, h = t["width"], t["height"]
    if max(w, h) <= MAX_SIDE // 2:
        return w * 2, h * 2
    return max(w // 2, 8), max(h // 2, 8)


def check_file(d: bytes, all_textures: bool = True, seed: int = 0) -> dict:
    """The per-file test used by `test`: identity, coverage, resize round trips."""
    r = {"ident": False, "cov": [], "tex": 0, "resized": 0, "refused": {}, "fail": []}
    b = Bch(d)
    r["ident"] = write(d) == d
    if not r["ident"]:
        r["fail"].append("unedited rebuild differs")
    r["cov"] = coverage_problems(b)
    texs = b.textures()
    r["tex"] = len(texs)
    for t in (texs if all_textures else texs[:1]):
        nw, nh = grow_shrink_target(t)
        mips = min(t["mips"], max_mips(nw, nh))
        ed = TexEdit(nw, nh, t["format"], mips, _synthetic_levels(t["format"], nw, nh, mips, seed + t["index"]))
        try:
            d1 = write(d, {t["index"]: ed})
        except BchError as e:
            k = str(e).split(":", 1)[-1].strip().split(";")[0][:60]
            r["refused"][k] = r["refused"].get(k, 0) + 1
            continue
        prob = verify_move(d, d1, {t["index"]: ed})
        back = TexEdit(t["width"], t["height"], t["format"], t["mips"], b"".join(b.levels(t)))
        d2 = write(d1, {t["index"]: back})
        if d2 != d:
            prob.append("restore after resize is not byte-identical")
        if prob:
            r["fail"].append(f"texture {t['index']} {t['width']}x{t['height']}->{nw}x{nh}: " + "; ".join(prob[:3]))
        else:
            r["resized"] += 1
    return r


def _test_one(args):
    path, fuzz = args
    rel = os.path.relpath(path, bch.ROMFS).replace(os.sep, "/")
    out = []
    try:
        if ".bch" in rel.lower():
            with open(path, "rb") as fh:
                blobs = [(rel, fh.read())]
        else:
            import arc
            import isbin
            dd, _ = isbin.load_maybe_lz(path)
            blobs = [(f"{rel}:{m['name'].decode('cp932', 'replace')}", m["data"])
                     for m in arc.parse(dd) if b".bch" in m["name"].lower()]
    except Exception as e:  # report, never hide
        return [{"rel": rel, "err": f"{type(e).__name__}: {e}"}]
    for name, raw in blobs:
        try:
            d, _w = bch.unwrap(raw)
            r = check_file(d)
            r["rel"] = name
            if fuzz:
                r["fuzz"] = fuzz_relocs(d, fuzz, seed=len(d))
        except Exception as e:  # report, never hide
            r = {"rel": name, "err": f"{type(e).__name__}: {e}"}
        out.append(r)
    return out


def fuzz_relocs(d: bytes, n: int, seed: int = 0) -> tuple[int, int]:
    """Mutation check of the coverage scan: remove one relocation at a time (only entries
    on a non-zero address-register word, i.e. pointers the writer would move) and count
    how many removals the scan reports. Returns (detected, tried)."""
    b = Bch(d)
    cands = [i for i, (_t, k, pos) in enumerate(b.relocs)
             if bch.kind_base(k) in ("data", "data_ext") and k != 14 and b.u32(pos) & 0x7FFFFFFF
             and b.sec["gpu"][0] <= pos < b.sec["gpu"][0] + b.sec["gpu"][1]]
    rnd = random.Random(seed)
    rnd.shuffle(cands)
    det = tried = 0
    ro, rl = b.sec["reloc"]
    for i in cands[:n]:
        m = bytearray(d)
        # drop entry i: shift the later entries down, leave a duplicate of the last one
        # (duplicates are harmless for the scan) so the section length stays the same
        tbl = [struct.unpack_from("<I", d, ro + 4 * j)[0] for j in range(rl // 4)]
        del tbl[i]
        tbl.append(tbl[-1])
        struct.pack_into(f"<{len(tbl)}I", m, ro, *tbl)
        tried += 1
        det += bool(coverage_problems(Bch(bytes(m))))
    return det, tried


def test(jobs: int, limit: int = 0, fuzz: int = 2) -> dict:
    """Whole-corpus test (see module doc). Returns the counts; "ok" is True only if every
    check passed."""
    from concurrent.futures import ProcessPoolExecutor
    files = bch.bch_files()
    if limit:
        files = files[:limit]
    files.sort(key=lambda p: -os.path.getsize(p))
    n = ident = cov_ok = tex = resized = fd = ft = 0
    refused: dict = {}
    fails = []
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for rs in ex.map(_test_one, [(f, fuzz) for f in files], chunksize=4):
            for r in rs:
                n += 1
                if "err" in r:
                    fails.append(f"{r['rel']}\t{r['err']}")
                    continue
                ident += r["ident"]
                cov_ok += not r["cov"]
                tex += r["tex"]
                resized += r["resized"]
                for k, v in r["refused"].items():
                    refused[k] = refused.get(k, 0) + v
                if "fuzz" in r:
                    fd += r["fuzz"][0]
                    ft += r["fuzz"][1]
                for f in r["fail"]:
                    fails.append(f"{r['rel']}\t{f}")
                for c in r["cov"][:2]:
                    fails.append(f"{r['rel']}\tcoverage: {c}")
    nref = sum(refused.values())
    lines = [f"BCH files: {n} (RomFS files + .arc members)",
             f"  unedited rebuild through the relocating writer identical: {ident}/{n}",
             f"  relocation coverage scan clean (every non-zero GPU address word listed): {cov_ok}/{n}",
             f"  textures resized (x2, or /2 when 1024 wide) + verified + restored identical: "
             f"{resized}/{tex - nref} ({nref} refused by the safety rules)",
             "  refusals: " + (", ".join(f"{k} = {v}" for k, v in sorted(refused.items())) or "none"),
             f"  mutation fuzz: removed relocations detected by the coverage scan: {fd}/{ft}"]
    text = "\n".join(lines)
    print(text)
    os.makedirs(bch.REPORT_DIR, exist_ok=True)
    with open(os.path.join(bch.REPORT_DIR, "bchwrite_report.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + "\n")
    with open(os.path.join(bch.REPORT_DIR, "bchwrite_fail.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(fails) + "\n")
    for f in fails[:20]:
        print("  FAIL", f)
    ok = not fails and ident == n and cov_ok == n and resized == tex - nref and fd == ft
    return {"ok": ok, "files": n, "ident": ident, "cov_ok": cov_ok, "resized": resized,
            "resizable": tex - nref, "refused": nref, "fuzz_detected": fd, "fuzz_tried": ft}


# ------------------------------------------------------------------ selftest
def synthetic_bch(textures: list[tuple[int, int, int, int]], ext_tail: int = 0x40) -> bytes:
    """A small made-up BCH (no game data): one texture entry per (w, h, fmt, mips), pixels
    in the data section, a data-extended section with `ext_tail` bytes pointed at by a
    vertex-buffer register (kind 11) and an attribute base (kind 14), standard layout."""
    n = len(textures)
    # contents: 15 x 12-byte kind table, then the pointer table, then entries
    kinds = 15 * 12
    ptab = kinds
    ent0 = ptab + 4 * n
    contents = bytearray(ent0 + 0x20 * n)
    struct.pack_into("<3I", contents, 3 * 12, ptab, n, 0)
    relocs = []  # (tgt, kind, off)
    gpu = bytearray()
    data = bytearray()
    for i, (w, h, fmt, mips) in enumerate(textures):
        struct.pack_into("<I", contents, ptab + 4 * i, ent0 + 0x20 * i)
        relocs.append(("contents", 0, ptab + 4 * i))
        addr = len(data)
        sz = data_size(w, h, fmt, mips)
        data += bytes((i * 37 + j) & 255 for j in range(sz))
        data += bytes((-len(data)) % ALIGN)
        e = ent0 + 0x20 * i
        for u in range(3):
            rg = UNIT_REG[u]
            off = len(gpu)
            cmds = [h | w << 16, 0x000F0000 | rg[REG_DIM], (mips - 1) << 16, 0x000F0000 | rg[REG_LOD],
                    addr, 0x000F0000 | rg[REG_ADDR], fmt, 0x000F0000 | rg[REG_FMT],
                    0, 0x000F0000, 1, 0x000F023D]
            relocs.append(("gpu", 5, off + 16))
            gpu += struct.pack("<12I", *cmds)
            struct.pack_into("<2I", contents, e + 8 * u, off, 12)
            relocs.append(("contents", 2, e + 8 * u))
        struct.pack_into("<2I", contents, e + 0x18, fmt | mips << 8, 0)
        relocs.append(("contents", 1, e + 0x1C))
    # a vertex setup: attribute base (kind 14) and buffer 0 offset (kind 11) into data_ext
    vo = len(gpu)
    gpu += struct.pack("<4I", 0, 0x000F0200, 0x10, 0x000F0203)
    relocs.append(("gpu", 14, vo))
    relocs.append(("gpu", 11, vo + 8))
    gpu += bytes((-len(gpu)) % 16)
    strings = b"t\0\0\0"
    ext = bytes(0x10) + bytes(range(ext_tail))
    hs = 0x44
    offs, lens = {}, {}
    cur = hs
    for s, blob, al in (("contents", contents, 4), ("strings", strings, 4), ("gpu", gpu, 16),
                        ("data", data, ALIGN), ("data_ext", ext, ALIGN)):
        cur = (cur + al - 1) & ~(al - 1)
        offs[s], lens[s] = cur, len(blob)
        cur += len(blob)
    cur = (cur + 3) & ~3
    offs["reloc"], lens["reloc"] = cur, 4 * len(relocs)
    out = bytearray(cur + lens["reloc"])
    hdr = struct.pack("<4sBBH", b"BCH\0", 0x22, 0x23, 1)
    hdr += struct.pack("<6I", *(offs[s] for s in ORDER)) + struct.pack("<6I", *(lens[s] for s in ORDER))
    naddr = sum(1 for _t, k, _o in relocs if 5 <= k <= 13)
    hdr += struct.pack("<2I2H", 4 * naddr, 0, 1, naddr)
    out[:hs] = hdr
    for s, blob in (("contents", contents), ("strings", strings), ("gpu", gpu), ("data", data), ("data_ext", ext)):
        out[offs[s]:offs[s] + len(blob)] = blob
    for i, (tgt, kind, off) in enumerate(relocs):
        struct.pack_into("<I", out, offs["reloc"] + 4 * i, encode_reloc(tgt, kind, off))
    return bytes(out)


def selftest() -> int:
    bad = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal bad
        print(f"  {'PASS' if cond else 'FAIL'} {label}")
        bad += not cond

    # synthetic file: three textures (no game data)
    d = synthetic_bch([(64, 64, 13, 1), (32, 16, 4, 2), (16, 16, 12, 1)])
    b = Bch(d)
    ok(write(d) == d, "synthetic: unedited rebuild identical")
    ok(not coverage_problems(b), "synthetic: coverage scan clean")
    for (nw, nh, fmt, mips) in ((128, 128, 13, 1), (32, 32, 13, 1), (8, 8, 13, 1), (64, 64, 0, 3)):
        ed = TexEdit(nw, nh, fmt, mips, _synthetic_levels(fmt, nw, nh, mips, nw))
        try:
            d1 = write(d, {0: ed})
            prob = verify_move(d, d1, {0: ed})
            back = TexEdit(64, 64, 13, 1, b"".join(b.levels(b.textures()[0])))
            same = write(d1, {0: back}) == d
        except BchError as e:
            prob, same = [str(e)], False
        ok(not prob and same, f"synthetic: texture 0 64x64 ETC1A4 -> {nw}x{nh} "
           f"{tex3ds.FORMAT_NAMES[fmt]} mips {mips}, verified and restored")
    ed2 = {1: TexEdit(64, 64, 4, 3, _synthetic_levels(4, 64, 64, 3, 5)),
           2: TexEdit(32, 32, 13, 1, _synthetic_levels(13, 32, 32, 1, 6))}
    d2 = write(d, ed2)
    ok(not verify_move(d, d2, ed2), "synthetic: two textures resized at once (one gains alpha)")
    for label, ed, idx in (("non-power-of-two", TexEdit(48, 64, 13, 1, bytes(data_size(48, 64, 13, 1))), 0),
                           ("2048 wide", TexEdit(2048, 8, 13, 1, bytes(data_size(2048, 8, 13, 1))), 0),
                           ("alpha dropped (ETC1A4 -> ETC1)", TexEdit(64, 64, 12, 1, bytes(data_size(64, 64, 12, 1))), 0),
                           ("too many mips", TexEdit(16, 16, 12, 3, bytes(data_size(16, 16, 12, 3))), 2),
                           ("wrong data length", TexEdit(64, 64, 13, 1, bytes(10)), 0)):
        try:
            write(d, {idx: ed})
            ok(False, f"synthetic: {label} refused")
        except BchError as e:
            ok(True, f"synthetic: {label} refused ({str(e)[:70]})")
    # mutation: drop the vertex-buffer relocation -> the scan must notice
    det, tried = fuzz_relocs(d, 10)
    ok(det == tried and tried > 0, f"synthetic: coverage scan notices removed relocations ({det}/{tried})")
    # sample ROM files, if extracted
    if os.path.isdir(bch.ROMFS):
        picks = _sample_rom_files()
        for rel, raw in picks:
            dd, _ = bch.unwrap(raw)
            r = check_file(dd)
            fine = r["ident"] and not r["cov"] and not r["fail"] and r["resized"] + sum(r["refused"].values()) == r["tex"]
            ok(fine, f"ROM {rel}: identity, coverage, {r['resized']}/{r['tex']} textures resized "
               f"and restored" + (f" ({r['fail'][0]})" if r["fail"] else ""))
    else:
        print("  SKIP ROM samples: no extracted/romfs")
    return bad


def _sample_rom_files() -> list[tuple[str, bytes]]:
    """A portrait expression, a portrait hair layer, a model file that carries its own
    textures and a stored-wrapper field texture file (first match of each, sorted)."""
    import arc
    import isbin
    out = []
    face = os.path.join(bch.ROMFS, "face", "face")
    if os.path.isdir(face):
        for f in sorted(os.listdir(face)):
            if f.endswith("_st.arc"):
                dd, _ = isbin.load_maybe_lz(os.path.join(face, f))
                m = next(x for x in arc.parse(dd) if b".bch" in x["name"].lower())
                out.append((f"face/face/{f}:{m['name'].decode('cp932', 'replace')}", m["data"]))
                break
    want = {"hair": None, "model": None, "stored": None}
    for p in bch.bch_files():
        if ".bch" not in p.lower() or all(want.values()):
            continue
        rel = os.path.relpath(p, bch.ROMFS).replace(os.sep, "/")
        key = "hair" if rel.startswith("face/hair/") else "model"
        with open(p, "rb") as fh:
            raw = fh.read()
        if raw[:1] == b"\0" and not want["stored"]:
            want["stored"] = (rel, raw)
        if key and not want[key]:
            d, _ = bch.unwrap(raw)
            b = Bch(d)
            if b.textures() and (key != "model" or (b.content["models"][1] and len(d) < 400000)):
                want[key] = (rel, raw)
    return out + [v for v in want.values() if v]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("selftest", "test"))
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--fuzz", type=int, default=2, help="relocations removed per file in the mutation check")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return 1 if selftest() else 0
    return 0 if test(a.jobs, a.limit, a.fuzz)["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
