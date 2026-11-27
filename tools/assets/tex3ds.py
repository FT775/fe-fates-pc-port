#!/usr/bin/env python3
"""3DS (PICA200) texture codecs + a minimal PNG reader/writer. Standard library only.

Formats (CTPK / CGFX numbering):
    0 RGBA8888  1 RGB888  2 RGBA5551  3 RGB565  4 RGBA4444  5 LA88  6 HILO8
    7 L8  8 A8  9 LA44  10 L4  11 A4  12 ETC1  13 ETC1A4
Pixel data is stored in 8x8 tiles (tiles left-to-right, rows of tiles in memory order),
Morton (Z) order inside a tile; the first tile row is the top of the picture (see
FLIP_Y). decode() returns a top-down RGBA8 image, encode() takes one. ETC1 blocks are 4x4, four per 8x8 tile in Z
order, each a little-endian u64 (ETC1A4: a u64 of 4-bit alpha first, column-major).

Exactness: every non-ETC format round-trips bit-exactly through RGBA8 (channels are
expanded by bit replication and reduced by truncation). ETC1/ETC1A4 decoding is exact,
but re-encoding is lossy; encode() has an ETC1 encoder for edited images (ETC_QUALITY
"high": refitted base colours, exact scoring, deterministic; "fast": the original simple
search), and callers keep the original blocks when the image is unchanged. ETC1A4 alpha
is rounded to the nearest 4-bit step.

Usage (library):  decode(fmt, w, h, data) -> bytes RGBA;  encode(fmt, w, h, rgba) -> bytes
                  write_png(path, w, h, rgba);  read_png(path) -> (w, h, rgba)
CLI:   python tools/assets/tex3ds.py selftest     encode/decode identities on random data,
                                                  refined ETC1 search checks
"""
from __future__ import annotations

import operator
import os
import random
import struct
import sys
import zlib
from array import array
from functools import lru_cache

FORMAT_NAMES = {0: "RGBA8888", 1: "RGB888", 2: "RGBA5551", 3: "RGB565", 4: "RGBA4444",
                5: "LA88", 6: "HILO8", 7: "L8", 8: "A8", 9: "LA44", 10: "L4", 11: "A4",
                12: "ETC1", 13: "ETC1A4"}
BPP = {0: 32, 1: 24, 2: 16, 3: 16, 4: 16, 5: 16, 6: 16, 7: 8, 8: 8, 9: 8, 10: 4, 11: 4,
       12: 4, 13: 8}


def data_size(fmt: int, w: int, h: int) -> int:
    return w * h * BPP[fmt] // 8


# ----------------------------------------------------------------- tables
def _tbl(f) -> bytes:
    return bytes(f(i) & 255 for i in range(256))


HI_REP = _tbl(lambda v: (v & 0xF0) | (v >> 4))          # high nibble -> 8 bit
LO_REP = _tbl(lambda v: (v & 0x0F) * 0x11)              # low nibble -> 8 bit
HI_NIB = _tbl(lambda v: v >> 4)
LO_NIB = _tbl(lambda v: v & 0x0F)
AND_F0 = _tbl(lambda v: v & 0xF0)
SHR4 = _tbl(lambda v: v >> 4)
SHL4 = _tbl(lambda v: v << 4)
FF = b"\xff"
ZERO = b"\0"


def _or(*parts: bytes) -> bytes:
    n = len(parts[0])
    acc = 0
    for p in parts:
        acc |= int.from_bytes(p, "little")
    return acc.to_bytes(n, "little")


def _interleave(chans: list[bytes]) -> bytes:
    k = len(chans)
    out = bytearray(len(chans[0]) * k)
    for i, c in enumerate(chans):
        out[i::k] = c
    return bytes(out)


def _split(data: bytes, k: int) -> list[bytes]:
    return [data[i::k] for i in range(k)]


# ----------------------------------------------------------------- swizzle
# The first tile row in memory is the TOP of the picture for FE Awakening's CTPK/CGFX and
# Fates' BCH textures
# (checked visually on portraits, map sprites and UI art). Set True for bottom-up data.
FLIP_Y = False

@lru_cache(maxsize=64)
def _perm(w: int, h: int):
    """getter mapping tiled-order pixel list -> top-down raster order."""
    order = [0] * (w * h)
    i = 0
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            for m in range(64):
                x = (m & 1) | (m >> 1 & 2) | (m >> 2 & 4)
                y = (m >> 1 & 1) | (m >> 2 & 2) | (m >> 3 & 4)
                yy = (h - 1 - (ty + y)) if FLIP_Y else (ty + y)
                order[yy * w + tx + x] = i
                i += 1
    inv = [0] * (w * h)
    for raster, tiled in enumerate(order):
        inv[tiled] = raster
    return operator.itemgetter(*order), operator.itemgetter(*inv)


def _untile(px: bytes, w: int, h: int, k: int) -> bytes:
    """Reorder k-byte pixels from tiled order to raster order."""
    get, _ = _perm(w, h)
    if k == 4:
        a = array("I")
        a.frombytes(px)
        return array("I", get(a)).tobytes() if w * h > 1 else px
    if k == 1:
        return bytes(get(px)) if w * h > 1 else px
    if k == 2:
        a = array("H")
        a.frombytes(px)
        return array("H", get(a)).tobytes() if w * h > 1 else px
    raise ValueError(k)


def _tile(px: bytes, w: int, h: int, k: int) -> bytes:
    _, get = _perm(w, h)
    if k == 4:
        a = array("I")
        a.frombytes(px)
        return array("I", get(a)).tobytes() if w * h > 1 else px
    if k == 1:
        return bytes(get(px)) if w * h > 1 else px
    if k == 2:
        a = array("H")
        a.frombytes(px)
        return array("H", get(a)).tobytes() if w * h > 1 else px
    raise ValueError(k)


# ----------------------------------------------------------------- 5/6-bit helpers
def _rep5(v: int) -> int:
    return (v << 3) | (v >> 2)


def _rep6(v: int) -> int:
    return (v << 2) | (v >> 4)


@lru_cache(maxsize=None)
def _lut16(kind: str) -> list[bytes]:
    """u16 -> 4-byte RGBA lookup for 5551/565."""
    out = []
    for v in range(65536):
        if kind == "5551":
            r, g, b, a = _rep5(v >> 11), _rep5(v >> 6 & 31), _rep5(v >> 1 & 31), 255 if v & 1 else 0
        else:
            r, g, b, a = _rep5(v >> 11), _rep6(v >> 5 & 63), _rep5(v & 31), 255
        out.append(bytes((r, g, b, a)))
    return out


def _nibbles(data: bytes) -> bytes:
    """4bpp -> one byte per pixel (low nibble first)."""
    return _interleave([data.translate(LO_NIB), data.translate(HI_NIB)])


# ----------------------------------------------------------------- decode
def decode(fmt: int, w: int, h: int, data: bytes) -> bytes:
    """Return top-down RGBA8 bytes (w*h*4)."""
    n = w * h
    data = bytes(data[:data_size(fmt, w, h)])
    if len(data) < data_size(fmt, w, h):
        raise ValueError("texture data too short")
    if fmt in (12, 13):
        return _etc_decode(data, w, h, fmt == 13)
    if fmt == 0:
        a, b, g, r = _split(data, 4)
        px = _interleave([r, g, b, a])
    elif fmt == 1:
        b, g, r = _split(data, 3)
        px = _interleave([r, g, b, FF * n])
    elif fmt in (2, 3):
        lut = _lut16("5551" if fmt == 2 else "565")
        a16 = array("H")
        a16.frombytes(data)
        px = b"".join(map(lut.__getitem__, a16))
    elif fmt == 4:
        lo, hi = _split(data, 2)
        px = _interleave([hi.translate(HI_REP), hi.translate(LO_REP), lo.translate(HI_REP), lo.translate(LO_REP)])
    elif fmt == 5:
        a, l = _split(data, 2)
        px = _interleave([l, l, l, a])
    elif fmt == 6:
        g, r = _split(data, 2)  # HILO8: stored as (G, R); B = 0
        px = _interleave([r, g, ZERO * n, FF * n])
    elif fmt == 7:
        px = _interleave([data, data, data, FF * n])
    elif fmt == 8:
        px = _interleave([FF * n, FF * n, FF * n, data])
    elif fmt == 9:
        l = data.translate(HI_REP)
        px = _interleave([l, l, l, data.translate(LO_REP)])
    elif fmt == 10:
        l = _nibbles(data).translate(LO_REP)
        px = _interleave([l, l, l, FF * n])
    elif fmt == 11:
        a = _nibbles(data).translate(LO_REP)
        px = _interleave([FF * n, FF * n, FF * n, a])
    else:
        raise ValueError(f"unknown texture format {fmt}")
    return _untile(px, w, h, 4)


# ----------------------------------------------------------------- encode
def encode(fmt: int, w: int, h: int, rgba: bytes) -> bytes:
    """Encode a top-down RGBA8 image (exact inverse of decode for non-ETC formats)."""
    n = w * h
    if len(rgba) != n * 4:
        raise ValueError("RGBA size mismatch")
    if fmt in (12, 13):
        return _etc_encode(rgba, w, h, fmt == 13)
    px = _tile(bytes(rgba), w, h, 4)
    r, g, b, a = _split(px, 4)
    if fmt == 0:
        return _interleave([a, b, g, r])
    if fmt == 1:
        return _interleave([b, g, r])
    if fmt in (2, 3):
        out = array("H", bytes(2 * n))
        if fmt == 2:
            for i in range(n):
                out[i] = (r[i] >> 3) << 11 | (g[i] >> 3) << 6 | (b[i] >> 3) << 1 | (a[i] >> 7)
        else:
            for i in range(n):
                out[i] = (r[i] >> 3) << 11 | (g[i] >> 2) << 5 | (b[i] >> 3)
        return out.tobytes()
    if fmt == 4:
        lo = _or(b.translate(AND_F0), a.translate(SHR4))
        hi = _or(r.translate(AND_F0), g.translate(SHR4))
        return _interleave([lo, hi])
    if fmt == 5:
        return _interleave([a, r])
    if fmt == 6:
        return _interleave([g, r])
    if fmt == 7:
        return r
    if fmt == 8:
        return a
    if fmt == 9:
        return _or(r.translate(AND_F0), a.translate(SHR4))
    if fmt in (10, 11):
        v = (r if fmt == 10 else a).translate(SHR4)
        return _or(v[0::2], v[1::2].translate(SHL4))
    raise ValueError(f"unknown texture format {fmt}")


# ----------------------------------------------------------------- ETC1
ETC_TABLES = ((2, 8), (5, 17), (9, 29), (13, 42), (18, 60), (24, 80), (33, 106), (47, 183))


def _clamp(v: int) -> int:
    return 0 if v < 0 else (255 if v > 255 else v)


def _etc_block(blk: int) -> list[tuple[int, int, int]]:
    """Decode one ETC1 u64 to 16 RGB tuples indexed by x*4+y."""
    hi = blk >> 32
    lo = blk & 0xFFFFFFFF
    flip = hi & 1
    diff = hi >> 1 & 1
    if diff:
        r1, g1, b1 = hi >> 27 & 31, hi >> 19 & 31, hi >> 11 & 31
        dr, dg, db = hi >> 24 & 7, hi >> 16 & 7, hi >> 8 & 7
        dr, dg, db = dr - 8 if dr > 3 else dr, dg - 8 if dg > 3 else dg, db - 8 if db > 3 else db
        r2, g2, b2 = r1 + dr, g1 + dg, b1 + db
        c1 = (_rep5(r1), _rep5(g1), _rep5(b1))
        c2 = (_rep5(r2 & 31), _rep5(g2 & 31), _rep5(b2 & 31))
    else:
        c1 = ((hi >> 28 & 15) * 17, (hi >> 20 & 15) * 17, (hi >> 12 & 15) * 17)
        c2 = ((hi >> 24 & 15) * 17, (hi >> 16 & 15) * 17, (hi >> 8 & 15) * 17)
    t1 = ETC_TABLES[hi >> 5 & 7]
    t2 = ETC_TABLES[hi >> 2 & 7]
    out = [None] * 16
    for i in range(16):
        x, y = i >> 2, i & 3
        second = (y >= 2) if flip else (x >= 2)
        base, t = (c2, t2) if second else (c1, t1)
        msb = lo >> (16 + i) & 1
        lsb = lo >> i & 1
        m = t[lsb]
        if msb:
            m = -m
        out[i] = (_clamp(base[0] + m), _clamp(base[1] + m), _clamp(base[2] + m))
    return out


def _etc_decode(data: bytes, w: int, h: int, alpha: bool) -> bytes:
    out = bytearray(w * h * 4)
    pos = 0
    step = 16 if alpha else 8
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            for bi in range(4):
                bx = tx + (bi & 1) * 4
                by = ty + (bi >> 1) * 4
                if alpha:
                    am = int.from_bytes(data[pos:pos + 8], "little")
                    blk = int.from_bytes(data[pos + 8:pos + 16], "little")
                else:
                    am = -1
                    blk = int.from_bytes(data[pos:pos + 8], "little")
                pos += step
                px = _etc_block(blk)
                for i in range(16):
                    x, y = bx + (i >> 2), by + (i & 3)
                    if x >= w or y >= h:
                        continue
                    a = ((am >> (4 * i)) & 15) * 17 if alpha else 255
                    o = (((h - 1 - y) if FLIP_Y else y) * w + x) * 4
                    r, g, b = px[i]
                    out[o] = r
                    out[o + 1] = g
                    out[o + 2] = b
                    out[o + 3] = a
    return bytes(out)


def _etc_half_best(pix, base):
    """Best table/modifiers for pixels around base colour: (err, table, idx list)."""
    best = None
    for ti, (a, b) in enumerate(ETC_TABLES):
        mods = (a, b, -a, -b)  # lsb/msb order: idx = msb<<1 | lsb -> mods[idx]
        err = 0
        idxs = []
        for (r, g, bl) in pix:
            be = None
            bi = 0
            for k, m in enumerate(mods):
                dr = _clamp(base[0] + m) - r
                dg = _clamp(base[1] + m) - g
                db = _clamp(base[2] + m) - bl
                e = dr * dr + dg * dg + db * db
                if be is None or e < be:
                    be, bi = e, k
            err += be
            idxs.append(bi)
            if best is not None and err >= best[0]:
                break
        else:
            if best is None or err < best[0]:
                best = (err, ti, idxs)
    return best


def _etc_split(flip: int):
    """Pixel indexes (x*4+y) of the two halves of a block for one flip bit."""
    h0, h1 = [], []
    for i in range(16):
        x, y = i >> 2, i & 3
        second = (y >= 2) if flip else (x >= 2)
        (h1 if second else h0).append(i)
    return h0, h1


_SPLIT = (_etc_split(0), _etc_split(1))


def _etc_search_simple(px16):
    """The original simple search: average colour per half, both flips, individual and
    differential modes. Returns (err, flip, diff, (q1, q2), (table1, idx1), (table2, idx2))."""
    best = None
    for flip in (0, 1):
        hidx = _SPLIT[flip]
        halves = ([px16[i] for i in hidx[0]], [px16[i] for i in hidx[1]])
        avgs = []
        for hp in halves:
            n = len(hp)
            avgs.append(tuple(sum(p[c] for p in hp) / n for c in range(3)))
        # individual (4-bit each) mode
        q4 = [tuple(min(15, max(0, int(round(c / 17)))) for c in a) for a in avgs]
        cand = [(0, q4, [tuple(c * 17 for c in q) for q in q4])]
        # differential mode
        q5 = [tuple(min(31, max(0, int(round(c * 31 / 255)))) for c in a) for a in avgs]
        d = [q5[1][c] - q5[0][c] for c in range(3)]
        if all(-4 <= v <= 3 for v in d):
            cand.append((1, q5, [tuple(_rep5(c) for c in q) for q in q5]))
        for diff, q, bases in cand:
            r1 = _etc_half_best(halves[0], bases[0])
            r2 = _etc_half_best(halves[1], bases[1])
            err = r1[0] + r2[0]
            if best is None or err < best[0]:
                best = (err, flip, diff, (tuple(q[0]), tuple(q[1])), (r1[1], r1[2]), (r2[1], r2[2]))
    return best


def _etc_pack(flip: int, diff: int, q, t1, t2) -> int:
    """ETC1 u64 from the chosen mode, quantized base colours and (table, indexes) per half."""
    (a1, b1, c1), (a2, b2, c2) = q
    if diff:
        hi = (a1 << 27 | ((a2 - a1) & 7) << 24 | b1 << 19 | ((b2 - b1) & 7) << 16 |
              c1 << 11 | ((c2 - c1) & 7) << 8)
    else:
        hi = a1 << 28 | a2 << 24 | b1 << 20 | b2 << 16 | c1 << 12 | c2 << 8
    hi |= t1[0] << 5 | t2[0] << 2 | diff << 1 | flip
    lo = 0
    for (_ti, idxs), pos in ((t1, _SPLIT[flip][0]), (t2, _SPLIT[flip][1])):
        for k, i in zip(idxs, pos):
            lo |= (k & 1) << i | (k >> 1) << (16 + i)
    return hi << 32 | lo


def _etc_encode_block_simple(px16) -> int:
    """px16: 16 RGB tuples indexed by x*4+y. Returns the ETC1 u64 (the original simple
    encoder, kept for comparison: ETC_QUALITY = "fast")."""
    _err, flip, diff, q, t1, t2 = _etc_search_simple(px16)
    return _etc_pack(flip, diff, q, t1, t2)


# ---- refined ETC1 search (ETC_QUALITY = "high", the default)
# Facts used (public ETC1 specification, Khronos OES_compressed_ETC1_RGB8_texture): a half
# block is one base colour plus one of 8 modifier tables, and each pixel adds the same
# modifier to R, G and B. So for a fixed table the best base colour is (pixel average -
# average chosen modifier), and each pixel's best modifier is the one nearest its
# brightness offset. The search refits the base colour per table that way, tries the
# quantization neighbours (floor / ceil per channel) and scores every candidate exactly
# (with the hardware's 0..255 clamping). Deterministic: candidates are visited in sorted
# order and ties keep the first one found.
_CL = bytes(_clamp(i - 512) for i in range(1024))  # _CL[v + m + 512] = clamp(v + m)
_MODS = tuple((a, b, -a, -b) for a, b in ETC_TABLES)
_EXP4 = tuple(v * 17 for v in range(16))
_EXP5 = tuple(_rep5(v) for v in range(32))
_NEAR = ((0, 0, 0), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))


def _etc_eval(pix, r: int, g: int, b: int, mods, limit: int):
    """Exact squared error of a half for base colour (r, g, b) and one table. Returns
    (err, indexes), or None as soon as the error reaches `limit`."""
    cl = _CL
    r += 512
    g += 512
    b += 512
    m0, m1, m2, m3 = mods
    r0, g0, b0 = cl[r + m0], cl[g + m0], cl[b + m0]
    r1, g1, b1 = cl[r + m1], cl[g + m1], cl[b + m1]
    r2, g2, b2 = cl[r + m2], cl[g + m2], cl[b + m2]
    r3, g3, b3 = cl[r + m3], cl[g + m3], cl[b + m3]
    err = 0
    idx = []
    for pr, pg, pb in pix:
        e = (r0 - pr) ** 2 + (g0 - pg) ** 2 + (b0 - pb) ** 2
        k = 0
        e1 = (r1 - pr) ** 2 + (g1 - pg) ** 2 + (b1 - pb) ** 2
        if e1 < e:
            e, k = e1, 1
        e1 = (r2 - pr) ** 2 + (g2 - pg) ** 2 + (b2 - pb) ** 2
        if e1 < e:
            e, k = e1, 2
        e1 = (r3 - pr) ** 2 + (g3 - pg) ** 2 + (b3 - pb) ** 2
        if e1 < e:
            e, k = e1, 3
        err += e
        if err >= limit:
            return None
        idx.append(k)
    return err, idx


def _etc_candidates(pix, bits: int) -> list:
    """Quantized base colours worth trying for one half (4-bit individual or 5-bit
    differential): the rounded average, and per table the refitted base colour's
    floor/ceil per channel."""
    n = len(pix)
    avg = [sum(p[c] for p in pix) / n for c in range(3)]
    lum = [(p[0] + p[1] + p[2]) / 3 for p in pix]
    la = sum(lum) / n
    top = 15 if bits == 4 else 31
    scale = 1 / 17 if bits == 4 else 31 / 255
    out = {tuple(min(top, max(0, int(round(c * scale)))) for c in avg)}
    for mods in _MODS:
        ms = 0
        for v in lum:
            dv = v - la
            best_m, best_e = 0, None
            for m in mods:
                e = (m - dv) * (m - dv)
                if best_e is None or e < best_e:
                    best_m, best_e = m, e
            ms += best_m
        mm = ms / n
        fl = [int((avg[c] - mm) * scale // 1) for c in range(3)]
        for dr in (0, 1):
            for dg in (0, 1):
                for db in (0, 1):
                    out.add((min(top, max(0, fl[0] + dr)), min(top, max(0, fl[1] + dg)),
                             min(top, max(0, fl[2] + db))))
    return sorted(out)


def _etc_try(pix, exp, qs, limit: int, best):
    for q in qs:
        r, g, b = exp[q[0]], exp[q[1]], exp[q[2]]
        for ti, mods in enumerate(_MODS):
            res = _etc_eval(pix, r, g, b, mods, limit)
            if res is not None:
                limit = res[0]
                best = (res[0], q, ti, res[1])
                if limit == 0:
                    return best, limit
    return best, limit


def _etc_half_search(pix, bits: int, qs, limit: int, lo=(0, 0, 0), hi=None):
    """Best (err, q, table, indexes) over candidate bases `qs` and all 8 tables, or None if
    nothing beats `limit`. The winner is refitted once more from its own modifier choice
    (base = average of pixel - modifier) and the new floor/ceil neighbours (kept inside
    lo..hi per channel) are tried."""
    exp = _EXP4 if bits == 4 else _EXP5
    best, limit = _etc_try(pix, exp, qs, limit, None)
    if best is None or limit == 0:
        return best
    top = 15 if bits == 4 else 31
    if hi is None:
        hi = (top, top, top)
    scale = 1 / 17 if bits == 4 else 31 / 255
    mods = _MODS[best[2]]
    n = len(pix)
    mm = sum(mods[k] for k in best[3]) / n
    fl = [int((sum(p[c] for p in pix) / n - mm) * scale // 1) for c in range(3)]
    seen = set(qs)
    more = sorted({(min(hi[0], max(lo[0], fl[0] + dr)), min(hi[1], max(lo[1], fl[1] + dg)),
                    min(hi[2], max(lo[2], fl[2] + db)))
                   for dr in (0, 1) for dg in (0, 1) for db in (0, 1)} - seen)
    best, _ = _etc_try(pix, exp, more, limit, best)
    return best


def _etc_search_hq(px16):
    """Refined search: starts from the simple encoder's answer, then for both flips tries
    refitted base colours in individual and differential mode (a differential pair out of
    the -4..3 range is re-searched with one half clamped into reach of the other)."""
    best = _etc_search_simple(px16)
    if best[0] == 0:
        return best
    for flip in (0, 1):
        hidx = _SPLIT[flip]
        h0 = [px16[i] for i in hidx[0]]
        h1 = [px16[i] for i in hidx[1]]
        # individual mode: the halves are independent
        a = _etc_half_search(h0, 4, _etc_candidates(h0, 4), best[0])
        if a is not None:
            b = _etc_half_search(h1, 4, _etc_candidates(h1, 4), best[0] - a[0])
            if b is not None:
                best = (a[0] + b[0], flip, 0, (a[1], b[1]), (a[2], a[3]), (b[2], b[3]))
        # differential mode
        a = _etc_half_search(h0, 5, _etc_candidates(h0, 5), best[0])
        if a is None:
            continue
        b = _etc_half_search(h1, 5, _etc_candidates(h1, 5), best[0])
        if b is None:
            continue
        if all(-4 <= b[1][c] - a[1][c] <= 3 for c in range(3)):
            if a[0] + b[0] < best[0]:
                best = (a[0] + b[0], flip, 1, (a[1], b[1]), (a[2], a[3]), (b[2], b[3]))
            continue
        for first in (True, False):
            keep, other, opix = (a, b, h1) if first else (b, a, h0)
            if keep[0] >= best[0]:
                continue
            qk = keep[1]
            # second = first + d with d in -4..3
            lo = [max(0, qk[c] - (4 if first else 3)) for c in range(3)]
            hi = [min(31, qk[c] + (3 if first else 4)) for c in range(3)]
            qc = [min(hi[c], max(lo[c], other[1][c])) for c in range(3)]
            near = sorted({tuple(min(hi[c], max(lo[c], qc[c] + dd[c])) for c in range(3))
                           for dd in _NEAR})
            o = _etc_half_search(opix, 5, near, best[0] - keep[0], lo, hi)
            if o is None:
                continue
            if first:
                best = (keep[0] + o[0], flip, 1, (keep[1], o[1]), (keep[2], keep[3]), (o[2], o[3]))
            else:
                best = (keep[0] + o[0], flip, 1, (o[1], keep[1]), (o[2], o[3]), (keep[2], keep[3]))
    return best


ETC_QUALITY = "high"  # "fast" = the original simple encoder (several times faster, lower PSNR)


def _etc_encode_block(px16) -> int:
    best = _etc_search_simple(px16) if ETC_QUALITY == "fast" else _etc_search_hq(px16)
    return _etc_pack(*best[1:])


def _etc_encode(rgba: bytes, w: int, h: int, alpha: bool) -> bytes:
    out = bytearray()
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            for bi in range(4):
                bx = tx + (bi & 1) * 4
                by = ty + (bi >> 1) * 4
                px = []
                am = 0
                for i in range(16):
                    x, y = min(bx + (i >> 2), w - 1), min(by + (i & 3), h - 1)
                    o = (((h - 1 - y) if FLIP_Y else y) * w + x) * 4
                    px.append((rgba[o], rgba[o + 1], rgba[o + 2]))
                    am |= ((rgba[o + 3] * 15 + 127) // 255) << (4 * i)  # nearest 4-bit
                if alpha:
                    out += am.to_bytes(8, "little")
                if alpha and am == 0 and ETC_QUALITY != "fast":
                    # fully transparent block: colour is only seen through filtering at
                    # edges, so the quick search is enough (keeps portraits fast)
                    out += _etc_encode_block_simple(px).to_bytes(8, "little")
                else:
                    out += _etc_encode_block(px).to_bytes(8, "little")
    return bytes(out)


# ----------------------------------------------------------------- PNG
def write_png(path: str, w: int, h: int, rgba: bytes, level: int = 6) -> None:
    with open(path, "wb") as fh:
        fh.write(png_bytes(w, h, rgba, level))


def png_bytes(w: int, h: int, rgba: bytes, level: int = 6) -> bytes:
    stride = w * 4
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(bytes(raw), level)) + chunk(b"IEND", b""))


def read_png(path: str) -> tuple[int, int, bytes]:
    with open(path, "rb") as fh:
        return parse_png(fh.read())


def parse_png(d: bytes) -> tuple[int, int, bytes]:
    """8-bit non-interlaced PNG (gray, gray+alpha, RGB, RGBA, palette) -> RGBA8."""
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos = 8
    idat = bytearray()
    plte = b""
    trns = b""
    w = h = depth = ctype = 0
    while pos < len(d):
        ln = struct.unpack_from(">I", d, pos)[0]
        t = d[pos + 4:pos + 8]
        body = d[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if t == b"IHDR":
            w, h, depth, ctype, _c, _f, il = struct.unpack(">IIBBBBB", body)
            if depth != 8 or il != 0:
                raise ValueError("only 8-bit non-interlaced PNGs are supported")
        elif t == b"PLTE":
            plte = body
        elif t == b"tRNS":
            trns = body
        elif t == b"IDAT":
            idat += body
        elif t == b"IEND":
            break
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(bytes(idat))
    stride = w * ch
    out = bytearray(h * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        ft = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if ft == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 255
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ft == 3:
            for i in range(stride):
                left = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        elif ft != 0:
            raise ValueError(f"bad PNG filter {ft}")
        out[y * stride:(y + 1) * stride] = line
        prev = line
    px = bytes(out)
    n = w * h
    if ctype == 6:
        return w, h, px
    if ctype == 2:
        r, g, b = _split(px, 3)
        return w, h, _interleave([r, g, b, FF * n])
    if ctype == 0:
        return w, h, _interleave([px, px, px, FF * n])
    if ctype == 4:
        l, a = _split(px, 2)
        return w, h, _interleave([l, l, l, a])
    pal = [plte[i * 3:i * 3 + 3] + (bytes((trns[i],)) if i < len(trns) else FF) for i in range(len(plte) // 3)]
    return w, h, b"".join(pal[i] for i in px)


# ----------------------------------------------------------------- selftest
def selftest() -> int:
    rnd = random.Random(1)
    bad = 0
    for fmt in range(12):
        for (w, h) in ((8, 8), (64, 32), (16, 128)):
            raw = bytes(rnd.randrange(256) for _ in range(data_size(fmt, w, h)))
            img = decode(fmt, w, h, raw)
            back = encode(fmt, w, h, img)
            png = parse_png(png_bytes(w, h, img))
            ok = back == raw and png == (w, h, img)
            if not ok:
                bad += 1
                print(f"FAIL {FORMAT_NAMES[fmt]} {w}x{h}")
    for fmt in (12, 13):
        w = h = 16
        raw = bytes(rnd.randrange(256) for _ in range(data_size(fmt, w, h)))
        img = decode(fmt, w, h, raw)
        enc = encode(fmt, w, h, img)
        img2 = decode(fmt, w, h, enc)
        err = sum((a - b) ** 2 for a, b in zip(img, img2)) / len(img)
        print(f"{FORMAT_NAMES[fmt]}: re-encode MSE per channel {err:.1f} (lossy by design)")
    # refined ETC1 search: never worse than the simple one, reported error matches the
    # decoded block, deterministic
    worse = wrong = 0
    gain = 0
    for trial in range(400):
        base = [rnd.randrange(256) for _ in range(3)]
        sp = (4, 30, 100)[trial % 3]
        px = [tuple(max(0, min(255, base[c] + rnd.randrange(-sp, sp + 1))) for c in range(3))
              for _ in range(16)]
        hq, simple = _etc_search_hq(px), _etc_search_simple(px)
        dec = _etc_block(_etc_pack(*hq[1:]))
        wrong += sum((a - b) ** 2 for p, q in zip(px, dec) for a, b in zip(p, q)) != hq[0]
        worse += hq[0] > simple[0]
        gain += simple[0] - hq[0]
    w, h = 32, 32
    img = bytes(rnd.randrange(256) for _ in range(w * h * 4))
    det = encode(13, w, h, img) == encode(13, w, h, img)
    ok = not worse and not wrong and det
    print(f"refined ETC1 search: {'PASS' if ok else 'FAIL'} (400 random blocks: worse than simple "
          f"{worse}, error mismatches {wrong}, deterministic {det}; total squared error saved {gain})")
    bad += not ok
    print("non-ETC formats exact" if not bad else f"{bad} failures")
    return 1 if bad else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        sys.exit(selftest())
    print(__doc__)
