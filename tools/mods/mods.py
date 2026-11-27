#!/usr/bin/env python3
"""Mods for Fire Emblem Fates (Special Edition, USA): edit text, spreadsheets or whole
files, build, play in Zakuro.

Standard library only. Per-game constants (title id, RomFS folders, temp-file suffix,
names) come from config/game.json through tools/gamecfg.py. A mod is a folder
mods/<Name>/ with a mod.json and any of:

  text/<RomFS path>.txt   message archives as text files (format of tools/assets/msg.py),
                          e.g. text/m/@E/GameData.bin.lz.txt; only labels whose text
                          differs from the game count (tools/mods/textmod.py, pipeline T1)
  tables/<Table>.csv      spreadsheets in the format tools/tables/dump.py writes; only the
                          cells you change count. A row numbered past the table's end is a
                          new row (allowed per table by config/tables/appends.csv; Item and
                          Job today); its text IDs may then get new messages under text/. Needs table layouts in config/tables/
                          (tools/tables); without them a mod with spreadsheets is refused
                          with a clear message and everything else still works
  romfs/<RomFS path>      whole replacement files, installed as they are (a picture
                          rebuilt by tools/assets, a sound, any game file)
  maps/<MAP>/             a map package from tools/maps/maps.py export (units.csv,
                          terrain.csv, tiles.csv): checked by tools/maps/maplib.py with
                          the IDs every enabled mod's tables/ adds, rebuilt into the
                          map's Dispos / Terrain file (tools/mods/mapface.py)
  faces/<NAME>/           a portrait folder from tools/assets/portrait.py export: changed
                          PNGs rebuilt into the face .arc / .bch files; other sizes only
                          with "allow_face_resize": true in mod.json (tools/mods/mapface.py)
  castle/<File>/<Sheet>.csv
                          castle spreadsheets as tools/castle/castle.py dump writes them
                          (castle/DiningData/DiningData_Dish.csv ...): only changed cells
                          count; new rows only where config/tables/castle/sheets.csv
                          allows them (the two dining sheets); rebuilt through tools/castle
                          and read back (tools/mods/castlemod.py)

The build compares every text label and cell with the original game (read fresh from
your extracted/romfs/), merges the enabled mods in order, rebuilds only the RomFS files
that changed (same LZ format as the originals), reads each one back, and stages them
under build/mods/romfs/. `install` copies the staged files into Zakuro's mod folder for
this game, %APPDATA%\\zakuro\\mods\\<title id>\\romfs\\, with a manifest so `uninstall`
removes exactly what it placed and puts back anything it had to move aside.

Commands:
    new NAME [--description TEXT] [--tables Person,Job] [--text m/@E/GameData.bin.lz]
                                make a mod (spreadsheets of every table with a layout, or
                                only --tables; with --text and no --tables a text-only mod)
    text NAME ARCHIVE...        add the text file of message archive(s) to a mod
    archives                    where the message archives are (shared, per route, common)
    example                     make the demo mod "Example" (Ryoma: Strength +10; needs
                                the Person layout in config/tables/)
    example-item                make the demo mod "ExampleItem" (a NEW item: a Bronze Sword
                                copy with might +5 and its own name, in the avatar's
                                Chapter 1 starting items)
    example-text                make the demo mod "ExampleText" (Ryoma's name -> "Ryouma")
    example-map                 make the demo mod "ExampleMap" (one enemy of Birthright
                                Chapter 7, A007, moved two tiles; found at run time)
    example-face                make the demo mod "ExampleFace" (Ryoma's normal standing
                                face tinted blue by code; no picture is stored here)
    example-castle              make the demo mod "ExampleCastle" (the dish made from
                                dining ingredient 0 alone gives Strength +3 more; the
                                dish is found by its ingredient numbers at run time)
    map NAME MAP...             add map package(s) to a mod (maps/<MAP>/, from your game;
                                the mod is made, empty, if it does not exist)
    castle NAME FILE [--sheets K,...]
                                add a castle file's spreadsheets to a mod (castle/<FILE>/;
                                FILE e.g. DiningData, AcceShop; the mod is made, empty, if
                                it does not exist)
    face NAME QUERY [--folder F] [--extras]
                                add a character's portrait folder to a mod (faces/<F>/;
                                the mod is made, empty, if it does not exist)
    list                        the mods, in build order, with their change counts
    enable NAME / disable NAME  switch a mod on or off (then run install again)
    build [--allow-odd-growth]  check and merge the enabled mods, stage the changed files
    install [--no-build]        build, then copy the staged files into Zakuro's mod folder
    uninstall [--restore-backups]
                                remove the files install placed; restore what it moved aside;
                                also undoes an install that was interrupted. A file changed
                                after install is left in place (and your previous file stays
                                in the backup folder) unless --restore-backups: then the
                                changed file is moved to the "changed" folder and your
                                previous file is put back. Nothing is ever deleted that is
                                not exactly what install placed.
    recover                     the same as uninstall --restore-backups
    status                      what is enabled, staged and installed
    selftest                    offline checks in a temporary folder (needs extracted/romfs/)

Common options: --zakuro-dir DIR (default %APPDATA%\\zakuro), --mods-dir DIR (default mods/),
--stage-dir DIR (default build/mods/).

How Zakuro takes mods (read from its source, crates/zakuro-core/src/mods.rs and
crates/zakuro-fs/src/layered.rs, v0.2.32, for the Awakening port; the code is the same for
every title): the folder is <data dir>/mods/<title id as 16 hex digits, upper case; lower
case is used only when it alone exists>; files under romfs/ replace the game's file at the
same path (names matched exactly, then ignoring case) or are added; the bytes are handed
to the game as they are, so files stay LZ-compressed like the originals. A data-only mod
needs no recompile (only code.bin / code.ips / code.bps change what 3dsrecomp compiled).
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from gamecfg import GAME  # noqa: E402
sys.path.insert(0, HERE)
import textmod as TX  # noqa: E402
import mapface as MF  # noqa: E402
import castlemod as CM  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "tools", "assets"))
import lz  # noqa: E402


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ the table backend
# Table mods use tools/tables (owned by the tables work; this file only calls it). The
# calls mods.py makes are listed in docs/MODDING.md section 9 ("table backend contract"):
#   tablelib: ROMFS, CONFIG, registry(), layout_path(), Codec(reg, name) .columns() .decode()
#             .fields .reflabels() .ids(), container(rel), Container(rel, raw), locate(),
#             record_labels(), text(), untext(), EMPTY_STR, LayoutError, _CACHE, Field
#   build.py: build_file(reg, rel, tables, override=...)  check.py: check_table(reg, name)
# If the import fails or config/tables/ has no layouts, table mods are switched off with a
# reason (tables_status()) and text and romfs mods keep working.
T = TB = CK = None
_TABLES_IMPORT_ERROR = ""
try:
    sys.path.insert(0, os.path.join(ROOT, "tools", "tables"))
    import tablelib as T  # noqa: E402
    TB = _load(f"{GAME.key}_tables_build", os.path.join(ROOT, "tools", "tables", "build.py"))
    CK = _load(f"{GAME.key}_tables_check", os.path.join(ROOT, "tools", "tables", "check.py"))
except Exception as _e:  # any problem in a tool being rewritten must not break text mods
    T = TB = CK = None
    _TABLES_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"

TOOL_VERSION = 1
TITLE_HEX = GAME.title_id.upper()                         # "0004000000179800"
TITLE_ID = int(TITLE_HEX, 16)
GAME_NAME = GAME.game
ROMFS = os.path.join(ROOT, "extracted", "romfs")
TMP_SUFFIX = GAME.port.mod_tmp_suffix                     # ".fe14tmp"
MANIFEST = f"{GAME.key}pcport-mods-manifest.json"         # in Zakuro's title folder (Zakuro ignores it)
BACKUP = f"{GAME.key}pcport-backup"                       # files we had to move aside, same layout
ASSET_DIR = "romfs"                                       # whole-file replacements inside a mod
ID_COLS = ("file", "index", "label")
# files a file manager or editor leaves behind; never installed from a mod's romfs/ folder
JUNK_FILES = {"thumbs.db", "desktop.ini", ".ds_store"}
# Tables or columns the game looks up by number or that key other data: never editable.
# Empty for Fates until the layouts say which ones; tools/tables may also provide
# config/tables/readonly.csv (table,column,reason; column empty = whole table).
READONLY_TABLES: dict[str, str] = {}
READONLY_COLS: dict[tuple[str, str], str] = {}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")


class ModError(Exception):
    """A problem the user can fix; printed without a traceback."""


# ------------------------------------------------------------------ places
class Ctx:
    def __init__(self, mods_dir: str | None = None, stage_dir: str | None = None,
                 zakuro_dir: str | None = None, quiet: bool = False, romfs: str | None = None):
        self.romfs = romfs or ROMFS                 # where the original game files are read
        self.mods_dir = mods_dir or os.path.join(ROOT, "mods")
        self.stage_dir = stage_dir or os.path.join(ROOT, "build", "mods")
        if zakuro_dir is None:
            appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
            zakuro_dir = os.path.join(appdata, "zakuro")
        self.zakuro_dir = zakuro_dir
        self.quiet = quiet

    def say(self, *a) -> None:
        if not self.quiet:
            print(*a)

    @property
    def stage_romfs(self) -> str:
        return os.path.join(self.stage_dir, "romfs")

    @property
    def staged_json(self) -> str:
        return os.path.join(self.stage_dir, "staged.json")

    def title_dir(self) -> str:
        """Zakuro's rule (mods.rs `dir`): upper-case id unless only lower case exists."""
        mods = os.path.join(self.zakuro_dir, "mods")
        upper = os.path.join(mods, TITLE_HEX)
        lower = os.path.join(mods, TITLE_HEX.lower())
        return lower if (not os.path.exists(upper) and os.path.exists(lower)) else upper


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


# ------------------------------------------------------------------ vanilla tables
_REG = None
_VANILLA: dict | None = None
_CODECS: dict = {}


def tables_status() -> str | None:
    """None when table mods can be used, else the reason in plain words."""
    if T is None:
        return f"tools/tables could not be loaded ({_TABLES_IMPORT_ERROR})"
    reg_csv = os.path.join(T.CONFIG, "tables.csv")
    if not os.path.isfile(reg_csv):
        return (f"there are no table layouts yet ({os.path.relpath(reg_csv, ROOT)} is missing; "
                "tools/tables is being rewritten for Fates)")
    if not os.path.isdir(T.ROMFS):
        return "no extracted/romfs/ (python tools/assets/romfs.py; it reads the .cci in roms/)"
    return None


def reset_tables() -> None:
    """Forget every cached table (after the layouts or the RomFS folder changed)."""
    global _REG, _VANILLA
    _REG, _VANILLA = None, None
    _CODECS.clear()
    _CELLS.clear()
    _READONLY_LOADED.clear()
    if T is not None:
        T._CACHE.clear()
        if hasattr(T, "_REG"):               # tablelib's own registry cache (layout_path uses it)
            T._REG = None


def reg():
    global _REG
    if _REG is None:
        why = tables_status()
        if why:
            raise ModError(f"table mods are not available: {why}")
        _REG = T.registry()
        _load_readonly()
    return _REG


_READONLY_LOADED: list[bool] = []


def _load_readonly() -> None:
    """Optional config/tables/readonly.csv (table,column,reason) from the tables work."""
    if _READONLY_LOADED:
        return
    _READONLY_LOADED.append(True)
    path = os.path.join(T.CONFIG, "readonly.csv")
    if not os.path.isfile(path):
        return
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            t, c, why = (row.get("table") or "").strip(), (row.get("column") or "").strip(), \
                (row.get("reason") or "read-only").strip()
            if t and c:
                READONLY_COLS[(t, c)] = why
            elif t:
                READONLY_TABLES[t] = why


def table_names() -> list[str]:
    if tables_status():
        return []
    return [n for n in reg() if os.path.exists(T.layout_path(n))]


def codec(name: str):
    if name not in _CODECS:
        _CODECS[name] = T.Codec(reg(), name)
    return _CODECS[name]


def vanilla() -> dict[str, tuple[list[str], list[list[str]]]]:
    """Every table with a layout, decoded from the original RomFS files (same cells as
    dump.py). Empty when table mods are not available."""
    global _VANILLA
    if _VANILLA is None:
        out = {}
        for name in table_names():
            t = reg()[name]
            cd = codec(name)
            rows = []
            for rel in t.files():
                c = T.container(rel)
                start, count = T.locate(t, c)
                labels = T.record_labels(t, c, start, count)
                rows += [cd.decode(c, i, start + i * t.size, labels[i]) for i in range(count)]
            out[name] = (cd.columns(), rows)
        _VANILLA = out
    return _VANILLA


def multi(name: str) -> bool:
    return "*" in reg()[name].file


def row_key(name: str, row: list[str]) -> tuple:
    return (row[0], int(row[1])) if multi(name) else (int(row[0]),)


def row_rel(name: str, key: tuple) -> str:
    return key[0] if multi(name) else reg()[name].files()[0]


def key_text(name: str, key: tuple) -> str:
    return f"{key[0].rsplit('/', 1)[-1]} #{key[1]}" if multi(name) else f"#{key[0]}"


def write_table_csv(path: str, head: list[str], rows: list[list[str]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(head)
        w.writerows(rows)


def read_table_csv(path: str) -> tuple[list[str], list[list[str]]]:
    """A spreadsheet as saved by Excel/LibreOffice: UTF-8 with or without BOM, comma,
    semicolon or tab separated, CRLF or LF."""
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ModError(f"{path}: not UTF-8 text. In Excel use Save As > 'CSV UTF-8 (Comma "
                       "delimited)'; in LibreOffice pick the UTF-8 character set.") from None
    first = text.split("\n", 1)[0]
    delim = max(",;\t", key=first.count)
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))
    while rows and not any(c.strip() for c in rows[-1]):
        rows.pop()
    if not rows:
        return [], []
    return [h.strip() for h in rows[0]], rows[1:]


# ------------------------------------------------------------------ mods on disk
class Mod:
    def __init__(self, path: str):
        self.dir = path
        self.folder = os.path.basename(path)
        self.json_path = os.path.join(path, "mod.json")
        try:
            with open(self.json_path, encoding="utf-8-sig") as fh:
                self.meta = json.load(fh)
        except (OSError, ValueError) as e:
            raise ModError(f"{self.json_path}: {e}") from None
        if not isinstance(self.meta, dict):
            raise ModError(f"{self.json_path}: must hold a JSON object {{...}}")
        self.name = str(self.meta.get("name") or self.folder)
        self.description = str(self.meta.get("description", ""))
        self.enabled = bool(self.meta.get("enabled", True))
        self.override = bool(self.meta.get("override", False))
        try:
            self.order = int(self.meta.get("order", 100))
        except (TypeError, ValueError):
            raise ModError(f"{self.json_path}: 'order' must be a whole number") from None

    def save(self) -> None:
        write_json(self.json_path, self.meta)

    def tables(self) -> list[str]:
        d = os.path.join(self.dir, "tables")
        if not os.path.isdir(d):
            return []
        return sorted(os.path.join(d, n) for n in os.listdir(d) if n.lower().endswith(".csv"))

    def texts(self) -> list[tuple[str, str]]:
        """[(RomFS path of the message archive, text file)] under text/."""
        return TX.mod_text_files(self.dir)

    def assets(self) -> tuple[list[tuple[str, str]], list[str]]:
        """([(RomFS path, file)] under romfs/, sorted; skipped junk files)."""
        top = os.path.join(self.dir, ASSET_DIR)
        out, skipped = [], []
        if not os.path.isdir(top):
            return out, skipped
        for dp, dn, fn in os.walk(top):
            dn.sort()
            for f in fn:
                p = os.path.join(dp, f)
                rel = os.path.relpath(p, top).replace(os.sep, "/")
                if f.lower() in JUNK_FILES or f.endswith("~") or TMP_SUFFIX in f:
                    skipped.append(rel)
                    continue
                out.append((rel, p))
        out.sort()
        return out, skipped

    def maps(self) -> list[tuple[str, str]]:
        """[(map name, folder)] under maps/ (tools/mods/mapface.py)."""
        return MF.map_packages(self.dir)

    def faces(self) -> list[tuple[str, str]]:
        """[(name, folder)] under faces/ (tools/mods/mapface.py)."""
        return MF.face_packages(self.dir)

    def castle(self) -> list[tuple[str, str]]:
        """[(file folder name, folder)] under castle/ (tools/mods/castlemod.py)."""
        return CM.packages(self.dir)


def load_mods(ctx: Ctx) -> list[Mod]:
    if not os.path.isdir(ctx.mods_dir):
        return []
    mods = [Mod(os.path.join(ctx.mods_dir, n)) for n in sorted(os.listdir(ctx.mods_dir))
            if os.path.isfile(os.path.join(ctx.mods_dir, n, "mod.json"))]
    mods.sort(key=lambda m: (m.order, m.folder.lower()))
    return mods


def find_mod(ctx: Ctx, name: str) -> Mod:
    for m in load_mods(ctx):
        if name.lower() in (m.folder.lower(), m.name.lower()):
            return m
    raise ModError(f"no mod named {name!r} in {ctx.mods_dir} (python tools/mods/mods.py list)")


def norm_rel(rel: str) -> str:
    rel = rel.replace("\\", "/").strip("/")
    return rel[:-len(TX.SUFFIX)] if rel.lower().endswith(TX.SUFFIX) else rel


def add_text(ctx: Ctx, mod: Mod, rel: str) -> str:
    """Write the full text form of one message archive into mod/text/<rel>.txt."""
    rel = norm_rel(rel)
    try:
        text = TX.archive(rel, ctx.romfs).dump()
    except TX.TextError as e:
        raise ModError(str(e)) from None
    path = os.path.join(mod.dir, TX.TEXT_DIR, *rel.split("/")) + TX.SUFFIX
    if os.path.exists(path):
        raise ModError(f"{path} already exists")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def new_mod(ctx: Ctx, name: str, description: str = "", tables: list[str] | None = None,
            enabled: bool = True, text: list[str] | None = None) -> Mod:
    """tables=None: every table with a layout (none while table mods are unavailable)."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_\-]{0,63}", name):
        raise ModError("mod names use letters, digits, '_' and '-' (no spaces), up to 64 characters")
    path = os.path.join(ctx.mods_dir, name)
    if os.path.exists(path):
        raise ModError(f"{path} already exists")
    if tables is None and (text or tables_status()):
        tables = []                                # a text-only mod, or no layouts yet
    if tables:
        why = tables_status()
        if why:
            raise ModError(f"table mods are not available: {why}")
    van = vanilla() if (tables is None or tables) else {}
    names = list(van) if tables is None else tables
    for n in names:
        if n not in van:
            raise ModError(f"unknown table {n!r}; tables: {', '.join(van) or '(none)'}")
    for rel in text or []:
        try:
            TX.archive(norm_rel(rel), ctx.romfs)
        except TX.TextError as e:
            raise ModError(str(e)) from None
    orders = [m.order for m in load_mods(ctx)]
    for n in names:
        head, rows = van[n]
        write_table_csv(os.path.join(path, "tables", f"{n}.csv"), head, rows)
    meta = {"name": name, "description": description, "enabled": enabled,
            "order": (max(orders) + 10) if orders else 100, "override": False}
    write_json(os.path.join(path, "mod.json"), meta)
    m = Mod(path)
    for rel in text or []:
        add_text(ctx, m, rel)
    return m


# ------------------------------------------------------------------ cells
def parse_int(s: str) -> int | None:
    s = s.strip()
    if re.fullmatch(r"[+-]?\d+", s):
        return int(s, 10)
    if re.fullmatch(r"[+-]?\d+\.0*", s):           # Excel's "12.0"
        return int(s.split(".")[0], 10)
    if re.fullmatch(r"[+-]?0[xX][0-9A-Fa-f]+", s):
        return int(s, 16)
    return None


def int_range(width: int, signed: bool) -> tuple[int, int]:
    bits = 8 * width
    return (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if signed else (0, (1 << bits) - 1)


class Cells:
    """Column metadata and value checks for one table; canon() returns the cell exactly as
    dump.py would print the value after a rebuild, or raises ModError."""

    def __init__(self, name: str):
        self.name = name
        self.cd = codec(name)
        self.info: dict[str, tuple] = {}
        for f in self.cd.fields:
            for k, col in enumerate(f.columns()):
                self.info[col] = (f, k)

    def canon(self, rel: str, col: str, s: str, allow_odd_growth: bool) -> tuple[str, str | None]:
        """(canonical cell, warning or None)."""
        name = self.name
        if name in READONLY_TABLES:
            raise ModError(f"{name} is read-only: {READONLY_TABLES[name]}")
        if (name, col) in READONLY_COLS:
            raise ModError(f"{name}.{col} is read-only: {READONLY_COLS[(name, col)]}")
        f, _k = self.info[col]
        if f.kind == "str" and f.ref == "self":
            raise ModError(f"{name}.{col} is the record's own ID (its label); renaming records is not supported")
        if f.kind in ("int", "enc"):
            v = parse_int(s)
            if v is None:
                raise ModError(f"{s!r} is not a whole number")
            lo, hi = int_range(f.width, f.signed)
            if not lo <= v <= hi:
                raise ModError(f"{v} is out of range ({f.type}: {lo}..{hi})")
            if f.kind == "enc" and v % 5 and not allow_odd_growth:
                raise ModError(f"{v} is not a multiple of 5 (every growth rate in the game is; "
                               "build with --allow-odd-growth to permit it)")
            if f.kind == "int" and col.split(".")[0].startswith("growth") and v % 5:
                return str(v), (f"{col} = {v} is not a multiple of 5 like every growth rate in the game "
                                "(allowed; the game uses the number as it is [medium])")
            return str(v), None
        s = s.strip() if f.kind != "str" else s
        if f.kind == "hex":                         # n raw bytes as one hex string (unknown meaning)
            h = re.sub(r"[\s_]", "", s)
            if not re.fullmatch(r"(?:[0-9A-Fa-f]{2})*", h) or len(h) != 2 * f.n:
                raise ModError(f"{s!r} is not {f.n} bytes written as {2 * f.n} hex digits")
            return h.lower(), None
        if f.kind == "ref":
            labs = self.cd.reflabels(f.ref, rel)
            if s.lower() == "none":
                return "none", None
            v = parse_int(s)
            if v is None:
                try:
                    v = labs.index(T.untext(s))
                except ValueError:
                    raise ModError(f"{s!r} is not a {f.ref} record label") from None
            if not 0 <= v < len(labs):
                raise ModError(f"{v} is not a {f.ref} record number (0..{len(labs) - 1}) or 'none'")
            return (T.text(labs[v]) if labs[v] and labs.index(labs[v]) == v else str(v)), None
        if f.kind == "enum":
            names = self.cd.ids(f.ref)
            v = parse_int(s)
            if v is None:
                try:
                    v = names.index(T.untext(s))
                except ValueError:
                    raise ModError(f"{s!r} is not one of the {f.ref} names") from None
            if not 0 <= v < len(names):
                raise ModError(f"{v} is not a {f.ref} value (0..{len(names) - 1})")
            return (T.text(names[v]) if names[v] and names.index(names[v]) == v else str(v)), None
        if f.kind == "flags":
            names = self.cd.ids(f.ref)
            bits = set()
            for part in filter(None, (p.strip() for p in s.split("|"))):
                m = re.fullmatch(r"bit(\d+)", part)
                if m:
                    b = int(m.group(1))
                else:
                    try:
                        b = names.index(T.untext(part))
                    except ValueError:
                        raise ModError(f"{part!r} is not one of the {f.ref} names") from None
                if b >= len(names) or b >= 8 * f.width:
                    raise ModError(f"bit {b} does not exist in {f.ref} ({len(names)} names)")
                bits.add(b)
            parts = [T.text(names[b]) if names[b] and names.index(names[b]) == b else f"bit{b}"
                     for b in sorted(bits)]
            return "|".join(parts), None
        if f.kind == "str":
            if s in ("", T.EMPTY_STR):
                return s, (f"{col}: an empty or missing string where the game expects an ID can crash it"
                           if s == "" else None)
            try:
                b = T.untext(s)
                b.decode("cp932")
            except (ValueError, UnicodeError):
                raise ModError(f"{s!r} is not a valid Shift-JIS string") from None
            if any(T.text(b).startswith(p) for p in ID_TABLES):
                return T.text(b), None              # checked against the records (check_new_references)
            return T.text(b), (f"{col} is an ID string (a message, portrait or class name the game "
                               "looks up); a name that does not exist may crash the game")
        if f.kind == "lptr":
            if s == "":
                return "", None
            if s.startswith("@0x"):
                raise ModError("raw data offsets cannot be edited")
            c = T.container(rel)
            off = c.label_off.get(T.untext(s))
            if off is None:
                raise ModError(f"{s!r} is not a label in {rel}")
            rt = reg()[f.ref]
            start, count = T.locate(rt, c)
            if off not in {start + i * rt.size for i in range(count)}:
                raise ModError(f"{s!r} is not a {f.ref} record")
            names = [n for n in c.labels_at.get(off, []) if c.label_off[n] == off]
            return T.text(names[-1]), None
        raise ModError(f"{name}.{col} ({f.type}) holds a raw data pointer and cannot be edited")


_CELLS: dict[str, Cells] = {}


def cells_of(name: str) -> Cells:
    if name not in _CELLS:
        _CELLS[name] = Cells(name)
    return _CELLS[name]


TEXT_ID = re.compile(r"M[A-Z]*ID_")          # message labels a record names (MIID_, MJID_ ...)
ID_TABLES = {"IID_": "Item", "JID_": "Job"}   # ID prefixes checked against the table's labels


def new_row(name: str, ix: int, head: list[str], colmap: list, row: list, vhead: list[str],
            vrows: list[list[str]], where: str, allow_odd_growth: bool):
    """A row a mod adds at the end of a table (tools/tables appends it). Returns
    (canonical full row, errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    t = reg()[name]
    why = T.append_refusal(t)
    if why:
        return None, [f"{where}: adding a row: {why}"], []
    pol = T.append_policies()[name]
    nid = 2
    have = {vhead[j] for j in colmap if j is not None}
    missing = [h for h in vhead[nid:] if h not in have]
    if missing:
        return None, [f"{where}: a new row needs every column of {name} (missing: {', '.join(missing[:6])}"
                      f"{' ...' if len(missing) > 6 else ''}); copy an existing row to the end and change it"], []
    li = head.index("label")
    lab = (row[li] or "").strip()
    try:
        labb = T.untext(lab)
        labb.decode("cp932")
    except (ValueError, UnicodeError):
        return None, [f"{where}: label {lab!r} is not valid Shift-JIS"], []
    if not labb.startswith(pol.prefix.encode()) or len(labb) <= len(pol.prefix):
        return None, [f"{where}: a new {name} row needs its own label starting with {pol.prefix} "
                      f"(for example {pol.prefix}MY_THING)"], []
    if labb in T.container(t.files()[0]).label_off:
        return None, [f"{where}: label {lab} already exists in {t.files()[0]}; a new row needs a new label"], []
    full = [""] * len(vhead)
    full[0], full[1] = str(ix), T.text(labb)
    first = 0
    if pol.number_field:
        first = parse_int(vrows[0][vhead.index(pol.number_field)]) or 0 if vrows else 0
    cells = cells_of(name)
    used = {}
    for i, j in enumerate(colmap):
        if j is None or j < nid:
            continue
        col, s = vhead[j], row[i]
        if s is None:
            errors.append(f"{where} {col}: the row is cut short; a new row needs every cell")
            continue
        f, _k = cells.info[col]
        if f.kind == "str" and f.ref == "self":
            if s.strip() not in ("", lab):
                errors.append(f"{where} {col}: must equal the label {lab} (or stay empty)")
            full[j] = T.text(labb)
            continue
        if col == pol.number_field:
            want = first + ix
            if s.strip() and parse_int(s) != want:
                errors.append(f"{where} {col}: must be {want} (the record's number), or empty to fill it in")
            full[j] = str(want)
            continue
        try:
            canon, _warn = cells.canon(t.files()[0], col, s, allow_odd_growth)
        except ModError as e:
            errors.append(f"{where} {col}: {e}")
            continue
        full[j] = canon
        if f.kind == "str" and canon not in ("", T.EMPTY_STR) and not TEXT_ID.match(canon):
            if col not in used:
                used[col] = {r[j] for r in vrows}
            if canon not in used[col] and not any(canon.startswith(p) for p in ID_TABLES):
                warnings.append(f"{name} {lab} {col} = {canon}: no game row uses this string; a name the "
                                "game looks up and does not find may crash it")
    return (None if errors else full), errors, warnings


def diff_mod(mod: Mod, allow_odd_growth: bool = False, rows_out: dict | None = None):
    """Cell-level differences of one mod against vanilla.
    Returns (changes {(table, row key, vanilla column position): canonical value},
    errors, warnings). Rows numbered past the end of a table are new rows: they are
    checked (config/tables/appends.csv must allow the table) and, when rows_out is
    given, collected there as {table: [(index, canonical full row)]}."""
    if not mod.tables():
        return {}, [], []
    why = tables_status()
    if why:
        return {}, [f"{mod.name}/tables/: this mod has spreadsheets, but table mods are not "
                    f"available: {why}. Disable the mod or move its tables/ folder away; text "
                    "and romfs mods work without layouts"], []
    van = vanilla()
    changes: dict[tuple, str] = {}
    errors: list[str] = []
    warnings: list[str] = []
    for path in mod.tables():
        name = os.path.splitext(os.path.basename(path))[0]
        where = f"{mod.name}/tables/{os.path.basename(path)}"
        if name not in van:
            errors.append(f"{where}: no table named {name} (tables: {', '.join(van)})")
            continue
        try:
            head, rows = read_table_csv(path)
        except ModError as e:
            errors.append(str(e))
            continue
        vhead, vrows = van[name]
        nid = 3 if multi(name) else 2              # leading ID columns: [file] index label
        # map each column to the vanilla column with the same name and occurrence (a
        # field may share a name with an ID column)
        colmap: list[int | None] = []
        used: dict[str, int] = {}
        for h in head:
            k = used.get(h, 0)
            used[h] = k + 1
            hits = [j for j, vh in enumerate(vhead) if vh == h]
            colmap.append(hits[k] if k < len(hits) else None)
        bad_cols = [h for h, j in zip(head, colmap) if j is None and h not in vhead]
        dup = sorted({h for h, j in zip(head, colmap) if j is None and h in vhead})
        idx = {vhead[j]: i for i, j in enumerate(colmap) if j is not None and j < nid}
        missing = [h for h in vhead[:nid] if h not in idx]
        if bad_cols or dup or missing:
            if bad_cols:
                errors.append(f"{where}: unknown column(s) {', '.join(bad_cols[:5])} (columns are renamed "
                              "only by tools/tables layouts; start again from 'new' if the layout changed)")
            if dup:
                errors.append(f"{where}: duplicate column(s) {', '.join(dup)}")
            if missing:
                errors.append(f"{where}: needs the column(s) {', '.join(missing)} to find each row")
            continue
        lab = nid - 1
        vkey = {row_key(name, r): r for r in vrows}
        cells = cells_of(name)
        seen = set()
        added: list[tuple[int, list[str]]] = []
        for n, row in enumerate(rows, start=2):
            if not any(c.strip() for c in row):
                continue
            # a row cut short (some programs drop trailing empty cells): the missing cells
            # count as unchanged, the ID cells are still required
            row = row + [None] * (len(head) - len(row))
            if any(row[i] is None for i in idx.values()):
                errors.append(f"{where} line {n}: the row is cut short before its ID columns")
                continue
            ix = parse_int(row[idx["index"]])
            if ix is None:
                errors.append(f"{where} line {n}: bad index {row[idx['index']]!r}")
                continue
            key = (row[idx["file"]].strip(), ix) if multi(name) else (ix,)
            vr = vkey.get(key)
            if vr is None and not multi(name) and ix >= len(vrows):
                if key in seen:
                    errors.append(f"{where} line {n}: row {key} appears twice")
                    continue
                seen.add(key)
                full, errs, warns = new_row(name, ix, head, colmap, row, vhead, vrows,
                                            f"{where} line {n} (new row {ix})", allow_odd_growth)
                errors += errs
                warnings += [f"{mod.name}: {w}" for w in warns]
                if full is not None:
                    added.append((ix, full))
                continue
            if vr is None:
                errors.append(f"{where} line {n}: no such row {key}"
                              + (" (adding rows to a table spread over several files is not supported)"
                                 if multi(name) else ""))
                continue
            if key in seen:
                errors.append(f"{where} line {n}: row {key} appears twice")
                continue
            seen.add(key)
            if row[idx["label"]].strip() != vr[lab]:
                errors.append(f"{where} line {n}: label {row[idx['label']]!r} should be {vr[lab]!r} "
                              "(rows cannot be renamed or reordered against their index)")
                continue
            rel = row_rel(name, key)
            for i, j in enumerate(colmap):
                if j < nid:
                    continue
                s, old = row[i], vr[j]
                if s is None or s == old:
                    continue
                try:
                    canon, warn = cells.canon(rel, vhead[j], s, allow_odd_growth)
                except ModError as e:
                    errors.append(f"{where} line {n} ({vr[lab]}) {vhead[j]}: {e}")
                    continue
                if canon == old:
                    continue
                changes[(name, key, j)] = canon
                if warn:
                    warnings.append(f"{mod.name}: {name} {vr[lab]} {warn}")
        if added:
            added.sort()
            want = list(range(len(vrows), len(vrows) + len(added)))
            if [ix for ix, _r in added] != want:
                errors.append(f"{where}: new rows must be numbered {len(vrows)}, {len(vrows) + 1}, ... "
                              f"without gaps (found {', '.join(str(ix) for ix, _r in added)})")
            labs = [r[1] for _ix, r in added]
            if len(set(labs)) != len(labs):
                errors.append(f"{where}: two new rows have the same label")
            if rows_out is not None:
                rows_out[name] = added
    return changes, errors, warnings


def merge(mods: list[Mod], allow_odd_growth: bool = False, new_rows: dict | None = None):
    """Merge the enabled mods' cells in order. Returns (merged {cell: (value, mod name)},
    per-mod counts, errors, warnings, notes). New rows go into new_rows (when given) as
    {table: [(index, full row, mod name)]}; two mods adding rows to the same table are
    refused (their numbers would collide) unless the rows are identical."""
    merged: dict[tuple, tuple[str, str]] = {}
    counts: dict[str, int] = {}
    errors, warnings, notes = [], [], []
    added: dict[str, list[tuple[int, list[str], str]]] = {} if new_rows is None else new_rows
    for m in mods:
        if not m.enabled:
            continue
        rows: dict[str, list] = {}
        ch, errs, warns = diff_mod(m, allow_odd_growth, rows)
        counts[m.name] = len(ch)
        errors += errs
        warnings += warns
        for name, lst in rows.items():
            prev = added.get(name)
            if prev is None:
                added[name] = [(ix, r, m.name) for ix, r in lst]
            elif [(ix, r) for ix, r, _m in prev] == lst:
                notes.append(f"{name}: {m.name} and {prev[0][2]} add the same new row(s)")
            else:
                errors.append(f"conflict: {m.name} and {prev[0][2]} both add rows to {name}; their "
                              "numbers would collide (put the new rows into one mod)")
        for cell, v in ch.items():
            prev = merged.get(cell)
            where = f"{cell[0]} {key_text(cell[0], cell[1])} {vanilla()[cell[0]][0][cell[2]]}"
            if prev is None:
                merged[cell] = (v, m.name)
            elif prev[0] == v:
                notes.append(f"{where}: {m.name} and {prev[1]} make the same change ({v})")
            elif m.override:
                notes.append(f"{where}: {m.name} overrides {prev[1]} ({prev[0]} -> {v})")
                merged[cell] = (v, m.name)
            else:
                errors.append(f"conflict: {where} is {prev[0]!r} in {prev[1]} and {v!r} in {m.name} "
                              f"(set \"override\": true in {m.name}/mod.json to let the later mod win, "
                              "or change one of them)")
    return merged, counts, errors, warnings, notes


def merge_text(ctx: Ctx, mods: list[Mod], new_ok: frozenset | set = frozenset()):
    """Merge the enabled mods' text files in order, with the same conflict and override
    rules as cells. new_ok: message labels the name archive does not have that new rows
    use (they may be given text there). Returns (merged {(archive, label bytes): (text,
    mod name)}, per-mod label counts, errors, warnings, notes)."""
    merged: dict[tuple, tuple[str, str]] = {}
    counts: dict[str, int] = {}
    errors, warnings, notes = [], [], []
    for m in mods:
        if not m.enabled:
            continue
        ch_all, errs_all, warns, nts = diff_mod_text(ctx, m, new_ok)
        errors += errs_all
        warnings += warns
        notes += nts
        counts[m.name] = len(ch_all)
        for cell, v in ch_all.items():
            prev = merged.get(cell)
            at = f"text {cell[0]} [{cell[1].decode('cp932', 'backslashreplace')}]"
            if prev is None:
                merged[cell] = (v, m.name)
            elif prev[0] == v:
                notes.append(f"{at}: {m.name} and {prev[1]} make the same change")
            elif m.override:
                notes.append(f"{at}: {m.name} overrides {prev[1]}")
                merged[cell] = (v, m.name)
            else:
                errors.append(f"conflict: {at} differs in {prev[1]} and {m.name} "
                              f"(set \"override\": true in {m.name}/mod.json to let the later mod win, "
                              "or change one of them)")
    return merged, counts, errors, warnings, notes


def diff_mod_text(ctx: Ctx, mod: Mod, new_ok: frozenset | set = frozenset()):
    """One mod's text files against the original archives. Labels in new_ok may be new
    in the name archive (NAME_ARCHIVE) only.
    Returns ({(archive, label bytes): text}, errors, warnings, notes)."""
    changes: dict[tuple, str] = {}
    errors, warnings, notes = [], [], []
    for rel, path in mod.texts():
        where = f"{mod.name}/{TX.TEXT_DIR}/{rel}{TX.SUFFIX}"
        try:
            van = TX.archive(rel, ctx.romfs)
        except TX.TextError as e:
            errors.append(f"{where}: {e}")
            continue
        with open(path, "rb") as fh:
            name, items, errs = TX.parse_mod_text(fh.read(), where)
        ch, errs2, warns, nts = TX.diff_text(van, name, items, where,
                                             new_ok if rel == NAME_ARCHIVE else frozenset())
        errors += errs + errs2
        warnings += warns
        notes += nts
        if not (errs or errs2):
            changes.update({(rel, lab): v for lab, v in ch.items()})
    return changes, errors, warnings, notes


# ------------------------------------------------------------------ romfs (whole files)
class _CaseIndex:
    """Exact-case RomFS paths, so a mod file named 'gamedata/x.bin.lz' maps to the game's
    'GameData/x.bin.lz' (Zakuro matches names exactly, then ignoring case)."""

    def __init__(self, romfs: str):
        self.romfs = romfs
        self._dirs: dict[str, dict[str, str]] = {}

    def _list(self, rel_dir: str) -> dict[str, str]:
        if rel_dir not in self._dirs:
            full = os.path.join(self.romfs, *rel_dir.split("/")) if rel_dir else self.romfs
            try:
                names = os.listdir(full)
            except OSError:
                names = []
            self._dirs[rel_dir] = {n.lower(): n for n in names}
        return self._dirs[rel_dir]

    def game_path(self, rel: str) -> str | None:
        """The game's own spelling of rel (a file), or None if the game has no such file."""
        out = []
        for part in rel.split("/"):
            hit = self._list("/".join(out)).get(part.lower())
            if hit is None:
                return None
            out.append(hit)
        found = "/".join(out)
        return found if os.path.isfile(os.path.join(self.romfs, *out)) else None


def _is_lz_ok(data: bytes) -> bool:
    if lz.lz_type(data) is None:
        return False
    try:
        lz.decompress(data)
        return True
    except (lz.LZError, IndexError, ValueError):
        return False


def diff_mod_assets(ctx: Ctx, mod: Mod, index: _CaseIndex):
    """One mod's romfs/ files. Returns ({RomFS path: (source file, sha256, size)},
    errors, warnings, notes)."""
    out: dict[str, tuple[str, str, int]] = {}
    errors, warnings, notes = [], [], []
    files, skipped = mod.assets()
    for rel in skipped:
        notes.append(f"{mod.name}/{ASSET_DIR}/{rel}: skipped (not a game file)")
    for rel, path in files:
        where = f"{mod.name}/{ASSET_DIR}/{rel}"
        if rel.split("/", 1)[0].lower() in ("exefs", "romfs") or rel.lower() in ("code.bin", "exheader.bin"):
            errors.append(f"{where}: put files at their RomFS path directly under {ASSET_DIR}/ "
                          "(code and ExeFS files are not data mods)")
            continue
        game = index.game_path(rel)
        if game is not None and game != rel:
            notes.append(f"{where}: the game spells it {game}; installed under that name")
            rel = game
        if rel in out:
            errors.append(f"{where}: two files in this mod give the same game path {rel}")
            continue
        size = os.path.getsize(path)
        head = _head(path)
        orig = os.path.join(ctx.romfs, *rel.split("/")) if game else None
        if orig is None:
            warnings.append(f"{where}: the game has no file {rel}; it is added (the game reads it only "
                            "if something asks for that name)")
        # a few game files end in .lz without being compressed (30 .bch.lz start with 0x00,
        # scout/file-formats.txt): only demand LZ where the game's own file is LZ
        game_lz = False
        if orig is not None and lz.lz_type(_head(orig)) is not None:
            game_lz = _is_lz_ok(_read(orig))
        if rel.lower().endswith(".lz") and (game_lz or orig is None):
            if not _is_lz_ok(_read(path)):
                errors.append(f"{where}: the name ends in .lz but the file is not LZ-compressed "
                              "(the game would fail to read it). Compress it first, e.g. "
                              "python tools/assets/lz.py c IN OUT --fmt 13")
                continue
        elif game_lz and lz.lz_type(head) is None:
            warnings.append(f"{where}: the game's file is LZ-compressed but yours is not; the game "
                            "may fail to read it")
        sha = file_sha(path)
        if orig and size == os.path.getsize(orig) and file_sha(orig) == sha:
            notes.append(f"{where}: same bytes as the game's file; not staged")
            continue
        out[rel] = (path, sha, size)
    return out, errors, warnings, notes


def _head(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(16)            # lz_type needs 8 bytes for LZ13


def _read(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def merge_assets(ctx: Ctx, mods: list[Mod]):
    """Merge the enabled mods' romfs/ files in order: the same path from two mods is a
    conflict unless the later one has override. Returns (merged {RomFS path: (source,
    sha256, size, mod name)}, per-mod counts, errors, warnings, notes)."""
    index = _CaseIndex(ctx.romfs)
    merged: dict[str, tuple[str, str, int, str]] = {}
    counts: dict[str, int] = {}
    errors, warnings, notes = [], [], []
    for m in mods:
        if not m.enabled:
            continue
        files, errs, warns, nts = diff_mod_assets(ctx, m, index)
        errors += errs
        warnings += warns
        notes += nts
        counts[m.name] = len(files)
        for rel, (src, sha, size) in files.items():
            prev = merged.get(rel)
            if prev is None:
                merged[rel] = (src, sha, size, m.name)
            elif prev[1] == sha:
                notes.append(f"romfs {rel}: {m.name} and {prev[3]} hold the same file")
            elif m.override:
                notes.append(f"romfs {rel}: {m.name} overrides {prev[3]}")
                merged[rel] = (src, sha, size, m.name)
            else:
                errors.append(f"conflict: romfs {rel} is replaced by both {prev[3]} and {m.name} "
                              f"(set \"override\": true in {m.name}/mod.json to let the later mod win, "
                              "or remove one of them)")
    return merged, counts, errors, warnings, notes


# ------------------------------------------------------------------ build
def fingerprint(ctx: Ctx) -> str:
    """Hash of everything a build depends on: the enabled mods and the table layouts."""
    h = hashlib.sha256(f"v{TOOL_VERSION} {TITLE_HEX}".encode())
    for m in load_mods(ctx):
        if not m.enabled:
            continue
        h.update(f"\0mod {m.folder} {m.order} {m.override} {m.meta.get('allow_face_resize', False)} "
                 f"{m.meta.get('lenient_maps', False)}".encode())
        for p in m.tables():
            with open(p, "rb") as fh:
                h.update(b"\0" + os.path.basename(p).encode() + b"\0" + fh.read())
        for rel, p in m.texts():
            with open(p, "rb") as fh:
                h.update(b"\0text " + rel.encode() + b"\0" + fh.read())
        for rel, p in m.assets()[0]:
            h.update(b"\0romfs " + rel.encode() + b"\0" + file_sha(p).encode())
        for rel, p in MF.files_to_hash(m.dir) + CM.files_to_hash(m.dir):
            h.update(b"\0" + rel.encode() + b"\0" + file_sha(p).encode())
    if T is not None and os.path.isdir(T.CONFIG):
        for n in sorted(os.listdir(T.CONFIG)):
            if n.endswith(".csv"):
                with open(os.path.join(T.CONFIG, n), "rb") as fh:
                    h.update(b"\0" + n.encode() + b"\0" + fh.read())
    cdir = os.path.join(ROOT, "config", "tables", "castle")      # castle layouts (tools/castle)
    if os.path.isdir(cdir):
        for n in sorted(os.listdir(cdir)):
            if n.endswith(".csv"):
                with open(os.path.join(cdir, n), "rb") as fh:
                    h.update(b"\0castle/" + n.encode() + b"\0" + fh.read())
    return h.hexdigest()


class BuildResult:
    def __init__(self):
        self.files: dict[str, bytes] = {}           # rebuilt text/table files
        self.assets: dict[str, tuple[str, str, int, str]] = {}   # romfs/ files, copied as-is
        self.merged: dict[tuple, tuple[str, str]] = {}
        self.new_rows: dict[str, list[tuple[int, list[str], str]]] = {}   # table: [(index, row, mod)]
        self.counts: dict[str, int] = {}
        self.text_merged: dict[tuple, tuple[str, str]] = {}
        self.text_counts: dict[str, int] = {}
        self.asset_counts: dict[str, int] = {}
        self.maps: dict[str, tuple[bytes, str]] = {}    # rebuilt map files: (bytes, mod)
        self.map_counts: dict[str, int] = {}
        self.faces: dict[str, tuple[bytes, str]] = {}   # rebuilt portrait files: (bytes, mod)
        self.face_counts: dict[str, int] = {}
        self.castle: dict[str, tuple[bytes, str]] = {}  # rebuilt castle files: (bytes, mod names)
        self.castle_counts: dict[str, int] = {}
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def paths(self) -> list[str]:
        return sorted(set(self.files) | set(self.assets))


def new_text_ids(ctx: Ctx, new_rows: dict) -> dict[bytes, str]:
    """Message labels (MIID_, MJID_ ...) that new rows name and the name archive does not
    have: {label: where it is used}. Each needs text from the mod (in NAME_ARCHIVE)."""
    out: dict[bytes, str] = {}
    if not new_rows:
        return out
    try:
        van = TX.archive(NAME_ARCHIVE, ctx.romfs)
    except TX.TextError:
        return out
    for name, lst in new_rows.items():
        head = vanilla()[name][0]
        for _ix, row, m in lst:
            for j, v in enumerate(row):
                if j < 2 or not TEXT_ID.match(v):
                    continue
                f, _k = cells_of(name).info[head[j]]
                if f.kind != "str":
                    continue
                lab = T.untext(v)
                if lab not in van.index:
                    out.setdefault(lab, f"{name} {row[1]} {head[j]} [{m}]")
    return out


def check_new_references(ctx: Ctx, r: "BuildResult", need_text: dict[bytes, str]) -> list[str]:
    """Every message a new row names must exist or get text from the mod; every IID_ /
    JID_ string a changed cell or new row holds must name an Item / Job record (the
    game's or a new one)."""
    errors = []
    for lab, where in sorted(need_text.items()):
        if (NAME_ARCHIVE, lab) not in r.text_merged:
            errors.append(f"{where}: names the message [{lab.decode('cp932', 'backslashreplace')}], which the "
                          f"game does not have; give it text in text/{NAME_ARCHIVE}{TX.SUFFIX} of the mod "
                          "(a label line and a text line)")
    if not (r.merged or r.new_rows):
        return errors
    van = vanilla()
    known: dict[str, set[str]] = {}
    for pfx, tname in ID_TABLES.items():
        if tname in van:
            h, rows = van[tname]
            li = h.index("label")
            known[pfx] = {x[li] for x in rows} | {x[1] for _ix, x, _m in r.new_rows.get(tname, [])}

    def check(name: str, col: str, v: str, where: str) -> None:
        f, _k = cells_of(name).info[col]
        if f.kind != "str" or f.ref == "self":
            return
        for pfx, labs in known.items():
            if v.startswith(pfx) and v not in labs:
                errors.append(f"{where} {col}: {v} is not a {ID_TABLES[pfx]} record (neither the game's "
                              "nor one an enabled mod adds)")

    for (name, key, col), (v, m) in r.merged.items():
        check(name, van[name][0][col], v, f"{name} {key_text(name, key)} [{m}]")
    for name, lst in r.new_rows.items():
        head = van[name][0]
        for ix, row, m in lst:
            for j in range(2, len(head)):
                check(name, head[j], row[j], f"{name} new row {ix} {row[1]} [{m}]")
    return errors


def compute(ctx: Ctx, allow_odd_growth: bool = False) -> BuildResult:
    """Merge, rebuild and verify; nothing is written."""
    r = BuildResult()
    mods = load_mods(ctx)
    r.merged, r.counts, r.errors, r.warnings, r.notes = merge(mods, allow_odd_growth, r.new_rows)
    need_text = new_text_ids(ctx, r.new_rows)
    r.text_merged, r.text_counts, terr, twarn, tnotes = merge_text(ctx, mods, set(need_text))
    r.assets, r.asset_counts, aerr, awarn, anotes = merge_assets(ctx, mods)
    r.errors += terr + aerr
    r.warnings += twarn + awarn
    r.notes += tnotes + anotes
    r.errors += check_new_references(ctx, r, need_text)
    r.maps, r.map_counts, merr, mwarn, mnotes = MF.merge_maps(ctx, mods)
    r.faces, r.face_counts, ferr, fwarn, fnotes = MF.merge_faces(ctx, mods)
    r.castle, r.castle_counts, cerr, cwarn, cnotes = CM.merge_castle(ctx, mods)
    r.errors += merr + ferr + cerr
    r.warnings += mwarn + fwarn + cwarn
    r.notes += mnotes + fnotes + cnotes
    # a whole-file replacement cannot be combined with text or cell edits of that file
    edited = {rel for rel, _l in r.text_merged}
    if r.merged or r.new_rows:
        edited |= {row_rel(n, k) for (n, k, _c) in r.merged}
        edited |= {reg()[n].files()[0] for n in r.new_rows}
    for rel in sorted(edited & set(r.assets)):
        r.errors.append(f"conflict: romfs {rel} is replaced as a whole file by {r.assets[rel][3]} and also "
                        "edited by a text or table change; a whole-file replacement already decides "
                        "every byte, so keep only one of them")
    for kind, got in (("map", r.maps), ("face", r.faces), ("castle", r.castle)):
        for rel in sorted(set(got) & set(r.assets)):
            r.errors.append(f"conflict: romfs {rel} is replaced as a whole file by {r.assets[rel][3]} and also "
                            f"rebuilt from the {kind} edits of {got[rel][1]}; keep only one of them")
    for rel in sorted(set(r.maps) & edited):
        r.errors.append(f"conflict: {rel} is edited both as a map (maps/ of {r.maps[rel][1]}) and as a "
                        "spreadsheet (tables/DisposUnit.csv or another table); make the change in the "
                        "map's units.csv only")
    for rel in sorted(set(r.castle) & (edited | set(r.maps) | set(r.faces))):
        r.errors.append(f"conflict: {rel} is edited both through castle/ (of {r.castle[rel][1]}) and as a "
                        "text, table, map or face change; make the change in one place only")
    if r.errors:
        r.assets, r.maps, r.faces, r.castle = {}, {}, {}, {}
        return r
    r.files.update({rel: data for rel, (data, _m) in r.maps.items()})
    r.files.update({rel: data for rel, (data, _m) in r.faces.items()})
    r.files.update({rel: data for rel, (data, _m) in r.castle.items()})
    # text: each changed message archive, re-encoded and compressed like the original,
    # then read back (textmod.build_archive)
    by_arc: dict[str, dict[bytes, str]] = {}
    for (rel, lab), (v, _m) in r.text_merged.items():
        by_arc.setdefault(rel, {})[lab] = v
    for rel in sorted(by_arc):
        try:
            r.files[rel] = TX.build_archive(TX.archive(rel, ctx.romfs), by_arc[rel])
        except (TX.TextError, ValueError) as e:
            r.errors.append(f"text {rel}: {e}")
    if r.errors:
        r.files, r.assets, r.maps, r.faces, r.castle = {}, {}, {}, {}, {}
        return r
    if not r.merged and not r.new_rows:
        return r
    van = vanilla()
    # apply the merged cells to copies of the vanilla rows; new rows go after the last one
    edited_rows: dict[str, tuple[list[str], list[list[str]]]] = {}
    pos: dict[str, dict[tuple, int]] = {}
    by_rel: dict[str, set[str]] = {}

    def rows_of(name: str) -> tuple[list[str], list[list[str]]]:
        if name not in edited_rows:
            head, rows = van[name]
            edited_rows[name] = (head, [list(x) for x in rows])
            pos[name] = {row_key(name, x): i for i, x in enumerate(rows)}
        return edited_rows[name]

    for (name, key, col), (v, _m) in r.merged.items():
        head, rows = rows_of(name)
        rows[pos[name][key]][col] = v
        by_rel.setdefault(row_rel(name, key), set()).add(name)
    for name, lst in r.new_rows.items():
        head, rows = rows_of(name)
        rows += [list(x) for _ix, x, _m in sorted(lst, key=lambda e: e[0])]
        by_rel.setdefault(reg()[name].files()[0], set()).add(name)
    built: dict[str, object] = {}
    for rel in sorted(by_rel):
        in_file = [n for n in table_names() if rel in reg()[n].files()]
        override = {n: edited_rows.get(n, van[n]) for n in in_file}
        try:
            out = TB.build_file(reg(), rel, in_file, override=override)
        except (T.LayoutError, ValueError, KeyError) as e:
            r.errors.append(f"{rel}: rebuild failed: {e}")
            continue
        orig = T.container(rel)
        if out == orig.raw:
            r.notes.append(f"{rel}: the edits give back the original file; not staged")
            continue
        nc = T.Container(rel, out)
        if orig.is_lz and (not nc.is_lz or out[0] != orig.raw[0]):
            r.errors.append(f"{rel}: rebuilt file is not in the original LZ format")
            continue
        # the rebuilt file must decode to exactly the merged spreadsheet, every table in it
        for n in in_file:
            t = reg()[n]
            s, cnt = T.locate(t, nc)
            labels = T.record_labels(t, nc, s, cnt)
            got = [codec(n).decode(nc, i, s + i * t.size, labels[i]) for i in range(cnt)]
            head, rows = override[n]
            want = [x for x in rows if (x[0] == rel if multi(n) else True)]
            if hasattr(TB, "shift_cells"):           # raw offsets after rows were appended
                want = TB.shift_cells(reg(), n, want, TB.LAST_MOVES.get(rel, []))
            if got != want:
                bad = [(g[1 if multi(n) else 0], h) for g, w in zip(got, want)
                       for h, a, b in zip(head, g, w) if a != b]
                r.errors.append(f"{rel}: {n} does not decode back to the edit: {bad[:5]}")
        built[rel] = nc
        r.files[rel] = out
    if r.errors:
        r.files, r.assets, r.maps, r.faces, r.castle = {}, {}, {}, {}, {}
        return r
    if not built:
        return r
    # tools/tables/check.py over every table living in a rebuilt file, on the rebuilt bytes
    saved = {rel: T._CACHE.get(rel) for rel in built}
    try:
        T._CACHE.update(built)
        for n in table_names():
            if any(rel in reg()[n].files() for rel in built):
                _nrec, errs = CK.check_table(reg(), n)
                if allow_odd_growth:
                    errs = [e for e in errs if "not a multiple of 5" not in e]
                r.errors += [f"check: {e}" for e in errs[:20]]
    finally:
        for rel, c in saved.items():
            if c is None:
                T._CACHE.pop(rel, None)
            else:
                T._CACHE[rel] = c
    if r.errors:
        r.files, r.assets, r.maps, r.faces, r.castle = {}, {}, {}, {}, {}
    return r


def change_lines(r: BuildResult, ctx: Ctx | None = None) -> list[str]:
    ctx = ctx or Ctx(quiet=True)
    van = vanilla() if r.merged else {}
    lines = []
    for (name, key, col), (v, m) in sorted(r.merged.items(), key=lambda x: (x[0][0], str(x[0][1]), x[0][2])):
        head, rows = van[name]
        row = next(x for x in rows if row_key(name, x) == key)
        lines.append(f"{name} {key_text(name, key)} {row[head.index('label')]} {head[col]}: "
                     f"{row[col]} -> {v}   [{m}]")
    for name, lst in sorted(r.new_rows.items()):
        for ix, row, m in lst:
            lines.append(f"{name} #{ix} {row[1]}: new row   [{m}]")
    for (rel, lab), (v, m) in sorted(r.text_merged.items()):
        old = TX.archive(rel, ctx.romfs).text_of.get(lab)
        if old is None:
            lines.append(f"text {rel} [{lab.decode('cp932', 'backslashreplace')}]: new message "
                         f"{TX.msg.escape(v)}   [{m}]")
            continue
        lines.append(f"text {rel} [{lab.decode('cp932', 'backslashreplace')}]: "
                     f"{TX.msg.escape(old)} -> {TX.msg.escape(v)}   [{m}]")
    for rel, (_src, sha, size, m) in sorted(r.assets.items()):
        lines.append(f"romfs {rel}: whole file replaced ({size} bytes, sha256 {sha[:12]})   [{m}]")
    for kind, got in (("map", r.maps), ("face", r.faces), ("castle", r.castle)):
        for rel, (data, m) in sorted(got.items()):
            lines.append(f"{kind} {rel}: rebuilt from the mod's {kind} folder ({len(data)} bytes)   [{m}]")
    return lines


def _write_atomic(dst: str, data: bytes | None = None, src: str | None = None) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + TMP_SUFFIX
    if src is not None:
        shutil.copyfile(src, tmp)
    else:
        with open(tmp, "wb") as fh:
            fh.write(data)
    os.replace(tmp, dst)


def build(ctx: Ctx, allow_odd_growth: bool = False) -> BuildResult:
    """compute() and, when it succeeds, replace build/mods/romfs/ with the changed files."""
    r = compute(ctx, allow_odd_growth)
    if r.errors:
        return r
    if os.path.isdir(ctx.stage_romfs):
        shutil.rmtree(ctx.stage_romfs)
    files = []
    for rel in r.paths():
        dst = os.path.join(ctx.stage_romfs, rel.replace("/", os.sep))
        if rel in r.assets:
            src, sha, size, m = r.assets[rel]
            _write_atomic(dst, src=src)
            if file_sha(dst) != sha:
                r.errors.append(f"romfs {rel}: {src} changed while it was being copied; build again")
                break
            files.append({"path": rel, "sha256": sha, "size": size, "kind": "romfs", "mod": m,
                          "tables": [], "cells": 0})
            continue
        data = r.files[rel]
        _write_atomic(dst, data=data)
        kind = "map" if rel in r.maps else "face" if rel in r.faces else "castle" if rel in r.castle else None
        if kind:
            files.append({"path": rel, "sha256": sha256(data), "size": len(data), "kind": kind,
                          "mod": (r.maps.get(rel) or r.faces.get(rel) or r.castle.get(rel))[1],
                          "tables": [], "cells": 0})
            continue
        tables = sorted({n for (n, k, _c) in r.merged if row_rel(n, k) == rel}
                        | {n for n in r.new_rows if reg()[n].files()[0] == rel})
        ent = {"path": rel, "sha256": sha256(data), "size": len(data), "tables": tables,
               "cells": sum(1 for (n, k, _c) in r.merged if row_rel(n, k) == rel),
               "new_rows": sum(len(v) for n, v in r.new_rows.items() if reg()[n].files()[0] == rel)}
        labels = sum(1 for (a, _l) in r.text_merged if a == rel)
        if labels:
            ent["kind"] = "text"
            ent["labels"] = labels
        files.append(ent)
    if r.errors:
        shutil.rmtree(ctx.stage_romfs, ignore_errors=True)
        return r
    enabled = [m for m in load_mods(ctx) if m.enabled]
    write_json(ctx.staged_json, {
        "format": TOOL_VERSION, "title_id": TITLE_HEX, "game": GAME_NAME,
        "built": time.strftime("%Y-%m-%d %H:%M:%S"), "fingerprint": fingerprint(ctx),
        "allow_odd_growth": allow_odd_growth,
        "mods": [{"name": m.name, "order": m.order, "override": m.override,
                  "cells": r.counts.get(m.name, 0), "labels": r.text_counts.get(m.name, 0),
                  "new_rows": sum(1 for v in r.new_rows.values() for e in v if e[2] == m.name),
                  "romfs": r.asset_counts.get(m.name, 0), "maps": r.map_counts.get(m.name, 0),
                  "faces": r.face_counts.get(m.name, 0), "castle": r.castle_counts.get(m.name, 0)}
                 for m in enabled],
        "files": files})
    with open(os.path.join(ctx.stage_dir, "changes.txt"), "w", encoding="utf-8", newline="\n") as fh:
        lines = change_lines(r, ctx)
        fh.write("\n".join(lines) + ("\n" if lines else ""))
    return r


def read_staged(ctx: Ctx) -> dict | None:
    try:
        with open(ctx.staged_json, encoding="utf-8") as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        return None
    if st.get("title_id", TITLE_HEX).upper() != TITLE_HEX:
        raise ModError(f"{ctx.staged_json} was built for another game ({st.get('title_id')}); run build")
    return st


# ------------------------------------------------------------------ install / uninstall
# The install journal (manifest) is written AHEAD of every change: each file's entry is
# recorded as "pending", with the backup path it will use, and flushed to disk before the
# old file is moved aside or the new one copied; it becomes "done" only after the new file
# is in place, and the manifest says "complete" only at the very end. So whatever moment an
# install stops at (crash, power cut, disk full), the manifest names every file it may have
# touched, and uninstall can put back the exact earlier files.
CHANGED = f"{GAME.key}pcport-changed"                     # files changed after install, set aside
                                                          # by uninstall --restore-backups
FAULT = None          # tests only: a function called with the name of each install/uninstall step


def _fault(step: str) -> None:
    if FAULT is not None:
        FAULT(step)


def _fsync_dir(path: str) -> None:
    """Make a rename in path durable where the OS allows it (POSIX; a no-op on Windows)."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def write_manifest(path: str, man: dict) -> None:
    """Write the install journal durably: a temp file, flushed and fsynced, then an atomic
    replace. A failure (disk full) leaves the previous manifest as it was."""
    tmp = path + ".tmp"
    data = (json.dumps(man, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data[: len(data) // 2])
            _fault("manifest")                             # a partial temp manifest is on disk here
            fh.write(data[len(data) // 2:])
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise
    _fsync_dir(os.path.dirname(path))


def _copy_durable(src: str, dst: str) -> None:
    """Copy src to dst (a temp name) and fsync it before the caller renames it into place."""
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        first = True
        while True:
            chunk = fi.read(1 << 20)
            if not chunk:
                break
            if first:
                n = max(1, len(chunk) // 2)
                fo.write(chunk[:n])
                _fault("copying")                          # a partial temp file is on disk here
                fo.write(chunk[n:])
                first = False
            else:
                fo.write(chunk)
        fo.flush()
        os.fsync(fo.fileno())


def _missing_dirs(path: str, top: str) -> list[str]:
    """The directories (absolute, outermost first) needed to make path below top."""
    missing = []
    p = os.path.abspath(path)
    top = os.path.abspath(top)
    while not os.path.isdir(p):
        if os.path.normcase(p) == os.path.normcase(top) or os.path.dirname(p) == p:
            raise ModError(f"{top} does not exist")
        missing.append(p)
        p = os.path.dirname(p)
    return list(reversed(missing))


def _ensure_dir(path: str, top: str, created: list[str]) -> None:
    """Make path (below top) and record, relative to top, each directory we created."""
    for d in _missing_dirs(path, top):
        os.mkdir(d)
        created.append(os.path.relpath(d, top).replace(os.sep, "/"))


def read_manifest(ctx: Ctx) -> dict | None:
    path = os.path.join(ctx.title_dir(), MANIFEST)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise ModError(f"{path} cannot be read ({e}); remove our files by hand or fix it") from None


def interrupted(man: dict | None) -> bool:
    """True when the manifest is the journal of an install, or an uninstall, that did not finish."""
    return bool(man) and (man.get("complete") is False or bool(man.get("uninstalling"))
                          or any(e.get("state") in ("pending", "restoring") for e in man.get("files", [])))


def backup_files(ctx: Ctx) -> list[str]:
    """Every file in the backup folder, as paths relative to it ('romfs/...')."""
    root = os.path.join(ctx.title_dir(), BACKUP)
    out = []
    for d, _dirs, files in os.walk(root):
        for f in files:
            out.append(os.path.relpath(os.path.join(d, f), root).replace(os.sep, "/"))
    return sorted(out)


def _set_aside(tdir: str, rel: str) -> str:
    """Move the file at rel (changed after install) into the CHANGED folder; never overwrite."""
    src = os.path.join(tdir, rel.replace("/", os.sep))
    base = os.path.join(tdir, CHANGED, rel.replace("/", os.sep))
    dst, n = base, 1
    while os.path.exists(dst):
        n += 1
        dst = f"{base}.{n}"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.replace(src, dst)
    return os.path.relpath(dst, tdir).replace(os.sep, "/")


RESTORE_COMMAND = "python tools/mods/mods.py uninstall --restore-backups"


def uninstall(ctx: Ctx, restore_backups: bool = False) -> tuple[bool, list[str]]:
    """Remove the files the manifest lists (only if unchanged since install), put back what
    install moved aside, remove the directories install made if they are empty. Also
    finishes undoing an install that was interrupted at any step, and puts back a previous
    file found in the backup folder without a record when nothing is in its place.
    restore_backups: where a file was changed after install, move it to the CHANGED
    folder (nothing is deleted) and put the previous file back anyway.
    Returns (everything removed and restored, messages)."""
    man = read_manifest(ctx)
    tdir = ctx.title_dir()
    z = ctx.zakuro_dir
    msgs: list[str] = []
    kept: list[dict] = []
    stuck: list[str] = []                                  # plain-language explanations
    named: set[str] = set()
    if man is None and not backup_files(ctx):
        half = os.path.join(tdir, MANIFEST) + ".tmp"
        if os.path.isfile(half):                           # install stopped writing its first record
            os.remove(half)
            return True, ["an earlier install stopped before it changed anything; removed its unfinished record"]
        return True, ["nothing installed by this tool"]
    mpath = os.path.join(tdir, MANIFEST)
    if interrupted(man):
        if man.get("uninstalling") and man.get("complete") is not False:
            msgs.append("an earlier uninstall did not finish (it was interrupted); finishing it")
        else:
            msgs.append("an earlier install did not finish (it was interrupted); undoing what it had done")
    # The uninstall is journaled too. man["files"] always lists the entries not yet undone;
    # before a previous file is put back its entry is marked "restoring" (written ahead), and
    # once it is back the entry is dropped from the manifest. A rerun after a crash therefore
    # never mistakes the owner's restored file for a changed mod file.
    for ent in reversed(list((man or {}).get("files", []))):
        rel = ent["path"]
        dst = os.path.join(tdir, rel.replace("/", os.sep))
        brel = ent.get("backup")
        bak = os.path.join(tdir, brel.replace("/", os.sep)) if brel else None
        if brel:
            named.add(brel[len(BACKUP) + 1:])

        def drop(persist: bool, ent=ent) -> None:
            man["files"].remove(ent)
            if persist:
                write_manifest(mpath, man)

        if ent.get("state") == "restoring" and not (bak and os.path.isfile(bak)):
            # an earlier uninstall already put the previous file back, then stopped
            msgs.append(f"your previous {rel} was already put back")
            drop(True)
            _fault("un-dropped")
            continue
        if ent.get("state") == "pending":
            tmp = dst + TMP_SUFFIX
            if os.path.isfile(tmp):
                os.remove(tmp)
                msgs.append(f"removed the half-copied {rel}{TMP_SUFFIX}")
            if bak and not os.path.isfile(bak):
                # the install stopped before moving the earlier file aside: it is still in place
                msgs.append(f"{rel}: the install stopped before touching it; left as it was")
                drop(False)
                continue
        if os.path.isfile(dst):
            if file_sha(dst) == ent["sha256"]:
                os.remove(dst)
                _fault("un-removed")
                msgs.append(f"removed {rel}")
            elif restore_backups:
                where = _set_aside(tdir, rel)
                _fault("un-setaside")
                msgs.append(f"{rel} was changed after install; moved it to {where} (not deleted)")
            else:
                msgs.append(f"left in place (changed since install): {dst}")
                kept.append(ent)
                if bak and os.path.isfile(bak):
                    stuck.append(f"{rel} was changed after it was installed, so uninstall left it in place. "
                                 f"The file that was there BEFORE the install (your previous file) is safe in "
                                 f"{bak}. It was not put back, because that would overwrite the changed file.")
                else:
                    stuck.append(f"{rel} was changed after it was installed, so uninstall left it in place.")
                continue
        if bak and os.path.isfile(bak):
            ent["state"] = "restoring"                     # write ahead: the restore about to happen
            man["uninstalling"] = True
            write_manifest(mpath, man)
            _fault("un-marked")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(bak, dst)
            _fsync_dir(os.path.dirname(dst))
            _fault("un-restored")
            msgs.append(f"restored your previous {rel}")
            drop(True)
            _fault("un-dropped")
        else:
            drop(False)                                    # nothing to put back; our file is gone
    # previous files in the backup folder that no manifest entry names (manifest deleted by
    # hand, or left by an older version of this tool, which moved a file before recording it)
    for orel in backup_files(ctx):
        if orel in named:
            continue
        bak = os.path.join(tdir, BACKUP, orel.replace("/", os.sep))
        dst = os.path.join(tdir, orel.replace("/", os.sep))
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(bak, dst)
            _fault("un-orphan")
            msgs.append(f"restored your previous {orel} (found in {BACKUP} without an install record)")
        elif restore_backups and os.path.isfile(dst):
            where = _set_aside(tdir, orel)
            _fault("un-setaside")
            os.replace(bak, dst)
            _fault("un-orphan")
            msgs.append(f"moved the file at {orel} to {where} (not deleted) and restored your previous {orel}")
        else:
            msgs.append(f"left in place: {bak}")
            stuck.append(f"{bak} is your previous copy of {orel}, from before an earlier install. It was not "
                         f"put back, because a different file is now at {dst} and there is no install record "
                         "saying whose it is.")
    def remove_empty_dirs() -> None:
        # anything left empty in the backup folder, and the folders install made; safe to repeat
        broot = os.path.join(tdir, BACKUP)
        for d, _dirs, _files in sorted(os.walk(broot), key=lambda t: t[0].count(os.sep), reverse=True):
            with contextlib.suppress(OSError):
                os.rmdir(d)
        for d in sorted((man or {}).get("created_dirs", []), key=lambda p: p.count("/"), reverse=True):
            with contextlib.suppress(OSError):
                os.rmdir(os.path.join(z, d.replace("/", os.sep)))

    if kept:
        # man["files"] now holds exactly the kept entries (the others were dropped as undone)
        man["complete"] = True
        man.pop("uninstalling", None)
        for e in man["files"]:
            e["state"] = "done"
        write_manifest(mpath, man)
    elif man is not None:
        remove_empty_dirs()            # while the manifest still names them (a crash here is harmless)
        _fault("un-end")
        os.remove(mpath)
    with contextlib.suppress(OSError):
        os.remove(mpath + ".tmp")
    remove_empty_dirs()
    if stuck:
        msgs.append("")
        msgs += stuck
        msgs.append(f"To put your previous files back, run:  {RESTORE_COMMAND}")
        msgs.append(f"  It moves each changed file to {os.path.join(tdir, CHANGED)} (nothing is deleted) and "
                    "puts your previous file back. Then install again if you want the mods.")
    return not stuck, msgs


def install(ctx: Ctx) -> list[str]:
    """Copy the staged files into Zakuro's title folder. Any earlier install by this tool
    (finished or interrupted) is undone first. Refuses if that would destroy something it
    does not own. The manifest is a write-ahead journal: each file is recorded, with its
    backup path, before anything is moved; the file is copied to a temporary name, fsynced
    and renamed into place; then the entry is marked done. A crash at any point leaves
    nothing uninstall cannot undo; a disk error is undone at once."""
    if not os.path.isdir(ctx.zakuro_dir):
        raise ModError(f"Zakuro's data folder {ctx.zakuro_dir} does not exist (start Zakuro once, "
                       "or pass --zakuro-dir)")
    st = read_staged(ctx)
    if st is None:
        raise ModError("nothing staged (python tools/mods/mods.py build)")
    for f in st["files"]:
        p = os.path.join(ctx.stage_romfs, f["path"].replace("/", os.sep))
        if not os.path.isfile(p) or file_sha(p) != f["sha256"]:
            raise ModError(f"staged file {p} is missing or changed; run build again")
    msgs = []
    if read_manifest(ctx) is not None or backup_files(ctx):
        ok, m = uninstall(ctx)
        msgs += m
        if not ok:
            raise ModError("install stopped before changing anything: the earlier install could not be fully "
                           "undone.\n  " + "\n  ".join(m))
    if not st["files"]:
        msgs.append("no enabled mod changes anything: nothing to install")
        return msgs
    tdir = ctx.title_dir()
    z = ctx.zakuro_dir
    mpath = os.path.join(tdir, MANIFEST)
    created: list[str] = []
    man = {"tool": f"{GAME_NAME} PC port tools/mods/mods.py", "format": TOOL_VERSION,
           "title_id": TITLE_HEX, "installed": time.strftime("%Y-%m-%d %H:%M:%S"),
           "fingerprint": st.get("fingerprint"), "mods": [m["name"] for m in st["mods"]],
           "complete": False, "created_dirs": created, "files": []}
    _ensure_dir(tdir, z, created)
    try:
        write_manifest(mpath, man)
        for f in st["files"]:
            rel = "romfs/" + f["path"]
            dst = os.path.join(tdir, rel.replace("/", os.sep))
            src = os.path.join(ctx.stage_romfs, f["path"].replace("/", os.sep))
            ent = {"path": rel, "sha256": f["sha256"], "backup": None, "state": "pending"}
            need = _missing_dirs(os.path.dirname(dst), z)
            bak = None
            if os.path.exists(dst):
                brel = f"{BACKUP}/{rel}"
                bak = os.path.join(tdir, brel.replace("/", os.sep))
                if os.path.exists(bak):
                    raise ModError(f"{bak} is a previous copy of {rel}, kept from an earlier install, and it "
                                   f"was not put back. Run:  {RESTORE_COMMAND}  (it puts that file back and "
                                   f"keeps the one now at {rel} in {CHANGED}), then install again.")
                ent["backup"] = brel
                need += [d for d in _missing_dirs(os.path.dirname(bak), z) if d not in need]
            # write ahead: record the folders we will make and the move we will do, then do them
            created += [os.path.relpath(d, z).replace(os.sep, "/") for d in need]
            man["files"].append(ent)
            write_manifest(mpath, man)
            _fault("planned")
            for d in need:
                os.mkdir(d)
            if bak:
                os.replace(dst, bak)
                _fsync_dir(os.path.dirname(bak))
                _fault("moved")
                msgs.append(f"moved the existing {rel} aside to {ent['backup']}")
            tmp = dst + TMP_SUFFIX
            _copy_durable(src, tmp)
            _fault("copied")
            os.replace(tmp, dst)
            _fsync_dir(os.path.dirname(dst))
            _fault("placed")
            ent["state"] = "done"
            write_manifest(mpath, man)
            _fault("recorded")
            msgs.append(f"installed {rel}")
        man["complete"] = True
        write_manifest(mpath, man)
    except (OSError, ModError) as e:
        # a disk error (disk full, file locked) or a refusal part-way: undo what was done, now
        try:
            ok, m = uninstall(ctx)
        except (OSError, ModError) as e2:
            raise ModError(f"install stopped: {e}\n  undoing it also failed ({e2}). Your previous files are "
                           f"safe in {os.path.join(tdir, BACKUP)}; when the problem is fixed run:  "
                           "python tools/mods/mods.py uninstall") from None
        why = " (is the disk full?)" if isinstance(e, OSError) else ""
        raise ModError(f"install stopped: {e}{why}\n  everything it had done was undone"
                       + ("" if ok else ", except:") + "\n  " + "\n  ".join(m)) from None
    return msgs


# ------------------------------------------------------------------ the demo mods
EXAMPLE_NAME = "Example"
EXAMPLE_ENGLISH = "Ryoma"                 # found through the English name text, at run time
NAME_PREFIX = b"MPID_"                    # unit display-name labels in the name archive
NAME_ARCHIVE = TX.NAME_ARCHIVE            # m/@E/GameData.bin.lz
# the Strength column of the Person table: the first of these names the layout has
EXAMPLE_COLS = ("base_stats.str", "bases.str", "base.str", "stats.str", "base_stats.1", "bases.1")
EXAMPLE_DELTA = 10
TEXT_EXAMPLE_NAME = "ExampleText"
TEXT_EXAMPLE_NEW = "Ryouma"               # what the demo renames him to


def example_name_label(ctx: Ctx) -> bytes:
    """The name label (MPID_...) in the English name archive whose text is exactly
    EXAMPLE_ENGLISH. Looked up in the user's own files, so no game string is written in
    this repository."""
    try:
        van = TX.archive(NAME_ARCHIVE, ctx.romfs)
    except TX.TextError as e:
        raise ModError(str(e)) from None
    hit = [lab for lab, _v, a in van.entries
           if lab.startswith(NAME_PREFIX) and not a and van.text_of[lab] == EXAMPLE_ENGLISH]
    if len(hit) != 1:
        raise ModError(f"expected one {NAME_PREFIX.decode()} label named {EXAMPLE_ENGLISH!r} in "
                       f"{NAME_ARCHIVE}, found {len(hit)}")
    return hit[0]


def make_text_example(ctx: Ctx) -> tuple[Mod, str]:
    """mods/ExampleText: one name label in m/@E/GameData.bin.lz, Ryoma -> Ryouma. The mod
    file holds only the two header lines and that label (no other game text)."""
    lab = example_name_label(ctx)
    van = TX.archive(NAME_ARCHIVE, ctx.romfs)
    m = new_mod(ctx, TEXT_EXAMPLE_NAME, f"Demo: {EXAMPLE_ENGLISH}'s name shows as {TEXT_EXAMPLE_NEW} "
                "(text mod, see docs/MODDING.md)", tables=[])
    path = os.path.join(m.dir, TX.TEXT_DIR, *NAME_ARCHIVE.split("/")) + TX.SUFFIX
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = "\n".join([TX.HEADER, "#name " + TX.msg.isbin.quote(van.name),
                      "# only the labels you change are needed; the rest of the archive stays as in the game",
                      f"[{lab.decode('cp932')}]", TX.msg.escape(TEXT_EXAMPLE_NEW)]) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    return m, (f"{NAME_ARCHIVE} [{lab.decode('cp932', 'backslashreplace')}]: "
               f"{van.text_of[lab]} -> {TEXT_EXAMPLE_NEW}")


def example_target(ctx: Ctx) -> tuple[str, tuple, str]:
    """(Person file, row key, Strength column) of the demo unit: the one Person row (in
    the table's first file, the main cast) that has a cell equal to his name label."""
    why = tables_status()
    if why:
        raise ModError(f"the table demo needs the Person layout: {why}. The text demo works today: "
                       "python tools/mods/mods.py example-text")
    van = vanilla()
    if "Person" not in van:
        raise ModError("the table demo needs a Person layout in config/tables/ (not there yet); "
                       "the text demo works today: python tools/mods/mods.py example-text")
    head, rows = van["Person"]
    col = next((c for c in EXAMPLE_COLS if c in head), None)
    if col is None:
        raise ModError(f"Person has none of the Strength columns {', '.join(EXAMPLE_COLS)}; "
                       "update EXAMPLE_COLS in tools/mods/mods.py to the layout's name")
    want = T.text(example_name_label(ctx))
    first = reg()["Person"].files()[0]
    hit = [r for r in rows if want in r and row_rel("Person", row_key("Person", r)) == first]
    if len(hit) != 1:
        raise ModError(f"expected one Person row in {first} with the name label of {EXAMPLE_ENGLISH!r}, "
                       f"found {len(hit)}")
    return first, row_key("Person", hit[0]), col


def make_example(ctx: Ctx) -> tuple[Mod, str]:
    """mods/Example: Ryoma's Strength column +10 in the main Person file. Only Person.csv
    is copied, trimmed to the ID columns and that one column and row."""
    rel, key, col = example_target(ctx)
    head, rows = vanilla()["Person"]
    ids = [h for h in head if h in ID_COLS]
    row = next(r for r in rows if row_key("Person", r) == key)
    old = parse_int(row[head.index(col)])
    if old is None:
        raise ModError(f"Person {col} is not a number")
    cells = cells_of("Person")
    f, _k = cells.info[col]
    lo, hi = int_range(f.width, f.signed)
    new = max(lo, min(hi, old + EXAMPLE_DELTA))
    m = new_mod(ctx, EXAMPLE_NAME, f"Demo: {EXAMPLE_ENGLISH}'s Strength +{EXAMPLE_DELTA} (see docs/MODDING.md)",
                tables=[])
    write_table_csv(os.path.join(m.dir, "tables", "Person.csv"), ids + [col],
                    [[row[head.index(h)] for h in ids] + [str(new)]])
    return m, f"{EXAMPLE_ENGLISH} ({row[head.index('label')]}, {rel}) {col}: {old} -> {new}"


ITEM_EXAMPLE_NAME = "ExampleItem"
ITEM_EXAMPLE_BASE = "Bronze Sword"        # English display name of the item copied, found at run time
ITEM_EXAMPLE_LABEL = "IID_EXAMPLE_SWORD"   # the new record's ID (our own name)
ITEM_EXAMPLE_TEXT = "Example Sword"        # our own display name for it
ITEM_EXAMPLE_HELP = "A Bronze Sword copy with 5 more might, added by the ExampleItem mod."
ITEM_EXAMPLE_MIGHT = 5
ITEM_EXAMPLE_DISPOS = "GameData/Dispos/A001.bin.lz"   # Chapter 1 placement: the avatar's starting items
ITEM_NAME_PREFIX = b"MIID_"


def example_item_base(ctx: Ctx) -> list[str]:
    """The Item row whose display name (English text of its miid_name label) is exactly
    ITEM_EXAMPLE_BASE; the lowest-numbered one if several share the name. Looked up in
    the user's own files, so no game string is written in this repository."""
    try:
        van = TX.archive(NAME_ARCHIVE, ctx.romfs)
    except TX.TextError as e:
        raise ModError(str(e)) from None
    labs = {T.text(lab) for lab, _v, a in van.entries
            if lab.startswith(ITEM_NAME_PREFIX) and van.text_of[lab] == ITEM_EXAMPLE_BASE}
    head, rows = vanilla()["Item"]
    hit = [r for r in rows if r[head.index("miid_name")] in labs]
    if not hit:
        raise ModError(f"no Item row is named {ITEM_EXAMPLE_BASE!r} in {NAME_ARCHIVE}")
    return hit[0]


def make_item_example(ctx: Ctx) -> tuple[Mod, str]:
    """mods/ExampleItem: one new Item row (a copy of the Bronze Sword, might +5, its own
    ID and name), its name and help text as two new messages in the name archive, and the
    avatar's first empty item slot in Chapter 1's placement file set to the new item."""
    why = tables_status()
    if why:
        raise ModError(f"the new-item demo needs the table layouts: {why}")
    van = vanilla()
    for need in ("Item", "DisposUnit"):
        if need not in van:
            raise ModError(f"the new-item demo needs the {need} layout in config/tables/")
    why = T.append_refusal(reg()["Item"])
    if why:
        raise ModError(f"the new-item demo cannot add an item: {why}")
    head, rows = van["Item"]
    col = {h: i for i, h in enumerate(head)}
    base = example_item_base(ctx)
    new = list(base)
    new[col["index"]] = str(len(rows))
    new[col["label"]] = new[col["iid"]] = ITEM_EXAMPLE_LABEL
    new[col["item_number"]] = ""                                # filled in by the build
    f, _k = cells_of("Item").info["might"]
    lo, hi = int_range(f.width, f.signed)
    old = int(base[col["might"]])
    new[col["might"]] = str(max(lo, min(hi, old + ITEM_EXAMPLE_MIGHT)))
    name_lab = "MIID_" + ITEM_EXAMPLE_LABEL[len("IID_"):]
    help_lab = "MIID_H_" + ITEM_EXAMPLE_LABEL[len("IID_"):]
    new[col["miid_name"]], new[col["miid_help"]] = name_lab, help_lab
    # the avatar in Chapter 1: the player-team unit there that carries the copied item
    dh, drows = van["DisposUnit"]
    dc = {h: i for i, h in enumerate(dh)}
    slots = [f"item_{k}" for k in range(1, 6)]
    mine = [r for r in drows if r[0] == ITEM_EXAMPLE_DISPOS and r[dc["team"]] == "0"]
    unit = next((r for r in mine if base[col["label"]] in [r[dc[s]] for s in slots]), mine[0] if mine else None)
    if unit is None:
        raise ModError(f"no player unit in {ITEM_EXAMPLE_DISPOS}")
    slot = next((s for s in slots if unit[dc[s]] == ""), None)
    if slot is None:
        raise ModError(f"the unit in {ITEM_EXAMPLE_DISPOS} has no empty item slot")
    m = new_mod(ctx, ITEM_EXAMPLE_NAME, f"Demo: a new item, {ITEM_EXAMPLE_TEXT} ({ITEM_EXAMPLE_BASE} copy, "
                f"might +{ITEM_EXAMPLE_MIGHT}), in the avatar's Chapter 1 items (see docs/MODDING.md)", tables=[])
    write_table_csv(os.path.join(m.dir, "tables", "Item.csv"), head, [new])
    write_table_csv(os.path.join(m.dir, "tables", "DisposUnit.csv"), ["file", "index", "label", slot],
                    [[unit[0], unit[1], unit[2], ITEM_EXAMPLE_LABEL]])
    arc = TX.archive(NAME_ARCHIVE, ctx.romfs)
    path = os.path.join(m.dir, TX.TEXT_DIR, *NAME_ARCHIVE.split("/")) + TX.SUFFIX
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = "\n".join([TX.HEADER, "#name " + TX.msg.isbin.quote(arc.name),
                      "# new messages for the new item (labels the game does not have are allowed",
                      "# only when a row this mod adds names them)",
                      f"[{name_lab}]", TX.msg.escape(ITEM_EXAMPLE_TEXT),
                      f"[{help_lab}]", TX.msg.escape(ITEM_EXAMPLE_HELP)]) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    return m, (f"Item #{len(rows)} {ITEM_EXAMPLE_LABEL} = {base[col['label']]} with might {old} -> "
               f"{new[col['might']]}, named {ITEM_EXAMPLE_TEXT!r}; {ITEM_EXAMPLE_DISPOS} unit #{unit[1]} "
               f"({unit[dc['pid']]}) {slot} = {ITEM_EXAMPLE_LABEL}")


MAP_EXAMPLE_NAME = "ExampleMap"
MAP_EXAMPLE_MAP = "A007"                  # Birthright Chapter 7 (docs/MAPS.md, docs/ROUTES.md)
FACE_EXAMPLE_NAME = "ExampleFace"
FACE_EXAMPLE_MEMBER = "通常"      # member file name prefix of the normal expression


def find_or_new_mod(ctx: Ctx, name: str) -> Mod:
    """The mod NAME, or a new empty one (no spreadsheets) when there is none yet."""
    try:
        return find_mod(ctx, name)
    except ModError:
        m = new_mod(ctx, name, tables=[])
        ctx.say(f"made the empty mod {os.path.relpath(m.dir, ROOT)}")
        return m


def add_map(ctx: Ctx, mod: Mod, name: str) -> str:
    """Write the map package NAME (from the user's game) into mod/maps/NAME/."""
    why = MF.maplib_status()
    if why:
        raise ModError(f"map mods are not available: {why}")
    M = MF.maplib()
    if name not in M.packages():
        raise ModError(f"no map called {name} (python tools/maps/maps.py list)")
    d = os.path.join(mod.dir, MF.MAPS_DIR, name)
    if os.path.exists(d):
        raise ModError(f"{d} already exists")
    try:
        return M.export(name, os.path.join(mod.dir, MF.MAPS_DIR))
    except M.MapError as e:
        raise ModError(str(e)) from None


def face_records(ctx: Ctx, query: str) -> list[dict]:
    why = MF.portrait_status()
    if why:
        raise ModError(f"face mods are not available: {why}")
    P = MF.portrait()
    P.ROMFS = ctx.romfs
    recs = P.match(P.load_facedata(os.path.join(ctx.romfs, "face", "FaceData.bin.lz")), query)
    if not recs:
        raise ModError(f"no portrait matches {query!r} (python tools/assets/portrait.py list)")
    return recs


def add_face(ctx: Ctx, mod: Mod, folder: str, recs: list[dict], sources: list[str] | None = None) -> str:
    """Write the portrait folder of recs (portrait.py export) into mod/faces/<folder>/."""
    P = MF.portrait()
    d = os.path.join(mod.dir, MF.FACES_DIR, folder)
    if os.path.exists(d):
        raise ModError(f"{d} already exists")
    try:
        P.export_sources(sources if sources is not None else P.sources_for(recs), d, recs)
    except (P.PortraitError, ValueError) as e:
        raise ModError(str(e)) from None
    return d


def make_map_example(ctx: Ctx) -> tuple[Mod, str]:
    """mods/ExampleMap: the A007 map package with one enemy of its first enemy group moved
    two tiles (the enemy and the tile are found at run time; the build checks the move)."""
    why = MF.maplib_status() or tables_status()
    if why:
        raise ModError(f"the map demo needs the map tools: {why}")
    m = new_mod(ctx, MAP_EXAMPLE_NAME, f"Demo: one enemy of {MAP_EXAMPLE_MAP} (Birthright Chapter 7) moved "
                "two tiles (map mod, see docs/MODDING.md)", tables=[])
    d = add_map(ctx, m, MAP_EXAMPLE_MAP)
    try:
        world, _n = MF.make_world([x for x in load_mods(ctx) if x.enabled and x.folder != m.folder])
        pid, jid, old, new = MF.example_map_edit(d, MAP_EXAMPLE_MAP, world)
    except (ValueError, MF.maplib().MapError) as e:
        shutil.rmtree(m.dir, ignore_errors=True)
        raise ModError(str(e)) from None
    pv = os.path.join(d, "preview.png")
    if os.path.isfile(pv):          # redraw the picture with the unit in its new place
        M = MF.maplib()
        head, rows = M.read_csv(os.path.join(d, "units.csv"))
        units = [dict(zip(head, r), first_group=not r[0].startswith("Reinforce")) for r in rows]
        t = M.Terrain(M.packages()[MAP_EXAMPLE_MAP]["terrain_ref"])
        M.write_bytes(pv, M.preview_png(t, units, world))
    m.meta["description"] += f" - {pid} ({jid or 'own class'}) {old[0]},{old[1]} -> {new[0]},{new[1]}"
    m.save()
    return m, f"{MAP_EXAMPLE_MAP}: enemy {pid} ({jid or 'own class'}) moved from {old} to {new}"


def make_face_example(ctx: Ctx) -> tuple[Mod, str]:
    """mods/ExampleFace: Ryoma's standing portrait package (found through his name label);
    its first expression picture is tinted blue by code (mapface.tint_png). No picture is
    stored in the repository: the folder is exported from the user's game here."""
    lab = example_name_label(ctx).decode("cp932")
    recs = [r for r in face_records(ctx, lab) if r["mpid"] == lab and r["package"].endswith("_st")]
    if not recs:
        raise ModError(f"no standing portrait (package ending _st) for {EXAMPLE_ENGLISH}")
    rec = recs[0]
    m = new_mod(ctx, FACE_EXAMPLE_NAME, f"Demo: {EXAMPLE_ENGLISH}'s normal standing portrait tinted blue "
                "(face mod, see docs/MODDING.md)", tables=[])
    try:
        src = f"face/face/{rec['package']}.arc"
        d = add_face(ctx, m, EXAMPLE_ENGLISH, [rec], [src])
        with open(os.path.join(d, "portrait.json"), encoding="utf-8") as fh:
            man = json.load(fh)
        exprs = [x for x in man["layers"] if x["role"] == "expression"]
        # the member named "normal" (the file name portrait.py's notes give), else the first
        ly = next((x for x in exprs if (x["member"] or "").startswith(FACE_EXAMPLE_MEMBER)), exprs[0])
        w, h = MF.tint_png(MF.portrait(), os.path.join(d, *ly["png"].split("/")))
    except (ModError, StopIteration, OSError, ValueError) as e:
        shutil.rmtree(m.dir, ignore_errors=True)
        raise ModError(f"the face demo failed: {e}") from None
    return m, f"{src} member {ly['member']} ({w}x{h}) tinted blue"


CASTLE_EXAMPLE_NAME = "ExampleCastle"
CASTLE_EXAMPLE_FILE = "DiningData"              # GameData/Castle/DiningData.bin.lz
CASTLE_EXAMPLE_SHEET = "DiningData_Dish"
CASTLE_EXAMPLE_INGREDIENT = 0                   # the dish made from this ingredient alone (ingredient_2 = 255)
CASTLE_EXAMPLE_COL = "str"                      # ReflectDishEffect adds dish+0x6+i to stat i (docs/CASTLE.md)
CASTLE_EXAMPLE_DELTA = 3


def add_castle(ctx: Ctx, mod: Mod, name: str, keys: list[str] | None = None) -> str:
    """Write the spreadsheets of the castle file NAME (from the user's game) into
    mod/castle/NAME/ (all its sheets, or only `keys`)."""
    why = CM.status()
    if why:
        raise ModError(f"castle mods are not available: {why}")
    d = os.path.join(mod.dir, CM.CASTLE_DIR, name)
    if os.path.exists(d):
        raise ModError(f"{d} already exists")
    try:
        return CM.write_folder(mod.dir, name, keys)
    except (ValueError, OSError) as e:
        raise ModError(str(e)) from None


def make_castle_example(ctx: Ctx) -> tuple[Mod, str]:
    """mods/ExampleCastle: the dining dishes sheet with the Strength bonus of one dish raised
    by CASTLE_EXAMPLE_DELTA. The dish is the one made from dining ingredient
    CASTLE_EXAMPLE_INGREDIENT alone, found by its ingredient numbers at run time (no game
    text is stored here)."""
    why = CM.status()
    if why:
        raise ModError(f"the castle demo needs tools/castle: {why}")
    m = new_mod(ctx, CASTLE_EXAMPLE_NAME, f"Demo: the dish made from dining ingredient "
                f"{CASTLE_EXAMPLE_INGREDIENT} alone gives Strength +{CASTLE_EXAMPLE_DELTA} more "
                "(castle mod, see docs/MODDING.md)", tables=[])
    try:
        d = add_castle(ctx, m, CASTLE_EXAMPLE_FILE, [CASTLE_EXAMPLE_SHEET])
        p = os.path.join(d, f"{CASTLE_EXAMPLE_SHEET}.csv")
        L = CM.castle().L
        head, rows = L.read_csv(p)
        i = CM.example_dish(rows, head, CASTLE_EXAMPLE_INGREDIENT)
        j = head.index(CASTLE_EXAMPLE_COL)
        old = int(rows[i][j], 0)
        new = old + CASTLE_EXAMPLE_DELTA
        if not -128 <= new <= 127:
            raise ValueError(f"{CASTLE_EXAMPLE_COL} {old} + {CASTLE_EXAMPLE_DELTA} does not fit a signed byte")
        rows[i][j] = str(new)
        L.write_csv(p, head, rows)
    except (ModError, ValueError, OSError, KeyError) as e:
        shutil.rmtree(m.dir, ignore_errors=True)
        raise ModError(f"the castle demo failed: {e}") from None
    m.meta["description"] += f" - dish row {i}: {CASTLE_EXAMPLE_COL} {old} -> {new}"
    m.save()
    return m, (f"{CASTLE_EXAMPLE_SHEET} row {i} (made from ingredient {CASTLE_EXAMPLE_INGREDIENT} alone): "
               f"{CASTLE_EXAMPLE_COL} {old} -> {new}")


# ------------------------------------------------------------------ commands
def print_build(ctx: Ctx, r: BuildResult, staged: bool) -> int:
    for n in r.notes:
        ctx.say("note:", n)
    for w in sorted(set(r.warnings))[:20]:
        ctx.say("warning:", w)
    if r.errors:
        for e in r.errors[:50]:
            ctx.say("ERROR:", e)
        if len(r.errors) > 50:
            ctx.say(f"... and {len(r.errors) - 50} more")
        ctx.say(f"build FAILED: {len(r.errors)} problem(s); nothing staged")
        return 1
    for m in dict.fromkeys(list(r.counts) + list(r.text_counts) + list(r.asset_counts)
                           + list(r.map_counts) + list(r.face_counts) + list(r.castle_counts)):
        parts = [f"{r.counts.get(m, 0)} changed cell(s)"]
        nrows = sum(1 for v in r.new_rows.values() for e in v if e[2] == m)
        if nrows:
            parts.append(f"{nrows} new row(s)")
        if r.text_counts.get(m):
            parts.append(f"{r.text_counts[m]} changed text label(s)")
        if r.asset_counts.get(m):
            parts.append(f"{r.asset_counts[m]} whole file(s)")
        if m in r.map_counts:
            parts.append(f"{r.map_counts[m]} map file(s)")
        if m in r.face_counts:
            parts.append(f"{r.face_counts[m]} portrait file(s)")
        if m in r.castle_counts:
            parts.append(f"{r.castle_counts[m]} castle cell(s)/row(s)")
        ctx.say(f"  {m}: {', '.join(parts)}")
    for rel in r.paths():
        ctx.say(f"  staged romfs/{rel}")
    where = os.path.relpath(ctx.stage_romfs, ROOT) if staged else "(not written)"
    nmods = len(set(r.counts) | set(r.text_counts) | set(r.asset_counts) | set(r.map_counts) | set(r.face_counts)
                | set(r.castle_counts))
    texts = f", {len(r.text_merged)} text label(s)" if r.text_merged else ""
    assets = f", {len(r.assets)} whole file(s)" if r.assets else ""
    assets += f", {len(r.maps)} map file(s)" if r.maps else ""
    assets += f", {len(r.faces)} portrait file(s)" if r.faces else ""
    assets += f", {len(r.castle)} castle file(s)" if r.castle else ""
    nrows = sum(len(v) for v in r.new_rows.values())
    texts = (f", {nrows} new row(s)" if nrows else "") + texts
    ctx.say(f"build OK: {len(r.merged)} cell(s){texts}{assets} from {nmods} enabled mod(s) -> "
            f"{len(r.paths())} file(s) in {where}")
    return 0


def cmd_list(ctx: Ctx) -> int:
    mods = load_mods(ctx)
    if not mods:
        ctx.say(f"no mods in {ctx.mods_dir} (python tools/mods/mods.py new MyMod)")
        return 0
    index = _CaseIndex(ctx.romfs)
    ctx.say(f"{'order':>5}  {'on':3} {'override':8} {'cells':>5} {'texts':>5} {'files':>5} {'maps':>4} "
            f"{'faces':>5} {'castle':>6}  name - description")
    for m in mods:
        rows: dict = {}
        ch, errs, _w = diff_mod(m, rows_out=rows)
        need = set(new_text_ids(ctx, {n: [(ix, x, m.name) for ix, x in v] for n, v in rows.items()}))
        tch, terrs, _tw, _tn = diff_mod_text(ctx, m, need)
        ach, aerrs, _aw, _an = diff_mod_assets(ctx, m, index)
        nrows = sum(len(v) for v in rows.values())
        cells = f"{len(ch)}" + (f"+{nrows}r" if nrows else "") + ("!" if errs else "")
        texts = f"{len(tch)}" + ("!" if terrs else "")
        files = f"{len(ach)}" + ("!" if aerrs else "")
        ctx.say(f"{m.order:5}  {'yes' if m.enabled else 'no':3} {'yes' if m.override else '':8} {cells:>5} "
                f"{texts:>5} {files:>5} {len(m.maps()):>4} {len(m.faces()):>5} {len(m.castle()):>6}  "
                f"{m.name} - {m.description}")
    ctx.say("(cells / texts / files = cells, text labels and whole romfs files that differ from the "
            "original game; +Nr = N new rows; '!' = the mod has errors, run build; maps / faces / castle = map, "
            "portrait and castle file folders, checked when you build)")
    why = tables_status()
    if why:
        ctx.say(f"(table mods are off: {why})")
    return 0


def cmd_status(ctx: Ctx) -> int:
    mods = load_mods(ctx)
    on = [m.name for m in mods if m.enabled]
    ctx.say(f"game: {GAME_NAME} ({GAME.edition}), title {TITLE_HEX}")
    ctx.say(f"mods: {len(mods)} in {ctx.mods_dir}; enabled (in order): {', '.join(on) or 'none'}")
    why = tables_status()
    ctx.say(f"table mods: {'available' if not why else 'off - ' + why}")
    st = read_staged(ctx)
    if st is None:
        ctx.say("staged: nothing (run build)")
    else:
        fresh = st.get("fingerprint") == fingerprint(ctx)
        ctx.say(f"staged: {len(st['files'])} file(s), built {st['built']}"
                f"{'' if fresh else '  -- OUT OF DATE: mods changed since, run build/install'}")
        for f in st["files"]:
            if f.get("kind") == "text":
                ctx.say(f"  romfs/{f['path']}  ({f['labels']} text label(s))")
            elif f.get("kind") == "romfs":
                ctx.say(f"  romfs/{f['path']}  (whole file from {f.get('mod', '?')})")
            elif f.get("kind") in ("map", "face", "castle"):
                what = {"map": "map edits", "face": "portrait edits", "castle": "castle edits"}[f["kind"]]
                ctx.say(f"  romfs/{f['path']}  ({what} from {f.get('mod', '?')})")
            else:
                nr = f.get("new_rows", 0)
                more = f", {nr} new row(s)" if nr else ""
                ctx.say(f"  romfs/{f['path']}  ({f['cells']} cell(s){more}: {', '.join(f['tables'])})")
    tdir = ctx.title_dir()
    ctx.say(f"zakuro mod folder: {tdir}{'' if os.path.isdir(ctx.zakuro_dir) else '  (Zakuro data folder not found)'}")
    try:
        man = read_manifest(ctx)
    except ModError as e:
        ctx.say(f"installed: {e}")
        return 1
    if man is None:
        ctx.say("installed: nothing by this tool")
    else:
        ctx.say(f"installed: {len(man['files'])} file(s) on {man['installed']} from {', '.join(man['mods'])}")
        if interrupted(man) and man.get("uninstalling") and man.get("complete") is not False:
            ctx.say("  AN UNINSTALL DID NOT FINISH (it was interrupted). Run python tools/mods/mods.py uninstall "
                    "to finish it: it puts the rest of your previous files back.")
        elif interrupted(man):
            ctx.say("  THIS INSTALL DID NOT FINISH (it was interrupted). Run python tools/mods/mods.py uninstall "
                    "(or install again): it puts your previous files back first.")
        staged_sha = {"romfs/" + f["path"]: f["sha256"] for f in (st or {}).get("files", [])}
        for ent in man["files"]:
            p = os.path.join(tdir, ent["path"].replace("/", os.sep))
            state = ("missing" if not os.path.isfile(p) else
                     "intact" if file_sha(p) == ent["sha256"] else "CHANGED since install")
            same = "" if staged_sha.get(ent["path"]) == ent["sha256"] else ", differs from the staged build"
            ctx.say(f"  {ent['path']}: {state}{same}"
                    + (f" (earlier file kept in {ent['backup']})" if ent.get("backup") else ""))
        if st is not None and set(staged_sha) != {e["path"] for e in man["files"]}:
            ctx.say("  the staged build has other files than the installed one: run install")
    named = {e["backup"][len(BACKUP) + 1:] for e in (man or {}).get("files", []) if e.get("backup")}
    loose = [r for r in backup_files(ctx) if r not in named]
    if loose:
        ctx.say(f"previous files in {BACKUP} without an install record ({len(loose)}): run "
                "python tools/mods/mods.py uninstall to put them back")
        for r in loose[:10]:
            ctx.say(f"  {r}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zakuro-dir", help="Zakuro's data folder (default %%APPDATA%%\\zakuro)")
    ap.add_argument("--mods-dir", help="the mods workspace (default mods/ in the repo)")
    ap.add_argument("--stage-dir", help="where build stages its files (default build/mods/)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new", help="make a mod")
    p.add_argument("name")
    p.add_argument("--description", default="")
    p.add_argument("--tables", help="comma-separated tables to copy (default: all with a layout, "
                                    "or none with --text)")
    p.add_argument("--text", help="comma-separated message archives to copy as text files "
                                  f"(RomFS paths, e.g. {NAME_ARCHIVE})")
    p = sub.add_parser("text", help="add message archive text file(s) to a mod")
    p.add_argument("name")
    p.add_argument("archives", nargs="+", help=f"RomFS paths, e.g. {NAME_ARCHIVE}")
    sub.add_parser("archives", help="where the message archives are")
    sub.add_parser("example", help=f"make the demo mod 'Example' ({EXAMPLE_ENGLISH}: Strength +{EXAMPLE_DELTA})")
    sub.add_parser("example-text", help=f"make the demo mod 'ExampleText' ({EXAMPLE_ENGLISH}'s name -> "
                                        f"{TEXT_EXAMPLE_NEW})")
    sub.add_parser("example-item", help=f"make the demo mod '{ITEM_EXAMPLE_NAME}' (a new item: "
                                        f"{ITEM_EXAMPLE_BASE} copy, might +{ITEM_EXAMPLE_MIGHT})")
    sub.add_parser("example-map", help=f"make the demo mod '{MAP_EXAMPLE_NAME}' (one enemy of "
                                       f"{MAP_EXAMPLE_MAP} moved two tiles)")
    sub.add_parser("example-face", help=f"make the demo mod '{FACE_EXAMPLE_NAME}' ({EXAMPLE_ENGLISH}'s "
                                        "standing portrait tinted blue)")
    p = sub.add_parser("map", help="add map package(s) to a mod (maps/<MAP>/)")
    p.add_argument("name")
    p.add_argument("maps", nargs="+", help="map names, e.g. A007 (python tools/maps/maps.py list)")
    sub.add_parser("example-castle", help=f"make the demo mod '{CASTLE_EXAMPLE_NAME}' (one dish: Strength "
                                          f"+{CASTLE_EXAMPLE_DELTA})")
    p = sub.add_parser("castle", help="add a castle file's spreadsheets to a mod (castle/<FILE>/)")
    p.add_argument("name")
    p.add_argument("file", help="castle file name without folder and extension, e.g. DiningData, AcceShop")
    p.add_argument("--sheets", help="comma-separated sheet keys (default: every sheet of the file)")
    p = sub.add_parser("face", help="add a character's portrait folder to a mod (faces/<folder>/)")
    p.add_argument("name")
    p.add_argument("query", help="FSID, name label, key or package (python tools/assets/portrait.py list)")
    p.add_argument("--folder", help="folder name under faces/ (default: the query)")
    p.add_argument("--extras", action="store_true", help="also hair and accessory layers")
    sub.add_parser("list", help="the mods, in build order")
    for c in ("enable", "disable"):
        sub.add_parser(c, help=f"{c} a mod").add_argument("name")
    p = sub.add_parser("build", help="merge the enabled mods and stage the changed files")
    p.add_argument("--allow-odd-growth", action="store_true", help="accept obfuscated growth rates that "
                                                                   "are not multiples of 5")
    p = sub.add_parser("install", help="build, then copy into Zakuro's mod folder")
    p.add_argument("--no-build", action="store_true", help="install the staged files as they are")
    p.add_argument("--allow-odd-growth", action="store_true")
    p = sub.add_parser("uninstall", help="remove what install placed (also undoes an interrupted install)")
    p.add_argument("--restore-backups", action="store_true",
                   help="put your previous files back even where an installed file was changed since; "
                        f"the changed file is moved to {CHANGED} (not deleted)")
    sub.add_parser("recover", help="the same as uninstall --restore-backups")
    sub.add_parser("status", help="what is enabled, staged and installed")
    sub.add_parser("selftest", help="offline checks in a temporary folder")
    a = ap.parse_args(argv)
    ctx = Ctx(mods_dir=a.mods_dir, stage_dir=a.stage_dir, zakuro_dir=a.zakuro_dir)
    try:
        if a.cmd == "new":
            tables = [t.strip() for t in a.tables.split(",") if t.strip()] if a.tables else None
            text = [t.strip() for t in a.text.split(",") if t.strip()] if a.text else None
            m = new_mod(ctx, a.name, a.description, tables, text=text)
            ctx.say(f"made {os.path.relpath(m.dir, ROOT)} ({len(m.tables())} table(s), {len(m.texts())} text "
                    f"file(s), order {m.order}); edit the files in {os.path.relpath(m.dir, ROOT)} (or put whole "
                    f"replacement files under {ASSET_DIR}/), then: python tools/mods/mods.py install")
            why = tables_status()
            if why and tables is None and not text:
                ctx.say(f"note: no spreadsheets were copied because table mods are off ({why})")
        elif a.cmd == "text":
            m = find_mod(ctx, a.name)
            for rel in a.archives:
                path = add_text(ctx, m, rel)
                ctx.say(f"wrote {os.path.relpath(path, ROOT)} (the whole archive; you may delete the labels "
                        "you do not change, keep the two header lines)")
        elif a.cmd == "archives":
            return TX.main(["archives", "--romfs", ctx.romfs])
        elif a.cmd == "example":
            m, what = make_example(ctx)
            ctx.say(f"made {os.path.relpath(m.dir, ROOT)}: {what}; next: python tools/mods/mods.py install")
        elif a.cmd == "example-text":
            m, what = make_text_example(ctx)
            ctx.say(f"made {os.path.relpath(m.dir, ROOT)}: {what}; next: python tools/mods/mods.py install")
        elif a.cmd == "example-item":
            m, what = make_item_example(ctx)
            ctx.say(f"made {os.path.relpath(m.dir, ROOT)}: {what}; next: python tools/mods/mods.py install")
        elif a.cmd == "example-map":
            m, what = make_map_example(ctx)
            ctx.say(f"made {os.path.relpath(m.dir, ROOT)}: {what}; next: python tools/mods/mods.py install")
        elif a.cmd == "example-face":
            m, what = make_face_example(ctx)
            ctx.say(f"made {os.path.relpath(m.dir, ROOT)}: {what}; next: python tools/mods/mods.py install")
        elif a.cmd == "example-castle":
            m, what = make_castle_example(ctx)
            ctx.say(f"made {os.path.relpath(m.dir, ROOT)}: {what}; next: python tools/mods/mods.py install")
        elif a.cmd == "castle":
            m = find_or_new_mod(ctx, a.name)
            keys = [k.strip() for k in a.sheets.split(",") if k.strip()] if a.sheets else None
            d = add_castle(ctx, m, a.file, keys)
            ctx.say(f"wrote {os.path.relpath(d, ROOT)} (edit the cells; rows can be added only where "
                    "docs/CASTLE.md says so)")
        elif a.cmd == "map":
            m = find_or_new_mod(ctx, a.name)
            for n in a.maps:
                d = add_map(ctx, m, n)
                ctx.say(f"wrote {os.path.relpath(d, ROOT)} (edit units.csv / terrain.csv; preview.png shows the "
                        "map; rules in docs/MAPS.md)")
        elif a.cmd == "face":
            recs = face_records(ctx, a.query)
            m = find_or_new_mod(ctx, a.name)
            folder = re.sub(r"[^\w.\-]", "_", a.folder or a.query)
            srcs = MF.portrait().sources_for(recs, extras=a.extras)
            d = add_face(ctx, m, folder, recs, srcs)
            ctx.say(f"wrote {os.path.relpath(d, ROOT)} ({len(recs)} portrait record(s), {len(srcs)} file(s)); "
                    "edit the PNGs, keep their size (or set \"allow_face_resize\": true in mod.json)")
        elif a.cmd == "list":
            return cmd_list(ctx)
        elif a.cmd in ("enable", "disable"):
            m = find_mod(ctx, a.name)
            m.meta["enabled"] = a.cmd == "enable"
            m.save()
            ctx.say(f"{m.name}: {a.cmd}d. Run python tools/mods/mods.py install to apply it to the game.")
        elif a.cmd == "build":
            return print_build(ctx, build(ctx, a.allow_odd_growth), True)
        elif a.cmd == "install":
            if a.no_build:
                st = read_staged(ctx)
                if st and st.get("fingerprint") != fingerprint(ctx):
                    raise ModError("the staged build is out of date (mods changed since); run without --no-build")
            elif print_build(ctx, build(ctx, a.allow_odd_growth), True):
                ctx.say("install cancelled: the build failed; nothing in Zakuro's folder was touched")
                return 1
            for line in install(ctx):
                ctx.say(" ", line)
            ctx.say(f"install OK -> {ctx.title_dir()}. Start (or restart) {GAME_NAME} in Zakuro; "
                    "no recompile is needed for data mods.")
        elif a.cmd in ("uninstall", "recover"):
            ok, msgs = uninstall(ctx, restore_backups=a.cmd == "recover" or a.restore_backups)
            for line in msgs:
                ctx.say(" ", line)
            ctx.say("uninstall OK" if ok else "uninstall INCOMPLETE: some files were left in place (see above)")
            return 0 if ok else 1
        elif a.cmd == "status":
            return cmd_status(ctx)
        elif a.cmd == "selftest":
            st = _load(f"{GAME.key}_mods_selftest", os.path.join(HERE, "selftest.py"))
            return st.run(sys.modules[__name__])
    except ModError as e:
        print(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
