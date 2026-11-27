#!/usr/bin/env python3
"""Host differential test of the capability batch (src/readable/capability/) against the game's own ARM code.

    python src/readable/capability/tests/capability_diff.py             all functions, 300 cases each
    python src/readable/capability/tests/capability_diff.py -n 1500 --seed 7    the long run
    python src/readable/capability/tests/capability_diff.py --only unit_capability
    python src/readable/capability/tests/capability_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/staff_range/tests/staff_range_diff.py (the C driver body of
src/readable/sheet/tests/sheet_diff.py, the ARM interpreter src/readable/battle/tests/arm_mini.py): for every
readable function of src/readable/capability/ the test makes up guest states (the stat table the game reads at
0x006D9CE0, the two stack words, the getters' one-time cache guards; all random test values, never game data,
and on purpose often outside what the game uses: stat numbers of 8 and more, negative and wrapping ones, table
entries moved to another stat, empty entries for stats other than HP, entries with a "this" adjustment, entries
naming a function that is not a getter, bools that are not 0/1, stats huge and negative), runs the ORIGINAL ARM
code from the owner's extracted/text.bin in arm_mini.py and the readable C function (built with the host gcc
against tools/readable/stub/) on the same memory, and compares r0, the number of bytes read from unmapped memory
AND the list of guest calls, in order, with their argument registers and stack words (docs/DECISIONS.md F-018).

Callees, answered by one table on both sides and listed:
- for unit_capability: the seven getters of stats 1..7 (listed with their fifth word, the word at sp: guest_call5),
  and one made-up function that is not a getter (the readable code gives up there, the original calls it: an
  early give-up). Stat 0's tail branch (B) into GetMHPImpl is NOT a call: 3dsrecomp keeps that target inside
  GetCapabilityImpl's generated code (a direct jump to the HP getter's override), so in the library the original
  makes no guest call there and the readable code runs unit_max_hp's C directly (round 15: the live capture
  r15-cap-capability showed the guest call it made before as "probe calls: 0 vs 1"). Here the original's
  GetMHPImpl runs on as ARM code, unlisted, and the callees IT calls (src/readable/sheet/tests/sheet_diff.py's
  LEAF_STUBS: GetLimit, Edit::GetCapability, IsEquipSkill, ...) are answered by one table and listed on both
  sides. About a third of the unit_capability cases are stat-0 cases on sheet_diff's made-up units (person, job,
  condition bytes, skill caches, torn and unmapped units), so the HP path is exercised on real-looking state.
- for the two totals: Unit::GetCapabilityImpl itself, listed with its two stack words (guest_call6, round 15).
The getters fill one-time caches: on the ARM side a call reaching one while one of its guards is cold gives up (as
the game would reach the guard routine there), on the C side it counts as a nested give-up. GetCapabilityImpl,
when it is the callee of a total, is guarded by every guard of the seven getters. The C driver counts the readable
code's stores of the stack words into the dead stack apart, never as a write of guest data.

A readable give-up before any unmapped read while the original went on is an early give-up: always safe, counted
and printed (stat numbers past the table, adjusted entries, entries naming no getter).

--plant copies src/readable/capability/ to build/readable/capability/plant/, makes one small wrong change at a
time (PLANTS below), rebuilds and reruns: every planted bug must give at least one mismatch. Changes that cannot
change an answer are not planted (docs/CAPABILITY.md 5 names the ones left out and why).

Exit 0 only when every case matches (and, with --plant, every planted bug is caught). Needs extracted/text.bin
and a host C compiler (FE_HOST_CC, or the ones tools/readable/check.py looks for); SKIPs (exit 0, says so) without
them.
"""
from __future__ import annotations

import argparse
import os
import random
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "readable", "battle", "tests"))
sys.path.insert(0, os.path.join(ROOT, "src", "readable", "sheet", "tests"))
sys.path.insert(0, os.path.join(ROOT, "src", "readable", "staff_range", "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
import arm_mini as A  # noqa: E402
from stance_diff import State, pick  # noqa: E402
import staff_range_diff as SR  # noqa: E402  the driver patches, build, compare

TEXT = os.path.join(ROOT, "extracted", "text.bin")
OUT = os.path.join(ROOT, "build", "readable", "capability")
SRC_AREA = os.path.join(ROOT, "src", "readable", "capability")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
STR, POW, TECH, QUICK, LUCK, DEF, MDEF = 0x0052A80C, 0x0052A500, 0x0052C30C, 0x0052D860, 0x0052BC5C, 0x0052A000, \
    0x0052BF6C
MHP, CAP = 0x0052A364, 0x0052F7A0
OTHER = 0x00100000  # a made-up "function" that is not a getter (answered by the table on both sides)
GETTERS = (STR, POW, TECH, QUICK, LUCK, DEF, MDEF)
TABLE = 0x006D9CE0
REAL_TABLE = [0] + list(GETTERS)  # the shape of the game's table: stat 0 empty, then the seven getters

import sheet_diff as S  # noqa: E402  GetMHPImpl's callees and sheet_diff's made-up units (the stat-0 cases)

# GetMHPImpl (MHP) is not stubbed: stat 0's tail branch runs its ARM code; its own callees are answered and listed
STUBS_CAP = {f: 4 for f in GETTERS + (OTHER,)}  # answered by r0..r3
STUBS_CAP.update(S.LEAF_STUBS)
STUBS_TOTAL = {CAP: 4}
ARITY = dict(S.LEAF_STUBS)
ARITY.update({f: 5 for f in GETTERS})
ARITY.update({OTHER: 4, CAP: 6})

OVERRIDES = {
    "unit_capability": 0x0052F7A0,
    "unit_capability_rating": 0x005309E0,
    "unit_capability_rating_no_weakness": 0x00532B70,
}
RANGES = {  # the original's code (config/functions.csv), for the coverage printed as evidence
    "unit_capability": (0x0052F7A0, 0x0052F820),  # the literal pool word at 0x0052F820 is never run
    "unit_capability_rating": (0x005309E0, 0x00530A34),
    "unit_capability_rating_no_weakness": (0x00532B70, 0x00532BC0),
}
REACHED: dict[str, set] = {}

# the getters' cache guards (src/readable/battle/formulas.h, src/readable/sheet/sheet.h)
GUARDS = {
    STR: (0x006D9740, 0x006D973C, 0x006D9738, 0x006D9734),
    POW: (0x006D974C, 0x006D9748, 0x006D9744),
    TECH: (0x006D9758, 0x006D9754, 0x006D9750),
    QUICK: (0x006D976C, 0x006D9768, 0x006D9764, 0x006D9760, 0x006D975C),
    LUCK: (0x006D9778, 0x006D9774, 0x006D9770),
    DEF: (0x006D9788, 0x006D9784, 0x006D9780, 0x006D977C),
    MDEF: (0x006D9794, 0x006D9790, 0x006D978C),
    MHP: (0x006D9730, 0x006D972C),
}
ALL_GUARDS = tuple(g for gs in GUARDS.values() for g in gs)
GUARDS_TOTAL = {CAP: tuple(g for f in GETTERS for g in GUARDS[f])}

UNIT = lambda k: 0x08000000 + k * 0x200  # noqa: E731   units (never read here: only passed on)
ITEM = lambda k: 0x08030000 + k * 4  # noqa: E731     unit::Items (only passed on)
NUNITS, NITEMS = 5, 6
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]
STAT_COMMON = [0, 0, 1, 3, 5, 8, 12, 15, 20, 25, 30, 31, 32, 40, 45, 60, 99]
STAT_ODD = [-1, -2, -5, 0x7FFFFFFF, -0x80000000, 0x40000000, 0x55555555, 0x3FFFFFFF]
BOOLS = [0, 1, 1, 0, 1]
BOOLS_ODD = [2, 0x100, 0x80000000, 0xFFFFFFFF]
STAT_PAST = [8, 9, 12, 15, 16, 0x20000000, 0x20000001, 0x20000007, 0xFFFFFFFF, 0xFFFFFFF8, 0x80000000]


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def word(st, addr: int, n: int = 4) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(n)), "little")


# ------------------------------------------------------------------ the made-up state
def guard(st, addr: int, cold_p: float) -> None:
    st.put(addr, 4, 0 if st.rng.random() < cold_p else st.rng.choice([1, 0x101, 0xFFFFFFFF, 3]))


def base_state(rng, cold_p: float) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.fill(SP - 0x400, 0x400)  # the dead stack below sp holds junk
    for g in ALL_GUARDS:
        guard(st, g, cold_p)
    return st


def unit_ptr(st, p_unmapped: float = 0.05) -> int:
    return st.rng.choice(UNMAPPED) if st.rng.random() < p_unmapped else UNIT(st.rng.randrange(NUNITS))


def item_ptr(st, p_zero: float = 0.3) -> int:
    r = st.rng.random()
    if r < p_zero:
        return 0
    return ITEM(st.rng.randrange(NITEMS)) if r < 0.96 else st.rng.choice(UNMAPPED)


def stat_value(rng) -> int:
    return s32(pick(rng, STAT_COMMON, STAT_ODD, 0.12))


def boolish(rng) -> int:
    return s32(pick(rng, BOOLS, BOOLS_ODD, 0.12))


def put_table(st, focus: int) -> list[tuple[int, int]]:
    """The stat table: mostly the game's shape; sometimes one entry changed so that a readable side which does
    not follow the table (or follows it wrongly) gives a different call. The changed entry is mostly the one of
    the stat asked (focus)."""
    rng = st.rng
    entries = [(f, 0) for f in REAL_TABLE]
    if rng.random() < 0.35:
        k = focus if focus < 8 and rng.random() < 0.75 else rng.randrange(8)
        how = rng.randrange(5)
        if how == 0:  # another getter at this stat (or a getter at stat 0)
            entries[k] = (rng.choice(GETTERS), 0)
        elif how == 1:  # an empty entry (for a stat other than 0: the game gives 0)
            entries[k] = (0, 0)
        elif how == 2:  # an even "this" adjustment (non-virtual): the game calls with this + adj / 2
            entries[k] = (rng.choice(GETTERS), rng.choice([2, 4, 0x10, 0x200, 0xFFFFFFFE]))
        elif how == 3:  # a function that is not a getter
            entries[k] = (OTHER, 0)
        else:  # an empty entry with an even adjustment: still "empty" for the game
            entries[k] = (0, rng.choice([2, 0x40]))
    for k, (f, adj) in enumerate(entries):
        st.put(TABLE + 8 * k, 4, f)
        st.put(TABLE + 8 * k + 4, 4, adj)
    return entries


def answer_all(st, unit: int, item: int, extras: int, loss: int, rally: int, adjs=(0,)) -> None:
    """Answers for every callee the original or a wrong readable side may ask with these (and nearby) arguments
    (keys: the callee and its r0..r3)."""
    rng = st.rng
    for adj in set(adjs):
        sadj = adj - (1 << 32) if adj & 0x80000000 else adj
        this = s32(unit + (sadj >> 1))
        for f in GETTERS + (OTHER,):
            for it in {item, 0}:
                for ex in {extras, 1, 0, loss}:
                    for lo in {loss, extras, rally, 0, 1}:
                        st.oracle[(f, this, s32(it), ex, lo)] = stat_value(rng)


def ov(name, args):
    a = OVERRIDES[name]
    return f"ov:0x{a:08X}", [s32(x) for x in args] + [0] * (4 - len(args)), ("call", a)


# ------------------------------------------------------------------ the functions
def gen_capability_hp(rng):
    """Stat 0 with the game's empty entry (sometimes an even adjustment word: still empty for the game, an early
    give-up for the readable code), now and then another stat with its entry emptied (the game gives 0, no HP),
    on sheet_diff's made-up units: the original runs on into GetMHPImpl's ARM code, the readable code into
    unit_max_hp."""
    st = S.base_state(rng)
    units = S.all_units(st)
    S.cool(st, S.HP_GUARDS)
    stat = 0 if rng.random() < 0.85 else rng.randrange(1, 8)
    entries = [(f, 0) for f in REAL_TABLE]
    if rng.random() < 0.08:
        entries[0] = (0, rng.choice([2, 0x40]))
    if stat != 0:
        entries[stat] = (0, 0)
    for k, (f, adj) in enumerate(entries):
        st.put(TABLE + 8 * k, 4, f)
        st.put(TABLE + 8 * k + 4, 4, adj)
    unit = S.unit_arg(st, units)
    item = S.item_arg(st, unit) if rng.random() < 0.7 else 0
    extras = boolish(rng)
    loss = boolish(rng)
    kind = s32(pick(rng, [0, 0, 8, 8, 1, 14], [rng.randrange(1 << 32), 0x108], 0.1))
    st.put(SP, 4, loss)
    st.put(SP + 4, 4, kind)
    if rng.random() < 0.3 and S.UNIT(0) <= unit < S.UNIT(S.NUNITS):  # the halving bit with an odd cap
        st.put(unit + 0x28, 1, st.mem[unit + 0x28] | 0x20)
        st.oracle[(S.GET_LIMIT, unit, 0)] = s32(rng.choice([-1, -3, -7, -51, 7, 9, 15]))
    return (st, STUBS_CAP, GUARDS) + ov("unit_capability", [unit, stat, item, extras])


def gen_capability(rng):
    if rng.random() < 0.35:
        return gen_capability_hp(rng)
    st = base_state(rng, 0.03)
    stat = rng.randrange(8) if rng.random() > 0.08 else rng.choice(STAT_PAST)
    entries = put_table(st, stat)
    unit = unit_ptr(st)
    item = item_ptr(st)
    extras = boolish(rng)
    loss = boolish(rng)
    rally = s32(pick(rng, [0, 0, 0, 8, 9, 14, 23, 31, 32, 33], [-1, 0x7FFFFFFF, 0x100], 0.1))
    st.put(SP, 4, loss)
    st.put(SP + 4, 4, rally)
    answer_all(st, unit, item, extras, loss, rally, [0] + [adj for _f, adj in entries])
    return (st, STUBS_CAP, GUARDS) + ov("unit_capability", [unit, stat, item, extras])


def gen_total(name):
    def gen(rng):
        st = base_state(rng, 0.006)
        unit = unit_ptr(st)
        for s in range(0, 9):
            for ex in (0, 1):
                st.oracle[(CAP, unit, s, 0, ex)] = stat_value(rng)
        st.oracle[(CAP, unit, 1, s32(unit), 1)] = stat_value(rng)
        return (st, STUBS_TOTAL, GUARDS_TOTAL) + ov(name, [unit])
    return gen


FUNCS = {
    "unit_capability": gen_capability,
    "unit_capability_rating": gen_total("unit_capability_rating"),
    "unit_capability_rating_no_weakness": gen_total("unit_capability_rating_no_weakness"),
}


# ------------------------------------------------------------------ the ARM side
class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every call to a stubbed callee of ARITY with its argument registers (an argument
    past r3 is the word at sp + 4 * (n - 4), as the callee sees it). Reaching a stubbed address by a plain branch
    counts as a call returning to lr; GetMHPImpl is not stubbed, so stat 0's `b GetMHPImpl` runs on as ARM code,
    unlisted (3dsrecomp keeps it inside the caller), and only its own callees are listed."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.listed: list[str] = []
        self.reach = None

    def call(self, target: int, ret: int) -> bool:
        if target in ARITY and target in self.stubs:
            n = ARITY[target]
            regs = list(self.r[:min(n, 4)]) + [self.mem.read(self.r[13] + 4 * k, 4) for k in range(n - 4)]
            self.listed.append(SR.call_text(target, regs))
        return super().call(target, ret)

    def step(self, ins: int, pc: int) -> None:
        if pc in self.stubs:  # entered by a branch, not a call: a tail call
            self.call(pc, self.r[14])
            return
        if self.reach is not None and self.reach[0] <= pc < self.reach[1]:
            self.reach[2].add(pc)
        super().step(ins, pc)


def arm_run(text: bytes, st, stubs_n: dict, guards: dict, args: list[int], how: tuple, name: str) -> list:
    """Expected outputs, in the order the C driver prints them: [gave_up, r0, faults, calls]."""
    mem = A.Memory(text)
    for a, d in st.regions():
        mem.map(a, d)

    def answer(f, n):
        return lambda cpu, a: st.oracle.get((f,) + tuple(x & 0xFFFFFFFF for x in a[:n]), 0)
    stubs = {f: answer(f, n) for f, n in stubs_n.items()}

    def guarded(f, inner):
        def stub(cpu, a):
            if any(not (cpu.mem.read(g, 4) & 1) for g in guards[f]):
                raise A.ColdGuard()
            return inner(cpu, a)
        return stub
    for f in guards:
        if f in stubs:
            stubs[f] = guarded(f, stubs[f])
    cpu = ListingCpu(mem, stubs, guard=GUARD)
    cpu.reach = RANGES[name] + (REACHED.setdefault(name, set()),)
    cpu.r[13], cpu.r[14] = SP, A.RETURN_SENTINEL
    for i in range(4):
        cpu.r[i] = args[i] & 0xFFFFFFFF
    try:
        cpu.run(how[1])
    except A.ColdGuard:
        return [1]
    stray = [w for w in mem.writes if not SP - 0x400 <= w[0] < SP]
    if stray:
        raise A.Unsupported(f"the original wrote guest memory outside its stack: {stray[:3]}")
    return [0, cpu.r[0], mem.faults, SR.calls_field(cpu.listed)]


# ------------------------------------------------------------------ the C side
DRIVER_HEAD = r'''
/* Generated by src/readable/capability/tests/capability_diff.py: runs the capability batch on memory
   images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "capability.h"
'''


def driver_text() -> str:
    import sheet_diff as S  # the same driver body: page memory, call list, oracle, nested give-ups
    body = S.DRIVER.split('#include "sheet.h"\n', 1)[1]
    for old, new in zip(SR.STACK_DRIVER_OLD, SR.STACK_DRIVER_NEW):
        if body.count(old) != 1:
            raise SystemExit(f"capability_diff: sheet_diff's driver changed, cannot patch: {old[:60]!r}")
        body = body.replace(old, new)
    addrs = sorted(OVERRIDES.values())
    decls = "".join(f"void override_0x{a:08X}(Context *);\n" for a in addrs)
    table = "static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n" + "".join(
        f"    {{0x{a:08X}u, override_0x{a:08X}}},\n" for a in addrs) + "};\n"
    return DRIVER_HEAD + body.replace("@OVERRIDE_DECLS@", decls + table)


def build_driver(cc: str, out: str, area_dir: str, strict: bool = True) -> str:
    """staff_range_diff's build (every source of src/readable/, this folder's taken from area_dir), with this
    batch's driver and folder."""
    saved = (SR.driver_text, SR.SRC_AREA, SR.OUT)
    SR.driver_text, SR.SRC_AREA, SR.OUT = driver_text, SRC_AREA, OUT
    try:
        exe = SR.build_driver(cc, out, area_dir, strict)
    finally:
        SR.driver_text, SR.SRC_AREA, SR.OUT = saved
    return exe


PATHS: dict[str, dict] = {}  # what the cases met (printed as evidence)


def note_path(name: str, st, args: list[int], exp: list) -> None:
    p = PATHS.setdefault(name, {})
    if exp[0] == 1:
        key = "gave up at a cache"
    elif name == "unit_capability":
        stat = args[1]
        if stat >= 8:
            key = "stat past the table"
        else:
            f, adj = word(st, TABLE + 8 * stat), word(st, TABLE + 8 * stat + 4)
            if f == 0:
                key = "HP tail call" if stat == 0 else "empty entry: 0"
            elif adj:
                key = "adjusted entry"
            elif f == OTHER:
                key = "entry names no getter"
            else:
                key = "getter" + (" (moved)" if f != REAL_TABLE[stat] else "")
    else:
        key = "sum" + (", wrapped" if exp[1] & 0x80000000 else "")
    if exp[0] == 0 and exp[2]:
        key += ", unmapped reads"
    p[key] = p.get(key, 0) + 1


def make_cases(text: bytes, n: int, seed: int, only: str | None):
    rng = random.Random(seed)
    lines = [f"arity {f:x} {k}" for f, k in ARITY.items()]
    expected: dict[int, tuple[str, list, tuple]] = {}
    unsupported: dict[str, int] = {}
    cid = 0
    for name, gen in FUNCS.items():
        if only and name != only:
            continue
        for _ in range(n):
            st, stubs_n, guards, kind, args, how = gen(rng)
            try:
                exp = arm_run(text, st, stubs_n, guards, args, how, name)
            except A.Unsupported as e:
                unsupported[name] = unsupported.get(name, 0) + 1
                if unsupported[name] == 1:
                    print(f"  ARM interpreter: {name}: {e}")
                continue
            note_path(name, st, args, exp)
            expected[cid] = (name, exp, (kind, args))
            lines.append(f"case {cid} {kind} " + " ".join(f"{x & 0xFFFFFFFF:x}" for x in args) + f" {SP:x}")
            lines += [f"stub {f:x} {k}" for f, k in stubs_n.items()]
            if name == "unit_capability":
                # C side only: a guest call of GetMHPImpl is answered (0) and listed there, so it shows as a call
                # the original never makes (the original runs on into it by a plain branch; round-15 live bug)
                lines.append(f"stub {MHP:x} 4")
            lines += [f"sguard {f:x} {g:x}" for f, gs in guards.items() if f in stubs_n for g in gs]
            for addr, data in st.regions():
                for off in range(0, len(data), 4096):
                    lines.append(f"mem {addr + off:x} {data[off:off + 4096].hex()}")
            for key, val in st.oracle.items():
                k = list(key) + [0] * (5 - len(key))
                lines.append("oracle " + " ".join(f"{x & 0xFFFFFFFF:x}" for x in k) + f" {val & 0xFFFFFFFF:x}")
            lines.append("run")
            cid += 1
    return lines, expected, unsupported


# planted bugs: (file, exact text, replacement); each text occurs once in its file
F, H = "capability.c", "capability.h"
PLANTS = [
    # unit_capability: the stack words
    (F, "    uint32_t with_loss = guest_u32(ctx, sp);\n    uint32_t rally = guest_u32(ctx, sp + 4u);",
     "    uint32_t with_loss = guest_u32(ctx, sp + 4u);\n    uint32_t rally = guest_u32(ctx, sp);"),
    (F, "    uint32_t rally = guest_u32(ctx, sp + 4u);", "    uint32_t rally = guest_u32(ctx, sp + 8u);"),
    (F, "    uint32_t rally = guest_u32(ctx, sp + 4u);", "    uint32_t rally = 0u;"),
    # the table
    (H, "#define CAP_STAT_TABLE_STEP 8u", "#define CAP_STAT_TABLE_STEP 4u"),
    (H, "#define CAP_STAT_TABLE 0x006D9CE0u", "#define CAP_STAT_TABLE 0x006D9CE8u"),
    (F, "    uint32_t adjust = guest_u32(ctx, entry + 4u);\n    if (adjust != 0)",
     "    uint32_t adjust = guest_u32(ctx, entry + 4u);\n    if (adjust & 1u)"),
    # the empty entry
    (F, "        if (stat != 0)\n            return 0;\n", ""),
    (F, "        if (stat != 0)\n            return 0;\n", "        if (stat != 0)\n            return 1;\n"),
    (F, "        if (stat != 0)\n            return 0;\n", "        if (stat > 1)\n            return 0;\n"),
    (F, "unit_max_hp(ctx, unit, with_extras, with_loss, (int32_t)rally);",
     "unit_max_hp(ctx, unit, 1u, with_loss, (int32_t)rally);"),
    (F, "unit_max_hp(ctx, unit, with_extras, with_loss, (int32_t)rally);",
     "unit_max_hp(ctx, unit, with_extras, with_loss, (int32_t)with_loss);"),
    (F, "unit_max_hp(ctx, unit, with_extras, with_loss, (int32_t)rally);",
     "unit_max_hp(ctx, unit, with_extras, with_loss, 0);"),
    # the round-15 live bug: a guest call where the library jumps (the host test must catch it now)
    (F, "return unit_max_hp(ctx, unit, with_extras, with_loss, (int32_t)rally);",
     "return (int32_t)guest_call(ctx, 0x0052A364u, unit, with_extras, with_loss, rally);"),
    # the getter call
    (F, "guest_call5(ctx, getter, unit, item, with_extras, with_loss, rally);",
     "guest_call5(ctx, getter, unit, item, with_loss, with_extras, rally);"),
    (F, "guest_call5(ctx, getter, unit, item, with_extras, with_loss, rally);",
     "guest_call5(ctx, getter, unit, 0u, with_extras, with_loss, rally);"),
    (F, "guest_call5(ctx, getter, unit, item, with_extras, with_loss, rally);",
     "guest_call(ctx, getter, unit, item, with_extras, with_loss);"),
    (F, "guest_call5(ctx, getter, unit, item, with_extras, with_loss, rally);",
     "guest_call5(ctx, getter, unit, item, with_extras != 0, with_loss, rally);"),
    # each getter's cache check
    (F, "    case CAP_UnitGetStrImpl: return unit_stat_caches_ready(ctx, CAP_STAT_STR);",
     "    case CAP_UnitGetStrImpl: return unit_stat_caches_ready(ctx, CAP_STAT_MAG);"),
    (F, "    case CAP_UnitGetPowImpl: return unit_stat_caches_ready(ctx, CAP_STAT_MAG);",
     "    case CAP_UnitGetPowImpl: return 1;"),
    (F, "    case CAP_UnitGetTechImpl: return unit_stat_caches_ready(ctx, CAP_STAT_SKL);",
     "    case CAP_UnitGetTechImpl: return unit_stat_caches_ready(ctx, CAP_STAT_LCK);"),
    (F, "    case CAP_UnitGetQuickImpl: return unit_stat_caches_ready(ctx, CAP_STAT_SPD);",
     "    case CAP_UnitGetQuickImpl: return unit_stat_caches_ready(ctx, CAP_STAT_STR);"),
    (F, "    case CAP_UnitGetLuckImpl: return unit_stat_caches_ready(ctx, CAP_STAT_LCK);",
     "    case CAP_UnitGetLuckImpl: return 1;"),
    (F, " && fe_static_ready(ctx, S_CapDefGuard3);", ";"),
    (F, "fe_static_ready(ctx, S_CapResGuard1) &&\n               fe_static_ready(ctx, S_CapResGuard2);",
     "fe_static_ready(ctx, S_CapResGuard1);"),
    # the totals
    (H, "#define CAP_TOTAL_LOSS_RATING 1u", "#define CAP_TOTAL_LOSS_RATING 0u"),
    (H, "#define CAP_TOTAL_LOSS_NO_WEAKNESS 0u", "#define CAP_TOTAL_LOSS_NO_WEAKNESS 1u"),
    (H, "#define CAP_TOTAL_FIRST 1u", "#define CAP_TOTAL_FIRST 0u"),
    (H, "#define CAP_TOTAL_END 8u", "#define CAP_TOTAL_END 7u"),
    (H, "#define CAP_TOTAL_EXTRAS 1u", "#define CAP_TOTAL_EXTRAS 0u"),
    (H, "#define CAP_TOTAL_RALLY 0u", "#define CAP_TOTAL_RALLY 1u"),
    (H, "#define CAP_TOTAL_ITEM 0u", "#define CAP_TOTAL_ITEM 1u"),
    (F, "        total = fe_add32(total, (int32_t)guest_call6(", "        total = ((int32_t)guest_call6("),
    (F, "(int32_t)guest_call6(ctx, CAP_UnitGetCapabilityImpl, unit, stat, CAP_TOTAL_ITEM,\n"
        "                                                      CAP_TOTAL_EXTRAS, with_loss, CAP_TOTAL_RALLY));",
     "(int32_t)guest_call5(ctx, CAP_UnitGetCapabilityImpl, unit, stat, CAP_TOTAL_ITEM,\n"
     "                                                      CAP_TOTAL_EXTRAS, with_loss));"),
    (F, "        !getter_caches_ready(ctx, CAP_UnitGetLuckImpl) || !getter_caches_ready(ctx, CAP_UnitGetDefImpl) ||",
     "        !getter_caches_ready(ctx, CAP_UnitGetLuckImpl) ||"),
    (F, "    if (!getter_caches_ready(ctx, CAP_UnitGetStrImpl) || !getter_caches_ready(ctx, CAP_UnitGetPowImpl) ||",
     "    if (!getter_caches_ready(ctx, CAP_UnitGetPowImpl) ||"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_AREA, d, ignore=shutil.ignore_patterns("tests"))
        path = os.path.join(d, fname)
        body = open(path, encoding="utf-8").read()
        if body.count(old) != 1:
            print(f"  planted bug {i}: its text occurs {body.count(old)} times in {fname} (the list is stale)")
            missed += 1
            continue
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body.replace(old, new))
        exe = build_driver(cc, os.path.join(OUT, "plant"), d, strict=False)
        per = SR.compare(exe, cc, lines, expected, 0, quiet=True)
        bad = sum(v[1] for v in per.values())
        hit = [k for k, v in per.items() if v[1]]
        print(f"  planted bug {i:2d} ({fname}: {old.strip()[:48]!r}): "
              + (f"caught, {bad} mismatches in {', '.join(hit)}" if bad else "NOT CAUGHT"))
        missed += 0 if bad else 1
    return missed


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=300, help="cases per function (default 300)")
    ap.add_argument("--seed", type=int, default=20261116)
    ap.add_argument("--only", help="one function name")
    ap.add_argument("--show", type=int, default=5, help="mismatches to print per function")
    ap.add_argument("--plant", action="store_true", help="also check that planted bugs are caught")
    ap.add_argument("--plant-n", type=int, help="cases per function for each planted bug (default: -n)")
    a = ap.parse_args(argv)
    if a.only and a.only not in FUNCS:
        print(f"unknown function {a.only}; one of: {', '.join(FUNCS)}")
        return 2
    if not os.path.isfile(TEXT):
        print("capability_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = SR.find_cc()
    if not cc:
        print("capability_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_AREA)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = SR.compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"capability_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, cold, early) in per.items():
        total_bad += bad
        notes = ([f"{cold} cold: both gave up at the cache"] if cold else []) + \
                ([f"{early} early give-ups"] if early else [])
        print(f"  {name:36s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({'; '.join(notes)})" if notes else ""))
    for name, k in unsupported.items():
        print(f"  {name:36s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("capability_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in SR.COVERAGE.items():
        print(f"  {name:36s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    print("capability_diff: instructions of the original reached (literal pools are never run)")
    for name, pcs in REACHED.items():
        lo, hi = RANGES[name]
        print(f"  {name:36s} {len(pcs):5d} of {(hi - lo) // 4} words")
    print("capability_diff: paths met")
    for name, p in PATHS.items():
        print(f"  {name:36s} " + ", ".join(f"{k} {v}" for k, v in sorted(p.items())))
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"capability_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"capability_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
