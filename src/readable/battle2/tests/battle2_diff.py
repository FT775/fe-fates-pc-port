#!/usr/bin/env python3
"""Host differential test of the second battle-numbers batch against the game's own ARM code.

    python src/readable/battle2/tests/battle2_diff.py             all functions, 300 cases each
    python src/readable/battle2/tests/battle2_diff.py -n 1500 --seed 7    the long run
    python src/readable/battle2/tests/battle2_diff.py --only forecast_damage
    python src/readable/battle2/tests/battle2_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/move/tests/move_diff.py (and the ARM interpreter
src/readable/battle/tests/arm_mini.py): for every readable function of src/readable/battle2/ the
test makes up guest states (fight sides with their detail rows, skill bits and terrain, strike
lists, units with their Person, class and force, item records, the avatar's boon and bane, a
rally record, the map rules and the save's mode bits, the one-time caches; all random test values,
never game data, and on purpose often outside the ranges the game uses: unmapped units, records
and terrain, negative and huge numbers, skill numbers that are negative, lists that end early),
runs the ORIGINAL ARM code from the owner's extracted/text.bin in arm_mini.py and the readable C
function (built with the host gcc against tools/readable/stub/) on the same memory, and compares
r0, the number of bytes read from unmapped memory AND the list of guest calls, in order, with their
argument registers (docs/DECISIONS.md F-018). On the ARM side every BL/BLX and every tail branch (B)
to a listed callee is listed; a tail branch to an override would run on as ARM code, unlisted
(3dsrecomp inlines it; move_diff.py, round 10) - none of this batch's functions has one. A one-time
cache that is not filled must make the original reach the guard routine and the readable code give
up before reading anything; a nested give-up (a guest call of another readable function giving up
inside while the outer one goes on) is a mismatch.

Guest functions answered by one table on both sides (listed and compared): unit::Item::ToData,
Item::IsMagic, Unit::IsEquipSkill, Unit::IsItemEnhanceHave, Unit::GetAttack, Unit::GetAvoid,
Force::IsAllied, Unit::GetStrImpl and Unit::GetPowImpl. Unit::GetDefImpl and GetMdefImpl are answered on the ARM side
only: the defense helper gets the same two numbers as arguments (they take a stack argument, so the
readable code cannot call them). Personality::Get and GameUserData::Get run as ARM code on the ARM
side and are done inline by the C side (not listed).

Three functions are not overrides and are run through test-only entries in the generated driver
(never a marker in src/readable/): forecast_damage (GetSimplePower; its registry address is taken,
docs/BATTLE2.md 3), battle_detail_avoid and battle_detail_defense (helpers of two writers). For the
two helpers the ARM function runs whole and the value it STORES is the expected result (the avoid
halfword; for defense the four words, folded into one number); the side record is always mapped,
since the game writes into it.

--plant copies src/readable/battle2/ to build/readable/battle2/plant/, makes one small wrong change at
a time (PLANTS below), rebuilds and reruns: every planted bug must give at least one mismatch.

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
OUT = os.path.join(ROOT, "build", "readable", "battle2")
SRC_B2 = os.path.join(ROOT, "src", "readable", "battle2")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
TO_DATA, IS_MAGIC, IS_EQUIP, ENHANCE_HAVE = 0x003D0EA4, 0x005290B8, 0x0052DD04, 0x0052FB98
GET_ATTACK, GET_AVOID, IS_ALLIED = 0x00534188, 0x00533524, 0x0053C3E0
STR_IMPL, POW_IMPL, DEF_IMPL, MDEF_IMPL = 0x0052A80C, 0x0052A500, 0x0052A000, 0x0052BF6C
LEAF_STUBS = {TO_DATA: 1, IS_MAGIC: 1, IS_EQUIP: 2, ENHANCE_HAVE: 3, GET_ATTACK: 3, GET_AVOID: 2,
              IS_ALLIED: 2, STR_IMPL: 4, POW_IMPL: 4}
ARM_ONLY_STUBS = {DEF_IMPL: 4, MDEF_IMPL: 4}  # answered on the ARM side, not listed
ARITY = dict(LEAF_STUBS)

OVERRIDES = {  # name -> address (the registered overrides)
    "battle_dead_unit": 0x00525FE0, "battle_strike_run": 0x0052603C,
    "unit_item_stat_bonus": 0x0033A790, "edit_stat_bonus": 0x0053ABEC, "enhance_has_rally_bonus": 0x0041B38C,
    "unit_has_rally_stat_skill": 0x00532124, "sound_is_individual_battle": 0x00397FB4,
    "job_is_promoted": 0x00524804, "job_is_giant": 0x005249F8, "situation_is_casual": 0x005281F8,
    "situation_is_phoenix": 0x0052824C, "situation_records_death": 0x00527E80,
    "situation_records_kill": 0x00527EA4,
}
TEST_ENTRIES = {  # name -> address (run through the driver's test-only entries)
    "forecast_damage": 0x005253A8, "battle_detail_avoid": 0x003491F8, "battle_detail_defense": 0x00349CF0,
}
ADDR = dict(OVERRIDES, **TEST_ENTRIES)

# globals and caches (src/readable/battle2/battle2.h)
G_GUD, G_PERS = 0x006DA248, 0x006D3B98
SP_GUARDS = (0x006D69EC, 0x006D69E8, 0x006D69E4, 0x006D69E0, 0x006D69DC, 0x006D69D8, 0x006D69D4, 0x006D69D0,
             0x006D69CC)
SP_SKILLS = dict(astra=0x006D6934, fang=0x006D6936, luna=0x006D6938, ignis=0x006D693A, rend=0x006D693C,
                 venge=0x006D693E, scale=0x006D6940, aegis=0x006D6942)
SP_PIERCE = 0x006D6AD8
DA_GUARD, DA_SKILL, DD_GUARD, DD_SKILL = 0x006D69C4, 0x006D6930, 0x006D69BC, 0x006D692E
RALLY_GUARDS = tuple(0x006D9974 - 4 * i for i in range(9))
RALLY_SKILLS = tuple(0x006D96AE + 2 * i for i in range(9))
SOUND_STATE = 0x006D7F38
EXP_GUARDS = (0x006D97B4, 0x006D97B0, 0x006D97AC)
STAT_GUARDS = (0x006D9740, 0x006D973C, 0x006D9738, 0x006D9734, 0x006D974C, 0x006D9748, 0x006D9744)
HIGH_GUARD, HIGH_MASK, GIANT_GUARD, GIANT_MASK = 0x006D39B0, 0x006D3A10, 0x006D39B4, 0x006D3A18
ALL_GUARDS = SP_GUARDS + (DA_GUARD, DD_GUARD) + RALLY_GUARDS + \
    EXP_GUARDS + STAT_GUARDS + (HIGH_GUARD, GIANT_GUARD)
U64_MASKS = (SP_PIERCE, HIGH_MASK, GIANT_MASK)
SKILL_CACHES = tuple(SP_SKILLS.values()) + (DA_SKILL, DD_SKILL) + RALLY_SKILLS

# guest layout of the made-up state
UNIT = lambda k: 0x08000000 + k * 0x140  # noqa: E731
PERSON = lambda k: 0x08010000 + k * 0x100  # noqa: E731
JOB = lambda k: 0x08020000 + k * 0x100  # noqa: E731
FORCE = lambda k: 0x08030000 + k * 12  # noqa: E731
ITEMDATA = lambda k: 0x08040000 + k * 0x80  # noqa: E731
INFO = 0x08100000                        # BattleInfo: four sides of 0x200
SIDE = lambda k: INFO + k * 0x200  # noqa: E731
CALC = 0x08110000
SCENE = lambda k: 0x08120000 + k * 0x10  # noqa: E731
TILE = lambda k: 0x08200000 + k * 0x28  # noqa: E731
PERS = 0x08300000                        # Personality records, 0x40 each
GUD = 0x08310000
SIT = 0x08320000
EDIT = 0x08340000
ENH = 0x08350000
NUNITS, NJOBS, NITEMS, NTILES, NPERS = 6, 6, 8, 6, 8
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]
SKILL_IDS = list(range(1, 40))


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def sx(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def word(st, addr: int, n: int = 4) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(n)), "little")


def guard(st, addr: int, cold_p: float = 0.01) -> None:
    st.put(addr, 4, 0 if st.rng.random() < cold_p else st.rng.choice([1, 0x101, 0xFFFFFFFF]))


def cool(st, guards, p: float = 0.03) -> None:
    for g in guards:
        if st.rng.random() < p:
            st.put(g, 4, 0)


def base_state(rng) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    for g in ALL_GUARDS:
        guard(st, g)
    for a in U64_MASKS:
        st.put(a, 8, 1 << rng.randrange(64) if rng.random() > 0.05 else rng.randrange(1 << 64))
    for a in SKILL_CACHES:
        st.put(a, 2, pick(rng, SKILL_IDS, [0, -1, -9, 0x7FFF, -0x8000], 0.08) & 0xFFFF)
    st.put(G_PERS, 4, PERS if rng.random() > 0.03 else rng.choice(UNMAPPED))
    st.fill(PERS, NPERS * 0x40)
    st.put(G_GUD, 4, GUD if rng.random() > 0.03 else rng.choice(UNMAPPED))
    st.fill(GUD, 0x40)
    st.fill(SIT, 0x20)
    for k in range(NJOBS):
        st.fill(JOB(k), 0x80)
    for k in range(NITEMS):
        st.fill(ITEMDATA(k), 0x68)
    for k in range(NTILES):
        st.fill(TILE(k), 0x28)
        attr = rng.randrange(1 << 32) if rng.random() < 0.3 else 0
        for bit, p in ((0x100, 0.4), (0x80000, 0.3), (0x100000, 0.3), (0x200000, 0.3), (0x400000, 0.3)):
            attr = (attr | bit) if rng.random() < p else (attr & ~bit)
        st.put(TILE(k) + 0x18, 4, attr)
        for f in (0x11, 0x12):
            st.put(TILE(k) + f, 1, pick(rng, [0, 0, 5, 10, 20, 30, -5, -10, -20], [127, -128, 100, -100], 0.15) & 0xFF)
    for k in range(10):
        st.fill(FORCE(k), 12)
    for k in range(NUNITS):
        u = UNIT(k)
        st.fill(u, 0x140)
        st.fill(PERSON(k), 0x10)
        st.put(u + 0x9C, 4, PERSON(k) if rng.random() > 0.03 else rng.choice(UNMAPPED))
        st.put(u + 0xA0, 4, JOB(rng.randrange(NJOBS)) if rng.random() > 0.03 else rng.choice(UNMAPPED))
        st.put(u + 0xA4, 4, FORCE(rng.randrange(10)) if rng.random() > 0.05 else rng.choice(UNMAPPED))
    return st


def unit_arg(st, unmapped_p: float = 0.06) -> int:
    return st.rng.choice(UNMAPPED) if st.rng.random() < unmapped_p else UNIT(st.rng.randrange(NUNITS))


def answer_unit(st, u: int) -> None:
    """what the table-answered guest calls give for this unit (also for an unmapped one)"""
    rng = st.rng
    for a in SKILL_CACHES:
        st.oracle[(IS_EQUIP, s32(u), s32(sx(word(st, a, 2), 16)))] = int(rng.random() < 0.3)
    for slot in range(5):
        item = s32(u + 0x108 + 4 * slot)
        st.oracle[(TO_DATA, item)] = ITEMDATA(rng.randrange(NITEMS)) if rng.random() > 0.05 else rng.choice(UNMAPPED)
        st.oracle[(ENHANCE_HAVE, s32(u), item, 0)] = int(rng.random() < 0.5)
    for f in list(range(10)) + [10, 11]:
        for t in (0, 1):
            st.oracle[(IS_ALLIED, s32(FORCE(f)), t)] = int(rng.random() < 0.5)
    for a in UNMAPPED:
        for t in (0, 1):
            st.oracle[(IS_ALLIED, a, t)] = int(rng.random() < 0.5)


def ov(name, args, post=None):
    a = ADDR[name]
    return f"ov:0x{a:08X}", [s32(x) for x in args] + [0] * (4 - len(args)), ("call", a, post)


def odd_int(rng) -> int:
    return pick(rng, list(range(-30, 60)), [0x7FFFFFFF, -0x80000000, 1000, -1000, 0x10000, -0x10000], 0.15)


# ------------------------------------------------------------------ fight sides
def make_sides(st) -> None:
    """four BattleSide records: random bytes, then the fields the readers use set to useful values"""
    rng = st.rng
    st.fill(INFO, 0x810)
    for k in range(4):
        s = SIDE(k)
        st.put(s, 1, pick(rng, [0, 1, 2, 3], [4, 255]))
        u = unit_arg(st, 0.08) if rng.random() > 0.06 else 0
        st.put(s + 4, 4, u)
        answer_unit(st, u)
        st.put(s + 0x10, 2, 0 if rng.random() < 0.08 else rng.randrange(1, 1 << 16))
        st.put(s + 0x14, 4, s32(pick(rng, [0, 1, -1, 2, -2], [0x7FFFFFFF, -0x80000000])))
        st.put(s + 0x20, 4, 0 if rng.random() < 0.25 else TILE(rng.randrange(NTILES)) if rng.random() > 0.08
               else rng.choice(UNMAPPED))
        flags = rng.randrange(1 << 32) if rng.random() < 0.2 else 0
        for bit, p in ((0x2, 0.3), (0x10, 0.2), (0x20, 0.4), (0x40, 0.1)):
            flags = (flags | bit) if rng.random() < p else (flags & ~bit)
        st.put(s + 0x28, 4, flags)
        for row in range(2):
            d = s + 0x48 + row * 0x24
            for f in (0, 4, 8, 0xC, 0x10):
                st.put(d + f, 4, s32(odd_int(rng)))
        for off in (0x12C, 0x130, 0x134, 0x1C0, 0x1C4, 0x1C8, 0x1E8, 0x1FC):
            st.put(s + off, 4, s32(pick(rng, [0, 0, 1, 2, 3, -1, -2, 5], [0x7FFFFFFF, -0x80000000, 300], 0.05)))
        for off in (0x13C, 0x1D0, 0xB0, 0x1F0):
            st.put(s + off, 2, pick(rng, [0, 0, 5, 10, 15, 0xFFFB, 0xFFF6], [0x7FFF, 0x8000, 0xFFFF], 0.1))
        for row in range(2):  # the skill bits: sparse, and often the cached skills' bits
            bits = s + 0xE6 + row * 0x94
            for i in range(0x40):
                st.mem[bits + i] = 0 if rng.random() < 0.85 else rng.randrange(256)
            for a in (SP_SKILLS["scale"], SP_SKILLS["aegis"]):
                if rng.random() < 0.35:
                    b = sx(word(st, a, 2), 16)
                    addr = bits + (b >> 3)
                    st.mem[addr] = st.mem.get(addr, 0) | (1 << (b & 7))


# ------------------------------------------------------------------ the functions
# Each generator returns (state, kind, args, how the ARM side runs).

def gen_dead_unit(rng):
    st = base_state(rng)
    make_sides(st)
    st.put(CALC, 4, INFO if rng.random() > 0.05 else rng.choice(UNMAPPED))
    n = rng.choice([0, 1, 2, 3, 5, 8])
    for i in range(n + 1):
        st.fill(SCENE(i), 0x10)
        st.put(SCENE(i) + 4, 1, pick(rng, [0, 1, 2, 3], [4, 7, 255]))
        st.put(SCENE(i) + 5, 1, pick(rng, [0, 2, 3, 5, 6, 7, 7, 1, 4, 8, 9], [10, 255]))
        nxt = SCENE(i + 1) if i < n else 0
        if rng.random() < 0.04:
            nxt = rng.choice(UNMAPPED)
        st.put(SCENE(i), 4, nxt)
    head = SCENE(0) if rng.random() > 0.08 else rng.choice([0, rng.choice(UNMAPPED)])
    return (st,) + ov("battle_dead_unit", [CALC, head])


def gen_strike_run(rng):
    st = base_state(rng)
    n = rng.choice([0, 1, 2, 3, 5, 8])
    side = rng.randrange(4)
    for i in range(n + 1):
        st.fill(SCENE(i), 0x10)
        st.put(SCENE(i) + 4, 1, side if rng.random() < 0.8 else pick(rng, [0, 1, 2, 3], [255]))
        st.put(SCENE(i) + 5, 1, pick(rng, [1, 1, 1, 2, 7, 8], [0, 255]))
        nxt = SCENE(i + 1) if i < n else 0
        if rng.random() < 0.04:
            nxt = rng.choice(UNMAPPED)
        st.put(SCENE(i), 4, nxt)
    head = SCENE(0) if rng.random() > 0.08 else rng.choice([0, rng.choice(UNMAPPED)])
    return (st,) + ov("battle_strike_run", [rng.randrange(1 << 32), head])


def gen_forecast(rng):
    st = base_state(rng)
    cool(st, SP_GUARDS + STAT_GUARDS + EXP_GUARDS, 0.01)
    make_sides(st)
    a, b = rng.sample(range(4), 2)
    side = SIDE(a)
    other = SIDE(b) if rng.random() > 0.05 else rng.choice(UNMAPPED)
    names = ["astra", "fang", "luna", "venge", "astra", "fang", "luna", "venge", "ignis", "rend"]
    skill = 0 if rng.random() < 0.3 else sx(word(st, SP_SKILLS[rng.choice(names)], 2), 16)
    if rng.random() < 0.05:
        skill = rng.choice([-1, 0x7FFFFFFF, 1000])
    u = word(st, side + 4)
    item = s32(side + 0x10)
    st.oracle[(GET_ATTACK, u, item, 1)] = s32(odd_int(rng))
    st.oracle[(GET_ATTACK, u, item, 0)] = s32(odd_int(rng))
    st.oracle[(TO_DATA, item)] = ITEMDATA(rng.randrange(NITEMS)) if rng.random() > 0.05 else rng.choice(UNMAPPED)
    if rng.random() < 0.4:  # the "pierces dragonskin" flag on the weapon now and then
        k = rng.randrange(NITEMS)
        st.put(ITEMDATA(k), 8, word(st, ITEMDATA(k), 8) | word(st, SP_PIERCE, 8))
    if rng.random() < 0.5:
        focus_forecast(st, side, other, item)
        skill = rng.choice([0, "astra", "fang", "luna", "venge", "astra", "fang", "luna", "venge"])
        skill = 0 if skill == 0 else sx(word(st, SP_SKILLS[skill], 2), 16)
    return (st,) + ov("forecast_damage", [side, other, skill, odd_int(rng)])


def focus_forecast(st, side: int, other: int, item: int) -> None:
    """Half the forecast cases: every cache warm, eight distinct skill numbers, a weapon that hits,
    positive damage most of the time, and the other side's Dragonskin and halve-damage bits set
    often in the row the striking side reads, so that every skill step meets each of them
    (Astra, Luna, Dragon Fang and Vengeance against Dragonskin, with and without the piercing flag)."""
    rng = st.rng
    for g in SP_GUARDS + STAT_GUARDS + EXP_GUARDS:
        st.put(g, 4, rng.choice([1, 0x101]))
    for a, v in zip(SP_SKILLS.values(), rng.sample(range(1, 40), len(SP_SKILLS))):
        st.put(a, 2, v)
    st.put(side + 0x10, 2, rng.randrange(1, 1 << 16))
    st.put(side + 0x28, 4, word(st, side + 0x28) & ~0x40)  # the strike does damage
    if other not in UNMAPPED:
        row = detail_row(st, side)
        st.put(side + 0x48, 4, rng.randrange(20, 130))  # own attack
        d = other + 0x48 + row * 0x24
        for f in (4, 8, 0xC, 0x10):  # defense, its bonus, resistance, its bonus: small
            st.put(d + f, 4, s32(rng.randrange(-3, 25)))
        bits = other + 0xE6 + row * 0x94
        for name, p in (("scale", 0.6), ("aegis", 0.25)):
            b = sx(word(st, SP_SKILLS[name], 2), 16)
            on = rng.random() < p
            addr = bits + (b >> 3)
            st.mem[addr] = (st.mem.get(addr, 0) | (1 << (b & 7))) if on else (st.mem.get(addr, 0) & ~(1 << (b & 7)))
        if rng.random() < 0.7:
            st.put(other + 0x20, 4, 0)  # no terrain: no halving there
    if rng.random() < 0.6:
        st.put(side + 0x28, 4, word(st, side + 0x28) & ~0x2)  # not a follower: no halving there
    if rng.random() < 0.5:  # the weapon pierces dragonskin
        data = st.oracle.get((TO_DATA, item), ITEMDATA(0))
        if data not in UNMAPPED:
            st.put(data, 8, word(st, data, 8) | word(st, SP_PIERCE, 8))


def detail_row(st, other: int) -> int:
    t = st.mem.get(other)
    return 1 if t in (2, 3) else 0


def gen_avoid(rng):
    st = base_state(rng)
    cool(st, (DA_GUARD,))
    make_sides(st)
    a, b = rng.sample(range(4), 2)
    side = SIDE(a)
    other = SIDE(b) if rng.random() > 0.05 else rng.choice(UNMAPPED)
    u = word(st, side + 4)
    st.oracle[(GET_AVOID, u, s32(side + 0x10))] = s32(pick(rng, list(range(-20, 120)), [0x7FFF, 0x8000, 0x12345, -0x8001]))
    row = detail_row(st, other)

    def post(mem):
        return mem.read(side + 0x48 + row * 0x24 + 0x18, 2)
    return (st,) + ov("battle_detail_avoid", [side, other], post)


def fold4(v) -> int:
    def rotl(x, n):
        x &= 0xFFFFFFFF
        return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF if n else x
    return (v[0] ^ rotl(v[1], 7) ^ rotl(v[2], 14) ^ rotl(v[3], 21)) & 0xFFFFFFFF


def gen_defense(rng):
    st = base_state(rng)
    cool(st, (DD_GUARD,))
    make_sides(st)
    a, b = rng.sample(range(4), 2)
    side = SIDE(a)
    other = SIDE(b) if rng.random() > 0.05 else rng.choice(UNMAPPED)
    u = word(st, side + 4)
    d, r = s32(odd_int(rng)), s32(odd_int(rng))
    st.oracle[(DEF_IMPL, u, s32(side + 0x10), 1, 1)] = d
    st.oracle[(MDEF_IMPL, u, s32(side + 0x10), 1, 1)] = r
    row = detail_row(st, other)

    def post(mem):
        base = side + 0x48 + row * 0x24
        return fold4([mem.read(base + off, 4) for off in (4, 8, 0xC, 0x10)])
    return (st,) + ov("battle_detail_defense", [side, other, d, r], post)


def gen_item_bonus(rng):
    st = base_state(rng)
    u = unit_arg(st)
    answer_unit(st, u)
    stat = pick(rng, list(range(8)), [-1, 8, 40, 0x7FFFFFFF, -0x80000000], 0.08)
    return (st,) + ov("unit_item_stat_bonus", [u, stat])


def gen_edit(rng):
    st = base_state(rng)
    st.fill(EDIT, 0x20)
    st.put(EDIT + 0x1A, 1, pick(rng, list(range(NPERS)), [255, 100], 0.05))
    st.put(EDIT + 0x1B, 1, pick(rng, list(range(NPERS)), [255, 100], 0.05))
    e = EDIT if rng.random() > 0.05 else rng.choice(UNMAPPED)
    stat = pick(rng, list(range(8)), [-1, 8, 40, -0x80000000], 0.08)
    return (st,) + ov("edit_stat_bonus", [e, stat])


def gen_rally_bit(rng):
    st = base_state(rng)
    st.fill(ENH, 0x10)
    e = ENH if rng.random() > 0.05 else rng.choice(UNMAPPED)
    stat = pick(rng, list(range(0, 12)) + [31, 1, 10, 10], [-1, -22, 234, 0x7FFFFFFF, -0x80000000, 255, 256 + 3], 0.15)
    value = pick(rng, [0, 1, 2, 3, 4, 5], [-1, -0x80000000, 0x7FFFFFFF], 0.1)
    if rng.random() < 0.3:  # the edge rally bits (23 and 32) set often
        st.put(ENH + 2, 1, st.mem[ENH + 2] | 0x80)
        st.put(ENH + 4, 1, st.mem[ENH + 4] | 0x01)
    return (st,) + ov("enhance_has_rally_bonus", [e, stat, value])


def gen_rally_skill(rng):
    st = base_state(rng)
    cool(st, RALLY_GUARDS, 0.005)
    u = unit_arg(st)
    answer_unit(st, u)
    if rng.random() < 0.5:  # focused: none or only a late skill, so more of the list is asked
        for a in RALLY_SKILLS:
            st.oracle[(IS_EQUIP, s32(u), s32(sx(word(st, a, 2), 16)))] = 0
        if rng.random() < 0.6:
            a = rng.choice(RALLY_SKILLS)
            st.oracle[(IS_EQUIP, s32(u), s32(sx(word(st, a, 2), 16)))] = 1
        if rng.random() < 0.3:  # exactly one guard cold, the others warm: each guard is asked
            for g in RALLY_GUARDS:
                st.put(g, 4, 1)
            st.put(rng.choice(RALLY_GUARDS), 4, 0)
    return (st,) + ov("unit_has_rally_stat_skill", [u])


def gen_sound(rng):
    st = base_state(rng)
    rec = 0x08370000
    st.fill(SOUND_STATE, 0x10)
    st.put(SOUND_STATE + 8, 4, rec if rng.random() > 0.05 else rng.choice(UNMAPPED))
    st.fill(rec + 0x180, 0x10)
    st.put(rec + 0x18C, 1, pick(rng, [0, 1, 2, 3, 4, 4, 5], [255, 0x84]))
    return (st,) + ov("sound_is_individual_battle", [])


def gen_job(name, guard_addr, mask):
    def gen(rng):
        st = base_state(rng)
        cool(st, (guard_addr,), 0.08)
        if rng.random() < 0.15:  # its own guard warm, the other class guard cold
            st.put(guard_addr, 4, 1)
            st.put(GIANT_GUARD if guard_addr == HIGH_GUARD else HIGH_GUARD, 4, 0)
        k = rng.randrange(NJOBS)
        if rng.random() < 0.4:
            st.put(JOB(k), 8, word(st, JOB(k), 8) & ~word(st, mask, 8))
        j = JOB(k) if rng.random() > 0.06 else rng.choice(UNMAPPED)
        return (st,) + ov(name, [j])
    return gen


def gen_situation(name, nargs):
    def gen(rng):
        st = base_state(rng)
        flags = rng.randrange(1 << 32)
        for bit in (0x200, 0x80000, 0x800000, 0x1000000):
            if rng.random() < 0.5:
                flags &= ~bit
        st.put(SIT + 4, 4, flags)
        for i in range(4):
            st.put(SIT + i, 1, pick(rng, [0, 1, 1, 2], [255]))
        st.put(GUD + 0x28, 4, rng.randrange(1 << 32) & (rng.choice([0, 4, 8, 12, 0xFFFFFFFF])))
        sit = SIT if rng.random() > 0.05 else rng.choice(UNMAPPED)
        args = [sit]
        if nargs == 2:
            args.append(pick(rng, [0, 1, 2, 3], [0xFFFFFFFF, 0x80000000, 100]) if name != "situation_is_casual"
                        else pick(rng, [0, 1], [2, 0x100, 0xFFFFFFFF]))
        return (st,) + ov(name, args)
    return gen


def cold(st, guards) -> bool:
    return any(word(st, g) & 1 == 0 for g in guards)


def early_ok(name: str, st, args: list[int]) -> bool:
    """Whether the readable code may give up before reading anything in this case while the
    original runs to the end: exactly when one of the caches it asks first is cold, or
    (forecast_damage) a step needs a getter with a stack argument (Ignis, Rend Heaven) or the
    Dragon Fang call's caches are cold. Any other early give-up is a mismatch."""
    if name == "forecast_damage":
        if cold(st, SP_GUARDS):
            return True
        skill = s32(args[2])
        sk = {k: s32(sx(word(st, a, 2), 16)) for k, a in SP_SKILLS.items()}
        if skill in (sk["ignis"], sk["rend"]):
            return True
        return skill == sk["fang"] and cold(st, STAT_GUARDS + EXP_GUARDS)
    guards = {"battle_detail_avoid": (DA_GUARD,), "battle_detail_defense": (DD_GUARD,),
              "unit_has_rally_stat_skill": RALLY_GUARDS, "job_is_promoted": (HIGH_GUARD,),
              "job_is_giant": (GIANT_GUARD,)}.get(name, ())
    return cold(st, guards)


FUNCS = {
    "battle_dead_unit": gen_dead_unit,
    "battle_strike_run": gen_strike_run,
    "forecast_damage": gen_forecast,
    "battle_detail_avoid": gen_avoid,
    "battle_detail_defense": gen_defense,
    "unit_item_stat_bonus": gen_item_bonus,
    "edit_stat_bonus": gen_edit,
    "enhance_has_rally_bonus": gen_rally_bit,
    "unit_has_rally_stat_skill": gen_rally_skill,
    "job_is_promoted": gen_job("job_is_promoted", HIGH_GUARD, HIGH_MASK),
    "job_is_giant": gen_job("job_is_giant", GIANT_GUARD, GIANT_MASK),
    "situation_is_casual": gen_situation("situation_is_casual", 2),
    "situation_is_phoenix": gen_situation("situation_is_phoenix", 1),
    "situation_records_death": gen_situation("situation_records_death", 2),
    "situation_records_kill": gen_situation("situation_records_kill", 2),
    "sound_is_individual_battle": gen_sound,
}


# ------------------------------------------------------------------ the ARM side
class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX and every tail branch (B) to a callee of ARITY with its
    argument registers (stubbed calls; a tail branch to an unstubbed callee runs on as ARM code)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.listed: list[str] = []

    def call(self, target: int, ret: int) -> bool:
        if target in ARITY:
            self.listed.append(call_text(target, self.r[:ARITY[target]]))
        return super().call(target, ret)

    def step(self, ins: int, pc: int) -> None:
        c = ins >> 28
        if c != 0xF and self.cond(c) and (ins >> 24) & 0xF == 0xA:  # B (no link)
            target = (pc + 8 + (A.sx(ins & 0xFFFFFF, 24) << 2)) & A.MASK
            stub = self.stubs.get(target)
            if target in ARITY and stub is not None:
                self.listed.append(call_text(target, self.r[:ARITY[target]]))
                self.r[0] = stub(self, tuple(self.r[:4])) & A.MASK
                self.r[15] = self.r[14]
                return
        super().step(ins, pc)


def call_text(target: int, regs) -> str:
    return f"{target:x}" + "".join(f":{r & 0xFFFFFFFF:x}" for r in regs)


def calls_field(listed: list[str]) -> str:
    return ",".join(listed) if listed else "-"


def arm_run(text: bytes, st, kind: str, args: list[int], how: tuple) -> list:
    """Expected outputs, in the order the C driver prints them: [gave_up, r0, faults, calls]. For a
    helper, r0 is what the original stored (how[2] reads it from the memory afterwards)."""
    mem = A.Memory(text)
    for a, d in st.regions():
        mem.map(a, d)

    def answer(f, n):
        return lambda cpu, a: st.oracle.get((f,) + tuple(x & 0xFFFFFFFF for x in a[:n]), 0)
    stubs = {f: answer(f, n) for f, n in LEAF_STUBS.items()}
    stubs.update({f: answer(f, n) for f, n in ARM_ONLY_STUBS.items()})
    cpu = ListingCpu(mem, stubs, guard=GUARD)
    cpu.r[13], cpu.r[14] = SP, A.RETURN_SENTINEL
    for i in range(4):
        cpu.r[i] = args[i] & 0xFFFFFFFF
    try:
        cpu.run(how[1])
    except A.ColdGuard:
        return [1]
    r0 = cpu.r[0] if how[2] is None else how[2](mem)
    return [0, r0, mem.faults, calls_field(cpu.listed)]


# ------------------------------------------------------------------ the C side
DRIVER_HEAD = r'''
/* Generated by src/readable/battle2/tests/battle2_diff.py: runs the second battle-numbers batch on
   memory images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "battle2.h"
'''

TEST_ENTRY_CODE = r'''
/* test-only entries (never in src/readable/: these addresses have no override row) */
static uint32_t b2_rotl(uint32_t x, unsigned n) { return n ? (x << n) | (x >> (32u - n)) : x; }
static uint32_t t_avoid(Context *ctx, gaddr side, gaddr other) { return battle_detail_avoid(ctx, side, other); }
static uint32_t t_defense(Context *ctx, gaddr side, gaddr other, int32_t d, int32_t r) {
    int32_t out[4];
    battle_detail_defense(ctx, side, other, d, r, out);
    return (uint32_t)out[0] ^ b2_rotl((uint32_t)out[1], 7) ^ b2_rotl((uint32_t)out[2], 14) ^ b2_rotl((uint32_t)out[3], 21);
}
void test_0x005253A8(Context *ctx) { FE_ENTRY(0x005253A8, forecast_damage, FE_ARG(0), FE_ARG(1), FE_ARG_S(2), FE_ARG_S(3)); }
void test_0x003491F8(Context *ctx) { FE_ENTRY(0x003491F8, t_avoid, FE_ARG(0), FE_ARG(1)); }
void test_0x00349CF0(Context *ctx) { FE_ENTRY(0x00349CF0, t_defense, FE_ARG(0), FE_ARG(1), FE_ARG_S(2), FE_ARG_S(3)); }
'''


def driver_text() -> str:
    sys.path.insert(0, os.path.join(ROOT, "src", "readable", "sheet", "tests"))
    import sheet_diff as S  # the same driver body: page memory, call list, oracle, nested give-ups
    body = S.DRIVER.split('#include "sheet.h"\n', 1)[1]
    decls = "".join(f"void override_0x{a:08X}(Context *);\n" for a in sorted(OVERRIDES.values()))
    entries = [(a, f"override_0x{a:08X}") for a in sorted(OVERRIDES.values())] + \
        [(a, f"test_0x{a:08X}") for a in sorted(TEST_ENTRIES.values())]
    table = "static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n" + "".join(
        f"    {{0x{a:08X}u, {f}}},\n" for a, f in entries) + "};\n"
    tdecls = "".join(f"void test_0x{a:08X}(Context *);\n" for a in sorted(TEST_ENTRIES.values()))
    return DRIVER_HEAD + body.replace("@OVERRIDE_DECLS@", decls + tdecls + table) + TEST_ENTRY_CODE


def find_cc() -> str | None:
    import check  # tools/readable/check.py: the same compiler search
    return check.find_cc()


_SHARED_OBJS: dict[str, str] = {}  # the other areas' objects, compiled once per run (plants reuse them)


def _compile(cc: str, src: str, obj: str, flags: list[str], env: dict) -> str | None:
    r = subprocess.run([cc] + flags + ["-c", src, "-o", obj], capture_output=True, text=True, env=env)
    return f"{src}:\n{r.stdout}{r.stderr}" if r.returncode else None


def build_driver(cc: str, out: str, b2_dir: str, strict: bool = True) -> str:
    """Builds the driver with every source of src/readable/, the battle2 folder's taken from b2_dir
    (a planted bug may leave a parameter unused: not strict then, warnings are not errors). Each
    source is compiled on its own, in parallel; the other areas' objects are compiled once per run
    (strict) and reused for every planted bug, so a plant rebuilds only battle2 and the driver."""
    from concurrent.futures import ThreadPoolExecutor
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "battle2_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_B2)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(b2_dir, f) for f in sorted(os.listdir(b2_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "battle2_driver.exe" if os.name == "nt" else "battle2_driver")
    inc = ["-I", b2_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
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
        raise SystemExit("battle2_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"battle2_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


PATHS: dict[tuple[str, bool], list[int]] = {}  # forecast_damage: (skill step, Dragonskin) -> [cases, damage > 0]


def forecast_path(st, args: list[int], r0: int) -> None:
    """Counts which skill step met the other side's Dragonskin bit (printed as evidence)."""
    side, other, skill = args[0], args[1], s32(args[2])
    names = [k for k in ("astra", "fang", "luna", "venge") if s32(sx(word(st, SP_SKILLS[k], 2), 16)) == skill]
    step = names[0] if names and skill != 0 else "none"
    row = detail_row(st, side)
    b = sx(word(st, SP_SKILLS["scale"], 2), 16)
    scale = bool(st.mem.get(other + 0xE6 + row * 0x94 + (b >> 3), 0) >> (b & 7) & 1)
    c = PATHS.setdefault((step, scale), [0, 0])
    c[0] += 1
    c[1] += int(r0 != 0)


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
                exp = arm_run(text, st, kind, args, how)
            except A.Unsupported as e:
                unsupported[name] = unsupported.get(name, 0) + 1
                if unsupported[name] == 1:
                    print(f"  ARM interpreter: {name}: {e}")
                continue
            expected[cid] = (name, exp, (kind, args), early_ok(name, st, args))
            if name == "forecast_damage" and exp[0] == 0:
                forecast_path(st, args, exp[1])
            lines.append(f"case {cid} {kind} " + " ".join(f"{x & 0xFFFFFFFF:x}" for x in args) + f" {SP:x}")
            lines += [f"stub {f:x} {k}" for f, k in LEAF_STUBS.items()]
            for addr, data in st.regions():
                for off in range(0, len(data), 4096):
                    lines.append(f"mem {addr + off:x} {data[off:off + 4096].hex()}")
            for key, val in st.oracle.items():
                if key[0] in ARM_ONLY_STUBS:
                    continue
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
        raise SystemExit(f"battle2_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
    got: dict[int, list] = {}
    flagged: dict[int, str] = {}
    for ln in r.stdout.split("\n"):
        parts = ln.split()
        if len(parts) >= 2 and parts[1] in ("WROTE-GUEST", "NO-OVERRIDE", "NESTED-GIVEUP"):
            flagged[int(parts[0])] = parts[1]
        elif parts:
            got[int(parts[0])] = [parse(x) for x in parts[1:4]] + parts[4:]  # the call list stays text
    per: dict[str, list[int]] = {}
    for c, (name, exp, inputs, early) in expected.items():
        res = per.setdefault(name, [0, 0, 0, 0])  # cases, mismatches, gave-up cases, early give-ups
        res[0] += 1
        g = got.get(c)
        if exp[0] == 0:  # what the cases exercise (printed as evidence)
            cov = COVERAGE.setdefault(name, {"values": set(), "nonzero": 0, "faulty": 0, "calls": 0})
            cov["values"].add(exp[1])
            cov["nonzero"] += int(exp[1] != 0)
            cov["faulty"] += int(exp[2] != 0)
            cov["calls"] += 0 if exp[3] == "-" else exp[3].count(",") + 1
        if exp[0] == 1:
            res[2] += 1
            exp = [1, 0]  # a give-up must come before any unmapped read
        elif g is not None and g[:1] == [1] and g[1:] == [0] and c not in flagged and early:
            # an early give-up where early_ok allows one: a needed cache is cold, or
            # (forecast_damage) a step needs a getter with a stack argument; the readable code asks
            # before reading anything unmapped; always safe (the original runs). Any other early
            # give-up falls through and is a mismatch (a bug that gives up more often is caught)
            res[3] += 1
            continue
        if g is None or g != exp or c in flagged:
            res[1] += 1
            if res[1] <= show and not quiet:
                why = f" ({flagged[c]})" if c in flagged else ""
                print(f"  MISMATCH {name} case {c}: original {exp}, readable {g}{why}; {inputs[0]} "
                      + " ".join(f"{x & 0xFFFFFFFF:#x}" for x in inputs[1]))
    return per


# planted bugs: (file, exact text, replacement); each text occurs once in its file
PLANTS = [
    # battle2_calc.c
    ("battle2_calc.c", "        if (kind == 1 || kind == 4 || kind == 8 || kind == 9)\n            return 0;",
     "        if (kind == 1 || kind == 4 || kind == 8)\n            return 0;"),
    ("battle2_calc.c", "            return READ_FIELD(ctx, BattleSide, info + side * B2_SIDE_SIZE, unit);",
     "            return READ_FIELD(ctx, BattleSide, info + side * 0x1F8u, unit);"),
    ("battle2_calc.c", "        if (kind == 8)\n            break;", "        if (kind == 7)\n            break;"),
    ("battle2_calc.c", "        if (kind == 1)\n            count++;", "        count++;"),
    # a record of the other side passed over instead of ending the run
    ("battle2_calc.c", "        if (guest_u8(ctx, rec + B2_SCENE_SIDE) != guest_u8(ctx, scene + B2_SCENE_SIDE))\n            break;",
     "        if (guest_u8(ctx, rec + B2_SCENE_SIDE) != guest_u8(ctx, scene + B2_SCENE_SIDE)) {\n"
     "            rec = guest_ptr(ctx, rec + B2_SCENE_NEXT);\n            continue;\n        }"),
    ("battle2_calc.c", "    if (skill == ignis || skill == rend)\n        return (int32_t)fe_use_original(ctx);",
     "    if (skill == ignis)\n        return (int32_t)fe_use_original(ctx);"),
    # gives up more often than it must (Astra too): an early give-up early_ok does not allow
    ("battle2_calc.c", "    if (skill == ignis || skill == rend)\n        return (int32_t)fe_use_original(ctx);",
     "    if (skill == ignis || skill == rend || skill == astra)\n        return (int32_t)fe_use_original(ctx);"),
    ("battle2_calc.c", "    gaddr guard = (flags & B2_SIDE_FLAG_MAGIC) ? FIELD_ADDR(BattleDetail, detail, resistance)",
     "    gaddr guard = (flags & 0x10u) ? FIELD_ADDR(BattleDetail, detail, resistance)"),
    ("battle2_calc.c", "    int32_t attack = READ_FIELD(ctx, BattleSide, side, detail[0].attack);",
     "    int32_t attack = guest_s32(ctx, FIELD_ADDR(BattleSide, side, detail) + row * (gaddr)sizeof(BattleDetail));"),
    ("battle2_calc.c", "    damage = fe_add32(damage, -guest_s32(ctx, guard + 4u)); /* the bonus word after the stat */",
     "    damage = fe_add32(damage, -guest_s32(ctx, guard + 8u)); /* the bonus word after the stat */"),
    ("battle2_calc.c", "                                           triangle < 0 ? 0u : 1u);",
     "                                           triangle <= 0 ? 0u : 1u);"),
    ("battle2_calc.c", "        damage = fe_add32(damage, b2_bit(ctx, bits, guest_s16(ctx, S_SpScale)) ? fe_asr(vengeance, 1) : vengeance);",
     "        damage = fe_add32(damage, b2_bit(ctx, bits, guest_s16(ctx, S_SpScale)) ? vengeance : fe_asr(vengeance, 1));"),
    ("battle2_calc.c", "            damage = fe_mul32(damage, 35) / 100; /* rounds toward zero, as the game's multiply-high does */",
     "            damage = fe_asr(fe_mul32(damage, 35), 7);"),
    ("battle2_calc.c", "            damage = fe_asr(fe_mul32(damage, 3), 2);", "            damage = fe_asr(damage, 1);"),
    ("battle2_calc.c", "    if (b2_bit(ctx, bits, guest_s16(ctx, S_SpAegis)))\n        damage = fe_asr(damage, 1);",
     "    if (b2_bit(ctx, bits, guest_s16(ctx, S_SpAegis)))\n        damage = fe_asr(damage, 2);"),
    ("battle2_calc.c", "    gaddr terrain = guest_ptr(ctx, other + B2_SIDE_TERRAIN);\n    if (terrain != 0) {",
     "    gaddr terrain = guest_ptr(ctx, side + B2_SIDE_TERRAIN);\n    if (terrain != 0) {"),
    ("battle2_calc.c", "        if (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & B2_TERRAIN_ATTR_QUARTER)",
     "        if (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & 0x800000u)"),
    ("battle2_calc.c", "        guest_s8(ctx, terrain + number_at) < 0) {", "        guest_s8(ctx, terrain + number_at) <= 0) {"),
    ("battle2_calc.c", "        if (guest_call2(ctx, B2_ForceIsAllied, force, 1u) != 0)\n            return 0;",
     "        if (guest_call2(ctx, B2_ForceIsAllied, force, 1u) == 0)\n            return 0;"),
    ("battle2_calc.c", "        avoid = (uint16_t)(avoid + READ_FIELD(ctx, TerrainTileData, terrain, avoid));",
     "        avoid = (uint16_t)(avoid + READ_FIELD(ctx, TerrainTileData, terrain, defense));"),
    ("battle2_calc.c", "    sum += guest_u16(ctx, side + B2_SIDE_AVOID_C);", "    sum += guest_u16(ctx, side + 0x1F2u);"),
    ("battle2_calc.c", "    int16_t result = (int16_t)(uint16_t)sum;\n    return result < 0 ? 0u : (uint32_t)result;",
     "    int32_t result = (int32_t)sum;\n    return result < 0 ? 0u : (uint32_t)(uint16_t)result;"),
    ("battle2_calc.c", "    uint32_t row = b2_row_of(ctx, other);\n    gaddr unit = READ_FIELD(ctx, BattleSide, side, unit);\n    if (unit == 0 || READ_FIELD(ctx, BattleSide, other, unit) == 0)\n        return 0;\n    uint16_t",
     "    uint32_t row = b2_row_of(ctx, side);\n    gaddr unit = READ_FIELD(ctx, BattleSide, side, unit);\n    if (unit == 0 || READ_FIELD(ctx, BattleSide, other, unit) == 0)\n        return 0;\n    uint16_t"),
    ("battle2_calc.c", "    int32_t res_bonus = fe_add32(fe_add32(guest_s32(ctx, bonus), guest_s32(ctx, bonus + 8u)), extra);",
     "    int32_t res_bonus = fe_add32(fe_add32(guest_s32(ctx, bonus), guest_s32(ctx, bonus + 4u)), extra);"),
    ("battle2_calc.c", "    out[2] = resistance > 0 ? resistance : 0;", "    out[2] = resistance;"),
    ("battle2_calc.c", "        res_bonus = fe_add32(res_bonus, READ_FIELD(ctx, TerrainTileData, terrain, defense));\n",
     ""),
    # battle2_bonus.c
    ("battle2_bonus.c", "        if (guest_call3(ctx, B2_UnitIsItemEnhanceHave, unit, item, 0u) != 0) {",
     "        if (guest_call3(ctx, B2_UnitIsItemEnhanceHave, unit, item, 1u) != 0) {"),
    ("battle2_bonus.c", "            total = fe_add32(total, guest_s8(ctx, data + (gaddr)stat + B2_ITEM_EXTRA));",
     "            total = fe_add32(total, guest_s8(ctx, data + (gaddr)stat + 0x38u));"),
    ("battle2_bonus.c", "                    guest_s8(ctx, FIELD_ADDR(PersonalityData, bane, bane_base) + (gaddr)stat));",
     "                    guest_s8(ctx, FIELD_ADDR(PersonalityData, bane, boon_base) + (gaddr)stat));"),
    ("battle2_bonus.c", "    if (bit - 23u > 9u)\n        return 0;", "    if (bit - 23u > 8u)\n        return 0;"),
    ("battle2_bonus.c", "    if (value > (stat == 31 ? 4 : 2))", "    if (value >= (stat == 31 ? 4 : 2))"),
    ("battle2_bonus.c", "        int32_t skill = guest_s16(ctx, S_RallySkills + 2u * i);",
     "        int32_t skill = guest_u16(ctx, S_RallySkills + 2u * i);"),
    # one rally guard not asked: a give-up after a guest call
    ("battle2_bonus.c", "    for (uint32_t i = 0; i < B2_RALLY_SKILLS; i++)\n        if (!fe_static_ready(ctx, S_RallyGuard0 - 4u * i))",
     "    for (uint32_t i = 0; i + 1u < B2_RALLY_SKILLS; i++)\n        if (!fe_static_ready(ctx, S_RallyGuard0 - 4u * i))"),
    # battle2_rules.c
    ("battle2_rules.c", "    return (READ_FIELD(ctx, JobData, job, flags) & guest_u64(ctx, S_HighMask)) != 0 ? 1u : 0u;",
     "    return (READ_FIELD(ctx, JobData, job, flags) & guest_u64(ctx, S_GiantMask)) != 0 ? 1u : 0u;"),
    ("battle2_rules.c", "    if (!fe_static_ready(ctx, S_GiantGuard))", "    if (!fe_static_ready(ctx, S_HighGuard))"),
    ("battle2_rules.c", "    if (ignore_map != 0)\n        return 0;", "    if (ignore_map == 1)\n        return 0;"),
    ("battle2_rules.c", "    return (user_mode(ctx) & B2_USER_PHOENIX) != 0 ? 1u : 0u;",
     "    return (user_mode(ctx) & B2_USER_CASUAL) != 0 ? 1u : 0u;"),
    ("battle2_rules.c", "    if (READ_FIELD(ctx, Situation, situation, flags) & B2_SITUATION_NO_DEATH_RECORD)",
     "    if (READ_FIELD(ctx, Situation, situation, flags) & B2_SITUATION_NO_KILL_RECORD)"),
    ("battle2_rules.c", "    if (force >= 3u)\n        return 0;\n    if (READ_FIELD(ctx, Situation, situation, flags) & B2_SITUATION_NO_KILL_RECORD)",
     "    if (force > 3u)\n        return 0;\n    if (READ_FIELD(ctx, Situation, situation, flags) & B2_SITUATION_NO_KILL_RECORD)"),
]
def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_B2, d, ignore=shutil.ignore_patterns("tests"))
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
              + (f"caught, {bad} mismatches in {', '.join(hit[:4])}{' ...' if len(hit) > 4 else ''}"
                 if bad else "NOT CAUGHT"))
        missed += 0 if bad else 1
    return missed


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=300, help="cases per function (default 300)")
    ap.add_argument("--seed", type=int, default=20261115)
    ap.add_argument("--only", help="one function name")
    ap.add_argument("--show", type=int, default=5, help="mismatches to print per function")
    ap.add_argument("--plant", action="store_true", help="also check that planted bugs are caught")
    ap.add_argument("--plant-n", type=int, help="cases per function for each planted bug (default: -n)")
    a = ap.parse_args(argv)
    if a.only and a.only not in FUNCS:
        print(f"unknown function {a.only}; one of: {', '.join(FUNCS)}")
        return 2
    if not os.path.isfile(TEXT):
        print("battle2_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("battle2_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_B2)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"battle2_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed {a.seed}")
    for name, (n, bad, cold, early) in per.items():
        total_bad += bad
        notes = ([f"{cold} cold: both reached / gave up at the cache"] if cold else []) + \
                ([f"{early} early give-ups"] if early else [])
        print(f"  {name:28s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({'; '.join(notes)})" if notes else ""))
    for name, k in unsupported.items():
        print(f"  {name:28s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("battle2_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:28s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    if PATHS:
        print("battle2_diff: forecast_damage steps met (skill step / other side's Dragonskin: cases, damage > 0)")
        print("  " + ", ".join(f"{k[0]}/{'skin' if k[1] else 'no skin'} {v[0]}:{v[1]}" for k, v in sorted(PATHS.items())))
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"battle2_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"battle2_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
