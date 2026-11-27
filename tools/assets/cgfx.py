#!/usr/bin/env python3
"""CGFX (NintendoWare CTR .bcres family) survey + texture PNG export/import. Stdlib only.

FE Awakening stores models (.m), textures (.t), skeletal animations (.sa), effects (.r,
.bcres), cameras (.bccam, .c) and map scenes (bls/*.lz) as CGFX, mostly LZ13-compressed.
This tool does not rebuild CGFX structure: the files round-trip byte-identically as
opaque blobs through lz.py. What it adds is texture access:

  * survey: dictionary counts per file type (models, textures, materials, animations ...)
    and texture formats
  * unpack: every embedded image texture (TXOB type 0x20000011) -> PNG (+ .mipN.png),
    plus cgfx.json (name, size, format, offsets, pixel hashes) and, for ETC1/ETC1A4,
    the original blocks
  * pack: re-inject PNGs in place (same width/height/format; the file layout is not
    changed). Non-ETC formats are exact; ETC is reused from the original blocks when
    the PNG is unchanged, otherwise re-encoded with tex3ds' simple ETC1 encoder.

CGFX facts used (all offsets marked "rel" are self-relative: value + field address):
    header "CGFX", u16 BOM, u16 header size, u32 revision, u32 file size, u32 blocks
    "DATA" block: u32 size, 16 x (u32 count, u32 rel offset to a DICT)
    DICT: "DICT", u32 size, u32 count, root node, count x 16-byte nodes
          (u32 ref bit, u16 left, u16 right, u32 rel name, u32 rel data)
    TXOB (at the DICT data offset): u32 type, "TXOB", u32 revision, u32 rel name,
          u32 user-data count, u32 rel user data, u32 height, u32 width, u32 GL format,
          u32 GL type, u32 mip levels, u32 texture object, u32 location flags,
          u32 PICA format (tex3ds numbering), u32 rel image ->
          image: u32 height, u32 width, u32 data size, u32 rel data, ...

Usage:
    python tools/assets/cgfx.py survey [--jobs N]
    python tools/assets/cgfx.py unpack IN(.lz) OUT_DIR
    python tools/assets/cgfx.py pack OUT_DIR ORIGINAL(.lz) OUT        (OUT is uncompressed)
    python tools/assets/cgfx.py test [--jobs N]
        every CGFX in extracted/romfs: decode + re-encode each texture (non-ETC must be
        bit-exact) and re-inject; prints the identical rate
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
import isbin  # noqa: E402
import lz  # noqa: E402
import tex3ds  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
ROMFS = os.path.join(ROOT, "extracted", "romfs")
DICT_NAMES = ("models", "textures", "luts", "materials", "shaders", "cameras", "lights",
              "fogs", "environments", "skeletal_anims", "texture_anims", "visibility_anims",
              "camera_anims", "light_anims", "fog_anims", "emitters")
TXOB_IMAGE = 0x20000011


class CgfxError(ValueError):
    pass


def _rel(d: bytes, at: int) -> int:
    v = struct.unpack_from("<I", d, at)[0]
    return at + v if v else 0


def _cstr(d: bytes, at: int) -> bytes:
    return d[at:d.index(b"\0", at)]


def parse(d: bytes) -> dict:
    if d[:4] != b"CGFX":
        raise CgfxError("not CGFX")
    hsize = struct.unpack_from("<H", d, 6)[0]
    if d[hsize:hsize + 4] != b"DATA":
        raise CgfxError("no DATA block after the header")
    dicts = {}
    for i, nm in enumerate(DICT_NAMES):
        at = hsize + 8 + 8 * i
        cnt = struct.unpack_from("<I", d, at)[0]
        if not cnt:
            continue
        doff = _rel(d, at + 4)
        if d[doff:doff + 4] != b"DICT":
            raise CgfxError(f"{nm}: no DICT")
        n = struct.unpack_from("<I", d, doff + 8)[0]
        ents = []
        for k in range(n):
            e = doff + 0x1C + 16 * k
            name = _cstr(d, _rel(d, e + 8))
            ents.append((name, _rel(d, e + 12)))
        dicts[nm] = ents
    return dicts


def textures(d: bytes, dicts: dict | None = None) -> list[dict]:
    dicts = parse(d) if dicts is None else dicts
    out = []
    for name, off in dicts.get("textures", []):
        typ = struct.unpack_from("<I", d, off)[0]
        if d[off + 4:off + 8] != b"TXOB":
            raise CgfxError("texture entry is not a TXOB")
        t = {"name": isbin.quote(name), "type": typ}
        if typ == TXOB_IMAGE:
            h, w, _glf, _glt, mips, _obj, _loc, fmt = struct.unpack_from("<8I", d, off + 0x18)
            img = _rel(d, off + 0x38)
            ih, iw, size = struct.unpack_from("<3I", d, img)
            data = _rel(d, img + 0x0C)
            t.update(width=w, height=h, mips=mips, format=fmt, size=size, data_off=data)
            if (ih, iw) != (h, w):
                raise CgfxError("image size disagrees with TXOB size")
        out.append(t)
    return out


def mip_dims(t: dict):
    w, h = t["width"], t["height"]
    for _ in range(t["mips"]):
        yield w, h
        w, h = max(8, w // 2), max(8, h // 2)


def levels(t: dict, d: bytes) -> list[bytes]:
    out = []
    p = t["data_off"]
    end = p + t["size"]
    for w, h in mip_dims(t):
        n = tex3ds.data_size(t["format"], w, h)
        if p + n > end:
            break  # chain shorter than declared (min size reached)
        out.append(d[p:p + n])
        p += n
    if p != end:
        raise CgfxError(f"mip chain {p - t['data_off']} != data size {t['size']}")
    return out


def _safe(name: str) -> str:
    s = name.strip('"')
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in s) or "tex"


def unpack(d: bytes, out_dir: str, source: str = "") -> int:
    os.makedirs(out_dir, exist_ok=True)
    texs = [t for t in textures(d) if t["type"] == TXOB_IMAGE]
    used = set()
    for i, t in enumerate(texs):
        base = _safe(t["name"])
        while base in used:
            base += f"_{i}"
        used.add(base)
        t["file"] = base
        lv = levels(t, d)
        t["pixels_sha1"] = []
        for k, ((w, h), raw) in enumerate(zip(mip_dims(t), lv)):
            img = tex3ds.decode(t["format"], w, h, raw)
            t["pixels_sha1"].append(hashlib.sha1(img).hexdigest())
            tex3ds.write_png(os.path.join(out_dir, base + (f".mip{k}" if k else "") + ".png"), w, h, img)
        if t["format"] in (12, 13):
            with open(os.path.join(out_dir, base + ".orig.bin"), "wb") as fh:
                fh.write(b"".join(lv))
    with open(os.path.join(out_dir, "cgfx.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"source": source, "textures": texs}, fh, indent=1, ensure_ascii=False)
    return len(texs)


def pack(in_dir: str, orig: bytes) -> bytes:
    with open(os.path.join(in_dir, "cgfx.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    out = bytearray(orig)
    for t in meta["textures"]:
        ob = None
        if t["format"] in (12, 13):
            p = os.path.join(in_dir, t["file"] + ".orig.bin")
            if os.path.exists(p):
                with open(p, "rb") as fh:
                    ob = fh.read()
        pos = t["data_off"]
        po = 0
        for k, (w, h) in enumerate(mip_dims(t)):
            fn = os.path.join(in_dir, t["file"] + (f".mip{k}" if k else "") + ".png")
            if not os.path.exists(fn):
                break
            n = tex3ds.data_size(t["format"], w, h)
            pw, ph, img = tex3ds.read_png(fn)
            if (pw, ph) != (w, h):
                raise CgfxError(f"{fn}: {pw}x{ph}, must stay {w}x{h} (in-place import)")
            if ob is not None and hashlib.sha1(img).hexdigest() == t["pixels_sha1"][k]:
                enc = ob[po:po + n]
            else:
                enc = tex3ds.encode(t["format"], w, h, img)
            out[pos:pos + n] = enc
            pos += n
            po += n
    return bytes(out)


# ----------------------------------------------------------------- survey / test
def cgfx_files():
    out = []
    for dp, _dn, fn in os.walk(ROMFS):
        for f in fn:
            p = os.path.join(dp, f)
            with open(p, "rb") as fh:
                head = fh.read(12)
            if head[:4] == b"CGFX" or (lz.lz_type(head) is not None and (f.endswith(".lz") or head[0] == 0x13)):
                out.append(p)
    return sorted(out)


def _ext(path: str) -> str:
    f = os.path.basename(path)
    return "." + f.split(".", 1)[1].lower() if "." in f else "(none)"


def _one(args):
    path, mode = args
    try:
        d, _ = isbin.load_maybe_lz(path)
    except lz.LZError:
        return None
    if d[:4] != b"CGFX":
        return None
    r = {"ext": _ext(path), "dicts": {}, "fmts": {}, "ref": 0, "ok": True, "err": "",
         "tex": 0, "exact": 0, "etc": 0}
    try:
        dicts = parse(d)
        r["dicts"] = {k: len(v) for k, v in dicts.items()}
        texs = textures(d, dicts)
    except (CgfxError, struct.error, ValueError) as e:
        r["ok"] = False
        r["err"] = str(e)
        return r
    out = bytearray(d)
    for t in texs:
        if t["type"] != TXOB_IMAGE:
            r["ref"] += 1
            continue
        r["tex"] += 1
        r["fmts"][t["format"]] = r["fmts"].get(t["format"], 0) + 1
        if mode != "test":
            continue
        try:
            lv = levels(t, d)
        except CgfxError as e:
            r["ok"] = False
            r["err"] = str(e)
            continue
        if t["format"] in (12, 13):
            r["etc"] += 1
            continue
        pos = t["data_off"]
        good = True
        for (w, h), raw in zip(mip_dims(t), lv):
            enc = tex3ds.encode(t["format"], w, h, tex3ds.decode(t["format"], w, h, raw))
            good &= enc == raw
            out[pos:pos + len(enc)] = enc
            pos += len(enc)
        r["exact"] += good
        r["ok"] &= good
    if mode == "test":
        r["ok"] &= bytes(out) == d
    return r


def run(mode: str, jobs: int) -> tuple[int, int]:
    from concurrent.futures import ProcessPoolExecutor
    files = cgfx_files()
    per_ext: dict[str, dict] = {}
    fmts: dict[int, int] = {}
    n = ok = tex = exact = etc = ref = 0
    errs = []
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for path, r in zip(files, ex.map(_one, [(f, mode) for f in files], chunksize=4)):
            if r is None:
                continue
            n += 1
            ok += r["ok"]
            tex += r["tex"]
            exact += r["exact"]
            etc += r["etc"]
            ref += r["ref"]
            if not r["ok"]:
                errs.append(f"{os.path.relpath(path, ROMFS)}\t{r['err']}")
            pe = per_ext.setdefault(r["ext"], {"files": 0})
            pe["files"] += 1
            for k, v in r["dicts"].items():
                pe[k] = pe.get(k, 0) + v
            for k, v in r["fmts"].items():
                fmts[k] = fmts.get(k, 0) + v
    print(f"CGFX files: {n}; image textures: {tex} (+{ref} reference textures without pixels)")
    print("   texture formats: " + ", ".join(f"{tex3ds.FORMAT_NAMES.get(k, k)}={v}" for k, v in sorted(fmts.items())))
    for e, pe in sorted(per_ext.items(), key=lambda x: -x[1]["files"]):
        rest = ", ".join(f"{k}={v}" for k, v in pe.items() if k != "files")
        print(f"   {e:<10} {pe['files']:>4} files: {rest}")
    if mode == "test":
        print(f"CGFX texture re-inject: {ok}/{n} files identical ({100.0 * ok / max(n, 1):.2f}%); "
              f"{exact}/{tex - etc} non-ETC textures bit-exact through decode/encode; "
              f"{etc} ETC textures reuse original blocks")
    os.makedirs(os.path.join(ROOT, "extracted", "assets"), exist_ok=True)
    with open(os.path.join(ROOT, "extracted", "assets", "cgfx_fail.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(errs) + "\n")
    return ok, n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("survey", "unpack", "pack", "test"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    if a.cmd in ("survey", "test"):
        ok, n = run(a.cmd, a.jobs)
        return 0 if ok == n else 1
    if a.cmd == "unpack":
        if len(a.args) != 2:
            ap.error("unpack IN OUT_DIR")
        d, _ = isbin.load_maybe_lz(a.args[0])
        print(f"{unpack(d, a.args[1], os.path.basename(a.args[0]))} textures")
        return 0
    if len(a.args) != 3:
        ap.error("pack OUT_DIR ORIGINAL OUT")
    orig, _ = isbin.load_maybe_lz(a.args[1])
    with open(a.args[2], "wb") as fh:
        fh.write(pack(a.args[0], orig))
    return 0


if __name__ == "__main__":
    sys.exit(main())
