#!/usr/bin/env python3
"""Code evidence for table layouts: which offsets each named function loads from its
arguments.

Standard library only. Reads the user's own extracted/text.bin and the symbol map the
game ships in its RomFS (debug/name.StackTrace + debug/addr.StackTrace: NUL-separated
demangled C++ names, and (u32 address, u32 name offset) pairs). Nothing is written to
tracked files.

For every function whose name matches the given regular expression, a tiny ARM decoder
walks the instructions in address order and tracks where each register's value came
from, starting with r0..r3 = arg0..arg3 ("this" is arg0 for methods). Every immediate
load or store through a tracked register is reported as a path, e.g.

    0053E198 Person::GetLowJobIndex(void) const      arg0+0x2C:u16  arg0+0x2E:u16

and a 32-bit load extends the path (arg0+0x0C->+0x04:u8 = a byte inside the object a
pointer field points to). A register-offset load is shown as an array access
(arg0+0x9C->+0x40[i]:s8), and so is an immediate load through a register that had an
untracked register added to it (add r0, r0, r1; ldrsb r0, [r0, #0x24] -> +0x24[i]).
After a call to a static lookup that returns a record (Item::Get(unsigned short),
Job::TryGet(const char*), or a getter in TABLE_GETTERS such as ExpTable::GetBattle(int))
r0 is tracked as that class / table (Item+0x1F:u8, ExpBattle+0x24[i]:s8). The walk is linear (no branch analysis) and only understands
ldr/str/ldrb/ldrh/ldrsb/ldrsh/ldrd (immediate and register offset), mov, add/sub with an
immediate, add of two registers, and bl; every other instruction that writes a register
forgets what that register held. Two conditional shapes are followed: a conditional word
load into a register that held nothing tracked (ldreq r0, [r6, #0x9C] -> r0 is the Person
record on that branch), and an addeq/addne pair on one register (Unit::GetGrow picks
Job+0x24 or Job+0x2C this way), whose next access is reported at both offsets. That is precise for the small accessors the layouts cite and noisy for
big functions, so read the disassembly before citing anything from a long function.

--fields TABLE scans every named function (up to 0x4000 bytes) and lists each offset of
TABLE that is loaded, with the functions that load it. Records are recognised through the
lookup functions above and through config/tables/slots.csv (function regex, path prefix,
table): e.g. inside Unit:: methods arg0+0x9C-> is the unit's Person record.

Usage:
    python tools/tables/evidence.py REGEX [--max-size N] [--writes]
        REGEX       matched against the demangled name (re.search)
        --max-size  skip functions longer than N bytes (default 0x400)
        --writes    also list stores
    python tools/tables/evidence.py --fields TABLE [--show N]
    python tools/tables/evidence.py --bitsets [LO:HI]
        fixed-size bit sets indexed by a bounded number (cmp Rn,#N then ldrb/strb
        [base, Rn, asr #3]); the scan behind config/tables/appends.csv
    python tools/tables/evidence.py --selftest
"""
from __future__ import annotations

import argparse
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from gamecfg import GAME  # noqa: E402

TEXT = os.path.join(ROOT, "extracted", "text.bin")
ROMFS = os.path.join(ROOT, "extracted", "romfs")
TEXT_VA = GAME.seg("text").vaddr


def symbols() -> list[tuple[int, str]]:
    sm = GAME.raw["romfs"]["symbol_map"]
    with open(os.path.join(ROMFS, sm["names"]), "rb") as fh:
        names = fh.read()
    with open(os.path.join(ROMFS, sm["addrs"]), "rb") as fh:
        addrs = fh.read()
    out = []
    for i in range(len(addrs) // 8):
        a, no = struct.unpack_from("<2I", addrs, 8 * i)
        e = names.find(b"\0", no)
        if e < 0:
            continue
        out.append((a, names[no:e].decode("utf-8", "replace")))
    out.sort()
    return out


WIDTH = {("w", False): "u32", ("b", False): "u8", ("h", False): "u16", ("sb", True): "s8",
         ("sh", True): "s16", ("d", False): "u64"}


def decode(ins: int):
    """('mem', L, kind, signed, rn, rd, off) | ('mov', rd, rm) | ('addi', rd, rn, imm) |
    ('addr', rd, rn, rm) | ('bl',) | ('wr', [regs]) | ('other',)"""
    cond = ins >> 28
    if cond == 0xF:
        return ("other",)
    if (ins >> 25) & 7 == 0b010:  # LDR/STR immediate
        p, u, b, w, l = (ins >> 24) & 1, (ins >> 23) & 1, (ins >> 22) & 1, (ins >> 21) & 1, (ins >> 20) & 1
        rn, rd, imm = (ins >> 16) & 15, (ins >> 12) & 15, ins & 0xFFF
        if p and not w:
            return ("mem", l, "b" if b else "w", False, rn, rd, imm if u else -imm, cond)
        return ("wr", [rd, rn] if l else [rn])
    if (ins >> 25) & 7 == 0b011 and not (ins >> 4) & 1:  # LDR/STR register offset
        p, b, w, l = (ins >> 24) & 1, (ins >> 22) & 1, (ins >> 21) & 1, (ins >> 20) & 1
        rn, rd = (ins >> 16) & 15, (ins >> 12) & 15
        if p and not w:
            return ("memr", l, "b" if b else "w", False, rn, rd)
        return ("wr", [rd, rn] if l else [rn])
    if (ins >> 25) & 7 == 0 and not (ins >> 22) & 1 and (ins >> 7) & 1 and (ins >> 4) & 1             and (ins >> 5) & 3 and not (ins >> 8) & 15:  # LDRH/LDRSB/LDRSH register offset
        sh, p, w, l = (ins >> 5) & 3, (ins >> 24) & 1, (ins >> 21) & 1, (ins >> 20) & 1
        rn, rd = (ins >> 16) & 15, (ins >> 12) & 15
        if l and p and not w:
            kind, signed = {1: ("h", False), 2: ("sb", True), 3: ("sh", True)}[sh]
            return ("memr", 1, kind, signed, rn, rd)
        return ("wr", [rd, rn] if l else [rn])
    if (ins >> 25) & 7 == 0 and (ins >> 22) & 1 and (ins >> 7) & 1 and (ins >> 4) & 1:
        sh = (ins >> 5) & 3
        if sh:
            p, u, w, l = (ins >> 24) & 1, (ins >> 23) & 1, (ins >> 21) & 1, (ins >> 20) & 1
            rn, rd = (ins >> 16) & 15, (ins >> 12) & 15
            imm = ((ins >> 4) & 0xF0) | (ins & 0xF)
            kind, signed = {(1, 1): ("h", False), (2, 1): ("sb", True), (3, 1): ("sh", True),
                            (1, 0): ("h", False), (2, 0): ("d", False), (3, 0): ("d", False)}[(sh, l)]
            load = l or sh == 2  # LDRD has L=0, SH=10
            if p and not w:
                return ("mem", 1 if load else 0, kind, signed, rn, rd, imm if u else -imm, cond)
            return ("wr", [rd, rn])
    if (ins & 0x0FEF0FF0) == 0x01A00000:
        return ("mov", (ins >> 12) & 15, ins & 15, cond)
    if (ins & 0x0F000000) == 0x0B000000:
        off = ins & 0xFFFFFF
        off = (off - (1 << 24) if off >> 23 else off) << 2
        return ("bl", off + 8)
    if (ins >> 26) & 3 == 0 and (ins >> 25) & 1:  # data processing, immediate operand
        op = (ins >> 21) & 15
        rd, rn = (ins >> 12) & 15, (ins >> 16) & 15
        rot = ((ins >> 8) & 15) * 2
        imm = ((ins & 0xFF) >> rot | (ins & 0xFF) << (32 - rot)) & 0xFFFFFFFF if rot else ins & 0xFF
        if op in (8, 9, 10, 11):
            return ("other",)
        if op == 4:
            return ("addi", rd, rn, imm, cond)
        if op == 2:
            return ("addi", rd, rn, -imm, cond)
        return ("wr", [rd])
    if (ins >> 26) & 3 == 0:
        op = (ins >> 21) & 15
        if op == 4 and not (ins >> 25) & 1 and not (ins >> 4) & 0xFF and cond == 0xE:  # add rd, rn, rm
            return ("addr", (ins >> 12) & 15, (ins >> 16) & 15, ins & 15)
        if (ins >> 4) & 0x9 == 0x9 and (ins >> 25) & 1 == 0:
            if (ins >> 22) & 0x3F == 0:  # MUL/MLA: only Rd (bits 16-19) is written
                return ("wr", [(ins >> 16) & 15])
            if (ins >> 23) & 0x1F == 1:  # UMULL/SMULL/..: RdHi and RdLo
                return ("wr", [(ins >> 16) & 15, (ins >> 12) & 15])
            return ("wr", [(ins >> 12) & 15])
        if op in (8, 9, 10, 11) and (ins >> 20) & 1:
            return ("other",)
        return ("wr", [(ins >> 12) & 15])
    if (ins >> 25) & 7 == 0b100:  # LDM/STM
        if (ins >> 20) & 1:
            return ("wr", [r for r in range(16) if ins >> r & 1] + [(ins >> 16) & 15])
        return ("wr", [(ins >> 16) & 15] if (ins >> 21) & 1 else [])
    if (ins >> 25) & 7 == 0b011:
        return ("wr", [(ins >> 12) & 15])
    return ("other",)


def fmt_path(path: tuple) -> str:
    s = path[0]
    for k in path[1:]:
        s += f"+0x{k:X}->"
    return s


GETTER = re.compile(r"^(\w+)::(?:Get|TryGet|GetFromNoPrefix)\((?:const char\*|unsigned short|unsigned char|short|int)\)$")


# Getters whose name does not follow GETTER, or that return a row of a sub-table: exact
# demangled name -> table name in config/tables/tables.csv.
TABLE_GETTERS = {
    "ItemRefine::Get(int,int)": "ItemRefine",
    "WeaponBonus::Get(ItemKind::Type)": "WeaponBonus",
    "WeaponLevel::Get(void)": "WeaponLevel",
    "WeaponInteract::Get(void)": "WeaponInteract",
    "ExpTable::GetBattle(int)": "ExpBattle",
    "ExpTable::GetBattleThreshold(int)": "ExpBattleFloor",
    "ExpTable::GetRodDecline(int)": "ExpRod",
    "ExpTable::GetRodHighDecline(int)": "ExpRodHigh",
    "ExpTable::GetDance(int)": "ExpDance",
    "ExpTable::GetSupportDecline(int)": "ExpSupport",
    # a unit's carried item (unit::Item, 4 bytes: item number, uses, forge bits) -> its Item
    # record; the stat getters reach Item.stat_bonus and Item.held_bonus this way
    "unit::Item::ToData(void) const": "Item",
}


def getters(syms: list[tuple[int, str]]) -> dict[int, str]:
    """address -> table class for the static lookup functions that return a record
    (Item::Get(unsigned short), Job::TryGet(const char*), ExpTable::GetBattle(int) ...):
    after a call to one, r0 is tracked as a record of that class."""
    out = {}
    for a, n in syms:
        m = GETTER.match(n)
        if m:
            out[a] = m.group(1)
        elif n in TABLE_GETTERS:
            out[a] = TABLE_GETTERS[n]
    return out


def analyse(code: bytes, va: int, writes: bool = False, rets: dict[int, str] | None = None) -> list[str]:
    regs: dict[int, tuple] = {0: ("arg0",), 1: ("arg1",), 2: ("arg2",), 3: ("arg3",)}
    adds: dict[int, int] = {}  # reg -> constant added to its tracked path base
    idx: set[int] = set()  # regs that also hold a register index (add rd, rn, rm)
    alts: dict[int, list[int]] = {}  # reg -> the other constants it may hold (addeq/addne pair)
    out: list[str] = []
    skip = False
    for i in range(0, len(code) - 3, 4):
        if skip:
            skip = False
            continue
        ins = struct.unpack_from("<I", code, i)[0]
        d = decode(ins)
        for r in [r for r in alts if d[0] not in ("mem", "memr")]:
            # an addeq/addne pair only feeds the accesses right after it; then forget the
            # register, whose offset depends on the branch taken
            alts.pop(r, None)
            regs.pop(r, None)
            adds.pop(r, None)
            idx.discard(r)
        if d[0] == "mem":
            _, load, kind, signed, rn, rd, off, cond = d
            if rn in regs:
                path = regs[rn]
                ix = "[i]" if rn in idx else ""
                for base in [adds.get(rn, 0)] + alts.get(rn, []):
                    o = off + base
                    if o >= 0 and (load or writes):
                        out.append(f"{fmt_path(path)}+0x{o:X}{ix}:{WIDTH[(kind, signed)]}{'' if load else '(w)'}")
                o = off + adds.get(rn, 0)
                if load:
                    # A conditional word load (ldreq rd, [rn, #o]) also extends the path when
                    # rd held nothing tracked before: on the other branch rd is untracked
                    # anyway, so the guess can only add, never replace, a known value.
                    if kind == "w" and len(path) < 3 and o >= 0 and not ix and rn not in alts                             and (cond == 0xE or rd not in regs):
                        regs[rd] = path + (o,)
                        adds.pop(rd, None)
                        idx.discard(rd)
                        continue
            if load:
                regs.pop(rd, None)
                adds.pop(rd, None)
                idx.discard(rd)
                alts.pop(rd, None)
                if kind == "d":
                    regs.pop(rd + 1, None)
                    idx.discard(rd + 1)
        elif d[0] == "memr":
            _, load, kind, signed, rn, rd = d
            if rn in regs and load:
                for base in [adds.get(rn, 0)] + alts.get(rn, []):
                    out.append(f"{fmt_path(regs[rn])}+0x{base:X}[i]:{WIDTH[(kind, signed)]}")
            if load:
                regs.pop(rd, None)
                adds.pop(rd, None)
                idx.discard(rd)
        elif d[0] == "mov":
            _, rd, rm, cond = d
            if rm in regs and cond == 0xE:
                regs[rd] = regs[rm]
                adds[rd] = adds.get(rm, 0)
                (idx.add if rm in idx else idx.discard)(rd)
            else:
                regs.pop(rd, None)
                adds.pop(rd, None)
                idx.discard(rd)
        elif d[0] == "addi":
            _, rd, rn, imm, cond = d
            if cond != 0xE:
                # addeq rd, rn, #a ; addne rd, rn, #b (complementary conditions, same
                # registers, e.g. Unit::GetGrow picking Job+0x24 or Job+0x2C): rd is
                # rn+a or rn+b, so the next access is reported at both offsets.
                nxt = decode(struct.unpack_from("<I", code, i + 4)[0]) if i + 8 <= len(code) else ("other",)
                if rn in regs and nxt[0] == "addi" and nxt[1:3] == (rd, rn) and nxt[4] == cond ^ 1                         and rd == rn:
                    regs[rd] = regs[rn]
                    base = adds.get(rn, 0)
                    adds[rd] = base + imm
                    alts[rd] = [base + nxt[3]]
                    skip = True
                    continue
                regs.pop(rd, None)
                adds.pop(rd, None)
                idx.discard(rd)
                continue
            if rn in regs:
                regs[rd] = regs[rn]
                adds[rd] = adds.get(rn, 0) + imm
                (idx.add if rn in idx else idx.discard)(rd)
            else:
                regs.pop(rd, None)
                adds.pop(rd, None)
                idx.discard(rd)
        elif d[0] == "addr":
            _, rd, rn, rm = d
            if (rn in regs) != (rm in regs):
                t = rn if rn in regs else rm
                regs[rd] = regs[t]
                adds[rd] = adds.get(t, 0)
                idx.add(rd)
            else:
                regs.pop(rd, None)
                adds.pop(rd, None)
                idx.discard(rd)
        elif d[0] == "bl":
            for r in (0, 1, 2, 3, 12, 14):
                regs.pop(r, None)
                adds.pop(r, None)
                idx.discard(r)
            cls = (rets or {}).get(va + i + d[1])
            if cls and ins >> 28 == 0xE:
                regs[0] = (cls,)
                idx.discard(0)
        elif d[0] == "wr":
            for r in d[1]:
                regs.pop(r, None)
                adds.pop(r, None)
                idx.discard(r)
    seen = []
    for x in out:
        if x not in seen:
            seen.append(x)
    return seen


def run(pattern: str, max_size: int, writes: bool) -> int:
    with open(TEXT, "rb") as fh:
        text = fh.read()
    syms = symbols()
    rx = re.compile(pattern)
    rets = getters(syms)
    n = 0
    for k, (a, name) in enumerate(syms):
        if not rx.search(name):
            continue
        end = syms[k + 1][0] if k + 1 < len(syms) else a + 4
        size = end - a
        if size > max_size or a < TEXT_VA or end > TEXT_VA + len(text):
            continue
        code = text[a - TEXT_VA:end - TEXT_VA]
        paths = analyse(code, a, writes, rets)
        print(f"{a:08X} [{size:#x}] {name}\n        " + "  ".join(paths))
        n += 1
    print(f"{n} function(s)")
    return 0


def find_bitsets(text: bytes, va: int, lo: int = 100, hi: int = 4096, window: int = 4) -> list[tuple[int, int, int]]:
    """Fixed-size bit sets and byte arrays indexed by a bounded number: a `cmp Rn, #N`
    (lo <= N <= hi) followed within `window` instructions by a byte load or store whose
    register offset is Rn shifted right by 3 or 5 (ldrb rX, [base, Rn, asr #3]: bit set
    of N bits). Returns [(address of the cmp, N, address of the access)]. The scan that
    decides whether a table may grow (config/tables/appends.csv): a set sized by a
    record count means new records would fall outside it."""
    out = []
    n = len(text) // 4
    words = struct.unpack_from(f"<{n}I", text, 0)
    for i, ins in enumerate(words):
        if ins >> 28 == 0xF or (ins & 0x0FF00000) != 0x03500000:   # CMP Rn, #imm
            continue
        rot = ((ins >> 8) & 15) * 2
        imm = ins & 0xFF
        if rot:
            imm = (imm >> rot | imm << (32 - rot)) & 0xFFFFFFFF
        if not lo <= imm <= hi:
            continue
        rn = (ins >> 16) & 15
        for j in range(i + 1, min(i + 1 + window, n)):
            w = words[j]
            if w >> 28 == 0xF or (w >> 25) & 7 != 0b011 or (w >> 4) & 1:   # LDR/STR register offset
                continue
            if (w >> 22) & 1 and w & 15 == rn and (w >> 5) & 3 in (1, 2) and (w >> 7) & 31 in (3, 5):
                out.append((va + 4 * i, imm, va + 4 * j))
                break
    return out


def bitsets(lo: int, hi: int) -> int:
    with open(TEXT, "rb") as fh:
        text = fh.read()
    syms = symbols()
    starts = [a for a, _n in syms]
    import bisect
    hits = find_bitsets(text, TEXT_VA, lo, hi)
    for a, n, acc in hits:
        k = bisect.bisect_right(starts, a) - 1
        name = syms[k][1] if k >= 0 else "?"
        print(f"{a:08X} {n:5d} entries (access {acc:08X})  {name}")
    print(f"{len(hits)} bounded bit set / byte array access(es) with a bound in {lo}..{hi}")
    return 0


SLOTS = os.path.join(ROOT, "config", "tables", "slots.csv")


def load_slots() -> list[tuple[re.Pattern, str, str]]:
    """config/tables/slots.csv: function-name regex, path prefix, table. A path that starts
    with the prefix inside a matching function is a record of that table (e.g. in Unit::
    methods, arg0+0x9C-> is the unit's Person record)."""
    import csv
    out = []
    if os.path.exists(SLOTS):
        with open(SLOTS, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                out.append((re.compile(row["function"]), row["path"], row["table"]))
    return out


def fields(table: str, max_size: int, show: int) -> int:
    """Every offset of TABLE that any function loads, with the functions that do it."""
    with open(TEXT, "rb") as fh:
        text = fh.read()
    syms = symbols()
    rets = getters(syms)
    slots = load_slots()
    acc: dict[tuple[int, str], list[str]] = {}
    pat = re.compile(r"^(.*?)\+0x([0-9A-F]+)(\[i\])?:(\w+)$")
    for k, (a, name) in enumerate(syms):
        end = syms[k + 1][0] if k + 1 < len(syms) else a + 4
        if end - a > max_size or a < TEXT_VA or end > TEXT_VA + len(text):
            continue
        prefixes = [table] + [pfx for rx, pfx, t in slots if t == table and rx.search(name)]
        for p in analyse(text[a - TEXT_VA:end - TEXT_VA], a, False, rets):
            m = pat.match(p)
            if not m:
                continue
            base = m.group(1)
            hit = base == table or any(base == pfx for pfx in prefixes[1:])
            if hit:
                key = (int(m.group(2), 16), m.group(4) + (m.group(3) or ""))
                acc.setdefault(key, []).append(f"{a:08X} {name.split('(')[0]}")
    for (off, w), fns in sorted(acc.items()):
        print(f"+0x{off:02X} {w:8} {len(fns):4}x  " + "; ".join(fns[:show]))
    print(f"{len(acc)} (offset, width) pairs for {table}")
    return 0


def selftest() -> int:
    # mov r4,r0 ; ldr r1,[r4,#12] ; ldrb r2,[r1,#4] ; ldrsh r3,[r4,#0x30] ; bl ; ldr r0,[r4,#8]
    # ; add r5,r4,#16 ; ldrh r5,[r5,#2]
    # ; ldrb r6,[r4,r3] ; add r7,r4,r6 ; ldrsb r8,[r7,#0x24]
    # ; mul r1,r1,r8 (writes r1 only) ; ldrb r9,[r0,#1]
    # ; ldreq r11,[r4,#0x9C] ; ldrsbeq r11,[r11,#0x36]  (conditional load extends the path)
    # ; addeq r4,r4,#0x40 ; addne r4,r4,#0x48 ; ldrsb r10,[r4,r6]  (both offsets)
    # ; mov r1,r1 ; ldrb r10,[r4,#1]  (r4 forgotten after the pair's access)
    prog = [0xE1A04000, 0xE594100C, 0xE5D12004, 0xE1D433F0, 0xEB000000, 0xE5940008,
            0xE2845010, 0xE1D550B2, 0xE7D46003, 0xE0847006, 0xE1D782D4,
            0xE0010891, 0xE5D09001,
            0x0594B09C, 0x01DBB3D6,
            0x02844040, 0x12844048, 0xE194A0D6,
            0xE1A01001, 0xE5D4A001]
    code = b"".join(struct.pack("<I", x) for x in prog)
    got = analyse(code, 0)
    want = ["arg0+0xC:u32", "arg0+0xC->+0x4:u8", "arg0+0x30:s16", "arg0+0x8:u32", "arg0+0x12:u16",
            "arg0+0x0[i]:u8", "arg0+0x24[i]:s8", "arg0+0x8->+0x1:u8",
            "arg0+0x9C:u32", "arg0+0x9C->+0x36:s8", "arg0+0x40[i]:s8", "arg0+0x48[i]:s8"]
    ok = got == want
    # cmp r1, #256 ; ldrhcc r2, [r0, #36] ; ldrb r3, [sp, r1, asr #3]  -> one 256-entry set;
    # cmp r1, #256 ; ldrb r3, [sp, r2, asr #3] (another register) -> none
    bs = find_bitsets(struct.pack("<3I", 0xE3510C01, 0x31D022B4, 0xE7DD31C1), 0x1000)
    bs_none = find_bitsets(struct.pack("<2I", 0xE3510C01, 0xE7DD31C2), 0x1000)
    ok_bs = bs == [(0x1000, 256, 0x1008)] and bs_none == []
    print("evidence selftest:", "PASS" if ok and ok_bs else f"FAIL got {got} bitsets {bs} {bs_none}")
    return 0 if ok and ok_bs else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pattern", nargs="?")
    ap.add_argument("--max-size", type=lambda s: int(s, 0), default=0x400)
    ap.add_argument("--writes", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--fields", metavar="TABLE", help="aggregate every load of TABLE records (getter returns + config/tables/slots.csv)")
    ap.add_argument("--show", type=int, default=4, help="with --fields: functions listed per offset")
    ap.add_argument("--bitsets", nargs="?", const="100:4096", metavar="LO:HI",
                    help="list fixed-size bit sets / byte arrays indexed by a number checked against "
                         "a constant LO..HI (default 100:4096): the fixed-array scan for appends")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.bitsets:
        lo, _, hi = a.bitsets.partition(":")
        return bitsets(int(lo, 0), int(hi or lo, 0))
    if a.fields:
        return fields(a.fields, a.max_size if a.max_size != 0x400 else 0x4000, a.show)
    if not a.pattern:
        ap.error("give a REGEX or --selftest")
    return run(a.pattern, a.max_size, a.writes)


if __name__ == "__main__":
    sys.exit(main())
