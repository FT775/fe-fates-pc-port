#!/usr/bin/env python3
"""Intelligent Systems ".bin" data container (FE Awakening and Fates) <-> editable text listing.

Standard library only.

Container layout (all little-endian):
    0x00 u32 file size            0x04 u32 data region size (D)
    0x08 u32 relocation count (R) 0x0C u32 label count (L)
    0x10 16 bytes padding (zero in every game file)
    0x20 data region, D bytes. "Pointers" inside it are offsets from 0x20.
    then R x u32: data-region offsets of the words that are pointers (relocations)
    then L x (u32 data offset, u32 name offset): exported labels
    then the name/string table: NUL-terminated Shift-JIS strings. Label names come first
    (label order, no dedup); then every string a data pointer refers to, in
    relocation-table order, skipping strings already present. Such pointers hold
    (table start - 0x20 + string offset), i.e. they point past the data region.

Listing (".isbin.txt") — a small assembler-like text format, one item per line:
    .isbin 1                      format marker (first line)
    .strtab pool|concat|dedup|raw HEX
                                  how the name table is rebuilt: pool = names + pooled
                                  strings (the game's layout; every game file uses it);
                                  the others are fallbacks (raw = original bytes kept)
    .hdrpad HEX / .tail HEX       only if the original had non-zero padding / extra bytes
    @NAME t=K [n=0xOFF]           exported label at this position (K = label-table index;
                                  n= only with ".strtab raw")
    L_XXXX:                       local label (pointer target with no exported label)
    .ptr TARGET r=K               4-byte relocated pointer; TARGET is a label name,
                                  L_XXXX, "a pooled string" (pool mode), or a number
                                  (0x...) for anything else
    .word 0x........              4 raw bytes (little-endian value)
    .byte xx xx ...               raw bytes
    .sjis "..."                   NUL-terminated Shift-JIS string (only emitted when it
                                  decodes and re-encodes to the identical bytes)
Names that are not printable cp932 are written with \\xNN escapes inside "..." quotes.
Rebuild assigns positions in listing order, resolves .ptr targets, orders the relocation
table by r= (new pointers without r= go last, in position order) and the label table by
t= likewise. Editing therefore keeps every pointer consistent; non-pointer offsets that
the game stores as plain integers are of course not adjusted.

Usage:
    python tools/assets/isbin.py dump IN.bin[.lz] OUT.isbin.txt
    python tools/assets/isbin.py build IN.isbin.txt OUT.bin [--like ORIGINAL.bin.lz]
        --like: compress the result the way ORIGINAL is compressed (if it is LZ)
    python tools/assets/isbin.py test [--jobs N] [--shift]
        every IS .bin in extracted/romfs (LZ-decompressed when needed): dump -> build,
        compare bytes, print the pass rate; failures -> extracted/assets/isbin_fail.txt.
        --shift also inserts 8 bytes at the top of each listing and checks that every
        pointer, label and pooled string followed the edit.
"""
from __future__ import annotations

import argparse
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lz  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
ROMFS = os.path.join(ROOT, "extracted", "romfs")


class BinError(ValueError):
    pass


def is_isbin(d: bytes) -> bool:
    if len(d) < 0x20:
        return False
    fs, ds, c1, c2 = struct.unpack_from("<4I", d, 0)
    if fs != len(d) or 0x20 + ds + c1 * 4 + c2 * 8 > len(d):
        return False
    if c1 == 0 and c2 == 0 and fs != 0x20 + ds:
        return False
    # every relocation must point at an aligned word inside the data region
    p1 = 0x20 + ds
    for i in range(c1):
        x = struct.unpack_from("<I", d, p1 + 4 * i)[0]
        if x + 4 > ds:
            return False
    return True


class IsBin:
    def __init__(self):
        self.data = b""
        self.relocs: list[int] = []
        self.labels: list[tuple[int, bytes, int]] = []  # (data off, name, name off)
        self.strtab = b""
        self.hdrpad = bytes(16)

    @classmethod
    def parse(cls, d: bytes) -> "IsBin":
        if not is_isbin(d):
            raise BinError("not an IS .bin container")
        fs, ds, c1, c2 = struct.unpack_from("<4I", d, 0)
        b = cls()
        b.hdrpad = d[0x10:0x20]
        b.data = d[0x20:0x20 + ds]
        p1 = 0x20 + ds
        b.relocs = list(struct.unpack_from(f"<{c1}I", d, p1))
        p2 = p1 + 4 * c1
        se = p2 + 8 * c2
        b.strtab = d[se:]
        for i in range(c2):
            off, no = struct.unpack_from("<2I", d, p2 + 8 * i)
            e = b.strtab.find(b"\0", no)
            if e < 0:
                raise BinError("label name runs off the end")
            b.labels.append((off, b.strtab[no:e], no))
        return b

    def build(self) -> bytes:
        out = bytearray(struct.pack("<4I", 0, len(self.data), len(self.relocs), len(self.labels)))
        out += self.hdrpad
        out += self.data
        out += struct.pack(f"<{len(self.relocs)}I", *self.relocs)
        for off, _name, no in self.labels:
            out += struct.pack("<2I", off, no)
        out += self.strtab
        struct.pack_into("<I", out, 0, len(out))
        return bytes(out)


# ---------------------------------------------------------------- string tables
def strtab_layout(names: list[bytes], mode: str) -> tuple[bytes, list[int]]:
    out = bytearray()
    offs = []
    seen: dict[bytes, int] = {}
    for n in names:
        if mode == "dedup" and n in seen:
            offs.append(seen[n])
            continue
        seen[n] = len(out)
        offs.append(len(out))
        out += n + b"\0"
    return bytes(out), offs


def detect_strtab(b: IsBin) -> tuple[str, bytes]:
    """Return (mode, tail): mode concat/dedup if the table is reproducible from label
    order (tail = extra bytes after it), else ("raw", b"")."""
    names = [n for _o, n, _no in b.labels]
    for mode in ("concat", "dedup"):
        tab, offs = strtab_layout(names, mode)
        if offs == [no for _o, _n, no in b.labels] and b.strtab.startswith(tab):
            return mode, b.strtab[len(tab):]
    return "raw", b""


# ---------------------------------------------------------------- quoting
_PRINTABLE = re.compile(r"^[^\x00-\x1f\x7f\"\\]*$")


def quote(raw: bytes) -> str:
    try:
        s = raw.decode("cp932")
        if s.encode("cp932") == raw and _PRINTABLE.fullmatch(s):
            return '"' + s + '"'
    except UnicodeError:
        pass
    out = []
    i = 0
    while i < len(raw):
        c = raw[i]
        if 0x20 <= c < 0x7F and c not in (0x22, 0x5C):
            out.append(chr(c))
            i += 1
            continue
        # try a two-byte cp932 char
        if i + 1 < len(raw):
            try:
                ch = raw[i:i + 2].decode("cp932")
                if len(ch) == 1 and ch.encode("cp932") == raw[i:i + 2] and _PRINTABLE.fullmatch(ch) and ord(ch) > 0x7F:
                    out.append(ch)
                    i += 2
                    continue
            except UnicodeError:
                pass
        out.append(f"\\x{c:02x}")
        i += 1
    return '"' + "".join(out) + '"'


def unquote(s: str) -> bytes:
    s = s.strip()
    if not (s.startswith('"') and s.endswith('"')):
        raise BinError(f"expected quoted string: {s}")
    s = s[1:-1]
    out = bytearray()
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 3 < len(s) + 0 and s[i + 1] == "x":
            out.append(int(s[i + 2:i + 4], 16))
            i += 4
        else:
            j = i
            while j < len(s) and s[j] != "\\":
                j += 1
            if j == i:
                raise BinError(f"bad escape in {s!r}")
            out += s[i:j].encode("cp932")
            i = j
    return bytes(out)


def _sym_ok(raw: bytes) -> str | None:
    """Label name usable bare in a .ptr target (ASCII identifier-ish)."""
    try:
        s = raw.decode("ascii")
    except UnicodeError:
        return None
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.$]*", s) and not re.fullmatch(r"L_[0-9A-F]+", s):
        return s
    return None


# ---------------------------------------------------------------- dump
def _sjis_at(data: bytes, pos: int, limit: int) -> int:
    """Length (incl. NUL) of a printable cp932 string at pos, or 0."""
    e = data.find(b"\0", pos, limit)
    if e <= pos:
        return 0
    raw = data[pos:e]
    try:
        s = raw.decode("cp932")
    except UnicodeError:
        return 0
    if s.encode("cp932") != raw or not _PRINTABLE.fullmatch(s):
        return 0
    return e - pos + 1


def build_pool(names: list[bytes], strs: list[bytes]) -> tuple[bytes, list[int], list[int]]:
    """Name table + string pool as the game's tool lays it out: label names in label
    order (no dedup), then every pointed-to string in relocation-table order, skipping
    any string already present as a label name or earlier pool string.
    Returns (table, name offsets, string offsets)."""
    out = bytearray()
    seen: dict[bytes, int] = {}
    noffs = []
    for n in names:
        seen.setdefault(n, len(out))
        noffs.append(len(out))
        out += n + b"\0"
    soffs = []
    for s in strs:
        if s not in seen:
            seen[s] = len(out)
            out += s + b"\0"
        soffs.append(seen[s])
    return bytes(out), noffs, soffs


def pool_pointers(b: IsBin) -> dict[int, bytes] | None:
    """Map reloc offset -> pooled string for pointers that target the name/string table,
    if the table is exactly reproducible by build_pool(); else None."""
    ds = len(b.data)
    se_rel = ds + 4 * len(b.relocs) + 8 * len(b.labels)
    found: list[tuple[int, bytes]] = []
    for off in b.relocs:
        t = struct.unpack_from("<I", b.data, off)[0]
        if t >= se_rel:
            o = t - se_rel
            e = b.strtab.find(b"\0", o)
            if e < 0 or (o > 0 and b.strtab[o - 1] != 0):
                return None
            found.append((off, b.strtab[o:e]))
    tab, noffs, soffs = build_pool([n for _o, n, _no in b.labels], [s for _off, s in found])
    if tab != b.strtab or noffs != [no for _o, _n, no in b.labels]:
        return None
    se = se_rel
    for (off, _s), so in zip(found, soffs):
        if struct.unpack_from("<I", b.data, off)[0] != se + so:
            return None
    return dict(found)


def dump(b: IsBin, source: str = "") -> str:
    ds = len(b.data)
    pooled = pool_pointers(b)
    if pooled is not None:
        mode, tail = "pool", b""
    else:
        pooled = {}
        mode, tail = detect_strtab(b)
    relset = {}
    for k, off in enumerate(b.relocs):
        if off in relset:
            raise BinError("duplicate relocation")
        relset[off] = k
    inside_word = set()
    for off in b.relocs:
        inside_word.update((off + 1, off + 2, off + 3))
    labels_at: dict[int, list[tuple[int, bytes, int]]] = {}
    absolute = []  # labels that cannot be placed inline (inside a pointer word / past end)
    for k, (off, name, no) in enumerate(b.labels):
        if off > ds or off in inside_word:
            absolute.append((k, name, no, off))
        else:
            labels_at.setdefault(off, []).append((k, name, no))
    # symbolic names for pointer targets (only names that are unique in the file)
    count: dict[bytes, int] = {}
    for _off, name, _no in b.labels:
        count[name] = count.get(name, 0) + 1
    sym_at: dict[int, str] = {}
    for off, lst in labels_at.items():
        for _k, name, _no in lst:
            s = _sym_ok(name)
            if s is not None and count[name] == 1 and off not in sym_at:
                sym_at[off] = s
    targets = {}
    for off in b.relocs:
        t = struct.unpack_from("<I", b.data, off)[0]
        targets[off] = t
    local = set()
    for off, t in targets.items():
        if off not in pooled and t <= ds and t not in sym_at and t not in inside_word:
            local.add(t)
    strings_start = set(targets.values()) | set(labels_at)
    lines = [".isbin 1"]
    if source:
        lines.append(f"# source: {source}")
    lines.append(f".strtab {mode}" + (" " + b.strtab.hex() if mode == "raw" else ""))
    if b.hdrpad != bytes(16):
        lines.append(f".hdrpad {b.hdrpad.hex()}")
    if tail:
        lines.append(f".tail {tail.hex()}")
    for k, name, no, off in absolute:
        extra = f" n=0x{no:X}" if mode == "raw" else ""
        lines.append(f"@{quote(name)} t={k}{extra} at=0x{off:X}")
    # cut points: any position where something must start
    cuts = set(relset) | set(labels_at) | local | {ds}
    for off in relset:
        cuts.add(off + 4)
    cuts = sorted(c for c in cuts if 0 <= c <= ds)
    pos = 0
    ci = 0

    def emit_marks(p):
        for k, name, no in labels_at.get(p, []):
            extra = f" n=0x{no:X}" if mode == "raw" else ""
            lines.append(f"@{quote(name)} t={k}{extra}")
        if p in local:
            lines.append(f"L_{p:X}:")

    while pos < ds:
        emit_marks(pos)
        if pos in relset:
            t = targets[pos]
            if pos in pooled:
                tgt = quote(pooled[pos])
            elif t in sym_at:
                tgt = sym_at[t]
            elif t in local:
                tgt = f"L_{t:X}"
            else:
                tgt = f"0x{t:X}"
            lines.append(f".ptr {tgt} r={relset[pos]}")
            pos += 4
            continue
        while ci < len(cuts) and cuts[ci] <= pos:
            ci += 1
        nxt = cuts[ci] if ci < len(cuts) else ds
        # a string where something points at it
        if pos in strings_start:
            n = _sjis_at(b.data, pos, nxt)
            if n and pos + n <= nxt:
                lines.append(".sjis " + quote(b.data[pos:pos + n - 1]))
                pos += n
                continue
        # raw bytes up to the next cut: words when aligned, bytes otherwise
        while pos < nxt:
            if pos % 4 == 0 and pos + 4 <= nxt:
                words = []
                while pos + 4 <= nxt and len(words) < 4:
                    words.append(f"0x{struct.unpack_from('<I', b.data, pos)[0]:08X}")
                    pos += 4
                lines.append(".word " + " ".join(words))
            else:
                n = min(nxt - pos, 4 - pos % 4 if pos % 4 else nxt - pos, 16)
                lines.append(".byte " + " ".join(f"{x:02x}" for x in b.data[pos:pos + n]))
                pos += n
    emit_marks(ds)  # labels at the very end of the data region
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- build
def assemble(text: str) -> bytes:
    data = bytearray()
    labels: list[tuple[int | None, int, bytes, int | None]] = []  # (t, off, name, n)
    syms: dict[str, int] = {}
    ptrs: list[tuple[int, str, int | None]] = []  # (pos, target, r)
    mode = "concat"
    rawtab = b""
    hdrpad = bytes(16)
    tail = b""
    lines = text.splitlines()
    if not lines or lines[0].strip() != ".isbin 1":
        raise BinError("missing '.isbin 1' header")
    for ln, line in enumerate(lines[1:], 2):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        try:
            if s.startswith("@"):
                m = re.fullmatch(r'@(".*?")((?:\s+[tn]=\w+|\s+at=\w+)*)', s)
                if not m:
                    raise BinError("bad label line")
                name = unquote(m.group(1))
                kv = dict(x.split("=", 1) for x in m.group(2).split())
                t = int(kv["t"]) if "t" in kv else None
                n = int(kv["n"], 16) if "n" in kv else None
                at = int(kv["at"], 16) if "at" in kv else None
                labels.append((t, len(data) if at is None else at, name, n))
                sy = _sym_ok(name)
                if sy is not None and at is None:
                    syms.setdefault(sy, len(data))
            elif s.endswith(":") and " " not in s:
                syms[s[:-1]] = len(data)
            elif s.startswith(".ptr "):
                m = re.fullmatch(r'\.ptr\s+(".*?"|\S+)(?:\s+r=(\d+))?', s)
                if not m:
                    raise BinError("bad .ptr line")
                r = int(m.group(2)) if m.group(2) else None
                ptrs.append((len(data), m.group(1), r))
                data += bytes(4)
            elif s.startswith(".word "):
                for w in s[6:].split():
                    data += struct.pack("<I", int(w, 0) & 0xFFFFFFFF)
            elif s.startswith(".byte "):
                data += bytes(int(x, 16) for x in s[6:].split())
            elif s.startswith(".sjis "):
                data += unquote(s[6:]) + b"\0"
            elif s.startswith(".strtab "):
                parts = s.split()
                mode = parts[1]
                if mode == "raw":
                    rawtab = bytes.fromhex(parts[2]) if len(parts) > 2 else b""
            elif s.startswith(".hdrpad "):
                hdrpad = bytes.fromhex(s.split()[1])
            elif s.startswith(".tail "):
                tail = bytes.fromhex(s.split()[1])
            else:
                raise BinError("unknown directive")
        except (ValueError, BinError) as e:
            raise BinError(f"line {ln}: {e}: {line!r}") from None
    b = IsBin()
    b.hdrpad = hdrpad
    big = 1 << 40
    order = sorted(ptrs, key=lambda p: (p[2] if p[2] is not None else big, p[0]))
    b.relocs = [p[0] for p in order]
    lorder = sorted(range(len(labels)), key=lambda i: (labels[i][0] if labels[i][0] is not None else big, labels[i][1], i))
    names = [labels[i][2] for i in lorder]
    pool_val: dict[int, int] = {}
    if mode == "pool":
        strs = [(p[0], unquote(p[1])) for p in order if p[1].startswith('"')]
        tab, noffs, soffs = build_pool(names, [x[1] for x in strs])
        se_rel = len(data) + 4 * len(ptrs) + 8 * len(labels)
        pool_val = {pos: se_rel + so for (pos, _s), so in zip(strs, soffs)}
    elif any(p[1].startswith('"') for p in ptrs):
        raise BinError("string pointer targets need '.strtab pool'")
    # pointers
    for pos, tgt, _r in ptrs:
        if pos in pool_val:
            v = pool_val[pos]
        elif tgt in syms:
            v = syms[tgt]
        else:
            try:
                v = int(tgt, 0)
            except ValueError:
                raise BinError(f"undefined pointer target {tgt}") from None
        struct.pack_into("<I", data, pos, v)
    b.data = bytes(data)
    if mode == "pool":
        b.strtab = tab
        b.labels = [(labels[i][1], labels[i][2], o) for i, o in zip(lorder, noffs)]
    elif mode == "raw":
        b.strtab = rawtab
        b.labels = []
        for i in lorder:
            t, off, name, n = labels[i]
            if n is None:  # new label in a raw table: append its name
                n = len(b.strtab)
                b.strtab += name + b"\0"
            b.labels.append((off, name, n))
    else:
        tab, offs = strtab_layout(names, mode)
        b.strtab = tab + tail
        b.labels = [(labels[i][1], labels[i][2], o) for i, o in zip(lorder, offs)]
    return b.build()


# ---------------------------------------------------------------- test
def load_maybe_lz(path: str) -> tuple[bytes, bool]:
    with open(path, "rb") as fh:
        d = fh.read()
    if lz.lz_type(d) is not None and (path.lower().endswith(".lz") or d[0] == 0x13):
        return lz.decompress(d), True
    return d, False


SHIFT_TEST = False


def _strz(tab: bytes, o: int) -> bytes:
    return tab[o:tab.index(b"\0", o)]


def shift_ok(orig: bytes, txt: str) -> bool:
    """Edit test: insert 8 bytes before the first data item of the listing, rebuild and
    check that every relocation, label and pooled string followed the move (internal
    pointers +8, pooled strings unchanged, all other bytes unchanged)."""
    lines = txt.split("\n")
    if any(" at=0x" in ln for ln in lines):
        return True  # absolute label positions do not follow edits by design
    i = 1
    while i < len(lines) and lines[i].startswith((".strtab", ".hdrpad", ".tail", "#")):
        i += 1
    edited = "\n".join(lines[:i] + [".word 0x5AFE5AFE 0x5AFE5AFE"] + lines[i:])
    old = IsBin.parse(orig)
    new = IsBin.parse(assemble(edited))
    ds = len(old.data)
    if new.relocs != [r + 8 for r in old.relocs]:
        return False
    if [(o + 8, n) for o, n, _ in old.labels] != [(o, n) for o, n, _ in new.labels]:
        return False
    od = bytearray(old.data)
    nd = bytearray(new.data[8:])
    ose = ds + 4 * len(old.relocs) + 8 * len(old.labels)
    nse = ose + 8
    for ro, rn in zip(old.relocs, new.relocs):
        t = struct.unpack_from("<I", old.data, ro)[0]
        u = struct.unpack_from("<I", new.data, rn)[0]
        if t >= ose:
            if _strz(old.strtab, t - ose) != _strz(new.strtab, u - nse):
                return False
        elif t <= ds:
            if u != t + 8:
                return False
        elif u != t:
            return False
        od[ro:ro + 4] = bytes(4)
        nd[ro:ro + 4] = bytes(4)
    return od == nd and new.data[:8] == b"\xfeZ\xfeZ\xfeZ\xfeZ"


def _init_worker(shift: bool) -> None:
    global SHIFT_TEST
    SHIFT_TEST = shift


def _test_one(path: str):
    try:
        d, _ = load_maybe_lz(path)
    except lz.LZError:
        return path, None, "lz"
    if not is_isbin(d):
        return path, None, "not isbin"
    try:
        b = IsBin.parse(d)
        txt = dump(b, os.path.relpath(path, ROMFS))
        ok = assemble(txt) == d
        mode = "pool" if pool_pointers(b) is not None else detect_strtab(b)[0]
        if ok and SHIFT_TEST:
            ok = shift_ok(d, txt)
            if not ok:
                mode = "shift test failed"
        return path, ok, mode
    except BinError as e:
        return path, False, str(e)


def test(jobs: int, shift: bool = False) -> tuple[int, int]:
    from concurrent.futures import ProcessPoolExecutor
    files = []
    for dp, _dn, fn in os.walk(ROMFS):
        for f in fn:
            files.append(os.path.join(dp, f))
    files.sort()
    n = ok = 0
    modes: dict[str, int] = {}
    fails = []
    with ProcessPoolExecutor(max_workers=jobs, initializer=_init_worker, initargs=(shift,)) as ex:
        for path, res, info in ex.map(_test_one, files, chunksize=8):
            if res is None:
                continue
            n += 1
            ok += res
            if res:
                modes[info] = modes.get(info, 0) + 1
            else:
                fails.append(f"{os.path.relpath(path, ROMFS)}\t{info}")
    print(f"IS .bin containers: {ok}/{n} rebuild byte-identically{' + pass the shift test' if shift else ''} "
          f"({100.0 * ok / max(n, 1):.2f}%); name-table modes: {modes}")
    os.makedirs(os.path.join(ROOT, "extracted", "assets"), exist_ok=True)
    with open(os.path.join(ROOT, "extracted", "assets", "isbin_fail.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(fails) + "\n")
    return ok, n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("dump", "build", "test"))
    ap.add_argument("inp", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--like", help="build: compress like this original file")
    ap.add_argument("--shift", action="store_true", help="test: also run the 8-byte insertion test")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    if a.cmd == "test":
        ok, n = test(a.jobs, a.shift)
        return 0 if ok == n else 1
    if not (a.inp and a.out):
        ap.error("need IN and OUT")
    if a.cmd == "dump":
        d, _ = load_maybe_lz(a.inp)
        with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(dump(IsBin.parse(d), os.path.basename(a.inp)))
    else:
        with open(a.inp, encoding="utf-8") as fh:
            out = assemble(fh.read())
        if a.like:
            with open(a.like, "rb") as fh:
                out = lz.compress_like(out, fh.read())
        with open(a.out, "wb") as fh:
            fh.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
