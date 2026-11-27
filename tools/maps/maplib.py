"""Map editing for Fire Emblem Fates: unit placement (Dispos) and terrain grids (Terrain).

Standard library only. Builds on the typed table layouts (config/tables/DisposFaction,
DisposUnit, TerrainHeader, TerrainTile, TerrainGrid) and the table tools
(tools/tables/tablelib.py, tools/tables/build.py), which are imported, not changed.

One "map package" per chapter file, written under build/maps/<NAME>/ (gitignored: it
holds game values):

    units.csv     one row per placed unit (every group, every difficulty): group, slot,
                  side, PID, class, level, position, items, skills, AI. Columns `name` and
                  `class_name` are the English names, for reading only.
    terrain.csv   the tile grid: one row per map row (y), one column per x; each cell is
                  a tile number of tiles.csv (only in the package that owns the terrain)
    tiles.csv     the tile types of this map (TerrainTile rows: defence, avoid, ...)
    map.csv       map size, playable area, map model (for reading; sizes cannot change)
    preview.png   our own picture: one colour per tile type, unit markers, coordinates
    about.txt     what the files are and how to rebuild

Code facts behind every rule here are in docs/MAPS.md (addresses from
config/functions.csv). The ones the checks depend on:

  * map::Dispos::Load 0039ED9C keeps the whole file in memory and reads it in place;
    CreateProcess 0039DB78 finds a group by name (list ends at a null name);
    Calculate 0039EF34 walks `unit_count` units from `first_unit` (no fixed array).
  * map::Dispos::Data::IsEnable 005278DC: a unit is used on difficulty d (GameUserData
    +0x2D: 0 normal, 1 hard, 2 lunatic) only when flags bit 8+d is set; its position must
    lie in the playable area [play_min, play_end) unless flags bit 15 (0x8000) is set
    (then anywhere on the map); its start position must lie on the map.
  * map::Image::Update 0038F96C copies the grid's six sizes into bytes and the 32x32
    tile bytes (index x | y << 5): maps are at most 32 x 32.
  * Dispos::Data::GetUnit 0039E43C creates no unit once its army (Force) holds 50 units,
    and takes units from the free pool (Force 9); UnitPool::Initialize 004F5ABC makes
    250 units in all.
"""
from __future__ import annotations

import csv
import io
import os
import re
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "tables"))
sys.path.insert(0, os.path.join(ROOT, "tools", "assets"))
import tablelib as T  # noqa: E402
import build as TB  # noqa: E402  (tools/tables/build.py)

OUTDIR = os.path.join(ROOT, "build", "maps")
REBUILT = os.path.join(OUTDIR, "rebuilt")
DISPOS_TABLES = ["DisposFaction", "DisposUnit"]
TERRAIN_TABLES = ["TerrainHeader", "TerrainTile", "TerrainGrid"]
UNIT_SIZE = 0x8C
GRID = 32                       # map::Image: tile index = x | y << 5
FORCE_LIMIT = 50                # Dispos::Data::GetUnit: no new unit once a Force holds 50
POOL_LIMIT = 250                # UnitPool::Initialize: 250 units
DIFFS = ("normal", "hard", "lunatic")
DIFF_BITS = {"normal": 0x100, "hard": 0x200, "lunatic": 0x400}   # IsEnable
FLAG_ANYWHERE = 0x8000          # IsEnable: whole map instead of the playable area
FLAG_PAIRED = 0x10000           # Calculate: the next unit of the group rides with this one
SIDES = {0: "player", 1: "enemy", 2: "ally"}
SIDE_NUM = {v: k for k, v in SIDES.items()}
READONLY_COLS = ("name", "class_name")
RENAME = {"pos.x": "x", "pos.y": "y", "pos_start.x": "start_x", "pos_start.y": "start_y",
          "team": "side"}


class MapError(ValueError):
    """An edit the tool refuses; the message says which file, row and column."""


# ------------------------------------------------------------------ files and names
_REG = None


def reg():
    global _REG
    if _REG is None:
        _REG = T.registry()
    return _REG


def stem(rel: str) -> str:
    b = os.path.basename(rel)
    return b[:-len(".bin.lz")] if b.endswith(".bin.lz") else os.path.splitext(b)[0]


def dispos_files() -> list[str]:
    return reg()["DisposUnit"].files()


def terrain_files() -> list[str]:
    return reg()["TerrainGrid"].files()


def packages() -> dict[str, dict]:
    """NAME -> {"dispos": rel|None, "terrain": rel|None (owned), "terrain_ref": rel|None
    (the terrain the units stand on)}. Dispos names end in E (encounter maps: Player +
    MobNN groups, Scripts/Encount.cmb) or V (versus maps) for variants of a chapter map;
    those use the chapter's terrain but do not own it."""
    terr = {stem(r): r for r in terrain_files()}
    out: dict[str, dict] = {}
    for rel in dispos_files():
        n = stem(rel)
        if n in out:
            raise MapError(f"two Dispos files are both called {n}: {out[n]['dispos']} and {rel}")
        ref = terr.get(n) or (terr.get(n[:-1]) if n[-1:] in ("E", "V") else None)
        out[n] = {"dispos": rel, "terrain": terr.get(n), "terrain_ref": ref}
    for n, rel in terr.items():
        if n not in out:
            out[n] = {"dispos": None, "terrain": rel, "terrain_ref": rel}
    return dict(sorted(out.items()))


# ------------------------------------------------------------------ CSV helpers
def write_csv(path: str, head: list[str], rows: list[list[str]]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(head)
        w.writerows(rows)
    os.replace(tmp, path)


def read_csv(path: str) -> tuple[list[str], list[list[str]]]:
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise MapError(f"{path}: not UTF-8. In Excel use Save As > 'CSV UTF-8 (Comma delimited)'") from None
    sample = text[:4096]
    delim = ";" if sample.count(";") > sample.count(",") else ("\t" if sample.count("\t") > sample.count(",") else ",")
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    if not rows:
        raise MapError(f"{path}: empty file")
    return [h.strip() for h in rows[0]], rows[1:]


def write_bytes(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


# ------------------------------------------------------------------ game text (names)
_TEXT: dict[str, str] | None = None


def text_names() -> dict[str, str]:
    """MPID_/MJID_/MIID_/MTID_ label -> English text (m/@E/GameData.bin.lz), {} if absent."""
    global _TEXT
    if _TEXT is None:
        _TEXT = {}
        p = os.path.join(T.ROMFS, "m", "@E", "GameData.bin.lz")
        if os.path.isfile(p):
            try:
                import msg
                _name, entries, _b = msg.parse(msg.load(p))
                first = {}
                for lab, val, alias in entries:
                    first[lab] = first.get(val, "") if alias else val
                _TEXT = {k.decode("cp932", "replace"): v for k, v in first.items() if isinstance(v, str)}
            except Exception:       # names are a convenience only
                _TEXT = {}
    return _TEXT


# ------------------------------------------------------------------ game tables
class World:
    """The tables the checks need: people (resident + per-chapter), classes, items,
    skills, movement costs, plus rows a mod adds or changes (extra_dir: a folder with
    Item.csv / Job.csv / Skill.csv in the tables' own format, e.g. a mod's tables/)."""

    def __init__(self, extra_dir: str | None = None):
        r = reg()
        self.persons: dict[str, dict] = {}
        h, rows = TB.dump_rows(r, "Person")
        for row in rows:
            d = dict(zip(h, row))
            self.persons[d["label"]] = d
        self.chapter_people: dict[str, dict[str, dict]] = {}
        h, rows = TB.dump_rows(r, "PersonChapter")
        for row in rows:
            d = dict(zip(h, row))
            self.chapter_people.setdefault(d["file"], {})[d["label"]] = d
        self.jobs: dict[str, dict] = {}
        h, rows = TB.dump_rows(r, "Job")
        for row in rows:
            d = dict(zip(h, row))
            self.jobs[d["label"]] = d
        self.items = {row[1] for row in TB.dump_rows(r, "Item")[1]}
        self.skills = {row[1] for row in TB.dump_rows(r, "Skill")[1]}
        self.cost = [[int(x) for x in row[2:]] for row in TB.dump_rows(r, "TerrainCost")[1]]
        self.extra_note = ""
        if extra_dir:
            self.add_extra(extra_dir)

    def add_extra(self, d: str) -> None:
        added = []
        for name, store in (("Item", None), ("Job", self.jobs), ("Skill", None)):
            p = os.path.join(d, f"{name}.csv")
            if not os.path.isfile(p):
                continue
            h, rows = read_csv(p)
            if "label" not in h:
                continue
            li = h.index("label")
            for row in rows:
                lab = row[li].strip() if li < len(row) else ""
                if not lab:
                    continue
                if name == "Item":
                    if lab not in self.items:
                        added.append(lab)
                    self.items.add(lab)
                elif name == "Skill":
                    if lab not in self.skills:
                        added.append(lab)
                    self.skills.add(lab)
                else:
                    if lab not in store:
                        added.append(lab)
                    base = dict(store.get(lab, {}))
                    base.update({k: v for k, v in zip(h, row) if v.strip() != ""})
                    store[lab] = base
        self.extra_note = f"{len(added)} new ID(s) from {d}" if added else ""

    def person_file(self, dispos_rel: str) -> str | None:
        """The per-chapter Person file the game loads with this map: Person::Load uses the
        route folder first, then the shared folder (docs/ROUTES.md step 3). E/V variants
        use their chapter's file."""
        n = stem(dispos_rel)
        cands = [n] + ([n[:-1]] if n[-1:] in ("E", "V") else [])
        sub = os.path.basename(os.path.dirname(dispos_rel))
        for c in cands:
            for folder in ([f"GameData/Person/{sub}"] if sub in ("A", "B", "C") else []) + ["GameData/Person"]:
                rel = f"{folder}/{c}.bin.lz"
                if rel in self.chapter_people:
                    return rel
        return None

    def person(self, pid: str, dispos_rel: str) -> dict | None:
        pf = self.person_file(dispos_rel)
        if pf and pid in self.chapter_people.get(pf, {}):
            return self.chapter_people[pf][pid]
        return self.persons.get(pid)

    def person_anywhere(self, pid: str) -> bool:
        return pid in self.persons or any(pid in m for m in self.chapter_people.values())

    def move_class(self, jid: str) -> int | None:
        j = self.jobs.get(jid)
        if not j:
            return None
        try:
            return int(j.get("move_cost_class", ""), 0)
        except ValueError:
            return None


# ------------------------------------------------------------------ decoding
def _rows_of(name: str, c: T.Container) -> tuple[list[str], list[list[str]]]:
    codec = T.Codec(reg(), name)
    t = reg()[name]
    start, count = T.locate(t, c)
    labels = T.record_labels(t, c, start, count)
    return codec.columns(), [codec.decode(c, i, start + i * t.size, labels[i]) for i in range(count)]


class Dispos:
    """One Dispos file decoded: groups [(name, first unit index, count)] and the
    DisposUnit rows (codec columns) in file order."""

    def __init__(self, rel: str, c: T.Container | None = None):
        self.rel = rel
        self.c = c or T.container(rel)
        self.fhead, self.frows = _rows_of("DisposFaction", self.c)
        self.uhead, self.urows = _rows_of("DisposUnit", self.c)
        fc = {h: i for i, h in enumerate(self.fhead)}
        self.groups = []
        for r in self.frows:
            fu = r[fc["first_unit"]]
            if not fu.startswith("#"):
                raise MapError(f"{rel}: group {r[fc['group']]} first_unit {fu} is not a unit record")
            self.groups.append((r[fc["group"]], int(fu[1:]), int(r[fc["unit_count"]])))
        pos = 0
        for g, first, n in self.groups:
            if first != pos or n <= 0:
                raise MapError(f"{rel}: groups are not contiguous and non-empty (group {g})")
            pos += n
        if pos != len(self.urows):
            raise MapError(f"{rel}: groups cover {pos} units, the file has {len(self.urows)}")


def unit_columns() -> list[str]:
    """units.csv columns: group, slot, then the DisposUnit fields in layout order with
    readable names (side for team, x/y for pos, start_x/start_y for pos_start), the
    flags split into normal/hard/lunatic + other_flags, and two read-only name columns."""
    codec = T.Codec(reg(), "DisposUnit")
    out = ["group", "slot"]
    for col in codec.columns()[3:]:
        if col == "flags":
            out += list(DIFFS) + ["other_flags"]
        elif col == "pid":
            out += ["pid", "name"]
        elif col == "jid":
            out += ["jid", "class_name"]
        else:
            out.append(RENAME.get(col, col))
    return out


def _text_of(label: str) -> str:
    return text_names().get(label, "") if label else ""


def unit_rows(d: Dispos, world: World | None = None) -> list[list[str]]:
    """The units.csv rows of a Dispos file."""
    uc = {h: i for i, h in enumerate(d.uhead)}
    cols = unit_columns()
    out = []
    k = 0
    for g, first, n in d.groups:
        for slot in range(n):
            r = d.urows[first + slot]
            cell = {}
            for h, i in uc.items():
                if h in ("file", "index", "label"):
                    continue
                cell[RENAME.get(h, h)] = r[i]
            fl = int(cell.pop("flags"), 0)
            for dname in DIFFS:
                cell[dname] = "1" if fl & DIFF_BITS[dname] else "0"
            cell["other_flags"] = f"0x{fl & ~0x700:X}"
            cell["side"] = SIDES.get(int(cell["side"]), cell["side"])
            cell["group"], cell["slot"] = g, str(slot)
            name = cls = ""
            if world is not None:
                p = world.person(cell["pid"], d.rel)
                if p:
                    name = _text_of(p.get("mpid_name", ""))
                jid = cell["jid"] or (p.get("job", "") if p else "")
                j = world.jobs.get(jid)
                if j:
                    cls = _text_of(j.get("mjid_name", ""))
            cell["name"], cell["class_name"] = name, cls
            out.append([cell.get(h, "") for h in cols])
            k += 1
    return out


class Terrain:
    def __init__(self, rel: str, c: T.Container | None = None):
        self.rel = rel
        self.c = c or T.container(rel)
        self.hhead, self.hrows = _rows_of("TerrainHeader", self.c)
        self.thead, self.trows = _rows_of("TerrainTile", self.c)
        self.ghead, self.grows = _rows_of("TerrainGrid", self.c)
        g = dict(zip(self.ghead, self.grows[0]))
        self.width, self.height = int(g["map_width"]), int(g["map_height"])
        self.play = (int(g["play_x_min"]), int(g["play_y_min"]), int(g["play_x_end"]), int(g["play_y_end"]))
        self.tiles = bytearray(bytes.fromhex(g["tiles"]))
        h = dict(zip(self.hhead, self.hrows[0]))
        self.model = h.get("map_model", "")

    def tile(self, x: int, y: int) -> int:
        return self.tiles[x | y << 5]

    def columns_of_tiles(self) -> list[int]:
        tc = self.thead.index("move_cost_column")
        return [int(r[tc]) for r in self.trows]

    def grid_rows(self) -> tuple[list[str], list[list[str]]]:
        head = ["y\\x"] + [str(x) for x in range(self.width)]
        return head, [[str(y)] + [str(self.tile(x, y)) for x in range(self.width)] for y in range(self.height)]

    def map_rows(self) -> list[list[str]]:
        return [["map_width", str(self.width)], ["map_height", str(self.height)],
                ["play_x_min", str(self.play[0])], ["play_y_min", str(self.play[1])],
                ["play_x_end", str(self.play[2])], ["play_y_end", str(self.play[3])],
                ["tile_count", str(len(self.trows))], ["map_model", self.model]]


def tile_rows(t: Terrain) -> tuple[list[str], list[list[str]]]:
    """tiles.csv: the TerrainTile rows without the file column, plus a read-only English
    name column."""
    head = [h for h in t.thead if h != "file"] + ["name"]
    mi = t.thead.index("mtid_name")
    rows = [[c for h, c in zip(t.thead, r) if h != "file"] + [_text_of(r[mi])] for r in t.trows]
    return head, rows


# ------------------------------------------------------------------ PNG preview
_FONT = {  # 3x5 digits, our own
    "0": "111101101101111", "1": "010110010010111", "2": "111001111100111",
    "3": "111001111001111", "4": "101101111001001", "5": "111100111001111",
    "6": "111100111101111", "7": "111001010010010", "8": "111101111101111",
    "9": "111101111001111",
}
TEAM_RGB = {0: (40, 90, 230), 1: (220, 40, 40), 2: (30, 170, 60)}


def _palette(col: int, impass: bool) -> tuple[int, int, int]:
    base = [(150, 200, 110), (60, 130, 60), (170, 150, 100), (120, 120, 120),
            (200, 190, 140), (90, 160, 210), (40, 90, 170), (210, 210, 200),
            (150, 110, 70), (190, 120, 160), (230, 200, 90), (110, 170, 150),
            (180, 180, 220), (140, 90, 140), (90, 90, 60), (200, 140, 90)][col % 16]
    return tuple(v // 3 for v in base) if impass else base


def _png(w: int, h: int, px: bytearray) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + bytes(px[y * w * 3:(y + 1) * w * 3]) for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def preview_png(t: Terrain, units: list[dict], world: World | None = None, cell: int = 16) -> bytes:
    """One square per tile (colour = movement-cost column; dark = no class can walk it;
    the playable area's edge is outlined), unit markers (blue player, red enemy, green
    ally; hollow = reinforcement groups),
    coordinates on the top and left edges. Our own drawing: no game art."""
    margin = 14
    W, H = margin + t.width * cell + 1, margin + t.height * cell + 1
    px = bytearray(b"\xff" * (W * H * 3))

    def put(x, y, rgb):
        if 0 <= x < W and 0 <= y < H:
            o = (y * W + x) * 3
            px[o:o + 3] = bytes(rgb)

    def rect(x0, y0, x1, y1, rgb, fill=True):
        for y in range(y0, y1):
            for x in range(x0, x1):
                if fill or y in (y0, y1 - 1) or x in (x0, x1 - 1):
                    put(x, y, rgb)

    def text(x, y, s, rgb=(0, 0, 0)):
        for k, ch in enumerate(s):
            bits = _FONT.get(ch)
            if bits:
                for i, b in enumerate(bits):
                    if b == "1":
                        put(x + k * 4 + i % 3, y + i // 3, rgb)

    cols = t.columns_of_tiles()
    costs = world.cost if world else None
    for y in range(t.height):
        for x in range(t.width):
            n = t.tile(x, y)
            col = cols[n] if n < len(cols) else 0
            imp = bool(costs) and all(row[col] < 0 for row in costs[1:]) if costs and col < 16 else False
            x0, y0 = margin + x * cell, margin + y * cell
            rect(x0, y0, x0 + cell, y0 + cell, _palette(col, imp))
            rect(x0, y0, x0 + cell + 1, y0 + cell + 1, (60, 60, 60), fill=False)
    px0, py0, px1, py1 = t.play
    rect(margin + px0 * cell, margin + py0 * cell, margin + px1 * cell + 1, margin + py1 * cell + 1,
         (255, 255, 255), fill=False)
    for x in range(t.width):
        text(margin + x * cell + 2, 4, str(x))
    for y in range(t.height):
        s = str(y)
        text(1 if len(s) > 1 else 5, margin + y * cell + 5, s)
    for u in units:
        try:
            x, y, side = int(u["x"]), int(u["y"]), u["side"]
        except (KeyError, ValueError):
            continue
        team = SIDE_NUM.get(side, int(side) if str(side).isdigit() else 1)
        rgb = TEAM_RGB.get(team, (0, 0, 0))
        x0, y0 = margin + x * cell + 4, margin + y * cell + 4
        rect(x0, y0, x0 + cell - 7, y0 + cell - 7, rgb, fill=u.get("first_group", False))
        rect(x0 + 1, y0 + 1, x0 + cell - 8, y0 + cell - 8, rgb, fill=u.get("first_group", False))
    return _png(W, H, px)


# ------------------------------------------------------------------ export
ABOUT = """Map package {name} (made by tools/maps/maps.py; your own game data, never share it)

units.csv    one row per placed unit. Edit cells and save as CSV UTF-8.
             group/slot say which unit a row is: do not change them for existing rows.
             side: player / enemy / ally. normal/hard/lunatic: 1 = the unit is on the map
             in that difficulty, 0 = not (set all three to 0 to take a unit off the map:
             rows are never deleted). x, y: position (0,0 = top left). start_x/start_y:
             where the unit appears before it walks to x, y (usually the same).
             jid empty = the character's own class; level 0 = the character's own level.
             name and class_name are for reading only.
             To add a unit: copy a row of the same group to the end and set its slot to
             "new" (allowed where docs/MAPS.md says so; the build tells you if not).
terrain.csv  the tile grid, one row per y, one column per x; numbers are tile numbers
             from tiles.csv (index column).{terrain_note}
tiles.csv    this map's tile types (defence, avoid, heal, movement-cost column).
map.csv      size and playable area (cannot be changed).
preview.png  the map as coloured squares with unit markers (blue player, red enemy,
             green ally; hollow = reinforcement groups).

Rebuild:  python tools/maps/maps.py build {name}
Check:    python tools/maps/maps.py check {name}
"""


def export(name: str, out_root: str = OUTDIR, world: World | None = None, png: bool = True) -> str:
    pk = packages().get(name)
    if pk is None:
        raise MapError(f"no map called {name} (python tools/maps/maps.py list)")
    world = world or World()
    d = os.path.join(out_root, name)
    os.makedirs(d, exist_ok=True)
    units = []
    if pk["dispos"]:
        disp = Dispos(pk["dispos"])
        rows = unit_rows(disp, world)
        write_csv(os.path.join(d, "units.csv"), unit_columns(), rows)
        cols = unit_columns()
        units = [dict(zip(cols, r), first_group=not r[0].startswith("Reinforce")) for r in rows]
    note = ""
    if pk["terrain"]:
        t = Terrain(pk["terrain"])
        h, rows = t.grid_rows()
        write_csv(os.path.join(d, "terrain.csv"), h, rows)
        h, rows = tile_rows(t)
        write_csv(os.path.join(d, "tiles.csv"), h, rows)
        write_csv(os.path.join(d, "map.csv"), ["key", "value"], t.map_rows())
    elif pk["terrain_ref"]:
        note = (f"\n             (this map uses the terrain of {stem(pk['terrain_ref'])}: edit it in that "
                "package)")
    else:
        note = "\n             (no terrain file has this map's name: positions are not checked)"
    ref = pk["terrain"] or pk["terrain_ref"]
    if png and ref:
        t = Terrain(ref)
        write_bytes(os.path.join(d, "preview.png"), preview_png(t, units, world))
    with open(os.path.join(d, "about.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(ABOUT.format(name=name, terrain_note=note))
    return d


# ------------------------------------------------------------------ reading edits back
def _yes(s: str, where: str) -> bool:
    v = s.strip().lower()
    if v in ("1", "yes", "y", "x", "true"):
        return True
    if v in ("0", "no", "n", "", "false"):
        return False
    raise MapError(f"{where}: {s!r} must be 1 or 0")


def _int(s: str, where: str, lo: int | None = None, hi: int | None = None) -> int:
    t = s.strip()
    if re.fullmatch(r"-?\d+\.0+", t):
        t = t.split(".")[0]
    try:
        v = int(t, 0)
    except ValueError:
        raise MapError(f"{where}: {s!r} is not a whole number") from None
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise MapError(f"{where}: {v} is outside {lo}..{hi}")
    return v


class UnitEdit:
    """units.csv read back: per group the ordered list of codec cells (DisposUnit columns
    after file/index/label) and which rows are new or changed."""

    def __init__(self, d: Dispos, head: list[str], rows: list[list[str]], src: str = "units.csv"):
        cols = unit_columns()
        missing = [c for c in cols if c not in head and c not in READONLY_COLS]
        if missing:
            raise MapError(f"{src}: missing column(s) {', '.join(missing)} (re-export the map)")
        hi = {h: i for i, h in enumerate(head)}
        codec_cols = T.Codec(reg(), "DisposUnit").columns()[3:]
        vanilla = unit_rows(d)
        vcells = {(r[0], r[1]): r for r in vanilla}
        gnames = [g for g, _f, _n in d.groups]
        self.by_group: dict[str, list[tuple[int, list[str]]]] = {g: [] for g in gnames}
        self.new: list[tuple[str, int]] = []
        self.changed: dict[tuple[str, int], set[str]] = {}
        seen = set()
        for k, r in enumerate(rows):
            line = k + 2
            r = list(r) + [""] * (len(head) - len(r))
            cell = {h: r[i].strip() for h, i in hi.items()}
            g = cell["group"]
            where = f"{src} line {line}"
            if g not in self.by_group:
                raise MapError(f"{where}: group {g!r} is not in this map (its groups: {', '.join(gnames)}); "
                               "new groups are refused: the chapter script calls groups by name")
            slot_s = cell["slot"].lower()
            gi = gnames.index(g)
            n0 = d.groups[gi][2]
            if slot_s in ("new", "", "+"):
                slot = None
            else:
                slot = _int(cell["slot"], f"{where} slot", 0)
            vals = []
            for c in codec_cols:
                if c == "flags":
                    fl = _int(cell["other_flags"] or "0", f"{where} other_flags", 0, 0xFFFFFFFF)
                    if fl & 0x700:
                        raise MapError(f"{where} other_flags: bits 0x700 are the difficulty columns; "
                                       "use normal/hard/lunatic")
                    for dn in DIFFS:
                        if _yes(cell[dn], f"{where} {dn}"):
                            fl |= DIFF_BITS[dn]
                    vals.append(str(fl))
                elif c == "team":
                    s = cell["side"].lower()
                    if s in SIDE_NUM:
                        vals.append(str(SIDE_NUM[s]))
                    else:
                        v = _int(s, f"{where} side", 0, 2)
                        vals.append(str(v))
                else:
                    vals.append(cell[RENAME.get(c, c)])
            if slot is not None and slot < n0:
                if (g, slot) in seen:
                    raise MapError(f"{where}: group {g} slot {slot} appears twice")
                seen.add((g, slot))
                vr = vcells[(g, str(slot))]
                vdict = dict(zip(cols, vr))
                diff = {c for c in cols if c not in READONLY_COLS and c not in ("group", "slot")
                        and _norm(cell.get(c, ""), c) != _norm(vdict.get(c, ""), c)}
                if diff:
                    self.changed[(g, slot)] = diff
            else:
                if slot is not None and slot != n0 + sum(1 for s, _ in self.by_group[g] if s >= n0):
                    raise MapError(f"{where}: group {g} has slots 0..{n0 - 1}; a new unit is slot "
                                   f"{n0 + sum(1 for s, _ in self.by_group[g] if s >= n0)} or 'new', not {slot}")
                slot = n0 + sum(1 for s, _ in self.by_group[g] if s >= n0)
                self.new.append((g, slot))
            self.by_group[g].append((slot, vals))
        for gi, (g, _f, n0) in enumerate(d.groups):
            have = {s for s, _ in self.by_group[g] if s < n0}
            lost = sorted(set(range(n0)) - have)
            if lost:
                raise MapError(f"{src}: group {g} slot(s) {', '.join(map(str, lost[:8]))} are missing: rows are never "
                               "deleted (to take a unit off the map set normal, hard and lunatic to 0)")
            self.by_group[g].sort(key=lambda sv: sv[0])
        self.d = d
        self.codec_cols = codec_cols

    def unit_cells(self) -> list[tuple[str, int, list[str]]]:
        return [(g, s, v) for g, _f, _n in self.d.groups for s, v in self.by_group[g]]


def _norm(s: str, col: str) -> str:
    s = (s or "").strip()
    if col in DIFFS:
        return "1" if s.lower() in ("1", "yes", "y", "x", "true") else "0"
    if col == "side":
        return str(SIDE_NUM.get(s.lower(), s))
    if re.fullmatch(r"-?(0x[0-9A-Fa-f]+|\d+)(\.0+)?", s):
        try:
            return str(int(s.split(".")[0], 0))
        except ValueError:
            return s
    return s


# ------------------------------------------------------------------ validation
class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def ok(self) -> bool:
        return not self.errors


def validate_units(d: Dispos, ue: UnitEdit, terr: Terrain | None, world: World, rep: Report,
                   src: str = "units.csv", lenient: bool = False) -> None:
    """Checks every unit; strict (an error) for new and changed units, a note for game
    rows nobody changed (the game's own data is not second-guessed: some of its units
    stand on doors or walls that open later, or wait off the map at 255,255).
    lenient: a moved unit on a tile its class cannot walk on is a warning, not an error
    (for doors and walls that a map event opens)."""
    col = {c: i for i, c in enumerate(ue.codec_cols)}
    cols_of_tiles = terr.columns_of_tiles() if terr else []
    tile_attr = [int(r[terr.thead.index("attributes")], 0) for r in terr.trows] if terr else []
    team_count: dict[tuple[str, int, str], int] = {}
    file_team: dict[tuple[int, str], int] = {}
    touched_g: set = set()
    touched_f: set = set()
    for g, _f, _n in d.groups:
        rows = ue.by_group[g]
        for k, (slot, v) in enumerate(rows):
            key = (g, slot)
            is_new = key in ue.new
            changed = ue.changed.get(key, set())
            strict = is_new or bool(changed)
            where = f"{src}: {g} slot {slot}"
            # errors for new/changed rows; untouched game rows only get a note
            bad = rep.errors.append if strict else rep.notes.append
            soft_id = rep.warnings.append if strict else rep.notes.append
            fl = int(v[col["flags"]])
            team = int(v[col["team"]])
            for dn in DIFFS:
                if fl & DIFF_BITS[dn]:
                    team_count[(g, team, dn)] = team_count.get((g, team, dn), 0) + 1
                    file_team[(team, dn)] = file_team.get((team, dn), 0) + 1
                    if strict:   # an edited or new row counts toward this army (review 2026-11-11b #1)
                        touched_g.add((g, team, dn))
                        touched_f.add((team, dn))
            partner = k > 0 and int(rows[k - 1][1][col["flags"]]) & FLAG_PAIRED
            # numbers that must fit their bytes
            for c, lo, hi in (("level", 0, 255), ("pos.x", 0, 255), ("pos.y", 0, 255),
                              ("pos_start.x", 0, 255), ("pos_start.y", 0, 255), ("sortie_flag", 0, 255)):
                _int(v[col[c]], f"{where} {RENAME.get(c, c)}", lo, hi)
            for n in range(1, 6):
                _int(v[col[f"item_{n}_flags"]], f"{where} item_{n}_flags", 0, 255)
                for dn in DIFFS:
                    _int(v[col[f"item_{n}_forge.{dn}"]], f"{where} item_{n}_forge.{dn}", -128, 127)
            for c in [c for c in ue.codec_cols if c.startswith("ai_params.")]:
                _int(v[col[c]], f"{where} {c}", 0, 255)
            if int(v[col["sortie_flag"]]) and strict:
                rep.errors.append(f"{where}: sortie_flag must be 0 (the game uses that byte while the map runs)")
            # IDs
            pid, jid = v[col["pid"]], v[col["jid"]]
            person = world.person(pid, d.rel) if pid else None
            if not pid:
                bad(f"{where}: pid is empty")
            elif person is None:
                if world.person_anywhere(pid):
                    soft_id(f"{where}: {pid} is not in the resident people or in this chapter's Person file "
                            f"({world.person_file(d.rel) or 'none'}), only in another chapter's (the game "
                            "has such units too; check it shows up)")
                else:
                    bad(f"{where}: no character {pid} (Person / per-chapter Person files)")
            if jid and jid not in world.jobs:
                bad(f"{where}: no class {jid} (Job, or a row your mod adds: --tables DIR)")
            for n in range(1, 6):
                iid = v[col[f"item_{n}"]]
                if iid and iid != T.EMPTY_STR and iid not in world.items:
                    bad(f"{where}: item_{n} {iid} is not an item (Item, or a row your mod adds: --tables DIR)")
            for n in range(1, 6):
                se = v[col[f"skill_{n}"]]
                if se and se != T.EMPTY_STR and se not in world.skills:
                    bad(f"{where}: skill_{n} {se} is not a skill")
            # positions (IsEnable)
            x, y = int(v[col["pos.x"]]), int(v[col["pos.y"]])
            sx, sy = int(v[col["pos_start.x"]]), int(v[col["pos_start.y"]])
            if terr is None:
                continue
            if partner:
                continue          # rides with the unit before it; Calculate skips its own checks
            if (x, y, sx, sy) == (255, 255, 255, 255):
                # the game reads positions as signed bytes (ldrsb): 255 = -1, which IsEnable
                # never accepts; the game's own off-map units (support partners) use it
                if strict:
                    rep.warnings.append(f"{where}: position 255,255 = off the map: the map never places this "
                                        "unit by itself (only an event can)")
                continue
            pos_bad = False
            if fl & FLAG_ANYWHERE:
                if not (x < terr.width and y < terr.height):
                    bad(f"{where}: position ({x},{y}) is outside the {terr.width}x{terr.height} map "
                        f"(x 0..{terr.width - 1}, y 0..{terr.height - 1})")
                    pos_bad = True
            else:
                x0, y0, x1, y1 = terr.play
                if not (x0 <= x < x1 and y0 <= y < y1):
                    bad(f"{where}: position ({x},{y}) is outside the playable area of this map "
                        f"(x {x0}..{x1 - 1}, y {y0}..{y1 - 1}); the game would leave this unit out")
                    pos_bad = True
            if not (sx < terr.width and sy < terr.height):
                bad(f"{where}: start position ({sx},{sy}) is outside the {terr.width}x{terr.height} map")
            if pos_bad or x >= GRID or y >= GRID:
                continue
            if not any(fl & b for b in DIFF_BITS.values()):
                continue          # on no difficulty: never placed
            tile = terr.tile(x, y)
            if tile >= len(cols_of_tiles):
                continue
            tcol = cols_of_tiles[tile]
            moved = is_new or bool(changed & {"x", "y", "jid", "pid", "side", "other_flags"})
            soft = rep.errors.append if (moved and not lenient) else (
                rep.warnings.append if strict else rep.notes.append)
            tname = terr.trows[tile][2]
            if team == 0 and fl & 0x7C and not fl & 0x44:
                # a deployment slot: map::Dispos::Calculate 0039EF34 adds it only when the
                # tile's move_cost_column is not 0 and its attributes lack bit 3 (0x8)
                if tcol == 0 or tile_attr[tile] & 8:
                    soft(f"{where}: deployment slot ({x},{y}) is on tile {tile} ({tname}), where the game "
                         "makes no deployment slot (movement-cost column 0 or attribute 0x8)")
                continue
            if re.match(r"Mob\d", g):
                continue          # class picked at random when the map starts (spot::Mob)
            # walkable for the unit's class: TerrainCost[Job.move_cost_class][tile column]
            job = jid or (person.get("job", "") if person else "")
            mc = world.move_class(job) if job else None
            if mc is None or mc >= len(world.cost):
                continue
            cost = world.cost[mc][tcol] if tcol < len(world.cost[mc]) else 0
            if cost < 0:
                soft(f"{where}: ({x},{y}) is tile {tile} ({tname}), which class {job} cannot walk on "
                     f"(movement cost class {mc}, terrain column {tcol})")
    # the 50-unit army limit (Dispos::Data::GetUnit), counted per difficulty. An army over the
    # limit is an error whenever an edited or new row is part of it (turning a difficulty on
    # counts as an edit); untouched game armies only get a note (review 2026-11-11b #1).
    for (g, team, dn), n in sorted(team_count.items()):
        if n > FORCE_LIMIT:
            msg = (f"{src}: group {g} places {n} {SIDES.get(team, team)} units on {dn}; the game creates no "
                   f"unit once an army holds {FORCE_LIMIT} (Dispos::Data::GetUnit 0039E43C)")
            (rep.errors.append if (g, team, dn) in touched_g else rep.notes.append)(msg)
    for (team, dn), n in sorted(file_team.items()):
        if n > FORCE_LIMIT:
            msg = (f"{src}: this map places {n} {SIDES.get(team, team)} units on {dn} over all groups; the game "
                   f"creates no unit once an army holds {FORCE_LIMIT} (Dispos::Data::GetUnit 0039E43C)")
            (rep.errors.append if (team, dn) in touched_f else rep.notes.append)(msg)


def add_refusal(d: Dispos, ue: UnitEdit) -> str | None:
    """None when the new units may be added, else the reason."""
    if not ue.new:
        return None
    if stem(d.rel).endswith("V"):
        return "units cannot be added to versus maps (V files): both sides' placements are matched by the versus code"
    col = {c: i for i, c in enumerate(ue.codec_cols)}
    for g, _s in ue.new:
        if re.match(r"Mob\d", g):
            return (f"units cannot be added to group {g}: Mob groups are filled at random by spot::Mob code "
                    "(CreateDisposUnitMonster) that nobody has read yet")
    for g, _f, n0 in d.groups:
        rows = [v for s, v in ue.by_group[g] if s < n0]
        if any(s >= n0 for s, _ in ue.by_group[g]) and int(rows[-1][col["flags"]]) & FLAG_PAIRED:
            return (f"group {g}: its last unit has the paired flag (0x10000), so a unit added after it "
                    "would become its partner")
    return None


# ------------------------------------------------------------------ rebuilding
def insert_units(c: T.Container, at: int, k: int) -> T.Container:
    """Container c with k zeroed unit records inserted at data offset `at` (the end of a
    group). Every relocation and every non-string pointer at or after `at` moves by
    k * 0x8C; the string pool is rebuilt with the game's rule. Dispos files have no
    labels and no empty groups, so a group's first_unit equal to `at` is always a later
    group's and moves with it."""
    if c.b.labels:
        raise MapError(f"{c.rel}: has labels; unit insertion only handles label-free Dispos files")
    import isbin
    n = k * UNIT_SIZE
    pooled = isbin.pool_pointers(c.b)
    if pooled is None:
        raise MapError(f"{c.rel}: string table is not in the game's pool layout")
    old = c.data
    data = bytearray(old[:at]) + bytearray(n) + bytearray(old[at:])
    relocs = [r + n if r >= at else r for r in c.b.relocs]
    strs, spos = [], []
    for r, nr in zip(c.b.relocs, relocs):
        if r in pooled:
            strs.append(pooled[r])
            spos.append(nr)
        else:
            v = struct.unpack_from("<I", old, r)[0]
            if v > len(old):
                raise MapError(f"{c.rel}: pointer at {r:#x} is neither data nor a pooled string")
            struct.pack_into("<I", data, nr, v + n if v >= at else v)
    tab, _noffs, soffs = isbin.build_pool([], strs)
    se = len(data) + 4 * len(relocs)
    for p, so in zip(spos, soffs):
        struct.pack_into("<I", data, p, se + so)
    nb = isbin.IsBin()
    nb.hdrpad = c.b.hdrpad
    nb.data = bytes(data)
    nb.relocs = relocs
    nb.labels = []
    nb.strtab = tab
    return T.Container.from_dec(c, nb.build())


def build_dispos(d: Dispos, ue: UnitEdit) -> bytes:
    """Stored bytes of the Dispos file from the edited units (new units appended at the
    end of their groups; group first_unit / unit_count follow)."""
    r = reg()
    c = d.c
    added: dict[str, int] = {}
    for g, _s in ue.new:
        added[g] = added.get(g, 0) + 1
    if added:
        # insert from the last group backwards so earlier offsets stay valid
        start, _cnt = T.locate(r["DisposUnit"], c)
        for g, first, n0 in reversed(d.groups):
            if g in added:
                c = insert_units(c, start + (first + n0) * UNIT_SIZE, added[g])
    fc = {h: i for i, h in enumerate(d.fhead)}
    frows, urows = [], []
    pos = 0
    for gi, (g, _first, _n0) in enumerate(d.groups):
        cells = ue.by_group[g]
        fr = list(d.frows[gi])
        fr[fc["first_unit"]] = f"#{pos}"
        fr[fc["unit_count"]] = str(len(cells))
        frows.append(fr)
        for _s, v in cells:
            urows.append([d.rel, str(pos), ""] + v)
            pos += 1
    override = {"DisposFaction": (d.fhead, frows), "DisposUnit": (d.uhead, urows)}
    saved = T._CACHE.get(d.rel)
    T._CACHE[d.rel] = c
    try:
        return TB.build_file(r, d.rel, DISPOS_TABLES, override=override)
    except (T.LayoutError, ValueError, KeyError) as e:
        raise MapError(f"{d.rel}: {e}") from None
    finally:
        if saved is None:
            T._CACHE.pop(d.rel, None)
        else:
            T._CACHE[d.rel] = saved


class TerrainEdit:
    def __init__(self, t: Terrain, grid: tuple[list[str], list[list[str]]] | None,
                 tiles: tuple[list[str], list[list[str]]] | None, mapcsv: tuple | None = None,
                 src: str = ""):
        self.t = t
        self.tiles = bytearray(t.tiles)
        self.changed_cells: list[tuple[int, int, int, int]] = []
        ntiles = len(t.trows)
        if grid is not None:
            head, rows = grid
            if len(rows) != t.height:
                raise MapError(f"{src}terrain.csv: {len(rows)} rows, the map has {t.height} (rows cannot be "
                               "added or removed: the map size is fixed)")
            for y, row in enumerate(rows):
                cells = row[1:]
                if len([c for c in cells if c.strip() != ""]) != t.width:
                    raise MapError(f"{src}terrain.csv line {y + 2}: {len([c for c in cells if c.strip()])} tiles, "
                                   f"the map is {t.width} wide")
                for x in range(t.width):
                    v = _int(cells[x], f"{src}terrain.csv line {y + 2} column x={x}", 0, ntiles - 1) \
                        if True else 0
                    if v != self.tiles[x | y << 5]:
                        self.changed_cells.append((x, y, self.tiles[x | y << 5], v))
                        self.tiles[x | y << 5] = v
        self.trows = [list(r) for r in t.trows]
        if tiles is not None:
            head, rows = tiles
            want = [h for h in t.thead if h != "file"]
            miss = [h for h in want if h not in head]
            if miss:
                raise MapError(f"{src}tiles.csv: missing column(s) {', '.join(miss)} (re-export the map)")
            if len(rows) < ntiles:
                raise MapError(f"{src}tiles.csv: {len(rows)} rows, the map has {ntiles} tile types "
                               "(rows are never deleted)")
            if len(rows) > ntiles:
                raise MapError(f"{src}tiles.csv: {len(rows)} rows, the map has {ntiles}: new tile types are "
                               "refused (the tile count and the change_to links are per map; not reviewed)")
            hi = {h: i for i, h in enumerate(head)}
            for k, row in enumerate(rows):
                row = list(row) + [""] * (len(head) - len(row))
                if row[hi["index"]].strip() != str(k):
                    raise MapError(f"{src}tiles.csv line {k + 2}: index must be {k} (rows stay in order)")
                if row[hi["label"]].strip() != t.trows[k][t.thead.index("label")]:
                    raise MapError(f"{src}tiles.csv line {k + 2}: the tile ID (label) cannot be renamed")
                self.trows[k] = [t.trows[k][0]] + [row[hi[h]].strip() for h in want]
        if mapcsv is not None:
            head, rows = mapcsv
            have = {r[0].strip(): r[1].strip() for r in rows if len(r) >= 2}
            for k, v in t.map_rows():
                if k in have and have[k] != v:
                    raise MapError(f"{src}map.csv: {k} cannot be changed ({v} -> {have[k]}): the map model, camera "
                                   "and the 32x32 grid are fixed per map (docs/MAPS.md)")

    def terrain_view(self) -> Terrain:
        nt = Terrain.__new__(Terrain)
        nt.__dict__.update(self.t.__dict__)
        nt.tiles = self.tiles
        nt.trows = self.trows
        return nt

    def build(self) -> bytes:
        t = self.t
        g = list(t.grows[0])
        g[t.ghead.index("tiles")] = bytes(self.tiles).hex()
        override = {"TerrainHeader": (t.hhead, t.hrows), "TerrainTile": (t.thead, self.trows),
                    "TerrainGrid": (t.ghead, [g])}
        try:
            return TB.build_file(reg(), t.rel, TERRAIN_TABLES, override=override)
        except (T.LayoutError, ValueError, KeyError) as e:
            raise MapError(f"{t.rel}: {e}") from None


def validate_terrain(te: TerrainEdit, world: World, rep: Report, src: str = "") -> None:
    cols = te.terrain_view().columns_of_tiles()
    tc = te.t.thead
    for k, r in enumerate(te.trows):
        d = dict(zip(tc, r))
        try:
            c = int(d["move_cost_column"], 0)
        except ValueError:
            rep.errors.append(f"{src}tiles.csv line {k + 2}: move_cost_column {d['move_cost_column']!r} is not a number")
            continue
        if not 0 <= c < len(world.cost[0]):
            rep.errors.append(f"{src}tiles.csv line {k + 2}: move_cost_column {c} is outside 0..{len(world.cost[0]) - 1} "
                              "(the movement-cost table has that many columns)")
        for fld, lo, hi in (("defense", -128, 127), ("avoid", -128, 127), ("heal", -128, 127),
                            ("minimap_color", 0, 255), ("tile_number", 0, 255)):
            try:
                _int(d[fld], f"{src}tiles.csv line {k + 2} {fld}", lo, hi)
            except MapError as e:
                rep.errors.append(str(e))
        if d.get("tile_number", "").strip() != str(k):
            rep.errors.append(f"{src}tiles.csv line {k + 2}: tile_number must stay {k} (the game reads it as the index)")
        for i in (1, 2, 3):
            v = d.get(f"change_to.{i}", "0").strip()
            try:
                if _int(v, "", 0, 255) >= len(te.trows):
                    rep.errors.append(f"{src}tiles.csv line {k + 2}: change_to.{i} = {v} is not a tile of this map")
            except MapError:
                rep.errors.append(f"{src}tiles.csv line {k + 2}: change_to.{i} {v!r} is not a number")
    del cols


# ------------------------------------------------------------------ packages back to files
def load_terrain_edit(pkg_dir: str, t: Terrain) -> TerrainEdit:
    def opt(name):
        p = os.path.join(pkg_dir, name)
        return read_csv(p) if os.path.isfile(p) else None
    return TerrainEdit(t, opt("terrain.csv"), opt("tiles.csv"), opt("map.csv"),
                       src=os.path.basename(pkg_dir) + "/")


def build_package(name: str, maps_root: str = OUTDIR, world: World | None = None,
                  lenient: bool = False) -> tuple[dict[str, bytes], Report]:
    """{RomFS rel: stored bytes} for the package's Dispos and/or Terrain file, plus the
    check report. Nothing is returned for a file when the report has errors."""
    pk = packages().get(name)
    if pk is None:
        raise MapError(f"no map called {name}")
    world = world or World()
    rep = Report()
    out: dict[str, bytes] = {}
    pdir = os.path.join(maps_root, name)
    if not os.path.isdir(pdir):
        raise MapError(f"{pdir} does not exist: run  python tools/maps/maps.py export {name}  first")
    te = None
    if pk["terrain"]:
        te = load_terrain_edit(pdir, Terrain(pk["terrain"]))
        validate_terrain(te, world, rep, src=f"{name}/")
    tview = None
    if pk["terrain_ref"]:
        if te is not None:
            tview = te.terrain_view()
        else:
            ref_name = stem(pk["terrain_ref"])
            rdir = os.path.join(maps_root, ref_name)
            base = Terrain(pk["terrain_ref"])
            tview = load_terrain_edit(rdir, base).terrain_view() if os.path.isfile(
                os.path.join(rdir, "terrain.csv")) else base
    if pk["dispos"]:
        p = os.path.join(pdir, "units.csv")
        if os.path.isfile(p):
            d = Dispos(pk["dispos"])
            head, rows = read_csv(p)
            ue = UnitEdit(d, head, rows, src=f"{name}/units.csv")
            why = add_refusal(d, ue)
            if why:
                rep.errors.append(f"{name}/units.csv: {len(ue.new)} new unit(s) refused: {why}")
            validate_units(d, ue, tview, world, rep, src=f"{name}/units.csv", lenient=lenient)
            if rep.ok():
                out[pk["dispos"]] = build_dispos(d, ue)
    if te is not None and rep.ok():
        out[pk["terrain"]] = te.build()
    return (out if rep.ok() else {}), rep


def write_rebuilt(files: dict[str, bytes], out_root: str = REBUILT) -> list[str]:
    paths = []
    for rel, data in files.items():
        dst = os.path.join(out_root, rel.replace("/", os.sep))
        write_bytes(dst, data)
        paths.append(dst)
    return paths


# ------------------------------------------------------------------ whole-game round trip
def roundtrip_all(verbose: bool = False) -> tuple[int, int, int, int, list[str]]:
    """Every Dispos and Terrain file: decode -> units.csv / terrain.csv rows (in memory)
    -> read back -> rebuild; returns (dispos same, dispos total, terrain same, terrain
    total, differing files)."""
    bad = []
    ds = dn = ts = tn = 0
    cols = unit_columns()
    for rel in dispos_files():
        d = Dispos(rel)
        rows = unit_rows(d)
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows([cols] + rows)
        back = list(csv.reader(io.StringIO(buf.getvalue())))
        ue = UnitEdit(d, back[0], back[1:])
        out = build_dispos(d, ue)
        dn += 1
        if out == d.c.raw and not ue.new and not ue.changed:
            ds += 1
        else:
            bad.append(rel)
    for rel in terrain_files():
        t = Terrain(rel)
        te = TerrainEdit(t, t.grid_rows(), tile_rows(t), (["key", "value"], t.map_rows()))
        out = te.build()
        tn += 1
        if out == t.c.raw and not te.changed_cells:
            ts += 1
        else:
            bad.append(rel)
        if verbose:
            print(rel, out == t.c.raw)
    return ds, dn, ts, tn, bad
