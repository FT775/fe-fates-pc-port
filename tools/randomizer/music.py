#!/usr/bin/env python3
"""Randomizer track "music" (F-046, round 55; docs/rando/MUSIC.md): each chapter's map theme and, as an option,
the boss and named-unit battle themes, picked from the game's own music tracks. Only what is heard changes.

    plan_music(tables, rng, opts) -> (edits, spoiler_lines)

tables  a MusicTables (load_tables() reads the user's own RomFS; the tests build small made-up ones)
rng     the run seed (text, as given to rando.py) or a random.Random; this track derives its OWN sub-seed from it
        and the track name, then one stream per (purpose, chapter file, cell), so no other track's draws are
        disturbed and a chapter always sounds the same for one seed
opts    {"music": "off" | "maps" | "maps+battles"}; default "off" = NO edits (existing seeds stay byte-identical)

edits   in a fixed order, only cells whose value changes:
        {"table": "MapConfig", "file": "map/config/A005.bin", "cid": "CID_A005", "cell": "player_bgm" | "player_bgm_2",
         "old": "STRM_MAP_E1", "new": "STRM_MAP_B2"}
        {"table": "PersonChapter" | "Person", "file": "GameData/Person/A002.bin.lz", "index": 3, "label": "PID_..",
         "cell": "combat_music", "old": "STRM_BOSS_A2", "new": "STRM_BOSS_C1"}

Where the game picks its music (facts from the user's own RomFS and the code's symbol names; docs/rando/MUSIC.md):
- the map theme: map/config/<chapter>.bin, one row of the sheet "マップ設定" (map settings) per chapter, fields
  自軍BGM (player_bgm: the chapter's map theme), 自軍BGMその2 (player_bgm_2: the theme after a scene switches it,
  one chapter), 進撃BGM (advance_bgm: the battle-preparations / base theme; never changed here), then two bytes
  (BGM switch effect, volume-only). map::sound::Setup (003998C4) reads field 0 of that sheet; with the flag
  S_BMapBGM切り替え set it switches to field 1 when field 0 is playing. Each STRM_MAP_* stream holds the calm map
  arrangement AND its battle arrangement (the Sound Room lists both under one label: "(Storm)" / "(Fire)"); the
  game fades between them by channel volume. So a new map theme also brings its own battle arrangement.
- boss and named-unit battle themes: Person/PersonChapter.combat_music (+0x88), read by map::sound::SetBattleInfo
  (003977DC) through the unit's Person row (unit+0x9C, then +0x88).
- picked by code, not tables (not changed; would need the core): the castle-invasion boss themes (five STRM_BOSS_
  labels written in SetBattleInfo itself) and the My Castle jukebox pick (castle::JukeBox::GetBgmLabel).
- event scenes name their own tracks in Scripts/*.cmb (ev::BGMPlay "STRM_EVT_..."): never changed. No script
  command waits for a track to end (there is no BGM-wait command among the ev:: names), so no scene can hang on
  a changed theme.

Guards (each has a test in tests/test_rando_music.py): only music labels (STRM_MAP_* for maps, STRM_BOSS_* for
battles) that the game's sound archive names and that the game already uses in that role; never jingles,
fanfares, voice, system, event or sound-effect tracks; a new track has the same stream layout (channel count) as
the one it replaces (so the map/battle fade still has its channels); every chapter that had a map theme still has
one, and no chapter or unit that had none gets one; only the cells above are written; within one chapter file a
battle theme maps to the same new theme for every unit; the prep/base theme and the finale themes (STRM_MAPEX_*:
another stream layout) never change; same seed and opts -> the same edits; a new name is never longer than the name
it replaces (FITS rule, round 59, Grok's pick A in docs/collab/E1_MUSIC_GROK.md: the in-game core writes the new name
over the old one inside the chapter's own file, so every path plays the same music for one seed; the reversed
prologue song stays on the Prologue and the four amiibo boss songs replace only each other).

Our own code. The FE8 port's "Random music" (its sister project) was the model: per chapter and slot, a pick from
the pool of the game's own map themes, battle themes from the battle songs. No public Fates tool randomizes music.

    python tools/randomizer/music.py inventory              the facts: each chapter's themes, the pools, what is kept
    python tools/randomizer/music.py make --seed S [--music maps|maps+battles] [--out DIR]
        this track alone as one mod folder (romfs/map/config/*.bin + tables/PersonChapter.csv), under build/
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import randolib as R  # noqa: E402

TRACK = "music"
TOOL = "rando-music-v1"
MODES = ("off", "maps", "maps+battles")
DEFAULT_OPTS = {"music": "off"}
DEFAULT_OUT = os.path.join(ROOT, "build", "rando55", "music")

MAP_DIR = "map/config"
SHEET = "マップ設定".encode("cp932")
# the sheet's own field list (the file describes itself): name, type, our cell name
SCHEMA = (("自軍BGM", "str", "player_bgm"), ("自軍BGMその2", "str", "player_bgm_2"), ("進撃BGM", "str", "advance_bgm"),
          ("BGM切り替え演出", "u8", None), ("音量制御のみ", "u8", None), ("pad", "u16", None))
MAP_CELLS = ("player_bgm", "player_bgm_2")          # written; advance_bgm (prep/base theme) never
BATTLE_CELL = "combat_music"
MAP_PREFIX = "STRM_MAP_"                             # STRM_MAPEX_ (finale) does not match: another layout
BATTLE_PREFIX = "STRM_BOSS_"
# never music for this track, whatever a table says (jingles, fanfares, voice, system, event, movie, effects)
NOT_MUSIC = re.compile(r"^STRM_(EVT|SYS|VO|MOV|FF|AAC|CRISIS|MAPEX)_|JINGLE|FANFARE|_SE$|^SE_|^VO_", re.I)


class MusicTables:
    """maps     [{"file", "cid", "player_bgm", "player_bgm_2", "advance_bgm", "schema": None | why not usable}]
    persons  [{"table", "file", "index", "label", "combat_music"}] (only rows that are read; any combat_music)
    sound_labels  the STRM_ labels the sound archive names (None = unknown: then not checked)
    layouts  {label: stream channel count} (None/missing = unknown: then the label is not used)
    names    {label: song name} (spoiler only)"""

    def __init__(self, maps, persons, sound_labels=None, layouts=None, names=None):
        self.maps = sorted(maps, key=lambda m: m["file"])
        self.persons = sorted(persons, key=lambda p: (p["table"], p.get("file", ""), int(p["index"])))
        self.sound_labels = set(sound_labels) if sound_labels is not None else None
        self.layouts = dict(layouts or {})
        self.names = dict(names or {})

    def song(self, lab: str | None) -> str:
        if not lab:
            return "(none)"
        n = self.names.get(lab)
        return f"{n} [{lab}]" if n else lab


def check_opts(opts: dict | None) -> dict:
    o = dict(DEFAULT_OPTS)
    if opts and opts.get("music") is not None:
        v = opts["music"]
        o["music"] = ("maps+battles" if v is True else "off" if v is False else str(v).strip().lower())
    if o["music"] not in MODES:
        raise R.RandoError(f"random music: {' | '.join(MODES)}")
    return o


def opts_text(o: dict) -> str:
    return f"music={check_opts(o)['music']}"


def track_key(rng) -> str:
    """This track's sub-seed: from the run seed text and the track name (or 256 bits of a given Random)."""
    if isinstance(rng, random.Random):
        base = "random:" + format(rng.getrandbits(256), "064x")
    else:
        base = "seed:" + R.check_seed(str(rng))
    return hashlib.sha256("\x1f".join([TOOL, base, TRACK]).encode("utf-8")).hexdigest()


def stream(key: str, *parts: str) -> random.Random:
    h = hashlib.sha256("\x1f".join((key,) + parts).encode("utf-8")).digest()
    return random.Random(int.from_bytes(h, "big"))


# ------------------------------------------------------------------ which labels are music, and the pools
def is_music(lab: str | None, kind: str) -> bool:
    """kind 'map' or 'battle': the label has that role's prefix and is not a jingle/voice/system/event track."""
    if not lab or NOT_MUSIC.search(lab):
        return False
    return lab.startswith(MAP_PREFIX if kind == "map" else BATTLE_PREFIX)


def _majority_layout(t: MusicTables, labs: list[str]) -> int | None:
    seen: dict[int, int] = {}
    for lab in labs:
        n = t.layouts.get(lab)
        if n is not None:
            seen[n] = seen.get(n, 0) + 1
    return max(sorted(seen), key=lambda n: seen[n]) if seen else None


def pools(t: MusicTables) -> tuple[list[str], list[str], dict[str, str]]:
    """(map pool, battle pool, {label: why it is not in a pool}). A pool is every label the game already uses in
    that role (map config fields / combat_music), that is music by name, that the sound archive names, and whose
    stream has the role's usual layout."""
    excluded: dict[str, str] = {}

    def build(cands: list[str], kind: str) -> list[str]:
        cands = sorted(set(c for c in cands if c))
        ok = []
        for lab in cands:
            if lab.startswith("STRM_MAPEX_"):
                excluded[lab] = "a finale theme (STRM_MAPEX_*: one arrangement, no battle version; kept where it is)"
            elif not is_music(lab, kind):
                excluded[lab] = (f"not a {kind} theme by name (only {MAP_PREFIX if kind == 'map' else BATTLE_PREFIX}*;"
                                 " jingles, voice, system, event and finale tracks stay out)")
            elif t.sound_labels is not None and lab not in t.sound_labels:
                excluded[lab] = "the sound archive does not name it"
            elif lab not in t.layouts:
                excluded[lab] = "its stream file was not found / not read"
            else:
                ok.append(lab)
        lay = _majority_layout(t, ok)
        out = []
        for lab in ok:
            if t.layouts.get(lab) != lay:
                excluded[lab] = f"another stream layout ({t.layouts.get(lab)} channels, the {kind} themes have {lay})"
            else:
                out.append(lab)
        return out

    mp = build([m[c] for m in t.maps if not m.get("schema") for c in MAP_CELLS], "map")
    bp = build([p[BATTLE_CELL] for p in t.persons], "battle")
    return mp, bp, excluded


# ------------------------------------------------------------------ the plan
def plan_music(tables: MusicTables, rng, opts: dict | None = None) -> tuple[list[dict], list[str]]:
    o = check_opts(opts)
    if o["music"] == "off":
        return [], []
    t = tables
    key = track_key(rng)
    mp, bp, excluded = pools(t)
    edits: list[dict] = []
    lines = [f"Random music: {o['music']}",
             "Each chapter's map theme is a pick from the game's own map themes (a map theme brings its own battle",
             "arrangement: the game fades between the two). Event scenes keep their own music; the battle-preparations",
             "theme, the finale themes, jingles and voices are not touched.", "", "Map themes:"]
    kept: list[str] = []
    for m in t.maps:
        if m.get("schema"):
            kept.append(f"{m['file']}: {m['schema']}")
            continue
        new_main = None
        for cell in MAP_CELLS:
            old = m.get(cell)
            if not old:
                continue
            if old not in mp:
                kept.append(f"{m['cid']} {cell}: {t.song(old)} kept ({excluded.get(old, 'not in the map pool')})")
                continue
            avoid = {old} | ({new_main} if cell == "player_bgm_2" and new_main else set())
            fits = [x for x in mp if len(x) <= len(old)]     # FITS rule (docs/collab/E1_MUSIC_GROK.md)
            choices = [x for x in fits if x not in avoid] or [x for x in fits if x != old] or [old]
            new = stream(key, "map", m["file"], cell).choice(choices)
            if cell == "player_bgm":
                new_main = new
            if new != old:
                edits.append({"table": "MapConfig", "file": m["file"], "cid": m["cid"], "cell": cell,
                              "old": old, "new": new})
                what = "" if cell == "player_bgm" else " (after the scene's switch)"
                lines.append(f"  {m['cid']}{what}: {t.song(old)} -> {t.song(new)}")
    if o["music"] == "maps+battles":
        lines += ["", "Boss and named-unit battle themes (same original theme -> same new theme within a chapter):"]
        groups: dict[tuple, list[dict]] = {}
        for p in t.persons:
            old = p.get(BATTLE_CELL)
            if old:
                groups.setdefault((p["table"], p.get("file", ""), old), []).append(p)
        for (table, f, old), rows in sorted(groups.items()):
            where = os.path.basename(f).split(".")[0] if f else table
            if old not in bp:
                kept.append(f"{where}: battle theme {t.song(old)} kept ({excluded.get(old, 'not in the battle pool')})")
                continue
            choices = [x for x in bp if x != old and len(x) <= len(old)] or [old]
            new = stream(key, "battle", table, f, old).choice(choices)
            for p in rows:
                edits.append({"table": table, "file": f, "index": int(p["index"]), "label": p["label"],
                              "cell": BATTLE_CELL, "old": old, "new": new})
            lines.append(f"  {where}: {t.song(old)} -> {t.song(new)} ({len(rows)} unit{'s' if len(rows) != 1 else ''})")
    if kept:
        lines += ["", "Kept as they are:"] + [f"  {k}" for k in kept]
    lines += ["", "Picked by the game's code, not tables (unchanged): the castle-invasion boss themes and the My Castle",
              "jukebox song."]
    return edits, lines


# ------------------------------------------------------------------ guards (from the edits alone)
def run_guards(tables: MusicTables, edits: list[dict], opts: dict | None = None) -> dict:
    o = check_opts(opts)
    t = tables
    mp, bp, _ex = pools(t)
    out: dict[str, dict] = {}

    def g(name, bad):
        out[name] = {"ok": not bad, "detail": bad[:50]}

    g("off makes no edits", [f"{len(edits)} edits with music=off"] if o["music"] == "off" and edits else [])
    maps = {m["file"]: m for m in t.maps}
    rows = {(p["table"], p.get("file", ""), int(p["index"])): p for p in t.persons}
    bad_cell, bad_old, bad_lab, bad_lay, bad_len = [], [], [], [], []
    after = {f: {c: m.get(c) for c in MAP_CELLS} for f, m in maps.items()}
    seen = set()
    for e in edits:
        k = (e["table"], e.get("file", ""), e.get("index"), e["cell"])
        if k in seen:
            bad_cell.append(f"{k}: written twice")
        seen.add(k)
        if e["table"] == "MapConfig":
            m = maps.get(e["file"])
            if e["cell"] not in MAP_CELLS or m is None or m.get("schema"):
                bad_cell.append(f"{e['file']} {e['cell']}: not a writable map-theme cell")
                continue
            if m.get(e["cell"]) != e["old"]:
                bad_old.append(f"{e['file']} {e['cell']}: old {e['old']} but the table has {m.get(e['cell'])}")
            if o["music"] == "off":
                continue
            if not is_music(e["new"], "map") or e["new"] not in mp:
                bad_lab.append(f"{e['file']} {e['cell']}: {e['new']} is not in the map-theme pool")
            after[e["file"]][e["cell"]] = e["new"]
        elif e["table"] in ("PersonChapter", "Person") and e["cell"] == BATTLE_CELL:
            p = rows.get((e["table"], e.get("file", ""), int(e["index"])))
            if p is None:
                bad_cell.append(f"{e['table']} {e.get('file')} #{e['index']}: no such row")
                continue
            if p.get(BATTLE_CELL) != e["old"] or not e["old"]:
                bad_old.append(f"{e['table']} {e.get('file')} #{e['index']}: old {e['old']!r} but the table has "
                               f"{p.get(BATTLE_CELL)!r} (a unit with no theme never gets one)")
            if o["music"] != "maps+battles":
                bad_cell.append(f"{e['table']} #{e['index']}: battle themes written with music={o['music']}")
            if not is_music(e["new"], "battle") or e["new"] not in bp:
                bad_lab.append(f"{e['table']} {e.get('file')} #{e['index']}: {e['new']} is not in the battle pool")
        else:
            bad_cell.append(f"{e['table']} {e['cell']}: this track writes only map themes and combat_music")
            continue
        if len(e["new"] or "") > len(e["old"] or ""):
            bad_len.append(f"{e.get('file')} {e['cell']}: {e['old']} -> {e['new']} (a longer name)")
        lo, ln = t.layouts.get(e["old"]), t.layouts.get(e["new"])
        if lo is None or ln is None or lo != ln:
            bad_lay.append(f"{e.get('file')} {e['cell']}: {e['old']} ({lo} ch) -> {e['new']} ({ln} ch)")
    g("only the map-theme cells and combat_music are written", bad_cell)
    g("old values match the game's tables", bad_old)
    g("only music labels of the right role, named by the sound archive", bad_lab)
    g("same stream layout as the track replaced", bad_lay)
    g("a new name is never longer than the old one (the in-game core writes it in place)", bad_len)
    lost = []
    for f, m in maps.items():
        for c in MAP_CELLS:
            if bool(m.get(c)) != bool(after[f][c]):
                lost.append(f"{f} {c}: {m.get(c)!r} -> {after[f][c]!r}")
        if m.get("player_bgm") and not after[f]["player_bgm"]:
            lost.append(f"{f}: no map theme left")
    g("every chapter that had a map theme still has one (and none gains one)", lost)
    per: dict[tuple, set] = {}
    for e in edits:
        if e["cell"] == BATTLE_CELL:
            per.setdefault((e["table"], e.get("file", ""), e["old"]), set()).add(e["new"])
    g("one chapter: the same old battle theme -> the same new one",
      [f"{k}: {sorted(v)}" for k, v in per.items() if len(v) > 1])
    return out


# ------------------------------------------------------------------ reading the game (user's own RomFS, read only)
def parse_config(rel: str, raw: bytes) -> dict:
    """One map/config file -> {"file", "cid", cells..., "schema": None | why the file is not usable}. The file
    describes itself (field names and types); anything unexpected leaves the file unusable (kept)."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "tables"))
    import tablelib as T
    stem = os.path.basename(rel).split(".")[0]
    row = {"file": rel, "cid": "CID_" + stem, "schema": None}
    for _n, _k, cell in SCHEMA:
        if cell:
            row[cell] = None
    try:
        c = T.Container(rel, raw)
    except Exception as ex:  # noqa: BLE001
        row["schema"] = f"not a readable table file ({ex.__class__.__name__})"
        return row
    if SHEET not in c.label_off:
        row["schema"] = "no map-settings sheet"
        return row
    # field list: label MOD_<sheet> at the start: u32 count, then per field (name ptr, type ptr, 3 words)
    mod = c.label_off.get(b"MOD_" + SHEET)
    lab = c.label_off[SHEET]
    try:
        n = c.u32(mod)
        names = []
        for i in range(n):
            o = mod + 4 + i * 20
            names.append(((c.string_at(c.u32(o)) or b"").decode("cp932"), (c.string_at(c.u32(o + 4)) or b"").decode("cp932")))
        want = [(a, b) for a, b, _c in SCHEMA]
        if names != want:
            row["schema"] = "the sheet's field list is not the one this track knows"
            return row
        cnt, size = struct.unpack_from("<HH", c.data, lab + 4)
        if cnt != 1 or size != 0x10:
            row["schema"] = f"the sheet has {cnt} rows of 0x{size:X} bytes (expected 1 of 0x10)"
            return row
    except Exception as ex:  # noqa: BLE001
        row["schema"] = f"the sheet could not be read ({ex.__class__.__name__})"
        return row
    for i, (_n, _k, cell) in enumerate(SCHEMA[:3]):
        o = lab + 12 + 4 * i
        if o in c.relset:
            s = c.string_at(c.u32(o))
            row[cell] = s.decode("cp932") if s else None
    return row


def rebuild_config(rel: str, raw: bytes, changes: dict[str, str]) -> bytes:
    """The map/config file with the given cells (player_bgm / player_bgm_2) set to new labels; every other byte
    the way the game's own file has it (same string-pool rule; a no-change rebuild is byte-identical)."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "tables"))
    import tablelib as T
    c = T.Container(rel, raw)
    lab = c.label_off[SHEET]
    where = {cell: lab + 12 + 4 * i for i, (_n, _k, cell) in enumerate(SCHEMA[:3]) if cell}
    ptrs = {}
    for cell, new in changes.items():
        if cell not in MAP_CELLS:
            raise R.RandoError(f"{rel}: {cell} is not written by this track")
        o = where[cell]
        if o not in c.relset:
            raise R.RandoError(f"{rel}: {cell} is empty in the game; a theme is never added")
        ptrs[o] = ("str", new.encode("ascii"))
    return T.rebuild(c, bytearray(c.data), ptrs)


def stream_channels(path: str) -> int | None:
    """Channel count of a .bcstm stream (INFO block, channel-info reference table), or None."""
    try:
        with open(path, "rb") as fh:
            b = fh.read(0x400)
        if b[:4] != b"CSTM":
            return None
        nblk = struct.unpack_from("<H", b, 0x10)[0]
        blocks = {struct.unpack_from("<H", b, 0x14 + i * 12)[0]: struct.unpack_from("<I", b, 0x18 + i * 12)[0]
                  for i in range(nblk)}
        io = blocks.get(0x4000)
        if io is None or b[io:io + 4] != b"INFO":
            return None
        base = io + 8
        kind, _p, off = struct.unpack_from("<HHi", b, base + 16)
        if kind != 0x0101 or off < 0:
            return None
        return struct.unpack_from("<I", b, base + off)[0]
    except (OSError, struct.error):
        return None


def load_tables(names: bool = True) -> MusicTables:
    import gamedata as GD
    why = GD.available()
    if why:
        raise R.RandoError(f"the game's tables are not available: {why}")
    import mods as M
    romfs = M.ROMFS
    d = os.path.join(romfs, *MAP_DIR.split("/"))
    maps = []
    for f in sorted(os.listdir(d)):
        if f.lower().endswith(".bin"):
            with open(os.path.join(d, f), "rb") as fh:
                maps.append(parse_config(f"{MAP_DIR}/{f}", fh.read()))
    persons = []
    for r in GD._load("PersonChapter"):
        persons.append({"table": "PersonChapter", "file": r["file"], "index": r["index"], "label": r["label"],
                        BATTLE_CELL: r.get(BATTLE_CELL, "")})
    for r in GD._load("Person", only_first=True):
        persons.append({"table": "Person", "file": "", "index": r["index"], "label": r["label"],
                        BATTLE_CELL: r.get(BATTLE_CELL, "")})
    sar = os.path.join(romfs, "sound", "IRON15_sound.bcsar")
    labels = None
    if os.path.isfile(sar):
        with open(sar, "rb") as fh:
            labels = {m.decode() for m in re.findall(rb"STRM_[A-Z0-9_]+", fh.read())}
    sd = os.path.join(romfs, "sound", "stream")
    layouts = {}
    if os.path.isdir(sd):
        for f in os.listdir(sd):
            if f.upper().startswith("STRM_") and f.lower().endswith(".bcstm"):
                n = stream_channels(os.path.join(sd, f))
                if n is not None:
                    layouts[f[:-len(".bcstm")]] = n
    nm = {}
    if names:
        try:
            a = M.TX.archive("m/@E/Bgm.bin.lz", romfs)
            for lab, _v, x in a.entries:
                s = lab.decode("cp932", "replace")
                if not x and s.startswith("MKID_STRM_"):
                    nm[s[len("MKID_"):]] = a.text_of[lab]
        except Exception:  # noqa: BLE001  (names only make the spoiler nicer)
            nm = {}
    return MusicTables(maps, persons, labels, layouts, nm)


# ------------------------------------------------------------------ mod files
def edits_to_files(tables: MusicTables, edits: list[dict], read_raw=None) -> dict[str, bytes]:
    """{mod-relative path: bytes}: romfs/map/config/<file>.bin (whole files, rebuilt from the game's own bytes)
    and tables/PersonChapter.csv (+ tables/Person.csv if a resident row changes). read_raw(rel) -> bytes reads the
    game file (default: the user's extracted RomFS)."""
    if read_raw is None:
        import gamedata as GD  # noqa: F401  (puts tools/mods on the path)
        import mods as M

        def read_raw(rel):
            with open(os.path.join(M.ROMFS, *rel.split("/")), "rb") as fh:
                return fh.read()
    files: dict[str, bytes] = {}
    per_file: dict[str, dict[str, str]] = {}
    for e in edits:
        if e["table"] == "MapConfig":
            per_file.setdefault(e["file"], {})[e["cell"]] = e["new"]
    for rel in sorted(per_file):
        files[f"romfs/{rel}"] = rebuild_config(rel, read_raw(rel), per_file[rel])
    for table in ("PersonChapter", "Person"):
        rows = [e for e in edits if e["table"] == table]
        if not rows:
            continue
        head = (["file"] if table == "PersonChapter" else []) + ["index", "label", BATTLE_CELL]
        out = [head]
        for e in sorted(rows, key=lambda e: (e.get("file", ""), e["index"])):
            out.append(([e["file"]] if table == "PersonChapter" else []) + [str(e["index"]), e["label"], e["new"]])
        files[f"tables/{table}.csv"] = R._csv(out)
    return files


def render(t: MusicTables, seed: str, o: dict, edits: list[dict], spoil: list[str], guards: dict,
           read_raw=None) -> dict[str, bytes]:
    files = edits_to_files(t, edits, read_raw)
    meta = {"name": R.mod_name(seed) + "-music", "description": f"Randomizer track music, seed {seed} "
            f"({opts_text(o)}). For one randomized save only; see docs/rando/MUSIC.md.", "enabled": True,
            "order": 130, "override": False, "randomizer": {"tool": TOOL, "track": TRACK, "seed": seed, "options": o}}
    plan = {"tool": TOOL, "track": TRACK, "seed": seed, "options": o, "edits": edits, "guards": guards}
    sp = ["Fire Emblem Fates randomizer - spoiler log, track music", f"seed: {seed}", f"options: {opts_text(o)}",
          ""] + spoil + ["", "Guards:"]
    for k, v in guards.items():
        sp.append(f"  {'PASS' if v['ok'] else 'FAIL'} {k}")
        sp += [f"       {x}" for x in v["detail"][:12]]
    files["mod.json"] = (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    files["spoiler-music.txt"] = ("\n".join(sp) + "\n").encode("utf-8")
    files["plan-music.json"] = (json.dumps(plan, indent=1, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    return files


def _forbidden(out: str) -> str | None:
    top = os.path.normcase(os.path.abspath(out)) + os.sep
    for env in ("APPDATA", "LOCALAPPDATA"):
        v = os.environ.get(env)
        if v and top.startswith(os.path.normcase(os.path.realpath(v)) + os.sep):
            return f"{out} is inside %{env}%"
    if top.startswith(os.path.normcase(os.path.join(ROOT, "mods")) + os.sep):
        return "the owner's mods/ folder"
    return None


def cmd_inventory() -> int:
    t = load_tables()
    mp, bp, ex = pools(t)
    print(f"map configs: {len(t.maps)} ({sum(1 for m in t.maps if m['player_bgm'])} with a map theme, "
          f"{sum(1 for m in t.maps if m['schema'])} unreadable)")
    for m in t.maps:
        print(f"  {m['cid']:<10} map={m['player_bgm'] or '-':<15} after-switch={m['player_bgm_2'] or '-':<13} "
              f"prep={m['advance_bgm'] or '-'}{'  [' + m['schema'] + ']' if m['schema'] else ''}")
    print(f"map pool ({len(mp)}): " + ", ".join(t.song(x) for x in mp))
    print(f"battle pool ({len(bp)}): " + ", ".join(t.song(x) for x in bp))
    print(f"units with a battle theme: {sum(1 for p in t.persons if p[BATTLE_CELL])}")
    for lab, why in sorted(ex.items()):
        print(f"  not used: {lab}: {why}")
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inventory")
    p = sub.add_parser("make")
    p.add_argument("--seed", required=True)
    p.add_argument("--music", choices=MODES[1:], default="maps+battles")
    p.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "inventory":
            return cmd_inventory()
        why = _forbidden(a.out)
        if why:
            raise R.RandoError(f"refused: {why}")
        seed = R.check_seed(a.seed)
        o = check_opts({"music": a.music})
        t = load_tables()
        edits, spoil = plan_music(t, seed, o)
        guards = run_guards(t, edits, o)
        files = render(t, seed, o, edits, spoil, guards)
        folder = R.write_mod(files, os.path.join(os.path.abspath(a.out), R.mod_name(seed) + "-music"))
        print(f"made {folder}: {len(edits)} cells")
        for k, v in guards.items():
            print(f"  {'PASS' if v['ok'] else 'FAIL'} {k}")
        return 0 if all(v["ok"] for v in guards.values()) else 2
    except R.RandoError as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
