"""Shared code for the typed data-table layouts (tools/tables/*.py), Fire Emblem Fates.

Standard library only. Reuses tools/assets/isbin.py (IS .bin container parse/build, the
game's string-pool rule) and tools/assets/lz.py (LZ13) by import; neither is modified.

Registry: config/tables/tables.csv
    table,file,start,count,record_size,layout,code_global,count_global,description
    file    RomFS path relative to extracted/romfs/; several patterns may be joined with
            ';' and each may contain one '*' (a table spread over several files, e.g. the
            per-chapter Person files). A table whose file field contains '*' is
            "multi-file": its dump gets a leading file column.
    start   where record 0 is, in the container's data region:
              EXPR                    an address expression (below)
              label:NAME[+N]          offset of an exported label, plus N
              family:PFX_             first label with that prefix
              offset:N                same as the expression N
    count   how many records:
              u8@EXPR | u16@EXPR | u32@EXPR   integer stored at that address
              header:N                u32 at data offset N (= u32@N)
              label:NAME              u32 stored at that label
              family:PFX_             number of labels with that prefix
              one                     exactly one record
              fixed:N                 exactly N records: for tables the game indexes
                                      without a stored count (WeaponBonus::Get(ItemKind)
                                      ...); check.py proves N against the file (the table
                                      must end at the next pointer target or label, with
                                      only zero bytes in between)
              span                    up to the next exported label, or the end of data
              zterm                   records up to (not including) the first all-zero
                                      record (that terminator stays outside the table)
    EXPR    terms joined by '+': a number (0x.. or decimal), or [EXPR] = the u32 stored at
            EXPR (a relocated pointer: data offsets are what the file stores).
            Example: Person in GameData.bin is start [0x8]+0x10, count u16@[0x8]+0x4:
            the header word at 0x8 points at the Person block, whose 16-byte header holds
            the record count at +4.
    layout  layout file name (config/tables/<layout>.csv); empty = the table name. Lets
            several tables share one layout (Person and PersonChapter).
    code_global, count_global   kept for tools/readable/gen_structs.py; empty for Fates
            (its tables are reached through linked "archive" nodes, not one global).

Layouts: config/tables/<layout>.csv
    offset,size,type,name,confidence,evidence[,elements]
    types  u8 s8 u16 s16 u32 s32 u64        plain integers (little-endian)
           T[n]                              array of n integers of type T
           hex[n]                            n raw bytes shown as one hex string cell
           str                               relocated pointer to a Shift-JIS string in
                                             the container's string pool, 0 = none
           str:self                          str that equals a label name exported at the
                                             record's own start (the record's ID)
           ptr:TABLE                         relocated pointer to a record of TABLE in the
                                             same file, 0 = none
           ptr                               relocated pointer to other data, 0 = none
           flagsN:IDTABLE                    N-bit bit set; bit k = ID-list entry number k
           enumN:IDTABLE                     N-bit value that is an ID-list entry number
           refN:TABLE[n]                     N-bit index of a TABLE record (all-ones = none);
                                             optional [n] for an array of n indexes
           pad                               bytes that are zero in every record
    ID lists: a table of 4-byte records (u32 number, label = the ID's name, e.g. SPID_女性
           = 0) or 8-byte records (name pointer + u32 number).
    elements  optional, '|'-separated element names for arrays (dump column suffixes)

Nothing in config/tables/ holds game values: only offsets, sizes, types, names and the
evidence for them.
"""
from __future__ import annotations

import csv
import fnmatch
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "assets"))
import isbin  # noqa: E402
import lz  # noqa: E402

ROMFS = os.path.join(ROOT, "extracted", "romfs")
CONFIG = os.path.join(ROOT, "config", "tables")
OUTDIR = os.path.join(ROOT, "build", "tables")
NUL = bytes(1)

INT_TYPES = {"u8": (1, False), "s8": (1, True), "u16": (2, False), "s16": (2, True),
             "u32": (4, False), "s32": (4, True), "u64": (8, False)}
FMT = {(1, False): "B", (1, True): "b", (2, False): "H", (2, True): "h", (4, False): "I",
       (4, True): "i", (8, False): "Q"}
NUM = re.compile(r"-?(?:0x[0-9A-Fa-f]+|\d+)")


class LayoutError(ValueError):
    pass


# ------------------------------------------------------------------ registry
class TableDef:
    def __init__(self, row: dict):
        self.name = row["table"]
        self.file = row["file"]
        self.start = row["start"]
        self.count = row["count"]
        self.size = int(row["record_size"], 0)
        self.layout = (row.get("layout") or "").strip() or self.name
        self.code_global = row.get("code_global", "") or ""
        self.count_global = row.get("count_global", "") or ""
        self.description = row.get("description", "")

    @property
    def multi(self) -> bool:
        return "*" in self.file

    def files(self) -> list[str]:
        out: list[str] = []
        for pat in self.file.split(";"):
            pat = pat.strip()
            if "*" not in pat:
                out.append(pat)
                continue
            d = os.path.dirname(pat)
            full = os.path.join(ROMFS, d)
            if os.path.isdir(full):
                out += sorted(f"{d}/{n}" for n in os.listdir(full)
                              if fnmatch.fnmatch(n, os.path.basename(pat))
                              and os.path.isfile(os.path.join(full, n)))
        return out


_REG: dict[str, TableDef] | None = None


def registry() -> dict[str, TableDef]:
    global _REG
    out = {}
    with open(os.path.join(CONFIG, "tables.csv"), newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["table"] and not row["table"].startswith("#"):
                out[row["table"]] = TableDef(row)
    _REG = out
    return out


def _reg() -> dict[str, TableDef]:
    return _REG if _REG is not None else registry()


# ------------------------------------------------------------------ containers
class Container:
    """One IS .bin file (LZ-decompressed) with label / relocation indexes."""

    def __init__(self, rel: str, raw: bytes | None = None):
        self.rel = rel
        self.path = os.path.join(ROMFS, rel.replace("/", os.sep))
        if raw is None:
            with open(self.path, "rb") as fh:
                raw = fh.read()
        self.raw = raw
        if lz.lz_type(self.raw) is not None and (rel.lower().endswith(".lz") or self.raw[0] == 0x13):
            self.dec = lz.decompress(self.raw)
            self.is_lz = True
        else:
            self.dec = self.raw
            self.is_lz = False
        self._index()

    @classmethod
    def from_dec(cls, like: "Container", dec: bytes) -> "Container":
        """A container made from decompressed bytes in memory (after records were
        inserted), stored and compressed like `like` (its .raw stays the original file,
        so rebuild() compresses the result the same way)."""
        self = cls.__new__(cls)
        self.rel, self.path, self.raw, self.is_lz, self.dec = like.rel, like.path, like.raw, like.is_lz, dec
        self._index()
        return self

    def _index(self) -> None:
        self.b = isbin.IsBin.parse(self.dec)
        self.data = self.b.data
        self.relset = set(self.b.relocs)
        self.se = len(self.data) + 4 * len(self.b.relocs) + 8 * len(self.b.labels)
        self.labels_at: dict[int, list[bytes]] = {}
        self.label_off: dict[bytes, int] = {}
        for off, name, _no in self.b.labels:
            self.labels_at.setdefault(off, []).append(name)
            self.label_off.setdefault(name, off)

    def u32(self, off: int) -> int:
        return struct.unpack_from("<I", self.data, off)[0]

    def string_at(self, ptr: int) -> bytes | None:
        """Bytes of the NUL-terminated string a pointer value refers to (pool or data)."""
        if ptr >= self.se:
            o = ptr - self.se
            e = self.b.strtab.find(NUL, o)
            return None if e < 0 else self.b.strtab[o:e]
        e = self.data.find(NUL, ptr)
        return None if e < 0 else self.data[ptr:e]

    def family(self, prefix: bytes) -> list[int]:
        return sorted({o for o, n, _ in self.b.labels if n.startswith(prefix)})


_CACHE: dict[str, Container] = {}


def container(rel: str) -> Container:
    if rel not in _CACHE:
        _CACHE[rel] = Container(rel)
    return _CACHE[rel]


def _split_plus(s: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "+" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def eval_expr(expr: str, c: Container) -> int:
    """Address expression: terms joined by '+'; a term is a number or [EXPR] (u32 at EXPR)."""
    total = 0
    for term in _split_plus(expr.strip()):
        term = term.strip()
        if term.startswith("[") and term.endswith("]"):
            a = eval_expr(term[1:-1], c)
            if a + 4 > len(c.data):
                raise LayoutError(f"{c.rel}: [{term[1:-1]}] = [{a:#x}] is outside the data region")
            total += c.u32(a)
        elif NUM.fullmatch(term):
            total += int(term, 0)
        else:
            raise LayoutError(f"bad address term {term!r} in {expr!r}")
    return total


def locate(t: TableDef, c: Container) -> tuple[int, int]:
    """(start offset, record count) of table t inside container c."""
    kind, _, arg = t.start.partition(":")
    if kind == "label":
        name, _, plus = arg.partition("+")
        start = c.label_off[name.encode()] + (int(plus, 0) if plus else 0)
    elif kind == "family":
        offs = c.family(arg.encode())
        if not offs:
            raise LayoutError(f"{t.name}: no labels with prefix {arg}")
        start = offs[0]
    elif kind == "offset":
        start = int(arg, 0)
    else:
        start = eval_expr(t.start, c)
    m = re.fullmatch(r"(u8|u16|u32)@(.+)", t.count)
    kind, _, arg = t.count.partition(":")
    if m:
        a = eval_expr(m.group(2), c)
        w = {"u8": 1, "u16": 2, "u32": 4}[m.group(1)]
        count = int.from_bytes(c.data[a:a + w], "little")
    elif kind == "label":
        count = c.u32(c.label_off[arg.encode()])
    elif kind == "family":
        count = len(c.family(arg.encode()))
    elif kind == "header":
        count = c.u32(int(arg, 0))
    elif t.count == "one":
        count = 1
    elif kind == "fixed":
        count = int(arg, 0)
    elif t.count == "span":
        nxt = min((o for o in c.labels_at if o > start), default=len(c.data))
        count = (nxt - start) // t.size
        if count * t.size != nxt - start:
            raise LayoutError(f"{t.name}: {nxt - start:#x} bytes to the next label is not a multiple of {t.size:#x}")
    elif t.count == "zterm":
        count = 0
        while start + (count + 1) * t.size <= len(c.data) and \
                any(c.data[start + count * t.size:start + (count + 1) * t.size]):
            count += 1
    else:
        raise LayoutError(f"{t.name}: bad count {t.count}")
    if start < 0 or start + count * t.size > len(c.data):
        raise LayoutError(f"{t.name}: {count} x {t.size:#x} from {start:#x} runs past the data region of {c.rel}")
    return start, count


# ------------------------------------------------------------------ layouts
class Field:
    def __init__(self, row: dict, table: str):
        self.table = table
        self.offset = int(row["offset"], 0)
        self.size = int(row["size"], 0)
        self.type = row["type"].strip()
        self.name = row["name"].strip()
        self.confidence = row["confidence"].strip()
        self.evidence = row["evidence"].strip()
        el = (row.get("elements") or "").strip()
        self.elements = el.split("|") if el else []
        self.kind, self.width, self.signed, self.n, self.ref = self._parse()
        if self.kind == "int" and self.width * self.n != self.size:
            raise LayoutError(f"{table}+{self.offset:#x} {self.name}: type {self.type} is "
                              f"{self.width * self.n} bytes, size says {self.size}")
        if self.kind == "hex" and self.n != self.size:
            raise LayoutError(f"{table}+{self.offset:#x}: hex[{self.n}] with size {self.size}")
        if self.kind in ("str", "ptr", "lptr") and self.size != 4:
            raise LayoutError(f"{table}+{self.offset:#x}: pointers are 4 bytes")
        if self.kind in ("flags", "ref", "enum") and self.width * self.n != self.size:
            raise LayoutError(f"{table}+{self.offset:#x}: {self.type} is {self.width * self.n} bytes")
        if self.elements and len(self.elements) != self.n:
            raise LayoutError(f"{table}+{self.offset:#x}: {len(self.elements)} element names for {self.n}")
        if self.confidence not in ("high", "medium", "low"):
            raise LayoutError(f"{table}+{self.offset:#x}: confidence must be high/medium/low")

    def _parse(self):
        t = self.type
        m = re.fullmatch(r"(u8|s8|u16|s16|u32|s32|u64)(?:\[(\d+)\])?", t)
        if m:
            w, s = INT_TYPES[m.group(1)]
            return "int", w, s, int(m.group(2) or 1), None
        m = re.fullmatch(r"hex\[(\d+)\]", t)
        if m:
            return "hex", 1, False, int(m.group(1)), None
        if t == "str":
            return "str", 4, False, 1, None
        if t == "str:self":
            return "str", 4, False, 1, "self"
        if t == "ptr":
            return "ptr", 4, False, 1, None
        m = re.fullmatch(r"ptr:(\w+)", t)
        if m:
            return "lptr", 4, False, 1, m.group(1)
        m = re.fullmatch(r"flags(8|16|32|64):(\w+)", t)
        if m:
            return "flags", int(m.group(1)) // 8, False, 1, m.group(2)
        m = re.fullmatch(r"enum(8|16|32):(\w+)", t)
        if m:
            return "enum", int(m.group(1)) // 8, False, 1, m.group(2)
        m = re.fullmatch(r"ref(8|16):(\w+)(?:\[(\d+)\])?", t)
        if m:
            return "ref", int(m.group(1)) // 8, False, int(m.group(3) or 1), m.group(2)
        if t == "pad":
            return "pad", 1, False, self.size, None
        raise LayoutError(f"{self.table}+{self.offset:#x}: unknown type {t}")

    def columns(self) -> list[str]:
        if self.kind == "pad":
            return []
        if self.n > 1 and self.kind in ("int", "ref"):
            names = self.elements or [str(i) for i in range(self.n)]
            return [f"{self.name}.{e}" for e in names]
        return [self.name]


def layout_path(table: str) -> str:
    """config/tables/<layout>.csv for a table (its own name unless the registry names a
    shared layout)."""
    try:
        t = _reg().get(table)
    except FileNotFoundError:
        t = None
    return os.path.join(CONFIG, f"{t.layout if t else table}.csv")


def load_layout(table: str) -> list[Field]:
    with open(layout_path(table), newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["offset"] and not r["offset"].startswith("#")]
    for r in rows:
        if None in r:
            raise LayoutError(f"{layout_path(table)}: row +{r['offset']} has extra cells (an unquoted comma?)")
    fields = [Field(r, table) for r in rows]
    fields.sort(key=lambda f: f.offset)
    return fields


def tile_errors(fields: list[Field], size: int) -> list[str]:
    errs = []
    pos = 0
    for f in fields:
        if f.offset != pos:
            errs.append(f"gap or overlap at +{pos:#x} (next field starts at +{f.offset:#x})")
        pos = f.offset + f.size
    if pos != size:
        errs.append(f"fields end at +{pos:#x}, record size is {size:#x}")
    return errs


# ------------------------------------------------------------------ ID lists
def id_names(idtable: str, reg: dict[str, TableDef]) -> list[bytes]:
    """number -> name for an ID-list table. 4-byte records: u32 number, the name is the
    label at the record (Fates: SPID_, ISID_, IUID_, JCID_). 8-byte records: name pointer
    + u32 number (the Awakening form)."""
    t = reg[idtable]
    c = container(t.files()[0])
    start, count = locate(t, c)
    names: dict[int, bytes] = {}
    for i in range(count):
        o = start + i * t.size
        if t.size == 4:
            labs = c.labels_at.get(o, [])
            names[c.u32(o)] = labs[0] if labs else b""
        else:
            names[c.u32(o + 4)] = c.string_at(c.u32(o)) or b""
    return [names.get(k, b"") for k in range(max(names) + 1 if names else 0)]


def text(raw: bytes) -> str:
    """Readable form of a Shift-JIS string; undecodable bytes as \\xNN (isbin.quote rules)."""
    return isbin.quote(raw)[1:-1]


def untext(s: str) -> bytes:
    return isbin.unquote('"' + s + '"')


# ------------------------------------------------------------------ record codec
EMPTY_STR = '""'  # cell for a pointer to an empty string (an empty cell means "no pointer")


def record_labels(t: TableDef, c: Container, start: int, count: int) -> list[bytes]:
    """Label exported at each record's start (b'' if none). Where a table label shares
    the offset with its first record, the record's own label wins."""
    tlabel = t.start.partition(":")[2].partition("+")[0].encode() if t.start.startswith("label:") else b""
    out = []
    for i in range(count):
        names = [n for n in c.labels_at.get(start + i * t.size, []) if n != tlabel]
        out.append(names[0] if names else b"")
    return out


class Codec:
    """Turns records into spreadsheet cells and back, for one table."""

    def __init__(self, reg: dict[str, TableDef], name: str):
        self.reg = reg
        self.t = reg[name]
        self.fields = load_layout(name)
        self._ids: dict[str, list[bytes]] = {}
        self._reflabels: dict[tuple[str, str], list[bytes]] = {}
        self._starts: dict[tuple[str, str], tuple[Container, tuple[int, int]]] = {}

    def columns(self) -> list[str]:
        cols = ["file"] if self.t.multi else []
        cols += ["index", "label"]
        for f in self.fields:
            cols += f.columns()
        return cols

    def ids(self, idt: str) -> list[bytes]:
        if idt not in self._ids:
            self._ids[idt] = id_names(idt, self.reg)
        return self._ids[idt]

    def reflabels(self, tname: str, rel: str) -> list[bytes]:
        key = (tname, rel)
        if key not in self._reflabels:
            rt = self.reg[tname]
            r = rel if rel in rt.files() else rt.files()[0]
            c = container(r)
            s, n = locate(rt, c)
            self._reflabels[key] = record_labels(rt, c, s, n)
        return self._reflabels[key]

    def target(self, tname: str, c: Container) -> tuple[int, int]:
        """(start, count) of table tname in the same container (for ptr:T fields)."""
        key = (tname, c.rel)
        hit = self._starts.get(key)
        if hit is None or hit[0] is not c:          # cached per container object
            hit = self._starts[key] = (c, locate(self.reg[tname], c))
        return hit[1]

    # -------------------------------------------------------------- decode
    def decode(self, c: Container, i: int, base: int, label: bytes) -> list[str]:
        row = ([c.rel] if self.t.multi else []) + [str(i), text(label)]
        for f in self.fields:
            o = base + f.offset
            if f.kind == "pad":
                continue
            if f.kind == "int":
                for k in range(f.n):
                    v = int.from_bytes(c.data[o + k * f.width:o + (k + 1) * f.width], "little", signed=f.signed)
                    row.append(str(v))
            elif f.kind == "hex":
                row.append(c.data[o:o + f.n].hex())
            elif f.kind == "ref":
                labs = self.reflabels(f.ref, c.rel)
                for k in range(f.n):
                    v = int.from_bytes(c.data[o + k * f.width:o + (k + 1) * f.width], "little")
                    if v == (1 << (8 * f.width)) - 1:
                        row.append("none")
                    elif v < len(labs) and labs[v] and labs.index(labs[v]) == v:
                        row.append(text(labs[v]))
                    else:
                        row.append(str(v))
            elif f.kind == "enum":
                v = int.from_bytes(c.data[o:o + f.width], "little")
                names = self.ids(f.ref)
                ok = v < len(names) and names[v] and names.index(names[v]) == v
                row.append(text(names[v]) if ok else str(v))
            elif f.kind == "flags":
                v = int.from_bytes(c.data[o:o + f.width], "little")
                names = self.ids(f.ref)
                parts = []
                for b in range(8 * f.width):
                    if v >> b & 1:
                        ok = b < len(names) and names[b] and names.index(names[b]) == b
                        parts.append(text(names[b]) if ok else f"bit{b}")
                row.append("|".join(parts))
            else:
                v = c.u32(o)
                if o not in c.relset:
                    row.append("" if v == 0 else f"={v}")
                elif f.kind == "str" and v >= c.se:
                    s = c.string_at(v)
                    row.append(text(s) if s else EMPTY_STR)
                elif f.kind == "lptr":
                    names = [n for n in c.labels_at.get(v, []) if c.label_off[n] == v]
                    if names:
                        row.append(text(names[-1]))
                    else:
                        s, n = self.target(f.ref, c)
                        k, r = divmod(v - s, self.reg[f.ref].size)
                        row.append(f"#{k}" if r == 0 and 0 <= k < n else f"@0x{v:X}")
                else:
                    row.append(f"@0x{v:X}")
        return row

    # -------------------------------------------------------------- encode
    def encode(self, c: Container, data: bytearray, i: int, base: int, cells: list[str],
               ptrs: dict[int, tuple[str, object]]) -> None:
        """Write one record's cells (without file/index/label) into data. Pointer fields
        are collected in ptrs[pos] = ("null", 0) | ("str", bytes) | ("off", data offset)
        | ("raw", value: a non-relocated word, kept as is)."""
        it = iter(cells)
        for f in self.fields:
            o = base + f.offset
            if f.kind == "pad":
                data[o:o + f.size] = bytes(f.size)
                continue
            if f.kind == "int":
                for k in range(f.n):
                    v = int(next(it), 0)
                    data[o + k * f.width:o + (k + 1) * f.width] = v.to_bytes(f.width, "little", signed=f.signed)
            elif f.kind == "hex":
                b = bytes.fromhex(next(it))
                if len(b) != f.n:
                    raise LayoutError(f"{self.t.name}.{f.name}: {len(b)} bytes, need {f.n}")
                data[o:o + f.n] = b
            elif f.kind == "ref":
                labs = self.reflabels(f.ref, c.rel)
                for k in range(f.n):
                    s = next(it)
                    if s == "none":
                        v = (1 << (8 * f.width)) - 1
                    elif NUM.fullmatch(s):
                        v = int(s, 0)
                    else:
                        v = labs.index(untext(s))
                    data[o + k * f.width:o + (k + 1) * f.width] = v.to_bytes(f.width, "little")
            elif f.kind == "enum":
                s = next(it)
                v = int(s, 0) if NUM.fullmatch(s) else self.ids(f.ref).index(untext(s))
                data[o:o + f.width] = v.to_bytes(f.width, "little")
            elif f.kind == "flags":
                s = next(it)
                names = self.ids(f.ref)
                v = 0
                for part in filter(None, s.split("|")):
                    m = re.fullmatch(r"bit(\d+)", part)
                    v |= 1 << (int(m.group(1)) if m else names.index(untext(part)))
                data[o:o + f.width] = v.to_bytes(f.width, "little")
            else:
                s = next(it)
                if s == "":
                    ptrs[o] = ("null", 0)
                elif s.startswith("=") and NUM.fullmatch(s[1:]):
                    ptrs[o] = ("raw", int(s[1:], 0))
                elif f.kind == "str":
                    ptrs[o] = ("str", b"" if s == EMPTY_STR else untext(s))
                elif s.startswith("@0x"):
                    ptrs[o] = ("off", int(s[1:], 16))
                elif s.startswith("#") and f.kind == "lptr" and s[1:].isdigit():
                    st, n = self.target(f.ref, c)
                    k = int(s[1:])
                    if k >= n:
                        raise LayoutError(f"{self.t.name}.{f.name}: {s} but {f.ref} has {n} records")
                    ptrs[o] = ("off", st + k * self.reg[f.ref].size)
                else:
                    ptrs[o] = ("off", c.label_off[untext(s)])


def rebuild(c: Container, data: bytearray, ptrs: dict[int, tuple[str, object]]) -> bytes:
    """Rebuild container c from a new data region plus pointer assignments, with the
    game's string-pool rule (isbin.build_pool) and the original relocation order (new
    pointers go last, in position order). Returns the stored file bytes, LZ-recompressed
    the way the original was (lz.compress_like) when it was LZ."""
    pooled = isbin.pool_pointers(c.b)
    if pooled is None:
        raise LayoutError(f"{c.rel}: string table is not in the game's pool layout")
    relocs = [r for r in c.b.relocs if ptrs.get(r, ("keep",))[0] not in ("null", "raw")]
    have = set(relocs)
    relocs += sorted(p for p, (k, _v) in ptrs.items() if k not in ("null", "raw") and p not in have)
    for p, (k, v) in ptrs.items():
        if k == "null":
            data[p:p + 4] = bytes(4)
        elif k in ("off", "raw"):
            struct.pack_into("<I", data, p, v)
    strs, spos = [], []
    for r in relocs:
        k, v = ptrs.get(r, ("keep", None))
        if k == "str":
            strs.append(v)
            spos.append(r)
        elif k == "keep" and r in pooled:
            strs.append(pooled[r])
            spos.append(r)
    names = [n for _o, n, _no in c.b.labels]
    tab, noffs, soffs = isbin.build_pool(names, strs)
    se_rel = len(data) + 4 * len(relocs) + 8 * len(c.b.labels)
    for r, so in zip(spos, soffs):
        struct.pack_into("<I", data, r, se_rel + so)
    nb = isbin.IsBin()
    nb.hdrpad = c.b.hdrpad
    nb.data = bytes(data)
    nb.relocs = relocs
    nb.labels = [(o, n, no) for (o, n, _), no in zip(c.b.labels, noffs)]
    nb.strtab = tab
    out = nb.build()
    if c.is_lz:
        out = lz.compress_like(out, c.raw)
    return out


# ------------------------------------------------------------------ appending records
# config/tables/appends.csv says, per table, whether new records may be added at the end
# and why (the code evidence: how the game counts and numbers the records, and whether
# any fixed-size array or bit set is sized by that count). A table that is not listed is
# refused. Columns: table,policy,number_field,label_prefix,evidence
#   policy        allow | refuse
#   number_field  the field that must hold the record's number (first record's number +
#                 index), e.g. Item.item_number; empty = none
#   label_prefix  every new record's label (its ID) must start with this, e.g. IID_
#   refuse_if_files  RomFS glob(s), ';'-joined: appends are refused while such a file
#                 exists (archives that would number their records where the new ones go)
APPENDS = os.path.join(CONFIG, "appends.csv")


class AppendPolicy:
    def __init__(self, table: str, allow: bool, number_field: str, prefix: str, evidence: str,
                 refuse_if: str = ""):
        self.table, self.allow, self.number_field, self.prefix, self.evidence = \
            table, allow, number_field, prefix, evidence
        self.refuse_if = refuse_if


def append_policies() -> dict[str, AppendPolicy]:
    out: dict[str, AppendPolicy] = {}
    if not os.path.isfile(APPENDS):
        return out
    with open(APPENDS, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            name = (r.get("table") or "").strip()
            if not name or name.startswith("#"):
                continue
            pol = (r.get("policy") or "").strip()
            if pol not in ("allow", "refuse"):
                raise LayoutError(f"{APPENDS}: {name}: policy must be allow or refuse, not {pol!r}")
            out[name] = AppendPolicy(name, pol == "allow", (r.get("number_field") or "").strip(),
                                     (r.get("label_prefix") or "").strip(), (r.get("evidence") or "").strip(),
                                     (r.get("refuse_if_files") or "").strip())
    return out


def append_refusal(t: TableDef, policies: dict[str, AppendPolicy] | None = None) -> str | None:
    """None when records may be appended to table t, else the reason (with the evidence)."""
    if t.count.startswith("fixed:") or t.count == "one":
        return (f"{t.name} has no stored count (registry count {t.count}): the game indexes a fixed "
                "number of rows, so its size can only change together with the code")
    if t.multi:
        return f"{t.name} is spread over several files; adding records to it is not supported"
    pol = (append_policies() if policies is None else policies).get(t.name)
    if pol is None:
        return (f"nobody has checked in the code how the game counts and numbers {t.name} records "
                f"(no row in config/tables/appends.csv), so adding records is refused")
    if not pol.allow:
        return f"adding {t.name} records is refused: {pol.evidence}"
    for pat in filter(None, (p.strip() for p in pol.refuse_if.split(";"))):
        d = os.path.join(ROMFS, os.path.dirname(pat))
        hits = sorted(n for n in os.listdir(d) if fnmatch.fnmatch(n, os.path.basename(pat)))             if os.path.isdir(d) else []
        if hits:
            return (f"adding {t.name} records is refused while {os.path.dirname(pat)}/{hits[0]} exists: "
                    "such an archive numbers its records from the resident count, where the new ones go")
    if not re.fullmatch(r"(u8|u16|u32)@.+|header:.+", t.count):
        return f"{t.name}: its count ({t.count}) is not a stored integer the build can update"
    return None


def insert_bytes(c: Container, at: int, nbytes: int, new_labels: list[tuple[int, bytes]]) -> Container:
    """Open a gap of nbytes zero bytes at data offset `at` and export new_labels
    [(offset inside the gap, name)]. Every relocated pointer to `at` or beyond, every
    relocation position and every label offset at or beyond `at` moves by nbytes; pooled
    strings are re-pooled with the game's rule. The relocation order is kept; new labels
    go into the label table after the last label before `at` (the tables keep their
    labels in offset order). Non-relocated words are never changed (a stored offset that
    is not a relocated pointer would be wrong afterwards; check.py looks at every table)."""
    if nbytes % 8:
        raise LayoutError(f"{c.rel}: an insertion of {nbytes:#x} bytes would break the 8-byte "
                          "alignment of everything after it")
    pooled = isbin.pool_pointers(c.b)
    if pooled is None:
        raise LayoutError(f"{c.rel}: string table is not in the game's pool layout")
    old = c.data
    data = bytearray(old[:at]) + bytearray(nbytes) + bytearray(old[at:])

    def mv(o: int) -> int:
        return o + nbytes if o >= at else o

    relocs = [mv(r) for r in c.b.relocs]
    strs, spos = [], []
    for r, nr in zip(c.b.relocs, relocs):
        if r in pooled:
            strs.append(pooled[r])
            spos.append(nr)
        else:
            v = struct.unpack_from("<I", old, r)[0]
            if v > len(old):
                raise LayoutError(f"{c.rel}: pointer at {r:#x} = {v:#x} is neither data nor a pooled string")
            struct.pack_into("<I", data, nr, mv(v))
    have = {n for _o, n, _no in c.b.labels}
    for o, n in new_labels:
        if not at <= o < at + nbytes:
            raise LayoutError(f"{c.rel}: new label {text(n)} is outside the inserted bytes")
        if n in have:
            raise LayoutError(f"{c.rel}: label {text(n)} already exists")
        have.add(n)
    k = max((i + 1 for i, (o, _n, _no) in enumerate(c.b.labels) if o < at), default=0)
    labels = [(mv(o), n) for o, n, _no in c.b.labels]
    labels[k:k] = sorted(new_labels)
    names = [n for _o, n in labels]
    tab, noffs, soffs = isbin.build_pool(names, strs)
    se = len(data) + 4 * len(relocs) + 8 * len(labels)
    for p, so in zip(spos, soffs):
        struct.pack_into("<I", data, p, se + so)
    nb = isbin.IsBin()
    nb.hdrpad = c.b.hdrpad
    nb.data = bytes(data)
    nb.relocs = relocs
    nb.labels = [(o, n, no) for (o, n), no in zip(labels, noffs)]
    nb.strtab = tab
    return Container.from_dec(c, nb.build())


def append_records(reg: dict[str, TableDef], name: str, c: Container, new_rows: list[list[str]],
                   policies: dict[str, AppendPolicy] | None = None) -> Container:
    """Container c with len(new_rows) zeroed records added after the last record of table
    `name`, the stored count raised and each new record's label exported. new_rows are
    the CSV rows (index, label, cells...) of the new records; their cells are written
    afterwards by Codec.encode like any other row. Refused (LayoutError) when the table's
    append policy refuses, or a row's index, label, own-ID cell or number cell is wrong."""
    t = reg[name]
    pols = append_policies() if policies is None else policies
    why = append_refusal(t, pols)
    if why:
        raise LayoutError(why)
    pol = pols[name]
    codec = Codec(reg, name)
    cols = codec.columns()
    start, count = locate(t, c)
    first = None
    if pol.number_field:
        nf = next((f for f in codec.fields if f.name == pol.number_field), None)
        if nf is None or nf.kind != "int" or nf.n != 1:
            raise LayoutError(f"appends.csv: {name}.{pol.number_field} is not a single integer field")
        o = start + nf.offset
        first = int.from_bytes(c.data[o:o + nf.width], "little") if count else 0
    selfcol = next((f.name for f in codec.fields if f.kind == "str" and f.ref == "self"), None)
    labels: list[tuple[int, bytes]] = []
    at = start + count * t.size
    for k, row in enumerate(new_rows):
        cell = dict(zip(cols, row))
        want = count + k
        if cell.get("index", "").strip() != str(want):
            raise LayoutError(f"{name}: new rows must be numbered {count}, {count + 1}, ... in order "
                              f"(found index {cell.get('index')!r} where {want} belongs)")
        lab = untext(cell["label"].strip())
        if not lab or not lab.startswith(pol.prefix.encode()):
            raise LayoutError(f"{name} #{want}: a new record needs a label starting with {pol.prefix}")
        try:
            lab.decode("cp932")
        except UnicodeError:
            raise LayoutError(f"{name} #{want}: label is not valid Shift-JIS") from None
        if selfcol and untext(cell[selfcol]) != lab:
            raise LayoutError(f"{name} #{want}: {selfcol} must equal the label ({cell['label']})")
        if first is not None and cell.get(pol.number_field, "").strip() != str(first + want):
            raise LayoutError(f"{name} #{want}: {pol.number_field} must be {first + want} "
                              f"(the first record's number + the index)")
        labels.append((at + k * t.size, lab))
    nc = insert_bytes(c, at, len(new_rows) * t.size, labels)
    m = re.fullmatch(r"(u8|u16|u32)@(.+)", t.count)
    if m:
        a, w = eval_expr(m.group(2), nc), {"u8": 1, "u16": 2, "u32": 4}[m.group(1)]
    else:
        a, w = int(t.count.partition(":")[2], 0), 4
    total = count + len(new_rows)
    if total >= 1 << (8 * w):
        raise LayoutError(f"{name}: {total} records do not fit the {8 * w}-bit count")
    d = bytearray(nc.dec)
    d[0x20 + a:0x20 + a + w] = total.to_bytes(w, "little")
    nc = Container.from_dec(c, bytes(d))
    if locate(t, nc) != (start, total):
        raise LayoutError(f"{name}: after the append the table is not at {start:#x} x {total}")
    return nc
