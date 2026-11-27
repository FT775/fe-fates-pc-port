#!/usr/bin/env python3
"""Round 59 CHECK ROBOT driver (docs/tests/RCHECK.md): strict OFF/ON pairs and the new screens.

Round 58's lesson (docs/REPORT_2027-01-01.md, "Honest note"): pairs were counted whose OFF and ON shots had the cursor
on another unit, or showed no change, or whose ON pictures were the same file for several settings. This driver
records, for every shot, the screen (markers' current process), the frame, and the unit the screen is about (read
from memory: the unit under the map cursor, or the unit at the menu cursor's index in the army list), with that
unit's own fields (class, growths, bases, skills, personal skill, Heart Seal classes, its class's promotions, items,
exp/level). A pair is VALID only when (judge_pair, self-tested):
  1. OFF and ON are the same screen, at the same frame, about the same unit (same person id);
  2. the setting's OWN field differs between OFF and ON (the unit's field, or the setting's patch cells in memory);
  3. the pictures differ (pixels, not file bytes);
  4. the ON picture is not byte-identical to the ON picture of a DIFFERENT setting at the same chapter and screen.
Anything else is REJECTED with its reason and never counted. A valid pair is still only "robot" until the owner
looks (F-037).

Each job is one headless boot-server copy (tools/harness/server.py: CREATE_NO_WINDOW, below normal, data/APPDATA/
LOCALAPPDATA in the job's folder below build/r59/robot/), on a FROZEN copy of the round-58 boot-server.exe and capture
library (build/r59/robot/bin, sha256 in SHA256.txt), so a rebuild elsewhere never changes what is tested.
build/STOP_ROUND is checked before every start and every step. A randomized run (made offline as the core makes it,
build/r58/check/runs/<game>/<id>/) is laid as the loaded save's side file, so the core lays it when the title reads
the save (round 51 T5/T6 path, as round 58's check did). Cheat pokes (exp, items) go into the job's own state only.

    python tools/harness/rcheck.py --selftest
    python tools/harness/rcheck.py run LANE.json [--redo]   a JSON list of jobs, one after another
    python tools/harness/rcheck.py pairs PAIRS.json          judge the pairs a pairs file names -> verdicts json

Job keys: name, chapter, base?, game fates|seal, path?, route_byte?, run (run id or null), mode select|direct|route,
screens [names below], steps look|full, plus a few per screen (seal_iid, ...).
Screens: unitpage, skillpage (prep: the bottom screen's second page), mseal / hseal (prep: a seal given to the first
unit, Inventory > Items > the seal > Use: the class change list), levelup (map: every player unit's exp 99, then the
enemy phase until a level-up window), child (map: cursor on the first 'other' force unit, its panel and page),
route (a recorded UI route, shots at given frames: castle shops).

Round 64's robot job keys, moved here in round 65 from the round drivers (build/r64/bosses/p64.py,
build/r64/bosses/might/p64m.py, build/r64/checks/robot/p64.py; cheat pokes in the job's own copy only):
  place_next   bosskill's attacker is PUT on a free tile next to the target (unit +0xF4/+0xF5 and the map's
               unit grid, found by grid_search with pair-ups left out), picked there and told to stay; with
               the armed-attacker swap (a singer or a unit that acted gives way to the next armed unit) and
               the talk skip (a Talk picked by A: the tile again with DOWN before the attack keys,
               command_downs, default 3; command_shots: pictures of the unit command)
  boss_look    before the kill, the cursor on the boss and the shot boss_page (its class on the bottom screen)
  touch_page   (enemy_look) the bottom screen's page icon touched at the first enemy: the full page
  enemy_at     (enemy_look) these squares first; enemy_page: R on each enemy
  attack_unit  (bosskill screen) that player unit attacks the nearest enemy: battle shots attack0..3
  dropcheck    (bosskill screen) the drop flag test: four kills from one memory slot
  yesno_left   every A on a Yes/No question is LEFT A (Yes)
Round 72: boss_attacker_pid (a person id or a list) puts bosskill's attackers (and place_next's armed swap and the
guard path's second unit) in an order that does not depend on the pool list (attacker_order): the same attacker in
the on and the off run; with boss_waves 1 every try is that unit's."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.append(HERE)
import chapsel as C  # noqa: E402

OUT = os.path.join(ROOT, "build", "r59", "robot")
BIN = os.path.join(OUT, "bin")
RUNS = os.path.join(ROOT, "build", "r58", "check", "runs")
SEALMOD = os.path.join(ROOT, "build", "r58", "chapsel", "_sealmod", C.TITLE)
TITLE = C.TITLE
POOL = 0x006D9F40
TOUCH_PAGE = (305, 12)  # the bottom screen's page switch (the two-arrow icon, top right): Simple UI, not wanted
TOUCH_SKILL = (250, 41)  # the bottom screen's first skill icon (right of the HP box) on the unit page


def setup(out: str = OUT) -> None:
    C.OUT_TOP = os.path.join(out, "jobs")
    exe, lib = os.path.join(BIN, "boot-server.exe"), os.path.join(BIN, f"{TITLE}.dll")
    if os.path.isfile(exe) and os.path.isfile(lib):
        C.SERVER_KW.update(exe=exe, lib=lib)


# ------------------------------------------------------------------ memory reads
def s8(b: int) -> int:
    return b - 256 if b > 127 else b


class Mem:
    def __init__(self, s):
        self.s = s

    def u32(self, a: int) -> int:
        if not a:
            return 0
        try:
            return struct.unpack("<I", self.s.peek1(a, 4))[0]
        except Exception:  # noqa: BLE001
            return 0

    def raw(self, a: int, n: int) -> bytes:
        return self.s.peek1(a, n) if a else b""

    def cstr(self, a: int, n: int = 48) -> str:
        if not a:
            return ""
        try:
            return self.raw(a, n).split(b"\0")[0].decode("cp932", "replace")
        except Exception:  # noqa: BLE001
            return ""

    def gamedata(self) -> int:
        arch = self.u32(C.GD_ARCH)
        a = self.u32(arch + 4) if arch else 0
        b = self.u32(a + 112) if a else 0
        return b + 32 if b else 0

    def item_numbers(self) -> dict[str, int]:
        """IID -> item number (GameData header +0x2C: the Item block, 8-byte header, 0x68-byte records)."""
        gd = self.gamedata()
        blk = self.u32(gd + 0x2C) if gd else 0
        if not blk:
            return {}
        n = struct.unpack("<H", self.raw(blk + 6, 2))[0]
        if not 0 < n < 2000:
            return {}
        blob = self.raw(blk + 8, n * 0x68)
        out = {}
        for k in range(n):
            iid = self.cstr(struct.unpack_from("<I", blob, k * 0x68 + 8)[0], 40)
            out[iid] = struct.unpack_from("<H", blob, k * 0x68 + 0x14)[0]
        return out

    def unit(self, u: int, force: int) -> dict:
        ub = self.raw(u, 0x140)
        per, job = struct.unpack_from("<II", ub, 0x9C)
        pb, jb = self.raw(per, 0x98), self.raw(job, 0x80)
        return {"force": force, "addr": f"{u:08x}",
                "pid": self.cstr(struct.unpack_from("<I", pb, 8)[0]), "jid": self.cstr(struct.unpack_from("<I", jb, 8)[0]),
                "level": ub[0xF1], "exp": ub[0xF2], "hp": ub[0xF3], "x": ub[0xF4], "y": ub[0xF5],
                "items": [list(struct.unpack_from("<HH", ub, 0x108 + 4 * i)) for i in range(5)],
                "skills": list(struct.unpack_from("<5H", ub, 0xFC)),
                "person_base": [s8(x) for x in pb[0x38:0x40]], "growth": [s8(x) for x in pb[0x40:0x48]],
                "personal_skill": list(struct.unpack_from("<3H", pb, 0x74)),
                "reclass": list(struct.unpack_from("<2H", pb, 0x7C)),
                "job_base": [s8(x) for x in jb[0x1C:0x24]], "job_growth": [s8(x) for x in jb[0x24:0x2C]],
                "promotion": list(struct.unpack_from("<2H", jb, 0x64)),
                "job_skill": list(struct.unpack_from("<4H", jb, 0x54))}

    def units(self, forces=(0, 1, 2, 3)) -> list[dict]:
        fp = self.u32(POOL + 4)
        out = []
        for f in forces:
            u, n = self.u32(fp + 12 * f), 0
            while u and C.LINEAR <= u < C.LINEAR + (128 << 20) and n < 200:
                n += 1
                out.append(self.unit(u, f))
                u = struct.unpack_from("<I", self.raw(u, 0x18), 0x14)[0]
        return out


# fields a setting changes, read off the unit a screen is about (None: the setting's patch cells are used)
SETTING_FIELD = {
    "classes": ("jid",), "growths": ("growth",), "bases": ("person_base",), "personal_skills": ("personal_skill",),
    "skill_slots": ("skills",), "promotions": ("promotion",), "reclass": ("reclass",), "children": ("jid", "reclass"),
    "class_growths": ("job_growth",), "class_bases": ("job_base",), "starting_items": ("items",),
    "enemy_classes": ("jid",), "boss_classes": ("jid",), "enemy_weapons": ("items",), "enemy_upgrade": ("items",),
    "enemy_growths": ("hp", "level"), "enemy_drops": ("items",),
    # round 62 (F-049): the growth view's numbers follow the laid growths (OFF = randomizer off, ON = growths on);
    # the growth floor's pair is the same screen with judge_floor's extra rule
    "growth_view": ("growth_total",), "growth_floor": ("growth_total",),
}
FLOOR, CEIL = 20, 100   # F-049 addendum: every total growth (personal + class) 20..100, also stats that were 0


def judge_growthview(stats: dict, stats2: dict, grown: dict, back: dict, diff=None) -> dict:
    """Round 62, goal 2: one run's growth-view toggle on one unit page. stats / stats2: the page twice with no
    press (stats2 later: the idle animation's pixel noise), grown: after the press (SELECT or the Growths
    button), back: after the second press. VALID only if all four are the same screen about the same unit, the
    press changed the picture by more than the idle noise, and the second press brought the stats picture back
    (no more than the idle noise from it)."""
    diff = diff or pixel_diff
    recs = [stats, stats2, grown, back]
    if any(r is None for r in recs):
        return {"valid": False, "why": ["a shot is missing"]}
    why = []
    if len({r.get("screen") for r in recs}) != 1:
        why.append(f"different screens {[r.get('screen') for r in recs]}")
    pids = {(r.get("focus") or {}).get("pid") for r in recs}
    if len(pids) != 1 or None in pids:
        why.append(f"not one unit read ({sorted(map(str, pids))})")
    noise = diff(stats["png"], stats2["png"])
    dg, db = diff(stats["png"], grown["png"]), diff(stats["png"], back["png"])
    if min(noise, dg, db) < 0:
        why.append("a picture could not be read")
    elif dg <= noise:
        why.append(f"the press changed nothing visible (diff {dg}, idle noise {noise})")
    elif db > noise:
        why.append(f"the second press did not bring the stats back (diff {db}, idle noise {noise})")
    return {"valid": not why, "why": why, "noise": noise, "diff_press": dg, "diff_back": db}


def judge_same(off: dict, on: dict, fields=("person_base", "growth", "hp", "items"), diff=None) -> dict:
    """Round 62: a setting that must NOT change this unit (tougher bosses: Conquest's chapter boss who joins on
    another route keeps his Person row). VALID only if same screen, frame and unit, every field equal and the
    pictures pixel-equal."""
    diff = diff or pixel_diff
    why = []
    if off.get("screen") != on.get("screen") or off.get("frame") != on.get("frame"):
        why.append("different screen or frame")
    fo, fn = off.get("focus") or {}, on.get("focus") or {}
    if not fo or fo.get("pid") != fn.get("pid"):
        why.append(f"not the same unit ({fo.get('pid')} / {fn.get('pid')})")
    changed = {k: [fo.get(k), fn.get(k)] for k in fields if fo.get(k) != fn.get(k)}
    if changed:
        why.append(f"changed: {changed}")
    pd = diff(off["png"], on["png"]) if off.get("png") and on.get("png") else -1.0
    if pd != 0:
        why.append("the pictures differ" if pd > 0 else "a picture could not be read")
    return {"valid": not why, "why": why, "pixel_diff": pd}


STEP = {"easy": 1, "normal": 2, "hard": 3}   # F-049: the randomizer's difficulty step
# class id parts of the flying classes (Sky Knight / Falcon Knight / Kinshi / Wyvern lines, Revenant): bosskill's
# second choice of attacker when no walker reaches the boss
FLIER_JOBS = ("天馬", "ドラゴン", "鷹", "金鵄", "レヴナント")


# ------------------------------------------------------------------ round 65: round 64's robot job keys, pure parts
# (moved from build/r64/bosses/p64.py, build/r64/bosses/might/p64m.py and build/r64/checks/robot/p64.py; the
# CheckRun methods below use them; each is self-tested)
ARMED = 0x4000   # item word 2 bit: the equipped weapon (round 64: B025's wave 2 was Azura, who holds none)


def is_armed(u: dict) -> bool:
    """the unit holds an equipped weapon (an item whose word 2 has bit 0x4000)"""
    return any(it[0] and it[1] & ARMED for it in u.get("items") or [])


def pick_attacker(att: dict, units: list, used: set) -> tuple[dict, bool]:
    """armed-attacker swap: att itself if it is armed and has not acted in this attempt, else the first living
    player unit (units in pool order) that is armed and has not acted; (unit, swapped). No such unit: att, False."""
    if is_armed(att) and att["addr"] not in used:
        return att, False
    for u in units:
        if u["hp"] > 0 and u["addr"] not in used and is_armed(u):
            return u, True
    return att, False


def attacker_order(ps: list, want=None) -> list:
    """round 72 (the round-64 note): the player units bosskill picks its attackers from. The pool list's order is
    not the same from run to run (round 66 R016: Corrin, Azura, Gunter, Kazahana with the randomizer on, Corrin,
    Felicia, Sakura, Takumi off, from the same save), so an index (boss_attacker) can name a different unit in the
    on and the off run. With job boss_attacker_pid (a person id, or a list of them) the list is put in an order
    that does not depend on the pool: the wanted person ids first, in the order given, then every other unit by
    person id (then address). Without it the pool order is kept (older jobs unchanged)."""
    if not want:
        return list(ps)
    want = [want] if isinstance(want, str) else list(want)
    rank = {p: k for k, p in enumerate(want)}
    return sorted(ps, key=lambda u: (u["pid"] not in rank, rank.get(u["pid"], 0), u["pid"], u.get("addr", "")))


def free_around(x: int, y: int, occ: set, near: tuple | None = None) -> list:
    """the four tiles next to (x, y) that are on the map and not taken (down, left, right, up; nearest to `near`
    first when given)"""
    out = [(x + dx, y + dy) for dx, dy in ((0, 1), (-1, 0), (1, 0), (0, -1))
           if x + dx >= 0 and y + dy >= 0 and (x + dx, y + dy) not in occ]
    if near:
        out.sort(key=lambda t: abs(t[0] - near[0]) + abs(t[1] - near[1]))
    return out


def grid_search(fc, units: list, linear: int = C.LINEAR) -> tuple[int | None, list]:
    """The map's unit grid (round 64, A013: 32 bytes a row, one byte per tile = the unit's pool number, 0 = empty;
    its heap address differs per chapter) in a FCRAM copy: the one place where every unit on the map stands at its
    (x, y) with numbers that differ like their pool slots (unit address / 0x140). A pair-up shares a tile and only
    its lead is on the grid: tiles with two units are left out; a few reference units are tried, so one odd unit
    (off the grid) does not hide it. Returns (guest address or None, up to 4 hit addresses)."""
    import numpy as np
    a = np.frombuffer(bytes(fc), dtype=np.uint8)
    us = [u for u in units if u["hp"] > 0 and 0 <= u["x"] < 32 and 0 <= u["y"] < 32]
    tiles: dict = {}
    for u in us:
        tiles.setdefault((u["x"], u["y"]), []).append(u)
    us = [v[0] for v in tiles.values() if len(v) == 1]
    if len(us) < 3:
        return None, []
    a0 = min(int(u["addr"], 16) for u in us)
    ps = [(u["y"] * 32 + u["x"], ((int(u["addr"], 16) - a0) // 0x140) % 256) for u in us]
    m = len(a) - max(p for p, _ in ps) - 1
    hits = np.zeros(0, dtype=np.int64)
    for ref in range(min(3, len(ps))):
        p0, k0 = ps[ref]
        base = a[p0:p0 + m] - np.uint8(k0)
        cnt = np.zeros(m, np.uint8)
        for p, k in ps:
            cnt += (a[p:p + m] - np.uint8(k)) == base
        hits = np.nonzero((cnt >= len(ps) - 2) & (base != 0))[0]
        if len(hits) == 1:
            break
    out = [linear + int(h) for h in hits[:4]]
    return (out[0] if len(hits) == 1 else None), out


def command_outcome(screens: list, battle: bool = False) -> str:
    """what the unit command's presses led to: 'battle' (a battle started, or the battle forecast ProcBattleInfo
    opened), 'talk' (a talk window opened before any forecast: the highlighted command was Talk, A023 Arthur),
    else 'none'"""
    if battle:
        return "battle"
    for s in screens:
        s = s or ""
        if "ProcBattleInfo" in s:
            return "battle"
        if "TalkKeyWait" in s or "Talk" in s:
            return "talk"
    return "none"


def next_downs(downs: int, outcome: str, top: int) -> int | None:
    """talk skip: the number of DOWN presses on the unit command before the attack keys for the next try on the
    same tile, or None (next tile). A talk moves one item down; after a first move, a menu item that is neither
    the forecast nor a talk moves one more; at downs 0 a plain failure is the tile's (not reachable)."""
    if outcome == "battle":
        return None
    if outcome == "talk" or downs > 0:
        return downs + 1 if downs + 1 <= top else None
    return None


def yesno_buttons(buttons: str, current: str | None, on: bool) -> str:
    """yesno_left: an A on a Yes/No question becomes LEFT A (Yes is the left choice; a drop into a full inventory
    otherwise loops, A018 Leo, A025 Iago)"""
    if on and buttons == "A" and "YesNo" in (current or ""):
        return "LEFT A"
    return buttons


def drop_writes(addr: int, items: list, mode: str | None) -> list:
    """dropcheck pokes for an enemy at unit address addr: 'clear' bit 0x8000 of word 2 on every item that has it,
    'set' it on the slot-1 item, None nothing. Item k's word 2 is at unit +0x108 + 4k + 2."""
    ws = []
    for k, (num, w2) in enumerate(items):
        if not num:
            continue
        if mode == "clear" and w2 & 0x8000:
            ws.append((addr + 0x108 + 4 * k + 2, struct.pack("<H", w2 & ~0x8000 & 0xFFFF)))
        if mode == "set" and k == 0:
            ws.append((addr + 0x108 + 2, struct.pack("<H", w2 | 0x8000)))
    return ws


def items_gained(before: list | None, after: list | None) -> list:
    """item numbers in `after` and not in `before` (a multiset difference; empty slots left out)"""
    gained = [x[0] for x in (after or []) if x[0]]
    for x in [y[0] for y in (before or []) if y[0]]:
        if x in gained:
            gained.remove(x)
    return gained


def judge_chest(chests: list, chapter: str, orig: str | None, before: list | None, after: list | None,
                num2iid: dict, convoy_before: list | None = None, convoy_after: list | None = None,
                x: int | None = None, y: int | None = None) -> dict:
    """round 70 (docs/rando/CHESTS.md section 5): the chest / village judge. chests = plan.json "chests" ([] for an
    off run); before/after = the opening unit's item slots around the open ([num, uses] pairs, as items_gained
    takes them); the convoy lists the same way (a full inventory sends the item there). Pure: the item numbers
    become IIDs through num2iid and tools/randomizer/chests.judge_gain decides.
    Round 73b: the gain is the NET gain of unit and convoy together. Round 72's Conquest B010 village gave Killer Axe
    into a full bag, so the game sent Corrin's Dragonstone from the bag to the convoy; counting the two lists apart
    saw the Dragonstone 'gained' in the convoy too and said 'more than one item gained' on a right village."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
    import chests as CH
    gained = items_gained(list(before or []) + list(convoy_before or []), list(after or []) + list(convoy_after or []))
    return CH.judge_gain(chests, chapter, orig, [num2iid.get(n, f"#{n}") for n in gained], x, y)


def enemy_order(es: list, want: list, cur) -> list:
    """enemy_at: the squares in `want` first (in that order), then unique people, then the nearest to the cursor"""
    want = [tuple(p) for p in want]
    cnt: dict = {}
    for u in es:
        cnt[u["pid"]] = cnt.get(u["pid"], 0) + 1
    return sorted(es, key=lambda u: ((u["x"], u["y"]) not in want,
                                     want.index((u["x"], u["y"])) if (u["x"], u["y"]) in want else 0,
                                     cnt[u["pid"]] > 1, abs(u["x"] - cur[0]) + abs(u["y"] - cur[1]), u["x"], u["y"]))


def forge_of(w2: int) -> int:
    """the forge level in a unit item's second word (round 62 rando track: 0x4101 = equipped, +1)"""
    return (w2 >> 8) & 0xF


def judge_ladder(off_items: list, on_items: list, difficulty: str, next_rung: dict, num2iid: dict,
                 never: set = frozenset()) -> dict:
    """Round 62, goal 3, one enemy's five item slots OFF -> ON ([item number, word 2] each). next_rung: {iid: the
    next rung's iid} for every weapon on a ladder (tools/randomizer/weapons.py ladder_lines / next_rung over the
    laid Item table; the top rung maps to None); num2iid: {item number: iid} (Mem.item_numbers reversed); never:
    iids that must not change (Yato, legendary, personal, precious). Per changed slot, the allowed steps:
      ladder weapon   easy: same item, forge +1; normal: next rung, same forge (or same item, forge +1: the
                      class cannot hold the next rung); hard: next rung and forge +1 (or same item, forge +2)
      other weapon    easy/normal: same item, forge +1; hard: forge +2 (Killer, Brave, effective ...)
    Forge never past 7. VALID only if at least one slot changed and every changed slot is allowed."""
    why, steps = [], []
    for k, (a, b) in enumerate(zip(off_items, on_items)):
        if list(a) == list(b):
            continue
        ia, ib = num2iid.get(a[0]), num2iid.get(b[0])
        fa, fb = forge_of(a[1]), forge_of(b[1])
        if ia in never:
            why.append(f"slot {k}: {ia} must never change")
            continue
        if fb > 7:
            why.append(f"slot {k}: forge {fb} past 7")
            continue
        same, nxt = ia == ib, (ia in next_rung and next_rung[ia] is not None and next_rung[ia] == ib)
        d = fb - fa
        if ia in next_rung:
            ok = {"easy": same and d == 1,
                  "normal": (nxt and d == 0) or (same and d == 1),
                  "hard": (nxt and d == 1) or (same and d == 2)}[difficulty]
        else:
            ok = same and d == (2 if difficulty == "hard" else 1)
        steps.append([k, ia, fa, ib, fb, "ok" if ok else "NOT ALLOWED"])
        if not ok:
            why.append(f"slot {k}: {ia}+{fa} -> {ib}+{fb} is not one {difficulty} step")
    if not steps and not why:
        why.append("no slot changed")
    return {"valid": not why, "why": why, "steps": steps}


def name_slot_might(num: int, f_off: int, f_on: int) -> int:
    """Shown might a boss weapon gains from forge f_off to f_on with name slot 1 (round 63): unit::Item::GetPower
    (0053B4B4) then reads the second forge table row (Item+0x49, +1 might per level)."""
    return f_on - f_off


def boss_hp_cap(tables, row: dict, jid: str | None = None) -> int | None:
    """Round 66: the personal-base HP cap the randomizer used for this boss row (tools/randomizer/stats.py
    boss_limits: class max HP + the row's limit modifier - class base HP), from a passed-in tables object (a
    StatsTables of the run's own game, or anything with unit_job). jid: the class the boss has in that run (the
    unit's class in memory) when it differs from the row's. None when the class is not known."""
    import importlib
    rd = os.path.join(ROOT, "tools", "randomizer")
    if rd not in sys.path:
        sys.path.insert(0, rd)
    S = importlib.import_module("stats")
    r = dict(row, job=jid) if jid else row
    lim = S.boss_limits(tables, r, "hp")
    return None if lim is None else lim[1]


def judge_boost(off_boss: dict, on_boss: dict, difficulty: str, army_boss: bool, num2iid: dict,
                never: set = frozenset(), might_add=name_slot_might, hp_cap: int | None = None) -> dict:
    """Round 62, goal 5, the same boss OFF (tougher bosses off) -> ON (on, the same seed and difficulty).
    HP: ON - OFF = ceil(10% x step x (personal + class base HP)) for an army boss (Conquest's chapter-only bosses
    who join elsewhere: no linear buff on top), at least that for the others; a smaller rise only when it stops
    at a cap ("capped"; round 66: only when hp_cap, the personal-base HP cap from that run's own tables (boss_hp_cap),
    is given and the ON personal HP sits exactly at max(OFF personal HP, cap) and the shown rise equals the personal
    rise; else a short rise fails; a rise of 0 passes only that way, the randomizer's "already at the cap stays"). Weapons (round 63, F-051: the might the player sees, not
    a forge count): every forged slot holding a weapon not in never shows might +1 / +2 / +3 (easy / normal /
    hard), computed by might_add(item number, forge OFF, forge ON) (default: name slot 1, +1 per level); a smaller
    rise only when forge 7 stops it ("forge_capped"); never-slots unchanged; item numbers unchanged."""
    why = []
    st = STEP[difficulty]
    hp_base = (off_boss.get("person_base") or [0])[0] + (off_boss.get("job_base") or [0])[0]
    want = -(-(10 * st * hp_base) // 100)
    rise = on_boss.get("hp", 0) - off_boss.get("hp", 0)
    pb_off = (off_boss.get("person_base") or [None])[0]
    pb_on = (on_boss.get("person_base") or [None])[0]
    at_cap = (hp_cap is not None and pb_off is not None and pb_on is not None
              and pb_on == max(pb_off, hp_cap) and rise == pb_on - pb_off)
    capped = 0 <= rise < want and at_cap
    if off_boss.get("pid") != on_boss.get("pid"):
        why.append("not the same boss")
    if rise < 0 or (army_boss and rise > want) or (rise < want and not capped):
        why.append(f"HP rise {rise}, want {want}{'' if not army_boss else ' exactly'}"
                   + ("" if rise < 0 or rise >= want else
                      " (no cap given)" if hp_cap is None else
                      f" (ON personal HP {pb_on} is not at its cap: max(OFF {pb_off}, cap {hp_cap}), shown rise {rise})"))
    if rise == 0 and want > 0 and not capped:
        why.append("HP did not rise")
    lv = st
    forged, fcap = [], []
    for k, (a, b) in enumerate(zip(off_boss.get("items") or [], on_boss.get("items") or [])):
        if not a[0]:
            continue
        if a[0] != b[0]:
            why.append(f"slot {k}: the item changed ({a[0]} -> {b[0]})")
            continue
        d = forge_of(b[1]) - forge_of(a[1])
        iid = num2iid.get(a[0])
        if iid in never:
            if d:
                why.append(f"slot {k}: {iid} must never be forged")
        elif d:
            m = might_add(a[0], forge_of(a[1]), forge_of(b[1]))
            forged.append([k, iid, d, m])
            if m != lv and not (m < lv and forge_of(b[1]) == 7):
                why.append(f"slot {k}: shown might +{m} (forge +{d}), want +{lv}")
            elif m < lv:
                fcap.append(k)
    if not forged:
        why.append("no weapon forged")
    return {"valid": not why, "why": why, "hp_rise": rise, "hp_want": want, "capped": capped, "hp_cap": hp_cap,
            "person_hp": [pb_off, pb_on], "forged": forged, "forge_capped": fcap}


def judge_floor(off: dict, on: dict, diff=None) -> dict:
    """Round 62, goal 1 on screen: the growth view of the same unit, OFF = randomizer off (the game's own growths),
    ON = a run with growths randomized. judge_pair's six rules for growth_floor, and: the unit's OFF totals have
    a stat below FLOOR (so the floor shows), and every ON total is FLOOR..CEIL."""
    r = judge_pair(off, on, "growth_floor", {}, diff=diff or pixel_diff)
    fo, fn = (off.get("focus") or {}).get("growth_total"), (on.get("focus") or {}).get("growth_total")
    if not fo or not fn:
        r["why"].append("no growth totals read")
    else:
        if min(fo) >= FLOOR:
            r["why"].append(f"the OFF unit has no total below {FLOOR} ({fo}): the floor cannot show")
        bad = [(k, v) for k, v in enumerate(fn) if not FLOOR <= v <= CEIL]
        if bad:
            r["why"].append(f"ON totals outside {FLOOR}..{CEIL}: {bad}")
    r["valid"] = not r["why"]
    return r


def focus_fields(u: dict | None) -> dict | None:
    if not u:
        return None
    keep = ("pid", "jid", "level", "exp", "hp", "x", "y", "force", "items", "skills", "person_base", "growth",
            "personal_skill", "reclass", "job_base", "job_growth", "promotion", "job_skill")
    out = {k: u.get(k) for k in keep}
    if u.get("growth_total") is not None:
        out["growth_total"] = u["growth_total"]
    elif u.get("growth") and u.get("job_growth"):   # round 62: the total the growth view shows (personal + class)
        out["growth_total"] = [a + b for a, b in zip(u["growth"], u["job_growth"])]
    return out


# ------------------------------------------------------------------ pair judging (pure, self-tested)
def png_pixels(path: str) -> bytes | None:
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.convert("RGB").tobytes()
    except Exception:  # noqa: BLE001
        return None


def pixel_diff(a: str, b: str) -> float:
    pa, pb = png_pixels(a), png_pixels(b)
    if pa is None or pb is None or len(pa) != len(pb):
        return -1.0
    diff = sum(1 for i in range(0, len(pa), 3) if pa[i:i + 3] != pb[i:i + 3])
    return round(diff / (len(pa) // 3), 5)


def sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def judge_pair(off: dict, on: dict, setting: str, others_on: dict[str, str] | None = None,
               diff=pixel_diff) -> dict:
    """off/on: shot records {"screen", "frame", "focus" (unit fields or None), "cells" (the setting's patch cells
    in memory: {"changed", "new_held"} or None), "png", "sha"}. others_on: {other setting: ON sha} at the same
    chapter and screen label. Returns {"valid": bool, "why": [...], "pixel_diff": f}."""
    why = []
    if off.get("screen") != on.get("screen"):
        why.append(f"different screen ({off.get('screen')} / {on.get('screen')})")
    if off.get("frame") != on.get("frame"):
        why.append(f"different frame ({off.get('frame')} / {on.get('frame')})")
    if off.get("hist") and on.get("hist") and off["hist"] != on["hist"]:
        why.append(f"the runs went through different screens before this shot (timing shift: off {off.get('hist_tail')}"
                   f" / on {on.get('hist_tail')})")
    fo, fn = off.get("focus"), on.get("focus")
    if (fo is None) != (fn is None):
        why.append("one side has no unit read")
    elif fo is not None and fo.get("pid") != fn.get("pid"):
        why.append(f"different unit ({fo.get('pid')} / {fn.get('pid')})")
    fields = SETTING_FIELD.get(setting)
    own = None
    if fields and fo is not None and fn is not None:
        own = {k: [fo.get(k), fn.get(k)] for k in fields if fo.get(k) != fn.get(k)}
        if not own:
            why.append(f"the setting's own field is equal ({'/'.join(fields)})")
    else:
        co, cn = off.get("cells") or {}, on.get("cells") or {}
        if not cn.get("changed"):
            why.append("no changed cell of the setting in this run")
        elif cn.get("wrong", 1) != 0 or co.get("wrong_vs_old", 1) != 0:
            why.append(f"the setting's cells are not OFF=old / ON=new in memory (off {co}, on {cn})")
        else:
            own = {"cells": [co.get("cells"), cn.get("changed")]}
    pd = diff(off["png"], on["png"]) if off.get("png") and on.get("png") else -1.0
    if pd <= 0:
        why.append("no visible change (pixels equal)" if pd == 0 else "a picture could not be read")
    for other, osha in (others_on or {}).items():
        if other != setting and osha and osha == on.get("sha"):
            why.append(f"ON picture byte-identical to setting {other}'s ON picture")
    return {"valid": not why, "why": why, "pixel_diff": pd, "own_field": own}


# ------------------------------------------------------------------ the run
def parse_patch(path: str) -> dict:
    sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
    import importlib
    return importlib.import_module("ingame").parse_patch(open(path, encoding="ascii").read())


def cells_check(m: Mem, base: int, f: dict, want_new: bool) -> dict:
    bad = []
    for off, old, new in f["v"]:
        w = new if want_new else old
        if m.raw(base + off, len(w)) != w:
            bad.append(off)
    changed = sum(1 for _o, a, b in f["v"] if a != b)
    return {"cells": len(f["v"]), "changed": changed, "wrong": len(bad)}


class Stop(C.Stop):
    pass


class CheckRun(C.Run):
    def __init__(self, job: dict, *a, **kw):
        super().__init__(*a, **kw)
        self.job = job
        self.patch = None
        self.cell_files = job.get("cell_files") or []  # patch file names (rel endswith) whose cells a shot reads

    def press(self, buttons: str, gap: int = 25, at: int | None = None) -> int:
        """job yesno_left (round 64, moved here round 65): every A on a Yes/No question is LEFT A (Yes)"""
        if self.job.get("yesno_left") and buttons == "A":
            try:
                buttons = yesno_buttons(buttons, self.screen()["current"], True)
            except Exception:  # noqa: BLE001
                pass
        return super().press(buttons, gap, at)

    # -- records
    def cells(self) -> dict | None:
        if not self.patch or not self.cell_files:
            return None
        m = Mem(self.s)
        gd = m.gamedata()
        tot = {"cells": 0, "changed": 0, "wrong": 0}
        for f in self.patch["files"]:
            if f["kind"] != "dispos" and any(f["rel"].endswith(x) for x in self.cell_files):
                r = cells_check(m, gd, f, self.job.get("run") is not None)
                for k in tot:
                    tot[k] += r[k]
        if self.job.get("run") is None:
            tot = {"cells": tot["cells"], "wrong_vs_old": tot["wrong"]}
        return tot

    def rshot(self, label: str, focus: dict | None) -> dict:
        png = self.shot(label)
        sc = self.screen()
        hist = []
        for f, cur in self.res["screens"]:
            if not hist or hist[-1][1] != cur:
                hist.append([f, cur])
        rec = {"label": label, "frame": self.s.frame, "screen": sc["current"], "png": os.path.relpath(png, ROOT),
               "sha": sha(png), "focus": focus_fields(focus), "cells": self.cells(),
               "hist": hashlib.sha256(json.dumps(hist).encode()).hexdigest()[:16], "hist_tail": hist[-4:]}
        self.res.setdefault("records", {})[label] = rec
        return rec

    def army_unit(self, index: int = 0) -> dict | None:
        m = Mem(self.s)
        us = [u for u in m.units((0, 3))]
        return us[index] if 0 <= index < len(us) else None

    def cursor_unit(self) -> dict | None:
        b = self.s.board()
        cur = b.get("cursor")
        if not cur:
            return None
        for u in Mem(self.s).units((0, 1, 2)):
            if (u["x"], u["y"]) == tuple(cur):
                return u
        return None

    def touch(self, x: int, y: int, hold: int = 6) -> None:
        f = self.s.frame + 4
        self.s.inputs_add(",".join(f"{f + i}:@{x}x{y}" for i in range(hold)))
        self.wait(hold + 40)

    def back_to(self, screen: str, tries: int = 6) -> str:
        for _ in range(tries):
            cur = self.screen()["current"]
            if cur == screen:
                return cur
            self.press("B")
            self.wait(60)
        return self.screen()["current"]

    # -- prep screens
    def prep_screens(self) -> None:
        want = set(self.job.get("screens", []))
        st = self.res["steps"].setdefault("prep_screens", {})
        if self.screen()["current"] != C.PREP:
            st["skipped"] = f"no preparations ({self.screen()['current']})"
            return
        self.wait(30)
        if want & {"unitpage", "skillpage"}:
            self.press("A")
            st["units_screen"] = self.wait(90)["current"]
            foc = self.army_unit(0)
            self.rshot("unitpage", foc)
            if "skillpage" in want:
                for k, xy in enumerate(self.job.get("skill_touch", [TOUCH_SKILL]) or [None]):
                    if xy:
                        self.touch(*xy)
                    self.wait(40)
                    st[f"skill_screen{k}"] = self.screen()["current"]
                    self.rshot("skillpage" if not k else f"skillpage{k}", foc)
                    for kk in self.job.get("skill_keys", []):
                        self.press_wait(kk, after=40)
                        st[f"skill_{kk}"] = self.screen()["current"]
                        self.rshot(f"skillpage_{kk}", foc)
            st["back_units"] = self.back_to(C.PREP)
        if "growthview" in want:
            self.growth_view(st)
        seals = [k for k in ("mseal", "hseal") if k in want]
        if len(seals) > 1:   # round 59: the preparations menu keeps its cursor on Inventory after the first seal, so
            raise Stop("one seal screen per job (mseal or hseal)")  # the second DOWN DOWN lands on another item
        for kind in seals:
            self.seal_menu(kind, st)
        if self.back_to(C.PREP) != C.PREP:
            raise Stop("could not return to the preparations")

    def growth_view(self, st: dict) -> None:
        """Round 62 (F-049 goal 2): the growth view on the unit's stat page. Preparations > Units (A) > army unit
        growth_unit (DOWN presses); growth_page: touch the bottom screen's page icon first (the stats page);
        shots gv_stats, gv_stats2 (20 frames later: idle noise), then growth_keys (default SELECT) -> gv_growths,
        the same keys again -> gv_back; growth_touch [x, y] (the bottom-screen Growths button): touch ->
        gv_touch, touch -> gv_touch_back. Every shot names the unit (its growth_total = what the view must show).
        judge_growthview judges the toggle; judge_pair(growth_view) / judge_floor judge OFF/ON runs."""
        g = st.setdefault("growthview", {})
        self.press("A")
        g["units_screen"] = self.wait(90)["current"]
        army = Mem(self.s).units((0, 3))
        g["army_totals"] = {u["pid"]: focus_fields(u).get("growth_total") for u in army}  # the floor, every unit
        idx = int(self.job.get("growth_unit", 0))
        if self.job.get("growth_pid"):   # the unit by person id (the check step: one the floor moved)
            ids = [u["pid"] for u in army]
            if self.job["growth_pid"] not in ids:
                raise Stop(f"growth view: {self.job['growth_pid']} is not in the army")
            idx = ids.index(self.job["growth_pid"])
        g["unit_index"] = idx
        # the Preparations unit list is a grid (Select Units: 3 columns, army order row by row; round 62: DOWN
        # moves a whole row, so index 1 is RIGHT once, not DOWN once); growth_cols 1 for a one-column list
        cols = int(self.job.get("growth_cols", 3))
        for key, n in (("DOWN", idx // cols), ("RIGHT", idx % cols)):
            for _ in range(n):
                self.press(key)
                self.wait(20)
        g["grid_moves"] = [idx // cols, idx % cols, cols]
        foc = self.army_unit(idx)
        if self.job.get("growth_page"):
            self.touch(*TOUCH_PAGE)
            self.wait(40)
        self.wait(30)
        self.rshot("gv_stats", foc)
        self.wait(20)
        self.rshot("gv_stats2", foc)
        keys = self.job.get("growth_keys") or ["SELECT"]
        for lab in ("gv_growths", "gv_back"):
            for k in keys:
                self.press(k)
                self.wait(20)
            self.wait(40)
            g[lab + "_screen"] = self.screen()["current"]
            self.rshot(lab, foc)
        xy = self.job.get("growth_touch")
        if xy:
            for lab in ("gv_touch", "gv_touch_back"):
                self.touch(*xy)
                self.wait(30)
                g[lab + "_screen"] = self.screen()["current"]
                self.rshot(lab, foc)
        g["back"] = self.back_to(C.PREP)

    def growth_view_map(self) -> None:
        """Round 62: the same growth-view shots on the map (screen growthview_map): the cursor onto player unit
        growth_unit (Mem order of force 0), its bottom-screen panel (growth_page: the page icon touched first),
        then the shots and presses of growth_view (labels gv_*), then B back to the map. Round 62 finding: in the
        Preparations unit list SELECT is the game's own 'Start the battle?' question, so the core's growth view
        lives on a stat page, and the check step picks the screen (prep growthview or map growthview_map) and
        growth_keys / growth_touch from the core's notes."""
        g = self.res["steps"].setdefault("growthview_map", {})
        us = Mem(self.s).units((0,))
        g["army_totals"] = {u["pid"]: focus_fields(u).get("growth_total") for u in Mem(self.s).units((0, 3))}
        idx = int(self.job.get("growth_unit", 0))
        if self.job.get("growth_pid"):
            ids = [u["pid"] for u in us]
            if self.job["growth_pid"] not in ids:
                raise Stop(f"growth view: {self.job['growth_pid']} is not on the map")
            idx = ids.index(self.job["growth_pid"])
        if not 0 <= idx < len(us):
            g["skipped"] = f"no player unit {idx}"
            return
        u = us[idx]
        g["cursor"] = self.move_cursor(u["x"], u["y"])
        self.wait(30)
        foc = self.cursor_unit()
        if self.job.get("growth_page"):
            self.touch(*TOUCH_PAGE)
            self.wait(40)
        self.wait(30)
        self.rshot("gv_stats", foc)
        self.wait(20)
        self.rshot("gv_stats2", foc)
        keys = self.job.get("growth_keys") or ["SELECT"]
        for lab in ("gv_growths", "gv_back"):
            for k in keys:
                self.press(k)
                self.wait(20)
            self.wait(40)
            g[lab + "_screen"] = self.screen()["current"]
            self.rshot(lab, foc)
        xy = self.job.get("growth_touch")
        if xy:
            for lab in ("gv_touch", "gv_touch_back"):
                self.touch(*xy)
                self.wait(30)
                g[lab + "_screen"] = self.screen()["current"]
                self.rshot(lab, foc)
        g["back"] = self.back_to(C.HUMAN, tries=3)

    def boss_kill(self) -> None:
        """the bosskill screen: job dropcheck -> drop_check, job attack_unit -> unit_attack, else (job boss_look:
        boss_look first) the boss kill below (round 64's dispatch, moved here round 65)"""
        if self.job.get("dropcheck"):
            return self.drop_check()
        if self.job.get("attack_unit"):
            return self.unit_attack()
        if self.job.get("boss_look"):
            self.boss_look()
        return self._boss_kill()

    def _boss_kill(self) -> None:
        """Round 62 (F-049 goal 4's proof: 'the chapter runs past the boss's scenes with the new class'), cheat track
        in this copy only. At the map shot (job pre_turns N first: the guards walk out of the boss's way) the boss
        (job boss_pid: a substring of its person id; default the PID_<chapter>_ボス row, else a person id no other
        enemy has) is read (class, HP, items). Then waves (up to boss_waves, default 4): a player unit (job boss_attacker: index of the
        player units on the map, default 0, the next one each wave) gets move bonus 60 (unit +0x12C, as the cheat
        routes do), every enemy on the boss's tile (a pair-up: the lead takes the hits first) gets HP 1, and the
        unit walks to a free tile next to the boss and attacks (attack_keys, default A x6 after the unit command
        opens). If no tile is reachable in wave 0, a guard next to the boss is killed first. After a battle the
        robot answers the talk/event screens until the castle (M_Butler), a next chapter's preparations, a save
        question or the title (end), or the player phase is back with the boss still standing (next wave), or
        boss_frames frames. Up to boss_tries attempts from one memory slot (7 frames more waited each).
        Records (steps.bosskill): boss (before), attempts (waves, tries, screens), end_screen, chapter_before /
        after, boss_after, passed_scenes (an end screen reached after a stage-complete screen); shots
        bosskill_battle and bosskill_end."""
        st = self.res["steps"].setdefault("bosskill", {})
        us = Mem(self.s).units((0, 1))
        es = [u for u in us if u["force"] == 1 and u["hp"] > 0]
        want = self.job.get("boss_pid")
        if want:
            bs = [u for u in es if want in u["pid"]]
        else:   # the chapter's boss row is PID_<chapter>_ボス ('boss'); else a person id no other enemy has
            cnt = {}
            for u in es:
                cnt[u["pid"]] = cnt.get(u["pid"], 0) + 1
            bs = [u for u in es if "ボス" in u["pid"]] or [u for u in es if cnt[u["pid"]] == 1]
        if not bs:
            raise Stop(f"bosskill: no boss on the map (boss_pid {want})")
        boss = bs[0]
        st["boss"] = focus_fields(boss)
        k0 = int(self.job.get("boss_attacker", 0))
        want_att = self.job.get("boss_attacker_pid")   # round 72: the same attacker in the on and the off run

        def around(t, occ, free=True):
            out = [(t["x"] + dx, t["y"] + dy) for dx, dy in ((0, 1), (-1, 0), (1, 0), (0, -1))
                   if t["x"] + dx >= 0 and t["y"] + dy >= 0]
            return [xy for xy in out if (xy not in occ) == free]

        def boss_now():
            b = [u for u in Mem(self.s).units((1,)) if u["addr"] == boss["addr"] and u["hp"] > 0]
            return b[0] if b else None

        self.s.save_slot("bossroot")
        attempts, seen, end, ch0 = [], [], None, self.screen()["chapter"]
        for at_n in range(int(self.job.get("boss_tries", 4))):
            C.stop_check()
            if at_n:
                self.s.load_slot("bossroot")
                self.s.inputs_clear()
                self.wait(7 * at_n)
            att_rec = {"waves": []}
            attempts.append(att_rec)
            for wave in range(int(self.job.get("boss_waves", 4))):
                C.stop_check()
                b = boss_now()
                if b is None:
                    break
                us = Mem(self.s).units((0, 1))
                ps = attacker_order([u for u in us if u["force"] == 0 and u["hp"] > 0], want_att)
                if not ps:
                    break
                att = ps[(k0 + wave) % len(ps)]
                if want_att:
                    st.setdefault("attacker_pick", []).append([at_n, wave, att["pid"], len(ps)])
                stack = [u for u in us if u["force"] == 1 and u["hp"] > 0 and (u["x"], u["y"]) == (b["x"], b["y"])]
                occ = {(u["x"], u["y"]) for u in self.s.board()["units"]}
                tiles = around(b, occ)
                wr = {"attacker": [att["pid"], att["jid"], att["x"], att["y"]], "boss_at": [b["x"], b["y"]],
                      "stack": [u["pid"] for u in stack], "tiles": tiles, "tries": []}
                att_rec["waves"].append(wr)
                hit = self._attack_from(att, stack, tiles, f"b{at_n}w{wave}", wr)
                if not hit and wave == 0:
                    # round 62 (cq B010: the boss on a roof): a flier may reach where a walker cannot
                    fl = [u for u in ps if u["addr"] != att["addr"] and any(k in u["jid"] for k in FLIER_JOBS)]
                    wr["fliers"] = [u["pid"] for u in fl[:2]]
                    for fi, f in enumerate(fl[:2]):
                        if self._attack_from(f, stack, tiles, f"b{at_n}fly{fi}", wr):
                            hit, wr["attacker"] = True, [f["pid"], f["jid"], f["x"], f["y"]]
                            break
                if not hit and wave == 0:
                    # a boss walled in by its guards: a guard next to it is put at 1 HP and killed first, then the
                    # next unit takes its tile
                    es = [u for u in us if u["force"] == 1 and u["hp"] > 0]
                    guards = [u for u in es if (u["x"], u["y"]) in set(around(b, occ, free=False))
                              and (u["x"], u["y"]) != (b["x"], b["y"])]
                    wr["guards"] = [(g["pid"], g["x"], g["y"]) for g in guards]
                    for gi, g in enumerate(guards[:2]):
                        C.stop_check()
                        self.s.save_slot("guard")
                        if self._attack_from(att, [g], around(g, occ), f"guard{gi}", wr) and self._settle(wr, f"guard{gi}"):
                            gone = not [u for u in Mem(self.s).units((1,)) if u["addr"] == g["addr"] and u["hp"] > 0]
                            wr.setdefault("guard_killed", []).append([g["pid"], gone])
                            ps2 = attacker_order([u for u in Mem(self.s).units((0,)) if u["hp"] > 0
                                                  and u["addr"] != att["addr"]], want_att)
                            if gone and ps2:
                                a2 = ps2[k0 % len(ps2)]
                                wr["attacker2"] = [a2["pid"], a2["jid"], a2["x"], a2["y"]]
                                hit = self._attack_from(a2, stack, [(g["x"], g["y"])], f"boss_g{gi}", wr)
                                if hit:
                                    self.s.drop_slot("guard")
                                    break
                        self.s.load_slot("guard")
                        self.s.inputs_clear()
                        self.s.drop_slot("guard")
                if not hit:
                    wr["result"] = "no battle"
                    break
                self.shot("bosskill_battle")
                stop = {C.BUTLER, C.PREP, "MapFileMenu", "ChapterFileMenu"}
                calm = 0
                for _ in range(int(self.job.get("boss_frames", 9000)) // 30):
                    C.stop_check()
                    sc = self.wait(30)
                    cur = sc["current"] or ""
                    if not seen or seen[-1][1] != cur:
                        seen.append([self.s.frame, cur])
                        nt = len(st.setdefault("talk_pngs", []))
                        talky = "Talk" in cur or "Event" in cur or "TalkKeyWait" in sc["classes"]
                        if talky and nt < int(self.job.get("talk_shots", 0)):
                            self.wait(40)   # the window's text has come in
                            st["talk_pngs"].append(os.path.relpath(self.shot(f"bosskill_talk{nt}"), ROOT))
                    if cur in stop or cur.startswith(("title__", "castle__")) or (sc["chapter"] and sc["chapter"] != ch0):
                        end = cur   # round 62: the castle's own sequence after a stage complete counts (cq B008)
                        break
                    calm = calm + 1 if cur == C.HUMAN and "BattleSeq" not in sc["classes"] else 0
                    if calm >= 6:
                        break   # the player phase is back (the boss stands: next wave; or it died, no end yet)
                    if cur and "YesNo" in cur:
                        # round 63 (job yesno_left): Yes is the left choice; a boss's drop into a full inventory
                        # ('send one item to the convoy') otherwise loops (A018 Leo, A025 Iago)
                        self.press("LEFT A" if self.job.get("yesno_left") else "A")
                    elif "BattleSeq" in sc["classes"] or cur in C.ANSWER or "TalkKeyWait" in sc["classes"] or \
                            cur in ("GameMessage",) or "Event" in cur or "Complete" in cur:
                        self.press(C.ANSWER.get(cur) or "A")
                wr["result"] = end or ("boss stands" if boss_now() else "boss down, no chapter end")
                if end or boss_now() is None:
                    break
            att_rec["end_screen"] = end
            att_rec["boss_down"] = end is not None or boss_now() is None
            if att_rec["boss_down"]:
                break
            if att_rec["waves"] and att_rec["waves"][-1].get("result") == "no battle":
                break
        self.s.drop_slot("bossroot")
        st["attempts"] = attempts
        st.update(screens=seen, end_screen=end, chapter_before=ch0, chapter_after=self.screen()["chapter"],
                  boss_after="gone" if attempts and attempts[-1].get("boss_down") else "stands", frame_end=self.s.frame)
        self.shot("bosskill_end")
        # passed the boss's scenes: the boss is down and the game went on to the next player phase or to an end
        # screen (castle, preparations, save question, title) with no fault; talk screens after the kill named
        down = bool(attempts and attempts[-1].get("boss_down"))
        st["talk_after_kill"] = sorted({c for _f, c in seen if "Talk" in c or "Event" in c or "event" in c})
        st["stage_complete"] = any("Complete" in c for _f, c in seen)
        st["passed_scenes"] = down and (bool(end) or (seen and seen[-1][1] == C.HUMAN))
        if not any(w.get("result") not in (None, "no battle") for a in attempts for w in a["waves"]):
            raise Stop("bosskill: no battle with the boss (no reachable tile, nor after a guard)")

    def _attack_from(self, att: dict, targets: list, tiles: list, tag: str, st: dict) -> bool:
        """job place_next -> _place_attack (put next to the target), else _walk_attack (walk there)"""
        if self.job.get("place_next"):
            return self._place_attack(att, targets, tiles, tag, st)
        return self._walk_attack(att, targets, tiles, tag, st)

    def _walk_attack(self, att: dict, targets: list, tiles: list, tag: str, st: dict) -> bool:
        """bosskill's attack: from a memory slot per tile (up to 4), every target's HP -> 1 and att's move bonus
        -> 60 (cheat pokes in this copy), att picked (A), the cursor onto the tile, A: the unit command must open
        (else the tile is not reachable: B back, next tile), then attack_keys; True when a battle starts."""
        tries = st.setdefault("tries", [])
        slot = "ak_" + tag
        self.s.save_slot(slot)
        try:
            for n, (tx, ty) in enumerate(tiles[:4]):
                C.stop_check()
                if n:
                    self.s.load_slot(slot)
                    self.s.inputs_clear()
                tr = {"tag": tag, "unit": att["pid"], "targets": [t["pid"] for t in targets], "tile": [tx, ty]}
                tries.append(tr)
                self.poke([(int(t["addr"], 16) + 0xF3, b"\x01") for t in targets] +
                          [(int(att["addr"], 16) + 0x12C, bytes([60]))], f"{tag}{n}")
                tr["cursor_unit"] = self.move_cursor(att["x"], att["y"])
                self.press_wait("A", after=45)
                tr["cursor_tile"] = self.move_cursor(tx, ty)
                if self.job.get("boss_debug"):
                    self.shot(f"{tag}{n}_tile")
                self.press_wait("A", after=45)
                cur = self.screen()["current"] or ""
                tr["screens"] = [cur]
                for _ in range(60):   # a long walk (move bonus 60) takes many frames before the command opens
                    if "UnitCommand" in cur or cur == C.HUMAN:
                        break
                    cur = self.wait(15)["current"] or ""
                    if cur != tr["screens"][-1]:
                        tr["screens"].append(cur)
                if "UnitCommand" not in cur:
                    for _ in range(4):
                        self.press("B")
                        self.wait(30)
                    continue
                for k in self.job.get("attack_keys", ["A", "A", "A", "A", "A", "A"]):
                    self.press_wait(k, after=45)
                    tr["screens"].append(self.screen()["current"])
                    if "BattleSeq" in self.screen()["classes"]:
                        break
                sc = self.screen()
                for _ in range(60):
                    if "BattleSeq" in sc["classes"]:
                        break
                    sc = self.wait(10)
                tr["battle"] = "BattleSeq" in sc["classes"]
                if tr["battle"]:
                    return True
                for _ in range(4):
                    self.press("B")
                    self.wait(30)
            return False
        finally:
            self.s.drop_slot(slot)

    def _settle(self, st: dict, tag: str) -> bool:
        """after a battle: answers talk/event screens until the map's player phase is back and steady"""
        stable, seen = 0, []
        for _ in range(200):
            sc = self.wait(30)
            cur = sc["current"] or ""
            seen.append(cur)
            stable = stable + 1 if cur == C.HUMAN and "BattleSeq" not in sc["classes"] else 0
            if stable >= 3:
                st.setdefault("settle", {})[tag] = sorted(set(seen))
                return True
            if "BattleSeq" in sc["classes"] or cur in C.ANSWER or "TalkKeyWait" in sc["classes"]:
                self.press(C.ANSWER.get(cur) or "A")
        st.setdefault("settle", {})[tag] = sorted(set(seen)) + ["not settled"]
        return False

    # -- round 64's robot job keys (moved here round 65 from the round drivers; see the module's job key list)
    def find_grid(self) -> tuple:
        """the map's unit grid in this state (grid_search on the state's FCRAM); (address or None, FCRAM)"""
        import cheats as ch
        path = os.path.join(self.s.dir, "tmp", "grid-state.bin")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.s.save_file(path)
        with open(path, "rb") as fh:
            _head, secs = ch.split_state(fh.read())
        os.remove(path)
        fc = ch.decode_section(secs[1])
        g, hits = grid_search(fc, Mem(self.s).units((0, 1, 2)))
        self.res["steps"].setdefault("grid_search", []).append({"hits": [f"0x{h:08X}" for h in hits]})
        return g, fc

    def _place_attack(self, att: dict, targets: list, tiles: list, tag: str, st: dict) -> bool:
        """job place_next (round 64): the attacker is PUT on the tile (unit +0xF4/+0xF5 and the unit grid poked, the
        targets' HP -> 1; cheat pokes in this copy), picked there and told to stay (A, A): the unit command opens and
        it attacks (attack_keys). Armed-attacker swap: an attacker with no equipped weapon, or one that already acted
        in this attempt, gives its place to the next armed player unit. Talk skip (round 65, A023 Arthur): when the
        presses open a talk instead of the battle forecast, the tile is tried again from its memory slot with one
        more DOWN on the unit command before the attack keys (up to command_downs, default 3). job command_shots:
        shots of the unit command per try. When no tile starts a battle, the state before the call is loaded back
        (round 64's fliers began inside Arthur's talk)."""
        tries = st.setdefault("tries", [])
        at_key = tag.split("w")[0] if tag.startswith("b") else tag
        used = self.__dict__.setdefault("_used", {}).setdefault(at_key, set())
        arm = attacker_order([u for u in Mem(self.s).units((0,)) if u["addr"] != att["addr"]],
                             self.job.get("boss_attacker_pid"))
        att, swapped = pick_attacker(att, [att] + arm, used)
        if swapped:
            st["swapped_to"] = [att["pid"], att["jid"]]
        used.add(att["addr"])
        top = int(self.job.get("command_downs", 3))
        slot = "pk_" + tag
        self.s.save_slot(slot)
        first = True
        try:
            for n, (tx, ty) in enumerate(tiles[:4]):
                downs = 0
                while downs is not None:
                    C.stop_check()
                    if not first:
                        self.s.load_slot(slot)
                        self.s.inputs_clear()
                    first = False
                    tr = {"tag": tag, "unit": att["pid"], "targets": [t["pid"] for t in targets], "tile": [tx, ty],
                          "placed": True, "downs": downs}
                    tries.append(tr)
                    g, fc = self.find_grid()
                    tr["grid"] = f"0x{g:08X}" if g else None
                    if not g:
                        tr["screens"] = ["no unit grid found"]
                        break
                    v = fc[g - C.LINEAR + att["y"] * 32 + att["x"]]
                    there = fc[g - C.LINEAR + ty * 32 + tx]
                    tr["grid_value"], tr["grid_there"] = int(v), int(there)
                    if not v or there:
                        break
                    ua = int(att["addr"], 16)
                    self.poke([(int(t["addr"], 16) + 0xF3, b"\x01") for t in targets] +
                              [(ua + 0xF4, bytes([tx])), (ua + 0xF5, bytes([ty])),
                               (g + att["y"] * 32 + att["x"], b"\x00"), (g + ty * 32 + tx, bytes([v]))], f"{tag}p{n}")
                    tr["poke"] = True
                    self.wait(20)
                    tr["cursor_unit"] = self.move_cursor(tx, ty)
                    tr["unit_at_cursor"] = (self.cursor_unit() or {}).get("pid")
                    self.press_wait("A", after=45)
                    if self.job.get("boss_debug"):
                        self.shot(f"{tag}{n}_picked")
                    self.press_wait("A", after=45)
                    cur = self.screen()["current"] or ""
                    tr["screens"] = [cur]
                    for _ in range(20):
                        if "UnitCommand" in cur:
                            break
                        cur = self.wait(15)["current"] or ""
                        if cur != tr["screens"][-1]:
                            tr["screens"].append(cur)
                    if "UnitCommand" not in cur:
                        break
                    if self.job.get("command_shots"):
                        tr["command_png"] = os.path.relpath(self.shot(f"{tag}{n}_cmd{downs}"), ROOT)
                    for _ in range(downs):
                        self.press_wait("DOWN", after=20)
                    if downs and self.job.get("command_shots"):
                        tr["command_png_moved"] = os.path.relpath(self.shot(f"{tag}{n}_cmd{downs}_moved"), ROOT)
                    for k in self.job.get("attack_keys", ["A", "A", "A", "A", "A", "A"]):
                        self.press_wait(k, after=45)
                        sc = self.screen()
                        tr["screens"].append(sc["current"])
                        if "BattleSeq" in sc["classes"] or "TalkKeyWait" in sc["classes"]:
                            break
                    sc = self.screen()
                    for _ in range(60):
                        if "BattleSeq" in sc["classes"] or "TalkKeyWait" in sc["classes"]:
                            break
                        sc = self.wait(10)
                    if "TalkKeyWait" in sc["classes"] and "TalkKeyWait" not in tr["screens"]:
                        tr["screens"].append("TalkKeyWait")
                    tr["battle"] = "BattleSeq" in sc["classes"]
                    tr["outcome"] = command_outcome(tr["screens"], tr["battle"])
                    if tr["battle"]:
                        return True
                    if tr["outcome"] == "talk" and self.job.get("command_shots"):
                        tr["talk_png"] = os.path.relpath(self.shot(f"{tag}{n}_talk{downs}"), ROOT)
                    downs = next_downs(downs, tr["outcome"], top)
            self.s.load_slot(slot)   # nothing started a battle: back to the state before this call
            self.s.inputs_clear()
            self.wait(5)
            return False
        finally:
            self.s.drop_slot(slot)

    def boss_look(self) -> None:
        """job boss_look (round 64): the map cursor on the boss (job boss_pid), the shot boss_page: the bottom screen
        names the boss's class (the SEEN picture of a new class). job dump_state: the state kept in the job folder."""
        look = self.res["steps"].setdefault("boss_look", {})
        if look.get("png"):   # already taken in this run (a round driver that still wraps boss_kill with its own)
            return
        try:
            want = self.job.get("boss_pid")
            es = [u for u in Mem(self.s).units((1,)) if u["hp"] > 0 and want and want in u["pid"]]
            if not es:
                look["error"] = "boss not found"
                return
            b = es[0]
            look["cursor"] = self.move_cursor(b["x"], b["y"])
            self.wait(60)
            rec = self.rshot("boss_page", self.cursor_unit())
            if self.job.get("dump_state"):
                self.s.save_file(os.path.join(self.dir, "state-bosspage.bin"))
                look["units"] = [[u["force"], u["addr"], u["x"], u["y"], u["pid"]]
                                 for u in Mem(self.s).units((0, 1, 2))]
            look.update(png=rec["png"], focus_pid=(rec["focus"] or {}).get("pid"),
                        focus_jid=(rec["focus"] or {}).get("jid"))
        except Exception as e:  # noqa: BLE001
            look["error"] = repr(e)

    def enemy_look(self) -> None:
        """the enemy page shots (pairs.py's enemy_look with round 61's enemy_at and round 64's touch_page; drivers
        set P.enemy_look = rcheck.CheckRun.enemy_look). enemy_at [[x, y], ...]: these squares first, then unique
        people, then the nearest (enemy_order). touch_page: at the first enemy the bottom screen's page icon is
        touched once (shot page_simple before), so every enemy shot shows the full page (Atk/Hit/Crit/Avo).
        enemy_page: after each enemy shot, R opens its page (shot enemypage<k>)."""
        st = self.res["steps"].setdefault("enemies", {})
        es = [u for u in Mem(self.s).units((1,)) if u["hp"] > 0]
        cur = self.s.board().get("cursor") or [0, 0]
        want = self.job.get("enemy_at") or []
        pick = enemy_order(es, want, cur)[:int(self.job.get("enemy_count", 8))]
        st["picked"] = [(u["pid"], u["x"], u["y"]) for u in pick]
        if want:
            st["enemy_at"] = [list(p) for p in want]
        for k, u in enumerate(pick):
            C.stop_check()
            st.setdefault("cursor", []).append(self.move_cursor(u["x"], u["y"]))
            self.wait(30)
            if k == 0 and self.job.get("touch_page"):
                self.rshot("page_simple", self.cursor_unit())
                self.touch(*TOUCH_PAGE)
                self.wait(40)
                st["touched"] = self.screen()["current"]
            foc = self.cursor_unit()
            self.rshot(f"enemy{k}", foc)
            if self.job.get("enemy_page"):
                self.press("R")
                st.setdefault("page", []).append(self.wait(80)["current"])
                self.rshot(f"enemypage{k}", foc)
                st.setdefault("back", []).append(self.back_to(C.HUMAN, tries=3))
            if self.screen()["current"] != C.HUMAN:
                st["error"] = "could not return to the map"
                break

    def unit_attack(self) -> None:
        """job attack_unit PID_ (round 64): at the map shot that player unit attacks the nearest enemy (of the
        nearest 3) with bosskill's attack (target HP -> 1, move bonus 60: cheat pokes, the same in the OFF and ON
        job), so the battle shows the unit itself (the recolour). Shots attack0..3 at battle_offsets."""
        st = self.res["steps"].setdefault("unitattack", {})
        us = Mem(self.s).units((0, 1))
        me = [u for u in us if u["force"] == 0 and u["pid"] == self.job["attack_unit"] and u["hp"] > 0]
        if not me:
            raise Stop(f"unitattack: {self.job['attack_unit']} not on the map")
        me = me[0]
        occ = {(u["x"], u["y"]) for u in self.s.board()["units"]}
        es = sorted((u for u in us if u["force"] == 1 and u["hp"] > 0),
                    key=lambda u: (abs(u["x"] - me["x"]) + abs(u["y"] - me["y"]), u["x"], u["y"]))
        offs = [int(x) for x in self.job.get("battle_offsets", [100, 160, 220, 280])]
        for e in es[:3]:
            C.stop_check()
            tiles = free_around(e["x"], e["y"], occ, near=(me["x"], me["y"]))
            if self._attack_from(me, [e], tiles, f"ua{len(st.get('targets', []))}", st):
                f0 = self.s.frame
                st.setdefault("targets", []).append([e["pid"], e["jid"], e["x"], e["y"]])
                st["start"] = f0
                foc = next((u for u in Mem(self.s).units((0,)) if u["addr"] == me["addr"]), None)
                for k, o in enumerate(offs):
                    self.wait(max(1, f0 + o - self.s.frame))
                    self.rshot(f"attack{k}", foc)
                st["unit"] = focus_fields(foc)
                return
            st.setdefault("targets", []).append([e["pid"], e["jid"], e["x"], e["y"], "no battle"])
        raise Stop("unitattack: no battle started")

    def _items_of(self, addr: str) -> tuple:
        u = [x for x in Mem(self.s).units((0, 1, 2, 3)) if x["addr"] == addr]
        return (u[0]["items"], u[0]["hp"], u[0]["force"]) if u else (None, 0, None)

    def drop_check(self) -> None:
        """job dropcheck (round 64 goal 5, cheat track): does item word 2 bit 0x8000 make the enemy drop the item?
        {"flag_xy": [x, y], "plain_xy": [x, y], "attacker": army index (default 0), "iids": [...]}. From one memory
        slot at the map, four kills by the same player unit: flag_as_laid, flag_cleared (bit cleared), plain_as_laid,
        plain_flag_set (bit set on slot 1), each recording the target's and attacker's items before and after,
        the screens, and shots drop_<variant>_battle / _sN / _after; 'gained' = items_gained."""
        st = self.res["steps"].setdefault("dropcheck", {})
        cfg = self.job["dropcheck"]
        self.s.save_slot("droproot")
        nums = Mem(self.s).item_numbers()
        st["item_numbers"] = {k: v for k, v in nums.items() if k in cfg.get("iids", [])}
        variants = [("flag_as_laid", "flag_xy", None), ("flag_cleared", "flag_xy", "clear"),
                    ("plain_as_laid", "plain_xy", None), ("plain_flag_set", "plain_xy", "set")]
        out: dict = {}
        for n, (vname, key, mode) in enumerate(variants):
            C.stop_check()
            if n:
                self.s.load_slot("droproot")
                self.s.inputs_clear()
                self.wait(5)
            v = out.setdefault(vname, {})
            us = Mem(self.s).units((0, 1))
            tx, ty = cfg[key]
            tg = [u for u in us if u["force"] == 1 and u["hp"] > 0 and (u["x"], u["y"]) == (tx, ty)]
            ps = [u for u in us if u["force"] == 0 and u["hp"] > 0]
            if not tg or not ps:
                v["error"] = f"no enemy at {tx},{ty}" if not tg else "no player unit"
                continue
            t, att = tg[0], ps[int(cfg.get("attacker", 0)) % len(ps)]
            if mode:
                ws = drop_writes(int(t["addr"], 16), t["items"], mode)
                self.poke(ws, f"drop_{mode}")
                v["poked"] = [[f"{a:08x}", b.hex()] for a, b in ws]
            aa = int(att["addr"], 16)
            if all(x[0] for x in att["items"]):      # a free slot for the drop (else the convoy question)
                self.poke([(aa + 0x108 + 16, b"\0\0\0\0")], "drop_free_slot")
                v["freed_slot"] = True
            t_items, _hp, _f = self._items_of(t["addr"])
            a_items, _hp, _f = self._items_of(att["addr"])
            v.update(target=[t["pid"], t["jid"], tx, ty], target_items=t_items, attacker=[att["pid"], att["jid"]],
                     attacker_items_before=a_items)
            occ = {(u["x"], u["y"]) for u in self.s.board()["units"]}
            hit = self._attack_from(att, [t], free_around(tx, ty, occ), f"d{n}", v)
            v["battle"] = hit
            if not hit:
                continue
            self.shot(f"drop_{vname}_battle")
            seen, stable, shots = [], 0, 0
            for _ in range(220):
                C.stop_check()
                sc = self.wait(30)
                cur = sc["current"] or ""
                isb = "BattleSeq" in sc["classes"]
                if not seen or seen[-1][1] != cur:
                    seen.append([self.s.frame, cur])
                    if cur and cur != C.HUMAN and not isb and shots < 6:
                        self.shot(f"drop_{vname}_s{shots}")
                        shots += 1
                stable = stable + 1 if cur == C.HUMAN and not isb else 0
                if stable >= 4:
                    break
                if cur and "YesNo" in cur:
                    v.setdefault("yesno", []).append(cur)
                    self.press("A")
                elif isb or cur in C.ANSWER or "TalkKeyWait" in sc["classes"] or cur in ("GameMessage",) or \
                        "Event" in cur or "Message" in cur or "Item" in cur:
                    self.press(C.ANSWER.get(cur) or "A")
            v["screens"] = seen
            t_after, t_hp, _f = self._items_of(t["addr"])
            a_after, _hp, _f = self._items_of(att["addr"])
            v.update(target_after={"hp": t_hp, "items": t_after}, attacker_items_after=a_after)
            v["gained"] = items_gained(a_items, a_after)
            v["target_dead"] = t_hp == 0 or t_after is None
            self.shot(f"drop_{vname}_after")
        self.s.drop_slot("droproot")
        st["variants"] = out

    def seal_menu(self, kind: str, st: dict) -> None:
        """A seal into the first unit's last item slot (a cheat poke in this copy), then Inventory > that unit >
        Items > the seal > Use: the class change list (Master Seal: the promotions; Heart Seal: the reclass list)."""
        m = Mem(self.s)
        nums = m.item_numbers()
        iid = self.job.get(f"{kind}_iid") or ("IID_マスタープルフ" if kind == "mseal" else "IID_パラレルプルフ")
        if iid not in nums:
            cand = sorted(k for k in nums if "プルフ" in k)
            st[kind] = {"error": f"no {iid} in the item table (seal-like: {cand})"}
            return
        ui = int(self.job.get("seal_unit", 0))   # army index (the unit grid is 3 wide, in army order)
        u = self.army_unit(ui)
        slot = int(self.job.get("seal_slot", 4))
        addr = int(u["addr"], 16) + 0x108 + 4 * slot
        self.poke([(addr, struct.pack("<HH", nums[iid], int(self.job.get("seal_flags", 1))))], kind)
        info = {"iid": iid, "number": nums[iid], "unit": u["pid"], "slot": slot}
        self.press_wait("DOWN DOWN A", gap=30, after=60)   # Inventory
        info["inv"] = self.screen()["current"]
        nav = " ".join(["DOWN"] * (ui // 3) + ["RIGHT"] * (ui % 3))
        if nav:
            self.press_wait(nav, gap=30, after=40)
        self.press_wait("A", after=60)                      # the unit: Items / Trade / ...
        info["split"] = self.screen()["current"]
        self.press_wait("A", after=60)                      # Items: the unit's item list
        info["items"] = self.screen()["current"]
        self.rshot(f"{kind}_items", u)
        if slot:
            self.press_wait(" ".join(["DOWN"] * slot), gap=30, after=40)
        self.press_wait("A", after=60)                      # the seal: Store / Trade / Combine / Use
        info["seal_menu"] = self.screen()["current"]
        self.rshot(f"{kind}_menu", u)
        self.press_wait("DOWN DOWN DOWN", gap=30, after=40)  # Use
        self.press_wait("A", after=90)                      # Use: the class list
        info["class_list"] = self.screen()["current"]
        self.rshot(kind, self.army_unit(ui))
        for k in self.job.get(f"{kind}_keys", []):
            self.press_wait(k, after=40)
            self.rshot(f"{kind}_{k}", self.army_unit(ui))
        st[kind] = info
        self.back_to(C.PREP, tries=8)

    # -- map screens
    def child_look(self) -> None:
        """The child of a child paralogue on the map ('other' force): the cursor on him, his panel and R page.
        Round 62: job key child_turns N: when no 'other' unit stands on the map at the start (Revelation and
        Conquest X015: the child arrives later), up to N turns are ended (chapsel's End > enemy phase > player
        phase) and the force is read again after each."""
        others = [u for u in Mem(self.s).units((2,))]
        st = {"others": [(u["pid"], u["x"], u["y"]) for u in others]}
        self.res["steps"]["child"] = st
        waited = []
        for k in range(int(self.job.get("child_turns", 0))):
            if others:
                break
            C.stop_check()
            if self.screen()["current"] != C.HUMAN:
                self.drive({C.HUMAN}, max_steps=100)
            self.map_and_enemy_phase()
            others = [u for u in Mem(self.s).units((2,))]
            waited.append({"turn": k + 2, "others": [(u["pid"], u["x"], u["y"]) for u in others],
                           "frame": self.s.frame})
        if waited:
            st["turns_waited"] = waited
            st["others"] = [(u["pid"], u["x"], u["y"]) for u in others]
        if not others and self.res.get("army"):
            # round 62: a child who starts in the player army (no 'other' unit at the start nor after 3 turns in
            # Revelation X015, nor in Conquest X015 in round 61): the player unit on the map that the base save's
            # army does not hold
            have = {a.get("pid") for a in self.res["army"]}
            newp = [u for u in Mem(self.s).units((0,)) if u["pid"] not in have]
            st["new_player"] = [(u["pid"], u["x"], u["y"]) for u in newp]
            if newp:
                others = newp[:1]
                st["child_force"] = 0
        if not others:
            st["skipped"] = "no unit of the 'other' force on the map"
            return
        u = others[0]
        st["cursor"] = self.move_cursor(u["x"], u["y"])
        self.wait(30)
        foc = self.cursor_unit()
        self.rshot("childhover", foc)
        self.press("R")
        st["page_screen"] = self.wait(80)["current"]
        self.rshot("childpage", foc)
        st["back"] = self.back_to(C.HUMAN, tries=3)

    def levelup(self) -> None:
        """Every player unit's exp -> 99 (a cheat poke in this copy), then End: the first unit an enemy attacks and
        that lives gains a level in the enemy phase. The level-up window is shot; its unit is read from memory."""
        m = Mem(self.s)
        ps = [u for u in m.units((0,))]
        writes = [(int(u["addr"], 16) + 0xF2, b"\x63") for u in ps if u["exp"] < 99 and u["level"] < 40]
        st = {"poked": len(writes)}
        self.res["steps"]["levelup"] = st
        if not writes:
            st["skipped"] = "no unit to poke"
            return
        self.poke(writes, "exp99")
        before = {u["addr"]: (u["pid"], u["level"], u["hp"]) for u in Mem(self.s).units((0,))}
        self.empty_tile_menu("UP")
        self.press("A")
        seen, left, stable, allc = None, None, 0, set()
        turns = int(self.job.get("levelup_turns", 1))  # round 60: Conquest maps where no enemy attacks on turn 1
        st["turns"] = 1
        prev = {a: b[1] for a, b in before.items()}
        changes = st.setdefault("level_changes", [])   # round 60: [frame, pid, old, new] each time a level rose

        def track():
            for u in Mem(self.s).units((0,)):
                if u["addr"] in prev and u["level"] != prev[u["addr"]]:
                    changes.append([self.s.frame, u["pid"], prev[u["addr"]], u["level"]])
                prev[u["addr"]] = u["level"]
        for _ in range(1200 * turns):
            sc = self.wait(10)
            if turns > 1:
                track()
            cur = sc["current"]
            cls = sc["classes"] + [cur or ""]
            allc.update(cls)
            if not st.get("trans") or st["trans"][-1][1] != cur:
                st.setdefault("trans", []).append([self.s.frame, cur])
            if "BattleSeq" in sc["classes"] and not st.get("battle_shot"):
                st["battle_shot"] = self.shot("levelup_battle")
            if any(k in c for c in cls for k in self.job.get("levelup_marks", ("Grow", "LevelUp", "LvUp"))):
                seen = sc
                break
            if cur and "YesNo" in cur:
                self.press("LEFT A")
            if left is None and cur not in (C.HUMAN, C.SYSMENU, None):
                left = self.s.frame
            stable = stable + 1 if (cur == C.HUMAN and left) else 0
            if stable >= 20:
                if st["turns"] >= turns:
                    break
                st["turns"] += 1          # back on the map with no level-up: End the next turn too
                stable, left = 0, None
                self.empty_tile_menu("UP")
                self.press("A")
                continue
            if "BattleSeq" in sc["classes"] or "TalkKeyWait" in sc["classes"]:
                if _ % 3 == 0:
                    self.press("A")
        st["classes_seen"] = sorted(allc)
        if not seen:  # defending gave no experience (a unit that cannot strike back gets none): attack instead
            seen = self.player_attack(st, before)
        if not seen:
            st["levels_after"] = [(u["pid"], before.get(u["addr"], (0, 0))[1], u["level"], u["exp"], u["hp"])
                                  for u in Mem(self.s).units((0,))]
            st["error"] = "no level-up (enemy phase and player attack)"
            return
        st["screen"] = seen["current"]
        st["classes"] = [c for c in seen["classes"] if "Grow" in c or "Level" in c or "Exp" in c]
        # round 60: the levels when the window was seen; after several turns an earlier level-up must not count
        mid = {u["addr"]: u["level"] for u in Mem(self.s).units((0,))}
        self.wait(int(self.job.get("levelup_wait", 10)))
        # the unit: the one whose level rose, else the attacker (the window comes after the exp bar fills)
        lv = None
        for u in Mem(self.s).units((0,)):
            b = before.get(u["addr"])
            if b and u["level"] != b[1] and st["turns"] == 1:
                lv = u
        atk = (st.get("attack") or [{}])[-1].get("unit")
        if lv is None and atk:
            lv = next((u for u in Mem(self.s).units((0,)) if u["pid"] == atk), None)
        if self.job.get("levelup_skip"):
            self.wait(int(self.job["levelup_skip"]))
        for k in range(int(self.job.get("levelup_shots", 12))):   # the exp bar, then the level-up window
            if k:
                self.wait(int(self.job.get("levelup_step", 30)))
            self.rshot("levelup" if not k else f"levelup{k + 1}", lv)
        if lv is None:
            # round 60: the window shows while the exp bar fills, before the level is written: the unit is the one
            # whose level rose by the last shot (read once after the shots), and every shot of this window is about it
            track()
            # the unit of this window: the last one whose level rose (an earlier turn's level-up came before it)
            last = changes[-1][1] if changes else None
            # two units can gain a level in one battle (a pair-up partner too): the window shows the lead unit
            # first; both are named so a reviewer checks the picture's name and level against them
            same = [c for c in changes if changes and c[0] == changes[-1][0]]
            if len(same) > 1:
                st["level_up_candidates"] = same
            units = Mem(self.s).units((0,))
            if last:
                lv = next((u for u in units if u["pid"] == last), None)
            else:
                lv = next((u for u in units if u["addr"] in mid and u["level"] != mid[u["addr"]]), None)
            if lv is not None:
                st["unit_after_shots"] = lv["pid"]
                for lab, rec in self.res.get("records", {}).items():
                    if lab.startswith("levelup") and lab != "levelup_battle" and rec.get("focus") is None:
                        rec["focus"] = focus_fields(lv)
        st["unit"] = lv["pid"] if lv else None


def _player_attack(self, st: dict, before: dict):
    """A player unit (level < 20) next to an enemy attacks it (A on the unit, A in place, Attack, weapon, target,
    confirm); a level-up shows when its exp was 99. Up to 4 pairs, each from a memory slot. Returns a screen
    record when a level rose, else None."""
    m = Mem(self.s)
    us = m.units((0, 1))
    ps = [u for u in us if u["force"] == 0 and u["level"] < 20 and u["hp"] > 0]
    es = [u for u in us if u["force"] == 1 and u["hp"] > 0]
    pairs = [(p, e) for p in ps for e in es if abs(p["x"] - e["x"]) + abs(p["y"] - e["y"]) == 1]
    st["attack_pairs"] = [(p["pid"], e["pid"], p["x"], p["y"], e["x"], e["y"]) for p, e in pairs[:6]]
    tries = []
    self.s.save_slot("atk")
    for n, (p, e) in enumerate(pairs[:4]):
        C.stop_check()
        if n:
            self.s.load_slot("atk")
            self.s.inputs_clear()
        tr = {"unit": p["pid"], "enemy": e["pid"]}
        if self.job.get("enemy_hp1", True):  # the enemy at 1 HP (a cheat poke in this copy): the attack kills it
            self.poke([(int(e["addr"], 16) + 0xF3, b"\x01")], "enemyhp1")
        tr["cursor"] = self.move_cursor(p["x"], p["y"])
        for k in self.job.get("attack_keys", ["A", "A", "A", "A", "A", "A"]):
            self.press_wait(k, after=45)
            tr.setdefault("screens", []).append(self.screen()["current"])
        seen = None
        for _ in range(250):
            sc = self.wait(10)
            lv = {u["addr"]: u["level"] for u in Mem(self.s).units((0,))}
            if any(before.get(a) and lv[a] != before[a][1] for a in lv) or any(
                    "Grow" in c or "LevelUp" in c for c in sc["classes"]):
                seen = sc
                tr["classes_at"] = sc["classes"][:40]
                break
            if sc["current"] == C.HUMAN and _ > 120:
                break
        tries.append(tr)
        if seen:
            st["attack"] = tries
            self.s.drop_slot("atk")
            return seen
    st["attack"] = tries
    self.s.drop_slot("atk")
    return None


def _stuck(r) -> None:
    """One picture of where a failed job stopped (the server may already be gone)."""
    try:
        if r.s is not None and not r.s.closed and not os.path.exists(C.STOP_FILE):
            r.shot("stuck")
            r.res["stuck_classes"] = r.screen()["classes"][:40]
    except Exception:  # noqa: BLE001
        pass


def run_job(job: dict) -> dict:
    C.stop_check()
    game = job.get("game", "fates")
    target = job.get("chapter", "none")
    base = job.get("base") or C.pick_base(target, route=job.get("path"))
    r = CheckRun(job, target, base, job["name"], game, job.get("route_byte"), "all", job.get("timeout", 900))
    if os.path.isdir(r.dir):
        shutil.rmtree(r.dir)
    os.makedirs(r.dir)
    r.res["job"] = job
    r.res["exe"] = C.SERVER_KW.get("exe")
    r.lend = job.get("lend", "locked")
    srv_root = os.path.join(r.dir, "server")
    rid = job.get("run")
    run_src = os.path.join(RUNS, game, rid) if rid else None
    ref = job.get("ref_run") or rid
    if ref:
        r.patch = parse_patch(os.path.join(RUNS, game, ref, "patch.txt"))
    extra_env = {"FEF_RANDO_TOOL": os.path.join(ROOT, "tools", "randomizer"), "FEF_PYTHON": sys.executable,
                 "RUST_LOG": "info"}
    if game == "seal":
        extra_env["FEF_RANDO_GAME"] = "seal"
    if job.get("rust_log"):   # round 60: e.g. "info,zakuro_core::services::fs=debug" (the files the game opens)
        extra_env["RUST_LOG"] = job["rust_log"]
    import headless as hl
    import server as sv
    orig = hl.lay_save

    def lay(zip_path, data_dir):
        names = orig(zip_path, data_dir)
        if not hl.below(os.path.abspath(data_dir), os.path.join(ROOT, "build")):
            raise Stop(f"{data_dir}: not below build/")
        if game == "seal":
            dst = os.path.join(data_dir, "mods", TITLE)
            if not os.path.isdir(dst):
                shutil.copytree(SEALMOD, dst)
        if rid:
            shutil.copytree(run_src, os.path.join(data_dir, "rando", TITLE, "runs", rid))
            sl = os.path.join(data_dir, "rando", TITLE, "slots")
            os.makedirs(sl, exist_ok=True)
            for slot in job.get("slots", ["Chapter0.json"]):
                with open(os.path.join(sl, slot), "w") as fh:
                    fh.write(json.dumps({"format": 1, "run": rid, "save": slot}) + "\n")
        return names

    def lay_reload(data_dir):  # the reload server: the seal mod copy and the first server's rando folder
        if game == "seal":
            dst = os.path.join(data_dir, "mods", TITLE)
            if not os.path.isdir(dst):
                shutil.copytree(SEALMOD, dst)
        src = os.path.join(srv_root, job["name"], "data", "rando")
        if os.path.isdir(src):
            dst = os.path.join(data_dir, "rando")
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)

    t0 = time.time()
    hl.lay_save = lay
    try:
        with sv.Server(job["name"], save=base, root=srv_root, timeout=job.get("timeout", 900), cheat=True,
                       extra_env=extra_env, **C.SERVER_KW) as s:
            try:
                r.s = s
                mode = job.get("mode", "select")
                if mode == "route":
                    rin = json.load(open(os.path.join(ROOT, "config", "harness", "routes.json"),
                                         encoding="utf-8"))["routes"][job["route"]]["input"]
                    s.inputs_set(",".join(x for x in rin.split(",") if x and int(x.split(":")[0]) <= job["last"]))
                    for f in job["shots"]:
                        C.stop_check()
                        s.step_to(f)
                        r.rshot(f"route{f}", None)
                else:
                    if mode == "direct":
                        r.direct(s)
                    else:
                        r.select(s)
                    r.res["status_at_start"] = str(s.cmd("rando-status"))
                    r.prep_screens()
                    if r.screen()["current"] == C.PREP:
                        r.press("START")
                        r.wait(40)
                        r.drive({C.HUMAN}, max_steps=200)
                    sc = r.wait(20)
                    if sc["current"] != C.HUMAN:
                        r.drive({C.HUMAN}, max_steps=100)
                    r.rshot("map", r.cursor_unit())
                    if job.get("item_numbers"):   # round 62: {iid: item number} as laid (the ladder judge)
                        r.res["item_numbers"] = Mem(s).item_numbers()
                    if "growthview_map" in job.get("screens", []):
                        r.growth_view_map()
                    if "bosskill" in job.get("screens", []):
                        r.boss_kill()
                    if "child" in job.get("screens", []):
                        r.child_look()
                    if "levelup" in job.get("screens", []):
                        r.levelup()
                    if job.get("steps") == "full":   # chapsel's End > enemy phase > player phase, then save + reload
                        if r.screen()["current"] != C.HUMAN:
                            r.drive({C.HUMAN}, max_steps=100)
                        r.map_and_enemy_phase()
                        if job.get("save", True):
                            hl.lay_save = orig
                            r.save_and_reload(srv_root, extra_env, lay_reload)
            except Exception:
                _stuck(r)
                raise
            r.res["ok"] = True
    except C.Stop as e:
        r.res["ok"] = False
        r.res["error"] = str(e)
    except Exception as e:  # noqa: BLE001
        r.res["ok"] = False
        r.res["error"] = f"{type(e).__name__}: {e}"
        r.res["trace"] = traceback.format_exc()
    finally:
        hl.lay_save = orig
        r.res["seconds"] = round(time.time() - t0, 1)
        faults = []
        for top, _d, fs in os.walk(srv_root):
            for fn in fs:
                if fn.endswith(".log"):
                    try:
                        low = open(os.path.join(top, fn), "rb").read().decode("utf-8", "replace").lower()
                    except OSError:
                        continue
                    faults += [f"{fn}: {w}" for w in ("panic", "guest fault", "data abort", "prefetch abort",
                                                      "undefined instruction") if w in low]
        r.res["log_faults"] = sorted(set(faults))
        if job.get("log_grep"):   # round 60: the server log lines holding any of these texts, in log order
            hits = []
            for top, _d, fs in os.walk(srv_root):
                for fn in sorted(fs):
                    if fn.endswith(".log"):
                        try:
                            raw = open(os.path.join(top, fn), "rb").read()
                        except OSError:
                            continue
                        at = 0   # each hit with the byte offset of its line (p60's log_at_map splits by it)
                        for ln in raw.split(bytes([10])):
                            t = ln.decode("utf-8", "replace")
                            if any(w in t for w in job["log_grep"]):
                                hits.append(f"{fn}@{at}: {t.strip()[-200:]}")
                            at += len(ln) + 1
            r.res["log_lines"] = hits[:400]
        r.res["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(r.dir, "result.json"), "w", encoding="utf-8") as fh:
            json.dump(r.res, fh, indent=1, ensure_ascii=False)
        if not job.get("keep_server"):
            shutil.rmtree(srv_root, ignore_errors=True)
    return r.res


def direct(self, s):
    """Chapters 2-6 from the chapter N-1 clear save: Continue goes straight on into chapter N."""
    self.s = s
    # round 59: the full title presses (round 58 cut them after 700:A and the title's demo ran for 30,000 frames:
    # ProcMovie / ProcEffect / ProcJobIntro / ProcJobGroup are the title's attract loop, START leaves it)
    s.inputs_set(",".join(x for x in C.CASTLE_PRESSES.split(",") if int(x.split(":")[0]) <= 2400))
    s.step_to(2500)
    demo = {"ProcMovie", "ProcEffect", "ProcJobIntro", "ProcJobGroup"}
    n = {"k": 0}

    def title(sc):
        cur = sc["current"] or ""
        if cur.startswith("title__") or cur in ("MapFileMenu", "ChapterFileMenu"):
            self.press("A")
        elif cur in demo and not sc.get("chapter"):
            n["k"] += 1
            self.press("START" if n["k"] % 2 else "A")
    sc = self.drive({C.PREP, C.HUMAN}, max_steps=500, extra=title)
    self.res["steps"]["start"] = {"frame": s.frame, "screen": sc["current"], "chapter": sc["chapter"]}
    if sc["chapter"] != self.target:
        raise C.Stop(f"the chapter that started reads {sc['chapter']}, not {self.target}")


CheckRun.direct = direct
CheckRun.player_attack = _player_attack


# ------------------------------------------------------------------ pairs
def judge_file(pairs_path: str) -> dict:
    """pairs file: [{"setting", "chapter", "screen" (record label), "off": job name, "on": job name}]. The ON shots
    of every other setting at the same chapter and label are gathered for rule 4."""
    pairs = json.load(open(pairs_path, encoding="utf-8"))
    jobs = os.path.join(OUT, "jobs")

    def rec(job, label):
        p = os.path.join(jobs, job, "result.json")
        if not os.path.isfile(p):
            return None
        r = json.load(open(p, encoding="utf-8"))
        x = (r.get("records") or {}).get(label)
        if x:
            x = dict(x, png=os.path.join(ROOT, x["png"]))
        return x
    out = []
    for p in pairs:
        off, on = rec(p["off"], p["screen"]), rec(p["on"], p["screen"])
        if not off or not on:
            out.append(dict(p, valid=False, why=["a shot is missing"]))
            continue
        others = {}
        for q in pairs:
            if q is not p and q["chapter"] == p["chapter"] and q["screen"] == p["screen"]:
                o = rec(q["on"], q["screen"])
                if o:
                    others[q["setting"]] = o["sha"]
        out.append(dict(p, **judge_pair(off, on, p["setting"], others), off_png=off["png"], on_png=on["png"],
                        off_unit=(off.get("focus") or {}).get("pid"), on_unit=(on.get("focus") or {}).get("pid")))
    res = {"pairs": out, "valid": sum(1 for x in out if x["valid"]), "rejected": sum(1 for x in out if not x["valid"])}
    with open(os.path.splitext(pairs_path)[0] + ".verdicts.json", "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, ensure_ascii=False)
    return res


# ------------------------------------------------------------------ self-test (invented records, no game)
def selftest() -> tuple[list[str], int]:
    bad, n = [], 0

    def check(c, what):
        nonlocal n
        n += 1
        if not c:
            bad.append(what)
    u = {"pid": "PID_A", "growth": [1, 2, 3, 4, 5, 6, 7, 8], "jid": "JID_X", "skills": [1, 0, 0, 0, 0]}
    u2 = dict(u, growth=[9, 2, 3, 4, 5, 6, 7, 8])
    base = {"screen": "S", "frame": 100, "png": "a", "sha": "1"}
    off = dict(base, focus=u)
    on = dict(base, focus=u2, png="b", sha="2")
    d1 = lambda a, b: 0.01 if a != b else 0.0  # noqa: E731
    r = judge_pair(off, on, "growths", {}, diff=d1)
    check(r["valid"], "a true pair is valid")
    check(not judge_pair(off, dict(on, frame=101), "growths", {}, diff=d1)["valid"], "another frame is rejected")
    check(not judge_pair(off, dict(on, screen="T"), "growths", {}, diff=d1)["valid"], "another screen is rejected")
    check(not judge_pair(off, dict(on, focus=dict(u2, pid="PID_B")), "growths", {}, diff=d1)["valid"],
          "another unit under the cursor is rejected")
    check(not judge_pair(off, dict(on, focus=dict(u)), "growths", {}, diff=d1)["valid"],
          "the setting's own field equal is rejected")
    check(not judge_pair(off, on, "skill_slots", {}, diff=d1)["valid"], "a pair whose difference is another field "
          "(growths) does not prove skill slots")
    check(not judge_pair(off, dict(on, png="a"), "growths", {}, diff=d1)["valid"], "equal pixels are rejected")
    check(not judge_pair(off, on, "growths", {"bases": "2"}, diff=d1)["valid"],
          "an ON picture byte-identical to another setting's ON picture is rejected")
    check(judge_pair(off, on, "growths", {"growths": "2", "bases": "3"}, diff=d1)["valid"],
          "its own sha and other shas do not reject")
    check(not judge_pair(dict(off, focus=None), on, "growths", {}, diff=d1)["valid"], "one side without a unit")
    check(not judge_pair(dict(off, hist="aa"), dict(on, hist="bb"), "growths", {}, diff=d1)["valid"],
          "runs that went through different screens before the shot (a timing shift) are rejected")
    check(judge_pair(dict(off, hist="aa"), dict(on, hist="aa"), "growths", {}, diff=d1)["valid"],
          "the same screen history is fine")
    # settings judged by cells (no unit field): shops
    offc = dict(base, focus=None, cells={"cells": 40, "wrong_vs_old": 0})
    onc = dict(base, focus=None, png="b", sha="2", cells={"cells": 40, "changed": 12, "wrong": 0})
    check(judge_pair(offc, onc, "shops", {}, diff=d1)["valid"], "cells: OFF old, ON new, changed: valid")
    check(not judge_pair(offc, dict(onc, cells={"cells": 40, "changed": 12, "wrong": 3}), "shops", {}, diff=d1)["valid"],
          "cells: ON not holding the new values is rejected")
    check(not judge_pair(dict(offc, cells={"cells": 40, "wrong_vs_old": 2}), onc, "shops", {}, diff=d1)["valid"],
          "cells: OFF not holding the old values is rejected")
    check(not judge_pair(offc, dict(onc, cells={"cells": 40, "changed": 0, "wrong": 0}), "shops", {}, diff=d1)["valid"],
          "cells: nothing changed is rejected")
    # round 62: the growth view's toggle (one run) and the floor (OFF/ON)
    gfoc = focus_fields(dict(u, job_growth=[10] * 8))
    check(gfoc["growth_total"] == [11, 12, 13, 14, 15, 16, 17, 18], "growth_total = personal + class")
    tab = {("st", "st2"): 0.001, ("st", "gr"): 0.2, ("st", "bk"): 0.0005, ("st", "same"): 0.0005}
    dd = lambda a, b: 0.0 if a == b else tab.get((a, b), 0.3)  # noqa: E731
    gv = lambda png: dict(base, png=png, focus=gfoc)  # noqa: E731
    check(judge_growthview(gv("st"), gv("st2"), gv("gr"), gv("bk"), diff=dd)["valid"], "growth view: a toggle is valid")
    check(not judge_growthview(gv("st"), gv("st2"), gv("same"), gv("bk"), diff=dd)["valid"],
          "growth view: a press that changes no more than the idle noise is rejected (the current exe)")
    check(not judge_growthview(gv("st"), gv("st2"), gv("gr"), gv("gr"), diff=dd)["valid"],
          "growth view: a second press that does not bring the stats back is rejected")
    check(not judge_growthview(gv("st"), gv("st2"), dict(gv("gr"), focus=dict(gfoc, pid="PID_B")), gv("bk"),
                               diff=dd)["valid"], "growth view: another unit is rejected")
    check(not judge_growthview(gv("st"), gv("st2"), None, gv("bk"), diff=dd)["valid"], "growth view: a missing shot")
    low = focus_fields(dict(u, growth=[40, 30, 0, 30, 30, 30, 20, 10], job_growth=[10, 10, 0, 5, 5, 5, 5, 0]))
    hi = focus_fields(dict(u, growth=[50, 35, 15, 40, 35, 30, 20, 25], job_growth=[10, 10, 5, 5, 5, 5, 5, 0]))
    offf, onf = dict(base, focus=low), dict(base, focus=hi, png="b", sha="2")
    check(judge_floor(offf, onf, diff=d1)["valid"], "floor: OFF has a total under 20, ON all 20..100: valid")
    check(not judge_floor(offf, dict(onf, focus=dict(hi, growth_total=[60, 45, 19, 45, 40, 35, 25, 25])),
                          diff=d1)["valid"], "floor: an ON total of 19 is rejected")
    check(not judge_floor(offf, dict(onf, focus=dict(hi, growth_total=[101, 45, 20, 45, 40, 35, 25, 25])),
                          diff=d1)["valid"], "floor: an ON total of 101 is rejected")
    check(not judge_floor(dict(offf, focus=hi), dict(onf, focus=dict(hi, growth_total=[61, 46, 21, 46, 41, 36, 26,
                                                                                         26])), diff=d1)["valid"],
          "floor: an OFF unit with no total under 20 cannot show the floor")
    check(judge_pair(offf, onf, "growth_view", {}, diff=d1)["valid"], "growth view OFF/ON: totals differ: valid")
    check(not judge_pair(offf, dict(onf, focus=low), "growth_view", {}, diff=d1)["valid"],
          "growth view OFF/ON: equal totals are rejected")
    check(judge_same(offf, dict(offf), diff=d1)["valid"], "same: an unchanged unit, equal pictures: valid")
    check(not judge_same(offf, onf, diff=d1)["valid"], "same: a changed growth is rejected")
    check(not judge_same(offf, dict(offf, png="b"), diff=d1)["valid"], "same: differing pictures are rejected")
    # round 62: the weapon ladder per difficulty and the boss boost (invented ids)
    n2i = {1: "IID_B", 2: "IID_I", 3: "IID_S", 4: "IID_KILL", 5: "IID_YATO", 6: "IID_VUL"}
    rung = {"IID_B": "IID_I", "IID_I": "IID_S", "IID_S": None}
    E = [[0, 0]] * 4
    jl = lambda a, b, d: judge_ladder([a] + E, [b] + E, d, rung, n2i, {"IID_YATO"})["valid"]  # noqa: E731
    check(jl([1, 0x4000], [1, 0x4100], "easy"), "ladder easy: +1 forge")
    check(not jl([1, 0x4000], [2, 0x4000], "easy"), "ladder easy: a next rung is not allowed")
    check(jl([1, 0x4000], [2, 0x4000], "normal"), "ladder normal: the next rung")
    check(jl([2, 0x4000], [2, 0x4100], "normal"), "ladder normal: +1 forge (next rung not holdable)")
    check(not jl([1, 0x4000], [3, 0x4000], "normal"), "ladder normal: two rungs (Bronze -> Steel) rejected")
    check(jl([2, 0x4000], [3, 0x4100], "hard"), "ladder hard: next rung and +1 forge")
    check(jl([3, 0x4000], [3, 0x4200], "hard"), "ladder hard: top rung, +2 forges")
    check(not jl([2, 0x4000], [3, 0x4000], "hard"), "ladder hard: the next rung without the forge rejected")
    check(jl([4, 0x4000], [4, 0x4100], "normal") and jl([4, 0x4000], [4, 0x4200], "hard"),
          "ladder: Killer/Brave/effective forge only")
    check(not jl([4, 0x4000], [3, 0x4000], "normal"), "ladder: a Killer weapon never becomes another item")
    check(not jl([5, 0x4000], [5, 0x4100], "hard"), "ladder: Yato never moves")
    check(not jl([1, 0x4000], [1, 0x4000], "easy"), "ladder: nothing changed is rejected")
    check(not jl([3, 0x4700], [3, 0x4800], "easy"), "ladder: forge past 7 rejected")
    bo = {"pid": "PID_X_ボス", "hp": 33, "person_base": [13, 0, 0, 0, 0, 0, 0, 0], "job_base": [20] + [0] * 7,
          "items": [[2, 0x4000], [5, 0], [6, 0x100], [0, 0], [0, 0]]}
    bn = lambda hp, it: dict(bo, hp=hp, items=it)  # noqa: E731
    check(judge_boost(bo, bn(37, [[2, 0x4100], [5, 0], [6, 0x100], [0, 0], [0, 0]]), "easy", True, n2i,
                      {"IID_YATO"})["valid"], "boost easy: +10% of 33 = 4 HP, might +1 shown")
    check(judge_boost(bo, bn(43, [[2, 0x4300], [5, 0], [6, 0x100], [0, 0], [0, 0]]), "hard", True, n2i,
                      {"IID_YATO"})["valid"], "boost hard: +30% = 10 HP, might +3 shown")
    check(not judge_boost(bo, bn(43, [[2, 0x4200], [5, 0], [6, 0x100], [0, 0], [0, 0]]), "hard", True, n2i,
                          {"IID_YATO"})["valid"], "boost hard: might +2 shown (round 62's forge count) is rejected")
    check(judge_boost(bo, bn(40, [[2, 0x4200], [5, 0], [6, 0x100], [0, 0], [0, 0]]), "normal", True, n2i,
                      {"IID_YATO"})["valid"], "boost normal: +20% = 7 HP, might +2 shown")
    check(not judge_boost(bo, bn(40, [[2, 0x4100], [5, 0], [6, 0x100], [0, 0], [0, 0]]), "normal", True, n2i,
                          {"IID_YATO"})["valid"], "boost normal: might +1 shown is rejected")
    check(judge_boost(bo, bn(40, [[2, 0x4100], [5, 0], [6, 0x100], [0, 0], [0, 0]]), "normal", True, n2i,
                      {"IID_YATO"}, might_add=lambda n, a, b: 2 * (b - a))["valid"],
          "boost normal: a +2-per-level row gives might +2 with one level")
    check(judge_boost(dict(bo, items=[[2, 0x4600]] + bo["items"][1:]),
                      bn(43, [[2, 0x4700], [5, 0], [6, 0x100], [0, 0], [0, 0]]), "hard", True, n2i,
                      {"IID_YATO"})["forge_capped"] == [0], "boost hard: forge 6 -> 7 stops at the maximum (capped)")
    check(not judge_boost(bo, bn(45, [[2, 0x4300], [5, 0], [6, 0x100], [0, 0], [0, 0]]), "hard", True, n2i,
                          {"IID_YATO"})["valid"], "boost: an army boss's HP must rise exactly")
    check(judge_boost(bo, bn(45, [[2, 0x4300], [5, 0], [6, 0x100], [0, 0], [0, 0]]), "hard", False, n2i,
                      {"IID_YATO"})["valid"], "boost: a non-joining boss may rise more (the linear buff)")
    check(not judge_boost(bo, bn(43, [[2, 0x4300], [5, 0x100], [6, 0x100], [0, 0], [0, 0]]), "hard", True, n2i,
                          {"IID_YATO"})["valid"], "boost: Yato forged is rejected")
    check(not judge_boost(bo, bn(37, [[2, 0x4000], [5, 0], [6, 0x100], [0, 0], [0, 0]]), "easy", True, n2i,
                          {"IID_YATO"})["valid"], "boost: no forge is rejected")
    # round 66: "capped" passes only at the real cap (personal-base HP, from the run's own tables)
    hc = lambda hp, pb, cap, diff="hard", off=bo: judge_boost(  # noqa: E731
        off, dict(bo, hp=hp, person_base=[pb] + bo["person_base"][1:],
                  items=[[2, 0x4000 + 0x100 * STEP[diff]]] + bo["items"][1:]), diff, True, n2i, {"IID_YATO"}, hp_cap=cap)
    check(hc(40, 20, 20)["valid"] and hc(40, 20, 20)["capped"], "capped: +7 of 10 with the ON personal HP 20 at cap 20")
    check(not hc(40, 20, 25)["valid"], "capped: a fake cap 25 (ON 20 is below it) is rejected")
    check(not hc(40, 20, None)["valid"], "capped: no cap given, a short rise is rejected")
    check(not hc(40, 20, 18)["valid"], "capped: ON above a cap 18 is rejected")
    check(not hc(40, 18, 18)["valid"], "capped: shown rise 7 but personal rise 5 is rejected")
    check(hc(33, 13, 10)["valid"] and hc(33, 13, 10)["capped"], "capped: already above its cap 10, HP stays (rise 0)")
    check(not hc(33, 13, 15)["valid"], "capped: rise 0 below a cap 15 is rejected")
    check(hc(43, 23, None)["valid"] and not hc(43, 23, None)["capped"], "capped: a full rise needs no cap")

    class _T:   # a passed-in tables stand-in for boss_hp_cap (F-047): unit_job only
        jobs = {"JID_A": {"base.hp": "17", "max.hp": "40"}, "JID_B": {"base.hp": "20", "max.hp": "50"}}

        def unit_job(self, r):
            return self.jobs.get(r.get("job", ""))
    check(boss_hp_cap(_T(), {"job": "JID_A"}) == 23, "boss_hp_cap: class max 40 - class base 17 = 23")
    check(boss_hp_cap(_T(), {"job": "JID_A", "limit_mod.hp": "2"}) == 25, "boss_hp_cap: + the limit modifier")
    check(boss_hp_cap(_T(), {"job": "JID_A"}, "JID_B") == 30, "boss_hp_cap: the run's class (memory jid) wins")
    check(boss_hp_cap(_T(), {"job": "JID_Z"}) is None, "boss_hp_cap: an unknown class gives None")
    # round 65: round 64's robot job keys, moved into this file (pure parts and the dispatch)
    arm_u = {"addr": "30000000", "hp": 20, "items": [[5, 0x4000], [0, 0]]}
    sing_u = {"addr": "30000140", "hp": 20, "items": [[9, 0x0000], [0, 0]]}
    arm2_u = {"addr": "30000280", "hp": 20, "items": [[0, 0], [7, 0x4001]]}
    dead_u = {"addr": "300003C0", "hp": 0, "items": [[5, 0x4000]]}
    check(is_armed(arm_u) and is_armed(arm2_u) and not is_armed(sing_u), "armed: bit 0x4000 on any held item")
    check(pick_attacker(arm_u, [sing_u, arm2_u], set()) == (arm_u, False), "swap: an armed unit keeps its turn")
    check(pick_attacker(sing_u, [sing_u, dead_u, arm2_u], set()) == (arm2_u, True),
          "swap: a singer gives way to the next living armed unit (round 64 B025 Azura)")
    check(pick_attacker(arm_u, [arm_u, arm2_u], {"30000000"}) == (arm2_u, True), "swap: a unit that acted gives way")
    check(pick_attacker(sing_u, [sing_u], set()) == (sing_u, False), "swap: nobody armed keeps the unit")
    # round 72: attacker_order (the round-64 note: an index named different units in the on and off runs)
    pa = [{"pid": "PID_C", "addr": "1"}, {"pid": "PID_A", "addr": "2"}, {"pid": "PID_B", "addr": "3"}]
    pb = [pa[2], pa[0], pa[1]]   # the same units in another pool order (round 66 R016)
    check(attacker_order(pa) == pa and attacker_order(pb) == pb, "attacker order: no pid wanted keeps the pool order")
    check(attacker_order(pa, "PID_C") == attacker_order(pb, "PID_C"), "attacker order: the same list in any pool order")
    check(attacker_order(pb, "PID_C")[0]["pid"] == "PID_C", "attacker order: the wanted person first")
    check([u["pid"] for u in attacker_order(pa, "PID_C")] == ["PID_C", "PID_A", "PID_B"],
          "attacker order: the others by person id")
    check([u["pid"] for u in attacker_order(pb, ["PID_B", "PID_C"])] == ["PID_B", "PID_C", "PID_A"],
          "attacker order: a list of wanted persons in the order given")
    check(attacker_order(pa, "PID_Z") == attacker_order(pb, "PID_Z") and attacker_order(pa, "PID_Z")[0]["pid"] == "PID_A",
          "attacker order: a wanted person not on the map still gives one order")
    check(free_around(0, 5, {(1, 5)}) == [(0, 6), (0, 4)], "tiles: off-map and taken tiles left out")
    check(free_around(5, 5, set(), near=(9, 5))[0] == (6, 5), "tiles: nearest to the attacker first")
    try:
        import numpy  # noqa: F401
        fc = bytearray(4096)
        g0 = 1000
        for i in range(0, 4096, 7):
            fc[i] = (i * 13) % 251   # noise
        for i in range(32 * 32):
            fc[g0 + i] = 0
        us = []
        for k, (x, y) in enumerate([(3, 4), (10, 2), (7, 7), (20, 15), (5, 30), (0, 0), (31, 9), (14, 21)]):
            us.append({"addr": f"{0x30010000 + (k + 2) * 0x140:08X}", "hp": 10, "x": x, "y": y})
            fc[g0 + y * 32 + x] = k + 5          # pool number = slot + a constant
        pair = {"addr": f"{0x30010000 + 9 * 0x140:08X}", "hp": 10, "x": 3, "y": 4}   # a pair-up: not on the grid
        g, hits = grid_search(fc, us + [pair], linear=C.LINEAR)
        check(g == C.LINEAR + g0 and hits == [C.LINEAR + g0], "grid: found where every unit stands (pair-up left out)")
        odd = dict(us[1], x=12)   # one unit drawn elsewhere: still found (two misses allowed)
        g2, _h = grid_search(fc, [us[0], odd] + us[2:], linear=C.LINEAR)
        check(g2 == C.LINEAR + g0, "grid: one odd unit does not hide it")
        g3, _h = grid_search(bytearray(4096), us, linear=C.LINEAR)
        check(g3 is None, "grid: no grid in memory -> None")
        check(grid_search(fc, us[:2], linear=C.LINEAR)[0] is None, "grid: under 3 single units -> None (no guess)")
    except ImportError:
        check(False, "numpy missing")
    talk = ["map__anonymous_namespace__UnitCommand", "map__anonymous_namespace__ProcSequence", "TalkKeyWait"]
    fight = ["map__anonymous_namespace__UnitCommand", "map__anonymous_namespace__ProcSequence", "ProcBattleInfo"]
    check(command_outcome(talk) == "talk", "command: a talk window before any forecast = Talk was picked (A023)")
    check(command_outcome(fight) == "battle" and command_outcome(talk, battle=True) == "battle",
          "command: the forecast or a battle = attack")
    check(command_outcome(["map__anonymous_namespace__UnitCommand", "ItemMenu"]) == "none", "command: other menus")
    check(next_downs(0, "talk", 3) == 1 and next_downs(1, "none", 3) == 2, "talk skip: one more DOWN after a talk")
    check(next_downs(0, "none", 3) is None, "talk skip: a plain failure at no DOWN is the tile's (next tile)")
    check(next_downs(3, "talk", 3) is None and next_downs(1, "battle", 3) is None, "talk skip: capped; done on battle")
    check(yesno_buttons("A", "YesNoDialog", True) == "LEFT A", "yesno_left: A on a question is LEFT A")
    check(yesno_buttons("A", "YesNoDialog", False) == "A" and yesno_buttons("B", "YesNoDialog", True) == "B" and
          yesno_buttons("A", "map", True) == "A", "yesno_left: off, other buttons, other screens unchanged")
    its = [[5, 0x8001], [7, 0x0002], [0, 0x8000], [9, 0x8000], [0, 0]]
    check(drop_writes(0x30000000, its, "clear") == [(0x30000108 + 2, struct.pack("<H", 1)),
                                                     (0x30000108 + 14, struct.pack("<H", 0))],
          "drop: clear takes bit 0x8000 off every held item that has it (empty slots skipped)")
    check(drop_writes(0x30000000, [[7, 2], [5, 0]], "set") == [(0x3000010A, struct.pack("<H", 0x8002))],
          "drop: set puts bit 0x8000 on the slot-1 item only")
    check(drop_writes(0x30000000, its, None) == [], "drop: as laid pokes nothing")
    check(items_gained([[5, 0], [7, 0], [0, 0]], [[5, 0], [7, 0], [12, 0]]) == [12], "drop: the new item is gained")
    check(items_gained([[5, 0], [5, 0]], [[5, 0], [5, 0], [5, 0]]) == [5] and items_gained([[5, 0]], [[5, 0]]) == [],
          "drop: a multiset difference (a second copy counts; nothing new = nothing)")
    es = [{"pid": "PID_G", "x": 1, "y": 1}, {"pid": "PID_G", "x": 9, "y": 9}, {"pid": "PID_BOSS", "x": 8, "y": 8},
          {"pid": "PID_G", "x": 5, "y": 5}]
    check([(u["x"], u["y"]) for u in enemy_order(es, [[9, 9]], [0, 0])] == [(9, 9), (8, 8), (1, 1), (5, 5)],
          "enemy_at first, then unique people, then the nearest")

    class _S:
        frame = 100

        def __init__(self):
            self.inputs = []

        def inputs_add(self, spec):
            self.inputs.append(spec)

    class _Fake(CheckRun):
        def __init__(self, job, cur="map"):   # no server: only the dispatch is tested
            self.job, self.calls, self.s, self._cur = job, [], _S(), cur

        def screen(self):
            return {"current": self._cur, "classes": []}

        def drop_check(self):
            self.calls.append("drop")

        def unit_attack(self):
            self.calls.append("unit")

        def boss_look(self):
            self.calls.append("look")

        def _boss_kill(self):
            self.calls.append("kill")

        def _place_attack(self, *a):
            self.calls.append("place")
            return True

        def _walk_attack(self, *a):
            self.calls.append("walk")
            return False
    for job, want in (({"dropcheck": {"flag_xy": [1, 1]}}, ["drop"]), ({"attack_unit": "PID_X"}, ["unit"]),
                      ({"boss_look": True}, ["look", "kill"]), ({}, ["kill"])):
        f = _Fake(job)
        f.boss_kill()
        check(f.calls == want, f"dispatch: bosskill with {sorted(job) or 'no keys'} -> {want}")
    f = _Fake({"place_next": True})
    check(f._attack_from({}, [], [], "b0w0", {}) is True and f.calls == ["place"], "dispatch: place_next attacks placed")
    f = _Fake({})
    check(f._attack_from({}, [], [], "b0w0", {}) is False and f.calls == ["walk"], "dispatch: default is the walk")
    f = _Fake({"yesno_left": True}, cur="YesNoDialog")
    f.press("A")
    check(f.s.inputs == ["104:LEFT,129:A"], "press: yesno_left turns A on a question into LEFT A")
    f = _Fake({}, cur="YesNoDialog")
    f.press("A")
    check(f.s.inputs == ["104:A"], "press: without yesno_left an A stays A")
    # round 70: the chest / village judge (pure)
    plan = [{"chapter": "A007", "kind": "chest", "orig": "IID_A", "new": "IID_B", "calls": [], "x": 3, "y": 4}]
    n2i = {1: "IID_A", 2: "IID_B", 9: "IID_Z"}
    check(judge_chest(plan, "A007", None, [[9, 1]], [[9, 1], [2, 1]], n2i, x=3, y=4)["ok"],
          "chest: the planned item in the unit's slots passes")
    check(judge_chest(plan, "A007", "IID_A", [[9, 1]] * 5, [[9, 1]] * 5, n2i, [], [[2, 1]])["ok"],
          "chest: a full inventory's item in the convoy passes")
    check(not judge_chest(plan, "A007", "IID_A", [], [[1, 1]], n2i)["ok"], "chest: the original item fails (hook off)")
    check(judge_chest([], "A007", "IID_A", [], [[1, 1]], n2i)["ok"], "chest: an off run must give the original")
    check(not judge_chest(plan, "A007", "IID_A", [], [], n2i)["ok"], "chest: nothing gained fails")
    # round 73b, round 72's B010 village pattern: the item lands in a full bag and the game sends another bag item
    # (Corrin's Dragonstone, here item 7) to the convoy; one net item was gained, not two
    vil = [{"chapter": "B010", "kind": "village", "orig": "IID_A", "new": "IID_B", "calls": [], "x": 5, "y": 6}]
    bag = [[9, 1], [7, 1], [8, 1], [9, 2], [8, 2]]
    r = judge_chest(vil, "B010", None, bag, [[9, 1], [2, 1], [8, 1], [9, 2], [8, 2]], n2i, [[8, 3]], [[8, 3], [7, 1]],
                    x=5, y=6)
    check(r["ok"] and r["got"] == "IID_B", f"chest: a bag item moved to the convoy is not a second gain ({r})")
    r = judge_chest(vil, "B010", None, bag, [[9, 1], [1, 1], [8, 1], [9, 2], [8, 2]], n2i, [[8, 3]], [[8, 3], [7, 1]],
                    x=5, y=6)
    check(not r["ok"] and r["got"] == "IID_A", "chest: the moved-item case still catches the original item")
    check(judge_chest(vil, "B010", None, bag, bag, n2i, [[8, 3]], [[8, 3], [2, 1]], x=5, y=6)["ok"],
          "chest: the new item sent straight to the convoy (bag unchanged) passes")
    # pixel diff on real pictures
    try:
        from PIL import Image
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            a, b, c = (os.path.join(d, x + ".png") for x in "abc")
            Image.new("RGB", (4, 4), (0, 0, 0)).save(a)
            Image.new("RGB", (4, 4), (0, 0, 0)).save(b, compress_level=1)
            im = Image.new("RGB", (4, 4), (0, 0, 0))
            im.putpixel((1, 1), (255, 0, 0))
            im.save(c)
            check(pixel_diff(a, b) == 0.0, "pixels: same picture, other file bytes -> 0")
            check(pixel_diff(a, c) == round(1 / 16, 5), "pixels: one pixel of 16")
    except ImportError:
        check(False, "PIL missing")
    return bad, n


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", default=OUT)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("run")
    p.add_argument("lane")
    p.add_argument("--redo", action="store_true")
    q = sub.add_parser("pairs")
    q.add_argument("pairs")
    a = ap.parse_args(argv)
    if a.selftest:
        bad, n = selftest()
        print(f"rcheck selftest: {n - len(bad)}/{n}")
        for b in bad:
            print("  FAIL", b)
        return 1 if bad else 0
    setup(a.out)
    if a.cmd == "run":
        import ctypes
        if os.name == "nt":
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
        jobs = json.load(open(a.lane, encoding="utf-8"))
        log = a.lane + ".log"
        for job in jobs:
            if os.path.exists(C.STOP_FILE):
                open(log, "a").write("STOP_ROUND\n")
                return 3
            done = os.path.join(C.OUT_TOP, job["name"], "result.json")
            if os.path.isfile(done) and not a.redo:
                continue
            res = run_job(job)
            open(log, "a").write(json.dumps({"name": job["name"], "ok": res.get("ok"), "err": res.get("error"),
                                             "s": res.get("seconds")}, ensure_ascii=False) + "\n")
        open(log, "a").write("DONE\n")
        return 0
    if a.cmd == "pairs":
        res = judge_file(a.pairs)
        print(json.dumps({"valid": res["valid"], "rejected": res["rejected"]}))
        for x in res["pairs"]:
            print(x["setting"], x["chapter"], x["screen"], "VALID" if x["valid"] else "REJECTED", x["why"])
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
