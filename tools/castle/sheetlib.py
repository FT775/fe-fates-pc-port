"""Sheet files: the self-describing lists inside some ordinary IS .bin files (Fates).

Standard library only. Reads containers with tools/tables/tablelib.py (which uses
tools/assets/isbin.py and lz.py); none of those files is changed. Facts below were read
from the user's own files and from the game code (docs/CASTLE.md has the evidence).

What a sheet file is
--------------------
An ordinary IS .bin (header, data, relocation list, labels, string pool). Inside its data
region it holds one or more *sheets*, each made of three parts, found through labels:

  MOD_<name>   u32 field count, then per field 20 bytes:
                 +0 str field name, +4 str type name (u8 s8 u16 s16 u32 f32 str ptr),
                 +8 12 bytes (three floats, editor ranges by the look of them;
                 StructList::Load and Update do not read them; kept as is)
  <name>       the sheet header, right after the field list (a label with the sheet's
               own name): +0 str sheet name, +4 u16 row count, +6 u16 row size,
               +8 ptr to the rows
  DAT_<name>   the rows: row count x row size bytes, the fields packed in declared order
               without padding. A row may carry its own label (its key).
  SHEET_LIST   u32 count, then that many str: the sheet names, once per file.

The game loads them with StructList::Load(path, sheet, base id, row size) (0018DF70):
it finds the header by name, refuses the file unless the u16 row size equals the size
compiled into the caller, and StructList::Update (0018E140) builds a pointer table
sized from the u16 row count in the file. Rows are then reached by number
(StructList::TryGet(int), bounds-checked against that count) or by row label
(StructList::TryGet(const char*), through the file's label hash). DiningData is read
directly with StructFile::GetHeader (ProcDining::ProcDining, 00180B90): count and rows
pointer from the header, the stride compiled in.

Layouts
-------
config/tables/castle/sheets.csv names every sheet this tool edits:
    key,file,sheet,record_size,append,label,evidence,description
      key          spreadsheet name (build/castle/<key>.csv) and layout name
      file         RomFS path; sheet = 0-based position of its MOD_ block in the file
      record_size  must equal the header's row size (and the code's, see evidence)
      append       allow | refuse; label = required | none (new rows need a row label)
config/tables/castle/<key>.csv: offset,size,type,name,confidence,evidence
    one row per declared field, in order; the type must match the file's declaration:
      u8 s8 u16 s16 u32 s32 f32  numbers;  hex[n]  raw bytes
      str          relocated pointer to a Shift-JIS string ('' = no pointer)
      ptr          relocated pointer kept as is (@0xOFFSET)
      list:SUBKEY  a declared ptr to {u32 count, ptr items}; the items are
                   config/tables/castle/<SUBKEY>.csv records and go to their own
                   spreadsheet build/castle/<key>__<SUBKEY>.csv (edit in place only)
Without a layout every sheet can still be read with its declared types ("generic"),
which is how every sheet file in the RomFS is round-trip tested.
"""
from __future__ import annotations

import csv
import math
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "tables"))
import tablelib as T  # noqa: E402

isbin = T.isbin
ROMFS = T.ROMFS
CONFIG = os.path.join(ROOT, "config", "tables", "castle")
OUTDIR = os.path.join(ROOT, "build", "castle")
REBUILT = os.path.join(OUTDIR, "rebuilt")
EMPTY_STR = T.EMPTY_STR

DECL_WIDTH = {"u8": 1, "s8": 1, "u16": 2, "s16": 2, "u32": 4, "s32": 4, "f32": 4, "str": 4, "ptr": 4}
INT = {"u8": (1, False), "s8": (1, True), "u16": (2, False), "s16": (2, True),
       "u32": (4, False), "s32": (4, True)}
MOD = b"MOD_"
FIELD_ENTRY = 20


class SheetError(ValueError):
    pass


# ------------------------------------------------------------------ parsing
class Decl:
    """One declared field: name (bytes), type name, the 12 unread bytes."""

    def __init__(self, name: bytes, typ: str, extra: bytes):
        self.name, self.type, self.extra = name, typ, extra

    @property
    def width(self) -> int:
        return DECL_WIDTH[self.type]


class Sheet:
    def __init__(self, index: int, mod_off: int, decls: list[Decl], hdr: int, name: bytes,
                 count: int, size: int, rows: int):
        self.index, self.mod_off, self.decls, self.hdr = index, mod_off, decls, hdr
        self.name, self.count, self.size, self.rows = name, count, size, rows

    @property
    def end(self) -> int:
        return self.rows + self.count * self.size

    @property
    def declared_size(self) -> int:
        return sum(d.width for d in self.decls)


def parse(c: T.Container) -> list[Sheet]:
    """Every sheet in container c, in MOD_ label order (the file order)."""
    out = []
    mods = sorted({o for o, n, _ in c.b.labels if n.startswith(MOD)})
    for k, mo in enumerate(mods):
        n = c.u32(mo)
        if n > 256 or mo + 4 + n * FIELD_ENTRY + 12 > len(c.data):
            raise SheetError(f"{c.rel}: MOD_ block at {mo:#x} has an implausible field count {n}")
        decls = []
        for i in range(n):
            e = mo + 4 + i * FIELD_ENTRY
            nm = c.string_at(c.u32(e))
            ty = c.string_at(c.u32(e + 4))
            if nm is None or ty is None or e not in c.relset or e + 4 not in c.relset:
                raise SheetError(f"{c.rel}: field {i} of the MOD_ block at {mo:#x} is not two strings")
            t = ty.decode("ascii", "replace")
            if t not in DECL_WIDTH:
                raise SheetError(f"{c.rel}: unknown declared type {t!r} at {e + 4:#x}")
            decls.append(Decl(nm, t, c.data[e + 8:e + 20]))
        h = mo + 4 + n * FIELD_ENTRY
        name = c.string_at(c.u32(h)) if h in c.relset else None
        if name is None:
            raise SheetError(f"{c.rel}: no sheet header after the MOD_ block at {mo:#x}")
        count, size = struct.unpack_from("<HH", c.data, h + 4)
        if count and h + 8 not in c.relset:
            raise SheetError(f"{c.rel}: sheet header at {h:#x} has no rows pointer")
        rows = c.u32(h + 8)
        if rows + count * size > len(c.data):
            raise SheetError(f"{c.rel}: rows of the sheet at {h:#x} run past the data")
        out.append(Sheet(k, mo, decls, h, name, count, size, rows))
    return out


def is_sheet_file(c: T.Container) -> bool:
    return any(n.startswith(MOD) for _o, n, _no in c.b.labels)


def row_labels(c: T.Container, s: Sheet) -> list[bytes]:
    """The label exported at each row's start ('' if none), ignoring DAT_ labels."""
    out = []
    for i in range(s.count):
        names = [n for n in c.labels_at.get(s.rows + i * s.size, []) if not n.startswith(b"DAT_")]
        out.append(names[0] if names else b"")
    return out


# ------------------------------------------------------------------ layouts
class Field:
    def __init__(self, offset: int, size: int, typ: str, name: str, confidence: str = "medium",
                 evidence: str = "", where: str = ""):
        self.offset, self.size, self.type, self.name = offset, size, typ, name
        self.confidence, self.evidence = confidence, evidence
        self.sub: str | None = None
        m = re.fullmatch(r"hex\[(\d+)\]", typ)
        if typ in INT:
            self.kind, w = "int", INT[typ][0]
        elif typ == "f32":
            self.kind, w = "f32", 4
        elif typ in ("str", "ptr"):
            self.kind, w = typ, 4
        elif typ.startswith("list:") and re.fullmatch(r"list:\w+", typ):
            self.kind, w, self.sub = "list", 4, typ[5:]
        elif m:
            self.kind, w = "hex", int(m.group(1))
        else:
            raise SheetError(f"{where}+{offset:#x} {name}: unknown type {typ}")
        if w != size:
            raise SheetError(f"{where}+{offset:#x} {name}: type {typ} is {w} bytes, size says {size}")
        if confidence not in ("high", "medium", "low"):
            raise SheetError(f"{where}+{offset:#x} {name}: confidence must be high/medium/low")


def layout_path(key: str) -> str:
    return os.path.join(CONFIG, f"{key}.csv")


def load_layout(key: str) -> list[Field]:
    path = layout_path(key)
    with open(path, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["offset"] and not r["offset"].startswith("#")]
    out = []
    for r in rows:
        if None in r:
            raise SheetError(f"{path}: row +{r['offset']} has extra cells (an unquoted comma?)")
        out.append(Field(int(r["offset"], 0), int(r["size"], 0), r["type"].strip(), r["name"].strip(),
                         r["confidence"].strip(), r["evidence"].strip(), key))
    names = [f.name for f in out]
    if len(set(names)) != len(names):
        raise SheetError(f"{path}: field names must be unique")
    clash = set(names) & {"index", "label", "row", "row_label", "item"}
    if clash:
        raise SheetError(f"{path}: {', '.join(sorted(clash))} is a spreadsheet column of its own; rename the field")
    return out


def tile_errors(fields: list[Field], size: int) -> list[str]:
    errs, pos = [], 0
    for f in fields:
        if f.offset != pos:
            errs.append(f"gap or overlap at +{pos:#x} (next field starts at +{f.offset:#x})")
        pos = f.offset + f.size
    if pos != size:
        errs.append(f"fields end at +{pos:#x}, record size is {size:#x}")
    return errs


def generic_layout(s: Sheet) -> list[Field]:
    out, pos = [], 0
    for i, d in enumerate(s.decls):
        out.append(Field(pos, d.width, d.type, f"field{i:02d}_{d.type}", "medium", "declared in the file"))
        pos += d.width
    return out


def decl_errors(fields: list[Field], s: Sheet) -> list[str]:
    """Layout against the file's own declaration: one field per declared field, same
    width, compatible type."""
    errs = []
    if len(fields) != len(s.decls):
        return [f"layout has {len(fields)} fields, the file declares {len(s.decls)}"]
    for f, d in zip(fields, s.decls):
        ok = f.type == d.type or f.kind == "hex" or (d.type == "ptr" and f.kind == "list")
        if f.size != d.width or not ok:
            errs.append(f"+{f.offset:#x} {f.name}: layout {f.type} but the file declares {d.type}")
    return errs


class SheetDef:
    def __init__(self, row: dict):
        self.key = row["key"].strip()
        self.file = row["file"].strip()
        self.sheet = int(row["sheet"])
        self.size = int(row["record_size"], 0)
        self.append = row["append"].strip()
        self.label = row["label"].strip()
        self.evidence = row["evidence"].strip()
        self.description = row.get("description", "").strip()
        if self.append not in ("allow", "refuse") or self.label not in ("required", "none"):
            raise SheetError(f"sheets.csv {self.key}: append must be allow/refuse, label required/none")


def registry() -> dict[str, SheetDef]:
    out = {}
    with open(os.path.join(CONFIG, "sheets.csv"), newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["key"] and not r["key"].startswith("#"):
                d = SheetDef(r)
                if d.key in out:
                    raise SheetError(f"sheets.csv: {d.key} twice")
                out[d.key] = d
    return out


def files(reg: dict[str, SheetDef]) -> list[str]:
    return sorted({d.file for d in reg.values()})


# ------------------------------------------------------------------ cells
def f32_cell(b: bytes) -> str:
    v = struct.unpack("<f", b)[0]
    if math.isfinite(v):
        s = repr(v)
        if struct.pack("<f", float(s)) == b:
            return s
    return "bits:0x" + b[::-1].hex().upper()


def f32_bytes(s: str) -> bytes:
    if s.startswith("bits:"):
        return int(s[5:], 16).to_bytes(4, "little")
    return struct.pack("<f", float(s))


def ptr_cell(c: T.Container, o: int, kind: str) -> str:
    v = c.u32(o)
    if o not in c.relset:
        return "" if v == 0 else f"={v}"
    if kind == "str" and v >= c.se:
        s = c.string_at(v)
        return T.text(s) if s else EMPTY_STR
    return f"@0x{v:X}"


def ptr_encode(s: str, kind: str, o: int, ptrs: dict) -> None:
    if s == "":
        ptrs[o] = ("null", 0)
    elif s.startswith("=") and T.NUM.fullmatch(s[1:]):
        ptrs[o] = ("raw", int(s[1:], 0))
    elif s.startswith("@0x"):
        ptrs[o] = ("off", int(s[1:], 16))
    elif kind == "str":
        ptrs[o] = ("str", b"" if s == EMPTY_STR else T.untext(s))
    else:
        raise SheetError(f"pointer cell {s!r}: use @0xOFFSET or leave it as dumped")


def list_at(c: T.Container, o: int) -> tuple[int, int] | None:
    """(item count, items offset) of the {u32 count, ptr items} list a field points at."""
    if o not in c.relset:
        return None
    h = c.u32(o)
    if h + 8 > len(c.data):
        raise SheetError(f"{c.rel}: list pointer at {o:#x} = {h:#x} is outside the data")
    n = c.u32(h)
    if n and h + 4 not in c.relset:
        raise SheetError(f"{c.rel}: list at {h:#x} has {n} items but no items pointer")
    return n, c.u32(h + 4)


def decode_fields(c: T.Container, fields: list[Field], base: int) -> list[str]:
    row = []
    for f in fields:
        o = base + f.offset
        if f.kind == "int":
            w, sg = INT[f.type]
            row.append(str(int.from_bytes(c.data[o:o + w], "little", signed=sg)))
        elif f.kind == "f32":
            row.append(f32_cell(c.data[o:o + 4]))
        elif f.kind == "hex":
            row.append(c.data[o:o + f.size].hex())
        elif f.kind in ("str", "ptr"):
            row.append(ptr_cell(c, o, f.kind))
        else:  # list
            lst = list_at(c, o)
            row.append("" if lst is None else f"n={lst[0]}")
    return row


def encode_fields(c: T.Container, fields: list[Field], base: int, cells: list[str], data: bytearray,
                  ptrs: dict, where: str) -> None:
    for f, s in zip(fields, cells):
        o = base + f.offset
        s = s.strip()
        try:
            if f.kind == "int":
                w, sg = INT[f.type]
                data[o:o + w] = int(s, 0).to_bytes(w, "little", signed=sg)
            elif f.kind == "f32":
                data[o:o + 4] = f32_bytes(s)
            elif f.kind == "hex":
                b = bytes.fromhex(s)
                if len(b) != f.size:
                    raise SheetError(f"{len(b)} bytes, need {f.size}")
                data[o:o + f.size] = b
            elif f.kind in ("str", "ptr"):
                ptr_encode(s, f.kind, o, ptrs)
            else:
                lst = list_at(c, o)
                want = "" if lst is None else f"n={lst[0]}"
                if s != want:
                    raise SheetError(f"the item count of a list cannot change here ({want} in the file); "
                                     "edit the items in their own spreadsheet")
        except (ValueError, OverflowError, SheetError) as e:
            raise SheetError(f"{where} {f.name} = {s!r}: {e}") from None


def columns(fields: list[Field]) -> list[str]:
    return ["index", "label"] + [f.name for f in fields]


def sub_columns(fields: list[Field]) -> list[str]:
    return ["row", "row_label", "item"] + [f.name for f in fields]


# ------------------------------------------------------------------ one sheet, decoded
class Codec:
    """Rows (and list items) of one sheet <-> cells, with a layout (registered sheets)
    or the declared types (generic)."""

    def __init__(self, c: T.Container, s: Sheet, fields: list[Field], subs: dict[str, list[Field]] | None = None):
        self.c, self.s, self.fields, self.subs = c, s, fields, subs or {}
        errs = tile_errors(fields, s.size) + decl_errors(fields, s)
        if s.declared_size != s.size:
            errs.append(f"declared fields are {s.declared_size:#x} bytes, header row size {s.size:#x}")
        if errs:
            raise SheetError(f"{c.rel} sheet {s.index}: " + "; ".join(errs))

    def rows(self) -> list[list[str]]:
        labs = row_labels(self.c, self.s)
        return [[str(i), T.text(labs[i])] + decode_fields(self.c, self.fields, self.s.rows + i * self.s.size)
                for i in range(self.s.count)]

    def items(self, f: Field) -> list[list[str]]:
        sub = self.subs[f.sub]
        size = sum(x.size for x in sub)
        labs = row_labels(self.c, self.s)
        out = []
        for i in range(self.s.count):
            lst = list_at(self.c, self.s.rows + i * self.s.size + f.offset)
            if lst is None:
                continue
            n, at = lst
            for k in range(n):
                out.append([str(i), T.text(labs[i]), str(k)] + decode_fields(self.c, sub, at + k * size))
        return out

    def encode(self, rows: list[list[str]], data: bytearray, ptrs: dict, where: str) -> None:
        cols = columns(self.fields)
        if len(rows) != self.s.count:
            raise SheetError(f"{where}: {len(rows)} rows for {self.s.count} in the file")
        labs = row_labels(self.c, self.s)
        for i, r in enumerate(rows):
            if len(r) != len(cols):
                raise SheetError(f"{where} row {i}: {len(r)} cells, need {len(cols)}")
            if r[0].strip() != str(i):
                raise SheetError(f"{where}: rows must stay in order (row {i} says index {r[0]!r})")
            if T.untext(r[1].strip()) != labs[i]:
                raise SheetError(f"{where} row {i}: row labels cannot be renamed ({T.text(labs[i])!r})")
            encode_fields(self.c, self.fields, self.s.rows + i * self.s.size, r[2:], data, ptrs, f"{where} row {i}")

    def encode_items(self, f: Field, items: list[list[str]], data: bytearray, ptrs: dict, where: str) -> None:
        sub = self.subs[f.sub]
        size = sum(x.size for x in sub)
        want = self.items(f)
        if [r[:3] for r in items] != [r[:3] for r in want]:
            raise SheetError(f"{where}: items cannot be added, removed or moved (row, row_label and item "
                             "columns must stay as dumped)")
        for r in items:
            i, k = int(r[0]), int(r[2])
            n, at = list_at(self.c, self.s.rows + i * self.s.size + f.offset)
            encode_fields(self.c, sub, at + k * size, r[3:], data, ptrs, f"{where} row {i} item {k}")


# ------------------------------------------------------------------ inserting rows
def insert_rows(c: T.Container, s: Sheet, n: int, labels: list[bytes]) -> T.Container:
    """Container c with n zeroed rows added after the last row of sheet s, the header's
    u16 count raised and labels[k] (if not empty) exported at new row k. Every
    relocated pointer at or past the insertion point, every relocation and label offset
    there moves by n x row size; the string pool is rebuilt with the game's rule.
    The new count is written at the header's own offset, so the header (its u16 count at
    hdr + 4) must lie wholly before the row block; a sheet laid out otherwise is refused
    (review 2026-11-12, finding 2)."""
    if not s.hdr + 6 <= s.rows:
        raise SheetError(f"{c.rel}: sheet {T.text(s.name)}: its header at {s.hdr:#x} is not before its rows "
                         f"at {s.rows:#x}; adding rows would move the count it must raise")
    nbytes = n * s.size
    if nbytes % 4:
        raise SheetError(f"{c.rel}: rows of {s.size} bytes would break the 4-byte alignment after them")
    if s.count + n > 0xFFFF:
        raise SheetError(f"{c.rel}: {s.count + n} rows do not fit the 16-bit count")
    pooled = isbin.pool_pointers(c.b)
    if pooled is None:
        raise SheetError(f"{c.rel}: string table is not in the game's pool layout")
    at = s.end
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
                raise SheetError(f"{c.rel}: pointer at {r:#x} = {v:#x} is neither data nor a pooled string")
            struct.pack_into("<I", data, nr, mv(v))
    have = {nm for _o, nm, _no in c.b.labels}
    new = []
    for k, lab in enumerate(labels):
        if not lab:
            continue
        if lab in have:
            raise SheetError(f"{c.rel}: label {T.text(lab)} already exists")
        have.add(lab)
        new.append((at + k * s.size, lab))
    pos = max((i + 1 for i, (o, _n, _no) in enumerate(c.b.labels) if o < at), default=0)
    labs = [(mv(o), nm) for o, nm, _no in c.b.labels]
    labs[pos:pos] = new
    tab, noffs, soffs = isbin.build_pool([nm for _o, nm in labs], strs)
    se = len(data) + 4 * len(relocs) + 8 * len(labs)
    for p, so in zip(spos, soffs):
        struct.pack_into("<I", data, p, se + so)
    struct.pack_into("<H", data, s.hdr + 4, s.count + n)  # header is before the rows (checked above)
    nb = isbin.IsBin()
    nb.hdrpad, nb.data, nb.relocs, nb.strtab = c.b.hdrpad, bytes(data), relocs, tab
    nb.labels = [(o, nm, no) for (o, nm), no in zip(labs, noffs)]
    return T.Container.from_dec(c, nb.build())


# ------------------------------------------------------------------ files
def container(rel: str) -> T.Container:
    return T.Container(rel)


def sheet_files() -> list[str]:
    """Every IS .bin in extracted/romfs with at least one MOD_ block (RomFS paths)."""
    out = []
    for dp, _dn, fn in os.walk(ROMFS):
        for f in fn:
            p = os.path.join(dp, f)
            if os.path.getsize(p) > 8_000_000:
                continue
            rel = os.path.relpath(p, ROMFS).replace(os.sep, "/")
            try:
                c = T.Container(rel)
            except Exception:  # noqa: BLE001 - anything that is not an IS .bin
                continue
            if is_sheet_file(c):
                out.append(rel)
    return sorted(out)


def generic_roundtrip(rel: str) -> tuple[bool, str]:
    """Decode every sheet of a file with its declared types, encode it back, rebuild:
    (identical?, note)."""
    c = T.Container(rel)
    sheets = parse(c)
    data = bytearray(c.data)
    ptrs: dict = {}
    flat = 0
    for s in sheets:
        if s.declared_size != s.size:
            return False, f"sheet {s.index}: declared {s.declared_size:#x} != row size {s.size:#x}"
        cod = Codec(c, s, generic_layout(s))
        cod.encode(cod.rows(), data, ptrs, f"{rel} sheet {s.index}")
        flat += all(d.type != "ptr" for d in s.decls)
    out = T.rebuild(c, data, ptrs)
    return out == c.raw, f"{len(sheets)} sheets ({flat} flat)"


def read_csv(path: str) -> tuple[list[str], list[list[str]]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise SheetError(f"{path} is empty")
    return rows[0], [r for r in rows[1:] if any(x.strip() for x in r)]


def write_csv(path: str, header: list[str], rows: list[list[str]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
