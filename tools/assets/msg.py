#!/usr/bin/env python3
"""FE Awakening / Fates message archives (game text) <-> editable UTF-8 text files.

Standard library only. Output goes under extracted/assets/text/ (gitignored): game text
is Nintendo-owned and must never be tracked.

A message archive is an IS .bin container (see isbin.py) with no relocations:
    data region = archive name (Shift-JIS, NUL, zero-padded to 4)
                  then each message as UTF-16LE + U+0000, zero-padded to 4
    labels      = (data offset of message, label name such as MID_xxx)
Archives are recognised by the data region starting with "MESS_ARCHIVE".

Text format (one file per archive, UTF-8, LF):
    #msgarchive 1
    #name "MESS_ARCHIVE_xxx"     archive name (Shift-JIS; quoted like isbin.py names)
    [LABEL]                  one message per label, in label-table order
    text...                  the message on ONE line; escapes: \\n newline, \\r CR,
                             \\\\ backslash, \\uXXXX any other control character
    [LABEL2] = LABEL         alias: LABEL2 shares LABEL's text (same data offset)
Messages are laid out in data order = order of first appearance in the file, so you can
edit text freely (lengths may change) and add/remove entries.

Usage:
    python tools/assets/msg.py dump IN.bin[.lz] OUT.txt
    python tools/assets/msg.py build IN.txt OUT.bin [--like ORIGINAL.bin.lz]
        --like: compress the result the way ORIGINAL is compressed (if it is LZ)
    python tools/assets/msg.py dumpall      every archive -> extracted/assets/text/<path>.txt
    python tools/assets/msg.py test [--jobs N]
        dump -> build every archive in extracted/romfs and compare (decompressed bytes);
        prints the pass rate; failures -> extracted/assets/msg_fail.txt
"""
from __future__ import annotations

import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import isbin  # noqa: E402
import lz  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
ROMFS = os.path.join(ROOT, "extracted", "romfs")
OUT_TEXT = os.path.join(ROOT, "extracted", "assets", "text")
MAGIC = b"MESS_ARCHIVE"


class MsgError(ValueError):
    pass


def is_msg(d: bytes) -> bool:
    return isbin.is_isbin(d) and d[0x20:0x20 + len(MAGIC)] == MAGIC and d[8:12] == b"\0\0\0\0"


def _pad4(b: bytearray) -> None:
    while len(b) % 4:
        b.append(0)


def escape(s: str) -> str:
    out = []
    for ch in s:
        o = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif o < 0x20 or o == 0x7F or 0xD800 <= o <= 0xDFFF:
            out.append(f"\\u{o:04X}")
        else:
            out.append(ch)
    return "".join(out)


def unescape(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        n = s[i + 1:i + 2]
        if n == "n":
            out.append("\n"); i += 2
        elif n == "r":
            out.append("\r"); i += 2
        elif n == "\\":
            out.append("\\"); i += 2
        elif n == "u":
            out.append(chr(int(s[i + 2:i + 6], 16))); i += 6
        else:
            raise MsgError(f"bad escape at {i}: {s[i:i + 6]!r}")
    return "".join(out)


def _utf16(units: bytes) -> str:
    # surrogatepass keeps lone surrogates reversible (written as \\uXXXX)
    return units.decode("utf-16-le", "surrogatepass")


def parse(d: bytes):
    """Return (archive name bytes, [(label bytes, text str or alias label bytes, is_alias)])."""
    if not is_msg(d):
        raise MsgError("not a message archive")
    b = isbin.IsBin.parse(d)
    data = b.data
    e = data.find(b"\0")
    name = data[:e]
    first_at: dict[int, bytes] = {}
    entries = []
    for off, lab, _no in b.labels:
        if off in first_at:
            entries.append((lab, first_at[off], True))
            continue
        first_at[off] = lab
        p = off
        while True:
            if p + 2 > len(data):
                raise MsgError("unterminated message")
            if data[p] == 0 and data[p + 1] == 0:
                break
            p += 2
        entries.append((lab, _utf16(data[off:p]), False))
    return name, entries, b


def build_bytes(name: bytes, entries) -> bytes:
    data = bytearray(name + b"\0")
    _pad4(data)
    offs: dict[bytes, int] = {}
    labels = []
    for lab, val, alias in entries:
        if alias:
            if val not in offs:
                raise MsgError(f"alias target {val!r} not defined before {lab!r}")
            labels.append((offs[val], lab))
            continue
        offs[lab] = len(data)
        labels.append((len(data), lab))
        data += val.encode("utf-16-le", "surrogatepass") + b"\0\0"
        _pad4(data)
    b = isbin.IsBin()
    b.data = bytes(data)
    b.relocs = []
    tab, noffs, _ = isbin.build_pool([lab for _o, lab in labels], [])
    b.strtab = tab
    b.labels = [(o, lab, no) for (o, lab), no in zip(labels, noffs)]
    return b.build()


def to_text(name: bytes, entries) -> str:
    lines = ["#msgarchive 1", "#name " + isbin.quote(name)]
    for lab, val, alias in entries:
        ls = lab.decode("cp932")
        if alias:
            lines.append(f"[{ls}] = {val.decode('cp932')}")
        else:
            lines.append(f"[{ls}]")
            lines.append(escape(val))
    return "\n".join(lines) + "\n"


def from_text(text: str):
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or lines[0].strip() != "#msgarchive 1":
        raise MsgError("missing '#msgarchive 1' header")
    if len(lines) < 2 or not lines[1].startswith("#name "):
        raise MsgError("missing '#name' line")
    name = isbin.unquote(lines[1][6:])
    entries = []
    i = 2
    while i < len(lines):
        ln = lines[i]
        if not ln.startswith("["):
            raise MsgError(f"line {i + 1}: expected [LABEL]")
        close = ln.index("]")
        lab = ln[1:close].encode("cp932")
        rest = ln[close + 1:].strip()
        if rest.startswith("="):
            entries.append((lab, rest[1:].strip().encode("cp932"), True))
            i += 1
            continue
        if i + 1 >= len(lines):
            raise MsgError(f"line {i + 1}: label without text line")
        entries.append((lab, unescape(lines[i + 1]), False))
        i += 2
    return name, entries


def load(path: str) -> bytes:
    with open(path, "rb") as fh:
        d = fh.read()
    if lz.lz_type(d) is not None and (path.lower().endswith(".lz") or d[0] == 0x13):
        d = lz.decompress(d)
    return d


def archives():
    out = []
    for dp, _dn, fn in os.walk(ROMFS):
        for f in fn:
            if f.endswith(".bin.lz") or f.endswith(".bin"):
                out.append(os.path.join(dp, f))
    out.sort()
    return out


def _test_one(path: str):
    try:
        d = load(path)
    except lz.LZError:
        return path, None, ""
    if not is_msg(d):
        return path, None, ""
    try:
        name, entries, _b = parse(d)
        txt = to_text(name, entries)
        n2, e2 = from_text(txt)
        ok = build_bytes(n2, e2) == d
        return path, ok, "" if ok else "rebuild differs"
    except (MsgError, isbin.BinError, UnicodeError, ValueError) as e:
        return path, False, str(e)


def test(jobs: int) -> tuple[int, int]:
    from concurrent.futures import ProcessPoolExecutor
    n = ok = 0
    fails = []
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for path, res, info in ex.map(_test_one, archives(), chunksize=8):
            if res is None:
                continue
            n += 1
            ok += res
            if not res:
                fails.append(f"{os.path.relpath(path, ROMFS)}\t{info}")
    print(f"message archives: {ok}/{n} rebuild byte-identically from text "
          f"({100.0 * ok / max(n, 1):.2f}%)")
    os.makedirs(os.path.join(ROOT, "extracted", "assets"), exist_ok=True)
    with open(os.path.join(ROOT, "extracted", "assets", "msg_fail.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(fails) + "\n")
    return ok, n


def _dump_one(path: str):
    try:
        d = load(path)
    except lz.LZError:
        return 0, 0
    if not is_msg(d):
        return 0, 0
    name, entries, _ = parse(d)
    rel = os.path.relpath(path, ROMFS)
    out = os.path.join(OUT_TEXT, rel + ".txt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(to_text(name, entries))
    return 1, len(entries)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("dump", "build", "dumpall", "test"))
    ap.add_argument("inp", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--like")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    if a.cmd == "test":
        ok, n = test(a.jobs)
        return 0 if ok == n else 1
    if a.cmd == "dumpall":
        from concurrent.futures import ProcessPoolExecutor
        files = msgs = 0
        with ProcessPoolExecutor(max_workers=a.jobs) as ex:
            for f, m in ex.map(_dump_one, archives(), chunksize=8):
                files += f
                msgs += m
        print(f"wrote {files} archives ({msgs} labels) to {OUT_TEXT}")
        return 0
    if not (a.inp and a.out):
        ap.error("need IN and OUT")
    if a.cmd == "dump":
        name, entries, _ = parse(load(a.inp))
        with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(to_text(name, entries))
    else:
        with open(a.inp, encoding="utf-8", newline="") as fh:
            name, entries = from_text(fh.read())
        out = build_bytes(name, entries)
        if a.like:
            with open(a.like, "rb") as fh:
                out = lz.compress_like(out, fh.read())
        with open(a.out, "wb") as fh:
            fh.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
