#!/usr/bin/env python3
"""Which route letter is which campaign: the evidence chain, read from the code.

Fates keeps per-route data in folders named A, B and C (GameData/Person/{A,B,C},
GameData/Dispos/{A,B,C}, Scripts/{A,B,C}, m/{A,B,C}). config/game.json says
A = Birthright, B = Conquest, C = Revelation, from file names only (docs/DECISIONS.md
F-009). This tool checks that mapping against the code and prints every step, so anyone
with their own dump can re-run it. The verdict and its confidence are in docs/ROUTES.md.

The steps (all addresses come from config/functions.csv by symbol name):

  1. route byte    the script commands RouteGet / RouteSet read and write one byte of
                   GameUserData (+0x2E); RouteSet refuses values >= 3. This is the
                   game's current Route::Type.
  2. folder        Route::GetDirectoryName(Route::Type) indexes a 3-entry string table:
                   the folder letter of each Route::Type.
  3. users         Person::Load, map::Dispos::Load, event::ScriptLoadRoute,
                   Mess::FileLoadRoute (and their Free/IsExist/Deserialize siblings) all
                   call Route::GetDirectoryName(GameUserData+0x2E) before formatting
                   their path, so the folder letter IS the route byte.
  4. purchase      the "buy another route" menu (link::ec::pcsroute TopMenu) builds three
                   items; each stores its Route::Type at item+0x38 and a message label;
                   MenuItem::BuildAttribute passes item+0x38 to
                   ContentsUtil::IsOnDeviceRoute(Route::Type). The label's English text
                   (read from the owner's m/@E archives) names the campaign.
  5. staff roll    StaffRoll::Create opens the "...C" staff roll file when the route byte
                   is 2 and the "...AB" file otherwise.
  6. epilogue      ProcEpilogue::SettingWord uses a label family with an extra suffix
                   only when the route byte is 2; the castle screen's per-route labels
                   (CastleLowerDrawer::SetupCardInfo) give that suffix's English name.
  7. sides         the castle lottery hides one of its two items on route 0 and the other
                   on route 1 (TopMenu{White,Black}Item::BuildAttribute); TalkConst picks
                   a white / black talk window texture by route; the chapter-6 choice
                   script offers labels _A, _B, _C and RouteBranchDialog shows the third
                   item only if ContentsUtil::IsOwnedRoute(2).
  8. route_mask    Spot::Rebuild / Spot::UpdateSpot keep a chapter when
                   Chapter.route_mask & (1 << route byte): bit n = "on route n".
                   ChapterComplete reads Chapter.next_chapter[route byte]. Data summary.
  9. experience    the Unit::GetExp* functions read GameUserData+0x2D (the byte the
                   DifficultyGet script command returns) to pick the ExpTable row, and
                   never the route byte: experience depends on difficulty, not route.

Usage:
    python tools/fates/routes.py           # print the chain, exit 1 if a step fails
    python tools/fates/routes.py --quiet   # verdict line only
Exit 2 (SKIP) when extracted/code.bin or the RomFS is missing.

Nothing here is copied from community tools; message text is read from the owner's
dump at run time and printed, never stored.
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "assets"))
from gamecfg import GAME  # noqa: E402

CODE = ROOT / "extracted" / "code.bin"
ROMFS = ROOT / "extracted" / "romfs"
FUNCS = ROOT / "config" / "functions.csv"

ROUTE_BYTE = 0x2E          # GameUserData offset of the route byte (checked in step 1)
DIFF_BYTE = 0x2D           # GameUserData offset of the difficulty byte (checked in step 9)
ITEM_ROUTE = 0x38          # pcsroute TopMenu::MenuItem offset of its Route::Type
CH_NEXT, CH_MASK, CH_SIZE = 0x0A, 0x14, 0x1C   # Chapter record (docs/TABLES.md)


# ------------------------------------------------------------------ code access
class Code:
    def __init__(self, path: Path):
        self.b = path.read_bytes()
        self.va = GAME.seg("text").vaddr

    def u32(self, a: int) -> int:
        return struct.unpack_from("<I", self.b, a - self.va)[0]

    def cstr(self, a: int, enc: str = "cp932") -> str:
        o = a - self.va
        e = self.b.find(b"\0", o)
        return self.b[o:e].decode(enc, "replace")

    def raw(self, a: int) -> bytes:
        o = a - self.va
        return self.b[o:self.b.find(b"\0", o)]


class Funcs:
    def __init__(self, path: Path):
        self.rows = list(csv.DictReader(path.open(encoding="utf-8")))
        self.by_name = {}
        for r in self.rows:
            self.by_name.setdefault(r["name"], r)

    def get(self, name: str) -> tuple[int, int]:
        r = self.by_name[name]
        return int(r["addr"], 16), int(r["end"], 16)


def rot_imm(w: int) -> int:
    imm, rot = w & 0xFF, ((w >> 8) & 0xF) * 2
    return ((imm >> rot) | (imm << (32 - rot))) & 0xFFFFFFFF if rot else imm


def decode(w: int, pc: int) -> tuple:
    """A small ARM decoder for the shapes this tool needs (all others -> ('?',))."""
    cond = w >> 28
    if (w & 0x0F000000) == 0x0B000000 and cond != 0xF:
        off = (w & 0xFFFFFF) - ((w & 0x800000) << 1)
        return ("bl", pc + 8 + off * 4, cond)
    if (w & 0x0F000000) == 0x0A000000 and cond != 0xF:
        off = (w & 0xFFFFFF) - ((w & 0x800000) << 1)
        return ("b", pc + 8 + off * 4, cond)
    if (w & 0x0E500000) == 0x04500000:                         # ldrb rd,[rn,#imm]
        imm = w & 0xFFF if (w >> 23) & 1 else -(w & 0xFFF)
        return ("ldrb", (w >> 12) & 15, (w >> 16) & 15, imm, cond)
    if (w & 0x0E500000) == 0x04400000:                         # strb rd,[rn,#imm]
        imm = w & 0xFFF if (w >> 23) & 1 else -(w & 0xFFF)
        return ("strb", (w >> 12) & 15, (w >> 16) & 15, imm, cond)
    if (w & 0x0F7F0000) == 0x051F0000:                         # ldr rd,[pc,#imm]
        imm = w & 0xFFF if (w >> 23) & 1 else -(w & 0xFFF)
        return ("ldrlit", (w >> 12) & 15, pc + 8 + imm, cond)
    if (w & 0x0FFF0000) == 0x028F0000:                         # add rd,pc,#imm (adr)
        return ("adr", (w >> 12) & 15, pc + 8 + rot_imm(w), cond)
    if (w & 0x0FF0F000) == 0x03500000:                         # cmp rn,#imm
        return ("cmp", (w >> 16) & 15, rot_imm(w), cond)
    if (w & 0x0FEF0000) == 0x03A00000:                         # mov rd,#imm
        return ("mov", (w >> 12) & 15, rot_imm(w), cond)
    if (w & 0x0FE00010) == 0x01A00010 and ((w >> 5) & 3) == 0:  # lsl rd, rm, rs
        return ("lslr", (w >> 12) & 15, w & 15, (w >> 8) & 15, cond)
    if (w & 0x0FF0F000) == 0x01100000 and (w & 0x90) != 0x90:  # tst rn, rm
        return ("tst", (w >> 16) & 15, w & 15, cond)
    if (w & 0x0FE00FF0) == 0x00800000:                         # add rd, rn, rm
        return ("addr", (w >> 12) & 15, (w >> 16) & 15, w & 15, cond)
    return ("?",)


def insns(code: Code, a: int, e: int):
    for pc in range(a, e, 4):
        yield pc, decode(code.u32(pc), pc)


def route_byte_loads(code: Code, F: Funcs, a: int, e: int, off: int = ROUTE_BYTE) -> list[int]:
    """Addresses of `bl GameUserData::Get` followed (within 5 insns) by ldrb rX,[r0,#off]."""
    get = F.get("GameUserData__Get")[0]
    out = []
    seq = list(insns(code, a, e))
    for i, (pc, d) in enumerate(seq):
        if d[0] == "bl" and d[1] == get:
            for pc2, d2 in seq[i + 1:i + 6]:
                if d2[0] == "ldrb" and d2[2] == 0 and d2[3] == off:
                    out.append(pc2)
                    break
    return out


# ------------------------------------------------------------------ messages
_MSG: dict[bytes, str] | None = None


def messages() -> dict[bytes, str]:
    """label -> English text over m/@E (the owner's dump; never stored)."""
    global _MSG
    if _MSG is None:
        import msg as M
        _MSG = {}
        for p in sorted(glob.glob(str(ROMFS / "m" / "@E" / "*.bin.lz"))):
            try:
                _name, ents, _b = M.parse(M.load(p))
            except Exception:
                continue
            for lab, text, alias in ents:
                if not alias:
                    _MSG.setdefault(lab, text)
    return _MSG


def en(label: bytes) -> str:
    t = messages().get(label)
    return "(no English text)" if t is None else t.replace("\n", " / ")


# ------------------------------------------------------------------ report
class Report:
    def __init__(self, quiet: bool):
        self.quiet, self.fails = quiet, []

    def say(self, s: str = "") -> None:
        if not self.quiet:
            print(s)

    def check(self, ok: bool, what: str) -> bool:
        self.say(f"  [{'ok' if ok else 'FAIL'}] {what}")
        if not ok:
            self.fails.append(what)
        return ok


def step1(code, F, R) -> None:
    R.say("1. route byte (script commands RouteGet / RouteSet)")
    a, e = F.get("anonymous_namespace__RouteGet")
    R.check(bool(route_byte_loads(code, F, a, e)), f"RouteGet {a:#x}: GameUserData::Get, ldrb r0,[r0,#{ROUTE_BYTE:#x}]")
    a, e = F.get("anonymous_namespace__RouteSet")
    ds = [d for _, d in insns(code, a, e)]
    bound = any(d[0] == "cmp" and d[1] == 1 and d[2] == 3 for d in ds)
    store = any(d[0] == "strb" and d[2] == 0 and d[3] == ROUTE_BYTE for d in ds)
    R.check(bound and store, f"RouteSet {a:#x}: refuses r1 >= 3, strb r1 -> [GameUserData,#{ROUTE_BYTE:#x}]")


def step2(code, F, R) -> dict[int, str]:
    R.say("2. Route::GetDirectoryName(Route::Type)")
    a, e = F.get("Route__GetDirectoryName")
    lit = [d for _, d in insns(code, a, e) if d[0] == "ldrlit"]
    folders = {}
    if R.check(len(lit) == 1, f"{a:#x}: one literal = address of a 3-entry string table"):
        tab = code.u32(lit[0][2])
        for t in range(3):
            folders[t] = code.cstr(code.u32(tab + 4 * t))
        R.say(f"     table {tab:#x}: " + ", ".join(f"Route::Type {t} -> \"{s}\"" for t, s in folders.items()))
    R.check(sorted(folders.values()) == ["A", "B", "C"], "the three entries are the folder letters A, B, C")
    return folders


def step3(code, F, R) -> None:
    R.say("3. path builders call Route::GetDirectoryName(GameUserData+0x2E)")
    gdn = F.get("Route__GetDirectoryName")[0]
    for name in ("Person__Load", "map__Dispos__Load", "event__ScriptLoadRoute", "Mess__FileLoadRoute",
                 "Mess__FileFreeRoute", "Mess__IsFileExistRoute", "event__ScriptFreeRoute", "Person__Deserialize"):
        a, e = F.get(name)
        loads = route_byte_loads(code, F, a, e)
        call = None
        for pc in loads:
            for pc2, d in insns(code, pc + 4, min(pc + 24, e)):
                if d[0] == "bl":
                    call = d[1]
                    break
        fmts = [code.cstr(code.u32(d[2])) for _, d in insns(code, a, e)
                if d[0] == "ldrlit" and GAME.seg("rodata").vaddr <= code.u32(d[2]) < GAME.seg("rodata").end
                and "%s" in code.cstr(code.u32(d[2]))]
        R.check(bool(loads) and call == gdn,
                f"{name.replace('__', '::')} {a:#x}: route byte -> GetDirectoryName" +
                (f"; formats {', '.join(fmts)}" if fmts else ""))


def step4(code, F, R, folders: dict[int, str]) -> dict[int, str]:
    R.say("4. the route purchase menu: Route::Type of each item and its label's English text")
    a, e = F.get("link__ec__pcsroute__anonymous_namespace__ProcFromMainMenuSequence__TopMenu")
    # one item per `operator new` block: the byte stored at item+0x38 and the MID_ label
    news = {int(r["addr"], 16) for r in F.rows if r["name"].startswith("operator_new")}
    regs: dict[int, int] = {}
    blocks: list[dict] = []
    for pc, d in insns(code, a, e):
        if d[0] == "bl" and d[1] in news:
            blocks.append({})
        elif d[0] == "mov" and d[3] == 0xE:
            regs[d[1]] = d[2]
        elif blocks and d[0] == "strb" and d[3] == ITEM_ROUTE and d[1] in regs:
            blocks[-1]["route"] = regs[d[1]]
        elif blocks and d[0] == "adr":
            lab = code.raw(d[2])
            if lab.startswith(b"MID_") and not lab.startswith(b"MID_H_"):
                blocks[-1].setdefault("label", lab)
    items = [(b["route"], b["label"]) for b in blocks if "route" in b and "label" in b]
    names = {}
    R.check(sorted(t for t, _ in items) == [0, 1, 2], f"TopMenu {a:#x}: three items, Route::Type 0, 1, 2 at item+{ITEM_ROUTE:#x}")
    for t, lab in sorted(items):
        names[t] = en(lab)
        R.say(f"     Route::Type {t} (folder {folders.get(t, '?')}): label {lab.decode('cp932', 'replace')}"
              f" -> \"{names[t]}\"")
    b, be = F.get("link__ec__pcsroute__anonymous_namespace__ProcFromMainMenuSequence__TopMenu__MenuItem__BuildAttribute")
    on_dev = F.get("ContentsUtil__IsOnDeviceRoute")[0]
    ds = [d for _, d in insns(code, b, be)]
    R.check(any(d[0] == "ldrb" and d[3] == ITEM_ROUTE for d in ds) and any(d[0] == "bl" and d[1] == on_dev for d in ds),
            f"MenuItem::BuildAttribute {b:#x}: ContentsUtil::IsOnDeviceRoute(Route::Type = item+{ITEM_ROUTE:#x})")
    for t, letter in folders.items():
        want = GAME.raw["romfs"]["route_folders"].get(letter, "?")
        R.check(want.lower() in names.get(t, "").lower(),
                f"config/game.json route_folders[{letter}] = {want} is named by the item of Route::Type {t}")
    return names


def branch_strings(code, a: int, e: int, pc0: int, value: int) -> tuple[list[str], list[str]]:
    """After the route-byte load at pc0: strings ADR'd on the path where route == value
    (taken branch of `cmp r,#value ; beq/bne`) and on the other path (first 2 each)."""
    seq = list(insns(code, pc0, e))
    for i, (pc, d) in enumerate(seq[:12]):
        if d[0] == "cmp" and d[2] == value:
            for pc2, d2 in seq[i + 1:i + 4]:
                if d2[0] == "b" and d2[2] in (0x0, 0x1):        # beq / bne
                    tgt, eq = d2[1], d2[2] == 0x0
                    def adrs(start: int) -> list[str]:
                        out = []
                        for _, d3 in insns(code, start, min(start + 0x60, e)):
                            if d3[0] == "adr":
                                out.append(code.cstr(d3[2]))
                            if len(out) == 2:
                                break
                        return out
                    taken, fall = adrs(tgt), adrs(pc2 + 4)
                    return (taken, fall) if eq else (fall, taken)
    return [], []


def step5(code, F, R) -> None:
    R.say("5. staff roll: which file for which route byte")
    a, e = F.get("StaffRoll__Create")
    loads = route_byte_loads(code, F, a, e)
    if R.check(bool(loads), f"StaffRoll::Create {a:#x} reads the route byte"):
        is2, other = branch_strings(code, a, e, loads[0], 2)
        R.say(f"     route byte == 2: {is2[:1]}; otherwise: {other[:1]}")
        R.check(bool(is2) and is2[0].endswith("C.bin") and bool(other) and other[0].endswith("AB.bin"),
                "route 2 -> the C staff roll, routes 0 and 1 -> the AB staff roll")


def step6(code, F, R) -> str:
    R.say("6. epilogue: the label family used only on route byte 2, and what the game calls it")
    a, e = F.get("anonymous_namespace__ProcEpilogue__SettingWord")
    loads = route_byte_loads(code, F, a, e)
    suffix = ""
    if R.check(bool(loads), f"ProcEpilogue::SettingWord {a:#x} reads the route byte ({len(loads)}x)"):
        is2, _ = branch_strings(code, a, e, loads[0], 2)
        if is2:
            suffix = is2[-1].rsplit("_", 1)[-1]
            R.say(f"     route byte == 2: {', '.join(is2)}  (suffix {suffix})")
    c, ce = F.get("CastleLowerDrawer__SetupCardInfo")
    found = []
    for pc, d in insns(code, c, ce):
        if d[0] == "adr":
            lab = code.raw(d[2])
            if suffix and suffix.encode("cp932") in lab and lab.startswith(b"MKID_H_"):
                found.append((lab, en(lab)))
    for lab, t in found[:5]:
        R.say(f"     castle label {lab.decode('cp932', 'replace')} -> \"{t}\"")
    third = GAME.raw["romfs"]["route_folders"].get("C", "?")
    R.check(any(third.lower() in t.lower() for _, t in found),
            f"the game's English text for that suffix names {third} (route_folders[C])")
    return suffix


def step7(code, F, R) -> None:
    R.say("7. the two sides: lottery items, talk window, chapter-6 choice")
    for cls in ("TopMenuWhiteItem", "TopMenuBlackItem"):
        a, e = F.get(f"anonymous_namespace__{cls}__BuildAttribute")
        g, ge = F.get(f"anonymous_namespace__{cls}__GetName")
        loads = route_byte_loads(code, F, a, e)
        hidden = None
        if loads:
            seq = list(insns(code, loads[0], e))
            for i, (pc, d) in enumerate(seq[:4]):
                if d[0] == "cmp" and seq[i + 1][1][0] == "mov" and seq[i + 1][1][2] == 4 and seq[i + 1][1][3] == 0x0:
                    hidden = d[2]
        lab = next((code.raw(d[2]) for _, d in insns(code, g, ge) if d[0] == "adr"), b"")
        R.check(hidden is not None, f"{cls}: attribute 4 (unavailable) when route byte == {hidden};"
                                    f" name {lab.decode('cp932', 'replace')} -> \"{en(lab)}\"")
    a, e = F.get("TalkConst__GetWindowTextureRoutePath")
    lit = [d for _, d in insns(code, a, e) if d[0] == "ldrlit"]
    if R.check(len(lit) == 1, f"TalkConst::GetWindowTextureRoutePath {a:#x}: 3-entry table by Route::Type"):
        tab = code.u32(lit[0][2])
        R.say("     " + ", ".join(f"{t} -> {code.cstr(code.u32(tab + 4 * t))}" for t in range(3)))
    a, e = F.get("anonymous_namespace__RouteBranchDialog")
    owned = F.get("ContentsUtil__IsOwnedRoute")[0]
    seq = list(insns(code, a, e))
    gate = any(d[0] == "mov" and d[1] == 0 and d[2] == 2 and seq[i + 1][1][:2] == ("bl", owned)
               for i, (_, d) in enumerate(seq[:-1]))
    R.check(gate, f"RouteBranchDialog {a:#x}: the third item is added only if ContentsUtil::IsOwnedRoute(2)")
    for p in sorted(glob.glob(str(ROMFS / "Scripts" / "*.cmb"))):
        d = Path(p).read_bytes()
        if b"RouteBranchDialog" in d and b"RouteSet" in d:
            labs = re.findall(rb"(MID_\w+_SELECT_[A-C])\x00", d)
            R.say(f"     {os.path.basename(p)}: RouteBranchDialog labels in order:")
            for lab in labs:
                R.say(f"       {lab.decode()} -> \"{en(lab)}\"")


def chapters():
    import tablelib as T
    t = T.registry()["Chapter"]
    c = T.container(t.file)
    s, n = T.locate(t, c)
    out = []
    for i in range(n):
        o = s + i * CH_SIZE
        d = c.data[o:o + CH_SIZE]
        out.append((c.string_at(c.u32(o)).decode(errors="replace"), list(d[CH_NEXT:CH_NEXT + 3]), d[CH_MASK]))
    return out


def step8(code, F, R) -> None:
    R.say("8. Chapter.route_mask and Chapter.next_chapter")
    a, e = F.get("Spot__Rebuild")
    seq = list(insns(code, a, e))
    ok = False
    loads = route_byte_loads(code, F, a, e)
    if loads:
        rreg = code.u32(loads[0]) >> 12 & 15
        shifted = {d[1] for _, d in seq if d[0] == "lslr" and d[3] == rreg}
        mask_regs = {d[1] for _, d in seq if d[0] == "ldrb" and d[3] == CH_MASK}
        ok = any(d[0] == "tst" and {d[1], d[2]} & shifted and {d[1], d[2]} & mask_regs for _, d in seq)
    R.check(ok, f"Spot::Rebuild {a:#x}: keeps a chapter when (Chapter+{CH_MASK:#x}) & (1 << route byte)")
    a, e = F.get("MainSequence__anonymous_namespace__ProcSequence__ChapterComplete")
    seq = list(insns(code, a, e))
    nxt = any(d[0] == "addr" for _, d in seq) and any(d[0] == "ldrb" and d[3] == CH_NEXT for _, d in seq)
    R.check(bool(route_byte_loads(code, F, a, e)) and nxt,
            f"ChapterComplete {a:#x}: next chapter = Chapter[current + route byte + {CH_NEXT:#x}]")
    try:
        recs = chapters()
    except Exception as ex:                                    # tables tool missing or changed
        R.check(False, f"Chapter table not readable: {ex}")
        return
    by = {r[0]: (i, r) for i, r in enumerate(recs)}
    from collections import Counter
    R.say(f"     route_mask values over {len(recs)} chapters: "
          + ", ".join(f"{k}: {v}" for k, v in sorted(Counter(r[2] for r in recs).items())))
    for bit, letter in enumerate("ABC"):
        own = Counter(r[0][4:5] for r in recs if r[2] == 1 << bit)
        R.check(set(own) == {letter}, f"route_mask == {1 << bit} only on CID_{letter}nnn chapters ({sum(own.values())})")
    for t, letter in enumerate("ABC"):
        six = by.get(f"CID_{letter}006")
        if six:
            R.check(six[1][2] == 1 << t, f"CID_{letter}006 route_mask = {six[1][2]} (only route {t})")
        cur = by.get(f"CID_{letter}007")
        chain = []
        while cur and cur[1][0] not in chain:
            chain.append(cur[1][0])
            n = cur[1][1][t]
            cur = (n, recs[n]) if n else None
        R.check(bool(chain) and all(c[4:5] == letter for c in chain[:-1]),
                f"next_chapter[{t}] from CID_{letter}007: {len(chain)} steps, all CID_{letter}nnn, ends {chain[-1] if chain else '-'}")


def step9(code, F, R) -> None:
    R.say("9. experience: which GameUserData bytes the Unit::GetExp* functions read")
    a, e = F.get("anonymous_namespace__DifficultyGet")
    R.check(bool(route_byte_loads(code, F, a, e, DIFF_BYTE)), f"DifficultyGet {a:#x}: returns GameUserData+{DIFF_BYTE:#x}")
    get = F.get("GameUserData__Get")[0]
    for name in ("Unit__GetExpDamage", "Unit__GetExpDestroy", "Unit__GetExpDance", "Unit__GetExpRod"):
        if name not in F.by_name:
            continue
        a, e = F.get(name)
        seq = list(insns(code, a, e))
        offs = set()
        for i, (pc, d) in enumerate(seq):
            if d[0] == "bl" and d[1] == get:
                for _, d2 in seq[i + 1:i + 4]:
                    if d2[0] == "ldrb" and d2[2] == 0:
                        offs.add(d2[3])
                        break
        R.check(ROUTE_BYTE not in offs, f"{name.replace('__', '::')}: GameUserData bytes read {sorted(hex(o) for o in offs) or '-'}"
                                        f" (route byte {ROUTE_BYTE:#x} not among them)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quiet", action="store_true", help="print the verdict line only")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not CODE.exists() or not (ROMFS / "m" / "@E").is_dir():
        print("SKIP: needs extracted/code.bin and extracted/romfs (python tools/extract_rom.py; tools/assets/romfs.py)")
        return 2
    sys.path.insert(0, str(ROOT / "tools" / "tables"))
    code, F, R = Code(CODE), Funcs(FUNCS), Report(args.quiet)
    step1(code, F, R)
    folders = step2(code, F, R)
    step3(code, F, R)
    names = step4(code, F, R, folders)
    step5(code, F, R)
    step6(code, F, R)
    step7(code, F, R)
    step8(code, F, R)
    step9(code, F, R)
    R.say()
    rf = GAME.raw["romfs"]["route_folders"]
    verdict = ", ".join(f"{folders.get(t, '?')} = Route::Type {t} = {rf.get(folders.get(t, ''), '?')}" for t in range(3))
    if R.fails:
        print(f"routes: {len(R.fails)} step(s) FAILED; config/game.json mapping NOT confirmed ({verdict})")
        return 1
    print(f"routes: confirmed from code: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
