#!/usr/bin/env python3
"""Nintendo LZ10 / LZ11 / LZ13 (de)compression, with byte-identical recompression.

Standard library only.

Formats
-------
LZ10  ``10 ss ss ss`` + stream. Token: flag byte (MSB first); 1-bit = 2-byte match,
      length (b0>>4)+3, displacement ((b0&15)<<8|b1)+1.
LZ11  ``11 ss ss ss`` (size 0 -> u32 extended size follows) + stream. Match forms:
      b0>>4 == 0: 3 bytes, len 0x11..0x110;   b0>>4 == 1: 4 bytes, len 0x111..0x10110;
      otherwise 2 bytes, len (b0>>4)+1 (3..16). Displacement 1..4096.
LZ13  Intelligent Systems wrapper used by FE Awakening and Fates: ``13 ss ss ss`` followed by a
      complete LZ11 stream. The wrapper size usually equals the LZ11 size; in 853 game
      files it is larger (kept as metadata "outer").

Recompression
-------------
The game's compressor was identified by measurement (`--survey`): greedy parsing, the
longest match at every position, ties broken toward the FARTHEST source in the
4096-byte window, and never displacement 1 ("VRAM-safe": minimum displacement 2).
That is `parse="greedy-far"` (the default) and it reproduces 100% of the RomFS LZ
files. Other parsers (greedy-near, lazy-far/near, optimal, "-d1" variants) exist to
show the claim is specific. Per-file facts a rebuild needs besides the data come from
`meta()`: the format byte, the LZ13 outer size when it differs, and trailing bytes after
the stream (74 files carry 1-3 zero bytes). `roundtrip()` says whether recompression is
identical; callers keep the original file as a blob otherwise.

Usage
-----
    python tools/assets/lz.py d IN OUT           decompress (format from header)
    python tools/assets/lz.py c IN OUT [--fmt 13] [--parse greedy-far]
    python tools/assets/lz.py --survey [--jobs N] [--parse greedy-far,greedy-near,...]
        recompress every LZ file under extracted/romfs/ and print the identical rate
        per parser and per format; files the FIRST parser misses go to
        extracted/assets/lz_mismatch.txt.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ROMFS = os.path.join(ROOT, "extracted", "romfs")
WINDOW = 0x1000


class LZError(ValueError):
    pass


def lz_type(data: bytes) -> int | None:
    """Return 0x10/0x11/0x13 if `data` looks like a Nintendo LZ stream, else None."""
    if len(data) < 4 or data[0] not in (0x10, 0x11, 0x13):
        return None
    if data[0] == 0x13:
        if len(data) < 8 or data[4] != 0x11:
            return None
    return data[0]


def _header(data: bytes, pos: int) -> tuple[int, int]:
    size = data[pos + 1] | data[pos + 2] << 8 | data[pos + 3] << 16
    pos += 4
    if size == 0:
        size = struct.unpack_from("<I", data, pos)[0]
        pos += 4
    return size, pos


def decompress_tokens(data: bytes, want_tokens: bool = False):
    """Decompress; raises LZError on any malformed input. See _decompress_tokens."""
    try:
        return _decompress_tokens(data, want_tokens)
    except (IndexError, struct.error) as e:
        raise LZError(f"malformed stream: {e}") from None


def _decompress_tokens(data: bytes, want_tokens: bool = False):
    """Decompress; returns (out, end_pos, tokens). tokens: list of int (literal byte)
    or (length, disp) tuples, only when want_tokens."""
    kind = lz_type(data)
    if kind is None:
        raise LZError("not an LZ10/11/13 stream")
    pos = 0
    outer = None
    if kind == 0x13:
        outer, _ = _header(data, 0)
        pos = 4
        kind = 0x11
    size, pos = _header(data, pos)
    out = bytearray()
    toks = [] if want_tokens else None
    n = len(data)
    while len(out) < size:
        if pos >= n:
            raise LZError("truncated stream")
        flags = data[pos]
        pos += 1
        for bit in range(7, -1, -1):
            if len(out) >= size:
                break
            if not (flags >> bit) & 1:
                out.append(data[pos])
                if toks is not None:
                    toks.append(data[pos])
                pos += 1
                continue
            b0 = data[pos]
            if kind == 0x10:
                ln = (b0 >> 4) + 3
                disp = ((b0 & 15) << 8 | data[pos + 1]) + 1
                pos += 2
            else:
                ind = b0 >> 4
                if ind == 0:
                    ln = ((b0 & 15) << 4 | data[pos + 1] >> 4) + 0x11
                    disp = ((data[pos + 1] & 15) << 8 | data[pos + 2]) + 1
                    pos += 3
                elif ind == 1:
                    ln = ((b0 & 15) << 12 | data[pos + 1] << 4 | data[pos + 2] >> 4) + 0x111
                    disp = ((data[pos + 2] & 15) << 8 | data[pos + 3]) + 1
                    pos += 4
                else:
                    ln = ind + 1
                    disp = ((b0 & 15) << 8 | data[pos + 1]) + 1
                    pos += 2
            src = len(out) - disp
            if src < 0:
                raise LZError("displacement before start of output")
            if toks is not None:
                toks.append((ln, disp))
            if disp >= ln:
                out += out[src:src + ln]
            else:
                for i in range(ln):
                    out.append(out[src + i])
    if len(out) != size:
        raise LZError("stream overruns its declared size")
    return bytes(out), pos, toks


def decompress(data: bytes) -> bytes:
    return decompress_tokens(data)[0]


# --------------------------------------------------------------------- parsers
def _longest(data: bytes, pos: int, max_len: int, min_disp: int, far: bool) -> tuple[int, int]:
    """Longest match at pos (len >= 3) within the window; ties -> nearest (or farthest).
    Uses C-speed bytes.find/rfind on growing needles."""
    n = len(data)
    lim = min(max_len, n - pos)
    if lim < 3:
        return 0, 0
    lo = max(0, pos - WINDOW)
    hi_start = pos - min_disp  # last allowed source start
    if hi_start < lo:
        return 0, 0
    best_len = 0
    ln = 3
    finder = data.find if far else data.rfind
    cap = min(lim, NEEDLE_CAP)
    # Phase 1: grow the needle (C-speed search), extending each hit by comparison.
    while ln <= cap:
        s = finder(data[pos:pos + ln], lo, hi_start + ln)
        if s < 0:
            break
        best_len = _matchlen(data, s, pos, ln, lim)
        ln = best_len + 1
    if best_len < 3:
        return 0, 0
    if best_len < NEEDLE_CAP:
        # Nearest (or farthest) source among those reaching best_len.
        s = finder(data[pos:pos + best_len], lo, hi_start + best_len)
        return best_len, pos - s
    # Phase 2: long match. Enumerate every source sharing the capped prefix.
    needle = data[pos:pos + NEEDLE_CAP]
    best_len = 0
    best_src = -1
    if far:
        start = lo
        while True:
            s = data.find(needle, start, hi_start + NEEDLE_CAP)
            if s < 0:
                break
            e = _matchlen(data, s, pos, NEEDLE_CAP, lim)
            if e > best_len:
                best_len, best_src = e, s
                if e == lim:
                    break
            start = s + 1
    else:
        end = hi_start + NEEDLE_CAP
        while True:
            s = data.rfind(needle, lo, end)
            if s < 0:
                break
            e = _matchlen(data, s, pos, NEEDLE_CAP, lim)
            if e > best_len:
                best_len, best_src = e, s
                if e == lim:
                    break
            end = s + NEEDLE_CAP - 1
    return best_len, pos - best_src


# CPython 3.13.14 on Windows was seen to crash (access violation) inside bytes.rfind with
# needles of ~590 bytes; needles are kept short and long matches extended by slice compares.
NEEDLE_CAP = 64


def _matchlen(data: bytes, s: int, pos: int, known: int, lim: int) -> int:
    """Length of the common run data[s:] vs data[pos:], at least `known`, at most `lim`."""
    k = known
    step = 16
    while k < lim:
        m = min(step, lim - k)
        if data[s + k:s + k + m] == data[pos + k:pos + k + m]:
            k += m
            step <<= 1
        elif m == 1:
            break
        else:
            step = max(1, m >> 1)
    return k


def parse_greedy(data: bytes, max_len: int, min_disp: int = 1, far: bool = False):
    toks = []
    pos = 0
    n = len(data)
    while pos < n:
        ln, disp = _longest(data, pos, max_len, min_disp, far)
        if ln >= 3:
            toks.append((ln, disp))
            pos += ln
        else:
            toks.append(data[pos])
            pos += 1
    return toks


def parse_lazy(data: bytes, max_len: int, min_disp: int = 1, far: bool = True):
    """One-step lazy matching (zlib style): emit a literal if the next position has a
    strictly longer match."""
    toks = []
    pos = 0
    n = len(data)
    nxt = None
    while pos < n:
        cur = nxt if nxt is not None else _longest(data, pos, max_len, min_disp, far)
        nxt = None
        if cur[0] >= 3 and pos + 1 < n:
            nm = _longest(data, pos + 1, max_len, min_disp, far)
            if nm[0] > cur[0]:
                toks.append(data[pos])
                pos += 1
                nxt = nm
                continue
        if cur[0] >= 3:
            toks.append(cur)
            pos += cur[0]
        else:
            toks.append(data[pos])
            pos += 1
    return toks


def _cost11(ln: int) -> int:
    return 17 if ln <= 16 else (25 if ln <= 0x110 else 33)  # bits incl. flag bit


def parse_optimal(data: bytes, max_len: int, min_disp: int = 1, fmt: int = 0x11):
    """Minimum-size parse (shortest path over positions, nearest source for each length
    taken from the longest match, which is a superset for all shorter lengths)."""
    n = len(data)
    INF = 1 << 60
    cost = [INF] * (n + 1)
    cost[n] = 0
    choice = [None] * (n + 1)
    matches = [_longest(data, p, max_len, min_disp, False) for p in range(n)]
    for p in range(n - 1, -1, -1):
        best = cost[p + 1] + 9
        ch = None
        ml, md = matches[p]
        if ml >= 3:
            for ln in range(3, ml + 1):
                c = (17 if fmt == 0x10 else _cost11(ln)) + cost[p + ln]
                if c <= best:
                    best = c
                    ch = (ln, md)
        cost[p] = best
        choice[p] = ch
    toks = []
    p = 0
    while p < n:
        ch = choice[p]
        if ch is None:
            toks.append(data[p])
            p += 1
        else:
            toks.append(ch)
            p += ch[0]
    return toks


PARSERS = ("greedy-far", "greedy-near", "lazy-far", "lazy-near", "optimal")
DEFAULT_PARSE = "greedy-far"


def encode(toks, size: int, fmt: int, outer: int | None = None, tail: bytes = b"") -> bytes:
    """Serialize a token list. `outer` is the LZ13 wrapper's size field (defaults to
    `size`); `tail` is appended verbatim after the stream (originals have none or a few
    pad bytes; recorded per file by `meta()`)."""
    out = bytearray()
    if fmt == 0x13:
        o = size if outer is None else outer
        out += bytes((0x13, o & 255, o >> 8 & 255, o >> 16 & 255))
        inner = 0x11
    else:
        inner = fmt
    if size < 0x1000000:
        out += bytes((inner, size & 255, size >> 8 & 255, size >> 16 & 255))
    else:
        out += bytes((inner, 0, 0, 0)) + struct.pack("<I", size)
    i = 0
    nt = len(toks)
    while i < nt:
        flag_pos = len(out)
        out.append(0)
        flags = 0
        for bit in range(7, -1, -1):
            if i >= nt:
                break
            t = toks[i]
            i += 1
            if isinstance(t, int):
                out.append(t)
                continue
            flags |= 1 << bit
            ln, disp = t
            d = disp - 1
            if inner == 0x10:
                out += bytes(((ln - 3) << 4 | d >> 8, d & 255))
            elif ln <= 16:
                out += bytes(((ln - 1) << 4 | d >> 8, d & 255))
            elif ln <= 0x110:
                l2 = ln - 0x11
                out += bytes((l2 >> 4, (l2 & 15) << 4 | d >> 8, d & 255))
            else:
                l2 = ln - 0x111
                out += bytes((0x10 | l2 >> 12, l2 >> 4 & 255, (l2 & 15) << 4 | d >> 8, d & 255))
        out[flag_pos] = flags
    out += tail
    return bytes(out)


def tokenize(data: bytes, fmt: int = 0x13, parse: str = DEFAULT_PARSE):
    """parse: greedy-far | greedy-near | lazy-far | lazy-near | optimal, optionally
    suffixed "-d1" to allow displacement 1 (the game files never use it: their
    compressor is "VRAM-safe", minimum displacement 2)."""
    max_len = 18 if fmt == 0x10 else 0x10110
    min_disp = 2
    base = parse
    if parse.endswith("-d1"):
        min_disp = 1
        base = parse[:-3]
    if base in ("greedy-far", "greedy-near"):
        return parse_greedy(data, max_len, min_disp, far=base.endswith("far"))
    if base in ("lazy-far", "lazy-near"):
        return parse_lazy(data, max_len, min_disp, far=base.endswith("far"))
    if base == "optimal":
        return parse_optimal(data, max_len, min_disp, fmt=0x10 if fmt == 0x10 else 0x11)
    raise ValueError(f"unknown parse {parse!r}; choose from {PARSERS} (+ optional -d1)")


def compress(data: bytes, fmt: int = 0x13, parse: str = DEFAULT_PARSE,
             outer: int | None = None, tail: bytes = b"") -> bytes:
    return encode(tokenize(data, fmt, parse), len(data), fmt, outer, tail)


def meta(orig: bytes) -> dict:
    """Header facts a byte-identical rebuild needs besides the decompressed data."""
    dec, end, _ = decompress_tokens(orig)
    m = {"fmt": orig[0]}
    if orig[0] == 0x13:
        outer = orig[1] | orig[2] << 8 | orig[3] << 16
        if outer != len(dec):
            m["outer"] = outer
    if end != len(orig):
        m["tail"] = orig[end:].hex()
    return m


def compress_meta(data: bytes, m: dict, parse: str = DEFAULT_PARSE) -> bytes:
    return compress(data, m["fmt"], parse, m.get("outer"), bytes.fromhex(m.get("tail", "")))


def compress_like(data: bytes, orig: bytes, parse: str = DEFAULT_PARSE) -> bytes:
    """Compress `data` the way the original file `orig` was compressed. If `orig` is not
    LZ, return `data` unchanged. Header extras (LZ13 outer size, trailing bytes) are kept
    only when the data is unchanged, since they describe the original contents."""
    if lz_type(orig) is None:
        return data
    m = meta(orig)
    if decompress(orig) != data:
        m = {"fmt": m["fmt"]}
    return compress_meta(data, m, parse)


def roundtrip(orig: bytes, parse: str = DEFAULT_PARSE) -> tuple[bytes, bool]:
    """Decompress then recompress; returns (decompressed, identical?)."""
    dec = decompress(orig)
    return dec, compress_meta(dec, meta(orig), parse) == orig


# ----------------------------------------------------------------------- survey
def lz_files(root: str = ROMFS):
    out = []
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            p = os.path.join(dp, f)
            with open(p, "rb") as fh:
                head = fh.read(8)
            if lz_type(head) is not None and (f.lower().endswith(".lz") or head[0] == 0x13):
                out.append(p)
    out.sort()
    return out


def _survey_one(args):
    path, parses = args
    with open(path, "rb") as fh:
        orig = fh.read()
    res = {"path": path, "fmt": orig[0], "csize": len(orig)}
    try:
        dec, end, _ = decompress_tokens(orig)
    except LZError as e:
        res["error"] = str(e)
        return res
    res["dsize"] = len(dec)
    res["tail"] = orig[end:]
    m = meta(orig)
    res["outer"] = "outer" in m
    res["ok"] = {}
    for p in parses:
        if p == "optimal" and len(dec) > 400_000:
            res["ok"][p] = None  # too slow in pure Python; skipped
            continue
        res["ok"][p] = compress_meta(dec, m, p) == orig
    return res


def survey(jobs: int, parses: list[str]) -> dict:
    """Returns {format byte: {parser: [identical, tried]}} (+ "errors" if any)."""
    from concurrent.futures import ProcessPoolExecutor
    files = lz_files()
    print(f"{len(files)} LZ files under extracted/romfs")
    stats: dict = {}
    mism = []
    errors = 0
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for r in ex.map(_survey_one, [(f, parses) for f in files], chunksize=4):
            fmt = r["fmt"]
            if "error" in r:
                errors += 1
                mism.append(f"ERROR {r['error']}\t{os.path.relpath(r['path'], ROMFS)}")
                continue
            st = stats.setdefault(fmt, {"n": 0, "c": 0, "d": 0, "padnz": 0, "tail": 0, "outer": 0, **{p: [0, 0] for p in parses}})
            st["n"] += 1
            st["c"] += r["csize"]
            st["d"] += r["dsize"]
            st["tail"] += bool(r["tail"])
            st["outer"] += r["outer"]
            if r["tail"].strip(b"\0") or len(r["tail"]) > 3:
                st["padnz"] += 1
            for p in parses:
                v = r["ok"][p]
                if v is None:
                    continue
                st[p][1] += 1
                st[p][0] += v
            if not r["ok"].get(parses[0]):
                mism.append(os.path.relpath(r["path"], ROMFS).replace(os.sep, "/"))
    for fmt, st in sorted(stats.items()):
        print(f"LZ{fmt:02X}: {st['n']} files, {st['c']:,} -> {st['d']:,} bytes; "
              f"with trailing bytes: {st['tail']} (non-zero or >3: {st['padnz']}); "
              f"LZ13 outer size != data size: {st['outer']}")
        for p in parses:
            ok, tried = st[p]
            pct = 100.0 * ok / tried if tried else 0.0
            print(f"   {p:<11} {ok}/{tried} identical ({pct:.2f}%)")
    print(f"decode errors: {errors}")
    os.makedirs(os.path.join(ROOT, "extracted", "assets"), exist_ok=True)
    with open(os.path.join(ROOT, "extracted", "assets", "lz_mismatch.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(mism) + "\n")
    res: dict = {fmt: {p: st[p] for p in parses} for fmt, st in stats.items()}
    if errors:
        res["errors"] = errors
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=("d", "c"))
    ap.add_argument("inp", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--fmt", default="13")
    ap.add_argument("--parse", default=DEFAULT_PARSE)
    ap.add_argument("--survey", action="store_true")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    if a.survey:
        first = a.parse.split(",")[0]
        res = survey(a.jobs, a.parse.split(","))
        return 0 if all(v[first][0] == v[first][1] for k, v in res.items() if k != "errors") else 1
    if not (a.cmd and a.inp and a.out):
        ap.error("need d|c IN OUT, or --survey")
    with open(a.inp, "rb") as fh:
        data = fh.read()
    res = decompress(data) if a.cmd == "d" else compress(data, int(a.fmt, 16), a.parse)
    with open(a.out, "wb") as fh:
        fh.write(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
