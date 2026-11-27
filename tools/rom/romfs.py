"""RomFS (IVFC level 3 + hash tree) parse, extract and streaming rebuild. Stdlib only.

Level 3 layout (all offsets relative to level 3 start):
    0x28-byte header: header size, then (offset, size) of dir hash table, dir metadata,
    file hash table, file metadata, then the file data offset.
    dir entry : parent, sibling, first child dir, first file, hash next, name length,
                UTF-16LE name padded to 4
    file entry: parent, sibling, data offset (u64), data size (u64), hash next,
                name length, UTF-16LE name padded to 4
Hash: h = parent_offset ^ 123456789; per UTF-16 unit: h = ror(h, 5) ^ unit.
Bucket count: n<3 -> 3; n<19 -> n|1; else the first k>=n not divisible by 2..17 primes.

Rules observed on every RomFS image of both games (Awakening: 3 partitions, Fates: 4) (checked by extract.py, recorded in
the manifest, and enforced byte-for-byte by rebuild.py's compare):
  - entries are inserted into hash buckets in metadata order, at the HEAD of the chain;
  - sibling links follow metadata order; a dir's child/file link is its first entry;
  - file data is laid out in file-metadata order, each file 0x10-aligned, zero padded,
    data region starts at align(end of file metadata, 0x10); level 3 ends at the end of
    the last file (no tail padding);
  - order rule (derivable from a plain directory tree, used for new trees):
    dirs  = root, then recursively: all children of a dir as one block, then recurse
            into each child; files = depth-first pre-order over dirs, each dir's files
            together; siblings sorted by name compared in upper case.
"""
from __future__ import annotations

import hashlib
import os
import struct
from pathlib import Path
from typing import BinaryIO

from ctr import CHUNK, IVFC_BLOCK_LOG2, NONE32, align, build_ivfc_header, ivfc_sizes, u32, u64

L3_HEADER_SIZE = 0x28
DATA_ALIGN = 0x10


def name_hash(parent: int, name: str) -> int:
    h = parent ^ 123456789
    units = struct.unpack(f"<{len(name.encode('utf-16-le')) // 2}H", name.encode("utf-16-le"))
    for c in units:
        h = ((h >> 5) | (h << 27)) & 0xFFFFFFFF
        h ^= c
    return h


def bucket_count(n: int) -> int:
    if n < 3:
        return 3
    if n < 19:
        return n | 1
    while any(n % p == 0 for p in (2, 3, 5, 7, 11, 13, 17)):
        n += 1
    return n


# --------------------------------------------------------------------------- parse
def parse_level3(meta: bytes) -> dict:
    """Parse header + metadata (bytes [0, data_offset) of level 3)."""
    (hlen, dh_off, dh_len, dm_off, dm_len, fh_off, fh_len, fm_off, fm_len,
     data_off) = struct.unpack_from("<10I", meta, 0)
    if hlen != L3_HEADER_SIZE:
        raise ValueError(f"unexpected level-3 header size 0x{hlen:X}")
    dm = meta[dm_off:dm_off + dm_len]
    fm = meta[fm_off:fm_off + fm_len]
    dirs, files = [], []
    o = 0
    while o < len(dm):
        par, sib, ch, fi, hn, nl = struct.unpack_from("<6I", dm, o)
        dirs.append({"off": o, "parent": par, "sibling": sib, "child": ch, "file": fi,
                     "hash_next": hn, "name": dm[o + 0x18:o + 0x18 + nl].decode("utf-16-le")})
        o += 0x18 + align(nl, 4)
    o = 0
    while o < len(fm):
        par, sib = struct.unpack_from("<2I", fm, o)
        doff, dsize = struct.unpack_from("<QQ", fm, o + 8)
        hn, nl = struct.unpack_from("<2I", fm, o + 0x18)
        files.append({"off": o, "parent": par, "sibling": sib, "data_off": doff, "size": dsize,
                      "hash_next": hn, "name": fm[o + 0x20:o + 0x20 + nl].decode("utf-16-le")})
        o += 0x20 + align(nl, 4)
    dpath = {}
    for d in dirs:
        dpath[d["off"]] = "" if d["off"] == 0 else (
            (dpath[d["parent"]] + "/" if dpath[d["parent"]] else "") + d["name"])
        d["path"] = dpath[d["off"]]
    for f in files:
        f["path"] = (dpath[f["parent"]] + "/" if dpath[f["parent"]] else "") + f["name"]
    return {"data_off": data_off, "dirs": dirs, "files": files,
            "dir_buckets": dh_len // 4, "file_buckets": fh_len // 4,
            "layout": [dh_off, dh_len, dm_off, dm_len, fh_off, fh_len, fm_off, fm_len]}


def order_by_rule(dirs: list[str], files: list[str]) -> tuple[list[str], list[str]]:
    """Canonical order (see module doc) for a set of dir and file paths ('' = root)."""
    kids: dict[str, list[str]] = {d: [] for d in dirs}
    dfiles: dict[str, list[str]] = {d: [] for d in dirs}
    for d in dirs:
        if d:
            kids[d.rpartition("/")[0]].append(d)
    for f in files:
        dfiles[f.rpartition("/")[0]].append(f)
    key = lambda p: p.rpartition("/")[2].upper()
    for v in kids.values():
        v.sort(key=key)
    for v in dfiles.values():
        v.sort(key=key)
    dout = [""]
    def emit(d):
        dout.extend(kids[d])
        for k in kids[d]:
            emit(k)
    emit("")
    fout: list[str] = []
    def visit(d):
        fout.extend(dfiles[d])
        for k in kids[d]:
            visit(k)
    visit("")
    return dout, fout


def scan_tree(root: Path) -> tuple[list[str], list[str]]:
    dirs, files = [""], []
    for dp, dns, fns in os.walk(root):
        rel = Path(dp).relative_to(root).as_posix()
        rel = "" if rel == "." else rel
        for d in dns:
            dirs.append(f"{rel}/{d}" if rel else d)
        for f in fns:
            files.append(f"{rel}/{f}" if rel else f)
    return dirs, files


# --------------------------------------------------------------------------- build
def build_level3_meta(dirs: list[str], files: list[tuple[str, int]]) -> tuple[bytes, list[int], int]:
    """Level-3 header + metadata for dirs (paths, metadata order, root '' first) and files
    ((path, size), metadata order). Returns (meta bytes incl. padding to the data offset,
    per-file data offsets, level-3 size)."""
    if not dirs or dirs[0] != "":
        raise ValueError("dir list must start with the root ''")
    doff, cur = {}, 0
    for d in dirs:
        doff[d] = cur
        cur += 0x18 + align(len(d.rpartition("/")[2].encode("utf-16-le")), 4)
    dm_len = cur
    foff, cur = [], 0
    for p, _ in files:
        foff.append(cur)
        cur += 0x20 + align(len(p.rpartition("/")[2].encode("utf-16-le")), 4)
    fm_len = cur

    def parent_of(p: str) -> str:
        return p.rpartition("/")[0]

    # sibling / first-child / first-file links, following list order
    dsib = {d: NONE32 for d in dirs}
    dchild = {d: NONE32 for d in dirs}
    dfile = {d: NONE32 for d in dirs}
    last_kid: dict[str, str] = {}
    for d in dirs[1:]:
        par = parent_of(d)
        if par not in doff:
            raise ValueError(f"dir {d!r} listed without its parent")
        if par in last_kid:
            dsib[last_kid[par]] = doff[d]
        else:
            dchild[par] = doff[d]
        last_kid[par] = d
    fsib = [NONE32] * len(files)
    last_file: dict[str, int] = {}
    for i, (p, _) in enumerate(files):
        par = parent_of(p)
        if par not in doff:
            raise ValueError(f"file {p!r} listed without its dir")
        if par in last_file:
            fsib[last_file[par]] = foff[i]
        else:
            dfile[par] = foff[i]
        last_file[par] = i

    nd, nf = bucket_count(len(dirs)), bucket_count(len(files))
    dtab, ftab = [NONE32] * nd, [NONE32] * nf
    dnext, fnext = {}, [NONE32] * len(files)
    for d in dirs:
        par = doff[parent_of(d)] if d else 0
        b = name_hash(par, d.rpartition("/")[2]) % nd
        dnext[d] = dtab[b]
        dtab[b] = doff[d]
    for i, (p, _) in enumerate(files):
        b = name_hash(doff[parent_of(p)], p.rpartition("/")[2]) % nf
        fnext[i] = ftab[b]
        ftab[b] = foff[i]

    dm = bytearray()
    for d in dirs:
        nb = d.rpartition("/")[2].encode("utf-16-le")
        par = doff[parent_of(d)] if d else 0
        dm += struct.pack("<6I", par, dsib[d] if d else NONE32, dchild[d], dfile[d], dnext[d], len(nb))
        dm += nb + bytes(align(len(nb), 4) - len(nb))
    data_offs = []
    cur = 0
    end = 0
    fm = bytearray()
    for i, (p, size) in enumerate(files):
        nb = p.rpartition("/")[2].encode("utf-16-le")
        cur = align(cur, DATA_ALIGN)
        data_offs.append(cur)
        fm += struct.pack("<2IQQ2I", doff[parent_of(p)], fsib[i], cur, size, fnext[i], len(nb))
        fm += nb + bytes(align(len(nb), 4) - len(nb))
        cur += size
        end = cur
    assert len(dm) == dm_len and len(fm) == fm_len
    dh_off = L3_HEADER_SIZE
    dm_off = dh_off + 4 * nd
    fh_off = dm_off + dm_len
    fm_off = fh_off + 4 * nf
    data_off = align(fm_off + fm_len, DATA_ALIGN)
    meta = bytearray(struct.pack("<10I", L3_HEADER_SIZE, dh_off, 4 * nd, dm_off, dm_len,
                                 fh_off, 4 * nf, fm_off, fm_len, data_off))
    meta += struct.pack(f"<{nd}I", *dtab) + dm + struct.pack(f"<{nf}I", *ftab) + fm
    meta += bytes(data_off - len(meta))
    return bytes(meta), data_offs, data_off + end


class BlockHashWriter:
    """Writes to `out` and collects SHA-256 of every `bs`-byte block written."""

    def __init__(self, out: BinaryIO, bs: int):
        self.out, self.bs = out, bs
        self.buf = bytearray()
        self.hashes = bytearray()
        self.written = 0

    def write(self, data) -> None:
        self.out.write(data)
        self.written += len(data)
        mv = memoryview(data)
        bs = self.bs
        if self.buf:
            need = bs - len(self.buf)
            self.buf += mv[:need]
            mv = mv[need:]
            if len(self.buf) < bs:
                return
            self.hashes += hashlib.sha256(self.buf).digest()
            self.buf.clear()
        n = len(mv) - len(mv) % bs
        for o in range(0, n, bs):
            self.hashes += hashlib.sha256(mv[o:o + bs]).digest()
        self.buf += mv[n:]

    def finish(self) -> bytes:
        if self.buf:
            self.buf += bytes(self.bs - len(self.buf))
            self.hashes += hashlib.sha256(self.buf).digest()
            self.buf.clear()
        return bytes(self.hashes)


def _hash_blocks(data: bytes, bs: int) -> bytes:
    w = BlockHashWriter(_Null(), bs)
    w.write(data)
    return w.finish()


class _Null:
    def write(self, b) -> None:
        pass


def write_romfs(out: BinaryIO, dirs: list[str], files: list[str], src_root: Path,
                bl: int = IVFC_BLOCK_LOG2) -> tuple[int, bytes, dict]:
    """Stream a complete RomFS (IVFC header, master hash, L3, L1, L2, physical order
    header|master|L3|L1|L2, each level block-aligned, zero padded) at out's current
    position; the header and master hash are patched in at the end. Returns
    (total size, superblock = IVFC header + master hash, info dict)."""
    bs = 1 << bl
    base = out.tell()
    sizes = [(p, (src_root / p).stat().st_size) for p in files]
    meta, data_offs, l3_size = build_level3_meta(dirs, sizes)
    mh_size, l1_size, l2_size = ivfc_sizes(l3_size, bl)
    l3_off = align(0x60 + mh_size, bs)
    out.write(bytes(l3_off))  # placeholder for header + master hash
    w = BlockHashWriter(out, bs)
    w.write(meta)
    pos = len(meta)
    for (p, size), doff in zip(sizes, data_offs):
        doff += len(meta)  # data offsets are relative to the data region
        if doff > pos:
            w.write(bytes(doff - pos))
            pos = doff
        with open(src_root / p, "rb") as fh:
            left = size
            while left:
                b = fh.read(min(CHUNK, left))
                if not b:
                    raise ValueError(f"{p}: file changed size while reading")
                w.write(b)
                left -= len(b)
        pos += size
    assert pos == l3_size
    l2 = w.finish()
    assert len(l2) == l2_size
    l1 = _hash_blocks(l2, bs)
    master = _hash_blocks(l1, bs)
    assert len(l1) == l1_size and len(master) == mh_size
    out.write(bytes(align(l3_off + l3_size, bs) - (l3_off + l3_size)))
    out.write(l1)
    out.write(bytes(align(len(l1), bs) - len(l1)))
    out.write(l2)
    total_unpadded = align(l3_off + l3_size, bs) + align(l1_size, bs) + l2_size
    total = align(total_unpadded, bs)
    out.write(bytes(total - total_unpadded))
    end = out.tell()
    superblock = build_ivfc_header(l3_size, bl) + master
    out.seek(base)
    out.write(superblock)
    out.seek(end)
    return total, superblock, {"l3_size": l3_size, "files": len(files), "dirs": len(dirs)}


def _same_as(fh: BinaryIO, pos: int, size: int, path: Path) -> bool:
    """True if `path` holds exactly the `size` bytes at fh[pos:] (streamed compare)."""
    try:
        if path.stat().st_size != size:
            return False
    except OSError:
        return False
    fh.seek(pos)
    with open(path, "rb") as o:
        left = size
        while left:
            n = min(CHUNK, left)
            if fh.read(n) != o.read(n):
                return False
            left -= n
    return True


def extract_romfs(fh: BinaryIO, romfs_off: int, out_root: Path, link_from: Path | None = None) -> dict:
    """Extract every file of the RomFS at absolute `romfs_off` into out_root.
    With `link_from` (an already extracted copy of the same RomFS, e.g. extracted/romfs),
    files there whose bytes equal the ROM's are hard-linked instead of copied, so the
    parts dir costs no extra disk; anything missing or different is written normally.
    Returns the parsed level 3 (paths in metadata order) plus layout facts
    (info["linked"] = number of files hard-linked)."""
    from ctr import parse_ivfc, read_at
    iv = parse_ivfc(read_at(fh, romfs_off, 0x60))
    l3 = romfs_off + iv["l3_off"]
    data_off = u32(read_at(fh, l3, 0x28), 0x24)
    info = parse_level3(read_at(fh, l3, data_off))
    out_root.mkdir(parents=True, exist_ok=True)
    seen = set()
    linked = 0
    for d in info["dirs"]:
        if d["path"]:
            key = d["path"].lower()
            if key in seen:
                raise ValueError(f"case-insensitive name clash: {d['path']}")
            seen.add(key)
            (out_root / d["path"]).mkdir(parents=True, exist_ok=True)
    for f in info["files"]:
        key = f["path"].lower()
        if key in seen:
            raise ValueError(f"case-insensitive name clash: {f['path']}")
        seen.add(key)
        pos = l3 + data_off + f["data_off"]
        dst = out_root / f["path"]
        if link_from is not None:
            src = link_from / f["path"]
            if _same_as(fh, pos, f["size"], src):
                if dst.exists() and os.path.samefile(src, dst):
                    linked += 1  # linked by an earlier run, bytes re-checked above
                    continue
                if dst.exists():
                    dst.unlink()
                try:
                    os.link(src, dst)
                    linked += 1
                    continue
                except OSError:
                    pass
        fh.seek(pos)
        left = f["size"]
        with open(dst, "wb") as o:
            while left:
                b = fh.read(min(CHUNK, left))
                o.write(b)
                left -= len(b)
    info["ivfc"] = iv
    info["linked"] = linked
    return info


def check_rules(info: dict) -> dict:
    """Which of the module-doc rules hold for a parsed level 3 (for the manifest)."""
    dirs = [d["path"] for d in info["dirs"]]
    files = [f["path"] for f in info["files"]]
    rd, rf = order_by_rule(dirs, files)
    meta, offs, l3 = build_level3_meta(dirs, [(f["path"], f["size"]) for f in info["files"]])
    return {
        "dir_order_matches_rule": rd == dirs,
        "file_order_matches_rule": rf == files,
        "data_offsets_match_rule": offs == [f["data_off"] for f in info["files"]],
        "rebuilt_meta_size_matches": len(meta) == info["data_off"],
    }
