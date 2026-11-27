#!/usr/bin/env python3
"""Fates portraits: every layer of a character's portrait -> PNG folders -> back. Stdlib only.

What makes up a portrait (from face/FaceData.bin.lz and the game's FaceData getters):
    face/FaceData.bin.lz   IS .bin: u32 count, then count x 0x48-byte records, one per
                           FSID (label = FSID). Fields used here (offsets in the record):
        +0x00 FSID name           +0x04 MPID (name message; "MPID_username" = avatar)
        +0x08 key (or 0): an ASCII name such as CAMILLA / PLAYER_M1 (meaning not
              checked in code; likely the voice / Live2D key)
                                  +0x0C package: face/face/<package>.arc
                                        (FaceData::GetPackegeFilePath, "%s/%s.arc")
        +0x10 body dir: face/body/<dir>/体<n>.bch.lz (GetBodyFilePath; 0 on this cart)
        +0x14 hair dir: face/hair/<dir>/髪<n>.bch.lz  (GetHairFilePath)
        +0x18 accessory dir: face/accessory1|2/<dir>/<accessory>.bch.lz
              (GetAccessory1/2FilePath; accessory names in FaceData_Acc1/2.bin.lz)
        +0x1C u32 colour (hair tint; 0xFF808080 for the avatar)
        +0x20, +0x24 expression names (two defaults, e.g. smile / pained)
        +0x28 .. +0x47 16 x u16 layout numbers (GetStandCenterOffset reads +0x30, +0x34;
              FaceInstance::CalcDrawFaceRect reads +0x34 / +0x36 as a draw size)
      Directory roots come from a table at 0x6BDBA0 in .data: face/face, face/body,
      face/hair, face/accessory1, face/accessory2. Getter addresses: FaceData::
      GetPackegeFilePath 0x545CB0, GetBodyFilePath 0x545C28, GetHairFilePath 0x545C74,
      GetAccessory1FilePath 0x545D00, GetAccessory2FilePath 0x545D4C.
    face/face/<package>.arc   one .arc per portrait kind: <name>_st (standing, 256x256
                           faces), _bu (bust / talk window, 128x128), _ct (cut-in,
                           512x512; only some characters). Members are LZ13 BCH files
                           named after the expression (通常 normal, 笑 smile, 怒 angry,
                           苦 pained, ...) plus two overlays: 汗 sweat and 照 blush (small
                           textures, 16x16 to 256x256); each holds one ETC1A4 texture.
    face/hair/<dir>/髪<n>.bch.lz   recolourable hair layers (avatar, children).
    face/accessory1|2/<dir>/*.bch.lz  avatar accessories.

Picture size and the game (code, see bchwrite.py for addresses): the size is read from
the file (TexCommand::GetWidth/GetHeight -> ITexture), and FaceInstance::CalcDrawFaceRect
draws the face at the texture's size in screen pixels (or at FaceData's layout size,
centred on a fixed 256). So on the 3DS a bigger face picture is drawn BIGGER, not sharper,
and overlay positions (sweat, blush) stay where they were. That is why `import` refuses
size changes unless --allow-resize is given, and even then requires every expression of
one package to get the same new size (overlays and hair/accessory layers are checked one
by one). Sizes must be powers of two from 8 to 1024 (bchwrite.py rules).

Folder layout written by `export` (one folder per character query):
    OUT/portrait.json                  manifest: records, sources and every layer
                                       (PNG path, role, size, format, mips)
    OUT/<package>/<NN>_<member>/       bch.py export of one expression (PNG + bch.json)
    OUT/hair/<dir>/<file>/             bch.py export of one hair layer
    OUT/accessory1|2/<dir>/<file>/     bch.py export of one accessory
Edit any PNG, then `import` checks everything first and only then writes the files that
changed, at their RomFS paths under DEST (e.g. a mod's romfs/ folder), each through a
temporary file (all or nothing). An unchanged export rebuilds every source
byte-identically.

Usage:
    python tools/assets/portrait.py list [QUERY]
        FaceData records (FSID, name id, PID, package, hair, accessory, expressions)
    python tools/assets/portrait.py export QUERY OUT_DIR [--no-extras]
        QUERY matches FSID, MPID, key or package (substring, e.g. カミラ or CAMILLA);
        the character's cut-in arc (<name>_ct, loaded by FaceCutInTexFile) is included;
        --no-extras skips hair/accessory layers
    python tools/assets/portrait.py import OUT_DIR DEST_DIR [--allow-resize]
    python tools/assets/portrait.py test [--jobs N]
        every face/face/*.arc, face/hair and face/accessory BCH: export -> import must
        change nothing; an edit test (one pixel block changed, re-imported, read back);
        a resize test (a package's expressions doubled and halved; refusals checked)
    python tools/assets/portrait.py etcbench [N]
        ETC1A4 encoder quality on N sample portraits (PSNR of the old simple encoder vs
        the refined one, on the original picture and on a re-filtered copy)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import arc  # noqa: E402
import bch  # noqa: E402
import isbin  # noqa: E402
import tex3ds  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
ROMFS = os.path.join(ROOT, "extracted", "romfs")
TEST_DIR = os.path.join(ROOT, "build", "assets", "portrait_test")
REC = 0x48
DIRS = {"package": "face/face", "body": "face/body", "hair": "face/hair",
        "accessory1": "face/accessory1", "accessory2": "face/accessory2"}
OVERLAYS = {"汗": "overlay-sweat", "照": "overlay-blush"}  # member name prefixes


class PortraitError(ValueError):
    pass


def _s(b: bytes | None) -> str:
    return b.decode("cp932", "replace") if b else ""


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in name) or "x"


def load_facedata(path: str | None = None) -> list[dict]:
    d, _ = isbin.load_maybe_lz(path or os.path.join(ROMFS, "face", "FaceData.bin.lz"))
    b = isbin.IsBin.parse(d)
    ds = len(b.data)
    se_rel = ds + 4 * len(b.relocs) + 8 * len(b.labels)
    relocs = set(b.relocs)
    count = struct.unpack_from("<I", b.data, 0)[0]
    if 4 + count * REC != ds:
        raise ValueError(f"FaceData: {count} records of 0x{REC:X} do not fill 0x{ds:X} bytes")

    def ptr(o: int) -> bytes | None:
        if o not in relocs:
            v = struct.unpack_from("<I", b.data, o)[0]
            if v:
                raise ValueError(f"FaceData +0x{o:X}: non-zero word without a relocation")
            return None
        return isbin._strz(b.strtab, struct.unpack_from("<I", b.data, o)[0] - se_rel)

    out = []
    for i in range(count):
        o = 4 + i * REC
        out.append({"index": i, "fsid": _s(ptr(o)), "mpid": _s(ptr(o + 4)), "key": _s(ptr(o + 8)),
                    "package": _s(ptr(o + 0x0C)), "body": _s(ptr(o + 0x10)),
                    "hair": _s(ptr(o + 0x14)), "accessory": _s(ptr(o + 0x18)),
                    "color": struct.unpack_from("<I", b.data, o + 0x1C)[0],
                    "expressions": [_s(ptr(o + 0x20)), _s(ptr(o + 0x24))],
                    "layout": list(struct.unpack_from("<16H", b.data, o + 0x28))})
    return out


def match(recs: list[dict], q: str) -> list[dict]:
    return [r for r in recs if any(q in r[k] for k in ("fsid", "mpid", "key", "package"))]


def sources_for(recs: list[dict], extras: bool = True) -> list[str]:
    """RomFS paths (posix) of every file that makes up these portraits."""
    out = []
    for r in recs:
        if r["package"]:
            pk = r["package"]
            cands = [pk] + ([pk[:-3] + "_ct"] if pk.endswith(("_st", "_bu")) else [])
            for c in cands:
                p = f"{DIRS['package']}/{c}.arc"
                if os.path.exists(os.path.join(ROMFS, *p.split("/"))):
                    out.append(p)
        if not extras:
            continue
        for key, roots in (("hair", ("hair",)), ("accessory", ("accessory1", "accessory2")),
                           ("body", ("body",))):
            if not r[key]:
                continue
            for root in roots:
                dd = os.path.join(ROMFS, *DIRS[root].split("/"), r[key])
                if os.path.isdir(dd):
                    for f in sorted(os.listdir(dd)):
                        out.append(f"{DIRS[root]}/{r[key]}/{f}")
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def _folder_for(src: str) -> str:
    parts = src.split("/")
    if parts[1] == "face":
        return _safe(parts[2].rsplit(".", 1)[0])
    return "/".join([parts[1], _safe(parts[2]), _safe(parts[3].split(".", 1)[0])])


def _role(src: str, member: str | None) -> str:
    if member is not None:
        for k, v in OVERLAYS.items():
            if member.startswith(k):
                return v
        return "expression"
    return src.split("/")[1]  # hair, accessory1, accessory2, body


def _layers(out_dir: str, folder: str, src: str, member: str | None) -> list[dict]:
    with open(os.path.join(out_dir, *folder.split("/"), "bch.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    return [{"png": f"{folder}/{t['file']}", "source": src, "member": member,
             "role": _role(src, member), "width": t["width"], "height": t["height"],
             "format": t["format"], "mips": t["mips"]} for t in meta["textures"]]


def export_sources(srcs: list[str], out_dir: str, recs: list[dict] | None = None) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    man = {"format": 2, "records": [], "sources": [], "layers": []}
    for r in recs or []:
        man["records"].append({k: r[k] for k in ("fsid", "mpid", "key", "package", "hair",
                                                   "accessory", "color", "expressions", "layout")})
    for src in srcs:
        path = os.path.join(ROMFS, *src.split("/"))
        if not os.path.exists(path):
            raise PortraitError(f"{src}: not in extracted/romfs (run tools/assets/romfs.py)")
        with open(path, "rb") as fh:
            raw = fh.read()
        folder = _folder_for(src)
        ent = {"src": src, "folder": folder}
        if src.endswith(".arc"):
            members, _layout = arc.parse_full(raw)
            ent["kind"] = "arc"
            ent["members"] = []
            for i, m in enumerate(members):
                sub = f"{i:02d}_{_safe(_s(m['name']).split('.', 1)[0])}"
                bch.export(m["data"], os.path.join(out_dir, *folder.split("/"), sub))
                ent["members"].append({"name": _s(m["name"]), "folder": sub})
                man["layers"] += _layers(out_dir, f"{folder}/{sub}", src, _s(m["name"]))
        else:
            ent["kind"] = "bch"
            bch.export(raw, os.path.join(out_dir, *folder.split("/")))
            man["layers"] += _layers(out_dir, folder, src, None)
        man["sources"].append(ent)
    with open(os.path.join(out_dir, "portrait.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(man, fh, indent=1, ensure_ascii=False)
    return man


def _png_size(path: str) -> tuple[int, int]:
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise PortraitError(f"{path}: not a PNG file")
    return struct.unpack(">II", head[16:24])


def check_sizes(out_dir: str, man: dict, allow_resize: bool) -> list[str]:
    """Size rules before anything is rebuilt. Returns notes for resized layers; raises
    PortraitError with every problem found."""
    probs, notes = [], []
    pkg_new: dict = {}
    for ly in man.get("layers", []):
        p = os.path.join(out_dir, *ly["png"].split("/"))
        if not os.path.exists(p):
            continue
        w, h = _png_size(p)
        if (w, h) == (ly["width"], ly["height"]):
            if ly["role"] == "expression":
                pkg_new.setdefault(ly["source"], {}).setdefault((w, h), []).append(ly["member"])
            continue
        if not allow_resize:
            probs.append(f"{ly['png']}: the PNG is {w}x{h}, the original is {ly['width']}x{ly['height']}. "
                         "The game draws portraits at their pixel size (a bigger picture shows bigger "
                         "on the 3DS screen, overlays stay where they were); keep the size, or pass "
                         "--allow-resize if that is what you want")
            continue
        if not (w & (w - 1) == 0 and h & (h - 1) == 0 and 8 <= w <= 1024 and 8 <= h <= 1024):
            probs.append(f"{ly['png']}: {w}x{h} - both sides must be powers of two between 8 and 1024")
            continue
        if ly["role"] == "expression":
            pkg_new.setdefault(ly["source"], {}).setdefault((w, h), []).append(ly["member"])
        notes.append(f"{ly['png']}: {ly['width']}x{ly['height']} -> {w}x{h} ({ly['role']})")
    for src, sizes in pkg_new.items():
        if len(sizes) > 1:
            desc = "; ".join(f"{w}x{h}: {', '.join(m for m in ms[:4])}{' ...' if len(ms) > 4 else ''}"
                             for (w, h), ms in sorted(sizes.items()))
            probs.append(f"{src}: expressions of one package must all have the same size "
                         f"(the game swaps them in place) - found {desc}")
    if probs:
        raise PortraitError("\n".join(probs))
    return notes


def rebuild_source(out_dir: str, ent: dict, allow_resize: bool = False) -> tuple[bytes, bytes, list[str]]:
    """(original bytes, rebuilt bytes, changed PNG paths) for one manifest entry."""
    path = os.path.join(ROMFS, *ent["src"].split("/"))
    if not os.path.exists(path):
        raise PortraitError(f"{ent['src']}: not in extracted/romfs")
    with open(path, "rb") as fh:
        raw = fh.read()
    base = os.path.join(out_dir, *ent["folder"].split("/"))
    changed = []
    try:
        if ent["kind"] == "bch":
            new, ch = bch.pack(base, raw, allow_resize)
            return raw, new, [f"{ent['folder']}/{c}" for c in ch]
        members, layout = arc.parse_full(raw)
        if [_s(m["name"]) for m in members] != [me["name"] for me in ent["members"]]:
            raise PortraitError(f"{ent['src']}: members differ from the export (re-export it)")
        for m, me in zip(members, ent["members"]):
            sub = os.path.join(base, me["folder"])
            if not os.path.isdir(sub):
                continue
            new, ch = bch.pack(sub, m["data"], allow_resize)
            if ch:
                m["data"] = new
                changed += [f"{ent['folder']}/{me['folder']}/{c}" for c in ch]
    except bch.BchError as e:
        raise PortraitError(f"{ent['src']}: {e}") from None
    return raw, (arc.build(members, layout) if changed else raw), changed


def import_dir(out_dir: str, dest: str, allow_resize: bool = False, quiet: bool = False) -> list[str]:
    mp = os.path.join(out_dir, "portrait.json")
    if not os.path.exists(mp):
        raise PortraitError(f"{out_dir}: no portrait.json (make the folder with `portrait.py export`)")
    with open(mp, encoding="utf-8") as fh:
        man = json.load(fh)
    notes = check_sizes(out_dir, man, allow_resize)
    built = []
    for ent in man["sources"]:  # build everything first: nothing is written on an error
        raw, new, changed = rebuild_source(out_dir, ent, allow_resize)
        if new != raw:
            built.append((ent["src"], new, changed))
    written = []
    for src, new, changed in built:
        p = os.path.join(dest, *src.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(new)
        os.replace(tmp, p)
        written.append(src)
        if not quiet:
            print(f"{src}: {len(changed)} textures changed")
    if not quiet:
        for n in notes:
            print(f"  resized {n}")
    return written


# ------------------------------------------------------------------ test
def all_sources() -> list[str]:
    out = []
    for root in ("face/face", "face/hair", "face/accessory1", "face/accessory2"):
        for dp, _dn, fn in os.walk(os.path.join(ROMFS, *root.split("/"))):
            for f in fn:
                out.append(os.path.relpath(os.path.join(dp, f), ROMFS).replace(os.sep, "/"))
    return sorted(out)


def _test_one(src: str):
    tmp = os.path.join(TEST_DIR, f"w{os.getpid()}")
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        man = export_sources([src], tmp)
        ent = man["sources"][0]
        npng = sum(1 for _dp, _dn, fn in os.walk(tmp) for f in fn if f.endswith(".png"))
        raw, new, changed = rebuild_source(tmp, ent)
        return src, new == raw and not changed, npng, ""
    except Exception as e:  # report, never hide
        return src, False, 0, f"{type(e).__name__}: {e}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def edit_test(recs: list[dict]) -> bool:
    """Change a 16x16 block of one expression, import, and read the pixels back."""
    r = next(x for x in recs if x["package"] and x["hair"])
    tmp = os.path.join(TEST_DIR, "edit")
    dest = os.path.join(TEST_DIR, "edit_dest")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(dest, ignore_errors=True)
    man = export_sources(sources_for([r]), tmp, [r])
    ent = man["sources"][0]
    sub = os.path.join(tmp, ent["folder"], ent["members"][0]["folder"])
    meta = json.load(open(os.path.join(sub, "bch.json"), encoding="utf-8"))
    png = os.path.join(sub, meta["textures"][0]["file"])
    w, h, rgba = tex3ds.read_png(png)
    img = bytearray(rgba)
    for y in range(32, 48):
        for x in range(32, 48):
            img[(y * w + x) * 4:(y * w + x) * 4 + 4] = b"\xff\x00\xff\xff"
    tex3ds.write_png(png, w, h, bytes(img))
    written = import_dir(tmp, dest, quiet=True)
    ok = written == [ent["src"]]
    with open(os.path.join(dest, *ent["src"].split("/")), "rb") as fh:
        members, _ = arc.parse_full(fh.read())
    with open(os.path.join(ROMFS, *ent["src"].split("/")), "rb") as fh:
        orig, _ = arc.parse_full(fh.read())
    ok &= [m["name"] for m in members] == [m["name"] for m in orig]
    ok &= all(a["data"] == b["data"] for a, b in zip(members[1:], orig[1:]))
    d, _w = bch.unwrap(members[0]["data"])
    od, _w = bch.unwrap(orig[0]["data"])
    ok &= len(d) == len(od)
    bb = bch.Bch(d)
    t = bb.textures()[0]
    back = bch.decode_level(t["format"], w, h, bb.levels(t)[0])
    px = back[(40 * w + 40) * 4:(40 * w + 40) * 4 + 4]
    ok &= px[0] > 200 and px[1] < 60 and px[2] > 200  # ETC1 is lossy; magenta survives
    print(f"edit test ({ent['src']}, member {_s(orig[0]['name'])}): "
          f"{'PASS' if ok else 'FAIL'}; pixel after re-import {px.hex()}")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(dest, ignore_errors=True)
    return ok


def _scale_png(path: str, factor: int) -> tuple[int, int]:
    """Nearest 2x (factor 2) or 2x2 box 1/2 (factor 0) of a PNG, in place (test helper)."""
    w, h, rgba = tex3ds.read_png(path)
    if factor == 2:
        img = bch._upscale2(rgba, w, h)
        w, h = w * 2, h * 2
    else:
        img = bch.downscale(rgba, w, h)
        w, h = w // 2, h // 2
    tex3ds.write_png(path, w, h, img)
    return w, h


def resize_test(recs: list[dict]) -> tuple[int, int]:
    """A standing-portrait package with its expressions doubled, then halved:
    refused without --allow-resize; refused when only one expression is resized; accepted
    with the flag (every expression re-parses at the new size, overlays and the other
    sources are unchanged, nothing else written)."""
    r = next(x for x in recs if x["package"].endswith("_st"))
    good = total = 0
    for factor, label in ((2, "doubled"), (0, "halved")):
        tmp = os.path.join(TEST_DIR, "resize")
        dest = os.path.join(TEST_DIR, "resize_dest")
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(dest, ignore_errors=True)
        srcs = sources_for([r], extras=False)
        man = export_sources(srcs, tmp, [r])
        ent = man["sources"][0]
        exprs = [ly for ly in man["layers"] if ly["source"] == ent["src"] and ly["role"] == "expression"]
        # 1. one expression only -> refused (mixed sizes)
        nw, nh = _scale_png(os.path.join(tmp, *exprs[0]["png"].split("/")), factor)
        checks = []
        try:
            import_dir(tmp, dest, allow_resize=True, quiet=True)
            checks.append(("mixed sizes refused", False))
        except PortraitError as e:
            checks.append(("mixed sizes refused", "same size" in str(e)))
        for ly in exprs[1:]:
            _scale_png(os.path.join(tmp, *ly["png"].split("/")), factor)
        # 2. without the flag -> refused
        try:
            import_dir(tmp, dest, quiet=True)
            checks.append(("refused without --allow-resize", False))
        except PortraitError as e:
            checks.append(("refused without --allow-resize", "allow-resize" in str(e)))
        checks.append(("nothing written by refusals", not os.path.exists(dest)))
        # 3. with the flag
        written = import_dir(tmp, dest, allow_resize=True, quiet=True)
        checks.append(("only the package written", written == [ent["src"]]))
        with open(os.path.join(dest, *ent["src"].split("/")), "rb") as fh:
            members, _ = arc.parse_full(fh.read())
        with open(os.path.join(ROMFS, *ent["src"].split("/")), "rb") as fh:
            orig, _ = arc.parse_full(fh.read())
        sizes_ok = overlays_same = True
        for m, o in zip(members, orig):
            role = _role(ent["src"], _s(o["name"]))
            if role == "expression":
                d, _w = bch.unwrap(m["data"])
                t = bch.Bch(d).textures()[0]
                sizes_ok &= (t["width"], t["height"]) == (nw, nh)
            else:
                overlays_same &= m["data"] == o["data"]
        checks.append((f"every expression re-parses at {nw}x{nh}", sizes_ok))
        checks.append(("overlays unchanged", overlays_same))
        ok = all(c for _n, c in checks)
        print(f"resize test {label} ({ent['src']}, {len(exprs)} expressions -> {nw}x{nh}): "
              f"{'PASS' if ok else 'FAIL'}" + ("" if ok else "; failed: " + ", ".join(n for n, c in checks if not c)))
        good += ok
        total += 1
    shutil.rmtree(os.path.join(TEST_DIR, "resize"), ignore_errors=True)
    shutil.rmtree(os.path.join(TEST_DIR, "resize_dest"), ignore_errors=True)
    return good, total


def test(jobs: int) -> tuple[int, int]:
    from concurrent.futures import ProcessPoolExecutor
    recs = load_facedata()
    srcs = all_sources()
    covered = set(sources_for(recs))
    ok = png = 0
    fails = []
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for src, good, n, err in ex.map(_test_one, srcs, chunksize=2):
            ok += good
            png += n
            if not good:
                fails.append(f"{src}\t{err or 'mismatch'}")
    print(f"FaceData: {len(recs)} records; portrait files referenced: {len(covered)} of "
          f"{len(srcs)} under face/ (face/face arcs, hair, accessories)")
    print(f"portrait files exported to PNG and rebuilt byte-identically: {ok}/{len(srcs)} "
          f"({png} PNGs)")
    for f in fails[:20]:
        print("  FAIL", f)
    good = edit_test(recs)
    rg, rn = resize_test(recs)
    shutil.rmtree(TEST_DIR, ignore_errors=True)
    return ok + good + rg, len(srcs) + 1 + rn


# ------------------------------------------------------------------ ETC benchmark
def psnr(a: bytes, b: bytes) -> float:
    """PSNR (dB) of the RGB channels over pixels that are not fully transparent in `a`."""
    se = n = 0
    for i in range(0, len(a), 4):
        if a[i + 3] == 0:
            continue
        se += (a[i] - b[i]) ** 2 + (a[i + 1] - b[i + 1]) ** 2 + (a[i + 2] - b[i + 2]) ** 2
        n += 3
    return 99.0 if se == 0 else 10 * math.log10(255 * 255 * n / se)


def refilter(img: bytes, w: int, h: int) -> bytes:
    """Average of each pixel and its right / lower neighbours: a stand-in for new art that
    was never ETC-compressed (the decoded original is already ETC-shaped)."""
    out = bytearray(img)
    s = w * 4
    for y in range(h - 1):
        for x in range(w - 1):
            p = y * s + x * 4
            for c in range(4):
                out[p + c] = (img[p + c] + img[p + 4 + c] + img[p + s + c] + img[p + s + 4 + c] + 2) // 4
    return bytes(out)


def etcbench(n: int = 4) -> list[dict]:
    face = os.path.join(ROMFS, "face", "face")
    arcs = sorted(f for f in os.listdir(face) if f.endswith("_st.arc"))
    step = max(1, len(arcs) // n)
    rows = []
    saved = tex3ds.ETC_QUALITY
    try:
        for f in arcs[::step][:n]:
            dd, _ = isbin.load_maybe_lz(os.path.join(face, f))
            m = next(x for x in arc.parse(dd) if b".bch" in x["name"].lower())
            d, _ = bch.unwrap(m["data"])
            b = bch.Bch(d)
            t = b.textures()[0]
            w, h = t["dims"][0]
            img = tex3ds.decode(t["format"], w, h, b.levels(t)[0])
            for label, src in (("original", img), ("re-filtered", refilter(img, w, h))):
                row = {"file": f, "picture": label, "size": f"{w}x{h}",
                       "format": tex3ds.FORMAT_NAMES[t["format"]]}
                for q in ("fast", "high"):
                    tex3ds.ETC_QUALITY = q
                    t0 = time.time()
                    enc = tex3ds.encode(t["format"], w, h, src)
                    row[f"{q}_s"] = time.time() - t0
                    row[f"{q}_db"] = psnr(src, tex3ds.decode(t["format"], w, h, enc))
                rows.append(row)
                print(f"{row['file'][:24]:24} {label:11} {row['size']} {row['format']}: simple "
                      f"{row['fast_db']:.2f} dB ({row['fast_s']:.1f} s)  refined {row['high_db']:.2f} dB "
                      f"({row['high_s']:.1f} s)  +{row['high_db'] - row['fast_db']:.2f} dB", flush=True)
    finally:
        tex3ds.ETC_QUALITY = saved
    for label in ("original", "re-filtered"):
        rs = [r for r in rows if r["picture"] == label]
        if rs:
            print(f"mean {label}: simple {sum(r['fast_db'] for r in rs) / len(rs):.2f} dB, refined "
                  f"{sum(r['high_db'] for r in rs) / len(rs):.2f} dB; time per picture "
                  f"{sum(r['fast_s'] for r in rs) / len(rs):.1f} s -> {sum(r['high_s'] for r in rs) / len(rs):.1f} s")
    return rows


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):  # Japanese names on a cp1252 console
        sys.stdout.reconfigure(errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("list", "export", "import", "test", "etcbench"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--no-extras", action="store_true")
    ap.add_argument("--allow-resize", action="store_true",
                    help="import: accept PNGs of another size (powers of two, 8..1024)")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    try:
        if a.cmd == "test":
            ok, n = test(a.jobs)
            return 0 if ok == n else 1
        if a.cmd == "etcbench":
            etcbench(int(a.args[0]) if a.args else 4)
            return 0
        if a.cmd == "list":
            recs = load_facedata()
            if a.args:
                recs = match(recs, a.args[0])
            for r in recs:
                print(f"{r['index']:3d} {r['fsid']:<34} {r['key'] or '-':<22} pkg={r['package']} "
                      f"hair={r['hair'] or '-'} acc={r['accessory'] or '-'} color={r['color']:08X} "
                      f"expr={'/'.join(r['expressions'])}")
            return 0
        if len(a.args) != 2:
            print(f"error: {a.cmd} needs two arguments (see --help)", file=sys.stderr)
            return 2
        if a.cmd == "export":
            recs = match(load_facedata(), a.args[0])
            if not recs:
                print(f"error: no FaceData record matches {a.args[0]!r} (try `portrait.py list`)",
                      file=sys.stderr)
                return 1
            srcs = sources_for(recs, not a.no_extras)
            man = export_sources(srcs, a.args[1], recs)
            print(f"{len(recs)} records, {len(srcs)} files, {len(man['layers'])} picture layers -> {a.args[1]}")
            return 0
        written = import_dir(a.args[0], a.args[1], a.allow_resize)
        print(f"{len(written)} files written under {a.args[1]}")
        return 0
    except (PortraitError, bch.BchError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
