#!/usr/bin/env python3
"""BLZ ("bottom LZ", backwards LZ77) codec for the 3DS ExeFS `.code` file. Stdlib only.

The encoder reproduces the parse and the byte layout of CUE's `blz.c` in its normal
(non "-best") mode, with one change to the raw-prefix cut test (a tie at the very end
prefers no raw prefix; cut="end"). That variant recompresses the retail decompressed
code.bin of both Awakening and Fates byte-identically
(see docs/ROM_REBUILD.md). This is a clean reimplementation from the format description,
not a copy of CUE's code.

Format (all little-endian; the stream is processed from the END of the file backwards):
    [raw prefix, stored as-is][compressed body][0xFF padding to 4][footer, 8 bytes]
    footer u32 #0: bits 0-23 = body + padding + footer length, bits 24-31 = padding + 8
    footer u32 #1: decompressed size minus compressed size
Inside the body, read backwards: a flag byte (MSB first), then per flag bit either a
literal byte (0) or a 2-byte match (1): u16 = ((len-3) << 12) | (disp-3),
len 3..18, disp 3..0x1002, no overlap (len <= disp) in the CUE encoder.

Encoder parse (CUE normal mode), in the reversed buffer:
    at each position take the longest match (max 18, min 3), ties broken by the
    SMALLEST displacement; else a literal. Greedy, no lookahead.
    The raw prefix is the cut point where (compressed so far + remaining raw) is minimal;
    retail needs the FIRST minimal point, but "everything compressed" wins a tie
    (compress(cut="end"), the default; checked on Awakening and Fates).

Usage:
    python tools/rom/blz.py decompress IN OUT
    python tools/rom/blz.py compress IN OUT [--best] [--cut=end|le|lt|none]
    python tools/rom/blz.py selftest [CODE_BIN] [COMPRESSED] [--best]
        default: extracted/code.bin and extracted/rom/p0/exefs/code.bin (from
        tools/rom/extract.py); recompresses with every cut rule (and CUE "-best" with
        --best), reports which are byte-identical and, if not, the first differing token.
        Exit 0 iff the default variant (normal, cut=end) is byte-identical.
"""
from __future__ import annotations

import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

BLZ_N = 0x1002       # max displacement
BLZ_F = 18           # max match length
BLZ_THRESHOLD = 2    # matches must be longer than this


class BLZError(ValueError):
    pass


# --------------------------------------------------------------------------- decode
def decompress(comp: bytes, tokens: list | None = None) -> bytes:
    """Decompress a BLZ blob. If `tokens` is a list, append (len, disp) per token
    (literals as (1, 0)) in stream order, for parse comparisons."""
    if len(comp) < 8:
        raise BLZError("compressed data too small")
    top, extra = struct.unpack_from("<II", comp, len(comp) - 8)
    if extra == 0:
        # Stored uncompressed by CUE: data, zero pad to 4, u32 0 (true length is lost).
        return bytes(comp[:-4])
    hdr = top >> 24
    enc = top & 0xFFFFFF
    if hdr < 8 or enc > len(comp) or hdr > enc:
        raise BLZError("bad BLZ footer")
    out = bytearray(comp)
    out += bytes(extra)
    src = len(comp) - hdr
    end = len(comp) - enc
    dst = len(out)
    while src > end:
        src -= 1
        flags = out[src]
        for _ in range(8):
            if flags & 0x80:
                src -= 2
                info = out[src] | (out[src + 1] << 8)
                n = (info >> 12) + 3
                d = (info & 0xFFF) + 3
                if dst - n < end or dst + d > len(out):
                    raise BLZError("BLZ match out of range")
                for _ in range(n):
                    dst -= 1
                    out[dst] = out[dst + d]
                if tokens is not None:
                    tokens.append((n, d))
            else:
                src -= 1
                dst -= 1
                out[dst] = out[src]
                if tokens is not None:
                    tokens.append((1, 0))
            flags = (flags << 1) & 0xFF
            if src <= end:
                break
    if dst != end:
        raise BLZError(f"BLZ decode misaligned (dst=0x{dst:X}, expected 0x{end:X})")
    return bytes(out)


# --------------------------------------------------------------------------- encode
def _searcher(rbuf: bytes):
    """Return search(i) -> (len, disp) equal to CUE's SEARCH macro on reversed data:
    smallest disp among the longest non-overlapping matches, len in 3..18, else (0, 0).

    Implemented with bytes.rfind: the nearest occurrence of rbuf[i:i+L] that ends at or
    before i is exactly the smallest disp reaching length >= L (CUE caps len at disp)."""
    n = len(rbuf)
    rfind = rbuf.rfind

    def search(i: int) -> tuple[int, int]:
        if n - i < 3:
            return 0, 0
        lo = i - BLZ_N if i > BLZ_N else 0
        j = rfind(rbuf[i:i + 3], lo, i)
        if j < 0:
            return 0, 0
        length = 3
        mx = n - i if n - i < BLZ_F else BLZ_F
        while length < mx:
            hi = j + length + 1
            k = rfind(rbuf[i:i + length + 1], lo, hi if hi < i else i)
            if k < 0:
                break
            j = k
            length += 1
        return length, i - j

    return search


CUT_MODES = ("end", "le", "lt", "none")


def compress(raw: bytes, best: bool = False, cut: str = "end") -> bytes:
    """BLZ-compress like CUE blz.c (`-en`; `best=True` emulates `-eo`).

    `cut` picks the rule for the raw (uncompressed) prefix:
      "end"  (default) the FIRST position where compressed-so-far + raw-remaining is
             minimal (strict `<`), except that compressing everything (the state after
             the last token) wins a tie (`<=`). The only rule found that reproduces BOTH
             retail `.code` files: Fates (minimal at 17 points, retail keeps the first,
             a 161-byte raw prefix) and Awakening (minimal at raw 1 and raw 0, retail
             keeps raw 0). See docs/ROM_REBUILD.md.
      "le"   keep the LAST minimal position (`<=`). Reproduces Awakening, not Fates
             (72 bytes differ: a 78-byte raw prefix instead of 161).
      "lt"   keep the FIRST minimal position (CUE's published `<` test, as far as we
             know). Reproduces Fates; on Awakening it stores byte 0 raw (footer differs).
      "none" never store a raw prefix (always matches "le" when the end is minimal)."""
    if cut not in CUT_MODES:
        raise ValueError(f"cut must be one of {CUT_MODES}")
    raw_len = len(raw)
    rbuf = raw[::-1]
    search = _searcher(rbuf)
    pak = bytearray()
    pak_tmp = 0
    raw_tmp = raw_len
    i = 0
    mask = 0
    flg = 0
    while i < raw_len:
        mask >>= 1
        if not mask:
            flg = len(pak)
            pak.append(0)
            mask = 0x80
        n, d = search(i)
        if best and n > BLZ_THRESHOLD and i + n < raw_len:
            n_next, _ = search(i + n)
            n_post, _ = search(i + 1)
            if n_next <= BLZ_THRESHOLD:
                n_next = 1
            if n_post <= BLZ_THRESHOLD:
                n_post = 1
            if n + n_next <= 1 + n_post:
                n = 1
        pak[flg] = (pak[flg] << 1) & 0xFF
        if n > BLZ_THRESHOLD:
            i += n
            pak[flg] |= 1
            pak.append(((n - (BLZ_THRESHOLD + 1)) << 4) | ((d - 3) >> 8))
            pak.append((d - 3) & 0xFF)
        else:
            pak.append(rbuf[i])
            i += 1
        total = len(pak) + raw_len - i
        if cut == "none" or total < pak_tmp + raw_tmp or (total == pak_tmp + raw_tmp and (
                cut == "le" or (cut == "end" and i >= raw_len))):
            pak_tmp = len(pak)
            raw_tmp = raw_len - i
    while mask and mask != 1:
        mask >>= 1
        pak[flg] = (pak[flg] << 1) & 0xFF

    if not pak_tmp or raw_len + 4 < ((pak_tmp + raw_tmp + 3) & ~3) + 8:
        out = bytearray(raw)
        while len(out) & 3:
            out.append(0)
        out += bytes(4)
        return bytes(out)

    out = bytearray(raw[:raw_tmp])
    out += pak[:pak_tmp][::-1]
    hdr_len = 8
    while len(out) & 3:
        out.append(0xFF)
        hdr_len += 1
    enc_len = pak_tmp
    inc_len = raw_len - pak_tmp - raw_tmp
    out += struct.pack("<II", ((enc_len + hdr_len) & 0xFFFFFF) | (hdr_len << 24), inc_len - hdr_len)
    return bytes(out)


def inplace_margin(comp: bytes) -> int:
    """Smallest (unread compressed bytes - undecoded output bytes) seen while decoding
    `comp` in place (the 3DS loader decompresses .code inside its own buffer). A value
    >= 0 means the writer never overtakes the reader, i.e. in-place decoding is safe."""
    top, extra = struct.unpack_from("<II", comp, len(comp) - 8)
    if extra == 0:
        return 0
    hdr = top >> 24
    end = len(comp) - (top & 0xFFFFFF)
    src = len(comp) - hdr
    dst = len(comp) + extra
    worst = 1 << 62
    while src > end:
        src -= 1
        flags = comp[src]
        for _ in range(8):
            if flags & 0x80:
                src -= 2
                dst -= (comp[src + 1] >> 4) + 3
            else:
                src -= 1
                dst -= 1
            # Bytes still to read live in [end, src); output writes land at >= dst.
            if dst - src < worst:
                worst = dst - src
            flags = (flags << 1) & 0xFF
            if src <= end:
                break
    return worst


# ----------------------------------------------------------------------------- CLI
def _first_token_diff(mine: bytes, orig: bytes) -> str:
    a: list = []
    b: list = []
    decompress(mine, a)
    decompress(orig, b)
    k = next((x for x in range(min(len(a), len(b))) if a[x] != b[x]), None)
    if k is None:
        return f"token streams agree on the first {min(len(a), len(b))} tokens ({len(a)} vs {len(b)})"
    return f"first differing token #{k}: mine {a[k]} vs original {b[k]}"


def _selftest(code_path: Path, comp_path: Path, with_best: bool) -> int:
    raw = code_path.read_bytes()
    orig = comp_path.read_bytes()
    t = time.time()
    dec = decompress(orig)
    print(f"decompress original: {'OK' if dec == raw else 'MISMATCH'} ({time.time() - t:.1f}s), "
          f"in-place margin {inplace_margin(orig)}")
    rc = 1
    variants = [(False, c) for c in CUT_MODES] + ([(True, "end")] if with_best else [])
    for best, cut in variants:
        t = time.time()
        mine = compress(raw, best, cut)
        dt = time.time() - t
        same = mine == orig
        nd = sum(1 for x, y in zip(mine, orig) if x != y) + abs(len(mine) - len(orig))
        try:
            rt = "OK" if decompress(mine) == raw else "FAIL"
        except BLZError as e:  # the "-best" emulation is research only; report, go on
            rt = f"FAIL ({e})"
        print(f"compress {'best' if best else 'normal'}/cut={cut}: {len(mine)} bytes vs {len(orig)}, "
              f"{'BYTE-IDENTICAL' if same else f'{nd} bytes differ'} ({dt:.1f}s); "
              f"roundtrip {rt}")
        if same:
            if not best and cut == "end":
                rc = 0
        else:
            try:
                print("  " + _first_token_diff(mine, orig))
            except BLZError as e:
                print(f"  token diff unavailable: {e}")
    return rc


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    cut = next((f.split("=", 1)[1] for f in flags if f.startswith("--cut=")), "end")
    if cmd == "decompress" and len(args) == 2:
        Path(args[1]).write_bytes(decompress(Path(args[0]).read_bytes()))
        return 0
    if cmd == "compress" and len(args) == 2:
        Path(args[1]).write_bytes(compress(Path(args[0]).read_bytes(), "--best" in flags, cut))
        return 0
    if cmd == "selftest":
        code = Path(args[0]) if len(args) > 0 else ROOT / "extracted" / "code.bin"
        comp = Path(args[1]) if len(args) > 1 else ROOT / "extracted" / "rom" / "p0" / "exefs" / "code.bin"
        return _selftest(code, comp, "--best" in flags)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
