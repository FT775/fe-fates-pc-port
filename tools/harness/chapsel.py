#!/usr/bin/env python3
"""The robot's CHAPTER SELECT on the cheat track (docs/tests/CHAPSEL.md; owner F-047, 2026-11-20: "enable a chapter
select cheat to allow yourself to test every chapter without a slow playthrough"). Standard library only.

It starts any chapter of a path in a headless boot-server copy, from a packed test save, and drives it through the
places a randomizer check needs: battle preparations, the unit list and a unit's page, the inventory, the map with
its enemies, the first enemy phase, a battle save and its reload. It is a robot test on the cheat track (docs/CHEATS.md):
never real play, never the owner's saves, settings, cheat file or mods; every file it makes is below build/.

How a chapter is selected (no engine change, no game file changed):
  1. A base save of the same path is loaded (the nearest packed clear save before the chapter: its army is that
     path's units at about that chapter's level). Title > Continue opens the castle's Preparations (frame ~3400).
  2. At frame 3590 the boot-server's state is saved to a file, and two kinds of bytes are changed in its FCRAM
     section (cheats.py's savestate helpers; every changed page is first checked equal to live memory):
       - the world-map spot record of the target chapter (68-byte records, +0 the Chapter record pointer, +4 u16
         state 0 locked / 1 open / 2 cleared): state -> 1 (open);
       - GameUserData (*0x006DA248) +0xC, the current chapter pointer, -> the target's Chapter record
         (table + index * 28), and +0x2E the route byte (0 A / 1 B / 2 C; for Seal of Flames the mod's own).
     The state is loaded back (the same moment, only those bytes differ).
  3. B, START (butler), DOWN x4, A: Next Battle opens the world-map spot list. The target is now listed. The robot
     tries list positions (a memory slot before the list; DOWN p times, A, Yes) until the chapter the game decided
     on (GameUserData +0xC after Yes) is the target; anything else is undone by loading the slot.
  4. The chapter's own events run (talk/movie skipped with START/A, as robot/auto.py answers them) up to battle
     preparations (sortie TopMenu) or straight to the first player phase.

Chapters with no spot in the base save's path (another path's chapter) are refused: pick a base of that path.
The prologue (CID_A000) is the new game itself (routes new-game / bt-prologue); chapters 1-5 run back to back
without a castle, so they are selected from the first castle save (bt-ch6-clear) through their (cleared) spots.

    python tools/harness/chapsel.py --selftest                 invented memory: spot finding, base pick, patching
    python tools/harness/chapsel.py plan A015 X007 B020        which base save each chapter would use
    python tools/harness/chapsel.py run A015 [--base SAVE] [--game seal] [--name N] [--steps all|prep]
                                                               one chapter, headless; result.json + PNGs below
                                                               build/r58/chapsel/<name>/
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.append(HERE)

OUT_TOP = os.path.join(ROOT, "build", "r58", "chapsel")
STOP_FILE = os.path.join(ROOT, "build", "STOP_ROUND")
SAVES = os.path.join(ROOT, "build", "harness", "saves")
TITLE = "0004000000179800"
SEAL_MODS = os.path.join(ROOT, "play", "seal-of-flames", "data", "mods", TITLE)  # read only: copied, never run

GD_ARCH, GUD = 0x006D3868, 0x006DA248   # GameData archive holder; GameUserData pointer (docs/ROUTES_SPLIT.md)
GUD_CHAPTER, GUD_ROUTE = 0xC, 0x2E
REC = 28                                # Chapter record size; +0 the CID string pointer, +8 its index byte
SPOT_SIZE = 68                          # world-map spot record; +0 Chapter pointer, +4 u16 state
LINEAR = 0x30000000
PAGE = 0x1000
CASTLE_PRESSES = "300:A,700:A,1200:START,1500:START,2000:A,2400:A,2800:A,3200:A"  # title > Continue > castle
POKE_FRAME = 3590
ANSWER = {  # robot/auto.py's answers: screens that need no decision
    "TalkKeyWait": "A", "TalkUtil__ProcBind": "A", "ProcTutorialViewer": "START", "ProcMovie": "START",
    "GameMessage": "A", "event__anonymous_namespace__ProcEvent": "A",
    "map__SequenceCompleteEffect__anonymous_namespace__ProcSequence": "A",
    # round 59: chapter 6's route choice (bt-ch6-castle answers it with A = the first item, Birthright; the Yes
    # after it is the YesNo rule below), seen in the A006 direct start
    "anonymous_namespace__EventDialog@00626DB0": "A",
    # round 59 check: a unit with a full inventory gets an item in the enemy phase (an enemy drop, more often with
    # Enemy drops on): the game asks which item goes to the convoy; A sends the highlighted one (rv C012 all3, C026)
    "map__anonymous_namespace__ItemMenuSend": "A",
}
PREP = "sortie__anonymous_namespace__TopMenu"
HUMAN = "map__SequenceHuman__anonymous_namespace__ProcSequence"
SPOTS = "castle__anonymous_namespace__M_SpotSelectTop"
SYSMENU = "map__anonymous_namespace__SystemMenu"
BUTLER = "castle__anonymous_namespace__M_Butler"
SERVER_KW: dict = {}   # extra sv.Server arguments (rcheck.py: a frozen exe/lib copy below build/r59/robot/bin)


class Stop(Exception):
    """A setup problem or build/STOP_ROUND: nothing more is started."""


def stop_check() -> None:
    if os.path.exists(STOP_FILE):
        raise Stop("build/STOP_ROUND exists")


# ------------------------------------------------------------------ which base save
REAL = {"A": "bt", "B": "cq", "C": "rv"}
# chapters whose clear save of the chapter before stops at the butler (a forced first build) or a castle event
# (round 58: A007, A016, B007, B016, C007, C016, C017 never reached the Preparations): they start from their OWN
# clear save instead (the spot is cleared, state 2 -> 1; proven for A007 and A016 in round 59)
OWN_CLEAR = {"A007", "A016", "B007", "B016", "C007", "C017"}
# C016: rv-ch15-clear stops at a castle event and rv-ch16-clear's Continue goes straight onto chapter 17's map, so
# it starts from rv-ch14-clear (its castle visit opens the Preparations; proven in round 59)
BASE_FIX = {"C016": 14}
RV_NO_CASTLE = {15, 16}   # Revelation clear saves whose Continue does not open the castle (see BASE_FIX)


def saves_of(prefix: str, folder: str = SAVES) -> dict[int, str]:
    """{chapter N: name} of the packed real-play clear saves <prefix>-chN-clear (never cheat-*)."""
    out = {}
    if os.path.isdir(folder):
        for fn in os.listdir(folder):
            m = re.fullmatch(re.escape(prefix) + r"-ch(\d+)-clear\.zip", fn)
            if m:
                out[int(m.group(1))] = fn[:-4]
    return out


def pick_base(cid: str, folder: str = SAVES, route: str | None = None) -> str:
    """The base save for chapter cid (without the CID_ prefix): the nearest real clear save of its path before it,
    at least the first castle save (chapter 6 clear) of that path."""
    m = re.fullmatch(r"([ABC])(\d{3})", cid)
    if m:
        letter, n = m.group(1), int(m.group(2))
        pre = REAL[letter] if n >= 6 else (route or "bt")
        have = saves_of(pre, folder)
        if cid in OWN_CLEAR and n in have:   # round 59: the save before opens the butler or a castle event
            return have[n]
        if cid in BASE_FIX and BASE_FIX[cid] in have:
            return have[BASE_FIX[cid]]
        ok = [k for k in have if 6 <= k < max(n, 7)]
        if not ok:
            raise Stop(f"{cid}: no {pre}-chN-clear save (N 6..{max(n, 7) - 1}) in {folder}")
        return have[max(ok)]
    m = re.fullmatch(r"X(\d{3})", cid)
    if m:
        n = int(m.group(1))
        pre = route or ("bt" if n <= 14 else "cq")
        if n >= 15 and pre == "bt" or 7 <= n <= 14 and pre == "cq":
            raise Stop(f"{cid}: not a paralogue of path {pre} (docs/ROUTES.md)")
        have = saves_of(pre, folder)
        want = 12 if n <= 6 else 16   # mid-path army: the paralogues open from about there
        if pre == "rv" and n >= 7:
            # round 62: rv-ch16-clear's Continue goes straight onto chapter 17's map and rv-ch15-clear stops at a
            # castle event (the 8 stopped Revelation paralogue pair jobs of round 61); and from rv-ch12-clear the
            # Nohrian children's paralogues (X015-) place no child: their parents (Xander, Leo, ...) join in
            # chapter 17. rv-ch18-clear is My Castle after chapter 18 (title > Continue > castle).
            want = 18
        ok = [k for k in have if 6 <= k <= want and not (pre == "rv" and k in RV_NO_CASTLE)]
        if not ok:
            raise Stop(f"{cid}: no {pre} clear save")
        return have[max(ok)]
    raise Stop(f"{cid}: give --base for this chapter (not a Birthright/Conquest/Revelation chapter or paralogue id)")


# ------------------------------------------------------------------ memory readers (live, through the server)
class Live:
    def __init__(self, s):
        self.s = s

    def u32(self, a: int) -> int:
        return struct.unpack("<I", self.s.peek1(a, 4))[0] if a else 0

    def raw(self, a: int, n: int) -> bytes:
        return self.s.peek1(a, n)

    def cstr(self, a: int, n: int = 24) -> str:
        if not a:
            return ""
        try:
            return self.raw(a, n).split(b"\0")[0].decode("cp932", "replace")
        except Exception:  # noqa: BLE001
            return ""

    def tables(self) -> dict:
        arch = self.u32(GD_ARCH)
        a = self.u32(arch + 4) if arch else 0
        b = self.u32(a + 112) if a else 0
        gd = b + 32 if b else 0
        tab, cnt = (self.u32(gd), self.u32(gd + 4)) if gd else (0, 0)
        gud = self.u32(GUD)
        ids = []
        if tab and 0 < cnt < 400:
            blob = self.raw(tab, cnt * REC)
            ids = [self.cstr(struct.unpack_from("<I", blob, k * REC)[0], 16).replace("CID_", "") for k in range(cnt)]
        cp = self.u32(gud + GUD_CHAPTER) if gud else 0
        cur = ids[(cp - tab) // REC] if cp and tab and (cp - tab) % REC == 0 and 0 <= (cp - tab) // REC < cnt else None
        return {"table": tab, "count": cnt, "gud": gud, "ids": ids, "chapter_ptr": cp, "chapter": cur,
                "route": self.raw(gud + GUD_ROUTE, 1)[0] if gud else None}

    def person_id(self, per: int) -> str:
        for i in range(0, 16, 4):
            t = self.cstr(self.u32(per + i), 24)
            if t.startswith("PID_"):
                return t
        return "?"

    def job_id(self, job: int) -> str:
        for i in range(0, 16, 4):
            t = self.cstr(self.u32(job + i), 24)
            if t.startswith("JID_"):
                return t
        return "?"

    def units(self) -> list[dict]:
        """Every unit of forces 0..2 (player, enemy, other): person, class, level, HP, place (server.board's walk)."""
        out = []
        g = 0x006D7000
        pool = struct.unpack("<II", self.raw(g + 0x2F40, 8))
        for f in range(3):
            u = self.u32(pool[1] + f * 12)
            seen = 0
            while u and LINEAR <= u < LINEAR + (128 << 20) and seen < 200:
                ub = self.raw(u, 0x140)
                out.append({"force": f, "pid": self.person_id(struct.unpack_from("<I", ub, 0x9C)[0]),
                            "jid": self.job_id(struct.unpack_from("<I", ub, 0xA0)[0]), "level": ub[0xF1],
                            "hp": ub[0xF3], "x": ub[0xF4], "y": ub[0xF5]})
                u = struct.unpack_from("<I", ub, 0x14)[0]
                seen += 1
        return out

    def army(self) -> list[dict]:
        """The army as the castle lists it (force 3 in My Castle, force 0 on a map; markers.force_units)."""
        g = 0x006D7000
        pool = struct.unpack("<II", self.raw(g + 0x2F40, 8))
        out = []
        for f in (0, 3):
            u = self.u32(pool[1] + f * 12)
            seen = 0
            while u and LINEAR <= u < LINEAR + (128 << 20) and seen < 200:
                ub = self.raw(u, 0x140)
                out.append({"force": f, "pid": self.person_id(struct.unpack_from("<I", ub, 0x9C)[0]),
                            "jid": self.job_id(struct.unpack_from("<I", ub, 0xA0)[0]), "level": ub[0xF1]})
                u = struct.unpack_from("<I", ub, 0x14)[0]
                seen += 1
        return out


# ------------------------------------------------------------------ the pokes (pure functions, self-tested)
def find_spots(fc: bytes, table: int, count: int) -> dict[int, int]:
    """{chapter index: FCRAM offset} of the world-map spot records: a word-aligned pointer to a Chapter record with
    a state u16 of 0/1/2 after it, and another such pointer 68 bytes before or after (the records sit in a row)."""
    hits = {}
    for k in range(count):
        pat = struct.pack("<I", table + REC * k)
        i = fc.find(pat)
        while i >= 0:
            if i % 4 == 0:
                hits[i] = k
            i = fc.find(pat, i + 1)
    out: dict[int, int] = {}
    for i, k in sorted(hits.items()):
        if i + 6 > len(fc):
            continue
        if (i + SPOT_SIZE in hits or i - SPOT_SIZE in hits) and struct.unpack_from("<H", fc, i + 4)[0] in (0, 1, 2):
            out.setdefault(k, i)
    return out


def patch_fcram(orig: bytes, live_page, writes: list[tuple[int, bytes]]) -> tuple[bytearray, list[dict]]:
    """writes: (guest address in the linear heap, new bytes). Each page is checked equal to live memory first
    (live_page(addr) -> 4 KiB); returns the new FCRAM and the record."""
    fc = bytearray(orig)
    rec = []
    for addr, new in writes:
        off = addr - LINEAR
        if not 0 <= off <= len(orig) - len(new):
            raise Stop(f"0x{addr:08X}: not in the linear heap")
        base = off & ~(PAGE - 1)
        if bytes(orig[base:base + PAGE]) != live_page(LINEAR + base):
            raise Stop(f"0x{addr:08X}: the savestate's page differs from live memory (mapping not as assumed)")
        rec.append({"address": f"0x{addr:08X}", "old": bytes(orig[off:off + len(new)]).hex(), "new": new.hex()})
        fc[off:off + len(new)] = new
    return fc, rec


def select_writes(fc: bytes, t: dict, target: str, route: int | None,
                  borrow: bool = False, lend: str = "locked") -> tuple[list[tuple[int, bytes]], dict]:
    spots = find_spots(fc, t["table"], t["count"])
    if target not in t["ids"]:
        raise Stop(f"CID_{target}: not in this game's chapter table ({t['count']} chapters; spots in this save: "
                   f"{' '.join(t['ids'][i] + '=' + str(struct.unpack_from('<H', fc, o + 4)[0]) for i, o in sorted(spots.items()))})")
    k = t["ids"].index(target)
    borrowed = None
    if k not in spots:
        have = sorted(t["ids"][i] for i in spots)
        want_state = 1 if lend == "open" else 0   # round 59: an OPEN spot can be lent (R011/R012/S007/S009 were
        locked = [(o, i) for i, o in spots.items()  # never decided from a lent locked spot), or a NAMED one
                  if (t["ids"][i] == lend if lend not in ("open", "locked")
                      else struct.unpack_from("<H", fc, o + 4)[0] == want_state)]
        if not borrow or not locked:
            raise Stop(f"CID_{target}: no world-map spot in this save (its path's spots: {' '.join(have)}); "
                       f"use a base save of the chapter's path" + ("" if borrow else " (or --borrow-spot)"))
        # a chapter no spot of this save names (Seal of Flames' own chapters in a Fates save): the last locked
        # spot of the row is lent to it (+0 its Chapter pointer, +4 open)
        off, lent = max(locked)
        borrowed = t["ids"][lent]
    else:
        off = spots[k]
    writes = [(LINEAR + off + 4, struct.pack("<H", 1)),
              (t["gud"] + GUD_CHAPTER, struct.pack("<I", t["table"] + REC * k))]
    if borrowed:
        writes.insert(0, (LINEAR + off, struct.pack("<I", t["table"] + REC * k)))
    if route is not None:
        writes.append((t["gud"] + GUD_ROUTE, bytes([route])))
    info = {"index": k, "spot": f"0x{LINEAR + off:08X}", "borrowed_spot_of": borrowed, "spot_state_before": struct.unpack_from("<H", fc, off + 4)[0],
            "spots_open_before": sorted(t["ids"][i] for i, o in spots.items()
                                        if struct.unpack_from("<H", fc, o + 4)[0] == 1)}
    return writes, info


# ------------------------------------------------------------------ the run
class Run:
    def __init__(self, target: str, base: str, name: str, game: str = "fates", route: int | None = None,
                 steps: str = "all", timeout: float = 900):
        self.target, self.base, self.name, self.game, self.route = target, base, name, game, route
        self.steps, self.timeout = steps, timeout
        self.borrow = game == "seal"
        self.dir = os.path.join(OUT_TOP, name)
        self.res: dict = {"chapter": target, "base": base, "game": game, "cheat": True, "steps": {}, "screens": [],
                          "shots": {}, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.s = None
        self.last = None

    # -- helpers
    def press(self, buttons: str, gap: int = 25, at: int | None = None) -> int:
        f = (self.s.frame if at is None else at) + 4
        spec = ",".join(f"{f + gap * j}:{b}" for j, b in enumerate(buttons.split()))
        self.s.inputs_add(spec)
        return f + gap * len(buttons.split())

    def press_wait(self, buttons: str, gap: int = 25, after: int = 30) -> dict:
        """Presses and waits until the last one is done (a later press must never land before an earlier one)."""
        end = self.press(buttons, gap)
        return self.wait(end - self.s.frame + after)

    def wait(self, frames: int) -> dict:
        stop_check()
        self.s.step_to(self.s.frame + frames)
        return self.screen()

    def screen(self) -> dict:
        m = self.s.markers()
        cur, cls = m.get("current"), m.get("classes", [])
        st = m.get("state") or {}
        self.res["screens"].append([self.s.frame, cur])
        return {"current": cur, "classes": cls, "chapter": st.get("chapter"), "units": st.get("units")}

    def shot(self, label: str) -> str:
        png = os.path.join(self.dir, f"{label}-{self.s.frame}.png")
        self.s.shot(png)
        self.res["shots"][label] = os.path.relpath(png, ROOT)
        return png

    def drive(self, stop: set[str], max_steps: int = 300, seg: int = 60, extra=None) -> dict:
        """robot/auto.py's answers until one of `stop` is the current screen."""
        last = None
        for _ in range(max_steps):
            sc = self.screen()
            cur, cls = sc["current"], sc["classes"]
            if cur in stop:
                return sc
            if extra:
                r = extra(sc)
                if r == "stop":
                    return sc
            btn = ANSWER.get(cur)
            if "TalkKeyWait" in cls:
                cur = "TalkKeyWait"
            if cur in ("TalkKeyWait", "TalkUtil__ProcBind", "event__anonymous_namespace__ProcEvent"):
                btn = "A" if last == ("START", cur) else "START"
            if "BattleSeq" in cls and btn == "START":
                btn = "A"
            if cur == "map__anonymous_namespace__ProcSequence" and "ProcScene" in cls:
                btn = "A"
            if cur and "YesNo" in cur:
                btn = "LEFT A"
            last = (btn, cur)
            if btn:
                self.press(btn)
            self.wait(seg)
        raise Stop(f"no {sorted(stop)} after {max_steps} steps (last screen {self.res['screens'][-1]})")

    def poke(self, writes: list[tuple[int, bytes]], label: str = "poke") -> list[dict]:
        """Changes guest bytes (linear heap addresses) at this frame: the state goes to a file, its FCRAM is changed
        (each page first checked equal to live memory) and loaded back. Returns the record (old/new per write)."""
        import cheats as ch
        s = self.s
        path = os.path.join(s.dir, "tmp", f"{label}-state.bin")
        s.save_file(path)
        with open(path, "rb") as fh:
            data = fh.read()
        head, secs = ch.split_state(data)
        orig = ch.decode_section(secs[1])
        fc, rec = patch_fcram(orig, lambda a: s.peek1(a, PAGE), writes)
        secs[1] = struct.pack("<I", len(fc)) + ch.lz4_literals(bytes(fc))
        with open(path, "wb") as fh:
            fh.write(ch.join_state(head, secs))
        s.load_file(path)
        os.remove(path)
        for addr, new in writes:  # read back: the poke must be in live memory now
            if s.peek1(addr, len(new)) != new:
                raise Stop(f"poke 0x{addr:08X}: not in memory after the load")
        self.res.setdefault("pokes_extra", []).append({"label": label, "frame": s.frame, "writes": rec})
        return rec

    def move_cursor(self, tx: int, ty: int, tries: int = 2) -> list | None:
        """Moves the map cursor to (tx, ty) with the d-pad (one press per tile, read back after); the final cursor."""
        cur = None
        for _ in range(tries):
            cur = self.s.board().get("cursor")
            if not cur:
                return None
            dx, dy = tx - cur[0], ty - cur[1]
            if not dx and not dy:
                return cur
            keys = (["RIGHT"] * dx if dx > 0 else ["LEFT"] * -dx) + (["DOWN"] * dy if dy > 0 else ["UP"] * -dy)
            for key in keys:
                self.press(key, gap=10)
                self.wait(14)
            self.wait(30)
        return self.s.board().get("cursor")

    def empty_tile_menu(self, item_downs: str) -> None:
        """Moves the map cursor onto a tile with no unit (the nearest free tiles in turn, each checked by reading the
        cursor back) and opens the system menu (A), then item presses. Round 59: the old walk moved relative to a
        cursor that had already moved and gave up in a tight group of units (A017, X009, X010, X012, X014)."""
        # round 62 (Seal Y006 all1/all2 in round 61): an A that answered the last turn-start event can land on the
        # map and pick up the unit under the cursor; every 'free' tile then took that unit there and opened its
        # UnitCommand. B twice first drops any picked-up unit (B on the bare map does nothing).
        self.drop_pick()
        b = self.s.board()
        occ = {(u["x"], u["y"]) for u in b["units"]}
        c0 = b["cursor"] or [0, 0]
        cands = sorted(((c0[0] + dx, c0[1] + dy) for dx in range(-6, 7) for dy in range(-6, 7)
                        if c0[0] + dx >= 0 and c0[1] + dy >= 0 and (c0[0] + dx, c0[1] + dy) not in occ),
                       key=lambda t: (abs(t[0] - c0[0]) + abs(t[1] - c0[1]), t[1], t[0]))
        tried, maxx, maxy = [], 99, 99
        for tx, ty in cands:
            if len(tried) >= 8:
                break
            if tx > maxx or ty > maxy:   # beyond the map edge learned from an earlier move that stopped short
                continue
            cur = self.move_cursor(tx, ty)
            if cur and cur[0] < tx:
                maxx = min(maxx, cur[0])
            if cur and cur[1] < ty:
                maxy = min(maxy, cur[1])
            if not cur or tuple(cur) in occ or tuple(cur) != (tx, ty):
                tried.append([tx, ty, cur, "occupied, edge or no cursor"])
                continue
            self.press("A")
            sc = self.wait(50)
            if sc["current"] == SYSMENU:
                self.res.setdefault("sysmenu_tiles", []).append([tx, ty])
                if item_downs:
                    self.press_wait(item_downs, gap=30)
                return
            tried.append([tx, ty, cur, sc["current"]])
            for _ in range(3):  # whatever A opened (a terrain window, a range): back to the map
                if self.screen()["current"] == HUMAN:
                    break
                self.press("B")
                self.wait(40)
            # round 62: back on HUMAN is not enough: B from a UnitCommand returns to the picked-up unit's move
            # range (still HUMAN), and the next A would move that unit. Drop it, and re-read the occupied tiles.
            self.drop_pick()
            occ = {(u["x"], u["y"]) for u in self.s.board()["units"]}
        raise Stop(f"the system menu did not open (tiles tried {tried})")

    def drop_pick(self) -> None:
        """B twice with waits: drops a picked-up unit (B from its move range) and closes a terrain window; on the
        bare map B does nothing. Logged in res["drop_pick"] (the screen after)."""
        for _ in range(2):
            self.press("B")
            self.wait(30)
        self.res.setdefault("drop_pick", []).append([self.s.frame, self.screen()["current"]])

    # -- the steps
    def select(self, s) -> None:
        import cheats as ch
        self.s = s
        live = Live(s)
        s.inputs_set(CASTLE_PRESSES)
        s.step_to(POKE_FRAME)
        sc = self.screen()
        if sc["current"] != PREP:  # a first castle visit talks first: answer it up to the Preparations
            sc = self.drive({PREP, BUTLER}, max_steps=60)
            self.wait(60)
        sc = self.screen()
        if sc["current"] == BUTLER:   # round 59: a first castle visit (A007, A016, ...) stops at the butler's menu
            self.res["butler_start"] = True
        elif sc["current"] != PREP:
            raise Stop(f"the base save did not open the castle's Preparations ({sc['current']})")
        f = s.frame
        self.res["poke_frame"] = f
        t = live.tables()
        self.res["base_chapter"] = t["chapter"]
        self.res["chapter_count"] = t["count"]
        self.res["chapter_ids"] = t["ids"]
        self.res["route_byte_before"] = t["route"]
        if self.target in t["ids"]:  # the target's Chapter record and its neighbours (route_mask +0x14, prep +0x18)
            k = t["ids"].index(self.target)
            self.res["target_records"] = {t["ids"][j]: live.raw(t["table"] + REC * j, REC).hex()
                                          for j in range(max(0, k - 3), min(t["count"], k + 4))}
        self.res["army"] = live.army()
        path = os.path.join(s.dir, "tmp", "chapsel-state.bin")
        s.save_file(path)
        with open(path, "rb") as fh:
            data = fh.read()
        head, secs = ch.split_state(data)
        orig = ch.decode_section(secs[1])
        writes, info = select_writes(orig, t, self.target, self.route, borrow=self.borrow,
                                     lend=getattr(self, "lend", "locked"))
        k = t["ids"].index(self.target)
        mask_at = t["table"] + REC * k + 0x14
        if self.borrow and self.route is not None and live.raw(mask_at, 1)[0] == 0:
            # round 59: a chapter whose route_mask (+0x14) is 0 is never decided from the list (Seal's R011, R012:
            # the game takes R001 instead); the test copy's record gets the route's bit (a cheat poke, recorded)
            writes.append((mask_at, bytes([1 << self.route])))
            info["route_mask_poked"] = f"0 -> {1 << self.route:#x}"
        fc, rec = patch_fcram(orig, lambda a: s.peek1(a, PAGE), writes)
        secs[1] = struct.pack("<I", len(fc)) + ch.lz4_literals(bytes(fc))
        with open(path, "wb") as fh:
            fh.write(ch.join_state(head, secs))
        s.load_file(path)
        os.remove(path)
        t2 = live.tables()
        self.res["pokes"] = rec
        self.res["select"] = {**info, "after": {"chapter": t2["chapter"], "route": t2["route"]}}
        if t2["chapter"] != self.target:
            raise Stop(f"after the poke the current chapter reads {t2['chapter']}")
        # Next Battle: B, START (butler), DOWN x4, A -> the spot list
        if self.res.get("butler_start"):  # already in the butler's menu: Next Battle is the fifth item
            f -= 250
            s.inputs_add(f"{f + 260}:DOWN,{f + 285}:DOWN,{f + 310}:DOWN,{f + 335}:DOWN,{f + 360}:A")
        else:
            s.inputs_add(f"{f + 10}:B,{f + 135}:START,{f + 260}:DOWN,{f + 285}:DOWN,{f + 310}:DOWN,{f + 335}:DOWN,"
                         f"{f + 360}:A")
        s.step_to(f + 500)
        sc = self.drive({SPOTS}, max_steps=40)
        self.shot("spotlist")
        s.save_slot("spots")
        spot_frame = s.frame
        for p in range(0, 14):
            stop_check()
            if p:
                s.load_slot("spots")
                s.inputs_clear()
            keys = " ".join(["DOWN"] * p + ["A"])
            self.press(keys, gap=20)
            ok = False
            for _ in range(8):
                sc = self.wait(40)
                if sc["current"] and "YesNo" in sc["current"]:
                    self.press("LEFT A")
                    self.wait(60)
                    ok = True
                    break
            if ok:
                ch_now = live.tables()["chapter"]
                self.res["select"].setdefault("decided", []).append([p, ch_now])
                if ch_now == self.target:
                    self.res["select"]["list_position"] = p
                    break
        else:
            raise Stop(f"CID_{self.target} was not decided from any list position (slot at {spot_frame})")
        s.drop_slot("spots")
        sc = self.drive({PREP, HUMAN}, max_steps=400)
        self.res["steps"]["start"] = {"frame": s.frame, "screen": sc["current"], "chapter": sc["chapter"]}
        if sc["chapter"] != self.target:
            raise Stop(f"the chapter that started reads {sc['chapter']}, not {self.target}")

    def prep(self) -> None:
        s = self.s
        sc = self.screen()
        if sc["current"] != PREP:
            self.res["steps"]["prep"] = {"skipped": f"no battle preparations in this chapter ({sc['current']})"}
            return
        self.wait(30)
        self.shot("prep")
        st = {"frame": s.frame}
        # Select Units (first item) -> the unit list
        self.press("A")
        sc = self.wait(90)
        st["units_screen"] = sc["current"]
        self.shot("unitlist")
        # a unit's page: R on the selected unit (the status view)
        self.press("R")
        sc = self.wait(90)
        st["unit_page_screen"] = sc["current"]
        self.shot("unitpage")
        self.press("B")
        sc = self.wait(60)
        if sc["current"] != PREP:
            self.press("B")
            sc = self.wait(60)
        if sc["current"] != PREP:
            self.press("B")
            sc = self.wait(60)
        st["back"] = sc["current"]
        # Inventory (DOWN DOWN): the items screen; the armory/shop where the menu offers one
        self.press("DOWN DOWN A")
        sc = self.wait(90)
        st["inventory_screen"] = sc["current"]
        self.shot("inventory")
        # the first unit's item menu (the shop/armory entry is here when the chapter's preparations have one)
        self.press("A")
        sc = self.wait(90)
        st["item_menu_screen"] = sc["current"]
        st["item_menu_classes"] = [c for c in sc["classes"] if "Shop" in c or "Buy" in c or "Item" in c]
        self.shot("itemmenu")
        for _ in range(4):
            if sc["current"] == PREP:
                break
            self.press("B")
            sc = self.wait(60)
        st["back2"] = sc["current"]
        self.res["steps"]["prep"] = st
        if sc["current"] != PREP:
            raise Stop(f"could not return to the preparations ({sc['current']})")
        # Fight!: START, then the map
        self.press("START")
        self.wait(40)
        sc = self.drive({HUMAN}, max_steps=200)

    def map_and_enemy_phase(self) -> None:
        s = self.s
        live = Live(s)
        sc = self.wait(20)
        if sc["current"] != HUMAN:
            sc = self.drive({HUMAN}, max_steps=100)
        self.shot("map")
        us = live.units()
        self.res["steps"]["map"] = {"frame": s.frame, "chapter": sc["chapter"], "counts": sc["units"],
                                    "player": [u for u in us if u["force"] == 0],
                                    "enemy": [u for u in us if u["force"] == 1],
                                    "other": [u for u in us if u["force"] == 2]}
        # the first enemy phase: system menu > End (UP wraps to the last item)
        self.empty_tile_menu("UP")  # End (UP wraps from Units to the last item)
        self.press("A")
        left, moved, frames, stable = None, None, [], 0
        for _ in range(800):
            sc = self.wait(30)
            cur = sc["current"]
            frames.append(cur)
            if cur and "YesNo" in cur:
                self.press("LEFT A")
                continue
            if left is None and cur not in (HUMAN, SYSMENU, None):
                left = s.frame  # the enemy phase began (the menu closed and the player phase left)
                self.shot("enemyphase")
            if moved is None and any(k in c for c in sc["classes"] + [cur or ""]
                                     for k in ("SequenceAI", "ProcMoveRoute", "ProcBattleInfo", "BattleSeq")):
                moved = s.frame
                if s.frame - left > 60:
                    self.shot("enemymove")
            stable = stable + 1 if (cur == HUMAN and left) else 0
            if stable >= 3:  # the next player phase, settled (turn-start events are over)
                break
            if "BattleSeq" in sc["classes"] or cur in ANSWER or "TalkKeyWait" in sc["classes"]:
                self.press(ANSWER.get(cur) or "A")   # round 59: a tutorial window needs START (A002, A005)
        self.res["steps"]["enemy_phase"] = {"enemy_phase_frame": left, "first_enemy_move_frame": moved,
                                            "back_to_player": s.frame,
                                            "screens": sorted({x for x in frames if x}),
                                            "counts_after": sc["units"]}
        if not left or stable < 3:
            raise Stop(f"the enemy phase did not run and return (left {left}, stable {stable})")
        self.shot("turn2")

    def save_and_reload(self, srv_root: str, extra_env: dict, lay_extra) -> None:
        import headless as hl
        import server as sv
        s = self.s
        live = Live(s)
        before = [(u["force"], u["pid"], u["jid"], u["level"], u["hp"], u["x"], u["y"]) for u in live.units()]
        st = {"tries": []}
        # the menu opens on Units (Units, Guide, Options, Save, Auto, End); presses closer than ~40 frames are lost
        for n_try, keys in enumerate(("DOWN DOWN DOWN", "UP UP UP")):
            self.empty_tile_menu("")
            self.press_wait(keys, gap=30)
            self.shot(f"sysmenu{n_try}")
            self.press("A")
            sc = self.wait(90)
            st["tries"].append([keys, sc["current"]])
            if sc["current"] and "File" in sc["current"]:
                break
            for _ in range(4):
                if sc["current"] == HUMAN:
                    break
                self.press("B")
                sc = self.wait(50)
        else:
            raise Stop(f"the Save item was not found in the system menu ({st['tries']})")
        st["menu_screen"] = sc["current"]
        self.shot("savemenu")
        self.press("A")
        for _ in range(10):
            sc = self.wait(40)
            if sc["current"] and "YesNo" in sc["current"]:
                self.press("LEFT A")
                self.wait(120)
                break
        sc = self.drive({HUMAN}, max_steps=40)
        self.shot("saved")
        ext = os.path.join(s.data_dir, "user", "extdata")
        files = []
        for r, _d, fs in os.walk(ext):
            files += [os.path.relpath(os.path.join(r, f), s.data_dir) for f in fs]
        st["extdata_files"] = sorted(files)
        if not any(f.endswith("Map0.bak") for f in files):
            raise Stop("no battle save (Map0.bak) written")
        keep = os.path.join(self.dir, "saved-user")
        if os.path.isdir(keep):
            shutil.rmtree(keep)
        shutil.copytree(os.path.join(s.data_dir, "user"), keep)
        # reload in a fresh server: the same base save laid, then this run's user folder over it
        orig = hl.lay_save

        def lay(zip_path, data_dir):
            names = orig(zip_path, data_dir)
            if not hl.below(os.path.abspath(data_dir), os.path.join(ROOT, "build")):
                raise Stop(f"{data_dir}: not below build/")
            shutil.rmtree(os.path.join(data_dir, "user"))
            shutil.copytree(keep, os.path.join(data_dir, "user"))
            if lay_extra:
                lay_extra(data_dir)
            return names
        stop_check()
        hl.lay_save = lay
        try:
            with sv.Server(f"{self.name}-reload", save=self.base, root=srv_root, timeout=self.timeout, cheat=True,
                           extra_env=extra_env, **SERVER_KW) as s2:
                self.s = s2
                s2.inputs_set(CASTLE_PRESSES)
                s2.step_to(1100)

                def title(sc):  # the title's save-type question (chapter or battle save): the default, A
                    cur = sc["current"] or ""
                    if cur.startswith("title__") or cur in ("MapFileMenu", "ChapterFileMenu"):
                        self.press("A")
                try:
                    sc = self.drive({HUMAN}, max_steps=120, extra=title)
                except Stop:
                    self.shot("reload-stuck")
                    raise
                self.wait(20)
                self.shot("reloaded")
                after = [(u["force"], u["pid"], u["jid"], u["level"], u["hp"], u["x"], u["y"])
                         for u in Live(s2).units()]
                st.update({"reload_frame": s2.frame, "reload_chapter": sc["chapter"],
                           "units_equal": before == after, "units": len(after)})
                self.s = s
        finally:
            hl.lay_save = orig
        self.res["steps"]["save_reload"] = st
        if not st["units_equal"] or st["reload_chapter"] != self.target:
            raise Stop(f"reload differs (chapter {st['reload_chapter']}, units equal {st['units_equal']})")


def run_one(target: str, base: str | None, name: str | None, game: str, route_byte: int | None, steps: str,
            timeout: float, path_route: str | None) -> dict:
    import headless as hl
    import server as sv
    stop_check()
    base = base or pick_base(target, route=path_route)
    name = name or f"{game}-{target}"
    r = Run(target, base, name, game, route_byte, steps, timeout)
    if os.path.isdir(r.dir):
        shutil.rmtree(r.dir)
    os.makedirs(r.dir)
    srv_root = os.path.join(r.dir, "server")
    extra_env, lay_extra = {}, None
    if game == "seal":
        modcopy = os.path.join(OUT_TOP, "_sealmod", TITLE)
        if not os.path.isdir(modcopy):
            if not os.path.isdir(SEAL_MODS):
                raise Stop(f"no Seal of Flames install at {SEAL_MODS}")
            shutil.copytree(SEAL_MODS, modcopy)  # read only on the profile: a copy

        def lay_extra(data_dir):  # noqa: F811
            dst = os.path.join(data_dir, "mods", TITLE)
            if not os.path.isdir(dst):
                shutil.copytree(modcopy, dst)
        # round 83 (F-070): the shared randomizer with the game named, as smoke.py and rcheck.py run Seal (the old
        # tools/sof_rando_off stand-in is retired)
        extra_env = {"FEF_RANDO_TOOL": os.path.join(ROOT, "tools", "randomizer"), "FEF_PYTHON": sys.executable,
                     "FEF_RANDO_GAME": "seal"}
    orig = hl.lay_save

    def lay(zip_path, data_dir):
        names = orig(zip_path, data_dir)
        if lay_extra:
            lay_extra(data_dir)
        return names
    t0 = time.time()
    hl.lay_save = lay
    try:
        with sv.Server(name, save=base, root=srv_root, timeout=timeout, cheat=True, extra_env=extra_env,
                       **SERVER_KW) as s:
            r.res["server_dir"] = os.path.relpath(s.dir, ROOT)
            r.select(s)
            if steps in ("all", "prep"):
                r.prep()
            if steps == "all":
                r.map_and_enemy_phase()
                hl.lay_save = orig
                r.save_and_reload(srv_root, extra_env, lay_extra)
            r.res["ok"] = True
    except Stop as e:
        r.res["ok"] = False
        r.res["error"] = str(e)
    except Exception as e:  # noqa: BLE001
        import traceback
        r.res["ok"] = False
        r.res["error"] = f"{type(e).__name__}: {e}"
        r.res["trace"] = traceback.format_exc()
    finally:
        hl.lay_save = orig
        r.res["seconds"] = round(time.time() - t0, 1)
        r.res["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(r.dir, "result.json"), "w", encoding="utf-8") as fh:
            json.dump(r.res, fh, indent=1)
        log = os.path.join(srv_root, name, "server.log")
        if os.path.isfile(log):
            with open(log, "rb") as fh:
                txt = fh.read().decode("utf-8", "replace").lower()
            r.res["log_faults"] = [w for w in ("panic", "guest fault", "data abort", "prefetch abort",
                                               "undefined instruction") if w in txt]
            with open(os.path.join(r.dir, "result.json"), "w", encoding="utf-8") as fh:
                json.dump(r.res, fh, indent=1)
    return r.res


# ------------------------------------------------------------------ self-test (invented memory, no game)
def selftest() -> tuple[list[str], int]:
    bad, n = [], 0

    def check(c, what):
        nonlocal n
        n += 1
        if not c:
            bad.append(what)
    table = 0x325D9104
    fc = bytearray(0x40000)
    base = 0x20000
    for k in range(10):  # spots for chapters 2..11 in a row, state 2 then 1 then 0
        o = base + SPOT_SIZE * k
        struct.pack_into("<IHH", fc, o, table + REC * (k + 2), 2 if k < 4 else (1 if k == 4 else 0), 0xFFFF)
    struct.pack_into("<I", fc, 0x100, table + REC * 6)    # a lone pointer (not a spot)
    struct.pack_into("<I", fc, 0x302, table + REC * 7)    # unaligned
    sp = find_spots(bytes(fc), table, 20)
    check(sorted(sp) == list(range(2, 12)), "spots: the ten chapters in the row")
    check(sp[6] == base + SPOT_SIZE * 4, "spots: the row's record, not the lone pointer")
    ids = [f"A{i:03d}" for i in range(20)]
    gud_off = 0x1000
    t = {"ids": ids, "table": table, "count": 20, "gud": LINEAR + gud_off}
    w, info = select_writes(bytes(fc), t, "A009", 0)
    check(info["index"] == 9 and info["spot_state_before"] == 0, "select: index and state")
    check(info["spots_open_before"] == ["A006"], "select: the open spot before")
    check((LINEAR + base + SPOT_SIZE * 7 + 4, b"\x01\x00") in w, "select: the spot state write")
    check((LINEAR + gud_off + GUD_CHAPTER, struct.pack("<I", table + REC * 9)) in w, "select: the chapter pointer")
    check((LINEAR + gud_off + GUD_ROUTE, b"\x00") in w, "select: the route byte")
    try:
        select_writes(bytes(fc), t, "A015", 0)
        check(False, "select: a chapter without a spot is refused")
    except Stop:
        check(True, "")
    try:
        select_writes(bytes(fc), t, "Q001", 0)
        check(False, "select: an unknown chapter is refused")
    except Stop:
        check(True, "")
    w2, info2 = select_writes(bytes(fc), t, "A015", 2, borrow=True)
    check(info2["borrowed_spot_of"] == "A011", "borrow: the last locked spot of the row is lent")
    check(w2[0] == (LINEAR + base + SPOT_SIZE * 9, struct.pack("<I", table + REC * 15)), "borrow: its pointer")
    check((LINEAR + base + SPOT_SIZE * 9 + 4, b"\x01\x00") in w2, "borrow: opened")
    w3, info3 = select_writes(bytes(fc), t, "A015", 2, borrow=True, lend="open")
    check(info3["borrowed_spot_of"] == "A006" and w3[0] == (LINEAR + base + SPOT_SIZE * 4, struct.pack("<I", table + REC * 15)),
          "borrow: lend=open lends the open spot")
    w4, info4 = select_writes(bytes(fc), t, "A015", 2, borrow=True, lend="A003")
    check(info4["borrowed_spot_of"] == "A003", "borrow: a named spot is lent")
    live = lambda a: bytes(fc[a - LINEAR:a - LINEAR + PAGE])  # noqa: E731
    new, rec = patch_fcram(bytes(fc), live, w)
    check(struct.unpack_from("<H", new, base + SPOT_SIZE * 7 + 4)[0] == 1, "patch: spot open")
    check(rec[0]["old"] == "0000" and rec[0]["new"] == "0100", "patch: record")
    check(bytes(fc) != bytes(new) and len(new) == len(fc), "patch: same size, changed")
    other = bytearray(fc)
    other[base + 10] ^= 1
    try:
        patch_fcram(bytes(fc), lambda a: bytes(other[a - LINEAR:a - LINEAR + PAGE]), w)
        check(False, "patch: a page that differs from live memory is refused")
    except Stop:
        check(True, "")
    # base pick over an invented saves folder
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        for nm in ("bt-ch6-clear", "bt-ch11-clear", "bt-ch14-clear", "bt-ch26-clear", "cq-ch6-clear",
                   "cq-ch16-clear", "rv-ch12-clear", "cheat-cq-ch20-clear"):
            open(os.path.join(d, nm + ".zip"), "wb").close()
        check(pick_base("A015", d) == "bt-ch14-clear", "base: nearest before")
        check(pick_base("A012", d) == "bt-ch11-clear", "base: the clear save of the chapter before")
        check(pick_base("A003", d) == "bt-ch6-clear", "base: chapters 1-5 from the first castle save")
        check(pick_base("B020", d) == "cq-ch16-clear", "base: never a cheat save")
        check(pick_base("A028", d) == "bt-ch26-clear", "base: the endgame from chapter 26")
        check(pick_base("X007", d) == "bt-ch14-clear", "base: a child paralogue mid-path")
        check(pick_base("X017", d) == "cq-ch16-clear", "base: a Conquest paralogue")
        check(pick_base("X017", d, route="rv") == "rv-ch12-clear", "base: a Revelation paralogue")
        for nm in ("rv-ch15-clear", "rv-ch16-clear"):
            open(os.path.join(d, nm + ".zip"), "wb").close()
        check(pick_base("X015", d, route="rv") == "rv-ch12-clear", "base: never rv-ch15/16 (no castle)")
        open(os.path.join(d, "rv-ch18-clear.zip"), "wb").close()
        open(os.path.join(d, "rv-ch20-clear.zip"), "wb").close()
        check(pick_base("X015", d, route="rv") == "rv-ch18-clear", "base: Revelation children from chapter 18")
        check(pick_base("X003", d, route="rv") == "rv-ch12-clear", "base: Revelation X001-X006 unchanged")
        open(os.path.join(d, "bt-ch16-clear.zip"), "wb").close()
        check(pick_base("A016", d) == "bt-ch16-clear", "base: a first-visit chapter from its own clear save")
        for cid, rt in (("C010", None), ("X009", "cq")):
            try:
                pick_base(cid, d, route=rt)
                check(False, f"base: {cid} without a save is refused")
            except Stop:
                check(True, "")
    return bad, n


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("plan")
    p.add_argument("chapters", nargs="+")
    p.add_argument("--path", choices=("bt", "cq", "rv"))
    r = sub.add_parser("run")
    r.add_argument("chapter")
    r.add_argument("--base")
    r.add_argument("--name")
    r.add_argument("--game", choices=("fates", "seal"), default="fates")
    r.add_argument("--route-byte", type=int)
    r.add_argument("--path", choices=("bt", "cq", "rv"))
    r.add_argument("--steps", choices=("all", "prep", "start"), default="all")
    r.add_argument("--timeout", type=float, default=900)
    a = ap.parse_args(argv)
    if a.selftest:
        bad, n = selftest()
        print(f"chapsel selftest: {n - len(bad)}/{n}")
        for b in bad:
            print("  FAIL", b)
        return 1 if bad else 0
    if a.cmd == "plan":
        for c in a.chapters:
            c = c.replace("CID_", "")
            try:
                print(c, pick_base(c, route=a.path))
            except Stop as e:
                print(c, "-", e)
        return 0
    if a.cmd == "run":
        res = run_one(a.chapter.replace("CID_", ""), a.base, a.name, a.game, a.route_byte, a.steps, a.timeout, a.path)
        print(json.dumps({k: res.get(k) for k in ("chapter", "base", "ok", "error", "seconds", "select", "steps")},
                         indent=1)[:4000])
        return 0 if res.get("ok") else 1
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
