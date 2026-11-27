#!/usr/bin/env python3
"""Randomizer track "colour": recolour a swapped character, and keep a character's own colours in a class they never
had (F-047 recolour addenda, 2026-11-20; facts and hooks in docs/rando/COLOURS.md; colour rule by Grok,
docs/collab/COLOUR_RULE_GROK.md).

    load_tables(game="fates", facts=None)        -> ColourTables  (read only; Fates or Seal of Flames)
    plan_colours(tables, plan, opts)             -> (edits, spoiler_lines)
    run_guards(tables, edits, plan, opts)        -> {name: {"ok": bool, "detail": [...]}}
    patch_lines(edits)                           -> text lines for the in-game patch (new kinds "asset", "face",
                                                    "tint"; the core hook that reads them: docs/rando/COLOURS.md 5)
    plan_from(merged_edits, facts, look)         -> the plan dict below, from the merged make's edits
    recolour_rgb(rgb, src, dst) / recolour_rgba  -> the picture recolour (reference for the core, and the previews)

Facts behind it (read from the game's own code and tables, docs/rando/COLOURS.md sections 1-3):
- Battle model hair = one 0xRRGGBB number per model-table row (asset/ROM0..6.lz, IS .bin; a row is mask_lo,
  [mask_hi when mask_lo bit 0], one always-present condition, then one field per set bit; mask_hi bit 2 = hair
  colour, bit 3 = skin colour; BattleUnitResName::Import 0x1F95A4). Rows are applied in priority order (the header
  word's high 16 bits, AssetTable::Load 0x1697BC keeps the list sorted), so a person's own row (ROM3/ROM4,
  condition AID_<person>) overrides the class row's generic hair (ROM2, condition JID_<class>): a person keeps
  their own hair and skin in ANY class already. BattleUnitResName::PostProcess 0x1F8A84 replaces the hair with the
  unit's own hair colour only for the avatar and children (Unit+0x13C, FaceData +0x1C via
  FaceDataManager::GetHairColorFromPerson 0x1E0180).
- Outfits carry no colour number: generic class bodies are baked army-colour textures (`..._cl0n_P/E/A`), a
  personal outfit is its own model (a row with AID_<person> AND JID_<class>).
- Portraits and map sprites of named adults have their hair baked into the pictures (FaceData hair layer only for
  the avatar and the children; unit/Head/<name>/<army colour><n>.bch.lz). So hair in battle is a table cell, while
  portrait and map hair need a picture recolour by the core (kind "tint").

tables  a ColourTables: main Person rows, chapter copies (GameData/Person/*), the model table rows, FaceData records,
        the map head folders, and the rules; a Seal of Flames tables object reads the mod's own files over the base
        RomFS (its FaceData with its 4 new face archives, ROM2/ROM3), nothing here names a person.
plan    {"look": "keep"|"full", "swaps": [[spot PID_, filler PID_], ...],
         "classes": {PID_: [JID_, ...]}  (every class a person can be in after the run: start class, class line,
                                          reclass and promotion targets, from every module that moved them)}
opts    {"recolour": "on"|"clear"|"off", "own_colours": "on"|"off", "boss_copies": "skip"|"follow"}; "recolour"
        applies only when there are swaps in the keep look (the full look shows the filler's own model: nothing to
        do). Round 71 (the page's own Recolour row): "clear" ("Easier to see") gives the battle hair cell a clearer
        colour of the new person's hue (clear_hair; battle hair only, the FaceData colour stays the person's own).

edits   (fixed order: spots by PID_, then file, then offset)
        {"table": "AssetTable", "file": "asset/ROM3.lz", "header": 0x0FA01111, "record": n, "off": data offset of
         the colour word, "cond": "AID_..", "field": "hair", "old": int, "new": int, "spot": .., "filler": ..,
         "laid_by": "core_resident"}
        {"table": "FaceData", "file": "face/FaceData.bin.lz", "index": n, "off": data offset (+0x1C),
         "label": "FSID_..", "field": "colour", "old": int, "new": int, "spot": .., "filler": ..,
         "laid_by": "core_resident"}
        {"table": "Picture", "what": "portrait"|"map_head", "file": romfs path, "from": 0xRRGGBB, "to": 0xRRGGBB,
         "spot": .., "filler": .., "laid_by": "core_tint"}
        own colours never edit anything (Grok's rule 2: hair and skin already stay the person's own; the army outfit
        stays, it shows the side); they give spoiler lines and a guard that every such person HAS an own hair row.

    python tools/randomizer/colours.py facts [--game seal]            (what the tables hold, counts only)
    python tools/randomizer/colours.py plan --seed S [--game seal] [--recruit route|any] [--recolour on|clear|off]
                                       [--json FILE] [--swatch build/.../swatch.png]
    python tools/randomizer/colours.py check [--seeds 50] [--game seal] [--recolour on|clear|off]
    python tools/randomizer/colours.py preview --spot PID_A --filler PID_B --out build/r59/colour/preview [--game seal]
Our own code. Public Fates tools are GPL: facts only, no code.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "assets"))

TRACK = "colour"
TOOL = "rando-colour-v1"
DEFAULT_OPTS = {"recolour": "on", "own_colours": "on", "boss_copies": "skip", "pictures": "on"}
CHOICES = {"recolour": ("on", "clear", "off"), "own_colours": ("on", "off"), "boss_copies": ("skip", "follow"),
           "pictures": ("on", "off")}
# "pictures": the portrait / map-head tint (core kind "tint"). The in-game make passes "off" (round-59 review: the
# per-pixel recolour bleached line art and skin on dark-to-light swaps, Kagero <- Crimson); then a swap changes the
# battle hair cell and the FaceData colour only, and the spoiler says the pictures keep their colours.
ASSET_FILES = tuple(f"asset/ROM{i}.lz" for i in range(7))
FACE_FILE = "face/FaceData.bin.lz"
HAIR_BIT, SKIN_BIT = 2, 3          # mask_hi bits (BattleUnitResName::Import: +0x724 hair, +0x728 skin)
FACE_REC, FACE_COLOUR = 0x48, 0x1C
PLACEHOLDER_FACE_COLOURS = (0xFFFFFFFF, 0xFF000000)   # generic faces (soldiers, Seal's new class faces)
CREDIT = "Colour rule: Grok (docs/collab/COLOUR_RULE_GROK.md). Seal of Flames by Laz14, CC BY-NC-ND 4.0 (read locally)."


# ------------------------------------------------------------------ small helpers
def rgb_hex(v: int) -> str:
    return f"#{v & 0xFFFFFF:06X}"


def face_to_rgb(c: int) -> int:
    """FaceData +0x1C is stored as bytes R, G, B, A (Color8): little-endian u32 0xAABBGGRR -> 0xRRGGBB."""
    return ((c & 0xFF) << 16) | (c & 0xFF00) | ((c >> 16) & 0xFF)


def rgb_to_face(rgb: int, old: int) -> int:
    """0xRRGGBB -> FaceData u32 keeping the old alpha byte."""
    return (old & 0xFF000000) | ((rgb & 0xFF) << 16) | (rgb & 0xFF00) | ((rgb >> 16) & 0xFF)


def check_opts(opts: dict | None) -> dict:
    o = dict(DEFAULT_OPTS)
    for k, v in (opts or {}).items():
        if k in DEFAULT_OPTS and v is not None:
            if v not in CHOICES[k]:
                raise ValueError(f"colour option {k}={v!r}: one of {CHOICES[k]}")
            o[k] = v
    return o


# ------------------------------------------------------------------ the model table (asset/ROM*.lz)
def parse_asset(data: bytes, relocs: set[int], strz) -> tuple[int, list[dict]]:
    """An AssetTable data region -> (header word, rows). Each row: {"record", "off", "lo", "hi", "fields":
    [(key, data offset, value)]} with key "L<n>"/"H<n>" (L0 = the always-present first condition); string fields
    (relocated words) come back as text, numbers as int. Layout from AssetFile::GetInfo 0x4F83A0 and
    BattleUnitResName::Import 0x1F95A4."""
    hdr = struct.unpack_from("<I", data, 0)[0]
    rows, o, n = [], 4, 0
    while o + 4 <= len(data):
        lo = struct.unpack_from("<I", data, o)[0]
        if lo == 0:
            break
        start, o, hi = o, o + 4, 0
        if lo & 1:
            hi = struct.unpack_from("<I", data, o)[0]
            o += 4
        keys = ["L0"] + [f"L{i}" for i in range(1, 32) if lo >> i & 1] + [f"H{i}" for i in range(32) if hi >> i & 1]
        fields = []
        for k in keys:
            if o + 4 > len(data):
                raise ValueError(f"asset row at 0x{start:X} runs past the data region")
            fields.append((k, o, strz(o) if o in relocs else struct.unpack_from("<I", data, o)[0]))
            o += 4
        rows.append({"record": n, "off": start, "lo": lo, "hi": hi, "fields": fields})
        n += 1
    return hdr, rows


def row_get(row: dict, key: str):
    for k, o, v in row["fields"]:
        if k == key:
            return o, v
    return None, None


def row_conds(row: dict) -> list[str]:
    """The row's condition strings (L0 always, L1/L2 when present)."""
    return [v for k, _o, v in row["fields"] if k in ("L0", "L1", "L2") and isinstance(v, str)]


# ------------------------------------------------------------------ the tables object
class ColourTables:
    def __init__(self, game: str, persons: list[dict], copies: list[dict], assets: dict, faces: list[dict],
                 heads: dict, rules: dict, female=None, arcs: set | None = None,
                 route_of: dict | None = None, in_scope=None, is_child=None):
        self.game = game
        self._in_scope = in_scope or (lambda p: True)
        self._is_child = is_child or (lambda p: False)
        self.route_of = route_of or {}  # PID_ -> route letters the person joins on (randolib route_members)
        self.persons = persons
        self.by_pid = {p["pid"]: p for p in persons}
        self.copies = copies
        self.assets = assets            # rel -> {"header": int, "rows": [...]}, in priority order
        self.faces = faces              # FaceData records (portrait.load_facedata format + "off")
        self.face_by_fsid = {f["fsid"]: f for f in faces}
        self.heads = heads              # map head folder name -> [romfs paths]
        self.rules = rules
        self.arcs = arcs or set()       # face/face/*.arc names present
        self._female = female or (lambda p: False)
        self._hair = None

    # ---- facts per person
    def female(self, p: dict) -> bool:
        return bool(self._female(p))

    def person_rows(self, aid: str) -> list[tuple[str, dict]]:
        """(file, row) for every model-table row whose first condition is this AID_, in priority order."""
        return [(rel, r) for rel, a in self.assets.items() for r in a["rows"] if r["fields"][0][2] == aid]

    def hair_of(self, aid: str) -> int | None:
        """The person's battle hair colour: the LAST (highest priority) row with this AID_ and no class condition
        that carries a hair field; else any row with this AID_ carrying one."""
        if self._hair is None:
            self._hair = {}
        if aid not in self._hair:
            best, any_ = None, None
            for _rel, r in self.person_rows(aid):
                _o, v = row_get(r, f"H{HAIR_BIT}")
                if v is None:
                    continue
                any_ = v
                if not any(c.lstrip("!").startswith("JID_") for c in row_conds(r)[1:]):
                    best = v
            self._hair[aid] = best if best is not None else any_
        return self._hair[aid]

    def hairless(self, aid: str) -> bool:
        """The person's own head row names no hair model ("null" hair, e.g. a bald man): no hair colour to keep."""
        for _rel, r in self.person_rows(aid):
            _o, v = row_get(r, "L7")
            if v == "null" and not any(c.lstrip("!").startswith("JID_") for c in row_conds(r)[1:]):
                return True
        return False

    def unit_hair(self, p: dict) -> bool:
        """The avatar and the children: the battle hair is the unit's own hair colour (PostProcess 0x1F8A84 copies
        Unit+0x13C when the unit has avatar data or the person has a parent), not a model-table number."""
        return self._is_child(p) or str(p.get("family_index", "0")) not in ("0", "") or             bool(set(str(p.get("flags", "")).split("|")) & set(self.rules.get("keep_class_person_flags", [])))

    def picture_hair(self, p: dict) -> int | None:
        """Hair colour for the pictures: the model-table hair, else the FaceData colour (as 0xRRGGBB; the
        placeholder colours white/black of generic faces do not count), else the hair of the person's class row
        (a generic person, e.g. Seal of Flames' class-named recruits, wears the class's soldier hair)."""
        h = self.hair_of(p["aid"]) if p.get("aid") else None
        if h is None and self.own_model(p):
            f = self.face_by_fsid.get(f"FSID_ST_{self.short(p.get('fid', ''))}")
            if f and f["color"] not in PLACEHOLDER_FACE_COLOURS:
                h = face_to_rgb(f["color"])
        if h is None:
            h = self.class_hair(p.get("job", ""))
        return h

    def own_model(self, p: dict) -> bool:
        """The person has model rows of their own (an AID_ with rows): only then do their hair cell, portrait and
        map head belong to them alone and can be recoloured."""
        return bool(p.get("aid")) and bool(self.person_rows(p["aid"]))

    def class_hair(self, jid: str) -> int | None:
        v = None
        for _rel, a in self.assets.items():
            for r in a["rows"]:
                if r["fields"][0][2] == jid:
                    _o, h = row_get(r, f"H{HAIR_BIT}")
                    if h is not None:
                        v = h
        return v

    def skin_of(self, aid: str) -> int | None:
        v = None
        for _rel, r in self.person_rows(aid):
            _o, s = row_get(r, f"H{SKIN_BIT}")
            if s is not None and not any(c.lstrip("!").startswith("JID_") for c in row_conds(r)[1:]):
                v = s
        return v

    def own_outfit_classes(self, aid: str) -> set[str]:
        """Classes for which this person has a personal outfit row (AID_ and JID_ conditions)."""
        out = set()
        for _rel, r in self.person_rows(aid):
            for c in row_conds(r)[1:]:
                if c.startswith("JID_"):
                    out.add(c)
        return out

    def short(self, aid_or_fid: str) -> str:
        return aid_or_fid.split("_", 1)[1] if "_" in aid_or_fid else aid_or_fid


def _romfs_roots(game: str) -> list[str]:
    import sources as SRC
    base = SRC.BASE_ROMFS
    if SRC.check_game(game) == "fates":
        return [base]
    return [SRC.seal_romfs(), base]       # the mod's own files win, the rest is the base game (as the game sees it)


def _find(roots: list[str], rel: str) -> str | None:
    for r in roots:
        p = os.path.join(r, *rel.split("/"))
        if os.path.isfile(p):
            return p
    return None


def load_assets(roots: list[str]) -> dict:
    import isbin
    out = []
    for rel in ASSET_FILES:
        p = _find(roots, rel)
        if not p:
            continue
        d, _ = isbin.load_maybe_lz(p)
        b = isbin.IsBin.parse(d)
        se_rel = len(b.data) + 4 * len(b.relocs) + 8 * len(b.labels)
        rel_set = set(b.relocs)

        def strz(o, b=b, se_rel=se_rel):
            return isbin._strz(b.strtab, struct.unpack_from("<I", b.data, o)[0] - se_rel).decode("cp932", "replace")

        hdr, rows = parse_asset(b.data, rel_set, strz)
        out.append((hdr >> 16, rel, {"header": hdr, "rows": rows, "path": p}))
    out.sort(key=lambda t: t[0])          # AssetTable::Load keeps the list sorted by this priority
    return {rel: a for _prio, rel, a in out}


def load_faces(roots: list[str]) -> list[dict]:
    import portrait
    p = _find(roots, FACE_FILE)
    recs = portrait.load_facedata(p)
    for r in recs:
        r["off"] = 4 + r["index"] * FACE_REC
    return recs


def load_tables(game: str = "fates", facts=None) -> ColourTables:
    """The user's own RomFS (and, for Seal of Flames, the mod's files over it). Read only."""
    import sources as SRC
    game = SRC.check_game(game)
    if facts is None:
        facts = SRC.tables(game, names=False)
    roots = _romfs_roots(game)
    assets = load_assets(roots)
    faces = load_faces(roots)
    heads = {}
    for r in reversed(roots):
        for d in glob.glob(os.path.join(r, "unit", "Head", "*")):
            if os.path.isdir(d):
                heads[os.path.basename(d)] = sorted(f"unit/Head/{os.path.basename(d)}/{os.path.basename(f)}"
                                                    for f in glob.glob(os.path.join(d, "*.bch.lz")))
    arcs = set()
    for r in roots:
        arcs |= {os.path.basename(f)[:-4] for f in glob.glob(os.path.join(r, "face", "face", "*.arc"))}
    copies = _load_copies(facts)
    route_of = {}
    for letter, pids in facts.route_members().items():
        for pid in pids:
            route_of.setdefault(pid, set()).add(letter)
    return ColourTables(game, list(facts.persons), copies, assets, faces, heads, facts.rules,
                        female=facts.female, arcs=arcs, route_of=route_of, in_scope=facts.in_scope,
                        is_child=facts.is_child)


def _load_copies(facts) -> list[dict]:
    """Chapter Person rows (GameData/Person/*) that reuse a main person's AID_ under another PID_."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "mods"))
    import mods as M
    main = {p["aid"]: p["pid"] for p in facts.persons if p.get("aid")}
    t = M.reg()["Person"]
    cd = M.codec("Person")
    head = cd.columns()
    out = []
    root = M.T.ROMFS
    for path in sorted(glob.glob(os.path.join(root, "GameData", "Person", "*.bin.lz"))):
        rel = "GameData/Person/" + os.path.basename(path)
        try:
            c = M.T.container(rel)
            start, count = M.T.locate(t, c)
            labels = M.T.record_labels(t, c, start, count)
        except Exception:  # noqa: BLE001  (a file the codec does not read is not a person file)
            continue
        for i in range(count):
            r = dict(zip(head, cd.decode(c, i, start + i * t.size, labels[i])))
            if r.get("aid") in main and r.get("pid") != main[r["aid"]]:
                out.append({"file": rel, "chapter": os.path.basename(path).split(".")[0], "pid": r["pid"],
                            "aid": r["aid"], "belong": r.get("belong", ""), "replace_index": r.get("replace_index", "0")})
    return out


# ------------------------------------------------------------------ boss copies (Grok's rule 3)
def boss_copies(t: ColourTables, pid: str) -> list[dict]:
    """Chapter copies of this person that fight as someone else's soldier on a route the person never joins, after
    the route split (chapter 6 on). Grok: "Leave enemy copies ... if they share a row, do not change that hair
    number" -- a recolour keyed by the person's model row would show on that boss too."""
    p = t.by_pid.get(pid)
    if not p:
        return []
    player = t.rules.get("player_army", "")
    neutral = set(t.rules.get("colour_neutral_belongs", ["BID_その他", "BID_村人"]))
    routes = t.rules.get("routes", {})
    joins = set(t.route_of.get(pid, ()))
    out = []
    for c in t.copies:
        if c["aid"] != p["aid"] or c["belong"] in (player, *neutral) or c["chapter"].endswith("HANDOVER"):
            continue
        ch = c["chapter"]
        if ch[:1] in routes and ch[1:4].isdigit() and int(ch[1:4]) >= 6 and ch[:1] not in joins:
            out.append(c)
    return out


# ------------------------------------------------------------------ the plan
def plan_from(edits: list[dict], facts, look: str = "keep") -> dict:
    """The colour plan from a merged make's edits: the shuffle's spot/filler pairs, and every class each person can
    be in (start class, class line, reclass cells after every module; promotion targets of those classes from the
    final Job rows when the edits carry Job promotion cells)."""
    swaps = sorted({(e["spot"], e["filler"]) for e in edits
                    if e.get("spot") and e.get("filler") and e["spot"] != e["filler"]})
    rows = {p["pid"]: dict(p) for p in facts.persons}
    jobs = {j: dict(r) for j, r in facts.jobs.items()}
    jid_of = {str(r.get("index")): j for j, r in facts.jobs.items()}
    for e in edits:
        if e.get("table") == "Person" and e.get("file", "GameData/GameData.bin.lz").endswith("GameData.bin.lz"):
            if e.get("label") in rows and e.get("cell"):
                rows[e["label"]][e["cell"]] = e["new"]
        if e.get("table") == "Job" and e.get("label") in jobs and e.get("cell"):
            jobs[e["label"]][e["cell"]] = e["new"]

    def jlabel(v):
        v = str(v)
        return v if v.startswith("JID_") else jid_of.get(v)

    classes = {}
    for pid, r in rows.items():
        cs = []
        for cell in ("job", "job_low", "reclass.1", "reclass.2"):
            j = jlabel(r.get(cell, ""))
            if j and j not in cs:
                cs.append(j)
        for j in list(cs):
            jr = jobs.get(j, {})
            for k in ("promote.1", "promote.2", "promotion.1", "promotion.2"):
                pj = jlabel(jr.get(k, ""))
                if pj and pj not in cs:
                    cs.append(pj)
        classes[pid] = cs
    return {"look": look, "swaps": [list(s) for s in swaps], "classes": classes}


def plan_colours(t: ColourTables, plan: dict, opts: dict | None = None) -> tuple[list[dict], list[str]]:
    o = check_opts(opts)
    edits, lines = [], []
    swaps = [tuple(s) for s in plan.get("swaps", []) if s[0] != s[1]]
    if o["recolour"] in ("on", "clear") and swaps and plan.get("look", "keep") == "keep":
        if o["pictures"] == "on":
            lines.append("Recolour (keep the face): each swapped spot wears the new person's hair colour in battle, "
                         "in the portrait and on the map.")
        else:
            lines.append("Recolour (keep the face): each swapped spot wears the new person's hair colour in battle; "
                         "the portrait and the map sprite keep the spot's own pictures.")
        if o["recolour"] == "clear":
            lines.append("Recolour: Easier to see: the battle hair takes a clearer colour of the new person's hue "
                         "(the face data keeps the person's own colour).")
        for spot, filler in sorted(swaps):
            sp, fi = t.by_pid.get(spot), t.by_pid.get(filler)
            if not sp or not fi:
                lines.append(f"  {spot} <- {filler}: not recoloured (person not in this game's tables)")
                continue
            if not t.own_model(sp):
                lines.append(f"  {t.short(spot)} <- {t.short(filler)}: not recoloured (a generic person: the class's "
                             f"soldier model and portrait are shared with every soldier of that class)")
                continue
            src, dst = t.picture_hair(sp), t.picture_hair(fi)
            if src is None or dst is None:
                lines.append(f"  {t.short(spot)} <- {t.short(filler)}: not recoloured (no hair colour)")
                continue
            bosses = boss_copies(t, spot)
            if bosses and o["boss_copies"] == "skip":
                lines.append(f"  {t.short(spot)} <- {t.short(filler)}: not recoloured (shares its model with a boss in "
                             f"{', '.join(sorted({b['chapter'] for b in bosses}))}; Grok's rule 3)")
                continue
            if src == dst:
                lines.append(f"  {t.short(spot)} <- {t.short(filler)}: same hair colour {rgb_hex(dst)} (no change)")
                continue
            battle = clear_hair(src, dst) if o["recolour"] == "clear" else dst
            if battle == dst:
                lines.append(f"  {t.short(spot)} <- {t.short(filler)}: hair {rgb_hex(src)} -> {rgb_hex(dst)}")
            else:
                lines.append(f"  {t.short(spot)} <- {t.short(filler)}: hair {rgb_hex(src)} -> {rgb_hex(dst)}, "
                             f"in battle {rgb_hex(battle)}")
            for rel, r in t.person_rows(sp["aid"]):
                off, v = row_get(r, f"H{HAIR_BIT}")
                if off is None or v == battle:
                    continue
                edits.append({"table": "AssetTable", "file": rel, "header": t.assets[rel]["header"],
                              "record": r["record"], "off": off, "cond": sp["aid"], "field": "hair", "old": v,
                              "new": battle, "spot": spot, "filler": filler, "laid_by": "core_resident"})
            short = t.short(sp["fid"])
            for kind in ("ST", "BU"):
                f = t.face_by_fsid.get(f"FSID_{kind}_{short}")
                if f is None:
                    continue
                new = rgb_to_face(dst, f["color"])
                if new != f["color"]:
                    edits.append({"table": "FaceData", "file": FACE_FILE, "index": f["index"],
                                  "off": f["off"] + FACE_COLOUR, "label": f["fsid"], "field": "colour",
                                  "old": f["color"], "new": new, "spot": spot, "filler": filler,
                                  "count": len(t.faces), "laid_by": "core_resident"})
                if f["package"] and o["pictures"] == "on":
                    edits.append(_tint("portrait", f"face/face/{f['package']}.arc", src, dst, spot, filler))
            ct = f"{short}_ct"
            if ct in t.arcs and o["pictures"] == "on":
                edits.append(_tint("portrait", f"face/face/{ct}.arc", src, dst, spot, filler))
            for path in (t.heads.get(t.short(sp["aid"]), []) if o["pictures"] == "on" else []):
                edits.append(_tint("map_head", path, src, dst, spot, filler))
    elif swaps and plan.get("look") == "full":
        lines.append("Recolour: full identity look, each spot shows the new person's own model (no recolour needed).")

    if o["own_colours"] == "on":
        never = own_colour_cases(t, plan)
        if never:
            lines.append("Own colours in new classes: hair and skin stay the person's own in any class (the game's own "
                         "model rows); a class with no personal outfit shows the army outfit, which tells the side "
                         "(Grok's rule 2).")
            for pid, js in never:
                lines.append(f"  {t.short(pid)}: {', '.join(t.short(j) for j in js)}")
    return edits, lines


def _tint(what: str, path: str, src: int, dst: int, spot: str, filler: str) -> dict:
    return {"table": "Picture", "what": what, "file": path, "from": src, "to": dst, "spot": spot, "filler": filler,
            "laid_by": "core_tint"}


def own_colour_cases(t: ColourTables, plan: dict) -> list[tuple[str, list[str]]]:
    """(PID_, [classes with no personal outfit row]) for each playable person who can be in such a class."""
    out = []
    for pid in sorted(plan.get("classes", {})):
        p = t.by_pid.get(pid)
        if not p or not p.get("aid") or not (t._in_scope(p) or t._is_child(p)):
            continue
        own = t.own_outfit_classes(p["aid"])
        new = [j for j in plan["classes"][pid] if j not in own]
        orig = {p.get("job"), p.get("job_low")}
        none = t.rules.get("colour_none_job_prefix", "JID_無し")
        new = [j for j in new if j not in orig and not j.startswith(none)]
        if new:
            out.append((pid, new))
    return out


# ------------------------------------------------------------------ guards
def run_guards(t: ColourTables, edits: list[dict], plan: dict, opts: dict | None = None) -> dict:
    o = check_opts(opts)
    g = {}

    def put(name, bad):
        g[name] = {"ok": not bad, "detail": bad[:20]}

    # every AssetTable / FaceData cell names the original value the file holds now
    bad = []
    for e in edits:
        if e["table"] == "AssetTable":
            a = t.assets.get(e["file"])
            row = a and next((r for r in a["rows"] if r["record"] == e["record"]), None)
            v = row and next((v for k, off, v in row["fields"] if off == e["off"]), None)
            if v != e["old"] or row["fields"][0][2] != e["cond"]:
                bad.append(f"{e['file']} row {e['record']}: original {v!r} != {e['old']!r}")
            if not (0 <= e["new"] <= 0xFFFFFF):
                bad.append(f"{e['file']} row {e['record']}: colour {e['new']:#x} out of range")
        elif e["table"] == "FaceData":
            f = t.face_by_fsid.get(e["label"])
            if not f or f["color"] != e["old"] or f["off"] + FACE_COLOUR != e["off"]:
                bad.append(f"{e['label']}: original colour does not match")
    put("colour: originals", bad)
    # one writer per cell, and every value plain (never a pointer)
    seen, bad = {}, []
    for e in edits:
        if e["table"] in ("AssetTable", "FaceData"):
            k = (e["file"], e["off"])
            if k in seen and seen[k] != e["new"]:
                bad.append(f"{k}: two values")
            seen[k] = e["new"]
    put("colour: one writer per cell", bad)
    # a swapped spot shows the FILLER's original hair (never a chain: computed from the original tables); with
    # "Easier to see" the clearer colour of it (clear_hair from the spot's own hair)
    bad = []
    for e in edits:
        if e["table"] == "AssetTable":
            want = t.picture_hair(t.by_pid[e["filler"]])
            if o["recolour"] == "clear":
                want = clear_hair(t.picture_hair(t.by_pid[e["spot"]]), want)
            if e["new"] != want:
                bad.append(f"{e['spot']}: {rgb_hex(e['new'])} is not {e['filler']}'s {rgb_hex(want)}")
    put("colour: filler's own colour", bad)
    # only swapped spots are touched, and only in the keep look with recolour on
    spots = {s for s, f in plan.get("swaps", []) if s != f}
    bad = [f"{e.get('spot')}: edited but not a swapped spot" for e in edits if e.get("spot") not in spots]
    if (o["recolour"] == "off" or plan.get("look") == "full") and edits:
        bad.append(f"{len(edits)} edits with recolour off or the full look")
    put("colour: only swapped spots", bad)
    # Grok's rule 3: no edited model row is shared with a boss copy (unless boss_copies=follow)
    bad = []
    if o["boss_copies"] == "skip":
        for e in edits:
            if e["table"] == "AssetTable" and boss_copies(t, e["spot"]):
                bad.append(f"{e['spot']}: shares its model row with a boss")
    put("colour: boss copies untouched", bad)
    # own colours: every person in a class they never had has an own hair row (else the class row's generic
    # soldier hair would show)
    bad = []
    if o["own_colours"] == "on":
        for pid, _js in own_colour_cases(t, plan):
            p = t.by_pid[pid]
            if t.hair_of(p["aid"]) is None and not t.hairless(p["aid"]) and not t.unit_hair(p):
                bad.append(f"{pid}: no own hair colour row")
    put("colour: own hair in new classes", bad)
    return g


# ------------------------------------------------------------------ the in-game patch lines (core hook, COLOURS.md 5)
def patch_lines(edits: list[dict]) -> list[str]:
    """Lines for the fates-rando-patch file, after the existing gamedata/dispos files:
        file asset <romfs path> <header hex>       then  v <data offset> <old 4 bytes> <new 4 bytes>
        file face face/FaceData.bin.lz <records>   then  v ...   (records: the file's count, a guard)
        tint <from RRGGBB> <to RRGGBB> <romfs path>
    Offsets count from the file's data region start (the in-memory "data start", as for gamedata). Each line
    of v counts towards the end line, as today; a tint line counts too."""
    out = []
    by_file = {}
    for e in edits:
        if e["table"] in ("AssetTable", "FaceData"):
            by_file.setdefault((e["table"], e["file"], e.get("header", e.get("count"))), []).append(e)
    for (table, rel, hdr), es in sorted(by_file.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        out.append(f"file asset {rel} {hdr:08X}" if table == "AssetTable" else f"file face {rel} {hdr}")
        for e in sorted(es, key=lambda e: e["off"]):
            out.append(f"v {e['off']:X} {struct.pack('<I', e['old']).hex()} {struct.pack('<I', e['new']).hex()}")
    for e in edits:
        if e["table"] == "Picture":
            out.append(f"tint {e['from'] & 0xFFFFFF:06X} {e['to'] & 0xFFFFFF:06X} {e['file']}")
    return out


# ------------------------------------------------------------------ round 71: the clearer battle hair (Recolour row)
# "Easier to see" (opts recolour="clear"): the battle hair cell gets a clearer colour of the new person's hue, because
# the plain swap was faint in battle (round 59 review: lavender -> blue-grey seen only zoomed). Rule (Grok,
# docs/collab/COLOUR_RULE_GROK.md rules 1 and 4, round-71 consult): in CIE Lab / LCh, the hue is always the new
# person's own; a coloured hair (chroma >= CLEAR_MIN_CHROMA) gets CLEAR_GAIN times the chroma and a lightness inside
# CLEAR_L (darker vanishes in the battle shading), moved at most CLEAR_L_STEP; a grey, white or black hair never
# gains a colour and its lightness moves at most CLEAR_GREY_STEP. Then, if it is still closer than CLEAR_MIN_DE
# (CIE76) to the spot's own hair, the lightness moves away from the spot's hair inside those limits until the
# distance is reached or a limit is hit (two silver heads may stay alike: that is the honest result). Out of the
# sRGB range the chroma is lowered until it fits (hue kept). Never fainter: when the result would be closer to the
# spot's hair than the plain colour, the plain colour stays. Battle hair only: the FaceData colour, portraits and
# map sprites are never touched by this (F-047 recolour scope).
CLEAR_MIN_CHROMA = 12.0
CLEAR_GAIN = 1.35
CLEAR_L = (35.0, 92.0)
CLEAR_L_STEP = 25.0        # a coloured hair's lightness moves at most this far (pale blond never turns brown)
CLEAR_GREY_STEP = 15.0
CLEAR_MIN_DE = 40.0
_D65 = (0.95047, 1.0, 1.08883)


def _lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _unlin(c: float) -> float:
    c = 12.92 * c if c <= 0.0031308 else 1.055 * (max(c, 0.0) ** (1 / 2.4)) - 0.055
    return c * 255.0


def rgb_to_lab(rgb: int) -> tuple[float, float, float]:
    """0xRRGGBB (sRGB, D65) -> CIE L*a*b*."""
    r, g, b = (_lin(float((rgb >> k) & 255)) for k in (16, 8, 0))
    xyz = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b, 0.2126729 * r + 0.7151522 * g + 0.0721750 * b,
           0.0193339 * r + 0.1191920 * g + 0.9503041 * b)
    f = [t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116 for t in (v / w for v, w in zip(xyz, _D65))]
    return 116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])


def lab_to_rgb(lab: tuple[float, float, float]) -> tuple[int, bool]:
    """CIE L*a*b* -> (0xRRGGBB, inside the sRGB range before rounding)."""
    L, a, b = lab
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200

    def inv(t: float) -> float:
        return t ** 3 if t ** 3 > 216 / 24389 else (116 * t - 16) / (24389 / 27)
    x, y, z = (inv(t) * w for t, w in zip((fx, fy, fz), _D65))
    lin = (3.2404542 * x - 1.5371385 * y - 0.4985314 * z, -0.9692660 * x + 1.8760108 * y + 0.0415560 * z,
           0.0556434 * x - 0.2040259 * y + 1.0572252 * z)
    ok = all(-1e-6 <= c <= 1 + 1e-6 for c in lin)
    r, g, bb = (max(0, min(255, int(round(_unlin(c))))) for c in lin)
    return (r << 16) | (g << 8) | bb, ok


def delta_e(c1: int, c2: int) -> float:
    """CIE76 distance between two 0xRRGGBB colours."""
    (l1, a1, b1), (l2, a2, b2) = rgb_to_lab(c1), rgb_to_lab(c2)
    return ((l1 - l2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2) ** 0.5


def _lch_rgb(L: float, C: float, h: float) -> int:
    """LCh -> 0xRRGGBB, the chroma lowered in 0.5 steps until the colour is inside sRGB (hue and lightness kept)."""
    import math
    while True:
        rgb, ok = lab_to_rgb((L, C * math.cos(h), C * math.sin(h)))
        if ok or C <= 0:
            return rgb
        C = max(0.0, C - 0.5)


def clear_hair(src: int, dst: int) -> int:
    """The clearer battle hair for a swapped spot (rule above): `src` = the spot's own hair, `dst` = the new
    person's hair (both 0xRRGGBB). Pure and deterministic; src == dst gives dst."""
    import math
    src, dst = src & 0xFFFFFF, dst & 0xFFFFFF
    if src == dst:
        return dst
    L, a, b = rgb_to_lab(dst)
    C, h = math.hypot(a, b), math.atan2(b, a)
    if C >= CLEAR_MIN_CHROMA:
        C *= CLEAR_GAIN
        L0 = min(CLEAR_L[1], max(CLEAR_L[0], L))
        lo, hi = max(CLEAR_L[0], L0 - CLEAR_L_STEP), min(CLEAR_L[1], L0 + CLEAR_L_STEP)
    else:
        lo, hi = max(0.0, L - CLEAR_GREY_STEP), min(100.0, L + CLEAR_GREY_STEP)
        L0 = L
    best = _lch_rgb(L0, C, h)
    plain = delta_e(src, dst)
    if delta_e(src, best) >= CLEAR_MIN_DE:
        return best if delta_e(src, best) >= plain else dst
    # move the lightness away from the spot's hair, nearest first; the first that reaches the distance wins, else the
    # farthest one inside the limits
    ls = rgb_to_lab(src)[0]
    first = 1.0 if (L0 > ls or (L0 == ls and ls < 50.0)) else -1.0
    far, far_de = best, delta_e(src, best)
    for step in range(1, 101):
        for sign in (first, -first):
            Lt = L0 + sign * step
            if not lo <= Lt <= hi:
                continue
            cand = _lch_rgb(Lt, C, h)
            d = delta_e(src, cand)
            if d >= CLEAR_MIN_DE:
                return cand if d >= plain else dst
            if d > far_de:
                far, far_de = cand, d
    return far if far_de >= plain else dst


# ------------------------------------------------------------------ the picture recolour (reference for the core)
def _lum(r: float, g: float, b: float) -> float:
    return 0.299 * r + 0.587 * g + 0.114 * b


def _hsv(r: int, g: int, b: int) -> tuple[float, float, float]:
    mx, mn = max(r, g, b), min(r, g, b)
    v = mx / 255.0
    s = 0.0 if mx == 0 else (mx - mn) / mx
    if mx == mn:
        h = 0.0
    elif mx == r:
        h = (60.0 * (g - b) / (mx - mn)) % 360.0
    elif mx == g:
        h = 60.0 * (b - r) / (mx - mn) + 120.0
    else:
        h = 60.0 * (r - g) / (mx - mn) + 240.0
    return h, s, v


def _ramp(x: float, full: float, zero: float) -> float:
    """1 at or below `full`, 0 at or above `zero`, linear between."""
    if x <= full:
        return 1.0
    if x >= zero:
        return 0.0
    return (zero - x) / (zero - full)


SKIN = (0.0, 42.0, 0.12, 0.65, 0.25)     # hue from, hue to, saturation from, to, minimum value (skin is kept)


def hair_weight(rgb: tuple[int, int, int], src: int) -> float:
    """How much a pixel looks like the source hair colour (0..1). Coloured hair (saturation >= 0.18): by hue
    distance (full within 18 degrees, none past 34) and a saturation at least 40% of the hair's. Grey, white or
    black hair: by low saturation. Skin-like pixels are never hair unless the hair itself is skin-coloured."""
    r, g, b = rgb
    h, s, v = _hsv(r, g, b)
    sh, ss, sv = _hsv((src >> 16) & 255, (src >> 8) & 255, src & 255)
    t = _lum(r, g, b) / max(_lum((src >> 16) & 255, (src >> 8) & 255, src & 255), 1.0)
    if t < 0.15 or t >= 1.8:
        return 0.0
    bright = _ramp(t, 1.3, 1.8)              # much brighter than the hair: a lit outfit, not hair
    hl, hh, sl, shh, vmin = SKIN
    skin_hair = hl <= sh <= hh and sl <= ss <= shh and sv >= vmin
    if not skin_hair and hl <= h <= hh and sl <= s <= shh and v >= vmin:
        return 0.0
    if ss >= 0.18:
        dh = abs(h - sh) % 360.0
        dh = min(dh, 360.0 - dh)
        return bright * _ramp(dh, 18.0, 34.0) * (1.0 - _ramp(s, 0.25 * ss, 0.45 * ss))
    return bright * _ramp(s, max(0.12, ss + 0.06), max(0.22, ss + 0.14))


def recolour_rgb(rgb: tuple[int, int, int], src: int, dst: int) -> tuple[int, int, int]:
    """One pixel: hair-like pixels (hair_weight) become the destination hair colour at the same brightness ratio
    (t = pixel luminance / hair luminance, so shading stays), blended by the weight; the rest is untouched.
    The same maths in the core (docs/rando/COLOURS.md 5.3); test vectors in tests/test_rando_colours.py."""
    w = hair_weight(rgb, src)
    if w <= 0.0:
        return rgb
    r, g, b = rgb
    sl = max(_lum((src >> 16) & 255, (src >> 8) & 255, src & 255), 1.0)
    t = _lum(r, g, b) / sl
    dr, dg, db = (dst >> 16) & 255, (dst >> 8) & 255, dst & 255
    n = [min(255.0, max(0.0, c * t)) for c in (dr, dg, db)]
    return (round(r + (n[0] - r) * w), round(g + (n[1] - g) * w), round(b + (n[2] - b) * w))


def recolour_rgba(buf: bytes, src: int, dst: int) -> bytes:
    """RGBA8 pixels -> recoloured RGBA8 (alpha kept)."""
    out = bytearray(buf)
    cache = {}
    for i in range(0, len(out), 4):
        if out[i + 3] == 0:
            continue
        k = (out[i], out[i + 1], out[i + 2])
        v = cache.get(k)
        if v is None:
            v = cache[k] = recolour_rgb(k, src, dst)
        out[i], out[i + 1], out[i + 2] = v
    return bytes(out)


# ------------------------------------------------------------------ host tools
def _recruit_plan(t: ColourTables, seed: str, mode: str, game: str) -> dict:
    import recruit as RC
    import sources as SRC
    facts = SRC.tables(game, names=False)
    rt = RC.load_tables(facts=facts)
    redits, _ = RC.plan_recruit(rt, seed, {"recruit": mode, "recruit_look": "keep"})
    return plan_from(redits, facts, "keep")


def facts_report(t: ColourTables) -> dict:
    playable = [p for p in t.persons if p.get("aid")]
    with_hair = [p for p in playable if t.hair_of(p["aid"]) is not None]
    rows_hair = sum(1 for a in t.assets.values() for r in a["rows"] if row_get(r, f"H{HAIR_BIT}")[0] is not None)
    rows_skin = sum(1 for a in t.assets.values() for r in a["rows"] if row_get(r, f"H{SKIN_BIT}")[0] is not None)
    return {"game": t.game, "asset_files": {rel: {"header": f"{a['header']:08X}", "rows": len(a["rows"])}
                                            for rel, a in t.assets.items()},
            "rows_with_hair": rows_hair, "rows_with_skin": rows_skin,
            "main_persons_with_aid": len(playable), "with_own_hair_row": len(with_hair),
            "facedata_records": len(t.faces), "facedata_with_hair_layer": sum(1 for f in t.faces if f["hair"]),
            "map_head_folders": len(t.heads), "chapter_copies": len(t.copies),
            "persons_with_boss_copies": sorted({p["pid"] for p in playable if boss_copies(t, p["pid"])})}


def recolour_file(raw: bytes, rel: str, src: int, dst: int) -> bytes:
    """A whole picture file (face/face/*.arc of LZ BCH members, or unit/Head/*.bch.lz) with every texture
    recoloured, re-encoded in its own format and size. Host side: the in-game proof (a test copy's mods folder)
    and the reference the core's tint hook must match in look (not in bytes: the core recolours decoded pixels)."""
    import arc
    import bch
    import lz

    def one_bch(blob: bytes) -> bytes:
        d, wrapper = bch.unwrap(blob)
        b = bch.Bch(d)
        rep = {}
        for tx in b.textures():
            w, h = tx["dims"][0]
            rgba = bch.decode_level(tx["format"], w, h, b.levels(tx)[0])
            new = recolour_rgba(rgba, src, dst)
            if new != rgba:
                rep[tx["index"]] = bch.encode_texture(tx, new, b.levels(tx))
        return bch.rewrap(bch.inject(d, rep), wrapper, blob) if rep else blob

    if rel.endswith(".arc"):
        members, layout = arc.parse_full(raw)
        for m in members:
            m["data"] = one_bch(m["data"])
        return arc.build(members, layout)
    return one_bch(raw)


def preview(t: ColourTables, spot: str, filler: str, out_dir: str) -> list[str]:
    """Host-side before/after PNGs of the spot's standing portrait (first expression) and one map head with the
    filler's hair colour (build/ only; game pictures are never tracked)."""
    import arc
    import bch
    import tex3ds
    sp, fi = t.by_pid[spot], t.by_pid[filler]
    src, dst = t.picture_hair(sp), t.picture_hair(fi)
    roots = _romfs_roots(t.game)
    os.makedirs(out_dir, exist_ok=True)
    made = []
    st = t.face_by_fsid["FSID_ST_" + t.short(sp["fid"])]
    files = [f"face/face/{st['package']}.arc"]
    files += [p for p in t.heads.get(t.short(sp["aid"]), []) if os.path.basename(p).startswith("青")][:1]
    for rel in files:
        raw = open(_find(roots, rel), "rb").read()
        blobs = [m["data"] for m in arc.parse(raw)][:1] if rel.endswith(".arc") else [raw]
        for blob in blobs:
            d, _w = bch.unwrap(blob)
            b = bch.Bch(d)
            for tx in b.textures()[:1]:
                w, h = tx["dims"][0]
                rgba = bch.decode_level(tx["format"], w, h, b.levels(tx)[0])
                base = os.path.basename(rel).split(".")[0]
                for tag, px in (("before", rgba), ("after", recolour_rgba(rgba, src, dst))):
                    o = os.path.join(out_dir, f"{t.short(spot)}_{base}_{tag}.png")
                    tex3ds.write_png(o, w, h, px)
                    made.append(o)
    return made


def swatch_rows(t: ColourTables, plan: dict) -> list[tuple[str, int, int, int]]:
    """(spot <- filler, spot's own hair, new person's hair, Easier to see colour) for each recoloured swap."""
    out = []
    for spot, filler in sorted(tuple(s) for s in plan.get("swaps", []) if s[0] != s[1]):
        sp, fi = t.by_pid.get(spot), t.by_pid.get(filler)
        if not sp or not fi or not t.own_model(sp):
            continue
        src, dst = t.picture_hair(sp), t.picture_hair(fi)
        if src is None or dst is None or src == dst:
            continue
        out.append((f"{t.short(spot)} <- {t.short(filler)}", src, dst, clear_hair(src, dst)))
    return out


def write_swatch(t: ColourTables, plan: dict, path: str, cell: int = 32) -> str:
    """A PNG (build/ only): one row per swap, three squares: own hair | new hair | Easier to see."""
    import tex3ds
    rows = swatch_rows(t, plan)
    w, h = 3 * cell + 2 * 4, max(1, len(rows)) * (cell + 4)
    px = bytearray(bytes((32, 32, 32, 255)) * (w * h))
    for i, (_name, *cols) in enumerate(rows):
        for j, c in enumerate(cols):
            rgba = bytes(((c >> 16) & 255, (c >> 8) & 255, c & 255, 255))
            for y in range(i * (cell + 4), i * (cell + 4) + cell):
                for x in range(j * (cell + 4), j * (cell + 4) + cell):
                    px[(y * w + x) * 4:(y * w + x) * 4 + 4] = rgba
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tex3ds.write_png(path, w, h, bytes(px))
    with open(os.path.splitext(path)[0] + ".txt", "w", encoding="utf-8", newline="\n") as fh:
        for name, src, dst, clr in rows:
            fh.write(f"{name}: own {rgb_hex(src)}  new {rgb_hex(dst)}  easier to see {rgb_hex(clr)}  "
                     f"(distance {delta_e(src, dst):.0f} -> {delta_e(src, clr):.0f})\n")
    return path


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("facts", "plan", "check", "preview"):
        s = sub.add_parser(n)
        s.add_argument("--game", default="fates")
        if n in ("plan", "check"):
            s.add_argument("--recruit", default="route", choices=("route", "any"))
            s.add_argument("--recolour", default="on", choices=CHOICES["recolour"],
                           help="on = the new person's hair colour (default), clear = Easier to see, off")
        if n == "plan":
            s.add_argument("--seed", required=True)
            s.add_argument("--json")
            s.add_argument("--swatch", help="round 71: a PNG under build/ with one row per swap: the spot's own hair, "
                                            "the new person's hair (on), the Easier to see colour (clear)")
        if n == "check":
            s.add_argument("--seeds", type=int, default=50)
        if n == "preview":
            s.add_argument("--spot", required=True)
            s.add_argument("--filler", required=True)
            s.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    t = load_tables(a.game)
    if a.cmd == "facts":
        print(json.dumps(facts_report(t), ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "plan":
        plan = _recruit_plan(t, a.seed, a.recruit, a.game)
        co = {"recolour": a.recolour}
        edits, lines = plan_colours(t, plan, co)
        g = run_guards(t, edits, plan, co)
        if a.swatch:
            print(f"swatch {write_swatch(t, plan, a.swatch)}")
        print("\n".join(lines))
        print(f"{len(edits)} edits; guards: " + ", ".join(f"{k} {'ok' if v['ok'] else 'FAIL'}" for k, v in g.items()))
        if a.json:
            os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
            json.dump({"plan": plan, "edits": edits, "lines": lines, "guards": g, "patch": patch_lines(edits)},
                      open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return 0 if all(v["ok"] for v in g.values()) else 2
    if a.cmd == "check":
        fails, n_edits = 0, 0
        for i in range(a.seeds):
            plan = _recruit_plan(t, f"colour{i}", a.recruit, a.game)
            co = {"recolour": a.recolour}
            edits, _ = plan_colours(t, plan, co)
            n_edits += len(edits)
            g = run_guards(t, edits, plan, co)
            bad = [k for k, v in g.items() if not v["ok"]]
            if bad:
                fails += 1
                print(f"seed colour{i}: FAIL {bad}")
        print(f"{a.seeds} seeds, {fails} failed, {n_edits} edits in all")
        return 0 if fails == 0 else 2
    if a.cmd == "preview":
        for p in preview(t, a.spot, a.filler, a.out):
            print(p)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
