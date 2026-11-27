#!/usr/bin/env python3
"""Host differential test of the status-sheet readable code against the game's own ARM code.

    python src/readable/sheet/tests/sheet_diff.py             all functions, 300 cases each
    python src/readable/sheet/tests/sheet_diff.py -n 1500 --seed 7    the long run
    python src/readable/sheet/tests/sheet_diff.py --only unit_move
    python src/readable/sheet/tests/sheet_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/skill/tests/skill_diff.py (and the ARM interpreter
src/readable/battle/tests/arm_mini.py): for every readable function of src/readable/sheet/ the
test makes up guest states (units with their Person, class, partner, avatar record, carried items,
Item and sub-kind records, Belong records, the map HP window, the one-time caches; all random test
values, never game data, and on purpose often outside the ranges the game uses: negative stats and
caps, bools that are not 0/1, rally kinds that are no rally, force types of 32 and more, slots past
4, unmapped units and "torn" units whose record stops at an offset the readers read), runs the
ORIGINAL ARM code from the owner's extracted/text.bin in arm_mini.py and the readable C function
(built with the host gcc against tools/readable/stub/) on the same memory, and compares r0, the
number of bytes read from unmapped memory (tier 2 compares that count) AND the list of guest calls,
in order, with their argument registers (docs/DECISIONS.md F-018). On the ARM side every BL/BLX to
a listed callee is listed (also inside callees that run as ARM code); on the C side every guest
call is listed (one that reaches another override of this batch runs that override, as in the
capture library). A one-time cache that is not filled must make the original reach the guard
routine and the readable code give up before reading anything; a nested give-up (a guest call of
another readable function giving up inside while the outer one goes on) is a mismatch.

Guest functions answered by one table on both sides: unit::Item::ToData, Unit::GetLimit,
unit::Edit::GetCapability, Unit::GetDoubleCapability, Unit::IsEquipSkill, GetEnhanceHave,
Unit::GetItemIndexEquipped, ItemSubKind::Get, Belong::Get, Person::GetCaptureChange, Job::IsGiant,
Person::IsDownload, Unit::CanItemEquip. Unit::GetCategory runs as ARM code on the ARM side and as
its readable override on the C side (unit_move calls it).

--plant copies src/readable/sheet/ to build/readable/sheet/plant/, makes one small wrong change at a
time (PLANTS below), rebuilds and reruns: every planted bug must give at least one mismatch.

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
OUT = os.path.join(ROOT, "build", "readable", "sheet")
SRC_SHEET = os.path.join(ROOT, "src", "readable", "sheet")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
TO_DATA, GET_LIMIT, EDIT_CAP, DOUBLE_CAP, IS_EQUIP, ENHANCE, EQUIP_INDEX = (
    0x003D0EA4, 0x005337F0, 0x0053ABEC, 0x00530A34, 0x0052DD04, 0x0033A790, 0x005310C0)
SUBKIND_GET, BELONG_GET, CAPTURE, IS_GIANT, IS_DOWNLOAD, CAN_EQUIP = (
    0x0019B97C, 0x0044529C, 0x0053E1BC, 0x005249F8, 0x0053DFEC, 0x0052C634)
LEAF_STUBS = {TO_DATA: 1, GET_LIMIT: 2, EDIT_CAP: 2, DOUBLE_CAP: 3, IS_EQUIP: 2, ENHANCE: 2, EQUIP_INDEX: 1,
              SUBKIND_GET: 1, BELONG_GET: 1, CAPTURE: 2, IS_GIANT: 1, IS_DOWNLOAD: 1, CAN_EQUIP: 4}

OVERRIDES = {  # name -> address
    "unit_defense": 0x0052A000, "unit_resistance": 0x0052BF6C, "unit_max_hp": 0x0052A364,
    "hp_window_max_hp": 0x0052A350, "hp_window_hp": 0x00373954, "unit_move": 0x0052D5E4,
    "unit_category": 0x0052B728, "unit_equipped_item": 0x0052EFE8, "unit_equipped_item_mutable": 0x003D5FB0,
    "unit_shown_level": 0x0052DC44, "unit_low_level": 0x0052BBCC, "unit_item_count": 0x0052E594,
    "unit_range_min": 0x00534474, "unit_may_not_attack": 0x0052DC90, "unit_is_unique": 0x00533A80,
    "unit_is_special_battle": 0x0052F234, "unit_is_invisible": 0x0052C61C, "unit_can_be_captured": 0x0052AE20,
    "unit_held_item_index": 0x0052F474,
}
GET_CATEGORY = 0x0052B728
# the callees listed on both sides, with the argument registers compared
ARITY = dict(LEAF_STUBS)
ARITY.update({GET_CATEGORY: 1})

# caches (src/readable/sheet/sheet.h): guard -> list of (value address, kind)
CACHE_BASE, CACHE_END = 0x006D9600, 0x006D9B00
DEF_GUARDS, DEF_SKILLS = (0x006D9788, 0x006D9784, 0x006D9780, 0x006D977C), (0x006D9650, 0x006D9652, 0x006D9654, 0x006D9656)
RES_GUARDS, RES_SKILLS = (0x006D9794, 0x006D9790, 0x006D978C), (0x006D9658, 0x006D965A, 0x006D965C)
HP_GUARDS, HP_SKILLS = (0x006D9730, 0x006D972C), (0x006D9628, 0x006D962A)
MOVE_GUARDS, MOVE_SKILLS = (0x006D97A8, 0x006D97A4, 0x006D97A0, 0x006D99A8), (0x006D9662, 0x006D9664)
MOVE_FLYER, MOVE_SHOOTER = 0x006D9666, 0x006D96D8
CAT_GUARDS = (0x006D97D0, 0x006D97CC, 0x006D97C8, 0x006D97C4, 0x006D97C0)
CAT_DRAGON, CAT_BEAST = 0x006D9668, 0x006D966A
CAT_FLAGS = (0x006D9AA8, 0x006D9AB0, 0x006D9AB8)
LOW_GUARD, LOW_MASK = 0x006D97E8, 0x006D9AE8
RANGE_GUARD, RANGE_SKILL = 0x006D9898, 0x006D9678
ALL_GUARDS = DEF_GUARDS + RES_GUARDS + HP_GUARDS + MOVE_GUARDS + CAT_GUARDS + (LOW_GUARD, RANGE_GUARD)
SKILL_CACHES = DEF_SKILLS + RES_SKILLS + HP_SKILLS + MOVE_SKILLS + (RANGE_SKILL,)
U16_MASKS = (MOVE_FLYER, MOVE_SHOOTER, CAT_DRAGON, CAT_BEAST)
U64_MASKS = CAT_FLAGS + (LOW_MASK,)

# guest layout of the made-up state
UNIT = lambda k: 0x08000000 + k * 0x400  # noqa: E731
PERSON = lambda k: 0x08010000 + k * 0x100  # noqa: E731
JOB = lambda k: 0x08020000 + k * 0x100  # noqa: E731
FORCE = lambda k: 0x08030000 + k * 0x10  # noqa: E731
ITEMDATA = lambda k: 0x08040000 + k * 0x80  # noqa: E731
SUBKIND = lambda k: 0x08048000 + k * 0x10  # noqa: E731
EDIT = lambda k: 0x08050000 + k * 0x40  # noqa: E731
BELONG = lambda k: 0x08058000 + k * 0x20  # noqa: E731
HPWIN = 0x08060000
LOOSE_ITEM = lambda k: 0x08068000 + k * 4  # noqa: E731
NUNITS = 4
NITEMS = 8
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]
TORN_END = 0x080F1000  # a page nothing else uses: a torn unit ends right before it
# 4-aligned (units are): the cut falls just before or inside a field the readers read
TORN_CUTS = (0x08, 0x0C, 0x28, 0x2C, 0x30, 0x34, 0x38, 0x3C, 0x9C, 0xA0, 0xA4, 0xA8, 0xAC, 0xB0, 0xCC, 0xE4,
             0xE8, 0xF0, 0xF4, 0xF8, 0xFC, 0x108, 0x10C, 0x110, 0x118, 0x11C, 0x12C, 0x130, 0x134)
RALLY_KINDS = [8, 14, 15, 21, 22, 28, 29, 30, 31]
SKILL_IDS = list(range(1, 30))


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def sxs16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def word(st, addr: int, n: int = 4) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(n)), "little")


def guard(st, addr: int, cold_p: float = 0.008) -> None:
    st.put(addr, 4, 0 if st.rng.random() < cold_p else st.rng.choice([1, 0x101, 0xFFFFFFFF]))


def base_state(rng) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.zero(CACHE_BASE, CACHE_END - CACHE_BASE)
    for g in ALL_GUARDS:
        guard(st, g)
    for a in SKILL_CACHES:
        st.put(a, 2, pick(rng, SKILL_IDS, [0, -1, 0x7FFF, 63, -0x8000], 0.08) & 0xFFFF)
    for a in U16_MASKS:
        st.put(a, 2, 1 << rng.randrange(16) if rng.random() > 0.05 else rng.randrange(1 << 16))
    for a in U64_MASKS:
        st.put(a, 8, 1 << rng.randrange(64))
    for k in range(NITEMS):
        item_data(st, k)
    for k in range(6):
        st.fill(SUBKIND(k), 0x10)
        st.put(SUBKIND(k) + 1, 1, pick(rng, [4, 4, 6, 6, 0, 1, 2, 5], [255, 7]))
        st.fill(BELONG(k), 0x20)
    return st


def item_data(st, k: int) -> None:
    rng = st.rng
    d = ITEMDATA(k)
    st.fill(d, 0x80)
    st.put(d + 0x28, 1, pick(rng, [0, 1, 1, 2, 2, 3], [255, 10, 0x80]))
    st.put(d + 0x1A, 1, pick(rng, [0, 1, 2, 3, 4, 5], [0xFF, 0x80, 0x7F]))
    for s in range(8):
        st.put(d + 0x38 + s, 1, pick(rng, [0, 0, 0, 1, 2, -2, 4], [-128, 127]) & 0xFF)


def answer_items(st, item: int) -> None:
    """what ToData / ItemSubKind::Get answer for the unit::Item at item"""
    rng = st.rng
    k = rng.randrange(NITEMS)
    st.oracle[(TO_DATA, s32(item))] = ITEMDATA(k) if rng.random() > 0.03 else rng.choice(UNMAPPED)
    sub = st.mem.get(ITEMDATA(k) + 0x1A, 0)
    sub = sub - 0x100 if sub & 0x80 else sub
    st.oracle[(SUBKIND_GET, s32(sub))] = SUBKIND(rng.randrange(6)) if rng.random() > 0.03 else rng.choice(UNMAPPED)


def flag64(st, addr: int, mask_addr: int, p: float) -> None:
    mask = word(st, mask_addr, 8)
    v = word(st, addr, 8)
    st.put(addr, 8, (v | mask) if st.rng.random() < p else (v & ~mask))


def stat_value(rng) -> int:
    return s32(pick(rng, [0, 1, 5, 10, 20, 30, 40, 60, 99], [-1, -50, 120, 200, 0x7FFFFFFF, -0x80000000], 0.15))


def make_unit(st, k: int) -> int:
    rng = st.rng
    u, p, j = UNIT(k), PERSON(k), JOB(k)
    st.fill(u, 0x140)
    st.fill(p, 0x98)
    st.fill(j, 0x80)
    st.put(u + 0x9C, 4, p)
    st.put(u + 0xA0, 4, j)
    st.put(u + 0xA4, 4, FORCE(k))
    st.fill(FORCE(k), 0x10)
    st.put(FORCE(k) + 8, 1, pick(rng, [0, 1, 2, 3, 4, 7], [31, 32, 33, 255]))
    other = UNIT((k + 1) % NUNITS)
    st.put(u + 0xA8, 4, other if rng.random() < 0.6 else 0)
    st.put(u + 0xB0, 4, EDIT(k) if rng.random() < 0.4 else 0)
    state = rng.randrange(1 << 32)
    for bit, pr in ((2, 0.4), (4, 0.4), (0x200000, 0.3), (0x40000000, 0.3), (0x400000, 0.2), (0x40000, 0.3),
                    (0x10000000, 0.5)):
        state = (state | bit) if rng.random() < pr else (state & ~bit)
    st.put(u + 8, 4, state)
    for i in range(7):  # condition bytes: mostly clear
        st.put(u + 0x28 + i, 1, rng.randrange(256) if rng.random() < 0.35 else 0)
    for s in range(8):  # bases: usually small, sometimes anything (the random fill)
        if rng.random() < 0.7:
            st.put(p + 0x38 + s, 1, pick(rng, [0, 1, 2, 3, 5, 8, 18], [-3, 60]) & 0xFF)
            st.put(j + 0x1C + s, 1, pick(rng, [0, 3, 5, 8, 12, 20], [-10, 127]) & 0xFF)
            st.put(u + 0xC8 + s, 1, pick(rng, [0, 0, 1, 4, 10], [-5, 100]) & 0xFF)
    st.put(j + 0x5D, 1, pick(rng, [4, 5, 6, 7, 8], [0, 1, 255, 0x80]))
    st.put(j + 0x3C, 1, pick(rng, [0, 0, 1, 2], [-1, 127, -128]) & 0xFF)
    st.put(j + 0x7A, 1, 0 if rng.random() < 0.6 else rng.randrange(1, 256))
    st.put(u + 0x12C, 1, pick(rng, [0, 0, 1, 2], [-3, 127, -128]) & 0xFF)
    st.put(u + 0x12D, 1, pick(rng, [0, 0, 0, 1, 3], [-2, 127, -128]) & 0xFF)
    st.put(u + 0xF1, 1, pick(rng, [1, 5, 10, 15, 20], [0, 99, 100, 200, 255]))
    st.put(u + 0xF8, 4, 0 if rng.random() < 0.5 else PERSON(rng.randrange(NUNITS)))
    st.put(u + 0x12E, 1, 0 if rng.random() < 0.4 else rng.randrange(256))
    st.put(u + 0x131, 1, rng.randrange(6) if rng.random() > 0.05 else rng.randrange(256))
    st.put(p + 0x0C, 4, 0 if rng.random() < 0.6 else rng.randrange(1, 1 << 32))
    for base in (u, p, j):
        for m in U64_MASKS:
            flag64(st, base, m, 0.15)
    # carried items: number + flags (0x4000 = equipped); an empty slot now and then
    eq = rng.choice([None, 0, 1, 2, 3, 4, None])
    for slot in range(5):
        a = u + 0x108 + 4 * slot
        flags = rng.randrange(1 << 16) & ~0x4000
        if eq is not None and (slot == eq or (slot > eq and rng.random() < 0.2)):
            flags |= 0x4000
        st.put(a, 2, 0 if rng.random() < 0.15 else rng.randrange(1, 400))
        st.put(a + 2, 2, flags)
        answer_items(st, a)
    # equipped skills: often the cached ones
    cached = [sxs16(word(st, a, 2)) for a in SKILL_CACHES]
    for i in range(5):
        st.put(u + 0xFE + 2 * i, 2, (rng.choice(cached) if rng.random() < 0.5 else rng.randrange(40)) & 0xFFFF)
    answer_unit(st, u, k)
    return u


def answer_unit(st, u: int, k: int) -> None:
    """what the guest calls answer for this unit (also for an unmapped or torn one)"""
    rng = st.rng
    for s in (0, 6, 7):
        st.oracle[(GET_LIMIT, u, s)] = stat_value(rng)
        st.oracle[(EDIT_CAP, EDIT(k), s)] = s32(pick(rng, [0, 1, -1, 2, -2, 3], [100, -100]))
        for partner in range(NUNITS):
            st.oracle[(DOUBLE_CAP, UNIT(partner), s, u)] = s32(pick(rng, [0, 1, 2, 3, 4], [-7, 90]))
        st.oracle[(ENHANCE, u, s)] = s32(pick(rng, [0, 0, 1, 2, 4], [-3, 0x7FFFFFFF]))
    for a in SKILL_CACHES:
        st.oracle[(IS_EQUIP, u, s32(sxs16(word(st, a, 2))))] = int(rng.random() < 0.4)
    st.oracle[(EQUIP_INDEX, u)] = s32(pick(rng, [-1, -1, 0, 1, 2, 3, 4], [5, -2, 0x7FFFFFFF], 0.05))
    for slot in range(5):
        st.oracle[(CAN_EQUIP, u, s32(u + 0x108 + 4 * slot), 1, 1)] = int(rng.random() < 0.5)
    st.oracle[(IS_DOWNLOAD, word(st, u + 0x9C))] = int(rng.random() < 0.5)
    st.oracle[(IS_GIANT, word(st, u + 0xA0))] = int(rng.random() < 0.3)
    st.oracle[(CAPTURE, word(st, u + 0x9C), word(st, word(st, u + 0xA0) + 0x18, 2))] = \
        0 if rng.random() < 0.4 else rng.randrange(1, 1 << 32)


def answer_belongs(st) -> None:
    """Belong::Get for the numbers the units carry (and 0, which unmapped units read)"""
    rng = st.rng
    for b in sorted({0} | set(range(6)) | {st.mem.get(UNIT(k) + 0x131, 0) for k in range(NUNITS)}):
        if rng.random() < 0.97:
            st.oracle[(BELONG_GET, b)] = BELONG(b % 6)
        else:
            st.oracle[(BELONG_GET, b)] = rng.choice(UNMAPPED)


def torn_unit(st, source: int) -> int:
    """a copy of a unit whose record stops (unmapped from there on) at one of the offsets the readers
    read: shows a read the game does not make (or skips) as a fault count"""
    if getattr(st, "torn", None) is not None:
        return st.torn
    cut = st.rng.choice(TORN_CUTS)
    base = TORN_END - cut
    for i in range(cut):
        st.mem[base + i] = st.mem.get(source + i, 0)
    st.torn = base
    answer_unit(st, base, (source - UNIT(0)) // 0x400)
    for slot in range(5):
        answer_items(st, base + 0x108 + 4 * slot)
    return base


def unit_arg(st, units: list[int], unmapped_p: float = 0.1, torn_p: float = 0.12) -> int:
    r = st.rng.random()
    if r < unmapped_p:
        u = st.rng.choice(UNMAPPED)
        answer_unit(st, u, 0)
        for slot in range(5):
            answer_items(st, u + 0x108 + 4 * slot)
        return u
    if r < unmapped_p + torn_p:
        return torn_unit(st, st.rng.choice(units))
    return st.rng.choice(units)


def all_units(st) -> list[int]:
    units = [make_unit(st, k) for k in range(NUNITS)]
    answer_belongs(st)
    return units


def bool_arg(rng) -> int:
    return pick(rng, [0, 1, 1], [2, 0x100, 0xFFFFFFFF], 0.15)


def item_arg(st, u: int) -> int:
    rng = st.rng
    r = rng.random()
    if r < 0.15:
        return 0
    if r < 0.75:
        return s32(u + 0x108 + 4 * rng.randrange(5))
    a = LOOSE_ITEM(rng.randrange(4))
    st.put(a, 4, rng.randrange(1 << 32))
    answer_items(st, a)
    return a


def cool(st, guards, p: float = 0.03) -> None:
    for g in guards:
        if st.rng.random() < p:
            st.put(g, 4, 0)


# ------------------------------------------------------------------ the functions
# Each generator returns (state, kind, args, how the ARM side runs).

def ov(name, args):
    a = OVERRIDES[name]
    return f"ov:0x{a:08X}", args + [0] * (4 - len(args)), ("call", a)


def gen_guard_stat(name, guards):
    def gen(rng):
        st = base_state(rng)
        units = all_units(st)
        cool(st, guards)
        u = unit_arg(st, units)
        st.put(SP, 4, s32(pick(rng, [0, 0, 0] + RALLY_KINDS, [rng.randrange(1 << 32), -1], 0.1)))
        return (st,) + ov(name, [u, item_arg(st, u), bool_arg(rng), bool_arg(rng)])
    return gen


def gen_max_hp(rng):
    st = base_state(rng)
    units = all_units(st)
    cool(st, HP_GUARDS)
    u = unit_arg(st, units)
    kind = pick(rng, [0, 0, 8, 8, 1, 14], [rng.randrange(1 << 32), 0x108], 0.1)
    if rng.random() < 0.3 and UNIT(0) <= u < UNIT(NUNITS):  # focused: the halving bit with an odd cap,
        # negative too (the game halves toward zero)
        st.put(u + 0x28, 1, st.mem[u + 0x28] | 0x20)
        st.oracle[(GET_LIMIT, u, 0)] = s32(rng.choice([-1, -3, -7, -51, 7, 9, 15]))
    return (st,) + ov("unit_max_hp", [u, bool_arg(rng), rng.randrange(1 << 32), s32(kind)])


def gen_window(name):
    def gen(rng):
        st = base_state(rng)
        units = all_units(st)
        cool(st, HP_GUARDS)
        st.fill(HPWIN, 0x100)
        st.put(HPWIN + 0xE0, 4, unit_arg(st, units))
        w = HPWIN if rng.random() > 0.05 else rng.choice(UNMAPPED)
        if w != HPWIN:
            answer_unit(st, 0, 0)
        return (st,) + ov(name, [w])
    return gen


def gen_move(rng):
    st = base_state(rng)
    units = all_units(st)
    cool(st, MOVE_GUARDS + CAT_GUARDS, 0.015)
    u = unit_arg(st, units)
    kind = pick(rng, [0, 0, 30, 30, 8, 31], [rng.randrange(1 << 32), 0x11E], 0.1)
    if rng.random() < 0.5 and UNIT(0) <= u < UNIT(NUNITS):  # focused: the flyer bits of byte 6
        st.put(u + 0x2E, 1, rng.choice([4, 8, 12, 0x0C | 2]))
        st.put(u + 0x28, 1, st.mem[u + 0x28] & ~2 if rng.random() < 0.8 else st.mem[u + 0x28])
    return (st,) + ov("unit_move", [u, bool_arg(rng), s32(kind)])


def gen_unit_only(name, guards=(), p=0.04):
    def gen(rng):
        st = base_state(rng)
        units = all_units(st)
        cool(st, guards, p)
        return (st,) + ov(name, [unit_arg(st, units)])
    return gen


def gen_range(rng):
    st = base_state(rng)
    units = all_units(st)
    cool(st, (RANGE_GUARD,))
    u = unit_arg(st, units)
    item = item_arg(st, u)
    if item == 0:
        answer_items(st, 0)
    return (st,) + ov("unit_range_min", [u, item])


def gen_no_attack(rng):
    st = base_state(rng)
    units = all_units(st)
    u = unit_arg(st, units)
    o = unit_arg(st, units, 0.06, 0.06)
    if rng.random() < 0.3 and UNIT(0) <= u < UNIT(NUNITS):  # focused: the person and force tests
        st.put(u + 8, 4, word(st, u + 8) & ~0x400000)
        if UNIT(0) <= o < UNIT(NUNITS):
            st.put(o + 8, 4, word(st, o + 8) & ~0x400000)
            if rng.random() < 0.5:
                st.put(u + 0xF8, 4, word(st, o + 0x9C))
            elif rng.random() < 0.5:  # a force type of 32 or more: the game's shift gives 0
                st.put(u + 0xF8, 4, 0)
                st.put(u + 0x12E, 1, 0xFF)
                st.put(word(st, o + 0xA4) + 8, 1, rng.choice([31, 32, 33, 40, 255]))
    return (st,) + ov("unit_may_not_attack", [u, o, bool_arg(rng)])


FUNCS = {
    "unit_defense": gen_guard_stat("unit_defense", DEF_GUARDS),
    "unit_resistance": gen_guard_stat("unit_resistance", RES_GUARDS),
    "unit_max_hp": gen_max_hp,
    "hp_window_max_hp": gen_window("hp_window_max_hp"),
    "hp_window_hp": gen_window("hp_window_hp"),
    "unit_move": gen_move,
    "unit_category": gen_unit_only("unit_category", CAT_GUARDS, 0.02),
    "unit_equipped_item": gen_unit_only("unit_equipped_item"),
    "unit_equipped_item_mutable": gen_unit_only("unit_equipped_item_mutable"),
    "unit_shown_level": gen_unit_only("unit_shown_level"),
    "unit_low_level": gen_unit_only("unit_low_level", (LOW_GUARD,)),
    "unit_item_count": gen_unit_only("unit_item_count"),
    "unit_range_min": gen_range,
    "unit_may_not_attack": gen_no_attack,
    "unit_is_unique": gen_unit_only("unit_is_unique"),
    "unit_is_special_battle": gen_unit_only("unit_is_special_battle"),
    "unit_is_invisible": gen_unit_only("unit_is_invisible"),
    "unit_can_be_captured": gen_unit_only("unit_can_be_captured"),
    "unit_held_item_index": gen_unit_only("unit_held_item_index"),
}


# Planted bugs (H6 survivors, docs/harness/H6_SURVIVORS.md, round 12) that no case above told apart. make_cases runs
# SHARP from its own random stream (n // 3 cases each), so the cases of FUNCS stay exactly as they were.

def gen_max_hp_cap(rng):
    """unit_max_hp right at the cap of 99: a unit whose HP adds up to 98 .. 102 with a high limit and no boon/bane,
    no loss, no condition byte (catches the cap test `value > 99` made `value > 100`: only 100 tells them apart)."""
    st = base_state(rng)
    units = all_units(st)
    u = rng.choice(units)
    k = units.index(u)
    total = rng.choice([100, 100, 100, 99, 101, 98, 102])
    st.put(u + 0xB0, 4, 0)  # no boon/bane record
    st.put(u + 8, 4, word(st, u + 8) & ~0x40000000)  # no stat loss
    for i in range(7):
        st.put(u + 0x28 + i, 1, 0)
    st.put(PERSON(k) + 0x38, 1, (total - 60) & 0xFF)
    st.put(JOB(k) + 0x1C, 1, 60)
    st.put(u + 0xC8, 1, 0)
    st.oracle[(GET_LIMIT, u, 0)] = rng.choice([100, 120, 127])
    for a in SKILL_CACHES:  # no HP skill
        st.oracle[(IS_EQUIP, u, s32(sxs16(word(st, a, 2))))] = 0
    return (st,) + ov("unit_max_hp", [u, bool_arg(rng), rng.randrange(1 << 32), 0])


SHARP = [
    ("unit_max_hp", gen_max_hp_cap),
]

# ------------------------------------------------------------------ the ARM side
class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX to a callee of ARITY (stubbed or run as ARM code) with its
    argument registers."""

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
    return [0, cpu.r[0], mem.faults, calls_field(cpu.listed)]


# ------------------------------------------------------------------ the C side
DRIVER = r'''
/* Generated by src/readable/sheet/tests/sheet_diff.py: runs readable status-sheet functions on
   memory images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sheet.h"

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

#define MAXO 8192
static uint32_t stub_n[32], stub_f[32]; static int nstubs;
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

/* give-ups by nesting depth: one inside a guest call of another override is a finding */
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
            uint32_t addr = (uint32_t)strtoul(kind + 3, NULL, 16);
            for (int i = 0; i < 4; i++) c.r[i] = a[i];
            int found = 0;
            for (unsigned i = 0; i < sizeof ovs / sizeof ovs[0]; i++) if (ovs[i].a == addr) { ovs[i].f(&c); found = 1; }
            const char *cl = ncalls ? calls : "-";
            if (!found) printf("%u NO-OVERRIDE\n", id);
            else if (originals) printf("%u 1 %d\n", id, faults);
            else printf("%u 0 %u %d %s\n", id, c.r[0], faults, cl);
            if (writes) printf("%u WROTE-GUEST %d\n", id, writes);
            if (nested) printf("%u NESTED-GIVEUP %d\n", id, nested);
        }
    }
    return 0;
}
'''

DRIVER_OVERRIDES = sorted(set(OVERRIDES.values()))


def driver_text() -> str:
    decls = "".join(f"void override_0x{a:08X}(Context *);\n" for a in DRIVER_OVERRIDES)
    table = "static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n" + "".join(
        f"    {{0x{a:08X}u, override_0x{a:08X}}},\n" for a in DRIVER_OVERRIDES) + "};\n"
    return DRIVER.replace("@OVERRIDE_DECLS@", decls + table)


def find_cc() -> str | None:
    import check  # tools/readable/check.py: the same compiler search
    return check.find_cc()


def build_driver(cc: str, out: str, sheet_dir: str, strict: bool = True) -> str:
    """Builds the driver with every source of src/readable/, the sheet folder's taken from sheet_dir
    (a planted bug may leave a parameter unused: not strict then, warnings are not errors)."""
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "sheet_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    sources = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_SHEET)):
            continue
        sources += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    sources += [os.path.join(sheet_dir, f) for f in os.listdir(sheet_dir) if f.endswith(".c")]
    exe = os.path.join(out, "sheet_driver.exe" if os.name == "nt" else "sheet_driver")
    inc = ["-I", sheet_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
           "-I", os.path.join(ROOT, "include", "readable"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    warn = ["-Wall", "-Wextra", "-Werror"] if strict else ["-w"]
    cmd = [cc, "-std=c11"] + warn + ["-O1", "-fwrapv"] + inc + [src] + sorted(sources) + ["-o", exe]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"sheet_diff: building the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


def make_cases(text: bytes, n: int, seed: int, only: str | None):
    rng = random.Random(seed)
    lines = [f"arity {f:x} {k}" for f, k in ARITY.items()]
    expected: dict[int, tuple[str, list, tuple]] = {}
    unsupported: dict[str, int] = {}
    cid = 0
    # round 12 (F-025): SHARP's cases come from their own random stream, so the cases of FUNCS stay as they were
    sharp_rng = random.Random(seed ^ 0x5EED12)
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
        raise SystemExit(f"sheet_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
    got: dict[int, list] = {}
    flagged: dict[int, str] = {}
    for ln in r.stdout.split("\n"):
        parts = ln.split()
        if len(parts) >= 2 and parts[1] in ("WROTE-GUEST", "NO-OVERRIDE", "NESTED-GIVEUP"):
            flagged[int(parts[0])] = parts[1]
        elif parts:
            got[int(parts[0])] = [parse(x) for x in parts[1:]]
    per: dict[str, list[int]] = {}
    for c, (name, exp, inputs) in expected.items():
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
        elif g is not None and g[:1] == [1] and g[1:] == [0] and c not in flagged:
            # an early give-up: a needed cache is cold, the readable code asks before reading anything
            # (the original would reach that cache later or not at all); always safe
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
    # the defence rule table
    ("sheet_stats.c", "{{28, 3, 0x10, 4, 0}, {31, 3, 0x80, 2, 0}, {14, 1, 0x40, 2, 1}, {21, 2, 0x20, 4, 0}}, 4,",
     "{{28, 3, 0x10, 4, 0}, {31, 3, 0x80, 2, 0}, {14, 1, 0x40, 2, 1}, {21, 2, 0x10, 4, 0}}, 4,"),
    ("sheet_stats.c", "    S_DefSkillTonic, 5, 0x40, 0x80};", "    S_DefSkillTonic, 5, 0x40, 0x40};"),
    ("sheet_stats.c", "{{S_DefSkillPlus2, 2, 0}, {S_DefSkillMinus1, -1, 0}, {S_DefSkillAbsorb, 0, 1}}, 3,",
     "{{S_DefSkillPlus2, 2, 0}, {S_DefSkillMinus1, 1, 0}, {S_DefSkillAbsorb, 0, 1}}, 3,"),
    # the resistance rule table: the mood byte of defence
    ("sheet_stats.c", "    S_ResSkillTonic, 6, 0x01, 0x02};", "    S_ResSkillTonic, 5, 0x01, 0x02};"),
    ("sheet_stats.c", "{{29, 3, 0x20, 4, 0}, {31, 3, 0x80, 2, 0}, {15, 1, 0x80, 2, 1}, {22, 2, 0x40, 4, 0}}, 4,",
     "{{29, 3, 0x20, 4, 0}, {31, 3, 0x80, 2, 0}, {15, 1, 0x80, 2, 0}, {22, 2, 0x40, 4, 0}}, 4,"),
    # one guard not asked: a give-up after reads (a cold cache reached by the original)
    ("sheet_stats.c", "    SHEET_STAT_RES, {S_ResGuard0, S_ResGuard1, S_ResGuard2, 0}, 3,",
     "    SHEET_STAT_RES, {S_ResGuard0, S_ResGuard1, S_ResGuard2, 0}, 2,"),
    # the loss taken off without state bit 30
    ("sheet_stats.c", "    if (state & UNIT_STATE_LOSS)\n        value = fe_add32(value, -guest_s8",
     "    if (1)\n        value = fe_add32(value, -guest_s8"),
    # the cap compared the wrong way
    ("sheet_stats.c", "    return limit < value ? limit : value;", "    return limit <= value ? value : limit;"),
    # the stat bonus of the equipped weapon left out (the item argument only)
    ("sheet_stats.c", "    if (item == 0 && with_extras) {", "    if (item == 0 && with_extras && 0) {"),
    # the state word read again for the pair test: same values, more unmapped reads
    ("sheet_stats.c", "    uint32_t bit = (state & UNIT_STATE_SWAP_PARTNER_BIT) ? 4u : 2u;",
     "    (void)state;\n    uint32_t bit = (READ_FIELD(ctx, Unit, unit, state_flags) & UNIT_STATE_SWAP_PARTNER_BIT) ? 4u : 2u;"),
    # the debuff taken off without the third bool
    ("sheet_stats.c", "    if (with_loss)\n        value = fe_add32(value, -guest_s8(ctx, FIELD_ADDR(Unit, unit, debuff) + s));",
     "    value = fe_add32(value, -guest_s8(ctx, FIELD_ADDR(Unit, unit, debuff) + s));"),
    # HP halved rounding down instead of toward zero (shows with a negative cap)
    ("sheet_stats.c", "            value -= value / 2;", "            value -= fe_asr(value, 1);"),
    ("sheet_stats.c", "        if (kind == 8 || (condition(ctx, unit, 1) & 0x01u)) {",
     "        if (kind == 8 || (condition(ctx, unit, 1) & 0x02u)) {"),
    ("sheet_stats.c", "        if (mood & 0x08u)\n            value = fe_add32(value, -1);\n    }",
     "        if (mood & 0x08u)\n            value = fe_add32(value, -2);\n    }"),
    # the HP window without the extras
    ("sheet_stats.c", "    return unit_max_hp(ctx, unit, 1u, 0u, 0);", "    return unit_max_hp(ctx, unit, 0u, 0u, 0);"),
    ("sheet_stats.c", "    return guest_s8(ctx, unit + UNIT_HP);", "    return guest_u8(ctx, unit + UNIT_HP);"),
    # move
    ("sheet_stats.c", "    value = fe_add32(value, -(loss < 0 ? 0 : loss));", "    value = fe_add32(value, -loss);"),
    ("sheet_stats.c", "    if (!(state & UNIT_STATE_LOSS))\n        value += guest_s8(ctx, unit + UNIT_MOVE_BONUS);",
     "    value += guest_s8(ctx, unit + UNIT_MOVE_BONUS);"),
    ("sheet_stats.c", "        value = half_move_for_flyers(ctx, unit, value, 0);",
     "        value = half_move_for_flyers(ctx, unit, value, 1);"),
    # GetCategory asked once and kept: same numbers, missing guest calls
    ("sheet_stats.c", "    uint32_t category = guest_call1(ctx, SHEET_UnitGetCategory, unit);\n    gaddr job",
     "    uint32_t category = unit_category(ctx, unit);\n    gaddr job"),
    # the skill tested before the category (the game asks the category first)
    ("sheet_stats.c", "    if ((guest_call1(ctx, SHEET_UnitGetCategory, unit) & shooter) != 0 && has_skill(ctx, unit, S_MoveSkillShooter))",
     "    if (has_skill(ctx, unit, S_MoveSkillShooter) && (guest_call1(ctx, SHEET_UnitGetCategory, unit) & shooter) != 0)"),
    # GetCategory's caches not asked by the move getter: its override gives up nested
    ("sheet_stats.c", "    if (with_extras && (!fe_static_ready(ctx, S_MoveGuard3) || !fe_static_ready(ctx, S_CatGuard0) ||",
     "    if (with_extras && (!fe_static_ready(ctx, S_MoveGuard3) ||"),
    ("sheet_stats.c", "    if (condition(ctx, unit, 0) & 0x02u)\n        return 0;", "    if (condition(ctx, unit, 0) & 0x04u)\n        return 0;"),
    # sheet_unit.c
    ("sheet_unit.c", "        category &= ~(uint32_t)guest_u16(ctx, S_CatDragon);", "        category &= ~(uint32_t)guest_u16(ctx, S_CatBeast);"),
    ("sheet_unit.c", "    flags |= READ_FIELD(ctx, JobData, job, flags);\n", ""),
    ("sheet_unit.c", "    return level > 99 ? 99 : level;", "    return level > 100 ? 99 : level;"),
    ("sheet_unit.c", "        level += 20;", "        level += 10;"),
    ("sheet_unit.c", "    if (slot < 0)\n        return 0;", "    if (slot <= 0)\n        return 0;"),
    ("sheet_unit.c", "        if (guest_u16(ctx, FIELD_ADDR(Unit, unit, items) + (gaddr)slot * 4u) == 0)",
     "        if (guest_u16(ctx, FIELD_ADDR(Unit, unit, items) + (gaddr)slot * 4u + 2u) == 0)"),
    ("sheet_unit.c", "    if (range < 2)\n        return range;", "    if (range < 1)\n        return range;"),
    # the record looked up once for the bow test: same answers, one ToData call less
    ("sheet_unit.c", "    if (item_weapon_kind(ctx, item) == 4 &&", "    if (guest_u8(ctx, guest_call1(ctx, SHEET_ItemSubKindGet, (uint32_t)(int32_t)guest_s8(ctx, data + ITEM_SUBKIND)) + SUBKIND_KIND) == 4 &&"),
    ("sheet_unit.c", "    return (type < 32u && (forces & (1u << type)) != 0) ? 1u : 0u;",
     "    return (forces & (1u << (type & 31u))) != 0 ? 1u : 0u;"),
    ("sheet_unit.c", "    if (person != 0 && READ_FIELD(ctx, Unit, other, person) == person)",
     "    if (READ_FIELD(ctx, Unit, other, person) == person)"),
    ("sheet_unit.c", "    if (!(READ_FIELD(ctx, Unit, unit, state_flags) & UNIT_STATE_MAYBE_CLONE))\n        return 1;",
     "    if (!(READ_FIELD(ctx, Unit, unit, state_flags) & UNIT_STATE_MAYBE_CLONE))\n        return 0;"),
    # Job::IsGiant left out: the byte decides alone, one guest call less
    ("sheet_unit.c", "    if (guest_call1(ctx, SHEET_JobIsGiant, job) != 0)\n        return 1;\n", ""),
    # Person::IsDownload left out: a possible clone always counts as unique
    ("sheet_unit.c", "    return guest_call1(ctx, SHEET_PersonIsDownload, person) != 0 ? 1u : 0u;", "    return 1u;"),
    ("sheet_unit.c", "        category |= guest_u16(ctx, S_CatBeast);", "        category |= guest_u16(ctx, S_CatDragon);"),
    ("sheet_unit.c", "    return belong_flags(ctx, unit) & 1u;", "    return belong_flags(ctx, unit) & 2u;"),
    ("sheet_unit.c", "    if (guest_u32(ctx, person + PERSON_CAPTURE_WORD) == 0 && (belong_flags(ctx, unit) & 2u) == 0)",
     "    if ((belong_flags(ctx, unit) & 2u) == 0)"),
    # the equipped test after the staff test: other calls
    ("sheet_unit.c", "        if (guest_u16(ctx, item + 2u) & UNIT_ITEM_IS_EQUIPPED)\n            return slot;\n        if (item_weapon_kind(ctx, item) == 6 && guest_call(ctx, SHEET_UnitCanItemEquip, unit, item, 1u, 1u) != 0)",
     "        if (item_weapon_kind(ctx, item) == 6 && guest_call(ctx, SHEET_UnitCanItemEquip, unit, item, 1u, 1u) != 0)\n            return slot;\n        if (guest_u16(ctx, item + 2u) & UNIT_ITEM_IS_EQUIPPED)"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_SHEET, d, ignore=shutil.ignore_patterns("tests"))
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
    ap.add_argument("--seed", type=int, default=20261113)
    ap.add_argument("--only", help="one function name")
    ap.add_argument("--show", type=int, default=5, help="mismatches to print per function")
    ap.add_argument("--plant", action="store_true", help="also check that planted bugs are caught")
    ap.add_argument("--plant-n", type=int, default=150, help="cases per function for each planted bug")
    a = ap.parse_args(argv)
    if a.only and a.only not in FUNCS:
        print(f"unknown function {a.only}; one of: {', '.join(FUNCS)}")
        return 2
    if not os.path.isfile(TEXT):
        print("sheet_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("sheet_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_SHEET)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"sheet_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed {a.seed}")
    for name, (n, bad, cold, early) in per.items():
        total_bad += bad
        notes = ([f"{cold} cold: both reached / gave up at the cache"] if cold else []) + \
                ([f"{early} early give-ups"] if early else [])
        print(f"  {name:28s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({'; '.join(notes)})" if notes else ""))
    for name, k in unsupported.items():
        print(f"  {name:28s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("sheet_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:28s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n, a.seed + 1)
        print(f"sheet_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"sheet_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
