#!/usr/bin/env python3
"""Fates screen markers from memory reads (docs/ROBOT.md). Standard library only.

A marker run (headless.run(..., markers=True)) has boot.exe dump the guest ranges named in
config/harness/markers.json at every shot frame (ZAKURO_DUMP_MEM + ZAKURO_DUMP_MEM_AT=1). This module walks the
game's process tree in those dumps and names each live process by the class of the functions its vtable points
at (config/functions.csv: names from the game's symbol map, e.g. MainSequence__anonymous_namespace__ProcSequence).
What is kept (run.json "markers"): per frame, the current main-sequence process class (MainSequence::GetCurrent's
walk), and the sorted class names of every live process. No bytes of game memory are kept; the dumps are deleted
with the run's tmp folder.

    python tools/harness/markers.py --selftest      invented memory, no game
    python tools/harness/markers.py RUN             print the markers a finished marker run stored
"""
from __future__ import annotations

import bisect
import csv
import glob
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CONFIG = os.path.join(ROOT, "config", "harness", "markers.json")
FUNCTIONS = os.path.join(ROOT, "config", "functions.csv")
CODE_BIN = os.path.join(ROOT, "extracted", "code.bin")  # the game's code + read-only data (gitignored): vtables
CODE_BASE = 0x00100000
RUNS = os.path.join(ROOT, "build", "harness", "runs")


def load_config(path: str = CONFIG) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def ranges(cfg: dict) -> list[tuple[int, int]]:
    out = [(int(a, 16), int(n)) for a, n in cfg["dump"]]
    if cfg.get("heap"):
        for a, n in cfg["heap"]:
            out.append((int(a, 16), int(n)))
    return out


def dump_env(cfg: dict) -> dict:
    """boot.exe settings: the ranges, dumped at every ZAKURO_DUMP_AT frame."""
    return {"ZAKURO_DUMP_MEM": ";".join(f"0x{a:08X},{n}" for a, n in ranges(cfg)), "ZAKURO_DUMP_MEM_AT": "1"}


class Memory:
    """Guest memory made of dumped ranges; a read outside them returns None."""

    def __init__(self, parts: list[tuple[int, bytes]], code: bytes | None = None):
        self.parts = sorted(parts)
        if code is not None:  # after the dumps: a dumped static wins over code.bin's initial value
            self.parts.append((CODE_BASE, code))

    def u32(self, addr: int) -> int | None:
        for base, data in self.parts:
            if base <= addr and addr + 4 <= base + len(data):
                return struct.unpack_from("<I", data, addr - base)[0]
        return None

    def u8(self, addr: int) -> int | None:
        for base, data in self.parts:
            if base <= addr < base + len(data):
                return data[addr - base]
        return None


_CODE: list[bytes] = []


def code_bin() -> bytes | None:
    if not _CODE and os.path.isfile(CODE_BIN):
        with open(CODE_BIN, "rb") as fh:
            _CODE.append(fh.read())
    return _CODE[0] if _CODE else None


def load_dumps(tmp_dir: str, frame: int) -> Memory:
    parts = []
    for p in glob.glob(os.path.join(tmp_dir, f"zakuro-dump-0x*-{frame}.bin")):
        m = re.search(r"zakuro-dump-0x([0-9A-Fa-f]{8})-(\d+)\.bin$", p)
        if m and int(m.group(2)) == frame:
            with open(p, "rb") as fh:
                parts.append((int(m.group(1), 16), fh.read()))
    return Memory(parts, code_bin() if parts else None)


class Names:
    """Function start -> name, from config/functions.csv."""

    def __init__(self, rows: list[tuple[int, str]] | None = None):
        if rows is None:
            rows = []
            with open(FUNCTIONS, encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    rows.append((int(r["addr"], 16), r["name"]))
        rows.sort()
        self.addrs = [a for a, _ in rows]
        self.names = [n for _, n in rows]

    def at(self, addr: int) -> str | None:
        a = addr & ~1  # a Thumb entry has bit 0 set
        i = bisect.bisect_left(self.addrs, a)
        return self.names[i] if i < len(self.addrs) and self.addrs[i] == a else None


def class_of(name: str) -> str | None:
    """Class__Method -> Class; func_XXXXXXXX and plain names have none."""
    if name.startswith("func_") or "__" not in name:
        return None
    return name.rsplit("__", 1)[0]


def vtable_class(mem: Memory, names: Names, vt: int, words: int) -> str:
    """The class of the vtable: its destructors' class first (entries 0-1), else the class most of its other named
    entries belong to; ProcInst's own methods count least (a subclass inherits Tick, Dispose...)."""
    votes: dict[str, int] = {}
    for i in range(words):
        f = mem.u32(vt + 4 * i)
        if f is None:
            break
        n = names.at(f)
        c = class_of(n) if n else None
        if c:
            votes[c] = votes.get(c, 0) + (1 if c in ("ProcInst", "Proc") else 100 if "__dtor_" in n else 10)
    if not votes:
        return f"vtable_{vt:08X}"
    best = max(sorted(votes), key=lambda c: votes[c])
    # a class in a file-local namespace only (several files have their own anonymous ProcSequence): add the vtable
    return f"{best}@{vt:08X}" if best.startswith("anonymous_namespace__") else best


def walk(mem: Memory, names: Names, cfg: dict) -> dict:
    p = cfg["proc"]
    off = {k: int(p[k]) for k in ("parent", "child", "sibling", "flags", "current", "hash")}
    words = int(p.get("vtable_words", 5))
    roots_at, count = int(p["roots"], 16), int(p["root_count"])
    seen: set[int] = set()
    procs: list[dict] = []
    cache: dict[int, str] = {}

    def cls(inst: int) -> str:
        vt = mem.u32(inst)
        if vt is None:
            return "unreadable"
        if vt not in cache:
            cache[vt] = vtable_class(mem, names, vt, words)
        return cache[vt]

    def visit(inst: int, depth: int, root: int) -> None:
        while inst and inst not in seen and len(seen) < 4096:
            seen.add(inst)
            flags = mem.u8(inst + off["flags"])
            if flags is None:
                procs.append({"root": root, "depth": depth, "class": "unreadable"})
                return
            procs.append({"root": root, "depth": depth, "class": cls(inst), "dying": bool(flags & 1),
                          "current": bool(mem.u8(inst + off["current"]))})
            child = mem.u32(inst + off["child"])
            if child:
                visit(child, depth + 1, root)
            inst = mem.u32(inst + off["sibling"]) or 0

    for r in range(count):
        head = mem.u32(roots_at + 4 * r)
        if head:
            visit(head, 0, r)
    # MainSequence::GetCurrent
    current = None
    inst = mem.u32(int(p["main_sequence"], 16))
    if inst:
        node, guard = inst, 0
        child = mem.u32(node + off["child"])
        while child and guard < 256:
            guard += 1
            node, c = child, mem.u32(child + off["sibling"])
            while c and guard < 256:
                guard += 1
                if mem.u8(c + off["current"]):
                    node = c
                c = mem.u32(c + off["sibling"])
            child = mem.u32(node + off["child"])
        current = cls(node)
    live = sorted({x["class"] for x in procs if not x.get("dying")})
    return {"main_sequence": cls(inst) if inst else None, "current": current, "procs": len(procs),
            "classes": live, "unreadable": sum(1 for x in procs if x["class"] in ("unreadable",)) +
            sum(1 for x in procs if x["class"].startswith("vtable_"))}


# round 9: the current chapter, read the way the game's own script call ChapterGetName (0x003A92E8) reads it:
# GameUserData::Get() (0x001B3AFC: *0x006DA248) -> +0xC the current chapter's data row (0 = none; ChapterIsCID
# 0x003A7F44 compares the same word) -> +0 a pointer to its id string "CID_xxxx"; ChapterGetName returns the text after
# the four-character prefix ("NONE" when there is no chapter). Kept as "chapter": "B006"; no other bytes.
# Which routes a chapter id belongs to (docs/ROUTES.md: route_mask 1 = CID_A (Birthright, route byte 0), 2 = CID_B
# (Conquest, 1), 4 = CID_C (Revelation, 2); X007-X014 Birthright and Revelation, X015-X022 Conquest and Revelation).
GUD_CHAPTER = "0xC"  # default when markers.json "state" has no gud_chapter (that file is shared; not edited here)


def chapter_routes(cid: str | None) -> list[str] | None:
    """The route families a chapter id is on: ["bt"], ["cq"], ["rv"], two for the X chapters, [] for the shared ones."""
    if not cid:
        return None
    m = re.fullmatch(r"([ABCX])(\d{3})", cid)
    if not m:
        return []
    letter, n = m.group(1), int(m.group(2))
    if letter == "X":
        return ["bt", "rv"] if 7 <= n <= 14 else ["cq", "rv"] if 15 <= n <= 22 else []
    if n < 6:  # A000-A005: the shared prologue (route_mask 7)
        return []
    return [{"A": "bt", "B": "cq", "C": "rv"}[letter]]


def read_cstr(mem: Memory, addr: int, limit: int = 24) -> str | None:
    out = []
    for i in range(limit):
        b = mem.u8(addr + i)
        if b is None:
            return None
        if b == 0:
            return "".join(out)
        if not 0x20 < b < 0x7F:
            return None
        out.append(chr(b))
    return None


def chapter_id(mem: Memory, gud: int, st: dict) -> str | None:
    row = mem.u32(gud + int(st.get("gud_chapter", GUD_CHAPTER), 16))
    if row is None:
        return None
    if row == 0:
        return "NONE"
    sp = mem.u32(row)
    s = read_cstr(mem, sp) if sp else None
    if not s or len(s) <= 4:
        return None
    return s[4:]


def game_state(mem: Memory, cfg: dict) -> dict | None:
    """A few named facts read through the game's own globals (config/harness/markers.json "state"): the
    difficulty, death-rule and route bytes of GameUserData, the player/enemy unit counts, the paired units
    (Unit.state_flags bit 1 lead, bit 2 partner) and the dragon veins (TrickData type 11, state bit 0 usable).
    Only these numbers are kept, no memory bytes."""
    st = cfg.get("state")
    if not st:
        return None
    out: dict = {}
    gud = mem.u32(int(st["game_user_data"], 16))
    if gud:
        flags = mem.u32(gud + int(st["gud_mode_flags"], 16))
        diff, route = mem.u8(gud + int(st["gud_difficulty"], 16)), mem.u8(gud + int(st["gud_route"], 16))
        if flags is not None and diff is not None and route is not None:
            out.update(difficulty=diff, route=route, casual=bool(flags & 4), phoenix=bool(flags & 8))
        cid = chapter_id(mem, gud, st)
        if cid is not None:
            out.update(chapter=cid, chapter_routes=chapter_routes(cid))
        if st.get("gud_gold"):  # anonymous_namespace::GoldGet 0x003B0660: GameUserData::Get()->+0x38
            gold = mem.u32(gud + int(st["gud_gold"], 16))
            if gold is not None:
                out["gold"] = gold
    pool = mem.u32(int(st["unit_pool"], 16) + 4)  # UnitPool.forces
    u = st["unit"]
    if pool:
        counts, paired = [], []
        for force in range(3):
            n, unit = 0, mem.u32(pool + 12 * force)
            while unit and n < 256:
                n += 1
                flags = mem.u32(unit + int(u["state_flags"], 16))
                if flags is not None and flags & 6:
                    paired.append({"force": force, "x": mem.u8(unit + int(u["map_x"], 16)),
                                   "y": mem.u8(unit + int(u["map_y"], 16)), "role": "lead" if flags & 2 else "partner"})
                unit = mem.u32(unit + int(u["next"], 16))
            counts.append(n)
        out.update(units=counts, paired=paired, paired_player=sum(1 for x in paired if x["force"] == 0))
    sup = st.get("support")
    if sup and pool:  # support (Reliance) points between force-0 units, by the game's own tables
        rows = support_list(mem, sup, pool)
        if rows is not None:
            out.update(support_pairs=len(rows), support_c=sum(1 for x in rows if x["points"] >= x["thresholds"][0]),
                       support_points_max=max([x["points"] for x in rows] or [0]), supports=supports_by_pair(rows))
    if st.get("levels") and pool:  # round 4: level, experience and stats of every force-0 unit
        lv = unit_levels(mem, st["levels"], pool)
        if lv:
            out["levels"] = lv
    if st.get("forge") and pool:  # round 4: forged weapons (unit::Item refine rank) in unit items and the convoy
        weapons = weapon_items(mem, st["forge"], pool)
        if weapons is not None:
            fg = [x for x in weapons if x["rank"]]
            groups: dict = {}
            for x in weapons:  # the smithy fuses two like weapons (same item, same rank) of one holder
                key = (x["where"], x["item"], x["rank"])
                groups[key] = groups.get(key, 0) + x.get("count", 1)
            out.update(forged=fg, forge_max=max([x["rank"] for x in fg] or [0]),
                       forge_pairs=sum(1 for v in groups.values() if v >= 2))
    if st.get("castle"):  # round 4: the castle's ore and food stock
        res = castle_stock(mem, st["castle"])
        if res is not None:
            out.update(res)
    if st.get("game_config"):  # round 7: the options block, to prove an options-screen visit changed nothing
        gc = game_config(mem, st["game_config"])
        if gc is not None:
            out["game_config"] = gc
    trick = mem.u32(int(st["trick"], 16))
    if trick:
        veins, used, node, n = 0, 0, mem.u32(trick), 0
        while node and n < 512:
            n += 1
            if mem.u8(node + 0xC) == 11:
                veins += 1
                state = mem.u8(node + 0x16)
                used += 1 if state is not None and not state & 1 else 0
            node = mem.u32(node)
        out.update(veins=veins, veins_used=used)
    return out


def game_config(mem: Memory, c: dict) -> str | None:
    """The options block (docs/MENUS.md 1): G_GameConfig 0x006DA0F8 -> GameConfigData; the bytes +0x4 .. +0x16 that
    GameConfigData::Serialize saves (the on/off word, battle animations, camera, speed, AI skip, danger, volumes, battle
    music, HP bars), as one hex string. Only these 19 option bytes are kept."""
    obj = mem.u32(int(c["pointer"], 16))
    if not obj:
        return None
    first, last = int(c["first"], 16), int(c["last"], 16)
    vals = [mem.u8(obj + i) for i in range(first, last + 1)]
    return None if None in vals else bytes(vals).hex()


def _u16(mem: Memory, a: int) -> int | None:
    lo, hi = mem.u8(a), mem.u8(a + 1)
    return None if lo is None or hi is None else lo | hi << 8


def _s8(v: int | None) -> int | None:
    return None if v is None else v - 256 if v > 127 else v


def unit_levels(mem: Memory, lv: dict, pool: int) -> dict:
    """{"<person id>": {"lv", "exp", "gain", "stats"}} for every unit of the configured forces (0, 3). Unit +0xF1 level (Unit::GetShowLevel
    0x0052DC44; Unit::LevelUp 0x003D8154 adds 1), +0xF2 experience (Unit::ExpNormalize 0x0052D34C), +0xC8 s8[8]
    per-stat gains (Unit::LevelUp adds to +0xC8[s]); stats = Person.base (+0x38) + Job.base (+0x1C) + gain, the raw
    stat of Unit::GetStrImpl and its kin before the class cap and before the avatar's boon/bane edit (docs/TABLES.md).
    Person +0x24 u16 id (Unit +0x9C person, +0xA0 job). Numbers only.
    Two units with one person id (Grok review 4, low #2: the second overwrote the first): the first in the
    forces' order keeps the bare id ("6"), the next ones are "6#2", "6#3", so a checkpoint's "levels.6.lv" still
    names the first and levelups.py compares each of them (in the pool's order, which a join or a death can shift:
    a level-up is then seen on the key, not proven on the same unit)."""
    h = lambda k: int(lv[k], 16)
    out = {}
    for unit in force_units(mem, pool, lv.get("forces", [0])):
        per, job = mem.u32(unit + h("unit_person")), mem.u32(unit + h("unit_job"))
        pid = _u16(mem, per + h("person_id")) if per else None
        level, exp = mem.u8(unit + h("unit_level")), mem.u8(unit + h("unit_exp"))
        gain = [_s8(mem.u8(unit + h("unit_gain") + s)) for s in range(8)]
        pb = [_s8(mem.u8(per + h("person_base") + s)) for s in range(8)] if per else [None] * 8
        jb = [_s8(mem.u8(job + h("job_base") + s)) for s in range(8)] if job else [None] * 8
        if pid is not None and level is not None and None not in gain + pb + jb:
            key, k = str(pid), 1
            while key in out:
                k += 1
                key = f"{pid}#{k}"
            out[key] = {"lv": level, "exp": exp, "gain": gain,
                        "stats": [a + b + c for a, b, c in zip(pb, jb, gain)]}
    return out


def force_units(mem: Memory, pool: int, forces: list[int]) -> list[int]:
    """The units of the given forces (UnitPool.forces + 12 * force, +0 first unit, Unit +0x14 next). Force 0 is the
    army on a map; in My Castle the army is listed under force 3 (seen in a castle dump: force 0 empty)."""
    out = []
    for force in forces:
        unit, n = mem.u32(pool + 12 * force), 0
        while unit and n < 256:
            n += 1
            out.append(unit)
            unit = mem.u32(unit + 0x14)
    return out


def item_is_weapon(mem: Memory, fg: dict, index: int) -> bool | None:
    """Item::IsWeapon 0x00529164 on Item::Get(index) 0x003D0EAC: the item data blocks hang from *0x006D38D0 (node +0
    header, +8 next; header +0x1C first index u16, +6 count u16; record = header + 8 + 0x68 * (index - first),
    falling back to record 0 of the first block); record +0x1A s8 sub-kind; ItemSubKind::Get 0x0019B97C =
    *(0x006D3950 + 4) + 16 * sub-kind; its +1 s8 kind is not a weapon when 6 or 8."""
    node, rec, n = mem.u32(int(fg["item_table"], 16)), None, 0
    first = node
    while node and n < 64:
        n += 1
        hdr = mem.u32(node)
        base, count = (_u16(mem, hdr + 0x1C), _u16(mem, hdr + 6)) if hdr else (None, None)
        if base is None or count is None:
            return None
        if base <= index < base + count:
            rec = hdr + 8 + 0x68 * (index - base)
            break
        node = mem.u32(node + 8)
    if rec is None:
        hdr = mem.u32(first) if first else None
        if not hdr:
            return None
        rec = hdr + 8
    sub = _s8(mem.u8(rec + int(fg["item_subkind"], 16)))
    table = mem.u32(int(fg["subkind_table"], 16))
    kind = _s8(mem.u8(table + 16 * sub + 1)) if table and sub is not None else None
    return None if kind is None else kind not in (6, 8)


def weapon_items(mem: Memory, fg: dict, pool: int) -> list[dict] | None:
    """Every weapon held by the configured forces or in the convoy, with its refine (forge) rank: unit::Item is u16 index + u16 bits, rank = bits 8..13 for a
    weapon (unit::Item::GetRefineRank 0x0053B278 / SetRefineRank 0x0041978C; for other items those bits are the
    uses). Unit items: five unit::Item at Unit +0x108 (Unit::GetHasItemNum 0x0052E594); convoy: *0x006D95E8, 500
    entries of 8 bytes, +0 unit::Item, +4 count (Transporter::Get 0x001A744C, GetExistNum 0x001A6E70).
    [{"where": "<person id>" | "convoy", "item": index, "rank": r (, "count": n in the convoy)}]; None when the
    item tables cannot be read. game_state keeps those with rank > 0 ("forged") and counts like pairs."""
    if not mem.u32(int(fg["item_table"], 16)) or not mem.u32(int(fg["subkind_table"], 16)):
        return None
    out = []

    def look(where: str, at: int) -> None:
        idx, bits = _u16(mem, at), _u16(mem, at + 2)
        if idx and bits is not None and item_is_weapon(mem, fg, idx):
            out.append({"where": where, "item": idx, "rank": (bits >> 8) & 0x3F})
    for unit in force_units(mem, pool, fg.get("forces", [0])):
        per = mem.u32(unit + 0x9C)
        pid = _u16(mem, per + 0x24) if per else None
        for i in range(int(fg["unit_item_count"])):
            look(str(pid), unit + int(fg["unit_items"], 16) + 4 * i)
    conv = mem.u32(int(fg["convoy"], 16))
    if conv:
        for i in range(int(fg["convoy_count"])):
            cnt = mem.u32(conv + 8 * i + 4)
            if cnt:
                look("convoy", conv + 8 * i)
                if out and out[-1]["where"] == "convoy" and "count" not in out[-1]:
                    out[-1]["count"] = cnt
    return out


def castle_stock(mem: Memory, c: dict) -> dict | None:
    """Ore and food counts of My Castle: Castle::Get 0x0044544C = *0x006D1998, +8 -> CastleUserData;
    castle::CastleUserData::GetGemstoneNum 0x00540AD4 = byte [type] of *(+0xD4), GetFoodNum 0x00540A3C = byte [type]
    of *(+0xD8); the type counts are castle::Gemstone::GetNum 0x00497520 = **(*0x006D1F50 + 4) and castle::Food::GetNum
    0x0048BE28 = **(*0x006D1F18 + 4) (both from the castle's own tables). {"ore": [...], "food": [...]}."""
    cas = mem.u32(int(c["castle"], 16))
    cud = mem.u32(cas + int(c["user_data"], 16)) if cas else None
    cud = mem.u32(cud) if cud else None
    if not cud:
        return None
    out = {}
    for key, arr, kinds in (("ore", "gem", "gem_types"), ("food", "food", "food_types")):
        t = mem.u32(int(c[kinds], 16) + 4)
        n = mem.u32(t) if t else None
        base = mem.u32(cud + int(c[arr], 16))
        if n is None or not base or n > 64:
            continue
        vals = [mem.u8(base + i) for i in range(n)]
        if None not in vals:
            out[key] = vals
    return out or None


# Person+0x24 ids of the playable army as docs/ROBOT.md names them (levelups.py's list); others print as "id N"
PERSON_NAMES = {1: "Corrin", 4: "Felicia", 6: "Rinkah", 7: "Kaze", 8: "Sakura", 9: "Azura", 10: "Hana", 11: "Subaki",
                12: "Silas", 13: "Saizo", 16: "Asama"}
RANKS = "CBAS"


def person_name(pid: int) -> str:
    return PERSON_NAMES.get(pid, f"id {pid}")


def support_ready(points: int, thresholds: list) -> tuple[str, int | None]:
    """The highest rank whose threshold the points reach ("-" for none) and the threshold of the next rank (None at S
    or when unread). Points ready for a rank, not the conversation seen: the game raises the rank at the talk."""
    ready, nxt = "-", None
    for letter, t in zip(RANKS, thresholds):
        if t is None:
            break
        if points >= t:
            ready = letter
        else:
            nxt = t
            break
    return ready, nxt


def support_list(mem: Memory, sup: dict, pool: int) -> list[dict] | None:
    """support_pairs with names: one dict per pair {"a", "b" (Person+0x24 ids, a < b in pool order), "points",
    "thresholds" [C, B, A, S], "ready" (highest rank the points reach), "next" (points for the next rank)}."""
    rows = _support_rows(mem, sup, pool)
    if rows is None:
        return None
    out = []
    for a, b, pts, th in rows:
        ready, nxt = support_ready(pts, th)
        out.append({"a": a, "b": b, "points": pts, "thresholds": th, "ready": ready, "next": nxt})
    return out


def supports_by_pair(rows: list[dict]) -> dict:
    """game_state's "supports": {"<id a>-<id b>": {"points", "ready", "next"}} with the smaller id first, so a
    checkpoint can name one pair: "supports.7-10.ready": "A" (Kaze-Hana), "supports.4-13.points" (Felicia-Saizo)."""
    out = {}
    for r in rows:
        lo, hi = sorted((r["a"], r["b"]))
        out[f"{lo}-{hi}"] = {"points": r["points"], "ready": r["ready"], "next": r["next"]}
    return out


def support_pairs(mem: Memory, sup: dict, pool: int) -> list[tuple[int, int]] | None:
    """(points, C threshold) of every pair (support_list's rows), the numbers the round-4 checkpoints use."""
    rows = _support_rows(mem, sup, pool)
    if rows is None:
        return None
    return [(pts, th[0]) for _a, _b, pts, th in rows]


def _support_rows(mem: Memory, sup: dict, pool: int) -> list[tuple] | None:
    """(id a, id b, points, [C, B, A, S thresholds]) for every pair of force-0 units that has a support. Unit.person +0x9C;
    Person +48 int16 support row (-1: none), +36 uint16 id; *G_Reliance (0x006D3BD0, Reliance::GetFromPerson
    0x004F0FDC) is a table of buckets by row & 127, each node -> record: +0 row, +2 count, then 12-byte
    entries (+0 partner id, +2 slot, +4..+7 C/B/A/S thresholds, Reliance::GetLevel 0x00546878); the points
    are byte [slot] of Unit +0x11C (Unit::GetReliance 0x0052C260)."""
    u16 = lambda a: (None if mem.u8(a) is None or mem.u8(a + 1) is None else mem.u8(a) | mem.u8(a + 1) << 8)
    table = mem.u32(int(sup["table"], 16))
    if not table:
        return None
    units, unit, n = [], mem.u32(pool), 0
    while unit and n < 256:
        n += 1
        per = mem.u32(unit + int(sup["unit_person"], 16))
        if per:
            units.append((unit, per))
        unit = mem.u32(unit + 0x14)
    out = []
    for ua, pa in units:
        row = u16(pa + int(sup["person_row"], 16))
        if row is None or row >= 0x8000:
            continue
        node, rec, hops = mem.u32(table + 4 * (row & 127)), None, 0
        while node and hops < 64:
            hops += 1
            r = mem.u32(node)
            if r and u16(r) == row:
                rec = r
                break
            node = mem.u32(node + 4)
        if rec is None:
            continue
        count = u16(rec + 2) or 0
        pts_base = mem.u32(ua + int(sup["unit_points"], 16))
        for ub, pb in units:
            if ub <= ua:
                continue
            want = u16(pb + int(sup["person_id"], 16))
            for i in range(min(count, 64)):
                e = rec + 4 + 12 * i
                if u16(e) == want:
                    slot, c = u16(e + 2), mem.u8(e + 4)
                    pts = mem.u8(pts_base + slot) if pts_base and slot is not None else None
                    if pts is not None and c is not None:
                        out.append((u16(pa + int(sup["person_id"], 16)), want, pts,
                                    [c] + [mem.u8(e + 5 + k) for k in range(3)]))
                    break
    return out


def frame_markers(tmp_dir: str, frames: list[int], cfg: dict | None = None, names: Names | None = None) -> dict:
    cfg = cfg or load_config()
    names = names or Names()
    out = {}
    for f in frames:
        mem = load_dumps(tmp_dir, f)
        if not mem.parts:
            out[str(f)] = None
            continue
        out[str(f)] = walk(mem, names, cfg)
        state = game_state(mem, cfg)
        if state is not None:
            out[str(f)]["state"] = state
    return out


def check(markers: dict, want: dict) -> list[str]:
    """want: {"frame": {"current": "...", "classes": [...]}}; the problems (empty: all met)."""
    bad = []
    for f, w in want.items():
        if f.startswith("_"):
            continue
        got = markers.get(str(f))
        if not got:
            bad.append(f"frame {f}: no markers")
            continue
        if w.get("current") and got.get("current") != w["current"]:
            bad.append(f"frame {f}: current {got.get('current')}, want {w['current']}")
        for c in w.get("classes", []):
            if c not in got.get("classes", []):
                bad.append(f"frame {f}: no live {c}")
        for k, v in w.get("state", {}).items():  # exact value, or "min:N" for at least N (a list's length)
            have = (got.get("state") or {}).get(k)
            if have is None and "." in k:  # "levels.<id>.lv": a path into a nested read
                have = got.get("state") or {}
                for part in k.split("."):
                    have = have.get(part) if isinstance(have, dict) else None
            have_n = len(have) if isinstance(have, list) else have
            if isinstance(v, str) and v.startswith("min:"):
                if have_n is None or have_n < int(v[4:]):
                    bad.append(f"frame {f}: state {k} {have_n}, want at least {v[4:]}")
            elif have != v:
                bad.append(f"frame {f}: state {k} {have}, want {v}")
    return bad


# ------------------------------------------------------------------ self-test (no game)
def selftest() -> tuple[list[str], str]:
    errors: list[str] = []
    checks = 0

    def ok(cond: bool, what: str) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            errors.append(f"markers: {what}")

    names = Names([(0x00100000, "ProcInst__Tick"), (0x00100100, "title__ProcTitle__Begin"),
                   (0x00100200, "title__ProcTitle__End"), (0x00100300, "MainSequence__anonymous_namespace__ProcSequence__Persistent"),
                   (0x00100400, "func_00100400"), (0x00100500, "Game__ProcMap__Tick")])
    cfg = {"proc": {"roots": "0x00700000", "root_count": 3, "main_sequence": "0x00700100", "parent": 16, "child": 20,
                    "sibling": 28, "flags": 40, "current": 41, "hash": 44, "vtable_words": 3}, "dump": []}
    heap = bytearray(0x1000)
    base = 0x08000000

    def proc(at: int, vt: int, parent=0, child=0, sib=0, flags=0, cur=0) -> None:
        struct.pack_into("<IIIIIIII", heap, at, vt, 0, 0, 0, parent, child, 0, sib)
        heap[at + 40], heap[at + 41] = flags, cur

    vts = {0x800: (0x00100000, 0x00100300, 0x00100400), 0x820: (0x00100000, 0x00100100, 0x00100201),
           0x840: (0x00100500, 0x00100000, 0)}
    for at, ents in vts.items():
        struct.pack_into("<III", heap, at, *ents)
    seq, ttl, mp, dead = base + 0x100, base + 0x200, base + 0x300, base + 0x400
    proc(0x100, base + 0x800, child=ttl)
    proc(0x200, base + 0x820, parent=seq, sib=mp, cur=0)
    proc(0x300, base + 0x840, parent=seq, sib=dead, cur=1)
    proc(0x400, base + 0x820, parent=seq, flags=1, cur=0)
    static = bytearray(0x200)
    struct.pack_into("<III", static, 0, seq, 0, 0)
    struct.pack_into("<I", static, 0x100, seq)
    mem = Memory([(0x00700000, bytes(static)), (base, bytes(heap))])
    m = walk(mem, names, cfg)
    ok(m["main_sequence"] == "MainSequence__anonymous_namespace__ProcSequence", f"main sequence class ({m['main_sequence']})")
    ok(m["current"] == "Game__ProcMap", f"GetCurrent takes the last child with +41 set ({m['current']})")
    ok(m["procs"] == 4 and m["classes"] == ["Game__ProcMap", "MainSequence__anonymous_namespace__ProcSequence",
                                            "title__ProcTitle"], f"tree walk and dying flag ({m})")
    struct.pack_into("<I", heap, 0x41C, ttl)  # a loop: dead's sibling is ttl again
    m2 = walk(Memory([(0x00700000, bytes(static)), (base, bytes(heap))]), names, cfg)
    ok(m2["procs"] == 4, "a sibling loop is walked once")
    ok(class_of("SceneSystem__Load_001A3AB0") == "SceneSystem" and class_of("func_00100000") is None
       and class_of("A__B__dtor_B") == "A__B", "class names from function names")
    names2 = Names([(0x00100000, "anonymous_namespace__ProcSequence__dtor_ProcSequence")])
    m3 = Memory([(0x00600000, struct.pack("<I", 0x00100000))])
    ok(vtable_class(m3, names2, 0x00600000, 1) == "anonymous_namespace__ProcSequence@00600000",
       "a file-local class is told apart by its vtable")
    ok(names.at(0x00100201) == "title__ProcTitle__End", "a Thumb entry (bit 0) is named")
    ok(Memory([(0x10, b"\x01\x02\x03")]).u32(0x10) is None, "a read past a dump is None")
    ok(check({"5": m}, {"5": {"current": "Game__ProcMap", "classes": ["title__ProcTitle"]}}) == [], "check passes")
    ok(len(check({"5": m}, {"5": {"current": "x"}, "6": {}})) == 2, "check names a wrong current and a missing frame")
    env = dump_env({"dump": [["0x006D88D4", 4]], "heap": [["0x08000000", 16]]})
    ok(env["ZAKURO_DUMP_MEM"] == "0x006D88D4,4;0x08000000,16" and env["ZAKURO_DUMP_MEM_AT"] == "1", "dump settings")
    ok(load_config()["proc"]["roots"] == "0x00752B48", "config/harness/markers.json reads")
    # game_state on invented memory: GameUserData, two forces with a paired couple, two veins (one used)
    cfg = load_config()
    st = cfg["state"]
    g = bytearray(0x40)
    g[0x2D], g[0x2E] = 0, 0
    struct.pack_into("<I", g, 0x28, 4)
    struct.pack_into("<I", g, 0x38, 4700)  # gold
    heap = bytearray(0x2000)
    H = 0x31000000
    def unit(at, x, y, flags, nxt):
        struct.pack_into("<I", heap, at + 8, flags)
        struct.pack_into("<I", heap, at + 0x14, nxt)
        heap[at + 0xF4], heap[at + 0xF5] = x, y
    unit(0x100, 3, 4, 2, H + 0x300)
    unit(0x300, 3, 4, 4, 0)
    unit(0x500, 9, 9, 0x100, 0)
    struct.pack_into("<III", heap, 0x1000, H + 0x100, 0, 0)          # force 0
    struct.pack_into("<III", heap, 0x100C, H + 0x500, 0, 1)          # force 1
    struct.pack_into("<II", heap, 0x1100, H + 0x1200, 2)             # Trick: first, count
    struct.pack_into("<I", heap, 0x1200, H + 0x1240); heap[0x120C], heap[0x1216] = 11, 2
    struct.pack_into("<I", heap, 0x1240, 0); heap[0x124C], heap[0x1256] = 11, 1
    statics = [(int(st["game_user_data"], 16), struct.pack("<I", H + 0x1800)),
               (int(st["unit_pool"], 16), struct.pack("<II", 0, H + 0x1000)),
               (int(st["trick"], 16), struct.pack("<I", H + 0x1100))]
    heap[0x1800:0x1840] = g
    gs = game_state(Memory(statics + [(H, bytes(heap))]), cfg)
    ok(gs.pop("chapter", None) == "NONE" and gs.pop("chapter_routes", 1) == [], "no chapter row: chapter NONE")
    ok(gs == {"difficulty": 0, "route": 0, "casual": True, "phoenix": False, "gold": 4700, "units": [2, 1, 0],
              "paired": [{"force": 0, "x": 3, "y": 4, "role": "lead"}, {"force": 0, "x": 3, "y": 4, "role": "partner"}],
              "paired_player": 2, "veins": 2, "veins_used": 1}, f"game_state reads the bytes, pairs and veins ({gs})")
    m2 = dict(m, state=gs)
    ok(check({"5": m2}, {"5": {"state": {"route": 0, "paired": "min:2", "veins_used": "min:1"}}}) == [], "state check passes")
    ok(len(check({"5": m2}, {"5": {"state": {"route": 1, "veins_used": "min:2"}}})) == 2, "state check names wrong values")
    # round 9: the chapter id through GameUserData +0xC -> row -> "CID_B007"
    for cid_text, want, fams in ((b"CID_B007\0", "B007", ["cq"]), (b"CID_C007\0", "C007", ["rv"]),
                                 (b"CID_A010\0", "A010", ["bt"]), (b"CID_X015\0", "X015", ["cq", "rv"]),
                                 (b"CID_A003\0", "A003", [])):
        hc = bytearray(heap)
        struct.pack_into("<I", hc, 0x1800 + 0xC, H + 0x1900)        # GameUserData +0xC: the chapter row
        struct.pack_into("<I", hc, 0x1900, H + 0x1A00)              # row +0: the id string
        hc[0x1A00:0x1A00 + len(cid_text)] = cid_text
        gc = game_state(Memory(statics + [(H, bytes(hc))]), cfg)
        ok(gc.get("chapter") == want and gc.get("chapter_routes") == fams,
           f"chapter id {want} read ({gc.get('chapter')}, {gc.get('chapter_routes')})")
    hc = bytearray(heap)
    struct.pack_into("<I", hc, 0x1800 + 0xC, H + 0x1900)
    struct.pack_into("<I", hc, 0x1900, H + 0x1A00)
    hc[0x1A00:0x1A06] = b"CID_\x01\x02"
    ok("chapter" not in game_state(Memory(statics + [(H, bytes(hc))]), cfg), "a non-text chapter id is not kept")
    ok(check({"5": dict(m, state={"chapter": "B007"})}, {"5": {"state": {"chapter": "B007"}}}) == [] and
       len(check({"5": dict(m, state={"chapter": "C007"})}, {"5": {"state": {"chapter": "B007"}}})) == 1,
       "a chapter checkpoint passes and fails")
    ok(chapter_routes("X007") == ["bt", "rv"] and chapter_routes("X022") == ["cq", "rv"] and chapter_routes("X006") == []
       and chapter_routes("B006") == ["cq"] and chapter_routes(None) is None and chapter_routes("ENDING") == [],
       "chapter_routes")
    ok(game_state(Memory([]), cfg) == {}, "game_state on missing memory reads nothing")
    # support_pairs: two force-0 units with persons (rows 1 and 5, ids 7 and 9), one bucket chain of two
    # nodes (the first for another row), an entry for partner 9 at slot 2 with C at 3; points 3 -> C ready
    sp = cfg["state"]["support"]
    h2 = bytearray(0x1000)
    def put32(at, v): struct.pack_into("<I", h2, at, v)
    def put16(at, v): struct.pack_into("<H", h2, at, v)
    put32(0x000, H + 0x100); put32(0x014 + 0x100, H + 0x200); put32(0x014 + 0x200, 0)   # pool -> u1 -> u2
    put32(0x100 + 0x9C, H + 0x400); put32(0x200 + 0x9C, H + 0x500)                       # persons
    put32(0x100 + 0x11C, H + 0x700); h2[0x702] = 3                                        # u1 points, slot 2
    put16(0x400 + 0x30, 1); put16(0x400 + 0x24, 7); put16(0x500 + 0x30, 5); put16(0x500 + 0x24, 9)
    put32(0x800 + 4 * 1, H + 0x900)                                                       # bucket for row 1
    put32(0x900, H + 0xA00); put32(0x904, H + 0x910); put32(0x910, H + 0xA40); put32(0x914, 0)
    put16(0xA00, 33)                                                                      # another row
    put16(0xA40, 1); put16(0xA42, 1); put16(0xA44, 9); put16(0xA46, 2); h2[0xA48:0xA4C] = bytes([3, 7, 12, 18])
    mem2 = Memory([(int(sp["table"], 16), struct.pack("<I", H + 0x800)), (H, bytes(h2))])
    ok(support_pairs(mem2, sp, H) == [(3, 3)], f"support_pairs follows the bucket chain ({support_pairs(mem2, sp, H)})")
    h2[0x702] = 2
    ok(support_pairs(Memory([(int(sp["table"], 16), struct.pack("<I", H + 0x800)), (H, bytes(h2))]), sp, H) == [(2, 3)],
       "support_pairs reads the points byte")
    # round 10: the named read (Kaze-Hana / Felicia-Saizo style): ids, all four thresholds, the rank the points reach
    h2[0x702] = 13
    sl = support_list(Memory([(int(sp["table"], 16), struct.pack("<I", H + 0x800)), (H, bytes(h2))]), sp, H)
    ok(sl == [{"a": 7, "b": 9, "points": 13, "thresholds": [3, 7, 12, 18], "ready": "A", "next": 18}],
       f"support_list: ids, thresholds, ready A at 13 points, next 18 ({sl})")
    ok(supports_by_pair(sl) == {"7-9": {"points": 13, "ready": "A", "next": 18}}, "supports_by_pair: smaller id first")
    # round 11 (tools-fixes item 2): pair-key order when the pool-order first id is the larger one. 13-4 must key
    # "4-13" and 10-7 "7-10" (a string sort would give "10-7"; no sort at all "13-4")
    ok(supports_by_pair([{"a": 13, "b": 4, "points": 3, "ready": "-", "next": 5},
                         {"a": 10, "b": 7, "points": 25, "ready": "A", "next": 35}])
       == {"4-13": {"points": 3, "ready": "-", "next": 5}, "7-10": {"points": 25, "ready": "A", "next": 35}},
       "supports_by_pair: a > b keys smaller id first, numeric (4-13, 7-10)")
    # round 11: the same through game_state: unit 1 is person 10 (Hana), unit 2 person 7 (Kaze), so the read row is
    # a=10, b=7; game_state's "supports" (and the counts beside it) must come out keyed "7-10"
    h7 = bytearray(h2)
    struct.pack_into("<H", h7, 0x400 + 0x24, 10)
    struct.pack_into("<H", h7, 0x500 + 0x24, 7)
    struct.pack_into("<H", h7, 0xA44, 7)                                  # the entry's partner id: 7
    h7[0x702] = 13
    up = (int(cfg["state"]["unit_pool"], 16), struct.pack("<II", 0, H))
    gs7 = game_state(Memory([(int(sp["table"], 16), struct.pack("<I", H + 0x800)), up, (H, bytes(h7))]), cfg)
    ok(gs7.get("supports") == {"7-10": {"points": 13, "ready": "A", "next": 18}} and gs7.get("support_pairs") == 1
       and gs7.get("support_c") == 1 and gs7.get("support_points_max") == 13,
       f"game_state: supports keyed 7-10 from a 10-7 row, counts beside it ({gs7})")
    ok(check({"5": {"state": gs7}}, {"5": {"state": {"supports.7-10.ready": "A", "supports.7-10.points": 13}}}) == []
       and len(check({"5": {"state": gs7}}, {"5": {"state": {"supports.10-7.ready": "A"}}})) == 1,
       "check: supports.7-10 found in game_state's read, supports.10-7 named missing")
    ok(support_ready(18, [3, 7, 12, 18]) == ("S", None) and support_ready(2, [3, 7, 12, 18]) == ("-", 3)
       and support_ready(7, [3, 7, None, None]) == ("B", None), "support_ready: S, none, unread thresholds")
    ok(check({"5": {"state": {"supports": {"7-10": {"points": 20, "ready": "A", "next": 30}}}}},
             {"5": {"state": {"supports.7-10.ready": "A"}}}) == [], "check: a dotted supports.<pair>.ready key")
    h2[0x702] = 2
    # round 4: levels and forge reads. Two force-3 units (the castle list); person ids 6 and 10; one item block
    # (first index 20, four records: 20 a sword sub-kind 1, 21 a staff sub-kind 2, 22 a sword, 23 an item sub-kind 3);
    # sub-kind table: 1 -> kind 0 (weapon), 2 -> kind 6 (staff), 3 -> kind 8 (Item::IsWeapon's second non-weapon kind).
    # Unit 6 holds item 20 twice, unit 10 item 22 at rank 1, a staff with 18 uses (bits 8..13 are uses, not a rank,
    # for a staff) and item 23 with 3 in those bits (kind 8: not a weapon either); the convoy has item 20 x2.
    lvc, fgc = dict(cfg["state"]["levels"]), dict(cfg["state"]["forge"])
    h3 = bytearray(0x3000)
    def p32(at, v): struct.pack_into("<I", h3, at, v)
    def p16(at, v): struct.pack_into("<H", h3, at, v)
    p32(12 * 3, H + 0x100); p32(0x100 + 0x14, H + 0x300)                  # force 3: u1 -> u2
    for at, per, job, pid in ((0x100, 0x600, 0x700, 6), (0x300, 0x640, 0x740, 10)):
        p32(at + 0x9C, H + per); p32(at + 0xA0, H + job); p16(per + 0x24, pid)
        h3[at + 0xF1], h3[at + 0xF2] = 5 + pid // 10, 89
        h3[per + 0x38:per + 0x40] = bytes([10, 5, 1, 4, 6, 3, 2, 1]); h3[job + 0x1C:job + 0x24] = bytes([7, 2, 0, 1, 1, 0, 2, 0])
        h3[at + 0xC8:at + 0xD0] = bytes([1, 0, 0, 1, 0, 0, 0xFF, 0])  # a gain of -1 on def
    p16(0x108 + 0x100, 20); p16(0x10C + 0x100, 20)
    p16(0x108 + 0x300, 22); p16(0x10A + 0x300, 0x0100); p16(0x10C + 0x300, 21); p16(0x10E + 0x300, 18 << 8)
    p16(0x110 + 0x300, 23); p16(0x112 + 0x300, 3 << 8)
    p32(0x1000, H + 0x1100); p32(0x1008, 0)                                # item block node: header, next
    p16(0x1100 + 0x1C, 20); p16(0x1100 + 6, 4)
    for i, sub in ((0, 1), (1, 2), (2, 1), (3, 3)):
        h3[0x1100 + 8 + 0x68 * i + 0x1A] = sub
    h3[0x1400 + 16 * 1 + 1], h3[0x1400 + 16 * 2 + 1] = 0, 6
    h3[0x1400 + 16 * 3 + 1] = 8
    p16(0x1800, 20); p32(0x1804, 2)                                        # convoy entry 0: item 20 x2
    statics3 = [(int(fgc["item_table"], 16), struct.pack("<I", H + 0x1000)),
                (int(fgc["subkind_table"], 16), struct.pack("<I", H + 0x1400)),
                (int(fgc["convoy"], 16), struct.pack("<I", H + 0x1800))]
    mem3 = Memory(statics3 + [(H, bytes(h3))])
    lv3 = unit_levels(mem3, lvc, H)
    ok(lv3 == {"6": {"lv": 5, "exp": 89, "gain": [1, 0, 0, 1, 0, 0, -1, 0], "stats": [18, 7, 1, 6, 7, 3, 3, 1]},
               "10": {"lv": 6, "exp": 89, "gain": [1, 0, 0, 1, 0, 0, -1, 0], "stats": [18, 7, 1, 6, 7, 3, 3, 1]}},
       f"unit_levels: level, exp, signed gains, base + class + gain over forces 0 and 3 ({lv3})")
    ok([item_is_weapon(mem3, fgc, i) for i in (20, 21, 22)] == [True, False, True], "item_is_weapon by sub-kind")
    ok(item_is_weapon(mem3, fgc, 23) is False, "item_is_weapon: kind 8 (the second non-weapon kind) is not a weapon")
    w3 = weapon_items(mem3, fgc, H)
    ok(w3 == [{"where": "6", "item": 20, "rank": 0}, {"where": "6", "item": 20, "rank": 0},
              {"where": "10", "item": 22, "rank": 1}, {"where": "convoy", "item": 20, "rank": 0, "count": 2}],
       f"weapon_items: unit items and the convoy, a staff's uses and a kind-8 item's bits are not a rank ({w3})")
    cfg3 = dict(cfg, state=dict(cfg["state"], unit_pool="0x00600000"))
    gs3 = game_state(Memory(statics3 + [(0x00600000, struct.pack("<II", 0, H)), (H, bytes(h3))]), cfg3)
    ok(gs3.get("forge_max") == 1 and gs3.get("forge_pairs") == 2 and gs3.get("forged") == [w3[2]]
       and gs3.get("levels") == lv3, f"game_state: forged, forge_max, like pairs, levels ({gs3})")
    m3 = dict(m, state=gs3)
    ok(check({"5": m3}, {"5": {"state": {"levels.6.lv": 5, "levels.10.stats": [18, 7, 1, 6, 7, 3, 3, 1],
                                         "forge_max": 1}}}) == [], "dotted state keys reach into levels")
    ok(len(check({"5": m3}, {"5": {"state": {"levels.6.lv": 6, "levels.99.lv": 1}}})) == 2,
       "dotted keys name a wrong value and a missing unit")
    # round 6 (Grok review 4, low #2): a third unit with person id 6 again (a second copy of a unit) is kept as "6#2"
    h4 = bytearray(h3)
    struct.pack_into("<I", h4, 0x300 + 0x14, H + 0x500)                    # u2 -> u3
    struct.pack_into("<I", h4, 0x500 + 0x9C, H + 0x600)                    # u3's person: id 6 again
    struct.pack_into("<I", h4, 0x500 + 0xA0, H + 0x700)
    h4[0x500 + 0xF1], h4[0x500 + 0xF2] = 9, 40
    lv4 = unit_levels(Memory(statics3 + [(H, bytes(h4))]), lvc, H)
    ok(set(lv4) == {"6", "10", "6#2"} and lv4["6"]["lv"] == 5 and lv4["6#2"]["lv"] == 9 and lv4["6#2"]["exp"] == 40,
       f"unit_levels: two units with one person id both survive, the first keeps the bare id ({sorted(lv4)})")
    # round 6 (review round 5): forge ranks beyond 1. The rank is the 6-bit field of bits 8..13; bits 14..15 are
    # other flags (0x4000 = equipped) and must not change it. A 5-bit or 3-bit mask, or a shift of 9, fails here.
    ranks = []
    for rank, extra in ((2, 0), (5, 0), (7, 0x4000), (31, 0), (32, 0x8000), (63, 0xC000)):
        h5 = bytearray(h3)
        struct.pack_into("<H", h5, 0x10A + 0x300, (rank << 8) | extra | 0x07)  # low byte: not part of the rank
        w5 = weapon_items(Memory(statics3 + [(H, bytes(h5))]), fgc, H)
        ranks.append(next((x["rank"] for x in w5 if x["where"] == "10" and x["item"] == 22), None))
    ok(ranks == [2, 5, 7, 31, 32, 63], f"weapon_items: refine ranks 2..63 from bits 8..13 only ({ranks})")
    h6 = bytearray(h3)
    struct.pack_into("<H", h6, 0x10A + 0x300, 3 << 8)
    struct.pack_into("<H", h6, 0x10E + 0x100, 3 << 8)                     # unit 6's second item 20 at rank 3
    gs6 = game_state(Memory(statics3 + [(0x00600000, struct.pack("<II", 0, H)), (H, bytes(h6))]), cfg3)
    ok(gs6.get("forge_max") == 3 and len(gs6.get("forged") or []) == 2 and gs6.get("forge_pairs") == 1,
       f"game_state: forge_max 3, two forged, the rank-3 and rank-0 swords of one holder are not a pair ({gs6})")
    # round 7: the options block read (GameConfigData +0x4 .. +0x16 through G_GameConfig)
    gcc = cfg["state"]["game_config"]
    blk = bytearray(0x40)
    struct.pack_into("<I", blk, 4, 0x00011E5E)
    blk[0x8:0x17] = bytes([1, 0, 0, 1, 2, 0, 0, 0x80, 0xFF, 0xFF, 0xFF, 0xFF, 0, 0, 1])
    blk[0x17] = 0xAA                                                      # past the block: must not be read
    mem7 = Memory([(int(gcc["pointer"], 16), struct.pack("<I", H)), (H, bytes(blk))])
    want7 = "5e1e0100" + "010000010200008" + "0ffffffff000001"
    ok(game_config(mem7, gcc) == want7, f"game_config: the 19 saved option bytes, in memory order ({game_config(mem7, gcc)})")
    ok(game_config(Memory([(int(gcc["pointer"], 16), struct.pack("<I", 0))]), gcc) is None, "game_config: no block -> None")
    blk[0xC] = 1
    ok(game_config(Memory([(int(gcc["pointer"], 16), struct.pack("<I", H)), (H, bytes(blk))]), gcc) != want7,
       "game_config: one changed option byte changes the read")
    return errors, f"markers self-test: {checks - len(errors)}/{checks} checks passed"


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        errs, line = selftest()
        for e in errs:
            print(f"  FAIL  {e}")
        print(line)
        sys.exit(1 if errs else 0)
    if len(sys.argv) == 2:
        with open(os.path.join(RUNS, sys.argv[1], "run.json"), encoding="utf-8") as fh:
            print(json.dumps(json.load(fh).get("markers"), indent=1))
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
