#!/usr/bin/env python3
"""FE Awakening / Fates ".arc" archives <-> a folder of member files + arc.json. Stdlib only.

An .arc is an IS .bin container (see isbin.py) whose data region is:
    zero bytes up to the "Data" label (Awakening: none, Data at 0; Fates: Data at 0x60,
             i.e. file offset 0x80)
    "Data":  the member files (each usually LZ13-compressed, e.g. *.ctpk.lz, *.bch.lz).
             Awakening packs them back to back (5 archives align to 0x20); Fates aligns
             every member to 0x80 in file coordinates. Recorded as "align" in arc.json.
    zero padding to max(align, 4) (file coordinates)
    "Count": u32 member count
    "Info":  count x { ptr name (pooled string), u32 index, u32 size, u32 offset from Data }
Labels: Data, Count, Info, then one label per member (named like the member) on its Info
entry. Relocations: the name pointers, in Info order.

`unpack` writes every member as its own file (OUT_DIR/<index>_<safe name>) plus arc.json
(names, indexes, order). `pack` rebuilds the archive from those files; members may be
edited, resized, added or removed (indexes/offsets/sizes are recomputed).

Usage:
    python tools/assets/arc.py unpack IN.arc[.lz] OUT_DIR
    python tools/assets/arc.py pack OUT_DIR OUT.arc
    python tools/assets/arc.py test [--jobs N]
        parse -> rebuild every .arc in extracted/romfs, print the identical rate, and the
        LZ round-trip rate of the LZ-compressed members
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import isbin  # noqa: E402
import lz  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
ROMFS = os.path.join(ROOT, "extracted", "romfs")
FIXED = (b"Data", b"Count", b"Info")


class ArcError(ValueError):
    pass


def is_arc(d: bytes) -> bool:
    if not isbin.is_isbin(d):
        return False
    b = isbin.IsBin.parse(d)
    return [n for _o, n, _no in b.labels[:3]] == list(FIXED)


def _falign(x: int, a: int) -> int:
    return (x + a - 1) & ~(a - 1)


def detect_align(members: list[dict], count_off: int, data_off: int = 0) -> int:
    """Member alignment. Offsets are measured in FILE coordinates (0x20 + data offset),
    which is what the game aligns. Awakening packs members back to back (1); a few of its
    archives (DLC faces, ui/dialog.arc) align each member, and the Count word, to 0x20.
    Fates aligns every member and the Count word to 0x80."""
    for a in (1, 4, 8, 16, 32, 64, 128, 256):
        pos = 0x20 + data_off
        good = True
        for m in members:
            pos = _falign(pos, a)
            if 0x20 + data_off + m["_off"] != pos:
                good = False
                break
            pos += len(m["data"])
        if good and 0x20 + count_off == _falign(pos, max(a, 4)):
            return a
    raise ArcError("member offsets follow no alignment rule")


def parse(d: bytes) -> list[dict]:
    """Return [{name: bytes, index: int, data: bytes}] in Info order."""
    return parse_full(d)[0]


def parse_layout(d: bytes) -> tuple[list[dict], dict]:
    """(members, layout). layout = {"align": member alignment, "data_off": offset of the
    Data label in the data region (Awakening 0, Fates 0x60; the bytes before it are
    zero)}. Member offsets in Info are relative to the Data label."""
    b = isbin.IsBin.parse(d)
    if [n for _o, n, _no in b.labels[:3]] != list(FIXED):
        raise ArcError("not an .arc (labels Data/Count/Info missing)")
    data_off, count_off, info_off = (b.labels[i][0] for i in range(3))
    if b.data[:data_off].strip(b"\0"):
        raise ArcError("non-zero bytes before the Data label")
    count = struct.unpack_from("<I", b.data, count_off)[0]
    ds = len(b.data)
    se_rel = ds + 4 * len(b.relocs) + 8 * len(b.labels)
    members = []
    for i in range(count):
        e = info_off + 16 * i
        nptr, idx, size, off = struct.unpack_from("<4I", b.data, e)
        name = isbin._strz(b.strtab, nptr - se_rel)
        members.append({"name": name, "index": idx, "_off": off,
                        "data": b.data[data_off + off:data_off + off + size]})
    return members, {"align": detect_align(members, count_off, data_off), "data_off": data_off}


def parse_full(d: bytes) -> tuple[list[dict], dict]:
    """(members, layout); pass layout back to build() unchanged."""
    return parse_layout(d)


def build(members: list[dict], layout: dict | int = 1) -> bytes:
    """Rebuild an .arc. `layout` is parse_full()'s dict (or a bare alignment int, meaning
    the Awakening layout with that alignment)."""
    if isinstance(layout, int):
        layout = {"align": layout, "data_off": 0}
    align, data_off = layout["align"], layout.get("data_off", 0)
    data = bytearray(data_off)
    offs = []
    for m in members:
        while (0x20 + len(data)) % align:
            data.append(0)
        offs.append(len(data) - data_off)
        data += m["data"]
    while (0x20 + len(data)) % max(align, 4):
        data.append(0)
    count_off = len(data)
    data += struct.pack("<I", len(members))
    info_off = len(data)
    relocs = []
    labels = [(data_off, b"Data"), (count_off, b"Count"), (info_off, b"Info")]
    for m, off in zip(members, offs):
        e = len(data)
        labels.append((e, m["name"]))
        relocs.append(e)
        data += struct.pack("<4I", 0, m["index"], len(m["data"]), off)
    tab, noffs, soffs = isbin.build_pool([n for _o, n in labels], [m["name"] for m in members])
    se_rel = len(data) + 4 * len(relocs) + 8 * len(labels)
    for e, so in zip(relocs, soffs):
        struct.pack_into("<I", data, e, se_rel + so)
    b = isbin.IsBin()
    b.data = bytes(data)
    b.relocs = relocs
    b.strtab = tab
    b.labels = [(o, n, no) for (o, n), no in zip(labels, noffs)]
    return b.build()


def _safe(name: bytes) -> str:
    s = name.decode("cp932", "replace")
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in s)


def unpack(d: bytes, out_dir: str) -> int:
    members, layout = parse_full(d)
    os.makedirs(out_dir, exist_ok=True)
    meta = []
    for i, m in enumerate(members):
        fn = f"{i:03d}_{_safe(m['name'])}"
        with open(os.path.join(out_dir, fn), "wb") as fh:
            fh.write(m["data"])
        meta.append({"name": isbin.quote(m["name"]), "index": m["index"], "file": fn})
    with open(os.path.join(out_dir, "arc.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"align": layout["align"], "data_off": layout["data_off"], "members": meta},
                  fh, indent=1, ensure_ascii=False)
    return len(members)


def pack(in_dir: str) -> bytes:
    with open(os.path.join(in_dir, "arc.json"), encoding="utf-8") as fh:
        j = json.load(fh)
    meta = j["members"]
    members = []
    for m in meta:
        with open(os.path.join(in_dir, m["file"]), "rb") as fh:
            members.append({"name": isbin.unquote(m["name"]), "index": m["index"], "data": fh.read()})
    return build(members, {"align": j.get("align", 1), "data_off": j.get("data_off", 0)})


def arc_files():
    out = []
    for dp, _dn, fn in os.walk(ROMFS):
        for f in fn:
            if f.lower().endswith((".arc", ".arc.lz")):
                out.append(os.path.join(dp, f))
    return sorted(out)


def _test_one(path: str):
    d, _ = isbin.load_maybe_lz(path)
    try:
        members, layout = parse_full(d)
    except (ArcError, isbin.BinError, struct.error, ValueError) as e:
        return path, False, 0, 0, 0, str(e)
    ok = build(members, layout) == d
    nlz = lzok = 0
    for m in members:
        if lz.lz_type(m["data"]) is not None:
            nlz += 1
            try:
                lzok += lz.roundtrip(m["data"])[1]
            except lz.LZError:
                pass
    return path, ok, len(members), nlz, lzok, ""


def test(jobs: int):
    from concurrent.futures import ProcessPoolExecutor
    n = ok = mem = nlz = lzok = 0
    fails = []
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for path, good, k, a, b, err in ex.map(_test_one, arc_files(), chunksize=4):
            n += 1
            ok += good
            mem += k
            nlz += a
            lzok += b
            if not good:
                fails.append(f"{os.path.relpath(path, ROMFS)}\t{err}")
    print(f".arc archives: {ok}/{n} rebuild byte-identically from members "
          f"({100.0 * ok / max(n, 1):.2f}%); {mem} members, LZ members recompress "
          f"identically: {lzok}/{nlz}")
    os.makedirs(os.path.join(ROOT, "extracted", "assets"), exist_ok=True)
    with open(os.path.join(ROOT, "extracted", "assets", "arc_fail.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(fails) + "\n")
    return ok, n, lzok, nlz


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("unpack", "pack", "test"))
    ap.add_argument("inp", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    if a.cmd == "test":
        ok, n, lzok, nlz = test(a.jobs)
        return 0 if ok == n and lzok == nlz else 1
    if not (a.inp and a.out):
        ap.error("need IN and OUT")
    if a.cmd == "unpack":
        d, _ = isbin.load_maybe_lz(a.inp)
        print(f"{unpack(d, a.out)} members")
    else:
        with open(a.out, "wb") as fh:
            fh.write(pack(a.inp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
