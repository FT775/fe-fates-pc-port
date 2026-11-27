#!/usr/bin/env python3
"""Run every asset converter over the whole RomFS and print byte-identical pass rates.

Standard library only. Needs extracted/romfs/ (tools/assets/romfs.py). Writes nothing
outside extracted/assets/ (failure lists and roundtrip_report.txt).

Stages (each converter's own `test`, run in-process):
    romfs     extracted files still match the manifest hashes (nothing edited)
    lz        decompress + recompress every LZ10/11/13 file (parser greedy-far)
    isbin     IS .bin container -> text listing -> rebuild, plus the 8-byte shift test
    msg       message archive -> UTF-8 text -> rebuild
    arc       .arc archive -> members -> rebuild; LZ members recompressed too
    ctpk      CTPK -> fields + PNG -> rebuild (non-ETC pixels go through PNG; ETC keeps
              the original blocks)
    cgfx      CGFX textures decoded/re-encoded and re-injected in place
    bch       BCH (H3D) files and .arc BCH members: every texture -> PNG -> re-encoded and
              re-injected in place (bch.py test); plus bch.py's edit selftest (in-place
              edits, a portrait resized through --allow-resize, refusals)
    bchwrite  the relocating BCH writer (bchwrite.py test): every BCH rebuilt unedited,
              the relocation coverage scan, every texture resized and restored, and a
              mutation fuzz of the relocation table
    portrait  every face/ portrait file (face/face arcs, hair, accessories) -> PNG folders
              -> rebuilt, plus an edit test (portrait.py test)
    chain     the whole RomFS, file by file, through the editable forms end to end:
              LZ decompress (or the "stored" 00+size wrapper) -> text/listing/PNG/members
              -> rebuild -> LZ recompress (arc members recursively), compared with the
              original file bytes
Files with no converter (audio, video, Live2D, scripts, fonts, particles, shaders) are
carried as blobs; the chain stage counts them as "blob".

Usage:
    python tools/assets/roundtrip_all.py [--jobs N] [--skip lz,cgfx,...]
Exit status 0 only if every stage is 100%.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import arc  # noqa: E402
import bch  # noqa: E402
import bchwrite  # noqa: E402
import cgfx  # noqa: E402
import ctpk  # noqa: E402
import isbin  # noqa: E402
import lz  # noqa: E402
import msg  # noqa: E402
import portrait  # noqa: E402
import romfs  # noqa: E402
import survey  # noqa: E402
import tex3ds  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
ROMFS = os.path.join(ROOT, "extracted", "romfs")
STAGES = ("romfs", "lz", "isbin", "msg", "arc", "ctpk", "cgfx", "bch", "bchwrite", "portrait", "chain")


# ----------------------------------------------------------------- chain stage
def _ctpk_via_png(d: bytes) -> bytes:
    hdr = ctpk.parse(d)
    datas = []
    for t in hdr["textures"]:
        new = []
        for (w, h), lv in zip(ctpk.mip_dims(t), ctpk.split_mips(t, t["_data"])):
            if t["format"] in (12, 13):
                new.append(lv)
                continue
            img = tex3ds.decode(t["format"], w, h, lv)
            _, _, img = tex3ds.parse_png(tex3ds.png_bytes(w, h, img, 1))
            new.append(tex3ds.encode(t["format"], w, h, img))
        datas.append(b"".join(new))
    return ctpk.build(hdr, datas)


def _cgfx_reinject(d: bytes) -> bytes:
    out = bytearray(d)
    for t in cgfx.textures(d):
        if t["type"] != cgfx.TXOB_IMAGE or t["format"] in (12, 13):
            continue
        pos = t["data_off"]
        for (w, h), raw in zip(cgfx.mip_dims(t), cgfx.levels(t, d)):
            enc = tex3ds.encode(t["format"], w, h, tex3ds.decode(t["format"], w, h, raw))
            out[pos:pos + len(enc)] = enc
            pos += len(enc)
    return bytes(out)


def rebuild_inner(d: bytes) -> tuple[bytes, str]:
    """Rebuild decompressed content through its editable form. Returns (bytes, kind)."""
    if d[:4] == b"CTPK":
        return _ctpk_via_png(d), "ctpk"
    if d[:4] == b"CGFX":
        return _cgfx_reinject(d), "cgfx"
    if d[:4] == b"BCH\0":
        return bch.roundtrip_bytes(d)[0], "bch"
    if msg.is_msg(d):
        name, entries, _ = msg.parse(d)
        return msg.build_bytes(*msg.from_text(msg.to_text(name, entries))), "msg"
    if arc.is_arc(d):
        members, layout = arc.parse_full(d)
        for m in members:
            md = m["data"]
            if lz.lz_type(md) is not None:
                inner, _k = rebuild_inner(lz.decompress(md))
                m["data"] = lz.compress_like(inner, md)
            else:
                m["data"] = rebuild_inner(md)[0]
        return arc.build(members, layout), "arc"
    if isbin.is_isbin(d):
        return isbin.assemble(isbin.dump(isbin.IsBin.parse(d))), "isbin"
    return d, "blob"


def _chain_one(path: str):
    with open(path, "rb") as fh:
        orig = fh.read()
    t = lz.lz_type(orig)
    is_lz = t is not None and (path.lower().endswith(".lz") or t == 0x13)
    stored = survey.unwrap_stored(orig)
    try:
        if stored is not None:
            new, kind = rebuild_inner(stored)
            new = orig[:4] + new
            return path, kind + "(stored)", new == orig, ""
        inner = lz.decompress(orig) if is_lz else orig
        new, kind = rebuild_inner(inner)
        if is_lz:
            new = lz.compress_like(new, orig)
        return path, kind, new == orig, ""
    except Exception as e:  # report, never hide
        return path, "error", False, f"{type(e).__name__}: {e}"


def chain(jobs: int) -> tuple[int, int, dict]:
    from concurrent.futures import ProcessPoolExecutor
    files = []
    for dp, _dn, fn in os.walk(ROMFS):
        for f in fn:
            files.append(os.path.join(dp, f))
    files.sort(key=lambda p: -os.path.getsize(p))  # big files first for load balance
    ok = 0
    kinds: dict = {}
    fails = []
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for path, kind, good, err in ex.map(_chain_one, files, chunksize=2):
            k = kinds.setdefault(kind, [0, 0])
            k[1] += 1
            k[0] += good
            ok += good
            if not good:
                fails.append(f"{os.path.relpath(path, ROMFS)}\t{kind}\t{err}")
    print(f"whole RomFS rebuilt from editable forms: {ok}/{len(files)} files identical; "
          + ", ".join(f"{k}={v[0]}/{v[1]}" for k, v in sorted(kinds.items())))
    with open(os.path.join(ROOT, "extracted", "assets", "chain_fail.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(fails) + "\n")
    return ok, len(files), kinds


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):  # Japanese names on a cp1252 console
        sys.stdout.reconfigure(errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--skip", default="", help="comma-separated stages to skip")
    a = ap.parse_args()
    skip = {s for s in a.skip.split(",") if s}
    rows = []  # (stage, what, ok, n, seconds)

    def run(stage, fn):
        if stage in skip:
            return None
        t = time.time()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            res = fn()
        dt = time.time() - t
        sys.stdout.write(buf.getvalue())
        return res, dt

    r = run("romfs", romfs.check)
    if r:
        (ok, n), dt = r
        rows.append(("romfs", "extracted files match manifest", ok, n, dt))
    r = run("lz", lambda: lz.survey(a.jobs, [lz.DEFAULT_PARSE]))
    if r:
        res, dt = r
        for fmt, st in sorted((k, v) for k, v in res.items() if k != "errors"):
            ok, n = st[lz.DEFAULT_PARSE]
            rows.append(("lz", f"LZ{fmt:02X} files recompress identically", ok, n, dt))
        if res.get("errors"):
            rows.append(("lz", "LZ decode errors", 0, res["errors"], dt))
    r = run("isbin", lambda: isbin.test(a.jobs, shift=True))
    if r:
        (ok, n), dt = r
        rows.append(("isbin", "IS .bin listing -> rebuild (+shift test)", ok, n, dt))
    r = run("msg", lambda: msg.test(a.jobs))
    if r:
        (ok, n), dt = r
        rows.append(("msg", "message archives via UTF-8 text", ok, n, dt))
    r = run("arc", lambda: arc.test(a.jobs))
    if r:
        (ok, n, lzok, nlz), dt = r
        rows.append(("arc", ".arc archives via member files", ok, n, dt))
        rows.append(("arc", ".arc LZ members recompress identically", lzok, nlz, 0.0))
    r = run("ctpk", lambda: ctpk.test(a.jobs, True))
    if r:
        (ok, n), dt = r
        rows.append(("ctpk", "CTPK packages via PNG + JSON", ok, n, dt))
    r = run("cgfx", lambda: cgfx.run("test", a.jobs))
    if r:
        (ok, n), dt = r
        rows.append(("cgfx", "CGFX files, textures re-injected", ok, n, dt))
    r = run("bch", lambda: bch.test(a.jobs))
    if r:
        (ok, n, parsed, ntex, _lz), dt = r
        rows.append(("bch", "BCH files + arc members parse", parsed, n, dt))
        rows.append(("bch", f"BCH via PNG re-inject ({ntex} textures)", ok, n, 0.0))
    r = run("bch", lambda: bch.edit_selftest())
    if r:
        bad, dt = r
        rows.append(("bch", "BCH edit selftest (6 cases)", 6 - bad, 6, dt))
    r = run("bchwrite", lambda: bchwrite.test(a.jobs))
    if r:
        st, dt = r
        rows.append(("bchw", "BCH unedited rebuild, relocating writer", st["ident"], st["files"], dt))
        rows.append(("bchw", "BCH relocation coverage scan clean", st["cov_ok"], st["files"], 0.0))
        rows.append(("bchw", "BCH textures resized, verified, restored", st["resized"], st["resizable"], 0.0))
        rows.append(("bchw", "relocation mutations caught by the scan", st["fuzz_detected"], st["fuzz_tried"], 0.0))
    r = run("portrait", lambda: portrait.test(a.jobs))
    if r:
        (ok, n), dt = r
        rows.append(("portr", "portrait files via PNG folders (+edit, resize)", ok, n, dt))
    r = run("chain", lambda: chain(a.jobs))
    if r:
        (ok, n, kinds), dt = r
        rows.append(("chain", "every RomFS file via its editable form", ok, n, dt))

    out = io.StringIO()
    print("\n=== round-trip summary (byte-identical) ===", file=out)
    allgood = True
    for stage, what, ok, n, dt in rows:
        pct = 100.0 * ok / n if n else 100.0
        allgood &= ok == n
        print(f"  {stage:<6} {what:<44} {ok:>6}/{n:<6} {pct:7.2f}%  ({dt:.0f}s)", file=out)
    print("  carried as blobs (no converter): audio CSTM/CSAR/.aac, MOFLEX video, Live2D "
          ".moc/.mtn/json, cmb scripts, .bfnt fonts, .ptcl particles, DVLB shaders, misc", file=out)
    print("ALL STAGES 100%" if allgood else "SOME STAGES BELOW 100% (see extracted/assets/*_fail.txt)", file=out)
    text = out.getvalue()
    sys.stdout.write(text)
    os.makedirs(os.path.join(ROOT, "extracted", "assets"), exist_ok=True)
    with open(os.path.join(ROOT, "extracted", "assets", "roundtrip_report.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    _ = survey  # survey.py is a separate report; imported to fail fast if broken
    return 0 if allgood else 1


if __name__ == "__main__":
    sys.exit(main())
