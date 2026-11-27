#!/usr/bin/env python3
"""Host differential test of the staff batch (src/readable/staff_range/) against the game's own ARM code.

    python src/readable/staff_range/tests/staff_range_diff.py             all functions, 300 cases each
    python src/readable/staff_range/tests/staff_range_diff.py -n 1500 --seed 7    the long run
    python src/readable/staff_range/tests/staff_range_diff.py --only unit_status_staff_hit
    python src/readable/staff_range/tests/staff_range_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/shop_price/tests/shop_price_diff.py (the C driver body of
src/readable/sheet/tests/sheet_diff.py, the ARM interpreter src/readable/battle/tests/arm_mini.py), with
the fifth-argument and cache-guard additions of the parked AI-score test (ai_score_diff.py, round 11):
for every readable function of src/readable/staff_range/ the test makes up guest states (units with a
class record and a staff exp byte, item records with a might byte and item flags, a WeaponBonus row, the
one-time caches; all random test values, never game data, and on purpose often outside the ranges the
game uses: unmapped units, items, records and rows, item 0, negative and huge stats, exp limits and
ranks, class hits of both signs, might bytes past 127, skill numbers of both signs), runs the ORIGINAL
ARM code from the owner's extracted/text.bin in arm_mini.py and the readable C function (built with the
host gcc against tools/readable/stub/) on the same memory, and compares r0, the number of bytes read
from unmapped memory AND the list of guest calls, in order, with their argument registers
(docs/DECISIONS.md F-018).

Every callee is answered by one table on both sides and listed: unit::Item::ToData, unit::Item::GetHit,
Unit::IsEquipSkill, WeaponBonus::Get, WeaponLevel::Get, WeaponLevel::GetLevel, Unit::GetWeaponExpLimit
and the four stat getters Unit::GetPowImpl / GetTechImpl / GetMdefImpl / GetLuckImpl. The stat getters
are listed with their fifth argument, the word at sp (guest_call5, round 11); the C driver counts the
readable code's store of that word into the dead stack apart, never as a write of guest data.
GetWeaponExpLimit and the stat getters fill one-time caches: on the ARM side a call reaching one of them
while one of its guards is cold gives up (as the game would reach the guard routine there), on the C side
it counts as a nested give-up. So a readable function that forgets to ask a callee's guards first is
caught. The original's own guards (GetRodHealPower's two) reach the guard routine in arm_mini.

A readable give-up before any read while the original went on is an early give-up: always safe, counted
and printed (heal asks the magic caches even for a staff without the "+ magic / 3" flag).

--plant copies src/readable/staff_range/ to build/readable/staff_range/plant/, makes one small wrong
change at a time (PLANTS below), rebuilds and reruns: every planted bug must give at least one mismatch.

Exit 0 only when every case matches (and, with --plant, every planted bug is caught). Needs
extracted/text.bin and a host C compiler (FE_HOST_CC, or the ones tools/readable/check.py looks for);
SKIPs (exit 0, says so) without them.
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
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
import arm_mini as A  # noqa: E402
from stance_diff import State, pick  # noqa: E402

TEXT = os.path.join(ROOT, "extracted", "text.bin")
OUT = os.path.join(ROOT, "build", "readable", "staff_range")
SRC_AREA = os.path.join(ROOT, "src", "readable", "staff_range")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
TO_DATA, ITEM_HIT, IS_EQUIP = 0x003D0EA4, 0x0053B2A4, 0x0052DD04
BONUS_GET, LEVEL_GET, GET_LEVEL, EXP_LIMIT = 0x001A8090, 0x001A80D4, 0x005090A4, 0x0052F824
POW, TECH, MDEF, LUCK = 0x0052A500, 0x0052C30C, 0x0052BF6C, 0x0052BC5C
STATS = (POW, TECH, MDEF, LUCK)
# answered by r0..r3 (the stat getters' fifth word is listed, not part of the answer's key)
LEAF_STUBS = {TO_DATA: 1, ITEM_HIT: 1, IS_EQUIP: 2, BONUS_GET: 1, LEVEL_GET: 0, GET_LEVEL: 2, EXP_LIMIT: 2,
              POW: 4, TECH: 4, MDEF: 4, LUCK: 4}
ARITY = dict(LEAF_STUBS)
ARITY.update({f: 5 for f in STATS})

OVERRIDES = {
    "unit_rod_heal_power": 0x0052F008,
    "unit_status_staff_hit": 0x0053135C,
    "unit_status_staff_avoid": 0x00531D30,
}
RANGES = {  # the original's code (config/functions.csv), for the coverage printed as evidence
    "unit_rod_heal_power": (0x0052F008, 0x0052F17C),
    "unit_status_staff_hit": (0x0053135C, 0x00531428),
    "unit_status_staff_avoid": (0x00531D30, 0x00531D80),
}
REACHED: dict[str, set] = {}

# caches (src/readable/staff_range/staff_range.h; the callees' from formulas.h, sheet.h, triangle.h)
HEAL_SKILL_GUARD, HEAL_SKILL, HEAL_MAGIC_GUARD, HEAL_MAGIC_MASK = 0x006D9918, 0x006D96AC, 0x006D9914, 0x006D9C40
LIMIT_GUARDS = (0x006D97B4, 0x006D97B0, 0x006D97AC)
MAG_GUARDS = (0x006D974C, 0x006D9748, 0x006D9744)
SKL_GUARDS = (0x006D9758, 0x006D9754, 0x006D9750)
LCK_GUARDS = (0x006D9778, 0x006D9774, 0x006D9770)
RES_GUARDS = (0x006D9794, 0x006D9790, 0x006D978C)
GUARDED_STUBS = {POW: MAG_GUARDS, TECH: SKL_GUARDS, MDEF: RES_GUARDS, LUCK: LCK_GUARDS, EXP_LIMIT: LIMIT_GUARDS}
ALL_GUARDS = (HEAL_SKILL_GUARD, HEAL_MAGIC_GUARD) + LIMIT_GUARDS + MAG_GUARDS + SKL_GUARDS + LCK_GUARDS + RES_GUARDS

# guest layout of the made-up state
UNIT = lambda k: 0x08000000 + k * 0x200  # noqa: E731
JOB = lambda k: 0x08010000 + k * 0x100  # noqa: E731
REC = lambda k: 0x08020000 + k * 0x80  # noqa: E731   Item records (ItemData)
ITEM = lambda k: 0x08030000 + k * 4  # noqa: E731     unit::Items (never read here: only passed on)
BONUS = 0x08040000                   # the WeaponBonus row the table answers
LEVELS = 0x08041000                  # the WeaponLevel record the table answers
NUNITS, NJOBS, NRECS, NITEMS = 5, 4, 6, 6
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]
STAT_COMMON = [0, 0, 1, 3, 5, 8, 12, 15, 20, 25, 30, 31, 32, 40, 45, 60]
STAT_ODD = [-1, -2, -3, -4, -5, 0x7FFFFFFF, -0x80000000, 0x40000000, 0x55555555, 0x3FFFFFFF]


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def sxs16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def word(st, addr: int, n: int = 4) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(n)), "little")


def is_mapped(st, addr: int) -> bool:
    return addr in st.mem


# ------------------------------------------------------------------ the made-up state
def guard(st, addr: int, cold_p: float) -> None:
    st.put(addr, 4, 0 if st.rng.random() < cold_p else st.rng.choice([1, 0x101, 0xFFFFFFFF, 3]))


def base_state(rng, cold_guards, cold_p: float = 0.012) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.fill(SP - 0x400, 0x400)  # the dead stack below sp holds junk
    for g in ALL_GUARDS:
        guard(st, g, cold_p if g in cold_guards else 0.0)
    st.put(HEAL_MAGIC_MASK, 8, 1 << rng.randrange(64) if rng.random() > 0.05 else rng.randrange(1 << 64))
    st.put(HEAL_SKILL, 2, pick(rng, list(range(1, 200)), [0, 0xFFFF, 0x8000, 0x7FFF, 0xFF9C], 0.1))
    for k in range(NJOBS):
        st.fill(JOB(k), 0x100)
        st.put(JOB(k) + 0x4C, 2, s32(pick(rng, [0, 0, 5, 10, 15, 20, 25, 30], [-1, -30, -0x8000, 0x7FFF, 300], 0.15)))
    for k in range(NUNITS):
        u = UNIT(k)
        st.fill(u, 0x200)
        st.put(u + 0xA0, 4, JOB(rng.randrange(NJOBS)) if rng.random() > 0.05 else rng.choice(UNMAPPED))
        st.put(u + 0xEE, 1, pick(rng, [0, 1, 20, 21, 50, 51, 90, 91, 140, 141, 200, 251], [255, 254, 128], 0.08))
    for k in range(NRECS):
        r = REC(k)
        st.fill(r, 0x80)
        st.put(r + 0x1F, 1, pick(rng, [0, 5, 7, 10, 15, 20, 25, 30], [0x80, 0xFF, 0x7F, 0xC8], 0.12))
    st.fill(BONUS, 0x40)
    return st


def unit_ptr(st, p_unmapped: float = 0.05) -> int:
    return st.rng.choice(UNMAPPED) if st.rng.random() < p_unmapped else UNIT(st.rng.randrange(NUNITS))


def item_ptr(st, p_zero: float = 0.0) -> int:
    r = st.rng.random()
    if r < p_zero:
        return 0
    return ITEM(st.rng.randrange(NITEMS)) if r < 0.96 else st.rng.choice(UNMAPPED)


def stat(rng) -> int:
    return s32(pick(rng, STAT_COMMON, STAT_ODD, 0.12))


def answer_rank(st, unit: int) -> None:
    """WeaponBonus::Get(6), GetWeaponExpLimit(unit, 6), WeaponLevel::Get, GetLevel for the capped exp."""
    rng = st.rng
    st.oracle[(BONUS_GET, 6)] = BONUS if rng.random() > 0.04 else rng.choice(UNMAPPED)
    limit = pick(rng, [0, 1, 20, 50, 51, 100, 141, 200, 251, 255], [-1, -0x80000000, 0x7FFFFFFF, 0x100, 300], 0.1)
    st.oracle[(EXP_LIMIT, s32(unit), 6)] = s32(limit)
    st.oracle[(LEVEL_GET,)] = LEVELS if rng.random() > 0.04 else rng.choice(UNMAPPED)
    exp = st.mem.get(unit + 0xEE, 0)
    capped = min(limit, exp)
    rank = pick(rng, [0, 1, 2, 3, 4, 5], [-1, 6, 0x40, 0x7FFFFFFF, -0x80000000, 0x10], 0.06)
    st.oracle[(GET_LEVEL, LEVELS, s32(capped))] = s32(rank)
    # a GetLevel answer for the other bound too, so a wrong min/max gives a different rank
    other = max(limit, exp)
    if other != capped:
        st.oracle[(GET_LEVEL, LEVELS, s32(other))] = s32((rank + 1 + rng.randrange(5)) % 6)


def ov(name, args):
    a = OVERRIDES[name]
    return f"ov:0x{a:08X}", [s32(x) for x in args] + [0] * (4 - len(args)), ("call", a)


# ------------------------------------------------------------------ the functions
def gen_heal(rng):
    st = base_state(rng, (HEAL_SKILL_GUARD, HEAL_MAGIC_GUARD) + LIMIT_GUARDS + MAG_GUARDS)
    unit = unit_ptr(st)
    item = item_ptr(st, 0.03)
    rec = REC(rng.randrange(NRECS)) if rng.random() > 0.05 else rng.choice(UNMAPPED)
    st.oracle[(TO_DATA, s32(item))] = rec
    if rec not in UNMAPPED and rng.random() < 0.45:  # the "+ magic / 3" flag set, with other bits
        st.put(rec, 8, word(st, rec, 8) | word(st, HEAL_MAGIC_MASK, 8))
    st.oracle[(POW, s32(unit), 0, 1, 1)] = stat(rng)
    answer_rank(st, unit)
    target = 0 if rng.random() < 0.3 else unit_ptr(st)
    st.oracle[(IS_EQUIP, s32(target), s32(sxs16(word(st, HEAL_SKILL, 2))))] = int(rng.random() < 0.45)
    return (st,) + ov("unit_rod_heal_power", [unit, item, target])


def gen_hit(rng):
    st = base_state(rng, LIMIT_GUARDS + MAG_GUARDS + SKL_GUARDS)
    unit = unit_ptr(st)
    item = item_ptr(st, 0.08)
    st.oracle[(ITEM_HIT, s32(item))] = s32(pick(rng, [0, 30, 45, 50, 60, 70, 75, 80], [-1, -100, 0x7FFFFFFF, 999], 0.1))
    st.oracle[(POW, s32(unit), 0, 1, 1)] = stat(rng)
    st.oracle[(TECH, s32(unit), 0, 1, 1)] = stat(rng)
    answer_rank(st, unit)
    return (st,) + ov("unit_status_staff_hit", [unit, item])


def gen_avoid(rng):
    st = base_state(rng, RES_GUARDS + LCK_GUARDS)
    unit = unit_ptr(st)
    item = item_ptr(st, 0.1)
    st.oracle[(MDEF, s32(unit), s32(item), 1, 1)] = stat(rng)
    st.oracle[(LUCK, s32(unit), s32(item), 1, 1)] = stat(rng)
    # an answer for "no item" too, so a stat asked without the staff gives a different value
    st.oracle[(MDEF, s32(unit), 0, 1, 1)] = stat(rng)
    st.oracle[(LUCK, s32(unit), 0, 1, 1)] = stat(rng)
    return (st,) + ov("unit_status_staff_avoid", [unit, item])


FUNCS = {
    "unit_rod_heal_power": gen_heal,
    "unit_status_staff_hit": gen_hit,
    "unit_status_staff_avoid": gen_avoid,
}


# ------------------------------------------------------------------ the ARM side
class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX to a callee of ARITY with its argument registers (an argument
    past r3 is the word at sp + 4 * (n - 4), as the callee sees it), and noting the words of the function
    under test it runs."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.listed: list[str] = []
        self.reach = None

    def call(self, target: int, ret: int) -> bool:
        if target in ARITY:
            n = ARITY[target]
            regs = list(self.r[:min(n, 4)]) + [self.mem.read(self.r[13] + 4 * k, 4) for k in range(n - 4)]
            self.listed.append(call_text(target, regs))
        return super().call(target, ret)

    def step(self, ins: int, pc: int) -> None:
        if self.reach is not None and self.reach[0] <= pc < self.reach[1]:
            self.reach[2].add(pc)
        super().step(ins, pc)


def call_text(target: int, regs) -> str:
    return f"{target:x}" + "".join(f":{r & 0xFFFFFFFF:x}" for r in regs)


def calls_field(listed: list[str]) -> str:
    return ",".join(listed) if listed else "-"


def arm_run(text: bytes, st, kind: str, args: list[int], how: tuple, name: str) -> list:
    """Expected outputs, in the order the C driver prints them: [gave_up, r0, faults, calls]."""
    mem = A.Memory(text)
    for a, d in st.regions():
        mem.map(a, d)

    def answer(f, n):
        return lambda cpu, a: st.oracle.get((f,) + tuple(x & 0xFFFFFFFF for x in a[:n]), 0)
    stubs = {f: answer(f, n) for f, n in LEAF_STUBS.items()}

    def guarded(f, inner):
        def stub(cpu, a):
            if any(not (cpu.mem.read(g, 4) & 1) for g in GUARDED_STUBS[f]):
                raise A.ColdGuard()
            return inner(cpu, a)
        return stub
    for f in GUARDED_STUBS:
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
    return [0, cpu.r[0], mem.faults, calls_field(cpu.listed)]


# ------------------------------------------------------------------ the C side
DRIVER_HEAD = r'''
/* Generated by src/readable/staff_range/tests/staff_range_diff.py: runs the staff batch on memory
   images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "staff_range.h"
'''

# patches of sheet_diff's driver body (as ai_score_diff.py, round 11): the dead-stack store of guest_call5
# counted apart, the fifth argument listed, and a guarded stub reached with a cold guard counted as a
# nested give-up
STACK_DRIVER_OLD = (
    "static void w8(Context *c, uint32_t a, uint8_t v) { (void)c; writes++; uint8_t *p = at(a, 0); if (p) *p = v; }",
    "    for (uint32_t i = 0; i < n; i++) k += snprintf(buf + k, sizeof buf - (size_t)k, \":%x\", r[i]);",
    "            c.r[13] = a[4];",
    "    char buf[96];",
    "static void oracle(Context *ctx) {\n    uint32_t f = ctx->r[15], n = 0;",
    "        } else if (!strncmp(line, \"stub \", 5)) {",
    "noracle = 0; nstubs = 0;",
)
STACK_DRIVER_NEW = (
    "static uint32_t stack_top; static int stack_writes;\n"
    "static void w8(Context *c, uint32_t a, uint8_t v) { (void)c; if (a < stack_top && a >= stack_top - 0x400u) "
    "stack_writes++; else writes++; uint8_t *p = at(a, 0); if (p) *p = v; }",
    "    for (uint32_t i = 0; i < n; i++) k += snprintf(buf + k, sizeof buf - (size_t)k, \":%x\", "
    "i < 4 ? r[i] : r32(NULL, r[13] + 4u * (i - 4u)));",
    "            c.r[13] = a[4]; stack_top = a[4]; stack_writes = 0;",
    "    char buf[128];",
    "static int nested; static uint32_t sg_f[32], sg_a[32]; static int nsg;\n"
    "static void oracle(Context *ctx) {\n    uint32_t f = ctx->r[15], n = 0;\n"
    "    for (int i = 0; i < nsg; i++) if (sg_f[i] == f && !(r32(ctx, sg_a[i]) & 1u)) nested++;",
    "        } else if (!strncmp(line, \"sguard \", 7)) {\n"
    "            if (nsg < 32) { sscanf(line + 7, \"%x %x\", &sg_f[nsg], &sg_a[nsg]); nsg++; }\n"
    "        } else if (!strncmp(line, \"stub \", 5)) {",
    "noracle = 0; nstubs = 0; nsg = 0;",
)


def driver_text() -> str:
    import sheet_diff as S  # the same driver body: page memory, call list, oracle, nested give-ups
    body = S.DRIVER.split('#include "sheet.h"\n', 1)[1]
    for old, new in zip(STACK_DRIVER_OLD, STACK_DRIVER_NEW):
        if body.count(old) != 1:
            raise SystemExit(f"staff_range_diff: sheet_diff's driver changed, cannot patch: {old[:60]!r}")
        body = body.replace(old, new)
    addrs = sorted(OVERRIDES.values())
    decls = "".join(f"void override_0x{a:08X}(Context *);\n" for a in addrs)
    table = "static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n" + "".join(
        f"    {{0x{a:08X}u, override_0x{a:08X}}},\n" for a in addrs) + "};\n"
    return DRIVER_HEAD + body.replace("@OVERRIDE_DECLS@", decls + table)


def find_cc() -> str | None:
    import check  # tools/readable/check.py: the same compiler search
    return check.find_cc()


_SHARED_OBJS: dict[str, str] = {}  # the other areas' objects, compiled once per run (plants reuse them)


def _compile(cc: str, src: str, obj: str, flags: list[str], env: dict) -> str | None:
    r = subprocess.run([cc] + flags + ["-c", src, "-o", obj], capture_output=True, text=True, env=env)
    return f"{src}:\n{r.stdout}{r.stderr}" if r.returncode else None


def build_driver(cc: str, out: str, area_dir: str, strict: bool = True) -> str:
    """Builds the driver with every source of src/readable/, this folder's taken from area_dir (a planted
    bug may leave a parameter unused: not strict then). Each source is compiled on its own, in parallel;
    the other areas' objects once per run, reused for every planted bug. The parked AI-score bodies
    (*.c.parked) are never picked up."""
    from concurrent.futures import ThreadPoolExecutor
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "staff_range_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_AREA)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(area_dir, f) for f in sorted(os.listdir(area_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "staff_range_driver.exe" if os.name == "nt" else "staff_range_driver")
    inc = ["-I", area_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
           "-I", os.path.join(ROOT, "include", "readable"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    strict_warn = ["-Wall", "-Wextra", "-Werror"]
    base = ["-std=c11", "-O1", "-fwrapv"]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    shared_dir = os.path.join(OUT, "obj_shared")
    own_dir = os.path.join(out, "obj")
    os.makedirs(shared_dir, exist_ok=True)
    os.makedirs(own_dir, exist_ok=True)
    jobs = []
    for s in sorted(others):
        if s not in _SHARED_OBJS:
            rel = os.path.relpath(s, os.path.join(ROOT, "src", "readable")).replace(os.sep, "_")
            jobs.append((s, os.path.join(shared_dir, rel[:-2] + ".o"), base + ["-w"] + inc, True))
    for s in mine:
        jobs.append((s, os.path.join(own_dir, os.path.basename(s)[:-2] + ".o"),
                     base + (strict_warn if strict else ["-w"]) + inc, False))
    with ThreadPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as pool:
        errs = list(pool.map(lambda j: _compile(cc, j[0], j[1], j[2], env), jobs))
    bad = [e for e in errs if e]
    if bad:
        raise SystemExit("staff_range_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"staff_range_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


PATHS: dict[str, dict] = {}  # what the cases met (printed as evidence)


def note_path(name: str, st, args: list[int], exp: list) -> None:
    p = PATHS.setdefault(name, {})
    if exp[0] == 1:
        key = "gave up at a cache"
    elif name == "unit_rod_heal_power":
        rec = st.oracle.get((TO_DATA, args[1]), 0)
        flag = rec not in UNMAPPED and (word(st, rec, 8) & word(st, HEAL_MAGIC_MASK, 8)) != 0
        half = args[2] != 0 and st.oracle.get((IS_EQUIP, args[2], s32(sxs16(word(st, HEAL_SKILL, 2)))), 0)
        key = ("+ magic / 3" if flag else "no magic") + (", half again" if half else "") + \
            (", unmapped record" if rec in UNMAPPED else "")
    elif name == "unit_status_staff_hit":
        key = "no staff" if args[1] == 0 else ("clamped to 0" if exp[1] == 0 else "above 0")
    else:
        key = "clamped to 0" if exp[1] == 0 else "above 0"
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
            st, kind, args, how = gen(rng)
            try:
                exp = arm_run(text, st, kind, args, how, name)
            except A.Unsupported as e:
                unsupported[name] = unsupported.get(name, 0) + 1
                if unsupported[name] == 1:
                    print(f"  ARM interpreter: {name}: {e}")
                continue
            note_path(name, st, args, exp)
            expected[cid] = (name, exp, (kind, args))
            lines.append(f"case {cid} {kind} " + " ".join(f"{x & 0xFFFFFFFF:x}" for x in args) + f" {SP:x}")
            lines += [f"stub {f:x} {k}" for f, k in LEAF_STUBS.items()]
            lines += [f"sguard {f:x} {g:x}" for f, gs in GUARDED_STUBS.items() for g in gs]
            for addr, data in st.regions():
                for off in range(0, len(data), 4096):
                    lines.append(f"mem {addr + off:x} {data[off:off + 4096].hex()}")
            for key, val in st.oracle.items():
                k = list(key) + [0] * (5 - len(key))
                lines.append("oracle " + " ".join(f"{x & 0xFFFFFFFF:x}" for x in k) + f" {val & 0xFFFFFFFF:x}")
            lines.append("run")
            cid += 1
    return lines, expected, unsupported


def parse(tok: str):
    try:
        return int(tok)
    except ValueError:
        return tok


COVERAGE: dict[str, dict] = {}


def compare(exe: str, cc: str, lines: list[str], expected: dict, show: int, quiet: bool = False):
    log = os.path.join(os.path.dirname(exe), "fe_readable.log")
    env = dict(os.environ, FE_READABLE_LOG=log, PATH=os.path.dirname(cc) + os.pathsep + os.environ.get("PATH", ""))
    r = subprocess.run([exe], input="\n".join(lines) + "\n", capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"staff_range_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
    got: dict[int, list] = {}
    flagged: dict[int, str] = {}
    for ln in r.stdout.split("\n"):
        parts = ln.split()
        if len(parts) >= 2 and parts[1] in ("WROTE-GUEST", "NO-OVERRIDE", "NESTED-GIVEUP"):
            flagged[int(parts[0])] = parts[1]
        elif parts:
            got[int(parts[0])] = [parse(x) for x in parts[1:4]] + parts[4:]  # the call list stays text
    per: dict[str, list[int]] = {}
    for c, (name, exp, inputs) in expected.items():
        res = per.setdefault(name, [0, 0, 0, 0])  # cases, mismatches, both gave up at a cache, early give-ups
        res[0] += 1
        g = got.get(c)
        if exp[0] == 0:
            cov = COVERAGE.setdefault(name, {"values": set(), "nonzero": 0, "faulty": 0, "calls": 0})
            cov["values"].add(exp[1])
            cov["nonzero"] += int(exp[1] != 0)
            cov["faulty"] += int(exp[2] != 0)
            cov["calls"] += 0 if exp[3] == "-" else exp[3].count(",") + 1
        if exp[0] == 1:
            res[2] += 1
            exp = [1, 0]  # a give-up must come before any unmapped read
        elif g is not None and g == [1, 0] and c not in flagged:
            res[3] += 1  # an early give-up: a cache it may need is cold; stops before any read; safe
            continue
        if g is None or g != exp or c in flagged:
            res[1] += 1
            if res[1] <= show and not quiet:
                why = f" ({flagged[c]})" if c in flagged else ""
                print(f"  MISMATCH {name} case {c}: original {exp}, readable {g}{why}; {inputs[0]} "
                      + " ".join(f"{x & 0xFFFFFFFF:#x}" for x in inputs[1]))
    return per


# planted bugs: (file, exact text, replacement); each text occurs once in its file
F, H = "staff_range.c", "staff_range.h"
PLANTS = [
    # the shared pieces
    (F, "unit, item, SR_WITH_EXTRAS, SR_WITH_LOSS, SR_RALLY_NONE);", "unit, item, SR_WITH_EXTRAS, SR_WITH_LOSS, 1u);"),
    (H, "#define SR_WITH_LOSS 1u", "#define SR_WITH_LOSS 0u"),
    (F, "    int32_t capped = limit < exp ? limit : exp;", "    int32_t capped = limit > exp ? limit : exp;"),
    (F, "    return guest_s8(ctx, bonus + ((gaddr)rank << 1) + column);", "    return guest_s8(ctx, bonus + ((gaddr)rank << 1));"),
    (F, "    return guest_s8(ctx, bonus + ((gaddr)rank << 1) + column);", "    return guest_s8(ctx, bonus + (gaddr)rank + column);"),
    (F, "    return guest_s8(ctx, bonus + ((gaddr)rank << 1) + column);", "    return guest_u8(ctx, bonus + ((gaddr)rank << 1) + column);"),
    # WeaponBonus::Get asked after the limit: the call order differs
    (F, "    gaddr bonus = guest_call1(ctx, SR_WeaponBonusGet, SR_STAFF_KIND);\n    int32_t exp = guest_u8(ctx, unit + SR_UNIT_STAFF_EXP);\n"
        "    int32_t limit = (int32_t)guest_call2(ctx, SR_UnitGetWeaponExpLimit, unit, SR_STAFF_KIND);\n",
     "    int32_t exp = guest_u8(ctx, unit + SR_UNIT_STAFF_EXP);\n"
     "    int32_t limit = (int32_t)guest_call2(ctx, SR_UnitGetWeaponExpLimit, unit, SR_STAFF_KIND);\n"
     "    gaddr bonus = guest_call1(ctx, SR_WeaponBonusGet, SR_STAFF_KIND);\n"),
    (F, "guest_call2(ctx, SR_WeaponLevelGetLevel, levels, (uint32_t)capped);", "guest_call2(ctx, SR_WeaponLevelGetLevel, levels, (uint32_t)exp);"),
    (H, "#define SR_UNIT_STAFF_EXP 0x0EEu", "#define SR_UNIT_STAFF_EXP 0x0EDu"),
    # unit_rod_heal_power
    (F, "    if (!fe_static_ready(ctx, S_SrHealSkillGuard) || !fe_static_ready(ctx, S_SrHealMagicGuard) ||",
     "    if (!fe_static_ready(ctx, S_SrHealMagicGuard) ||"),
    (F, "        !exp_limit_caches_ready(ctx) || !unit_stat_caches_ready(ctx, SR_STAT_MAG))\n        return (int32_t)fe_use_original(ctx);\n    gaddr record",
     "        !exp_limit_caches_ready(ctx))\n        return (int32_t)fe_use_original(ctx);\n    gaddr record"),
    (F, "    int32_t heal = READ_FIELD(ctx, ItemData, record, might);", "    int32_t heal = guest_s8(ctx, record + 0x1Fu);"),
    (F, "    int32_t heal = READ_FIELD(ctx, ItemData, record, might);", "    int32_t heal = guest_u8(ctx, record + 0x1Eu);"),
    (F, "staff_stat(ctx, SR_UnitGetPowImpl, unit, 0u) / 3);", "staff_stat(ctx, SR_UnitGetPowImpl, unit, 0u) / 4);"),
    (F, "staff_stat(ctx, SR_UnitGetPowImpl, unit, 0u) / 3);", "staff_stat(ctx, SR_UnitGetPowImpl, unit, item) / 3);"),
    # magic / 3 rounded down instead of toward zero
    (F, "staff_stat(ctx, SR_UnitGetPowImpl, unit, 0u) / 3);",
     "(int32_t)((int64_t)staff_stat(ctx, SR_UnitGetPowImpl, unit, 0u) * 0x55555556LL >> 32));"),
    (F, "    if (READ_FIELD(ctx, ItemData, record, flags) & guest_u64(ctx, S_SrHealMagicMask))",
     "    if ((uint32_t)READ_FIELD(ctx, ItemData, record, flags) & (uint32_t)guest_u64(ctx, S_SrHealMagicMask))"),
    (F, "    if (target != 0 &&\n", "    if (\n"),
    (F, "target, (uint32_t)(int32_t)guest_s16(ctx, S_SrHealSkill)) != 0)", "target, (uint32_t)guest_u16(ctx, S_SrHealSkill)) != 0)"),
    (F, "        heal = fe_add32(heal, fe_asr(heal, 1));", "        heal = fe_add32(heal, fe_asr(heal, 2));"),
    (F, "        heal = fe_add32(heal, fe_asr(heal, 1));", "        heal = fe_add32(heal, heal / 2);"),
    # unit_status_staff_hit
    (F, "    if (item == 0)\n        return 0; /* the game answers before asking anything */\n", ""),
    (F, "    if (!unit_stat_caches_ready(ctx, SR_STAT_MAG) || !unit_stat_caches_ready(ctx, SR_STAT_SKL) ||\n        !exp_limit_caches_ready(ctx))",
     "    if (!unit_stat_caches_ready(ctx, SR_STAT_MAG) || !exp_limit_caches_ready(ctx))"),
    (F, "    if (!unit_stat_caches_ready(ctx, SR_STAT_MAG) || !unit_stat_caches_ready(ctx, SR_STAT_SKL) ||\n        !exp_limit_caches_ready(ctx))",
     "    if (!unit_stat_caches_ready(ctx, SR_STAT_MAG) || !unit_stat_caches_ready(ctx, SR_STAT_SKL))"),
    (F, "READ_FIELD(ctx, JobData, READ_FIELD(ctx, Unit, unit, job), hit)", "guest_u16(ctx, READ_FIELD(ctx, Unit, unit, job) + 0x4Cu)"),
    (F, "    int32_t skill = staff_stat(ctx, SR_UnitGetTechImpl, unit, 0u);", "    int32_t skill = staff_stat(ctx, SR_UnitGetTechImpl, unit, item);"),
    (F, "    int32_t skill = staff_stat(ctx, SR_UnitGetTechImpl, unit, 0u);", "    int32_t skill = magic;"),
    (F, "    hit = fe_add32(staff_rank_bonus(ctx, unit, SR_RANK_COLUMN_HIT), hit);",
     "    hit = fe_add32(staff_rank_bonus(ctx, unit, SR_RANK_COLUMN_MIGHT), hit);"),
    (F, "    return hit < 0 ? 0 : hit;", "    return hit;"),
    # unit_status_staff_avoid
    (F, "        !fe_static_ready(ctx, S_SrResGuard2) || !unit_stat_caches_ready(ctx, SR_STAT_LCK))",
     "        !fe_static_ready(ctx, S_SrResGuard2))"),
    (F, "    if (!fe_static_ready(ctx, S_SrResGuard0) || !fe_static_ready(ctx, S_SrResGuard1) ||\n        !fe_static_ready(ctx, S_SrResGuard2) ||",
     "    if ("),
    (F, "    int32_t resistance = staff_stat(ctx, SR_UnitGetMdefImpl, unit, item);",
     "    int32_t resistance = staff_stat(ctx, SR_UnitGetMdefImpl, unit, 0u);"),
    # luck asked before resistance: the call order differs
    (F, "    int32_t resistance = staff_stat(ctx, SR_UnitGetMdefImpl, unit, item);\n    int32_t luck = staff_stat(ctx, SR_UnitGetLuckImpl, unit, item);",
     "    int32_t luck = staff_stat(ctx, SR_UnitGetLuckImpl, unit, item);\n    int32_t resistance = staff_stat(ctx, SR_UnitGetMdefImpl, unit, item);"),
    (F, "(int32_t)((uint32_t)resistance << 1));", "(int32_t)((uint32_t)resistance << 2));"),
    (F, "    int32_t avoid = fe_asr(fe_add32(luck, triple), 1);", "    int32_t avoid = fe_add32(luck, triple);"),
    (F, "    return avoid < 0 ? 0 : avoid;", "    return avoid;"),
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
        per = compare(exe, cc, lines, expected, 0, quiet=True)
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
        print("staff_range_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("staff_range_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_AREA)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"staff_range_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, cold, early) in per.items():
        total_bad += bad
        notes = ([f"{cold} cold: both gave up at the cache"] if cold else []) + \
                ([f"{early} early give-ups"] if early else [])
        print(f"  {name:30s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({'; '.join(notes)})" if notes else ""))
    for name, k in unsupported.items():
        print(f"  {name:30s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("staff_range_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:30s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    print("staff_range_diff: instructions of the original reached (literal pools are never run)")
    for name, pcs in REACHED.items():
        lo, hi = RANGES[name]
        print(f"  {name:30s} {len(pcs):5d} of {(hi - lo) // 4} words")
    print("staff_range_diff: paths met")
    for name, p in PATHS.items():
        print(f"  {name:30s} " + ", ".join(f"{k} {v}" for k, v in sorted(p.items())))
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"staff_range_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"staff_range_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
