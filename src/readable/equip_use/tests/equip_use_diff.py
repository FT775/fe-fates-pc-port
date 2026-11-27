#!/usr/bin/env python3
"""Host differential test of the equip_use batch (Unit::CanItemEquip) against the game's own ARM code.

    python src/readable/equip_use/tests/equip_use_diff.py             300 cases
    python src/readable/equip_use/tests/equip_use_diff.py -n 1500 --seed 7    the long run
    python src/readable/equip_use/tests/equip_use_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/shop_price/tests/shop_price_diff.py (the C driver body of
src/readable/sheet/tests/sheet_diff.py, the ARM interpreter src/readable/battle/tests/arm_mini.py): the
test makes up guest states (units with their Person and class records, Item records, ItemSubKind
records, the 21 one-time caches of Unit::CanItemEquip and the caches of the overrides it calls; all
random test values, never game data, and on purpose often outside the ranges the game uses: unmapped
units, Persons, classes and records, weapon kinds of 8 and up and negative ones, bools that are not
0/1, a combined "only for" cache that does not match its nine parts, experience caps of -1 or 2^31),
runs the ORIGINAL ARM code from the owner's extracted/text.bin in arm_mini.py and the readable C
function (built with the host gcc against tools/readable/stub/) on the same memory, and compares r0,
the number of bytes read from unmapped memory AND the list of guest calls, in order, with their
argument registers (docs/DECISIONS.md F-018).

Every callee is answered by one table on both sides and listed: unit::Item::ToData, ItemSubKind::Get,
Unit::GetWeaponExpLimit, Job::CanEquipFromSubKind, Person::IsDownload, Unit::GetCategory,
Unit::IsEquipSkill, Unit::IsFemale. None gives up.

One-time caches: the readable code must give up, before reading anything else, exactly when one of
the 30 guards it asks (its 21 own, and the 9 of the overrides it calls: GetWeaponExpLimit,
IsDownload, GetCategory) is cold (bit 0 clear), and must not give up otherwise. The test knows
which guard it made cold, so it checks both ways: a case with a cold guard must give [gave up, 0
unmapped bytes] on the readable side, whatever the original did (a cold own cache makes the original
reach the guard routine __cxa_guard_acquire, or not, if that path never reads it; a cold callee cache
is not seen by the original, whose callees the table answers); a case with every guard warm must
match the original exactly, so a give-up there is a mismatch. Cases with a cold callee guard where the
original went on are counted apart as "early give-ups" (safe: the original runs; docs/ITEM.md
section 5). Every one of the 30 guards is made cold in turn, so each is tested on every run.
Callees are answered by the table, never by their overrides, so a nested give-up cannot happen here.

--plant copies src/readable/equip_use/ to build/readable/equip_use/plant/, makes one small wrong
change at a time (PLANTS below), rebuilds and reruns: every planted bug must give at least one
mismatch.

Exit 0 only when every case matches (and, with --plant, every planted bug is caught). Needs
extracted/text.bin and a host C compiler (FE_HOST_CC, or the ones tools/readable/check.py looks
for); SKIPs (exit 0, says so) without them.
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
OUT = os.path.join(ROOT, "build", "readable", "equip_use")
SRC_EU = os.path.join(ROOT, "src", "readable", "equip_use")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
TO_DATA, SUBKIND, EXP_LIMIT = 0x003D0EA4, 0x0019B97C, 0x0052F824
CAN_SUB, IS_DOWNLOAD, GET_CAT, HAS_SKILL, IS_FEMALE = 0x00524420, 0x0053DFEC, 0x0052B728, 0x0052DD04, 0x00533938
LEAF_STUBS = {TO_DATA: 1, SUBKIND: 1, EXP_LIMIT: 2, CAN_SUB: 2, IS_DOWNLOAD: 1, GET_CAT: 1, HAS_SKILL: 2,
              IS_FEMALE: 1}
ARITY = dict(LEAF_STUBS)
NAMES = {TO_DATA: "ToData", SUBKIND: "ItemSubKind::Get", EXP_LIMIT: "GetWeaponExpLimit",
         CAN_SUB: "Job::CanEquipFromSubKind", IS_DOWNLOAD: "IsDownload", GET_CAT: "GetCategory",
         HAS_SKILL: "IsEquipSkill", IS_FEMALE: "IsFemale"}

OVERRIDES = {"unit_can_equip_item": 0x0052C634}
ADDR = dict(OVERRIDES)

# the caches (equip_use.h)
OWN_GUARDS = tuple(range(0x006D9804, 0x006D9858, 4))  # 21 guard words
CALLEE_GUARDS = (0x006D97B4, 0x006D97B0, 0x006D97AC, 0x006D3B3C, 0x006D97D0, 0x006D97CC, 0x006D97C8,
                 0x006D97C4, 0x006D97C0)
DARK_CAT, DARK_SKILL, RESCUE_USE, DRAW_USE = 0x006D9670, 0x006D9672, 0x006D9674, 0x006D9676
PERSON_MASKS = tuple(0x006D9B10 + 8 * i for i in range(7))  # avatar, Takumi, Ryoma, Leo, Xander, Ophelia, no warp
ITEM_MASKS = tuple(0x006D9B48 + 8 * i for i in range(9))    # avatar, dark mage, male, female, 5 royals
ANY_ONLY = 0x006D9B90
CACHE_LO, CACHE_N = 0x006D9600, 0x600
ALL_GUARDS = OWN_GUARDS + CALLEE_GUARDS
COLD_TURN = [0, 0]  # cold guards made so far, and the turn through ALL_GUARDS (reset per case set)
COLD_SEEN: dict[int, int] = {}  # cases per cold guard (printed as evidence)


def any_cold(st) -> bool:
    """Is any of the 30 guards cold (bit 0 clear) in this state? (fe_static_ready's test)"""
    return any((word(st, g) & 1) == 0 for g in ALL_GUARDS)

# guest layout of the made-up state
UNIT = lambda k: 0x08100000 + k * 0x200  # noqa: E731
PERSON = lambda k: 0x08110000 + k * 0x100  # noqa: E731
JOB = lambda k: 0x08120000 + k * 0x100  # noqa: E731
REC = lambda k: 0x08010000 + k * 0x68  # noqa: E731   Item records (ItemData, 0x68 bytes)
SUB = lambda i: 0x08030000 + (i & 0xFF) * 0x10  # noqa: E731   ItemSubKind records
ITEM = lambda k: 0x08000000 + k * 4  # noqa: E731     unit::Items (only passed on to ToData)
# "torn" records: the record's memory stops partway: at TORN_REC only the low word of the flags is
# mapped (the next page is not), at TORN_REC2 the flags and nothing after them; so a read the game
# makes once and a copy makes twice shows as more unmapped bytes
TORN_REC, TORN_REC2 = 0x08050FFC, 0x08052FF8
# a "torn" unit: its flag words, state and the bytes up to +0x7F are mapped, its Person and class
# pointers, weapon experience and the rest are not
TORN_UNIT = 0x08060F80
NUNITS, NRECS, NITEMS = 3, 6, 6
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]
SUB_INDICES = list(range(12)) + [-1, -128, 127, 0x40]
USES = list(range(0, 24))


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def sx(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def word(st, addr: int, n: int = 4) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(n)), "little")


def ostub(st, func: int, *args: int, value: int) -> None:
    st.oracle[(func,) + tuple(s32(a) for a in args[:LEAF_STUBS[func]])] = s32(value)


def bit64(rng) -> int:
    return 1 << rng.randrange(64) if rng.random() > 0.05 else rng.choice([0, rng.randrange(1 << 64)])


# ------------------------------------------------------------------ the made-up state
def caches(st) -> None:
    rng = st.rng
    st.zero(CACHE_LO, CACHE_N)
    for g in OWN_GUARDS + CALLEE_GUARDS:
        st.put(g, 4, rng.choice([1, 0x101, 0xFFFFFFFF]))
    if rng.random() < 0.3:  # one cold cache: each of the 30 in turn, the first and last of the 21 more often
        g = (rng.choice(OWN_GUARDS + CALLEE_GUARDS) if rng.random() < 0.7 else
             rng.choice([OWN_GUARDS[0], OWN_GUARDS[-1]]))
        if g not in (OWN_GUARDS[0], OWN_GUARDS[-1]) or COLD_TURN[0] % 3 == 0:
            g = ALL_GUARDS[COLD_TURN[1] % len(ALL_GUARDS)]  # the turn, so no guard is missed by chance
            COLD_TURN[1] += 1
        # cold is bit 0 clear: mostly 0, sometimes a word with other bits set
        st.put(g, 4, 0x100 if COLD_TURN[0] % 4 == 3 else 0)
        COLD_TURN[0] += 1
        COLD_SEEN[g] = COLD_SEEN.get(g, 0) + 1
    st.put(DARK_CAT, 2, 1 << rng.randrange(16) if rng.random() > 0.05 else rng.choice([0, 0xFFFF, 0x8001]))
    st.put(DARK_SKILL, 2, pick(rng, [1, 5, 40, 77, 120, 300], [0, 0xFFFF, 0x8000, 0xFF80], 0.35))
    st.put(RESCUE_USE, 2, pick(rng, USES, [0x100, 0xFFFF, 0x0105], 0.08))
    st.put(DRAW_USE, 2, pick(rng, USES, [0x100, 0xFFFF, 0x0107], 0.08))
    for a in PERSON_MASKS:
        st.put(a, 8, bit64(rng))
    any_only = 0
    for a in ITEM_MASKS:
        m = bit64(rng)
        st.put(a, 8, m)
        any_only |= m
    r = rng.random()
    st.put(ANY_ONLY, 8, any_only if r < 0.85 else (0 if r < 0.9 else rng.randrange(1 << 64)))


def some_bits(st, masks, p: float) -> int:
    rng = st.rng
    v = 0
    for a in masks:
        if rng.random() < p:
            v |= word(st, a, 8)
    if rng.random() < 0.1:
        v |= rng.randrange(1 << 64)
    return v


def base_state(rng) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.fill(SP - 0x400, 0x400)  # the dead stack below sp holds junk
    caches(st)
    for k in range(NUNITS):
        p, j = PERSON(k), JOB(k)
        st.fill(p, 0x98)
        st.fill(j, 0x80)
        st.put(p, 8, some_bits(st, PERSON_MASKS, 0.3))
        st.put(j, 8, some_bits(st, PERSON_MASKS, 0.08))
    for k in range(NUNITS):
        u = UNIT(k)
        st.fill(u, 0x140)
        st.put(u, 8, some_bits(st, PERSON_MASKS, 0.08))
        state = word(st, u + 8)
        st.put(u + 8, 4, state | 0x10000000 if rng.random() < 0.35 else state & ~0x10000000)
        r = rng.random()
        st.put(u + 0x9C, 4, PERSON(rng.randrange(NUNITS)) if r < 0.93 else rng.choice(UNMAPPED + [0]))
        r = rng.random()
        st.put(u + 0xA0, 4, JOB(rng.randrange(NUNITS)) if r < 0.95 else rng.choice(UNMAPPED + [0]))
        for i in range(8):
            st.put(u + 0xE8 + i, 1, pick(rng, [0, 1, 20, 21, 50, 51, 95, 96, 160, 161, 250, 251, 251, 251],
                                         [255, 0x80], 0.1))
    for k in range(NRECS):
        r = REC(k)
        st.fill(r, 0x68)
        st.put(r, 8, some_bits(st, ITEM_MASKS, 0.12))
        st.put(r + 0x1A, 1, s32(rng.choice(SUB_INDICES)) & 0xFF)
        st.put(r + 0x1B, 1, rng.choice([word(st, RESCUE_USE, 2) & 0xFF, word(st, DRAW_USE, 2) & 0xFF]
                                       + USES[:6] + [rng.randrange(256)]))
        st.put(r + 0x1C, 1, pick(rng, [0, 0, 0, 1, 1, 21, 51, 96, 161, 251], [255, 0x80, 0x7F], 0.1))
    st.put(TORN_REC, 4, some_bits(st, ITEM_MASKS, 0.5) & 0xFFFFFFFF)
    st.put(TORN_REC2, 8, some_bits(st, ITEM_MASKS, 0.5))
    st.fill(TORN_UNIT, 0x80)
    st.put(TORN_UNIT, 8, some_bits(st, PERSON_MASKS, 0.5))
    st.put(TORN_UNIT + 8, 4, word(st, TORN_UNIT + 8) | 0x10000000 if rng.random() < 0.6 else 0)
    for i in SUB_INDICES:
        st.fill(SUB(i), 0x10)
        st.put(SUB(i) + 1, 1, pick(rng, [0, 1, 2, 3, 4, 5, 6, 6, 7, 7], [8, 9, 0xFF, 0x80, 0xF9, 0x7F], 0.12))
    return st


def answers(st, unit: int, item: int, rec: int) -> None:
    """One answer per callee and argument list a case can reach, on both sides."""
    rng = st.rng
    ostub(st, TO_DATA, item, value=rec)
    for i in SUB_INDICES + [0]:
        ostub(st, SUBKIND, s32(i), value=SUB(i) if rng.random() > 0.03 else rng.choice(UNMAPPED))
    kinds = {sx(st.mem.get(SUB(i) + 1, 0), 8) for i in SUB_INDICES} | {0}
    for kd in kinds:
        ostub(st, EXP_LIMIT, unit, s32(kd), value=pick(rng, [0, 1, 21, 51, 96, 161, 251, 251, 251, 251],
                                                       [-1, 0x7FFFFFFF, -0x80000000, 255, 256], 0.1))
    job = word(st, unit + 0xA0) if unit not in UNMAPPED and unit != TORN_UNIT else 0
    for i in SUB_INDICES + [0]:
        ostub(st, CAN_SUB, job, s32(i), value=pick(rng, [0, 1, 1], [2, 0xFFFFFFFF, 0x100], 0.1))
    person = word(st, unit + 0x9C) if unit not in UNMAPPED and unit != TORN_UNIT else 0
    ostub(st, IS_DOWNLOAD, person, value=pick(rng, [0, 1], [2, 0x100], 0.1))
    dark = word(st, DARK_CAT, 2)
    ostub(st, GET_CAT, unit, value=(rng.randrange(1 << 16) & ~dark) | (dark if rng.random() < 0.5 else 0)
          if rng.random() > 0.05 else rng.randrange(1 << 32))
    ostub(st, HAS_SKILL, unit, s32(sx(word(st, DARK_SKILL, 2), 16)), value=pick(rng, [0, 1], [2, 0x80000000], 0.1))
    ostub(st, IS_FEMALE, unit, value=pick(rng, [0, 1], [2, 0x100], 0.3))


def bool_arg(rng) -> int:
    return pick(rng, [0, 1], [2, 0x100, 0xFFFFFFFF, 0x80000000], 0.15)


def gen_equip(rng):
    st = base_state(rng)
    r = rng.random()
    unit = UNIT(rng.randrange(NUNITS)) if r < 0.92 else (TORN_UNIT if r < 0.97 else rng.choice(UNMAPPED))
    item = ITEM(rng.randrange(NITEMS)) if rng.random() > 0.05 else rng.choice(UNMAPPED + [0])
    r = rng.random()
    rec = REC(rng.randrange(NRECS)) if r < 0.88 else rng.choice([TORN_REC, TORN_REC2] * 2 + UNMAPPED)
    allow_staff = bool_arg(rng)
    if rec in [REC(k) for k in range(NRECS)] and rng.random() < 0.3:
        # a staff the "no warp" test reaches: kind 6, rank 0, a use near the two cached ones
        idx = rng.choice(SUB_INDICES)
        st.put(SUB(idx) + 1, 1, 6)
        st.put(rec + 0x1A, 1, s32(idx) & 0xFF)
        st.put(rec + 0x1C, 1, 0)
        st.put(rec + 0x1B, 1, rng.choice([word(st, RESCUE_USE, 2), word(st, DRAW_USE, 2), rng.randrange(256)]) & 0xFF)
        if unit in [UNIT(k) for k in range(NUNITS)] and rng.random() < 0.7:
            st.put(unit, 8, word(st, unit, 8) | word(st, PERSON_MASKS[6], 8))
        allow_staff = 1 if rng.random() < 0.9 else allow_staff
    elif rec in [REC(k) for k in range(NRECS)] and rng.random() < 0.4:
        # an "only for" weapon the nine tests reach: kind 0..5, rank 0, one "only for" bit (sometimes more)
        idx = rng.choice(SUB_INDICES)
        st.put(SUB(idx) + 1, 1, rng.randrange(6))
        st.put(rec + 0x1A, 1, s32(idx) & 0xFF)
        st.put(rec + 0x1C, 1, 0)
        st.put(rec, 8, word(st, rng.choice(ITEM_MASKS), 8) | some_bits(st, ITEM_MASKS, 0.08))
    answers(st, unit, item, rec)
    a = ADDR["unit_can_equip_item"]
    return st, f"ov:0x{a:08X}", [unit, item, allow_staff, bool_arg(rng)], ("call", a, None)


FUNCS = {"unit_can_equip_item": gen_equip}


# ------------------------------------------------------------------ the ARM side
class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX to a callee of ARITY with its argument registers."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.listed: list[str] = []

    def call(self, target: int, ret: int) -> bool:
        if target in ARITY:
            self.listed.append(call_text(target, self.r[:ARITY[target]]))
        return super().call(target, ret)


def call_text(target: int, regs) -> str:
    return f"{target:x}" + "".join(f":{r & 0xFFFFFFFF:x}" for r in regs)


def calls_field(listed: list[str]) -> str:
    return ",".join(listed) if listed else "-"


def arm_run(text: bytes, st, kind: str, args: list[int], how: tuple) -> list:
    """Expected outputs, in the order the C driver prints them: [gave_up, r0, faults, calls]."""
    mem = A.Memory(text)
    for a, d in st.regions():
        mem.map(a, d)

    def answer(f, n):
        return lambda cpu, a: st.oracle.get((f,) + tuple(x & 0xFFFFFFFF for x in a[:n]), 0)
    stubs = {f: answer(f, n) for f, n in LEAF_STUBS.items()}
    cpu = ListingCpu(mem, stubs, guard=GUARD)
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
/* Generated by src/readable/equip_use/tests/equip_use_diff.py: runs the equip_use batch on memory
   images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "equip_use.h"
'''


def driver_text() -> str:
    import sheet_diff as S  # the same driver body: page memory, call list, oracle, nested give-ups
    body = S.DRIVER.split('#include "sheet.h"\n', 1)[1]
    decls = "".join(f"void override_0x{a:08X}(Context *);\n" for a in sorted(OVERRIDES.values()))
    table = "static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n" + "".join(
        f"    {{0x{a:08X}u, override_0x{a:08X}}},\n" for a in sorted(OVERRIDES.values())) + "};\n"
    return DRIVER_HEAD + body.replace("@OVERRIDE_DECLS@", decls + table)


def find_cc() -> str | None:
    import check  # tools/readable/check.py: the same compiler search
    return check.find_cc()


_SHARED_OBJS: dict[str, str] = {}  # the other areas' objects, compiled once per run (plants reuse them)


def _compile(cc: str, src: str, obj: str, flags: list[str], env: dict) -> str | None:
    r = subprocess.run([cc] + flags + ["-c", src, "-o", obj], capture_output=True, text=True, env=env)
    return f"{src}:\n{r.stdout}{r.stderr}" if r.returncode else None


def build_driver(cc: str, out: str, eu_dir: str, strict: bool = True) -> str:
    """Builds the driver with every source of src/readable/, this folder's taken from eu_dir (a planted
    bug may leave a parameter unused: not strict then). Each source is compiled on its own, in
    parallel; the other areas' objects once per run, reused for every planted bug."""
    from concurrent.futures import ThreadPoolExecutor
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "equip_use_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_EU)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(eu_dir, f) for f in sorted(os.listdir(eu_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "equip_use_driver.exe" if os.name == "nt" else "equip_use_driver")
    inc = ["-I", eu_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
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
            jobs.append((s, os.path.join(shared_dir, rel[:-2] + ".o"), base + strict_warn + inc, True))
    for s in mine:
        jobs.append((s, os.path.join(own_dir, os.path.basename(s)[:-2] + ".o"),
                     base + (strict_warn if strict else ["-w"]) + inc, False))
    with ThreadPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as pool:
        errs = list(pool.map(lambda j: _compile(cc, j[0], j[1], j[2], env), jobs))
    bad = [e for e in errs if e]
    if bad:
        raise SystemExit("equip_use_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"equip_use_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


PATHS: dict[str, dict] = {}  # what the cases met (printed as evidence)


def note_path(name: str, exp: list) -> None:
    p = PATHS.setdefault(name, {})
    if exp[0] == 1:
        key = "gave up (own cache cold)"
    else:
        calls = [] if exp[3] == "-" else exp[3].split(",")
        last = NAMES.get(int(calls[-1].split(":")[0], 16), "?") if calls else "no call"
        key = f"{'yes' if exp[1] else 'no'} after {last}"
    p[key] = p.get(key, 0) + 1


def make_cases(text: bytes, n: int, seed: int, only: str | None):
    rng = random.Random(seed)
    lines = [f"arity {f:x} {k}" for f, k in ARITY.items()]
    expected: dict[int, tuple[str, list, tuple]] = {}
    unsupported: dict[str, int] = {}
    COLD_TURN[0] = COLD_TURN[1] = 0
    COLD_SEEN.clear()
    cid = 0
    for name, gen in FUNCS.items():
        if only and name != only:
            continue
        for _ in range(n):
            st, kind, args, how = gen(rng)
            try:
                exp = arm_run(text, st, kind, args, how)
            except A.Unsupported as e:
                unsupported[name] = unsupported.get(name, 0) + 1
                if unsupported[name] == 1:
                    print(f"  ARM interpreter: {name}: {e}")
                continue
            note_path(name, exp)
            expected[cid] = (name, exp, (kind, args), any_cold(st))
            lines.append(f"case {cid} {kind} " + " ".join(f"{x & 0xFFFFFFFF:x}" for x in args) + f" {SP:x}")
            lines += [f"stub {f:x} {k}" for f, k in LEAF_STUBS.items()]
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
        raise SystemExit(f"equip_use_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
    got: dict[int, list] = {}
    flagged: dict[int, str] = {}
    for ln in r.stdout.split("\n"):
        parts = ln.split()
        if len(parts) >= 2 and parts[1] in ("WROTE-GUEST", "NO-OVERRIDE", "NESTED-GIVEUP"):
            flagged[int(parts[0])] = parts[1]
        elif parts:
            got[int(parts[0])] = [parse(x) for x in parts[1:4]] + parts[4:]  # the call list stays text
    per: dict[str, list[int]] = {}
    for c, (name, exp, inputs, cold) in expected.items():
        res = per.setdefault(name, [0, 0, 0, 0])  # cases, mismatches, gave-up cases, early give-ups
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
        elif cold:
            # a guard is cold that the original did not reach (a callee's, or an own one off its path):
            # the readable code must give up before reading anything; the original goes on. Safe.
            exp = [1, 0]
            if g == exp and c not in flagged:
                res[3] += 1
                continue
        # every guard warm: the readable result must be the original's; a give-up is a mismatch
        if g is None or g != exp or c in flagged:
            res[1] += 1
            if res[1] <= show and not quiet:
                why = f" ({flagged[c]})" if c in flagged else ""
                print(f"  MISMATCH {name} case {c}: original {exp}, readable {g}{why}; {inputs[0]} "
                      + " ".join(f"{x & 0xFFFFFFFF:#x}" for x in inputs[1]))
    return per


# planted bugs: (file, exact text, replacement); each text occurs once in its file
F = "equip_use.c"
PLANTS = [
    # caches
    (F, "    for (gaddr g = S_EuGuardFirst; g <= S_EuGuardLast; g += S_EuGuardStep)",
     "    for (gaddr g = S_EuGuardFirst + 4u; g <= S_EuGuardLast; g += S_EuGuardStep)"),
    (F, "    for (gaddr g = S_EuGuardFirst; g <= S_EuGuardLast; g += S_EuGuardStep)",
     "    for (gaddr g = S_EuGuardFirst; g < S_EuGuardLast; g += S_EuGuardStep)"),
    # the give-up test as a whole: always give up; one extra (cold) guard; each callee guard left out
    (F, "    if (!caches_ready(ctx))\n        return fe_use_original(ctx);",
     "    if (1)\n        return fe_use_original(ctx);"),
    (F, "    return fe_static_ready(ctx, S_EuExpLimitGuardA) &&",
     "    return fe_static_ready(ctx, 0x006D9858u) && fe_static_ready(ctx, S_EuExpLimitGuardA) &&"),
] + [
    (F, f"fe_static_ready(ctx, {g}) &&", "1 &&") for g in
    ("S_EuExpLimitGuardA", "S_EuExpLimitGuardB", "S_EuExpLimitGuardC", "S_EuDownloadGuard",
     "S_EuCatGuard0", "S_EuCatGuard1", "S_EuCatGuard2", "S_EuCatGuard3")
] + [
    (F, "fe_static_ready(ctx, S_EuCatGuard4);", "1;"),
    # kind tests
    (F, "    if (allow_staff == 0 && kind == EU_KIND_STAFF)\n", "    if (allow_staff != 1 && kind == EU_KIND_STAFF)\n"),
    (F, "    if (kind >= EU_KIND_COUNT)\n        return 0;", "    if ((uint32_t)kind >= EU_KIND_COUNT)\n        return 0;"),
    (F, "    int32_t kind = guest_s8(ctx, subkind_of(ctx, record) + EU_SUBKIND_KIND);",
     "    int32_t kind = guest_u8(ctx, subkind_of(ctx, record) + EU_SUBKIND_KIND);"),
    # the rank
    (F, "    if (current_rank != 0) {", "    if (current_rank == 1) {"),
    (F, "        reach = cap < exp ? cap : exp;", "        reach = cap > exp ? cap : exp;"),
    (F, "        reach = cap < exp ? cap : exp;", "        reach = (uint32_t)cap < (uint32_t)exp ? cap : exp;"),
    (F, "    if (reach < (int32_t)READ_FIELD(ctx, ItemData, record, weapon_rank))",
     "    if (reach <= (int32_t)READ_FIELD(ctx, ItemData, record, weapon_rank))"),
    (F, "        int32_t exp = guest_u8(ctx, FIELD_ADDR(Unit, unit, weapon_exp) + (gaddr)kind);",
     "        int32_t exp = guest_u8(ctx, FIELD_ADDR(Unit, unit, weapon_exp) + (gaddr)kind + 1u);"),
    # stones
    (F, "record) + EU_SUBKIND_KIND) == EU_KIND_STONE &&", "record) + EU_SUBKIND_KIND) == EU_KIND_STAFF &&"),
    (F, "        guest_call2(ctx, EU_JobCanEquipFromSubKind, READ_FIELD(ctx, Unit, unit, job),",
     "        guest_call2(ctx, EU_JobCanEquipFromSubKind, READ_FIELD(ctx, Unit, unit, person),"),
    # the "only for" tests
    (F, "    if ((flags & guest_u64(ctx, S_EuAnyOnly)) != 0) {", "    if ((flags & guest_u64(ctx, S_EuAvatarOnly)) != 0) {"),
    # the avatar test reading the flags again: 8 more unmapped bytes for an unmapped record
    (F, "        if (!personal_ok(ctx, unit, flags, S_EuAvatarOnly, S_EuAvatarFlag))",
     "        if (!personal_ok(ctx, unit, item_flags(ctx, record), S_EuAvatarOnly, S_EuAvatarFlag))"),
    (F, "    if ((unit_flags(ctx, unit, &person) & guest_u64(ctx, person_mask)) == 0)\n        return 0;",
     "    if ((unit_flags(ctx, unit, &person) & guest_u64(ctx, person_mask)) == 0)\n        return 1;"),
    (F, "    if ((READ_FIELD(ctx, Unit, unit, state_flags) & EU_UNIT_DOWNLOAD_ONLY) &&",
     "    if ((READ_FIELD(ctx, Unit, unit, state_flags) & 0x08000000u) &&"),
    # the Person read again for IsDownload: more unmapped reads for an unmapped unit
    (F, "        guest_call1(ctx, EU_PersonIsDownload, person) == 0)",
     "        guest_call1(ctx, EU_PersonIsDownload, READ_FIELD(ctx, Unit, unit, person) + (person & 0u)) == 0)"),
    (F, "    return READ_FIELD(ctx, Unit, unit, private_flags) | READ_FIELD(ctx, PersonData, *person, flags) |\n"
        "           READ_FIELD(ctx, JobData, job, flags);",
     "    return READ_FIELD(ctx, Unit, unit, private_flags) | READ_FIELD(ctx, PersonData, *person, flags) |\n"
     "           (READ_FIELD(ctx, JobData, job, flags) & 0u);"),
    (F, "(guest_call1(ctx, EU_UnitGetCategory, unit) & guest_u16(ctx, S_EuDarkMageCategory)) == 0 &&",
     "(guest_call1(ctx, EU_UnitGetCategory, unit) & guest_u16(ctx, S_EuDarkMageSkill)) == 0 &&"),
    (F, "(uint32_t)(int32_t)guest_s16(ctx, S_EuDarkMageSkill)) == 0)",
     "(uint32_t)guest_u16(ctx, S_EuDarkMageSkill)) == 0)"),
    (F, "        if (item_has(ctx, record, S_EuMaleOnly) && guest_call1(ctx, EU_UnitIsFemale, unit) != 0)",
     "        if (item_has(ctx, record, S_EuMaleOnly) && guest_call1(ctx, EU_UnitIsFemale, unit) == 1)"),
    (F, "        if (item_has(ctx, record, S_EuFemaleOnly) && guest_call1(ctx, EU_UnitIsFemale, unit) == 0)",
     "        if (item_has(ctx, record, S_EuMaleOnly) && guest_call1(ctx, EU_UnitIsFemale, unit) == 0)"),
    (F, "            !personal_ok(ctx, unit, item_flags(ctx, record), S_EuLeoOnly, S_EuLeoFlag) ||",
     "            !personal_ok(ctx, unit, item_flags(ctx, record), S_EuLeoOnly, S_EuXanderFlag) ||"),
    (F, "            !personal_ok(ctx, unit, item_flags(ctx, record), S_EuOpheliaOnly, S_EuOpheliaFlag))",
     "            0)"),
    # the "no warp" staffs
    (F, "    if ((unit_flags(ctx, unit, &person) & guest_u64(ctx, S_EuNoWarpFlag)) == 0)\n        return 1;",
     "    if ((unit_flags(ctx, unit, &person) & guest_u64(ctx, S_EuOpheliaFlag)) == 0)\n        return 1;"),
    (F, "record) + EU_SUBKIND_KIND) != EU_KIND_STAFF)\n        return 1;",
     "record) + EU_SUBKIND_KIND) == EU_KIND_STONE)\n        return 1;"),
    (F, "    if (use == guest_u16(ctx, S_EuRescueUse) || use == guest_u16(ctx, S_EuDrawUse))",
     "    if (use == guest_u16(ctx, S_EuRescueUse))"),
    (F, "    uint32_t use = guest_u8(ctx, record + EU_ITEMDATA_USE);",
     "    uint32_t use = guest_u8(ctx, record + EU_ITEMDATA_USE - 1u);"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_EU, d, ignore=shutil.ignore_patterns("tests"))
        path = os.path.join(d, fname)
        body = open(path, encoding="utf-8").read()
        if body.count(old) != 1:
            print(f"  planted bug {i}: its text occurs {body.count(old)} times in {fname} (the list is stale)")
            missed += 1
            continue
        body = body.replace(old, new)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        exe = build_driver(cc, os.path.join(OUT, "plant"), d, strict=False)
        per = compare(exe, cc, lines, expected, 0, quiet=True)
        bad = sum(v[1] for v in per.values())
        hit = [k for k, v in per.items() if v[1]]
        print(f"  planted bug {i:2d} ({fname}: {old.strip()[:48]!r}): "
              + (f"caught, {bad} mismatches in {', '.join(hit[:4])}" if bad else "NOT CAUGHT"))
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
        print("equip_use_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("equip_use_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_EU)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"equip_use_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, gave, early) in per.items():
        total_bad += bad
        extra = [f"{gave} gave up"] if gave else []
        extra += [f"{early} early give-ups"] if early else []
        print(f"  {name:30s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({', '.join(extra)})" if extra else ""))
    for name, k in unsupported.items():
        print(f"  {name:30s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("equip_use_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:30s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    print("equip_use_diff: paths met (result, and the last guest call before it)")
    for name, p in PATHS.items():
        print(f"  {name}:")
        for k, v in sorted(p.items()):
            print(f"    {k:45s} {v}")
    own = [COLD_SEEN.get(g, 0) for g in OWN_GUARDS]
    callee = [COLD_SEEN.get(g, 0) for g in CALLEE_GUARDS]
    print(f"equip_use_diff: cold guards: each of the 21 own cold in {min(own)}..{max(own)} cases, "
          f"each of the 9 callee guards in {min(callee)}..{max(callee)} cases")
    if min(own + callee) == 0:
        print("equip_use_diff: a guard was never cold (raise -n)")
        total_bad += 1
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"equip_use_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"equip_use_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
