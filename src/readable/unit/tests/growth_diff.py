#!/usr/bin/env python3
"""Host differential test of the growth / level-up / experience readable code against the
game's own ARM code.

    python src/readable/unit/tests/growth_diff.py             all functions, 300 cases each
    python src/readable/unit/tests/growth_diff.py -n 2000     more cases
    python src/readable/unit/tests/growth_diff.py --seed 7    another random sequence
    python src/readable/unit/tests/growth_diff.py --only unit_grow
    python src/readable/unit/tests/growth_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/battle/tests/formula_diff.py (and its ARM interpreter
arm_mini.py): for every readable function of src/readable/unit/growth_*.c the test makes up
guest states (units, their Person, Job, Edit and Family records, parents and grandparents,
Personality rows, the ExpTable rows, the one-time caches, the map Situation; all random test
values, never game data, and on purpose often outside the ranges the game uses: negative
growths, levels 0 and 255, difficulties past 2, modes and bools that are not 0/1, unmapped
unit pointers), runs the ORIGINAL ARM code from the owner's extracted/text.bin in arm_mini.py
and the readable C function (built with the host gcc against tools/readable/stub/) on the same
memory, and compares:

  - overrides (23): r0, the number of bytes read from unmapped memory (tier 2 compares that
    count) AND the list of guest calls, in order, with their argument registers (the live
    shadow compare holds a readable function to the game's list of callee calls,
    docs/DECISIONS.md F-018). On the ARM side every BL/BLX to a callee the readable code
    calls through the guest is listed (also inside callees that run as ARM code); on the C
    side every guest call is listed (one that reaches another readable override of this
    batch, or unit_equipped_index, runs that override, as in the capture library). About 1
    case in 8 uses an unmapped unit pointer (r0 = 2 and the like), as tier 2's made-up state
    does. A one-time cache that is not filled must make the original reach the guard routine
    and the readable code give up before reading anything else; and no readable override may let
    a NESTED override give up (a guest call of another readable function that gives up inside
    while the outer one goes on: the driver counts give-ups by nesting depth, a nested one is a
    mismatch). In the capture library that runs the inner original and shows in tier 2 as a
    fault-count surplus (unit_dual_exp_damage, 2026-11-12; planted bug "review 4" below).
  - helpers: growth_random_* against Random::Initialize / GetValue(void) / GetValue(int)
    (the value stream, signed moduli included); growth_level_up_plan against the whole of
    Unit::LevelUp 0x003D8154 with the caps out of the way (the next seed, the points per
    stat, the number of GetValue(int) calls and of passes); unit_level_up_preview against the
    whole of Unit::LevelUp (the stored seed, level, eight gains and eight stat_loss bytes, and
    the calls to GetGrow / GetCapabilityImpl / GetLimit in order). There GetGrow and GetLimit
    are answered by a table and GetCapabilityImpl by "a base + the gains byte now in memory"
    on the ARM side; the readable helper gets the same through its callback.

Guest functions answered by one table on both sides: Person::Get, Person::IsFemale,
Unit::IsEquipSkill, Job::IsHigh, unit::Item::ToData (and, for the level-up, Unit::GetGrow,
Unit::GetLimit). Everything else runs as ARM code: Personality::Get, GameUserData::Get,
GetItemIndexEquipped, the ExpTable getters, GetLevelForCalculateExp, Job::GetLimitLevel,
Family::GetGrow / ParentSingle::GetGrow inside Unit::GetGrow, Family/Edit::GetLimit inside
Unit::GetLimit, the generator and the RVCT division inside Unit::LevelUp.

--plant copies src/readable/unit/ to build/readable/growth/plant/, makes one small wrong change
at a time (PLANTS below), rebuilds and reruns: every planted bug must give at least one mismatch.

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
BATTLE_TESTS = os.path.join(ROOT, "src", "readable", "battle", "tests")
sys.path.insert(0, BATTLE_TESTS)
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
import arm_mini as A  # noqa: E402
from stance_diff import State, pick  # noqa: E402

TEXT = os.path.join(ROOT, "extracted", "text.bin")
OUT = os.path.join(ROOT, "build", "readable", "growth")
SRC_UNIT = os.path.join(ROOT, "src", "readable", "unit")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
# guest functions answered by the table: address -> number of arguments in the key
PERSON_GET, IS_FEMALE, IS_EQUIP, IS_HIGH, TO_DATA = 0x0044A6F8, 0x0053ED90, 0x0052DD04, 0x00524804, 0x003D0EA4
GET_GROW, GET_LIMIT, GET_CAP = 0x005330B4, 0x005337F0, 0x0052F7A0
LEAF_STUBS = {PERSON_GET: 1, IS_FEMALE: 1, IS_EQUIP: 2, IS_HIGH: 1, TO_DATA: 1}
LEVELUP_STUBS = {GET_GROW: 2, GET_LIMIT: 2}  # GET_CAP: a memory-aware stub (below)
RANDOM_INIT, RANDOM_NEXT, RANDOM_BELOW = 0x0044ABC4, 0x0044AE14, 0x0044ADF8
LEVEL_UP = 0x003D8154
EQUIPPED = 0x005310C0  # Unit::GetItemIndexEquipped: readable unit_equipped_index (battle batch)

OVERRIDES = {  # name -> address
    "unit_grow": 0x005330B4, "edit_grow": 0x0053AC20, "family_grow": 0x0053B6CC,
    "family_parent_grow": 0x0053B740, "unit_stat_limit": 0x005337F0, "edit_limit": 0x0053AC54,
    "family_limit": 0x0053BDC4, "exp_table_battle": 0x004E6368, "exp_table_battle_threshold": 0x004E6314,
    "exp_table_dance": 0x004E634C, "exp_table_support_decline": 0x004E62F8, "exp_table_rod_decline": 0x004E62C4,
    "exp_table_rod_high_decline": 0x004E62E0, "unit_exp_level": 0x00531F24, "unit_exp_damage": 0x0052D418,
    "unit_dual_exp_damage": 0x0052F274, "unit_exp_destroy": 0x0052E184, "unit_exp_dance": 0x0052BAD0,
    "unit_exp_rod": 0x005342F4, "unit_exp_normalize": 0x0052D34C, "unit_level_limit": 0x0052E5EC,
    "job_level_limit": 0x005242F0, "situation_can_gain_exp": 0x00527D90,
}
# the callees listed on both sides, with the argument registers compared
ARITY = {PERSON_GET: 1, IS_FEMALE: 1, IS_EQUIP: 2, IS_HIGH: 1, TO_DATA: 1, GET_GROW: 2, GET_LIMIT: 2, GET_CAP: 2,
         EQUIPPED: 1, 0x0053AC20: 2, 0x0053B6CC: 3, 0x0053B740: 2, 0x0053AC54: 2, 0x0053BDC4: 2,
         0x004E6368: 1, 0x004E6314: 1, 0x004E634C: 1, 0x004E62F8: 1, 0x004E62C4: 1, 0x004E62E0: 1,
         0x00531F24: 1, 0x0052D418: 3, 0x0052F274: 3, 0x0052E184: 4, 0x0052BAD0: 3, 0x005342F4: 4,
         0x0052D34C: 2, 0x0052E5EC: 1, 0x005242F0: 1, 0x00527D90: 2}

# globals and caches (config/readable/globals.csv, src/readable/unit/growth.h)
G_PERSONALITY, G_GAMEUSER, G_EXPTABLE = 0x006D3B98, 0x006DA248, 0x006D3804
GROW_GUARD, GROW_SKILL = 0x006D979C, 0x006D9660
LEVEL_GUARD, LEVEL_MASK = 0x006D993C, 0x006D9C88
DESTROY_GUARDS = (0x006D994C, 0x006D9948, 0x006D9944, 0x006D9940)
DESTROY_MASKS = (0x006D9C90, 0x006D9C98, 0x006D9CA0, 0x006D9CA8)
JOB_GUARD1, JOB_SPECIAL, JOB_HIGH_GUARD, JOB_HIGH_MASK = 0x006D39B8, 0x006D39BC, 0x006D39B0, 0x006D3A10
LIMIT_STEP = 0x006D96E4

# guest layout of the made-up state
UNIT = lambda k: 0x08000000 + k * 0x400  # noqa: E731
PERSON = lambda k: 0x08010000 + k * 0x100  # noqa: E731
JOB = lambda k: 0x08020000 + k * 0x100  # noqa: E731
EDIT = lambda k: 0x08030000 + k * 0x40  # noqa: E731
FAMILY = lambda k: 0x08040000 + k * 0x40  # noqa: E731
PERSONALITY = 0x08050000                   # 256 records of 0x40 (only the ones used are filled)
KIN = lambda k: 0x08060000 + k * 0x100  # noqa: E731  (parents, grandparents, fixed parents)
EXPHDR = 0x08070000
EXPROW = 0x08071000                        # six sub-tables, 0x400 apart
ITEMDATA = lambda k: 0x080A0000 + k * 0x80  # noqa: E731
GUD = 0x08080000
SITUATION = 0x08090000
RATES = 0x080B0000
RNG_OBJ = 0x080C0000
EXP_SUB = [(0x0, 0x48), (0x4, 0x18), (0x8, 0x28), (0xC, 0x4), (0x10, 0x28), (0x14, 0x28)]
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]


def s8(rng, common, rare=(), p=0.1) -> int:
    return pick(rng, common, rare, p) & 0xFF


def guard(st, addr: int, cold_p: float = 0.02) -> None:
    st.put(addr, 4, 0 if st.rng.random() < cold_p else st.rng.choice([1, 0x101, 0xFFFFFFFF]))


def flag64(st, addr: int, mask_addr: int, p: float) -> None:
    mask = int.from_bytes(bytes(st.mem.get(mask_addr + i, 0) for i in range(8)), "little")
    v = int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(8)), "little")
    st.put(addr, 8, (v | mask) if st.rng.random() < p else (v & ~mask))


def personality(st, index: int) -> None:
    a = PERSONALITY + index * 0x40
    if a not in st.mem:
        st.fill(a, 0x40)
        for off in range(0x0C, 0x3C):  # boon/bane base, growth, limit: mostly small
            if st.rng.random() < 0.8:
                st.put(a + off, 1, s8(st.rng, [0, 0, 5, 10, 15, 20, -5, -10, -15, 1, 2, 4, -1, -2, -3]))


def person(st, a: int, family_p: float = 0.5) -> None:
    rng = st.rng
    st.fill(a, 0x98)
    for s in range(8):
        if rng.random() < 0.85:
            st.put(a + 0x40 + s, 1, s8(rng, [0, 5, 10, 25, 40, 45, 55, 60, 70, 90, 100], [-20, -128, 127, 150 - 256]))
            st.put(a + 0x48 + s, 1, s8(rng, [0, 0, 1, 2, -1, -2, 3], [-128, 127, 50]))
    st.put(a + 0x2A, 2, 0 if rng.random() > family_p else rng.choice([1, 2, 0x55, 0x123, 0xFFFF]))
    st.put(a + 0x34, 1, pick(rng, [0, 1, 1, 1, 2, 3], [255, 4]))
    st.put(a + 0x86, 1, s8(rng, [0, 0, 1, 2, 5], [-1, -128, 127]))
    for m in (LEVEL_MASK,) + DESTROY_MASKS:
        flag64(st, a, m, 0.15)


def base_state(rng) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.put(G_PERSONALITY, 4, PERSONALITY)
    st.put(G_GAMEUSER, 4, GUD)
    st.fill(GUD, 0x40)
    st.put(GUD + 0x2D, 1, pick(rng, [0, 1, 2, 0, 1, 2], [3, 255, 7], 0.12))
    st.put(G_EXPTABLE, 4, EXPHDR)
    for i, (off, stride) in enumerate(EXP_SUB):
        row0 = EXPROW + i * 0x400
        st.put(EXPHDR + off, 4, row0)
        for d in range(4):  # rows for difficulties 0 .. 3; past that the reads are unmapped (both sides)
            for j in range(stride):
                st.put(row0 + d * stride + j, 1, s8(rng, [0, 1, 2, 3, 5, 8, 10, 15, 20, 30, 40, -1, -5, -10],
                                                     [-128, 127, 100], 0.1))
    # caches: mostly warm
    guard(st, GROW_GUARD)
    st.put(GROW_SKILL, 2, rng.choice([1, 5, 40, 0x7FFF, 0xFFFF, 200]))
    guard(st, LEVEL_GUARD)
    st.put(LEVEL_MASK, 8, 1 << rng.randrange(64))
    for g in DESTROY_GUARDS:
        guard(st, g, 0.01)
    for m in DESTROY_MASKS:
        st.put(m, 8, 1 << rng.randrange(64))
    guard(st, JOB_GUARD1)
    guard(st, JOB_HIGH_GUARD)
    st.put(JOB_HIGH_MASK, 8, 1 << rng.randrange(64))
    st.put(JOB_SPECIAL, 4, rng.randrange(1 << 32))
    st.put(LIMIT_STEP, 4, pick(rng, [5, 5, 0, 1, 10], [-1, 0x7FFFFFFF, -0x80000000]) & 0xFFFFFFFF)
    return st


def make_unit(st, k: int) -> int:
    rng = st.rng
    u, p, j = UNIT(k), PERSON(k), JOB(k)
    st.fill(u, 0x140)
    person(st, p)
    st.fill(j, 0x80)
    st.put(u + 0x9C, 4, p)
    st.put(u + 0xA0, 4, j)
    for s in range(8):
        st.put(j + 0x24 + s, 1, s8(rng, [0, 5, 10, 15, 20, 25, 30], [-10, -128, 127]))
        st.put(j + 0x2C + s, 1, s8(rng, [0, 5, 10, 15, 20, 25, 30], [-10, -128, 127]))
        st.put(j + 0x34 + s, 1, s8(rng, [20, 25, 30, 35, 40, 60], [-1, -128, 127, 0]))
        st.put(j + 0x44 + s, 1, 0 if rng.random() < 0.75 else rng.choice([1, 51, 251, 255]))
        st.put(u + 0xD0 + s, 1, s8(rng, [0, 0, 0, 1, 2, -1], [-128, 127, 100]))
        st.put(u + 0xC8 + s, 1, s8(rng, [0, 1, 3, 5, 10, 20], [-5, 127, -128, 126]))
        st.put(u + 0xE0 + s, 1, s8(rng, [0, 0, 1, 2], [-1, 127, 255 - 256]))
    st.put(j + 0x64, 2, 0 if rng.random() < 0.5 else rng.choice([1, 0x20, 0xFFFF]))
    for base in (u, j):
        for m in (LEVEL_MASK, JOB_HIGH_MASK) + DESTROY_MASKS:
            flag64(st, base, m, 0.15)
    st.put(u + 0xF1, 1, pick(rng, [1, 2, 5, 10, 15, 19, 20, 21, 30, 39, 40], [0, 99, 255, 41, 100]))
    st.put(u + 0xF2, 1, pick(rng, [0, 1, 50, 90, 99], [100, 255, 150]))
    st.put(u + 0x12F, 1, s8(rng, [0, 0, 0, 20, -20, 1], [-128, 127, 60]))
    st.put(u + 0x130, 1, pick(rng, [0, 0, 1, 2, 3], [255, 20]))
    st.put(u + 0x132, 1, pick(rng, [0, 0, 1, 2, 3, 5, 10], [255, 128]))
    # avatar choices
    if rng.random() < 0.45:
        e = EDIT(k)
        st.fill(e, 0x20)
        st.put(u + 0xB0, 4, e)
        for off in (0x1A, 0x1B):
            idx = rng.randrange(256)
            st.put(e + off, 1, idx)
            personality(st, idx)
    else:
        st.put(u + 0xB0, 4, 0)
    # family
    if rng.random() < 0.5:
        f = FAMILY(k)
        st.fill(f, 0x28)
        st.put(u + 0xB4, 4, f)
        if rng.random() < 0.85:  # a child: the Person names a fixed parent
            st.put(p + 0x2A, 2, rng.choice([1, 2, 0x55, 0x123, 0xFFFF]))
        for half in (0, 0x14):
            r = rng.random()
            if r < 0.85:
                kp = 4 * k + half // 0x14 * 2
                person(st, KIN(kp), 0.8)
                st.put(f + half, 4, KIN(kp))
            else:
                st.put(f + half, 4, 0)
            for off in (4, 5):
                idx = rng.randrange(256)
                st.put(f + half + off, 1, idx)
                personality(st, idx)
            for off, kg in ((8, 16 + 4 * k + half // 0x14 * 2), (0xC, 17 + 4 * k + half // 0x14 * 2)):
                if rng.random() < 0.75:
                    person(st, KIN(kg), 0.2)
                    st.put(f + half + off, 4, KIN(kg))
                else:
                    st.put(f + half + off, 4, 0)
    else:
        st.put(u + 0xB4, 4, 0 if rng.random() < 0.85 else FAMILY(k) + 0x20)  # rare: a record with zero links
        if st.mem.get(u + 0xB4 + 3):
            st.zero(FAMILY(k) + 0x20, 0x28)
    return u


def answer_people(st) -> None:
    """Person::Get, IsFemale and IsEquipSkill answers for every value the code can ask about."""
    rng = st.rng
    fids = set()
    for base in [PERSON(k) for k in range(2)] + [KIN(k) for k in range(32)]:
        if base + 0x2B in st.mem:
            fids.add(st.mem[base + 0x2A] | st.mem[base + 0x2B] << 8)
    results = [0]
    for fid in fids:
        v = 0 if rng.random() < 0.12 else KIN(40 + fid % 8)
        st.oracle[(PERSON_GET, fid)] = v
        results.append(v)
    for v in set(results):
        st.oracle[(IS_FEMALE, v)] = int(rng.random() < 0.5)
    sk = st.mem.get(GROW_SKILL, 0) | st.mem.get(GROW_SKILL + 1, 0) << 8
    sk = sk - 0x10000 if sk & 0x8000 else sk
    for k in range(2):
        st.oracle[(IS_EQUIP, UNIT(k), sk & 0xFFFFFFFF)] = int(rng.random() < 0.3)
    for k in range(2):
        st.oracle[(IS_HIGH, JOB(k))] = int(rng.random() < 0.4)


def unit_state(rng, k: int = 0, unmapped_p: float = 0.12):
    st = base_state(rng)
    u = make_unit(st, k)
    if rng.random() < unmapped_p:
        u = rng.choice(UNMAPPED)
    return st, u


def stat_arg(rng) -> int:
    return pick(rng, list(range(8)), [8, 9, -1, 0x7F, 0x80], 0.06) & 0xFFFFFFFF


def mode_arg(rng) -> int:
    return pick(rng, [0, 1, 2, 3, 0, 2, 3], [4, -1, 0x103, 0x80000003], 0.1) & 0xFFFFFFFF


# ------------------------------------------------------------------ the functions
# Each generator returns (state, kind, args, how the ARM side runs).

def ov(name, args):
    a = OVERRIDES[name]
    return f"ov:0x{a:08X}", args + [0] * (4 - len(args)), ("call", a)


def gen_unit_grow(rng):
    st, u = unit_state(rng)
    answer_people(st)
    return (st,) + ov("unit_grow", [u, stat_arg(rng)])


def gen_edit_grow(rng):
    st, u = unit_state(rng, unmapped_p=0)
    e = EDIT(0)
    if e not in st.mem:
        st.fill(e, 0x20)
        for off in (0x1A, 0x1B):
            idx = rng.randrange(256)
            st.put(e + off, 1, idx)
            personality(st, idx)
    if rng.random() < 0.08:
        e = rng.choice(UNMAPPED)
    return (st,) + ov("edit_grow", [e, stat_arg(rng)])


def family_record(st, rng) -> int:
    f = FAMILY(0)
    if f not in st.mem:
        st.fill(f, 0x28)
        for half in (0, 0x14):
            person(st, KIN(half // 0x14), 0.8)
            st.put(f + half, 4, KIN(half // 0x14) if rng.random() < 0.85 else 0)
            for off in (4, 5):
                idx = rng.randrange(256)
                st.put(f + half + off, 1, idx)
                personality(st, idx)
            if rng.random() < 0.85:
                st.put(KIN(half // 0x14) + 0x2A, 2, rng.choice([3, 4, 0x77, 0x200]))
            for off, kg in ((8, 20 + half // 0x14 * 2), (0xC, 21 + half // 0x14 * 2)):
                if rng.random() < 0.75:
                    person(st, KIN(kg), 0.2)
                    st.put(f + half + off, 4, KIN(kg))
                else:
                    st.put(f + half + off, 4, 0)
    return f


def gen_family_grow(rng):
    st, _u = unit_state(rng, unmapped_p=0)
    f = family_record(st, rng)
    if rng.random() < 0.85:
        st.put(PERSON(0) + 0x2A, 2, rng.choice([1, 2, 0x55, 0x123, 0xFFFF]))
    answer_people(st)
    p = PERSON(0) if rng.random() < 0.9 else rng.choice(UNMAPPED)
    if rng.random() < 0.06:
        f = rng.choice(UNMAPPED)
    return (st,) + ov("family_grow", [f, p, stat_arg(rng)])


def gen_family_parent_grow(rng):
    st, _u = unit_state(rng, unmapped_p=0)
    f = family_record(st, rng)
    answer_people(st)
    ps = f + rng.choice([0, 0x14])
    if rng.random() < 0.06:
        ps = rng.choice(UNMAPPED)
    return (st,) + ov("family_parent_grow", [ps, stat_arg(rng)])


def gen_unit_stat_limit(rng):
    st, u = unit_state(rng)
    return (st,) + ov("unit_stat_limit", [u, stat_arg(rng)])


def gen_edit_limit(rng):
    st, e, stat = gen_edit_grow(rng)[0], None, stat_arg(rng)
    e = EDIT(0) if rng.random() < 0.93 else rng.choice(UNMAPPED)
    if EDIT(0) not in st.mem:
        st.fill(EDIT(0), 0x20)
        for off in (0x1A, 0x1B):
            idx = rng.randrange(256)
            st.put(EDIT(0) + off, 1, idx)
            personality(st, idx)
    return (st,) + ov("edit_limit", [e, stat])


def gen_family_limit(rng):
    st, _u = unit_state(rng, unmapped_p=0)
    f = family_record(st, rng)
    if rng.random() < 0.06:
        f = rng.choice(UNMAPPED)
    return (st,) + ov("family_limit", [f, stat_arg(rng)])


def gen_exp_table(name):
    def gen(rng):
        st = base_state(rng)
        if rng.random() < 0.05:
            st.put(G_EXPTABLE, 4, 0)
        d = pick(rng, [0, 1, 2, 3], [-1, 255, 0x7FFFFFFF, 0x80000000, 7]) & 0xFFFFFFFF
        return (st,) + ov(name, [d])
    return gen


def gen_exp_level(rng):
    st, u = unit_state(rng)
    return (st,) + ov("unit_exp_level", [u])


def two_units(rng):
    st = base_state(rng)
    u = make_unit(st, 0)
    o = make_unit(st, 1)
    if rng.random() < 0.08:
        u = rng.choice(UNMAPPED)
    r = rng.random()
    if r < 0.1:
        o = 0
    elif r < 0.17:
        o = rng.choice(UNMAPPED)
    # the other unit's items: equipped or not (GetItemIndexEquipped runs as ARM code)
    if o == UNIT(1):
        for slot in range(5):
            a = o + 0x108 + 4 * slot
            fl = rng.randrange(1 << 16) & ~0x4000
            if rng.random() < 0.15:
                fl |= 0x4000
            st.put(a + 2, 2, fl)
    answer_people(st)
    return st, u, o


def gen_exp_two(name, with_bool=False):
    def gen(rng):
        st, u, o = two_units(rng)
        if rng.random() < 0.06:  # the level cache cold more often: the give-up paths (nested ones too)
            st.put(LEVEL_GUARD, 4, 0)
        args = [u, mode_arg(rng), o]
        if with_bool:
            args.append(pick(rng, [0, 1, 0, 1], [2, 0x100, 0x200, 0xFFFFFFFF], 0.3))
        return (st,) + ov(name, args)
    return gen


def gen_exp_rod(rng):
    st, u, o = two_units(rng)
    item = UNIT(0) + 0x108 + 4 * rng.randrange(5) if rng.random() < 0.9 else 0
    k = rng.randrange(4)
    st.fill(ITEMDATA(k), 0x68)
    st.put(ITEMDATA(k) + 0x1D, 1, pick(rng, [0, 10, 15, 20, 25, 30, 40, 50], [255, 31, 100]))
    st.oracle[(TO_DATA, item)] = ITEMDATA(k) if rng.random() < 0.95 else rng.choice(UNMAPPED)
    return (st,) + ov("unit_exp_rod", [u, mode_arg(rng), item, o])


def special_job(st, rng, u):
    if u == UNIT(0) and rng.random() < 0.2:
        st.put(JOB_SPECIAL, 4, JOB(0))


def gen_exp_normalize(rng):
    st, u = unit_state(rng)
    answer_people(st)
    special_job(st, rng, u)
    amount = pick(rng, [0, 1, 5, 10, 30, 50, 99, 100], [101, 1000, -1, -100, 0x7FFFFFFF, -0x80000000]) & 0xFFFFFFFF
    if u == UNIT(0) and rng.random() < 0.35:  # focused: the last level below the limit, a full bar
        st.put(u + 0x130, 1, 0)
        st.put(u + 0xF1, 1, rng.choice([19, 39, 18, 38, 20, 40]))
        st.put(u + 0xF2, 1, rng.choice([50, 70, 90, 99, 0]))
        amount = rng.choice([30, 50, 60, 100])
    return (st,) + ov("unit_exp_normalize", [u, amount])


def gen_level_limit(rng):
    st, u = unit_state(rng)
    answer_people(st)
    special_job(st, rng, u)
    return (st,) + ov("unit_level_limit", [u])


def gen_job_limit(rng):
    st, u = unit_state(rng, unmapped_p=0)
    j = JOB(0) if rng.random() < 0.9 else rng.choice(UNMAPPED)
    special_job(st, rng, UNIT(0))
    return (st,) + ov("job_level_limit", [j])


def gen_can_gain_exp(rng):
    st = base_state(rng)
    st.fill(SITUATION, 0x20)
    for i in range(4):
        st.put(SITUATION + i, 1, pick(rng, [0, 1, 1, 2]))
    st.put(SITUATION + 0x17, 1, pick(rng, [0, 0, 1, 2], [255]))
    s = SITUATION if rng.random() < 0.93 else rng.choice(UNMAPPED)
    force = pick(rng, [0, 1, 2, 3, 0, 1, 2], [-1, 5, 0x80000000, 0x100]) & 0xFFFFFFFF
    return (st,) + ov("situation_can_gain_exp", [s, force])


RNG_MODS = [100, 100, 100, 1, 2, 7, 3, 1000, 0x7FFFFFFF, -5, -100, -1, -0x80000000]


def gen_rng(rng):
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.zero(RNG_OBJ, 0x10)
    seed = rng.choice([0, 1, 0xFFFFFFFF, 0x80000000, rng.randrange(1 << 32), rng.randrange(1 << 32)])
    n = pick(rng, RNG_MODS[:3], RNG_MODS[3:], 0.5) & 0xFFFFFFFF
    return st, "rng", [seed, n, 0, 0], ("rng",)


def rate_value(rng) -> int:
    return pick(rng, [0, 5, 10, 20, 30, 40, 45, 50, 55, 60, 70, 80, 95, 100], [-5, -100, 99, 101, 150, 200, 255, 399, 1000])


def levelup_unit(st, rng, cap_mode: str) -> int:
    """A mapped unit for Unit::LevelUp, with GetGrow / GetLimit / GetCapabilityImpl answers."""
    u = make_unit(st, 0)
    st.put(u + 0xC0, 4, rng.choice([0, 1, 0xFFFFFFFF, rng.randrange(1 << 32), rng.randrange(1 << 32)]))
    if rng.random() < 0.15:  # nothing grows: four passes, no point
        rates = [rng.choice([0, -5, -128]) for _ in range(8)]
    elif rng.random() < 0.15:  # only full hundreds: the remainder roll never hits
        rates = [0] * 8
        rates[rng.randrange(8)] = rng.choice([100, 200, 300])
    elif rng.random() < 0.2:  # one small rate: often several passes
        rates = [0] * 8
        rates[rng.randrange(8)] = rng.choice([1, 5, 10, 20])
    else:
        rates = [rate_value(rng) for _ in range(8)]
    for s in range(8):
        st.oracle[(GET_GROW, u, s)] = rates[s] & 0xFFFFFFFF
        st.put(RATES + 4 * s, 4, rates[s] & 0xFFFFFFFF)
        if cap_mode == "open":
            st.oracle[(GET_LIMIT, u, s)] = 99
            st.oracle[(GET_CAP, u, s)] = (-1000) & 0xFFFFFFFF  # base: the stat stays far below the cap
        else:
            st.oracle[(GET_LIMIT, u, s)] = pick(rng, [20, 30, 40, 60, 99], [0, -1, 5])
            st.oracle[(GET_CAP, u, s)] = pick(rng, [0, 5, 10, 15, 20, 25, 30, 40, 99], [-200, 200, -5]) & 0xFFFFFFFF
    return u


def gen_plan(rng):
    st = base_state(rng)
    u = levelup_unit(st, rng, "open")
    return st, "plan", [u, RATES, 0, 0], ("levelup",)


def gen_preview(rng):
    st = base_state(rng)
    u = levelup_unit(st, rng, "caps")
    return st, "preview", [u, 0, 0, 0], ("levelup",)


FUNCS = {
    "unit_grow": gen_unit_grow,
    "edit_grow": gen_edit_grow,
    "family_grow": gen_family_grow,
    "family_parent_grow": gen_family_parent_grow,
    "unit_stat_limit": gen_unit_stat_limit,
    "edit_limit": gen_edit_limit,
    "family_limit": gen_family_limit,
    "exp_table_battle": gen_exp_table("exp_table_battle"),
    "exp_table_battle_threshold": gen_exp_table("exp_table_battle_threshold"),
    "exp_table_dance": gen_exp_table("exp_table_dance"),
    "exp_table_support_decline": gen_exp_table("exp_table_support_decline"),
    "exp_table_rod_decline": gen_exp_table("exp_table_rod_decline"),
    "exp_table_rod_high_decline": gen_exp_table("exp_table_rod_high_decline"),
    "unit_exp_level": gen_exp_level,
    "unit_exp_damage": gen_exp_two("unit_exp_damage"),
    "unit_dual_exp_damage": gen_exp_two("unit_dual_exp_damage"),
    "unit_exp_destroy": gen_exp_two("unit_exp_destroy", with_bool=True),
    "unit_exp_dance": gen_exp_two("unit_exp_dance"),
    "unit_exp_rod": gen_exp_rod,
    "unit_exp_normalize": gen_exp_normalize,
    "unit_level_limit": gen_level_limit,
    "job_level_limit": gen_job_limit,
    "situation_can_gain_exp": gen_can_gain_exp,
    "growth_random": gen_rng,
    "growth_level_up_plan": gen_plan,
    "unit_level_up_preview": gen_preview,
}


# ------------------------------------------------------------------ sharper cases (round 11, F-025)
# Planted bugs (H6 survivors) that no case above reached; docs/harness/H6_SURVIVORS.md. make_cases runs SHARP
# from its own random stream (n // 3 cases each), so the cases of FUNCS stay exactly as they were.

def gen_dance_sharp(rng):
    """dancing in modes 2 and 3 with every experience-table byte 9 .. 12: the dance amount sits right at its
    cap of 10, so a cap of 11 (or a cap test of >= for >) shows"""
    st, u, o = two_units(rng)
    for i, (off, stride) in enumerate(EXP_SUB):
        row0 = EXPROW + i * 0x400
        for j in range(4 * stride):
            st.put(row0 + j, 1, rng.choice([9, 10, 11, 11, 11, 12]))
    return (st,) + ov("unit_exp_dance", [u, rng.choice([2, 3]), o])


SHARP = [
    ("unit_exp_dance", gen_dance_sharp),
]


# ------------------------------------------------------------------ the ARM side
class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX to a callee of ARITY (stubbed or run as ARM code)
    with its argument registers, and counting the GetValue(int) calls."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.listed: list[str] = []
        self.below_calls = 0
        self.grow_calls = 0

    def call(self, target: int, ret: int) -> bool:
        if target in ARITY:
            self.listed.append(call_text(target, self.r[:ARITY[target]]))
        if target == RANDOM_BELOW:
            self.below_calls += 1
        if target == GET_GROW:
            self.grow_calls += 1
        return super().call(target, ret)


def call_text(target: int, regs) -> str:
    return f"{target:x}" + "".join(f":{r & 0xFFFFFFFF:x}" for r in regs)


def calls_field(listed: list[str]) -> str:
    return ",".join(listed) if listed else "-"


def arm_run(text: bytes, st, kind: str, args: list[int], how: tuple) -> list:
    """Expected outputs, in the order the C driver prints them: [gave_up, values...]."""
    mem = A.Memory(text)
    for a, d in st.regions():
        mem.map(a, d)

    def answer(f, n):
        return lambda cpu, a: st.oracle.get((f,) + tuple(x & 0xFFFFFFFF for x in a[:n]), 0)
    stubs = {f: answer(f, n) for f, n in LEAF_STUBS.items()}
    if how[0] == "levelup":
        stubs.update({f: answer(f, n) for f, n in LEVELUP_STUBS.items()})

        def cap(cpu, a):
            u, s = a[0], a[1]
            return st.oracle.get((GET_CAP, u, s), 0) + A.sx(cpu.mem.read(u + 0xC8 + s, 1), 8)
        stubs[GET_CAP] = cap
    cpu = ListingCpu(mem, stubs, guard=GUARD)
    cpu.r[13], cpu.r[14] = SP, A.RETURN_SENTINEL
    for i in range(4):
        cpu.r[i] = args[i] & 0xFFFFFFFF
    try:
        if how[0] == "call":
            cpu.run(how[1])
            return [0, cpu.r[0], mem.faults, calls_field(cpu.listed)]
        if how[0] == "rng":
            seed, n = args[0], args[1]
            cpu.r[0], cpu.r[1] = RNG_OBJ, seed
            cpu.run(RANDOM_INIT)
            out = []
            for i in range(8):
                cpu.r[13], cpu.r[14] = SP, A.RETURN_SENTINEL
                cpu.r[0], cpu.r[1] = RNG_OBJ, n
                cpu.run(RANDOM_NEXT if i % 2 == 0 else RANDOM_BELOW)
                out.append(cpu.r[0])
            return [0] + out
        if how[0] == "levelup":
            u = args[0]
            before = [mem.read(u + 0xC8 + s, 1) for s in range(8)]
            cpu.r[0] = u
            cpu.run(LEVEL_UP)
            if kind == "plan":
                pts = [(mem.read(u + 0xC8 + s, 1) - before[s]) & 0xFF for s in range(8)]
                return [0, mem.read(u + 0xC0, 4)] + pts + [cpu.below_calls, cpu.grow_calls // 8]
            return ([0, mem.read(u + 0xC0, 4), mem.read(u + 0xF1, 1)] + [mem.read(u + 0xC8 + s, 1) for s in range(8)]
                    + [mem.read(u + 0xE0 + s, 1) for s in range(8)] + [calls_field(cpu.listed)])
    except A.ColdGuard:
        return [1]
    raise ValueError(how)


# ------------------------------------------------------------------ the C side
DRIVER = r'''
/* Generated by src/readable/unit/tests/growth_diff.py: runs readable growth / experience
   functions on memory images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "growth.h"

static uint8_t **pages, **nopages;
static uint32_t used[16384]; static int nused;
static uint8_t *at(uint32_t a, int make) {
    uint8_t *p = pages[a >> 12];
    if (!p && make && nused < 16384) { p = pages[a >> 12] = calloc(4096, 1); used[nused++] = a >> 12; }
    return p ? p + (a & 0xFFF) : NULL;
}
static int faults;
static uint8_t r8(Context *c, uint32_t a) { (void)c; uint8_t *p = at(a, 0); if (!p) faults++; return p ? *p : 0; }
static uint16_t r16(Context *c, uint32_t a) { return (uint16_t)(r8(c, a) | r8(c, a + 1) << 8); }
static uint32_t r32(Context *c, uint32_t a) { return (uint32_t)r16(c, a) | (uint32_t)r16(c, a + 2) << 16; }
static int writes;
static void w8(Context *c, uint32_t a, uint8_t v) { (void)c; writes++; uint8_t *p = at(a, 0); if (p) *p = v; }
static void w16(Context *c, uint32_t a, uint16_t v) { w8(c, a, (uint8_t)v); w8(c, a + 1, (uint8_t)(v >> 8)); }
static void w32(Context *c, uint32_t a, uint32_t v) { w16(c, a, (uint16_t)v); w16(c, a + 2, (uint16_t)(v >> 16)); }
static void interp(Context *c, uint32_t a, uint32_t o) { (void)c; (void)a; (void)o; }
static void svc(Context *c, uint32_t n) { (void)c; (void)n; }

/* the call list: every guest call, with the argument registers of its callee */
#define MAXA 64
static uint32_t ar_f[MAXA], ar_n[MAXA]; static int narity;
static char calls[1 << 16]; static size_t ncalls;
static void list_call(uint32_t f, const uint32_t *r) {
    uint32_t n = 4;
    for (int i = 0; i < narity; i++) if (ar_f[i] == f) n = ar_n[i];
    char buf[96]; int k = snprintf(buf, sizeof buf, "%s%x", ncalls ? "," : "", f);
    for (uint32_t i = 0; i < n; i++) k += snprintf(buf + k, sizeof buf - (size_t)k, ":%x", r[i]);
    if (ncalls + (size_t)k + 1 < sizeof calls) { memcpy(calls + ncalls, buf, (size_t)k + 1); ncalls += (size_t)k; }
}

#define MAXO 4096
static uint32_t stub_n[16], stub_f[16]; static int nstubs;
static uint32_t o_key[MAXO][5], o_val[MAXO]; static int noracle;
static uint32_t oracle_get(uint32_t f, uint32_t n, const uint32_t *k) {
    for (int i = 0; i < noracle; i++) {
        if (o_key[i][0] != f) continue;
        int ok = 1;
        for (uint32_t j = 0; j < n; j++) if (o_key[i][1 + j] != k[j]) ok = 0;
        if (ok) return o_val[i];
    }
    return 0;
}
static void oracle(Context *ctx) {
    uint32_t f = ctx->r[15], n = 0;
    for (int i = 0; i < nstubs; i++) if (stub_f[i] == f) n = stub_n[i];
    ctx->r[0] = oracle_get(f, n, ctx->r);
    ctx->r[15] = ctx->r[14];
}

@OVERRIDE_DECLS@

/* give-ups by nesting depth: an override reached by a guest call that gives up inside while the
   outer readable function goes on is a finding (in the capture library the inner original runs:
   a fault-count surplus in tier 2, the unit_dual_exp_damage finding of 2026-11-12) */
static int depth, nested;

/* every guest call comes here: listed, then answered by the table or run by its override */
static void listed(Context *ctx) {
    uint32_t f = ctx->r[15];
    list_call(f, ctx->r);
    for (int i = 0; i < nstubs; i++) if (stub_f[i] == f) { oracle(ctx); return; }
    for (unsigned i = 0; i < sizeof ovs / sizeof ovs[0]; i++)
        if (ovs[i].a == f) { depth++; ovs[i].f(ctx); depth--; return; }
}
static Code lookup(Context *c, uint32_t a) {
    (void)c;
    for (int i = 0; i < nstubs; i++) if (stub_f[i] == a) return listed;
    for (unsigned i = 0; i < sizeof ovs / sizeof ovs[0]; i++) if (ovs[i].a == a) return listed;
    return NULL;
}
static int originals;
void fe_stub_original(Context *ctx) {
    if (depth > 0) nested++;
    originals++; ctx->r[0] = 0xDEADBEEFu; ctx->r[15] = ctx->r[14] & ~3u;
}

/* the level-up's capability callback: a base from the table + the gains byte by then */
static int32_t capability(Context *ctx, void *env, gaddr unit, uint32_t stat, int8_t gains_now) {
    (void)ctx; (void)env;
    uint32_t r[4] = {unit, stat, 0, 0};
    list_call(0x0052F7A0u, r);
    return (int32_t)oracle_get(0x0052F7A0u, 2, r) + gains_now;
}

static const Host host = {r8, r16, r32, w8, w16, w32, interp, lookup, svc};
static uint32_t vfp[32], fpscr;
static Context fresh(void) {
    Context c; memset(&c, 0, sizeof c);
    c.read_pages = nopages; c.write_pages = nopages; c.vfp = vfp; c.fpscr = &fpscr; c.host = &host;
    c.r[14] = 0x00123450u; c.budget = 1000;
    return c;
}

static int hexval(int ch) { return ch <= '9' ? ch - '0' : (ch | 32) - 'a' + 10; }

int main(void) {
    pages = calloc(1u << 20, sizeof *pages);
    nopages = calloc(1u << 20, sizeof *nopages);
    fe_force_mode(FE_MODE_READABLE);
    static char line[1 << 16];
    char kind[64]; unsigned id = 0; uint32_t a[5] = {0};
    while (fgets(line, sizeof line, stdin)) {
        if (!strncmp(line, "arity ", 6)) {
            sscanf(line + 6, "%x %u", &ar_f[narity], &ar_n[narity]); narity++;
        } else if (!strncmp(line, "stub ", 5)) {
            sscanf(line + 5, "%x %u", &stub_f[nstubs], &stub_n[nstubs]); nstubs++;
        } else if (!strncmp(line, "case ", 5)) {
            sscanf(line + 5, "%u %63s %x %x %x %x %x", &id, kind, &a[0], &a[1], &a[2], &a[3], &a[4]);
            for (int i = 0; i < nused; i++) { free(pages[used[i]]); pages[used[i]] = NULL; } nused = 0;
            noracle = 0; nstubs = 0; originals = 0; writes = 0; faults = 0; ncalls = 0; calls[0] = 0;
            depth = 0; nested = 0;
        } else if (!strncmp(line, "mem ", 4)) {
            uint32_t addr; int off = 0;
            sscanf(line + 4, "%x %n", &addr, &off);
            const char *h = line + 4 + off;
            for (uint32_t i = 0; h[2 * i] && h[2 * i] != '\n' && h[2 * i] != '\r'; i++)
                *at(addr + i, 1) = (uint8_t)(hexval(h[2 * i]) << 4 | hexval(h[2 * i + 1]));
        } else if (!strncmp(line, "oracle ", 7)) {
            uint32_t *k = o_key[noracle];
            sscanf(line + 7, "%x %x %x %x %x %x", &k[0], &k[1], &k[2], &k[3], &k[4], &o_val[noracle]);
            if (noracle < MAXO - 1) noracle++; else { fprintf(stderr, "oracle table full\n"); return 3; }
        } else if (!strncmp(line, "run", 3)) {
            Context c = fresh();
            c.r[13] = a[4];
            const char *cl = ncalls ? calls : "-";
            if (!strncmp(kind, "ov:", 3)) {
                uint32_t addr = (uint32_t)strtoul(kind + 3, NULL, 16);
                for (int i = 0; i < 4; i++) c.r[i] = a[i];
                int found = 0;
                for (unsigned i = 0; i < sizeof ovs / sizeof ovs[0]; i++) if (ovs[i].a == addr) { ovs[i].f(&c); found = 1; }
                cl = ncalls ? calls : "-";
                if (!found) printf("%u NO-OVERRIDE\n", id);
                else if (originals) printf("%u 1 %d\n", id, faults);
                else printf("%u 0 %u %d %s\n", id, c.r[0], faults, cl);
            } else if (!strcmp(kind, "rng")) {
                GrowthRandom r; growth_random_seed(NULL, &r, a[0]);
                printf("%u 0", id);
                for (int i = 0; i < 8; i++)
                    printf(" %u", i % 2 == 0 ? growth_random_next(NULL, &r) : (uint32_t)growth_random_below(NULL, &r, (int32_t)a[1]));
                printf("\n");
            } else if (!strcmp(kind, "plan")) {
                int32_t rates[8]; GrowthPlan p;
                for (int s = 0; s < 8; s++) rates[s] = (int32_t)r32(&c, a[1] + 4u * (uint32_t)s);
                growth_level_up_plan(NULL, (uint32_t)r32(&c, a[0] + 0xC0u), rates, &p);
                printf("%u 0 %u", id, p.next_seed);
                for (int s = 0; s < 8; s++) {
                    uint32_t sum = 0;
                    for (int k = 0; k < GROW_PASSES; k++) sum += (uint32_t)p.points[k][s];
                    printf(" %u", sum & 0xFFu);
                }
                printf(" %d %d\n", p.draws, p.passes);
            } else if (!strcmp(kind, "preview")) {
                GrowthLevelUp o;
                int ok = unit_level_up_preview(&c, a[0], capability, NULL, &o);
                cl = ncalls ? calls : "-";
                if (!ok || originals) printf("%u 1\n", id);
                else {
                    printf("%u 0 %u %u", id, o.growth_seed, o.level);
                    for (int s = 0; s < 8; s++) printf(" %u", (uint8_t)o.gains[s]);
                    for (int s = 0; s < 8; s++) printf(" %u", (uint8_t)o.stat_loss[s]);
                    printf(" %s\n", cl);
                }
            }
            if (writes) printf("%u WROTE-GUEST %d\n", id, writes);
            if (nested) printf("%u NESTED-GIVEUP %d\n", id, nested);
        }
    }
    return 0;
}
'''

DRIVER_OVERRIDES = sorted(set(OVERRIDES.values()) | {EQUIPPED})


def driver_text() -> str:
    decls = "".join(f"void override_0x{a:08X}(Context *);\n" for a in DRIVER_OVERRIDES)
    table = "static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n" + "".join(
        f"    {{0x{a:08X}u, override_0x{a:08X}}},\n" for a in DRIVER_OVERRIDES) + "};\n"
    return DRIVER.replace("@OVERRIDE_DECLS@", decls + table)


def find_cc() -> str | None:
    import check  # tools/readable/check.py: the same compiler search
    return check.find_cc()


def build_driver(cc: str, out: str, unit_dir: str) -> str:
    """Builds the driver with every source of src/readable/, the unit folder's taken from unit_dir."""
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "growth_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    sources = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_UNIT)):
            continue
        sources += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    sources += [os.path.join(unit_dir, f) for f in os.listdir(unit_dir) if f.endswith(".c")]
    exe = os.path.join(out, "growth_driver.exe" if os.name == "nt" else "growth_driver")
    inc = ["-I", unit_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
           "-I", os.path.join(ROOT, "include", "readable"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    cmd = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1", "-fwrapv"] + inc + [src] + sorted(sources) + ["-o", exe]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"growth_diff: building the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


def make_cases(text: bytes, n: int, seed: int, only: str | None):
    rng = random.Random(seed)
    lines = [f"arity {f:x} {k}" for f, k in ARITY.items()]
    expected: dict[int, tuple[str, list, tuple]] = {}
    unsupported: dict[str, int] = {}
    cid = 0
    # round 11 (F-025): SHARP's cases come from their own random stream, so the cases of FUNCS stay as they were
    sharp_rng = random.Random(seed ^ 0x5EED11)
    jobs = [(name, gen, n, rng) for name, gen in FUNCS.items()] +         [(name, gen, max(1, n // 3), sharp_rng) for name, gen in SHARP]
    for name, gen, count, gen_rng in jobs:
        if only and name != only:
            continue
        for _ in range(count):
            st, kind, args, how = gen(gen_rng)
            try:
                exp = arm_run(text, st, kind, args, how)
            except A.Unsupported as e:
                unsupported[name] = unsupported.get(name, 0) + 1
                if unsupported[name] == 1:
                    print(f"  ARM interpreter: {name}: {e}")
                continue
            expected[cid] = (name, exp, (kind, args))
            lines.append(f"case {cid} {kind} " + " ".join(f"{x & 0xFFFFFFFF:x}" for x in args) + f" {SP:x}")
            stubs = dict(LEAF_STUBS)
            if how[0] == "levelup":
                stubs.update(LEVELUP_STUBS)
            lines += [f"stub {f:x} {k}" for f, k in stubs.items()]
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


def compare(exe: str, cc: str, lines: list[str], expected: dict, show: int, quiet: bool = False):
    log = os.path.join(os.path.dirname(exe), "fe_readable.log")
    env = dict(os.environ, FE_READABLE_LOG=log, PATH=os.path.dirname(cc) + os.pathsep + os.environ.get("PATH", ""))
    r = subprocess.run([exe], input="\n".join(lines) + "\n", capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"growth_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
    got: dict[int, list] = {}
    wrote: set[int] = set()
    for ln in r.stdout.split("\n"):
        parts = ln.split()
        if len(parts) >= 2 and parts[1] in ("WROTE-GUEST", "NO-OVERRIDE", "NESTED-GIVEUP"):
            wrote.add(int(parts[0]))
        elif parts:
            got[int(parts[0])] = [parse(x) for x in parts[1:]]
    per: dict[str, list[int]] = {}
    for c, (name, exp, inputs) in expected.items():
        res = per.setdefault(name, [0, 0, 0, 0])  # cases, mismatches, gave-up cases, early give-ups
        res[0] += 1
        g = got.get(c)
        ov = inputs[0].startswith("ov:")
        if exp[0] == 1:
            res[2] += 1
            exp = [1, 0] if ov else exp  # a give-up must come before any unmapped read
        elif ov and g is not None and g[:1] == [1] and g[1:] == [0] and c not in wrote:
            # an early give-up: a needed cache is cold, the readable code asks before reading
            # anything (the original would reach that cache later or not at all); always safe
            res[3] += 1
            continue
        if g is None or g != exp or c in wrote:
            res[1] += 1
            if res[1] <= show and not quiet:
                why = " (wrote guest memory, no override, or a nested override gave up)" if c in wrote else ""
                print(f"  MISMATCH {name} case {c}: original {exp}, readable {g}{why}; {inputs[0]} "
                      + " ".join(f"{x & 0xFFFFFFFF:#x}" for x in inputs[1]))
    return per


# planted bugs: (file, exact text, replacement); each text occurs once in its file
PLANTS = [
    # growth rates
    ("growth_rates.c", "rate = fe_add32(rate, 10);", "rate = fe_add32(rate, 5);"),
    ("growth_rates.c", "int player = READ_FIELD(ctx, PersonData, person, unit_kind) == 1;",
     "int player = READ_FIELD(ctx, PersonData, person, unit_kind) != 0;"),
    ("growth_rates.c", "    return v / 2;", "    return v >> 1;"),
    ("growth_rates.c", "return rate < 0 ? 0 : rate;", "return rate;"),
    ("growth_rates.c", "family + (female ? 0u : (gaddr)sizeof(FamilyParent))", "family + (female ? (gaddr)sizeof(FamilyParent) : 0u)"),
    # the child path asks Person::Get once instead of twice: same result, fewer callee calls (F-018)
    ("growth_rates.c", "    if (family_index == 0 || guest_call1(ctx, GROW_PersonGet, family_index) == 0)\n        return 0;\n"
                       "    uint32_t again = READ_FIELD(ctx, PersonData, person, family_index);\n"
                       "    gaddr fixed = again != 0 ? guest_call1(ctx, GROW_PersonGet, again) : 0;\n",
     "    gaddr fixed = family_index != 0 ? guest_call1(ctx, GROW_PersonGet, family_index) : 0;\n"
     "    if (fixed == 0)\n        return 0;\n"),
    ("growth_rates.c", "boon_growth) + stat),\n                    guest_s8(ctx, FIELD_ADDR(PersonalityData, bane, bane_growth)",
     "boon_growth) + stat),\n                    guest_s8(ctx, FIELD_ADDR(PersonalityData, bane, boon_growth)"),
    ("growth_rates.c", "    return stat != 0 ? fe_add32(v, 1) : v;", "    return fe_add32(v, 1);"),
    ("growth_rates.c", "    return cap > 99 ? 99 : cap;", "    return cap > 98 ? 98 : cap;"),
    # Edit::GetLimit done in C instead of through the guest: same numbers, a missing callee call
    ("growth_rates.c", "cap = fe_add32(cap, (int32_t)guest_call2(ctx, GROW_EditGetLimit, edit, stat));",
     "cap = fe_add32(cap, edit_limit(ctx, edit, stat));"),
    # experience
    ("growth_exp.c", "level = fe_add32(level, 6);", "level = fe_add32(level, 5);"),
    ("growth_exp.c", "    return clamp(level, 1, 40);", "    return clamp(level, 0, 40);"),
    ("growth_exp.c", "return clamp(b >= a ? a : b, 1, 38);", "return clamp(b >= a ? b : a, 1, 38);"),
    ("growth_exp.c", "clamp(fe_add32(fe_add32(theirs, -mine), 10), 0, 33));\n    gaddr floor_row = guest_call1(ctx, GROW_ExpGetBattleThreshold, difficulty(ctx));\n    int32_t floor = guest_s8(ctx, floor_row + (gaddr)",
     "clamp(fe_add32(fe_add32(theirs, -mine), 10), 0, 34));\n    gaddr floor_row = guest_call1(ctx, GROW_ExpGetBattleThreshold, difficulty(ctx));\n    int32_t floor = guest_s8(ctx, floor_row + (gaddr)"),
    ("growth_exp.c", "    if ((uint32_t)difficulty(ctx) >= 2) {", "    if ((uint32_t)difficulty(ctx) >= 3) {"),
    ("growth_exp.c", "v = base < 20 ? fe_add32(base, fe_asr(base, 1)) : fe_add32(base, 10);",
     "v = base < 20 ? fe_add32(base, fe_asr(base, 2)) : fe_add32(base, 10);"),
    ("growth_exp.c", "        v = fe_add32(v, base < 20 ? base : 20);", "        v = fe_add32(v, v < 20 ? v : 20);"),
    ("growth_exp.c", "    if (boss != 0)", "    if ((boss & 0xFFu) != 0)"),
    ("growth_exp.c", "    if ((mode == 2 || mode == GROW_EXP_MODE_HALF) && dance > 10)", "    if (dance > 10)"),
    ("growth_exp.c", "        if (kind == 6)  /* staff */", "        if (kind == 7)  /* staff */"),
    ("growth_exp.c", "    return v >= 2 ? fe_asr(v, 1) : v;", "    return v >= 1 ? fe_asr(v, 1) : v;"),
    ("growth_exp.c", "    if (limit > 20 || guest_call1", "    if (limit >= 20 || guest_call1"),
    ("growth_exp.c", "        if (limit <= fe_add32(READ_FIELD(ctx, Unit, unit, level), 1)) {",
     "        if (limit <= READ_FIELD(ctx, Unit, unit, level)) {"),
    ("growth_exp.c", "        return 101;", "        return 100;"),
    ("growth_exp.c", "    if (force >= 3)", "    if (force > 3)"),
    # the job word read once in the staff loop: same numbers, fewer unmapped reads (tier 2 counts them)
    ("growth_exp.c", "    for (uint32_t kind = 0; kind < 8; kind++) {\n        if (kind == 6)  /* staff */\n            continue;\n        gaddr job = READ_FIELD(ctx, Unit, unit, job);",
     "    gaddr job = READ_FIELD(ctx, Unit, unit, job);\n    for (uint32_t kind = 0; kind < 8; kind++) {\n        if (kind == 6)  /* staff */\n            continue;"),
    # review 4: unit_dual_exp_damage without "ask for the level cache first": its guest call of
    # GetExpDamage gives up inside (a nested give-up) while the outer function goes on; tier 2 saw it
    # as a fault-count surplus on 2026-11-12, this test sees it through the driver's nesting count
    ("growth_exp.c", "int32_t unit_dual_exp_damage(Context *ctx, gaddr unit, int32_t mode, gaddr other) {\n"
                     "    if (!fe_static_ready(ctx, S_ExpLevelGuard))  /* the cache GetExpDamage's level calls need: ask first */\n"
                     "        return (int32_t)fe_use_original(ctx);\n",
     "int32_t unit_dual_exp_damage(Context *ctx, gaddr unit, int32_t mode, gaddr other) {\n"),
    # one of GetExpDestroy's five caches not asked: a cold mask read as 0 instead of giving up
    ("growth_exp.c", "!fe_static_ready(ctx, S_DestroyGuard3) ||", ""),
    # the roll
    ("growth_roll.c", "        r->s[i] = GROW_SEED_MULT * (prev ^ (prev >> 30)) + i;", "        r->s[i] = GROW_SEED_MULT * (prev ^ (prev >> 29)) + i;"),
    ("growth_roll.c", "#define GROW_SEED_DISCARD 20", "#define GROW_SEED_DISCARD 19"),
    ("growth_roll.c", "    r->s[3] = (t ^ (t >> 8)) ^ (w ^ (w >> 19));", "    r->s[3] = (t ^ (t >> 8)) ^ (w ^ (w >> 18));"),
    ("growth_roll.c", "    return roll < rate;", "    return roll <= rate;"),
    ("growth_roll.c", "    for (int pass = 0; pass < GROW_PASSES && !rose; pass++) {\n        plan->passes++;",
     "    for (int pass = 0; pass < 1 && !rose; pass++) {\n        plan->passes++;"),
    ("growth_roll.c", "            if (rate <= 0)\n                continue;\n            while (rate >= 100) {\n                rate -= 100;\n                plan->points[pass][s]++;",
     "            if (rate < 0)\n                continue;\n            while (rate >= 100) {\n                rate -= 100;\n                plan->points[pass][s]++;"),
    ("growth_roll.c", "    if (now < cap) {", "    if (now <= cap) {"),
    ("growth_roll.c", "            if ((int32_t)READ_FIELD(ctx, Unit, unit, level_limit_raises) > READ_FIELD(ctx, PersonData, person, level_cap))",
     "            if ((int32_t)READ_FIELD(ctx, Unit, unit, level_limit_raises) >= READ_FIELD(ctx, PersonData, person, level_cap))"),
    ("growth_roll.c", "                added += add_point(ctx, unit, s, capability, env, &gains);\n                out->gains[s] = (int8_t)gains;\n                rose = 1;",
     "                added += add_point(ctx, unit, s, capability, env, &gains);\n                out->gains[s] = (int8_t)gains;"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_UNIT, d, ignore=shutil.ignore_patterns("tests"))
        path = os.path.join(d, fname)
        body = open(path, encoding="utf-8").read()
        if body.count(old) != 1:
            print(f"  planted bug {i}: its text occurs {body.count(old)} times in {fname} (the list is stale)")
            missed += 1
            continue
        body = body.replace(old, new)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        exe = build_driver(cc, os.path.join(OUT, "plant"), d)
        per = compare(exe, cc, lines, expected, 0, quiet=True)
        bad = sum(v[1] for v in per.values())
        hit = [k for k, v in per.items() if v[1]]
        print(f"  planted bug {i:2d} ({fname}: {old.strip()[:48]!r}): "
              + (f"caught, {bad} mismatches in {', '.join(hit[:4])}{' ...' if len(hit) > 4 else ''}"
                 if bad else "NOT CAUGHT"))
        missed += 0 if bad else 1
    return missed


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=300, help="cases per function (default 300)")
    ap.add_argument("--seed", type=int, default=20261112)
    ap.add_argument("--only", help="one function name")
    ap.add_argument("--show", type=int, default=5, help="mismatches to print per function")
    ap.add_argument("--plant", action="store_true", help="also check that planted bugs are caught")
    ap.add_argument("--plant-n", type=int, default=100, help="cases per function for each planted bug")
    a = ap.parse_args(argv)
    if a.only and a.only not in FUNCS:
        print(f"unknown function {a.only}; one of: {', '.join(FUNCS)}")
        return 2
    if not os.path.isfile(TEXT):
        print("growth_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("growth_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_UNIT)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"growth_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed {a.seed}")
    for name, (n, bad, cold, early) in per.items():
        total_bad += bad
        notes = ([f"{cold} cold: both reached / gave up at the cache"] if cold else []) + \
                ([f"{early} early give-ups"] if early else [])
        print(f"  {name:32s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({'; '.join(notes)})" if notes else ""))
    for name, k in unsupported.items():
        print(f"  {name:32s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n, a.seed + 1)
        print(f"growth_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"growth_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
