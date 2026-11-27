#!/usr/bin/env python3
"""Survey every RomFS file: tree shape, extensions, sizes, magics, compression, containers.

Standard library only. Reads extracted/romfs/ (run tools/assets/romfs.py first) and
prints counts/types only; the same report is written to extracted/assets/survey.txt.
docs/ASSETS.md summarizes it (no file contents, no game text).

Usage:
    python tools/assets/survey.py [--jobs N]
"""
from __future__ import annotations

import argparse
import io
import os
import struct
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import arc  # noqa: E402
import isbin  # noqa: E402
import lz  # noqa: E402
import msg  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
ROMFS = os.path.join(ROOT, "extracted", "romfs")
TEXT_MAGICS = {b"CTPK", b"CGFX", b"CSTM", b"CSAR", b"DVLB", b"cmb\0", b"CFNT", b"BCH\0",
               b"CWAV", b"CBMD", b"SARC", b"FFNT", b"CLIM", b"CFNU"}


def unwrap_stored(raw: bytes) -> bytes | None:
    """Fates' "stored" wrapper (bch.py): 00 + u24 size + the raw bytes. None if not."""
    if len(raw) >= 8 and raw[0] == 0 and (raw[1] | raw[2] << 8 | raw[3] << 16) == len(raw) - 4 \
            and raw[4:8] in TEXT_MAGICS:
        return raw[4:]
    return None


def ext_of(name: str) -> str:
    return "." + name.split(".", 1)[1].lower() if "." in name else "(none)"


def classify(d: bytes) -> str:
    m = d[:4]
    if m in TEXT_MAGICS:
        return m.rstrip(b"\0").decode()
    if m == b"L2\xaa\xab":
        return "MOFLEX"
    if m == b"\xd0\xcf\x11\xe0":
        return "OLE2 (Thumbs.db)"
    if msg.is_msg(d):
        return "IS .bin: message archive"
    if isbin.is_isbin(d):
        if arc.is_arc(d):
            return "IS .bin: .arc archive"
        return "IS .bin: data"
    if d[:4] == b"SMDH":
        return "SMDH icon"
    try:
        d[:64].decode("ascii")
        if all(32 <= c < 127 or c in (9, 10, 13) for c in d[:64]):
            return "text"
    except UnicodeError:
        pass
    return "other/raw"


def _one(path: str):
    with open(path, "rb") as fh:
        raw = fh.read()
    rel = os.path.relpath(path, ROMFS).replace(os.sep, "/")
    r = {"rel": rel, "ext": ext_of(os.path.basename(path)), "size": len(raw),
         "lz": None, "dsize": len(raw), "kind": "", "members": []}
    d = raw
    t = lz.lz_type(raw)
    st = unwrap_stored(raw)
    if st is not None:
        d = st
        r["lz"] = "stored"
        r["dsize"] = len(d)
    elif t is not None and (rel.endswith(".lz") or t == 0x13):
        try:
            d = lz.decompress(raw)
            r["lz"] = t
            r["dsize"] = len(d)
        except lz.LZError:
            r["lz"] = "bad"
    r["kind"] = classify(d)
    if r["kind"] == "IS .bin: .arc archive":
        for m in arc.parse(d):
            md = m["data"]
            mt = lz.lz_type(md)
            if mt is not None:
                try:
                    md = lz.decompress(md)
                except lz.LZError:
                    mt = "bad"
            r["members"].append((ext_of(m["name"].decode("cp932", "replace")), mt, classify(md)))
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    from concurrent.futures import ProcessPoolExecutor
    files = []
    dirs = set()
    for dp, dn, fn in os.walk(ROMFS):
        rel = os.path.relpath(dp, ROMFS).replace(os.sep, "/")
        dirs.add(rel)
        for f in fn:
            files.append(os.path.join(dp, f))
    files.sort()
    if not files:
        sys.exit("extracted/romfs is empty; run tools/assets/romfs.py first")
    by_ext = defaultdict(lambda: [0, 0, 0])
    by_top = defaultdict(lambda: [0, 0])
    kinds = Counter()
    kind_bytes = Counter()
    comp = Counter()
    ext_kind = Counter()
    mem = Counter()
    nonascii = 0
    depth = Counter()
    total = dtotal = 0
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        for r in ex.map(_one, files, chunksize=8):
            e = by_ext[r["ext"]]
            e[0] += 1
            e[1] += r["size"]
            e[2] += r["dsize"]
            top = r["rel"].split("/")[0] if "/" in r["rel"] else "(root)"
            by_top[top][0] += 1
            by_top[top][1] += r["size"]
            kinds[r["kind"]] += 1
            kind_bytes[r["kind"]] += r["dsize"]
            comp[{None: "none", 0x10: "LZ10", 0x11: "LZ11", 0x13: "LZ13", "bad": "bad", "stored": "stored"}[r["lz"]]] += 1
            ext_kind[(r["ext"], r["lz"] is not None, r["kind"])] += 1
            for me, mt, mk in r["members"]:
                mem[(me, {None: "raw", 0x11: "LZ11", 0x13: "LZ13", 0x10: "LZ10", "bad": "bad", "stored": "stored"}[mt], mk)] += 1
            if any(ord(c) > 127 for c in r["rel"]):
                nonascii += 1
            depth[r["rel"].count("/")] += 1
            total += r["size"]
            dtotal += r["dsize"]
    out = io.StringIO()
    p = lambda *x: print(*x, file=out)  # noqa: E731
    p(f"RomFS: {len(files)} files, {len(dirs)} directories (incl. root), {total:,} bytes "
      f"({dtotal:,} after LZ decompression)")
    p(f"paths with non-ASCII (Japanese) names: {nonascii}; files by depth: "
      + ", ".join(f"{k}:{v}" for k, v in sorted(depth.items())))
    p("compression: " + ", ".join(f"{k}={v}" for k, v in comp.most_common()))
    p("\ntop-level directories (files, bytes):")
    for k, (n, s) in sorted(by_top.items(), key=lambda x: -x[1][1]):
        p(f"  {k:<16} {n:>5} {s:>13,}")
    p("\nextensions (files, stored bytes, decompressed bytes):")
    for k, (n, s, ds) in sorted(by_ext.items(), key=lambda x: -x[1][0]):
        p(f"  {k:<12} {n:>5} {s:>13,} {ds:>13,}")
    p("\ncontent kinds (after decompression):")
    for k, n in kinds.most_common():
        p(f"  {k:<28} {n:>5} {kind_bytes[k]:>13,}")
    p("\nextension x compressed x kind:")
    for (e, c, k), n in sorted(ext_kind.items(), key=lambda x: -x[1]):
        p(f"  {e:<12} {'lz ' if c else 'raw'} {k:<28} {n:>5}")
    p("\n.arc members (member extension, compression, kind):")
    for (e, c, k), n in sorted(mem.items(), key=lambda x: -x[1]):
        p(f"  {e:<12} {c:<5} {k:<28} {n:>5}")
    text = out.getvalue()
    sys.stdout.write(text)
    os.makedirs(os.path.join(ROOT, "extracted", "assets"), exist_ok=True)
    with open(os.path.join(ROOT, "extracted", "assets", "survey.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
